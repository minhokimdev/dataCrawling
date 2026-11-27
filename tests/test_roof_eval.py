import numpy as np

from coolroof.evaluate.metrics import binary_pr, per_class_iou, precision_at_n
from coolroof.evaluate.split import block_split
from coolroof.roof.area import area_interval
from coolroof.roof.rule_baseline import classify_roof


def _building_mask():
    m = np.zeros((128, 128), bool)
    m[34:94, 24:104] = True
    return m


def test_flat_roof_detected_with_area_interval(cfg):
    img = np.full((128, 128, 3), 90, np.uint8)
    m = _building_mask()
    img[m] = [235, 235, 230]
    r = classify_roof(img, m, 0.25, 0.25, cfg)
    assert r["roof_type"] == "flat"
    assert r["area_low_m2"] < r["area_m2"] < r["area_high_m2"]
    assert abs(r["area_m2"] - m.sum() * 0.0625) < 1e-6
    assert r["white_ratio"] > 0.9  # 흰색은 관찰값으로만 기록


def test_pitched_roof_two_tone(cfg):
    img = np.full((128, 128, 3), 90, np.uint8)
    m = _building_mask()
    img[34:64, 24:104] = [200, 120, 100]
    img[64:94, 24:104] = [110, 60, 50]
    assert classify_roof(img, m, 0.25, 0.25, cfg)["roof_type"] == "pitched"


def test_shadow_unreadable(cfg):
    img = np.full((128, 128, 3), 10, np.uint8)
    r = classify_roof(img, _building_mask(), 0.25, 0.25, cfg)
    assert r["roof_type"] == "unreadable" and r["unreadable_reason"]


def test_area_interval_empty():
    assert area_interval(np.zeros((4, 4), bool), 0.5, 0.5)["area_m2"] == 0


def test_block_split_no_block_leak():
    rng = np.random.default_rng(0)
    x, y = rng.uniform(0, 3000, 500), rng.uniform(0, 3000, 500)
    lab = block_split(x, y, 300, seed=1)
    blocks = list(zip((x // 300).astype(int), (y // 300).astype(int)))
    seen = {}
    for b, l in zip(blocks, lab):
        assert seen.setdefault(b, l) == l
    frac = {k: (lab == k).mean() for k in ("train", "val", "test")}
    assert 0.45 < frac["train"] < 0.75
    assert (block_split(x, y, 300, seed=1) == lab).all()


def test_metrics():
    gt = np.array([0, 0, 1, 1, 2])
    pr = np.array([0, 1, 1, 1, 2])
    iou = per_class_iou(gt, pr, 3)
    assert np.isclose(iou[0], 0.5) and np.isclose(iou[1], 2 / 3) and iou[2] == 1
    assert binary_pr([1, 1, 0, 0], [1, 0, 1, 0])["precision"] == 0.5
    assert precision_at_n(["a", "b", "c"], {"a", "c"}, 2) == 0.5
