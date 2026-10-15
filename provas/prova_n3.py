"""Provas da fase N-3 -- compra de créditos (RULINGS §29.5). Espelha prova_n2.py.

    python provas/prova_n3.py                # estruturais
    python provas/prova_n3.py --fisicas      # + fisicas
    python provas/prova_n3.py N3-E1 N3-F1    # casos escolhidos

Fisicas e o que cada uma precisa:
  N3-F1  banco das compras -> CLIPPRO_PROVA_PG (Postgres de TESTE) + psql
  N3-F2  compra no Chromium -> node + playwright, Mercado Pago FALSO local

Nada aqui fala com o Mercado Pago de verdade.

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from provas.prova_f6 import (  # noqa: E402
    Falhou,
    Pulou,
    _amarelo,
    _verde,
    _vermelho,
    _zero,
    confere,
)
from provas.prova_n1 import _SUPABASE_IMITADO, _pasta  # noqa: E402
from provas.prova_n2 import (  # noqa: E402
    _AUTH_IMITADO,
    ANA,
    BIA,
    _Banco,
    _erro,
    _psql_ou_pula,
    _saldo,
)


# ==========================================================================
# Fisicas
# ==========================================================================


def f_banco_das_compras(raiz: Path) -> None:
    """N3-F1: pacotes, compra e crédito só pela porta certa, num Postgres real."""
    db = _Banco(*_psql_ou_pula())
    pasta = RAIZ / "nuvem" / "supabase"
    p = db("drop table if exists public.compras, public.pacotes cascade;"
           + _SUPABASE_IMITADO + _AUTH_IMITADO)
    confere(p.returncode == 0, "o banco de teste imita o Supabase", _erro(p))
    for rodada in (1, 2):
        ps = [db(arquivo=pasta / n) for n in ("001_fila.sql", "002_contas.sql", "003_compras.sql")]
        falhas = [_erro(x) for x in ps if x.returncode]
        confere(not falhas, f"001 + 002 + 003 rodam em ordem (rodada {rodada})", "; ".join(falhas))

    db.valor("insert into convites (email) values ('ana@exemplo.com')")
    db.valor(f"insert into auth.users values ('{ANA}', 'ana@exemplo.com', now())")
    db.valor(f"insert into auth.users values ('{BIA}', 'bia@exemplo.com', now())")
    db.valor("insert into pacotes values ('p60', '60 minutos', 60, 1990, true, 1), "
             "('p-velho', 'antigo', 120, 2990, false, 2)")

    vistos = db.valor("select string_agg(id, ',') from pacotes", como=ANA)
    confere(vistos == "p60", "o usuário só vê os pacotes ativos", vistos)
    p = db("select count(*) from pacotes", como="anon")
    confere(p.returncode != 0, "sem login, nem os pacotes aparecem")

    c1 = db.valor("select iniciar_compra('p60')", como=ANA)
    confere(bool(c1), "a convidada abre uma compra do pacote ativo")
    p = db("select iniciar_compra('p-velho')", como=ANA)
    confere(p.returncode != 0 and "não está à venda" in p.stderr, "pacote inativo não se compra", _erro(p))
    p = db("select iniciar_compra('p60')", como=BIA)
    confere(p.returncode != 0 and "só para convidados" in p.stderr, "conta sem convite não compra")

    p = db(f"select confirmar_compra('{c1}', 'mp-1', 1990, true)", como=ANA)
    confere(p.returncode != 0 and "permission denied" in p.stderr,
            "o usuário NÃO consegue confirmar a própria compra (crédito só pelo webhook)")
    r1 = db.valor(f"select confirmar_compra('{c1}', 'mp-1', 1990, true)", como="worker")
    r2 = db.valor(f"select confirmar_compra('{c1}', 'mp-1', 1990, true)", como="worker")
    confere(r1 == "creditada" and r2 == "ja_processada" and _saldo(db, ANA) == 360,
            "pagamento aprovado credita 60 min uma vez só (300 → 360), mesmo com webhook repetido",
            f"{r1}/{r2}, saldo {_saldo(db, ANA)}")

    c2 = db.valor("select iniciar_compra('p60')", como=ANA)
    p = db(f"select confirmar_compra('{c2}', 'mp-2', 1000, true)", como="worker")
    confere(p.returncode != 0 and "diferente do preço" in p.stderr and _saldo(db, ANA) == 360,
            "valor pago diferente do preço não credita", _erro(p))
    r = db.valor(f"select confirmar_compra('{c2}', 'mp-2', 1990, false)", como="worker")
    confere(r == "recusada" and _saldo(db, ANA) == 360, "pagamento recusado não credita")

    c3 = db.valor("select iniciar_compra('p60')", como=ANA)
    db.valor("update pacotes set preco_centavos = 2490 where id = 'p60'")
    r = db.valor(f"select confirmar_compra('{c3}', 'mp-3', 1990, true)", como="worker")
    confere(r == "creditada" and _saldo(db, ANA) == 420,
            "o preço fica congelado no momento da compra (Bruno mudou o preço depois)")

    c4 = db.valor("select iniciar_compra('p60')", como=ANA)
    p = db(f"select confirmar_compra('{c4}', 'mp-1', 2490, true)", como="worker")
    confere(p.returncode != 0 and _saldo(db, ANA) == 420,
            "um pagamento já usado não credita uma segunda compra", _erro(p))

    meus = db.valor("select count(*) from compras", como=ANA)
    alheios = db.valor("select count(*) from compras", como=BIA)
    confere(meus == "4" and alheios == "0", "cada conta só vê as próprias compras", f"{meus}/{alheios}")
    extrato = db.valor("select string_agg(motivo || ':' || delta, ',' order by id) from movimentos",
                       como=ANA)
    confere(extrato == "cadastro:300,compra:60,compra:60",
            "o extrato da conta mostra o bônus e as duas compras", extrato)

    db.valor("delete from compras where status = 'pendente'")
    for _ in range(5):
        db.valor("select iniciar_compra('p60')", como=ANA)
    p = db("select iniciar_compra('p60')", como=ANA)
    confere(p.returncode != 0 and "várias compras" in p.stderr,
            "no máximo 5 compras abertas por hora (clique repetido)", _erro(p))


FISICAS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "N3-F1": ("banco das compras num Postgres real", f_banco_das_compras),
}


# ==========================================================================
# Estruturais: Mercado Pago e rotas contra os falsos (provas/nuvem_falsa.py)
# ==========================================================================

APP_URL = "https://clippro-app.exemplo"


def _amb(url_sb: str, url_mp: str, **mexe: str) -> dict[str, str]:
    from provas.nuvem_falsa import MercadoPagoFalso, SupabaseFalso

    amb = {"SUPABASE_URL": url_sb, "SUPABASE_PUBLISHABLE_KEY": SupabaseFalso.CHAVE_PUBLICA,
           "SUPABASE_SECRET_KEY": SupabaseFalso.CHAVE_SECRETA, "COMPRAS_ATIVAS": "1",
           "MP_ACCESS_TOKEN": MercadoPagoFalso.TOKEN, "MP_WEBHOOK_SECRET": MercadoPagoFalso.SEGREDO,
           "MP_API": url_mp, "APP_URL": APP_URL}
    amb.update(mexe)
    return amb


def _loja() -> Any:
    from provas.nuvem_falsa import SupabaseFalso

    sb = SupabaseFalso()
    sb.cadastrar("ana@exemplo.com", "senha-da-ana")
    sb.cadastrar("bia@exemplo.com", "senha-da-bia", liberado=False)
    sb.pacotes += [
        {"id": "p60", "nome": "60 minutos", "minutos": 60, "preco_centavos": 1990, "ativo": True, "ordem": 1},
        {"id": "p-off", "nome": "antigo", "minutos": 120, "preco_centavos": 2990, "ativo": False, "ordem": 2},
    ]
    return sb


def e_assinatura_mp(_: Path) -> None:
    """N3-E1: a assinatura do webhook segue o manifest oficial do Mercado Pago."""
    import hashlib
    import hmac

    from nuvem.mercadopago import assinatura_valida, manifest

    segredo, pid, req, ts = "segredo", "123456789", "bb56a2f1-6aae-46ac-982e-9dcd3581d08e", "1742505638683"
    confere(manifest(pid, req, ts) == f"id:{pid};request-id:{req};ts:{ts};",
            "o manifest é id:…;request-id:…;ts:…; (documentação oficial)")
    v1 = hmac.new(segredo.encode(), manifest(pid, req, ts).encode(), hashlib.sha256).hexdigest()
    confere(assinatura_valida(f"ts={ts},v1={v1}", req, pid, segredo), "assinatura certa passa")
    confere(assinatura_valida(f"ts={ts}, v1={v1.upper()}", req, pid, segredo),
            "espaço depois da vírgula e hex maiúsculo também passam")
    tortos = {
        "outro pagamento": (f"ts={ts},v1={v1}", req, "123456780"),
        "outro request-id": (f"ts={ts},v1={v1}", "x", pid),
        "ts trocado": (f"ts=1,v1={v1}", req, pid),
        "sem v1": (f"ts={ts}", req, pid),
        "sem cabeçalho": (None, req, pid),
    }
    aceitos = [r for r, (x, q, d) in tortos.items() if assinatura_valida(x, q, d, segredo)]
    confere(not aceitos, "assinatura de outro pagamento, request, ts ou sem cabeçalho é recusada",
            ", ".join(aceitos))
    confere(not assinatura_valida(f"ts={ts},v1={v1}", req, pid, "outro-segredo"),
            "segredo errado é recusado")
    confere(manifest("ABC123", None, ts) == f"id:abc123;ts:{ts};",
            "parte ausente sai do manifest e id alfanumérico vai em minúsculas")


def e_comprar(_: Path) -> None:
    """N3-E2: abrir a compra cria a preferência com o preço CONGELADO da compra."""
    from nuvem import app
    from provas.nuvem_falsa import MercadoPagoFalso

    sb, mp = _loja(), MercadoPagoFalso()
    with sb.servir() as url_sb, mp.servir() as url_mp:
        amb = _amb(url_sb, url_mp)
        tok = sb.token_de("ana@exemplo.com")
        st, r = app.iniciar_pagamento({**amb, "COMPRAS_ATIVAS": ""}, tok, {"pacote": "p60"})
        confere(st == 503 and "lançamento" in r["erro"] and not mp.preferencias,
                "com as vendas desligadas: 503, e nada vai ao Mercado Pago")
        confere(app.configuracao_publica({**amb, "COMPRAS_ATIVAS": ""})[1]["compras"] is False
                and app.configuracao_publica(amb)[1]["compras"] is True,
                "/api/config diz ao app se a loja está aberta")
        confere(app.iniciar_pagamento(amb, None, {"pacote": "p60"})[0] == 401, "sem login: 401")
        confere(app.iniciar_pagamento(amb, tok, {"pacote": "../x"})[0] == 400, "pacote torto: 400")
        st, r = app.iniciar_pagamento(amb, tok, {"pacote": "p-off"})
        confere(st == 400 and r["erro"] == "este pacote não está à venda.",
                "pacote inativo: a mensagem do banco chega ao usuário", r.get("erro", ""))
        st, r = app.iniciar_pagamento(amb, sb.token_de("bia@exemplo.com"), {"pacote": "p60"})
        confere(st == 400 and "convidados" in r["erro"], "conta sem convite não compra")

        st, r = app.iniciar_pagamento(amb, tok, {"pacote": "p60"})
        confere(st == 200 and r["url"].startswith(url_mp + "/checkout/"),
                "devolve o link de pagamento do Mercado Pago")
        pref = next(iter(mp.preferencias.values()))
        item = pref["items"][0]
        confere(item["unit_price"] == 19.9 and item["currency_id"] == "BRL" and item["quantity"] == 1,
                "o item vai com R$ 19,90 em BRL", json.dumps(item, ensure_ascii=False))
        confere(pref["external_reference"] == r["compra"]
                and pref["notification_url"] == f"{APP_URL}/api/mp_webhook"
                and pref["back_urls"]["success"] == f"{APP_URL}/#/compra/aprovada"
                and pref["payer"]["email"] == "ana@exemplo.com",
                "a preferência leva a compra, o webhook, as voltas e o e-mail")
        sb.pacotes[0]["preco_centavos"] = 2490
        app.iniciar_pagamento(amb, tok, {"pacote": "p60"})
        confere(list(mp.preferencias.values())[-1]["items"][0]["unit_price"] == 24.9,
                "preço novo do pacote vale para compra nova")


def e_webhook(_: Path) -> None:
    """N3-E3: o webhook só credita pagamento conferido na API, uma vez só."""
    from nuvem import app
    from provas.nuvem_falsa import MercadoPagoFalso

    sb, mp = _loja(), MercadoPagoFalso()
    ana = sb.usuarios["ana@exemplo.com"]["id"]

    def abrir() -> str:
        st, r = app.iniciar_pagamento(amb, sb.token_de("ana@exemplo.com"), {"pacote": "p60"})
        assert st == 200, r
        return list(mp.preferencias)[-1]

    with sb.servir() as url_sb, mp.servir() as url_mp:
        amb = _amb(url_sb, url_mp)
        from provas.prova_n2 import _servidor_do_app  # noqa: PLC0415 - o mesmo do N2-F2

        with _servidor_do_app(amb) as url_app:
            amb["APP_URL"] = url_app

            pref = abrir()
            pid = mp.pagar(pref)
            st, r = mp.avisar(pref, pid)
            confere(st == 200 and r == {"resultado": "creditada"} and sb.saldo[ana] == 360,
                    "pagamento aprovado e assinado: credita 60 min (300 → 360)", f"{st} {r}")
            st, r = mp.avisar(pref, pid)
            confere(st == 200 and r == {"resultado": "ja_processada"} and sb.saldo[ana] == 360,
                    "o mesmo aviso de novo não credita outra vez")

            pref = abrir()
            pid = mp.pagar(pref)
            st, _ = mp.avisar(pref, pid, adulterar=True)
            st2, _ = mp.avisar(pref, pid, segredo="segredo-de-outro")
            confere(st == 401 and st2 == 401 and sb.saldo[ana] == 360,
                    "assinatura adulterada ou de outro segredo: 401, nada creditado")

            pid = mp.pagar(pref, valor=10.0)
            st, r = mp.avisar(pref, pid)
            confere(st == 200 and "recusado" in r and sb.saldo[ana] == 360,
                    "valor pago menor que o preço: não credita (e não fica tentando)", str(r))

            pref = abrir()
            pid = mp.pagar(pref, status="pending")
            st, r = mp.avisar(pref, pid)
            confere(r == {"aguardando": "pending"} and sb.saldo[ana] == 360,
                    "Pix ainda não pago: espera, sem crédito")
            pid = mp.pagar(pref, status="rejected")
            st, r = mp.avisar(pref, pid)
            confere(r == {"resultado": "recusada"} and sb.saldo[ana] == 360, "pagamento recusado: sem crédito")

            pref = abrir()
            pid = mp.pagar(pref, moeda="USD")
            st, r = mp.avisar(pref, pid)
            confere(sb.saldo[ana] == 360 and r == {"resultado": "recusada"}, "moeda diferente de BRL não credita")

            pref = abrir()
            pid = mp.pagar(pref, referencia="pedido-de-outra-loja")
            st, r = mp.avisar(pref, pid)
            confere(st == 200 and "ignorado" in r, "pagamento de fora do ClipPro é ignorado")

            mp.fora_do_ar = True
            pid = mp.pagar(pref)
            st, _ = mp.avisar(pref, pid)
            confere(st == 502 and sb.saldo[ana] == 360,
                    "Mercado Pago fora do ar: 502 (ele tenta de novo depois), nada creditado")
            mp.fora_do_ar = False
            st, r = mp.avisar(pref, pid)
            confere(r == {"resultado": "creditada"} and sb.saldo[ana] == 420,
                    "na nova tentativa, credita")

            st, r = app.receber_webhook(amb, {"type": "merchant_order", "data.id": "1"}, {}, {})
            confere(st == 200 and "ignorado" in r, "aviso que não é de pagamento é ignorado")
            st, r = app.receber_webhook({**amb, "COMPRAS_ATIVAS": ""},
                                        {"type": "payment", "data.id": pid}, {}, {})
            confere(st == 200 and "ignorado" in r, "com as vendas desligadas, o webhook não faz nada")


def e_rotas_compra(_: Path) -> None:
    """N3-E4: /api/comprar e /api/mp_webhook pelo HTTP de verdade (cola da Vercel)."""
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from threading import Thread

    from api import comprar, mp_webhook
    from provas.nuvem_falsa import MercadoPagoFalso

    sb, mp = _loja(), MercadoPagoFalso()
    with sb.servir() as url_sb, mp.servir() as url_mp:
        antes = dict(os.environ)
        os.environ.update(_amb(url_sb, url_mp))
        try:
            servidores = {}
            for nome, mod in (("comprar", comprar), ("webhook", mp_webhook)):
                quieto = type("Quieto", (mod.handler,), {"log_message": lambda *_: None})
                srv = ThreadingHTTPServer(("127.0.0.1", 0), quieto)
                Thread(target=srv.serve_forever, daemon=True).start()
                servidores[nome] = srv
            base_c = f"http://127.0.0.1:{servidores['comprar'].server_address[1]}"
            req = urllib.request.Request(base_c + "/api/comprar", method="POST",
                                         data=json.dumps({"pacote": "p60"}).encode(),
                                         headers={"Authorization": f"Bearer {sb.token_de('ana@exemplo.com')}",
                                                  "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                corpo = json.loads(r.read())
            confere("url" in corpo, "POST /api/comprar responde com o link")
            pref = list(mp.preferencias)[-1]
            mp.preferencias[pref]["notification_url"] = (
                f"http://127.0.0.1:{servidores['webhook'].server_address[1]}/api/mp_webhook")
            st, r = mp.avisar(pref, mp.pagar(pref))
            confere(st == 200 and r == {"resultado": "creditada"},
                    "POST /api/mp_webhook lê query, cabeçalhos e corpo e credita", f"{st} {r}")
            for srv in servidores.values():
                srv.shutdown()
                srv.server_close()
        finally:
            os.environ.clear()
            os.environ.update(antes)


ESTRUTURAIS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "N3-E1": ("assinatura do webhook (manifest oficial)", e_assinatura_mp),
    "N3-E2": ("abrir compra: preferência com preço congelado", e_comprar),
    "N3-E3": ("webhook: só credita pagamento conferido, uma vez", e_webhook),
    "N3-E4": ("rotas de compra pelo HTTP de verdade", e_rotas_compra),
}


# ==========================================================================


def main(argv: list[str]) -> int:
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
    raiz = RAIZ / "_teste" / "out-prova-n3"

    titulo = "PROVAS DA N-3 — compra de créditos"
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
