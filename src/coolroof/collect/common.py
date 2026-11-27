"""수집 공통: 재시도 HTTP, 출처 메타데이터 기록 (기획안 4장 획득절차 ③)."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import requests

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "coolroof-research/0.1"


def get_json(url: str, params: dict, retries: int = 3, interval: float = 0.3) -> dict:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=30)
            r.raise_for_status()
            time.sleep(interval)
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last_err = e
            time.sleep(interval * (2 ** attempt))
    raise RuntimeError(f"요청 실패: {url} ({last_err})")


def write_meta(out_path: Path, source: str, url: str, params: dict | None = None,
               license_note: str = "", extra: dict | None = None) -> None:
    """산출 파일 옆에 <파일>.meta.json 으로 출처·시점·라이선스를 남긴다."""
    safe_params = {k: v for k, v in (params or {}).items() if "key" not in k.lower() and "secret" not in k.lower()}
    meta = {
        "source": source,
        "url": url,
        "params": safe_params,
        "collected_at": datetime.now().isoformat(timespec="seconds"),
        "license_note": license_note,
        **(extra or {}),
    }
    Path(str(out_path) + ".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
