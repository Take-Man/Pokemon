// 共通部品（DOM生成・API・ピッカー・タイプチップ・ヘルプ）
export const $ = (s, r = document) => r.querySelector(s);
export const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) e.append(k.nodeType ? k : String(k));
  return e;
};
export const debounce = (fn, ms = 250) => { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); }; };

// サービス版はログインのアクセストークンを付ける（auth.js が設定する）。401 なら onUnauthorized（ログイン画面へ）
let authToken = async () => null;
let onUnauthorized = () => {};
export function setAuth(getToken, unauthorized) { authToken = getToken; onUnauthorized = unauthorized; }

export async function api(path, opt = {}) {
  const headers = { 'Content-Type': 'application/json' };
  const tok = await authToken();
  if (tok) headers.Authorization = `Bearer ${tok}`;
  const r = await fetch(path, { headers, ...opt, body: opt.body ? JSON.stringify(opt.body) : undefined });
  if (!r.ok) {
    const t = await r.text();
    if (r.status === 401) onUnauthorized();
    else if (r.status === 403) { let d = t; try { d = JSON.parse(t).detail; } catch (_) { /* 本文のまま */ } banner(d); }
    else if (r.status >= 500 || r.status === 404) banner(`サーバでエラー（${path.split('?')[0]}）。時間をおいても続くときは知らせてください`);
    throw new Error(t);
  }
  return r.json();
}
export function banner(msg) { const b = $('#banner'); if (b) { b.textContent = msg; b.title = '押すと閉じる'; b.onclick = () => { b.hidden = true; }; b.hidden = false; } }
export function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove('show'), 1800); }

// ---- タイプ ----
export const TYPE_COLOR = { Normal: '#A8A77A', Fire: '#EE8130', Water: '#6390F0', Electric: '#F7D02C', Grass: '#7AC74C', Ice: '#96D9D6',
  Fighting: '#C22E28', Poison: '#A33EA1', Ground: '#E2BF65', Flying: '#A98FF3', Psychic: '#F95587', Bug: '#A6B91A',
  Rock: '#B6A136', Ghost: '#735797', Dragon: '#6F35FC', Dark: '#705746', Steel: '#B7B7CE', Fairy: '#D685AD' };
export const TYPE_SHORT = { Normal: '無', Fire: '炎', Water: '水', Electric: '電', Grass: '草', Ice: '氷', Fighting: '闘', Poison: '毒', Ground: '地',
  Flying: '飛', Psychic: '超', Bug: '虫', Rock: '岩', Ghost: '霊', Dragon: '竜', Dark: '悪', Steel: '鋼', Fairy: '妖' };
export function typeFg(t) {
  const h = TYPE_COLOR[t] || '#888'; const r = parseInt(h.slice(1, 3), 16), g = parseInt(h.slice(3, 5), 16), b = parseInt(h.slice(5, 7), 16);
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? '#1d2330' : '#fff';
}
export const typeChip = (t, label, short = false) => el('span', { class: 'tchip', style: `background:${TYPE_COLOR[t]};color:${typeFg(t)}` }, short ? TYPE_SHORT[t] : label);

// 確認（画面の中に出すダイアログ）。ブラウザ標準の confirm・prompt は、アプリ内ブラウザ（LINE等）で表示されずに
// 即「キャンセル」になることがあるので使わない。結果は Promise<boolean>。
// type を渡すと、その文字を入力するまで OK を押せない（取り返しのつかない操作用）
export function confirmBox(message, { ok = 'OK', cancel = 'やめる', danger = false, type = null } = {}) {
  return new Promise((resolve) => {
    const prev = document.activeElement;
    const close = (v) => { overlay.remove(); document.removeEventListener('keydown', onKey, true); if (prev && prev.focus) prev.focus(); resolve(v); };
    const input = type ? el('input', { placeholder: type, 'aria-label': `確認のため「${type}」と入力`, oninput: () => { okBtn.disabled = input.value.trim() !== type; } }) : null;
    const okBtn = el('button', { class: 'btn ' + (danger ? 'danger' : 'primary'), disabled: !!type, onclick: () => close(true) }, ok);
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); close(false); }
      else if (e.key === 'Enter' && !okBtn.disabled && (!type || document.activeElement === input)) { e.preventDefault(); close(true); }
    };
    const overlay = el('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', onclick: (e) => { if (e.target === overlay) close(false); } },
      el('div', { class: 'modal-card card' }, el('div', { class: 'modal-msg' }, message),
        input ? el('div', { class: 'modal-input' }, el('small', { class: 'muted' }, `確認のため「${type}」と入力`), input) : '',
        el('div', { class: 'modal-btns' }, el('button', { class: 'btn ghost', onclick: () => close(false) }, cancel), okBtn)));
    document.body.append(overlay);
    document.addEventListener('keydown', onKey, true);
    (input || okBtn).focus();
  });
}

// 「？」マーク。用語の説明をその場で出す
export const help = (tip) => el('span', { class: 'help', tabindex: '0', 'data-tip': tip, 'aria-label': tip }, '?');

// ---- 検索付き入力 ----
export function picker({ kind, value = '', label = '', placeholder = '', species = () => null, onPick, onEnterNext }) {
  const input = el('input', { value: label || '', placeholder, autocomplete: 'off', spellcheck: 'false' });
  input.dataset.id = value || '';
  const dd = el('div', { class: 'dd', hidden: true });
  const wrap = el('div', { class: 'picker' }, input, dd);
  let items = [], sel = 0;
  const render = () => {
    dd.innerHTML = '';
    items.forEach((it, i) => {
      const extra = kind === 'pokemon' ? (it.types_ja || []).join('・')
        : kind === 'moves' ? `${it.category === 'Physical' ? '物理' : it.category === 'Special' ? '特殊' : '変化'} ${it.basePower || '-'}` : '';
      dd.append(el('div', { class: i === sel ? 'sel' : '', onmousedown: (e) => { e.preventDefault(); pick(it); } }, it.ja, el('small', {}, extra)));
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

// ページ見出し（番号バッジ＋タイトル）
export const lead = (badge, title) => el('div', { class: 'lead' }, el('h1', {}, el('span', { class: 'badge' }, badge), title));
