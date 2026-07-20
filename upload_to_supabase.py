# -*- coding: utf-8 -*-
"""
dashboard_data.json을 Supabase scm_dashboard_snapshots 테이블에 업로드.
service_role 키가 필요하며, 이 키는 .env.local 파일(git에 커밋 안 됨)에서만 읽는다.

사용법:
  1) .env.local 파일을 이 스크립트와 같은 폴더에 만들고 아래 두 줄을 채운다:
       SUPABASE_URL=https://xfmpdbzwtslwvwoqoypc.supabase.co
       SUPABASE_SERVICE_ROLE_KEY=<Supabase 대시보드 Settings > API 에서 복사한 service_role 키>
  2) python upload_to_supabase.py 실행
"""
import io
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, ".env.local")
DATA_FILE = os.path.join(HERE, "dashboard_data.json")


def load_env(path):
    env = {}
    if not os.path.exists(path):
        return env
    with io.open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main():
    env = load_env(ENV_FILE)
    supabase_url = env.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    service_key = env.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not service_key:
        raise SystemExit(
            f"SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 가 없습니다.\n"
            f"{ENV_FILE} 파일을 만들고 값을 채워주세요 (스크립트 상단 사용법 참고)."
        )

    with io.open(DATA_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    body = json.dumps({"payload": payload}).encode("utf-8")
    endpoint = supabase_url.rstrip("/") + "/rest/v1/scm_dashboard_snapshots"

    req = urllib.request.Request(endpoint, data=body, method="POST")
    req.add_header("apikey", service_key)
    req.add_header("Authorization", f"Bearer {service_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=representation")

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(f"업로드 성공. snapshot id={result[0]['id']}, created_at={result[0]['created_at']}")
    except urllib.error.HTTPError as e:
        print("업로드 실패:", e.code, e.read().decode("utf-8"))
        raise


if __name__ == "__main__":
    main()
