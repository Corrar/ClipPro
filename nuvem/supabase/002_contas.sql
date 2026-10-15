-- ClipPro, fase N-2 (RULINGS §29.3): contas, convites e créditos.
--
-- Rodar DEPOIS de 001_fila.sql, no SQL Editor do Supabase. Idempotente.
--
-- Regras:
--   - 1 crédito = 1 minuto de vídeo (§26, N7 = A); o cadastro liberado
--     ganha 300 (§25);
--   - beta fechado (§27, G1): só e-mail convidado E CONFIRMADO é liberado. O
--     Supabase cria o usuário antes da confirmação; liberar no cadastro
--     deixaria alguém se cadastrar com o e-mail de um convidado e levar os
--     créditos dele;
--   - saldo = soma dos movimentos (nada de coluna "saldo" que desanda);
--   - pedir clipe RESERVA até 600 min do saldo; quando o trabalho termina,
--     uma trigger devolve o que não foi usado (falha devolve tudo);
--   - cada conta só lê o que é seu (RLS); escrever, só pelas funções.

create table if not exists public.convites (
    email     text primary key check (email = lower(email)),
    criado_em timestamptz not null default now()
);

create table if not exists public.perfis (
    conta     uuid primary key references auth.users (id) on delete cascade,
    email     text not null,
    liberado  boolean not null default false,
    criado_em timestamptz not null default now()
);

create table if not exists public.movimentos (
    id        bigint generated always as identity primary key,
    conta     uuid not null references public.perfis (conta) on delete cascade,
    delta     int not null,
    motivo    text not null
              check (motivo in ('cadastro', 'reserva', 'devolucao', 'compra', 'ajuste')),
    trabalho  uuid references public.trabalhos (id) on delete set null,
    criado_em timestamptz not null default now()
);

-- Idempotência: um bônus de cadastro por conta, uma reserva e uma devolução
-- por trabalho, mesmo que a trigger rode duas vezes.
create unique index if not exists movimentos_um_cadastro
    on public.movimentos (conta) where motivo = 'cadastro';
create unique index if not exists movimentos_uma_reserva
    on public.movimentos (trabalho) where motivo = 'reserva';
create unique index if not exists movimentos_uma_devolucao
    on public.movimentos (trabalho) where motivo = 'devolucao';
create index if not exists movimentos_conta on public.movimentos (conta);
create index if not exists trabalhos_conta on public.trabalhos (conta, criado_em desc);


create or replace function public.clippro_creditos_cadastro()
returns int language sql immutable as $$ select 300 $$;


-- Libera a conta e dá o bônus. Idempotente (índice movimentos_um_cadastro).
create or replace function public.liberar_conta(p_conta uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    update public.perfis set liberado = true where conta = p_conta and not liberado;
    insert into public.movimentos (conta, delta, motivo)
    values (p_conta, public.clippro_creditos_cadastro(), 'cadastro')
    on conflict do nothing;
end;
$$;


-- Cadastro e confirmação de e-mail: cria o perfil; libera se o e-mail
-- CONFIRMADO estiver convidado.
create or replace function public.ao_mudar_usuario()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.perfis (conta, email)
    values (new.id, lower(coalesce(new.email, '')))
    on conflict (conta) do update set email = excluded.email;
    if new.email_confirmed_at is not null
       and exists (select 1 from public.convites c where c.email = lower(new.email)) then
        perform public.liberar_conta(new.id);
    end if;
    return new;
end;
$$;

drop trigger if exists clippro_ao_criar_usuario on auth.users;
create trigger clippro_ao_criar_usuario
    after insert on auth.users
    for each row execute function public.ao_mudar_usuario();

drop trigger if exists clippro_ao_confirmar_usuario on auth.users;
create trigger clippro_ao_confirmar_usuario
    after update of email_confirmed_at, email on auth.users
    for each row execute function public.ao_mudar_usuario();


-- Convite que chega DEPOIS do cadastro libera quem já confirmou o e-mail.
create or replace function public.ao_convidar()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    perform public.liberar_conta(p.conta)
       from public.perfis p
       join auth.users u on u.id = p.conta
      where p.email = new.email and u.email_confirmed_at is not null;
    return new;
end;
$$;

drop trigger if exists clippro_ao_convidar on public.convites;
create trigger clippro_ao_convidar
    after insert on public.convites
    for each row execute function public.ao_convidar();


create or replace function public.meu_saldo()
returns int
language sql
stable
set search_path = public
as $$
    select coalesce(sum(delta), 0)::int from public.movimentos where conta = auth.uid();
$$;


-- O único jeito de o usuário pedir clipes. Valida o básico com mensagem
-- legível; a validação completa é do contrato do worker (worker/contrato.py),
-- e o pedido que ele recusar volta com os créditos devolvidos.
create or replace function public.criar_trabalho(
    p_entrada jsonb, p_n int, p_preset text, p_estrategia text default null)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_conta  uuid := auth.uid();
    v_saldo  int;
    v_limite int;
    v_id     uuid;
    v_pedido jsonb;
begin
    if v_conta is null then
        raise exception using errcode = 'P0001', message = 'entre na sua conta para gerar clipes.';
    end if;
    -- FOR UPDATE no perfil: dois pedidos da mesma conta ao mesmo tempo não
    -- reservam o mesmo saldo duas vezes.
    perform 1 from public.perfis where conta = v_conta and liberado for update;
    if not found then
        raise exception using errcode = 'P0001',
            message = 'o beta do ClipPro é só para convidados.';
    end if;
    if coalesce(p_entrada->>'tipo', '') not in ('link', 'arquivo')
       or coalesce(p_entrada->>'valor', '') = '' then
        raise exception using errcode = 'P0001', message = 'informe o link ou envie o vídeo.';
    end if;
    if p_n is null or p_n not between 1 and 20 then
        raise exception using errcode = 'P0001', message = 'escolha de 1 a 20 cortes.';
    end if;
    if (select count(*) from public.trabalhos
         where conta = v_conta and status in ('pendente', 'em_curso')) >= 3 then
        raise exception using errcode = 'P0001',
            message = 'você já tem 3 vídeos na fila; espere um terminar.';
    end if;
    select coalesce(sum(delta), 0) into v_saldo from public.movimentos where conta = v_conta;
    if v_saldo < 1 then
        raise exception using errcode = 'P0001', message = 'seus créditos acabaram.';
    end if;
    v_limite := least(v_saldo, 600);
    v_pedido := jsonb_build_object(
        'entrada', jsonb_build_object('tipo', p_entrada->>'tipo', 'valor', p_entrada->>'valor'),
        'n', p_n, 'preset', p_preset, 'limite_minutos', v_limite);
    if p_estrategia is not null and btrim(p_estrategia) <> '' then
        v_pedido := v_pedido || jsonb_build_object('estrategia', p_estrategia);
    end if;
    insert into public.trabalhos (conta, pedido) values (v_conta, v_pedido) returning id into v_id;
    insert into public.movimentos (conta, delta, motivo, trabalho)
    values (v_conta, -v_limite, 'reserva', v_id);
    return v_id;
end;
$$;


-- Fim do trabalho: devolve a reserva menos o que foi usado. Trabalho sem
-- reserva (inserido por fora, como na prova N-F4) passa direto.
create or replace function public.acertar_creditos()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    v_reserva int;
    v_usado   int := 0;
    v_texto   text;
begin
    if new.status not in ('concluido', 'falhou', 'recusado') or new.status = old.status then
        return new;
    end if;
    select -delta into v_reserva from public.movimentos
     where trabalho = new.id and motivo = 'reserva';
    if v_reserva is null then
        return new;
    end if;
    if new.status = 'concluido' then
        v_texto := new.resultado->>'creditos';
        -- Valor torto cobra zero: o erro fica a favor do usuário.
        if v_texto ~ '^[0-9]{1,6}$' then
            v_usado := least(v_texto::int, v_reserva);
        end if;
    end if;
    insert into public.movimentos (conta, delta, motivo, trabalho)
    values (new.conta, v_reserva - v_usado, 'devolucao', new.id)
    on conflict do nothing;
    return new;
end;
$$;

drop trigger if exists clippro_acertar_creditos on public.trabalhos;
create trigger clippro_acertar_creditos
    after update of status on public.trabalhos
    for each row execute function public.acertar_creditos();


-- RLS: cada conta lê o que é seu. Ninguém escreve direto.
alter table public.convites   enable row level security;
alter table public.perfis     enable row level security;
alter table public.movimentos enable row level security;

drop policy if exists perfis_dono on public.perfis;
create policy perfis_dono on public.perfis
    for select to authenticated using (conta = auth.uid());
drop policy if exists movimentos_dono on public.movimentos;
create policy movimentos_dono on public.movimentos
    for select to authenticated using (conta = auth.uid());
drop policy if exists trabalhos_dono on public.trabalhos;
create policy trabalhos_dono on public.trabalhos
    for select to authenticated using (conta = auth.uid());

-- Colunas internas da fila (worker, tentativas, prazo) não são do usuário.
revoke all on public.trabalhos from anon, authenticated;
grant select (id, conta, pedido, status, resultado, criado_em, atualizado_em)
    on public.trabalhos to authenticated;
revoke all on public.perfis, public.movimentos, public.convites from anon, authenticated;
grant select on public.perfis, public.movimentos to authenticated;

revoke all on function public.liberar_conta(uuid) from public, anon, authenticated;
revoke all on function public.ao_mudar_usuario() from public, anon, authenticated;
revoke all on function public.ao_convidar() from public, anon, authenticated;
revoke all on function public.acertar_creditos() from public, anon, authenticated;
revoke all on function public.criar_trabalho(jsonb, int, text, text) from public, anon;
revoke all on function public.meu_saldo() from public, anon;
grant execute on function public.criar_trabalho(jsonb, int, text, text) to authenticated;
grant execute on function public.meu_saldo() to authenticated;
