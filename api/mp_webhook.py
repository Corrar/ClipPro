"""POST /api/mp_webhook -- aviso de pagamento do Mercado Pago.

Confere a assinatura x-signature, consulta o pagamento na API do Mercado Pago
e so entao credita (confirmar_compra, idempotente). Logica em nuvem/app.py
(RULINGS §29.5).
"""

import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nuvem import app  # noqa: E402
from nuvem.web import ler_json, responder  # noqa: E402


class handler(BaseHTTPRequestHandler):  # noqa: N801 - nome exigido pela Vercel
    def do_POST(self) -> None:  # noqa: N802
        consulta = dict(parse_qsl(urlsplit(self.path).query))
        cabecalhos = {k.lower(): v for k, v in self.headers.items()}
        responder(self, *app.receber_webhook(os.environ, consulta, cabecalhos, ler_json(self)))
