"""O motor do pipeline: quais estagios existem, em que ordem, e como roda-los.

DUAS CABINES, UM MOTOR. O CLI (clipper/cli.py) e o painel web (ui/server.py)
usam este modulo; nenhum dos dois sabe COMO um estagio funciona nem repete a
regra de ordem. Quem mexe na fila mexe aqui, e as duas cabines mudam juntas.

O que mora aqui:
  - os padroes das flags (um so lugar, lido pelo argparse e pelo formulario web);
  - Opcoes, o objeto de parametros que as duas cabines preenchem;
  - Estagio, que amarra nome, rotulo, artefato e a funcao do pipeline;
  - montar_estagios(), que faz essa amarracao sem executar nada;
  - rodar_estagios(), que executa a fila em ordem e avisa cada transicao.

O que NAO mora aqui: apresentacao. Tabela no terminal, bloco de proximos passos,
SSE, HTML -- isso e da cabine.

Convencao deste arquivo: comentarios e docstrings em PT-BR sem acento; mensagens
dirigidas ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from clipper import config, registro
from clipper.config import Estado, Saida
from clipper.erros import ErroRender, ErroSelecao

# --------------------------------------------------------------------------
# Padroes das flags (o argparse e o formulario do painel leem daqui)
# --------------------------------------------------------------------------
N_PADRAO = 5
PRESET_PADRAO = "cortes"
MODELO_PADRAO = "haiku"
MODELOS_API = ("haiku", "sonnet")
IDIOMA_PADRAO = "pt"
MODELOS_WHISPER = ("tiny", "base", "small", "medium", "large-v3")
# Altura maxima do download. 1080 nao e estetica: e o teto do H.264 no
# YouTube. Acima disso vem VP9/AV1, que obriga a ingestao a reencodar o
# video inteiro na CPU -- horas, num video longo -- em vez de remuxar em
# segundos. O clipe final e 1080x1920, entao 1080p de origem paga a conta.
ALTURA_MAX_PADRAO = 1080

# Estagios que ainda nao existem. Este conjunto e o unico lugar que decide se
# um 'clipper run' para com elegancia (codigo 0) ao esbarrar neles.
# HOJE ELE ESTA VAZIO: todo estagio da fila e real e uma falha dele volta a ser
# falha de verdade. O conjunto vazio e um estado NORMAL e suportado --
# rodar_estagios simplesmente nunca entra no ramo "nao_existe".
# O maquinario de parada elegante continua de pe porque ele serve a OUTRA
# parada, que nao tem nada de provisoria: a selecao em modo manual devolve
# {"pendente": True} e o pipeline termina em 0 esperando o usuario.
ESTAGIOS_PENDENTES: frozenset[str] = frozenset()

# Ordem canonica dos estagios e quais rodam em cada subcomando.
ESTAGIOS_POR_COMANDO: dict[str, tuple[str, ...]] = {
    "run": ("ingestao", "transcricao", "energia", "selecao", "render"),
    "ingest": ("ingestao",),
    "transcribe": ("ingestao", "transcricao", "energia"),
    "select": ("ingestao", "transcricao", "energia", "selecao"),
    "render": ("render",),
    "info": ("ingestao", "transcricao", "energia", "selecao", "render"),
}

# O que cada subcomando REFAZ quando o usuario passa --force. Nao confundir com
# ESTAGIOS_POR_COMANDO, que lista o que o subcomando EXECUTA: 'select' executa
# ingestao/transcricao/energia porque precisa delas prontas, mas quem pede
# 'select --force' quer refazer a SELECAO (0,1 s) -- nao rebaixar 1 GB de video
# e rodar 20 minutos de whisper por cima do artefato de que o prompt saiu.
# Os estagios de fora deste conjunto continuam decidindo pela propria
# assinatura: mudou parametro deles, refazem sozinhos.
ESTAGIOS_ALVO_DO_FORCE: dict[str, tuple[str, ...]] = {
    "run": ("ingestao", "transcricao", "energia", "selecao", "render"),
    "ingest": ("ingestao",),
    "transcribe": ("transcricao", "energia"),
    "select": ("selecao",),
    "render": ("render",),
    "info": (),
}

# Rotulo curto de cada estagio, para quem precisa nomear a etapa sem montar o
# rotulo completo (o painel, a barra de progresso, o job.json).
ROTULOS_CURTOS: dict[str, str] = {
    "ingestao": "Baixar",
    "transcricao": "Transcrever",
    "energia": "Energia do áudio",
    "selecao": "Selecionar",
    "render": "Renderizar",
}


# --------------------------------------------------------------------------
# Opcoes normalizadas
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Opcoes:
    """Flags ja normalizadas, com padrao para o que a cabine nao define."""

    out: Path | None = None
    forcar: bool = False
    verboso: bool = False
    n: int = N_PADRAO
    estrategia: str = config.ESTRATEGIA_PADRAO
    preset: str = PRESET_PADRAO
    modelo: str = MODELO_PADRAO
    modelo_whisper: str = config.MODELO_WHISPER_PADRAO
    idioma: str = IDIOMA_PADRAO
    threads: int | None = None
    vad: bool = True
    reencodar: bool = False
    altura_max: int | None = ALTURA_MAX_PADRAO
    resposta: Path | None = None
    usar_api: bool = False
    # None = renderiza a selecao inteira. Lista = so estes ids.
    clipes: list[int] | None = None
    pitch: bool = False

    @classmethod
    def de_args(cls, args: Any) -> "Opcoes":
        """Constroi a partir de um Namespace do argparse (cabine de terminal)."""
        return cls(
            out=getattr(args, "out", None),
            forcar=bool(getattr(args, "force", False)),
            verboso=bool(getattr(args, "verboso", False)),
            n=int(getattr(args, "n", N_PADRAO)),
            estrategia=str(getattr(args, "estrategia", config.ESTRATEGIA_PADRAO)),
            preset=str(getattr(args, "preset", PRESET_PADRAO)),
            modelo=str(getattr(args, "modelo", MODELO_PADRAO)),
            modelo_whisper=str(
                getattr(args, "modelo_whisper", config.MODELO_WHISPER_PADRAO)
            ),
            idioma=str(getattr(args, "idioma", IDIOMA_PADRAO)),
            threads=getattr(args, "threads", None),
            vad=not bool(getattr(args, "sem_vad", False)),
            reencodar=bool(getattr(args, "reencodar_fonte", False)),
            altura_max=getattr(args, "altura_max", ALTURA_MAX_PADRAO),
            resposta=getattr(args, "resposta", None),
            usar_api=bool(getattr(args, "api", False)),
            # argparse com action="append" devolve None quando a flag nao veio.
            # Lista vazia recebe o mesmo tratamento de None: "renderize tudo" e
            # o padrao, e uma lista vazia significaria "nao renderize nada".
            clipes=([int(c) for c in getattr(args, "clipe", None) or ()] or None),
            pitch=bool(getattr(args, "pitch", False)),
        )


# --------------------------------------------------------------------------
# Estagios
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Estagio:
    """Um passo do pipeline: como chamar, como rotular e o que ele produz.

    'padrao' so importa quando o artefato e uma PASTA: e o glob dos arquivos
    que contam como resultado do estagio. O render grava .mp4 em clips/, e e o
    tamanho somado deles que o resumo mostra -- nao o de qualquer arquivo que
    tenha ido parar la.
    """

    nome: str
    rotulo: str
    artefato: Path
    executar: Callable[[], Any]
    pendente: bool = False
    padrao: str | None = None


@dataclass(frozen=True)
class Parada:
    """Motivo pelo qual a fila de estagios terminou antes do fim, sem erro.

    Sao dois motivos, e eles nao se parecem:

      "nao_existe"  -- o estagio ainda nao foi implementado. O pipeline para
                       porque o clipper acaba ali. Com ESTAGIOS_PENDENTES
                       vazio (o caso de hoje) este motivo nunca acontece; o
                       ramo fica de pe para a proxima fase que entrar meio
                       pronta.
      "aguardando"  -- o estagio rodou, fez o que tinha que fazer e devolveu
                       {"pendente": True}: falta uma acao do usuario. Hoje so
                       a selecao em modo manual faz isso -- e ela nao e
                       provisoria, e o funcionamento normal do modo manual.
    """

    estagio: Estagio
    motivo: str
    resultado: dict[str, Any]


def rotulo_render(opcoes: Opcoes) -> str:
    """Rotulo do estagio de render, dizendo tambem se ele foi restringido.

    O render de 5 clipes leva minutos: quando o usuario pediu --clipe, a tela
    precisa deixar claro que o resto da selecao NAO esta sendo refeito.
    """
    rotulo = f"Render dos clipes (preset {opcoes.preset})"
    if opcoes.clipes:
        ids = ", ".join(str(c) for c in opcoes.clipes)
        rotulo += f", apenas o(s) clipe(s) {ids}"
    return rotulo


def montar_estagios(
    opcoes: Opcoes,
    origem: Any,
    saida: Saida,
    estado: Estado,
    forcados: frozenset[str] = frozenset(),
) -> dict[str, Estagio]:
    """Amarra cada estagio aos seus argumentos, sem executar nada ainda.

    'forcados' e o conjunto de estagios que o --force deste subcomando refaz
    (ver ESTAGIOS_ALVO_DO_FORCE). Quem esta fora dele recebe forcar=False e
    continua reaproveitando o que ja existe -- e o que impede um
    'select --force' de disparar download e whisper de novo.
    """
    # Import tardio: 'clipper --help' e 'clipper info' nao precisam pagar o
    # custo de carregar faster-whisper/ctranslate2.
    from clipper.pipeline import ingest, render, select, transcribe

    def _forcar(nome: str) -> bool:
        return nome in forcados

    def _fazer(
        nome: str,
        rotulo: str,
        artefato: Path,
        alvo: Callable[[], Any],
        padrao: str | None = None,
    ) -> Estagio:
        return Estagio(
            nome=nome,
            rotulo=rotulo,
            artefato=artefato,
            executar=alvo,
            pendente=nome in ESTAGIOS_PENDENTES,
            padrao=padrao,
        )

    estagios = [
        _fazer(
            "ingestao",
            "Ingestão do vídeo",
            saida.fonte_mp4,
            lambda: ingest.ingerir(
                origem,
                saida,
                estado,
                forcar=_forcar("ingestao"),
                reencodar=opcoes.reencodar,
                altura_max=opcoes.altura_max,
            ),
        ),
        _fazer(
            "transcricao",
            f"Transcrição (whisper {opcoes.modelo_whisper})",
            saida.transcricao_json,
            lambda: transcribe.transcrever(
                saida,
                estado,
                modelo=opcoes.modelo_whisper,
                idioma=opcoes.idioma,
                forcar=_forcar("transcricao"),
                threads=opcoes.threads,
                vad=opcoes.vad,
            ),
        ),
        _fazer(
            "energia",
            "Curva de energia do áudio",
            saida.energia_json,
            lambda: transcribe.calcular_energia(
                saida, estado, forcar=_forcar("energia")
            ),
        ),
        _fazer(
            "selecao",
            # O rotulo segue a MESMA regra de prioridade do select.py: com
            # --resposta o arquivo local vence, mesmo que --api esteja junto.
            # A tela nao pode anunciar 'API' enquanto le um arquivo do disco.
            (
                f"Seleção dos clipes (API {opcoes.modelo})"
                if opcoes.usar_api and opcoes.resposta is None
                else "Seleção dos clipes (modo manual)"
            ),
            saida.selecao_json,
            lambda: select.selecionar(
                saida,
                estado,
                estrategia=opcoes.estrategia,
                n=opcoes.n,
                modelo=opcoes.modelo,
                forcar=_forcar("selecao"),
                resposta_manual=str(opcoes.resposta) if opcoes.resposta else None,
                usar_api=opcoes.usar_api,
            ),
        ),
        _fazer(
            "render",
            rotulo_render(opcoes),
            saida.clips_dir,
            lambda: render.renderizar(
                saida,
                estado,
                preset=opcoes.preset,
                forcar=_forcar("render"),
                clipes=opcoes.clipes,
                pitch=opcoes.pitch,
            ),
            padrao="*.mp4",
        ),
    ]
    return {e.nome: e for e in estagios}


def rodar_estagios(
    estagios: Iterable[Estagio],
    medidos: dict[str, float],
    *,
    tolerar_pendentes: bool,
    ao_iniciar: Callable[[Estagio], None] | None = None,
    ao_concluir: Callable[[Estagio, Any, float], None] | None = None,
) -> Parada | None:
    """Roda os estagios em ordem.

    Devolve None se todos rodaram ate o fim. Devolve uma Parada quando a fila
    foi interrompida sem que isso seja erro: um estagio ainda nao implementado
    e o chamador aceitou parar ali (tolerar_pendentes=True, usado so pelo
    'run'), ou um estagio que devolveu {"pendente": True} porque a bola agora
    esta com o usuario.

    'ao_iniciar' e 'ao_concluir' sao os ganchos da cabine: o terminal nao usa
    nenhum dos dois (ele ja tem o log), e o painel usa os dois para gravar
    job.json e empurrar o evento de progresso. Um gancho que levanta excecao
    NAO derruba o pipeline -- progresso e enfeite, o trabalho e o que importa.
    """
    log = registro.obter()

    def _avisar(gancho: Callable[..., None] | None, *args: Any) -> None:
        if gancho is None:
            return
        try:
            gancho(*args)
        except Exception:  # noqa: BLE001 - relatar progresso nunca derruba o render
            log.debug("gancho de progresso falhou", exc_info=True)

    for est in estagios:
        _avisar(ao_iniciar, est)
        try:
            with registro.etapa(est.rotulo) as crono:
                resultado = est.executar()
            medidos[est.nome] = crono.segundos
        except (ErroSelecao, ErroRender) as exc:
            if not (tolerar_pendentes and est.pendente):
                raise
            log.info("")
            log.info(f"   {exc.mensagem}")
            if exc.sugestao:
                log.info(f"   -> {exc.sugestao}")
            return Parada(est, "nao_existe", {})
        _avisar(ao_concluir, est, resultado, medidos.get(est.nome, 0.0))
        if isinstance(resultado, dict) and resultado.get("pendente"):
            return Parada(est, "aguardando", resultado)
    return None
