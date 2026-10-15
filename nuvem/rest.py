"""Chamadas a API REST do Supabase (PostgREST e Auth), so biblioteca padrao.

Dois jeitos de se apresentar, e a diferenca importa:

- chave SECRETA (worker): vai no 'apikey'. Passa por cima do RLS; por isso o
  worker so chama as funcoes da fila, que conferem dono e tentativa.
- chave PUBLICA + token do usuario (funcoes da Vercel): o RLS vale, e o
  banco so devolve o que e da conta logada.

As chaves novas (sb_secret_..., sb_publishable_...) NAO sao JWT: vao so no
'apikey'. As antigas (service_role, anon) sao JWT e vao tambem no
Authorization, como manda a documentacao do Supabase. Com token de usuario,
o Authorization e SEMPRE o token.

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

TIMEOUT_S = 60.0


class ErroNuvem(Exception):
    def __init__(self, mensagem: str, detalhe: str = "", status: int = 0) -> None:
        self.mensagem, self.detalhe, self.status = mensagem, detalhe, status
        super().__init__(f"{mensagem} {detalhe}".strip())


def cabecalhos(chave: str, token: str | None = None) -> dict[str, str]:
    cab = {"apikey": chave, "Content-Type": "application/json", "Accept": "application/json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    elif chave.startswith("eyJ"):
        cab["Authorization"] = f"Bearer {chave}"
    return cab


def chamar(
    url_base: str,
    chave: str,
    metodo: str,
    caminho: str,
    corpo: Any = None,
    *,
    token: str | None = None,
    prefer: str | None = None,
    timeout: float = TIMEOUT_S,
) -> Any:
    """Uma chamada REST. Devolve o JSON (ou None); erro HTTP vira ErroNuvem."""
    cab = cabecalhos(chave, token)
    if prefer:
        cab["Prefer"] = prefer
    pedido = urllib.request.Request(
        url_base.rstrip("/") + caminho, method=metodo, headers=cab,
        data=None if corpo is None else json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as r:
            dados = r.read()
    except urllib.error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", "replace")[:300]
        raise ErroNuvem(f"o Supabase recusou {metodo} {caminho.split('?')[0]} (HTTP {exc.code}).",
                        detalhe, exc.code) from None
    except urllib.error.URLError as exc:
        raise ErroNuvem(f"não consegui falar com o Supabase ({exc.reason}).") from None
    return json.loads(dados.decode("utf-8")) if dados else None


def rpc(url_base: str, chave: str, funcao: str, parametros: dict[str, Any], *,
        token: str | None = None) -> Any:
    return chamar(url_base, chave, "POST", f"/rest/v1/rpc/{funcao}", parametros, token=token)


def usuario_do_token(url_base: str, chave_publica: str, token: str) -> dict[str, Any] | None:
    """O usuario dono do token, perguntado ao proprio Auth do Supabase.

    None = token invalido ou vencido. Perguntar ao Auth (em vez de validar o
    JWT aqui) dispensa guardar o segredo de JWT do projeto nas funcoes.
    """
    if not token:
        return None
    try:
        dados = chamar(url_base, chave_publica, "GET", "/auth/v1/user", token=token)
    except ErroNuvem as exc:
        if exc.status in (401, 403):
            return None
        raise
    return dados if isinstance(dados, dict) and dados.get("id") else None
