import { el, lead } from '../ui.js';

export default {
  key: 'team', label: 'パーティ', badge: '1',
  async render(view) { view.append(lead('1', 'パーティ', '準備中')); },
};
