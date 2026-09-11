"""Painel web local do ClipPro: a segunda cabine do mesmo motor.

O servidor NAO tem regra de pipeline. Ele recebe um pedido, monta um
motor.Opcoes, chama a fila (ui/jobs.py) e serve o resultado. Toda decisao
sobre estagio, idempotencia, validacao e render continua em clipper/.

BIND 127.0.0.1 E DE PROPOSITO, E E UMA REGRA DE SEGURANCA. O painel nao pede
senha, lista o conteudo de out/ e serve os videos do usuario. Abrir em
0.0.0.0 entregaria tudo isso para qualquer maquina da rede -- em Wi-Fi de
cafe, para qualquer um. O host e constante neste arquivo; nao vira flag.

Convencao deste arquivo: comentarios e docstrings em PT-BR sem acento;
mensagens dirigidas ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)

from clipper import config, ffmpeg_utils, motor, registro
from clipper.config import Estado, Saida, slugificar
from clipper.erros import ErroClipper
from ui import jobs as filas

HOST = "127.0.0.1"
PORTA = 8765

ESTATICOS = Path(__file__).resolve().parent / "estaticos"

# Pedaco lido por vez ao servir video. 512 KB e o compromisso medido: pedaco
# menor multiplica chamadas de sistema, maior segura memoria a toa.
_PEDACO = 512 * 1024

_PADRAO_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def criar_app(raiz_saida: Path | None = None) -> FastAPI:
    raiz = Path(raiz_saida or config.DIR_SAIDA_PADRAO)
    raiz.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="ClipPro", docs_url=None, redoc_url=None)
    fila = filas.Fila(raiz)
    app.state.raiz = raiz
    app.state.fila = fila

    @app.on_event("startup")
    def _subir() -> None:
        fila.iniciar()
        _retomar_interrompidos(raiz, fila)

    @app.on_event("shutdown")
    def _descer() -> None:
        fila.encerrar()

    # ---------------------------------------------------------------- telas
    @app.get("/", response_class=HTMLResponse)
    def home() -> HTMLResponse:
        return HTMLResponse((ESTATICOS / "index.html").read_text(encoding="utf-8"))

    @app.get("/styles.css")
    def css() -> FileResponse:
        return FileResponse(ESTATICOS / "styles.css", media_type="text/css")

    @app.get("/app.js")
    def js() -> FileResponse:
        return FileResponse(
            ESTATICOS / "app.js", media_type="application/javascript"
        )

    @app.get("/api/padroes")
    def padroes() -> dict[str, Any]:
        """O que o formulario precisa saber para nascer preenchido."""
        return {
            "estrategia": config.ESTRATEGIA_PADRAO,
            "n": motor.N_PADRAO,
            "preset": motor.PRESET_PADRAO,
            "presets": sorted(p.stem for p in config.DIR_PRESETS.glob("*.json")),
            "modelo_whisper": config.MODELO_WHISPER_PADRAO,
            "modelos_whisper": list(motor.MODELOS_WHISPER),
            "tem_chave_api": config.chave_api_anthropic() is not None,
        }

    # ---------------------------------------------------------------- jobs
    @app.get("/jobs")
    def listar() -> dict[str, Any]:
        return {
            "jobs": filas.listar_jobs(raiz),
            "em_execucao": fila.em_execucao,
        }

    @app.post("/jobs")
    async def criar(
        request: Request,
        url: str | None = Form(default=None),
        arquivo: UploadFile | None = File(default=None),
        n: int | None = Form(default=None),
        estrategia: str | None = Form(default=None),
        preset: str | None = Form(default=None),
        modelo_whisper: str | None = Form(default=None),
        usar_api: bool | None = Form(default=False),
    ) -> JSONResponse:
        """Cria (ou reabre) o job de um video, por URL ou por upload.

        Aceita multipart (com upload) e JSON (so URL): o formulario do painel
        manda multipart, e quem chama de script normalmente manda JSON.
        """
        if request.headers.get("content-type", "").startswith("application/json"):
            corpo = await request.json()
            url = corpo.get("url") or url
            n = corpo.get("n", n)
            estrategia = corpo.get("estrategia", estrategia)
            preset = corpo.get("preset", preset)
            modelo_whisper = corpo.get("modelo_whisper", modelo_whisper)
            usar_api = corpo.get("usar_api", usar_api)

        if arquivo is not None and arquivo.filename:
            entrada, slug = await _receber_upload(arquivo, raiz)
        elif url and str(url).strip():
            entrada = str(url).strip()
            try:
                from clipper.pipeline import ingest

                origem = ingest.resolver_origem(entrada)
            except ErroClipper as exc:
                return _erro_http(400, exc)
            slug = origem.slug
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "mensagem": "não veio nem link nem arquivo.",
                    "sugestao": "cole um link de vídeo ou arraste um arquivo.",
                },
            )

        opcoes = motor.Opcoes(
            n=int(n or motor.N_PADRAO),
            estrategia=str(estrategia or config.ESTRATEGIA_PADRAO),
            preset=str(preset or motor.PRESET_PADRAO),
            modelo_whisper=str(modelo_whisper or config.MODELO_WHISPER_PADRAO),
            usar_api=bool(usar_api) and config.chave_api_anthropic() is not None,
        )
        job = fila.enfileirar(
            filas.Pedido(slug=slug, entrada=entrada, opcoes=opcoes, comando="run")
        )
        return JSONResponse(job, status_code=201)

    def _detalhar(saida: Saida, job: dict[str, Any]) -> dict[str, Any]:
        """O job com o que so se sabe olhando o disco (clipes, estimativa).

        A rota de detalhe E o primeiro evento do SSE usam esta funcao: se o
        evento inicial mandasse o job cru, a tela desenharia a grade de clipes
        com o detalhe e apagaria tudo um instante depois, quando o SSE
        conectasse.
        """
        preset = str((job.get("opcoes") or {}).get("preset") or motor.PRESET_PADRAO)
        completo = dict(job)
        completo["clipes"] = filas.clipes_do_job(saida, preset)
        completo["estimativa"] = filas.estimativa_segundos(saida, job)
        completo["prompt_existe"] = saida.prompt_selecao_txt.is_file()
        completo["pasta"] = str(saida.base)
        return completo

    @app.get("/jobs/{job_id}")
    def detalhe(job_id: str) -> dict[str, Any]:
        saida, job = _exigir_job(raiz, job_id)
        return _detalhar(saida, job)

    @app.get("/jobs/{job_id}/prompt")
    def prompt(job_id: str) -> Response:
        """O texto do prompt de seleção, para o botão de copiar."""
        saida, _ = _exigir_job(raiz, job_id)
        if not saida.prompt_selecao_txt.is_file():
            raise HTTPException(
                status_code=404,
                detail={
                    "mensagem": "este vídeo ainda não tem prompt de seleção gravado.",
                    "sugestao": "espere a transcrição terminar.",
                },
            )
        return Response(
            saida.prompt_selecao_txt.read_text(encoding="utf-8"),
            media_type="text/plain; charset=utf-8",
        )

    @app.post("/jobs/{job_id}/prompt-resposta")
    async def resposta_manual(job_id: str, request: Request) -> JSONResponse:
        """Recebe o JSON colado, roda o VALIDADOR EXISTENTE e segue, ou recusa.

        Nada de validacao nova aqui: grava o texto num arquivo e chama o mesmo
        estagio de selecao que o CLI chama com --resposta. Se a resposta estiver
        torta, o erro que volta e o mesmo que o terminal mostraria, quebrado em
        itens para a tela listar um a um.
        """
        saida, job = _exigir_job(raiz, job_id)
        corpo = await request.json()
        texto = str(corpo.get("resposta") or "").strip()
        if not texto:
            raise HTTPException(
                status_code=400,
                detail={
                    "mensagem": "a resposta veio vazia.",
                    "sugestao": "cole o array JSON que o modelo devolveu.",
                },
            )

        destino = saida.base / "resposta.json"
        destino.write_text(texto, encoding="utf-8")

        opcoes = filas.opcoes_de_json(job.get("opcoes") or {})
        opcoes = dataclasses.replace(opcoes, resposta=destino)
        estado = Estado(saida.estado_json)

        from clipper.pipeline import select

        try:
            resultado = select.selecionar(
                saida,
                estado,
                estrategia=opcoes.estrategia,
                n=opcoes.n,
                modelo=opcoes.modelo,
                resposta_manual=str(destino),
                usar_api=False,
            )
        except ErroClipper as exc:
            return _erro_http(422, exc)

        # Selecao aceita: o job volta para a fila e segue do render em diante.
        job["estagios"] = {**(job.get("estagios") or {}), "selecao": {
            "status": "pronto",
            "rotulo": motor.ROTULOS_CURTOS["selecao"],
            "segundos": 0.0,
            "terminado_em": filas.agora(),
        }}
        filas.gravar(saida, job)
        fila.enfileirar(
            filas.Pedido(
                slug=job_id,
                entrada=str(job.get("entrada") or job_id),
                opcoes=opcoes,
                comando="run",
            )
        )
        return JSONResponse({"ok": True, "selecao": resultado}, status_code=202)

    @app.post("/jobs/{job_id}/rerender")
    async def rerender(job_id: str, request: Request) -> JSONResponse:
        """Refaz o render, opcionalmente de um clipe so e/ou em outro preset."""
        saida, job = _exigir_job(raiz, job_id)
        corpo = {}
        try:
            corpo = await request.json()
        except Exception:  # noqa: BLE001 - corpo vazio e valido
            corpo = {}
        base = filas.opcoes_de_json(job.get("opcoes") or {})
        clipe = corpo.get("clip_n")
        opcoes = dataclasses.replace(
            base,
            preset=str(corpo.get("preset") or base.preset),
            clipes=[int(clipe)] if clipe else None,
            forcar=bool(corpo.get("forcar", False)),
        )
        job["opcoes"] = filas.opcoes_para_json(opcoes)
        filas.gravar(saida, job)
        novo = fila.enfileirar(
            filas.Pedido(
                slug=job_id,
                entrada=str(job.get("entrada") or job_id),
                opcoes=opcoes,
                comando="render",
                somente=("render",),
            )
        )
        return JSONResponse(novo, status_code=202)

    @app.delete("/jobs/{job_id}")
    def apagar(job_id: str) -> JSONResponse:
        """Remove o job da listagem. NAO apaga vídeo nem clipe do disco."""
        saida, _ = _exigir_job(raiz, job_id)
        if fila.em_execucao == job_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "mensagem": "este vídeo está sendo processado agora.",
                    "sugestao": "espere o estágio atual terminar e tente de novo.",
                },
            )
        if job.get("do_terminal") and not filas.caminho_job(saida).is_file():
            raise HTTPException(
                status_code=409,
                detail={
                    "mensagem": "este vídeo foi processado pelo terminal, não pelo painel.",
                    "sugestao": (
                        "ele aparece na lista porque a pasta existe em out/. Para tirá-lo "
                        f"da lista, apague a pasta: {saida.base}"
                    ),
                },
            )
        alvo = filas.caminho_job(saida)
        try:
            alvo.unlink(missing_ok=True)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "mensagem": f"não consegui remover {alvo.name}.",
                    "sugestao": f"apague o arquivo à mão: {alvo}",
                    "detalhe": str(exc),
                },
            ) from exc
        return JSONResponse({"ok": True, "pasta_mantida": str(saida.base)})

    @app.post("/jobs/{job_id}/abrir-pasta")
    def abrir_pasta(job_id: str) -> JSONResponse:
        """Abre out/<slug>/ no explorador do sistema (o painel é local)."""
        saida, _ = _exigir_job(raiz, job_id)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(saida.base))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.run(["open", str(saida.base)], check=False)
            else:
                subprocess.run(["xdg-open", str(saida.base)], check=False)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "mensagem": "não consegui abrir a pasta.",
                    "sugestao": f"abra à mão: {saida.base}",
                    "detalhe": str(exc),
                },
            ) from exc
        return JSONResponse({"ok": True, "pasta": str(saida.base)})

    # -------------------------------------------------------------- eventos
    @app.get("/jobs/{job_id}/events")
    def eventos(job_id: str) -> StreamingResponse:
        """SSE: uma linha por transição de estágio, mais batimento.

        O primeiro evento é sempre o estado atual -- assim um cliente que
        conecta no meio do trabalho já desenha a tela certa sem esperar a
        próxima transição.
        """
        saida, job = _exigir_job(raiz, job_id)
        assinatura = fila.barramento.inscrever(job_id)

        def fluxo() -> Iterator[bytes]:
            try:
                yield _sse({"tipo": "estado", "job": _detalhar(saida, job)})
                ultimo = time.monotonic()
                while True:
                    try:
                        evento = assinatura.get(timeout=1.0)
                    except Exception:  # noqa: BLE001 - Empty
                        evento = None
                    if evento is not None:
                        yield _sse(evento)
                        if evento.get("tipo") in ("concluido", "erro", "aguardando"):
                            # Nao fecha: o job pode voltar a rodar (re-render).
                            pass
                    agora = time.monotonic()
                    if agora - ultimo >= 15.0:
                        ultimo = agora
                        yield b": batimento\n\n"
            finally:
                fila.barramento.cancelar(job_id, assinatura)

        return StreamingResponse(
            fluxo(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # --------------------------------------------------------------- video
    @app.get("/jobs/{job_id}/clips/{numero}.jpg")
    def miniatura(job_id: str, numero: int) -> Response:
        """Um quadro do clipe, para a grade não ser um mural de retângulos pretos.

        Sem miniatura o <video> precisaria de preload="metadata" para desenhar
        algo, e cinco players baixando metadado de arquivos de 20 a 70 MB ao
        mesmo tempo estouram o limite de conexões do navegador -- a grade fica
        girando. A miniatura é extraída uma vez e cacheada em _trabalho/.
        """
        saida, job = _exigir_job(raiz, job_id)
        alvo = _mp4_do_clipe(saida, job, numero)
        destino = saida.trabalho_dir / f"miniatura_{numero}_{int(alvo.stat().st_mtime)}.jpg"
        if not destino.is_file():
            destino.parent.mkdir(parents=True, exist_ok=True)
            try:
                ffmpeg_utils.rodar(
                    [
                        "-ss", "0.6", "-i", str(alvo),
                        "-frames:v", "1", "-vf", "scale=360:-2",
                        "-q:v", "5", str(destino),
                    ],
                    descricao=f"miniatura do clipe {numero}",
                    timeout=60.0,
                )
            except ErroClipper:
                raise HTTPException(
                    status_code=404,
                    detail={"mensagem": f"não consegui extrair a miniatura do clipe {numero}."},
                ) from None
        return FileResponse(destino, media_type="image/jpeg")

    @app.get("/jobs/{job_id}/clips/{numero}.mp4")
    def clipe(job_id: str, numero: int, request: Request) -> Response:
        """Serve o mp4 com suporte a Range -- sem isso o player não busca."""
        saida, job = _exigir_job(raiz, job_id)
        return _servir_com_range(_mp4_do_clipe(saida, job, numero), request)

    return app


# ==========================================================================
# Apoio
# ==========================================================================


def _mp4_do_clipe(saida: Saida, job: dict[str, Any], numero: int) -> Path:
    """O arquivo do clipe N deste job, ou 404 com mensagem util."""
    preset = str((job.get("opcoes") or {}).get("preset") or motor.PRESET_PADRAO)
    for c in filas.clipes_do_job(saida, preset):
        if int(c.get("id") or 0) == int(numero):
            alvo = saida.base / str(c["arquivo"])
            if alvo.is_file():
                return alvo
    raise HTTPException(
        status_code=404,
        detail={
            "mensagem": f"não achei o clipe {numero} deste vídeo.",
            "sugestao": "renderize de novo pelo botão do card.",
        },
    )


def _sse(evento: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(evento, ensure_ascii=False)}\n\n".encode("utf-8")


def _erro_http(codigo: int, exc: ErroClipper) -> JSONResponse:
    """Traduz um ErroClipper para JSON, quebrando o detalhe em itens.

    O validador da selecao junta os problemas numa lista numerada dentro de
    'detalhe'. A tela quer mostrar item a item, entao a quebra acontece aqui --
    e nao no navegador, que nao deveria conhecer esse formato.
    """
    itens = [
        re.sub(r"^\d+\.\s*", "", linha).strip()
        for linha in str(exc.detalhe or "").splitlines()
        if linha.strip()
    ]
    return JSONResponse(
        {
            "mensagem": exc.mensagem,
            "sugestao": exc.sugestao or "",
            "detalhe": exc.detalhe or "",
            "problemas": itens,
        },
        status_code=codigo,
    )


def _exigir_job(raiz: Path, job_id: str) -> tuple[Saida, dict[str, Any]]:
    """Resolve o job pelo slug, recusando qualquer coisa que saia de out/.

    O que se confere aqui e CONTENCAO DE CAMINHO, nao formato de slug. A
    primeira versao exigia que o id fosse igual ao proprio slugificar() dele --
    e slugificar() poe tudo em minuscula, enquanto o slug de um video de URL
    termina com o id remoto COMO ELE E ("...-qp3uNTpf"). O painel recusava,
    com 'identificador inválido', exatamente os videos vindos de link.
    """
    nome = str(job_id).strip()
    raiz_real = Path(raiz).resolve()
    if (
        not nome
        or nome in (".", "..")
        or "/" in nome
        or "\\" in nome
        or ":" in nome
        or chr(0) in nome
    ):
        raise HTTPException(
            status_code=400,
            detail={"mensagem": f"identificador inválido: '{job_id}'."},
        )
    try:
        destino = (raiz_real / nome).resolve()
        destino.relative_to(raiz_real)
    except (OSError, ValueError):
        raise HTTPException(
            status_code=400,
            detail={"mensagem": f"identificador inválido: '{job_id}'."},
        ) from None
    saida = Saida.para(nome, raiz)
    job = filas.ler_job(saida.base)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "mensagem": f"não há nenhum trabalho gravado para '{job_id}'.",
                "sugestao": "volte à tela inicial e comece um vídeo novo.",
            },
        )
    return saida, job


async def _receber_upload(arquivo: UploadFile, raiz: Path) -> tuple[str, str]:
    """Grava o upload em out/<slug>/source/ SEM passar pela memória.

    O slug sai do nome do arquivo -- o mesmo que ingest.resolver_origem faria
    com um caminho local -- então o arquivo já nasce na pasta definitiva do
    vídeo, e não num diretório de passagem.
    """
    nome = Path(str(arquivo.filename or "video.mp4")).name
    slug = slugificar(Path(nome).stem)
    destino_dir = Saida.para(slug, raiz).base / "source"
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / nome
    parcial = destino.with_name(destino.name + ".parcial")
    try:
        with parcial.open("wb") as saida_arquivo:
            while True:
                pedaco = await arquivo.read(_PEDACO)
                if not pedaco:
                    break
                saida_arquivo.write(pedaco)
        parcial.replace(destino)
    except OSError as exc:
        try:
            parcial.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(
            status_code=500,
            detail={
                "mensagem": f"não consegui gravar o upload em {destino_dir}.",
                "sugestao": "confira o espaço em disco e tente de novo.",
                "detalhe": str(exc),
            },
        ) from exc
    finally:
        await arquivo.close()
    return str(destino), slug


def _servir_com_range(alvo: Path, request: Request) -> Response:
    """Resposta 206 quando o player pede um pedaco, 200 quando pede tudo.

    O <video> do navegador manda 'Range: bytes=...' para buscar no meio do
    video. Sem 206 o player baixa o arquivo inteiro para pular 10 segundos --
    ou simplesmente nao deixa arrastar a linha do tempo.
    """
    tamanho = alvo.stat().st_size
    cabecalho = request.headers.get("range") or request.headers.get("Range")
    comuns = {
        "Accept-Ranges": "bytes",
        "Content-Type": "video/mp4",
        "Cache-Control": "no-cache",
    }

    if not cabecalho:
        return FileResponse(alvo, media_type="video/mp4", headers={"Accept-Ranges": "bytes"})

    achado = _PADRAO_RANGE.match(cabecalho.strip())
    if not achado:
        return Response(status_code=416, headers={**comuns, "Content-Range": f"bytes */{tamanho}"})

    bruto_ini, bruto_fim = achado.group(1), achado.group(2)
    if bruto_ini == "":
        # "bytes=-500": os ultimos 500 bytes.
        comprimento = min(int(bruto_fim or 0), tamanho)
        inicio = max(0, tamanho - comprimento)
        fim = tamanho - 1
    else:
        inicio = int(bruto_ini)
        fim = int(bruto_fim) if bruto_fim else tamanho - 1
    fim = min(fim, tamanho - 1)
    if inicio > fim or inicio >= tamanho:
        return Response(status_code=416, headers={**comuns, "Content-Range": f"bytes */{tamanho}"})

    def ler() -> Iterator[bytes]:
        restante = fim - inicio + 1
        with alvo.open("rb") as f:
            f.seek(inicio)
            while restante > 0:
                pedaco = f.read(min(_PEDACO, restante))
                if not pedaco:
                    break
                restante -= len(pedaco)
                yield pedaco

    return StreamingResponse(
        ler(),
        status_code=206,
        headers={
            **comuns,
            "Content-Range": f"bytes {inicio}-{fim}/{tamanho}",
            "Content-Length": str(fim - inicio + 1),
        },
    )


def _retomar_interrompidos(raiz: Path, fila: filas.Fila) -> None:
    """Recoloca na fila o que ficou pela metade quando o processo morreu.

    Um job gravado como 'rodando' ou 'na fila' nao terminou -- ninguem regrava
    o status na saida abrupta. Reenfileirar e seguro porque cada estagio decide
    sozinho se refaz: a transcricao pronta nao roda de novo, o render que parou
    no meio reencoda so o clipe que faltava.
    """
    log = registro.obter()
    for job in filas.listar_jobs(raiz):
        if job.get("status") not in (filas.RODANDO, filas.NA_FILA):
            continue
        slug = str(job.get("slug") or job.get("id") or "")
        entrada = str(job.get("entrada") or "")
        if not slug or not entrada:
            continue
        opcoes = filas.opcoes_de_json(job.get("opcoes") or {})
        log.info(f"   retomando '{slug}': estava em '{job.get('estagio')}'.")
        fila.enfileirar(
            filas.Pedido(
                slug=slug,
                entrada=entrada,
                opcoes=opcoes,
                comando=str(job.get("comando") or "run"),
            )
        )


def servir(raiz_saida: Path | None = None, abrir_navegador: bool = True) -> None:
    """Sobe o painel. Chamado por 'clipper ui'."""
    import uvicorn

    app = criar_app(raiz_saida)
    if abrir_navegador:
        import threading
        import webbrowser

        threading.Timer(1.2, lambda: webbrowser.open(f"http://{HOST}:{PORTA}/")).start()
    uvicorn.run(app, host=HOST, port=PORTA, log_level="warning", access_log=False)
