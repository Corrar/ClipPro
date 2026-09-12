"""Gera _teste/clipe-curto.mp4 com fontes lavfi -- sem baixar nada da rede.

Por que existe: a suite p1..p9 (ui/provas/casos.py:35) exige
RAIZ/_teste/clipe-curto.mp4, e _teste/ esta no .gitignore. Em clone limpo a
suite inteira falha por falta de arquivo, nao por defeito de codigo. Este
gerador fecha esse buraco sem versionar binario: o video e SINTETIZADO na
maquina que for rodar a prova.

O que o clipe tem, e por que:
  - 1280x720, paisagem. A fonte real do pipeline e um video horizontal que o
    render reenquadra para 9:16; gerar ja em vertical pularia justamente o
    estagio que se quer exercitar.
  - testsrc2, que TEM movimento. Fonte parada nao exercita zoompan nem
    cropdetect -- os dois leem diferenca entre quadros.
  - audio com amplitude modulada a 0,35 Hz. A curva de energia da F1 procura
    PICOS para virar punch-in; um tom de volume constante nao produz pico
    nenhum e o punch nunca dispara.
  - 44100 Hz de proposito. E a taxa da fonte deste projeto, e a cadeia de
    pitch depende disso (clipper/composicao.py:1166 documenta o estrago de
    assumir 48000 numa fonte de 44,1 kHz).

LIMITE CONHECIDO, e importante: lavfi nao sintetiza FALA. A transcricao
deste clipe sai vazia ou com ruido. Ele serve as provas FISICAS que medem
pixel, duracao e nivel de audio -- nao serve a nenhuma prova que precise de
palavras com timestamp. Para essas vale a fixture real promovida no P0.5
(provas/fixtures/wetyO2gOOeU/transcricao.json).

Convencao deste arquivo: comentarios e docstrings em PT-BR sem acento;
mensagens dirigidas ao usuario em PT-BR com acentuacao correta.

Uso:
    python provas/gerar_clipe_curto.py
    python provas/gerar_clipe_curto.py --duracao 60 --destino _teste/outro.mp4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from clipper import ffmpeg_utils  # noqa: E402
from clipper.erros import ErroClipper  # noqa: E402

DESTINO_PADRAO = RAIZ / "_teste" / "clipe-curto.mp4"

# 40s cabe um clipe de 20s (o MIN_CLIPE_S de select.py) com folga nas duas
# pontas para o encaixe em fronteira ter onde se mexer.
DURACAO_PADRAO = 40.0

LARGURA, ALTURA, FPS = 1280, 720, 30
TAXA_AUDIO = 44100

# Portadora de 220 Hz (La3) com envelope de 0,35 Hz: da ~14 maximos em 40s,
# o bastante para a deteccao de pico ter de escolher, em vez de aceitar tudo.
_EXPR_AUDIO = "0.35*sin(2*PI*220*t)*(1+0.8*sin(2*PI*0.35*t))"


def gerar(destino: Path, duracao: float) -> Path:
    """Sintetiza o clipe e devolve o caminho. Levanta ErroClipper em falha."""
    destino = Path(destino).resolve()
    destino.parent.mkdir(parents=True, exist_ok=True)

    args = [
        "-f", "lavfi",
        "-i", f"testsrc2=size={LARGURA}x{ALTURA}:rate={FPS}:duration={duracao:g}",
        "-f", "lavfi",
        "-i", f"aevalsrc={_EXPR_AUDIO}:s={TAXA_AUDIO}:d={duracao:g}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "128k", "-ar", str(TAXA_AUDIO), "-ac", "2",
        "-movflags", "+faststart",
        "-y",
        str(destino),
    ]
    ffmpeg_utils.rodar(
        args,
        descricao="geração do clipe curto de prova",
        timeout=300.0,
    )
    return destino


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="gerar_clipe_curto",
        description="Gera o clipe sintético que as provas usam como vídeo de entrada.",
    )
    p.add_argument("--duracao", type=float, default=DURACAO_PADRAO,
                   help=f"duração em segundos (padrão: {DURACAO_PADRAO:g})")
    p.add_argument("--destino", type=Path, default=DESTINO_PADRAO,
                   help=f"caminho de saída (padrão: {DESTINO_PADRAO})")
    p.add_argument("--force", action="store_true",
                   help="regenera mesmo se o arquivo já existir")
    args = p.parse_args(argv)

    if args.duracao < 25.0:
        print(
            f"erro: {args.duracao:g}s é curto demais — o menor clipe que o "
            "seletor aceita tem 20s, e as pontas precisam de folga para o "
            "encaixe em fronteira de frase. Use 25s ou mais.",
            file=sys.stderr,
        )
        return 2

    destino = Path(args.destino)
    if destino.is_file() and not args.force:
        print(f"já existe, nada a fazer: {destino}")
        print("use --force para regenerar.")
        return 0

    try:
        caminho = gerar(destino, args.duracao)
    except ErroClipper as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1

    try:
        info = ffmpeg_utils.sondar(caminho)
        print(f"gerado: {caminho}")
        print(
            f"  {info.largura}x{info.altura}, {float(info.duracao):.2f}s, "
            f"vídeo={'sim' if info.tem_video else 'não'}, "
            f"áudio={'sim' if info.tem_audio else 'não'}"
        )
    except ErroClipper:
        # Sondar e conferencia, nao a entrega: o arquivo ja esta no disco.
        print(f"gerado: {caminho}  (não consegui sondar para conferir)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
