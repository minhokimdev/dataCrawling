import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { BuildingFeature, Scored, SeniorCenter } from "../types";

export const GRADE_COLOR = { A: "#2f9e44", B: "#f08c00", C: "#e03131" } as const;

function FitBounds({ features }: { features: BuildingFeature[] }) {
  const map = useMap();
  useEffect(() => {
    if (!features.length) return;
    const b = L.geoJSON({ type: "FeatureCollection", features } as never).getBounds();
    if (b.isValid()) map.fitBounds(b, { padding: [24, 24] });
  }, [features, map]);
  return null;
}

function useZoom() {
  const map = useMap();
  const [z, setZ] = useState(map.getZoom());
  useEffect(() => {
    const h = () => setZ(map.getZoom());
    map.on("zoomend", h);
    return () => { map.off("zoomend", h); };
  }, [map]);
  return z;
}

const POLYGON_MIN_ZOOM = 16;

/** 낮은 줌에서는 건물 폴리곤이 점보다 작아 보이지 않으므로 중심점 원으로 대신 그린다. */
function BuildingDots({ features, scored, topIds, selectedId, onSelect }: Omit<Props, "seniors" | "showSeniors">) {
  const zoom = useZoom();
  const centers = useMemo(
    () => features.map((f) => ({ p: f.properties, c: L.geoJSON(f as never).getBounds().getCenter() })), [features]);
  if (zoom >= POLYGON_MIN_ZOOM) return null;
  return (
    <>
      {centers.map(({ p, c }) => {
        const s = scored.get(p.bld_id);
        const top = topIds.has(p.bld_id);
        const color = p.exclude_reason ? "#adb5bd" : GRADE_COLOR[p.confidence];
        return (
          <CircleMarker key={p.bld_id} center={c} radius={p.bld_id === selectedId ? 9 : top ? 6 : 3.5}
            pathOptions={{ color: p.bld_id === selectedId ? "#1c7ed6" : "#fff", weight: top ? 1.5 : 0.5,
              fillColor: color, fillOpacity: top ? 0.95 : 0.55, dashArray: s?.missing.length ? "2 2" : undefined }}
            eventHandlers={{ click: () => onSelect(p.bld_id) }}>
            <Tooltip>#{s?.rank_main ?? "-"} {p.bld_id} · 신뢰도 {p.confidence}</Tooltip>
          </CircleMarker>
        );
      })}
    </>
  );
}

function FlyTo({ feature }: { feature?: BuildingFeature }) {
  const map = useMap();
  useEffect(() => {
    if (!feature) return;
    const c = L.geoJSON(feature as never).getBounds().getCenter();
    map.flyTo(c, Math.max(map.getZoom(), 17), { duration: 0.6 });
  }, [feature, map]);
  return null;
}

interface Props {
  features: BuildingFeature[];
  scored: Map<string, Scored>;
  topIds: Set<string>;
  seniors: SeniorCenter[];
  showSeniors: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function MapView({ features, scored, topIds, seniors, showSeniors, selectedId, onSelect }: Props) {
  const selected = useMemo(() => features.find((f) => f.properties.bld_id === selectedId), [features, selectedId]);
  // GeoJSON 레이어는 data 가 바뀌어도 스타일이 갱신되지 않으므로 key 로 다시 그린다.
  const styleKey = useMemo(() => [...topIds].join(",") + selectedId, [topIds, selectedId]);

  return (
    <MapContainer center={[35.1, 128.99]} zoom={14} className="map" preferCanvas>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds features={features} />
      <FlyTo feature={selected} />
      <GeoJSON
        key={styleKey}
        data={{ type: "FeatureCollection", features } as never}
        style={(f) => {
          const p = (f as unknown as BuildingFeature).properties;
          const s = scored.get(p.bld_id);
          const excluded = !!p.exclude_reason;
          const top = topIds.has(p.bld_id);
          const sel = p.bld_id === selectedId;
          return {
            color: sel ? "#1c7ed6" : excluded ? "#adb5bd" : GRADE_COLOR[p.confidence],
            weight: sel ? 4 : top ? 2 : 1,
            fillOpacity: excluded ? 0.08 : top ? 0.65 : 0.2,
            fillColor: excluded ? "#adb5bd" : GRADE_COLOR[p.confidence],
            dashArray: s && s.missing.length ? "4 3" : undefined,
          };
        }}
        onEachFeature={(f, layer) => {
          const p = (f as unknown as BuildingFeature).properties;
          const s = scored.get(p.bld_id);
          const label = p.exclude_reason
            ? `${p.bld_id} · 제외: ${p.exclude_reason}`
            : `#${s?.rank_main ?? "-"} ${p.bld_id} · ${s?.score_low.toFixed(1)}~${s?.score_high.toFixed(1)}점 · 신뢰도 ${p.confidence}`;
          layer.bindTooltip(label, { sticky: true });
          layer.on("click", () => onSelect(p.bld_id));
        }}
      />
      <BuildingDots features={features} scored={scored} topIds={topIds} selectedId={selectedId} onSelect={onSelect} />
      {showSeniors &&
        seniors.map((s, i) => (
          <CircleMarker key={s.facility_key ?? i} center={[s.lat, s.lon]} radius={5}
            pathOptions={{ color: "#5f3dc4", fillColor: "#9775fa", fillOpacity: 0.9, weight: 1.5 }}>
            <Tooltip>
              <b>{s.name ?? "(이름 없음)"}</b>
              <br />
              {s.address}
            </Tooltip>
          </CircleMarker>
        ))}
    </MapContainer>
  );
}
