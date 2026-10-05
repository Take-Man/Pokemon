import { $, el, api, lead, toast, picker, help, typeChip, debounce } from '../ui.js';
import { S, dexInfo, loadMeta, loadTypes } from '../store.js';

import { STATS, STAT_JA, spGrid } from '../parts.js';

let team = null, teams = [], dirty = false, saveTimer = null;

const strip = (m) => Object.fromEntries(Object.entries(m).filter(([k]) => !k.startsWith('_')));
const body = () => ({ id: team.id, name: team.name, archetype: team.archetype, members: team.members.map(strip) });

async function saveNow() {
  clearTimeout(saveTimer);
  await api('/api/team', { method: 'PUT', body: body() });
  const t = await api('/api/team');
  t.members.forEach((m, i) => { if (team.members[i]) Object.assign(team.members[i], { _stats: m._stats, _errors: m._errors, _ja: m._ja }); });
  setDirty(false);
}
function setDirty(f) { dirty = f; const s = $('#save-state'); if (s) { s.textContent = f ? '保存中…' : '✓ 自動保存済み'; s.classList.toggle('dirty', f); } }
function save() { setDirty(true); clearTimeout(saveTimer); saveTimer = setTimeout(() => saveNow().catch(e => toast('保存に失敗: ' + e.message)), 500); }
window.addEventListener('beforeunload', () => {
  if (dirty && team) fetch('/api/team', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body()), keepalive: true });
});

const jaOf = async (kind, id) => {
  if (!id) return '';
  const r = await api(`/api/search?kind=${kind}&q=${encodeURIComponent(id)}&limit=1&include_mega=true`);
  return r[0] ? r[0].ja : id;
};

async function load(view) {
  team = await api('/api/team');
  teams = await api('/api/teams');
  for (const m of team.members) {
    m._item_ja = await jaOf('items', m.item);
    m._moves_ja = await Promise.all((m.moves || []).map(x => jaOf('moves', x)));
  }
  while (team.members.length < 6) team.members.push({ species: null, sp: {}, moves: [] });
  draw(view);
}

function draw(view) {
  view.innerHTML = '';
  view.append(lead('1', 'パーティ'));
  view.append(teamBar(view), importCard(view));
  const cards = el('div', { class: 'team-cards' });
  team.members.forEach((m, i) => cards.append(memberCard(m, i)));
  view.append(cards);
}

function teamBar(view) {
  const sel = el('select', { 'aria-label': 'パーティを選ぶ', onchange: async () => { if (dirty) await saveNow(); await api(`/api/teams/active/${sel.value}`, { method: 'PUT' }); await load(view); toast('パーティを切り替えた'); } },
    ...teams.map(t => el('option', { value: t.id, selected: t.id === team.id }, `${t.name || '名前なし'}（${t.members.join('・') || '空'}）`)));
  const name = el('input', { value: team.name || '', placeholder: 'パーティ名', 'aria-label': 'パーティ名', oninput: () => { team.name = name.value; save(); } });
  name.addEventListener('change', async () => { await saveNow(); teams = await api('/api/teams'); draw(view); });
  const arch = el('select', { 'aria-label': '構築の型', onchange: () => { team.archetype = arch.value; save(); } },
    ...(team.archetypes || ['スタンダード']).map(a => el('option', { value: a, selected: a === team.archetype }, a)));
  const act = (label, fn, cls = '') => el('button', { class: 'btn small ' + cls, onclick: async () => { if (dirty) await saveNow(); await fn(); await load(view); } }, label);
  return el('div', { class: 'card teambar' },
    el('div', { class: 'row' }, el('div', { class: 'grow' }, el('label', { class: 'f' }, 'パーティを選ぶ', sel)),
      act('＋ 新規', async () => { await api('/api/teams', { method: 'POST', body: { name: '' } }); toast('新しいパーティを作った'); }),
      el('button', { class: 'btn small alt', onclick: () => { const c = $('#import-card'); c.hidden = !c.hidden; } }, '画像から取り込む'),
      act('複製', async () => { await api('/api/teams', { method: 'POST', body: { copy_from: team.id } }); toast('複製した'); }),
      act('削除', async () => { if (!confirm(`「${team.name}」を削除しますか？`)) throw new Error('cancel'); await api(`/api/teams/${team.id}`, { method: 'DELETE' }); toast('削除した'); }, 'ghost')),
    el('div', { class: 'row', style: 'margin-top:10px' },
      el('div', { class: 'grow' }, el('label', { class: 'f' }, 'パーティ名', name)),
      el('div', { class: 'grow' }, el('label', { class: 'f' }, ['構築の型', help('パーティの戦い方。対面=読み合いで押す／サイクル=交代しながら有利を取る／展開=積み・設置から勝つ／受けループ=耐久で崩す')], arch)),
      el('span', { id: 'save-state', class: 'save-state' }, '✓ 自動保存済み')));
}


function memberCard(m, idx) {
  m.sp = m.sp || {}; m.moves = m.moves || [];
  const card = el('div', { class: 'card member' });
  const typeBox = el('span'), stats = el('div', { class: 'stats-line' }), errs = el('div', { class: 'err' });
  const refresh = (mm) => {
    stats.textContent = mm && mm._stats ? '実数値 ' + STATS.map(k => `${STAT_JA[k]}${mm._stats[k]}`).join(' ') : '';
    errs.textContent = mm && mm._errors ? mm._errors.join(' / ') : '';
  };
  const updTypes = async () => {
    typeBox.innerHTML = '';
    if (!m.species) return;
    const d = await dexInfo(m.species), { ja } = (await loadTypes()).types.reduce((a, t) => (a.ja[t.id] = t.ja, a), { ja: {} });
    const mega = d.megas.find(x => x.item === m.item);
    let types = d.types;
    if (mega) types = (await dexInfo(mega.id)).types;
    typeBox.append(...types.map(t => typeChip(t, ja[t])), mega ? el('span', { class: 'chip' }, `メガ→${mega.ja}`) : '');
  };
  const abilitySel = el('select', { 'aria-label': '特性', onchange: () => { m.ability = abilitySel.value || null; save(); } });
  const fillAbilities = async () => {
    abilitySel.innerHTML = '';
    if (!m.species) return;
    const d = await dexInfo(m.species);
    abilitySel.append(el('option', { value: '' }, '特性を選ぶ'));
    d.abilities.forEach(a => abilitySel.append(el('option', { value: a.en, selected: a.en === m.ability }, a.ja)));
  };
  const item = picker({ kind: 'items', value: m.item, label: m._item_ja || '', placeholder: '持ち物', onPick: (it) => { m.item = it ? it.en : null; updTypes(); save(); } });
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
      if (mg) { m.item = mg.item; item.setValue(mg.item, mg.item_ja); item.input.disabled = true; }
      else { if (m._megaItems.includes(m.item)) { m.item = null; item.setValue('', ''); } item.input.disabled = false; }
      updTypes(); save();
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
      m.species = it ? it.id : null;
      if (prev !== m.species) { m.ability = null; if (m._megaItems && m._megaItems.includes(m.item)) { m.item = null; item.setValue('', ''); } }
      await fillAbilities(); await renderMega(); await updTypes(); save();
    } });
  const moves = el('div', { class: 'moves' });
  for (let i = 0; i < 4; i++) {
    moves.append(picker({ kind: 'moves', value: m.moves[i], label: (m._moves_ja || [])[i] || '', placeholder: `技${i + 1}`, species: () => m.species,
      onPick: (it) => { m.moves[i] = it ? it.id : null; m.moves = m.moves.filter(Boolean); save(); } }));
  }
  const fill = el('button', { class: 'btn small alt', title: '入力済みの項目は変えず、空いている項目をよく使われる型で埋める', onclick: async () => {
    if (!m.species) { toast('先にポケモンを入力してね'); return; }
    await saveNow();
    const r = await api('/api/autofill', { method: 'POST', body: { member: strip(m) } });
    toast(r.message);
    if (!r.filled.length) return;
    Object.assign(m, r.member);
    await saveNow();
    await load($('#view'));
  } }, 'おまかせ入力');
  const nature = el('select', { 'aria-label': '性格', onchange: () => { m.nature = nature.value || null; save(); } }, el('option', { value: '' }, '性格を選ぶ'),
    ...S.meta.natures.map(n => el('option', { value: n.id, selected: n.id === m.nature }, `${n.ja}（${n.label}）`)));

  card.append(
    el('div', { class: 'member-head' }, el('span', { class: 'idx' }, idx + 1), el('div', { class: 'grow' }, sp), fill),
    el('div', { class: 'member-types' }, typeBox), megaBox,
    el('div', { class: 'row' }, el('div', { class: 'grow' }, el('label', { class: 'f' }, ['性格', help('上がる能力と下がる能力が決まる。（）内は 上がる↑／下がる↓')], nature)),
      el('div', { class: 'grow' }, el('label', { class: 'f' }, '特性', abilitySel))),
    el('label', { class: 'f', style: 'margin-top:8px' }, '持ち物', item),
    spGrid(m.sp, save), stats, errs,
    el('div', { class: 'sp-head' }, '技'), moves);
  refresh(m); fillAbilities(); renderMega(); updTypes();
  return card;
}

export default {
  key: 'team', label: 'パーティ', badge: '1',
  async render(view) { await loadMeta(); await load(view); },
};


// ---- 画像（ゲームの「パーティ確認」画面のスクショ）から取り込む ----
const readFile = (f) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(f); });

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
      const r = await api('/api/team/import-image', { method: 'POST', body: { images: await Promise.all(files.map(readFile)) } });
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
      if (dirty) await saveNow();
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
