# Relatório D4 — retomada local do CLIP-F6

> Relatório entregue no PARE da D4 e **aceito na D5** (§13 do RULINGS).
> Gravado no branch pela autorização da D5. Régua C.11: só contagens, bytes e
> hashes — nenhum conteúdo de fixture.

**SHA de referência:** `638fa69` (`origin/lote/clip-f6`). `master` em
`12fc1e2b`. A cópia do painel (`C:\Users\Micro\Desktop\ClipPro`) não recebeu
checkout.

## Resumo

- Passos 0–5 da D4 executados. Fixtures commitadas e enviadas; o D3 já tinha
  pousado; 25/25 estruturais verdes nesta máquina; físicas com 5 verdes e 1
  pulada (F-V2, defeito do harness).
- Colisão plano × código: as "2 provas de material real" não existiam em
  `provas/prova_f6.py`, e nenhuma diretiva autorizava escrevê-las.
- Bloqueio de merge novo: o render recusa todo clipe v2 que o próprio select
  gera (D-B). Mais 5 defeitos altos confirmados com reprodução executável.
  Nenhum conserto (a D4 não autorizava código).

## 0. Paridade e leitura

- `origin/master` = `12fc1e2b`; `origin/lote/clip-f6` = `7e903ab` (D3), igual
  ao último item do RULINGS. Reconferido antes do primeiro commit.
- `CLAUDE.md` e `RULINGS.md` lidos inteiros antes de qualquer pergunta. A D4
  entrou como §12 do RULINGS em `26a7be8` (primeiro ato), com o CLIP-F6.1 no
  §12.2.
- "C.11" não aparece no RULINGS nem no `CLAUDE.md`; aplicada pela definição
  dada na própria D4 (§12.1).

## 1. Worktree

`C:\Users\Micro\Desktop\ClipPro-clip-f6`, branch local `lote/clip-f6`
rastreando o remoto, com `out/` e `_teste/` próprios.

## 2. Fixtures (`638fa69`, enviado)

| Arquivo | Bytes | sha256 |
|---|---|---|
| `provas/fixtures/wetyO2gOOeU/resposta-v1.json` | 2026 | `ae5f52683dcaa0e46e0fb02ca3b61136c126bd65a511c8a14b7a516b618f8760` |
| `provas/fixtures/wetyO2gOOeU/transcricao.json` | 457062 | `8676f82ecdcfa5eb6b5bb2b8fb041b399e7a42451bce55a567c14e70199c1056` |

- sha256 igual na origem, no arquivo copiado e no blob do git.
- Os dois arquivos são 100% CRLF (41/41 e 23108/23108) e a máquina tem
  `core.autocrlf=true`: o add foi feito com `-c core.autocrlf=false`
  (`git ls-files --eol` → `i/crlf`). Durabilidade: Q9.

## 3. D3

Pousado em `7e903ab` (default de `de_preset` e os dois presets compostos).
E-C4 nesta máquina: `cortes` 960..1112 contra legenda a partir de 1142 → 30 px;
`cortes-editorial` 960..1104 contra 1188 → 84 px. E-R1, E-R2 e E-C1 verdes:
E1–E3 intactas e "conclusão ausente ⇒ 0 etapas" de pé.

## 4. Provas — `provas/prova_f6.py --fisicas` (Windows, ffmpeg 9.0.1)

**30 passaram, 1 pulou, 0 falharam.**

| Física | Resultado |
|---|---|
| F-G1 | passou: 1280×720, 44,1 kHz, 40,00 s |
| F-G2 | passou: faixa do topo 56,3 contra 0,7 no meio |
| F-V1 | passou: soma 23,00 s, medido 23,00 s |
| F-V2 | **pulou**: "não consegui ler o input_i do loudnorm nesta build do ffmpeg" |
| F-P1 | passou: fonte 25,0 s → clipe 15,00 s; mesmo ts 0,000 contra controle 2,215 |
| F-C1 | passou: faixa da conclusão 41,8 |

**F-V2 — defeito do harness, não da build.** `ffmpeg_utils.rodar` injeta
`-loglevel error` (`clipper/ffmpeg_utils.py:210`) e o loudnorm só imprime o
JSON no nível info. Medição avulsa do mesmo arquivo (23,000 s): −13,92 LUFS.
Um `-loglevel info` posterior prevalece (testado).

**Inspeção:** `_teste\inspecao-D4-638fa69\` no worktree (gancho t=1 s e
t=4 s, conclusão meio e fim, capa, clipe da conclusão). Ressalva: os renders
de prova não queimam legenda e usam conclusão de 1 linha.

## 5. Defeitos confirmados (nenhum consertado no D4)

Reproduzidos pelo fluxo real, só com dados sintéticos. D-A, D-B e D-C com dois
verificadores independentes cada.

| # | Defeito | Gravidade |
|---|---|---|
| D-B | Render recusa todo `selecao.json` v2 gerado pelo select: `_para_esquema` grava `duracao`/`inicio_mmss`/`fim_mmss` em cada segmento e o render aplica a checagem de forma da resposta (`render.py:807-811` → `select.py:498-503`). `clipper render` com código de saída 1; caminho do motor do painel com a mesma recusa. | bloqueia merge |
| D-A | Sobreposição entre clipes não adjacentes passa (`select.py:1032-1035`, invariante `1144-1156`). 3 aprovados, 0 problemas, 11,65 s em comum. | alta |
| D-C | `--api` nunca entrega v2: `required` exige `inicio`/`fim` e o validador rejeita esses campos junto com `segmentos`. 1536 itens conformes ao esquema, todos rejeitados. E-V5 prende o defeito (`prova_f6.py:888`). | alta |
| D-D | v2 em preset sem composição sai só com o 1º segmento (`render.py:1639-1664`): 15,567 s contra soma de 31,10 s. | alta |
| D-E | Capa velha sobrevive a re-encode; reaproveitamento pula o bloco P3 (`render.py:1729`, `1439`, `2218`). | alta |
| D-F | Janela do reframe no v2 é `[span_inicio, span_inicio+soma]` (`render.py:1475-1483`): amostra gordura e pode excluir segmentos. | alta |

Menores: E-C4 estima 152 px para a pílula de 2 linhas do `cortes` e a medida
com a fonte dá 156 px (vão real 26 px, ainda ≥ 24); E-R2 aceita qualquer
mudança na linha Style; log do render mostra o span; conclusão truncada sem
aviso. Não verificado (exige chave): `maxItems` no structured outputs.

## 6. As 18 perguntas depois da leitura

- **Resolvidas no RULINGS (13):** P02 (§10 D2 item 2), P04 (§2 E1–E3, Q2, Q3,
  Q6), P05 (§2 Q2 (B), §10 D2 item 4), P06 (por exclusão: lista fechada + §6),
  P08 (§2 Q6, §4), P10 (§2 R3, A3), P11 (§2 R2), P12 (§9 D1 P2, §10 D2 item 3,
  §11), P13 (§2 R4), P14 (§9 D1 P3, §10 D2 item 2, §2 Q4), P15 (§6), P17 (§5,
  §10 D2), P18 (§2 R7, §10.2).
- **Fato novo na P05:** com a fixture real, blocos de 1 palavra 36 → 18
  (`cortes`) e 39 → 17 (`cortes-editorial`), a maioria no meio do clipe,
  travada pelo teto 3.
- **Só no código (aceite genérico do §10 D2 item 1):** P01 (encaixe de 15 s
  por segmento, silencioso no v2), P03 (sem piso por segmento; contíguos
  aceitos), P07 (gancho truncado: 2 dos 5 reais no `cortes`), P16 (sem limite
  de gancho/título no validador).
- **Abertas:** P09 (v2 em F3 → D-D), P14 resíduo (regeneração da capa → D-E),
  P17 resíduo (as 2 provas de material real sem id nem autorização).

**Execução avulsa das 2 provas de material real** (não substitui prova
registrada): validador sobre `resposta-v1.json` → 5/5 aprovados, 0 problemas,
sem edição; quebrador sobre a transcrição real → 0 blocos com mais de 7
palavras e 0 com mais de 2 linhas nos 4 presets (1528/1528 palavras na
transcrição inteira).

## 7. Perguntas ao arquiteto

Q1 D-B · Q2 D-A · Q3 D-C · Q4 D-D · Q5 D-E · Q6 D-F · Q7 E-X1/E-X2 ·
Q8 F-V2 · Q9 `.gitattributes` · Q10 ratificação de P01/P03/P07/P16/P05.
Todas decididas na D5 (§13).

## 8. `prompt-v2.txt`

Colado na íntegra no relatório entregue; idêntico a
`docs/lote-clip-f6/prompt-v2.txt` em `638fa69`. Aprovado como texto na D5,
condicionado ao P5.

## 9. Checklist de merge no PARE da D4

- [ ] prompt-v2 revisado — pendente no D4 (aprovado condicionado na D5).
- [ ] 6 físicas + inspeção — 5/6; inspeção pendente.
- [ ] fixtures + 2 provas de material real — fixtures ✅; provas inexistentes.
- [ ] palavra do Bruno — pendente.
- Bloqueios novos: D-B (merge), D-A, D-C, D-D, D-E, D-F.
