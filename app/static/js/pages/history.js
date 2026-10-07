import { el, api, lead, toast, help, confirmBox } from '../ui.js';
import { monLabel } from '../store.js';
import { evaluateTeam } from './evaluate.js';

const RESULT = { win: ['勝ち', 'win'], lose: ['負け', 'lose'] };

export default {
  key: 'history', label: '履歴', badge: '歴', side: true,
  async render(view) {
    view.append(lead('歴', '履歴'));
    const card = el('div', { class: 'card' }, el('h2', {}, '相手の6体の履歴 ', help('選出予想を押すたびに、相手の6体を保存している。同じ6体を2時間以内にもう一度押したときは、同じ記録として扱う')));
    view.append(card);
    const draw = async () => {
      const rows = await api('/api/matches');
      card.querySelectorAll('.hist-list, .empty').forEach(n => n.remove());
      if (!rows.length) { card.append(el('div', { class: 'empty' }, ['まだ何もない。', el('a', { href: '#select' }, '選出'), 'で「選出を予想する」を押すと残る'])); return; }
      card.append(el('div', { class: 'hist-list' }, ...rows.map(m => {
        const [rt, rc] = RESULT[m.result] || [];
        return el('div', { class: 'hist-row' + (m.current ? ' current' : '') },
          el('div', { class: 'hist-head' }, el('b', {}, (m.created_at || '').slice(5, 16).replace('T', ' ')),
            m.current ? el('span', { class: 'chip me' }, '開いている') : '', rt ? el('span', { class: 'chip ' + rc }, rt) : '',
            m.team_name ? el('span', { class: 'muted' }, `自分: ${m.team_name}`) : '', m.has_detail ? el('span', { class: 'muted' }, `記録 ${m.records}件`) : ''),
          el('div', { class: 'hist-mons' }, ...m.opp_ja.map(ja => el('span', { class: 'chip opp' }, monLabel(ja)))),
          m.opp_picks_ja.length ? el('div', { class: 'muted' }, `相手の選出: ${m.opp_picks_ja.join('・')}`) : '',
          el('div', { class: 'row', style: 'margin-top:8px' },
            el('button', { class: 'btn small primary', onclick: async () => { await api(`/api/matches/${m.id}/load`, { method: 'POST' }); toast('相手の6体を呼び出した'); location.hash = 'select'; } }, '呼び出す'),
            el('button', { class: 'btn small alt', onclick: async () => { await api(`/api/matches/${m.id}/load`, { method: 'POST' }); location.hash = 'reverse'; } }, '対戦を開く'),
            m.team_id ? el('button', { class: 'btn small ghost', title: `自分のパーティ（${m.team_name || ''}）を評価する`, onclick: () => evaluateTeam(m.team_id) }, '評価する') : '',
            el('button', { class: 'btn small ghost', onclick: async () => {
              if (!(await confirmBox(`${m.opp_ja.join('・')} の履歴を削除しますか？`, { ok: '削除する', danger: true }))) return;
              await api(`/api/matches/${m.id}`, { method: 'DELETE' }); toast('削除した'); draw();
            } }, '削除')));
      })));
    };
    await draw();
  },
};
