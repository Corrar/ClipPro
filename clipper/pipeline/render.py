"""Render dos clipes 9:16 com legenda karaoke (F3).

Este arquivo existe agora apenas para fixar a assinatura publica que o cli.py
ja importa, de modo que a F3 nao mude a interface.
"""

from __future__ import annotations

from typing import Any

from clipper.config import Estado, Saida
from clipper.erros import ErroRender


def renderizar(
    saida: Saida,
    estado: Estado,
    *,
    preset: str = "bold-amarelo",
    forcar: bool = False,
) -> dict[str, Any]:
    """Corta, reenquadra em 9:16, queima legenda e grava clips/ + relatorio.md."""
    raise ErroRender(
        "o render dos clipes ainda nao foi implementado.",
        sugestao="ele entra na fase F3 do projeto; por enquanto rode 'clipper transcribe'.",
    )
