"""Estagio 2: transcricao (faster-whisper) + curva de energia do audio.

Duas responsabilidades, ambas idempotentes, ambas alimentando as fases
seguintes:

  transcrever()      -> transcricao.json + transcricao.srt
  calcular_energia() -> energia.json

Alem dos segmentos, a transcricao grava uma lista PLANA de palavras com
indice global: a F2 usa isso para encaixar cortes em fronteira de frase e a
F3 usa para a legenda karaoke palavra a palavra.

Convencao deste arquivo: comentarios e docstrings em PT-BR sem acento;
mensagens dirigidas ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import math
import os
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from clipper.config import Estado, Saida, escrever_json, humanizar_tempo
from clipper.erros import ErroTranscricao
from clipper.ffmpeg_utils import sondar
from clipper.registro import obter

ESTAGIO_TRANSCRICAO = "transcricao"
ESTAGIO_ENERGIA = "energia"

# Quanto tempo de relogio custa 1 s de audio na CPU, por familia de modelo.
# Medido/estimado para CPU desktop de 6 nucleos com compute_type int8.
_FATORES_CPU: dict[str, tuple[float, float]] = {
    "tiny": (0.05, 0.09),
    "base": (0.09, 0.15),
    "small": (0.17, 0.25),
    "medium": (0.50, 0.70),
    "large": (1.20, 1.80),
}

# Tamanho aproximado do download na primeira vez, por familia de modelo.
_TAMANHOS_MODELO: dict[str, str] = {
    "tiny": "~75 MB",
    "base": "~145 MB",
    "small": "~500 MB",
    "medium": "~1,5 GB",
    "large": "~3 GB",
}

_MAX_PICOS = 200

# Menor duracao que uma palavra pode ter na transcricao final, em segundos.
# 60 ms = 6 centissegundos, a unidade do \k do ASS: da para o olho ver o
# realce acender.
_DURACAO_MINIMA_PALAVRA = 0.06
_PISO_DBFS = -80.0
_RMS_MINIMO = 1e-4  # 20*log10(1e-4) == -80 dBFS
_BLOCO_SEGUNDOS = 60.0  # leitura do wav em pedacos, para nao carregar 1h de uma vez

# Grafia UNICA da flag de reprocessamento em toda mensagem ao usuario.
# O parser do cli registra "--force"; "--forcar" nao existe e o argparse recusa
# (nem cai na abreviacao, porque divergem no 5o caractere). Toda sugestao deste
# arquivo deve sair daqui, para que a renomear a flag nada fique desatualizado.
_FLAG_FORCE = "--force"


# ---------------------------------------------------------------- utilidades


def _num(valor: Any, padrao: float = 0.0) -> float:
    """float() tolerante: None, texto invalido, NaN e inf viram o padrao."""
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return padrao
    if math.isnan(f) or math.isinf(f):
        return padrao
    return f


def _mmss(segundos: float) -> str:
    total = int(max(0.0, _num(segundos)))
    return f"{total // 60:02d}:{total % 60:02d}"


def _ts_srt(segundos: float) -> str:
    """Formata 'HH:MM:SS,mmm' como manda o SRT (virgula, nao ponto)."""
    ms_total = int(round(max(0.0, _num(segundos)) * 1000.0))
    horas, resto = divmod(ms_total, 3_600_000)
    minutos, resto = divmod(resto, 60_000)
    seg, ms = divmod(resto, 1000)
    return f"{horas:02d}:{minutos:02d}:{seg:02d},{ms:03d}"


def _escrever_texto(caminho: Path, conteudo: str) -> Path:
    """Escrita atomica em utf-8 sem BOM, quebras \\n (espelha config.escrever_json)."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(conteudo, encoding="utf-8", newline="\n")
    tmp.replace(caminho)
    return caminho


def _familia(modelo: str) -> str:
    nome = str(modelo).lower()
    for chave in ("large", "medium", "small", "base", "tiny"):
        if chave in nome:
            return chave
    return "medium"


def _fator_cpu(modelo: str) -> tuple[float, float]:
    return _FATORES_CPU[_familia(modelo)]


def _minutos(segundos: float) -> int:
    return max(1, int(round(max(0.0, segundos) / 60.0)))


def _faixa_tempo(baixo_s: float, alto_s: float) -> str:
    """'~30 a ~45 minutos' para estimativas longas; segundos quando for curto."""
    if alto_s < 120.0:
        return f"~{humanizar_tempo(baixo_s)} a ~{humanizar_tempo(alto_s)}"
    return f"~{_minutos(baixo_s)} a ~{_minutos(alto_s)} minutos"


def _exigir_audio(saida: Saida) -> Path:
    caminho = saida.audio_wav
    if not caminho.exists() or caminho.stat().st_size == 0:
        raise ErroTranscricao(
            f"não encontrei o áudio extraído em {caminho}.",
            sugestao=(
                "rode a ingestão primeiro:  clipper ingest <arquivo-ou-url>  "
                "(ela é quem gera fonte.mp4 e audio.wav em "
                f"{saida.base})."
            ),
        )
    return caminho


def _impressao_audio(saida: Saida) -> dict[str, Any]:
    """Identidade do audio.wav, para entrar na assinatura de idempotencia.

    Transcricao e energia leem audio.wav, entao a identidade DELE faz parte dos
    parametros do estagio: sem isso, dois videos diferentes com o mesmo nome
    caem no mesmo out/<slug>/ e o segundo reaproveita a transcricao do primeiro.
    Com bytes+mtime a cascata se resolve sozinha: a ingestao reescreve o wav e
    os dois estagios se invalidam sem orquestracao no cli.

    Se o wav nao existe, devolve {}: a assinatura fica diferente da gravada, o
    estagio nao e pulado e _exigir_audio da a mensagem certa logo em seguida.
    """
    try:
        st = saida.audio_wav.stat()
    except OSError:
        return {}
    return {"audio_bytes": int(st.st_size), "audio_mtime": int(st.st_mtime)}


def _duracao_audio(caminho: Path) -> float:
    """Duracao real do wav. Tenta ffprobe; cai para o cabecalho do proprio wav."""
    try:
        duracao = _num(sondar(caminho).duracao)
        if duracao > 0:
            return duracao
    except Exception:  # ffprobe ausente/quebrado nao pode derrubar a transcricao
        obter().debug("ffprobe falhou ao sondar o audio; usando o cabecalho do wav.")
    try:
        with wave.open(str(caminho), "rb") as wav:
            taxa = wav.getframerate()
            if taxa > 0:
                return wav.getnframes() / float(taxa)
    except (wave.Error, OSError, EOFError):
        pass
    return 0.0


class _Progresso:
    """Progresso legivel no console E no arquivo de log (por isso, sem tqdm).

    Imprime no maximo a cada 2% de avanco OU a cada 15 s de relogio, o que
    vier primeiro, com posicao no audio e ETA pelo ritmo medido ate agora.
    """

    def __init__(self, total_s: float, rotulo: str = "transcrevendo") -> None:
        self.total = max(0.001, _num(total_s))
        self.rotulo = rotulo
        self.log = obter()
        self.t0 = time.perf_counter()
        self._ultimo_pct = -100.0
        self._ultimo_relogio = self.t0

    def atualizar(self, posicao_s: float) -> None:
        agora = time.perf_counter()
        pct = min(100.0, max(0.0, _num(posicao_s) / self.total * 100.0))
        if pct - self._ultimo_pct < 2.0 and agora - self._ultimo_relogio < 15.0:
            return
        self._ultimo_pct = pct
        self._ultimo_relogio = agora
        self._imprimir(pct, posicao_s, agora)

    def concluir(self, posicao_s: float) -> float:
        agora = time.perf_counter()
        if self._ultimo_pct < 99.5:  # nao repete a linha quando ja bateu 100%
            self._imprimir(100.0, posicao_s, agora, final=True)
        return agora - self.t0

    def _imprimir(self, pct: float, posicao_s: float, agora: float, final: bool = False) -> None:
        decorrido = agora - self.t0
        posicao = max(0.0, _num(posicao_s))
        if final:
            cauda = f"levou {humanizar_tempo(decorrido)}"
        elif posicao > 1.0 and decorrido > 1.0:
            eta = decorrido * (self.total - posicao) / posicao
            cauda = f"faltam ~{humanizar_tempo(max(0.0, eta))}"
        else:
            cauda = "calculando o tempo restante..."
        self.log.info(
            f"   {self.rotulo} {pct:5.1f}%  "
            f"{_mmss(posicao)}/{_mmss(self.total)}  {cauda}"
        )


# ------------------------------------------------------------------ hardware


def detectar_dispositivo() -> tuple[str, str]:
    """Devolve (device, compute_type): CUDA quando ha GPU NVIDIA, senao CPU int8."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception as exc:  # sem ctranslate2, sem driver, sem CUDA: cai para CPU
        obter().debug(f"deteccao de GPU falhou ({type(exc).__name__}: {exc}); usando CPU.")
    return "cpu", "int8"


# --------------------------------------------------------------- transcricao


def escrever_srt(transcricao: dict[str, Any], destino: Path) -> Path:
    """Gera o SRT classico a partir dos SEGMENTOS (nao das palavras)."""
    destino = Path(destino)
    linhas: list[str] = []
    indice = 1
    for seg in transcricao.get("segmentos") or []:
        texto = str(seg.get("texto") or "").strip()
        if not texto:
            continue
        inicio = _num(seg.get("inicio"))
        fim = _num(seg.get("fim"))
        if fim <= inicio:
            fim = inicio + 0.05  # legenda de duracao zero/negativa nao renderiza
        linhas.append(str(indice))
        linhas.append(f"{_ts_srt(inicio)} --> {_ts_srt(fim)}")
        linhas.append(texto)
        linhas.append("")
        indice += 1
    # o join deixaria o arquivo sem o \n final; o SRT quer a linha em branco
    return _escrever_texto(destino, ("\n".join(linhas) + "\n") if linhas else "")


def _carregar_modelo(modelo: str, device: str, compute_type: str, cpu_threads: int) -> Any:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ErroTranscricao(
            "o pacote faster-whisper não está instalado neste ambiente.",
            detalhe=str(exc),
            sugestao=(
                "instale as dependências do projeto:  "
                ".venv\\Scripts\\python.exe -m pip install -r requirements.txt"
            ),
        ) from None

    cache = (
        os.environ.get("HUGGINGFACE_HUB_CACHE")
        or os.environ.get("HF_HOME")
        or "%USERPROFILE%\\.cache\\huggingface"
    )
    try:
        return WhisperModel(
            modelo,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
        )
    except Exception as exc:
        raise ErroTranscricao(
            f"não consegui carregar o modelo Whisper '{modelo}'.",
            detalhe=f"{type(exc).__name__}: {exc}",
            sugestao=(
                "o modelo é baixado UMA única vez (~1,5 GB no caso do 'medium') e depois "
                f"fica em cache em {cache} (controlado por HF_HOME / HUGGINGFACE_HUB_CACHE). "
                "Então: confira a conexão de internet, confira o espaço livre em disco e "
                "confira se o nome do modelo existe (tiny/base/small/medium/large-v3). "
                "Se a rede ou o disco estiverem apertados, tente  --modelo-whisper small  "
                "(~500 MB e cerca de 1/3 do tempo)."
            ),
        ) from None


def _garantir_duracao_minima(
    planas: list[dict[str, Any]],
    segmentos: list[dict[str, Any]],
    duracao_audio: float,
) -> int:
    """Tira as palavras de duracao zero que o faster-whisper devolve.

    Na primeira palavra depois de um corte do VAD o modelo costuma entregar
    start == end. Palavra de duracao zero vira 0 centissegundos no \\k do ASS:
    a legenda karaoke da F3 simplesmente NUNCA acende aquela palavra, e no
    corte da F2 ela e uma fronteira de largura nula. Damos a ela o menor tempo
    visivel que caiba antes da palavra seguinte, sem furar a ordem.

    Mexe nas duas copias (lista plana e palavras de cada segmento), que andam
    na mesma ordem, para os dois artefatos nao divergirem.
    """
    referencias = [w for s in segmentos for w in s["palavras"]]
    total = len(planas)
    ajustadas = 0
    for k, palavra in enumerate(planas):
        if palavra["fim"] > palavra["inicio"]:
            continue
        if k + 1 < total:
            limite = planas[k + 1]["inicio"]
        else:
            limite = max(duracao_audio, palavra["inicio"])
        novo_fim = min(palavra["inicio"] + _DURACAO_MINIMA_PALAVRA, limite)
        if novo_fim <= palavra["inicio"] and k + 1 < total:
            # A proxima palavra comeca no mesmo instante: nao ha folga a tomar.
            # Em vez de sobrepor as duas (o que faria o karaoke da F3 contar o
            # mesmo tempo duas vezes), pegamos emprestado do inicio da proxima,
            # desde que ela continue com duracao propria.
            proxima = planas[k + 1]
            folga = proxima["fim"] - proxima["inicio"]
            # Dividir a folga ao meio em vez de exigir que a proxima palavra
            # fique com o minimo inteiro: quando ela propria dura so o minimo
            # (60 ms), exigir isso zeraria o emprestimo e a unica saida seria
            # sobrepor. Meio a meio da 30 ms a cada uma -- visivel nas duas.
            emprestimo = min(_DURACAO_MINIMA_PALAVRA, folga / 2.0)
            if emprestimo >= 0.01:
                novo_fim = round(palavra["inicio"] + emprestimo, 3)
                proxima["inicio"] = novo_fim
                if k + 1 < len(referencias):
                    referencias[k + 1]["inicio"] = novo_fim
        if novo_fim <= palavra["inicio"]:
            # Ultimo recurso (proxima palavra tambem e curtissima): 10 ms de
            # sobreposicao ainda e melhor que uma palavra que nunca acende.
            novo_fim = palavra["inicio"] + 0.01
        novo_fim = round(novo_fim, 3)
        palavra["fim"] = novo_fim
        if k < len(referencias):
            referencias[k]["fim"] = novo_fim
        # Se o ultimo recurso invadiu a proxima palavra (acontece quando ela
        # tambem veio zerada, no mesmo instante), empurra o inicio dela. Como
        # o laco anda em ordem, ela sera consertada na propria iteracao caso
        # isso a deixe sem duracao.
        if k + 1 < total and planas[k + 1]["inicio"] < novo_fim:
            planas[k + 1]["inicio"] = novo_fim
            if k + 1 < len(referencias):
                referencias[k + 1]["inicio"] = novo_fim
        ajustadas += 1
    return ajustadas


def transcrever(
    saida: Saida,
    estado: Estado,
    *,
    modelo: str = "medium",
    idioma: str = "pt",
    forcar: bool = False,
    threads: int | None = None,
    vad: bool = True,
) -> dict[str, Any]:
    """Transcreve audio.wav com faster-whisper e grava transcricao.json/.srt."""
    log = obter()
    device, compute_type = detectar_dispositivo()
    assinatura = {
        "modelo": modelo,
        "idioma": idioma,
        "vad": vad,
        "device": device,
        "compute_type": compute_type,
        # identidade do audio de entrada: audio novo => transcricao nova
        **_impressao_audio(saida),
    }
    artefatos = [saida.transcricao_json, saida.transcricao_srt]

    if not forcar and estado.concluido(ESTAGIO_TRANSCRICAO, assinatura, artefatos):
        log.info(
            "   transcrição já existe com os mesmos parâmetros e o mesmo áudio; "
            f"pulando (use {_FLAG_FORCE} para refazer)."
        )
        resumo = dict(estado.extra(ESTAGIO_TRANSCRICAO))
        resumo["reaproveitado"] = True
        return resumo

    audio = _exigir_audio(saida)
    saida.criar_dirs()

    duracao = _duracao_audio(audio)
    cpu_threads = int(threads or os.cpu_count() or 4)

    if device == "cpu":
        lo, hi = _fator_cpu(modelo)
        log.info(f"   dispositivo: CPU ({compute_type}), {cpu_threads} threads — sem GPU NVIDIA.")
        if duracao > 0:
            log.warning(
                f"   Atenção: na CPU isso demora. {humanizar_tempo(duracao)} de áudio com o "
                f"modelo '{modelo}' devem levar {_faixa_tempo(duracao * lo, duracao * hi)} "
                f"nesta máquina (fator {lo:.2f}x–{hi:.2f}x da duração do áudio)."
            )
        else:
            log.warning(
                f"   Atenção: na CPU isso demora — espere de {lo:.2f}x a {hi:.2f}x a duração "
                f"do áudio com o modelo '{modelo}'."
            )
        slo, shi = _FATORES_CPU["small"]
        if lo > slo:
            extra = f" ({_faixa_tempo(duracao * slo, duracao * shi)})" if duracao > 0 else ""
            log.warning(
                f"   Se quiser cerca de 1/3 desse tempo{extra}, com um pouco menos de "
                "precisão, use  --modelo-whisper small."
            )
        log.warning("   Pode deixar rodando: o progresso é impresso abaixo e vai para o log.")
    else:
        log.info(f"   dispositivo: {device} ({compute_type}).")

    log.info(
        f"   carregando o modelo Whisper '{modelo}' "
        f"(na primeira vez ele é baixado, {_TAMANHOS_MODELO[_familia(modelo)]})..."
    )
    modelo_obj = _carregar_modelo(modelo, device, compute_type, cpu_threads)

    t0 = time.perf_counter()
    try:
        segmentos_iter, info = modelo_obj.transcribe(
            str(audio),
            language=idioma,
            word_timestamps=True,
            vad_filter=vad,
            beam_size=5,
            # condition_on_previous_text=False corta a alucinacao em loop que o
            # whisper produz em audio longo de PT-BR.
            condition_on_previous_text=False,
        )
    except Exception as exc:
        raise ErroTranscricao(
            "o faster-whisper não conseguiu iniciar a transcrição do áudio.",
            detalhe=f"{type(exc).__name__}: {exc}",
            sugestao=(
                "confira se o áudio está íntegro abrindo "
                f"{audio} num player; se estiver corrompido, refaça a ingestão com "
                f"clipper ingest <arquivo> {_FLAG_FORCE}."
            ),
        ) from None

    if duracao <= 0:
        duracao = _num(getattr(info, "duration", 0.0))

    segmentos: list[dict[str, Any]] = []
    palavras_planas: list[dict[str, Any]] = []
    correcoes = 0
    sem_palavras = 0
    indice_global = 0
    ultimo_fim = 0.0  # monotonicidade GLOBAL, atravessa a fronteira dos segmentos
    posicao = 0.0
    progresso = _Progresso(duracao if duracao > 0 else 1.0)

    try:
        for id_seg, seg in enumerate(segmentos_iter):
            inicio_seg = round(_num(getattr(seg, "start", 0.0)), 3)
            fim_seg = round(_num(getattr(seg, "end", inicio_seg)), 3)
            texto_seg = str(getattr(seg, "text", "") or "").strip()

            palavras_seg: list[dict[str, Any]] = []
            brutas = getattr(seg, "words", None) or []
            if not brutas:
                sem_palavras += 1
            for w in brutas:
                texto_w = str(getattr(w, "word", "") or "").strip()
                if not texto_w:
                    continue  # o whisper devolve tokens so de espaco/pontuacao vazia
                ini_w = round(_num(getattr(w, "start", inicio_seg), inicio_seg), 3)
                fim_w = round(_num(getattr(w, "end", ini_w), ini_w), 3)
                if ini_w < ultimo_fim:
                    ini_w = ultimo_fim
                    correcoes += 1
                if fim_w < ini_w:
                    fim_w = ini_w
                ultimo_fim = fim_w
                prob_bruta = getattr(w, "probability", None)
                prob = round(float(prob_bruta), 4) if prob_bruta is not None else None
                palavras_seg.append(
                    {"inicio": ini_w, "fim": fim_w, "texto": texto_w, "prob": prob}
                )
                palavras_planas.append(
                    {
                        "i": indice_global,
                        "seg": id_seg,
                        "inicio": ini_w,
                        "fim": fim_w,
                        "texto": texto_w,
                        "prob": prob,
                    }
                )
                indice_global += 1

            segmentos.append(
                {
                    "id": id_seg,
                    "inicio": inicio_seg,
                    "fim": fim_seg,
                    "texto": texto_seg,
                    "palavras": palavras_seg,
                }
            )
            posicao = max(posicao, fim_seg)
            progresso.atualizar(posicao)
    except ErroTranscricao:
        raise
    except Exception as exc:
        raise ErroTranscricao(
            "a transcrição foi interrompida por um erro do faster-whisper.",
            detalhe=f"{type(exc).__name__}: {exc}",
            sugestao=(
                "se a mensagem acima fala em memória, feche outros programas ou use "
                "--modelo-whisper small; se fala em áudio/formato, refaça a ingestão com "
                f"clipper ingest <arquivo> {_FLAG_FORCE}."
            ),
        ) from None

    segundos = progresso.concluir(duracao if duracao > 0 else posicao)
    segundos = max(segundos, time.perf_counter() - t0)

    duracao_zerada = _garantir_duracao_minima(palavras_planas, segmentos, duracao)
    if duracao_zerada:
        log.debug(
            f"{duracao_zerada} palavra(s) vieram com duracao zero e ganharam o "
            "minimo visivel."
        )

    if correcoes:
        log.debug(f"monotonicidade: {correcoes} palavra(s) tiveram o início ajustado.")
    if sem_palavras:
        log.debug(f"{sem_palavras} segmento(s) vieram sem timestamps de palavra.")

    if not segmentos or not any(s["texto"] for s in segmentos):
        # com o VAD ligado a causa mais provavel nao e audio mudo, e o proprio
        # filtro engolindo clipe curto/fala baixa: essa dica vem primeiro.
        dica_vad = (
            "tente de novo com  --sem-vad  (o filtro de voz costuma engolir clipe curto "
            "ou fala baixa); se não resolver, "
            if vad
            else ""
        )
        raise ErroTranscricao(
            "o Whisper não encontrou nenhuma fala neste áudio.",
            sugestao=(
                f"{dica_vad}ouça {audio}: se estiver mudo, refaça a ingestão com "
                f"clipper ingest <arquivo> {_FLAG_FORCE}; se tiver fala em outro idioma, "
                "passe  --idioma <código>  (ex.: en)."
            ),
        )

    if duracao <= 0:
        duracao = posicao

    transcricao: dict[str, Any] = {
        "idioma": idioma or str(getattr(info, "language", "") or ""),
        "modelo": modelo,
        "device": device,
        "compute_type": compute_type,
        "duracao_audio": round(duracao, 3),
        "segundos_transcricao": round(segundos, 3),
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "segmentos": segmentos,
        "palavras": palavras_planas,
    }

    escrever_json(saida.transcricao_json, transcricao)
    escrever_srt(transcricao, saida.transcricao_srt)

    resumo: dict[str, Any] = {
        "segmentos": len(segmentos),
        "palavras": len(palavras_planas),
        "duracao_audio": round(duracao, 3),
        "device": device,
        "compute_type": compute_type,
        "modelo": modelo,
        "segundos_transcricao": round(segundos, 3),
        "fator_tempo_real": round(duracao / max(segundos, 1e-6), 3),
    }
    estado.marcar(ESTAGIO_TRANSCRICAO, assinatura, segundos=segundos, extra=resumo)

    log.info(
        f"   {resumo['segmentos']} segmentos e {resumo['palavras']} palavras "
        f"em {humanizar_tempo(segundos)} ({resumo['fator_tempo_real']}x tempo real)."
    )
    log.info(f"   {saida.transcricao_json.name} e {saida.transcricao_srt.name} gravados.")

    return {**resumo, "reaproveitado": False}


# ------------------------------------------------------------------- energia


def _dtype_wav(sampwidth: int, caminho: Path) -> tuple[Any, float, float]:
    """(dtype, divisor, offset) para normalizar as amostras PCM em [-1, 1]."""
    if sampwidth == 1:
        return np.uint8, 128.0, 128.0  # PCM de 8 bits e sem sinal
    if sampwidth == 2:
        return np.int16, 32768.0, 0.0
    if sampwidth == 4:
        return np.int32, 2147483648.0, 0.0
    raise ErroTranscricao(
        f"o áudio {caminho.name} tem {sampwidth * 8} bits por amostra, formato que eu não leio.",
        sugestao=(
            "regere o áudio pela ingestão (ela grava pcm_s16le mono 16 kHz):  "
            f"clipper ingest <arquivo> {_FLAG_FORCE}"
        ),
    )


def _rms_por_janela(caminho: Path, janela_s: float) -> tuple[np.ndarray, float, int]:
    """Le o wav em blocos e devolve (rms por janela, duracao, taxa_amostragem)."""
    log = obter()
    try:
        wav = wave.open(str(caminho), "rb")
    except (wave.Error, OSError, EOFError) as exc:
        raise ErroTranscricao(
            f"não consegui abrir {caminho.name} como WAV PCM.",
            detalhe=f"{type(exc).__name__}: {exc}",
            sugestao=f"refaça a ingestão:  clipper ingest <arquivo> {_FLAG_FORCE}",
        ) from None

    with wav:
        canais = max(1, wav.getnchannels())
        sampwidth = wav.getsampwidth()
        taxa = wav.getframerate()
        nframes = wav.getnframes()
        if taxa <= 0 or nframes <= 0:
            raise ErroTranscricao(
                f"o áudio {caminho.name} está vazio ou com cabeçalho inválido.",
                sugestao=f"refaça a ingestão:  clipper ingest <arquivo> {_FLAG_FORCE}",
            )
        dtype, divisor, offset = _dtype_wav(sampwidth, caminho)

        amostras_janela = max(1, int(round(taxa * janela_s)))
        frames_bloco = max(amostras_janela, int(taxa * _BLOCO_SEGUNDOS))
        # tamanho de um frame completo (todos os canais), em bytes
        tam_frame = max(1, np.dtype(dtype).itemsize * canais)
        avisou_cauda = False
        resto = np.empty(0, dtype=np.float32)
        rms: list[float] = []

        while True:
            try:
                cru = wav.readframes(frames_bloco)
            except (wave.Error, OSError, EOFError) as exc:
                raise ErroTranscricao(
                    f"a leitura de {caminho.name} falhou no meio do arquivo.",
                    detalhe=f"{type(exc).__name__}: {exc}",
                    sugestao=(
                        "o arquivo pode estar truncado; refaça a ingestão com  "
                        f"clipper ingest <arquivo> {_FLAG_FORCE}"
                    ),
                ) from None
            if not cru:
                break
            # wav truncado no meio de um frame devolve bytes de sobra; sem
            # descartar a cauda, np.frombuffer explodiria com ValueError cru.
            sobra = len(cru) % tam_frame
            if sobra:
                if not avisou_cauda:
                    avisou_cauda = True
                    log.warning(
                        f"   Atenção: {caminho.name} termina no meio de um frame "
                        f"(sobraram {sobra} byte(s)); ignorando essa cauda incompleta. "
                        "Se o áudio parecer cortado, refaça a ingestão com  "
                        f"clipper ingest <arquivo> {_FLAG_FORCE}"
                    )
                cru = cru[: len(cru) - sobra]
            if not cru:
                break
            try:
                bloco = np.frombuffer(cru, dtype=dtype).astype(np.float32)
            except ValueError as exc:  # rede de seguranca: buffer nao alinhado
                raise ErroTranscricao(
                    f"a leitura de {caminho.name} encontrou dados de áudio inválidos.",
                    detalhe=f"{type(exc).__name__}: {exc}",
                    sugestao=(
                        "o arquivo pode estar truncado ou corrompido; refaça a ingestão com  "
                        f"clipper ingest <arquivo> {_FLAG_FORCE}"
                    ),
                ) from None
            if offset:
                bloco = bloco - offset
            bloco = bloco / divisor
            if canais > 1:
                # estereo (ou mais): media dos canais, mantendo o eixo do tempo
                bloco = bloco[: (bloco.size // canais) * canais]
                bloco = bloco.reshape(-1, canais).mean(axis=1)
            dados = np.concatenate((resto, bloco)) if resto.size else bloco
            n_completas = dados.size // amostras_janela
            if n_completas:
                cortadas = dados[: n_completas * amostras_janela].reshape(
                    n_completas, amostras_janela
                )
                rms.extend(
                    np.sqrt(np.mean(np.square(cortadas, dtype=np.float64), axis=1)).tolist()
                )
            resto = dados[n_completas * amostras_janela :].copy()

        if resto.size:  # ultima janela parcial ainda conta
            rms.append(float(np.sqrt(np.mean(np.square(resto, dtype=np.float64)))))

    return np.asarray(rms, dtype=np.float64), nframes / float(taxa), taxa


def calcular_energia(
    saida: Saida,
    estado: Estado,
    *,
    janela_s: float = 1.0,
    forcar: bool = False,
) -> dict[str, Any]:
    """Calcula a curva de RMS/dBFS por janela e grava energia.json."""
    log = obter()
    # identidade do audio de entrada na assinatura: audio novo => energia nova
    assinatura = {"janela_s": janela_s, **_impressao_audio(saida)}
    artefatos = [saida.energia_json]

    if not forcar and estado.concluido(ESTAGIO_ENERGIA, assinatura, artefatos):
        log.info(
            "   energia já calculada com os mesmos parâmetros e o mesmo áudio; "
            f"pulando (use {_FLAG_FORCE} para refazer)."
        )
        resumo = dict(estado.extra(ESTAGIO_ENERGIA))
        resumo["reaproveitado"] = True
        return resumo

    if _num(janela_s) <= 0:
        raise ErroTranscricao(
            f"janela de energia inválida: {janela_s}s.",
            sugestao="use um valor positivo, por exemplo 1.0 (padrão) ou 0.5.",
        )

    audio = _exigir_audio(saida)
    saida.criar_dirs()

    t0 = time.perf_counter()
    rms, duracao, taxa = _rms_por_janela(audio, float(janela_s))
    if rms.size == 0:
        raise ErroTranscricao(
            f"não consegui extrair nenhuma janela de energia de {audio.name}.",
            sugestao=f"refaça a ingestão:  clipper ingest <arquivo> {_FLAG_FORCE}",
        )

    p99 = float(np.percentile(rms, 99))
    pico_max = float(rms.max())
    # mudo de verdade e "nenhuma janela tem energia". O p99 zera tambem em audio
    # esparso (99% de silencio digital), e ai normalizar por ele apagaria justo
    # o unico trecho com conteudo.
    mudo = pico_max <= 0.0
    if mudo:
        log.warning(
            "   Atenção: o áudio parece completamente mudo (RMS zero em todas as janelas). "
            f"Confira {audio} antes de seguir para a seleção."
        )
        rms_norm = np.zeros_like(rms)
        picos: list[dict[str, float]] = []
    else:
        ref = p99 if p99 > 0.0 else pico_max
        if p99 <= 0.0:
            log.warning(
                "   Atenção: quase todo o áudio é silêncio digital (99% das janelas com RMS "
                "zero); normalizando pela janela mais alta para não perder o pouco que tem fala."
            )
        rms_norm = np.clip(rms / ref, 0.0, 1.0)
        p90 = float(np.percentile(rms_norm, 90))
        # o "> 0" importa no audio esparso: com p90 == 0 todas as janelas mudas
        # entrariam na lista de picos e afogariam os trechos reais.
        indices = [int(i) for i in np.nonzero((rms_norm >= p90) & (rms_norm > 0.0))[0]]
        if len(indices) > _MAX_PICOS:
            # fica com os mais altos, mas devolve na ordem do tempo
            indices = sorted(indices, key=lambda k: float(rms_norm[k]), reverse=True)[:_MAX_PICOS]
            indices.sort()
        picos = [
            {"t": round(i * float(janela_s), 3), "rms_norm": round(float(rms_norm[i]), 6)}
            for i in indices
        ]

    dbfs = np.maximum(20.0 * np.log10(np.maximum(rms, _RMS_MINIMO)), _PISO_DBFS)

    energia: dict[str, Any] = {
        "janela_s": float(janela_s),
        "duracao_audio": round(duracao, 3),
        "total_janelas": int(rms.size),
        "rms": [round(float(v), 6) for v in rms],
        "rms_norm": [round(float(v), 6) for v in rms_norm],
        "dbfs": [round(float(v), 1) for v in dbfs],
        "picos": picos,
    }
    escrever_json(saida.energia_json, energia)

    segundos = time.perf_counter() - t0
    resumo: dict[str, Any] = {
        "total_janelas": int(rms.size),
        "duracao_audio": round(duracao, 3),
        "picos": len(picos),
    }
    estado.marcar(ESTAGIO_ENERGIA, assinatura, segundos=segundos, extra=resumo)

    log.info(
        f"   {resumo['total_janelas']} janelas de {janela_s}s a {taxa} Hz, "
        f"{resumo['picos']} picos — {saida.energia_json.name} gravado."
    )

    return {**resumo, "reaproveitado": False}
