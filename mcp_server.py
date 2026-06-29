#!/usr/bin/env python3
"""MCP server: ポケモンカード イベント検索"""
import asyncio
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types
from scraper import scrape_events

try:
    import jpholiday
    HAS_JPHOLIDAY = True
except ImportError:
    HAS_JPHOLIDAY = False

server = Server("pokemon-event-finder")
DAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]


def get_weekend_dates(date_from: str, date_to: str) -> list:
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    result = []
    cur = start
    while cur <= end:
        is_weekend = cur.weekday() >= 5
        is_holiday = HAS_JPHOLIDAY and bool(jpholiday.is_holiday(cur))
        holiday_name = (jpholiday.is_holiday_name(cur) if HAS_JPHOLIDAY else None) or ""
        if is_weekend or is_holiday:
            result.append({
                "date": cur.isoformat(),
                "day": DAYS_JP[cur.weekday()],
                "is_holiday": is_holiday,
                "holiday_name": holiday_name,
            })
        cur += timedelta(days=1)
    return result


def filter_by_weekends(events: list, date_from: str, date_to: str) -> list:
    weekend_set = {d["date"] for d in get_weekend_dates(date_from, date_to)}
    return [e for e in events if e.get("date", "")[:10] in weekend_set]


def format_events(events: list) -> str:
    if not events:
        return (
            "イベントが見つかりませんでした。\n\n"
            "試してみてください：\n"
            "- 地域を変える（例: 東京→神奈川）\n"
            "- 日付範囲を広げる\n"
            "- キーワードを外す"
        )

    lines = [f"**{len(events)} 件のイベントが見つかりました**\n"]
    for i, e in enumerate(events, 1):
        name  = e.get("name")  or "（名称不明）"
        d     = e.get("date")  or ""
        venue = e.get("venue") or ""
        url   = e.get("url")   or ""
        pref  = e.get("prefecture") or ""

        line = f"{i}. **{name}**"
        meta_parts = []
        if d:     meta_parts.append(f"📅 {d}")
        if venue: meta_parts.append(f"📍 {venue}")
        if pref:  meta_parts.append(f"🗾 {pref}")
        if meta_parts:
            line += "\n   " + "  ".join(meta_parts)
        if url:
            line += f"\n   🔗 {url}"
        lines.append(line)

    return "\n".join(lines)


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_pokemon_events",
            description=(
                "players.pokemon-card.com でポケモンカードゲームのイベントを検索する。"
                "都道府県・日付範囲・イベント名・土日祝フィルターを指定可能。"
                "結果はイベント名・日付・会場・URLの一覧で返す。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prefecture": {
                        "type": "string",
                        "description": "都道府県名（例: 東京, 大阪, 神奈川）",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "検索開始日 YYYY-MM-DD形式",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "検索終了日 YYYY-MM-DD形式",
                    },
                    "event_name": {
                        "type": "string",
                        "description": "イベント名キーワード（例: シティリーグ, トレーナーズリーグ）",
                    },
                    "weekends_only": {
                        "type": "boolean",
                        "description": "土日祝のみに絞り込む場合は true",
                    },
                },
            },
        ),
        types.Tool(
            name="get_weekend_dates",
            description="指定期間内の土日祝日の一覧を取得する。イベントの土日祝フィルタリングに使う。",
            inputSchema={
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "開始日 YYYY-MM-DD"},
                    "date_to":   {"type": "string", "description": "終了日 YYYY-MM-DD"},
                },
                "required": ["date_from", "date_to"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    today = date.today().isoformat()

    if name == "search_pokemon_events":
        try:
            events = await scrape_events(
                prefecture=arguments.get("prefecture"),
                date_from=arguments.get("date_from"),
                date_to=arguments.get("date_to"),
                event_name_keyword=arguments.get("event_name"),
            )
            if arguments.get("weekends_only"):
                df = arguments.get("date_from") or today
                dt = arguments.get("date_to") or (
                    date.fromisoformat(today) + timedelta(days=60)
                ).isoformat()
                events = filter_by_weekends(events, df, dt)

            text = format_events(events)
        except RuntimeError as e:
            text = str(e)
        except Exception as e:
            text = (
                f"スクレイピングエラー: {e}\n\n"
                "Playwright が未インストールの場合は以下を実行してください:\n"
                "  cd ~/pokemon-event-finder && source .venv/bin/activate\n"
                "  pip install playwright && playwright install chromium"
            )
        return [types.TextContent(type="text", text=text)]

    if name == "get_weekend_dates":
        try:
            dates = get_weekend_dates(arguments["date_from"], arguments["date_to"])
            lines = [f"**{len(dates)} 日間の土日祝（{arguments['date_from']} 〜 {arguments['date_to']}）**\n"]
            for d in dates:
                flag = f"🎌 {d['holiday_name']}" if d["is_holiday"] else ""
                lines.append(f"- {d['date']} ({d['day']}) {flag}")
            text = "\n".join(lines)
        except Exception as e:
            text = f"エラー: {e}"
        return [types.TextContent(type="text", text=text)]

    return [types.TextContent(type="text", text=f"不明なツール: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
