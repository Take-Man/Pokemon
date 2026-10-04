# 情報源アダプタ

## 方針

- サイトごとに1モジュール（collectors/<source>.py）。LLMにブラウザを操作させず、決まった手順のコードで取る
- 取得したHTMLは data/snapshots/_raw/<source>/ に保存し、パーサの修正は保存済みHTMLで検証する（`probe` は通信しない）
- 通信は標準ライブラリのurllib。失敗したときだけ Playwright（入っていれば）

## ポケモンバトルデータベース（collectors/pokedb.py）

### 利用条件（2026/6/11版の利用規約・robots.txt・公開データ案内から）

- 禁止: 過度な連続アクセス、大量のデータ取得を目的とした継続的・断続的なアクセス、競合サービス関係者のデータ取得
- robots.txt は AIクローラ（ClaudeBot等）を拒否。このアプリは本人がPCで手動実行する個人用ツールとして扱う
- 上位構築データ（CSV/JSON）はサイトが公式に配布。プログラムでの取得可、ただし過度な負荷は不可

これを受けた実装上の制限:

| 項目 | 設定 |
|---|---|
| アクセス間隔 | 同一サイトに3秒以上 |
| 詳細ページ | 既定で上位30体。取得済みは24時間再取得しない（`--force` で上書き） |
| 対戦中の追加取得 | 環境データに無い相手の分だけ |
| 名前一覧（検索API） | 7日に1回 |

### コマンド

```
python -m collectors.pokedb update            # 一覧＋上位30体の詳細（1回あたり最大約32リクエスト）
python -m collectors.pokedb update --only garchomp rotomwash
python -m collectors.pokedb opendata          # 前シーズンの上位構築（公開データ、1リクエスト）
python -m collectors.pokedb probe             # 保存済みHTMLでパーサ確認（通信なし）
```

アプリ右上の「環境データ更新」ボタンは `update` と同じ。選出予想ボタンは、環境データに無い相手の分だけ取る。

### 取れる項目（詳細ページ）

技・特性・性格・持ち物（各上位10、採用率%）、能力ポイント（個別配分の上位30）、同じチーム・倒したポケモン・倒されたポケモン（上位10、順位のみ）、倒した技・倒された技（上位10、%）。

ポケモンの対応付けは pokedb のキー（図鑑番号-フォルム番号）で行う。-00 と地方フォルムは自動、それ以外は pokedb.py の KEY_OVERRIDES。

## 出力形式

data/snapshots/current/usage.json

```json
{
  "source": "ポケモンバトルデータベース", "season": 6, "season_label": "シーズンM-6", "rule": "single",
  "source_updated": "2026/9/28 16:07", "fetched_at": "...",
  "ranking": [{"rank": 1, "id": "garchomp", "ja": "ガブリアス", "key": "0445-00"}],
  "pokemon": {
    "garchomp": {
      "moves": [{"id": "earthquake", "ja": "じしん", "rate": 67.6}],
      "abilities": [...], "natures": [...], "items": [...],
      "sp": [{"spread": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}, "rate": 26.9, "label": "AS + h"}],
      "teammates": [{"id": "primarina", "ja": "アシレーヌ"}],
      "ko_pokemon": [...], "ko_moves": [...], "koed_by_pokemon": [...], "koed_by_moves": [...],
      "fetched_at": "...", "key": "0445-00"
    }
  }
}
```

data/snapshots/current/top_teams.json: 前シーズンの上位構築（順位・レート・6体と持ち物）。

新しい情報源を足すときは、この形式に合わせれば engine 側はそのまま使える。
