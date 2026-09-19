"""Coverage Ledger drift guard (ACNR consumer wiring — Task 34.4).

依 design.md「Coverage Ledger — 全库 ACNR 消费点清单」建 CI 契约测试。

Property 27 (Legacy-Consumer Drift Guard):
    任何新后端模块引入直接 `address_registry.` 消费者，若不在文档化豁免白名单
    且无对应 Coverage Ledger 条目 → 本 drift-guard 测试 CI 失败。

规则：
1. 扫描 `backend/app/` 全部 .py，匹配对 legacy `address_registry` 的直接引用
   （属性访问 `address_registry.` 或 `from app.(services|routers).address_registry import`
   或 `import address_registry`）。
2. 已知消费者（Coverage Ledger 条目）∪ 豁免白名单 = 允许集（allowlist）。
   每一条目均注明其 design Coverage Ledger 映射（P 优先级 / Req 号）作为单一真源。
3. 断言实际引用集合 ⊆ allowlist。新增未登记的 legacy 消费者 → 失败，提示补 Ledger 条目
   （Req 22.2 / 22.3）。

单一真源：`.kiro/specs/acnr-consumer-wiring/design.md` §「Coverage Ledger」。
新增 `address_registry.` 消费点时，必须同步更新该 Ledger 表 **和** 下方 allowlist。

Validates: Requirements 22.1, 22.2, 22.3
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# tests/ -> backend/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_APP = _REPO_ROOT / "backend" / "app"

# 直接消费 legacy address_registry 的引用形态：
#   - 属性访问：address_registry.invalidate_async / .search / ...
#   - 模块导入：from app.services.address_registry import ...
#                from app.routers.address_registry import router
#                import address_registry
_CONSUMER_RE = re.compile(
    r"address_registry\."
    r"|from\s+app\.(?:services|routers)\.address_registry\s+import"
    r"|import\s+address_registry"
)

# ── Coverage Ledger allowlist（design.md §Coverage Ledger 单一真源）──
# 路径相对 backend/app/，使用正斜杠。value = 该消费点的 Ledger 映射/豁免理由。
#
# A. 迁移/已覆盖消费者（Ledger 条目）
_LEDGER_CONSUMERS: dict[str, str] = {
    "services/wp_parsed_data_service.py": "P6 / Req 10.1 — touch_wp_registry invalidate(domain=wp)",
    "services/event_handlers.py": "P6 / Req 11 — _invalidate_addr_tb/report/note delegation",
    "services/wp_structure_bridge.py": "P15 / Req 21.2 — build_uri/AddressEntry 产出",
    "services/formula_engine.py": "P15 / Req 21.1 — extract_custom_cells WP cell 解析",
    "routers/query_builder.py": "P15 / Req 21.3 — TB() ref 语法生成",
    "routers/wp_structure.py": "P6 / Req 2.6 — wp_structure invalidate(domain=wp)",
}

# B. 文档化豁免白名单（ACNR core delegation + legacy V1 router，非 gap）
_EXEMPTIONS: dict[str, str] = {
    "routers/address_registry.py": "豁免 Req 21.4 — V1 API strangler fallback（不删）",
    "router_registry/system.py": "豁免 Req 21.4 — 注册 V1 address_registry router（strangler wiring）",
    "services/acnr/events.py": "豁免 Req 21.5 — ACNR core：WP 域 canonical invalidate 委托 legacy",
    "services/acnr/grammar.py": "豁免 Req 21.5 — ACNR core：非 WP/PREV 域委托 legacy",
    "services/acnr/resolver.py": "豁免 Req 21.5 — ACNR core：V1 delegation (_delegate_v1)",
    "services/acnr/runtime.py": "豁免 Req 21.5 — ACNR core：custom_flat profile 注释引用",
    "services/acnr/formula_validation.py": "豁免 Req 21.5 / P5 Req 9 — ACNR helper 非 WP 域委托 legacy",
}

_ALLOWLIST: dict[str, str] = {**_LEDGER_CONSUMERS, **_EXEMPTIONS}


def _scan_consumers() -> set[str]:
    """扫描 backend/app 下所有 .py，返回直接引用 legacy address_registry 的相对路径集合。"""
    assert _BACKEND_APP.is_dir(), f"backend/app 不存在: {_BACKEND_APP}"
    hits: set[str] = set()
    for path in _BACKEND_APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if _CONSUMER_RE.search(text):
            rel = path.relative_to(_BACKEND_APP).as_posix()
            hits.add(rel)
    return hits


@pytest.fixture(scope="module")
def consumers() -> set[str]:
    found = _scan_consumers()
    # 该测试必须真正枚举出真实引用点，否则退化为无意义的空集通过。
    assert found, "扫描未发现任何 address_registry 引用 — 正则或扫描根目录可能失效"
    return found


def test_scan_finds_known_consumers(consumers: set[str]) -> None:
    """健全性：扫描必须命中已知核心消费点（防扫描/正则退化为 trivial pass）。"""
    must_include = {
        "services/acnr/events.py",
        "services/event_handlers.py",
        "routers/address_registry.py",
    }
    missing = must_include - consumers
    assert not missing, f"扫描漏掉已知 address_registry 消费点: {sorted(missing)}"


def test_no_undocumented_legacy_consumer(consumers: set[str]) -> None:
    """Property 27 — drift guard：无未登记的新 legacy 消费者。

    实际引用集合必须 ⊆ (Ledger 消费者 ∪ 豁免白名单)。
    """
    undocumented = sorted(consumers - _ALLOWLIST.keys())
    assert not undocumented, (
        "检测到未登记的 legacy `address_registry.` 直接消费者：\n"
        + "\n".join(f"  - {p}" for p in undocumented)
        + "\n\n请将其迁移到 ACNR（acnr.events / full_resolve 等 canonical 入口），"
        "或若属正当直接消费，则在 design.md §Coverage Ledger 补充条目并同步更新本测试的 "
        "_LEDGER_CONSUMERS/_EXEMPTIONS allowlist（Req 22.2 / 22.3）。"
    )


def test_allowlist_has_no_stale_entries(consumers: set[str]) -> None:
    """Ledger 保持权威（Req 22.3）：allowlist 不得残留已不再引用 address_registry 的条目。"""
    stale = sorted(_ALLOWLIST.keys() - consumers)
    assert not stale, (
        "Coverage Ledger allowlist 存在过期条目（这些文件已不再引用 address_registry）：\n"
        + "\n".join(f"  - {p}  [{_ALLOWLIST[p]}]" for p in stale)
        + "\n\n请从 design.md §Coverage Ledger 与本测试 allowlist 中移除，保持 sweep 权威。"
    )


def test_ledger_entries_are_disjoint() -> None:
    """Ledger 消费者与豁免白名单不重叠（映射唯一，避免双重登记歧义）。"""
    overlap = _LEDGER_CONSUMERS.keys() & _EXEMPTIONS.keys()
    assert not overlap, f"同一路径同时登记为消费者与豁免: {sorted(overlap)}"
