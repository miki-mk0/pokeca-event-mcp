@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "DIR=%CD%"

echo === ポケモンカード イベント検索 MCP セットアップ ===
echo.

where node >nul 2>&1
if errorlevel 1 (
  echo エラー: Node.js が見つかりません。https://nodejs.org からインストールしてください。
  exit /b 1
)

where claude >nul 2>&1
if errorlevel 1 (
  echo エラー: claude コマンドが見つかりません。Claude Code をインストールしてください。
  exit /b 1
)

echo npm パッケージをインストール中...
npm install
if errorlevel 1 exit /b 1

echo Playwright ブラウザをインストール中（初回のみ・約100MB）...
npx playwright install chromium
if errorlevel 1 exit /b 1

echo.
echo Claude Code に MCP サーバーを登録中...
claude mcp add pokemon-events node "%DIR%\mcp_server.mjs"
if errorlevel 1 exit /b 1

echo.
echo === セットアップ完了 ===
echo.
echo Claude Code を再起動後、こんなふうに使えます：
echo   「東京の来月の土日のシティリーグを探して」
echo   「横浜・川崎でエルレイドSAR争奪戦を探して」
echo.
echo 登録確認: claude mcp list
