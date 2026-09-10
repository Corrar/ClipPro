"""Interface de linha de comando do ClipPro.

Um subcomando por estagio (mais 'run' que roda tudo e 'info' que so olha).
O CLI nao contem regra de negocio: ele resolve a origem, monta o layout de
saida, configura o log e chama os estagios na ordem certa. Toda falha
esperada chega aqui como ErroClipper e vira uma mensagem curta e acionavel;
falha inesperada vira traceback no arquivo de log e um bloco de 3 linhas na
tela. Traceback cru no console: nunca.
"""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from clipper import __version__, config, registro
from clipper.config import Estado, Saida, humanizar_bytes, humanizar_tempo
from clipper.erros import ErroClipper, ErroIngestao, ErroRender, ErroSelecao

# --------------------------------------------------------------------------
# Padroes das flags (um so lugar: o argparse e a classe Opcoes leem daqui)
# --------------------------------------------------------------------------
N_PADRAO = 5
PRESET_PADRAO = "bold-amarelo"
MODELO_PADRAO = "haiku"
MODELOS_API = ("haiku", "sonnet")
IDIOMA_PADRAO = "pt"
MODELOS_WHISPER = ("tiny", "base", "small", "medium", "large-v3")
# Altura maxima do download. 1080 nao e estetica: e o teto do H.264 no
# YouTube. Acima disso vem VP9/AV1, que obriga a ingestao a reencodar o
# video inteiro na CPU -- horas, num video longo -- em vez de remuxar em
# segundos. O clipe final e 1080x1920, entao 1080p de origem paga a conta.
ALTURA_MAX_PADRAO = 1080

# Estagios que ainda nao existem (F2/F3). Este conjunto e o unico lugar que
# decide se um 'clipper run' para com elegancia (codigo 0) ao esbarrar neles.
# Quando a fase entrar, tire o nome daqui e o erro volta a ser erro de verdade.
ESTAGIOS_PENDENTES: frozenset[str] = frozenset({"selecao", "render"})

# Ordem canonica dos estagios e quais rodam em cada subcomando.
ESTAGIOS_POR_COMANDO: dict[str, tuple[str, ...]] = {
    "run": ("ingestao", "transcricao", "energia", "selecao", "render"),
    "ingest": ("ingestao",),
    "transcribe": ("ingestao", "transcricao", "energia"),
    "select": ("ingestao", "transcricao", "energia", "selecao"),
    "render": ("render",),
    "info": ("ingestao", "transcricao", "energia", "selecao", "render"),
}

_EPILOGO = """\
exemplos:
  clipper run aula.mp4
  clipper run "https://youtu.be/XXXXXXXXXXX" --n 8 --preset bold-amarelo
  clipper transcribe aula.mp4 --modelo-whisper small --threads 8
  clipper select aula.mp4 --estrategia "ganchos e punchlines" --modelo sonnet
  clipper render aula.mp4 --preset bold-amarelo
  clipper info aula.mp4

observacoes:
  - todo artefato fica em out/<slug>/; rodar de novo reaproveita o que ja existe.
  - use --force para reprocessar do zero.
  - a selecao usa a API da Anthropic: exporte ANTHROPIC_API_KEY antes.
"""


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------
def _inteiro_positivo(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{texto}' não é um número inteiro.") from None
    if valor < 1:
        raise argparse.ArgumentTypeError(f"'{texto}' precisa ser um inteiro >= 1.")
    return valor


def _pai_entrada() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument(
        "entrada",
        help="caminho de um vídeo local ou URL (YouTube, Twitch VOD, etc.)",
    )
    return p


def _pai_global() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("opções gerais")
    g.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar="DIR",
        help=f"diretório raiz de saída (padrão: {config.DIR_SAIDA_PADRAO})",
    )
    g.add_argument(
        "--force",
        action="store_true",
        help="reprocessa tudo, ignorando os artefatos já existentes",
    )
    g.add_argument(
        "-v",
        "--verboso",
        action="store_true",
        help="mostra o log em nível DEBUG no console",
    )
    return p


def _pai_ingestao() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("opções de ingestão")
    g.add_argument(
        "--reencodar-fonte",
        action="store_true",
        help="força reencode do vídeo de origem mesmo se ele já for h264+aac",
    )
    g.add_argument(
        "--altura-max",
        type=int,
        default=ALTURA_MAX_PADRAO,
        metavar="PIXELS",
        help=(
            f"altura máxima do vídeo baixado de uma URL (padrão: {ALTURA_MAX_PADRAO}). "
            "O YouTube só entrega H.264 até 1080p; acima disso é VP9/AV1 e a "
            "ingestão precisa reencodar o vídeo inteiro na CPU (horas). "
            "Use 0 para não limitar. Não afeta arquivos locais."
        ),
    )
    return p


def _pai_transcricao() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("opções de transcrição")
    g.add_argument(
        "--modelo-whisper",
        default=config.MODELO_WHISPER_PADRAO,
        choices=MODELOS_WHISPER,
        metavar="NOME",
        help=(
            "modelo do faster-whisper: "
            + "/".join(MODELOS_WHISPER)
            + f" (padrão: {config.MODELO_WHISPER_PADRAO})"
        ),
    )
    g.add_argument(
        "--idioma",
        default=IDIOMA_PADRAO,
        metavar="CODIGO",
        help=f"código do idioma falado no vídeo (padrão: {IDIOMA_PADRAO})",
    )
    g.add_argument(
        "--threads",
        type=_inteiro_positivo,
        default=None,
        metavar="INT",
        help="threads de CPU na transcrição (padrão: todos os núcleos)",
    )
    g.add_argument(
        "--sem-vad",
        action="store_true",
        help="desliga o filtro de voz (VAD) do whisper, que vem ligado",
    )
    return p


def _pai_selecao() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("opções de seleção")
    g.add_argument(
        "--n",
        type=_inteiro_positivo,
        default=N_PADRAO,
        metavar="INT",
        help=f"número máximo de clipes a produzir (padrão: {N_PADRAO})",
    )
    g.add_argument(
        "--estrategia",
        default=config.ESTRATEGIA_PADRAO,
        metavar="TEXTO",
        help=f"o que procurar no vídeo (padrão: {config.ESTRATEGIA_PADRAO!r})",
    )
    g.add_argument(
        "--modelo",
        default=MODELO_PADRAO,
        choices=MODELOS_API,
        help=f"modelo da API usado na seleção (padrão: {MODELO_PADRAO})",
    )
    return p


def _pai_render() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("opções de render")
    g.add_argument(
        "--preset",
        default=PRESET_PADRAO,
        metavar="NOME",
        help=f"preset visual da legenda (padrão: {PRESET_PADRAO})",
    )
    return p


def construir_parser() -> argparse.ArgumentParser:
    """Monta o parser completo, com um subcomando por estagio."""
    entrada = _pai_entrada()
    geral = _pai_global()
    ingestao = _pai_ingestao()
    transcricao = _pai_transcricao()
    selecao = _pai_selecao()
    render = _pai_render()

    parser = argparse.ArgumentParser(
        prog="clipper",
        description=(
            "ClipPro — transforma um vídeo longo em clipes verticais 9:16 "
            "com legenda queimada."
        ),
        epilog=_EPILOGO,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--versao",
        action="version",
        version=f"clipper {__version__}",
        help="mostra a versão e sai",
    )

    subs = parser.add_subparsers(dest="comando", title="comandos", metavar="COMANDO")

    subs.add_parser(
        "run",
        parents=[entrada, geral, ingestao, transcricao, selecao, render],
        help="pipeline completo: ingestão -> transcrição -> seleção -> render",
        description="Roda o pipeline inteiro, do vídeo bruto aos clipes prontos.",
    )
    subs.add_parser(
        "ingest",
        parents=[entrada, geral, ingestao],
        help="só baixa/normaliza o vídeo e extrai o áudio",
        description="Resolve a origem, normaliza para fonte.mp4 e extrai audio.wav.",
    )
    subs.add_parser(
        "transcribe",
        parents=[entrada, geral, ingestao, transcricao],
        help="transcreve o áudio e calcula a curva de energia",
        description=(
            "Faz a ingestão se ainda faltar, transcreve com o faster-whisper e "
            "gera a curva de energia do áudio."
        ),
    )
    p_select = subs.add_parser(
        "select",
        parents=[entrada, geral, ingestao, transcricao, selecao],
        help="escolhe os melhores trechos (usa a API da Anthropic)",
        description=(
            "Roda o que faltar de ingestão/transcrição e então escolhe os trechos, "
            "gravando selecao.json."
        ),
    )
    p_select.add_argument(
        "--resposta",
        type=Path,
        default=None,
        metavar="ARQUIVO",
        help=(
            "modo manual: usa este resposta.json (colado à mão) em vez de "
            "chamar a API"
        ),
    )
    subs.add_parser(
        "render",
        parents=[entrada, geral, render],
        help="renderiza os clipes a partir de uma seleção pronta",
        description=(
            "Exige um selecao.json já pronto em out/<slug>/ e renderiza os clipes."
        ),
    )
    subs.add_parser(
        "info",
        parents=[entrada, geral],
        help="mostra o estado de cada estágio em out/<slug>/",
        description="Não processa nada: só resolve a origem e relata o que já existe.",
    )
    return parser


# --------------------------------------------------------------------------
# Opcoes normalizadas
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Opcoes:
    """Flags ja normalizadas, com padrao para o que o subcomando nao define."""

    out: Path | None
    forcar: bool
    verboso: bool
    n: int
    estrategia: str
    preset: str
    modelo: str
    modelo_whisper: str
    idioma: str
    threads: int | None
    vad: bool
    reencodar: bool
    altura_max: int | None
    resposta: Path | None

    @classmethod
    def de_args(cls, args: argparse.Namespace) -> "Opcoes":
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
        )


# --------------------------------------------------------------------------
# Estagios
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Estagio:
    """Um passo do pipeline: como chamar, como rotular e o que ele produz."""

    nome: str
    rotulo: str
    artefato: Path
    executar: Callable[[], Any]
    pendente: bool = False


def _montar_estagios(
    opcoes: Opcoes,
    origem: Any,
    saida: Saida,
    estado: Estado,
) -> dict[str, Estagio]:
    """Amarra cada estagio aos seus argumentos, sem executar nada ainda."""
    # Import tardio: 'clipper --help' e 'clipper info' nao precisam pagar o
    # custo de carregar faster-whisper/ctranslate2.
    from clipper.pipeline import ingest, render, select, transcribe

    def _fazer(nome: str, rotulo: str, artefato: Path, alvo: Callable[[], Any]) -> Estagio:
        return Estagio(
            nome=nome,
            rotulo=rotulo,
            artefato=artefato,
            executar=alvo,
            pendente=nome in ESTAGIOS_PENDENTES,
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
                forcar=opcoes.forcar,
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
                forcar=opcoes.forcar,
                threads=opcoes.threads,
                vad=opcoes.vad,
            ),
        ),
        _fazer(
            "energia",
            "Curva de energia do áudio",
            saida.energia_json,
            lambda: transcribe.calcular_energia(saida, estado, forcar=opcoes.forcar),
        ),
        _fazer(
            "selecao",
            f"Seleção dos clipes (modelo {opcoes.modelo})",
            saida.selecao_json,
            lambda: select.selecionar(
                saida,
                estado,
                estrategia=opcoes.estrategia,
                n=opcoes.n,
                modelo=opcoes.modelo,
                forcar=opcoes.forcar,
                resposta_manual=str(opcoes.resposta) if opcoes.resposta else None,
            ),
        ),
        _fazer(
            "render",
            f"Render dos clipes (preset {opcoes.preset})",
            saida.clips_dir,
            lambda: render.renderizar(
                saida, estado, preset=opcoes.preset, forcar=opcoes.forcar
            ),
        ),
    ]
    return {e.nome: e for e in estagios}


def _rodar_estagios(
    estagios: list[Estagio],
    medidos: dict[str, float],
    *,
    tolerar_pendentes: bool,
) -> Estagio | None:
    """Roda os estagios em ordem.

    Devolve None se todos rodaram; devolve o estagio que interrompeu quando ele
    e um estagio ainda nao implementado e o chamador aceitou parar ali
    (tolerar_pendentes=True, usado so pelo 'run').
    """
    log = registro.obter()
    for est in estagios:
        try:
            with registro.etapa(est.rotulo) as crono:
                est.executar()
            medidos[est.nome] = crono.segundos
        except (ErroSelecao, ErroRender) as exc:
            if not (tolerar_pendentes and est.pendente):
                raise
            log.info("")
            log.info(f"   {exc.mensagem}")
            if exc.sugestao:
                log.info(f"   -> {exc.sugestao}")
            return est
    return None


# --------------------------------------------------------------------------
# Relatorio na tela
# --------------------------------------------------------------------------
# Rotulos de tamanho que significam "esse artefato NAO conta como pronto".
# _descrever_artefato produz, _comando_info consome: mexeu num, mexa no outro.
_TAMANHOS_VAZIOS = ("não gerado", "vazio", "ilegível")


def _descrever_artefato(caminho: Path, base: Path) -> tuple[str, str]:
    """Devolve (nome relativo a out/<slug>/, tamanho legivel).

    Tamanho zero vira "vazio", nunca "0 B": arquivo de 0 byte e o que sobra de
    um ffmpeg que morreu no meio, e Estado.concluido() tambem o trata como nao
    concluido. Se aparecesse como "0 B" o info diria 'pronto' para um artefato
    que o resto do pipeline considera inexistente.
    """
    try:
        rel = caminho.relative_to(base).as_posix()
    except ValueError:
        rel = str(caminho)
    try:
        if caminho.is_dir():
            arquivos = [p for p in caminho.iterdir() if p.is_file()]
            if not arquivos:
                return f"{rel}/", "vazio"
            total = sum(p.stat().st_size for p in arquivos)
            rotulo = f"{rel}/ ({len(arquivos)} arq.)"
            return rotulo, (humanizar_bytes(total) if total else "vazio")
        if caminho.is_file():
            tamanho = caminho.stat().st_size
            return rel, (humanizar_bytes(tamanho) if tamanho else "vazio")
    except OSError:
        return rel, "ilegível"
    return rel, "não gerado"


def _imprimir_tabela(
    titulo: str,
    cabecalho: tuple[str, ...],
    linhas: list[tuple[str, ...]],
) -> None:
    """Tabela simples de largura fixa, com a ultima coluna alinhada a direita."""
    log = registro.obter()
    colunas = [cabecalho, *linhas]
    larguras = [max(len(l[i]) for l in colunas) for i in range(len(cabecalho))]
    ultima = len(cabecalho) - 1

    def formatar(linha: tuple[str, ...]) -> str:
        partes = [
            linha[i].rjust(larguras[i]) if i == ultima else linha[i].ljust(larguras[i])
            for i in range(len(cabecalho))
        ]
        return "  " + "  ".join(partes).rstrip()

    regua = "  " + "-" * (sum(larguras) + 2 * ultima)
    log.info("")
    log.info(titulo)
    log.info(formatar(cabecalho))
    log.info(regua)
    for linha in linhas:
        log.info(formatar(linha))
    log.info(regua)


def _resumo(
    comando: str,
    saida: Saida,
    estado: Estado,
    estagios: dict[str, Estagio],
    medidos: dict[str, float],
) -> None:
    """Tabela final: estagio | tempo | artefato principal | tamanho."""
    log = registro.obter()
    duracoes = estado.duracoes()
    # Sempre na ordem canonica do pipeline. Alem dos estagios deste subcomando,
    # entram os que o Estado ja conhece de execucoes anteriores (senao o resumo
    # de 'clipper render' fingiria que nada foi transcrito).
    ordem = list(ESTAGIOS_POR_COMANDO["run"])
    alvo = set(ESTAGIOS_POR_COMANDO.get(comando, ())) | set(duracoes)
    nomes = [n for n in ordem if n in alvo]
    nomes += [n for n in duracoes if n not in ordem]

    linhas: list[tuple[str, ...]] = []
    total = 0.0
    for nome in nomes:
        est = estagios.get(nome)
        segundos = duracoes.get(nome, medidos.get(nome))
        if segundos is not None:
            total += float(segundos)
        tempo = humanizar_tempo(segundos) if segundos is not None else "—"
        if est is None:
            linhas.append((nome, tempo, "—", "—"))
            continue
        artefato, tamanho = _descrever_artefato(est.artefato, saida.base)
        linhas.append((nome, tempo, artefato, tamanho))

    _imprimir_tabela("RESUMO", ("estágio", "tempo", "artefato", "tamanho"), linhas)
    log.info(f"  total: {humanizar_tempo(total)}")
    log.info(f"  saída: {saida.base}")
    log.info(f"  log:   {saida.log}")


def _comando_info(
    saida: Saida,
    estado: Estado,
    estagios: dict[str, Estagio],
    entrada: str,
) -> int:
    """Mostra o que ja existe em out/<slug>/ sem processar nada.

    Nao cria nada: se a pasta nem existe, diz isso em uma linha em vez de
    imprimir uma tabela inteira de 'pendente'.
    """
    log = registro.obter()
    if not saida.base.is_dir():
        log.info("")
        log.info(f"  Nada processado ainda: a pasta {saida.base} nem existe.")
        log.info(f'  Comece com:  clipper run "{entrada}"')
        return 0

    duracoes = estado.duracoes()
    linhas: list[tuple[str, ...]] = []
    prontos = 0
    for nome in ESTAGIOS_POR_COMANDO["info"]:
        est = estagios[nome]
        artefato, tamanho = _descrever_artefato(est.artefato, saida.base)
        pronto = tamanho not in _TAMANHOS_VAZIOS
        prontos += int(pronto)
        segundos = duracoes.get(nome)
        linhas.append(
            (
                nome,
                "pronto" if pronto else "pendente",
                humanizar_tempo(segundos) if segundos is not None else "—",
                artefato,
                tamanho,
            )
        )

    _imprimir_tabela(
        "ESTADO ATUAL",
        ("estágio", "situação", "tempo", "artefato", "tamanho"),
        linhas,
    )
    if prontos == 0:
        log.info(f'  Nada processado ainda. Comece com:  clipper run "{entrada}"')
    log.info(f"  saída: {saida.base}")
    return 0


# --------------------------------------------------------------------------
# Log de erro / cabecalho
# --------------------------------------------------------------------------
@contextmanager
def _somente_no_arquivo() -> Iterator[None]:
    """Silencia o console para que o traceback fique so no clipper.log."""
    log = registro.obter()
    console = next((h for h in log.handlers if h.get_name() == "console"), None)
    nivel = console.level if console is not None else None
    try:
        if console is not None:
            console.setLevel(logging.CRITICAL + 1)
        yield
    finally:
        if console is not None and nivel is not None:
            console.setLevel(nivel)


def _arquivo_de_log() -> Path | None:
    """Caminho do clipper.log, se o log em arquivo ja tiver sido configurado."""
    for h in registro.obter().handlers:
        caminho = getattr(h, "baseFilename", None)
        if caminho:
            return Path(caminho)
    return None


def _texto_origem(origem: Any, entrada: str) -> tuple[str, str]:
    """(titulo, descricao) da origem, tolerante ao formato do objeto."""
    titulo = str(getattr(origem, "titulo", "") or entrada)
    tipo = str(getattr(origem, "tipo", "") or "entrada")
    valor = str(getattr(origem, "valor", "") or entrada)
    return titulo, f"{tipo}: {valor}"


def _dispositivo() -> str:
    """Device/compute type da transcricao. Nunca derruba o cabecalho."""
    try:
        from clipper.pipeline import transcribe

        info = transcribe.detectar_dispositivo()
    except Exception:  # cabecalho e informativo: falhar aqui nao pode parar o run
        return "desconhecido"
    if isinstance(info, dict):
        return " / ".join(f"{k}={v}" for k, v in info.items())
    if isinstance(info, (tuple, list)):
        return " / ".join(str(x) for x in info if x)
    return str(info)


def _cabecalho(comando: str, entrada: str, origem: Any, saida: Saida) -> None:
    log = registro.obter()
    titulo, descricao = _texto_origem(origem, entrada)
    log.info(f"ClipPro {__version__} — clipper {comando}")
    log.info(f"  vídeo:  {titulo}")
    log.info(f"  origem: {descricao}")
    log.info(f"  slug:   {saida.slug}")
    log.info(f"  saída:  {saida.base}")
    # O 'info' nao liga o log em arquivo (nao cria nada): so cita o clipper.log
    # quando ele ja existe de uma execucao anterior.
    if saida.log.exists():
        log.info(f"  log:    {saida.log}")
    log.info(f"  device: {_dispositivo()}")


def _erro_inesperado(exc: BaseException) -> int:
    """Traceback inteiro no arquivo, tres linhas na tela."""
    log = registro.obter()
    caminho_log = _arquivo_de_log()
    with _somente_no_arquivo():
        log.exception("Erro inesperado: %s: %s", type(exc).__name__, exc)
    onde = (
        f"O traceback completo está em {caminho_log}."
        if caminho_log is not None
        else (
            "A falha ocorreu antes de a pasta de saída existir, então não há "
            "arquivo de log; rode de novo com --verboso."
        )
    )
    print(f"[ERRO INESPERADO] {type(exc).__name__}: {exc}", file=sys.stderr)
    print(f"  -> O que fazer: isso é um bug do clipper. {onde}", file=sys.stderr)
    return 2


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    comando = getattr(args, "comando", None)
    if not comando:
        parser.print_help()
        return 2

    opcoes = Opcoes.de_args(args)
    # Console primeiro (sem arquivo): erros de resolucao da origem ja aparecem.
    registro.configurar(None, verboso=opcoes.verboso)

    try:
        return _executar(comando, args.entrada, opcoes)
    except KeyboardInterrupt:
        print("Interrompido pelo usuário.", file=sys.stderr)
        return 130
    except ErroClipper as exc:
        with _somente_no_arquivo():
            registro.obter().exception("Falha em '%s': %s", exc.estagio, exc.mensagem)
        print("", file=sys.stderr)
        print(exc.formatar(), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - ultima barreira: nada de stack cru
        return _erro_inesperado(exc)


# --------------------------------------------------------------------------
# Preparo da saida e resolucao da origem
# --------------------------------------------------------------------------
def _raiz_saida(opcoes: Opcoes) -> Path:
    """Diretorio raiz de out/, ja com o padrao aplicado."""
    return Path(opcoes.out) if opcoes.out is not None else config.DIR_SAIDA_PADRAO


def _preparar_saida(slug: str, comando: str, entrada: str, opcoes: Opcoes) -> Saida:
    """Cria out/<slug>/ e subpastas.

    Um --out impossivel (drive que nao existe, caminho que ja e arquivo, pasta
    sem permissao) e erro de entrada do usuario, nao bug: vira ErroClipper com
    o comando certo, em vez de OSError cru rotulado como defeito interno.
    """
    raiz = _raiz_saida(opcoes)
    try:
        return Saida.para(slug, opcoes.out).criar_dirs()
    except OSError as exc:
        raise ErroClipper(
            f"não consegui criar a pasta de saída em {raiz / slug}.",
            detalhe=f"{type(exc).__name__}: {exc}",
            sugestao=(
                "o --out precisa ser uma PASTA, num drive que existe e onde você "
                "pode escrever. Rode sem --out para usar o padrão:  "
                f'clipper {comando} "{entrada}"   '
                f"(grava em {config.DIR_SAIDA_PADRAO})"
            ),
        ) from None


def _configurar_log(
    saida: Saida, comando: str, entrada: str, opcoes: Opcoes
) -> logging.Logger:
    """Liga o log em arquivo. Um clipper.log que nao abre tambem nao e bug."""
    try:
        return registro.configurar(saida.log, verboso=opcoes.verboso)
    except OSError as exc:
        raise ErroClipper(
            f"não consegui abrir o arquivo de log {saida.log}.",
            detalhe=f"{type(exc).__name__}: {exc}",
            sugestao=(
                "feche o programa que está com esse arquivo aberto (ou apague-o "
                f'com:  del "{saida.log}") e rode de novo:  '
                f'clipper {comando} "{entrada}"'
            ),
        ) from None


def _e_url(entrada: str) -> bool:
    """Mesma checagem do ingest, repetida aqui para nao tocar a rede sem querer."""
    return entrada.strip().lower().startswith(("http://", "https://"))


def _limpar_entrada(entrada: str) -> str:
    """Tira espacos e as aspas que o Windows cola ao arrastar um arquivo."""
    texto = entrada.strip()
    if len(texto) >= 2 and texto[0] == '"' and texto[-1] == '"':
        texto = texto[1:-1]
    return texto


def _manifesto_origem(base: Path) -> dict[str, Any]:
    """Bloco 'origem' do fonte.json de uma pasta ja processada ({} se nao der)."""
    try:
        dados = config.ler_json(Saida(slug=base.name, base=base).fonte_info_json)
    except (OSError, ValueError):
        return {}
    bloco = dados.get("origem") if isinstance(dados, dict) else None
    return bloco if isinstance(bloco, dict) else {}


def _pastas_processadas(raiz: Path) -> list[str]:
    """Nomes das pastas que ja existem em out/ (vazio se a raiz nem existe)."""
    try:
        return sorted(p.name for p in raiz.iterdir() if p.is_dir())
    except OSError:
        return []


def _achar_saida_gravada(raiz: Path, entrada: str) -> Path | None:
    """Acha em <raiz> a pasta ja processada que corresponde a 'entrada'.

    So le disco local: primeiro por nome (o proprio slug serve de entrada),
    depois lendo o fonte.json de cada pasta atras da mesma origem.
    """
    alvo = _limpar_entrada(entrada)
    if not alvo or not raiz.is_dir():
        return None

    if not _e_url(alvo):
        nomes = [config.slugificar(Path(alvo).stem or alvo)]
        if Path(alvo).name == alvo:  # entrada sem separador: pode ser o slug
            nomes.insert(0, alvo)
        for nome in nomes:
            pasta = raiz / nome
            if pasta.is_dir():
                return pasta

    alvo_cmp = alvo.casefold()
    for nome in _pastas_processadas(raiz):
        pasta = raiz / nome
        bloco = _manifesto_origem(pasta)
        valor = str(bloco.get("valor") or "")
        id_remoto = str(bloco.get("id_remoto") or "")
        if valor and valor.casefold() == alvo_cmp:
            return pasta
        if len(id_remoto) >= 6 and id_remoto.casefold() in alvo_cmp:
            return pasta
    return None


def _origem_para_info(entrada: str, raiz: Path) -> tuple[Any, str | None]:
    """Origem do 'info': sem rede e sem exigir que o arquivo ainda exista.

    Devolve (origem, aviso). Ordem de tentativa: arquivo local presente ->
    pasta ja gravada em out/ (le o fonte.json) -> consulta a URL, so como
    ultimo recurso -> slug deduzido do nome, so para dizer que nada foi feito.
    """
    from clipper.pipeline import ingest

    if not _e_url(entrada):
        try:
            return ingest.resolver_origem(entrada), None
        except ErroClipper:
            pass  # arquivo sumiu, ou a entrada e o proprio slug: segue no disco

    alvo = _limpar_entrada(entrada)
    pasta = _achar_saida_gravada(raiz, entrada)
    if pasta is not None:
        bloco = _manifesto_origem(pasta)
        origem = ingest.Origem(
            tipo=str(bloco.get("tipo") or ("url" if _e_url(entrada) else "arquivo")),
            valor=str(bloco.get("valor") or alvo),
            slug=pasta.name,
            titulo=str(bloco.get("titulo") or pasta.name),
            id_remoto=str(bloco["id_remoto"]) if bloco.get("id_remoto") else None,
        )
        if _e_url(entrada):
            aviso = f"não consultei a rede: usei o que já está gravado em {pasta}."
        elif Path(alvo).name == alvo and pasta.name in (alvo, config.slugificar(alvo)):
            aviso = (
                f"'{alvo}' não é um arquivo no disco; tratei como nome de pasta "
                f"e relato o que existe em {pasta}."
            )
        else:
            aviso = (
                f"a origem '{alvo}' não está acessível agora; abaixo está só o "
                f"que já existe em {pasta}."
            )
        return origem, aviso

    if _e_url(entrada):
        try:
            return ingest.resolver_origem(entrada), None
        except ErroClipper as exc:
            nomes = _pastas_processadas(raiz)
            exemplo = nomes[0] if nomes else "<nome-da-pasta-em-out>"
            listagem = ", ".join(nomes[:5]) if nomes else "nenhuma ainda"
            raise ErroIngestao(
                f"não achei nada processado para essa URL em {raiz} e também "
                "não consegui consultar a URL agora.",
                detalhe=f"{exc.mensagem} {exc.detalhe or ''}".strip(),
                sugestao=(
                    "se o vídeo já foi processado, chame o info pelo nome da "
                    f'pasta em vez da URL:  clipper info "{exemplo}"   '
                    f"(pastas em {raiz}: {listagem}). Se ainda não foi "
                    "processado, é preciso rede para ler o título do vídeo."
                ),
            ) from None

    origem = ingest.Origem(
        tipo="arquivo",
        valor=alvo,
        slug=config.slugificar(Path(alvo).stem or alvo),
        titulo=Path(alvo).stem or alvo,
        id_remoto=None,
    )
    aviso = (
        f"não encontrei '{alvo}' no disco nem uma pasta correspondente em "
        f"{raiz}; mostro o estado do slug deduzido do nome do arquivo."
    )
    return origem, aviso


def _executar(comando: str, entrada: str, opcoes: Opcoes) -> int:
    """Corpo do comando. Erros sobem para o main, que sabe formatar."""
    from clipper.pipeline import ingest

    # 'info' nao processa nada: nao toca a rede, nao exige que a origem ainda
    # exista e NAO cria out/<slug>/ (nem clips/, _trabalho/, clipper.log) so
    # para depois relatar que nao ha nada la.
    if comando == "info":
        raiz = _raiz_saida(opcoes)
        origem, aviso = _origem_para_info(entrada, raiz)
        saida = Saida.para(origem.slug, opcoes.out)
        estado = Estado(saida.estado_json)
        _cabecalho(comando, entrada, origem, saida)
        if aviso:
            registro.obter().info(f"  aviso:  {aviso}")
        estagios = _montar_estagios(opcoes, origem, saida, estado)
        return _comando_info(saida, estado, estagios, entrada)

    origem = ingest.resolver_origem(entrada)
    saida = _preparar_saida(origem.slug, comando, entrada, opcoes)
    estado = Estado(saida.estado_json)

    log = _configurar_log(saida, comando, entrada, opcoes)
    _cabecalho(comando, entrada, origem, saida)

    estagios = _montar_estagios(opcoes, origem, saida, estado)
    alvos = ESTAGIOS_POR_COMANDO[comando]

    if comando == "select" and opcoes.resposta is not None:
        _conferir_resposta_manual(opcoes.resposta)
    if comando == "render":
        _conferir_selecao_pronta(saida, entrada)

    # A limpeza vem DEPOIS das checagens (comando que aborta nao pode destruir
    # estado) e alcanca SO os estagios deste subcomando: o que estiver a jusante
    # se invalida sozinho pela assinatura (audio novo derruba transcricao e
    # energia), sem o CLI apagar registro de estagio que ele nem vai refazer.
    if opcoes.forcar:
        estado.limpar(alvos)
        recado = "  --force: vou refazer do zero " + ", ".join(alvos) + "."
        if set(alvos) != set(ESTAGIOS_POR_COMANDO["run"]):
            recado += " Os demais estágios mantêm o que já foi feito."
        log.info(recado)

    medidos: dict[str, float] = {}
    escolhidos = [estagios[n] for n in alvos]
    parou_em = _rodar_estagios(
        escolhidos, medidos, tolerar_pendentes=(comando == "run")
    )

    if parou_em is not None:
        log.info("")
        log.info(
            "Pipeline concluído até onde esta versão do clipper vai hoje: o "
            f"estágio '{parou_em.nome}' ainda não existe. Isso não é erro seu."
        )
        log.info("Artefatos já produzidos:")
    _resumo(comando, saida, estado, estagios, medidos)
    if parou_em is None:
        log.info("")
        log.info("Pronto.")
    return 0


def _conferir_resposta_manual(caminho: Path) -> None:
    if not caminho.is_file() or caminho.stat().st_size == 0:
        raise ErroSelecao(
            f"o arquivo de resposta manual '{caminho}' não existe ou está vazio.",
            sugestao=(
                "confira o caminho; ele deve apontar para o .json com a resposta "
                "do modelo colada à mão. Sem --resposta, o clipper chama a API "
                "sozinho."
            ),
        )


def _conferir_selecao_pronta(saida: Saida, entrada: str) -> None:
    alvo = saida.selecao_json
    if not alvo.is_file() or alvo.stat().st_size == 0:
        raise ErroRender(
            f"não encontrei uma seleção pronta em {alvo}.",
            sugestao=(
                "gere a seleção antes de renderizar:  "
                f'clipper select "{entrada}"   (ou rode tudo de uma vez com '
                f'clipper run "{entrada}")'
            ),
        )
