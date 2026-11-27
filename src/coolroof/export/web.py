"""React 대시보드(web/)용 데이터 번들 생성: web/public/data/bundle.json.

점수 조합·순위는 프론트에서 가중치를 바꿔 다시 계산하므로, 여기서는 항목별 점수(0~100)와 근거만 내보낸다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

PROPS = ["bld_id", "physical", "region_need", "non_support", "reliability", "confidence",
         "roof_type", "flat_prob", "area_low_m2", "area_m2", "area_high_m2", "green_ratio", "white_ratio",
         "obstacle_ratio", "unreadable_reason", "match_method", "match_score", "missing_reason",
         "mainPurpsCdNm", "useAprDay", "exclude_reason", "adm_nm", "stat_year", "image_date",
         "roof_source", "roof_basis", "senior_population", "senior_single_households",
         "senior_population_per_km2", "senior_single_households_per_km2"]


def _clean(v):
    if v is None:
        return None
    if isinstance(v, (float, np.floating)):
        return None if np.isnan(v) else round(float(v), 4)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    return v


def _meta(cfg: dict, is_demo: bool) -> dict:
    sc = cfg["scoring"]
    scope = cfg.get("analysis", {})
    return {"gu_name": scope.get("scope_name") or cfg["pilot"]["gu_name"],
            "sigungu_cd": scope.get("scope_sigungu_cd"),
            "image_date": cfg["pilot"].get("image_date"), "analysis_base_date": cfg["pilot"].get("analysis_base_date"),
            "generated_at": datetime.now().isoformat(timespec="seconds"), "is_demo": is_demo,
            "weights": sc["weights"], "top_n": sc["top_n"], "sensitivity": sc["sensitivity"]}


def _seniors(path: Path) -> list[dict]:
    if not path.exists():
        return []
    df = pd.read_csv(path)
    cols = [c for c in ["facility_key", "name", "address", "category", "lon", "lat", "bld_id", "fac_match",
                        "in_target_gu"] if c in df.columns]
    return [{k: _clean(v) for k, v in r.items()} for r in df[cols].to_dict("records")]


def _crawl_stats(log_path: Path) -> dict | None:
    if not log_path.exists():
        return None
    cells = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if '"step": "cell"' in l]
    if not cells:
        return None
    keys = ["clicked", "ok", "dup", "no_popup"]
    return {"cells": len(cells), "cells_with_points": sum(1 for c in cells if c.get("clicked")),
            **{k: sum(c.get(k, 0) for c in cells) for k in keys},
            "started_at": cells[0]["ts"], "finished_at": cells[-1]["ts"]}


def build_bundle(cfg: dict, buildings: gpd.GeoDataFrame | None, raw_dir: Path, interim_dir: Path,
                 include_address: bool = False, is_demo: bool = False) -> dict:
    feats = []
    if buildings is not None and len(buildings):
        b = buildings.to_crs("EPSG:4326")
        props = [c for c in PROPS if c in b.columns]
        if include_address:
            props += [c for c in ("platPlc", "newPlatPlc") if c in b.columns]
        for _, r in b.iterrows():
            feats.append({"type": "Feature", "geometry": r.geometry.__geo_interface__,
                          "properties": {k: _clean(r[k]) for k in props}})
    fac_path = interim_dir / "senior_center_buildings.csv"
    seniors = _seniors(fac_path if fac_path.exists() else raw_dir / "senior_centers.csv")
    cmp_path = interim_dir / "senior_compare.csv"
    compare = None
    if cmp_path.exists():
        compare = pd.read_csv(cmp_path)["status"].value_counts().to_dict()
    return {"meta": _meta(cfg, is_demo), "buildings": {"type": "FeatureCollection", "features": feats},
            "senior_centers": seniors, "senior_compare": compare,
            "crawl_stats": _crawl_stats(raw_dir / "crawl_senior" / "crawl_log.jsonl")}


def demo_buildings(cfg: dict, seniors: list[dict], n: int = 220, seed: int = 7) -> gpd.GeoDataFrame:
    """⚠ 화면 시연용 합성 건물. 실제 건물·점수가 아니다 (meta.is_demo=true 로 표시됨)."""
    rng = np.random.default_rng(seed)
    if seniors:
        anchors = np.array([[s["lon"], s["lat"]] for s in seniors if s.get("lon") is not None])
    else:
        anchors = np.array([[128.993, 35.100]])
    work = cfg["crs"]["work"]
    pts = gpd.GeoSeries.from_xy(anchors[:, 0], anchors[:, 1], crs="EPSG:4326").to_crs(work)
    rows = []
    usages = ["단독주택", "공동주택", "노유자시설", "제1종근린생활시설", "공장", "교육연구시설"]
    for i in range(n):
        a = pts.iloc[rng.integers(len(pts))]
        x, y = a.x + rng.normal(0, 220), a.y + rng.normal(0, 220)
        w, h = rng.uniform(7, 22), rng.uniform(7, 18)
        roof = rng.choice(["flat", "pitched", "unreadable"], p=[0.62, 0.28, 0.10])
        area = w * h * rng.uniform(0.6, 0.9) if roof == "flat" else np.nan
        conf = rng.choice(["A", "B", "C"], p=[0.55, 0.3, 0.15])
        usage = rng.choice(usages, p=[0.38, 0.27, 0.08, 0.15, 0.07, 0.05])
        rows.append({
            "bld_id": f"DEMO-{i:04d}", "geometry": box(x, y, x + w, y + h),
            "roof_type": roof, "flat_prob": float(rng.uniform(0.6, 1)) if roof == "flat" else
            (float(rng.uniform(0, 0.4)) if roof == "pitched" else np.nan),
            "area_m2": area, "area_low_m2": area * 0.88 if roof == "flat" else np.nan,
            "area_high_m2": area * 1.15 if roof == "flat" else np.nan,
            "green_ratio": float(rng.uniform(0, 0.7)), "white_ratio": float(rng.uniform(0, 0.4)),
            "obstacle_ratio": float(rng.uniform(0, 0.25)),
            "unreadable_reason": "그림자·가림 과다" if roof == "unreadable" else None,
            "physical": float(rng.uniform(20, 100)) if roof == "flat" else
            (float(rng.uniform(0, 30)) if roof == "pitched" else np.nan),
            "region_need": float(rng.uniform(10, 100)),
            "non_support": np.nan if rng.random() < 0.5 else float(rng.choice([100, 50])),
            "reliability": {"A": 100.0, "B": 60.0, "C": 20.0}[conf], "confidence": conf,
            "match_method": {"A": "pnu_unique", "B": "pnu_area_name", "C": "manual_review"}[conf],
            "match_score": {"A": 0.92, "B": 0.66, "C": 0.41}[conf],
            "missing_reason": "한 필지 다수 동 자동 결합 보류" if conf == "C" else None,
            "mainPurpsCdNm": usage,
            "exclude_reason": None if usage in cfg["target_usages"] else "대상 용도 아님(대장)",
            "adm_nm": f"합성 행정동 {rng.integers(1, 6)}", "stat_year": cfg["api"]["sgis_year"],
            "image_date": "2025-09-01",
        })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=work)
