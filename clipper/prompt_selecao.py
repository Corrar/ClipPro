"""Monta o prompt_selecao.txt que o usuario leva a um modelo.

O prompt precisa ser AUTOCONTIDO: quem o recebe nao tem acesso ao video, ao
audio, nem a este repositorio. Tudo que o modelo precisa para escolher bem
esta no texto -- estrategia, regras, marcas de energia e a transcricao inteira
em blocos de frase com tempo.

Decisao central: os blocos listados sao exatamente as FRONTEIRAS legais de
corte (ver clipper/fronteiras.py). Ao pedir que `inicio` e `fim` coincidam com
a abertura e o fechamento de blocos, o unico corte que o modelo consegue
expressar ja e um corte legal. A validacao depois confere isso de novo, mas o
prompt e a primeira linha de defesa: e mais barato impedir o erro do que
detecta-lo.
"""

from __future__ import annotations

from typing import Any

from clipper.fronteiras import Fronteiras, blocos_para_prompt, mmss

MARCADOR_ENERGIA = "▲"
_MAX_PICOS_LISTADOS = 12
_MIN_SEGUNDOS_PICO = 2


def _agrupar_picos(picos: list[dict[str, Any]]) -> list[tuple[float, float, float]]:
    """Junta segundos de pico vizinhos em faixas, para nao listar 175 linhas."""
    if not picos:
        return []
    faixas: list[list[float]] = []
    for pico in sorted(picos, key=lambda p: float(p["t"])):
        t = float(pico["t"])
        forca = float(pico.get("rms_norm") or 0.0)
        if faixas and t - faixas[-1][1] <= 2.0:
            faixas[-1][1] = t
            faixas[-1][2] = max(faixas[-1][2], forca)
        else:
            faixas.append([t, t, forca])
    return [(a, b, f) for a, b, f in faixas if b - a >= _MIN_SEGUNDOS_PICO or f >= 0.98]


def _secao_energia(energia: dict[str, Any]) -> str:
    faixas = _agrupar_picos(energia.get("picos") or [])
    if not faixas:
        return "(sem picos de energia notaveis neste audio)"
    faixas.sort(key=lambda x: x[2], reverse=True)
    escolhidas = sorted(faixas[:_MAX_PICOS_LISTADOS], key=lambda x: x[0])
    linhas = [
        f"  {mmss(a)}–{mmss(b)}  (intensidade {f:.2f})" for a, b, f in escolhidas
    ]
    return "\n".join(linhas)


def montar(
    *,
    titulo: str,
    fronteiras: Fronteiras,
    energia: dict[str, Any],
    estrategia: str,
    n: int,
    min_s: float,
    max_s: float,
) -> str:
    """Devolve o texto completo do prompt de selecao."""
    picos_t = [float(p["t"]) for p in (energia.get("picos") or [])]
    blocos = blocos_para_prompt(fronteiras, picos_t, marcador=MARCADOR_ENERGIA)

    cabecalho = f"""\
Você é um editor de clipes. Sua tarefa é escolher os melhores trechos de um
vídeo longo para virarem clipes verticais curtos (TikTok / Reels / Shorts).

VÍDEO: {titulo}
DURAÇÃO: {mmss(fronteiras.duracao)}
BLOCOS DE TRANSCRIÇÃO: {len(fronteiras.frases)}


==================== ESTRATÉGIA (definida pelo dono do vídeo) ====================

{estrategia.strip()}


==================== REGRAS DE CORTE (obrigatórias) ====================

Uma resposta que violar qualquer regra abaixo é rejeitada por um validador
automático — não é um pedido de estilo, é um contrato.

1. DURAÇÃO: cada clipe tem que durar entre {min_s:.0f} e {max_s:.0f} segundos.

2. FRONTEIRA DE FRASE: o `inicio` de um clipe tem que ser o tempo de ABERTURA
   de um bloco listado abaixo, e o `fim` tem que ser o tempo de FECHAMENTO de
   um bloco. Você pode juntar quantos blocos consecutivos quiser — o que você
   NÃO pode é começar ou terminar no meio de um bloco, nem inventar um tempo
   que não aparece na lista. Cada bloco é uma frase inteira; cortar no meio
   entrega um clipe que começa em "que fazem casas de alto padrão".

3. SEM SOBREPOSIÇÃO: dois clipes não podem dividir nenhum segundo em comum.

4. NO MÁXIMO {n} clipe(s). Devolver MENOS é aceitável e é melhor do que
   completar a cota com trecho fraco. Devolver mais é rejeitado.

5. CADA CLIPE PRECISA SE SUSTENTAR SOZINHO, para quem nunca viu o vídeo: tem
   que abrir com contexto suficiente e fechar com uma ideia terminada.


==================== FORMATO DA RESPOSTA ====================

Responda APENAS com um array JSON. Nada antes, nada depois, sem cercas de
código, sem comentários.

[
  {{
    "inicio": "mm:ss",
    "fim": "mm:ss",
    "titulo": "título curto do clipe (até 60 caracteres)",
    "score_0_10": 8.5,
    "motivo": "por que ESTE trecho funciona como clipe (1 a 2 frases)",
    "gancho_sugerido": "frase de abertura para prender nos 2 primeiros segundos (até 90 caracteres)"
  }}
]

- `inicio` e `fim` no formato mm:ss, copiados da lista de blocos.
- `score_0_10` é um número (pode ter decimal) de 0 a 10.
- Ordene do maior `score_0_10` para o menor.


==================== COMO LER A TRANSCRIÇÃO ====================

Cada linha é um bloco:  [abertura→fechamento]{MARCADOR_ENERGIA} texto da frase

O marcador {MARCADOR_ENERGIA} indica que o áudio ali está entre os mais altos do vídeo
(ênfase, riso, exclamação, reação). Costuma marcar um momento de virada, mas
não é regra: o critério final é a estratégia lá em cima.


==================== MOMENTOS DE MAIOR ENERGIA DO ÁUDIO ====================

{_secao_energia(energia)}


==================== TRANSCRIÇÃO EM BLOCOS ====================

"""
    rodape = f"""

==================== FIM DA TRANSCRIÇÃO ====================

Escolha até {n} clipe(s) seguindo a estratégia e as regras. Responda só com o
array JSON.
"""
    return cabecalho + "\n".join(blocos) + rodape


def montar_conserto(prompt_original: str, problemas: list[str], resposta_torta: str) -> str:
    """Prompt de uma rodada de conserto, quando a resposta veio invalida.

    Nao repete a transcricao inteira: quem vai consertar ja tem o contexto na
    conversa. Repetir 40 KB de transcricao so gastaria tokens e enterraria o
    que de fato precisa mudar.
    """
    lista = "\n".join(f"  {i}. {p}" for i, p in enumerate(problemas, 1))
    return f"""\
A resposta anterior não passou no validador automático. Os problemas foram:

{lista}

Sua resposta anterior foi:

{resposta_torta.strip()}

Corrija APENAS o que está listado acima, mantendo o resto igual, e responda de
novo só com o array JSON (nada antes, nada depois, sem cercas de código).
Lembre dos limites: duração entre 20 e 90 segundos, `inicio` na abertura de um
bloco e `fim` no fechamento de um bloco, sem sobreposição entre clipes.
"""
