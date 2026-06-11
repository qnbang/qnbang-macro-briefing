# -*- coding: utf-8 -*-
"""
브리핑 저장 헬퍼 (생성 레이어 → DB)
- 매일 클라우드 예약 에이전트(클로드 헤드리스)가 브리핑 본문(dict)을 만들어
  upsert_briefing()으로 daily_briefings에 저장하고,
  log_scenario()로 시나리오 이력_로그를 1일차부터 쌓는다.
- 본문은 JSON 한 덩어리로 content 칸에 넣는다(렌더는 build_site.py 담당).
"""
import json
from datetime import datetime, timezone

from db import get_db_connection


def upsert_briefing(date_str, period, payload):
    """브리핑 1편 저장(같은 id면 덮어씀).
    date_str: 'YYYY-MM-DD', period: 'daily'|'weekly'|'monthly',
    payload: 본문 dict (build_site.py가 읽는 구조)."""
    bid = f"{period}-{date_str}"
    payload = dict(payload)
    payload.setdefault("period", period)
    payload.setdefault("date", date_str)
    meta = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "verify_note": payload.get("verify_note", ""),
    }
    conn = get_db_connection()
    conn.execute(
        """INSERT OR REPLACE INTO daily_briefings (id, date, content, metadata)
           VALUES (?, ?, ?, ?)""",
        (bid, date_str, json.dumps(payload, ensure_ascii=False), json.dumps(meta, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    return bid


def log_scenario(scenario_id, date_str, change_type, reason, briefing_id, source=""):
    """시나리오 이력_로그 한 줄 추가 + 시나리오 상태/신뢰도 반영.
    change_type: '강화'|'약화'|'유지'|'종료'."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO scenario_logs (scenario_id, date, change_type, reason, source, briefing_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (scenario_id, date_str, change_type, reason, source, briefing_id),
    )
    # 상태·신뢰도 가볍게 반영(강화 +0.05, 약화 -0.05, 0~1 클램프)
    row = cur.execute("SELECT confidence FROM scenarios WHERE id=?", (scenario_id,)).fetchone()
    if row is not None:
        conf = row[0] if row[0] is not None else 0.5
        delta = {"강화": 0.05, "약화": -0.05}.get(change_type, 0.0)
        conf = max(0.0, min(1.0, round(conf + delta, 2)))
        status_map = {"강화": "강화중", "약화": "약화중", "유지": "활성"}
        status = status_map.get(change_type)
        if status:
            cur.execute(
                "UPDATE scenarios SET confidence=?, status=?, updated_at=? WHERE id=?",
                (conf, status, date_str, scenario_id),
            )
        else:
            cur.execute(
                "UPDATE scenarios SET confidence=?, updated_at=? WHERE id=?",
                (conf, date_str, scenario_id),
            )
    conn.commit()
    conn.close()
