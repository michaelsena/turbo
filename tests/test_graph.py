import unittest

from turbo.universe.graph import (
    market_id_from_creation,
    market_version_id,
    project_graph,
    validate_event,
)


def identity() -> dict[str, dict[str, object]]:
    return {
        dimension: {"result": "same", "confidence": 0.8}
        for dimension in (
            "buyer",
            "job",
            "delivery",
            "workforce",
            "economics_risk",
            "acquisition_universe",
            "ambient_ai_workflow",
        )
    }


def event(event_id: str, recorded_at: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "event_id": event_id,
        "event_type": "map",
        "decision": "accepted",
        "recorded_at": recorded_at,
        "input_source_record_ids": ["naics:123456"],
        "input_market_ids": [],
        "input_candidate_market_ids": [],
        "output_market_ids": ["market:01"],
        "relationship_type": "industry_containing_market",
        "operating_identity": identity(),
        "supporting_record_ids": [],
        "counterevidence_record_ids": [],
        "alternatives_considered": [],
        "review": {
            "proposer": "agent-a",
            "independent_reviewer": "agent-b",
            "result": "accepted",
        },
        "supersedes": [],
        "supersedes_market_version_ids": [],
    }
    value.update(overrides)
    return value


def market_version(event_id: str, market_id: str, name: str = "Test market") -> dict[str, object]:
    return {
        "market_version_id": market_version_id(event_id, market_id),
        "market_id": market_id,
        "canonical_name": name,
        "definition": "A bounded test market.",
        "boundary": "Included test operations; excludes unrelated work.",
        "buyer": "Test buyer",
        "job_to_be_done": "Complete test work",
        "delivery_model": "Service delivery",
        "workforce_model": "Skilled workers",
        "economics_risk": "Contract revenue with execution risk",
        "acquisition_universe": "U.S. test operators",
        "ambient_ai_workflow": "Capture and route test context",
        "parent_market_id": None,
        "aliases": [],
        "explicit_exclusions": [],
        "source_record_ids": [],
        "mapping_event_ids": [],
        "candidate_market_ids": [],
        "evidence_by_dimension": {dimension: "assumption" for dimension in identity()},
        "confidence_by_dimension": {dimension: 0.8 for dimension in identity()},
    }


def creation(event_id: str, recorded_at: str) -> dict[str, object]:
    market_id = market_id_from_creation(event_id)
    return event(
        event_id,
        recorded_at,
        event_type="create_market",
        input_source_record_ids=[],
        output_market_ids=[market_id],
        relationship_type=None,
        market_version=market_version(event_id, market_id),
    )


class GraphContractTest(unittest.TestCase):
    def test_independent_review_is_required(self) -> None:
        candidate = event("event-1", "2026-11-08T12:00:00Z")
        candidate["review"]["independent_reviewer"] = "agent-a"
        self.assertIn(
            "proposer and independent_reviewer must differ",
            validate_event(candidate),
        )

    def test_projection_is_order_independent_and_supersession_is_append_only(self) -> None:
        create = creation("event-create", "2026-11-08T11:00:00Z")
        market_id = create["output_market_ids"][0]
        first = event("event-1", "2026-11-08T12:00:00Z", output_market_ids=[market_id])
        correction = event(
            "event-2",
            "2026-11-08T13:00:00Z",
            supersedes=["event-1"],
            relationship_type="partial_overlap",
            output_market_ids=[market_id],
        )
        inputs = {
            "as_of": "2026-11-08T14:00:00Z",
            "known_source_record_ids": {"naics:123456"},
            "source_hashes": {"naics": "abc"},
            "config_hash": "config",
            "code_hash": "code",
        }
        forward = project_graph([create, first, correction], **inputs)
        reverse = project_graph([correction, first, create], **inputs)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward["active_event_ids"], ["event-create", "event-2"])
        self.assertEqual(forward["superseded_event_ids"], ["event-1"])

    def test_create_market_requires_complete_version(self) -> None:
        candidate = event(
            "event-create",
            "2026-11-08T12:00:00Z",
            event_type="create_market",
            input_source_record_ids=[],
            output_market_ids=[market_id_from_creation("event-create")],
        )
        self.assertIn("market version must be an object", validate_event(candidate))

    def test_event_cardinality_and_supersession_invariants(self) -> None:
        invalid_map = event(
            "map-empty",
            "2026-11-08T12:00:00Z",
            input_source_record_ids=[],
            relationship_type=None,
        )
        self.assertIn("map requires at least one input source record", validate_event(invalid_map))
        self.assertIn("map requires relationship_type", validate_event(invalid_map))
        invalid_split = event(
            "split-empty",
            "2026-11-08T12:00:00Z",
            event_type="split",
            input_source_record_ids=[],
            input_market_ids=[],
            output_market_ids=[],
        )
        self.assertIn(
            "split requires exactly one input market and at least two outputs",
            validate_event(invalid_split),
        )
        self_superseding = event(
            "event-self",
            "2026-11-08T12:00:00Z",
            supersedes=["event-self"],
        )
        self.assertIn("event cannot supersede itself", validate_event(self_superseding))

    def test_projection_rejects_orphan_map_and_naive_timestamp(self) -> None:
        create = creation("event-create", "2026-11-08T11:00:00Z")
        orphan = event("event-map", "2026-11-08T12:00:00Z")
        with self.assertRaisesRegex(ValueError, "unknown market"):
            project_graph(
                [create, orphan],
                as_of="2026-11-08T14:00:00Z",
                known_source_record_ids={"naics:123456"},
            )
        naive = event("event-naive", "2026-11-08T12:00:00")
        self.assertTrue(any("timezone-aware" in error for error in validate_event(naive)))

    def test_invalid_future_event_does_not_block_historical_projection(self) -> None:
        create = creation("event-create", "2026-11-08T11:00:00Z")
        future_invalid = event(
            "future-split",
            "2026-11-09T12:00:00Z",
            event_type="split",
            input_source_record_ids=[],
            input_market_ids=[],
            output_market_ids=[],
        )
        projection = project_graph(
            [future_invalid, create],
            as_of="2026-11-08T14:00:00Z",
            known_source_record_ids=set(),
        )
        self.assertEqual(len(projection["markets"]), 1)

        future_invalid_reference = creation(
            "future-create",
            "2026-11-09T13:00:00Z",
        )
        future_invalid_reference["market_version"]["source_record_ids"] = [
            "future-unknown-source"
        ]
        projection = project_graph(
            [future_invalid_reference, create],
            as_of="2026-11-08T14:00:00Z",
            known_source_record_ids=set(),
        )
        self.assertEqual(len(projection["markets"]), 1)

    def test_split_retires_predecessor_and_preserves_lineage(self) -> None:
        create = creation("event-create", "2026-11-08T11:00:00Z")
        predecessor = create["output_market_ids"][0]
        split_id = "event-split"
        successors = [market_id_from_creation(split_id, index) for index in range(2)]
        split = event(
            split_id,
            "2026-11-08T12:00:00Z",
            event_type="split",
            input_source_record_ids=[],
            input_market_ids=[predecessor],
            output_market_ids=successors,
            relationship_type=None,
            market_versions=[
                market_version(split_id, market_id, f"Successor {index}")
                for index, market_id in enumerate(successors, 1)
            ],
        )
        projection = project_graph(
            [split, create],
            as_of="2026-11-08T14:00:00Z",
            known_source_record_ids=set(),
        )
        self.assertEqual(
            [market["market_id"] for market in projection["markets"]],
            sorted(successors),
        )
        self.assertEqual(projection["retired_market_ids"], [predecessor])
        self.assertEqual([item["event_id"] for item in projection["lineage"]], [split_id])

    def test_retired_market_versions_retain_referential_integrity(self) -> None:
        def retired_projection(
            suffix: str,
            mutate: object,
        ) -> None:
            create = creation(f"create-{suffix}", "2026-11-08T11:00:00Z")
            mutate(create["market_version"])
            predecessor = create["output_market_ids"][0]
            split_id = f"split-{suffix}"
            successors = [market_id_from_creation(split_id, index) for index in range(2)]
            split = event(
                split_id,
                "2026-11-08T12:00:00Z",
                event_type="split",
                input_source_record_ids=[],
                input_market_ids=[predecessor],
                output_market_ids=successors,
                relationship_type=None,
                market_versions=[
                    market_version(split_id, market_id, f"Successor {index}")
                    for index, market_id in enumerate(successors, 1)
                ],
            )
            project_graph(
                [create, split],
                as_of="2026-11-08T14:00:00Z",
                known_source_record_ids=set(),
                known_candidate_market_ids=set(),
            )

        cases = (
            (
                "source",
                lambda version: version["source_record_ids"].append("missing-source"),
                "unknown source records",
            ),
            (
                "candidate",
                lambda version: version["candidate_market_ids"].append(
                    "candidate-market:missing"
                ),
                "unknown candidate markets",
            ),
            (
                "mapping",
                lambda version: version["mapping_event_ids"].append("missing-map"),
                "invalid mapping event",
            ),
            (
                "parent",
                lambda version: version.__setitem__(
                    "parent_market_id", "market:000000000000000000000000"
                ),
                "unknown or future parent",
            ),
        )
        for suffix, mutate, message in cases:
            with self.subTest(reference=suffix):
                with self.assertRaisesRegex(ValueError, message):
                    retired_projection(suffix, mutate)

    def test_replacement_split_does_not_apply_superseded_retirement(self) -> None:
        create = creation("event-create", "2026-11-08T11:00:00Z")
        predecessor = create["output_market_ids"][0]

        def split(event_id: str, recorded_at: str, supersedes: list[str]) -> dict[str, object]:
            successors = [market_id_from_creation(event_id, index) for index in range(2)]
            return event(
                event_id,
                recorded_at,
                event_type="split",
                input_source_record_ids=[],
                input_market_ids=[predecessor],
                output_market_ids=successors,
                relationship_type=None,
                supersedes=supersedes,
                market_versions=[
                    market_version(event_id, market_id, f"{event_id} successor {index}")
                    for index, market_id in enumerate(successors, 1)
                ],
            )

        old = split("split-old", "2026-11-08T12:00:00Z", [])
        replacement = split("split-new", "2026-11-08T13:00:00Z", ["split-old"])
        projection = project_graph(
            [old, replacement, create],
            as_of="2026-11-08T14:00:00Z",
            known_source_record_ids=set(),
        )
        expected = sorted(replacement["output_market_ids"])
        self.assertEqual([item["market_id"] for item in projection["markets"]], expected)
        self.assertEqual([item["event_id"] for item in projection["lineage"]], ["split-new"])

    def test_supersede_decision_withdraws_creation(self) -> None:
        create = creation("event-create", "2026-11-08T11:00:00Z")
        withdrawal = event(
            "withdraw-create",
            "2026-11-08T12:00:00Z",
            event_type="supersede_decision",
            input_source_record_ids=[],
            output_market_ids=[],
            relationship_type=None,
            supersedes=["event-create"],
        )
        projection = project_graph(
            [create, withdrawal],
            as_of="2026-11-08T14:00:00Z",
            known_source_record_ids=set(),
        )
        self.assertEqual(projection["markets"], [])

    def test_superseded_withdrawal_restores_original_event(self) -> None:
        create = creation("event-create", "2026-11-08T11:00:00Z")
        withdrawal = event(
            "withdraw-create",
            "2026-11-08T12:00:00Z",
            event_type="supersede_decision",
            input_source_record_ids=[],
            output_market_ids=[],
            relationship_type=None,
            supersedes=["event-create"],
        )
        correction = event(
            "correct-withdrawal",
            "2026-11-08T13:00:00Z",
            event_type="supersede_decision",
            input_source_record_ids=[],
            output_market_ids=[],
            relationship_type=None,
            supersedes=["withdraw-create"],
        )
        projection = project_graph(
            [withdrawal, create, correction],
            as_of="2026-11-08T14:00:00Z",
            known_source_record_ids=set(),
        )
        self.assertEqual(len(projection["markets"]), 1)
        self.assertIn("event-create", projection["active_event_ids"])
        self.assertIn("withdraw-create", projection["superseded_event_ids"])

    def test_rename_supersedes_market_version_not_creation_event(self) -> None:
        create = creation("event-create", "2026-11-08T11:00:00Z")
        market_id = create["output_market_ids"][0]
        rename = event(
            "rename-market",
            "2026-11-08T12:00:00Z",
            event_type="rename",
            input_source_record_ids=[],
            input_market_ids=[market_id],
            output_market_ids=[market_id],
            relationship_type=None,
            supersedes_market_version_ids=[create["market_version"]["market_version_id"]],
            market_version=market_version("rename-market", market_id, "Renamed market"),
        )
        projection = project_graph(
            [rename, create],
            as_of="2026-11-08T14:00:00Z",
            known_source_record_ids=set(),
        )
        self.assertEqual(projection["markets"][0]["canonical_name"], "Renamed market")
        self.assertIn("event-create", projection["active_event_ids"])

    def test_mapping_to_retired_market_is_historical_not_effective(self) -> None:
        create = creation("event-create", "2026-11-08T11:00:00Z")
        predecessor = create["output_market_ids"][0]
        mapping = event(
            "event-map",
            "2026-11-08T11:30:00Z",
            output_market_ids=[predecessor],
        )
        split_id = "event-split"
        successors = [market_id_from_creation(split_id, index) for index in range(2)]
        split = event(
            split_id,
            "2026-11-08T12:00:00Z",
            event_type="split",
            input_source_record_ids=[],
            input_market_ids=[predecessor],
            output_market_ids=successors,
            relationship_type=None,
            market_versions=[
                market_version(split_id, market_id, f"Successor {index}")
                for index, market_id in enumerate(successors, 1)
            ],
        )
        projection = project_graph(
            [split, mapping, create],
            as_of="2026-11-08T14:00:00Z",
            known_source_record_ids={"naics:123456"},
        )
        self.assertEqual(projection["mappings"], [])
        self.assertEqual([item["event_id"] for item in projection["retired_mappings"]], ["event-map"])

    def test_market_version_mapping_lineage_must_match_active_earlier_map(self) -> None:
        create = creation("event-create", "2026-11-08T11:00:00Z")
        market_id = create["output_market_ids"][0]
        mapping = event(
            "event-map",
            "2026-11-08T12:00:00Z",
            output_market_ids=[market_id],
        )
        revised_version = market_version("rename-market", market_id, "Mapped market")
        revised_version["source_record_ids"] = ["naics:123456"]
        revised_version["mapping_event_ids"] = ["event-map"]
        rename = event(
            "rename-market",
            "2026-11-08T13:00:00Z",
            event_type="rename",
            input_source_record_ids=[],
            input_market_ids=[market_id],
            output_market_ids=[market_id],
            relationship_type=None,
            supersedes_market_version_ids=[create["market_version"]["market_version_id"]],
            market_version=revised_version,
        )
        projection = project_graph(
            [rename, mapping, create],
            as_of="2026-11-08T14:00:00Z",
            known_source_record_ids={"naics:123456"},
        )
        self.assertEqual(projection["markets"][0]["mapping_event_ids"], ["event-map"])

        wrong_target = creation("other-create", "2026-11-08T11:15:00Z")
        mapping["output_market_ids"] = [wrong_target["output_market_ids"][0]]
        with self.assertRaisesRegex(ValueError, "invalid mapping event"):
            project_graph(
                [rename, mapping, wrong_target, create],
                as_of="2026-11-08T14:00:00Z",
                known_source_record_ids={"naics:123456"},
            )


if __name__ == "__main__":
    unittest.main()
