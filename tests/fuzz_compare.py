"""fuzz_casesの結果をエンジンで計算し、Showdownの出力と突き合わせる（開発用）。

python tests/fuzz_compare.py <cases.json> <showdown結果.json>
Showdown側（tools/verify_with_showdown.js）は1発目だけを測るので、おやこあいは1発目どうしで比べる。
"""
import json, sys
sys.path.insert(0, '.')
from engine.stats import Build
from engine.damage import Side, Field, Options, calc
from engine.data import to_id
cases = json.load(open(sys.argv[1])); refs = json.load(open(sys.argv[2]))
bad = []; ok = 0; skipped = 0
for c, ref in zip(cases, refs):  # 同名のケースがあるので順番で対応づける
    if "rolls" not in ref:
        skipped += 1
        continue
    A, Dd = c["attacker"], c["defender"]
    a = Side(Build(A["species"], to_id(A["nature"]), A["sp"], A["ability"], A["item"] or None), boosts=c.get("atkBoosts", {}), status=A.get("status"))
    d = Side(Build(Dd["species"], to_id(Dd["nature"]), Dd["sp"], Dd["ability"], Dd["item"] or None), boosts=c.get("defBoosts", {}),
             reflect=Dd.get("reflect", False), light_screen=Dd.get("light_screen", False))
    f = Field(**c.get("field", {}))
    r = calc(a, d, c["move"], f, Options(crit=c.get("crit", False), hits=1))
    got = r.hit_rolls[0] if r.hit_rolls else r.rolls
    exp = sorted(0 if x in (False, None, "") else x for x in ref["rolls"])
    if sorted(got) == exp: ok += 1
    else: bad.append((c["name"], c["move"], A["ability"], A["item"], Dd["ability"], Dd["item"], c.get("field"), sorted(got)[:2], exp[:2]))
print(f"一致 {ok}/{len(cases) - skipped}（Showdown側のエラー {skipped}件）")
for b in bad[:80]: print(b)
