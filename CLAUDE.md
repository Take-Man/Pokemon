# Claude向けの案内（このフォルダをチャットから読むとき）

このフォルダはポケモンチャンピオンズ（シングル）の対戦サポートアプリ「ギャクダメノート（Gyakudame Note）」。アプリ本体はコードで、Claudeは
(1) 実装の変更 と (2) 状況を読んで自然言語で答える役を担う。

## 質問に答えるとき

1. まず state/current.md を読む（選択中のパーティ、保存済みパーティ一覧、相手の6体、選出予想、直近のダメ計が要約されている）
2. 必要に応じて周辺を読む
   - 対戦モード（選出・相手の型の確定/推定・記録）: state/battle.md、元データは data/user/matches/<id>.json
   - 対面表・予想の詳細: state/prediction.json（受け出し先・積みで起点にされる駒・実戦データ補正を含む）
   - 保存済みパーティ: data/user/teams/*.json（選択中は data/user/settings.json の active）
   - 構築診断・調整の計算: engine/roles.py（diagnose）、engine/tuning.py（survive / ko）
   - 相手・自分の型の採用率: data/snapshots/current/usage.json
   - 固定データ: data/static/*.json（pokemon/moves/items/abilities/natures/types）
   - 概念・用語: knowledge/battle_concepts.md、knowledge/types.md、knowledge/natures.md
3. 数値が必要なら推測せずエンジンで計算する（例）
   ```
   python -c "from engine.stats import Build; from engine.damage import Side, calc; \
   print(calc(Side(Build('garchomp','jolly',{'atk':32,'spe':32})), Side(Build('kingambit','adamant',{'hp':32})), 'earthquake').to_dict())"
   ```
4. 回答では、環境データ由来か推定かを区別して書く（usage.json の有無・fetched_at を確認）

## スクショから相手の6体を登録するとき

画像から6体を判定したら、次を実行する（名前は日本語でよい。見つからなければ候補が出る）。
起動中のアプリは3秒以内に反映する。

```
python tools/set_opponent.py "リザードン,バンギラス,マリルリ,ハッサム,カバルドン,ルカリオ" --source screenshot
```

## 実装を変えるとき

- 仕様: docs/spec.md（決定事項・構成・既知の限界）
- テスト: `python -m pytest -q`（ダメ計はShowdownとの一致ケースで回帰テスト）
- 固定データの再生成手順: README.md の「データの再生成」
- 書き口: 体言止め、または「〜した」。「〜である」調は使わない
