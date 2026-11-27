"""산출물: 후보 Top N CSV, GIS(GeoJSON), 신뢰도별 지도(HTML), 개별 근거 카드 (기획안 8장 ⑤)."""
from __future__ import annotations

import json
from pathlib import Path

import folium
import geopandas as gpd

CARD_FIELDS = ["bld_id", "rank_main", "rank_aux", "score", "score_low", "score_high", "score_reweighted",
               "missing_components", "physical", "region_need", "non_support", "reliability", "confidence",
               "roof_type", "flat_prob", "area_low_m2", "area_m2", "area_high_m2", "green_ratio", "white_ratio",
               "image_date", "match_method", "match_score", "mainPurpsCdNm", "stat_year", "stat_unit",
               "exclude_reason", "field_check_reason"]

COLORS = {"A": "#2b8a3e", "B": "#f08c00", "C": "#c92a2a"}


def export_candidates(gdf: gpd.GeoDataFrame, out_dir: str | Path, top_n: int, include_address: bool = False) -> dict:
    """include_address=False 가 기본: 대외 공개본은 주소·영상·개인정보 허용 범위에 맞춰 별도 생성."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    gdf = gdf.copy()
    if "field_check_reason" not in gdf:
        gdf["field_check_reason"] = None
    fields = [c for c in CARD_FIELDS if c in gdf.columns]
    if include_address:
        fields += [c for c in ("platPlc", "newPlatPlc") if c in gdf.columns]
    live = gdf[gdf["exclude_reason"].isna()] if "exclude_reason" in gdf else gdf
    top = live.sort_values("rank_main").head(top_n)
    # 모든 건물에서 결측인 항목(예: 기시공 명단 미확보 → non_support)은 건물별 검토 사유가 아니므로 제외한다.
    miss = live["missing_components"].fillna("").str.split(",")
    universal = set.intersection(*map(set, miss)) - {""} if len(live) else set()
    own_missing = miss.map(lambda m: bool(set(m) - universal - {""}))
    review = live[live["confidence"].eq("C") | own_missing]

    top[fields].to_csv(out / "candidates_top.csv", index=False, encoding="utf-8-sig")
    review[fields].to_csv(out / "manual_review.csv", index=False, encoding="utf-8-sig")
    top[fields + ["geometry"]].to_crs("EPSG:4326").to_file(out / "candidates_top.geojson", driver="GeoJSON")

    cards = out / "cards"
    cards.mkdir(exist_ok=True)
    for rec in top[fields].to_dict("records"):
        (cards / f"{rec['bld_id']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    wgs = top.to_crs("EPSG:4326")
    c = wgs.geometry.union_all().centroid if len(wgs) else None
    fmap = folium.Map(location=[c.y, c.x] if c else [35.1, 129.0], zoom_start=15, tiles="OpenStreetMap")
    for _, r in wgs.iterrows():
        tip = (f"#{int(r['rank_main'])} {r['bld_id']} | 점수 {r.get('score_low', 0):.1f}~{r.get('score_high', 0):.1f}"
               f" | 신뢰도 {r.get('confidence')}")
        folium.GeoJson(r.geometry.__geo_interface__, tooltip=tip,
                       style_function=lambda _, col=COLORS.get(r.get("confidence"), "#555"): {
                           "color": col, "fillColor": col, "weight": 2, "fillOpacity": 0.5}).add_to(fmap)
    fmap.save(out / "candidates_map.html")
    return {"top": len(top), "manual_review": len(review), "dir": str(out)}
