# -*- coding: utf-8 -*-
"""
매크로 브리핑 챗봇 — Vercel 서버리스 함수 (/api/chat)
- 오늘 브리핑 맥락(bot-context.json)을 바탕으로 사용자의 질문에 '판단 틀'로 답한다.
- 규제 방어선: 매수/매도·개별 종목·목표가 금지, 자산군 레벨 관점 + 면책. 학습·관찰 도구 톤.
- 모델: Google Gemini Flash(무료 등급). 키는 환경변수 GEMINI_API_KEY(코드에 넣지 않음).
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.error

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_HOST = "qnbang-macro-briefing.vercel.app"

SYSTEM = """당신은 '매크로 브리핑 봇'입니다. 한국 개인투자자에게 거시 흐름을 쉽게 설명하고 '스스로 판단할 틀'을 주는 학습·관찰 도우미입니다.

[반드시 지키기]
- "사세요/파세요", 개별 종목 추천, 목표가·수익률 단정 금지. 자산군(주식·채권·금·달러 등) 레벨의 관점만.
- 대신 '판단 틀'을 줍니다: 체크리스트(투자기간·여유자금·분할 가능 여부), 분할·분산 같은 원칙.
- 오늘 브리핑 맥락 안에서 답하고, 모르거나 맥락에 없는 수치는 지어내지 말 것("그건 오늘 브리핑엔 없어요").
- 쉬운 말로, 3~8줄 정도로 짧고 친근하게. 한국어. 필요하면 • 불릿이나 ① 단계로.
- 답 끝에 과한 면책 문구를 매번 붙이지 말 것(서비스가 별도 고지). 단정만 피하면 됨.

[오늘 브리핑 맥락]
{context}
"""


def _load_context(host):
    """배포된 같은 호스트에서 오늘 브리핑 맥락을 읽어온다."""
    for h in [host, FALLBACK_HOST]:
        if not h:
            continue
        try:
            url = f"https://{h}/bot-context.json"
            with urllib.request.urlopen(url, timeout=8) as r:
                return json.loads(r.read().decode()).get("context", "")
        except Exception:
            continue
    return "(오늘 브리핑 맥락을 불러오지 못했습니다. 일반적인 원칙 위주로 답하세요.)"


def _ask_gemini(api_key, context, question, history):
    contents = []
    for turn in (history or [])[-6:]:
        role = turn.get("role")
        text = (turn.get("content") or "").strip()
        if not text:
            continue
        g_role = "user" if role == "user" else "model"  # Gemini는 'model' 사용
        contents.append({"role": g_role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": question}]})

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM.format(context=context)}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 800, "temperature": 0.7},
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{MODEL}:generateContent?key={api_key}")
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = json.loads(resp.read().decode())
    cands = data.get("candidates", [])
    if not cands:
        return "음, 답을 만들지 못했어요. 다시 한 번 물어봐 주세요."
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    return text or "음, 답을 만들지 못했어요. 다시 한 번 물어봐 주세요."


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("content-length", 0) or 0)
            body = json.loads(self.rfile.read(length).decode() or "{}") if length else {}
        except Exception:
            return self._send(400, {"error": "잘못된 요청이에요."})

        question = (body.get("question") or "").strip()
        if not question:
            return self._send(400, {"error": "질문을 입력해 주세요."})
        if len(question) > 800:
            question = question[:800]

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return self._send(503, {"error": "챗봇이 아직 준비 중이에요(키 미설정). 잠시 후 다시 시도해 주세요."})

        host = self.headers.get("host", "")
        context = _load_context(host)
        try:
            answer = _ask_gemini(api_key, context, question, body.get("history"))
            return self._send(200, {"answer": answer})
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode()[:200]
            except Exception:
                pass
            return self._send(502, {"error": "답변 생성에 실패했어요. 잠시 후 다시 시도해 주세요.", "detail": detail})
        except Exception:
            return self._send(502, {"error": "답변 생성에 실패했어요. 잠시 후 다시 시도해 주세요."})
