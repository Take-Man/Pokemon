// サービス版のログイン（Supabase Auth・Google）。ローカル版では読み込まない
import { el, setAuth } from './ui.js';

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

export function loginView() {
  const err = el('div', { class: 'err', hidden: true });
  const go = async () => {
    const { error } = await client.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: location.origin + '/' } });
    if (error) { err.textContent = 'ログインを始められなかった: ' + error.message; err.hidden = false; }
  };
  return el('div', { class: 'login' },
    el('div', { class: 'card login-card' },
      el('h1', {}, 'ギャクダメノート'), el('div', { class: 'muted login-en' }, 'Gyakudame Note'),
      el('p', {}, 'ポケモンチャンピオンズ（シングル）の選出・ダメ計・対戦中の型の絞り込みを、手元の端末で素早く引き出すための道具。'),
      el('button', { class: 'btn primary big', onclick: go }, 'Googleでログイン'),
      err,
      el('p', { class: 'muted', style: 'font-size:13px' }, '保存する個人情報はログイン用のメールアドレスだけ。パーティと対戦履歴は本人しか見られない。'),
      el('p', { class: 'muted', style: 'font-size:13px' }, el('a', { href: '/terms' }, '利用規約'), '・', el('a', { href: '/privacy' }, 'プライバシーポリシー'), '・', el('a', { href: 'https://forms.gle/BZJUwgC3okBH2XrW9', target: '_blank', rel: 'noopener' }, 'お問い合わせ'))));
}
