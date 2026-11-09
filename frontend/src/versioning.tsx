import { useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { getJson, params } from "./api";
import type { Provenance, Versions, VersionTuple } from "./types";

const VERSION_KEYS = ["source_run_id", "partition_id", "graph_version_id"] as const;

function keyFor(tuple: VersionTuple | Provenance) {
  return `${tuple.source_run_id}|${tuple.partition_id}|${tuple.graph_version_id}`;
}

interface VersioningValue {
  catalog?: Versions;
  catalogError: Error | null;
  isCatalogPending: boolean;
  selected?: Provenance;
  selectedKey: string;
  apiUrl: (path: string, values?: Record<string, string | number | boolean | null | undefined>) => string;
  versionedPath: (path: string, values?: Record<string, string | number | boolean | null | undefined>) => string;
  selectVersion: (key: string) => void;
}

const VersioningContext = createContext<VersioningValue | null>(null);

export function VersionProvider({ children }: { children: ReactNode }) {
  const [search, setSearch] = useSearchParams();
  const catalogQuery = useQuery({
    queryKey: ["version-catalog"],
    queryFn: () => getJson<Versions>("/api/v1/versions"),
    staleTime: Number.POSITIVE_INFINITY,
  });
  const explicit = useMemo(() => {
    const values = Object.fromEntries(VERSION_KEYS.map(key => [key, search.get(key)]));
    return VERSION_KEYS.every(key => values[key]) ? values as unknown as VersionTuple : undefined;
  }, [search]);
  const catalog = catalogQuery.data?.data;
  const selected = explicit
    ? catalog?.compatible_snapshots.find(item => keyFor(item) === keyFor(explicit))
    : catalog?.current;
  const selectedKey = explicit ? keyFor(explicit) : "latest";
  const versionValues = explicit ?? {};
  const buildUrl = useCallback(
    (path: string, values: Record<string, string | number | boolean | null | undefined> = {}) =>
      `${path}${params({ ...values, ...versionValues })}`,
    [explicit?.source_run_id, explicit?.partition_id, explicit?.graph_version_id],
  );
  const selectVersion = useCallback((key: string) => {
    setSearch(current => {
      const next = new URLSearchParams(current);
      VERSION_KEYS.forEach(name => next.delete(name));
      if (key !== "latest") {
        const tuple = catalog?.compatible_snapshots.find(item => keyFor(item) === key);
        if (tuple) VERSION_KEYS.forEach(name => next.set(name, tuple[name]));
      }
      return next;
    }, { replace: true });
  }, [catalog, setSearch]);
  return <VersioningContext.Provider value={{
    catalog,
    catalogError: catalogQuery.error,
    isCatalogPending: catalogQuery.isPending,
    selected,
    selectedKey,
    apiUrl: buildUrl,
    versionedPath: buildUrl,
    selectVersion,
  }}>{children}</VersioningContext.Provider>;
}

export function useVersioning() {
  const value = useContext(VersioningContext);
  if (!value) throw new Error("useVersioning must be used inside VersionProvider");
  return value;
}

export { keyFor as versionKeyFor };
