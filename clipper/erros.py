"""Erros previstos do pipeline.

Regra do projeto: nenhum estagio morre com stack trace cru na cara do usuario.
Todo erro esperado vira um ErroClipper carregando (1) o que aconteceu e (2) o
que fazer a respeito. O cli.py imprime os dois e sai com codigo 1.
Excecoes NAO previstas sao gravadas inteiras no log do projeto e resumidas na
tela com o caminho do log.
"""

from __future__ import annotations


class ErroClipper(Exception):
    """Falha esperada de um estagio, com mensagem acionavel."""

    estagio = "clipper"

    def __init__(
        self,
        mensagem: str,
        *,
        sugestao: str | None = None,
        detalhe: str | None = None,
    ) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.sugestao = sugestao
        self.detalhe = detalhe

    def formatar(self, max_linhas_detalhe: int = 20) -> str:
        linhas = [f"[ERRO: {self.estagio}] {self.mensagem}"]
        if self.detalhe:
            corpo = self.detalhe.strip().splitlines()
            cortado = corpo[-max_linhas_detalhe:]
            linhas.append("")
            linhas.append("  Saida da ferramenta:")
            if len(corpo) > len(cortado):
                linhas.append(f"    (... {len(corpo) - len(cortado)} linhas omitidas ...)")
            linhas.extend(f"    {l}" for l in cortado)
        if self.sugestao:
            linhas.append("")
            linhas.append(f"  -> O que fazer: {self.sugestao}")
        return "\n".join(linhas)


class ErroDependencia(ErroClipper):
    estagio = "dependencias"


class ErroIngestao(ErroClipper):
    estagio = "ingestao"


class ErroFFmpeg(ErroClipper):
    estagio = "ffmpeg"


class ErroTranscricao(ErroClipper):
    estagio = "transcricao"


class ErroSelecao(ErroClipper):
    estagio = "selecao"


class ErroRender(ErroClipper):
    estagio = "render"
