"""调整分录导入导出 —— 后端契约守卫（对 adjustment_ie_contract.json）。

spec: adjustment-import-export-contract / Task 4.1 + Task 4.3

守卫内容：
  * Property 9  遍历**全部循环** `_X_SPECS` 中的调整 sheet（不硬编码逐条清单），
                逐条对照 `backend/data/adjustment_ie_contract.json`：
                `item_id` / **有效** `storage_field` / `field_keys` 必须一致；
                不一致时失败信息指名具体 sheet + 维度。
  * Property 11 注册完整性：后端发现的每张调整 sheet 必须出现在清单 `sheets` 或 `exempt` 中；
                遗漏即失败（前端侧同款守卫在 vitest：`adjustmentIeContract.spec.ts`）。
  * Property 6  中央通道三者列集合互相兼容：中央导入必填列 ⊆ 富模板列集合，
                且 ⊆ 汇总导出列集合（经别名规范化后）→ 导出产物可被导入接受。

判定「调整 sheet」的口径（避免硬编码清单）：spec 的 `title` 含「调整分录」，
或 `item_id` 命中 `adj` / `adjustment` / `-aje-` 等调整语义片段。
"""
from __future__ import annotations

import importlib
import inspect
import json
import re
from pathlib import Path
from typing import Any

import pytest

_IE_DIR = Path(__file__).resolve().parents[1] / "app" / "routers" / "wp_render_strategies"
_CONTRACT_PATH = Path(__file__).resolve().parents[1] / "data" / "adjustment_ie_contract.json"
_FACTORY_DEFAULT_STORAGE_FIELD = "conclusion"

# 调整分录 sheet 的 item_id 语义片段。
# ⚠️ 刻意**不含**裸 `-adj-`：审定表（X-1）的 AJE/RJE 列数据键形如 `F4-1-adj-aging-rows`、
#    `G10-adj-rows`、`I1-adj-rows`，属审定表而非调整分录汇总表，不在本 spec 契约范围内。
_ADJ_ITEM_ID_HINTS = ("adjustment", "adj-entries", "-aje-rows")


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def _router_default_storage_field(mod) -> str:
    """截取 `create_cycle_import_export_router(...)` 实参里的 storage_field（未传则工厂默认）。"""
    try:
        src = inspect.getsource(mod)
    except OSError:  # pragma: no cover
        return _FACTORY_DEFAULT_STORAGE_FIELD
    marker = "create_cycle_import_export_router("
    if marker not in src:
        return _FACTORY_DEFAULT_STORAGE_FIELD
    idx = src.index(marker)
    i = idx + len(marker)
    depth = 1
    while i < len(src) and depth:
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
        i += 1
    args = src[idx + len(marker):i - 1]
    m = re.search(r'storage_field\s*=\s*"([^"]*)"', args)
    return m.group(1) if m else _FACTORY_DEFAULT_STORAGE_FIELD


def _is_adjustment_spec(sheet: str, spec: dict) -> bool:
    title = str(spec.get("title") or "")
    item_id = str(spec.get("item_id") or f"{sheet}-rows")
    if "调整分录" in title:
        return True
    low = item_id.lower()
    return any(h in low for h in _ADJ_ITEM_ID_HINTS)


def _discover_factory_adjustment_sheets() -> dict[str, dict[str, Any]]:
    """遍历全部 `*_import_export.py` 的工厂式 `_X_SPECS`，返回调整 sheet 的实测三重键。"""
    found: dict[str, dict[str, Any]] = {}
    for f in sorted(_IE_DIR.glob("*_import_export.py")):
        mod_name = "app.routers.wp_render_strategies." + f.stem
        mod = importlib.import_module(mod_name)
        specs = None
        for attr in dir(mod):
            if re.fullmatch(r"_[A-Z0-9]+_SPECS", attr) and isinstance(getattr(mod, attr), dict):
                specs = getattr(mod, attr)
                break
        if not specs:
            continue
        router_default = _router_default_storage_field(mod)
        for sheet, spec in specs.items():
            if not isinstance(spec, dict) or "item_id" not in spec:
                continue
            if not _is_adjustment_spec(sheet, spec):
                continue
            found[sheet] = {
                "module": mod_name,
                "item_id": spec["item_id"],
                "storage_field_effective": spec.get("storage_field") or router_default,
                "field_keys": list(spec["field_keys"]),
                "headers": list(spec["headers"]),
            }
    return found


_DISCOVERED = _discover_factory_adjustment_sheets()


def test_guard_discovers_adjustment_sheets():
    """守卫自身有效性：必须真的发现到调整 sheet（否则遍历口径失效 → 守卫变空转）。"""
    assert len(_DISCOVERED) >= 14, f"仅发现 {len(_DISCOVERED)} 张调整 sheet，遍历口径疑似失效：{sorted(_DISCOVERED)}"


@pytest.mark.parametrize("sheet", sorted(_DISCOVERED))
def test_p11_every_backend_adjustment_sheet_is_registered(sheet, contract):
    """Property 11：后端调整 sheet 必须登记在清单 sheets 或 exempt。"""
    in_sheets = sheet in contract["sheets"]
    in_exempt = sheet in contract["exempt"] and not sheet.startswith("_")
    assert in_sheets or in_exempt, (
        f"后端调整 sheet {sheet}（{_DISCOVERED[sheet]['module']}）未登记到契约清单；"
        "请补 sheets 条目（纳入对齐）或 exempt 条目（写明豁免原因）"
    )


@pytest.mark.parametrize("sheet", sorted(_DISCOVERED))
def test_p9_backend_triple_matches_contract(sheet, contract):
    """Property 9：清单内 aligned 的 sheet，后端三重键逐字一致。"""
    if sheet not in contract["sheets"]:
        pytest.skip(f"{sheet} 属 exempt（{contract['exempt'][sheet]['kind']}）")
    entry = contract["sheets"][sheet]
    if entry["status"] != "aligned":
        pytest.skip(f"{sheet} 仍待对齐（status={entry['status']}）")
    actual = _DISCOVERED[sheet]
    mismatches = []
    if actual["item_id"] != entry["item_id"]:
        mismatches.append(f"item_id: 后端 {actual['item_id']!r} != 清单 {entry['item_id']!r}")
    if actual["storage_field_effective"] != entry["storage_field"]:
        mismatches.append(
            f"storage_field(有效): 后端 {actual['storage_field_effective']!r} != 清单 {entry['storage_field']!r}"
        )
    if actual["field_keys"] != entry["field_keys"]:
        mismatches.append(
            f"field_keys:\n    后端 {actual['field_keys']}\n    清单 {entry['field_keys']}"
        )
    assert not mismatches, f"{sheet} 契约漂移（{actual['module']}）:\n  " + "\n  ".join(mismatches)


def test_p9_contract_sheets_all_exist_in_backend(contract):
    """反向：清单 sheets 里的每张必须真的在后端注册（防清单登记了不存在的 sheet）。"""
    missing = [s for s in contract["sheets"] if s not in _DISCOVERED]
    assert not missing, f"清单 sheets 登记了后端未注册/未被识别为调整 sheet 的条目: {missing}"


def test_exempt_entries_have_kind_and_reason(contract):
    """豁免必须可区分：每条 exempt 有已登记的 kind + 非空 reason。"""
    kinds = set(contract["exempt"]["_exempt_kinds"])
    bad = []
    for sheet, e in contract["exempt"].items():
        if sheet.startswith("_"):
            continue
        if not isinstance(e, dict) or e.get("kind") not in kinds or not e.get("reason"):
            bad.append(sheet)
    assert not bad, f"exempt 条目缺 kind/reason 或 kind 未登记: {bad}"


def test_no_sheet_both_registered_and_exempt(contract):
    dup = sorted(set(contract["sheets"]) & {k for k in contract["exempt"] if not k.startswith("_")})
    assert not dup, f"同一 sheet 既在 sheets 又在 exempt: {dup}"


# ═══════════════════════════════════════════════════════════════════════════
# Property 6 —— 中央通道三者列集合互相兼容
# ═══════════════════════════════════════════════════════════════════════════


def _summary_export_headers() -> list[str]:
    """从 `_write_adj_sheet` 源码提取汇总导出列头（唯一真源，避免复制常量）。"""
    from app.routers import adjustments as adj_router

    src = inspect.getsource(adj_router._write_adj_sheet)
    m = re.search(r"headers\s*=\s*\[(.*?)\]", src, re.S)
    assert m, "未能从 _write_adj_sheet 提取 headers"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_p6_central_required_columns_compatible_with_both_templates():
    """中央导入必填列 ⊆ 富模板列，且（经别名规范化后）⊆ 汇总导出列。"""
    from app.services.import_template_service import (
        TEMPLATE_COLUMNS,
        ImportType,
        normalize_adjustment_header,
    )

    cols = TEMPLATE_COLUMNS[ImportType.adjustments]
    required = [c[0] for c in cols if c[1]]
    rich = [c[0] for c in cols]
    assert required, "调整分录模板必填列不应为空"
    assert set(required) <= set(rich)

    summary_norm = {normalize_adjustment_header(h) for h in _summary_export_headers()}
    missing = [h for h in required if h not in summary_norm]
    assert not missing, (
        f"汇总导出列（规范化后 {sorted(summary_norm)}）缺中央导入必填列 {missing} → "
        "导出的汇总无法直接导回（Property 6）"
    )
