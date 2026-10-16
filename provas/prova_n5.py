"""Provas da fase N-5 -- design do app (RULINGS §30). Espelha prova_n2.py.

    python provas/prova_n5.py                # estruturais
    python provas/prova_n5.py --fisicas      # + fisicas
    python provas/prova_n5.py --gerar        # imprime o bloco PREVIAS para o app.js

O que se prova:
  N5-E1  a tabela PREVIAS do app.js e a que os presets de fabrica geram hoje.
         A galeria de modelos desenha a partir dela; se alguem mexer num
         preset e nao regenerar, a prova cai em vez de a previa mentir.
  N5-E2  o app nao usa mais os enfeites que o Bruno leu como "cara de IA"
         (claquete, pelicula, ingresso, REC piscando, brilho no botao) e
         segue sem pedir nada a terceiros.
  N5-F1  a galeria num Chromium de verdade: as previas aparecem, o karaoke
         segue a regra de cores do motor, a escolha vai no pedido e o quadro
         do video do usuario entra nas previas.

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from provas.prova_f6 import Falhou, Pulou, _amarelo, _verde, _vermelho, _zero, confere  # noqa: E402

# Os quatro modelos que o app oferece, na ordem da galeria. Precisa bater com
# a lista PRESETS do app.js (N5-E1 confere).
MODELOS = ("cortes", "cortes-editorial", "bold-amarelo", "clean-branco")

INICIO = "// >>> PREVIAS"
FIM = "// <<< PREVIAS"


# ==========================================================================
# Gerador: presets de fabrica -> tabela da previa
# ==========================================================================


def _ass(cor: str) -> tuple[str, float]:
    """'&HAABBGGRR&' -> ('#RRGGBB', opacidade). No ASS, alfa 00 e opaco."""
    m = re.fullmatch(r"&H([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})&?", cor.strip())
    if not m:
        raise ValueError(f"cor ASS inesperada: {cor!r}")
    aa, bb, gg, rr = (int(x, 16) for x in m.groups())
    return f"#{rr:02X}{gg:02X}{bb:02X}", round(1 - aa / 255, 3)


def previas_dos_presets() -> dict[str, Any]:
    """So o que a previa desenha, em pixels do canvas 1080x1920 do motor."""
    from clipper import modelo

    tabela: dict[str, Any] = {}
    for nome in MODELOS:
        m = modelo.carregar(nome)
        p = m.legenda
        por_falar, _ = _ass(p.cor_por_falar)
        falada, _ = _ass(p.cor_falada)
        contorno, _ = _ass(p.cor_contorno)
        sombra, sombra_op = _ass(p.cor_sombra)
        legenda = {
            "fonte": p.fonte,
            "tamanho": int(p.tamanho),
            "negrito": bool(p.negrito),
            "maiusculas": bool(p.maiusculas),
            "espacamento": p.espacamento,
            "por_falar": por_falar,
            "falada": falada,
            # Sem pop, a palavra so troca de "por falar" para "falada" e fica
            # (legendas._bloco_palavra); com pop ela acende na cor de destaque,
            # cresce e volta a "falada" no fim.
            "destaque": _ass(p.cor_do_pop)[0] if p.tem_pop else None,
            "pop": int(p.pop_escala) if p.tem_pop else 100,
            "destaque_minimo": int(p.destaque_minimo_letras),
            "contorno_cor": contorno,
            "contorno": p.contorno,
            "sombra_cor": sombra,
            "sombra_opacidade": sombra_op,
            "sombra": p.sombra,
            "margem_lateral": int(p.margem_lateral),
            "margem_inferior": int(p.margem_inferior),
            "palavras_linha": int(p.max_palavras_linha),
        }
        c = m.composicao
        comp = None
        if c is not None:
            comp = {
                "cartao": {
                    "x": c.cartao_x, "y": c.cartao_y,
                    "largura": c.cartao_largura, "altura": c.cartao_altura,
                    "raio": c.cartao_raio,
                    "traco": c.traco_largura, "traco_cor": c.traco_cor,
                    "traco_opacidade": c.traco_opacidade,
                    "sombra_dy": c.sombra_dy, "sombra_sigma": c.sombra_sigma,
                    "sombra_opacidade": c.sombra_opacidade, "sombra_cor": c.sombra_cor,
                },
                "fundo": {
                    "escurecer": c.fundo_escurecer, "saturacao": c.fundo_saturacao,
                    "vinheta": c.vinheta,
                },
                "titulo": None if not c.titulo_ativo else {
                    "fonte": c.titulo_fonte, "tamanho": c.titulo_tamanho,
                    "maiusculas": c.titulo_maiusculas, "cor": c.titulo_cor,
                    "pilula_cor": c.titulo_pilula_cor,
                    "pilula_opacidade": c.titulo_pilula_opacidade,
                    "altura": c.titulo_altura, "raio": c.titulo_raio,
                    "padding_h": c.titulo_padding_h,
                    "largura_maxima": c.titulo_largura_maxima,
                    "x": c.titulo_x, "y": c.titulo_y,
                    "acento": c.titulo_acento, "acento_cor": c.titulo_acento_cor,
                    "acento_largura": c.titulo_acento_largura,
                    "acento_altura": c.titulo_acento_altura,
                    "acento_gap": c.titulo_acento_gap,
                },
                "progresso": None if not c.progresso_ativo else {
                    "y": c.progresso_y, "altura": c.progresso_altura,
                    "recuo": c.progresso_recuo,
                    "trilho_cor": c.progresso_trilho_cor,
                    "trilho_opacidade": c.progresso_trilho_opacidade,
                    "cor": c.progresso_cor, "opacidade": c.progresso_opacidade,
                    "contorno": c.progresso_contorno,
                    "contorno_cor": c.progresso_contorno_cor,
                    "contorno_opacidade": c.progresso_contorno_opacidade,
                },
                "scrim": None if not c.scrim_ativo else {
                    "y_inicio": c.scrim_y_inicio, "y_fim": c.scrim_y_fim,
                    "opacidade": c.scrim_opacidade, "cor": c.scrim_cor,
                },
            }
        tabela[nome] = {"legenda": legenda, "composicao": comp}
    return tabela


def bloco_js(tabela: dict[str, Any]) -> str:
    corpo = json.dumps(tabela, ensure_ascii=False, indent=2, sort_keys=False).replace("\n", "\n  ")
    return (
        f"{INICIO} -- gerado por `python provas/prova_n5.py --gerar`; N5-E1 confere\n"
        f"  const PREVIAS = {corpo};\n"
        f"  {FIM}"
    )


def _previas_do_app() -> dict[str, Any]:
    texto = (RAIZ / "app" / "app.js").read_text(encoding="utf-8")
    m = re.search(re.escape(INICIO) + r"[^\r\n]*\r?\n\s*const PREVIAS = (\{.*?\});\r?\n\s*"
                  + re.escape(FIM), texto, re.S)
    if not m:
        raise Falhou("o app.js não tem o bloco PREVIAS entre os marcadores")
    return json.loads(m.group(1))


# ==========================================================================
# Estruturais
# ==========================================================================


def e_previas_batem(_: Path) -> None:
    """N5-E1: a galeria desenha o que os presets de fabrica mandam."""
    do_app = _previas_do_app()
    dos_presets = previas_dos_presets()
    confere(list(do_app) == list(MODELOS), "a tabela do app tem os 4 modelos, na ordem da galeria",
            ", ".join(do_app))
    for nome in MODELOS:
        diferencas = _diferencas(do_app.get(nome), dos_presets[nome])
        confere(not diferencas, f"a prévia de “{nome}” bate com o preset", "; ".join(diferencas[:4]))

    texto = (RAIZ / "app" / "app.js").read_text(encoding="utf-8")
    nomes_galeria = re.findall(r'\{ nome: "([a-z-]+)", titulo:', texto)
    confere(tuple(nomes_galeria) == MODELOS, "a galeria oferece exatamente os 4 modelos de fábrica",
            ", ".join(nomes_galeria))

    # Mutante embutido: um preset com outra cor tem de ser pego.
    torto = json.loads(json.dumps(dos_presets))
    torto["cortes"]["legenda"]["destaque"] = "#FF0000"
    confere(_diferencas(torto["cortes"], dos_presets["cortes"]),
            "uma cor trocada no preset seria acusada (mutante)")


def _diferencas(a: Any, b: Any, caminho: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        saida: list[str] = []
        for k in sorted(set(a) | set(b)):
            saida += _diferencas(a.get(k, "<falta>"), b.get(k, "<falta>"), f"{caminho}.{k}")
        return saida
    if isinstance(a, float) or isinstance(b, float):
        try:
            if abs(float(a) - float(b)) < 1e-9:
                return []
        except (TypeError, ValueError):
            pass
    return [] if a == b else [f"{caminho.lstrip('.')}: app={a!r} preset={b!r}"]


def e_sem_enfeites(_: Path) -> None:
    """N5-E2: os enfeites lidos como "cara de IA" sairam; nada de terceiros."""
    css = (RAIZ / "app" / "estilos.css").read_text(encoding="utf-8")
    html = (RAIZ / "app" / "index.html").read_text(encoding="utf-8")
    js = (RAIZ / "app" / "app.js").read_text(encoding="utf-8")
    tudo = css + html + js
    for marca, o_que in (
        ("claquete", "a claquete listrada"),
        ("ingresso", "o pacote em forma de ingresso"),
        ("--furo", "a trilha perfurada de película"),
        ("quadro-cena", "o rosto desfocado de mentira"),
        ("class=\"rec\"", "o REC piscando"),
        ("ilha de edição", "o jargão “ilha de edição”"),
        ("Seus rolos", "o jargão “rolos”"),
    ):
        confere(marca not in tudo, f"saiu {o_que}")
    confere(not _brilhos_amarelos(css), "nenhum brilho amarelo (sombra borrada) em volta de botão ou cartão",
            "; ".join(_brilhos_amarelos(css)[:2]))
    externos = re.findall(r"""(?:src|href)=["'](https?://[^"']+)""", html)
    externos += re.findall(r"url\(\s*[\"']?(https?://[^)\"']+)", css)
    confere(not externos, "o app não carrega nada de fora (fontes e imagens locais)", ", ".join(externos[:3]))
    usos_mono = css.count("var(--f-mono)") + css.count("JetBrains")
    confere(usos_mono == 0, "sem rótulos em fonte de terminal (mono) espalhados pela interface",
            f"{usos_mono} usos")


def _brilhos_amarelos(css: str) -> list[str]:
    """Sombras amarelas COM desfoque. O anel de foco (0 0 0 3px) nao conta:
    e contorno nitido, pedido de acessibilidade, nao brilho."""
    achados = []
    for decl in re.findall(r"(?:box|text)-shadow:\s*([^;}]+)", css):
        for sombra in re.split(r",(?![^(]*\))", decl):
            if not re.search(r"rgba?\(\s*255,\s*229,\s*0|#ffe500|var\(--acento\)", sombra, re.I):
                continue
            # Medidas na ordem do CSS: x, y, desfoque, espalhamento. O 0 vem
            # sem unidade, e precisa contar como medida.
            sem_cor = re.sub(r"rgba?\([^)]*\)|#[0-9a-f]{3,8}|var\([^)]*\)", " ", sombra, flags=re.I)
            medidas = [m for m in sem_cor.split() if re.fullmatch(r"-?[\d.]+(px)?", m)]
            if len(medidas) >= 3 and float(medidas[2].removesuffix("px")) > 0:
                achados.append(sombra.strip())
    return achados


ESTRUTURAIS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "N5-E1": ("prévias dos modelos = presets de fábrica", e_previas_batem),
    "N5-E2": ("sem enfeites de “cara de IA”, sem terceiros", e_sem_enfeites),
}


# ==========================================================================
# Fisicas
# ==========================================================================


def f_galeria(raiz: Path) -> None:
    """N5-F1: a galeria de modelos num Chromium de verdade."""
    from provas.nuvem_falsa import SupabaseFalso, s3_falso
    from provas.prova_n1 import _pasta
    from provas.prova_n2 import SEGREDO_R2, _ambiente, _node_com_playwright, _servidor_do_app

    node, env_node = _node_com_playwright()
    saida = _pasta(raiz, "n5-f1")
    quadro = _video_de_teste(saida)
    sb = SupabaseFalso()
    sb.cadastrar("ana@exemplo.com", "senha-da-ana")
    with sb.servir() as url_sb, s3_falso(SEGREDO_R2) as (url_s3, _objetos, _):
        # Com a CSP de producao: se o app precisasse de estilo inline ou de
        # algo de fora, o navegador bloquearia e a prova cairia.
        with _servidor_do_app(_ambiente(url_sb, url_s3), csp=True) as url_app:
            proc = subprocess.run(
                [node, str(RAIZ / "provas" / "n5_galeria.cjs")],
                env={**env_node, "APP_URL": url_app, "SAIDA": str(saida), "VIDEO": str(quadro),
                     "PREVIAS": json.dumps(previas_dos_presets())},
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
    checks = [json.loads(l[6:]) for l in proc.stdout.splitlines() if l.startswith("CHECK ")]
    if not checks:
        raise Falhou(f"o script da galeria não relatou nada: {(proc.stderr or proc.stdout)[-300:]}")
    for c in checks:
        confere(c["ok"], c["descricao"], c["detalhe"] if not c["ok"] else "")
    pedidos = [p for p in sb.pedidos if p["caminho"] == "/rest/v1/rpc/criar_trabalho"]
    confere(bool(pedidos) and pedidos[-1]["corpo"].get("p_preset") == "bold-amarelo",
            "o modelo escolhido na galeria foi o que seguiu no pedido",
            pedidos[-1]["corpo"].get("p_preset") if pedidos else "nenhum pedido")
    print(f"    prints  {saida}")


def _video_de_teste(pasta: Path) -> Path:
    """Video curto com um quadro reconhecivel (barras de cor), feito pelo ffmpeg.

    WebM/VP9 e nao MP4/H.264: o Chromium do Playwright nao traz o decodificador
    H.264 (o Chrome, o Edge e o Safari de quem usa o app trazem). Com MP4 aqui
    o navegador nao le o quadro e a prova mediria a falta de codec, nao o app.
    """
    import shutil

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise Pulou("pendente: N5-F1 precisa do ffmpeg para gerar o vídeo de teste.")
    alvo = pasta / "quadro-teste.webm"
    p = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "smptehdbars=size=1280x720:rate=30:duration=4",
         "-pix_fmt", "yuv420p", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "40", "-deadline", "realtime", str(alvo)],
        capture_output=True, text=True)
    if p.returncode:
        raise Falhou(f"ffmpeg não gerou o vídeo de teste: {p.stderr[-200:]}")
    return alvo


FISICAS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "N5-F1": ("galeria de modelos num Chromium real (Playwright)", f_galeria),
}


# ==========================================================================


def main(argv: list[str]) -> int:
    if "--gerar" in argv:
        print(bloco_js(previas_dos_presets()))
        return 0
    quer_fisicas = "--fisicas" in argv
    nomes = [a.upper() for a in argv if not a.startswith("--")]

    casos: dict[str, tuple[str, Callable[[Path], None]]] = dict(ESTRUTURAIS)
    if quer_fisicas:
        casos.update(FISICAS)
    desconhecidos = [n for n in nomes if n not in casos]
    if desconhecidos:
        print(f"prova desconhecida: {', '.join(desconhecidos)}. Disponíveis: {', '.join(casos)}")
        return 2
    pedidos = nomes or list(casos)
    raiz = RAIZ / "_teste" / "out-prova-n5"

    titulo = "PROVAS DA N-5 — design do app"
    if not quer_fisicas:
        titulo += "  (só ESTRUTURAIS; use --fisicas para as demais)"
    print(f"\n{'=' * 78}\n{titulo}\n{'=' * 78}\n")

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
        print(f"  {len(FISICAS)} prova(s) FÍSICA(S) não executada(s).")
    return 1 if falharam else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
