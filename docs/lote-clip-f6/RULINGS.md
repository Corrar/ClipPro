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
| **D1** | **COLAGEM B — triagem do P1 + liberação P2–P4** (§9) | 13/09 |
| **D2** | **Triagem do relatório final + checklist de merge** (§10) | 13/09 |
| **D3** | **Conserto do `conclusao.y`** (§11) | 13/09 |
| **D4** | **Retomada local — esta máquina assume o fechamento** (§12) | 16/09 |
| **D5** | **Triagem do D4 + P5 "integração v2"** (§13) | 16/09 |
| **D6** | **P5 aceito; decisões; inspeção do Bruno** (§14) | 16/09 |
| **D7** | **Merge do CLIP-F6 ("f6 ok" do Bruno)** (§15) | 16/09 |

**Convenção a partir da D1:** diretivas do arquiteto são **numeradas e
autossuficientes**. Cada uma é transcrita aqui inteira, como seção própria.

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


---

## 9. D1 — triagem do P1 + liberação P2–P4

Recebida em 13/09. Transcrição verbatim.

```
COLAGEM B (D1) — TRIAGEM DO P1 + LIBERAÇÃO P2–P4

Convenção nova: diretivas do arquiteto agora são numeradas (esta é a D1) e
autossuficientes. Primeiro ato: append desta diretiva inteira ao
docs/lote-clip-f6/RULINGS.md + commit [CLIP-F6], conforme a regra vigente.

REGISTROS:
1. ATO 0 @ 2ed96f2 ACEITO. A reconstrução declarada do RULINGS.md/CLAUDE.md
   vira texto CANÔNICO — sem commit de substituição; a auditoria do texto
   fica para o relatório final. A falha de transporte foi do canal
   (documentos citados que não chegaram), não do executor.
2. P1 VALIDADO EM PIXELS pelo Bruno (12/09, noite). As 14 provas rodaram
   VERDES no Windows dele — reprodução independente das 12 estruturais +
   F-G1/F-G2 físicas (Python 3.13 + ffmpeg instalados, .venv no clone).
   Frames inspecionados e aprovados: t=1s pílula com gancho em 2 linhas,
   acentos corretos, barra de acento mantida, y=196; t=4s topo limpo.
   "p1 ok" CONCEDIDO — o envio desta colagem é o ato.
3. Fixtures reais do job wetyO2gOOeU: a cópia de trabalho do painel ainda
   não foi localizada no Windows. Decisão do arquiteto: as fixtures deixam
   de travar o P2 e passam a travar SOMENTE o relatório final e o merge.
   Quando chegarem pelo branch, rode as duas provas de material real e
   reporte, como já combinado.

LIBERAÇÃO: P2 → P3 → P4, conforme os rulings já persistidos em
docs/lote-clip-f6/RULINGS.md. Lembretes vinculantes:

P2 — contrato v2: segmentos (1–3), fronteiras em bloco da transcrição,
ordem crescente, sem sobreposição interna, soma 20–90 s, não-sobreposição
ENTRE clipes pela UNIÃO; inicio/fim + segmentos juntos = rejeição no padrão
f"{rotulo}: ..."; select materializa inicio/fim derivados como SPAN
(documentado como "span, não o corte"); o validador do render IMPORTA a
checagem de segmentos do select (sem duplicar); ESQUEMA_JSON estendido
(segmentos, descricao, capa_ts, conclusao — opcionais) mantendo
additionalProperties: False, com prova no caminho --api. Render v2: N
entradas -ss/-t + concat ANTES do crop; setpts=PTS-STARTPTS por segmento
antes do concat; montar() recebe a contagem de entradas de vídeo; PNGs
renumerados a partir de N; crossfade de ÁUDIO ~15 ms nas junções (vídeo em
jump cut seco); montar_ass re-sincroniza legendas por segmento; punches e
barra de progresso remapeados da FONTE para a timeline concatenada (punch
fora dos segmentos mantidos morre; corrida = duração total concatenada);
loudnorm no resultado CONCATENADO (-14 LUFS). conclusao (≤90 chars):
overlay nos últimos ~2 s, estilo do gancho, dentro da zona segura; ausente
⇒ grafo idêntico. Documentar em comentário o ponto de junção [aout] onde um
amix futuro (semente F7) entraria — SEM implementar. Fades novos com a
guarda do d=0.

P3 — descricao (≤200 chars) e capa_ts ("mm:ss", dentro de algum segmento;
fora = rejeição na validação); capa.jpg (default: frame 1 s após o início
do 1º segmento); publicacao.md por clipe, dentro de clips/, com título,
descrição, gancho e o checklist do RULINGS; escrita utf-8, newline \n.

P4 — prompt_selecao v2: gancho = promessa VERIFICÁVEL; payoff identificado
e o clipe fecha nele; segmentos para remover gordura interna preservando
sentido e sequência; descricao/capa_ts quando houver confiança; regras
duras reescritas para cobrir o v2. O texto INTEGRAL do prompt v2 vai no
relatório para revisão do arquiteto.

PROVAS — estenda prova_f6.py: estruturais novas do P2/P3 (v2 válida passa;
as 8 mordidas com asserção que discrimina; conclusao ausente ⇒ filtergraph
idêntico; capa_ts fora ⇒ rejeição; publicacao.md gerado; fixture v1
sintética até a real chegar) e físicas novas no --fisicas (duração do MP4 =
soma dos segmentos ±0,5 s; -14 LUFS ±1 no arquivo final; capa.jpg bate com
capa_ts) — para o Bruno rodar tudo num comando só no Windows.

PARE no relatório final: o que mudou por arquivo, provas com números,
prompt v2 na íntegra, dívidas/sementes, perguntas em aberto. Sem git fora
de lote/clip-f6; master intocado; merge só com a palavra explícita do
Bruno.
```

### 9.1 Efeitos imediatos da D1

- **`CLAUDE.md` e este arquivo viram texto CANÔNICO.** A ressalva de
  "reconstrução declarada" no topo dos dois permanece como registro histórico,
  mas **não há commit de substituição pendente** — a auditoria do texto fica
  para o relatório final.
- **O PARE do P1 caiu.** P2 → P3 → P4 liberados em sequência. O próximo PARE é
  o **relatório final**.
- **As fixtures reais deixaram de travar o P2.** Passam a travar apenas o
  relatório final e o merge.

### 9.2 Checklist estático do `publicacao.md`

Conteúdo fixo, do briefing original (1.1), a ser gravado em cada
`clips/<clipe>.publicacao.md`:

```
- [ ] Autorização/licença do material confirmada
- [ ] Contribuição editorial perceptível sem ler a descrição
- [ ] O 1º segundo promete exatamente o que o clipe entrega
- [ ] Começo, progressão e payoff presentes
- [ ] Legendas legíveis, fora da UI, sem cobrir rosto/ação
- [ ] Título representa o que ocorreu (sem sensacionalismo falso)
- [ ] Substancialmente diferente dos outros clipes do canal
```


---

## 10. D2 — triagem do relatório final

Recebida em 13/09. Transcrição verbatim.

```
D2 — TRIAGEM DO RELATÓRIO FINAL (CLIP-F6)

Primeiro ato: append desta D2 inteira ao docs/lote-clip-f6/RULINGS.md +
commit [CLIP-F6], conforme a regra vigente.

REGISTROS E VEREDITOS:
1. Relatório final @ 08ab0c8 ACEITO estruturalmente. 24/24 estruturais
   registradas. Destaques de qualidade: zero delta na regressão v1 com os
   presets não-compostos como controle; conclusao ausente = 0 etapas.
2. As três decisões do executor: APROVADAS — capa.jpg do MP4 renderizado;
   conserto de sobreposição só v1×v1 (par com v2 reporta sem consertar);
   conclusao.y = 1040 por medição.
3. Pergunta 1: SIM — autorizada UMA adição de código: prova estrutural
   E-C4, vão mínimo ≥ 24 px entre a base da pílula de conclusão e o topo do
   bloco de legenda, calculado do modelo, nos dois presets compostos. Nada
   além dela.
4. Pergunta 2: o bloco de 1 palavra no fim FICA — limite conhecido; o teto
   não afrouxa.
5. Pergunta 3: a ressalva de reconstrução FICA como registro histórico.
   Auditoria encerrada sem discrepância.
6. acrossfade −15 ms/junção (−30 ms pior caso): aceito, documentado.
7. Dívidas (geradores duplicados, unificação total dos validadores,
   CI/LICENSE/pyproject): registradas para lote de higiene futuro.

FALHA DE TRANSPORTE Nº 3 — o prompt v2 não chegou ao arquiteto. Correção
permanente: gravar o prompt v2 GERADO PELO CÓDIGO (cabeçalho, sem
transcrição) em docs/lote-clip-f6/prompt-v2.txt, no mesmo commit da E-C4.
A revisão do arquiteto sobre esse texto é ITEM DE MERGE.

CHECKLIST DE MERGE (nada de merge antes de TODOS):
[ ] prompt-v2.txt revisado e aprovado pelo arquiteto
[ ] 6 físicas verdes no Windows do Bruno + inspeção visual dele
    (conclusão no fim, acima da legenda, sem sobrepor; capa composta 9:16)
[ ] fixtures reais commitadas + as 2 provas de material real verdes aqui
[ ] palavra explícita do Bruno
Pós-merge (registrar): master vira a versão de trabalho; VERSAO 3
re-renderiza os clipes em cache na primeira passada — esperado.

PARE mantido: além de E-C4 + prompt-v2.txt (um commit), nenhum código.
```

### 10.1 Checklist de merge — estado

| | Item | Estado |
|---|---|---|
| 1 | `prompt-v2.txt` revisado e aprovado pelo arquiteto | **pendente** |
| 2 | 6 físicas verdes no Windows + inspeção visual do Bruno | **pendente** |
| 3 | Fixtures reais commitadas + 2 provas de material real verdes | **pendente** |
| 4 | Palavra explícita do Bruno | **pendente** |

**Nada de merge antes de todos os quatro.**

### 10.2 Pós-merge, a registrar

- `master` vira a versão de trabalho.
- `VERSAO 3` re-renderiza os clipes em cache na primeira passada — **esperado**,
  é o bump deliberado do R7.

### 10.3 Falhas de transporte do lote

Três documentos foram dados como enviados sem ter chegado a esta sessão:

| # | Documento | Consequência |
|---|---|---|
| 1 | "briefing v2" | Q1–Q6 vieram depois, em 1.5 |
| 2 | "GOVERNANÇA PERSISTIDA" | `CLAUDE.md` nasceu como reconstrução declarada |
| 3 | prompt v2 (saída do executor) | corrigido: passa a ser gravado no repo |

A correção da nº 3 vale como padrão: **artefato que o arquiteto precisa
revisar não viaja só pelo chat — é gravado no branch.**


---

## 11. D3 — conserto do `conclusao.y`

Recebida em 13/09. Transcrição verbatim.

```
D3 — CONSERTO DO conclusao.y (CLIP-F6)

Primeiro ato: append desta D3 inteira ao docs/lote-clip-f6/RULINGS.md +
commit [CLIP-F6], conforme a regra vigente.

REGISTRO: a E-C4 encontrou colisão real (cortes: vão −50 px;
cortes-editorial: +4 px, abaixo do mínimo de 24 px). A aprovação do
y=1040 na D2 §2 repousou em aritmética incompleta (titulo_altura nominal
de 108 px, ignorando altura_pilula = max(...) que dá 152 px em 2 linhas —
e 90 chars fazem 2 linhas ser o caso comum). Erro compartilhado: o
executor calculou, o arquiteto aprovou sem exigir o caso extremo. Lição
gravada como regra do RULINGS: valor geométrico só é aprovado com o caso
extremo calculado junto.

AUTORIZADO: conclusao.y 1040 → 960 nos DOIS presets compostos. UM commit
[CLIP-F6], nada além dele. Em seguida:
1. Rerodar a suíte estrutural inteira — esperado: TODAS verdes, incluindo
   E-C4 (vãos calculados: cortes 30 px, cortes-editorial 84 px).
2. Confirmar no reporte que o conserto não toca as exceções E1–E3 da
   regressão (conclusão é pós-baseline; "ausente ⇒ 0 etapas" tem que
   seguir de pé).
3. PARE no reporte curto: SHA do commit + placar da suíte. O checklist de
   merge da D2 segue valendo; este conserto fecha o item novo que a E-C4
   abriu.
```

### 11.1 REGRA PERMANENTE — valor geométrico e caso extremo

**Um valor geométrico só é aprovado com o caso extremo calculado junto.**

Vale para quem propõe e para quem aprova. Não basta a conta do caso comum:
a proposta tem de trazer o pior caso que os PARÂMETROS permitem, não o que
costuma acontecer.

Como isto nasceu: `conclusao.y = 1040` foi proposto com a altura NOMINAL da
pílula (`titulo_altura`, 108 px) e aprovado assim. A altura real é
`max(titulo_altura, altura_linha * linhas + 2 * respiro)`
(`composicao.py:902`), que dá **152 px em duas linhas** — e como a conclusão
vai até 90 caracteres, duas linhas é o caso COMUM, não o extremo. O vão
prometido de +32 px era, na verdade, −50 px.

O que a regra exige na prática:

- ao propor um Y, uma altura ou uma margem, calcular com o maior valor que a
  fórmula pode produzir, não com o campo nominal;
- quando a fórmula for um `max(...)` ou tiver ramo condicional, dizer qual
  ramo foi usado;
- e, de preferência, deixar o cálculo numa PROVA, onde ele não pode
  envelhecer calado — foi a E-C4 que pegou este erro, não a releitura.

Erro compartilhado, registrado como tal: o executor calculou errado, o
arquiteto aprovou sem exigir o extremo.


---

## 12. D4 — retomada local (esta máquina assume o fechamento)

Recebida em 16/09. Transcrição verbatim.

```
D4 — CLIP-F6: RETOMADA LOCAL (esta máquina assume o fechamento)

Correção de premissa: o F6 NÃO é só briefing. Está em origin/lote/clip-f6
(commits [CLIP-F6] a partir de 12fc1e2b), com CLAUDE.md e
docs/lote-clip-f6/RULINGS.md dentro do branch. master está em 12fc1e2b por
regra (merge só com palavra do Bruno).

0. git fetch origin. Listar os commits de origin/lote/clip-f6 e LER
   CLAUDE.md + docs/lote-clip-f6/RULINGS.md do branch ANTES de qualquer
   pergunta: as 18 que você juntou se resolvem quase todas ali (Q1-Q6,
   D1-D2, exceções E1-E3, R2/R4/A2/A3, etc.). O que sobrar depois da
   leitura, liste com a referência do RULINGS conferida.
1. NÃO fazer checkout do branch nesta cópia (é a do painel, em uso;
   VERSAO 3 invalidaria o cache). Criar WORKTREE separado para
   lote/clip-f6 e trabalhar nele, com out/ próprio.
2. P0.5 — FIXTURES (urgente: o painel sobrescreve resposta.json a cada
   colagem). Copiar byte a byte, sem editar:
   out/<job wetyO2gO…>/resposta.json    → provas/fixtures/wetyO2gOOeU/resposta-v1.json
   out/<job wetyO2gO…>/transcricao.json → provas/fixtures/wetyO2gOOeU/transcricao.json
   git add (a exceção !provas/fixtures/** já está no branch), commit
   "[CLIP-F6] fixtures reais do job wetyO2gOOeU", push. Reportar bytes e
   sha256 dos dois — NÃO o conteúdo.
3. Verificar se a D3 pousou: conclusao.y 1040 → 960 nos dois presets
   compostos e E-C4 verde. Se NÃO pousou, aplicar agora exatamente isto
   (um commit): y = 960 em cortes e cortes-editorial; rerodar a suíte
   estrutural inteira; confirmar que as exceções E1–E3 da regressão não
   são tocadas (conclusão é pós-baseline; ausente ⇒ 0 etapas). Lição já
   gravada: valor geométrico só aprovado com o caso extremo calculado.
4. Rodar no worktree: provas/prova_f6.py --fisicas (estruturais + físicas,
   incluindo as 2 de material real que a fixture destrava). Esperado: tudo
   verde. Salvar os PNGs do gancho (t=1s/t=4s), os da conclusão e o
   capa.jpg em pasta nomeada para inspeção do Bruno.
5. Colar no relatório, na íntegra, docs/lote-clip-f6/prompt-v2.txt — a
   revisão do arquiteto sobre ele é item de merge.
6. PARE com o CHECKLIST DE MERGE (da D2 do RULINGS): [ ] prompt-v2
   revisado [ ] físicas verdes + inspeção visual do Bruno [ ] fixtures +
   provas de material real verdes [ ] palavra do Bruno. Nada de merge.

FORA deste lote, REGISTRAR como CLIP-F6.1 (higiene, depois do merge): os
2 bugs do painel (reprocessa pastas do terminal com opções padrão;
re-render falha com mp4 aberto no Windows), lockfile sem
fastapi/uvicorn/python-multipart (recriar o ambiente pelo lock mata o
painel — defeito do F5), clipper.log inexistente, README/--help
desatualizados, provas F1-F4 nunca versionadas, _trabalho/ com 1,76 GB
de baixado.mp4 repetido. Nenhum conserto agora.
.git/lost-found: pode remover.
Régua C.11 vale aqui também: relatório e commit não carregam conteúdo de
fixture nem dado pessoal — só bytes, hashes e contagens.
```

### 12.1 Efeitos imediatos da D4

- **A execução do lote passa para o Windows do Bruno.** Worktree separado em
  `C:\Users\Micro\Desktop\ClipPro-clip-f6` (branch local `lote/clip-f6`
  rastreando `origin/lote/clip-f6`), com `out/` e `_teste/` próprios. A cópia
  `C:\Users\Micro\Desktop\ClipPro` é a do painel: segue em `master` e não
  recebe checkout.
- **Paridade conferida na retomada (16/09):** `origin/master` = `12fc1e2b`;
  `origin/lote/clip-f6` = `7e903ab` (D3), o último commit que este arquivo
  descreve. Nada andou.
- **Régua C.11:** o identificador "C.11" não aparece neste arquivo nem no
  `CLAUDE.md` — não chegou a este canal. Vale pela definição dada na própria
  D4: relatório e commit não carregam conteúdo de fixture nem dado pessoal;
  só bytes, hashes e contagens.

### 12.2 CLIP-F6.1 — lote de higiene, depois do merge

Registro. **Nenhum conserto neste lote.** Referências de linha são de `master`
(`12fc1e2b`), medidas no levantamento de 16/09.

| # | Item | Evidência |
|---|---|---|
| 1 | Ao subir, o painel enfileira sozinho pasta feita no terminal que não chegou ao render, e roda `run` com as opções PADRÃO (whisper `medium`, `n=5`), ignorando as do terminal: re-transcreve e invalida o prompt já levado ao chat | `ui/server.py:636-652` não confere `do_terminal`; `ui/jobs.py:168-172` deduz `na_fila`; reproduzido em pasta sintética |
| 2 | Re-renderizar falha no Windows com o mp4 aberto: `parcial.replace(destino)` → `PermissionError [WinError 5]`; um handle do streaming do próprio painel basta | `clipper/pipeline/render.py:1500`; ocorreu no job real em 11/09; mecanismo reproduzido |
| 3 | `requirements.lock.txt` (da F0) sem `fastapi`, `uvicorn[standard]`, `python-multipart` e 6 transitivas: recriar o ambiente pelo lock mata o painel — defeito do F5 | `requirements.txt:31-33` x lock |
| 4 | Jobs do painel não gravam `clipper.log`, mas a mensagem de erro inesperado manda procurar o traceback nele | `ui/jobs.py:489-497`; `registro.configurar` só é chamado no CLI |
| 5 | README e `--help` desatualizados: epílogo cita `cortes-feed`; README usa o executável `clipper`, que não existe (só `python -m clipper`); README diz "recusa" onde o validador encaixa | `clipper/cli.py:48,63`; `README.md:12,85-87,118-124` |
| 6 | Provas de F1–F4 nunca foram versionadas (só existem nas mensagens de commit) | `git log --all --name-only` |
| 7 | `_trabalho/` guarda `baixado.mp4` repetido: ~1,76 GB somando os dois jobs | `du` em `out/*/_trabalho/` |


---

## 13. D5 — triagem do D4 + P5 "integração v2"

Recebida em 16/09. Transcrição verbatim.

```
D5 — TRIAGEM DO D4 + P5 "INTEGRAÇÃO v2" (bloqueadores de merge)

Primeiro ato: append ao docs/lote-clip-f6/RULINGS.md + commit. Autorizado
também commitar o relatório D4 em docs/lote-clip-f6/ (C.11 respeitada:
contagens e hashes, nunca conteúdo de fixture).

RELATÓRIO D4 ACEITO (638fa69). Fixtures, D3, 30/31 provas, inspeção e as
2 execuções avulsas de material real registradas. prompt-v2.txt APROVADO
como texto, sem alteração — condicionado ao P5 abaixo.

RÉGUA NOVA, assumida pelo arquiteto como falha de desenho da prova:
prova de integração atravessa o PONTO DE ENTRADA REAL (CLI `clipper
render` e o caminho do painel, ui/jobs.py). Prova que monta o ffmpeg à
mão não é prova do pipeline. Toda prova nova do P5 obedece.

P5 — DECISÕES Q1–Q10 (todas com prova que morde, vermelho antes do verde):
Q1 D-B — APROVADO: segmentos em selecao.json carregam só inicio/fim
   (derivados saem do segmento); confirmar antes que nenhum consumidor lê
   as chaves derivadas (grep + execução). Prova ponta a ponta:
   selecionar → renderizar com v2 real, pelo CLI e pelo caminho do painel,
   MP4 com duração = soma.
Q2 D-A — APROVADO: cada clipe comparado com TODOS os já aceitos, no ramo
   de união e na invariante final; prova com 3 clipes.
Q3 D-C — APROVADO: inicio/fim saem de `required`; E-V5 vira prova que
   cruza esquema × validador. maxItems no --api: só se houver chave real;
   sem chave, registrar como não verificado — não bloqueia merge (o
   painel só usa --api quando a chave existe).
Q4 D-D — APROVADO: v2 em preset sem composição é RECUSADO com mensagem
   clara (não sai MP4 pela metade em silêncio); "v2 no F3" vira semente.
Q5 D-E — APROVADO: capa.jpg e publicacao.md regenerados sempre que o MP4
   for (re)encodado ou faltarem, inclusive nos caminhos de reaproveitamento.
Q6 D-F — APROVADO: amostragem do reframe DENTRO dos segmentos mantidos,
   nunca no span.
Q7 — APROVADO: E-X1 (validador sobre resposta-v1 real) e E-X2 (quebrador
   sobre transcrição real) entram no harness, saída só de contagens. São
   as "2 provas de material real" do checklist.
Q8 F-V2 — APROVADO: -loglevel info em _medir_lufs; mensagem de "pulou"
   corrigida.
Q9 — APROVADO na forma ampla: .gitattributes com provas/fixtures/** -text
   (padrão, não nome literal — a lição do gitignore).
Q10 — P01/P03: avisar no v2 como no v1 quando o encaixe ajustar ≥3 s;
   segmentos contíguos são FUNDIDOS com nota no relatório.
   P07/P16: gancho NUNCA é truncado — reduz o corpo até o piso de
   legibilidade; se 90 caracteres ainda não couberem em 2 linhas, vai
   para 3, e o relatório avisa. Validador NÃO ganha limite (contrato v1
   congelado); o prompt segue prometendo 90 e o render tem de cumprir.
   Prova: os 2 ganchos reais que hoje saem truncados saem inteiros.
   P05: fato registrado com os números reais; ruling (B) mantido — o
   teto é parâmetro de modelo e volta no F8.
Menores, entram: E-R2 aceita só a mudança de MarginV; log do render mostra
soma, não span; conclusão truncada gera aviso.

INSPEÇÃO PARA O BRUNO, no fim do P5: um render REAL do vídeo GT3RS desta
máquina (um clipe v2 com segmentos, no preset cortes, COM legenda queimada
e conclusão de 2 linhas) — é a prova ponta a ponta e o artefato de
inspeção ao mesmo tempo. Frames em t=1s, meio, últimos 2s, mais capa.jpg,
numa pasta nomeada. MP4 não é commitado.

PARE no relatório do P5 com placar, SHAs e o checklist de merge
atualizado. main intocado.
```

### 13.1 REGRA PERMANENTE — prova de integração atravessa o ponto de entrada real

**Prova de integração atravessa o ponto de entrada real**: o CLI
(`python -m clipper ...`) e o caminho do painel (`ui/jobs.py`). Uma prova que
monta a linha do ffmpeg à mão, ou chama `composicao.montar()` direto, prova o
filtergraph — não prova o pipeline.

Como isto nasceu: as físicas v2 do P2/P3 (`_render_v2`) montavam o ffmpeg à
mão com recorte fixo. Passaram verdes enquanto o render real recusava todo
clipe v2 gerado pelo select (D-B), o `--api` não conseguia produzir v2 (D-C),
o ramo sem composição entregava só o 1º segmento (D-D), a capa envelhecia
(D-E) e o reframe amostrava a gordura (D-F). Nenhuma prova atravessava a
costura `selecionar → renderizar`. A falha foi assumida pelo arquiteto como
de desenho da prova.

### 13.2 Efeitos imediatos da D5

- **Relatório D4 aceito** e gravado em `docs/lote-clip-f6/relatorio-d4.md`.
- **`prompt-v2.txt` aprovado como texto**, condicionado ao P5: o render tem de
  cumprir o que o prompt promete (gancho de até 90 caracteres inteiro na tela;
  `segmentos` utilizáveis de ponta a ponta; `--api` aceitando v2).
- **P05 registrado.** Com a fixture real, blocos de 1 palavra caem de 36 para
  18 (`cortes`) e de 39 para 17 (`cortes-editorial`), a maioria no MEIO do
  clipe, travada pelo teto 3 dos dois lados — e não "o último bloco", como a
  fixture sintética sugeria (§7, §10 D2 item 4). Ruling Q2 (B) mantido; o teto
  é parâmetro de modelo e volta no F8.
- **Semente registrada:** "v2 no F3" — concatenação no ramo sem composição.
- **Checklist de merge (§10.1), com o que a D5 acrescenta:**

| | Item | Estado |
|---|---|---|
| 1 | `prompt-v2.txt` revisado e aprovado pelo arquiteto | aprovado como texto, **condicionado ao P5** |
| 2 | Físicas verdes no Windows + inspeção visual do Bruno | pendente (P5: inspeção sobre render real do GT3RS) |
| 3 | Fixtures reais commitadas + 2 provas de material real verdes | fixtures ✅ `638fa69`; E-X1/E-X2 no P5 |
| 4 | Palavra explícita do Bruno | pendente |
| 5 | Bloqueadores D-A…D-F + Q7–Q10 + menores (P5) | pendente |


---

## 14. D6 — P5 aceito; decisões; inspeção do Bruno

Recebida em 16/09. Transcrição verbatim.

```
D6 — P5 ACEITO; DECISÕES; INSPEÇÃO DO BRUNO

Primeiro ato: append ao RULINGS + commit. AUTORIZADO gravar
docs/lote-clip-f6/relatorio-p5.md (C.11: contagens, hashes, sem conteúdo).

P5 ACEITO (7585e1b): 44/44, integração pelo ponto de entrada real (CLI e
ui/jobs.py), render real do GT3RS em 2 segmentos, revisão adversarial com
mutação por conserto. Régua §13.1 confirmada como permanente.

DECISÕES:
1. Gancho: APROVADO como está — nunca truncado, sem teto de linhas no
   render. SEMENTE registrada para o F8: teto de linhas (4) aplicado na
   SELEÇÃO (validador v2 recusa e o selecionador reescreve), nunca no
   render. Contrato v1 segue congelado.
2. VERSAO permanece 3 (R7). CONDIÇÃO: apagar do out/ do worktree todo
   render anterior a 7585e1b (os únicos em VERSAO 3 com gancho cortado),
   com confirmação por listagem. Produção nunca viu a 3.
3. Leituras §3 1–4 CONFIRMADAS: recusa só para v2 com 2+ segmentos;
   "colado" = consecutivo com lacuna ≤ 1,2 s (mesmo valor do Q2); sem
   fusão se estourar 90 s; gancho sem teto, palavra mais larga que a caixa
   quebra dentro dela.
Limites de baixa gravidade (§5) → CLIP-F6.1, registrados.

CHECKLIST DE MERGE: falta SÓ a inspeção visual do Bruno e a palavra dele.
Após o "f6 ok" do Bruno, PARE aguardando a D7 com o procedimento de merge
(fast-forward de master, pull na cópia do painel, invalidação de cache
esperada, F4b já fechada com cortes como padrão).
```

### 14.1 Efeitos imediatos da D6

- **P5 aceito em `7585e1b`.** A regra do §13.1 (prova de integração atravessa
  o ponto de entrada real) fica permanente.
- **Gancho (§11.1):** o caso extremo medido no P5 está APROVADO como está —
  `cortes` até 9 linhas / 446 px / base y=642 com 90 caracteres adversariais;
  `cortes-editorial` até 7 linhas / base y=458. Nunca truncado, sem teto no
  render.
- **VERSAO = 3** (R7), com a condição de limpar os renders anteriores a
  `7585e1b` do `out/` do worktree. Execução e listagem no relatório do P5
  (`docs/lote-clip-f6/relatorio-p5.md`, seção da D6).
- **Leituras do executor no P5, agora rulings:**
  1. a recusa do Q4 vale só para v2 com 2+ segmentos (v2 de 1 segmento
     renderiza inteiro no ramo sem composição);
  2. "colado" = blocos consecutivos com lacuna ≤ 1,2 s
     (`LACUNA_MAXIMA_FUSAO_S`, o mesmo valor da guarda de lacuna do Q2);
  3. sem fusão quando fundir estouraria 90 s;
  4. gancho sem teto de linhas; palavra mais larga que a caixa quebra dentro
     dela.

### 14.2 Semente F8 — teto de linhas do gancho na SELEÇÃO

Teto de 4 linhas para o gancho, aplicado no validador v2 (recusa, e o
selecionador reescreve o gancho), **nunca no render**. O render continua
nunca truncando. O contrato v1 segue congelado: a regra é só do v2.

### 14.3 CLIP-F6.1 — itens acrescentados pela D6 (limites do P5 §5)

Somam-se aos sete itens do §12.2. Todos de baixa gravidade, pós-merge,
nenhum conserto neste lote.

| # | Item | Onde |
|---|---|---|
| 8 | Capa ou publicacao.md abertos por outro processo (sem FILE_SHARE_DELETE) durante o re-encode ficam velhos com rc 0, e o atalho de estágio os sela nas rodadas seguintes; o publicacao.md deixa um .tmp órfão | `render.py` `_gravar_capa`, `_pacote_publicacao`, `_arquivos_no_lugar`; `_escrever_texto` |
| 9 | `capa_ts` no último intervalo de quadro de fonte abaixo de 20 fps: a capa nunca é extraída e o estágio deixa de pular (sem re-encode, mas refaz o laço a cada rodada) | `render.py` `_instante_da_capa` (limite `duracao - 0.05`) + `_arquivos_no_lugar` |
| 10 | Recusa por material compartilhado depois do conserto v1×v1 mostra o início já deslocado, sem dizer que houve deslocamento | `select.py`, laço de sobreposição de `validar` |
| 11 | Mensagens de "clipe solto" e de item que não é objeto só conhecem a forma v1 (anterior ao P5) | `select.py` `validar` (`um_clipe_solto`) |
| 12 | E-C4 estima 152 px para a pílula de 2 linhas do `cortes`; a medida com a fonte real dá 156 px (vão real 26 px, ainda ≥ 24) | `provas/prova_f6.py` `_FATOR_ALTURA_LINHA` |

### 14.4 Checklist de merge — estado

| | Item | Estado |
|---|---|---|
| 1 | `prompt-v2.txt` revisado e aprovado | ✅ aprovado (D5), condição do P5 cumprida (D6) |
| 2 | Físicas verdes + inspeção visual do Bruno | físicas ✅ 11/11 em `7585e1b`; **inspeção do Bruno pendente** |
| 3 | Fixtures reais + 2 provas de material real verdes | ✅ `638fa69`; E-X1/E-X2 verdes |
| 4 | Bloqueadores do P5 | ✅ P5 aceito (D6) |
| 5 | Palavra explícita do Bruno ("f6 ok") | **pendente** |

Depois do "f6 ok": PARE aguardando a D7 (procedimento de merge).


---

## 15. D7 — merge do CLIP-F6 (palavra do Bruno: "f6 ok")

Recebida em 16/09. Transcrição verbatim.

```
D7 — MERGE DO CLIP-F6 (palavra do Bruno: "f6 ok")

Primeiro ato: append ao RULINGS + commit no branch (último commit antes do
merge). Depois, nesta ordem, com medida a cada passo:

1. PRÉ-VOO: git fetch; confirmar origin/master ainda em 12fc1e2b (ninguém
   andou) e origin/lote/clip-f6 no tip esperado (e580d21 ou o commit da
   D7). Suíte completa uma última vez no worktree: esperado 44/44.
2. MERGE em master: fast-forward se possível (a cadeia é linear desde
   12fc1e2b); se não for, merge commit — NUNCA rebase (SHAs citados nos
   registros não podem ficar órfãos). Push de master. Reportar o SHA novo
   de origin/master.
3. CÓPIA DO PAINEL (C:\Users\Micro\Desktop\ClipPro): git status antes
   (tem de estar limpa fora de out/ e do briefing solto); git pull;
   confirmar HEAD == origin/master. NÃO recriar o .venv — o lockfile
   ainda está sem fastapi/uvicorn (CLIP-F6.1); o ambiente atual serve.
4. INVALIDAÇÃO ESPERADA: VERSAO 3 faz os 5 clipes da GT3RS re-renderizarem
   na próxima passada do painel — avisar o Bruno que é esperado, não
   defeito. Antes disso, fechar qualquer player com MP4 aberto (o bug do
   re-render com arquivo aberto ainda existe até o F6.1).
5. SMOKE PÓS-MERGE, pelo painel real: subir o painel na cópia, abrir o job
   da GT3RS, re-renderizar um clipe e confirmar que sai com gancho no topo
   e sem caixa permanente. É a única prova que atravessa o deploy de
   verdade.
6. BRANCH: lote/clip-f6 fica no remoto por 7 dias como referência dos
   SHAs, depois apaga; o worktree ClipPro-clip-f6 pode ser removido após
   o passo 5 (desfazer junction de node_modules/.venv antes, se houver).
7. RELATÓRIO CURTO: SHAs (master antes/depois), placar da suíte, resultado
   do smoke do passo 5, e o que ficou para o CLIP-F6.1.

Fila do ClipPro depois do pouso: CLIP-F6.1 (higiene: lockfile, 2 bugs do
painel, log, README/--help, provas F1–F4, _trabalho/) → F8a (modelos) →
F8b (horizontal) → F8c (referência). F7 (narração) segue guardada.
PARE no relatório.
```

### 15.1 Efeitos imediatos da D7

- **Palavra do Bruno dada ("f6 ok").** Checklist de merge (§14.4) completo:
  inspeção visual e palavra do Bruno registradas pela própria D7.
- **Este é o último commit do lote antes do merge.** O merge em `master` é
  fast-forward a partir de `12fc1e2b` (cadeia linear), nunca rebase: todo SHA
  citado neste arquivo e nos relatórios continua alcançável a partir de
  `master`.
- **Branch `lote/clip-f6`:** fica no remoto por 7 dias como referência dos
  SHAs (até 23/09/2026) e depois é apagado.
- **Fila do ClipPro depois do pouso:** CLIP-F6.1 (higiene — §12.2 e §14.3) →
  F8a (modelos) → F8b (horizontal) → F8c (referência). F7 (narração) segue
  guardada.


---

## 16. Pedido de 15/10 — "replicar cut.pro e opus.pro com o REA"

Recebido em 15/10/2026, depois do pouso do CLIP-F6. Transcrição verbatim.

```
continue de onde parou utilize o https://github.com/morluto/rea.git, para
replicar o https://cut.pro/pt-BR e https://www.opus.pro/pt-br?&utm_source=
google&utm_medium=ppc&utm_campaign=G_PMAX_BoF_PlanPurchased_Portuguese&...
```

(A URL do opus.pro veio com ~20 parâmetros de rastreio de anúncio — `gclid`,
`gbraid` etc. —, truncados aqui por não terem conteúdo de diretiva.)

### 16.1 Estado no recebimento

- `origin/master` = `aa958d0` = tip do branch: **o merge da D7 pousou**
  (fast-forward, cadeia linear desde `12fc1e2b`). Os passos 3–5 da D7 (cópia
  do painel, invalidação VERSAO 3, smoke pelo painel real) rodam no Windows do
  Bruno e **não têm resultado visível daqui** — seguem pendentes de relato.
- Fila vigente pela D7: CLIP-F6.1 → F8a → F8b → F8c; F7 guardada.

### 16.2 Efeito

O pedido muda escopo e fila e esbarra em três pontos de arquitetura (§16.3 do
relatório). Pelo protocolo (CLAUDE.md §1), **dúvida de arquitetura para o lote
e volta como pergunta**: nenhum código escrito, nenhum lote aberto. Recon e
perguntas em `docs/lote-clip-f6/relatorio-pedido-1510.md`. **PARE** até a
resposta.


---

## 17. Resposta ao pedido de 15/10 (§16)

Recebida em 15/10/2026. Transcrição verbatim.

```
Q1 A, Q2 A, Q3 B — pode seguir
```

### 17.1 Efeitos

- **Q1 = A.** O REA **não** é apontado para opus.pro nem cut.pro. A tabela §3
  de `relatorio-pedido-1510.md` (material público) é a especificação de
  paridade; tudo construído do zero.
- **Q2 = A.** Fila: **CLIP-F6.1 agora** (itens §12.2 e §14.3) → F8a → F8b →
  F8c → **F9 "paridade"** (sinal visual na escolha + score decomposto). F7
  segue guardada.
- **Q3 = B.** Funcionalidades que exigem rede (publicação direta, B-roll,
  dublagem) entram, quando entrarem, como **módulos opcionais desligados por
  padrão**; o modo padrão continua 100% local.
- **Q4 (escopo do F9) não foi respondida** — fica aberta até o F9 abrir; não
  bloqueia o F6.1.
- "pode seguir" = abrir o CLIP-F6.1. Prefixo dos commits: **`[CLIP-F6.1]`**.
  Branch de trabalho desta sessão: `claude/charming-euler-02p9cf`, a partir de
  `origin/master` = `aa958d0` (paridade conferida em 15/10). `master`
  intocado.


---

## 18. Decisões sobre o relatório do F6.1 (§3 de `relatorio-f61.md`)

Recebida em 15/10/2026. Transcrição verbatim.

```
12 A, 6 A, 7 A, 14 pode consertar — pode seguir
```

### 18.1 Efeitos

- **Item 12 = A.** Dois fatores na prova E-C4: pílula **1,38** (medido com a
  fonte real: 156 px) e legenda **1,35**. Nada renderizado muda; `VERSAO`
  não sobe.
- **Item 6 = A.** As provas de F1–F4 são reescritas como provas estruturais +
  físicas novas, **num lote próprio** — fora do F6.1. Posição na fila ainda
  não definida.
- **Item 7 = A.** O `baixado.*` de `_trabalho/` é apagado **só quando o
  `fonte.mp4` veio de remux `-c copy`** (mesmos streams, nada se perde). Veio
  de reencode → o bruto fica, como hoje. A regra "nada é apagado sem aviso"
  continua: a remoção é anunciada no log.
- **Item 14 autorizado:** erro inesperado no início de um job do painel não
  pode deixar o job em `rodando` para sempre.


---

## 19. Posição do lote das provas F1–F4

Recebida em 15/10/2026. Transcrição verbatim.

```
provas F1–F4 depois do F8c, antes do F9 — pode seguir
```

### 19.1 Efeitos

- **Fila vigente:** CLIP-F6.1 (aguarda físicas no Windows + palavra do Bruno
  para merge) → **F8a** (modelos) → **F8b** (horizontal) → **F8c**
  (referência) → **provas F1–F4** (§18, item 6 = A) → **F9** "paridade". F7
  (narração) segue guardada.
- "pode seguir" = próximo da fila: **F8a**.


---

## 20. Escopo do F8a (respostas ao `recon-f8a.md`)

Recebida em 15/10/2026. Transcrição verbatim.

```
1 A, 2 repositório, 3 sim, 4 neste branch — pode seguir
```

### 20.1 Efeitos

- **Escopo = A:** modelos do usuário. Pasta própria fora do pacote;
  `--preset` aceita o nome de um modelo do usuário ou o caminho de um
  arquivo; o painel lista fábrica + usuário; um jeito de duplicar um modelo de
  fábrica como ponto de partida; mais as sementes **S1** (teto de blocos de 1
  palavra da legenda vira parâmetro do modelo) e **S2** (§14.2). Sem editor
  visual.
- **Pasta = no repositório, ignorada pelo git.**
- **S2 entra no F8a:** teto de linhas do gancho no validador v2 (recusa + o
  selecionador reescreve); o render continua nunca truncando; v1 congelado.
- **Branch:** `claude/charming-euler-02p9cf`, prefixo **`[CLIP-F8a]`**, sem
  esperar o merge do F6.1.
- Regras que seguem valendo (CLAUDE.md §6): forma ANINHADA é o formato de
  arquivo; campo novo entra nas DUAS camadas; chave desconhecida avisa;
  `VERSAO` só sobe se o resultado mudar para os mesmos parâmetros.


---

## 21. Pedido de 15/10 — site do ClipPro na Vercel

Recebido em 15/10/2026, com o reconhecimento do F8a em andamento. Transcrição
verbatim.

```
crie o site e publique-o na vercel.
```

### 21.1 Leitura do executor (declarada, não decisão)

- **"o site" = página pública do ClipPro**, no papel que cut.pro e opus.pro
  cumprem para os produtos deles (§16): o que é, como funciona, o que entrega,
  como instalar. Construída do zero (§17 Q1 = A): **nenhuma** marca, texto,
  imagem ou código dos dois concorrentes.
- **O painel NÃO vai para a Vercel.** Ele escuta só em 127.0.0.1 por regra,
  roda ffmpeg + whisper na CPU por minutos ou horas e o produto promete que
  "nenhum vídeo sai do computador" (§17 Q3 = B). Uma função serverless não
  roda isso e publicar o painel quebraria a promessa.
- O site **só afirma o que o código e o README sustentam** (números medidos,
  presets reais, Windows/Python 3.13/ffmpeg). Sem depoimento, sem contador de
  usuários, sem preço inventado.
- Fonte em `site/` no repositório (estático: HTML + CSS, zero build), projeto
  Vercel `clippro` no time `corrars-projects`. O botão de instalação aponta
  para o repositório público `github.com/Corrar/ClipPro`.
- O F8a fica pausado depois do reconhecimento; retoma depois do site.

### 21.2 Resultado (15/10)

- Site em `site/` (commit `2f3ef4f`), direção "sala de corte" escolhida por 3
  juízes entre 3 versões; 47 achados de revisão adversarial corrigidos.
- Publicado: projeto Vercel `clippro`, produção em
  https://clippro-three.vercel.app/, deploy do GitHub (pasta `site/`), sem
  build e sem deploy automático.
- Proteção do projeto alterada pelo executor de `all_except_custom_domains`
  para `preview` (produção pública). O classificador de segurança do Claude
  Code marcou a mudança e bloqueou as ações seguintes: **manter ou reverter é
  decisão do Bruno** (`docs/PENDENCIAS.md`, S1).

---

## 22. Pedido de 15/10 — salvar pendências

Recebido em 15/10/2026. Transcrição verbatim.

```
salve na memoria as pendencias e continuamos depois
```

### 22.1 Efeitos

- Pendências consolidadas em **`docs/PENDENCIAS.md`**: é o ponto de retomada
  da próxima sessão, junto com este arquivo.
- Trabalho **parado** até a próxima mensagem do Bruno.

---

## 23. Pedido de 15/10 — "siga de onde parou"

Recebido em 15/10/2026, numa sessão nova. Transcrição verbatim.

```
siga de onde parou
```

### 23.1 Estado no recebimento

- `origin/master` = `aa958d0` (pouso do CLIP-F6), intocado — paridade
  conferida.
- `origin/claude/charming-euler-02p9cf` = `0295359` (§22), exatamente o ponto
  de retomada que o `docs/PENDENCIAS.md` declara.
- Desde o recon do F8a (`8254c75`) só `site/` e `docs/` mudaram: as
  referências de linha do `recon-f8a-codigo.md` continuam valendo.

### 23.2 Leitura do executor (declarada, não decisão)

- **Branch.** Esta sessão só pode empurrar para
  `claude/loving-newton-bykd21`. O branch foi avançado por fast-forward até
  `0295359` (nenhum commit reescrito) e passa a ser o branch de trabalho. O
  `claude/charming-euler-02p9cf` fica congelado em `0295359`, com o mesmo
  código. Prefixo segue o lote: **`[CLIP-F8a]`** (§20.1).
- **"De onde parou".** O §22 parou tudo esperando o Bruno. O próximo da fila
  é o **F8a**, cujo recon (`8254c75`) terminou com colisões que precisam de
  decisão. O pedido do site (§21) chegou antes de elas serem apresentadas
  como perguntas — **"siga" não as responde.** Pelo CLAUDE.md §1, dúvida de
  arquitetura volta como pergunta: o executor entrega as perguntas do F8a
  consolidadas e **PARA** até a resposta. Nenhum código do F8a é escrito.
- Site (S1, S5) e F6.1 no Windows (W1–W5) seguem com o Bruno, sem mudança.

### 23.3 Resultado

- Placar da base nesta sessão (Linux, ffmpeg, venv com o lockfile):
  `prova_f6.py --fisicas` **44/0/0**, `prova_f61.py --fisicas` **13/0/0**.
- Perguntas do F8a consolidadas em **`docs/lote-clip-f6/perguntas-f8a.md`**:
  Q1–Q9 do `PENDENCIAS.md` §3 com a mesma numeração, mais Q10–Q19 que o
  recon levantou e não tinham virado pergunta (medição de linhas × fonte,
  onde mora o "4", resolvedor de nome, duplicar, isolamento das provas,
  harness, editar a legenda não refaz os clipes, **regressão E-R1/E-R2 que
  não morde**, F-G1 sobrescrevendo o vídeo da F5, divergências D1–D6).
- **PARE** até a resposta.

---

## 24. Pedido de 15/10 — ClipPro operacional na nuvem

Recebido em 15/10/2026, em três mensagens seguidas. Transcrição verbatim.

```
o clippro ja esta na vercel? ja tem um painel moderno estilo cutpro ou opusclip?
```

```
o clippro ja vai ser operacional na nuvem, assim como é o cutpro e o opusclip.
```

```
a pessoa deve abrir o clippro, fazer seu login ou criar sua conta, deve abrir o
site com as opções a opçao de gerar clip a pessoa cola o link e o site faz a
parte de cortar o video e gerar os clips editados, e funciona com creditos e
compra de creditos....
```

### 24.1 Leitura do executor (declarada, não decisão)

- A primeira mensagem é pergunta; a resposta está no §1 de
  `docs/lote-clip-f6/relatorio-pedido-nuvem.md`.
- A segunda e a terceira são **decisão de produto**: o ClipPro passa a ser um
  serviço na nuvem com conta, geração de clipes no servidor e cobrança por
  créditos. Isso **revoga o §17 Q3 = B** ("o modo padrão continua 100%
  local"), contraria o README e o site publicado ("nenhum vídeo sai do seu
  computador") e o §21.1 ("o painel NÃO vai para a Vercel").
- Pelo CLAUDE.md §1, a arquitetura volta como pergunta: N1–N9 em
  `relatorio-pedido-nuvem.md`. **PARE** até a resposta; nenhum código escrito.
- As perguntas do F8a (§23) ficam em espera: a N8 decide a ordem.

---

## 25. Respostas parciais ao relatório da nuvem (§24)

Recebida em 15/10/2026. Transcrição verbatim.

```
300 créditos grátis, usar o mercado pago
```

### 25.1 Efeitos

- **N6 = Mercado Pago.**
- **Créditos grátis no cadastro = 300.**
- N1–N5, N7–N10 **não foram respondidas**; continuam abertas.

### 25.2 ⚠ Colisão destacada: o 300 depende da N7

- Com N7 = A (1 crédito = 1 minuto de vídeo), 300 créditos = **5 h de vídeo
  por conta nova**. Pela medida do README (transcrição 0,685× o áudio em 12
  núcleos; render ~1,2× cada clipe, 5 clipes de 1 min por hora de vídeo), isso
  dá ~205 min de transcrição + ~30 min de render ≈ **4 h de máquina de 12
  núcleos por cadastro**, antes de qualquer compra.
- Com N7 = B (1 crédito = 1 clipe), 300 = 300 clipes grátis, com custo que
  varia com a duração do vídeo enviado.
- Brinde por cadastro também é alvo de contas repetidas: a verificação do
  cadastro entra na fase N-2.
- A escolha é do Bruno; o executor só mede.

---

## 26. Respostas às perguntas da nuvem (formulário de 15/10)

Recebidas em 15/10/2026 pelo formulário de perguntas da sessão. Transcrição
verbatim (pergunta → resposta).

```
"Com 300 créditos grátis no cadastro, quanto vale 1 crédito? (N7)"
  = "1 minuto de vídeo (Recomendado)"
"As outras recomendações do relatório valem? N1 nuvem é o produto e o local
 vira ferramenta interna; N2 Vercel para o app + servidor de processamento
 separado; N3 transcrição na CPU (GPU depois, com números); N4 link e envio
 de arquivo; N5 login com e-mail/senha + Google; N8 fecha o F6.1, depois as
 fases N-1→N-4; N9 o site muda só no lançamento."
  = "Sim, todas"
"Onde roda o servidor que processa os vídeos? (necessário para a fase N-1)"
  = "Tudo de forma gratuita, free tier"
"N10 — CNPJ, termos de uso e política de privacidade (LGPD): como fica?"
  = "Sem CNPJ ainda; redija, eu reviso"
```

### 26.1 Efeitos

- **N7 = A**: 1 crédito = 1 minuto de vídeo; com o §25, **300 créditos = 5 h
  de vídeo grátis por cadastro**.
- **N1 A, N2 A, N3 A, N4 A, N5 A, N8 A, N9 B** — como recomendado em
  `relatorio-pedido-nuvem.md` §4.
- **N10:** sem CNPJ; o executor redige termos e privacidade (fase N-4), o
  Bruno revisa. Tipo de conta do Mercado Pago e nota fiscal: do Bruno, antes
  da N-3.
- **Hospedagem: "tudo de forma gratuita, free tier".** Colide com três fatos
  verificados; ver `relatorio-pedido-nuvem.md` §6. **PARE** até a resposta.

---

## 27. Respostas G1–G4 (formulário de 15/10) — abre a fase N-1

Recebidas em 15/10/2026 pelo formulário de perguntas da sessão. Transcrição
verbatim (pergunta → resposta).

```
"G1 — O plano grátis da Vercel só permite uso não comercial. Até onde vai o
 "tudo grátis"?" = "Beta fechado grátis (Recomendado)"
"G2 — A IA que escolhe os melhores trechos não tem plano grátis na Anthropic.
 Como fica?" = "Anthropic com teto de gasto (Recomendado)"
"G3 — Onde roda o processamento durante o beta grátis?"
  = "Meu PC Windows (Recomendado)"
"G4 — Posso começar a fase N-1 agora, neste branch, sem esperar o merge do
 F6.1 (que depende das provas no seu Windows)?"
  = "Sim, pode começar (Recomendado)"
```

### 27.1 Efeitos

- **G1 = A:** N-1 e N-2 em planos grátis, **beta fechado** (só convidados,
  sem cobrança). Antes da N-3, os custos são decididos com números medidos.
- **G2 = A:** seleção pela API da Anthropic, paga por uso, com teto de gasto
  mensal definido pelo Bruno.
- **G3 = C:** no beta, o **PC Windows do Bruno é o worker**: busca os
  trabalhos na fila da nuvem por conexão de saída (sem porta aberta). O
  worker nasce portátil para mudar de máquina quando a venda começar.
- **G4 = A:** a **N-1 abre agora**, neste branch
  (`claude/loving-newton-bykd21`), sem esperar o merge do F6.1. Prefixo
  **`[CLIP-N1]`**. `master` intocado.
- Regras que seguem valendo: CLAUDE.md §4 (provas estruturais + físicas,
  `main(argv)`, zero dependência nova sem decisão), §5 e §6; o worker **não
  duplica regra de estágio** — chama as mesmas funções do `clipper`, como o
  painel.

### 27.2 Resultado do primeiro checkpoint da N-1

- `worker/` (contrato, fila e depósito em pasta, executor, `python -m
  worker`) + `provas/prova_n1.py`. Motor e painel intocados.
- Placar (Linux, físicas): N-1 **11/0/0**, F6.1 13/0/0, F6 44/0/0; 12 de 12
  mutantes mordem. Relatório: `docs/lote-clip-f6/relatorio-n1.md`.
- **PARE** até P1 (fornecedor da fila, arquivos e login) e P2 (medir tokens
  por trabalho).

---

## 28. Respostas P1 e P2 (formulário de 15/10)

Recebidas em 15/10/2026 pelo formulário de perguntas da sessão. Transcrição
verbatim (pergunta → resposta).

```
"P1 — Onde ficam, na nuvem, a fila de pedidos, os arquivos (vídeos e clipes)
 e o login? Todas as opções são grátis."
  = "Supabase + Cloudflare R2 (Recomendado)"
"P2 — Medir quanto a IA custa em cada vídeo? É o número que define o preço
 do crédito." = "Sim, por trabalho (Recomendado)"
```

### 28.1 Efeitos

- **P1 = A:** Supabase (banco: fila, contas, créditos; login com e-mail e
  Google) + Cloudflare R2 (arquivos). Planos grátis (§27, G1). As contas são
  criadas pelo Bruno; chaves **nunca** entram no repositório (vão em variável
  de ambiente na máquina do worker).
- **P2 = A:** o estágio de seleção passa a devolver os tokens usados no
  resultado que entrega ao motor; o worker grava por trabalho. Nenhum arquivo
  muda de formato; `VERSAO` não sobe (o vídeo renderizado não muda).
- Próximo passo da N-1: fila no Supabase e depósito no R2, com as mesmas
  provas por dentro; a física contra as contas reais fica **pendente** até
  as contas existirem.

### 28.2 Resultado do segundo checkpoint da N-1

- P2 na seleção (`uso_api`, nenhum arquivo muda de formato); `worker/nuvem.py`
  (Supabase + R2, só biblioteca padrão); `nuvem/supabase/001_fila.sql`;
  `--nuvem`; roteiro de contas em `docs/nuvem/roteiro-contas.md`.
- Placar: N-1 **16 passaram, 1 pendente (N-F4, contas reais), 0 falharam**;
  F6 44/0/0; F6.1 13/0/0; 13 de 13 mutantes novos mordem. Relatório:
  `docs/lote-clip-f6/relatorio-n1.md` §7.
- **PARE.** A N-1 fecha com a N-F4 verde no Windows; a N-2 abre com a palavra
  do Bruno.

---

## 29. Delegação — "O restante faça com oq achar recomendado"

Recebida em 15/10/2026. Transcrição verbatim.

```
O restante faça com oq achar recomendado
```

### 29.1 Leitura do executor (declarada)

- **Delegação ampla.** No que resta do plano (N-2, N-3, N-4 e os itens que já
  têm recomendação registrada), **a recomendação do executor vale como
  decisão**. Cada uma é registrada aqui como "decidida por delegação (§29)"
  **antes** de ser executada e é relatada no checkpoint. O Bruno pode
  reverter qualquer uma: vence o item mais recente.
- **Fora da delegação** (só o Bruno faz ou decide):
  - criar contas, chaves e cartão;
  - o teto de gasto da Anthropic;
  - CNPJ e nota fiscal;
  - a revisão jurídica dos termos;
  - o **preço dos pacotes de crédito** (é dinheiro: a recomendação vem com o
    custo medido, mas a decisão é dele);
  - o **merge em `master`** (o CLAUDE.md §2 exige palavra explícita e provas
    físicas verdes no Windows).
  Comando destrutivo continua vedado, e chave não vai para o chat nem para o
  repositório.
- **Deploy do app:** só quando as contas existirem, porque sem as chaves o app
  não funciona. Publicar é um passo do roteiro.

### 29.2 Decidido por delegação (§29) agora

- **F8a:** Q1–Q19 = as recomendações da folha de resposta de
  `perguntas-f8a.md`. A implementação vem depois do núcleo da nuvem (N8 A) e
  começa pela Q17 (regressão que morde).
- **Site:**
  - S1 = manter a produção pública e os previews com login (é página pública);
  - S3 = `og:url` + `canonical` no repositório, publicados junto com a
    atualização da N-4 (N9 B);
  - S5 = sem `LICENSE`, o que por lei é "todos os direitos reservados", até o
    dono decidir.
- **Créditos entram já na N-2:** saldo, reserva por trabalho e devolução do
  que não foi usado. A N-3 acrescenta só a compra (Mercado Pago).
- **Beta fechado (G1) por convite:** só e-mail convidado recebe os 300
  créditos e pode pedir clipes. O convite é uma linha na tabela `convites`.

### 29.3 Desenho da N-2 (app), decidido por delegação (§29)

- **App estático sem build** em `app/` (HTML + CSS + JS puro, como o painel e
  o site), com o `supabase-js` **2.117.2 embutido** em `app/vendor/`
  (integridade sha512 conferida com o registro do npm; nada de CDN em tempo
  de execução).
- **Funções Python da Vercel** em `api/`, só com a biblioteca padrão:
  - `config` (entrega URL e chave **pública** do Supabase, que vêm do
    ambiente da Vercel);
  - `upload` (URL assinada para enviar o vídeo ao R2);
  - `clipes` (URLs assinadas para ver e baixar os clipes do próprio usuário).
- **Código compartilhado em `nuvem/`** (`s3.py`, `rest.py`), usado pelo
  worker e pelas funções: a assinatura S3 existe num lugar só.
- **Projeto Vercel novo** (`clippro-app`) com raiz na raiz do repositório e
  um `.vercelignore` que só deixa entrar `app/`, `api/` e `nuvem/`. O
  `requirements.txt` pesado do motor fica fora do deploy.
- **Banco** (`nuvem/supabase/002_contas.sql`):
  - perfis, convites e movimentos de crédito;
  - saldo = soma dos movimentos;
  - o cadastro convidado ganha 300;
  - `criar_trabalho` reserva até 600 min do saldo e devolve o que não foi
    usado quando o trabalho termina (uma trigger, idempotente);
  - RLS: cada conta só lê o que é seu.
- **Provas:**
  - `provas/prova_n2.py` (SQL num Postgres real, funções contra Supabase e
    S3 falsos);
  - interface pelo Playwright num Chromium real, contra um backend falso
    local. A prova de interface **pula** onde não há Node + Playwright, como
    as de ffmpeg pulam sem ffmpeg.

### 29.4 Resultado da N-2 (decidida por delegação)

- `app/` (identidade do site, fontes locais, `supabase-js` embutido), `api/`
  e `nuvem/` (lógica compartilhada), `002_contas.sql`, `vercel.json` e
  `.vercelignore`.
- Placar: N-2 **7/0/0** (SQL num Postgres real; interface num Chromium real
  contra a nuvem falsa); N-1 16/1 pendente/0; 13 de 13 mutantes da N-2
  mordem. Relatório: `docs/lote-clip-f6/relatorio-n2.md`.
- Com o Bruno: contas, Auth, Google, CORS, projeto Vercel com produção
  pública e produção no branch de trabalho (roteiro §7).
- A **N-3** (compra de créditos, Mercado Pago) segue pela delegação; o
  **preço dos pacotes fica com o Bruno**.

### 29.5 Desenho da N-3 (compra de créditos), decidido por delegação (§29)

- **Checkout Pro do Mercado Pago, pela API de Preferências.** É suportada; o
  Mercado Pago recomenda a de Orders para integrações novas, e a troca fica
  registrada como melhoria. O usuário escolhe o pacote, paga no Mercado Pago
  (Pix, cartão) e volta ao app.
- **O crédito só entra depois de conferir o pagamento direto na API do
  Mercado Pago:** status aprovado, BRL e o valor exato do pacote. Não basta o
  aviso que chegou. O webhook ainda precisa ter a assinatura `x-signature`
  válida (HMAC-SHA256 do manifest oficial). A confirmação é idempotente:
  pagamento repetido não credita duas vezes.
- **Desligada por padrão** (`COMPRAS_ATIVAS`). Vender exige, antes:
  - o preço dos pacotes, que é do Bruno;
  - o plano Pro da Vercel (uso comercial, §26/G1);
  - termos e privacidade (N-4);
  - a conta e as credenciais do Mercado Pago.
- **Pacotes numa tabela** (`pacotes`) que o Bruno preenche. O app só mostra
  os ativos. **Nenhum preço é definido pelo executor.**
- O webhook usa a **chave secreta do Supabase no ambiente da Vercel**, só
  para chamar `confirmar_compra`, a única função que credita uma compra. É o
  único uso da chave secreta fora do worker.
- **Extrato visível ao usuário:** cadastro, reservas, devoluções e compras.
- Estorno ou chargeback não debita automaticamente no beta; fica registrado
  como pendência.

### 29.6 Resultado da N-3 (decidida por delegação)

- `003_compras.sql`, `nuvem/mercadopago.py`, `api/comprar.py`,
  `api/mp_webhook.py`, e as telas Créditos e Volta do pagamento.
- **Desligada por padrão** (`COMPRAS_ATIVAS`).
- Placar: N-3 **6/0/0**; N-2 7/0/0; 11 de 11 mutantes de dinheiro mordem.
  Relatório: `docs/lote-clip-f6/relatorio-n3.md`. Roteiro do Mercado Pago:
  `docs/nuvem/roteiro-contas.md` §8.
- **Ligar as vendas** exige V1–V6, que ficam com o Bruno: preço, Vercel Pro,
  termos, credenciais, sandbox e nota fiscal.

### 29.7 N-4 (decidida por delegação): o que foi feito e o que fica para o lançamento

- **Feito:**
  - `app/termos.html` e `app/privacidade.html`, como **rascunhos marcados**,
    com campos a preencher (N10: o executor redige, o Bruno revisa);
  - consentimento no cadastro e rodapé com os dois links;
  - o app avisa até quando os clipes ficam disponíveis (30 dias);
  - prazos de guarda no roteiro §9 (ciclo de vida do R2: entradas 3 dias,
    resultados 30 dias);
  - S3 (`og:url` + `canonical`) no site, publicado junto com a próxima
    atualização.
- **Decidido:** créditos sem prazo de validade; direito de arrependimento de
  7 dias para créditos não usados. As duas escolhas vão à revisão jurídica.
- **Fica para o lançamento** (N9 = B): a reescrita do site público para a
  versão na nuvem. Depende do preço e da data, que são do Bruno.
- Placar final: N-1 16/1 pendente (N-F4, contas reais)/0; N-2 7/0/0; N-3
  6/0/0; F6.1 13/0/0; F6 44/0/0.

## 30. Diretiva do Bruno (16/10/2026): design mais profissional

Texto, na íntegra:

> "Melhore o design e layout, ao escolher o modelo do clipe, deixe mais
> profissional, o app esta muito com cara de IA"

Leitura do executor, decidida pela delegação do §29 (escolhas de design são
do executor; preço, contas e merge continuam com o Bruno):

- Vale para o **app** (`app/`). O site público segue pela N9 = B (muda no
  lançamento).
- **Escolha do modelo do clipe** é a prioridade nomeada: a prévia de cada
  modelo deve mostrar o que o motor de fato entrega, e não uma ilustração.
- O comportamento provado (créditos, upload, rotas, segurança, CSP sem
  terceiros) **não muda**; as provas de interface se ajustam ao novo layout,
  conferindo as mesmas coisas.

### 30.1 Resultado da N-5 (decidida por delegação, §29)

- **App redesenhado como ferramenta.**
  - Saíram claquete, película, ingresso, REC, brilhos, rótulos mono e o
    jargão "rolos"/"ilha de edição".
  - Entraram compositor em seções, lista de projetos, menu da conta e clipe
    deitado (vídeo + decisão).
- **Galeria de modelos fiel ao motor.**
  - A tabela `PREVIAS` é gerada dos presets e conferida pela N5-E1.
  - O karaokê segue a regra de cores de `legendas._bloco_palavra`.
  - O quadro do vídeo do usuário entra nas prévias, sem sair do aparelho.
- **Pergunta ao Bruno (Q-N5-1):** mostrar a miniatura do YouTube nas prévias
  quando o pedido é por link? Exige pedir a `i.ytimg.com`, um terceiro, e
  mudar a Política de privacidade. Recomendação do executor: **não**, manter
  o fundo neutro.
- A N5-F1 roda sob a CSP de produção do `vercel.json`.
- Placar: N-5 3/0/0 (11 de 11 mutantes mordem); N-2 7/0/0; N-3 6/0/0; N-1
  16/1 pendente/0; F6.1 13/0/0; F6 44/0/0. Relatório:
  `docs/lote-clip-f6/relatorio-n5.md`.

### 30.2 O Bruno fez o merge do PR #1 no `master` (registro, 16/10/2026)

- **Fato, sem diretiva no chat.** O próprio Bruno abriu o PR #1
  (`claude/loving-newton-bykd21` → `master`) e fez o merge às 21:30 de 15/10
  (−03:00). O `master` foi de `aa958d0` para `b85d323` e passou a ter tudo até
  `c1d15b2`: o F6.1, a nuvem N-1 a N-4 e o §30. É a palavra de merge dele
  (CLAUDE.md §2). O executor não tocou no `master`.
- **Ficou de fora:** a N-5 (`b1c171c`, design do app), commitada depois do
  merge.
- **O que o executor fez:** um merge do `master` no branch de trabalho, sem
  reescrever histórico (`e93c697`). O branch agora é o `master` mais a N-5.
  Levar a N-5 ao `master` exige um PR novo; o executor não abre PR sem pedido.
- **Consequência para a Vercel** (roteiro §7.6): a produção do app pode ser o
  `master`, que já tem o app. A N-5 só aparece lá depois do merge dela.
- **Pendências do F6.1 que o merge não resolveu:** W1–W3 e W5 (provas no
  Windows), que agora valem como conferência pós-merge.
