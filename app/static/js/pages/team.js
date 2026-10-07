import { $, el, api, lead, toast, picker, help, typeChip, debounce } from '../ui.js';
import { S, dexInfo, isService, jaOf, loadMeta, loadTypes } from '../store.js';

import { STATS, STAT_JA, spGrid } from '../parts.js';
import { evaluateTeam } from './evaluate.js';

// team = 編集中、saved = 保存済み。保存は手動のみで、保存済みと違う項目に印を付ける
let team = null, saved = null, teams = [], viewEl = null, cardEls = [], ui = {};

const clone = (x) => JSON.parse(JSON.stringify(x));
const strip = (m) => ({ ...Object.fromEntries(Object.entries(m).filter(([k]) => !k.startsWith('_'))), moves: (m.moves || []).filter(Boolean) });
const body = () => ({ id: team.id, name: team.name, archetype: team.archetype, members: team.members.map(strip) });
const pad4 = (a) => [0, 1, 2, 3].map(i => (a || [])[i] || null);

// 保存済みとの違い（項目名の集合）
function diff(i) {
  const a = team.members[i], b = saved.members[i], out = new Set();
  for (const k of ['species', 'nature', 'ability', 'item']) if ((a[k] || null) !== (b[k] || null)) out.add(k);
  for (const k of STATS) if (((a.sp || {})[k] || 0) !== ((b.sp || {})[k] || 0)) out.add('sp.' + k);
  const am = pad4(a.moves), bm = pad4(b.moves);
  for (let j = 0; j < 4; j++) if (am[j] !== bm[j]) out.add('move' + j);
  return out;
}
function countChanges() {
  let n = (team.name || '') !== (saved.name || '') ? 1 : 0;
  if ((team.archetype || null) !== (saved.archetype || null)) n++;
  team.members.forEach((_, i) => { n += diff(i).size; });
  return n;
}
const guard = () => !team || countChanges() === 0 || confirm('保存していない変更があります。破棄して続けますか？');
window.addEventListener('beforeunload', (e) => { if (team && saved && countChanges() > 0) { e.preventDefault(); e.returnValue = ''; } });

// 変更した項目に印を付け、保存・戻すボタンの状態を合わせる
function paint() {
  const mark = (node, on) => { if (node) node.classList.toggle('changed', on); };
  mark(ui.name, (team.name || '') !== (saved.name || ''));
  mark(ui.arch, (team.archetype || null) !== (saved.archetype || null));
  cardEls.forEach((c, i) => { const ch = diff(i); for (const [k, node] of Object.entries(c.fields)) mark(node, ch.has(k)); });
  const n = countChanges();
  if (ui.state) { ui.state.textContent = n ? `変更 ${n} 項目（未保存）` : '✓ 保存済み'; ui.state.classList.toggle('dirty', n > 0); }
  if (ui.save) ui.save.disabled = ui.revert.disabled = n === 0;
  if (!n && ui.confirm) ui.confirm.innerHTML = '';
}

// 保存・戻すは、押したあとに1回確認してから実行する
function ask(text, okLabel, fn, cls = 'primary') {
  ui.confirm.innerHTML = '';
  ui.confirm.append(el('div', { class: 'confirm', role: 'alert' }, el('span', {}, text),
    el('button', { class: 'btn small ' + cls, onclick: async () => { ui.confirm.innerHTML = ''; await fn(); } }, okLabel),
    el('button', { class: 'btn small ghost', onclick: () => { ui.confirm.innerHTML = ''; } }, 'やめる')));
}
const doSave = async () => { await api('/api/team', { method: 'PUT', body: body() }); await load(viewEl); toast('保存した'); };
const doRevert = () => { team = clone(saved); draw(viewEl); toast('保存済みの状態に戻した'); };

// 表示用の日本語名（持ち物・技）を付ける。技は4枠の位置に合わせる
async function labelize(m) {
  m.moves = pad4(m.moves);
  m._item_ja = await jaOf('items', m.item);
  m._moves_ja = await Promise.all(m.moves.map(x => jaOf('moves', x)));
}

async function fetchTeam() {
  const t = await api('/api/team');
  for (const m of t.members) await labelize(m);
  while (t.members.length < 6) t.members.push({ species: null, sp: {}, moves: pad4([]), _moves_ja: ['', '', '', ''] });
  team = t; saved = clone(t);
}
async function load(view) {
  viewEl = view;
  teams = await api('/api/teams');
  await fetchTeam();
  draw(view);
}

// 評価画面から使う: 編集中（未保存を含む）のパーティと、そこへの反映
export const unsavedFor = (id) => team && saved && team.id === id ? countChanges() : 0;
// 開いているパーティの編集中の内容に能力ポイントを入れる（別のパーティなら false）
export async function applySp(id, index, sp) {
  if (!team) await fetchTeam();
  if (team.id !== id) return false;
  const m = team.members[index];
  m.sp = { ...sp };
  Object.assign(m, await api('/api/member/stats', { method: 'POST', body: { member: strip(m) } }));
  return true;
}

function draw(view) {
  view.innerHTML = '';
  view.append(lead('1', 'パーティ'));
  view.append(teamBar(view), importCard(view));
  const cards = el('div', { class: 'team-cards' });
  cardEls = team.members.map((m, i) => { const c = memberCard(m, i); cards.append(c); return c; });
  view.append(cards);
  paint();
}

function teamBar(view) {
  const sel = el('select', { 'aria-label': 'パーティを選ぶ', onchange: async () => {
    if (!guard()) { sel.value = saved.id; return; }
    await api(`/api/teams/active/${sel.value}`, { method: 'PUT' }); await load(view); toast('パーティを切り替えた'); } },
    ...teams.map(t => el('option', { value: t.id, selected: t.id === team.id }, `${t.name || '名前なし'}（${t.members.join('・') || '空'}）`)));
  const name = el('input', { value: team.name || '', placeholder: 'パーティ名', 'aria-label': 'パーティ名', oninput: () => { team.name = name.value; paint(); } });
  const arch = el('select', { 'aria-label': '構築の型', onchange: () => { team.archetype = arch.value; paint(); } },
    ...(team.archetypes || ['スタンダード']).map(a => el('option', { value: a, selected: a === team.archetype }, a)));
  const act = (label, fn, cls = '') => el('button', { class: 'btn small ' + cls, onclick: async () => { if (!guard()) return; await fn(); await load(view); } }, label);
  const save = el('button', { class: 'btn small primary', onclick: () => ask(`変更した ${countChanges()} 項目を保存します。`, '保存する', doSave) }, '保存');
  const revert = el('button', { class: 'btn small', onclick: () => ask(`変更した ${countChanges()} 項目を、保存済みの内容に戻します。入力した内容は失われます。`, '戻す', doRevert, 'alt') }, '保存済みに戻す');
  const state = el('span', { class: 'save-state' }, '✓ 保存済み');
  const confirmSlot = el('div', { class: 'confirm-slot' });
  Object.assign(ui, { name, arch, save, revert, state, confirm: confirmSlot });
  return el('div', { class: 'card teambar' },
    el('div', { class: 'row' }, el('div', { class: 'grow' }, el('label', { class: 'f' }, 'パーティを選ぶ', sel)),
      act('＋ 新規', async () => { await api('/api/teams', { method: 'POST', body: { name: '' } }); toast('新しいパーティを作った'); }),
      el('button', { class: 'btn small alt', onclick: () => { const c = $('#import-card'); c.hidden = !c.hidden; } }, '画像から取り込む'),
      act('複製', async () => { await api('/api/teams', { method: 'POST', body: { copy_from: team.id } }); toast('複製した'); }),
      act('削除', async () => { if (!confirm(`「${saved.name}」を削除しますか？`)) throw new Error('cancel'); await api(`/api/teams/${team.id}`, { method: 'DELETE' }); toast('削除した'); }, 'ghost')),
    el('div', { class: 'row', style: 'margin-top:10px' },
      el('div', { class: 'grow' }, el('label', { class: 'f' }, 'パーティ名', name)),
      el('div', { class: 'grow' }, el('label', { class: 'f' }, ['構築の型', help('パーティの戦い方。対面=読み合いで押す／サイクル=交代しながら有利を取る／展開=積み・設置から勝つ／受けループ=耐久で崩す')], arch)),
      el('div', { class: 'save-row' }, state, save, revert, el('button', { class: 'btn small alt', title: '保存済みの内容を評価する', onclick: () => evaluateTeam(team.id) }, 'このパーティを評価'))),
    confirmSlot);
}


function memberCard(m, idx) {
  m.sp = m.sp || {}; m.moves = pad4(m.moves); m._moves_ja = m._moves_ja || ['', '', '', ''];
  const card = el('div', { class: 'card member' });
  const fields = card.fields = {};
  const typeBox = el('span'), stats = el('div', { class: 'stats-line' }), errs = el('div', { class: 'err' });
  const refresh = () => {
    stats.textContent = m._stats ? '実数値 ' + STATS.map(k => `${STAT_JA[k]}${m._stats[k]}`).join(' ') : '';
    errs.textContent = m._errors ? m._errors.join(' / ') : '';
  };
  // 実数値は保存せずにサーバで計算する
  const refreshStats = debounce(async () => {
    if (!m.species) { m._stats = null; m._errors = []; refresh(); return; }
    try { Object.assign(m, await api('/api/member/stats', { method: 'POST', body: { member: strip(m) } })); refresh(); } catch (e) { /* 次の編集で再計算 */ }
  }, 250);
  const touched = () => { refreshStats(); paint(); };
  const updTypes = async () => {
    typeBox.innerHTML = '';
    if (!m.species) return;
    const d = await dexInfo(m.species), { ja } = (await loadTypes()).types.reduce((a, t) => (a.ja[t.id] = t.ja, a), { ja: {} });
    const mega = d.megas.find(x => x.item === m.item);
    let types = d.types;
    if (mega) types = (await dexInfo(mega.id)).types;
    typeBox.append(...types.map(t => typeChip(t, ja[t])), mega ? el('span', { class: 'chip' }, `メガ→${mega.ja}`) : '');
  };
  const abilitySel = el('select', { 'aria-label': '特性', onchange: () => { m.ability = abilitySel.value || null; touched(); } });
  const fillAbilities = async () => {
    abilitySel.innerHTML = '';
    if (!m.species) return;
    const d = await dexInfo(m.species);
    abilitySel.append(el('option', { value: '' }, '特性を選ぶ'));
    d.abilities.forEach(a => abilitySel.append(el('option', { value: a.en, selected: a.en === m.ability }, a.ja)));
  };
  const item = picker({ kind: 'items', value: m.item, label: m._item_ja || '', placeholder: '持ち物', onPick: (it) => { m.item = it ? it.en : null; m._item_ja = it ? it.ja : ''; updTypes(); touched(); } });
  const megaBox = el('div');
  const renderMega = async () => {
    megaBox.innerHTML = '';
    if (!m.species) { item.input.disabled = false; return; }
    const d = await dexInfo(m.species);
    m._megaItems = d.megas.map(x => x.item);
    item.input.disabled = m._megaItems.includes(m.item);
    if (!d.megas.length) return;
    const cur = d.megas.find(x => x.item === m.item) || null;
    const apply = (mg) => {
      if (mg) { m.item = mg.item; m._item_ja = mg.item_ja; item.setValue(mg.item, mg.item_ja); item.input.disabled = true; }
      else { if (m._megaItems.includes(m.item)) { m.item = null; m._item_ja = ''; item.setValue('', ''); } item.input.disabled = false; }
      updTypes(); touched();
    };
    if (d.megas.length === 1) {
      const cb = el('input', { type: 'checkbox', checked: !!cur, onchange: () => apply(cb.checked ? d.megas[0] : null) });
      megaBox.append(el('label', { class: 'check' }, cb, `メガシンカ枠（${d.megas[0].ja}）`, help('このポケモンをメガシンカさせる。持ち物はメガストーン固定。メガシンカは1試合に1体だけ')));
    } else {
      const s = el('select', { onchange: () => apply(d.megas.find(x => x.id === s.value) || null) }, el('option', { value: '' }, 'メガシンカしない'),
        ...d.megas.map(x => el('option', { value: x.id, selected: cur && cur.id === x.id }, x.ja)));
      megaBox.append(el('label', { class: 'f' }, 'メガシンカ枠', s));
    }
  };
  const sp = picker({ kind: 'pokemon', value: m.species, label: m._ja || '', placeholder: `${idx + 1}体目のポケモン名`,
    onPick: async (it) => {
      const prev = m.species;
      m.species = it ? it.id : null; m._ja = it ? it.ja : '';
      if (prev !== m.species) { m.ability = null; if (m._megaItems && m._megaItems.includes(m.item)) { m.item = null; m._item_ja = ''; item.setValue('', ''); } }
      await fillAbilities(); await renderMega(); await updTypes(); touched();
    } });
  const moves = el('div', { class: 'moves' });
  for (let i = 0; i < 4; i++) {
    fields['move' + i] = picker({ kind: 'moves', value: m.moves[i], label: m._moves_ja[i] || '', placeholder: `技${i + 1}`, species: () => m.species,
      onPick: (it) => { m.moves[i] = it ? it.id : null; m._moves_ja[i] = it ? it.ja : ''; touched(); } });
    moves.append(fields['move' + i]);
  }
  const fill = el('button', { class: 'btn small alt', title: '入力済みの項目は変えず、空いている項目をよく使われる型で埋める', onclick: async () => {
    if (!m.species) { toast('先にポケモンを入力してね'); return; }
    const r = await api('/api/autofill', { method: 'POST', body: { member: strip(m) } });
    toast(r.message);
    if (!r.filled.length) return;
    Object.assign(m, r.member);
    await labelize(m);
    draw(viewEl);
  } }, 'おまかせ入力');
  const nature = el('select', { 'aria-label': '性格', onchange: () => { m.nature = nature.value || null; touched(); } }, el('option', { value: '' }, '性格を選ぶ'),
    ...S.meta.natures.map(n => el('option', { value: n.id, selected: n.id === m.nature }, `${n.ja}（${n.label}）`)));
  const spw = spGrid(m.sp, touched);
  Object.assign(fields, { species: sp, nature, ability: abilitySel, item });
  for (const k of STATS) fields['sp.' + k] = spw.cells[k];

  card.append(
    el('div', { class: 'member-head' }, el('span', { class: 'idx' }, idx + 1), el('div', { class: 'grow' }, sp), fill),
    el('div', { class: 'member-types' }, typeBox), megaBox,
    el('div', { class: 'row' }, el('div', { class: 'grow' }, el('label', { class: 'f' }, ['性格', help('上がる能力と下がる能力が決まる。（）内は 上がる↑／下がる↓')], nature)),
      el('div', { class: 'grow' }, el('label', { class: 'f' }, '特性', abilitySel))),
    el('label', { class: 'f', style: 'margin-top:8px' }, '持ち物', item),
    spw, stats, errs,
    el('div', { class: 'sp-head' }, '技'), moves);
  refresh(); fillAbilities(); renderMega(); updTypes();
  return card;
}

export default {
  key: 'team', label: 'パーティ', badge: '1',
  async render(view) {
    await loadMeta();
    // 未保存の変更があるあいだは、他の画面から戻ってきても編集中の内容を残す
    if (team && saved && countChanges() > 0) { viewEl = view; teams = await api('/api/teams'); draw(view); } else await load(view);
  },
};


// ---- 画像（ゲームの「パーティ確認」画面のスクショ）から取り込む ----
const readFile = (f) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(f); });
// サービス版は送る前にJPEG（品質0.9）にする（1回の送信は4.5MBまで。読み取りの結果は変わらないことを実機スクショで確認済み）
const toUpload = async (f) => {
  if (!isService()) return readFile(f);
  const bmp = await createImageBitmap(f);
  const s = Math.min(1, 3000 / Math.max(bmp.width, bmp.height));
  const c = el('canvas', { width: Math.round(bmp.width * s), height: Math.round(bmp.height * s) });
  c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
  return c.toDataURL('image/jpeg', 0.9);
};

function importCard(view) {
  const card = el('div', { class: 'card import', id: 'import-card', hidden: true });
  const body = el('div'), result = el('div');
  let files = [];
  const input = el('input', { type: 'file', accept: 'image/*', multiple: true, hidden: true, onchange: () => add([...input.files]) });
  const drop = el('div', { class: 'dropzone', tabindex: '0', onclick: () => input.click() },
    el('b', {}, 'スクショをここにドロップ / クリックして選択 / 貼り付け'), el('div', { class: 'muted' }, 'ゲームの「パーティ確認」画面の「能力」タブと「ステータス」タブの2枚（片方だけでも読める）'));
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('over'); add([...e.dataTransfer.files]); });
  document.addEventListener('paste', (e) => { if (!card.hidden && document.body.contains(card)) add([...(e.clipboardData ? e.clipboardData.files : [])]); });

  const add = async (fs) => {
    fs = fs.filter(f => f.type.startsWith('image/'));
    if (!fs.length) return;
    files = [...files, ...fs].slice(-2);
    await analyze();
  };
  const analyze = async () => {
    result.innerHTML = '';
    body.innerHTML = '';
    body.append(el('div', { class: 'thumbs' }, ...files.map(f => el('img', { src: URL.createObjectURL(f), alt: f.name }))), el('div', { class: 'muted' }, '読み取り中…'));
    try {
      const r = await api('/api/team/import-image', { method: 'POST', body: { images: await Promise.all(files.map(toUpload)) } });
      body.lastChild.remove();
      showResult(r);
    } catch (e) {
      body.lastChild.remove();
      let msg = e.message; try { msg = JSON.parse(msg).detail || msg; } catch (_) { /* そのまま */ }
      result.append(el('div', { class: 'err' }, `読み取れなかった: ${msg}`));
    }
  };
  const showResult = (r) => {
    result.innerHTML = '';
    const list = el('div', { class: 'imp-list' });
    r.members.forEach((m, i) => {
      const flags = m.flags || [];
      list.append(el('div', { class: 'imp-mon' + (flags.length ? ' warn' : '') },
        el('div', { class: 'imp-head' }, el('span', { class: 'idx' }, i + 1), el('b', {}, m.species_ja || '読み取れず')),
        m.nature_ja ? el('div', { class: 'muted' }, `${m.nature_ja}　${m.sp ? STATS.map(k => `${STAT_JA[k]}${m.sp[k]}`).join(' ') : ''}`) : '',
        m.ability_ja || m.item_ja ? el('div', { class: 'muted' }, [m.ability_ja, m.item_ja && `@${m.item_ja}`].filter(Boolean).join('　')) : '',
        (m.moves_ja || []).length ? el('div', { class: 'muted' }, m.moves_ja.join(' / ')) : '',
        ...flags.map(f => el('div', { class: 'imp-flag' }, f))));
    });
    const members = () => r.members.filter(m => m.species).map(m => {
      const o = { species: m.species, sp: m.sp || {}, moves: m.moves || [] };
      for (const k of ['nature', 'ability', 'item']) if (m[k]) o[k] = m[k];
      return o;
    });
    const doImport = async (asNew) => {
      const ms = members();
      if (!ms.length) { toast('取り込める内容がない'); return; }
      if (!guard()) return;
      let id = team.id, name = team.name, archetype = team.archetype;
      if (asNew) { const t = await api('/api/teams', { method: 'POST', body: { name: '取り込んだパーティ' } }); id = t.id; name = t.name; archetype = t.archetype; }
      else if (team.members.some(m => m.species) && !confirm('現在のパーティの内容を上書きします。よろしいですか？')) return;
      // 6体の内容を丸ごと入れ替える（読み取れなかった項目は空のまま。別のポケモンの内容が混ざらない）
      await api('/api/team', { method: 'PUT', body: { id, name, archetype, members: ms } });
      await load($('#view'));
      toast(asNew ? '新しいパーティとして取り込んだ' : '取り込んだ');
    };
    result.append(...(r.warnings || []).map(w => el('div', { class: 'imp-flag' }, w)), list,
      el('div', { class: 'row', style: 'margin-top:12px' },
        el('button', { class: 'btn primary', onclick: () => doImport(true) }, '新しいパーティとして取り込む'),
        el('button', { class: 'btn', onclick: () => doImport(false) }, '現在のパーティに上書き'),
        el('button', { class: 'btn ghost', onclick: () => { files = []; body.innerHTML = ''; result.innerHTML = ''; } }, 'やり直す')),
      el('div', { class: 'muted', style: 'margin-top:6px;font-size:13px' }, '黄色の注意が出た項目は、取り込んだあとにパーティ画面で確認してください。'));
  };
  card.append(el('h2', {}, '画像から取り込む'), input, drop, body, result);
  return card;
}
