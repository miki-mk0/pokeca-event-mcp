import asyncio
import json
from typing import Optional, List, Dict
from datetime import datetime

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

PREFECTURE_CODES: Dict[str, str] = {
    "北海道": "1", "青森": "2", "岩手": "3", "宮城": "4", "秋田": "5",
    "山形": "6", "福島": "7", "茨城": "8", "栃木": "9", "群馬": "10",
    "埼玉": "11", "千葉": "12", "東京": "13", "神奈川": "14", "新潟": "15",
    "富山": "16", "石川": "17", "福井": "18", "山梨": "19", "長野": "20",
    "岐阜": "21", "静岡": "22", "愛知": "23", "三重": "24", "滋賀": "25",
    "京都": "26", "大阪": "27", "兵庫": "28", "奈良": "29", "和歌山": "30",
    "鳥取": "31", "島根": "32", "岡山": "33", "広島": "34", "山口": "35",
    "徳島": "36", "香川": "37", "愛媛": "38", "高知": "39", "福岡": "40",
    "佐賀": "41", "長崎": "42", "熊本": "43", "大分": "44", "宮崎": "45",
    "鹿児島": "46", "沖縄": "47",
}

BASE_URL = "https://players.pokemon-card.com"
EVENT_SEARCH_URL = f"{BASE_URL}/event/search"


async def scrape_events(
    prefecture: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    event_name_keyword: Optional[str] = None,
) -> List[Dict]:
    if not HAS_PLAYWRIGHT:
        raise RuntimeError("Playwrightがインストールされていません。`pip install playwright && playwright install chromium` を実行してください。")

    api_responses: List[Dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ja-JP",
        )
        page = await context.new_page()

        async def handle_response(response):
            url = response.url
            status = response.status
            if status != 200:
                return
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                return
            # Capture anything that looks like event data
            if any(kw in url for kw in ["event", "search", "api", "list"]):
                try:
                    data = await response.json()
                    api_responses.append({"url": url, "data": data})
                except Exception:
                    pass

        page.on("response", handle_response)

        # Build URL
        params = []
        if prefecture:
            code = PREFECTURE_CODES.get(prefecture, prefecture if prefecture.isdigit() else None)
            if code:
                params.append(f"prefecture={code}")
        params.extend(["offset=0", "order=1"])

        target_url = EVENT_SEARCH_URL + ("?" + "&".join(params) if params else "")

        try:
            await page.goto(target_url, wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"[scraper] ページ読み込みエラー: {e}")

        # Try to extract events from intercepted API responses
        events: List[Dict] = []
        for resp in api_responses:
            extracted = _extract_from_data(resp["data"])
            if extracted:
                events.extend(extracted)
                break

        # Fallback: DOM extraction
        if not events:
            events = await _extract_from_dom(page)

        await browser.close()

    # Apply client-side filters
    if date_from or date_to or event_name_keyword:
        events = _filter_events(events, date_from, date_to, event_name_keyword)

    return events


def _extract_from_data(data) -> List[Dict]:
    if isinstance(data, list):
        results = []
        for item in data:
            if isinstance(item, dict):
                e = _parse_event(item)
                if e:
                    results.append(e)
        return results

    if isinstance(data, dict):
        # Look for the largest nested list that looks like events
        best: List[Dict] = []
        for value in data.values():
            if isinstance(value, list) and len(value) > len(best):
                extracted = _extract_from_data(value)
                if extracted:
                    best = extracted
        return best

    return []


def _parse_event(d: dict) -> Optional[Dict]:
    event_id = (
        d.get("id") or d.get("event_id") or d.get("eventId")
        or d.get("event_schedule_id") or d.get("scheduleId")
    )
    name = (
        d.get("name") or d.get("title") or d.get("event_name")
        or d.get("eventName") or d.get("event_title") or d.get("league_name") or ""
    )
    date_val = (
        d.get("date") or d.get("start_date") or d.get("startDate")
        or d.get("event_date") or d.get("held_date") or d.get("schedule_date") or ""
    )
    venue = (
        d.get("venue") or d.get("shop_name") or d.get("shopName")
        or d.get("place") or d.get("location") or ""
    )
    prefecture = d.get("prefecture") or d.get("pref") or d.get("area") or ""

    if not (event_id or name):
        return None

    url = (
        d.get("url")
        or (f"{BASE_URL}/event/search/{event_id}/list" if event_id else "")
    )

    return {
        "id": str(event_id) if event_id else "",
        "name": str(name),
        "date": str(date_val)[:10] if date_val else "",
        "venue": str(venue),
        "prefecture": str(prefecture),
        "url": url,
    }


async def _extract_from_dom(page) -> List[Dict]:
    return await page.evaluate("""() => {
        const events = [];
        const seen = new Set();

        // Try links pointing to event detail pages
        const links = document.querySelectorAll('a[href*="/event/search/"], a[href*="/event/detail/"]');
        links.forEach(link => {
            const href = link.href;
            if (!href || seen.has(href)) return;
            seen.add(href);

            // Walk up to find a container
            const container = link.closest('li, article, [class*="card"], [class*="Card"], [class*="item"], [class*="Item"]') || link.parentElement;
            const getText = sel => container?.querySelector(sel)?.textContent?.trim() || '';

            events.push({
                id: '',
                name: getText('h2, h3, h4, [class*="title"], [class*="name"], [class*="Title"]')
                      || link.textContent?.trim() || '',
                date: getText('time, [class*="date"], [class*="Date"], [class*="day"]'),
                venue: getText('[class*="venue"], [class*="shop"], [class*="place"], [class*="Store"]'),
                prefecture: getText('[class*="pref"], [class*="region"], [class*="area"]'),
                url: href,
            });
        });

        return events;
    }""")


def _filter_events(
    events: List[Dict],
    date_from: Optional[str],
    date_to: Optional[str],
    keyword: Optional[str],
) -> List[Dict]:
    result = []
    for e in events:
        raw_date = e.get("date", "")[:10]
        if date_from and raw_date and raw_date < date_from:
            continue
        if date_to and raw_date and raw_date > date_to:
            continue
        if keyword:
            kw = keyword.lower()
            if kw not in e.get("name", "").lower() and kw not in e.get("venue", "").lower():
                continue
        result.append(e)
    return result
