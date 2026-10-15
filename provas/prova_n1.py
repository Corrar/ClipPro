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

import contextlib
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterator

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


# --------------------------------------------------------------------------
# Nuvem (§28): assinatura, R2 e Supabase contra servidores falsos locais
# --------------------------------------------------------------------------


@contextlib.contextmanager
def _s3_falso(segredo: str) -> Iterator[tuple[str, dict[str, Any], list[tuple[str, str, int]]]]:
    """S3 local que RECALCULA a assinatura de cada pedido e recusa a errada.

    Confere o que viajou (Host com porta, cabecalhos assinados, hash do
    corpo), nao so o algoritmo -- este a N-E10 confere contra a AWS.
    """
    from worker.nuvem import assinar_s3

    objetos: dict[str, Any] = {}
    pedidos: list[tuple[str, str, int]] = []
    padrao = re.compile(
        r"AWS4-HMAC-SHA256 Credential=([^/]+)/(\d{8})/([^/]+)/s3/aws4_request, "
        r"SignedHeaders=([^,]+), Signature=([0-9a-f]{64})$")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            pass

        def _valido(self, corpo: bytes) -> bool:
            auth = self.headers.get("Authorization", "")
            m = padrao.match(auth)
            if not m:
                return False
            chave_id, _, regiao, assinados, _ = m.groups()
            carga = self.headers.get("x-amz-content-sha256", "")
            if self.command == "PUT" and hashlib.sha256(corpo).hexdigest() != carga:
                return False
            extras = {n: self.headers.get(n, "") for n in assinados.split(";")
                      if n not in ("host", "x-amz-date", "x-amz-content-sha256")}
            quando = datetime.strptime(self.headers.get("x-amz-date", ""),
                                       "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            esperado = assinar_s3(self.command, f"http://{self.headers.get('Host')}{self.path}",
                                  extras, carga, chave_id=chave_id, segredo=segredo,
                                  regiao=regiao, quando=quando)
            return hmac.compare_digest(esperado["Authorization"], auth)

        def _fim(self, status: int, corpo: bytes = b"", cab: dict[str, str] | None = None) -> None:
            pedidos.append((self.command, self.path, status))
            self.send_response(status)
            for k, v in (cab or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(corpo) if self.command != "HEAD" else
                                                   int((cab or {}).get("X-Tamanho", 0))))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)

        def do_PUT(self) -> None:  # noqa: N802
            corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if not self._valido(corpo):
                return self._fim(403)
            objetos[self.path] = (corpo, time.time())
            self._fim(200)

        def _ler(self) -> None:
            if not self._valido(b""):
                return self._fim(403)
            if self.path not in objetos:
                return self._fim(404)
            corpo, mtime = objetos[self.path]
            self._fim(200, corpo, {"Last-Modified": formatdate(mtime, usegmt=True),
                                   "X-Tamanho": str(len(corpo))})

        do_GET = _ler  # noqa: N815
        do_HEAD = _ler  # noqa: N815

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{servidor.server_address[1]}", objetos, pedidos
    finally:
        servidor.shutdown()
        servidor.server_close()


@contextlib.contextmanager
def _postgrest_falso(
    respostas: dict[str, Callable[[dict[str, Any]], tuple[int, Any]]],
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """POST /rest/v1/rpc/<funcao> do Supabase, com respostas roteirizadas."""
    pedidos: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            pass

        def do_POST(self) -> None:  # noqa: N802
            corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            funcao = self.path.rsplit("/", 1)[-1]
            pedidos.append({"caminho": self.path, "funcao": funcao, "corpo": corpo,
                            "apikey": self.headers.get("apikey"),
                            "auth": self.headers.get("Authorization")})
            status, dados = respostas.get(funcao, lambda _: (404, {"message": "?"}))(corpo)
            saida = json.dumps(dados).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(saida)))
            self.end_headers()
            self.wfile.write(saida)

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{servidor.server_address[1]}", pedidos
    finally:
        servidor.shutdown()
        servidor.server_close()


def e_assinatura_aws(_: Path) -> None:
    """N-E10: a assinatura S3 reproduz o exemplo oficial da AWS (GET Object)."""
    from worker.nuvem import assinar_s3

    cab = assinar_s3(
        "GET", "https://examplebucket.s3.amazonaws.com/test.txt", {"Range": "bytes=0-9"},
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        chave_id="AKIAIOSFODNN7EXAMPLE", segredo="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        regiao="us-east-1", quando=datetime(2013, 5, 24, tzinfo=timezone.utc))
    assinatura = cab["Authorization"].rsplit("Signature=", 1)[-1]
    confere(assinatura == "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41",
            "a assinatura bate com a documentação da AWS (SigV4, GET Object)", assinatura[:16])
    confere("SignedHeaders=host;range;x-amz-content-sha256;x-amz-date" in cab["Authorization"],
            "os cabeçalhos assinados são os do exemplo")


def e_deposito_r2(raiz: Path) -> None:
    """N-E11: R2 contra um S3 falso que confere cada assinatura."""
    from worker.deposito import ErroDeposito
    from worker.nuvem import DepositoR2

    R = _pasta(raiz, "n-e11")
    segredo = "segredo-da-prova"
    with _s3_falso(segredo) as (url, objetos, pedidos):
        dep = DepositoR2("conta", "AKIDPROVA", segredo, "clippro", endpoint=url)
        conteudo = b"video" * 5000
        objetos["/clippro/entradas/video.mp4"] = (conteudo, 1_700_000_000.0)

        local = dep.obter_entrada("video.mp4", R / "t")
        confere(local.read_bytes() == conteudo, "o vídeo enviado chega íntegro do R2")
        confere(abs(local.stat().st_mtime - 1_700_000_000.0) < 1.0,
                "o mtime local é o Last-Modified do objeto (a retomada reaproveita o ingest)")
        gets = sum(1 for m, _, _ in pedidos if m == "GET")
        dep.obter_entrada("video.mp4", R / "t")
        confere(sum(1 for m, _, _ in pedidos if m == "GET") == gets,
                "na 2ª vez só o HEAD vai ao R2: nada é baixado de novo")

        clipe = R / "01-clipe--cortes.mp4"
        clipe.write_bytes(b"clipe" * 999)
        chave = dep.enviar("t-1", clipe)
        confere(chave == "resultados/t-1/01-clipe--cortes.mp4"
                and objetos.get("/clippro/" + chave, (b"",))[0] == clipe.read_bytes(),
                "o clipe é publicado em resultados/<trabalho>/ com os mesmos bytes", chave)
        confere(all(s != 403 for _, _, s in pedidos),
                "toda requisição do depósito passou na conferência da assinatura")

        try:
            dep.obter_entrada("sumiu.mp4", R / "t")
            confere(False, "entrada inexistente vira erro de depósito")
        except ErroDeposito as exc:
            confere("não está mais" in exc.mensagem, "entrada inexistente vira erro claro",
                    exc.mensagem)
        errado = DepositoR2("conta", "AKIDPROVA", "segredo-errado", "clippro", endpoint=url)
        try:
            errado.enviar("t-1", clipe)
            confere(False, "segredo errado é recusado")
        except ErroDeposito as exc:
            confere("403" in exc.mensagem, "segredo errado é recusado pelo servidor", exc.mensagem)


def e_fila_supabase(_: Path) -> None:
    """N-E12: a fila do Supabase contra um PostgREST falso."""
    from worker.nuvem import ErroNuvem, FilaSupabase

    bom = {"id": "0b9a3c1e-2f4d-4e5a-9b6c-7d8e9f0a1b2c",
           "conta": "5c6d7e8f-9a0b-4c1d-8e2f-3a4b5c6d7e8f", "tentativas": 1,
           "pedido": {"entrada": {"tipo": "arquivo", "valor": "live.mp4"}, "n": 3,
                      "preset": "cortes", "limite_minutos": 300}}
    torto = {**bom, "id": "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
             "pedido": {**bom["pedido"], "n": "3"}}
    fila_de_linhas = [[torto], [bom], []]
    respostas = {
        "reservar_trabalho": lambda _: (200, fila_de_linhas.pop(0) if fila_de_linhas else []),
        "encerrar_trabalho": lambda _: (200, True),
        "renovar_trabalho": lambda _: (500, {"message": "fora do ar"}),
    }
    with _postgrest_falso(respostas) as (url, pedidos):
        fila = FilaSupabase(url, "sb_secret_prova", 600)
        r = fila.reservar("w1")
        confere(r is not None and r.trabalho.id == bom["id"] and r.tentativa == 1,
                "reserva o primeiro pedido válido, com a tentativa que o banco contou")
        recusas = [p for p in pedidos if p["funcao"] == "encerrar_trabalho"]
        confere(len(recusas) == 1 and recusas[0]["corpo"]["p_status"] == "recusado"
                and recusas[0]["corpo"]["p_id"] == torto["id"]
                and "'n'" in recusas[0]["corpo"]["p_resultado"]["erro"]["detalhe"],
                "o pedido torto é encerrado como 'recusado', com o motivo")
        confere(all(p["apikey"] == "sb_secret_prova" and p["auth"] is None for p in pedidos),
                "chave nova (sb_secret_…) vai só no cabeçalho apikey, sem Bearer")

        confere(fila.concluir(r, {"status": "concluido"}) is True,
                "concluir devolve o que o banco respondeu")
        ultimo = pedidos[-1]["corpo"]
        confere(ultimo["p_status"] == "concluido" and ultimo["p_worker"] == "w1"
                and ultimo["p_tentativa"] == 1,
                "o encerramento leva dono e tentativa (o banco confere os dois)")
        fila.renovar(r)
        confere(True, "renovar engole a falha de rede (tenta no próximo batimento)")
        confere(fila.reservar("w1") is None, "fila vazia devolve None")

        antiga = FilaSupabase(url, "eyJhbGciOiJIUzI1NiJ9.prova.assinatura", 600)
        fila_de_linhas.append([])
        antiga.reservar("w2")
        confere(pedidos[-1]["auth"] == "Bearer eyJhbGciOiJIUzI1NiJ9.prova.assinatura",
                "a service_role antiga (JWT) vai também no Authorization")

    with _postgrest_falso({"reservar_trabalho": lambda _: (500, {"message": "x"})}) as (url, _p):
        try:
            FilaSupabase(url, "sb_secret_prova", 600).reservar("w1")
            confere(False, "erro do servidor vira ErroNuvem")
        except ErroNuvem as exc:
            confere("500" in exc.mensagem, "erro do servidor vira ErroNuvem", exc.mensagem)


def e_modo_nuvem_sem_chaves(raiz: Path) -> None:
    """N-E13: `--nuvem` sem as variáveis lista o que falta; e não mistura com pasta."""
    from provas import entrada_real as ER
    from worker.nuvem import VARIAVEIS

    env = {k: v for k, v in ER.ambiente({"ANTHROPIC_API_KEY": "chave-falsa-da-prova"}).items()
           if k not in VARIAVEIS}
    proc = _worker("--nuvem", "--uma-vez", env=env)
    saida = _saida(proc)
    confere(proc.returncode == 2 and all(n in (proc.stderr or "") for n in VARIAVEIS),
            "sem as chaves, o worker lista as 6 variáveis que faltam", saida[-90:])
    proc = _worker("--nuvem", "--fila", raiz / "x", "--uma-vez", env=env)
    confere(proc.returncode == 2 and "não os dois" in (proc.stderr or ""),
            "--nuvem com --fila é recusado", _saida(proc)[-80:])


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
    "N-E10": ("assinatura S3 contra o exemplo da AWS", e_assinatura_aws),
    "N-E11": ("depósito R2 contra S3 que confere a assinatura", e_deposito_r2),
    "N-E12": ("fila Supabase contra PostgREST falso", e_fila_supabase),
    "N-E13": ("`--nuvem` sem chaves", e_modo_nuvem_sem_chaves),
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
    uso = res.get("uso_api") or {}
    confere(uso.get("chamadas") == 1 and uso.get("tokens_entrada") == 1
            and uso.get("tokens_saida") == 1 and "haiku" in str(uso.get("modelo")),
            "os tokens que a API informou foram gravados no trabalho (§28, P2)", str(uso))

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
    confere(res.get("uso_api") is None, "sem chamada, sem uso de API no resultado")
    saida = cen["base"] / "fonte-n1"
    confere(not (saida / "fonte.mp4").exists() and not cen["entrada"].exists()
            and (cen["base"] / "worker.log").is_file(),
            "fontes apagadas, log mantido para diagnóstico")
    confere(not (cen["R"] / "deposito" / "resultados" / "n-f2").exists(),
            "nada foi publicado no depósito")


# Imita o que o Supabase ja traz pronto: os papeis anon/authenticated/
# service_role e o EXECUTE/ALL que ele da por padrao a eles. Sem isto a prova
# de permissao passaria por motivo errado (o papel nem existiria).
_SUPABASE_IMITADO = """
do $$ begin
  if not exists (select from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
  if not exists (select from pg_roles where rolname = 'service_role') then create role service_role nologin bypassrls; end if;
end $$;
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant execute on functions to anon, authenticated, service_role;
drop table if exists public.trabalhos cascade;
drop function if exists public.reservar_trabalho(text, int);
drop function if exists public.renovar_trabalho(uuid, text, int, int);
drop function if exists public.encerrar_trabalho(uuid, text, int, text, jsonb);
drop function if exists public.devolver_trabalho(uuid, text, int);
"""
_PEDIDO_SQL = """'{"entrada": {"tipo": "arquivo", "valor": "v.mp4"}, "n": 3, "preset": "cortes", "limite_minutos": 300}'::jsonb"""


def f_sql_da_fila(raiz: Path) -> None:
    """N-F3: o SQL da fila num Postgres de verdade — disputa, prazo, permissões."""
    url, psql = os.environ.get("CLIPPRO_PROVA_PG"), shutil.which("psql")
    if not url or not psql:
        raise Pulou("pendente: defina CLIPPRO_PROVA_PG com a URL de um Postgres de TESTE "
                    "(a prova apaga e recria a tabela) e tenha o psql no PATH.")
    migracao = RAIZ / "nuvem" / "supabase" / "001_fila.sql"

    def sql(*comandos: str, papel: str | None = None,
            arquivo: Path | None = None) -> subprocess.CompletedProcess:
        args = [psql, url, "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1"]
        if papel:
            args += ["-c", f"set role {papel}"]
        if arquivo:
            args += ["-f", str(arquivo)]
        for c in comandos:
            args += ["-c", c]
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120, env=env)

    # NOTICE de "ja existe, pulando" e ruido: so erro interessa ao relatorio.
    env = {**os.environ, "PGOPTIONS": "-c client_min_messages=warning"}

    p = sql(_SUPABASE_IMITADO)
    confere(p.returncode == 0, "o banco de teste imita os papéis do Supabase",
            p.stderr[-120:] if p.returncode else "")
    p1, p2 = sql(arquivo=migracao), sql(arquivo=migracao)
    confere(p1.returncode == 0 and p2.returncode == 0,
            "a migração roda, e roda de novo sem erro (idempotente)",
            (p1.stderr or p2.stderr)[-140:] if (p1.returncode or p2.returncode) else "")

    sql(f"insert into trabalhos (conta, pedido) select gen_random_uuid(), {_PEDIDO_SQL} "
        "from generate_series(1, 20)")
    reservar = "select id from reservar_trabalho('w{k}', 600)"
    procs = [subprocess.Popen(
        [psql, url, "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", "-c", "set role service_role",
         *[a for _ in range(4) for a in ("-c", reservar.format(k=k))]],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for k in range(8)]
    ids: list[str] = []
    for pr in procs:
        saida, _ = pr.communicate(timeout=120)
        ids += [linha for linha in saida.split() if linha]
    confere(len(ids) == 20 and len(set(ids)) == 20,
            "8 sessões disputando 20 trabalhos: cada um reservado uma vez, nenhum perdido",
            f"{len(ids)} reservas, {len(set(ids))} distintas")

    # SKIP LOCKED nao e sobre duplicar (sem ele tambem nao duplica): e sobre
    # um worker NAO ESPERAR o outro. A sessao A segura a reserva aberta por
    # 2 s; a B tem de sair na hora com OUTRO trabalho.
    sql("delete from trabalhos")
    sql(f"insert into trabalhos (conta, pedido) select gen_random_uuid(), {_PEDIDO_SQL} "
        "from generate_series(1, 2)")
    segura = subprocess.Popen(
        [psql, url, "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", "-c", "set role service_role",
         "-c", "begin", "-c", reservar.format(k="A"), "-c", "select pg_sleep(2)", "-c", "commit"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    time.sleep(0.5)
    t0 = time.monotonic()
    id_b = sql(reservar.format(k="B"), papel="service_role").stdout.strip()
    espera = time.monotonic() - t0
    id_a = segura.communicate(timeout=30)[0].split()[0]
    confere(bool(id_b) and id_b != id_a and espera < 1.0,
            "um worker não espera o outro: com A segurando a reserva, B pega outro na hora",
            f"B esperou {espera:.2f} s")

    sql("delete from trabalhos")
    sql(f"insert into trabalhos (conta, pedido) values (gen_random_uuid(), {_PEDIDO_SQL})")
    id1 = sql(reservar.format(k=1), papel="service_role").stdout.strip()
    sql("update trabalhos set reservado_ate = now() - interval '1 second'")
    id2 = sql(reservar.format(k=2), papel="service_role").stdout.strip()
    confere(id1 and id1 == id2, "a reserva vencida volta e o próximo worker pega")
    velho = sql(f"select encerrar_trabalho('{id1}', 'w1', 1, 'concluido', '{{}}'::jsonb)",
                papel="service_role").stdout.strip()
    novo = sql(f"select encerrar_trabalho('{id1}', 'w2', 2, 'concluido', '{{}}'::jsonb)",
               papel="service_role").stdout.strip()
    confere(velho == "f" and novo == "t",
            "o worker antigo NÃO encerra; o dono da tentativa 2 encerra", f"{velho}/{novo}")
    p = sql(f"select encerrar_trabalho('{id1}', 'w2', 2, 'apagado', '{{}}'::jsonb)",
            papel="service_role")
    confere(p.returncode != 0, "status de encerramento fora da lista é recusado")

    sql("delete from trabalhos")
    sql(f"insert into trabalhos (conta, pedido) values (gen_random_uuid(), {_PEDIDO_SQL})")
    for k in range(3):
        sql(reservar.format(k=k), papel="service_role")
        sql("update trabalhos set reservado_ate = now() - interval '1 second'")
    sql(reservar.format(k=9), papel="service_role")
    final = sql("select status || '|' || (resultado->>'creditos') from trabalhos").stdout.strip()
    confere(final == "falhou|0", "na 3ª reserva vencida o trabalho falha, sem crédito", final)

    p = sql(reservar.format(k=0), papel="anon")
    confere(p.returncode != 0 and "permission denied" in p.stderr,
            "o papel anon não pode mexer na fila", p.stderr.strip()[-80:])
    contagem = sql("select count(*) from trabalhos", papel="authenticated").stdout.strip()
    p = sql(f"insert into trabalhos (conta, pedido) values (gen_random_uuid(), {_PEDIDO_SQL})",
            papel="authenticated")
    confere(contagem == "0" and p.returncode != 0 and "row-level security" in p.stderr,
            "usuário logado não lê nem escreve a fila ainda (RLS sem policy até a N-2)",
            f"leu {contagem}; {p.stderr.strip()[-60:]}")


def _supabase(metodo: str, caminho: str, corpo: Any = None, prefer: str | None = None) -> Any:
    """API REST do Supabase com a chave secreta (papel do app, que entra na N-2)."""
    import urllib.request

    chave = os.environ["SUPABASE_SECRET_KEY"].strip()
    cab = {"apikey": chave, "Content-Type": "application/json", "Accept": "application/json"}
    if chave.startswith("eyJ"):
        cab["Authorization"] = f"Bearer {chave}"
    if prefer:
        cab["Prefer"] = prefer
    pedido = urllib.request.Request(
        os.environ["SUPABASE_URL"].strip().rstrip("/") + caminho, method=metodo, headers=cab,
        data=None if corpo is None else json.dumps(corpo).encode("utf-8"))
    with urllib.request.urlopen(pedido, timeout=60) as r:
        dados = r.read()
    return json.loads(dados) if dados else None


def f_contas_reais(raiz: Path) -> None:
    """N-F4: o worker --nuvem de verdade, no Supabase e no R2 do Bruno."""
    import urllib.request
    import uuid

    from provas import entrada_real as ER
    from worker.executor import pastas
    from worker.nuvem import DepositoR2, variaveis_faltando

    _exigir_fisicas()
    if os.environ.get("CLIPPRO_PROVA_NUVEM") != "1" or variaveis_faltando():
        raise Pulou("pendente: precisa das contas (variáveis SUPABASE_* e R2_*) e de "
                    "CLIPPRO_PROVA_NUVEM=1 — a prova escreve na nuvem de verdade.")
    if _supabase("GET", "/rest/v1/trabalhos?status=eq.pendente&select=id"):
        raise Pulou("a fila real tem trabalhos pendentes; rode esta prova com a fila vazia.")

    R = _pasta(raiz, "n-f4")
    video = ER.video_lavfi(raiz / "videos" / "fonte-n1.mp4", 70.0)
    dep = DepositoR2.do_ambiente()
    chave = f"prova-n1-{int(time.time())}.mp4"
    with open(video, "rb") as corpo:
        pedido = dep._pedido("PUT", f"entradas/{chave}", corpo=corpo,
                             sha=hashlib.sha256(video.read_bytes()).hexdigest(),
                             extra={"Content-Length": str(video.stat().st_size)})
        urllib.request.urlopen(pedido, timeout=120).close()

    linha = _supabase("POST", "/rest/v1/trabalhos", {
        "conta": str(uuid.uuid4()),
        "pedido": {"entrada": {"tipo": "arquivo", "valor": chave}, "n": 1,
                   "preset": "cortes", "limite_minutos": 300},
    }, prefer="return=representation")[0]
    id_ = linha["id"]
    criados = [f"entradas/{chave}"]
    try:
        base, pasta_entrada = pastas(R / "trabalhos", id_)
        local = dep.obter_entrada(chave, pasta_entrada)
        trans = ER.transcricao_sintetica(68.0)
        ER.semear(base, Path(chave).stem, trans, video=local)
        frs = ER.frases(trans)

        from clipper.fronteiras import mmss

        def responder(_: dict[str, Any]) -> list[dict[str, Any]]:
            return [ER.item(titulo="Clipe da nuvem", inicio=mmss(frs[0].inicio),
                            fim=mmss(frs[7].fim))]

        with ER.api_falsa(responder) as (url, _pedidos):
            env = ER.ambiente({"ANTHROPIC_BASE_URL": url,
                               "ANTHROPIC_API_KEY": "chave-falsa-da-prova",
                               "NO_PROXY": "127.0.0.1,localhost"})
            proc = _worker("--nuvem", "--trabalhos", R / "trabalhos", "--uma-vez", env=env)
        confere(proc.returncode == 0, "`python -m worker --nuvem --uma-vez` termina bem",
                _saida(proc))
        estado = _supabase("GET", f"/rest/v1/trabalhos?id=eq.{id_}&select=status,resultado")[0]
        res = estado.get("resultado") or {}
        confere(estado["status"] == "concluido" and res.get("creditos") == 2,
                "no Supabase: concluído, 2 créditos", f"{estado['status']}")
        arquivos = ((res.get("clipes") or [{}])[0]).get("arquivos") or {}
        criados += list(arquivos.values())
        for nome, objeto in arquivos.items():
            with urllib.request.urlopen(dep._pedido("HEAD", objeto), timeout=60) as r:
                confere(int(r.headers.get("Content-Length") or 0) > 0,
                        f"no R2: {nome} publicado", objeto)
        confere(set(arquivos) == {"video", "capa", "publicacao"},
                "MP4, capa e publicação foram para o R2")
    finally:
        _supabase("DELETE", f"/rest/v1/trabalhos?id=eq.{id_}")
        for objeto in criados:
            try:
                urllib.request.urlopen(dep._pedido("DELETE", objeto), timeout=60).close()
            except Exception:  # noqa: BLE001 - limpeza nao derruba o resultado da prova
                print(f"    aviso  não apaguei {objeto} do R2")


FISICAS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "N-F1": ("ponta a ponta pelo worker e pela API falsa", f_ponta_a_ponta),
    "N-F2": ("limite de minutos antes da IA", f_limite_de_minutos),
    "N-F3": ("SQL da fila num Postgres de verdade", f_sql_da_fila),
    "N-F4": ("worker --nuvem nas contas reais (Supabase + R2)", f_contas_reais),
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
        print(f"  {len(FISICAS)} prova(s) FÍSICA(S) não executada(s) "
              "(precisam de ffmpeg; a N-F3 de Postgres; a N-F4 das contas).")
    return 1 if falharam else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
