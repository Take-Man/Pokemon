// 画面間で共有する状態と、読み込み済みデータ
import { api } from './ui.js';

export const S = { meta: null, types: null, dex: {} };

export async function loadMeta() { return S.meta || (S.meta = await api('/api/meta')); }
export async function loadTypes() { return S.types || (S.types = await api('/api/types')); }
export async function dexInfo(id) { return S.dex[id] || (S.dex[id] = await api(`/api/pokemon/${encodeURIComponent(id)}`)); }
