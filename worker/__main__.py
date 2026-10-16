"""python -m worker -- o laco do worker: reservar, executar, entregar.

    python -m worker --nuvem                              # Supabase + R2 (§28)
    python -m worker --fila DIR --deposito DIR            # pastas (provas)
    python -m worker ... --uma-vez                        # um trabalho e sai

Com --nuvem, as chaves vem de variaveis de ambiente (worker/nuvem.py,
VARIAVEIS); nunca de arquivo do repositorio.

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

from clipper import config, motor, registro
from worker.deposito import DepositoEmPasta
from worker.executor import executar
from worker.fila import FilaEmPasta, Reserva
from worker.nuvem import VARIAVEIS, DepositoR2, ErroNuvem, FilaSupabase, variaveis_faltando

# 10 min sem renovar = worker caiu. O batimento renova a cada 1/4 do prazo,
# entao so um worker morto (ou suspenso) deixa a reserva vencer.
PRAZO_PADRAO_S = 600.0
INTERVALO_PADRAO_S = 5.0
# Entregar o resultado depois de um video de 1 h: a rede pode piscar. Sem
# insistir, a reserva venceria e o video inteiro seria refeito (a pasta local
# ja foi limpa no sucesso). 2+4+8+16+32 s ~ 1 min de insistencia.
ESPERAS_ENTREGA_S = (2.0, 4.0, 8.0, 16.0, 32.0)


class _Batimento(threading.Thread):
    """Renova a reserva enquanto o motor trabalha (o whisper leva minutos)."""

    def __init__(self, fila: Any, reserva: Reserva, a_cada_s: float) -> None:
        super().__init__(name="worker-batimento", daemon=True)
        self._fila, self._reserva, self._a_cada = fila, reserva, max(1.0, a_cada_s)
        self._parar = threading.Event()

    def run(self) -> None:
        while not self._parar.wait(self._a_cada):
            self._fila.renovar(self._reserva)

    def parar(self) -> None:
        self._parar.set()


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m worker",
        description="Worker do ClipPro: pega trabalhos da fila e devolve os clipes no depósito.",
    )
    p.add_argument("--nuvem", action="store_true",
                   help="usa a fila do Supabase e o depósito do R2 (chaves no ambiente)")
    p.add_argument("--fila", type=Path, help="pasta da fila de trabalhos (sem --nuvem)")
    p.add_argument("--deposito", type=Path,
                   help="pasta do depósito (vídeos enviados e clipes prontos; sem --nuvem)")
    p.add_argument("--trabalhos", type=Path, default=config.DIR_SAIDA_PADRAO / "_worker",
                   help="pasta de trabalho local (padrão: out/_worker)")
    p.add_argument("--uma-vez", action="store_true",
                   help="processa no máximo um trabalho e sai")
    p.add_argument("--intervalo", type=float, default=INTERVALO_PADRAO_S,
                   help="segundos entre consultas à fila vazia")
    p.add_argument("--prazo", type=float, default=PRAZO_PADRAO_S,
                   help="segundos sem renovação até a reserva voltar para a fila")
    p.add_argument("--modelo-whisper", choices=motor.MODELOS_WHISPER,
                   default=config.MODELO_WHISPER_PADRAO)
    args = p.parse_args(argv)
    if args.nuvem and (args.fila or args.deposito):
        p.error("use --nuvem OU --fila/--deposito, não os dois.")
    if not args.nuvem and not (args.fila and args.deposito):
        p.error("informe --nuvem, ou --fila e --deposito.")
    return args


def _entregar(fila: Any, reserva: Reserva, resultado: dict[str, Any]) -> bool:
    log = registro.obter()
    encerrar = fila.concluir if resultado["status"] == "concluido" else fila.falhar
    for i, espera in enumerate((*ESPERAS_ENTREGA_S, None), 1):
        try:
            return encerrar(reserva, resultado)
        except ErroNuvem as exc:
            if espera is None:
                raise
            log.warning(f"entrega do resultado falhou ({exc.mensagem}); "
                        f"tentativa {i}, nova em {espera:.0f} s.")
            time.sleep(espera)
    return False


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    log = registro.configurar(None, verboso=False)
    # O worker so usa o caminho da API (§27, G2): sem chave, todo trabalho
    # falharia na selecao depois de gastar a transcricao. Recusa na partida.
    if config.chave_api_anthropic() is None:
        print("o worker precisa de ANTHROPIC_API_KEY no ambiente para escolher os cortes.",
              file=sys.stderr)
        print("defina a chave (com teto de gasto mensal no console da Anthropic) e rode de novo.",
              file=sys.stderr)
        return 2

    if args.nuvem:
        faltam = variaveis_faltando()
        if faltam:
            print("faltam variáveis de ambiente para o modo --nuvem:", file=sys.stderr)
            for nome in faltam:
                print(f"  {nome}: {VARIAVEIS[nome]}", file=sys.stderr)
            return 2
        fila: Any = FilaSupabase.do_ambiente(args.prazo)
        deposito: Any = DepositoR2.do_ambiente()
        onde = "Supabase + R2"
    else:
        fila = FilaEmPasta(args.fila)
        deposito = DepositoEmPasta(args.deposito)
        onde = str(args.fila)
    worker = f"{socket.gethostname()}-{os.getpid()}"
    log.info(f"worker {worker} de plantão na fila {onde}")

    try:
        while True:
            try:
                for nome in fila.devolver_expirados(args.prazo):
                    log.info(f"reserva vencida devolvida: {nome}")
                reserva = fila.reservar(worker)
            except ErroNuvem as exc:
                # Sem rede o worker espera e tenta de novo; nao morre.
                log.warning(f"a fila não respondeu: {exc.mensagem} {exc.detalhe}".strip())
                if args.uma_vez:
                    return 1
                time.sleep(args.intervalo)
                continue
            if reserva is None:
                if args.uma_vez:
                    return 0
                time.sleep(args.intervalo)
                continue

            batimento = _Batimento(fila, reserva, args.prazo / 4)
            batimento.start()
            try:
                resultado = executar(reserva.trabalho, deposito, args.trabalhos,
                                     worker=worker, modelo_whisper=args.modelo_whisper)
            except KeyboardInterrupt:
                batimento.parar()
                fila.devolver(reserva)
                print("Interrompido: o trabalho voltou para a fila.", file=sys.stderr)
                return 130
            finally:
                batimento.parar()

            try:
                entregue = _entregar(fila, reserva, resultado)
            except ErroNuvem as exc:
                log.error(f"não consegui entregar o resultado de {reserva.trabalho.id}: "
                          f"{exc.mensagem}; a reserva vai vencer e o trabalho volta à fila.")
                entregue = True  # ja relatado; nao repetir a mensagem abaixo
            if not entregue:
                log.info(f"a reserva de {reserva.trabalho.id} venceu antes do fim; "
                         "o resultado desta tentativa foi descartado.")
            log.info(f"trabalho {reserva.trabalho.id}: {resultado['status']}, "
                     f"{len(resultado.get('clipes') or [])} clipe(s), "
                     f"{resultado.get('creditos', 0)} crédito(s), "
                     f"{resultado.get('segundos_total', 0):.0f} s")
            if args.uma_vez:
                return 0
    except KeyboardInterrupt:
        print("Interrompido.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
