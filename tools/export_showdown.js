// Pokémon Showdown の champions mod から、現行レギュ（シングル）で使用可能なデータを書き出す。
// 使い方: node tools/export_showdown.js <pokemon-showdownのパス(ビルド済み)> <出力dir> [formatId]
const path = require('path');
const fs = require('fs');
const psRoot = path.resolve(process.argv[2]);
const outDir = path.resolve(process.argv[3]);
const formatId = process.argv[4] || 'gen9championsbssregmc';
const { Dex } = require(path.join(psRoot, 'dist/sim'));
const { TeamValidator } = require(path.join(psRoot, 'dist/sim/team-validator'));

const format = Dex.formats.get(formatId);
const dex = Dex.mod(format.mod);
const validator = new TeamValidator(format);

const species = [];
const movePoolAll = new Set();
for (const s of dex.species.all()) {
  if (s.isNonstandard) continue;
  const set = { species: s.name, ability: s.abilities[0], moves: ['protect'], level: 50, evs: {}, nature: 'Hardy', item: s.requiredItem || '' };
  const probs = (validator.validateSet(set, {}) || []).filter(p => !/move|ability|item|EVs|Protect|learn/i.test(p));
  if (probs.length) continue;
  let pool = [];
  try { pool = [...dex.species.getMovePool(s.id)]; } catch (e) { pool = []; }
  pool = pool.filter(m => { const mv = dex.moves.get(m); return mv.exists && !mv.isNonstandard; });
  pool.forEach(m => movePoolAll.add(m));
  species.push({
    id: s.id, name: s.name, num: s.num, baseSpecies: s.baseSpecies, forme: s.forme || '',
    types: s.types, baseStats: s.baseStats, abilities: s.abilities, weightkg: s.weightkg,
    isMega: !!s.isMega, requiredItem: s.requiredItem || null,
    otherFormes: s.otherFormes || [], changesFrom: s.changesFrom || null,
    tier: s.tier, battleOnly: s.battleOnly || null, moves: pool.sort(),
  });
}

const moves = [];
for (const m of dex.moves.all()) {
  if (m.isNonstandard || !movePoolAll.has(m.id)) continue;
  moves.push({
    id: m.id, name: m.name, num: m.num, type: m.type, category: m.category,
    basePower: m.basePower, accuracy: m.accuracy, pp: m.pp, priority: m.priority,
    target: m.target, flags: m.flags, critRatio: m.critRatio || 1, willCrit: !!m.willCrit,
    multihit: m.multihit || null, recoil: m.recoil || null, drain: m.drain || null,
    hasSecondary: !!(m.secondary || (m.secondaries && m.secondaries.length)),
    secondary: m.secondary ? { chance: m.secondary.chance, status: m.secondary.status, volatileStatus: m.secondary.volatileStatus, boosts: m.secondary.boosts, self: m.secondary.self } : null,
    self: m.self || null, selfBoost: m.selfBoost || null, boosts: m.boosts || null,
    overrideOffensiveStat: m.overrideOffensiveStat || null, overrideOffensivePokemon: m.overrideOffensivePokemon || null,
    overrideDefensiveStat: m.overrideDefensiveStat || null, ignoreDefensive: !!m.ignoreDefensive,
    selfSwitch: m.selfSwitch || null, heal: m.heal || null, status: m.status || null, volatileStatus: m.volatileStatus || null,
    sideCondition: m.sideCondition || null, weather: m.weather || null, terrain: m.terrain || null, pseudoWeather: m.pseudoWeather || null,
    shortDesc: m.shortDesc,
  });
}

const abilityIds = new Set();
species.forEach(s => Object.values(s.abilities).forEach(a => abilityIds.add(dex.abilities.get(a).id)));
const abilities = [...abilityIds].map(id => { const a = dex.abilities.get(id); return { id: a.id, name: a.name, num: a.num, shortDesc: a.shortDesc, flags: a.flags }; });

const items = dex.items.all().filter(i => !i.isNonstandard).map(i => ({
  id: i.id, name: i.name, num: i.num, megaStone: i.megaStone || null, megaEvolves: i.megaEvolves || null,
  isBerry: !!i.isBerry, naturalGift: i.naturalGift || null, fling: i.fling || null, shortDesc: i.shortDesc,
}));

const natures = dex.natures.all().map(n => ({ id: n.id, name: n.name, plus: n.plus || null, minus: n.minus || null }));
const types = dex.types.all().filter(t => !t.isNonstandard).map(t => ({ id: t.id, name: t.name, damageTaken: t.damageTaken }));

fs.mkdirSync(outDir, { recursive: true });
const meta = { format: format.name, formatId, mod: format.mod, exportedAt: new Date().toISOString(), counts: { species: species.length, moves: moves.length, abilities: abilities.length, items: items.length } };
for (const [k, v] of Object.entries({ species, moves, abilities, items, natures, types, meta })) {
  fs.writeFileSync(path.join(outDir, `showdown_${k}.json`), JSON.stringify(v));
}
console.log(JSON.stringify(meta));
