"""Provas da F6 -- camada editorial. Espelha ui/provas/prova_f5.py.

Sem pytest e sem dependencia nova, como a casa faz: um main(argv) que roda os
casos, cronometra cada um e devolve 0 se todos passaram.

Duas famílias, e a separacao importa:

  ESTRUTURAIS  rodam so com o repositorio. Comparam filtergraph, conteudo de
               .ass, resultado de validador e texto de prompt. Nao abrem
               ffmpeg, nao leem video, nao precisam de fonte instalada.

  FISICAS      exigem ffmpeg e arquivo real: duracao medida, -14 LUFS,
               capa.jpg, frame do gancho. Rodam com --fisicas, na maquina
               que tem a cadeia completa.

Sem argumento roda so as ESTRUTURAIS -- e o modo que funciona em qualquer
clone, inclusive no sandbox web.

    python provas/prova_f6.py                 # estruturais
    python provas/prova_f6.py --fisicas       # fisicas (precisa de ffmpeg)
    python provas/prova_f6.py E1 E2           # casos escolhidos

Convencao deste arquivo: comentarios e docstrings em PT-BR sem acento;
mensagens dirigidas ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

DIR_FIXTURES = RAIZ / "provas" / "fixtures"

_verde, _vermelho, _amarelo, _zero = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
if sys.platform == "win32":
    # O terminal do Windows so entende ANSI depois de habilitar; sem isso a
    # saida vira lixo de escape. Mais barato desligar a cor do que detectar.
    import os

    if not os.environ.get("WT_SESSION") and not os.environ.get("ANSICON"):
        _verde = _vermelho = _amarelo = _zero = ""


class Falhou(AssertionError):
    pass


class Pulou(Exception):
    """A prova nao pode rodar aqui -- falta artefato ou ferramenta."""


def confere(condicao: bool, descricao: str, detalhe: str = "") -> None:
    if condicao:
        print(f"    {_verde}ok{_zero}  {descricao}" + (f"  [{detalhe}]" if detalhe else ""))
        return
    print(f"    {_vermelho}FALHOU{_zero}  {descricao}" + (f"  [{detalhe}]" if detalhe else ""))
    raise Falhou(descricao)


# ==========================================================================
# Infraestrutura
# ==========================================================================

# Ativos falsos: `montar()` so precisa dos CAMINHOS para montar as entradas.
# Nenhum PNG e aberto, entao a prova de filtergraph roda sem Pillow, sem fonte
# instalada e sem tocar o disco.
def ativos_falsos(*, com_pilula: bool = True) -> dict[str, Any]:
    base = {
        "mascara": Path("/f/mascara.png"),
        "atras": Path("/f/atras.png"),
        "frente": Path("/f/frente.png"),
    }
    if com_pilula:
        base["pilula"] = {
            "arquivo": Path("/f/pilula.png"),
            "largura": 810,
            "altura": 108,
            "linhas": 1,
            "tamanho": 44,
            "truncado": False,
        }
    return base


RECORTE_PADRAO = {"largura": 608, "altura": 1080, "x": 336, "y": 0}


def filtergraph(
    comp: Any,
    *,
    duracao: float = 42.0,
    punches: tuple[float, ...] = (5.0, 12.0),
    filtro_legenda: str | None = "subtitles=clipe.ass",
    com_pilula: bool = True,
    pitch: bool = False,
) -> str:
    """O filter_complex que este estilo produziria. Funcao pura, sem ffmpeg."""
    from clipper import composicao as C

    return C.montar(
        comp=comp,
        ativos=ativos_falsos(com_pilula=com_pilula),
        recorte=dict(RECORTE_PADRAO),
        duracao=duracao,
        fps="30000/1001",
        punches=punches,
        filtro_legenda=filtro_legenda,
        tem_audio=True,
        pitch=pitch,
    ).filtro


def diff_etapas(a: str, b: str) -> list[str]:
    """Diferencas entre dois filtergraphs, etapa a etapa, em texto legivel."""
    ea, eb = a.split(";"), b.split(";")
    linhas: list[str] = []
    for i in range(max(len(ea), len(eb))):
        x = ea[i] if i < len(ea) else "(ausente)"
        y = eb[i] if i < len(eb) else "(ausente)"
        if x != y:
            linhas.append(f"  etapa {i}:\n    - {x}\n    + {y}")
    return linhas


MODELOS_COMPOSTOS = ("cortes", "cortes-editorial")
TODOS_OS_MODELOS = ("cortes", "cortes-editorial", "bold-amarelo", "clean-branco")

DIR_BASELINE = DIR_FIXTURES / "baseline"
FIXTURE_SINTETICA = DIR_FIXTURES / "sintetica" / "palavras.json"

# As UNICAS diferencas que a regressao aceita contra o baseline de 12fc1e2b.
# Lista FECHADA por decisao do arquiteto: qualquer delta fora daqui e defeito,
# nao melhoria. Cada entrada diz em que arquivo o delta pode aparecer.
EXCECOES = {
    "E1": "slot do topo: pílula permanente de título -> gancho com recorte temporal",
    "E2": "cortes-editorial: margem_inferior corrigida para a zona segura",
    "E3": "legendas: piso de 3 palavras com guarda + destaque pulando ≤2 letras",
}


def palavras_sinteticas() -> dict[str, Any]:
    if not FIXTURE_SINTETICA.is_file():
        raise Pulou(f"falta a fixture sintética: {FIXTURE_SINTETICA}")
    return json.loads(FIXTURE_SINTETICA.read_text(encoding="utf-8"))


def ass_do_modelo(nome: str) -> str:
    """O .ass que este modelo produz sobre a fixture sintética."""
    from clipper import legendas as L
    from clipper.modelo import Modelo

    fx = palavras_sinteticas()
    texto, _ = L.montar_ass(
        fx["palavras"],
        preset=Modelo.de_fabrica(nome).legenda,
        inicio=fx["inicio"],
        fim=fx["fim"],
    )
    return texto


def ler_baseline(nome_arquivo: str) -> str:
    alvo = DIR_BASELINE / nome_arquivo
    if not alvo.is_file():
        raise Pulou(f"falta o baseline: {alvo}")
    return alvo.read_text(encoding="utf-8")


# ==========================================================================
# ESTRUTURAIS
# ==========================================================================


def e_modelo_roundtrip(_: Path) -> None:
    """Emenda 1: JSON aninhado -> de_preset() -> montar() == instancia de fabrica.

    O que esta prova defende: a forma de ARQUIVO do modelo e recarregavel sem
    perder um pixel. Se alguem trocar a serializacao por `asdict()` (a forma
    flat, que e identidade interna), esta prova quebra -- que e exatamente o
    ponto, porque `de_preset()` nao le flat.
    """
    import tempfile

    from clipper.modelo import Modelo

    for nome in MODELOS_COMPOSTOS:
        fabrica = Modelo.de_fabrica(nome)
        confere(fabrica.compoe, f"{nome}: a fábrica traz composição")

        with tempfile.TemporaryDirectory() as tmp:
            destino = Modelo.de_fabrica(nome).gravar(Path(tmp) / f"{nome}.json")
            voltou = Modelo.de_arquivo(destino)

            confere(
                voltou.para_json() == fabrica.para_json(),
                f"{nome}: a forma canônica sobrevive à ida e volta",
            )
            confere(
                voltou.legenda == fabrica.legenda,
                f"{nome}: o preset de legenda volta idêntico",
            )
            confere(
                voltou.composicao == fabrica.composicao,
                f"{nome}: a composição resolvida volta idêntica",
            )

            g_fab = filtergraph(fabrica.composicao)
            g_volta = filtergraph(voltou.composicao)
            confere(
                g_fab == g_volta,
                f"{nome}: filtergraph idêntico após o round-trip",
                f"{len(g_fab)} chars, {g_fab.count(';') + 1} etapas",
            )
            if g_fab != g_volta:
                for linha in diff_etapas(g_fab, g_volta):
                    print(linha)


def e_modelo_flat_nao_recarrega(_: Path) -> None:
    """A forma flat NAO e formato de arquivo -- e a prova disso é explícita.

    Sem esta prova, alguem 'simplifica' o Modelo serializando `asdict()` e
    descobre o estrago meses depois, quando um modelo gravado nao carregar.
    """
    from dataclasses import asdict

    from clipper import composicao as C
    from clipper.modelo import Modelo

    fabrica = Modelo.de_fabrica("cortes")
    flat = asdict(fabrica.composicao)
    confere(
        C.de_preset(flat, "cortes") is None,
        "de_preset() recusa a forma flat (ela não é formato de arquivo)",
        f"{len(flat)} campos flat",
    )
    confere(
        "fracao_altura" not in flat and "cartao_largura" in flat,
        "o flat guarda pixel resolvido, não a fração de origem",
    )


def e_modelo_avisa_chave_desconhecida(_: Path) -> None:
    """Chave que ninguem consome AVISA, e mesmo assim carrega."""
    from clipper.modelo import Modelo

    base = json.loads((RAIZ / "clipper" / "presets" / "cortes.json").read_text(encoding="utf-8"))
    sujo = json.loads(json.dumps(base))
    sujo["cor_faladaa"] = "&H00FFFFFF&"           # erro de digitacao no topo
    sujo["composicao"]["titulo"]["coor"] = "#FFF"  # erro dentro de um ramo
    sujo["composicao"]["inventado"] = {"x": 1}     # ramo que nao existe

    m = Modelo.de_dict(sujo, "sujo")
    avisos = m.avisos()
    confere(m.compoe, "carregou mesmo com chave desconhecida (avisa, não rejeita)")
    for esperado in ("cor_faladaa", "composicao.titulo.coor", "composicao.inventado"):
        confere(esperado in avisos, f"avisou sobre {esperado}")

    limpo = Modelo.de_fabrica("cortes")
    confere(limpo.avisos() == [], "preset de fábrica não gera aviso nenhum",
            "os 4 presets são o contrato do esquema")


def e_regressao_filtergraph(_: Path) -> None:
    """Filtergraph contra o baseline de 12fc1e2b. Delta só onde E1 permite.

    O baseline foi capturado do commit base com ativos falsos e parâmetros
    fixos (provas/fixtures/baseline/). Comparar contra arquivo, e não contra
    o commit, é o que faz esta prova rodar em clone raso e continuar valendo
    depois que o histórico andar.
    """
    from clipper.modelo import Modelo

    for nome in MODELOS_COMPOSTOS:
        antes = ler_baseline(f"filtergraph-{nome}.txt").replace(";\n", ";").strip()
        agora = filtergraph(Modelo.de_fabrica(nome).composicao)
        if antes == agora:
            confere(True, f"{nome}: filtergraph idêntico ao baseline",
                    f"{len(agora)} chars, {agora.count(';') + 1} etapas")
            continue

        deltas = diff_etapas(antes, agora)
        # Delta permitido: só a etapa da pílula/gancho (E1). Qualquer outra
        # etapa tocada é regressão.
        so_do_topo = all(("pilula" in d or "gancho" in d) for d in deltas)
        print(f"    {_amarelo}delta{_zero}  {nome}: {len(deltas)} etapa(s) diferente(s)")
        for linha in deltas:
            print(linha)
        confere(so_do_topo, f"{nome}: o delta fica contido no slot do topo (E1)",
                EXCECOES["E1"])


def e_regressao_ass(_: Path) -> None:
    """Conteúdo do .ass contra o baseline. Delta só onde E2 e E3 permitem.

    Os dois presets sem composição (bold-amarelo, clean-branco) não têm pop e
    portanto não têm destaque de palavra ativa: neles o .ass tem de sair
    BYTE A BYTE igual, sem exceção nenhuma. É o controle da prova.
    """
    for nome in ("bold-amarelo", "clean-branco"):
        antes, agora = ler_baseline(f"legenda-{nome}.ass"), ass_do_modelo(nome)
        confere(antes == agora, f"{nome}: .ass idêntico byte a byte (sem pop, sem exceção)",
                f"{agora.count('Dialogue:')} blocos")

    for nome in MODELOS_COMPOSTOS:
        antes, agora = ler_baseline(f"legenda-{nome}.ass"), ass_do_modelo(nome)
        if antes == agora:
            confere(True, f"{nome}: .ass idêntico ao baseline",
                    f"{agora.count('Dialogue:')} blocos")
            continue

        la, lb = antes.splitlines(), agora.splitlines()
        # O cabeçalho carrega MarginV (E2). Os Dialogue carregam a quebra e o
        # destaque (E3). Delta em qualquer outra linha é regressão.
        cab_a = [l for l in la if not l.startswith("Dialogue:")]
        cab_b = [l for l in lb if not l.startswith("Dialogue:")]
        difs_cab = [(x, y) for x, y in zip(cab_a, cab_b) if x != y]
        for x, y in difs_cab:
            print(f"      cabeçalho:\n        - {x}\n        + {y}")
        # D5 (menor): a linha Style inteira não é exceção -- só o MarginV é.
        # Cor, fonte ou contorno mudando no cabeçalho é regressão, e a versão
        # anterior desta prova aceitava qualquer delta numa linha Style.
        so_margin_v = all(_so_margin_v_mudou(x, y) for x, y in difs_cab)
        confere(
            len(cab_a) == len(cab_b) and so_margin_v,
            f"{nome}: no cabeçalho, só o MarginV da linha Style muda (E2)",
            EXCECOES["E2"] if difs_cab else "cabeçalho intacto",
        )
        confere(len(lb) <= len(la), f"{nome}: o E3 não criou bloco novo",
                f"{sum(1 for x in la if x.startswith('Dialogue:'))} -> "
                f"{sum(1 for x in lb if x.startswith('Dialogue:'))} blocos")

    # Controle que morde: o comparador precisa RECUSAR uma cor trocada e
    # aceitar só o MarginV. Sem este controle, um comparador frouxo passaria
    # verde para sempre.
    estilo = next(l for l in ler_baseline("legenda-cortes-editorial.ass").splitlines()
                  if l.startswith("Style:"))
    campos = estilo[len("Style:"):].split(",")
    cor_trocada = list(campos)
    cor_trocada[3] = "&H00123456&" if campos[3].strip() != "&H00123456&" else "&H00654321&"
    margem_trocada = list(campos)
    margem_trocada[_INDICE_MARGIN_V] = str(int(campos[_INDICE_MARGIN_V]) + 7)
    confere(not _so_margin_v_mudou(estilo, "Style:" + ",".join(cor_trocada)),
            "controle: o comparador recusa uma cor trocada na linha Style")
    confere(_so_margin_v_mudou(estilo, "Style:" + ",".join(margem_trocada)),
            "controle: e aceita só o MarginV")


# Formato do ASS (legendas.py): Name, Fontname, Fontsize, PrimaryColour,
# SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline,
# StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow,
# Alignment, MarginL, MarginR, MarginV, Encoding.
_INDICE_MARGIN_V = 21


def _so_margin_v_mudou(x: str, y: str) -> bool:
    """Duas linhas Style que diferem, no maximo, no campo MarginV."""
    if not (x.startswith("Style:") and y.startswith("Style:")):
        return False
    fa, fb = x[len("Style:"):].split(","), y[len("Style:"):].split(",")
    if len(fa) != len(fb) or len(fa) <= _INDICE_MARGIN_V:
        return False
    return all(a.strip() == b.strip()
               for i, (a, b) in enumerate(zip(fa, fb)) if i != _INDICE_MARGIN_V)


def _blocos_do_ass(texto: str) -> list[str]:
    """Só o campo Text de cada Dialogue.

    O formato tem NOVE vírgulas antes do texto (Layer, Start, End, Style,
    Name, MarginL, MarginR, MarginV, Effect) e DOIS pares ",," no caminho --
    depois de Name e depois de Effect. Cortar no primeiro ",," traz "0,0,0,,"
    junto e infla qualquer contagem feita em cima.
    """
    return [
        l.split(",", 9)[9]
        for l in texto.splitlines()
        if l.startswith("Dialogue:") and l.count(",") >= 9
    ]


def _palavras_do_bloco(corpo: str) -> list[str]:
    """As palavras de um Dialogue, na ordem, sem as chaves de override.

    Cada palavra carrega exatamente um \\k, então a contagem de \\k é o
    controle independente de que este parser não está inventando palavra.
    """
    import re

    palavras = [w for w in re.sub(r"\{[^}]*\}", "\x00", corpo).split("\x00") if w.strip()]
    assert len(palavras) == corpo.count("\\k"), (
        f"parser de bloco divergiu da contagem de \\k: "
        f"{len(palavras)} peça(s) para {corpo.count(chr(92) + 'k')} \\k em {corpo!r}"
    )
    return palavras


def e_legenda_conformidade(_: Path) -> None:
    """P1: nenhum bloco passa de 7 palavras nem de 2 linhas. Percorre TODOS."""
    from clipper.modelo import Modelo

    for nome in MODELOS_COMPOSTOS:
        preset = Modelo.de_fabrica(nome).legenda
        blocos = _blocos_do_ass(ass_do_modelo(nome))
        confere(bool(blocos), f"{nome}: gerou blocos", f"{len(blocos)} blocos")

        piores_palavras = max(len(_palavras_do_bloco(b)) for b in blocos)
        confere(piores_palavras <= 7, f"{nome}: nenhum bloco passa de 7 palavras",
                f"maior = {piores_palavras}")
        confere(piores_palavras <= preset.max_palavras_linha,
                f"{nome}: o teto do preset continua valendo (o piso não o afrouxou)",
                f"teto = {preset.max_palavras_linha}, maior = {piores_palavras}")

        piores_linhas = max(b.count("\\N") + 1 for b in blocos)
        confere(piores_linhas <= 2, f"{nome}: nenhum bloco passa de 2 linhas",
                f"maior = {piores_linhas}")

        de_uma = [b for b in blocos if len(_palavras_do_bloco(b)) == 1]
        antes = [b for b in _blocos_do_ass(ler_baseline(f"legenda-{nome}.ass"))
                 if len(_palavras_do_bloco(b)) == 1]
        confere(len(de_uma) < len(antes),
                f"{nome}: o piso reduziu os blocos de uma palavra",
                f"{len(antes)} -> {len(de_uma)}")


def e_legenda_destaque_pula_curtas(_: Path) -> None:
    """E3: palavra com menos letras que o limiar nunca recebe o realce."""
    import re
    import unicodedata

    from clipper.modelo import Modelo

    for nome in MODELOS_COMPOSTOS:
        preset = Modelo.de_fabrica(nome).legenda
        limiar = preset.destaque_minimo_letras
        confere(limiar >= 3, f"{nome}: o limiar de letras está ligado", f"limiar = {limiar}")

        destaque = preset.cor_do_pop
        faltas, pulados = [], 0
        for bloco in _blocos_do_ass(ass_do_modelo(nome)):
            for chaves, palavra in re.findall(r"\{([^}]*)\}([^{]*)", bloco):
                nu = "".join(c for c in unicodedata.normalize("NFC", palavra) if c.isalpha())
                tem_destaque = f"\\1c{destaque}" in chaves
                if len(nu) < limiar and tem_destaque:
                    faltas.append(palavra.strip())
                elif len(nu) < limiar:
                    pulados += 1
        confere(not faltas, f"{nome}: nenhuma palavra curta recebe destaque",
                f"{pulados} puladas" if not faltas else f"falhas: {faltas}")

    # O caso que o Bruno viu no MP4: "É A PRIMEIRA" com o A amarelo.
    antes = ler_baseline("legenda-cortes.ass")
    agora = ass_do_modelo("cortes")
    alvo = "&H0000E5FF&"
    confere(f"\\1c{alvo}" in antes.split("PRIMEIRA")[0].split("}É")[0],
            "o baseline realmente continha o defeito (É com destaque)")
    confere("}É" not in agora or f"\\1c{alvo}" not in agora.split("}É")[0].split("{")[-1],
            "o defeito do 'É' amarelo não sobrevive")


def e_legenda_guarda_de_lacuna(_: Path) -> None:
    """E3: o piso não funde através de pausa longa, mesmo ficando curto."""
    import dataclasses

    from clipper import legendas as L
    from clipper.modelo import Modelo

    preset = Modelo.de_fabrica("cortes").legenda

    # Caso ISOLADO: dois blocos de uma palavra, separados por 2s. O teto (3)
    # permite a fusão de sobra, então só a guarda pode impedi-la. Medir isso
    # na fixture inteira não serviria: lá o teto bloqueia antes da guarda, e a
    # prova passaria sem nunca exercitar a regra que diz testar.
    curto = [
        [{"texto": "Sim.", "inicio": 0.0, "fim": 0.4}],
        [{"texto": "Claro.", "inicio": 2.4, "fim": 2.9}],
    ]
    com = L.fundir_curtos(curto, minimo=3, maximo=3, gap_maximo=1.2)
    sem = L.fundir_curtos(curto, minimo=3, maximo=3, gap_maximo=999.0)
    confere(len(com) == 2, "com a guarda, a pausa de 2,0 s impede a fusão",
            "os dois blocos ficam curtos, de propósito")
    confere(len(sem) == 1, "sem a guarda, os mesmos dois blocos se fundiriam",
            "a guarda é o que faz a diferença, não o teto")

    perto = [
        [{"texto": "Sim.", "inicio": 0.0, "fim": 0.4}],
        [{"texto": "Claro.", "inicio": 0.9, "fim": 1.4}],
    ]
    confere(len(L.fundir_curtos(perto, minimo=3, maximo=3, gap_maximo=1.2)) == 1,
            "pausa curta (0,5 s) não impede a fusão")

    teto = [
        [{"texto": "Sim.", "inicio": 0.0, "fim": 0.4}],
        [{"texto": "a", "inicio": 0.5, "fim": 0.6},
         {"texto": "b", "inicio": 0.7, "fim": 0.8},
         {"texto": "c", "inicio": 0.9, "fim": 1.0}],
    ]
    confere(len(L.fundir_curtos(teto, minimo=3, maximo=3, gap_maximo=1.2)) == 2,
            "o teto também pode deixar o bloco curto, e isso é permitido",
            "1+3 = 4 passaria do teto 3")

    # E na fixture real: nenhum bloco pode ter atravessado pausa longa.
    fx = palavras_sinteticas()
    cru = L.agrupar_linhas(fx["palavras"], max_palavras=preset.max_palavras_linha,
                           max_caracteres=preset.max_caracteres_linha)
    final = L.fundir_curtos(cru, minimo=preset.min_palavras_linha,
                            maximo=preset.max_palavras_linha,
                            gap_maximo=preset.gap_maximo_fusao_s)
    travessias = sum(
        1 for b in final
        for i in range(len(b) - 1)
        if float(b[i + 1]["inicio"]) - float(b[i]["fim"]) > preset.gap_maximo_fusao_s
    )
    confere(travessias == 0, "na fixture, nenhum bloco atravessa pausa longa",
            f"gap máximo = {preset.gap_maximo_fusao_s}s")
    confere(all(len(b) <= preset.max_palavras_linha for b in final),
            "o teto continua respeitado depois da fusão",
            f"maior = {max(len(b) for b in final)}, teto = {preset.max_palavras_linha}")


def e_legenda_segunda_linha_por_largura(_: Path) -> None:
    """E3: o \\N nasce da largura e só dela.

    Usa um medidor SINTÉTICO (largura = nº de caracteres) porque a fonte real
    é do Windows e não existe neste sandbox. A prova é da REGRA de quebra; que
    a fonte real meça o que se espera é prova física.
    """
    from clipper import legendas as L

    def medir(texto: str) -> float:
        return float(len(texto))

    palavras = [{"texto": p, "inicio": i * 0.4, "fim": i * 0.4 + 0.3}
                for i, p in enumerate(["alpha", "bravo", "charlie"])]

    uma = L.quebrar_bloco(palavras, maiusculas=False, medidor=medir, teto=100.0, max_linhas=2)
    confere(len(uma) == 1, "cabendo na largura, o bloco fica em uma linha só")

    duas = L.quebrar_bloco(palavras, maiusculas=False, medidor=medir, teto=14.0, max_linhas=2)
    confere(len(duas) == 2, "estourando a largura, nasce a segunda linha")
    confere(sum(len(l) for l in duas) == len(palavras), "nenhuma palavra se perde na quebra")
    confere([p["texto"] for l in duas for p in l] == ["alpha", "bravo", "charlie"],
            "a ordem das palavras sobrevive")

    sem_medidor = L.quebrar_bloco(palavras, maiusculas=False, medidor=None, teto=0.0, max_linhas=2)
    confere(len(sem_medidor) == 1, "sem medidor não há quebra (comportamento da F4a)")

    gigante = [{"texto": "x" * 80, "inicio": 0.0, "fim": 0.4}]
    confere(len(L.quebrar_bloco(gigante, maiusculas=False, medidor=medir,
                                teto=10.0, max_linhas=2)) == 1,
            "palavra sozinha maior que a caixa não vira duas linhas estouradas")


def e_gancho_no_filtergraph(_: Path) -> None:
    """E1: o gancho tem recorte temporal, fade de saída e Y na zona segura."""
    from clipper.modelo import Modelo

    for nome in MODELOS_COMPOSTOS:
        c = Modelo.de_fabrica(nome).composicao
        g = filtergraph(c)

        confere(c.gancho_ativo, f"{nome}: o gancho é o padrão (a substituição, não o escape)")
        confere(f"enable='between(t,0,{c.gancho_duracao_s:g})'" in g,
                f"{nome}: o overlay tem enable entre 0 e a duração",
                f"{c.gancho_duracao_s:g}s")
        confere(2.5 <= c.gancho_duracao_s <= 3.0, f"{nome}: duração na faixa pedida",
                f"{c.gancho_duracao_s:g}s")
        ramo = next(e for e in g.split(";") if e.endswith("[pilula]"))
        confere("fade=t=out" in ramo and ":d=0:" not in ramo,
                f"{nome}: fade de saída no ramo da pílula, nunca com d=0",
                "guarda do fade (composicao.py:1113)")
        confere(c.gancho_y >= c.zona_topo,
                f"{nome}: o gancho começa dentro da zona segura",
                f"y={c.gancho_y} >= topo={c.zona_topo}")
        confere(f"y='{c.gancho_y}+" in g, f"{nome}: o Y da zona segura chegou ao grafo")
        confere("pow(1-min(t/" in g, f"{nome}: a animação de entrada foi mantida")


def e_gancho_escape_restaura_titulo(_: Path) -> None:
    """E1: desligar gancho.ativo devolve exatamente a caixa permanente."""
    import json

    from clipper.modelo import Modelo

    for nome in MODELOS_COMPOSTOS:
        fonte = Modelo.de_fabrica(nome).para_json()
        fonte["composicao"]["gancho"]["ativo"] = False
        escape = Modelo.de_dict(fonte, nome)

        g = filtergraph(escape.composicao)
        ramo = next(e for e in g.split(";") if e.endswith("[pilula]"))
        confere("enable='between" not in g, f"{nome}: sem gancho, sem recorte temporal")
        confere("fade=t=out" not in ramo,
                f"{nome}: sem gancho, sem fade de saída no ramo da pílula",
                "o fade=t=out da cauda é do clipe, não da pílula")

        antes = ler_baseline(f"filtergraph-{nome}.txt").replace(";\n", ";").strip()
        confere(g == antes,
                f"{nome}: o escape devolve o filtergraph do baseline, byte a byte",
                "a caixa permanente de título volta inteira")


def e_modelo_sem_composicao(_: Path) -> None:
    """Preset sem bloco 'composicao' continua no caminho F3, sem cartao."""
    from clipper.modelo import Modelo

    for nome in ("bold-amarelo", "clean-branco"):
        m = Modelo.de_fabrica(nome)
        confere(not m.compoe, f"{nome}: sem composição, caminho F3 preservado")
        confere(m.legenda.nome == nome, f"{nome}: a legenda carrega mesmo assim")
        confere(m.impressao() == "", f"{nome}: sem composição não há impressão de estilo")


# ==========================================================================
# FISICAS
# ==========================================================================


def f_clipe_curto_gera(_: Path) -> None:
    """O gerador lavfi produz um mp4 sondavel com video e audio."""
    from clipper import ffmpeg_utils

    sys.path.insert(0, str(RAIZ / "provas"))
    from provas.gerar_clipe_curto import DESTINO_PADRAO, gerar

    caminho = gerar(DESTINO_PADRAO, 40.0)
    info = ffmpeg_utils.sondar(caminho)
    confere(info.tem_video, "o clipe curto tem vídeo", f"{info.largura}x{info.altura}")
    confere(info.tem_audio, "o clipe curto tem áudio", f"{info.taxa_amostragem} Hz")
    confere(abs(float(info.duracao) - 40.0) <= 0.5, "duração dentro de ±0,5 s",
            f"{float(info.duracao):.2f}s")


def f_gancho_no_frame(raiz: Path) -> None:
    """P1 FÍSICA: o gancho aparece em t=1 s e sumiu em t=4 s.

    Renderiza um clipe curto com o modelo `cortes`, extrai os dois frames e
    mede a banda do topo. Não compara com imagem de referência -- compara o
    clipe COM ELE MESMO em dois instantes, que é o que a regra afirma: a
    faixa do gancho muda, o resto do quadro não.

    Os dois PNG ficam em disco para inspeção do Bruno; o caminho sai no fim.
    """
    from clipper import composicao as C
    from clipper import ffmpeg_utils
    from clipper.modelo import Modelo

    sys.path.insert(0, str(RAIZ / "provas"))
    from provas.gerar_clipe_curto import DESTINO_PADRAO, gerar

    fonte = DESTINO_PADRAO if DESTINO_PADRAO.is_file() else gerar(DESTINO_PADRAO, 40.0)
    trabalho = raiz / "_trabalho"
    trabalho.mkdir(parents=True, exist_ok=True)

    modelo = Modelo.de_fabrica("cortes")
    comp = modelo.composicao
    gancho = "ELE NÃO FAZIA IDEIA DO QUE VINHA DEPOIS"

    ativos = C.gerar_ativos(comp, "Título que não deve aparecer", trabalho, gancho=gancho)
    confere(ativos.get("pilula") is not None, "a pílula foi desenhada a partir do gancho")

    info = ffmpeg_utils.sondar(fonte)
    montagem = C.montar(
        comp=comp, ativos=ativos,
        recorte={"largura": 405, "altura": 720, "x": 437, "y": 0},
        duracao=10.0, fps=info.fps_fracao or "30/1",
        punches=[], filtro_legenda=None, tem_audio=info.tem_audio, pitch=False,
    )
    clipe = raiz / "gancho.mp4"
    args = ["-ss", "2.000", "-t", "10.000", "-i", str(fonte)]
    args += montagem.entradas
    args += ["-filter_complex", montagem.filtro, "-map", montagem.rotulo_video]
    if montagem.rotulo_audio:
        args += ["-map", montagem.rotulo_audio]
    args += ["-t", "10.000", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-y", str(clipe)]
    ffmpeg_utils.rodar(args, descricao="render do clipe de prova do gancho", timeout=300.0)
    confere(clipe.is_file() and clipe.stat().st_size > 0, "o clipe de prova foi renderizado")

    frames = {}
    for rotulo, ts in (("t1", 1.0), ("t4", 4.0)):
        destino = raiz / f"gancho-{rotulo}.png"
        ffmpeg_utils.rodar(
            ["-ss", f"{ts:.3f}", "-i", str(clipe), "-frames:v", "1", "-y", str(destino)],
            descricao=f"frame em t={ts:g}s", timeout=120.0,
        )
        frames[rotulo] = destino
        confere(destino.is_file(), f"frame extraído em t={ts:g}s", str(destino))

    from PIL import Image, ImageChops, ImageStat

    a = Image.open(frames["t1"]).convert("L")
    b = Image.open(frames["t4"]).convert("L")
    topo = (0, comp.gancho_y, C.LARGURA_SAIDA, comp.gancho_y + int(ativos["pilula"]["altura"]))
    # Banda de controle: no meio do cartão, longe do gancho e da legenda.
    meio = (0, 900, C.LARGURA_SAIDA, 1000)

    d_topo = ImageStat.Stat(ImageChops.difference(a.crop(topo), b.crop(topo))).mean[0]
    d_meio = ImageStat.Stat(ImageChops.difference(a.crop(meio), b.crop(meio))).mean[0]

    confere(d_topo > 6.0, "a faixa do gancho muda entre t=1 s e t=4 s",
            f"diferença média {d_topo:.1f}")
    confere(d_topo > d_meio * 2.0,
            "a mudança está no topo, não no quadro inteiro",
            f"topo {d_topo:.1f} x meio {d_meio:.1f}")
    print(f"    >>> frames para inspeção: {frames['t1']}  e  {frames['t4']}")




# ==========================================================================
# P2/P3 — contrato v2, render concatenado e pacote de publicacao
# ==========================================================================


def _cenario():
    """Transcricao sintetica com frases regulares, para montar casos v2.

    Gerada aqui e nao versionada de proposito: ela nao descreve nenhum video
    real, so precisa ter fronteiras previsiveis para que cada mordida do
    validador falhe pelo motivo que a prova quer testar, e nao por acaso.
    """
    from clipper.fronteiras import Fronteiras

    # A LACUNA de 60s no meio nao e enfeite: sem ela todo tempo do video tem
    # uma fronteira a menos de 4s, e a tolerancia de encaixe (15s) absorve
    # qualquer erro. A mordida "fronteira fora de bloco" so pode ser testada
    # onde existe um tempo ORFAO -- e silencio longo e onde isso acontece de
    # verdade num video (intervalo, corte de camera, musica).
    palavras, t, idx = [], 0.0, 0
    while t < 400.0:
        if 180.0 <= t < 240.0:
            t = 240.0
        for k in range(6):
            palavras.append(
                {"texto": f"p{idx}" + ("." if k == 5 else ""),
                 "inicio": round(t, 3), "fim": round(t + 0.6, 3)}
            )
            t += 0.65
            idx += 1
    fr = Fronteiras.de_transcricao({"palavras": palavras, "duracao": round(t, 3)})
    energia = {"rms_norm": [0.5] * (int(t) + 2), "janela_s": 1.0}
    return fr, energia


_BASE_CLIPE = {
    "titulo": "Um título",
    "score_0_10": 8.0,
    "motivo": "um motivo",
    "gancho_sugerido": "um gancho",
}


def _clipe_v2(fr, pares):
    from clipper.fronteiras import mmss

    return {
        **_BASE_CLIPE,
        "segmentos": [
            {"inicio": mmss(fr.frases[a].inicio), "fim": mmss(fr.frases[b].fim)}
            for a, b in pares
        ],
    }


def _clipe_v1(fr, a, b):
    from clipper.fronteiras import mmss

    return {**_BASE_CLIPE, "inicio": mmss(fr.frases[a].inicio), "fim": mmss(fr.frases[b].fim)}


def e_v2_valida_passa(_: Path) -> None:
    """Um clipe v2 bem formado passa, e o span não vira o corte."""
    from clipper.pipeline import select

    fr, energia = _cenario()
    ok, probs = select.validar([_clipe_v2(fr, [(0, 3), (20, 24)])], fr, energia, n=5)
    confere(not probs, "v2 válida passa sem problema", str(probs)[:120])
    confere(len(ok) == 1, "um clipe aprovado")
    c = ok[0]
    soma = sum(s["duracao"] for s in c["segmentos"])
    span = c["fim"] - c["inicio"]
    confere(len(c["segmentos"]) == 2, "os dois segmentos sobreviveram")
    confere(abs(c["duracao"] - soma) < 0.01,
            "a duração é a SOMA dos segmentos", f"{soma:.1f}s")
    confere(span > soma + 1.0,
            "o span é maior que a soma — é span, não o corte",
            f"span {span:.1f}s x soma {soma:.1f}s")

    esquema = select._para_esquema(1, c)
    confere("segmentos" in esquema, "o esquema de saída carrega `segmentos`")
    confere(esquema["span_inicio"] == round(c["inicio"], 3),
            "o esquema marca o span explicitamente")


def e_v2_mordidas(_: Path) -> None:
    """As 8 mordidas obrigatórias, cada uma com asserção que DISCRIMINA.

    Não basta reprovar: cada caso tem de reprovar pelo motivo certo. Uma prova
    que só conta problemas passaria com a mensagem errada, e a mensagem é o
    produto — é ela que diz ao usuário o que consertar.
    """
    from clipper.fronteiras import mmss
    from clipper.pipeline import select

    fr, energia = _cenario()

    def reprova(clipe, marca, descricao):
        _, probs = select.validar([clipe], fr, energia, n=5)
        achou = [p for p in probs if marca.lower() in p.lower()]
        confere(bool(probs), f"{descricao}: reprovou")
        confere(bool(achou), f"{descricao}: a mensagem discrimina o motivo",
                (achou[0] if achou else (probs[0] if probs else ""))[:110])

    # 1. fronteira fora de bloco: um tempo no meio da lacuna de silêncio, longe
    #    de qualquer abertura ou fechamento. Deslocar poucos segundos não serve
    #    de mordida — a tolerância de encaixe existe justamente para absorver
    #    isso, e absorveria.
    torto = _clipe_v2(fr, [(0, 3)])
    torto["segmentos"][0]["fim"] = mmss(210.0)
    reprova(torto, "fronteira de frase", "1. fronteira fora de bloco")

    # 2. segmentos fora de ordem
    reprova(_clipe_v2(fr, [(20, 24), (0, 3)]), "ordem crescente",
            "2. segmentos fora de ordem")

    # 3. sobreposicao interna
    reprova(_clipe_v2(fr, [(0, 10), (5, 14)]), "se sobrepõem",
            "3. sobreposição entre segmentos do mesmo clipe")

    # 4. soma curta demais
    reprova(_clipe_v2(fr, [(0, 0), (10, 10)]), "somam", "4. soma abaixo de 20s")

    # 5. soma longa demais. Cada segmento tem ~39s -- válido sozinho --, e é a
    #    SOMA que estoura. Segmentos individualmente longos demais reprovariam
    #    antes, pelo limite por trecho, e a prova não testaria a regra do total.
    reprova(_clipe_v2(fr, [(0, 9), (15, 24), (30, 39)]), "somam",
            "5. soma acima de 90s (cada segmento válido sozinho)")

    # 6. mais de 3 segmentos
    reprova(_clipe_v2(fr, [(0, 2), (10, 12), (20, 22), (30, 32)]), "máximo é 3",
            "6. mais de 3 segmentos")

    # 7. inicio/fim junto com segmentos
    hibrido = _clipe_v2(fr, [(0, 5)])
    hibrido["inicio"] = mmss(fr.frases[0].inicio)
    hibrido["fim"] = mmss(fr.frases[5].fim)
    reprova(hibrido, "UMA das duas formas", "7. inicio/fim junto com segmentos")

    # 8. sobreposicao ENTRE clipes, pela uniao
    # Os dois têm ~31s cada (dentro do limite) e compartilham material só no
    # segundo segmento: a reprovação tem de vir da UNIÃO, não da duração.
    a = _clipe_v2(fr, [(0, 3), (40, 43)])
    b = _clipe_v2(fr, [(42, 45), (60, 63)])
    _, probs = select.validar([a, b], fr, energia, n=5)
    achou = [p for p in probs if "compartilham material" in p]
    confere(bool(achou), "8. dois clipes que compartilham material são reprovados",
            achou[0][:110] if achou else str(probs)[:110])


def e_v2_uniao_nao_span(_: Path) -> None:
    """Spans que se cruzam SEM material em comum são aceitos.

    É a razão de a regra ser sobre a união e não sobre o span: dois clipes
    podem intercalar trechos do mesmo intervalo do vídeo sem dividir um
    segundo sequer.
    """
    from clipper.pipeline import select

    fr, energia = _cenario()
    a = _clipe_v2(fr, [(0, 5), (60, 65)])     # span 0..65
    b = _clipe_v2(fr, [(20, 25), (40, 45)])   # span 20..45 — DENTRO do span de a
    ok, probs = select.validar([a, b], fr, energia, n=5)
    confere(not probs, "spans aninhados sem material comum passam", str(probs)[:120])
    confere(len(ok) == 2, "os dois clipes foram aprovados")

    ia = select.intervalos_do_clipe(ok[0])
    ib = select.intervalos_do_clipe(ok[1])
    confere(select._cruzam(ia, ib) is None, "as uniões realmente não se tocam")
    span_a = (ok[0]["inicio"], ok[0]["fim"])
    span_b = (ok[1]["inicio"], ok[1]["fim"])
    confere(span_a[0] < span_b[0] and span_b[1] < span_a[1],
            "e os spans se cruzam de fato — a regra do span teria reprovado",
            f"{span_a} contém {span_b}")


def e_v1_intacto_no_validador(_: Path) -> None:
    """O contrato v1 continua válido, e sem `segmentos` na saída."""
    from clipper.pipeline import select

    fr, energia = _cenario()
    ok, probs = select.validar([_clipe_v1(fr, 0, 7)], fr, energia, n=5)
    confere(not probs, "v1 passa sem problema", str(probs)[:120])
    esquema = select._para_esquema(1, ok[0])
    confere("segmentos" not in esquema,
            "o esquema do v1 não ganha `segmentos` — contrato byte a byte")
    confere("span_inicio" not in esquema, "nem span_inicio")
    confere(esquema["duracao"] == round(esquema["fim"] - esquema["inicio"], 3),
            "no v1 a duração continua sendo fim - inicio")


def e_esquema_api_aceita_v2(raiz: Path) -> None:
    """Q3 (D-C): o que o esquema deixa o modelo mandar, o validador aceita.

    A versão anterior desta prova só lia a FORMA do dicionário -- e ainda
    exigia que `required` não mudasse, o que prendia o defeito no lugar. Agora
    ela cruza as duas metades: cada exemplo é conferido contra o esquema E
    passado pelo validador. E fecha pelo ponto de entrada real: `clipper select
    --api` com o SDK de verdade falando com uma API falsa local que obedece ao
    esquema que recebeu, como o structured outputs obriga o modelo real.
    """
    from clipper.pipeline import select
    from provas import entrada_real as ER

    item = select.ESQUEMA_JSON["properties"]["clipes"]["items"]
    confere(item["additionalProperties"] is False,
            "additionalProperties continua False")
    for campo in ("segmentos", "descricao", "capa_ts", "conclusao"):
        confere(campo in item["properties"], f"`{campo}` está no esquema da API")
    seg = item["properties"]["segmentos"]
    confere(seg["maxItems"] == select.MAX_SEGMENTOS,
            "o teto de segmentos do esquema é o mesmo do validador",
            f"{seg['maxItems']}")
    confere(seg["items"]["additionalProperties"] is False,
            "um segmento também não aceita campo extra")

    fr, energia = _cenario()
    v1 = _clipe_v1(fr, 0, 7)
    v2 = _clipe_v2(fr, [(0, 3), (20, 24)])
    hibrido = {**v2, "inicio": v1["inicio"], "fim": v1["fim"]}
    sem_forma = dict(_BASE_CLIPE)

    erros = ER.conforme(item, v1)
    confere(not erros, "um clipe v1 cabe no esquema", "; ".join(erros))
    ok, probs = select.validar([v1], fr, energia, n=5)
    confere(len(ok) == 1 and not probs, "… e o validador aceita o v1")

    erros = ER.conforme(item, v2)
    confere(not erros, "um clipe v2 PURO (sem inicio/fim) cabe no esquema", "; ".join(erros))
    ok, probs = select.validar([v2], fr, energia, n=5)
    confere(len(ok) == 1 and not probs, "… e o validador aceita o v2 puro")

    erros = ER.conforme(item, hibrido)
    confere(not erros, "o híbrido também cabe no esquema", "; ".join(erros))
    _, probs = select.validar([hibrido], fr, energia, n=5)
    confere(any("UMA das duas formas" in p for p in probs),
            "… mas o validador recusa o híbrido pelo motivo certo")

    erros = ER.conforme(item, sem_forma)
    confere(not erros, "um clipe sem nenhuma das duas formas cabe no esquema",
            "; ".join(erros))
    _, probs = select.validar([sem_forma], fr, energia, n=5)
    confere(any("inicio" in p and "segmentos" in p for p in probs),
            "… e o validador recusa dizendo as duas formas possíveis",
            (probs[0] if probs else "")[:110])

    try:
        import anthropic  # noqa: F401
    except ImportError as exc:
        raise Pulou(f"sem o pacote anthropic para a metade ponta a ponta ({exc})")

    R = _p5_raiz(raiz, "e-v5")
    trans = _p5_transcricao()
    frs = ER.frases(trans)
    entrada, saida = ER.semear(R, "e-v5", trans)
    conformidade: list[list[str]] = []

    def responder(esquema: dict[str, Any]) -> list[dict[str, Any]]:
        itens = ((esquema.get("properties") or {}).get("clipes") or {}).get("items") or {}
        clipe = ER.item(segmentos=[_p5_seg(frs, 0, 2), _p5_seg(frs, 6, 8)])
        if "inicio" in (itens.get("required") or []):
            # Obrigado pelo esquema a mandar inicio/fim, o modelo manda o span.
            clipe["inicio"] = clipe["segmentos"][0]["inicio"]
            clipe["fim"] = clipe["segmentos"][-1]["fim"]
        conformidade.append(ER.conforme(esquema, {"clipes": [clipe]}))
        return [clipe]

    with ER.api_falsa(responder) as (url, pedidos):
        env = ER.ambiente({
            "ANTHROPIC_BASE_URL": url,
            "ANTHROPIC_API_KEY": "chave-falsa-da-prova",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        proc = ER.cli("select", entrada, "--out", R, "--api", "--force", env=env)

    confere(bool(conformidade) and all(not e for e in conformidade),
            "toda resposta da API falsa obedeceu ao esquema que chegou na requisição")
    confere(proc.returncode == 0, "`clipper select --api` com resposta v2 termina bem",
            f"rc={proc.returncode} " + ER.saida_do_cli(proc).strip()[-160:])
    clipes = json.loads(saida.selecao_json.read_text(encoding="utf-8")).get("clipes") or []
    confere(len(clipes) == 1 and len(clipes[0].get("segmentos") or []) == 2,
            "o selecao.json veio da API com os 2 segmentos")
    chamadas = sum(1 for p in pedidos if p["caminho"].rstrip("/").endswith("/v1/messages"))
    confere(chamadas == 1, "uma chamada só — sem rodada de conserto cobrada",
            f"{chamadas} chamada(s)")
    print("    nota  `maxItems` no structured outputs real: NÃO VERIFICADO "
          "(exige chave; D5 Q3 — não bloqueia merge)")


def e_conclusao_ausente_grafo_identico(_: Path) -> None:
    """Sem `conclusao`, o filtergraph é idêntico ao de antes do campo existir."""
    from clipper.modelo import Modelo

    comp = Modelo.de_fabrica("cortes").composicao
    sem = filtergraph(comp)
    confere(sem == ler_baseline("filtergraph-cortes.txt").replace(";\n", ";").strip()
            or "concl" not in sem,
            "sem conclusão, nenhuma etapa de conclusão no grafo")
    confere("[concl]" not in sem, "nenhum rótulo [concl]")
    confere("compc" not in sem, "nenhum rótulo compc")

    from clipper import composicao as C

    ativos = ativos_falsos()
    ativos["conclusao"] = {"arquivo": Path("/f/concl.png"), "largura": 700, "altura": 108}
    com = C.montar(
        comp=comp, ativos=ativos, recorte=dict(RECORTE_PADRAO), duracao=42.0,
        fps="30000/1001", punches=(5.0, 12.0), filtro_legenda="subtitles=clipe.ass",
        tem_audio=True, pitch=False,
    ).filtro
    novas = [e for e in com.split(";") if e not in sem.split(";")]
    de_concl = [e for e in novas if "concl" in e]
    outras = [e for e in novas if "concl" not in e]
    confere(len(de_concl) == 2, "a conclusão acrescenta duas etapas",
            f"{len(de_concl)}")
    # A terceira diferença é a CAUDA: ela passa a ler de [compc] em vez de
    # [compt]. Não é etapa nova nem efeito colateral -- é o encadeamento
    # seguindo o último rótulo, como faz para toda camada opcional do grafo.
    confere(len(outras) == 1 and outras[0].startswith("[compc]"),
            "a única outra mudança é a cauda lendo do novo rótulo",
            outras[0][:60] if outras else "nenhuma")
    confere(
        outras[0].replace("[compc]", "[compt]", 1)
        in sem.split(";"),
        "e essa cauda é byte a byte a de antes, só com o rótulo trocado",
    )
    confere("enable='between(t,40.000,42.000)'" in com,
            "a conclusão ocupa os últimos 2 s", "duração 42 s")
    confere(":d=0:" not in com, "nenhum fade com d=0 (a guarda vale para o novo)")


def e_concat_v2_no_grafo(_: Path) -> None:
    """Render v2: concat antes do crop, PNGs renumerados, crossfade no áudio."""
    from clipper import composicao as C
    from clipper.modelo import Modelo

    comp = Modelo.de_fabrica("cortes").composicao
    g = C.montar(
        comp=comp, ativos=ativos_falsos(), recorte=dict(RECORTE_PADRAO),
        duracao=35.0, fps="30000/1001", punches=(2.0, 19.0),
        filtro_legenda="subtitles=c.ass", tem_audio=True, pitch=False,
        entradas_video=3,
    ).filtro
    etapas = g.split(";")

    confere("concat=n=3:v=1:a=0" in g, "os 3 segmentos são concatenados")
    i_concat = next(i for i, e in enumerate(etapas) if "concat=" in e)
    i_crop = next(i for i, e in enumerate(etapas) if "crop=" in e)
    confere(i_concat < i_crop, "o concat vem ANTES do crop",
            f"etapa {i_concat} < {i_crop}")
    for i in range(3):
        confere(f"[{i}:v]setpts=PTS-STARTPTS[s{i}v]" in g,
                f"segmento {i} tem setpts próprio antes do concat")

    confere("[3:v]format=gray[mk]" in g,
            "os PNGs foram renumerados a partir de N", "máscara = entrada 3")
    confere(g.count("acrossfade=") == 2, "duas junções de áudio para 3 segmentos")
    confere("acrossfade=d=0.015" in g, "crossfade de 15 ms")
    confere("concat=n=3:v=1:a=1" not in g, "o vídeo corta seco (jump cut), sem fade")

    i_cross = max(i for i, e in enumerate(etapas) if "acrossfade" in e)
    i_loud = next(i for i, e in enumerate(etapas) if "loudnorm" in e)
    confere(i_cross < i_loud, "o loudnorm roda no áudio JÁ concatenado",
            f"etapa {i_cross} < {i_loud}")
    confere("[aout]" in g, "o ponto de junção [aout] existe (semente F7)")


def e_remapeamento_de_tempos(_: Path) -> None:
    """Punches e legendas saem do tempo da fonte para o do clipe."""
    from clipper import composicao as C
    from clipper import legendas as L

    segs = [{"inicio": 10.0, "fim": 30.0}, {"inicio": 100.0, "fim": 115.0}]
    vivos = C.remapear_tempos([5.0, 12.0, 29.0, 50.0, 101.0, 114.0, 200.0], segs)
    confere(vivos == [2.0, 19.0, 21.0, 34.0],
            "punch dentro dos segmentos é remapeado; fora, morre", str(vivos))
    confere(all(0 <= v <= 35.0 for v in vivos),
            "nenhum punch cai fora da timeline concatenada")

    palavras = [{"texto": f"p{i}", "inicio": i * 1.0, "fim": i * 1.0 + 0.8}
                for i in range(140)]
    novas, total = L.resincronizar(palavras, segs)
    confere(abs(total - 35.0) < 0.01, "a duração concatenada é a soma", f"{total}s")
    confere(len(novas) == 35, "só as palavras dos segmentos sobreviveram",
            f"{len(novas)} de {len(palavras)}")
    confere(all(0 <= p["inicio"] and p["fim"] <= total + 1e-6 for p in novas),
            "nenhuma palavra cai fora do clipe")
    confere(novas == sorted(novas, key=lambda p: p["inicio"]),
            "as palavras saem em ordem crescente")


def e_capa_ts_fora_rejeita(_: Path) -> None:
    """`capa_ts` fora dos segmentos mantidos é rejeitado na validação."""
    from clipper.fronteiras import mmss
    from clipper.pipeline import select

    fr, energia = _cenario()

    dentro = _clipe_v2(fr, [(0, 5), (40, 45)])
    dentro["capa_ts"] = mmss(fr.frases[2].inicio)
    ok, probs = select.validar([dentro], fr, energia, n=5)
    confere(not probs, "capa_ts dentro de um segmento passa", str(probs)[:110])
    confere("capa_ts" in select._para_esquema(1, ok[0]),
            "e chega ao esquema de saída")

    fora = _clipe_v2(fr, [(0, 5), (40, 45)])
    fora["capa_ts"] = mmss(fr.frases[20].inicio)  # na gordura removida
    _, probs = select.validar([fora], fr, energia, n=5)
    achou = [p for p in probs if "capa_ts" in p and "fora dos trechos" in p]
    confere(bool(achou), "capa_ts na gordura removida é rejeitado",
            achou[0][:110] if achou else str(probs)[:110])


def e_opcionais_limites(_: Path) -> None:
    """descricao e conclusao respeitam os limites de tamanho."""
    from clipper.pipeline import select

    fr, energia = _cenario()

    longo = _clipe_v1(fr, 0, 7)
    longo["descricao"] = "x" * (select.MAX_DESCRICAO_CHARS + 1)
    _, probs = select.validar([longo], fr, energia, n=5)
    confere(any("descricao" in p and "limite" in p for p in probs),
            f"descrição acima de {select.MAX_DESCRICAO_CHARS} chars é rejeitada")

    longo2 = _clipe_v1(fr, 0, 7)
    longo2["conclusao"] = "y" * (select.MAX_CONCLUSAO_CHARS + 1)
    _, probs = select.validar([longo2], fr, energia, n=5)
    confere(any("conclusao" in p and str(select.MAX_CONCLUSAO_CHARS) in p for p in probs),
            f"conclusão acima de {select.MAX_CONCLUSAO_CHARS} chars é rejeitada")

    bom = _clipe_v1(fr, 0, 7)
    bom["descricao"] = "Uma descrição curta."
    bom["conclusao"] = "E foi assim."
    ok, probs = select.validar([bom], fr, energia, n=5)
    confere(not probs, "dentro do limite, passam", str(probs)[:110])
    esquema = select._para_esquema(1, ok[0])
    confere(esquema.get("descricao") == "Uma descrição curta.", "descrição chega à saída")
    confere(esquema.get("conclusao") == "E foi assim.", "conclusão chega à saída")


def e_publicacao_md(_: Path) -> None:
    """publicacao.md traz título, descrição, gancho e o checklist inteiro."""
    from clipper.pipeline.render import CHECKLIST_PUBLICACAO, montar_publicacao

    clipe = {
        "inicio": 10.0, "fim": 55.0,
        "gancho_sugerido": "Ele não fazia ideia do que vinha",
        "descricao": "Uma descrição para o post.",
        "conclusao": "E foi assim que acabou.",
    }
    segs = [{"inicio": 10.0, "fim": 30.0}, {"inicio": 40.0, "fim": 55.0}]
    texto = montar_publicacao(
        clipe, titulo="O título do clipe", arquivo_mp4="clips/01-x--cortes.mp4",
        capa="clips/01-x--cortes.capa.jpg", duracao=35.0, segmentos=segs,
    )
    confere(texto.startswith("# O título do clipe"), "abre com o título")
    confere("clips/01-x--cortes.mp4" in texto, "cita o mp4")
    confere("clips/01-x--cortes.capa.jpg" in texto, "cita a capa")
    confere("Ele não fazia ideia do que vinha" in texto, "traz o gancho")
    confere("Uma descrição para o post." in texto, "traz a descrição")
    confere("E foi assim que acabou." in texto, "traz a conclusão")
    confere("00:10–00:30, 00:40–00:55" in texto, "lista os trechos da fonte")
    for item in CHECKLIST_PUBLICACAO:
        confere(f"- [ ] {item}" in texto, f"checklist: {item[:40]}…")
    confere(texto.endswith("\n") and "\r" not in texto,
            "termina em LF e não contém CR (a mordida de CRLF da casa)")

    magro = montar_publicacao(
        {"inicio": 0.0, "fim": 30.0}, titulo="Sem nada", arquivo_mp4="clips/a.mp4",
        capa=None, duracao=30.0, segmentos=[],
    )
    confere("_(o modelo não sugeriu descrição)_" in magro,
            "sem descrição, o arquivo diz isso em vez de mentir")
    confere("Capa:" not in magro, "sem capa, não inventa a linha")


def e_prompt_v2(_: Path) -> None:
    """O prompt v2 ensina segmentos, gancho verificável e payoff."""
    from clipper import prompt_selecao
    from clipper.pipeline import select

    fr, energia = _cenario()
    texto = prompt_selecao.montar(
        titulo="Vídeo de teste", fronteiras=fr, energia=energia,
        estrategia="ganchos e punchlines", n=5,
        min_s=select.MIN_CLIPE_S, max_s=select.MAX_CLIPE_S,
        max_seg=select.MAX_SEGMENTOS, max_desc=select.MAX_DESCRICAO_CHARS,
        max_concl=select.MAX_CONCLUSAO_CHARS,
    )
    for marca, o_que in (
        ("PROMESSA VERIFICÁVEL", "o gancho como promessa verificável"),
        ("PAYOFF", "o payoff identificado"),
        ("FECHAR nele", "o clipe fechando no payoff"),
        ("segmentos", "o campo segmentos"),
        ("GORDURA", "a remoção de gordura interna"),
        ("PRESERVE O SENTIDO", "preservar sentido e sequência"),
        ("ordem crescente", "a ordem crescente"),
        ("é rejeitado", "a rejeição das duas formas juntas"),
        ("capa_ts", "o capa_ts"),
        ("descricao", "a descricao"),
        ("conclusao", "a conclusao"),
    ):
        confere(marca in texto, f"o prompt cobre {o_que}")

    confere(f"entre {select.MIN_CLIPE_S:.0f} e {select.MAX_CLIPE_S:.0f} segundos" in texto,
            "os limites de duração vêm de quem valida", "20 e 90")
    confere(f"no máximo {select.MAX_SEGMENTOS} trechos" in texto,
            "o teto de segmentos vem de quem valida")
    confere(f"até {select.MAX_DESCRICAO_CHARS} caracteres" in texto,
            "o limite da descrição vem de quem valida")
    confere("\r" not in texto, "o prompt não carrega CR")




def _render_v2(raiz: Path, segmentos, *, conclusao: str = "", capa_ts=None):
    """Renderiza um clipe v2 de verdade e devolve (mp4, duracao_esperada)."""
    from clipper import composicao as C
    from clipper import ffmpeg_utils
    from clipper.modelo import Modelo

    sys.path.insert(0, str(RAIZ / "provas"))
    from provas.gerar_clipe_curto import DESTINO_PADRAO, gerar

    fonte = DESTINO_PADRAO if DESTINO_PADRAO.is_file() else gerar(DESTINO_PADRAO, 40.0)
    raiz.mkdir(parents=True, exist_ok=True)
    trabalho = raiz / "_trabalho"

    modelo = Modelo.de_fabrica("cortes")
    comp = modelo.composicao
    ativos = C.gerar_ativos(
        comp, "Título fora do vídeo", trabalho,
        gancho="O QUE ACONTECEU DEPOIS", conclusao=conclusao,
    )
    info = ffmpeg_utils.sondar(fonte)
    total = sum(s["fim"] - s["inicio"] for s in segmentos)

    montagem = C.montar(
        comp=comp, ativos=ativos,
        recorte={"largura": 405, "altura": 720, "x": 437, "y": 0},
        duracao=total, fps=info.fps_fracao or "30/1",
        punches=[], filtro_legenda=None, tem_audio=info.tem_audio, pitch=False,
        entradas_video=len(segmentos),
    )
    args: list[str] = []
    for s in segmentos:
        args += ["-ss", f"{s['inicio']:.3f}", "-t", f"{s['fim'] - s['inicio']:.3f}",
                 "-i", str(fonte)]
    args += montagem.entradas
    args += ["-filter_complex", montagem.filtro, "-map", montagem.rotulo_video]
    if montagem.rotulo_audio:
        args += ["-map", montagem.rotulo_audio]
    destino = raiz / f"v2-{len(segmentos)}seg.mp4"
    args += ["-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
             "-ar", "48000", "-y", str(destino)]
    ffmpeg_utils.rodar(args, descricao="render v2 de prova", timeout=600.0)
    return destino, total


def _medir_lufs(caminho: Path) -> float | None:
    """I integrado do arquivo, pelo loudnorm em modo de análise."""
    import json as _json
    import re as _re

    from clipper import ffmpeg_utils

    saida = ffmpeg_utils.rodar(
        # ffmpeg_utils.rodar ja prefixa "-loglevel error", e o loudnorm publica
        # o JSON em nivel INFO: sem repetir a opcao aqui (a ultima ocorrencia
        # vence -- o mesmo caso do cropdetect em render.py) a saida vem vazia
        # e a F-V2 pulava em qualquer build do ffmpeg (D5 Q8).
        ["-hide_banner", "-loglevel", "info", "-i", str(caminho),
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
         "-f", "null", "-"],
        descricao=f"medição de loudness de {caminho.name}", timeout=300.0,
    )
    bloco = _re.findall(r"\{[^{}]*input_i[^{}]*\}", saida, _re.DOTALL)
    if not bloco:
        return None
    try:
        return float(_json.loads(bloco[-1])["input_i"])
    except (ValueError, KeyError, _json.JSONDecodeError):
        return None


def f_v2_duracao(raiz: Path) -> None:
    """A duração do MP4 v2 bate com a SOMA dos segmentos, ±0,5 s."""
    from clipper import ffmpeg_utils

    segmentos = [{"inicio": 2.0, "fim": 14.0}, {"inicio": 22.0, "fim": 33.0}]
    mp4, total = _render_v2(raiz, segmentos)
    info = ffmpeg_utils.sondar(mp4)
    medida = float(info.duracao)
    confere(abs(medida - total) <= 0.5,
            "duração do MP4 = soma dos segmentos ±0,5 s",
            f"soma {total:.2f}s, medido {medida:.2f}s, erro {abs(medida - total):.3f}s")
    confere(info.tem_audio, "o clipe concatenado tem áudio")
    print(f"    >>> clipe v2 para inspeção: {mp4}")


def f_v2_lufs(raiz: Path) -> None:
    """O loudnorm no resultado concatenado entrega -14 LUFS ±1."""
    segmentos = [{"inicio": 2.0, "fim": 14.0}, {"inicio": 22.0, "fim": 33.0}]
    mp4, _ = _render_v2(raiz, segmentos)
    lufs = _medir_lufs(mp4)
    if lufs is None:
        raise Pulou("o loudnorm não publicou o bloco JSON com input_i na saída do ffmpeg "
                    "(confira se a medição roda com -loglevel info)")
    confere(abs(lufs - (-14.0)) <= 1.0, "-14 LUFS ±1 no arquivo concatenado",
            f"medido {lufs:.2f} LUFS")


def f_v2_capa(raiz: Path) -> None:
    """capa.jpg sai do instante certo: extrair de novo no mesmo ts bate."""
    from clipper import ffmpeg_utils
    from clipper.pipeline.render import _gravar_capa, _instante_da_capa

    segmentos = [{"inicio": 2.0, "fim": 14.0}, {"inicio": 22.0, "fim": 33.0}]
    mp4, total = _render_v2(raiz, segmentos)

    # capa_ts em tempo da FONTE, dentro do 2º segmento: 25s da fonte cai em
    # 12+3 = 15s do clipe concatenado.
    clipe = {"inicio": 2.0, "fim": 33.0, "capa_ts": 25.0}
    instante = _instante_da_capa(clipe, segmentos, total)
    confere(abs(instante - 15.0) < 0.01,
            "capa_ts da fonte foi convertido para o tempo do clipe",
            f"fonte 25,0s -> clipe {instante:.2f}s")

    capa = _gravar_capa(mp4, instante, raiz / "capa.jpg")
    confere(capa is not None and capa.is_file(), "capa.jpg foi gravada")

    conferencia = raiz / "capa-conferencia.jpg"
    ffmpeg_utils.rodar(
        ["-ss", f"{instante:.3f}", "-i", str(mp4), "-frames:v", "1", "-q:v", "3",
         "-y", str(conferencia)],
        descricao="capa de conferência", timeout=120.0,
    )
    from PIL import Image, ImageChops, ImageStat

    a = Image.open(capa).convert("L")
    b = Image.open(conferencia).convert("L")
    confere(a.size == b.size, "as duas capas têm o mesmo tamanho", f"{a.size}")
    d = ImageStat.Stat(ImageChops.difference(a, b)).mean[0]
    confere(d < 1.0, "extrair de novo no mesmo ts dá o mesmo quadro",
            f"diferença média {d:.3f}")

    outra = raiz / "capa-outro-ts.jpg"
    ffmpeg_utils.rodar(
        ["-ss", f"{max(0.0, instante - 5.0):.3f}", "-i", str(mp4), "-frames:v", "1",
         "-q:v", "3", "-y", str(outra)],
        descricao="capa de controle", timeout=120.0,
    )
    c = Image.open(outra).convert("L")
    d2 = ImageStat.Stat(ImageChops.difference(a, c)).mean[0]
    confere(d2 > d, "e um ts diferente dá um quadro diferente — o controle",
            f"mesmo ts {d:.3f} x outro ts {d2:.3f}")
    print(f"    >>> capa para inspeção: {capa}")


def f_conclusao_no_frame(raiz: Path) -> None:
    """A conclusão aparece no fim e não no meio."""
    from clipper import ffmpeg_utils

    segmentos = [{"inicio": 2.0, "fim": 16.0}, {"inicio": 22.0, "fim": 33.0}]
    mp4, total = _render_v2(raiz, segmentos, conclusao="E FOI ASSIM QUE ACABOU")

    frames = {}
    for rotulo, ts in (("meio", total / 2.0), ("fim", max(0.0, total - 0.8))):
        destino = raiz / f"conclusao-{rotulo}.png"
        ffmpeg_utils.rodar(
            ["-ss", f"{ts:.3f}", "-i", str(mp4), "-frames:v", "1", "-y", str(destino)],
            descricao=f"frame em t={ts:.1f}s", timeout=120.0,
        )
        frames[rotulo] = destino

    from PIL import Image, ImageChops, ImageStat
    from clipper.modelo import Modelo

    comp = Modelo.de_fabrica("cortes").composicao
    a = Image.open(frames["meio"]).convert("L")
    b = Image.open(frames["fim"]).convert("L")
    faixa = (0, comp.conclusao_y, 1080, min(1920, comp.conclusao_y + 140))
    d = ImageStat.Stat(ImageChops.difference(a.crop(faixa), b.crop(faixa))).mean[0]
    confere(d > 6.0, "a faixa da conclusão muda entre o meio e o fim",
            f"diferença média {d:.1f}")
    print(f"    >>> frames da conclusão: {frames['meio']}  e  {frames['fim']}")




# Quanto de altura uma linha de texto ocupa, em multiplos do corpo da fonte.
# `pilula_titulo` usa ascendente+descendente do Pillow (composicao.py:892), que
# exige a fonte instalada -- e as fontes do preset sao do Windows. Numa prova
# ESTRUTURAL nao ha fonte, entao a altura e estimada, e a estimativa e
# DELIBERADAMENTE alta: 1,35 em cobre com folga as familias que os presets
# usam (Impact, Segoe UI Black), e errar para cima e o lado seguro -- superestimar
# a altura ENCOLHE o vao calculado, entao a prova reprova antes de o pixel
# encostar, nunca depois.
_FATOR_ALTURA_LINHA = 1.35


def _altura_pilula(comp: Any, linhas: int) -> int:
    """Altura da pílula com `linhas` linhas, pela fórmula de composicao.py:902."""
    altura_linha = int(comp.titulo_tamanho * _FATOR_ALTURA_LINHA)
    respiro = max(16, int(altura_linha * 0.30))
    bruto = max(int(comp.titulo_altura), altura_linha * linhas + 2 * respiro)
    return bruto - (bruto % 2)  # _par(): o H.264 4:2:0 exige par


def _topo_do_bloco_de_legenda(preset: Any, altura_canvas: int = 1920) -> float:
    """Y do topo do bloco de legenda no pior caso de linhas.

    No ASS com Alignment 2, MarginV é a distância da BASE do texto até a base
    do quadro, e o texto cresce para CIMA. O contorno e a sombra são tinta
    além do glifo e também sobem.
    """
    altura_linha = preset.tamanho * _FATOR_ALTURA_LINHA
    linhas = max(1, int(preset.max_linhas_bloco))
    altura_bloco = altura_linha * linhas + float(preset.contorno) + float(preset.sombra)
    return altura_canvas - float(preset.margem_inferior) - altura_bloco


# Vão mínimo entre a base da pílula de conclusão e o topo do bloco de legenda.
# Abaixo disto os dois leem como um bloco só, e a conclusão deixa de ser um
# fecho para virar uma terceira linha de legenda.
VAO_MINIMO_PX = 24


def e_conclusao_nao_encosta_na_legenda(_: Path) -> None:
    """E-C4: vão ≥ 24 px entre a conclusão e o bloco de legenda.

    Calculado do MODELO, no pior caso que os parâmetros permitem: pílula de
    conclusão de duas linhas (o texto vai até 90 caracteres e não cabe em uma
    só) contra bloco de legenda de duas linhas (`max_linhas_bloco`). Testar o
    caso feliz — uma linha de cada — daria um vão confortável e falso.
    """
    from clipper.modelo import Modelo

    for nome in MODELOS_COMPOSTOS:
        m = Modelo.de_fabrica(nome)
        comp, preset = m.composicao, m.legenda

        altura = _altura_pilula(comp, 2)
        base_pilula = comp.conclusao_y + altura
        topo_legenda = _topo_do_bloco_de_legenda(preset)
        vao = topo_legenda - base_pilula

        confere(
            comp.conclusao_y >= comp.zona_topo,
            f"{nome}: a conclusão começa abaixo do topo da zona segura",
            f"y={comp.conclusao_y} >= {comp.zona_topo}",
        )
        confere(
            base_pilula <= comp.zona_base,
            f"{nome}: a conclusão termina acima da base da zona segura",
            f"base={base_pilula} <= {comp.zona_base}",
        )
        confere(
            vao >= VAO_MINIMO_PX,
            f"{nome}: vão ≥ {VAO_MINIMO_PX} px entre conclusão e legenda",
            f"pílula {comp.conclusao_y}..{base_pilula} (2 linhas, {altura} px), "
            f"legenda a partir de {topo_legenda:.0f} -> vão {vao:.0f} px",
        )


# ==========================================================================
# P5 — integracao v2 pelo ponto de entrada real (RULINGS §13, D5)
# ==========================================================================
#
# Regra do §13.1: a parte de INTEGRACAO destas provas atravessa o CLI
# (`python -m clipper`) e o caminho do painel (ui/jobs.py). Nenhuma monta a
# linha do ffmpeg a mao. O apoio (semear a pasta, chamar o CLI, a fila do
# painel, a API falsa) vive em provas/entrada_real.py.
#
# Declarado, e nao escondido: algumas conferencias sao de UNIDADE e chamam a
# funcao direto -- as variantes de ordem da E-I2 e a primeira metade da E-V5
# (select.validar), o portao do render na E-I1 e na E-X1
# (render._validar_clipes), a E-X2 (quebrador) e a F-G3 (pilula). Cada uma
# tem a sua contraparte pelo ponto de entrada na mesma prova ou numa fisica.


def _p5_raiz(raiz: Path, nome: str) -> Path:
    import shutil

    alvo = Path(raiz) / "p5" / nome
    shutil.rmtree(alvo, ignore_errors=True)
    alvo.mkdir(parents=True, exist_ok=True)
    return alvo


def _p5_videos(raiz: Path) -> Path:
    alvo = Path(raiz) / "p5-videos"
    alvo.mkdir(parents=True, exist_ok=True)
    return alvo


def _p5_transcricao() -> dict[str, Any]:
    """Frases de 3,9 s; entre frases consecutivas a lacuna e de 0,05 s.

    Uma pausa REAL de 7,15 s separa a frase 15 (59,00-62,85 s) da 16 (70,0 s):
    e ela que distingue "blocos consecutivos" de "blocos colados".
    """
    from provas import entrada_real as ER

    return ER.transcricao_sintetica(140.0, pausas=((60.0, 70.0),))


def _p5_seg(frases_: Any, a: int, b: int) -> dict[str, str]:
    from clipper.fronteiras import mmss

    return {"inicio": mmss(frases_[a].inicio), "fim": mmss(frases_[b].fim)}


def _p5_rc(proc: Any) -> str:
    """rc e a cauda da saida do CLI -- SO para dados sinteticos (C.11)."""
    from provas import entrada_real as ER

    cauda = " ".join(ER.saida_do_cli(proc).split())[-180:]
    return f"rc={proc.returncode} {cauda}"


def _p5_validador_do_render_aceita(clipes: list[dict[str, Any]], caminho: Path) -> tuple[bool, str]:
    from clipper.pipeline import render

    try:
        render._validar_clipes(clipes, caminho)
    except Exception as exc:  # noqa: BLE001 - a prova relata o motivo
        return False, str(getattr(exc, "mensagem", exc))[:140]
    return True, ""


def e_p5_selecao_v2_passa_no_render(raiz: Path) -> None:
    """Q1 (D-B): o selecao.json v2 que o CLI grava passa no portão do render."""
    from provas import entrada_real as ER

    R = _p5_raiz(raiz, "e-i1")
    trans = _p5_transcricao()
    fr = ER.frases(trans)
    entrada, saida = ER.semear(R, "e-i1", trans)
    resp = ER.gravar_resposta(R, "resp", [
        ER.item(segmentos=[_p5_seg(fr, 0, 2), _p5_seg(fr, 6, 8)]),
    ])
    proc = ER.cli("select", entrada, "--out", R, "--resposta", resp)
    confere(proc.returncode == 0, "`clipper select` com resposta v2 termina bem", _p5_rc(proc))

    clipes = json.loads(saida.selecao_json.read_text(encoding="utf-8")).get("clipes") or []
    confere(len(clipes) == 1 and len(clipes[0].get("segmentos") or []) == 2,
            "o selecao.json tem 1 clipe com 2 segmentos")
    chaves = sorted({k for s in clipes[0]["segmentos"] for k in s})
    confere(chaves == ["fim", "inicio"],
            "cada segmento gravado carrega só `inicio` e `fim`", ", ".join(chaves))
    aceito, motivo = _p5_validador_do_render_aceita(clipes, saida.selecao_json)
    confere(aceito, "o validador do render aceita o selecao.json que o select gravou", motivo)


def e_p5_sobreposicao_tres_clipes(raiz: Path) -> None:
    """Q2 (D-A): sobreposição entre clipes NÃO adjacentes é recusada.

    A (v2) tem um segmento no começo e outro depois de C começar; B fica no
    meio. Ordenados pelo span, C só era comparado com B -- e passava.
    """
    from clipper.fronteiras import Fronteiras
    from clipper.pipeline import select
    from provas import entrada_real as ER

    R = _p5_raiz(raiz, "e-i2")
    trans = _p5_transcricao()
    fr = ER.frases(trans)
    entrada, saida = ER.semear(R, "e-i2", trans)
    a = ER.item(titulo="A", segmentos=[_p5_seg(fr, 0, 2), _p5_seg(fr, 20, 22)])
    b = ER.item(titulo="B", **_p5_seg(fr, 8, 13))
    c = ER.item(titulo="C", **_p5_seg(fr, 21, 26))
    resp = ER.gravar_resposta(R, "resp", [a, b, c])
    proc = ER.cli("select", entrada, "--out", R, "--resposta", resp)
    texto = ER.saida_do_cli(proc)
    linhas = [l for l in texto.splitlines()
              if "compartilham material" in l and "clipe 1" in l and "clipe 3" in l]
    confere(proc.returncode != 0, "`clipper select` recusa a resposta", f"rc={proc.returncode}")
    confere(bool(linhas), "a recusa aponta o par não adjacente (clipe 1 × clipe 3)",
            (linhas[0].strip() if linhas else texto.strip()[-120:])[:120])

    # Mesmo furo por outros caminhos: ordem de entrada, C em v2, quatro clipes.
    fronteiras = Fronteiras.de_transcricao(trans)
    c_v2 = ER.item(titulo="C", segmentos=[_p5_seg(fr, 21, 26)])
    d = ER.item(titulo="D", **_p5_seg(fr, 27, 32))
    for rotulo, dados, aprovados_esperados in (
        ("ordem C, B, A", [c, b, a], 2),
        ("C em v2", [a, b, c_v2], 2),
        ("quatro clipes (A, B, C, D)", [a, b, c, d], 3),
    ):
        ok, probs = select.validar(dados, fronteiras, {}, n=5)
        achou = [p for p in probs if "compartilham material" in p]
        confere(len(achou) == 1 and len(ok) == aprovados_esperados,
                f"{rotulo}: um problema de material compartilhado, o resto aprovado",
                f"{len(ok)} aprovados, {len(probs)} problema(s)")


def e_p5_aviso_de_ajuste_v2(raiz: Path) -> None:
    """Q10 (P01): encaixe de ≥3 s num segmento avisa, como já avisava no v1."""
    from clipper.fronteiras import mmss
    from provas import entrada_real as ER

    R = _p5_raiz(raiz, "e-i3")
    trans = _p5_transcricao()
    fr = ER.frases(trans)
    entrada, saida = ER.semear(R, "e-i3", trans)
    # O fim pedido (01:06) cai no silêncio; a fronteira mais próxima é o fim da
    # frase 15, 3,15 s antes. O segmento 1 encaixa com menos de 1 s.
    seg2 = {"inicio": mmss(fr[10].inicio), "fim": mmss(66.0)}
    resp = ER.gravar_resposta(R, "resp", [ER.item(segmentos=[_p5_seg(fr, 0, 2), seg2])])
    proc = ER.cli("select", entrada, "--out", R, "--resposta", resp)
    confere(proc.returncode == 0, "`clipper select` aceita o clipe", _p5_rc(proc))

    clipes = json.loads(saida.selecao_json.read_text(encoding="utf-8")).get("clipes") or []
    fim_seg2 = float(clipes[0]["segmentos"][1]["fim"])
    confere(abs(fim_seg2 - fr[15].fim) < 0.01,
            "o segmento 2 foi mesmo encaixado ≥3 s antes do pedido",
            f"pedido 66,00 s, entregue {fim_seg2:.2f} s")
    texto = ER.saida_do_cli(proc)
    avisos_2 = [l for l in texto.splitlines() if "atenção" in l and "segmento 2" in l]
    avisos_1 = [l for l in texto.splitlines() if "atenção" in l and "segmento 1" in l]
    confere(bool(avisos_2), "o ajuste ≥3 s do segmento 2 gera aviso",
            (avisos_2[0].strip() if avisos_2 else "nenhum aviso")[:120])
    confere(not avisos_1, "e o ajuste pequeno do segmento 1 não gera")

    # Costura interna (achado da revisão do P5): o fim pedido do segmento 1 cai
    # no meio de uma frase longa, o encaixe o empurra +5,3 s até o fim dela, e
    # ISSO deixa os dois segmentos colados -- eles são fundidos. O material que
    # o pedido cortava voltou ao clipe; o aviso não pode sumir junto com a costura.
    longa = _p5_transcricao_longa()
    frl = ER.frases(longa)
    entrada2, saida2 = ER.semear(R, "e-i3-costura", longa)
    seg1 = {"inicio": mmss(30.0), "fim": mmss(55.0)}
    resp2 = ER.gravar_resposta(R, "costura", [ER.item(segmentos=[seg1, _p5_seg(frl, 2, 2)])])
    proc2 = ER.cli("select", entrada2, "--out", R, "--resposta", resp2)
    confere(proc2.returncode == 0, "costura: `clipper select` aceita o clipe", _p5_rc(proc2))
    clipe2 = (json.loads(saida2.selecao_json.read_text(encoding="utf-8")).get("clipes") or [{}])[0]
    confere(len(clipe2.get("segmentos") or []) == 1,
            "costura: o encaixe deixou os segmentos colados e eles foram fundidos",
            f"{len(clipe2.get('segmentos') or [])} segmento(s)")
    avisos_costura = [l for l in ER.saida_do_cli(proc2).splitlines()
                      if "atenção" in l and "segmento 1" in l]
    confere(bool(avisos_costura), "costura: o ajuste ≥3 s que sumiu na fusão também avisa",
            (avisos_costura[0].strip() if avisos_costura else "nenhum aviso")[:120])


def _p5_transcricao_longa() -> dict[str, Any]:
    """Frases de 29,4 s (19 palavras) com 1,0 s de lacuna entre elas.

    Frase 0: 0,5-29,9 · 1: 30,9-60,3 · 2: 61,3-90,7 · 3: 91,7-121,1. A lacuna
    de 1,0 s fica abaixo do limite de fusão (1,2 s): blocos consecutivos aqui
    são COLADOS. E dois segmentos 0-1 e 2 somam 89,2 s, mas fundidos dariam
    90,2 s -- a lacuna entra na soma.
    """
    from provas import entrada_real as ER

    return ER.transcricao_sintetica(200.0, palavras_por_frase=19, passo=1.6,
                                    duracao_palavra=0.6)


def e_p5_segmentos_colados_fundidos(raiz: Path) -> None:
    """Q10 (P03): segmentos colados viram um só, com nota; pausa real não funde."""
    from provas import entrada_real as ER

    R = _p5_raiz(raiz, "e-i4")
    trans = _p5_transcricao()
    fr = ER.frases(trans)

    entrada, saida = ER.semear(R, "e-i4-colados", trans)
    resp = ER.gravar_resposta(R, "colados", [
        ER.item(segmentos=[_p5_seg(fr, 0, 2), _p5_seg(fr, 3, 6)]),
    ])
    proc = ER.cli("select", entrada, "--out", R, "--resposta", resp)
    confere(proc.returncode == 0, "colados: `clipper select` aceita", _p5_rc(proc))
    clipe = (json.loads(saida.selecao_json.read_text(encoding="utf-8")).get("clipes") or [{}])[0]
    segs = clipe.get("segmentos") or []
    confere(len(segs) == 1, "colados (lacuna de 0,05 s): os dois segmentos viram um só",
            f"{len(segs)} segmento(s)")
    confere(abs(float(segs[0]["inicio"]) - fr[0].inicio) < 0.01
            and abs(float(segs[0]["fim"]) - fr[6].fim) < 0.01,
            "o fundido vai do início do 1º ao fim do 2º")
    notas = clipe.get("notas") or []
    confere(any("fundid" in n for n in notas), "a fusão fica registrada como nota do clipe",
            (notas[0] if notas else "sem nota")[:110])

    entrada2, saida2 = ER.semear(R, "e-i4-pausa", trans)
    resp2 = ER.gravar_resposta(R, "pausa", [
        ER.item(segmentos=[_p5_seg(fr, 12, 15), _p5_seg(fr, 16, 18)]),
    ])
    proc2 = ER.cli("select", entrada2, "--out", R, "--resposta", resp2)
    confere(proc2.returncode == 0, "pausa: `clipper select` aceita", _p5_rc(proc2))
    clipe2 = (json.loads(saida2.selecao_json.read_text(encoding="utf-8")).get("clipes") or [{}])[0]
    confere(len(clipe2.get("segmentos") or []) == 2,
            "blocos consecutivos com pausa real (7,15 s) no meio seguem separados — "
            "a pausa é gordura removida")
    confere(not clipe2.get("notas"), "e sem nota de fusão")

    # Fusão que estouraria o teto (achado da revisão do P5): dois segmentos que
    # SOMAM 89,2 s, colados por 1,0 s de lacuna. Fundidos dariam 90,2 s. O pedido
    # é válido e tem de passar -- a fusão é conveniência, não pode reprovar.
    longa = _p5_transcricao_longa()
    frl = ER.frases(longa)
    entrada4, saida4 = ER.semear(R, "e-i4-teto", longa)
    resp4 = ER.gravar_resposta(R, "teto", [
        ER.item(segmentos=[_p5_seg(frl, 0, 1), _p5_seg(frl, 2, 2)]),
    ])
    proc4 = ER.cli("select", entrada4, "--out", R, "--resposta", resp4)
    confere(proc4.returncode == 0, "teto: dois segmentos somando 89,2 s são aceitos",
            _p5_rc(proc4))
    clipe4 = (json.loads(saida4.selecao_json.read_text(encoding="utf-8")).get("clipes") or [{}])[0]
    soma4 = sum(float(s["fim"]) - float(s["inicio"]) for s in clipe4.get("segmentos") or [])
    confere(len(clipe4.get("segmentos") or []) == 2 and not clipe4.get("notas"),
            "teto: sem fusão quando fundir estouraria 90 s — a costura fica",
            f"{len(clipe4.get('segmentos') or [])} segmento(s), soma {soma4:.1f} s")

    # Três colados: a nota tem de ler como português ("1, 2 e 3").
    entrada3, saida3 = ER.semear(R, "e-i4-tres", trans)
    resp3 = ER.gravar_resposta(R, "tres", [
        ER.item(segmentos=[_p5_seg(fr, 0, 2), _p5_seg(fr, 3, 5), _p5_seg(fr, 6, 8)]),
    ])
    proc3 = ER.cli("select", entrada3, "--out", R, "--resposta", resp3)
    confere(proc3.returncode == 0, "três colados: `clipper select` aceita", _p5_rc(proc3))
    clipe3 = (json.loads(saida3.selecao_json.read_text(encoding="utf-8")).get("clipes") or [{}])[0]
    notas3 = clipe3.get("notas") or []
    confere(len(clipe3.get("segmentos") or []) == 1
            and any("segmentos 1, 2 e 3" in n for n in notas3),
            "três colados viram um, e a nota diz \"segmentos 1, 2 e 3\"",
            (notas3[0] if notas3 else "sem nota")[:90])


def e_p5_v2_sem_composicao_recusado(raiz: Path) -> None:
    """Q4 (D-D): v2 de 2+ segmentos em preset sem composição é recusado."""
    from provas import entrada_real as ER

    R = _p5_raiz(raiz, "e-i5")
    trans = _p5_transcricao()
    fr = ER.frases(trans)
    entrada, saida = ER.semear(R, "e-i5", trans)
    resp = ER.gravar_resposta(R, "resp", [
        ER.item(segmentos=[_p5_seg(fr, 0, 2), _p5_seg(fr, 6, 8)]),
    ])
    proc = ER.cli("select", entrada, "--out", R, "--resposta", resp)
    confere(proc.returncode == 0, "`clipper select` aceita o v2", _p5_rc(proc))

    proc = ER.cli("render", saida.slug, "--out", R, "--preset", "bold-amarelo")
    texto = ER.saida_do_cli(proc)
    if "não encontrei o executável" in texto:
        raise Pulou("o render deste ambiente não acha o ffmpeg antes de chegar à recusa")
    confere(proc.returncode != 0, "`clipper render --preset bold-amarelo` recusa",
            f"rc={proc.returncode}")
    confere("não tem composição" in texto and "segmentos" in texto,
            "a recusa diz o motivo: preset sem composição não junta segmentos",
            " ".join(texto.split())[-140:])
    confere(not ER.clipes_mp4(saida, "bold-amarelo"), "nenhum MP4 saiu pela metade")


FIXTURE_REAL = DIR_FIXTURES / "wetyO2gOOeU"

# Bytes dos arquivos reais como sairam do painel (commit 638fa69). A prova de
# material real so vale se o arquivo for o real.
_SHA256_FIXTURES_REAIS = {
    "resposta-v1.json": "ae5f52683dcaa0e46e0fb02ca3b61136c126bd65a511c8a14b7a516b618f8760",
    "transcricao.json": "8676f82ecdcfa5eb6b5bb2b8fb041b399e7a42451bce55a567c14e70199c1056",
}


def _fixture_real(nome: str) -> Path:
    alvo = FIXTURE_REAL / nome
    if not alvo.is_file():
        raise Pulou(f"falta a fixture real {alvo.name} — ela chega pelo branch")
    return alvo


def e_material_real_validador(raiz: Path) -> None:
    """E-X1 (Q7): a resposta v1 REAL passa pelo `clipper select`, sem edição.

    Régua C.11: nada do conteúdo sai na tela -- nem a saída do CLI, que cita
    títulos. Só contagens.
    """
    import shutil

    from provas import entrada_real as ER

    resposta = _fixture_real("resposta-v1.json")
    trans = json.loads(_fixture_real("transcricao.json").read_text(encoding="utf-8"))
    R = _p5_raiz(raiz, "e-x1")
    entrada, saida = ER.semear(R, "e-x1", trans)
    copia = R / "_entradas" / "resposta-v1.json"
    shutil.copyfile(resposta, copia)
    confere(copia.read_bytes() == resposta.read_bytes(),
            "a resposta vai ao CLI byte a byte, sem edição", f"{copia.stat().st_size} bytes")

    proc = ER.cli("select", entrada, "--out", R, "--resposta", copia)
    confere(proc.returncode == 0, "`clipper select` aceita a resposta real",
            f"rc={proc.returncode}")
    clipes = json.loads(saida.selecao_json.read_text(encoding="utf-8")).get("clipes") or []
    confere(len(clipes) == 5, "os 5 clipes da resposta real foram aprovados",
            f"{len(clipes)} clipe(s)")
    confere(all(not c.get("segmentos") for c in clipes), "os 5 seguem v1 (contrato congelado)")
    confere(all(20.0 - 1e-6 <= float(c["duracao"]) <= 90.0 + 1e-6 for c in clipes),
            "todas as durações dentro de 20–90 s",
            f"soma {sum(float(c['duracao']) for c in clipes):.1f} s")
    aceito, _ = _p5_validador_do_render_aceita(clipes, saida.selecao_json)
    confere(aceito, "o validador do render aceita o selecao.json real")
    avisos = sum(1 for l in ER.saida_do_cli(proc).splitlines() if "atenção" in l)
    print(f"    nota  avisos de ajuste ≥3 s na resposta real: {avisos}")


def e_material_real_quebrador(raiz: Path) -> None:
    """E-X2 (Q7): o quebrador de legenda sobre a transcrição REAL.

    Nenhum bloco com mais de 7 palavras nem mais de 2 linhas, em todo bloco,
    nos 4 presets, na transcrição inteira e nos 5 trechos reais. Só contagens.
    Prova de UNIDADE do quebrador (mesma via da E-L1); a contraparte de
    integração é a legenda queimada no render real da inspeção.
    """
    from clipper import legendas as L
    from clipper.fronteiras import Fronteiras
    from clipper.modelo import Modelo
    from clipper.pipeline import select

    trans = json.loads(_fixture_real("transcricao.json").read_text(encoding="utf-8"))
    dados = json.loads(_fixture_real("resposta-v1.json").read_text(encoding="utf-8"))
    fr = Fronteiras.de_transcricao(trans)
    ok, probs = select.validar(dados, fr, {}, n=5)
    confere(len(ok) == 5 and not probs, "os 5 trechos reais saem do validador",
            f"{len(ok)} trecho(s), {len(probs)} problema(s)")

    escopos = [(0.0, fr.duracao)] + [(float(c["inicio"]), float(c["fim"])) for c in ok]
    for nome in TODOS_OS_MODELOS:
        preset = Modelo.de_fabrica(nome).legenda
        blocos_total = maior_palavras = maior_linhas = de_uma = 0
        palavras_lidas = palavras_esperadas = 0
        for inicio, fim in escopos:
            lista = [p for p in fr.palavras_entre(inicio, fim)
                     if str(p.get("texto") or "").strip()]
            texto, _ = L.montar_ass(lista, preset=preset, inicio=inicio, fim=fim)
            blocos = _blocos_do_ass(texto)
            contagens = [len(_palavras_do_bloco(b)) for b in blocos]
            blocos_total += len(blocos)
            maior_palavras = max([maior_palavras, *contagens])
            maior_linhas = max([maior_linhas, *(b.count("\\N") + 1 for b in blocos)])
            de_uma += sum(1 for n in contagens if n == 1)
            palavras_lidas += sum(contagens)
            palavras_esperadas += len(lista)
        confere(maior_palavras <= 7 and maior_palavras <= preset.max_palavras_linha,
                f"{nome}: nenhum bloco passa de 7 palavras nem do teto do preset",
                f"{blocos_total} blocos, maior {maior_palavras}, teto {preset.max_palavras_linha}")
        confere(maior_linhas <= 2, f"{nome}: nenhum bloco passa de 2 linhas",
                f"maior {maior_linhas}")
        confere(palavras_lidas == palavras_esperadas,
                f"{nome}: nenhuma palavra perdida nem inventada",
                f"{palavras_lidas}/{palavras_esperadas}; blocos de 1 palavra: {de_uma}")


def e_fixtures_sem_conversao_de_linha(raiz: Path) -> None:
    """Q9: `provas/fixtures/** -text` — nenhum clone converte fim de linha."""
    import hashlib
    import shutil
    import subprocess

    git = shutil.which("git")
    if not git or not (RAIZ / ".git").exists():
        raise Pulou("sem git ou fora de um clone git")
    regras = RAIZ / ".gitattributes"
    linhas = regras.read_text(encoding="utf-8").splitlines() if regras.is_file() else []
    confere(any(l.split() == ["provas/fixtures/**", "-text"] for l in linhas),
            "`.gitattributes` tem a regra no padrão amplo `provas/fixtures/** -text`",
            "presente" if regras.is_file() else "arquivo ausente")
    alvos = [
        "provas/fixtures/wetyO2gOOeU/resposta-v1.json",
        "provas/fixtures/wetyO2gOOeU/transcricao.json",
        "provas/fixtures/sintetica/palavras.json",
        "provas/fixtures/baseline/legenda-cortes.ass",
    ]
    proc = subprocess.run([git, "check-attr", "text", "--", *alvos], cwd=RAIZ,
                          capture_output=True, text=True)
    for alvo in alvos:
        linha = next((l for l in proc.stdout.splitlines() if l.startswith(alvo + ":")), "")
        confere(linha.endswith(": unset"), f"{alvo}: atributo `text` desligado",
                linha.rsplit(": ", 1)[-1] if linha else "sem resposta do git")
    for nome, esperado in _SHA256_FIXTURES_REAIS.items():
        obtido = hashlib.sha256(_fixture_real(nome).read_bytes()).hexdigest()
        confere(obtido == esperado, f"{nome}: bytes idênticos aos do painel", obtido[:16])


_GANCHO_LONGO = (
    "DESCOBRIMOS EXATAMENTE QUANTO CUSTA MANTER ESSA MÁQUINA "
    "FUNCIONANDO DURANTE UM ANO INTEIRO"
)
# Letras largas de proposito: a conclusao continua podendo ser cortada (so o
# gancho ganhou "nunca truncar"), e quando for, o render tem de avisar.
_CONCLUSAO_LARGA = "WWWWW MMMMM WWWWW MMMMM WWWWW MMMMM WWWWW MMMMM WWWWW MMMMM WWWWW MMMMM WWWWW MMMMM WWWWW"


def f_p5_v2_ponta_a_ponta(raiz: Path) -> None:
    """Q1 (D-B) física: select → render de um v2 pelo CLI e pelo painel.

    Mais três menores da D5 no mesmo render: o log mostra a soma e não o span;
    o gancho de 90 caracteres vai para 3 linhas e o relatório avisa; a
    conclusão cortada gera aviso.
    """
    from provas import entrada_real as ER

    R = _p5_raiz(raiz, "f-i1")
    video = ER.video_lavfi(_p5_videos(raiz) / "fonte-p5.mp4", 70.0)
    trans = ER.transcricao_sintetica(68.0)
    fr = ER.frases(trans)
    entrada, saida = ER.semear(R, "f-i1", trans, video=video)
    resp = ER.gravar_resposta(R, "resp", [ER.item(
        titulo="Clipe de prova", segmentos=[_p5_seg(fr, 0, 2), _p5_seg(fr, 6, 8)],
        gancho_sugerido=_GANCHO_LONGO, conclusao=_CONCLUSAO_LARGA,
    )])
    proc = ER.cli("select", entrada, "--out", R, "--resposta", resp)
    confere(proc.returncode == 0, "`clipper select` aceita o v2", _p5_rc(proc))
    clipe = json.loads(saida.selecao_json.read_text(encoding="utf-8"))["clipes"][0]
    soma = sum(float(s["fim"]) - float(s["inicio"]) for s in clipe["segmentos"])
    span = float(clipe["fim"]) - float(clipe["inicio"])

    proc = ER.cli("render", saida.slug, "--out", R, "--preset", "cortes")
    texto = ER.saida_do_cli(proc)
    confere(proc.returncode == 0, "CLI: `clipper render` renderiza o clipe v2", _p5_rc(proc))
    mp4s = ER.clipes_mp4(saida, "cortes")
    confere(len(mp4s) == 1, "CLI: saiu um MP4")
    medida = ER.duracao_medida(mp4s[0])
    confere(abs(medida - soma) <= 0.5, "CLI: duração do MP4 = soma dos segmentos ±0,5 s",
            f"soma {soma:.2f} s, medido {medida:.2f} s")

    linha = next((l for l in texto.splitlines() if "clipe 1 —" in l), "")
    confere(f"{soma:.0f}s" in linha and f"{span:.0f}s" not in linha,
            "o log do render mostra a soma, não o span",
            f"soma {soma:.0f}s, span {span:.0f}s: {linha.strip()[-60:]}")
    avisos_gancho = [l for l in texto.splitlines() if "gancho" in l and "linhas" in l]
    confere(bool(avisos_gancho), "o gancho de 90 caracteres passou de 2 linhas e o log avisa",
            (avisos_gancho[0].strip() if avisos_gancho else "sem aviso")[:110])
    avisos_concl = [l for l in texto.splitlines() if "conclusão" in l and "cortad" in l]
    confere(bool(avisos_concl), "a conclusão cortada gera aviso",
            (avisos_concl[0].strip() if avisos_concl else "sem aviso")[:110])
    relatorio = saida.relatorio_md.read_text(encoding="utf-8")
    trecho = relatorio.split("**Avisos:**", 1)[1][:300] if "**Avisos:**" in relatorio else ""
    confere("gancho" in trecho and "conclusão" in trecho,
            "o relatorio.md avisa do gancho em 3+ linhas e da conclusão cortada",
            " ".join(trecho.split())[:110] or "sem seção de avisos")

    job = ER.job_do_painel(R, saida.slug, entrada, comando="render",
                           somente=("render",), preset="cortes", forcar=True)
    confere(job.get("status") == "concluido", "painel: o job de render termina concluído",
            f"status {job.get('status')}; erro {str((job.get('erro') or {}).get('mensagem'))[:80]}")
    medida = ER.duracao_medida(ER.clipes_mp4(saida, "cortes")[0])
    confere(abs(medida - soma) <= 0.5, "painel: duração do MP4 = soma dos segmentos ±0,5 s",
            f"soma {soma:.2f} s, medido {medida:.2f} s")


def f_p5_v2_um_segmento_sem_composicao(raiz: Path) -> None:
    """Q4 física: sem composição, v2 de 1 segmento renderiza inteiro; 2+ é recusado."""
    from provas import entrada_real as ER

    R = _p5_raiz(raiz, "f-i2")
    video = ER.video_lavfi(_p5_videos(raiz) / "fonte-p5.mp4", 70.0)
    trans = ER.transcricao_sintetica(68.0)
    fr = ER.frases(trans)
    entrada, saida = ER.semear(R, "f-i2", trans, video=video)

    resp = ER.gravar_resposta(R, "um", [ER.item(titulo="Um trecho", segmentos=[_p5_seg(fr, 0, 5)])])
    proc = ER.cli("select", entrada, "--out", R, "--resposta", resp)
    confere(proc.returncode == 0, "`clipper select` aceita o v2 de 1 segmento", _p5_rc(proc))
    clipe = json.loads(saida.selecao_json.read_text(encoding="utf-8"))["clipes"][0]
    esperado = float(clipe["segmentos"][0]["fim"]) - float(clipe["segmentos"][0]["inicio"])
    proc = ER.cli("render", saida.slug, "--out", R, "--preset", "bold-amarelo")
    confere(proc.returncode == 0, "1 segmento: `clipper render --preset bold-amarelo` renderiza",
            _p5_rc(proc))
    mp4s = ER.clipes_mp4(saida, "bold-amarelo")
    confere(len(mp4s) == 1, "1 segmento: saiu um MP4")
    medida = ER.duracao_medida(mp4s[0])
    confere(abs(medida - esperado) <= 0.5, "1 segmento: o MP4 tem o trecho inteiro",
            f"esperado {esperado:.2f} s, medido {medida:.2f} s")
    marca = mp4s[0].stat().st_mtime_ns

    time.sleep(1.1)  # a assinatura do render usa o mtime do selecao.json em segundos
    resp = ER.gravar_resposta(R, "dois", [ER.item(
        titulo="Um trecho", segmentos=[_p5_seg(fr, 0, 2), _p5_seg(fr, 6, 8)])])
    proc = ER.cli("select", entrada, "--out", R, "--resposta", resp)
    confere(proc.returncode == 0, "`clipper select` aceita o v2 de 2 segmentos", _p5_rc(proc))
    proc = ER.cli("render", saida.slug, "--out", R, "--preset", "bold-amarelo")
    texto = ER.saida_do_cli(proc)
    confere(proc.returncode != 0 and "não tem composição" in texto,
            "2 segmentos: o render recusa com o motivo", f"rc={proc.returncode}")
    confere(all(p.stat().st_mtime_ns == marca for p in ER.clipes_mp4(saida, "bold-amarelo")),
            "2 segmentos: nenhum MP4 foi escrito")


def f_p5_capa_regenerada(raiz: Path) -> None:
    """Q5 (D-E): capa e publicacao.md acompanham o MP4, sempre, pelo CLI."""
    from clipper import ffmpeg_utils
    from PIL import Image, ImageChops, ImageStat
    from provas import entrada_real as ER

    R = _p5_raiz(raiz, "f-i3")
    video = ER.video_lavfi(_p5_videos(raiz) / "fonte-p5.mp4", 70.0)
    trans = ER.transcricao_sintetica(68.0)
    fr = ER.frases(trans)
    entrada, saida = ER.semear(R, "f-i3", trans, video=video)

    def selecionar(capa_ts: str) -> float:
        time.sleep(1.1)  # a assinatura do render usa o mtime do selecao.json em segundos
        resp = ER.gravar_resposta(R, f"capa-{capa_ts.replace(':', '')}", [
            ER.item(titulo="Capa", capa_ts=capa_ts, **_p5_seg(fr, 1, 6)),
        ])
        proc = ER.cli("select", entrada, "--out", R, "--resposta", resp)
        confere(proc.returncode == 0, f"`clipper select` com capa_ts {capa_ts}", _p5_rc(proc))
        clipe = json.loads(saida.selecao_json.read_text(encoding="utf-8"))["clipes"][0]
        return float(clipe["capa_ts"]) - float(clipe["inicio"])

    def renderizar(*extra: str) -> tuple[Path, Path, Path]:
        proc = ER.cli("render", saida.slug, "--out", R, "--preset", "cortes", *extra)
        confere(proc.returncode == 0, "`clipper render " + " ".join(extra) + "` termina bem",
                _p5_rc(proc))
        mp4 = ER.clipes_mp4(saida, "cortes")[0]
        return mp4, mp4.with_suffix(".capa.jpg"), mp4.with_suffix(".publicacao.md")

    def bate(capa: Path, mp4: Path, instante: float, rotulo: str) -> None:
        confere(capa.is_file(), f"{rotulo}: capa.jpg existe")
        ref = R / "_entradas" / "referencia.jpg"
        ffmpeg_utils.rodar(["-ss", f"{instante:.3f}", "-i", str(mp4), "-frames:v", "1",
                            "-q:v", "3", "-y", str(ref)], descricao="quadro de referência")
        a, b = Image.open(capa).convert("L"), Image.open(ref).convert("L")
        d = ImageStat.Stat(ImageChops.difference(a, b)).mean[0] if a.size == b.size else 999.0
        confere(d < 1.0, f"{rotulo}: a capa é o quadro do capa_ts atual",
                f"instante {instante:.2f} s, diferença média {d:.3f}")

    instante = selecionar("00:08")
    mp4, capa, pub = renderizar()
    bate(capa, mp4, instante, "1ª rodada")

    instante = selecionar("00:20")
    mp4, capa, pub = renderizar()
    bate(capa, mp4, instante, "capa_ts novo, sem --force")

    marca_mp4 = mp4.stat().st_mtime_ns
    capa.unlink()
    pub.unlink()
    mp4, capa, pub = renderizar()
    confere(capa.is_file() and pub.is_file(),
            "capa e publicacao.md apagadas voltam sem --force")
    confere(mp4.stat().st_mtime_ns == marca_mp4, "… sem re-encodar o MP4")
    bate(capa, mp4, instante, "capa regenerada no reaproveitamento")

    marca_capa = capa.stat().st_mtime_ns
    time.sleep(1.1)
    mp4, capa, pub = renderizar("--force")
    confere(mp4.stat().st_mtime_ns > marca_mp4 and capa.stat().st_mtime_ns > marca_capa,
            "`--force` re-encoda e regrava a capa")
    bate(capa, mp4, instante, "depois do --force")


def f_p5_reframe_dentro_dos_segmentos(raiz: Path) -> None:
    """Q6 (D-F): o reframe amostra só DENTRO dos segmentos mantidos.

    Espião não-invasivo em ffmpeg_utils.rodar: registra -ss/-t das chamadas de
    amostragem e de detecção de tarja e repassa sem mudar nada. O render roda
    por clipper.cli.main -- a mesma função do `python -m clipper`.
    """
    from clipper import ffmpeg_utils
    from provas import entrada_real as ER

    R = _p5_raiz(raiz, "f-i4")
    video = ER.video_lavfi(_p5_videos(raiz) / "fonte-p5.mp4", 70.0)
    trans = ER.transcricao_sintetica(68.0)
    fr = ER.frases(trans)
    entrada, saida = ER.semear(R, "f-i4", trans, video=video)
    resp = ER.gravar_resposta(R, "resp", [ER.item(
        titulo="Reframe", segmentos=[_p5_seg(fr, 0, 2), _p5_seg(fr, 12, 14)])])
    proc = ER.cli("select", entrada, "--out", R, "--resposta", resp)
    confere(proc.returncode == 0, "`clipper select` aceita o v2", _p5_rc(proc))
    clipe = json.loads(saida.selecao_json.read_text(encoding="utf-8"))["clipes"][0]
    trechos = [(float(s["inicio"]), float(s["fim"])) for s in clipe["segmentos"]]

    original = ffmpeg_utils.rodar
    janelas: list[tuple[str, float, float]] = []

    def espiao(args: list[str], *a: Any, **k: Any) -> Any:
        descricao = str(k.get("descricao") or "")
        if descricao.startswith(("amostragem de frames", "detecção de tarja")) and "-ss" in args:
            ss = float(args[args.index("-ss") + 1])
            t = float(args[args.index("-t") + 1])
            janelas.append((descricao.split(" ")[0], ss, ss + t))
        return original(args, *a, **k)

    ffmpeg_utils.rodar = espiao
    try:
        rc = ER.cli_em_processo(["render", saida.slug, "--out", str(R), "--preset", "cortes",
                                 "--force"])
    finally:
        ffmpeg_utils.rodar = original
    confere(rc == 0, "`clipper render` termina bem", f"rc={rc}")
    confere(any(t == "amostragem" for t, _, _ in janelas), "o reframe amostrou quadros",
            f"{len(janelas)} janela(s)")

    def dentro(a: float, b: float) -> bool:
        return any(a >= s0 - 0.05 and b <= s1 + 0.05 for s0, s1 in trechos)

    for tipo, a, b in janelas:
        confere(dentro(a, b), f"janela de {tipo} {a:.2f}–{b:.2f} s cai dentro de um segmento",
                " | ".join(f"{s0:.2f}–{s1:.2f}" for s0, s1 in trechos))
    s0, s1 = trechos[-1]
    confere(any(t == "amostragem" and a >= s0 - 0.05 and b <= s1 + 0.05 for t, a, b in janelas),
            "o último segmento também é amostrado")


def f_p5_gancho_real_nunca_truncado(raiz: Path) -> None:
    """Q10 (P07/P16): os ganchos REAIS saem inteiros. Só contagens (C.11).

    Mede também o caso extremo que o §11.1 exige ver junto: 90 caracteres de
    letras largas e uma palavra única sem espaço.
    """
    from clipper import composicao as C
    from clipper.modelo import Modelo

    dados = json.loads(_fixture_real("resposta-v1.json").read_text(encoding="utf-8"))
    trabalho = _p5_raiz(raiz, "f-g3")
    extremos = {
        "PT caixa alta, 90": _GANCHO_LONGO,
        "W/M, 89": _CONCLUSAO_LARGA,
        "palavra única de 90 W": "W" * 90,
    }
    for nome in MODELOS_COMPOSTOS:
        comp = Modelo.de_fabrica(nome).composicao
        truncados, incompletos, linhas = 0, 0, []
        for i, clipe in enumerate(dados, 1):
            gancho = str(clipe["gancho_sugerido"])
            pil = C.gerar_ativos(comp, "título", trabalho / nome / f"real-{i}", gancho=gancho)["pilula"]
            esperado = " ".join(gancho.split())
            if comp.titulo_maiusculas:
                esperado = esperado.upper()
            desenhado = "".join(pil.get("texto_linhas") or [])
            truncados += 1 if pil.get("truncado") else 0
            incompletos += 0 if desenhado.replace(" ", "") == esperado.replace(" ", "") else 1
            linhas.append(int(pil.get("linhas") or 0))
        confere(truncados == 0, f"{nome}: nenhum dos {len(dados)} ganchos reais sai truncado",
                f"truncados: {truncados}; linhas por gancho: {linhas}")
        confere(incompletos == 0, f"{nome}: cada gancho desenhado é o texto inteiro",
                f"incompletos: {incompletos}")

        for rotulo, texto in extremos.items():
            pil = C.gerar_ativos(comp, "título", trabalho / nome / "extremo", gancho=texto)["pilula"]
            base = int(comp.gancho_y) + int(pil["altura"])
            confere(not pil.get("truncado"),
                    f"{nome}: caso extremo ({rotulo}) também sai inteiro",
                    f"{pil['linhas']} linhas @ {pil['tamanho']} px, altura {pil['altura']} px, "
                    f"base em y={base}")


# ==========================================================================
# Registro
# ==========================================================================

ESTRUTURAIS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "E-M1": ("Emenda 1: round-trip do modelo (JSON aninhado -> filtergraph)", e_modelo_roundtrip),
    "E-M2": ("Emenda 1: a forma flat não é formato de arquivo", e_modelo_flat_nao_recarrega),
    "E-M3": ("Emenda 1: chave desconhecida avisa e não rejeita", e_modelo_avisa_chave_desconhecida),
    "E-M4": ("Emenda 1: preset sem composição segue no caminho F3", e_modelo_sem_composicao),
    "E-R1": ("Regressão: filtergraph x baseline 12fc1e2b (delta só em E1)", e_regressao_filtergraph),
    "E-R2": ("Regressão: .ass x baseline 12fc1e2b (delta só em E2/E3; Style só MarginV)", e_regressao_ass),
    "E-L1": ("E3: conformidade — ≤7 palavras e ≤2 linhas em TODOS os blocos", e_legenda_conformidade),
    "E-L2": ("E3: destaque nunca cai em palavra de ≤2 letras", e_legenda_destaque_pula_curtas),
    "E-L3": ("E3: a guarda de lacuna impede fusão através de pausa longa", e_legenda_guarda_de_lacuna),
    "E-L4": ("E3: a segunda linha (\\N) nasce da largura e só dela", e_legenda_segunda_linha_por_largura),
    "E-G1": ("E1: gancho com enable, fade de saída e Y na zona segura", e_gancho_no_filtergraph),
    "E-G2": ("E1: o escape devolve a caixa permanente de título", e_gancho_escape_restaura_titulo),
    "E-V1": ("P2: v2 válida passa; o span não é o corte", e_v2_valida_passa),
    "E-V2": ("P2: as 8 mordidas, cada uma discriminando o motivo", e_v2_mordidas),
    "E-V3": ("P2: não-sobreposição é pela UNIÃO, não pelo span", e_v2_uniao_nao_span),
    "E-V4": ("P2: o contrato v1 segue intacto no validador", e_v1_intacto_no_validador),
    "E-V5": ("Q3 D-C: esquema × validador; `select --api` pelo CLI aceita v2", e_esquema_api_aceita_v2),
    "E-C1": ("P2: sem conclusão, grafo idêntico; com ela, 2 etapas", e_conclusao_ausente_grafo_identico),
    "E-C2": ("P2: concat antes do crop, PNGs renumerados, crossfade", e_concat_v2_no_grafo),
    "E-C3": ("P2: punches e legendas remapeados para a timeline", e_remapeamento_de_tempos),
    "E-P1": ("P3: capa_ts fora dos segmentos é rejeitado", e_capa_ts_fora_rejeita),
    "E-P2": ("P3: limites de descricao e conclusao", e_opcionais_limites),
    "E-P3": ("P3: publicacao.md com título, gancho e checklist", e_publicacao_md),
    "E-P4": ("P4: o prompt v2 ensina segmentos, gancho e payoff", e_prompt_v2),
    "E-C4": ("P2: vão ≥ 24 px entre a conclusão e o bloco de legenda", e_conclusao_nao_encosta_na_legenda),
    "E-I1": ("Q1 D-B: o selecao.json v2 do CLI passa no portão do render", e_p5_selecao_v2_passa_no_render),
    "E-I2": ("Q2 D-A: sobreposição entre 3 clipes não adjacentes, pelo CLI", e_p5_sobreposicao_tres_clipes),
    "E-I3": ("Q10 P01: aviso de ajuste ≥3 s também no v2, pelo CLI", e_p5_aviso_de_ajuste_v2),
    "E-I4": ("Q10 P03: segmentos colados fundidos com nota; pausa real não", e_p5_segmentos_colados_fundidos),
    "E-I5": ("Q4 D-D: v2 de 2+ segmentos sem composição é recusado, pelo CLI", e_p5_v2_sem_composicao_recusado),
    "E-X1": ("Q7: resposta v1 REAL passa pelo `clipper select` (contagens)", e_material_real_validador),
    "E-X2": ("Q7: quebrador sobre a transcrição REAL (contagens)", e_material_real_quebrador),
    "E-F1": ("Q9: provas/fixtures/** é -text; bytes reais intactos", e_fixtures_sem_conversao_de_linha),
}

FISICAS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "F-G1": ("Gerador lavfi produz clipe sondável", f_clipe_curto_gera),
    "F-G2": ("E1 física: gancho visível em t=1 s e ausente em t=4 s", f_gancho_no_frame),
    "F-V1": ("P2 física: duração do MP4 = soma dos segmentos ±0,5 s", f_v2_duracao),
    "F-V2": ("P2 física: -14 LUFS ±1 no áudio concatenado", f_v2_lufs),
    "F-P1": ("P3 física: capa.jpg sai do instante certo", f_v2_capa),
    "F-C1": ("P2 física: a conclusão aparece no fim, não no meio", f_conclusao_no_frame),
    "F-I1": ("Q1 D-B física: select → render v2 pelo CLI e pelo painel; MP4 = soma", f_p5_v2_ponta_a_ponta),
    "F-I2": ("Q4 física: sem composição, 1 segmento renderiza e 2+ é recusado", f_p5_v2_um_segmento_sem_composicao),
    "F-I3": ("Q5 D-E: capa e publicacao.md acompanham o MP4, pelo CLI", f_p5_capa_regenerada),
    "F-I4": ("Q6 D-F: o reframe amostra dentro dos segmentos, pelo CLI", f_p5_reframe_dentro_dos_segmentos),
    "F-G3": ("Q10 P07: ganchos reais e caso extremo nunca truncados (contagens)", f_p5_gancho_real_nunca_truncado),
}


def main(argv: list[str]) -> int:
    quer_fisicas = "--fisicas" in argv
    nomes = [a.upper() for a in argv if not a.startswith("--")]

    casos: dict[str, tuple[str, Callable[[Path], None]]] = dict(ESTRUTURAIS)
    if quer_fisicas:
        casos.update(FISICAS)

    pedidos = [n for n in nomes if n in casos] or list(casos)
    raiz = RAIZ / "_teste" / "out-prova-f6"

    titulo = "PROVAS DA F6 — camada editorial"
    if not quer_fisicas:
        titulo += "  (só ESTRUTURAIS; use --fisicas para as demais)"
    print(f"\n{'=' * 78}\n{titulo}\n{'=' * 78}")
    print(f"  fixtures: {DIR_FIXTURES}\n")

    resultados: list[tuple[str, str, float, str]] = []
    for nome in pedidos:
        descricao, funcao = casos[nome]
        print(f"{_amarelo}{nome}{_zero}  {descricao}")
        t0 = time.monotonic()
        try:
            funcao(raiz)
            resultados.append((nome, "passou", time.monotonic() - t0, ""))
        except Pulou as exc:
            print(f"    {_amarelo}pulou{_zero}  {exc}")
            resultados.append((nome, "pulou", time.monotonic() - t0, str(exc)[:160]))
        except BaseException as exc:  # noqa: BLE001 - a prova relata, nao propaga
            if not isinstance(exc, Falhou):
                import traceback

                traceback.print_exc()
            resultados.append((nome, "falhou", time.monotonic() - t0, str(exc)[:160]))
        print()

    print("=" * 78)
    marcas = {
        "passou": f"{_verde}PASSOU{_zero}",
        "pulou": f"{_amarelo}PULOU {_zero}",
        "falhou": f"{_vermelho}FALHOU{_zero}",
    }
    for nome, estado, segundos, motivo in resultados:
        print(f"  {nome:6} {marcas[estado]}  {segundos:6.2f}s  {motivo}")
    passaram = sum(1 for _, e, _, _ in resultados if e == "passou")
    pularam = sum(1 for _, e, _, _ in resultados if e == "pulou")
    falharam = sum(1 for _, e, _, _ in resultados if e == "falhou")
    print("=" * 78)
    print(f"  {passaram} passaram, {pularam} pularam, {falharam} falharam")
    if not quer_fisicas:
        print(f"  {len(FISICAS)} provas FÍSICAS não foram executadas (precisam de ffmpeg).")
    return 1 if falharam else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
