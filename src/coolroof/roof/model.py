"""픽셀 단위 분할 모델 (기획안 5.1~5.2). `pip install -e ".[model]"` 필요.

클래스(상호 배타): background, flat_visible, pitched, equipment, shadow_occlusion
라벨: data/labels/mask/<bld_id>.png (픽셀값 = 클래스 인덱스), 영상: data/interim/patches/img/<bld_id>.png
1차 후보 U-Net, 비교 모델 SegFormer-B0. 손실: CrossEntropy + Dice.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
from PIL import Image

from ..evaluate.metrics import per_class_iou


def _lazy_torch():
    import segmentation_models_pytorch as smp
    import torch
    return torch, smp


def build_model(cfg: dict):
    torch, smp = _lazy_torch()
    m = cfg["model"]
    n = len(m["classes"])
    if m["arch"] == "segformer":
        return smp.Segformer(encoder_name="mit_b0", encoder_weights="imagenet", classes=n)
    return smp.Unet(encoder_name=m["encoder"], encoder_weights="imagenet", classes=n)


class RoofDataset:
    MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def __init__(self, ids: list[str], img_dir: Path, mask_dir: Path | None, augment: bool = False):
        self.ids, self.img_dir, self.mask_dir, self.augment = ids, Path(img_dir), mask_dir, augment

    def __len__(self):
        return len(self.ids)

    def __getitem__(self, i):
        torch, _ = _lazy_torch()
        bid = self.ids[i]
        img = np.asarray(Image.open(self.img_dir / f"{bid}.png").convert("RGB"), dtype=np.float32) / 255
        mask = np.asarray(Image.open(Path(self.mask_dir) / f"{bid}.png"), dtype=np.int64) if self.mask_dir else None
        if self.augment:  # 회전·반전·제한적 밝기 변화만
            k = random.randint(0, 3)
            img = np.rot90(img, k)
            mask = np.rot90(mask, k) if mask is not None else None
            if random.random() < 0.5:
                img = img[:, ::-1]
                mask = mask[:, ::-1] if mask is not None else None
            img = np.clip(img * random.uniform(0.9, 1.1), 0, 1)
        img = (img - self.MEAN) / self.STD
        x = torch.from_numpy(np.ascontiguousarray(img.transpose(2, 0, 1)))
        y = torch.from_numpy(np.ascontiguousarray(mask)) if mask is not None else torch.zeros(1)
        return x, y, bid


def train(cfg: dict, split: dict[str, list[str]], img_dir: Path, mask_dir: Path, out_dir: Path) -> dict:
    torch, smp = _lazy_torch()
    m = cfg["model"]
    random.seed(m["seed"]); np.random.seed(m["seed"]); torch.manual_seed(m["seed"])
    dev = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    model = build_model(cfg).to(dev)
    dl = lambda ids, aug, sh: torch.utils.data.DataLoader(  # noqa: E731
        RoofDataset(ids, img_dir, mask_dir, aug), batch_size=m["batch_size"], shuffle=sh, num_workers=0)
    tr, va = dl(split["train"], True, True), dl(split["val"], False, False)
    ce = torch.nn.CrossEntropyLoss()
    dice = smp.losses.DiceLoss(mode="multiclass")
    opt = torch.optim.AdamW(model.parameters(), lr=m["lr"])
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=m["epochs"])
    out_dir.mkdir(parents=True, exist_ok=True)
    best, history = -1.0, []
    for ep in range(m["epochs"]):
        model.train()
        for x, y, _ in tr:
            x, y = x.to(dev), y.to(dev)
            logits = model(x)
            loss = ce(logits, y) + dice(logits, y)
            opt.zero_grad(); loss.backward(); opt.step()
        sched.step()
        ious = evaluate(model, va, len(m["classes"]), dev)
        miou = float(np.nanmean(ious))
        history.append({"epoch": ep, "val_miou": miou, "val_iou": ious.tolist()})
        if miou > best:  # 최종 평가 집합은 여기서 쓰지 않는다
            best = miou
            torch.save(model.state_dict(), out_dir / "best.pt")
    (out_dir / "history.json").write_text(json.dumps({"seed": m["seed"], "history": history}, indent=2))
    return {"best_val_miou": best}


def evaluate(model, loader, n_classes: int, dev: str) -> np.ndarray:
    torch, _ = _lazy_torch()
    model.eval()
    preds, gts = [], []
    with torch.no_grad():
        for x, y, _ in loader:
            preds.append(model(x.to(dev)).argmax(1).cpu().numpy())
            gts.append(y.numpy())
    return per_class_iou(np.concatenate(gts), np.concatenate(preds), n_classes)


def predict_probs(model, img: np.ndarray, dev: str = "cpu") -> np.ndarray:
    """(H,W,3) uint8 → (C,H,W) 클래스 확률 지도."""
    torch, _ = _lazy_torch()
    x = (img.astype(np.float32) / 255 - RoofDataset.MEAN) / RoofDataset.STD
    x = torch.from_numpy(x.transpose(2, 0, 1)).unsqueeze(0).to(dev)
    model.eval()
    with torch.no_grad():
        return torch.softmax(model(x), 1)[0].cpu().numpy()
