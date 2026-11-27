"""경로당 수집 결과 ↔ 공공 CSV 대조, 그리고 건물 도형 결합 (기획안 4.1 공공자료 대조·분석 결합)."""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

from .normalize import facility_key


def compare_with_public(crawled: pd.DataFrame, public: pd.DataFrame,
                        name_col: str, addr_col: str) -> pd.DataFrame:
    """양쪽 일치 / 지도에만 있음 / 파일에만 있음 분류표."""
    pub = public.copy()
    pub["facility_key"] = [facility_key(n, a) for n, a in zip(pub[name_col], pub[addr_col])]
    m = crawled[["facility_key", "name", "address"]].merge(
        pub[["facility_key", name_col, addr_col]], on="facility_key", how="outer", indicator=True)
    m["status"] = m["_merge"].map({"both": "양쪽 일치", "left_only": "지도에만 있음", "right_only": "파일에만 있음"})
    return m.drop(columns="_merge")


def attach_to_buildings(facilities: pd.DataFrame, buildings: gpd.GeoDataFrame,
                        work_crs: str, snap_m: float) -> pd.DataFrame:
    """시설 좌표 → 건물 도형. 포함 건물이 없으면 snap_m 이내 최근접, 그래도 없거나 다수면 수동 검토."""
    pts = gpd.GeoDataFrame(facilities.copy(), geometry=gpd.points_from_xy(facilities["lon"], facilities["lat"]),
                           crs="EPSG:4326").to_crs(work_crs)
    b = buildings[["bld_id", "geometry"]]
    inside = gpd.sjoin(pts, b, how="left", predicate="within")
    counts = inside.groupby("facility_key")["bld_id"].nunique()
    rows = []
    for key, grp in inside.groupby("facility_key", sort=False):
        base = grp.iloc[0].drop(labels=["index_right"], errors="ignore")
        if counts[key] == 1:
            rows.append({**base.to_dict(), "fac_match": "within"})
            continue
        if counts[key] > 1:
            rows.append({**base.to_dict(), "bld_id": None, "fac_match": "manual_review(다중 건물)"})
            continue
        pt = pts.loc[pts["facility_key"] == key].iloc[[0]]
        near = gpd.sjoin_nearest(pt, b, how="left", max_distance=snap_m, distance_col="dist_m")
        if near["bld_id"].notna().any() and near["bld_id"].nunique() == 1:
            rows.append({**base.to_dict(), "bld_id": near["bld_id"].iloc[0], "fac_match": f"nearest<={snap_m}m"})
        else:
            rows.append({**base.to_dict(), "bld_id": None, "fac_match": "manual_review(도형 없음)"})
    return pd.DataFrame(rows).drop(columns="geometry", errors="ignore")
