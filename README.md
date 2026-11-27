# coolroof-busan

데이터크롤링 12조 기말프로젝트 — **부산시 하얀지붕(쿨루프) 미발굴 후보 건물 발굴** 파이프라인.
기획안: `V1_데이터크롤링12조_기획안.pdf`

> 분석 결과는 담당자의 현장 조사·신청 안내 순서를 돕는 참고 자료다. 개별 가구의 지원 자격이나 시공 가능 여부를 자동으로 판정하지 않는다.

## 구조

```
config/settings.yaml          시범 구·API·가중치·임계값 (TODO(착수) 표시 = 확인 필요)
src/coolroof/
  collect/
    senior_center_crawler.py  빅데이터웨이브 지도 경로당 동적 수집 (Playwright)   ← 기획안 4.1
    building_register.py      건축HUB 건축물대장 표제부 (15134735)
    gis_building.py           GIS건물통합정보 SHP(15083092) / WFS(15123552)
    sgis.py                   SGIS 행정동 경계 + 총조사 주요지표
  join/                       주소 정규화, 건물 단위 결합(4.2), 경로당↔공공CSV 대조·건물 결합
  roof/                       정사영상 패치, 규칙 기반 기준선, 면적 구간, U-Net/SegFormer(5장)
  scoring/priority.py         S=0.40·물리+0.35·지역+0.15·미지원+0.10·신뢰도, 결측 범위, ±20% 민감도(6장)
  evaluate/                   공간 블록 60/20/20 분할, IoU·Precision@N·동별 오류·신뢰도 보정표
  export/gis.py               Top N CSV, 수동검토 CSV, GeoJSON, 지도 HTML, 근거 카드
tests/                        합성 데이터 단위·E2E 테스트 (14개)
```

## 설치

```bash
uv venv -p 3.12 && uv pip install -e ".[dev]"      # 모델 학습까지: ".[dev,model]"
.venv/bin/playwright install chromium
cp .env.example .env                               # 키 입력
.venv/bin/python -m pytest -q
```

## 실행 순서

### A. 팀 수집 자료로 부산 전역 분석 (2026-11-27~, 현재 기본 경로)

```bash
coolroof ingest-team --src ~/Desktop/데이터크롤링   # 대장↔WFS 폴리곤 27만 동 + 행정동 고령 통계 + 대장 지붕 대리판독
coolroof score && coolroof export && coolroof export-web   # 대시보드엔 상위 3000동(--limit)
```

- 지붕: 정사영상 대신 대장 `지붕코드명`·`기타지붕` 규칙(`roof/register_proxy.py`). `roof_rule.csv`(영상 판독)가 생기면 score 가 그쪽을 우선 사용.
- 지역 필요도: 행정동 65세 이상 인구·고령 1인가구의 **㎢당 밀도**(원 수치는 큰 동이 독식). 행정동 경계는 `data/raw/admdong/` (vuski/admdongkor ver20241231, CC BY 4.0).
- 범위: `analysis.scope_sigungu_cd: null` = 부산 전역. 구 하나만 보려면 5자리 코드 입력.
- 미반영: 기온(AWS 관측소-구 대응 미확정), KRAS(파이썬 직접 요청 차단 → 조사 기록만).

### B. API·영상 경로 (키·정사영상 확보 시)

```bash
coolroof crawl-senior                 # → data/raw/senior_centers.csv, crawl_senior/{crawl_log.jsonl, screens/}
coolroof compare-senior --public 경로당현황.csv --name-col 시설명 --addr-col 주소
coolroof buildings --shp <GIS건물통합정보>.shp
coolroof register                     # DATA_GO_KR_KEY 필요
coolroof sgis --adm-cd <SGIS 시군구코드>   # SGIS 키 필요
coolroof join                         # 건물 결합 + 경로당→건물
coolroof patches --ortho <정사영상>.tif
coolroof roof-rule                    # 규칙 기반 기준선
coolroof split && coolroof train      # 라벨 확보 후 (data/labels/mask/<bld_id>.png)
coolroof score [--constructed 기시공명단.csv --constructed-addr-col 주소]
coolroof export                       # → outputs/candidates/
```

## 웹 대시보드 (React)

`web/`: Vite + React + TypeScript + react-leaflet. 파이프라인 산출물을 `bundle.json`으로 받아서 보여줍니다.

```bash
coolroof export-web            # 실제: data/processed/scored.gpkg + 경로당 → web/public/data/bundle.json
coolroof export-web --demo     # 시연: 합성 건물 220동 + 실제 수집 경로당 (화면에 DEMO 배지 표시)
cd web && npm install && npm run dev    # http://localhost:5173
npm test                       # 점수 로직(priority.py 이식) 테스트
```

| 화면 | 내용 |
|---|---|
| 후보 지도 | 신뢰도 A/B/C 색, 결측은 점선, 상위 N 강조, 경로당 레이어. 줌 16 미만이면 점, 그 이상이면 건물 폴리곤 |
| 가중치 슬라이더 | 움직이면 브라우저에서 즉시 재순위 (`web/src/lib/scoring.ts` = `scoring/priority.py`와 같은 규칙) |
| 근거 카드 | 순위·점수 범위·항목별 막대(결측 표시)·옥상 판독·면적 구간·결합 방법·통계 단위 |
| 경로당 수집 | 크롤링 칸·클릭·성공·중복·누락 통계, 수집 목록 |
| 가중치 민감도 | ±20%·항목 제외 시 Top N 교체율 |

캡처: `docs/screenshots/1_map.png` ~ `5_sens.png`

## 검증된 것 (2026-11-17)

- 크롤러: 실제 사이트에서 괴정동 2칸을 수집해 경로당 17곳을 얻었고 정보창 실패는 0건. 정보창 항목은 `시설명 / 주소 / 전화번호`.
  - 지점 검출: 레이어 켬/끔 스크린샷 차분 → 채도 필터 → 3×3 열림 연산. 화면의 핀은 모두 검출됨.
  - 한계: 같은 좌표에 시설 2곳(예: 양지할머니·양지할아버지)이 겹치면 정보창이 첫 번째만 보여준다. 나머지는 `compare-senior`에서 "파일에만 있음"으로 잡아 수동 보완해야 함.
- 결합·점수·산출물 로직: 합성 데이터 테스트 통과.
- **API 클라이언트(건축HUB·WFS·SGIS)는 키가 없어 실제 호출 검증을 못 했음.**

---

## ✅ 내가 해야 할 일

### 1. 착수 전 결정·확인 (기획안 2장 게이트)
- [ ] **시범 구 확정** → `settings.yaml`의 `pilot.gu_name`, `sigungu_cd`, `bbox_wgs84`를 수정 (지금은 예시값인 사하구)
- [ ] 해당 연도 하얀지붕 **공식 공고 원문** 확보: 70㎡ 기준, 대상 용도 → `target_usages` 반영
- [ ] 부산시·구 담당 부서에 **기시공 명단**(사업명·연도·시공일·주소) 요청 (필요하면 정보공개청구). 명단이 없으면 미지원 항목은 결측으로 남는다
- [ ] 정사영상 **이용권한 확인** (저장·학습·결과 공개 범위). 권한이 없으면 AI 학습은 빼고 규칙 기반·현장 표본 중심으로 축소

### 2. 키 발급 → `.env`
- [ ] 공공데이터포털에서 활용신청: 건축HUB 건축물대장정보(15134735), GIS건물일반집합정보 WMS/WFS(15123552) → `DATA_GO_KR_KEY`
- [ ] SGIS 개발지원센터 → `SGIS_CONSUMER_KEY`, `SGIS_CONSUMER_SECRET`

### 3. 데이터 내려받기
- [ ] GIS건물통합정보 SHP(15083092, 부산) 다운로드 → **컬럼명 확인 후 `gis_fields` 수정** (현재 값은 A1/A2/... 추정치)
- [ ] 국토정보플랫폼(map.ngii.go.kr)에서 시범 구 **정사영상 도엽 신청·다운로드**, 촬영일을 `pilot.image_date`에 기입
- [ ] 부산 경로당 현황 공공 CSV(빅데이터웨이브 15084229 "Data" 버튼) 다운로드 → `compare-senior`에 사용

### 4. 첫 시험 호출 (각 1회)
- [ ] `coolroof register`: 응답 필드명이 `TITLE_COLUMNS`와 맞는지 확인
- [ ] `coolroof sgis`: `population.json` 응답에 `aged_child_idx`, `oldage_suprt_per`가 있는지 확인 → `region_need_cols` 조정
- [ ] 시범 구 전체로 `coolroof crawl-senior` 실행 (`--headed`로 눈으로 확인 가능). 요청 속도와 이용조건 확인

### 5. 라벨링·모델 (민호·태현)
- [ ] `patches` 실행 후 층화 추출한 300~500동에 **2인 독립 라벨링** (`data/labels/mask/<bld_id>.png`, 픽셀값 0~4 = background / flat_visible / pitched / equipment / shadow_occlusion). 불일치 조정 기록 보존
- [ ] `roof-rule` 결과와 수동 판독을 비교한 뒤 `roof:` 임계값 재조정
- [ ] `split` → `train`(U-Net), 이어서 `model.arch: segformer` 비교. 최종 평가 집합은 한 번만 사용

### 6. 현장·담당자 협의
- [ ] 가중치(0.40/0.35/0.15/0.10)를 담당자와 협의해 확정. `weight_sensitivity.csv`(±20% Top N 교체율)를 근거로 제시
- [ ] Top N 현장 검토 후 유효 여부를 기록 → Precision@N 산출 (`evaluate/metrics.py`)

### 7. 발표자료 (민호)
- [ ] `outputs/candidates/candidates_map.html` 스크린샷, 크롤링 증빙(`screens/`, `crawl_log.jsonl`), 대조표, 민감도 표 활용
- [ ] 대외 공개본은 주소를 뺀 기본 export를 사용 (`--include-address`는 내부용)
