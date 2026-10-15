"""Onde ficam o video enviado (entrada) e os clipes prontos (resultado).

Hoje: DepositoEmPasta, para as provas e para uma maquina so. O deposito da
NUVEM (fornecedor por decidir, relatorio da N-1) implementa os mesmos dois
verbos: obter_entrada e enviar.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from worker.contrato import _RE_CHAVE, _RE_ID


class ErroDeposito(Exception):
    def __init__(self, mensagem: str) -> None:
        self.mensagem = mensagem
        super().__init__(mensagem)


class DepositoEmPasta:
    """raiz/entradas/<chave> e raiz/resultados/<trabalho>/<arquivo>."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = Path(raiz)
        (self.raiz / "entradas").mkdir(parents=True, exist_ok=True)
        (self.raiz / "resultados").mkdir(parents=True, exist_ok=True)

    def obter_entrada(self, chave: str, destino_dir: Path) -> Path:
        """Traz o video enviado para a pasta do trabalho. Idempotente.

        POR QUE IDEMPOTENTE: um trabalho devolvido (worker desligou) roda de
        novo e nao pode recopiar 1 GB (29 min = 1,0 GB, medida do README).
        copy2 preserva o mtime, entao a copia ja feita bate em tamanho e mtime
        -- e a assinatura do ingest (bytes + mtime) tambem bate, e o estagio
        reaproveita em vez de refazer.
        """
        if not (_RE_CHAVE.match(chave) and ".." not in chave):
            raise ErroDeposito("a chave do arquivo enviado é inválida.")
        origem = self.raiz / "entradas" / chave
        if not origem.is_file():
            raise ErroDeposito("o arquivo enviado não está mais no depósito.")
        destino_dir = Path(destino_dir)
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / chave
        st = origem.stat()
        try:
            atual = destino.stat()
            if atual.st_size == st.st_size and atual.st_mtime_ns == st.st_mtime_ns:
                return destino
        except FileNotFoundError:
            pass
        temp = destino.with_name(destino.name + ".parcial")
        shutil.copy2(origem, temp)
        os.replace(temp, destino)
        return destino

    def enviar(self, trabalho_id: str, arquivo: Path) -> str:
        """Publica um arquivo do resultado. Devolve a chave relativa."""
        if not _RE_ID.match(trabalho_id):
            raise ErroDeposito("id de trabalho inválido para o depósito.")
        pasta = self.raiz / "resultados" / trabalho_id
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / Path(arquivo).name
        temp = destino.with_name(destino.name + ".parcial")
        shutil.copyfile(arquivo, temp)
        os.replace(temp, destino)
        return f"resultados/{trabalho_id}/{destino.name}"
