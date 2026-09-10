"""Descoberta e execucao de ffmpeg/ffprobe + escape de filtergraph no Windows.

O ponto sensivel deste arquivo e `escapar_filtro`: o valor de uma opcao de
filtro do ffmpeg passa por tres parsers (filtergraph -> filtro -> libavutil),
e no Windows o caminho traz "C:\\" com dois-pontos e contrabarra, que sao
metacaracteres nos tres. A estrategia primaria e nem passar por isso:
rodamos o ffmpeg com cwd na pasta do arquivo e referenciamos so o nome.
`escapar_filtro` fica como caminho alternativo quando isso nao for possivel.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from clipper.erros import ErroDependencia, ErroFFmpeg

# Locais onde winget/scoop/chocolatey costumam deixar o ffmpeg no Windows.
_PADROES_WINDOWS = (
    "%LOCALAPPDATA%\\Microsoft\\WinGet\\Packages",
    "%LOCALAPPDATA%\\Microsoft\\WinGet\\Links",
    "%USERPROFILE%\\scoop\\shims",
    "C:\\ProgramData\\chocolatey\\bin",
    "C:\\ffmpeg\\bin",
)


@lru_cache(maxsize=8)
def binario(nome: str) -> str:
    """Devolve o caminho absoluto de ffmpeg/ffprobe ou explica como instalar."""
    env = os.environ.get("CLIPPER_" + nome.upper())
    if env and Path(env).exists():
        return str(Path(env).resolve())

    achado = shutil.which(nome)
    if achado:
        return str(Path(achado).resolve())

    exe = nome + ".exe" if os.name == "nt" else nome
    for padrao in _PADROES_WINDOWS:
        raiz = Path(os.path.expandvars(padrao))
        if "%" in str(raiz) or not raiz.exists():
            continue
        try:
            for candidato in raiz.rglob(exe):
                if candidato.is_file():
                    return str(candidato.resolve())
        except OSError:
            continue

    raise ErroDependencia(
        "nao encontrei o executavel '" + nome + "' nesta maquina.",
        sugestao=(
            "instale com  winget install --id Gyan.FFmpeg --exact --scope user  "
            "e abra um terminal novo; ou aponte direto com a variavel de ambiente "
            "CLIPPER_" + nome.upper() + "=C:\\caminho\\para\\" + exe
        ),
    )


def ffmpeg() -> str:
    return binario("ffmpeg")


def ffprobe() -> str:
    return binario("ffprobe")


@dataclass(frozen=True)
class InfoMidia:
    caminho: Path
    duracao: float
    largura: int
    altura: int
    fps: float
    tem_audio: bool
    codec_video: str
    codec_audio: str
    taxa_amostragem: int
    canais: int

    @property
    def tem_video(self) -> bool:
        return self.largura > 0 and self.altura > 0


def _fracao(texto: str) -> float:
    """Converte '30000/1001' (formato de fps do ffprobe) em float."""
    try:
        if "/" in str(texto):
            num, den = str(texto).split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else 0.0
        return float(texto)
    except (ValueError, ZeroDivisionError):
        return 0.0


def sondar(caminho: Path) -> InfoMidia:
    """Le metadados com ffprobe. Erro aqui significa arquivo invalido/corrompido."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroFFmpeg(
            "arquivo nao existe: " + str(caminho),
            sugestao="confira o caminho passado para o clipper.",
        )

    cmd = [
        ffprobe(), "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(caminho),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise ErroFFmpeg(
            "o ffprobe nao conseguiu ler '" + caminho.name + "'.",
            detalhe=proc.stderr,
            sugestao=(
                "o arquivo pode estar corrompido, incompleto ou nao ser um video. "
                "Tente abri-lo num player para confirmar."
            ),
        )

    try:
        dados = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ErroFFmpeg(
            "resposta do ffprobe ilegivel para '" + caminho.name + "'.",
            detalhe=str(exc),
            sugestao="reinstale o ffmpeg (winget install --id Gyan.FFmpeg --exact).",
        ) from None

    fluxos = dados.get("streams", [])
    v = next((s for s in fluxos if s.get("codec_type") == "video"), {})
    a = next((s for s in fluxos if s.get("codec_type") == "audio"), {})

    duracao = 0.0
    candidatos = (
        dados.get("format", {}).get("duration"),
        v.get("duration"),
        a.get("duration"),
    )
    for fonte in candidatos:
        try:
            duracao = float(fonte)
        except (TypeError, ValueError):
            continue
        if duracao > 0:
            break

    return InfoMidia(
        caminho=caminho,
        duracao=duracao,
        largura=int(v.get("width") or 0),
        altura=int(v.get("height") or 0),
        fps=_fracao(v.get("avg_frame_rate") or v.get("r_frame_rate") or "0"),
        tem_audio=bool(a),
        codec_video=str(v.get("codec_name") or ""),
        codec_audio=str(a.get("codec_name") or ""),
        taxa_amostragem=int(a.get("sample_rate") or 0),
        canais=int(a.get("channels") or 0),
    )


def rodar(
    args: Sequence[str],
    *,
    descricao: str,
    cwd: Path | None = None,
    sugestao: str | None = None,
    timeout: float | None = None,
) -> str:
    """Executa ffmpeg. Em falha levanta ErroFFmpeg com a saida real, sem stack cru."""
    cmd = [ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    cmd.extend(str(a) for a in args)
    log_cmd = " ".join(cmd)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ErroFFmpeg(
            descricao + ": o ffmpeg estourou o tempo limite e foi interrompido.",
            sugestao=sugestao
            or "tente um trecho menor ou verifique se o arquivo esta integro.",
        ) from None
    except OSError as exc:
        raise ErroFFmpeg(
            descricao + ": nao consegui executar o ffmpeg.",
            detalhe=str(exc) + "\ncomando: " + log_cmd,
            sugestao="confirme a instalacao com  ffmpeg -version.",
        ) from None

    if proc.returncode != 0:
        raise ErroFFmpeg(
            descricao + ": o ffmpeg saiu com codigo " + str(proc.returncode) + ".",
            detalhe=proc.stderr + "\n\ncomando: " + log_cmd,
            sugestao=sugestao
            or "leia a saida acima: ela costuma dizer exatamente o que faltou.",
        )
    return proc.stderr


def escapar_filtro(caminho: Path | str) -> str:
    """Escapa um caminho para virar valor de opcao dentro de um filtergraph.

    Regra que funciona no Windows: barras normais + dois-pontos escapado; o
    chamador ainda precisa envolver o resultado em aspas simples.
    Exemplo: C:\\Videos\\Meu Clipe\\leg.ass  ->  C\\:/Videos/Meu Clipe/leg.ass
    Prefira `opcao_subtitles()` a montar isso na mao.
    """
    texto = str(caminho).replace("\\", "/")
    texto = texto.replace("'", "\\'")
    texto = texto.replace(":", "\\:")
    return texto


def opcao_subtitles(arquivo_ass: Path, *, forcar_absoluto: bool = False) -> tuple[str, Path]:
    """Monta o filtro `subtitles=` e o cwd em que o ffmpeg deve rodar.

    Estrategia primaria (forcar_absoluto=False): devolve o filtro com apenas o
    NOME do arquivo e o diretorio dele como cwd. Sem drive, sem dois-pontos,
    sem espaco -> nada para o parser do ffmpeg estragar, mesmo que a pasta se
    chame "Meu Video 2026".
    Estrategia alternativa (forcar_absoluto=True): caminho absoluto escapado,
    usada nos testes para provar que o escape tambem funciona.
    """
    arquivo_ass = Path(arquivo_ass).resolve()
    if forcar_absoluto:
        return "subtitles=filename='" + escapar_filtro(arquivo_ass) + "'", Path.cwd()
    return "subtitles=filename='" + arquivo_ass.name + "'", arquivo_ass.parent
