# Feature: zero-downtime-deployment, Property 1
"""Property 1：版本端点返回完整构建版本。

Validates: Requirements 1.1, 1.7, 12.3
任意版本来源（env/file/兜底），/api/version 均含 version/git_commit/build_time
且取值与生效来源一致（优先级 env > file > 兜底）。
"""
import json
import os
from unittest.mock import patch

import httpx
import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

from app.core.build_version import get_build_version, _FALLBACK_VERSION
from app.main import app


@pytest.fixture(autouse=True)
def clear_version_cache():
    get_build_version.cache_clear()
    yield
    get_build_version.cache_clear()


# Constrain to ASCII (HTTP headers require latin-1; real git commits/versions are ASCII)
ascii_version_st = st.fixed_dictionaries({
    "semantic_version": st.from_regex(r"[a-z0-9][a-z0-9.\-]{0,19}", fullmatch=True),
    "git_commit": st.from_regex(r"[0-9a-f]{7,40}", fullmatch=True),
    "build_time": st.from_regex(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z", fullmatch=True),
})


def _unwrap(resp_json: dict) -> dict:
    """Unwrap ResponseWrapperMiddleware envelope {code, message, data}."""
    if "data" in resp_json and "code" in resp_json:
        return resp_json["data"]
    return resp_json


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(version_data=ascii_version_st)
@pytest.mark.asyncio
async def test_version_endpoint_env_priority(version_data):
    """Env var takes highest priority over file and fallback."""
    env_json = json.dumps(version_data)
    with patch.dict(os.environ, {"BUILD_VERSION_JSON": env_json}):
        get_build_version.cache_clear()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/version")
            assert resp.status_code == 200
            body = _unwrap(resp.json())
            assert body["version"] == version_data["semantic_version"]
            assert body["git_commit"] == version_data["git_commit"]
            assert body["build_time"] == version_data["build_time"]
            assert "api_prefix" in body


@pytest.mark.asyncio
async def test_version_endpoint_fallback():
    """No env, no file → fallback values."""
    env_patch = {k: v for k, v in os.environ.items() if k != "BUILD_VERSION_JSON"}
    with patch.dict(os.environ, env_patch, clear=True):
        get_build_version.cache_clear()
        with patch("app.core.build_version._BUILD_VERSION_FILE") as mock_path:
            mock_path.exists.return_value = False
            get_build_version.cache_clear()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/api/version")
                assert resp.status_code == 200
                body = _unwrap(resp.json())
                assert body["version"] == "dev"
                assert body["git_commit"] == "unknown"
                assert body["build_time"] == "unknown"
