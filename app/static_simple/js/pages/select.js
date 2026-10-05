import { el, lead } from '../ui.js';

export default {
  key: 'select', label: '選出', badge: '2',
  async render(view) { view.append(lead('2', '選出', '準備中')); },
};
