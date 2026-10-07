// アカウント（サービス版だけ）: ログイン中のメールアドレス、プランと使用量、データの書き出し、ログアウト、削除
import { el, api, lead, toast, help, confirmBox } from '../ui.js';
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
      el('h2', {}, 'プランと使用量 ', help('パーティは上限を超えて作れない。対戦履歴は上限を超えると古いものから消える。画像からの取り込みは直近24時間の回数')),
      el('p', {}, 'プラン: ', el('b', {}, lim.plan === 'free' ? '無料' : (lim.plan || '-'))),
      usageRow('保存したパーティ', a.usage.teams, lim.max_teams),
      usageRow('対戦履歴', a.usage.matches, lim.max_matches),
      usageRow('画像からの取り込み（24時間）', a.usage.imports_today, lim.max_imports_per_day)),
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
  const a = el('a', { href: url, download: `gyakudame-note-${new Date().toISOString().slice(0, 10)}.json` });
  document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  toast('書き出した');
}

async function deleteAccount() {
  if (!(await confirmBox('アカウントと、パーティ・対戦履歴などすべてのデータを削除します。元には戻せません。', { ok: 'アカウントを削除する', danger: true, type: '削除' }))) { toast('削除をやめた'); return; }
  await api('/api/account', { method: 'DELETE' });
  await signOut();
}

export default { key: 'account', label: 'アカウント', badge: '人', side: true, serviceOnly: true, render };
