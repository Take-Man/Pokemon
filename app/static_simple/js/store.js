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
