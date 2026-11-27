import type { Geometry } from "geojson";

export const COMPONENTS = ["physical", "region_need", "non_support", "reliability"] as const;
export type Component = (typeof COMPONENTS)[number];
export type Weights = Record<Component, number>;
export type Grade = "A" | "B" | "C";

export const COMPONENT_LABEL: Record<Component, string> = {
  physical: "물리적 적합성",
  region_need: "지역 필요도",
  non_support: "미지원 가능성",
  reliability: "자료 신뢰도",
};

export interface BuildingProps {
  bld_id: string;
  physical: number | null;
  region_need: number | null;
  non_support: number | null;
  reliability: number | null;
  confidence: Grade;
  roof_type?: "flat" | "pitched" | "metal" | "unknown" | "unreadable" | null;
  roof_source?: "register" | null;
  roof_basis?: string | null;
  senior_population?: number | null;
  senior_single_households?: number | null;
  senior_population_per_km2?: number | null;
  senior_single_households_per_km2?: number | null;
  flat_prob?: number | null;
  area_low_m2?: number | null;
  area_m2?: number | null;
  area_high_m2?: number | null;
  green_ratio?: number | null;
  white_ratio?: number | null;
  obstacle_ratio?: number | null;
  unreadable_reason?: string | null;
  match_method?: string | null;
  match_score?: number | null;
  missing_reason?: string | null;
  mainPurpsCdNm?: string | null;
  useAprDay?: string | null;
  exclude_reason?: string | null;
  adm_nm?: string | null;
  stat_year?: string | null;
  image_date?: string | null;
  platPlc?: string | null;
}

export interface BuildingFeature {
  type: "Feature";
  geometry: Geometry;
  properties: BuildingProps;
}

export interface SeniorCenter {
  facility_key?: string;
  name?: string | null;
  address?: string | null;
  category?: string | null;
  lon: number;
  lat: number;
  bld_id?: string | null;
  fac_match?: string | null;
  in_target_gu?: boolean | null;
}

export interface CrawlStats {
  cells: number;
  cells_with_points: number;
  clicked: number;
  ok: number;
  dup: number;
  no_popup: number;
  started_at: string;
  finished_at: string;
}

export interface Bundle {
  meta: {
    gu_name: string;
    sigungu_cd: string;
    image_date: string | null;
    analysis_base_date: string | null;
    generated_at: string;
    is_demo: boolean;
    weights: Weights;
    top_n: number;
    sensitivity: number;
  };
  buildings: { type: "FeatureCollection"; features: BuildingFeature[] };
  senior_centers: SeniorCenter[];
  senior_compare: Record<string, number> | null;
  crawl_stats: CrawlStats | null;
}

export interface Scored extends BuildingProps {
  score: number | null;
  score_low: number;
  score_high: number;
  score_reweighted: number | null;
  missing: Component[];
  rank_main: number | null;
  rank_aux: number | null;
}
