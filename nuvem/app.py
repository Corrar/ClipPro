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

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote

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
    }


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
