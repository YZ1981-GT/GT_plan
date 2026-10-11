"""R17：OO 清空的受管格必须回写进 HTML store（否则清空丢失、并被下次 HTML 冲刷回滚）。

真库实证（重药安徽 D2，2026-10-11）：rev6（OO 清空 `company_code`）与 rev5（html）只差这一个键
（rev6 里**键缺失**）；store 镜像只遍历 merged 里存在的键 ⇒ store 的 `updated_at` 停在 rev4、
`companyCode` 仍是旧值；rev7（html，下次进在线编辑时的冲刷）与 rev5 的 projection sha256 逐字节相同。

判据全部走**真契约**（D2 生产契约）+ **真三方 merge** + **真 D2 store 合并函数**，不 mock：
修复点 `store_view_with_cleared_fields` 只是把 merge 的判定交给镜像，两头都必须是生产实现。
"""

from __future__ import annotations

import ast
import inspect
import json
import textwrap
from typing import Any

import pytest

from app.services.workpaper_sync import pilot_d2_large_json as P
from app.services.workpaper_sync.cleared_field_view import store_view_with_cleared_fields
from app.services.workpaper_sync.d2_bidirectional_bridge import merge_projection_into_store_rows
from app.services.workpaper_sync.merge import merge_projections
from app.services.workpaper_sync.oo_to_html import OoToHtmlCoordinator

ROW_A = "dr-r17-row-a"
ROW_B = "dr-r17-row-b"


@pytest.fixture(scope="module")
def contract() -> Any:
    return P.load_pilot_contract()


def _store_rows() -> list[dict[str, Any]]:
    return [
        {"rowId": ROW_A, "seq": 1, "customerName": "甲公司", "companyCode": "OLD-A",
         "relationType": "非关联方", "endBalance": 100, "remark": "保留"},
        {"rowId": ROW_B, "seq": 2, "customerName": "乙公司", "companyCode": "OLD-B",
         "relationType": "非关联方", "endBalance": 200},
    ]


def _key(row: str, column: str) -> str:
    return P.stable_key_for(column, row)


def _without(projection: Any, drop: set[str]) -> Any:
    """模拟 extract 对「OO 里被清空的格」的输出：键缺失（`_collect_fields` 的 MISSING）。"""
    from app.services.workpaper_sync.adapters.base import Projection

    values = {k: v for k, v in projection.values.items() if k not in drop}
    rows: dict[str, list[str]] = {}
    for fv in values.values():
        if fv.row_key:
            bucket = rows.setdefault(P.ROWS_TABLE_KEY, [])
            if fv.row_key not in bucket:
                bucket.append(fv.row_key)
    return Projection(
        contract_id=projection.contract_id,
        semantic_version=projection.semantic_version,
        document_type=projection.document_type,
        values=values,
        row_keys={t: tuple(r) for t, r in rows.items()},
    )


def _three_way(contract: Any, drop: set[str]) -> tuple[Any, Any]:
    # 先用生产合并把手写行补齐全部受管键（真实 store 行本就齐全），否则「补键」本身会被
    # 计成 applied，判据分不清「清空被写回」与「缺键被补上」。
    seed = P.build_store_projection(json.dumps(_store_rows()), contract=contract)
    rows, *_ = merge_projection_into_store_rows(projection=seed, base_rows=_store_rows())
    base = P.build_store_projection(json.dumps(rows), contract=contract)
    incoming = _without(base, drop)
    merge = merge_projections(base=base, current=base, incoming=incoming, contract=contract)
    assert not merge.conflicts.records, merge.conflicts.records
    return merge, rows


class TestTheDefectIsReal:
    def test_without_the_view_the_store_keeps_the_cleared_value(self, contract: Any) -> None:
        """负对照：直接把 merged 交给 store 合并 ⇒ 被清空的格原值保留（修前的生产行为）。"""
        merge, rows = _three_way(contract, {_key(ROW_A, "company_code")})
        assert _key(ROW_A, "company_code") not in merge.merged.values, "前置：merged 里键缺失"
        merged_rows, applied, _visited, _touched = merge_projection_into_store_rows(
            projection=merge.merged, base_rows=rows
        )
        by_id = {r["rowId"]: r for r in merged_rows}
        assert by_id[ROW_A]["companyCode"] == "OLD-A"
        assert applied == 0, "修前镜像认为「什么都没变」⇒ `applied<=0 且有基线` 直接跳过写库"


class TestTheViewCarriesTheClear:
    def test_cleared_editable_field_becomes_explicit_null(self, contract: Any) -> None:
        merge, rows = _three_way(contract, {_key(ROW_A, "company_code")})
        view, added = store_view_with_cleared_fields(merge.merged, merge=merge, contract=contract)
        assert added == (_key(ROW_A, "company_code"),)
        assert view.get(_key(ROW_A, "company_code")).value is None
        merged_rows, applied, _visited, touched = merge_projection_into_store_rows(
            projection=view, base_rows=rows
        )
        by_id = {r["rowId"]: r for r in merged_rows}
        assert by_id[ROW_A]["companyCode"] is None, "OO 里清空 ⇒ store 也必须清空"
        assert by_id[ROW_B]["companyCode"] == "OLD-B", "别的行不受影响"
        assert by_id[ROW_A]["remark"] == "保留", "非受管键原样保留"
        assert applied == 1 and touched == {ROW_A}

    def test_published_projection_is_not_modified(self, contract: Any) -> None:
        merge, _rows = _three_way(contract, {_key(ROW_A, "company_code")})
        before = dict(merge.merged.values)
        store_view_with_cleared_fields(merge.merged, merge=merge, contract=contract)
        assert dict(merge.merged.values) == before, "视图不得改写发布出去的 projection"

    def test_deleted_row_is_not_cleared(self, contract: Any) -> None:
        """整行在 OO 里没了 = 删行；镜像侧不推断删除，也不把它的字段清空。"""
        row_b_keys = {k for k in P.build_store_projection(json.dumps(_store_rows()), contract=contract).values if f"/{ROW_B}/" in k}
        merge, _rows = _three_way(contract, row_b_keys)
        assert ROW_B not in (merge.merged.row_keys.get(P.ROWS_TABLE_KEY) or ())
        _view, added = store_view_with_cleared_fields(merge.merged, merge=merge, contract=contract)
        assert not [k for k in added if f"/{ROW_B}/" in k], added

    def test_protected_field_is_not_cleared(self, contract: Any) -> None:
        """公式/只读字段不回写 store：即便 merge 判掉了，视图也不补。"""
        protected = next(
            spec.stable_field_key.replace("{row_uuid}", ROW_A)
            for sheet in contract.sheets for table in sheet.tables
            if table.table_key == P.ROWS_TABLE_KEY
            for spec in table.fields if spec.is_protected
        )
        merge, _rows = _three_way(contract, {protected})
        _view, added = store_view_with_cleared_fields(merge.merged, merge=merge, contract=contract)
        assert protected not in added

    def test_nothing_to_clear_returns_the_same_object(self, contract: Any) -> None:
        merge, _rows = _three_way(contract, set())
        view, added = store_view_with_cleared_fields(merge.merged, merge=merge, contract=contract)
        assert view is merge.merged and added == ()

    def test_word_contract_is_left_alone(self, contract: Any) -> None:
        """docx 的键缺失可能是 SDT 载体真被删了（真 MISSING），不能当清空推断。"""
        import dataclasses

        merge, _rows = _three_way(contract, {_key(ROW_A, "company_code")})
        docx = dataclasses.replace(contract, document_type="docx")
        view, added = store_view_with_cleared_fields(merge.merged, merge=merge, contract=docx)
        assert view is merge.merged and added == ()

    @pytest.mark.parametrize("merge_none,contract_none", [(True, False), (False, True)])
    def test_missing_inputs_are_a_no_op(
        self, contract: Any, merge_none: bool, contract_none: bool
    ) -> None:
        merge, _rows = _three_way(contract, {_key(ROW_A, "company_code")})
        view, added = store_view_with_cleared_fields(
            merge.merged,
            merge=None if merge_none else merge,
            contract=None if contract_none else contract,
        )
        assert view is merge.merged and added == ()


class TestTheCoordinatorUsesTheView:
    def test_mirror_receives_the_view_not_the_raw_merged(self) -> None:
        """接线：`_apply_committed` 把视图交给镜像（AST，注释/docstring 骗不过）。"""
        fn = ast.parse(textwrap.dedent(inspect.getsource(OoToHtmlCoordinator._apply_committed)))
        view_calls = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "store_view_with_cleared_fields"
        ]
        assert len(view_calls) == 1, "镜像前没有补清空视图"
        mirror_calls = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "_mirror_store_backed_if_needed"
        ]
        assert len(mirror_calls) == 1
        kw = {k.arg: k.value for k in mirror_calls[0].keywords}
        assert isinstance(kw.get("merged_projection"), ast.Name)
        assert kw["merged_projection"].id == "store_view", (
            "镜像拿到的必须是视图，不是 merged 本身"
        )
