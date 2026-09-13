"""O 'modelo de edicao': um objeto so, serializavel, com tudo que decide pixel.

Antes deste modulo o mesmo arquivo de preset era lido por DOIS carregadores
independentes que nao se conheciam: `legendas.Preset.de_dict()` pegava as
chaves do topo (fonte, cores, margens da legenda) e `composicao.de_preset()`
pegava a subarvore "composicao" (cartao, titulo, progresso, movimento,
audio). Quem quisesse "o estilo inteiro" carregava os dois e torcia para nao
esquecer um.

`Modelo` e esse par, embrulhado e nomeado. O render passa a receber UM objeto
e desenhar a partir dele.

FORMATO DE ARQUIVO -- decisao de arquitetura, nao detalhe de implementacao:

  A forma ANINHADA (a dos quatro presets em clipper/presets/) e a forma
  canonica de ARQUIVO. E ela que se escreve, se le e se versiona.

  A forma FLAT que `dataclasses.asdict()` produz e identidade INTERNA: serve
  a `impressao()` e ao cache de clipes, e nunca vira arquivo.

  As duas NAO sao intercambiaveis, e a assimetria e real, nao descuido:
  `de_preset()` resolve `cartao.fracao_altura` (um numero) em quatro campos
  de pixel (largura, altura, x, y) e apara faixas pelo caminho
  (`composicao.py:287-301`). Reconstruir a fonte a partir do resolvido
  perderia a fracao e devolveria arredondamento. Por isso o Modelo GUARDA a
  fonte aninhada em vez de tentar deduzi-la -- `para_json()` devolve o que
  entrou, normalizado, e o round-trip fecha por construcao.

CHAVE DESCONHECIDA AVISA, NAO REJEITA. Os carregadores de hoje silenciam o
que nao reconhecem (`legendas.py:74` filtra por campo do dataclass;
`_num/_txt/_flag` caem no padrao quando o caminho nao existe). Isso e
tolerante na hora certa -- preset de versao futura nao derruba render -- mas
transforma um erro de digitacao em nada acontecendo. `Modelo.avisos()`
devolve a lista das chaves ignoradas para quem quiser mostrar.

Convencao deste arquivo: comentarios e docstrings em PT-BR sem acento;
mensagens dirigidas ao usuario em PT-BR com acentuacao correta.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clipper import composicao, legendas

# Chaves que os carregadores realmente consomem. Existe para UMA coisa: dizer
# o que e desconhecido. Nao valida tipo nem faixa -- disso cuidam _num/_txt/
# _flag, que ja aparam e ja tem padrao. Um dict aqui e um nivel aninhado; uma
# tupla/lista e um conjunto de folhas.
_CONHECIDAS: dict[str, Any] = {
    # identidade + legenda (topo do arquivo: os campos de legendas.Preset)
    "__folhas__": (
        "nome", "descricao",
        "fonte", "tamanho", "negrito", "maiusculas",
        "cor_falada", "cor_por_falar", "cor_contorno", "cor_sombra",
        "contorno", "sombra", "espacamento",
        "margem_lateral", "margem_inferior",
        "max_palavras_linha", "max_caracteres_linha",
        "cor_destaque", "pop_escala", "pop_subida_ms", "pop_descida_ms",
        "pop_volta_ms", "largura_por_medida", "arquivo_fonte",
        # conformidade de legenda (F6)
        "min_palavras_linha", "gap_maximo_fusao_s", "max_linhas_bloco",
        "destaque_minimo_letras", "margem_direita",
    ),
    "composicao": {
        "__folhas__": ("ativo", "fade_s"),
        "cartao": {
            "__folhas__": (
                "fracao_altura", "raio",
                "traco_largura", "traco_cor", "traco_opacidade",
            ),
            "sombra": {
                "__folhas__": ("dx", "dy", "sigma", "opacidade", "expansao", "cor"),
            },
        },
        "fundo": {
            "__folhas__": ("proxy_largura", "sigma", "escurecer", "saturacao", "vinheta"),
        },
        "titulo": {
            "__folhas__": (
                "ativo", "fonte", "arquivo", "tamanho", "tamanho_minimo",
                "maiusculas", "cor", "pilula_cor", "pilula_opacidade",
                "altura", "raio", "padding_h", "largura_maxima",
                "alinhamento", "x", "y", "deslize_s", "fade_s",
                "acento", "acento_cor", "acento_largura", "acento_altura",
                "acento_gap",
            ),
        },
        "gancho": {
            "__folhas__": ("ativo", "duracao_s", "fade_saida_s", "y"),
        },
        "conclusao": {
            "__folhas__": ("duracao_s", "fade_s", "y"),
        },
        "juncao": {
            "__folhas__": ("crossfade_audio_s",),
        },
        "zona_segura": {
            "__folhas__": ("topo", "base"),
        },
        "progresso": {
            "__folhas__": (
                "ativo", "altura", "recuo", "y",
                "trilho_cor", "trilho_opacidade", "cor", "opacidade",
                "contorno", "contorno_cor", "contorno_opacidade",
            ),
        },
        "scrim": {
            "__folhas__": ("ativo", "y_inicio", "y_fim", "opacidade", "cor"),
        },
        "movimento": {
            "__folhas__": (
                "kenburns_ate", "prescale",
                "punch_ganho", "punch_duracao", "punch_maximo",
                "punch_inicio_minimo", "punch_espacamento", "punch_antecipar",
            ),
        },
        "audio": {
            "__folhas__": ("eq", "i", "tp", "lra", "pitch_razao"),
        },
    },
}


def _desconhecidas(dados: Any, esquema: dict[str, Any], prefixo: str = "") -> list[str]:
    """Caminhos presentes em 'dados' que o esquema nao declara."""
    if not isinstance(dados, dict):
        return []
    folhas = set(esquema.get("__folhas__", ()))
    ramos = {k: v for k, v in esquema.items() if k != "__folhas__"}
    fora: list[str] = []
    for chave, valor in dados.items():
        caminho = f"{prefixo}{chave}"
        if chave in ramos:
            fora.extend(_desconhecidas(valor, ramos[chave], f"{caminho}."))
        elif chave not in folhas:
            fora.append(caminho)
    return fora


def _normalizar(dados: Any) -> Any:
    """Copia profunda com chaves ordenadas: duas fontes iguais viram bytes iguais."""
    if isinstance(dados, dict):
        return {k: _normalizar(dados[k]) for k in sorted(dados)}
    if isinstance(dados, list):
        return [_normalizar(v) for v in dados]
    return dados


@dataclass(frozen=True)
class Modelo:
    """Um estilo de edicao inteiro: identidade, legenda e composicao.

    `composicao` e None quando o preset nao traz o bloco -- e o caminho da F3,
    recorte 9:16 cheio com legenda por cima, sem cartao.

    A fonte aninhada viaja como TEXTO JSON normalizado (`fonte_json`) e nao
    como dict: assim o dataclass continua congelado e comparavel de verdade,
    e `para_json()` nunca devolve uma referencia que alguem possa mutar por
    baixo.
    """

    nome: str
    descricao: str
    legenda: legendas.Preset
    composicao: composicao.Composicao | None
    fonte_json: str = field(repr=False)
    _avisos: tuple[str, ...] = field(default=(), repr=False)

    # ---------------------------------------------------------------- carga

    @classmethod
    def de_dict(cls, dados: Any, nome: str = "") -> "Modelo":
        """Carrega da forma ANINHADA -- a canonica de arquivo."""
        if not isinstance(dados, dict):
            raise TypeError("um modelo é um objeto JSON, não " + type(dados).__name__)
        nome = str(nome or dados.get("nome") or "").strip() or "sem-nome"
        return cls(
            nome=nome,
            descricao=str(dados.get("descricao") or ""),
            legenda=legendas.Preset.de_dict({**dados, "nome": nome}),
            composicao=composicao.de_preset(dados, nome),
            fonte_json=json.dumps(_normalizar(dados), ensure_ascii=False, sort_keys=True),
            _avisos=tuple(_desconhecidas(dados, _CONHECIDAS)),
        )

    @classmethod
    def de_arquivo(cls, caminho: Path | str) -> "Modelo":
        caminho = Path(caminho)
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return cls.de_dict(dados, nome=caminho.stem)

    @classmethod
    def de_fabrica(cls, nome: str) -> "Modelo":
        """Um dos modelos que vem no projeto (clipper/presets/<nome>.json)."""
        from clipper import config

        return cls.de_arquivo(config.DIR_PRESETS / f"{nome}.json")

    # ------------------------------------------------------------- entrega

    def para_json(self) -> dict[str, Any]:
        """A forma ANINHADA canonica. Recarregavel por `de_dict()` sem perda."""
        return json.loads(self.fonte_json)

    def gravar(self, caminho: Path | str) -> Path:
        """Grava a forma canonica. UTF-8 e LF explicitos: o alvo e o Windows."""
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(
            json.dumps(self.para_json(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return caminho

    def avisos(self) -> list[str]:
        """Chaves que o arquivo traz e nenhum carregador consome."""
        return list(self._avisos)

    # ---------------------------------------------------------- identidade

    @property
    def compoe(self) -> bool:
        """True quando este modelo desenha cartao (caminho F4a), nao recorte cheio."""
        return self.composicao is not None

    def impressao(self, *, pitch: bool = False) -> str:
        """Identidade INTERNA do estilo -- entra no cache, nunca em arquivo.

        Delega a `Composicao.impressao()` quando ha composicao, para que o
        cache ja gravado por ela continue valendo bit a bit. Sem composicao
        nao havia impressao nenhuma antes deste modulo, e continua nao
        havendo: devolve string vazia e o chamador decide.
        """
        if self.composicao is None:
            return ""
        return self.composicao.impressao(pitch=pitch)


def carregar(nome_ou_caminho: str | Path) -> Modelo:
    """Aceita nome de modelo de fabrica ou caminho de arquivo."""
    caminho = Path(nome_ou_caminho)
    if caminho.suffix.lower() == ".json" and caminho.is_file():
        return Modelo.de_arquivo(caminho)
    return Modelo.de_fabrica(str(nome_ou_caminho))
