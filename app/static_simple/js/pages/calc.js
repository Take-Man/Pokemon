import { el, lead } from '../ui.js';

export default {
  key: 'calc', label: 'ダメ計', badge: '3',
  async render(view) { view.append(lead('3', 'ダメ計', '準備中')); },
};
