"""Provas da fase N-2 -- o app na nuvem (RULINGS §29.3). Espelha prova_n1.py.

    python provas/prova_n2.py                # estruturais
    python provas/prova_n2.py --fisicas      # + fisicas
    python provas/prova_n2.py N2-E1 N2-F1    # casos escolhidos

Fisicas e o que cada uma precisa:
  N2-F1  banco das contas  -> CLIPPRO_PROVA_PG (Postgres de TESTE) + psql
  N2-F2  interface         -> node + playwright (Chromium), backend falso local

Nada aqui fala com o Supabase, o R2 ou a Anthropic de verdade.

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterator

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

# O esquema auth do Supabase, no minimo que as migracoes usam: a tabela de
# usuarios (com a confirmacao de e-mail) e auth.uid().
_AUTH_IMITADO = """
create schema if not exists auth;
create table if not exists auth.users (
    id uuid primary key, email text, email_confirmed_at timestamptz);
create or replace function auth.uid() returns uuid language sql stable as
    $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to anon, authenticated, service_role;
grant execute on function auth.uid() to anon, authenticated, service_role;
drop table if exists public.movimentos, public.perfis, public.convites cascade;
drop trigger if exists clippro_ao_criar_usuario on auth.users;
drop trigger if exists clippro_ao_confirmar_usuario on auth.users;
delete from auth.users;
"""

ANA = "a0000000-0000-4000-8000-00000000000a"
BIA = "b0000000-0000-4000-8000-00000000000b"
CAIO = "c0000000-0000-4000-8000-00000000000c"
LINK = """'{"tipo": "link", "valor": "https://www.youtube.com/watch?v=abc"}'::jsonb"""


def _psql_ou_pula() -> tuple[str, str]:
    url, psql = os.environ.get("CLIPPRO_PROVA_PG"), shutil.which("psql")
    if not url or not psql:
        raise Pulou("pendente: defina CLIPPRO_PROVA_PG com a URL de um Postgres de TESTE "
                    "(a prova apaga e recria as tabelas) e tenha o psql no PATH.")
    return url, psql


class _Banco:
    def __init__(self, url: str, psql: str) -> None:
        self.url, self.psql = url, psql
        self.env = {**os.environ, "PGOPTIONS": "-c client_min_messages=warning"}

    def args(self, *comandos: str, como: str | None = None,
             arquivo: Path | None = None) -> list[str]:
        a = [self.psql, self.url, "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1"]
        if como == "anon":
            a += ["-c", "set role anon"]
        elif como == "worker":
            a += ["-c", "set role service_role"]
        elif como:
            a += ["-c", f"set request.jwt.claim.sub = '{como}'", "-c", "set role authenticated"]
        if arquivo:
            a += ["-f", str(arquivo)]
        for c in comandos:
            a += ["-c", c]
        return a

    def __call__(self, *comandos: str, como: str | None = None,
                 arquivo: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(self.args(*comandos, como=como, arquivo=arquivo),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120, env=self.env)

    def valor(self, comando: str, como: str | None = None) -> str:
        p = self(comando, como=como)
        if p.returncode:
            raise Falhou(f"SQL falhou: {comando[:60]} -> {_erro(p)}")
        return p.stdout.strip()


def _erro(p: subprocess.CompletedProcess) -> str:
    """A linha ERROR do psql (o resto e contexto tecnico)."""
    linhas = [l for l in (p.stderr or "").splitlines() if "ERROR" in l]
    return (linhas[0].split("ERROR:", 1)[-1].strip() if linhas else "")[:90]


def _saldo(db: _Banco, conta: str) -> int:
    return int(db.valor("select meu_saldo()", como=conta))


# ==========================================================================
# Fisicas
# ==========================================================================


def f_banco_das_contas(raiz: Path) -> None:
    """N2-F1: convites, créditos, RLS e corrida de pedidos num Postgres real."""
    db = _Banco(*_psql_ou_pula())
    pasta = RAIZ / "nuvem" / "supabase"

    p = db(_SUPABASE_IMITADO + _AUTH_IMITADO)
    confere(p.returncode == 0, "o banco de teste imita o Supabase (papéis + auth)",
            p.stderr[-120:] if p.returncode else "")
    for rodada in (1, 2):
        p1 = db(arquivo=pasta / "001_fila.sql")
        p2 = db(arquivo=pasta / "002_contas.sql")
        confere(p1.returncode == 0 and p2.returncode == 0,
                f"001 + 002 rodam em ordem (rodada {rodada}: idempotentes)",
                (p1.stderr or p2.stderr)[-140:] if (p1.returncode or p2.returncode) else "")

    # Convite + e-mail confirmado = liberado com 300.
    db.valor("insert into convites (email) values ('ana@exemplo.com'), ('caio@exemplo.com')")
    db.valor(f"insert into auth.users values ('{ANA}', 'Ana@Exemplo.com', now())")
    confere(_saldo(db, ANA) == 300, "convidada com e-mail confirmado ganha 300 créditos")

    db.valor(f"insert into auth.users values ('{BIA}', 'bia@exemplo.com', now())")
    p = db(f"select criar_trabalho({LINK}, 3, 'cortes')", como=BIA)
    confere(_saldo(db, BIA) == 0 and p.returncode != 0 and "só para convidados" in p.stderr,
            "sem convite: saldo 0 e o pedido é recusado com a mensagem do beta",
            _erro(p))

    db.valor(f"insert into auth.users values ('{CAIO}', 'caio@exemplo.com', null)")
    confere(_saldo(db, CAIO) == 0,
            "convidado que NÃO confirmou o e-mail ainda não ganha nada")
    db.valor(f"update auth.users set email_confirmed_at = now() where id = '{CAIO}'")
    db.valor(f"update auth.users set email_confirmed_at = now() where id = '{CAIO}'")
    confere(_saldo(db, CAIO) == 300, "ao confirmar, ganha 300 — uma vez só, mesmo confirmando 2x")

    db.valor("insert into convites (email) values ('bia@exemplo.com')")
    confere(_saldo(db, BIA) == 300, "convite que chega depois do cadastro libera quem já confirmou")

    # Pedido: reserva o saldo (até 600) e devolve o que sobrou no fim.
    id1 = db.valor(f"select criar_trabalho({LINK}, 3, 'cortes')", como=ANA)
    confere(bool(id1) and _saldo(db, ANA) == 0, "pedir clipes reserva o saldo inteiro (300 < 600)")
    p = db(f"select criar_trabalho({LINK}, 3, 'cortes')", como=ANA)
    confere(p.returncode != 0 and "créditos acabaram" in p.stderr,
            "sem saldo livre, o 2º pedido é recusado", _erro(p))
    reservado = db.valor("select id from reservar_trabalho('w1', 600)", como="worker")
    ok = db.valor(f"""select encerrar_trabalho('{id1}', 'w1', 1, 'concluido',
                      '{{"status": "concluido", "creditos": 2}}'::jsonb)""", como="worker")
    confere(reservado == id1 and ok == "t" and _saldo(db, ANA) == 298,
            "o worker conclui com 2 créditos e a conta fica com 298", f"saldo {_saldo(db, ANA)}")

    id2 = db.valor(f"select criar_trabalho({LINK}, 3, 'cortes')", como=ANA)
    db.valor("select id from reservar_trabalho('w1', 600)", como="worker")
    db.valor(f"""select encerrar_trabalho('{id2}', 'w1', 1, 'falhou',
                 '{{"status": "falhou", "creditos": 0}}'::jsonb)""", como="worker")
    confere(_saldo(db, ANA) == 298, "falha devolve a reserva inteira")
    db.valor(f"update trabalhos set status = 'pendente' where id = '{id2}'")
    db.valor(f"update trabalhos set status = 'falhou' where id = '{id2}'")
    confere(_saldo(db, ANA) == 298, "a devolução não se repete se o status oscilar")

    id3 = db.valor(f"select criar_trabalho({LINK}, 3, 'cortes')", como=ANA)
    db.valor("select id from reservar_trabalho('w1', 600)", como="worker")
    db.valor(f"""select encerrar_trabalho('{id3}', 'w1', 1, 'concluido',
                 '{{"status": "concluido", "creditos": "dois"}}'::jsonb)""", como="worker")
    confere(_saldo(db, ANA) == 298, "crédito torto no resultado cobra zero (a favor do usuário)")

    # RLS e colunas internas.
    meus = db.valor("select count(*) from trabalhos", como=ANA)
    alheios = db.valor("select count(*) from trabalhos", como=BIA)
    confere(meus == "3" and alheios == "0", "cada conta só vê os próprios trabalhos",
            f"ana {meus}, bia {alheios}")
    p = db("select worker from trabalhos", como=ANA)
    confere(p.returncode != 0 and "permission denied" in p.stderr,
            "colunas internas da fila (worker) não são legíveis pelo usuário")
    p = db(f"insert into movimentos (conta, delta, motivo) values ('{ANA}', 999, 'ajuste')",
           como=ANA)
    confere(p.returncode != 0, "o usuário não consegue se dar créditos")
    p = db(f"select criar_trabalho({LINK}, 3, 'cortes')", como="anon")
    confere(p.returncode != 0 and "permission denied" in p.stderr,
            "sem login (anon) não se pede clipe")
    p = db(f"select criar_trabalho({LINK}, 0, 'cortes')", como=BIA)
    confere(p.returncode != 0 and "1 a 20" in p.stderr, "n fora de 1–20 é recusado com mensagem")

    # Limite de 3 na fila.
    db.valor(f"insert into movimentos (conta, delta, motivo) values ('{ANA}', 2000, 'ajuste')")
    for _ in range(3):
        db.valor(f"select criar_trabalho({LINK}, 3, 'cortes')", como=ANA)
    p = db(f"select criar_trabalho({LINK}, 3, 'cortes')", como=ANA)
    confere(p.returncode != 0 and "3 vídeos na fila" in p.stderr,
            "no máximo 3 vídeos na fila por conta", _erro(p))

    # Corrida: dois pedidos da mesma conta ao mesmo tempo não gastam o mesmo saldo.
    db.valor("delete from trabalhos")
    db.valor(f"delete from movimentos where conta = '{CAIO}'")
    db.valor(f"insert into movimentos (conta, delta, motivo) values ('{CAIO}', 10, 'ajuste')")
    segura = subprocess.Popen(
        db.args("begin", f"select criar_trabalho({LINK}, 3, 'cortes')", "select pg_sleep(2)",
                "commit", como=CAIO),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=db.env)
    time.sleep(0.5)
    p = db(f"select criar_trabalho({LINK}, 3, 'cortes')", como=CAIO)
    segura.communicate(timeout=30)
    confere(p.returncode != 0 and "créditos acabaram" in p.stderr and _saldo(db, CAIO) == 0,
            "dois pedidos simultâneos: um reserva, o outro espera e é recusado; saldo nunca "
            "fica negativo", f"saldo {_saldo(db, CAIO)}")


def _node_com_playwright() -> tuple[str, dict[str, str]]:
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        raise Pulou("pendente: a prova de interface precisa de Node + Playwright (Chromium).")
    raiz_global = subprocess.run([npm, "root", "-g"], capture_output=True, text=True).stdout.strip()
    env = {**os.environ, "NODE_PATH": raiz_global}
    teste = subprocess.run([node, "-e", "require('playwright')"], env=env, capture_output=True)
    if teste.returncode:
        raise Pulou("pendente: o pacote playwright do Node não está instalado neste ambiente.")
    return node, env


@contextlib.contextmanager
def _servidor_do_app(amb: dict[str, str]) -> Iterator[str]:
    """Serve app/ e as rotas /api/* como a Vercel: estatico + funcoes."""
    import mimetypes
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from urllib.parse import parse_qs, urlsplit

    from nuvem import app
    from nuvem.web import ler_json, responder, token_de

    pasta = (RAIZ / "app").resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            partes = urlsplit(self.path)
            if partes.path == "/api/config":
                return responder(self, *app.configuracao_publica(amb))
            if partes.path == "/api/clipes":
                trabalho = (parse_qs(partes.query).get("trabalho") or [""])[0]
                return responder(self, *app.links_dos_clipes(amb, token_de(self), trabalho))
            alvo = (pasta / (partes.path.lstrip("/") or "index.html")).resolve()
            if pasta not in alvo.parents or not alvo.is_file():
                self.send_response(404)
                self.end_headers()
                return
            corpo = alvo.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(alvo.name)[0] or "text/plain")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def do_POST(self) -> None:  # noqa: N802
            partes = urlsplit(self.path)
            if partes.path == "/api/upload":
                return responder(self, *app.pedir_upload(amb, token_de(self), ler_json(self)))
            if partes.path == "/api/comprar":
                return responder(self, *app.iniciar_pagamento(amb, token_de(self), ler_json(self)))
            if partes.path == "/api/mp_webhook":
                from urllib.parse import parse_qsl

                cab = {k.lower(): v for k, v in self.headers.items()}
                return responder(self, *app.receber_webhook(
                    amb, dict(parse_qsl(partes.query)), cab, ler_json(self)))
            self.send_response(404)
            self.end_headers()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def f_interface(raiz: Path) -> None:
    """N2-F2: o app num Chromium de verdade, ponta a ponta, contra a nuvem falsa."""
    from provas.nuvem_falsa import SupabaseFalso, s3_falso

    node, env_node = _node_com_playwright()
    saida = _pasta(raiz, "n2-f2")
    sb = SupabaseFalso()
    sb.cadastrar("ana@exemplo.com", "senha-da-ana")
    sb.cadastrar("bia@exemplo.com", "senha-da-bia", liberado=False)

    with sb.servir() as url_sb, s3_falso(SEGREDO_R2) as (url_s3, objetos, _):
        def ao_concluir(id_: str) -> dict[str, Any]:
            pasta = f"resultados/{id_}/"
            agora = time.time()
            objetos[f"/clippro/{pasta}01-o-momento--cortes.mp4"] = (b"\x00" * 2048, agora)
            objetos[f"/clippro/{pasta}01-o-momento--cortes.capa.jpg"] = (b"\xff\xd8\xff", agora)
            objetos[f"/clippro/{pasta}01-o-momento--cortes.publicacao.md"] = (
                "Texto do post #clippro".encode(), agora)
            objetos[f"/clippro/{pasta}02-x--cortes.mp4"] = (b"\x00" * 1024, agora)
            return {"status": "concluido", "creditos": 2, "clipes": [
                {"titulo": "O momento em que tudo mudou", "score": 8.7, "duracao": 42.0,
                 "gancho": "Ninguém esperava essa resposta",
                 "arquivos": {"video": pasta + "01-o-momento--cortes.mp4",
                              "capa": pasta + "01-o-momento--cortes.capa.jpg",
                              "publicacao": pasta + "01-o-momento--cortes.publicacao.md"}},
                {"titulo": "<img src=x onerror=alert(1)>", "score": 7.1, "duracao": 30.0,
                 "gancho": "x", "arquivos": {"video": pasta + "02-x--cortes.mp4"}},
            ]}

        sb.ao_concluir = ao_concluir
        with _servidor_do_app(_ambiente(url_sb, url_s3)) as url_app:
            proc = subprocess.run(
                [node, str(RAIZ / "provas" / "n2_interface.cjs")],
                env={**env_node, "APP_URL": url_app, "SB_URL": url_sb, "SAIDA": str(saida)},
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)

    checks = [json.loads(l[6:]) for l in proc.stdout.splitlines() if l.startswith("CHECK ")]
    if not checks:
        raise Falhou(f"o script de interface não relatou nada: {(proc.stderr or proc.stdout)[-300:]}")
    for c in checks:
        confere(c["ok"], c["descricao"], c["detalhe"] if not c["ok"] else "")

    pedidos = [p for p in sb.pedidos if p["caminho"] == "/rest/v1/rpc/criar_trabalho"]
    primeiro = pedidos[0]["corpo"] if pedidos else {}
    confere(primeiro.get("p_preset") == "cortes-editorial" and primeiro.get("p_n") == 3,
            "o pedido levou o visual e o número de cortes escolhidos na tela",
            f"{primeiro.get('p_preset')}, {primeiro.get('p_n')}")
    enviados = [k for k in objetos if k.startswith("/clippro/entradas/")]
    por_arquivo = [t for t in sb.trabalhos if t["pedido"]["entrada"]["tipo"] == "arquivo"]
    confere(len(enviados) == 1 and len(objetos[enviados[0]][0]) == 50000 and por_arquivo
            and enviados[0].endswith(por_arquivo[0]["pedido"]["entrada"]["valor"]),
            "o arquivo chegou ao R2 inteiro e o pedido aponta para ele")
    confere(all(p["apikey"] == SupabaseFalso.CHAVE_PUBLICA for p in sb.pedidos
                if not p["caminho"].startswith("/__prova")),
            "o navegador só usou a chave pública do Supabase")
    print(f"    prints  {saida}")


FISICAS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "N2-F1": ("banco das contas num Postgres real", f_banco_das_contas),
    "N2-F2": ("interface num Chromium real (Playwright)", f_interface),
}


# ==========================================================================
# Estruturais: funcoes do app contra Supabase e S3 falsos (provas/nuvem_falsa.py)
# ==========================================================================

SEGREDO_R2 = "segredo-r2-da-prova"


def _ambiente(supabase_url: str, s3_url: str, **mexe: str) -> dict[str, str]:
    from provas.nuvem_falsa import SupabaseFalso

    amb = {
        "SUPABASE_URL": supabase_url, "SUPABASE_PUBLISHABLE_KEY": SupabaseFalso.CHAVE_PUBLICA,
        "SUPABASE_SECRET_KEY": "sb_secret_NAO_PODE_VAZAR",
        "R2_ACCOUNT_ID": "conta", "R2_ACCESS_KEY_ID": "AKIDPROVA",
        "R2_SECRET_ACCESS_KEY": SEGREDO_R2, "R2_BUCKET": "clippro", "R2_ENDPOINT": s3_url,
    }
    amb.update(mexe)
    return amb


def _put(url: str, corpo: bytes) -> int:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=corpo, method="PUT"),
                                    timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _get(url: str) -> tuple[int, bytes, dict[str, str]]:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, b"", {}


def e_url_assinada(_: Path) -> None:
    """N2-E1: URL pré-assinada bate com a AWS e não codifica duas vezes."""
    from datetime import datetime, timezone
    from urllib.parse import parse_qsl, quote, urlsplit

    from nuvem.s3 import presignar_s3

    k = dict(chave_id="AKIAIOSFODNN7EXAMPLE", segredo="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
             regiao="us-east-1", quando=datetime(2013, 5, 24, tzinfo=timezone.utc))
    url = presignar_s3("GET", "https://examplebucket.s3.amazonaws.com/test.txt",
                       expira_s=86400, **k)
    confere(url.endswith("X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"),
            "a URL pré-assinada bate com o exemplo oficial da AWS")
    disp = 'attachment; filename="01-clipe--cortes.mp4"'
    url = presignar_s3("GET", "https://b.exemplo/x.mp4?response-content-disposition="
                       + quote(disp, safe=""), expira_s=60, **k)
    volta = dict(parse_qsl(urlsplit(url).query)).get("response-content-disposition")
    confere(volta == disp, "o nome do arquivo no download chega íntegro (sem %253B)", str(volta))


def e_config_publica(_: Path) -> None:
    """N2-E2: /api/config entrega só valores públicos; sem eles, 503 claro."""
    from nuvem import app

    status, dados = app.configuracao_publica({})
    confere(status == 503 and "configurado" in dados["erro"], "sem ambiente: 503 com mensagem")
    status, dados = app.configuracao_publica(_ambiente("https://p.supabase.co/", "http://s3"))
    texto = json.dumps(dados)
    confere(status == 200 and dados["supabase_url"] == "https://p.supabase.co"
            and "NAO_PODE_VAZAR" not in texto and SEGREDO_R2 not in texto,
            "entrega URL e chave pública — nunca a secreta nem o segredo do R2")


def e_upload(_: Path) -> None:
    """N2-E3: o envio exige login, limita tamanho e tipo, e o R2 confere o tamanho."""
    from nuvem import app
    from provas.nuvem_falsa import SupabaseFalso, s3_falso

    sb = SupabaseFalso()
    ana = sb.cadastrar("ana@exemplo.com", "senha-ana")
    with sb.servir() as url_sb, s3_falso(SEGREDO_R2) as (url_s3, objetos, _):
        amb = _ambiente(url_sb, url_s3)
        token = sb.token_de("ana@exemplo.com")
        pedido = {"nome": "Live de Sexta.MP4", "tamanho": 4096, "tipo": "video/mp4"}

        confere(app.pedir_upload(amb, None, pedido)[0] == 401, "sem login: 401")
        confere(app.pedir_upload(amb, "token-falso", pedido)[0] == 401, "token inválido: 401")
        casos = {
            "maior que 2 GB": {**pedido, "tamanho": 2 * 1024**3 + 1},
            "tamanho como texto": {**pedido, "tamanho": "4096"},
            "não é vídeo (.exe)": {**pedido, "nome": "virus.exe"},
            "tipo declarado não é vídeo": {**pedido, "tipo": "image/png"},
        }
        aceitos = [r for r, c in casos.items() if app.pedir_upload(amb, token, c)[0] != 400]
        confere(not aceitos, "tamanho, tipo e extensão inválidos dão 400", ", ".join(aceitos))
        st, sem_tipo = app.pedir_upload(amb, token, {**pedido, "nome": "a.mkv", "tipo": ""})
        confere(st == 200, "tipo vazio com extensão de vídeo passa (navegador que não sabe o .mkv)")

        status, r = app.pedir_upload(amb, token, pedido)
        confere(status == 200 and r["chave"].startswith(ana["id"] + "-")
                and r["chave"].endswith(".mp4") and "X-Amz-SignedHeaders=content-length%3Bhost" in r["url"],
                "devolve a URL assinada com o tamanho dentro da assinatura", r.get("chave", ""))
        confere(_put(r["url"], b"\x00" * 4096) == 200
                and objetos.get(f"/clippro/entradas/{r['chave']}", (b"",))[0] == b"\x00" * 4096,
                "o navegador consegue enviar exatamente o tamanho declarado")
        confere(_put(r["url"], b"\x00" * 9000) == 403,
                "arquivo maior que o declarado é recusado pelo próprio R2")


def e_clipes(_: Path) -> None:
    """N2-E4: os clipes só saem para o dono, com URL de ver e de baixar."""
    from nuvem import app
    from provas.nuvem_falsa import SupabaseFalso, s3_falso

    sb = SupabaseFalso()
    sb.cadastrar("ana@exemplo.com", "a")
    sb.cadastrar("bia@exemplo.com", "b")
    ana = sb.usuarios["ana@exemplo.com"]
    with sb.servir() as url_sb, s3_falso(SEGREDO_R2) as (url_s3, objetos, _):
        amb = _ambiente(url_sb, url_s3)
        tok_ana, tok_bia = sb.token_de("ana@exemplo.com"), sb.token_de("bia@exemplo.com")
        st, id_ = sb.criar_trabalho(ana, {"p_entrada": {"tipo": "link", "valor": "https://y/x"},
                                          "p_n": 1, "p_preset": "cortes"})
        status, r = app.links_dos_clipes(amb, tok_ana, id_)
        confere(status == 200 and r["status"] == "pendente" and r["clipes"] == [],
                "trabalho ainda na fila: sem clipes, com o status")

        pasta = f"resultados/{id_}/"
        objetos[f"/clippro/{pasta}01-clipe--cortes.mp4"] = (b"mp4" * 100, time.time())
        objetos[f"/clippro/{pasta}01-clipe--cortes.capa.jpg"] = (b"jpg", time.time())
        sb.concluir(id_, {"status": "concluido", "creditos": 2, "clipes": [
            {"titulo": "Clipe 1", "score": 8.5, "gancho": "um gancho", "duracao": 31.2,
             "arquivos": {"video": pasta + "01-clipe--cortes.mp4",
                          "capa": pasta + "01-clipe--cortes.capa.jpg"}},
            {"titulo": "Adulterado", "arquivos": {"video": "resultados/outro/x.mp4"}},
        ]})
        confere(sb.saldo[ana["id"]] == 298, "a conclusão devolve o que sobrou da reserva (300 → 298)")

        confere(app.links_dos_clipes(amb, tok_bia, id_)[0] == 404,
                "outra conta recebe 404 (o banco nem devolve o trabalho)")
        confere(app.links_dos_clipes(amb, None, id_)[0] == 401, "sem login: 401")
        confere(app.links_dos_clipes(amb, tok_ana, "../../etc")[0] == 400, "id torto: 400")

        status, r = app.links_dos_clipes(amb, tok_ana, id_)
        confere(status == 200 and [c["titulo"] for c in r["clipes"]] == ["Clipe 1"],
                "o clipe com chave fora de resultados/<id>/ é ignorado")
        c = r["clipes"][0]
        st, corpo, _ = _get(c["ver"])
        confere(st == 200 and corpo == b"mp4" * 100, "a URL de ver abre o MP4")
        st, _, cab = _get(c["baixar"])
        confere(st == 200 and cab.get("Content-Disposition") ==
                'attachment; filename="01-clipe--cortes.mp4"',
                "a URL de baixar devolve o arquivo com o nome certo", cab.get("Content-Disposition", ""))
        confere(c["capa"] and _get(c["capa"])[0] == 200 and c["publicacao"] is None,
                "capa assinada; sem publicação no resultado, sem URL")
        adulterada = c["ver"].replace("01-clipe", "02-clipe")
        confere(_get(adulterada)[0] == 403, "URL adulterada é recusada pelo R2")


def e_rotas_http(_: Path) -> None:
    """N2-E5: as rotas da Vercel respondem JSON sem cache, pelo HTTP de verdade."""
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from threading import Thread

    from api import clipes, config, upload
    from provas.nuvem_falsa import SupabaseFalso, s3_falso

    sb = SupabaseFalso()
    sb.cadastrar("ana@exemplo.com", "a")
    with sb.servir() as url_sb, s3_falso(SEGREDO_R2) as (url_s3, _o, _p):
        antes = dict(os.environ)
        os.environ.update(_ambiente(url_sb, url_s3))
        try:
            respostas = {}
            for nome, mod, metodo, corpo, caminho in (
                ("config", config, "GET", None, "/api/config"),
                ("upload", upload, "POST", {"nome": "a.mp4", "tamanho": 10, "tipo": "video/mp4"},
                 "/api/upload"),
                ("clipes", clipes, "GET", None, "/api/clipes?trabalho=nao-e-uuid"),
            ):
                quieto = type("Quieto", (mod.handler,), {"log_message": lambda *_: None})
                srv = ThreadingHTTPServer(("127.0.0.1", 0), quieto)
                Thread(target=srv.serve_forever, daemon=True).start()
                req = urllib.request.Request(
                    f"http://127.0.0.1:{srv.server_address[1]}{caminho}", method=metodo,
                    data=None if corpo is None else json.dumps(corpo).encode(),
                    headers={"Authorization": f"Bearer {sb.token_de('ana@exemplo.com')}",
                             "Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req, timeout=30) as r:
                        respostas[nome] = (r.status, json.loads(r.read()), r.headers)
                except urllib.error.HTTPError as exc:
                    respostas[nome] = (exc.code, json.loads(exc.read()), exc.headers)
                srv.shutdown()
                srv.server_close()
        finally:
            os.environ.clear()
            os.environ.update(antes)
    confere(respostas["config"][0] == 200 and "supabase_chave" in respostas["config"][1],
            "GET /api/config responde")
    confere(respostas["upload"][0] == 200 and "url" in respostas["upload"][1],
            "POST /api/upload responde com a URL")
    confere(respostas["clipes"][0] == 400, "GET /api/clipes com id torto: 400")
    confere(all(r[2].get("Cache-Control") == "no-store" for r in respostas.values()),
            "nenhuma resposta fica em cache (URL assinada não pode vazar por cache)")


ESTRUTURAIS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "N2-E1": ("URL pré-assinada", e_url_assinada),
    "N2-E2": ("/api/config só com valores públicos", e_config_publica),
    "N2-E3": ("/api/upload: login, limites e tamanho assinado", e_upload),
    "N2-E4": ("/api/clipes: só para o dono", e_clipes),
    "N2-E5": ("rotas pelo HTTP de verdade", e_rotas_http),
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
    raiz = RAIZ / "_teste" / "out-prova-n2"

    titulo = "PROVAS DA N-2 — app na nuvem"
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
