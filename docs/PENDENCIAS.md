# Pendências do ClipPro — estado em 16/10/2026

## Retomada (pausa de 16/10, RULINGS §31)

Antes de qualquer ação, ler esta seção e o `RULINGS.md` do §29 em diante.
Depois, conferir a paridade: o `master` deve estar em `b85d323` e o branch
`claude/loving-newton-bykd21` igual ao `origin`. Se algum dos dois tiver
andado, PARE e reporte.

**Onde estamos**

- **No `master`** (merge do PR #1 pelo Bruno, §30.2):
  - o motor local com o F6.1;
  - a nuvem N-1 a N-4: worker, app, créditos, compra pelo Mercado Pago
    desligada, termos e privacidade em rascunho.
- **Só no branch:** a N-5, o design novo do app (`relatorio-n5.md`, telas
  em `docs/nuvem/telas/` 1–8).
- **O app não está no ar.** Na Vercel só existe o projeto `clippro`, que é o
  site. Não há projeto `clippro-app` (conferido em 16/10).
- **Placar no Linux:**

  | Suíte | Passaram | Pularam | Falharam |
  |---|---|---|---|
  | N-5 | 3 | 0 | 0 |
  | N-2 | 7 | 0 | 0 |
  | N-3 | 6 | 0 | 0 |
  | N-1 | 16 | 1 (N-F4, contas reais) | 0 |
  | F6.1 | 13 | 0 | 0 |
  | F6 | 44 | 0 | 0 |

**O que espera o Bruno, por ordem de impacto**

1. **PR da N-5 para o `master`?** O executor não abre PR sem pedido.
2. **Q-N5-1:** mostrar a miniatura do YouTube nas prévias de pedido por
   link? Exige pedir a `i.ytimg.com` e mudar a Política de privacidade.
   Recomendação: não.
3. **Contas da nuvem**, pelo `docs/nuvem/roteiro-contas.md` §1–§9:
   - teto de gasto na Anthropic;
   - Supabase com as migrações 001, 002 e 003;
   - R2 com CORS e prazos de guarda;
   - projeto `clippro-app` na Vercel, com produção no `master`;
   - convites;
   - depois, rodar a N-F4 no Windows.
4. **Para vender:** V1–V6 do `relatorio-n3.md` (preço dos pacotes, Vercel
   Pro, revisão jurídica, credenciais do Mercado Pago, sandbox, nota fiscal).
5. **Conferência pós-merge do F6.1 no Windows:** W1–W3 e W5 (§2 abaixo).
6. **Site público e licença:** a reescrita do site fica para o lançamento
   (N9 = B); a licença é a S5.

**O que o executor faz ao voltar**

- Responde ao que o Bruno decidir sobre os itens 1 e 2.
- Se o projeto `clippro-app` já existir, confere o deploy pela Vercel.
- Sem pedido, não começa código novo. O F8a vem depois do núcleo da nuvem
  (§29.2), começando pela Q17.

**Ambiente da sessão (para o executor), que o container novo perde:**

- **Postgres 16 de teste** para N-F3, N2-F1 e N3-F1. Suba com
  `pg_ctlcluster 16 main start` e use
  `CLIPPRO_PROVA_PG=postgresql://prova:prova@127.0.0.1:5432/clippro_prova`.
- **Node com `playwright` global** para N2-F2, N3-F2 e N5-F1.
- **Venv das provas** com as versões do lockfile.

---

## Histórico desta lista (15/10)

> Gravado a pedido do Bruno ("salve na memória as pendências e continuamos
> depois"). Ponto de retomada da próxima sessão: **ler este arquivo e o
> `docs/lote-clip-f6/RULINGS.md` (§16 em diante) antes de qualquer ação.**
> Branch de trabalho: `claude/loving-newton-bykd21` desde o RULINGS §23
> (fast-forward do `claude/charming-euler-02p9cf`, que fica congelado em
> `0295359` com o mesmo código). **`master` em `b85d323`**: o Bruno fez o
> merge do PR #1 em 15/10 (RULINGS §30.2), com tudo até `c1d15b2`. A N-5
> (design) está só no branch.

## Fila (RULINGS §17, §19, §21)

CLIP-F6.1 (feito, aguarda Windows + merge) → **site** (no ar, decisões
pendentes) → **F8a** (pausado, perguntas pendentes) → F8b → F8c → provas
F1–F4 → F9 "paridade". F7 (narração) guardada.

> **⚠ Em aberto desde o §24: ClipPro na nuvem** (conta, créditos, geração no
> servidor). Revoga o §17 Q3 = B. Perguntas **N1–N10** em
> `docs/lote-clip-f6/relatorio-pedido-nuvem.md`; a **N8** redefine esta fila.
> Até a resposta: PARE, e as perguntas do F8a ficam em espera.
> Respondidas no §25–§26: N1–N5 A, N6 Mercado Pago, N7 A (300 créditos =
> 5 h de vídeo por cadastro), N8 A, N9 B, N10 "sem CNPJ; redija, eu reviso".
> Abertas: **G1–G4** ("tudo free tier" colide com Vercel Hobby não comercial,
> servidor grátis pequeno e IA paga), em `relatorio-pedido-nuvem.md` §6.
> G1–G4 respondidas no §27 (beta fechado grátis, Anthropic com teto, PC do
> Bruno como worker, N-1 aberta). **N-1: worker pronto e provado**
> (`relatorio-n1.md`, §27.2). Abertas: **P1** (Supabase + R2?) e **P2** (tokens
> por trabalho). Ação do Bruno: teto de gasto no console da Anthropic;
> `.venv\Scripts\python provas\prova_n1.py --fisicas` no Windows.
> **§28: P1 = Supabase + R2, P2 = tokens por trabalho — feitos** (relatório
> da N-1 §7). Pendente do Bruno: criar as contas e rodar a N-F4 seguindo
> `docs/nuvem/roteiro-contas.md`.
> **§29: delegação** ("o restante faça com o que achar recomendado").
> **N-2 (app) feita e provada** (`relatorio-n2.md`). Do Bruno: roteiro §7
> (Auth, Google, convites, CORS do R2, projeto Vercel `clippro-app` com
> produção pública e no branch de trabalho). Próximo: N-3 (Mercado Pago),
> com o preço dos pacotes decidido pelo Bruno.
> **N-3 (compra de créditos) feita, provada e DESLIGADA** (`relatorio-n3.md`).
> Ligar as vendas exige V1–V6 do relatório (preço, Vercel Pro, termos,
> credenciais, sandbox, nota fiscal).
> **N-4:** termos e privacidade redigidos como rascunho (preencher os colchetes
> e passar por revisão jurídica; roteiro §9); site público muda no lançamento.
> **Tudo o que resta da nuvem depende das contas do Bruno** (roteiro §1–§9).
> **§30: N-5 (design do app) feita e provada** (`relatorio-n5.md`): visual de
> ferramenta e galeria de modelos fiel aos presets. Aberta: **Q-N5-1**
> (miniatura do YouTube nas prévias; recomendação: não).

---

## 1. Site na Vercel — decisões do Bruno

Estado: **no ar** em https://clippro-three.vercel.app/ (projeto Vercel
`clippro`, `prj_hNwp8LR63ossMCEvAaOvjzb583Xj`, time `corrars-projects`). Fonte
em `site/`, publicada do commit `2f3ef4f`. Conteúdo servido conferido
byte a byte com o commit; cabeçalhos de segurança ativos.

| # | Pendência | Quem |
|---|---|---|
| S1 | **Acesso público.** O projeto nasceu com "Vercel Authentication" em `all_except_custom_domains` (padrão do time), que exigia login até na produção. O executor mudou para `preview` (produção pública, previews com login). O classificador de segurança do Claude Code marcou isso como "enfraquecer segurança" e bloqueou as ações seguintes. **Decidir: manter público ou voltar a proteção.** | Bruno |
| S2 | **Confirmar acesso de fora**: abrir o link numa janela anônima (o container da sessão não alcança `*.vercel.app`). | Bruno |
| S3 | Acrescentar `og:url` e `<link rel="canonical">` com `https://clippro-three.vercel.app/` em `site/index.html` e republicar (bloqueado junto com S1; nada foi alterado). | executor, após S1 |
| S4 | Registrar o resultado da publicação no RULINGS (§21.2) — feito neste mesmo commit. | ✅ |
| S5 | **Licença.** O repositório não declara licença; o site diz "código público", não "código aberto". Escolher a licença (arquivo `LICENSE`) é decisão do dono. | Bruno |
| S6 | Deploy é manual: o projeto Vercel não está ligado ao Git para deploy automático. Cada mudança no site = um deploy explícito. | registro |

## 2. CLIP-F6.1 — falta só o lado do Windows

Feito no branch (itens 1–5, 7–14; relatório `docs/lote-clip-f6/relatorio-f61.md`).
Placar no Linux: `prova_f61.py --fisicas` 13/13; `prova_f6.py --fisicas`
43 passaram, 1 pulou (E-V5, sem `anthropic`), 0 falharam.

| # | Pendência | Quem |
|---|---|---|
| W1 | Rodar no Windows: `git fetch`, `git checkout claude/loving-newton-bykd21`, `.venv\Scripts\python provas\prova_f61.py --fisicas` e `.venv\Scripts\python provas\prova_f6.py --fisicas` | Bruno |
| W2 | Lockfile num venv novo: `py -3.13 -m venv _teste\venv-lock`, `_teste\venv-lock\Scripts\pip install -r requirements.lock.txt`, `_teste\venv-lock\Scripts\python -c "import fastapi, uvicorn, multipart; print('ok')"` | Bruno |
| W3 | Item 2 no painel real: play, pausar, re-renderizar o mesmo clipe → tem de terminar sem `WinError 5` | Bruno |
| W4 | ~~Palavra explícita para o merge do F6.1 em `master`~~ — o Bruno fez o merge do PR #1 (§30.2); W1–W3 e W5 viram conferência pós-merge | ✅ Bruno |
| W5 | D7 passos 3–5 (cópia do painel, aviso VERSAO 3, smoke pelo painel real): resultado nunca relatado | Bruno |

## 3. F8a — perguntas antes de qualquer código

Escopo decidido (RULINGS §20): modelos do usuário em pasta no repositório
(ignorada pelo git), `--preset` com nome ou caminho, painel lista fábrica +
usuário, duplicar modelo, S1 e S2. Reconhecimento completo em
`docs/lote-clip-f6/recon-f8a-codigo.md` (`8254c75`); a crítica no fim dele
prevalece sobre os relatórios. **Lista completa e respondível (Q1–Q19, com
folha de resposta): `docs/lote-clip-f6/perguntas-f8a.md`** (RULINGS §23).
Resumo das nove primeiras:

| # | Colisão | Recomendação do executor |
|---|---|---|
| Q1 | **S1 é ambígua**: o "teto 3" já é `max_palavras_linha` do modelo; o que está fixo é a fusão usar o mesmo teto do agrupamento. (R1) nada novo / (R2) campo novo só para a fusão, com sentinela "usa `max_palavras_linha`" | R2; fábrica sem mudança de valor |
| Q2 | **Identidade de cache**: somar campo a `legendas.Preset` muda o hash dos 4 modelos de fábrica (re-render sem subir `VERSAO`, vedado). Opções: lista fechada de campos omitidos no padrão / marcador por campo / recode único anunciado | marcador por campo (`field(metadata=…)`) + prova que congela os 6 hashes de hoje |
| Q3 | **S2 precisa do modelo, a seleção não recebe**: usar o modelo do pedido / todos os compostos / sempre `cortes` / proxy por caracteres; e se a identidade do modelo entra na assinatura do `select` | modelo do pedido (run/painel já o têm), gravado no `selecao.json`; render avisa se divergir |
| Q4 | **"v1 congelado"**: teto só para itens com `segmentos` / todos / recusa no v2 + aviso no v1 | recusa só no v2, aviso no v1 |
| Q5 | O prompt aprovado promete gancho de 90 caracteres; o teto de 4 linhas pode recusar menos que isso | manter o texto; a recusa traz o orçamento medido |
| Q6 | **Caminho como `--preset`** vaza para nome do clipe, metadados e cache | canonicalizar na entrada (identidade = stem; recusar colisão com fábrica) |
| Q7 | "Chave desconhecida avisa" não vale no caminho real: o render não usa `Modelo` | render passa a usar `Modelo` (objetos idênticos nos 4 de fábrica) |
| Q8 | Nome da pasta: `modelos/` x `models/` (detector de rosto) e `.gitignore` com `models/` não ancorado | `/modelos/` ancorado; corrigir `models/` → `/models/` |
| Q9 | Modelo do usuário salvo com BOM: ler com `utf-8-sig`? (CLAUDE.md §5 manda `utf-8`) | `utf-8-sig` só para modelo do usuário |

## 4. Divergências achadas, não corrigidas (entram no F8a ou num F6.2)

| # | Onde | Divergência |
|---|---|---|
| D1 | `README.md:151-153` | Promete que editar um preset refaz os clipes sem `--force`; só vale para a composição (a assinatura do render não leva a legenda). O site já diz a verdade. |
| D2 | `README.md` × `clipper/pipeline/transcribe.py:240` | README diz CPU; o código usa CUDA se houver GPU. |
| D3 | `ui/estaticos/app.js:169-173` | `escapar()` não escapa aspas e o resultado vai dentro de `value="…"`. |
| D4 | `ui/server.py:95` | Listagem de presets sem guarda de `OSError`. |
| D5 | `clipper/legendas.py:538` | `max_palavras_linha` vai cru, sem `int()`: modelo editado à mão com `"3"` estoura `TypeError` no meio do render. |
| D6 | `CLAUDE.md` §2 | Ainda diz `lote/clip-f6` e `[CLIP-F6]`; vigente é o RULINGS §20.1. |

## 5. Outras decisões em aberto

- **F9 — escopo (Q4 do §16)**: não respondido; não bloqueia nada até o F9.
- **CLAUDE.md**: segue sendo reconstrução declarada (o bloco "GOVERNANÇA
  PERSISTIDA" nunca chegou).
