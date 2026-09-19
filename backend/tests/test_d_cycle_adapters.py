"""单元测试 — D 循环 adapter 接线 (Task 2.2)

验证：
- d1~d7 全部注册到 IE_ADAPTER_REGISTRY
- 注册表内容为 AdapterSpec 类型
- export/import 函数签名可调用
"""
import pytest

from app.services.bulk_tab.single_tab_adapter import (
    AdapterSpec,
    IE_ADAPTER_REGISTRY,
)

# 确保 adapter 注册代码被执行
import app.services.bulk_tab._d_cycle_adapters  # noqa: F401


# ---------------------------------------------------------------------------
# Tests: 所有 D 循环 prefix 已注册
# ---------------------------------------------------------------------------


D_PREFIXES = ["d1", "d2", "d3", "d4", "d5", "d6", "d7"]


def test_all_d_cycle_prefixes_registered():
    """d1~d7 全部存在于 IE_ADAPTER_REGISTRY。"""
    for prefix in D_PREFIXES:
        assert prefix in IE_ADAPTER_REGISTRY, f"prefix '{prefix}' 未注册"


def test_registry_entries_are_adapter_spec():
    """每个注册项必须是 AdapterSpec 类型。"""
    for prefix in D_PREFIXES:
        adapter = IE_ADAPTER_REGISTRY[prefix]
        assert isinstance(adapter, AdapterSpec), (
            f"prefix '{prefix}' 注册的不是 AdapterSpec: {type(adapter)}"
        )


def test_adapter_spec_has_callable_fns():
    """每个 AdapterSpec 的 export_fn / import_fn 必须是 callable。"""
    for prefix in D_PREFIXES:
        adapter = IE_ADAPTER_REGISTRY[prefix]
        assert callable(adapter.export_fn), f"{prefix} export_fn 不可调用"
        assert callable(adapter.import_fn), f"{prefix} import_fn 不可调用"


def test_no_duplicate_registrations():
    """确认 d1~d7 各注册一次，不重复。"""
    d_entries = {k: v for k, v in IE_ADAPTER_REGISTRY.items() if k.startswith("d")}
    # 至少有 d1~d7
    assert len(d_entries) >= 7
    # 每个 prefix 只有一个 entry（dict 天然去重，此处确认 fn 不同）
    fns = set()
    for prefix in D_PREFIXES:
        fn_id = id(IE_ADAPTER_REGISTRY[prefix].export_fn)
        assert fn_id not in fns, f"{prefix} export_fn 与其他 prefix 重复"
        fns.add(fn_id)


def test_unregistered_prefix_not_in_registry():
    """确保只注册了 d1~d7，其他 prefix 不在。"""
    assert "d0" not in IE_ADAPTER_REGISTRY
    assert "d8" not in IE_ADAPTER_REGISTRY
    assert "d99" not in IE_ADAPTER_REGISTRY
