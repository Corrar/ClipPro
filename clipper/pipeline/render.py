"""Estagio 4: render dos clipes verticais 9:16 com legenda karaoke.

O que este modulo faz, em uma frase: pega os trechos ja validados em
selecao.json, decide para ONDE olhar em cada um (reframe), queima a legenda
karaoke do preset escolhido e produz um mp4 1080x1920 por clipe, mais
metadados.json e relatorio.md.

DOIS CAMINHOS DE RENDER, e o preset escolhe qual (F4a). Um preset sem bloco
"composicao" -- bold-amarelo, clean-branco -- renderiza como na F3: recorte
9:16 cheio, legenda por cima, '-vf' de uma linha. Um preset COM esse bloco --
cortes-feed, cortes-editorial -- vai para clipper/composicao.py, que monta um
'-filter_complex' com fundo borrado, cartao arredondado, movimento de camera,
barra de titulo, barra de progresso e cadeia de audio. O objetivo desse
segundo caminho e o clipe nao ser lido como copia 1:1 do video de origem;
medido nos clipes de teste, o SSIM contra o mesmo trecho da fonte cai para
0,41-0,49 (1,00 seria identico).

Tres decisoes que valem a explicacao:

1. CORTE POR RE-ENCODE, nunca -c copy. O corte de um clipe cai numa fronteira
   de frase, que quase nunca coincide com um keyframe; copiar o fluxo daria
   um comeco congelado ou audio dessincronizado. Entao o clipe e reencodado
   em libx264, com "-ss" ANTES do "-i" (busca rapida, e exata porque estamos
   reencodando) e "-t" para a duracao -- "-to" depois de um "-ss" de entrada
   muda de significado entre versoes do ffmpeg e nao entra aqui.

2. REFRAME ESTATICO POR CLIPE. Amostramos um frame a cada
   INTERVALO_AMOSTRA_S, procuramos rosto em cada um e usamos a MEDIANA do
   centro horizontal como coluna do recorte. Um crop por clipe, fixo do
   comeco ao fim: nada de camera que persegue rosto, que treme e enjoa. Se
   menos de FRACAO_MINIMA_ROSTOS das amostras tiverem rosto (screen-share,
   b-roll, drone), o palpite do detector nao e confiavel e caimos no recorte
   central -- que e o comportamento certo, nao uma falha.

   Detalhe medido que custa caro esquecer: o BlazeFace so acha rosto em
   resolucao alta. Amostrando os frames reduzidos a 640px de largura ele acha
   ZERO rostos no video de teste; em largura cheia (1920px) acha bem. Por
   isso as amostras saem SEM scale.

3. LEGENDA SEM DOR DE ESCAPE. O valor de uma opcao de filtro do ffmpeg passa
   por tres parsers, e "C:\\..." e metacaractere nos tres. Em vez de escapar,
   gravamos o .ass numa pasta, pedimos o par (filtro, cwd) a
   ffmpeg_utils.opcao_subtitles() e rodamos o ffmpeg naquele cwd: o filtro
   cita so o NOME do arquivo. Como o cwd muda, 'fonte' e 'destino' PRECISAM
   ser caminhos absolutos -- um caminho relativo cairia na pasta errada.

Idempotencia em dois niveis. A assinatura do estagio guarda o preset, os
limites de saida e a impressao (bytes+mtime) de selecao.json -- NAO guarda
quais clipes foram pedidos, porque isso e a forma do pedido, nao o que existe
pronto em disco. Alem disso, cada clipe e conferido individualmente antes do
encode: mp4 legivel, 1080x1920 e com a duracao pedida e reaproveitado. Assim
alternar entre 'render' inteiro e '--clipe N' nao reencoda o que ja esta bom,
e selecao nova continua refazendo os clipes sozinha, sem --force.

Convencao deste arquivo: comentarios e docstrings em PT-BR sem acento;
mensagens dirigidas ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from clipper import composicao, ffmpeg_utils, legendas
from clipper.config import (
    DIR_PRESETS,
    RAIZ,
    Estado,
    Saida,
    escrever_json,
    humanizar_bytes,
    humanizar_tempo,
    ler_json,
    slugificar,
)
from clipper.erros import ErroClipper, ErroFFmpeg, ErroRender
from clipper.fronteiras import Fronteiras, mmss
from clipper.legendas import Preset
from clipper.pipeline import select
from clipper.registro import Cronometro, obter

ESTAGIO = "render"

LARGURA_SAIDA = 1080
ALTURA_SAIDA = 1920

# Um frame a cada 2 s: em um clipe de 40 s sao ~20 amostras, o bastante para
# uma mediana estavel sem transformar o reframe em outro estagio demorado.
INTERVALO_AMOSTRA_S = 2.0

# Abaixo disso o rosto e excecao no trecho (screen-share, b-roll), e seguir a
# mediana de meia duzia de deteccoes soltas cortaria o enquadramento errado.
FRACAO_MINIMA_ROSTOS = 0.5

# Confianca baixa de proposito: aqui um falso positivo custa pouco (a mediana
# absorve), e um falso negativo joga o clipe inteiro no recorte central.
CONFIANCA_ROSTO = 0.3

PRESET_PADRAO = "cortes"

# --- letterbox da fonte ----------------------------------------------------
# Video entregue em 16:9 mas FILMADO mais largo vem com tarja preta em cima e
# embaixo. Se o recorte 9:16 pegar a altura inteira, essas tarjas viajam para
# o clipe: no video de teste sao 80px de preto em cima e embaixo de um quadro
# de 1080, que viram ~142px no 1920 final -- 15% da tela apagada, justo num
# formato cujo objetivo e preencher o celular.
# So consideramos letterbox quando a tarja e grossa o bastante para nao ser
# uma cena escura passageira.
_MIN_TARJA_FRACAO = 0.02
_SEGUNDOS_CROPDETECT = 4.0
_LIMITE_CROPDETECT = 24

# --- modelo de deteccao de rosto ------------------------------------------
# O mediapipe 1.x nao traz mais a API legada 'mediapipe.solutions': o
# FaceDetector novo exige um .tflite no disco. Sao 224 KB, baixados uma vez.
DIR_MODELOS = RAIZ / "models"
NOME_MODELO_ROSTO = "blaze_face_short_range.tflite"
URL_MODELO_ROSTO = os.environ.get(
    "CLIPPER_MODELO_ROSTO_URL",
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
)
_TIMEOUT_DOWNLOAD_S = 60.0

# Criar o FaceDetector custa segundos (carrega o grafo do tflite). Um so para
# a execucao inteira, criado na primeira vez que alguem precisar dele.
_DETECTOR: Any = None

_FLAG_FORCE = "--force"

_LIMITE_TEXTO_RELATORIO = 200

# Um mp4 ja pronto e reaproveitado quando a duracao medida bate com a pedida
# dentro desta folga. O encode fecha no ultimo frame inteiro, entao a diferenca
# real fica na casa dos milissegundos; 0,3 s cobre isso sem aceitar um arquivo
# de outro trecho.
TOLERANCIA_DURACAO_S = 0.3

# clips/NN-titulo--preset.mp4: o padrao dos arquivos que ESTE estagio cria, e
# portanto os unicos que ele se permite apontar como orfaos.
_PADRAO_NOME_CLIPE = re.compile(r"^\d{2}-.+--.+\.mp4$")


# ==========================================================================
# Presets
# ==========================================================================


def _presets_disponiveis() -> list[str]:
    """Nomes dos presets que existem na pasta, em ordem alfabetica."""
    try:
        return sorted(p.stem for p in DIR_PRESETS.glob("*.json"))
    except OSError:
        return []


def _ler_preset(nome: str) -> dict[str, Any]:
    """O JSON cru do preset, com as mensagens de erro que o usuario precisa.

    Nome inexistente nao vira KeyError: vira uma mensagem que LISTA os presets
    que existem, porque o usuario nao tem como adivinhar os nomes.
    """
    nome = str(nome).strip()
    arquivo = DIR_PRESETS / f"{nome}.json"
    if not nome or not arquivo.is_file():
        existentes = _presets_disponiveis()
        catalogo = ", ".join(existentes) if existentes else "(nenhum)"
        raise ErroRender(
            f"não existe o preset de legenda '{nome}'. "
            f"Os presets disponíveis são: {catalogo}.",
            sugestao=(
                f'rode com um preset que existe:  clipper render <entrada> '
                f'--preset {existentes[0] if existentes else PRESET_PADRAO}   '
                f"(os arquivos ficam em {DIR_PRESETS})"
            ),
        )

    try:
        dados = ler_json(arquivo)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ErroRender(
            f"o preset '{nome}' existe mas não é um JSON legível: {exc}",
            sugestao=(
                f'abra {arquivo} e conserte o JSON, ou use outro preset '
                f"({', '.join(_presets_disponiveis())})."
            ),
        ) from exc

    if not isinstance(dados, dict):
        raise ErroRender(
            f"o preset '{nome}' deveria ser um objeto JSON, e veio "
            f"{type(dados).__name__}.",
            sugestao=f"compare {arquivo} com {DIR_PRESETS / (PRESET_PADRAO + '.json')}.",
        )

    dados.setdefault("nome", nome)
    return dados


def carregar_preset(nome: str) -> Preset:
    """Le clipper/presets/<nome>.json e devolve o Preset da legenda."""
    dados = _ler_preset(nome)
    try:
        preset_obj = Preset.de_dict(dados)
    except TypeError as exc:
        # de_dict so repassa os campos conhecidos: TypeError aqui significa
        # que FALTA campo obrigatorio no json. Os campos da v2 (pop, cor de
        # destaque) tem padrao e nao entram nesta lista -- senao um preset
        # perfeitamente valido da F3 seria acusado de incompleto.
        import dataclasses

        obrigatorios = {
            f.name
            for f in dataclasses.fields(Preset)
            if f.default is dataclasses.MISSING
            and f.default_factory is dataclasses.MISSING  # type: ignore[misc]
        }
        faltando = sorted(obrigatorios - set(dados))
        raise ErroRender(
            f"o preset '{nome}' está incompleto: falta(m) "
            f"{', '.join(faltando) if faltando else 'campo(s) obrigatório(s)'}.",
            detalhe=str(exc),
            sugestao=(
                f"copie {DIR_PRESETS / (PRESET_PADRAO + '.json')} e edite as cores/"
                "tamanhos a partir dele: assim nenhum campo fica de fora."
            ),
        ) from exc

    _conferir_cores(preset_obj, nome)
    return preset_obj


_PADRAO_COR_ASS = re.compile(r"^&H[0-9a-fA-F]{6,8}&$")

# Os campos de cor da legenda, que vao CRUS para dentro do ASS.
_CORES_DA_LEGENDA = (
    "cor_falada",
    "cor_por_falar",
    "cor_destaque",
    "cor_contorno",
    "cor_sombra",
)


def _conferir_cores(preset_obj: Preset, nome: str) -> None:
    """Cor de legenda fora do formato do ASS vira erro aqui, nao pixel preto.

    O mesmo arquivo de preset usa '#RRGGBB' nas cores da composicao e
    '&HBBGGRR&' nas da legenda -- trocar as duas notacoes e a confusao mais
    natural do mundo. E o libass nao reclama: ele ignora a tag e desenha a
    palavra em PRETO, sobre um contorno preto. Sem esta checagem, o defeito so
    aparece assistindo ao clipe, depois do encode inteiro.
    """
    tortas = [
        f"{campo}={getattr(preset_obj, campo)!r}"
        for campo in _CORES_DA_LEGENDA
        if str(getattr(preset_obj, campo, "") or "")
        and not _PADRAO_COR_ASS.match(str(getattr(preset_obj, campo)))
    ]
    if not tortas:
        return
    raise ErroRender(
        f"o preset '{nome}' tem cor(es) de legenda fora do formato do ASS: "
        + ", ".join(tortas)
        + ".",
        sugestao=(
            "as cores da LEGENDA são &HBBGGRR& (azul, verde, vermelho — nesta ordem, "
            "ao contrário do HTML); as do bloco 'composicao' são #RRGGBB. Exemplo: "
            "amarelo é &H0000E5FF& na legenda e #FFE500 na composição."
        ),
    )


def carregar_composicao(nome: str) -> composicao.Composicao | None:
    """O bloco de composicao do preset, ou None se ele nao tiver um.

    Preset sem "composicao" e um preset da F3: recorte 9:16 cheio, legenda
    queimada por cima e mais nada. Os dois caminhos convivem de proposito --
    o visual aprovado na F3 continua disponivel exatamente como estava.
    """
    return composicao.de_preset(_ler_preset(nome), nome)


# ==========================================================================
# Deteccao de rosto (imports tardios: 'clipper --help' nao paga por mediapipe)
# ==========================================================================


def _garantir_modelo() -> Path:
    """Devolve o .tflite do detector, baixando-o uma unica vez se faltar."""
    alvo = DIR_MODELOS / NOME_MODELO_ROSTO
    if alvo.is_file() and alvo.stat().st_size > 0:
        return alvo

    log = obter()
    log.info("   baixando o modelo de detecção de rosto (224 KB, uma vez)…")
    tmp = alvo.with_name(alvo.name + ".parcial")
    try:
        DIR_MODELOS.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL_MODELO_ROSTO, timeout=_TIMEOUT_DOWNLOAD_S) as resposta:
            tmp.write_bytes(resposta.read())
        if tmp.stat().st_size == 0:
            raise OSError("o download veio vazio (0 byte)")
        tmp.replace(alvo)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ErroRender(
            "não consegui baixar o modelo de detecção de rosto "
            f"({NOME_MODELO_ROSTO}, 224 KB).",
            detalhe=f"{type(exc).__name__}: {exc}\nURL: {URL_MODELO_ROSTO}",
            sugestao=(
                f"baixe o arquivo à mão no navegador ({URL_MODELO_ROSTO}) e "
                f"salve-o como {alvo} — a pasta {DIR_MODELOS} é o único lugar "
                "onde o clipper procura por ele. Depois repita o mesmo comando."
            ),
        ) from exc

    log.info(f"   modelo salvo em {alvo} ({humanizar_bytes(alvo.stat().st_size)}).")
    return alvo


def _obter_detector() -> Any:
    """FaceDetector unico do processo (lazy). Criar um por clipe seria caro."""
    global _DETECTOR
    if _DETECTOR is not None:
        return _DETECTOR

    modelo = _garantir_modelo()
    try:
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core import base_options as bo
    except ImportError as exc:
        raise ErroRender(
            "o mediapipe não está instalado, e sem ele não há detecção de rosto "
            "para reenquadrar os clipes.",
            detalhe=str(exc),
            sugestao=(
                "instale as dependências do projeto:  "
                f'"{RAIZ / ".venv" / "Scripts" / "python.exe"}" -m pip install '
                f'-r "{RAIZ / "requirements.txt"}"'
            ),
        ) from exc

    try:
        opcoes = vision.FaceDetectorOptions(
            base_options=bo.BaseOptions(model_asset_path=str(modelo)),
            running_mode=vision.RunningMode.IMAGE,
            min_detection_confidence=CONFIANCA_ROSTO,
        )
        _DETECTOR = vision.FaceDetector.create_from_options(opcoes)
    except Exception as exc:  # o mediapipe levanta tipos proprios do C++
        raise ErroRender(
            "não consegui inicializar o detector de rosto do mediapipe.",
            detalhe=f"{type(exc).__name__}: {exc}\nmodelo: {modelo}",
            sugestao=(
                f"apague {modelo} para forçar um download novo (o arquivo pode "
                "ter vindo corrompido) e repita o comando."
            ),
        ) from exc
    return _DETECTOR


def _ler_rgb(caminho: Path) -> Any:
    """Le um frame do disco como ndarray RGB, ou None se o arquivo nao presta.

    Passa pelos bytes de proposito: cv2.imread() falha em caminho com
    caractere fora do ASCII no Windows, e o caminho aqui vem da pasta do
    usuario.
    """
    import cv2
    import numpy as np

    try:
        dados = np.frombuffer(caminho.read_bytes(), dtype=np.uint8)
    except OSError:
        return None
    if dados.size == 0:
        return None
    imagem = cv2.imdecode(dados, cv2.IMREAD_COLOR)
    if imagem is None:
        return None
    return cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)


def _centro_do_maior_rosto(quadro: Any) -> float | None:
    """Centro x normalizado (0..1) do maior rosto do frame, ou None se nenhum.

    O MAIOR e o certo: numa cena com plateia ou reflexo, o rosto que ocupa
    mais area e o do apresentador, que e quem o clipe precisa enquadrar.
    """
    import mediapipe as mp

    altura, largura = quadro.shape[0], quadro.shape[1]
    if not largura or not altura:
        return None

    imagem = mp.Image(image_format=mp.ImageFormat.SRGB, data=quadro)
    deteccoes = _obter_detector().detect(imagem).detections
    if not deteccoes:
        return None

    maior = max(
        deteccoes,
        key=lambda d: float(d.bounding_box.width) * float(d.bounding_box.height),
    )
    caixa = maior.bounding_box
    centro = (float(caixa.origin_x) + float(caixa.width) / 2.0) / float(largura)
    return min(1.0, max(0.0, centro))


# ==========================================================================
# Reframe
# ==========================================================================


def _par(valor: float) -> int:
    """Arredonda para baixo ao par mais proximo. O H.264 4:2:0 exige par."""
    n = int(valor)
    return n - (n % 2)


def detectar_conteudo(
    fonte: Path, inicio: float, duracao: float, largura_fonte: int, altura_fonte: int
) -> dict[str, Any]:
    """Acha o retangulo com imagem de verdade, descontando tarja preta.

    Usa o filtro cropdetect do proprio ffmpeg sobre alguns segundos do trecho e
    fica com o retangulo mais frequente. Devolve o quadro inteiro quando nao ha
    tarja, quando ela e fina demais para ser levada a serio, ou quando o
    cropdetect nao responde -- em duvida, nunca cortar imagem do usuario.
    """
    log = obter()
    largura_fonte, altura_fonte = int(largura_fonte), int(altura_fonte)
    inteiro = {
        "x": 0, "y": 0,
        "largura": largura_fonte, "altura": altura_fonte,
        "letterbox": False,
    }
    amostra = max(1.0, min(_SEGUNDOS_CROPDETECT, float(duracao)))
    try:
        saida = ffmpeg_utils.rodar(
            [
                # ffmpeg_utils.rodar ja prefixa "-loglevel error", e o cropdetect
                # publica o resultado em nivel INFO: sem repetir a opcao aqui
                # (a ultima ocorrencia vence) a saida vem vazia e a tarja passa
                # despercebida.
                "-loglevel", "info",
                "-ss", f"{float(inicio):.3f}",
                "-i", str(fonte),
                "-t", f"{amostra:.3f}",
                "-vf", f"cropdetect=limit={_LIMITE_CROPDETECT}:round=2",
                "-f", "null", "-",
            ],
            descricao="detecção de tarja preta",
            timeout=120.0,
        )
    except ErroClipper:
        return inteiro

    contagem: dict[tuple[int, int, int, int], int] = {}
    for achado in re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", saida):
        chave = tuple(int(v) for v in achado)  # type: ignore[assignment]
        contagem[chave] = contagem.get(chave, 0) + 1
    if not contagem:
        return inteiro

    largura, altura, x, y = max(contagem.items(), key=lambda par: par[1])[0]
    if largura <= 0 or altura <= 0:
        return inteiro
    if x < 0 or y < 0 or x + largura > largura_fonte or y + altura > altura_fonte:
        return inteiro

    corta_altura = (altura_fonte - altura) / altura_fonte
    corta_largura = (largura_fonte - largura) / largura_fonte
    if max(corta_altura, corta_largura) < _MIN_TARJA_FRACAO:
        return inteiro

    log.info(
        f"      tarja preta na fonte: a imagem real é {largura}×{altura} "
        f"(+{x}+{y}) dentro de {largura_fonte}×{altura_fonte} — recortando dela, "
        "para o clipe não sair com faixa preta."
    )
    return {
        "x": _par(x), "y": _par(y),
        "largura": _par(largura), "altura": _par(altura),
        "letterbox": True,
    }


def _geometria(centro: float, largura_fonte: int, altura_fonte: int) -> dict[str, Any]:
    """Traduz um centro normalizado no retangulo de crop, em pixels reais.

    O recorte sai SEMPRE na proporcao de saida (9:16), cortando no eixo que
    sobra -- e quem decide o eixo e a comparacao das razoes, nao um palpite
    sobre a fonte ser "de camera" ou "de celular":

      - fonte mais LARGA que 9:16 (16:9, 4:3, quadrada): mantem a altura
        inteira e corta na horizontal, na coluna que o reframe indicou;
      - fonte mais ALTA que 9:16 (celular 1080x2340) ou exatamente 9:16:
        mantem a largura inteira e corta faixas em cima e embaixo. Aqui o
        centro horizontal do rosto nao tem uso: nao ha o que escolher na
        horizontal.

    A versao antiga so cortava na horizontal, entao uma fonte mais alta
    passava inteira pelo crop e o scale seguinte ACHATAVA a imagem (um quadrado
    de 800x800 saia 800x656). Cortar nos dois eixos e o que garante que o scale
    nunca deforme.

    Devolve tambem 'corte' ("horizontal" ou "vertical") para o chamador saber
    se a deteccao de rosto tem alguma influencia no resultado.
    """
    largura_fonte = max(2, int(largura_fonte))
    altura_fonte = max(2, int(altura_fonte))
    alvo = LARGURA_SAIDA / ALTURA_SAIDA
    razao_fonte = largura_fonte / altura_fonte

    if razao_fonte > alvo:
        corte = "horizontal"
        altura_crop = max(2, _par(altura_fonte))
        largura_crop = max(2, _par(min(largura_fonte, round(altura_crop * alvo))))
        limite_x = max(0, largura_fonte - largura_crop)
        x = _par(min(max(round(centro * largura_fonte - largura_crop / 2), 0), limite_x))
        y = 0
    else:
        corte = "vertical"
        largura_crop = max(2, _par(largura_fonte))
        altura_crop = max(2, _par(min(altura_fonte, round(largura_crop / alvo))))
        limite_y = max(0, altura_fonte - altura_crop)
        y = _par(min(max(round((altura_fonte - altura_crop) / 2), 0), limite_y))
        x = 0

    return {
        "x": int(x),
        "y": int(y),
        "largura": int(largura_crop),
        "altura": int(altura_crop),
        "corte": corte,
    }


def _limpar_frames(trabalho: Path, prefixo: str) -> None:
    """Apaga as amostras deste clipe (as de uma rodada anterior, e as desta).

    As amostras saem em PNG por precisao: no video de teste, as MESMAS amostras
    em JPEG q2 mudam a conta de rostos em ate um frame por clipe (o artefato de
    compressao come o contorno do rosto pequeno). PNG em 1920x1080 custa ~1,4 MB
    por frame, ~186 MB numa selecao de cinco clipes -- por isso os frames sao
    apagados assim que a mediana e calculada, em vez de ficarem na pasta.
    """
    for antigo in trabalho.glob(prefixo + "*"):
        try:
            antigo.unlink()
        except OSError:
            continue


def calcular_reframe(
    fonte: Path,
    inicio: float,
    duracao: float,
    trabalho: Path,
    largura_fonte: int,
    altura_fonte: int,
    *,
    id_clipe: int | None = None,
    trechos: Sequence[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Decide o recorte 9:16 de um trecho: rosto quando da, centro quando nao.

    Amostra um frame a cada INTERVALO_AMOSTRA_S em LARGURA CHEIA (reduzir para
    640px zera a deteccao neste tipo de video), procura o maior rosto de cada
    frame e usa a MEDIANA dos centros -- a mediana ignora o frame em que o
    detector se animou com um quadro na parede, coisa que a media nao faria.

    'id_clipe' e opcional so para manter a chamada curta em uso avulso; o
    estagio passa o id real para que as amostras de clipes diferentes nao se
    misturem na pasta de trabalho.

    `trechos` (clipe v2) sao os segmentos MANTIDOS, em tempo da fonte. Com
    eles a amostragem roda dentro de cada segmento e nunca no span (D5 Q6):
    [inicio, inicio+duracao] num v2 e o comeco do span mais a SOMA, que
    amostrava justamente a gordura removida e podia deixar segmentos inteiros
    de fora -- o enquadramento do clipe saia decidido por imagem que nao esta
    no clipe. Sem `trechos`, a chamada e exatamente a de antes.
    """
    log = obter()
    fonte = Path(fonte).resolve()
    trabalho = Path(trabalho)
    trabalho.mkdir(parents=True, exist_ok=True)

    marca = int(id_clipe) if id_clipe is not None else int(round(float(inicio) * 1000))
    prefixo = f"crop_{marca}_"
    _limpar_frames(trabalho, prefixo)

    janelas = [
        (float(a), float(b) - float(a)) for a, b in (trechos or ()) if float(b) > float(a)
    ] or [(float(inicio), float(duracao))]

    # Fonte ja vertical (ou exatamente 9:16): o corte e em cima/embaixo e o
    # centro horizontal do rosto nao influencia nada. Amostrar e detectar
    # rosto aqui seria minuto de CPU para chegar no mesmo retangulo.
    # A tarja preta da fonte nao e imagem: o recorte 9:16 e calculado DENTRO do
    # retangulo com conteudo, senao o preto viaja para o clipe.
    # O cropdetect le poucos segundos: no v2 eles saem do MAIOR segmento, o que
    # menos chance tem de ser curto demais para os 4 s da amostra.
    inicio_tarja, duracao_tarja = max(janelas, key=lambda j: j[1])
    conteudo = detectar_conteudo(
        fonte, inicio_tarja, duracao_tarja, int(largura_fonte), int(altura_fonte)
    )

    geo_vertical = _geometria(0.5, conteudo["largura"], conteudo["altura"])
    if geo_vertical["corte"] == "vertical":
        log.info(
            f"      a imagem é vertical ({conteudo['largura']}×{conteudo['altura']}): o "
            "recorte tira faixas em cima e embaixo, mantendo a largura inteira — não há "
            "coluna a escolher, então a detecção de rosto é dispensada."
        )
        return {
            "modo": "vertical",
            "x": geo_vertical["x"] + conteudo["x"],
            "y": geo_vertical["y"] + conteudo["y"],
            "largura": geo_vertical["largura"],
            "altura": geo_vertical["altura"],
            "amostras": 0,
            "com_rosto": 0,
            "fracao": 0.0,
            "mediana_x_norm": 0.5,
            "conteudo": conteudo,
        }

    amostras: list[Path] = []
    centros: list[float] = []
    try:
        # A chamada do ffmpeg fica DENTRO do try: um Ctrl+C no meio da
        # amostragem deixaria dezenas de PNG de 1,4 MB em _trabalho/.
        for k, (ini_janela, dur_janela) in enumerate(janelas):
            # Um trecho so (v1) mantem o nome de sempre; no v2 cada segmento
            # ganha o seu, e a mediana sai de todos juntos.
            padrao = prefixo + ("%03d.png" if len(janelas) == 1 else f"s{k}_%03d.png")
            ffmpeg_utils.rodar(
                [
                    "-ss", f"{ini_janela:.3f}",
                    "-i", str(fonte),
                    "-t", f"{dur_janela:.3f}",
                    "-vf", f"fps=1/{INTERVALO_AMOSTRA_S}",
                    "-q:v", "2",
                    str(trabalho / padrao),
                ],
                descricao=f"amostragem de frames do clipe {marca}",
                sugestao=(
                    "confira se fonte.mp4 não está truncado (o download pode ter caído "
                    "no meio):  clipper ingest <entrada> " + _FLAG_FORCE
                ),
            )
        amostras = sorted(trabalho.glob(prefixo + "*.png"))
        for quadro_arquivo in amostras:
            quadro = _ler_rgb(quadro_arquivo)
            if quadro is None:
                continue
            centro = _centro_do_maior_rosto(quadro)
            if centro is not None:
                centros.append(centro)
    finally:
        # Os frames ja deram o que tinham que dar: sao ~1,4 MB cada e nao
        # entram em nenhum artefato. Some com eles mesmo se a deteccao falhar.
        _limpar_frames(trabalho, prefixo)

    total = len(amostras)
    fracao = (len(centros) / total) if total else 0.0

    if total and fracao >= FRACAO_MINIMA_ROSTOS:
        centro_final = float(statistics.median(centros))
        modo = "rosto"
        log.info(
            f"      reframe por rosto: {len(centros)}/{total} amostras com rosto "
            f"({fracao * 100:.0f}%), centro mediano em {centro_final:.3f} da largura."
        )
    else:
        centro_final = 0.5
        modo = "central"
        motivo = (
            "nenhuma amostra pôde ser lida"
            if not total
            else (
                f"só {len(centros)}/{total} amostras ({fracao * 100:.0f}%) têm rosto, "
                f"abaixo do mínimo de {FRACAO_MINIMA_ROSTOS * 100:.0f}%"
            )
        )
        log.info(
            f"      reframe central: {motivo} — a mediana de tão poucas detecções "
            "não é confiável, então o recorte fica no meio do quadro."
        )

    # O centro do rosto foi medido no quadro INTEIRO; dentro do retangulo de
    # conteudo ele ocupa outra fracao. Sem essa conversao, uma tarja lateral
    # deslocaria o recorte.
    centro_conteudo = centro_final
    if conteudo["letterbox"] and conteudo["largura"] > 0:
        centro_px = centro_final * int(largura_fonte) - conteudo["x"]
        centro_conteudo = min(1.0, max(0.0, centro_px / conteudo["largura"]))

    geo = _geometria(centro_conteudo, conteudo["largura"], conteudo["altura"])
    return {
        "modo": modo,
        "x": geo["x"] + conteudo["x"],
        "y": geo["y"] + conteudo["y"],
        "largura": geo["largura"],
        "altura": geo["altura"],
        "amostras": total,
        "com_rosto": len(centros),
        "fracao": round(fracao, 3),
        "mediana_x_norm": round(centro_final, 3),
        "conteudo": conteudo,
    }


# ==========================================================================
# Entradas do estagio
# ==========================================================================


def _exigir_entradas(saida: Saida, entrada_exemplo: str = "<entrada>") -> None:
    """Falha cedo e com o comando concreto de quem produz o que falta."""
    if not saida.fonte_mp4.is_file() or saida.fonte_mp4.stat().st_size == 0:
        raise ErroRender(
            f"não encontrei o vídeo de origem em {saida.fonte_mp4}.",
            sugestao=(
                "faça a ingestão antes de renderizar:  "
                f'clipper ingest "{entrada_exemplo}"'
            ),
        )
    if not saida.selecao_json.is_file() or saida.selecao_json.stat().st_size == 0:
        raise ErroRender(
            f"não encontrei uma seleção pronta em {saida.selecao_json}.",
            sugestao=(
                "gere a seleção antes de renderizar:  "
                f'clipper select "{entrada_exemplo}" --resposta <arquivo>'
            ),
        )
    if not saida.transcricao_json.is_file() or saida.transcricao_json.stat().st_size == 0:
        raise ErroRender(
            f"não encontrei a transcrição em {saida.transcricao_json}, e sem ela "
            "não há palavras com tempo para montar a legenda karaoke.",
            sugestao=f'refaça a transcrição:  clipper transcribe "{entrada_exemplo}"',
        )


def _ler_entrada(caminho: Path, o_que: str) -> Any:
    try:
        return ler_json(caminho)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ErroRender(
            f"não consegui ler {o_que} em {caminho}: {exc}",
            sugestao=(
                "o arquivo está corrompido ou pela metade. Refaça o estágio que "
                f"o produziu e repita o render (veja  clipper info)."
            ),
        ) from exc


def _clipes_da_selecao(selecao: Any, caminho: Path) -> list[dict[str, Any]]:
    if not isinstance(selecao, dict) or not isinstance(selecao.get("clipes"), list):
        raise ErroRender(
            f"{caminho.name} não tem o formato esperado (um objeto com a lista "
            "'clipes').",
            sugestao="refaça a seleção:  clipper select <entrada> --resposta <arquivo>",
        )
    lista = [c for c in selecao["clipes"] if isinstance(c, dict)]
    if not lista:
        raise ErroRender(
            f"{caminho.name} não tem nenhum clipe para renderizar.",
            sugestao="refaça a seleção:  clipper select <entrada> --resposta <arquivo>",
        )
    return lista


def _id_seguro(valor: Any) -> int | None:
    """int(valor) sem explodir: devolve None quando o campo 'id' esta torto.

    Um id ilegivel nao pode virar ValueError cru aqui -- ele e um defeito de
    selecao.json, e quem nomeia os defeitos e _validar_clipes().
    """
    if isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _validar_clipes(escolhidos: list[dict[str, Any]], caminho: Path) -> None:
    """Confere os campos de TODOS os clipes escolhidos ANTES de encodar nada.

    selecao.json e texto na pasta do usuario, e ajustar um tempo a mao e uma
    tentacao obvia. Sem esta checagem, um campo faltando so aparecia quando a
    fila chegava no clipe defeituoso -- depois de minutos de encode nos
    anteriores -- e ainda por cima como KeyError cru.
    """
    defeitos: list[str] = []
    for posicao, clipe in enumerate(escolhidos, 1):
        id_clipe = _id_seguro(clipe.get("id", posicao))
        nome = f"o clipe {id_clipe}" if id_clipe is not None else f"o {posicao}º clipe"

        if id_clipe is None:
            defeitos.append(
                f"o {posicao}º clipe tem um 'id' que não é um número inteiro "
                f"({clipe.get('id')!r})"
            )

        # v2: se o clipe declara `segmentos`, a FORMA e conferida pela mesma
        # funcao que o select usa -- importada, nao copiada. O render nao tem
        # como conferir fronteira de frase (isso exige a transcricao, que ele
        # nao carrega para validar), mas nao pode montar um filtergraph em
        # cima de um `segmentos` malformado.
        if select.e_v2(clipe):
            erros_forma = select.conferir_forma_segmentos(clipe.get("segmentos"), nome)
            if erros_forma:
                defeitos.extend(erros_forma)
                continue

        tempos: dict[str, float] = {}
        for campo in ("inicio", "fim"):
            if campo not in clipe:
                defeitos.append(f"{nome} está sem o campo '{campo}'")
                continue
            valor = clipe.get(campo)
            if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
                defeitos.append(f"{nome} tem '{campo}' que não é um número ({valor!r})")
                continue
            try:
                tempos[campo] = float(valor)
            except (TypeError, ValueError):
                defeitos.append(f"{nome} tem '{campo}' que não é um número ({valor!r})")
        if len(tempos) == 2 and tempos["fim"] <= tempos["inicio"]:
            defeitos.append(
                f"{nome} tem 'fim' ({tempos['fim']:g}) menor ou igual a 'inicio' "
                f"({tempos['inicio']:g}) — a duração seria zero ou negativa"
            )

        titulo = clipe.get("titulo")
        if not isinstance(titulo, str) or not titulo.strip():
            defeitos.append(f"{nome} está sem um 'titulo' de texto preenchido")

    if not defeitos:
        return

    raise ErroRender(
        f"{caminho.name} tem {len(defeitos)} campo(s) com problema, e sem eles não dá "
        "para renderizar:\n  - " + "\n  - ".join(defeitos),
        sugestao=(
            f'refaça a seleção:  clipper select "{caminho.parent.name}" '
            f"--resposta <arquivo>   "
            f"— ou conserte os campos à mão em {caminho} (cada clipe precisa de "
            "'id' inteiro, 'inicio' e 'fim' em segundos com fim > inicio, e 'titulo' "
            "preenchido). Nenhum clipe foi renderizado."
        ),
    )


def _filtrar_clipes(
    lista: list[dict[str, Any]], pedidos: Sequence[int] | None
) -> list[dict[str, Any]]:
    """Nenhum pedido = todos. Id inexistente diz quais ids existem."""
    existentes = [
        i
        for i in (_id_seguro(c.get("id", n + 1)) for n, c in enumerate(lista))
        if i is not None
    ]
    if pedidos is None:
        return list(lista)

    faltando = [int(p) for p in pedidos if int(p) not in existentes]
    if faltando:
        raise ErroRender(
            "a seleção não tem o(s) clipe(s) "
            + ", ".join(str(f) for f in sorted(set(faltando)))
            + ". Os ids disponíveis são: "
            + ", ".join(str(i) for i in existentes)
            + ".",
            sugestao=(
                "repita o comando pedindo um id que existe (ou sem --clipe "
                "nenhum, para renderizar todos)."
            ),
        )
    querido = {int(p) for p in pedidos}
    return [c for i, c in enumerate(lista) if _id_seguro(c.get("id", i + 1)) in querido]


def _impressao_transcricao(saida: Saida) -> dict[str, Any]:
    """Identidade de transcricao.json, para entrar na assinatura do estagio.

    E a transcricao que vira a legenda QUEIMADA no video. Sem ela aqui, trocar
    o modelo do whisper e rodar 'clipper transcribe --force' nao fazia o render
    perceber nada: os clipes continuavam com a legenda antiga para sempre.
    """
    try:
        st = saida.transcricao_json.stat()
    except OSError:
        return {}
    return {"transcricao_bytes": int(st.st_size), "transcricao_mtime": int(st.st_mtime)}


def _impressao_energia(saida: Saida) -> dict[str, Any]:
    """Identidade de energia.json: e dela que saem os instantes de punch-in."""
    try:
        st = saida.energia_json.stat()
    except OSError:
        return {}
    return {"energia_bytes": int(st.st_size), "energia_mtime": int(st.st_mtime)}


def _impressao_selecao(saida: Saida) -> dict[str, Any]:
    """Identidade de selecao.json, para entrar na assinatura de idempotencia.

    Sem isso, trocar a seleção e repetir 'clipper render' devolveria os clipes
    velhos, porque o preset e o tamanho de saida continuariam os mesmos.
    """
    try:
        st = saida.selecao_json.stat()
    except OSError:
        return {}
    return {"selecao_bytes": int(st.st_size), "selecao_mtime": int(st.st_mtime)}


def _bloco_selecao(impressao: dict[str, Any]) -> dict[str, Any]:
    """A mesma impressao, no formato que vai para o topo de metadados.json.

    O metadados guarda de QUAL selecao vieram os clipes que ele lista: sem
    isso, entradas de uma selecao antiga sobreviveriam para sempre e o mesmo
    'id' passaria a descrever dois trechos diferentes.
    """
    return {
        "bytes": impressao.get("selecao_bytes"),
        "mtime": impressao.get("selecao_mtime"),
    }


# ==========================================================================
# Render de um clipe
# ==========================================================================


def _nome_arquivo(id_clipe: int, titulo: str, preset: str) -> str:
    """clips/NN-titulo--preset.mp4.

    O preset entra SEMPRE no nome: o mesmo clipe pode ser renderizado em dois
    presets, e os dois precisam coexistir para a comparacao lado a lado.
    """
    return f"{int(id_clipe):02d}-{slugificar(titulo, limite=48)}--{slugificar(preset, limite=32)}.mp4"


def _apagar_silencioso(caminho: Path) -> None:
    """Remove um .tmp/.parcial orfao de escrita atomica. Nunca levanta."""
    try:
        caminho.unlink(missing_ok=True)
    except OSError:
        pass


def _erro_de_escrita(
    caminho: Path, exc: OSError, *, o_que: str, sugestao: str
) -> ErroRender:
    """Disco cheio / arquivo aberto e falha PREVISIVEL, nao bug do clipper.

    No Windows, um metadados.json apenas ABERTO em outro processo ja faz o
    replace() falhar com PermissionError [WinError 5]. Sem este tratamento a
    excecao subia crua ate o cli e saia como "isso e um bug do clipper",
    deixando um .tmp orfao na pasta do usuario.
    """
    _apagar_silencioso(caminho.with_name(caminho.name + ".tmp"))
    return ErroRender(
        f"não consegui gravar {o_que} em {caminho}.",
        detalhe=f"{type(exc).__name__}: {exc}",
        sugestao=sugestao,
    )


def _escrever_texto(caminho: Path, texto: str) -> Path:
    """Escrita atomica de texto. utf-8 e LF explicitos: o alvo e o Windows.

    Sem `newline="\n"` o Python traduziria cada \n para \r\n no Windows e o
    mesmo conteudo sairia com bytes diferentes em cada maquina -- o bastante
    para uma prova de diff acusar mudanca que nao houve.
    """
    tmp = caminho.with_name(caminho.name + ".tmp")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(texto, encoding="utf-8", newline="\n")
    tmp.replace(caminho)
    return caminho


def _gravar_ass(caminho: Path, texto: str) -> None:
    tmp = caminho.with_name(caminho.name + ".tmp")
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(texto, encoding="utf-8", newline="\n")
        tmp.replace(caminho)
    except OSError as exc:
        raise _erro_de_escrita(
            caminho,
            exc,
            o_que=f"o arquivo de legenda {caminho.name}",
            sugestao=(
                f"libere espaço em disco (ou feche o programa que está com {caminho.parent} "
                "aberta) e repita o mesmo comando — os clipes que já ficaram prontos em "
                "clips/ são reaproveitados, então o render recomeça de onde parou."
            ),
        ) from exc


# ==========================================================================
# Pacote de publicacao (F6/P3): capa.jpg e publicacao.md por clipe
# ==========================================================================

# O checklist e ESTATICO e vem do briefing do lote: e o que o Bruno confere
# antes de publicar, e nao depende de nada do clipe.
CHECKLIST_PUBLICACAO = (
    "Autorização/licença do material confirmada",
    "Contribuição editorial perceptível sem ler a descrição",
    "O 1º segundo promete exatamente o que o clipe entrega",
    "Começo, progressão e payoff presentes",
    "Legendas legíveis, fora da UI, sem cobrir rosto/ação",
    "Título representa o que ocorreu (sem sensacionalismo falso)",
    "Substancialmente diferente dos outros clipes do canal",
)

# Onde a capa cai quando o clipe nao pede `capa_ts`: 1s depois do inicio. Nao
# e o frame 0 de proposito -- no primeiro quadro o fade de entrada ainda esta
# escurecendo a imagem e a pilula do gancho ainda esta deslizando.
_CAPA_PADRAO_S = 1.0


def _instante_da_capa(
    clipe: dict[str, Any], segmentos: list[dict[str, Any]], duracao: float
) -> float:
    """O instante da capa, em tempo do CLIPE (nao da fonte).

    `capa_ts` chega em tempo da FONTE, porque e assim que o modelo enxerga o
    video. A capa, porem, e extraida do mp4 JA RENDERIZADO: assim ela sai
    composta, em 9:16, com cartao e legenda -- igual ao que o espectador ve.
    Uma capa tirada da fonte mostraria o vídeo horizontal cru, que nao e o
    produto.
    """
    bruto = clipe.get("capa_ts")
    if bruto is not None:
        try:
            fonte_ts = float(bruto)
        except (TypeError, ValueError):
            fonte_ts = None
        if fonte_ts is not None:
            if segmentos:
                convertidos = composicao.remapear_tempos([fonte_ts], segmentos)
                if convertidos:
                    return max(0.0, min(convertidos[0], max(0.0, duracao - 0.05)))
            else:
                relativo = fonte_ts - float(clipe["inicio"])
                if 0.0 <= relativo <= duracao:
                    return max(0.0, min(relativo, max(0.0, duracao - 0.05)))
    return max(0.0, min(_CAPA_PADRAO_S, max(0.0, duracao - 0.05)))


def _gravar_capa(clipe_mp4: Path, instante: float, destino: Path) -> Path | None:
    """Extrai um quadro do clipe pronto. Nunca derruba o render se falhar."""
    try:
        ffmpeg_utils.rodar(
            [
                "-ss", f"{instante:.3f}",
                "-i", str(clipe_mp4),
                "-frames:v", "1",
                "-q:v", "3",
                "-y", str(destino),
            ],
            descricao=f"capa de {clipe_mp4.name}",
            timeout=120.0,
        )
    except ErroClipper as exc:
        obter().warning(
            f"      aviso:  não consegui gravar a capa de {clipe_mp4.name}: {exc}"
        )
        return None
    return destino if destino.is_file() else None


def montar_publicacao(
    clipe: dict[str, Any],
    *,
    titulo: str,
    arquivo_mp4: str,
    capa: str | None,
    duracao: float,
    segmentos: list[dict[str, Any]],
) -> str:
    """O texto de clips/<clipe>.publicacao.md.

    Funcao pura para poder ser conferida sem renderizar nada.
    """
    linhas: list[str] = [f"# {titulo}", ""]
    linhas.append(f"- **Arquivo:** `{arquivo_mp4}`")
    if capa:
        linhas.append(f"- **Capa:** `{capa}`")
    linhas.append(f"- **Duração:** {duracao:.1f}s")
    if segmentos:
        faixas = ", ".join(
            f"{mmss(s['inicio'])}–{mmss(s['fim'])}" for s in segmentos
        )
        linhas.append(f"- **Trechos da fonte:** {faixas} ({len(segmentos)} segmentos)")
    else:
        linhas.append(
            f"- **Trecho da fonte:** {mmss(float(clipe['inicio']))}–"
            f"{mmss(float(clipe['fim']))}"
        )

    gancho = str(clipe.get("gancho_sugerido") or "").strip()
    if gancho:
        linhas += ["", "## Gancho", "", f"> {gancho}"]

    descricao = str(clipe.get("descricao") or "").strip()
    linhas += ["", "## Descrição", ""]
    linhas.append(descricao if descricao else "_(o modelo não sugeriu descrição)_")

    conclusao = str(clipe.get("conclusao") or "").strip()
    if conclusao:
        linhas += ["", "## Conclusão na tela", "", f"> {conclusao}"]

    linhas += ["", "## Checklist", ""]
    linhas += [f"- [ ] {item}" for item in CHECKLIST_PUBLICACAO]
    return "\n".join(linhas) + "\n"


def _item_metadado(
    *,
    clipe: dict[str, Any],
    id_clipe: int,
    preset_nome: str,
    titulo: str,
    inicio: float,
    fim: float,
    duracao: float,
    destino: Path,
    info: Any,
    reframe: dict[str, Any],
    legenda: dict[str, Any],
    segundos_encode: float,
    fronteiras: Fronteiras,
    estilo: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A entrada de metadados.json de um clipe -- encodado agora ou reaproveitado.

    Uma funcao so para os dois caminhos: se o clipe reaproveitado descrevesse
    campos diferentes do recem-encodado, metadados.json passaria a depender de
    QUANDO cada linha foi escrita.
    """
    try:
        bytes_arquivo = int(destino.stat().st_size)
    except OSError:
        bytes_arquivo = 0
    return {
        "id": int(id_clipe),
        "preset": preset_nome,
        "arquivo": f"clips/{destino.name}",
        "inicio": round(inicio, 3),
        "fim": round(fim, 3),
        "duracao": round(duracao, 3),
        "inicio_mmss": mmss(inicio),
        "fim_mmss": mmss(fim),
        "titulo": titulo,
        "score_0_10": clipe.get("score_0_10"),
        "motivo": clipe.get("motivo"),
        "gancho_sugerido": clipe.get("gancho_sugerido"),
        "texto": str(clipe.get("texto") or fronteiras.texto_entre(inicio, fim)),
        "reframe": reframe,
        "legenda": legenda,
        "estilo": estilo or {},
        "render": {
            "largura": int(info.largura),
            "altura": int(info.altura),
            "duracao_real": round(float(info.duracao), 3),
            "bytes": bytes_arquivo,
            "segundos_encode": round(float(segundos_encode), 1),
        },
    }


def impressao_legenda(preset_obj: Preset) -> str:
    """Identidade da METADE de legenda do preset (fonte, cores, margens, pop).

    A impressao da composicao cobre so o bloco "composicao". Sem esta aqui,
    editar a cor de destaque do karaoke -- que e a edicao mais provavel, e
    justamente o item que o dono do projeto aprova olhando -- nao refazia clipe
    nenhum: o nome do preset continuava o mesmo e era so isso que a assinatura
    guardava.
    """
    import dataclasses

    corpo = json.dumps(
        dataclasses.asdict(preset_obj), sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:16]


def _mesmo_estilo(
    anterior: dict[str, Any],
    impressao: str | None,
    *,
    legenda: str | None = None,
    punches: Sequence[float] | None = None,
) -> bool:
    """O mp4 pronto foi feito com ESTE estilo, ESTA legenda e ESTES punch-ins?

    Sem esta pergunta, editar o preset (outra cor, outro raio, outro zoom) e
    repetir o comando devolveria o clipe antigo: o nome do arquivo, o trecho e
    o tamanho em bytes continuam os mesmos, e e so isso que o resto do
    reaproveitamento olha.

    Os tres campos sao comparados SO QUANDO o metadado anterior ja os traz.
    Assim um clipe gravado por uma versao anterior do clipper continua sendo
    reaproveitado ate a primeira edicao de verdade, em vez de todo mundo ter
    que reencodar por causa de um campo novo.
    """
    estilo = anterior.get("estilo")
    estilo = estilo if isinstance(estilo, dict) else {}
    if (estilo.get("impressao") or None) != (impressao or None):
        return False
    if legenda is not None and estilo.get("legenda_impressao"):
        if str(estilo["legenda_impressao"]) != legenda:
            return False
    if punches is not None and "punch_em" in estilo:
        anteriores = estilo.get("punch_em")
        if not isinstance(anteriores, list):
            return False
        if [round(float(p), 3) for p in anteriores] != [round(float(p), 3) for p in punches]:
            return False
    return True


def _clipe_reaproveitavel(
    destino: Path,
    duracao: float,
    *,
    inicio: float,
    fim: float,
    anterior: dict[str, Any] | None,
    impressao_estilo: str | None = None,
    impressao_legenda_atual: str | None = None,
    punches: Sequence[float] | None = None,
) -> Any:
    """InfoMidia do mp4 que ja esta pronto e valido, ou None se precisa encodar.

    Reaproveitar um mp4 e uma afirmacao forte: "este arquivo E o clipe pedido".
    O nome do arquivo nao prova isso -- ele so carrega id, titulo e preset, e
    dois trechos DIFERENTES podem compartilhar os tres. Entao o reuso exige o
    metadado da rodada anterior, gravado sob a MESMA impressao de selecao
    (_mesclar_clipes ja descarta o de selecao antiga), e exige que ele descreva
    o mesmo trecho e o mesmo tamanho em bytes:

      - sem metadado anterior            -> encoda (nada prova o que o arquivo e)
      - inicio/fim diferentes            -> encoda (a selecao mudou o trecho)
      - tamanho em bytes diferente       -> encoda (o arquivo mudou por fora:
                                            copia interrompida, sincronizacao
                                            de nuvem, disco com erro)

    O ultimo ponto tambem fecha o furo do arquivo TRUNCADO: com
    -movflags +faststart o moov fica no comeco, entao o ffprobe continua
    anunciando 1080x1920 e a duracao certa mesmo num arquivo cortado pela
    metade. O que nao mente e o tamanho que nos mesmos gravamos.
    """
    if not isinstance(anterior, dict):
        return None
    try:
        if not destino.is_file():
            return None
        bytes_agora = destino.stat().st_size
    except OSError:
        return None
    if bytes_agora == 0:
        return None

    if not _mesmo_trecho(anterior, inicio, fim):
        return None

    if not _mesmo_estilo(
        anterior,
        impressao_estilo,
        legenda=impressao_legenda_atual,
        punches=punches,
    ):
        return None

    render_antigo = anterior.get("render")
    render_antigo = render_antigo if isinstance(render_antigo, dict) else {}
    try:
        bytes_antes = int(render_antigo.get("bytes") or 0)
    except (TypeError, ValueError):
        return None
    if bytes_antes <= 0 or bytes_antes != bytes_agora:
        return None

    try:
        info = ffmpeg_utils.sondar(destino)
    except ErroClipper:
        return None
    if info.largura != LARGURA_SAIDA or info.altura != ALTURA_SAIDA:
        return None
    if abs(float(info.duracao) - float(duracao)) > TOLERANCIA_DURACAO_S:
        return None
    return info


def _sufixo_out(saida: Saida) -> str:
    """' --out "<raiz>"' quando a saida nao e a padrao, senao string vazia.

    Comando sugerido sem o --out em uso olharia para out/ do repo e falharia
    com 'nao encontrei nada processado'. A regra do projeto e que a sugestao
    seja executavel como esta escrita.
    """
    from clipper import config as _config

    try:
        raiz = saida.base.parent.resolve()
        if raiz == Path(_config.DIR_SAIDA_PADRAO).resolve():
            return ""
        return f' --out "{raiz}"'
    except OSError:
        return ""


def _mesmo_trecho(anterior: dict[str, Any], inicio: float, fim: float) -> bool:
    """O metadado anterior descreve exatamente este trecho da linha do tempo?"""
    try:
        return (
            abs(float(anterior.get("inicio")) - float(inicio)) <= 1e-3
            and abs(float(anterior.get("fim")) - float(fim)) <= 1e-3
        )
    except (TypeError, ValueError):
        return False


def _erro_do_ffmpeg(exc: ErroFFmpeg, preset_nome: str) -> ErroRender:
    """Re-etiqueta a falha do ffmpeg com a sugestao que a saida real pede.

    Antes, TODA falha de render saia sugerindo instalar fonte -- porque a
    sugestao era passada de cima e 'rodar()' usa 'sugestao or <padrao>'. Quem
    ficasse sem espaco em disco lia um conselho sobre fontconfig.
    """
    detalhe = str(exc.detalhe or "")
    baixo = detalhe.lower()
    if "fontconfig" in baixo or "font" in baixo:
        sugestao = (
            f"o preset '{preset_nome}' pede uma fonte que não está instalada nesta "
            "máquina: escolha outro preset (clipper render <entrada> --preset "
            "clean-branco) ou instale a fonte."
        )
    elif "no space" in baixo or "disk full" in baixo or "errno 28" in baixo:
        sugestao = (
            "faltou espaço em disco no meio do encode. Libere espaço e repita o mesmo "
            "comando — os clipes que já ficaram prontos são reaproveitados."
        )
    elif "permission" in baixo or "access is denied" in baixo:
        sugestao = (
            "algum arquivo desta pasta está aberto em outro programa. Feche-o e repita "
            "o mesmo comando."
        )
    else:
        sugestao = (
            "leia a saída do ffmpeg acima: ela costuma dizer exatamente o que faltou. "
            "O comando completo ficou registrado no clipper.log desta pasta."
        )
    return ErroRender(exc.mensagem, detalhe=detalhe, sugestao=sugestao)


def _renderizar_clipe(
    *,
    saida: Saida,
    clipe: dict[str, Any],
    id_clipe: int,
    preset_nome: str,
    preset_obj: Preset,
    fronteiras: Fronteiras,
    fonte: Path,
    largura_fonte: int,
    altura_fonte: int,
    forcar: bool = False,
    anterior: dict[str, Any] | None = None,
    comp: composicao.Composicao | None = None,
    picos: Sequence[Any] = (),
    fps_fracao: str = "",
    pitch: bool = False,
    tem_audio: bool = True,
) -> dict[str, Any]:
    """Reframe -> ASS -> ffmpeg -> sondagem do resultado. Devolve o metadado.

    Antes de tudo confere se o mp4 de destino ja esta pronto e valido: nesse
    caso nao ha o que reencodar, e o metadado da rodada anterior (quando
    existe) e reaproveitado inteiro. E o que faz alternar entre render completo
    e '--clipe N' custar segundos em vez de minutos.
    """
    log = obter()
    # `inicio` e `fim` sao o SPAN do clipe (min e max da uniao). Num clipe v1
    # eles SAO o corte; num v2 o material entre segmentos foi removido, e a
    # duracao real e a SOMA dos segmentos, nao o span.
    segmentos = [
        {"inicio": float(s["inicio"]), "fim": float(s["fim"])}
        for s in (clipe.get("segmentos") or [])
    ]
    inicio = float(clipe["inicio"])
    fim = float(clipe["fim"])
    if segmentos:
        duracao = sum(s["fim"] - s["inicio"] for s in segmentos)
    else:
        duracao = max(0.0, fim - inicio)
    titulo = str(clipe.get("titulo") or f"clipe {id_clipe}")

    destino = (saida.clips_dir / _nome_arquivo(id_clipe, titulo, preset_nome)).resolve()
    destino.parent.mkdir(parents=True, exist_ok=True)

    impressao_estilo = comp.impressao(pitch=pitch) if comp is not None else None
    marca_legenda = impressao_legenda(preset_obj)
    # Os punch-ins saem de energia.json, que nao entra em assinatura nenhuma:
    # escolher a lista ANTES de decidir o reaproveitamento e o que faz um clipe
    # rendido sem energia legivel voltar a ganhar punch quando a energia
    # aparece. E python puro sobre a lista de picos -- custa microssegundos.
    punches = (
        composicao.escolher_punches(picos, inicio, fim, comp) if comp is not None else []
    )
    if segmentos and punches:
        # `escolher_punches` devolve instantes contados do inicio do SPAN, mas
        # o clipe concatenado nao tem span nenhum -- ele tem a soma. Converto
        # de volta para tempo da fonte e dali para o tempo do clipe. Punch que
        # caiu na gordura removida morre: soco de zoom no lugar errado e pior
        # que soco nenhum.
        absolutos = [inicio + p for p in punches]
        punches = composicao.remapear_tempos(absolutos, segmentos)
    pronto = (
        None
        if forcar
        else _clipe_reaproveitavel(
            destino,
            duracao,
            inicio=inicio,
            fim=fim,
            anterior=anterior,
            impressao_estilo=impressao_estilo,
            impressao_legenda_atual=marca_legenda,
            punches=punches if comp is not None else None,
        )
    )
    if pronto is not None and anterior:
        log.info(
            f"      clipe {id_clipe}: mp4 já pronto, reaproveitando "
            f"({destino.name}, {humanizar_bytes(destino.stat().st_size)})."
        )
        # O metadado antigo e artefato nosso, mas pode ter sido editado a mao:
        # o que nao vier no formato esperado entra vazio, nunca explode.
        antigo_render = anterior.get("render")
        antigo_render = antigo_render if isinstance(antigo_render, dict) else {}
        try:
            segundos_antes = float(antigo_render.get("segundos_encode") or 0.0)
        except (TypeError, ValueError):
            segundos_antes = 0.0
        return _item_metadado(
            clipe=clipe,
            id_clipe=id_clipe,
            preset_nome=preset_nome,
            titulo=titulo,
            inicio=inicio,
            fim=fim,
            duracao=duracao,
            destino=destino,
            info=pronto,
            reframe=(
                anterior["reframe"] if isinstance(anterior.get("reframe"), dict) else {}
            ),
            legenda=(
                anterior["legenda"] if isinstance(anterior.get("legenda"), dict) else {}
            ),
            segundos_encode=segundos_antes,
            fronteiras=fronteiras,
            estilo=(
                anterior["estilo"] if isinstance(anterior.get("estilo"), dict) else {}
            ),
        )

    reframe = calcular_reframe(
        fonte,
        inicio,
        duracao,
        saida.trabalho_dir,
        largura_fonte,
        altura_fonte,
        id_clipe=id_clipe,
        trechos=[(s["inicio"], s["fim"]) for s in segmentos] or None,
    )

    if segmentos:
        palavras: list[dict[str, Any]] = []
        for s in segmentos:
            palavras.extend(fronteiras.palavras_entre(s["inicio"], s["fim"]))
    else:
        palavras = fronteiras.palavras_entre(inicio, fim)
    texto_ass, resumo = legendas.montar_ass(
        palavras,
        preset=preset_obj,
        inicio=inicio,
        fim=fim,
        largura=LARGURA_SAIDA,
        altura=ALTURA_SAIDA,
        segmentos=segmentos or None,
    )
    arquivo_ass = saida.trabalho_dir / f"legenda_{id_clipe}_{preset_nome}.ass"
    _gravar_ass(arquivo_ass, texto_ass)

    tem_legenda = int(resumo["palavras"]) > 0
    if tem_legenda:
        detalhe_pop = (
            f", pop {resumo['pop']}%" if int(resumo.get("pop") or 0) else ""
        )
        log.info(
            f"      legenda: {resumo['linhas']} linha(s), {resumo['palavras']} "
            f"palavra(s), preset {preset_nome}{detalhe_pop} "
            f"(quebra por {resumo.get('quebra')})."
        )
    else:
        log.warning(
            "      aviso:  não há palavra transcrita dentro deste trecho — o clipe "
            "sai SEM legenda. (Trecho de música, silêncio ou fala não reconhecida.)"
        )

    # O filtro 'subtitles' recebe so o NOME do arquivo e o ffmpeg roda com cwd
    # na pasta dele: caminho do Windows com ':' e '\' nao sobrevive aos tres
    # parsers do filtergraph. Por isso 'fonte' e 'destino' sao absolutos.
    cwd: Path | None = None
    filtro_sub = None
    if tem_legenda:
        filtro_sub, cwd = ffmpeg_utils.opcao_subtitles(arquivo_ass)

    estilo: dict[str, Any] = {}
    montagem: composicao.Montagem | None = None
    if comp is not None:
        if not fps_fracao:
            raise ErroRender(
                "não consegui ler a taxa de quadros exata de fonte.mp4, e o preset "
                f"'{preset_nome}' precisa dela para o movimento de câmera.",
                sugestao=(
                    "refaça a ingestão para gravar um fonte.mp4 íntegro:  "
                    f"clipper ingest <entrada> {_FLAG_FORCE}   — ou renderize com um "
                    "preset sem composição (--preset bold-amarelo)."
                ),
            )
        # O gancho e o novo dono do slot do topo. Ele ja chegava ate aqui --
        # metadados.json e relatorio.md sempre o carregaram --, so nunca tinha
        # virado pixel. Quem decide entre gancho e titulo e gerar_ativos(),
        # pelo `gancho.ativo` do modelo.
        ativos = composicao.gerar_ativos(
            comp,
            titulo,
            saida.trabalho_dir,
            gancho=str(clipe.get("gancho_sugerido") or ""),
            conclusao=str(clipe.get("conclusao") or ""),
        )
        montagem = composicao.montar(
            entradas_video=max(1, len(segmentos)),
            comp=comp,
            ativos=ativos,
            recorte=reframe,
            duracao=duracao,
            fps=fps_fracao,
            punches=punches,
            filtro_legenda=filtro_sub,
            tem_audio=tem_audio,
            pitch=pitch,
        )
        pilula = ativos.get("pilula") or {}
        estilo = {
            "preset": preset_nome,
            "versao": composicao.VERSAO,
            "impressao": impressao_estilo,
            "legenda_impressao": marca_legenda,
            "cartao": [comp.cartao_largura, comp.cartao_altura, comp.cartao_x, comp.cartao_y],
            "kenburns": [1.0, round(comp.kenburns_ate, 4)],
            "punch_em": punches,
            "punch_ganho": comp.punch_ganho,
            "punch_duracao": comp.punch_duracao,
            "punch_inicio_minimo": comp.punch_inicio_minimo,
            "fps": fps_fracao,
            "pitch": bool(pitch),
            "titulo_linhas": int(pilula.get("linhas") or 0),
            "titulo_tamanho": int(pilula.get("tamanho") or 0),
            "titulo_truncado": bool(pilula.get("truncado")),
        }
        if punches:
            log.info(
                "      movimento: zoom 1,00→"
                f"{comp.kenburns_ate:.2f} ao longo do clipe e "
                f"{len(punches)} punch-in(s) de +{comp.punch_ganho * 100:.0f}% em "
                + ", ".join(f"{p:.1f}s" for p in punches)
                + "."
            )
        else:
            log.info(
                f"      movimento: zoom 1,00→{comp.kenburns_ate:.2f} ao longo do clipe, "
                "sem punch-in (nenhum pico de áudio elegível neste trecho)."
            )
        if pilula.get("truncado"):
            log.warning(
                "      aviso:  o título não coube na barra e foi cortado com reticências."
            )
    else:
        estilo = {"legenda_impressao": marca_legenda}
        # Caminho F3: recorte cheio, legenda por cima, nada mais.
        # setsar=1 no fim da cadeia geometrica, sempre. Um recorte de 1920x1080
        # sai 608x1080 (o ideal, 607,5, nao e inteiro), e o scale empurra essa
        # sobra para o sample aspect ratio: sem o setsar o mp4 anuncia 1080x1920
        # mas grava SAR 1216:1215 / DAR 76:135, e todo player que honra o SAR
        # reamostra.
        vf = (
            f"crop={reframe['largura']}:{reframe['altura']}:{reframe['x']}:{reframe['y']},"
            f"scale={LARGURA_SAIDA}:{ALTURA_SAIDA}:flags=lanczos,setsar=1"
        )
        if filtro_sub:
            vf += "," + filtro_sub

    if pronto is not None:
        # O mp4 esta pronto e valido, mas nao havia metadado anterior para ele
        # (metadados.json apagado, por exemplo): o reframe/legenda acabou de ser
        # recalculado, e so o encode -- a parte cara -- e que foi poupado.
        log.info(
            f"      clipe {id_clipe}: mp4 já pronto, reaproveitando "
            f"({destino.name}, {humanizar_bytes(destino.stat().st_size)})."
        )
        info = pronto
        segundos_encode = 0.0
    else:
        # Encode ATOMICO: escreve em <destino>.parcial, sonda, e so entao
        # renomeia. Ctrl+C, disco cheio ou ffmpeg morto no meio nao podem
        # deixar um mp4 truncado em clips/ passando por clipe pronto -- ele
        # tem tamanho > 0 e passaria em qualquer checagem de existencia.
        # O que este try NAO cobre: MATAR o processo. No Windows o ffmpeg filho
        # sobrevive ao pai e termina de escrever o .parcial. Quem limpa esse
        # caso e _limpar_parciais(), no comeco do estagio.
        parcial = destino.with_name(destino.name + ".parcial")
        crono = Cronometro(f"render do clipe {id_clipe}")
        try:
            _apagar_silencioso(parcial)
            # 'fonte' e 'parcial' absolutos por obrigacao: o cwd do processo
            # passa a ser a pasta do .ass, e um caminho relativo cairia la
            # dentro. '-f mp4' e obrigatorio porque a extensao .parcial nao
            # diz nada ao ffmpeg sobre o formato de saida.
            if segmentos:
                # Uma entrada por segmento, cada uma com o SEU '-ss'/'-t'. O
                # seek de entrada continua sendo o rapido, e o concat acontece
                # dentro do filtergraph -- decodificar do zero e cortar com
                # 'trim' custaria a leitura do video inteiro por segmento.
                args = []
                for s in segmentos:
                    args += [
                        "-ss", f"{s['inicio']:.3f}",
                        "-t", f"{s['fim'] - s['inicio']:.3f}",
                        "-i", str(fonte),
                    ]
            else:
                args = ["-ss", f"{inicio:.3f}", "-t", f"{duracao:.3f}", "-i", str(fonte)]
            if montagem is not None:
                args.extend(montagem.entradas)
                args.extend(["-filter_complex", montagem.filtro])
                args.extend(["-map", montagem.rotulo_video])
                if montagem.rotulo_audio:
                    args.extend(["-map", montagem.rotulo_audio])
                # O '-t' de SAIDA nao e redundante: a pilula do titulo entra
                # como '-loop 1', que e uma entrada INFINITA, e nem o '-shortest'
                # segura o render de um clipe de um minuto para sempre.
                args.extend(["-t", f"{duracao:.3f}"])
            else:
                args.extend(["-vf", vf])
            args.extend([
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p", "-profile:v", "high",
                "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-ar", "48000",
                "-movflags", "+faststart",
                "-f", "mp4",
                str(parcial),
            ])
            with crono:
                try:
                    ffmpeg_utils.rodar(
                        args,
                        descricao=f"render do clipe {id_clipe}",
                        cwd=cwd,
                    )
                except ErroFFmpeg as exc:
                    raise _erro_do_ffmpeg(exc, preset_nome) from exc
            info = ffmpeg_utils.sondar(parcial)
            if parcial.stat().st_size == 0 or not info.tem_video:
                raise ErroRender(
                    f"o encode do clipe {id_clipe} terminou, mas o arquivo saiu sem "
                    "vídeo legível.",
                    sugestao=(
                        "pode ter faltado espaço em disco. Libere espaço e repita o mesmo "
                        "comando — os clipes que já ficaram prontos são reaproveitados."
                    ),
                )
            try:
                parcial.replace(destino)
            except OSError as exc:
                raise _erro_de_escrita(
                    destino,
                    exc,
                    o_que=f"o clipe {destino.name}",
                    sugestao=(
                        "feche o player ou o Explorer que está com esse arquivo aberto "
                        "(ou libere espaço em disco) e repita o mesmo comando — os clipes "
                        "que já ficaram prontos são reaproveitados."
                    ),
                ) from exc
        except BaseException:
            # BaseException de proposito: KeyboardInterrupt tambem tem que
            # levar o .parcial embora.
            _apagar_silencioso(parcial)
            raise
        segundos_encode = crono.segundos

    bytes_arquivo = destino.stat().st_size
    if not info.tem_audio:
        log.warning(
            f"      aviso:  o clipe {id_clipe} saiu sem faixa de áudio; confira o "
            "áudio da fonte nesse trecho."
        )
    log.info(
        f"      pronto: {destino.name} — {info.largura}x{info.altura}, "
        f"{info.duracao:.1f}s, {humanizar_bytes(bytes_arquivo)}, "
        f"encode em {humanizar_tempo(segundos_encode)}."
    )

    # ---- pacote de publicacao (P3) ------------------------------------
    # Roda TAMBEM para clipe reaproveitado: quem apagou a capa sem apagar o
    # mp4 recebe a capa de volta na proxima rodada, sem reencodar um minuto
    # de video para isso.
    capa_destino = destino.with_suffix(".capa.jpg")
    if not capa_destino.is_file():
        _gravar_capa(destino, _instante_da_capa(clipe, segmentos, duracao), capa_destino)
    capa_rel = f"clips/{capa_destino.name}" if capa_destino.is_file() else None

    publicacao = destino.with_suffix(".publicacao.md")
    try:
        _escrever_texto(
            publicacao,
            montar_publicacao(
                clipe,
                titulo=titulo,
                arquivo_mp4=f"clips/{destino.name}",
                capa=capa_rel,
                duracao=duracao,
                segmentos=segmentos,
            ),
        )
    except OSError as exc:
        log.warning(f"      aviso:  não consegui gravar {publicacao.name}: {exc}")

    return _item_metadado(
        clipe=clipe,
        id_clipe=id_clipe,
        preset_nome=preset_nome,
        titulo=titulo,
        inicio=inicio,
        fim=fim,
        duracao=duracao,
        destino=destino,
        info=info,
        reframe=reframe,
        legenda={
            "preset": preset_nome,
            "linhas": int(resumo["linhas"]),
            "palavras": int(resumo["palavras"]),
            "menor_k_centis": int(resumo["menor_k_centis"]),
            "pop": int(resumo.get("pop") or 0),
            "quebra": str(resumo.get("quebra") or ""),
        },
        segundos_encode=segundos_encode,
        fronteiras=fronteiras,
        estilo=estilo,
    )


# ==========================================================================
# Metadados e relatorio
# ==========================================================================


def _corpo_metadados(
    saida: Saida,
    *,
    todos: list[dict[str, Any]],
    bloco_selecao: dict[str, Any],
    info_fonte: Any,
) -> dict[str, Any]:
    """O dicionario de metadados.json. Um lugar so, usado no parcial e no fim."""
    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "slug": saida.slug,
        "selecao": bloco_selecao,
        "fonte": {
            "largura": info_fonte.largura,
            "altura": info_fonte.altura,
            "fps": round(info_fonte.fps, 3),
            "duracao": round(info_fonte.duracao, 3),
        },
        "saida": {"largura": LARGURA_SAIDA, "altura": ALTURA_SAIDA},
        "presets_usados": sorted({str(c.get("preset")) for c in todos if c.get("preset")}),
        "clipes": todos,
    }


def _salvar_metadados_parcial(
    saida: Saida,
    *,
    anteriores: list[dict[str, Any]],
    itens: list[dict[str, Any]],
    bloco_anterior: Any,
    bloco_selecao: dict[str, Any],
    info_fonte: Any,
) -> None:
    """Grava metadados.json com o que ja ficou pronto. Falha aqui nao interrompe.

    E melhor esforco de proposito: a gravacao que VALE e a do fim do estagio, e
    e ela que levanta erro acionavel se o disco estiver cheio. Esta aqui existe
    so para que um clipe ja encodado nao se perca no meio do caminho.
    """
    try:
        todos = _mesclar_clipes(
            anteriores,
            itens,
            selecao_anterior=bloco_anterior,
            selecao_atual=bloco_selecao,
        )
        escrever_json(
            saida.metadados_json,
            _corpo_metadados(
                saida, todos=todos, bloco_selecao=bloco_selecao, info_fonte=info_fonte
            ),
        )
    except (OSError, ValueError, TypeError):
        return


def _metadados_anteriores(saida: Saida) -> dict[str, Any]:
    """Le metadados.json antigo (se houver) para preservar outros presets."""
    if not saida.metadados_json.is_file():
        return {}
    try:
        dados = ler_json(saida.metadados_json)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _mesclar_clipes(
    anteriores: Iterable[Any],
    novos: list[dict[str, Any]],
    *,
    selecao_anterior: Any = None,
    selecao_atual: Any = None,
) -> list[dict[str, Any]]:
    """Junta o que acabou de sair com o que ja existia de OUTRAS renderizacoes.

    A chave e o par (id, preset): renderizar o mesmo clipe no mesmo preset
    substitui a entrada; noutro preset acrescenta, porque os dois arquivos
    coexistem em clips/.

    Mas so DENTRO DA MESMA SELECAO. O 'id' e reaproveitado entre selecoes, entao
    manter entradas de uma selecao anterior faria o mesmo id descrever dois
    trechos e dois titulos incompativeis -- e 'presets_usados' anunciaria preset
    sem nenhum clipe vigente. Impressao diferente: descarta tudo o que era de
    antes.
    """
    if selecao_anterior != selecao_atual:
        anteriores = []
    chaves_novas = {(c["id"], c["preset"]) for c in novos}
    mantidos = [
        c
        for c in anteriores
        if isinstance(c, dict) and (c.get("id"), c.get("preset")) not in chaves_novas
    ]
    juntos = mantidos + novos
    juntos.sort(key=lambda c: (int(c.get("id") or 0), str(c.get("preset") or "")))
    return juntos


def _cortar_texto(texto: str, limite: int = _LIMITE_TEXTO_RELATORIO) -> str:
    texto = " ".join(str(texto or "").split())
    if len(texto) <= limite:
        return texto
    return texto[:limite].rstrip() + "…"


def _linha_reframe(reframe: dict[str, Any]) -> str:
    fracao = float(reframe.get("fracao") or 0.0)
    com = reframe.get("com_rosto", 0)
    total = reframe.get("amostras", 0)
    if str(reframe.get("modo")) == "vertical":
        return (
            f"a fonte já é vertical → corte de faixas em cima e embaixo, largura "
            f"inteira: crop {reframe.get('largura')}×{reframe.get('altura')} em "
            f"y={reframe.get('y')} (sem detecção de rosto: não há coluna a escolher)"
        )
    if str(reframe.get("modo")) == "rosto":
        return (
            f"recorte guiado por rosto ({com}/{total} amostras com rosto = "
            f"{fracao * 100:.0f}%), centro em {float(reframe.get('mediana_x_norm', 0.5)):.3f} "
            f"da largura → crop {reframe.get('largura')}×{reframe.get('altura')} "
            f"em x={reframe.get('x')}"
        )
    return (
        f"recorte central ({com}/{total} amostras com rosto = {fracao * 100:.0f}%, "
        f"abaixo do mínimo de {FRACAO_MINIMA_ROSTOS * 100:.0f}%) → crop "
        f"{reframe.get('largura')}×{reframe.get('altura')} em x={reframe.get('x')}"
    )


def _ordem_ranking(item: dict[str, Any]) -> tuple[float, int, str]:
    """Score decrescente; empate desempata por id crescente, depois preset."""
    try:
        score = float(item.get("score_0_10") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    return (-score, int(item.get("id") or 0), str(item.get("preset") or ""))


def _montar_relatorio(
    *,
    titulo_video: str,
    fonte_duracao: float,
    presets: Sequence[str],
    itens: list[dict[str, Any]],
) -> str:
    """Markdown ranqueado por score: o melhor clipe primeiro, sempre.

    'itens' e a lista MESCLADA (tudo o que existe em clips/ sob a selecao
    vigente), nunca so os clipes desta rodada: um '--clipe 2' que reescrevesse
    o relatorio com uma linha so apagaria o ranking dos outros quatro, enquanto
    metadados.json continuaria listando os cinco.
    """
    ranking = sorted(itens, key=_ordem_ranking)
    somada = sum(float(c.get("duracao") or 0.0) for c in ranking)
    bytes_total = sum(int((c.get("render") or {}).get("bytes") or 0) for c in ranking)
    lista_presets = [str(p) for p in presets if str(p)]

    linhas: list[str] = []
    linhas.append(f"# Clipes de “{titulo_video}”")
    linhas.append("")
    linhas.append(f"- **Vídeo de origem:** {titulo_video}")
    linhas.append(f"- **Duração da fonte:** {humanizar_tempo(fonte_duracao)}")
    linhas.append(
        "- **Presets de legenda:** "
        + (", ".join(f"`{p}`" for p in lista_presets) if lista_presets else "—")
    )
    linhas.append(f"- **Clipes renderizados:** {len(ranking)}")
    linhas.append(
        f"- **Duração somada:** {humanizar_tempo(somada)} "
        f"({humanizar_bytes(bytes_total)} em disco)"
    )
    linhas.append(f"- **Formato de saída:** {LARGURA_SAIDA}×{ALTURA_SAIDA} (9:16)")
    linhas.append("")
    linhas.append("## Ranking")
    linhas.append("")
    linhas.append("| # | id | preset | trecho | duração | score | título | arquivo |")
    linhas.append("|---|----|--------|--------|---------|-------|--------|---------|")
    for posicao, item in enumerate(ranking, 1):
        score = item.get("score_0_10")
        score_txt = f"{float(score):.1f}" if score is not None else "—"
        linhas.append(
            f"| {posicao} | {item.get('id')} | `{item.get('preset')}` | "
            f"{item.get('inicio_mmss')}–"
            f"{item.get('fim_mmss')} | {float(item.get('duracao') or 0.0):.0f}s | "
            f"{score_txt} | {item.get('titulo')} | `{item.get('arquivo')}` |"
        )
    linhas.append("")

    for posicao, item in enumerate(ranking, 1):
        score = item.get("score_0_10")
        score_txt = f"{float(score):.1f}" if score is not None else "—"
        render = item.get("render") or {}
        linhas.append(
            f"## {posicao}. Clipe {item.get('id')} — {item.get('titulo')} "
            f"(score {score_txt}, preset `{item.get('preset')}`)"
        )
        linhas.append("")
        linhas.append(
            f"- **Trecho:** {item.get('inicio_mmss')}–{item.get('fim_mmss')} "
            f"({float(item.get('duracao') or 0.0):.1f}s)"
        )
        gancho = item.get("gancho_sugerido")
        if gancho:
            linhas.append(f"- **Gancho sugerido:** “{gancho}”")
        motivo = item.get("motivo")
        if motivo:
            linhas.append(f"- **Por que este trecho:** {motivo}")
        linhas.append(f"- **Enquadramento:** {_linha_reframe(item.get('reframe') or {})}")
        estilo = item.get("estilo") or {}
        if estilo.get("impressao"):
            zoom = estilo.get("kenburns") or [1.0, 1.0]
            punches = estilo.get("punch_em") or []
            texto_punch = (
                ", ".join(f"{float(p):.1f}s" for p in punches)
                if punches
                else "nenhum (sem pico de áudio elegível)"
            )
            linhas.append(
                f"- **Composição:** cartão {estilo.get('cartao', [0, 0])[0]}×"
                f"{estilo.get('cartao', [0, 0])[1]} sobre fundo borrado, zoom "
                f"{float(zoom[0]):.2f}→{float(zoom[-1]):.2f}, punch-in de "
                f"+{float(estilo.get('punch_ganho') or 0) * 100:.0f}% em: {texto_punch}"
                + (" — áudio com pitch +0,5%" if estilo.get("pitch") else "")
            )
        legenda = item.get("legenda") or {}
        if int(legenda.get("palavras") or 0) > 0:
            linhas.append(
                f"- **Legenda:** {legenda.get('linhas')} linha(s), "
                f"{legenda.get('palavras')} palavra(s), preset `{legenda.get('preset')}`"
            )
        else:
            linhas.append(
                "- **Legenda:** nenhuma (não há fala transcrita dentro do trecho)"
            )
        linhas.append(
            f"- **Arquivo:** `{item.get('arquivo')}` — "
            f"{humanizar_bytes(int(render.get('bytes') or 0))}, "
            f"{render.get('largura')}×{render.get('altura')}, "
            f"{float(render.get('duracao_real') or 0.0):.1f}s"
        )
        linhas.append("")
        linhas.append(f"> {_cortar_texto(item.get('texto') or '')}")
        linhas.append("")

    linhas.append("---")
    linhas.append("")
    linhas.append("## Limitações conhecidas desta versão")
    linhas.append("")
    linhas.append(
        "- **Reenquadramento estático.** Cada clipe recebe UM recorte, calculado "
        "uma vez a partir da mediana das amostras e mantido do começo ao fim. O "
        "clipper não segue o rosto ao longo do tempo: se a pessoa atravessa o "
        "quadro no meio do trecho, ela sai do enquadramento. É de propósito — um "
        "recorte que persegue o rosto treme e cansa de assistir."
    )
    linhas.append(
        "- **Corte em fronteira de frase.** O início e o fim de cada clipe caem "
        "no começo e no fim de frases inteiras, nunca no meio de uma palavra. Em "
        "troca disso, sobra 1–2 s de respiro nas pontas (a pausa antes da "
        "primeira palavra e depois da última). Se quiser um corte mais seco, "
        "apare as pontas no editor."
    )
    linhas.append("")
    return "\n".join(linhas)


# ==========================================================================
# Estagio
# ==========================================================================


def _titulo_do_video(saida: Saida) -> str:
    try:
        fonte = ler_json(saida.fonte_info_json)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return saida.slug
    if isinstance(fonte, dict):
        origem = fonte.get("origem")
        if isinstance(origem, dict):
            titulo = str(origem.get("titulo") or "").strip()
            if titulo:
                return titulo
    return saida.slug


def _arquivos_no_lugar(saida: Saida, preset: str, ids: list[int]) -> bool:
    """Confere se os mp4 descritos no metadados ainda existem em clips/.

    Os artefatos declarados sao metadados.json e relatorio.md, mas apagar um
    clipe de clips/ e repetir o comando tem que reproduzi-lo -- senao o
    usuario fica preso num estado "concluido" sem o arquivo.
    """
    dados = _metadados_anteriores(saida)
    clipes = dados.get("clipes")
    if not isinstance(clipes, list):
        return False
    por_id = {
        int(c.get("id")): c
        for c in clipes
        if isinstance(c, dict) and c.get("preset") == preset and c.get("id") is not None
    }
    for id_clipe in ids:
        item = por_id.get(id_clipe)
        if not item:
            return False
        alvo = saida.base / str(item.get("arquivo") or "")
        if not alvo.is_file() or alvo.stat().st_size == 0:
            return False
    return True


def _avisar_orfaos(saida: Saida, todos: list[dict[str, Any]]) -> list[str]:
    """Aponta os mp4 de clips/ que nao pertencem mais a nenhuma entrada atual.

    O nome do arquivo embute o slug do TITULO, entao trocar a selecao (ou so o
    titulo de um clipe) deixa o arquivo anterior no disco, com o mesmo prefixo
    'NN-' do atual e sem nenhuma referencia. Quem olha a pasta para publicar nao
    tem como saber qual e o vigente.

    So AVISA. Sao arquivos do usuario, dentro da pasta de entrega dele: apagar
    por conta propria seria apagar o render que ele talvez tenha guardado de
    proposito.
    """
    log = obter()
    esperados = {
        str(c.get("arquivo") or "").replace("\\", "/").rsplit("/", 1)[-1] for c in todos
    }
    try:
        presentes = sorted(p.name for p in saida.clips_dir.glob("*.mp4") if p.is_file())
    except OSError:
        return []
    orfaos = [
        nome
        for nome in presentes
        if _PADRAO_NOME_CLIPE.match(nome) and nome not in esperados
    ]
    if not orfaos:
        return []
    log.warning(
        f"   aviso:  {len(orfaos)} arquivo(s) em {saida.clips_dir.name}/ não pertencem "
        "a nenhum clipe da seleção atual:"
    )
    for nome in orfaos:
        log.warning(f"             - {nome}")
    log.warning(
        "           São de uma seleção ou de um título anteriores. O clipper não apaga "
        "arquivo seu: confira e remova à mão se não precisar mais deles."
    )
    return orfaos


def _limpar_parciais(saida: Saida) -> None:
    """Apaga .parcial de um render interrompido. Nunca levanta.

    O encode e atomico (escreve em .parcial e so entao renomeia), e o Ctrl+C
    esta coberto pelo try/except do proprio encode. O que NAO estava: matar o
    processo. No Windows o ffmpeg filho sobrevive ao pai, termina o encode e
    deixa um .parcial completo de dezenas de MB em clips/ -- que _avisar_orfaos
    nao lista, porque ele so olha *.mp4, e que so seria apagado se aquele mesmo
    clipe fosse reencodado.
    """
    log = obter()
    for parcial in sorted(saida.clips_dir.glob("*.parcial")):
        try:
            tamanho = parcial.stat().st_size
            parcial.unlink()
            log.info(
                f"   apaguei {parcial.name} ({humanizar_bytes(tamanho)}): sobra de um "
                "render interrompido."
            )
        except OSError:
            continue


def _picos_de_energia(saida: Saida) -> list[Any]:
    """Os picos de energia.json, ou lista vazia se ele nao existir/estiver torto.

    Energia ausente NAO e erro de render: o clipe sai com o Ken Burns e sem
    punch-in. Exigir energia.json aqui quebraria o 'render' de um projeto
    antigo, que e justamente o comando que funciona offline.
    """
    try:
        dados = ler_json(saida.energia_json)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(dados, dict):
        return []
    picos = dados.get("picos")
    return [p for p in picos if isinstance(p, dict)] if isinstance(picos, list) else []


def renderizar(
    saida: Saida,
    estado: Estado,
    *,
    preset: str = PRESET_PADRAO,
    forcar: bool = False,
    clipes: list[int] | None = None,
    pitch: bool = False,
) -> dict[str, Any]:
    """Corta, reenquadra em 9:16, queima legenda e grava clips/ + relatorio.md.

    'clipes' None significa todos os da seleção; uma lista de ids renderiza
    apenas eles (útil para revisar um clipe sem reencodar os outros cinco).
    """
    log = obter()
    saida.criar_dirs()
    _exigir_entradas(saida)

    preset_obj = carregar_preset(preset)
    comp = carregar_composicao(preset)
    selecao = _ler_entrada(saida.selecao_json, "a seleção")
    lista = _clipes_da_selecao(selecao, saida.selecao_json)
    escolhidos = _filtrar_clipes(lista, clipes)
    # Antes de qualquer encode: um campo torto nao pode aparecer no meio da
    # fila, depois de minutos gastos nos clipes anteriores.
    _validar_clipes(escolhidos, saida.selecao_json)
    ids = sorted(int(c.get("id", i + 1)) for i, c in enumerate(escolhidos))

    # A assinatura NAO guarda quais clipes foram pedidos: isso e a forma do
    # pedido, e alternar entre render completo e '--clipe N' invalidaria o
    # registro mesmo com todos os mp4 intactos. O que existe pronto em disco e
    # decidido clipe a clipe, la no encode.
    impressao = _impressao_selecao(saida)
    assinatura: dict[str, Any] = {
        "preset": preset,
        "largura": LARGURA_SAIDA,
        "altura": ALTURA_SAIDA,
        # O estilo entra na assinatura para que editar o preset -- e nao apenas
        # trocar de preset -- refaca os clipes sozinho, sem --force.
        "estilo": comp.impressao(pitch=pitch) if comp is not None else None,
        "pitch": bool(pitch),
        **impressao,
        **_impressao_transcricao(saida),
        **(_impressao_energia(saida) if comp is not None else {}),
    }
    artefatos = [saida.metadados_json, saida.relatorio_md]

    if not forcar and estado.concluido(ESTAGIO, assinatura, artefatos):
        if _arquivos_no_lugar(saida, preset, ids):
            extra = estado.extra(ESTAGIO)
            log.info(
                f"   os clipes já estão prontos no preset '{preset}' com esta mesma "
                f"seleção; pulando (use {_FLAG_FORCE} para renderizar de novo)."
            )
            return {
                "clipes": extra.get("clipes", len(ids)),
                "preset": extra.get("preset", preset),
                "duracao_total": extra.get("duracao_total", 0.0),
                "bytes_total": extra.get("bytes_total", 0),
                "reaproveitado": True,
            }
        log.info(
            "   o estado diz que o render está feito, mas falta arquivo em "
            f"{saida.clips_dir.name}/ — vou refazer os clipes."
        )

    _limpar_parciais(saida)

    transcricao = _ler_entrada(saida.transcricao_json, "a transcrição")
    if not isinstance(transcricao, dict):
        raise ErroRender(
            "transcricao.json não tem o formato esperado.",
            sugestao=f"refaça:  clipper transcribe <entrada> {_FLAG_FORCE}",
        )
    try:
        fronteiras = Fronteiras.de_transcricao(transcricao)
    except ErroClipper as exc:
        # A transcricao e boa o bastante para a selecao ou nao e; aqui o erro
        # vem do estagio errado, entao ele e reetiquetado como erro de render.
        raise ErroRender(exc.mensagem, sugestao=exc.sugestao, detalhe=exc.detalhe) from exc

    fonte = saida.fonte_mp4.resolve()
    info_fonte = ffmpeg_utils.sondar(fonte)
    if not info_fonte.tem_video or info_fonte.largura <= 0 or info_fonte.altura <= 0:
        raise ErroRender(
            f"{fonte.name} não tem faixa de vídeo legível "
            f"({info_fonte.largura}x{info_fonte.altura}).",
            sugestao=f'refaça a ingestão:  clipper ingest <entrada> {_FLAG_FORCE}',
        )

    picos = _picos_de_energia(saida) if comp is not None else []
    log.info(
        f"   fonte {info_fonte.largura}×{info_fonte.altura} @ {info_fonte.fps:.2f} fps, "
        f"{humanizar_tempo(info_fonte.duracao)} — saída {LARGURA_SAIDA}×{ALTURA_SAIDA}, "
        f"preset '{preset}'."
    )
    if comp is not None:
        log.info(
            f"   composição '{preset}': cartão {comp.cartao_largura}×{comp.cartao_altura} "
            f"em ({comp.cartao_x},{comp.cartao_y}) sobre fundo borrado, "
            f"{len(picos)} pico(s) de áudio no vídeo inteiro para escolher os punch-ins"
            + (", áudio com pitch +0,5%" if pitch else "")
            + "."
        )
        if not picos:
            log.info(
                "   (sem energia.json legível: os clipes saem com o zoom contínuo e "
                "sem punch-in — o resto da composição não muda.)"
            )
    log.info(
        f"   {len(escolhidos)} clipe(s) para renderizar; o encode é em CPU, "
        "conte alguns minutos."
    )

    # Metadados anteriores: servem para reaproveitar a descricao de um clipe
    # cujo mp4 ja esta pronto -- mas so se vierem da MESMA selecao.
    anteriores = _metadados_anteriores(saida)
    bloco_selecao = _bloco_selecao(impressao)
    bloco_anterior = anteriores.get("selecao")
    if not isinstance(bloco_anterior, dict):
        bloco_anterior = None
    clipes_anteriores = [
        c for c in (anteriores.get("clipes") or []) if isinstance(c, dict)
    ]
    mesma_selecao = bloco_anterior == bloco_selecao
    if clipes_anteriores and not mesma_selecao:
        log.info(
            f"   metadados.json trazia {len(clipes_anteriores)} clipe(s) de uma seleção "
            "anterior; eles saem da lista (os ids são reaproveitados entre seleções)."
        )
    por_chave: dict[tuple[int, str], dict[str, Any]] = {}
    if mesma_selecao:
        for item_antigo in clipes_anteriores:
            id_antigo = _id_seguro(item_antigo.get("id"))
            if id_antigo is not None:
                por_chave[(id_antigo, str(item_antigo.get("preset") or ""))] = item_antigo

    itens: list[dict[str, Any]] = []
    crono = Cronometro(ESTAGIO)
    with crono:
        for posicao, clipe in enumerate(escolhidos, 1):
            id_clipe = int(clipe.get("id", posicao))
            titulo = str(clipe.get("titulo") or f"clipe {id_clipe}")
            inicio = float(clipe["inicio"])
            fim = float(clipe["fim"])
            log.info("")
            log.info(
                f"   [{posicao}/{len(escolhidos)}] clipe {id_clipe} — {titulo} "
                f"({mmss(inicio)}–{mmss(fim)}, {fim - inicio:.0f}s)"
            )
            item = _renderizar_clipe(
                saida=saida,
                clipe=clipe,
                id_clipe=id_clipe,
                preset_nome=preset,
                preset_obj=preset_obj,
                fronteiras=fronteiras,
                fonte=fonte,
                largura_fonte=info_fonte.largura,
                altura_fonte=info_fonte.altura,
                forcar=forcar,
                anterior=por_chave.get((id_clipe, preset)),
                comp=comp,
                picos=picos,
                fps_fracao=info_fonte.fps_fracao,
                pitch=pitch,
                tem_audio=info_fonte.tem_audio,
            )
            itens.append(item)
            # Grava o que ja existe a cada clipe. Sem isto, uma falha na
            # gravacao final (disco cheio, arquivo aberto) deixava os clipes
            # recem-encodados sem metadado nenhum -- e repetir o comando
            # reencodava tudo de novo, ao contrario do que a mensagem promete.
            _salvar_metadados_parcial(
                saida,
                anteriores=clipes_anteriores,
                itens=itens,
                bloco_anterior=bloco_anterior,
                bloco_selecao=bloco_selecao,
                info_fonte=info_fonte,
            )

    todos = _mesclar_clipes(
        clipes_anteriores,
        itens,
        selecao_anterior=bloco_anterior,
        selecao_atual=bloco_selecao,
    )
    presets_usados = sorted({str(c.get("preset")) for c in todos if c.get("preset")})

    metadados = _corpo_metadados(
        saida, todos=todos, bloco_selecao=bloco_selecao, info_fonte=info_fonte
    )
    # Daqui para baixo os clipes JA estao gravados: disco cheio ou arquivo
    # aberto em outro programa e falha previsivel, com conserto obvio -- e
    # repetir o comando agora custa segundos, porque os mp4 sao reaproveitados.
    conserto = (
        f"os clipes já estão em {saida.clips_dir} — só faltou este arquivo. Feche o "
        "programa que está com ele aberto (ou libere espaço em disco) e repita:  "
        f'clipper render "{saida.slug}" --preset {preset}{_sufixo_out(saida)}   '
        "(os mp4 prontos são reaproveitados, então a repetição leva segundos)"
    )
    try:
        escrever_json(saida.metadados_json, metadados)
    except OSError as exc:
        raise _erro_de_escrita(
            saida.metadados_json, exc, o_que="o metadados.json", sugestao=conserto
        ) from exc

    _avisar_orfaos(saida, todos)

    relatorio = _montar_relatorio(
        titulo_video=_titulo_do_video(saida),
        fonte_duracao=info_fonte.duracao,
        presets=presets_usados,
        itens=todos,
    )
    tmp = saida.relatorio_md.with_name(saida.relatorio_md.name + ".tmp")
    try:
        tmp.write_text(relatorio, encoding="utf-8", newline="\n")
        tmp.replace(saida.relatorio_md)
    except OSError as exc:
        raise _erro_de_escrita(
            saida.relatorio_md, exc, o_que="o relatorio.md", sugestao=conserto
        ) from exc

    duracao_total = round(sum(float(c["duracao"]) for c in itens), 2)
    bytes_total = int(sum(int(c["render"]["bytes"]) for c in itens))
    resumo = {
        "clipes": len(itens),
        "preset": preset,
        "duracao_total": duracao_total,
        "bytes_total": bytes_total,
    }
    estado.marcar(ESTAGIO, assinatura, segundos=crono.segundos, extra=resumo)

    log.info("")
    log.info(
        f"   {len(itens)} clipe(s) renderizado(s) em {humanizar_tempo(crono.segundos)} — "
        f"{humanizar_tempo(duracao_total)} de vídeo, {humanizar_bytes(bytes_total)} em "
        f"{saida.clips_dir}."
    )
    log.info(f"   relatório em {saida.relatorio_md}")
    return {**resumo, "reaproveitado": False}
