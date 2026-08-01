"""K1 导入导出 item_id ⊆ 前端字面量集合守卫（Property 10）.

spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
Requirements 3.1, 3.5
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routers.wp_render_strategies._k1_import_export import _K1_SPECS

#: 已知缺陷、明确另立 spec 处理的 item_id（非本 spec 范围）。
#:
#: 核查发现 K1-5/K1-7 的 `headers`/`field_keys` 与真实前端模型
#: （`K1LargeAmountSheetRow`/`K1StageRow`）字段名大面积不符（不只是 item_id 名字
#: 不对，`closingBalance` vs `endBalance`、`currentStage` vs `stage` 等结构性错位），
#: K1-8 的持久化根本不是行数组而是单一 JSON 对象（`K1BadDebtCalcPayloadV2`）。
#: 三者都需要各写一套 bespoke `export_loader`/`build_workbook`/`parse_import`/
#: `import_handler`（同 K1-1/K1-3/K1-6/K1-9/K1-11 范式），工作量等同重做三张表的
#: 导入导出，超出本 spec「取数级联 + 披露/附注结构对齐」核心范围。
#: **新增豁免必须写明理由；本 spec 只修复 K1-2（四表库自动 seed 直接读写该键）。**
_KNOWN_MISMATCH_ALLOWLIST = {
    "K1-5-rows": "K1LargeAmountSheetRow 字段名大面积不符，需 bespoke 导入导出（另立）",
    "K1-7-rows": "K1StageRow 字段名部分错位（closingBalance/currentStage 等），需 bespoke（另立）",
    "K1-8-rows": "K1-8 持久化是单一 JSON 对象非行数组，通用行列表模型结构性不适用（另立）",
}

REPO = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

_ITEM_ID_RE = re.compile(r"['\"](K1-\d+-[A-Za-z0-9_\-]+)['\"]")


def _frontend_item_ids() -> set[str]:
    """扫描前端非测试源码里的 K1 item_id 字面量集合。"""
    found: set[str] = set()
    for path in FRONTEND_DIR.rglob("*"):
        if path.suffix not in (".ts", ".vue"):
            continue
        if "__tests__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        found.update(_ITEM_ID_RE.findall(text))
    return found


def _backend_item_ids() -> set[str]:
    ids: set[str] = set()
    for spec in _K1_SPECS.values():
        raw = spec.get("item_id")
        if isinstance(raw, str):
            ids.add(raw)
        elif isinstance(raw, (list, tuple)):
            ids.update(str(x) for x in raw)
    return ids


def test_frontend_literal_scan_is_non_empty():
    """反向自检：正则必须真的抓到东西，否则本守卫全程空转。"""
    ids = _frontend_item_ids()
    assert len(ids) > 30, f"抽取异常偏少：{len(ids)} 个"


def test_backend_item_ids_all_consumed_by_frontend():
    """Property 10：后端 `_K1_SPECS` 的每个 item_id 都出现在前端字面量集合中
    （已知缺陷条目走显式 allowlist，禁止悄悄扩大豁免范围）。"""
    backend_ids = _backend_item_ids()
    frontend_ids = _frontend_item_ids()
    missing = backend_ids - frontend_ids - set(_KNOWN_MISMATCH_ALLOWLIST)
    assert not missing, (
        f"以下后端 item_id 未被任何前端非测试源码消费（导入导出静默无效）：{sorted(missing)}"
    )


def test_allowlist_entries_still_actually_mismatched():
    """反向自检：allowlist 条目若已被修好必须移出（防豁免名单只增不减、越滚越大）。"""
    frontend_ids = _frontend_item_ids()
    stale = set(_KNOWN_MISMATCH_ALLOWLIST) & frontend_ids
    assert not stale, f"以下 allowlist 条目已被前端消费，应移出豁免名单：{sorted(stale)}"


def test_k1_2_item_id_is_detail_rows():
    """🔴 本 spec 修正点：K1-2 的 item_id 必须是前端真实读写键。"""
    assert _K1_SPECS["K1-2"]["item_id"] == "K1-2-detail-rows"


def test_guard_detects_regression_when_item_id_reverted():
    """反向自检：把 K1-2 item_id 改回旧值，守卫必须能抓到。"""
    backend_ids = {"K1-2-rows"}  # 模拟回退
    frontend_ids = _frontend_item_ids()
    missing = backend_ids - frontend_ids
    assert missing == {"K1-2-rows"}
