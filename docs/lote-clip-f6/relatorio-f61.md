# Relatório — CLIP-F6.1 (higiene pós-merge)

Base: `origin/master` = `aa958d0`, conferido em 15/10 (paridade ok). Branch de
trabalho: `claude/charming-euler-02p9cf`. `master` intocado. Diretiva:
RULINGS §17 ("Q1 A, Q2 A, Q3 B — pode seguir").

## 1. Placar

| Suíte | Resultado |
|---|---|
| `provas/prova_f61.py --fisicas` (nova) | **10/10** verdes; contra o código de `aa958d0`, **10/10 vermelhas** (todas mordem) |
| `provas/prova_f6.py` estruturais | 32 passaram, 1 pulou (E-V5: sem o pacote `anthropic` aqui), 0 falharam — igual à partida |
| `provas/prova_f6.py --fisicas` | **11/11** físicas verdes. F-I1–F-I4 só depois de instalar no venv de teste mediapipe/opencv do lock + `libegl1` do sistema; sem eles falhavam igual no código de `aa958d0` (ambiente, não regressão) |

Ambiente desta medição: Linux, Python 3.13, ffmpeg do sistema, venv de teste
fora do repositório. **Não é o Windows do Bruno** — as físicas valem como
sinal, a prova oficial continua sendo o comando do §5.

## 2. Itens consertados

| # | Item | Conserto | Prova |
|---|---|---|---|
| 1 | Painel reenfileira pasta do terminal com opções padrão | `_retomar_interrompidos` pula job `do_terminal` | H-1 |
| 2 | Re-render falha com mp4 aberto (WinError 5) | (a) o stream do painel abre e fecha o arquivo a cada pedaço de 512 KB e para se o mp4 mudar no meio; (b) `_substituir()` no render repete o `replace()` só em `PermissionError`, esperas 0,2+0,4+0,8+1,6 s (~3 s), depois vira o erro acionável que já existia | H-2, H-3 |
| 3 | Lockfile sem fastapi/uvicorn/python-multipart | +9 entradas resolvidas para `win_amd64`/cp313 **com as pins atuais como restrição**: nenhuma versão existente mudou | (commit `deef1c0`) |
| 4 | Job do painel não grava `clipper.log` | `registro.em_arquivo()` liga o log do job e o desliga na saída (o worker roda job atrás de job; handler pendurado vazaria log de um job na pasta do outro) | H-4 |
| 5 | README e `--help` desatualizados | epílogo: `cortes-feed` → `cortes`; nota de que `clipper` = `python -m clipper`; README: comandos com `python -m clipper` e "recusa" reescrito (encaixa até 15 s, avisa a partir de 3 s, recusa o que não tem conserto) | — (texto) |
| 8 | Capa/publicacao.md velhos selados após `replace()` falho; `.tmp` órfão | `_atual()`: derivado mais velho que o mp4 conta como faltando (no atalho e no pacote); `_escrever_texto` apaga o `.tmp` na falha | H-5, H-6 |
| 9 | Capa nunca extraída no último intervalo de quadro (< 20 fps) | `_gravar_capa` tenta de novo 0,5 s antes quando o ffmpeg sai sem quadro | F-H1 |
| 10 | Recusa após conserto v1×v1 mostra início deslocado sem avisar | a mensagem diz "o início já tinha sido movido de X para Y para não encostar no clipe N" | H-7 |
| 11 | Mensagens de "clipe solto"/"item não é objeto" só conhecem v1 | reconhecem v2 e citam `segmentos` | H-8 |
| 13 | **Novo (recon de 15/10):** `DELETE /jobs/{id}` usava `job` sem defini-lo → `NameError`/500 em toda remoção | `saida, job = _exigir_job(...)` | H-9 |

## 3. ⚠ Colisões e itens NÃO feitos — decisão do arquiteto

**Item 12 (fator da E-C4) — colide com a geometria.** Subir
`_FATOR_ALTURA_LINHA` de 1,35 para 1,38 faz a pílula estimada bater com a
medida real (156 px), mas o mesmo fator estima a legenda, e o vão do `cortes`
cai de 30 para **20 px < 24**: a E-C4 reprovaria. Opções:
- (A) dois fatores — pílula 1,38 (medido) e legenda 1,35 — vão estimado do
  `cortes` = 26 px, igual ao medido. *Recomendado:* não muda nada renderizado.
- (B) baixar `conclusao_y` do `cortes` — muda o resultado, sobe `VERSAO`,
  invalida o cache.
- (C) aceitar a subestimativa e só documentar.

**Item 6 (provas F1–F4 nunca versionadas) — não feito.** Elas só existem como
texto nas mensagens dos commits `58ae7e9`…`2d8c2f9`. Transformar isso em
código é **escrever provas novas** a partir de descrição, e várias (ingestão,
whisper) exigem vídeo e modelo reais. Opções: (A) reescrever como provas
estruturais + físicas novas, num lote próprio; (B) versionar só o texto como
registro histórico; (C) desistir.

**Item 7 (`_trabalho/baixado.mp4`, ~1,76 GB) — não feito.** "Nada é apagado
sem aviso" é regra declarada do `ingest.py`. Apagar o bruto muda essa regra.
Opções: (A) apagar o bruto só quando o `fonte.mp4` veio de remux `-c copy`
(mesmos streams, nada se perde); (B) subcomando `clipper limpar` explícito;
(C) manter e só avisar, como hoje.

**Item 14 — novo, achado ao escrever a H-4, NÃO consertado.** Em
`ui/jobs.py`, `motor.montar_estagios()` roda **fora** do `try`: um erro
inesperado ali sobe para o worker, que só loga — o `job.json` fica em
`rodando` para sempre e a tela gira sem fim. O conserto é pequeno (pôr a
chamada dentro do mesmo `try`), mas está fora da lista; fica aqui para
autorização.

**Item 5, parcial:** dezenas de mensagens do CLI sugerem `clipper run ...`,
que não existe como executável. O README agora explica a convenção; trocar
todas as mensagens fica fora do escopo registrado.

## 4. Pendências herdadas

- D7 passos 3–5 (cópia do painel, aviso VERSAO 3, smoke pelo painel real):
  resultado ainda não relatado.
- O lockfile foi **resolvido**, não congelado de um ambiente real: confirmar
  no Windows que `pip install -r requirements.lock.txt` num venv limpo sobe o
  painel (é o roteiro do §5).

## 5. Roteiro para o Bruno (Windows)

```powershell
git fetch
git checkout claude/charming-euler-02p9cf
.venv\Scripts\python provas\prova_f61.py --fisicas
.venv\Scripts\python provas\prova_f6.py --fisicas

# lockfile: venv descartável, fora da cópia do painel
py -3.13 -m venv _teste\venv-lock
_teste\venv-lock\Scripts\pip install -r requirements.lock.txt
_teste\venv-lock\Scripts\python -c "import fastapi, uvicorn, multipart; print('ok')"
```

Smoke do item 2 (o que a prova não alcança no Linux): no painel, dar play num
clipe, pausar, clicar em re-renderizar o mesmo clipe → tem de terminar sem
`WinError 5`.

---

## 6. Rodada 2 — decisões do §18 ("12 A, 6 A, 7 A, 14 pode consertar")

| # | Feito | Prova |
|---|---|---|
| 12 | Dois fatores na E-C4: pílula 1,38 (estimativa 156 px = medida), legenda 1,35. Vão do `cortes` estimado 26 px = medido. Nada renderizado muda | E-C4 |
| 14 | `Fila._executar` ganhou rede do job inteiro: erro em `montar_estagios()` (ou qualquer ponto fora dos `try` de dentro) vira job em `erro`, com traceback no `clipper.log` | H-10 |
| 7 | Download por URL que virou `fonte.mp4` por remux é apagado e anunciado no log; reencodado, fica; arquivo local nunca é tocado (guarda: só `baixado.*` de dentro de `_trabalho/`). README atualizado | H-11, F-H2 |
| 6 | **Não feito aqui** — opção A é lote próprio; posição na fila a definir | — |

Mordida: H-10, H-11 e F-H2 falham no código de `5bf2699` (antes desta
rodada) e passam no novo.

**Custo aceito do item 7, declarado:** depois do descarte, `--force` na
ingestão ou `--reencodar-fonte` baixam o vídeo de novo. Rodar o mesmo comando
de novo não baixa nada (a ingestão é reaproveitada — conferido na F-H2).

Placar desta rodada: `prova_f61.py --fisicas` **13/13**;
`prova_f6.py --fisicas` **43 passaram, 1 pulou (E-V5, sem `anthropic` aqui), 0 falharam** — 11/11 físicas.

**Pergunta aberta:** onde entra o lote das provas F1–F4 (item 6 A) na fila
F8a → F8b → F8c → F9?

PARE aqui.
