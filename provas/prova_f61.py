"""Provas do CLIP-F6.1 -- higiene pos-merge. Espelha provas/prova_f6.py.

Uma prova por item consertado do RULINGS (§12.2, §14.3 e o item 13 achado no
recon de 15/10). Cada uma foi conferida contra o codigo ANTERIOR ao conserto:
ali ela falha -- prova que nao morde nao prova nada.

    python provas/prova_f61.py                # estruturais
    python provas/prova_f61.py --fisicas      # + fisicas (precisa de ffmpeg)
    python provas/prova_f61.py H-1 H-4        # casos escolhidos

As que precisam do fastapi (painel) PULAM onde ele nao esta instalado; no
ambiente do lockfile ele esta.

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
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
    _cenario,
    _clipe_v1,
    _clipe_v2,
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


def _exigir_fastapi() -> None:
    try:
        import fastapi  # noqa: F401
        import httpx  # noqa: F401
    except ImportError as exc:
        raise Pulou(f"falta {exc.name} neste ambiente (o painel precisa dele).") from None


def _gravar_json(caminho: Path, dados: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados), encoding="utf-8", newline="\n")


# ==========================================================================
# Item 1 -- o painel nao reenfileira pasta feita no terminal
# ==========================================================================


def h_retomada_ignora_terminal(raiz: Path) -> None:
    """H-1: a retomada não reprocessa pasta do terminal; job do painel sim."""
    _exigir_fastapi()
    from ui import server

    base = _pasta(raiz, "h1")
    # Pasta do terminal: so .estado.json, sem clipes -> deduzida como 'na fila'.
    _gravar_json(base / "do-terminal" / ".estado.json", {"estagios": {"ingest": {}}})
    # Controle: job do painel interrompido, com job.json.
    _gravar_json(
        base / "do-painel" / "job.json",
        {"id": "do-painel", "slug": "do-painel", "entrada": "x.mp4",
         "status": "rodando", "comando": "run", "opcoes": {}},
    )

    pedidos: list[Any] = []

    class FilaFalsa:
        def enfileirar(self, pedido: Any) -> None:
            pedidos.append(pedido)

    server._retomar_interrompidos(base, FilaFalsa())
    slugs = sorted(p.slug for p in pedidos)
    confere("do-terminal" not in slugs,
            "a pasta do terminal NÃO volta para a fila", str(slugs))
    confere(slugs == ["do-painel"],
            "o job interrompido do painel continua sendo retomado", str(slugs))


# ==========================================================================
# Item 2 -- re-render com o mp4 aberto pelo proprio painel
# ==========================================================================


def _handles_abertos(alvo: Path) -> int | None:
    """Quantos descritores deste processo apontam para `alvo` (so Linux)."""
    fds = Path("/proc/self/fd")
    if not fds.is_dir():
        return None
    real = os.path.realpath(alvo)
    n = 0
    for fd in fds.iterdir():
        try:
            if os.readlink(fd) == real:
                n += 1
        except OSError:
            pass
    return n


def h_stream_solta_o_arquivo(raiz: Path) -> None:
    """H-2: o stream do painel não segura o mp4 entre um pedaço e outro."""
    _exigir_fastapi()
    from ui import server

    base = _pasta(raiz, "h2")
    alvo = base / "clipe.mp4"
    alvo.write_bytes(b"a" * (server._PEDACO * 3))
    novo = base / "novo.mp4"
    novo.write_bytes(b"b" * (server._PEDACO * 3))

    gerador = server._ler_em_pedacos(alvo, 0, alvo.stat().st_size - 1)
    primeiro = next(gerador)
    confere(primeiro == b"a" * server._PEDACO, "o primeiro pedaço sai inteiro")

    abertos = _handles_abertos(alvo)
    if abertos is not None:
        confere(abertos == 0, "entre pedaços nenhum handle fica aberto", f"{abertos} aberto(s)")

    # O re-render termina no meio do stream. No Windows, com o handle preso,
    # este replace era o WinError 5 do item 2.
    os.replace(novo, alvo)
    resto = b"".join(gerador)
    confere(b"b" not in resto,
            "o stream para em vez de emendar bytes do mp4 novo",
            f"{len(resto)} bytes depois da troca")


def h_replace_tolera_handle_curto(_: Path) -> None:
    """H-3: o replace() do render espera um handle transitório soltar."""
    from clipper.pipeline import render

    tentativas = {"n": 0}

    class Caminho(type(Path())):
        def replace(self, destino):  # noqa: D401 - dublê
            tentativas["n"] += 1
            if tentativas["n"] < 3:
                raise PermissionError(13, "WinError 5 simulado")
            return destino

    dormir = render.time.sleep
    render.time.sleep = lambda _s: None
    try:
        render._substituir(Caminho("x.parcial"), Path("x.mp4"))
        confere(tentativas["n"] == 3, "falhou 2×, passou na 3ª", f"{tentativas['n']} tentativas")

        tentativas["n"] = -100  # nunca solta
        try:
            render._substituir(Caminho("x.parcial"), Path("x.mp4"))
        except PermissionError:
            pass
        else:
            raise Falhou("handle que nunca solta tinha de virar PermissionError")
        feitas = tentativas["n"] + 100
        confere(feitas == len(render._ESPERAS_REPLACE_S) + 1,
                "desiste depois das esperas previstas (~3 s), sem laço infinito",
                f"{feitas} tentativas")

        tentativas["n"] = 0

        class Cheio(type(Path())):
            def replace(self, destino):
                tentativas["n"] += 1
                raise OSError(28, "disco cheio")

        try:
            render._substituir(Cheio("x.parcial"), Path("x.mp4"))
        except OSError:
            pass
        confere(tentativas["n"] == 1, "erro que não é de handle não é repetido",
                f"{tentativas['n']} tentativas")
    finally:
        render.time.sleep = dormir


# ==========================================================================
# Item 4 -- job do painel grava clipper.log
# ==========================================================================


def h_painel_grava_log(raiz: Path) -> None:
    """H-4: erro inesperado num job do painel deixa o traceback no clipper.log."""
    from clipper import motor, registro
    from clipper.config import Saida
    from clipper.pipeline import ingest
    from ui import jobs

    base = _pasta(raiz, "h4")
    opcoes = motor.Opcoes(out=base) if "out" in motor.Opcoes.__dataclass_fields__ else None
    if opcoes is None:
        raise Falhou("motor.Opcoes perdeu o campo `out` -- a prova precisa ser revista.")

    original_origem, original_montar, original_rodar = (
        ingest.resolver_origem, motor.montar_estagios, motor.rodar_estagios)
    ingest.resolver_origem = lambda entrada: type("O", (), {"titulo": "t"})()

    def explodir(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("bomba-da-prova-h4")

    # A bomba vai num estagio, onde o erro inesperado acontece de verdade.
    motor.montar_estagios = lambda *_a, **_k: {}
    motor.rodar_estagios = explodir
    try:
        fila = jobs.Fila(base)
        fila._executar(jobs.Pedido(slug="video-a", entrada="x.mp4", opcoes=opcoes))
        fila._executar(jobs.Pedido(slug="video-b", entrada="y.mp4", opcoes=opcoes))
    finally:
        ingest.resolver_origem, motor.montar_estagios, motor.rodar_estagios = (
            original_origem, original_montar, original_rodar)

    log_a = Saida.para("video-a", base).log
    confere(log_a.is_file(), "o job do painel criou clipper.log", str(log_a))
    texto_a = log_a.read_text(encoding="utf-8")
    confere("RuntimeError: bomba-da-prova-h4" in texto_a,
            "o traceback está no clipper.log, como a mensagem promete")
    log_b = Saida.para("video-b", base).log
    confere(texto_a.count("Traceback") == 1 and log_b.is_file(),
            "o log do job seguinte não vaza para a pasta do anterior",
            f"{texto_a.count('Traceback')} traceback(s) no log do video-a")
    presos = [h for h in registro.obter().handlers if getattr(h, "baseFilename", None)]
    confere(not presos, "nenhum FileHandler fica pendurado depois do job",
            str([h.baseFilename for h in presos]))
    job = json.loads((Saida.para("video-a", base).base / "job.json").read_text(encoding="utf-8"))
    confere(job.get("status") == jobs.ERRO, "o job foi marcado como erro", str(job.get("status")))


# ==========================================================================
# Item 8 -- capa/publicacao presas num replace falho nao sao seladas
# ==========================================================================


def h_capa_velha_nao_e_selada(raiz: Path) -> None:
    """H-5: capa ou publicacao.md mais velhos que o mp4 não contam como prontos."""
    from clipper.config import Saida
    from clipper.pipeline import render

    base = _pasta(raiz, "h5")
    saida = Saida.para("video", base).criar_dirs()
    mp4 = saida.clips_dir / "01-um-titulo--cortes.mp4"
    mp4.write_bytes(b"mp4")
    capa, publicacao = render._caminhos_publicacao(mp4)
    capa.write_bytes(b"jpg")
    publicacao.write_text("# t\n", encoding="utf-8", newline="\n")
    _gravar_json(saida.metadados_json, {"clipes": [
        {"id": 1, "preset": "cortes", "arquivo": f"clips/{mp4.name}"}]})

    agora = time.time()
    os.utime(mp4, (agora, agora))
    os.utime(capa, (agora + 1, agora + 1))
    os.utime(publicacao, (agora + 1, agora + 1))
    confere(render._arquivos_no_lugar(saida, "cortes", [1]),
            "controle: capa e publicacao.md novos contam como prontos")

    # O mp4 foi re-encodado, mas o replace() da capa falhou (arquivo aberto):
    # a velha ficou no disco, com tamanho > 0.
    os.utime(capa, (agora - 60, agora - 60))
    confere(not render._arquivos_no_lugar(saida, "cortes", [1]),
            "capa mais velha que o mp4 não sela o estágio")
    os.utime(capa, (agora + 1, agora + 1))
    os.utime(publicacao, (agora - 60, agora - 60))
    confere(not render._arquivos_no_lugar(saida, "cortes", [1]),
            "publicacao.md mais velho que o mp4 não sela o estágio")


def h_publicacao_sem_tmp_orfao(raiz: Path) -> None:
    """H-6: falha ao gravar o publicacao.md não deixa .tmp na pasta de entrega."""
    from clipper.pipeline import render

    base = _pasta(raiz, "h6")
    alvo = base / "01-x--cortes.publicacao.md"
    original = render._substituir

    def travado(_o: Path, _d: Path) -> None:
        raise PermissionError(13, "WinError 5 simulado")

    render._substituir = travado
    try:
        try:
            render._escrever_texto(alvo, "# t\n")
        except PermissionError:
            pass
        else:
            raise Falhou("a falha de escrita tinha de subir para o chamador avisar")
    finally:
        render._substituir = original
    sobras = sorted(p.name for p in base.iterdir())
    confere(not sobras, "nenhum .tmp órfão ficou para trás", str(sobras))


# ==========================================================================
# Itens 10 e 11 -- mensagens do validador
# ==========================================================================


def h_aviso_de_deslocamento(_: Path) -> None:
    """H-7: recusa depois do conserto v1×v1 diz que o início já foi movido."""
    from clipper.pipeline import select

    fr, energia = _cenario()
    # A (v2) pega frases 0-1 e 10-13; B (v1) fica no meio, 2-9, sem tocar A.
    # C (v1) comeca dentro de B: o conserto empurra C para a frase 10 -- que e
    # do A. A recusa cita a faixa JA deslocada.
    a = _clipe_v2(fr, [(0, 1), (10, 13)])
    b = _clipe_v1(fr, 2, 9)
    c = _clipe_v1(fr, 8, 20)
    _, probs = select.validar([a, b, c], fr, energia, n=5)
    confere(any("compartilham material" in p for p in probs),
            "controle: C é recusado por material compartilhado", str(probs)[:200])
    texto = " ".join(probs)
    confere("já tinha sido movido de" in texto,
            "a recusa diz que o início já tinha sido deslocado", texto[:240])


def h_mensagens_conhecem_v2(_: Path) -> None:
    """H-8: 'clipe solto' e 'item não é objeto' falam também da forma v2."""
    from clipper.pipeline import select

    fr, energia = _cenario()
    _, probs = select.validar(_clipe_v2(fr, [(0, 3), (20, 24)]), fr, energia, n=5)
    confere(any("UM clipe solto" in p for p in probs),
            "um v2 solto é reconhecido como clipe solto", str(probs)[:200])
    _, probs = select.validar(["texto"], fr, energia, n=5)
    confere(any("`segmentos`" in p for p in probs),
            "o item que não é objeto cita também `segmentos`", str(probs)[:200])


# ==========================================================================
# Item 13 -- DELETE /jobs/{id} (achado no recon de 15/10)
# ==========================================================================


def h_apagar_job(raiz: Path) -> None:
    """H-9: remover um job da lista responde, em vez de 500 por NameError."""
    _exigir_fastapi()
    from fastapi.testclient import TestClient

    from ui import server

    base = _pasta(raiz, "h9")
    _gravar_json(base / "um-video" / "job.json",
                 {"id": "um-video", "slug": "um-video", "status": "concluido"})
    _gravar_json(base / "do-terminal" / ".estado.json", {"estagios": {}})

    app = server.criar_app(base)
    with TestClient(app, raise_server_exceptions=False) as cliente:
        r = cliente.delete("/jobs/um-video")
        confere(r.status_code < 300, "DELETE de job do painel responde 2xx",
                f"HTTP {r.status_code}")
        confere(not (base / "um-video" / "job.json").exists(),
                "o job.json saiu; a pasta do vídeo ficou")
        confere((base / "um-video").is_dir(), "a pasta do vídeo não foi apagada")
        r = cliente.delete("/jobs/do-terminal")
        confere(r.status_code == 409, "pasta do terminal recebe o 409 explicativo",
                f"HTTP {r.status_code}")


# ==========================================================================
# Item 14 -- erro fora dos `try` do job nao deixa o job em 'rodando'
# ==========================================================================


def h_job_nunca_fica_rodando(raiz: Path) -> None:
    """H-10: erro em montar_estagios() marca o job como erro, com traceback."""
    from clipper import motor
    from clipper.config import Saida
    from clipper.pipeline import ingest
    from ui import jobs

    base = _pasta(raiz, "h10")
    opcoes = motor.Opcoes(out=base)
    original_origem, original_montar = ingest.resolver_origem, motor.montar_estagios
    ingest.resolver_origem = lambda entrada: type("O", (), {"titulo": "t"})()

    def explodir(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("bomba-da-prova-h10")

    motor.montar_estagios = explodir
    try:
        fila = jobs.Fila(base)
        try:
            fila._executar(jobs.Pedido(slug="video", entrada="x.mp4", opcoes=opcoes))
        except RuntimeError:
            raise Falhou("o erro escapou do job e foi parar no worker") from None
    finally:
        ingest.resolver_origem, motor.montar_estagios = original_origem, original_montar

    saida = Saida.para("video", base)
    job = json.loads((saida.base / "job.json").read_text(encoding="utf-8"))
    confere(job.get("status") == jobs.ERRO, "o job termina em erro, não em 'rodando'",
            str(job.get("status")))
    confere("bomba-da-prova-h10" in saida.log.read_text(encoding="utf-8"),
            "o traceback está no clipper.log")


# ==========================================================================
# Item 7 -- o download que virou fonte.mp4 por remux sai de _trabalho
# ==========================================================================


def h_descarte_so_do_baixado(raiz: Path) -> None:
    """H-11: o descarte só alcança `_trabalho/baixado.*`, nunca arquivo do usuário."""
    import logging

    from clipper.config import Saida
    from clipper.pipeline import ingest

    base = _pasta(raiz, "h11")
    saida = Saida.para("video", base).criar_dirs()
    saida.fonte_mp4.write_bytes(b"fonte")
    log = logging.getLogger("prova-h11")

    do_usuario = base / "meu-video.mp4"
    do_usuario.write_bytes(b"original")
    confere(not ingest._descartar_bruto_remuxado(do_usuario, saida, log) and do_usuario.is_file(),
            "arquivo fora de _trabalho nunca é apagado")

    outro = saida.trabalho_dir / "outro.mp4"
    outro.write_bytes(b"x")
    confere(not ingest._descartar_bruto_remuxado(outro, saida, log) and outro.is_file(),
            "arquivo de _trabalho que não é 'baixado.*' fica")

    baixado = saida.trabalho_dir / "baixado.mp4"
    baixado.write_bytes(b"x")
    saida.fonte_mp4.unlink()
    confere(not ingest._descartar_bruto_remuxado(baixado, saida, log) and baixado.is_file(),
            "sem fonte.mp4 válido, o download fica")

    saida.fonte_mp4.write_bytes(b"fonte")
    confere(ingest._descartar_bruto_remuxado(baixado, saida, log) and not baixado.exists(),
            "com fonte.mp4 válido, o baixado.* de _trabalho sai")


# ==========================================================================
# Fisicas
# ==========================================================================


def f_capa_em_fonte_lenta(raiz: Path) -> None:
    """F-H1: capa no último quadro de uma fonte de 5 fps ainda é extraída."""
    from clipper import ffmpeg_utils
    from clipper.pipeline import render

    if shutil.which("ffmpeg") is None:
        raise Pulou("ffmpeg indisponível neste ambiente.")

    base = _pasta(raiz, "fh1")
    mp4 = base / "lento.mp4"
    ffmpeg_utils.rodar(
        ["-f", "lavfi", "-i", "testsrc=size=320x240:rate=5:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(mp4)],
        descricao="fonte de 5 fps",
        timeout=120.0,
    )
    duracao = ffmpeg_utils.sondar(mp4).duracao
    instante = render._instante_da_capa({"inicio": 0.0, "capa_ts": duracao}, [], duracao)
    capa = render._gravar_capa(mp4, instante, base / "lento.capa.jpg")
    confere(capa is not None and capa.stat().st_size > 0,
            "a capa sai mesmo com o instante no último intervalo de quadro",
            f"instante {instante:.3f}s de {duracao:.3f}s, 5 fps")


def _semear_download(raiz: Path, nome: str) -> tuple[Path, Any]:
    """Pasta de job com um 'download' h264+aac ja em _trabalho.

    O _baixar() reaproveita baixado.* existente sem chamar o yt-dlp, entao a
    prova atravessa o ingerir() real sem rede.
    """
    from clipper.config import Saida
    from provas.gerar_clipe_curto import gerar

    base = _pasta(raiz, nome)
    saida = Saida.para("video", base).criar_dirs()
    gerar(saida.trabalho_dir / "baixado.mp4", 4.0)
    return base, saida


def f_bruto_remuxado_sai(raiz: Path) -> None:
    """F-H2: remux apaga o download; reencode e arquivo local não."""
    from clipper.config import Estado
    from clipper.pipeline import ingest

    if shutil.which("ffmpeg") is None:
        raise Pulou("ffmpeg indisponível neste ambiente.")

    url = ingest.Origem(tipo="url", valor="https://exemplo.invalid/v", slug="video", titulo="t")

    _, saida = _semear_download(raiz, "fh2-remux")
    bruto = saida.trabalho_dir / "baixado.mp4"
    dados = ingest.ingerir(url, saida, Estado(saida.estado_json))
    confere(dados["normalizado"]["reencodado"] is False, "controle: o caminho foi remux")
    confere(not bruto.exists(), "remux: o download saiu de _trabalho")
    confere(saida.fonte_mp4.stat().st_size > 0 and saida.audio_wav.is_file(),
            "fonte.mp4 e audio.wav ficaram")
    confere(dados.get("bruto_descartado") is True, "o descarte ficou registrado no estado")
    de_novo = ingest.ingerir(url, saida, Estado(saida.estado_json))
    confere(de_novo.get("reaproveitado") is True,
            "rodar de novo reaproveita a ingestão sem precisar do download")

    _, saida = _semear_download(raiz, "fh2-reencode")
    bruto = saida.trabalho_dir / "baixado.mp4"
    dados = ingest.ingerir(url, saida, Estado(saida.estado_json), reencodar=True)
    confere(dados["normalizado"]["reencodado"] is True, "controle: o caminho foi reencode")
    confere(bruto.is_file(), "reencode: o download (único original) fica")

    base, saida = _semear_download(raiz, "fh2-local")
    local = base / "meu-video.mp4"
    shutil.move(str(saida.trabalho_dir / "baixado.mp4"), local)
    arquivo = ingest.Origem(tipo="arquivo", valor=str(local), slug="video", titulo="t")
    dados = ingest.ingerir(arquivo, saida, Estado(saida.estado_json))
    confere(dados["normalizado"]["reencodado"] is False, "controle: arquivo local por remux")
    confere(local.is_file(), "arquivo local do usuário nunca é apagado")


# ==========================================================================
# Registro e execucao
# ==========================================================================

ESTRUTURAIS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "H-1": ("item 1: retomada do painel ignora pasta do terminal", h_retomada_ignora_terminal),
    "H-2": ("item 2: stream do painel solta o mp4 entre pedaços", h_stream_solta_o_arquivo),
    "H-3": ("item 2: replace() do render tolera handle transitório", h_replace_tolera_handle_curto),
    "H-4": ("item 4: job do painel grava o traceback em clipper.log", h_painel_grava_log),
    "H-5": ("item 8: capa/publicacao.md velhos não selam o estágio", h_capa_velha_nao_e_selada),
    "H-6": ("item 8: falha no publicacao.md não deixa .tmp órfão", h_publicacao_sem_tmp_orfao),
    "H-7": ("item 10: recusa avisa que o início já foi deslocado", h_aviso_de_deslocamento),
    "H-8": ("item 11: mensagens de forma conhecem o v2", h_mensagens_conhecem_v2),
    "H-9": ("item 13: DELETE /jobs/{id} não quebra com NameError", h_apagar_job),
    "H-10": ("item 14: erro no início do job não o deixa em 'rodando'", h_job_nunca_fica_rodando),
    "H-11": ("item 7: descarte só alcança _trabalho/baixado.*", h_descarte_so_do_baixado),
}

FISICAS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "F-H1": ("item 9: capa no último quadro de fonte < 20 fps", f_capa_em_fonte_lenta),
    "F-H2": ("item 7: remux apaga o download; reencode e local não", f_bruto_remuxado_sai),
}


def main(argv: list[str]) -> int:
    quer_fisicas = "--fisicas" in argv
    nomes = [a.upper() for a in argv if not a.startswith("--")]

    casos: dict[str, tuple[str, Callable[[Path], None]]] = dict(ESTRUTURAIS)
    if quer_fisicas:
        casos.update(FISICAS)
    pedidos = [n for n in nomes if n in casos] or list(casos)
    raiz = RAIZ / "_teste" / "out-prova-f61"

    titulo = "PROVAS DO CLIP-F6.1 — higiene"
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
