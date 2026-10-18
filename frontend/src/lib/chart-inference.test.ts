import { describe, expect, it } from "vitest";
import { deriveExtremes, inferChart, toChartData } from "./chart-inference";

const cols = (...defs: Array<[string, string | null]>) => defs.map(([name, data_type]) => ({ name, data_type }));

describe("inferChart", () => {
  it("returns null for empty results", () => {
    expect(inferChart(cols(["A", "VARCHAR"]), [])).toBeNull();
  });

  it("uses KPI figures for a single numeric row", () => {
    const spec = inferChart(cols(["TOTAL", "NUMBER"]), [{ TOTAL: 5 }]);
    expect(spec?.kind).toBe("kpi");
    expect(spec?.y).toEqual(["TOTAL"]);
  });

  it("picks a line chart for a date dimension", () => {
    const rows = [
      { D: "2024-02-01", V: 2 },
      { D: "2024-01-01", V: 1 },
    ];
    const spec = inferChart(cols(["D", "DATE"], ["V", "NUMBER"]), rows);
    expect(spec?.kind).toBe("line");
    expect(spec?.x).toBe("D");
    // toChartData sorts by time
    expect(toChartData(spec!, rows).map((r) => r.D)).toEqual(["2024-01-01", "2024-02-01"]);
  });

  it("treats a numeric YEAR column as time, not as a measure", () => {
    const spec = inferChart(cols(["ORDER_YEAR", "NUMBER"], ["REVENUE", "NUMBER"]), [
      { ORDER_YEAR: 1992, REVENUE: 10 },
      { ORDER_YEAR: 1993, REVENUE: 12 },
    ]);
    expect(spec).toMatchObject({ kind: "line", x: "ORDER_YEAR", y: ["REVENUE"] });
  });

  it("picks vertical bars for a few short categories", () => {
    const spec = inferChart(cols(["REGION", "VARCHAR"], ["REV", "NUMBER"]), [
      { REGION: "ASIA", REV: 1 },
      { REGION: "EUROPE", REV: 2 },
    ]);
    expect(spec?.kind).toBe("bar");
  });

  it("switches to horizontal bars for many or long labels", () => {
    const rows = Array.from({ length: 10 }, (_, i) => ({ NAME: `Customer#00000${i}`, SPENT: i }));
    expect(inferChart(cols(["NAME", "VARCHAR"], ["SPENT", "NUMBER"]), rows)?.kind).toBe("horizontal_bar");
  });

  it("does not chart too many categories", () => {
    const rows = Array.from({ length: 80 }, (_, i) => ({ NAME: `n${i}`, V: i }));
    expect(inferChart(cols(["NAME", "VARCHAR"], ["V", "NUMBER"]), rows)).toBeNull();
  });

  it("does not treat key/id columns as measures", () => {
    const spec = inferChart(cols(["C_CUSTKEY", "NUMBER"], ["C_NAME", "VARCHAR"]), [
      { C_CUSTKEY: 1, C_NAME: "a" },
      { C_CUSTKEY: 2, C_NAME: "b" },
    ]);
    expect(spec).toBeNull();
  });

  it("detects numeric strings without declared types", () => {
    const spec = inferChart(cols(["SEG", null], ["TOTAL", null]), [
      { SEG: "A", TOTAL: "10.5" },
      { SEG: "B", TOTAL: "3" },
    ]);
    expect(spec).toMatchObject({ kind: "bar", y: ["TOTAL"] });
  });

  it("honours a valid backend hint and ignores one naming missing columns", () => {
    const c = cols(["SEG", "VARCHAR"], ["V", "NUMBER"]);
    const rows = [
      { SEG: "A", V: 1 },
      { SEG: "B", V: 2 },
    ];
    expect(inferChart(c, rows, { type: "pie", x: "SEG", y: ["V"] })?.source).toBe("backend");
    expect(inferChart(c, rows, { type: "pie", x: "NOPE", y: ["V"] })?.source).toBe("heuristic");
    expect(inferChart(c, rows, { type: "none" })).toBeNull();
  });

  it("rejects a pie hint with negative values", () => {
    const c = cols(["SEG", "VARCHAR"], ["V", "NUMBER"]);
    const spec = inferChart(c, [{ SEG: "A", V: -1 }, { SEG: "B", V: 2 }], { type: "pie", x: "SEG", y: ["V"] });
    expect(spec?.kind).toBe("bar");
  });
});

describe("deriveExtremes", () => {
  const spec = { kind: "bar" as const, x: "R", y: ["V"], reason: "", source: "heuristic" as const };
  const rows = [
    { R: "a", V: 3 },
    { R: "b", V: 9 },
    { R: "c", V: 1 },
  ];
  it("finds max and min rows", () => {
    const e = deriveExtremes(spec, rows, false);
    expect(e?.max.R).toBe("b");
    expect(e?.min.R).toBe("c");
  });
  it("refuses to derive extremes from truncated results", () => {
    expect(deriveExtremes(spec, rows, true)).toBeNull();
  });
});

describe("comparableMeasures", () => {
  it("drops series on a very different scale so one axis stays honest", () => {
    const spec = inferChart(
      [
        { name: "ORDER_YEAR", data_type: "NUMBER" },
        { name: "TOTAL_ORDER_VALUE", data_type: "NUMBER" },
        { name: "ORDERS", data_type: "NUMBER" },
      ],
      [
        { ORDER_YEAR: 1992, TOTAL_ORDER_VALUE: 3.4e10, ORDERS: 228091 },
        { ORDER_YEAR: 1993, TOTAL_ORDER_VALUE: 3.5e10, ORDERS: 227598 },
      ],
    );
    expect(spec?.y).toEqual(["TOTAL_ORDER_VALUE"]);
  });
});
