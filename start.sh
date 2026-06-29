#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "=== ポケモンカード イベント検索 ==="
echo ""

# 仮想環境の作成・有効化
if [ ! -d ".venv" ]; then
  echo "仮想環境を作成中..."
  python3 -m venv .venv
fi
source .venv/bin/activate

# 依存関係インストール
echo "依存関係をインストール中..."
pip install -r requirements.txt -q

# Playwright ブラウザインストール
if ! python3 -c "from playwright.sync_api import sync_playwright; sync_playwright().start().chromium" 2>/dev/null; then
  echo "Playwright のブラウザをインストール中（初回のみ）..."
  playwright install chromium
fi

echo ""
echo "起動しました → http://localhost:8000"
echo "停止: Ctrl+C"
echo ""

uvicorn app:app --host 127.0.0.1 --port 8000 --reload
