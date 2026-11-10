import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from turbo.web.app import create_app


class WebApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app(frontend_dist=Path("/nonexistent")))

    def test_context_has_provenance_and_etag(self) -> None:
        response = self.client.get("/api/v1/context")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["provenance"]["partition_id"],
            "family-partition:60517981ab96e7f243c7033e",
        )
        self.assertEqual(response.headers["x-turbo-source-run"], "run-2ea0f00db84148de663f")
        self.assertTrue(response.headers["etag"].startswith('"'))

    def test_etag_returns_not_modified(self) -> None:
        first = self.client.get("/api/v1/markets")
        replay = self.client.get(
            "/api/v1/markets", headers={"If-None-Match": first.headers["etag"]}
        )
        self.assertEqual(replay.status_code, 304)
        self.assertEqual(replay.content, b"")

    def test_etag_is_bound_to_the_exact_response_representation(self) -> None:
        markets = self.client.get("/api/v1/markets?page_size=1")
        families = self.client.get(
            "/api/v1/families?page_size=1",
            headers={"If-None-Match": markets.headers["etag"]},
        )
        second_market_page = self.client.get("/api/v1/markets?page=2&page_size=1")
        self.assertEqual(families.status_code, 200)
        self.assertNotEqual(markets.headers["etag"], families.headers["etag"])
        self.assertNotEqual(markets.headers["etag"], second_market_page.headers["etag"])

    def test_markets_are_deterministic_and_not_ranked(self) -> None:
        first = self.client.get("/api/v1/markets?page_size=100")
        replay = self.client.get("/api/v1/markets?page_size=100")
        self.assertEqual(first.json(), replay.json())
        data = first.json()["data"]
        self.assertEqual(data["total"], 5)
        serialized = first.text.casefold()
        self.assertNotIn('"score"', serialized)
        self.assertNotIn('"rank"', serialized)

    def test_family_detail_bounds_context_collection(self) -> None:
        listing = self.client.get("/api/v1/families?page_size=1").json()["data"]
        family_id = listing["items"][0]["family_id"]
        detail = self.client.get(
            f"/api/v1/families/{family_id}?context_page_size=5"
        )
        self.assertEqual(detail.status_code, 200)
        context = detail.json()["data"]["context_identities"]
        self.assertLessEqual(len(context["items"]), 5)
        self.assertIn("ownership_notice", detail.text)

    def test_candidate_search_link_filters_the_candidate_endpoint(self) -> None:
        results = self.client.get("/api/v1/search?q=office&limit=100").json()["data"]
        candidate = next(item for item in results if item["kind"] == "candidate")
        response = self.client.get(candidate["href"])
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["candidate_market_id"], candidate["id"])

    def test_search_requires_bounded_query(self) -> None:
        response = self.client.get("/api/v1/search?q=x")
        self.assertEqual(response.status_code, 400)
        self.assertIn("at least 2", response.json()["detail"])

    def test_receipt_paths_are_allowlisted(self) -> None:
        valid = self.client.get(
            "/api/v1/receipts/graph-release/graph-release-aa5b6f83e7a06e073d3a"
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["data"]["kind"], "graph-release")
        unknown = self.client.get("/api/v1/receipts/arbitrary/value")
        self.assertEqual(unknown.status_code, 404)
        missing = self.client.get("/api/v1/receipts/graph-release/nonexistent")
        self.assertEqual(missing.status_code, 404)
        self.assertNotIn(str(Path.cwd()), missing.text)
        self.assertEqual(missing.json()["detail"], "Receipt not found")

    def test_incompatible_version_tuple_fails_closed(self) -> None:
        response = self.client.get(
            "/api/v1/context?source_run_id=run-1f039950ed1e4e3192c7"
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("incompatible", response.json()["detail"])

    def test_missing_version_errors_are_sanitized(self) -> None:
        for query in ("source_run_id=nonexistent", "partition_id=nonexistent",
                      "graph_version_id=nonexistent", "source_run_id=",
                      "partition_id=", "graph_version_id="):
            with self.subTest(query=query):
                response = self.client.get("/api/v1/context?" + query)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["detail"],
                                 "Requested snapshot is unavailable or incompatible")
                self.assertNotIn(str(Path.cwd()), response.text)

    def test_every_snapshot_route_uses_the_shared_version_selection(self) -> None:
        market_id = self.client.get("/api/v1/markets?page_size=1").json()["data"][
            "items"
        ][0]["market_id"]
        family_id = self.client.get("/api/v1/families?page_size=1").json()["data"][
            "items"
        ][0]["family_id"]
        incompatible = "source_run_id=run-1f039950ed1e4e3192c7"
        routes = [
            "/api/v1/context",
            "/api/v1/versions",
            "/api/v1/markets",
            f"/api/v1/markets/{market_id}",
            "/api/v1/mappings",
            "/api/v1/families",
            f"/api/v1/families/{family_id}",
            "/api/v1/batches",
            "/api/v1/identities/identity:naics:561110",
            "/api/v1/candidates",
            "/api/v1/search?q=office",
            (
                "/api/v1/receipts/graph-release/"
                "graph-release-aa5b6f83e7a06e073d3a"
            ),
        ]
        for route in routes:
            separator = "&" if "?" in route else "?"
            with self.subTest(route=route):
                response = self.client.get(f"{route}{separator}{incompatible}")
                self.assertEqual(response.status_code, 409)
                self.assertIn("incompatible", response.json()["detail"])

    def test_compatible_historical_tuple_reaches_detail_routes(self) -> None:
        versions = self.client.get("/api/v1/versions").json()["data"]
        historical = next(
            item for item in versions["compatible_snapshots"] if not item["current"]
        )
        family_id = self.client.get("/api/v1/families?page_size=1").json()["data"][
            "items"
        ][0]["family_id"]
        query = (
            f"source_run_id={historical['source_run_id']}"
            f"&partition_id={historical['partition_id']}"
            f"&graph_version_id={historical['graph_version_id']}"
        )
        response = self.client.get(f"/api/v1/families/{family_id}?{query}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["provenance"]["partition_id"],
            historical["partition_id"],
        )
        self.assertEqual(response.headers["x-turbo-partition"], historical["partition_id"])

    def test_page_size_is_bounded_at_http_boundary(self) -> None:
        response = self.client.get("/api/v1/families?page_size=101")
        self.assertEqual(response.status_code, 422)

    def test_compiled_spa_is_served_without_second_application_server(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            dist = Path(temporary)
            (dist / "index.html").write_text("<title>Turbo</title>", encoding="utf-8")
            client = TestClient(create_app(frontend_dist=dist))
            response = client.get("/families/example")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Turbo", response.text)


if __name__ == "__main__":
    unittest.main()
