import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { App } from "../App";
import { RESOLVED_STATE, RUNBOOKS, STRATEGIES, incident, mockApi } from "../test/fixtures";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("incident list", () => {
  it("shows memory matches and status per incident", async () => {
    mockApi({ "/v1/incidents": [incident()] });
    renderAt("/");
    const row = (await screen.findByText("INC-1002")).closest("tr")!;
    expect([within(row).getByText("↺ INC-1001"), within(row).getByText("Pending approval")]).toHaveLength(2);
  });

  it("explains how to start when empty", async () => {
    mockApi({ "/v1/incidents": [] });
    renderAt("/");
    expect(await screen.findByText(/No incidents yet/)).toBeInTheDocument();
  });

  it("reports an unavailable backend", async () => {
    mockApi({});
    renderAt("/");
    expect(await screen.findByText(/Backend unavailable/)).toBeInTheDocument();
  });
});

describe("incident detail", () => {
  it("shows the key facts, recalled memory and decision panel while pending", async () => {
    mockApi({ "/v1/incidents/INC-1002": incident(), "/v1/runbooks": RUNBOOKS });
    renderAt("/incidents/INC-1002");
    expect(await screen.findByText("Operator rejected full flush")).toBeInTheDocument();
    expect([screen.getByLabelText("Incident summary"), screen.getByLabelText("Human decision")]).toHaveLength(2);
  });

  it("submits a decision to the backend", async () => {
    const calls: { url: string; body?: string }[] = [];
    mockApi({ "/decisions": {}, "/v1/incidents/INC-1002": incident(), "/v1/runbooks": RUNBOOKS }, calls);
    renderAt("/incidents/INC-1002");
    const user = userEvent.setup();
    await user.type(await screen.findByPlaceholderText("your name"), "sre");
    await user.click(screen.getByRole("button", { name: "Approve" }));
    const decision = calls.find((c) => c.url.endsWith("/decisions"))!;
    expect(JSON.parse(decision.body!)).toEqual({ decision: "APPROVED", operator: "sre", comment: "" });
  });

  it("shows execution, before/after verification and the lesson when resolved", async () => {
    mockApi({ "/v1/incidents/INC-1002": incident({ status: "RESOLVED" }, RESOLVED_STATE), "/v1/runbooks": RUNBOOKS });
    renderAt("/incidents/INC-1002");
    expect(await screen.findByText("7.6 s → 273 ms")).toBeInTheDocument();
    expect([screen.getByText(/RB-CACHE-001 resolved cache_saturation/), screen.getByText("Dry run (--check)")]).toHaveLength(2);
  });

  it("reports a missing incident", async () => {
    mockApi({ "/v1/runbooks": RUNBOOKS });
    renderAt("/incidents/INC-9");
    expect(await screen.findByText("not found")).toBeInTheDocument();
  });

  it("explains when Hindsight was unavailable", async () => {
    const state = { historical_memories: [], memory_status: "unavailable: timeout", tool_errors: ["get_metrics: down"] };
    mockApi({ "/v1/incidents/INC-1002": incident({ historical_matches: [] }, state), "/v1/runbooks": RUNBOOKS });
    renderAt("/incidents/INC-1002");
    expect(await screen.findByText("Hindsight unavailable: timeout")).toBeInTheDocument();
  });
});

describe("learning page", () => {
  it("shows strategy scores and the runbook catalog", async () => {
    mockApi({ "/v1/strategies": STRATEGIES, "/v1/runbooks": RUNBOOKS });
    renderAt("/learning");
    expect(await screen.findByText("1.00")).toBeInTheDocument();
    expect(await screen.findByText("Full cache flush")).toBeInTheDocument();
  });

  it("searches Hindsight memory", async () => {
    mockApi({ "/v1/strategies": [], "/v1/runbooks": [], "/v1/memories": incident().state.historical_memories });
    renderAt("/learning");
    await userEvent.setup().click(screen.getByRole("button", { name: "Recall" }));
    expect(await screen.findByText("Operator rejected full flush")).toBeInTheDocument();
  });

  it("reports memory search failures", async () => {
    mockApi({ "/v1/strategies": [], "/v1/runbooks": [], "/v1/memories": new Error("Hindsight unavailable") });
    renderAt("/learning");
    await userEvent.setup().click(screen.getByRole("button", { name: "Recall" }));
    expect(await screen.findByText("Hindsight unavailable")).toBeInTheDocument();
  });
});
