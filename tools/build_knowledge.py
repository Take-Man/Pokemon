"""固定データからLLM向けのMarkdown（タイプ相性表・性格表）を生成する。python tools/build_knowledge.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.data import STAT_JA, dex  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "knowledge"
D = dex()
ORDER = ["Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground", "Flying",
         "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"]
types = [t for t in ORDER if t in D.type_chart]
ja = D.type_ja
sym = {2.0: "◎", 0.5: "△", 0.0: "×", 1.0: "・"}
L = ["# タイプ相性表", "", "行=攻撃タイプ、列=防御タイプ。◎=2倍 △=0.5倍 ×=無効 ・=等倍。機械可読版は data/static/types.json", "",
     "| 攻＼防 | " + " | ".join(ja[t] for t in types) + " |", "|" + "---|" * (len(types) + 1)]
for a in types:
    L.append(f"| {ja[a]} | " + " | ".join(sym[D.type_chart[a][d]] for d in types) + " |")
L += ["", "## 攻撃タイプ別の一覧", ""]
for a in types:
    row = D.type_chart[a]
    g = lambda v: "、".join(ja[d] for d in types if row[d] == v) or "なし"  # noqa: E731
    L.append(f"- {ja[a]}: 抜群={g(2.0)} ／ 半減={g(0.5)} ／ 無効={g(0.0)}")
(OUT / "types.md").write_text("\n".join(L) + "\n", encoding="utf-8")

N = ["# 性格一覧", "", "補正は上昇1.1倍・下降0.9倍（HPは補正なし）。表記は H/A/B/C/D/S。", "",
     "| 性格 | 英名 | 上昇 | 下降 | 略記 |", "|---|---|---|---|---|"]
for n in sorted(D.natures.rows, key=lambda n: (n["plus"] or "z", n["minus"] or "z")):
    N.append(f"| {n['ja']} | {n['en']} | {STAT_JA.get(n['plus'], '-')} | {STAT_JA.get(n['minus'], '-')} | {n['label']} |")
N += ["", "よく使う性格: いじっぱり(A↑C↓) ようき(S↑C↓) ひかえめ(C↑A↓) おくびょう(S↑A↓) わんぱく(B↑C↓) ずぶとい(B↑A↓) "
      "しんちょう(D↑C↓) おだやか(D↑A↓) ゆうかん(A↑S↓) れいせい(C↑S↓)"]
(OUT / "natures.md").write_text("\n".join(N) + "\n", encoding="utf-8")
print("knowledge/types.md, knowledge/natures.md を生成")
