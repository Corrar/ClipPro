"""POST /api/comprar -- abre a compra de um pacote e devolve o link do Mercado Pago.

Corpo: {"pacote": "<id>"}, com o token do usuario. Desligada sem
COMPRAS_ATIVAS=1. Logica em nuvem/app.py (RULINGS §29.5).
"""

import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nuvem import app  # noqa: E402
from nuvem.web import ler_json, responder, token_de  # noqa: E402


class handler(BaseHTTPRequestHandler):  # noqa: N801 - nome exigido pela Vercel
    def do_POST(self) -> None:  # noqa: N802
        responder(self, *app.iniciar_pagamento(os.environ, token_de(self), ler_json(self)))
