"""팀 수집 자료 적재·대장 지붕 대리판독."""
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from coolroof.collect.team_data import attach_region
from coolroof.roof.register_proxy import classify, roof_from_register
from coolroof.scoring import priority as pr


def test_classify_rules():
    assert classify("(철근)콘크리트", "평스라브")[:2] == ("flat", 0.85)
    assert classify("(철근)콘크리트", "경사스라브")[0] == "pitched"
    assert classify("(철근)콘크리트", "스라브, 스레트")[1] == 0.5
    assert classify("기타지붕", "샌드위치판넬")[0] == "metal"
    assert classify("기타지붕", "초가")[0] == "pitched"
    assert classify("슬레이트", None)[0] == "pitched"
    t, p, _ = classify("기타지붕", "기타지붕")
    assert t == "unknown" and np.isnan(p)
    assert classify(None, None)[0] == "unknown"


def test_roof_from_register_and_physical():
    df = pd.DataFrame({"bld_id": ["a", "b", "c"], "roofCdNm": ["(철근)콘크리트", "기와", None],
                       "etcRoof": ["스라브", None, None], "poly_area_m2": [100.0, 80.0, 50.0],
                       "archArea": [90.0, 0.0, 55.0]})
    r = roof_from_register(df).set_index("bld_id")
    assert (r.loc["a", "area_low_m2"], r.loc["a", "area_high_m2"]) == (90.0, 100.0)
    assert r.loc["b", "area_low_m2"] == 80.0          # 건축면적 0 은 결측 취급
    phys = pr.physical_fit(r)
    assert np.isnan(phys["c"]) and phys["a"] > phys["b"]


def test_attach_region():
    crs = "EPSG:5186"
    bld = gpd.GeoDataFrame({"bld_id": ["x", "y"]}, geometry=[box(1, 1, 2, 2), box(20, 20, 21, 21)], crs=crs)
    bnd = gpd.GeoDataFrame({"adm_cd": ["21010510"]}, geometry=[box(0, 0, 10, 10)], crs=crs)
    stats = pd.DataFrame({"adm_cd": ["21010510"], "senior_population": [393]})
    out = attach_region(bld, bnd, stats).set_index("bld_id")
    assert out.loc["x", "senior_population"] == 393 and pd.isna(out.loc["y", "adm_cd"])
    assert abs(out.loc["x", "senior_population_per_km2"] - 393 / 1e-4) < 1e-6   # 10m×10m = 1e-4 ㎢


def test_align_split_dongs():
    from coolroof.collect.team_data import align_split_dongs
    s = pd.DataFrame({"adm_cd": ["21120561", "21120562", "21010510"], "senior_population": [10, 5, 7],
                      "adm_nm": ["강서구 녹산동", "강서구 신호동", "중구 중앙동"], "stat_year": ["2024"] * 3})
    out = align_split_dongs(s, {"21120560", "21010510"}).set_index("adm_cd")
    assert out.loc["21120560", "senior_population"] == 15 and "신호동" in out.loc["21120560", "adm_nm"]
    assert out.loc["21010510", "senior_population"] == 7
