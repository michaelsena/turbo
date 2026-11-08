import unittest

from turbo.universe.graph import project_graph, validate_event


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
    }
    value.update(overrides)
    return value


class GraphContractTest(unittest.TestCase):
    def test_independent_review_is_required(self) -> None:
        candidate = event("event-1", "2026-11-08T12:00:00Z")
        candidate["review"]["independent_reviewer"] = "agent-a"
        self.assertIn(
            "proposer and independent_reviewer must differ",
            validate_event(candidate),
        )

    def test_projection_is_order_independent_and_supersession_is_append_only(self) -> None:
        first = event("event-1", "2026-11-08T12:00:00Z")
        correction = event(
            "event-2",
            "2026-11-08T13:00:00Z",
            supersedes=["event-1"],
            relationship_type="partial_overlap",
        )
        inputs = {
            "as_of": "2026-11-08T14:00:00Z",
            "source_hashes": {"naics": "abc"},
            "config_hash": "config",
            "code_hash": "code",
        }
        forward = project_graph([first, correction], **inputs)
        reverse = project_graph([correction, first], **inputs)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward["active_event_ids"], ["event-2"])
        self.assertEqual(forward["superseded_event_ids"], ["event-1"])

    def test_create_market_requires_complete_version(self) -> None:
        candidate = event(
            "event-create",
            "2026-11-08T12:00:00Z",
            event_type="create_market",
        )
        self.assertIn("create_market requires market_version", validate_event(candidate))


if __name__ == "__main__":
    unittest.main()
