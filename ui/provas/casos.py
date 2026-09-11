"""Os nove casos de prova da F5. Rode por ui/provas/prova_f5.py."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ui.provas.prova_f5 import (
    PORTA_ARQUIVOS,
    PORTA_PAINEL,
    PYTHON,
    RAIZ,
    Falhou,
    ServidorDeArquivos,
    confere,
    enviar_multipart,
    esperar_porta,
    esperar_status,
    matar_arvore,
    painel,
    pedir,
    resposta_fixture,
)

VIDEO_CURTO = RAIZ / "_teste" / "clipe-curto.mp4"
URL_LOCAL = f"http://127.0.0.1:{PORTA_ARQUIVOS}/clipe-curto.mp4"


def _exigir_video() -> None:
    if not VIDEO_CURTO.is_file():
        raise Falhou(
            f"falta o vídeo de teste em {VIDEO_CURTO}. Gere com:\n"
            "  ffmpeg -ss 0 -t 40 -i out/<slug>/fonte.mp4 -c:v libx264 -preset veryfast "
            "-crf 26 -vf scale=854:-2 -c:a aac -b:a 96k _teste/clipe-curto.mp4"
        )


def _limpar(raiz: Path) -> None:
    if raiz.exists():
        shutil.rmtree(raiz, ignore_errors=True)
    raiz.mkdir(parents=True, exist_ok=True)


def _ate_a_selecao(raiz: Path, entrada: str, por_upload: bool = False) -> str:
    """Cria o job e espera ele parar pedindo a resposta manual. Devolve o id."""
    if por_upload:
        codigo, job = enviar_multipart(
            VIDEO_CURTO, {"url": "", "n": "1", "estrategia": "trecho de teste", "preset": "cortes"}
        )
    else:
        codigo, job, _ = pedir(
            "POST", "/jobs",
            {"url": entrada, "n": 1, "estrategia": "trecho de teste", "preset": "cortes"},
        )
    confere(codigo == 201, "POST /jobs criou o job", f"HTTP {codigo}")
    job_id = job["id"]
    confere(job["status"] == "na_fila", "nasce 'na_fila'", job["status"])
    esperar_status(job_id, {"aguardando_resposta", "erro"}, timeout=600)
    return job_id


# ==========================================================================
# P1 — URL, ponta a ponta, modo manual
# ==========================================================================
def p1(raiz: Path) -> None:
    _exigir_video()
    _limpar(raiz)
    arquivos = ServidorDeArquivos(VIDEO_CURTO.parent, PORTA_ARQUIVOS)
    arquivos.start()
    try:
        with painel(raiz):
            job_id = _ate_a_selecao(raiz, URL_LOCAL)
            codigo, job, _ = pedir("GET", f"/jobs/{job_id}")
            confere(
                job["status"] == "aguardando_resposta",
                "parou no modo manual, esperando a resposta",
                job["status"],
            )
            confere(job["prompt_existe"], "prompt_selecao.txt foi gravado")

            codigo, texto, _ = pedir("GET", f"/jobs/{job_id}/prompt")
            confere(codigo == 200 and len(texto) > 500, "GET /prompt devolve o texto", f"{len(texto)} bytes")

            base = raiz / job_id
            fixture = resposta_fixture(base)
            codigo, corpo, _ = pedir(
                "POST", f"/jobs/{job_id}/prompt-resposta", {"resposta": fixture}, timeout=120
            )
            confere(codigo == 202, "o validador ACEITOU a resposta boa", f"HTTP {codigo}")

            job = esperar_status(job_id, {"concluido", "erro"}, timeout=900)
            confere(job["status"] == "concluido", "o job chegou a 'concluido'", str(job.get("erro")))

            # job.json atravessou TODOS os estagios
            feitos = job.get("estagios") or {}
            for nome in ("ingestao", "transcricao", "energia", "selecao", "render"):
                confere(
                    (feitos.get(nome) or {}).get("status") == "pronto",
                    f"estágio '{nome}' consta como pronto no job.json",
                )
            confere(job["progresso"] == 1.0, "progresso fechou em 1.0", str(job["progresso"]))
            confere(len(job.get("clipes") or []) >= 1, "tem clipe renderizado",
                    f"{len(job.get('clipes') or [])} clipe(s)")
            mp4 = base / job["clipes"][0]["arquivo"]
            confere(mp4.is_file() and mp4.stat().st_size > 0, "o mp4 existe em disco", mp4.name)
    finally:
        arquivos.parar()


# ==========================================================================
# P2 — upload multipart pelo mesmo caminho
# ==========================================================================
def p2(raiz: Path) -> None:
    _exigir_video()
    _limpar(raiz)
    with painel(raiz):
        job_id = _ate_a_selecao(raiz, "", por_upload=True)
        base = raiz / job_id
        enviado = base / "source" / VIDEO_CURTO.name
        confere(enviado.is_file(), "o upload foi gravado em out/<slug>/source/", str(enviado.relative_to(raiz)))
        confere(
            enviado.stat().st_size == VIDEO_CURTO.stat().st_size,
            "o arquivo chegou inteiro",
            f"{enviado.stat().st_size} bytes",
        )
        confere(
            not list((base / "source").glob("*.parcial")),
            "não sobrou .parcial da escrita atômica",
        )
        codigo, corpo, _ = pedir(
            "POST", f"/jobs/{job_id}/prompt-resposta", {"resposta": resposta_fixture(base)}, timeout=120
        )
        confere(codigo == 202, "validador aceitou (caminho do upload)", f"HTTP {codigo}")
        job = esperar_status(job_id, {"concluido", "erro"}, timeout=900)
        confere(job["status"] == "concluido", "upload chegou a 'concluido'", str(job.get("erro")))


# ==========================================================================
# P3 — retomada depois de morrer no meio do render
# ==========================================================================
def p3(raiz: Path) -> None:
    _exigir_video()
    _limpar(raiz)
    arquivos = ServidorDeArquivos(VIDEO_CURTO.parent, PORTA_ARQUIVOS)
    arquivos.start()
    job_id = ""
    try:
        # 1a subida: vai ate a selecao aceita e comeca a renderizar.
        with painel(raiz) as proc:
            job_id = _ate_a_selecao(raiz, URL_LOCAL)
            base = raiz / job_id
            pedir("POST", f"/jobs/{job_id}/prompt-resposta", {"resposta": resposta_fixture(base)}, timeout=120)
            # espera ENTRAR no render e mata no meio
            limite = time.monotonic() + 300
            entrou = False
            while time.monotonic() < limite:
                _, job, _ = pedir("GET", f"/jobs/{job_id}")
                if job.get("estagio") == "render":
                    entrou = True
                    break
                if job.get("status") == "concluido":
                    break
                time.sleep(0.5)
            confere(entrou, "o job chegou ao estágio de render antes de eu matar o processo")
            transcricao_antes = (base / "transcricao.json").stat().st_mtime_ns
            matar_arvore(proc)

        confere(
            not esperar_porta(PORTA_PAINEL, timeout=8),
            "o painel morreu e SOLTOU a porta (senão não dá para subir de novo)",
        )
        _, job_disco = 0, json.loads((raiz / job_id / "job.json").read_text(encoding="utf-8"))
        confere(
            job_disco["status"] in ("rodando", "na_fila"),
            "o job.json ficou marcado como interrompido",
            job_disco["status"],
        )

        # 2a subida: retoma sozinho
        with painel(raiz):
            job = esperar_status(job_id, {"concluido", "erro"}, timeout=900)
            confere(job["status"] == "concluido", "retomou e terminou", str(job.get("erro")))
            transcricao_depois = (raiz / job_id / "transcricao.json").stat().st_mtime_ns
            confere(
                transcricao_antes == transcricao_depois,
                "NÃO re-transcreveu na retomada (mtime intacto)",
                f"{transcricao_antes} == {transcricao_depois}",
            )
            feitos = job.get("estagios") or {}
            confere(
                (feitos.get("transcricao") or {}).get("reaproveitado") is True,
                "o job registra a transcrição como reaproveitada",
                json.dumps(feitos.get("transcricao") or {}, ensure_ascii=False),
            )
    finally:
        arquivos.parar()


# ==========================================================================
# P4 — resposta torta: erros acionaveis e o job NAO avanca
# ==========================================================================
TORTAS = [
    ("texto que não é JSON", "desculpe, aqui estão os clipes: bla bla"),
    ("array vazio", "[]"),
    ("faltando campo obrigatório", '[{"inicio": 1.0, "fim": 25.0}]'),
    ("fim antes do início", '[{"inicio": 30.0, "fim": 5.0, "titulo": "x", "score_0_10": 9}]'),
    ("trecho fora do vídeo", '[{"inicio": 5000.0, "fim": 5030.0, "titulo": "x", "score_0_10": 9}]'),
    ("clipe curto demais", '[{"inicio": 1.0, "fim": 3.0, "titulo": "x", "score_0_10": 9}]'),
]


def p4(raiz: Path) -> None:
    _exigir_video()
    _limpar(raiz)
    arquivos = ServidorDeArquivos(VIDEO_CURTO.parent, PORTA_ARQUIVOS)
    arquivos.start()
    try:
        with painel(raiz):
            job_id = _ate_a_selecao(raiz, URL_LOCAL)
            base = raiz / job_id
            for rotulo, texto in TORTAS:
                codigo, corpo, _ = pedir(
                    "POST", f"/jobs/{job_id}/prompt-resposta", {"resposta": texto}, timeout=60
                )
                confere(codigo == 422, f"recusou: {rotulo}", f"HTTP {codigo}")
                confere(
                    bool(corpo.get("mensagem")) and bool(corpo.get("sugestao")),
                    f"  com mensagem E sugestão acionável: {rotulo}",
                    str(corpo.get("mensagem"))[:70],
                )
                confere(
                    "Traceback" not in json.dumps(corpo),
                    f"  sem stack trace vazando: {rotulo}",
                )
                _, job, _ = pedir("GET", f"/jobs/{job_id}")
                confere(
                    job["status"] == "aguardando_resposta",
                    f"  o job NÃO avançou: {rotulo}",
                    job["status"],
                )
            confere(
                not (base / "selecao.json").is_file(),
                "nenhuma resposta torta gravou selecao.json",
            )
            # e a boa ainda passa depois de todas as tortas
            codigo, _, _ = pedir(
                "POST", f"/jobs/{job_id}/prompt-resposta",
                {"resposta": resposta_fixture(base)}, timeout=120,
            )
            confere(codigo == 202, "a resposta BOA ainda é aceita depois das tortas", f"HTTP {codigo}")
    finally:
        arquivos.parar()


# ==========================================================================
# P5 — SSE emite progresso em cada transicao
# ==========================================================================
def p5(raiz: Path) -> None:
    _exigir_video()
    _limpar(raiz)
    arquivos = ServidorDeArquivos(VIDEO_CURTO.parent, PORTA_ARQUIVOS)
    arquivos.start()
    coletados: list[dict[str, Any]] = []
    try:
        with painel(raiz):
            codigo, job, _ = pedir(
                "POST", "/jobs",
                {"url": URL_LOCAL, "n": 1, "estrategia": "trecho de teste", "preset": "cortes"},
            )
            job_id = job["id"]

            parar = threading.Event()

            def ouvir() -> None:
                req = urllib.request.Request(f"http://127.0.0.1:{PORTA_PAINEL}/jobs/{job_id}/events")
                with urllib.request.urlopen(req, timeout=900) as fluxo:
                    for linha in fluxo:
                        if parar.is_set():
                            return
                        texto = linha.decode("utf-8", "replace").strip()
                        if texto.startswith("data: "):
                            coletados.append(json.loads(texto[6:]))

            ouvinte = threading.Thread(target=ouvir, daemon=True)
            ouvinte.start()

            esperar_status(job_id, {"aguardando_resposta", "erro"}, timeout=600)
            base = raiz / job_id
            pedir("POST", f"/jobs/{job_id}/prompt-resposta", {"resposta": resposta_fixture(base)}, timeout=120)
            esperar_status(job_id, {"concluido", "erro"}, timeout=900)
            time.sleep(1.5)
            parar.set()

        tipos = [e.get("tipo") for e in coletados]
        confere(len(coletados) >= 8, "o SSE entregou eventos", f"{len(coletados)} eventos: {tipos}")
        confere(tipos[0] == "estado", "o primeiro evento é o estado atual", str(tipos[0]))

        # a sequencia completa de transicoes de estagio
        sequencia = [
            (e.get("estagio"), e.get("status")) for e in coletados if e.get("tipo") == "estagio"
        ]
        for nome in ("ingestao", "transcricao", "energia", "selecao", "render"):
            confere(
                (nome, "rodando") in sequencia,
                f"chegou 'rodando' de '{nome}'",
            )
            confere(
                (nome, "pronto") in sequencia,
                f"chegou 'pronto' de '{nome}'",
            )
        confere("concluido" in tipos, "chegou o evento final 'concluido'")

        progressos = [e["job"]["progresso"] for e in coletados if e.get("job")]
        confere(
            all(b >= a - 1e-9 for a, b in zip(progressos, progressos[1:])),
            "o progresso nunca anda para trás",
            f"{progressos[0]} → {progressos[-1]}",
        )
    finally:
        arquivos.parar()


# ==========================================================================
# P6 — video servido com range requests
# ==========================================================================
def p6(raiz: Path) -> None:
    jobs = [p for p in raiz.iterdir() if (p / "job.json").is_file()] if raiz.exists() else []
    if not jobs:
        raise Falhou("P6 depende de um job com clipe pronto: rode P1 antes (ou a suíte inteira).")
    with painel(raiz):
        job_id = jobs[0].name
        _, job, _ = pedir("GET", f"/jobs/{job_id}")
        confere(bool(job.get("clipes")), "há clipe para servir")
        numero = job["clipes"][0]["id"]
        caminho = f"/jobs/{job_id}/clips/{numero}.mp4"

        codigo, corpo, cab = pedir("GET", caminho)
        confere(codigo == 200, "GET inteiro responde 200", f"HTTP {codigo}")
        confere(cab.get("Accept-Ranges") == "bytes", "anuncia Accept-Ranges: bytes", str(cab.get("Accept-Ranges")))
        tamanho = len(corpo)

        codigo, pedaco, cab = pedir("GET", caminho, cabecalhos={"Range": "bytes=0-1023"})
        confere(codigo == 206, "pedaço do começo responde 206", f"HTTP {codigo}")
        confere(len(pedaco) == 1024, "veio exatamente 1024 bytes", f"{len(pedaco)}")
        confere(
            cab.get("Content-Range") == f"bytes 0-1023/{tamanho}",
            "Content-Range correto",
            str(cab.get("Content-Range")),
        )

        meio = tamanho // 2
        codigo, pedaco, cab = pedir("GET", caminho, cabecalhos={"Range": f"bytes={meio}-{meio + 511}"})
        confere(codigo == 206, "pedaço do meio (o seek do player) responde 206", f"HTTP {codigo}")
        confere(pedaco == corpo[meio:meio + 512], "o pedaço do meio bate byte a byte")

        codigo, pedaco, _ = pedir("GET", caminho, cabecalhos={"Range": "bytes=-256"})
        confere(codigo == 206 and pedaco == corpo[-256:], "sufixo 'bytes=-256' devolve o fim do arquivo")

        codigo, _, cab = pedir("GET", caminho, cabecalhos={"Range": f"bytes={tamanho + 10}-"})
        confere(codigo == 416, "range fora do arquivo responde 416", f"HTTP {codigo}")

        # Slug de video vindo de LINK termina com o id remoto como ele e, com
        # maiuscula ("...-qp3uNTpf"). A validacao do id nao pode confundir isso
        # com identificador invalido -- o painel recusava todo video de URL.
        codigo, corpo, _ = pedir("GET", "/jobs/video-de-teste-AbCdEfGh")
        confere(
            codigo == 404,
            "id com MAIÚSCULA é tratado como 'não existe', não como 'inválido'",
            f"HTTP {codigo}: {str(corpo)[:60]}",
        )
        for ruim in ("..", "..%2F..%2Fetc", "sub/dir"):
            codigo, _, _ = pedir("GET", f"/jobs/{ruim}")
            confere(codigo in (400, 404), f"id perigoso recusado: '{ruim}'", f"HTTP {codigo}")


# ==========================================================================
# P7 — fila serializa: nunca dois jobs ao mesmo tempo
# ==========================================================================
def p7(raiz: Path) -> None:
    _exigir_video()
    _limpar(raiz)
    arquivos = ServidorDeArquivos(VIDEO_CURTO.parent, PORTA_ARQUIVOS)
    arquivos.start()
    try:
        # duas copias com nomes diferentes = dois slugs = dois jobs
        segundo = VIDEO_CURTO.parent / "clipe-curto-b.mp4"
        shutil.copy2(VIDEO_CURTO, segundo)
        url_b = f"http://127.0.0.1:{PORTA_ARQUIVOS}/{segundo.name}"
        with painel(raiz):
            ids = []
            for url in (URL_LOCAL, url_b):
                codigo, job, _ = pedir(
                    "POST", "/jobs",
                    {"url": url, "n": 1, "estrategia": "trecho de teste", "preset": "cortes"},
                )
                confere(codigo == 201, f"job criado: {url.rsplit('/', 1)[-1]}")
                ids.append(job["id"])
            confere(ids[0] != ids[1], "são dois jobs distintos", " / ".join(ids))

            # amostra o estado dos dois ate os dois pararem
            juntos = 0
            limite = time.monotonic() + 600
            vistos_rodando: set[str] = set()
            while time.monotonic() < limite:
                estados = {}
                for i in ids:
                    _, j, _ = pedir("GET", f"/jobs/{i}")
                    estados[i] = j.get("status")
                    if j.get("status") == "rodando":
                        vistos_rodando.add(i)
                rodando = [i for i, s in estados.items() if s == "rodando"]
                if len(rodando) > 1:
                    juntos += 1
                if all(s in ("aguardando_resposta", "concluido", "erro") for s in estados.values()):
                    break
                time.sleep(0.4)

            confere(juntos == 0, "NUNCA dois jobs em 'rodando' ao mesmo tempo", f"{juntos} amostras com dois")
            confere(len(vistos_rodando) == 2, "os dois jobs chegaram a rodar", str(vistos_rodando))

            # os tempos gravados nao se sobrepoem
            janelas = []
            for i in ids:
                dados = json.loads((raiz / i / "job.json").read_text(encoding="utf-8"))
                for nome, e in (dados.get("estagios") or {}).items():
                    if e.get("iniciado_em") and e.get("terminado_em"):
                        janelas.append((i, nome, e["iniciado_em"], e["terminado_em"]))
            sobrepostas = 0
            for a in janelas:
                for b in janelas:
                    if a[0] >= b[0]:
                        continue
                    if a[2] < b[3] and b[2] < a[3]:
                        sobrepostas += 1
            # Sem esta primeira asserção a de baixo passava com ZERO janelas --
            # um verde que não provava nada (foi o que aconteceu na 1a rodada).
            confere(
                len(janelas) >= 4,
                "há janelas de estágio com início E fim para comparar",
                f"{len(janelas)} janelas",
            )
            confere(sobrepostas == 0, "nenhuma janela de estágio de jobs diferentes se sobrepõe",
                    f"{len(janelas)} janelas conferidas")
        segundo.unlink(missing_ok=True)
    finally:
        arquivos.parar()


# ==========================================================================
# P8 — bind exclusivo em 127.0.0.1
# ==========================================================================
def _ip_da_lan() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip if not ip.startswith("127.") else None
    except OSError:
        return None


def p8(raiz: Path) -> None:
    raiz.mkdir(parents=True, exist_ok=True)
    with painel(raiz):
        codigo, _, _ = pedir("GET", "/jobs", host="127.0.0.1")
        confere(codigo == 200, "127.0.0.1 responde", f"HTTP {codigo}")

        ip = _ip_da_lan()
        if ip is None:
            print(f"    {_amarelo_}sem IP de LAN nesta máquina: só dá para provar o socket{_zero_}")
        else:
            recusou = False
            try:
                with socket.create_connection((ip, PORTA_PAINEL), timeout=3):
                    recusou = False
            except OSError:
                recusou = True
            confere(recusou, f"conexão pelo IP da LAN ({ip}) é RECUSADA", f"porta {PORTA_PAINEL}")

        # o socket do servidor esta preso a 127.0.0.1, nao a 0.0.0.0
        saida = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, errors="replace"
        ).stdout
        linhas = [l for l in saida.splitlines() if f":{PORTA_PAINEL}" in l and "LISTENING" in l]
        confere(bool(linhas), "o painel aparece escutando no netstat", f"{len(linhas)} linha(s)")
        confere(
            all("127.0.0.1" in l for l in linhas),
            "escuta SÓ em 127.0.0.1 (nada de 0.0.0.0)",
            " | ".join(l.split()[1] for l in linhas),
        )


_amarelo_ = "\033[33m"
_zero_ = "\033[0m"


# ==========================================================================
# P9 — controle que MORDE: quebrar a retomada tem que reprovar a P3
# ==========================================================================
def p9(raiz: Path) -> None:
    """Sabota a retomada e exige que a P3 falhe. Depois restaura e confere o sha.

    Uma prova que passa mesmo com o código quebrado não prova nada. Aqui o
    controle negativo é explícito: desligo a retomada, rodo a P3 e ela TEM que
    ficar vermelha. Se ela passar assim, é a P3 que está cega.
    """
    import hashlib

    alvo = RAIZ / "ui" / "server.py"
    original = alvo.read_bytes()
    sha_antes = hashlib.sha256(original).hexdigest()
    print(f"    sha256 de ui/server.py antes: {sha_antes[:16]}")

    texto = original.decode("utf-8")
    marca = "    for job in filas.listar_jobs(raiz):"
    if marca not in texto:
        raise Falhou("não achei o laço de retomada em _retomar_interrompidos")
    sabotado = texto.replace(marca, "    for job in []:  # SABOTAGEM DA P9", 1)

    try:
        alvo.write_text(sabotado, encoding="utf-8")
        print(f"    {_amarelo_}retomada desligada — a P3 agora TEM que falhar{_zero_}")
        mordeu = False
        try:
            p3(raiz)
        except (Falhou, AssertionError):
            mordeu = True
        except Exception as exc:  # noqa: BLE001 - qualquer falha serve como mordida
            print(f"    (a P3 quebrou com {type(exc).__name__}: {exc})")
            mordeu = True
        confere(mordeu, "com a retomada quebrada, a P3 REPROVA (o teste enxerga)")
    finally:
        alvo.write_bytes(original)
        sha_depois = hashlib.sha256(alvo.read_bytes()).hexdigest()
        print(f"    sha256 de ui/server.py depois: {sha_depois[:16]}")
        confere(sha_depois == sha_antes, "ui/server.py restaurado byte a byte", sha_depois[:16])


CASOS = {
    "P1": ("job por URL, ponta a ponta, modo manual", p1),
    "P2": ("upload multipart pelo mesmo caminho", p2),
    "P3": ("retomada depois de matar o processo no render", p3),
    "P4": ("resposta torta: erro acionável e job parado", p4),
    "P5": ("SSE emite progresso em cada transição", p5),
    "P6": ("vídeo servido com range requests", p6),
    "P7": ("fila serializa dois jobs", p7),
    "P8": ("bind exclusivo em 127.0.0.1", p8),
    "P9": ("controle que morde: quebrar a retomada reprova a P3", p9),
}
