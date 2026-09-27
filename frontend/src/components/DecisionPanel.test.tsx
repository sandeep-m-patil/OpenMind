import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { RUNBOOKS } from "../test/fixtures";
import { DecisionPanel } from "./DecisionPanel";

function setup(onDecide = vi.fn().mockResolvedValue(undefined)) {
  render(<DecisionPanel recommended="RB-CACHE-002" recommendedParams={{}} runbooks={RUNBOOKS} onDecide={onDecide} />);
  return { onDecide, user: userEvent.setup() };
}

describe("DecisionPanel", () => {
  it("requires an operator name before deciding", async () => {
    const { onDecide, user } = setup();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect([onDecide.mock.calls.length, screen.getByRole("alert").textContent]).toEqual([0, "Enter your name first — decisions are attributed."]);
  });

  it("approves with operator and comment", async () => {
    const { onDecide, user } = setup();
    await user.type(screen.getByPlaceholderText("your name"), "harinath");
    await user.type(screen.getByPlaceholderText(/why\?/), "looks right");
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(onDecide).toHaveBeenCalledWith({ decision: "APPROVED", operator: "harinath", comment: "looks right" });
  });

  it("edits the recommendation into a different runbook with parameters", async () => {
    const { onDecide, user } = setup();
    await user.type(screen.getByPlaceholderText("your name"), "sre");
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.selectOptions(screen.getByRole("combobox"), "RB-CACHE-001");
    await user.clear(screen.getByLabelText("max_idle_hours"));
    await user.type(screen.getByLabelText("max_idle_hours"), "48");
    await user.click(screen.getByRole("button", { name: "Submit edited action" }));
    expect(onDecide).toHaveBeenCalledWith(expect.objectContaining({ decision: "MODIFIED", runbook_id: "RB-CACHE-001", params: { max_idle_hours: 48 } }));
  });

  it("shows the backend's refusal", async () => {
    const { user } = setup(vi.fn().mockRejectedValue(new Error("parameter outside range")));
    await user.type(screen.getByPlaceholderText("your name"), "sre");
    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("parameter outside range");
  });

  it("remembers the operator name", async () => {
    const { user } = setup();
    await user.type(screen.getByPlaceholderText("your name"), "sre");
    await user.click(screen.getByRole("button", { name: "Execute manually" }));
    expect(localStorage.getItem("opsmind.operator")).toBe("sre");
  });
});
