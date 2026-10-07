import { $, el, api, lead, toast, picker, help, debounce, typeChip } from '../ui.js';
import { S, jaOf, loadTypes, monLabel } from '../store.js';
import { STATS, STAT_JA, STATUS, rankText } from '../parts.js';

let B = null;          // /api/battle の内容
let edit = null;       // 編集中の記録
let kind = 'taken';    // 記録の種類
let root = null;
let prefill = null;    // ダメ計から「記録」で飛んできたときの入力済みの内容
let scrollForm = false;
let showAll = { me: false, opp: false };   // 3体選出したあとも6体を出すか
let showLogs = false;
let lastEffects = [];   // 直近の記録で、技の確定効果として現在の対面に自動で反映した内容
const openState = { detail: true, bench: true };

// ダメ計の技から、記録の追加フォームを埋めた状態で開く
export function prefillRecord(p) { prefill = p; kind = p.kind; edit = null; scrollForm = true; location.hash = 'reverse'; }

const STATUS_JA = Object.fromEntries(STATUS);
const SCREEN = [['none', 'なし'], ['reflect', 'リフレクター'], ['lightscreen', 'ひかりのかべ'], ['both', '両方・オーロラベール']];
const WEATHER = [['none', 'なし'], ['sun', '晴れ'], ['rain', '雨'], ['sand', '砂嵐'], ['snow', '雪']];
const TERRAIN = [['none', 'なし'], ['electric', 'エレキ'], ['grassy', 'グラス'], ['psychic', 'サイコ'], ['misty', 'ミスト']];
const SRC_JA = { confirmed: '確定', inferred: '逆算', usage: '採用率', estimate: '推定', battle: '推定' };
const RANKS = [...Array(13).keys()].map(i => 6 - i);
const pct = (a) => a ? `${a[0]}〜${a[1]}%` : '-';
const srcTag = (src) => el('span', { class: `src src-${src}` }, SRC_JA[src] || src);
const moveType = (id) => (S.types.moves[id] || [])[0] || null;
const moveName = (name, id) => el('span', { class: 'mv' }, moveType(id) ? typeChip(moveType(id), '', true) : '', name);
const errMsg = (e) => { try { return JSON.parse(e.message).detail; } catch (_) { return e.message; } };

// 続けて変えたときは0.4秒待ってまとめて送る（間に別のポケモン・項目を変えても取りこぼさないよう、変更を重ねていく）
const deepMerge = (a, b) => { for (const [k, v] of Object.entries(b)) a[k] = v && typeof v === 'object' && !Array.isArray(v) ? deepMerge(a[k] && typeof a[k] === 'object' ? a[k] : {}, v) : v; return a; };
let pendingLive = null;
// すぐ送るときは、待っている変更も一緒に送る（古い状態で描き直さないため）
const livePut = (patch) => {
  if (pendingLive) { patch = deepMerge(pendingLive, patch); pendingLive = null; }
  return api('/api/battle/live', { method: 'PUT', body: patch }).then(v => { B = v; return v; });
};
const flushLive = debounce(async () => { const patch = pendingLive; pendingLive = null; if (patch) { await livePut(patch); refreshRecords(); } }, 400);
const livePutLater = (patch) => { pendingLive = deepMerge(pendingLive || {}, patch); flushLive(); };
// 待っている変更があれば先に送る（他のタブへ移る・記録する前）
const flushNow = () => pendingLive ? livePut({}) : Promise.resolve();
const put = async (patch) => { await flushNow(); B = await api('/api/battle', { method: 'PUT', body: patch }); draw(); };

export default {
  key: 'reverse', label: '対戦', badge: '4',
  async render(view) {
    await loadTypes();
    root = view;
    try { B = await api('/api/battle'); } catch (e) { B = { match: null }; }
    draw();
  },
  leave: () => flushNow().catch(() => {}),
};

function draw() {
  const y = window.scrollY;
  root.innerHTML = '';
  root.append(lead('4', '対戦'));
  if (!B || !B.match) {
    root.append(el('div', { class: 'card' }, el('div', { class: 'empty' }, ['対戦がまだない。', el('a', { href: '#select' }, '選出'), 'で相手の6体を入れて「選出を予想する」を押すか、', el('a', { href: '#history' }, '履歴'), 'から開く'])));
    return;
  }
  root.append(headCard(), picksCard(), liveCard());
  root.append(el('div', { class: 'grid2 rv-two', style: 'margin-top:18px' }, formCard(), recordsCard()));
  if (scrollForm) { scrollForm = false; setTimeout(() => { const f = $('#rv-form'); if (f) f.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 50); }
  root.append(detailCard(), matrixCard());
  window.scrollTo(0, y);
}

// ---- 対戦の情報 ----
function headCard() {
  const m = B.match;
  const res = el('select', { 'aria-label': '結果', onchange: () => put({ result: res.value || '' }) }, el('option', { value: '' }, '結果（未記入）'),
    el('option', { value: 'win', selected: B.result === 'win' }, '勝ち'), el('option', { value: 'lose', selected: B.result === 'lose' }, '負け'));
  const memo = el('input', { value: B.memo || '', placeholder: 'メモ', 'aria-label': 'メモ' });
  memo.addEventListener('change', () => put({ memo: memo.value }));
  return el('div', { class: 'card' },
    el('div', { class: 'rv-head' }, el('b', {}, (m.created_at || '').slice(5, 16).replace('T', ' ')), el('span', { class: 'muted' }, `自分: ${B.my_team_name || ''}`),
      el('button', { class: 'btn small ghost', title: '記録の前提になる自分のパーティを、今のパーティで取り直す', onclick: async () => {
        if (!confirm('自分のパーティのコピーを現在のパーティで取り直しますか？（記録は残る）')) return;
        B = await api('/api/battle/resnapshot', { method: 'POST' }); draw(); } }, 'パーティを取り直す')),
    el('div', { class: 'rv-head' }, ...m.opp_ja.map((ja, i) => el('span', { class: 'chip opp' }, monLabel(ja)))),
    el('div', { class: 'row', style: 'margin-top:8px' }, el('div', { class: 'grow' }, res), el('div', { class: 'grow', style: 'flex-basis:260px' }, memo)));
}

// ---- 選出 ----
// 選出から外すと、そのポケモンの HP・状態異常・ランクが消えるので確認する
function unpick(selected, ja, go) {
  if (selected && !confirm(`${ja} を選出から外すと、HP・状態異常・ランクの記録が消える。外しますか？`)) return;
  go();
}
function picksCard() {
  const m = B.match;
  const toggle = (arr, v) => arr.includes(v) ? arr.filter(x => x !== v) : (arr.length >= 3 ? arr : [...arr, v]);
  const pickOpp = async (sid) => {
    const next = toggle(B.opp_picks, sid), added = next.length > B.opp_picks.length ? sid : null;
    B = await api('/api/battle', { method: 'PUT', body: { opp_picks: next } });
    if (added && B.live && B.live.active.opp !== added) await switchTo('opp', added); else draw();   // 新しく選んだ相手は、そのまま場に出ている扱いにする
  };
  // 3体選び終わったら、選んだ3体だけを出す（「6体表示」で全員を出し直せる）
  const all = (side, n) => n < 3 || showAll[side];
  const more = (side, n) => n >= 3 ? el('label', { class: 'check' }, el('input', { type: 'checkbox', checked: showAll[side], onchange: (e) => { showAll[side] = e.target.checked; draw(); } }), '6体表示') : '';
  const mine = B.my_team.filter(x => all('me', B.my_picks.length) || B.my_picks.includes(x.index))
    .map(x => el('button', { class: 'pick me' + (B.my_picks.includes(x.index) ? ' on' : ''), onclick: () => unpick(B.my_picks.includes(x.index), x.ja, () => put({ my_picks: toggle(B.my_picks, x.index) })) }, monLabel(x.ja)));
  const opp = m.opp.map((sid, k) => [sid, m.opp_ja[k]]).filter(([sid]) => all('opp', B.opp_picks.length) || B.opp_picks.includes(sid))
    .map(([sid, ja]) => el('button', { class: 'pick opp' + (B.opp_picks.includes(sid) ? ' on' : ''), onclick: () => unpick(B.opp_picks.includes(sid), ja, () => pickOpp(sid)) }, monLabel(ja)));
  return el('div', { class: 'card', style: 'margin-top:18px' },
    el('h2', {}, '選出 ', help('見せ合いのあとに選んだ3体ずつ。相手は見えた順に選ぶ。ここで選んだ体だけが、現在の対面・記録・控え相性に出る')),
    el('div', { class: 'rv-picks' }, el('b', { class: 'side-me' }, '自分'), ...mine, more('me', B.my_picks.length)),
    el('div', { class: 'rv-picks' }, el('b', { class: 'side-opp' }, '相手'), ...opp, more('opp', B.opp_picks.length)));
}

// ---- 現在の対面 ----
// 場に出すポケモンを変える。設置技（ステルスロック等）がある場なら、その影響を反映するか確認する
async function switchTo(side, key) {
  const lv = B.live; if (!lv || lv.active[side] === key) return;
  const patch = { active: { [side]: key } };
  try {
    const hz = await api(`/api/battle/hazard-preview?side=${side}&key=${encodeURIComponent(key)}`);
    if (hz.lines.length && confirm(`${hz.name} が場に出ると、設置技の影響を受ける。\n\n・${hz.lines.join('\n・')}\n\n反映しますか？`)) {
      const cur = lv[side][key] || {}, mon = {};
      if (hz.hp != null) mon.hp = hz.hp;
      if (hz.status && (cur.status || 'none') === 'none') mon.status = hz.status;
      if (hz.boosts.spe) mon.boosts = { spe: Math.max(-6, ((cur.boosts || {}).spe || 0) + hz.boosts.spe) };
      patch[side] = { [key]: mon };
      if (Object.keys(hz.field).length) patch.field = hz.field;
      patch.reason = '設置技';
    }
  } catch (e) { /* 反映できなくても、場の切替は行う */ }
  prefill = null;
  await livePut(patch);
  draw();
}
const setActive = (side, key) => switchTo(side, key);

function liveCard() {
  const lv = B.live;
  const card = el('div', { class: 'card', style: 'margin-top:18px' }, el('h2', {}, '現在の対面 ', help('カードを押すと場に出ているポケモンになる。HP・状態異常・ランク・場の状態は記録の条件になり、記録するとHPも更新される。ダメ計の「対戦の対面」にも反映される')));
  if (!lv || (!B.my_picks.length && !B.opp_picks.length)) { card.append(el('div', { class: 'muted' }, '上で自分と相手の選出を選ぶと出る')); return card; }
  const rankRow = (side, key, mon) => el('div', { class: 'rv-ranks' }, ...['atk', 'def', 'spa', 'spd', 'spe'].map(k => {
    const s = el('select', { 'aria-label': `${STAT_JA[k]}ランク`, onchange: () => { mon.boosts[k] = parseInt(s.value, 10); s.className = mon.boosts[k] > 0 ? 'up' : mon.boosts[k] < 0 ? 'down' : ''; livePutLater({ [side]: { [key]: { boosts: { [k]: mon.boosts[k] } } } }); refreshSummary(); } },
      ...RANKS.map(v => el('option', { value: v, selected: v === (mon.boosts[k] || 0) }, rankText(v))));
    s.className = mon.boosts[k] > 0 ? 'up' : mon.boosts[k] < 0 ? 'down' : '';
    return el('label', {}, STAT_JA[k], s);
  }), el('button', { class: 'mini', title: 'ランクをすべて0に（交代したとき）', onclick: (e) => { e.stopPropagation(); livePut({ [side]: { [key]: { boosts: { atk: 0, def: 0, spa: 0, spd: 0, spe: 0 } } } }).then(draw); } }, '0'));
  const statusSel = (side, key, mon) => { const s = el('select', { 'aria-label': '状態異常', onchange: () => { mon.status = s.value; livePutLater({ [side]: { [key]: { status: s.value } } }); refreshSummary(); } }, ...STATUS.map(([v, t]) => el('option', { value: v, selected: v === mon.status }, t))); return s; };
  const hpBar = (ratio) => el('div', { class: 'hpbar' }, el('span', { class: ratio > 0.5 ? 'hp-g' : ratio > 0.2 ? 'hp-y' : 'hp-r', style: `width:${Math.max(0, Math.min(100, ratio * 100))}%` }));
  const stTag = (mon) => mon.status !== 'none' ? el('span', { class: 'st st-' + mon.status }, STATUS_JA[mon.status]) : '';

  const myRow = el('div', { class: 'live-row' });
  for (const x of B.mine) {
    const key = String(x.index), mon = lv.my[key]; if (!mon) continue;
    const max = x.stats.hp, hp = mon.hp == null ? max : mon.hp;
    const hpIn = el('input', { type: 'number', min: 0, max, value: hp, 'aria-label': 'HP（実数）' });
    hpIn.addEventListener('change', () => { livePut({ my: { [key]: { hp: Math.max(0, Math.min(max, parseInt(hpIn.value || '0', 10))) } } }).then(draw); });
    myRow.append(el('div', { 'data-key': key, class: 'live-card' + (lv.active.my === x.index ? ' active' : '') + (hp <= 0 ? ' fainted' : ''), onclick: () => setActive('my', x.index) },
      el('div', { class: 't' }, monLabel(x.battle_ja), stTag(mon)), hpBar(hp / max),
      el('div', { class: 'live-line' }, el('span', { class: 'hpin' }, 'HP', hpIn, `/ ${max}`), statusSel('my', key, mon)), rankRow('my', key, mon)));
  }
  const oppRow = el('div', { class: 'live-row' });
  for (const o of B.opp_builds) {
    const key = o.base_species, mon = lv.opp[key]; if (!mon) continue;
    const hp = mon.hp == null ? 100 : mon.hp;
    const hpIn = el('input', { type: 'number', min: 0, max: 100, value: hp, 'aria-label': 'HP（%）' });
    hpIn.addEventListener('change', () => { livePut({ opp: { [key]: { hp: Math.max(0, Math.min(100, parseFloat(hpIn.value || '0'))) } } }).then(draw); });
    const extras = [];
    if (B.opp_has_mega[key]) {
      const st = mon.mega_state || 'auto';
      const setMega = (v) => (e) => { e.stopPropagation(); livePut({ opp: { [key]: { mega_state: st === v ? 'auto' : v } } }).then(draw); };
      extras.push(el('div', { class: 'seg' },
        el('button', { class: st === 'yes' ? 'on' : '', title: 'メガシンカした（もう一度押すと未確定に戻す）', onclick: setMega('yes') }, 'メガした'),
        el('button', { class: st === 'no' ? 'on' : '', title: 'メガシンカしなかった（メガストーン以外の型で表示）', onclick: setMega('no') }, 'メガしなかった'),
        el('small', { class: 'muted' }, st === 'auto' ? (o.mega_hint === false ? '他がメガ済み' : '未確定') : '')));
    }
    oppRow.append(el('div', { 'data-key': key, class: 'live-card opp' + (lv.active.opp === key ? ' active' : '') + (hp <= 0 ? ' fainted' : ''), onclick: () => setActive('opp', key) },
      el('div', { class: 't' }, monLabel(o.battle_ja || o.ja), stTag(mon)), hpBar(hp / 100),
      el('div', { class: 'live-line' }, el('span', { class: 'hpin' }, 'HP', hpIn, '%'), statusSel('opp', key, mon)), ...extras, rankRow('opp', key, mon)));
  }
  const fsel = (key, label, opts) => { const s = el('select', { onchange: () => { lv.field[key] = s.value; livePut({ field: { [key]: s.value } }).then(refreshRecords); refreshSummary(); } }, ...opts.map(([v, t]) => el('option', { value: v, selected: v === lv.field[key] }, t))); return el('label', { class: 'f' }, label, s); };
  card.append(el('div', { class: 'rv-sidehead side-me' }, '自分'), myRow, el('div', { class: 'rv-sidehead side-opp' }, '相手'), oppRow,
    el('div', { class: 'rv-field' }, fsel('weather', '天候', WEATHER), fsel('terrain', 'フィールド', TERRAIN), fsel('my_screen', '自分側の壁', SCREEN), fsel('opp_screen', '相手側の壁', SCREEN)),
    el('div', { class: 'rv-hazards' }, hazardRow(lv, 'my_hazards', '自分側の設置', 'side-me'), hazardRow(lv, 'opp_hazards', '相手側の設置', 'side-opp')));
  return card;
}

// 設置技（出てきたポケモンへの影響は、場に出すポケモンを変えたときに確認する）
function hazardRow(lv, key, label, cls) {
  const h = { rocks: false, spikes: 0, tspikes: 0, web: false, ...(lv.field[key] || {}) };
  const save = (patch) => { lv.field[key] = Object.assign(h, patch); livePut({ field: { [key]: { ...h } } }).then(refreshRecords); };
  const num = (name, max, text) => { const s = el('select', { 'aria-label': text, onchange: () => save({ [name]: parseInt(s.value, 10) }) }, ...[...Array(max + 1).keys()].map(n => el('option', { value: n, selected: h[name] === n }, n ? `${n}層` : 'なし'))); return el('label', { class: 'f' }, text, s); };
  const chk = (name, text) => el('label', { class: 'check' }, el('input', { type: 'checkbox', checked: h[name], onchange: (e) => save({ [name]: e.target.checked }) }), text);
  return el('div', { class: 'hz-row' }, el('b', { class: cls }, label, ' ', help('出てきたポケモンがダメージや状態異常を受ける設置技。場に出すポケモンを変えたとき、その影響を反映するか確認する')),
    chk('rocks', 'ステルスロック'), num('spikes', 3, 'まきびし'), num('tspikes', 2, 'どくびし'), chk('web', 'ねばねばネット'));
}

// ---- 選出カード ----
function kv(rows) { return el('div', { class: 'kv2' }, ...rows.flat()); }
function mineCard(x) {
  const spTxt = STATS.filter(k => x.sp[k]).map(k => `${STAT_JA[k]}${x.sp[k]}`).join(' ') || '無振り';
  return el('div', { class: 'bcard' }, el('div', { class: 't' }, monLabel(x.battle_ja)),
    kv([[el('div', {}, '持ち物'), el('div', {}, x.item_ja || 'なし')], [el('div', {}, '特性'), el('div', {}, x.ability_ja || '不明')], [el('div', {}, '性格'), el('div', {}, x.nature_ja || '不明')],
      [el('div', {}, '能力P'), el('div', {}, spTxt)], [el('div', {}, '技'), el('div', {}, ...x.moves.map(mv => el('div', {}, moveName(mv.ja, mv.id))))],
      [el('div', {}, '実数値'), el('div', { class: 'muted' }, STATS.map(k => `${STAT_JA[k]}${x.stats[k]}`).join(' '))]]));
}
function oppCard(o, picked) {
  const inf = o.inference || {};
  const spTxt = STATS.filter(k => o.sp[k]).map(k => `${STAT_JA[k]}${o.sp[k]}`).join(' ') || '無振り';
  const spSrc = Object.values(o.sp_src || {}).includes('inferred') ? 'inferred' : (o.sp_src || {}).hp || 'usage';
  const ranges = Object.entries(o.stats_range || {}).map(([k, v]) => `${STAT_JA[k]} ${v[0]}〜${v[1]}`).join(' / ');
  const p = (v) => v ? el('small', { class: 'muted' }, ` ${Math.round(v * 100)}%`) : '';
  const rows = [[el('div', {}, '持ち物'), el('div', {}, o.item.ja || '不明', srcTag(o.item.src), p(o.item.p))],
    [el('div', {}, '特性'), el('div', {}, o.ability.ja || '不明', srcTag(o.ability.src))],
    [el('div', {}, '性格'), el('div', {}, o.nature.ja || '不明', srcTag(o.nature.src), p(o.nature.p))],
    [el('div', {}, '能力P'), el('div', {}, spTxt, srcTag(spSrc))],
    [el('div', {}, '技'), el('div', {}, ...o.moves.map(mv => el('div', {}, moveName(mv.ja, mv.id), srcTag(mv.src))))],
    [el('div', {}, '実数値'), el('div', { class: 'muted' }, STATS.map(k => `${STAT_JA[k]}${o.stats[k]}`).join(' '))]];
  if (ranges) rows.push([el('div', {}, '逆算範囲'), el('div', { class: 'muted' }, ranges)]);
  const card = el('div', { class: 'bcard' + (picked ? '' : ' dim') }, el('div', { class: 't' }, monLabel(o.battle_ja || o.ja), picked ? '' : el('small', { class: 'muted' }, '（選出外・記録あり）')), kv(rows));
  if (inf.records) {
    const det = el('details', {}, el('summary', {}, `逆算の候補（記録${inf.records}件・組み合わせ${inf.candidates}通り）`));
    if (!inf.feasible) det.append(el('div', { class: 'err' }, '全記録を同時に満たす候補が無い。記録の入力値・条件を確認'));
    for (const n of inf.by_nature || []) det.append(el('div', {}, `${n.ja} ${Math.round(n.p * 100)}%: `, Object.entries(n.ranges).map(([k, v]) => `${STAT_JA[k]}${v[0]}〜${v[1]}`).join(' ')));
    det.append(el('div', {}, '持ち物: ', (inf.items || []).map(i => `${i.ja} ${Math.round(i.p * 100)}%`).join(' / ')));
    det.append(el('div', {}, '特性: ', (inf.abilities || []).map(i => `${i.ja} ${Math.round(i.p * 100)}%`).join(' / ')));
    for (const nt of inf.notes || []) det.append(el('div', { class: 'muted' }, nt));
    card.append(det);
  }
  return card;
}
function mineCol() {
  const c = el('div', { class: 'sidebox me' }, el('h3', {}, '自分の選出'));
  B.mine.forEach(x => c.append(mineCard(x)));
  if (!B.mine.length) c.append(el('div', { class: 'muted' }, '上で選出を選ぶと出る'));
  return c;
}
function oppCol() {
  const c = el('div', { class: 'sidebox opp' }, el('h3', {}, '相手の選出 ', el('small', {}, srcTag('confirmed'), srcTag('inferred'), srcTag('usage'), srcTag('estimate')), help('確定=見えた情報、逆算=記録から絞り込んだ値、採用率=環境データの上位、推定=種族値からの推定')));
  B.opp_builds.concat(B.other_builds || []).forEach(o => c.append(oppCard(o, B.opp_builds.includes(o))));
  if (!B.opp_builds.length) c.append(el('div', { class: 'muted' }, '上で相手の選出を選ぶと出る'));
  return c;
}
// 閉じられるセクション
function fold(key, title, tip, ...kids) {
  const d = el('details', { class: 'card fold', open: openState[key] ? true : undefined, ontoggle: () => { openState[key] = d.open; } },
    el('summary', {}, el('h2', {}, title, ' ', tip ? help(tip) : '')), ...kids);
  return d;
}
function detailCard() { return fold('detail', '構築の詳細', '選出した3体ずつの型。相手は記録から絞り込んだ内容', el('div', { class: 'grid2 rv-two' }, mineCol(), oppCol())); }

// ---- 控え相性 ----
function matrixCard() {
  const card = fold('bench', '控え相性', '選出した3体どうしの対面表と素早さ。上段が自分の最大打点、下段が相手の最大打点。緑は有利、赤は不利');
  if (!(B.matrix.length && B.opp_builds.length)) { card.append(el('div', { class: 'muted' }, '自分と相手の選出を選ぶと出る')); return card; }
  const line = (who, mv, id, p, hits) => el('div', { class: 'mx-line' + (who === '相' ? ' muted' : '') }, el('span', { class: 'mx-who' }, who), mv ? moveName(mv, id) : '-', el('span', { class: 'mx-pct' }, ` ${pct(p)}`), hits ? el('small', {}, `（${hits}発）`) : '');
  const t = el('table', { class: 'mx' }, el('tr', {}, el('th', {}, ''), ...B.opp_builds.map(o => el('th', {}, monLabel(o.battle_ja || o.ja, true)))));
  B.matrix.forEach((row, i) => t.append(el('tr', {}, el('th', {}, monLabel(B.mine[i].battle_ja)), ...row.map(x =>
    el('td', { class: x.score >= 0.75 ? 'cell-good' : x.score <= 0.25 ? 'cell-bad' : 'cell-mid' }, line('自', x.a_move, x.a_move_id, x.a_pct, x.a_hits), line('相', x.b_move, x.b_move_id, x.b_pct, x.b_hits))))));
  card.append(el('div', { class: 'scroll-x' }, t));
  if (B.speed.length) {
    const lad = el('div', { class: 'ladder', style: 'margin-top:14px' });
    for (const r of B.speed) lad.append(el('div', { class: 'lrow ' + r.side },
      el('div', { class: 'lcell l' }, r.side === 'me' ? el('span', { class: 'lbadge me' }, r.ja) : ''), el('div', { class: 'lnum' }, r.speed),
      el('div', { class: 'lcell r' }, r.side === 'opp' ? el('span', { class: 'lbadge opp' }, el('small', {}, r.ja), r.label) : '')));
    card.append(lad);
  }
  return card;
}

// ---- 記録フォーム ----
let refreshSummary = () => {};
let refreshForm = () => {};
function screenOn(v, physical) { return v === 'both' || (physical ? v === 'reflect' : v === 'lightscreen'); }

function formCard() {
  const card = el('div', { class: 'card', id: 'rv-form' });
  refreshForm = () => { card.innerHTML = ''; buildForm(card); fitRecords(); };
  buildForm(card);
  return card;
}

function buildForm(box) {
  const lv = B.live;
  const f = edit ? JSON.parse(JSON.stringify(edit)) : { kind, cond: {} };
  f.cond = f.cond || {};
  if (!edit && lv) { f.opp = lv.active.opp; f.my_index = lv.active.my; }
  if (!edit && prefill) {
    const oppIds = B.opp_picks.length ? B.opp_picks : B.match.opp;
    if (prefill.opp && oppIds.includes(prefill.opp)) f.opp = prefill.opp;
    const mi = prefill.mySpecies ? B.my_team.findIndex(x => x.species === prefill.mySpecies) : -1;
    if (mi >= 0 && (B.my_picks.length ? B.my_picks.includes(mi) : true)) f.my_index = mi;
    Object.assign(f, { kind: prefill.kind, move: prefill.move, move_ja: prefill.move_ja, reveal_type: 'move', reveal_value: prefill.move, reveal_value_ja: prefill.move_ja });
  }
  box.append(el('div', { class: 'sec-title' }, el('h2', {}, edit ? '記録を直す' : '記録/逆ダメ計 ', help('被ダメ・与ダメ・判明した情報から、相手の性格・能力ポイント・持ち物・特性を逆算する。技の確定効果（ランク変化・状態異常・設置・天候など）は、追加すると現在の対面にも反映する')),
    !edit && lastEffects.length ? el('small', { class: 'fx-note', title: '直近の記録で、技の効果として自動で反映した内容' }, `反映: ${lastEffects.join('・')}`) : ''));
  box.append(el('div', { class: 'seg wide' }, ...[['taken', '被ダメ（相手→自分）'], ['dealt', '与ダメ（自分→相手）'], ['reveal', '判明（技・特性・持ち物）']].map(([k, t]) =>
    el('button', { class: f.kind === k ? 'on' : '', onclick: () => { if (edit) return; kind = k; prefill = null; refreshForm(); } }, t))));
  const oppList = B.opp_picks.length ? B.opp_picks : B.match.opp;
  const oppName = (sid) => B.match.opp_ja[B.match.opp.indexOf(sid)];
  const oppSel = el('select', {}, ...oppList.map(sid => el('option', { value: sid, selected: sid === f.opp }, oppName(sid))));
  const myList = B.my_picks.length ? B.my_picks : B.my_team.map(x => x.index);
  const mySel = el('select', {}, ...myList.map(i => el('option', { value: i, selected: i === f.my_index }, B.my_team[i].ja)));
  const grid = el('div', { class: 'rv-grid' });
  const lbl = (t, n) => el('label', { class: 'f' }, t, n);
  const done = async (body) => {
    try {
      await flushNow();
      B = edit ? await api(`/api/battle/records/${edit.id}`, { method: 'PUT', body }) : await api('/api/battle/records', { method: 'POST', body });
      const was = edit; edit = null; prefill = null;
      lastEffects = was ? [] : ((B.records.filter(r => r.kind !== 'log').slice(-1)[0] || {}).effects || []);
      draw(); toast(was ? '記録を更新した' : '記録を追加し、HPを反映した');
    } catch (e) { toast('入力を確認: ' + errMsg(e)); }
  };
  const actions = (onSubmit, hint) => el('div', { class: 'row', style: 'margin-top:12px' }, el('button', { class: 'btn primary small', onclick: onSubmit }, edit ? '更新' : '追加'),
    edit ? el('button', { class: 'btn small ghost', onclick: () => { edit = null; refreshForm(); } }, 'キャンセル') : '',
    el('button', { class: 'btn small alt', title: 'ダメ計の技の一覧から、記録したい技を選ぶ', onclick: () => { S.focusMoves = true; location.hash = 'calc'; } }, '技一覧から選ぶ'),
    hint ? el('small', { class: 'muted' }, hint) : '');

  if (f.kind === 'reveal') {
    const typeSel = el('select', {}, ...[['move', '技'], ['ability', '特性'], ['item', '持ち物']].map(([v, t]) => el('option', { value: v, selected: f.reveal_type === v }, t)));
    const valBox = el('div'); let valPicker;
    const mk = () => { valBox.innerHTML = ''; const k = { item: 'items', move: 'moves', ability: 'abilities' }[typeSel.value];
      valPicker = picker({ kind: k, value: f.reveal_value, label: f.reveal_value_ja || '', placeholder: '名前', species: () => k === 'items' ? null : oppSel.value }); valBox.append(valPicker); };
    typeSel.addEventListener('change', mk); oppSel.addEventListener('change', mk); mk();
    grid.append(lbl('相手', oppSel), lbl('種類', typeSel), lbl('内容', valBox));
    box.append(grid, actions(() => done({ kind: 'reveal', opp: oppSel.value, reveal_type: typeSel.value, reveal_value: valPicker.input.dataset.id || null })));
    return;
  }

  const taken = f.kind === 'taken';
  let moveInfo = { id: f.move || null, category: null };
  const moveBox = el('div');
  const mkMove = () => {
    moveBox.innerHTML = '';
    if (taken) {
      const mp = picker({ kind: 'moves', value: f.move, label: f.move_ja || '', placeholder: '相手の技', species: () => oppSel.value,
        onPick: (it) => { moveInfo = it ? { id: it.id, category: it.category } : { id: null }; updSummary(); } });
      moveBox.append(mp);
      mp.input.addEventListener('input', () => { moveInfo = { id: null }; });
      if (f.move) moveInfo = { id: f.move, category: null };
    } else {
      const my = B.my_team[parseInt(mySel.value, 10)];
      const ms = el('select', { onchange: () => { const x = my.moves.find(q => q.id === ms.value); moveInfo = { id: ms.value, category: x && x.category }; updSummary(); } },
        ...(my ? my.moves : []).map(mv => el('option', { value: mv.id, selected: mv.id === f.move }, mv.ja)));
      moveBox.append(ms);
      const x = my && my.moves.find(q => q.id === ms.value); moveInfo = { id: ms.value || null, category: x && x.category };
    }
  };
  const liveMy = () => lv && lv.my[String(mySel.value)];
  const liveOpp = () => lv && lv.opp[oppSel.value];
  const myMax = () => { const x = B.mine.find(q => q.index === parseInt(mySel.value, 10)); return x ? x.stats.hp : B.my_team[parseInt(mySel.value, 10)].hp; };
  const curBefore = () => taken ? (liveMy() && liveMy().hp != null ? liveMy().hp : myMax()) : (liveOpp() && liveOpp().hp != null ? liveOpp().hp : 100);
  const before = el('input', { type: 'number', value: f.before != null ? f.before : curBefore() });
  const after = el('input', { type: 'number', value: f.after != null ? f.after : '' });
  const ko = el('input', { type: 'checkbox', checked: !!f.cond.ko });
  const miss = el('input', { type: 'checkbox', checked: !!f.cond.miss });
  const crit = el('input', { type: 'checkbox', checked: !!f.cond.crit });
  const hits = el('select', {}, el('option', { value: '' }, '1回'), ...[2, 3, 4, 5].map(n => el('option', { value: n, selected: f.cond.hits === n }, `${n}回`)));
  mySel.addEventListener('change', () => { mkMove(); if (!edit) before.value = curBefore(); updSummary(); });
  oppSel.addEventListener('change', () => { mkMove(); if (!edit) before.value = curBefore(); updSummary(); });
  mkMove();
  grid.append(lbl(taken ? '攻撃した相手' : '攻撃された相手', oppSel), lbl(taken ? '受けた自分' : '攻撃した自分', mySel), lbl('技', moveBox),
    lbl(taken ? '受ける前のHP（実数）' : '当てる前の相手HP（%）', before), lbl(taken ? '受けた後のHP（実数）' : '当てた後の相手HP（%）', after), lbl('連続技', hits),
    el('label', { class: 'check' }, ko, 'この攻撃で倒れた'), el('label', { class: 'check' }, crit, '急所'),
    el('label', { class: 'check', title: '技が外れた・効果がなかったときは、ダメージの逆算に使わない' }, miss, '不発・効果なし'));
  box.append(grid);

  const summary = el('div', { class: 'cond-summary' });
  const condFromLive = () => {
    const physical = moveInfo.category ? moveInfo.category === 'Physical' : true;
    const [ak, dk] = physical ? ['atk', 'def'] : ['spa', 'spd'];
    const me = liveMy() || { boosts: {}, status: 'none' }, op = liveOpp() || { boosts: {}, status: 'none', mega: false };
    const att = taken ? op : me, dfd = taken ? me : op;
    return { weather: lv ? lv.field.weather : 'none', terrain: lv ? lv.field.terrain : 'none',
      atk_boost: att.boosts[ak] || 0, def_boost: dfd.boosts[dk] || 0, atk_status: att.status || 'none', def_status: dfd.status || 'none',
      screen: screenOn(lv ? lv.field[taken ? 'my_screen' : 'opp_screen'] : 'none', physical), opp_mega: op.mega_state === 'yes' || !!op.mega, _uncat: !moveInfo.category };
  };
  function updSummary() {
    if (edit) return;
    const c = condFromLive();
    const W = { none: '', sun: '晴れ', rain: '雨', sand: '砂嵐', snow: '雪' }, T = { none: '', electric: 'エレキF', grassy: 'グラスF', psychic: 'サイコF', misty: 'ミストF' };
    const parts = [W[c.weather], T[c.terrain], c.atk_boost ? `攻撃側${rankText(c.atk_boost)}` : '', c.def_boost ? `防御側${rankText(c.def_boost)}` : '',
      c.atk_status !== 'none' ? `攻撃側${STATUS_JA[c.atk_status]}` : '', c.def_status !== 'none' ? `防御側${STATUS_JA[c.def_status]}` : '', c.screen ? '壁' : '', c.opp_mega ? '相手メガ後' : ''].filter(Boolean);
    summary.textContent = '条件（現在の対面から）: ' + (parts.join('・') || 'なし') + (c._uncat ? '　※技を選ぶと物理/特殊に合わせてランクを選び直す' : '');
  }
  refreshSummary = updSummary;
  let condGrid = null;
  if (edit) {
    const tri = (key, label) => { const s = el('select', {}, el('option', { value: '' }, '未入力'), el('option', { value: 'false' }, 'なし'), el('option', { value: 'true' }, 'あり'));
      s.value = f.cond[key] === true ? 'true' : f.cond[key] === false ? 'false' : ''; s.dataset.key = key; s.dataset.t = 'bool'; return lbl(label, s); };
    const opt = (key, label, opts, t = 'str') => { const s = el('select', {}, el('option', { value: '' }, '未入力'), ...opts.map(([v, tt]) => el('option', { value: v }, tt)));
      s.value = f.cond[key] != null ? String(f.cond[key]) : ''; s.dataset.key = key; s.dataset.t = t; return lbl(label, s); };
    const ranks = RANKS.map(v => [String(v), rankText(v)]);
    if (f.cond.atk_status == null && f.cond.burn) f.cond.atk_status = 'brn';
    condGrid = el('div', { class: 'rv-grid' }, opt('weather', '天候', WEATHER), opt('terrain', 'フィールド', TERRAIN), opt('atk_boost', '攻撃側ランク', ranks, 'int'), opt('def_boost', '防御側ランク', ranks, 'int'),
      opt('atk_status', '攻撃側の状態異常', STATUS), opt('def_status', '防御側の状態異常', STATUS), tri('screen', '防御側の壁'), tri('opp_mega', '相手がメガシンカ後'));
    box.append(el('div', { class: 'muted', style: 'margin-top:10px' }, '条件（この記録だけ修正）'), condGrid);
  } else { box.append(summary); updSummary(); }
  const collect = () => {
    let cond;
    if (edit) { cond = {}; condGrid.querySelectorAll('select[data-key]').forEach(s => { if (s.value === '') return; cond[s.dataset.key] = s.dataset.t === 'bool' ? s.value === 'true' : s.dataset.t === 'int' ? parseInt(s.value, 10) : s.value; }); }
    else { cond = condFromLive(); delete cond._uncat; }
    if (ko.checked) cond.ko = true;
    if (crit.checked) cond.crit = true;
    if (miss.checked) cond.miss = true;
    if (hits.value) cond.hits = parseInt(hits.value, 10);
    return { kind: f.kind, opp: oppSel.value, my_index: parseInt(mySel.value, 10), move: moveInfo.id,
      before: before.value === '' ? null : parseFloat(before.value), after: ko.checked && after.value === '' ? 0 : (after.value === '' ? (miss.checked && before.value !== '' ? parseFloat(before.value) : null) : parseFloat(after.value)), cond };
  };
  box.append(actions(() => done(collect()), taken ? '自分のHPは実数（画面の数値）' : '相手のHPは画面の%'));
}

// ---- 記録一覧 ----
let recordsEl = null;
// 現在の対面を変えたあと、ログが増えた一覧を出し直す（保存の応答で B は最新になっている）
function refreshRecords() {
  if (!recordsEl || !document.body.contains(recordsEl)) return;
  fillRecords();
}
function recordsCard() { recordsEl = el('div', { class: 'card rec-card' }); fillRecords(); return recordsEl; }
function fillRecords() {
  const card = recordsEl; card.innerHTML = '';
  const logN = B.records.filter(r => r.kind === 'log').length;
  card.append(el('div', { class: 'sec-title' }, el('h2', {}, '記録一覧 ', help('被ダメ・与ダメ・判明は型の逆算に使う。「ログ」は、現在の対面を手で直したときの変化（項目・変化前・変化後）で、逆算には使わない')),
    el('label', { class: 'check' }, el('input', { type: 'checkbox', checked: showLogs, onchange: (e) => { showLogs = e.target.checked; fillRecords(); } }), `ログを表示${logN ? `（${logN}）` : ''}`)));
  const rows = B.records.filter(r => showLogs || r.kind !== 'log');
  if (!rows.length) { card.append(el('div', { class: 'muted' }, 'まだ記録が無い')); return; }
  const list = el('div', { class: 'rec-list' });
  // 新しいものを先頭にする（番号も新しいほど大きい）
  rows.map((r, i) => [r, i + 1]).reverse().forEach(([r, n]) => {
    const del = el('button', { class: 'btn small ghost', onclick: async () => { const v = await api(`/api/battle/records/${r.id}`, { method: 'DELETE' }); B = v; draw(); toast((v.reverted || []).length ? `削除した（戻した: ${v.reverted.join('・')}）` : '削除した'); } }, '削除');
    if (r.kind === 'log') { list.append(el('div', { class: 'rec-row log' }, el('div', { class: 'rec-top' }, el('span', { class: 'n' }, n), el('span', { class: 'kind kind-log' }, 'ログ')), el('div', { class: 'muted' }, r.summary), el('div', { class: 'row' }, del))); return; }
    list.append(el('div', { class: 'rec-row' + (r.feasible === 0 ? ' bad' : '') },
      el('div', { class: 'rec-top' }, el('span', { class: 'n' }, n), el('span', { class: 'kind kind-' + r.kind }, r.kind_short || r.kind_ja),
        r.chip_move && moveType(r.chip_move) ? typeChip(moveType(r.chip_move), '', true) : '',
        r.feasible == null ? '' : el('small', { class: 'muted', title: '観測値と矛盾しない組み合わせの数。0なら入力か条件の誤り' }, `候補 ${r.feasible}`)),
      el('div', {}, r.summary),
      (r.effects || []).length ? el('div', { class: 'fx-note' }, `反映: ${r.effects.join('・')}`) : '',
      el('div', { class: 'row' },
        el('button', { class: 'btn small ghost', onclick: async () => {
          const e2 = JSON.parse(JSON.stringify(r));
          if (e2.my) e2.my_index = B.my_team.findIndex(x => x.species === e2.my.species);
          if (e2.move) e2.move_ja = await jaOf('moves', e2.move);
          if (e2.reveal_value) e2.reveal_value_ja = await jaOf({ item: 'items', move: 'moves', ability: 'abilities' }[e2.reveal_type], e2.reveal_value);
          prefill = null; edit = e2; refreshForm(); const f = $('#rv-form'); if (f) f.scrollIntoView({ behavior: 'smooth', block: 'start' }); } }, '編集'), del)));
  });
  card.append(el('div', { class: 'rec-scroll' }, list));
  fitRecords();
}
// 一覧の高さは、横に並ぶ「記録/逆ダメ計」と同じにする（縦に積むときは固定）。中でスクロールする
function fitRecords() {
  requestAnimationFrame(() => {
    const sc = recordsEl && recordsEl.querySelector('.rec-scroll'), form = $('#rv-form');
    if (!sc || !form) return;
    sc.style.maxHeight = '420px';   // 縦に積むとき
    if (window.innerWidth > 820) {  // 横に並ぶときは「記録/逆ダメ計」の高さに合わせる（両方とも上揃えで、一覧の中だけスクロール）
      const room = form.offsetHeight - (sc.getBoundingClientRect().top - recordsEl.getBoundingClientRect().top) - 20;
      sc.style.maxHeight = Math.max(240, room) + 'px';
    }
  });
}
