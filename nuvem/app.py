"""Logica das funcoes da Vercel (api/), sem HTTP: testavel direto.

Cada funcao recebe o ambiente (dict) e o pedido e devolve (status, json). Os
arquivos em api/ so traduzem HTTP <-> estas funcoes; nenhuma regra mora la.

O QUE NUNCA SAI DAQUI: a chave secreta do Supabase (as funcoes nem a usam --
falam com o banco com o token do usuario, e o RLS decide o que ele ve) e o
segredo do R2 (sai so a URL assinada, que vence sozinha).

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote

from nuvem import mercadopago as mp
from nuvem import rest
from nuvem.s3 import presignar_s3

# 2 GB por envio: ~1 h de video na medida do README (29 min = 1,0 GB). Acima
# disso o beta grátis (R2 com 10 GB) encheria com meia duzia de envios.
TAMANHO_MAXIMO = 2 * 1024**3
EXPIRA_UPLOAD_S = 15 * 60
EXPIRA_CLIPE_S = 60 * 60
EXTENSOES = (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi")
_RE_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

Resposta = tuple[int, dict[str, Any]]


def _erro(status: int, mensagem: str) -> Resposta:
    return status, {"erro": mensagem}


def _faltando(amb: Mapping[str, str], nomes: tuple[str, ...]) -> list[str]:
    return [n for n in nomes if not (amb.get(n) or "").strip()]


def configuracao_publica(amb: Mapping[str, str]) -> Resposta:
    """O que o navegador precisa para falar com o Supabase -- so valores PUBLICOS."""
    faltam = _faltando(amb, ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"))
    if faltam:
        return _erro(503, "o ClipPro ainda não foi configurado neste endereço.")
    return 200, {
        "supabase_url": amb["SUPABASE_URL"].strip().rstrip("/"),
        "supabase_chave": amb["SUPABASE_PUBLISHABLE_KEY"].strip(),
        # A loja so aparece com as vendas ligadas (RULINGS §29.5).
        "compras": _compras_ativas(amb),
    }


def _compras_ativas(amb: Mapping[str, str]) -> bool:
    return (amb.get("COMPRAS_ATIVAS") or "").strip() == "1"


def _usuario(amb: Mapping[str, str], token: str | None) -> dict[str, Any] | None:
    try:
        return rest.usuario_do_token(amb["SUPABASE_URL"].strip(),
                                     amb["SUPABASE_PUBLISHABLE_KEY"].strip(), token or "")
    except rest.ErroNuvem:
        return None


def _r2(amb: Mapping[str, str]) -> tuple[str, str, str, str]:
    base = (amb.get("R2_ENDPOINT") or "").strip().rstrip("/") or \
        f"https://{amb['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com"
    return (f"{base}/{amb['R2_BUCKET'].strip()}", amb["R2_ACCESS_KEY_ID"].strip(),
            amb["R2_SECRET_ACCESS_KEY"].strip(), "auto")


_R2_VARS = ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "R2_ACCOUNT_ID",
            "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")


def pedir_upload(amb: Mapping[str, str], token: str | None, corpo: Any) -> Resposta:
    """URL assinada para o navegador mandar o video DIRETO ao R2.

    O content-length vai ASSINADO: o tamanho declarado aqui vira regra, e um
    arquivo diferente e recusado pelo proprio R2. A chave leva a conta na
    frente (limpeza por usuario) e um uuid (ninguem adivinha a de outro).
    """
    if _faltando(amb, _R2_VARS):
        return _erro(503, "o envio de vídeos ainda não foi configurado.")
    usuario = _usuario(amb, token)
    if usuario is None:
        return _erro(401, "entre na sua conta para enviar vídeos.")
    if not isinstance(corpo, dict):
        return _erro(400, "pedido inválido.")
    nome, tamanho, tipo = corpo.get("nome"), corpo.get("tamanho"), corpo.get("tipo") or ""
    if not isinstance(nome, str) or not isinstance(tamanho, int) or isinstance(tamanho, bool):
        return _erro(400, "informe o nome e o tamanho do arquivo.")
    if not 1 <= tamanho <= TAMANHO_MAXIMO:
        return _erro(400, "o vídeo passa de 2 GB; envie um trecho menor.")
    extensao = next((e for e in EXTENSOES if nome.lower().endswith(e)), None)
    # Tipo vazio e aceito (alguns navegadores nao sabem o tipo de .mkv); tipo
    # declarado tem de ser video/*.
    if extensao is None or (tipo and not str(tipo).startswith("video/")):
        return _erro(400, "envie um arquivo de vídeo (mp4, mov, mkv, webm, m4v ou avi).")
    chave = f"{usuario['id']}-{uuid.uuid4().hex}{extensao}"
    base, chave_id, segredo, regiao = _r2(amb)
    url = presignar_s3("PUT", f"{base}/entradas/{chave}", chave_id=chave_id, segredo=segredo,
                       regiao=regiao, quando=datetime.now(timezone.utc),
                       expira_s=EXPIRA_UPLOAD_S, cabecalhos={"content-length": str(tamanho)})
    return 200, {"chave": chave, "url": url, "expira_s": EXPIRA_UPLOAD_S}


def links_dos_clipes(amb: Mapping[str, str], token: str | None, trabalho_id: str) -> Resposta:
    """URLs assinadas dos clipes de UM trabalho da conta logada.

    O trabalho e lido pelo banco COM O TOKEN do usuario: o RLS so devolve se
    for dele. Chave fora de resultados/<id>/ e ignorada (defesa contra um
    resultado adulterado apontar para o arquivo de outro).
    """
    if _faltando(amb, _R2_VARS):
        return _erro(503, "os clipes ainda não foram configurados.")
    if not _RE_UUID.match(trabalho_id or ""):
        return _erro(400, "trabalho inválido.")
    usuario = _usuario(amb, token)
    if usuario is None:
        return _erro(401, "entre na sua conta para ver os clipes.")
    try:
        linhas = rest.chamar(amb["SUPABASE_URL"].strip(), amb["SUPABASE_PUBLISHABLE_KEY"].strip(),
                             "GET", f"/rest/v1/trabalhos?id=eq.{trabalho_id}"
                             "&select=id,status,resultado", token=token)
    except rest.ErroNuvem:
        return _erro(502, "não consegui consultar o trabalho agora; tente de novo.")
    if not linhas:
        return _erro(404, "trabalho não encontrado.")
    linha = linhas[0]
    if linha.get("status") != "concluido":
        return 200, {"status": linha.get("status"), "clipes": []}

    base, chave_id, segredo, regiao = _r2(amb)
    agora = datetime.now(timezone.utc)
    prefixo = f"resultados/{trabalho_id}/"

    def assinar(chave: str, baixar: bool = False) -> str:
        url = f"{base}/{chave}"
        if baixar:
            nome = chave.rsplit("/", 1)[-1]
            url += "?response-content-disposition=" + quote(f'attachment; filename="{nome}"',
                                                             safe="")
        return presignar_s3("GET", url, chave_id=chave_id, segredo=segredo, regiao=regiao,
                            quando=agora, expira_s=EXPIRA_CLIPE_S)

    clipes = []
    for c in (linha.get("resultado") or {}).get("clipes") or []:
        arquivos = {k: v for k, v in (c.get("arquivos") or {}).items()
                    if isinstance(v, str) and v.startswith(prefixo) and ".." not in v}
        if "video" not in arquivos:
            continue
        clipes.append({
            "titulo": c.get("titulo"), "score": c.get("score"), "gancho": c.get("gancho"),
            "motivo": c.get("motivo"), "duracao": c.get("duracao"),
            "ver": assinar(arquivos["video"]),
            "baixar": assinar(arquivos["video"], baixar=True),
            "capa": assinar(arquivos["capa"]) if "capa" in arquivos else None,
            "publicacao": assinar(arquivos["publicacao"]) if "publicacao" in arquivos else None,
        })
    return 200, {"status": "concluido", "clipes": clipes}


# ==========================================================================
# N-3: compra de creditos (RULINGS §29.5)
# ==========================================================================

_RE_PACOTE = re.compile(r"^[a-z0-9-]{1,32}$")


def _mensagem_do_banco(exc: rest.ErroNuvem) -> str | None:
    """A mensagem em portugues que a funcao SQL levantou (raise exception)."""
    try:
        dados = json.loads(exc.detalhe or "{}")
    except json.JSONDecodeError:
        return None
    msg = dados.get("message") if isinstance(dados, dict) else None
    return msg if isinstance(msg, str) and msg else None


def iniciar_pagamento(amb: Mapping[str, str], token: str | None, corpo: Any) -> Resposta:
    """Abre a compra no banco e devolve o link de pagamento do Mercado Pago."""
    if not _compras_ativas(amb):
        return _erro(503, "a compra de créditos abre no lançamento do ClipPro.")
    if _faltando(amb, ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "MP_ACCESS_TOKEN", "APP_URL")):
        return _erro(503, "a compra de créditos ainda não foi configurada.")
    usuario = _usuario(amb, token)
    if usuario is None:
        return _erro(401, "entre na sua conta para comprar créditos.")
    pacote = corpo.get("pacote") if isinstance(corpo, dict) else None
    if not isinstance(pacote, str) or not _RE_PACOTE.match(pacote):
        return _erro(400, "escolha um pacote.")
    url, chave = amb["SUPABASE_URL"].strip(), amb["SUPABASE_PUBLISHABLE_KEY"].strip()
    try:
        compra_id = rest.rpc(url, chave, "iniciar_compra", {"p_pacote": pacote}, token=token)
        linhas = rest.chamar(url, chave, "GET", f"/rest/v1/compras?id=eq.{compra_id}"
                             "&select=id,pacote,minutos,preco_centavos", token=token)
    except rest.ErroNuvem as exc:
        mensagem = _mensagem_do_banco(exc)
        if mensagem and exc.status == 400:
            return _erro(400, mensagem)
        return _erro(502, "não consegui abrir a compra agora; tente de novo.")
    if not linhas:
        return _erro(502, "não consegui abrir a compra agora; tente de novo.")
    try:
        pref = mp.criar_preferencia(amb["MP_ACCESS_TOKEN"].strip(), compra=linhas[0],
                                    email=usuario.get("email"), app_url=amb["APP_URL"].strip(),
                                    api=(amb.get("MP_API") or mp.API_PADRAO).strip())
    except mp.ErroMercadoPago:
        return _erro(502, "o Mercado Pago não respondeu; tente de novo em instantes.")
    return 200, {"url": pref["init_point"], "compra": linhas[0]["id"]}


def _log(texto: str) -> None:
    # Vai para os logs da funcao na Vercel: e onde o Bruno ve o que o webhook
    # recusou de proposito.
    print(f"[mp_webhook] {texto}", file=sys.stderr, flush=True)


def receber_webhook(amb: Mapping[str, str], consulta: Mapping[str, str],
                    cabecalhos: Mapping[str, str], corpo: Any) -> Resposta:
    """Aviso de pagamento do Mercado Pago.

    200 = recebido (mesmo que ignorado: repetir nao muda nada).
    401 = assinatura invalida. 500/502 = falha passageira: o Mercado Pago
    tenta de novo sozinho, e a confirmacao e idempotente.
    """
    if not _compras_ativas(amb):
        return 200, {"ignorado": "compras desligadas"}
    if _faltando(amb, ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "MP_ACCESS_TOKEN", "MP_WEBHOOK_SECRET")):
        return _erro(500, "webhook não configurado.")
    corpo = corpo if isinstance(corpo, dict) else {}
    tipo = consulta.get("type") or corpo.get("type") or consulta.get("topic")
    data_id = consulta.get("data.id") or (corpo.get("data") or {}).get("id")
    if tipo != "payment" or not data_id:
        return 200, {"ignorado": f"tipo {tipo!r}"}
    if not mp.assinatura_valida(cabecalhos.get("x-signature"), cabecalhos.get("x-request-id"),
                                str(data_id), amb["MP_WEBHOOK_SECRET"].strip()):
        _log(f"assinatura inválida para o pagamento {data_id}")
        return _erro(401, "assinatura inválida.")
    try:
        pag = mp.consultar_pagamento(amb["MP_ACCESS_TOKEN"].strip(), str(data_id),
                                     api=(amb.get("MP_API") or mp.API_PADRAO).strip())
    except mp.ErroMercadoPago as exc:
        return _erro(502, exc.mensagem)

    status = str(pag.get("status") or "")
    compra = str(pag.get("external_reference") or "")
    if status in ("pending", "in_process", "authorized", "in_mediation"):
        return 200, {"aguardando": status}
    if not _RE_UUID.match(compra):
        _log(f"pagamento {data_id} sem compra do ClipPro (external_reference {compra!r})")
        return 200, {"ignorado": "não é uma compra do ClipPro"}
    if status in ("refunded", "charged_back"):
        # Estorno no beta: registrado, sem debito automatico (§29.5).
        _log(f"ESTORNO do pagamento {data_id} da compra {compra}: tratar à mão")
        return 200, {"estorno": "registrado"}
    aprovado = status == "approved" and pag.get("currency_id") == "BRL"
    valor = round(float(pag.get("transaction_amount") or 0) * 100)
    try:
        resultado = rest.rpc(amb["SUPABASE_URL"].strip(), amb["SUPABASE_SECRET_KEY"].strip(),
                             "confirmar_compra", {"p_compra": compra, "p_pagamento": str(data_id),
                                                  "p_valor_centavos": valor, "p_aprovado": aprovado})
    except rest.ErroNuvem as exc:
        if exc.status in (400, 409):
            # Permanente (valor diferente, pagamento reaproveitado): repetir
            # nao conserta. Fica no log para o Bruno.
            _log(f"compra {compra} NÃO creditada: {_mensagem_do_banco(exc) or exc.detalhe}")
            return 200, {"recusado": _mensagem_do_banco(exc) or "recusado pelo banco"}
        return _erro(500, "banco indisponível; o Mercado Pago tenta de novo.")
    return 200, {"resultado": resultado}
