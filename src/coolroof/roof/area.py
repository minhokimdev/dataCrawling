"""면적 산정 (기획안 5.1): 픽셀당 지상면적 × 분할 픽셀 수, 경계 오차·가림 비율을 반영한 구간값.

70㎡ 는 공고 확인 전 필터로 쓰지 않으며, 추정 면적은 현장 실측을 대체하지 않는다.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def area_interval(region: np.ndarray, gsd_x: float, gsd_y: float,
                  occluded: np.ndarray | None = None, boundary_px: int = 1) -> dict:
    """region: 평지붕 가시 영역 bool 마스크. occluded: 그림자·가림 마스크(상한에 더함)."""
    px_area = gsd_x * gsd_y
    region = region.astype(bool)
    n = int(region.sum())
    if n == 0:
        return {"area_m2": 0.0, "area_low_m2": 0.0, "area_high_m2": 0.0, "px_area_m2": px_area}
    low = ndimage.binary_erosion(region, iterations=boundary_px).sum()
    high_mask = ndimage.binary_dilation(region, iterations=boundary_px)
    occ_px = 0
    if occluded is not None:
        occ_px = int((occluded.astype(bool) & ~high_mask).sum())
    return {
        "area_m2": n * px_area,
        "area_low_m2": float(low) * px_area,
        "area_high_m2": float(high_mask.sum() + occ_px) * px_area,
        "px_area_m2": px_area,
    }
