// アカウント（サービス版だけ）: ログイン中のメールアドレス、プランと使用量、データの書き出し、ログアウト、削除
import { el, api, lead, toast, help } from '../ui.js';
import { signOut } from '../auth.js';

const usageRow = (label, n, max) => el('div', { class: 'acc-row' }, el('span', {}, label),
  el('b', {}, max == null ? `${n}` : `${n} / ${max}`));

async function render(view) {
  const a = await api('/api/account');
  const lim = a.limits || {};
  view.append(lead('人', 'アカウント'),
    el('div', { class: 'card' },
      el('h2', {}, 'ログイン中'), el('p', {}, a.email || '（メールアドレスなし）'),
      el('button', { class: 'btn small', onclick: signOut }, 'ログアウト')),
    el('div', { class: 'card', style: 'margin-top:18px' },
      el('h2', {}, 'プランと使用量 ', help('パーティは上限を超えて作れない。対戦履歴は上限を超えると古いものから消える')),
      el('p', {}, 'プラン: ', el('b', {}, lim.plan === 'free' ? '無料' : (lim.plan || '-'))),
      usageRow('保存したパーティ', a.usage.teams, lim.max_teams),
      usageRow('対戦履歴', a.usage.matches, lim.max_matches)),
    el('div', { class: 'card', style: 'margin-top:18px' },
      el('h2', {}, 'データ'),
      el('p', { class: 'muted' }, 'パーティ・対戦履歴・設定をまとめてファイル（JSON）に書き出す。'),
      el('button', { class: 'btn small alt', onclick: exportData }, '書き出す')),
    el('div', { class: 'card danger', style: 'margin-top:18px' },
      el('h2', {}, 'アカウントの削除'),
      el('p', { class: 'muted' }, 'アカウントと、パーティ・対戦履歴などすべてのデータを消す。元には戻せない。'),
      el('button', { class: 'btn small ghost', onclick: deleteAccount }, 'アカウントを削除する')));
}

async function exportData() {
  const d = await api('/api/account/export');
  const url = URL.createObjectURL(new Blob([JSON.stringify(d, null, 1)], { type: 'application/json' }));
  const a = el('a', { href: url, download: `battle-support-${new Date().toISOString().slice(0, 10)}.json` });
  document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  toast('書き出した');
}

async function deleteAccount() {
  if (!confirm('アカウントとすべてのデータを削除します。元には戻せません。よろしいですか？')) return;
  if (prompt('確認のため「削除」と入力してください') !== '削除') { toast('削除をやめた'); return; }
  await api('/api/account', { method: 'DELETE' });
  await signOut();
}

export default { key: 'account', label: 'アカウント', badge: '人', side: true, serviceOnly: true, render };
