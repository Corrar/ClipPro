"""Fila no Supabase e deposito no Cloudflare R2 (RULINGS §28, P1 = A).

So biblioteca padrao (urllib, hmac, hashlib): zero dependencia nova (CLAUDE.md
§4). Os mesmos verbos de worker/fila.py e worker/deposito.py, entao o laco
do worker e o executor nao sabem se falam com pasta ou com a nuvem.

CHAVES NUNCA NO REPOSITORIO. Tudo vem de variavel de ambiente na maquina do
worker (ver VARIAVEIS). A chave do Supabase e a SECRETA: ela passa por cima do
RLS, e e por isso que a fila so se mexe pelas quatro funcoes de
nuvem/supabase/001_fila.sql, que conferem dono e tentativa.

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from worker.contrato import _RE_CHAVE, _RE_ID, ErroContrato, Trabalho
from worker.deposito import ErroDeposito
from worker.fila import Reserva

VARIAVEIS = {
    "SUPABASE_URL": "endereço do projeto (https://<projeto>.supabase.co)",
    "SUPABASE_SECRET_KEY": "chave secreta do projeto (sb_secret_… ou a service_role antiga)",
    "R2_ACCOUNT_ID": "id da conta da Cloudflare",
    "R2_ACCESS_KEY_ID": "id da chave de API do R2",
    "R2_SECRET_ACCESS_KEY": "segredo da chave de API do R2",
    "R2_BUCKET": "nome do bucket",
}
TIMEOUT_S = 60.0
_VAZIO_SHA256 = hashlib.sha256(b"").hexdigest()
_BLOCO = 1024 * 1024


class ErroNuvem(Exception):
    def __init__(self, mensagem: str, detalhe: str = "") -> None:
        self.mensagem, self.detalhe = mensagem, detalhe
        super().__init__(f"{mensagem} {detalhe}".strip())


def variaveis_faltando(ambiente: dict[str, str] | None = None) -> list[str]:
    amb = os.environ if ambiente is None else ambiente
    return [nome for nome in VARIAVEIS if not (amb.get(nome) or "").strip()]


# ==========================================================================
# Assinatura S3 (SigV4) -- o R2 fala a API do S3
# ==========================================================================


def _hmac(chave: bytes, texto: str) -> bytes:
    return hmac.new(chave, texto.encode("utf-8"), hashlib.sha256).digest()


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
    """Devolve os cabecalhos assinados (Authorization, x-amz-date, ...).

    Algoritmo AWS Signature Version 4, conferido pela prova contra o exemplo
    oficial da AWS (GET Object com Range). 'cabecalhos' sao os que vao na
    requisicao alem de host/x-amz-*; todos entram na assinatura.
    """
    partes = urlsplit(url)
    data_hora = quando.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    data = data_hora[:8]
    todos = {k.lower(): " ".join(str(v).split()) for k, v in cabecalhos.items()}
    todos["host"] = partes.netloc
    todos["x-amz-content-sha256"] = carga_sha256
    todos["x-amz-date"] = data_hora
    nomes = sorted(todos)
    caminho = quote(partes.path or "/", safe="/-_.~")
    consulta = "&".join(sorted(
        f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}"
        for k, _, v in (p.partition("=") for p in partes.query.split("&") if p)
    ))
    canonica = "\n".join([
        metodo.upper(), caminho, consulta,
        "".join(f"{n}:{todos[n]}\n" for n in nomes),
        ";".join(nomes), carga_sha256,
    ])
    escopo = f"{data}/{regiao}/{servico}/aws4_request"
    a_assinar = "\n".join([
        "AWS4-HMAC-SHA256", data_hora, escopo,
        hashlib.sha256(canonica.encode("utf-8")).hexdigest(),
    ])
    chave = _hmac(_hmac(_hmac(_hmac(f"AWS4{segredo}".encode("utf-8"), data), regiao),
                        servico), "aws4_request")
    assinatura = hmac.new(chave, a_assinar.encode("utf-8"), hashlib.sha256).hexdigest()
    saida = {k: v for k, v in cabecalhos.items()}
    saida["x-amz-content-sha256"] = carga_sha256
    saida["x-amz-date"] = data_hora
    saida["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={chave_id}/{escopo}, "
        f"SignedHeaders={';'.join(nomes)}, Signature={assinatura}"
    )
    return saida


def _sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while bloco := f.read(_BLOCO):
            h.update(bloco)
    return h.hexdigest()


# ==========================================================================
# Deposito no R2
# ==========================================================================


class DepositoR2:
    """entradas/<chave> e resultados/<trabalho>/<arquivo>, como DepositoEmPasta."""

    def __init__(self, conta: str, chave_id: str, segredo: str, bucket: str,
                 *, endpoint: str | None = None) -> None:
        self.base = (endpoint or f"https://{conta}.r2.cloudflarestorage.com").rstrip("/")
        self.bucket = bucket
        self._chave_id, self._segredo = chave_id, segredo

    @classmethod
    def do_ambiente(cls) -> "DepositoR2":
        a = os.environ
        return cls(a["R2_ACCOUNT_ID"].strip(), a["R2_ACCESS_KEY_ID"].strip(),
                   a["R2_SECRET_ACCESS_KEY"].strip(), a["R2_BUCKET"].strip())

    def _url(self, chave: str) -> str:
        return f"{self.base}/{self.bucket}/{chave}"

    def _pedido(self, metodo: str, chave: str, *, corpo: Any = None, sha: str = _VAZIO_SHA256,
                extra: dict[str, str] | None = None) -> urllib.request.Request:
        url = self._url(chave)
        cab = assinar_s3(metodo, url, dict(extra or {}), sha, chave_id=self._chave_id,
                         segredo=self._segredo, regiao="auto",
                         quando=datetime.now(timezone.utc))
        return urllib.request.Request(url, data=corpo, method=metodo, headers=cab)

    def obter_entrada(self, chave: str, destino_dir: Path) -> Path:
        """Baixa o video enviado. Idempotente, como DepositoEmPasta.

        O mtime local vira o Last-Modified do objeto: numa retomada, tamanho
        e mtime batem, o download nao se repete e a assinatura do ingest
        (bytes + mtime) tambem bate.
        """
        if not (_RE_CHAVE.match(chave) and ".." not in chave):
            raise ErroDeposito("a chave do arquivo enviado é inválida.")
        objeto = f"entradas/{chave}"
        try:
            with urllib.request.urlopen(self._pedido("HEAD", objeto), timeout=TIMEOUT_S) as r:
                tamanho = int(r.headers.get("Content-Length") or -1)
                modificado = r.headers.get("Last-Modified")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise ErroDeposito("o arquivo enviado não está mais no depósito.") from None
            raise ErroDeposito(f"o depósito recusou a leitura (HTTP {exc.code}).") from None
        except urllib.error.URLError as exc:
            raise ErroDeposito(f"não consegui falar com o depósito ({exc.reason}).") from None
        mtime = parsedate_to_datetime(modificado).timestamp() if modificado else None

        destino_dir = Path(destino_dir)
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / chave
        try:
            st = destino.stat()
            if st.st_size == tamanho and (mtime is None or abs(st.st_mtime - mtime) < 1.0):
                return destino
        except FileNotFoundError:
            pass
        temp = destino.with_name(destino.name + ".parcial")
        try:
            with urllib.request.urlopen(self._pedido("GET", objeto), timeout=TIMEOUT_S) as r, \
                    open(temp, "wb") as f:
                shutil.copyfileobj(r, f, _BLOCO)
        except urllib.error.HTTPError as exc:
            raise ErroDeposito(f"o depósito recusou o download (HTTP {exc.code}).") from None
        except urllib.error.URLError as exc:
            raise ErroDeposito(f"o download do depósito falhou ({exc.reason}).") from None
        if mtime is not None:
            os.utime(temp, (mtime, mtime))
        os.replace(temp, destino)
        return destino

    def enviar(self, trabalho_id: str, arquivo: Path) -> str:
        if not _RE_ID.match(trabalho_id):
            raise ErroDeposito("id de trabalho inválido para o depósito.")
        arquivo = Path(arquivo)
        chave = f"resultados/{trabalho_id}/{arquivo.name}"
        tamanho = arquivo.stat().st_size
        with open(arquivo, "rb") as corpo:
            pedido = self._pedido("PUT", chave, corpo=corpo, sha=_sha256_arquivo(arquivo),
                                  extra={"Content-Length": str(tamanho)})
            try:
                with urllib.request.urlopen(pedido, timeout=TIMEOUT_S):
                    pass
            except urllib.error.HTTPError as exc:
                raise ErroDeposito(f"o depósito recusou o envio (HTTP {exc.code}).") from None
            except urllib.error.URLError as exc:
                raise ErroDeposito(f"o envio ao depósito falhou ({exc.reason}).") from None
        return chave


# ==========================================================================
# Fila no Supabase
# ==========================================================================


@dataclass
class FilaSupabase:
    """Os verbos da FilaEmPasta sobre as funcoes de nuvem/supabase/001_fila.sql."""

    url: str
    chave: str
    prazo_s: float = 600.0

    @classmethod
    def do_ambiente(cls, prazo_s: float) -> "FilaSupabase":
        return cls(os.environ["SUPABASE_URL"].strip().rstrip("/"),
                   os.environ["SUPABASE_SECRET_KEY"].strip(), prazo_s)

    def _rpc(self, funcao: str, parametros: dict[str, Any]) -> Any:
        # As chaves novas (sb_secret_...) NAO sao JWT: vao so no 'apikey'.
        # A service_role antiga e JWT (comeca com 'eyJ') e vai tambem no
        # Authorization, como a documentacao do Supabase manda.
        cab = {"apikey": self.chave, "Content-Type": "application/json",
               "Accept": "application/json"}
        if self.chave.startswith("eyJ"):
            cab["Authorization"] = f"Bearer {self.chave}"
        pedido = urllib.request.Request(
            f"{self.url}/rest/v1/rpc/{funcao}", method="POST", headers=cab,
            data=json.dumps(parametros, ensure_ascii=False).encode("utf-8"),
        )
        try:
            with urllib.request.urlopen(pedido, timeout=TIMEOUT_S) as r:
                corpo = r.read()
        except urllib.error.HTTPError as exc:
            detalhe = exc.read().decode("utf-8", "replace")[:300]
            raise ErroNuvem(f"a fila recusou '{funcao}' (HTTP {exc.code}).", detalhe) from None
        except urllib.error.URLError as exc:
            raise ErroNuvem(f"não consegui falar com a fila ({exc.reason}).") from None
        return json.loads(corpo.decode("utf-8")) if corpo else None

    def reservar(self, worker: str) -> Reserva | None:
        while True:
            linhas = self._rpc("reservar_trabalho",
                               {"p_worker": worker, "p_prazo_s": int(self.prazo_s)})
            if not linhas:
                return None
            linha = linhas[0]
            pedido = linha.get("pedido") if isinstance(linha.get("pedido"), dict) else {}
            dados = {**pedido, "id": linha.get("id"), "conta": linha.get("conta")}
            tentativa = int(linha.get("tentativas") or 0)
            try:
                trabalho = Trabalho.de_dict(dados)
            except ErroContrato as exc:
                # Pedido torto nunca chega ao motor (a mesma regra da pasta).
                self._encerrar(str(linha.get("id")), worker, tentativa, "recusado", {
                    "status": "recusado", "creditos": 0,
                    "erro": {"mensagem": "o pedido foi recusado.", "sugestao": "",
                             "detalhe": "; ".join(exc.problemas)},
                })
                continue
            return Reserva(trabalho.id, trabalho, worker, tentativa)

    def renovar(self, reserva: Reserva) -> None:
        try:
            self._rpc("renovar_trabalho", {
                "p_id": reserva.nome, "p_worker": reserva.worker,
                "p_tentativa": reserva.tentativa, "p_prazo_s": int(self.prazo_s)})
        except ErroNuvem:
            pass  # rede piscou: tenta no proximo batimento

    def concluir(self, reserva: Reserva, resultado: dict[str, Any]) -> bool:
        return self._encerrar(reserva.nome, reserva.worker, reserva.tentativa,
                              "concluido", resultado)

    def falhar(self, reserva: Reserva, resultado: dict[str, Any]) -> bool:
        return self._encerrar(reserva.nome, reserva.worker, reserva.tentativa,
                              "falhou", resultado)

    def devolver(self, reserva: Reserva) -> None:
        try:
            self._rpc("devolver_trabalho", {"p_id": reserva.nome, "p_worker": reserva.worker,
                                            "p_tentativa": reserva.tentativa})
        except ErroNuvem:
            pass  # sem rede, o prazo devolve sozinho

    def devolver_expirados(self, _prazo_s: float) -> list[str]:
        # No Supabase a devolucao acontece DENTRO de reservar_trabalho, na
        # mesma transacao: nao ha janela entre devolver e reservar.
        return []

    def _encerrar(self, id_: str, worker: str, tentativa: int, status: str,
                  resultado: dict[str, Any]) -> bool:
        return bool(self._rpc("encerrar_trabalho", {
            "p_id": id_, "p_worker": worker, "p_tentativa": tentativa,
            "p_status": status, "p_resultado": resultado}))
