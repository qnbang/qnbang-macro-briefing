# 매크로 투자 브리핑

거시 흐름을 먼저 읽고 "이 자산을 이런 관점으로 보라"를 기사 형식으로 자동 발행하는 서비스.
**포지셔닝:** 매수/매도 신호가 아닌 *거시 흐름 학습 + 시나리오 관찰 도구*.
**차별화:** 글로벌 거시 흐름을 **한국 투자자의 자산 언어(원화·코스피·수출산업)로 번역**.

## 구조 — 맥이 꺼져 있어도 매일 자동

```
[매일 아침] 클라우드 예약 에이전트(클로드 헤드리스·구독, 추가비용 0원)
   1) fetch_market.py   — yfinance로 시장 '숫자' 수집 → DB
   2) (클로드 분석)      — 웹 리서치 → 시나리오 대조 → 한국자산 시사점
   3) store_briefing.py — 브리핑 본문·시나리오 이력 DB 기록
   4) build_site.py     — DB → 정적 대시보드(site/) 렌더
   5) git push          — DB·site/ 커밋·푸시
        │
        ▼
[푸시 감지] Vercel — site/ 를 그대로 정적 서빙 (빌드 없음 = 가장 안정적)
```

**핵심 원칙(할루시네이션 차단):** 기사에 들어가는 **모든 숫자는 검증 경로에서만** 온다.
시세는 `market_data`(yfinance, 값·시점·출처 동반), 그 외 인용 수치(CPI·정책금리 등)는 Tier1 출처를 명시.
LLM은 산문을 쓰되 **새 숫자를 만들 수 없다.**

## 파일

| 파일 | 역할 |
|------|------|
| `브리핑기/db.py` | DB 스키마 + 시나리오 시드 |
| `브리핑기/fetch_market.py` | 시장 숫자 수집(yfinance) → `market_data` |
| `브리핑기/store_briefing.py` | 브리핑 본문·시나리오 이력 저장 헬퍼 |
| `브리핑기/오늘브리핑_seed.py` | 브리핑 본문 dict **형식 견본** + 1회 실행본 |
| `브리핑기/build_site.py` | DB → 정적 대시보드(`site/`) 렌더 |
| `site/` | 배포되는 정적 산출물(index·archive·data.json) |
| `macro_briefing.db` | 시나리오·시세·브리핑·이력 (단일 진실원) |

## 수동 실행(로컬)

```bash
cd 브리핑기
.venv/bin/python fetch_market.py        # 시세 수집
.venv/bin/python 오늘브리핑_seed.py      # (오늘은 견본) 브리핑 기록
.venv/bin/python build_site.py          # site/ 렌더
```

## 매일 자동 — 클라우드 예약 에이전트가 하는 일

매일 아침 아래를 순서대로 수행하고 푸시한다(이 README의 "구조" 참고):
`fetch_market.py` → 웹 리서치·분석으로 새 브리핑 dict 작성 → `store_briefing.upsert_briefing`/`log_scenario` →
`build_site.py` → `git add -A && git commit && git push`.

> 거시 흐름 학습·관찰용이며 투자 자문이나 매매 권유가 아닙니다.
