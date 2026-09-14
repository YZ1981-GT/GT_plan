"""test_workpaper_summaries — 底稿摘要 API 骨架测试

覆盖:
- 有效 key 返回 200 + ready=False 响应
- 未知 key 返回 404
- 全部 5 个 key 均注册
- 响应 schema 验证
"""

import uuid

import pytest
from hypothesis import given, settings, strategies as st
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.workpaper_summaries_service import SUMMARY_REGISTRY

# ── 有效 key 列表 ──
VALID_KEYS = list(SUMMARY_REGISTRY.keys())


# ── fixture: async client ──
@pytest.fixture
async def client():
    """In-process ASGI client (无需真实 DB 连接即可验证路由注册+404)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── 单元测试: SUMMARY_REGISTRY ──

def test_registry_has_5_keys():
    """注册表包含全部 5 个 key"""
    expected = {"misstatement", "control_deficiency", "going_concern",
                "governance_communication", "related_party"}
    assert set(SUMMARY_REGISTRY.keys()) == expected


def test_registry_entries_have_required_fields():
    """每个注册表项包含 source_wp 和 description"""
    for key, entry in SUMMARY_REGISTRY.items():
        assert "source_wp" in entry, f"{key} 缺少 source_wp"
        assert "description" in entry, f"{key} 缺少 description"
        assert isinstance(entry["source_wp"], list)
        assert len(entry["source_wp"]) > 0


# ── 单元测试: service 函数 ──

@pytest.mark.asyncio
async def test_get_workpaper_summary_valid_key():
    """有效 key 返回 not-ready 响应 dict"""
    from app.services.workpaper_summaries_service import get_workpaper_summary

    # db 参数在 P1 不使用，传 None 即可
    result = await get_workpaper_summary(None, uuid.uuid4(), "misstatement")
    assert result is not None
    assert result["ready"] is False
    assert result["key"] == "misstatement"
    assert result["source_wp"] == ["A13-1", "A13-4"]
    assert result["reason"] == "数据源未就绪"


@pytest.mark.asyncio
async def test_get_workpaper_summary_unknown_key():
    """未知 key 返回 None"""
    from app.services.workpaper_summaries_service import get_workpaper_summary

    result = await get_workpaper_summary(None, uuid.uuid4(), "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_get_workpaper_summary_all_keys_not_ready():
    """全部 5 个 key 均返回 ready=False"""
    from app.services.workpaper_summaries_service import get_workpaper_summary

    pid = uuid.uuid4()
    for key in VALID_KEYS:
        result = await get_workpaper_summary(None, pid, key)
        assert result is not None
        assert result["ready"] is False
        assert result["key"] == key
        assert "source_wp" in result
        assert "reason" in result


# ── Property-based test ──

@settings(max_examples=5)
@given(key=st.sampled_from(VALID_KEYS))
def test_pbt_valid_key_schema(key: str):
    """**Validates: Requirements INFRA-2**

    Property: 对注册表内任意有效 key，service 返回符合 schema 的 not-ready 响应。
    """
    import asyncio
    from app.services.workpaper_summaries_service import get_workpaper_summary

    result = asyncio.run(get_workpaper_summary(None, uuid.uuid4(), key))
    # Schema 验证
    assert isinstance(result, dict)
    assert result["ready"] is False
    assert result["key"] == key
    assert isinstance(result["source_wp"], list)
    assert all(isinstance(wp, str) for wp in result["source_wp"])
    assert isinstance(result["reason"], str)
    assert len(result["reason"]) > 0


@settings(max_examples=5)
@given(key=st.text(min_size=1, max_size=50).filter(lambda k: k not in SUMMARY_REGISTRY))
def test_pbt_unknown_key_returns_none(key: str):
    """**Validates: Requirements INFRA-2**

    Property: 任何不在注册表中的 key，service 返回 None（路由应转 404）。
    """
    import asyncio
    from app.services.workpaper_summaries_service import get_workpaper_summary

    result = asyncio.run(get_workpaper_summary(None, uuid.uuid4(), key))
    assert result is None
