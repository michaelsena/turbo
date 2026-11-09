import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MarketIdentity } from "./MarketIdentity";
import type { MarketDetail } from "./types";

import fixture from "./test/fixtures/provisional-market.json";

const market: MarketDetail = fixture.market;

afterEach(cleanup);
function dimension(name: string) { return within(screen.getByRole("article", { name })); }

describe("MarketIdentity", () => {
  it("renders seven exact narratives with confidence and evidence class", () => {
    render(<MarketIdentity market={market} />);
    expect(screen.getAllByRole("article")).toHaveLength(7);
    expect(dimension("Buyer").getByText(market.buyer!)).toBeInTheDocument();
    expect(dimension("Job to be done").getByText(market.job_to_be_done!)).toBeInTheDocument();
    expect(dimension("Delivery model").getByText(market.delivery_model!)).toBeInTheDocument();
    expect(dimension("Workforce model").getByText(market.workforce_model!)).toBeInTheDocument();
    expect(dimension("Economics and risk").getByText("Unknown.")).toBeInTheDocument();
    expect(dimension("Acquisition universe").getByText(market.acquisition_universe!)).toBeInTheDocument();
    const ai = dimension("Ambient AI workflow");
    expect(ai.getByText("Unknown from the frozen evidence.")).toBeInTheDocument();
    expect(ai.getByText("0.1 / 1")).toBeInTheDocument();
    expect(ai.getByText("unknown", { exact: true })).toBeInTheDocument();
    expect(dimension("Buyer").getByText("inference", { exact: true })).toBeInTheDocument();
    expect(screen.getByText(/not an investment score/)).toBeInTheDocument();
    for (const exclusion of market.explicit_exclusions!) expect(screen.getByText(exclusion)).toBeInTheDocument();
  });

  it("preserves zero confidence while missing values remain explicit", () => {
    render(<MarketIdentity market={{ ...market, buyer: null, job_to_be_done: undefined, confidence_by_dimension: { buyer: 0, job: null }, evidence_by_dimension: { buyer: "assumption" } }} />);
    const buyer = dimension("Buyer");
    expect(buyer.getByText("0 / 1")).toBeInTheDocument();
    expect(buyer.getByText("assumption", { exact: true })).toBeInTheDocument();
    expect(buyer.getByText("Not recorded in this snapshot")).toBeInTheDocument();
    expect(dimension("Job to be done").getAllByText("Not recorded in this snapshot")).toHaveLength(3);
    expect(dimension("Ambient AI workflow").queryByText("0 / 1")).not.toBeInTheDocument();
  });

  it("distinguishes empty recorded lists from absent lists", () => {
    const { rerender } = render(<MarketIdentity market={{ ...market, explicit_exclusions: [], supporting_evidence_ids: [], counterevidence_ids: [] }} />);
    expect(screen.getAllByText("None recorded")).toHaveLength(3);
    expect(screen.queryByText("Not recorded in this snapshot")).not.toBeInTheDocument();
    rerender(<MarketIdentity market={{ ...market, explicit_exclusions: null, supporting_evidence_ids: undefined, counterevidence_ids: null }} />);
    expect(screen.getAllByText("Not recorded in this snapshot")).toHaveLength(3);
    expect(screen.queryByText("None recorded")).not.toBeInTheDocument();
  });

  it("keeps global supporting and contrary IDs separate without invented links", () => {
    const longId = `evidence:fixture:${"a".repeat(200)}`;
    render(<MarketIdentity market={{ ...market, supporting_evidence_ids: [longId] }} />);
    const support = screen.getByText("Supporting evidence IDs").closest("details")!;
    const contrary = screen.getByText("Counterevidence IDs").closest("details")!;
    expect(within(support).getByText(longId).tagName).toBe("CODE");
    expect(within(support).queryByText(market.counterevidence_ids![0])).not.toBeInTheDocument();
    expect(within(contrary).getByText(market.counterevidence_ids![0])).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
