#!/usr/bin/env bash
# 매일 발행의 '결정적 단계'(시세 수집 → 렌더 → 커밋·푸시)를 한 번에.
# 브리핑 '본문 작성'(운영가이드 3·4번)은 이 스크립트 호출 전에 클로드가 DB에 기록해 둔다.
set -euo pipefail
cd "$(dirname "$0")"                 # 브리핑기/
ROOT="$(cd .. && pwd)"

# 가상환경 보장
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

# 1) 시세 수집
.venv/bin/python fetch_market.py

# 2) 렌더 (DB → site/)
.venv/bin/python build_site.py

# 3) 변경 있으면 커밋·푸시 → Vercel 자동배포
cd "$ROOT"
if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git -c user.email=ceo@qnbang.com -c user.name="신종호" \
    commit -m "데일리 자동발행 $(date +%Y-%m-%d)"
  git push
  echo "발행 완료 → https://qnbang-macro-briefing.vercel.app"
else
  echo "변경 없음 — 푸시 생략"
fi
