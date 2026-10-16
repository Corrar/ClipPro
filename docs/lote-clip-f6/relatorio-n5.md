# Relatório da N-5 — design do app (RULINGS §30)

Diretiva do Bruno (16/10/2026): *"Melhore o design e layout, ao escolher o
modelo do clipe, deixe mais profissional, o app esta muito com cara de IA"*.
Decidida pela delegação do §29. O comportamento provado (créditos, envio,
rotas, segurança, CSP sem terceiros) não mudou.

## 1. O que saiu, e por quê

O que se lia como "cara de IA" era a moldura temática e não o conteúdo:

| Saiu | Entrou |
|---|---|
| Claquete listrada com "CENA 02" | Compositor neutro, em seções, com barra de ação fixa no pé |
| Trilha perfurada de película em cada item da lista | Lista de projetos em tabela, com ícone de estado |
| Pacote em forma de ingresso (picote, furos) | Cartão de pacote simples |
| Rótulos em fonte de terminal, caixa alta e espaçada | Archivo em tudo, caixa normal |
| Títulos em Anton caixa alta ("SEUS ROLOS") | Títulos em peso 600–650 ("Projetos") |
| REC piscando, varredura amarela, brilho amarelo nos botões | Indicador de carregamento discreto; amarelo só em ação e estado |
| Celular inclinado com rosto desfocado de mentira | Vitrine com três modelos reais, animados |
| Jargão de cinema ("rolos", "ilha de edição") | "Projetos", "clipes" |
| Botão "Sair" solto no topo | Menu da conta (avatar com a inicial do e-mail) |

## 2. A escolha do modelo

A galeria mostra cada modelo como o motor o desenha, e não uma ilustração:

- **Medidas do preset.** A tabela `PREVIAS` do `app.js` é gerada dos presets
  de fábrica (`python provas/prova_n5.py --gerar`). Ela traz a posição e o
  tamanho da legenda, o cartão de 75%, a pílula do título, a barra de
  progresso, o degradê, as cores e o contorno, todos em pixels do canvas
  1080×1920. O CSS converte com `--u = 100cqw / 1080`. A N5-E1 derruba a
  prova se alguém mudar um preset sem regenerar a tabela.
- **Karaokê com a regra do motor** (`legendas._bloco_palavra`):
  - cada palavra passa de "por falar" para "acesa" e depois para "falada";
  - pop de 112% só nos modelos que têm pop;
  - palavra curta, abaixo de `destaque_minimo_letras`, acende sem destaque.
- **O quadro do vídeo do próprio usuário.** Ao escolher um arquivo, o
  navegador lê um quadro dele e as quatro prévias passam a usá-lo. O quadro é
  lido no aparelho de quem envia e não sai dele.
- A prévia escolhida e a que está sob o mouse animam; as outras ficam
  paradas, mostrando as três cores. Com "reduzir movimento" ligado no
  sistema, nada anima.

Telas: `docs/nuvem/telas/` 1–8. A 7 mostra a galeria sem vídeo; a 8 mostra
a galeria com o quadro do vídeo.

## 3. Colisões e limites (destacados)

1. **Fontes fora do Windows.** Impact, Segoe UI e Bahnschrift são da
   Microsoft e não podem ir no app. No Windows, a prévia usa as fontes de
   verdade. No Mac, no Android e no Linux, entram Anton e Archivo, e a prévia
   fica aproximada. A geometria e as cores continuam exatas.
2. **Pedido por link usa fundo neutro, sem a miniatura do vídeo.** Mostrar a
   miniatura do YouTube exigiria carregar `i.ytimg.com`, um terceiro. Hoje o
   app não pede nada a terceiros: isso é provado (N2-F2) e está dito na
   Política de privacidade. **Fica como pergunta ao Bruno (Q-N5-1)**; a
   recomendação do executor é manter como está.
3. **Codec.** O quadro do vídeo depende de o navegador decodificar o arquivo:
   - Chrome, Edge e Safari decodificam H.264;
   - um `.mov` HEVC do iPhone, no Chrome do Windows, pode não decodificar;
   - nesse caso a prévia fica com o fundo neutro, sem erro, e o envio segue
     normal.

   O Chromium do Playwright não tem H.264, por isso a N5-F1 usa um vídeo de
   teste em VP9.
4. **A prévia é o layout, não o filme.** Ficam de fora: o zoom contínuo, o
   punch-in, a entrada do título e o gancho dos 3 primeiros segundos. O
   enquadramento da prévia é o centro do quadro; o motor segue o rosto.
5. O botão "Copiar legenda do post" virou **"Copiar legenda"**, com o texto
   completo na dica do botão.
6. A JetBrains Mono saiu do app (`app/fontes/`). O `relatorio-n2.md`, que a
   cita, fica como registro do que a N-2 entregou.

## 4. Provas

`provas/prova_n5.py` espelha a N-2: `main(argv)`, sem pytest, sem
dependência nova.

| | |
|---|---|
| **N5-E1** | a tabela `PREVIAS` do app é a que os 4 presets geram hoje; a galeria oferece exatamente os 4 modelos de fábrica |
| **N5-E2** | os enfeites saíram; nenhum brilho amarelo borrado; nada de fora no HTML e no CSS; sem fonte mono |
| **N5-F1** | Chromium real. Confere: <br>• a geometria de cada prévia contra o preset, com tolerância de 1,5 px; <br>• as três cores e o pop, nas prévias paradas; <br>• a regra da palavra curta; <br>• a animação passando para o modelo escolhido; <br>• o quadro do vídeo entrando nas prévias, e saindo ao voltar para Link; <br>• o pedido levando o modelo escolhido; <br>• "reduzir movimento"; <br>• 2 colunas no celular; <br>• nenhum erro de JavaScript; <br>• nada pedido a terceiros; <br>• **tudo sob a CSP de produção do `vercel.json`**, com só os hosts trocados pelos falsos |

A N2-F2 e a N3-F2 foram ajustadas aos seletores novos e conferem o mesmo
comportamento de antes. A N2-F2 ganhou uma conferência: o menu da conta
mostra o e-mail de quem entrou.

**Mutantes: 11 de 11 mordem.** Cada um quebra uma coisa e a prova acusa:
1. o tamanho da legenda;
2. um modelo fora da fábrica;
3. o cartão deslocado;
4. a legenda na altura errada;
5. a cor da palavra falada;
6. o destaque numa palavra curta;
7. o quadro do vídeo que não entra;
8. a animação com movimento reduzido;
9. as ações do clipe sumindo;
10. a volta do brilho amarelo;
11. um estilo inline, que a CSP de produção bloqueia.

**Placar no Linux:**

| Suíte | Passaram | Pularam | Falharam |
|---|---|---|---|
| N-5 | 3 | 0 | 0 |
| N-2 | 7 | 0 | 0 |
| N-3 | 6 | 0 | 0 |
| N-1 | 16 | 1 (N-F4, contas reais) | 0 |
| F6.1 | 13 | 0 | 0 |
| F6 | 44 | 0 | 0 |

### No Windows do Bruno

```
git fetch
git checkout claude/loving-newton-bykd21
git pull
.venv\Scripts\python provas\prova_n5.py
```

As estruturais (N5-E1, N5-E2) rodam só com o repositório. A N5-F1 precisa de
Node, do pacote `playwright` e do ffmpeg; sem eles, ela aparece como
**pendente**. As prévias com as fontes reais da Microsoft só se veem no
Windows, quando o app estiver no ar.
