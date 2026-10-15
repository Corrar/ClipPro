"""O contrato de um trabalho: o que a fila entrega ao worker.

POR QUE UM CONTRATO PROPRIO, E NAO motor.Opcoes DIRETO: o pedido vem de fora
(da conta de um usuario, pela fila da nuvem) e roda no PC de quem opera o
worker (RULINGS §27, G3). Tudo que chega aqui e entrada NAO CONFIAVEL:

- 'entrada' nunca e caminho local. Arquivo e uma CHAVE do deposito; link so
  http(s) para host publico. ingest.resolver_origem() aceita qualquer caminho
  que exista no disco -- repassar o texto cru deixaria um usuario pedir um
  arquivo do PC do operador.
- 'preset' so do catalogo de fabrica, por NOME (nunca caminho: F8a Q6).
- tipos conferidos de verdade: "3" nao e 3 (o D5 do PENDENCIAS mostrou o
  TypeError que isso vira no meio do render).
- opcoes de maquina (modelo do whisper, threads, forcar, resposta manual) NAO
  vem do pedido: sao do operador.

Convencao: comentarios e docstrings em PT-BR sem acento; mensagens dirigidas
ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit

from clipper import config

# Ids viram nome de pasta no PC do operador: so o alfabeto do slug.
_RE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_RE_CONTA = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# Chave do deposito: um nome de arquivo, sem pasta. Ponto inicial proibido
# (arquivo oculto) e '..' recusado a parte.
_RE_CHAVE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

TIPOS_DE_ENTRADA = ("link", "arquivo")
N_MAXIMO = 20  # o mesmo teto do painel (ui/estaticos/index.html, campo 'n')
ESTRATEGIA_MAXIMA = 500
LINK_MAXIMO = 2048
# 600 min = 10 h de video: acima disso o worker do beta ficaria dias ocupado
# (~0,7x a duracao so de transcricao, medida do README).
LIMITE_MINUTOS_MAXIMO = 600

CAMPOS = ("id", "conta", "entrada", "n", "preset", "estrategia", "limite_minutos")


class ErroContrato(ValueError):
    """Pedido recusado antes de tocar o motor. Leva TODOS os problemas."""

    def __init__(self, problemas: list[str]) -> None:
        self.problemas = list(problemas)
        super().__init__("; ".join(self.problemas))


@dataclass(frozen=True)
class Trabalho:
    id: str
    conta: str
    entrada_tipo: str  # "link" ou "arquivo"
    entrada_valor: str  # URL, ou chave do deposito
    n: int
    preset: str
    estrategia: str
    limite_minutos: int
    # Chaves que vieram e nao sao do contrato: avisam, nao recusam (a mesma
    # regra do Modelo.avisos(), CLAUDE.md §6).
    avisos: tuple[str, ...] = field(default=(), compare=False)

    @classmethod
    def de_dict(cls, dados: Any, presets: tuple[str, ...] | None = None) -> "Trabalho":
        if not isinstance(dados, dict):
            raise ErroContrato(["o trabalho não é um objeto JSON."])
        catalogo = presets if presets is not None else presets_de_fabrica()
        problemas: list[str] = []

        id_ = dados.get("id")
        if not (isinstance(id_, str) and _RE_ID.match(id_)):
            problemas.append("'id' tem de ser texto com letras minúsculas, números e hífen (até 64).")

        conta = dados.get("conta")
        if not (isinstance(conta, str) and _RE_CONTA.match(conta)):
            problemas.append("'conta' tem de ser um identificador de até 64 caracteres.")

        tipo, valor = "", ""
        entrada = dados.get("entrada")
        if not isinstance(entrada, dict):
            problemas.append("'entrada' tem de ser um objeto com 'tipo' e 'valor'.")
        else:
            tipo = entrada.get("tipo") if isinstance(entrada.get("tipo"), str) else ""
            valor = entrada.get("valor") if isinstance(entrada.get("valor"), str) else ""
            if tipo not in TIPOS_DE_ENTRADA:
                problemas.append("o tipo da entrada tem de ser 'link' ou 'arquivo'.")
            elif tipo == "link":
                problema = problema_do_link(valor)
                if problema:
                    problemas.append(problema)
            elif not (_RE_CHAVE.match(valor) and ".." not in valor):
                problemas.append("a chave do arquivo enviado é inválida.")

        n = dados.get("n")
        if not _inteiro(n) or not 1 <= n <= N_MAXIMO:
            problemas.append(f"'n' tem de ser um número inteiro de 1 a {N_MAXIMO}.")

        preset = dados.get("preset")
        if not (isinstance(preset, str) and preset in catalogo):
            opcoes = ", ".join(catalogo) or "nenhum"
            problemas.append(f"'preset' tem de ser um dos visuais disponíveis ({opcoes}).")

        estrategia = dados.get("estrategia", config.ESTRATEGIA_PADRAO)
        if not isinstance(estrategia, str) or not estrategia.strip():
            problemas.append("'estrategia' tem de ser um texto não vazio.")
        elif len(estrategia) > ESTRATEGIA_MAXIMA:
            problemas.append(f"'estrategia' passa de {ESTRATEGIA_MAXIMA} caracteres.")

        limite = dados.get("limite_minutos")
        if not _inteiro(limite) or not 1 <= limite <= LIMITE_MINUTOS_MAXIMO:
            problemas.append(
                f"'limite_minutos' tem de ser um número inteiro de 1 a {LIMITE_MINUTOS_MAXIMO}."
            )

        if problemas:
            raise ErroContrato(problemas)

        extras = tuple(sorted(k for k in dados if k not in CAMPOS and not str(k).startswith("_")))
        return cls(
            id=id_, conta=conta, entrada_tipo=tipo, entrada_valor=valor, n=n,
            preset=preset, estrategia=estrategia.strip(), limite_minutos=limite,
            avisos=tuple(f"chave desconhecida ignorada: '{k}'" for k in extras),
        )

    def para_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conta": self.conta,
            "entrada": {"tipo": self.entrada_tipo, "valor": self.entrada_valor},
            "n": self.n,
            "preset": self.preset,
            "estrategia": self.estrategia,
            "limite_minutos": self.limite_minutos,
        }


def _inteiro(valor: Any) -> bool:
    # bool e subclasse de int em Python: True passaria como 1.
    return isinstance(valor, int) and not isinstance(valor, bool)


def presets_de_fabrica() -> tuple[str, ...]:
    """Os nomes em clipper/presets/*.json -- a mesma leitura do --help do CLI."""
    try:
        return tuple(sorted(p.stem for p in config.DIR_PRESETS.glob("*.json") if p.stem))
    except OSError:
        return ()


def problema_do_link(url: str) -> str | None:
    """Recusa o que nao e link publico http(s). Sem rede: so o texto.

    A resolucao de nome (host publico que aponta para a rede de casa) e do
    executor, que pode consultar o DNS: ver host_privado(resolver=...).
    """
    if not url or len(url) > LINK_MAXIMO:
        return "o link está vazio ou é longo demais."
    if any(c.isspace() for c in url):
        return "o link não pode ter espaços."
    try:
        partes = urlsplit(url)
        host = partes.hostname or ""
    except ValueError:
        return "o link não é um endereço válido."
    if partes.scheme not in ("http", "https"):
        return "o link tem de começar com http:// ou https://."
    if not host:
        return "o link não tem endereço de site."
    if partes.username or partes.password:
        return "o link não pode trazer usuário ou senha."
    if host_privado(host):
        return "o link aponta para um endereço local ou privado."
    return None


def host_privado(
    host: str,
    resolver: Callable[[str], list[str]] | None = None,
) -> bool:
    """True se o host e local/privado. Com 'resolver', confere tambem o DNS.

    POR QUE: no beta o worker roda no PC do operador (§27, G3). Um link para
    192.168.x ou 'localhost' faria o yt-dlp do worker buscar algo da rede de
    casa a pedido de um usuario de fora.
    """
    nome = host.strip().strip("[]").lower().rstrip(".")
    if not nome:
        return True
    if nome == "localhost" or nome.endswith((".localhost", ".local", ".internal", ".lan")):
        return True
    if _ip_privado(nome):
        return True
    if resolver is None:
        return False
    try:
        enderecos = resolver(nome)
    except OSError:
        # Nome que nao resolve nao e privado: o ingest falha depois com a
        # mensagem propria dele ("o yt-dlp não conseguiu ler...").
        return False
    return any(_ip_privado(e) for e in enderecos)


def _ip_privado(texto: str) -> bool:
    try:
        ip = ipaddress.ip_address(texto.split("%", 1)[0])
    except ValueError:
        return False
    return not ip.is_global or ip.is_multicast


def resolver_dns(host: str) -> list[str]:
    """Todos os enderecos do host, IPv4 e IPv6 (o resolver de verdade)."""
    import socket

    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
