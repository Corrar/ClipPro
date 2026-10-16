# Relatório — pedido de 15/10: ClipPro operacional na nuvem (RULINGS §24)

Base: `9286215`. **Nenhum código alterado.**

## 1. Resposta à pergunta: "já está na Vercel? já tem painel moderno?"

**Na Vercel está só o site de apresentação**, não o produto.

- Projeto `clippro`: produção `READY` em https://clippro-three.vercel.app/,
  publicada do commit `2f3ef4f` (pasta `site/`, HTML estático). Produção
  pública, previews com login (o S1 do `PENDENCIAS.md` segue aberto).
  Conferido agora pela API da Vercel.
- O site diz "Roda no seu Windows: nenhum vídeo sai do seu computador"
  (`site/index.html:7`, `:9`, `:860`, `:1217`).

**O painel existe, mas é local e simples.**

- Roda só em `127.0.0.1:8765`, com FastAPI e HTML/CSS/JS sem framework, em
  tema escuro.
- **Tela "novo vídeo":** link ou arquivo, quantos cortes, visual, modelo de
  transcrição e o que procurar.
- **Tela do trabalho:** trilha Baixar → Transcrever → Selecionar → Renderizar
  com progresso ao vivo. Cada corte tem player, nota, gancho, Baixar,
  Re-renderizar e Copiar gancho.
- Prints tirados nesta sessão, com o painel rodando aqui.

**O que falta para ser "estilo OpusClip/cut.pro":**

- conta e login;
- créditos;
- rodar no servidor;
- editar no navegador (legenda, aparar, linha do tempo);
- nota explicada;
- publicar direto.

O núcleo (achar o momento, dar nota, recortar em 9:16, legendar) **já existe**
e roda bem: 44/0/0 e 13/0/0 com as provas físicas, em Linux, nesta sessão.

## 2. O pedido, como o executor o leu

Um serviço na nuvem:

1. a pessoa abre o ClipPro e entra ou cria a conta;
2. vê um menu de opções e escolhe "gerar clipe";
3. cola o link;
4. o servidor baixa, transcreve, escolhe, corta e edita o vídeo;
5. os clipes ficam prontos para baixar.

Tudo isso é cobrado em créditos, que a pessoa compra.

## 3. ⚠ Colisões entre o pedido e o que existe

| # | Colisão | Consequência |
|---|---|---|
| C1 | **Revoga o §17 Q3 = B** ("o modo padrão continua 100% local") e a promessa do README e do site no ar. | O site passa a prometer o contrário do produto (N9). |
| C2 | **A Vercel sozinha não roda o motor.** As funções da Vercel têm teto de duração em minutos. O motor gasta **~47 min de CPU num vídeo de 1 h** (README: transcrição 0,685× o áudio em 12 núcleos; render ~1,2× cada clipe). Além disso, ffmpeg, faster-whisper, mediapipe e opencv pesam demais para uma função. | É preciso uma **máquina de processamento ("worker") com fila**, separada do site (N2). |
| C3 | **"Cola o link" no servidor:** (a) o YouTube costuma bloquear download feito de IP de datacenter, pedindo para confirmar que não é um robô; (b) o `requirements.txt` limita o yt-dlp a "vídeo PRÓPRIO do usuário"; num serviço público, o ClipPro baixa vídeo de terceiros a pedido de quem paga. | Termos de uso e direito autoral. O envio do arquivo contorna (a) (N4). |
| C4 | **A seleção hoje tem modo manual** (copiar o prompt num chat). | Na nuvem, a seleção vai pela API da Anthropic, paga pelo ClipPro a cada vídeo. |
| C5 | **Cada vídeo custa dinheiro de verdade:** máquina, armazenamento, tráfego e API. | O preço do crédito tem de cobrir esse custo. **O preço é do Bruno**; o executor mede o custo real no primeiro lote. |
| C6 | **Conta e pagamento trazem obrigações:** dados pessoais (LGPD), termos de uso, política de privacidade, CNPJ e nota fiscal. | Responsabilidade do dono. O executor pode redigir rascunhos, não dar parecer jurídico (N10). |
| C7 | **O F8a foi desenhado para modelos numa pasta local.** Num serviço com contas, o modelo do usuário vira registro da conta no banco. | Parte das Q1–Q19 do F8a muda. As do **motor** (Q1–Q5, Q10, Q11, Q16, Q17) valem nos dois mundos (N8). |
| C8 | **Escala do trabalho:** é um produto novo em cima do motor. Envolve app com contas, banco, fila, worker, armazenamento, pagamento e um painel de administração. | Várias fases (lotes), não um lote só (N8). |

Ponto a favor, medido nesta sessão: **o motor já roda em Linux**, que é o
sistema dos servidores. As duas suítes passaram com as provas físicas neste
container.

## 4. Perguntas ao arquiteto

**N1. Local × nuvem.**

| | |
|---|---|
| **A** | A nuvem vira o produto; o local continua como ferramenta interna e de teste, **com o mesmo motor**. |
| B | Só a nuvem; o local é abandonado. |
| C | Os dois são produto: local grátis e offline, nuvem paga. |

Recomendação **A**. O worker chama as mesmas funções do `clipper`, como o
painel já faz, e as provas físicas continuam valendo.

**N2. Onde roda o processamento pesado.**

| | |
|---|---|
| **A** | Vercel para o app (login, telas, pagamento) + worker separado com fila (servidor Linux com o motor em contêiner). |
| B | Vercel + Vercel Sandbox como worker (tudo num fornecedor; teto de tempo e custo por plano a medir antes). |
| C | Tudo num servidor próprio, sem a Vercel no app. |

Recomendação **A**: dá para trocar o worker depois (Sandbox, servidor com GPU)
sem mexer no app.

**N3. Transcrição na nuvem.**

| | |
|---|---|
| **A** | O mesmo faster-whisper, na CPU do worker (mais barato, mais lento: ~0,7× a duração em 12 núcleos). |
| B | Worker com GPU (muito mais rápido, mais caro). |
| C | API externa de transcrição (paga por minuto; o áudio vai para mais um fornecedor). |

Recomendação **A** no primeiro lote. Com o custo e a espera medidos, decidir
GPU com números.

**N4. Entrada.**

| | |
|---|---|
| **A** | Link **e** envio de arquivo. Os termos de uso exigem que a pessoa tenha direito sobre o vídeo, e o envio é o caminho quando o link falhar. |
| B | Só envio de arquivo. |
| C | Só link. |

Recomendação **A**.

**N5. Login.**

| | |
|---|---|
| **A** | E-mail e senha + "entrar com Google". |
| B | Só Google. |
| C | Só e-mail (senha ou link mágico). |

Recomendação **A**.

**N6. Pagamento.** Depende de CNPJ e de onde você já tem conta.

- Stripe (cartão e Pix);
- Mercado Pago (Pix e cartão);
- outro.

Recomendação: **o que você já usa**. Diga qual.

**N7. Crédito.**

| | |
|---|---|
| **A** | 1 crédito = 1 minuto de vídeo enviado (o modelo do OpusClip, pelo material público). O custo do motor cresce com a duração, e a transcrição domina. |
| B | 1 crédito = 1 clipe gerado. |
| C | Outro. |

Recomendação **A**. Os **números** são seus: créditos grátis no cadastro e
preço de cada pacote. Até lá, os valores ficam configuráveis e nenhum preço
aparece em público.

**N8. Fila e fases.**

| | |
|---|---|
| **A** | O F6.1 fecha como está (Windows + merge). A nuvem vira a próxima fase. O F8a é redesenhado dentro dela: as perguntas do motor valem, e "modelos do usuário" vira "modelos da conta". |
| B | O F8a (local) termina antes; depois vem a nuvem. |
| C | A nuvem passa na frente de tudo, inclusive do merge do F6.1. |

Recomendação **A**, com estas fases (cada uma termina com prova e PARE):

- **N-1 Motor na nuvem:** worker + fila + armazenamento. Prova: um vídeo vira
  clipes no servidor, com custo e tempo medidos.
- **N-2 App:** contas e as telas entrar, gerar clipe, meus vídeos e clipes.
- **N-3 Créditos:** saldo, débito por vídeo, compra e devolução de crédito
  quando o processamento falha.
- **N-4 Lançamento:** termos, privacidade e o site atualizado.
- **Depois:** editor no navegador, nota explicada (o F9), publicação direta.

**N9. O site no ar promete "nenhum vídeo sai do seu computador".**

| | |
|---|---|
| A | Tirar a frase já. |
| **B** | Manter enquanto o produto é local (é verdade hoje) e trocar no lançamento (N-4). |

Recomendação **B**.

**N10. Jurídico** (não é escolha de letra). CNPJ, termos de uso e política de
privacidade (LGPD): quem cuida? O executor pode redigir os rascunhos.

## 5. Folha de resposta

Com as recomendações (troque o que discordar e complete N6, N7 e N10):

```
N1 A, N2 A, N3 A, N4 A, N5 A, N6 <qual>, N7 A, N8 A, N9 B
créditos grátis: <quantos>   N10: <quem>
```

Respondidas no RULINGS §25 e §26: N1 A, N2 A, N3 A, N4 A, N5 A, N6 Mercado
Pago, N7 A, N8 A, N9 B, 300 créditos grátis, N10 "sem CNPJ; redija, eu
reviso". Hospedagem: "tudo de forma gratuita, free tier" (§6 abaixo).

## 6. "Tudo de forma gratuita, free tier" — o que os fatos dizem

Verificado em 15/10/2026 (fontes no fim desta seção).

| # | Fato | Consequência |
|---|---|---|
| Z1 | **O plano grátis da Vercel (Hobby) é só para uso pessoal e não comercial.** Cobrar dos visitantes exige o plano Pro ou o Enterprise, segundo a página do plano Hobby e o guia de uso justo da Vercel. A redação mais nova deve ser confirmada. | Dá para construir e testar no grátis. **Vender créditos no Hobby viola os termos**: antes da N-3, Pro (pago) ou outro host. |
| Z2 | **Processamento grátis é pequeno.** O maior servidor grátis conhecido, o Oracle Always Free ARM, **caiu em 2026 de 4 núcleos/24 GB para 2 núcleos/12 GB** (as fontes divergem na data). O Modal dá US$ 30/mês de crédito, com cartão. | Estimativa grosseira, por escala linear da medida do README (de 12 núcleos para 2): transcrição ~4× a duração do vídeo. **Os 300 min grátis de UMA conta ≈ 20 h de servidor**; um servidor grátis atende ~1 cadastro novo por dia. A N-1 mede o número real. |
| Z3 | **A IA que escolhe os cortes (API da Anthropic) não tem plano grátis**: é paga por uso. | O único jeito "grátis" é trocar de fornecedor (ex.: plano grátis do Google Gemini, com limites e uso dos dados pelo Google) ou tirar a IA. |
| Z4 | **Vídeo é pesado:** 29 min = 1,0 GB no download medido (README). Armazenamento grátis é da ordem de poucos GB. | O vídeo original é apagado logo após o processamento; ficam só os clipes, com prazo de validade. |

**A favor, medido nesta sessão:** todas as bibliotecas do motor têm pacote
pronto para servidor ARM com Python 3.13. O `pip download` para `aarch64`
achou mediapipe, ctranslate2, onnxruntime, av, opencv, numpy e pillow. Isso
prova que instalam; que rodam, só a N-1 prova.

### Perguntas

**G1. Grátis até onde.**

| | |
|---|---|
| **A** | N-1 e N-2 em planos grátis, como **beta fechado**: só convidados, sem cobrança. Antes da N-3, decidir os custos com os números medidos. |
| B | Abrir ao público já no grátis (fila longa; cobrar no Hobby viola os termos da Vercel). |

Recomendação **A**.

**G2. A IA que escolhe os cortes.**

| | |
|---|---|
| **A** | API da Anthropic paga por uso, com **teto de gasto mensal** definido pelo Bruno. É a que o motor já usa e que as provas cobrem. |
| B | Plano grátis do Google Gemini: troca o fornecedor no motor, tem limites diários e o Google pode usar os dados. |
| C | Sem IA na nuvem (seleção pior). |

Recomendação **A**.

**G3. Servidor de processamento no beta.**

| | |
|---|---|
| A | Oracle Always Free: 2 núcleos ARM, grátis, pede cartão para verificar; lento. |
| B | Modal: US$ 30/mês de crédito grátis; pede cartão. |
| **C** | **O PC Windows do Bruno como servidor do beta.** Ele busca os trabalhos na fila da nuvem por conexão de saída, sem abrir porta no roteador. |

Recomendação **C**:

- é grátis;
- é a máquina mais rápida disponível (12 núcleos, medida do README);
- o motor já é provado nela;
- o IP de casa escapa do bloqueio que o YouTube faz em datacenter (C3).

Contras: o PC precisa estar ligado, e os vídeos dos convidados passam por ele
(os termos do beta dizem isso). O worker nasce portátil, em contêiner, para
mudar para um servidor pago quando a venda começar.

**G4. Começar a N-1 antes do merge do F6.1?** O F6.1 espera as provas no
Windows (W1–W5 do `PENDENCIAS.md`).

| | |
|---|---|
| **A** | Sim, neste branch, como foi com o F8a (§20). |
| B | Não; esperar o merge. |

Recomendação **A**.

**Fontes:**

- [Vercel — plano Hobby](https://vercel.com/docs/plans/hobby)
- [Vercel — uso justo](https://vercel.com/docs/limits/fair-use-guidelines)
- [InfoQ — limites do free tier da Oracle](https://infoq.com/news/2026/07/oracle-cloud-free-tier-limits/)
- [terminalbytes — mudanças de 2026](https://terminalbytes.com/oracle-cloud-free-tier-changes-2026)
- [freetier.co — Modal](https://freetier.co/directory/products/modal)
- [morphllm — preços do Modal](https://www.morphllm.com/modal-pricing)

PARE aqui.
