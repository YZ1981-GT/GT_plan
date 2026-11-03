# -*- coding: utf-8 -*-
"""OpenAPI/docs 非阻塞与生产关闭（runtime-performance-and-reload-hardening-followup R5.4）。"""
from __future__ import annotations

import asyncio
import inspect
import threading
import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import openapi_runtime as runtime


def _app(env: str) -> FastAPI:
    app = FastAPI(title="T", **runtime.fastapi_docs_kwargs(env))

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    runtime.install_deferred_docs(app, env)
    return app


def test_environment_policy_closes_all_three_production_routes():
    for env in ("prod", "production", "staging", " PRODUCTION "):
        assert runtime.docs_enabled(env) is False
    for env in ("dev", "test", "", None):
        assert runtime.docs_enabled(env) is True
    assert runtime.fastapi_docs_kwargs("dev") == {
        "openapi_url": None,
        "docs_url": None,
        "redoc_url": None,
    }


@pytest.mark.asyncio
async def test_production_has_no_public_docs_but_offline_openapi_still_works():
    app = _app("production")
    assert app.openapi()["info"]["title"] == "T"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        for path in ("/openapi.json", "/docs", "/redoc"):
            assert (await client.get(path)).status_code == 404
        assert (await client.get("/ping")).status_code == 200


@pytest.mark.asyncio
async def test_development_routes_serve_schema_and_ui():
    app = _app("dev")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        schema = await client.get("/openapi.json")
        assert schema.status_code == 200
        assert schema.json()["paths"]["/ping"]
        assert (await client.get("/docs")).status_code == 200
        assert (await client.get("/redoc")).status_code == 200


@pytest.mark.asyncio
async def test_concurrent_schema_requests_are_single_flight():
    app = _app("dev")
    calls = 0

    def generate():
        nonlocal calls
        calls += 1
        time.sleep(0.03)
        app.openapi_schema = {"openapi": "3.1.0", "info": {"title": "T", "version": "1"}, "paths": {}}
        return app.openapi_schema

    app.openapi = generate  # type: ignore[method-assign]
    results = await asyncio.gather(*(runtime.ensure_openapi_schema(app) for _ in range(10)))
    assert calls == 1
    assert all(result is results[0] for result in results)


@pytest.mark.asyncio
async def test_schema_generation_in_thread_does_not_block_normal_api():
    app = _app("dev")
    entered = threading.Event()
    release = threading.Event()

    def generate():
        entered.set()
        release.wait(3)
        app.openapi_schema = {"openapi": "3.1.0", "info": {"title": "T", "version": "1"}, "paths": {}}
        return app.openapi_schema

    app.openapi = generate  # type: ignore[method-assign]
    timer = threading.Timer(0.5, release.set)
    timer.start()
    started = time.perf_counter()
    schema_task = asyncio.create_task(runtime.ensure_openapi_schema(app))
    try:
        # 心跳必须在生成线程被阻塞期间照常运行。若 _generate 改回直接 app.openapi()，
        # 事件循环会卡到外部 Timer 0.5s 后才恢复，这个断言立即打红。
        await asyncio.sleep(0.05)
        heartbeat_elapsed = time.perf_counter() - started
        assert entered.is_set()
        assert heartbeat_elapsed < 0.2
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            response = await client.get("/ping")
        assert response.status_code == 200
    finally:
        release.set()
        timer.cancel()
    await asyncio.wait_for(schema_task, 2)


@pytest.mark.asyncio
async def test_background_prewarm_is_dev_only_and_registered_for_shutdown(monkeypatch):
    monkeypatch.setattr(runtime, "OPENAPI_PREWARM_DELAY_S", 0)
    dev = _app("dev")
    tasks: list[asyncio.Task] = []
    assert runtime.schedule_openapi_prewarm(dev, tasks, "dev") is True
    assert len(tasks) == 1
    await asyncio.wait_for(tasks[0], 2)
    assert dev.openapi_schema is not None

    prod_tasks: list[asyncio.Task] = []
    assert runtime.schedule_openapi_prewarm(_app("production"), prod_tasks, "production") is False
    assert prod_tasks == []


def test_schema_generator_does_not_repeat_lazy_materialization():
    """AST 判据，注释里写到 materialize_all 不得造成假红。"""
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(runtime._generate)))
    called = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert all(not name.endswith("materialize_all") for name in called)
    assert "asyncio.to_thread" in called
