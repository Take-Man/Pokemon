import { $, el, api, lead, toast, help, typeChip, debounce } from '../ui.js';
import { S, dexInfo, loadTypes, monLabel, weaknessOf } from '../store.js';
import { STAT_JA } from '../parts.js';
import { workingTeam, applySp } from './team.js';

const ROLE_TIP = {
  ace: '積み技で一気に押し切る役', breaker: '高い火力で相手の受けを崩す役', faceoff: '1対1で勝ちにいく役', cushion: '攻撃を受けて流す役',
  wall_phys: '物理攻撃を受け止める役', wall_spec: '特殊攻撃を受け止める役', setter: '壁・ステルスロックなどで場を整える役',
  stopper: '先制技やスカーフで相手を止める役', pivot: '交代しながら有利を作る役', weather: '天候・フィールドを始動する役',
};
const ROLE_ORDER = ['ace', 'breaker', 'faceoff', 'cushion', 'wall_phys', 'wall_spec', 'setter', 'stopper', 'pivot', 'weather'];
const RANK_ROLE_JA = { ace: 'エース', breaker: '崩し', faceoff: '対面駒', cushion: 'クッション', wall_phys: '物理受け', wall_spec: '特殊受け', setter: '起点作り', stopper: 'ストッパー', pivot: 'サイクル要員', weather: '天候始動' };

let T = null, threats = null;

const page = {
  key: 'evaluate', label: 'パーティ評価', badge: '評', side: true,
  async render(view) {
    await loadTypes();
    T = await workingTeam();
    const filled = T.members.filter(m => m.species);
    view.append(lead('評', 'パーティ評価'));
    if (!filled.length) {
      view.append(el('div', { class: 'card' }, el('div', { class: 'empty' }, ['パーティが空。', el('a', { href: '#team' }, 'パーティ'), 'に登録すると評価が出る'])));
      return;
    }
    if (T.unsaved) view.append(el('div', { class: 'tip' }, `保存していない変更（${T.unsaved}項目）を含めて評価している。`));
    const d = await api('/api/diagnose', { method: 'POST', body: { archetype: T.archetype, members: T.members } });
    view.append(await rolesCard(d, filled), findingsCard(d), overlapCard(d), await tuneCard(view));
  },
};

export default page;

async function rolesCard(d, filled) {
  const counts = ROLE_ORDER.filter(k => (d.role_counts || {})[k]).map(k => el('span', { class: 'chip', title: ROLE_TIP[k] }, `${RANK_ROLE_JA[k]} ${d.role_counts[k]}`));
  const cards = [];
  for (let i = 0; i < d.members.length; i++) {
    const r = d.members[i], m = filled[i];
    const w = await weaknessOf(m.species, m.item, m.ability);
    const chip = (t) => typeChip(t, T_JA(t), true);
    cards.push(el('div', { class: 'eval-mon' },
      el('div', { class: 'eval-head' }, el('b', {}, monLabel(r.ja)), w.mega ? el('span', { class: 'chip' }, `メガ→${w.mega.ja}`) : ''),
      el('div', { class: 'eval-roles' }, r.roles.length ? r.roles.map(t => el('div', {}, el('span', { class: 'role', title: ROLE_TIP[t.tag] || '' }, t.ja), el('small', { class: 'muted' }, ` ${t.reason}`)))
        : el('span', { class: 'muted' }, '役割が付かない（積み技・火力・耐久などの条件に当てはまらない）')),
      el('div', { class: 'eval-weak' }, el('span', { class: 'lbl' }, '弱点 ', help('受けたときの弱点。メガ後の姿で見て、特性が決まっているときは相性を変える特性（ふゆう等）も反映')),
        w.x4.length || w.x2.length ? [...(w.x4.length ? [el('b', { class: 'wk-m' }, '×4'), ...w.x4.map(chip)] : []), ...(w.x2.length ? [el('b', { class: 'wk-m' }, '×2'), ...w.x2.map(chip)] : [])] : el('span', { class: 'muted' }, 'なし'))));
  }
  return el('div', { class: 'card', style: 'margin-top:18px' },
    el('h2', {}, '役割と弱点 ', help('持ち物・技・能力ポイントから自動で付けた役割。構築の型に必要な役割が揃っているかを下で確認する')),
    el('div', { class: 'muted', style: 'margin-bottom:8px' }, `構築の型: ${d.archetype}　`, ...counts),
    el('div', { class: 'eval-grid' }, ...cards));
}
const T_JA = (t) => S.types.types.find(x => x.id === t).ja;

function findingsCard(d) {
  const groups = [['role', '役割の不足'], ['threat', '勝てる駒がいない相手', '使用率上位30体のうち、自分の6体に有利な駒が少ない相手']];
  const body = el('div');
  for (const [kind, title, tip] of groups) {
    const fs = d.findings.filter(f => f.kind === kind);
    body.append(el('h3', {}, title, ' ', tip ? help(tip) : ''));
    if (!fs.length) body.append(el('div', { class: 'muted' }, '目立った穴は見つからない'));
    for (const f of fs) body.append(el('div', { class: 'finding ' + f.level }, f.text));
  }
  return el('div', { class: 'card', style: 'margin-top:18px' }, el('h2', {}, '気になる点'), body);
}

function overlapCard(d) {
  const rows = (d.type_overlap || []).filter(o => o.weak >= 2).sort((a, b) => b.weak - a.weak);
  const box = el('div');
  if (!rows.length) box.append(el('div', { class: 'muted' }, '同じタイプの弱点が2体以上に重なる攻撃タイプは無い'));
  else {
    const t = el('table', { class: 'plain' }, el('tr', {}, el('th', {}, '攻撃タイプ'), el('th', {}, '弱点'), el('th', {}, '半減以下'), el('th', {}, '弱点のポケモン')));
    for (const o of rows) t.append(el('tr', { class: o.weak >= 3 ? 'warn' : '' }, el('td', {}, typeChip(o.type, o.ja)), el('td', {}, `${o.weak}体`), el('td', {}, `${o.resist}体`), el('td', {}, o.weak_members.join('・'))));
    box.append(el('div', { class: 'scroll-x' }, t));
  }
  return el('div', { class: 'card', style: 'margin-top:18px' }, el('h2', {}, 'タイプの重なり ', help('同じ攻撃タイプに弱いポケモンの数。3体以上は赤。半減以下が0体なら、そのタイプの攻撃を受けられる駒がいない')), box);
}

// ---- 能力ポイント調整 ----
async function tuneCard(view) {
  threats = threats || await api('/api/threats');
  const members = T.members.map((m, i) => ({ m, i })).filter(x => x.m.species);
  const jaOf = (x) => (S.types.pokemon.find(p => p.id === x.m.species) || {}).ja || x.m.species;
  const moveJa = (id) => (S.types.moves[id] || [])[1] || id;
  const who = el('select', {}, ...members.map(x => el('option', { value: x.i }, jaOf(x))));
  const mode = el('select', {}, el('option', { value: 'survive' }, '相手の技を耐える（H・B/D）'), el('option', { value: 'ko' }, '相手を倒す（A/C）'));
  const opp = el('select', {}, ...threats.map(t => el('option', { value: t.id }, `${t.rank}位 ${t.ja}`)));
  const move = el('select');
  const hits = el('select', {}, ...[1, 2, 3].map(n => el('option', { value: n }, `${n}発`)));
  const cond = el('select', {}, el('option', { value: 'guaranteed' }, '確定で'), el('option', { value: 'pct' }, '確率を指定'));
  const pct = el('input', { type: 'number', min: 0, max: 100, value: 10, disabled: true, 'aria-label': '確率（%）' });
  const worst = el('input', { type: 'checkbox' });
  const pctLbl = el('span', {}, '倒される確率');
  const setLbl = el('div', { class: 'muted', style: 'margin-top:8px;font-size:13px' });
  const out = el('div', { style: 'margin-top:10px' });
  const f = (text, node, tip) => el('label', { class: 'f' }, tip ? [text, help(tip)] : text, node);
  const fillMoves = () => {
    move.innerHTML = '';
    const t = threats.find(x => x.id === opp.value);
    if (mode.value === 'survive') {
      (t ? t.moves : []).forEach(mv => move.append(el('option', { value: mv.id }, mv.ja)));
      setLbl.textContent = t ? `相手の型: ${t.set_label}` : '';
    } else {
      const m = T.members[parseInt(who.value, 10)];
      (m.moves || []).forEach(mv => move.append(el('option', { value: mv }, moveJa(mv))));
      setLbl.textContent = t ? `相手の型: ${t.set_label}` : '';
    }
    pctLbl.textContent = mode.value === 'survive' ? '倒される確率（%以下）' : '倒す確率（%以上）';
  };
  const run = debounce(async () => {
    if (!move.value) { out.textContent = '技がない'; return; }
    const surv = mode.value === 'survive';
    const thr = cond.value === 'pct' ? parseFloat(pct.value || '0') / 100 : (surv ? 0 : 1);
    const body = { index: parseInt(who.value, 10), mode: mode.value, opponent: opp.value, move: move.value, hits: parseInt(hits.value, 10), threshold: thr, worst_case: worst.checked, members: T.members };
    try {
      const r = await api('/api/tune', { method: 'POST', body });
      out.innerHTML = '';
      const sk = STAT_JA[r.stat];
      const keep = `固定: ${Object.entries(r.keep).filter(([, v]) => v).map(([k, v]) => STAT_JA[k] + v).join(' ') || 'なし'}／使える残り ${r.budget}`;
      const apply = async (sp, label) => { await applySp(body.index, sp); T = await workingTeam(); toast(`${label} をパーティに反映した（保存はパーティ画面で）`); view.innerHTML = ''; await page.render(view); };
      if (surv) {
        out.append(el('div', {}, `いま: ${r.current.damage_pct[0]}〜${r.current.damage_pct[1]}%、${body.hits}発で倒される確率 ${(r.current.ko_chance * 100).toFixed(1)}%`), el('div', { class: 'muted' }, keep));
        if (!r.feasible) { out.append(el('div', { class: 'err' }, r.note)); return; }
        const t = el('table', { class: 'plain' }, el('tr', {}, el('th', {}, '配分'), el('th', {}, '合計'), el('th', {}, '被ダメ'), el('th', {}, '確率'), el('th', {}, '')));
        for (const o of r.options) t.append(el('tr', {}, el('td', {}, `H${o.hp} ${sk}${o[r.stat]}`), el('td', {}, o.total), el('td', {}, `${o.damage_pct[0]}〜${o.damage_pct[1]}%`), el('td', {}, `${(o.ko_chance * 100).toFixed(1)}%`),
          el('td', {}, el('button', { class: 'btn small', onclick: () => apply({ ...r.keep, hp: o.hp, [r.stat]: o[r.stat] }, `H${o.hp} ${sk}${o[r.stat]}`) }, '反映'))));
        out.append(el('div', { class: 'scroll-x' }, t), el('div', { class: 'muted' }, `余り ${r.budget - (r.options[0] ? r.options[0].total : 0)} ポイントを他に回せる`));
      } else {
        out.append(el('div', { class: 'muted' }, keep));
        if (!r.feasible) { out.append(el('div', { class: 'err' }, r.note)); return; }
        const o = r.option;
        out.append(el('div', {}, `${sk}${o[r.stat]} で ${o.damage_pct[0]}〜${o.damage_pct[1]}%（${body.hits}発で倒す確率 ${(o.ko_chance * 100).toFixed(1)}%）`, ' ',
          el('button', { class: 'btn small', onclick: () => apply({ ...r.keep, [r.stat]: o[r.stat] }, `${sk}${o[r.stat]}`) }, '反映')));
      }
    } catch (e) { out.textContent = '計算エラー: ' + e.message; }
  }, 150);
  [who, mode, opp].forEach(x => x.addEventListener('change', () => { fillMoves(); run(); }));
  [move, hits, pct, worst].forEach(x => x.addEventListener('change', run));
  cond.addEventListener('change', () => { pct.disabled = cond.value !== 'pct'; run(); });
  fillMoves(); run();
  return el('div', { class: 'card', style: 'margin-top:18px' },
    el('h2', {}, '能力ポイント調整 ', help('仮想敵（使用率の高い順）の技を耐える最小のH・B/D、または倒すのに必要な最小のA/C。「反映」はパーティ画面の編集中の内容に入り、保存はパーティ画面で行う')),
    el('div', { class: 'grid2' }, f('自分のポケモン', who), f('目的', mode)),
    el('div', { class: 'grid2', style: 'margin-top:8px' }, f('仮想敵', opp), f('技', move)),
    el('div', { class: 'grid3', style: 'margin-top:8px' }, f('回数', hits), f('条件', cond), f(pctLbl, pct)),
    el('label', { class: 'check', style: 'margin-top:8px' }, worst, '相手を最大火力の型で計算', help('相手の性格・能力ポイント・持ち物を、こちらに不利な最大火力に振った型で計算する')),
    setLbl, out);
}
