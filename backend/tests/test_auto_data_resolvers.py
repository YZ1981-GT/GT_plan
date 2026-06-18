"""auto_data_resolvers 注册式解析器测试。

验证：
1. 所有 procedure_table_templates.json 中引用的 auto_data_source 都已注册
2. resolve_auto_data_source 对未注册 source 返回 None
3. 每个 resolver 被正确注册（名称不重复）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.auto_data_resolvers import (
    _REGISTRY,
    get_registered_sources,
    resolve_auto_data_source,
)


_TEMPLATES_PATH = Path(__file__).resolve().parent.parent / "data" / "procedure_table_templates.json"


def _collect_all_auto_data_sources() -> set[str]:
    """从 procedure_table_templates.json 收集所有引用的 auto_data_source 值。"""
    if not _TEMPLATES_PATH.exists():
        pytest.skip("procedure_table_templates.json 不存在")
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    sources: set[str] = set()
    for table in data.get("tables", {}).values():
        for item in table.get("items", []):
            src = item.get("auto_data_source")
            if src:
                sources.add(src)
    return sources


class TestRegistryCoverage:
    """所有在模板中引用的 auto_data_source 都必须在 registry 中有对应 resolver。"""

    def test_all_template_sources_registered(self):
        sources = _collect_all_auto_data_sources()
        registered = set(get_registered_sources())
        missing = sources - registered
        assert not missing, (
            f"以下 auto_data_source 在模板中使用但未注册 resolver：{missing}\n"
            f"请在 auto_data_resolvers.py 中添加 @auto_resolver(name) 函数"
        )

    def test_no_duplicate_registrations(self):
        """检查 registry 中无重复注册（装饰器天然防重，此测试确认逻辑正确）。"""
        sources = get_registered_sources()
        assert len(sources) == len(set(sources))

    def test_registry_has_at_least_20_resolvers(self):
        """确保迁移完整（原有 20+ 分支）。"""
        assert len(_REGISTRY) >= 20, f"当前仅注册 {len(_REGISTRY)} 个 resolver"


@pytest.mark.anyio
async def test_unknown_source_returns_none():
    """未注册的 source 应返回 None（非 KeyError）。"""
    import uuid
    from unittest.mock import AsyncMock

    db = AsyncMock()
    result = await resolve_auto_data_source(
        db, uuid.uuid4(), 2025, "nonexistent_source_xyz"
    )
    assert result is None
