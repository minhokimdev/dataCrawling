"""규칙 기반 기준선 (기획안 5.1): 영상·건물 폴리곤 중첩 + 밝기·색상 규칙.

- 평지붕/경사지붕: 건물 주축으로 양분했을 때 두 면의 밝기 차가 크면 경사지붕(용마루 양쪽 음영 차).
- 녹색·흰색 비율은 '관찰값'으로만 기록한다. 방수 완료·기시공 여부로 변환하지 않는다.
- 그림자 비율이 높거나 건물 픽셀이 너무 적으면 판독 불가로 분리한다.
"""
from __future__ import annotations

import numpy as np

from .area import area_interval


def rgb_to_hsv(img: np.ndarray) -> np.ndarray:
    x = img.astype(np.float32) / 255.0
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    mx, mn = x.max(-1), x.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    nz = d > 1e-6
    rm = nz & (mx == r)
    gm = nz & (mx == g) & ~rm
    bm = nz & ~rm & ~gm
    h[rm] = ((g - b)[rm] / d[rm]) % 6
    h[gm] = (b - r)[gm] / d[gm] + 2
    h[bm] = (r - g)[bm] / d[bm] + 4
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0)
    return np.stack([h * 60, s, mx], -1)


def _principal_halves(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.nonzero(mask)
    pts = np.stack([xs, ys], 1).astype(float)
    pts -= pts.mean(0)
    _, vecs = np.linalg.eigh(np.cov(pts.T))
    major = vecs[:, -1]
    # 주축에 수직인 방향으로 투영해 용마루(주축) 기준 양쪽으로 나눔
    minor = np.array([-major[1], major[0]])
    side = pts @ minor > 0
    a = np.zeros_like(mask)
    b = np.zeros_like(mask)
    a[ys[side], xs[side]] = True
    b[ys[~side], xs[~side]] = True
    return a, b


def classify_roof(img: np.ndarray, bmask: np.ndarray, gsd_x: float, gsd_y: float, cfg: dict) -> dict:
    rc = cfg["roof"]
    n = int(bmask.sum())
    out = {"roof_type": "unreadable", "flat_prob": np.nan, "green_ratio": np.nan, "white_ratio": np.nan,
           "shadow_ratio": np.nan, "obstacle_ratio": np.nan, "half_diff": np.nan,
           "area_m2": np.nan, "area_low_m2": np.nan, "area_high_m2": np.nan, "unreadable_reason": None}
    if n < rc["min_building_px"]:
        out["unreadable_reason"] = "건물 픽셀 부족"
        return out
    hsv = rgb_to_hsv(img)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    shadow = bmask & (v < rc["shadow_v"])
    white = bmask & (s < rc["white_s"]) & (v > rc["white_v"])
    green = bmask & (h > 80) & (h < 170) & (s > 0.2) & (v > rc["shadow_v"])
    # 장애물(설비 등): 지붕 평균과 밝기가 크게 다른 작은 덩어리 → 간단히 국소 이상치로 근사
    vb = v[bmask & ~shadow]
    mu, sd = (float(vb.mean()), float(vb.std())) if vb.size else (0.0, 0.0)
    obstacle = bmask & ~shadow & (np.abs(v - mu) > 2.5 * max(sd, 1e-3))
    out.update(green_ratio=float(green.sum() / n), white_ratio=float(white.sum() / n),
               shadow_ratio=float(shadow.sum() / n), obstacle_ratio=float(obstacle.sum() / n))
    if out["shadow_ratio"] > rc["unreadable_shadow_ratio"]:
        out["unreadable_reason"] = "그림자·가림 과다"
        return out
    a, b = _principal_halves(bmask & ~shadow)
    va, vb2 = v[a], v[b]
    diff = abs(float(va.mean()) - float(vb2.mean())) if va.size and vb2.size else 0.0
    out["half_diff"] = diff
    thr = rc["pitched_half_diff"]
    out["flat_prob"] = float(np.clip(1 - diff / (2 * thr), 0, 1))
    out["roof_type"] = "flat" if diff < thr else "pitched"
    if out["roof_type"] == "flat":
        flat_visible = bmask & ~shadow & ~obstacle
        out.update(area_interval(flat_visible, gsd_x, gsd_y, occluded=shadow))
        out.pop("px_area_m2", None)
    return out
