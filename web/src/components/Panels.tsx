import { useMemo } from "react";
import { weightSensitivity } from "../lib/scoring";
import { COMPONENTS, COMPONENT_LABEL, type Bundle, type BuildingProps, type Grade, type Scored, type Weights } from "../types";
import { GRADE_COLOR } from "./MapView";

export function WeightPanel({ weights, base, onChange }: { weights: Weights; base: Weights; onChange: (w: Weights) => void }) {
  const tot = COMPONENTS.reduce((s, c) => s + weights[c], 0) || 1;
  return (
    <section className="panel">
      <div className="panel-head">
        <h3>가중치</h3>
        <button className="link" onClick={() => onChange(base)}>기본값</button>
      </div>
      {COMPONENTS.map((c) => (
        <label key={c} className="slider">
          <span>{COMPONENT_LABEL[c]}</span>
          <input type="range" min={0} max={1} step={0.01} value={weights[c]}
            onChange={(e) => onChange({ ...weights, [c]: Number(e.target.value) })} />
          <span className="num">{(weights[c] / tot).toFixed(2)}</span>
        </label>
      ))}
      <p className="muted small">합이 1이 되도록 자동 정규화. 확정 가중치는 담당자 협의 후 고정.</p>
    </section>
  );
}

export interface Filters { grades: Set<Grade>; hideExcluded: boolean; onlyComplete: boolean; query: string }

export function FilterBar({ f, onChange }: { f: Filters; onChange: (f: Filters) => void }) {
  const toggle = (g: Grade) => {
    const s = new Set(f.grades);
    s.has(g) ? s.delete(g) : s.add(g);
    onChange({ ...f, grades: s });
  };
  return (
    <div className="filters">
      <input className="search" placeholder="건물 ID·용도·행정동 검색" value={f.query}
        onChange={(e) => onChange({ ...f, query: e.target.value })} />
      <div className="chips">
        {(["A", "B", "C"] as Grade[]).map((g) => (
          <button key={g} className={`chip ${f.grades.has(g) ? "on" : ""}`} onClick={() => toggle(g)}
            style={f.grades.has(g) ? { background: GRADE_COLOR[g], borderColor: GRADE_COLOR[g] } : {}}>
            {g}
          </button>
        ))}
        <label className="check"><input type="checkbox" checked={f.hideExcluded}
          onChange={(e) => onChange({ ...f, hideExcluded: e.target.checked })} />제외 숨김</label>
        <label className="check"><input type="checkbox" checked={f.onlyComplete}
          onChange={(e) => onChange({ ...f, onlyComplete: e.target.checked })} />결측 없음만</label>
      </div>
    </div>
  );
}

export function CandidateList({ items, selectedId, onSelect }: { items: Scored[]; selectedId: string | null; onSelect: (id: string) => void }) {
  return (
    <ol className="list">
      {items.slice(0, 300).map((s) => (
        <li key={s.bld_id} className={s.bld_id === selectedId ? "sel" : ""} onClick={() => onSelect(s.bld_id)}>
          <span className="rank">{s.rank_main ?? "–"}</span>
          <span className="dot" style={{ background: s.exclude_reason ? "#adb5bd" : GRADE_COLOR[s.confidence] }} />
          <span className="li-main">
            <b>{s.bld_id}</b>
            <span className="muted small">{s.mainPurpsCdNm ?? "용도 미상"} · {s.adm_nm ?? ""}</span>
          </span>
          <span className="li-score">
            {s.exclude_reason ? <span className="muted small">제외</span>
              : s.score !== null ? s.score.toFixed(1)
              : <span title="결측 항목 있음 → 범위">{s.score_low.toFixed(0)}~{s.score_high.toFixed(0)}</span>}
          </span>
        </li>
      ))}
      {items.length === 0 && <li className="muted">조건에 맞는 건물이 없습니다.</li>}
    </ol>
  );
}

export function SensitivityView({ items, weights, topN, delta }: { items: BuildingProps[]; weights: Weights; topN: number; delta: number }) {
  const rows = useMemo(() => weightSensitivity(items, weights, topN, delta), [items, weights, topN, delta]);
  return (
    <div className="page">
      <h2>가중치 민감도 — Top {topN} 교체율</h2>
      <p className="muted">각 가중치를 ±{delta * 100}% 바꾸거나 항목을 빼고 다시 계산했을 때, 기존 Top {topN} 중 몇 %가 바뀌는지 보여줍니다. 교체율이 높을수록 그 항목의 가중치를 협의할 때 신중해야 합니다.</p>
      <table className="tbl">
        <thead><tr><th>항목</th><th>+{delta * 100}%</th><th>−{delta * 100}%</th><th>제외</th></tr></thead>
        <tbody>
          {COMPONENTS.map((c) => (
            <tr key={c}>
              <td>{COMPONENT_LABEL[c]}</td>
              {rows.filter((r) => r.component === c).map((r) => (
                <td key={r.change}>
                  <div className="cell-bar"><div style={{ width: `${r.turnover * 100}%` }} /></div>
                  {(r.turnover * 100).toFixed(0)}%
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SeniorView({ bundle }: { bundle: Bundle }) {
  const st = bundle.crawl_stats;
  const s = bundle.senior_centers;
  return (
    <div className="page">
      <h2>경로당 동적 수집 결과</h2>
      <p className="muted">부산시 빅데이터웨이브「지도 기반 데이터」→ 공공데이터 지도 → 사회복지 → 경로당 현황. Playwright로 지도 칸을 이동하며 지점을 클릭해 정보창을 수집했습니다.</p>
      {st && (
        <div className="stats">
          <Stat label="탐색 칸" v={st.cells} sub={`지점 있는 칸 ${st.cells_with_points}`} />
          <Stat label="클릭" v={st.clicked} />
          <Stat label="수집 성공" v={st.ok} />
          <Stat label="중복" v={st.dup} sub="인접 칸 겹침·동일 좌표" />
          <Stat label="정보창 누락" v={st.no_popup} />
          <Stat label="고유 시설" v={s.length} sub={`대상 구 ${s.filter((x) => x.in_target_gu).length}곳`} />
        </div>
      )}
      {bundle.senior_compare && (
        <p>공공 CSV 대조: {Object.entries(bundle.senior_compare).map(([k, v]) => `${k} ${v}`).join(" · ")}</p>
      )}
      <table className="tbl">
        <thead><tr><th>#</th><th>시설명</th><th>주소</th><th>좌표</th><th>건물 결합</th></tr></thead>
        <tbody>
          {s.map((x, i) => (
            <tr key={x.facility_key ?? i} className={x.in_target_gu === false ? "dim" : ""}>
              <td>{i + 1}</td><td>{x.name ?? "–"}</td><td>{x.address ?? "–"}</td>
              <td className="mono small">{x.lat.toFixed(5)}, {x.lon.toFixed(5)}</td>
              <td>{x.fac_match ?? <span className="muted">join 전</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {st && <p className="muted small">수집 {st.started_at} ~ {st.finished_at}. 지도 배경·타일은 수집하지 않았습니다.</p>}
    </div>
  );
}

function Stat({ label, v, sub }: { label: string; v: number; sub?: string }) {
  return (
    <div className="stat">
      <div className="muted small">{label}</div>
      <div className="big">{v.toLocaleString()}</div>
      {sub && <div className="muted small">{sub}</div>}
    </div>
  );
}
