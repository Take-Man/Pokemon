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
  view.append(lead('1', 'パーティ', '自分のポケモン6体を登録しよう。ポケモン名を入れて「おまかせ入力」を押すと、よく使われる型が自動で入る。'));
  view.append(teamBar(view));
  const cards = el('div', { class: 'team-cards' });
  team.members.forEach((m, i) => cards.append(memberCard(m, i)));
  view.append(cards);
  if (!team.members.some(m => m.species)) view.querySelector('.team-cards').before(el('div', { class: 'tip' }, '👇 まず1体目のポケモン名を入力（例: ガブリアス）'));
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
      if (it && prev !== m.species) toast('「おまかせ入力」で型を自動入力できる');
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
  } }, '✨ おまかせ入力');
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
