"""Provas da F5 — o painel, com asserções que executam de verdade.

Cada prova sobe o servidor real (uvicorn em 127.0.0.1), fala com ele por HTTP e
confere o efeito no DISCO. Nada de mock: o que estiver quebrado aparece aqui.

    .venv\\Scripts\\python -m ui.provas.prova_f5            # todas
    .venv\\Scripts\\python -m ui.provas.prova_f5 P3 P6      # só estas

O vídeo de teste é fabricado na hora com o ffmpeg (8 s, fala sintética por tom)
e servido por um HTTP local quando a prova precisa de uma URL — assim o P1 roda
o caminho de URL inteiro sem depender do YouTube nem da rede.
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

PYTHON = str(RAIZ / ".venv" / "Scripts" / "python.exe")
PORTA_PAINEL = 8799  # porta própria: não colide com o painel do usuário (8765)
PORTA_ARQUIVOS = 8798

_verde = "\033[32m"
_vermelho = "\033[31m"
_amarelo = "\033[33m"
_zero = "\033[0m"


class Falhou(AssertionError):
    pass


def confere(condicao: bool, descricao: str, detalhe: str = "") -> None:
    if condicao:
        print(f"    {_verde}ok{_zero}  {descricao}" + (f"  [{detalhe}]" if detalhe else ""))
        return
    print(f"    {_vermelho}FALHOU{_zero}  {descricao}" + (f"  [{detalhe}]" if detalhe else ""))
    raise Falhou(descricao)


# ==========================================================================
# Infraestrutura das provas
# ==========================================================================


def video_de_teste(destino: Path, segundos: int = 8) -> Path:
    """Um mp4 curto, com imagem e com FALA sintetizada por tons.

    O whisper precisa de algo para transcrever: silêncio puro sai com zero
    palavra e a seleção não teria o que cortar. Os tons não viram texto de
    verdade, mas produzem segmentos — o bastante para o pipeline atravessar.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.is_file() and destino.stat().st_size > 0:
        return destino
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=30:duration={segundos}",
        "-f", "lavfi", "-i",
        f"sine=frequency=180:duration={segundos},"
        f"atempo=1.0,aformat=sample_rates=44100:channel_layouts=stereo",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-shortest",
        str(destino),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return destino


class ServidorDeArquivos(threading.Thread):
    """HTTP local que serve uma pasta — vira a 'URL' do P1, sem rede externa."""

    def __init__(self, pasta: Path, porta: int) -> None:
        super().__init__(daemon=True)
        self.pasta = str(pasta)
        self.porta = porta
        pasta_str = self.pasta

        class Manipulador(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a: Any, **kw: Any) -> None:
                super().__init__(*a, directory=pasta_str, **kw)

            def log_message(self, *a: Any) -> None:
                pass

        self._servidor = http.server.ThreadingHTTPServer(("127.0.0.1", porta), Manipulador)

    def run(self) -> None:
        self._servidor.serve_forever(poll_interval=0.2)

    def parar(self) -> None:
        self._servidor.shutdown()
        self._servidor.server_close()


def esperar_porta(porta: int, timeout: float = 40.0, host: str = "127.0.0.1") -> bool:
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        try:
            with socket.create_connection((host, porta), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


@contextmanager
def painel(raiz_saida: Path, porta: int = PORTA_PAINEL) -> Iterator[subprocess.Popen]:
    """Sobe o painel num processo separado — é assim que ele roda de verdade."""
    ambiente = {**os.environ, "PYTHONPATH": str(RAIZ), "PYTHONUTF8": "1"}
    codigo = (
        "import uvicorn, sys;"
        "from pathlib import Path;"
        "from ui.server import criar_app;"
        f"uvicorn.run(criar_app(Path(r'{raiz_saida}')), host='127.0.0.1', port={porta},"
        " log_level='warning', access_log=False)"
    )
    proc = subprocess.Popen(
        [PYTHON, "-c", codigo],
        cwd=str(RAIZ),
        env=ambiente,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        if not esperar_porta(porta):
            proc.kill()
            saida = proc.stdout.read() if proc.stdout else ""
            raise Falhou(f"o painel não subiu na porta {porta}:\n{saida[-2000:]}")
        yield proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()


class _Cabecalhos(dict):
    """Cabeçalhos HTTP com busca insensível a caixa.

    O servidor manda 'accept-ranges' em minúsculo (todo servidor HTTP/1.1
    manda), e um dict comum não acha 'Accept-Ranges'. A primeira versão desta
    prova reprovou o servidor por isso — o defeito era da prova.
    """

    def __init__(self, cabecalhos: Any) -> None:
        super().__init__({str(k): str(v) for k, v in cabecalhos.items()})
        self._minusculo = {str(k).lower(): str(v) for k, v in cabecalhos.items()}

    def get(self, chave: str, padrao: Any = None) -> Any:  # type: ignore[override]
        return self._minusculo.get(str(chave).lower(), padrao)


def matar_arvore(proc: subprocess.Popen) -> None:
    """Mata o processo E os filhos dele.

    Matar so o pai nao simula "fechei o terminal": no Windows o ffmpeg que o
    render disparou sobrevive ao pai e continua segurando handles herdados --
    entre eles o socket do painel, que fica ocupado ate o encode terminar.
    'taskkill /T' derruba a arvore inteira, que e o que acontece de verdade
    quando o usuario fecha a janela.
    """
    subprocess.run(
        ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
        capture_output=True,
        text=True,
    )
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def pedir(
    metodo: str, caminho: str, dados: Any = None, porta: int = PORTA_PAINEL,
    host: str = "127.0.0.1", timeout: float = 30.0, cabecalhos: dict[str, str] | None = None,
) -> tuple[int, Any, dict[str, str]]:
    url = f"http://{host}:{porta}{caminho}"
    corpo = None
    cabecalhos = dict(cabecalhos or {})
    if dados is not None:
        corpo = json.dumps(dados).encode("utf-8")
        cabecalhos["content-type"] = "application/json"
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            bruto = r.read()
            tipo = r.headers.get("content-type", "")
            valor = json.loads(bruto) if "json" in tipo else bruto
            return r.status, valor, _Cabecalhos(r.headers)
    except urllib.error.HTTPError as exc:
        bruto = exc.read()
        try:
            valor = json.loads(bruto)
        except (ValueError, json.JSONDecodeError):
            valor = bruto
        return exc.code, valor, _Cabecalhos(exc.headers)


def enviar_multipart(
    caminho_arquivo: Path, campos: dict[str, str], porta: int = PORTA_PAINEL
) -> tuple[int, Any]:
    """POST multipart de verdade, montado à mão (sem dependência extra)."""
    limite = "----clipperprova"
    partes: list[bytes] = []
    for chave, valor in campos.items():
        partes.append(
            f"--{limite}\r\nContent-Disposition: form-data; name=\"{chave}\"\r\n\r\n{valor}\r\n".encode()
        )
    partes.append(
        f"--{limite}\r\nContent-Disposition: form-data; name=\"arquivo\"; "
        f"filename=\"{caminho_arquivo.name}\"\r\n"
        "Content-Type: video/mp4\r\n\r\n".encode()
    )
    partes.append(caminho_arquivo.read_bytes())
    partes.append(f"\r\n--{limite}--\r\n".encode())
    corpo = b"".join(partes)
    req = urllib.request.Request(
        f"http://127.0.0.1:{porta}/jobs",
        data=corpo,
        method="POST",
        headers={"content-type": f"multipart/form-data; boundary={limite}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def esperar_status(
    job_id: str, alvos: set[str], timeout: float = 900.0, porta: int = PORTA_PAINEL
) -> dict[str, Any]:
    """Espera o job chegar num dos status pedidos. Devolve o job."""
    limite = time.monotonic() + timeout
    ultimo: dict[str, Any] = {}
    while time.monotonic() < limite:
        codigo, job, _ = pedir("GET", f"/jobs/{job_id}", porta=porta)
        if codigo == 200 and isinstance(job, dict):
            ultimo = job
            if job.get("status") in alvos:
                return job
        time.sleep(1.0)
    raise Falhou(
        f"o job '{job_id}' não chegou em {alvos} em {timeout:.0f}s "
        f"(ficou em '{ultimo.get('status')}' no estágio '{ultimo.get('estagio')}')"
    )


def resposta_fixture(saida_base: Path, n: int = 1) -> str:
    """Um array JSON válido para o vídeo de teste, feito da transcrição real.

    A fixture NÃO é escrita à mão: ela lê as fronteiras de frase que o próprio
    clipper achou e escolhe a primeira que couber. Uma fixture fixa quebraria
    assim que o vídeo de teste mudasse de duração.
    """
    from clipper.fronteiras import Fronteiras

    transcricao = json.loads((saida_base / "transcricao.json").read_text(encoding="utf-8"))
    fronteiras = Fronteiras.de_transcricao(transcricao)
    frases = fronteiras.frases
    inicio = float(frases[0].inicio)
    fim = float(frases[-1].fim)
    return json.dumps(
        [
            {
                "inicio": round(inicio, 2),
                "fim": round(fim, 2),
                "titulo": "Trecho de teste do painel",
                "score_0_10": 9.0,
                "motivo": "fixture da prova P1/P4: cobre o vídeo inteiro.",
                "gancho_sugerido": "o gancho da fixture",
            }
        ][:n],
        ensure_ascii=False,
    )


# ==========================================================================
# Execucao
# ==========================================================================


def main(argv: list[str]) -> int:
    from ui.provas.casos import CASOS

    pedidos = [a.upper() for a in argv if a.upper() in CASOS] or list(CASOS)
    raiz = RAIZ / "_teste" / "out-provas"
    resultados: list[tuple[str, bool, float, str]] = []

    print(f"\n{'=' * 78}\nPROVAS DA F5 — painel local\n{'=' * 78}")
    print(f"  saída das provas: {raiz}")
    print(f"  vídeo de teste:   {RAIZ / '_teste' / 'clipe-curto.mp4'}\n")

    for nome in pedidos:
        descricao, funcao = CASOS[nome]
        print(f"{_amarelo}{nome}{_zero}  {descricao}")
        t0 = time.monotonic()
        try:
            funcao(raiz)
            resultados.append((nome, True, time.monotonic() - t0, ""))
        except BaseException as exc:  # noqa: BLE001 - a prova relata, nao propaga
            import traceback

            if not isinstance(exc, Falhou):
                traceback.print_exc()
            resultados.append((nome, False, time.monotonic() - t0, str(exc)[:160]))
        print()

    print(f"{'=' * 78}")
    passaram = sum(1 for _, ok, _, _ in resultados if ok)
    for nome, ok, segundos, motivo in resultados:
        marca = f"{_verde}PASSOU{_zero}" if ok else f"{_vermelho}FALHOU{_zero}"
        print(f"  {nome}  {marca}  {segundos:6.1f}s  {motivo}")
    print(f"{'=' * 78}")
    print(f"  {passaram}/{len(resultados)} provas passaram")
    return 0 if passaram == len(resultados) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
