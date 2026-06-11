# -*- coding: utf-8 -*-
"""
시장 '숫자' 데이터 수집기 (숫자 경로)
- yfinance로 핵심 거시 지표를 받아 market_data 테이블에 적재한다.
- 아키텍처 원칙: 기사에 들어갈 모든 숫자는 '오직 이 경로'에서만 온다.
  값마다 {지표, 값, 단위, 시점, 출처, 전일대비}를 함께 저장하고,
  시점·출처가 없는 값은 저장하지 않는다.
"""
import sys
import os
from datetime import datetime, timezone

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_db_connection, init_db

# (지표코드, yfinance 티커, 한글이름, 단위)
SERIES = [
    ("KOSPI",   "^KS11",    "코스피",            "pt"),
    ("KOSDAQ",  "^KQ11",    "코스닥",            "pt"),
    ("SPX",     "^GSPC",    "S&P500",           "pt"),
    ("NDX",     "^IXIC",    "나스닥 종합",        "pt"),
    ("VIX",     "^VIX",     "VIX 변동성지수",     "pt"),
    ("USDKRW",  "KRW=X",    "원/달러 환율",       "원"),
    ("DXY",     "DX-Y.NYB", "달러지수(DXY)",      "pt"),
    ("WTI",     "CL=F",     "WTI 유가",          "USD/배럴"),
    ("GOLD",    "GC=F",     "금 선물",            "USD/온스"),
    ("US10Y",   "^TNX",     "미국 국채 10년물 금리", "%"),
]


def fetch_one(ticker):
    """최근 종가 2개를 받아 (마지막값, 전일대비%, 시점) 반환. 실패 시 None."""
    hist = yf.Ticker(ticker).history(period="7d")
    closes = hist["Close"].dropna()
    if len(closes) == 0:
        return None
    last = float(closes.iloc[-1])
    change_pct = None
    if len(closes) >= 2:
        prev = float(closes.iloc[-2])
        if prev:
            change_pct = round((last - prev) / prev * 100, 2)
    ts = closes.index[-1].strftime("%Y-%m-%d")
    return round(last, 2), change_pct, ts


def run():
    init_db()  # 테이블 없으면 생성(+시드). 이미 있으면 그대로.
    conn = get_db_connection()
    cur = conn.cursor()

    ok, fail = 0, 0
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for code, ticker, name, unit in SERIES:
        try:
            res = fetch_one(ticker)
        except Exception as e:
            res = None
            print(f"  [에러] {name}({ticker}): {e}")
        if not res:
            fail += 1
            print(f"  [실패] {name} — 데이터 없음")
            continue
        value, change, ts = res
        cur.execute(
            """INSERT INTO market_data (indicator, value, unit, timestamp, source, daily_change)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (code, value, unit, ts, "yfinance", change),
        )
        ok += 1
        chg = f"{change:+.2f}%" if change is not None else "—"
        print(f"  [수집] {name:14s} {value:>12,.2f} {unit:8s} ({ts}) 전일대비 {chg}")

    conn.commit()
    conn.close()
    print(f"\n수집 완료 — 성공 {ok} / 실패 {fail} (수집시각 {fetched_at})")


if __name__ == "__main__":
    run()
