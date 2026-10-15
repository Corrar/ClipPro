-- ClipPro, fase N-3 (RULINGS §29.5): compra de créditos (Mercado Pago).
--
-- Rodar DEPOIS de 002_contas.sql, no SQL Editor do Supabase. Idempotente.
--
-- Regras:
--   - os pacotes são do Bruno (tabela pacotes); o app só mostra os ativos;
--   - iniciar_compra (usuário logado) registra a intenção com o preço do
--     pacote NAQUELE momento;
--   - confirmar_compra é a ÚNICA porta que credita uma compra. Só a chave
--     secreta chama (o webhook, depois de conferir o pagamento na API do
--     Mercado Pago). Idempotente: o mesmo pagamento nunca credita duas vezes;
--     valor diferente do preço não credita.

create table if not exists public.pacotes (
    id             text primary key check (id ~ '^[a-z0-9-]{1,32}$'),
    nome           text not null,
    minutos        int not null check (minutos between 1 and 100000),
    preco_centavos int not null check (preco_centavos between 100 and 10000000),
    ativo          boolean not null default false,
    ordem          int not null default 0
);

create table if not exists public.compras (
    id             uuid primary key default gen_random_uuid(),
    conta          uuid not null references public.perfis (conta) on delete cascade,
    pacote         text not null references public.pacotes (id),
    minutos        int not null,
    preco_centavos int not null,
    status         text not null default 'pendente'
                   check (status in ('pendente', 'aprovada', 'recusada')),
    pagamento      text unique,
    criado_em      timestamptz not null default now(),
    atualizado_em  timestamptz not null default now()
);
create index if not exists compras_conta on public.compras (conta, criado_em desc);

alter table public.movimentos add column if not exists compra uuid references public.compras (id);
create unique index if not exists movimentos_uma_compra
    on public.movimentos (compra) where motivo = 'compra';


create or replace function public.iniciar_compra(p_pacote text)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_conta uuid := auth.uid();
    v_pac   public.pacotes%rowtype;
    v_id    uuid;
begin
    if v_conta is null then
        raise exception using errcode = 'P0001', message = 'entre na sua conta para comprar créditos.';
    end if;
    if not exists (select 1 from public.perfis where conta = v_conta and liberado) then
        raise exception using errcode = 'P0001', message = 'o beta do ClipPro é só para convidados.';
    end if;
    select * into v_pac from public.pacotes where id = p_pacote and ativo;
    if not found then
        raise exception using errcode = 'P0001', message = 'este pacote não está à venda.';
    end if;
    -- Freio contra clique repetido: no máximo 5 compras abertas por hora.
    if (select count(*) from public.compras
         where conta = v_conta and status = 'pendente'
           and criado_em > now() - interval '1 hour') >= 5 then
        raise exception using errcode = 'P0001',
            message = 'você já abriu várias compras agora; termine uma ou espere alguns minutos.';
    end if;
    insert into public.compras (conta, pacote, minutos, preco_centavos)
    values (v_conta, v_pac.id, v_pac.minutos, v_pac.preco_centavos)
    returning id into v_id;
    return v_id;
end;
$$;


-- Chamada pelo webhook (chave secreta), DEPOIS de consultar o pagamento na
-- API do Mercado Pago. Devolve: creditada | recusada | ja_processada.
create or replace function public.confirmar_compra(
    p_compra uuid, p_pagamento text, p_valor_centavos int, p_aprovado boolean)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
    v_c public.compras%rowtype;
begin
    select * into v_c from public.compras where id = p_compra for update;
    if not found then
        raise exception 'compra inexistente: %', p_compra;
    end if;
    if v_c.status <> 'pendente' then
        return 'ja_processada';
    end if;
    if not p_aprovado then
        update public.compras set status = 'recusada', pagamento = p_pagamento, atualizado_em = now()
         where id = p_compra;
        return 'recusada';
    end if;
    if p_valor_centavos is distinct from v_c.preco_centavos then
        raise exception 'valor pago (%) diferente do preço da compra (%)',
            p_valor_centavos, v_c.preco_centavos;
    end if;
    update public.compras set status = 'aprovada', pagamento = p_pagamento, atualizado_em = now()
     where id = p_compra;
    insert into public.movimentos (conta, delta, motivo, compra)
    values (v_c.conta, v_c.minutos, 'compra', p_compra)
    on conflict do nothing;
    return 'creditada';
end;
$$;


alter table public.pacotes enable row level security;
alter table public.compras enable row level security;
drop policy if exists pacotes_ativos on public.pacotes;
create policy pacotes_ativos on public.pacotes
    for select to authenticated using (ativo);
drop policy if exists compras_dono on public.compras;
create policy compras_dono on public.compras
    for select to authenticated using (conta = auth.uid());

revoke all on public.pacotes, public.compras from anon, authenticated;
grant select on public.pacotes, public.compras to authenticated;

revoke all on function public.iniciar_compra(text) from public, anon;
grant execute on function public.iniciar_compra(text) to authenticated;
revoke all on function public.confirmar_compra(uuid, text, int, boolean) from public, anon, authenticated;
grant execute on function public.confirmar_compra(uuid, text, int, boolean) to service_role;
