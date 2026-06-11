import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'macro_briefing.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """데이터베이스 테이블 생성 및 초기 데이터(시드) 입력"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. 시나리오 테이블 (scenarios)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scenarios (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT,
            hypothesis TEXT,
            status TEXT NOT NULL, -- '활성', '강화중', '약화중', '종료(적중)', '종료(빗나감)'
            confidence REAL DEFAULT 0.5,
            trigger_conditions TEXT, -- JSON Array
            counter_conditions TEXT, -- JSON Array
            ripple_chain TEXT, -- JSON Array
            affected_assets TEXT, -- JSON Array
            korean_asset_implication TEXT,
            created_at TEXT,
            updated_at TEXT,
            tags TEXT -- JSON Array
        )
    ''')

    # 2. 시장 데이터 테이블 (market_data)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            indicator TEXT NOT NULL, -- KOSPI, USDKRW, WTI, GOLD, US10Y 등
            value REAL NOT NULL,
            unit TEXT,
            timestamp TEXT NOT NULL,
            source TEXT,
            daily_change REAL
        )
    ''')

    # 3. 브리핑 기사 테이블 (daily_briefings)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_briefings (
            id TEXT PRIMARY KEY, -- daily-YYYYMMDD
            date TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT -- JSON Metadata
        )
    ''')

    # 4. 시나리오 로그 테이블 (scenario_logs)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scenario_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id TEXT NOT NULL,
            date TEXT NOT NULL,
            change_type TEXT NOT NULL, -- '강화', '약화', '유지', '종료'
            reason TEXT NOT NULL,
            source TEXT,
            briefing_id TEXT,
            FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
        )
    ''')

    conn.commit()
    seed_scenarios(conn)
    conn.close()
    print("데이터베이스 초기화 완료.")

def seed_scenarios(conn):
    """초기 시드 시나리오 5종 추가 (한국 투자자 맞춤형)"""
    cursor = conn.cursor()
    
    # 이미 데이터가 있으면 건너뜀
    cursor.execute("SELECT COUNT(*) FROM scenarios")
    if cursor.fetchone()[0] > 0:
        return

    today = datetime.now().strftime('%Y-%m-%d')

    scenarios_data = [
        {
            "id": "scn-fed-rate-cut",
            "title": "연준 금리 인하 사이클과 코스피 유동성 환율 랠리",
            "summary": "미국 연방준비제도(Fed)가 금리를 인하하면서 달러 약세와 신흥국 시장으로의 자금 유입이 발생하는 가설",
            "hypothesis": "미국의 정책 금리 인하로 인해 글로벌 유동성이 증대되고, 한미 금리차가 축소되며 원/달러 환율이 하락(원화 강세)하고 코스피 지수에 외국인 순매수가 강하게 유입될 것이다.",
            "status": "활성",
            "confidence": 0.55,
            "trigger_conditions": json.dumps([
                "FOMC 회의에서 정책금리 인하 또는 비둘기파적 성명서 발표",
                "미국 국채 10년물 금리의 3.5% 이하 하향 안정화",
                "원/달러 환율의 1,300원선 하향 돌파"
            ]),
            "counter_conditions": json.dumps([
                "미국 근원 인플레이션(Core CPI) 반등 및 고금리 장기화(Higher for longer) 기조 부활",
                "미국 국채 금리 재급등",
                "외국인 자금의 한국 시장 이탈 가속화"
            ]),
            "ripple_chain": json.dumps([
                {"단계": "사건", "내용": "연준 정책금리 인하 개시", "근거": "인플레이션 목표치 수렴 및 경기 둔화 우려", "출처": "FOMC"},
                {"단계": "1차 파급", "내용": "달러지수(DXY) 약세 및 원화 강세 유도", "신뢰도": 0.8},
                {"단계": "2차 파급", "내용": "신흥국(한국 등) 자산 선호 심리 개선으로 유동성 랠리", "신뢰도": 0.7}
            ]),
            "affected_assets": json.dumps([
                {"자산": "KOSPI", "방향": "상승편향", "시계열": "중기", "신뢰도": 0.7},
                {"자산": "원/달러 환율", "방향": "하락(원화강세)", "시계열": "단기", "신뢰도": 0.8},
                {"자산": "한국 국채 3년물", "방향": "금리하락(채권상승)", "시계열": "단기", "신뢰도": 0.75}
            ]),
            "korean_asset_implication": "금리 인하 수혜주인 성장주(바이오, 이차전지, IT 플랫폼) 우호적 환경 조성, 원화 강세로 내수 업종(유통, 항공 등) 비용 개선 효과 기대.",
            "created_at": today,
            "updated_at": today,
            "tags": json.dumps(["통화정책", "금리", "환율", "코스피"])
        },
        {
            "id": "scn-usd-krw-high",
            "title": "고환율(달러 강세) 지속과 한국 수출 대형주의 실적 대칭",
            "summary": "연준의 긴축 장기화나 지정학적 리스크로 원/달러 환율이 고공행진하여 자동차, 조선 등 수출 기업의 환차익 실적이 개선되는 시나리오",
            "hypothesis": "환율이 1,350원 이상에서 장기 유지될 경우, 원화 기준 매출 비중이 큰 한국의 수출 대형주(반도체, 자동차, 조선)의 영업이익 마진이 증가할 것이다. 다만 수입 원자재 비중이 큰 기업은 악영향을 받는다.",
            "status": "활성",
            "confidence": 0.60,
            "trigger_conditions": json.dumps([
                "원/달러 환율의 1,360원 돌파 및 지지",
                "미국과 타 국가의 금리차 확대 지속",
                "글로벌 지정학적 리스크 고조로 인한 안전자산(달러) 선호"
            ]),
            "counter_conditions": json.dumps([
                "미국 경기 침체 신호로 인한 급격한 달러 약세 전환",
                "한국은행의 매파적 금리 인상 또는 외환당국의 강한 미세조정(구두개입)"
            ]),
            "ripple_chain": json.dumps([
                {"단계": "사건", "내용": "글로벌 달러 강세 압력 지속", "근거": "지정학 불확실성 및 미국 예외주의 성장세", "출처": "FRED"},
                {"단계": "1차 파급", "내용": "원화 가치 하락(1,380원 상향 돌파 시도)", "신뢰도": 0.85},
                {"단계": "2차 파급", "내용": "자동차, 조선 등 원화 환산 마진 증가로 실적 발표 서프라이즈 기대", "신뢰도": 0.75}
            ]),
            "affected_assets": json.dumps([
                {"자산": "원/달러 환율", "방향": "상승(원화약세)", "시계열": "단기", "신뢰도": 0.85},
                {"자산": "현대차/기아 (자동차 업종)", "방향": "상승편향", "시계열": "중기", "신뢰도": 0.7},
                {"자산": "내수/유틸리티 (한전 등)", "방향": "하락편향(수입원가 상승)", "시계열": "중기", "신뢰도": 0.65}
            ]),
            "korean_asset_implication": "수출 주도형 포트폴리오(자동차, 전장) 비중 확대 기회이나, 외인 입장에서는 환차손 우려로 코스피 지수 자체의 대규모 매수는 제약될 수 있음.",
            "created_at": today,
            "updated_at": today,
            "tags": json.dumps(["환율", "달러강세", "자동차", "실적"])
        },
        {
            "id": "scn-wti-inflation",
            "title": "국제유가(WTI) 급등과 한국 인플레이션 압력 및 금리 동결 연장",
            "summary": "중동 불안 등으로 국제유가가 급등해 국내 수입 물가를 자극하고 한국은행의 기준금리 인하 시점을 뒤로 늦추는 시나리오",
            "hypothesis": "WTI 유가가 배럴당 85달러를 돌파할 경우, 한국의 소비자물가지수(CPI)가 자극받아 한국은행이 기준금리를 빠르게 인하하지 못하고 장기 동결하게 되며, 이는 내수 소비 둔화로 이어진다.",
            "status": "활성",
            "confidence": 0.50,
            "trigger_conditions": json.dumps([
                "WTI Crude Oil 가격 85달러 돌파",
                "한국 수입물가지수 상승 반전",
                "한국은행 금융통화위원회의 매파적 동결 성명 발표"
            ]),
            "counter_conditions": json.dumps([
                "글로벌 경기 둔화로 인한 원유 수요 급감",
                "OPEC+의 감산 조치 해제 및 원유 증산 전환"
            ]),
            "ripple_chain": json.dumps([
                {"단계": "사건", "내용": "중동 지정학 불안으로 공급 차질 우려", "근거": "호르무즈 해협 위기 등 뉴스 검색", "출처": "Reuters"},
                {"단계": "1차 파급", "내용": "WTI 유가 급등 및 수입 원가 상승", "신뢰도": 0.9},
                {"단계": "2차 파급", "내용": "한국 근원/소비자물가 반등으로 금리 인하 기대 후퇴", "신뢰도": 0.8}
            ]),
            "affected_assets": json.dumps([
                {"자산": "WTI 유가", "방향": "상승", "시계열": "단기", "신뢰도": 0.9},
                {"자산": "정유주(S-Oil, SK이노베이션)", "방향": "상승편향", "시계열": "단기", "신뢰도": 0.7},
                {"자산": "항공/화학 업종", "방향": "하락편향(원가압박)", "시계열": "중기", "신뢰도": 0.75}
            ]),
            "korean_asset_implication": "에너지 수입 부담으로 무역수지 악화 우려. 유가 상승세 지속 시 석유화학, 항공 업종의 이익 훼손에 대비하고 정유/에너지 자원개발 업종에 주목.",
            "created_at": today,
            "updated_at": today,
            "tags": json.dumps(["유가", "인플레이션", "금리동결", "정유"])
        },
        {
            "id": "scn-semi-cycle",
            "title": "글로벌 반도체 사이클 회복과 IT 대장주(삼성전자/SK하이닉스) 동조화",
            "summary": "빅테크의 AI 인프라 투자 지속 및 HBM 수요 급증으로 글로벌 D램 반도체 사이클이 상승 국면에 진입하고 국내 반도체 양사가 코스피를 주도하는 시나리오",
            "hypothesis": "글로벌 AI 서버 수요 및 고대역폭 메모리(HBM) 공급 부족이 해소되지 않는 한, 한국의 반도체 수출 실적은 계속 증가하며 삼성전자와 SK하이닉스가 코스피 전체 시가총액 상승을 이끌 것이다.",
            "status": "활성",
            "confidence": 0.65,
            "trigger_conditions": json.dumps([
                "필라델피아 반도체 지수(SOXX)의 연고점 돌파",
                "국내 반도체 월간 수출 실적(산업부) 두 자릿수 증가 지속",
                "글로벌 메모리 고정거래 가격 상승 우상향 진행"
            ]),
            "counter_conditions": json.dumps([
                "글로벌 빅테크의 AI 투자 거품론 및 설비투자(CAPEX) 축소 발표",
                "미국의 대중국 반도체 장비/칩 규제 강화에 따른 한국 기업의 중국 공장 차질"
            ]),
            "ripple_chain": json.dumps([
                {"단계": "사건", "내용": "HBM 및 DDR5 서버용 수요 폭증", "근거": "엔비디아 실적 및 투자 가이드라인 확인", "출처": "Bloomberg"},
                {"단계": "1차 파급", "내용": "반도체 고정가 상승 및 수출 물량 확대", "신뢰도": 0.85},
                {"단계": "2차 파급", "내용": "외국인의 삼성전자/SK하이닉스 집중 매수 및 영업이익 정상화", "신뢰도": 0.8}
            ]),
            "affected_assets": json.dumps([
                {"자산": "KOSPI", "방향": "상승편향(반도체 시총 절대적)", "시계열": "중기", "신뢰도": 0.8},
                {"자산": "SK하이닉스", "방향": "상승", "시계열": "중기", "신뢰도": 0.8},
                {"자산": "국내 반도체 소부장(소재/부품/장비)", "방향": "상승편향", "시계열": "장기", "신뢰도": 0.75}
            ]),
            "korean_asset_implication": "코스피의 상하단 방향성을 쥐고 있는 핵심 테마. 반도체 회복 사이클 전개 시 소부장 낙수효과를 노린 중소형 장비주 선별 투자 유효.",
            "created_at": today,
            "updated_at": today,
            "tags": json.dumps(["반도체", "HBM", "코스피", "삼성전자", "SK하이닉스"])
        },
        {
            "id": "scn-us-real-yield-gold",
            "title": "미국 실질금리 하락에 따른 안전자산(금/은) 랠리",
            "summary": "미국의 실질금리(명목금리 - 기대인플레이션)가 하락하여 이자가 붙지 않는 대체 자산인 귀금속(금, 은) 수요가 증가하는 시나리오",
            "hypothesis": "미국의 실질금리가 하락 국면에 진입하고 달러 가치 신뢰도가 저하될 때, 대표적인 안전/대체 자산인 금과 은 가격이 급등할 것이다. 한국 시장에서는 금광주 및 원자재 관련 상장지수펀드(ETF)가 수혜를 입는다.",
            "status": "활성",
            "confidence": 0.50,
            "trigger_conditions": json.dumps([
                "미국 국채 10년물 실질금리(TIPS)의 1.0% 이하 하락",
                "국제 금 선물 가격 연고점 돌파",
                "글로벌 중앙은행들의 금 매입 비중 증가 지속"
            ]),
            "counter_conditions": json.dumps([
                "실질금리의 급격한 반등(고금리 유지 속 인플레이션 둔화)",
                "달러화 강세 추세 지속"
            ]),
            "ripple_chain": json.dumps([
                {"단계": "사건", "내용": "미국 실질금리 하락세 진입", "근거": "TIPS 금리 10년물 하락 데이터", "출처": "FRED"},
                {"단계": "1차 파급", "내용": "이자 기회비용 저하로 금/은 실물 가격 상승", "신뢰도": 0.85},
                {"단계": "2차 파급", "내용": "금 대비 가격 레버리지가 높은 은(Silver)의 상대적 강세", "신뢰도": 0.7}
            ]),
            "affected_assets": json.dumps([
                {"자산": "국제 금 가격 (GLD)", "방향": "상승", "시계열": "장기", "신뢰도": 0.8},
                {"자산": "국제 은 가격 (SLV)", "방향": "상승(레버리지)", "시계열": "장기", "신뢰도": 0.75},
                {"자산": "원/달러 환율", "방향": "중립(안전선호 시 강달러 변수 있음)", "시계열": "단기", "신뢰도": 0.5}
            ]),
            "korean_asset_implication": "헤지 수단으로서의 자산 배분 전략 수립 시점. 금 현물 자산 혹은 국내 상장된 금/은 ETF(예: KODEX 골드선물, KODEX 은선물) 활용 투자 유효.",
            "created_at": today,
            "updated_at": today,
            "tags": json.dumps(["실질금리", "귀금속", "금", "은", "대체자산"])
        }
    ]

    for scn in scenarios_data:
        cursor.execute('''
            INSERT OR REPLACE INTO scenarios (
                id, title, summary, hypothesis, status, confidence,
                trigger_conditions, counter_conditions, ripple_chain,
                affected_assets, korean_asset_implication, created_at, updated_at, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            scn["id"], scn["title"], scn["summary"], scn["hypothesis"], scn["status"], scn["confidence"],
            scn["trigger_conditions"], scn["counter_conditions"], scn["ripple_chain"],
            scn["affected_assets"], scn["korean_asset_implication"], scn["created_at"], scn["updated_at"], scn["tags"]
        ))
    
    conn.commit()
    print("시드 시나리오 5종 등록 성공.")

if __name__ == '__main__':
    init_db()
