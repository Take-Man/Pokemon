-- 画像からのパーティ取り込みの回数の上限（直近24時間）。読み取りに外部のOCR（従量課金）を使うための歯止め。
-- 使った回数は usage_log に残す（将来の課金で、機能ごとの使用量を数えるのにも使える）。

alter table public.plan_limits add column max_imports_per_day int not null default 20;

create table public.usage_log (
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  kind       text not null,
  created_at timestamptz not null default now()
);
create index usage_log_user_kind on public.usage_log (user_id, kind, created_at desc);
alter table public.usage_log enable row level security;
-- 本人は読むだけ。書き込みは use_quota だけが行う
create policy "usage_log: 本人が読む" on public.usage_log for select to authenticated using (user_id = (select auth.uid()));
revoke all on public.usage_log from anon;

-- 回数を数えて、上限内なら1回分を記録する。上限なら LIMIT:imports:<上限> の例外
create function public.use_quota(kind text) returns void
language plpgsql security definer set search_path = '' as $$
declare lim int; n int;
begin
  if kind <> 'image_import' then
    raise exception 'unknown quota kind: %', kind;
  end if;
  select l.max_imports_per_day into lim from public.profiles p join public.plan_limits l on l.plan = p.plan
   where p.user_id = auth.uid();
  select count(*) into n from public.usage_log u
   where u.user_id = auth.uid() and u.kind = use_quota.kind and u.created_at > now() - interval '24 hours';
  if lim is not null and n >= lim then
    raise exception 'LIMIT:imports:%', lim using errcode = 'P0001';
  end if;
  insert into public.usage_log (user_id, kind) values (auth.uid(), use_quota.kind);
end $$;
revoke execute on function public.use_quota(text) from anon, public;
grant execute on function public.use_quota(text) to authenticated;

-- 本人のプランと上限に、取り込みの上限を足す（戻り値の形が変わるので作り直す）
drop function public.my_limits();
create function public.my_limits()
returns table (plan text, max_teams int, max_matches int, max_imports_per_day int, features jsonb)
language sql stable security definer set search_path = '' as $$
  select l.plan, l.max_teams, l.max_matches, l.max_imports_per_day, l.features
  from public.profiles p join public.plan_limits l on l.plan = p.plan
  where p.user_id = auth.uid()
$$;
revoke execute on function public.my_limits() from anon, public;
grant execute on function public.my_limits() to authenticated;
