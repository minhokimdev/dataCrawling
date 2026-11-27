"""파이프라인 CLI. 단계별 산출물은 data/ 아래에 파일로 남겨 재현 가능하게 한다.

  coolroof ingest-team --src ~/Desktop/데이터크롤링   # 팀 수집 자료 → 결합 건물 + 대장 지붕 대리판독
  coolroof crawl-senior [--headed]
  coolroof compare-senior --public 경로당.csv --name-col 시설명 --addr-col 주소
  coolroof buildings --shp GIS건물통합정보.shp
  coolroof register
  coolroof sgis --adm-cd 21080
  coolroof join
  coolroof patches --ortho 정사영상.tif
  coolroof roof-rule
  coolroof split
  coolroof train
  coolroof score [--constructed 기시공명단.csv --constructed-addr-col 주소]
  coolroof export [--include-address]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import env, load_config


def _paths(cfg):
    p = cfg["paths"]
    return {
        "senior": p["raw"] / "senior_centers.csv",
        "senior_cmp": p["interim"] / "senior_compare.csv",
        "buildings": p["interim"] / "buildings.gpkg",
        "register": p["raw"] / "register_title.csv",
        "sgis_bnd": p["raw"] / "sgis_boundary.gpkg",
        "sgis_pop": p["raw"] / "sgis_population.csv",
        "joined": p["interim"] / "buildings_joined.gpkg",
        "facility_bld": p["interim"] / "senior_center_buildings.csv",
        "patches": p["interim"] / "patches",
        "roof": p["processed"] / "roof_rule.csv",
        "roof_register": p["processed"] / "roof_register.csv",
        "split": p["labels"] / "split.json",
        "scored": p["processed"] / "scored.gpkg",
        "sens": p["processed"] / "weight_sensitivity.csv",
    }


def cmd_crawl_senior(cfg, a):
    from .collect.common import write_meta
    from .collect.senior_center_crawler import SeniorCenterCrawler

    P = _paths(cfg)
    df = SeniorCenterCrawler(cfg, cfg["paths"]["raw"] / "crawl_senior", headless=not a.headed).run()
    gu = cfg["pilot"]["gu_name"]
    if "address" in df and gu:
        df["in_target_gu"] = df["address"].fillna("").str.contains(gu)
    df.to_csv(P["senior"], index=False, encoding="utf-8-sig")
    write_meta(P["senior"], "부산시 빅데이터웨이브 지도 기반 데이터(경로당 현황)", cfg["crawler"]["url"],
               license_note="화면에 공개된 시설 정보만 제한적으로 수집. 지도 배경·타일 미수집.")
    print(f"경로당 {len(df)}곳 수집 → {P['senior']}")


def cmd_compare_senior(cfg, a):
    from .join.facility_join import compare_with_public

    P = _paths(cfg)
    crawled = pd.read_csv(P["senior"])
    public = pd.read_csv(a.public, encoding=a.encoding)
    out = compare_with_public(crawled, public, a.name_col, a.addr_col)
    out.to_csv(P["senior_cmp"], index=False, encoding="utf-8-sig")
    print(out["status"].value_counts().to_string())


def cmd_buildings(cfg, a):
    from .collect.gis_building import load_building_shp

    P = _paths(cfg)
    gdf = load_building_shp(a.shp, cfg["gis_fields"], cfg["pilot"]["sigungu_cd"], cfg["crs"]["work"])
    gdf.to_file(P["buildings"], driver="GPKG")
    print(f"건물 도형 {len(gdf)}동 → {P['buildings']}")


def cmd_register(cfg, a):
    from .collect.building_register import fetch_title_for_dongs
    from .collect.common import write_meta

    P = _paths(cfg)
    b = gpd.read_file(P["buildings"], ignore_geometry=True)
    url = cfg["api"]["building_register_base"]
    df = fetch_title_for_dongs(url, env("DATA_GO_KR_KEY"), cfg["pilot"]["sigungu_cd"], b["bjdongCd"].unique(),
                               interval=cfg["api"]["request_interval_sec"])
    df.to_csv(P["register"], index=False, encoding="utf-8-sig")
    write_meta(P["register"], "국토교통부 건축HUB 건축물대장정보(15134735) 표제부", url)
    print(f"대장 표제부 {len(df)}건 → {P['register']}")


def cmd_sgis(cfg, a):
    from .collect import sgis
    from .collect.common import write_meta

    P = _paths(cfg)
    base, year = cfg["api"]["sgis_base"], cfg["api"]["sgis_year"]
    token = sgis.auth(base, env("SGIS_CONSUMER_KEY"), env("SGIS_CONSUMER_SECRET"))
    bnd = sgis.admin_boundary(base, token, year, a.adm_cd)
    pop = sgis.population_indicators(base, token, year, a.adm_cd)
    bnd.to_file(P["sgis_bnd"], driver="GPKG")
    pop.to_csv(P["sgis_pop"], index=False, encoding="utf-8-sig")
    write_meta(P["sgis_pop"], "통계청 SGIS 총조사 주요지표", base, {"year": year, "adm_cd": a.adm_cd})
    print(f"행정동 {len(bnd)}개, 지표 {len(pop)}행")


def cmd_join(cfg, a):
    from .join.building_join import join_buildings
    from .join.facility_join import attach_to_buildings

    P = _paths(cfg)
    gis = gpd.read_file(P["buildings"])
    reg = pd.read_csv(P["register"], dtype=str)
    joined = join_buildings(gis, reg, cfg)
    if P["sgis_bnd"].exists() and P["sgis_pop"].exists():
        bnd = gpd.read_file(P["sgis_bnd"]).to_crs(joined.crs)
        pop = pd.read_csv(P["sgis_pop"], dtype={"adm_cd": str})
        cent = joined[["bld_id", "geometry"]].copy()
        cent["geometry"] = cent.geometry.representative_point()
        hit = gpd.sjoin(cent, bnd[["adm_cd", "geometry"]], how="left", predicate="within")
        hit = hit.drop_duplicates("bld_id")[["bld_id", "adm_cd"]]
        joined = joined.merge(hit, on="bld_id", how="left").merge(pop, on="adm_cd", how="left")
    joined.to_file(P["joined"], driver="GPKG")
    print(joined["match_method"].value_counts().to_string())
    print(joined["confidence"].value_counts().to_string())
    if P["senior"].exists():
        fac = pd.read_csv(P["senior"])
        fb = attach_to_buildings(fac, joined, cfg["crs"]["work"], cfg["join"]["facility_snap_m"])
        fb.to_csv(P["facility_bld"], index=False, encoding="utf-8-sig")
        print(fb["fac_match"].value_counts().to_string())


def cmd_ingest_team(cfg, a):
    from .collect import team_data as td
    from .roof.register_proxy import roof_from_register

    P = _paths(cfg)
    src = Path(a.src).expanduser()
    work = cfg["crs"]["work"]
    b = td.load_buildings(src, work, cfg["join"]["area_ratio_ok"])
    bnd = td.load_admdong(Path(a.admdong), work)
    b = td.attach_region(b, bnd, td.load_senior_stats(src, a.year))
    b.to_file(P["joined"], driver="GPKG")
    roof = roof_from_register(b)
    roof.to_csv(P["roof_register"], index=False, encoding="utf-8-sig")
    print(f"건물 {len(b)}동 → {P['joined']}")
    print(b["confidence"].value_counts().to_string())
    print(f"행정동 미결합 {b['adm_cd'].isna().sum()}동, 통계 결측 {b['senior_population'].isna().sum()}동")
    print(roof["roof_type"].value_counts().to_string())


def cmd_patches(cfg, a):
    from .roof.patches import export_patches

    P = _paths(cfg)
    b = gpd.read_file(P["joined"])
    meta = export_patches(a.ortho, b, P["patches"], cfg["roof"]["patch_size"])
    pd.DataFrame(meta).to_csv(P["patches"] / "patches_meta.csv", index=False)
    print(f"패치 {len(meta)}개 → {P['patches']}")


def cmd_roof_rule(cfg, a):
    from PIL import Image

    from .roof.rule_baseline import classify_roof

    P = _paths(cfg)
    meta = pd.read_csv(P["patches"] / "patches_meta.csv")
    rows = []
    for r in meta.itertuples():
        img = np.asarray(Image.open(P["patches"] / "img" / f"{r.bld_id}.png").convert("RGB"))
        bm = np.asarray(Image.open(P["patches"] / "bmask" / f"{r.bld_id}.png")) > 0
        rows.append({"bld_id": r.bld_id, **classify_roof(img, bm, r.gsd_x, r.gsd_y, cfg)})
    df = pd.DataFrame(rows)
    df.to_csv(P["roof"], index=False)
    print(df["roof_type"].value_counts().to_string())


def cmd_split(cfg, a):
    from .evaluate.split import block_split

    P = _paths(cfg)
    labeled = {p.stem for p in (cfg["paths"]["labels"] / "mask").glob("*.png")}
    b = gpd.read_file(P["joined"])
    b = b[b["bld_id"].isin(labeled)]
    c = b.geometry.centroid
    s = cfg["model"]["split"]
    lab = block_split(c.x.values, c.y.values, s["block_size_m"], (s["train"], s["val"], s["test"]),
                      cfg["model"]["seed"])
    split = {k: b["bld_id"][lab == k].tolist() for k in ("train", "val", "test")}
    split["_seed"] = cfg["model"]["seed"]
    split["_block_size_m"] = s["block_size_m"]
    P["split"].write_text(json.dumps(split, ensure_ascii=False, indent=2))
    print({k: len(v) for k, v in split.items() if not k.startswith("_")})


def cmd_train(cfg, a):
    from .roof.model import train

    P = _paths(cfg)
    split = json.loads(P["split"].read_text())
    res = train(cfg, split, P["patches"] / "img", cfg["paths"]["labels"] / "mask",
                cfg["paths"]["outputs"] / "model" / cfg["model"]["arch"])
    print(res)


def cmd_score(cfg, a):
    from .join.normalize import normalize_address
    from .scoring import priority as pr

    P = _paths(cfg)
    sc = cfg["scoring"]
    b = gpd.read_file(P["joined"])
    roof_path = P["roof"] if P["roof"].exists() else P["roof_register"]   # 영상 판독이 있으면 우선
    print(f"지붕 판독: {roof_path.name}")
    roof = pd.read_csv(roof_path)
    d = b.merge(roof, on="bld_id", how="left")
    d["addr_key"] = d.get("platPlc", pd.Series("", index=d.index)).map(normalize_address)
    constructed = None
    if a.constructed:
        cdf = pd.read_csv(a.constructed, encoding=a.encoding)
        constructed = set(cdf[a.constructed_addr_col].map(normalize_address))
    d = pr.apply_exclusions(d, cfg, constructed)
    d["physical"] = pr.physical_fit(d)
    d["region_need"] = pr.region_need(d, sc["region_need_cols"])
    d["non_support"] = pr.non_support(d, constructed_known=constructed is not None)
    d["reliability"] = d["confidence"].map(sc["reliability_by_grade"]).astype(float)
    d = pr.rank(pr.combine(d, sc["weights"]))
    gpd.GeoDataFrame(d, geometry="geometry", crs=b.crs).to_file(P["scored"], driver="GPKG")
    live = d[d["exclude_reason"].isna()]
    pr.weight_sensitivity(live, sc["weights"], sc["top_n"], sc["sensitivity"]).to_csv(P["sens"], index=False)
    print(f"대상 {len(live)}동 / 제외 {d['exclude_reason'].notna().sum()}동 → {P['scored']}")


def cmd_export(cfg, a):
    from .export.gis import export_candidates

    P = _paths(cfg)
    d = gpd.read_file(P["scored"])
    print(export_candidates(d, cfg["paths"]["outputs"] / "candidates", cfg["scoring"]["top_n"], a.include_address))


def cmd_export_web(cfg, a):
    from .config import ROOT
    from .export.web import _seniors, build_bundle, demo_buildings

    P = _paths(cfg)
    raw, interim = cfg["paths"]["raw"], cfg["paths"]["interim"]
    if a.demo:
        b = demo_buildings(cfg, _seniors(P["senior"]))
    else:
        b = gpd.read_file(P["scored"]) if P["scored"].exists() else None
        if b is not None and a.limit:   # 부산 전역은 수십만 동이라 대시보드에는 상위 후보만 싣는다
            b = b[b["exclude_reason"].isna()].nsmallest(a.limit, "rank_main")
    bundle = build_bundle(cfg, b, raw, interim, a.include_address, is_demo=a.demo)
    out = ROOT / "web" / "public" / "data" / "bundle.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    print(f"건물 {len(bundle['buildings']['features'])}동, 경로당 {len(bundle['senior_centers'])}곳 → {out}"
          + (" (⚠ 합성 데모)" if a.demo else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="coolroof")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest-team", help="팀 수집 자료(건축물대장 폴리곤 매핑·SGIS 고령 통계) 적재")
    s.add_argument("--src", default="~/Desktop/데이터크롤링")
    s.add_argument("--admdong", default=str(Path(__file__).resolve().parents[2] / "data/raw/admdong/HangJeongDong_ver20241231.geojson"))
    s.add_argument("--year", type=int, default=None, help="고령 통계 연도(기본: 최신)")
    s.set_defaults(fn=cmd_ingest_team)
    s = sub.add_parser("crawl-senior"); s.add_argument("--headed", action="store_true"); s.set_defaults(fn=cmd_crawl_senior)
    s = sub.add_parser("compare-senior"); s.add_argument("--public", required=True)
    s.add_argument("--name-col", required=True); s.add_argument("--addr-col", required=True)
    s.add_argument("--encoding", default="utf-8-sig"); s.set_defaults(fn=cmd_compare_senior)
    s = sub.add_parser("buildings"); s.add_argument("--shp", required=True); s.set_defaults(fn=cmd_buildings)
    s = sub.add_parser("register"); s.set_defaults(fn=cmd_register)
    s = sub.add_parser("sgis"); s.add_argument("--adm-cd", required=True, help="SGIS 시군구 코드(5자리)"); s.set_defaults(fn=cmd_sgis)
    s = sub.add_parser("join"); s.set_defaults(fn=cmd_join)
    s = sub.add_parser("patches"); s.add_argument("--ortho", required=True); s.set_defaults(fn=cmd_patches)
    s = sub.add_parser("roof-rule"); s.set_defaults(fn=cmd_roof_rule)
    s = sub.add_parser("split"); s.set_defaults(fn=cmd_split)
    s = sub.add_parser("train"); s.set_defaults(fn=cmd_train)
    s = sub.add_parser("score"); s.add_argument("--constructed"); s.add_argument("--constructed-addr-col", default="주소")
    s.add_argument("--encoding", default="utf-8-sig"); s.set_defaults(fn=cmd_score)
    s = sub.add_parser("export"); s.add_argument("--include-address", action="store_true"); s.set_defaults(fn=cmd_export)
    s = sub.add_parser("export-web", help="React 대시보드용 web/public/data/bundle.json")
    s.add_argument("--include-address", action="store_true")
    s.add_argument("--demo", action="store_true", help="합성 건물로 화면 시연용 번들 생성")
    s.add_argument("--limit", type=int, default=3000, help="번들에 넣을 상위 후보 수(0=전체)")
    s.set_defaults(fn=cmd_export_web)

    a = ap.parse_args(argv)
    a.fn(load_config(a.config), a)


if __name__ == "__main__":
    main()
