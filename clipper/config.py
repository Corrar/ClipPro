"""Caminhos, slug, estado de idempotencia e leitura de chave.

Este modulo e o "contrato" compartilhado por todos os estagios: quem quiser
saber ONDE um artefato mora pergunta aqui, nunca monta caminho na mao.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

RAIZ = Path(__file__).resolve().parent.parent
DIR_PRESETS = Path(__file__).resolve().parent / "presets"
DIR_SAIDA_PADRAO = RAIZ / "out"

MODELO_WHISPER_PADRAO = "medium"

ESTRATEGIA_PADRAO = "momentos de maior densidade de informacao, ganchos e punchlines"


def slugificar(texto: str, limite: int = 60) -> str:
    """Transforma um titulo/nome de arquivo em slug ASCII seguro para pasta."""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    texto = re.sub(r"-{2,}", "-", texto).strip("-")
    if not texto:
        return "video"
    return texto[:limite].strip("-") or "video"


@dataclass(frozen=True)
class Saida:
    """Layout de out/<slug>/. Uma instancia por video processado."""

    slug: str
    base: Path

    @classmethod
    def para(cls, slug: str, dir_saida: Path | None = None) -> "Saida":
        base = Path(dir_saida or DIR_SAIDA_PADRAO) / slug
        return cls(slug=slug, base=base)

    def criar_dirs(self) -> "Saida":
        self.base.mkdir(parents=True, exist_ok=True)
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.trabalho_dir.mkdir(parents=True, exist_ok=True)
        return self

    # --- estagio 1: ingestao ---
    @property
    def fonte_mp4(self) -> Path:
        return self.base / "fonte.mp4"

    @property
    def audio_wav(self) -> Path:
        return self.base / "audio.wav"

    @property
    def fonte_info_json(self) -> Path:
        return self.base / "fonte.json"

    # --- estagio 2: transcricao ---
    @property
    def transcricao_json(self) -> Path:
        return self.base / "transcricao.json"

    @property
    def transcricao_srt(self) -> Path:
        return self.base / "transcricao.srt"

    @property
    def energia_json(self) -> Path:
        return self.base / "energia.json"

    # --- estagio 3: selecao ---
    @property
    def prompt_selecao_txt(self) -> Path:
        return self.base / "prompt_selecao.txt"

    @property
    def selecao_json(self) -> Path:
        return self.base / "selecao.json"

    # --- estagio 4: render ---
    @property
    def clips_dir(self) -> Path:
        return self.base / "clips"

    @property
    def metadados_json(self) -> Path:
        return self.base / "metadados.json"

    @property
    def relatorio_md(self) -> Path:
        return self.base / "relatorio.md"

    # --- infra ---
    @property
    def trabalho_dir(self) -> Path:
        """Arquivos intermediarios descartaveis (frames, .ass, listas)."""
        return self.base / "_trabalho"

    @property
    def log(self) -> Path:
        return self.base / "clipper.log"

    @property
    def estado_json(self) -> Path:
        return self.base / ".estado.json"


class Estado:
    """Idempotencia: guarda o que ja rodou e com quais parametros.

    Um estagio e considerado concluido quando (a) o estado registra a mesma
    assinatura de parametros e (b) todos os artefatos declarados existem e nao
    estao vazios. Mudou parametro -> refaz. Sumiu arquivo -> refaz.
    """

    def __init__(self, caminho: Path) -> None:
        self.caminho = Path(caminho)
        self.dados: dict[str, Any] = {"estagios": {}, "duracoes": {}}
        if self.caminho.exists():
            try:
                self.dados = json.loads(self.caminho.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                self.dados = {"estagios": {}, "duracoes": {}}
        self.dados.setdefault("estagios", {})
        self.dados.setdefault("duracoes", {})

    @staticmethod
    def _assinar(assinatura: dict[str, Any]) -> str:
        return json.dumps(assinatura, sort_keys=True, ensure_ascii=False, default=str)

    def concluido(
        self,
        estagio: str,
        assinatura: dict[str, Any],
        artefatos: Iterable[Path],
    ) -> bool:
        registro = self.dados["estagios"].get(estagio)
        if not registro:
            return False
        if registro.get("assinatura") != self._assinar(assinatura):
            return False
        for artefato in artefatos:
            p = Path(artefato)
            if not p.exists():
                return False
            if p.is_file() and p.stat().st_size == 0:
                return False
        return True

    def marcar(
        self,
        estagio: str,
        assinatura: dict[str, Any],
        *,
        segundos: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.dados["estagios"][estagio] = {
            "assinatura": self._assinar(assinatura),
            "extra": extra or {},
        }
        if segundos is not None:
            self.dados["duracoes"][estagio] = round(float(segundos), 2)
        self.salvar()

    def extra(self, estagio: str) -> dict[str, Any]:
        return (self.dados["estagios"].get(estagio) or {}).get("extra", {})

    def limpar(self, estagios: Iterable[str] | None = None) -> None:
        if estagios is None:
            self.dados["estagios"] = {}
            self.dados["duracoes"] = {}
        else:
            for e in estagios:
                self.dados["estagios"].pop(e, None)
                self.dados["duracoes"].pop(e, None)
        self.salvar()

    def duracoes(self) -> dict[str, float]:
        return dict(self.dados.get("duracoes", {}))

    def salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_name(self.caminho.name + ".tmp")
        tmp.write_text(json.dumps(self.dados, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.caminho)


def chave_api_anthropic() -> str | None:
    """Le a chave APENAS do ambiente. Nunca de arquivo, nunca de outro projeto."""
    for nome in ("ANTHROPIC_API_KEY", "CLIPPER_ANTHROPIC_API_KEY"):
        valor = os.environ.get(nome, "").strip()
        if valor:
            return valor
    return None


def escrever_json(caminho: Path, dados: Any) -> Path:
    """Escrita atomica em UTF-8, para nao deixar artefato meio-gravado."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(caminho)
    return caminho


def ler_json(caminho: Path) -> Any:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def humanizar_bytes(n: float) -> str:
    n = float(n)
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{int(n)} B" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024.0
    return f"{n:.1f} PB"


def humanizar_tempo(segundos: float) -> str:
    segundos = max(0.0, float(segundos))
    h, resto = divmod(int(segundos), 3600)
    m, s = divmod(resto, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{segundos:.1f}s"
