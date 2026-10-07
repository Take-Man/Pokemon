import { api, el, typeChip } from './ui.js';

export const S = { meta: null, types: null, dex: {} };

export async function loadMeta() { return S.meta || (S.meta = await api('/api/meta')); }
export async function loadTypes() { return S.types || (S.types = await api('/api/types')); }
export async function dexInfo(id) { return S.dex[id] || (S.dex[id] = await api(`/api/pokemon/${encodeURIComponent(id)}`)); }

// ポケモン名（日本語）→ タイプ。メガ後の姿も含む
let _byJa = null;
export function typesOfJa(ja) {
  if (!S.types) return [];
  if (!_byJa) { _byJa = {}; for (const p of S.types.pokemon) if (!(p.ja in _byJa) || !p.isMega) _byJa[p.ja] = p.types; }
  return _byJa[String(ja).replace(/（.*?）/g, '').trim()] || [];
}
// 名前＋1文字のタイプチップ（stacked=true ならチップの次の行に名前）
export function monLabel(ja, stacked = false) {
  const chips = el('span', { class: 'tchips' }, ...typesOfJa(ja).map(t => typeChip(t, t, true)));
  return stacked ? el('span', { class: 'mon stacked' }, chips, el('span', { class: 'mon-name' }, ja)) : el('span', { class: 'mon' }, ja, chips);
}

// ---- 弱点 ----
// 特性で受けるタイプの倍率が変わるもの（特性が決まっているときだけ反映する）
const ABIL_TYPE_MOD = {
  levitate: { Ground: 0 }, eartheater: { Ground: 0 }, flashfire: { Fire: 0 }, wellbakedbody: { Fire: 0 },
  waterabsorb: { Water: 0 }, stormdrain: { Water: 0 }, dryskin: { Water: 0, Fire: 1.25 }, voltabsorb: { Electric: 0 },
  lightningrod: { Electric: 0 }, motordrive: { Electric: 0 }, sapsipper: { Grass: 0 }, thickfat: { Fire: 0.5, Ice: 0.5 },
  heatproof: { Fire: 0.5 }, waterbubble: { Fire: 0.5 }, purifyingsalt: { Ghost: 0.5 }, fluffy: { Fire: 2 },
};
const toId = (x) => String(x || '').toLowerCase().replace(/[^a-z0-9]/g, '');

// 受けたときの弱点（×4 と ×2 のタイプ）。メガストーンを持っていればメガ後の姿（特性は1つに決まる）で見る
export async function weaknessOf(species, item, ability) {
  const d = await dexInfo(species);
  const mega = d.megas.find(x => x.item === item);
  const p = mega ? S.types.pokemon.find(q => q.id === mega.id) : S.types.pokemon.find(q => q.id === species);
  if (!p) return { x4: [], x2: [], types: [], mega: null };
  let ab = ability;
  if (mega) ab = p.abilities.length === 1 ? p.abilities[0] : null;
  const mod = ABIL_TYPE_MOD[toId(ab)] || {};
  const x4 = [], x2 = [];
  for (const t of S.types.types) {
    const m = p.types.reduce((v, def) => v * S.types.chart[t.id][def], 1) * (mod[t.id] ?? 1);
    if (m >= 4) x4.push(t.id); else if (m >= 2) x2.push(t.id);
  }
  return { x4, x2, types: p.types, mega: mega || null, byAbility: Object.keys(mod).length > 0 };
}
