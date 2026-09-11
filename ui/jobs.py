"""A fila de trabalhos do painel: estado em disco, worker unico e eventos.

TRES DECISOES QUE EXPLICAM O RESTO:

1. O JOB E O SLUG. Nao ha banco nem id sintetico: o trabalho de um video mora
   em out/<slug>/job.json, do lado dos artefatos dele. Mandar o mesmo video
   duas vezes reabre o MESMO job -- que e o comportamento certo, porque os
   estagios ja sabem pular o que esta pronto. Um id separado criaria dois jobs
   apontando para a mesma pasta, competindo pelos mesmos arquivos.

2. UM WORKER SO, FILA FIFO. Cada estagio ja usa a maquina inteira (o whisper
   ocupa todos os nucleos, o x264 tambem). Dois jobs em paralelo nao terminam
   mais rapido: terminam os dois mais devagar, e disputam disco. A fila
   serializa de proposito, e a prova P7 assere isso.

3. RETOMADA E IDEMPOTENCIA, NAO CHECKPOINT. Se o processo morre no meio, o
   job volta para a fila e roda os MESMOS estagios de novo -- quem decide o
   que refazer e o .estado.json de cada estagio, que ja existia antes do
   painel. O job.json nao guarda "de onde continuar"; ele guarda o que
   aconteceu, para a tela mostrar.

Convencao deste arquivo: comentarios e docstrings em PT-BR sem acento;
mensagens dirigidas ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import dataclasses
import json
import queue
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from clipper import config, motor, registro
from clipper.config import Estado, Saida, escrever_json
from clipper.erros import ErroClipper

# Estados possiveis de um job. Quem le a tela ve estes nomes.
NA_FILA = "na_fila"
RODANDO = "rodando"
AGUARDANDO = "aguardando_resposta"  # modo manual: a bola esta com o usuario
CONCLUIDO = "concluido"
ERRO = "erro"
CANCELADO = "cancelado"

# Peso de cada estagio na barra de progresso. Nao e igual por estagio porque a
# transcricao sozinha leva mais tempo que todo o resto somado: uma barra que
# desse 20% a cada estagio ficaria parada em 40% por vinte minutos.
# Medido no video de teste (29 min): ingestao 35s, transcricao 1197s,
# energia 0,3s, selecao 0s, render 343s.
PESO_ESTAGIO: dict[str, float] = {
    "ingestao": 0.04,
    "transcricao": 0.62,
    "energia": 0.01,
    "selecao": 0.01,
    "render": 0.32,
}

# Quanto tempo de transcricao esperar por segundo de audio, medido na F1 nesta
# maquina (whisper medium, CPU, int8): 1196,89s para 1745,7s de audio.
FATOR_TRANSCRICAO = 0.685
# Render do preset de composicao, medido na F4: 313s de encode para 261s de
# clipe.
FATOR_RENDER = 1.20


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ==========================================================================
# O job em disco
# ==========================================================================


def caminho_job(saida: Saida) -> Path:
    return saida.base / "job.json"


def ler_job(base: Path) -> dict[str, Any] | None:
    """Le out/<slug>/job.json, ou DEDUZ um job de uma pasta feita no terminal.

    Quem processou pelo CLI nao tem job.json -- e apareceria como "nenhum video
    processado ainda" num painel que esta olhando para a pasta cheia dele. A
    deducao le o que ja existe (.estado.json, fonte.json, metadados.json) e
    monta um job somente-leitura, com a marca 'do_terminal' para a tela poder
    dizer de onde ele veio.
    """
    base = Path(base)
    alvo = base / "job.json"
    try:
        dados = json.loads(alvo.read_text(encoding="utf-8"))
        if isinstance(dados, dict):
            return dados
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return _job_deduzido(base)


def _preset_mais_recente(base: Path, metadados: dict[str, Any]) -> str:
    """Qual preset a pasta mostra: o do render mais NOVO em clips/.

    Uma pasta acumula renders de varios presets (foi assim que os dois
    candidatos da F4a conviveram). Pegar o ultimo da lista 'presets_usados' e
    pegar o ultimo em ordem ALFABETICA -- e foi o que fez o painel exibir dois
    clipes de um preset velho no lugar dos cinco do preset atual.
    """
    melhor, melhor_mtime = motor.PRESET_PADRAO, -1.0
    for clipe in metadados.get("clipes") or []:
        if not isinstance(clipe, dict):
            continue
        arquivo = base / str(clipe.get("arquivo") or "")
        try:
            mtime = arquivo.stat().st_mtime
        except OSError:
            continue
        if mtime > melhor_mtime:
            melhor, melhor_mtime = str(clipe.get("preset") or motor.PRESET_PADRAO), mtime
    return melhor


def _job_deduzido(base: Path) -> dict[str, Any] | None:
    """O job de uma pasta que o terminal produziu. None se nao for uma."""
    estado = base / ".estado.json"
    if not estado.is_file():
        return None

    def _ler(caminho: Path) -> dict[str, Any]:
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            return dados if isinstance(dados, dict) else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}

    dados_estado = _ler(estado)
    fonte = _ler(base / "fonte.json")
    metadados = _ler(base / "metadados.json")
    origem = fonte.get("origem") if isinstance(fonte.get("origem"), dict) else {}

    duracoes = dados_estado.get("duracoes") or {}
    feitos = {}
    for nome in PESO_ESTAGIO:
        if nome in (dados_estado.get("estagios") or {}):
            feitos[nome] = {
                "status": "pronto",
                "rotulo": motor.ROTULOS_CURTOS.get(nome, nome),
                "segundos": float(duracoes.get(nome) or 0.0),
            }

    preset = _preset_mais_recente(base, metadados)
    try:
        criado = datetime.fromtimestamp(estado.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        criado = agora()

    job = {
        "id": base.name,
        "slug": base.name,
        "entrada": str(origem.get("valor") or base.name),
        "titulo": str(origem.get("titulo") or base.name),
        "criado_em": criado,
        "atualizado_em": criado,
        "status": CONCLUIDO if metadados.get("clipes") else NA_FILA,
        "estagio": None,
        "erro": None,
        "comando": "run",
        "opcoes": {"preset": preset, "n": len(metadados.get("clipes") or []) or motor.N_PADRAO},
        "estagios": feitos,
        "do_terminal": True,
    }
    job["progresso"] = _progresso(job)
    return job


def listar_jobs(raiz: Path) -> list[dict[str, Any]]:
    """Todos os jobs gravados em out/*/job.json, do mais novo para o mais velho."""
    achados: list[dict[str, Any]] = []
    try:
        pastas = sorted(p for p in Path(raiz).iterdir() if p.is_dir())
    except OSError:
        return []
    for pasta in pastas:
        dados = ler_job(pasta)
        if dados:
            achados.append(dados)
    achados.sort(key=lambda j: str(j.get("criado_em") or ""), reverse=True)
    return achados


# ==========================================================================
# Eventos (SSE)
# ==========================================================================


class Barramento:
    """Distribui eventos de um job para quem estiver ouvindo.

    Cada ouvinte tem a propria fila: um navegador lento nao segura o worker.
    Fila cheia descarta o evento mais antigo -- progresso e informacao
    perecivel, e travar o pipeline para nao perder um evento seria absurdo.
    """

    def __init__(self, tamanho: int = 256) -> None:
        self._tamanho = tamanho
        self._ouvintes: dict[str, list[queue.Queue]] = {}
        self._trava = threading.Lock()

    def inscrever(self, job_id: str) -> queue.Queue:
        fila: queue.Queue = queue.Queue(maxsize=self._tamanho)
        with self._trava:
            self._ouvintes.setdefault(job_id, []).append(fila)
        return fila

    def cancelar(self, job_id: str, fila: queue.Queue) -> None:
        with self._trava:
            if job_id in self._ouvintes:
                try:
                    self._ouvintes[job_id].remove(fila)
                except ValueError:
                    pass
                if not self._ouvintes[job_id]:
                    self._ouvintes.pop(job_id, None)

    def publicar(self, job_id: str, evento: dict[str, Any]) -> None:
        with self._trava:
            filas = list(self._ouvintes.get(job_id, ()))
        for fila in filas:
            try:
                fila.put_nowait(evento)
            except queue.Full:
                try:
                    fila.get_nowait()
                    fila.put_nowait(evento)
                except (queue.Empty, queue.Full):
                    continue

    def ouvintes(self, job_id: str) -> int:
        with self._trava:
            return len(self._ouvintes.get(job_id, ()))


# ==========================================================================
# A fila
# ==========================================================================


@dataclass
class Pedido:
    """O que a rota POST /jobs coloca na fila."""

    slug: str
    entrada: str
    opcoes: motor.Opcoes
    comando: str = "run"
    # Quando o usuario pede re-render de um clipe, so o estagio de render roda.
    somente: tuple[str, ...] | None = None


class Fila:
    """Fila FIFO com UM worker. O coracao do painel.

    A fila nao sabe o que um estagio faz: ela chama motor.rodar_estagios() e
    traduz as transicoes em job.json + evento. Toda regra de pipeline continua
    em clipper/.
    """

    def __init__(self, raiz_saida: Path) -> None:
        self.raiz = Path(raiz_saida)
        self.barramento = Barramento()
        self._fila: queue.Queue[Pedido | None] = queue.Queue()
        self._trava = threading.Lock()
        self._atual: str | None = None
        self._parar = threading.Event()
        self._worker: threading.Thread | None = None

    # ------------------------------------------------------------ ciclo
    def iniciar(self) -> None:
        if self._worker is not None:
            return
        self._worker = threading.Thread(
            target=self._rodar, name="clipper-worker", daemon=True
        )
        self._worker.start()

    def encerrar(self, timeout: float = 2.0) -> None:
        self._parar.set()
        self._fila.put(None)
        if self._worker is not None:
            self._worker.join(timeout=timeout)

    @property
    def em_execucao(self) -> str | None:
        with self._trava:
            return self._atual

    # ------------------------------------------------------------ entrada
    def enfileirar(self, pedido: Pedido) -> dict[str, Any]:
        """Grava o job como 'na fila' e devolve o job.json ja atualizado.

        QUEM MANDA NA RAIZ E A FILA. Um pedido que chega sem 'out' herda a raiz
        do painel aqui, num ponto so -- senao Saida.para() cairia no out/ padrao
        do pacote e o trabalho iria parar noutra pasta que nao a que o painel
        esta mostrando (era o que acontecia com 'clipper ui --out DIR').
        """
        if pedido.opcoes.out is None:
            pedido = dataclasses.replace(
                pedido, opcoes=dataclasses.replace(pedido.opcoes, out=self.raiz)
            )
        saida = Saida.para(pedido.slug, pedido.opcoes.out)
        saida.criar_dirs()
        job = ler_job(saida.base) or {}
        job.update(
            {
                "id": pedido.slug,
                "slug": pedido.slug,
                "entrada": pedido.entrada,
                "criado_em": job.get("criado_em") or agora(),
                "atualizado_em": agora(),
                "status": NA_FILA,
                "estagio": None,
                # NAO zera o progresso: um job volta para a fila depois da
                # resposta manual e depois de um re-render, e nas duas vezes
                # metade do trabalho ja esta feita. Zerar fazia a barra andar
                # PARA TRAS na cara do usuario (a prova P5 pega isso).
                "progresso": _progresso(job),
                "erro": None,
                "comando": pedido.comando,
                "opcoes": opcoes_para_json(pedido.opcoes),
                "estagios": job.get("estagios") or {},
                "titulo": job.get("titulo") or pedido.entrada,
            }
        )
        gravar(saida, job)
        self.barramento.publicar(pedido.slug, {"tipo": "estado", "job": job})
        self._fila.put(pedido)
        return job

    # ------------------------------------------------------------ worker
    def _rodar(self) -> None:
        while not self._parar.is_set():
            pedido = self._fila.get()
            if pedido is None:
                break
            with self._trava:
                self._atual = pedido.slug
            try:
                self._executar(pedido)
            except BaseException:  # noqa: BLE001 - o worker nao pode morrer
                registro.obter().error(
                    "falha inesperada no worker do painel:\n" + traceback.format_exc()
                )
            finally:
                with self._trava:
                    self._atual = None
                self._fila.task_done()

    def _executar(self, pedido: Pedido) -> None:
        from clipper.pipeline import ingest

        saida = Saida.para(pedido.slug, pedido.opcoes.out)
        saida.criar_dirs()
        estado = Estado(saida.estado_json)
        job = ler_job(saida.base) or {}

        alvos = pedido.somente or motor.ESTAGIOS_POR_COMANDO[pedido.comando]
        forcados = frozenset(
            motor.ESTAGIOS_ALVO_DO_FORCE.get(pedido.comando, ())
            if pedido.opcoes.forcar
            else ()
        )

        job.update({"status": RODANDO, "atualizado_em": agora(), "erro": None})
        gravar(saida, job)
        self.barramento.publicar(pedido.slug, {"tipo": "estado", "job": job})

        try:
            origem = ingest.resolver_origem(pedido.entrada)
        except ErroClipper as exc:
            self._falhar(saida, pedido.slug, exc)
            return

        job["titulo"] = getattr(origem, "titulo", None) or pedido.entrada
        gravar(saida, job)

        estagios = motor.montar_estagios(pedido.opcoes, origem, saida, estado, forcados)
        fila_estagios = [estagios[n] for n in alvos if n in estagios]
        medidos: dict[str, float] = {}

        def ao_iniciar(est: motor.Estagio) -> None:
            job["estagio"] = est.nome
            job["status"] = RODANDO
            anterior = (job.get("estagios") or {}).get(est.nome) or {}
            job.setdefault("estagios", {})[est.nome] = {
                "status": "rodando",
                "rotulo": motor.ROTULOS_CURTOS.get(est.nome, est.nome),
                "iniciado_em": agora(),
                # Um job que volta para a fila (resposta manual, re-render)
                # reentra em estagios que JA terminaram. Sem esta marca, a
                # barra recuava a cada reentrada -- o estagio saia de 'pronto'
                # para 'rodando' e perdia o peso dele na conta.
                "concluido_antes": anterior.get("status") == "pronto"
                or bool(anterior.get("concluido_antes")),
            }
            job["progresso"] = _progresso(job, em_curso=est.nome)
            job["atualizado_em"] = agora()
            gravar(saida, job)
            self.barramento.publicar(
                pedido.slug,
                {"tipo": "estagio", "estagio": est.nome, "status": "rodando", "job": job},
            )

        def ao_concluir(est: motor.Estagio, resultado: Any, segundos: float) -> None:
            reaproveitado = bool(
                isinstance(resultado, dict) and resultado.get("reaproveitado")
            )
            anterior = (job.get("estagios") or {}).get(est.nome) or {}
            job.setdefault("estagios", {})[est.nome] = {
                "status": "pronto",
                "rotulo": motor.ROTULOS_CURTOS.get(est.nome, est.nome),
                "segundos": round(float(segundos), 2),
                "reaproveitado": reaproveitado,
                # O inicio e PRESERVADO: sem ele ninguem consegue medir a
                # janela do estagio -- nem a tela, nem a prova que assere que
                # dois jobs nunca rodam ao mesmo tempo.
                "iniciado_em": anterior.get("iniciado_em"),
                "terminado_em": agora(),
            }
            job["progresso"] = _progresso(job)
            job["atualizado_em"] = agora()
            gravar(saida, job)
            self.barramento.publicar(
                pedido.slug,
                {"tipo": "estagio", "estagio": est.nome, "status": "pronto", "job": job},
            )

        try:
            parada = motor.rodar_estagios(
                fila_estagios,
                medidos,
                tolerar_pendentes=False,
                ao_iniciar=ao_iniciar,
                ao_concluir=ao_concluir,
            )
        except ErroClipper as exc:
            self._falhar(saida, pedido.slug, exc)
            return
        except BaseException as exc:  # noqa: BLE001
            registro.obter().error("erro inesperado no job:\n" + traceback.format_exc())
            self._falhar(saida, pedido.slug, exc)
            return

        if parada is not None and parada.motivo == "aguardando":
            # Modo manual: o prompt foi gravado e o pipeline parou de proposito.
            job["status"] = AGUARDANDO
            job["estagio"] = parada.estagio.nome
            job["prompt"] = str(
                parada.resultado.get("prompt") or saida.prompt_selecao_txt
            )
            job["atualizado_em"] = agora()
            gravar(saida, job)
            self.barramento.publicar(
                pedido.slug, {"tipo": "aguardando", "job": job}
            )
            return

        job["status"] = CONCLUIDO
        job["estagio"] = None
        job["progresso"] = 1.0
        job["clipes"] = _clipes_do_disco(saida, pedido.opcoes.preset)
        job["atualizado_em"] = agora()
        gravar(saida, job)
        self.barramento.publicar(pedido.slug, {"tipo": "concluido", "job": job})

    def _falhar(self, saida: Saida, slug: str, exc: BaseException) -> None:
        """Grava o erro no job do jeito que o usuario le -- nunca um traceback."""
        job = ler_job(saida.base) or {}
        if isinstance(exc, ErroClipper):
            erro = {
                "mensagem": exc.mensagem,
                "sugestao": exc.sugestao or "",
                "detalhe": exc.detalhe or "",
            }
        else:
            erro = {
                "mensagem": "o clipper encontrou um erro inesperado neste vídeo.",
                "sugestao": (
                    "o traceback completo está em clipper.log, dentro da pasta do "
                    "vídeo. Repita o comando: os estágios que já terminaram são "
                    "reaproveitados."
                ),
                "detalhe": f"{type(exc).__name__}: {exc}",
            }
        job.update({"status": ERRO, "erro": erro, "atualizado_em": agora()})
        gravar(saida, job)
        self.barramento.publicar(slug, {"tipo": "erro", "job": job})


# ==========================================================================
# Apoio
# ==========================================================================


def gravar(saida: Saida, job: dict[str, Any]) -> None:
    """Escrita atomica do job.json. Falha aqui nao derruba o pipeline."""
    try:
        escrever_json(caminho_job(saida), job)
    except OSError:
        registro.obter().warning("não consegui gravar o job.json deste vídeo.")


def opcoes_para_json(opcoes: motor.Opcoes) -> dict[str, Any]:
    return {
        "n": opcoes.n,
        "estrategia": opcoes.estrategia,
        "preset": opcoes.preset,
        "modelo": opcoes.modelo,
        "modelo_whisper": opcoes.modelo_whisper,
        "idioma": opcoes.idioma,
        "usar_api": opcoes.usar_api,
        "pitch": opcoes.pitch,
        "forcar": opcoes.forcar,
        "clipes": opcoes.clipes,
        "out": str(opcoes.out) if opcoes.out else None,
    }


def opcoes_de_json(dados: dict[str, Any]) -> motor.Opcoes:
    """O caminho de volta: job.json -> Opcoes (usado na retomada e no re-render)."""
    dados = dados if isinstance(dados, dict) else {}
    out = dados.get("out")
    return motor.Opcoes(
        out=Path(out) if out else None,
        n=int(dados.get("n") or motor.N_PADRAO),
        estrategia=str(dados.get("estrategia") or config.ESTRATEGIA_PADRAO),
        preset=str(dados.get("preset") or motor.PRESET_PADRAO),
        modelo=str(dados.get("modelo") or motor.MODELO_PADRAO),
        modelo_whisper=str(
            dados.get("modelo_whisper") or config.MODELO_WHISPER_PADRAO
        ),
        idioma=str(dados.get("idioma") or motor.IDIOMA_PADRAO),
        usar_api=bool(dados.get("usar_api")),
        pitch=bool(dados.get("pitch")),
        forcar=bool(dados.get("forcar")),
        clipes=list(dados["clipes"]) if dados.get("clipes") else None,
    )


def _progresso(job: dict[str, Any], em_curso: str | None = None) -> float:
    """Fracao concluida, ponderada pelo peso medido de cada estagio.

    O estagio em curso conta METADE do peso dele: sem isso a barra fica parada
    os vinte minutos da transcricao e o usuario acha que travou.
    """
    feitos = job.get("estagios") or {}
    total = 0.0
    for nome, peso in PESO_ESTAGIO.items():
        registro_estagio = feitos.get(nome) or {}
        if registro_estagio.get("status") == "pronto" or registro_estagio.get(
            "concluido_antes"
        ):
            total += peso
        elif nome == em_curso:
            total += peso * 0.5
    return round(min(1.0, total), 4)


def estimativa_segundos(saida: Saida, job: dict[str, Any]) -> dict[str, float]:
    """Quanto ainda deve levar, pelos fatores medidos nesta maquina.

    Nao promete: informa. A transcricao e a unica parte cara e previsivel (ela
    escala com a duracao do audio), e o render escala com a soma dos clipes.
    """
    duracao = 0.0
    try:
        fonte = json.loads(saida.fonte_info_json.read_text(encoding="utf-8"))
        duracao = float(((fonte.get("midia") or {}).get("duracao")) or 0.0)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        duracao = 0.0

    feitos = job.get("estagios") or {}
    faltando = 0.0
    if duracao > 0:
        if (feitos.get("transcricao") or {}).get("status") != "pronto":
            faltando += duracao * FATOR_TRANSCRICAO
        if (feitos.get("render") or {}).get("status") != "pronto":
            # Sem selecao ainda, estima pelos limites do projeto: n clipes de
            # ~45s. Com selecao, usa a duracao real somada.
            try:
                selecao = json.loads(saida.selecao_json.read_text(encoding="utf-8"))
                somada = sum(float(c["fim"]) - float(c["inicio"]) for c in selecao["clipes"])
            except Exception:  # noqa: BLE001
                somada = float((job.get("opcoes") or {}).get("n") or 5) * 45.0
            faltando += somada * FATOR_RENDER
    return {"restante_s": round(faltando, 1), "duracao_fonte_s": round(duracao, 1)}


def _clipes_do_disco(saida: Saida, preset: str) -> list[dict[str, Any]]:
    """Os clipes do preset pedido, lidos de metadados.json.

    Filtra por preset de proposito: a mesma pasta pode ter renders antigos em
    outros presets, e a tela do job mostra o que ESTE job produziu.
    """
    try:
        dados = json.loads(saida.metadados_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    clipes = [c for c in (dados.get("clipes") or []) if isinstance(c, dict)]
    do_preset = [c for c in clipes if str(c.get("preset")) == str(preset)]
    escolhidos = do_preset or clipes
    escolhidos.sort(key=lambda c: (-(float(c.get("score_0_10") or 0)), int(c.get("id") or 0)))
    saida_lista = []
    for c in escolhidos:
        arquivo = str(c.get("arquivo") or "")
        if not (saida.base / arquivo).is_file():
            continue
        saida_lista.append(
            {
                "id": c.get("id"),
                "preset": c.get("preset"),
                "titulo": c.get("titulo"),
                "score": c.get("score_0_10"),
                "motivo": c.get("motivo"),
                "gancho": c.get("gancho_sugerido"),
                "duracao": c.get("duracao"),
                "inicio_mmss": c.get("inicio_mmss"),
                "fim_mmss": c.get("fim_mmss"),
                "arquivo": arquivo,
                "bytes": (c.get("render") or {}).get("bytes"),
            }
        )
    return saida_lista


def clipes_do_job(saida: Saida, preset: str) -> list[dict[str, Any]]:
    """Versao publica de _clipes_do_disco (as rotas leem por aqui)."""
    return _clipes_do_disco(saida, preset)
