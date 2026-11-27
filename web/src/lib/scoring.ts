// src/coolroof/scoring/priority.py 의 combine / rank / weight_sensitivity 를 그대로 옮긴 것.
// 결측 항목은 0점으로 숨기지 않고 score_low(결측=0) ~ score_high(결측=100) 범위로 보여준다.
import { COMPONENTS, type BuildingProps, type Component, type Scored, type Weights } from "../types";

export function normalize(w: Weights): Weights {
  const tot = COMPONENTS.reduce((s, c) => s + Math.max(0, w[c]), 0) || 1;
  return Object.fromEntries(COMPONENTS.map((c) => [c, Math.max(0, w[c]) / tot])) as Weights;
}

export function combine(b: BuildingProps, weights: Weights): Omit<Scored, "rank_main" | "rank_aux"> {
  let low = 0, high = 0, availW = 0, availSum = 0;
  const missing: Component[] = [];
  for (const c of COMPONENTS) {
    const v = b[c];
    const w = weights[c];
    if (v === null || v === undefined || Number.isNaN(v)) {
      missing.push(c);
      high += 100 * w;
    } else {
      low += v * w;
      high += v * w;
      availW += w;
      availSum += v * w;
    }
  }
  return {
    ...b,
    score_low: low,
    score_high: high,
    score: missing.length === 0 ? low : null,
    score_reweighted: availW > 0 ? availSum / availW : null,
    missing,
  };
}

/** 주 순위: 결측 없는 건 score, 결측 있는 건 보수적 score_low. 보조 순위: score_reweighted. 제외 건물은 순위 없음. */
export function rankAll(items: BuildingProps[], weights: Weights): Scored[] {
  const w = normalize(weights);
  const scored = items.map((b) => ({ ...combine(b, w), rank_main: null, rank_aux: null })) as Scored[];
  const live = scored.filter((s) => !s.exclude_reason);
  const assign = (key: (s: Scored) => number | null, field: "rank_main" | "rank_aux") => {
    live
      .filter((s) => key(s) !== null)
      .map((s, i) => ({ s, i, v: key(s) as number }))
      .sort((a, b) => b.v - a.v || a.i - b.i)
      .forEach(({ s }, r) => (s[field] = r + 1));
  };
  assign((s) => s.score ?? s.score_low, "rank_main");
  assign((s) => s.score_reweighted, "rank_aux");
  return scored.sort((a, b) => (a.rank_main ?? Infinity) - (b.rank_main ?? Infinity));
}

export function topIds(items: BuildingProps[], weights: Weights, n: number): Set<string> {
  return new Set(rankAll(items, weights).filter((s) => s.rank_main !== null).slice(0, n).map((s) => s.bld_id));
}

export interface SensitivityRow { component: Component; change: string; turnover: number }

/** 각 가중치를 ±delta 바꾸거나 항목을 제외했을 때 Top N 교체율. */
export function weightSensitivity(items: BuildingProps[], weights: Weights, n: number, delta = 0.2): SensitivityRow[] {
  const base = topIds(items, weights, n);
  const rows: SensitivityRow[] = [];
  for (const c of COMPONENTS) {
    for (const [label, f] of [[`+${delta * 100}%`, 1 + delta], [`-${delta * 100}%`, 1 - delta], ["제외", 0]] as const) {
      const top = topIds(items, { ...weights, [c]: weights[c] * f }, n);
      let kept = 0;
      base.forEach((id) => top.has(id) && kept++);
      rows.push({ component: c, change: label, turnover: base.size ? 1 - kept / base.size : 0 });
    }
  }
  return rows;
}
