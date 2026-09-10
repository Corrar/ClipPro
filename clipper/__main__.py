"""Permite rodar o pacote como  python -m clipper  (mesma coisa que 'clipper')."""

from __future__ import annotations

import sys

from clipper.cli import main

if __name__ == "__main__":
    sys.exit(main())
