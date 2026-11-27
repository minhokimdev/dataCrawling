"""정사영상이 없을 때의 지붕 대리 판독: 건축물대장 지붕코드명·기타지붕 문자열 규칙.

영상 판독(rule_baseline·model)과 같은 컬럼(roof_type, flat_prob, area_*)을 내보내 점수 모듈을 그대로 쓴다.
- 대장 기재값이므로 현재 옥상 상태(증축·설비·기시공 도료)를 반영하지 못한다. 근거는 roof_basis 에 남긴다.
- 면적은 건물 도형 면적과 대장 건축면적의 범위이며 옥상 실면적·도포 가능 면적이 아니다.
- flat_prob 값은 규칙의 확신 정도를 나타내는 임의 척도이며 검증된 확률이 아니다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SLAB = ("스라브", "슬라브", "슬래브", "평지붕", "평")
PITCHED = ("경사", "기와", "초가", "루삥", "트러스")
METAL = ("판넬", "패널", "아연", "함석", "강판", "칼라", "시트", "쉬트", "철골")
MIXED = ("스레트", "슬레이트", "기와")


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def classify(code: str | None, etc: str | None) -> tuple[str, float, str]:
    """(roof_type, flat_prob, roof_basis). roof_type: flat | pitched | metal | unknown."""
    code = code if isinstance(code, str) else ""
    etc = etc if isinstance(etc, str) else ""
    if _has(etc, ("경사",)):
        return "pitched", 0.1, f"기타지붕 '{etc}'"
    if code == "(철근)콘크리트":
        if _has(etc, MIXED):
            return "flat", 0.5, f"콘크리트+혼합 '{etc}'"
        if _has(etc, SLAB):
            return "flat", 0.85, f"콘크리트 슬래브 '{etc}'"
        return "flat", 0.7, "지붕코드 (철근)콘크리트"
    if code == "슬레이트":
        return "pitched", 0.1, "지붕코드 슬레이트"
    if code == "기와":
        return "pitched", 0.05, "지붕코드 기와"
    if code == "기타지붕":
        if _has(etc, SLAB):
            return "flat", 0.7, f"기타지붕 '{etc}'"
        if _has(etc, PITCHED):
            return "pitched", 0.05, f"기타지붕 '{etc}'"
        if _has(etc, METAL):
            return "metal", 0.2, f"기타지붕 '{etc}'"
        return "unknown", np.nan, f"기타지붕 '{etc or '미기재'}'"
    return "unknown", np.nan, "지붕코드 결측"


def roof_from_register(df: pd.DataFrame) -> pd.DataFrame:
    """입력: bld_id, roofCdNm, etcRoof, poly_area_m2, archArea. 출력: 점수 모듈용 지붕 표."""
    cls = [classify(c, e) for c, e in zip(df["roofCdNm"], df["etcRoof"])]
    out = pd.DataFrame(cls, columns=["roof_type", "flat_prob", "roof_basis"], index=df.index)
    poly = pd.to_numeric(df["poly_area_m2"], errors="coerce")
    arch = pd.to_numeric(df["archArea"], errors="coerce").where(lambda s: s > 0)
    out.insert(0, "bld_id", df["bld_id"])
    out["area_m2"] = poly
    out["area_low_m2"] = pd.concat([poly, arch], axis=1).min(axis=1)
    out["area_high_m2"] = pd.concat([poly, arch], axis=1).max(axis=1)
    out["obstacle_ratio"] = np.nan          # 대장으로는 옥상 설비·장애물을 알 수 없음
    out["roof_source"] = "register"
    out["unreadable_reason"] = np.where(out["roof_type"] == "unknown", "대장 지붕정보로 판단 불가", None)
    return out
