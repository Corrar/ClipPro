# ClipPro — protocolo de trabalho

> **⚠ Este arquivo é uma RECONSTRUÇÃO declarada, não o texto original.**
>
> A diretiva `CORREÇÃO DO ARQUITETO` (12/09) manda escrever aqui *"o protocolo
> permanente descrito no ATO 0"* do bloco **"GOVERNANÇA PERSISTIDA"**. Esse
> bloco **nunca chegou à sessão** — ver a lacuna documentada em
> `docs/lote-clip-f6/RULINGS.md`.
>
> O que segue foi reconstruído a partir das regras que o arquiteto **de fato
> enunciou** ao longo do lote CLIP-F6, cada uma rastreável às diretivas
> transcritas naquele arquivo. Quando o texto original chegar, **substituir
> este arquivo inteiro** — é um commit.

---

## 1. Papel e protocolo

O executor **executa**; o arquiteto **decide**.

- **Dúvida de arquitetura PARA o lote e volta como pergunta.** Nunca vira
  decisão do executor. Quando a pergunta for feita, vem com as opções
  enxergadas e uma recomendação — mas a escolha é do arquiteto.
- **Relatório completo ANTES de qualquer `git add`/`git commit`** nos pontos de
  PARE. Commit só com a palavra explícita do Bruno, exceto onde uma diretiva
  tiver autorizado o branch de trabalho (ver §2).
- **Nenhum comando destrutivo.**
- **Colisão entre o plano e o código real vai DESTACADA no relatório**, não
  silenciada nem contornada.
- Se algo citado como recebido não tiver chegado, **dizer isso** em vez de
  inventar o conteúdo.

## 2. Git

- Desenvolver no branch do lote em curso (hoje: `lote/clip-f6`, a partir de
  `12fc1e2b`). **`master` INTOCADO.** Merge somente com a palavra explícita do
  Bruno, após relatório final + provas físicas verdes.
- Commits e push **permitidos só no branch do lote** — são o transporte do
  código e o seguro contra reset de contexto.
- Commits prefixados **`[CLIP-F6]`** (o prefixo acompanha o lote em curso).
- **Cada relatório cita o SHA** do commit a que se refere.
- `git push -u origin <branch>`; em falha de rede, até 4 tentativas com espera
  2s, 4s, 8s, 16s.
- **Paridade antes de começar**: conferir que o ponto de partida bate com o
  esperado. Se `origin` tiver andado, **PARE e reporte**.

## 3. Persistência de diretivas

**Diretiva nova do arquiteto = append em `docs/lote-clip-f6/RULINGS.md` +
commit, como PRIMEIRO ATO**, antes de qualquer código.

Motivo: o contexto da sessão já foi perdido uma vez no meio do lote. Diretiva
que só vive no chat morre com o reset.

Ordem de precedência: `RULINGS.md` prevalece sobre relatórios e sobre a leitura
do executor. Entre dois itens do próprio arquivo, vence o mais recente.

## 4. Provas

Duas famílias, e a separação é de dependência, não de importância:

| | |
|---|---|
| **ESTRUTURAL** | roda só com o repositório: validador, quebrador de legenda, diff de filtergraph, prompt, round-trip do `modelo`. Sem ffmpeg, sem vídeo, sem fonte instalada. |
| **FÍSICA** | exige ffmpeg + arquivo real: duração medida, −14 LUFS, `capa.jpg`, frame do gancho. Roda no Windows do Bruno, por roteiro. |

- Harness: `provas/prova_f6.py`, espelhando `ui/provas/prova_f5.py` —
  `main(argv)`, **sem pytest, zero dependências novas**.
- Sem argumento roda as estruturais; `--fisicas` acrescenta as demais.
- **Todo checkpoint entrega o comando exato** para o Bruno rodar no Windows,
  depois de `git fetch && git checkout <branch>`.
- Fixtures são **versionadas** em `provas/fixtures/` — prova de regressão não
  pode depender de diretório ignorado. O `.gitignore` tem exceção ampla
  `!provas/fixtures/**` para isso; segredos (`.env`, `*.key`) continuam
  ignorados porque suas regras vêm depois no arquivo.
- **Prova que não pode rodar é reportada como pendente, nunca substituída por
  uma fixture inventada.** O valor da fixture real é ser real.

### Regressão e exceções

A lista de exceções declaradas é **FECHADA**. O diff de filtergraph **e** de
conteúdo do `.ass` (com caminho normalizado) deve mostrar exatamente o que a
lista permite. **Qualquer outro delta é regressão e a prova falha.**

Baseline versionado em `provas/fixtures/baseline/`, capturado do commit base.
Comparar contra arquivo — e não contra o commit — faz a prova valer em clone
raso e continuar valendo depois que o histórico andar.

## 5. Convenções de código

- **Comentários e docstrings em PT-BR sem acento; mensagens dirigidas ao
  usuário em PT-BR com acentuação correta.**
- Comentário explica **por que**, não o que — de preferência com o número
  medido que justificou a escolha.
- **CRLF é mordida conhecida da casa:** qualquer regex ou split de linha usa
  `\r?\n`.
- **Escrita de texto**: sempre `encoding="utf-8"` e, em conteúdo multilinha,
  `newline="\n"` explícito. Leitura: sempre `encoding="utf-8"`.
- Alvo declarado: Windows x64, Python 3.13, CPU-only.

## 6. Arquitetura — o que não se mexe sem decisão

- **Formato de arquivo do `modelo`**: a forma **ANINHADA** (a dos presets em
  `clipper/presets/`) é canônica; carrega por `de_preset()`. A forma **flat**
  de `asdict()` é identidade **interna** (impressão/cache) e **nunca** vira
  arquivo. As duas não são intercambiáveis — `de_preset()` resolve
  `cartao.fracao_altura` em quatro campos de pixel e apara faixas.
- **Campo novo entra nas DUAS camadas**: esquema aninhado
  (`clipper/modelo.py`) e dataclass resolvido.
- **Chave desconhecida avisa, não rejeita** (`Modelo.avisos()`).
- **`VERSAO`** (`composicao.py`) sobe **deliberadamente** quando o resultado
  muda para os mesmos parâmetros — nunca por efeito colateral de somar campo ao
  dataclass. Subir invalida todo clipe em cache.
- **`fade` com `d=0` NÃO é desligado** — cai no padrão de 25 quadros. Todo fade
  novo nasce com a guarda.
- **O `-t` de saída não sai**: o `-loop 1` da pílula é entrada infinita e nem
  `-shortest` segura.
- **`format=yuv420` explícito em todo overlay**: o `auto` custa +23% de tempo e
  mexe em 1,6 M de pixels fora da região.

## 7. Onde as coisas ficam

```
clipper/
  cli.py            CLI e subcomandos
  config.py         caminhos, slug, Estado, Saida
  modelo.py         o objeto `modelo` (legenda + composição), formato de arquivo
  composicao.py     Composicao, montar() (filter_complex), cadeia_audio()
  legendas.py       Preset da legenda, montar_ass(), karaokê
  fronteiras.py     fronteiras de frase
  ffmpeg_utils.py   binário, sondar(), rodar(), escape de caminho
  pipeline/         ingest, transcribe, select, render
  presets/          os modelos de fábrica (JSON aninhado)
ui/                 painel FastAPI local (127.0.0.1) e provas da F5
provas/             harness da F6, fixtures versionadas, gerador lavfi
docs/lote-clip-f6/  RULINGS.md — memória do lote
```

`ui/` **não duplica regra de estágio**: o painel chama as mesmas funções do
`clipper` (confirmado no recon — `server.py:204-243` chama
`select.selecionar()`, o mesmo ponto de entrada do CLI).
