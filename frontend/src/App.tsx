import { useMemo, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { getJson } from "./api";
import { DataTable, ErrorState, Eyebrow, JsonDetails, Layout, Loading, Pager, Status } from "./components";
import type { Batch, FamilyDetail, FamilySummary, MarketDetail, MarketSummary, Page, SystemContext, Versions } from "./types";
import { useVersioning, VersionProvider } from "./versioning";

function useSystemContext() {
  const { apiUrl, selectedKey } = useVersioning();
  return useQuery({ queryKey: ["context", selectedKey], queryFn: () => getJson<SystemContext>(apiUrl("/api/v1/context")) });
}

export function App() {
  return <VersionProvider><AppRoutes /></VersionProvider>;
}

function AppRoutes() {
  const context = useSystemContext();
  return <Routes>
    <Route element={<Layout provenance={context.data?.provenance} />}>
      <Route index element={<Overview />} />
      <Route path="universe" element={<Universe />} />
      <Route path="markets/:marketId" element={<Market />} />
      <Route path="families" element={<Families />} />
      <Route path="families/:familyId" element={<Family />} />
      <Route path="batches" element={<Batches />} />
      <Route path="audit" element={<Audit />} />
      <Route path="*" element={<NotFound />} />
    </Route>
  </Routes>;
}

function Overview() {
  const { apiUrl, selectedKey, versionedPath } = useVersioning();
  const context = useSystemContext();
  const markets = useQuery({ queryKey: ["markets", selectedKey, 1, 10], queryFn: () => getJson<Page<MarketSummary>>(apiUrl("/api/v1/markets", { page_size: 10 })) });
  const batches = useQuery({ queryKey: ["batches", selectedKey, 1, 5], queryFn: () => getJson<Page<Batch>>(apiUrl("/api/v1/batches", { page_size: 5 })) });
  if (context.isPending || markets.isPending || batches.isPending) return <Loading />;
  const error = context.error || markets.error || batches.error;
  if (error) return <ErrorState error={error} />;
  const source = context.data.data.source_universe;
  const schedule = context.data.data.family_schedule.counts;
  const graph = context.data.data.canonical_market_graph;
  const metrics: Array<[string, number]> = [
    ["source identities", source.normalized_identities ?? 0],
    ["operating families", schedule.families ?? 0],
    ["schedulable families", schedule.schedulable_families ?? 0],
    ["canonical markets", context.data.data.canonical_markets],
    ["open graph gaps", Number(graph.open_research_gaps ?? 0)],
  ];
  return <>
    <section className="hero"><Eyebrow>Verified research system</Eyebrow><h1>See the market universe<br />as it is being built.</h1><p className="lede">A read-only view of source coverage, operating-family work, and the cumulative canonical Market Graph. Universe construction stays separate from filtering, evaluation, and ranking.</p></section>
    <section className="metric-grid" aria-label="Current verified counts">{metrics.map(([label, value]) => <article className="metric" key={label}><strong>{value.toLocaleString()}</strong><span>{label}</span></article>)}</section>
    <section className="two-column"><div className="panel"><div className="section-head"><div><Eyebrow>Canonical graph</Eyebrow><h2>Accepted markets</h2></div><Link to={versionedPath("/universe")}>Explore all</Link></div>{markets.data.data.items.map(market => <Link className="row-link" key={market.market_id} to={versionedPath(`/markets/${market.market_id}`)}><span><strong>{market.canonical_name}</strong><small>{market.definition}</small></span><Status value={market.activation_status} /></Link>)}</div>
    <div className="panel"><div className="section-head"><div><Eyebrow>Deterministic work queue</Eyebrow><h2>Next batches</h2></div><Link to={versionedPath("/batches")}>View manifest</Link></div>{batches.data.data.items.map(batch => <div className="row-link static" key={batch.batch_id}><span><strong>Batch {batch.ordinal}</strong><small>{batch.family_ids.length} families · {batch.required_identities.toLocaleString()} identities</small></span><Status value={batch.status} /></div>)}</div></section>
    <section className="callout"><div><Eyebrow>Important boundary</Eyebrow><h2>This is not a ranking.</h2></div><p>Family priority is administrative and neutral. A market’s presence means only that its boundary passed the audited universe-construction process.</p></section>
  </>;
}

function Universe() {
  const { apiUrl, selectedKey, versionedPath } = useVersioning();
  const [search, setSearch] = useSearchParams();
  const page = Number(search.get("page") || 1);
  const q = search.get("q") || "";
  const [draft, setDraft] = useState(q);
  const result = useQuery({ queryKey: ["markets", selectedKey, page, q], queryFn: () => getJson<Page<MarketSummary>>(apiUrl("/api/v1/markets", { page, q })) });
  const columns = useMemo<ColumnDef<MarketSummary>[]>(() => [
    { header: "Market", cell: ({ row }) => <><Link to={versionedPath(`/markets/${row.original.market_id}`)}><strong>{row.original.canonical_name}</strong><small>{row.original.definition}</small></Link><code>{row.original.market_id}</code></> },
    { header: "Status", cell: ({ row }) => <Status value={row.original.activation_status} /> },
    { header: "Open gaps", accessorFn: row => row.research_gap_ids.length },
    { header: "Parent", accessorFn: row => row.parent_market_id || "—" },
  ], [versionedPath]);
  function submit(event: FormEvent) { event.preventDefault(); setSearch(current => { current.delete("page"); draft ? current.set("q", draft) : current.delete("q"); return current; }); }
  return <><header className="page-head"><div><Eyebrow>Cumulative canonical graph</Eyebrow><h1>Market universe</h1><p>Accepted boundaries in the current graph version—not a shortlist or ranking.</p></div></header>
    <form className="filters compact" onSubmit={submit}><label><span>Search</span><input value={draft} onChange={event => setDraft(event.target.value)} placeholder="Name, definition, or ID" /></label><button>Search</button></form>
    {result.isPending ? <Loading /> : result.error ? <ErrorState error={result.error} /> : <><p className="result-count">{result.data.data.total.toLocaleString()} records</p><DataTable data={result.data.data.items} columns={columns} /><Pager page={result.data.data} setPage={value => setSearch(current => { current.set("page", String(value)); return current; })} /></>}
  </>;
}

function Market() {
  const { apiUrl, selectedKey, versionedPath } = useVersioning();
  const { marketId = "" } = useParams();
  const query = useQuery({ queryKey: ["market", selectedKey, marketId], queryFn: () => getJson<MarketDetail>(apiUrl(`/api/v1/markets/${marketId}`)) });
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorState error={query.error} />;
  const market = query.data.data;
  return <><Link className="back" to={versionedPath("/universe")}>← Market universe</Link><header className="page-head"><div><Eyebrow>Canonical market</Eyebrow><h1>{market.canonical_name}</h1><p>{market.definition}</p></div><Status value={market.activation_status} /></header>
    <section className="detail-grid"><article className="panel"><Eyebrow>Boundary</Eyebrow><h2>Inspect definition</h2><JsonDetails label="Included and excluded scope" value={market.boundary} /></article><article className="panel"><Eyebrow>Identity</Eyebrow><h2>Versioned record</h2><dl><dt>Market ID</dt><dd><code>{market.market_id}</code></dd><dt>Version</dt><dd><code>{market.market_version_id}</code></dd><dt>Parent</dt><dd>{market.parent_market_id || "None"}</dd><dt>Aliases</dt><dd>{market.aliases?.join(", ") || "None"}</dd></dl></article></section>
    <section className="panel"><div className="section-head"><div><Eyebrow>Open questions</Eyebrow><h2>Research gaps</h2></div><span>{market.research_gaps.length}</span></div>{market.research_gaps.map((gap, index) => <JsonDetails key={index} label={String(gap.gap_id ?? `Gap ${index + 1}`)} value={gap} />)}</section>
    <section className="two-column"><article className="panel"><Eyebrow>Source lineage</Eyebrow><h2>Evidence records</h2>{market.source_records.map((record, index) => <JsonDetails key={index} label={String(record.record_id ?? `Record ${index + 1}`)} value={record} />)}</article><article className="panel"><Eyebrow>Audit chain</Eyebrow><h2>Review receipts</h2><dl>{Object.entries(market.audit_chain).map(([key, value]) => <><dt key={`${key}-dt`}>{key.replaceAll("_", " ")}</dt><dd key={`${key}-dd`}><code>{value || "—"}</code></dd></>)}</dl></article></section>
  </>;
}

function Families() {
  const { apiUrl, selectedKey, versionedPath } = useVersioning();
  const [search, setSearch] = useSearchParams();
  const page = Number(search.get("page") || 1); const q = search.get("q") || ""; const [draft, setDraft] = useState(q);
  const result = useQuery({ queryKey: ["families", selectedKey, page, q], queryFn: () => getJson<Page<FamilySummary>>(apiUrl("/api/v1/families", { page, q })) });
  const columns = useMemo<ColumnDef<FamilySummary>[]>(() => [
    { header: "Family", cell: ({ row }) => <><Link to={versionedPath(`/families/${row.original.family_id}`)}><strong>{row.original.label}</strong></Link><code>{row.original.family_id}</code></> },
    { header: "Kind", cell: ({ row }) => row.original.family_kind.replaceAll("_", " ") },
    { header: "Status", cell: ({ row }) => <Status value={row.original.status} /> },
    { header: "Required", accessorFn: row => row.counts.required_identities },
    { header: "Context", accessorFn: row => row.counts.context_identities },
    { header: "Batch", accessorFn: row => row.batch_ordinal || "—" },
  ], [versionedPath]);
  return <><header className="page-head"><div><Eyebrow>Administrative schedule</Eyebrow><h1>Operating families</h1><p>Deterministic review ownership. Ordering is neutral and is not a market score.</p></div></header><div className="notice"><strong>Ownership is administrative.</strong> A family assignment is not evidence of market membership, attractiveness, Target eligibility, or economic primacy.</div>
    <form className="filters compact" onSubmit={event => { event.preventDefault(); setSearch(current => { current.delete("page"); draft ? current.set("q", draft) : current.delete("q"); return current; }); }}><label><span>Search</span><input value={draft} onChange={event => setDraft(event.target.value)} placeholder="Family label or ID" /></label><button>Search</button></form>
    {result.isPending ? <Loading /> : result.error ? <ErrorState error={result.error} /> : <><p className="result-count">{result.data.data.total.toLocaleString()} families</p><DataTable data={result.data.data.items} columns={columns} /><Pager page={result.data.data} setPage={value => setSearch(current => { current.set("page", String(value)); return current; })} /></>}
  </>;
}

function Family() {
  const { apiUrl, selectedKey, versionedPath } = useVersioning();
  const { familyId = "" } = useParams(); const [search, setSearch] = useSearchParams(); const contextPage = Number(search.get("context_page") || 1);
  const query = useQuery({ queryKey: ["family", selectedKey, familyId, contextPage], queryFn: () => getJson<FamilyDetail>(apiUrl(`/api/v1/families/${familyId}`, { context_page: contextPage })) });
  if (query.isPending) return <Loading />; if (query.error) return <ErrorState error={query.error} />; const family = query.data.data;
  return <><Link className="back" to={versionedPath("/families")}>← Operating families</Link><header className="page-head"><div><Eyebrow>{family.family_kind.replaceAll("_", " ")}</Eyebrow><h1>{family.label}</h1><code>{family.family_id}</code></div><Status value={family.status} /></header><div className="notice"><strong>Boundary notice.</strong> {family.ownership_notice}</div>
    <section className="metric-grid small"><Metric label="required identities" value={family.counts.required_identities} /><Metric label="context identities" value={family.counts.context_identities} /><Metric label="prior candidates" value={family.counts.required_candidates} /><Metric label="batch ordinal" value={family.batch?.ordinal ?? "—"} /></section>
    <section className="panel"><Eyebrow>Disposition work</Eyebrow><h2>Required identities</h2>{family.required_identities.map(identity => <IdentityRow key={identity.identity_id} identity={identity} />)}</section>
    <section className="panel"><div className="section-head"><div><Eyebrow>Supporting evidence</Eyebrow><h2>Context identities</h2></div><span>{family.context_identities.total}</span></div>{family.context_identities.items.map(identity => <IdentityRow key={identity.identity_id} identity={identity} />)}<Pager page={family.context_identities} setPage={value => setSearch(current => { current.set("context_page", String(value)); return current; })} /></section>
    {!!family.required_candidates.length && <section className="panel"><Eyebrow>Prior work</Eyebrow><h2>Required candidates</h2>{family.required_candidates.map((candidate, index) => <JsonDetails key={index} label={String(candidate.name ?? `Candidate ${index + 1}`)} value={candidate} />)}</section>}
  </>;
}

function IdentityRow({ identity }: { identity: FamilyDetail["required_identities"][number] }) { return <div className="row-link static"><span><strong>{(identity.analysis_labels.length ? identity.analysis_labels : identity.labels)[0]}</strong><code>{identity.identity_id}</code></span><small>{identity.identity_type}</small></div>; }
function Metric({ label, value }: { label: string; value: string | number }) { return <article className="metric"><strong>{typeof value === "number" ? value.toLocaleString() : value}</strong><span>{label}</span></article>; }

function Batches() {
  const { apiUrl, selectedKey } = useVersioning();
  const [page, setPage] = useState(1); const query = useQuery({ queryKey: ["batches", selectedKey, page], queryFn: () => getJson<Page<Batch>>(apiUrl("/api/v1/batches", { page })) });
  const columns = useMemo<ColumnDef<Batch>[]>(() => [{ header: "Ordinal", accessorKey: "ordinal" }, { header: "Batch ID", cell: ({ row }) => <code>{row.original.batch_id}</code> }, { header: "Status", cell: ({ row }) => <Status value={row.original.status} /> }, { header: "Families", accessorFn: row => row.family_ids.length }, { header: "Required identities", accessorKey: "required_identities" }, { header: "Prior candidates", accessorKey: "required_candidates" }], []);
  return <><header className="page-head"><div><Eyebrow>Deterministic manifest</Eyebrow><h1>Research batches</h1><p>Bounded execution units generated from the operating-family schedule.</p></div></header>{query.isPending ? <Loading /> : query.error ? <ErrorState error={query.error} /> : <><DataTable data={query.data.data.items} columns={columns} /><Pager page={query.data.data} setPage={setPage} /></>}</>;
}

function Audit() {
  const { apiUrl, selectedKey } = useVersioning();
  const query = useQuery({ queryKey: ["versions", selectedKey], queryFn: () => getJson<Versions>(apiUrl("/api/v1/versions")) });
  if (query.isPending) return <Loading />; if (query.error) return <ErrorState error={query.error} />; const catalog = query.data.data;
  return <><header className="page-head"><div><Eyebrow>Exact repository truth</Eyebrow><h1>Versions and receipts</h1><p>Every view resolves one compatible, hash-verified source run, family partition, and graph release.</p></div></header><section className="panel"><Eyebrow>Active snapshot</Eyebrow><h2>Current provenance</h2><dl>{Object.entries(query.data.provenance).map(([key, value]) => <><dt key={`${key}-dt`}>{key.replaceAll("_", " ")}</dt><dd key={`${key}-dd`}><code>{value}</code></dd></>)}</dl></section><section className="three-column"><VersionCard title="Universe runs" items={catalog.source_runs} /><VersionCard title="Partitions" items={catalog.partitions} /><VersionCard title="Graph releases" items={catalog.graph_releases} /></section><section className="callout"><div><Eyebrow>Read-only contract</Eyebrow><h2>Inspect, never mutate.</h2></div><p>The product reads only committed artifact paths, exposes sanitized receipts from a fixed allowlist, and rejects incompatible or hash-mismatched versions.</p></section></>;
}

function VersionCard({ title, items }: { title: string; items: Array<Record<string, unknown>> }) { return <article className="panel"><Eyebrow>Version catalog</Eyebrow><h2>{title}</h2>{items.map((item, index) => <JsonDetails key={index} label={String(item.run_id ?? item.partition_id ?? item.release_id ?? `Version ${index + 1}`)} value={item} />)}</article>; }
function NotFound() { const navigate = useNavigate(); const { versionedPath } = useVersioning(); return <section className="hero"><Eyebrow>Not found</Eyebrow><h1>This view does not exist.</h1><p className="lede">The research artifacts were not changed.</p><button className="primary" onClick={() => navigate(versionedPath("/"))}>Return to overview</button></section>; }
