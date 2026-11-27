"""건물 단위 결합 규칙 (기획안 4.2).

- GIS 원본 ID 와 대장 원본 PK 는 그대로 보존하고 별도 내부 건물 ID(bld_id) 발급.
- 1차: PNU(시군구+법정동+대지구분+본번+부번)로 대장 조회.
- 2차: 도형 면적 vs 대장 건축면적, 건물명/동명, 주/부속 구분 대조.
- 한 필지 다수 동, 시점 불일치는 자동 매칭하지 않고 manual_review.
- 결과에 match_method, match_score, source_date, image_date, geometry_version, missing_reason 기록.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from ..collect.building_register import register_pnu

JOIN_COLUMNS = ["bld_id", "gis_id", "mgmBldrgstPk", "match_method", "match_score", "confidence",
                "source_date", "image_date", "geometry_version", "missing_reason"]


def area_similarity(poly_area: float, reg_area: float, ok_ratio: float) -> float:
    """1.0 = 동일, ok_ratio 경계에서 0.5, 그 밖으로 갈수록 0 으로."""
    if not (poly_area > 0 and reg_area > 0):
        return 0.0
    r = min(poly_area, reg_area) / max(poly_area, reg_area)
    if r >= ok_ratio:
        return 0.5 + 0.5 * (r - ok_ratio) / (1 - ok_ratio)
    return 0.5 * r / ok_ratio


def _name_hit(gis_row: pd.Series, reg_row: pd.Series) -> bool:
    gname = f"{gis_row.get('building_name') or ''}{gis_row.get('dong_name') or ''}".replace(" ", "")
    rname = f"{reg_row.get('bldNm') or ''}{reg_row.get('dongNm') or ''}".replace(" ", "")
    return bool(gname) and bool(rname) and (gname in rname or rname in gname)


def grade(score: float, method: str) -> str:
    if method in ("none", "manual_review"):
        return "C"
    if score >= 0.8:
        return "A"
    if score >= 0.5:
        return "B"
    return "C"


def join_buildings(gis: gpd.GeoDataFrame, register: pd.DataFrame, cfg: dict) -> gpd.GeoDataFrame:
    ok_ratio = cfg["join"]["area_ratio_ok"]
    margin = cfg["join"]["unique_margin"]
    reg = register.copy()
    reg["pnu"] = register_pnu(reg)
    reg["archArea"] = pd.to_numeric(reg.get("archArea"), errors="coerce")
    is_main = reg.get("mainAtchGbCdNm", pd.Series("주건축물", index=reg.index)).fillna("") != "부속건축물"
    by_pnu = {k: g for k, g in reg[is_main].groupby("pnu")}
    gis_per_pnu = gis.groupby("pnu").size()

    out = []
    for i, row in enumerate(gis.itertuples(index=False)):
        r = pd.Series(row._asdict())
        rec = {"bld_id": f"B{r['pnu'][:5]}-{i:06d}", "gis_id": r.get("gis_id"), "mgmBldrgstPk": None,
               "match_method": "none", "match_score": 0.0, "missing_reason": None,
               "source_date": r.get("base_date"), "image_date": cfg["pilot"].get("image_date"),
               "geometry_version": r.get("base_date")}
        cands = by_pnu.get(r["pnu"])
        if cands is None or cands.empty:
            rec["missing_reason"] = "대장 없음(PNU 불일치)"
        else:
            scores = []
            for _, c in cands.iterrows():
                s = area_similarity(r["poly_area_m2"], c["archArea"], ok_ratio)
                if _name_hit(r, c):
                    s = min(1.0, s + 0.3)
                scores.append(s)
            order = np.argsort(scores)[::-1]
            best = float(scores[order[0]])
            second = float(scores[order[1]]) if len(order) > 1 else 0.0
            multi = len(cands) > 1 or gis_per_pnu.get(r["pnu"], 1) > 1
            if not multi:
                rec.update(match_method="pnu_unique", match_score=best)
                rec["mgmBldrgstPk"] = cands.iloc[order[0]]["mgmBldrgstPk"]
                if best < 0.5:
                    rec["missing_reason"] = "면적 불일치(신축·증축·멸실 의심)"
            elif best >= 0.8 and best - second >= margin:
                rec.update(match_method="pnu_area_name", match_score=best)
                rec["mgmBldrgstPk"] = cands.iloc[order[0]]["mgmBldrgstPk"]
            else:
                rec.update(match_method="manual_review", match_score=best,
                           missing_reason=f"한 필지 다수 동(후보 {len(cands)}개) 자동 결합 보류")
        rec["confidence"] = grade(rec["match_score"], rec["match_method"])
        out.append(rec)

    joined = gis.reset_index(drop=True).join(pd.DataFrame(out).drop(columns=["gis_id"]))
    reg_cols = [c for c in ["mgmBldrgstPk", "mainPurpsCdNm", "strctCdNm", "roofCdNm", "archArea",
                            "grndFlrCnt", "useAprDay", "platPlc", "newPlatPlc", "bldNm"] if c in reg.columns]
    return joined.merge(reg[reg_cols], on="mgmBldrgstPk", how="left")
