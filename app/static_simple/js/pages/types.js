import { el, lead, typeChip, TYPE_COLOR, typeFg, help } from '../ui.js';
import { loadTypes } from '../store.js';

let focus = [];

export default {
  key: 'types', label: 'タイプ相性', badge: '相', side: true,
  async render(view) {
    const { types, chart, pokemon } = await loadTypes();
    const ja = Object.fromEntries(types.map(t => [t.id, t.ja]));
    const chips = (ts) => ts.map(t => typeChip(t, ja[t]));
    const mult = (m) => el('span', { class: 'tymult m' + String(m).replace('.', '_') }, `×${m}`);
    const eff = (atk, defs) => defs.reduce((a, d) => a * chart[atk][d], 1);

    // 左=有利なタイプ、右=不利なタイプ
    const favGrid = (fav, unfav) => el('div', { class: 'fav-grid' },
      el('div', { class: 'fav' }, el('h3', {}, '有利なタイプ'), fav),
      el('div', { class: 'unfav' }, el('h3', {}, '不利なタイプ'), unfav));
    const rows = (pairs, order) => {
      const box = el('div');
      for (const m of order) {
        const ts = pairs.filter(p => p[1] === m).map(p => p[0]);
        if (ts.length) box.append(el('div', { class: 'tygroup' }, mult(m), ...chips(ts)));
      }
      if (!box.children.length) box.append(el('span', { class: 'muted' }, 'なし'));
      return box;
    };

    const draw = () => {
      view.innerHTML = '';
      view.append(lead('相', 'タイプ相性'));
      const toggle = (t) => { focus = focus.includes(t) ? focus.filter(x => x !== t) : (focus.length >= 2 ? [focus[1], t] : [...focus, t]); draw(); };
      view.append(el('div', { class: 'card' }, el('h2', {}, 'タイプを選ぶ ', help('最大2つ。2つ選ぶと、そのタイプを併せ持つポケモンとして調べる')),
        el('div', { class: 'tpick-grid' }, ...types.map(t => {
          const on = focus.includes(t.id);
          return el('button', { class: 'tpick' + (on ? ' on' : focus.length ? ' off' : ''), 'aria-pressed': on ? 'true' : 'false',
            style: `--tc:${TYPE_COLOR[t.id]};--tf:${typeFg(t.id)}`, onclick: () => toggle(t.id) }, on ? '✓ ' : '', t.ja);
        })),
        focus.length ? el('div', { style: 'margin-top:10px' }, el('button', { class: 'btn small ghost', onclick: () => { focus = []; draw(); } }, 'クリア')) : ''));

      if (!focus.length) {
        view.append(el('div', { class: 'card', style: 'margin-top:18px' }, el('div', { class: 'empty' }, 'タイプを選ぶと、ここに相性が出る')));
      } else {
        const F = focus;
        // 攻撃するとき
        const atk = el('div');
        for (const a of F) {
          const pairs = types.map(t => [t.id, chart[a][t.id]]);
          atk.append(el('div', { class: 'tysub' }, typeChip(a, ja[a]), ' の技'), favGrid(rows(pairs, [2]), rows(pairs, [0.5, 0])));
        }
        if (F.length === 2) {
          const pairs = types.map(t => [t.id, Math.max(chart[F[0]][t.id], chart[F[1]][t.id])]);
          atk.append(el('div', { class: 'tysub' }, '一致技2つの良い方'), favGrid(rows(pairs, [2]), rows(pairs, [0.5, 0])));
        }
        view.append(el('div', { class: 'card', style: 'margin-top:18px' }, el('h2', {}, '攻撃するとき'), atk));
        // 防御するとき
        const defPairs = types.map(t => [t.id, eff(t.id, F)]);
        view.append(el('div', { class: 'card', style: 'margin-top:18px' }, el('h2', {}, '攻撃を受けるとき'),
          favGrid(rows(defPairs, [0.25, 0.5, 0]), rows(defPairs, [4, 2]))));
        // 弱点メタ
        const weak = defPairs.filter(p => p[1] >= 2).map(p => p[0]);
        const meta = el('div');
        if (!weak.length) meta.append(el('span', { class: 'muted' }, '抜群を取られるタイプが無い'));
        else {
          const rs = types.map(t => ({ t: t.id, hits: weak.filter(w => chart[t.id][w] >= 2) })).filter(r => r.hits.length).sort((a, b) => b.hits.length - a.hits.length);
          meta.append(el('div', { class: 'muted', style: 'margin-bottom:6px' }, '弱点を突いてくるタイプ: ', ...chips(weak)));
          for (const r of rs) meta.append(el('div', { class: 'tygroup' }, typeChip(r.t, ja[r.t]), el('span', { class: 'muted' }, `→ ${r.hits.length}/${weak.length} に抜群`), ...chips(r.hits)));
        }
        view.append(el('div', { class: 'card', style: 'margin-top:18px' }, el('h2', {}, '弱点メタ ', help('このタイプの弱点を突いてくる相手に対して、こちらから抜群を取れるタイプ')),
          el('div', { class: 'fav-grid single' }, el('div', { class: 'fav' }, el('h3', {}, '有利なタイプ'), meta))));
        // 該当ポケモン
        const match = pokemon.filter(p => p.searchable !== false && p.types.length === F.length && F.every(t => p.types.includes(t)));
        const mons = el('div');
        mons.append(el('div', { class: 'muted' }, `${match.length}体`), el('div', {}, ...match.filter(p => !p.isMega).map(p => el('span', { class: 'chip' }, p.ja))));
        const megas = match.filter(p => p.isMega);
        if (megas.length) mons.append(el('div', { class: 'muted', style: 'margin-top:6px' }, 'メガシンカ後'), el('div', {}, ...megas.map(p => el('span', { class: 'chip' }, p.ja))));
        view.append(el('div', { class: 'card', style: 'margin-top:18px' }, el('h2', {}, '該当ポケモン'), mons));
      }

      // 相性表（横スクロールなし。狭いときは行名も1文字表記）
      const tbl = el('table', { class: 'tychart' });
      tbl.append(el('tr', {}, el('th', { class: 'corner' }, ''), ...types.map(t => el('th', { class: focus.includes(t.id) ? 'focus' : '', onclick: () => toggle(t.id) }, typeChip(t.id, t.ja, true)))));
      for (const a of types) {
        tbl.append(el('tr', {}, el('th', { class: 'rowh' + (focus.includes(a.id) ? ' focus' : ''), onclick: () => toggle(a.id) },
          el('span', { class: 'full' }, typeChip(a.id, a.ja)), el('span', { class: 'short' }, typeChip(a.id, a.ja, true))),
        ...types.map(d => { const v = chart[a.id][d.id]; return el('td', { class: 'm' + String(v).replace('.', '_') + (focus.includes(a.id) || focus.includes(d.id) ? ' focus' : '') }, v === 1 ? '' : v === 2 ? '◎' : v === 0.5 ? '△' : '×'); })));
      }
      view.append(el('div', { class: 'card', style: 'margin-top:18px' }, el('h2', {}, 'タイプ相性表 ', help('行が攻撃側、列が防御側。◎=抜群 △=いまひとつ ×=無効')), tbl));
    };
    draw();
  },
};
