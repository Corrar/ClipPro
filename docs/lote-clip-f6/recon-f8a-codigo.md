# Recon de código do F8a (antes de implementar)

Base: `ecd79b4`. Gerado por 4 leitores em paralelo (S1 legenda, S2 gancho/seleção,
resolução de preset, provas/convenções) e um crítico de completude que conferiu
no código as afirmações decisivas. **Nenhum código alterado.** A crítica (§ final)
corrige os relatórios onde eles erram e prevalece sobre eles.

O F8a está **pausado** (RULINGS §21): o site entrou na frente. As colisões
listadas na crítica, seção (c), voltam ao arquiteto como perguntas antes de
qualquer código do F8a.

---

### S1-legenda
# S1: teto de blocos de 1 palavra da legenda (só leitura, nada editado)

Base: branch `claude/charming-euler-02p9cf` @ `ecd79b4`, `git status` limpo antes e depois. As medições rodaram por scripts no scratchpad, fora do repositório.

Resposta curta: **não existe "teto 3" próprio para blocos de 1 palavra**. O 3 é o `max_palavras_linha` dos presets compostos. Somar qualquer campo a `legendas.Preset`, mesmo com padrão neutro, **muda a identidade de cache dos 4 presets de fábrica**. Isso foi demonstrado, e hoje não existe mecanismo que evite.

---

## 1. Onde está o "teto 3"

**Não há constante.** O 3 é o campo obrigatório `max_palavras_linha: int` (`clipper/legendas.py:54`). Ele vale 3 em `cortes.json:18` e `cortes-editorial.json:18`, 4 em `bold-amarelo.json:17` e 5 em `clean-branco.json:17`.

O **mesmo campo** é aplicado em dois lugares:

**a) No agrupamento.** `montar_ass` passa `max_palavras=preset.max_palavras_linha` (`legendas.py:536-542`). A linha fecha em `len(atual) >= max_palavras` (`:233-237`) ou no fim de frase (`:246-248`).
- O valor vai cru, sem `int()` (`:538`), ao contrário dos campos F6.

**b) Na fusão.** `fundir_curtos(..., maximo=int(preset.max_palavras_linha), ...)` (`legendas.py:547-552`).
- O piso vem de `min_palavras_linha`: o padrão é 0 (`:78`), e cortes/editorial usam 3 (`cortes.json:20`).
- Com `minimo <= 1` a função sai sem fazer nada (`:301-302`).

**"Travada pelo teto 3 dos dois lados"**, no código: para um bloco de 1 palavra na posição `i`:
- para a frente, a fusão exige `len(bloco) + len(proximo) <= maximo` (`:314`);
- para trás, exige `len(anterior) + len(bloco) <= maximo` (`:322`).

Com os dois vizinhos já cheios em 3 palavras, dá 1+3=4 > 3 dos dois lados e o bloco fica sozinho. A origem típica é uma frase de 4 palavras que o agrupamento corta em [3][1], seguida de outra frase que abre com 3.

A fusão **só conta palavras**: ignora `max_caracteres_linha` e a largura. A largura só é tratada depois, em `quebrar_bloco` (`:576-582`, `:330-371`):
- no máximo 2 linhas;
- se nenhum corte cabe, devolve 1 linha estourada (`:366-370`);
- sem medidor nunca há `\N` (`:346`).

**O que foi decidido sobre isso no RULINGS:**
- Q2 (B): "o teto de cada preset NÃO muda (3 segue 3)" (`RULINGS.md:77-80`).
- Limite medido na fixture sintética, 5→1: "Com teto 5 iriam a zero, mas isso mudaria pixel além do E3" (`:319-322`).
- D2 item 4: "o bloco de 1 palavra no fim FICA — limite conhecido; o teto não afrouxa" (`:500-501`).
- D5/P05: "o teto é parâmetro de modelo e volta no F8" (`:759-760`).
- Números reais 36→18 (`cortes`) e 39→17 (`cortes-editorial`) (`:795-799`).
- A S1 aparece em `recon-f8a.md:12` e em `RULINGS.md:1079-1080`.

**Reprodução aqui** (fixture real `wetyO2gOOeU`, os 5 trechos aprovados):

| | sem medidor | com medidor |
|---|---|---|
| `cortes-editorial` | **39→17** | **39→17** |
| `cortes` | 33→20 | 64→14 |

- O 39→17 do `cortes-editorial` bate exatamente com o RULINGS.
- O 36→18 do `cortes` **não reproduz** neste ambiente. Aqui o medidor usa a fonte reserva DejaVu (`composicao.py:656-664`), porque a Impact não existe no sandbox.
- Hipótese **não verificada**: o D4 foi medido na máquina Windows com Impact instalada (`RULINGS.md:619-640`). O método que gerou 36/18 não está registrado em lugar nenhum.

**Por que os blocos de 1 palavra sobram** (transcrição inteira, teto 3):

| Preset | Total | Teto dos dois lados | Lacuna em algum lado | Borda |
|---|---|---|---|---|
| `cortes`, sem medidor | 37 | 29 | 8 | — |
| `cortes`, com DejaVu | 32 | 21 | 10 | 1 |
| `cortes-editorial` | 36 | 25 | 11 | — |

**Simulação de um teto de fusão separado** (o agrupamento segue em 3, 5 trechos):

| Teto de fusão | Blocos de 1 palavra |
|---|---|
| 3 | 14–20 |
| 4 | 2–3 |
| 5 | 2–3 |

O custo aparece em `cortes` (com medidor DejaVu, transcrição inteira + 5 trechos), indo de teto 3 → 4 → 5:
- blocos acima de 18 caracteres: 58 → 165 → 271;
- blocos com `\N`: 162 → 266 → 348;
- linhas estourando a largura: 13 → 31 → 41.

Os números dependem da fonte; só a tendência vale.

### ⚠ Colisão entre o plano e o código: a S1 é ambígua

O texto diz "hoje fixo em 3", mas o teto **já é parâmetro do modelo** (`max_palavras_linha` no JSON). O que está fixo é o **acoplamento**: a fusão usa o mesmo teto do agrupamento. Há duas leituras:

- **(R1) Nada novo.** Um modelo do usuário muda `max_palavras_linha`. Isso muda também o agrupamento, e todas as linhas passam a ter até N palavras: é o "mudaria pixel além do E3" (`:321-322`).
- **(R2) Campo novo só para a fusão.** O padrão seria um sentinela que significa "usa `max_palavras_linha`". O precedente é `margem_direita=-1` (`legendas.py:91-94`, `:110-112`). Com isso a fábrica sai byte a byte igual.

**Recomendação: (R2).** A escolha é do arquiteto, e ela inclui o nome do campo. Também fica para ele decidir se algum preset de fábrica recebe um valor diferente do padrão; isso esbarraria no D2 item 4, "o teto não afrouxa".

## 2. Do JSON aninhado ao dataclass

Os campos de legenda são **folhas do topo** da forma aninhada. Não há subárvore nem passo de resolução (diferente de `cartao.fracao_altura`).

**`legendas.Preset.de_dict`** (`legendas.py:96-99`): `{f: dados[f] for f in cls.__dataclass_fields__ if f in dados}`.
- Ignora o resto em silêncio.
- **Não converte tipo nem confere faixa.** Os campos F6 levam `int()`/`float()` no ponto de uso (`:549-551`, `:581`, `:592`).
- Campo obrigatório ausente vira `TypeError`. O render captura e lista o que falta (`render.py:211-238`); `Modelo.de_dict` não captura (`modelo.py:184`).
- Os padrões seguem a regra "igual à fase anterior": F4a em `:57-70`, F6 em `:72-94` ("byte a byte").

**`clipper/modelo.py`:**
- `_CONHECIDAS["__folhas__"]` (`:55-67`) já traz os campos F6 em `:64-66`. O campo novo entra aí.
- `_desconhecidas` fica em `:128-141`.
- `de_dict` (`:175-188`):
  - a legenda sai de `legendas.Preset.de_dict({**dados, "nome": nome})` (`:184`), e o nome é o stem do arquivo (`:180`, `:194`);
  - a composição sai de `de_preset` (`:185`);
  - `fonte_json` é a fonte normalizada (`:186`) e `_avisos` a lista de chaves desconhecidas (`:187`).
- `para_json()` devolve a própria fonte (`:205-207`). O round-trip só carrega a chave nova se ela estiver no arquivo.
- `avisos()` fica em `:220-222`.
- `impressao()` (`:231-241`) delega para `Composicao.impressao()`. **A legenda não entra**, e sem composição devolve `""`.

"Duas camadas", para um campo de legenda, quer dizer:
1. a folha em `_CONHECIDAS`;
2. o campo no dataclass, com padrão.

Se faltar a primeira, `avisos()` acusa a chave, e a E-M3 falha caso ela vá para o `cortes.json` (`prova_f6.py:266-268`).

**Os 4 presets:**
- Os campos F6 só existem em `cortes.json:20-23` e `cortes-editorial.json:20-23` (`min_palavras_linha` 3, `gap_maximo_fusao_s` 1.2, `max_linhas_bloco` 2, `destaque_minimo_letras` 3).
- `bold-amarelo` e `clean-branco` não têm campo F6, nem pop, nem `composicao`: seguem o caminho F3.

**O render não usa `Modelo`:**
- `carregar_preset` → `_ler_preset` (`render.py:166-206`) lê só `DIR_PRESETS/<nome>.json` e faz `setdefault("nome")` (`:205`) → `Preset.de_dict` (`:209-213`).
- `carregar_composicao` → `de_preset` (`:283-290`).
- Nos 4 de fábrica o stem do arquivo é igual ao `"nome"` interno (linha 2 de cada JSON), então os dois caminhos coincidem.

## 3. Cache e identidade

**Três camadas:**

**a) Assinatura do estágio** (`render.py:2431-2450`): preset (nome), largura, altura, `estilo=comp.impressao(pitch)`, pitch, a impressão de `selecao.json`, transcrição e energia.
- **Nenhuma identidade de legenda.**
- A comparação é string JSON (`config.py:139-158`).

**b) Reaproveitamento por clipe:** `_clipe_reaproveitavel` (`render.py:1388-1460`) chama `_mesmo_estilo` (`:1352-1384`).
- A impressão da composição tem de bater (`:1373`).
- `legenda_impressao` só é comparada quando o metadado anterior a traz (`:1375-1377`).

**c) `impressao_legenda`** (`render.py:1335-1349`) é o ponto decisivo:
```python
corpo = json.dumps(dataclasses.asdict(preset_obj), sort_keys=True, ensure_ascii=False)
return hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:16]
```
É o asdict **flat inteiro**, sem filtro nenhum.
- No metadado, os compostos gravam `versao`/`impressao`/`legenda_impressao` (`:1733-1737`); o caminho F3 grava só `{"legenda_impressao": ...}` (`:1789`).
- `Composicao.impressao` (`composicao.py:270-286`) cobre só a Composicao + `VERSAO`, e soma `pitch` apenas quando ligado (`:277-284`).

**Resposta: sim, a chave muda.** Simulei com `make_dataclass(bases=(Preset,))` um campo `int = 0` que ninguém lê:

| Preset | Hoje (`ecd79b4`) | Com campo novo |
|---|---|---|
| cortes | `6eff370c49b2277c` | `7f31eeee133a66e1` |
| cortes-editorial | `95edae0fb8870f39` | `6bc392e2a0ff3e1e` |
| bold-amarelo | `16c6f5d4fabb5aeb` | `55a69baffd90e055` |
| clean-branco | `d085151441e51159` | `ac1bc52d46665ebd` |

O efeito fica **latente**:
- numa repetição pura, o atalho do estágio pula tudo (`render.py:2450-2458`);
- na próxima vez que o estágio for reaberto (seleção nova, `--force`, transcrição, energia, edição da composição), **todo clipe recodifica**, inclusive os do caminho F3, onde `VERSAO` nem entra;
- o F6 já está em `master` (`aa958d0`, D7), então isso atingiria os clipes que já existem.

**Como os campos F6 entraram:** o mesmo commit `1a4ba89` somou os 5 campos (`legendas.py:78-94`) e subiu `VERSAO` de 2 para 3 (`composicao.py:66-72`).
- Nos compostos, a mudança coincidiu com o bump deliberado (R7).
- **Em `bold-amarelo` e `clean-branco`, a identidade mudou só por efeito colateral de somar campo.** O `.ass` deles sai byte a byte igual (`prova_f6.py:307-310`), e mesmo assim os clipes re-renderizam.
- Isso não está registrado em nenhum doc (grep por `legenda_impressao` em `docs/` não acha nada). **Precedente que viola a regra — destacado aqui.**

**Mecanismo:** não existe nenhum em `impressao_legenda`. Os precedentes no código são:
- o `pitch` só entra no hash quando ligado (`composicao.py:277-284`);
- o "compara só se o metadado anterior traz" (`render.py:1364-1367`);
- o padrão sentinela de `margem_direita`.

Opções para o arquiteto:
- **(i)** `impressao_legenda` exclui uma **lista fechada** de campos pós-F6 quando valem o padrão. Os hashes de fábrica ficam iguais, e um valor fora do padrão entra no hash.
- **(ii)** *Não* generalizar para "omitir todo campo no padrão": isso mudaria o hash atual de presets com campos F6 no padrão. `bold-amarelo`, por exemplo, tem `min_palavras_linha=0` dentro do hash hoje.
- **(iii)** Subir `VERSAO`: é proibido aqui, porque o resultado não muda, e nem alcança o caminho F3.

**⚠ Colisão com o recon:** `recon-f8a.md:35-37` recomendou o escopo A por "não tocar em render". A S1 obriga a mexer em `legendas.py` e, para preservar a identidade, em `render.py:1335-1349`.

**Lacuna pré-existente, fora da S1 mas que morde o F8a:** a assinatura do estágio não leva a legenda (`render.py:2436-2447`). Editar só campos de legenda de um modelo e rodar `render` de novo cai em "já estão prontos… pulando" (`:2450-2458`). Isso foi lido no código, não executado.

## 4. Provas que tocam isso (rodadas aqui: 9/9 verdes)

O que rodei: `python provas/prova_f6.py E-M1 E-M3 E-R1 E-R2 E-L1 E-L2 E-L3 E-L4 E-X2`.

| Prova | Onde | O que confere | Efeito da S1 |
|---|---|---|---|
| **E-R2** | `prova_f6.py:300-353` | Os dois presets F3 byte a byte (`:307-310`), mas nos compostos só cabeçalho/MarginV e "não criou bloco" (`:319-338`) | Neutra para os F3 (`minimo` 0 sai cedo, `legendas.py:301`). **Não prova neutralidade nos compostos:** subir o teto de fusão reduz blocos e passa verde |
| **E-R1** | `:271-297` | Filtergraph; a legenda entra como string fixa (`:100`) | Nenhum |
| **E-L1** | `:405-430` | ≤ `max_palavras_linha` (`:417-419`), ≤ 2 linhas, de-uma < baseline | Falha se um preset de fábrica fundir acima de `max_palavras_linha` |
| **E-L3** | `:468-525` | Chama `fundir_curtos(minimo=, maximo=, gap_maximo=)` por keyword (`:485-505`) e espelha `maximo=preset.max_palavras_linha` (`:513-515`, `:523-525`) | Quebra se a assinatura mudar; fica desatualizada em silêncio se o render passar outro teto |
| **E-X2** | `:1840-1895` | Maior ≤ 7 e ≤ `max_palavras_linha` (`:1888-1890`) | Mesmo efeito da E-L1. Hoje (com DejaVu): cortes 809 blocos/46 de 1 palavra; editorial 789/53; bold 643/82; clean 530/53 |
| **E-M1** | `:181-223` | Round-trip | Segue verde |
| **E-M3** | `:250-268` | `cortes` com zero avisos | Exige a chave nova em `_CONHECIDAS` se ela for para o JSON |

- E-L2, E-L4 e E-C4 (`:1436-1500`, que usa `max_linhas_bloco`) não são afetadas.
- `prova_f61.py` e `ui/provas/` não tocam em legenda.

**Baseline:** `provas/fixtures/baseline/` tem 6 arquivos capturados de `12fc1e2b`, **antes do F6**. **Nenhuma prova hoje garante "padrão = comportamento atual" byte a byte nos compostos.** Para isso é preciso uma referência nova, e isso é decisão do arquiteto:
- um `.ass` congelado em `ecd79b4`;
- e/ou os 4 hashes de `impressao_legenda` da tabela acima.

**Para continuar verde:**
- padrão igual ao comportamento atual;
- campo em `_CONHECIDAS` e no dataclass;
- manter os nomes de keyword de `fundir_curtos`, ou atualizar a E-L3;
- se algum preset passar a usar teto de fusão maior que `max_palavras_linha`, a E-L1, a E-L3 e a E-X2 têm de conferir contra o teto efetivo de fusão.

**Fora da frente:** em `ui/jobs.py:538` e `:558`, "modelo" é o modelo do Whisper (`motor.MODELO_PADRAO`). O nome colide com o "modelo" do F8a.

Scripts de medição:
- /tmp/claude-0/-home-user-ClipPro/a6c45088-77bb-59ae-9bce-89eebcd589cd/scratchpad/medir_s1.py
- /tmp/claude-0/-home-user-ClipPro/a6c45088-77bb-59ae-9bce-89eebcd589cd/scratchpad/medir_s1b.py
- /tmp/claude-0/-home-user-ClipPro/a6c45088-77bb-59ae-9bce-89eebcd589cd/scratchpad/medir_s1c.py

### S2-gancho
# S2: teto de 4 linhas do gancho na seleção (recon, só leitura)

Base: `claude/charming-euler-02p9cf` @ `ecd79b4`. Não editei nenhum arquivo do repositório. As medições rodaram só no scratchpad (`/tmp/claude-0/-home-user-ClipPro/a6c45088-77bb-59ae-9bce-89eebcd589cd/scratchpad/`).

---

## 1. Como o render quebra o gancho hoje

**Caminho.**
- `render.py:1713-1719` chama `composicao.gerar_ativos(comp, titulo, trabalho, gancho=clipe["gancho_sugerido"], conclusao=...)`.
- Em `gerar_ativos`, o texto do topo é escolhido assim (`composicao.py:1057-1069`):
  - com `comp.gancho_ativo`, o texto é o gancho; gancho vazio deixa o topo limpo, sem cair no título (`1060-1063`);
  - sem ele, vale o título, se `titulo_ativo` estiver ligado.
  - A chamada é `pilula_titulo(comp, texto_do_topo, alvo, truncar=not comp.gancho_ativo)` (`1069`), então o gancho vai sempre com `truncar=False`.

**Função exata** (`composicao.py:891-1011`):
```python
def pilula_titulo(comp: Composicao, titulo: str, destino: Path, *, truncar: bool = True) -> dict[str, Any]
```
O que ela faz, em ordem:

- **Texto.** Junta os espaços e aplica `upper()` se `titulo_maiusculas` (`908-910`).
- **Largura útil.** `util = max(80, titulo_largura_maxima - 2*titulo_padding_h)`. Com acento `barra`/`circulo`, subtrai ainda `acento_largura + acento_gap` (`912-914`).
  - `cortes`: 810−72−30 = **708 px**.
  - `cortes-editorial`: 810−80−30 = **700 px**.
- **Encolhimento.** Começa em `titulo_tamanho` e chama `_quebrar_titulo(texto, fonte, util, 2)`.
  - O alvo de **2 linhas é fixo no código** (`921`, `925`), não vem do modelo.
  - Enquanto `sobrou and tamanho > titulo_tamanho_minimo`, faz `tamanho -= 2` e recarrega a fonte com `_fonte` (`922-925`).
  - `sobrou` fica verdadeiro quando o texto não cabe em 2 linhas **ou** quando uma palavra sozinha é mais larga que `util` (`853-855`).
- **3+ linhas.** Se ainda sobra no piso e é gancho, roda `_quebrar_sem_cortar(texto, fonte, util)` no corpo mínimo, em quantas linhas precisar. Palavra maior que a caixa quebra por letra (`927-930`, `858-888`). **Só nesse ponto nascem 3+ linhas.**
- **Altura.**
  - `altura_linha = ascendente + descendente` (`getmetrics`, `942-943`).
  - `respiro = max(16, int(altura_linha*0.30))`.
  - `altura = _par(max(titulo_altura, altura_linha*linhas + 2*respiro))` (`950-956`).
- **Gravação.** Desenha e grava o PNG com `_salvar(imagem, destino)` (`1000`).
  - Devolve `{"arquivo","largura","altura","linhas","tamanho","truncado","texto_linhas"}` (`1001-1011`).
  - O render avisa quando `linhas > 2` (`render.py:1763-1777`) e grava `titulo_linhas`/`titulo_tamanho` no estilo (`render.py:1746-1748`).

**Parâmetros do modelo que decidem o número de linhas.**
- O gancho **não tem tipografia própria**: o bloco `gancho` só tem `ativo, duracao_s, fade_saida_s, y` (`modelo.py:92-94`, `composicao.py:382-389`). Tudo vem de `composicao.titulo`:
  - `fonte`, `arquivo`;
  - `tamanho`, `tamanho_minimo`;
  - `maiusculas`;
  - `largura_maxima` (o padrão é a largura do cartão, `371`), `padding_h`;
  - `acento`, `acento_largura`, `acento_gap`;
  - e `gancho.ativo`: se estiver desligado, o gancho nem é desenhado.
- Fixos no código: alvo de 2 linhas, passo de 2 px, `util` mínimo de 80.
- Por modelo de fábrica:
  - `cortes`: Segoe UI Black (`seguibl.ttf`), 44→34.
  - `cortes-editorial`: Bahnschrift, 42→32.
  - `bold-amarelo` e `clean-branco`: sem composição (`comp` é None), então o gancho nunca é desenhado.
- Nota menor: o laço desce abaixo do mínimo se `tamanho - minimo` for ímpar (`922-924`). Nos dois presets a diferença é par.

**Dá para chamar sem renderizar? Não existe função pura.**
- `pilula_titulo` exige Pillow e um `destino`, e **sempre grava o PNG** (de forma atômica, `579-595`). Não precisa de ffmpeg nem de vídeo.
- `_quebrar_titulo` e `_quebrar_sem_cortar` são puras: só usam `fonte.getlength`.
- O laço de encolhimento, porém, está embutido em `pilula_titulo` (`916-930`) e chama `_fonte` por dentro, sem ponto de injeção.
- Para o validador medir sem gravar PNG, seria preciso extrair `908-930` numa função nova. Se o PNG não mudar, isso não exige VERSAO.
- Já existe precedente de outro módulo importar a função privada de fonte: `legendas._medidor` importa `composicao._fonte` (`legendas.py:157-177`).

**Fonte ausente: há fallback, e ele nunca levanta** (`composicao.py:612-674`). A ordem de tentativas é:
1. o `arquivo` do preset;
2. a tabela `_ARQUIVOS_DE_FONTE` (`76-92`);
3. o nome sem espaços + `.ttf`;
4. uma varredura de `%WINDIR%\Fonts` pela família (`637-647`) — no Linux essa pasta não existe;
5. reservas `segoeui.ttf`, `arial.ttf`, `DejaVuSans.ttf`, com aviso *"a barra de título vai sair em X"* (`655-665`);
6. `load_default(size)`, com aviso (`666-674`).

Neste sandbox nenhuma fonte do preset abre (seguibl, impact, bahnschrift, segoeui, arial) e cai em **DejaVu Sans**. O aviso sai a cada chamada: 99 avisos para 2 modelos × 10 textos.

**O número de linhas depende da máquina.** Medido aqui contra o Windows (`relatorio-p5.md:86-89`):

| | Linux (DejaVu Sans) | Windows (fonte real) |
|---|---|---|
| `cortes`, 5 ganchos reais | [3,2,2,2,3] | até 3 |
| `editorial`, 5 ganchos reais | [2,2,2,2,3] | **2** |
| PT caixa alta, 90 caracteres: `cortes` / `editorial` | 4 / 3 | 4 (base y=412) / 3 |
| pior caso ≤90 caracteres, `cortes` | 7 | **9** |
| `"W"*90`, `editorial` | 5 (com `load_default`: 4) | — |

**F-G3** (`prova_f6.py:2192-2239`):
- Está registrada em FÍSICAS (`2293`), embora não use ffmpeg.
- Chama `gerar_ativos` direto e não confere qual fonte abriu nem pula quando ela falta.
- Só afirma "não truncado" e "texto inteiro" (`_texto_inteiro`, `2173-2189`). As linhas aparecem só no detalhe, sem asserção.
- Rodei a função apontando para o scratchpad: **passa no Linux com DejaVu.** Não guarda teto nenhum.

**E-C4** (`1456-1494`):
- É ESTRUTURAL e contorna a fonte estimando `altura_linha = titulo_tamanho × 1,38` na pílula e `× 1,35` na legenda (`1410-1430`). As 2 linhas são fixas (`1466`).
- Não conta linhas. Passa aqui: vão de 26 px no `cortes` e 80 px no editorial.

**Precedente aplicável:** a E-L4 (`prova_f6.py:528-557`) injeta um medidor sintético porque *"a fonte real é do Windows… que a fonte real meça o que se espera é prova física"*.

---

## 2. O validador da seleção (`clipper/pipeline/select.py`)

**Assinatura** (`809-818`):
```python
validar(dados, fronteiras, energia, *, n, min_s, max_s, tolerancia) -> (clipes, problemas)
```

**Campos.**
- `_CAMPOS_OBRIGATORIOS` (`76-83`); `_CAMPOS_COMUNS` (`86`); v2 = comuns + `segmentos` (`91`); `MAX_SEGMENTOS = 3` (`94`).
- Opcionais `descricao` ≤200, `conclusao` ≤90 e `capa_ts` (`108-110`), conferidos em `_conferir_opcionais` (`728-767`), nas duas formas.
- **`gancho_sugerido`:**
  - só é conferido como "texto não vazio" (`916-920`); não há limite de tamanho nem `MAX_GANCHO` (os "90" do arquivo são `MAX_CLIPE_S` e `MAX_CONCLUSAO_CHARS`);
  - no `ESQUEMA_JSON` é só `{"type":"string"}` (`172`), sem `maxLength`.

**Junta todos os problemas** (`24-28`, `819-824`).
- Os campos de texto (título, motivo, gancho, score, `905-933`) são conferidos **antes** do ramo de forma, *"para o pedido de conserto sair completo"*.
- O ramo `if v2:` (`935-1015`) tem `continue` precoces: forma (`937-939`), encaixe (`948-950`), opcionais (`952-954`), campos None (`955-956`).

**De problema a pedido de conserto.**
- `_preparar` (`1863-1878`) chama `_erro_de_validacao` (`1442-1465`), que grava `prompt_conserto.txt` (`_NOME_PROMPT_CONSERTO`, `118`) via `prompt_selecao.montar_conserto`.
  - Esse texto lista os problemas numerados, cita a resposta anterior e diz *"Corrija APENAS o que está listado"*.
  - O lembrete fixo (`prompt_selecao.py:260-265`) não fala do gancho.
- A sugestão do erro: colar o arquivo no MESMO chat, salvar a nova resposta por cima e repetir com `--resposta` (`1456-1460`).

**Laço do `--api`** (`_selecao_via_api`, `1641-1676`).
- Uma ida à API, depois `validar`. Havendo problema, faz **1 rodada de conserto** na mesma conversa, com `[user prompt, assistant texto, user conserto]` (`1668-1673`), e valida de novo.
- Se ainda houver problema, `_preparar` levanta o erro e grava `prompt_conserto.txt` com a 2ª resposta, que segue pelo modo manual.
- Transporte (`_enviar`):
  - 3 tentativas (`125`, `1557`), só para 429, 5xx e falha de conexão;
  - espera de `2**t + U(0,1)` s entre tentativas (`1623-1630`);
  - 401, 403, 404 e os demais 4xx não repetem (`1567-1609`).
- Usa structured outputs com `ESQUEMA_JSON` (`1563-1565`).

**Modo manual.**
- Sem fonte de resposta, grava o prompt e devolve `pendente` (`1834-1855`).
- `--resposta` é lido em `1400-1439`.
- O digest do conteúdo (`1391-1398`) faz o mesmo arquivo com conteúdo novo revalidar sem `--force` (`1815-1823`).
- No painel, `POST /jobs/{id}/prompt-resposta` grava `resposta.json` e chama `selecionar` (`server.py:204-263`). O erro volta como 422 com `problemas` item a item (`server.py:244-245`, `464-484`).

**Onde o teto entraria.**
- **(a)** Junto da conferência do gancho (`916-920`), condicionado a `v2` (calculado em `875`). Sai na mesma rodada mesmo quando os segmentos falham, o que é coerente com "junta todos".
- **(b)** Dentro do ramo `if v2:`, depois dos opcionais (`951-956`). Some quando forma, encaixe ou opcionais falham.
- Em qualquer dos dois:
  - `validar` precisa de um parâmetro novo **opcional**: além de 1658, 1675 e 1864 há 18 chamadas diretas nas provas (ex. `prova_f6.py:784, 899, 942, 1617, 1865`; `prova_f61.py:328-344`);
  - a mensagem tem de dar ao LLM algo que ele consiga agir (ele não mede pixel);
  - o `ESQUEMA_JSON` não tem como expressar linhas.

---

## 3. A seleção conhece o modelo? Não

- **CLI.**
  - `select` tem como parents `[entrada, geral, ingestao, transcricao, selecao]` (`cli.py:341-351`). **Não tem `--preset`.**
  - `--preset` só existe em `_pai_render` (`cli.py:261-290`), usado por `run` (`322`) e `render`.
  - `Opcoes.de_args` usa `preset=getattr(args,"preset",PRESET_PADRAO)` (`motor.py:128`). Logo, num `clipper select`, `opcoes.preset` é **sempre `"cortes"`** (`motor.py:35`), em silêncio.
- **Motor.**
  - O lambda da seleção (`motor.py:277-298`) passa `estrategia, n, modelo, forcar, resposta_manual, usar_api`, **sem preset**. Só o render recebe preset (`299-311`).
  - `selecionar` (`1694-1704`), `_preparar` (`1740-1750`), `_selecao_via_api` (`1641-1648`) e `validar` não têm preset.
  - `select.py` não importa `composicao`, `modelo` nem Pillow (`35-57`).
  - A assinatura do select (`1796-1802`) é `estrategia, n, min_s, max_s, transcrição`, **sem preset**. Hoje um `run --preset X` depois de uma seleção pronta reaproveita sem revalidar (`1812-1830`).
- **Painel.**
  - O job nasce com o preset do formulário (`server.py:116,130,157`) e o guarda em `job.opcoes` (`jobs.py:533-546`).
  - O `run` passa pelo mesmo `motor.montar_estagios` (`jobs.py:407`), então o preset não chega ao select.
  - A rota de resposta manual chama `select.selecionar` direto (`server.py:236-243`) e também não passa o preset.
- **Seleção sob um modelo, render sob outro.** O re-render do painel troca de preset sem selecionar de novo (`server.py:278`), e o `clipper render --preset X` lê o `selecao.json` existente.
- **Carregamento do modelo.**
  - O render carrega preset só por nome em `DIR_PRESETS` (`render.py:166-206`, `283-290`).
  - `modelo.carregar()` (`modelo.py:244-249`) aceita caminho, mas **nada do pipeline usa `Modelo`**; só as provas.
- **Precedente.** A restrição dependente de modelo da Q4 foi posta no **render** (`_recusar_v2_sem_composicao`, `render.py:2245-2284`, que varre os presets em `2266-2272`), justamente porque a seleção não conhece o preset.
- **Importações.** `render` importa `select` no topo (`render.py:88`), então `select` não pode importar `render`. Já `select` importar `composicao` ou `modelo` não cria ciclo (`composicao.py:44-55`, `modelo.py:47`).

**Opções que o código permite:**

- **O1 — o modelo do pedido.**
  - Passar o preset em `motor.py:288-297` e `server.py:236-243`, e daí por `selecionar`, `_preparar`, `_selecao_via_api` e `validar`.
  - Dar `--preset` ao `select`, separado de `_pai_render` (que traz `--clipe` e `--pitch` junto).
  - Incluir `"select"` em `_flags_repetidas` (`cli.py:592-595`); sem isso, o PRÓXIMO PASSO volta sem a flag e valida contra `cortes`.
  - Pôr a identidade do modelo/teto na assinatura (`1796-1802`).
  - Limite: o render posterior pode usar outro modelo.
- **O2 — todos os modelos compostos com `gancho.ativo`** (fábrica + usuário).
  - Exige ≤4 linhas em todos, no pior caso; vale para qualquer render futuro.
  - Custa N medições por gancho. Um modelo de usuário com caixa estreita recusa tudo, e a assinatura teria de cobrir o conjunto.
- **O3 — sempre o modelo padrão** (`PRESET_PADRAO`). Simples, mas ignora o modelo de verdade.
- **O4 — proxy sem fonte.** Caracteres ou largura estimada por fator, como a E-C4 (`prova_f6.py:1410-1430`) ou `_FATOR_LIBASS` (`legendas.py:150-153`). É estrutural e igual em qualquer máquina, mas não são "4 linhas medidas".

**Onde mora o número 4** (pode combinar com qualquer opção acima):
- Constante de contrato em `select.py`, como `MAX_SEGMENTOS` (`94`), passada ao prompt como `max_seg`.
- **Ou** uma chave nova em `composicao.gancho` no modelo: `modelo.py:93`, dataclass em `composicao.py:198-202`, leitura em `382-389`.

**Leitura do executor (a escolha é do arquiteto):** O1 com a medição extraída para uma função de medidor injetável. A prova estrutural da regra usaria medidor sintético, como na E-L4, e a contagem real ficaria numa prova física no Windows.

---

## 4. O prompt

**`prompt_selecao.montar`** (`55-240`).
- Promessas sobre o gancho:
  - queimado na tela nos primeiros 3 s, como PROMESSA VERIFICÁVEL (`95-100`);
  - `"gancho_sugerido": "promessa verificável para os 3 primeiros segundos (até 90 caracteres)"` (`172`);
  - exemplo v2 com `"..."` (`190`);
  - conferência final (`234-236`).
- O **"90" e o "3 segundos" são literais no texto**. `montar` recebe só `max_seg, max_desc, max_concl` (`64-66`).
- O 90 do gancho **não é validado**, por decisão da D5 Q10 (`RULINGS.md:754-757`): *"Validador NÃO ganha limite… o prompt segue prometendo 90 e o render tem de cumprir"*.
- `montar_conserto` (`243-266`) não menciona o gancho.

**`docs/lote-clip-f6/prompt-v2.txt`.**
- Por diff, é a saída atual de `montar()`; só diferem os placeholders (título, estratégia, blocos).
- Foi aprovado como texto na D5 (`RULINGS.md:722-724`, `791-794`). O gancho aparece em `18-22`, `95`, `113`, `156`.

**E-P4** (`prova_f6.py:1195-1229`) **não congela o texto.**
- Confere substrings: "PROMESSA VERIFICÁVEL", "PAYOFF", "FECHAR nele", "segmentos", "GORDURA", "PRESERVE O SENTIDO", "ordem crescente", "é rejeitado", "capa_ts", "descricao", "conclusao".
- Confere também que os limites vêm do validador ("entre 20 e 90 segundos", "no máximo 3 trechos", "até 200 caracteres") e que não há CR.
- Não confere os "90 caracteres" do gancho. Nenhum `.py` referencia `prompt-v2.txt`.
- Mudar o prompt não quebra prova, mas se afasta do texto aprovado.

**Compatibilidade com o teto.**
- PT caixa alta de 90 caracteres dá **exatamente 4 linhas** no `cortes` no Windows (`relatorio-p5.md:88`).
- Um texto de ≤90 caracteres com letras largas passa de 4 (até 9 no Windows).
- A F-I1 (`prova_f6.py:1943-1985`) seleciona um v2 com esse PT-90 e espera aceite. Com teto 4 ela fica **no limite**, e o resultado depende da fonte.

---

## 5. O que "v1 congelado" exige

**Como o validador distingue as formas.**
- `e_v2(item)` = `isinstance(item, dict) and item.get("segmentos") is not None` (`select.py:464-466`). É **por item**, não por resposta.
- Não há marcador de versão em lugar nenhum: nem na resposta, nem no `ESQUEMA_JSON`, nem no `selecao.json`.
- As duas formas são exclusivas no mesmo item (`872-886`).
- O render usa a mesma `e_v2` (`render.py:827-831`).

**O que está congelado.**
- Nos RULINGS:
  - §6, *"Contrato v1 do JSON (byte a byte)"* (`RULINGS.md:266-269`);
  - D5 Q10 (`754-757`);
  - §14.2 *"a regra é só do v2"* (`872`);
  - §20.1 (`1083-1084`).
- No código:
  - `_CAMPOS_OBRIGATORIOS` (`76-83`);
  - o ramo v1 (`1017-1140`);
  - o conserto automático de sobreposição só entre v1 e v1 (`1150-1158`);
  - `_para_esquema` sem `segmentos` e sem `span_*` no v1 (`1903-1921`).
- Provas:
  - E-V4 (`894-906`);
  - E-V5 (`940-943`);
  - **E-X1** (`1800-1830`, estrutural): a resposta v1 real, byte a byte, pelo `clipper select`, com 5/5 aprovados e "os 5 seguem v1".

**Precedente de leitura.** A P3 já fez os opcionais valerem no v1 (`1083-1093`). "Congelado" vem sendo lido como: o que era aceito continua aceito, e o v1 não ganha chave nova nem campo obrigatório.

**Para o S2, isso exige:**
- nenhum v1 aceito hoje passa a ser recusado por linhas do gancho;
- nenhum campo obrigatório novo;
- nenhuma chave nova no clipe v1 do `selecao.json`;
- o ramo v1 não passa a depender de Pillow nem de fonte.

Os 5 ganchos reais (v1) medem ≤3 linhas tanto no Windows quanto aqui. Por isso a E-X1 só morderia uma violação da regra, nunca um estouro acidental do número.

---

## ⚠ Colisões destacadas

1. **A frase "o teto é parâmetro de modelo" é do S1, não do S2.** Ela aparece na D5 P05 e no §13.2 (`RULINGS.md:759-760`, `797-799`) e se refere ao teto dos blocos de 1 palavra da legenda. O §14.2 (`868-872`) fixa "4 linhas" para o gancho e não diz se esse número é parâmetro de modelo. **Isso volta como pergunta.**
2. **"Só do v2" não alcança a maioria dos clipes.** O prompt v2 manda o clipe de UM trecho usar `inicio`/`fim` (`prompt_selecao.py:163-177`) e diz *"Na dúvida, use um trecho só"* (`148`). Pela `e_v2`, esse clipe é v1. Um teto aplicado via `e_v2` valeria só para clipes com `segmentos`.
3. **A contagem de linhas depende da fonte instalada.** Isso vale mesmo com o "4" fixo. Uma prova estrutural não consegue medir a fronteira (4 contra 5 linhas). A seleção pode dar resultados diferentes no Windows e no Linux, e a assinatura não registra o ambiente.
4. **Seleção e render podem usar modelos diferentes** (`server.py:278`; `render --preset`). O teto só garante o modelo usado na seleção.
5. **Chave nova no dataclass `Composicao` muda a `impressao`.** A `impressao` é calculada com `asdict` (`composicao.py:282`), então todo clipe composto seria re-encodado uma vez (`render.py:1373`, `2442`) **sem a VERSAO subir**. É o mesmo efeito que o CLAUDE.md §6 quer evitar, por outro caminho. Para o S1 vale o mesmo: `impressao_legenda` também usa `asdict` (`render.py:1345-1348`).
6. **O prompt promete até 90 caracteres, e o teto de 4 linhas pode recusar um gancho dentro disso.** Mexer no texto mexe no prompt aprovado na D5, então exige decisão do arquiteto.
7. **O caso extremo do §11.1 está incompleto.**
   - `cortes` com 4 linhas: base em y=412, 216 px (Windows, `relatorio-p5.md:88`).
   - `cortes-editorial` com 4 linhas: **não foi medido no Windows**. O número daqui (184 px, DejaVu) não vale para lá; fica pendente de prova física.
8. **Referências de linha velhas em comentários.** `prova_f6.py:1413` cita `composicao.py:892`, e `composicao.py:395` e o `RULINGS.md` §11.1 citam `:902`. A fórmula hoje está em `composicao.py:954-956`.

### preset-resolucao
# Recon F8a: como um preset/modelo é escolhido e carregado (CLI e painel)

Base: HEAD `ecd79b4` no branch `claude/charming-euler-02p9cf`. Nenhum arquivo do repositório foi alterado (`git status` limpo). Rodei apenas Python de leitura (`PYTHONDONTWRITEBYTECODE=1`) e uma simulação em `/tmp/claude-0/-home-user-ClipPro/a6c45088-77bb-59ae-9bce-89eebcd589cd/scratchpad/sim/sim_atalho.py`. O comportamento no Windows está marcado como inferência quando não foi testado.

## 0. Colisões (plano x código)

**C1. O render não usa `clipper/modelo.py`.**
- A docstring diz "O render passa a receber UM objeto" (`modelo.py:10-11`), mas não é o que acontece.
- O `render.py:73` importa só `composicao, ffmpeg_utils, legendas`. A carga é feita por `carregar_preset(preset)` e `carregar_composicao(preset)` (`render.py:2417-2418`), e cada um relê o JSON via `_ler_preset`.
- `modelo.carregar()` (`modelo.py:244-249`) não tem nenhum chamador no repositório. `Modelo` só aparece em `provas/prova_f6.py`.
- Por isso **`--preset caminho.json` não funciona hoje de ponta a ponta**, ao contrário do que sugere `recon-f8a.md:20-22` ("ler um JSON qualquer do disco já funciona por dentro"). Testado: `render._ler_preset(".../clipper/presets/cortes.json")` dá `ErroRender` "não existe o preset de legenda ...".
- Ponto a favor: medi `Modelo.de_fabrica(n).legenda == render.carregar_preset(n)` e `.composicao == render.carregar_composicao(n)`, e deu True nos 4 de fábrica. As impressões também são idênticas (cortes: `af47dd00e646a23a` / `6eff370c49b2277c`). Portanto, trocar o render para usar `Modelo` não muda pixel, cache nem `VERSAO` dos modelos de fábrica.

**C2. Editar só a legenda de um preset não refaz os clipes.**
- A assinatura do estágio (`render.py:2436-2447`) guarda `preset`, `estilo` (impressão da composição), `pitch`, seleção, transcrição e energia. A impressão da legenda não entra.
- Com o estado concluído, `_arquivos_no_lugar` (`render.py:2450-2463`) devolve `reaproveitado` antes da conferência por clipe `_mesmo_estilo` (`render.py:1373-1377`).
- Simulado para `cortes` e `bold-amarelo`: trocar `cor_falada` leva a `reaproveitado: True`, e `_renderizar_clipe` não é chamado.
- Isso contradiz `README.md:152-153` ("Editar um preset **refaz** os clipes") e a docstring de `impressao_legenda` (`render.py:1335-1342`).
- O defeito já existia e não está registrado no RULINGS. No F8a ele vira central, porque o modelo do usuário existe justamente para ser editado.

**C3. Somar campo a um dataclass já invalida o cache, sem mexer em `VERSAO`.**
- `Composicao.impressao()` = sha256 de `{"versao", **asdict(self)}` (`composicao.py:282`).
- `impressao_legenda()` = sha256 de `asdict(Preset)` (`render.py:1346-1349`).
- Qualquer campo novo, mesmo com valor padrão, muda o hash de todos os modelos:
  - **Campo em `Composicao`:** o `estilo` da assinatura muda, o atalho falha e todos os clipes compostos reencodam.
  - **Campo em `legendas.Preset`** (onde o S1 tende a cair): a assinatura não muda (C2) e o atalho continua pulando. Mas sempre que o laço por clipe roda (`--force`, arquivo faltando), todos reencodam.
- A regra do CLAUDE.md §6 sobre `VERSAO` não cobre isso, porque as impressões usam o `asdict` inteiro. Precisa de decisão.

**C4. O nome do modelo vira identidade de três jeitos diferentes.**
- `Composicao.nome` recebe a string crua do `--preset`, sem `strip` (`render.py:290`), e entra no `asdict`, logo na impressão. O mesmo arquivo `cortes` deu quatro impressões diferentes:

  | Grafia passada em `--preset` | Impressão |
  |---|---|
  | `"cortes"` | `af47…` |
  | `"../../clipper/presets/cortes"` | `6afd…` |
  | caminho absoluto | `7cb2…` |
  | `" cortes "` | `2d99…` |

- `Preset.nome` (da legenda) é o `"nome"` **interno** do JSON, por `dados.setdefault("nome", nome)` (`render.py:205`). Uma cópia de `cortes.json` continua dizendo `"nome": "cortes"`.
- `Modelo.de_arquivo` faz o contrário: o nome é o stem do arquivo e sobrescreve o interno (`modelo.py:194`).

**C5. `.gitignore`: a regra `models/` derruba a exceção das fixtures.**
- `models/` (linha 29) não é ancorado e vem **depois** de `!provas/fixtures/**` (linha 22), então ignora `provas/fixtures/**/models/`.
- Confirmado com `git check-ignore -v`: `.gitignore:29:models/  provas/fixtures/models/x`.
- O comentário das linhas 16-21 afirma que a exceção protege contra `models/`, e isso é falso. (Para `out/` e `_teste/` a proteção funciona.)

**C6. "modelo" já tem quatro significados no código.**
- `--modelo` é o modelo da API (`cli.py:199`, `motor.py:36` `MODELO_PADRAO="haiku"`, `select.py:1700`).
- `--modelo-whisper` (`cli.py:151`).
- `DIR_MODELOS = RAIZ / "models"` guarda o `.tflite` de detecção de rosto (`render.py:125`).
- `Modelo` é o estilo de edição.
- Uma pasta `modelos/` ao lado de `models/` vai confundir, e uma flag ou subcomando chamado "modelo" colide com `--modelo`.

## 1. `clipper/cli.py`

**Definição de `--preset`** (`cli.py:261-270`): `default=PRESET_PADRAO`, `metavar="NOME"`, `help=_ajuda_preset()`.
- Não tem `choices`, nem `type`, nem `strip`, nem validação.
- Só existe em `run` (`cli.py:316`) e `render` (`cli.py:354`).

**Ajuda que lista os presets reais:**
- `_presets_disponiveis()` (`cli.py:231-243`) faz `sorted(p.stem for p in config.DIR_PRESETS.glob("*.json"))`, com `OSError` virando lista vazia.
- `_ajuda_preset()` (`cli.py:246-258`) monta o texto. Só enxerga `clipper/presets/`.
- **Risco ao incluir modelos do usuário:** o argparse formata a ajuda com `%`. Testei: as strings `"meu-50%"`, `"50% b"` e `"x%y"` dão `ValueError` ao formatar a ajuda, o que derrubaria `clipper --help` e o `print_help` de `cli.py:818-819`.
  - `%` é válido em nome de arquivo no Windows.
  - A `descricao` de `cortes.json` contém "75%".
  - O `--pitch` já escapa com `%%` (`cli.py:285`).
- O epílogo cita só nomes de fábrica (`cli.py:43`, `48-51`, `62-66`).

**Onde o nome é validado ou recusado:** em nenhum ponto do CLI.
- `Opcoes.de_args` copia a string (`motor.py:128`).
- A única recusa é `render._ler_preset` (seção 3), já dentro do estágio de render.
- No `run`, isso só acontece depois de ingestão, transcrição e seleção (`motor.py:58`).
- No modo manual, o `run` para em `selecao` com o status "aguardando" (`motor.py:363-364`). Assim um preset inválido passa despercebido até a volta com `--resposta`.

**`_flags_repetidas`** (`cli.py:559-607`): repete `--preset "{opcoes.preset}"`, com aspas, só em `run`/`render` e só quando a string é `!= PRESET_PADRAO` (`cli.py:594-595`). A comparação é por string, então um preset inválido também é repetido.

**Mensagens que repetem `--preset`:**
- `_comando_para_continuar` (`cli.py:610-630`, chama na linha 629).
- `_sufixo_render` (`cli.py:1085-1092`), usado em `_conferir_pasta_do_render` (`cli.py:1123`, sugestão na linha 1128) e em `_origem_pelo_disco(..., flags=...)` (`cli.py:1173`, mensagem na linha 1057).
- Um caminho relativo repetido nessas sugestões só vale no mesmo diretório de trabalho (cwd).

## 2. `config.py`, `motor.py`, `modelo.py`

**`config.py`**
- `RAIZ` (linha 17) é a raiz do repositório.
- `DIR_PRESETS = Path(__file__).resolve().parent / "presets"` (linha 18) fica dentro do pacote.
- `DIR_SAIDA_PADRAO = RAIZ / "out"` (linha 19) é o padrão natural a seguir para `RAIZ / "<pasta de modelos>"`.
- **Não existe nenhuma constante para modelos do usuário.**
- `slugificar(texto, limite=60)` (linhas 26-35): normaliza para ASCII, põe em minúsculas, troca `[^a-z0-9]+` por `-`, trunca e cai em `"video"` quando o resultado fica vazio.
- `Saida` (linhas 38-116) não tem nada de preset.
- `escrever_json` (linhas 209-216) não passa `newline="\n"`, o que diverge do CLAUDE.md §5. Não deve ser usado para gravar modelo.

**`motor.py`**
- `PRESET_PADRAO = "cortes"` (linha 35), duplicado em `render.py:108`.
- `Opcoes.preset: str` (linha 105).
- `rotulo_render` imprime `preset {opcoes.preset}` cru (linhas 191-201).
- `montar_estagios` passa `preset=opcoes.preset` como string para `render.renderizar` (linhas 299-312).
- A seleção **não recebe o preset** (linhas 288-297; `select.py:1694-1704`). Isso pesa no S2: o teto de linhas do gancho medido na seleção não conhece a fonte nem a caixa do modelo, e um `render --preset X` posterior pode trocar o modelo.

**`modelo.py`**

`de_dict` (linhas 175-188):
- Nome: argumento, depois `"nome"` interno, depois `"sem-nome"`.
- Levanta `TypeError` se o JSON não for um objeto.
- Monta a legenda com `Preset.de_dict({**dados, "nome": nome})` e a composição com `de_preset(dados, nome)`.
- Guarda `fonte_json` normalizado (chaves ordenadas) e `_avisos`.

`de_arquivo` (linhas 190-194): lê em UTF-8 e usa `nome = caminho.stem`. As exceções saem cruas (`FileNotFoundError`, `JSONDecodeError`, `TypeError`).

`de_fabrica` (linhas 196-201): `DIR_PRESETS / f"{nome}.json"`, sem sanear o nome.

`para_json` (linhas 205-207): devolve a forma normalizada, com chaves em ordem alfabética.

`gravar` (linhas 209-218):
- Grava em UTF-8 com `newline="\n"` e `\n` final, como pede o §5.
- Cria a pasta pai.
- **Sobrescreve sem perguntar.**
- Grava as chaves **reordenadas**: uma duplicata de `cortes` começa por `arquivo_fonte, composicao, contorno…`, enquanto o arquivo de fábrica começa por `nome, descricao, fonte…`.

`avisos()` (linhas 220-222): não é exibido em lugar nenhum fora de `prova_f6.py:261-267`.

`carregar(nome_ou_caminho)` (linhas 244-249), testado:
- `"cortes.json"` (sem arquivo no cwd) dá `FileNotFoundError` cru em `.../presets/cortes.json.json`.
- `"/tmp/nao-existe.json"` cai em `de_fabrica` e procura `/tmp/nao-existe.json.json`.
- `"modelos/meu"` procura em `.../presets/modelos/meu.json`.
- `"../../clipper/presets/cortes"` **carrega** (path traversal).
- Caminho relativo é resolvido contra o **cwd**, não contra `RAIZ`.
- Não procura na pasta do usuário, não trata nome repetido entre fábrica e usuário, não faz `strip`.

**Diferenças em relação ao loader do render:**
- O `modelo.py` não tem a mensagem amigável de campo faltando (`render.py:212-236`).
- Também não tem `_conferir_cores` (`render.py:254-280`).

## 3. `clipper/pipeline/render.py`

**Carga do preset**
- `renderizar` (linhas 2401-2418) chama `carregar_preset` (209-239) e `carregar_composicao` (283-290), cada um passando por `_ler_preset` (166-206).
- `_ler_preset` faz `strip` (linha 172), monta `arquivo = DIR_PRESETS / f"{nome}.json"` (linha 173) e devolve `setdefault("nome", nome)` (linha 205).
- `carregar_composicao` repassa o `nome` **sem strip** (linha 290).

**Recusa** (linhas 175-184):
- Lista só os presets de fábrica.
- Sugere `existentes[0]` (= `bold-amarelo`), não o padrão.
- Diz "(os arquivos ficam em DIR_PRESETS)".
- Para caminho: `modelos/meu.json` e caminho absoluto `.json` são recusados (testado). Caminho absoluto **sem** `.json`, ou com `../`, carrega. No Windows, `"C:\x\meu"` carregaria `C:\x\meu.json` (inferência pela semântica do pathlib).

**Nome do arquivo do clipe**
- `_nome_arquivo` (linhas 955-961) monta `NN-{slug(titulo,48)}--{slug(preset,32)}.mp4`. Medido:
  - `modelos/meu.json` vira `modelos-meu-json`.
  - `C:\x\meu.json` vira `c-x-meu-json`.
  - Um caminho absoluto longo vira `home-user-clippro-clipper-preset`: **o nome do modelo some** no truncamento de 32 caracteres.
  - `"Meu Modelo"`, `"meu_modelo"` e `"meu-modelo"` viram todos `meu-modelo`.
  - Nomes longos colidem depois do truncamento.
  - Nome só com caracteres não-ASCII vira `video`.
  - Um modelo do usuário chamado `cortes` gera o mesmo nome de arquivo do de fábrica.
- No Windows, `--preset Cortes` funciona hoje (NTFS não diferencia maiúsculas; inferência): gera o slug `cortes`, mas a chave `"Cortes"`.

**Arquivo `.ass`** (`render.py:1668`): `legenda_{id}_{preset_nome}.ass` usa o nome **cru**, sem slug.
- Um caminho vira subpastas dentro de `_trabalho/`. Testado no Linux: `legenda_1_../../clipper/presets/cortes.ass`.
- No Windows, `C:\…` gera o componente `legenda_1_C:`, que é inválido (inferência).
- `opcao_subtitles` põe `arquivo_ass.name` **sem escape** dentro de `'…'` (`ffmpeg_utils.py:270-273`). Um apóstrofo no nome do modelo (válido no Windows) quebra o filtro.
- A garantia "sem dois-pontos, sem espaço" da docstring (`ffmpeg_utils.py:263-266`) só vale para os nomes de fábrica.

**`metadados.json`**
- `"preset"` de cada clipe (linha 1303).
- `legenda.preset` (linha 1934) e `estilo.preset` (linha 1734) recebem a string crua.
- `presets_usados` aparece nas linhas 1972 e 2602.
- Em `.estado.json`: assinatura `"preset"` (linha 2437) e `extra.preset` (linha 2644).
- Com caminho absoluto, os metadados ficam presos à máquina, e mover a pasta muda a identidade.

**Comparações por string exata**
- `_arquivos_no_lugar` faz `c.get("preset") == preset` (linha 2305).
- `_mesclar_clipes` usa a chave `(id, preset)` (linhas 2041-2045) e ordena por ela (linha 2048).
- `por_chave` é montado nas linhas 2535-2539 e consultado na linha 2575.
- Consequência: o mesmo arquivo por duas grafias não é reaproveitado. Se o slug difere, sai um mp4 duplicado. Se o slug é igual (`" cortes "` x `cortes`), o mp4 é sobrescrito e ficam duas entradas apontando para ele, o que faz um reencode alternado a cada rodada.

**`relatorio.md`**: linhas 2116-2119, 2129-2140, 2147-2149 e 2185-2189. O preset aparece entre crases; um caminho só piora a leitura.

**Mensagens que citam preset**
- Linhas 190-195, 199-203 e 228-236. Esta última manda copiar o arquivo para **dentro do pacote**.
- Linhas 1499-1502 sugerem `clean-branco` fixo; linhas 1703-1707 sugerem `bold-amarelo` fixo.
- Linhas 2266-2284: `_recusar_v2_sem_composicao` sugere só modelos de fábrica com composição.
- Linhas 2453-2456, 2496-2502 e log 1676-1680 citam o preset cru.
- Linha 2613: `--preset {preset}` **sem aspas**, o que quebra com espaço.

**Cache e identidade**: ver C2, C3 e C4. `_mesmo_estilo` está nas linhas 1352-1384.

## 4. Painel: pontos que assumem "preset = nome de arquivo em `clipper/presets/`"

1. **`/api/padroes`** (`server.py:88-98`): `"presets": sorted(p.stem for p in config.DIR_PRESETS.glob("*.json"))` (linha 95), **sem a guarda de `OSError`** que o CLI e o render têm. É a terceira cópia dessa listagem.
2. **`app.js:80-85`** preenche o `<select id="preset">` (`index.html:48-49`) com `value` e rótulo iguais ao stem e marca como selecionado o `padroes.preset`. Não há grupos fábrica/usuário. Um nome repetido entre fábrica e usuário geraria `value` ambíguo. `escapar()` não escapa aspas (`app.js:169-173`; comentário em `app.js:307-310`).
3. **`app.js:131`** envia o valor escolhido. **`app.js:161`** mostra `j.opcoes.preset` cru na lista. **`app.js:298-307`**: o botão de re-render manda só `clip_n` e `forcar`, então não há interface para re-renderizar com outro modelo.
4. **`POST /jobs`** (`server.py:110-162`): lê `preset` do formulário ou do JSON (linhas 116 e 130) e faz `Opcoes(preset=str(preset or PADRAO))` (linha 157) **sem validar**. O valor é persistido em `job.json` via `enfileirar` e `opcoes_para_json` (`jobs.py:333`, `537`) e só falha no render.
5. **Re-render** (`server.py:266-292`): `preset=str(corpo.get("preset") or base.preset)` (linha 278), sem validar. O valor é gravado em `job.json` **antes** de rodar (linhas 282-283).
6. **`_detalhar`** (`server.py:174-176`) e **`_mp4_do_clipe`** (`server.py:445-446`) filtram os clipes pelo preset do job.
7. **`_clipes_do_disco`** (`jobs.py:619-653`) filtra por igualdade exata (linha 630). O fallback `do_preset or clipes` (linha 631) mostra os clipes de todos os presets quando nada bate, e aí `_mp4_do_clipe` pode servir o mp4 de outro preset com o mesmo id.
8. **`_preset_mais_recente`** (`jobs.py:105-124`) e **`_job_deduzido`** (`jobs.py:155`, `172`): para pastas feitas no terminal, o preset do job é a string gravada no metadados, que pode ser um caminho.
9. **`opcoes_para_json` / `opcoes_de_json`** (`jobs.py:533-546` / `549-566`) fazem a ida e volta da string pura. Também são usados por `resposta_manual` (`server.py:228`), `_retomar_interrompidos` (`server.py:679`) e na conclusão do job (`jobs.py:491`).
   - Modelo do usuário renomeado ou apagado faz a retomada falhar no render.
   - Caminho relativo depende do cwd onde se rodou `clipper ui`.
10. **Segurança:** o painel escuta só em 127.0.0.1, mas não tem autenticação. Qualquer string chega a `_ler_preset`, e hoje `../../x` já lê qualquer `.json` do disco (testado com caminho análogo no Linux). Aceitar caminhos no painel alargaria isso.
   - **Recomendação:** o painel aceita só nomes do catálogo (fábrica + usuário) e o CLI aceita caminho. A resolução nome→arquivo fica em `clipper/`, uma vez só (`motor.py:3-5`, CLAUDE.md §7).

## 5. `.gitignore`

Ordem atual:
- 2-6: ambiente (`.venv/`, `__pycache__/`, …)
- 9: `out/`
- 10: `_teste/`
- 14: `resposta*.json` (não ancorado)
- 22: `!provas/fixtures/**`
- 25: `.env`
- 26: `*.key`
- 29: `models/` (não ancorado, ver C5)

`.gitattributes` só trata `provas/fixtures/** -text`.

Resultados de `git check-ignore`:
- `modelos/meu.json` **não** está ignorado hoje.
- `provas/fixtures/.env` e `provas/fixtures/x.key` continuam ignorados, como afirma o CLAUDE.md §4.
- `provas/fixtures/a.env` **não** está ignorado: `.env` casa só o nome exato.

Onde entraria a pasta de modelos do usuário:
- **Usar padrão ancorado, `/modelos/`.** Assim ele não pode casar com `provas/fixtures/**/modelos/`, qualquer que seja a posição no arquivo.
- Uma regra `modelos/` não ancorada, colocada depois da linha 22, repetiria o defeito de `models/` e engoliria em silêncio uma futura fixture de modelo do usuário.
- Se o arquiteto quiser um `LEIAME` ou `.gitkeep` versionado dentro da pasta, é preciso usar `/modelos/*` com `!/modelos/LEIAME.md`, porque o git não reinclui arquivo de pasta excluída. A alternativa é criar a pasta sob demanda, como já se faz com `models/` (`render.py:308`).

## 6. Outros usos de `DIR_PRESETS`, glob de presets e nomes fixos

**Código:**
- `config.py:18`
- `cli.py:240`, `252`
- `render.py:75` (import), `161`, `173`, `183`, `194`, `202`, `233`
- `modelo.py:201`
- `server.py:95`

**Docstrings:** `legendas.py:37`, `render.py:210`, `modelo.py:15`, `198`.

**Provas:**
- `prova_f6.py:254` monta o caminho literal `RAIZ/"clipper"/"presets"/"cortes.json"`.
- `prova_f6.py:132-133` fixa os nomes em `MODELOS_COMPOSTOS` e `TODOS_OS_MODELOS`.
- `entrada_real.py:381-382` faz o glob `*--{preset}.mp4` com o preset **cru**, sem slug. Só funciona quando nome e slug coincidem.
- `ui/provas/casos.py:57`, `62`, `277`, `403` e `prova_f61.py:267` usam `"cortes"`.
- **Nenhuma prova cobre preset inválido nem `/api/padroes`.**

**Documentação:**
- `README.md:151-153` manda copiar o preset para dentro de `clipper/presets/` (vai contra a "pasta própria fora do pacote" do F8a) e faz a promessa desmentida em C2.
- CLAUDE.md, linhas 103-104 e 133.

**Decisões que ficam para o arquiteto:**
1. A identidade canônica de um modelo do usuário (stem, `"nome"` interno ou caminho) e se o `--preset` é normalizado antes de entrar em `Opcoes`, `job.json` e metadados.
2. O que fazer quando um modelo do usuário tem o mesmo nome de um de fábrica: o do usuário sobrepõe, o nome é recusado, ou vai para um prefixo próprio.
3. Se o painel aceita caminho de arquivo ou só nomes do catálogo.
4. O nome da pasta, por causa da colisão com `models/` (C6).
5. Se o C2 entra no F8a.
6. Como tratar a invalidação de cache do C3 quando o S1 somar campo ao dataclass.

### provas-convencoes
# Harness de provas para o F8a: estrutura, regressão, físicas e convenções

Respondo às 5 perguntas e trago o placar das estruturais. Também encontrei 8 colisões entre o plano do F8a e o código atual. Não editei nada no repositório: `git status` continua limpo. As saídas que as provas gravam ficam em `_teste/`, que o `.gitignore:10` ignora. As simulações foram feitas em memória, com scripts no scratchpad.

## Placar das estruturais (HEAD `ecd79b4`, igual a `origin/claude/charming-euler-02p9cf`)

| Comando | Resultado |
|---|---|
| `python3 provas/prova_f6.py` | **32 passaram, 1 pulou, 0 falharam**, rc=0, cerca de 3,1 s. E-V5 pulou porque falta o pacote `anthropic` (`prova_f6.py:964-967`). As 11 físicas não rodaram. O resultado bate com `relatorio-f61.md:12`. |
| `python3 provas/prova_f61.py` | **8 passaram, 3 pularam, 0 falharam**, rc=0. H-1, H-2 e H-9 pularam porque falta o `fastapi`/`httpx` (`prova_f61.py:54-59`). As 2 físicas não rodaram. |

Ambiente do sandbox: Python 3.13.16 e `/usr/bin/ffmpeg` presentes. Não estão instalados `mediapipe`, `fastapi`, `anthropic` nem `faster_whisper`. O Pillow está.

## ⚠ Colisões e lacunas: decisão do arquiteto

1. **O `Modelo` não está no caminho real.**
   - Nenhum módulo de `clipper/` ou `ui/` importa `clipper.modelo`. Só as provas usam.
   - O `--preset` carrega por `carregar_preset`/`carregar_composicao` → `_ler_preset`, que lê só `DIR_PRESETS/<nome>.json` (`render.py:166-206`, `render.py:2417-2418`).
   - `modelo.carregar()` já aceita nome ou caminho (`modelo.py:244-249`), mas ninguém o chama.
   - Os dois caminhos tratam o nome de forma diferente: `_ler_preset` usa `setdefault("nome", nome)`, e o JSON vence (`render.py:205`); `Modelo.de_dict` força o nome do arquivo (`modelo.py:180-184`).
   - Consequência: E-M1..E-M4 e E-R1/E-R2 não provam o ponto de entrada `--preset`, que é o que o §13.1 exige.

2. **A E-R2 é frouxa nos presets compostos, e a E-R1 também.**
   - Nos compostos, a E-R2 só compara as linhas fora de `Dialogue` (aceitando diferença apenas no MarginV) e exige que o número de linhas não cresça (`prova_f6.py:319-338`).
   - Testei mutantes em memória contra a suíte estrutural inteira:
     - texto de um `Dialogue` trocado no `cortes`: nenhuma prova pegou;
     - cor do realce trocada dentro dos `Dialogue`: nenhuma prova pegou;
     - último `Dialogue` removido: nenhuma prova pegou.
   - Isso contraria o CLAUDE.md §4, que manda o diff de conteúdo mostrar exatamente o que a lista permite.
   - A E-R1 aceita qualquer delta em etapa cujo texto contenha `pilula` ou `gancho` (`prova_f6.py:292`). O mutante `format=auto` no overlay da pílula passou na E-R1; quem o pegou foram a E-G2 e a E-C1.

3. **Somar campo a um dataclass invalida o cache sem subir a `VERSAO`.**
   - `impressao_legenda` faz hash de `asdict(Preset)` inteiro (`render.py:1335-1349`).
   - `Composicao.impressao` faz hash de `asdict(self)` (`composicao.py:270-286`).
   - Logo, qualquer campo novo (o S1, por exemplo) muda a impressão, `_mesmo_estilo` devolve False (`render.py:1352-1383`) e todo clipe é re-encodado.
   - Nenhuma prova fixa esses hashes; a única conferência é `impressao() == ""` em `prova_f6.py:618`.

4. **O "teto fixo em 3" do S1 não é um literal no código.**
   - É `max_palavras_linha`, que vale 3 em `cortes.json:18` e em `cortes-editorial.json:18`. Ele é passado como `maximo` para `fundir_curtos` (`legendas.py:547-552`).
   - Três provas afirmam que a fusão nunca passa de `max_palavras_linha`: E-L1 (`prova_f6.py:417-419`), E-L3 (`:511-525`) e E-X2 (`:1888-1890`).
   - Se o S1 criar um teto de fusão separado e maior, essas três falham por desenho. Isso colide com o ruling Q2(B), "o teto de cada preset NÃO muda" (`RULINGS.md:77-80`).

5. **No S2, as linhas do gancho dependem da fonte.**
   - `select.validar` não recebe preset nem modelo (`select.py:809-818`).
   - As linhas da pílula vêm de `_fonte` (`composicao.py:612-668`). Sem as fontes do Windows, ela cai em DejaVu Sans e só avisa (`composicao.py:660`). É por isso que a F-G3 está entre as FÍSICAS.
   - Uma prova estrutural do S2 teria de usar um medidor sintético, como faz a E-L4 (`prova_f6.py:528-558`).

6. **Não há como isolar a pasta de presets numa prova.**
   - O render importa `DIR_PRESETS` por valor (`render.py:74-76`), enquanto `cli.py:240` e `ui/server.py:95` leem `config.DIR_PRESETS`.
   - Não existe variável de ambiente para trocar essa pasta (`config.py:18`).
   - Um monkeypatch em `config` não alcança o render, e `ER.cli` roda num subprocesso, onde nada pode ser remendado.

7. **Nomes já ocupados.**
   - `.gitignore:28-29` já ignora `models/`, onde está o `.tflite` do detector de rosto (`render.py:125-126`). A pasta de modelos do usuário não pode ser `models/`.
   - "modelo" já tem outros donos: `selecionar(modelo="haiku")` (`select.py:1700`) e `modelo_whisper` (`ui/server.py:96-97`).

8. **A F-G1 sobrescreve `_teste/clipe-curto.mp4`.** Ela chama `gerar(DESTINO_PADRAO, 40.0)` sempre (`prova_f6.py:633`).
   - É o mesmo vídeo que a `prova_f5` exige (`casos.py:34`).
   - O caminho que `casos.py:42-43` ensina é cortar esse vídeo de um vídeo real com fala, e o lavfi não tem fala (`gerar_clipe_curto.py:22-26`).
   - `resposta_fixture` lê `frases[0]` (`prova_f5.py:280-284`); sem fala, provavelmente quebra. Não verifiquei no Windows.

Menores:
- A E-M3 só confere `avisos() == []` no `cortes` (`prova_f6.py:266-268`). Conferi em memória que os 4 presets dão `[]` hoje.
- No `main` da `prova_f6`, um nome desconhecido roda tudo sem avisar (`prova_f6.py:2305`). Rodar `F-I1` sem `--fisicas` executa todas as estruturais.

## 1. Estrutura de `prova_f6.py` e `prova_f61.py`

**O que dá para reutilizar de `provas/prova_f6.py`.** O módulo só importa a biblioteca padrão no topo; os imports de `clipper` ficam dentro das funções.

| Item | Onde | O que é |
|---|---|---|
| `RAIZ`, `sys.path` | `:35-37` | raiz do repositório no path |
| `DIR_FIXTURES`, `DIR_BASELINE`, `FIXTURE_SINTETICA` | `:39`, `:135-136` | caminhos das fixtures |
| cores | `:41-48` | desligadas no Windows sem `WT_SESSION`/`ANSICON` |
| `class Falhou(AssertionError)` | `:51` | falha de prova |
| `class Pulou(Exception)` | `:55` | prova que não pode rodar aqui |
| `confere(condicao: bool, descricao: str, detalhe: str = "") -> None` | `:59-64` | imprime ok/FALHOU e levanta `Falhou` |
| `ativos_falsos(*, com_pilula=True) -> dict` | `:74-89` | ativos com caminhos falsos `/f/*.png` |
| `RECORTE_PADRAO` | `:92` | recorte fixo |
| `filtergraph(comp, *, duracao=42.0, punches=(5.0, 12.0), filtro_legenda="subtitles=clipe.ass", com_pilula=True, pitch=False) -> str` | `:95-117` | chama `C.montar`, sem ffmpeg |
| `diff_etapas(a, b) -> list[str]` | `:120-129` | diferença etapa a etapa |
| `MODELOS_COMPOSTOS`, `TODOS_OS_MODELOS` | `:132-133` | `("cortes", "cortes-editorial")` e os 4 |
| `EXCECOES` | `:141-145` | lista FECHADA |
| `palavras_sinteticas()` | `:148-151` | levanta `Pulou` se a fixture faltar |
| `ass_do_modelo(nome) -> str` | `:154-166` | `montar_ass` com `Modelo.de_fabrica(nome).legenda` sobre a fixture sintética |
| `ler_baseline(nome_arquivo) -> str` | `:169-173` | levanta `Pulou` se faltar |
| `_blocos_do_ass`, `_palavras_do_bloco` | `:374-402` | leitura dos `Dialogue` |
| `_cenario() -> (Fronteiras, energia)` | `:723-750` | frases de 6 palavras, lacuna 180–240 s |
| `_BASE_CLIPE` | `:753-758` | `gancho_sugerido="um gancho"` |
| `_clipe_v2(fr, pares)`, `_clipe_v1(fr, a, b)` | `:761-776` | clipes montados por índice de frase |
| `_p5_raiz(raiz, nome)` | `:1508-1514` | faz rmtree e recria `raiz/p5/<nome>` |
| `_p5_videos`, `_p5_transcricao`, `_p5_seg(frases, a, b)`, `_p5_rc(proc)` | `:1517-1545` | apoio do P5 |
| `_p5_validador_do_render_aceita(clipes, caminho)` | `:1548-1555` | portão do render |
| `_fixture_real(nome)` | `:1793-1797` | levanta `Pulou` se faltar |

**`prova_f61.py`.**
- Importa de `provas.prova_f6`: `Falhou`, `Pulou`, as cores, `_cenario`, `_clipe_v1`, `_clipe_v2` e `confere` (`:32-43`).
- Tem apoio próprio: `_pasta(raiz, nome)` (`:46-51`), `_exigir_fastapi()` (`:54-59`) e `_gravar_json(caminho, dados)`, que grava com `utf-8` e `newline="\n"` (`:62-64`).
- O `main` é copiado, não importado (`:560-609`).

**Como estruturais e físicas rodam.**
- Registro: `ESTRUTURAIS` e `FISICAS` são dicionários `{ID: (descrição, função(raiz))}` (`prova_f6.py:2246-2294`; `prova_f61.py:540-557`).
- `main(argv)`: `--fisicas` acrescenta as FÍSICAS; os nomes são passados para maiúsculas (`prova_f6.py:2297-2305`).
- Pasta de saída: `_teste/out-prova-f6` ou `_teste/out-prova-f61`.
- Desfecho: `Pulou` conta como "pulou"; outra exceção vira "falhou" com traceback; rc=1 só se alguma falhou (`:2315-2348`).

**E-M1..E-M4** (`:2247-2250`):
- **E-M1** (`:181-223`): grava a fábrica e recarrega com `Modelo.gravar`/`de_arquivo`; confere `para_json`, `legenda`, `composicao` e filtergraph idênticos nos 2 compostos. `para_json()` devolve a fonte normalizada (`modelo.py:186`, `205-207`), então o round-trip fecha por construção.
- **E-M2** (`:226-247`): `de_preset(asdict(...))` é None porque o flat não tem a chave `composicao` (`composicao.py:310-312`). São 83 campos no flat, e o flat não guarda `fracao_altura`.
- **E-M3** (`:250-268`): chave desconhecida no topo, num ramo e num ramo inventado gera aviso e carrega mesmo assim. Fábrica sem aviso, mas só no `cortes`.
- **E-M4** (`:610-618`): trata de preset sem composição seguindo no caminho F3, não de chave desconhecida (essa é a E-M3). `impressao() == ""`.

**`provas/entrada_real.py`: integração pelo ponto de entrada real (§13.1).**

| Função | Linha | O que faz |
|---|---|---|
| `transcricao_sintetica(duracao_s, *, pausas=(), inicio=0.5, palavras_por_frase=6, passo=0.65, duracao_palavra=0.6) -> dict` | `:52-92` | transcrição de frases regulares |
| `frases(transcricao)` | `:95-98` | frases da transcrição |
| `semear(raiz, nome, transcricao, *, video=None, segundos_wav=10.0) -> (entrada, saida)` | `:117-173` | prepara a pasta; detalhe abaixo |
| `gravar_resposta(raiz, nome, itens) -> Path` | `:176-181` | grava em `_entradas/<nome>.json` (utf-8, LF) |
| `item(**campos)` | `:184-188` | clipe-base para respostas |
| `ambiente(extra=None)` | `:196-202` | remove `ANTHROPIC*`; define `PYTHONPATH`, `PYTHONUTF8` e afins |
| `cli(*args, env=None, timeout=900.0) -> CompletedProcess` | `:205-212` | `[sys.executable, "-B", "-m", "clipper", ...]`, cwd=RAIZ |
| `saida_do_cli(proc)` | `:215-216` | stdout + stderr |
| `cli_em_processo(argv) -> int` | `:219-231` | `clipper.cli.main` no mesmo processo, para espiões |
| `job_do_painel(raiz, slug, entrada, *, comando, somente=None, timeout=900.0, **opcoes) -> dict` | `:239-265` | `ui.jobs.Fila` real sem uvicorn; não precisa de fastapi (H-4 e H-10 passaram aqui) |
| `api_falsa(responder)` | `:273-322` | servidor local para o SDK real |
| `conforme(esquema, valor)` | `:325-358` | validação JSON Schema mínima |
| `video_lavfi(destino, segundos)` | `:366-372` | vídeo lavfi, reaproveita se existir |
| `duracao_medida(caminho)` | `:375-378` | duração medida |
| `clipes_mp4(saida, preset)` | `:381-382` | glob `*--<preset>.mp4` |

`semear` sem vídeo é a forma estrutural: entrada de 1 byte, `audio.wav` gerado como seno, e as assinaturas de ingestão e transcrição gravadas iguais às do CLI. A energia é calculada de verdade.

O E-I5 (`prova_f6.py:1757-1780`) é um molde estrutural útil: `render --preset` recusado antes de abrir o ffmpeg. `carregar_preset` roda logo depois de `_exigir_entradas` (`render.py:2414-2418`).

## 2. Regressão (E-R1/E-R2) e `provas/fixtures/baseline/`

**Baseline.** São 6 arquivos LF, gravados no commit `fd89a4a` e capturados de `12fc1e2b`:
- `filtergraph-{cortes,cortes-editorial}.txt`, com etapas separadas por `;\n` e normalizadas por `.replace(";\n", ";")` (`:282`);
- `legenda-{4 presets}.ass`.

Não existe script no repositório que regenere o baseline.

**O que cada prova compara.**
- **E-R1** (`:271-297`): o filtergraph dos 2 compostos. Igual ao baseline, ou delta só em etapas que contenham `pilula`/`gancho`. Hoje há 2 etapas diferentes em cada um (16 e 17).
- **E-R2** (`:300-353`):
  - `bold-amarelo` e `clean-branco` têm de sair byte a byte iguais;
  - nos compostos, o cabeçalho só pode mudar o MarginV (índice 21, `:360-371`) e o número de linhas não pode crescer;
  - inclui controles que mordem (`:340-353`).
- **E-G2** (`:604-607`): o escape tem de devolver o filtergraph do baseline byte a byte.
- Também leem o baseline: E-L1 (`:426-430`, conta blocos de 1 palavra), E-L2 (`:459-465`) e E-C1 (`:1013`, com um OR frouxo).

**Lista FECHADA de exceções** (`:141-145`):
- **E1**: pílula permanente vira gancho com recorte temporal;
- **E2**: MarginV do `cortes-editorial` (450 → 500);
- **E3**: piso de 3 palavras com guarda de lacuna, e destaque pulando palavras de até 2 letras.

**Mudar o JSON de um preset de fábrica quebra alguma prova?** Simulei em memória:
- **Chave conhecida com o valor padrão** (`min_palavras_linha=0` e `max_linhas_bloco=2` no `bold-amarelo`; `gancho.fade_saida_s=0.4` no `cortes`): nada muda. Avisos `[]`, `.ass`, filtergraph e impressão iguais, e nenhuma prova quebra.
- **Chave desconhecida**: gera aviso e carrega. Só a E-M3 quebra, e só se a chave entrar no `cortes.json`. Saídas iguais.
- **Campo novo no dataclass** com padrão que reproduz o comportamento atual: as provas continuam verdes, mas a impressão muda (colisão 3).
- **Hashes de fixture**: E-X1 e E-F1 só cobrem `wetyO2gOOeU` (`:1787-1790`), não os presets.

## 3. Físicas pelo CLI: F-I1..F-I4

**Montagem da pasta.**
- `R = _p5_raiz(raiz, "f-iN")`, que limpa a pasta antes.
- Vídeo: `ER.video_lavfi(.../p5-videos/fonte-p5.mp4, 70.0)`, um lavfi 1280×720 reaproveitado entre as provas.
- Transcrição: `transcricao_sintetica(68.0)`.
- `ER.semear(..., video=video)` roda a ingestão real com ffmpeg, grava a transcrição sintética com a assinatura do CLI e calcula a energia de verdade (`entrada_real.py:160-172`).

**O que cada uma faz.**
- **F-I1** (`:1942-2014`): select e render pelo CLI e pelo painel (`job_do_painel`), mais LUFS e avisos.
- **F-I2** (`:2017-2052`): `bold-amarelo` com 1 segmento renderiza; com 2, recusa.
- **F-I3** (`:2055-2116`): 4 rodadas de render, com `time.sleep(1.1)` porque a assinatura usa o mtime em segundos.
- **F-I4** (`:2119-2170`): `cli_em_processo` com espião em `ffmpeg_utils.rodar`.

**O que precisam.**
- ffmpeg e ffprobe.
- `mediapipe` e `opencv` do lock (`requirements.lock.txt:33,36`). O vídeo é horizontal, então todo render chama `calcular_reframe` (`render.py:1642`), que precisa do detector de rosto (`render.py:334-371`).
- O `.tflite` em `models/`, que é baixado na primeira vez (`render.py:299-331`). Aqui ele já existe.
- Pillow (F-I3) e `libegl1` no Linux (`relatorio-f61.md:13`).
- Não precisam de whisper, `anthropic` nem `fastapi`.
- Aqui falta o `mediapipe`, então elas não rodariam neste sandbox.

**Tempo.** Nenhum documento registra. Inferi pelos mtimes dos artefatos de uma rodada anterior neste sandbox Linux, em 15/10: F-I1 cerca de 65 s, F-I2 cerca de 17 s, F-I3 cerca de 90 s, F-I4 cerca de 34 s. Somam uns 3,5 minutos. O `segundos_encode` nos `metadados.json` foi 27,6 / 10,4 / 24,6 / 25,7 s. Não é medida do Windows.

## 4. `ui/provas/prova_f5.py`

São as provas do painel, P1–P9 (`casos.py:549-559`). Cada uma sobe o uvicorn real e fala HTTP com ele. Rodam com `python -m ui.provas.prova_f5` (`:6-7`). O harness é de dois estados, sem `Pulou`; o `main` está em `:305-338`.

| Precisa de | Onde |
|---|---|
| `PYTHON` fixo em `.venv\Scripts\python.exe` | `:35` |
| portas 8799 (painel) e 8798 (servidor de arquivos) | `:36-37` |
| `taskkill` | `:184-188` |
| `netstat -ano` | `casos.py:492` |
| `_teste/clipe-curto.mp4` | `casos.py:34`, `38-44` |
| whisper (os jobs passam pela transcrição) | `casos.py:67`, `106-110` |

Na prática, só roda no Windows. `video_de_teste()` (`:62-83`) é código morto: ninguém o chama. A P9 sabota temporariamente o `ui/server.py`, que é arquivo versionado, e o restaura conferindo o sha (`casos.py:510-546`).

## 5. Convenções e CRLF

**Regras do CLAUDE.md §5.** Comentários e docstrings em PT-BR sem acento; mensagens ao usuário com acento; `encoding="utf-8"` sempre; `newline="\n"` em texto multilinha; `\r?\n` em regex ou split.

Conformidades:
- `Modelo.gravar` (`modelo.py:213-217`), `gravar_resposta` (`entrada_real.py:179-180`) e `prova_f61.py:64,265` gravam com `newline="\n"`.
- As provas usam `.splitlines()`; não há `split("\n")` no harness.

Desvios:
- `prova_f6.py` tem 47 linhas de comentário com acento (por exemplo `:290-291`, `:320-321`) e docstrings acentuadas (`:6`, `:227`, `:272`).
- `casos.py` tem 11 linhas assim.
- `casos.py:531` grava com `write_text` sem `newline`; o arquivo é restaurado byte a byte em `:543`.

**CRLF.** Rodei `git ls-files --eol`, contei os bytes CR e rodei `file`.
- Só 2 arquivos versionados têm CRLF, e de propósito: `provas/fixtures/wetyO2gOOeU/resposta-v1.json` (41 CR) e `transcricao.json` (23108 CR). Os dois estão protegidos por `.gitattributes`: `provas/fixtures/** -text`.
- Todo o resto é LF: os `.py`, os 4 presets, o baseline, `sintetica/palavras.json` e os `.md`. `provas/__init__.py` está vazio.

**Comando para o Bruno no Windows**, no formato de `relatorio-f61.md:80-84`, depois de `git fetch` e `git checkout claude/charming-euler-02p9cf`:

```
.venv\Scripts\python provas\prova_f8a.py [--fisicas]
```

Arquivos citados:
- /home/user/ClipPro/provas/prova_f6.py
- /home/user/ClipPro/provas/prova_f61.py
- /home/user/ClipPro/provas/entrada_real.py
- /home/user/ClipPro/provas/gerar_clipe_curto.py
- /home/user/ClipPro/ui/provas/prova_f5.py
- /home/user/ClipPro/ui/provas/casos.py
- /home/user/ClipPro/clipper/modelo.py
- /home/user/ClipPro/clipper/pipeline/render.py
- /home/user/ClipPro/provas/fixtures/baseline/

Scripts da simulação em memória, que não fazem parte do repositório:
- /tmp/claude-0/-home-user-ClipPro/a6c45088-77bb-59ae-9bce-89eebcd589cd/scratchpad/sim_chave.py
- /tmp/claude-0/-home-user-ClipPro/a6c45088-77bb-59ae-9bce-89eebcd589cd/scratchpad/sim_r2.py
- /tmp/claude-0/-home-user-ClipPro/a6c45088-77bb-59ae-9bce-89eebcd589cd/scratchpad/sim_r2b.py

---

## Crítica de completude e de conflito

# Crítica de completude e de conflito: recon do F8a

Base: `ecd79b4` (`claude/charming-euler-02p9cf`). Não editei nenhum arquivo do repositório. Li o código e rodei 3 verificações no scratchpad:
- `/tmp/claude-0/-home-user-ClipPro/a6c45088-77bb-59ae-9bce-89eebcd589cd/scratchpad/verif_hash.py` (hashes de identidade e caminho usado como preset)
- `/tmp/claude-0/-home-user-ClipPro/a6c45088-77bb-59ae-9bce-89eebcd589cd/scratchpad/verif_tipo.py` (campo de legenda com tipo errado)
- uma checagem inline de BOM e de `%` no argparse

**Confirmado no código:**
- Preset-resolução C1: `Modelo.de_fabrica(n).legenda == carregar_preset(n)` e `.composicao == carregar_composicao(n)` dão True nos 4 modelos de fábrica.
- C2: a assinatura do estágio não leva a legenda (`render.py:2435-2447`).
- C4: reproduzi as 4 impressões `af47…`, `2d99…`, `7cb2…` e `6afd…`.
- C5: `git check-ignore` devolve `.gitignore:29:models/` para `provas/fixtures/models/x`.
- `%` na ajuda do `--preset` dá `ValueError`.
- Hashes de legenda de hoje: cortes `6eff370c49b2277c`, cortes-editorial `95edae0fb8870f39`, bold-amarelo `16c6f5d4fabb5aeb`, clean-branco `d085151441e51159`. De composição: cortes `af47dd00e646a23a`, cortes-editorial `c494ebf020e8579e`.

---

## (a) Afirmações erradas ou imprecisas

1. **S1, fim do §4 (ERRADO).** O relatório diz que, em `ui/jobs.py:538` e `:558`, "modelo" é o modelo do Whisper (`motor.MODELO_PADRAO`).
   - Correção: é o modelo da **API de seleção**. `motor.py:36` define `MODELO_PADRAO = "haiku"`, e `motor.py:37` traz haiku/sonnet.
   - O Whisper é `modelo_whisper` (`jobs.py:539`, `:559-561`).
   - A colisão de nome continua existindo. E há um sentido a mais: `function modelo(id)` em `ui/estaticos/app.js:17` clona `<template>`.

2. **provas-convenções, colisão 3 (impreciso).** "`_mesmo_estilo` devolve False e todo clipe é re-encodado" só vale para campo em `Composicao`:
   - a impressão entra em `"estilo"` na assinatura (`render.py:2442`), o atalho falha e os compostos recodificam já na próxima chamada;
   - campo em `legendas.Preset` não toca a assinatura, o atalho pula (`render.py:2450-2458`) e o efeito fica **latente**, como dizem S1 e C3.

3. **S1 §3 e preset-resolução C3 citam `--force` como gatilho do recode por efeito colateral.** Com `--force` o reaproveitamento por clipe já está desligado (`render.py:1584-1586`: `pronto = None if forcar`). Os gatilhos reais do efeito colateral são outros:
   - capa ou `publicacao.md` faltando: `_arquivos_no_lugar` devolve False (`render.py:2310-2313`) e o laço roda;
   - seleção nova que mantém trechos iguais;
   - transcrição ou energia regravadas;
   - no caminho F3, qualquer reabertura do estágio.

4. **S1 §3a.** A energia **só entra** na assinatura com composição (`render.py:2446`), e não sempre.

5. **S2 §2.** Diz "18 chamadas diretas nas provas"; são **19**: 16 em `prova_f6.py` (784…1865) e 3 em `prova_f61.py:328,341,344`.

6. **S2, colisão 7.** O 4-linhas do `cortes-editorial` de fato não foi medido no Windows. Mas o **pior caso de 7 linhas foi**: 262 px, base em y=458 (`relatorio-p5.md:89`; o placar é de Windows, `relatorio-p5.md:12`). Esse limite superior existe e o relatório o omitiu.

7. **S2 §1, "util mínimo de 80".** O `max(80, …)` é aplicado **antes** de subtrair o acento (`composicao.py:912-914`), então o `util` pode ficar abaixo de 80.

8. **S1, hashes "com campo novo"** (`7f31…` e outros). São ilustrativos e dependem do nome e do valor do campo simulado: com outro nome deu `17e2e2902dd435ac` para o cortes. O que vale é o fato de o hash mudar. Os hashes "hoje" batem exatamente.

9. **`recon-f8a.md:20-22` e `:35-37`.** "Ler um JSON qualquer já funciona" e "não toca em render" estão desmentidos, como C1 e S1 apontaram:
   - o render só lê `DIR_PRESETS / f"{nome}.json"` (`render.py:173`);
   - fora de `clipper/modelo.py`, há 42 usos de `clipper.modelo`, todos em `provas/prova_f6.py`.

---

## (b) O que ficou sem resposta e é necessário para implementar o F8a com segurança

1. **Resolvedor único nome→arquivo.** Hoje há 3 listagens independentes:
   - `cli.py:231-243`;
   - `render.py:158-163`;
   - `server.py:95`, sem guarda de `OSError`.

   Além disso:
   - `_recusar_v2_sem_composicao` só enumera modelos de fábrica (`render.py:2267`);
   - o render importa `DIR_PRESETS` por valor (`render.py:74-76`).

   Ninguém definiu:
   - a precedência quando o nome existe na fábrica e no usuário;
   - como distinguir nome de caminho: `"meu.json"` sem arquivo vira `meu.json.json` (`modelo.py:247-249`, `render.py:173`);
   - se o caminho resolve contra o cwd ou contra `RAIZ`;
   - o tratamento de maiúsculas e minúsculas no Windows.

2. **Regra de nome válido para modelo do usuário: não existe.** O nome cru vai para:
   - o `.ass`, em `legenda_{id}_{preset_nome}.ass` (`render.py:1668`). O `subtitles=filename='…'` não escapa o nome (`ffmpeg_utils.py:273`), então um apóstrofo quebra o filtro;
   - o slug truncado em 32 caracteres (`render.py:961`);
   - a ajuda do `--preset`, onde um `%` faz o argparse levantar `ValueError` (reproduzido).

3. **Constante da pasta.** Não existe em `config.py`. E o nome óbvio, `DIR_MODELOS`, **já está ocupado**: `render.py:125` é `RAIZ / "models"`, o `.tflite` do detector de rosto.

4. **Isolamento nas provas.** Não há override por ambiente. Sem isso, uma prova de "duplicar" escreve na pasta real do usuário. Há precedente de variável de ambiente: `CLIPPER_MODELO_ROSTO_URL` (`render.py:127-128`).

5. **Tipo não validado (achado novo).** Um modelo com `"max_palavras_linha": "3"`:
   - carrega com `avisos() == []`;
   - estoura `TypeError: '>=' not supported between 'int' and 'str'` em `agrupar_linhas` (`legendas.py:234`), porque o valor vai cru (`:538`);
   - o mesmo vale para `max_caracteres_linha`;
   - em modelo de fábrica nunca aconteceu; em modelo editado à mão é provável, e a falha só aparece no meio do render.

6. **BOM (achado novo).** `ler_json` (`config.py:219-220`) e `Modelo.de_arquivo` (`modelo.py:193`) leem com `utf-8`, e um JSON salvo com BOM dá `JSONDecodeError: Unexpected UTF-8 BOM` (reproduzido).
   - O select já tolera BOM na resposta colada (`select.py:249`).
   - O CLAUDE.md §5 manda ler com `utf-8`. É decisão do arquiteto se modelo do usuário lê com `utf-8-sig`.

7. **Duplicar.** Falta decidir:
   - a interface: subcomando, botão ou os dois;
   - o nome de destino e a política de sobrescrita (`Modelo.gravar` sobrescreve calado, `modelo.py:209-218`);
   - a ordem das chaves: `gravar` reordena alfabeticamente (`modelo.py:144-150`, `:214`), então a cópia não se parece com o arquivo de fábrica;
   - o `"nome"`/`"descricao"` internos herdados (`"cortes"`). Hoje o render usa o nome interno (`render.py:205`) e o `Modelo` usa o stem (`modelo.py:194`).

8. **Onde `avisos()` aparece.** Nenhum consumidor fora de `prova_f6.py:261-267`.

9. **Painel.**
   - O `<select>` não tem grupos (`app.js:83-85`).
   - `escapar()` não escapa aspas e o resultado vai dentro de `value="…"` (`app.js:169-173`).
   - O re-render manda só `clip_n` e `forcar` (`app.js:305`).
   - O `job.json` guarda a string crua (`jobs.py:537`): retomar um job cujo modelo foi apagado ou renomeado falha no render.

10. **S1.** Ficam abertos:
    - o nome do campo, a sentinela e se algum modelo de fábrica muda de valor (D2 item 4, "o teto não afrouxa", `RULINGS.md:500-501`);
    - E-L1, E-L3 e E-X2 conferem contra `max_palavras_linha` (`prova_f6.py:417-419`, `:523-525`, `:1888-1890`);
    - não há referência byte a byte de "padrão = hoje" nos compostos: a E-R2 só olha o cabeçalho e a contagem (`prova_f6.py:319-338`).

11. **S2, detalhes não resolvidos.**
    - **Mensagem de recusa:** precisa ser acionável pelo LLM, por exemplo com um orçamento em caracteres.
    - **Avisos de fonte:** o aviso de fonte de reserva sai a cada chamada (`composicao.py:658-662`) e precisa de dedupe.
    - **Quando pular:** com `comp is None` ou `gancho_ativo` falso (`composicao.py:1059-1063`).
    - **Normalização:** replicar a do texto (`composicao.py:908-910`).
    - **Laço de encolhimento:** o passo de 2 px pode descer 1 px abaixo do mínimo (`composicao.py:922-924`).

    O caminho exato é extrair `composicao.py:908-930` para uma função compartilhada.

12. **Sugestão fixa no erro de validação.** `_erro_de_validacao` sugere literalmente `clipper select <entrada> --resposta <arquivo>` (`select.py:1458`), sem flags. Se a seleção passar a depender do modelo, o conserto revalida contra `cortes`.

13. **C2 entra no F8a?** Pôr `impressao_legenda` na assinatura do estágio custa **uma passada do laço, sem recode**: `_mesmo_estilo` reaproveita quando a legenda não mudou (`render.py:1373-1377`, `:1584-1596`). Mas, se o S1 mudar o hash sem mecanismo, esse conserto transforma o recode latente em imediato.

14. **Harness.** O CLAUDE.md §4 nomeia `provas/prova_f6.py`. A F6.1 abriu `prova_f61.py`, que é o precedente. `prova_f8a.py` não existe, e o comando para o Bruno depende disso.

15. **Documentação.**
    - `README.md:151-153` manda copiar o preset para dentro de `clipper/presets/` e promete que editar refaz os clipes, o que é falso por C2.
    - O CLAUDE.md §2 ainda diz `lote/clip-f6` e `[CLIP-F6]`. O RULINGS §20.1 diz `claude/charming-euler-02p9cf` e `[CLIP-F8a]`, e prevalece (§3).

---

## (c) Colisões com o que o arquiteto decidiu

### C-1. A S2 depende do modelo, mas a seleção não o recebe
- `validar` (`select.py:809-818`), `selecionar` e `_preparar` não têm preset.
- O lambda da seleção passa só estratégia, n, modelo, forçar, resposta e api (`motor.py:288-297`).
- O `select` não tem `--preset` (`cli.py:341-351`).
- **Nuance não destacada nos relatórios:** no `run` e no painel o modelo **já é conhecido** antes da seleção. Está em `Opcoes.preset` e em `job.opcoes`, e chega à rota manual (`server.py:224-228`). Só não é repassado. Quem não tem modelo nenhum é o subcomando `select`.

Opções:
- **O1 — usar o modelo do pedido.**
  - Prós: mede exatamente o modelo que vai renderizar.
  - Contras: um render posterior pode trocar de modelo (`server.py:278`; `render --preset`). Exige `--preset` no `select`, mexer em `_flags_repetidas` (`cli.py:592-595`, cujo comentário diz que o `select` recusaria a flag) e na sugestão de `select.py:1458`.
- **O2 — todos os compostos com gancho ativo.**
  - Prós: vale para qualquer render futuro.
  - Contras: N medições por gancho. Um modelo de usuário com caixa estreita recusa tudo. O conjunto muda quando o usuário cria um modelo.
- **O3 — sempre `PRESET_PADRAO`.**
  - Prós: simples.
  - Contras: a S2 vira o teto do `cortes`, não do modelo.
- **O4 — proxy por caracteres.**
  - Prós: determinístico.
  - Contras: não são "4 linhas". O pior caso com até 90 caracteres dá 9 linhas no Windows (`relatorio-p5.md:88`).

**Sub-decisão: a assinatura do select.**
- **(α) Pôr a identidade do modelo na assinatura.** Achado novo: sem `--resposta`, `run --preset B` depois de uma seleção manual não reaproveita (`select.py:1812`). Sem fonte de resposta, devolve **pendente** (`select.py:1841-1855`). Isso quebra o fluxo "seleciona uma vez, renderiza em vários modelos".
- **(β) Não pôr.** O render avisa quando o gancho passa de 4 linhas no modelo dele; hoje ele já avisa acima de 2 (`render.py:1757-1777`).
- **(γ) Gravar no `selecao.json`, só nos clipes v2, qual modelo foi medido.** O render compara e avisa.

**Onde mora o 4.**
- Constante em `select.py`, como `MAX_SEGMENTOS` (`select.py:94`): não afeta identidade.
- Chave do modelo dentro de `Composicao`: muda a impressão (C-5).
- Chave do modelo num dataclass próprio fora da impressão: cumpre "duas camadas" sem mexer no cache.

### C-2. Medir linhas exige a fonte do Windows
- A pílula é desenhada pelo Pillow com `_fonte` (`composicao.py:612-674`), cuja cadeia de reserva nunca levanta. Logo, **na mesma máquina**, medir com a mesma função dá exatamente o que o render desenha, inclusive quando cai na reserva.
- A divergência só acontece em dois casos:
  - seleção e render em máquinas ou fontes diferentes;
  - provas estruturais no Linux, que caem em DejaVu.
- `_fonte` não informa que caiu na reserva: só loga.
- A F-I1 usa `_GANCHO_LONGO`, com 90 caracteres (`prova_f6.py:1933-1936`). Esse gancho mede **exatamente 4 linhas** no `cortes` no Windows e vai em `segmentos`, então vira prova de fronteira que depende da fonte.

Opções:
- **(a) Medição real.** Função extraída de `composicao.py:908-930`, com medidor injetável. A prova estrutural usa medidor sintético (precedente E-L4, `prova_f6.py:528-557`). A contagem real fica numa física no Windows (estender a F-G3).
  - Prós: exato no Windows.
  - Contras: depende da máquina, e a estrutural não decide 4 contra 5 linhas.
- **(b) Proxy por fator** (como a E-C4, `prova_f6.py:1410-1430`, ou `_FATOR_LIBASS`, `legendas.py:150-153`).
  - Prós: igual em qualquer máquina.
  - Contras: letras largas (W, M) estouram.
- **(c) (a) mais recusa ou aviso quando a fonte do modelo não abriu.** Exige que `_fonte` devolva se caiu na reserva, mudando uma função também usada por `legendas._medidor` (`legendas.py:171`).
- **(d) (a) com recuo para (b)** quando a fonte não abriu.

### C-3. "v1 congelado" contra "a regra é só do v2"
- `e_v2` decide por item, pela chave `segmentos` (`select.py:464-466`).
- O prompt v2 manda o clipe de 1 trecho usar `inicio`/`fim` (`prompt_selecao.py:163`) e diz "Na dúvida, use um trecho só" (`:148`).
- O próprio arquiteto usa "v2 de 1 segmento" para um item com `segmentos` (D6, item 3).
- Não há marcador de versão na resposta.

Opções:
- **(i) Só itens com `segmentos`.** Respeita o congelamento; cobre poucos clipes.
- **(ii) Todos os itens.** Cobre tudo, mas muda o contrato v1. A E-X1 continua verde: os 5 ganchos reais têm 57–70 caracteres e medem até 3 linhas.
- **(iii) Recusa só nos itens com `segmentos`, aviso nos de `inicio`/`fim`.** Aviso não faz o selecionador reescrever.
- **(iv) Marcador de versão.** Muda o contrato e o prompt aprovado.

### C-4. O prompt promete 90 caracteres; o teto de 4 linhas pode recusar menos que isso
- `prompt_selecao.py:172`; D5 Q10 (`RULINGS.md:754-757`).

Opções:
- Manter o texto, com a recusa trazendo o orçamento medido.
- Mudar o texto: exige aprovação, porque o prompt-v2 foi aprovado como texto na D5.
- Prompt por modelo: o `prompt_selecao.txt` passa a mudar quando o modelo muda (`select.py:1358-1367`).

### C-5. Identidade de cache ao somar campo
- `impressao_legenda` faz sha de `asdict(Preset)` (`render.py:1345-1349`).
- `Composicao.impressao` faz sha de `{versao, **asdict}` (`composicao.py:282`).
- `Composicao.nome` entra na impressão: renomear um modelo do usuário recodifica.
- **Precedente verificado no git:** `impressao_legenda` existe desde `7afa164` (F4a). Os campos F6 entraram em `1a4ba89` junto com `VERSAO = 3`. A identidade de `bold-amarelo` e `clean-branco` mudou por efeito colateral, e isso não está registrado.
- Nenhuma prova fixa esses hashes.

Opções:
- **(i) Lista fechada** de campos pós-F6 omitidos do hash quando estão no padrão.
- **(ii) Marcador por campo** (`field(metadata=…)`) com a mesma semântica de (i), sem lista separada.
- **(iii) Campo que não muda pixel** (o da S2) num dataclass fora da impressão.
- **(iv) Recode único**, anunciado e gravado no RULINGS (precedente: D7, "invalidação de cache esperada").
- **(v) Subir `VERSAO`:** vedado, porque o resultado não muda, e não alcança o caminho F3.
- **(vi) S1 na leitura R1:** nenhum campo novo, nada muda.

Em qualquer caso: uma prova que congele os 6 hashes listados no topo.

### C-6. Preset como caminho no nome de arquivo e nos metadados
A string crua vai para:
- `Opcoes` (`motor.py:128`);
- a assinatura (`render.py:2437`) e o `extra` (`:2644`);
- `Composicao.nome` e, portanto, a impressão (`render.py:290`);
- o `.ass` (`:1668`) e o slug do mp4 (`:961`);
- os metadados (`:1303`, `:1734`, `:1934`);
- a chave `(id, preset)` (`:2041-2048`) e `_arquivos_no_lugar` (`:2305`);
- o filtro do painel (`jobs.py:630`) e o `job.json` (`jobs.py:537`);
- as sugestões de linha de comando (`cli.py:594-595`; `render.py:2613`, sem aspas).

Reproduzido: um caminho absoluto vira o slug `home-user-clippro-clipper-preset`, e o nome do modelo some.

Opções:
- **(a) Canonicalizar na entrada.** Identidade = stem; recusar caminho cujo stem colide com o catálogo; charset com stem igual ao próprio slug.
  - Prós: uma identidade só, metadados portáveis; elimina os problemas de `%`, apóstrofo, `:` e maiúsculas.
  - Contras: proíbe acento e espaço no nome.
- **(b) Importar.** `--preset arq.json` copia o arquivo para a pasta do usuário e passa a usar o nome.
  - Prós: os mesmos de (a).
  - Contras: escrita como efeito colateral, mais uma política de sobrescrita.
- **(c) Manter o caminho cru e só higienizar os nomes de arquivo.**
  - Prós: menos código.
  - Contras: metadados presos à máquina, uma identidade por grafia, `(id, preset)` duplicado.
- **(d) Ortogonal às anteriores:** o painel aceita só nomes do catálogo e o CLI aceita caminho.

### C-7. "Chave desconhecida avisa" não vale no caminho real (colisão nova)
- O render carrega por `Preset.de_dict`, que filtra em silêncio (`legendas.py:96-99`), e por `de_preset`, que cai no padrão.
- `avisos()` só existe no `Modelo`, que o pipeline não usa.

Opções:
- **(a) O render passa a usar `Modelo`.** Os objetos são idênticos nos 4 modelos de fábrica, então não muda pixel nem cache.
  - Contras: é preciso migrar `_conferir_cores` e a mensagem de campo faltando (`render.py:209-280`). E o nome vira o stem: uma cópia `meu.json` com `"nome": "cortes"` muda `Preset.nome` e `impressao_legenda`.
- **(b) `_ler_preset` chama `_desconhecidas` e loga.**
  - Prós: menor mudança.
  - Contras: mantém dois carregadores.

### C-8. `.gitignore` e o nome da pasta
- `models/` não é ancorado (`.gitignore:29`) e vem depois de `!provas/fixtures/**` (`:22`), então engole `provas/fixtures/**/models/`. O comentário em `:16-21` afirma o contrário.
- `modelos/` não está ignorado hoje.

Opções:
- `/modelos/` ancorado.
- Outro nome, para fugir de models×modelos e de `DIR_MODELOS`.
- Corrigir `models/` para `/models/`, se o arquiteto aceitar no escopo.
