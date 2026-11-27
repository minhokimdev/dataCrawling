"""공간 블록 분할 (기획안 5.2): 인접 건물이 학습·평가에 동시에 들어가지 않도록 블록 단위 60/20/20."""
from __future__ import annotations

import numpy as np
import pandas as pd


def block_split(x: np.ndarray, y: np.ndarray, block_size: float, ratios=(0.6, 0.2, 0.2),
                seed: int = 42) -> np.ndarray:
    """x, y: 건물 중심 좌표(미터 단위 CRS). 반환: 'train'/'val'/'test' 배열."""
    bx = np.floor(np.asarray(x) / block_size).astype(int)
    by = np.floor(np.asarray(y) / block_size).astype(int)
    block = pd.Series(list(zip(bx, by)))
    counts = block.value_counts()
    rng = np.random.default_rng(seed)
    order = counts.index[rng.permutation(len(counts))]
    total = counts.sum()
    cum, assign = 0, {}
    cut1, cut2 = ratios[0] * total, (ratios[0] + ratios[1]) * total
    for b in order:
        assign[b] = "train" if cum < cut1 else ("val" if cum < cut2 else "test")
        cum += counts[b]
    return block.map(assign).to_numpy()
