# ClipPro

Transforma um vídeo longo em clipes verticais 9:16 prontos para TikTok, Reels e
Shorts — legenda karaokê queimada, enquadramento por rosto e composição que faz
o clipe **não** ser lido como cópia 1:1 do vídeo de origem.

Roda **inteiro na sua máquina**. Nenhum vídeo sai do computador. A única parte
que pode usar internet é a escolha dos trechos, e mesmo ela é opcional
(o modo padrão é você colar o prompt num chat qualquer).

```
clipper run "https://youtu.be/XXXXXXXXXXX" --n 5 --estrategia "ganchos e punchlines" --preset cortes
```

---

## O que ele faz, em ordem

| # | Estágio | O que produz |
|---|---------|--------------|
| 1 | **Ingestão** | baixa (yt-dlp) ou copia o vídeo, normaliza para `fonte.mp4` e extrai `audio.wav` 16 kHz mono |
| 2 | **Transcrição** | `faster-whisper` na CPU → `transcricao.json` (palavra a palavra, com tempo) + `.srt` + curva de energia do áudio |
| 3 | **Seleção** | monta o prompt com a transcrição em blocos e recebe de volta os N melhores trechos → `selecao.json` |
| 4 | **Render** | corta, reenquadra em 9:16, compõe o visual e queima a legenda → `clips/*.mp4` + `relatorio.md` |

Cada estágio grava o que produziu e **pula o que já está pronto**. Rodar o mesmo
comando duas vezes não baixa nem transcreve de novo.

---

## Instalação (Windows)

Pré-requisitos: **Python 3.13** e **ffmpeg**.

```powershell
# 1. ffmpeg (abra um terminal novo depois de instalar)
winget install --id Gyan.FFmpeg --exact --scope user

# 2. o projeto
cd C:\caminho\onde\voce\quer
git clone <este-repositorio> ClipPro
cd ClipPro
py -3.13 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Confira:

```powershell
.venv\Scripts\python -m clipper --versao
ffmpeg -version
```

O modelo de detecção de rosto (224 KB) é baixado sozinho na primeira vez que
você renderiza. As fontes usadas pelos presets (**Impact**, **Segoe UI Black**,
**Bahnschrift**) já vêm no Windows.

---

## Uso

### O comando de uma linha

```powershell
.venv\Scripts\python -m clipper run "https://youtu.be/XXXXXXXXXXX" --n 5 --estrategia "ganchos e punchlines" --preset cortes
```

Funciona igual com um arquivo local:

```powershell
.venv\Scripts\python -m clipper run "C:\videos\live-de-ontem.mp4" --n 8
```

### A parada do modo manual

Sem chave de API, o clipper **para** no estágio 3 e te diz exatamente o que
fazer: ele gravou `out/<slug>/prompt_selecao.txt`. Você abre esse arquivo, cola
o conteúdo num chat com qualquer modelo, salva o array JSON que ele devolver em
`resposta.json` e volta:

```powershell
.venv\Scripts\python -m clipper run "https://youtu.be/XXXXXXXXXXX" --resposta "resposta.json"
```

Se a resposta vier torta (tempo fora do vídeo, clipe curto demais, corte no meio
de uma palavra), o clipper **recusa e diz qual campo está errado em qual clipe** —
ele não renderiza um corte quebrado.

Com `ANTHROPIC_API_KEY` no ambiente, use `--api` e o clipper conversa sozinho com
o modelo, sem ida e volta.

### O painel (se você prefere não usar o terminal)

```powershell
.venv\Scripts\python -m clipper ui
```

Abre `http://127.0.0.1:8765` no navegador. É a mesma coisa que a linha de
comando faz — o painel só chama as mesmas funções — mas com:

- campo de link **ou** arrastar-e-soltar de arquivo;
- linha do tempo dos estágios com progresso ao vivo e estimativa;
- no modo manual, um botão que copia o prompt e um campo para colar a resposta,
  com os erros da validação listados **um a um**;
- os cortes prontos numa grade de players verticais, com baixar, re-renderizar
  e copiar gancho.

Um trabalho por vez, em fila: dois vídeos ao mesmo tempo não terminariam mais
rápido, só disputariam CPU e disco. Se você fechar o painel no meio, ele
**retoma** de onde parou na próxima vez — o que já estava pronto não é refeito.

O painel escuta **só em 127.0.0.1**: nenhuma outra máquina da rede alcança. Ele
não pede senha e serve os seus vídeos, então isso não é configurável.

### Comandos

```
clipper run <entrada>         pipeline completo
clipper ingest <entrada>      só baixa/normaliza
clipper transcribe <entrada>  transcreve e calcula a energia
clipper select <entrada>      escolhe os trechos
clipper render <entrada>      renderiza a partir de uma seleção pronta
clipper info <entrada>        mostra o que já existe, sem processar nada
clipper ui                    abre o painel web local
```

`render` e `info` leem **apenas** `out/<slug>/`: aceitam o nome da pasta no lugar
do vídeo e funcionam offline, mesmo que o arquivo original já tenha sido apagado.

```powershell
.venv\Scripts\python -m clipper render "o-projeto-da-minha-casa-ficou-pronto-qp3uNTpf" --clipe 2 --clipe 4
```

---

## Presets

| Preset | Visual |
|--------|--------|
| **`cortes`** *(padrão)* | Composição completa: fundo do próprio vídeo borrado e escurecido, vídeo num cartão arredondado de 75% da altura com sombra, pílula de título, barra de progresso, zoom contínuo com punch-in nos picos de áudio, karaokê Impact com uma palavra acesa por vez |
| `cortes-editorial` | A mesma composição com acabamento contido: Segoe UI Black caixa mista, âmbar no lugar do amarelo, tarja Bahnschrift, fundo dessaturado com vinheta |
| `bold-amarelo` | Sem composição: recorte 9:16 cheio, legenda Impact amarela por cima |
| `clean-branco` | Sem composição: recorte 9:16 cheio, legenda Segoe UI branca |

Os presets são JSON em `clipper/presets/`. Copie um, mude as cores e os tamanhos,
e ele aparece sozinho no `--help`. Editar um preset **refaz** os clipes dele na
próxima rodada — o clipper percebe a mudança sem precisar de `--force`.

### Por que a composição existe

Um clipe que é recorte puro do original é fácil de casar quadro a quadro. O preset
`cortes` muda a geometria, o movimento, o áudio e a tipografia do quadro inteiro.
Medido nos cinco clipes de teste: **SSIM de 0,41 a 0,73** contra o mesmo trecho da fonte
(1,00 seria idêntico).

---

## Custos

### Tempo de máquina

Medido em: Windows 11, CPU 12 núcleos, **sem GPU**, num vídeo de **29 min**.

| Estágio | Tempo | Fator |
|---------|-------|-------|
| Ingestão (download 1,0 GB + remux) | 35 s | depende da sua internet |
| Transcrição (whisper `medium`, CPU) | 19 min 56 s | **0,685× a duração do áudio** |
| Energia | 0,3 s | — |
| Seleção | instantânea (manual) | — |
| Render, por clipe, preset `cortes` | 42 s a 80 s | **~1,2× a duração do clipe** |

Ou seja: **um vídeo de 1 hora leva ~41 min de transcrição** e mais uns 6 min para
renderizar 5 clipes de 1 minuto. A transcrição é o gargalo — `--modelo-whisper small`
corta esse tempo pela metade com alguma perda de precisão nos nomes próprios.

### Disco

`out/<slug>/` guarda o vídeo normalizado (medido: 1,0 GB para 29 min em 1080p,
ou ~2 GB por hora), o `audio.wav` (~115 MB por hora) e os clipes (~1,1 MB por
segundo de clipe).
A pasta `_trabalho/` é descartável: pode apagar quando quiser.

### Dinheiro

**Zero no modo padrão.** Tudo roda local.

Com `--api`, o único custo é a chamada de seleção — um prompt de ~40 KB
(≈12 mil tokens) e uma resposta curta, **uma vez por vídeo**:

| Modelo | Preço (entrada / saída por 1M tokens) | Por vídeo, estimado |
|--------|--------------------------------------|---------------------|
| `--modelo haiku` *(padrão)* | US$ 1,00 / US$ 5,00 | **~US$ 0,02** |
| `--modelo sonnet` | US$ 2,00 / US$ 10,00 | **~US$ 0,04** |

---

## Limitações conhecidas

- **Reenquadramento estático.** Cada clipe recebe UM recorte, da mediana das
  amostras, fixo do começo ao fim. O clipper não persegue o rosto ao longo do
  tempo — de propósito: recorte que persegue rosto treme e cansa de assistir.
  Se a pessoa atravessa o quadro no meio do trecho, ela sai do enquadramento.
- **Sem rosto, recorte central.** Screen-share, b-roll e drone caem no meio do
  quadro (é o comportamento certo, não uma falha).
- **Corte em fronteira de frase.** Início e fim caem no começo e no fim de frases
  inteiras, nunca no meio de uma palavra. Em troca sobra 1–2 s de respiro nas
  pontas.
- **A qualidade dos clipes é a qualidade da seleção.** O clipper garante que o
  corte é válido; quem julga se o trecho é bom é o modelo que lê a transcrição.
- **CPU apenas.** Não há caminho de GPU. Numa máquina sem GPU a transcrição é o
  que dita o tempo total.
- **Português por padrão** (`--idioma pt`). Outros idiomas funcionam, mas as
  regras de quebra de frase foram medidas em PT-BR.
- **`loudnorm` de uma passagem** erra o alvo de −14 LUFS em até 0,7 LU. Duas
  passagens seriam exatas ao custo de um passe de análise.
- **Windows.** O código evita armadilhas de caminho do Windows e usa fontes que
  vêm com ele. Deve rodar em Linux/macOS trocando as fontes do preset, mas não
  foi testado lá.
- **`--pitch` é experimental.** Sobe o tom em 0,5% sem mudar a duração (medido:
  +0,479%). Fica desligado por padrão.

---

## Onde as coisas ficam

```
out/<slug>/
  fonte.mp4          vídeo normalizado
  audio.wav          áudio 16 kHz mono para o whisper
  transcricao.json   palavras com tempo   transcricao.srt
  energia.json       curva de energia + picos (viram os punch-ins)
  prompt_selecao.txt o texto para colar no chat (modo manual)
  selecao.json       os trechos escolhidos
  clips/*.mp4        os clipes prontos
  metadados.json     tudo sobre cada clipe (trecho, score, enquadramento, estilo)
  relatorio.md       ranking legível, com gancho e motivo de cada clipe
  clipper.log        log completo da última execução
  .estado.json       o que já rodou (é isto que faz o clipper pular etapas)
  _trabalho/         descartável
```

---

## Problemas comuns

**"não encontrei o executável 'ffmpeg'"** — instale com o winget acima e abra um
terminal **novo**. Ou aponte direto: `$env:CLIPPER_FFMPEG="C:\caminho\ffmpeg.exe"`.

**A transcrição parece travada** — não está. `medium` na CPU roda a 0,685× a
duração do áudio e só escreve o arquivo no fim. Acompanhe por `clipper.log`.

**"o preset pede uma fonte que não está instalada"** — troque de preset
(`--preset clean-branco`) ou instale a fonte.

**Quero refazer só uma parte** — `--force` refaz apenas o estágio que dá nome ao
subcomando: `clipper select <entrada> --force` custa 0,1 s e não rebaixa 1 GB de
vídeo de novo.

**Mudei o preset e nada mudou** — mudou sim, na próxima rodada: o clipper compara
a impressão digital do preset. Se o clipe não refez, o que você editou não afeta
pixel nenhum.
