"""Nuvem falsa para as provas: S3 (R2) e Supabase locais, em memoria.

Nada sai da maquina. As duas existem para morder no que importa:
- o S3 RECALCULA a assinatura de cada pedido (cabecalho ou URL pre-assinada,
  com prazo) e recusa a errada -- confere o que viajou, nao so o algoritmo;
- o Supabase imita Auth + PostgREST no minimo que o app usa, com as MESMAS
  regras do SQL (convite, saldo, 3 na fila, cada conta ve o que e seu).
  A fidelidade do SQL em si e provada num Postgres real (N2-F1).

Os dois respondem CORS como os servicos de verdade, para o navegador da
prova de interface (N2-F2) conseguir falar com eles.

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit


def _cors(h: BaseHTTPRequestHandler) -> None:
    h.send_header("Access-Control-Allow-Origin", h.headers.get("Origin") or "*")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS")
    h.send_header("Access-Control-Allow-Headers",
                  h.headers.get("Access-Control-Request-Headers") or "*")
    h.send_header("Access-Control-Expose-Headers", "ETag, Content-Range")
    h.send_header("Access-Control-Max-Age", "600")


@contextlib.contextmanager
def _servir(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{servidor.server_address[1]}"
    finally:
        servidor.shutdown()
        servidor.server_close()


# ==========================================================================
# S3 (R2)
# ==========================================================================

_RE_AUTH = re.compile(
    r"AWS4-HMAC-SHA256 Credential=([^/]+)/(\d{8})/([^/]+)/s3/aws4_request, "
    r"SignedHeaders=([^,]+), Signature=([0-9a-f]{64})$")


@contextlib.contextmanager
def s3_falso(segredo: str) -> Iterator[tuple[str, dict[str, Any], list[tuple[str, str, int]]]]:
    """(url, objetos, pedidos). objetos[caminho] = (bytes, mtime)."""
    from nuvem.s3 import assinar_s3, presignar_s3

    objetos: dict[str, Any] = {}
    pedidos: list[tuple[str, str, int]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            pass

        def _caminho(self) -> str:
            return urlsplit(self.path).path

        def _valido_cabecalho(self, corpo: bytes) -> bool:
            auth = self.headers.get("Authorization", "")
            m = _RE_AUTH.match(auth)
            if not m:
                return False
            chave_id, _, regiao, assinados, _ = m.groups()
            carga = self.headers.get("x-amz-content-sha256", "")
            if self.command == "PUT" and hashlib.sha256(corpo).hexdigest() != carga:
                return False
            extras = {n: self.headers.get(n, "") for n in assinados.split(";")
                      if n not in ("host", "x-amz-date", "x-amz-content-sha256")}
            quando = datetime.strptime(self.headers.get("x-amz-date", ""),
                                       "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            esperado = assinar_s3(self.command, f"http://{self.headers.get('Host')}{self.path}",
                                  extras, carga, chave_id=chave_id, segredo=segredo,
                                  regiao=regiao, quando=quando)
            return hmac.compare_digest(esperado["Authorization"], auth)

        def _valido_url(self) -> bool:
            partes = urlsplit(self.path)
            q = dict(parse_qsl(partes.query, keep_blank_values=True))
            if q.get("X-Amz-Algorithm") != "AWS4-HMAC-SHA256":
                return False
            try:
                quando = datetime.strptime(q["X-Amz-Date"], "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc)
                expira = int(q["X-Amz-Expires"])
                chave_id, _, regiao, _, _ = q["X-Amz-Credential"].split("/")
            except (KeyError, ValueError):
                return False
            if datetime.now(timezone.utc) > quando + timedelta(seconds=expira):
                return False
            assinados = q["X-Amz-SignedHeaders"].split(";")
            extras = {n: self.headers.get(n, "") for n in assinados if n != "host"}
            originais = [(k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True)
                         if not k.startswith("X-Amz-")]
            base = f"http://{self.headers.get('Host')}{partes.path}"
            if originais:
                base += "?" + urlencode(originais)
            esperado = presignar_s3(self.command, base, chave_id=chave_id, segredo=segredo,
                                    regiao=regiao, quando=quando, expira_s=expira,
                                    cabecalhos=extras)
            return hmac.compare_digest(esperado.rsplit("X-Amz-Signature=", 1)[-1],
                                       q.get("X-Amz-Signature", ""))

        def _valido(self, corpo: bytes) -> bool:
            if "X-Amz-Signature=" in self.path:
                return self._valido_url()
            return self._valido_cabecalho(corpo)

        def _fim(self, status: int, corpo: bytes = b"", cab: dict[str, str] | None = None,
                 tamanho: int | None = None) -> None:
            pedidos.append((self.command, self._caminho(), status))
            self.send_response(status)
            _cors(self)
            for k, v in (cab or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(corpo) if tamanho is None else tamanho))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._fim(204)

        def do_PUT(self) -> None:  # noqa: N802
            corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if not self._valido(corpo):
                return self._fim(403)
            objetos[self._caminho()] = (corpo, time.time())
            self._fim(200)

        def _ler(self) -> None:
            if not self._valido(b""):
                return self._fim(403)
            if self._caminho() not in objetos:
                return self._fim(404)
            corpo, mtime = objetos[self._caminho()]
            q = dict(parse_qsl(urlsplit(self.path).query))
            cab = {"Last-Modified": formatdate(mtime, usegmt=True)}
            if "response-content-disposition" in q:
                cab["Content-Disposition"] = q["response-content-disposition"]
            self._fim(200, b"" if self.command == "HEAD" else corpo, cab, len(corpo))

        do_GET = _ler  # noqa: N815
        do_HEAD = _ler  # noqa: N815

        def do_DELETE(self) -> None:  # noqa: N802
            if not self._valido(b""):
                return self._fim(403)
            objetos.pop(self._caminho(), None)
            self._fim(204)

    with _servir(Handler) as url:
        yield url, objetos, pedidos


# ==========================================================================
# Supabase (Auth + PostgREST), so o que o app usa
# ==========================================================================


def _b64(dados: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(dados).encode()).decode().rstrip("=")


class SupabaseFalso:
    """Estado em memoria + as regras do 002_contas.sql que o app enxerga."""

    CHAVE_PUBLICA = "sb_publishable_prova"

    def __init__(self) -> None:
        self.usuarios: dict[str, dict[str, Any]] = {}  # email -> usuario
        self.tokens: dict[str, str] = {}  # token -> id
        self.saldo: dict[str, int] = {}
        self.trabalhos: list[dict[str, Any]] = []
        self.pedidos: list[dict[str, Any]] = []
        self.trava = threading.Lock()
        # Gancho da prova de interface: recebe o id, semeia os arquivos e
        # devolve o resultado que o "worker" gravaria.
        self.ao_concluir: Any = None

    # ---------------------------------------------------- apoio das provas
    def cadastrar(self, email: str, senha: str, *, liberado: bool = True,
                  saldo: int = 300) -> dict[str, Any]:
        u = {"id": str(uuid.uuid4()), "email": email, "senha": senha,
             "confirmado": True, "liberado": liberado}
        self.usuarios[email] = u
        self.saldo[u["id"]] = saldo if liberado else 0
        return u

    def token_de(self, email: str) -> str:
        return self._sessao(self.usuarios[email])["access_token"]

    def concluir(self, trabalho_id: str, resultado: dict[str, Any]) -> None:
        with self.trava:
            t = next(t for t in self.trabalhos if t["id"] == trabalho_id)
            t["status"], t["resultado"] = "concluido", resultado
            usado = min(int(resultado.get("creditos") or 0), t["pedido"]["limite_minutos"])
            self.saldo[t["conta"]] += t["pedido"]["limite_minutos"] - usado

    # ---------------------------------------------------- regras
    def _sessao(self, u: dict[str, Any]) -> dict[str, Any]:
        agora = int(time.time())
        token = ".".join([_b64({"alg": "HS256", "typ": "JWT"}), _b64({
            "sub": u["id"], "email": u["email"], "role": "authenticated",
            "aud": "authenticated", "exp": agora + 3600, "iat": agora,
            "session_id": uuid.uuid4().hex}), uuid.uuid4().hex])
        self.tokens[token] = u["id"]
        return {"access_token": token, "token_type": "bearer", "expires_in": 3600,
                "expires_at": agora + 3600, "refresh_token": uuid.uuid4().hex,
                "user": self._publico(u)}

    @staticmethod
    def _publico(u: dict[str, Any]) -> dict[str, Any]:
        return {"id": u["id"], "aud": "authenticated", "role": "authenticated",
                "email": u["email"],
                "email_confirmed_at": "2026-10-15T00:00:00Z" if u["confirmado"] else None,
                "app_metadata": {"provider": "email", "providers": ["email"]},
                "user_metadata": {}, "identities": [], "created_at": "2026-10-15T00:00:00Z",
                "updated_at": "2026-10-15T00:00:00Z"}

    def _quem(self, h: BaseHTTPRequestHandler) -> dict[str, Any] | None:
        auth = h.headers.get("Authorization") or ""
        uid = self.tokens.get(auth[7:].strip()) if auth.lower().startswith("bearer ") else None
        return next((u for u in self.usuarios.values() if u["id"] == uid), None)

    def criar_trabalho(self, u: dict[str, Any], p: dict[str, Any]) -> tuple[int, Any]:
        def erro(msg: str) -> tuple[int, Any]:
            return 400, {"code": "P0001", "message": msg, "details": None, "hint": None}

        with self.trava:
            if not u["liberado"]:
                return erro("o beta do ClipPro é só para convidados.")
            entrada = p.get("p_entrada") or {}
            if entrada.get("tipo") not in ("link", "arquivo") or not entrada.get("valor"):
                return erro("informe o link ou envie o vídeo.")
            if not isinstance(p.get("p_n"), int) or not 1 <= p["p_n"] <= 20:
                return erro("escolha de 1 a 20 cortes.")
            na_fila = [t for t in self.trabalhos
                       if t["conta"] == u["id"] and t["status"] in ("pendente", "em_curso")]
            if len(na_fila) >= 3:
                return erro("você já tem 3 vídeos na fila; espere um terminar.")
            if self.saldo[u["id"]] < 1:
                return erro("seus créditos acabaram.")
            limite = min(self.saldo[u["id"]], 600)
            self.saldo[u["id"]] -= limite
            pedido = {"entrada": entrada, "n": p["p_n"], "preset": p.get("p_preset"),
                      "limite_minutos": limite}
            if (p.get("p_estrategia") or "").strip():
                pedido["estrategia"] = p["p_estrategia"]
            t = {"id": str(uuid.uuid4()), "conta": u["id"], "pedido": pedido,
                 "status": "pendente", "resultado": None,
                 "criado_em": datetime.now(timezone.utc).isoformat(),
                 "atualizado_em": datetime.now(timezone.utc).isoformat()}
            self.trabalhos.append(t)
            return 200, t["id"]

    # ---------------------------------------------------- HTTP
    @contextlib.contextmanager
    def servir(self) -> Iterator[str]:
        sb = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:
                pass

            def _json(self, status: int, dados: Any) -> None:
                corpo = b"" if status == 204 else json.dumps(dados, ensure_ascii=False).encode()
                self.send_response(status)
                _cors(self)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def _corpo(self) -> Any:
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n) or b"{}") if n else {}

            def do_OPTIONS(self) -> None:  # noqa: N802
                self._json(204, None)

            def do_GET(self) -> None:  # noqa: N802
                partes = urlsplit(self.path)
                sb.pedidos.append({"metodo": "GET", "caminho": partes.path,
                                   "apikey": self.headers.get("apikey")})
                u = sb._quem(self)
                if partes.path == "/auth/v1/user":
                    return self._json(200, sb._publico(u)) if u else self._json(
                        401, {"code": 401, "msg": "invalid JWT"})
                if partes.path.startswith("/rest/v1/"):
                    if u is None:
                        return self._json(200, [])  # RLS: anon nao ve nada
                    tabela = partes.path.rsplit("/", 1)[-1]
                    q = dict(parse_qsl(partes.query))
                    if tabela == "perfis":
                        return self._json(200, [{"conta": u["id"], "email": u["email"],
                                                 "liberado": u["liberado"]}])
                    if tabela == "trabalhos":
                        meus = [t for t in sb.trabalhos if t["conta"] == u["id"]]
                        if q.get("id", "").startswith("eq."):
                            meus = [t for t in meus if t["id"] == q["id"][3:]]
                        meus.sort(key=lambda t: t["criado_em"], reverse=True)
                        return self._json(200, meus)
                self._json(404, {"message": "rota falsa inexistente"})

            def do_POST(self) -> None:  # noqa: N802
                partes = urlsplit(self.path)
                corpo = self._corpo()
                sb.pedidos.append({"metodo": "POST", "caminho": partes.path, "corpo": corpo,
                                   "apikey": self.headers.get("apikey")})
                q = dict(parse_qsl(partes.query))
                if partes.path == "/auth/v1/token" and q.get("grant_type") == "password":
                    u = sb.usuarios.get(str(corpo.get("email", "")).lower())
                    if not u or u["senha"] != corpo.get("password"):
                        return self._json(400, {"error": "invalid_grant", "code": 400,
                                                "error_code": "invalid_credentials",
                                                "msg": "Invalid login credentials"})
                    if not u["confirmado"]:
                        return self._json(400, {"code": 400, "error_code": "email_not_confirmed",
                                                "msg": "Email not confirmed"})
                    return self._json(200, sb._sessao(u))
                if partes.path == "/auth/v1/token" and q.get("grant_type") == "refresh_token":
                    u = next(iter(sb.usuarios.values()), None)
                    return self._json(200, sb._sessao(u)) if u else self._json(400, {})
                if partes.path == "/auth/v1/signup":
                    email = str(corpo.get("email", "")).lower()
                    if email in sb.usuarios:
                        return self._json(422, {"code": 422, "error_code": "user_already_exists",
                                                "msg": "User already registered"})
                    u = sb.cadastrar(email, str(corpo.get("password")), liberado=False)
                    u["confirmado"] = False
                    return self._json(200, sb._publico(u))
                if partes.path == "/auth/v1/logout":
                    return self._json(204, None)
                if partes.path == "/__prova/concluir":
                    # Rota SO da falsa: a prova de interface "faz o papel do
                    # worker" e conclui o trabalho com os clipes que semeou.
                    resultado = sb.ao_concluir(corpo["id"]) if sb.ao_concluir else {}
                    sb.concluir(corpo["id"], resultado)
                    return self._json(200, {"ok": True})
                u = sb._quem(self)
                if partes.path == "/rest/v1/rpc/meu_saldo":
                    return self._json(200, sb.saldo.get(u["id"], 0) if u else 0)
                if partes.path == "/rest/v1/rpc/criar_trabalho":
                    if u is None:
                        return self._json(401, {"code": "42501", "message": "permission denied"})
                    return self._json(*sb.criar_trabalho(u, corpo))
                self._json(404, {"message": "rota falsa inexistente"})

        with _servir(Handler) as url:
            yield url
