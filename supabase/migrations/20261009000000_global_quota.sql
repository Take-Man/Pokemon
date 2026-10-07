-- 使いすぎ対策: 画像からの取り込みに、全利用者の合計の上限（直近24時間）を足す。
-- 1人あたりの上限（plan_limits.max_imports_per_day）だけだと、アカウントを大量に作れば外部OCR（従量課金）を
-- 使い続けられるため。値は app_limits の行で変える（例: update public.app_limits set value = 100 where key = 'max_imports_per_day_total';）。

create table public.app_limits (
  key   text primary key,
  value int  not null
);
insert into public.app_limits (key, value) values ('max_imports_per_day_total', 50);  -- 最悪でも約 50回×4呼び出し×30日 ≈ 6,000回/月（無料1,000回を超える分で約1,000円）
alter table public.app_limits enable row level security;  -- 利用者からは見えない・変えられない（関数の中だけで読む）
revoke all on public.app_limits from anon, authenticated;

-- 上限に達していないか確かめる（数えはしない）。1人あたり → 全体 の順に確かめ、達していれば LIMIT の例外
create function public.check_quota(kind text) returns void
language plpgsql security definer set search_path = '' as $$
declare lim int; n int; total_lim int; total_n int;
begin
  if kind <> 'image_import' then
    raise exception 'unknown quota kind: %', kind;
  end if;
  select l.max_imports_per_day into lim from public.profiles p join public.plan_limits l on l.plan = p.plan
   where p.user_id = auth.uid();
  select count(*) into n from public.usage_log u
   where u.user_id = auth.uid() and u.kind = check_quota.kind and u.created_at > now() - interval '24 hours';
  if lim is not null and n >= lim then
    raise exception 'LIMIT:imports:%', lim using errcode = 'P0001';
  end if;
  select a.value into total_lim from public.app_limits a where a.key = 'max_imports_per_day_total';
  select count(*) into total_n from public.usage_log u
   where u.kind = check_quota.kind and u.created_at > now() - interval '24 hours';
  if total_lim is not null and total_n >= total_lim then
    raise exception 'LIMIT:imports_total:%', total_lim using errcode = 'P0001';
  end if;
end $$;
revoke execute on function public.check_quota(text) from anon, public;
grant execute on function public.check_quota(text) to authenticated;

-- 1回分を記録する（上限の確認も同じ関数で行う）
create or replace function public.use_quota(kind text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  perform public.check_quota(use_quota.kind);
  insert into public.usage_log (user_id, kind) values (auth.uid(), use_quota.kind);
end $$;

-- 全体の件数を数えるときのための索引
create index usage_log_kind_created on public.usage_log (kind, created_at desc);
