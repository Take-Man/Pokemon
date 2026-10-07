import { el, help } from './ui.js';

export const STATS = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'];
export const STAT_JA = { hp: 'H', atk: 'A', def: 'B', spa: 'C', spd: 'D', spe: 'S' };
export const STAT_TIP = { hp: 'HP（体力）', atk: 'こうげき', def: 'ぼうぎょ', spa: 'とくこう', spd: 'とくぼう', spe: 'すばやさ' };

export function spGrid(sp, onChange) {
  const total = el('div', { class: 'sp-total' });
  const sum = () => STATS.reduce((a, k) => a + (sp[k] || 0), 0);
  const upd = () => { const t = sum(); total.textContent = `合計 ${t} / 66（残り ${66 - t}）`; total.classList.toggle('over', t > 66); };
  const inputs = {};
  const set = (k, v) => { sp[k] = Math.max(0, Math.min(32, v)); inputs[k].value = sp[k]; upd(); onChange(); };
  const g = el('div', { class: 'sp-grid' });
  const cells = {};
  for (const k of STATS) {
    const i = el('input', { type: 'number', min: 0, max: 32, value: sp[k] || 0, 'aria-label': STAT_TIP[k] });
    inputs[k] = i;
    i.addEventListener('input', () => set(k, parseInt(i.value || '0', 10) || 0));
    g.append(cells[k] = el('div', { class: 'sp-cell' }, el('b', { title: STAT_TIP[k] }, STAT_JA[k]), i,
      el('div', { class: 'sp-btns' },
        el('button', { class: 'mini', title: '0にする', onclick: () => set(k, 0) }, '0'),
        el('button', { class: 'mini', title: '振れる上限（32か残りポイント）', onclick: () => set(k, Math.min(32, 66 - (sum() - (sp[k] || 0)))) }, 'Max'))));
  }
  upd();
  const w = el('div', {}, el('div', { class: 'sp-head' }, '能力ポイント ', help('努力値にあたる、各能力の強化ポイント。合計66・1つ32まで。H=HP A=こうげき B=ぼうぎょ C=とくこう D=とくぼう S=すばやさ')), g, total);
  w.cells = cells;  // 項目ごとの印付け用
  return w;
}
