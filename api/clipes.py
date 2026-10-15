"""GET /api/clipes?trabalho=<id> -- URLs assinadas dos clipes do usuario.

O trabalho e lido com o token do proprio usuario: o RLS so devolve o que e
dele. Logica em nuvem/app.py (RULINGS §29.3).
"""

import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nuvem import app  # noqa: E402
from nuvem.web import responder, token_de  # noqa: E402


class handler(BaseHTTPRequestHandler):  # noqa: N801 - nome exigido pela Vercel
    def do_GET(self) -> None:  # noqa: N802
        consulta = parse_qs(urlsplit(self.path).query)
        trabalho = (consulta.get("trabalho") or [""])[0]
        responder(self, *app.links_dos_clipes(os.environ, token_de(self), trabalho))
