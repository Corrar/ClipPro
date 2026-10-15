"""Provas da fase N-1 -- o worker da nuvem (RULINGS §27). Espelha prova_f61.py.

    python provas/prova_n1.py                # estruturais
    python provas/prova_n1.py --fisicas      # + fisicas (ffmpeg e anthropic)
    python provas/prova_n1.py N-E2 N-F1      # casos escolhidos

As fisicas passam pelo ponto de entrada real (`python -m worker`) e pelo
caminho real da API (SDK da Anthropic), apontado para a API FALSA de
provas/entrada_real.py: nada sai da maquina e nada e cobrado. O video e
sintetico (lavfi) e gravado em _teste/out-prova-n1/, NUNCA em
_teste/clipe-curto.mp4, que e o video com fala da prova F5 (F8a, Q18).

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from provas.prova_f6 import (  # noqa: E402
    Falhou,
    Pulou,
    _amarelo,
    _verde,
    _vermelho,
    _zero,
    confere,
)


def _pasta(raiz: Path, nome: str) -> Path:
    alvo = raiz / nome
    if alvo.exists():
        shutil.rmtree(alvo, ignore_errors=True)
    alvo.mkdir(parents=True, exist_ok=True)
    return alvo


def _valido(**mexe: Any) -> dict[str, Any]:
    base = {
        "id": "trabalho-1", "conta": "conta_1",
        "entrada": {"tipo": "link", "valor": "https://www.youtube.com/watch?v=abc"},
        "n": 3, "preset": "cortes", "limite_minutos": 300,
    }
    base.update(mexe)
    return base


def _recusa(dados: dict[str, Any]) -> list[str]:
    from worker.contrato import ErroContrato, Trabalho

    try:
        Trabalho.de_dict(dados)
    except ErroContrato as exc:
        return exc.problemas
    return []


def _worker(*args: str, env: dict[str, str], timeout: float = 900.0) -> subprocess.CompletedProcess:
    """`python -m worker <args>` num subprocesso, como o operador roda."""
    return subprocess.run(
        [sys.executable, "-B", "-m", "worker", *[str(a) for a in args]],
        cwd=str(RAIZ), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def _saida(proc: subprocess.CompletedProcess) -> str:
    return " ".join(((proc.stdout or "") + (proc.stderr or "")).split())[-200:]


def _jsons(pasta: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(pasta.glob("*.json"))]


# ==========================================================================
# Estruturais
# ==========================================================================


def e_contrato_valido(_: Path) -> None:
    """N-E1: o pedido válido passa, ida e volta, e chave desconhecida só avisa."""
    from worker.contrato import Trabalho

    t = Trabalho.de_dict(_valido(extra=1, _interna=2))
    confere(Trabalho.de_dict(t.para_dict()) == t, "ida e volta pelo dict preserva o trabalho")
    confere(t.avisos == ("chave desconhecida ignorada: 'extra'",),
            "chave desconhecida avisa (e as de fila, com '_', nem avisam)", str(t.avisos))
    confere(t.estrategia.startswith("momentos"), "sem 'estrategia', vale a padrão do clipper")


def e_contrato_recusa(_: Path) -> None:
    """N-E2: o contrato recusa tipo errado, caminho local e host privado."""
    casos = {
        "n como texto \"3\" (o D5)": _valido(n="3"),
        "n booleano": _valido(n=True),
        "n = 0": _valido(n=0),
        "n = 21": _valido(n=21),
        "preset como caminho": _valido(preset="../clipper/presets/cortes"),
        "preset fora do catálogo": _valido(preset="meu-modelo"),
        "limite como texto": _valido(limite_minutos="300"),
        "limite = 0": _valido(limite_minutos=0),
        "limite acima de 600": _valido(limite_minutos=601),
        "id com barra": _valido(id="a/b"),
        "id com maiúscula": _valido(id="Trabalho"),
        "estratégia vazia": _valido(estrategia="   "),
        "estratégia de 501 caracteres": _valido(estrategia="x" * 501),
        "entrada que não é objeto": _valido(entrada="https://youtu.be/x"),
        "tipo de entrada desconhecido": _valido(entrada={"tipo": "pasta", "valor": "x"}),
    }
    links = {
        "file://": "file:///etc/passwd",
        "ftp://": "ftp://exemplo.com/v.mp4",
        "localhost": "http://localhost:8765/",
        "127.0.0.1": "http://127.0.0.1/x",
        "10.x": "http://10.0.0.8/x",
        "192.168.x": "http://192.168.0.1/admin",
        "169.254.169.254 (metadados de nuvem)": "http://169.254.169.254/latest/",
        "[::1]": "http://[::1]/x",
        ".local": "http://impressora.local/",
        "usuário e senha no link": "https://eu:senha@youtube.com/x",
        "espaço no link": "https://youtube.com/ x",
    }
    for rotulo, url in links.items():
        casos[f"link {rotulo}"] = _valido(entrada={"tipo": "link", "valor": url})
    chaves = {
        "'..'": "../segredo.mp4",
        "caminho do Windows": "C:\\Users\\bruno\\x.mp4",
        "caminho absoluto": "/etc/hosts",
        "arquivo oculto": ".oculto.mp4",
    }
    for rotulo, chave in chaves.items():
        casos[f"arquivo com {rotulo}"] = _valido(entrada={"tipo": "arquivo", "valor": chave})

    aceitos = [rotulo for rotulo, dados in casos.items() if not _recusa(dados)]
    confere(not aceitos, f"os {len(casos)} pedidos tortos são recusados", ", ".join(aceitos))
    probs = _recusa(_valido(n="3", preset="x"))
    confere(len(probs) == 2, "a recusa traz TODOS os problemas de uma vez", str(probs))
    confere(not _recusa(_valido(entrada={"tipo": "arquivo", "valor": "live_01.mp4"})),
            "uma chave de arquivo comum passa")


def e_guarda_dns(_: Path) -> None:
    """N-E3: host público que resolve para a rede de casa é privado."""
    from worker.contrato import host_privado

    confere(host_privado("videos.exemplo.com", resolver=lambda h: ["192.168.0.10"]),
            "nome que resolve para 192.168.x é privado")
    confere(host_privado("videos.exemplo.com", resolver=lambda h: ["8.8.8.8", "::1"]),
            "basta UM endereço privado entre os resolvidos")
    confere(not host_privado("videos.exemplo.com", resolver=lambda h: ["8.8.8.8"]),
            "nome que resolve para endereço público passa")

    def falha(_: str) -> list[str]:
        raise OSError("sem DNS")

    confere(not host_privado("videos.exemplo.com", resolver=falha),
            "nome que não resolve não é privado (o ingest falha com a mensagem dele)")


def e_creditos(_: Path) -> None:
    """N-E4: 1 crédito = 1 minuto de vídeo, para cima, com tolerância de 0,5 s."""
    from worker.executor import creditos_de

    tabela = [(3.0, 1), (60.0, 1), (60.04, 1), (60.6, 2), (70.0, 2), (3600.2, 60), (0.0, 1)]
    erradas = [(d, e, creditos_de(d)) for d, e in tabela if creditos_de(d) != e]
    confere(not erradas, "a tabela de créditos bate", str(erradas))


def e_fila_reserva(raiz: Path) -> None:
    """N-E5: FIFO e reserva atômica — 8 workers, 30 trabalhos, cada um pego uma vez."""
    from worker.fila import FilaEmPasta

    fila = FilaEmPasta(_pasta(raiz, "n-e5"))
    ids = [f"t-{i:02d}" for i in range(30)]
    for i in ids:
        fila.publicar(_valido(id=i))
    pegos: list[str] = []
    trava = threading.Lock()

    def worker(nome: str) -> None:
        while (r := fila.reservar(nome)) is not None:
            with trava:
                pegos.append(r.trabalho.id)

    threads = [threading.Thread(target=worker, args=(f"w{k}",)) for k in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    confere(sorted(pegos) == ids, "cada trabalho foi reservado exatamente uma vez",
            f"{len(pegos)} reservas, {len(set(pegos))} distintas")

    fila2 = FilaEmPasta(_pasta(raiz, "n-e5b"))
    for i in ids[:5]:
        fila2.publicar(_valido(id=i))
    ordem = [fila2.reservar("w").trabalho.id for _ in range(5)]
    confere(ordem == ids[:5], "um worker só pega na ordem de chegada", str(ordem))


def e_fila_prazo(raiz: Path) -> None:
    """N-E6: reserva vencida volta; na 3ª vez falha; reserva velha não encerra a nova."""
    from worker import fila as F

    fila = F.FilaEmPasta(_pasta(raiz, "n-e6"))
    fila.publicar(_valido(id="lento"))
    velho = time.time() - 3600

    r1 = fila.reservar("w1")
    os.utime(fila.raiz / F.EM_CURSO / r1.nome, (velho, velho))
    confere(fila.devolver_expirados(60) == [r1.nome], "a reserva sem renovação volta para a fila")
    r2 = fila.reservar("w2")
    confere(r2 is not None and r2.tentativa == 2, "o próximo worker pega como 2ª tentativa")
    confere(fila.concluir(r1, {"status": "concluido"}) is False,
            "o worker antigo NÃO encerra a reserva nova")
    confere(any((fila.raiz / F.EM_CURSO).glob("*.json")), "… e a reserva nova continua em curso")

    os.utime(fila.raiz / F.EM_CURSO / r2.nome, (velho, velho))
    fila.devolver_expirados(60)
    r3 = fila.reservar("w3")
    os.utime(fila.raiz / F.EM_CURSO / r3.nome, (velho, velho))
    fila.devolver_expirados(60)
    falhos = _jsons(fila.raiz / F.FALHOS)
    confere(len(falhos) == 1 and falhos[0]["resultado"]["creditos"] == 0,
            "na 3ª reserva vencida o trabalho falha, sem crédito", str(len(falhos)))

    fila.publicar(_valido(id="torto", n="3"))
    fila.publicar(_valido(id="bom"))
    r = fila.reservar("w4")
    confere(r is not None and r.trabalho.id == "bom",
            "pedido torto vai direto para falhos e o worker pega o seguinte")
    recusado = [j for j in _jsons(fila.raiz / F.FALHOS) if j["trabalho"].get("id") == "torto"]
    confere(bool(recusado) and recusado[0]["resultado"]["status"] == "recusado"
            and "'n'" in recusado[0]["resultado"]["erro"]["detalhe"],
            "o recusado leva o motivo",
            (recusado[0]["resultado"]["erro"]["detalhe"] if recusado else "nenhum")[:100])


def e_deposito(raiz: Path) -> None:
    """N-E7: chave torta recusada; trazer a entrada é idempotente; enviar publica."""
    from worker.deposito import DepositoEmPasta, ErroDeposito

    R = _pasta(raiz, "n-e7")
    dep = DepositoEmPasta(R / "deposito")
    (R / "deposito" / "entradas" / "video.mp4").write_bytes(b"\x00" * 4096)
    for chave in ("../x.mp4", "a/b.mp4", ".oculto"):
        try:
            dep.obter_entrada(chave, R / "t")
            confere(False, f"a chave '{chave}' é recusada")
        except ErroDeposito:
            pass
    confere(True, "chaves com '..', pasta ou ponto inicial são recusadas")

    primeira = dep.obter_entrada("video.mp4", R / "t")
    marca = (primeira.stat().st_mtime_ns, primeira.stat().st_ino)
    segunda = dep.obter_entrada("video.mp4", R / "t")
    confere((segunda.stat().st_mtime_ns, segunda.stat().st_ino) == marca,
            "a 2ª chamada não recopia (retomada não baixa 1 GB de novo)")
    chave = dep.enviar("t-1", primeira)
    confere(chave == "resultados/t-1/video.mp4" and (R / "deposito" / chave).is_file(),
            "enviar publica em resultados/<trabalho>/", chave)


def e_limpeza(raiz: Path) -> None:
    """N-E8: falha tira só o pesado; sucesso tira a pasta inteira (Z4)."""
    from clipper.config import Saida
    from worker.executor import _limpar, pastas

    R = _pasta(raiz, "n-e8")
    base, entrada = pastas(R, "t-1")
    saida = Saida.para("video", base).criar_dirs()
    entrada.mkdir(parents=True)
    for p in (entrada / "video.mp4", saida.fonte_mp4, saida.audio_wav,
              saida.trabalho_dir / "baixado.mp4", saida.clips_dir / "01.mp4", saida.log):
        p.write_bytes(b"\x00")
    _limpar(base, entrada, saida, sucesso=False)
    sobrou = sorted(str(p.relative_to(base)).replace("\\", "/") for p in base.rglob("*") if p.is_file())
    confere(sobrou == ["video/clipper.log", "video/clips/01.mp4"],
            "na falha saem vídeo, áudio e bruto; ficam log e clipes", str(sobrou))
    _limpar(base, entrada, saida, sucesso=True)
    confere(not base.exists(), "no sucesso a pasta do trabalho some")


def e_porta_de_entrada(raiz: Path) -> None:
    """N-E9: `python -m worker` sem chave recusa; com pedido torto não toca o motor."""
    from provas import entrada_real as ER
    from worker.fila import FALHOS, FEITOS, FilaEmPasta

    R = _pasta(raiz, "n-e9")
    args = ("--fila", R / "fila", "--deposito", R / "dep", "--trabalhos", R / "t", "--uma-vez")
    proc = _worker(*args, env=ER.ambiente())
    confere(proc.returncode == 2 and "ANTHROPIC_API_KEY" in _saida(proc),
            "sem ANTHROPIC_API_KEY o worker recusa na partida", _saida(proc)[-100:])

    env = ER.ambiente({"ANTHROPIC_API_KEY": "chave-falsa-da-prova"})
    proc = _worker(*args, env=env)
    confere(proc.returncode == 0, "fila vazia com --uma-vez sai limpo", _saida(proc)[-100:])

    fila = FilaEmPasta(R / "fila")
    fila.publicar(_valido(id="privado", entrada={"tipo": "link", "valor": "http://192.168.0.1/"}))
    proc = _worker(*args, env=env)
    falhos = _jsons(fila.raiz / FALHOS)
    confere(proc.returncode == 0 and len(falhos) == 1
            and falhos[0]["resultado"]["status"] == "recusado"
            and not any((fila.raiz / FEITOS).glob("*.json")) and not (R / "t").exists(),
            "link para a rede de casa vai para falhos sem criar pasta de trabalho",
            _saida(proc)[-100:])


ESTRUTURAIS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "N-E1": ("contrato válido e chave desconhecida", e_contrato_valido),
    "N-E2": ("contrato recusa entrada não confiável", e_contrato_recusa),
    "N-E3": ("guarda de host privado com DNS", e_guarda_dns),
    "N-E4": ("créditos = minutos para cima", e_creditos),
    "N-E5": ("fila: FIFO e reserva atômica", e_fila_reserva),
    "N-E6": ("fila: prazo, tentativas e reserva vencida", e_fila_prazo),
    "N-E7": ("depósito: chave, idempotência, envio", e_deposito),
    "N-E8": ("limpeza das fontes", e_limpeza),
    "N-E9": ("porta de entrada `python -m worker`", e_porta_de_entrada),
}


# ==========================================================================
# Fisicas
# ==========================================================================


def _exigir_fisicas() -> None:
    if shutil.which("ffmpeg") is None:
        raise Pulou("sem ffmpeg neste ambiente.")
    try:
        import anthropic  # noqa: F401
    except ImportError as exc:
        raise Pulou(f"sem o pacote anthropic ({exc}).") from None


def _preparar(raiz: Path, nome: str, limite: int) -> dict[str, Any]:
    """Fila + depósito + vídeo enviado, com a transcrição semeada.

    A transcricao sintetica entra pelo mesmo caminho da F-I1 (ER.semear): o
    lavfi nao tem fala. O video e trazido do deposito pela MESMA funcao que o
    worker usa, entao a assinatura do ingest bate e o estagio reaproveita.
    """
    from provas import entrada_real as ER
    from worker.deposito import DepositoEmPasta
    from worker.executor import pastas
    from worker.fila import FilaEmPasta

    R = _pasta(raiz, nome)
    video = ER.video_lavfi(raiz / "videos" / "fonte-n1.mp4", 70.0)
    dep = DepositoEmPasta(R / "deposito")
    shutil.copy2(video, R / "deposito" / "entradas" / "fonte-n1.mp4")
    base, pasta_entrada = pastas(R / "trabalhos", nome)
    local = dep.obter_entrada("fonte-n1.mp4", pasta_entrada)
    trans = ER.transcricao_sintetica(68.0)
    ER.semear(base, "fonte-n1", trans, video=local)
    fila = FilaEmPasta(R / "fila")
    fila.publicar(_valido(id=nome, entrada={"tipo": "arquivo", "valor": "fonte-n1.mp4"},
                          n=1, limite_minutos=limite))
    return {"R": R, "fila": fila, "base": base, "entrada": pasta_entrada,
            "frases": ER.frases(trans)}


def _rodar_com_api_falsa(cen: dict[str, Any]) -> tuple[subprocess.CompletedProcess, list[dict[str, Any]]]:
    from clipper.fronteiras import mmss
    from provas import entrada_real as ER

    frs = cen["frases"]

    def responder(_: dict[str, Any]) -> list[dict[str, Any]]:
        # Um clipe v1 de 8 frases (~31 s): dentro de 20-90 s do validador.
        return [ER.item(titulo="Clipe do worker", inicio=mmss(frs[0].inicio), fim=mmss(frs[7].fim))]

    R = cen["R"]
    with ER.api_falsa(responder) as (url, pedidos):
        env = ER.ambiente({"ANTHROPIC_BASE_URL": url, "ANTHROPIC_API_KEY": "chave-falsa-da-prova",
                           "NO_PROXY": "127.0.0.1,localhost"})
        proc = _worker("--fila", R / "fila", "--deposito", R / "deposito",
                       "--trabalhos", R / "trabalhos", "--uma-vez", env=env)
    return proc, pedidos


def f_ponta_a_ponta(raiz: Path) -> None:
    """N-F1: um vídeo enviado vira clipe no depósito, com tempo e créditos medidos."""
    from provas import entrada_real as ER
    from worker.fila import FEITOS

    _exigir_fisicas()
    cen = _preparar(raiz, "n-f1", limite=300)
    proc, pedidos = _rodar_com_api_falsa(cen)
    confere(proc.returncode == 0, "`python -m worker --uma-vez` termina bem", _saida(proc))

    feitos = _jsons(cen["fila"].raiz / FEITOS)
    confere(len(feitos) == 1, "o trabalho foi para feitos/", f"{len(feitos)} arquivo(s)")
    res = feitos[0]["resultado"]
    confere(res["status"] == "concluido" and res["creditos"] == 2,
            "concluído, 70 s de vídeo = 2 créditos", f"{res['status']}, {res.get('creditos')}")
    estagios = set(res.get("segundos_por_estagio") or {})
    confere({"ingestao", "transcricao", "energia", "selecao", "render"} <= estagios,
            "o tempo de cada estágio foi medido", ", ".join(sorted(estagios)))

    chamadas = [p for p in pedidos if p["caminho"].rstrip("/").endswith("/v1/messages")]
    confere(len(chamadas) == 1 and "haiku" in str(chamadas[0]["corpo"].get("model")),
            "uma chamada à API, no modelo haiku", f"{len(chamadas)} chamada(s)")

    clipes = res.get("clipes") or []
    confere(len(clipes) == 1, "um clipe no resultado")
    arquivos = clipes[0]["arquivos"]
    dep = cen["R"] / "deposito"
    confere(set(arquivos) == {"video", "capa", "publicacao"}
            and all((dep / c).is_file() for c in arquivos.values()),
            "MP4, capa e texto de publicação estão no depósito", str(sorted(arquivos)))
    medida = ER.duracao_medida(dep / arquivos["video"])
    confere(abs(medida - (cen["frases"][7].fim - cen["frases"][0].inicio)) <= 1.0,
            "a duração do MP4 bate com o trecho escolhido ±1 s", f"{medida:.2f} s")
    confere(not cen["base"].exists(), "a pasta local do trabalho foi apagada (Z4)")
    print(f"    medida  {res['segundos_total']:.1f} s no total; "
          + ", ".join(f"{k} {v:.1f} s" for k, v in res["segundos_por_estagio"].items()))


def f_limite_de_minutos(raiz: Path) -> None:
    """N-F2: vídeo maior que o saldo falha antes da IA, sem crédito, e limpa."""
    from worker.fila import FALHOS, FEITOS

    _exigir_fisicas()
    cen = _preparar(raiz, "n-f2", limite=1)
    proc, pedidos = _rodar_com_api_falsa(cen)
    confere(proc.returncode == 0, "o worker termina bem mesmo recusando", _saida(proc))
    falhos = _jsons(cen["fila"].raiz / FALHOS)
    confere(len(falhos) == 1 and not any((cen["fila"].raiz / FEITOS).glob("*.json")),
            "o trabalho foi para falhos/")
    res = falhos[0]["resultado"]
    confere("saldo" in res["erro"]["mensagem"] and res["creditos"] == 0,
            "a mensagem fala do saldo e nenhum crédito é usado", res["erro"]["mensagem"])
    confere(not [p for p in pedidos if p["caminho"].rstrip("/").endswith("/v1/messages")],
            "a API não foi chamada")
    saida = cen["base"] / "fonte-n1"
    confere(not (saida / "fonte.mp4").exists() and not cen["entrada"].exists()
            and (cen["base"] / "worker.log").is_file(),
            "fontes apagadas, log mantido para diagnóstico")
    confere(not (cen["R"] / "deposito" / "resultados" / "n-f2").exists(),
            "nada foi publicado no depósito")


FISICAS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "N-F1": ("ponta a ponta pelo worker e pela API falsa", f_ponta_a_ponta),
    "N-F2": ("limite de minutos antes da IA", f_limite_de_minutos),
}


# ==========================================================================


def main(argv: list[str]) -> int:
    quer_fisicas = "--fisicas" in argv
    nomes = [a.upper() for a in argv if not a.startswith("--")]

    casos: dict[str, tuple[str, Callable[[Path], None]]] = dict(ESTRUTURAIS)
    if quer_fisicas:
        casos.update(FISICAS)
    desconhecidos = [n for n in nomes if n not in casos]
    if desconhecidos:
        # Nome errado nao roda "tudo" calado (o menor do recon do F8a).
        print(f"prova desconhecida: {', '.join(desconhecidos)}. Disponíveis: {', '.join(casos)}")
        return 2
    pedidos = nomes or list(casos)
    raiz = RAIZ / "_teste" / "out-prova-n1"

    titulo = "PROVAS DA N-1 — worker da nuvem"
    if not quer_fisicas:
        titulo += "  (só ESTRUTURAIS; use --fisicas para as demais)"
    print(f"\n{'=' * 78}\n{titulo}\n{'=' * 78}\n")

    resultados: list[tuple[str, str, float, str]] = []
    for nome in pedidos:
        descricao, funcao = casos[nome]
        print(f"{_amarelo}{nome}{_zero}  {descricao}")
        t0 = time.monotonic()
        try:
            funcao(raiz)
            resultados.append((nome, "passou", time.monotonic() - t0, ""))
        except Pulou as exc:
            print(f"    {_amarelo}pulou{_zero}  {exc}")
            resultados.append((nome, "pulou", time.monotonic() - t0, str(exc)[:160]))
        except BaseException as exc:  # noqa: BLE001 - a prova relata, nao propaga
            if not isinstance(exc, Falhou):
                import traceback

                traceback.print_exc()
            resultados.append((nome, "falhou", time.monotonic() - t0, str(exc)[:160]))
        print()

    print("=" * 78)
    marcas = {
        "passou": f"{_verde}PASSOU{_zero}",
        "pulou": f"{_amarelo}PULOU {_zero}",
        "falhou": f"{_vermelho}FALHOU{_zero}",
    }
    for nome, estado, segundos, motivo in resultados:
        print(f"  {nome:6} {marcas[estado]}  {segundos:6.2f}s  {motivo}")
    passaram = sum(1 for _, e, _, _ in resultados if e == "passou")
    pularam = sum(1 for _, e, _, _ in resultados if e == "pulou")
    falharam = sum(1 for _, e, _, _ in resultados if e == "falhou")
    print("=" * 78)
    print(f"  {passaram} passaram, {pularam} pularam, {falharam} falharam")
    if not quer_fisicas:
        print(f"  {len(FISICAS)} prova(s) FÍSICA(S) não executada(s) (precisam de ffmpeg).")
    return 1 if falharam else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
