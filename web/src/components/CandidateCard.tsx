import { COMPONENTS, COMPONENT_LABEL, type Scored, type Weights } from "../types";
import { GRADE_COLOR } from "./MapView";

const ROOF = { flat: "평지붕", pitched: "경사지붕", metal: "판넬·금속", unknown: "판단 불가", unreadable: "판독 불가" } as const;
const MATCH: Record<string, string> = {
  pk_wfs: "대장PK↔WFS 도형", pnu_unique: "PNU 단일 매칭", pnu_area_name: "PNU+면적·건물명", manual_review: "수동 검토 필요", none: "대장 없음",
};
const fmt = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "–" : v.toFixed(d));
const pct = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${Math.round(v * 100)}%`);

export function CandidateCard({ s, weights, onClose }: { s: Scored; weights: Weights; onClose: () => void }) {
  return (
    <aside className="card">
      <header className="card-head">
        <div>
          <div className="muted small">근거 카드</div>
          <h2>{s.bld_id} <span className="grade" style={{ background: GRADE_COLOR[s.confidence] }}>신뢰도 {s.confidence}</span></h2>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="닫기">✕</button>
      </header>

      {s.exclude_reason ? (
        <div className="banner gray">1차 제외: {s.exclude_reason}</div>
      ) : (
        <div className="score-box">
          <div>
            <div className="muted small">주 순위</div>
            <div className="big">#{s.rank_main ?? "–"}</div>
          </div>
          <div>
            <div className="muted small">점수 {s.score === null ? "범위" : ""}</div>
            <div className="big">
              {s.score !== null ? fmt(s.score) : `${fmt(s.score_low)} ~ ${fmt(s.score_high)}`}
            </div>
          </div>
          <div>
            <div className="muted small">보조 순위(재정규화)</div>
            <div className="big">#{s.rank_aux ?? "–"} <span className="small muted">{fmt(s.score_reweighted)}</span></div>
          </div>
        </div>
      )}

      <section>
        <h3>항목별 점수</h3>
        {COMPONENTS.map((c) => {
          const v = s[c];
          return (
            <div key={c} className="bar-row">
              <span className="bar-label">{COMPONENT_LABEL[c]} <span className="muted small">×{weights[c].toFixed(2)}</span></span>
              <div className="bar">
                {v === null ? <div className="bar-missing">결측 (0~100 범위로 반영)</div>
                  : <div className="bar-fill" style={{ width: `${v}%` }} />}
              </div>
              <span className="bar-val">{fmt(v, 0)}</span>
            </div>
          );
        })}
      </section>

      <section>
        <h3>옥상 판독 {s.roof_source === "register" && <span className="muted small">· 건축물대장 기재값 기반(영상 미사용)</span>}</h3>
        <dl>
          {s.roof_basis && (<><dt>근거</dt><dd>{s.roof_basis}</dd></>)}
          <dt>형태</dt><dd>{s.roof_type ? ROOF[s.roof_type] : "–"} {s.flat_prob != null && <span className="muted">({s.roof_source === "register" ? "규칙 확신도" : "평지붕 확률"} {pct(s.flat_prob)})</span>}</dd>
          {s.unreadable_reason && (<><dt>판독 불가 사유</dt><dd>{s.unreadable_reason}</dd></>)}
          <dt>가시 평지붕 면적</dt>
          <dd>{s.area_m2 != null ? `${fmt(s.area_low_m2, 0)} ~ ${fmt(s.area_high_m2, 0)}㎡ (점추정 ${fmt(s.area_m2, 0)}㎡)` : "–"}</dd>
          <dt>장애물 비율</dt><dd>{pct(s.obstacle_ratio)}</dd>
          <dt>녹색 / 흰색 표면</dt><dd>{pct(s.green_ratio)} / {pct(s.white_ratio)} <span className="muted small">관찰값 · 방수·기시공 판정 아님</span></dd>
          <dt>영상 촬영일</dt><dd>{s.image_date ?? "–"}</dd>
        </dl>
      </section>

      <section>
        <h3>결합·자료</h3>
        <dl>
          <dt>대장 용도</dt><dd>{s.mainPurpsCdNm ?? "–"}</dd>
          <dt>결합 방법</dt><dd>{MATCH[s.match_method ?? ""] ?? s.match_method ?? "–"} <span className="muted">(score {fmt(s.match_score, 2)})</span></dd>
          {s.missing_reason && (<><dt>결합 메모</dt><dd>{s.missing_reason}</dd></>)}
          <dt>지역 통계</dt><dd>{s.adm_nm ?? "–"} · {s.stat_year ?? "–"}년 · 행정동 단위</dd>
          {s.senior_population != null && (<><dt>65세 이상 / 고령 1인가구</dt>
            <dd>{s.senior_population.toLocaleString()}명 / {s.senior_single_households?.toLocaleString() ?? "–"}가구
              <span className="muted small"> (㎢당 {fmt(s.senior_population_per_km2, 0)}명 · {fmt(s.senior_single_households_per_km2, 0)}가구)</span></dd></>)}
          {s.useAprDay && (<><dt>사용승인일</dt><dd>{s.useAprDay}</dd></>)}
          {s.missing.length > 0 && (<><dt>결측 항목</dt><dd>{s.missing.map((m) => COMPONENT_LABEL[m]).join(", ")}</dd></>)}
          {s.platPlc && (<><dt>주소(내부용)</dt><dd>{s.platPlc}</dd></>)}
        </dl>
      </section>

      <p className="foot muted small">
        현장 조사 순서를 돕는 참고 자료입니다. 지원 자격·시공 가능 여부·면적은 공고 기준과 현장 실측으로 확인하세요.
      </p>
    </aside>
  );
}
