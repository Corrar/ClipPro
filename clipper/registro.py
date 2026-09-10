"""Log e cronometragem dos estagios.

Duas saidas: console (curto, PT-BR, sem stack) e arquivo out/<slug>/clipper.log
(completo, com stack quando algo inesperado explode).
"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import contextmanager
from pathlib import Path

_NOME = "clipper"
_CONFIGURADO = False


def _forcar_utf8() -> None:
    """Windows: o console pode estar em cp1252 e engasgar com acento."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def configurar(arquivo_log: Path | None = None, verboso: bool = False) -> logging.Logger:
    global _CONFIGURADO
    _forcar_utf8()
    log = logging.getLogger(_NOME)
    log.setLevel(logging.DEBUG)

    if not _CONFIGURADO:
        console = logging.StreamHandler(stream=sys.stderr)
        console.setLevel(logging.DEBUG if verboso else logging.INFO)
        console.setFormatter(logging.Formatter("%(message)s"))
        console.set_name("console")
        log.addHandler(console)
        _CONFIGURADO = True
    else:
        for h in log.handlers:
            if h.get_name() == "console":
                h.setLevel(logging.DEBUG if verboso else logging.INFO)

    if arquivo_log is not None:
        ja_tem = any(
            isinstance(h, logging.FileHandler)
            and Path(getattr(h, "baseFilename", "")) == Path(arquivo_log).resolve()
            for h in log.handlers
        )
        if not ja_tem:
            Path(arquivo_log).parent.mkdir(parents=True, exist_ok=True)
            arq = logging.FileHandler(arquivo_log, encoding="utf-8")
            arq.setLevel(logging.DEBUG)
            arq.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
            )
            log.addHandler(arq)

    return log


def obter() -> logging.Logger:
    return logging.getLogger(_NOME)


class Cronometro:
    """Mede um estagio e devolve os segundos gastos."""

    def __init__(self, rotulo: str) -> None:
        self.rotulo = rotulo
        self.segundos = 0.0

    def __enter__(self) -> "Cronometro":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *_exc) -> None:
        self.segundos = time.perf_counter() - self._t0


@contextmanager
def etapa(rotulo: str):
    """Loga inicio/fim de um estagio com o tempo gasto."""
    from clipper.config import humanizar_tempo

    log = obter()
    log.info("")
    log.info(f">> {rotulo}")
    crono = Cronometro(rotulo)
    with crono:
        yield crono
    log.info(f"   concluido em {humanizar_tempo(crono.segundos)}")
