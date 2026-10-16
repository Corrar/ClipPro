"""Assinatura AWS SigV4 para a API S3 (o Cloudflare R2 fala essa API).

Duas formas, as duas conferidas pela prova contra os exemplos oficiais da AWS:

- assinar_s3: cabecalhos assinados (o worker sobe e baixa arquivos);
- presignar_s3: URL pre-assinada (o navegador sobe o video e ve os clipes
  sem nunca ver o segredo).

Convencao: comentarios e docstrings em PT-BR sem acento.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, urlsplit

ALGORITMO = "AWS4-HMAC-SHA256"
CARGA_NAO_ASSINADA = "UNSIGNED-PAYLOAD"


def _hmac(chave: bytes, texto: str) -> bytes:
    return hmac.new(chave, texto.encode("utf-8"), hashlib.sha256).digest()


def _chave_de_assinatura(segredo: str, data: str, regiao: str, servico: str) -> bytes:
    return _hmac(_hmac(_hmac(_hmac(f"AWS4{segredo}".encode("utf-8"), data), regiao),
                       servico), "aws4_request")


def _q(texto: str) -> str:
    return quote(texto, safe="-_.~")


def _consulta_canonica(pares: list[tuple[str, str]]) -> str:
    return "&".join(f"{_q(k)}={_q(v)}" for k, v in sorted(pares))


def _pares_da_url(consulta: str) -> list[tuple[str, str]]:
    # DECODIFICA antes: a forma canonica codifica uma vez so. Repassar o texto
    # cru codificava duas (%3B virava %253B) -- a assinatura batia, mas o
    # nome do arquivo no download chegava quebrado.
    return parse_qsl(consulta, keep_blank_values=True)


def _assinatura(metodo: str, caminho: str, consulta: str, cabecalhos: dict[str, str],
                carga: str, segredo: str, data_hora: str, regiao: str,
                servico: str) -> tuple[str, str, str]:
    """(assinatura, escopo, cabecalhos assinados) -- o miolo das duas formas."""
    nomes = sorted(cabecalhos)
    canonica = "\n".join([
        metodo.upper(), quote(caminho or "/", safe="/-_.~"), consulta,
        "".join(f"{n}:{cabecalhos[n]}\n" for n in nomes),
        ";".join(nomes), carga,
    ])
    escopo = f"{data_hora[:8]}/{regiao}/{servico}/aws4_request"
    a_assinar = "\n".join([ALGORITMO, data_hora, escopo,
                           hashlib.sha256(canonica.encode("utf-8")).hexdigest()])
    chave = _chave_de_assinatura(segredo, data_hora[:8], regiao, servico)
    return (hmac.new(chave, a_assinar.encode("utf-8"), hashlib.sha256).hexdigest(),
            escopo, ";".join(nomes))


def _data_hora(quando: datetime) -> str:
    return quando.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def assinar_s3(
    metodo: str,
    url: str,
    cabecalhos: dict[str, str],
    carga_sha256: str,
    *,
    chave_id: str,
    segredo: str,
    regiao: str,
    quando: datetime,
    servico: str = "s3",
) -> dict[str, str]:
    """Devolve os cabecalhos assinados (Authorization, x-amz-date, ...)."""
    partes = urlsplit(url)
    data_hora = _data_hora(quando)
    todos = {k.lower(): " ".join(str(v).split()) for k, v in cabecalhos.items()}
    todos["host"] = partes.netloc
    todos["x-amz-content-sha256"] = carga_sha256
    todos["x-amz-date"] = data_hora
    assinatura, escopo, assinados = _assinatura(
        metodo, partes.path, _consulta_canonica(_pares_da_url(partes.query)), todos,
        carga_sha256, segredo, data_hora, regiao, servico)
    saida = dict(cabecalhos)
    saida["x-amz-content-sha256"] = carga_sha256
    saida["x-amz-date"] = data_hora
    saida["Authorization"] = (f"{ALGORITMO} Credential={chave_id}/{escopo}, "
                              f"SignedHeaders={assinados}, Signature={assinatura}")
    return saida


def presignar_s3(
    metodo: str,
    url: str,
    *,
    chave_id: str,
    segredo: str,
    regiao: str,
    quando: datetime,
    expira_s: int,
    cabecalhos: dict[str, str] | None = None,
    servico: str = "s3",
) -> str:
    """URL pre-assinada (assinatura na query string), valida por 'expira_s'.

    'cabecalhos' entram na assinatura e o navegador TEM de manda-los iguais.
    O upload assina o content-length: o tamanho declarado ao pedir a URL vira
    regra, e um arquivo maior que o liberado e recusado pelo proprio R2.
    """
    partes = urlsplit(url)
    data_hora = _data_hora(quando)
    todos = {k.lower(): " ".join(str(v).split()) for k, v in (cabecalhos or {}).items()}
    todos["host"] = partes.netloc
    escopo_prev = f"{data_hora[:8]}/{regiao}/{servico}/aws4_request"
    pares = _pares_da_url(partes.query) + [
        ("X-Amz-Algorithm", ALGORITMO),
        ("X-Amz-Credential", f"{chave_id}/{escopo_prev}"),
        ("X-Amz-Date", data_hora),
        ("X-Amz-Expires", str(int(expira_s))),
        ("X-Amz-SignedHeaders", ";".join(sorted(todos))),
    ]
    consulta = _consulta_canonica(pares)
    assinatura, _, _ = _assinatura(metodo, partes.path, consulta, todos,
                                   CARGA_NAO_ASSINADA, segredo, data_hora, regiao, servico)
    base = f"{partes.scheme}://{partes.netloc}{quote(partes.path or '/', safe='/-_.~')}"
    return f"{base}?{consulta}&X-Amz-Signature={assinatura}"
