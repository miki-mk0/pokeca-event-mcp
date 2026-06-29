# ポケモンカード イベント検索 MCP サーバー

Claude Code に話しかけるだけで、[players.pokemon-card.com](https://players.pokemon-card.com/event/search) のイベントを検索できる MCP サーバーです。

## こんなふうに使えます

Claude Code を開いて、そのまま日本語で聞くだけ：

```
東京の来月の土日のシティリーグを探して
大阪で8月にやるトレーナーズリーグのURL一覧が欲しい
横浜・川崎エリアのエルレイドSAR争奪戦を教えて
```

結果はイベント名・日付・店舗名・住所・URL で返ってきます。

## セットアップ

**必要なもの：** Node.js 18以上、Claude Code

```bash
git clone https://github.com/miki-mk0/pokeca-event-mcp.git
cd pokeca-event-mcp
./setup_mcp.sh
```

これだけで完了です。Claude Code を再起動すると使えるようになります。

### setup_mcp.sh がやること

1. npm パッケージをインストール（`@modelcontextprotocol/sdk`, `playwright`, `zod`）
2. Playwright の Chromium をインストール（初回のみ、約100MB）
3. `claude mcp add` で Claude Code にサーバーを登録

## 使える検索条件

| 条件 | 例 |
|------|----|
| 都道府県 | 東京、神奈川、大阪 など |
| 日付範囲 | 来月、7月、2026-07-01〜2026-07-31 |
| イベント名 | シティリーグ、トレーナーズリーグ、SAR争奪戦 |
| 土日祝のみ | 「土日だけ」「週末限定」など |
| 平日夜 | 「18時以降」「夕方から」など |

## 仕組み

```
Claude Code
  └─ MCP ツール呼び出し
       └─ players.pokemon-card.com の内部API を直接取得
            └─ 結果を整形して返す
```

JavaScript SPA のため Playwright（ヘッドレス Chromium）で初回ページロードし、内部 API エンドポイント (`/event_search`) を特定。以降は API を直接叩いています。

## アンインストール

```bash
claude mcp remove pokemon-events
```
