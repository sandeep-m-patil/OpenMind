import { formatLatency, formatPercent, humanize, riskTone, statusTone } from "./format";

describe("formatting", () => {
  it("shows latency in ms below a second and seconds above", () => {
    expect([formatLatency(0.273), formatLatency(7.594), formatLatency(null)]).toEqual(["273 ms", "7.6 s", "n/a"]);
  });

  it("shows ratios as whole percentages", () => {
    expect([formatPercent(0.936), formatPercent(undefined)]).toEqual(["94%", "n/a"]);
  });

  it("humanizes enum values", () => {
    expect([humanize("REMEDIATION_FAILED"), humanize(null)]).toEqual(["Remediation failed", "—"]);
  });

  it("maps statuses to tones", () => {
    expect(["RESOLVED", "ERROR", "PENDING_APPROVAL", "REJECTED", "VERIFYING"].map(statusTone)).toEqual(["good", "bad", "warn", "neutral", "wait"]);
  });

  it("maps risk to tones", () => {
    expect(["LOW", "MEDIUM", "HIGH", null].map(riskTone)).toEqual(["good", "warn", "bad", "neutral"]);
  });
});
