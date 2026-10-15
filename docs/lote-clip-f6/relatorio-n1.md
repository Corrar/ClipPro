# Relatório — N-1 "motor na nuvem": o worker (RULINGS §27)

Base: `17bd568` (`claude/loving-newton-bykd21`). O SHA do commit que traz este
relatório vai na mensagem do checkpoint.

## 1. O que foi feito

Pacote novo `worker/`. Ele pega um trabalho de uma fila, roda o **mesmo motor**
do CLI e do painel e entrega os clipes num depósito.

| Arquivo | Papel |
|---|---|
| `worker/contrato.py` | O pedido que vem da nuvem, tratado como **entrada não confiável**: tipos conferidos (`"3"` não é 3), preset só por nome do catálogo, arquivo só por chave do depósito, link só `http(s)` para host público. |
| `worker/fila.py` | `FilaEmPasta`: reserva atômica por renomeação, prazo renovado por batimento, devolução quando o worker cai, 3 tentativas no máximo. |
| `worker/deposito.py` | `DepositoEmPasta`: traz o vídeo enviado (sem recopiar numa retomada) e publica MP4, capa e texto de publicação. |
| `worker/executor.py` | Um trabalho de ponta a ponta. Confere o saldo de minutos logo depois da ingestão, **antes** da transcrição, e limpa as fontes no fim. |
| `worker/__main__.py` | `python -m worker`: o laço reservar → executar → entregar. Recusa partir sem `ANTHROPIC_API_KEY`. |
| `provas/prova_n1.py` | 9 provas estruturais + 2 físicas, `main(argv)`, sem dependência nova. |

**Nada mudou no motor (`clipper/`) nem no painel (`ui/`).** `VERSAO` intocada.
O worker chama `motor.montar_estagios`/`rodar_estagios`, como `ui/jobs.py`.

Hoje fila e depósito são **pastas**: servem às provas e a uma máquina só. As
versões na nuvem implementam os mesmos verbos e dependem da **P1** (§6).

## 2. Placar (Linux, ffmpeg, venv do lockfile)

| Prova | Resultado |
|---|---|
| `prova_n1.py --fisicas` | **11 passaram, 0 pularam, 0 falharam** |
| `prova_f61.py --fisicas` | 13 passaram, 0 pularam, 0 falharam |
| `prova_f6.py --fisicas` | 44 passaram, 0 pularam, 0 falharam |

**Mutantes: 12 de 12 mordem.** Cada regra abaixo foi quebrada no código, uma
de cada vez, e a prova correspondente falhou:

- link privado aceito → N-E2
- `True` aceito como inteiro → N-E2
- DNS ignorado → N-E3
- arredondamento sem tolerância → N-E4
- reserva vencida encerrando a nova → N-E6
- tentativas infinitas → N-E6
- entrada recopiada numa retomada → N-E7
- falha que não apaga as fontes → N-E8
- worker que parte sem chave → N-E9
- sem conferência do saldo → N-F2
- sucesso que não limpa → N-F1
- worker em modo manual → N-F1

**As físicas** (N-F1, N-F2) passam pelo ponto de entrada real
(`python -m worker`) e pelo SDK real da Anthropic, apontado para a API falsa de
`provas/entrada_real.py`: nada sai da máquina e nada é cobrado. O vídeo é
sintético e fica em `_teste/out-prova-n1/`, não no vídeo da F5 (lição da Q18
do F8a).

**Medido no container** (não é o PC do Bruno), na N-F1:

- 65 s no total;
- render de 63,3 s para um clipe de 31 s;
- seleção de 1,5 s, pela API falsa;
- ingestão e transcrição reaproveitadas (a transcrição foi semeada; o lavfi
  não tem fala).

## 3. Para rodar no Windows

```
git fetch
git checkout claude/loving-newton-bykd21
git pull
.venv\Scripts\python provas\prova_n1.py --fisicas
```

## 4. Decisões do executor (declaradas, não de arquitetura)

1. **Pasta por trabalho, não por vídeo.** O painel usa "o job é o slug" porque
   tem um usuário só. Na nuvem, dois usuários com o mesmo vídeo não dividem
   pasta, seleção nem clipes.
2. **Créditos = minutos arredondados para cima**, com tolerância de 0,5 s: o
   ffprobe mede 60,04 s num vídeo de 1 min. A regra final de cobrança é da N-3.
3. **O saldo é conferido depois da ingestão**, antes do whisper (a parte cara).
   Para link, o download já aconteceu: é o preço de não perguntar a duração ao
   yt-dlp duas vezes.
4. **Limpeza.** No sucesso, a pasta inteira sai (os clipes já estão no
   depósito). Na falha, saem vídeo, áudio e bruto; ficam log, JSONs e clipes
   para diagnóstico. Apagar o vídeo enviado do depósito é papel da nuvem.
5. **Reserva:** prazo de 10 min, renovada a cada 2,5 min. Um trabalho que
   derruba o worker 3 vezes vai para `falhos/` sem crédito.
6. **IA:** modelo `haiku` (o padrão do motor). O whisper é `medium` por padrão,
   com flag do operador (`--modelo-whisper`).
7. **Windows:** a disputa por um arquivo da fila também aparece como
   `PermissionError`; a reserva trata esse erro como "outro worker levou", e a
   gravação tenta de novo por meio segundo.

## 5. ⚠ Colisões e limites

| # | O quê | Situação |
|---|---|---|
| C1 | **Fila, depósito e login da nuvem não existem.** O worker ainda não fala com a nuvem. | **P1.** |
| C2 | **O custo da IA por trabalho não é medido:** o `select.py` não guarda o `usage` (tokens) da resposta. | **P2.** |
| C3 | **Guarda de rede residual.** Um link público que **redireciona** para a rede de casa, ou um DNS que muda entre a conferência e o download, passa. | Mitigado pelo beta fechado (G1): só convidados. Fechar de vez exige mexer no yt-dlp; fica registrado. |
| C4 | **O mesmo vídeo de dois usuários é processado duas vezes.** | Custo; otimização futura (cache por vídeo). |
| C5 | **O teto de gasto da IA (G2) não é código:** fica no console da Anthropic (Limits). | Ação do Bruno antes de ligar o worker de verdade. |
| C6 | **Capacidade do PC:** 300 créditos = 5 h de vídeo ≈ **4 h de PC** por cadastro (README: 0,685× em 12 núcleos + render). | Número registrado; o beta fechado comporta poucos convidados por dia. |

## 6. Perguntas

**P1. Onde ficam, na nuvem, a fila, os arquivos e o login.** Todos grátis
(§26, G1).

| | |
|---|---|
| **A** | **Supabase** (banco para fila, contas e créditos + login com e-mail e Google) **e Cloudflare R2** (arquivos: 10 GB grátis, sem taxa quando o usuário baixa o clipe). Duas contas. |
| B | Só Supabase (banco, login e arquivos). Uma conta, mas ~1 GB de arquivos (~70 clipes de 15 MB) e o projeto **pausa após 7 dias parado**. |
| C | Só Cloudflare (banco D1 + R2). Não tem login pronto: o "entrar com Google" (N5) teria de ser construído. |

Recomendação **A**. O Supabase cobre login e banco, que é o que ele faz
melhor; o R2 cobre o que pesa. O risco da pausa fica menor porque o worker
consulta a fila o tempo todo. Isso ainda precisa ser confirmado na N-2.

**P2. Medir o custo da IA por trabalho** (C2).

| | |
|---|---|
| **A** | O estágio de seleção passa a devolver os tokens usados no resultado que entrega ao motor. Nenhum arquivo muda de formato, e o worker grava o número no resultado do trabalho. |
| B | Medir só pelo console da Anthropic (total do mês, sem separar por trabalho). |

Recomendação **A**: é o número que define o preço do crédito antes da N-3.

**Fontes (P1):**

- [Cloudflare — preços do R2](https://developers.cloudflare.com/r2/pricing)
- [automationatlas — limites grátis do Supabase em 2026](https://automationatlas.io/answers/supabase-free-tier-limits-2026/)
- [costbench — plano grátis do Supabase](https://costbench.com/software/database-as-service/supabase/free-plan/)
- [jetadmin — guia de preços do Supabase 2026](https://www.jetadmin.io/blog/supabase-pricing-2026-guide-to-plans-limits-and-real-world-costs/)

Os limites do Supabase vêm de sites terceiros e divergem entre si (500 MB ou
1 GB de arquivos). A página oficial deve ser conferida na hora de criar a
conta.

---

## 7. Segundo checkpoint — P1 e P2 (RULINGS §28)

### 7.1 O que entrou

| Arquivo | Papel |
|---|---|
| `clipper/pipeline/select.py` | **P2.** A seleção soma os tokens que a API **informa** ter cobrado (entrada, saída e cache, inclusive na ida de conserto) e devolve a soma no resultado do estágio (`uso_api`). `selecao.json` e `.estado.json` não mudam de formato; `VERSAO` intocada. |
| `worker/executor.py` | Grava `uso_api` no resultado de cada trabalho. |
| `nuvem/supabase/001_fila.sql` | Tabela `trabalhos` + 4 funções (reservar, renovar, encerrar, devolver). A reserva usa `SKIP LOCKED`; dono e tentativa são conferidos no encerramento; RLS ligado sem policy; só a chave secreta executa. Idempotente. |
| `worker/nuvem.py` | `FilaSupabase` (as 4 funções pela API REST) e `DepositoR2` (API S3 com assinatura SigV4). Só biblioteca padrão: zero dependência nova. |
| `worker/__main__.py` | `--nuvem`: as chaves vêm do ambiente, e o worker lista as que faltam. Fila fora do ar não derruba o worker; a entrega do resultado insiste por ~1 min se a rede piscar. |
| `docs/nuvem/roteiro-contas.md` | Passo a passo das contas (Anthropic, Supabase, R2) e das variáveis no Windows. |

### 7.2 Placar

| Prova | Resultado |
|---|---|
| `prova_n1.py --fisicas` (Postgres 16 local) | **16 passaram, 1 pulou, 0 falharam** — a que pulou é a N-F4, **pendente** (contas reais) |
| `prova_n1.py` (estruturais, sem Postgres, como no Windows) | 13 passaram, 0 pularam, 0 falharam |
| `prova_f6.py --fisicas` (depois da mudança na seleção) | 44 passaram, 0 pularam, 0 falharam |
| `prova_f61.py --fisicas` | 13 passaram, 0 pularam, 0 falharam |

**Conferido contra fonte externa:** a assinatura reproduz exatamente o exemplo
oficial da AWS ("GET Object", `Signature=f0e8bdb8…`). O depósito R2 roda
contra um S3 falso que **recalcula a assinatura** de cada requisição recebida.
O SQL roda num **Postgres de verdade**, com os papéis do Supabase imitados.

**Mutantes: 13 de 13 mordem.** Cada regra foi quebrada no código e a prova
correspondente falhou:

- SigV4 sem ordenar os cabeçalhos → N-E10
- R2 sem o mtime do objeto → N-E11
- R2 baixando sempre → N-E11
- Bearer com a chave nova → N-E12
- pedido torto não recusado → N-E12
- `--nuvem` sem conferir as variáveis → N-E13
- SQL sem `SKIP LOCKED` → N-F3
- SQL encerrando sem conferir o dono → N-F3
- SQL sem o revoke do anon → N-F3
- SQL com tentativas infinitas → N-F3
- SQL sem RLS → N-F3
- seleção sem contar os tokens → N-F1
- (e os 12 do primeiro checkpoint seguem valendo)

**Um mutante sobreviveu na primeira rodada, e a prova foi corrigida.** Tirar
o `SKIP LOCKED` **não** duplica reserva; o que ele garante é que um worker não
espera o outro. A N-F3 passou a medir isso: com uma sessão segurando a
reserva, a outra pega outro trabalho em **0,06 s**. Sem `SKIP LOCKED`,
esperou **1,57 s** e a prova falhou.

### 7.3 Decisões do executor (declaradas)

1. **A chave secreta do Supabase passa por cima do RLS.** O worker só chama
   as 4 funções, que conferem dono e tentativa. A chave fica no PC do Bruno
   (G3).
2. **Formato da chave.** A chave nova (`sb_secret_…`) vai só no cabeçalho
   `apikey`; a `service_role` antiga vai também no `Authorization`, como
   manda a documentação do Supabase.
3. **No Supabase, devolver a reserva vencida acontece dentro de
   `reservar_trabalho`**, na mesma transação: não há janela entre devolver e
   reservar.
4. **A regra das 3 tentativas existe nos dois lados** (pasta e SQL), com a
   mesma mensagem. A N-E6 cobre um lado e a N-F3 cobre o outro.
5. **Tokens só aparecem no sucesso.** Se a seleção falhar depois de chamar a
   API (resposta inválida mesmo após o conserto), o gasto daquela tentativa
   não chega ao resultado. O C2 fica coberto em parte.
6. **A N-F4 foi escrita, mas não executada:** não há contas. O primeiro uso
   real dela é no Windows do Bruno. Ela recusa rodar se a fila real tiver
   outros pendentes e apaga o que criou.

### 7.4 ⚠ Pendências

| # | Pendência | Quem |
|---|---|---|
| K1 | Criar as contas e rodar a N-F4 (`docs/nuvem/roteiro-contas.md`) | Bruno |
| K2 | Teto de gasto mensal no console da Anthropic (C5) | Bruno |
| K3 | O worker consultando a fila conta como "atividade" para o Supabase não pausar? | executor, na N-2 |
| K4 | Ninguém insere trabalhos na tabela ainda: é o app (N-2) | N-2 |

PARE aqui. A N-1 fecha com a N-F4 verde no Windows. A N-2 (app com login e
telas) abre com a palavra do Bruno e traz as perguntas dela.
