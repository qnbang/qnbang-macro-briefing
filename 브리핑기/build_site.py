# -*- coding: utf-8 -*-
"""
정적 대시보드 생성기 (전달 레이어)
- DB(market_data·daily_briefings·scenarios·scenario_logs)를 읽어
  디자인 시안 v2 그대로의 정적 사이트를 site/ 에 렌더한다.
- 숫자 원칙: 지표 카드의 market 종류는 market_data에서 '값·시점·출처·등락'을 그대로 가져온다
  (LLM이 만든 숫자가 끼어들 자리 없음). cited 종류는 본문에 명시된 Tier1 출처를 함께 보여준다.
- 산출물: site/index.html(최신), site/archive/<id>.html(과거본), site/data.json(원자료).
"""
import os
import re
import json
import html
import sqlite3
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB_PATH = os.path.join(HERE, "macro_briefing.db")
SITE = os.path.join(ROOT, "site")

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
PERIOD_KR = {"daily": "데일리 시그널", "weekly": "위클리 플로우", "monthly": "먼슬리 테마"}


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def latest_market(c):
    """지표별 최신 1건을 {code: row} 로."""
    rows = c.execute(
        """SELECT m.* FROM market_data m
           JOIN (SELECT indicator, MAX(id) mx FROM market_data GROUP BY indicator) t
             ON m.id = t.mx"""
    ).fetchall()
    return {r["indicator"]: r for r in rows}


def fmt_date_kr(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{d.year}년 {d.month}월 {d.day}일 ({WEEKDAY_KR[d.weekday()]})"


def fmt_value(code, value, unit):
    """지표 단위에 맞춘 표기."""
    if unit == "원":
        return f"{value:,.0f}원"
    if unit == "%":
        return f"{value:.2f}%"
    if unit in ("USD/배럴", "USD/온스"):
        return f"${value:,.2f}"
    return f"{value:,.2f}"


def chg_html(change):
    """전일대비 칩(한국 증시 색: 상승=빨강/up, 하락=파랑/down)."""
    if change is None:
        return ""
    cls = "up" if change >= 0 else "down"
    arrow = "▲" if change >= 0 else "▼"
    return f'<span class="chg {cls}">{arrow} {abs(change):.2f}%</span>'


# ── 핵심 지표 카드 ────────────────────────────────────────────────
def render_indicators(indicators, market):
    cards = []
    for ind in indicators:
        if ind.get("kind") == "market":
            row = market.get(ind["code"])
            if not row:
                continue
            val = fmt_value(ind["code"], row["value"], row["unit"])
            tag = chg_html(row["daily_change"])
            if ind.get("tag"):  # 의미 라벨이 명시되면 우선
                tcls = "up" if (row["daily_change"] or 0) >= 0 else "down"
                tag = f'<span class="chg {tcls}">{esc(ind["tag"])}</span>'
            src = f'<span class="csrc">출처 {esc(row["source"])} · {esc(row["timestamp"])}</span>'
        else:  # cited
            val = esc(ind.get("value", ""))
            tcls = ind.get("tagClass", "up")
            tag = f'<span class="chg {tcls}">{esc(ind.get("tag",""))}</span>' if ind.get("tag") else ""
            src = f'<span class="csrc">출처 {esc(ind.get("source",""))}</span>'
        cards.append(
            f'<div class="ind"><div class="name">{esc(ind["label"])}</div>'
            f'<div class="val">{val} {tag}</div>'
            f'<div class="mean">{esc(ind["mean"])}</div>{src}</div>'
        )
    return '<div class="grid">' + "".join(cards) + "</div>"


def render_views(views):
    out = []
    for v in views:
        out.append(
            f'<div class="view"><span class="badge {esc(v["badgeClass"])}">{esc(v["badge"])}</span>'
            f'<div><div class="vname">{esc(v["name"])} <span class="horizon">{esc(v["horizon"])}</span></div>'
            f'<div class="vwhy">{esc(v["why"])}</div>'
            f'<div class="vhow"><b>어떻게:</b> {v["how"]}</div></div></div>'
        )
    return "".join(out)


def render_flow(flow):
    parts = []
    for i, s in enumerate(flow):
        tagcls = "tag kr" if s.get("kr") else "tag"
        parts.append(
            f'<div class="hstep"><span class="{tagcls}">{esc(s["tag"])}</span>'
            f'<b>{esc(s["title"])}</b><p>{esc(s["desc"])}</p></div>'
        )
        if i < len(flow) - 1:
            parts.append('<div class="harrow">→</div>')
    return '<div class="hflow">' + "".join(parts) + "</div>"


def render_chips(chips):
    out = []
    for ch in chips:
        cls = ch.get("cls", "watch")
        dot = f'<span class="dot">{esc(ch["dot"])}</span>' if ch.get("dot") else ""
        out.append(f'<span class="chip {cls}">{dot}{esc(ch["text"])}</span>')
    return '<div class="chips">' + "".join(out) + "</div>"


# ── 시나리오 현황(성적표 씨앗) ─────────────────────────────────────
STATUS_CLS = {"강화중": "str", "약화중": "weak", "활성": "watch",
              "종료(적중)": "str", "종료(빗나감)": "weak"}
STATUS_DOT = {"강화중": "▲", "약화중": "▼"}


def render_scenarios(c):
    rows = c.execute(
        "SELECT id,title,status,confidence FROM scenarios ORDER BY confidence DESC"
    ).fetchall()
    chips = []
    for r in rows:
        cls = STATUS_CLS.get(r["status"], "watch")
        dot = STATUS_DOT.get(r["status"], "")
        dot_h = f'<span class="dot">{dot}</span>' if dot else ""
        conf = int(round((r["confidence"] or 0) * 100))
        chips.append(
            f'<span class="chip {cls}">{dot_h}{esc(r["title"])} '
            f'<b style="opacity:.7">{esc(r["status"])}·{conf}%</b></span>'
        )
    return '<div class="chips scn">' + "".join(chips) + "</div>"


def render_full_market(market):
    """전체 시세 투명 공개 strip."""
    names = {"KOSPI": "코스피", "KOSDAQ": "코스닥", "SPX": "S&P500", "NDX": "나스닥",
             "VIX": "VIX", "USDKRW": "원/달러", "DXY": "달러지수", "WTI": "WTI유가",
             "GOLD": "금", "US10Y": "미10년물"}
    cells = []
    for code, name in names.items():
        r = market.get(code)
        if not r:
            continue
        cells.append(
            f'<div class="mq"><span class="mqn">{esc(name)}</span>'
            f'<span class="mqv">{fmt_value(code, r["value"], r["unit"])}</span>'
            f'{chg_html(r["daily_change"])}</div>'
        )
    return '<div class="mqgrid">' + "".join(cells) + "</div>"


# ── HTML 셸 ───────────────────────────────────────────────────────
def page(body, title):
    css = CSS
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<style>{css}</style></head><body><div class="wrap">{body}</div></body></html>"""


def build_bot_context(b, market):
    """챗봇이 '오늘 브리핑'으로 답하도록 줄 압축 맥락 텍스트."""
    lines = [f"오늘은 {b.get('date','')} 데일리 브리핑."]
    w = b.get("weather", {})
    if w:
        lines.append(f"시장 날씨: {w.get('state','')} — {w.get('desc','')}")
    if b.get("title"):
        lines.append(f"핵심: {b['title']}")
    # 핵심 시세(검증된 숫자만)
    names = {"USDKRW": "원/달러", "WTI": "WTI유가", "KOSPI": "코스피", "US10Y": "미10년물금리",
             "GOLD": "금", "DXY": "달러지수", "VIX": "VIX", "SPX": "S&P500"}
    quotes = []
    for code, nm in names.items():
        r = market.get(code)
        if r:
            chg = f"({r['daily_change']:+.2f}%)" if r["daily_change"] is not None else ""
            quotes.append(f"{nm} {fmt_value(code, r['value'], r['unit'])}{chg}")
    if quotes:
        lines.append("오늘 시세: " + ", ".join(quotes))
    # 투자 관점
    st = b.get("stance", {})
    if st:
        lines.append(f"오늘의 관점(한줄): {st.get('title','')}")
    if b.get("increase"):
        lines.append("비중 늘릴 것: " + ", ".join(b["increase"]))
    if b.get("decrease"):
        lines.append("줄이거나 미룰 것: " + ", ".join(b["decrease"]))
    # 흐름
    if b.get("flow"):
        chain = " → ".join(f"{s['title']}" for s in b["flow"])
        lines.append("오늘의 흐름: " + chain)
    # 자산별 관점
    for v in b.get("views", []):
        why = re.sub(r"<[^>]+>", "", v.get("why", ""))
        how = re.sub(r"<[^>]+>", "", v.get("how", ""))
        lines.append(f"[{v.get('name','')} · {v.get('badge','')}] {why} {how}")
    return "\n".join(lines)


def render_briefing(c, brow, market, is_archive=False, with_chat=False):
    b = json.loads(brow["content"])
    period = b.get("period", "daily")
    date_str = brow["date"]
    plabel = PERIOD_KR.get(period, period)
    head = (
        '<div class="top"><div class="brand">📈 매크로 브리핑</div>'
        f'<div class="date">{esc(fmt_date_kr(date_str))} · {esc(plabel)}</div></div>'
    )
    w = b["weather"]
    weather = (
        f'<div class="weather"><div class="emoji">{esc(w["emoji"])}</div><div>'
        '<div class="label">오늘의 시장 날씨</div>'
        f'<div class="state">{esc(w["state"])}</div>'
        f'<div class="desc">{esc(w["desc"])}</div></div></div>'
    )
    plain = f'<div class="plain"><h3>🗣️ 쉽게 말하면</h3><p>{b["plain"]}</p></div>'

    st = b["stance"]
    stance = (
        '<div class="sec">🧭 지금, 어떻게 투자할까 <small>참고용 의견 · 종목 추천 아님</small></div>'
        f'<div class="stance"><div class="k">한 줄 결론</div>'
        f'<div class="t">{esc(st["title"])}</div><div class="s">{esc(st["sub"])}</div></div>'
    )
    inc = "".join(f"<li>{esc(x)}</li>" for x in b["increase"])
    dec = "".join(f"<li>{esc(x)}</li>" for x in b["decrease"])
    twocol = (
        f'<div class="twocol"><div class="box up-b"><h4>⬆️ 비중 늘려 둘 것</h4>{inc}</div>'
        f'<div class="box dn-b"><h4>⬇️ 줄이거나 미룰 것</h4>{dec}</div></div>'
    )
    views = render_views(b["views"])

    ind_sec = (
        '<div class="sec">📊 핵심 지표 <small>숫자 옆에 \'무슨 뜻인지\' 한 줄</small></div>'
        + render_indicators(b["indicators"], market)
    )
    full_mkt = (
        '<div class="sec">📈 전체 시세 <small>자동수집 · 투명 공개</small></div>'
        + render_full_market(market)
    )
    flow_sec = (
        '<div class="sec">🔗 오늘의 흐름 <small>→ 옆으로 밀어보세요 · 사건이 한국까지 오는 길</small></div>'
        + render_flow(b["flow"])
    )

    weekly = ""
    if b.get("weekly"):
        wk = b["weekly"]
        weekly = (
            '<div class="sec">📅 이번 주 흐름 <small>무게중심이 어디로 옮겨갔나</small></div>'
            '<div class="shift">'
            f'<div class="from"><div class="k">지난주까지 주인공</div><div class="v">{esc(wk["from"])}</div></div>'
            '<div class="mid">➜</div>'
            f'<div class="to"><div class="k">이번 주 주인공</div><div class="v">{esc(wk["to"])}</div></div></div>'
            '<ul class="bullets">' + "".join(f'<li>{x}</li>' for x in wk["bullets"]) + "</ul>"
            + render_chips(wk["chips"])
        )

    monthly = ""
    if b.get("monthly"):
        mo = b["monthly"]
        monthly = (
            '<div class="sec">🗓️ 이번 달 테마 <small>올해 큰 그림의 한 장면</small></div>'
            f'<div class="theme"><div class="tt">{esc(mo["title"])}</div><p>{mo["body"]}</p>'
            + render_chips(mo["chips"]) + "</div>"
        )

    scn_sec = (
        '<div class="sec">🎯 시나리오 현황 <small>오늘 이벤트로 강화/약화된 가설 · 적중 추적</small></div>'
        + render_scenarios(c)
    )

    terms = "".join(
        f'<div class="term"><b>{esc(t["term"])}</b> <span>— {esc(t["desc"])}</span></div>'
        for t in b.get("terms", [])
    )
    terms_block = f'<details><summary>📖 어려운 말 풀이 (펼치기)</summary>{terms}</details>' if terms else ""

    src = f'<div class="src">📌 {esc(b.get("sources",""))}</div>'
    disc = (
        '<div class="disc">본 자료는 거시 흐름 학습·관찰용이며 투자 자문이나 매매 권유가 아닙니다.<br>'
        '모든 수치는 출처를 명시했고, 검증 불가 수치는 제외했습니다. 투자 판단과 책임은 본인에게 있습니다.</div>'
    )
    nav = '<div class="nav"><a href="/">← 최신 브리핑</a></div>' if is_archive else \
          '<div class="nav"><a href="/archive">📚 지난 브리핑 보기</a></div>'

    body = (head + weather + plain + stance + twocol + views + ind_sec + full_mkt
            + flow_sec + weekly + monthly + scn_sec + terms_block + src + nav + disc)
    if with_chat:
        body += CHAT_WIDGET
    return page(body, f"매크로 브리핑 — {date_str}")


def render_archive_index(c):
    rows = c.execute(
        "SELECT id,date,content FROM daily_briefings ORDER BY date DESC, id DESC"
    ).fetchall()
    items = []
    for r in rows:
        b = json.loads(r["content"])
        plabel = PERIOD_KR.get(b.get("period", "daily"), "")
        items.append(
            f'<a class="arow" href="/archive/{esc(r["id"])}">'
            f'<span class="ad">{esc(fmt_date_kr(r["date"]))}</span>'
            f'<span class="ap">{esc(plabel)}</span>'
            f'<span class="at">{esc(b.get("title",""))}</span></a>'
        )
    body = ('<div class="top"><div class="brand">📚 지난 브리핑</div>'
            '<div class="date"><a href="/">← 최신</a></div></div>'
            '<div class="arclist">' + "".join(items) + "</div>")
    return page(body, "매크로 브리핑 — 아카이브")


def build():
    c = conn()
    market = latest_market(c)
    os.makedirs(os.path.join(SITE, "archive"), exist_ok=True)

    briefings = c.execute(
        "SELECT * FROM daily_briefings ORDER BY date DESC, id DESC"
    ).fetchall()
    if not briefings:
        print("브리핑이 없습니다. 먼저 생성하세요.")
        return

    # 최신 → index.html (+ 챗봇 위젯)
    latest = briefings[0]
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_briefing(c, latest, market, with_chat=True))

    # 챗봇용 오늘 맥락
    latest_b = json.loads(latest["content"])
    with open(os.path.join(SITE, "bot-context.json"), "w", encoding="utf-8") as f:
        json.dump({"date": latest["date"], "context": build_bot_context(latest_b, market)},
                  f, ensure_ascii=False, indent=2)

    # 전체 → archive/<id>.html
    for br in briefings:
        with open(os.path.join(SITE, "archive", f"{br['id']}.html"), "w", encoding="utf-8") as f:
            f.write(render_briefing(c, br, market, is_archive=True))

    # 아카이브 인덱스
    with open(os.path.join(SITE, "archive.html"), "w", encoding="utf-8") as f:
        f.write(render_archive_index(c))

    # 원자료 JSON(투명·API용)
    data = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "market": {k: dict(v) for k, v in market.items()},
        "latest_briefing_id": latest["id"],
    }
    with open(os.path.join(SITE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    c.close()
    print(f"빌드 완료 → {SITE}  (브리핑 {len(briefings)}편)")


CSS = """
:root{--up:#e0392b;--down:#1f6fd6;--ink:#1a1d21;--sub:#6b7280;--line:#e9ebef;--bg:#f4f6f9;--card:#fff}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"Apple SD Gothic Neo","Pretendard","Malgun Gothic",sans-serif;background:var(--bg);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:18px 16px 60px}
.top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px}
.brand{font-weight:800;font-size:18px;letter-spacing:-.3px}
.date{color:var(--sub);font-size:13px}
.date a,.nav a{color:var(--down);text-decoration:none;font-weight:700}
.weather{background:linear-gradient(135deg,#374151,#1f2937);color:#fff;border-radius:20px;padding:20px 22px;display:flex;align-items:center;gap:18px;box-shadow:0 8px 24px rgba(31,41,55,.18)}
.weather .emoji{font-size:52px;line-height:1}
.weather .label{font-size:12px;opacity:.75;letter-spacing:2px}
.weather .state{font-size:24px;font-weight:800;margin:2px 0}
.weather .desc{font-size:13.5px;opacity:.9}
.plain{background:#fff7e6;border:1px solid #ffe2a8;border-radius:16px;padding:15px 18px;margin-top:13px}
.plain h3{font-size:13px;color:#b7791f;margin-bottom:5px;font-weight:700}
.plain p{font-size:15px;font-weight:500}
.sec{margin:26px 0 12px;font-size:15px;font-weight:800;color:#374151;letter-spacing:-.2px}
.sec small{font-weight:500;color:var(--sub);margin-left:6px;font-size:12.5px}
.stance{background:linear-gradient(135deg,#1e3a5f,#2563eb);color:#fff;border-radius:18px;padding:18px 20px;box-shadow:0 6px 20px rgba(37,99,235,.22)}
.stance .k{font-size:12px;opacity:.8;letter-spacing:1px}
.stance .t{font-size:18px;font-weight:800;margin:4px 0 2px;line-height:1.4}
.stance .s{font-size:13.5px;opacity:.92}
.twocol{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:11px}
.box{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px 15px}
.box.up-b{border-top:3px solid var(--up)}.box.dn-b{border-top:3px solid var(--down)}
.box h4{font-size:13px;margin-bottom:7px}.box.up-b h4{color:var(--up)}.box.dn-b h4{color:var(--down)}
.box li{font-size:12.5px;color:#4b5563;list-style:none;padding:3px 0 3px 14px;position:relative}
.box li:before{content:"•";position:absolute;left:2px;color:#cbd1da}
.view{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px 15px;display:flex;align-items:flex-start;gap:12px;margin-top:9px}
.badge{flex-shrink:0;font-size:11.5px;font-weight:800;padding:4px 10px;border-radius:20px;margin-top:2px;white-space:nowrap}
.b-good{background:#dcfce7;color:#15803d}.b-warn{background:#fef3c7;color:#b45309}.b-bad{background:#fee2e2;color:#b91c1c}.b-neu{background:#f1f5f9;color:#475569}
.view .vname{font-size:14.5px;font-weight:700;display:flex;align-items:center;gap:7px}
.view .horizon{font-size:10.5px;font-weight:700;color:#64748b;background:#f1f5f9;border-radius:5px;padding:1px 6px}
.view .vwhy{font-size:12.5px;color:#5b6473;margin-top:3px}
.view .vhow{font-size:12px;color:#475569;margin-top:5px;background:#f8fafc;border-radius:8px;padding:6px 9px}
.view .vhow b{color:var(--ink)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.ind{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px 14px}
.ind .name{font-size:12.5px;color:var(--sub)}
.ind .val{font-size:20px;font-weight:800;margin:2px 0;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.chg{font-size:11.5px;font-weight:700;padding:1px 7px;border-radius:20px}
.up{color:var(--up)}.down{color:var(--down)}
.chg.up{background:#fde8e6;color:var(--up)}.chg.down{background:#e6f0fb;color:var(--down)}
.ind .mean{font-size:12px;color:#4b5563;margin-top:6px;border-top:1px dashed var(--line);padding-top:7px}
.csrc{display:block;font-size:10.5px;color:#aab1bd;margin-top:5px}
.mqgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px}
.mq{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:9px 11px;display:flex;flex-direction:column;gap:2px}
.mqn{font-size:11.5px;color:var(--sub)}.mqv{font-size:15px;font-weight:800}
.hflow{display:flex;gap:0;overflow-x:auto;padding:2px 2px 10px;-webkit-overflow-scrolling:touch}
.hstep{flex:0 0 auto;width:158px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px}
.hstep .tag{font-size:10.5px;font-weight:800;color:#fff;background:#374151;border-radius:6px;padding:1px 7px}
.hstep .tag.kr{background:var(--up)}
.hstep b{font-size:14px;display:block;margin-top:7px}
.hstep p{font-size:11.5px;color:#6b7280;margin-top:3px}
.harrow{flex:0 0 auto;display:flex;align-items:center;color:#cbd1da;font-size:20px;padding:0 5px}
.shift{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px;display:flex;align-items:center;gap:12px;justify-content:center;flex-wrap:wrap}
.shift .from,.shift .to{text-align:center;flex:1;min-width:120px}
.shift .k{font-size:11px;color:var(--sub)}
.shift .v{font-size:14.5px;font-weight:800;margin-top:3px}
.shift .from .v{color:#94a3b8}.shift .to .v{color:var(--up)}
.shift .mid{font-size:24px;color:#cbd1da}
.bullets{margin-top:10px}
.bullets li{font-size:13px;color:#4b5563;list-style:none;padding:4px 0 4px 16px;position:relative}
.bullets li:before{content:"→";position:absolute;left:0;color:#cbd1da}
.chips{display:flex;gap:7px;flex-wrap:wrap;margin-top:11px}
.chips.scn .chip{font-size:11.5px}
.chip{font-size:12px;font-weight:700;padding:5px 11px;border-radius:20px;border:1px solid var(--line);background:#fff}
.chip .dot{font-weight:800;margin-right:3px}
.chip.str{color:var(--up);border-color:#f6cdc9}.chip.str .dot{color:var(--up)}
.chip.weak{color:var(--down);border-color:#cfe0f5}.chip.weak .dot{color:var(--down)}
.chip.watch{color:#b45309;border-color:#fde68a}
.theme{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.theme .tt{font-size:16px;font-weight:800;margin-bottom:7px}
.theme p{font-size:13.5px;color:#4b5563}
details{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:4px 16px;margin-top:12px}
summary{font-size:13.5px;font-weight:700;cursor:pointer;padding:10px 0;color:#374151}
.term{padding:8px 0;border-top:1px dashed var(--line);font-size:13px}
.term b{color:var(--ink)}.term span{color:#6b7280}
.nav{margin-top:20px;text-align:center;font-size:13.5px}
.src{margin-top:18px;font-size:11.5px;color:#9ca3af}
.disc{margin-top:14px;font-size:11.5px;color:#9ca3af;text-align:center;line-height:1.7}
.arclist{display:flex;flex-direction:column;gap:9px}
.arow{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px;text-decoration:none;color:var(--ink)}
.arow .ad{font-size:12.5px;color:var(--sub);white-space:nowrap}
.arow .ap{font-size:11px;font-weight:800;color:var(--down);background:#eef4fd;border-radius:6px;padding:2px 7px;white-space:nowrap}
.arow .at{font-size:13.5px;font-weight:600}
"""


CHAT_WIDGET = """
<style>
#mbot-fab{position:fixed;right:18px;bottom:18px;z-index:50;width:58px;height:58px;border:none;border-radius:50%;
  background:linear-gradient(135deg,#1e3a5f,#2563eb);color:#fff;font-size:26px;cursor:pointer;
  box-shadow:0 8px 22px rgba(37,99,235,.4);transition:transform .15s}
#mbot-fab:hover{transform:scale(1.06)}
#mbot-fab .badge{position:absolute;top:-3px;right:-3px;background:#e0392b;color:#fff;font-size:10px;font-weight:800;
  border-radius:10px;padding:1px 6px}
#mbot{position:fixed;right:18px;bottom:18px;z-index:51;width:min(400px,calc(100vw - 24px));height:min(640px,calc(100vh - 36px));
  background:#fff;border-radius:20px;box-shadow:0 20px 60px rgba(15,23,42,.32);display:none;flex-direction:column;overflow:hidden}
#mbot.open{display:flex}
#mbot .hd{background:linear-gradient(135deg,#1e3a5f,#2563eb);color:#fff;padding:14px 16px;display:flex;align-items:center;gap:10px}
#mbot .hd .av{font-size:22px}
#mbot .hd .t{font-weight:800;font-size:14.5px}
#mbot .hd .s{font-size:11.5px;opacity:.85}
#mbot .hd .x{margin-left:auto;background:none;border:none;color:#fff;font-size:20px;cursor:pointer;opacity:.85}
#mbot .body{flex:1;overflow-y:auto;padding:14px;background:#f4f6f9;display:flex;flex-direction:column;gap:10px}
#mbot .msg{max-width:85%;padding:10px 13px;border-radius:14px;font-size:13.5px;line-height:1.6;white-space:pre-wrap;word-break:break-word}
#mbot .bot{background:#fff;border:1px solid #e9ebef;align-self:flex-start;border-bottom-left-radius:4px}
#mbot .me{background:#2563eb;color:#fff;align-self:flex-end;border-bottom-right-radius:4px}
#mbot .sug{display:flex;flex-wrap:wrap;gap:6px;margin-top:2px}
#mbot .sug button{font-size:12px;border:1px solid #cfe0f5;background:#fff;color:#2563eb;border-radius:16px;padding:6px 11px;cursor:pointer}
#mbot .typing{font-size:13px;color:#8a93a0;align-self:flex-start;padding:4px 6px}
#mbot .ft{border-top:1px solid #e9ebef;padding:9px;display:flex;gap:8px;background:#fff}
#mbot .ft input{flex:1;border:1px solid #d8dde6;border-radius:20px;padding:9px 14px;font-size:13.5px;outline:none}
#mbot .ft button{border:none;background:#2563eb;color:#fff;border-radius:20px;padding:0 16px;font-weight:700;cursor:pointer}
#mbot .ft button:disabled{opacity:.5}
#mbot .disc{font-size:10px;color:#aab1bd;text-align:center;padding:5px 10px 9px;background:#fff}
</style>
<button id="mbot-fab" aria-label="브리핑 봇 열기">💬<span class="badge">봇</span></button>
<div id="mbot" role="dialog" aria-label="매크로 브리핑 봇">
  <div class="hd"><span class="av">📈</span><div><div class="t">매크로 브리핑 봇</div>
    <div class="s">오늘 브리핑을 알고 있어요</div></div>
    <button class="x" aria-label="닫기">×</button></div>
  <div class="body" id="mbot-body"></div>
  <div class="ft"><input id="mbot-in" placeholder="궁금한 걸 물어보세요…" autocomplete="off"/>
    <button id="mbot-send">전송</button></div>
  <div class="disc">학습·관찰용 도우미예요. 매수/매도 권유가 아닙니다.</div>
</div>
<script>
(function(){
  var fab=document.getElementById('mbot-fab'),box=document.getElementById('mbot'),
      body=document.getElementById('mbot-body'),inp=document.getElementById('mbot-in'),
      send=document.getElementById('mbot-send'),hist=[],busy=false,greeted=false;
  var SUG=["환율이 왜 이렇게 올랐어요?","지금 달러 사도 안 늦었나요?","금 지금 사도 돼요?","한국 주식 어떻게 봐야 해요?"];
  function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
  function add(side,text){var m=document.createElement('div');m.className='msg '+side;m.innerHTML=esc(text);
    body.appendChild(m);body.scrollTop=body.scrollHeight;return m;}
  function suggest(){var w=document.createElement('div');w.className='sug';
    SUG.forEach(function(q){var b=document.createElement('button');b.textContent=q;
      b.onclick=function(){ask(q);};w.appendChild(b);});body.appendChild(w);body.scrollTop=body.scrollHeight;}
  function greet(){if(greeted)return;greeted=true;
    add('bot','안녕하세요! 오늘 브리핑을 바탕으로 편하게 답해드려요. 단, 「사라/팔라」 대신 스스로 판단할 틀을 드립니다. 무엇이 궁금하세요? 👇');suggest();}
  function ask(q){
    if(busy||!q.trim())return;busy=true;send.disabled=true;
    document.querySelectorAll('#mbot .sug').forEach(function(e){e.remove();});
    add('me',q);hist.push({role:'user',content:q});inp.value='';
    var t=document.createElement('div');t.className='typing';t.textContent='생각하는 중…';
    body.appendChild(t);body.scrollTop=body.scrollHeight;
    fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:q,history:hist.slice(0,-1)})})
      .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
      .then(function(o){t.remove();
        var a=o.ok?o.j.answer:(o.j.error||'잠시 후 다시 시도해 주세요.');
        add('bot',a);if(o.ok)hist.push({role:'assistant',content:a});})
      .catch(function(){t.remove();add('bot','연결이 잠깐 끊겼어요. 다시 시도해 주세요.');})
      .finally(function(){busy=false;send.disabled=false;inp.focus();});
  }
  fab.onclick=function(){box.classList.add('open');fab.style.display='none';greet();inp.focus();};
  box.querySelector('.x').onclick=function(){box.classList.remove('open');fab.style.display='block';};
  send.onclick=function(){ask(inp.value);};
  inp.addEventListener('keydown',function(e){if(e.key==='Enter')ask(inp.value);});
})();
</script>
"""


if __name__ == "__main__":
    build()
