import { $, el, lead, typeChip, TYPE_COLOR, typeFg, help } from '../ui.js';
import { loadTypes } from '../store.js';

let focus = [];

export default {
  key: 'types', label: 'タイプ相性', badge: '📖', side: true,
  async render(view) {
    const { types, chart, pokemon } = await loadTypes();
    const ja = Object.fromEntries(types.map(t => [t.id, t.ja]));
    const draw = () => {
      view.innerHTML = '';
      view.append(lead('📖', 'タイプ相性', 'タイプを選ぶ（最大2つ）と、攻撃・防御の相性が出る。'));
      const toggle = (t) => { focus = focus.includes(t) ? focus.filter(x => x !== t) : (focus.length >= 2 ? [focus[1], t] : [...focus, t]); draw(); };
      const pick = el('div', { class: 'tpick-grid' }, ...types.map(t => {
        const on = focus.includes(t.id);
        return el('button', { class: 'tpick' + (on ? ' on' : ''), style: `background:${on ? TYPE_COLOR[t.id] : ''};color:${on ? typeFg(t.id) : ''}`, onclick: () => toggle(t.id) }, t.ja);
      }));
      view.append(el('div', { class: 'card' }, el('h2', {}, 'タイプを選ぶ ', help('2つ選ぶと、そのタイプを併せ持つポケモンとして調べる')),
        pick, focus.length ? el('div', { style: 'margin-top:10px' }, el('button', { class: 'btn small ghost', onclick: () => { focus = []; draw(); } }, 'クリア')) : ''));

      const eff = (atk, defs) => defs.reduce((a, d) => a * chart[atk][d], 1);
      const cls = (m) => 'm' + String(m).replace('.', '_');
      const group = (pairs, order) => {
        const box = el('div');
        for (const [mult, label] of order) {
          const ts = pairs.filter(p => p[1] === mult).map(p => p[0]);
          if (ts.length) box.append(el('div', { class: 'tygroup' }, el('span', { class: 'tymult ' + cls(mult) }, label), ...ts.map(t => typeChip(t, ja[t]))));
        }
        return box;
      };
      if (focus.length) {
        const F = focus;
        const atk = el('div'), def = el('div'), ctr = el('div'), mons = el('div');
        const AORD = [[2, '×2'], [0.5, '×0.5'], [0, '×0']];
        for (const a of F) atk.append(el('div', { class: 'tysub' }, typeChip(a, ja[a]), ' の技で攻撃'), group(types.map(t => [t.id, chart[a][t.id]]), AORD));
        if (F.length === 2) atk.append(el('div', { class: 'tysub' }, '一致技2つの良い方'), group(types.map(t => [t.id, Math.max(chart[F[0]][t.id], chart[F[1]][t.id])]), AORD));
        const defPairs = types.map(t => [t.id, eff(t.id, F)]);
        def.append(group(defPairs, [[4, '×4'], [2, '×2'], [0.5, '×0.5'], [0.25, '×0.25'], [0, '×0']]));
        const weak = defPairs.filter(p => p[1] >= 2).map(p => p[0]);
        if (!weak.length) ctr.append(el('p', { class: 'muted' }, '抜群を取られるタイプが無い'));
        else {
          ctr.append(el('div', { class: 'tygroup' }, el('span', { class: 'muted' }, '抜群を取ってくる: '), ...weak.map(t => typeChip(t, ja[t]))));
          const rows = types.map(t => ({ t: t.id, hits: weak.filter(w => chart[t.id][w] >= 2) })).filter(r => r.hits.length).sort((a, b) => b.hits.length - a.hits.length);
          const tb = el('table', { class: 'plain' }, el('tr', {}, el('th', {}, '返しの技'), el('th', { class: 'num' }, `抜群（/${weak.length}）`), el('th', {}, '抜群を取れる相手')));
          for (const r of rows) tb.append(el('tr', {}, el('td', {}, typeChip(r.t, ja[r.t])), el('td', { class: 'num' }, r.hits.length), el('td', {}, ...r.hits.map(w => typeChip(w, ja[w])))));
          ctr.append(tb);
        }
        const match = pokemon.filter(p => p.searchable !== false && p.types.length === F.length && F.every(t => p.types.includes(t)));
        mons.append(el('div', {}, `${match.length}体`), el('div', {}, ...match.filter(p => !p.isMega).map(p => el('span', { class: 'chip' }, p.ja))));
        const megas = match.filter(p => p.isMega);
        if (megas.length) mons.append(el('div', { class: 'muted' }, 'メガシンカ後'), el('div', {}, ...megas.map(p => el('span', { class: 'chip' }, p.ja))));
        view.append(el('div', { class: 'grid2', style: 'margin-top:18px' },
          el('div', { class: 'card' }, el('h2', {}, '⚔️ 攻撃するとき'), atk),
          el('div', { class: 'card' }, el('h2', {}, '🛡️ 攻撃を受けるとき'), def)),
        el('div', { class: 'grid2', style: 'margin-top:18px' },
          el('div', { class: 'card' }, el('h2', {}, '弱点メタ ', help('このタイプの弱点を突いてくる相手に、こちらからどのタイプの技が有効か')), ctr),
          el('div', { class: 'card' }, el('h2', {}, '該当ポケモン'), mons)));
      } else {
        view.append(el('div', { class: 'card', style: 'margin-top:18px' }, el('div', { class: 'empty' }, el('div', { class: 'big' }, '👆'), 'タイプを選ぶと、ここに相性が出る')));
      }
      const tbl = el('table', { class: 'tychart' });
      tbl.append(el('tr', {}, el('th', {}, '攻＼防'), ...types.map(t => el('th', { class: focus.includes(t.id) ? 'focus' : '', onclick: () => toggle(t.id) }, typeChip(t.id, t.ja, true)))));
      for (const a of types) {
        const tr = el('tr', {}, el('th', { class: focus.includes(a.id) ? 'focus' : '', onclick: () => toggle(a.id) }, typeChip(a.id, a.ja)));
        for (const d of types) {
          const v = chart[a.id][d.id];
          tr.append(el('td', { class: cls(v) + (focus.includes(a.id) || focus.includes(d.id) ? ' focus' : '') }, v === 1 ? '' : v === 2 ? '◎' : v === 0.5 ? '△' : '×'));
        }
        tbl.append(tr);
      }
      view.append(el('div', { class: 'card', style: 'margin-top:18px' }, el('h2', {}, 'タイプ相性表 ', help('行が攻撃側、列が防御側。◎=抜群 △=いまひとつ ×=無効')), el('div', { class: 'scroll-x' }, tbl)));
    };
    draw();
  },
};
