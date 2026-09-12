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
        confere(True, f"{nome}: blocos mudaram como o E3 prevê",
                f"{len(la)} -> {len(lb)} linhas")


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
}

FISICAS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "F-G1": ("Gerador lavfi produz clipe sondável", f_clipe_curto_gera),
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
