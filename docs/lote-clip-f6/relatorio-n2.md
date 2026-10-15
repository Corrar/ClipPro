# Relatório — N-2 "o app" (RULINGS §29, decidido por delegação)

Base: `cbadea3`. O SHA do commit que traz este relatório vai na mensagem do
checkpoint.

## 1. O que existe agora

| Peça | O que faz |
|---|---|
| `app/` | O app: entrar (e-mail e senha, Google, "esqueci a senha"), painel com a claquete "Novo corte" (link **ou** envio do arquivo direto ao R2, 4 visuais, quantos cortes, o que procurar), "Seus rolos" que se atualiza sozinho e a tela dos clipes (ver, baixar, copiar gancho, copiar a legenda do post). Mesma identidade do site. Sem build. |
| `app/vendor/` | `supabase-js` 2.117.2 embutido (sha512 conferido com o npm; licença MIT junto). |
| `app/fontes/` | Anton, Archivo e JetBrains Mono **hospedadas no próprio app** (SIL OFL 1.1, licenças junto). Nenhum pedido ao Google. |
| `api/` | `config`, `upload` e `clipes`: funções Python da Vercel, só biblioteca padrão. Lógica em `nuvem/app.py`. |
| `nuvem/` | `s3.py` (assinatura e URL pré-assinada), `rest.py` (Supabase), `app.py` (regras das rotas), `web.py` (cola HTTP). O worker usa o mesmo `s3.py`. |
| `nuvem/supabase/002_contas.sql` | Perfis, convites e movimentos de crédito; `criar_trabalho`; devolução automática; RLS. |
| `vercel.json`, `.vercelignore` | Projeto Vercel do app; lista de permissão (só `app/`, `api/`, `nuvem/`); cabeçalhos de segurança com CSP sem terceiros. |

## 2. Placar (Linux, Postgres 16 local, Chromium do Playwright)

| Prova | Resultado |
|---|---|
| `prova_n2.py --fisicas` | **7 passaram, 0 pularam, 0 falharam** |
| `prova_n1.py --fisicas` | 16 passaram, 1 pulou (N-F4, contas reais — pendente), 0 falharam |

- **N2-F1** (SQL num Postgres real), 21 conferências:
  - convite só libera e-mail confirmado, e uma vez só;
  - reserva e devolução de créditos;
  - RLS por conta;
  - colunas internas da fila escondidas;
  - o usuário não se dá créditos;
  - no máximo 3 vídeos na fila;
  - **dois pedidos simultâneos da mesma conta nunca deixam o saldo negativo**.
- **N2-F2** (interface num Chromium real), 28 conferências, de entrar até sair:
  - pedido por link e por arquivo;
  - o rolo vira "Pronto" sem recarregar;
  - a devolução aparece no saldo;
  - clipes, download com o nome certo e cópia do gancho e do post;
  - título malicioso aparece como texto;
  - celular sem rolagem lateral;
  - **nenhum pedido a terceiros**;
  - nenhum erro de JavaScript.
- **Mutantes: 13 de 13 mordem.** Cada regra foi quebrada e a prova falhou:
  - tamanho fora da assinatura;
  - tipo de arquivo livre;
  - clipe fora do prefixo;
  - configuração vazando o ambiente;
  - query codificada duas vezes;
  - URL assinada em cache;
  - XSS por `innerHTML`;
  - lista sem atualização automática;
  - fontes de volta ao Google;
  - convite sem confirmar o e-mail;
  - pedido sem trava por conta;
  - colunas da fila expostas;
  - devolução em dobro.

## 3. Achados durante a N-2 (corrigidos)

1. **O nome do arquivo no download chegaria quebrado.** A query da URL
   assinada era codificada duas vezes (`%3B` → `%253B`). A assinatura passava,
   mas o nome não. A N2-E1 guarda isso.
2. **Uma folha de fontes lenta travaria o app.** O navegador segura o
   `app.js` até a folha do Google carregar. Agora as fontes estão no próprio
   app, o que ainda tira o IP do usuário do Google (LGPD).
3. **Convite × e-mail não confirmado.** O Supabase cria o usuário antes da
   confirmação; liberar no cadastro deixaria alguém usar o e-mail de um
   convidado. Agora só libera depois da confirmação.

## 4. Decisões do executor (por delegação, §29)

- Até **10 cortes por vídeo** na tela (o contrato aceita até 20). Menos
  cortes, cortes melhores.
- **Reserva de até 600 min por pedido.** Com 300 de saldo, o primeiro pedido
  reserva tudo e o segundo espera o primeiro devolver o que sobrou. Simples e
  sem saldo negativo; no beta a fila é de uma máquina só.
- **Envio de até 2 GB** (cerca de 1 h de vídeo), com o tamanho **dentro da
  assinatura**.
- A **URL dos clipes vale 1 h** e a de envio, 15 min.
- **O app não mostra o estágio** (transcrevendo, renderizando): a fila só
  sabe "na fila / processando / pronto". Isso exige o worker reportar o
  estágio, o que fica para depois.

## 5. ⚠ Pendências e limites

| # | O quê | Quem |
|---|---|---|
| A1 | Criar as contas e configurar Auth, Google, CORS do R2 e o projeto Vercel (roteiro §7) | Bruno |
| A2 | Na Vercel, o app precisa de **produção pública** (as pessoas entram nele). O padrão do time protege tudo com login da Vercel; mudar é decisão sua (é o mesmo tipo de ajuste do S1) | Bruno |
| A3 | O código do app está no branch `claude/loving-newton-bykd21`, não no `master`. Para o beta: produção do projeto `clippro-app` apontando para esse branch (roteiro §7.6) — `master` segue intocado | Bruno |
| A4 | "Entrar com Google" e o e-mail de confirmação só podem ser provados com as contas reais | depois de A1 |
| A5 | A interface foi provada contra a nuvem falsa (regras iguais às do SQL, que foi provado num Postgres real). A primeira rodada com o Supabase de verdade é a do roteiro §7.8 | depois de A1 |

## 6. Para rodar no Windows

```
git fetch
git checkout claude/loving-newton-bykd21
git pull
.venv\Scripts\python provas\prova_n2.py --fisicas
```

No Windows, a N2-F1 (precisa de um Postgres de teste) e a N2-F2 (precisa de
Node + Playwright) **pulam**. As 5 estruturais rodam.

PARE aqui para a N-2. A N-3 (compra de créditos pelo Mercado Pago) segue pela
delegação; o **preço dos pacotes** é decisão do Bruno.
