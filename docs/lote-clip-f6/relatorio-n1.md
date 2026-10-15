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

PARE aqui.
