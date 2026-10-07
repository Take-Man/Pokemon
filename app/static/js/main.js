import { $, el, banner } from './ui.js';
import { loadMeta, loadTypes } from './store.js';
import team from './pages/team.js';
import select from './pages/select.js';
import calc from './pages/calc.js';
import reverse from './pages/reverse.js';
import evaluate from './pages/evaluate.js';
import history from './pages/history.js';
import types from './pages/types.js';

const pages = [team, select, calc, reverse, evaluate, history, types];

function renderNav(cur) {
  const nav = $('#nav'); nav.innerHTML = '';
  for (const p of pages) {
    nav.append(el('button', { class: 'step' + (p.key === cur ? ' on' : '') + (p.side ? ' side sep' : ''), onclick: () => { location.hash = p.key; } },
      el('span', { class: 'n' }, p.badge), el('span', { class: 'lbl' }, p.label)));
  }
}

let current = null;
async function show() {
  const key = location.hash.slice(1) || 'team';
  const page = pages.find(p => p.key === key) || pages[0];
  if (current && current.leave) await current.leave();  // 前の画面の保存待ちを済ませてから次の画面を読む
  current = page;
  renderNav(page.key);
  const view = $('#view'); view.innerHTML = '';
  try { await page.render(view); } catch (e) { console.error(e); banner(`${page.label}の表示に失敗: ${e.message}`); }
  window.scrollTo(0, 0);
}

window.addEventListener('hashchange', show);
(async () => { try { await Promise.all([loadMeta(), loadTypes()]); } catch (e) { banner('データの読み込みに失敗。サーバを確認してください'); } show(); })();
