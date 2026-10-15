"""Mercado Pago: Checkout Pro (API de Preferencias) e webhook assinado.

So biblioteca padrao. Tres verbos:
- criar_preferencia: o link de pagamento do pacote;
- assinatura_valida: o aviso (webhook) veio mesmo do Mercado Pago;
- consultar_pagamento: a VERDADE sobre o pagamento, direto na API -- o
  credito nunca e dado so com base no que o aviso diz (RULINGS §29.5).

Manifest da assinatura, como na documentacao oficial:
    id:{data.id};request-id:{x-request-id};ts:{ts};
HMAC-SHA256 com a chave secreta do webhook, em hexadecimal, comparado com o
v1 do cabecalho x-signature ("ts=...,v1=...").

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from typing import Any

API_PADRAO = "https://api.mercadopago.com"
TIMEOUT_S = 20.0


class ErroMercadoPago(Exception):
    def __init__(self, mensagem: str, status: int = 0) -> None:
        self.mensagem, self.status = mensagem, status
        super().__init__(mensagem)


def _pedir(api: str, token: str, metodo: str, caminho: str, corpo: Any = None) -> Any:
    pedido = urllib.request.Request(
        api.rstrip("/") + caminho, method=metodo,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Accept": "application/json"},
        data=None if corpo is None else json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_S) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as exc:
        raise ErroMercadoPago(f"o Mercado Pago recusou {metodo} {caminho} (HTTP {exc.code}).",
                              exc.code) from None
    except urllib.error.URLError as exc:
        raise ErroMercadoPago(f"não consegui falar com o Mercado Pago ({exc.reason}).") from None


def criar_preferencia(token: str, *, compra: dict[str, Any], email: str | None, app_url: str,
                      api: str = API_PADRAO) -> dict[str, Any]:
    """O link de pagamento de UMA compra. O preco vem da COMPRA (congelado
    quando ela foi aberta), nunca do pacote atual nem do navegador."""
    base = app_url.rstrip("/")
    corpo: dict[str, Any] = {
        "items": [{
            "id": str(compra["pacote"]),
            "title": f"ClipPro — {int(compra['minutos'])} minutos de vídeo",
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": round(int(compra["preco_centavos"]) / 100, 2),
        }],
        "external_reference": str(compra["id"]),
        "notification_url": f"{base}/api/mp_webhook",
        "back_urls": {
            "success": f"{base}/#/compra/aprovada",
            "pending": f"{base}/#/compra/pendente",
            "failure": f"{base}/#/compra/recusada",
        },
        "auto_return": "approved",
        "statement_descriptor": "CLIPPRO",
    }
    if email:
        corpo["payer"] = {"email": email}
    dados = _pedir(api, token, "POST", "/checkout/preferences", corpo)
    if not isinstance(dados, dict) or not dados.get("init_point"):
        raise ErroMercadoPago("o Mercado Pago não devolveu o link de pagamento.")
    return dados


def consultar_pagamento(token: str, pagamento_id: str, *, api: str = API_PADRAO) -> dict[str, Any]:
    if not str(pagamento_id).isdigit():
        raise ErroMercadoPago("id de pagamento inválido.", 400)
    dados = _pedir(api, token, "GET", f"/v1/payments/{pagamento_id}")
    if not isinstance(dados, dict):
        raise ErroMercadoPago("resposta inesperada do Mercado Pago.")
    return dados


def manifest(data_id: str | None, request_id: str | None, ts: str | None) -> str:
    """O texto que o Mercado Pago assina. Parte sem valor sai do manifest
    (regra da documentacao); id alfanumerico vai em minusculas."""
    partes = []
    if data_id:
        partes.append(f"id:{str(data_id).lower()};")
    if request_id:
        partes.append(f"request-id:{request_id};")
    if ts:
        partes.append(f"ts:{ts};")
    return "".join(partes)


def assinatura_valida(x_signature: str | None, request_id: str | None, data_id: str | None,
                      segredo: str) -> bool:
    if not x_signature or not segredo:
        return False
    campos: dict[str, str] = {}
    for parte in x_signature.split(","):
        chave, _, valor = parte.strip().partition("=")
        campos[chave.strip()] = valor.strip()
    ts, v1 = campos.get("ts"), campos.get("v1")
    if not ts or not v1:
        return False
    esperado = hmac.new(segredo.encode("utf-8"), manifest(data_id, request_id, ts).encode("utf-8"),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, v1.lower())
