"""우선순위 모형 (기획안 6장).

S = 0.40×물리적 적합성 + 0.35×지역 필요도 + 0.15×미지원 가능성 + 0.10×자료 신뢰도 (각 0~100)
- 결측 항목은 0점 처리하지 않는다: score_low(결측=0) ~ score_high(결측=100) 범위와 결측 목록을 표시.
- 확인 가능한 항목만으로 가중치를 재정규화한 보조 순위(score_reweighted)를 함께 제시.
- 자료 신뢰도는 점수에 소폭 반영하되 A/B/C 등급으로 별도 표시.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COMPONENTS = ["physical", "region_need", "non_support", "reliability"]


def pct_rank(s: pd.Series) -> pd.Series:
    """0~100 정규화(백분위). 결측은 결측 유지."""
    return s.rank(pct=True, method="average") * 100


def apply_exclusions(df: pd.DataFrame, cfg: dict, constructed_keys: set[str] | None = None) -> pd.DataFrame:
    """1차 제외: 관할 구 밖, 대장상 명백한 비대상 용도, 공식 명단상 동일 사업 기시공."""
    d = df.copy()
    reason = pd.Series(None, index=d.index, dtype=object)
    scope = cfg.get("analysis", {}).get("scope_sigungu_cd")   # null 이면 부산 전역: 구 필터 없음
    if scope:
        reason[d["sigunguCd"].astype(str) != scope] = "관할 구 밖"
    usage = d.get("mainPurpsCdNm")
    if usage is not None:
        known = usage.notna()
        non_target = known & ~usage.isin(cfg["target_usages"])
        reason[non_target & reason.isna()] = "대상 용도 아님(대장)"
    if constructed_keys:
        hit = d["addr_key"].isin(constructed_keys) if "addr_key" in d else pd.Series(False, index=d.index)
        reason[hit & reason.isna()] = "기시공(공식 명단)"
    d["exclude_reason"] = reason
    return d


def physical_fit(roof: pd.DataFrame) -> pd.Series:
    """평지붕 가능성 × 가시 면적(백분위) × (1-장애물 비율). 판독 불가(unreadable·unknown)는 결측."""
    area_score = pct_rank(roof["area_m2"].where(roof["roof_type"] == "flat"))
    s = roof["flat_prob"] * area_score.fillna(0) * (1 - roof["obstacle_ratio"].fillna(0))
    s = pct_rank(s)
    return s.where(~roof["roof_type"].isin(["unreadable", "unknown"]))


def region_need(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """실제 제공되는 집계 지표(예: 고령인구 비율, 노후주택 비율)의 백분위 평균."""
    present = [c for c in cols if c in df]
    if not present:
        return pd.Series(np.nan, index=df.index)
    return pd.concat([pct_rank(df[c]) for c in present], axis=1).mean(axis=1, skipna=False)


def non_support(df: pd.DataFrame, constructed_known: bool, image_after_list: pd.Series | None = None) -> pd.Series:
    """기시공 명단이 확보되면 명단에 없는 건물=100, 명단 시점 이후 촬영 영상과 상충하면 50. 명단 없으면 결측."""
    if not constructed_known:
        return pd.Series(np.nan, index=df.index)
    s = pd.Series(100.0, index=df.index)
    if image_after_list is not None:
        s[image_after_list.fillna(False)] = 50.0
    return s


def combine(df: pd.DataFrame, weights: dict) -> pd.DataFrame:
    d = df.copy()
    w = pd.Series(weights)[COMPONENTS]
    comp = d[COMPONENTS].astype(float)
    d["score_low"] = (comp.fillna(0) * w).sum(axis=1)
    d["score_high"] = (comp.fillna(100) * w).sum(axis=1)
    has = comp.notna()
    d["score"] = d["score_low"].where(has.all(axis=1))
    w_avail = has.mul(w, axis=1).sum(axis=1)
    d["score_reweighted"] = (comp.fillna(0) * w).sum(axis=1) / w_avail.replace(0, np.nan)
    d["missing_components"] = has.apply(lambda r: ",".join(c for c in COMPONENTS if not r[c]), axis=1)
    return d


def rank(d: pd.DataFrame) -> pd.DataFrame:
    """주 순위: 결측 없는 건 score, 결측 있는 건 보수적 score_low. 보조 순위: score_reweighted."""
    d = d.copy()
    live = d["exclude_reason"].isna() if "exclude_reason" in d else pd.Series(True, index=d.index)
    d["rank_main"] = d["score"].fillna(d["score_low"]).where(live).rank(ascending=False, method="first")
    d["rank_aux"] = d["score_reweighted"].where(live).rank(ascending=False, method="first")
    return d.sort_values("rank_main")


def weight_sensitivity(df: pd.DataFrame, weights: dict, top_n: int, delta: float = 0.2) -> pd.DataFrame:
    """각 가중치를 ±delta 바꾸거나 항목을 제외했을 때 Top N 교체율."""
    base = set(rank(combine(df, weights)).head(top_n).index)
    rows = []
    for c in COMPONENTS:
        for label, factor in ((f"+{int(delta*100)}%", 1 + delta), (f"-{int(delta*100)}%", 1 - delta), ("제외", 0.0)):
            w = dict(weights)
            w[c] *= factor
            tot = sum(w.values())
            w = {k: v / tot for k, v in w.items()}
            top = set(rank(combine(df, w)).head(top_n).index)
            rows.append({"component": c, "change": label, "top_n_turnover": 1 - len(base & top) / max(len(base), 1)})
    return pd.DataFrame(rows)
