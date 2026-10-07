-- サービス版の初期定義。Supabase の SQL Editor に貼って実行するか、supabase db push で適用する。
--
-- 方針
-- - 保存する個人情報はログイン用のメールアドレスだけ（auth.users が持つ）。ここの表には名前・アイコン等を置かない
-- - すべての表で RLS を有効にし、本人の行（user_id = auth.uid()）だけを読み書きできる
-- - プランごとの上限は plan_limits の行で決める（課金を入れるときは profiles.plan を書き換えるだけ）
-- - パーティ・対戦はローカル版のファイルと同じ形の JSON（doc）をそのまま入れる

-- ---------------------------------------------------------------------------
-- プランと上限
-- ---------------------------------------------------------------------------
create table public.plan_limits (
  plan        text primary key,
  max_teams   int  not null,          -- 保存できるパーティの数（超える追加は拒否）
  max_matches int  not null,          -- 残す対戦履歴の数（超えたら古いものから消す）
  features    jsonb not null default '{}'::jsonb  -- 機能の制限（例: {"reverse_calc": false}）。キーが無ければ使える
);
insert into public.plan_limits (plan, max_teams, max_matches) values ('free', 5, 50);

create table public.profiles (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  plan       text not null default 'free' references public.plan_limits (plan),
  created_at timestamptz not null default now()
);

-- 登録時にプロフィールを作る
create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (user_id) values (new.id) on conflict do nothing;
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();
-- このSQLより前に登録済みの利用者にも作る
insert into public.profiles (user_id) select id from auth.users on conflict do nothing;

-- 本人のプランと上限（画面・API向け）
create function public.my_limits() returns table (plan text, max_teams int, max_matches int, features jsonb)
language sql stable security definer set search_path = '' as $$
  select l.plan, l.max_teams, l.max_matches, l.features
  from public.profiles p join public.plan_limits l on l.plan = p.plan
  where p.user_id = auth.uid()
$$;

-- ---------------------------------------------------------------------------
-- 利用者のデータ
-- ---------------------------------------------------------------------------
create table public.teams (
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  id         text not null,
  doc        jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, id)
);

create table public.matches (
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  id         text not null,
  created_at timestamptz not null default now(),
  doc        jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, id)
);
create index matches_user_created on public.matches (user_id, created_at desc);

-- 選択中のパーティ・現在の対戦（settings）、相手の6体、選出予想
create table public.user_state (
  user_id             uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  settings            jsonb not null default '{}'::jsonb,
  opponent            jsonb,
  opponent_updated_at timestamptz,
  prediction          jsonb,
  updated_at          timestamptz not null default now()
);

-- 更新日時は DB で付ける
create function public.touch_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;
create trigger teams_touch before update on public.teams for each row execute function public.touch_updated_at();
create trigger matches_touch before update on public.matches for each row execute function public.touch_updated_at();
create trigger user_state_touch before update on public.user_state for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- 上限
-- ---------------------------------------------------------------------------
create function public.check_team_limit() returns trigger
language plpgsql set search_path = '' as $$
declare lim int; n int;
begin
  -- 既存のパーティの上書き（upsert）は数えない
  if exists (select 1 from public.teams t where t.user_id = new.user_id and t.id = new.id) then
    return new;
  end if;
  select l.max_teams into lim from public.profiles p join public.plan_limits l on l.plan = p.plan
   where p.user_id = new.user_id;
  select count(*) into n from public.teams t where t.user_id = new.user_id;
  if lim is not null and n >= lim then
    raise exception 'LIMIT:teams:%', lim using errcode = 'P0001';
  end if;
  return new;
end $$;
create trigger teams_limit before insert on public.teams
  for each row execute function public.check_team_limit();

create function public.trim_matches() returns trigger
language plpgsql set search_path = '' as $$
declare lim int;
begin
  select l.max_matches into lim from public.profiles p join public.plan_limits l on l.plan = p.plan
   where p.user_id = new.user_id;
  if lim is not null then
    delete from public.matches m
     where m.user_id = new.user_id
       and m.id not in (select m2.id from public.matches m2 where m2.user_id = new.user_id
                         order by m2.created_at desc limit lim);
  end if;
  return null;
end $$;
create trigger matches_trim after insert on public.matches
  for each row execute function public.trim_matches();

-- ---------------------------------------------------------------------------
-- RLS（本人の行だけ）
-- ---------------------------------------------------------------------------
alter table public.plan_limits enable row level security;
alter table public.profiles    enable row level security;
alter table public.teams       enable row level security;
alter table public.matches     enable row level security;
alter table public.user_state  enable row level security;

create policy "plan_limits: 読むだけ" on public.plan_limits for select to authenticated using (true);
-- プランの変更は管理用キー（将来の課金のWebhook）だけ。本人は読むだけ
create policy "profiles: 本人が読む" on public.profiles for select to authenticated using (user_id = (select auth.uid()));

create policy "teams: 本人" on public.teams for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "matches: 本人" on public.matches for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "user_state: 本人" on public.user_state for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- 匿名（未ログイン）には何も見せない
revoke all on public.teams, public.matches, public.user_state, public.profiles, public.plan_limits from anon;
-- ログインした利用者に必要な権限だけを明示する（「新しい表を自動で公開する」をオフにしたプロジェクト向け。オンでも害はない）
grant select, insert, update, delete on public.teams, public.matches, public.user_state to authenticated;
grant select on public.profiles, public.plan_limits to authenticated;
revoke execute on function public.my_limits() from anon, public;
grant execute on function public.my_limits() to authenticated;
