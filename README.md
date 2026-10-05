# 対戦サポート（ポケモンチャンピオンズ・シングル）

対戦中に別端末（このPC）で使う、選出予想・ダメ計・素早さ比較・型参照のローカルアプリ。

## セットアップ（初回のみ）

```
cd ~/Pokemon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.10以上。

## 起動

```
source .venv/bin/activate
python -m app
```

ブラウザで http://127.0.0.1:8765 が開く。

対戦中に使う最小機能の画面（パーティ・選出・ダメ計・タイプ相性）は次のコマンドで起動する。

```
python -m app --ui simple
```

どちらの画面も同じ `data/user`（パーティ・相手の6体）を読み書きするので、同時に開いて編集しないこと（同時に起動するときは `--port` を分ける）。コードが書き換わると自動で再起動する（止めるときは `--no-reload`）。画面上部に赤い帯が出たら、表示どおりサーバの起動し直しかブラウザの再読み込みをする。

## 画像からのパーティ取り込み

新UIのパーティ画面で、ゲームの「パーティ確認」画面のスクショ（能力タブ・ステータスタブ）から6体を取り込める。macOS は追加設定なし（`pip install -r requirements.txt` で Vision 用の pyobjc が入る）。Linux などでは tesseract と日本語データ（`jpn`）を入れる。

## 環境データの取得

```
python -m collectors.pokedb probe          # 初回: サイト構造の確認（結果をClaudeに見せてパーサを確定）
python -m collectors.pokedb update --top 60
```

取得前でも、相手の型は種族値からの推定で動く。

## テスト

```
python -m pytest -q
```

## データの再生成（レギュレーションが変わったとき）

固定データは Pokémon Showdown の champions mod と PokeAPI から作っている。Showdown のビルドには Node.js 22 以上が必要。

```
git clone --depth 1 https://github.com/smogon/pokemon-showdown.git ../pokemon-showdown
(cd ../pokemon-showdown && npm install && node build)
node tools/export_showdown.js ../pokemon-showdown data/static/_src gen9championsbssregmc
# PokeAPI の CSV（data/v2/csv）を取得したディレクトリを指定
python tools/build_static.py <PokeAPIのcsvディレクトリ>
python tools/build_knowledge.py
```

新レギュのフォーマットIDは Showdown の config/formats.ts で確認する。

## フォルダ

docs/spec.md を参照。Claudeのチャットから読むときの入口は CLAUDE.md と state/current.md。
