#!/bin/bash
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"

echo "=== ポケモンカード イベント検索 MCP セットアップ ==="
echo ""

# Node.js チェック
if ! command -v node &>/dev/null; then
  echo "エラー: Node.js が見つかりません。https://nodejs.org からインストールしてください。"
  exit 1
fi

# claude CLI チェック
if ! command -v claude &>/dev/null; then
  echo "エラー: claude コマンドが見つかりません。Claude Code をインストールしてください。"
  exit 1
fi

echo "npm パッケージをインストール中..."
npm install

echo "Playwright ブラウザをインストール中（初回のみ・約100MB）..."
npx playwright install chromium

echo ""
echo "Claude Code に MCP サーバーを登録中..."
claude mcp add pokemon-events node "${DIR}/mcp_server.mjs"

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "Claude Code を再起動後、こんなふうに使えます："
echo "  「東京の来月の土日のシティリーグを探して」"
echo "  「横浜・川崎でエルレイドSAR争奪戦を探して」"
echo ""
echo "登録確認: claude mcp list"
