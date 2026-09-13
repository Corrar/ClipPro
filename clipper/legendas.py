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

    # --- conformidade de legenda (F6). Todos com padrao DESLIGADO, e o padrao
    # e "igual a F4a": um preset que nao declara nenhum destes gera exatamente
    # o mesmo ASS de antes, byte a byte.
    #
    # min_palavras_linha 0 = sem piso. O teto (max_palavras_linha) NAO muda:
    # o piso so junta bloco curto, nunca afrouxa o teto.
    min_palavras_linha: int = 0
    # Nao fundir ATRAVES de uma pausa maior que isto. Bloco curto separado do
    # vizinho por silencio longo e uma escolha de quem falou, nao sobra de
    # quebra -- juntar os dois ressuscitaria texto que ja saiu da tela.
    gap_maximo_fusao_s: float = 1.2
    # Maximo de linhas dentro de um bloco. A segunda linha (\N) so nasce
    # quando a largura obriga; nunca para "equilibrar" visual.
    max_linhas_bloco: int = 2
    # Palavra com menos letras que isto NAO recebe o destaque da palavra
    # ativa: o realce pula para a proxima que alcance o limiar. 0 = desligado.
    # Defeito que isto mata, visto em render real: "E A PRIMEIRA" com o "A"
    # aceso em amarelo.
    destaque_minimo_letras: int = 0
    # Margem direita propria. -1 = simetrica com margem_lateral, que e o que
    # os presets de fabrica usam (zero pixel de diferenca). O respiro
    # assimetrico para a coluna de botoes e botao de modelo, nao padrao.
    margem_direita: int = -1

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

    @property
    def margem_dir(self) -> int:
        """A margem direita efetiva: a propria, ou a lateral quando nao ha."""
        return self.margem_lateral if int(self.margem_direita) < 0 else int(self.margem_direita)


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
    util = max(80.0, float(largura_canvas) - float(preset.margem_lateral) - float(preset.margem_dir))
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


def _letras(texto: str) -> int:
    """Quantas LETRAS a palavra tem, ignorando pontuacao e acento combinante.

    "e" tem 1, "de," tem 2, "que" tem 3. A pontuacao nao conta porque quem le
    a tela ve a palavra, nao o ponto -- e e a palavra curta que fica feia
    acesa sozinha.
    """
    limpo = unicodedata.normalize("NFC", str(texto))
    return sum(1 for c in limpo if c.isalpha())


def _lacuna(anterior: Sequence[dict[str, Any]], proxima: Sequence[dict[str, Any]]) -> float:
    """Silencio entre o fim de um bloco e o comeco do seguinte, em segundos."""
    try:
        return max(0.0, float(proxima[0]["inicio"]) - float(anterior[-1]["fim"]))
    except (IndexError, KeyError, TypeError, ValueError):
        return 0.0


def fundir_curtos(
    linhas: list[list[dict[str, Any]]],
    *,
    minimo: int,
    maximo: int,
    gap_maximo: float,
) -> list[list[dict[str, Any]]]:
    """Junta blocos abaixo do piso, sem afrouxar o teto nem atravessar pausa.

    Por que o piso existe: `agrupar_linhas` fecha a linha no fim de frase, e
    uma frase de uma palavra ("Sim.") vira um bloco de uma palavra. Um flash
    de uma palavra na tela nao da tempo de ler e pisca.

    Duas guardas, e as duas podem DEIXAR o bloco curto -- de proposito:

      teto: fundir nunca pode passar de `maximo`. O teto e o que mantem a
      linha curta o bastante para caber na area segura; afrouxa-lo para
      cumprir o piso trocaria um defeito por outro.

      lacuna: nao funde atraves de silencio maior que `gap_maximo`. Bloco
      separado do vizinho por pausa longa esta separado porque quem falou
      parou ali; juntar traria de volta um texto que ja tinha saido.

    Tenta primeiro juntar com o bloco SEGUINTE (a leitura segue para a
    frente); so entao com o anterior, que e o que salva o bloco final, sem
    vizinho a direita.
    """
    if minimo <= 1 or not linhas:
        return linhas

    atual = [list(linha) for linha in linhas]
    mudou = True
    while mudou:
        mudou = False
        for i, bloco in enumerate(atual):
            if len(bloco) >= minimo:
                continue
            # para a frente
            if i + 1 < len(atual):
                proximo = atual[i + 1]
                if len(bloco) + len(proximo) <= maximo and _lacuna(bloco, proximo) <= gap_maximo:
                    atual[i] = bloco + proximo
                    del atual[i + 1]
                    mudou = True
                    break
            # para tras
            if i > 0:
                anterior = atual[i - 1]
                if len(anterior) + len(bloco) <= maximo and _lacuna(anterior, bloco) <= gap_maximo:
                    atual[i - 1] = anterior + bloco
                    del atual[i]
                    mudou = True
                    break
    return atual


def quebrar_bloco(
    bloco: Sequence[dict[str, Any]],
    *,
    maiusculas: bool,
    medidor: Any,
    teto: float,
    max_linhas: int,
) -> list[list[dict[str, Any]]]:
    """Divide um bloco em ate `max_linhas` linhas, e SO se a largura obrigar.

    Sem medidor, ou cabendo em uma linha, devolve o bloco inteiro numa linha
    so -- que e o comportamento da F4a. A segunda linha nasce da largura, nao
    de gosto: o ponto de corte escolhido e o que deixa as duas linhas mais
    parecidas, porque linha longa sobre linha curta le pior que duas medias.
    """
    palavras = list(bloco)
    if medidor is None or teto <= 0 or max_linhas <= 1 or len(palavras) < 2:
        return [palavras]

    def texto(seq: Sequence[dict[str, Any]]) -> str:
        junto = " ".join(str(p.get("texto") or "").strip() for p in seq)
        return junto.upper() if maiusculas else junto

    if medidor(texto(palavras)) <= teto:
        return [palavras]

    melhor, menor_desequilibrio = None, None
    for corte in range(1, len(palavras)):
        a, b = palavras[:corte], palavras[corte:]
        la, lb = medidor(texto(a)), medidor(texto(b))
        if la > teto or lb > teto:
            continue
        desequilibrio = abs(la - lb)
        if menor_desequilibrio is None or desequilibrio < menor_desequilibrio:
            melhor, menor_desequilibrio = corte, desequilibrio

    if melhor is None:
        # Nenhum corte faz as duas linhas caberem -- uma palavra sozinha mais
        # larga que a caixa, tipicamente. Uma linha so e melhor do que duas
        # linhas ambas estourando.
        return [palavras]
    return [palavras[:melhor], palavras[melhor:]]


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
Style: Clip,{preset.fonte},{preset.tamanho},{preset.cor_falada},{preset.cor_por_falar},{preset.cor_contorno},{preset.cor_sombra},{negrito},0,0,0,100,100,{preset.espacamento},0,1,{preset.contorno},{preset.sombra},2,{preset.margem_lateral},{preset.margem_dir},{preset.margem_inferior},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _bloco_palavra(preset: Preset, k: int, t0_ms: int, *, destacar: bool = True) -> str:
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

    if not destacar:
        # Palavra curta demais para merecer o realce. Ela NAO some nem fica
        # sem karaoke: continua acendendo no tempo certo, direto na cor de
        # "ja falada". O que se pula e o flash de destaque, e o realce
        # naturalmente recai na proxima palavra que alcance o limiar.
        #
        # A linha de base vai explicita (\\fscx100\\fscy100\\1c) porque
        # override de ASS vale para todo o texto que vem DEPOIS dele: sem
        # repor escala e cor aqui, esta palavra herdaria o que a anterior
        # deixou no ar.
        return (
            "{\\k" + str(k)
            + "\\fscx100\\fscy100\\1c" + preset.cor_falada
            + "}"
        )

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


def resincronizar(
    palavras: Iterable[dict[str, Any]], segmentos: Sequence[dict[str, Any]]
) -> tuple[list[dict[str, Any]], float]:
    """Leva as palavras do tempo da FONTE para o tempo do clipe concatenado.

    Num clipe de varios trechos, a palavra que estava em 03:12 da fonte pode
    cair em 00:08 do clipe -- ou em lugar nenhum, se estava na gordura
    removida. Palavra fora dos segmentos mantidos SOME: legenda de fala que
    foi cortada e legenda mentindo.

    Palavra que atravessa a borda de um segmento e APARADA na borda, nao
    descartada: ela foi parcialmente dita no clipe, e o karaoke precisa de um
    tempo valido para ela.

    Devolve (palavras_no_tempo_do_clipe, duracao_total).
    """
    saida: list[dict[str, Any]] = []
    decorrido = 0.0
    for s in segmentos:
        ini, fim = float(s["inicio"]), float(s["fim"])
        for p in palavras:
            try:
                p_ini, p_fim = float(p["inicio"]), float(p["fim"])
            except (KeyError, TypeError, ValueError):
                continue
            if p_fim <= ini + 1e-6 or p_ini >= fim - 1e-6:
                continue
            novo_ini = decorrido + (max(p_ini, ini) - ini)
            novo_fim = decorrido + (min(p_fim, fim) - ini)
            if novo_fim <= novo_ini:
                novo_fim = novo_ini + 0.06  # o mesmo piso de 60 ms da F1
            saida.append({**p, "inicio": round(novo_ini, 3), "fim": round(novo_fim, 3)})
        decorrido += fim - ini
    saida.sort(key=lambda p: (float(p["inicio"]), float(p["fim"])))
    return saida, round(decorrido, 3)


def montar_ass(
    palavras: Iterable[dict[str, Any]],
    *,
    preset: Preset,
    inicio: float,
    fim: float,
    largura: int = 1080,
    altura: int = 1920,
    segmentos: Sequence[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Monta o texto ASS de um clipe e um resumo do que foi gerado.

    'palavras' vem com tempos ABSOLUTOS (os de transcricao.json); aqui eles
    viram tempos relativos ao inicio do clipe, que e onde o corte comeca.

    Com `segmentos`, o clipe e multi-trecho: as palavras sao primeiro levadas
    para o tempo do clipe CONCATENADO e o resto do caminho segue igual, com
    inicio 0 e fim na duracao somada. Sem `segmentos`, nada muda -- e o que
    mantem o clipe v1 gerando o mesmo ASS de antes.
    """
    lista = [p for p in palavras if str(p.get("texto") or "").strip()]
    if segmentos:
        lista, total = resincronizar(lista, segmentos)
        inicio, fim = 0.0, total
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
    # Piso de palavras DEPOIS do agrupamento, nao dentro dele: agrupar decide
    # onde a frase quebra, fundir decide se o pedaco resultante e curto demais
    # para ficar sozinho. Sao duas perguntas diferentes, e misturar as duas na
    # mesma passada tornaria impossivel dizer qual regra fechou a linha.
    linhas = fundir_curtos(
        linhas,
        minimo=int(preset.min_palavras_linha),
        maximo=int(preset.max_palavras_linha),
        gap_maximo=float(preset.gap_maximo_fusao_s),
    )

    eventos: list[str] = []
    menor_k = None
    total_palavras = 0
    blocos_com_duas_linhas = 0
    destaques_pulados = 0

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

        # A segunda linha visual (\N) sai da LARGURA, nunca de gosto. O bloco
        # continua sendo UM Dialogue: o \N e quebra de linha dentro dele, e o
        # relogio do karaoke atravessa a quebra sem saber que ela existe.
        visuais = quebrar_bloco(
            linha,
            maiusculas=bool(preset.maiusculas),
            medidor=medidor,
            teto=teto,
            max_linhas=int(preset.max_linhas_bloco),
        )
        if len(visuais) > 1:
            blocos_com_duas_linhas += 1

        pedacos: list[str] = []
        # Relogio da linha: o \t de cada palavra e contado do inicio do
        # Dialogue, e a soma dos \k anteriores E esse relogio (em centisegundos
        # convertidos para ms). Recalcular pelo timestamp da palavra abriria
        # uma diferenca de ate um centissegundo por palavra contra o karaoke.
        decorrido_ms = 0
        limiar = int(preset.destaque_minimo_letras)
        for j, palavra in enumerate(linha):
            comeca = max(0.0, float(palavra["inicio"]) - inicio)
            if j + 1 < len(linha):
                proxima = max(0.0, float(linha[j + 1]["inicio"]) - inicio)
            else:
                proxima = fim_linha
            k = _centis(proxima - comeca)
            if menor_k is None or k < menor_k:
                menor_k = k
            cru = str(palavra["texto"]).strip()
            texto = cru.upper() if preset.maiusculas else cru
            destacar = limiar <= 0 or _letras(cru) >= limiar
            if not destacar and preset.tem_pop:
                destaques_pulados += 1
            if j:
                # Separador ANTES desta palavra: quebra de linha quando ela
                # abre a segunda linha visual, espaco no resto.
                pedacos.append("\\N" if j == len(visuais[0]) and len(visuais) > 1 else " ")
            pedacos.append(
                _bloco_palavra(preset, k, decorrido_ms, destacar=destacar) + _escapar(texto)
            )
            decorrido_ms += k * 10
            total_palavras += 1

        eventos.append(
            f"Dialogue: 0,{_tempo_ass(ini_linha)},{_tempo_ass(fim_linha)},Clip,,0,0,0,,"
            + "".join(pedacos)
        )

    resumo = {
        "linhas": len(linhas),
        "palavras": total_palavras,
        "menor_k_centis": menor_k or 0,
        "preset": preset.nome,
        "pop": int(preset.pop_escala) if preset.tem_pop else 0,
        "quebra": "largura medida" if medidor is not None else "contagem de caracteres",
        "teto_largura": round(teto, 1),
        "piso_palavras": int(preset.min_palavras_linha),
        "blocos_duas_linhas": blocos_com_duas_linhas,
        "destaques_pulados": destaques_pulados,
        "menor_bloco_palavras": min((len(l) for l in linhas), default=0),
        "maior_bloco_palavras": max((len(l) for l in linhas), default=0),
        "segmentos": len(segmentos) if segmentos else 0,
    }
    return _cabecalho(preset, largura, altura) + "\n".join(eventos) + "\n", resumo
