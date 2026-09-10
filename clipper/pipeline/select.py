"""Selecao de clipes (F2). Implementacao completa chega na fase 2.

Este arquivo existe agora apenas para fixar a assinatura publica que o cli.py
ja importa, de modo que a F2 nao mude a interface.
"""

from __future__ import annotations

from typing import Any

from clipper.config import Estado, Saida
from clipper.erros import ErroSelecao


def selecionar(
    saida: Saida,
    estado: Estado,
    *,
    estrategia: str,
    n: int = 5,
    modelo: str = "haiku",
    forcar: bool = False,
    resposta_manual: str | None = None,
) -> dict[str, Any]:
    """Escolhe os melhores trechos e grava selecao.json."""
    raise ErroSelecao(
        "a selecao de clipes ainda nao foi implementada.",
        sugestao="ela entra na fase F2 do projeto; por enquanto rode 'clipper transcribe'.",
    )
