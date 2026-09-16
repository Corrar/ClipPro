"""Apoio das provas do P5: tudo passa pelo PONTO DE ENTRADA REAL.

RULINGS §13.1: prova de integracao atravessa o CLI (`python -m clipper ...`)
e o caminho do painel (`ui/jobs.py`). Prova que monta o ffmpeg a mao prova o
filtergraph, nao o pipeline -- foi assim que D-B..D-F passaram verdes.

O que este modulo NAO faz: montar filtergraph, chamar composicao.montar() ou
escrever a linha do ffmpeg. O que ele faz e preparar a pasta de saida que o
CLI espera encontrar e, depois, chamar o CLI de verdade.

Duas formas de semear out/<slug>/:

  - ESTRUTURAL (sem ffmpeg, sem whisper): o video de entrada e um arquivo de
    1 byte, o fonte.mp4 tambem, o audio.wav e um seno gerado em Python. Os
    estagios de ingestao e transcricao sao registrados no .estado.json com a
    MESMA assinatura que o CLI calcula, entao `clipper select` pula direto para
    a selecao. A energia roda de verdade (e Python puro sobre o wav).
    Medido: `select` pelo CLI assim nao abre ffmpeg nem ffprobe.

  - FISICA: o video de entrada e um mp4 lavfi de verdade e a ingestao roda de
    verdade (remux + extracao do wav). Transcricao sintetica registrada do
    mesmo jeito -- whisper sobre tom de teste nao produz fala, e a prova nao e
    sobre o whisper.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import struct
import subprocess
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterator

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


# --------------------------------------------------------------------------
# Transcricao sintetica
# --------------------------------------------------------------------------


def transcricao_sintetica(
    duracao_s: float,
    *,
    pausas: tuple[tuple[float, float], ...] = (),
    inicio: float = 0.5,
    palavras_por_frase: int = 6,
    passo: float = 0.65,
    duracao_palavra: float = 0.6,
) -> dict[str, Any]:
    """Transcricao no formato do transcribe.py, com frases regulares.

    Cada frase tem `palavras_por_frase` palavras e termina em ponto, entao a
    fronteira de frase e previsivel: a frase k abre em inicio + k*6*passo
    (fora das pausas). `pausas` sao intervalos SEM fala -- e silencio longo
    que torna testavel a diferenca entre "blocos consecutivos" e "blocos
    colados".
    """
    palavras: list[dict[str, Any]] = []
    t, i = float(inicio), 0
    while t + palavras_por_frase * passo < duracao_s:
        for a, b in pausas:
            if a <= t < b:
                t = float(b)
        if t + palavras_por_frase * passo >= duracao_s:
            break
        for k in range(palavras_por_frase):
            palavras.append({
                "i": i, "seg": 0,
                "inicio": round(t, 3), "fim": round(t + duracao_palavra, 3),
                "texto": f"p{i}" + ("." if k == palavras_por_frase - 1 else ""),
                "prob": 0.9,
            })
            t += passo
            i += 1
    return {
        "idioma": "pt",
        "duracao_audio": float(duracao_s),
        "segmentos": [{"id": 0, "inicio": palavras[0]["inicio"],
                       "fim": palavras[-1]["fim"], "texto": "sintetico", "palavras": []}],
        "palavras": palavras,
    }


def frases(transcricao: dict[str, Any]):
    from clipper.fronteiras import Fronteiras

    return Fronteiras.de_transcricao(transcricao).frases


# --------------------------------------------------------------------------
# Semeadura de out/<slug>/
# --------------------------------------------------------------------------


def _wav_seno(destino: Path, segundos: float) -> None:
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        amostras = int(16000 * segundos)
        w.writeframes(b"".join(
            struct.pack("<h", int(8000 * math.sin(k / 7.0))) for k in range(amostras)
        ))


def semear(
    raiz: Path,
    nome: str,
    transcricao: dict[str, Any],
    *,
    video: Path | None = None,
    segundos_wav: float = 10.0,
) -> tuple[Path, Any]:
    """Prepara raiz/<slug>/ para o CLI. Devolve (entrada, saida).

    `video=None` e a forma ESTRUTURAL; com um mp4 de verdade, a FISICA.
    A entrada devolvida e o que se passa ao CLI no lugar do video.
    """
    from clipper.config import Estado, Saida, escrever_json
    from clipper.pipeline import ingest, transcribe

    raiz = Path(raiz)
    fontes = raiz / "_entradas"
    fontes.mkdir(parents=True, exist_ok=True)

    if video is None:
        entrada = fontes / f"{nome}.mp4"
        entrada.write_bytes(b"\x00")
    else:
        entrada = Path(video)

    origem = ingest.resolver_origem(str(entrada))
    saida = Saida.para(origem.slug, raiz).criar_dirs()
    estado = Estado(saida.estado_json)

    if video is None:
        saida.fonte_mp4.write_bytes(b"\x00")
        _wav_seno(saida.audio_wav, segundos_wav)
        escrever_json(saida.fonte_info_json, {"origem": {
            "tipo": origem.tipo, "valor": origem.valor,
            "titulo": origem.titulo, "id_remoto": None,
        }})
        st = Path(origem.valor).stat()
        # A mesma assinatura que ingest.ingerir calcula para arquivo local.
        estado.marcar(ingest.ESTAGIO, {
            "origem": origem.valor, "tipo": origem.tipo, "reencodar": False,
            "bytes": st.st_size, "mtime": int(st.st_mtime),
        })
    else:
        ingest.ingerir(origem, saida, estado)

    escrever_json(saida.transcricao_json, transcricao)
    transcribe.escrever_srt(transcricao, saida.transcricao_srt)
    device, compute_type = transcribe.detectar_dispositivo()
    # A assinatura que o CLI calcula com os padroes (medium, pt, vad).
    estado.marcar(transcribe.ESTAGIO_TRANSCRICAO, {
        "modelo": "medium", "idioma": "pt", "vad": True,
        "device": device, "compute_type": compute_type,
        **transcribe._impressao_audio(saida),
    })
    transcribe.calcular_energia(saida, estado)
    return entrada, saida


def gravar_resposta(raiz: Path, nome: str, itens: list[dict[str, Any]]) -> Path:
    destino = Path(raiz) / "_entradas" / f"{nome}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(itens, ensure_ascii=False, indent=2),
                       encoding="utf-8", newline="\n")
    return destino


def item(**campos: Any) -> dict[str, Any]:
    base = {"titulo": "Um título sintético", "score_0_10": 8.0,
            "motivo": "um motivo", "gancho_sugerido": "um gancho"}
    base.update(campos)
    return base


# --------------------------------------------------------------------------
# CLI de verdade
# --------------------------------------------------------------------------


def ambiente(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("ANTHROPIC") and k != "CLIPPER_ANTHROPIC_API_KEY"}
    env.update(PYTHONPATH=str(RAIZ), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
               PYTHONIOENCODING="utf-8")
    env.update(extra or {})
    return env


def cli(*args: str, env: dict[str, str] | None = None,
        timeout: float = 900.0) -> subprocess.CompletedProcess:
    """`python -m clipper <args>` num subprocesso, como o usuario roda."""
    return subprocess.run(
        [sys.executable, "-B", "-m", "clipper", *[str(a) for a in args]],
        cwd=str(RAIZ), env=env or ambiente(), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def saida_do_cli(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout or "") + (proc.stderr or "")


def cli_em_processo(argv: list[str]) -> int:
    """`clipper.cli.main(argv)` no mesmo processo.

    E a MESMA funcao que `python -m clipper` chama (clipper/__main__.py). Existe
    para as provas que precisam OBSERVAR uma chamada interna com um espiao --
    um espiao que so registra e repassa, sem trocar comportamento.
    """
    from clipper import cli as cli_mod

    try:
        return int(cli_mod.main(argv) or 0)
    except SystemExit as exc:
        return int(exc.code or 0)


# --------------------------------------------------------------------------
# Caminho do painel
# --------------------------------------------------------------------------


def job_do_painel(raiz: Path, slug: str, entrada: Path, *, comando: str,
                  somente: tuple[str, ...] | None = None, timeout: float = 900.0,
                  **opcoes: Any) -> dict[str, Any]:
    """Roda UM job pela fila do painel (ui/jobs.py), sem subir o uvicorn.

    E a mesma Fila que o server.py usa: enfileira, o worker executa via
    motor.montar_estagios/rodar_estagios, e o resultado sai do job.json.
    """
    from clipper import motor
    from ui import jobs as filas

    fila = filas.Fila(Path(raiz))
    fila.iniciar()
    try:
        fila.enfileirar(filas.Pedido(
            slug=slug, entrada=str(entrada),
            opcoes=motor.Opcoes(out=Path(raiz), **opcoes),
            comando=comando, somente=somente,
        ))
        limite = time.monotonic() + timeout
        while fila._fila.unfinished_tasks:
            if time.monotonic() > limite:
                raise TimeoutError(f"o job do painel não terminou em {timeout:.0f}s")
            time.sleep(0.2)
    finally:
        fila.encerrar()
    return filas.ler_job(Path(raiz) / slug) or {}


# --------------------------------------------------------------------------
# API falsa (SDK real, servidor local)
# --------------------------------------------------------------------------


@contextlib.contextmanager
def api_falsa(
    responder: Callable[[dict[str, Any]], list[dict[str, Any]]],
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Servidor HTTP local que fala o bastante da Messages API para o SDK real.

    `responder(esquema)` recebe o JSON Schema que CHEGOU na requisicao
    (output_config.format.schema) e devolve a lista de clipes. Assim o "modelo"
    falso obedece ao esquema como o structured outputs obriga o real a
    obedecer -- e a prova morde exatamente onde esquema e validador divergem.
    Nada sai da maquina: ANTHROPIC_BASE_URL aponta para 127.0.0.1.
    """
    pedidos: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:  # silencio no console da prova
            pass

        def do_POST(self) -> None:  # noqa: N802 - nome imposto pela stdlib
            tamanho = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(tamanho) or b"{}")
            pedidos.append({"caminho": self.path, "corpo": corpo})
            if self.path.endswith("/count_tokens"):
                resposta: dict[str, Any] = {"input_tokens": 1}
            else:
                esquema = ((corpo.get("output_config") or {}).get("format") or {}).get("schema") or {}
                clipes = responder(esquema)
                resposta = {
                    "id": f"msg_prova_{len(pedidos)}", "type": "message",
                    "role": "assistant", "model": corpo.get("model", "x"),
                    "content": [{"type": "text",
                                 "text": json.dumps({"clipes": clipes}, ensure_ascii=False)}],
                    "stop_reason": "end_turn", "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            dados = json.dumps(resposta).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{servidor.server_address[1]}", pedidos
    finally:
        servidor.shutdown()
        servidor.server_close()


def conforme(esquema: dict[str, Any], valor: Any, caminho: str = "$") -> list[str]:
    """Confere `valor` contra o subconjunto de JSON Schema que ESQUEMA_JSON usa.

    Sem dependencia nova (jsonschema nao esta no ambiente): type, properties,
    required, additionalProperties, items, minItems, maxItems.
    """
    erros: list[str] = []
    tipo = esquema.get("type")
    tipos = {"object": dict, "array": list, "string": str}
    if tipo == "number":
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            return [f"{caminho}: esperava number"]
    elif tipo in tipos and not isinstance(valor, tipos[tipo]):
        return [f"{caminho}: esperava {tipo}"]
    if tipo == "object":
        props = esquema.get("properties") or {}
        for campo in esquema.get("required") or []:
            if campo not in valor:
                erros.append(f"{caminho}: falta required {campo!r}")
        if esquema.get("additionalProperties") is False:
            for campo in valor:
                if campo not in props:
                    erros.append(f"{caminho}: campo extra {campo!r}")
        for campo, sub in props.items():
            if campo in valor:
                erros += conforme(sub, valor[campo], f"{caminho}.{campo}")
    if tipo == "array":
        if "minItems" in esquema and len(valor) < esquema["minItems"]:
            erros.append(f"{caminho}: menos que minItems")
        if "maxItems" in esquema and len(valor) > esquema["maxItems"]:
            erros.append(f"{caminho}: mais que maxItems")
        for k, sub in enumerate(valor):
            erros += conforme(esquema.get("items") or {}, sub, f"{caminho}[{k}]")
    return erros


# --------------------------------------------------------------------------
# Video e medicoes
# --------------------------------------------------------------------------


def video_lavfi(destino: Path, segundos: float) -> Path:
    """Video de entrada sintetico (gerador lavfi ja aceito no P0.5)."""
    from provas.gerar_clipe_curto import gerar

    if Path(destino).is_file():
        return Path(destino)
    return gerar(Path(destino), float(segundos))


def duracao_medida(caminho: Path) -> float:
    from clipper import ffmpeg_utils

    return float(ffmpeg_utils.sondar(Path(caminho)).duracao)


def clipes_mp4(saida: Any, preset: str) -> list[Path]:
    return sorted(Path(saida.clips_dir).glob(f"*--{preset}.mp4"))
