"""합성 데이터로 결합 → 지붕 → 점수 → 산출물까지 한 번에 돌려본다."""
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from coolroof.export.gis import export_candidates
from coolroof.join.building_join import join_buildings
from coolroof.join.facility_join import attach_to_buildings, compare_with_public
from coolroof.scoring import priority as pr

SG = "26380"


def _gis(cfg):
    # pnu 별: P1 단일 동(면적 일치), P2 두 동(대장 2건), P3 대장 없음, P4 단일 동(면적 불일치)
    rows = [
        ("g1", f"{SG}10100" + "1" + "0001" + "0000", box(0, 0, 10, 10), None, None),
        ("g2", f"{SG}10100" + "1" + "0002" + "0000", box(30, 0, 40, 10), "행복빌라", "가동"),
        ("g3", f"{SG}10100" + "1" + "0002" + "0000", box(45, 0, 50, 5), "행복빌라", "나동"),
        ("g4", f"{SG}10100" + "1" + "0003" + "0000", box(60, 0, 70, 10), None, None),
        ("g5", f"{SG}10100" + "1" + "0004" + "0000", box(90, 0, 100, 10), None, None),
    ]
    g = gpd.GeoDataFrame(rows, columns=["gis_id", "pnu", "geometry", "building_name", "dong_name"],
                         crs=cfg["crs"]["work"])
    g["poly_area_m2"] = g.area
    g["base_date"] = "2026-06-30"
    g["sigunguCd"] = g["pnu"].str[:5]
    g["bjdongCd"] = g["pnu"].str[5:10]
    return g


def _register():
    return pd.DataFrame([
        dict(mgmBldrgstPk="R1", sigunguCd=SG, bjdongCd="10100", platGbCd="0", bun="1", ji="0",
             archArea="98", mainPurpsCdNm="단독주택", mainAtchGbCdNm="주건축물", bldNm="", dongNm="",
             platPlc="부산광역시 사하구 괴정동 1"),
        dict(mgmBldrgstPk="R2", sigunguCd=SG, bjdongCd="10100", platGbCd="0", bun="2", ji="0",
             archArea="100", mainPurpsCdNm="공동주택", mainAtchGbCdNm="주건축물", bldNm="행복빌라", dongNm="가동",
             platPlc="부산광역시 사하구 괴정동 2"),
        dict(mgmBldrgstPk="R3", sigunguCd=SG, bjdongCd="10100", platGbCd="0", bun="2", ji="0",
             archArea="25", mainPurpsCdNm="공동주택", mainAtchGbCdNm="주건축물", bldNm="행복빌라", dongNm="나동",
             platPlc="부산광역시 사하구 괴정동 2"),
        dict(mgmBldrgstPk="R5", sigunguCd=SG, bjdongCd="10100", platGbCd="0", bun="4", ji="0",
             archArea="20", mainPurpsCdNm="공장", mainAtchGbCdNm="주건축물", bldNm="", dongNm="",
             platPlc="부산광역시 사하구 괴정동 4"),
    ])


def test_building_join_rules(cfg):
    j = join_buildings(_gis(cfg), _register(), cfg).set_index("gis_id")
    assert j.loc["g1", "match_method"] == "pnu_unique" and j.loc["g1", "mgmBldrgstPk"] == "R1"
    assert j.loc["g1", "confidence"] == "A"
    # 다수 동이지만 이름+면적이 명확하면 자동 결합
    assert j.loc["g2", "mgmBldrgstPk"] == "R2" and j.loc["g3", "mgmBldrgstPk"] == "R3"
    assert j.loc["g4", "match_method"] == "none" and "대장 없음" in j.loc["g4", "missing_reason"]
    assert j.loc["g5", "missing_reason"].startswith("면적 불일치")
    for col in ["match_method", "match_score", "source_date", "image_date", "geometry_version", "missing_reason"]:
        assert col in j.columns


def test_facility_compare_and_attach(cfg):
    crawled = pd.DataFrame({"facility_key": ["괴정|부산사하구괴정동1", "다대|부산사하구다대동9"],
                            "name": ["괴정경로당", "다대경로당"], "address": ["", ""],
                            "lon": [0.0, 0.0], "lat": [0.0, 0.0]})
    public = pd.DataFrame({"시설명": ["괴정 경로당", "신평경로당"], "주소": ["부산광역시 사하구 괴정동 1", "사하구 신평동 3"]})
    cmp = compare_with_public(crawled, public, "시설명", "주소")
    assert set(cmp["status"]) == {"양쪽 일치", "지도에만 있음", "파일에만 있음"}

    b = join_buildings(_gis(cfg), _register(), cfg)
    pts = gpd.GeoSeries.from_xy([5, 200], [5, 200], crs=cfg["crs"]["work"]).to_crs("EPSG:4326")
    fac = pd.DataFrame({"facility_key": ["a", "b"], "lon": pts.x, "lat": pts.y})
    out = attach_to_buildings(fac, b, cfg["crs"]["work"], 10).set_index("facility_key")
    assert out.loc["a", "fac_match"] == "within"
    assert out.loc["b", "fac_match"].startswith("manual_review")


def test_scoring_and_export(cfg, tmp_path):
    b = join_buildings(_gis(cfg), _register(), cfg)
    roof = pd.DataFrame({"bld_id": b["bld_id"],
                         "roof_type": ["flat", "flat", "pitched", "unreadable", "flat"],
                         "flat_prob": [0.9, 0.8, 0.1, np.nan, 0.95],
                         "area_m2": [90, 80, np.nan, np.nan, 85], "area_low_m2": [80, 70, np.nan, np.nan, 75],
                         "area_high_m2": [95, 85, np.nan, np.nan, 90], "obstacle_ratio": [0.0, 0.1, 0.0, np.nan, 0.0]})
    d = b.merge(roof, on="bld_id")
    d["senior_population"] = [3000, 2000, 2000, 1000, 2500]
    d["senior_single_households"] = [400, 300, 300, 200, 350]
    d = pr.apply_exclusions(d, cfg)
    assert d.set_index("gis_id").loc["g5", "exclude_reason"] == "대상 용도 아님(대장)"
    d["physical"] = pr.physical_fit(d)
    d["region_need"] = pr.region_need(d, cfg["scoring"]["region_need_cols"])
    d["non_support"] = pr.non_support(d, constructed_known=False)   # 명단 없음 → 결측
    d["reliability"] = d["confidence"].map(cfg["scoring"]["reliability_by_grade"]).astype(float)
    d = pr.rank(pr.combine(d, cfg["scoring"]["weights"]))

    assert d["score"].isna().all()                       # 결측을 0점으로 숨기지 않음
    assert (d["score_high"] - d["score_low"] >= 15 - 1e-9).all()
    assert d["missing_components"].str.contains("non_support").all()
    top = d.dropna(subset=["rank_main"]).iloc[0]
    assert top["gis_id"] == "g1"

    sens = pr.weight_sensitivity(d[d["exclude_reason"].isna()], cfg["scoring"]["weights"], 2)
    assert len(sens) == 12 and sens["top_n_turnover"].between(0, 1).all()

    res = export_candidates(gpd.GeoDataFrame(d, geometry="geometry", crs=b.crs), tmp_path, 3)
    assert res["top"] == 3
    for f in ["candidates_top.csv", "manual_review.csv", "candidates_top.geojson", "candidates_map.html"]:
        assert (tmp_path / f).exists()
    top_csv = pd.read_csv(tmp_path / "candidates_top.csv")
    assert "platPlc" not in top_csv.columns              # 기본 공개본은 주소 제외
