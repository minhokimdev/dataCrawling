"""건물 도형: GIS건물통합정보 SHP(15083092) 우선, WFS(15123552)는 시범 호출용."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from .common import get_json


def load_building_shp(path: str | Path, fields: dict, sigungu_cd: str, work_crs: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path, encoding="cp949")
    missing = [v for v in fields.values() if v not in gdf.columns]
    if missing:
        raise KeyError(f"SHP 에 없는 컬럼: {missing}. config.gis_fields 를 실제 컬럼명으로 고치세요. "
                       f"(존재 컬럼: {list(gdf.columns)})")
    gdf = gdf.rename(columns={v: k for k, v in fields.items()})
    gdf["pnu"] = gdf["pnu"].astype(str)
    gdf = gdf[gdf["pnu"].str.startswith(sigungu_cd)].copy()
    return standardize(gdf, work_crs)


def fetch_wfs(url: str, service_key: str, typename: str, bbox: tuple[float, float, float, float],
              srs: str = "EPSG:4326", max_features: int = 1000) -> gpd.GeoDataFrame:
    params = {"serviceKey": service_key, "typename": typename, "srsName": srs,
              "bbox": ",".join(map(str, bbox)) + f",{srs}", "maxFeatures": max_features,
              "resultType": "results", "output": "application/json"}
    data = get_json(url, params)
    return gpd.GeoDataFrame.from_features(data.get("features", []), crs=srs)


def standardize(gdf: gpd.GeoDataFrame, work_crs: str) -> gpd.GeoDataFrame:
    gdf = gdf.to_crs(work_crs)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf["poly_area_m2"] = gdf.geometry.area
    for col in ("arch_area", "ground_floors"):
        if col in gdf.columns:
            gdf[col] = pd.to_numeric(gdf[col], errors="coerce")
    gdf["sigunguCd"] = gdf["pnu"].str[:5]
    gdf["bjdongCd"] = gdf["pnu"].str[5:10]
    return gdf
