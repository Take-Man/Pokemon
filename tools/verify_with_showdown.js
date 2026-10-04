// エンジンの検証用: Showdownシミュレータで同条件のダメージ16通りを出す（開発用）。
// node tools/verify_with_showdown.js <showdownパス(ビルド済み)> <cases.json>
const path = require('path');
const fs = require('fs');
const ps = path.resolve(process.argv[2]);
const { Battle } = require(path.join(ps, 'dist/sim/battle'));
const cases = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

function mk(b, move) {
  return { species: b.species, ability: b.ability || '', item: b.item || '', nature: b.nature || 'Hardy',
    evs: Object.assign({ hp: 0, atk: 0, def: 0, spa: 0, spd: 0, spe: 0 }, b.sp || {}),
    ivs: { hp: 31, atk: 31, def: 31, spa: 31, spd: 31, spe: 31 }, moves: [move], level: 50, name: 'x' };
}

function oneRoll(c, k) {
  const battle = new Battle({ formatid: 'gen9championsbssregmc', seed: [1, 2, 3, 4] });
  battle.setPlayer('p1', { team: [mk(c.attacker, c.move)] });
  battle.setPlayer('p2', { team: [mk(c.defender, c.move)] });
  try { battle.choose('p1', 'team 1'); battle.choose('p2', 'team 1'); } catch (e) {}
  const src = battle.p1.active[0], tgt = battle.p2.active[0];
  // 登場時特性（いかく・天候・フィールド・トレース等）の影響を消す
  src.clearBoosts(); tgt.clearBoosts();
  battle.field.clearWeather(); battle.field.clearTerrain();
  if (c.field && c.field.weather) battle.field.setWeather({ sun: 'sunnyday', rain: 'raindance', sand: 'sandstorm', snow: 'snowscape' }[c.field.weather], src);
  if (c.field && c.field.terrain) battle.field.setTerrain(c.field.terrain + 'terrain', src);
  if (c.atkBoosts) src.setBoost(c.atkBoosts);
  if (c.defBoosts) tgt.setBoost(c.defBoosts);
  if (c.defender.reflect) battle.p2.addSideCondition('reflect', tgt);
  if (c.defender.light_screen) battle.p2.addSideCondition('lightscreen', tgt);
  if (c.attacker.status) src.setStatus(c.attacker.status, src);
  battle.random = (m, n) => (m === 16 ? k : 0);
  battle.randomChance = () => false;
  let move = battle.dex.getActiveMove(c.move);
  if (c.crit) move.willCrit = true;
  battle.singleEvent('ModifyType', move, null, src, tgt, move, move);
  battle.singleEvent('ModifyMove', move, null, src, tgt, move, move);
  move = battle.runEvent('ModifyType', src, tgt, move, move);
  move = battle.runEvent('ModifyMove', src, tgt, move, move);
  battle.runEvent('PrepareHit', src, tgt, move);
  const imm = tgt.runImmunity(move) && battle.runEvent('TryImmunity', tgt, src, move) !== false;
  const tryHit = battle.runEvent('TryHit', tgt, src, move);
  if (!imm || tryHit === null || tryHit === false) return 0;
  const d = battle.actions.getDamage(src, tgt, move);
  return { d: d || 0, hp: tgt.maxhp };
}

const out = [];
for (const c of cases) {
  try {
    const rolls = []; let hp = 0;
    for (let k = 15; k >= 0; k--) { const r = oneRoll(c, k); rolls.push(r === 0 ? 0 : r.d); if (r) hp = r.hp; }
    out.push({ name: c.name, rolls: rolls.sort((a, b) => a - b), hp });
  } catch (e) { out.push({ name: c.name, error: String(e).slice(0, 200) }); }
}
console.log(JSON.stringify(out));
