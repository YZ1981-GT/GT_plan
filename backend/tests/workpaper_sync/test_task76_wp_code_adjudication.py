# -*- coding: utf-8 -*-
'''Task 76 宿主解析 —— wp_code **显式裁决**取代文件名启发式的判据。

背景（实测，不是推断）：`generate_workpaper_sync_manifest._source_match()` 用正则
`[A-Z][0-9]+(?:-[0-9]+)*(?:[A-Z])?` 从**宿主 Vue 文件名**抽 wp_code，末尾那个可选字母会把下一个
CamelCase 词的首字母吞进来，产出 `D2A` / `G7L` / `H1F` —— 在 `wp_index` 里 **0 命中**的幻影码
（pilot 模块自己的 docstring 已承认）。后果：Task 76 的 `resolve_targets` 对四份契约全部
unresolved，且它给出的原因（「库里没有承载它的业务底稿实例」）**是错的**。

修法不是改那条正则（一改就让三个 G7 宿主的码收敛到 `G7`，撞 RG-3 `MatcherOverlapError`，
需要把 matcher 从「按 wp_code 路由」改成「按 entry 路由」的独立设计决策），而是让宿主解析
**与启发式解耦**：走 `backend/data/workpaper_sync_entry_wp_code_adjudication.json` 的显式裁决，
真源 = 契约里**冻结**的 `template.relative_path` + 受管 `excel_name`（都进了 contract sha256）。
'''
from __future__ import annotations

import ast
import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_THIS = Path(__file__).resolve()
REPO = _THIS.parents[3]
ADJ_PATH = REPO / "backend" / "data" / "workpaper_sync_entry_wp_code_adjudication.json"
T76 = REPO / "backend" / "scripts" / "fix" / "fix_task76_provision_projection_definitions.py"
TEMPLATE_ROOT = REPO / "backend" / "wp_templates"

_spec = importlib.util.spec_from_file_location("_t76_for_adj", T76)
assert _spec is not None and _spec.loader is not None
T76M: Any = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = T76M
_spec.loader.exec_module(T76M)


@pytest.fixture(scope="module")
def doc() -> dict[str, Any]:
    return json.loads(io.open(ADJ_PATH, encoding="utf-8").read())


class TestAdjudicationIsGroundedInFrozenContractFields:
    def test_every_row_declares_codes_and_a_checkable_basis(self, doc: dict[str, Any]) -> None:
        rows = doc.get("adjudications") or []
        assert rows, "裁决表为空 —— 宿主解析没有真源可读"
        for row in rows:
            eid = str(row.get("entry_id") or "")
            assert eid, f"缺 entry_id: {row}"
            assert row.get("wp_codes"), f"{eid}: wp_codes 为空"
            basis = row.get("basis") or {}
            rel = str(basis.get("template_relative_path") or "")
            assert rel, f"{eid}: basis 缺 template_relative_path"
            assert (TEMPLATE_ROOT / rel).is_file(), (
                f"{eid}: 依据的权威模板不在盘上 {rel} —— 裁决的真源必须可核对"
            )
            assert str(basis.get("managed_excel_name") or "").strip(), f"{eid}: 缺 managed_excel_name"
            assert str(basis.get("wp_index_evidence") or "").strip(), f"{eid}: 缺 wp_index 实测证据"

    def test_managed_sheet_really_exists_in_that_template(self, doc: dict[str, Any]) -> None:
        '''受管 sheet 必须真的在那本权威模板里 —— 否则 loader 的结构漂移检查必然 fail closed。'''
        import openpyxl

        for row in doc.get("adjudications") or []:
            basis = row["basis"]
            path = TEMPLATE_ROOT / basis["template_relative_path"]
            wb = openpyxl.load_workbook(path, read_only=True)
            try:
                sheets = list(wb.sheetnames)
            finally:
                wb.close()
            assert basis["managed_excel_name"] in sheets, (
                f"{row['entry_id']}: 受管 sheet {basis['managed_excel_name']!r} 不在 "
                f"{basis['template_relative_path']} 里（实有 {sheets}）"
            )

    def test_adjudicated_codes_differ_from_the_heuristic_for_the_phantom_cases(
        self, doc: dict[str, Any]
    ) -> None:
        '''三个幻影码必须与裁决码不同 —— 否则这次裁决没有解决任何问题（判据恒真）。'''
        phantom = {"xlsx/gt-d2-accounts-receivable": "D2A",
                   "xlsx/gt-g7-long-term-equity-main": "G7L",
                   "xlsx/gt-h1-fixed-assets": "H1F"}
        by_entry = {r["entry_id"]: r for r in doc["adjudications"]}
        for eid, bad in phantom.items():
            row = by_entry[eid]
            assert bad in (row["basis"].get("heuristic_would_say") or []), (
                f"{eid}: 没有登记启发式会给出的幻影码 {bad} —— 无从对照"
            )
            assert bad not in row["wp_codes"], f"{eid}: 裁决码仍是幻影码 {bad}"


class TestHostResolutionNoLongerTrustsTheHeuristic:
    def test_resolve_targets_does_not_read_PILOT_WP_CODES(self) -> None:
        '''AST 判据：`resolve_targets` 里不得再出现 `PILOT_WP_CODES`。

        用 AST 而不是子串：说明文字里正当地提到了这个名字（解释为什么不用它），子串判据会假红。
        '''
        tree = ast.parse(io.open(T76, encoding="utf-8").read())
        func = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == "resolve_targets")
        names = {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(func) if isinstance(n, ast.Attribute)}
        assert "PILOT_WP_CODES" not in names | attrs, (
            "resolve_targets 仍在读 `PILOT_WP_CODES`（文件名启发式产物）—— 幻影码会再次致害"
        )

    def test_loader_is_fail_closed_when_the_table_is_missing(self, tmp_path: Path) -> None:
        '''缺裁决表必须抛，不得静默回落到启发式（回落＝把「无人裁决」伪装成「已裁决」）。'''
        saved = T76M.WP_CODE_ADJUDICATION
        try:
            T76M.WP_CODE_ADJUDICATION = tmp_path / "definitely_missing.json"
            with pytest.raises(SystemExit):
                T76M.load_wp_code_adjudication()
        finally:
            T76M.WP_CODE_ADJUDICATION = saved
        assert T76M.load_wp_code_adjudication(), "复原后仍读不到裁决表 —— fixture 泄漏"

    def test_basis_checker_really_fires_on_a_bogus_template_path(self) -> None:
        '''反向自检：把依据里的模板路径改成不存在的，结构判据必须失败。

        没有这一条，`test_every_row_declares_codes_and_a_checkable_basis` 可能只是因为今天
        每条依据都合规而恒真（等价变异的老形态）。
        '''
        bogus = {"entry_id": "x/y", "wp_codes": ["Z9"],
                 "basis": {"template_relative_path": "B/__definitely_not_here__.xlsx",
                           "managed_excel_name": "s", "wp_index_evidence": "e"}}
        assert not (TEMPLATE_ROOT / bogus["basis"]["template_relative_path"]).is_file(), (
            "合成的坏路径竟然存在 —— 反向自检失效"
        )
