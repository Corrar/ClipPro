# Relatório — pedido de 15/10 ("replicar cut.pro e opus.pro com o REA")

Base: `aa958d0` (= `origin/master`). Nenhum código alterado.

## 1. O que é o REA

`morluto/rea` ("Reverse Engineer Anything") é um servidor MCP + CLI em Node
para **engenharia reversa**: binários nativos (via Hopper/Ghidra/IDA), apps
JavaScript/Electron, assemblies .NET e sites. Ele mostra *como o código do
cliente* faz alguma coisa. Não é biblioteca de vídeo nem de clipping.

## 2. ⚠ Colisões entre o pedido e a realidade

| # | Colisão | Consequência |
|---|---|---|
| C1 | opus.pro e cut.pro são **SaaS**: seleção de momentos, virality score, reframe e legenda rodam **no servidor deles**. O REA, apontado para o site, enxerga só o front-end (UI, chamadas de API). | O REA **não revela** o que interessa (como escolhem e pontuam o trecho). Ganho técnico perto de zero. |
| C2 | Engenharia reversa do bundle de um SaaS comercial para copiar implementação esbarra nos termos de uso deles e em direito autoral. | Risco jurídico para o produto. Replicar **funcionalidade** a partir do que é público é legítimo; copiar código, não. |
| C3 | A rede deste container bloqueia os dois domínios (curl: `CONNECT 403`; fetch: `ENOTFOUND`). | Daqui não dá para rodar o REA neles; só na máquina do Bruno. |
| C4 | O README promete "roda inteiro na sua máquina, nenhum vídeo sai do computador". Publicação direta, B-roll de banco/IA e dublagem dos concorrentes **exigem rede**. | Parte da "paridade" contraria um princípio do produto — decisão do arquiteto. |
| C5 | A D7 fixou a fila F6.1 → F8a → F8b → F8c. | O pedido disputa prioridade com ela. |

## 3. Lacunas — fonte: material público (busca web), não engenharia reversa

| Funcionalidade | OpusClip | cut.pro | ClipPro hoje |
|---|---|---|---|
| Escolha de momentos por IA | sim (ClipAnything, multimodal) | sim ("assiste o vídeo todo": picos de energia, reações) | **sim** — LLM sobre a transcrição (`select.py`, prompt v2, `--api`) |
| Sinal além do texto | visual + áudio + sentimento | energia, reações, dinâmica de falantes | **parcial** — curva RMS de áudio; nenhum sinal visual |
| Virality score | sim | sim | **sim** — `score_0_10` do LLM, sem decomposição |
| Reframe 9:16 por rosto | sim (falantes e objetos em movimento) | sim | **sim** — rosto; troca de falante: a verificar |
| Legenda animada / templates | sim, vários templates | sim, 40+ idiomas | **sim** — karaokê, presets (`cortes`…), idiomas do whisper |
| Outros formatos (16:9, 1:1) | sim | — | **não** — é o F8b |
| Modelos/marca | sim | template | **parcial** — é o F8a |
| Capa + texto de publicação | — | — | **sim** — `capa.jpg`, `publicacao.md` |
| B-roll (banco ou IA) | sim (planos altos) | não citado | não — exige rede (C4) |
| Publicar/agendar direto | sim | sim | não — exige OAuth e rede (C4) |
| Dublagem | sim | não citado | não — vizinho do F7 (guardado) |
| API / MCP | API | API + MCP | só CLI e painel local |
| Export p/ editor (XML) | sim | — | não |

Leitura: o núcleo dos dois produtos (momento → score → 9:16 → legenda) **o
ClipPro já tem, local e sem custo por crédito**. A diferença real está em
(a) sinal visual na escolha, (b) score explicado, (c) formatos/modelos (já na
fila como F8a/F8b) e (d) o que depende de nuvem.

Fontes públicas: thecmo.com/tools/opusclip-review, martech.zone (OpusClip),
opus.pro/home-a-b, cut.pro e cut.pro/en (via resultado de busca).

## 4. Perguntas ao arquiteto

**Q1 — Uso do REA.**
- (A) **Não** apontar o REA para os sites; a tabela §3 vira a especificação
  de paridade, construída do zero. *Recomendado* (C1, C2).
- (B) Rodar o REA na máquina do Bruno só no front-end público, para mapear o
  fluxo de UI do painel, sem copiar código.

**Q2 — Fila.**
- (A) F6.1 primeiro (como na D7); F8a/F8b já cobrem modelos e formatos; abrir
  depois um **F9 "paridade"** com sinal visual + score decomposto. *Recomendado.*
- (B) F9 passa à frente do F8.
- (C) Outra ordem.

**Q3 — Princípio "tudo local" (C4).** Publicação direta, B-roll e dublagem:
(A) ficam fora; (B) entram como módulos opcionais com rede, desligados por
padrão; (C) entram de vez, revendo o README.

**Q4 — Escopo do F9**, se aprovado: quais linhas da §3 entram.

## 5. Pendências herdadas da D7

Passos 3–5 (cópia do painel, aviso da invalidação VERSAO 3, smoke pelo painel
real) e o relatório curto do passo 7 dependem do Windows do Bruno: **resultado
do smoke ainda não relatado**.

PARE aqui.
