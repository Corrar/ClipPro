-- ClipPro, fase N-1 (RULINGS §28): a fila de trabalhos no Supabase.
--
-- Rodar UMA vez no SQL Editor do projeto (ou `psql -f`). Idempotente: rodar
-- de novo nao apaga nada.
--
-- Quem usa:
--   - o worker (PC do operador, §27 G3), com a chave SECRETA, so por estas
--     quatro funcoes;
--   - o app (N-2), que insere o pedido da conta logada. A leitura da propria
--     conta (RLS) entra na N-2; ate la ninguem alem da chave secreta enxerga
--     a tabela.
--
-- As mesmas regras da FilaEmPasta (worker/fila.py): reserva com prazo,
-- devolucao quando o worker para de renovar, 3 tentativas no maximo, e uma
-- reserva vencida nunca encerra a reserva nova de outro worker.

create table if not exists public.trabalhos (
    id            uuid primary key default gen_random_uuid(),
    conta         uuid not null,          -- auth.users.id (a chave estrangeira entra na N-2)
    pedido        jsonb not null,         -- entrada, n, preset, estrategia, limite_minutos
    status        text not null default 'pendente'
                  check (status in ('pendente', 'em_curso', 'concluido', 'falhou', 'recusado')),
    worker        text,
    tentativas    int not null default 0,
    reservado_ate timestamptz,
    resultado     jsonb,
    criado_em     timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);

create index if not exists trabalhos_pendentes
    on public.trabalhos (criado_em, id) where status = 'pendente';

alter table public.trabalhos enable row level security;
-- Sem policy de proposito: anon e authenticated nao leem nem escrevem nada.


-- Reserva o trabalho pendente mais antigo. Antes, devolve as reservas
-- vencidas (worker desligou) -- ou falha a que ja venceu 3 vezes.
create or replace function public.reservar_trabalho(p_worker text, p_prazo_s int)
returns setof public.trabalhos
language plpgsql
set search_path = public
as $$
begin
    update public.trabalhos
       set status = 'falhou', worker = null, reservado_ate = null, atualizado_em = now(),
           resultado = jsonb_build_object(
               'status', 'falhou', 'creditos', 0,
               'erro', jsonb_build_object(
                   'mensagem', 'o processamento deste vídeo parou várias vezes no meio.',
                   'sugestao', 'tente de novo mais tarde; nenhum crédito foi usado.',
                   'detalhe', '3 tentativas sem terminar'))
     where status = 'em_curso' and reservado_ate < now() and tentativas >= 3;

    update public.trabalhos
       set status = 'pendente', worker = null, reservado_ate = null, atualizado_em = now()
     where status = 'em_curso' and reservado_ate < now();

    -- SKIP LOCKED: dois workers chamando ao mesmo tempo pegam linhas
    -- diferentes, sem esperar um pelo outro.
    return query
    update public.trabalhos t
       set status = 'em_curso', worker = p_worker, tentativas = t.tentativas + 1,
           reservado_ate = now() + make_interval(secs => p_prazo_s), atualizado_em = now()
     where t.id = (select id from public.trabalhos
                    where status = 'pendente'
                    order by criado_em, id
                    limit 1
                    for update skip locked)
    returning t.*;
end;
$$;


-- Renova o prazo. False = a reserva ja nao e desta tentativa.
create or replace function public.renovar_trabalho(
    p_id uuid, p_worker text, p_tentativa int, p_prazo_s int)
returns boolean
language sql
set search_path = public
as $$
    with r as (
        update public.trabalhos
           set reservado_ate = now() + make_interval(secs => p_prazo_s), atualizado_em = now()
         where id = p_id and worker = p_worker and tentativas = p_tentativa
           and status = 'em_curso'
        returning 1)
    select exists (select 1 from r);
$$;


-- Encerra (concluido, falhou ou recusado). False = reserva vencida: o
-- resultado desta tentativa e descartado e a reserva nova fica intacta.
create or replace function public.encerrar_trabalho(
    p_id uuid, p_worker text, p_tentativa int, p_status text, p_resultado jsonb)
returns boolean
language plpgsql
set search_path = public
as $$
begin
    if p_status not in ('concluido', 'falhou', 'recusado') then
        raise exception 'status de encerramento invalido: %', p_status;
    end if;
    update public.trabalhos
       set status = p_status, resultado = p_resultado, reservado_ate = null,
           atualizado_em = now()
     where id = p_id and worker = p_worker and tentativas = p_tentativa
       and status = 'em_curso';
    return found;
end;
$$;


-- Ctrl+C no worker: o trabalho volta para a fila agora, sem esperar o prazo.
create or replace function public.devolver_trabalho(
    p_id uuid, p_worker text, p_tentativa int)
returns boolean
language plpgsql
set search_path = public
as $$
begin
    update public.trabalhos
       set status = 'pendente', worker = null, reservado_ate = null, atualizado_em = now()
     where id = p_id and worker = p_worker and tentativas = p_tentativa
       and status = 'em_curso';
    return found;
end;
$$;


-- O Supabase da EXECUTE em funcao nova para anon e authenticated. Aqui so a
-- chave secreta (service_role) pode mexer na fila.
revoke all on function public.reservar_trabalho(text, int) from public, anon, authenticated;
revoke all on function public.renovar_trabalho(uuid, text, int, int) from public, anon, authenticated;
revoke all on function public.encerrar_trabalho(uuid, text, int, text, jsonb) from public, anon, authenticated;
revoke all on function public.devolver_trabalho(uuid, text, int) from public, anon, authenticated;
grant execute on function public.reservar_trabalho(text, int) to service_role;
grant execute on function public.renovar_trabalho(uuid, text, int, int) to service_role;
grant execute on function public.encerrar_trabalho(uuid, text, int, text, jsonb) to service_role;
grant execute on function public.devolver_trabalho(uuid, text, int) to service_role;
