"""GET /api/config -- URL e chave PUBLICA do Supabase para o navegador.

As duas vem do ambiente da Vercel (nunca do repositorio). Logica em
nuvem/app.py (RULINGS §29.3).
"""

import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nuvem import app  # noqa: E402
from nuvem.web import responder  # noqa: E402


class handler(BaseHTTPRequestHandler):  # noqa: N801 - nome exigido pela Vercel
    def do_GET(self) -> None:  # noqa: N802
        responder(self, *app.configuracao_publica(os.environ))
