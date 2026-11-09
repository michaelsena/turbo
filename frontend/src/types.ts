export interface Provenance {
  source_run_id: string;
  partition_id: string;
  graph_version_id: string;
  release_id: string;
  as_of_utc: string;
  context_fingerprint: string;
  read_model_version: string;
}

export interface Envelope<T> { data: T; provenance: Provenance }
export interface Page<T> { items: T[]; page: number; page_size: number; total: number; pages: number }
export type VersionTuple = Pick<Provenance, "source_run_id" | "partition_id" | "graph_version_id">;

export interface MarketSummary {
  market_id: string;
  market_version_id: string;
  canonical_name: string;
  definition: string;
  activation_status: string;
  research_gap_ids: string[];
  parent_market_id: string | null;
}

export interface MarketDetail extends MarketSummary {
  aliases: string[];
  boundary: Record<string, unknown>;
  mappings: Record<string, unknown>[];
  research_gaps: Record<string, unknown>[];
  source_records: Record<string, unknown>[];
  audit_chain: Record<string, string | null>;
  [key: string]: unknown;
}

export interface FamilySummary {
  family_id: string;
  label: string;
  family_kind: string;
  status: string;
  schedulable: boolean;
  counts: FamilyCounts;
  neutral_priority: { ordering_key: Array<string | number> };
  batch_id: string | null;
  batch_ordinal: number | null;
}

export interface FamilyCounts {
  required_identities: number;
  context_identities: number;
  required_candidates: number;
  [key: string]: number;
}

export interface Identity {
  identity_id: string;
  identity_type: string;
  source_code: string;
  labels: string[];
  analysis_labels: string[];
  assignment: Record<string, unknown>;
}

export interface FamilyDetail extends FamilySummary {
  required_identities: Identity[];
  context_identities: Page<Identity>;
  required_candidates: Record<string, unknown>[];
  batch: Batch | null;
  ownership_notice: string;
  [key: string]: unknown;
}

export interface Batch {
  batch_id: string;
  ordinal: number;
  status: string;
  family_ids: string[];
  required_identities: number;
  required_candidates: number;
}

export interface Versions {
  source_runs: Array<Record<string, unknown>>;
  partitions: Array<Record<string, unknown>>;
  graph_releases: Array<Record<string, unknown>>;
  compatible_snapshots: Array<Provenance & { current: boolean }>;
  current: Provenance;
}

export interface SystemContext {
  source_universe: { normalized_identities: number; [key: string]: unknown };
  family_schedule: { counts: Record<string, number>; [key: string]: unknown };
  canonical_market_graph: Record<string, number | string>;
  canonical_markets: number;
  [key: string]: unknown;
}
