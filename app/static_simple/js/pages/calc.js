import { $, el, api, lead, toast, picker, help, typeChip, debounce } from '../ui.js';
import { S, dexInfo, loadMeta, loadTypes } from '../store.js';
import { STATS, STAT_JA, spGrid } from '../parts.js';

const blank = () => ({ species: null, ja: '', nature: null, sp: {}, ability: null, item: null, item_ja: '', boosts: {}, status: 'none', hp_percent: 100, hp: null,
  max_hp: null, mega: false, reflect: false, light_screen: false, aurora_veil: false, moves: [], moves_ja: [], set_moves: [] });
// 画面を行き来しても選んだ内容が残るようモジュールで保持する
const C = { me: blank(), opp: blank(), weather: '', terrain: '', crit: false, myTeam: null, oppIds: null, pred: null };

const STATUS = [['none', 'なし'], ['brn', 'やけど'], ['par', 'まひ'], ['psn', 'どく'], ['tox', 'もうどく'], ['slp', 'ねむり'], ['frz', 'こおり']];
const RANK_LABEL = { atk: 'こうげき', def: 'ぼうぎょ', spa: 'とくこう', spd: 'とくぼう', spe: 'すばやさ' };

const jaOf = async (kind, id) => {
  if (!id) return '';
  const r = await api(`/api/search?kind=${kind}&q=${encodeURIComponent(id)}&limit=1&include_mega=true`);
  return r[0] ? r[0].ja : id;
};

async function setFromSet(side, set, ja) {
  const x = C[side];
  Object.assign(x, blank(), { species: set.species, ja, nature: set.nature, sp: { ...(set.sp || {}) }, ability: set.ability, item: set.item,
    item_ja: await jaOf('items', set.item), moves: [...(set.moves || [])].slice(0, 4),
    moves_ja: await Promise.all((set.moves || []).slice(0, 4).map(m => jaOf('moves', m))), set_moves: [...(set.moves || [])] });
  const d = await dexInfo(set.species);
  if (set.item && d.megas.some(m => m.item === set.item)) x.mega = true;
}

async function draw(view) {
  await loadMeta();
  view.innerHTML = '';
  C.myTeam = (await api('/api/team')).members.filter(m => m.species);
  const o = await api('/api/opponent');
  C.oppIds = o.species.map((id, i) => ({ id, ja: o.ja[i] }));
  try { C.pred = await api('/api/predict'); } catch (e) { C.pred = null; }
  view.append(lead('3', 'ダメ計', '場に出ている自分と相手のポケモンを選ぶだけ。どの技でどれくらい削れるかが、すぐ出る。'));
  const sides = el('div', { class: 'duel' }, sideCard('me'), el('div', { class: 'vs' }, 'VS'), sideCard('opp'));
  view.append(sides, fieldCard(), el('div', { id: 'calc-out' }));
  run();
}

export default { key: 'calc', label: 'ダメ計', badge: '3', render: draw };

function quickButtons(side) {
  const box = el('div', { class: 'quick' });
  if (side === 'me') {
    for (const m of C.myTeam) box.append(el('button', { class: 'chip me', onclick: async () => { await setFromSet('me', m, m._ja || await jaOf('pokemon', m.species)); redraw(); } }, m._ja || m.species));
    if (!C.myTeam.length) box.append(el('span', { class: 'muted' }, 'パーティが空: ', el('a', { href: '#team' }, '① パーティ'), 'で登録'));
  } else {
    for (const o of C.oppIds) box.append(el('button', { class: 'chip opp', onclick: async () => {
      const p = C.pred && (C.pred.opponent || []).find(q => q.species === o.id);
      if (p) await setFromSet('opp', p.set, p.ja); else { const d = await dexInfo(o.id); await setFromSet('opp', d.likely_set, d.ja); }
      redraw();
    } }, o.ja));
    if (!C.oppIds.length) box.append(el('span', { class: 'muted' }, '相手の6体は ', el('a', { href: '#select' }, '② 選出'), ' で入力（ここで直接検索もできる）'));
  }
  return box;
}

const redraw = () => draw($('#view'));

function sideCard(side) {
  const x = C[side], isMe = side === 'me';
  const card = el('div', { class: 'card side ' + side });
  const sp = picker({ kind: 'pokemon', value: x.species, label: x.ja, placeholder: isMe ? '自分のポケモンを検索' : '相手のポケモンを検索',
    onPick: async (it) => { if (!it) return; const d = await dexInfo(it.id); await setFromSet(side, d.likely_set, d.ja); redraw(); } });
  card.append(el('h2', {}, isMe ? '🔵 自分' : '🔴 相手'), quickButtons(side), sp);
  if (x.species) {
    const info = el('div', { class: 'side-info' });
    (async () => {
      const d = await dexInfo(x.species);
      const ja = Object.fromEntries((await loadTypes()).types.map(t => [t.id, t.ja]));
      info.append(...d.types.map(t => typeChip(t, ja[t])));
    })();
    card.append(info, el('div', { class: 'muted setline' }, [x.item_ja ? `@${x.item_ja}` : null, isMe && x.moves_ja.length ? x.moves_ja.join('/') : null].filter(Boolean).join('　')));
    card.append(detail(side));
  }
  return card;
}

function labelled(text, node, tip) { return el('label', { class: 'f' }, tip ? [text, help(tip)] : text, node); }

function detail(side) {
  const x = C[side], isMe = side === 'me';
  const d = el('details', { class: 'detail' }, el('summary', {}, '⚙️ くわしく設定'));
  const body = el('div', { class: 'detail-body' });
  const upd = () => run();

  // --- いまの状態 ---
  const hp = isMe
    ? el('input', { type: 'number', min: 0, value: x.hp ?? '', placeholder: '満タン', oninput: (e) => { x.hp = e.target.value === '' ? null : parseInt(e.target.value, 10); upd(); } })
    : el('input', { type: 'number', min: 1, max: 100, value: x.hp_percent, oninput: (e) => { x.hp_percent = parseFloat(e.target.value || '100'); upd(); } });
  const status = el('select', { onchange: (e) => { x.status = e.target.value; upd(); } }, ...STATUS.map(([v, t]) => el('option', { value: v, selected: (x.status || 'none') === v }, t)));
  const ranks = el('div', { class: 'ranks' }, ...Object.keys(RANK_LABEL).map(k => {
    const s = el('select', { onchange: () => { x.boosts[k] = parseInt(s.value, 10); upd(); } },
      ...[...Array(13).keys()].map(i => 6 - i).map(v => el('option', { value: v, selected: (x.boosts[k] || 0) === v }, v > 0 ? `+${v}` : `${v}`)));
    return labelled(RANK_LABEL[k], s);
  }));
  const scr = (key, label) => el('label', { class: 'check' }, el('input', { type: 'checkbox', checked: x[key], onchange: (e) => { x[key] = e.target.checked; upd(); } }), label);
  body.append(el('h3', {}, '🔥 いまの状態'),
    el('div', { class: 'row' }, el('div', { class: 'grow' }, labelled(isMe ? '残りHP（数値）' : '残りHP（%）', hp, isMe ? '空欄なら満タン' : '相手のHPバーの%')),
      el('div', { class: 'grow' }, labelled('状態異常', status))),
    labelled('能力ランク', ranks, '技で上がり下がりした能力の段階。+1で1.5倍、+2で2倍…（−側は逆）'),
    el('div', { class: 'row', style: 'margin-top:8px' }, el('b', { class: 'muted' }, isMe ? '自分側の壁' : '相手側の壁'), scr('reflect', 'リフレクター'), scr('light_screen', 'ひかりのかべ'), scr('aurora_veil', 'オーロラベール')));

  // --- 型 ---
  const nature = el('select', { onchange: (e) => { x.nature = e.target.value || null; upd(); } }, el('option', { value: '' }, '性格'),
    ...S.meta.natures.map(n => el('option', { value: n.id, selected: n.id === x.nature }, `${n.ja}（${n.label}）`)));
  const ab = el('select', { onchange: (e) => { x.ability = e.target.value || null; upd(); } });
  const item = picker({ kind: 'items', value: x.item, label: x.item_ja, placeholder: '持ち物', onPick: (it) => { x.item = it ? it.en : null; x.item_ja = it ? it.ja : ''; upd(); } });
  const megaBox = el('div');
  (async () => {
    const dd = await dexInfo(x.species);
    ab.append(el('option', { value: '' }, '特性なし'), ...dd.abilities.map(a => el('option', { value: a.en, selected: a.en === x.ability }, a.ja)));
    item.input.disabled = dd.megas.some(m => m.item === x.item);
    if (!dd.megas.length) return;
    const cur = dd.megas.find(m => m.item === x.item) || null;
    const apply = (mg) => {
      if (mg) { x.item = mg.item; x.item_ja = mg.item_ja; x.mega = true; item.setValue(mg.item, mg.item_ja); item.input.disabled = true; }
      else { x.mega = false; if (dd.megas.some(q => q.item === x.item)) { x.item = null; x.item_ja = ''; item.setValue('', ''); } item.input.disabled = false; }
      upd();
    };
    if (dd.megas.length === 1) megaBox.append(el('label', { class: 'check' }, el('input', { type: 'checkbox', checked: !!cur, onchange: (e) => apply(e.target.checked ? dd.megas[0] : null) }), `メガシンカ後で計算（${dd.megas[0].ja}）`));
    else { const s = el('select', { onchange: () => apply(dd.megas.find(m => m.id === s.value) || null) }, el('option', { value: '' }, 'メガシンカしない'), ...dd.megas.map(m => el('option', { value: m.id, selected: cur && cur.id === m.id }, m.ja))); megaBox.append(labelled('メガシンカ', s)); }
  })();
  body.append(el('h3', {}, '🧬 型（性格・特性・持ち物…）'),
    el('div', { class: 'row' }, el('div', { class: 'grow' }, labelled('性格', nature, '上がる能力と下がる能力が決まる')), el('div', { class: 'grow' }, labelled('特性', ab))),
    labelled('持ち物', item), megaBox, spGrid(x.sp, upd));
  if (isMe) {
    const mv = el('div', { class: 'moves' });
    for (let i = 0; i < 4; i++) mv.append(picker({ kind: 'moves', value: x.moves[i], label: x.moves_ja[i] || '', placeholder: `技${i + 1}`, species: () => x.species,
      onPick: (it) => { x.moves[i] = it ? it.id : null; x.moves_ja[i] = it ? it.ja : ''; upd(); } }));
    body.append(el('h3', {}, '⚔️ 自分の技'), mv);
  } else {
    body.append(el('p', { class: 'muted', style: 'font-size:13px' }, '相手の技は、よく使われている技（採用率1%以上）がすべて自動で出る。'));
  }
  d.append(body);
  return d;
}

function fieldCard() {
  const sel = (key, opts) => { const s = el('select', { onchange: () => { C[key] = s.value; run(); } }, ...opts.map(([v, t]) => el('option', { value: v, selected: C[key] === v }, t))); return s; };
  return el('div', { class: 'card field' }, el('h2', {}, '🌦️ 場の状態'),
    el('div', { class: 'row' },
      el('div', { class: 'grow' }, labelled('天候', sel('weather', [['', 'なし'], ['sun', '晴れ'], ['rain', '雨'], ['sand', '砂嵐'], ['snow', '雪']]))),
      el('div', { class: 'grow' }, labelled('フィールド', sel('terrain', [['', 'なし'], ['electric', 'エレキ'], ['grassy', 'グラス'], ['psychic', 'サイコ'], ['misty', 'ミスト']]))),
      el('label', { class: 'check' }, el('input', { type: 'checkbox', checked: C.crit, onchange: (e) => { C.crit = e.target.checked; run(); } }), '急所に当たる', help('急所に当たったときのダメージで計算する'))));
}

const KO_HOT = (ko) => /^(確定1|乱数1)/.test(ko);

function moveRow(x) {
  const immune = x.effectiveness === 0;
  const tag = x.rate != null ? `採用率${x.rate}%` : x.src === 'set' ? '型の技' : '';
  const effText = immune ? '' : x.effectiveness > 1 ? '効果は抜群' : x.effectiveness < 1 ? 'いまひとつ' : '';
  const ko = immune ? '効果なし' : x.ko;
  return el('div', { class: 'mrow' + (immune ? ' immune' : '') },
    el('div', { class: 'm-name' }, typeChip(x.type, x.move, false), el('small', { class: 'muted' }, ` 威力${x.base_power}${tag ? '・' + tag : ''}`)),
    immune ? '' : el('div', { class: 'm-bar', title: `${x.min}〜${x.max}ダメージ` }, el('span', { class: 'max', style: `width:${Math.min(100, x.max_pct)}%` }), el('span', { class: 'min', style: `width:${Math.min(100, x.min_pct)}%` })),
    el('div', { class: 'm-num' }, immune ? '' : el('b', {}, `${x.min_pct}〜${x.max_pct}%`), ' ', el('span', { class: 'ko' + (KO_HOT(ko) ? ' hot' : '') }, ko)),
    (effText || x.notes.length) ? el('div', { class: 'm-notes muted' }, [effText, ...x.notes].filter(Boolean).join('・')) : '');
}

function statusRow(x) {
  const e = x.effect || { text: '変化技', notes: [], fails: '' };
  return el('div', { class: 'mrow status' + (e.fails ? ' immune' : '') }, el('div', { class: 'm-name' }, el('b', {}, x.move), el('small', { class: 'muted' }, ' 変化技')),
    el('div', {}, e.text), e.fails ? el('div', { class: 'err' }, `この対面では無効・失敗: ${e.fails}`) : '', e.notes.length ? el('div', { class: 'm-notes muted' }, e.notes.join(' / ')) : '');
}

const run = debounce(async () => {
  const out = $('#calc-out'); if (!out) return;
  const me = C.me, op = C.opp;
  if (!me.species || !op.species) {
    out.innerHTML = '';
    out.append(el('div', { class: 'card', style: 'margin-top:18px' }, el('div', { class: 'empty' }, el('div', { class: 'big' }, '⚔️'), '自分と相手のポケモンを選ぶと、ダメージが出る')));
    return;
  }
  const side = (x, isMe) => ({ species: x.species, nature: x.nature, sp: x.sp, ability: x.ability, item: x.item, boosts: x.boosts, status: x.status && x.status !== 'none' ? x.status : null,
    hp_percent: x.hp_percent, hp: isMe && x.hp != null ? x.hp : null, mega: x.mega, reflect: !!x.reflect, light_screen: !!x.light_screen, aurora_veil: !!x.aurora_veil, moves: x.set_moves || [] });
  try {
    const r = await api('/api/calc/duel', { method: 'POST', body: { me: side(me, true), opp: side(op, false), my_moves: me.moves.filter(Boolean),
      weather: C.weather || null, terrain: C.terrain || null, crit: C.crit } });
    me.max_hp = r.me.stats.hp;
    out.innerHTML = '';
    const mf = r.me.speed, of = r.opp.speed;
    const first = mf > of ? `${r.me.ja}が先に動く` : mf < of ? `${r.opp.ja}が先に動く` : '同じ速さ（運しだい）';
    out.append(el('div', { class: 'speedbar' }, el('span', {}, '⚡ すばやさ'), el('b', { class: 'me-c' }, `${r.me.ja} ${mf}`), 'vs', el('b', { class: 'opp-c' }, `${r.opp.ja} ${of}`),
      el('span', { class: 'first' }, first), help('ランク・スカーフ・まひなどを含めた、実際の素早さ。大きい方が先に動く（トリックルームは逆）')));
    const col = (title, hpTxt, rows, empty) => {
      const attacks = rows.filter(x => x.category !== 'Status'), status = rows.filter(x => x.category === 'Status');
      const c = el('div', { class: 'card res' }, el('h2', {}, title), el('div', { class: 'muted hp' }, hpTxt));
      if (!attacks.length) c.append(el('p', { class: 'muted' }, empty));
      attacks.forEach(x => c.append(moveRow(x)));
      if (status.length) c.append(el('details', {}, el('summary', {}, `変化技（${status.length}）`), ...status.map(statusRow)));
      return c;
    };
    out.append(el('div', { class: 'grid2', style: 'margin-top:18px' },
      col(`🔵 ${r.me.ja} → ${r.opp.ja}`, `相手のHP ${r.opp.current_hp} / ${r.opp.stats.hp}`, r.to_opp, '自分の技が未設定。「くわしく設定」で技を入れよう'),
      col(`🔴 ${r.opp.ja} → ${r.me.ja}`, `自分のHP ${r.me.current_hp} / ${r.me.stats.hp}`, r.to_me, '技のデータがない')));
  } catch (e) { out.textContent = '計算エラー: ' + e.message; }
}, 200);
