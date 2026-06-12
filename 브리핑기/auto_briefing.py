# -*- coding: utf-8 -*-
"""
GitHub Actions 및 구글 제미나이(Google Gemini) API를 활용한 매일 자동 브리핑 생성기
- yfinance 시세를 수집합니다.
- 제미나이 API에 Google Search Grounding(구글 검색 연동)을 적용하여 오늘 매크로 뉴스를 리서치합니다.
- 오늘의 시장 지표와 경제 뉴스를 대조하여 시나리오 분석 및 브리핑 본문 JSON을 생성합니다.
- 생성된 브리핑을 DB에 저장하고, 정적 대시보드를 빌드합니다.
"""
import os
import sys
import json
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# 경로 추가
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from dotenv import load_dotenv
for env_file in [".env.production", ".env.local", ".env"]:
    path = os.path.join(os.path.dirname(HERE), env_file)
    if os.path.exists(path):
        load_dotenv(path)

import fetch_market
import store_briefing
import build_site

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

SYSTEM_INSTRUCTION = """당신은 금융/경제 전문 AI 에디터입니다. 오늘의 시장 가격 지표와 구글 검색을 활용한 최신 매크로 분석을 바탕으로, 한국 개인투자자를 위한 '매크로 투자 브리핑' 기사를 작성하는 것이 임무입니다.

[작성 규칙]
1. 모든 숫자는 검증된 수치만 사용해야 합니다.
   - yfinance에서 수집된 시세 데이터(제공 예정)는 그대로 카드로 자동 렌더링되므로 본문에서 함부로 값을 위조하지 마십시오.
   - 본문에 직접 수록하는 거시 지표(미국 CPI, PPI, 정책금리 등)는 반드시 구글 검색으로 확인된 Tier1 출처(연준, 통계청, 블룸버그 등)의 실데이터를 사용하고, 'source' 필드에 출처를 명시해야 합니다.
   - 불확실한 수치는 절대 단정해서 쓰지 마십시오.
2. 가독성과 톤앤매너:
   - 개인투자자가 이해하기 쉽도록 구어체와 친근한 톤을 사용하되 전문성을 잃지 마십시오.
   - 상승 지표와 하락 지표의 한국 시장 색상 규칙을 준수하십시오 (상승: 빨강/up, 하락: 파랑/down).
   - "사라/팔라"와 같은 직접적인 추천을 피하고, 거시 분석과 시나리오 평가를 통한 '스스로의 판단 틀'을 제공하십시오.
3. 시나리오 분석:
   - 제공된 시나리오 목록을 확인하고, 오늘의 매크로 뉴스 및 시세 변화가 각 시나리오의 조건(trigger_conditions, counter_conditions)을 충족하는지 대조하십시오.
   - 각 시나리오의 상태 변화를 '강화', '약화', '유지' 중 하나로 판정하고 명확한 근거를 제시하십시오.

출력은 반드시 제공된 스키마를 따르는 JSON 형식이어야 합니다.
"""

USER_PROMPT_TEMPLATE = """오늘 날짜: {today}
최신 시세 데이터:
{market_data}

기존 활성 시나리오 목록:
{scenarios}

오늘(그리고 최근 1~2일간)의 글로벌 및 한국 경제 뉴스(중동/호르무즈 해협/유가 갈등, 미국 CPI/PPI 물가 지수, 연준 FOMC 금리 전망, 원달러 환율 및 외인 수급 등)를 구글 검색으로 심층 리서치하십시오.

그 후, 아래 구조를 가진 단일 JSON 객체를 생성하십시오.
JSON 구조:
{{
  "briefing": {{
    "period": "daily",
    "title": "오늘 브리핑의 핵심을 요약하는 매력적인 기사 제목",
    "weather": {{
      "emoji": "날씨 이모지 (예: ☀️, ⛈️, 🌤️, ☁️ 등)",
      "state": "날씨 상태 요약 (예: '흐리고 비', '맑음' 등)",
      "desc": "오늘 시장 상황을 날씨에 비유한 한줄 설명"
    }},
    "plain": "오늘 시장에서 일어난 일을 아주 쉽고 친근하게 설명하는 본문 (강조할 부분은 <b>태그 사용)",
    "stance": {{
      "title": "지금 어떻게 투자해야 할지에 대한 한줄 결론",
      "sub": "부연 설명"
    }},
    "increase": ["비중을 늘리거나 관심을 가질 만한 자산 1", "자산 2", ...],
    "decrease": ["비중을 줄이거나 보수적으로 볼 자산 1", "자산 2", ...],
    "views": [
      {{
        "badge": "관점 (예: 유리, 중립, 주의 등)",
        "badgeClass": "배지 스타일 클래스 (b-good, b-neu, b-warn, b-bad 중 선택)",
        "name": "자산군 이름 (예: 달러·현금성 자산, 금·안전자산, 미국 국채, 한국 주식(지수), 에너지 관련 등)",
        "horizon": "투자 기간 (예: 단기, 중기, 장기)",
        "why": "그렇게 판단한 거시적 이유",
        "how": "구체적인 투자 접근 및 팁"
      }},
      ... (5개 자산군 모두 포함: 달러·현금성 자산, 금·안전자산, 미국 국채, 한국 주식(지수), 에너지 관련)
    ],
    "indicators": [
      {{
        "kind": "market",
        "code": "USDKRW",
        "label": "원/달러 환율",
        "mean": "지표의 오늘 움직임이 갖는 매크로적 의미 설명"
      }},
      {{
        "kind": "market",
        "code": "WTI",
        "label": "국제 유가 (WTI)",
        "mean": "의미 설명"
      }},
      {{
        "kind": "market",
        "code": "KOSPI",
        "label": "코스피",
        "mean": "의미 설명"
      }},
      {{
        "kind": "market",
        "code": "US10Y",
        "label": "미 국채 10년 금리",
        "mean": "의미 설명"
      }},
      {{
        "kind": "cited",
        "label": "추가 지표 이름 (예: 미국 소비자물가 (CPI) 등)",
        "value": "실제 최근 발표 값 (예: +4.2%)",
        "tag": "지표 상태 (예: 3년래 최고 등)",
        "tagClass": "up 또는 down",
        "mean": "이 지표의 시장 파급 효과 설명",
        "source": "실제 공식 출처 (예: 美 노동부)"
      }},
      ... (최소 2개 이상의 cited 지표 추가)
    ],
    "flow": [
      {{
        "tag": "단계명 (예: 사건, 1차, 2차, 3차, 한국 등)",
        "kr": 단계가 한국 자산에 미치는 영향인지 여부 (true/false),
        "title": "사건 단계의 제목",
        "desc": "세부 내용"
      }},
      ... (최소 4~5단계의 인과관계 체인 구성)
    ],
    "weekly": {{
      "from": "지난주까지의 핵심 테마/주인공",
      "to": "이번 주의 핵심 테마/주인공",
      "bullets": [
        "이번 주 시장 흐름의 핵심 요약 포인트 1",
        "포인트 2",
        "포인트 3"
      ],
      "chips": [
        {{ "text": "상태 설명 칩 (예: 지정학·에너지 약화중)", "cls": "str 또는 weak 또는 watch", "dot": "▲ 또는 ▼ 또는 empty" }},
        ...
      ]
    }},
    "monthly": {{
      "title": "이번 달 거시 테마 제목",
      "body": "이번 달 주요 거시 골격과 한국 투자자를 위한 관전 포인트 상세 설명 (<b>태그 적절히 사용)",
      "chips": [
        {{ "text": "관찰 포인트 칩 (예: ⏳ 이란 합의 서명 확인)", "cls": "watch" }},
        ...
      ]
    }},
    "terms": [
      {{ "term": "용어 1", "desc": "설명" }},
      ... (브리핑에 등장하는 어려운 경제 용어 3~4개 설명)
    ],
    "sources": "정보 출처 문구 (예: 시세=yfinance(자동수집) · 물가=美 노동부...)",
    "verify_note": "수치 팩트체크 내용 기술"
  }},
  "scenario_updates": [
    ["시나리오 ID (예: scn-fed-rate-cut)", "강화 또는 약화 또는 유지", "오늘 뉴스/시세에 근거한 구체적인 판정 사유"],
    ... (제공된 시나리오 전체에 대해 판정)
  ]
}}
"""


def get_latest_market_data(conn):
    """최근 수집된 시장 데이터 문자열화"""
    rows = conn.execute(
        """SELECT m.* FROM market_data m
           JOIN (SELECT indicator, MAX(id) mx FROM market_data GROUP BY indicator) t
             ON m.id = t.mx"""
    ).fetchall()
    data_list = []
    for r in rows:
        chg = f"{r['daily_change']:+.2f}%" if r['daily_change'] is not None else "N/A"
        data_list.append(f"- {r['indicator']}: {r['value']} {r['unit']} (전일대비 {chg}, 날짜: {r['timestamp']})")
    return "\n".join(data_list)


def get_scenarios(conn):
    """현재 DB의 시나리오 목록 문자열화"""
    rows = conn.execute("SELECT id, title, hypothesis, status, confidence FROM scenarios").fetchall()
    scenarios_list = []
    for r in rows:
        scenarios_list.append(
            f"- ID: {r['id']}\n  제목: {r['title']}\n  가설: {r['hypothesis']}\n  현재상태: {r['status']} / 신뢰도: {r['confidence']}"
        )
    return "\n\n".join(scenarios_list)


def ask_gemini(api_key, prompt):
    """Google Gemini API 호출 (Google Search Grounding 활성화 및 JSON 출력 강제)"""
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={api_key}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print("[에러] Gemini API HTTP 에러 발생!")
        print(f"상태 코드: {e.code}")
        try:
            err_detail = e.read().decode()
            print(f"상태 세부내용:\n{err_detail}")
        except Exception as read_err:
            print(f"에러 세부내용 읽기 실패: {read_err}")
        raise e
    
    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("Gemini API가 빈 응답을 반환했습니다.")
    
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    return text


def run():
    # 1. 시세 수집 실행
    print("1단계: 시세 수집 시작...")
    fetch_market.run()
    print("시세 수집 완료.")

    # API 키 확인
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("[에러] GEMINI_API_KEY 또는 GOOGLE_API_KEY 환경변수가 설정되어 있지 않습니다.")
        sys.exit(1)

    # 2. DB 연결 및 데이터 조회
    db_conn = sqlite3.connect(store_briefing.get_db_connection().execute("PRAGMA database_list").fetchone()[2])
    db_conn.row_factory = sqlite3.Row
    
    # 오늘 날짜 (KST 기준)
    kst = timezone(timedelta(hours=9))
    today_str = datetime.now(kst).strftime("%Y-%m-%d")
    
    print(f"2단계: DB 조회 및 프롬프트 빌드 (기준 날짜: {today_str})...")
    market_data_str = get_latest_market_data(db_conn)
    scenarios_str = get_scenarios(db_conn)

    prompt = USER_PROMPT_TEMPLATE.format(
        today=today_str,
        market_data=market_data_str,
        scenarios=scenarios_str
    )

    # 3. Gemini API 호출
    print("3단계: Gemini API 호출 (구글 검색 연동)...")
    try:
        response_text = ask_gemini(api_key, prompt)
        res_json = json.loads(response_text)
    except Exception as e:
        print(f"[에러] Gemini 호출 또는 JSON 파싱 중 오류 발생: {e}")
        if 'response_text' in locals():
            print(f"응답 텍스트 일부: {response_text[:500]}")
        sys.exit(1)

    briefing_payload = res_json.get("briefing")
    scenario_updates = res_json.get("scenario_updates", [])

    if not briefing_payload:
        print("[에러] 응답 JSON에 'briefing' 키가 없습니다.")
        sys.exit(1)

    # 4. DB 저장
    print("4단계: DB에 브리핑 및 시나리오 업데이트 기록...")
    bid = store_briefing.upsert_briefing(today_str, "daily", briefing_payload)
    print(f"  - 브리핑 저장 완료: {bid}")

    for update in scenario_updates:
        if len(update) >= 3:
            sid, change, reason = update[0], update[1], update[2]
            store_briefing.log_scenario(sid, today_str, change, reason, bid, source="제미나이 AI 분석체인")
            print(f"  - 시나리오 {sid} 업데이트: {change}")
        else:
            print(f"  - 잘못된 시나리오 업데이트 형식: {update}")

    db_conn.close()

    # 5. 정적 사이트 빌드
    print("5단계: build_site.py 실행하여 HTML 렌더링...")
    build_site.build()
    print("자동 브리핑 생성 및 정적 빌드 최종 완료!")


if __name__ == "__main__":
    run()
