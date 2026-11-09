# Anchored research pilot — 2026-11-09

This collaboration-agent pilot produced **six provisional operating-boundary
hypotheses**, covering 82 required identities and one prior candidate. Independent
review corrected two scope errors and approved **provisional research publication
only**. It added **zero accepted canonical markets**. Nine identities and 16 research
gaps remain unresolved; no Target eligibility, investment scoring, or activation
occurred.

`output.json.gz` is the corrected output. `review.json` records the final verdict;
`researcher-notes.json` is preserved unchanged, including its earlier pending-review
status. `history/` retains the two superseded output versions and original notes.

`inputs.tar.xz` contains both exact CLI context snapshots and the two immutable
family preparations, using relative regular-file members. Tar metadata is fixed
(uid/gid/mtime zero, mode 0644); XZ uses preset 6. Output gzip timestamps are zero.
`provenance.json` supplies SHA-256 hashes for archive members and every bundle file
except itself.

The operator approval and two CLI receipts are historical records, not successful
research provenance. The first CLI attempt retains a stale `in_progress` receipt: its process session
was unavailable, and no active process is asserted. Model invocation remains unknown; the second exited 1 without output or usage and likewise retains
unknown invocation status. The actual research and independent review came from
collaboration agents, not a successful CLI run, OpenRouter, or the simulation ledger.
No metered-provider invoice or calibrated research confidence is claimed.

## Replay

Use the repository source/schema versions recorded in `provenance.json`, with its
Python dependencies installed. From the repository root:

```bash
pilot=data/research_pilots/anchored-20261109
replay_dir=$(mktemp -d)
tar -xf "$pilot/inputs.tar.xz" -C "$replay_dir"
gzip -dc "$pilot/output.json.gz" > "$replay_dir/output.json"
PYTHONPATH=src python3 -m turbo.cli batch-output-validate \
  "$replay_dir/output.json" \
  approved-real-anchored-10-333415-20261109 \
  invocation:ffffffffffffffffffffffff \
  "$replay_dir/preparations/family-preparation:78408ce718cfa2d94c77e0ec" \
  "$replay_dir/preparations/family-preparation:ef0c5fb162a6fd1c9c350f99"
```

This checks exact frozen inputs and structural output integrity. It does not rerun a
model or establish canonical-market acceptance. Source changes intentionally require
the original checkout for preparation replay.
