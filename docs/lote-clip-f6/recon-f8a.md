# Recon — F8a "modelos" (antes do briefing)

Base: `3428504`. Nenhum código alterado.

## ⚠ O briefing do F8a não chegou

A fila (D7, §17, §19) nomeia o F8a como **"modelos"**, sem escopo. O que existe
registrado sobre ele são duas sementes:

| Semente | Origem | Conteúdo |
|---|---|---|
| S1 | §13 (P05), §13.2 | o **teto de blocos de 1 palavra** da legenda (hoje fixo em 3) vira parâmetro do modelo |
| S2 | §14.2 | **teto de 4 linhas para o gancho**, no validador v2 (recusa + o selecionador reescreve); o render nunca trunca; v1 congelado |

## O que já existe

- `clipper/modelo.py`: `Modelo` = legenda + composição, forma **aninhada**
  canônica, `avisos()` para chave desconhecida, `de_arquivo(caminho)` e
  `carregar(nome_ou_caminho)` — **ler um JSON qualquer do disco já funciona
  por dentro**.
- Os 4 modelos de fábrica moram em `clipper/presets/` (dentro do pacote).
- CLI e painel só oferecem `--preset <nome>` / um `<select>` com os de
  fábrica: **não há como o usuário usar um modelo próprio** sem editar o
  pacote.

## Leituras possíveis de "F8a — modelos"

- (A) **Modelos do usuário**: pasta própria fora do pacote (ex.
  `modelos/` na raiz ou `%APPDATA%`), `--preset caminho.json`, painel lista
  fábrica + usuário, "duplicar modelo de fábrica" como ponto de partida; mais
  S1 e S2. Sem editor visual.
- (B) A + **editor no painel** (campos principais, prévia de um quadro).
- (C) Só as sementes S1 + S2.

**Recomendação:** (A). Usa o que o `modelo.py` já faz, não toca em
render nem em `VERSAO` (modelo de fábrica não muda), e deixa o editor visual
para quando o formato tiver uso real.

## Perguntas

1. Escopo: A, B ou C (ou o briefing do F8a, se ele existir)?
2. Se A/B: onde mora a pasta de modelos do usuário — no repositório (ignorada
   pelo git) ou no perfil do Windows?
3. S2 mexe no contrato de seleção (validador v2 + prompt): entra no F8a ou
   fica para quando o prompt for revisto?
4. Branch/prefixo: seguir em `claude/charming-euler-02p9cf` com `[CLIP-F8a]`,
   ou o F8a espera o merge do F6.1 em `master`?
