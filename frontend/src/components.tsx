import type { ReactNode } from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { NavLink, Outlet } from "react-router-dom";
import type { Page, Provenance } from "./types";

export function Layout({ provenance }: { provenance?: Provenance }) {
  return <>
    <a className="skip-link" href="#content">Skip to content</a>
    <header className="site-header">
      <NavLink className="wordmark" to="/" aria-label="Turbo overview"><span className="mark">T</span>Turbo</NavLink>
      <nav aria-label="Primary navigation">
        <NavLink to="/universe">Universe</NavLink>
        <NavLink to="/families">Families</NavLink>
        <NavLink to="/batches">Batches</NavLink>
        <NavLink to="/audit">Audit</NavLink>
        <a href="/docs">API</a>
      </nav>
    </header>
    <main id="content" className="shell"><Outlet /></main>
    {provenance && <footer className="provenance-bar" aria-label="Current data version">
      <ProvenanceItem label="As of" value={provenance.as_of_utc} />
      <ProvenanceItem label="Source run" value={provenance.source_run_id} code />
      <ProvenanceItem label="Partition" value={provenance.partition_id} code />
      <ProvenanceItem label="Graph" value={provenance.graph_version_id} code />
    </footer>}
  </>;
}

function ProvenanceItem({ label, value, code = false }: { label: string; value: string; code?: boolean }) {
  return <div><span>{label}</span>{code ? <code>{value}</code> : <strong>{value}</strong>}</div>;
}

export function Eyebrow({ children }: { children: ReactNode }) { return <p className="eyebrow">{children}</p>; }
export function Status({ value }: { value: string }) { return <span className={`status status-${value.replaceAll("_", "-")}`}>{value.replaceAll("_", " ")}</span>; }

export function Loading() { return <div className="state"><span className="spinner" />Verifying repository snapshot…</div>; }
export function ErrorState({ error }: { error: Error }) { return <div className="state error"><strong>Unable to load this view.</strong><span>{error.message}</span></div>; }

export function DataTable<T>({ data, columns, empty = "No records match this view." }: { data: T[]; columns: ColumnDef<T>[]; empty?: string }) {
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });
  return <div className="table-wrap"><table>
    <thead>{table.getHeaderGroups().map(group => <tr key={group.id}>{group.headers.map(header => <th key={header.id}>{header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr>)}</thead>
    <tbody>{table.getRowModel().rows.map(row => <tr key={row.id}>{row.getVisibleCells().map(cell => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}
    {!data.length && <tr><td className="empty" colSpan={columns.length}>{empty}</td></tr>}</tbody>
  </table></div>;
}

export function Pager<T>({ page, setPage }: { page: Page<T>; setPage: (value: number) => void }) {
  if (page.pages <= 1) return null;
  return <nav className="pager" aria-label="Pagination">
    <button disabled={page.page <= 1} onClick={() => setPage(page.page - 1)}>Previous</button>
    <span>Page {page.page} of {page.pages}</span>
    <button disabled={page.page >= page.pages} onClick={() => setPage(page.page + 1)}>Next</button>
  </nav>;
}

export function JsonDetails({ label, value }: { label: string; value: unknown }) {
  return <details><summary>{label}<span>Inspect JSON</span></summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
}
