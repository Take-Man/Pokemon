"""python -m app でローカルサーバを起動する。

既定でコードの変更を検知して自動で再起動する（Claudeがコードを書き換えたあと、再起動し忘れて
古いサーバが動き続けるのを防ぐ）。止めたいときは --no-reload。
"""
import argparse
import os
import webbrowser
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8765)
ap.add_argument("--no-browser", action="store_true")
ap.add_argument("--no-reload", action="store_true")
ap.add_argument("--ui", choices=["classic", "simple"], default="classic",
                help="classic=現行の分析向け画面、simple=対戦中に使う最小機能の画面")
a = ap.parse_args()
os.environ["APP_UI"] = a.ui  # reload の子プロセスにも引き継がれる
if not a.no_browser:
    webbrowser.open(f"http://127.0.0.1:{a.port}")
if a.no_reload:
    uvicorn.run("app.server:app", host="127.0.0.1", port=a.port, reload=False)
else:
    uvicorn.run("app.server:app", host="127.0.0.1", port=a.port, reload=True,
                reload_dirs=[str(ROOT / d) for d in ("app", "engine", "collectors")])
