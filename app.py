from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import anthropic
import json
from datetime import date, timedelta
from typing import List, Optional

try:
    import jpholiday
    HAS_JPHOLIDAY = True
except ImportError:
    HAS_JPHOLIDAY = False

from scraper import scrape_events

BASE_DIR = Path(__file__).parent
app = FastAPI(title="ポケモンカード イベント検索")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

claude = anthropic.Anthropic()

TOOLS = [
    {
        "name": "search_events",
        "description": (
            "players.pokemon-card.com でポケモンカードゲームのイベントを検索する。"
            "指定した都道府県・期間・イベント名のイベント一覧（名前・日付・会場・URL）を返す。"
        ),
        "input_schema": {
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
    },
    {
        "name": "get_weekend_dates",
        "description": "指定期間内の土曜・日曜・祝日の日付一覧を返す",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "開始日 YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "終了日 YYYY-MM-DD"},
            },
            "required": ["date_from", "date_to"],
        },
    },
]

DAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]


def get_weekend_dates(date_from: str, date_to: str) -> List[dict]:
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    result = []
    current = start
    while current <= end:
        is_weekend = current.weekday() >= 5
        is_holiday = HAS_JPHOLIDAY and bool(jpholiday.is_holiday(current))
        holiday_name = (jpholiday.is_holiday_name(current) if HAS_JPHOLIDAY else None) or ""
        if is_weekend or is_holiday:
            result.append({
                "date": current.isoformat(),
                "day": DAYS_JP[current.weekday()],
                "is_holiday": is_holiday,
                "holiday_name": holiday_name,
            })
        current += timedelta(days=1)
    return result


def filter_by_weekends(events: List[dict], date_from: str, date_to: str) -> List[dict]:
    weekend_set = {d["date"] for d in get_weekend_dates(date_from, date_to)}
    return [e for e in events if e.get("date", "")[:10] in weekend_set]


@app.get("/", response_class=HTMLResponse)
async def root():
    return (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    query = body.get("query", "").strip()
    if not query:
        return {"error": "クエリが空です"}

    today = date.today().isoformat()
    events_found: List[dict] = []

    messages = [
        {
            "role": "user",
            "content": (
                f"今日の日付: {today}\n\n"
                f"ユーザーのリクエスト:\n{query}\n\n"
                "search_eventsツールを使って実際にイベントを検索し、"
                "見つかったイベントのURL一覧をわかりやすく整理して返してください。"
            ),
        }
    ]

    system = """あなたはポケモンカードゲームのイベント検索アシスタントです。
ユーザーが指定した地域・日付・イベント種別などの条件でsearch_eventsツールを呼び出し、
実際に取得したイベントのURL一覧を整理して回答してください。

回答のルール:
- 必ずsearch_eventsツールを呼び出して実データを取得する
- 見つかったイベント数を最初に伝える
- イベント名・日付・会場・URLを箇条書きで列挙する
- URLは省略せず完全なものを記載する
- データが取得できなかった場合は理由と代替案を提示する
- 日本語で回答する"""

    for _ in range(6):
        response = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            text = "".join(b.text for b in response.content if hasattr(b, "text"))
            return {"response": text, "events": events_found}

        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if hasattr(b, "text"))
            return {"response": text or "処理できませんでした", "events": events_found}

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            inp = block.input

            if block.name == "search_events":
                try:
                    events = await scrape_events(
                        prefecture=inp.get("prefecture"),
                        date_from=inp.get("date_from"),
                        date_to=inp.get("date_to"),
                        event_name_keyword=inp.get("event_name"),
                    )
                    if inp.get("weekends_only"):
                        df = inp.get("date_from") or today
                        dt = inp.get("date_to") or (
                            date.fromisoformat(today) + timedelta(days=60)
                        ).isoformat()
                        events = filter_by_weekends(events, df, dt)

                    events_found.extend(events)
                    result_content = (
                        json.dumps(events[:50], ensure_ascii=False)
                        if events
                        else "イベントが見つかりませんでした"
                    )
                except Exception as e:
                    result_content = f"スクレイピングエラー: {e}"

            elif block.name == "get_weekend_dates":
                try:
                    dates = get_weekend_dates(inp["date_from"], inp["date_to"])
                    result_content = json.dumps(dates, ensure_ascii=False)
                except Exception as e:
                    result_content = f"エラー: {e}"
            else:
                result_content = "不明なツール"

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_content,
                }
            )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return {"response": "最大試行回数に達しました", "events": events_found}
