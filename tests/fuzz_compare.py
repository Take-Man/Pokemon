"""fuzz_casesの結果をエンジンで計算し、Showdownの出力と突き合わせる（開発用）。"""
import json, sys
from collections import Counter
sys.path.insert(0, '.')
from engine.stats import Build
from engine.damage import Side, Field, Options, calc
from engine.data import to_id
cases = json.load(open(sys.argv[1])); ref = {r["name"]: r for r in json.load(open(sys.argv[2]))}
bad = []; ok = 0
for c in cases:
    A, Dd = c["attacker"], c["defender"]
    a = Side(Build(A["species"], to_id(A["nature"]), A["sp"], A["ability"], A["item"] or None), boosts=c.get("atkBoosts", {}), status=A.get("status"))
    d = Side(Build(Dd["species"], to_id(Dd["nature"]), Dd["sp"], Dd["ability"], Dd["item"] or None), boosts=c.get("defBoosts", {}),
             reflect=Dd.get("reflect", False), light_screen=Dd.get("light_screen", False))
    f = Field(**c.get("field", {}))
    r = calc(a, d, c["move"], f, Options(crit=c.get("crit", False), hits=1))
    if "rolls" not in ref[c["name"]]: continue
    exp = ref[c["name"]]["rolls"]
    exp = [0 if x in (False, None, "") else x for x in exp]
    if r.rolls == sorted(exp): ok += 1
    else: bad.append((c["name"], c["move"], A["ability"], A["item"], Dd["ability"], Dd["item"], c.get("field"), r.rolls[:2], exp[:2]))
print(f"一致 {ok}/{len(cases)}")
for b in bad[:60]: print(b)
