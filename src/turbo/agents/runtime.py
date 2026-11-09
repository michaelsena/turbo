from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from turbo.agents.boundary_harness import canonical_sha256


@dataclass(frozen=True)
class InvocationResult:
    output: dict[str, Any]
    receipt: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def runtime_envelope(
    *,
    role_id: str,
    invocation_id: str,
    pack: dict[str, Any],
    specialist_outputs: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "expected_role_id": role_id,
        "expected_invocation_id": invocation_id,
        "expected_family_id": pack["metadata"]["family_id"],
        "expected_input_pack_sha256": pack["metadata"]["pack_sha256"],
        "frozen_evidence_pack": pack,
    }
    if specialist_outputs is not None:
        envelope["validated_specialist_outputs"] = specialist_outputs
        envelope["expected_specialist_output_sha256"] = [
            canonical_sha256(item) for item in specialist_outputs
        ]
    return envelope


def runtime_prompt(
    base_prompt: str,
    *,
    role_id: str,
    invocation_id: str,
    pack: dict[str, Any],
    specialist_outputs: list[dict[str, Any]] | None,
) -> str:
    envelope = runtime_envelope(
        role_id=role_id,
        invocation_id=invocation_id,
        pack=pack,
        specialist_outputs=specialist_outputs,
    )
    return base_prompt.rstrip() + "\n\n# Runtime envelope\n\n" + json.dumps(
        envelope, sort_keys=True, separators=(",", ":")
    )
