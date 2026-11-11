#!/usr/bin/env python3
"""Fetch words already studied today from the MaiMemo Open API.

    POST https://open.maimemo.com/open/api/v1/study/get_today_items
    {"is_finished": true, "limit": 1000}

Token: log in at
https://open.maimemo.com/open/api/v1/tokens/openapi
then save the token to momo/.token or export MAIMEMO_TOKEN.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://open.maimemo.com/open/api/v1"
ROOT = Path(__file__).resolve().parent
TOKEN_PATH = ROOT / ".token"
OUT_PATH = ROOT / "today-words.json"


def load_token() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    env = os.environ.get("MAIMEMO_TOKEN", "").strip()
    if env:
        return env
    if TOKEN_PATH.is_file():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    return ""


def request_json(token: str, path: str, body: dict | None, retries: int = 4) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(
            BASE + path,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "momo-today-list/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
                wait = int(exc.headers.get("Retry-After") or exc.headers.get("x-ratelimit-reset-short") or 2 * (attempt + 1))
                time.sleep(max(1, min(wait, 30)))
                last_error = exc
                continue
            raise SystemExit(f"HTTP {exc.code} {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise SystemExit(f"network error {path}: {exc}") from exc
    raise SystemExit(f"request failed: {last_error}")


def unwrap(payload: dict) -> dict:
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def main() -> None:
    token = load_token()
    if not token:
        raise SystemExit(
            "缺少 token。请在浏览器打开\n"
            "https://open.maimemo.com/open/api/v1/tokens/openapi\n"
            "登录后把 token 写入 momo/.token，或设置环境变量 MAIMEMO_TOKEN。"
        )

    progress = unwrap(request_json(token, "/study/get_study_progress", None))
    items_resp = unwrap(
        request_json(
            token,
            "/study/get_today_items",
            {"is_finished": True, "limit": 1000},
        )
    )
    items = items_resp.get("today_items") or []
    items = [row for row in items if row.get("is_finished")]
    items = sorted(items, key=lambda row: row.get("order", 0))
    payload = {
        "progress": progress.get("progress", progress),
        "count": len(items),
        "truncated": len(items) >= 1000,
        "today_items": items,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    prog = payload["progress"] if isinstance(payload["progress"], dict) else {}
    print(
        f"今日进度 finished={prog.get('finished')} total={prog.get('total')} "
        f"study_time_ms={prog.get('study_time')}"
    )
    print(f"今日已学 {len(items)} 个 -> {OUT_PATH}")
    if payload["truncated"]:
        print("返回达到 1000 条上限，列表可能不完整。")
    response_label = {
        "FAMILIAR": "认识",
        "VAGUE": "模糊",
        "FORGET": "忘记",
        "WELL_FAMILIAR": "熟知",
        "CANCEL_WELL_FAMILIAR": "取消熟知",
    }
    for row in items:
        flags = []
        if row.get("is_new"):
            flags.append("新词")
        answer = response_label.get(row.get("first_response") or "", "")
        if answer:
            flags.append(answer)
        mark = (" [" + ",".join(flags) + "]") if flags else ""
        print(f"{row.get('order', 0):4d}  {row.get('voc_spelling', '')}{mark}")


if __name__ == "__main__":
    main()
