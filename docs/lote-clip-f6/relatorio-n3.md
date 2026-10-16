# Relatório — N-3 "compra de créditos" (RULINGS §29.5, decidido por delegação)

Base: `7251960`. O SHA do commit que traz este relatório vai na mensagem do
checkpoint.

## 1. O que existe agora

| Peça | O que faz |
|---|---|
| `nuvem/supabase/003_compras.sql` | `pacotes` (do Bruno; o app só mostra os ativos); `compras` com o **preço congelado** na abertura; `iniciar_compra` (usuário logado); `confirmar_compra`, **a única porta que credita**, só pela chave secreta, idempotente. Valor diferente do preço não credita; um pagamento não credita duas compras; no máximo 5 compras abertas por hora. |
| `nuvem/mercadopago.py` | Preferência do Checkout Pro; assinatura do webhook pelo **manifest oficial** (`id:…;request-id:…;ts:…;`, HMAC-SHA256); consulta do pagamento na API. Só biblioteca padrão. |
| `api/comprar.py` | Abre a compra e devolve o link do Mercado Pago. |
| `api/mp_webhook.py` | Aviso de pagamento: confere a assinatura, **consulta o pagamento na API** (status aprovado, BRL, valor exato) e só então credita. |
| `app/` | Tela **Créditos**: saldo, pacotes como ingressos de cinema, preço por minuto e **extrato** (bônus, reservas, devoluções, compras). Tela de **volta do pagamento**, que acompanha a compra até os minutos entrarem. O saldo no topo leva a Créditos. |

**Tudo desligado por padrão** (`COMPRAS_ATIVAS`). Com a chave desligada, a
loja diz que abre no lançamento, e nenhuma chamada vai ao Mercado Pago.

## 2. Placar

| Prova | Resultado |
|---|---|
| `prova_n3.py --fisicas` | **6 passaram, 0 pularam, 0 falharam** |
| `prova_n2.py --fisicas` | 7 passaram, 0 pularam, 0 falharam |

- **N3-F1** (Postgres real): 16 conferências. Inclui: o usuário não confirma
  a própria compra; webhook repetido não credita de novo; valor divergente,
  pagamento recusado e pagamento reaproveitado não creditam; preço congelado;
  extrato; freio de 5 compras.
- **N3-E1..E4**, contra um Mercado Pago falso que **assina o aviso como o de
  verdade**. A N3-E3 roda o webhook em 13 cenários:
  - aprovado;
  - aviso repetido;
  - assinatura adulterada;
  - assinatura de outro segredo;
  - valor menor que o preço;
  - Pix pendente;
  - pagamento recusado;
  - moeda diferente de BRL;
  - pagamento de outra loja;
  - Mercado Pago fora do ar (502), e a nova tentativa credita;
  - aviso que não é de pagamento;
  - vendas desligadas.
- **N3-F2** (Chromium real): Créditos → Comprar → checkout falso → volta →
  "60 minutos entraram" → saldo 360 → extrato. Com a loja fechada, nada vai
  ao Mercado Pago.
- **Mutantes: 11 de 11 mordem.** Cada regra de dinheiro foi quebrada e a
  prova falhou:
  - assinatura ignorada;
  - aprovação sem olhar o status;
  - outra moeda aceita;
  - erro permanente virando retentativa infinita;
  - chave de ligar ignorada;
  - manifest errado;
  - valor errado creditado;
  - usuário confirmando a própria compra;
  - sem idempotência;
  - preço do pacote atual em vez do congelado;
  - loja aberta com as vendas desligadas.

Os preços que aparecem nas provas e nos prints (R$ 19,90 e R$ 79,90) são
**valores de teste**, não uma sugestão de preço.

## 3. Decisões do executor (por delegação)

- **API de Preferências**, e não a de Orders que o Mercado Pago recomenda
  para integrações novas. A de Preferências segue suportada e é a forma mais
  direta do Checkout Pro. Migrar fica como melhoria.
- **Erro permanente** (valor divergente, pagamento reaproveitado) responde
  200 e vai para o log da função: repetir não conserta. **Erro passageiro**
  (rede, banco) responde 500/502, e o Mercado Pago tenta de novo.
- **Estorno ou chargeback** é registrado no log, **sem débito automático**
  no beta.
- O webhook usa a **chave secreta do Supabase na Vercel**, só para
  `confirmar_compra`.

## 4. ⚠ Antes de ligar as vendas (`COMPRAS_ATIVAS=1`)

| # | O quê | Quem |
|---|---|---|
| V1 | **Preço de cada pacote**, com o custo medido no beta (tokens por vídeo, §28; tempo de PC) | Bruno |
| V2 | **Plano Pro da Vercel**: o Hobby proíbe uso comercial (§26) | Bruno |
| V3 | **Termos de uso e política de privacidade** publicados (N-4) | executor redige, Bruno revisa |
| V4 | **Conta e credenciais do Mercado Pago**, e o webhook com assinatura secreta (roteiro §8) | Bruno |
| V5 | **Teste no sandbox do Mercado Pago**, com as credenciais de teste. Confere de ponta a ponta, inclusive que o aviso chega com `x-signature` | Bruno + executor |
| V6 | Nota fiscal e enquadramento (CPF/CNPJ) para vender | Bruno |

## 5. Para rodar no Windows

```
git fetch
git checkout claude/loving-newton-bykd21
git pull
.venv\Scripts\python provas\prova_n3.py --fisicas
```

No Windows, a N3-F1 (precisa de Postgres) e a N3-F2 (precisa de Node +
Playwright) **pulam**. As 4 estruturais rodam.

PARE aqui para a N-3. A N-4 (termos, privacidade e site atualizado) segue
pela delegação; a publicação do site e a revisão jurídica são do Bruno.
