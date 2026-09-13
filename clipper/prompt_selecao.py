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
    max_seg: int = 3,
    max_desc: int = 200,
    max_concl: int = 90,
) -> str:
    """Devolve o texto completo do prompt de selecao (contrato v2).

    Os limites chegam por argumento em vez de serem importados de select.py
    porque este modulo nao deve depender do estagio: o prompt descreve o
    contrato, e quem o define e quem valida.
    """
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


==================== O QUE FAZ UM CLIPE BOM ====================

Um recorte não é um clipe. O que separa os dois é CONTRIBUIÇÃO EDITORIAL:

1. GANCHO — o `gancho_sugerido` aparece queimado na tela nos primeiros 3
   segundos. Ele é uma PROMESSA VERIFICÁVEL: o que ele promete tem que
   acontecer dentro deste clipe. Prometer o que o trecho não entrega é o
   defeito mais caro que existe aqui — o espectador sai antes do fim e o
   clipe inteiro se perde. Se você não consegue escrever um gancho honesto
   para o trecho, o trecho não é um clipe.

2. PAYOFF — todo clipe tem um instante em que a promessa se cumpre: a
   resposta, a virada, o número, a piada. Identifique qual é, e faça o clipe
   FECHAR nele. Não termine 20 segundos depois do payoff, com a conversa já
   andando para outro assunto; e nunca termine ANTES dele.

3. PROGRESSÃO — começo, meio e fim. Quem chega sem ter visto o vídeo precisa
   entender do que se trata sem nenhuma informação de fora.


==================== REGRAS DE CORTE (obrigatórias) ====================

Uma resposta que violar qualquer regra abaixo é rejeitada por um validador
automático — não é um pedido de estilo, é um contrato.

1. DURAÇÃO: cada clipe tem que durar entre {min_s:.0f} e {max_s:.0f} segundos.
   Num clipe de vários trechos, o que conta é a SOMA dos trechos.

2. FRONTEIRA DE FRASE: todo `inicio` tem que ser o tempo de ABERTURA de um
   bloco listado abaixo, e todo `fim` tem que ser o tempo de FECHAMENTO de um
   bloco. Vale para o clipe inteiro e para CADA segmento. Você pode juntar
   quantos blocos consecutivos quiser — o que você NÃO pode é começar ou
   terminar no meio de um bloco, nem inventar um tempo que não aparece na
   lista. Cada bloco é uma frase inteira; cortar no meio entrega um clipe que
   começa em "que fazem casas de alto padrão".

3. SEM SOBREPOSIÇÃO: dois clipes não podem dividir nenhum segundo em comum, e
   dois segmentos do MESMO clipe também não.

4. NO MÁXIMO {n} clipe(s). Devolver MENOS é aceitável e é melhor do que
   completar a cota com trecho fraco. Devolver mais é rejeitado.

5. CADA CLIPE PRECISA SE SUSTENTAR SOZINHO, para quem nunca viu o vídeo: tem
   que abrir com contexto suficiente e fechar com uma ideia terminada.


==================== TIRAR A GORDURA: `segmentos` ====================

Um clipe pode ser UM trecho contínuo ou até {max_seg} trechos separados, colados na
ordem. Os trechos separados existem para REMOVER GORDURA INTERNA:

  - preparação repetida ("então, como eu ia dizendo...");
  - deslocamento sem informação (andar até o outro lado, mexer no papel);
  - pausa longa sem função dramática.

Regras do uso:

  - só corte gordura se o clipe ficar MELHOR. Na dúvida, use um trecho só.
  - PRESERVE O SENTIDO E A SEQUÊNCIA. Os trechos entram colados na ordem em
    que você os listar, e essa lista tem que estar em ordem crescente no
    tempo: colar o fim antes do começo inverte a fala.
  - não corte no meio de um raciocínio só para encurtar. O corte tem que ser
    invisível para quem ouve — se a emenda deixar a frase sem pé, não corte.
  - no máximo {max_seg} trechos. Mais que isso deixa de ser limpeza e vira
    remontagem, e o espectador perde o fio.


==================== FORMATO DA RESPOSTA ====================

Responda APENAS com um array JSON. Nada antes, nada depois, sem cercas de
código, sem comentários.

Um clipe de UM trecho (use `inicio` e `fim`):

[
  {{
    "inicio": "mm:ss",
    "fim": "mm:ss",
    "titulo": "título curto do clipe (até 60 caracteres)",
    "score_0_10": 8.5,
    "motivo": "por que ESTE trecho funciona como clipe (1 a 2 frases)",
    "gancho_sugerido": "promessa verificável para os 3 primeiros segundos (até 90 caracteres)",
    "descricao": "opcional: descrição para o post (até {max_desc} caracteres)",
    "capa_ts": "opcional: mm:ss de um instante que renda uma boa capa",
    "conclusao": "opcional: frase de fecho na tela nos últimos 2s (até {max_concl} caracteres)"
  }}
]

Um clipe de VÁRIOS trechos (use `segmentos`, SEM `inicio`/`fim`):

[
  {{
    "segmentos": [
      {{ "inicio": "mm:ss", "fim": "mm:ss" }},
      {{ "inicio": "mm:ss", "fim": "mm:ss" }}
    ],
    "titulo": "...",
    "score_0_10": 9.0,
    "motivo": "...",
    "gancho_sugerido": "..."
  }}
]

- Use UMA das duas formas por clipe. `inicio`/`fim` JUNTO com `segmentos` é
  rejeitado — com as duas no mesmo clipe não há como saber qual você quis.
- Todos os tempos no formato mm:ss, copiados da lista de blocos.
- `score_0_10` é um número (pode ter decimal) de 0 a 10.
- Ordene do maior `score_0_10` para o menor.

Sobre os campos opcionais — preencha só quando tiver CONFIANÇA; deixar de fora
é melhor do que chutar:

- `descricao`: até {max_desc} caracteres, o texto que acompanharia o post.
- `capa_ts`: um instante que renda uma boa capa. Tem que cair DENTRO de um
  trecho que o clipe mantém — um tempo que caiu na gordura removida não
  existe no clipe final e é rejeitado.
- `conclusao`: até {max_concl} caracteres, queimada na tela nos últimos 2
  segundos. Serve para fechar a ideia, não para repetir o gancho.


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

Escolha até {n} clipe(s) seguindo a estratégia e as regras.

Antes de responder, confira cada clipe: o gancho promete o que este trecho
entrega? o corte fecha no payoff? se você usou `segmentos`, a emenda continua
fazendo sentido lida em voz alta?

Responda só com o array JSON.
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
Lembre dos limites: duração entre 20 e 90 segundos (num clipe de vários
trechos, a SOMA dos trechos), todo `inicio` na abertura de um bloco e todo
`fim` no fechamento de um bloco, sem sobreposição entre clipes nem entre
segmentos do mesmo clipe, e nunca `inicio`/`fim` junto com `segmentos`.
"""
