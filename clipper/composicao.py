"""Composicao visual do clipe (F4a): o preset "cortes" e os ativos que ele desenha.

A F3 entregava o recorte 9:16 cheio com a legenda queimada por cima. Este modulo
existe para o objetivo novo: o clipe precisa ser VISUALMENTE DISTINTO do video de
origem -- um leitor automatico de duplicata nao pode casar quadro a quadro com o
original -- sem deixar de ser o mesmo conteudo.

A composicao empilha, de tras para frente:

    fundo   = o proprio video, borrado pesado e escurecido, preenchendo 1080x1920
    sombra  = mancha suave sob o cartao (PNG, desenhado uma vez)
    cartao  = o recorte 9:16 com Ken Burns + punch-in, cantos arredondados
    frente  = fio de luz na borda do cartao e degrade sob a legenda (PNG)
    barra   = progresso do clipe na base do cartao
    titulo  = pilula com o titulo do clipe, entrando por cima nos primeiros 0,5s
    legenda = ASS karaoke v2 (a palavra ativa cresce e acende)
    fade    = 0,3s de entrada e de saida no conjunto

Tres decisoes que custaram medicao e que nao dao para adivinhar:

1. O TEMPO DENTRO DO zoompan E 'ot', NUNCA 'it'. Com "-ss" antes do "-i" o
   timestamp da primeira imagem nao e zero: ele carrega o residuo do seek, que
   MUDA a cada clipe (0,0165s com -ss 200; 0,0050s com -ss 5). 'ot' (out_time) e
   a hora de saida e comeca exatamente em 0. E 'fps=' precisa ser a FRACAO da
   fonte (60000/1001): sem ela o zoompan assume 25 e a duracao do clipe sai 2,4x
   maior -- com a contagem de frames CERTA, entao so a duracao denuncia.

2. O zoompan TRUNCA a janela de corte em pixel inteiro do espaco de ENTRADA. Com
   518px de entrada, 1px = 0,19% de zoom, enquanto o Ken Burns anda 0,0017% por
   frame: a imagem congela por ate 12 frames e depois salta 1,3px. Por isso o
   recorte e AMPLIADO (scale=...:flags=neighbor) antes do zoompan -- com o dobro
   da resolucao do cartao o salto cai para 0,47px, abaixo de um pixel de saida.

3. A BARRA DE PROGRESSO NAO PODE SER drawbox ANIMADO. O drawbox deste ffmpeg nao
   tem a opcao 'eval', e dentro das expressoes dele 't' e a ESPESSURA, nao o
   tempo: "drawbox=w='730*min(t/6,1)'" roda sem erro nenhum e desenha a barra
   CHEIA e parada. A barra e feita recortando a faixa do quadro, desenhando o
   trilho e deslizando o preenchimento com overlay:eval=frame.

Convencao deste arquivo: comentarios e docstrings em PT-BR sem acento; mensagens
dirigidas ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from clipper.erros import ErroRender

LARGURA_SAIDA = 1080
ALTURA_SAIDA = 1920

# Sobe quando o RESULTADO do render muda para os mesmos parametros (expressao
# nova, camada nova, ordem diferente). Entra na impressao do estilo, entao um
# clipe gravado pela versao anterior deixa de ser reaproveitado e e refeito.
#   1 -- primeira versao da composicao (F4a).
#   2 -- pilula, acento e fio do cartao passam a ser desenhados com antialias;
#        o pop da legenda passa a ser proporcional a duracao da palavra.
#   3 -- F6: o slot do topo troca de dono (titulo permanente -> gancho com
#        recorte temporal), a legenda ganha piso de palavras com guarda de
#        lacuna, e o destaque passa a pular palavra curta. Bump DELIBERADO:
#        o resultado muda para os MESMOS parametros, entao todo clipe ja
#        gravado e refeito uma vez -- de proposito, nao por efeito colateral
#        de ter somado campo ao dataclass.
VERSAO = 3

# Fontes do Windows por nome de familia. A tabela cobre o que os presets usam;
# o que nao estiver aqui ainda e procurado na pasta de fontes do sistema.
_ARQUIVOS_DE_FONTE = {
    "impact": "impact.ttf",
    "arial black": "ariblk.ttf",
    "arial": "arial.ttf",
    "segoe ui": "segoeui.ttf",
    "segoe ui black": "seguibl.ttf",
    "segoe ui semibold": "seguisb.ttf",
    "segoe ui bold": "segoeuib.ttf",
    "bahnschrift": "bahnschrift.ttf",
    "verdana": "verdana.ttf",
    "verdana bold": "verdanab.ttf",
    "trebuchet ms": "trebuc.ttf",
    "trebuchet ms bold": "trebucbd.ttf",
    "calibri": "calibri.ttf",
    "calibri bold": "calibrib.ttf",
}


# ==========================================================================
# Parametros
# ==========================================================================


def _num(dados: Any, caminho: str, padrao: float) -> float:
    """Le um numero de um caminho 'a.b.c' no dict do preset, com padrao."""
    atual: Any = dados
    for parte in caminho.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return float(padrao)
        atual = atual[parte]
    if isinstance(atual, bool) or not isinstance(atual, (int, float, str)):
        return float(padrao)
    try:
        return float(atual)
    except (TypeError, ValueError):
        return float(padrao)


def _txt(dados: Any, caminho: str, padrao: str) -> str:
    atual: Any = dados
    for parte in caminho.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return padrao
        atual = atual[parte]
    return str(atual) if isinstance(atual, (str, int, float)) else padrao


def _flag(dados: Any, caminho: str, padrao: bool) -> bool:
    atual: Any = dados
    for parte in caminho.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return padrao
        atual = atual[parte]
    return bool(atual) if isinstance(atual, bool) else padrao


def _par(valor: float) -> int:
    """Arredonda para baixo ao par mais proximo (o H.264 4:2:0 exige par)."""
    n = int(valor)
    return n - (n % 2)


@dataclass(frozen=True)
class Composicao:
    """Todos os numeros do layout, ja resolvidos em pixels do canvas 1080x1920.

    Um preset sem bloco "composicao" nao chega aqui: quem decide e
    `de_preset()`, que devolve None e mantem o caminho da F3 (recorte cheio).
    """

    nome: str

    # cartao
    cartao_largura: int
    cartao_altura: int
    cartao_x: int
    cartao_y: int
    cartao_raio: int
    traco_largura: float
    traco_cor: str
    traco_opacidade: float

    # sombra e vinheta (camada atras do cartao)
    sombra_dx: int
    sombra_dy: int
    sombra_sigma: float
    sombra_opacidade: float
    sombra_expansao: int
    sombra_cor: str
    vinheta: float

    # fundo borrado
    fundo_proxy_largura: int
    fundo_sigma: float
    fundo_escurecer: float
    fundo_saturacao: float

    # barra de titulo
    titulo_ativo: bool
    titulo_fonte: str
    titulo_arquivo: str
    titulo_tamanho: int
    titulo_tamanho_minimo: int
    titulo_maiusculas: bool
    titulo_cor: str
    titulo_pilula_cor: str
    titulo_pilula_opacidade: float
    titulo_altura: int
    titulo_raio: int
    titulo_padding_h: int
    titulo_largura_maxima: int
    titulo_alinhamento: str
    titulo_x: int
    titulo_y: int
    titulo_deslize_s: float
    titulo_fade_s: float
    titulo_acento: str
    titulo_acento_cor: str
    titulo_acento_largura: int
    titulo_acento_altura: int
    titulo_acento_gap: int

    # gancho: o slot do topo com recorte temporal (F6)
    gancho_ativo: bool
    gancho_duracao_s: float
    gancho_fade_saida_s: float
    gancho_y: int

    # conclusao: overlay dos ultimos segundos (F6/P2)
    conclusao_duracao_s: float
    conclusao_fade_s: float
    conclusao_y: int

    # Crossfade de AUDIO nas juncoes de um clipe multi-segmento. O video corta
    # seco (jump cut e idiomatico em Shorts); o audio NAO pode, porque emenda
    # de forma de onda vira clique audivel.
    juncao_crossfade_s: float

    # zona segura da UI do Shorts. Os numeros saem da interface do app
    # (coluna de botoes a direita, descricao e handle na base) e sao
    # AJUSTAVEIS: quando a UI mudar, muda-se aqui, nao no codigo que desenha.
    zona_topo: int
    zona_base: int

    # barra de progresso
    progresso_ativo: bool
    progresso_altura: int
    progresso_recuo: int
    progresso_y: int
    progresso_trilho_cor: str
    progresso_trilho_opacidade: float
    progresso_cor: str
    progresso_opacidade: float
    progresso_contorno: int
    progresso_contorno_cor: str
    progresso_contorno_opacidade: float

    # degrade sob a legenda
    scrim_ativo: bool
    scrim_y_inicio: int
    scrim_y_fim: int
    scrim_opacidade: float
    scrim_cor: str

    # movimento
    kenburns_ate: float
    kenburns_prescale: float
    punch_ganho: float
    punch_duracao: float
    punch_maximo: int
    punch_inicio_minimo: float
    punch_espacamento: float
    punch_antecipar: float

    # audio e pontas
    fade_s: float
    audio_eq: str
    audio_i: float
    audio_tp: float
    audio_lra: float
    pitch_razao: float

    @property
    def cartao_direita(self) -> int:
        return self.cartao_x + self.cartao_largura

    @property
    def cartao_base(self) -> int:
        return self.cartao_y + self.cartao_altura

    @property
    def fundo_proxy_altura(self) -> int:
        return _par(self.fundo_proxy_largura * ALTURA_SAIDA / LARGURA_SAIDA)

    def impressao(self, *, pitch: bool = False) -> str:
        """Identidade do estilo: muda aqui, o clipe pronto deixa de valer.

        Sem isso, editar o preset (outra cor, outro raio) e repetir o comando
        devolveria o mp4 antigo: o nome do arquivo e o trecho continuam os
        mesmos, e e so isso que o reaproveitamento olha.

        O 'pitch' e argumento, e nao campo, porque ele e BANDEIRA DE LINHA DE
        COMANDO e nao do preset -- mas precisa entrar aqui de qualquer jeito:
        ele muda a cadeia de audio, logo muda o arquivo. E so soma quando esta
        LIGADO, para que os clipes ja gravados sem pitch continuem valendo.
        """
        dados: dict[str, Any] = {"versao": VERSAO, **asdict(self)}
        if pitch:
            dados["pitch"] = True
        corpo = json.dumps(dados, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:16]

    def marca_desenho(self) -> str:
        """Identidade so do que vira PIXEL nos PNG do cartao.

        Separada da impressao cheia de proposito: mexer no ganho do punch, na
        cor da barra ou no loudnorm nao muda um pixel dos PNG, e usar a
        impressao cheia no nome deles redesenhava tudo e deixava o conjunto
        anterior na pasta a cada ajuste de preset.
        """
        campos = {
            nome: valor
            for nome, valor in asdict(self).items()
            if nome.startswith(("cartao_", "sombra_", "traco_", "scrim_"))
            or nome == "vinheta"
        }
        corpo = json.dumps({"versao": VERSAO, **campos}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:16]


def de_preset(dados: Any, nome: str) -> Composicao | None:
    """Le o bloco "composicao" do preset. Sem ele, devolve None (caminho F3)."""
    if not isinstance(dados, dict):
        return None
    comp = dados.get("composicao")
    if not isinstance(comp, dict) or not _flag(comp, "ativo", True):
        return None

    fracao = min(0.95, max(0.40, _num(comp, "cartao.fracao_altura", 0.75)))
    largura = _par(LARGURA_SAIDA * fracao)
    altura = _par(ALTURA_SAIDA * fracao)
    x = _par((LARGURA_SAIDA - largura) / 2)
    y = _par((ALTURA_SAIDA - altura) / 2)

    progresso_altura = max(2, int(_num(comp, "progresso.altura", 10)))
    # Por padrao a barra fica DENTRO do cartao, colada na base: e o pedido da
    # F4a ("na base do video principal") e o unico lugar que a sondagem provou
    # nao vazar pela silhueta arredondada (recuo 40, zero pixel fora).
    progresso_y = int(_num(comp, "progresso.y", y + altura - progresso_altura - 14))
    # Recuo maior que a metade do cartao daria largura NEGATIVA, e o ffmpeg
    # aceita 'crop=-190:10' calado. Preset e arquivo que o usuario edita: aqui
    # o valor impossivel e aparado, nao repassado.
    progresso_recuo = max(0, min(int(_num(comp, "progresso.recuo", 40)), (largura - 40) // 2))

    # Zona segura da UI do Shorts, em pixels do canvas 1080x1920. 180 no topo
    # cobre a faixa onde o app desenha o proprio cabecalho; 1420 na base deixa
    # livres os ~26% de baixo, onde ficam descricao e handle. Os dois sao
    # PARAMETROS: a UI do app muda com o tempo, e quando mudar troca-se o
    # numero no modelo, sem tocar em quem desenha.
    zona_topo = max(0, int(_num(comp, "zona_segura.topo", 180)))
    zona_base = min(ALTURA_SAIDA, int(_num(comp, "zona_segura.base", 1420)))

    return Composicao(
        nome=nome,
        cartao_largura=largura,
        cartao_altura=altura,
        cartao_x=x,
        cartao_y=y,
        cartao_raio=max(0, min(int(_num(comp, "cartao.raio", 32)), min(largura, altura) // 2)),
        traco_largura=max(0.0, _num(comp, "cartao.traco_largura", 0.0)),
        traco_cor=_txt(comp, "cartao.traco_cor", "#FFFFFF"),
        traco_opacidade=_num(comp, "cartao.traco_opacidade", 0.15),
        sombra_dx=int(_num(comp, "cartao.sombra.dx", 0)),
        sombra_dy=int(_num(comp, "cartao.sombra.dy", 18)),
        sombra_sigma=max(0.0, _num(comp, "cartao.sombra.sigma", 30.0)),
        sombra_opacidade=_num(comp, "cartao.sombra.opacidade", 0.6),
        sombra_expansao=max(0, int(_num(comp, "cartao.sombra.expansao", 8))),
        sombra_cor=_txt(comp, "cartao.sombra.cor", "#000000"),
        vinheta=min(1.0, max(0.0, _num(comp, "fundo.vinheta", 0.0))),
        fundo_proxy_largura=max(16, _par(_num(comp, "fundo.proxy_largura", 180))),
        fundo_sigma=max(0.0, _num(comp, "fundo.sigma", 12.0)),
        fundo_escurecer=min(0.8, max(0.0, _num(comp, "fundo.escurecer", 0.40))),
        fundo_saturacao=max(0.0, _num(comp, "fundo.saturacao", 0.80)),
        titulo_ativo=_flag(comp, "titulo.ativo", True),
        titulo_fonte=_txt(comp, "titulo.fonte", "Segoe UI Black"),
        titulo_arquivo=_txt(comp, "titulo.arquivo", ""),
        titulo_tamanho=max(8, int(_num(comp, "titulo.tamanho", 44))),
        titulo_tamanho_minimo=max(8, int(_num(comp, "titulo.tamanho_minimo", 32))),
        titulo_maiusculas=_flag(comp, "titulo.maiusculas", True),
        titulo_cor=_txt(comp, "titulo.cor", "#FFFFFF"),
        titulo_pilula_cor=_txt(comp, "titulo.pilula_cor", "#101317"),
        titulo_pilula_opacidade=_num(comp, "titulo.pilula_opacidade", 0.84),
        titulo_altura=max(24, int(_num(comp, "titulo.altura", 108))),
        titulo_raio=max(0, int(_num(comp, "titulo.raio", 54))),
        titulo_padding_h=max(0, int(_num(comp, "titulo.padding_h", 36))),
        titulo_largura_maxima=max(160, min(int(_num(comp, "titulo.largura_maxima", largura)), LARGURA_SAIDA)),
        titulo_alinhamento=_txt(comp, "titulo.alinhamento", "centro"),
        titulo_x=int(_num(comp, "titulo.x", x)),
        titulo_y=int(_num(comp, "titulo.y", 76)),
        titulo_deslize_s=_num(comp, "titulo.deslize_s", 0.5),
        titulo_fade_s=_num(comp, "titulo.fade_s", 0.5),
        titulo_acento=_txt(comp, "titulo.acento", "nenhum"),
        titulo_acento_cor=_txt(comp, "titulo.acento_cor", "#FFE500"),
        titulo_acento_largura=int(_num(comp, "titulo.acento_largura", 8)),
        titulo_acento_altura=int(_num(comp, "titulo.acento_altura", 44)),
        titulo_acento_gap=int(_num(comp, "titulo.acento_gap", 22)),
        gancho_ativo=_flag(comp, "gancho.ativo", False),
        gancho_duracao_s=max(0.5, _num(comp, "gancho.duracao_s", 3.0)),
        gancho_fade_saida_s=max(0.0, _num(comp, "gancho.fade_saida_s", 0.4)),
        # O piso do topo e aplicado AQUI, no carregamento, e nao na hora de
        # desenhar: um preset que peca y=64 para o gancho recebe 180 e o
        # filtergraph ja nasce dentro da zona segura. Aparar no carregador e
        # o que faz a regra valer para todo modelo futuro de graca.
        gancho_y=max(zona_topo, int(_num(comp, "gancho.y", zona_topo))),
        conclusao_duracao_s=max(0.5, _num(comp, "conclusao.duracao_s", 2.0)),
        conclusao_fade_s=max(0.0, _num(comp, "conclusao.fade_s", 0.3)),
        # 1040 + a altura da pilula (~108) fecha em 1148, ACIMA do bloco de
        # legenda, que com margem_inferior 500-520 e corpo 84-92 ocupa de
        # ~1180 a ~1420. Sobrepor a legenda nos ultimos segundos esconderia
        # justamente a frase que fecha o clipe.
        conclusao_y=int(_num(comp, "conclusao.y", 1040)),
        juncao_crossfade_s=max(0.0, _num(comp, "juncao.crossfade_audio_s", 0.015)),
        zona_topo=zona_topo,
        zona_base=zona_base,
        progresso_ativo=_flag(comp, "progresso.ativo", True),
        progresso_altura=progresso_altura,
        progresso_recuo=progresso_recuo,
        progresso_y=progresso_y,
        progresso_trilho_cor=_txt(comp, "progresso.trilho_cor", "#FFFFFF"),
        progresso_trilho_opacidade=_num(comp, "progresso.trilho_opacidade", 0.35),
        progresso_cor=_txt(comp, "progresso.cor", "#FFE500"),
        progresso_opacidade=_num(comp, "progresso.opacidade", 1.0),
        progresso_contorno=max(0, min(int(_num(comp, "progresso.contorno", 2)), progresso_altura // 2)),
        progresso_contorno_cor=_txt(comp, "progresso.contorno_cor", "#000000"),
        progresso_contorno_opacidade=_num(comp, "progresso.contorno_opacidade", 0.45),
        scrim_ativo=_flag(comp, "scrim.ativo", False),
        scrim_y_inicio=int(_num(comp, "scrim.y_inicio", y + altura - 700)),
        scrim_y_fim=int(_num(comp, "scrim.y_fim", y + altura - 200)),
        scrim_opacidade=_num(comp, "scrim.opacidade", 0.45),
        scrim_cor=_txt(comp, "scrim.cor", "#000000"),
        kenburns_ate=max(1.0, _num(comp, "movimento.kenburns_ate", 1.06)),
        kenburns_prescale=min(4.0, max(1.0, _num(comp, "movimento.prescale", 2.0))),
        punch_ganho=max(0.0, _num(comp, "movimento.punch_ganho", 0.08)),
        punch_duracao=max(0.05, _num(comp, "movimento.punch_duracao", 0.4)),
        punch_maximo=max(0, int(_num(comp, "movimento.punch_maximo", 3))),
        punch_inicio_minimo=_num(comp, "movimento.punch_inicio_minimo", 2.0),
        punch_espacamento=_num(comp, "movimento.punch_espacamento", 1.5),
        punch_antecipar=_num(comp, "movimento.punch_antecipar", 0.2),
        fade_s=max(0.0, _num(comp, "fade_s", 0.3)),
        audio_eq=_txt(
            comp,
            "audio.eq",
            "highpass=f=80:poles=2,"
            "equalizer=f=250:t=q:w=1.0:g=-2.5,"
            "equalizer=f=3000:t=q:w=0.9:g=2",
        ),
        audio_i=_num(comp, "audio.i", -14.0),
        audio_tp=_num(comp, "audio.tp", -1.5),
        audio_lra=_num(comp, "audio.lra", 11.0),
        pitch_razao=_num(comp, "audio.pitch_razao", 1.005),
    )


# ==========================================================================
# Punch-in: quais picos do audio viram soco de zoom
# ==========================================================================


def remapear_tempos(
    tempos: Sequence[float], segmentos: Sequence[dict[str, Any]]
) -> list[float]:
    """Leva instantes do tempo da FONTE para o tempo do clipe concatenado.

    Um punch nasce de um pico de energia medido no audio original. Com o clipe
    montado de trechos nao contiguos, o instante 03:12 da fonte pode estar em
    qualquer lugar do clipe -- ou em lugar nenhum, se caiu na gordura removida.

    Instante fora dos segmentos mantidos MORRE. Nao se aproxima para a borda
    mais perto: um soco de zoom no lugar errado e pior que soco nenhum, porque
    o espectador sente o movimento sem o motivo.
    """
    if not segmentos:
        return [float(t) for t in tempos]
    saida: list[float] = []
    for t in tempos:
        t = float(t)
        decorrido = 0.0
        for s in segmentos:
            ini, fim = float(s["inicio"]), float(s["fim"])
            if ini - 1e-6 <= t <= fim + 1e-6:
                saida.append(round(decorrido + (t - ini), 3))
                break
            decorrido += fim - ini
    return sorted(saida)


def escolher_punches(
    picos: Iterable[Any], inicio: float, fim: float, comp: Composicao
) -> list[float]:
    """Instantes (relativos ao clipe) em que o zoom da um soco de +8%.

    Regras, todas do pedido da F4a mais o que a sondagem mediu:
      - nenhum punch nos primeiros `punch_inicio_minimo` segundos;
      - nenhum punch que nao caiba inteiro dentro do clipe;
      - no maximo `punch_maximo`, espacados -- dois meio-senos sobrepostos SOMAM
        e o zoom estoura (1,22 medido), alem de virar tremedeira;
      - espalhados pelo clipe: a janela util e dividida em faixas e cada faixa
        cede o seu pico mais alto. Sem isso os tres punches se amontoam no
        comeco, porque a energia vem quantizada em 1s e empata em 1,0 o tempo
        todo.

    O pico do meio-seno cai em p+duracao/2, entao o instante do audio e
    ANTECIPADO em `punch_antecipar` para o soco bater EM CIMA do transiente.
    """
    duracao = max(0.0, float(fim) - float(inicio))
    if comp.punch_maximo <= 0 or comp.punch_ganho <= 0.0 or duracao <= 0.0:
        return []

    candidatos: list[tuple[float, float]] = []  # (t_relativo, forca)
    for pico in picos or ():
        if not isinstance(pico, dict):
            continue
        try:
            t_abs = float(pico.get("t"))
            forca = float(pico.get("rms_norm") or 0.0)
        except (TypeError, ValueError):
            continue
        t = t_abs - float(inicio) - comp.punch_antecipar
        if t < comp.punch_inicio_minimo:
            continue
        if t + comp.punch_duracao > duracao:
            continue
        candidatos.append((t, forca))

    if not candidatos:
        return []

    espacamento = max(comp.punch_espacamento, comp.punch_duracao)
    inicio_util = comp.punch_inicio_minimo
    fim_util = duracao - comp.punch_duracao
    faixa = (fim_util - inicio_util) / comp.punch_maximo if fim_util > inicio_util else 0.0

    escolhidos: list[float] = []
    if faixa <= 0.0:
        ordenados = sorted(candidatos, key=lambda c: (-c[1], c[0]))
        for t, _ in ordenados:
            if all(abs(t - outro) >= espacamento for outro in escolhidos):
                escolhidos.append(t)
            if len(escolhidos) >= comp.punch_maximo:
                break
    else:
        for i in range(comp.punch_maximo):
            baixo = inicio_util + i * faixa
            alto = baixo + faixa
            na_faixa = [c for c in candidatos if baixo <= c[0] < alto]
            if not na_faixa:
                continue
            t, _ = max(na_faixa, key=lambda c: (c[1], -c[0]))
            if all(abs(t - outro) >= espacamento for outro in escolhidos):
                escolhidos.append(t)

    return sorted(round(t, 3) for t in escolhidos)


def expressao_zoom(duracao: float, punches: Sequence[float], comp: Composicao) -> str:
    """A expressao 'z' do zoompan: Ken Burns continuo + socos de meio-seno.

    'ot' e a hora de saida em segundos, que comeca em 0 na primeira imagem do
    clipe. 'it' NAO serve: carrega o residuo do seek de entrada, diferente a
    cada clipe.
    """
    duracao = max(0.001, float(duracao))
    partes = [f"min(1+{comp.kenburns_ate - 1.0:.4f}*ot/{duracao:.3f},{comp.kenburns_ate:.4f})"]
    for p in punches:
        partes.append(
            f"{comp.punch_ganho:.4f}"
            f"*between(ot,{p:.3f},{p + comp.punch_duracao:.3f})"
            f"*sin(PI*(ot-{p:.3f})/{comp.punch_duracao:.3f})"
        )
    return "+".join(partes)


# ==========================================================================
# Ativos desenhados (PNG gerados uma vez por geometria)
# ==========================================================================


def _cor_rgb(texto: str) -> tuple[int, int, int]:
    """'#RRGGBB' -> (r, g, b). Cor torta vira preto, nunca excecao."""
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(texto).strip())
    if not m:
        return (0, 0, 0)
    v = m.group(1)
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))


def _salvar(imagem: Any, destino: Path) -> Path:
    """Grava o PNG de forma atomica: .tmp e depois replace.

    O resto do projeto ja escreve assim (escrever_json, _gravar_ass, Estado).
    Aqui faltava, e o estrago era pior: um processo morto no meio do save
    deixava um PNG TRUNCADO com o nome definitivo, e como o reaproveitamento
    olhava so a existencia do arquivo, aquele preset passava a morrer no
    ffmpeg em toda rodada seguinte, para sempre.
    """
    destino = Path(destino)
    tmp = destino.with_name(destino.name + ".tmp")
    # 'format' explicito: o Pillow deduz o formato pela EXTENSAO, e ".png.tmp"
    # nao e extensao conhecida -- sem isto o save morre com "unknown file
    # extension: .tmp".
    imagem.save(tmp, format="PNG")
    tmp.replace(destino)
    return destino


def _png_intacto(caminho: Path) -> bool:
    """O PNG existe e abre inteiro? Um arquivo pela metade nao vale cache."""
    try:
        from PIL import Image

        if not caminho.is_file() or caminho.stat().st_size == 0:
            return False
        with Image.open(caminho) as im:
            im.load()
        return True
    except Exception:  # noqa: BLE001 - qualquer defeito aqui significa "regere"
        return False


def _fonte(nome: str, arquivo: str, tamanho: int) -> Any:
    """Carrega a fonte do preset com o Pillow, pelo caminho ou pelo nome.

    A ordem e: caminho explicito do preset -> tabela de arquivos conhecidos ->
    varredura da pasta de fontes do Windows comparando a familia -> fonte
    embutida do Pillow. Nunca levanta: uma fonte ausente nao pode derrubar o
    render (a legenda ASS tem o proprio caminho de fallback, no libass).
    """
    from PIL import ImageFont

    tamanho = max(8, int(tamanho))
    tentativas: list[str] = []
    if arquivo:
        tentativas.append(arquivo)
    chave = str(nome or "").strip().lower()
    if chave in _ARQUIVOS_DE_FONTE:
        tentativas.append(_ARQUIVOS_DE_FONTE[chave])
    if chave:
        tentativas.append(re.sub(r"\s+", "", chave) + ".ttf")

    for candidato in tentativas:
        try:
            return ImageFont.truetype(candidato, tamanho)
        except (OSError, ValueError):
            continue

    pasta = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    try:
        for arq in sorted(pasta.glob("*.tt[fc]")):
            try:
                f = ImageFont.truetype(str(arq), tamanho)
                if str(f.getname()[0]).strip().lower() == chave:
                    return f
            except (OSError, ValueError):
                continue
    except OSError:
        pass

    # Ultimo recurso, e ele PRECISA avisar: a troca silenciosa entregava um
    # titulo de 8px de tinta dentro de uma pilula de 108px, porque o
    # load_default() do Pillow ignora o tamanho pedido quando nao recebe
    # 'size'. Antes de chegar nele, tenta duas fontes que todo Windows tem.
    from clipper.registro import obter

    for reserva in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            f = ImageFont.truetype(reserva, tamanho)
            obter().warning(
                f"      aviso:  a fonte '{nome}' não foi encontrada nesta máquina; "
                f"a barra de título vai sair em {f.getname()[0]}."
            )
            return f
        except (OSError, ValueError):
            continue
    obter().warning(
        f"      aviso:  a fonte '{nome}' não foi encontrada e nenhuma fonte de "
        "reserva do sistema abriu; a barra de título vai sair na fonte embutida "
        "do Pillow."
    )
    try:
        return ImageFont.load_default(size=tamanho)
    except TypeError:  # Pillow antigo, sem o argumento 'size'
        return ImageFont.load_default()


def _silhueta(largura: int, altura: int, raio: int, supersample: int = 4) -> Any:
    """Mascara L do cartao: retangulo de cantos arredondados, com antialias.

    Desenhar em 4x e reduzir com LANCZOS da ~80 niveis de cinza no arco; o
    rounded_rectangle direto no tamanho final sai serrilhado.
    """
    from PIL import Image, ImageDraw, ImageFilter

    grande = Image.new("L", (largura * supersample, altura * supersample), 0)
    ImageDraw.Draw(grande).rounded_rectangle(
        (0, 0, largura * supersample - 1, altura * supersample - 1),
        radius=max(0, raio) * supersample,
        fill=255,
    )
    pequena = grande.resize((largura, altura), Image.LANCZOS)
    return pequena.filter(ImageFilter.GaussianBlur(0.6))


def _mascara(comp: Composicao, destino: Path) -> Path:
    return _salvar(
        _silhueta(comp.cartao_largura, comp.cartao_altura, comp.cartao_raio), destino
    )


def _atras_do_cartao(comp: Composicao, destino: Path) -> Path:
    """Sombra sob o cartao (+ vinheta opcional), furada pela silhueta do cartao.

    O furo nao e detalhe: sem ele o preto da sombra aparece POR DENTRO dos
    cantos arredondados -- justamente onde deveria aparecer o fundo borrado.
    """
    from PIL import Image, ImageDraw, ImageFilter

    camada = Image.new("RGBA", (LARGURA_SAIDA, ALTURA_SAIDA), (0, 0, 0, 0))

    if comp.vinheta > 0.0:
        # Vinheta por gradiente radial barato: um degrade em L, esticado.
        raio_max = math.hypot(LARGURA_SAIDA / 2, ALTURA_SAIDA / 2)
        mapa = Image.new("L", (LARGURA_SAIDA // 8, ALTURA_SAIDA // 8), 0)
        px = mapa.load()
        for j in range(mapa.height):
            for i in range(mapa.width):
                dx = (i + 0.5) * 8 - LARGURA_SAIDA / 2
                dy = (j + 0.5) * 8 - ALTURA_SAIDA / 2
                r = math.hypot(dx, dy) / raio_max
                px[i, j] = int(255 * min(1.0, max(0.0, (r - 0.55) / 0.45)) ** 2)
        mapa = mapa.resize((LARGURA_SAIDA, ALTURA_SAIDA), Image.BILINEAR)
        vinheta = Image.new("RGBA", camada.size, (0, 0, 0, 0))
        vinheta.putalpha(mapa.point(lambda v: int(v * comp.vinheta)))
        camada = Image.alpha_composite(camada, vinheta)

    if comp.sombra_opacidade > 0.0:
        expandido_l = comp.cartao_largura + 2 * comp.sombra_expansao
        expandido_a = comp.cartao_altura + 2 * comp.sombra_expansao
        forma = _silhueta(
            expandido_l, expandido_a, comp.cartao_raio + comp.sombra_expansao
        )
        mancha = Image.new("L", camada.size, 0)
        mancha.paste(
            forma,
            (
                comp.cartao_x - comp.sombra_expansao + comp.sombra_dx,
                comp.cartao_y - comp.sombra_expansao + comp.sombra_dy,
            ),
        )
        mancha = mancha.filter(ImageFilter.GaussianBlur(comp.sombra_sigma))
        mancha = mancha.point(lambda v: int(v * comp.sombra_opacidade))
        sombra = Image.new("RGBA", camada.size, _cor_rgb(comp.sombra_cor) + (0,))
        sombra.putalpha(mancha)
        camada = Image.alpha_composite(camada, sombra)

    # Furo: o que cai dentro do cartao seria tapado por ele de qualquer jeito,
    # menos nos cantos arredondados -- e la o furo e obrigatorio.
    furo = Image.new("L", camada.size, 0)
    furo.paste(
        _silhueta(comp.cartao_largura, comp.cartao_altura, comp.cartao_raio),
        (comp.cartao_x, comp.cartao_y),
    )
    alfa = camada.getchannel("A")
    camada.putalpha(
        Image.composite(Image.new("L", camada.size, 0), alfa, furo)
    )
    return _salvar(camada, destino)


def _na_frente_do_cartao(comp: Composicao, destino: Path) -> Path | None:
    """Fio de luz na borda do cartao + degrade sob a legenda. Opcional.

    As duas coisas vivem no mesmo PNG porque as duas sao estaticas e as duas
    entram DEPOIS do cartao e ANTES da legenda -- uma sobreposicao so.
    """
    from PIL import Image, ImageChops, ImageDraw

    if comp.traco_largura <= 0 and not comp.scrim_ativo:
        return None

    camada = Image.new("RGBA", (LARGURA_SAIDA, ALTURA_SAIDA), (0, 0, 0, 0))

    if comp.scrim_ativo and comp.scrim_opacidade > 0:
        topo = max(comp.cartao_y, min(comp.scrim_y_inicio, comp.cartao_base))
        base = max(topo + 1, min(comp.scrim_y_fim, comp.cartao_base))
        rampa = Image.new("L", (1, ALTURA_SAIDA), 0)
        px = rampa.load()
        for y in range(ALTURA_SAIDA):
            if y <= topo:
                v = 0.0
            elif y >= base:
                v = 1.0
            else:
                v = (y - topo) / (base - topo)
            px[0, y] = int(255 * v * comp.scrim_opacidade)
        degrade = Image.new("RGBA", camada.size, _cor_rgb(comp.scrim_cor) + (0,))
        degrade.putalpha(rampa.resize(camada.size, Image.BILINEAR))
        # Recortado pela silhueta: o degrade e do CARTAO, nao da tela.
        recorte = Image.new("L", camada.size, 0)
        recorte.paste(
            _silhueta(comp.cartao_largura, comp.cartao_altura, comp.cartao_raio),
            (comp.cartao_x, comp.cartao_y),
        )
        degrade.putalpha(
            Image.composite(degrade.getchannel("A"), Image.new("L", camada.size, 0), recorte)
        )
        camada = Image.alpha_composite(camada, degrade)

    if comp.traco_largura > 0 and comp.traco_opacidade > 0:
        # O fio e a DIFERENCA de duas silhuetas, nao um rounded_rectangle com
        # 'outline': o outline do Pillow nao tem antialias e deixava o fio
        # serrilhado justo nos arcos -- o mesmo motivo pelo qual a mascara do
        # cartao ja era desenhada em 4x e reduzida.
        espessura = max(1, int(comp.traco_largura))
        fora = Image.new("L", camada.size, 0)
        fora.paste(
            _silhueta(comp.cartao_largura, comp.cartao_altura, comp.cartao_raio),
            (comp.cartao_x, comp.cartao_y),
        )
        dentro = Image.new("L", camada.size, 0)
        dentro.paste(
            _silhueta(
                comp.cartao_largura - 2 * espessura,
                comp.cartao_altura - 2 * espessura,
                max(0, comp.cartao_raio - espessura),
            ),
            (comp.cartao_x + espessura, comp.cartao_y + espessura),
        )
        anel = ImageChops.subtract(fora, dentro)
        traco = Image.new("RGBA", camada.size, _cor_rgb(comp.traco_cor) + (0,))
        traco.putalpha(
            anel.point(lambda v: int(v * min(1.0, max(0.0, comp.traco_opacidade))))
        )
        camada = Image.alpha_composite(camada, traco)

    return _salvar(camada, destino)


def _quebrar_titulo(
    texto: str, fonte: Any, largura: int, max_linhas: int
) -> tuple[list[str], bool]:
    """Quebra o titulo por LARGURA MEDIDA e diz se sobrou texto de fora.

    O "sobrou" e o que permite escolher o corpo da fonte pela pergunta certa --
    "cabe inteiro neste tamanho?" -- em vez de encolher ate a linha unica, que
    espremeria um titulo de duas linhas ate o corpo minimo sem necessidade.
    """
    palavras = [p for p in str(texto).split() if p]
    linhas: list[str] = []
    atual = ""
    for i, palavra in enumerate(palavras):
        tentativa = f"{atual} {palavra}".strip()
        if atual and fonte.getlength(tentativa) > largura:
            linhas.append(atual)
            atual = palavra
            if len(linhas) >= max_linhas:
                return linhas, True
        else:
            atual = tentativa
    if atual:
        linhas.append(atual)
    # Uma palavra sozinha mais larga que a caixa nao tem onde quebrar.
    sobrou = any(fonte.getlength(l) > largura for l in linhas)
    return (linhas or [""]), sobrou


def pilula_titulo(comp: Composicao, titulo: str, destino: Path) -> dict[str, Any]:
    """Desenha a pilula do titulo e devolve a geometria que o overlay precisa.

    O texto ENCOLHE ate caber em no maximo duas linhas; se nem no menor corpo
    couber, a ultima linha ganha reticencias. Titulo de clipe e escrito por
    um modelo e ninguem garante o tamanho.
    """
    from PIL import Image, ImageDraw

    texto = " ".join(str(titulo or "").split())
    if comp.titulo_maiusculas:
        texto = texto.upper()

    util = max(80, comp.titulo_largura_maxima - 2 * comp.titulo_padding_h)
    if comp.titulo_acento in ("barra", "circulo"):
        util -= comp.titulo_acento_largura + comp.titulo_acento_gap

    # Encolhe SO enquanto o titulo nao cabe inteiro em ate duas linhas. Uma
    # unica linha e melhor quando da, mas duas linhas no corpo cheio leem muito
    # melhor do que uma linha no corpo minimo.
    tamanho = comp.titulo_tamanho
    fonte = _fonte(comp.titulo_fonte, comp.titulo_arquivo, tamanho)
    linhas, sobrou = _quebrar_titulo(texto, fonte, util, 2)
    while sobrou and tamanho > comp.titulo_tamanho_minimo:
        tamanho -= 2
        fonte = _fonte(comp.titulo_fonte, comp.titulo_arquivo, tamanho)
        linhas, sobrou = _quebrar_titulo(texto, fonte, util, 2)

    cortado = False
    if sobrou:
        # Nem no corpo minimo coube: a ultima linha perde caractere ate caber e
        # ganha reticencias. Titulo de clipe e escrito por um modelo e ninguem
        # garante o tamanho -- e um titulo cortado SEM reticencias mente sobre o
        # que foi escrito.
        cortado = True
        while linhas and len(linhas[-1]) > 1 and fonte.getlength(linhas[-1] + "…") > util:
            linhas[-1] = linhas[-1][:-1].rstrip()
        if linhas:
            linhas[-1] = linhas[-1].rstrip(" ,;:-") + "…"

    ascendente, descendente = fonte.getmetrics()
    altura_linha = ascendente + descendente
    largura_texto = int(max(fonte.getlength(l) for l in linhas)) if linhas else 0

    largura_pilula = largura_texto + 2 * comp.titulo_padding_h
    if comp.titulo_acento in ("barra", "circulo"):
        largura_pilula += comp.titulo_acento_largura + comp.titulo_acento_gap
    largura_pilula = _par(min(comp.titulo_largura_maxima, max(160, largura_pilula)))
    # O respiro e por LINHA, nao por pilula: com um respiro fixo, a pilula de
    # duas linhas saia com 12px de folga no topo e no pe e lia como texto
    # espremido numa tarja.
    respiro = max(16, int(altura_linha * 0.30))
    altura_pilula = _par(
        max(comp.titulo_altura, altura_linha * len(linhas) + 2 * respiro)
    )

    # A pilula sai pela mesma porta da mascara do cartao (silhueta em 4x
    # reduzida com LANCZOS): rounded_rectangle direto deixa o arco serrilhado,
    # e a pilula fica sobre um fundo borrado, onde a escadinha aparece.
    imagem = Image.new("RGBA", (largura_pilula, altura_pilula), (0, 0, 0, 0))
    forma = _silhueta(
        largura_pilula, altura_pilula, min(comp.titulo_raio, altura_pilula // 2)
    )
    fundo = Image.new("RGBA", imagem.size, _cor_rgb(comp.titulo_pilula_cor) + (0,))
    fundo.putalpha(
        forma.point(
            lambda v: int(v * min(1.0, max(0.0, comp.titulo_pilula_opacidade)))
        )
    )
    imagem = Image.alpha_composite(imagem, fundo)
    d = ImageDraw.Draw(imagem)

    x_texto = comp.titulo_padding_h
    if comp.titulo_acento in ("barra", "circulo"):
        cor = _cor_rgb(comp.titulo_acento_cor)
        if comp.titulo_acento == "barra":
            larg = max(2, comp.titulo_acento_largura)
            alt = max(4, min(comp.titulo_acento_altura, altura_pilula - 24))
            marca = _silhueta(larg, alt, larg // 2)
        else:
            larg = alt = max(4, comp.titulo_acento_largura)
            marca = _silhueta(larg, alt, larg // 2)
        topo = (altura_pilula - alt) // 2
        camada = Image.new("RGBA", imagem.size, cor + (0,))
        alfa = Image.new("L", imagem.size, 0)
        alfa.paste(marca, (x_texto, topo))
        camada.putalpha(alfa)
        imagem = Image.alpha_composite(imagem, camada)
        d = ImageDraw.Draw(imagem)
        x_texto += comp.titulo_acento_largura + comp.titulo_acento_gap

    y_texto = (altura_pilula - altura_linha * len(linhas)) // 2
    for i, linha in enumerate(linhas):
        x = x_texto
        if comp.titulo_alinhamento == "centro" and len(linhas) > 1:
            x = x_texto + (largura_texto - int(fonte.getlength(linha))) // 2
        d.text((x, y_texto + i * altura_linha), linha, font=fonte, fill=_cor_rgb(comp.titulo_cor) + (255,))

    _salvar(imagem, destino)
    return {
        "arquivo": destino,
        "largura": largura_pilula,
        "altura": altura_pilula,
        "linhas": len(linhas),
        "tamanho": tamanho,
        "truncado": cortado,
    }


def gerar_ativos(
    comp: Composicao,
    titulo: str,
    trabalho: Path,
    *,
    gancho: str = "",
    conclusao: str = "",
) -> dict[str, Any]:
    """Gera (ou reaproveita) os PNG desta composicao e devolve os caminhos.

    Os arquivos levam no nome a marca de DESENHO -- o hash so dos campos que
    viram pixel. Nao a impressao cheia: mexer no ganho do punch ou no loudnorm
    nao muda um pixel dos PNG, e usar a impressao cheia redesenhava os tres a
    cada ajuste de preset, deixando o conjunto anterior na pasta para sempre.

    Um PNG ja existente so e reaproveitado se ABRIR INTEIRO: um arquivo
    truncado (processo morto no meio do save de uma versao antiga) travaria
    aquele preset em toda rodada seguinte.
    """
    trabalho = Path(trabalho)
    trabalho.mkdir(parents=True, exist_ok=True)
    marca = comp.marca_desenho()
    fecho: dict[str, Any] | None = None

    mascara = trabalho / f"cartao_{marca}_mascara.png"
    atras = trabalho / f"cartao_{marca}_atras.png"
    frente = trabalho / f"cartao_{marca}_frente.png"

    try:
        if not _png_intacto(mascara):
            _mascara(comp, mascara)
        if not _png_intacto(atras):
            _atras_do_cartao(comp, atras)
        if comp.traco_largura <= 0 and not comp.scrim_ativo:
            frente = None  # type: ignore[assignment]
        elif not _png_intacto(frente):
            if _na_frente_do_cartao(comp, frente) is None:
                frente = None  # type: ignore[assignment]

        # De quem e o slot do topo. Com o gancho ligado ele e o dono e o
        # titulo NAO aparece em pixel nenhum -- vive no nome do arquivo, em
        # metadados.json e no relatorio. Desligar `gancho.ativo` devolve a
        # caixa permanente de titulo, e e esse o escape.
        pilula = None
        texto_do_topo = ""
        if comp.gancho_ativo:
            # Sem gancho escrito o topo fica LIMPO. Cair de volta no titulo
            # aqui ressuscitaria a caixa permanente justamente no clipe em
            # que o modelo nao entregou gancho -- o oposto do pedido.
            texto_do_topo = str(gancho or "").strip()
        elif comp.titulo_ativo:
            texto_do_topo = str(titulo or "").strip()
        if texto_do_topo:
            alvo = trabalho / f"titulo_{marca}_{_marca_texto(texto_do_topo)}.png"
            pilula = pilula_titulo(comp, texto_do_topo, alvo)

        # A conclusao usa a MESMA pilula do gancho: mesma fonte, mesmo fundo,
        # mesmos cantos. Sao a abertura e o fecho do mesmo clipe e leem como
        # par; inventar um segundo estilo aqui so criaria mais um numero para
        # manter em sincronia.
        fecho = None
        texto_fecho = str(conclusao or "").strip()
        if texto_fecho:
            alvo_f = trabalho / f"conclusao_{marca}_{_marca_texto(texto_fecho)}.png"
            fecho = pilula_titulo(comp, texto_fecho, alvo_f)
        _limpar_ativos_antigos(trabalho, marca)
    except ImportError as exc:  # Pillow ausente
        raise ErroRender(
            "o preset de composição precisa do Pillow para desenhar o cartão e a "
            "barra de título, e ele não está instalado neste ambiente.",
            detalhe=str(exc),
            sugestao=(
                "instale as dependências do projeto:  "
                ".venv\\Scripts\\pip install -r requirements.txt   "
                "— ou renderize com um preset sem composição (--preset bold-amarelo)."
            ),
        ) from exc
    except OSError as exc:
        raise ErroRender(
            f"não consegui gravar os arquivos de composição em {trabalho}.",
            detalhe=f"{type(exc).__name__}: {exc}",
            sugestao=(
                "libere espaço em disco (ou feche o programa que está com essa pasta "
                "aberta) e repita o mesmo comando."
            ),
        ) from exc

    return {
        "mascara": mascara,
        "atras": atras,
        "frente": frente,
        "pilula": pilula,
        "conclusao": fecho,
    }


def _limpar_ativos_antigos(trabalho: Path, marca: str) -> None:
    """Apaga os PNG de composicoes anteriores. Nunca levanta.

    Ajustar um preset algumas vezes deixava um conjunto de cartao_*.png por
    tentativa em _trabalho/. Sao poucos KB cada, mas e lixo com nome de hash
    que ninguem sabe interpretar depois.
    """
    for antigo in list(trabalho.glob("cartao_*.png")) + list(trabalho.glob("titulo_*.png")):
        if f"_{marca}_" in antigo.name:
            continue
        try:
            antigo.unlink()
        except OSError:
            continue


def _marca_texto(texto: str) -> str:
    return hashlib.sha256(str(texto).encode("utf-8")).hexdigest()[:8]


# ==========================================================================
# Filtergraph
# ==========================================================================


def _cor_ff(hexa: str, opacidade: float) -> str:
    """'#RRGGBB' + alfa -> '0xRRGGBB@0.55', a sintaxe de cor do ffmpeg."""
    r, g, b = _cor_rgb(hexa)
    alfa = min(1.0, max(0.0, float(opacidade)))
    return f"0x{r:02X}{g:02X}{b:02X}@{alfa:.3f}"


@dataclass(frozen=True)
class Montagem:
    """O que o estagio de render precisa passar ao ffmpeg."""

    entradas: list[str]
    filtro: str
    rotulo_video: str
    rotulo_audio: str | None
    punches: list[float]
    pilula: dict[str, Any] | None


def montar(
    *,
    comp: Composicao,
    ativos: dict[str, Any],
    recorte: dict[str, int],
    duracao: float,
    fps: str,
    punches: Sequence[float],
    filtro_legenda: str | None,
    tem_audio: bool,
    pitch: bool,
    entradas_video: int = 1,
) -> Montagem:
    """Monta o filter_complex inteiro e a lista de entradas extras do ffmpeg.

    'recorte' e o retangulo 9:16 que a F3 ja calculava (reframe por rosto). O
    cartao e ele, ampliado e com movimento; o fundo e ele tambem, borrado --
    por isso o crop acontece UMA vez e o resultado e dividido em dois ramos.
    """
    entradas: list[str] = []
    indices: dict[str, int] = {}

    def _entrada(caminho: Path, *, loop: bool = False) -> int:
        if loop:
            # A taxa do PNG casa com a de SAIDA: mais alta faz o ffmpeg decodificar
            # imagem que ele mesmo joga fora; mais baixa degrada o fade.
            entradas.extend(["-loop", "1", "-framerate", str(fps)])
        entradas.extend(["-i", str(Path(caminho).resolve())])
        # Os PNG entram DEPOIS das entradas de video. Num clipe v2 a fonte
        # ocupa os indices 0..N-1 (uma entrada por segmento, cada uma com o
        # seu -ss/-t), entao a primeira mascara e N, nao 1.
        return len(indices) + max(1, int(entradas_video))

    indices["mascara"] = _entrada(ativos["mascara"])
    indices["atras"] = _entrada(ativos["atras"])
    if ativos.get("frente"):
        indices["frente"] = _entrada(ativos["frente"])
    if ativos.get("pilula"):
        # O PNG do titulo PRECISA de '-loop 1': com uma imagem so o filtro fade
        # nao tem em que interpolar e a pilula nunca aparece (medido: o mp4 sai
        # 19x menor, sem pilula nenhuma). A mascara e a sombra NAO precisam --
        # o framesync repete o ultimo quadro sozinho (provado em 40s de clipe).
        indices["pilula"] = _entrada(ativos["pilula"]["arquivo"], loop=True)
    if ativos.get("conclusao"):
        # Mesmo motivo do '-loop 1' da pilula: sem ele o fade nao tem em que
        # interpolar e a conclusao nunca aparece.
        indices["conclusao"] = _entrada(ativos["conclusao"]["arquivo"], loop=True)

    cl, ca = comp.cartao_largura, comp.cartao_altura
    pre_l = _par(cl * comp.kenburns_prescale)
    pre_a = _par(ca * comp.kenburns_prescale)
    escuro = max(0.0, 1.0 - comp.fundo_escurecer)

    partes: list[str] = []
    # setpts=PTS-STARTPTS nao e enfeite: o '-ss' de entrada deixa um residuo no
    # timestamp da primeira imagem (0,0165s medido com -ss 200) e as expressoes
    # de overlay leem 't', que e esse timestamp. Sem zerar, a barra de progresso
    # e o deslize do titulo comecam com um atraso que MUDA a cada clipe.
    # Concatenacao dos segmentos, ANTES do crop. Depois daqui o grafo inteiro
    # nao sabe que o clipe foi montado de pedacos -- e por isso que o v1
    # continua saindo byte a byte igual: com uma entrada so, nada deste bloco
    # e emitido e a fonte segue sendo [0:v].
    n_seg = max(1, int(entradas_video))
    fonte_v = "0:v"
    if n_seg > 1:
        # setpts POR SEGMENTO antes de juntar: cada entrada carrega o residuo
        # de timestamp do seu proprio '-ss', e o filtro concat exige que cada
        # trecho comece em zero. Sem isso os trechos entram com buracos de
        # tempo entre si e a duracao de saida sai errada.
        for i in range(n_seg):
            partes.append(f"[{i}:v]setpts=PTS-STARTPTS[s{i}v]")
        rotulos = "".join(f"[s{i}v]" for i in range(n_seg))
        partes.append(f"{rotulos}concat=n={n_seg}:v=1:a=0[vcat]")
        fonte_v = "vcat"
    partes.append(
        f"[{fonte_v}]crop={recorte['largura']}:{recorte['altura']}:{recorte['x']}:{recorte['y']},"
        "setpts=PTS-STARTPTS,split=2[bgsrc][cardsrc]"
    )
    # Fundo: borrar em miniatura e reampliar sai 7,7x mais barato que borrar em
    # 1080x1920 e mede PSNR 45,7 dB contra o borrao caro -- diferenca invisivel.
    partes.append(
        f"[bgsrc]scale={comp.fundo_proxy_largura}:{comp.fundo_proxy_altura}:flags=area,"
        f"gblur=sigma={comp.fundo_sigma:g}:steps=3,"
        f"lutyuv=y=val*{escuro:.3f}:"
        f"u='(val-128)*{comp.fundo_saturacao:.3f}+128':"
        f"v='(val-128)*{comp.fundo_saturacao:.3f}+128',"
        f"scale={LARGURA_SAIDA}:{ALTURA_SAIDA}:flags=bicubic,setsar=1,format=yuv420p[bg]"
    )
    # Cartao: a ampliacao com 'neighbor' antes do zoompan e o anti-tremor.
    partes.append(
        f"[cardsrc]scale={pre_l}:{pre_a}:flags=neighbor,"
        f"zoompan=z='{expressao_zoom(duracao, punches, comp)}':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d=1:s={cl}x{ca}:fps={fps},setsar=1,format=yuva420p[cardw]"
    )
    partes.append(f"[{indices['mascara']}:v]format=gray[mk]")
    partes.append("[cardw][mk]alphamerge[card]")
    partes.append(f"[{indices['atras']}:v]format=yuva420p[atras]")
    partes.append("[bg][atras]overlay=0:0:format=yuv420[bgs]")
    partes.append(
        f"[bgs][card]overlay={comp.cartao_x}:{comp.cartao_y}:format=yuv420[comp]"
    )
    ultimo = "comp"

    if "frente" in indices:
        partes.append(f"[{indices['frente']}:v]format=yuva420p[frente]")
        partes.append(f"[{ultimo}][frente]overlay=0:0:format=yuv420[compf]")
        ultimo = "compf"

    if comp.progresso_ativo and comp.progresso_altura > 0:
        bx = _par(comp.cartao_x + comp.progresso_recuo)
        bw = _par(comp.cartao_largura - 2 * comp.progresso_recuo)
        bh = comp.progresso_altura
        by = _par(comp.progresso_y)
        # A barra fecha ANTES do fade de saida comecar: com o denominador na
        # duracao cheia, os ultimos 0,3s -- justamente o 100% -- acontecem com a
        # tela ja apagando, e o clipe nunca mostra a barra cheia.
        corrida = max(0.1, duracao - comp.fade_s)
        # drawbox NAO anima (nao tem 'eval' neste ffmpeg, e 't' la dentro e a
        # ESPESSURA, nao o tempo): o preenchimento e uma fonte de cor deslizando
        # por overlay, dentro de uma faixa recortada do proprio quadro.
        partes.append(f"[{ultimo}]split=2[c0][c1]")
        partes.append(
            f"[c1]crop={bw}:{bh}:{bx}:{by},"
            f"drawbox=x=0:y=0:w={bw}:h={bh}:"
            f"color={_cor_ff(comp.progresso_trilho_cor, comp.progresso_trilho_opacidade)}:t=fill[trk]"
        )
        partes.append(
            f"color=c={_cor_ff(comp.progresso_cor, comp.progresso_opacidade)}:"
            f"s={bw}x{bh}:r={fps}:d={duracao:.3f}[fil]"
        )
        preenchida = f"[trk][fil]overlay=x='{bw}*min(t/{corrida:.3f},1)-{bw}':y=0:eval=frame"
        if comp.progresso_contorno > 0:
            # O trilho claro some sobre conteudo claro (medido num plano de
            # concreto branco). O fio escuro por cima do conjunto devolve a
            # leitura de "x% de um trilho" em qualquer fundo.
            partes.append(
                preenchida
                + f"[barf];[barf]drawbox=x=0:y=0:w={bw}:h={bh}:"
                f"color={_cor_ff(comp.progresso_contorno_cor, comp.progresso_contorno_opacidade)}:"
                f"t={int(comp.progresso_contorno)}[bar]"
            )
        else:
            partes.append(preenchida + "[bar]")
        partes.append(f"[c0][bar]overlay={bx}:{by}:format=yuv420[compb]")
        ultimo = "compb"

    if "pilula" in indices:
        p = ativos["pilula"]
        # O gancho mora mais abaixo que a caixa de titulo morava: o topo do
        # canvas pertence a UI do Shorts, e a pilula em y=64 caia dentro dela.
        alvo_y = comp.gancho_y if comp.gancho_ativo else comp.titulo_y
        desloca = -(int(p["altura"]) + alvo_y)
        if comp.titulo_alinhamento == "esquerda":
            px = str(comp.titulo_x)
        else:
            px = "(W-w)/2"
        # A guarda do fade nao e zelo: 'fade' com d=0 NAO e desligado, cai no
        # padrao de 25 QUADROS. Um preset pedindo "pilula sem fade" receberia
        # 0,42s de fade -- mais do que varios valores explicitos pequenos.
        ramo = ["format=rgba"]
        if comp.titulo_fade_s > 0:
            ramo.append(f"fade=t=in:st=0:d={comp.titulo_fade_s:g}:alpha=1")
        if comp.gancho_ativo and comp.gancho_fade_saida_s > 0:
            # Mesma guarda do fade de entrada, pelo mesmo motivo: 'fade' com
            # d=0 nao e desligado, cai no padrao de 25 QUADROS. O 'st' nunca
            # e negativo -- gancho mais curto que o proprio fade sairia
            # desbotando antes de aparecer.
            saida = min(float(comp.gancho_fade_saida_s), float(comp.gancho_duracao_s))
            ramo.append(
                f"fade=t=out:st={max(0.0, comp.gancho_duracao_s - saida):.3f}"
                f":d={saida:g}:alpha=1"
            )
        partes.append(f"[{indices['pilula']}:v]" + ",".join(ramo) + "[pilula]")
        # format=yuv420 explicito, nunca o 'auto' padrao: com 'auto' o overlay
        # negocia um formato intermediario e faz o quadro INTEIRO dar uma volta
        # de croma -- 1,6 milhao de pixels alterados fora da pilula e +23% de
        # tempo de render, medidos. Vale para TODO overlay deste grafo.
        # 'enable' corta o overlay inteiro depois do gancho: passado o
        # recorte, o topo fica limpo E o ffmpeg para de compor a camada.
        # Sem ele a pilula ficaria ate o ultimo frame, que e o que a F4a
        # fazia e o que esta troca existe para desfazer.
        recorte_temporal = (
            f":enable='between(t,0,{comp.gancho_duracao_s:g})'"
            if comp.gancho_ativo
            else ""
        )
        partes.append(
            f"[{ultimo}][pilula]overlay=x={px}:"
            f"y='{alvo_y}+({desloca})*pow(1-min(t/{max(0.01, comp.titulo_deslize_s):g},1),3)'"
            f"{recorte_temporal}:"
            "format=yuv420[compt]"
        )
        ultimo = "compt"

    if "conclusao" in indices:
        c = ativos["conclusao"]
        # Comeca `conclusao_duracao_s` antes do fim e vai ate o fim do clipe.
        # O piso em 0 protege o clipe curto demais: sem ele o 'between' sairia
        # com inicio negativo e o overlay valeria o clipe inteiro.
        inicio_c = max(0.0, float(duracao) - float(comp.conclusao_duracao_s))
        ramo_c = ["format=rgba"]
        if comp.conclusao_fade_s > 0:
            # A mesma guarda do d=0 de sempre: 'fade' com d=0 nao e desligado,
            # cai no padrao de 25 quadros.
            fade_c = min(float(comp.conclusao_fade_s), float(comp.conclusao_duracao_s))
            ramo_c.append(f"fade=t=in:st={inicio_c:.3f}:d={fade_c:g}:alpha=1")
        partes.append(f"[{indices['conclusao']}:v]" + ",".join(ramo_c) + "[concl]")
        partes.append(
            f"[{ultimo}][concl]overlay=x=(W-w)/2:y={int(comp.conclusao_y)}"
            f":enable='between(t,{inicio_c:.3f},{float(duracao):.3f})'"
            ":format=yuv420[compc]"
        )
        ultimo = "compc"

    cauda = []
    if filtro_legenda:
        # O filtro vem PRONTO de ffmpeg_utils.opcao_subtitles(), que e o unico
        # lugar do projeto que sabe escapar caminho do Windows para dentro de
        # um filtergraph. Remontar aqui duplicaria essa regra.
        cauda.append(filtro_legenda)
    if comp.fade_s > 0:
        cauda.append(f"fade=t=in:st=0:d={comp.fade_s:g}")
        cauda.append(f"fade=t=out:st={max(0.0, duracao - comp.fade_s):.3f}:d={comp.fade_s:g}")
    cauda.append("format=yuv420p")
    partes.append(f"[{ultimo}]" + ",".join(cauda) + "[vout]")

    rotulo_audio = None
    if tem_audio:
        fonte_a = "0:a"
        if n_seg > 1:
            for i in range(n_seg):
                partes.append(f"[{i}:a]asetpts=PTS-STARTPTS[s{i}a]")
            # O video corta seco (jump cut e idiomatico em Shorts); o audio
            # NAO pode -- emenda de forma de onda vira clique audivel. O
            # crossfade e curto de proposito: 15 ms nao se ouve como transicao,
            # so mata o estalo.
            #
            # Efeito colateral conhecido e aceito: cada acrossfade ENCURTA o
            # audio pela duracao do fade. Com 15 ms e no maximo duas juncoes
            # sao 30 ms no pior caso -- dentro da tolerancia de +-0,5s da prova
            # de duracao, e o '-t' de saida fecha o arquivo de qualquer jeito.
            d = max(0.001, float(comp.juncao_crossfade_s))
            atual = "s0a"
            for i in range(1, n_seg):
                destino = "acat" if i == n_seg - 1 else f"ax{i}"
                partes.append(
                    f"[{atual}][s{i}a]acrossfade=d={d:g}:c1=tri:c2=tri[{destino}]"
                )
                atual = destino
            fonte_a = atual
        # O loudnorm roda no resultado JA CONCATENADO: medir cada segmento
        # sozinho e normalizar depois daria degraus de volume nas juncoes.
        #
        # SEMENTE F7 (narracao/TTS) -- ponto de juncao, nao implementacao:
        # uma trilha de narracao entraria como mais uma entrada de audio e se
        # juntaria a esta cadeia com 'amix' AQUI, entre `fonte_a` e a
        # cadeia_audio(), para que o loudnorm normalize a MISTURA e nao a voz
        # e o ambiente em separado. Nada disso esta implementado, e nao deve
        # ser implementado sem pedido explicito.
        partes.append(f"[{fonte_a}]{cadeia_audio(comp, duracao, pitch=pitch)}[aout]")
        rotulo_audio = "[aout]"

    return Montagem(
        entradas=entradas,
        filtro=";".join(partes),
        rotulo_video="[vout]",
        rotulo_audio=rotulo_audio,
        punches=[float(p) for p in punches],
        pilula=ativos.get("pilula"),
    )


def cadeia_audio(comp: Composicao, duracao: float, *, pitch: bool) -> str:
    """EQ suave -> loudnorm -> fades. Nesta ordem, e por medicao.

    Com o loudnorm por ULTIMO o true peak fica no alvo (-1,5 dBTP medido nos
    tres trechos de teste). Invertendo -- loudnorm e depois EQ -- o realce de
    presenca entra DEPOIS do limitador e o pico volta a subir: medimos
    -0,1 dBTP num trecho, 1,4 dB acima do alvo, ou seja quase estourando.

    O pitch e opcional e chega ANTES de tudo. O 'aresample' que abre a cadeia
    nao e enfeite: asetrate multiplica a taxa DECLARADA, e a fonte deste
    projeto e 44100 Hz -- pedir 48000*1.005 num fluxo de 44,1 kHz desloca o
    pitch em +9,4% (voz de esquilo) e encurta o audio de 61,8s para 56,7s.
    Normalizando para 48 kHz primeiro, o fator vira exatamente +0,5%, e o
    atempo devolve a duracao original.
    """
    etapas: list[str] = []
    if pitch:
        razao = max(1.0001, float(comp.pitch_razao))
        etapas.extend(
            [
                "aresample=48000",
                f"asetrate=48000*{razao:g}",
                "aresample=48000",
                f"atempo={1.0 / razao:.11f}",
            ]
        )
    if comp.audio_eq:
        etapas.append(comp.audio_eq)
    etapas.append(
        f"loudnorm=I={comp.audio_i:g}:TP={comp.audio_tp:g}:LRA={comp.audio_lra:g}"
    )
    etapas.append("aresample=48000")
    if comp.fade_s > 0:
        etapas.append(f"afade=t=in:st=0:d={comp.fade_s:g}")
        etapas.append(
            f"afade=t=out:st={max(0.0, duracao - comp.fade_s):.3f}:d={comp.fade_s:g}"
        )
    return ",".join(etapas)
