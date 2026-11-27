"""주소·시설명 정규화 (기획안 4.1 중복·누락 관리, 4.2 결합 1차)."""
from __future__ import annotations

import re

_SIDO = [("부산광역시", "부산"), ("부산시", "부산")]
_ADDR_NOISE = re.compile(r"\(.*?\)|번지|외\s*\d+\s*필지|\s+")
_JIBUN = re.compile(r"(?P<san>산\s*)?(?P<bun>\d+)(?:-(?P<ji>\d+))?(?:\s|$|번지)")
_NAME_NOISE = re.compile(r"\(.*?\)|\s+|경로당$|노인정$")


def normalize_address(addr: str | None) -> str:
    if not addr:
        return ""
    s = str(addr).strip()
    for a, b in _SIDO:
        s = s.replace(a, b)
    if not s.startswith("부산"):
        s = "부산" + s
    return _ADDR_NOISE.sub("", s)


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return _NAME_NOISE.sub("", str(name).strip())


def facility_key(name: str | None, addr: str | None) -> str:
    return f"{normalize_name(name)}|{normalize_address(addr)}"


def parse_jibun(addr: str | None) -> tuple[str, str, str] | None:
    """'부산 사하구 괴정동 123-4' → (platGbCd, bun 4자리, ji 4자리). 지번이 없으면 None."""
    if not addr:
        return None
    m = None
    for m in _JIBUN.finditer(str(addr) + " "):
        pass
    if m is None:
        return None
    plat = "1" if m.group("san") else "0"
    return plat, m.group("bun").zfill(4), (m.group("ji") or "0").zfill(4)
