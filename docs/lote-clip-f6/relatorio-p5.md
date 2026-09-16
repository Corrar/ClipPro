# Relatório do P5 — integração v2

> Relatório entregue no PARE do P5 (código em `7585e1b`) e **aceito na D6**
> (§14 do RULINGS). Gravado no branch pela autorização da D6. Régua C.11: só
> contagens, bytes, hashes e referências de linha — nenhum conteúdo de fixture.
> A seção 7 registra a execução da condição da D6 sobre a VERSAO.

## Resumo

- As dez decisões da D5 (§13) e os menores foram implementados, cada um com
  prova que morde, **vermelha antes de verde**.
- Placar final em `7585e1b`, Windows, ffmpeg 9.0.1: **44/44** — 33 estruturais
  e 11 físicas, nenhuma pulada. Rodada vermelha, registrada na mensagem do
  commit `cf3fabe`: 31 passaram, 1 pulou, 12 falharam.
- As provas de integração novas atravessam o ponto de entrada real: CLI em
  subprocesso e a fila do painel (`ui/jobs.py`). As conferências de unidade
  estão declaradas no cabeçalho da seção P5 de `provas/prova_f6.py`.
- Render real do vídeo de teste pelo CLI, em 2 segmentos, para a inspeção do
  Bruno (seção 4).
- Revisão adversarial independente em cópias descartáveis: 2 defeitos no Q10 e
  5 provas frouxas, todos consertados e confirmados por mutação.

## 1. Commits

| SHA | O quê |
|---|---|
| `1342a30`, `ed7e22e` | D5 no RULINGS §13 (com §13.1) e relatório D4 gravado |
| `cf3fabe` | Provas novas, **vermelhas**: 31 passaram, 1 pulou, 12 falharam |
| `a82b1a0` | Q1: segmento só com `inicio`/`fim` |
| `aa33e12` | Q6: reframe amostra dentro dos segmentos |
| `a10b83f` | Q4: recusa v2 de 2+ segmentos sem composição |
| `a7933db` | Q5: capa e publicação acompanham o MP4 |
| `9148aa1` | Q2, Q3 e Q10 no select |
| `4bda30e` | Q9: `.gitattributes` |
| `6231f01` | Q10: gancho nunca cortado, mais os menores |
| `b935dc3` | Q8: F-V2 |
| `00da6ef` | Revisão: fusão não estoura o teto, aviso na costura, nota "1, 2 e 3" |
| `7585e1b` | Revisão: provas frouxas passam a morder |

## 2. Decisões da D5: antes e depois

| Q | Prova | Antes | Depois |
|---|---|---|---|
| Q1 D-B | E-I1 (CLI), F-I1 (CLI e painel) | render recusava o v2 | MP4 de 23,30 s = soma, pelo CLI e pelo painel |
| Q2 D-A | E-I2 (3 clipes, CLI) | `rc=0` com 11,65 s em comum | recusado apontando "clipe 1 × clipe 3" |
| Q3 D-C | E-V5 (esquema × validador; `select --api` com SDK real e API falsa local) | v2 fora do esquema | v2 passa, 1 chamada só; `maxItems` **não verificado** (sem chave) |
| Q4 D-D | E-I5, F-I2 | não recusava | recusa com motivo e sugestão executável; 1 segmento renderiza inteiro |
| Q5 D-E | F-I3 (4 rodadas pelo CLI) | capa velha (diferença média 3,103) | capa = quadro do `capa_ts` atual nas 4 (0,000); apagadas voltam sem re-encode |
| Q6 D-F | F-I4 (espião só-registra sobre o CLI) | janela 0,50–23,80 s | janelas dentro de 0,50–12,15 s e 47,30–58,95 s |
| Q7 | E-X1, E-X2 | não existiam | 5/5 clipes reais aprovados; 0 blocos com mais de 7 palavras ou mais de 2 linhas |
| Q8 | F-V2 | pulava | −13,92 LUFS |
| Q9 | E-F1 | sem `.gitattributes` | `text: unset`; hashes reais intactos |
| Q10 P01 | E-I3 | sem aviso no v2 | aviso por segmento pedido, inclusive na costura fundida |
| Q10 P03 | E-I4 | 2 segmentos | colados fundidos com nota; pausa real separada; sem fusão acima de 90 s |
| Q10 P07 | F-G3, F-I1 | 2 de 5 ganchos reais truncados | 0 truncados; texto conferido exato, inclusive espaços |
| Menores | E-R2, F-I1 | — | Style aceita só MarginV (com controle); log mostra a soma; avisos no log e no `relatorio.md`; −14,19 LUFS medido no MP4 do pipeline |

Revisão adversarial: cada conserto revertido numa cópia deixou a prova dele
vermelha no motivo certo; contrato v1 idêntico byte a byte a `638fa69` com a
resposta real; `ui/`, `prompt_selecao.py`, `prompt-v2.txt` e a cadeia de áudio
sem diff; nenhum conteúdo de fixture em saídas, commits ou documentos.

## 3. Leituras do executor (confirmadas como rulings na D6)

1. Q4: a recusa vale só para v2 de 2+ segmentos; 1 segmento renderiza inteiro
   (F-I2: 23,35 s esperados, 23,37 s medidos).
2. Q10/P03: "colado" = blocos consecutivos com lacuna ≤ 1,2 s. Na fixture real,
   28 de 171 pares consecutivos passam de 1,2 s.
3. Q10/P03: sem fusão quando fundir estouraria 90 s.
4. Q10/P07: gancho sem teto de linhas; palavra mais larga que a caixa quebra
   dentro dela.

## 4. Inspeção para o Bruno

- Render real pelo CLI do clipe mais longo da resposta real, em 2 segmentos:
  42,86 s mantidos, 31,73 s de gordura removida; MP4 de 42,876 s,
  −13,98 LUFS; reframe com rosto em 21/21 amostras; legenda queimada com
  36 blocos (máximo 3 palavras, 1 linha); gancho real em 2 linhas; conclusão de
  teste neutra em 2 linhas em y=960, acima da legenda; capa 9:16 composta,
  do 2º segmento.
- Quadros e capa: `_teste\inspecao-P5-7585e1b\` no worktree (seção 7). O MP4
  fica em `out\inspecao-p5-wetyo2gooeu\clips\` e não é commitado.

## 5. Caso extremo do gancho (§11.1), medido pela F-G3

| Preset | Pior caso ≤ 90 caracteres | PT caixa alta, 90 | Ganchos reais |
|---|---|---|---|
| `cortes` | 9 linhas, 446 px, base y=642 | 4 linhas, base y=412 | até 3 linhas |
| `cortes-editorial` | 7 linhas, 262 px, base y=458 | 3 linhas, base y=326 | 2 linhas |

Aprovado como está na D6 (§14.1). Teto de 4 linhas na SELEÇÃO registrado como
semente do F8 (§14.2).

## 6. Limites de baixa gravidade

Registrados no CLIP-F6.1 (RULINGS §14.3, itens 8 a 12).

## 7. Execução da condição da D6 sobre a VERSAO

Condição: apagar do `out/` do worktree todo render anterior a `7585e1b`
(commitado em 16/09 12:30), com confirmação por listagem.

**Antes.** O `out/` do worktree tinha um único job (`inspecao-p5-wetyo2gooeu`),
com um render de 16/09 11:33–11:34 (anterior a `7585e1b`), VERSAO 3, gancho em
2 linhas e não truncado. Arquivos de render: 3 em `clips/` (MP4, capa,
publicação), `metadados.json`, `relatorio.md`, 6 em `_trabalho/` (5 PNG de
composição — cartão atrás, frente e máscara, pílula do gancho e pílula da
conclusão — e o `.ass`), e a entrada `render` no `.estado.json`.

**Apagado.** Os 11 arquivos acima e a entrada `render` do `.estado.json`
(por `Estado.limpar`). Mantidos, por não serem render: `fonte.mp4`,
`audio.wav`, `fonte.json`, transcrição, energia, seleção, prompt e log.

**Depois (listagem).** 0 arquivos de render em `out/` (MP4 de clipe, capa,
publicação, metadados, relatório, `.ass` e PNG de composição); `.estado.json`
com os estágios `energia`, `ingestao`, `selecao` e `transcricao`.

**Fora do escopo, registrado.** `_teste/` do worktree não é `out/` e não é cache
do pipeline, mas guarda coisas anteriores a `7585e1b` (conferido por listagem
independente): o clipe de prova montado à mão pelo harness na inspeção do D4
(gancho sintético curto, sem truncamento, sem metadado de cache); o vídeo-fonte
lavfi de 70 s das provas do P5 (`_teste/out-prova-f6/p5-videos/`, entrada, não
render); 3 PNG de cartão do harness em `_teste/out-prova-f6/_trabalho/`; e a
pasta `_teste/inspecao-P5-b935dc3/` com os quadros e a capa do render apagado —
byte a byte iguais aos da pasta nova. Ao todo, 2 MP4, 2 JPG e 10 PNG. Nada foi
apagado ali.

**Render de inspeção refeito.** Pelo CLI, no código de `7585e1b` (o commit da
D6 só toca o RULINGS). A seleção foi conferida idêntica à anterior; os
3 quadros e a capa saíram **byte a byte iguais** aos do render apagado
(sha256 comparado). MP4 de 42,876 s, −13,98 LUFS, VERSAO 3, gancho em
2 linhas, não truncado. Quadros e capa em `_teste\inspecao-P5-7585e1b\`.

## 8. Checklist de merge

| | Item | Estado |
|---|---|---|
| 1 | `prompt-v2.txt` revisado e aprovado | ✅ (D5; condição do P5 cumprida, D6) |
| 2 | Físicas verdes + inspeção visual do Bruno | físicas ✅ 11/11; **inspeção pendente** |
| 3 | Fixtures reais + 2 provas de material real | ✅ |
| 4 | Bloqueadores do P5 | ✅ (D6) |
| 5 | Palavra do Bruno ("f6 ok") | **pendente** |

Depois do "f6 ok": PARE aguardando a D7 (procedimento de merge).
