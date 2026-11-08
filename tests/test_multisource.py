import unittest

from turbo.universe.multisource import (
    parse_napcs,
    parse_prior,
    parse_trilateral_products,
    prior_records,
    reconcile,
    semantic_conflicts,
    semantic_flags,
)


class MultiSourceUniverseTest(unittest.TestCase):
    def test_all_initial_lists_are_loaded(self) -> None:
        records = parse_napcs()
        self.assertEqual(len({record.source_code for record in records}), 7_236)
        self.assertEqual(
            len(
                {
                    record.source_code
                    for record in records
                    if record.record_kind == "relationship_product"
                }
            ),
            945,
        )
        self.assertEqual(
            sum(record.record_kind == "relationship_product" for record in records),
            12_247,
        )
        self.assertEqual(
            len(
                {
                    record.source_code
                    for record in records
                    if record.record_kind == "concordance_product"
                }
            ),
            1,
        )
        self.assertEqual(
            len({record.source_code for record in parse_trilateral_products()}),
            1_072,
        )
        self.assertEqual(len(parse_prior()), 978)

    def test_reconciliation_preserves_every_source_row(self) -> None:
        result = reconcile()
        counts = result["source_counts"]
        self.assertEqual(
            len(result["mappings"]),
            counts["normalized_source_identities"],
        )
        self.assertEqual(len(result["mappings"]), counts["reconciliation_mappings"])
        mapping_identity_ids = [
            item["normalized_identity_id"] for item in result["mappings"]
        ]
        self.assertEqual(len(mapping_identity_ids), len(set(mapping_identity_ids)))
        self.assertEqual(
            set(mapping_identity_ids),
            {item["identity_id"] for item in result["source_identities"]},
        )
        self.assertTrue(
            all(
                item["supporting_source_record_ids"]
                for item in result["mappings"]
            )
        )
        self.assertTrue(
            all("source_record_id" not in item for item in result["mappings"])
        )
        self.assertEqual(len(result["candidate_markets"]), counts["prior_candidate_markets"])
        self.assertEqual(
            len(result["source_records"]),
            counts["naics_nodes"]
            + counts["napcs_source_records"]
            + counts["napcs_trilateral_source_records"]
            + counts["prior_seed_records"],
        )
        self.assertEqual(len(result["source_records"]), counts["source_records"])
        self.assertEqual(sum(result["mapping_counts"].values()), len(result["mappings"]))
        self.assertNotIn("accepted_exact_label", result["mapping_counts"])
        self.assertTrue(all(len(item["candidates"]) <= 5 for item in result["mappings"]))
        self.assertTrue(
            all(
                "component_signals" in candidate
                for item in result["mappings"]
                for candidate in item["candidates"]
            )
        )

    def test_relationship_only_products_preserve_each_exact_row_locator(self) -> None:
        records = [
            record
            for record in parse_napcs()
            if record.record_kind == "relationship_product"
        ]
        self.assertEqual(len({record.record_id for record in records}), len(records))
        self.assertEqual(len({record.locator for record in records}), len(records))
        self.assertTrue(all(":row:" in record.locator for record in records))
        self.assertTrue(all("TYPOP=" in record.locator for record in records))

    def test_candidate_ids_survive_input_reordering_and_duplicate_rows(self) -> None:
        first = {
            item.name: item.candidate_market_id
            for item in prior_records(["Alpha Services", "Beta Services", "Alpha Services"])
        }
        second = {
            item.name: item.candidate_market_id
            for item in prior_records(["Beta Services", "Alpha Services", "Alpha Services"])
        }
        self.assertEqual(first, second)
        self.assertEqual(len(set(first.values())), 2)

    def test_source_records_preserve_snapshot_and_relationship_lineage(self) -> None:
        result = reconcile()
        records = {item["record_id"]: item for item in result["source_records"]}
        naics = records["source-row:census-naics-2022:541330"]
        self.assertEqual(naics["snapshot_id"], "census-naics-2022")
        self.assertEqual(naics["hierarchy_path"][-1], "identity:naics:541330")
        self.assertEqual(naics["parent_ids"], ["identity:naics:54133"])
        napcs = next(
            item
            for item in result["source_records"]
            if item["source"].startswith("napcs") and item["source_relationships"]
        )
        self.assertTrue(
            all(
                edge["relationship_type"] == "collection_to_trilateral"
                for edge in napcs["source_relationships"]
            )
        )
        identity_ids = {item["identity_id"] for item in result["source_identities"]}
        self.assertTrue(
            all(
                edge["target_identity_id"] in identity_ids
                for item in result["source_records"]
                for edge in item["source_relationships"]
            )
        )

    def test_source_rows_and_normalized_identities_are_distinct(self) -> None:
        result = reconcile()
        source_ids = {item["record_id"] for item in result["source_records"]}
        identity_ids = {item["identity_id"] for item in result["source_identities"]}
        self.assertFalse(source_ids & identity_ids)
        self.assertTrue(all(item.startswith("identity:") for item in identity_ids))

    def test_conflicting_trilateral_labels_preserve_snapshot_lineage(self) -> None:
        result = reconcile()
        identities = {
            item["identity_id"]: item for item in result["source_identities"]
        }
        records = {
            item["record_id"]: item for item in result["source_records"]
        }
        expected = {
            "identity:napcs-trilateral:21101020301": {
                "Household electric lamps, including parts and accessories",
                "Household-type portable lighting fixtures, including parts and accessories",
            },
            "identity:napcs-trilateral:51501010104": {
                "Paper industry machinery",
                "Printing machinery and equipment",
            },
        }
        for identity_id, labels in expected.items():
            identity = identities[identity_id]
            self.assertTrue(identity["label_conflict"])
            self.assertEqual(set(identity["labels"]), labels)
            observations = [records[record_id] for record_id in identity["source_record_ids"]]
            self.assertGreaterEqual(
                len({record["snapshot_id"] for record in observations}),
                2,
            )
            self.assertEqual(
                len({(record["snapshot_id"], record["locator"]) for record in observations}),
                len(observations),
            )
            mapping = next(
                item
                for item in result["mappings"]
                if item["normalized_identity_id"] == identity_id
            )
            self.assertTrue(mapping["raw_label_conflict"])
            self.assertTrue(mapping["analysis_label_conflict"])
            self.assertEqual(set(mapping["raw_labels"]), labels)
            self.assertEqual(set(mapping["analysis_labels"]), labels)
            self.assertEqual(
                set(mapping["supporting_source_record_ids"]),
                set(identity["source_record_ids"]),
            )

        candidate_changing_conflict = next(
            item
            for item in result["mappings"]
            if item["normalized_identity_id"]
            == "identity:napcs-trilateral:51501010104"
        )
        self.assertTrue(candidate_changing_conflict["label_conflict_alters_candidates"])
        self.assertEqual(
            candidate_changing_conflict["status"],
            "ambiguous_or_semantically_conflicted_review",
        )
        self.assertEqual(
            candidate_changing_conflict["reason"],
            "official_label_conflict_changes_candidate_ordering",
        )
        for candidate in candidate_changing_conflict["candidates"]:
            evaluations = candidate["component_signals"]["label_evaluations"]
            self.assertEqual(
                {evaluation["analysis_label"] for evaluation in evaluations},
                expected["identity:napcs-trilateral:51501010104"],
            )

    def test_naics_trilateral_marker_is_not_a_retrieval_token(self) -> None:
        result = reconcile()
        record = next(
            item
            for item in result["source_records"]
            if item["record_id"] == "source-row:census-naics-2022:54162"
        )
        self.assertEqual(record["raw_label"], "Environmental Consulting ServicesT")
        self.assertEqual(record["source_indicator"], "trilateral")
        self.assertEqual(record["normalized_label"], "environmental consulting services")
        mapping = next(
            item
            for item in result["mappings"]
            if item["normalized_identity_id"] == "identity:naics:54162"
        )
        self.assertEqual(mapping["analysis_labels"], ["Environmental Consulting Services"])
        self.assertIn(record["record_id"], mapping["supporting_source_record_ids"])
        first_signals = mapping["candidates"][0]["component_signals"]
        source_tokens = set(first_signals["matched_tokens"]) | set(
            first_signals["source_only_tokens"]
        )
        self.assertEqual(source_tokens, {"consulting", "environmental", "service"})

    def test_scope_semantics_are_not_erased(self) -> None:
        self.assertIn(
            "candidate_contains_source_excluded_scope",
            semantic_conflicts(
                "Surveying and Mapping (except Geophysical) Services",
                "Geophysical surveying",
            ),
        )
        self.assertIn(
            "candidate_contains_source_excluded_scope",
            semantic_conflicts(
                "Project management services, except construction",
                "Construction project management",
            ),
        )
        self.assertIn(
            "candidate_contains_source_excluded_scope",
            semantic_conflicts(
                "Administration of Human Resource Programs (except Education, Public Health, and Veterans' Affairs Programs)",
                "Public Health Program Administration",
            ),
        )
        self.assertIn(
            "candidate_contains_source_excluded_scope",
            semantic_conflicts(
                "Manufacturing of canned meats (excluding dog, cat, and baby food)",
                "Baby Food Manufacturing",
            ),
        )
        self.assertIn(
            "hazard_scope_conflict",
            semantic_conflicts("Nonhazardous Waste Treatment", "Hazardous Waste Treatment"),
        )
        self.assertIn(
            "hazard_scope_conflict",
            semantic_conflicts("Non-hazardous Waste Treatment", "Hazardous Waste Treatment"),
        )
        specialty_flags = semantic_flags(
            "Specialty (except Psychiatric and Substance Abuse) Hospitals"
        )
        self.assertEqual(
            specialty_flags["excluded_terms"],
            ["abuse", "psychiatric", "substance"],
        )
        self.assertTrue(semantic_flags("All Other Warehousing and Storage")["residual"])

    def test_napcs_controls_are_typed(self) -> None:
        kinds = [record.record_kind for record in parse_napcs()]
        self.assertIn("survey_control", kinds)
        self.assertIn("napcs_broad_line", kinds)
        self.assertIn("napcs_detail_line", kinds)


if __name__ == "__main__":
    unittest.main()

