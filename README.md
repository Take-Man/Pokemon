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

ブラウザで http://127.0.0.1:8765 が開く。データ（パーティ・相手の6体・対戦）は `data/user` に保存される。同時に起動するときは `--port` を分ける。コードが書き換わると自動で再起動する（止めるときは `--no-reload`）。

## サービス版（ログインあり・公開用）

Vercel と Supabase で動かす版。手順は [docs/service-setup.md](docs/service-setup.md)、構成は [docs/service-architecture.md](docs/service-architecture.md)。ローカル版とコードは共通で、保存先だけが違う。

## 画像からのパーティ取り込み

新UIのパーティ画面で、ゲームの「パーティ確認」画面のスクショ（能力タブ・ステータスタブ）から6体を取り込める。macOS は追加設定なし（`pip install -r requirements.txt` で Vision 用の pyobjc が入る）。Linux などでは tesseract と日本語データ（`jpn`）を入れる。

## 環境データの取得

選出画面の「環境データ」の行で鮮度を確認し、「更新を確認」で取り直す。CLIでもできる。

```
python -m collectors.pokedb update --top 30
python -m collectors.pokedb probe          # 保存済みのHTMLでパーサを確認（通信なし）
```

取得先（ポケモンバトルデータベース）の利用規約と robots.txt に合わせて、次を守る。

- 自動・定期的には取りに行かない（「更新を確認」を押したとき、CLI、選出予想で環境データの無い相手がいたときだけ）
- 1件ずつ3秒以上空ける。1日150件まで。断られたら（403・429・5xx）1時間止める。ブラウザを使った取り直しなどの回避はしない
- User-Agent は個人用ツールであることを名乗る。robots.txt で禁止されたURLは取らない
- サイトの更新日時より後に取得済みのページは取り直さない。一覧の確認は1時間に1回まで

取得前でも、相手の型は種族値からの推定で動く。今日の件数・停止中かどうかは `data/snapshots/_raw/_access.json`。

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
