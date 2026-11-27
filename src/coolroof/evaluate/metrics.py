"""평가 지표 (기획안 3장, 5.2, 6장)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def confusion(gt: np.ndarray, pred: np.ndarray, n: int) -> np.ndarray:
    g, p = np.asarray(gt).ravel(), np.asarray(pred).ravel()
    ok = (g >= 0) & (g < n)
    return np.bincount(n * g[ok] + p[ok], minlength=n * n).reshape(n, n)


def per_class_iou(gt: np.ndarray, pred: np.ndarray, n: int) -> np.ndarray:
    cm = confusion(gt, pred, n)
    inter = np.diag(cm).astype(float)
    union = cm.sum(0) + cm.sum(1) - np.diag(cm)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(union > 0, inter / union, np.nan)


def per_class_recall(gt: np.ndarray, pred: np.ndarray, n: int) -> np.ndarray:
    cm = confusion(gt, pred, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cm.sum(1) > 0, np.diag(cm) / cm.sum(1), np.nan)


def binary_pr(gt: np.ndarray, pred: np.ndarray) -> dict:
    """건물 단위 평지붕 여부 정밀도/재현율."""
    g, p = np.asarray(gt, bool), np.asarray(pred, bool)
    tp, fp, fn = int((g & p).sum()), int((~g & p).sum()), int((g & ~p).sum())
    return {"precision": tp / (tp + fp) if tp + fp else np.nan,
            "recall": tp / (tp + fn) if tp + fn else np.nan, "tp": tp, "fp": fp, "fn": fn}


def median_abs_area_error(true_m2, est_m2) -> float:
    t, e = np.asarray(true_m2, float), np.asarray(est_m2, float)
    ok = ~np.isnan(t) & ~np.isnan(e)
    return float(np.median(np.abs(t[ok] - e[ok]))) if ok.any() else np.nan


def precision_at_n(ranked_ids: list, useful_ids: set, n: int) -> float:
    """상위 N 현장조사 건물 중 담당자가 '검토할 가치가 있다'고 판정한 비율. 미조사 건은 분모에서 제외하지 않는다."""
    top = list(ranked_ids)[:n]
    return sum(1 for i in top if i in useful_ids) / len(top) if top else np.nan


def group_error_rates(df: pd.DataFrame, group_col: str, gt_col: str, pred_col: str) -> pd.DataFrame:
    """동별/건물 유형별 오탐·미탐률 (공정성·오류 지표)."""
    def agg(g):
        gt, pr = g[gt_col].astype(bool), g[pred_col].astype(bool)
        return pd.Series({"n": len(g),
                          "false_pos_rate": (pr & ~gt).sum() / max((~gt).sum(), 1),
                          "false_neg_rate": (~pr & gt).sum() / max(gt.sum(), 1)})
    return df.groupby(group_col).apply(agg, include_groups=False).reset_index()


def calibration_table(prob: np.ndarray, gt: np.ndarray, bins: int = 5) -> pd.DataFrame:
    """신뢰도 구간별 실제 정답률."""
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(prob, edges) - 1, 0, bins - 1)
    df = pd.DataFrame({"bin": idx, "prob": prob, "gt": np.asarray(gt, float)})
    out = df.groupby("bin").agg(n=("gt", "size"), mean_prob=("prob", "mean"), accuracy=("gt", "mean")).reset_index()
    out["range"] = [f"{edges[b]:.1f}-{edges[b+1]:.1f}" for b in out["bin"]]
    return out
