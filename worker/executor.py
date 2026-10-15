"""Roda UM trabalho de ponta a ponta: entrada -> motor -> deposito -> limpeza.

O motor e o mesmo do CLI e do painel: motor.montar_estagios/rodar_estagios,
como ui/jobs.py. O que e so do worker:

1. A ENTRADA E NAO CONFIAVEL (ver worker/contrato.py). Link passa pela guarda
   de host privado, agora com DNS; arquivo vem do deposito para a pasta do
   trabalho -- nunca um caminho que o usuario escolheu.
2. O LIMITE DE MINUTOS E CONFERIDO LOGO DEPOIS DA INGESTAO, antes do whisper.
   1 credito = 1 minuto de video (RULINGS §26, N7 = A); um video maior que o
   saldo reservado nao gasta a transcricao (~0,7x a duracao, a parte cara).
   Para link, o download ja aconteceu: e o preco de nao perguntar a duracao
   ao yt-dlp duas vezes (declarado no relatorio da N-1).
3. A PASTA E POR TRABALHO, NAO POR VIDEO. O painel usa "o job e o slug"
   porque tem um usuario so; na nuvem, dois usuarios mandando o mesmo video
   nao podem dividir pasta, selecao nem clipes.
4. LIMPEZA (relatorio da nuvem, Z4): video pesa ~1 GB a cada 30 min. Com
   sucesso, os clipes ja foram para o deposito e a pasta inteira sai. Com
   falha, saem as fontes (video, audio, bruto); ficam log e JSONs para
   diagnostico.

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import json
import math
import shutil
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from clipper import config, motor, registro
from clipper.config import Estado, Saida
from clipper.erros import ErroClipper
from worker.contrato import Trabalho, host_privado, resolver_dns
from worker.deposito import ErroDeposito

PASTA_ENTRADA = "_entrada"
# Tolerancia do arredondamento: o ffprobe mede 60,04 s num video de 1 min, e
# cobrar 2 creditos por isso seria injusto. A regra final de cobranca e da N-3.
TOLERANCIA_S = 0.5


class ErroTrabalho(Exception):
    """Recusa com mensagem para quem pediu (link privado, saldo, nada gerado)."""

    def __init__(self, mensagem: str, sugestao: str = "", detalhe: str = "") -> None:
        self.mensagem, self.sugestao, self.detalhe = mensagem, sugestao, detalhe
        super().__init__(mensagem)


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def pastas(trabalho_dir: Path, trabalho_id: str) -> tuple[Path, Path]:
    """(base do trabalho, pasta onde o video enviado e copiado)."""
    base = Path(trabalho_dir) / trabalho_id
    return base, base / PASTA_ENTRADA


def creditos_de(duracao_s: float) -> int:
    """Minutos de video arredondados para cima, minimo 1 (§26, N7 = A)."""
    return max(1, math.ceil(max(0.0, float(duracao_s) - TOLERANCIA_S) / 60.0))


def executar(
    trabalho: Trabalho,
    deposito: Any,
    trabalho_dir: Path,
    *,
    worker: str,
    resolver: Callable[[str], list[str]] = resolver_dns,
    modelo: str = motor.MODELO_PADRAO,
    modelo_whisper: str = config.MODELO_WHISPER_PADRAO,
) -> dict[str, Any]:
    """Devolve o resultado (sempre um dict; nunca levanta)."""
    base, pasta_entrada = pastas(trabalho_dir, trabalho.id)
    base.mkdir(parents=True, exist_ok=True)
    medidos: dict[str, float] = {}
    contexto: dict[str, Any] = {"saida": None, "duracao": None, "uso_api": None}
    resultado: dict[str, Any] = {
        "worker": worker,
        "iniciado_em": agora(),
        "segundos_por_estagio": medidos,
        "avisos": list(trabalho.avisos),
    }
    t0 = time.monotonic()

    with registro.em_arquivo(base / "worker.log"):
        log = registro.obter()
        log.info(f"trabalho {trabalho.id} (conta {trabalho.conta}): "
                 f"{trabalho.entrada_tipo}, {trabalho.n} cortes, preset {trabalho.preset}")
        try:
            clipes = _rodar(trabalho, deposito, base, pasta_entrada, medidos, contexto,
                            resolver, modelo, modelo_whisper)
            resultado.update(status="concluido", erro=None, clipes=clipes,
                             creditos=creditos_de(contexto["duracao"]))
        except ErroTrabalho as exc:
            resultado.update(status="falhou", erro={
                "mensagem": exc.mensagem, "sugestao": exc.sugestao, "detalhe": exc.detalhe})
        except ErroClipper as exc:
            resultado.update(status="falhou", erro={
                "mensagem": exc.mensagem, "sugestao": exc.sugestao or "",
                "detalhe": exc.detalhe or ""})
        except ErroDeposito as exc:
            resultado.update(status="falhou", erro={
                "mensagem": exc.mensagem, "sugestao": "envie o vídeo de novo.", "detalhe": ""})
        except Exception as exc:  # noqa: BLE001 - o trabalho tem de terminar
            log.error("erro inesperado no trabalho:\n" + traceback.format_exc())
            resultado.update(status="falhou", erro={
                "mensagem": "o processamento encontrou um erro inesperado.",
                "sugestao": "tente de novo; nenhum crédito foi usado.",
                "detalhe": f"{type(exc).__name__}: {exc}"})
        if resultado["status"] != "concluido":
            resultado["creditos"] = 0
            log.info(f"trabalho {trabalho.id} falhou: {resultado['erro']['mensagem']}")

    resultado["duracao_video_s"] = contexto["duracao"]
    # Tokens que a API cobrou neste trabalho (§28, P2). None = a selecao foi
    # reaproveitada ou nem chegou a rodar (ex.: recusa por saldo).
    resultado["uso_api"] = contexto["uso_api"]
    resultado["segundos_total"] = round(time.monotonic() - t0, 2)
    resultado["terminado_em"] = agora()
    _limpar(base, pasta_entrada, contexto["saida"], sucesso=resultado["status"] == "concluido")
    return resultado


def _rodar(
    trabalho: Trabalho,
    deposito: Any,
    base: Path,
    pasta_entrada: Path,
    medidos: dict[str, float],
    contexto: dict[str, Any],
    resolver: Callable[[str], list[str]],
    modelo: str,
    modelo_whisper: str,
) -> list[dict[str, Any]]:
    from clipper.pipeline import ingest
    from ui import jobs  # so a leitura dos clipes; jobs.py nao importa fastapi

    if trabalho.entrada_tipo == "link":
        host = urlsplit(trabalho.entrada_valor).hostname or ""
        if host_privado(host, resolver=resolver):
            raise ErroTrabalho("o link aponta para um endereço local ou privado.",
                               sugestao="use o link público do vídeo.")
        entrada = trabalho.entrada_valor
    else:
        entrada = str(deposito.obter_entrada(trabalho.entrada_valor, pasta_entrada))

    origem = ingest.resolver_origem(entrada)
    # Defesa em profundidade: o tipo que o motor enxergou tem de ser o pedido.
    if origem.tipo != {"link": "url", "arquivo": "arquivo"}[trabalho.entrada_tipo]:
        raise ErroTrabalho("a entrada do trabalho não é do tipo declarado.",
                           detalhe=f"pedido {trabalho.entrada_tipo}, motor viu {origem.tipo}")

    saida = Saida.para(origem.slug, base).criar_dirs()
    contexto["saida"] = saida
    estado = Estado(saida.estado_json)
    opcoes = motor.Opcoes(
        out=base, n=trabalho.n, estrategia=trabalho.estrategia, preset=trabalho.preset,
        modelo=modelo, modelo_whisper=modelo_whisper, usar_api=True,
    )
    estagios = motor.montar_estagios(opcoes, origem, saida, estado, frozenset())
    primeiro, *resto = motor.ESTAGIOS_POR_COMANDO["run"]

    motor.rodar_estagios([estagios[primeiro]], medidos, tolerar_pendentes=False)
    duracao = _duracao(saida)
    contexto["duracao"] = duracao
    minutos = creditos_de(duracao)
    if minutos > trabalho.limite_minutos:
        raise ErroTrabalho(
            f"o vídeo tem {minutos} min e o saldo reservado cobre {trabalho.limite_minutos} min.",
            sugestao="envie um trecho menor do vídeo ou compre mais créditos.",
            detalhe=f"duração medida {duracao:.1f} s",
        )

    def ao_concluir(est: motor.Estagio, res: Any, _segundos: float) -> None:
        if isinstance(res, dict) and res.get("uso_api"):
            contexto["uso_api"] = res["uso_api"]

    parada = motor.rodar_estagios(
        [estagios[n] for n in resto if n in estagios], medidos,
        tolerar_pendentes=False, ao_concluir=ao_concluir,
    )
    if parada is not None:
        raise ErroTrabalho("a escolha dos cortes não terminou.",
                           detalhe=f"parada '{parada.motivo}' em {parada.estagio.nome}")

    clipes = jobs.clipes_do_job(saida, trabalho.preset)
    if not clipes:
        raise ErroTrabalho("nenhum corte foi gerado para este vídeo.")
    enviados = []
    for c in clipes:
        mp4 = saida.base / str(c["arquivo"])
        arquivos = {
            "video": mp4,
            "capa": mp4.with_name(mp4.stem + ".capa.jpg"),
            "publicacao": mp4.with_name(mp4.stem + ".publicacao.md"),
        }
        chaves = {k: deposito.enviar(trabalho.id, p) for k, p in arquivos.items() if p.is_file()}
        enviados.append({
            **{k: c.get(k) for k in ("id", "titulo", "score", "motivo", "gancho", "duracao", "bytes")},
            "arquivos": chaves,
        })
    return enviados


def _duracao(saida: Saida) -> float:
    dados = json.loads(saida.fonte_info_json.read_text(encoding="utf-8"))
    return float(dados["midia"]["duracao"])


def _limpar(base: Path, pasta_entrada: Path, saida: Saida | None, *, sucesso: bool) -> None:
    if sucesso:
        shutil.rmtree(base, ignore_errors=True)
        return
    shutil.rmtree(pasta_entrada, ignore_errors=True)
    if saida is None:
        return
    for pesado in (saida.fonte_mp4, saida.audio_wav):
        try:
            pesado.unlink()
        except FileNotFoundError:
            pass
    shutil.rmtree(saida.trabalho_dir, ignore_errors=True)
