"""Legenda ASS karaoke palavra a palavra.

Por que ASS e nao SRT: o SRT nao sabe acender uma palavra por vez. O efeito
karaoke do ASS (`\\k`) troca a cor de cada silaba no instante certo, e como a
F1 grava a lista PLANA de palavras com timestamp, cada palavra vira uma silaba.

Duas armadilhas que este modulo resolve de proposito:

1. Palavra de duracao zero. O faster-whisper devolve fim == inicio na primeira
   palavra depois de um corte do VAD (118 casos no video de teste, 2,2%).
   `\\k0` significa "nao acende": a palavra ficaria apagada a legenda inteira.
   A F1 ja da a toda palavra um minimo de 60 ms, e aqui o piso e reforcado --
   `_centis()` nunca devolve menos de 1 centissegundo.

2. Sincronia com o audio. O valor de `\\k` de uma palavra nao e a duracao dela,
   e a distancia ate o INICIO da proxima. Usar a duracao deixaria o realce
   adiantado, porque os silencios entre palavras somem. Com a distancia, a
   soma dos `\\k` fecha exatamente com a duracao da linha.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

# Quanto a linha fica na tela depois da ultima palavra, em segundos. Sem isso
# a legenda pisca fora no instante em que a fala acaba.
_SEGURAR_S = 0.35

# Piso absoluto de um \k. 1 centissegundo e o menor valor que ainda acende.
_MINIMO_CENTIS = 1


@dataclass(frozen=True)
class Preset:
    """Aparencia da legenda. Carregado de clipper/presets/<nome>.json."""

    nome: str
    descricao: str
    fonte: str
    tamanho: int
    negrito: bool
    maiusculas: bool
    cor_falada: str
    cor_por_falar: str
    cor_contorno: str
    cor_sombra: str
    contorno: float
    sombra: float
    espacamento: float
    margem_lateral: int
    margem_inferior: int
    max_palavras_linha: int
    max_caracteres_linha: int

    # --- karaoke v2 (F4a). Todos com padrao, e o padrao e "igual a F3": um
    # preset antigo continua gerando exatamente o mesmo ASS de antes.
    # pop_escala 100 = sem pop. cor_destaque vazia = usa cor_falada.
    cor_destaque: str = ""
    pop_escala: int = 100
    pop_subida_ms: int = 90
    pop_descida_ms: int = 120
    pop_volta_ms: int = 90
    # Quebrar linha por LARGURA MEDIDA em vez de contar caractere. Contagem nao
    # preve largura: medido em Impact 96, "GRANDE DIA DE VER ISSO" ocupa 781 px
    # e "METROS QUADRADOS MESMO" ocupa 923 px -- os dois com 22 caracteres, um
    # dentro e o outro fora da area segura do cartao.
    largura_por_medida: bool = False
    arquivo_fonte: str = ""

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> "Preset":
        campos = {f: dados[f] for f in cls.__dataclass_fields__ if f in dados}
        return cls(**campos)

    @property
    def tem_pop(self) -> bool:
        return int(self.pop_escala) != 100

    @property
    def cor_do_pop(self) -> str:
        return self.cor_destaque or self.cor_falada


def _centis(segundos: float) -> int:
    """Converte para centissegundos com piso de 1: \\k0 nunca acende."""
    return max(_MINIMO_CENTIS, int(round(float(segundos) * 100.0)))


def _tempo_ass(segundos: float) -> str:
    """Formato de tempo do ASS: H:MM:SS.cc (centissegundos, dois digitos)."""
    segundos = max(0.0, float(segundos))
    centis = int(round(segundos * 100.0))
    h, resto = divmod(centis, 360000)
    m, resto = divmod(resto, 6000)
    s, cc = divmod(resto, 100)
    return f"{h}:{m:02d}:{s:02d}.{cc:02d}"


def _escapar(texto: str) -> str:
    """Neutraliza o que o parser do ASS trataria como marcacao."""
    return (
        texto.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _largura_visual(texto: str) -> int:
    """Conta caracteres ignorando acentos combinantes (NFD nao infla a conta)."""
    return sum(1 for c in unicodedata.normalize("NFC", texto) if not unicodedata.combining(c))


def _termina_frase(texto: str) -> bool:
    limpo = texto.rstrip("\"'»)]}")
    return bool(limpo) and limpo[-1] in ".!?…"


# Quanto da largura que o Pillow mede vira tinta na tela pelo libass. Medido
# em 14 amostras com Impact 96 (Spacing 1, Outline 7, Shadow 4): a razao ficou
# entre 0,845 e 0,870. O numero e usado para converter o teto de largura da
# area segura em um teto que o Pillow consiga aferir ANTES de renderizar.
_FATOR_LIBASS = 0.858


def _medidor(preset: Preset) -> Any:
    """Funcao que mede a largura de um texto na fonte do preset, ou None.

    Mede o texto COMO ELE VAI PARA A TELA (em caixa alta, se o preset pedir):
    "metros quadrados" e "METROS QUADRADOS" nao tem a mesma largura.

    Import tardio e falha silenciosa de proposito: medir e uma MELHORIA da
    quebra de linha, nao um requisito. Sem Pillow ou sem a fonte instalada, a
    legenda continua saindo pela contagem de caracteres, como na F3.
    """
    if not preset.largura_por_medida:
        return None
    try:
        from clipper.composicao import _fonte  # import tardio: Pillow

        fonte = _fonte(preset.fonte, preset.arquivo_fonte, int(preset.tamanho))
    except Exception:  # noqa: BLE001 - medir nunca pode derrubar o render
        return None

    def medir(texto: str) -> float:
        alvo = str(texto).upper() if preset.maiusculas else str(texto)
        try:
            return float(fonte.getlength(alvo))
        except Exception:  # noqa: BLE001
            return 0.0

    return medir


def teto_de_largura(preset: Preset, largura_canvas: int = 1080) -> float:
    """Maior largura (em unidades do Pillow) que uma linha pode ter.

    Sai da area segura do proprio preset: a caixa util e o canvas menos as duas
    margens laterais; dela saem o contorno e a sombra, que sao tinta alem do
    glifo; e o que sobra ainda tem que caber COM a palavra em pop, que estica a
    linha inteira -- o libass remede e recentraliza a cada quadro.
    """
    util = max(80.0, float(largura_canvas) - 2.0 * float(preset.margem_lateral))
    util -= 2.0 * (float(preset.contorno) + float(preset.sombra))
    if preset.tem_pop:
        util /= max(1.0, float(preset.pop_escala) / 100.0)
    return max(40.0, util / _FATOR_LIBASS)


def agrupar_linhas(
    palavras: Sequence[dict[str, Any]],
    *,
    max_palavras: int,
    max_caracteres: int,
    medidor: Any = None,
    teto: float = 0.0,
) -> list[list[dict[str, Any]]]:
    """Quebra a sequencia de palavras em linhas curtas de legenda.

    Regras, na ordem: fecha a linha no fim de frase (ponto final e uma pausa
    natural, quebrar ali le melhor), ao atingir o numero maximo de palavras, ou
    ao estourar a largura. Linhas curtas sao de proposito -- em video vertical
    o leitor tem fracoes de segundo, e uma linha longa ainda esbarraria na
    coluna de botoes do TikTok.

    Quando 'medidor' vem preenchido, a largura e medida na FONTE do preset em
    vez de contada em caracteres -- as duas regras valem juntas, e a primeira
    que estourar fecha a linha.
    """
    linhas: list[list[dict[str, Any]]] = []
    atual: list[dict[str, Any]] = []
    largura = 0
    texto_atual = ""

    for palavra in palavras:
        texto = str(palavra.get("texto") or "")
        if not texto:
            continue
        custo = _largura_visual(texto) + (1 if atual else 0)
        candidato = f"{texto_atual} {texto}".strip()
        estoura = bool(atual) and (
            len(atual) >= max_palavras
            or largura + custo > max_caracteres
            or (medidor is not None and teto > 0 and medidor(candidato) > teto)
        )
        if estoura:
            linhas.append(atual)
            atual, largura, texto_atual = [], 0, ""
            custo = _largura_visual(texto)
            candidato = texto
        atual.append(palavra)
        largura += custo
        texto_atual = candidato
        if _termina_frase(texto):
            linhas.append(atual)
            atual, largura, texto_atual = [], 0, ""

    if atual:
        linhas.append(atual)
    return linhas


def _cabecalho(preset: Preset, largura: int, altura: int) -> str:
    negrito = -1 if preset.negrito else 0
    return f"""\
[Script Info]
; Gerado pelo ClipPro -- legenda karaoke palavra a palavra.
ScriptType: v4.00+
PlayResX: {largura}
PlayResY: {altura}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Clip,{preset.fonte},{preset.tamanho},{preset.cor_falada},{preset.cor_por_falar},{preset.cor_contorno},{preset.cor_sombra},{negrito},0,0,0,100,100,{preset.espacamento},0,1,{preset.contorno},{preset.sombra},2,{preset.margem_lateral},{preset.margem_lateral},{preset.margem_inferior},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _bloco_palavra(preset: Preset, k: int, t0_ms: int) -> str:
    """O bloco de override de UMA palavra: karaoke, pop de escala e cor.

    Sem pop o bloco e o da F3, "{\\kNN}". Com pop ele carrega quatro coisas, e
    a ordem delas importa:

      1. `\\fscx100\\fscy100` -- a LINHA DE BASE. Sem ela o pop vaza: uma tag de
         override vale para todo o texto que vem DEPOIS dela ate a proxima, e
         medimos as palavras seguintes ficando infladas junto (a palavra 3
         media 336x73 em vez de 300x65, ainda por falar).
      2. `\\1c<destaque>` -- a cor que a palavra ganha quando o karaoke passa
         por ela. Ela NAO pinta a palavra antes da hora: enquanto a palavra nao
         foi cantada o libass usa a SecondaryColour do estilo (a cor "por
         falar"); `\\1c` e a PrimaryColour, que so entra quando o `\\k` chega.
      3. Dois `\\t` de escala: sobe ate pop_escala e volta a 100. Os dois sao
         cortados pela duracao da PROPRIA palavra -- com pop fixo de 480 ms e
         palavras de 150 ms medimos DUAS palavras acesas ao mesmo tempo.
      4. Um `\\t` final devolvendo a cor para "ja falada" no fim da palavra.
         E o que mantem exatamente UMA palavra em destaque a cada instante, e
         o que diferencia a v2 da F3 -- la, a palavra acendia e ficava acesa
         para sempre, e no fim da linha tudo estava aceso.

    Os tempos de `\\t` sao em milissegundos relativos ao inicio do Dialogue.
    """
    if not preset.tem_pop:
        return "{\\k" + str(k) + "}"

    e = t0_ms + k * 10
    janela = max(10, e - t0_ms)

    # Tudo aqui e PROPORCIONAL a palavra, com piso. Com tempos fixos, palavra
    # curta quebrava de dois jeitos medidos: em 1,5% delas o \t saia com
    # duracao ZERO, e em 6,4% a volta da cor comecava no mesmo instante em que
    # a palavra acendia -- ela nascia desbotando e NUNCA aparecia na cor de
    # destaque, que e justamente o efeito pedido.
    volta = min(int(preset.pop_volta_ms), max(10, int(janela * 0.30)))
    p = int(preset.pop_escala)

    if janela >= 60:
        sobe = min(int(preset.pop_subida_ms), max(20, int(janela * 0.30)))
        desce = min(int(preset.pop_descida_ms), max(20, int(janela * 0.30)))
        b = t0_ms + sobe
        c = min(b + desce, e - 10)
        escala = f"\\t({t0_ms},{b},\\fscx{p}\\fscy{p})\\t({b},{c},\\fscx100\\fscy100)"
    else:
        # Abaixo de 60 ms (menos de 4 quadros a 59,94 fps) o pop de escala nao
        # chega a ser visto; fica so a troca de cor, que sincroniza com o \k.
        c = t0_ms
        escala = ""

    d = max(c, e - volta)

    return (
        "{\\k" + str(k)
        + "\\fscx100\\fscy100\\1c" + preset.cor_do_pop
        + escala
        + f"\\t({d},{e},\\1c{preset.cor_falada})"
        + "}"
    )


def montar_ass(
    palavras: Iterable[dict[str, Any]],
    *,
    preset: Preset,
    inicio: float,
    fim: float,
    largura: int = 1080,
    altura: int = 1920,
) -> tuple[str, dict[str, Any]]:
    """Monta o texto ASS de um clipe e um resumo do que foi gerado.

    'palavras' vem com tempos ABSOLUTOS (os de transcricao.json); aqui eles
    viram tempos relativos ao inicio do clipe, que e onde o corte comeca.
    """
    lista = [p for p in palavras if str(p.get("texto") or "").strip()]
    duracao = max(0.0, float(fim) - float(inicio))
    medidor = _medidor(preset)
    teto = teto_de_largura(preset, largura) if medidor is not None else 0.0
    linhas = agrupar_linhas(
        lista,
        max_palavras=preset.max_palavras_linha,
        max_caracteres=preset.max_caracteres_linha,
        medidor=medidor,
        teto=teto,
    )

    eventos: list[str] = []
    menor_k = None
    total_palavras = 0

    for i, linha in enumerate(linhas):
        ini_linha = max(0.0, float(linha[0]["inicio"]) - inicio)
        fim_fala = max(ini_linha, float(linha[-1]["fim"]) - inicio)

        # Segura a linha um pouco alem da fala, sem invadir a proxima nem
        # passar do fim do clipe.
        limite = duracao
        if i + 1 < len(linhas):
            limite = min(limite, max(0.0, float(linhas[i + 1][0]["inicio"]) - inicio))
        fim_linha = min(fim_fala + _SEGURAR_S, limite)
        if fim_linha <= ini_linha:
            fim_linha = min(ini_linha + 0.10, duracao)

        pedacos: list[str] = []
        # Relogio da linha: o \t de cada palavra e contado do inicio do
        # Dialogue, e a soma dos \k anteriores E esse relogio (em centisegundos
        # convertidos para ms). Recalcular pelo timestamp da palavra abriria
        # uma diferenca de ate um centissegundo por palavra contra o karaoke.
        decorrido_ms = 0
        for j, palavra in enumerate(linha):
            comeca = max(0.0, float(palavra["inicio"]) - inicio)
            if j + 1 < len(linha):
                proxima = max(0.0, float(linha[j + 1]["inicio"]) - inicio)
            else:
                proxima = fim_linha
            k = _centis(proxima - comeca)
            if menor_k is None or k < menor_k:
                menor_k = k
            texto = str(palavra["texto"]).strip()
            if preset.maiusculas:
                texto = texto.upper()
            pedacos.append(_bloco_palavra(preset, k, decorrido_ms) + _escapar(texto))
            decorrido_ms += k * 10
            total_palavras += 1

        eventos.append(
            f"Dialogue: 0,{_tempo_ass(ini_linha)},{_tempo_ass(fim_linha)},Clip,,0,0,0,,"
            + " ".join(pedacos)
        )

    resumo = {
        "linhas": len(linhas),
        "palavras": total_palavras,
        "menor_k_centis": menor_k or 0,
        "preset": preset.nome,
        "pop": int(preset.pop_escala) if preset.tem_pop else 0,
        "quebra": "largura medida" if medidor is not None else "contagem de caracteres",
        "teto_largura": round(teto, 1),
    }
    return _cabecalho(preset, largura, altura) + "\n".join(eventos) + "\n", resumo
