"""K/F/G/H 循环 adapter 注册验证 — Task 8.1（Phase 2 扩循环）.

验证 `_kfgh_cycle_adapters.register_kfgh_cycle_adapters()` 把 K/F/G/H 各循环单表
I/E 端点接入 `IE_ADAPTER_REGISTRY`：
  1. 每个新登记的 api_prefix 都能在注册表中解析到 AdapterSpec；
  2. 其 export_fn / import_fn 均为 callable；
  3. 每个循环（K/F/G/H）至少一张 sheet 的「导出模板」冒烟通过
     （经 export_tab(mode="template") + mock db，返回合法 xlsx 字节流）。

铁律：断言指向「接线正确性」，不弱化。冒烟只走 template 导出（不触库/不写库）。
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")
os.environ.setdefault("DB_DISABLE_SSL", "True")

import pytest

# 导入包触发 D + K/F/G/H adapter 注册（__init__.py 内 import 即注册）
import app.services.bulk_tab  # noqa: F401
from app.services.bulk_tab.single_tab_adapter import (
    IE_ADAPTER_REGISTRY,
    export_tab,
)
from app.services.bulk_tab._kfgh_cycle_adapters import (
    _PREFIX_TO_MODULE,
    register_kfgh_cycle_adapters,
)


# ---------------------------------------------------------------------------
# 期望注册的 api_prefix（源自 K/F/G/H 单表 I/E 端点模块枚举）
# ---------------------------------------------------------------------------

EXPECTED_PREFIXES: dict[str, list[str]] = {
    "F": ["f0", "f1", "f2", "f2-spe", "f2-st", "f2-val", "f3", "f4", "f5"],
    "G": [
        "g0", "g1", "g2", "g3", "g4-ecl", "g4-main", "g4-sppi", "g5",
        "g6-ecl", "g6-main", "g6-sppi", "g7-main", "g7-equity-method",
        "g7-sub", "g8", "g9", "g10", "g11", "g12", "g13", "g14",
    ],
    "H": ["h0", "h1", "h2", "h3", "h4", "h5", "h6", "h7", "h8", "h9", "h10"],
    "K": [
        "k0", "k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "k9",
        "k10", "k11", "k12", "k13",
    ],
}

# C/E/I/J/L/M/N wp_render_strategies 统一族（补齐，同构路径）；j3 异形单独 bespoke
EXPECTED_PREFIXES["CEIJL"] = [
    "c24-journal", "e1",
    "i1", "i2", "i3", "i4", "i5", "i6",
    "j1", "j2", "l0",
    "l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8",
    "m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10",
    "n1", "n2", "n3", "n4", "n5",
]

ALL_EXPECTED = [p for prefixes in EXPECTED_PREFIXES.values() for p in prefixes]

# 每循环一张代表 sheet，用于「导出模板」冒烟（模板导出不触库，mock db 足够）
SMOKE_SHEETS: dict[str, tuple[str, str]] = {
    "F": ("f2-st", "F2-24"),   # 存货监盘（DB-free 模板）
    "G": ("g8", "G8-3"),        # 其他权益工具（DB-free 模板）
    "H": ("h10", "H10-2"),      # 资产处置收益（DB-free 模板）
    "K": ("k1", "K1-5"),        # 其他应收款（工厂族非账龄 sheet，db 未用）
}


# ---------------------------------------------------------------------------
# 1) 注册表解析 + callable
# ---------------------------------------------------------------------------


def test_prefix_map_covers_all_expected():
    """_PREFIX_TO_MODULE 与期望 prefix 集一致（防漏防多；j3 走 bespoke 不入此 dict）。"""
    assert set(_PREFIX_TO_MODULE.keys()) == set(ALL_EXPECTED)


def test_j3_bespoke_registered():
    """J3 异形路径 bespoke adapter 注册到 registry（不在 _PREFIX_TO_MODULE dict）。"""
    assert "j3" not in _PREFIX_TO_MODULE
    assert "j3" in IE_ADAPTER_REGISTRY
    spec = IE_ADAPTER_REGISTRY["j3"]
    assert callable(spec.export_fn) and callable(spec.import_fn)


@pytest.mark.parametrize("api_prefix", EXPECTED_PREFIXES["CEIJL"])
def test_ceijl_endpoints_resolve(api_prefix: str):
    """C/E/I/J/L 统一族：三端点均能从 module.router 按 /{prefix}/{suffix} 提取。

    这是「接线正确性」的核心断言——路径匹配失败即 adapter 死代码。
    不触库（仅解析 endpoint 闭包）。
    """
    import importlib

    from app.services.bulk_tab._kfgh_cycle_adapters import (
        _MODULE_PKG,
        _SUFFIX_DATA,
        _SUFFIX_IMPORT,
        _SUFFIX_TEMPLATE,
        _endpoint_for,
    )

    module = importlib.import_module(_MODULE_PKG + _PREFIX_TO_MODULE[api_prefix])
    for suffix in (_SUFFIX_TEMPLATE, _SUFFIX_DATA, _SUFFIX_IMPORT):
        assert _endpoint_for(module, api_prefix, suffix) is not None, (
            f"{api_prefix}: 未能提取 {suffix} 端点（路径不匹配 → adapter 死代码）"
        )


@pytest.mark.parametrize("api_prefix", ALL_EXPECTED)
def test_prefix_resolves_in_registry(api_prefix: str):
    """每个新登记的 api_prefix 都能在 IE_ADAPTER_REGISTRY 中解析到 AdapterSpec。"""
    assert api_prefix in IE_ADAPTER_REGISTRY, (
        f"api_prefix='{api_prefix}' 未注册到 IE_ADAPTER_REGISTRY"
    )
    spec = IE_ADAPTER_REGISTRY[api_prefix]
    assert callable(spec.export_fn), f"{api_prefix} export_fn 不可调用"
    assert callable(spec.import_fn), f"{api_prefix} import_fn 不可调用"


def test_registration_is_idempotent():
    """重复调用 register 不改变注册键集合（幂等）。"""
    before = set(IE_ADAPTER_REGISTRY.keys())
    register_kfgh_cycle_adapters()
    after = set(IE_ADAPTER_REGISTRY.keys())
    assert before == after


def test_d_cycle_adapters_still_present():
    """扩 K/F/G/H 不得覆盖既有 D 循环注册。"""
    for d in ("d1", "d2", "d3", "d4", "d5", "d6", "d7"):
        assert d in IE_ADAPTER_REGISTRY, f"D 循环 '{d}' 注册丢失"


# ---------------------------------------------------------------------------
# 2) 每循环导出模板冒烟（export_tab template → 合法 xlsx）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cycle", ["F", "G", "H", "K"])
def test_export_template_smoke_per_cycle(cycle: str):
    """每个循环至少一张 sheet：export_tab(mode="template") 返回合法 xlsx 字节流。

    模板导出不读/写库；用 AsyncMock db 驱动，验证 adapter 接线（端点提取 +
    签名感知调用 + StreamingResponse→bytes）端到端可用。
    """
    api_prefix, sheet_code = SMOKE_SHEETS[cycle]
    db = AsyncMock()
    data = asyncio.run(
        export_tab(db, "wp-smoke-test", api_prefix, sheet_code, "template")
    )
    assert isinstance(data, (bytes, bytearray)), f"{cycle} 导出未返回 bytes"
    # xlsx 是 zip 容器，magic number 为 'PK'
    assert data[:2] == b"PK", f"{cycle} 导出的模板不是合法 xlsx（缺 PK 头）"
    assert len(data) > 0
