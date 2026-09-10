"""Estagio 4: render dos clipes verticais 9:16 com legenda karaoke (F3).

O que este modulo faz, em uma frase: pega os trechos ja validados em
selecao.json, decide para ONDE olhar em cada um (reframe), queima a legenda
karaoke do preset escolhido e produz um mp4 1080x1920 por clipe, mais
metadados.json e relatorio.md.

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

import json
import os
import re
import statistics
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from clipper import ffmpeg_utils, legendas
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
from clipper.erros import ErroClipper, ErroRender
from clipper.fronteiras import Fronteiras, mmss
from clipper.legendas import Preset
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

PRESET_PADRAO = "bold-amarelo"

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


def carregar_preset(nome: str) -> Preset:
    """Le clipper/presets/<nome>.json e devolve o Preset da legenda.

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
    try:
        return Preset.de_dict(dados)
    except TypeError as exc:
        # de_dict so repassa os campos conhecidos: TypeError aqui significa
        # que FALTA campo obrigatorio no json.
        esperados = set(Preset.__dataclass_fields__)
        faltando = sorted(esperados - set(dados))
        raise ErroRender(
            f"o preset '{nome}' está incompleto: falta(m) "
            f"{', '.join(faltando) if faltando else 'campo(s) obrigatório(s)'}.",
            detalhe=str(exc),
            sugestao=(
                f"copie {DIR_PRESETS / (PRESET_PADRAO + '.json')} e edite as cores/"
                "tamanhos a partir dele: assim nenhum campo fica de fora."
            ),
        ) from exc


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
) -> dict[str, Any]:
    """Decide o recorte 9:16 de um trecho: rosto quando da, centro quando nao.

    Amostra um frame a cada INTERVALO_AMOSTRA_S em LARGURA CHEIA (reduzir para
    640px zera a deteccao neste tipo de video), procura o maior rosto de cada
    frame e usa a MEDIANA dos centros -- a mediana ignora o frame em que o
    detector se animou com um quadro na parede, coisa que a media nao faria.

    'id_clipe' e opcional so para manter a chamada curta em uso avulso; o
    estagio passa o id real para que as amostras de clipes diferentes nao se
    misturem na pasta de trabalho.
    """
    log = obter()
    fonte = Path(fonte).resolve()
    trabalho = Path(trabalho)
    trabalho.mkdir(parents=True, exist_ok=True)

    marca = int(id_clipe) if id_clipe is not None else int(round(float(inicio) * 1000))
    prefixo = f"crop_{marca}_"
    _limpar_frames(trabalho, prefixo)

    # Fonte ja vertical (ou exatamente 9:16): o corte e em cima/embaixo e o
    # centro horizontal do rosto nao influencia nada. Amostrar e detectar
    # rosto aqui seria minuto de CPU para chegar no mesmo retangulo.
    geo_vertical = _geometria(0.5, int(largura_fonte), int(altura_fonte))
    if geo_vertical["corte"] == "vertical":
        log.info(
            f"      a fonte já é vertical ({int(largura_fonte)}×{int(altura_fonte)}): o "
            "recorte tira faixas em cima e embaixo, mantendo a largura inteira — não há "
            "coluna a escolher, então a detecção de rosto é dispensada."
        )
        return {
            "modo": "vertical",
            "x": geo_vertical["x"],
            "y": geo_vertical["y"],
            "largura": geo_vertical["largura"],
            "altura": geo_vertical["altura"],
            "amostras": 0,
            "com_rosto": 0,
            "fracao": 0.0,
            "mediana_x_norm": 0.5,
        }

    amostras: list[Path] = []
    centros: list[float] = []
    try:
        # A chamada do ffmpeg fica DENTRO do try: um Ctrl+C no meio da
        # amostragem deixaria dezenas de PNG de 1,4 MB em _trabalho/.
        ffmpeg_utils.rodar(
            [
                "-ss", f"{float(inicio):.3f}",
                "-i", str(fonte),
                "-t", f"{float(duracao):.3f}",
                "-vf", f"fps=1/{INTERVALO_AMOSTRA_S}",
                "-q:v", "2",
                str(trabalho / (prefixo + "%03d.png")),
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

    geo = _geometria(centro_final, int(largura_fonte), int(altura_fonte))
    return {
        "modo": modo,
        "x": geo["x"],
        "y": geo["y"],
        "largura": geo["largura"],
        "altura": geo["altura"],
        "amostras": total,
        "com_rosto": len(centros),
        "fracao": round(fracao, 3),
        "mediana_x_norm": round(centro_final, 3),
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
        "render": {
            "largura": int(info.largura),
            "altura": int(info.altura),
            "duracao_real": round(float(info.duracao), 3),
            "bytes": bytes_arquivo,
            "segundos_encode": round(float(segundos_encode), 1),
        },
    }


def _clipe_reaproveitavel(
    destino: Path,
    duracao: float,
    *,
    inicio: float,
    fim: float,
    anterior: dict[str, Any] | None,
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
) -> dict[str, Any]:
    """Reframe -> ASS -> ffmpeg -> sondagem do resultado. Devolve o metadado.

    Antes de tudo confere se o mp4 de destino ja esta pronto e valido: nesse
    caso nao ha o que reencodar, e o metadado da rodada anterior (quando
    existe) e reaproveitado inteiro. E o que faz alternar entre render completo
    e '--clipe N' custar segundos em vez de minutos.
    """
    log = obter()
    inicio = float(clipe["inicio"])
    fim = float(clipe["fim"])
    duracao = max(0.0, fim - inicio)
    titulo = str(clipe.get("titulo") or f"clipe {id_clipe}")

    destino = (saida.clips_dir / _nome_arquivo(id_clipe, titulo, preset_nome)).resolve()
    destino.parent.mkdir(parents=True, exist_ok=True)

    pronto = (
        None
        if forcar
        else _clipe_reaproveitavel(
            destino, duracao, inicio=inicio, fim=fim, anterior=anterior
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
        )

    reframe = calcular_reframe(
        fonte,
        inicio,
        duracao,
        saida.trabalho_dir,
        largura_fonte,
        altura_fonte,
        id_clipe=id_clipe,
    )

    palavras = fronteiras.palavras_entre(inicio, fim)
    texto_ass, resumo = legendas.montar_ass(
        palavras,
        preset=preset_obj,
        inicio=inicio,
        fim=fim,
        largura=LARGURA_SAIDA,
        altura=ALTURA_SAIDA,
    )
    arquivo_ass = saida.trabalho_dir / f"legenda_{id_clipe}_{preset_nome}.ass"
    _gravar_ass(arquivo_ass, texto_ass)

    # setsar=1 no fim da cadeia geometrica, sempre. Um recorte de 1920x1080 sai
    # 608x1080 (o ideal, 607,5, nao e inteiro), e o scale empurra essa sobra
    # para o sample aspect ratio: sem o setsar o mp4 anuncia 1080x1920 mas
    # grava SAR 1216:1215 / DAR 76:135, e todo player que honra o SAR reamostra.
    recorte = (
        f"crop={reframe['largura']}:{reframe['altura']}:{reframe['x']}:{reframe['y']},"
        f"scale={LARGURA_SAIDA}:{ALTURA_SAIDA}:flags=lanczos,setsar=1"
    )
    cwd: Path | None = None
    if int(resumo["palavras"]) > 0:
        filtro_sub, cwd = ffmpeg_utils.opcao_subtitles(arquivo_ass)
        vf = recorte + "," + filtro_sub
        log.info(
            f"      legenda: {resumo['linhas']} linha(s), {resumo['palavras']} "
            f"palavra(s), preset {preset_nome}."
        )
    else:
        vf = recorte
        log.warning(
            "      aviso:  não há palavra transcrita dentro deste trecho — o clipe "
            "sai SEM legenda. (Trecho de música, silêncio ou fala não reconhecida.)"
        )

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
        parcial = destino.with_name(destino.name + ".parcial")
        crono = Cronometro(f"render do clipe {id_clipe}")
        try:
            _apagar_silencioso(parcial)
            # 'fonte' e 'parcial' absolutos por obrigacao: o cwd do processo
            # passa a ser a pasta do .ass, e um caminho relativo cairia la
            # dentro. '-f mp4' e obrigatorio porque a extensao .parcial nao
            # diz nada ao ffmpeg sobre o formato de saida.
            args = [
                "-ss", f"{inicio:.3f}",
                "-i", str(fonte),
                "-t", f"{duracao:.3f}",
                "-vf", vf,
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p", "-profile:v", "high",
                "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-ar", "48000",
                "-movflags", "+faststart",
                "-f", "mp4",
                str(parcial),
            ]
            with crono:
                ffmpeg_utils.rodar(
                    args,
                    descricao=f"render do clipe {id_clipe}",
                    cwd=cwd,
                    sugestao=(
                        "se a mensagem acima fala em fonte/fontconfig, o preset pede uma "
                        "fonte que não está instalada nesta máquina: escolha outro preset "
                        "(clipper render <entrada> --preset clean-branco) ou instale a fonte."
                    ),
                )
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
            parcial.replace(destino)
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
        },
        segundos_encode=segundos_encode,
        fronteiras=fronteiras,
    )


# ==========================================================================
# Metadados e relatorio
# ==========================================================================


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


def renderizar(
    saida: Saida,
    estado: Estado,
    *,
    preset: str = PRESET_PADRAO,
    forcar: bool = False,
    clipes: list[int] | None = None,
) -> dict[str, Any]:
    """Corta, reenquadra em 9:16, queima legenda e grava clips/ + relatorio.md.

    'clipes' None significa todos os da seleção; uma lista de ids renderiza
    apenas eles (útil para revisar um clipe sem reencodar os outros cinco).
    """
    log = obter()
    saida.criar_dirs()
    _exigir_entradas(saida)

    preset_obj = carregar_preset(preset)
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
        **impressao,
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

    log.info(
        f"   fonte {info_fonte.largura}×{info_fonte.altura} @ {info_fonte.fps:.2f} fps, "
        f"{humanizar_tempo(info_fonte.duracao)} — saída {LARGURA_SAIDA}×{ALTURA_SAIDA}, "
        f"preset '{preset}'."
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
            itens.append(
                _renderizar_clipe(
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
                )
            )

    todos = _mesclar_clipes(
        clipes_anteriores,
        itens,
        selecao_anterior=bloco_anterior,
        selecao_atual=bloco_selecao,
    )
    presets_usados = sorted({str(c.get("preset")) for c in todos if c.get("preset")})

    metadados = {
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
        "presets_usados": presets_usados,
        "clipes": todos,
    }
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
