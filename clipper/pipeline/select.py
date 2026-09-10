"""Estagio 3: selecao dos clipes (F2).

O que este modulo faz, em uma frase: pega a transcricao ja fatiada em frases
(clipper/fronteiras.py), monta um prompt autocontido, recebe de volta um JSON
com os trechos escolhidos e so grava selecao.json depois de provar que cada
corte cai em fronteira de frase, respeita a duracao e nao invade o vizinho.

Duas fontes de resposta, e o caminho principal e o MANUAL:

  clipper select <entrada>                      -> gera prompt_selecao.txt e para
  clipper select <entrada> --resposta r.json    -> valida a resposta colada
  (com ANTHROPIC_API_KEY e usar_api=True)       -> conversa com a API sozinho

Rodar sem fonte de resposta NAO e erro: e o passo 1 do fluxo manual. O comando
grava o prompt, diz onde ele esta e devolve {"pendente": True} -- a menos que
ja exista um selecao.json feito com os MESMOS parametros e a MESMA transcricao,
caso em que ele e reaproveitado e o pipeline segue para o render.

Idempotencia: a assinatura guarda os parametros (estrategia, n, limites,
impressao da transcricao); a identidade da resposta fica no extra do estado
(resposta_digest). Assim, editar o resposta.json e repetir o mesmo comando
revalida sozinho, sem --force.

Filosofia da validacao: nao morrer no primeiro defeito. Um modelo que errou
uma duracao normalmente errou tres coisas; abortar na primeira obriga o usuario
a fazer tres viagens ao chat. Entao validar() junta TODOS os problemas, o
estagio grava um prompt_conserto.txt com a lista inteira e o usuario resolve
tudo numa rodada so.

Convencao deste arquivo: comentarios e docstrings em PT-BR sem acento;
mensagens dirigidas ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from clipper import prompt_selecao
from clipper.config import (
    Estado,
    Saida,
    chave_api_anthropic,
    escrever_json,
    ler_json,
)
from clipper.erros import ErroClipper, ErroSelecao
from clipper.fronteiras import Fronteiras, mmss, para_segundos
from clipper.registro import Cronometro, obter

ESTAGIO = "selecao"

MIN_CLIPE_S = 20.0
MAX_CLIPE_S = 90.0
TOLERANCIA_ENCAIXE_S = 15.0

# A partir de quanto um deslocamento do encaixe deixa de ser 'ajuste fino'
# e vira um aviso na tela. Com frases a cada ~2,4s (mediana medida), um
# modelo que copiou os tempos do prompt fica bem abaixo disso.
_AVISO_AJUSTE_S = 3.0

MODELOS_API = {"haiku": "claude-haiku-4-5", "sonnet": "claude-sonnet-5"}

# A flag do CLI e "--force" (nunca "--forcar"): mensagem que sugere flag
# inexistente e pior do que mensagem nenhuma.
_FLAG_FORCE = "--force"

_CAMPOS_OBRIGATORIOS = (
    "inicio",
    "fim",
    "titulo",
    "score_0_10",
    "motivo",
    "gancho_sugerido",
)

# Chaves aceitas quando o modelo embrulha o array num objeto.
_CHAVES_DE_LISTA = ("clipes", "clips", "resultado", "selecao")

# Folga numerica para comparar tempos vindos de round(x, 3).
_EPS = 1e-6

_NOME_PROMPT_CONSERTO = "prompt_conserto.txt"

# --------------------------------------------------------------------------
# Caminho de API (nao exercitado em maquina sem chave)
# --------------------------------------------------------------------------

_MAX_TOKENS_API = 16000
_TENTATIVAS_API = 3
_BASE_BACKOFF_S = 2.0
_TOKENS_SAIDA_ESTIMADOS = 2000

# USD por 1 milhao de tokens (entrada, saida).
_PRECOS_POR_MILHAO: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
}

# Structured outputs: garante que o texto devolvido e JSON valido contra este
# schema. A validacao SEMANTICA (duracao, fronteira, sobreposicao) continua
# sendo a nossa -- nenhum schema sabe onde acaba uma frase deste video.
ESQUEMA_JSON: dict[str, Any] = {
    "type": "object",
    "properties": {
        "clipes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "inicio": {"type": "string"},
                    "fim": {"type": "string"},
                    "titulo": {"type": "string"},
                    "score_0_10": {"type": "number"},
                    "motivo": {"type": "string"},
                    "gancho_sugerido": {"type": "string"},
                },
                "required": list(_CAMPOS_OBRIGATORIOS),
                "additionalProperties": False,
            },
        }
    },
    "required": ["clipes"],
    "additionalProperties": False,
}


# ==========================================================================
# Extracao do JSON da resposta
# ==========================================================================

_CERCA = re.compile(r"```[ \t]*[A-Za-z0-9_+-]*[ \t]*\r?\n(.*?)(?:```|\Z)", re.DOTALL)
_ASPAS_SOLTAS = "“”‘’\"' \t\r\n"

# Saneamento de ultimo recurso (so quando NENHUM candidato parseou): os dois
# defeitos de sintaxe mais comuns em resposta de modelo.
_ASPAS_CURVAS = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})
_VIRGULA_SOBRANDO = re.compile(r",\s*([\]}])")


def _sanear(texto: str) -> str:
    """Troca aspas curvas por retas e tira virgula sobrando antes de ] ou }."""
    return _VIRGULA_SOBRANDO.sub(r"\1", texto.translate(_ASPAS_CURVAS))


def _mais_promissor(
    erros: list[tuple[str, json.JSONDecodeError]],
) -> tuple[str | None, json.JSONDecodeError | None]:
    """Escolhe o candidato que mais parece a resposta pretendida.

    Preferencia para o primeiro recorte que comeca em '[' (a resposta pedida e
    um array); na falta dele, o candidato mais longo.
    """
    if not erros:
        return None, None
    for candidato, exc in erros:
        if candidato.startswith("["):
            return candidato, exc
    return max(erros, key=lambda par: len(par[0]))


def _sem_cercas(texto: str) -> str:
    """Devolve o maior bloco cercado por ``` se houver, senao o texto limpo."""
    blocos = [m.group(1) for m in _CERCA.finditer(texto) if m.group(1).strip()]
    if blocos:
        return max(blocos, key=len)
    if "```" in texto:
        return texto.replace("```", "")
    return texto


def _desembrulhar(dados: Any) -> Any:
    """Aceita array cru ou objeto com uma unica chave de lista."""
    if isinstance(dados, dict):
        for chave in _CHAVES_DE_LISTA:
            valor = dados.get(chave)
            if isinstance(valor, list):
                return valor
        if len(dados) == 1:
            (valor,) = dados.values()
            if isinstance(valor, list):
                return valor
    return dados


def extrair_json(texto: str) -> Any:
    """Tira o JSON de uma resposta de modelo do jeito que ela realmente chega.

    Tolera cerca ```json, texto antes ("Aqui estao os clipes:"), texto depois,
    BOM e aspas curvas em volta do bloco. A ordem das tentativas importa: o
    texto inteiro primeiro (caso ja seja JSON puro), depois TODOS os recortes
    entre colchetes, e so entao os recortes de chaves -- assim uma resposta com
    prosa em volta de um array (a prosa costuma citar blocos no formato
    [mm:ss->mm:ss], entao colchete no meio do texto e o caso comum) nao e
    confundida com um objeto solto que apareceu no meio da conversa.

    Se nenhum candidato parseia, tenta UM saneamento do candidato mais
    promissor (aspas curvas e virgula sobrando antes de ] ou }) antes de
    desistir.
    """
    if not isinstance(texto, str) or not texto.strip():
        raise ErroSelecao(
            "a resposta do modelo está vazia.",
            sugestao=(
                "cole no arquivo de resposta apenas o array JSON que o modelo "
                "devolveu e repita o comando com  --resposta <arquivo>."
            ),
        )

    log = obter()
    limpo = texto.replace("﻿", "").strip()
    candidatos: list[str] = []
    # Recortes de chaves ficam numa lista separada e so entram no fim: um
    # array de UM clipe com prosa em volta casaria com eles por acidente.
    de_chaves: list[str] = []

    def _acrescentar(alvo: list[str], recorte: str) -> None:
        recorte = recorte.strip()
        if recorte and recorte not in candidatos and recorte not in de_chaves:
            alvo.append(recorte)

    def _juntar(bruto: str) -> None:
        bruto = bruto.strip()
        if not bruto:
            return
        for variante in (bruto, bruto.strip(_ASPAS_SOLTAS)):
            _acrescentar(candidatos, variante)
        # Do primeiro '[' ao ultimo ']' e, se a prosa em volta sujou esse
        # recorte, do ULTIMO '[' ao ultimo ']' (o array de verdade costuma ser
        # a ultima coisa da resposta).
        fecha = bruto.rfind("]")
        for i in (bruto.find("["), bruto.rfind("[")):
            if i != -1 and fecha > i:
                _acrescentar(candidatos, bruto[i : fecha + 1])
        i, j = bruto.find("{"), bruto.rfind("}")
        if i != -1 and j > i:
            _acrescentar(de_chaves, bruto[i : j + 1])

    _juntar(_sem_cercas(limpo))
    _juntar(limpo)
    candidatos.extend(de_chaves)

    erros: list[tuple[str, json.JSONDecodeError]] = []
    for candidato in candidatos:
        try:
            return _desembrulhar(json.loads(candidato))
        except json.JSONDecodeError as exc:
            erros.append((candidato, exc))
        except ValueError:
            continue

    # Ultima chance antes de desistir: sanear o candidato mais promissor.
    promissor, erro = _mais_promissor(erros)
    if promissor is not None:
        saneado = _sanear(promissor)
        if saneado != promissor:
            try:
                dados = _desembrulhar(json.loads(saneado))
            except (json.JSONDecodeError, ValueError):
                pass
            else:
                log.debug(
                    "extrair_json: precisei sanear a resposta (aspas curvas e/ou "
                    "vírgula sobrando antes de ']' ou '}') para conseguir parsear."
                )
                return dados

    detalhe = limpo[:1000]
    if erro is not None:
        detalhe = (
            f"o JSON quebra na linha {erro.lineno}, coluna {erro.colno}: {erro.msg}\n"
            f"---\n{detalhe}"
        )
    raise ErroSelecao(
        "não encontrei nenhum JSON válido na resposta do modelo.",
        detalhe=detalhe,
        sugestao=(
            "as duas causas mais comuns são vírgula sobrando antes de ']' ou '}' e "
            "aspas curvas (“ ” em vez de \"); corrija isso no ponto indicado acima. "
            "Se houver texto em volta, deixe no arquivo APENAS o array JSON — de "
            "'[' a ']', sem cercas de código — e repita  "
            "clipper select <entrada> --resposta <arquivo>."
        ),
    )


# ==========================================================================
# Validacao
# ==========================================================================


def _rotulo(posicao: int, item: Any) -> str:
    """'clipe 3 ("titulo")' -- o usuario precisa saber de QUAL clipe se fala."""
    titulo = ""
    if isinstance(item, dict):
        bruto = item.get("titulo")
        if isinstance(bruto, str) and bruto.strip():
            titulo = bruto.strip()
    return f'clipe {posicao} ("{titulo}")' if titulo else f"clipe {posicao}"


def _texto_nao_vazio(valor: Any) -> str | None:
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def _para_score(valor: Any) -> float | None:
    """Aceita 8, 8.5 e "8.5"; recusa booleano e qualquer coisa fora de 0..10."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        nota = float(valor)
    elif isinstance(valor, str):
        try:
            nota = float(valor.strip().replace(",", "."))
        except ValueError:
            return None
    else:
        return None
    if math.isnan(nota) or math.isinf(nota):
        return None
    return nota


def _energia_media(energia: dict[str, Any], inicio: float, fim: float) -> float:
    """Media de rms_norm nas janelas que cobrem [inicio, fim)."""
    valores = energia.get("rms_norm") if isinstance(energia, dict) else None
    if not isinstance(valores, list) or not valores:
        return 0.0
    janela = float(energia.get("janela_s") or 1.0) or 1.0
    i0 = max(0, int(inicio // janela))
    i1 = min(len(valores), max(i0 + 1, int(math.ceil(fim / janela))))
    fatia = [float(v) for v in valores[i0:i1] if isinstance(v, (int, float))]
    if not fatia:
        return 0.0
    return round(sum(fatia) / len(fatia), 3)


def _conferir_encaixe(
    fronteiras: Fronteiras,
    inicio: float,
    fim: float,
    min_s: float,
    max_s: float,
    onde: str,
) -> None:
    """Invariante do clipper, nao do modelo: falhar aqui e BUG nosso."""
    duracao = fim - inicio
    if not fronteiras.e_inicio_de_frase(inicio):
        raise ErroClipper(
            f"bug interno do clipper: {onde} produziu um início ({mmss(inicio)}) "
            "que não é abertura de frase.",
            sugestao=(
                "isto não é erro do modelo nem seu. Guarde o out/<slug>/ e o "
                "clipper.log e abra um issue — o encaixe em fronteira quebrou."
            ),
        )
    if not fronteiras.e_fim_de_frase(fim):
        raise ErroClipper(
            f"bug interno do clipper: {onde} produziu um fim ({mmss(fim)}) "
            "que não é fechamento de frase.",
            sugestao=(
                "isto não é erro do modelo nem seu. Guarde o out/<slug>/ e o "
                "clipper.log e abra um issue — o encaixe em fronteira quebrou."
            ),
        )
    if duracao < min_s - _EPS or duracao > max_s + _EPS:
        raise ErroClipper(
            f"bug interno do clipper: {onde} produziu um clipe de {duracao:.1f}s, "
            f"fora do limite de {min_s:.0f}–{max_s:.0f}s que ele mesmo aplicou.",
            sugestao=(
                "isto não é erro do modelo nem seu. Guarde o out/<slug>/ e o "
                "clipper.log e abra um issue."
            ),
        )
    # A janela [0, duracao do audio] vale para o que VAI SER GRAVADO, nao so
    # para o que o modelo pediu: o encaixe anda ate `tolerancia` e pode passar
    # do fim da midia se a transcricao tiver cauda transbordada.
    if inicio < -_EPS or fim > fronteiras.duracao + _EPS:
        raise ErroClipper(
            f"bug interno do clipper: {onde} produziu o trecho {mmss(inicio)}–"
            f"{mmss(fim)} ({inicio:.2f}s–{fim:.2f}s), fora da janela do áudio "
            f"(0–{fronteiras.duracao:.2f}s).",
            sugestao=(
                "isto não é erro do modelo nem seu. Costuma ser transcrição com "
                "timestamp além do fim do áudio: refaça  clipper transcribe "
                f"<entrada> {_FLAG_FORCE}  e, se repetir, guarde o out/<slug>/ e o "
                "clipper.log e abra um issue."
            ),
        )


def validar(
    dados: Any,
    fronteiras: Fronteiras,
    energia: dict,
    *,
    n: int,
    min_s: float = MIN_CLIPE_S,
    max_s: float = MAX_CLIPE_S,
    tolerancia: float = TOLERANCIA_ENCAIXE_S,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Confere a resposta do modelo e devolve (clipes_validados, problemas).

    Nao levanta na primeira falha: junta a lista inteira, porque ela vira um
    unico pedido de conserto. As unicas excecoes levantadas aqui sao
    ErroClipper -- e elas significam que quem errou foi o clipper.
    """
    log = obter()
    problemas: list[str] = []

    if not isinstance(dados, list):
        tipo = type(dados).__name__
        um_clipe_solto = isinstance(dados, dict) and all(
            dados.get(campo) is not None for campo in _CAMPOS_OBRIGATORIOS
        )
        if um_clipe_solto:
            # Nao acuse o usuario de nao ter mandado uma lista: o mais provavel
            # e que ele mandou, e o texto em volta do array e que atrapalhou.
            problemas.append(
                "veio UM clipe solto (objeto JSON), não a lista. Se no arquivo de "
                "resposta houver texto explicativo em volta do array, apague-o e "
                "deixe apenas de '[' a ']'; se o modelo mandou mesmo um clipe só, "
                "embrulhe-o em '[' e ']'."
            )
        else:
            problemas.append(
                f"a resposta não é um array JSON de clipes (veio um {tipo}). "
                "Responda com uma lista, de '[' a ']'."
            )
        return [], problemas
    if not dados:
        problemas.append(
            "a resposta veio como um array vazio: nenhum clipe foi escolhido. "
            f"Escolha de 1 a {n} trecho(s) que caibam em {min_s:.0f}–{max_s:.0f}s."
        )
        return [], problemas

    aprovados: list[dict[str, Any]] = []

    for posicao, item in enumerate(dados, 1):
        rotulo = _rotulo(posicao, item)

        if not isinstance(item, dict):
            problemas.append(
                f"{rotulo}: cada item do array tem que ser um objeto JSON com os "
                f"campos {', '.join(_CAMPOS_OBRIGATORIOS)} (veio um "
                f"{type(item).__name__})."
            )
            continue

        faltando = [c for c in _CAMPOS_OBRIGATORIOS if item.get(c) is None]
        if faltando:
            problemas.append(
                f"{rotulo}: faltou preencher {', '.join(faltando)}. Repita o clipe "
                "com todos os campos do formato pedido."
            )

        # Campos de texto e nota: conferidos mesmo quando os tempos falharam,
        # para o pedido de conserto sair completo de uma vez.
        titulo = _texto_nao_vazio(item.get("titulo"))
        if "titulo" not in faltando and titulo is None:
            problemas.append(f"{rotulo}: o `titulo` tem que ser um texto não vazio.")
        motivo = _texto_nao_vazio(item.get("motivo"))
        if "motivo" not in faltando and motivo is None:
            problemas.append(
                f"{rotulo}: o `motivo` tem que ser um texto não vazio explicando "
                "por que o trecho funciona como clipe."
            )
        gancho = _texto_nao_vazio(item.get("gancho_sugerido"))
        if "gancho_sugerido" not in faltando and gancho is None:
            problemas.append(
                f"{rotulo}: o `gancho_sugerido` tem que ser um texto não vazio."
            )
        score = _para_score(item.get("score_0_10"))
        if "score_0_10" not in faltando:
            if score is None:
                problemas.append(
                    f"{rotulo}: `score_0_10` tem que ser um número "
                    f"(veio {item.get('score_0_10')!r})."
                )
            elif not (0.0 <= score <= 10.0):
                problemas.append(
                    f"{rotulo}: `score_0_10` é uma nota de 0 a 10 e veio {score:g}. "
                    "Use a escala pedida."
                )
                score = None

        if "inicio" in faltando or "fim" in faltando:
            continue

        try:
            inicio_pedido = para_segundos(item["inicio"])
        except (ValueError, TypeError):
            problemas.append(
                f"{rotulo}: não entendi o `inicio` {item['inicio']!r}. Use mm:ss "
                "(ou segundos), copiado da lista de blocos."
            )
            inicio_pedido = None
        try:
            fim_pedido = para_segundos(item["fim"])
        except (ValueError, TypeError):
            problemas.append(
                f"{rotulo}: não entendi o `fim` {item['fim']!r}. Use mm:ss "
                "(ou segundos), copiado da lista de blocos."
            )
            fim_pedido = None
        if inicio_pedido is None or fim_pedido is None:
            continue

        if fim_pedido <= inicio_pedido:
            problemas.append(
                f"{rotulo}: o `fim` ({mmss(fim_pedido)}) não vem depois do `inicio` "
                f"({mmss(inicio_pedido)})."
            )
            continue
        fora = [
            nome
            for nome, valor in (("inicio", inicio_pedido), ("fim", fim_pedido))
            if valor < -_EPS or valor > fronteiras.duracao + _EPS
        ]
        if fora:
            verbo = "cai" if len(fora) == 1 else "caem"
            problemas.append(
                f"{rotulo}: `{'` e `'.join(fora)}` {verbo} fora do vídeo, que tem "
                f"{mmss(fronteiras.duracao)}. Use apenas tempos que aparecem na "
                "lista de blocos."
            )
            continue

        try:
            encaixe = fronteiras.encaixar(
                inicio_pedido,
                fim_pedido,
                min_s=min_s,
                max_s=max_s,
                tolerancia=tolerancia,
            )
        except ErroSelecao as exc:
            recado = f"{rotulo}: {exc.mensagem}"
            if exc.sugestao:
                recado += f" {exc.sugestao}"
            problemas.append(recado)
            continue

        _conferir_encaixe(
            fronteiras, encaixe.inicio, encaixe.fim, min_s, max_s, "o encaixe"
        )

        if titulo is None or motivo is None or gancho is None or score is None:
            # Os tempos estao bons, mas o clipe nao esta completo: ja virou
            # problema acima e nao entra no resultado.
            continue

        aprovados.append(
            {
                "rotulo": rotulo,
                "inicio": encaixe.inicio,
                "fim": encaixe.fim,
                "duracao": round(encaixe.duracao, 3),
                "inicio_pedido": round(inicio_pedido, 3),
                "fim_pedido": round(fim_pedido, 3),
                "frase_inicio": encaixe.frase_inicio,
                "frase_fim": encaixe.frase_fim,
                "palavra_inicio": encaixe.palavra_inicio,
                "palavra_fim": encaixe.palavra_fim,
                "ajuste_inicio": encaixe.ajuste_inicio,
                "ajuste_fim": encaixe.ajuste_fim,
                "titulo": titulo,
                "score_0_10": round(score, 3),
                "motivo": motivo,
                "gancho_sugerido": gancho,
                "texto": fronteiras.texto_entre(encaixe.inicio, encaixe.fim),
                "energia_media": _energia_media(energia, encaixe.inicio, encaixe.fim),
            }
        )

        # O encaixe pode esticar bastante um pedido fora de medida (um clipe de
        # 8s vira 20s porque esse e o minimo). Isso e legitimo -- continua em
        # fronteira de frase e dentro do limite --, mas nao pode acontecer em
        # silencio: o titulo, o motivo e o gancho foram escritos para o trecho
        # que o modelo pediu, e quem le o relatorio precisa saber que o trecho
        # entregue e outro.
        maior_ajuste = max(abs(encaixe.ajuste_inicio), abs(encaixe.ajuste_fim))
        if maior_ajuste >= _AVISO_AJUSTE_S:
            obter().warning(
                f"   atenção: {rotulo} foi movido para caber em fronteira de "
                f"frase e no limite de {min_s:.0f}–{max_s:.0f}s — pedido "
                f"{mmss(inicio_pedido)}–{mmss(fim_pedido)} "
                f"({fim_pedido - inicio_pedido:.0f}s), entregue "
                f"{mmss(encaixe.inicio)}–{mmss(encaixe.fim)} "
                f"({encaixe.duracao:.0f}s). Confira se o título e o gancho "
                "ainda descrevem o trecho."
            )

    if len(dados) > n:
        problemas.append(
            f"vieram {len(dados)} clipes e o limite é {n}. Devolva no máximo {n}, "
            "descartando os de menor score."
        )

    # ---- sobreposicao: tentar consertar sozinho antes de reclamar -----------
    aprovados.sort(key=lambda c: c["inicio"])
    resultado: list[dict[str, Any]] = []
    for clipe in aprovados:
        anterior = resultado[-1] if resultado else None
        if anterior is not None and clipe["inicio"] < anterior["fim"] - _EPS:
            frase = fronteiras.primeiro_inicio_apos(anterior["fim"])
            nova_duracao = clipe["fim"] - frase.inicio if frase is not None else 0.0
            # Teto do conserto: o mesmo da tolerancia de encaixe. Andar mais do
            # que isso reescreveria por baixo dos panos um trecho que o titulo,
            # o motivo e o gancho do modelo nao descrevem mais.
            desvio = (
                abs(frase.inicio - clipe["inicio_pedido"])
                if frase is not None
                else float("inf")
            )
            cabe = (
                frase is not None
                and frase.inicio >= anterior["fim"] - _EPS
                and frase.inicio < clipe["fim"]
                and min_s - _EPS <= nova_duracao <= max_s + _EPS
            )
            if cabe and desvio <= tolerancia + _EPS:
                log.info(
                    f"   sobreposição desfeita sozinha: {clipe['rotulo']} agora "
                    f"começa em {mmss(frase.inicio)} (era {mmss(clipe['inicio'])}), "
                    f"ficando com {nova_duracao:.0f}s."
                )
                clipe.update(
                    inicio=frase.inicio,
                    duracao=round(nova_duracao, 3),
                    frase_inicio=frase.indice,
                    palavra_inicio=frase.palavra_inicio,
                    ajuste_inicio=round(frase.inicio - clipe["inicio_pedido"], 3),
                    texto=fronteiras.texto_entre(frase.inicio, clipe["fim"]),
                    energia_media=_energia_media(energia, frase.inicio, clipe["fim"]),
                )
                _conferir_encaixe(
                    fronteiras,
                    clipe["inicio"],
                    clipe["fim"],
                    min_s,
                    max_s,
                    "o conserto de sobreposição",
                )
            elif cabe:
                problemas.append(
                    f"{anterior['rotulo']} e {clipe['rotulo']} se sobrepõem "
                    f"({mmss(anterior['inicio'])}–{mmss(anterior['fim'])} contra "
                    f"{mmss(clipe['inicio'])}–{mmss(clipe['fim'])}). Para separar, o "
                    f"início do {clipe['rotulo']} teria que andar {desvio:.0f}s, e o "
                    f"limite é {tolerancia:.0f}s — o título, o motivo e o gancho "
                    "deixariam de descrever o trecho. Escolha outro trecho para um "
                    "dos dois, sem nenhum segundo em comum."
                )
                continue
            else:
                problemas.append(
                    f"{anterior['rotulo']} e {clipe['rotulo']} se sobrepõem "
                    f"({mmss(anterior['inicio'])}–{mmss(anterior['fim'])} contra "
                    f"{mmss(clipe['inicio'])}–{mmss(clipe['fim'])}) e não dá para "
                    "separar sem furar a duração. Escolha outro trecho para um dos "
                    "dois, sem nenhum segundo em comum."
                )
                continue
        resultado.append(clipe)

    # ---- invariantes finais: falhar aqui e bug do clipper -------------------
    for clipe in resultado:
        _conferir_encaixe(
            fronteiras, clipe["inicio"], clipe["fim"], min_s, max_s, "a validação"
        )
    for anterior, seguinte in zip(resultado, resultado[1:]):
        if seguinte["inicio"] < anterior["fim"] - _EPS:
            raise ErroClipper(
                "bug interno do clipper: a validação devolveu clipes sobrepostos "
                f"({mmss(anterior['inicio'])}–{mmss(anterior['fim'])} e "
                f"{mmss(seguinte['inicio'])}–{mmss(seguinte['fim'])}).",
                sugestao=(
                    "isto não é erro do modelo nem seu. Guarde o out/<slug>/ e o "
                    "clipper.log e abra um issue."
                ),
            )

    return resultado, problemas


# ==========================================================================
# Leitura das entradas e montagem do prompt
# ==========================================================================


def _exigir_entradas(saida: Saida) -> None:
    faltando = [
        caminho
        for caminho in (saida.transcricao_json, saida.energia_json)
        if not caminho.exists() or caminho.stat().st_size == 0
    ]
    if faltando:
        nomes = ", ".join(c.name for c in faltando)
        raise ErroSelecao(
            f"a seleção precisa da transcrição pronta, e falta {nomes} em {saida.base}.",
            sugestao=(
                "rode a transcrição primeiro:  clipper transcribe <entrada>   "
                "(ela gera transcricao.json e energia.json)."
            ),
        )


def _ler_entrada(caminho: Path, o_que: str) -> Any:
    try:
        return ler_json(caminho)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ErroSelecao(
            f"não consegui ler {o_que} em {caminho}: {exc}",
            sugestao=(
                f"o arquivo está corrompido ou pela metade. Refaça:  "
                f"clipper transcribe <entrada> {_FLAG_FORCE}"
            ),
        ) from exc


def _titulo_do_video(saida: Saida) -> str:
    """Titulo real do video (fonte.json) ou, na falta dele, o slug."""
    try:
        fonte = ler_json(saida.fonte_info_json)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return saida.slug
    if isinstance(fonte, dict):
        origem = fonte.get("origem")
        if isinstance(origem, dict):
            titulo = _texto_nao_vazio(origem.get("titulo"))
            if titulo:
                return titulo
    return saida.slug


def _escrever_texto(caminho: Path, conteudo: str) -> Path:
    """Escrita atomica em utf-8 sem BOM, quebras \\n (espelha escrever_json)."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(conteudo, encoding="utf-8", newline="\n")
    tmp.replace(caminho)
    return caminho


def _gravar_prompt(caminho: Path, prompt: str, forcar: bool) -> bool:
    """Grava so quando muda (ou com --force). Devolve True se escreveu."""
    try:
        atual = caminho.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        atual = None
    if not forcar and atual == prompt:
        return False
    _escrever_texto(caminho, prompt)
    return True


def _impressao_transcricao(saida: Saida) -> dict[str, Any]:
    """Identidade da transcricao, para entrar na assinatura de idempotencia.

    Transcricao nova (outro modelo de whisper, outro video no mesmo slug) muda
    as fronteiras de frase e, portanto, invalida a selecao sem ninguem precisar
    orquestrar isso no cli. Se o arquivo nao existe, devolve {}: a assinatura
    fica diferente da gravada e _exigir_entradas da a mensagem certa em seguida.
    """
    try:
        st = saida.transcricao_json.stat()
    except OSError:
        return {}
    return {"transcricao_bytes": int(st.st_size), "transcricao_mtime": int(st.st_mtime)}


def _origem_rotulo(resposta_manual: str | Path | None, modelo_id: str | None) -> str:
    if resposta_manual is not None:
        return f"manual: {Path(resposta_manual).name}"
    return f"api: {modelo_id}"


def _digest_resposta(texto: str) -> str:
    """Identidade do CONTEUDO da resposta (o nome do arquivo nao serve).

    Vai para o extra do estado, nao para a assinatura: a assinatura descreve os
    PARAMETROS da selecao; a resposta e a resposta, e e conferida a parte.
    """
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def _ler_resposta_manual(caminho: str | Path) -> str:
    alvo = Path(caminho)
    if alvo.is_dir():
        # Remediacao diferente das outras duas: nao adianta criar o arquivo nem
        # colar conteudo — o caminho aponta para o lugar errado.
        raise ErroSelecao(
            f"o --resposta aponta para uma pasta ('{alvo}'), não para um arquivo.",
            sugestao=(
                "o --resposta precisa apontar para o ARQUIVO onde você colou o array "
                f"JSON, por exemplo  --resposta {alvo / 'resposta.json'}"
            ),
        )
    try:
        texto = alvo.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ErroSelecao(
            f"não encontrei o arquivo de resposta '{alvo}'.",
            sugestao=(
                "confira o caminho (ou crie o arquivo): é nele que você cola a "
                "resposta do modelo — o array JSON — e o comando é  "
                "clipper select <entrada> --resposta <arquivo>."
            ),
        ) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ErroSelecao(
            f"não consegui ler o arquivo de resposta '{alvo}': {exc}",
            sugestao=(
                "salve a resposta como texto UTF-8 (.json ou .txt) e repita  "
                "clipper select <entrada> --resposta <arquivo>."
            ),
        ) from exc
    if not texto.strip():
        raise ErroSelecao(
            f"o arquivo de resposta '{alvo}' está vazio.",
            sugestao=(
                "cole nele o array JSON que o modelo devolveu e repita  "
                "clipper select <entrada> --resposta <arquivo>."
            ),
        )
    return texto


def _erro_de_validacao(
    saida: Saida, prompt: str, problemas: list[str], resposta: str
) -> ErroSelecao:
    """Grava o pedido de conserto e devolve o erro que o Bruno vai ler."""
    caminho = saida.base / _NOME_PROMPT_CONSERTO
    _escrever_texto(
        caminho, prompt_selecao.montar_conserto(prompt, problemas, resposta)
    )
    numerados = "\n".join(f"{i}. {p}" for i, p in enumerate(problemas, 1))
    return ErroSelecao(
        f"a resposta do modelo não passou na validação "
        f"({len(problemas)} problema(s))",
        detalhe=numerados,
        sugestao=(
            f"o pedido de conserto já está gravado em {caminho} — cole esse arquivo "
            "no MESMO chat, salve a nova resposta por cima do seu arquivo de "
            "resposta e repita  clipper select <entrada> --resposta <arquivo>."
        ),
    )


# ==========================================================================
# Caminho de API
# ==========================================================================


def _exigir_chave() -> None:
    if chave_api_anthropic() is None:
        raise ErroSelecao(
            "não há ANTHROPIC_API_KEY no ambiente, então não dá para chamar a API.",
            sugestao=(
                "o modo manual é o padrão e não precisa de chave: rode  "
                "clipper select <entrada>  (sem --api), leve o prompt_selecao.txt "
                "a um chat e volte com  clipper select <entrada> --resposta resposta.json."
            ),
        )


def _carregar_sdk():
    """Import tardio: quem nunca usa a API nao paga o custo de importar o SDK."""
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise ErroSelecao(
            "o pacote 'anthropic' não está instalado neste ambiente.",
            sugestao=(
                "instale com  pip install anthropic  — ou fique no modo manual, "
                "que não precisa dele:  clipper select <entrada>  e depois  "
                "--resposta resposta.json."
            ),
        ) from exc
    return anthropic


def _modelo_id(modelo: str) -> str:
    try:
        return MODELOS_API[modelo]
    except KeyError:
        raise ErroSelecao(
            f"não conheço o modelo '{modelo}'.",
            sugestao=(
                "use um destes:  " + ", ".join(sorted(MODELOS_API)) + "  "
                "(ex.:  clipper select <entrada> --modelo haiku)."
            ),
        ) from None


def _texto_da_resposta(resposta: Any) -> str:
    for bloco in getattr(resposta, "content", None) or []:
        if getattr(bloco, "type", None) == "text":
            return str(getattr(bloco, "text", "") or "")
    raise ErroSelecao(
        "a API respondeu sem nenhum bloco de texto.",
        sugestao=(
            "tente de novo; se repetir, use o modo manual:  clipper select "
            "<entrada>  e depois  --resposta resposta.json."
        ),
    )


def _logar_estimativa(client: Any, modelo_id: str, prompt: str) -> None:
    """Estimativa de custo -- e ESTIMATIVA, e o log diz isso em letras."""
    log = obter()
    tokens: int | None = None
    try:
        contagem = client.messages.count_tokens(
            model=modelo_id, messages=[{"role": "user", "content": prompt}]
        )
        tokens = int(getattr(contagem, "input_tokens", 0) or 0) or None
    except Exception:  # contagem e opcional: nao pode derrubar a selecao
        log.debug("count_tokens indisponível; estimando por len(prompt)/4.")
    aproximado = tokens is None
    if tokens is None:
        tokens = int(len(prompt) / 4)
    preco_entrada, preco_saida = _PRECOS_POR_MILHAO.get(modelo_id, (0.0, 0.0))
    custo = (tokens / 1e6) * preco_entrada + (
        _TOKENS_SAIDA_ESTIMADOS / 1e6
    ) * preco_saida
    origem = "aproximado por len(prompt)/4" if aproximado else "contado pela API"
    log.info(
        f"   ESTIMATIVA de custo (não é cobrança): ~{tokens} tokens de entrada "
        f"({origem}) + ~{_TOKENS_SAIDA_ESTIMADOS} de saída em {modelo_id} "
        f"≈ US$ {custo:.4f}."
    )


def _enviar(client: Any, anthropic: Any, mensagens: list[dict[str, Any]], modelo_id: str) -> str:
    """Uma ida a API, com 3 tentativas para falhas que valem retentar.

    4xx nao repete (exceto 429): tentar de novo uma chave invalida so gasta
    tempo do usuario. Nenhuma excecao do SDK sai daqui crua.
    """
    log = obter()
    ultimo: Exception | None = None
    motivo = ""
    for tentativa in range(1, _TENTATIVAS_API + 1):
        try:
            resposta = client.messages.create(
                model=modelo_id,
                max_tokens=_MAX_TOKENS_API,
                messages=mensagens,
                output_config={
                    "format": {"type": "json_schema", "schema": ESQUEMA_JSON}
                },
            )
            return _texto_da_resposta(resposta)
        except anthropic.AuthenticationError as exc:
            raise ErroSelecao(
                "a API recusou a chave (401).",
                detalhe=str(exc),
                sugestao=(
                    "confira o valor de ANTHROPIC_API_KEY, ou fique no modo "
                    "manual:  clipper select <entrada>  e depois  "
                    "--resposta resposta.json."
                ),
            ) from exc
        except anthropic.PermissionDeniedError as exc:
            raise ErroSelecao(
                "a chave não tem permissão para usar este modelo (403).",
                detalhe=str(exc),
                sugestao=(
                    "use outro modelo (  --modelo haiku  ) ou libere o acesso no "
                    "console da Anthropic."
                ),
            ) from exc
        except anthropic.NotFoundError as exc:
            raise ErroSelecao(
                f"a API não conhece o modelo '{modelo_id}' (404).",
                detalhe=str(exc),
                sugestao=(
                    "escolha um modelo disponível:  --modelo "
                    + " | --modelo ".join(sorted(MODELOS_API))
                ),
            ) from exc
        except anthropic.RateLimitError as exc:
            ultimo, motivo = exc, "limite de requisições (429)"
        except anthropic.APIStatusError as exc:
            status = int(getattr(exc, "status_code", 0) or 0)
            if status < 500:
                raise ErroSelecao(
                    f"a API recusou a requisição (HTTP {status}).",
                    detalhe=str(exc),
                    sugestao=(
                        "não adianta repetir: o pedido foi rejeitado. Use o modo "
                        "manual:  clipper select <entrada>  e depois  "
                        "--resposta resposta.json."
                    ),
                ) from exc
            ultimo, motivo = exc, f"erro {status} no servidor da Anthropic"
        except anthropic.APIConnectionError as exc:
            ultimo, motivo = exc, "falha de conexão com a API"
        except anthropic.AnthropicError as exc:  # rede de segurança do SDK
            raise ErroSelecao(
                "a chamada à API falhou.",
                detalhe=str(exc),
                sugestao=(
                    "use o modo manual enquanto isso:  clipper select <entrada>  "
                    "e depois  --resposta resposta.json."
                ),
            ) from exc

        if tentativa < _TENTATIVAS_API:
            espera = _BASE_BACKOFF_S**tentativa + random.uniform(0.0, 1.0)
            log.warning(
                f"   {motivo}; tentativa {tentativa}/{_TENTATIVAS_API} falhou. "
                f"Aguardando {espera:.1f}s antes de tentar de novo."
            )
            time.sleep(espera)

    raise ErroSelecao(
        f"a API não respondeu em {_TENTATIVAS_API} tentativas ({motivo}).",
        detalhe=str(ultimo) if ultimo else None,
        sugestao=(
            "tente mais tarde, ou resolva agora pelo modo manual:  clipper select "
            "<entrada>  e depois  --resposta resposta.json."
        ),
    )


def _selecao_via_api(
    *,
    prompt: str,
    modelo_id: str,
    fronteiras: Fronteiras,
    energia: dict[str, Any],
    n: int,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Conversa com a API e faz UMA rodada de conserto se precisar."""
    log = obter()
    _exigir_chave()
    anthropic = _carregar_sdk()
    client = anthropic.Anthropic()  # le a chave do ambiente sozinho
    _logar_estimativa(client, modelo_id, prompt)

    mensagens: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    texto = _enviar(client, anthropic, mensagens, modelo_id)
    clipes, problemas = validar(
        extrair_json(texto), fronteiras, energia, n=n
    )
    if not problemas:
        return texto, clipes, problemas

    log.info(
        f"   a primeira resposta teve {len(problemas)} problema(s); pedindo "
        "conserto na mesma conversa (1 rodada)."
    )
    conserto = prompt_selecao.montar_conserto(prompt, problemas, texto)
    mensagens = [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": texto},
        {"role": "user", "content": conserto},
    ]
    texto = _enviar(client, anthropic, mensagens, modelo_id)
    clipes, problemas = validar(extrair_json(texto), fronteiras, energia, n=n)
    return texto, clipes, problemas


# ==========================================================================
# Estagio
# ==========================================================================


@dataclass
class _Preparado:
    """O que o corpo cronometrado do estagio devolve."""

    atalho: dict[str, Any] | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    assinatura: dict[str, Any] = field(default_factory=dict)
    resumo: dict[str, Any] = field(default_factory=dict)


def selecionar(
    saida: Saida,
    estado: Estado,
    *,
    estrategia: str,
    n: int = 5,
    modelo: str = "haiku",
    forcar: bool = False,
    resposta_manual: str | Path | None = None,
    usar_api: bool = False,
) -> dict[str, Any]:
    """Escolhe os melhores trechos e grava selecao.json.

    Sem resposta_manual e sem usar_api: se ja houver selecao.json compativel,
    reaproveita e devolve {"pendente": False, ..., "reaproveitado": True};
    senao, apenas gera o prompt e devolve {"pendente": True} -- que e o passo 1
    do fluxo manual, nao um erro.
    """
    log = obter()
    crono = Cronometro(ESTAGIO)
    with crono:
        pronto = _preparar(
            saida,
            estado,
            estrategia=estrategia,
            n=n,
            modelo=modelo,
            forcar=forcar,
            resposta_manual=resposta_manual,
            usar_api=usar_api,
        )
    if pronto.atalho is not None:
        return pronto.atalho

    escrever_json(saida.selecao_json, pronto.payload)
    estado.marcar(
        ESTAGIO, pronto.assinatura, segundos=crono.segundos, extra=pronto.resumo
    )
    log.info(
        f"   {pronto.resumo['clipes']} clipe(s), "
        f"{pronto.resumo['duracao_total']:.0f}s no total, score médio "
        f"{pronto.resumo['score_medio']:.1f} — {saida.selecao_json.name} gravado."
    )
    return {**pronto.resumo, "reaproveitado": False}


def _preparar(
    saida: Saida,
    estado: Estado,
    *,
    estrategia: str,
    n: int,
    modelo: str,
    forcar: bool,
    resposta_manual: str | Path | None,
    usar_api: bool,
) -> _Preparado:
    log = obter()

    _exigir_entradas(saida)
    transcricao = _ler_entrada(saida.transcricao_json, "a transcrição")
    energia = _ler_entrada(saida.energia_json, "a curva de energia")
    if not isinstance(transcricao, dict) or not isinstance(energia, dict):
        raise ErroSelecao(
            "transcricao.json ou energia.json não têm o formato esperado.",
            sugestao=f"refaça:  clipper transcribe <entrada> {_FLAG_FORCE}",
        )

    fronteiras = Fronteiras.de_transcricao(transcricao)
    titulo = _titulo_do_video(saida)

    prompt = prompt_selecao.montar(
        titulo=titulo,
        fronteiras=fronteiras,
        energia=energia,
        estrategia=estrategia,
        n=n,
        min_s=MIN_CLIPE_S,
        max_s=MAX_CLIPE_S,
    )
    saida.criar_dirs()
    if _gravar_prompt(saida.prompt_selecao_txt, prompt, forcar):
        log.info(
            f"   prompt de seleção gravado em {saida.prompt_selecao_txt} "
            f"({len(prompt)} caracteres, {len(fronteiras.frases)} blocos)."
        )

    if resposta_manual is not None and usar_api:
        log.warning(
            "   --resposta e --api foram passados juntos: vou usar o arquivo de "
            "resposta e ignorar o --api (nenhuma chamada será cobrada)."
        )
    modelo_id = _modelo_id(modelo) if (usar_api and resposta_manual is None) else None

    tem_fonte = resposta_manual is not None or usar_api
    # A assinatura descreve os PARAMETROS que definem o conteudo da selecao. O
    # rotulo de origem NAO entra: se ele entrasse, uma chamada sem fonte (o
    # 'clipper run' depois de um 'select --resposta') nunca casaria com o que
    # esta gravado e o render jamais seria alcancado.
    assinatura = {
        "estrategia": estrategia,
        "n": n,
        "min_s": MIN_CLIPE_S,
        "max_s": MAX_CLIPE_S,
        **_impressao_transcricao(saida),
    }

    # A resposta manual e lida ANTES do atalho: e o unico jeito de saber se o
    # que esta colado no arquivo hoje e o mesmo que gerou selecao.json.
    resposta: str | None = None
    digest: str | None = None
    if resposta_manual is not None:
        resposta = _ler_resposta_manual(resposta_manual)
        digest = _digest_resposta(resposta)

    reaproveitar = not forcar and estado.concluido(
        ESTAGIO, assinatura, [saida.selecao_json]
    )
    if reaproveitar and resposta_manual is not None:
        # Mesmo arquivo, conteudo novo => revalida sozinho, sem exigir --force.
        anterior = estado.extra(ESTAGIO).get("resposta_digest")
        reaproveitar = anterior == digest
        if not reaproveitar:
            log.info(
                "   o arquivo de resposta mudou desde a última seleção; "
                "revalidando."
            )
    if reaproveitar:
        extra = estado.extra(ESTAGIO)
        quantos = extra.get("clipes")
        quantos_txt = f" ({quantos} clipe(s))" if quantos is not None else ""
        if tem_fonte:
            log.info(
                f"   seleção já existe{quantos_txt} com os mesmos parâmetros e a "
                f"mesma transcrição; pulando (use {_FLAG_FORCE} para refazer)."
            )
        else:
            log.info(
                f"   seleção já pronta em {saida.selecao_json.name}{quantos_txt}; "
                f"reaproveitando (use  --resposta <arquivo>  para trocá-la, ou "
                f"{_FLAG_FORCE} para refazer)."
            )
        return _Preparado(atalho={**extra, "reaproveitado": True})

    if not tem_fonte:
        # Fluxo manual, passo 1: o prompt esta pronto e a bola esta com o usuario.
        # NAO imprimimos o comando de volta aqui: o estagio nao sabe qual
        # subcomando o usuario rodou (select ou run) nem quais flags ele
        # passou, e um comando incompleto ou com o subcomando errado faz o
        # retorno reprocessar o video. Quem monta essa linha e o cli, que tem
        # as duas informacoes -- ela sai logo abaixo, no bloco PRÓXIMO PASSO.
        log.info("")
        log.info(
            f"   Modo manual: o prompt está pronto em {saida.prompt_selecao_txt.name} "
            "— veja o PRÓXIMO PASSO abaixo."
        )
        return _Preparado(
            atalho={
                "pendente": True,
                "prompt": str(saida.prompt_selecao_txt),
                "caracteres": len(prompt),
                "blocos": len(fronteiras.frases),
                "reaproveitado": False,
            }
        )

    if resposta is not None:
        clipes, problemas = validar(
            extrair_json(resposta), fronteiras, energia, n=n
        )
    else:
        resposta, clipes, problemas = _selecao_via_api(
            prompt=prompt,
            modelo_id=str(modelo_id),
            fronteiras=fronteiras,
            energia=energia,
            n=n,
        )
        digest = _digest_resposta(resposta)

    if problemas:
        raise _erro_de_validacao(saida, prompt, problemas, resposta)

    origem = _origem_rotulo(resposta_manual, modelo_id)
    payload = {
        "estrategia": estrategia,
        "n_pedido": n,
        "origem": origem,
        "modelo": "manual" if resposta_manual is not None else str(modelo_id),
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "limites": {
            "min_s": MIN_CLIPE_S,
            "max_s": MAX_CLIPE_S,
            "tolerancia_s": TOLERANCIA_ENCAIXE_S,
        },
        "clipes": [_para_esquema(i, c) for i, c in enumerate(clipes, 1)],
    }

    duracao_total = round(sum(c["duracao"] for c in payload["clipes"]), 3)
    score_medio = (
        round(sum(c["score_0_10"] for c in payload["clipes"]) / len(payload["clipes"]), 2)
        if payload["clipes"]
        else 0.0
    )
    resumo = {
        "pendente": False,
        "clipes": len(payload["clipes"]),
        "duracao_total": duracao_total,
        "score_medio": score_medio,
        "origem": origem,
        # Identidade da RESPOSTA (nao da assinatura): e o que permite detectar
        # que o mesmo arquivo agora tem outro conteudo.
        "resposta_digest": digest,
    }
    return _Preparado(payload=payload, assinatura=assinatura, resumo=resumo)


def _para_esquema(indice: int, clipe: dict[str, Any]) -> dict[str, Any]:
    """Um clipe validado no esquema exato que a F3 consome."""
    return {
        "id": indice,
        "inicio": round(float(clipe["inicio"]), 3),
        "fim": round(float(clipe["fim"]), 3),
        "duracao": round(float(clipe["duracao"]), 3),
        "inicio_mmss": mmss(clipe["inicio"]),
        "fim_mmss": mmss(clipe["fim"]),
        "titulo": clipe["titulo"],
        "score_0_10": clipe["score_0_10"],
        "motivo": clipe["motivo"],
        "gancho_sugerido": clipe["gancho_sugerido"],
        "texto": clipe["texto"],
        "palavra_inicio": int(clipe["palavra_inicio"]),
        "palavra_fim": int(clipe["palavra_fim"]),
        "frase_inicio": int(clipe["frase_inicio"]),
        "frase_fim": int(clipe["frase_fim"]),
        "ajuste_inicio": round(float(clipe["ajuste_inicio"]), 3),
        "ajuste_fim": round(float(clipe["ajuste_fim"]), 3),
        "energia_media": round(float(clipe["energia_media"]), 3),
    }
