"""POST /api/upload -- URL assinada para enviar o video direto ao R2.

Corpo: {"nome": "live.mp4", "tamanho": 123, "tipo": "video/mp4"}, com o
token do usuario no Authorization. Logica em nuvem/app.py (RULINGS §29.3).
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
        responder(self, *app.pedir_upload(os.environ, token_de(self), ler_json(self)))
