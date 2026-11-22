"""SheetOpenBindingResolver 行为守卫。"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver


def _resolver(tmp_path: Path, rows: list[dict]) -> SheetOpenBindingResolver:
    path = tmp_path / "bindings.json"
    path.write_text(json.dumps({"schema_version": "sheet-open-binding:v1", "bindings": rows}), encoding="utf-8")
    return SheetOpenBindingResolver(path)


def _manifest(*entry_ids: str) -> dict:
    return {"entries": [{"entry_id": entry_id} for entry_id in entry_ids]}


def test_provider_binding_without_identity_is_refused(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, [{
        "entry_id": "xlsx/gt-k11-asset-impairment-loss",
        "effective_entry_id": "xlsx/gt-k11-asset-impairment-loss",
        "source_wp_code": "K11",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "mapping_kind": "provider",
        "status": "pending",
    }])
    result = resolver.resolve(
        source_wp_code="K11",
        sheet_name="任意运行时名称K11-1",
        whole_workbook=False,
        manifest=_manifest("xlsx/gt-k11-asset-impairment-loss"),
    )
    assert result.binding is None
    assert result.status == "pending"
    # 批 2 起 provider 型**会**解析（取运行时请求名作 target sheet），但缺
    # `resolver_identity` 时仍必须拒 —— 没有稳定身份就无法审核这条 binding。
    # 旧的 `sheet_binding_provider_review_required` 是「一律不解析」时代的码，已不存在。
    assert result.reason == "sheet_binding_provider_identity_missing"


def test_exact_binding_resolves_only_when_target_sheet_matches(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, [{
        "entry_id": "xlsx/gt-d4-operating-revenue",
        "effective_entry_id": "xlsx/gt-d4-operating-revenue",
        "source_wp_code": "D4",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "target_sheet": "收入披露表D4-8",
        "mapping_kind": "exact",
        "status": "ready",
        "binding_id": "sha256:binding",
    }])
    manifest = _manifest("xlsx/gt-d4-operating-revenue")
    ok = resolver.resolve(source_wp_code="D4", sheet_name="收入披露表D4-8", whole_workbook=False, manifest=manifest)
    assert ok.binding is not None
    assert ok.status == "ready"
    miss = resolver.resolve(source_wp_code="D4", sheet_name="父级模板D4", whole_workbook=False, manifest=manifest)
    assert miss.binding is None
    assert miss.reason == "sheet_target_not_declared"


def test_binding_to_missing_manifest_entry_is_pending_not_room_ready(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, [{
        "entry_id": "xlsx/gt-d4-operating-revenue",
        "effective_entry_id": "xlsx/gt-d4-operating-revenue",
        "source_wp_code": "D4",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "target_sheet": "D4-8",
        "mapping_kind": "exact",
        "status": "ready",
    }])
    result = resolver.resolve(
        source_wp_code="D4",
        sheet_name="D4-8",
        whole_workbook=False,
        manifest=_manifest("xlsx/other-entry"),
    )
    assert result.status == "pending"
    assert result.reason == "sheet_binding_entry_not_in_manifest"
    assert result.binding is not None


def test_duplicate_exact_bindings_are_ambiguous(tmp_path: Path) -> None:
    row = {
        "entry_id": "xlsx/one",
        "effective_entry_id": "xlsx/one",
        "source_wp_code": "D4",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "target_sheet": "D4-8",
        "mapping_kind": "exact",
        "status": "ready",
    }
    resolver = _resolver(tmp_path, [row, {**row, "entry_id": "xlsx/two", "effective_entry_id": "xlsx/two"}])
    result = resolver.resolve(
        source_wp_code="D4", sheet_name="D4-8", whole_workbook=False,
        manifest=_manifest("xlsx/one", "xlsx/two"),
    )
    assert result.binding is None
    assert result.reason == "sheet_binding_ambiguous"


# ═══════════════════════════════════════════════════════════════════════════
# 候选码集（spec task 3.3 真实端点实测暴露的缺陷）
#
# 🔴 缺陷：`resolve_sheet_wp_code` 会把底稿码换成父码（`B60-1` → `B60`，当父码
# 有自己的模板时），而生成器写的是 manifest 的 `wp_code_patterns[0]`（`B60-1`）。
# 单值等值匹配 ⇒ **已 migrated 的 binding 在运行时命中不到**。
# 真实库实测：B60 的 binding 已 migrated，端点仍返回 `sheet_binding_not_found`。
#
# 修法不是「在 resolver 里再算一次码」（那会造第二套判定，与
# `_wp_sheet_code_resolution.py` 的「必须只有一份」直接冲突），而是让调用方把
# **候选集合**传进来 —— 判定仍只有 `resolve_sheet_wp_code` 一份。
# ═══════════════════════════════════════════════════════════════════════════


_B60_ROW = {
    "entry_id": "xlsx/b60/gt-b60-bundle",
    "effective_entry_id": "xlsx/b60/gt-b60-bundle",
    "source_wp_code": "B60-1",
    "document_type": "xlsx",
    "document_scope": "single_sheet",
    "target_sheet": "B60",
    "mapping_kind": "exact",
    "status": "migrated",
    "binding_id": "sha256:b60",
}


def test_runtime_code_hits_the_binding(tmp_path: Path) -> None:
    """① 按**真实端点**的方式传候选集（运行时码 + 底稿原码）⇒ 必须命中。

    真实路径：`resolve_sheet_wp_code("B60-1", "B60", False, has_template)` 得 `B60`
    （父码有自己的模板 ⇒ 换码），而 binding 的 `source_wp_code` 是 manifest 的
    `wp_code_patterns[0]` = `B60-1`。端点把两者都传进候选集。
    """
    resolver = _resolver(tmp_path, [dict(_B60_ROW)])
    result = resolver.resolve(
        source_wp_code="B60",
        source_wp_codes=("B60", "B60-1"),
        sheet_name="B60",
        whole_workbook=False,
        manifest=_manifest("xlsx/b60/gt-b60-bundle"),
    )
    assert result.binding is not None, (
        f"候选集 (B60, B60-1) 没命中 —— reason={result.reason}"
    )
    assert result.binding["source_wp_code"] == "B60-1"
    assert result.status == "migrated"


def test_single_code_without_candidate_set_does_not_guess(tmp_path: Path) -> None:
    """①b 反向：只给运行时码、**不给**候选集 ⇒ 必须不命中（fail-closed 正确）。

    🔴 这条钉的是「resolver 不许自己猜还有哪些码可能对」：
    `_wp_sheet_code_resolution.py` 的 docstring 明写「必须只有一份」判定，
    在 resolver 里再算一次就是第二套 —— 那会让两侧协商出不同 wp_code（历史事故）。
    将来若有人为了让上面的用例过而给 resolver 加猜测，这条会打红。
    """
    resolver = _resolver(tmp_path, [dict(_B60_ROW)])
    result = resolver.resolve(
        source_wp_code="B60",
        sheet_name="B60",
        whole_workbook=False,
        manifest=_manifest("xlsx/b60/gt-b60-bundle"),
    )
    assert result.reason == "sheet_binding_not_found", (
        f"resolver 不该凭单个码猜到 B60-1（reason={result.reason}）—— "
        "候选集必须由调用方显式给出"
    )


def test_declared_code_alone_also_hits(tmp_path: Path) -> None:
    """② 只传底稿原码（`B60-1`）⇒ 也必须命中（向后兼容）。"""
    resolver = _resolver(tmp_path, [dict(_B60_ROW)])
    result = resolver.resolve(
        source_wp_code="B60-1",
        sheet_name="B60",
        whole_workbook=False,
        manifest=_manifest("xlsx/b60/gt-b60-bundle"),
    )
    assert result.reason != "sheet_binding_not_found"
    assert result.binding is not None


def test_candidate_set_does_not_match_unrelated_codes(tmp_path: Path) -> None:
    """③ 反向：候选集里没有的码不许命中（不能见谁都放行）。"""
    resolver = _resolver(tmp_path, [dict(_B60_ROW)])
    result = resolver.resolve(
        source_wp_code="Z99",
        sheet_name="B60",
        whole_workbook=False,
        manifest=_manifest("xlsx/b60/gt-b60-bundle"),
        source_wp_codes=("Z99", "Z98"),
    )
    assert result.reason == "sheet_binding_not_found", result.reason


def test_real_endpoint_passes_the_candidate_set() -> None:
    """端点必须真的传了候选集 —— 否则修了 resolver 也没用（典型假绿）。

    判据是**源码形态**（AST）：`wp_sync_router.resolve_entry_identity` 里的
    `SheetOpenBindingResolver().resolve(...)` 必须有 `source_wp_codes=` 实参。
    文本匹配会被注释/docstring 骗过（memory ㉖），所以用 AST。
    """
    import ast

    router_path = Path(__file__).resolve().parents[2] / "app/routers/wp_sync_router.py"
    tree = ast.parse(router_path.read_text(encoding="utf-8"))
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "resolve_entry_identity":
            fn = node
            break
    assert fn is not None, "wp_sync_router 里没有 resolve_entry_identity"

    calls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "resolve"
    ]
    assert calls, "resolve_entry_identity 里没有 .resolve(...) 调用"
    names = {kw.arg for c in calls for kw in c.keywords if kw.arg}
    assert "source_wp_codes" in names, (
        f"端点没传候选码集（实参 {sorted(names)}）—— resolver 修了也不会生效"
    )
