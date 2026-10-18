import { describe, expect, it } from "vitest";
import { formatCell, formatDuration, formatNumber, humanizeColumn, toNumber } from "./formatters";

describe("formatters", () => {
  it("formats numbers, compact and currency", () => {
    expect(formatNumber(1234567)).toBe("1,234,567");
    expect(formatNumber(12.345)).toBe("12.35");
    expect(formatNumber(43750214321.47, { compact: true, currency: true })).toBe("$43.8B");
    expect(formatNumber(-1500, { currency: true })).toBe("-$1,500");
  });

  it("parses numeric strings but not mixed text", () => {
    expect(toNumber("10.50")).toBe(10.5);
    expect(toNumber("1e3")).toBe(1000);
    expect(toNumber("12 apples")).toBeNull();
    expect(toNumber("")).toBeNull();
  });

  it("formats cells by type and name", () => {
    expect(formatCell(null, { name: "X" })).toEqual({ text: "null", kind: "null" });
    expect(formatCell(1995, { name: "ORDER_YEAR", data_type: "NUMBER" }).text).toBe("1995");
    expect(formatCell(42, { name: "C_CUSTKEY", data_type: "NUMBER" }).text).toBe("42");
    expect(formatCell(7012696.48, { name: "TOTAL_SPENT", data_type: "NUMBER" }).text).toBe("$7,012,696.48");
    expect(formatCell("2024-01-05", { name: "D", data_type: "DATE" })).toEqual({ text: "2024-01-05", kind: "date" });
    // A VARCHAR that looks numeric (e.g. a phone or code) stays text.
    expect(formatCell("0042", { name: "CODE", data_type: "VARCHAR" }).text).toBe("0042");
    expect(formatCell({ a: 1 }, { name: "J" }).kind).toBe("json");
  });

  it("formats durations", () => {
    expect(formatDuration(320)).toBe("320 ms");
    expect(formatDuration(1520)).toBe("1.52 s");
    expect(formatDuration(null)).toBeNull();
  });

  it("humanizes column names", () => {
    expect(humanizeColumn("TOTAL_ORDER_VALUE")).toBe("Total order value");
    expect(humanizeColumn("L_EXTENDEDPRICE")).toBe("Extendedprice");
  });
});
