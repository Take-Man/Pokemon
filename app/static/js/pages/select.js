import { $, el, api, lead, toast, picker, help, debounce } from '../ui.js';
import { isService, loadMeta, monLabel } from '../store.js';

const STAT_JA = { hp: 'H', atk: 'A', def: 'B', spa: 'C', spd: 'D', spe: 'S' };
let opp = { species: [], ja: [] }, pred = null, oppMtime = null, pollTimer = null, jobMsg = '';
let selected = null, slowest = false; // 対面表で選んでいるセル {i, j}

// 対面スコア → 表示
const VERDICT = (s) => s >= 0.99 ? ['◎', '有利', 'v-good'] : s >= 0.7 ? ['○', 'やや有利', 'v-good2'] : s > 0.4 ? ['△', '互角', 'v-mid'] : s > 0.2 ? ['▲', 'やや不利', 'v-bad2'] : ['✕', '不利', 'v-bad'];
const pct = (a) => a ? `${a[0]}〜${a[1]}%` : '-';

const saveOpp = debounce(async (pickers) => {
  const species = pickers.map(p => p.input.dataset.id).filter(Boolean);
  await api('/api/opponent', { method: 'PUT', body: { species, source: 'manual' } });
  opp = await api('/api/opponent'); oppMtime = opp.mtime;
}, 150);

async function runPredict(view) {
  try {
    const btn = $('#go'); if (btn) { btn.disabled = true; btn.textContent = '考え中…'; }
    pred = await api('/api/predict', { method: 'POST' });
    selected = null;
    drawResult(view);
    if (pred.job) watchJob(view, pred.job);
  } catch (e) { toast('自分のパーティと相手の6体を入力してね'); }
  const btn = $('#go'); if (btn) { btn.disabled = false; btn.textContent = '選出を予想する'; }
}

async function watchJob(view, id) {
  jobMsg = '追加データを取得中…（相手の使用データが足りないポケモンがいる）'; drawJob();
  for (let i = 0; i < 90; i++) {
    await new Promise(r => setTimeout(r, 2000));
    if (!document.body.contains($('#job'))) return;
    const j = (await api('/api/jobs')).find(x => x.id === id);
    if (!j || j.status === 'running') { if (j && j.total) { jobMsg = `追加データを取得中… ${j.done}/${j.total}`; drawJob(); } continue; }
    if (j.status === 'done') { jobMsg = j.warning ? `一部だけ反映した（${j.warning}）` : '追加データを反映した ✓'; pred = await api('/api/predict'); drawResult(view); }
    else jobMsg = `追加データの取得に失敗: ${j.error || ''}`;
    drawJob(); drawEnv(); return;
  }
}

// ---- 環境データ（使用率・型）の鮮度と「更新を確認」 ----
const hm = (iso) => iso ? iso.slice(5, 16).replace('T', ' ').replace('-', '/') : '-';
async function drawEnv() {
  const box = $('#env'); if (!box || isService()) return;  // サービス版の環境データは運営が更新する
  let e; try { e = await api('/api/env'); } catch (_) { return; }
  box.innerHTML = '';
  if (!e.season_label) { box.append('環境データ: なし（相手の型は種族値から推定）'); }
  else box.append('環境データ: ', el('b', {}, e.season_label), ` サイト更新 ${e.source_updated || '-'}・確認 ${hm(e.list_fetched_at)}`,
    e.stale ? `・上位${e.top}体のうち${e.stale}体が古い` : '');
  const ac = e.access || {};
  let note = '', disabled = false;
  if (e.job) { disabled = true; note = e.job.total ? `取得中 ${e.job.done}/${e.job.total}（3秒に1件）` : '取得中…'; }
  else if (ac.cooldown_until) { disabled = true; note = `サイトに断られたため ${hm(ac.cooldown_until).slice(6)} まで取得を止めている`; }
  else if (ac.today >= ac.limit) { disabled = true; note = '今日の取得の上限に達した'; }
  else if (!e.can_check && !e.stale) { disabled = true; note = `${e.check_hours}時間以内に確認済み`; }
  box.append(' ', el('button', { class: 'btn small ghost', disabled, title: 'サイトの更新日時を確認し、更新後に取得していない上位のポケモンだけを取りに行く（3秒に1件・1日の上限あり）',
    onclick: async () => { await api('/api/collect', { method: 'POST' }); drawEnv(); } }, '更新を確認'),
    note ? el('small', { class: 'muted' }, ' ' + note) : '',
    help(`取得先: ポケモンバトルデータベース。サイトに負担をかけないよう、自動では取りに行かない（押したときと、選出予想でデータの無い相手がいたときだけ）。今日の取得 ${ac.today || 0}/${ac.limit || '-'}件`));
  if (e.job) setTimeout(drawEnv, 2000);
}
function drawJob() { const j = $('#job'); if (j) j.textContent = jobMsg; }

export default {
  key: 'select', label: '選出', badge: '2',
  async render(view) {
    await loadMeta();
    clearInterval(pollTimer);
    opp = await api('/api/opponent'); oppMtime = opp.mtime;
    const teams = await api('/api/teams');
    const active = teams.find(t => t.active);
    try { pred = await api('/api/predict'); } catch (e) { pred = null; }
    selected = null;

    view.append(lead('2', '選出'));
    const slots = el('div', { class: 'opp-grid' });
    let pickers = [];
    const drawSlots = () => {
      slots.innerHTML = ''; pickers = [];
      for (let i = 0; i < 6; i++) {
        const p = picker({ kind: 'pokemon', value: opp.species[i], label: opp.ja[i] || '', placeholder: `相手 ${i + 1}`,
          onPick: () => saveOpp(pickers), onEnterNext: () => { const n = pickers[i + 1]; if (n) n.input.focus(); else $('#go').focus(); } });
        pickers.push(p);
        slots.append(el('div', { class: 'opp-slot' }, el('span', { class: 'idx opp' }, i + 1), p));
      }
    };
    drawSlots();
    const myTeam = active && active.members.length
      ? el('div', { class: 'muted', style: 'font-size:14px' }, '使うパーティ: ', el('b', {}, active.name || '名前なし'), `（${active.members.join('・')}）`, ' ', el('a', { href: '#team' }, '変更'))
      : el('div', { class: 'tip' }, 'まだパーティが空。先に ', el('a', { href: '#team' }, '① パーティ'), ' を登録しよう。');
    view.append(el('div', { class: 'card' },
      el('div', { class: 'sec-title' }, el('h2', {}, '相手の6体 ', help('対戦の「見せ合い」で表示される相手のポケモン。名前を入れてEnterで次の枠へ')),
        el('span', { class: 'row', style: 'gap:6px' }, el('span', { class: 'muted' }, 'タイプから調べる→'), el('a', { class: 'btn small alt', href: '#types' }, 'タイプ相性'))),
      slots, el('div', { class: 'row', style: 'margin-top:12px' },
        el('button', { id: 'go', class: 'btn primary big', onclick: () => runPredict(view) }, '選出を予想する'),
        el('button', { class: 'btn ghost', onclick: async () => { await api('/api/opponent', { method: 'PUT', body: { species: [], source: 'manual' } }); opp = await api('/api/opponent'); oppMtime = opp.mtime; drawSlots(); } }, 'クリア'),
        el('span', { id: 'job', class: 'muted' })),
      el('div', { style: 'margin-top:10px' }, myTeam),
      el('div', { id: 'env', class: 'muted', style: 'margin-top:6px; font-size:13px' })));
    drawEnv();
    view.append(el('div', { id: 'result' }));
    drawResult(view);

    // スクショ判定など、ファイル経由で相手の6体が更新されたら反映（ローカル版だけ）
    if (!isService()) pollTimer = setInterval(async () => {
      if (!document.body.contains(slots)) { clearInterval(pollTimer); return; }
      try {
        const o = await api('/api/opponent');
        if (oppMtime && o.mtime !== oppMtime && o.source !== 'manual') { opp = o; drawSlots(); toast(`相手の6体を${o.source}から読み込んだ`); }
        oppMtime = o.mtime;
      } catch (e) { /* ignore */ }
    }, 3000);
  },
};

function drawResult(view) {
  const box = $('#result'); if (!box) return;
  box.innerHTML = '';
  if (!pred || !pred.opponent) {
    box.append(el('div', { class: 'card', style: 'margin-top:18px' }, el('div', { class: 'empty' }, el('div', { class: 'big' }, '—'), '相手の6体を入れて「選出を予想する」を押すと、結果がここに出る')));
    return;
  }
  // ① おすすめ選出
  const [best, ...others] = pred.recommend;
  const answerRows = (c) => Object.entries(c.answers).map(([k, v]) => el('div', { class: 'ans' },
    el('span', { class: 'chip opp' }, monLabel(k)), el('span', { class: 'arrow' }, '→'),
    v.length ? v.map(n => el('span', { class: 'chip me' }, monLabel(n))) : el('span', { class: 'err' }, '有利な駒なし')));
  const recCard = (c, big) => el('div', { class: 'rec' + (big ? ' best' : ' sub') },
    el('div', { class: 'rec-names' }, ...c.members.map(n => el('span', { class: 'rec-name' }, monLabel(n)))),
    c.mega_conflict ? el('div', { class: 'err' }, 'メガ持ちが2体いる（メガシンカできるのは1体だけ）') : '',
    el('div', { class: 'muted ans-title' }, '相手ごとの対応 ', big ? help('左が相手、右がその相手に有利な自分のポケモン') : ''),
    answerRows(c));
  box.append(el('div', { class: 'card result-card', style: 'margin-top:18px' },
    el('h2', {}, 'おすすめの選出 ', el('small', { class: 'muted' }, `データ: ${pred.data_source}`)),
    best ? recCard(best, true) : el('p', { class: 'muted' }, '候補なし'),
    others.length ? el('div', { class: 'rec-pair' }, ...others.slice(0, 2).map(c => recCard(c, false))) : ''));

  // ② 相手の選出予想
  const oppCards = pred.opponent.map(o => {
    const threats = o.threatens || [];
    return el('div', { class: 'opp-card' },
      el('div', { class: 'oc-head' }, el('span', { class: 'rank-badge' }, o.rank), el('b', {}, monLabel(o.ja)),
        o.rank <= 3 ? el('span', { class: 'chip opp' }, '出てきそう') : ''),
      el('div', { class: 'score-line' }, el('span', { class: 'lbl' }, 'スコア ', help('相手が選出してきそうな度合い。自分のパーティへの通りの良さと、使用率から算出（高いほど出てきやすい）')),
        el('div', { class: 'meter' }, el('span', { style: `width:${Math.max(4, Math.min(100, o.score * 100))}%` })), el('b', { class: 'score-num' }, Math.round(o.score * 100))),
      el('div', { class: 'oc-line' }, el('span', { class: 'lbl' }, '想定の型'), el('span', { class: 'muted' }, o.set_label)),
      el('div', { class: 'oc-line' }, el('span', { class: 'lbl' }, '要注意 ', help('この相手が有利を取れる、自分のポケモン')), threats.length ? threats.map(t => el('span', { class: 'chip me' }, monLabel(t))) : el('span', { class: 'muted' }, 'なし')),
      el('div', { class: 'oc-line' }, el('span', { class: 'lbl' }, '受け出し ', help('この相手の攻撃を受けても倒れにくい（最大打点50%未満）、後ろに控えさせたい自分のポケモン')),
        (o.switch_ins || []).length ? (o.switch_ins).map(t => el('span', { class: 'chip me' }, monLabel(t))) : el('span', { class: 'muted' }, 'なし')),
      ...(o.setup || []).map(su => el('div', { class: 'oc-line' }, el('span', { class: 'lbl' }, '積み技 ', help('能力を上げる技。積まれると有利が逆転する味方に注意')), `${su.move} → `,
        su.flips.length ? el('span', { class: 'err' }, `起点にされる: ${su.flips.join('・')}`) : el('span', { class: 'muted' }, '積まれても不利にならない'))));
  });
  box.append(el('div', { class: 'card', style: 'margin-top:18px' }, el('h2', {}, '相手の選出予想 ', el('small', { class: 'muted' }, '出てきそうな順')), el('div', { class: 'opp-cards' }, ...oppCards)));

  // ③ 対面表
  const detail = el('div', { class: 'cell-detail muted' }, '表のマスを押すと、技とダメージの目安が出る');
  const showDetail = (i, j) => {
    const x = pred.matrix[i][j], [mark, text] = VERDICT(x.score);
    const first = x.a_speed > x.b_speed ? `${pred.my[i]}が先に動く` : x.a_speed < x.b_speed ? `${pred.opp[j]}が先に動く` : '同速';
    detail.className = 'cell-detail';
    detail.innerHTML = '';
    detail.append(el('b', {}, `${pred.my[i]} vs ${pred.opp[j]}: ${mark} ${text}`),
      el('div', {}, `自分の${x.a_move || '-'}: ${pct(x.a_pct)}（${x.a_hits}発で倒せる） ／ 相手の${x.b_move || '-'}: ${pct(x.b_pct)}（${x.b_hits}発で倒される）`),
      el('div', { class: 'muted' }, `素早さ ${x.a_speed} 対 ${x.b_speed} → ${first}`), x.evidence ? el('div', { class: 'muted' }, `実戦データ: ${x.evidence}`) : '');
  };
  const tbl = el('table', { class: 'matrix' }, el('tr', {}, el('th', {}, ''), ...pred.opp.map(o => el('th', { class: 'col-opp' }, monLabel(o, true)))));
  pred.matrix.forEach((row, i) => tbl.append(el('tr', {}, el('th', { class: 'row-me' }, monLabel(pred.my[i])),
    ...row.map((x, j) => { const [mark, text, cls] = VERDICT(x.score); return el('td', { class: 'vcell ' + cls, title: text, tabindex: '0', onclick: () => showDetail(i, j) }, mark); }))));
  box.append(el('div', { class: 'card', style: 'margin-top:18px' },
    el('h2', {}, '1対1の相性表 ', help('縦が自分、横が相手。お互いの一番強い技で殴り合ったときの有利不利。素早さも考慮')),
    el('div', { class: 'legend' }, ...['◎ 有利', '○ やや有利', '△ 互角', '▲ やや不利', '✕ 不利'].map((t, k) => el('span', { class: 'vlegend ' + ['v-good', 'v-good2', 'v-mid', 'v-bad2', 'v-bad'][k] }, t))),
    el('div', { class: 'scroll-x' }, tbl), detail));

  box.append(speedCard());
}

// ④ 素早さ比較: 自分の実際の素早さと、相手の最速スカーフ・最速・準速（メガ後の最速も）を1本に並べる
function speedCard() {
  const lad = el('div', { class: 'ladder' }, el('div', { class: 'muted' }, '読み込み中…'));
  const slow = el('input', { type: 'checkbox', checked: slowest, onchange: () => { slowest = slow.checked; draw(); } });
  const card = el('div', { class: 'card', style: 'margin-top:18px' },
    el('h2', {}, '素早さ比較 ', help('相手の努力値は分からないので、よくある型の素早さを並べている。大きい方が先に動く（トリックルーム中は逆）')),
    el('label', { class: 'check', style: 'margin-bottom:10px' }, slow, '最遅も表示', help('トリックルームで先に動きたいときなど、素早さを下げた型を見る')), lad);
  const draw = async () => {
    const rows = await api(`/api/speed?ids=${(opp.species || []).join(',')}&slowest=${slowest}`);
    const list = rows.map(r => ({ ...r, v: r.scarf ? Math.floor(r.speed * 1.5) : r.speed,
      label: r.side === 'me' ? (r.scarf ? 'スカーフ込み' : r.label.replace(/^自分/, '').replace(/[()（）]/g, '') || '実数値') : r.label }))
      .sort((a, b) => b.v - a.v || (a.side === 'me' ? 1 : -1));
    lad.innerHTML = '';
    for (const x of list) lad.append(el('div', { class: 'lrow ' + x.side },
      el('div', { class: 'lcell l' }, x.side === 'me' ? el('span', { class: 'lbadge me' }, el('small', {}, x.label), x.ja) : ''),
      el('div', { class: 'lnum' }, x.v),
      el('div', { class: 'lcell r' }, x.side === 'opp' ? el('span', { class: 'lbadge opp' }, el('small', {}, x.label), x.ja) : '')));
  };
  draw();
  return card;
}
