# サービス版のセットアップ手順

サービス版（ログインあり・Vercel＋Supabase）を動かすまでの手順。構成の考え方は [service-architecture.md](service-architecture.md)。
ローカル版（`python -m app`）はこの手順なしで今までどおり動く。

## 1. Supabase

1. https://supabase.com でプロジェクトを作る。リージョンは **Northeast Asia (Tokyo)**。データベースのパスワードは控えておく
2. 左メニュー「SQL Editor」で [supabase/migrations/20261008000000_init.sql](../supabase/migrations/20261008000000_init.sql) の中身を貼って実行する
3. 「Project Settings → API」で次の3つを控える（後で Vercel に入れる）
   - Project URL（例: `https://abcdxyz.supabase.co`）→ `SUPABASE_URL`
   - anon / publishable key → `SUPABASE_ANON_KEY`（画面に渡してよい公開キー。RLS で守られる）
   - service_role / secret key → `SUPABASE_SERVICE_ROLE_KEY`（**秘密**。アカウント削除だけで使う。画面やGitに出さない）
4. 「Authentication → Sign In / Providers」
   - **Email はオフ**（MVPは Google のみ）
   - Google をオンにして、次の手順2で作る Client ID と Client Secret を入れる
   - 画面に出ている Callback URL（`https://<プロジェクト>.supabase.co/auth/v1/callback`）を控える

## 2. Google Cloud（Googleログイン）

1. https://console.cloud.google.com でプロジェクトを作る
2. 「APIとサービス → OAuth 同意画面」: 外部、アプリ名・サポートメールを入れる。スコープは既定（email・profile・openid）のまま
3. 「認証情報 → 認証情報を作成 → OAuth クライアント ID」: 種類は「ウェブ アプリケーション」
   - 承認済みのリダイレクト URI に、手順1-4の Callback URL を入れる
4. 表示された Client ID・Client Secret を Supabase の Google 設定に入れる

## 3. Vercel

1. https://vercel.com で GitHub の `Take-Man/Pokemon` を Import する（Framework Preset は FastAPI を自動で選ぶ）
2. 「Settings → Environment Variables」に入れる
   - `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY`（手順1-3）
   - `PBA_USAGE_DATA` は入れない（既定で使用率データを使わない。取得先の利用許可が出たら `on`）
3. Deploy。出来たURL（例: `https://pokemon-xxx.vercel.app`）を控える
4. Supabase の「Authentication → URL Configuration」
   - Site URL: 手順3-3のURL
   - Redirect URLs: 同じURL（独自ドメインにしたら追加する）

## 4. 動作確認

- 開くとログイン画面が出る → Google でログイン → パーティ画面が出る
- 「アカウント」タブにメールアドレスとプラン（無料・パーティ5件・対戦履歴50件）が出る
- 別の Google アカウントでログインすると、最初のアカウントのパーティ・履歴が見えない

上限の数は Supabase の `plan_limits` 表（`free` の行）を書き換えれば変わる。

## ローカルでサービス版を試す

```
export SUPABASE_URL=https://<プロジェクト>.supabase.co SUPABASE_ANON_KEY=<anonキー> SUPABASE_SERVICE_ROLE_KEY=<service_roleキー>
.venv/bin/python -m uvicorn service.main:app --port 8770
```

http://localhost:8770 を開く。Googleログインから戻ってくるには、Supabase の Redirect URLs に `http://localhost:8770` を足す。

## 使えない機能（サービス版）

- 画像からのパーティ取り込み（macOS の文字認識に依存）
- 環境データの「更新を確認」（運営者がローカルで取得して git push する）
- 相手の6体のファイル経由の読み込み・Claude 向けの state/ 書き出し
