# ADR 0026: Archive-backed workload publication bindings

Status: Accepted for read-only workload reporting.

## Context

The approved lease activation publishes canonical config, closure and graph artifacts
on disk while preserving accepted workflow records in a hash-bound replay ZIP. The
version 1 workload publication manifest requires all bound records on disk, leaving
current activation coverage incomplete despite those records already being public.

## Decision

Add publication manifest version 2 with explicit virtual artifact references:
`archived_files[name] = {archive_path, member, sha256}`. Keep `files` as the exact
on-disk byte bindings, including the archive itself. Resolve bounded ZIP members in
memory and feed their strict JSON into the unchanged approval and closure validator.
Do not extract members, follow restore paths, duplicate public workflow data, infer
provenance from an archive name, or relax complete current-activation coverage.

Reject ambiguous physical/virtual names, repeated member bindings, duplicate or
unsafe ZIP paths, symlinks and special entries. Bound compressed, expanded and member
sizes and entry counts. Hash the same archive bytes used by the ZIP reader. Bind
selected members independently by their expanded byte SHA256. Version 1 remains
supported; archive references require version 2.

## Consequences

The current six-market report can include both mining and lease publications without
making a model call. Counts describe completed review obligations and retain all
research gaps; they establish neither acquisition eligibility nor investment scores.
The report continues to verify artifact bindings rather than replay fresh research
or authenticate external authors. Malformed transport or incomplete coverage fails
closed. Other archive formats and general restoration remain outside this change.
