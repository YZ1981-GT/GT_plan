"""独占键写入方基线守卫（Task 14 · 需求 4.6, 4.7）。

后端直写 checklist_responses 的站点中，item_id 字面量命中已接入主编码独占集合的，
冻结为基线——只许减少（消除直写站点后从基线移除），不许增加（新增直写独占键即红）。

扫描方式：AST 提取字符串常量和 f-string 段，按独占集合精确匹配。
不扫推送引擎自身的写入路径（formula_push/ 和 formula_runtime/）。

前端读取独占命名空间键的字面量检查另在 vitest 守卫中完成。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.services.formula_push.owned_keys import owned_item_ids

_ROOT = Path(__file__).resolve().parents[1] / "app"

# 当前已接入的主编码
_REGISTERED_CODES = ["E1"]

# 排除推送引擎自身的写入路径（它们是唯一合法写入方）
_EXCLUDED_DIRS = {"formula_push", "formula_runtime"}


def _scan_owned_key_references() -> dict[str, list[tuple[str, int, str]]]:
    """扫描后端 app/ 下所有 .py 中字符串字面量命中独占键的站点。

    返回 {主编码: [(相对路径, 行号, 命中键), ...]}
    """
    result: dict[str, list[tuple[str, int, str]]] = {}
    for code in _REGISTERED_CODES:
        owned = owned_item_ids(code)
        if not owned:
            continue
        hits: list[tuple[str, int, str]] = []
        for f in sorted(_ROOT.rglob("*.py")):
            # 排除推送引擎自身
            rel = f.relative_to(_ROOT)
            if any(part in _EXCLUDED_DIRS for part in rel.parts):
                continue
            try:
                tree = ast.parse(f.read_text("utf-8"), filename=str(f))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if node.value in owned:
                        hits.append((str(rel).replace("\\", "/"), node.lineno, node.value))
        result[code] = hits
    return result


# ── 基线：当前后端引用 E1 独占键的站点 ────────────────────────────────────
# 这些引用全在 workpaper_sync/ 和 e1_calc（推送 binding 的计算层，不经 checklist 端点写入）。
# 它们是读取方（取值计算或同步映射），不是直写方。
# 真正的直写方（checklist_responses PUT 端点）已由 Task 12 加入独占键剔除。

_E1_BASELINE_FILES = {
    "services/workpaper_sync/phase5_e1_01_adjudication.py",
    "services/workpaper_sync/phase5_e1_03_bank_detail.py",
    # e1_calc 在 formula_push/ 下已被排除，不出现在此基线
}


def test_e1_owned_key_references_only_in_baseline():
    """后端引用 E1 独占键的站点不得超出基线（只许减少，不许增加）。"""
    all_refs = _scan_owned_key_references()
    e1_refs = all_refs.get("E1", [])
    files_with_refs = {path for path, _, _ in e1_refs}
    unexpected = files_with_refs - _E1_BASELINE_FILES
    assert not unexpected, (
        f"新增了后端引用 E1 独占键的文件（只许减少不许增加）：{sorted(unexpected)}\n"
        f"命中详情：{[(p, l, k) for p, l, k in e1_refs if p in unexpected]}"
    )


def test_baseline_has_no_stale_entries():
    """基线文件必须实际存在且仍有命中（已清理的文件须从基线移除）。"""
    all_refs = _scan_owned_key_references()
    e1_refs = all_refs.get("E1", [])
    files_with_refs = {path for path, _, _ in e1_refs}
    stale = _E1_BASELINE_FILES - files_with_refs
    assert not stale, f"基线中的以下文件已无独占键引用，须移除：{sorted(stale)}"


def test_owned_keys_backend_and_frontend_in_sync():
    """后端 owned_item_ids 与生成器产出一致（重复确认，防 mtime 缓存失效）。"""
    from scripts.gen.gen_formula_push_owned_keys import compute_owned

    for code in _REGISTERED_CODES:
        gen = set(compute_owned().get(code, []))
        backend = owned_item_ids(code)
        assert gen == backend, f"{code} 前后端独占键不一致"
