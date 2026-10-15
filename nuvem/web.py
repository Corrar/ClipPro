"""A cola HTTP das funcoes da Vercel: ler o pedido, responder JSON.

Separada de nuvem/app.py para a logica ser testada sem servidor.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Any

LIMITE_CORPO = 16 * 1024  # os pedidos do app sao JSON pequenos


def token_de(h: BaseHTTPRequestHandler) -> str | None:
    valor = h.headers.get("Authorization") or ""
    return valor[7:].strip() if valor.lower().startswith("bearer ") else None


def ler_json(h: BaseHTTPRequestHandler) -> Any:
    try:
        tamanho = int(h.headers.get("Content-Length") or 0)
    except ValueError:
        return None
    if not 0 < tamanho <= LIMITE_CORPO:
        return None
    try:
        return json.loads(h.rfile.read(tamanho).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def responder(h: BaseHTTPRequestHandler, status: int, dados: dict[str, Any]) -> None:
    corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(corpo)))
    # URL assinada nao pode ficar em cache de ninguem.
    h.send_header("Cache-Control", "no-store")
    h.send_header("X-Content-Type-Options", "nosniff")
    h.end_headers()
    h.wfile.write(corpo)
