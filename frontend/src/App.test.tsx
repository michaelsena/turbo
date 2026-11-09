import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const provenance = {
  source_run_id: "run-2ea0f00db84148de663f",
  partition_id: "family-partition:60517981ab96e7f243c7033e",
  graph_version_id: "graph-e674a77fbfd5939c25c9e9a1",
  release_id: "graph-release-aa5b6f83e7a06e073d3a",
  as_of_utc: "2026-11-09T00:00:00Z",
  context_fingerprint: "abc",
  read_model_version: "1.0.0",
};
const historical = { ...provenance, partition_id: "family-partition:historical", context_fingerprint: "def", current: false };

function payload(url: string) {
  if (url.includes("/versions")) return { data: { source_runs: [], partitions: [], graph_releases: [], compatible_snapshots: [{ ...provenance, current: true }, historical], current: provenance }, provenance };
  if (url.includes("/context")) return { data: { source_universe: { normalized_identities: 11543 }, family_schedule: { counts: { families: 1026, schedulable_families: 1018 } }, canonical_market_graph: { open_research_gaps: 2 }, canonical_markets: 3 }, provenance };
  if (url.includes("/markets")) return { data: { items: [{ market_id: "market:1", market_version_id: "v1", canonical_name: "Office administrative services", definition: "A tested market boundary.", activation_status: "activated", research_gap_ids: [], parent_market_id: null }], page: 1, page_size: 10, total: 1, pages: 1 }, provenance };
  if (url.includes("/batches")) return { data: { items: [{ batch_id: "batch:1", ordinal: 1, status: "scheduled", family_ids: ["family:1"], required_identities: 1, required_candidates: 0 }], page: 1, page_size: 5, total: 1, pages: 1 }, provenance };
  throw new Error(`Unexpected URL: ${url}`);
}

function renderApp(path = "/") {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => ({ ok: true, json: async () => payload(String(input)) })));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Turbo research console", () => {
  it("keeps universe construction visibly separate from ranking", async () => {
    renderApp();
    expect(await screen.findByRole("heading", { name: /see the market universe/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /this is not a ranking/i })).toBeInTheDocument();
    expect(screen.getByText(/universe construction stays separate/i)).toBeInTheDocument();
  });

  it("shows exact snapshot provenance", async () => {
    renderApp();
    expect(await screen.findByText(provenance.partition_id)).toBeInTheDocument();
    expect(screen.getByText(provenance.graph_version_id)).toBeInTheDocument();
  });

  it("propagates an explicit compatible tuple into every subsequent API read", async () => {
    renderApp(`/?source_run_id=${encodeURIComponent(historical.source_run_id)}&partition_id=${encodeURIComponent(historical.partition_id)}&graph_version_id=${encodeURIComponent(historical.graph_version_id)}`);
    await screen.findByRole("combobox", { name: /research snapshot/i });
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes(`partition_id=${encodeURIComponent(historical.partition_id)}`))).toBe(true));
  });
});
