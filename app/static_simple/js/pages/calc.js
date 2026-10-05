import { $, el, api, lead, toast, picker, help, typeChip, debounce } from '../ui.js';
import { S, dexInfo, loadMeta, monLabel } from '../store.js';
import { STATS, STAT_JA, spGrid } from '../parts.js';

const blank = () => ({ species: null, ja: '', nature: null, sp: {}, ability: null, item: null, item_ja: '', boosts: {}, status: 'none', hp_percent: 100, hp: null,
  max_hp: null, mega: false, reflect: false, light_screen: false, aurora_veil: false, moves: [], moves_ja: [], set_moves: [] });
// 画面を行き来しても選んだ内容が残るようモジュールで保持する
const C = { me: blank(), opp: blank(), weather: '', terrain: '', myTeam: null, oppIds: null, pred: null, open: false, live: null, syncSig: null };

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
  const y = window.scrollY;
  view.innerHTML = '';
  C.myTeam = (await api('/api/team')).members.filter(m => m.species);
  const o = await api('/api/opponent');
  C.oppIds = o.species.map((id, i) => ({ id, ja: o.ja[i] }));
  try { C.pred = await api('/api/predict'); } catch (e) { C.pred = null; }
  // 逆ダメ計の現在の対面が変わっていたら、ダメ計に写す。変わっていなければ、試している内容をそのまま残す
  C.live = await battleLive();
  if (C.live && C.live.sig !== C.syncSig) { await syncFromBattle(C.live); C.syncSig = C.live.sig; }
  view.append(lead('3', 'ダメ計'));
  view.append(liveStrip());
  view.append(el('div', { class: 'duel' }, selectList('me'), el('div', { class: 'vs' }, 'VS'), selectList('opp')), settingsCard(), el('div', { id: 'calc-out' }));
  window.scrollTo(0, y);
  run();
}

export default { key: 'calc', label: 'ダメ計', badge: '3', render: draw };

const redraw = () => draw($('#view'));

// ---- 逆ダメ計の「現在の対面」 ----
async function battleLive() {
  let b; try { b = await api('/api/battle'); } catch (e) { return null; }
  const lv = b && b.match && b.live; if (!lv) return null;
  const me = (b.mine || []).find(x => x.index === lv.active.my), opp = (b.opp_builds || []).find(o => o.base_species === lv.active.opp);
  if (!me && !opp) return null;
  return { lv, me, opp, sig: JSON.stringify({ lv, me: me && me.set, opp: opp && opp.set }) };
}

async function syncFromBattle(a) {
  const { lv, me, opp } = a;
  const scr = (x, v) => { x.reflect = v === 'reflect' || v === 'both'; x.light_screen = v === 'lightscreen' || v === 'both'; x.aurora_veil = false; };
  if (me) {
    await setFromSet('me', me.set, me.ja);
    const x = C.me, mon = lv.my[String(me.index)] || {};
    x.hp = mon.hp == null ? null : mon.hp; x.max_hp = me.stats.hp; x.status = mon.status || 'none'; x.boosts = { ...(mon.boosts || {}) };
    scr(x, lv.field.my_screen);
  }
  if (opp) {
    await setFromSet('opp', opp.set, opp.ja);
    const x = C.opp, mon = lv.opp[opp.base_species] || {};
    x.hp_percent = Math.max(1, mon.hp == null ? 100 : mon.hp); x.status = mon.status || 'none'; x.boosts = { ...(mon.boosts || {}) };
    scr(x, lv.field.opp_screen);
  }
  const f = (v) => (v && v !== 'none') ? v : '';
  C.weather = f(lv.field.weather); C.terrain = f(lv.field.terrain);
}

// 現在の対面（2体）と、その状態へ戻すボタン
function liveStrip() {
  const a = C.live;
  const side = (cls, name) => el('span', { class: 'live-side ' + cls }, name ? monLabel(name) : el('span', { class: 'muted' }, '未選択'));
  return el('div', { class: 'card live-strip' },
    el('div', { class: 'live-names' }, el('b', {}, '対戦の対面 ', help('逆ダメ計で場に出している2体。対面や記録が変わると、ここの設定がその状態に入れ替わる。ここで変えた内容は試すだけで、逆ダメ計には反映されない')),
      a ? [side('me', a.me && a.me.battle_ja), el('span', { class: 'muted' }, 'VS'), side('opp', a.opp && (a.opp.battle_ja || a.opp.ja))] : el('span', { class: 'muted' }, ['なし（', el('a', { href: '#reverse' }, '逆ダメ計'), 'で選出を選ぶと出る）'])),
    el('button', { class: 'btn small alt', disabled: !a, onclick: async () => { await syncFromBattle(a); C.syncSig = a.sig; await redraw(); toast('対戦の対面に戻した'); } }, '対戦の対面に戻す'));
}

// ゲームの選出画面のように、6体を縦に並べて1体を選ぶ
function selectList(side) {
  const isMe = side === 'me', x = C[side];
  const list = isMe ? C.myTeam.map(m => ({ key: m.species, ja: m._ja || m.species, item: m.item, set: m })) : C.oppIds.map(o => ({ key: o.id, ja: o.ja, set: null }));
  const card = el('div', { class: 'card side ' + side }, el('h2', {}, isMe ? '自分' : '相手'));
  if (!list.length) {
    card.append(el('div', { class: 'muted' }, isMe ? ['パーティが空。', el('a', { href: '#team' }, 'パーティ'), 'で登録'] : ['相手の6体が未入力。', el('a', { href: '#select' }, '選出'), 'で入力']));
    return card;
  }
  const col = el('div', { class: 'pick-col' });
  for (const it of list) {
    col.append(el('button', { class: 'pick-btn' + (x.species === it.key ? ' on' : ''), onclick: async () => {
      if (isMe) await setFromSet('me', it.set, it.ja);
      else {
        const p = C.pred && (C.pred.opponent || []).find(q => q.species === it.key);
        if (p) await setFromSet('opp', p.set, p.ja); else { const d = await dexInfo(it.key); await setFromSet('opp', d.likely_set, d.ja); }
      }
      redraw();
    } }, monLabel(it.ja, true)));
  }
  card.append(col);
  return card;
}

function settingsCard() {
  const d = el('details', { class: 'card settings', open: C.open ? true : undefined, ontoggle: () => { C.open = d.open; } },
    el('summary', {}, '追加情報の入力 ', el('small', { class: 'muted' }, '天候・状態異常・ランク・持ち物など')));
  d.append(fieldBlock());
  const sides = el('div', { class: 'grid2 side-settings' });
  for (const side of ['me', 'opp']) {
    const x = C[side];
    sides.append(el('div', { class: 'side-set ' + side }, el('h3', {}, side === 'me' ? '自分' : '相手', x.species ? ` ${x.ja}` : ''),
      x.species ? detailBody(side) : el('div', { class: 'muted' }, 'ポケモンを選ぶと設定できる')));
  }
  d.append(sides);
  return d;
}

function labelled(text, node, tip) { return el('label', { class: 'f' }, tip ? [text, help(tip)] : text, node); }

function detailBody(side) {
  const x = C[side], isMe = side === 'me';
  const body = el('div', { class: 'detail-body' });
  const upd = () => run();

  // --- いまの状態 ---
  const hp = isMe
    ? el('input', { type: 'number', min: 0, value: x.hp ?? '', placeholder: '満タン', oninput: (e) => { x.hp = e.target.value === '' ? null : parseInt(e.target.value, 10); upd(); } })
    : el('input', { type: 'number', min: 1, max: 100, value: x.hp_percent, oninput: (e) => { x.hp_percent = parseFloat(e.target.value || '100'); upd(); } });
  const status = el('select', { onchange: (e) => { x.status = e.target.value; upd(); } }, ...STATUS.map(([v, t]) => el('option', { value: v, selected: (x.status || 'none') === v }, t)));
  const ranks = el('div', { class: 'ranks' }, ...Object.keys(RANK_LABEL).map(k => {
    const s = el('select', { 'data-rank': `${side}-${k}`, onchange: () => { x.boosts[k] = parseInt(s.value, 10); upd(); } },
      ...[...Array(13).keys()].map(i => 6 - i).map(v => el('option', { value: v, selected: (x.boosts[k] || 0) === v }, v > 0 ? `+${v}` : `${v}`)));
    return labelled(RANK_LABEL[k], s);
  }));
  const scr = (key, label) => el('label', { class: 'check' }, el('input', { type: 'checkbox', checked: x[key], onchange: (e) => { x[key] = e.target.checked; upd(); } }), label);
  body.append(el('h3', {}, '状態'),
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
  body.append(el('h3', {}, '型'),
    el('div', { class: 'row' }, el('div', { class: 'grow' }, labelled('性格', nature, '上がる能力と下がる能力が決まる')), el('div', { class: 'grow' }, labelled('特性', ab))),
    labelled('持ち物', item), megaBox, spGrid(x.sp, upd));
  if (isMe) {
    const mv = el('div', { class: 'moves' });
    for (let i = 0; i < 4; i++) mv.append(picker({ kind: 'moves', value: x.moves[i], label: x.moves_ja[i] || '', placeholder: `技${i + 1}`, species: () => x.species,
      onPick: (it) => { x.moves[i] = it ? it.id : null; x.moves_ja[i] = it ? it.ja : ''; upd(); } }));
    body.append(el('h3', {}, '自分の技'), mv);
  } else {
    body.append(el('p', { class: 'muted', style: 'font-size:13px' }, '相手の技は、よく使われている技（採用率1%以上）がすべて自動で出る。'));
  }
  return body;
}

function fieldBlock() {
  const sel = (key, opts) => { const s = el('select', { onchange: () => { C[key] = s.value; run(); } }, ...opts.map(([v, t]) => el('option', { value: v, selected: C[key] === v }, t))); return s; };
  return el('div', { class: 'field-block' },
    el('div', { class: 'row' },
      el('div', { class: 'grow' }, labelled('天候', sel('weather', [['', 'なし'], ['sun', '晴れ'], ['rain', '雨'], ['sand', '砂嵐'], ['snow', '雪']]))),
      el('div', { class: 'grow' }, labelled('フィールド', sel('terrain', [['', 'なし'], ['electric', 'エレキ'], ['grassy', 'グラス'], ['psychic', 'サイコ'], ['misty', 'ミスト']])))));
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
  const e = x.effect || { text: '', notes: [], fails: '' };
  return el('div', { class: 'mrow status' + (e.fails ? ' immune' : '') },
    el('div', { class: 'm-name' }, typeChip(x.type, x.move, false), x.rate != null ? el('small', { class: 'muted' }, ` 採用率${x.rate}%`) : ''),
    el('div', {}, e.text), e.fails ? el('div', { class: 'err' }, `この対面では無効・失敗: ${e.fails}`) : '', e.notes.length ? el('div', { class: 'm-notes muted' }, e.notes.join(' / ')) : '');
}

const rankMult = (st) => st >= 0 ? (2 + st) / 2 : 2 / (2 - st);
const stageText = (v) => v > 0 ? `+${v}` : `${v}`;

// 素早さライン: 自分の実際の素早さと、相手の最速スカーフ・最速・準速・無振りを並べる（相手の努力は断言できないため）。
// 左右のスライダーで、素早さのランクを上げ下げした後の比較ができる
function speedCard(r) {
  const op = C.opp;
  const box = el('div', { class: 'ladder' });
  const sync = (side) => { const sel = document.querySelector(`[data-rank="${side}-spe"]`); if (sel) sel.value = (C[side].boosts.spe || 0); };
  const ctl = (side) => {
    const x = C[side];
    const label = el('b', { class: 'stage' }, stageText(x.boosts.spe || 0));
    const range = el('input', { type: 'range', min: -6, max: 6, step: 1, value: x.boosts.spe || 0, 'aria-label': (side === 'me' ? '自分' : '相手') + 'の素早さランク' });
    const set = (v) => { v = Math.max(-6, Math.min(6, v)); x.boosts.spe = v; range.value = v; label.textContent = stageText(v); sync(side); refresh(); };
    range.addEventListener('input', () => set(parseInt(range.value, 10)));
    return el('div', { class: 'sctl ' + side }, el('div', { class: 'sctl-head' }, el('span', {}, 'ランク'), label),
      el('button', { class: 'mini', 'aria-label': 'ランクを上げる', onclick: () => set((x.boosts.spe || 0) + 1) }, '＋'), range,
      el('button', { class: 'mini', 'aria-label': 'ランクを下げる', onclick: () => set((x.boosts.spe || 0) - 1) }, '−'));
  };
  const refresh = debounce(async () => {
    const dex = await dexInfo(op.species);
    let spe = dex.speed;
    if (op.mega) { const mg = dex.megas.find(m => m.item === op.item); if (mg) spe = (await dexInfo(mg.id)).speed; }
    const st = (op.boosts && op.boosts.spe) || 0, par = op.status === 'par';
    const adj = (v, scarf) => { let n = Math.floor(v * rankMult(st)); if (scarf) n = Math.floor(n * 1.5); return par ? Math.floor(n / 2) : n; };
    // 自分の実際の素早さ（ランク・持ち物・まひ込み）はサーバで計算する
    const me = C.me;
    const side = (x, isMe) => ({ species: x.species, nature: x.nature, sp: x.sp, ability: x.ability, item: x.item, boosts: x.boosts, status: x.status && x.status !== 'none' ? x.status : null,
      hp_percent: x.hp_percent, hp: isMe && x.hp != null ? x.hp : null, mega: x.mega, moves: [] });
    const rr = await api('/api/calc/duel', { method: 'POST', body: { me: side(me, true), opp: side(op, false), my_moves: [], opp_moves: [], weather: C.weather || null, terrain: C.terrain || null, log: false } });
    const rows = [
      { side: 'opp', label: '最速スカーフ', v: adj(spe['最速'], true), tip: '性格補正あり・能力ポイント最大＋こだわりスカーフ' },
      { side: 'opp', label: '最速', v: adj(spe['最速']), tip: 'すばやさ↑の性格・能力ポイント最大' },
      { side: 'opp', label: '準速', v: adj(spe['準速']), tip: '性格補正なし・能力ポイント最大' },
      { side: 'opp', label: '無振り', v: adj(spe['無振り']), tip: '性格補正なし・能力ポイント0' },
      { side: 'me', label: me.ja, v: rr.me.speed },
    ].sort((a, b) => b.v - a.v || (a.side === 'me' ? 1 : -1));
    box.innerHTML = '';
    for (const x of rows) box.append(el('div', { class: 'lrow ' + x.side },
      el('div', { class: 'lcell l' }, x.side === 'me' ? el('span', { class: 'lbadge me' }, x.label) : ''),
      el('div', { class: 'lnum' }, x.v),
      el('div', { class: 'lcell r', title: x.tip || '' }, x.side === 'opp' ? el('span', { class: 'lbadge opp' }, el('small', {}, op.ja), x.label) : '')));
  }, 80);
  refresh();
  return el('div', { class: 'card speed' }, el('h2', {}, '素早さ ', help('相手の努力値は分からないので、よくある型の素早さを並べている。大きい方が先に動く（トリックルーム中は逆）。左右のスライダーで素早さのランクを上げ下げした後の比較ができる')),
    el('div', { class: 'sbody' }, ctl('me'), box, ctl('opp')));
}

const run = debounce(async () => {
  const out = $('#calc-out'); if (!out) return;
  const me = C.me, op = C.opp;
  if (!me.species || !op.species) {
    out.innerHTML = '';
    out.append(el('div', { class: 'card', style: 'margin-top:18px' }, el('div', { class: 'empty' }, '自分と相手のポケモンを選ぶと、ダメージが出る')));
    return;
  }
  const side = (x, isMe) => ({ species: x.species, nature: x.nature, sp: x.sp, ability: x.ability, item: x.item, boosts: x.boosts, status: x.status && x.status !== 'none' ? x.status : null,
    hp_percent: x.hp_percent, hp: isMe && x.hp != null ? x.hp : null, mega: x.mega, reflect: !!x.reflect, light_screen: !!x.light_screen, aurora_veil: !!x.aurora_veil, moves: x.set_moves || [] });
  try {
    const r = await api('/api/calc/duel', { method: 'POST', body: { me: side(me, true), opp: side(op, false), my_moves: me.moves.filter(Boolean),
      weather: C.weather || null, terrain: C.terrain || null } });
    me.max_hp = r.me.stats.hp;
    const ladder = speedCard(r);
    out.innerHTML = '';
    const col = (cls, title, hpTxt, rows, empty) => {
      const attacks = rows.filter(x => x.category !== 'Status'), status = rows.filter(x => x.category === 'Status');
      const c = el('div', { class: 'card res ' + cls }, el('h2', {}, title), el('div', { class: 'muted hp' }, hpTxt));
      if (!attacks.length && !status.length) c.append(el('p', { class: 'muted' }, empty));
      attacks.forEach(x => c.append(moveRow(x)));
      status.forEach(x => c.append(statusRow(x)));
      return c;
    };
    out.append(el('div', { class: 'grid2 results', style: 'margin-top:18px' },
      col('me', el('span', {}, monLabel(r.me.ja), ' → ', monLabel(r.opp.ja)), `相手のHP ${r.opp.current_hp} / ${r.opp.stats.hp}`, r.to_opp, '技が未設定。状態設定の「自分の技」で入れる'),
      col('opp', el('span', {}, monLabel(r.opp.ja), ' → ', monLabel(r.me.ja)), `自分のHP ${r.me.current_hp} / ${r.me.stats.hp}`, r.to_me, '技のデータがない')), ladder);
  } catch (e) { out.textContent = '計算エラー: ' + e.message; }
}, 200);
