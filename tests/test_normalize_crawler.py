import numpy as np

from coolroof.collect.senior_center_crawler import find_marker_pixels, pick
from coolroof.join.normalize import facility_key, normalize_address, parse_jibun


def test_normalize_address_variants_equal():
    a = normalize_address("부산광역시 사하구 괴정동 123-4번지")
    b = normalize_address("사하구 괴정동 123-4 (괴정1동)")
    assert a == b == "부산사하구괴정동123-4"


def test_facility_key_strips_suffix():
    assert facility_key("괴정 경로당", "부산시 사하구 괴정동 1") == facility_key("괴정", "부산광역시 사하구 괴정동 1")


def test_parse_jibun():
    assert parse_jibun("부산 사하구 괴정동 123-4") == ("0", "0123", "0004")
    assert parse_jibun("부산 사하구 다대동 산 12") == ("1", "0012", "0000")
    assert parse_jibun(None) is None


def test_find_marker_pixels_diff():
    off = np.full((100, 100, 3), 240, np.uint8)
    on = off.copy()
    on[10:19, 20:29] = [130, 176, 63]   # 핀 본체(채도 높은 녹색)
    on[60:68, 70:78] = [130, 176, 63]
    on[40, 10:60] = [130, 176, 63]      # 얇은 글자 획 → 열림 연산으로 제거
    on[80:90, 10:20] = [255, 255, 255]  # 흰 halo → 채도 필터로 제거
    pts = sorted(find_marker_pixels(on, off))
    assert pts == [(24, 14), (74, 64)]


def test_pick_partial_key():
    # 실제 정보창 항목(2026-11-17): 전화번호 / 주소 / 시설명
    info = {"전화번호": "051-000-0000", "주소": "부산광역시 사하구 사하로186번라길 8(괴정동)", "시설명": "장수"}
    assert pick(info, ["시설명", "경로당명"]) == "장수"
    assert pick(info, ["주소"]).startswith("부산광역시 사하구")
    assert pick({"주소": "-"}, ["주소"]) is None
