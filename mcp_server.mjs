#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { chromium } from "playwright";

// ---- 都道府県コード ----
const PREFECTURE_CODES = {
  北海道:"1", 青森:"2", 岩手:"3", 宮城:"4", 秋田:"5",
  山形:"6", 福島:"7", 茨城:"8", 栃木:"9", 群馬:"10",
  埼玉:"11", 千葉:"12", 東京:"13", 神奈川:"14", 新潟:"15",
  富山:"16", 石川:"17", 福井:"18", 山梨:"19", 長野:"20",
  岐阜:"21", 静岡:"22", 愛知:"23", 三重:"24", 滋賀:"25",
  京都:"26", 大阪:"27", 兵庫:"28", 奈良:"29", 和歌山:"30",
  鳥取:"31", 島根:"32", 岡山:"33", 広島:"34", 山口:"35",
  徳島:"36", 香川:"37", 愛媛:"38", 高知:"39", 福岡:"40",
  佐賀:"41", 長崎:"42", 熊本:"43", 大分:"44", 宮崎:"45",
  鹿児島:"46", 沖縄:"47",
};

const BASE_URL = "https://players.pokemon-card.com";
const DAYS_JP = ["日","月","火","水","木","金","土"];

// ---- 祝日判定（内閣府 2025-2027年）----
const HOLIDAYS = new Set([
  // 2025
  "2025-01-01","2025-01-13","2025-02-11","2025-02-23","2025-02-24",
  "2025-03-20","2025-04-29","2025-05-03","2025-05-04","2025-05-05","2025-05-06",
  "2025-07-21","2025-08-11","2025-09-15","2025-09-23","2025-10-13",
  "2025-11-03","2025-11-23","2025-11-24","2025-12-23",
  // 2026
  "2026-01-01","2026-01-12","2026-02-11","2026-02-23","2026-03-20",
  "2026-04-29","2026-05-03","2026-05-04","2026-05-05","2026-05-06",
  "2026-07-20","2026-08-11","2026-09-21","2026-09-22","2026-09-23",
  "2026-10-12","2026-11-03","2026-11-23",
  // 2027
  "2027-01-01","2027-01-11","2027-02-11","2027-02-23","2027-03-21",
  "2027-04-29","2027-05-03","2027-05-04","2027-05-05",
  "2027-07-19","2027-08-11","2027-09-20","2027-09-23",
  "2027-10-11","2027-11-03","2027-11-23",
]);

function isWeekendOrHoliday(dateStr) {
  const d = new Date(dateStr);
  const dow = d.getDay(); // 0=Sun, 6=Sat
  return dow === 0 || dow === 6 || HOLIDAYS.has(dateStr);
}

function getWeekendDates(dateFrom, dateTo) {
  const result = [];
  const cur = new Date(dateFrom);
  const end = new Date(dateTo);
  while (cur <= end) {
    const ds = cur.toISOString().slice(0, 10);
    if (isWeekendOrHoliday(ds)) {
      result.push({
        date: ds,
        day: DAYS_JP[cur.getDay()],
        is_holiday: HOLIDAYS.has(ds),
      });
    }
    cur.setDate(cur.getDate() + 1);
  }
  return result;
}

// ---- Playwright スクレイパー ----
const PAGE_SIZE = 20;
const MAX_PAGES = 15;

async function scrapeEvents({ prefecture, city, dateFrom, dateTo, eventName } = {}) {
  // カンマ・読点区切りで複数都道府県をサポート（例: "東京,神奈川"）
  const prefList = prefecture
    ? prefecture.split(/[,、]/).map(p => p.trim()).filter(Boolean)
    : [null];

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    locale: "ja-JP",
  });

  const seenKeys = new Set();
  const allEvents = [];

  for (const pref of prefList) {
    const prefCode = pref
      ? (PREFECTURE_CODES[pref] ?? (String(pref).match(/^\d+$/) ? pref : null))
      : null;

    const baseParams = new URLSearchParams({ order: "1" });
    if (eventName) baseParams.set("keyword", eventName);
    if (prefCode) baseParams.set("prefecture", prefCode);

    for (let pageNum = 0; pageNum < MAX_PAGES; pageNum++) {
      const offset = pageNum * PAGE_SIZE;
      const apiResponses = [];

      const page = await context.newPage();
      page.on("response", async (response) => {
        if (response.status() !== 200) return;
        const ct = response.headers()["content-type"] || "";
        if (!ct.includes("json")) return;
        try {
          const data = await response.json();
          apiResponses.push({ url: response.url(), data });
        } catch {}
      });

      const params = new URLSearchParams(baseParams);
      params.set("offset", String(offset));
      const targetUrl = `${BASE_URL}/event/search?${params}`;

      try {
        await page.goto(targetUrl, { waitUntil: "networkidle", timeout: 20000 });
        await page.waitForTimeout(2000);
      } catch (e) {
        console.error(`[scraper] page load error (offset=${offset}):`, e.message);
        await page.close();
        break;
      }

      let pageEvents = [];
      for (const { data } of apiResponses) {
        const extracted = extractFromData(data);
        if (extracted.length > pageEvents.length) pageEvents = extracted;
      }
      if (pageEvents.length === 0) {
        pageEvents = await extractFromDom(page);
      }
      await page.close();

      const newEvents = pageEvents.filter(e => {
        const key = e.url || e.id || (e.name + e.date);
        if (!key || seenKeys.has(key)) return false;
        seenKeys.add(key);
        return true;
      });

      if (newEvents.length === 0) break;
      allEvents.push(...newEvents);

      // 取得済みの最新日が dateTo を超えていたら打ち切り
      if (dateTo) {
        const latest = newEvents.map(e => (e.date ?? "").slice(0, 10)).filter(Boolean).sort().at(-1) ?? "";
        if (latest && latest > dateTo) break;
      }
    }
  }

  await browser.close();

  return filterEvents(allEvents, dateFrom, dateTo, eventName, city);
}

function extractFromData(data) {
  if (Array.isArray(data)) {
    return data.flatMap(item =>
      typeof item === "object" && item ? [parseEvent(item)].filter(Boolean) : []
    );
  }
  if (data && typeof data === "object") {
    // APIレスポンスは {"event": [...]} 形式なので event キーを優先
    if (Array.isArray(data.event)) {
      const results = extractFromData(data.event);
      if (results.length > 0) return results;
    }
    let best = [];
    for (const value of Object.values(data)) {
      if (!Array.isArray(value)) continue;
      const extracted = extractFromData(value);
      if (extracted.length > best.length) best = extracted;
    }
    return best;
  }
  return [];
}

function parseEvent(d) {
  const id = d.id ?? d.event_id ?? d.eventId ?? d.event_schedule_id ?? d.scheduleId ?? null;
  const name = d.event_title ?? d.name ?? d.title ?? d.event_name ?? d.eventName ?? d.league_name ?? "";

  // event_date_params is "YYYYMMDD", event_date is "MM/DD" — prefer params form
  let date = "";
  const raw = d.event_date_params ?? d.date ?? d.start_date ?? d.startDate ?? d.event_date ?? d.held_date ?? d.schedule_date ?? "";
  const s = raw.toString();
  if (/^\d{8}$/.test(s)) {
    date = `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
  } else {
    date = s.slice(0, 10);
  }

  const venue = d.shop_name ?? d.shopName ?? d.venue ?? d.place ?? d.location ?? "";
  const address = d.address ?? "";
  const prefecture = (d.prefecture_name ?? d.prefecture ?? d.pref ?? d.area ?? "").toString();
  const startTime = d.event_started_at ?? d.started_at ?? "";
  const endTime = d.event_ended_at ?? d.ended_at ?? "";
  if (!id && !name) return null;
  return {
    id: id ? String(id) : "",
    name: String(name),
    date,
    start_time: String(startTime),
    end_time: String(endTime),
    shop_name: String(venue),
    address: String(address),
    prefecture,
    url: d.url ?? (d.event_holding_id && d.shop_id && d.event_date_params && d.date_id
      ? `${BASE_URL}/event/detail/${d.event_holding_id}/1/${d.shop_id}/${d.event_date_params}/${d.date_id}`
      : ""),
  };
}

async function extractFromDom(page) {
  return page.evaluate((base) => {
    const events = [];
    const seen = new Set();
    const links = document.querySelectorAll('a[href*="/event/search/"], a[href*="/event/detail/"]');
    links.forEach(link => {
      const href = link.href;
      if (!href || seen.has(href)) return;
      seen.add(href);
      const container = link.closest("li, article, [class*='card'], [class*='Card'], [class*='item'], [class*='Item']") || link.parentElement;
      const getText = sel => container?.querySelector(sel)?.textContent?.trim() ?? "";
      events.push({
        id: "", name: getText("h2, h3, h4, [class*='title'], [class*='name'], [class*='Title']") || link.textContent?.trim() || "",
        date: getText("time, [class*='date'], [class*='Date'], [class*='day']"),
        venue: getText("[class*='venue'], [class*='shop'], [class*='place'], [class*='Store']"),
        prefecture: getText("[class*='pref'], [class*='region'], [class*='area']"),
        url: href,
      });
    });
    return events;
  }, BASE_URL);
}

function filterEvents(events, dateFrom, dateTo, keyword, city) {
  return events.filter(e => {
    const d = (e.date ?? "").slice(0, 10);
    if (dateFrom && d && d < dateFrom) return false;
    if (dateTo && d && d > dateTo) return false;
    if (keyword) {
      const kw = keyword.toLowerCase();
      if (!e.name?.toLowerCase().includes(kw) && !e.shop_name?.toLowerCase().includes(kw)) return false;
    }
    if (city) {
      // カンマ区切りで複数市区町村を指定可 — いずれかに一致すれば通す
      const cityList = city.split(/[,、]/).map(c => c.trim()).filter(Boolean);
      const searchable = `${e.address ?? ""}${e.shop_name ?? ""}`;
      if (!cityList.some(c => searchable.includes(c))) return false;
    }
    return true;
  });
}

function formatEvents(events) {
  if (events.length === 0) {
    return "イベントが見つかりませんでした。\n\n試してみてください：\n- 地域を変える（例: 東京→神奈川）\n- 日付範囲を広げる\n- キーワードを外す";
  }
  const lines = [`**${events.length} 件のイベントが見つかりました**\n`];
  for (const [i, e] of events.entries()) {
    let line = `${i + 1}. **${e.name || "（名称不明）"}**`;
    const timeStr = e.start_time
      ? (e.end_time ? `${e.start_time}〜${e.end_time}` : e.start_time)
      : "";
    const meta = [
      e.date                                   && `📅 ${e.date}${timeStr ? " " + timeStr : ""}`,
      e.shop_name                              && `🏪 ${e.shop_name}`,
      e.address                                && `📍 ${e.address}`,
      (!e.address && !e.shop_name && e.prefecture) && `🗾 ${e.prefecture}`,
    ].filter(Boolean);
    if (meta.length) line += `\n   ${meta.join("\n   ")}`;
    if (e.url) line += `\n   ${e.url}`;
    lines.push(line);
  }
  return lines.join("\n");
}

// ---- MCP サーバー ----
const server = new McpServer({
  name: "pokemon-event-finder",
  version: "1.0.0",
});

server.tool(
  "search_pokemon_events",
  "players.pokemon-card.com でポケモンカードゲームのイベントを検索する。都道府県・市区町村・日付範囲・イベント名・土日祝フィルターを指定可能。結果はイベント名・日付・会場・URLの一覧で返す。",
  {
    prefecture:    z.string().optional().describe("都道府県名（例: 東京, 大阪）。カンマ区切りで複数指定可（例: 東京,神奈川）"),
    city:          z.string().optional().describe("市区町村名。カンマ区切りで複数指定可（例: 横浜,川崎,町田）。prefectureで広く取ってからここで絞り込む"),
    date_from:     z.string().optional().describe("開始日 YYYY-MM-DD形式"),
    date_to:       z.string().optional().describe("終了日 YYYY-MM-DD形式"),
    event_name:    z.string().optional().describe("イベント名キーワード（例: シティリーグ）"),
    weekends_only: z.boolean().optional().describe("土日祝のみに絞り込む場合は true"),
  },
  async ({ prefecture, city, date_from, date_to, event_name, weekends_only }) => {
    try {
      let events = await scrapeEvents({
        prefecture,
        city,
        dateFrom: date_from,
        dateTo: date_to,
        eventName: event_name,
      });

      if (weekends_only) {
        const today = new Date().toISOString().slice(0, 10);
        const df = date_from ?? today;
        const dt = date_to ?? (() => { const d = new Date(); d.setDate(d.getDate() + 60); return d.toISOString().slice(0, 10); })();
        const weekendSet = new Set(getWeekendDates(df, dt).map(d => d.date));
        events = events.filter(e => weekendSet.has((e.date ?? "").slice(0, 10)));
      }

      return { content: [{ type: "text", text: formatEvents(events) }] };
    } catch (err) {
      return { content: [{ type: "text", text: `エラー: ${err.message}\n\nPlaywright インストール確認:\n  cd ~/pokemon-event-finder && npm run setup` }] };
    }
  }
);

server.tool(
  "get_weekend_dates",
  "指定期間内の土日祝日の一覧を取得する",
  {
    date_from: z.string().describe("開始日 YYYY-MM-DD"),
    date_to:   z.string().describe("終了日 YYYY-MM-DD"),
  },
  async ({ date_from, date_to }) => {
    const dates = getWeekendDates(date_from, date_to);
    const lines = [`**${dates.length} 日間の土日祝（${date_from} 〜 ${date_to}）**\n`];
    for (const d of dates) {
      lines.push(`- ${d.date} (${d.day}) ${d.is_holiday ? "🎌 祝日" : ""}`);
    }
    return { content: [{ type: "text", text: lines.join("\n") }] };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
