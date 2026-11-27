import { describe, expect, it } from "vitest";
import type { BuildingProps, Weights } from "../types";
import { combine, rankAll, weightSensitivity } from "./scoring";

const W: Weights = { physical: 0.4, region_need: 0.35, non_support: 0.15, reliability: 0.1 };
const b = (id: string, p: Partial<BuildingProps>): BuildingProps => ({
  bld_id: id, physical: null, region_need: null, non_support: null, reliability: null, confidence: "A", ...p,
});

describe("combine (priority.py 와 동일)", () => {
  it("결측은 범위로", () => {
    const r = combine(b("x", { physical: 80, region_need: 60, reliability: 100 }), W);
    expect(r.score).toBeNull();
    expect(r.score_low).toBeCloseTo(0.4 * 80 + 0.35 * 60 + 0.1 * 100);
    expect(r.score_high).toBeCloseTo(r.score_low + 15);
    expect(r.score_reweighted).toBeCloseTo((0.4 * 80 + 0.35 * 60 + 0.1 * 100) / 0.85);
    expect(r.missing).toEqual(["non_support"]);
  });
  it("결측 없으면 score = score_low", () => {
    const r = combine(b("x", { physical: 50, region_need: 50, non_support: 50, reliability: 50 }), W);
    expect(r.score).toBeCloseTo(50);
  });
});

describe("rankAll", () => {
  const items = [
    b("a", { physical: 90, region_need: 90, non_support: 100, reliability: 100 }),
    b("b", { physical: 95, region_need: 95, reliability: 100 }),
    b("c", { physical: 99, region_need: 99, non_support: 100, reliability: 100, exclude_reason: "관할 구 밖" }),
  ];
  it("제외 건물은 순위 없음, 결측은 보수적 순위", () => {
    const r = Object.fromEntries(rankAll(items, W).map((s) => [s.bld_id, s]));
    expect(r.c.rank_main).toBeNull();
    expect(r.a.rank_main).toBe(1);
    expect(r.b.rank_main).toBe(2);
    expect(r.b.rank_aux).toBe(1);
  });
  it("민감도 12행, 교체율 0~1", () => {
    const s = weightSensitivity(items, W, 1);
    expect(s).toHaveLength(12);
    s.forEach((x) => expect(x.turnover).toBeGreaterThanOrEqual(0));
  });
});
