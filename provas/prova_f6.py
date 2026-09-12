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
        so_estilo = all(x.startswith("Style:") and y.startswith("Style:") for x, y in difs_cab)
        confere(
            len(cab_a) == len(cab_b) and so_estilo,
            f"{nome}: no cabeçalho, só a linha Style muda (E2)",
            EXCECOES["E2"] if difs_cab else "cabeçalho intacto",
        )
        confere(len(lb) <= len(la), f"{nome}: o E3 não criou bloco novo",
                f"{la.count('') + sum(1 for x in la if x.startswith('Dialogue:'))} -> "
                f"{sum(1 for x in lb if x.startswith('Dialogue:'))} blocos")


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
# Registro
# ==========================================================================

ESTRUTURAIS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "E-M1": ("Emenda 1: round-trip do modelo (JSON aninhado -> filtergraph)", e_modelo_roundtrip),
    "E-M2": ("Emenda 1: a forma flat não é formato de arquivo", e_modelo_flat_nao_recarrega),
    "E-M3": ("Emenda 1: chave desconhecida avisa e não rejeita", e_modelo_avisa_chave_desconhecida),
    "E-M4": ("Emenda 1: preset sem composição segue no caminho F3", e_modelo_sem_composicao),
    "E-R1": ("Regressão: filtergraph x baseline 12fc1e2b (delta só em E1)", e_regressao_filtergraph),
    "E-R2": ("Regressão: .ass x baseline 12fc1e2b (delta só em E2/E3)", e_regressao_ass),
    "E-L1": ("E3: conformidade — ≤7 palavras e ≤2 linhas em TODOS os blocos", e_legenda_conformidade),
    "E-L2": ("E3: destaque nunca cai em palavra de ≤2 letras", e_legenda_destaque_pula_curtas),
    "E-L3": ("E3: a guarda de lacuna impede fusão através de pausa longa", e_legenda_guarda_de_lacuna),
    "E-L4": ("E3: a segunda linha (\\N) nasce da largura e só dela", e_legenda_segunda_linha_por_largura),
    "E-G1": ("E1: gancho com enable, fade de saída e Y na zona segura", e_gancho_no_filtergraph),
    "E-G2": ("E1: o escape devolve a caixa permanente de título", e_gancho_escape_restaura_titulo),
}

FISICAS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "F-G1": ("Gerador lavfi produz clipe sondável", f_clipe_curto_gera),
    "F-G2": ("E1 física: gancho visível em t=1 s e ausente em t=4 s", f_gancho_no_frame),
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
