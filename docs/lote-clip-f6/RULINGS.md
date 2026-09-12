# CLIP-F6 — Rulings e governança do lote

> **Para que este arquivo existe.** O contexto da sessão já foi perdido uma vez
> no meio do lote. Diretiva que só vive no chat morre com o reset; diretiva
> commitada sobrevive. Este arquivo é a memória do lote, e a regra vigente é:
> **diretiva nova do arquiteto = append aqui + commit, como primeiro ato**,
> antes de qualquer código.
>
> **Ordem de precedência.** O que está aqui prevalece sobre relatórios e sobre
> a leitura do executor. Entre dois itens daqui, vence o mais recente.

---

## ⚠ Lacuna conhecida nesta transcrição

A diretiva de 12/09 (`CORREÇÃO DO ARQUITETO`) manda transcrever **verbatim** a
seção `=== RULINGS ===` do bloco **"GOVERNANÇA PERSISTIDA"**, e escrever o
`CLAUDE.md` com o protocolo permanente descrito no **ATO 0 daquele bloco**.

**Esse bloco nunca chegou a esta sessão.** As mensagens recebidas estão todas
listadas em §1 abaixo, e nenhuma delas tem esse título, essa seção ou esse ATO 0.
É a segunda vez que um documento é dado como enviado sem ter chegado — o
"briefing v2" (§1.4) foi o primeiro.

O que está neste arquivo é, portanto, a transcrição verbatim do que **de fato**
foi recebido. O `CLAUDE.md` que acompanha este commit é uma **reconstrução
declarada** (ver cabeçalho dele), não o texto original. Quando o bloco chegar,
substituir os dois — é um commit.

---

## 1. Diretivas recebidas nesta sessão, em ordem

| # | Documento | Data |
|---|---|---|
| 1.1 | Lote CLIP-F6 — Camada Editorial (briefing original) | — |
| 1.2 | EMENDA 1 AO LOTE CLIP-F6 | — |
| 1.3 | DIRETIVA DO ARQUITETO — triagem do pré-relatório P0 | — |
| 1.4 | ADENDO WEB AO BRIEFING v2 | — |
| 1.5 | RULINGS DO ARQUITETO — destrava Emenda 1 + P1 | — |
| 1.6 | CORREÇÃO DO ARQUITETO — ATO 0 | 12/09 |

Documentos **citados mas nunca recebidos**: "briefing v2" (citado em 1.4 e 1.5
como portador das respostas Q1–Q6, que acabaram vindo em 1.5) e "GOVERNANÇA
PERSISTIDA" (citado em 1.6).

---

## 2. RULINGS — decisões fechadas

Transcrição verbatim de 1.5 (`RULINGS DO ARQUITETO — destrava Emenda 1 + P1`).

```
CHECKPOINT 1515c314 ACEITO. Branch lote/clip-f6 MANTIDO. Ajuste no próximo
commit: a exceção do .gitignore vira a forma ampla !provas/fixtures/**
(fixtures/ é curado por definição; a estreita desarma só um padrão).
Manter check-ignore -q como prova. Gerador lavfi aceito como está.

Q1 — Forma ANINHADA (a dos 4 presets) é o formato canônico de ARQUIVO do
modelo; carregamento por de_preset(); asdict()/flat fica como identidade
INTERNA (impressao/cache), nunca formato de arquivo. Campos NOVOS do F6
entram nas DUAS camadas (esquema aninhado + dataclass resolvido).
Round-trip da Emenda redefinido: JSON aninhado → de_preset() → montar() →
filtergraph idêntico ao da instância de fábrica em código, nos dois presets
compostos. O carregador passa a AVISAR (sem rejeitar) chave desconhecida.

Q2 — (B). O teto de cada preset NÃO muda (3 segue 3); nasce o PISO de 3
palavras fundindo blocos curtos, COM guarda de lacuna: não fundir através
de pausa > ~1,2 s (parametrizável); bloco pode ficar < 3 palavras quando a
fusão violaria a guarda ou o teto. Alvo: matar o bloco de 1 palavra.
Máx 2 linhas: \N só quando a quebra por largura exigir.

Q3 — ENTRA. margem_inferior do cortes-editorial → valor que ponha a base
≤ 1420. Exceção declarada E2.

Q4 — Convivem. publicacao.md por clipe, dentro de clips/; relatorio.md
segue como revisão do lote. Duplicação intencional.

Q6 — REAPROVEITAR a pílula PNG (pilula_titulo + gerar_ativos); nada de
drawtext. Texto-fonte = gancho_sugerido; y ≥ 180; enable entre 0 e a
duração (~2,5–3 s, parametrizável); fade=t=out com a guarda do d=0; mantém
a animação de entrada; após o fade, topo limpo e o enable corta o custo do
overlay. titulo_ativo é a base do escape para restaurar a caixa permanente;
o default É a substituição. O -t de saída permanece (-loop 1 é infinita).

VEREDITOS R/A:
R2 — clipe v2: o select MATERIALIZA inicio/fim derivados como SPAN (min/max
da união), documentado como "span, não o corte"; o validador de
render.py:801 ganha UMA adição — se segmentos presente, valida a forma
IMPORTANDO a função do select (sem duplicar). Unificação total = dívida.
R3 — aceito: N entradas -ss/-t + concat ANTES do crop; setpts=PTS-STARTPTS
por segmento antes do concat; montar() recebe a contagem de entradas de
vídeo; PNGs renumerados a partir de N.
R4 — entra no P2: ESQUEMA_JSON estendido ao v2 (segmentos, descricao,
capa_ts, conclusao — opcionais), mantendo additionalProperties: False.
Prova nova: o caminho --api aceita v2.
R7 — bump deliberado VERSAO 2 → 3 (todo cache re-renderiza uma vez, de
propósito; uma linha no relatório).
A2 — MarginL/MarginR separam-se (e teto_de_largura soma os dois), MAS os
presets de fábrica mantêm os valores simétricos atuais — zero pixel; o
respiro assimétrico é botão de modelo, não default.
A3 — obrigatório no P2: punches e barra de progresso remapeados da FONTE
para a timeline concatenada; punch fora dos segmentos mantidos morre;
corrida = duração total concatenada.
A4 — harness prova_f6.py espelhando prova_f5.py (main(argv)); zero
dependências novas; sem pytest.
Fades novos nascem com a guarda do d=0 (composicao.py:1113).
Semente F7: no P2, apenas DOCUMENTAR em comentário o ponto de junção [aout]
onde um amix futuro entraria. Nada de implementação.

EXCEÇÕES DECLARADAS DA REGRESSÃO — lista FECHADA. Diff de filtergraph E de
conteúdo do .ass (caminho normalizado), clipe v1 com recursos novos
desligados, deve mostrar EXATAMENTE:
E1 — slot do topo: pílula permanente → gancho ~3 s com fade-out;
E2 — cortes-editorial: margem_inferior corrigida;
E3 — legendas: piso de 3 com guarda + destaque pulando palavras ≤ 2 letras.
Qualquer outro delta = regressão, prova falha.

ORDEM: upgrade do .gitignore → fixtures (o Bruno fornece nesta sessão:
resposta-v1.json = o resposta.json de out/<slug>/ do job GT3RS, byte a
byte, como entrou no validador — NÃO recopiar do chat; transcricao.json do
mesmo job) → commit [CLIP-F6] do P0.5 → Emenda 1 (objeto modelo +
round-trip) → P1 → PARE: checkpoint com estruturais verdes + roteiro físico
completo (gerar_clipe_curto + frame do gancho em t=1 s).
```

### 2.1 Q5 — respondida em 1.4, não em 1.5

O item 4 de 1.4 determina: *"Exceção do .gitignore (Q5) ANTES do add."*
Aplicada em `dcef617` na forma ampla que 1.5 exigiu.

---

## 3. Ambiente e git

Transcrição verbatim de 1.4 (`ADENDO WEB AO BRIEFING v2`), que **prevalece
sobre** a seção "Passo zero" e sobre qualquer instrução de "sessão local":

```
1. AMBIENTE: o lote executa NESTA sessão (Claude Code web, sandbox). Provas
   ESTRUTURAIS rodam aqui; as 4 FÍSICAS rodam no Windows do Bruno via
   roteiro (item 5).
2. GIT (adaptação autorizada pelo arquiteto): criar branch `lote/clip-f6` a
   partir de 12fc1e2b. Commits e push PERMITIDOS só nesse branch — são o
   transporte do código e o seguro contra reset de contexto (já aconteceu
   uma vez). `master` INTOCADO; merge somente com a palavra explícita do
   Bruno, após relatório final + físicas verdes. Commits prefixados
   [CLIP-F6]; cada relatório cita o SHA do commit a que se refere.
3. PARIDADE: partir de origin/master == 12fc1e2b. Se origin tiver andado,
   PARE e reporte.
4. P0.5: o Bruno fornece nesta sessão as fixtures resposta-v1.json e
   transcricao.json (colagem/upload). Exceção do .gitignore (Q5) ANTES do
   add. O gerador lavfi do clipe-curto entra no branch; a execução dele é
   física (vai no roteiro).
5. ROTEIRO FÍSICO: prova_f6.py ganha um modo --fisicas que roda tudo que
   exige ffmpeg/fonte e salva o frame do gancho; cada checkpoint entrega o
   comando exato para o Bruno rodar no Windows após
   `git fetch && git checkout lote/clip-f6`.
6. PAREs mantidos: checkpoint pós-P1 (estruturais + roteiro físico) e
   relatório final. Q1–Q6 estão no briefing v2, que prevalece sobre o
   relatório P0.
```

**Emenda de 1.6:** as fixtures deixam de vir por colagem e chegam **pelo próprio
branch** — o Bruno as commita do Windows, byte a byte. Ao aparecerem via
`git pull` em `provas/fixtures/wetyO2gOOeU/`, rodar as duas provas de material
real e reportar **ainda dentro do PARE**.

---

## 4. Emenda 1 — estrutura do `modelo`

Transcrição verbatim de 1.2:

```
Motivo: o clipper vai ganhar, em lote futuro, "modelos de edição"
selecionáveis (presets: shorts vertical, vídeo horizontal editado, estilos
diversos). Para não refatorar depois, a ESTRUTURA nasce agora — sem mudar o
escopo funcional nem as provas do F6.

Regra estrutural: TODOS os parâmetros visuais e de estilo tocados neste lote
(gancho: on/off, duração, posição; zona segura: margens; legenda: fonte,
cores, palavras por bloco, linhas, highlight on/off e limiar de letras;
formato de saída) nascem agrupados num único objeto de configuração
serializável chamado `modelo` (dataclass → JSON), em vez de constantes
espalhadas. Os dois layouts atuais (cortes-feed, cortes-editorial) passam a
ser expressos como duas instâncias desse objeto — comportamento idêntico,
organização nova. O render recebe UM `modelo` e desenha a partir dele.

Continua FORA do F6: CRUD de modelos, seletor no painel, modelos novos, modo
horizontal. Só a estrutura.

Prova adicional: serializar os dois modelos de fábrica para JSON, recarregar
e renderizar → filtergraph idêntico ao da instância em código (round-trip).
```

Redefinida por Q1 (§2): o round-trip passa a ser **JSON aninhado →
`de_preset()` → `montar()` → filtergraph idêntico ao da instância de fábrica**.

---

## 5. Emenda 2 — fixtures versionadas

Transcrição verbatim de 1.3, item 2:

```
FIXTURE (bloqueio 1) — EMENDA 2 ao lote: prova de regressão não pode
depender de diretório gitignored. Novo passo P0.5, executado na sessão
LOCAL antes do P1: promover a fixtures versionadas
(provas/fixtures/wetyO2gOOeU/) a resposta v1 validada hoje no painel
(5 clipes) e a transcrição em blocos do mesmo vídeo — ambas existem em
out/ na máquina do Bruno. As provas do P1/P2 que citam "resposta real" e
"transcrição real" passam a apontar para essas fixtures.
```

E o item 4 do mesmo documento, que rege a classificação de provas:

```
CLASSIFICAÇÃO DE PROVAS — no relatório P0, marcar cada prova como:
ESTRUTURAL (roda só com o repo: validador v1/v2, quebrador de legenda,
diff de filtergraph, prompt v2, round-trip JSON do `modelo` da Emenda 1)
ou FÍSICA (exige ffmpeg + arquivos reais: duração ±0,5s, -14 LUFS ±1,
capa.jpg, frame do gancho). Todas rodarão na sessão local; a
classificação é mapa, não dispensa.
```

Item 3 do mesmo documento, sobre a colisão do `gancho_sugerido`:

```
COLISÃO do gancho_sugerido — registrada e absorvida: premissa corrigida
para "o gancho não é DESENHADO no vídeo" (comprovado em MP4 — a caixa
queimada mostra o titulo). O campo já chegar ao render em
metadados/relatório FACILITA o P1: encanamento pronto, falta o drawtext.
Sem mudança de contrato.
```

> Correção técnica levantada no recon e resolvida por Q6: a caixa **não** é
> `drawtext` — é um PNG do Pillow (`pilula_titulo`) sobreposto por `overlay`.
> Q6 decidiu reaproveitar o PNG.

---

## 6. Escopo vedado — não implementar sem pedido explícito

De 1.1 (briefing original):

- Narração/TTS ou mixagem de voz do editor (semente F7).
- Espelhamento, mudança de velocidade, pitch (segue default OFF), blur de
  borda, segundo vídeo/gameplay — vedados; **não deixar nem flag**.
- Redesenho dos layouts feed/editorial (a F4b decide o vencedor).
- Mudanças de tela no painel F5. Exceção mínima: a validação aceitar v1 e v2 —
  confirmado no recon que o painel já reusa `select.selecionar()`, então vem
  de graça.
- Integração com API do YouTube / coleta automática de métricas.

### Congelados

- Contrato v1 do JSON (byte a byte).
- Telas e fluxo do painel F5 (exceto a validação acima).
- Alvos de áudio do F4a: −14 LUFS, ordem EQ→loudnorm, pitch default OFF.

---

## 7. Estado do lote

### Commits em `lote/clip-f6` (base `12fc1e2b`)

| SHA | O que |
|---|---|
| `1515c31` | P0.5 — exceção estreita do `.gitignore` + gerador lavfi |
| `dcef617` | P0.5 — exceção passa à forma ampla `!provas/fixtures/**` |
| `fd89a4a` | Emenda 1 — objeto `modelo` + harness `prova_f6.py` + baseline |
| `1a4ba89` | P1 — E1 gancho, E2 zona segura, E3 conformidade de legenda |

### Checkpoint 1a4ba89 — registro de estado

**Aceito estruturalmente pelo arquiteto em 1.6.**

Provas: **12/12 estruturais verdes.**

```
E-M1  round-trip do modelo (JSON aninhado -> filtergraph)
E-M2  a forma flat não é formato de arquivo
E-M3  chave desconhecida avisa e não rejeita
E-M4  preset sem composição segue no caminho F3
E-R1  filtergraph x baseline 12fc1e2b: delta só em E1
E-R2  .ass x baseline 12fc1e2b: delta só em E2/E3
E-L1  ≤7 palavras e ≤2 linhas em TODOS os blocos
E-L2  destaque nunca em palavra de ≤2 letras
E-L3  guarda de lacuna, isolada num caso onde só ela pode agir
E-L4  \N nasce da largura e só dela
E-G1  enable + fade de saída sem d=0 + Y na zona segura
E-G2  o escape devolve o baseline byte a byte
```

Delta de filtergraph — duas etapas, ambas da pílula, nos dois presets compostos:

```
- [4:v]format=rgba,fade=t=in:st=0:d=0.5:alpha=1[pilula]
+ [4:v]...,fade=t=out:st=2.600:d=0.4:alpha=1[pilula]
- [compb][pilula]overlay=x=135:y='64+(-172)*pow(...)':format=yuv420[compt]
+ [compb][pilula]overlay=x=135:y='196+(-304)*pow(...)':enable='between(t,0,3)':format=yuv420[compt]
```

No `.ass`: `bold-amarelo` e `clean-branco` saem **byte a byte** (controle da
prova); nos compostos só a linha `Style` muda (E2: MarginV 450→500) e os
blocos (E3).

**Limite conhecido do ruling Q2 (B), medido.** Blocos de uma palavra caem de
**5 → 1** na fixture sintética. O sobrevivente é estrutural: é o *último* bloco
do clipe — sem vizinho à direita, e fundir para trás estouraria o teto 3. Com
teto 5 iriam a zero, mas isso mudaria pixel além do E3.

**Defeito real reproduzido e morto.** O baseline contém
`{\k24…\1c&H0000E5FF&}É` e o mesmo em `A` — o "É A PRIMEIRA" com o A amarelo
visto no MP4. E-L2 falha se alguém desfizer.

**Duas provas estavam erradas, o código não.** `_blocos_do_ass` cortava o
`Dialogue` no primeiro `,,` quando o formato ASS tem dois (contava `0,0,0,,`
como palavra); E-G1/E-G2 procuravam `fade=t=out` no grafo inteiro, casando com
o fade do *clipe*. Corrigidas; o parser agora confere contra a contagem de
`\k`, que é independente.

### Roteiro físico pendente

```powershell
git fetch && git checkout lote/clip-f6
.venv\Scripts\python provas\gerar_clipe_curto.py
.venv\Scripts\python provas\prova_f6.py --fisicas
```

| Prova | O que faz |
|---|---|
| **F-G1** | gerador lavfi produz clipe sondável (1280×720, ~40 s, com áudio) |
| **F-G2** | renderiza com `cortes`, extrai t=1 s e t=4 s, mede a faixa do topo contra banda de controle no meio do quadro; salva os dois PNG para inspeção |

### Pendências

1. **Fixtures do job GT3RS** — `provas/fixtures/wetyO2gOOeU/`. Chegam pelo
   branch, commitadas do Windows. Ao aparecerem: rodar as duas provas de
   material real e reportar dentro do PARE.
2. **Bloco "GOVERNANÇA PERSISTIDA"** — ver a lacuna no topo deste arquivo.
3. **Provas físicas** — não rodam no sandbox (sem ffmpeg, sem fontes do
   Windows).

---

## 8. Dívidas e sementes registradas

- **F7 (narração/TTS)** — `cadeia_audio()` (`composicao.py:1158`) é cadeia
  linear sobre `[aout]`. Trilha de narração exigiria `amix`. No P2, **apenas
  documentar** o ponto de junção em comentário.
- **Duplicação de validação** entre `select.py` e `render.py:801`. R2 manda
  importar a função do select em vez de duplicar; unificação total é dívida.
- **`ESQUEMA_JSON` fechado** (`select.py:132`, `additionalProperties: False`)
  faz o caminho `--api` divergir do manual até ser estendido no P2 (R4).
- **Dois geradores de clipe de prova** — `ui/provas/prova_f5.py:294`
  (`video_de_teste`, 8 s) e `provas/gerar_clipe_curto.py` (40 s). Não
  conflitam; consolidar em lote futuro.
- **Repo sem CI, sem `LICENSE`, sem `pyproject.toml`.**
