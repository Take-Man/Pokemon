// サービス版のログイン（Supabase Auth・Google）。ローカル版では読み込まない
import { banner, setAuth } from './ui.js';

const SUPABASE_JS = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.117.3/+esm';
let client = null;

// ログイン済みなら利用者（{email}）、未ログインなら null
export async function initAuth(config) {
  const { createClient } = await import(SUPABASE_JS);
  client = createClient(config.supabase_url, config.supabase_anon_key, { auth: { flowType: 'pkce' } });
  setAuth(async () => {
    const { data } = await client.auth.getSession();  // 期限が近ければ supabase-js が更新する
    return data.session ? data.session.access_token : null;
  }, () => { location.hash = ''; location.reload(); });
  // 別のタブでログアウトしたときなど
  client.auth.onAuthStateChange((event) => { if (event === 'SIGNED_OUT') location.reload(); });
  const { data } = await client.auth.getSession();
  return data.session ? { email: data.session.user.email || '' } : null;
}

export async function signOut() { await client.auth.signOut(); location.hash = ''; location.reload(); }

// Google のログイン画面へ移る（戻ってくると initAuth がログイン済みとして扱う）
export async function startLogin() {
  const { error } = await client.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: location.origin + '/' } });
  if (error) banner('ログインを始められなかった: ' + error.message);
}
