"""相手の6体を state/opponent.json に書く（スクショ判定後にClaudeのチャットから実行する想定）。

使い方: python tools/set_opponent.py "リザードン,バンギラス,マリルリ,ハッサム,カバルドン,ルカリオ" [--source screenshot]
名前は日本語・英語・ひらがなのいずれでもよい。見つからない名前は候補を表示して終了する（ファイルは書かない）。
起動中のアプリは3秒以内にこのファイルの変更を検知して画面に反映する。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.state import save_opponent  # noqa: E402
from engine.data import dex  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("names")
ap.add_argument("--source", default="screenshot")
a = ap.parse_args()
D = dex()
names = [x.strip() for x in a.names.replace("、", ",").split(",") if x.strip()]
ids, bad = [], []
for n in names:
    p = D.pokemon.get(n)
    if p:
        ids.append(p["id"])
    else:
        bad.append((n, [r["ja"] for r in D.pokemon.search(n, 5)]))
if bad:
    for n, c in bad:
        print(f"見つからない: {n}  候補: {'、'.join(c) or 'なし'}")
    sys.exit(1)
o = save_opponent({"species": ids, "source": a.source})
print("書き込み:", "、".join(D.pokemon[i]["ja"] for i in o["species"]))
