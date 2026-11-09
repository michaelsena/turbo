from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from turbo.pipeline_paths import ROOT
from turbo.web.read_model import ReadSnapshot, SnapshotError, SnapshotStore


def _snapshot(
    store: SnapshotStore,
    *,
    source_run_id: str | None = None,
    partition_id: str | None = None,
    graph_version_id: str | None = None,
) -> ReadSnapshot:
    try:
        return store.get(
            source_run_id=source_run_id,
            partition_id=partition_id,
            graph_version_id=graph_version_id,
        )
    except (KeyError, OSError, SnapshotError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def _api_response(request: Request, snapshot: ReadSnapshot, data: Any) -> Response:
    headers = {
        "ETag": snapshot.etag,
        "Cache-Control": "private, no-cache",
        "X-Turbo-Source-Run": snapshot.version.source_run_id,
        "X-Turbo-Partition": snapshot.version.partition_id,
        "X-Turbo-Graph-Version": snapshot.version.graph_version_id,
    }
    if request.headers.get("if-none-match") == snapshot.etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(
        {"data": data, "provenance": snapshot.provenance()}, headers=headers
    )


def create_app(*, root: Path = ROOT, frontend_dist: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="Turbo read API",
        version="1.0.0",
        description="Local, read-only access to verified Turbo research artifacts.",
    )
    app.state.store = SnapshotStore(root)
    dist = frontend_dist if frontend_dist is not None else root / "frontend" / "dist"

    @app.exception_handler(SnapshotError)
    async def snapshot_error(_: Request, error: SnapshotError) -> Response:
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.get("/api/v1/context")
    def context(
        request: Request,
        source_run_id: str | None = None,
        partition_id: str | None = None,
        graph_version_id: str | None = None,
    ) -> Response:
        snapshot = _snapshot(
            app.state.store,
            source_run_id=source_run_id,
            partition_id=partition_id,
            graph_version_id=graph_version_id,
        )
        return _api_response(request, snapshot, snapshot.context)

    @app.get("/api/v1/versions")
    def versions(request: Request) -> Response:
        snapshot = _snapshot(app.state.store)
        return _api_response(request, snapshot, app.state.store.versions())

    @app.get("/api/v1/markets")
    def markets(
        request: Request,
        q: str | None = None,
        activation_status: str | None = None,
        gap_id: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
        source_run_id: str | None = None,
        partition_id: str | None = None,
        graph_version_id: str | None = None,
    ) -> Response:
        snapshot = _snapshot(
            app.state.store,
            source_run_id=source_run_id,
            partition_id=partition_id,
            graph_version_id=graph_version_id,
        )
        data = snapshot.list_markets(
            query=q,
            activation_status=activation_status,
            gap_id=gap_id,
            page=page,
            page_size=page_size,
        )
        return _api_response(request, snapshot, data)

    @app.get("/api/v1/markets/{market_id}")
    def market(request: Request, market_id: str) -> Response:
        snapshot = _snapshot(app.state.store)
        try:
            data = snapshot.market_detail(market_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Market not found") from error
        return _api_response(request, snapshot, data)

    @app.get("/api/v1/mappings")
    def mappings(
        request: Request,
        identity_id: str | None = None,
        market_id: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
    ) -> Response:
        snapshot = _snapshot(app.state.store)
        data = snapshot.list_mappings(
            identity_id=identity_id,
            market_id=market_id,
            page=page,
            page_size=page_size,
        )
        return _api_response(request, snapshot, data)

    @app.get("/api/v1/families")
    def families(
        request: Request,
        q: str | None = None,
        family_kind: str | None = None,
        status: str | None = None,
        schedulable: bool | None = None,
        batch_id: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
    ) -> Response:
        snapshot = _snapshot(app.state.store)
        data = snapshot.list_families(
            query=q,
            family_kind=family_kind,
            status=status,
            schedulable=schedulable,
            batch_id=batch_id,
            page=page,
            page_size=page_size,
        )
        return _api_response(request, snapshot, data)

    @app.get("/api/v1/families/{family_id}")
    def family(
        request: Request,
        family_id: str,
        context_page: int = Query(1, ge=1),
        context_page_size: int = Query(25, ge=1, le=100),
    ) -> Response:
        snapshot = _snapshot(app.state.store)
        try:
            data = snapshot.family_detail(
                family_id,
                context_page=context_page,
                context_page_size=context_page_size,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Family not found") from error
        return _api_response(request, snapshot, data)

    @app.get("/api/v1/batches")
    def batches(
        request: Request,
        status: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
    ) -> Response:
        snapshot = _snapshot(app.state.store)
        data = snapshot.list_batches(status=status, page=page, page_size=page_size)
        return _api_response(request, snapshot, data)

    @app.get("/api/v1/identities/{identity_id}")
    def identity(request: Request, identity_id: str) -> Response:
        snapshot = _snapshot(app.state.store)
        try:
            data = snapshot.identity_detail(identity_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Identity not found") from error
        return _api_response(request, snapshot, data)

    @app.get("/api/v1/candidates")
    def candidates(
        request: Request,
        q: str | None = None,
        coverage_status: str | None = None,
        family_id: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
    ) -> Response:
        snapshot = _snapshot(app.state.store)
        data = snapshot.list_candidates(
            query=q,
            coverage_status=coverage_status,
            family_id=family_id,
            page=page,
            page_size=page_size,
        )
        return _api_response(request, snapshot, data)

    @app.get("/api/v1/search")
    def search(
        request: Request,
        q: str,
        limit: int = Query(30, ge=1, le=100),
    ) -> Response:
        snapshot = _snapshot(app.state.store)
        return _api_response(request, snapshot, snapshot.search(q, limit=limit))

    @app.get("/api/v1/receipts/{kind}/{receipt_id}")
    def receipt(request: Request, kind: str, receipt_id: str) -> Response:
        snapshot = _snapshot(app.state.store)
        try:
            data = snapshot.receipt(kind, receipt_id)
        except (KeyError, OSError) as error:
            raise HTTPException(status_code=404, detail="Receipt not found") from error
        return _api_response(request, snapshot, data)

    if dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> Response:
            requested = dist / path
            if (
                path
                and requested.is_file()
                and requested.resolve().is_relative_to(dist.resolve())
            ):
                return FileResponse(requested)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
