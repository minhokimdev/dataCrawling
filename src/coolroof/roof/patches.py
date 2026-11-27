"""정사영상 → 건물별 512×512 패치 + 건물 폴리곤 마스크 (기획안 5.1 입력·전처리).

원본 픽셀 크기·좌표계는 유지한다(리샘플링 없이 창을 자르고 부족하면 패딩).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window
from shapely.geometry.base import BaseGeometry


@dataclass
class Patch:
    image: np.ndarray        # (H, W, 3) uint8
    mask: np.ndarray         # (H, W) bool, 건물 폴리곤 내부
    gsd_x: float
    gsd_y: float
    transform: object
    valid_ratio: float       # 패치 중 영상 데이터가 있는 비율


def extract_patch(src: rasterio.DatasetReader, geom: BaseGeometry, size: int = 512) -> Patch | None:
    """geom 은 영상과 같은 CRS 여야 한다."""
    cx, cy = geom.centroid.x, geom.centroid.y
    row, col = src.index(cx, cy)
    win = Window(col - size // 2, row - size // 2, size, size)
    data = src.read([1, 2, 3], window=win, boundless=True, fill_value=0)
    if data.size == 0:
        return None
    img = np.moveaxis(data, 0, -1)
    if img.dtype != np.uint8:
        hi = np.percentile(img, 99) or 1
        img = np.clip(img / hi * 255, 0, 255).astype(np.uint8)
    tr = src.window_transform(win)
    mask = rasterize([(geom, 1)], out_shape=(size, size), transform=tr, fill=0).astype(bool)
    return Patch(img, mask, abs(tr.a), abs(tr.e), tr, float((img.sum(-1) > 0).mean()))


def export_patches(ortho_path: str | Path, buildings, out_dir: str | Path, size: int = 512) -> list[dict]:
    out_dir = Path(out_dir)
    (out_dir / "img").mkdir(parents=True, exist_ok=True)
    (out_dir / "bmask").mkdir(parents=True, exist_ok=True)
    from PIL import Image

    meta = []
    with rasterio.open(ortho_path) as src:
        b = buildings.to_crs(src.crs)
        for bld_id, geom in zip(b["bld_id"], b.geometry):
            p = extract_patch(src, geom, size)
            if p is None:
                continue
            Image.fromarray(p.image).save(out_dir / "img" / f"{bld_id}.png")
            Image.fromarray(p.mask.astype(np.uint8) * 255).save(out_dir / "bmask" / f"{bld_id}.png")
            meta.append({"bld_id": bld_id, "gsd_x": p.gsd_x, "gsd_y": p.gsd_y,
                         "valid_ratio": p.valid_ratio, "building_px": int(p.mask.sum()),
                         "ortho": str(ortho_path)})
    return meta
