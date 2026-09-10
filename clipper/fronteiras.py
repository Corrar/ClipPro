"""Fronteiras de frase da transcricao: onde e permitido cortar um clipe.

Por que este modulo existe separado: um segmento do whisper NAO e uma frase.
Medido no video de teste, os segmentos cortam no meio da oracao o tempo todo:

    [02:11 - 02:16] ...ela e muito recomendada por varios
    [02:16 - 02:21] que fazem casas de alto padrao...

Cortar num fim de segmento entregaria um clipe comecando em "que fazem casas".
Entao a unidade de corte aqui e a FRASE, reconstruida a partir da lista plana
de palavras de transcricao.json usando a pontuacao terminal. Toda fronteira
devolvida por este modulo cai exatamente no inicio da primeira palavra de uma
frase ou no fim da ultima palavra de uma frase -- nunca no meio de uma palavra,
por construcao.

A F3 tambem consome daqui (`palavras_entre`) para montar a legenda karaoke.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Any, Iterable

from clipper.erros import ErroSelecao

# Pontuacao que fecha uma frase. Inclui o travessao reticente do PT-BR falado.
_FIM_DE_FRASE = ".!?…"

# Fechamentos que podem vir DEPOIS da pontuacao terminal: 'ele disse "acabou."'
_FECHAMENTOS = "\"'»)]}"

# Se a transcricao vier praticamente sem pontuacao, as "frases" viram blocos
# gigantes e a promessa de cortar em fronteira de frase deixa de valer.
_DURACAO_MEDIA_SUSPEITA = 45.0
_MINIMO_DE_FRASES = 5


@dataclass(frozen=True)
class Frase:
    """Uma frase da transcricao, com os indices das palavras que a compoem."""

    indice: int
    inicio: float
    fim: float
    texto: str
    palavra_inicio: int  # indice na lista plana, inclusivo
    palavra_fim: int  # indice na lista plana, inclusivo

    @property
    def duracao(self) -> float:
        return self.fim - self.inicio


@dataclass(frozen=True)
class Encaixe:
    """Resultado de encaixar um pedido de corte nas fronteiras reais."""

    inicio: float
    fim: float
    frase_inicio: int
    frase_fim: int
    palavra_inicio: int
    palavra_fim: int
    ajuste_inicio: float  # quanto o inicio andou em relacao ao pedido
    ajuste_fim: float

    @property
    def duracao(self) -> float:
        return self.fim - self.inicio


def _termina_frase(texto: str) -> bool:
    limpo = texto.rstrip(_FECHAMENTOS)
    return bool(limpo) and limpo[-1] in _FIM_DE_FRASE


class Fronteiras:
    """Indice de frases de uma transcricao, com busca e encaixe de cortes."""

    def __init__(self, frases: list[Frase], palavras: list[dict[str, Any]], duracao: float) -> None:
        self.frases = frases
        self.palavras = palavras
        self.duracao = duracao
        self._inicios = [f.inicio for f in frases]
        self._fins = [f.fim for f in frases]

    # ------------------------------------------------------------ construcao

    @classmethod
    def de_transcricao(cls, transcricao: dict[str, Any]) -> "Fronteiras":
        palavras = transcricao.get("palavras") or []
        if not palavras:
            raise ErroSelecao(
                "a transcrição não tem a lista de palavras com timestamps.",
                sugestao=(
                    "refaça a transcrição para gerar o arquivo no formato novo:  "
                    "clipper transcribe <entrada> --force"
                ),
            )

        frases: list[Frase] = []
        atual: list[int] = []
        for i, palavra in enumerate(palavras):
            atual.append(i)
            if _termina_frase(str(palavra.get("texto") or "")):
                frases.append(cls._montar(len(frases), atual, palavras))
                atual = []
        if atual:
            # Cauda sem pontuacao terminal: ainda e material utilizavel.
            frases.append(cls._montar(len(frases), atual, palavras))

        duracao = float(transcricao.get("duracao_audio") or 0.0)
        if not duracao and palavras:
            duracao = float(palavras[-1]["fim"])

        cls._conferir_pontuacao(frases, duracao)
        return cls(frases, palavras, duracao)

    @staticmethod
    def _montar(indice: int, indices: list[int], palavras: list[dict[str, Any]]) -> Frase:
        primeira, ultima = palavras[indices[0]], palavras[indices[-1]]
        texto = " ".join(str(palavras[i]["texto"]) for i in indices)
        return Frase(
            indice=indice,
            inicio=round(float(primeira["inicio"]), 3),
            fim=round(float(ultima["fim"]), 3),
            texto=texto,
            palavra_inicio=indices[0],
            palavra_fim=indices[-1],
        )

    @staticmethod
    def _conferir_pontuacao(frases: list[Frase], duracao: float) -> None:
        """Sem pontuacao nao existe fronteira de frase -- e melhor parar."""
        if not frases:
            raise ErroSelecao(
                "não consegui montar nenhuma frase a partir da transcrição.",
                sugestao="confira se out/<slug>/transcricao.json tem conteúdo real.",
            )
        media = duracao / len(frases) if duracao else 0.0
        if len(frases) < _MINIMO_DE_FRASES or media > _DURACAO_MEDIA_SUSPEITA:
            raise ErroSelecao(
                f"a transcrição praticamente não tem pontuação: {len(frases)} frase(s) "
                f"em {duracao:.0f}s (média de {media:.0f}s por frase). Sem pontuação não "
                "existe fronteira de frase, e o clipper se recusa a cortar no meio de uma.",
                sugestao=(
                    "refaça a transcrição com um modelo maior, que pontua melhor:  "
                    "clipper transcribe <entrada> --modelo-whisper medium --force  "
                    "(ou large-v3, se tiver paciência)."
                ),
            )

    # --------------------------------------------------------------- consulta

    def frase_em(self, indice: int) -> Frase:
        return self.frases[indice]

    def palavras_entre(self, inicio: float, fim: float) -> list[dict[str, Any]]:
        """Palavras cujo intervalo cai dentro de [inicio, fim]. Usado pela F3."""
        return [
            p
            for p in self.palavras
            if float(p["inicio"]) >= inicio - 1e-6 and float(p["fim"]) <= fim + 1e-6
        ]

    def texto_entre(self, inicio: float, fim: float) -> str:
        return " ".join(str(p["texto"]) for p in self.palavras_entre(inicio, fim))

    def e_inicio_de_frase(self, t: float, tolerancia: float = 1e-3) -> bool:
        return self._tem_proximo(self._inicios, t, tolerancia)

    def e_fim_de_frase(self, t: float, tolerancia: float = 1e-3) -> bool:
        return self._tem_proximo(self._fins, t, tolerancia)

    @staticmethod
    def _tem_proximo(valores: list[float], t: float, tolerancia: float) -> bool:
        if not valores:
            return False
        i = bisect.bisect_left(valores, t)
        for j in (i - 1, i, i + 1):
            if 0 <= j < len(valores) and abs(valores[j] - t) <= tolerancia:
                return True
        return False

    # ---------------------------------------------------------------- encaixe

    def _proximas(self, valores: list[float], alvo: float, tolerancia: float) -> list[int]:
        """Indices de frase cujo valor esta a no maximo `tolerancia` do alvo."""
        esquerda = bisect.bisect_left(valores, alvo - tolerancia)
        direita = bisect.bisect_right(valores, alvo + tolerancia)
        return list(range(esquerda, direita))

    def encaixar(
        self,
        inicio_pedido: float,
        fim_pedido: float,
        *,
        min_s: float,
        max_s: float,
        tolerancia: float,
    ) -> Encaixe:
        """Move um pedido de corte para a fronteira de frase mais proxima.

        Procura o par (inicio de frase, fim de frase) que respeite a duracao
        pedida e ande o MENOS possivel em relacao ao que foi pedido. Se nenhum
        par servir, levanta ErroSelecao explicando o que foi possivel encontrar
        -- assim a mensagem diz ao usuario o que pedir ao modelo na proxima
        rodada, em vez de so dizer "invalido".
        """
        cand_i = self._proximas(self._inicios, inicio_pedido, tolerancia)
        cand_f = self._proximas(self._fins, fim_pedido, tolerancia)

        if not cand_i or not cand_f:
            faltou = "início" if not cand_i else "fim"
            alvo = inicio_pedido if not cand_i else fim_pedido
            perto = self._mais_proximo(self._inicios if not cand_i else self._fins, alvo)
            raise ErroSelecao(
                f"não há fronteira de frase perto do {faltou} pedido "
                f"({_mmss(alvo)}). A mais próxima está em {_mmss(perto)}, "
                f"a {abs(perto - alvo):.0f}s de distância (o limite é {tolerancia:.0f}s).",
                sugestao=(
                    "esse tempo provavelmente foi inventado. Peça ao modelo para usar "
                    "apenas os tempos [mm:ss] que aparecem no prompt."
                ),
            )

        melhor: Encaixe | None = None
        melhor_custo = float("inf")
        duracoes_vistas: list[float] = []
        for i in cand_i:
            fi = self.frases[i]
            for f in cand_f:
                ff = self.frases[f]
                dur = ff.fim - fi.inicio
                duracoes_vistas.append(dur)
                if dur < min_s or dur > max_s:
                    continue
                custo = abs(fi.inicio - inicio_pedido) + abs(ff.fim - fim_pedido)
                if custo < melhor_custo:
                    melhor_custo = custo
                    melhor = Encaixe(
                        inicio=fi.inicio,
                        fim=ff.fim,
                        frase_inicio=fi.indice,
                        frase_fim=ff.indice,
                        palavra_inicio=fi.palavra_inicio,
                        palavra_fim=ff.palavra_fim,
                        ajuste_inicio=round(fi.inicio - inicio_pedido, 3),
                        ajuste_fim=round(ff.fim - fim_pedido, 3),
                    )

        if melhor is None:
            possiveis = [d for d in duracoes_vistas if d > 0]
            faixa = (
                f"as combinações possíveis por perto dão de {min(possiveis):.0f}s a "
                f"{max(possiveis):.0f}s"
                if possiveis
                else "não sobrou nenhuma combinação válida por perto"
            )
            raise ErroSelecao(
                f"o trecho {_mmss(inicio_pedido)}–{_mmss(fim_pedido)} "
                f"({fim_pedido - inicio_pedido:.0f}s) não encaixa em fronteira de frase "
                f"respeitando o limite de {min_s:.0f}–{max_s:.0f}s: {faixa}.",
                sugestao=(
                    "peça ao modelo para escolher outro trecho, ou para esticar/encurtar "
                    "este até cair entre dois tempos [mm:ss] que existem no prompt."
                ),
            )
        return melhor

    def primeiro_inicio_apos(self, t: float) -> Frase | None:
        """Primeira frase que comeca em t ou depois. Usado para desfazer overlap."""
        i = bisect.bisect_left(self._inicios, t - 1e-6)
        return self.frases[i] if i < len(self.frases) else None

    def _mais_proximo(self, valores: list[float], alvo: float) -> float:
        if not valores:
            return 0.0
        i = bisect.bisect_left(valores, alvo)
        opcoes = [valores[j] for j in (i - 1, i) if 0 <= j < len(valores)]
        return min(opcoes, key=lambda v: abs(v - alvo)) if opcoes else valores[0]


def _mmss(segundos: float) -> str:
    segundos = max(0.0, float(segundos))
    m, s = divmod(int(segundos), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def mmss(segundos: float) -> str:
    """Formata segundos como mm:ss (ou h:mm:ss). Publico: o prompt usa."""
    return _mmss(segundos)


def para_segundos(valor: Any) -> float:
    """Aceita 92.5, "92.5", "01:32" ou "1:01:32" e devolve segundos float.

    O modelo responde ora em segundos, ora no mm:ss que ele leu no prompt.
    Aceitar os dois evita rejeitar uma resposta boa por detalhe de formato.
    """
    if isinstance(valor, bool):
        raise ValueError("booleano não é tempo")
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(",", ".")
    if not texto:
        raise ValueError("tempo vazio")
    if ":" in texto:
        partes = texto.split(":")
        if len(partes) > 3:
            raise ValueError(f"formato de tempo não reconhecido: {valor!r}")
        total = 0.0
        for parte in partes:
            total = total * 60.0 + float(parte)
        return total
    return float(texto)


def blocos_para_prompt(
    fronteiras: Fronteiras,
    picos: Iterable[float] = (),
    marcador: str = "▲",
) -> list[str]:
    """Uma linha por frase: "[mm:ss→mm:ss] texto", com marca de energia alta.

    Os dois tempos sao TRUNCADOS (nao arredondados) de proposito: arredondar o
    fim para cima faz o bloco parecer invadir o proximo, e um prompt com tempos
    que se contradizem convida o modelo a inventar os seus.
    """
    picos_set = {int(p) for p in picos}
    linhas: list[str] = []
    for frase in fronteiras.frases:
        alto = any(int(frase.inicio) <= t <= int(frase.fim) for t in picos_set)
        marca = marcador if alto else " "
        linhas.append(
            f"[{_mmss(frase.inicio)}→{_mmss(frase.fim)}]{marca} {frase.texto}"
        )
    return linhas
