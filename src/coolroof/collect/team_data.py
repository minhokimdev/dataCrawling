"""팀원 수집 자료(~/Desktop/데이터크롤링)를 파이프라인 표준 컬럼으로 읽는다.

- 부산시_건축물대장_폴리곤_매핑/busan_bldg_pk_joined.gpkg
    건축HUB 표제부(2026-10 대용량 파일)를 GIS건물통합정보 WFS 도형에 관리건축물대장PK로 매핑한 결과(EPSG:4326).
- 부산시_인구통계/sgis_downloads/senior_population.csv, senior_single.csv
    SGIS 통계주제도 행정동별 65세 이상 인구·고령 1인가구 (2015~2024, SGIS 8자리 adm_cd).
- 행정동 경계: vuski/admdongkor ver20241231 (CC BY 4.0, 원자료 SGIS) — 인구통계 크롤러와 같은 코드 체계.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from ..join.building_join import area_similarity

# 팀 매핑 파일 컬럼 → 파이프라인(건축HUB API 필드명) 표준 컬럼
COLMAP = {
    "관리건축물대장PK": "mgmBldrgstPk", "건물명": "bldNm", "동명칭": "dongNm", "대지위치": "platPlc",
    "도로명대지위치": "newPlatPlc", "시군구코드": "sigunguCd", "법정동코드": "bjdongCd",
    "주부속구분코드": "mainAtchGbCd", "주용도코드명": "mainPurpsCdNm", "기타용도": "etcPurps",
    "건축면적(㎡)": "archArea", "연면적(㎡)": "totArea", "지상층수": "grndFlrCnt",
    "구조코드명": "strctCdNm", "지붕코드명": "roofCdNm", "기타지붕": "etcRoof", "사용승인일": "useAprDay",
    "PNU": "pnu", "id": "gis_id",
}

BLD_FILE = "부산시_건축물대장_폴리곤_매핑/busan_bldg_pk_joined.gpkg"
POP_FILE = "부산시_인구통계/sgis_downloads/senior_population.csv"
SINGLE_FILE = "부산시_인구통계/sgis_downloads/senior_single.csv"


def load_buildings(src: Path, work_crs: str, ok_ratio: float) -> gpd.GeoDataFrame:
    g = gpd.read_file(src / BLD_FILE, columns=list(COLMAP))
    g = g.rename(columns=COLMAP).to_crs(work_crs)
    g["poly_area_m2"] = g.area
    g["archArea"] = pd.to_numeric(g["archArea"], errors="coerce")
    g["bld_id"] = "B" + g["sigunguCd"].astype(str) + "-" + g["mgmBldrgstPk"].astype(str)
    # PK 로 직접 매핑된 자료라 결합 신뢰도는 도형 면적과 대장 건축면적의 정합으로만 판단한다.
    sim = [area_similarity(p, a, ok_ratio) for p, a in zip(g["poly_area_m2"], g["archArea"])]
    g["match_method"] = "pk_wfs"
    g["match_score"] = sim
    g["confidence"] = pd.cut(pd.Series(sim, index=g.index), [-1, 0.5, 0.8, 2], labels=["C", "B", "A"],
                             right=False).astype(str)
    g["missing_reason"] = None
    g.loc[g["match_score"] < 0.5, "missing_reason"] = "도형·대장 면적 불일치(증축·멸실·도형 오류 의심)"
    g.loc[g["archArea"].isna(), "missing_reason"] = "대장 건축면적 결측"
    g["source_date"] = "2026-10"          # 건축HUB 대용량 파일 기준월 (팀 KRAS 조사 노트)
    g["image_date"] = None
    g["geometry_version"] = "WFS lt_c_bldginfo"
    return g


def load_senior_stats(src: Path, year: int | None = None) -> pd.DataFrame:
    pop = pd.read_csv(src / POP_FILE, dtype={"adm_cd": str})
    single = pd.read_csv(src / SINGLE_FILE, dtype={"adm_cd": str})
    year = year or int(pop["year"].max())
    keys = ["adm_cd", "year"]
    d = pop.merge(single[keys + ["senior_single_households"]], on=keys, how="outer")
    d = d[d["year"] == year].drop(columns="year")
    d["stat_year"] = str(year)
    d["stat_unit"] = "행정동"
    d["adm_nm"] = d["sigungu"] + " " + d["eupmyeondong"]
    return d.drop(columns=["sigungu", "eupmyeondong"])


def load_admdong(path: Path, work_crs: str, sido: str = "26") -> gpd.GeoDataFrame:
    b = gpd.read_file(path)
    b = b[b["sido"] == sido][["adm_cd", "geometry"]]   # sido 는 행안부 코드(26), adm_cd 는 SGIS 코드(21…)
    return b.to_crs(work_crs)


def attach_region(bld: gpd.GeoDataFrame, bnd: gpd.GeoDataFrame, stats: pd.DataFrame) -> gpd.GeoDataFrame:
    """건물 대표점이 포함된 행정동의 집계 통계를 붙인다. 개인·가구 특성으로 해석하지 않는다."""
    pts = gpd.GeoDataFrame(bld[["bld_id"]], geometry=bld.geometry.representative_point(), crs=bld.crs)
    hit = gpd.sjoin(pts, bnd, how="left", predicate="within").drop_duplicates("bld_id")[["bld_id", "adm_cd"]]
    st = align_split_dongs(stats, set(bnd["adm_cd"]))
    # 인원·가구 '수'는 행정동 크기에 비례하므로 면적당 밀도(명/㎢)를 함께 만든다.
    st = st.merge(pd.DataFrame({"adm_cd": bnd["adm_cd"], "adm_area_km2": bnd.area / 1e6}), on="adm_cd", how="left")
    for c in ("senior_population", "senior_single_households"):
        if c in st:
            st[f"{c}_per_km2"] = st[c] / st["adm_area_km2"]
    return bld.merge(hit, on="bld_id", how="left").merge(st, on="adm_cd", how="left")


def align_split_dongs(stats: pd.DataFrame, bnd_codes: set[str]) -> pd.DataFrame:
    """통계에는 분동된 코드(예: 녹산동 21120561·신호동 21120562)가 있는데 경계는 분동 전 코드(21120560)만
    있으면, 끝자리를 0으로 바꾼 상위 코드로 인원·가구 수를 합산한다."""
    s = stats.copy()
    parent = s["adm_cd"].str[:7] + "0"
    remap = ~s["adm_cd"].isin(bnd_codes) & parent.isin(bnd_codes)
    if not remap.any():
        return s
    s.loc[remap, "adm_cd"] = parent[remap]
    num = s.select_dtypes("number").columns.tolist()
    agg = {c: "sum" for c in num} | {c: "first" for c in s.columns if c not in num + ["adm_cd"]}
    agg["adm_nm"] = lambda x: "+".join(x)
    return s.groupby("adm_cd", as_index=False).agg(agg)
