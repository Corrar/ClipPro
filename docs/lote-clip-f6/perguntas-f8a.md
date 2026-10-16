# F8a "modelos" — perguntas ao arquiteto (PARE)

Base: `2ea323d` (`claude/loving-newton-bykd21`). Código de `clipper/`, `ui/` e
`provas/` idêntico ao do recon (`8254c75`); as referências de linha do
`recon-f8a-codigo.md` valem. **Nenhum código do F8a foi escrito.**

Escopo já decidido (RULINGS §20.1): modelos do usuário numa pasta do
repositório ignorada pelo git; `--preset` com nome ou caminho; painel lista
fábrica + usuário; duplicar um modelo de fábrica; sementes S1 e S2; sem editor
visual.

Q1–Q9 são as do `docs/PENDENCIAS.md` §3, com a mesma numeração. Q10–Q19 o
recon levantou mas não tinham virado pergunta. Cada uma tem letras e a
recomendação do executor; **a escolha é do Bruno**.

## Placar da base (rodado nesta sessão, Linux, com ffmpeg)

| Prova | Resultado |
|---|---|
| `prova_f6.py --fisicas` | **44 passaram, 0 pularam, 0 falharam** |
| `prova_f61.py --fisicas` | **13 passaram, 0 pularam, 0 falharam** |

Ambiente: venv com os pacotes do lockfile que faltavam no container e a
`libegl1` do sistema (o `mediapipe` a carrega). Nada mudou no repositório.

---

## Bloco 1 — legenda (S1) e identidade de cache

**Q1. O que é a S1.** O "teto 3" já é `max_palavras_linha` do modelo; o que está
fixo é a fusão usar o mesmo teto do agrupamento (`legendas.py:547-552`).

| | |
|---|---|
| A | Nada novo: o usuário muda `max_palavras_linha` (muda também o agrupamento). |
| **B** | Campo novo só para a fusão, `teto_fusao`, sentinela `-1` = "usa `max_palavras_linha`" (precedente `margem_direita=-1`). Fábrica sem mudança de valor. |

Recomendação **B**. E-L1, E-L3 e E-X2 passam a conferir contra o teto efetivo.

**Q2. Campo novo muda o hash de todos os modelos** (`asdict` inteiro em
`render.py:1345-1349` e `composicao.py:282`) → recodifica sem subir `VERSAO`.

| | |
|---|---|
| A | Lista fechada de campos pós-F6 omitidos do hash quando no padrão. |
| **B** | Marcador por campo (`field(metadata=…)`), mesma regra de A sem lista à parte. |
| C | Recode único, anunciado e gravado no RULINGS (precedente D7). |

Recomendação **B**, mais uma prova que congela os 6 hashes de hoje (legenda:
cortes `6eff370c…`, cortes-editorial `95edae0f…`, bold-amarelo `16c6f5d4…`,
clean-branco `d0851514…`; composição: cortes `af47dd00…`, cortes-editorial
`c494ebf0…`). Subir `VERSAO` é vedado: o resultado não muda.

**Q16. Editar só a legenda não refaz os clipes** (a assinatura do render não
leva `impressao_legenda`, `render.py:2435-2446`). O `README.md:151-153` promete o
contrário (D1). No F8a isso vira central: modelo do usuário existe para ser
editado.

| | |
|---|---|
| **A** | Entra no F8a: `impressao_legenda` na assinatura + README corrigido. Custa uma passada do laço por `out/`, sem recode (com Q2 = B o hash da fábrica não muda). |
| B | Fica para um F6.2. |

Recomendação **A**.

## Bloco 2 — gancho (S2)

**Q3. A S2 precisa do modelo, a seleção não o recebe** (`select.py:809-818`).
No `run` e no painel o modelo já é conhecido antes da seleção; só o subcomando
`select` não tem nenhum.

| | |
|---|---|
| **A** | Mede no modelo do pedido; `select` ganha `--preset` (padrão `cortes`). |
| B | Mede em todos os compostos com gancho ativo. |
| C | Mede sempre no `cortes`. |
| D | Proxy por caracteres (pior caso de 90 caracteres = 9 linhas no Windows). |

Sub-decisão: o modelo **não** entra na assinatura do select (senão `run --preset
B` depois de uma seleção manual fica pendente, `select.py:1841-1855`); fica
gravado no `selecao.json` e o render avisa se divergir. Recomendação **A**.

**Q4. "v1 congelado" × "a regra é do v2".** Clipe de 1 trecho usa
`inicio`/`fim` e conta como v1 (`select.py:464-466`, `prompt_selecao.py:148,163`).

| | |
|---|---|
| A | Teto só nos itens com `segmentos`. |
| B | Teto em todos os itens (muda o contrato v1). |
| **C** | Recusa nos itens com `segmentos`; aviso nos de `inicio`/`fim`. |
| D | Marcador de versão na resposta (muda contrato e prompt aprovado). |

Recomendação **C**.

**Q5. O prompt aprovado promete gancho de até 90 caracteres** (`prompt_selecao.py:172`);
4 linhas pode recusar menos que isso.

| | |
|---|---|
| **A** | Mantém o texto; a recusa traz o orçamento medido em caracteres. |
| B | Muda o texto do prompt (exige aprovar texto novo). |
| C | Prompt por modelo. |

Recomendação **A**.

**Q10. Contar linhas depende da fonte instalada** (`composicao.py:612-674`).
Na mesma máquina, medir com a função do render dá exatamente o que ele desenha,
inclusive na fonte de reserva.

| | |
|---|---|
| **A** | Medição real: extrair `composicao.py:908-930` para função compartilhada com medidor injetável; estrutural com medidor sintético (precedente E-L4); a fronteira 4×5 numa física no Windows (estende a F-G3). |
| B | Proxy por fator (igual em qualquer máquina; W e M estouram). |
| C | A + recusa/aviso quando a fonte do modelo não abriu (muda `_fonte`, usada também pela legenda). |
| D | A com recuo para B quando a fonte não abriu. |

Recomendação **A**.

**Q11. Onde mora o "4".** O §14.2 fixa 4 linhas e não diz se é parâmetro do modelo.

| | |
|---|---|
| **A** | Constante em `select.py`, como `MAX_SEGMENTOS`: não toca identidade. |
| B | Campo do modelo dentro de `Composicao` (muda a impressão, cai no Q2). |
| C | Campo do modelo num dataclass fora da impressão. |

Recomendação **A**.

## Bloco 3 — modelos do usuário

**Q6. Caminho como `--preset`** vaza cru para o nome do `.ass`, o slug do mp4,
os metadados e o cache (um caminho absoluto vira o slug
`home-user-clippro-clipper-preset`).

| | |
|---|---|
| **A** | Canonicalizar: identidade = stem; charset igual ao do slug; recusa stem que colide com a fábrica. |
| B | Importar: `--preset arq.json` copia para a pasta do usuário e passa a usar o nome. |
| C | Caminho cru; só higienizar nomes de arquivo. |

Recomendação **A**. Contra: proíbe acento e espaço no nome; e um modelo usado
por caminho fora da pasta não é reabrível pelo painel (B resolveria isso com uma
escrita como efeito colateral).

**Q12. Resolver nome → arquivo** (hoje há 3 listagens independentes:
`cli.py:231-243`, `render.py:158-163`, `server.py:95`).

| | |
|---|---|
| **A** | Um resolvedor só. Tem `/`, `\` ou termina em `.json` → caminho (relativo ao diretório atual); senão nome: fábrica primeiro, depois usuário. Nome de fábrica é reservado: modelo do usuário com esse nome é recusado e a listagem avisa. |
| B | Igual a A, mas o usuário sobrepõe a fábrica. |

Recomendação **A**: `--preset cortes` significa sempre a mesma coisa.

**Q7. "Chave desconhecida avisa" não vale no caminho real**: o render carrega por
`Preset.de_dict`, que filtra calado (`legendas.py:96-99`); `avisos()` só existe
no `Modelo`, que o pipeline não usa.

| | |
|---|---|
| **A** | O render passa a usar `Modelo` (objetos idênticos nos 4 de fábrica: zero pixel, zero cache). |
| B | `_ler_preset` chama `_desconhecidas` e loga; dois carregadores seguem. |

Recomendação **A**.

**Q8. Nome da pasta e `.gitignore`.** `models/` (detector de rosto) não é
ancorado e engole `provas/fixtures/**/models/` (`.gitignore:29`, confirmado com
`git check-ignore`), ao contrário do que diz o comentário das linhas 16-21.

| | |
|---|---|
| **A** | `/modelos/` ancorado; corrigir `models/` → `/models/`. |
| B | Outro nome de pasta, fugindo de models × modelos. |
| C | `/modelos/` sem mexer em `models/`. |

Recomendação **A**.

**Q9. Modelo salvo com BOM** (o Bloco de Notas faz isso) dá `JSONDecodeError`
(reproduzido). O CLAUDE.md §5 manda ler com `utf-8`.

| | |
|---|---|
| **A** | `utf-8-sig` só para modelo do usuário. |
| B | `utf-8` em tudo; recusa com mensagem "salve sem BOM". |
| C | `utf-8-sig` em toda leitura de JSON. |

Recomendação **A**.

**Q13. Duplicar.** `Modelo.gravar` sobrescreve calado e reordena as chaves.

| | |
|---|---|
| A | Só subcomando no CLI. |
| B | Só botão no painel. |
| **C** | Os dois, chamando a mesma função. |

Recomendação **C**, com: recusa se o destino existir; cópia preserva a ordem do
arquivo de fábrica e troca só `nome`.

**Q14. Isolar as provas da pasta real.** Uma prova de "duplicar" escreveria na
pasta do usuário; o render importa `DIR_PRESETS` por valor e as físicas rodam o
CLI em subprocesso.

| | |
|---|---|
| **A** | Variável de ambiente `CLIPPER_DIR_MODELOS` (precedente `CLIPPER_MODELO_ROSTO_URL`). |
| B | Só parâmetro de função; nenhuma prova pelo CLI. |

Recomendação **A**.

## Bloco 4 — provas e divergências

**Q15. Harness.** `provas/prova_f8a.py` novo (precedente `prova_f61.py`) ou
estender `prova_f6.py`? Recomendação: **novo**.

**Q17. A regressão não morde** (CLAUDE.md §4 exige que morda). Nos compostos, a
E-R2 só compara cabeçalho e contagem de `Dialogue` (`prova_f6.py:313-336`): texto
trocado, cor do realce trocada e `Dialogue` removido passaram em toda a suíte
(mutantes do recon). A E-R1 aceita qualquer delta em etapa cujo texto contenha
`pilula` ou `gancho` (`prova_f6.py:292`).

| | |
|---|---|
| **A** | Primeiro commit do F8a, antes de qualquer código: E-R2 confere também a sequência de palavras, os tempos e as cores contra o baseline (E3 segue como única exceção nos `Dialogue`); E-R1 restringe o delta à etapa da pílula; os 3 mutantes viram controles. |
| B | Lote próprio (F6.2). |

Recomendação **A**: o F8a mexe na legenda (S1) e no carregador (Q7) e precisa
de uma regressão que morda.

**Q18. A F-G1 sobrescreve `_teste/clipe-curto.mp4`** (`prova_f6.py:633`), o mesmo
vídeo que a prova F5 exige com fala real (`ui/provas/casos.py:34`). O lavfi não
tem fala. Recomendação: **a F-G1 grava num caminho próprio**.

**Q19. Divergências D1–D6 do `PENDENCIAS.md` §4.** D1 já está na Q16. D3 (aspas
no `escapar()` do painel), D4 (listagem sem guarda de `OSError`) e D5
(`max_palavras_linha: "3"` carrega sem aviso e estoura `TypeError` no meio do
render; reproduzido) estão no caminho do modelo do usuário. Recomendação: **D3,
D4 e D5 entram no F8a**; D2 (README × CUDA) e D6 (CLAUDE.md §2) num commit de
documentação à parte.

---

## Folha de resposta

Com todas as recomendações (copiar e trocar o que discordar):

```
Q1 B, Q2 B, Q3 A, Q4 C, Q5 A, Q6 A, Q7 A, Q8 A, Q9 A, Q10 A,
Q11 A, Q12 A, Q13 C, Q14 A, Q15 novo, Q16 A, Q17 A, Q18 sim, Q19 sim
```

Ou, para aceitar todas: **"F8a: recomendações"**.
