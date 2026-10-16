"""A fila de trabalhos, vista do worker.

Hoje existe uma implementacao: FilaEmPasta, uma pasta com quatro
subpastas. Ela serve as provas e o uso numa maquina so. A fila da NUVEM
(fornecedor ainda por decidir, relatorio da N-1) implementa os mesmos cinco
verbos: reservar, renovar, concluir, falhar, devolver.

RESERVA COM PRAZO, NAO TRAVA. O worker do beta e um PC de casa: pode
desligar no meio de um video de 1 h. Um trabalho reservado e devolvido sozinho
quando o worker para de renovar a reserva (devolver_expirados), e o mesmo
trabalho roda de novo no proximo worker. Isso so e seguro porque os estagios
ja sao idempotentes (o .estado.json de cada um decide o que refazer).

Um trabalho que derruba o worker tres vezes vai para 'falhos' em vez de
voltar para sempre.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worker.contrato import ErroContrato, Trabalho

PENDENTES, EM_CURSO, FEITOS, FALHOS = "pendentes", "em_curso", "feitos", "falhos"
TENTATIVAS_MAXIMAS = 3


@dataclass
class Reserva:
    nome: str  # nome do arquivo dentro de em_curso/
    trabalho: Trabalho
    worker: str
    tentativa: int


class FilaEmPasta:
    """pendentes/ -> em_curso/ -> feitos/ ou falhos/, por renomeacao atomica.

    os.replace e atomico no mesmo disco, no Windows e no Linux: dois workers
    disputando o mesmo arquivo, so um renomeia; o outro ve FileNotFoundError
    e passa para o proximo. O nome comeca com o instante da publicacao, entao
    a ordem alfabetica e a ordem de chegada (FIFO).
    """

    def __init__(self, raiz: Path) -> None:
        self.raiz = Path(raiz)
        for sub in (PENDENTES, EM_CURSO, FEITOS, FALHOS):
            (self.raiz / sub).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ nuvem
    def publicar(self, dados: dict[str, Any]) -> str:
        """Coloca um trabalho na fila (papel da nuvem; aqui, das provas)."""
        nome = f"{time.time_ns():020d}-{dados.get('id', 'trabalho')}.json"
        _gravar_atomico(self.raiz / PENDENTES / nome, dados)
        return nome

    # ------------------------------------------------------------ worker
    def reservar(self, worker: str) -> Reserva | None:
        for origem in sorted((self.raiz / PENDENTES).glob("*.json")):
            destino = self.raiz / EM_CURSO / origem.name
            try:
                os.replace(origem, destino)
            except (FileNotFoundError, PermissionError):
                # Outro worker levou primeiro. No Windows a disputa tambem
                # aparece como PermissionError (arquivo no meio de um rename).
                continue
            dados = _ler(destino)
            tentativa = int(dados.get("_tentativas") or 0) + 1
            try:
                trabalho = Trabalho.de_dict(dados)
            except ErroContrato as exc:
                # Pedido torto nunca chega ao motor: vai direto para falhos,
                # com o motivo, e o worker segue para o proximo.
                self._encerrar(destino, FALHOS, dados, {
                    "status": "recusado",
                    "erro": {"mensagem": "o pedido foi recusado.", "sugestao": "",
                             "detalhe": "; ".join(exc.problemas)},
                    "creditos": 0,
                })
                continue
            dados["_tentativas"] = tentativa
            dados["_worker"] = worker
            _gravar_atomico(destino, dados)
            return Reserva(origem.name, trabalho, worker, tentativa)
        return None

    def renovar(self, reserva: Reserva) -> None:
        try:
            os.utime(self.raiz / EM_CURSO / reserva.nome)
        except OSError:
            pass  # prazo vencido (reserva devolvida) ou arquivo ocupado: tenta no proximo batimento

    def concluir(self, reserva: Reserva, resultado: dict[str, Any]) -> bool:
        return self._encerrar_se_minha(reserva, FEITOS, resultado)

    def falhar(self, reserva: Reserva, resultado: dict[str, Any]) -> bool:
        return self._encerrar_se_minha(reserva, FALHOS, resultado)

    def _encerrar_se_minha(self, reserva: Reserva, destino_sub: str,
                           resultado: dict[str, Any]) -> bool:
        """False quando a reserva venceu e o trabalho ja e de outra tentativa.

        Sem esta conferencia, um worker lento cujo prazo venceu encerraria a
        reserva NOVA (mesmo nome de arquivo) de quem pegou o trabalho depois.
        """
        caminho = self.raiz / EM_CURSO / reserva.nome
        dados = _ler(caminho)
        if (dados.get("_worker") != reserva.worker
                or int(dados.get("_tentativas") or 0) != reserva.tentativa):
            return False
        self._encerrar(caminho, destino_sub, dados, resultado)
        return True

    def devolver(self, reserva: Reserva) -> None:
        """Ctrl+C no worker: o trabalho volta para a fila agora, sem esperar o prazo."""
        origem = self.raiz / EM_CURSO / reserva.nome
        try:
            os.replace(origem, self.raiz / PENDENTES / reserva.nome)
        except FileNotFoundError:
            pass

    def devolver_expirados(self, prazo_s: float) -> list[str]:
        """Reservas sem renovacao ha mais de 'prazo_s' voltam (ou falham na 3a)."""
        devolvidos = []
        limite = time.time() - prazo_s
        for caminho in sorted((self.raiz / EM_CURSO).glob("*.json")):
            try:
                if caminho.stat().st_mtime > limite:
                    continue
            except FileNotFoundError:
                continue
            dados = _ler(caminho)
            if int(dados.get("_tentativas") or 0) >= TENTATIVAS_MAXIMAS:
                self._encerrar(caminho, FALHOS, dados, {
                    "status": "falhou",
                    "erro": {
                        "mensagem": "o processamento deste vídeo parou várias vezes no meio.",
                        "sugestao": "tente de novo mais tarde; nenhum crédito foi usado.",
                        "detalhe": f"{TENTATIVAS_MAXIMAS} tentativas sem terminar",
                    },
                    "creditos": 0,
                })
            else:
                try:
                    os.replace(caminho, self.raiz / PENDENTES / caminho.name)
                except FileNotFoundError:
                    continue
            devolvidos.append(caminho.name)
        return devolvidos

    # ------------------------------------------------------------ apoio
    def _encerrar(self, origem: Path, destino_sub: str, dados: dict[str, Any],
                  resultado: dict[str, Any]) -> None:
        trabalho = {k: v for k, v in dados.items() if not str(k).startswith("_")}
        meta = {k: v for k, v in dados.items() if str(k).startswith("_")}
        _gravar_atomico(self.raiz / destino_sub / origem.name,
                        {"trabalho": trabalho, "fila": meta, "resultado": resultado})
        try:
            origem.unlink()
        except FileNotFoundError:
            pass


def _ler(caminho: Path) -> dict[str, Any]:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _gravar_atomico(caminho: Path, dados: dict[str, Any]) -> None:
    # Escreve ao lado e renomeia: quem le nunca ve um JSON pela metade. O
    # '.tmp' nao casa com o glob '*.json' de reservar().
    temp = caminho.with_name(caminho.name + ".tmp")
    temp.write_text(json.dumps(dados, ensure_ascii=False, indent=2),
                    encoding="utf-8", newline="\n")
    # No Windows, trocar um arquivo que outro processo esta lendo da
    # PermissionError por um instante: tenta de novo antes de desistir.
    for tentativa in range(10):
        try:
            os.replace(temp, caminho)
            return
        except PermissionError:
            if tentativa == 9:
                raise
            time.sleep(0.05)
