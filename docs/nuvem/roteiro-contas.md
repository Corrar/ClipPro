# Roteiro — contas da nuvem do ClipPro (fase N-1)

Para o Bruno, no Windows. Decisões de origem: RULINGS §27 e §28. Tudo em plano
grátis.

> **Chave secreta não vai para o chat nem para o repositório.** Elas ficam só
> nas variáveis de ambiente do seu PC (passo 4). Se uma chave vazar, apague-a
> no painel do serviço e crie outra.

## 1. Anthropic: teto de gasto (G2)

1. Em https://console.anthropic.com, abra **Settings → Limits** e defina o
   **limite de gasto mensal**. É o teto do §27; o código não consegue impor
   esse limite por você.
2. Em **API Keys**, crie uma chave só para o worker. Ela vira
   `ANTHROPIC_API_KEY` no passo 4.

## 2. Supabase: fila, contas e login

1. Crie a conta em https://supabase.com e um **New project**. Região
   sugerida: **South America (São Paulo)**. Guarde a senha do banco.
2. Abra **SQL Editor → New query**, cole o conteúdo inteiro de
   `nuvem/supabase/001_fila.sql` e clique em **Run**. A migração pode ser
   rodada de novo sem perigo.
3. Em **Project Settings → API Keys**, copie:
   - a **URL do projeto** (`https://<projeto>.supabase.co`) → `SUPABASE_URL`;
   - a **Secret key** (`sb_secret_…`) → `SUPABASE_SECRET_KEY`. A chave
     `service_role` antiga também funciona.

O plano grátis **pausa o projeto após 7 dias parado**. Se isso acontecer,
basta reativá-lo no painel.

## 3. Cloudflare R2: vídeos e clipes

1. Crie a conta em https://dash.cloudflare.com e abra **R2**. A Cloudflare
   pode pedir um cartão para ativar o R2, mesmo no plano grátis (10 GB). Isso
   aparece na tela de ativação.
2. **Create bucket** com o nome `clippro` (localização automática). O nome
   vira `R2_BUCKET`.
3. Em **Manage R2 API Tokens → Create API token**, use a permissão **Object
   Read & Write**, só para o bucket `clippro`. Copie:
   - o **Access Key ID** → `R2_ACCESS_KEY_ID`;
   - o **Secret Access Key** → `R2_SECRET_ACCESS_KEY` (aparece uma vez só);
   - o **Account ID**, que está no endereço
     `https://<account-id>.r2.cloudflarestorage.com` → `R2_ACCOUNT_ID`.

## 4. Variáveis no Windows

No **Prompt de Comando** (cmd), uma linha por variável, com os seus valores:

```
setx ANTHROPIC_API_KEY "sk-ant-..."
setx SUPABASE_URL "https://<projeto>.supabase.co"
setx SUPABASE_SECRET_KEY "sb_secret_..."
setx R2_ACCOUNT_ID "<account-id>"
setx R2_ACCESS_KEY_ID "<access-key-id>"
setx R2_SECRET_ACCESS_KEY "<secret-access-key>"
setx R2_BUCKET "clippro"
```

O `setx` vale para os terminais abertos **depois** dele: feche e abra o cmd.

## 5. Prova contra as contas reais

No terminal novo, na pasta do ClipPro:

```
git fetch
git checkout claude/loving-newton-bykd21
git pull
set CLIPPRO_PROVA_NUVEM=1
.venv\Scripts\python provas\prova_n1.py --fisicas
```

O que esperar:

- **N-F4** sobe um vídeo de teste para o R2, cria um trabalho no Supabase,
  roda o worker de verdade e confere o clipe no R2. No fim, apaga o que criou.
  A IA nessa prova é a **falsa**: não gasta crédito da Anthropic.
- **N-F3** pula no Windows (precisa de um Postgres de teste); ela já passou no
  servidor da sessão.

Mande o placar final (a linha "X passaram, Y pularam, Z falharam").

## 6. Ligar o worker (depois da N-2)

Quando o app (N-2) estiver criando pedidos:

```
.venv\Scripts\python -m worker --nuvem
```

Deixe o terminal aberto: o PC é o servidor do beta (G3). `Ctrl+C` devolve à
fila o trabalho em andamento.

---

## 7. N-2: o app (login, pedidos, clipes)

Depois dos passos 1 a 5.

### 7.1 Banco

No **SQL Editor** do Supabase, cole e rode `nuvem/supabase/002_contas.sql`
(depois do 001). A migração pode ser rodada de novo sem perigo.

### 7.2 Login por e-mail

Em **Authentication → Sign In / Providers → Email**, deixe **"Confirm email"
ligado**. O convite só libera depois da confirmação.

### 7.3 Entrar com Google

1. No Google Cloud Console (https://console.cloud.google.com), em **APIs e
   serviços → Credenciais → Criar credenciais → ID do cliente OAuth**, escolha
   o tipo **Aplicativo da Web**.
2. Em **URI de redirecionamento autorizado**, use
   `https://<projeto>.supabase.co/auth/v1/callback`.
3. Cole o **Client ID** e o **Client Secret** em **Supabase → Authentication →
   Sign In / Providers → Google**.

### 7.4 Endereços do app

Em **Authentication → URL Configuration**:

- **Site URL** = o endereço do app na Vercel (passo 7.6), por exemplo
  `https://clippro-app.vercel.app`;
- **Redirect URLs**: o mesmo endereço seguido de `/**`.

### 7.5 Chave pública e convites

1. Em **Project Settings → API Keys**, copie a **Publishable key**
   (`sb_publishable_…`). Ela vai para a Vercel como `SUPABASE_PUBLISHABLE_KEY`.
   Esta é pública por natureza; a secreta **nunca** vai para a Vercel.
2. **Convites:** em **Table Editor → convites → Insert row**, um e-mail por
   linha, **em minúsculas**. Ou pelo SQL Editor:

   ```
   insert into convites (email) values ('seu-email@gmail.com');
   ```

   Comece pelo seu.

### 7.6 Projeto na Vercel

1. Em https://vercel.com/new, importe `Corrar/ClipPro`:
   - Project Name: **clippro-app**;
   - Root Directory: **./** (a raiz);
   - Framework: **Other**.
2. Em **Environment Variables**, cadastre:
   - `SUPABASE_URL`;
   - `SUPABASE_PUBLISHABLE_KEY`;
   - `R2_ACCOUNT_ID`;
   - `R2_ACCESS_KEY_ID` e `R2_SECRET_ACCESS_KEY` — de uma **segunda chave do
     R2**, só para o app, com Object Read & Write no bucket `clippro`. Assim dá
     para revogar uma sem derrubar a outra;
   - `R2_BUCKET` = `clippro`.
3. Em **Settings → Git → Production Branch**, coloque
   `claude/loving-newton-bykd21`. O `master` não tem o app, e continua
   intocado até o seu "pode fazer o merge".
4. Em **Settings → Deployment Protection**, o app precisa de **produção
   pública**: as pessoas entram nele. Deixe a proteção só nos previews. É uma
   decisão sua.
5. Faça o **Deploy**. O site público (projeto `clippro`) não muda.

### 7.7 CORS do R2

O navegador envia o vídeo e lê o texto do post direto do R2. Em **R2 →
clippro → Settings → CORS Policy**, use (troque pelo endereço do passo 7.6):

```
[
  {
    "AllowedOrigins": ["https://clippro-app.vercel.app"],
    "AllowedMethods": ["GET", "PUT", "HEAD"],
    "AllowedHeaders": ["content-type"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

### 7.8 Primeira volta completa

1. Abra o app, **crie a conta** com o e-mail convidado e **confirme** pelo
   link do e-mail. O saldo deve mostrar **300 min**.
2. No PC, deixe o worker de plantão: `.venv\Scripts\python -m worker --nuvem`.
3. No app, cole um link **seu**, com 2 a 5 minutos, e clique em **Gerar
   cortes**. O rolo passa de "Na fila" para "Processando" e depois para
   "Pronto", e o saldo devolve o que sobrou.
4. Abra o rolo, veja e baixe um clipe.

Mande o que viu em cada passo. Se algo falhar, mande também a mensagem que
apareceu.

---

## 8. N-3: vender créditos (Mercado Pago)

Só quando for vender. Antes, as pendências V1–V6 do
`docs/lote-clip-f6/relatorio-n3.md` (preço, Vercel Pro, termos, sandbox,
nota fiscal).

### 8.1 Aplicação no Mercado Pago

1. Em https://www.mercadopago.com.br/developers, abra **Suas integrações →
   Criar aplicação** e escolha **Checkout Pro**.
2. Em **Credenciais de produção**, copie o **Access Token** (`APP_USR-…`). Ele
   vira `MP_ACCESS_TOKEN`.
3. Use primeiro as **credenciais de teste**, com contas de comprador de
   teste, e só depois as de produção.

### 8.2 Webhook

1. Na aplicação, abra **Webhooks → Configurar notificações**.
2. Em **URL de produção**, use `https://<endereço do app>/api/mp_webhook` e
   marque o evento **Pagamentos**.
3. Copie a **assinatura secreta**. Ela vira `MP_WEBHOOK_SECRET`.

### 8.3 Banco

No SQL Editor, rode `nuvem/supabase/003_compras.sql` (depois do 002).

Os pacotes são seus: **o preço é decisão sua**. Um insert por pacote, com o
preço **em centavos**:

```
insert into pacotes (id, nome, minutos, preco_centavos, ativo, ordem)
values ('p60', 'Pacote 60', 60, <PREÇO_EM_CENTAVOS>, true, 1);
```

Para tirar um pacote da loja, troque `ativo` para `false`. Para mudar o
preço, edite `preco_centavos`: quem já abriu uma compra paga o preço daquele
momento.

### 8.4 Variáveis na Vercel (projeto `clippro-app`)

- `MP_ACCESS_TOKEN`;
- `MP_WEBHOOK_SECRET`;
- `SUPABASE_SECRET_KEY` — **só agora** ela entra na Vercel, para o webhook
  confirmar as compras;
- `APP_URL` = o endereço do app, por exemplo `https://clippro-app.vercel.app`;
- `COMPRAS_ATIVAS` = `1` **só no dia de abrir as vendas**. Sem ela, a loja
  aparece fechada.

### 8.5 Conferir

1. Compre o menor pacote com uma conta de teste do Mercado Pago.
2. O app deve voltar com "Pronto: N minutos entraram no seu saldo".
3. O extrato deve mostrar a compra.

Se não entrar, veja em **Vercel → clippro-app → Logs** as linhas
`[mp_webhook]`: elas dizem o motivo (assinatura, valor ou estorno).

---

## 9. N-4: antes de abrir para mais gente

### 9.1 Prazo de guarda no R2

A Política de privacidade promete prazos; quem os cumpre é o R2. Em **R2 →
clippro → Settings → Object lifecycle rules**, crie duas regras:

- prefixo `entradas/` → **apagar objetos 3 dias** depois de enviados (o
  vídeo original);
- prefixo `resultados/` → **apagar objetos 30 dias** depois de criados (os
  clipes; o app avisa até quando cada um fica disponível).

### 9.2 Termos e privacidade

1. `app/termos.html` e `app/privacidade.html` são **rascunhos** e aparecem
   marcados como tal. Preencha os colchetes: `[NOME DO RESPONSÁVEL]`,
   `[CPF OU CNPJ]` e `[E-MAIL DE CONTATO]`.
2. Leve o texto a um advogado. Merecem atenção:
   - o direito de arrependimento de 7 dias para créditos não usados;
   - os créditos sem prazo de validade (escolha do executor, troque se
     quiser);
   - a transferência internacional (Supabase, Vercel, Anthropic).
3. Depois da revisão, tire o aviso de rascunho, o `<p class="rascunho">` no
   topo de cada página.

### 9.3 Site público

O site (`clippro-three.vercel.app`) ainda descreve a versão local ("nenhum
vídeo sai do seu computador"). Pela decisão N9 = B, ele muda **no
lançamento**, junto com o preço. Peça "atualize o site para o lançamento" e
o executor reescreve e publica.
