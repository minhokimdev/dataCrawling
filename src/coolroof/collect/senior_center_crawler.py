"""부산시 빅데이터웨이브「지도 기반 데이터」경로당 현황 동적 수집 (기획안 4.1 수집 단계).

페이지 구조(2026-11-17 확인):
- OpenLayers 지도(전역 `map`, `view`) 위에 GeoServer WMS 레이어 `map:TL_SENIOR_CENTER` 를 올린다.
- 지점을 클릭하면 GetFeatureInfo 결과가 `#hygiene_pop` 정보창의 `#featureInfoList` 표(<th>키</th><td>값</td>)로 뜬다.

수집 절차:
1) 화면 진입: 「공공데이터 지도」→「사회복지」→「경로당 현황」을 순서대로 선택.
2) 시범 구 bbox 를 격자로 나눠 칸마다 지도를 이동·확대.
3) 레이어 켬/끔 스크린샷 차분으로 화면에 그려진 지점 위치를 찾는다 (지도 배경·타일은 저장하지 않음).
4) 지점을 차례로 클릭해 정보창 표를 읽는다. 화면에 없는 항목은 추정하지 않는다.
5) 칸별 클릭 수·성공 수·중복 수·정보창 누락 수와 조작 전후 시각·URL 을 로그로 남긴다.
"""
from __future__ import annotations

import io
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage

from ..join.normalize import facility_key

DIFF_THRESHOLD = 60      # RGB 차분 합 임계값
MIN_SATURATION = 0.45    # 경로당 핀은 채도 높은 녹색. 라벨 글자 테두리(흰 halo)를 거른다.
MIN_BLOB_PX = 25         # 열림 연산 후 핀 본체 최소 픽셀 수


def find_marker_pixels(img_on: np.ndarray, img_off: np.ndarray) -> list[tuple[int, int]]:
    """레이어 켬/끔 이미지 차분에서 지점 아이콘(핀) 중심 픽셀 (x, y) 목록.

    차분만 쓰면 핀 옆 라벨 글자까지 잡히므로, 채도 높은 픽셀만 남긴 뒤 3×3 열림 연산으로
    얇은 글자 획을 지우고 두꺼운 핀 본체만 남긴다 (2026-11-17 괴정동 화면에서 핀 11개 전부 검출 확인).
    """
    from ..roof.rule_baseline import rgb_to_hsv

    diff = np.abs(img_on[..., :3].astype(int) - img_off[..., :3].astype(int)).sum(axis=-1)
    sat = rgb_to_hsv(img_on[..., :3])[..., 1]
    mask = ndimage.binary_opening((diff > DIFF_THRESHOLD) & (sat > MIN_SATURATION), structure=np.ones((3, 3)))
    labels, n = ndimage.label(mask)
    if n == 0:
        return []
    idx = range(1, n + 1)
    sizes = ndimage.sum(mask, labels, idx)
    centers = ndimage.center_of_mass(mask, labels, idx)
    return [(int(round(cx)), int(round(cy))) for (cy, cx), s in zip(centers, sizes) if s >= MIN_BLOB_PX]


def pick(info: dict, keys: list[str]) -> str | None:
    for k in keys:
        for ik, v in info.items():
            if k in ik and v not in (None, "", "-"):
                return str(v).strip()
    return None


class SeniorCenterCrawler:
    def __init__(self, cfg: dict, out_dir: Path, headless: bool = True):
        self.cfg = cfg
        self.c = cfg["crawler"]
        self.out_dir = Path(out_dir)
        self.shot_dir = self.out_dir / "screens"
        self.shot_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.log_path = self.out_dir / "crawl_log.jsonl"
        self.log_path.write_text("", encoding="utf-8")

    def log(self, page, step: str, **kw) -> None:
        rec = {"ts": datetime.now().isoformat(timespec="seconds"), "step": step, "url": page.url, **kw}
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---------- 1) 화면 진입 ----------
    def enter(self, page) -> None:
        layer = self.c["layer_id"]
        page.goto(self.c["url"], wait_until="networkidle")
        page.screenshot(path=str(self.shot_dir / "00_enter.png"))
        self.log(page, "open")
        page.locator("#selectTab_1 > span.mT0").click()          # 공공데이터 지도
        page.locator("#selectTab_1 .list_in > span", has_text="사회복지").click()
        page.locator(f"label[for='{layer}']").click()             # 경로당 현황 (input 은 숨김 처리됨) → checkMap()
        page.wait_for_function(f"typeof wmsLayerList !== 'undefined' && !!wmsLayerList['{layer}']")
        # 정보창 autoPan 이 지도를 움직이지 않도록 끄고, 선택 패널은 지점을 가리지 않게 숨긴다.
        page.evaluate("() => { overlay.autoPan = false; }")
        page.add_style_tag(content="#map > .ck_wrap { visibility: hidden !important; }")
        self.wait_render(page)
        page.screenshot(path=str(self.shot_dir / "01_layer_on.png"))
        self.log(page, "layer_on", layer=layer)

    def wait_render(self, page) -> None:
        page.evaluate("""() => new Promise(res => {
            let done = false; const fin = () => { if (!done) { done = true; res(); } };
            map.once('rendercomplete', fin); map.render(); setTimeout(fin, 8000);
        })""")

    # ---------- 2) 격자 ----------
    def grid_centers(self, page) -> list[tuple[float, float]]:
        bbox = self.cfg["pilot"]["bbox_wgs84"]
        zoom = self.c["zoom"]
        # 지도 상단은 사이트 헤더·탭이 덮고 있으므로, 지도가 실제로 보이는 첫 y(top_px)부터를 탐색 영역으로 쓴다.
        info = page.evaluate(f"""() => {{
            const ext = ol.proj.transformExtent({json.dumps(bbox)}, 'EPSG:4326', 'EPSG:3857');
            const size = map.getSize();
            const res = view.getResolutionForZoom({zoom});
            let top = 0;
            for (; top < size[1]; top += 4) {{
                const e = document.elementFromPoint(size[0] / 2, top);
                if (e && e.closest('.ol-viewport')) break;
            }}
            return {{ext, res, top, w: size[0] * res * 0.9, h: (size[1] - top) * res * 0.9}};
        }}""")
        # 보이는 영역의 중심이 칸 중심에 오도록 view 중심을 위로 top/2 픽셀만큼 올린다
        self.center_shift = info["top"] / 2 * info["res"]
        x0, y0, x1, y1 = info["ext"]
        nx, ny = math.ceil((x1 - x0) / info["w"]), math.ceil((y1 - y0) / info["h"])
        centers = [(x0 + (i + 0.5) * info["w"], y0 + (j + 0.5) * info["h"]) for j in range(ny) for i in range(nx)]
        return centers[: self.c["max_cells"]]

    def goto_cell(self, page, center: tuple[float, float]) -> None:
        cx, cy = center[0], center[1] + getattr(self, "center_shift", 0.0)
        page.evaluate(f"() => {{ view.setZoom({self.c['zoom']}); view.setCenter([{cx}, {cy}]); }}")
        self.wait_render(page)

    def map_shot(self, page) -> np.ndarray:
        return np.array(Image.open(io.BytesIO(page.locator("#map").screenshot())).convert("RGB"))

    def set_layer_visible(self, page, visible: bool) -> None:
        page.evaluate(f"() => wmsLayerList['{self.c['layer_id']}'].setVisible({str(visible).lower()})")
        self.wait_render(page)

    # ---------- 4) 클릭 → 정보창 ----------
    def is_map_pixel(self, page, px: int, py: int) -> bool:
        """사이트 헤더·탭 등이 덮고 있는 위치면 False (지도 캔버스가 직접 보이는 곳만 클릭)."""
        return page.evaluate(f"""() => {{ const e = document.elementFromPoint({px}, {py});
            return !!e && !!e.closest('.ol-viewport'); }}""")

    def click_and_read(self, page, px: int, py: int) -> dict | None:
        page.evaluate("""() => { document.getElementById('featureInfoList').replaceChildren();
                                document.getElementById('hygiene_pop').style.display = 'none'; }""")
        box = page.locator("#map").bounding_box()
        page.mouse.click(box["x"] + px, box["y"] + py)
        try:
            page.wait_for_selector("#featureInfoList tr", timeout=self.c["click_wait_ms"])
        except Exception:
            return None
        rows = page.evaluate("""() => Array.from(document.querySelectorAll('#featureInfoList tr'))
            .map(tr => [tr.querySelector('th')?.innerText.trim(), tr.querySelector('td')?.innerText.trim()])""")
        lonlat = page.evaluate(f"() => ol.proj.toLonLat(map.getCoordinateFromPixel([{px}, {py}]))")
        page.evaluate("() => closePop()")
        return {"info": {k: v for k, v in rows if k}, "click_lon": lonlat[0], "click_lat": lonlat[1]}

    # ---------- 실행 ----------
    def run(self) -> pd.DataFrame:
        from playwright.sync_api import sync_playwright

        records: dict[str, dict] = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            ctx = browser.new_context(viewport={"width": 1600, "height": 1000})
            ctx.add_cookies([{"name": "storInfoPop", "value": "Y", "domain": "data.busan.go.kr", "path": "/"}])
            page = ctx.new_page()
            self.enter(page)
            centers = self.grid_centers(page)
            self.log(page, "grid", n_cells=len(centers))
            for idx, center in enumerate(centers):
                self.goto_cell(page, center)
                on = self.map_shot(page)
                self.set_layer_visible(page, False)
                off = self.map_shot(page)
                self.set_layer_visible(page, True)
                found = find_marker_pixels(on, off)
                markers = [m for m in found if self.is_map_pixel(page, *m)]
                stat = {"cell": idx, "center_3857": center, "found": len(found), "clicked": len(markers),
                        "ok": 0, "dup": 0, "no_popup": 0}
                if markers:
                    Image.fromarray(on).save(self.shot_dir / f"cell_{idx:04d}.png")
                for px, py in markers:
                    res = self.click_and_read(page, px, py)
                    self.goto_cell(page, center)   # 혹시 모를 지도 이동 복구
                    if res is None:
                        stat["no_popup"] += 1
                        continue
                    info = res["info"]
                    name = pick(info, self.c["name_keys"])
                    addr = pick(info, self.c["address_keys"])
                    key = facility_key(name, addr) if (name or addr) else f"{res['click_lon']:.5f},{res['click_lat']:.5f}"
                    if key in records:
                        stat["dup"] += 1
                        continue
                    stat["ok"] += 1
                    records[key] = {
                        "facility_key": key, "name": name, "address": addr,
                        "category": pick(info, self.c["category_keys"]),
                        "lon": res["click_lon"], "lat": res["click_lat"],
                        "source_url": page.url, "collected_at": datetime.now().isoformat(timespec="seconds"),
                        "cell": idx, "raw_info": json.dumps(info, ensure_ascii=False),
                    }
                self.log(page, "cell", **stat)
            browser.close()
        df = pd.DataFrame(records.values())
        return df
