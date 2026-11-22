"""provider 型 / project-scope 的**运行时**解析守卫（从 `test_sheet_open_bindings.py` 拆出）。

拆出的理由：原文件 902 行已超 `check_file_size.py` 的 800 行上限（预存超限，本 spec 触碰后
按「抽模块不抬白名单」的纪律处理）。这里收的是「resolver 拿到一条 binding 之后怎么解析」
那一族 —— 与留在原文件的「生成器怎么产出 binding」是两件事，边界清晰。

spec: `onlyoffice-sheet-open-via-published-artifact` Phase 1.6 / 1.7 / 批 2
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver


def _write_bindings(tmp_path, rows: list[dict]):
    p = tmp_path / "bindings.json"
    p.write_text(
        json.dumps({"schema_version": "sheet-open-binding:v1", "bindings": rows}, ensure_ascii=False),
        encoding="utf-8",
    )
    return p


def _provider_manifest(entry_id: str) -> dict:
    return {"entries": [{"entry_id": entry_id, "capability": "bidirectional"}]}


def _provider_row(**over) -> dict:
    row = {
        "binding_id": "sha256:prov",
        "entry_id": "xlsx/gt-d4-operating-revenue",
        "effective_entry_id": "xlsx/gt-d4-operating-revenue",
        "mapping_kind": "provider",
        "status": "pending",
        "source_wp_code": "D4",
        "target_sheet": None,
        "document_scope": "single_sheet",
        "sheet_literals": [],
        "sheet_expressions": [':sheet-name="ooSheetName"'],
        "reason": "runtime_sheet_name_requires_provider_binding",
        "resolver_identity": "provider:70aa0edae04eb926",
        "document_type": "xlsx",
        "independent_entry": True,
    }
    row.update(over)
    return row




def test_provider_binding_resolves_with_runtime_sheet_name(tmp_path):
    """正向：provider 型能解析，且 target sheet 取**本次请求名**（不是静态值）。"""
    from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver

    path = _write_bindings(tmp_path, [_provider_row()])
    r = SheetOpenBindingResolver(path).resolve(
        source_wp_code="D4",
        sheet_name="主营业务收入明细表D4-2",
        whole_workbook=False,
        manifest=_provider_manifest("xlsx/gt-d4-operating-revenue"),
    )
    assert r.status == "pending", "没有 reviewed 审核时仍是 pending（不伪造迁移）"
    assert r.binding is not None, "provider 型必须给出 binding（否则前端拿不到 entry_id）"
    assert r.binding["entry_id"] == "xlsx/gt-d4-operating-revenue"
    assert r.binding["target_sheet"] == "主营业务收入明细表D4-2", (
        "provider 型的 target sheet 必须取本次请求名"
    )


def test_provider_binding_stays_pending_without_reviewed_status(tmp_path):
    """反向：provider 型解析出 binding ≠ 允许迁移 —— status 仍取生成物里的值。"""
    from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver

    path = _write_bindings(tmp_path, [_provider_row()])
    r = SheetOpenBindingResolver(path).resolve(
        source_wp_code="D4",
        sheet_name="任意表名",
        whole_workbook=False,
        manifest=_provider_manifest("xlsx/gt-d4-operating-revenue"),
    )
    assert r.status == "pending"
    assert r.reason == "runtime_sheet_name_requires_provider_binding"
    assert not r.is_migrated


def test_provider_binding_migrated_after_review(tmp_path):
    """审为 migrated 后，provider 型同样能进 migrated（与 exact 同一状态机）。"""
    from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver

    path = _write_bindings(
        tmp_path, [_provider_row(status="migrated", reason=None)]
    )
    r = SheetOpenBindingResolver(path).resolve(
        source_wp_code="D4",
        sheet_name="主营业务收入明细表D4-2",
        whole_workbook=False,
        manifest=_provider_manifest("xlsx/gt-d4-operating-revenue"),
    )
    assert r.status == "migrated"
    assert r.is_migrated
    assert r.binding["target_sheet"] == "主营业务收入明细表D4-2"


def test_provider_binding_rejects_empty_sheet_name(tmp_path):
    """反向：空 sheet 名不许落到 artifact 默认 sheet（那等于静默回退父级）。"""
    from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver

    path = _write_bindings(tmp_path, [_provider_row()])
    r = SheetOpenBindingResolver(path).resolve(
        source_wp_code="D4",
        sheet_name="",
        whole_workbook=False,
        manifest=_provider_manifest("xlsx/gt-d4-operating-revenue"),
    )
    assert r.status == "pending"
    assert r.reason == "sheet_binding_provider_sheet_name_missing"
    assert r.binding is None


def test_provider_binding_requires_resolver_identity(tmp_path):
    """反向：没有稳定 resolver identity ⇒ 无法审核 ⇒ 必须 pending 且不给 binding。"""
    from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver

    path = _write_bindings(tmp_path, [_provider_row(resolver_identity=None)])
    r = SheetOpenBindingResolver(path).resolve(
        source_wp_code="D4",
        sheet_name="任意表名",
        whole_workbook=False,
        manifest=_provider_manifest("xlsx/gt-d4-operating-revenue"),
    )
    assert r.status == "pending"
    assert r.reason == "sheet_binding_provider_identity_missing"
    assert r.binding is None


def test_multiple_provider_bindings_are_ambiguous(tmp_path):
    """反向：同一码族多条 provider binding ⇒ 歧义，不许挑一条。"""
    from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver

    path = _write_bindings(
        tmp_path,
        [
            _provider_row(binding_id="sha256:a"),
            _provider_row(binding_id="sha256:b", entry_id="xlsx/gt-d4-operating-revenue"),
        ],
    )
    r = SheetOpenBindingResolver(path).resolve(
        source_wp_code="D4",
        sheet_name="任意表名",
        whole_workbook=False,
        manifest=_provider_manifest("xlsx/gt-d4-operating-revenue"),
    )
    assert r.status == "pending"
    assert r.reason == "sheet_binding_ambiguous"
    assert r.binding is None


def test_provider_binding_target_sheet_not_leaked_into_static_row(tmp_path):
    """生成物是只读真源：解析不得把请求 sheet 名写回**磁盘文件**。

    🔴 该保证的**实际承担者是 `_load()`**（每次从磁盘重读并 `dict(row)` 复制），
    不是 `resolve()` 里的浅拷贝。首版我在 resolve 里重复拷了一次，导致
    「去掉拷贝」的变异存活（等价变异 —— 两层防御互相兜底，删一层仍绿）。
    现在只保留 `_load` 那一层，本用例作为**回归栅栏**：将来若给 `_load` 加缓存
    或改成返回引用，这条会打红。
    """
    import json

    from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver

    path = _write_bindings(tmp_path, [_provider_row()])
    before = path.read_bytes()

    SheetOpenBindingResolver(path).resolve(
        source_wp_code="D4",
        sheet_name="某表",
        whole_workbook=False,
        manifest=_provider_manifest("xlsx/gt-d4-operating-revenue"),
    )

    assert path.read_bytes() == before, "磁盘生成物被解析写脏了（它必须是只读真源）"
    on_disk = json.loads(before.decode("utf-8"))["bindings"][0]
    assert on_disk["target_sheet"] is None
    import json

    from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver

    path = _write_bindings(tmp_path, [_provider_row()])
    before = path.read_bytes()

    SheetOpenBindingResolver(path).resolve(
        source_wp_code="D4",
        sheet_name="某表",
        whole_workbook=False,
        manifest=_provider_manifest("xlsx/gt-d4-operating-revenue"),
    )

    assert path.read_bytes() == before, "磁盘生成物被解析写脏了（它必须是只读真源）"
    on_disk = json.loads(before.decode("utf-8"))["bindings"][0]
    assert on_disk["target_sheet"] is None

def test_project_scoped_review_only_migrates_named_project(tmp_path):
    """项目范围 review：指定项目迁移，其它项目保持 pending。"""
    from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver
    row = _provider_row(status="migrated", reason=None, reviewed={"decision":"migrated", "project_ids":["e8c40d30-de96-440d-a880-fafcf41f32f3"]})
    r = SheetOpenBindingResolver(_write_bindings(tmp_path, [row]))
    manifest = _provider_manifest("xlsx/gt-d4-operating-revenue")
    inside = r.resolve(source_wp_code="D4", sheet_name="D4", whole_workbook=False, manifest=manifest, project_id="e8c40d30-de96-440d-a880-fafcf41f32f3")
    assert inside.status == "migrated"
    outside = r.resolve(source_wp_code="D4", sheet_name="D4", whole_workbook=False, manifest=manifest, project_id="2aa00f57-1df4-4fe8-9840-2d65d0fd8749")
    assert outside.status == "pending"
    assert outside.reason == "reviewed_binding_project_not_in_scope"
    assert outside.binding["reviewed"] is None
