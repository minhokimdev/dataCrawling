"""국토교통부 건축HUB 건축물대장정보 (data.go.kr 15134735).

표제부/기본개요/층별개요를 시군구+법정동 단위로 페이지 순회한다.
법정동 목록은 GIS 건물 도형의 PNU 에서 뽑는다 (pnu[:5]=시군구, pnu[5:10]=법정동).
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from .common import get_json

OPERATIONS = {
    "title": "getBrTitleInfo",       # 표제부: 용도·구조·건축면적·지붕·사용승인일
    "basis": "getBrBasisOulnInfo",   # 기본개요
    "floor": "getBrFlrOulnInfo",     # 층별개요: 층별 용도
}

TITLE_COLUMNS = [
    "mgmBldrgstPk", "sigunguCd", "bjdongCd", "platGbCd", "bun", "ji",
    "platPlc", "newPlatPlc", "bldNm", "dongNm", "mainAtchGbCdNm",
    "mainPurpsCdNm", "etcPurps", "strctCdNm", "roofCdNm", "etcRoof",
    "archArea", "totArea", "grndFlrCnt", "useAprDay", "crtnDay",
]


def _items(payload: dict) -> tuple[list[dict], int]:
    body = payload.get("response", {}).get("body", {})
    header = payload.get("response", {}).get("header", {})
    if header.get("resultCode") not in (None, "00", "0"):
        raise RuntimeError(f"건축HUB 오류: {header}")
    items = body.get("items") or {}
    item = items.get("item", []) if isinstance(items, dict) else []
    if isinstance(item, dict):
        item = [item]
    return item, int(body.get("totalCount", 0) or 0)


def fetch_operation(base_url: str, service_key: str, op: str, sigungu_cd: str, bjdong_cd: str,
                    num_rows: int = 100, interval: float = 0.3, **filters) -> list[dict]:
    url = f"{base_url}/{OPERATIONS[op]}"
    rows: list[dict] = []
    page = 1
    while True:
        params = {"serviceKey": service_key, "sigunguCd": sigungu_cd, "bjdongCd": bjdong_cd,
                  "numOfRows": num_rows, "pageNo": page, "_type": "json", **filters}
        items, total = _items(get_json(url, params, interval=interval))
        rows.extend(items)
        if not items or len(rows) >= total:
            return rows
        page += 1


def fetch_title_for_dongs(base_url: str, service_key: str, sigungu_cd: str,
                          bjdong_cds: Iterable[str], interval: float = 0.3) -> pd.DataFrame:
    frames = []
    for bjdong in sorted(set(bjdong_cds)):
        rows = fetch_operation(base_url, service_key, "title", sigungu_cd, bjdong, interval=interval)
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=TITLE_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    keep = [c for c in TITLE_COLUMNS if c in df.columns]
    return df[keep].drop_duplicates("mgmBldrgstPk")


def register_pnu(df: pd.DataFrame) -> pd.Series:
    """대장 키 → PNU(19자리). 대장 platGbCd 0=대지,1=산 / PNU 대지구분 1=일반,2=산."""
    land = df["platGbCd"].astype(str).map({"0": "1", "1": "2"}).fillna("1")
    return (df["sigunguCd"].astype(str).str.zfill(5) + df["bjdongCd"].astype(str).str.zfill(5)
            + land + df["bun"].astype(str).str.zfill(4) + df["ji"].astype(str).str.zfill(4))
