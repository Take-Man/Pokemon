// 対戦サポート UI（ビルド不要の素のJS）
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined) e.append(k.nodeType ? k : String(k));
  return e;
};
// 画面とサーバの世代。server.py の API_VERSION と一致しないときは再起動を促す
const APP_API_VERSION = 10;
const api = async (path, opt = {}) => {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opt,
    body: opt.body ? JSON.stringify(opt.body) : undefined });
  if (!r.ok) {
    const t = await r.text();
    if (r.status === 404 && path.startsWith('/api/')) showBanner(`サーバに ${path.split('?')[0]} が無い。サーバが古いまま動いている可能性がある（ターミナルで Ctrl+C → python -m app で起動し直す）`);
    if (r.status >= 500) showBanner(`サーバでエラー（${path.split('?')[0]}）: ターミナルの表示を確認`);
    throw new Error(t);
  }
  return r.json();
};
function showBanner(msg) {
  let b = document.getElementById('banner');
  if (!b) { b = document.createElement('div'); b.id = 'banner'; document.body.prepend(b); }
  b.textContent = msg; b.hidden = false;
  b.onclick = () => { b.hidden = true; };
}
window.addEventListener('error', (e) => showBanner(`画面のエラー: ${e.message}（${(e.filename || '').split('/').pop()}:${e.lineno}）。再読み込みで直らなければ内容を教えてください`));
window.addEventListener('unhandledrejection', (e) => { const m = String((e.reason && e.reason.message) || e.reason || ''); if (!m.startsWith('{')) showBanner(`処理のエラー: ${m.slice(0, 200)}`); });
const toast = (msg) => { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); setTimeout(() => t.classList.remove('show'), 1800); };
const debounce = (fn, ms = 250) => { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); }; };
const STATS = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'];
const STAT_JA = { hp: 'H', atk: 'A', def: 'B', spa: 'C', spd: 'D', spe: 'S' };
const S = { meta: null, team: { name: '', members: [] }, opp: { species: [], ja: [] }, pred: null, dexCache: {} };

const TYPE_COLOR = { Normal: '#A8A77A', Fire: '#EE8130', Water: '#6390F0', Electric: '#F7D02C', Grass: '#7AC74C', Ice: '#96D9D6',
  Fighting: '#C22E28', Poison: '#A33EA1', Ground: '#E2BF65', Flying: '#A98FF3', Psychic: '#F95587', Bug: '#A6B91A',
  Rock: '#B6A136', Ghost: '#735797', Dragon: '#6F35FC', Dark: '#705746', Steel: '#B7B7CE', Fairy: '#D685AD' };
const TYPE_SHORT = { Normal: '無', Fire: '炎', Water: '水', Electric: '電', Grass: '草', Ice: '氷', Fighting: '闘', Poison: '毒', Ground: '地',
  Flying: '飛', Psychic: '超', Bug: '虫', Rock: '岩', Ghost: '霊', Dragon: '竜', Dark: '悪', Steel: '鋼', Fairy: '妖' };
function typeFg(t) { const h = TYPE_COLOR[t] || '#888'; const r = parseInt(h.slice(1, 3), 16), g = parseInt(h.slice(3, 5), 16), b = parseInt(h.slice(5, 7), 16); return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? '#1d2330' : '#fff'; }
function typeChip(t, label, short = false) { return el('span', { class: 'tchip', style: `background:${TYPE_COLOR[t]};color:${typeFg(t)}` }, short ? TYPE_SHORT[t] : label); }
// タイプ表示: 1文字チップ（ポケモン名・技名の横）と、名前チップ（余裕のある画面）
S.typeData = null;  // /api/types の結果
S.jaTypes = {};     // 日本語名 → タイプ
function typesOf(key) {
  if (!key || !S.typeData) return [];
  const byId = S.typeData.byId[key];
  if (byId) return byId;
  const name = String(key).replace(/（.*?）|\(.*?\)/g, '').trim();
  return S.jaTypes[name] || S.jaTypes[key] || [];
}
function moveType(idOrJa) {
  if (!idOrJa || !S.typeData) return null;
  const m = S.typeData.moves[idOrJa] || S.typeData.movesJa[idOrJa];
  return m ? m[0] : null;
}
function tChips(types, full = false) {
  if (!types || !types.length) return null;
  return el('span', { class: 'tchips' }, ...types.map(t => typeChip(t, (S.typeData && S.typeData.ja[t]) || t, !full)));
}
// ポケモン名＋タイプ（keyはidか日本語名）
const monName = (name, key, full = false) => el('span', { class: 'mon' }, name, tChips(typesOf(key || name), full));
// タイプ＋技名
const moveName = (name, key) => { const t = moveType(key || name); return el('span', { class: 'mv' }, t ? typeChip(t, t, true) : '', name); };

// 受けたときの弱点（×4 → ×2）。特性が決まっているときだけ、相性を変える特性を反映する
const toId = (x) => String(x || '').toLowerCase().replace(/[^a-z0-9]/g, '');
const ABIL_TYPE_MOD = {
  levitate: { Ground: 0 }, eartheater: { Ground: 0 }, flashfire: { Fire: 0 }, wellbakedbody: { Fire: 0 },
  waterabsorb: { Water: 0 }, stormdrain: { Water: 0 }, dryskin: { Water: 0, Fire: 1.25 }, voltabsorb: { Electric: 0 },
  lightningrod: { Electric: 0 }, motordrive: { Electric: 0 }, sapsipper: { Grass: 0 }, thickfat: { Fire: 0.5, Ice: 0.5 },
  heatproof: { Fire: 0.5 }, waterbubble: { Fire: 0.5 }, purifyingsalt: { Ghost: 0.5 }, fluffy: { Fire: 2 },
};
function weakness(types, ability) {
  const T = S.typeData; if (!T || !types || !types.length) return { x4: [], x2: [], abil: '' };
  const mod = ABIL_TYPE_MOD[toId(ability)] || {};
  const x4 = [], x2 = [];
  for (const a of T.order) {
    const m = types.reduce((v, d) => v * T.chart[a][d], 1) * (mod[a] ?? 1);
    if (m >= 4) x4.push(a); else if (m >= 2) x2.push(a);
  }
  return { x4, x2, abil: Object.keys(mod).length ? toId(ability) : '' };
}
// その場の姿（メガ後を含む）の種族idと、確定している特性から弱点チップを作る。ability が null なら特性は考えない
function weakChips(key, ability = null, abilityJa = '') {
  const w = weakness(typesOf(key), ability);
  if (!w.x4.length && !w.x2.length) return el('span', { class: 'weak none', title: '弱点なし' }, '弱点なし');
  const chip = (t) => el('span', { class: 'tchip wk', style: `background:${TYPE_COLOR[t]};color:${typeFg(t)}`, title: S.typeData.ja[t] }, TYPE_SHORT[t]);
  const title = '受けたときの弱点' + (w.abil ? `（特性${abilityJa || ''}を考慮）` : '');
  return el('span', { class: 'weak', title }, el('span', { class: 'wk-l' }, '弱点'),
    ...(w.x4.length ? [el('span', { class: 'wk-m' }, '×4'), ...w.x4.map(chip)] : []),
    ...(w.x2.length ? [el('span', { class: 'wk-m' }, '×2'), ...w.x2.map(chip)] : []));
}
// 特性が1つに決まる姿なら、その特性を返す（メガ後など）
// 自分側（パーティ・ダメ計）: メガストーンを持っていればメガ後の姿と特性で弱点を出す
async function fillWeak(box, species, item, ability, megaOn = true) {
  box.innerHTML = '';
  if (!species) return;
  await loadTypeData();
  const d = await dexInfo(species);
  const mg = megaOn ? d.megas.find(x => x.item === item) : null;
  const key = mg ? mg.id : species;
  const ab = mg ? onlyAbility(mg.id) : ability;
  const abJa = mg ? '' : ((d.abilities.find(a => a.en === ability) || {}).ja || '');
  box.append(weakChips(key, ab, abJa));
  return key;
}
const oppAbility = (o) => (o.ability && o.ability.src === 'confirmed' && o.ability.id) || onlyAbility(o.battle_species);
const onlyAbility = (key) => { const a = (S.typeData && S.typeData.abil[key]) || []; return a.length === 1 ? a[0] : null; };
async function loadTypeData() {
  if (S.typeData) return;
  const d = await api('/api/types');
  const byId = {}, ja = {};
  const abil = {};
  for (const p of d.pokemon) { byId[p.id] = p.types; S.jaTypes[p.ja] = p.types; abil[p.id] = p.abilities || []; }
  for (const t of d.types) ja[t.id] = t.ja;
  const movesJa = {};
  for (const [id, v] of Object.entries(d.moves)) movesJa[v[1]] = v;
  S.typeData = { byId, ja, moves: d.moves, movesJa, abil, chart: d.chart, order: d.types.map(t => t.id) };
  S.ty = d;
}

async function dexInfo(id) {
  if (!S.dexCache[id]) S.dexCache[id] = await api(`/api/pokemon/${encodeURIComponent(id)}`);
  return S.dexCache[id];
}

// ---------------------------------------------------------------------------
// 検索付き入力
// ---------------------------------------------------------------------------
function picker({ kind, value = '', label = '', placeholder = '', species = () => null, onPick, onEnterNext }) {
  const input = el('input', { value: label || '', placeholder, autocomplete: 'off', spellcheck: 'false' });
  input.dataset.id = value || '';
  const dd = el('div', { class: 'dd', hidden: true });
  const wrap = el('div', { class: 'picker' }, input, dd);
  let items = [], sel = 0;
  const render = () => {
    dd.innerHTML = '';
    items.forEach((it, i) => {
      const extra = kind === 'moves' ? `${it.category === 'Physical' ? '物' : it.category === 'Special' ? '特' : '変'} ${it.basePower || '-'}` : '';
      const label = kind === 'pokemon' ? monName(it.ja, it.id) : kind === 'moves' ? moveName(it.ja, it.id) : it.ja;
      dd.append(el('div', { class: i === sel ? 'sel' : '', onmousedown: (e) => { e.preventDefault(); pick(it); } },
        label, el('small', { class: 'muted' }, extra)));
    });
    dd.hidden = items.length === 0;
  };
  const search = debounce(async () => {
    const q = input.value.trim();
    if (!q) { items = []; render(); return; }
    const sp = species();
    items = await api(`/api/search?kind=${kind}&q=${encodeURIComponent(q)}${sp ? `&species=${sp}` : ''}`);
    sel = 0; render();
  }, 120);
  const pick = (it) => {
    input.value = it ? it.ja : ''; input.dataset.id = it ? it.id : '';
    items = []; render();
    onPick && onPick(it);
  };
  input.addEventListener('input', search);
  input.addEventListener('focus', () => input.select());
  input.addEventListener('blur', () => setTimeout(() => { items = []; render(); }, 100));
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { sel = Math.min(sel + 1, items.length - 1); render(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sel = Math.max(sel - 1, 0); render(); e.preventDefault(); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      if (items[sel]) { pick(items[sel]); onEnterNext && onEnterNext(); }
      else if (!input.value.trim()) pick(null);
    } else if (e.key === 'Escape') { items = []; render(); }
  });
  wrap.input = input;
  wrap.setValue = (id, ja) => { input.value = ja || ''; input.dataset.id = id || ''; };
  return wrap;
}

function natureSelect(value, onChange) {
  const s = el('select', { onchange: () => onChange(s.value || null) }, el('option', { value: '' }, '性格'));
  for (const n of S.meta.natures) s.append(el('option', { value: n.id, selected: n.id === value }, `${n.ja}（${n.label}）`));
  return s;
}

function spGrid(sp, onChange) {
  const g = el('div', { class: 'sp-grid' });
  const total = el('div', { class: 'stats-line' });
  const sum = () => STATS.reduce((a, k) => a + (sp[k] || 0), 0);
  const upd = () => { const t = sum(); total.textContent = `合計 ${t}/66（残り ${66 - t}）`; total.className = t > 66 ? 'err' : 'stats-line'; };
  const inputs = {};
  const set = (k, v) => { sp[k] = Math.max(0, Math.min(32, v)); inputs[k].value = sp[k]; upd(); onChange(sp); };
  for (const k of STATS) {
    const i = el('input', { type: 'number', min: 0, max: 32, value: sp[k] || 0 });
    inputs[k] = i;
    i.addEventListener('input', () => set(k, parseInt(i.value || '0', 10) || 0));
    const zero = el('button', { class: 'mini', title: '0にする', onclick: () => set(k, 0) }, '0');
    const max = el('button', { class: 'mini', title: '振れる上限（32か残りポイント）', onclick: () => set(k, Math.min(32, 66 - (sum() - (sp[k] || 0)))) }, 'Max');
    g.append(el('label', {}, STAT_JA[k], i, el('span', { class: 'mini-row' }, zero, max)));
  }
  upd();
  return el('div', {}, g, total);
}

// メガシンカ枠の指定（メガが1種ならチェックボックス、複数ならセレクト）。onChange(mega|null)
function megaControl(speciesId, currentItem, onChange) {
  const box = el('span', { class: 'mega-ctl' });
  if (!speciesId) return box;
  (async () => {
    const d = await dexInfo(speciesId);
    if (!d.megas.length) return;
    const cur = d.megas.find(m => m.item === currentItem) || null;
    if (d.megas.length === 1) {
      const mg = d.megas[0];
      const cb = el('input', { type: 'checkbox', checked: !!cur, onchange: () => onChange(cb.checked ? mg : null, d) });
      box.append(el('label', { class: 'inline' }, cb, ` メガシンカ枠（${mg.ja}）`));
    } else {
      const sel = el('select', { onchange: () => onChange(d.megas.find(m => m.id === sel.value) || null, d) },
        el('option', { value: '' }, 'メガシンカしない'), ...d.megas.map(m => el('option', { value: m.id, selected: cur && cur.id === m.id }, m.ja)));
      box.append(el('label', { class: 'inline' }, 'メガシンカ枠 ', sel));
    }
  })();
  return box;
}

// ---------------------------------------------------------------------------
// タブ
// ---------------------------------------------------------------------------
function showTab(name) {
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.id === `tab-${name}`));
  if (name === 'speed') renderSpeed();
  if (name === 'calc') renderCalc();
  if (name === 'battle') loadBattle();
  if (name === 'history') renderHistory();
  if (name === 'types') renderTypes();
}
document.querySelectorAll('#tabs button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));

// ---------------------------------------------------------------------------
// パーティ
// ---------------------------------------------------------------------------
let saveTimer = null, saving = null;
function markDirty(flag) {
  S.dirty = flag;
  const b = $('#btn-save'); if (b) { b.textContent = flag ? '保存（未保存の変更あり）' : '保存済み'; b.classList.toggle('primary', flag); }
}
async function saveTeamNow() {
  clearTimeout(saveTimer);
  const body = { id: S.team.id, name: S.team.name, archetype: S.team.archetype, members: S.team.members.map(m => Object.fromEntries(Object.entries(m).filter(([k]) => !k.startsWith('_')))) };
  saving = api('/api/team', { method: 'PUT', body });
  await saving;
  const t = await api('/api/team');
  t.members.forEach((m, i) => { if (S.team.members[i]) Object.assign(S.team.members[i], { _stats: m._stats, _errors: m._errors, _ja: m._ja }); });
  document.querySelectorAll('#team-cards .card').forEach((c, i) => c.updateStats && c.updateStats(S.team.members[i]));
  markDirty(false);
  refreshDiag();
}
function saveTeam() {
  markDirty(true);
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => saveTeamNow().catch(e => toast('保存に失敗: ' + e.message)), 500);
}
// タブを閉じる・再読み込みする前に未保存分を送る
window.addEventListener('beforeunload', () => {
  if (!S.dirty || !S.team) return;
  const body = JSON.stringify({ id: S.team.id, name: S.team.name, archetype: S.team.archetype, members: S.team.members.map(m => Object.fromEntries(Object.entries(m).filter(([k]) => !k.startsWith('_')))) });
  fetch('/api/team', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body, keepalive: true });
});

async function renderTeamBar() {
  const bar = $('#team-bar'); bar.innerHTML = '';
  S.teams = await api('/api/teams');
  const sel = el('select', { onchange: async () => { if (S.dirty) await saveTeamNow(); await api(`/api/teams/active/${sel.value}`, { method: 'PUT' }); await loadTeam(); } });
  for (const t of S.teams) sel.append(el('option', { value: t.id, selected: t.id === S.team.id }, `${t.name}（${t.members.join('・') || '空'}）`));
  const name = el('input', { value: S.team.name || '', placeholder: 'パーティ名', oninput: () => { S.team.name = name.value; saveTeam(); } });
  name.addEventListener('change', () => setTimeout(renderTeamBar, 700));
  const arch = el('select', { title: '構築の型', onchange: () => { S.team.archetype = arch.value; saveTeam(); } });
  for (const a of (S.team.archetypes || ['スタンダード'])) arch.append(el('option', { value: a, selected: a === S.team.archetype }, a));
  const save = el('button', { id: 'btn-save', onclick: async () => { await saveTeamNow(); await renderTeamBar(); toast('保存した'); } }, '保存済み');
  bar.append(el('b', {}, 'パーティ'), sel, name, el('label', {}, '構築の型 ', arch), save,
    el('button', { onclick: async () => { if (S.dirty) await saveTeamNow(); await api('/api/teams', { method: 'POST', body: { name: '' } }); await loadTeam(); toast('新しいパーティを作成した'); } }, '新規'),
    el('button', { onclick: async () => { if (S.dirty) await saveTeamNow(); await api('/api/teams', { method: 'POST', body: { copy_from: S.team.id } }); await loadTeam(); toast('複製した'); } }, '複製'),
    el('button', { onclick: async () => {
      if (!confirm(`「${S.team.name}」を削除しますか？`)) return;
      await api(`/api/teams/${S.team.id}`, { method: 'DELETE' }); await loadTeam(); toast('削除した');
    } }, '削除'));
  renderSelTeam();
}

function renderSelTeam() {
  const box = $('#sel-team'); if (!box) return; box.innerHTML = '';
  const sel = el('select', { onchange: async () => { if (S.dirty) await saveTeamNow(); await api(`/api/teams/active/${sel.value}`, { method: 'PUT' }); await loadTeam(); toast('パーティを切り替えた'); } });
  for (const t of (S.teams || [])) sel.append(el('option', { value: t.id, selected: t.id === S.team.id }, t.name));
  box.append(el('small', {}, '自分: '), sel);
}

function renderTeam() {
  const box = $('#team-cards'); box.innerHTML = '';
  while (S.team.members.length < 6) S.team.members.push({ species: null, sp: {}, moves: [] });
  S.team.members.forEach((m, idx) => box.append(teamCard(m, idx)));
}

function teamCard(m, idx) {
  m.sp = m.sp || {}; m.moves = m.moves || [];
  const card = el('div', { class: 'card' });
  const stats = el('div', { class: 'stats-line' });
  const errs = el('div', { class: 'err' });
  const roles = el('div', { class: 'roles' });
  card.roles = roles;
  card.updateStats = (mm) => {
    stats.textContent = mm && mm._stats ? STATS.map(k => `${STAT_JA[k]}${mm._stats[k]}`).join(' ') : '';
    errs.textContent = mm && mm._errors ? mm._errors.join(' / ') : '';
  };
  const wkBox = el('span'), typeBox = el('span');
  // タイプと弱点はメガ後の姿に合わせる
  const updWeak = async () => { const key = await fillWeak(wkBox, m.species, m.item, m.ability); typeBox.innerHTML = ''; if (key) typeBox.append(tChips(typesOf(key), true)); };
  const abilitySel = el('select', { onchange: () => { m.ability = abilitySel.value || null; updWeak(); saveTeam(); } });
  const fillAbilities = async () => {
    abilitySel.innerHTML = '';
    if (!m.species) return;
    const d = await dexInfo(m.species);
    abilitySel.append(el('option', { value: '' }, '特性'));
    d.abilities.forEach(a => abilitySel.append(el('option', { value: a.en, selected: a.en === m.ability }, a.ja)));
  };
  const megaBox = el('div');
  const item = picker({ kind: 'items', value: m.item, label: m._item_ja || '', placeholder: '持ち物',
    onPick: (it) => { m.item = it ? it.en : null; updWeak(); saveTeam(); } });
  const renderMega = () => {
    megaBox.innerHTML = '';
    megaBox.append(megaControl(m.species, m.item, (mg) => {
      if (mg) { m.item = mg.item; item.setValue(mg.item, mg.item_ja); item.input.disabled = true; }
      else { if (m._megaItems && m._megaItems.includes(m.item)) { m.item = null; item.setValue('', ''); } item.input.disabled = false; }
      updWeak(); saveTeam(); refreshDiag();
    }));
    updWeak();
    (async () => {
      if (!m.species) { item.input.disabled = false; return; }
      const d = await dexInfo(m.species);
      m._megaItems = d.megas.map(x => x.item);
      item.input.disabled = m._megaItems.includes(m.item);
    })();
  };
  const sp = picker({ kind: 'pokemon', value: m.species, label: m._ja || '', placeholder: `${idx + 1}体目`,
    onPick: async (it) => {
      const prev = m.species;
      m.species = it ? it.id : null;
      if (prev !== m.species) {
        m.ability = null;
        if (m._megaItems && m._megaItems.includes(m.item)) { m.item = null; item.setValue('', ''); }
      }
      await fillAbilities(); renderMega(); saveTeam();
    } });
  const moves = el('div', { class: 'moves' });
  const movePickers = [];
  for (let i = 0; i < 4; i++) {
    const mp = picker({ kind: 'moves', value: m.moves[i], label: (m._moves_ja || [])[i] || '', placeholder: `技${i + 1}`,
      species: () => m.species, onPick: (it) => { m.moves[i] = it ? it.id : null; m.moves = m.moves.filter(Boolean); saveTeam(); } });
    movePickers.push(mp); moves.append(mp);
  }
  const fill = el('button', { title: '入力済みの項目は変えず、未入力の項目を環境データの採用率上位で埋める', onclick: async () => {
    if (!m.species) { toast('ポケモンを先に入力'); return; }
    if (saveTimer) await saveTeamNow();
    const r = await api('/api/autofill', { method: 'POST', body: { member: m } });
    toast(r.message);
    if (!r.filled.length) return;
    Object.assign(m, r.member);
    await saveTeamNow();
    await loadTeam();
  } }, '型を自動入力');
  card.append(sp, el('div', { class: 'card-types' }, typeBox, wkBox, roles), megaBox, el('div', { class: 'row' }, natureSelect(m.nature, v => { m.nature = v; saveTeam(); }), abilitySel, fill),
    item, spGrid(m.sp, () => saveTeam()), stats, errs, moves);
  renderMega();
  fillAbilities(); card.updateStats(m);
  return card;
}

async function loadTeam() {
  S.team = await api('/api/team');
  const ja = async (kind, id) => { if (!id) return ''; const r = await api(`/api/search?kind=${kind}&q=${encodeURIComponent(id)}&limit=1&include_mega=true`); return r[0] ? r[0].ja : id; };
  markDirty(false);
  for (const m of S.team.members) {
    m._item_ja = await ja('items', m.item);
    m._moves_ja = await Promise.all((m.moves || []).map(x => ja('moves', x)));
  }
  renderTeam();
  await renderTeamBar();
  refreshDiag();
  renderTune();
}

// ---- 構築診断 ----
const refreshDiag = debounce(async () => {
  const box = $('#diag');
  const d = await api('/api/diagnose');
  box.innerHTML = '';
  const cards = document.querySelectorAll('#team-cards .card');
  let k = 0;
  S.team.members.forEach((m, i) => {
    const c = cards[i]; if (!c || !c.roles) return;
    c.roles.innerHTML = '';
    if (!m.species) return;
    const r = d.members[k++];
    if (r) for (const t of r.roles) c.roles.append(el('span', { class: 'role', title: t.reason }, t.ja));
  });
  if (!d.members.length) { box.append(el('p', { class: 'muted' }, 'ポケモンを登録すると診断する')); return; }
  const counts = Object.entries(d.role_counts || {}).map(([k2, v]) => `${({ ace: 'エース', breaker: '崩し', faceoff: '対面駒', cushion: 'クッション', wall_phys: '物理受け', wall_spec: '特殊受け', setter: '起点作り', stopper: 'ストッパー', pivot: 'サイクル要員', weather: '天候始動' })[k2] || k2}${v}`);
  box.append(el('div', { class: 'muted' }, `構築の型: ${d.archetype}　役割: ${counts.join(' / ')}`));
  if (!d.findings.length) box.append(el('div', { class: 'finding' }, '目立った穴は見つからない'));
  for (const f of d.findings) box.append(el('div', { class: `finding ${f.level}` }, f.text));
  const multi = (d.type_overlap || []).filter(o => o.weak >= 2).sort((a, b) => b.weak - a.weak);
  if (multi.length) {
    const t = el('table', { style: 'margin-top:8px' }, el('tr', {}, el('th', {}, '攻撃タイプ'), el('th', { class: 'num' }, '弱点'), el('th', { class: 'num' }, '半減以下'), el('th', {}, '弱点のポケモン')));
    for (const o of multi) t.append(el('tr', {}, el('td', {}, o.ja), el('td', { class: 'num' }, o.weak), el('td', { class: 'num' }, o.resist), el('td', {}, o.weak_members.join('・'))));
    box.append(t);
  }
}, 300);

// ---- 能力ポイント調整 ----
async function renderTune() {
  const box = $('#tune'); box.innerHTML = '';
  if (!S.threats) S.threats = await api('/api/threats');
  const members = S.team.members.map((m, i) => ({ m, i })).filter(x => x.m.species);
  if (!members.length) { box.append(el('p', { class: 'muted' }, 'ポケモンを登録すると使える')); return; }
  const f = { index: members[0].i, mode: 'survive', opponent: S.threats[0] && S.threats[0].id, move: null, hits: 1, cond: 'guaranteed', pct: 10, worst_case: false };
  const who = el('select', {}, ...members.map(x => el('option', { value: x.i }, x.m._ja || x.m.species)));
  const mode = el('select', {}, el('option', { value: 'survive' }, '耐える（H/B・H/D）'), el('option', { value: 'ko' }, '倒す（A/C）'));
  const opp = el('select', {}, ...S.threats.map(t => el('option', { value: t.id }, `${t.rank}. ${t.ja}`)));
  const move = el('select');
  const hits = el('select', {}, ...[1, 2, 3].map(n => el('option', { value: n }, `${n}発`)));
  const cond = el('select', {}, el('option', { value: 'guaranteed' }, '確定'), el('option', { value: 'pct' }, '確率を指定'));
  const pct = el('input', { type: 'number', min: 0, max: 100, value: 10, class: 'w5', disabled: true });
  const worst = el('input', { type: 'checkbox' });
  const setLbl = el('div', { class: 'muted' });
  const out = el('div');
  const fillMoves = () => {
    move.innerHTML = '';
    if (mode.value === 'survive') {
      const t = S.threats.find(x => x.id === opp.value);
      (t ? t.moves : []).forEach(mv => move.append(el('option', { value: mv.id }, mv.ja)));
      setLbl.textContent = t ? `仮想敵の型: ${t.set_label}` : '';
    } else {
      const m = S.team.members[parseInt(who.value, 10)];
      (m.moves || []).forEach((mv, k) => move.append(el('option', { value: mv }, (m._moves_ja || [])[k] || mv)));
      const t = S.threats.find(x => x.id === opp.value);
      setLbl.textContent = t ? `相手の型: ${t.set_label}` : '';
    }
    pctLabel.firstChild.textContent = mode.value === 'survive' ? '倒される確率（%以下）' : '倒す確率（%以上）';
  };
  const pctLabel = el('label', {}, '倒される確率（%以下）', pct);
  [who, mode, opp].forEach(x => x.addEventListener('change', () => { fillMoves(); run(); }));
  [move, hits, pct, worst].forEach(x => x.addEventListener('change', () => run()));
  cond.addEventListener('change', () => { pct.disabled = cond.value !== 'pct'; run(); });
  box.append(el('div', { class: 'tune-form' },
    el('label', {}, '自分', who), el('label', {}, '目的', mode), el('label', {}, '仮想敵（使用率順）', opp), el('label', {}, '技', move),
    el('label', {}, '回数', hits), el('label', {}, '条件', cond), pctLabel, el('label', {}, '最大火力型で計算', worst)), setLbl, out);
  const run = debounce(async () => {
    if (!move.value) { out.textContent = '技がない'; return; }
    const surv = mode.value === 'survive';
    const p = cond.value === 'pct' ? parseFloat(pct.value || '0') / 100 : (surv ? 0 : 1);
    const body = { index: parseInt(who.value, 10), mode: mode.value, opponent: opp.value, move: move.value, hits: parseInt(hits.value, 10), threshold: p, worst_case: worst.checked };
    try {
      const r = await api('/api/tune', { method: 'POST', body });
      out.innerHTML = '';
      const m = S.team.members[body.index];
      const sk = STAT_JA[r.stat];
      if (surv) {
        out.append(el('div', {}, `現在: ${r.current.damage_pct[0]}–${r.current.damage_pct[1]}%、${body.hits}発で倒される確率 ${(r.current.ko_chance * 100).toFixed(1)}%`));
        out.append(el('div', { class: 'muted' }, `固定: ${Object.entries(r.keep).filter(([, v]) => v).map(([k, v]) => STAT_JA[k] + v).join(' ') || 'なし'}／使える残り ${r.budget}`));
        if (!r.feasible) { out.append(el('div', { class: 'err' }, r.note)); return; }
        const t = el('table', {}, el('tr', {}, el('th', {}, '配分'), el('th', { class: 'num' }, '合計'), el('th', {}, '被ダメ'), el('th', { class: 'num' }, '確率'), el('th', {}, '')));
        for (const o of r.options) t.append(el('tr', {}, el('td', {}, `H${o.hp} ${sk}${o[r.stat]}`), el('td', { class: 'num' }, o.total),
          el('td', {}, `${o.damage_pct[0]}–${o.damage_pct[1]}%`), el('td', { class: 'num' }, `${(o.ko_chance * 100).toFixed(1)}%`),
          el('td', {}, el('button', { onclick: async () => { m.sp = { ...r.keep, hp: o.hp, [r.stat]: o[r.stat] }; await saveTeamNow(); await loadTeam(); toast(`H${o.hp} ${sk}${o[r.stat]} を反映した`); } }, '反映'))));
        out.append(t, el('div', { class: 'muted' }, `余り ${r.budget - (r.options[0] ? r.options[0].total : 0)} ポイントを他に回せる`));
      } else {
        out.append(el('div', { class: 'muted' }, `固定: ${Object.entries(r.keep).filter(([, v]) => v).map(([k, v]) => STAT_JA[k] + v).join(' ') || 'なし'}／使える残り ${r.budget}`));
        if (!r.feasible) { out.append(el('div', { class: 'err' }, r.note)); return; }
        const o = r.option;
        out.append(el('div', {}, `${sk}${o[r.stat]} で ${o.damage_pct[0]}–${o.damage_pct[1]}%（${body.hits}発で倒す確率 ${(o.ko_chance * 100).toFixed(1)}%）`),
          el('button', { onclick: async () => { m.sp = { ...r.keep, [r.stat]: o[r.stat] }; await saveTeamNow(); await loadTeam(); toast(`${sk}${o[r.stat]} を反映した`); } }, '反映'));
      }
    } catch (e) { out.textContent = '計算エラー: ' + e.message; }
  }, 150);
  fillMoves(); run();
}

// ---------------------------------------------------------------------------
// 選出
// ---------------------------------------------------------------------------
let oppPickers = [];
function renderOppSlots() {
  const box = $('#opp-slots'); box.innerHTML = ''; oppPickers = [];
  for (let i = 0; i < 6; i++) {
    const p = picker({ kind: 'pokemon', value: S.opp.species[i], label: S.opp.ja[i] || '', placeholder: `相手${i + 1}`,
      onPick: () => saveOpp(), onEnterNext: () => { const n = oppPickers[i + 1]; if (n) n.input.focus(); else $('#btn-predict').focus(); } });
    oppPickers.push(p); box.append(p);
  }
}
const saveOpp = debounce(async () => {
  const species = oppPickers.map(p => p.input.dataset.id).filter(Boolean);
  await api('/api/opponent', { method: 'PUT', body: { species, source: 'manual' } });
  const o = await api('/api/opponent'); S.opp = o; S.oppMtime = o.mtime;
}, 150);

$('#btn-opp-clear').addEventListener('click', async () => {
  await api('/api/opponent', { method: 'PUT', body: { species: [], source: 'manual' } });
  S.opp = await api('/api/opponent'); S.oppMtime = S.opp.mtime; renderOppSlots();
});

$('#btn-predict').addEventListener('click', async () => {
  try {
    const p = await api('/api/predict', { method: 'POST' });
    S.pred = p; renderPred();
    toast('予想した（相手の6体を履歴に保存）');
    if (p.job) watchJob(p.job);
  } catch (e) { toast('自分のパーティと相手の6体を入力してください'); }
});

async function watchJob(id) {
  const js = $('#job-status');
  js.textContent = '追加データ取得中…';
  for (let i = 0; i < 90; i++) {
    await new Promise(r => setTimeout(r, 2000));
    const jobs = await api('/api/jobs');
    const j = jobs.find(x => x.id === id);
    if (!j || j.status === 'running') continue;
    if (j.status === 'done') { js.textContent = '追加データを反映した'; S.pred = await api('/api/predict'); renderPred(); }
    else js.textContent = `追加データ取得に失敗: ${j.error || ''}`;
    return;
  }
}

const pct = (a) => a ? `${a[0]}–${a[1]}%` : '-';
function renderPred() {
  const p = S.pred; if (!p || !p.opponent) return;
  $('#pred-source').textContent = `データ: ${p.data_source}`;
  const box = $('#pred-opp'); box.innerHTML = '';
  for (const o of p.opponent) {
    box.append(el('div', { class: 'opp-card' },
      el('div', { class: 'head' }, el('span', { class: 'rank' }, `${o.rank}`), el('b', {}, monName(o.ja, o.species)),
        el('small', {}, `スコア ${o.score}（通り ${o.matchup}${o.usage !== null ? ` / 使用率 ${o.usage}` : ''}）`)),
      el('div', { class: 'muted' }, `想定型: ${o.set_label}`),
      el('div', {}, '重い相手: ', o.threatens.length ? o.threatens.map(t => el('span', { class: 'chip' }, t)) : 'なし'),
      el('div', {}, '受け出し先: ', (o.switch_ins || []).length ? o.switch_ins.join('・') : el('span', { class: 'muted' }, 'なし（最大打点50%未満の駒がいない）')),
      ...(o.setup || []).map(su => el('div', {}, `積み: ${su.move}（${Object.entries(su.boosts).map(([k, v]) => STAT_JA[k] + (v > 0 ? '+' : '') + v).join(' ')}）→ `,
        su.flips.length ? el('span', { class: 'err' }, `起点にされる: ${su.flips.join('・')}`) : el('span', { class: 'muted' }, '積まれても不利にならない')))));
  }
  const rec = $('#pred-rec'); rec.innerHTML = '';
  for (const c of p.recommend) {
    const ans = Object.entries(c.answers).map(([k, v]) => el('div', {}, el('span', { class: 'chip opp' }, k), ' → ', v.length ? v.join('・') : el('span', { class: 'err' }, '有利な駒なし')));
    rec.append(el('div', { class: 'opp-card' }, el('div', { class: 'head' }, el('b', {}, c.members.join('・')), el('small', {}, `スコア ${c.score}${c.mega_conflict ? '（メガ2体: 片方のみメガ可）' : ''}`)), ...ans));
  }
  const t = el('table', {}, el('tr', {}, el('th', {}, '自分＼相手'), ...p.opp.map(o => el('th', {}, monName(o)))));
  p.matrix.forEach((row, i) => {
    t.append(el('tr', {}, el('th', {}, monName(p.my[i])), ...row.map(x => el('td', {
      class: x.score >= 0.75 ? 'cell-good' : x.score <= 0.25 ? 'cell-bad' : 'cell-mid',
      title: `自分: ${x.a_move || '-'} ${pct(x.a_pct)}（${x.a_hits}発） / 相手: ${x.b_move || '-'} ${pct(x.b_pct)}（${x.b_hits}発） / S ${x.a_speed} vs ${x.b_speed}${x.evidence ? ` / 実戦データ: ${x.evidence}` : ''}`,
    }, el('div', {}, `${pct(x.a_pct)}`, x.evidence && x.score !== x.calc_score ? el('span', { class: 'evi', title: x.evidence }, ' *') : ''), el('div', { class: 'muted' }, `${pct(x.b_pct)}`), el('div', { class: 'muted' }, `S${x.a_speed} vs ${x.b_speed}`)))));
  });
  const mb = $('#pred-matrix'); mb.innerHTML = ''; mb.append(t);
}

// 相手の6体がファイル経由（スクショ判定など）で更新されたら反映
async function pollOpponent() {
  try {
    const o = await api('/api/opponent');
    if (S.oppMtime && o.mtime !== S.oppMtime && o.source !== 'manual') { S.opp = o; renderOppSlots(); toast(`相手の6体を${o.source}から読み込んだ`); }
    S.oppMtime = o.mtime;
  } catch (e) { /* ignore */ }
}
setInterval(pollOpponent, 3000);

// ---------------------------------------------------------------------------
// ダメ計
// ---------------------------------------------------------------------------
const blank = () => ({ species: null, ja: '', nature: null, sp: {}, ability: null, item: null, item_ja: '', boosts: {}, status: 'none', hp_percent: 100, hp: null, max_hp: null, mega: false, reflect: false, light_screen: false, aurora_veil: false, moves: [], moves_ja: [], set_moves: [] });
S.calc = { me: blank(), opp: blank() };

async function setFromSet(side, set, ja) {
  const x = S.calc[side];
  const find = async (kind, id) => { if (!id) return ''; const r = await api(`/api/search?kind=${kind}&q=${encodeURIComponent(id)}&limit=1&include_mega=true`); return r[0] ? r[0].ja : id; };
  Object.assign(x, { species: set.species, ja, nature: set.nature, sp: { ...(set.sp || {}) }, ability: set.ability, item: set.item,
    item_ja: await find('items', set.item), moves: [...(set.moves || [])].slice(0, 4), moves_ja: await Promise.all((set.moves || []).slice(0, 4).map(m => find('moves', m))),
    set_moves: [...(set.moves || [])], boosts: {}, status: 'none', hp_percent: 100, hp: null, max_hp: null, mega: false });
  const d = await dexInfo(set.species);
  if (set.item && d.megas.some(m => m.item === set.item)) x.mega = true;
}

function sideBox(side) {
  S.calcHead = S.calcHead || {};
  const x = S.calc[side];
  const isMe = side === 'me';
  const box = el('div', { class: 'sidebox' });
  const quick = el('div', { class: 'quick' });
  if (isMe) {
    for (const m of S.team.members.filter(m => m.species)) quick.append(el('button', { class: 'chip', onclick: async () => { await setFromSet(side, m, m._ja); renderCalc(); } }, m._ja));
  } else if (S.bt && S.bt.opp_builds && S.bt.opp_builds.length) {
    for (const o of S.bt.opp_builds) quick.append(el('button', { class: 'chip opp', title: '対戦モードの推定型', onclick: async () => { await setFromSet(side, o.set, o.ja); renderCalc(); } }, `${o.battle_ja || o.ja}（対戦）`));
  } else if (S.pred && S.pred.opponent) {
    for (const o of S.pred.opponent) quick.append(el('button', { class: 'chip opp', onclick: async () => { await setFromSet(side, o.set, o.ja); renderCalc(); } }, o.ja));
  } else {
    for (let i = 0; i < (S.opp.species || []).length; i++) {
      const id = S.opp.species[i];
      quick.append(el('button', { class: 'chip opp', onclick: async () => { const d = await dexInfo(id); await setFromSet(side, d.likely_set, d.ja); renderCalc(); } }, S.opp.ja[i]));
    }
  }
  const sp = picker({ kind: 'pokemon', value: x.species, label: x.ja, placeholder: 'ポケモン',
    onPick: async (it) => { if (!it) return; const d = await dexInfo(it.id); await setFromSet(side, d.likely_set, d.ja); renderCalc(); } });
  const ab = el('select', { onchange: () => { x.ability = ab.value || null; S.calcHead[side](); runCalc(); } });
  const item = picker({ kind: 'items', value: x.item, label: x.item_ja, placeholder: '持ち物', onPick: (it) => { x.item = it ? it.en : null; S.calcHead[side](); runCalc(); } });
  (async () => { if (!x.species) return; const d = await dexInfo(x.species); ab.append(el('option', { value: '' }, '特性なし'));
    d.abilities.forEach(a => ab.append(el('option', { value: a.en, selected: a.en === x.ability }, a.ja)));
    item.input.disabled = d.megas.some(mg => mg.item === x.item); })();
  const megaLbl = el('div', {}, megaControl(x.species, x.item, (mg, d) => {
    if (mg) { x.item = mg.item; x.item_ja = mg.item_ja; x.mega = true; item.setValue(mg.item, mg.item_ja); item.input.disabled = true; }
    else { x.mega = false; if (d.megas.some(q => q.item === x.item)) { x.item = null; x.item_ja = ''; item.setValue('', ''); } item.input.disabled = false; }
    S.calcHead[side]();
    runCalc();
  }));
  const ranks = el('div', { class: 'ranks' }, ...['atk', 'def', 'spa', 'spd', 'spe'].map(k => {
    const s2 = el('select', { onchange: () => { x.boosts[k] = parseInt(s2.value, 10); s2.className = x.boosts[k] > 0 ? 'up' : x.boosts[k] < 0 ? 'down' : ''; runCalc(); } },
      ...[...Array(13).keys()].map(i => 6 - i).map(v => el('option', { value: v, selected: (x.boosts[k] || 0) === v }, v > 0 ? `+${v}` : `${v}`)));
    s2.className = (x.boosts[k] || 0) > 0 ? 'up' : (x.boosts[k] || 0) < 0 ? 'down' : '';
    return el('label', {}, `${STAT_JA[k]}ランク`, s2);
  }));
  const status = el('select', { onchange: () => { x.status = status.value; runCalc(); } }, ...STATUS_OPTS.map(([v, t]) => el('option', { value: v, selected: (x.status || 'none') === v }, t)));
  // 自分は実数（画面のHP）、相手は%（相手の画面は%表示）
  const hp = isMe
    ? el('input', { type: 'number', min: 0, value: x.hp ?? x.max_hp ?? '', placeholder: '満タン', class: 'w5', oninput: () => { x.hp = hp.value === '' ? null : parseInt(hp.value, 10); runCalc(); } })
    : el('input', { type: 'number', min: 1, max: 100, value: x.hp_percent, class: 'w5', oninput: () => { x.hp_percent = parseFloat(hp.value || '100'); runCalc(); } });
  if (isMe) S.calcHpIn = hp;
  const hpLabel = isMe ? el('label', {}, '残りHP（実数）', el('span', { class: 'hp-real' }, hp, el('span', { id: 'calc-me-hpmax', class: 'muted' }, x.max_hp ? ` / ${x.max_hp}` : ''))) : el('label', {}, '残りHP%', hp);
  const scr = (key, label) => { const c = el('input', { type: 'checkbox', checked: x[key], onchange: () => { x[key] = c.checked; runCalc(); } }); return el('label', { class: 'inline' }, c, label); };
  const grid = el('div', { class: 'grid' },
    el('label', {}, '性格', natureSelect(x.nature, v => { x.nature = v; runCalc(); })), el('label', {}, '特性', ab),
    el('label', {}, '持ち物', item), megaLbl, el('label', {}, '状態異常', status), hpLabel);
  const typeBox = el('span'), wkBox = el('span');
  const updHead = async () => {
    typeBox.innerHTML = '';
    const key = await fillWeak(wkBox, x.species, x.item, x.ability, !!x.mega);
    if (key) typeBox.append(tChips(typesOf(key), true));
  };
  S.calcHead = S.calcHead || {}; S.calcHead[side] = updHead; updHead();
  box.append(el('h2', {}, isMe ? '自分' : '相手', ' ', typeBox, wkBox), quick, sp, grid, ranks,
    el('div', { class: 'field-row', style: 'margin:6px 0' }, el('small', { class: 'muted' }, isMe ? '自分側の壁' : '相手側の壁'), scr('reflect', 'リフレクター'), scr('light_screen', 'ひかりのかべ'), scr('aurora_veil', 'オーロラベール')),
    spGrid(x.sp, () => runCalc()));
  if (isMe) {
    const mv = el('div', { class: 'moves', style: 'display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px' });
    for (let i = 0; i < 4; i++) mv.append(picker({ kind: 'moves', value: x.moves[i], label: x.moves_ja[i] || '', placeholder: `技${i + 1}`, species: () => x.species,
      onPick: (it) => { x.moves[i] = it ? it.id : null; x.moves_ja[i] = it ? it.ja : ''; runCalc(); } }));
    box.append(mv);
  } else {
    box.append(el('div', { class: 'muted', style: 'margin-top:6px;font-size:12px' }, '相手の技は採用率1%以上の技すべて（変化技を含む。環境データは各ポケモン上位10技まで。無いときは推定型の技）'));
  }
  return box;
}

// 対戦タブの「現在の対面」をダメ計に写す（2体の型・HP・状態異常・ランク・場の状態）
function battleActive() {
  const b = S.bt; const lv = b && b.match && b.live; if (!lv) return null;
  const me = (b.mine || []).find(x => x.index === lv.active.my);
  const opp = (b.opp_builds || []).find(o => o.base_species === lv.active.opp);
  return (me || opp) ? { b, lv, me, opp } : null;
}

async function syncCalcFromBattle(sides = ['me', 'opp']) {
  const a = battleActive(); if (!a) return false;
  const { lv, me, opp } = a;
  const scr = (x, v) => { x.reflect = v === 'reflect' || v === 'both'; x.light_screen = v === 'lightscreen' || v === 'both'; x.aurora_veil = false; };
  if (me && sides.includes('me')) {
    await setFromSet('me', me.set, me.ja);
    const x = S.calc.me, mon = lv.my[String(me.index)] || {};
    x.hp = mon.hp == null ? null : mon.hp; x.max_hp = me.stats.hp;
    x.status = mon.status || 'none'; x.boosts = { ...(mon.boosts || {}) };
    scr(x, lv.field.my_screen);
  }
  if (opp && sides.includes('opp')) {
    await setFromSet('opp', opp.set, opp.ja);
    const x = S.calc.opp, mon = lv.opp[opp.base_species] || {};
    x.hp_percent = Math.max(1, mon.hp == null ? 100 : mon.hp);
    x.status = mon.status || 'none'; x.boosts = { ...(mon.boosts || {}) };
    scr(x, lv.field.opp_screen);
  }
  const f = (v) => (v && v !== 'none') ? v : '';
  $('#f-weather').value = f(lv.field.weather); $('#f-terrain').value = f(lv.field.terrain);
  if ($('#tab-calc').classList.contains('active')) renderCalc();
  return true;
}

$('#calc-reset').addEventListener('click', async () => {
  if (!(await syncCalcFromBattle())) { toast('対戦タブの「現在の対面」が無い'); return; }
  renderCalc(); toast('対戦の対面に戻した');
});

function renderCalcNow() {
  const box = $('#calc-now'); box.innerHTML = '';
  const a = battleActive();
  box.append(el('div', { class: 'muted now-h' }, '現在の対面'));
  if (!a) { box.append(el('div', { class: 'muted' }, '対戦なし')); return; }
  const row = (cls, label, name, key) => el('div', { class: 'now-row ' + cls }, el('span', { class: 'now-side' }, label),
    name ? el('span', {}, el('b', {}, name), ' ', tChips(typesOf(key))) : el('span', { class: 'muted' }, '未選択'));
  box.append(row('me', '自分', a.me && a.me.battle_ja, a.me && a.me.battle_species),
    row('opp', '相手', a.opp && (a.opp.battle_ja || a.opp.ja), a.opp && a.opp.battle_species));
}

function renderCalc() {
  $('#calc-reset').disabled = !battleActive();
  renderCalcNow();
  const a = $('#calc-me'), d = $('#calc-opp');
  a.innerHTML = ''; d.innerHTML = '';
  a.append(sideBox('me')); d.append(sideBox('opp'));
  runCalc();
}
['#f-weather', '#f-terrain', '#f-crit'].forEach(s => $(s).addEventListener('input', () => runCalc()));

function effectRow(x) {
  const e = x.effect || { text: '変化技', notes: [], fails: '' };
  const tag = x.rate != null ? `・採用${x.rate}%` : x.src === 'set' ? '・型' : '';
  return el('div', { class: 'result effect' + (e.fails ? ' muted' : '') },
    el('div', {}, el('b', {}, moveName(x.move, x.move_id)), el('div', { class: 'muted' }, `変化技${tag}`)),
    el('div', { class: 'effect-body' }, el('div', {}, e.text),
      e.fails ? el('div', { class: 'err' }, `この対面では無効・失敗: ${e.fails}`) : '',
      e.notes.length ? el('div', { class: 'muted' }, e.notes.join(' / ')) : ''));
}

function resultRow(x) {
  if (x.category === 'Status') return effectRow(x);
  const immune = x.effectiveness === 0;
  const bar = el('div', { class: 'bar' }, el('span', { style: `left:0;width:${Math.min(100, x.max_pct)}%` }), el('span', { class: 'min', style: `left:0;width:${Math.min(100, x.min_pct)}%` }));
  const tag = x.rate != null ? `・採用${x.rate}%` : x.src === 'set' ? '・型' : '';
  return el('div', { class: 'result' + (immune ? ' muted' : '') },
    el('div', {}, el('b', {}, moveName(x.move, x.move_id)), el('div', { class: 'muted' }, immune ? `無効${tag}` : `威力${x.base_power} ×${x.effectiveness}${tag}`)),
    el('div', {}, immune ? '' : bar, el('div', { class: 'muted' }, x.notes.join(' / '))),
    el('div', {}, el('div', { class: 'ko' + (x.ko.startsWith('確定1') || x.ko.startsWith('乱数1') ? ' kill' : '') }, immune ? '無効' : x.ko), el('div', {}, immune ? '' : `${x.min}–${x.max}（${x.min_pct}–${x.max_pct}%）`)));
}

const runCalc = debounce(async () => {
  const me = S.calc.me, op = S.calc.opp, box = $('#calc-results');
  if (!me.species || !op.species) { box.innerHTML = '<p class="muted">自分と相手を選ぶと、自分→相手（自分の技）と相手→自分（相手の採用率上位の技）を計算する</p>'; return; }
  const side = (x) => ({ species: x.species, nature: x.nature, sp: x.sp, ability: x.ability, item: x.item, boosts: x.boosts, status: x.status && x.status !== 'none' ? x.status : null,
    hp_percent: x.hp_percent, hp: x === S.calc.me && x.hp != null ? x.hp : null, mega: x.mega, reflect: !!x.reflect, light_screen: !!x.light_screen, aurora_veil: !!x.aurora_veil, moves: x.set_moves || [] });
  const body = { me: side(me), opp: side(op), my_moves: me.moves.filter(Boolean), weather: $('#f-weather').value || null, terrain: $('#f-terrain').value || null, crit: $('#f-crit').checked };
  try {
    const r = await api('/api/calc/duel', { method: 'POST', body });
    me.max_hp = r.me.stats.hp;
    const mx = $('#calc-me-hpmax'); if (mx) mx.textContent = ` / ${r.me.stats.hp}`;
    if (S.calcHpIn && me.hp == null && document.activeElement !== S.calcHpIn) S.calcHpIn.value = r.me.stats.hp;
    box.innerHTML = '';
    const faster = r.me.speed > r.opp.speed ? `${r.me.ja}が先に動く` : r.me.speed < r.opp.speed ? `${r.opp.ja}が先に動く` : '同速';
    box.append(el('div', { class: 'stats-line' }, `素早さ ${r.me.ja} ${r.me.speed} / ${r.opp.ja} ${r.opp.speed}（ランク・スカーフ・まひ込み）→ ${faster}`));
    const colA = el('div', { class: 'grow' }, el('h2', {}, `${r.me.ja} → ${r.opp.ja}`, el('small', {}, ` 相手HP ${r.opp.current_hp}/${r.opp.stats.hp}`)));
    if (!r.to_opp.length) colA.append(el('p', { class: 'muted' }, '自分の技を入れる'));
    r.to_opp.forEach(x => colA.append(resultRow(x)));
    const colB = el('div', { class: 'grow' }, el('h2', {}, `${r.opp.ja} → ${r.me.ja}`, el('small', {}, ` 自分HP ${r.me.current_hp}/${r.me.stats.hp}`)));
    r.to_me.forEach(x => colB.append(resultRow(x)));
    box.append(el('div', { class: 'row calc-cols' }, colA, colB),
      el('div', { class: 'stats-line' }, `${r.me.ja}: ${STATS.map(k => STAT_JA[k] + r.me.stats[k]).join(' ')}　／　${r.opp.ja}: ${STATS.map(k => STAT_JA[k] + r.opp.stats[k]).join(' ')}`));
  } catch (e) { box.textContent = '計算エラー: ' + e.message; }
}, 200);

// ---------------------------------------------------------------------------
// 素早さ
// ---------------------------------------------------------------------------
async function renderSpeed() {
  const rows = await api(`/api/speed?ids=${(S.opp.species || []).join(',')}`);
  const t = el('table', {}, el('tr', {}, el('th', { class: 'num' }, '実数値'), el('th', {}, 'ポケモン'), el('th', {}, '条件')));
  for (const r of rows) t.append(el('tr', { class: r.side === 'me' ? 'me' : '' }, el('td', { class: 'num' }, r.speed), el('td', { class: r.side === 'me' ? 'me' : 'them' }, monName(r.ja)), el('td', {}, r.label + (r.scarf ? '（スカーフ込み×1.5前）' : ''))));
  const b = $('#speed-table'); b.innerHTML = ''; b.append(t);
}

// ---------------------------------------------------------------------------
// 図鑑・型
// ---------------------------------------------------------------------------
function renderDexPicker() {
  const pk = picker({ kind: 'pokemon', placeholder: 'ポケモンを検索', onPick: async (it) => { if (it) renderDex(await dexInfo(it.id)); } });
  S.dexPicker = pk;
  $('#dex-picker').append(pk);
}

// 他のタブから図鑑・型を開く（検索した状態にする）
async function openDex(id, ja) {
  showTab('dex');
  if (S.dexPicker && S.dexPicker.setValue) S.dexPicker.setValue(id, ja);
  renderDex(await dexInfo(id));
}
function renderDex(d) {
  const b = $('#dex-body'); b.innerHTML = '';
  const bs = d.baseStats;
  const jaToId = Object.fromEntries(Object.entries((S.typeData || {}).ja || {}).map(([id, ja]) => [ja, id]));
  const weak = Object.entries(d.weakness).sort((a, b) => parseFloat(b[0]) - parseFloat(a[0])).map(([k, v]) => el('div', { class: 'tygroup' },
    el('span', { class: 'tymult m' + String(parseFloat(k)).replace('.', '_') }, `×${parseFloat(k)}`), ...v.map(ja => jaToId[ja] ? typeChip(jaToId[ja], ja) : ja + ' ')));
  const ls = d.likely_set;
  b.append(el('h2', {}, `${d.ja} `, tChips(d.types, true), el('small', {}, `　${d.usage_rank ? `使用率${d.usage_rank}位` : ''}`)),
    el('div', { class: 'row' },
      el('div', { class: 'grow' }, el('div', { class: 'kv' },
        el('div', {}, '種族値'), el('div', {}, `${STATS.map(k => STAT_JA[k] + bs[k]).join(' ')}（合計${d.bst}）`),
        el('div', {}, '特性'), el('div', {}, d.abilities.map(a => a.ja).join(' / ')),
        el('div', {}, '素早さ'), el('div', {}, Object.entries(d.speed).map(([k, v]) => `${k}${v}`).join(' / ')),
        el('div', {}, 'メガ'), el('div', {}, d.megas.map(m => m.ja).join(' / ') || 'なし'),
        el('div', {}, '想定型'), el('div', {}, `${ls.source === 'usage' ? '採用率上位' : '推定'}: ${d.likely_set_label}`))),
      el('div', { class: 'grow' }, el('b', {}, 'タイプ相性（受け）'), ...weak)));
  if (d.usage) {
    const col = (title, rows) => el('div', {}, el('b', {}, title), el('table', {}, ...(rows || []).slice(0, 10).map(r => el('tr', {}, el('td', {}, r.ja), el('td', { class: 'num' }, r.rate != null ? `${r.rate}%` : '')))));
    b.append(el('h2', { style: 'margin-top:12px' }, '採用率 ', el('small', {}, d.usage.fetched_at || '')),
      el('div', { class: 'usage-cols' }, col('技', d.usage.moves), col('持ち物', d.usage.items), col('特性', d.usage.abilities), col('性格', d.usage.natures), col('能力ポイント', (d.usage.sp || []).map(r => ({ ja: `${r.label}（${Object.entries(r.spread).filter(([, v]) => v).map(([k, v]) => STAT_JA[k] + v).join(' ')}）`, rate: r.rate }))), col('倒した技', d.usage.ko_moves), col('倒された技', d.usage.koed_by_moves), col('同じチーム', d.usage.teammates)));
  } else b.append(el('p', { class: 'muted' }, '環境データ未取得'));
}


// ---------------------------------------------------------------------------
// 履歴（相手の6体）
// ---------------------------------------------------------------------------
async function renderHistory() {
  const box = $('#history'); box.innerHTML = '';
  const rows = await api('/api/matches');
  if (!rows.length) { box.append(el('p', { class: 'muted' }, 'まだ無い（選出タブで選出予想を押すと保存される）')); return; }
  const RES = { win: '勝ち', lose: '負け' };
  const t = el('table', {}, el('tr', {}, el('th', {}, '日時'), el('th', {}, '相手の6体'), el('th', {}, '自分のパーティ'), el('th', {}, '相手の選出'), el('th', { class: 'num' }, '記録'), el('th', {}, '結果'), el('th', {}, '')));
  for (const m of rows) {
    const load = async (tab) => { await api(`/api/matches/${m.id}/load`, { method: 'POST' }); S.opp = await api('/api/opponent'); S.oppMtime = S.opp.mtime; renderOppSlots(); S.pred = null; $('#pred-opp').innerHTML = ''; $('#pred-rec').innerHTML = ''; $('#pred-matrix').innerHTML = ''; showTab(tab); };
    t.append(el('tr', { class: m.current ? 'me' : '' },
      el('td', {}, (m.created_at || '').slice(0, 16).replace('T', ' ')),
      el('td', {}, el('span', { class: 'monlist' }, ...m.opp.map((sid, k) => monName(m.opp_ja[k], sid)))),
      el('td', {}, m.team_name || ''),
      el('td', {}, m.opp_picks_ja.join('・')),
      el('td', { class: 'num' }, m.has_detail ? m.records : ''),
      el('td', {}, RES[m.result] || ''),
      el('td', {}, el('button', { onclick: () => load('select') }, '呼び出す'), ' ',
        el('button', { onclick: () => load('battle') }, '対戦を開く'), ' ',
        el('button', { onclick: async () => { if (!confirm(`${m.opp_ja.join('・')} の記録を削除しますか？`)) return; await api(`/api/matches/${m.id}`, { method: 'DELETE' }); renderHistory(); } }, '削除'))));
  }
  box.append(t);
}

// ---------------------------------------------------------------------------
// 対戦モード
// ---------------------------------------------------------------------------
const SRC_JA = { confirmed: '確定', inferred: '逆算', usage: '採用率', estimate: '推定', battle: '推定' };
const srcTag = (src) => el('span', { class: `src src-${src}` }, SRC_JA[src] || src);
S.bt = null; S.btEdit = null;

async function loadBattle() {
  try { S.bt = await api('/api/battle'); } catch (e) { S.bt = { match: null }; }
  renderBattle();
}

async function btPut(body) { S.bt = await api('/api/battle', { method: 'PUT', body }); renderBattle(); }

function renderBattle() {
  const b = S.bt;
  const ids = ['#bt-head', '#bt-picks', '#bt-live', '#bt-mine', '#bt-opp', '#bt-matrix', '#bt-speed', '#bt-form', '#bt-records'];
  ids.forEach(i => { $(i).innerHTML = ''; });
  if (!b || !b.match) { $('#bt-head').append(el('p', { class: 'muted' }, '対戦がない。選出タブで相手の6体を入れて「選出予想」を押すか、履歴から「対戦を開く」。')); return; }
  const m = b.match;
  // ヘッダ
  const res = el('select', { onchange: () => btPut({ result: res.value || '' }) }, el('option', { value: '' }, '結果（未記入）'),
    el('option', { value: 'win', selected: b.result === 'win' }, '勝ち'), el('option', { value: 'lose', selected: b.result === 'lose' }, '負け'));
  const memo = el('input', { value: b.memo || '', placeholder: 'メモ', style: 'min-width:16em' });
  memo.addEventListener('change', () => btPut({ memo: memo.value }));
  $('#bt-head').append(el('div', { class: 'team-bar' },
    el('b', {}, `${(m.created_at || '').slice(5, 16).replace('T', ' ')}`), el('span', {}, `相手: ${m.opp_ja.join('・')}`),
    el('span', { class: 'muted' }, `自分: ${b.my_team_name || ''}`),
    el('button', { title: '記録の前提になる自分のパーティを、今のパーティで取り直す', onclick: async () => { if (!confirm('自分のパーティのコピーを現在のパーティで取り直しますか？（記録は残る）')) return; S.bt = await api('/api/battle/resnapshot', { method: 'POST' }); renderBattle(); } }, 'パーティを取り直す'),
    res, memo));
  // 選出
  const toggle = (arr, v) => arr.includes(v) ? arr.filter(x => x !== v) : (arr.length >= 3 ? arr : [...arr, v]);
  const mineBtns = b.my_team.map(x => el('button', { class: 'pick' + (b.my_picks.includes(x.index) ? ' on' : ''), onclick: () => btPut({ my_picks: toggle(b.my_picks, x.index) }) }, x.ja));
  const oppBtns = m.opp.map((sid, k) => el('button', { class: 'pick opp' + (b.opp_picks.includes(sid) ? ' on' : ''), onclick: () => btPut({ opp_picks: toggle(b.opp_picks, sid) }) }, m.opp_ja[k]));
  $('#bt-picks').append(el('div', {}, el('b', {}, '自分の選出 '), el('small', { class: 'muted' }, '（3体まで）'), ...mineBtns),
    el('div', {}, el('b', {}, '相手の選出 '), el('small', { class: 'muted' }, '（見えた順に3体まで）'), ...oppBtns));
  // 自分
  for (const x of b.mine) $('#bt-mine').append(mineCard(x));
  if (!b.mine.length) $('#bt-mine').append(el('p', { class: 'muted' }, '上で選出を選ぶ'));
  // 相手
  for (const o of b.opp_builds.concat(b.other_builds || [])) $('#bt-opp').append(oppCard(o, b.opp_builds.includes(o)));
  if (!b.opp_builds.length) $('#bt-opp').append(el('p', { class: 'muted' }, '上で相手の選出を選ぶ'));
  // 対面・素早さ
  if (b.matrix.length && b.opp_builds.length) {
    const t = el('table', { class: 'mx' }, el('tr', {}, el('th', {}, ''), ...b.opp_builds.map(o => el('th', {}, monName(o.battle_ja || o.ja, o.battle_species)))));
    const line = (who, mv, id, p, hits) => el('div', { class: 'mx-line' + (who === '相' ? ' muted' : '') }, el('span', { class: 'mx-who' }, who),
      mv ? moveName(mv, id) : '-', el('span', { class: 'mx-pct' }, ` ${pct(p)}`), hits ? el('small', {}, `（${hits}発）`) : '');
    b.matrix.forEach((row, i) => t.append(el('tr', {}, el('th', {}, monName(b.mine[i].battle_ja, b.mine[i].battle_species)), ...row.map(x => el('td', {
      class: x.score >= 0.75 ? 'cell-good' : x.score <= 0.25 ? 'cell-bad' : 'cell-mid',
    }, line('自', x.a_move, x.a_move_id, x.a_pct, x.a_hits), line('相', x.b_move, x.b_move_id, x.b_pct, x.b_hits))))));
    $('#bt-matrix').append(el('div', { class: 'scroll-x' }, t));
  } else $('#bt-matrix').append(el('p', { class: 'muted' }, '自分と相手の選出を選ぶと表示'));
  if (b.speed.length) {
    const t = el('table', {}, el('tr', {}, el('th', { class: 'num' }, 'S'), el('th', {}, ''), el('th', {}, '')));
    for (const r of b.speed) t.append(el('tr', { class: r.side === 'me' ? 'me' : '' }, el('td', { class: 'num' }, r.speed), el('td', { class: r.side === 'me' ? 'me' : 'them' }, monName(r.ja)), el('td', { class: 'muted' }, r.label)));
    $('#bt-speed').append(t);
  }
  renderBtLive();
  renderBtForm();
  renderBtRecords();
}

// ---- 現在の対面 ----
const STATUS_OPTS = [['none', 'なし'], ['brn', 'やけど'], ['par', 'まひ'], ['psn', 'どく'], ['tox', 'もうどく'], ['slp', 'ねむり'], ['frz', 'こおり']];
const STATUS_JA = Object.fromEntries(STATUS_OPTS);
const SCREEN_OPTS = [['none', 'なし'], ['reflect', 'リフレクター'], ['lightscreen', 'ひかりのかべ'], ['both', '両方・オーロラベール']];
const livePut = (patch) => api('/api/battle/live', { method: 'PUT', body: patch }).then(v => { S.bt = v; return v; });
const livePutLater = debounce((patch, rerender) => livePut(patch).then(() => { if (rerender) renderBattle(); }), 400);

// カードのどこを触っても、そのポケモンを場に出ている扱いにする（入力中のフォーカスは保つ）
function setActive(side, key, e) {
  const lv = S.bt && S.bt.live; if (!lv || lv.active[side] === key) return;
  lv.active[side] = key;
  document.querySelectorAll(`#bt-live .live-card${side === 'opp' ? '.opp' : ':not(.opp)'}`).forEach(c => c.classList.toggle('active', c.dataset.key === String(key)));
  livePut({ active: { [side]: key } });
  if (!S.btEdit) renderBtForm();
  syncCalcFromBattle([side === 'my' ? 'me' : 'opp']);  // 対面が変わったらダメ計の同じ側も差し替える
}

function renderBtLive() {
  const b = S.bt, box = $('#bt-live'), lv = b.live;
  if (!lv || (!b.my_picks.length && !b.opp_picks.length)) { box.append(el('p', { class: 'muted' }, '上で自分と相手の選出を選ぶと表示')); return; }
  const rankRow = (side, key, mon) => el('div', { class: 'ranks' }, ...['atk', 'def', 'spa', 'spd', 'spe'].map(k => {
    const s2 = el('select', { title: `${STAT_JA[k]}ランク`, onchange: () => { mon.boosts[k] = parseInt(s2.value, 10); s2.className = mon.boosts[k] > 0 ? 'up' : mon.boosts[k] < 0 ? 'down' : ''; livePutLater({ [side]: { [key]: { boosts: { [k]: mon.boosts[k] } } } }); S.btUpdSummary && S.btUpdSummary(); } },
      ...[...Array(13).keys()].map(i => 6 - i).map(v => el('option', { value: v, selected: v === (mon.boosts[k] || 0) }, v > 0 ? `+${v}` : `${v}`)));
    s2.className = mon.boosts[k] > 0 ? 'up' : mon.boosts[k] < 0 ? 'down' : '';
    return el('label', {}, STAT_JA[k], s2);
  }), el('button', { class: 'mini', title: 'ランクをすべて0に（交代したとき）', onclick: (e) => { e.stopPropagation(); livePut({ [side]: { [key]: { boosts: { atk: 0, def: 0, spa: 0, spd: 0, spe: 0 } } } }).then(renderBattle); } }, '0'));
  const statusSel = (side, key, mon) => { const s2 = el('select', { onchange: () => { mon.status = s2.value; livePutLater({ [side]: { [key]: { status: s2.value } } }); S.btUpdSummary && S.btUpdSummary(); } }, ...STATUS_OPTS.map(([v, t]) => el('option', { value: v, selected: v === mon.status }, t))); return s2; };
  const hpBar = (ratio) => el('div', { class: 'bar hpbar' }, el('span', { class: 'min ' + (ratio > 0.5 ? 'hp-g' : ratio > 0.2 ? 'hp-y' : 'hp-r'), style: `left:0;width:${Math.max(0, Math.min(100, ratio * 100))}%` }));
  const myRow = el('div', { class: 'live-row' }, el('div', { class: 'live-side' }, '自分'));
  for (const x of b.mine) {
    const key = String(x.index), mon = lv.my[key]; if (!mon) continue;
    const max = x.stats.hp; const hp = mon.hp == null ? max : mon.hp;
    const hpIn = el('input', { type: 'number', min: 0, max, value: hp, class: 'w5' });
    hpIn.addEventListener('change', () => { livePut({ my: { [key]: { hp: Math.max(0, Math.min(max, parseInt(hpIn.value || '0', 10))) } } }).then(renderBattle); });
    const card = el('div', { 'data-key': key, class: 'live-card' + (lv.active.my === x.index ? ' active' : '') + (hp <= 0 ? ' fainted' : ''), onclick: (e) => setActive('my', x.index, e) },
      el('div', { class: 't' }, monName(x.battle_ja, x.battle_species), weakChips(x.battle_species, x.ability_id, x.ability_ja), mon.status !== 'none' ? el('span', { class: 'st st-' + mon.status }, STATUS_JA[mon.status]) : ''),
      hpBar(hp / max), el('div', { class: 'live-line' }, 'HP ', hpIn, ` / ${max}`, statusSel('my', key, mon)), rankRow('my', key, mon));
    myRow.append(card);
  }
  const oppRow = el('div', { class: 'live-row' }, el('div', { class: 'live-side them' }, '相手'));
  for (const o of b.opp_builds) {
    const key = o.base_species, mon = lv.opp[key]; if (!mon) continue;
    const hp = mon.hp == null ? 100 : mon.hp;
    const hpIn = el('input', { type: 'number', min: 0, max: 100, value: hp, class: 'w4' });
    hpIn.addEventListener('change', () => { livePut({ opp: { [key]: { hp: Math.max(0, Math.min(100, parseFloat(hpIn.value || '0'))) } } }).then(renderBattle); });
    const extras = [];
    if (b.opp_has_mega[key]) {
      const st = mon.mega_state || 'auto';
      const setMega = (v) => (e) => { e.stopPropagation(); livePut({ opp: { [key]: { mega_state: st === v ? 'auto' : v } } }).then(() => { renderBattle(); if (lv.active.opp === key) syncCalcFromBattle(['opp']); }); };
      extras.push(el('span', { class: 'seg mega-seg' },
        el('button', { class: 'mini' + (st === 'yes' ? ' on' : ''), title: 'メガシンカした（もう一度押すと未確定に戻す）', onclick: setMega('yes') }, 'メガした'),
        el('button', { class: 'mini' + (st === 'no' ? ' on' : ''), title: 'メガシンカしなかった（メガストーン以外の型で表示）', onclick: setMega('no') }, 'メガしなかった')),
        el('small', { class: 'muted' }, st === 'auto' ? (o.mega_hint === false ? '他がメガ済み' : '未確定') : ''));
    }
    const card = el('div', { 'data-key': key, class: 'live-card opp' + (lv.active.opp === key ? ' active' : '') + (hp <= 0 ? ' fainted' : ''), onclick: (e) => setActive('opp', key, e) },
      el('div', { class: 't' }, monName(o.battle_ja || o.ja, o.battle_species), weakChips(o.battle_species, oppAbility(o), o.ability && o.ability.ja), mon.status !== 'none' ? el('span', { class: 'st st-' + mon.status }, STATUS_JA[mon.status]) : ''),
      hpBar(hp / 100), el('div', { class: 'live-line' }, 'HP ', hpIn, '%', statusSel('opp', key, mon), ...extras), rankRow('opp', key, mon));
    oppRow.append(card);
  }
  const fsel = (key, label, opts) => { const s2 = el('select', { onchange: () => { lv.field[key] = s2.value; livePut({ field: { [key]: s2.value } }); S.btUpdSummary && S.btUpdSummary(); } }, ...opts.map(([v, t]) => el('option', { value: v, selected: v === lv.field[key] }, t))); return el('label', {}, label, s2); };
  const fieldRow = el('div', { class: 'form-grid' },
    fsel('weather', '天候', [['none', 'なし'], ['sun', '晴れ'], ['rain', '雨'], ['sand', '砂嵐'], ['snow', '雪']]),
    fsel('terrain', 'フィールド', [['none', 'なし'], ['electric', 'エレキ'], ['grassy', 'グラス'], ['psychic', 'サイコ'], ['misty', 'ミスト']]),
    fsel('my_screen', '自分側の壁', SCREEN_OPTS), fsel('opp_screen', '相手側の壁', SCREEN_OPTS));
  box.append(myRow, oppRow, fieldRow);
}

function mineCard(x) {
  const spTxt = STATS.filter(k => x.sp[k]).map(k => `${STAT_JA[k]}${x.sp[k]}`).join(' ') || '無振り';
  return el('div', { class: 'bcard' },
    el('div', { class: 't' }, monName(x.battle_ja, x.battle_species), weakChips(x.battle_species, x.ability_id, x.ability_ja)),
    el('div', { class: 'kv2' },
      el('div', {}, '持ち物'), el('div', {}, x.item_ja || 'なし'),
      el('div', {}, '特性'), el('div', {}, x.ability_ja || '不明'),
      el('div', {}, '性格'), el('div', {}, x.nature_ja || '不明'),
      el('div', {}, '能力P'), el('div', {}, spTxt),
      el('div', {}, '技'), el('div', { class: 'mvlist' }, ...x.moves.map(mv => el('div', {}, moveName(mv.ja, mv.id)))),
      el('div', {}, '実数値'), el('div', { class: 'stats-line' }, STATS.map(k => `${STAT_JA[k]}${x.stats[k]}`).join(' '))));
}

function oppCard(o, picked) {
  const inf = o.inference || {};
  const spTxt = STATS.filter(k => o.sp[k]).map(k => `${STAT_JA[k]}${o.sp[k]}`).join(' ') || '無振り';
  const spSrc = Object.values(o.sp_src || {}).includes('inferred') ? 'inferred' : (o.sp_src || {}).hp || 'usage';
  const ranges = Object.entries(o.stats_range || {}).map(([k, v]) => `${STAT_JA[k]} ${v[0]}〜${v[1]}`).join(' / ');
  const card = el('div', { class: 'bcard' + (picked ? '' : ' muted') },
    el('div', { class: 't' }, monName(o.battle_ja || o.ja, o.battle_species), weakChips(o.battle_species, oppAbility(o), o.ability && o.ability.ja), picked ? '' : el('small', {}, '（選出外・記録あり）')),
    el('div', { class: 'kv2' },
      el('div', {}, '持ち物'), el('div', {}, o.item.ja || '不明', srcTag(o.item.src), o.item.p ? el('small', { class: 'muted' }, ` ${Math.round(o.item.p * 100)}%`) : ''),
      el('div', {}, '特性'), el('div', {}, o.ability.ja || '不明', srcTag(o.ability.src)),
      el('div', {}, '性格'), el('div', {}, o.nature.ja || '不明', srcTag(o.nature.src), o.nature.p ? el('small', { class: 'muted' }, ` ${Math.round(o.nature.p * 100)}%`) : ''),
      el('div', {}, '能力P'), el('div', {}, spTxt, srcTag(spSrc)),
      el('div', {}, '技'), el('div', { class: 'mvlist' }, ...o.moves.map(mv => el('div', {}, moveName(mv.ja, mv.id), srcTag(mv.src)))),
      el('div', {}, '実数値'), el('div', { class: 'stats-line' }, STATS.map(k => `${STAT_JA[k]}${o.stats[k]}`).join(' ')),
      ...(ranges ? [el('div', {}, '逆算範囲'), el('div', { class: 'stats-line' }, ranges)] : [])));
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

// 記録フォーム
function screenOn(v, physical) { return v === 'both' || (physical ? v === 'reflect' : v === 'lightscreen'); }

function renderBtForm() {
  const b = S.bt, box = $('#bt-form');
  box.innerHTML = '';
  const ed = S.btEdit;  // 編集中の記録（編集では条件を個別に直せる）
  const lv = b.live;
  const f = ed ? JSON.parse(JSON.stringify(ed)) : { kind: S.btKind || 'taken', cond: {} };
  f.cond = f.cond || {};
  if (!ed && lv) { f.opp = lv.active.opp; f.my_index = lv.active.my; }
  const kindSeg = el('div', { class: 'seg' }, ...[['taken', '被ダメ（相手→自分）'], ['dealt', '与ダメ（自分→相手）'], ['reveal', '判明（持ち物・技・特性）']].map(([k, t]) =>
    el('button', { class: f.kind === k ? 'on' : '', onclick: () => { if (ed) return; S.btKind = k; renderBtForm(); } }, t)));
  box.append(kindSeg);
  box.classList.toggle('editing', !!ed);
  const oppList = b.opp_picks.length ? b.opp_picks : b.match.opp;
  const oppName = (sid) => b.match.opp_ja[b.match.opp.indexOf(sid)];
  const oppSel = el('select', {}, ...oppList.map(sid => el('option', { value: sid, selected: sid === f.opp }, oppName(sid))));
  const myList = b.my_picks.length ? b.my_picks : b.my_team.map(x => x.index);
  const mySel = el('select', {}, ...myList.map(i => el('option', { value: i, selected: i === f.my_index }, b.my_team[i].ja)));
  const grid = el('div', { class: 'form-grid' });
  const done = async (body) => {
    try {
      S.bt = ed ? await api(`/api/battle/records/${ed.id}`, { method: 'PUT', body }) : await api('/api/battle/records', { method: 'POST', body });
      S.btEdit = null; renderBattle(); toast(ed ? '記録を更新した' : '記録を追加し、HPを反映した');
    } catch (e) { let msg = e.message; try { msg = JSON.parse(e.message).detail; } catch (_) { /* */ } toast('入力を確認: ' + msg); }
  };
  const actions = (onSubmit, hint) => el('div', { class: 'actions' }, el('button', { class: 'primary', onclick: onSubmit }, ed ? '更新' : '追加'),
    ed ? el('button', { onclick: () => { S.btEdit = null; renderBtForm(); } }, 'キャンセル') : '', hint ? el('small', { class: 'muted' }, hint) : '');

  if (f.kind === 'reveal') {
    const typeSel = el('select', {}, ...[['item', '持ち物'], ['move', '技'], ['ability', '特性']].map(([v, t]) => el('option', { value: v, selected: f.reveal_type === v }, t)));
    const valBox = el('div'); let valPicker;
    const mk = () => { valBox.innerHTML = ''; const kind = { item: 'items', move: 'moves', ability: 'abilities' }[typeSel.value];
      valPicker = picker({ kind, value: f.reveal_value, label: f.reveal_value_ja || '', placeholder: '名前', species: () => kind === 'items' ? null : oppSel.value }); valBox.append(valPicker); };
    typeSel.addEventListener('change', mk); oppSel.addEventListener('change', mk); mk();
    grid.append(el('label', {}, '相手', oppSel), el('label', {}, '種類', typeSel), el('label', {}, '内容', valBox));
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
      const my = b.my_team[parseInt(mySel.value, 10)];
      const ms = el('select', { onchange: () => { const x = my.moves.find(q => q.id === ms.value); moveInfo = { id: ms.value, category: x && x.category }; updSummary(); } },
        ...(my ? my.moves : []).map(mv => el('option', { value: mv.id, selected: mv.id === f.move }, mv.ja)));
      moveBox.append(ms);
      const x = my && my.moves.find(q => q.id === ms.value); moveInfo = { id: ms.value || null, category: x && x.category };
    }
  };
  const liveMy = () => lv && lv.my[String(mySel.value)];
  const liveOpp = () => lv && lv.opp[oppSel.value];
  const myMax = () => { const x = b.mine.find(q => q.index === parseInt(mySel.value, 10)); return x ? x.stats.hp : b.my_team[parseInt(mySel.value, 10)].hp; };
  const curBefore = () => taken ? (liveMy() && liveMy().hp != null ? liveMy().hp : myMax()) : (liveOpp() && liveOpp().hp != null ? liveOpp().hp : 100);
  const before = el('input', { type: 'number', class: 'w5', value: f.before != null ? f.before : curBefore() });
  const after = el('input', { type: 'number', class: 'w5', value: f.after != null ? f.after : '' });
  const ko = el('input', { type: 'checkbox', checked: !!f.cond.ko });
  const crit = el('input', { type: 'checkbox', checked: !!f.cond.crit });
  const hits = el('select', {}, el('option', { value: '' }, '1回'), ...[2, 3, 4, 5].map(n => el('option', { value: n, selected: f.cond.hits === n }, `${n}回`)));
  mySel.addEventListener('change', () => { mkMove(); if (!ed) before.value = curBefore(); updSummary(); });
  oppSel.addEventListener('change', () => { mkMove(); if (!ed) before.value = curBefore(); updSummary(); });
  mkMove();
  grid.append(el('label', {}, taken ? '攻撃した相手' : '攻撃された相手', oppSel), el('label', {}, taken ? '受けた自分' : '攻撃した自分', mySel),
    el('label', {}, '技', moveBox),
    el('label', {}, taken ? `受ける前のHP（実数）` : '当てる前の相手HP（%）', before),
    el('label', {}, taken ? '受けた後のHP（実数）' : '当てた後の相手HP（%）', after),
    el('label', { class: 'inline' }, ko, 'この攻撃で倒れた'), el('label', { class: 'inline' }, crit, '急所'), el('label', {}, '連続技', hits));
  box.append(grid);

  // 条件: 新規は「現在の対面」から自動、編集は個別に直せる
  const summary = el('div', { class: 'cond-summary' });
  const condFromLive = () => {
    const physical = moveInfo.category ? moveInfo.category === 'Physical' : true;
    const [ak, dk] = physical ? ['atk', 'def'] : ['spa', 'spd'];
    const me = liveMy() || { boosts: {}, status: 'none' }, op = liveOpp() || { boosts: {}, status: 'none', mega: false };
    const att = taken ? op : me, dfd = taken ? me : op;
    return { weather: lv ? lv.field.weather : 'none', terrain: lv ? lv.field.terrain : 'none',
      atk_boost: att.boosts[ak] || 0, def_boost: dfd.boosts[dk] || 0, atk_status: att.status || 'none', def_status: dfd.status || 'none',
      screen: screenOn(lv ? lv.field[taken ? 'my_screen' : 'opp_screen'] : 'none', physical), opp_mega: op.mega_state === 'yes' || !!op.mega,
      _uncat: !moveInfo.category };
  };
  function updSummary() {
    if (ed) return;
    const c = condFromLive();
    const W = { none: '', sun: '晴れ', rain: '雨', sand: '砂嵐', snow: '雪' }, T = { none: '', electric: 'エレキF', grassy: 'グラスF', psychic: 'サイコF', misty: 'ミストF' };
    const parts = [W[c.weather], T[c.terrain], c.atk_boost ? `攻撃側${c.atk_boost > 0 ? '+' : ''}${c.atk_boost}` : '', c.def_boost ? `防御側${c.def_boost > 0 ? '+' : ''}${c.def_boost}` : '',
      c.atk_status !== 'none' ? `攻撃側${STATUS_JA[c.atk_status]}` : '', c.def_status !== 'none' ? `防御側${STATUS_JA[c.def_status]}` : '', c.screen ? '壁' : '', c.opp_mega ? '相手メガ後' : ''].filter(Boolean);
    summary.textContent = '条件（現在の対面から）: ' + (parts.join('・') || 'なし') + (c._uncat ? '　※技を選ぶと物理/特殊に合わせてランクを選び直す' : '');
  }
  let condGrid = null;
  if (ed) {
    const tri = (key, label) => { const s2 = el('select', {}, el('option', { value: '' }, '未入力'), el('option', { value: 'false' }, 'なし'), el('option', { value: 'true' }, 'あり'));
      s2.value = f.cond[key] === true ? 'true' : f.cond[key] === false ? 'false' : ''; s2.dataset.key = key; s2.dataset.t = 'bool'; return el('label', {}, label, s2); };
    const opt = (key, label, opts, t = 'str') => { const s2 = el('select', {}, el('option', { value: '' }, '未入力'), ...opts.map(([v, tt]) => el('option', { value: v }, tt)));
      s2.value = f.cond[key] != null ? String(f.cond[key]) : ''; s2.dataset.key = key; s2.dataset.t = t; return el('label', {}, label, s2); };
    const ranks = [...Array(13).keys()].map(i => 6 - i).map(v => [String(v), v > 0 ? `+${v}` : `${v}`]);
    if (f.cond.atk_status == null && f.cond.burn) f.cond.atk_status = 'brn';
    condGrid = el('div', { class: 'form-grid' },
      opt('weather', '天候', [['none', 'なし'], ['sun', '晴れ'], ['rain', '雨'], ['sand', '砂嵐'], ['snow', '雪']]),
      opt('terrain', 'フィールド', [['none', 'なし'], ['electric', 'エレキ'], ['grassy', 'グラス'], ['psychic', 'サイコ'], ['misty', 'ミスト']]),
      opt('atk_boost', '攻撃側ランク', ranks, 'int'), opt('def_boost', '防御側ランク', ranks, 'int'),
      opt('atk_status', '攻撃側の状態異常', STATUS_OPTS), opt('def_status', '防御側の状態異常', STATUS_OPTS),
      tri('screen', '防御側の壁'), tri('opp_mega', '相手がメガシンカ後'));
    box.append(el('div', { class: 'muted' }, '条件（この記録だけ修正）'), condGrid);
  } else {
    box.append(summary); updSummary(); S.btUpdSummary = updSummary;
  }
  const collect = () => {
    let cond;
    if (ed) {
      cond = {};
      condGrid.querySelectorAll('select[data-key]').forEach(s2 => { if (s2.value === '') return; cond[s2.dataset.key] = s2.dataset.t === 'bool' ? s2.value === 'true' : s2.dataset.t === 'int' ? parseInt(s2.value, 10) : s2.value; });
    } else { cond = condFromLive(); delete cond._uncat; }
    if (ko.checked) cond.ko = true;
    if (crit.checked) cond.crit = true;
    if (hits.value) cond.hits = parseInt(hits.value, 10);
    return { kind: f.kind, opp: oppSel.value, my_index: parseInt(mySel.value, 10), move: moveInfo.id,
      before: before.value === '' ? null : parseFloat(before.value), after: ko.checked && after.value === '' ? 0 : (after.value === '' ? null : parseFloat(after.value)), cond };
  };
  box.append(actions(() => done(collect()), taken ? '自分のHPは実数（画面の数値）' : '相手のHPは画面の%'));
}

function renderBtRecords() {
  const b = S.bt, box = $('#bt-records');
  if (!b.records.length) { box.append(el('p', { class: 'muted' }, 'まだ記録が無い')); return; }
  const t = el('table', {}, el('tr', {}, el('th', {}, '#'), el('th', {}, '種類'), el('th', {}, '内容'), el('th', { class: 'num' }, '候補'), el('th', {}, '')));
  b.records.forEach((r, i) => {
    t.append(el('tr', { class: r.feasible === 0 ? 'bad' : '' },
      el('td', {}, i + 1), el('td', { class: 'kind' }, el('span', { class: 'kind-' + r.kind }, r.kind_short || r.kind_ja), r.chip_move && moveType(r.chip_move) ? typeChip(moveType(r.chip_move), '', true) : ''), el('td', {}, r.summary),
      el('td', { class: 'num', title: '観測値と矛盾しない組み合わせの数。0なら入力か条件の誤り' }, r.feasible == null ? '' : r.feasible),
      el('td', {}, el('button', { onclick: async () => {
        const e2 = JSON.parse(JSON.stringify(r));
        if (e2.my) e2.my_index = b.my_team.findIndex(x => x.species === e2.my.species);
        const ja = async (kind, id) => { if (!id) return ''; const q = await api(`/api/search?kind=${kind}&q=${encodeURIComponent(id)}&limit=1&include_mega=true`); return q[0] ? q[0].ja : id; };
        if (e2.move) e2.move_ja = await ja('moves', e2.move);
        if (e2.reveal_value) e2.reveal_value_ja = await ja({ item: 'items', move: 'moves', ability: 'abilities' }[e2.reveal_type], e2.reveal_value);
        S.btEdit = e2; $('#bt-form').innerHTML = ''; renderBtForm(); $('#bt-form').scrollIntoView({ behavior: 'smooth' });
      } }, '編集'), ' ', el('button', { onclick: async () => { S.bt = await api(`/api/battle/records/${r.id}`, { method: 'DELETE' }); renderBattle(); toast('削除した'); } }, '削除'))));
  });
  box.append(t);
}


// ---------------------------------------------------------------------------
// タイプ相性
// ---------------------------------------------------------------------------
S.tyFocus = [];

async function renderTypes() {
  await loadTypeData();
  const { types, chart, pokemon } = S.ty;
  const ja = Object.fromEntries(types.map(t => [t.id, t.ja]));
  const F = S.tyFocus;
  const toggle = (t) => { S.tyFocus = F.includes(t) ? F.filter(x => x !== t) : (F.length >= 2 ? [F[1], t] : [...F, t]); renderTypes(); };
  // 選択
  const pick = $('#ty-pick'); pick.innerHTML = '';
  for (const t of types) {
    const on = F.includes(t.id);
    pick.append(el('button', { class: 'tpick' + (on ? ' on' : ''), style: `background:${on ? TYPE_COLOR[t.id] : 'transparent'};color:${on ? typeFg(t.id) : 'inherit'};border-color:${TYPE_COLOR[t.id]}`, onclick: () => toggle(t.id) }, t.ja));
  }
  if (F.length) pick.append(el('button', { onclick: () => { S.tyFocus = []; renderTypes(); } }, 'クリア'));
  const eff = (atk, defs) => defs.reduce((a, d) => a * chart[atk][d], 1);
  const groupList = (pairs, order) => {
    const box = el('div');
    for (const [mult, label] of order) {
      const ts = pairs.filter(p => p[1] === mult).map(p => p[0]);
      if (!ts.length) continue;
      box.append(el('div', { class: 'tygroup' }, el('span', { class: 'tymult m' + String(mult).replace('.', '_') }, label), ...ts.map(t => typeChip(t, ja[t]))));
    }
    return box;
  };
  const mons = $('#ty-mons'), atk = $('#ty-atk'), def = $('#ty-def'), ctr = $('#ty-counter');
  [mons, atk, def, ctr].forEach(x => { x.innerHTML = ''; });
  if (!F.length) {
    [mons, atk, def, ctr].forEach(x => x.append(el('p', { class: 'muted' }, 'タイプを選ぶと表示')));
  } else {
    // 該当ポケモン
    const match = pokemon.filter(p => p.searchable !== false && p.types.length === F.length && F.every(t => p.types.includes(t)));
    const normal = match.filter(p => !p.isMega), mega = match.filter(p => p.isMega);
    const monBtn = (p) => el('button', { class: 'chip link', title: '図鑑・型で開く', onclick: () => openDex(p.id, p.ja) }, p.ja);
    mons.append(el('div', {}, `${match.length}体`), el('div', { class: 'tymons' }, ...normal.map(monBtn)));
    if (mega.length) mons.append(el('div', { class: 'muted', style: 'margin-top:4px' }, 'メガシンカ後'), el('div', { class: 'tymons' }, ...mega.map(monBtn)));
    // 攻撃側
    const AORD = [[2, '×2'], [0.5, '×0.5'], [0, '×0']];  // 等倍は省略
    for (const a of F) {
      atk.append(el('div', { class: 'tysub' }, typeChip(a, ja[a]), ' の技'), groupList(types.map(t => [t.id, chart[a][t.id]]), AORD));
    }
    if (F.length === 2) {
      atk.append(el('div', { class: 'tysub' }, '一致技2つの良い方（通りの確認）'), groupList(types.map(t => [t.id, Math.max(chart[F[0]][t.id], chart[F[1]][t.id])]), AORD));
    }
    // 防御側
    const DORD = [[4, '×4'], [2, '×2'], [0.5, '×0.5'], [0.25, '×0.25'], [0, '×0']];  // 等倍は省略
    const defPairs = types.map(t => [t.id, eff(t.id, F)]);
    def.append(groupList(defPairs, DORD));
    // 弱点を突いてくる相手への有効打
    const weak = defPairs.filter(p => p[1] >= 2).map(p => p[0]);
    if (!weak.length) ctr.append(el('p', { class: 'muted' }, '抜群を取られるタイプが無い'));
    else {
      ctr.append(el('div', { class: 'tygroup' }, el('span', { class: 'muted' }, '抜群を取ってくるタイプ: '), ...weak.map(t => typeChip(t, ja[t]))));
      const rows = types.map(t => ({ t: t.id, hits: weak.filter(w => chart[t.id][w] >= 2) })).filter(r => r.hits.length).sort((a, b) => b.hits.length - a.hits.length);
      const tb = el('table', {}, el('tr', {}, el('th', {}, '技のタイプ'), el('th', { class: 'num' }, `抜群（/${weak.length}）`), el('th', {}, '抜群を取れる相手')));
      for (const r of rows) tb.append(el('tr', {}, el('td', {}, typeChip(r.t, ja[r.t])), el('td', { class: 'num' }, r.hits.length), el('td', {}, ...r.hits.map(w => typeChip(w, ja[w])))));
      ctr.append(tb);
    }
  }
  // 相性表
  const tbl = el('table', { class: 'tychart' });
  tbl.append(el('tr', {}, el('th', {}, '攻＼防'), ...types.map(t => el('th', { class: 'tyh' + (F.includes(t.id) ? ' focus' : ''), onclick: () => toggle(t.id), title: t.ja }, typeChip(t.id, t.ja, true)))));
  for (const a of types) {
    const tr = el('tr', {}, el('th', { class: 'tyh' + (F.includes(a.id) ? ' focus' : ''), onclick: () => toggle(a.id) }, typeChip(a.id, a.ja)));
    for (const d of types) {
      const v = chart[a.id][d.id];
      tr.append(el('td', { class: 'tyc m' + String(v).replace('.', '_') + (F.includes(a.id) || F.includes(d.id) ? ' focus' : '') }, v === 1 ? '' : v === 2 ? '◎' : v === 0.5 ? '△' : '×'));
    }
    tbl.append(tr);
  }
  const c = $('#ty-chart'); c.innerHTML = ''; c.append(tbl);
}

// ---------------------------------------------------------------------------
async function init() {
  const steps = [];
  const run = async (name, fn) => { try { await fn(); } catch (e) { steps.push(name); console.error(name, e); } };
  await run('meta', async () => {
    S.meta = await api('/api/meta');
    if (S.meta.api_version !== APP_API_VERSION) showBanner(`画面とサーバの版が合っていない（画面 ${APP_API_VERSION} / サーバ ${S.meta.api_version || '古い版'}）。ターミナルで Ctrl+C → python -m app で起動し直し、ブラウザを再読み込みしてください`);
  });
  await run('types', loadTypeData);
  const snap = (S.meta || {}).snapshot;
  const st = $('#status'); st.innerHTML = '';
  st.append(`${snap ? `${snap.source} ${snap.season_label}（上位${snap.detail}体・${(snap.fetched_at || '').slice(5, 16).replace('T', ' ')}）` : '環境データ未取得'} `,
    el('button', { onclick: async (e) => {
      e.target.disabled = true; e.target.textContent = '取得中…';
      const r = await api('/api/collect', { method: 'POST' });
      for (let i = 0; i < 120; i++) {
        await new Promise(res => setTimeout(res, 3000));
        const j = (await api('/api/jobs')).find(x => x.id === r.job);
        if (j && j.status !== 'running') { toast(j.status === 'done' ? '環境データを更新した' : `取得失敗: ${j.error}`); break; }
      }
      S.dexCache = {}; S.threats = null; S.meta = await api('/api/meta'); init();
    } }, '環境データ更新'));
  await run('パーティ', loadTeam);
  await run('相手の6体', async () => { S.opp = await api('/api/opponent'); S.oppMtime = S.opp.mtime; renderOppSlots(); });
  await run('選出予想', async () => { S.pred = await api('/api/predict'); renderPred(); });
  await run('図鑑', async () => { $('#dex-picker').innerHTML = ''; renderDexPicker(); });
  await run('対戦', async () => { S.bt = await api('/api/battle'); });
  await run('ダメ計', async () => { if (!S.calc.me.species && !S.calc.opp.species) await syncCalcFromBattle(); });
  if (steps.length) showBanner(`読み込みに失敗: ${steps.join('・')}。サーバを起動し直して再読み込みしてください`);
}
init();
