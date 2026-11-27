import { useEffect, useMemo, useState } from "react";
import { CandidateCard } from "./components/CandidateCard";
import { MapView } from "./components/MapView";
import { CandidateList, FilterBar, SeniorView, SensitivityView, WeightPanel, type Filters } from "./components/Panels";
import { normalize, rankAll } from "./lib/scoring";
import type { Bundle, Scored, Weights } from "./types";

type Tab = "map" | "senior" | "sens";

export default function App() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("map");
  const [weights, setWeights] = useState<Weights | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showSeniors, setShowSeniors] = useState(true);
  const [filters, setFilters] = useState<Filters>({
    grades: new Set(["A", "B", "C"]), hideExcluded: true, onlyComplete: false, query: "",
  });

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/bundle.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((b: Bundle) => { setBundle(b); setWeights(b.meta.weights); })
      .catch((e) => setError(String(e)));
  }, []);

  const props = useMemo(() => bundle?.buildings.features.map((f) => f.properties) ?? [], [bundle]);
  const ranked = useMemo<Scored[]>(() => (weights ? rankAll(props, weights) : []), [props, weights]);
  const byId = useMemo(() => new Map(ranked.map((s) => [s.bld_id, s])), [ranked]);
  const topN = bundle?.meta.top_n ?? 50;
  const topIds = useMemo(
    () => new Set(ranked.filter((s) => s.rank_main !== null && s.rank_main <= topN).map((s) => s.bld_id)), [ranked, topN]);

  const visible = useMemo(() => {
    const q = filters.query.trim().toLowerCase();
    return ranked.filter((s) =>
      filters.grades.has(s.confidence) &&
      !(filters.hideExcluded && s.exclude_reason) &&
      !(filters.onlyComplete && s.missing.length) &&
      (!q || [s.bld_id, s.mainPurpsCdNm, s.adm_nm].some((v) => v?.toLowerCase().includes(q))));
  }, [ranked, filters]);
  const visibleIds = useMemo(() => new Set(visible.map((s) => s.bld_id)), [visible]);
  const features = useMemo(
    () => bundle?.buildings.features.filter((f) => visibleIds.has(f.properties.bld_id)) ?? [], [bundle, visibleIds]);

  if (error) return <div className="center">bundle.json 을 불러오지 못했습니다 ({error}).<br /><code>coolroof export-web</code> 을 먼저 실행하세요.</div>;
  if (!bundle || !weights) return <div className="center">불러오는 중…</div>;

  const live = ranked.filter((s) => !s.exclude_reason);
  const selected = selectedId ? byId.get(selectedId) : undefined;
  const m = bundle.meta;

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo">◻︎</span>
          <div>
            <h1>쿨루프 미발굴 후보 건물</h1>
            <div className="muted small">부산 {m.gu_name} · 영상 {m.image_date ?? "미기입"} · 생성 {m.generated_at.replace("T", " ")}</div>
          </div>
          {m.is_demo && <span className="demo" title="건물·점수는 화면 시연용 합성 데이터입니다. 경로당은 실제 수집 결과입니다.">DEMO · 합성 건물</span>}
        </div>
        <nav className="tabs">
          {([["map", "후보 지도"], ["senior", "경로당 수집"], ["sens", "가중치 민감도"]] as [Tab, string][]).map(([k, l]) => (
            <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>
          ))}
        </nav>
        <div className="kpis">
          <span><b>{live.length}</b> 대상</span>
          <span><b>{ranked.length - live.length}</b> 제외</span>
          <span><b>{live.filter((s) => s.missing.length).length}</b> 결측 포함</span>
          <span><b>{live.filter((s) => s.confidence === "C").length}</b> 수동검토</span>
        </div>
      </header>

      {tab === "map" && (
        <main className="main">
          <div className="side">
            <WeightPanel weights={weights} base={m.weights} onChange={setWeights} />
            <FilterBar f={filters} onChange={setFilters} />
            <div className="list-head">
              <span>순위 (상위 {topN} 강조)</span>
              <label className="check"><input type="checkbox" checked={showSeniors} onChange={(e) => setShowSeniors(e.target.checked)} />경로당</label>
            </div>
            <CandidateList items={visible} selectedId={selectedId} onSelect={setSelectedId} />
          </div>
          <div className="map-wrap">
            <MapView features={features} scored={byId} topIds={topIds} seniors={bundle.senior_centers}
              showSeniors={showSeniors} selectedId={selectedId} onSelect={setSelectedId} />
            <div className="legend">
              <span><i style={{ background: "#2f9e44" }} />신뢰도 A</span>
              <span><i style={{ background: "#f08c00" }} />B</span>
              <span><i style={{ background: "#e03131" }} />C</span>
              <span><i className="dash" />결측 포함</span>
              <span><i style={{ background: "#9775fa", borderRadius: 8 }} />경로당</span>
            </div>
            {selected && <CandidateCard s={selected} weights={normalize(weights)} onClose={() => setSelectedId(null)} />}
          </div>
        </main>
      )}
      {tab === "senior" && <SeniorView bundle={bundle} />}
      {tab === "sens" && <SensitivityView items={props} weights={weights} topN={topN} delta={m.sensitivity} />}
    </div>
  );
}
