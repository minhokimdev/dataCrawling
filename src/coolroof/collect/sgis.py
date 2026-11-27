"""통계청 SGIS OpenAPI3: 행정동 경계 + 총조사 주요지표.

집계구가 비공개·결측이면 행정동 단위로 상향하고 기준연도를 기록한다 (기획안 4.1).
지역 통계는 지역 우선순위로만 쓰고 개별 가구 특성으로 해석하지 않는다.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

from .common import get_json


def auth(base: str, key: str, secret: str) -> str:
    data = get_json(f"{base}/auth/authentication.json", {"consumer_key": key, "consumer_secret": secret})
    if str(data.get("errCd")) != "0":
        raise RuntimeError(f"SGIS 인증 실패: {data.get('errMsg')}")
    return data["result"]["accessToken"]


def _check(data: dict) -> list[dict]:
    if str(data.get("errCd")) != "0":
        raise RuntimeError(f"SGIS 오류: {data.get('errCd')} {data.get('errMsg')}")
    return data.get("result", [])


def admin_boundary(base: str, token: str, year: str, adm_cd: str) -> gpd.GeoDataFrame:
    """adm_cd(시군구 5자리 SGIS 코드) 하위 행정동 경계. SGIS 좌표계는 UTM-K(EPSG:5179)."""
    data = get_json(f"{base}/boundary/hadmarea.geojson",
                    {"accessToken": token, "year": year, "adm_cd": adm_cd, "low_search": 1})
    if "features" not in data:
        _check(data)
    return gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:5179")


def population_indicators(base: str, token: str, year: str, adm_cd: str) -> pd.DataFrame:
    rows = _check(get_json(f"{base}/stats/population.json",
                           {"accessToken": token, "year": year, "adm_cd": adm_cd, "low_search": 1}))
    df = pd.DataFrame(rows)
    num_cols = [c for c in df.columns if c not in ("adm_cd", "adm_nm")]
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce")
    df["stat_year"] = year
    df["stat_unit"] = "행정동"
    return df
