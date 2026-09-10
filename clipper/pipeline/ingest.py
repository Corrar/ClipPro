"""Estagio 1: ingestao.

Pega uma origem (arquivo local ou URL de video PROPRIO do usuario) e produz
dois artefatos canonicos que todos os estagios seguintes consomem:

  out/<slug>/fonte.mp4  -> h264 + aac, faststart (base de todo corte/render)
  out/<slug>/audio.wav  -> pcm_s16le 16 kHz mono (entrada do faster-whisper)

mais o manifesto out/<slug>/fonte.json descrevendo o que entrou e como foi
normalizado.

Duas decisoes que valem explicar:

1. Caminho rapido de remux. Se o arquivo ja e mp4 h264+aac, copiar os
   streams (-c copy) leva segundos em vez de dezenas de minutos de reencode.
   Se o remux falhar por qualquer motivo (moov quebrado, stream exotico), o
   modulo cai sozinho no reencode completo em vez de estourar na cara do
   usuario.
2. O bruto baixado fica em _trabalho. Nada e apagado sem aviso; o tamanho vai
   para o log para o usuario decidir se quer limpar.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clipper import ffmpeg_utils, registro
from clipper.config import (
    Estado,
    Saida,
    escrever_json,
    humanizar_bytes,
    humanizar_tempo,
    slugificar,
)
from clipper.erros import ErroClipper, ErroIngestao
from clipper.ffmpeg_utils import InfoMidia, ffmpeg
from clipper.registro import Cronometro

ESTAGIO = "ingestao"

# Containers em que o remux direto costuma funcionar sem dor de cabeca.
_EXT_REMUXAVEIS = {".mp4", ".m4v", ".mov"}

# Sobras que o yt-dlp deixa no meio do caminho e que NAO sao o video pronto.
_SUFIXOS_PARCIAIS = {".part", ".ytdl", ".temp", ".tmp"}

# Containers de audio puro: mesmo trazendo capa embutida, nao sao video.
_EXT_AUDIO = {
    ".mp3", ".m4a", ".m4b", ".aac", ".wav", ".ogg", ".oga", ".opus",
    ".flac", ".wma", ".aiff", ".aif", ".mka", ".ac3", ".dts", ".amr",
}

# Codecs de imagem parada: capa de album aparece no ffprobe como um destes.
_CODECS_IMAGEM = {"mjpeg", "png", "bmp", "gif", "webp", "jpeg", "tiff", "ppm"}

_PREFIXO_BAIXADO = "baixado"


@dataclass(frozen=True)
class Origem:
    """De onde o video vem, ja resolvido e sem ambiguidade."""

    tipo: str  # "arquivo" ou "url"
    valor: str  # caminho absoluto resolvido, ou a URL
    slug: str
    titulo: str
    id_remoto: str | None = None


# ---------------------------------------------------------------- resolucao


def _limpar_entrada(entrada: str) -> str:
    """Tira espacos das pontas e as aspas que o Windows agrega ao arrastar."""
    texto = entrada.strip()
    # Windows: arrastar um arquivo para o terminal costuma trazer aspas junto.
    if len(texto) >= 2 and texto[0] == '"' and texto[-1] == '"':
        texto = texto[1:-1]
    return texto


def _como_caminho(entrada: str) -> Path | None:
    """Devolve o caminho resolvido se 'entrada' aponta para um arquivo real."""
    texto = _limpar_entrada(entrada)
    if not texto:
        return None
    try:
        caminho = Path(texto)
        if caminho.is_file():
            return caminho.resolve()
    except (OSError, ValueError):
        return None
    return None


def _e_url(entrada: str) -> bool:
    return entrada.strip().lower().startswith(("http://", "https://"))


def _importar_yt_dlp() -> Any:
    try:
        import yt_dlp  # noqa: PLC0415  (import tardio: so quem usa URL paga o custo)
    except ImportError as exc:
        raise ErroIngestao(
            "o yt-dlp não está disponível neste ambiente, então não dá para "
            "tratar uma URL.",
            detalhe=str(exc),
            sugestao=(
                "instale com  .venv\\Scripts\\python.exe -m pip install yt-dlp  "
                "ou baixe o vídeo você mesmo e passe o caminho do arquivo local."
            ),
        ) from None
    return yt_dlp


def _sugestao_url() -> str:
    return (
        "baixe o vídeo manualmente e passe o caminho do arquivo local para o "
        "clipper; e confira se o vídeo é público (ou se é mesmo seu e você está "
        "logado na conta certa)."
    )


def resolver_origem(entrada: str) -> Origem:
    """Descobre se 'entrada' e um arquivo local ou uma URL, e monta o slug.

    Arquivo local nao toca a rede: titulo = nome do arquivo sem extensao.
    URL consulta o yt-dlp apenas para ler titulo e id (skip_download=True),
    e o slug vira "<titulo>-<id[:8]>" para que dois videos de mesmo nome nao
    briguem pela mesma pasta em out/.

    IMPORTANTE: o suporte a URL existe para o usuario processar VIDEO PROPRIO
    (o canal dele, a live dele, a gravacao dele). Nao use para baixar conteudo
    de terceiros sem autorizacao.
    """
    caminho = _como_caminho(entrada)
    if caminho is not None:
        titulo = caminho.stem
        return Origem(
            tipo="arquivo",
            valor=str(caminho),
            slug=slugificar(titulo),
            titulo=titulo,
            id_remoto=None,
        )

    if _e_url(entrada):
        return _resolver_url(entrada.strip())

    # Caso classico: o usuario arrastou a PASTA do video em vez do video.
    # Dizer "nao existe" para algo que existe manda o usuario procurar no lugar
    # errado, entao o diretorio ganha mensagem propria.
    alvo = _limpar_entrada(entrada)
    if alvo:
        try:
            pasta = Path(alvo)
            e_pasta = pasta.is_dir()
        except (OSError, ValueError):
            pasta, e_pasta = None, False
        if e_pasta and pasta is not None:
            exemplo = pasta / "aula.mp4"
            raise ErroIngestao(
                f"'{pasta}' é uma pasta, não um arquivo de vídeo.",
                sugestao=(
                    "aponte para o arquivo em si, ex.: "
                    f'clipper ingest "{exemplo}"  '
                    "(o clipper processa um vídeo por vez)."
                ),
            )

    raise ErroIngestao(
        f"não encontrei nada em '{entrada}': não é um caminho existente no "
        "disco e também não parece uma URL.",
        sugestao=(
            "passe o caminho absoluto do arquivo (ex.: "
            'clipper ingest "C:\\Users\\voce\\Videos\\live.mp4") '
            "ou uma URL começando com http:// ou https://."
        ),
    )


def _resolver_url(url: str) -> Origem:
    """Le titulo/id da URL com o yt-dlp, sem baixar nada."""
    yt_dlp = _importar_yt_dlp()
    opcoes = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # DownloadError, ExtractorError, rede fora, etc.
        raise ErroIngestao(
            "o yt-dlp não conseguiu ler os dados dessa URL.",
            detalhe=f"{type(exc).__name__}: {exc}",
            sugestao=_sugestao_url(),
        ) from None

    if not isinstance(info, dict):
        raise ErroIngestao(
            "o yt-dlp respondeu, mas não trouxe informações sobre essa URL.",
            sugestao=_sugestao_url(),
        )
    # Defesa extra: se ainda assim vier uma playlist, fica com o primeiro item.
    entradas = info.get("entries")
    if entradas:
        primeiro = next((e for e in entradas if isinstance(e, dict)), None)
        if primeiro is None:
            raise ErroIngestao(
                "essa URL aponta para uma playlist vazia (ou sem vídeos acessíveis).",
                sugestao="passe a URL de um vídeo específico, não a da playlist.",
            )
        info = primeiro

    titulo = str(info.get("title") or info.get("id") or "video")
    id_remoto = info.get("id")
    id_remoto = str(id_remoto) if id_remoto else None

    slug = slugificar(titulo)
    if id_remoto:
        slug = f"{slug}-{id_remoto[:8]}"

    return Origem(
        tipo="url",
        valor=url,
        slug=slug,
        titulo=titulo,
        id_remoto=id_remoto,
    )


# ------------------------------------------------------------------ download


def _achar_baixado(trabalho_dir: Path) -> Path | None:
    """Procura o 'baixado.*' pronto em _trabalho, ignorando restos parciais."""
    candidatos = [
        p
        for p in trabalho_dir.glob(_PREFIXO_BAIXADO + ".*")
        if p.is_file()
        and p.stat().st_size > 0
        and p.suffix.lower() not in _SUFIXOS_PARCIAIS
    ]
    if not candidatos:
        return None
    # mp4 primeiro (e o resultado do merge); em empate, o maior arquivo.
    candidatos.sort(key=lambda p: (p.suffix.lower() != ".mp4", -p.stat().st_size))
    return candidatos[0]


def _hook_progresso(log: Any) -> Any:
    """Hook do yt-dlp que loga o download a cada ~5%, com ETA."""
    ultimo = {"pct": -10.0}

    def hook(d: dict[str, Any]) -> None:
        try:
            estado_hook = d.get("status")
            if estado_hook == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                baixado = d.get("downloaded_bytes") or 0
                if not total:
                    return
                pct = 100.0 * float(baixado) / float(total)
                if pct - ultimo["pct"] < 5.0:
                    return
                ultimo["pct"] = pct
                eta = d.get("eta")
                falta = f" — faltam ~{humanizar_tempo(eta)}" if eta else ""
                log.info(
                    f"   download: {pct:5.1f}% de {humanizar_bytes(total)}{falta}"
                )
            elif estado_hook == "finished":
                ultimo["pct"] = -10.0
                log.info("   download da faixa concluído; juntando/convertendo…")
        except Exception:  # hook nunca pode derrubar o download
            return

    return hook


def _apagar_baixados(trabalho_dir: Path, log: Any) -> None:
    """Remove 'baixado.*' (pronto ou parcial) antes de um download forcado."""
    presos: list[Path] = []
    apagados: list[str] = []
    for p in sorted(trabalho_dir.glob(_PREFIXO_BAIXADO + ".*")):
        nome = p.name
        try:
            p.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            presos.append(p)
        else:
            apagados.append(nome)
    # O modulo nao apaga nada em silencio: com --force o usuario ve o que saiu.
    if apagados:
        log.info(f"   --force: apaguei o download anterior ({', '.join(apagados)})")
    if presos:
        nomes = ", ".join(p.name for p in presos)
        log.warning(
            f"   não consegui apagar {nomes} (arquivo em uso?); vou pedir ao "
            "yt-dlp para sobrescrever mesmo assim."
        )


def _formato_ytdl(altura_max: int | None) -> str:
    """Seletor de formato do yt-dlp, preferindo h264 ate a altura pedida.

    Por que limitar a altura: o YouTube so entrega H.264 ate 1080p; acima disso
    e VP9/AV1, o que obriga a ingestao a REENCODAR o video inteiro na CPU.
    Num video de 29 min em 4K60 isso passa de duas horas nesta maquina, contra
    segundos de remux quando o bruto ja e h264+aac. Como o clipe final e
    1080x1920, 1080p de origem e o ponto de equilibrio. Quem quiser mais
    qualidade no reenquadramento passa --altura-max maior e paga o reencode.
    """
    if not altura_max or altura_max <= 0:
        return "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"
    h = int(altura_max)
    return (
        f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/"
        f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/"
        f"bv*[height<={h}]+ba/"
        f"b[height<={h}]/"
        "bv*+ba/b"
    )


def _baixar(
    origem: Origem, saida: Saida, *, forcar: bool, altura_max: int | None = None
) -> Path:
    """Baixa a URL para _trabalho/baixado.<ext> e devolve o arquivo bruto."""
    log = registro.obter()
    existente = _achar_baixado(saida.trabalho_dir)
    if existente is not None and not forcar:
        log.info(
            f"   download reaproveitado: {existente.name} "
            f"({humanizar_bytes(existente.stat().st_size)})"
        )
        return existente

    yt_dlp = _importar_yt_dlp()
    opcoes = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": str(saida.trabalho_dir / (_PREFIXO_BAIXADO + ".%(ext)s")),
        "format": _formato_ytdl(altura_max),
        "merge_output_format": "mp4",
        "progress_hooks": [_hook_progresso(log)],
        # Sem isto o yt-dlp procura o ffmpeg SO no PATH. No Windows, logo apos
        # 'winget install Gyan.FFmpeg' o PATH do shell atual ainda nao tem o
        # binario, e o yt-dlp entao baixa video e audio em arquivos separados,
        # avisa "ffmpeg is not installed" e NAO faz o merge -- sobra um
        # baixado.fNNN.mp4 sem trilha de audio. Apontamos para o ffmpeg que o
        # proprio clipper ja sabe localizar.
        "ffmpeg_location": str(Path(ffmpeg()).parent),
    }
    if forcar:
        # Sem 'overwrites' o yt-dlp ve o baixado.* existente, diz "has already
        # been downloaded" e nao baixa nada -- o --force viraria mentira e o
        # arquivo truncado seria reaproveitado. Os restos vao junto (inclusive
        # .part/.ytdl) para o merge nao retomar de lixo antigo.
        opcoes["overwrites"] = True
        _apagar_baixados(saida.trabalho_dir, log)
    log.info("   baixando o vídeo com o yt-dlp…")
    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            ydl.download([origem.valor])
    except Exception as exc:
        raise ErroIngestao(
            "o download do vídeo falhou.",
            detalhe=f"{type(exc).__name__}: {exc}",
            sugestao=_sugestao_url(),
        ) from None

    bruto = _achar_baixado(saida.trabalho_dir)
    if bruto is None:
        raise ErroIngestao(
            "o yt-dlp terminou sem erro, mas não sobrou nenhum arquivo "
            f"'{_PREFIXO_BAIXADO}.*' em {saida.trabalho_dir}.",
            sugestao=(
                "rode  clipper ingest "
                f'"{origem.valor}" --force  '
                "(isso apaga o que sobrou e baixa de novo); se persistir, baixe "
                "o vídeo manualmente e passe o caminho do arquivo local."
            ),
        )
    return bruto


# --------------------------------------------------------------- normalizacao


def _obter_bruto(
    origem: Origem, saida: Saida, *, forcar: bool, altura_max: int | None = None
) -> Path:
    if origem.tipo == "arquivo":
        bruto = Path(origem.valor)
        if not bruto.is_file():
            raise ErroIngestao(
                f"o arquivo '{bruto}' sumiu entre a resolução da origem e a ingestão.",
                sugestao="confira se o arquivo ainda existe (ou se o pendrive/rede caiu).",
            )
        return bruto
    if origem.tipo == "url":
        return _baixar(origem, saida, forcar=forcar, altura_max=altura_max)
    raise ErroIngestao(
        f"tipo de origem desconhecido: '{origem.tipo}'.",
        sugestao="use resolver_origem() para montar a origem em vez de criá-la na mão.",
    )


def _todo_video_e_capa(bruto: Path) -> bool | None:
    """Pergunta ao ffprobe se TODO stream de video e capa embutida.

    Devolve None quando nao deu para saber (ffprobe fora do ar, saida
    ilegivel), para o chamador decidir com o que tem em maos.
    """
    try:
        proc = subprocess.run(
            [
                ffmpeg_utils.ffprobe(), "-v", "error",
                "-select_streams", "v",
                "-show_entries", "stream=index:stream_disposition=attached_pic",
                "-print_format", "json",
                str(bruto),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError, ErroClipper):
        return None
    if proc.returncode != 0:
        return None
    try:
        fluxos = json.loads(proc.stdout).get("streams") or []
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None
    if not fluxos:
        return None
    marcados = []
    for fluxo in fluxos:
        disp = fluxo.get("disposition") or {}
        try:
            marcados.append(int(disp.get("attached_pic") or 0) == 1)
        except (TypeError, ValueError):
            return None
    return all(marcados)


def _so_tem_capa(bruto: Path, info: InfoMidia) -> bool:
    """True quando o unico 'video' do arquivo e a capa de album embutida.

    info.tem_video olha apenas largura/altura, e uma capa tem largura e altura
    de verdade: sem esta checagem um mp3 com capa passa pela validacao e vai
    morrer la na frente no reencode, com uma mensagem de codec que nao tem
    nada a ver com a causa real.
    """
    if not info.tem_video:
        return False
    if bruto.suffix.lower() in _EXT_AUDIO:
        return True
    resposta = _todo_video_e_capa(bruto)
    if resposta is not None:
        return resposta
    # Sem resposta do ffprobe: imagem parada sem taxa de quadros nao e video.
    return info.codec_video in _CODECS_IMAGEM and info.fps <= 0.0


def _validar_bruto(bruto: Path, info: InfoMidia) -> None:
    sugestao_sem_video = (
        "o clipper corta vídeo, não áudio puro. Passe o arquivo de vídeo "
        "original (mp4/mkv/mov) em vez do mp3/m4a."
    )
    if _so_tem_capa(bruto, info):
        raise ErroIngestao(
            f"o arquivo '{bruto.name}' é áudio: a única imagem dentro dele é a "
            "capa embutida, não uma trilha de vídeo.",
            sugestao=sugestao_sem_video,
        )
    if not info.tem_video:
        raise ErroIngestao(
            f"o arquivo '{bruto.name}' não tem trilha de vídeo.",
            sugestao=sugestao_sem_video,
        )
    if not info.tem_audio:
        raise ErroIngestao(
            f"o arquivo '{bruto.name}' está sem trilha de áudio: não dá para transcrever.",
            sugestao=(
                "verifique o arquivo num player — se o áudio estiver mudo ou tiver "
                "sido removido na exportação, exporte de novo com a trilha de áudio."
            ),
        )


def _normalizar(
    bruto: Path,
    info: InfoMidia,
    destino: Path,
    *,
    reencodar: bool,
) -> tuple[bool, str]:
    """Gera fonte.mp4. Devolve (reencodado, motivo)."""
    log = registro.obter()
    ja_compativel = (
        bruto.suffix.lower() in _EXT_REMUXAVEIS
        and info.codec_video == "h264"
        and info.codec_audio == "aac"
    )

    if not reencodar and ja_compativel:
        log.info("   normalização: remux (o bruto já era h264+aac) — rápido")
        try:
            ffmpeg_utils.rodar(
                [
                    "-i", str(bruto),
                    "-map", "0:v:0",
                    "-map", "0:a:0",
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(destino),
                ],
                descricao="remux do vídeo de origem para fonte.mp4",
            )
            return False, "remux (ja era h264+aac)"
        except Exception as exc:
            motivo = exc.mensagem if isinstance(exc, ErroClipper) else str(exc)
            log.warning(
                f"   o remux não funcionou ({motivo}); refazendo com reencode completo."
            )
            try:
                destino.unlink()
            except OSError:
                pass

    log.info("   normalização: reencode para h264+aac (pode demorar)")
    ffmpeg_utils.rodar(
        [
            "-i", str(bruto),
            "-map", "0:v:0",
            "-map", "0:a:0",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-profile:v", "high",
            "-c:a", "aac",
            "-b:a", "160k",
            "-ac", "2",
            "-movflags", "+faststart",
            str(destino),
        ],
        descricao="reencode do vídeo de origem para fonte.mp4 (h264+aac)",
        sugestao=(
            "leia a saída acima: costuma ser arquivo corrompido, codec exótico "
            "ou disco cheio. Se o vídeo abre num player, tente convertê-lo "
            "manualmente com  ffmpeg -i entrada -c:v libx264 -c:a aac saida.mp4"
        ),
    )
    return True, "reencode para h264+aac"


def _extrair_audio(fonte_mp4: Path, destino: Path) -> None:
    ffmpeg_utils.rodar(
        [
            "-i", str(fonte_mp4),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(destino),
        ],
        descricao="extração do áudio para audio.wav (16 kHz mono)",
        sugestao=(
            "confira se sobrou espaço em disco: 1 hora de wav 16 kHz mono ocupa "
            "cerca de 110 MB."
        ),
    )


def _arredondar(valor: float | int | None, casas: int = 3) -> float:
    try:
        return round(float(valor or 0.0), casas)
    except (TypeError, ValueError):
        return 0.0


# -------------------------------------------------------------------- estagio


def ingerir(
    origem: Origem,
    saida: Saida,
    estado: Estado,
    *,
    forcar: bool = False,
    reencodar: bool = False,
    altura_max: int | None = None,
) -> dict[str, Any]:
    """Normaliza a origem em fonte.mp4 + audio.wav e grava fonte.json.

    Idempotente: se o estado registra a mesma assinatura e os tres artefatos
    existem, nao refaz nada e devolve o resultado guardado. Use forcar=True
    (ou --force no cli) para refazer do zero.
    """
    log = registro.obter()
    saida.criar_dirs()

    assinatura: dict[str, Any] = {
        "origem": origem.valor,
        "tipo": origem.tipo,
        "reencodar": reencodar,
    }
    if origem.tipo == "url":
        # A altura pedida muda QUAL arquivo o yt-dlp baixa, entao muda o
        # resultado: precisa entrar na assinatura para que --altura-max
        # diferente reprocesse em vez de reaproveitar o download antigo.
        assinatura["altura_max"] = altura_max
    if origem.tipo == "arquivo":
        # Caminho igual nao quer dizer conteudo igual: quem reexporta o video
        # por cima do mesmo nome precisa ver a ingestao rodar de novo, senao o
        # pipeline inteiro segue com o fonte.mp4 antigo com cara de sucesso.
        # Como audio.wav muda junto, transcricao e energia (que assinam bytes e
        # mtime dele) se invalidam em cascata sozinhas.
        try:
            st = Path(origem.valor).stat()
            assinatura["bytes"] = st.st_size
            assinatura["mtime"] = int(st.st_mtime)
        except OSError:
            pass
    artefatos = [saida.fonte_mp4, saida.audio_wav, saida.fonte_info_json]

    if not forcar and estado.concluido(ESTAGIO, assinatura, artefatos):
        log.info("ingestao: reaproveitando artefatos existentes (use --force para refazer)")
        return {**estado.extra(ESTAGIO), "reaproveitado": True}

    with Cronometro(ESTAGIO) as crono:
        log.info(f"   origem: {origem.tipo} — {origem.titulo}")
        log.info(f"   valor: {origem.valor}")

        bruto = _obter_bruto(origem, saida, forcar=forcar, altura_max=altura_max)
        try:
            tamanho_bruto = bruto.stat().st_size
        except OSError:
            tamanho_bruto = 0
        log.info(f"   bruto: {bruto.name} ({humanizar_bytes(tamanho_bruto)})")

        info_bruto = ffmpeg_utils.sondar(bruto)
        _validar_bruto(bruto, info_bruto)

        reencodado, motivo = _normalizar(
            bruto, info_bruto, saida.fonte_mp4, reencodar=reencodar
        )
        _extrair_audio(saida.fonte_mp4, saida.audio_wav)

        info_video = ffmpeg_utils.sondar(saida.fonte_mp4)
        info_audio = ffmpeg_utils.sondar(saida.audio_wav)

        dados: dict[str, Any] = {
            "origem": {
                "tipo": origem.tipo,
                "valor": origem.valor,
                "titulo": origem.titulo,
                "id_remoto": origem.id_remoto,
            },
            "normalizado": {"reencodado": reencodado, "motivo": motivo},
            "midia": {
                "duracao": _arredondar(info_video.duracao),
                "largura": int(info_video.largura),
                "altura": int(info_video.altura),
                "fps": _arredondar(info_video.fps),
                "codec_video": info_video.codec_video,
                "codec_audio": info_video.codec_audio,
                "tem_audio": bool(info_video.tem_audio),
                "taxa_amostragem": int(info_video.taxa_amostragem),
                "canais": int(info_video.canais),
            },
            "audio": {
                "taxa_amostragem": int(info_audio.taxa_amostragem),
                "canais": int(info_audio.canais),
                "duracao": _arredondar(info_audio.duracao),
            },
            "tamanhos_bytes": {
                "fonte_mp4": saida.fonte_mp4.stat().st_size,
                "audio_wav": saida.audio_wav.stat().st_size,
            },
        }
        escrever_json(saida.fonte_info_json, dados)

        dados["fonte_mp4"] = str(saida.fonte_mp4)
        dados["audio_wav"] = str(saida.audio_wav)

        log.info(
            "   fonte.mp4: "
            f"{humanizar_bytes(dados['tamanhos_bytes']['fonte_mp4'])} — "
            f"{info_video.largura}x{info_video.altura} @ {info_video.fps:.2f} fps, "
            f"{info_video.codec_video}+{info_video.codec_audio}"
        )
        log.info(
            "   audio.wav: "
            f"{humanizar_bytes(dados['tamanhos_bytes']['audio_wav'])} — "
            f"{info_audio.taxa_amostragem} Hz, {info_audio.canais} canal(is)"
        )
        log.info(f"   duração: {humanizar_tempo(info_video.duracao)}")

        # Nada e apagado sem aviso: o bruto baixado fica, mas o usuario sabe o custo.
        if origem.tipo == "url" and tamanho_bruto:
            log.info(
                f"   o bruto baixado continua em {bruto} "
                f"({humanizar_bytes(tamanho_bruto)}); apague se precisar de espaço."
            )

    estado.marcar(ESTAGIO, assinatura, segundos=crono.segundos, extra=dados)
    return {**dados, "reaproveitado": False}
