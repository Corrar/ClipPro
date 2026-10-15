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
