# -*- coding: utf-8 -*-
import os
import json
import urllib.request
import urllib.error

def main():
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("[에러] GEMINI_API_KEY 또는 GOOGLE_API_KEY 환경변수가 없습니다.")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    print(f"Calling: {url.replace(api_key, '***')}")
    
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            models = data.get("models", [])
            print(f"--- 사용 가능한 모델 목록 (총 {len(models)}개) ---")
            for m in models:
                name = m.get("name", "")
                methods = m.get("supportedGenerationMethods", [])
                print(f"- Model: {name}")
                print(f"  Methods: {methods}")
    except urllib.error.HTTPError as e:
        print(f"[에러] HTTP 에러 발생: {e.code}")
        print(e.read().decode())
    except Exception as e:
        print(f"[에러] 일반 예외 발생: {e}")

if __name__ == "__main__":
    main()
