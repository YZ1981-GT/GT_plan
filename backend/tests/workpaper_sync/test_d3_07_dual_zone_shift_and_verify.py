# -*- coding: utf-8 -*-
"""D3-7 双区位移链实证（Task 12 · D3-7 接入验收）。

spec: d3-sync-coverage-via-row-table-engine · Task 12 · Requirements 3.3, 3.4, 6.1

═══ 为什么需要这一份 ═══

D3-7「预收账款检查表」是本 spec 第二张双区 sheet（区①本期增减变动检查 17-26 /
区②期后结转检查 31-38，共享 sheet_key `d37-managed`）。Task 11 openpyxl 已确认它**无模板缺陷**
（区①合计行 A27「合计」+ `G27=SUM(G17:G26)`/`H27=SUM(H17:H26)`、区②合计行 A39「合计」+
`G39=SUM(G31:G38)`，SUM 区间逐项覆盖全部数据行；末行 R26/R38 非 BP-21 占位行）——所以本文件
**不重复** D3-4 那条"footer 散落单格差异公式不随插行扩张"的引擎边界判据（D3-7 两区 footer 都是
标准 `SUM(range)` 冒号区间公式，会被 `assert_footer_formula_covers_managed_rows` 正确归一化，
无 D3-4 段①那种 `=B11-B13-B14-B15-B16` 散落引用漏算问题）。

本文件在真实注入产物上走**真实** `build_excel_adapter` + `adapter.materialize` +
`adapter.verify_unmanaged_regions` 完整离线管线（照抄 `test_d3_04_dual_zone_shift_and_verify.py`
的 `_synthetic_definitions` + `sibling_bindings` 范式，D4-9 双区已验证同款手法），钉住三件：

1. **Table ref 位移**：区①（本期）插行后，区②（期后）兄弟 Table 的 ref 随之整体下移。
2. **`verify_unmanaged_regions` 累积归一化**：单趟（仅区①插）与两趟（区①+区②都插）后，
   受管/非受管边界判定仍等价（`report.equivalent is True`）。
3. **`_GT_SYNC` footer 重冻结**：区①插行后 `GT_FOOTER_ROW_D37CURRENT` 按 `row_shift.count`
   下移；两区都插后 `GT_FOOTER_ROW_D37POST` 也按累积下移量重冻结（声明与物理同源）。

全程离线（不连库、不依赖 adapter 注册），沿用 Task 5/10 已确认的裁决 F5 处置原则：真栈端到端
不可测（D3 adapter 真库未注册），但支撑它的核心机制是纯函数/离线可验证。
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_extract as X
from app.services.workpaper_sync import excel_instrumentation as EI
from app.services.workpaper_sync import phase5_d3_07_voucher_check as D307
from app.services.workpaper_sync import phase5_d3_expansion as P
from app.services.workpaper_sync import phase5_d3_prepaid_receipts as ENTRY

SHEET_NAME = D307.MANAGED_SHEET_D307
UPPER = D307.SPEC_D307_CURRENT  # 区①：本期增减变动检查（数据区 17-26，footer 27）
LOWER = D307.SPEC_D307_POST  # 区②：期后结转检查（数据区 31-38，footer 39）—— 同 sheet 兄弟区


@pytest.fixture(scope="module")
def gate() -> EI.ExcelIdentityCarrierGate:
    return EI.ExcelIdentityCarrierGate.load()


@pytest.fixture(scope="module")
def all_specs() -> tuple[Any, ...]:
    """D3-7 开关打开后的完整扩容面 instrumentation 清单（真实产出，非近似结构）。"""
    return P.instrumentation_specs()


@pytest.fixture(scope="module")
def instrumented(
    all_specs: tuple[Any, ...], gate: EI.ExcelIdentityCarrierGate
) -> EI.InstrumentedWorkbook:
    return EI.instrument_workbook_bytes_multi(
        ENTRY.read_authoritative_template(), all_specs, gate=gate
    )


@pytest.fixture(scope="module")
def contract_with_d307() -> Any:
    from app.services.workpaper_sync.contracts import parse_contract

    payload = ENTRY.build_contract_payload()
    return parse_contract(payload, adapter_id=ENTRY.ADAPTER_ID)


@pytest.fixture(scope="module")
def upper_binding() -> X.ExcelIdentityBinding:
    return X.ExcelIdentityBinding(
        table_name=UPPER.table_name, uuid_column=UPPER.uuid_col, table_key=UPPER.table_key
    )


@pytest.fixture(scope="module")
def lower_binding() -> X.ExcelIdentityBinding:
    return X.ExcelIdentityBinding(
        table_name=LOWER.table_name, uuid_column=LOWER.uuid_col, table_key=LOWER.table_key
    )


def _synthetic_definitions(contract: Any) -> Any:
    """本地构造 `FrozenEntryDefinitions`（不走真库 `register_from_manifest()`），绕开 D3
    adapter 未注册阻塞（裁决 F5）。照抄 `test_d3_04_dual_zone_shift_and_verify._synthetic_
    definitions` 同款手法。
    """
    import hashlib
    import uuid

    from app.services.workpaper_sync.excel_entry_gate import (
        AdapterBuild,
        FrozenEntryDefinitions,
    )
    from app.services.workpaper_sync.models import (
        AuthorityModel,
        BundleSlot,
        BundleSlotSpec,
        DefinitionState,
    )
    from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot

    def _d(label: str) -> str:
        return hashlib.sha256(label.encode("utf-8")).hexdigest()

    def slot(kind: Any, digest: str) -> Any:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    bundle = DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("d3-07-dual-zone-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("d3-07-dual-zone-authority"),
        slots={
            BundleSlot.template: slot(BundleSlot.template, contract.template_definition_sha256),
            BundleSlot.instrumentation: slot(
                BundleSlot.instrumentation, contract.instrumentation_definition_sha256
            ),
            BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
        },
    )
    return FrozenEntryDefinitions(
        entry_id=ENTRY.ENTRY_ID,
        bundle=bundle,
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=ENTRY.ADAPTER_ID,
            adapter_build_digest=_d("d3-07-dual-zone-build"),
            document_type="xlsx",
            contract_version=contract.semantic_version,
        ),
        identity_inventory=None,  # type: ignore[arg-type]
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


def _definitions_with_inventory(
    contract: Any, instrumented: EI.InstrumentedWorkbook
) -> Any:
    """把区①的 identity_inventory 注入 `_synthetic_definitions`（materialize 前置）。"""
    from app.services.excel_structure_fingerprint import identity_inventory
    from app.services.workpaper_sync.excel_entry_gate import parse_identity_inventory

    base = _synthetic_definitions(contract)
    inv_raw = identity_inventory(
        instrumented.instrumented_bytes,
        expected_table=str(UPPER.table_name),
        uuid_column_letter=str(UPPER.uuid_col),
    )
    return base.__class__(
        entry_id=base.entry_id,
        bundle=base.bundle,
        contract=base.contract,
        adapter_build=base.adapter_build,
        identity_inventory=parse_identity_inventory(inv_raw),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


class TestPremiseD307IsRegisteredAsDualZone:
    """前提确认：D3-7 双区已通过灰度开关真实接入且共享同一 sheet_key（同 D4-9/D3-4 范式）。"""

    def test_two_specs_share_managed_sheet(self) -> None:
        assert UPPER.managed_sheet == LOWER.managed_sheet == SHEET_NAME
        assert UPPER.sheet_key == LOWER.sheet_key == "d37-managed", (
            "双区应共享 sheet_key（Task 11 声明裁决）"
        )
        # 区①在区②之上（数据区 17-26 vs 31-38）—— 位移发生在下方兄弟区上方是复现前提。
        assert int(UPPER.last_data_row) < int(LOWER.first_data_row), (
            f"区①末行 {UPPER.last_data_row} 应在区②首行 {LOWER.first_data_row} 之上"
        )

    def test_appears_in_sibling_shift_parametrized_coverage(self) -> None:
        """D3-7 应自动出现在上游 D1 spec Task 24 参数化后的位移判据覆盖清单里
        （`test_sibling_table_ref_row_shift.py::test_all_multi_region_sheets_shift_sibling_
        table_refs` 的参数化来源 `_multi_region_sheets()`）—— 不重复造判定逻辑，只确认接线。"""
        sys.path.insert(0, str(_BACKEND / "tests" / "workpaper_sync"))
        try:
            from test_sibling_table_ref_row_shift import _multi_region_sheets
        finally:
            sys.path.remove(str(_BACKEND / "tests" / "workpaper_sync"))
        multi = _multi_region_sheets()
        assert SHEET_NAME in multi, (
            f"D3-7 应已自动进入同 sheet 多受管区参数化清单（D3-7 开关已开、共享 d37-managed），"
            f"实得 {sorted(multi)}"
        )
        assert len(multi[SHEET_NAME]) == 2, (
            f"D3-7 应恰 2 个受管区，实得 {len(multi[SHEET_NAME])}"
        )


class TestBothFootersAreStandardSumRange:
    """对照确认：D3-7 两区 footer 都是标准 `SUM(range)` 冒号区间公式（无 D3-4 段①那种散落
    单格差异公式漏算问题）—— 所以本文件不重复 D3-4 的"区间不扩张"引擎边界判据。"""

    def _sheet_xml(self, instrumented: EI.InstrumentedWorkbook) -> str:
        with zipfile.ZipFile(io.BytesIO(instrumented.instrumented_bytes)) as zf:
            part = X._sheet_parts(zf).get(SHEET_NAME)
            assert part, f"定位不到 {SHEET_NAME}"
            return zf.read(part).decode("utf-8")

    def test_current_footer_is_sum_range(self, instrumented: EI.InstrumentedWorkbook) -> None:
        import re

        xml = self._sheet_xml(instrumented)
        # 区①合计行 G27/H27 都是 SUM(冒号区间) —— 会被 footer 归一化正确扩张，不漏算。
        for coord, rng in (("G27", "G17:G26"), ("H27", "H17:H26")):
            m = re.search(rf'<c r="{coord}"[^>]*>(?:(?!</c>).)*?<f[^>]*>([^<]*)</f>', xml, re.S)
            assert m and f"SUM({rng}" in m.group(1).upper().replace(" ", ""), (
                f"区① {coord} 应为 SUM({rng})，实得 {m.group(1) if m else None!r}"
            )

    def test_post_footer_is_sum_range(self, instrumented: EI.InstrumentedWorkbook) -> None:
        import re

        xml = self._sheet_xml(instrumented)
        m = re.search(r'<c r="G39"[^>]*>(?:(?!</c>).)*?<f[^>]*>([^<]*)</f>', xml, re.S)
        assert m and "SUM(G31:G38" in m.group(1).upper().replace(" ", ""), (
            f"区② G39 应为 SUM(G31:G38)，实得 {m.group(1) if m else None!r}"
        )


class TestUpperZoneInsertionShiftsSiblingAndVerifyPasses:
    """单趟：区①（本期）插 5 行后，区②（期后）兄弟 Table ref 随之下移，且真实 adapter 管线的
    `verify_unmanaged_regions` 仍判等价（含 sheet 内比例检查块 41-44 等非 binding 区域）。
    """

    def test_upper_insertion_shifts_sibling_table_ref_and_verify_still_passes(
        self,
        instrumented: EI.InstrumentedWorkbook,
        contract_with_d307: Any,
        upper_binding: X.ExcelIdentityBinding,
        lower_binding: X.ExcelIdentityBinding,
        tmp_path: Path,
    ) -> None:
        from app.services.workpaper_sync.adapters.excel import build_excel_adapter
        from app.services.workpaper_sync.phase5_row_table_sheet import build_store_projection

        base_path = tmp_path / "d307-base.xlsx"
        base_path.write_bytes(instrumented.instrumented_bytes)

        definitions = _definitions_with_inventory(contract_with_d307, instrumented)
        adapter = build_excel_adapter(
            definitions=definitions,
            binding=upper_binding,
            direction="html_to_oo",
            sibling_bindings=(lower_binding,),
        )

        # 🔴 区① 插 **5 行**（任务原文口径「单趟区①插 5 行」）：10 行模板 → 15 行 ⇒ 触发
        #    结构性插行。避开区①插行数恰 == 2 的 footer/组标题撞行引擎边界（见本文件
        #    `TestKnownEngineBoundaryFooterHeaderCollision`）。
        derived_rows = [
            {
                "rowId": f"vc-current-p{i}",
                "customerName": f"客户{i}",
                "voucherDate": "2025-06-30",
                "voucherNo": f"记-{i}",
                "businessContent": "预收货款",
                "counterAccount": "1122",
                "counterSubAccount": "明细",
                "debitAmount": 100.0 + i,
                "creditAmount": 0.0,
                "supportingDoc": "合同",
                "check1": "√", "check2": "√", "check3": "√", "check4": "", "check5": "",
                "indexNo": f"D3-7-{i}", "isAbnormal": "否", "remark": "",
            }
            for i in range(15)  # 10 行占位 → 15 ⇒ 必插行（区①插 5 行）
        ]
        proj = build_store_projection(UPPER, derived_rows, contract=contract_with_d307)

        before = _table_ref(base_path, str(LOWER.table_name))
        staged = tmp_path / ".staging" / "d307-verify.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path, projection=proj, output=staged, contract=contract_with_d307
        )
        assert staged.is_file() and staged.read_bytes()[:2] == b"PK"

        row_shift = getattr(result, "row_shift", None)
        assert row_shift is not None and int(row_shift.count) > 0, (
            f"区①派生 12 行 > 模板占位 ⇒ 应真实插行，实得 row_shift={row_shift!r}"
        )
        inserted = int(row_shift.count)

        # 区②（兄弟区）Table ref 随之整体下移 inserted 行。
        after = _table_ref(staged, str(LOWER.table_name))
        b_head, b_tail = _ref_rows(before)
        a_head, a_tail = _ref_rows(after)
        assert (a_head, a_tail) == (b_head + inserted, b_tail + inserted), (
            f"区②兄弟 Table ref 没随区①插行下移：{before} → {after}"
            f"（插了 {inserted} 行，应为 {b_head + inserted}..{b_tail + inserted}）"
        )

        report = adapter.verify_unmanaged_regions(
            before=base_path,
            after=staged,
            contract=contract_with_d307,
            row_shift=getattr(result, "row_shift", None),
            total_formula_rows=getattr(result, "total_formula_rows", ()) or (),
            propagation=getattr(result, "workbook_row_change", None),
            per_table_shift=getattr(result, "per_table_shift", None),
        )
        assert report.equivalent is True, (
            f"区①插行后，真实 adapter 管线的 verify_unmanaged_regions 应判等价，"
            f"实得差异：{report.details}"
        )


class TestCumulativeTwoPassInsertionStillVerifies:
    """两趟：区①+区②都插行 —— 复现 D4-9/D3-4 的 `CompositeRowShift` 累积归一化场景
    （同 sheet 两区都插才需要累积归一化），走真实 `adapters/excel._sheet_cumulative_shift`
    链式路径（`adapter.materialize()` 单次调用完成两个 binding 各自的插行判定）。
    """

    def test_two_pass_insertion_still_verifies_correctly(
        self,
        instrumented: EI.InstrumentedWorkbook,
        contract_with_d307: Any,
        upper_binding: X.ExcelIdentityBinding,
        lower_binding: X.ExcelIdentityBinding,
        tmp_path: Path,
    ) -> None:
        from app.services.workpaper_sync.adapters.base import Projection
        from app.services.workpaper_sync.adapters.excel import build_excel_adapter
        from app.services.workpaper_sync.phase5_row_table_sheet import build_store_projection

        base_path = tmp_path / "d307-base2.xlsx"
        base_path.write_bytes(instrumented.instrumented_bytes)

        definitions = _definitions_with_inventory(contract_with_d307, instrumented)
        adapter = build_excel_adapter(
            definitions=definitions,
            binding=upper_binding,
            direction="html_to_oo",
            sibling_bindings=(lower_binding,),
        )

        # 🔴 两区各插 **5 行**（任务原文口径「两趟各插 5 行」）：区① 10 行模板 → 15 行、
        #    区② 8 行模板 → 13 行。两区都超模板占位 ⇒ 两趟都插行（累积归一化复现前提）。
        #    行数刻意避开区①插行数恰 == 2（footer 27→29 撞区②组标题行 29）的引擎边界——
        #    该边界已由本文件 `TestKnownEngineBoundaryFooterHeaderCollision` 单独登记（不修）。
        upper_rows = [
            {
                "rowId": f"vc-current-{i}", "customerName": f"本期{i}", "voucherDate": "2025-06-30",
                "voucherNo": f"记-{i}", "businessContent": "预收", "counterAccount": "1122",
                "counterSubAccount": "明细", "debitAmount": 100.0 + i, "creditAmount": 0.0,
                "supportingDoc": "合同", "check1": "√", "check2": "", "check3": "", "check4": "",
                "check5": "", "indexNo": f"C-{i}", "isAbnormal": "否", "remark": "",
            }
            for i in range(15)
        ]
        lower_rows = [
            {
                "rowId": f"vc-post-{i}", "customerName": f"期后{i}", "voucherDate": "2025-07-15",
                "voucherNo": f"结-{i}", "businessContent": "结转", "counterAccount": "6001",
                "counterSubAccount": "明细", "creditAmount": 200.0 + i, "supportingDoc": "发票",
                "check1": "√", "check2": "", "check3": "", "check4": "", "check5": "",
                "indexNo": f"P-{i}", "isAbnormal": "否", "remark": "",
            }
            for i in range(13)
        ]
        proj_upper = build_store_projection(UPPER, upper_rows, contract=contract_with_d307)
        proj_lower = build_store_projection(LOWER, lower_rows, contract=contract_with_d307)
        combined = Projection(
            contract_id=proj_upper.contract_id,
            semantic_version=proj_upper.semantic_version,
            document_type=proj_upper.document_type,
            values={**proj_upper.values, **proj_lower.values},
            row_keys={**proj_upper.row_keys, **proj_lower.row_keys},
        )

        staged = tmp_path / ".staging" / "d307-cumulative.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path, projection=combined, output=staged, contract=contract_with_d307
        )
        assert staged.is_file()

        pts = getattr(result, "per_table_shift", None)
        assert pts, f"两区都插行 ⇒ per_table_shift 应带出两条声明，实得 {pts!r}"
        assert str(UPPER.table_key) in pts and str(LOWER.table_key) in pts, (
            f"两趟位移声明应都存在（累积场景复现前提），实得 {sorted(pts)}"
        )

        report = adapter.verify_unmanaged_regions(
            before=base_path,
            after=staged,
            contract=contract_with_d307,
            row_shift=getattr(result, "row_shift", None),
            total_formula_rows=getattr(result, "total_formula_rows", ()) or (),
            propagation=getattr(result, "workbook_row_change", None),
            per_table_shift=pts,
        )
        assert report.equivalent is True, (
            f"两趟累积插行（区①+区②）后，累积归一化（CompositeRowShift）应仍正确判定"
            f"受管/非受管边界，实得差异：{report.details}"
        )


class TestGtSyncFooterRowsReFrozenAfterInsertion:
    """`_GT_SYNC` 的 `GT_FOOTER_ROW_D37CURRENT` / `GT_FOOTER_ROW_D37POST` 应按插行数重冻结
    （声明与物理同源，同 D3-4 `TestGtSyncFooterRowReFrozenAfterD34DebitInsertion` 范式）。

    读产物隐藏 `_GT_SYNC` sheet 走唯一读侧入口 `read_runtime_binding_pairs`（不手搓第二份）。
    """

    def test_current_footer_row_key_shifts_by_inserted_count(
        self,
        instrumented: EI.InstrumentedWorkbook,
        contract_with_d307: Any,
        upper_binding: X.ExcelIdentityBinding,
        lower_binding: X.ExcelIdentityBinding,
        tmp_path: Path,
    ) -> None:
        from app.services.workpaper_sync.adapters.excel import build_excel_adapter
        from app.services.workpaper_sync.phase5_row_table_sheet import build_store_projection

        footer_key = f"GT_FOOTER_ROW_{UPPER.template_id}"  # GT_FOOTER_ROW_D37CURRENT

        base_path = tmp_path / "d307-gtsync-base.xlsx"
        base_path.write_bytes(instrumented.instrumented_bytes)

        with zipfile.ZipFile(base_path) as zf:
            before_pairs = X.read_runtime_binding_pairs(zf)
        assert footer_key in before_pairs, (
            f"前提不成立：`_GT_SYNC` 无 {footer_key}，实得 "
            f"{[k for k in before_pairs if k.startswith('GT_FOOTER_ROW')]}"
        )
        footer_before = int(before_pairs[footer_key])
        assert footer_before == int(UPPER.footer_row), (
            f"{footer_key} 冻结值应 == 区① footer 行 {UPPER.footer_row}，实得 {footer_before}"
        )

        definitions = _definitions_with_inventory(contract_with_d307, instrumented)
        adapter = build_excel_adapter(
            definitions=definitions, binding=upper_binding, direction="html_to_oo",
            sibling_bindings=(lower_binding,),
        )

        rows = [
            {
                "rowId": f"vc-current-{i}", "customerName": f"客户{i}", "voucherDate": "2025-06-30",
                "voucherNo": f"记-{i}", "businessContent": "预收", "counterAccount": "1122",
                "counterSubAccount": "明细", "debitAmount": 100.0 + i, "creditAmount": 0.0,
                "supportingDoc": "合同", "check1": "√", "check2": "", "check3": "", "check4": "",
                "check5": "", "indexNo": f"C-{i}", "isAbnormal": "否", "remark": "",
            }
            for i in range(15)  # 区①插 5 行（避开 footer/组标题撞行边界）
        ]
        proj = build_store_projection(UPPER, rows, contract=contract_with_d307)
        staged = tmp_path / ".staging" / "d307-gtsync.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path, projection=proj, output=staged, contract=contract_with_d307
        )
        row_shift = getattr(result, "row_shift", None)
        assert row_shift is not None, "区①插行 ⇒ result.row_shift 应非空"
        inserted = int(row_shift.count)
        assert inserted > 0, f"应真实插行，实得 count={inserted}"

        with zipfile.ZipFile(staged) as zf:
            after_pairs = X.read_runtime_binding_pairs(zf)
        footer_after = int(after_pairs[footer_key])
        assert footer_after == footer_before + inserted, (
            f"{footer_key} 应从 {footer_before} 重冻结为 {footer_before + inserted}"
            f"（下移 {inserted} = row_shift.count），实得 {footer_after} —— "
            "`_GT_SYNC` footer 坐标未与物理插行同源"
        )

        # 区②（下方兄弟区）footer 冻结坐标也应随区①插行整体下移（声明与物理同源）。
        post_key = f"GT_FOOTER_ROW_{LOWER.template_id}"  # GT_FOOTER_ROW_D37POST
        if post_key in before_pairs:
            post_before = int(before_pairs[post_key])
            assert int(after_pairs[post_key]) == post_before + inserted, (
                f"{post_key} 应随区①插行从 {post_before} 下移到 {post_before + inserted}，"
                f"实得 {after_pairs[post_key]}"
            )


class TestFullBookSevenRegionMaterialize:
    """整册 **7 个受管区**（D3-2 primary + D3-6 / D3-4借 / D3-4贷 / D3-5 / D3-7区① / D3-7区②
    全 sibling）一次 materialize + verify equivalent。

    Task 12：D3-7 接入后，D3 entry 的完整受管面从 5 区扩到 7 区。本判据把 D3-7 两区加进
    Task 10 §9 建立的整册 materialize 链路（照抄 `test_d3_04_dual_zone_shift_and_verify.py`
    的 `TestFullBookMaterializeAfterTemplateFooterFix` 范式），走真实 `build_excel_adapter` +
    `adapter.materialize` + `adapter.verify_unmanaged_regions` 完整离线管线。

    🔴 每区行数刻意避开 D3-7 区①插行数恰 == 2 的引擎撞行边界（区①给 15 行 = 模板 10 + 插 5）。
    真栈端到端仍受 adapter capability 限制不可测（裁决 F5，tasks.md 标 `[ ]*`）。
    """

    def test_all_seven_managed_regions_materialize_and_verify_equivalent(
        self,
        gate: EI.ExcelIdentityCarrierGate,
        contract_with_d307: Any,
        tmp_path: Path,
    ) -> None:
        from app.services.excel_structure_fingerprint import identity_inventory
        from app.services.workpaper_sync import phase5_d3_04_analysis as D304
        from app.services.workpaper_sync import phase5_d3_05_long_term as D305
        from app.services.workpaper_sync import phase5_d3_06_related_party as D306
        from app.services.workpaper_sync.adapters.base import Projection
        from app.services.workpaper_sync.adapters.excel import build_excel_adapter
        from app.services.workpaper_sync.excel_entry_gate import parse_identity_inventory
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            build_store_projection,
            managed_field_specs,
        )

        # 整册 substrate = [D3-2 单数声明] + 扩容面全部 6 个（D3-6/D3-4借/D3-4贷/D3-5/
        # D3-7区①/D3-7区②）——同 test_d3_04 §9 手法。`P.instrumentation_specs()` 现含 D3-7 两区。
        full_specs = (ENTRY.instrumentation_spec(),) + tuple(P.instrumentation_specs())
        instrumented = EI.instrument_workbook_bytes_multi(
            ENTRY.read_authoritative_template(), full_specs, gate=gate
        )

        primary_binding = X.ExcelIdentityBinding(
            table_name=ENTRY.TABLE_NAME, uuid_column=ENTRY.UUID_COL,
            table_key=ENTRY.ROWS_TABLE_KEY,
        )
        # siblings 按 Excel 行序：D3-6 / D3-4借 / D3-4贷 / D3-5 / D3-7区① / D3-7区②。
        sibling_specs = (
            D306.SPEC_D306,
            D304.SPEC_D304_DEBIT,
            D304.SPEC_D304_CREDIT,
            D305.SPEC_D305,
            UPPER,
            LOWER,
        )
        sibling_bindings = tuple(
            X.ExcelIdentityBinding(
                table_name=s.table_name, uuid_column=s.uuid_col, table_key=s.table_key
            )
            for s in sibling_specs
        )

        base_path = tmp_path / "d3-fullbook7-base.xlsx"
        base_path.write_bytes(instrumented.instrumented_bytes)

        definitions = _definitions_with_inventory(contract_with_d307, instrumented)
        # 🔴 identity_inventory 用 primary（D3-2）表——整册 substrate 必须含 D3-2 的 Table。
        base = definitions
        inv_raw = identity_inventory(
            instrumented.instrumented_bytes,
            expected_table=str(ENTRY.TABLE_NAME),
            uuid_column_letter=str(ENTRY.UUID_COL),
        )
        definitions = base.__class__(
            entry_id=base.entry_id, bundle=base.bundle, contract=base.contract,
            adapter_build=base.adapter_build,
            identity_inventory=parse_identity_inventory(inv_raw),
            business_sheets=(), dynamic_column_keys={}, structure_inventory_size=0,
        )

        adapter = build_excel_adapter(
            definitions=definitions,
            binding=primary_binding,
            direction="html_to_oo",
            sibling_bindings=sibling_bindings,
        )

        def _generic_rows(spec: Any, tag: str, n: int) -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for i in range(n):
                row: dict[str, Any] = {spec.row_identity_key: f"{tag}-{i}"}
                for _ck, _col, _mode, value_type, json_key, _label, _grp in managed_field_specs(spec):
                    if "/" in json_key:
                        continue
                    row[json_key] = (
                        (100.0 + i) if value_type in ("number", "amount") else f"{tag}{_ck}{i}"
                    )
                rows.append(row)
            return rows

        # D3-2/D3-6/D3-4借/D3-4贷/D3-5 各 5 行（模板占位小 ⇒ 触发插行，同 §9）；
        # 🔴 D3-7 区①给 5 行（模板 10 行 ⇒ **不插行**）、区②给 13 行（模板 8 + 插 5 ⇒ 插行）。
        #    为什么区①不给插行：整册场景（primary=D3-2、D3-7 两区为 sibling）下，**区①作为
        #    非主 sibling 插行**会触发引擎累积归一化边界（见本文件
        #    `TestKnownEngineBoundaryFooterHeaderCollision` §整册补充实测：full-book 下 cur≥15
        #    即 DRIFT、cur=5/post=13 ✅、cur=5/post=5 ✅）——那是与本任务同源的上游引擎边界，
        #    登记不修。本判据要的是「7 个受管区一次 materialize + verify equivalent」，用「区①
        #    present-no-insert + 区②真插行 + 其余五区真插行」即可覆盖全部 7 区的 materialize 与
        #    verify 归一化，不必让每一区都插行（插行归一化边界另有专jud据钉）。
        d32_spec = ENTRY.SPEC_D32
        values: dict[str, Any] = {}
        row_keys: dict[str, Any] = {}
        for spec, tag, n in (
            (d32_spec, "d32", 5),
            (D306.SPEC_D306, "d36", 5),
            (D304.SPEC_D304_DEBIT, "d34dr", 5),
            (D304.SPEC_D304_CREDIT, "d34cr", 5),
            (D305.SPEC_D305, "d35", 5),
            (UPPER, "d37cur", 5),
            (LOWER, "d37post", 13),
        ):
            proj = build_store_projection(spec, _generic_rows(spec, tag, n), contract=contract_with_d307)
            values.update(proj.values)
            row_keys.update(proj.row_keys)

        combined = Projection(
            contract_id=contract_with_d307.contract_id,
            semantic_version=contract_with_d307.semantic_version,
            document_type=contract_with_d307.document_type,
            values=values,
            row_keys=row_keys,
        )

        staged = tmp_path / ".staging" / "d3-fullbook7.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path, projection=combined, output=staged, contract=contract_with_d307
        )
        assert staged.is_file() and staged.read_bytes()[:2] == b"PK", (
            "整册 7 区 materialize 应产出 staged 工作簿"
        )

        # 7 个受管区的字段都进了 projection（materialize 覆盖全部 7 区，非只前 5 区）。
        for spec in (d32_spec, D306.SPEC_D306, D304.SPEC_D304_DEBIT, D304.SPEC_D304_CREDIT,
                     D305.SPEC_D305, UPPER, LOWER):
            assert any(str(spec.table_key) in k for k in combined.row_keys), (
                f"整册 projection 缺 {spec.table_key} 的行 —— 未覆盖全部 7 区"
            )

        pts = getattr(result, "per_table_shift", None)
        assert pts, f"整册插行 ⇒ per_table_shift 应非空，实得 {pts!r}"
        # D3-7 区②插了 5 行 ⇒ 其位移声明应在（区①不插行故不必在）。
        assert str(LOWER.table_key) in pts, (
            f"D3-7 区②位移声明应在整册 per_table_shift 里，实得 {sorted(pts)}"
        )

        report = adapter.verify_unmanaged_regions(
            before=base_path,
            after=staged,
            contract=contract_with_d307,
            row_shift=getattr(result, "row_shift", None),
            total_formula_rows=getattr(result, "total_formula_rows", ()) or (),
            propagation=getattr(result, "workbook_row_change", None),
            per_table_shift=pts,
        )
        assert report.equivalent is True, (
            "D3-7 接入后，D3 整册 7 区 materialize（D3-2 primary + D3-6/D3-4借/D3-4贷/D3-5/"
            f"D3-7区①/D3-7区② 全 sibling）的 verify_unmanaged_regions 应判等价，实得：{report.details}"
        )


class TestEngineLayerTimingBaseline:
    """D3-7 两 spec 的引擎层耗时基线（`build_store_projection`，1/10/50 行）。

    🔴 引擎层非真栈（同 Task 5/10 口径）：只测「provider 把 store payload 现算成 projection」
    这一段纯函数耗时，不含 HTTP / registration / materialize 写盘 / OnlyOffice room——真栈
    端到端耗时受 D3 adapter 未注册阻塞（裁决 F5），tasks.md 标 `[ ]*`。本判据只登记耗时数量级，
    不设硬阈值（需求 6.1「脚本现测、不手抄」；软上限门在 Task 5 已立）。
    """

    @pytest.mark.parametrize("n_rows", [1, 10, 50])
    @pytest.mark.parametrize(
        "spec_label", ["D3-vc-current-rows", "D3-vc-post-rows"]
    )
    def test_build_store_projection_engine_layer_baseline(
        self, contract_with_d307: Any, n_rows: int, spec_label: str
    ) -> None:
        import time

        from app.services.workpaper_sync.phase5_row_table_sheet import (
            build_store_projection,
            managed_field_specs,
        )

        spec = UPPER if spec_label == "D3-vc-current-rows" else LOWER
        rows: list[dict[str, Any]] = []
        for i in range(n_rows):
            row: dict[str, Any] = {spec.row_identity_key: f"{spec_label}-{i:06d}"}
            for _ck, _col, _mode, value_type, json_key, _label, _grp in managed_field_specs(spec):
                if "/" in json_key:
                    continue
                row[json_key] = (100.0 + i) if value_type in ("number", "amount") else f"v{_ck}{i}"
            rows.append(row)

        started = time.perf_counter()
        projection = build_store_projection(spec, rows, contract=contract_with_d307)
        elapsed_ms = (time.perf_counter() - started) * 1000
        field_count = len(projection.values)
        print(
            f"\n[engine-layer-timing] {spec_label} n_rows={n_rows} "
            f"store_field_count={field_count} elapsed_ms={elapsed_ms:.3f}（引擎层非真栈）"
        )
        assert field_count > 0, "合成 payload 非空时投影不得为空"


class TestKnownEngineBoundaryFooterHeaderCollision:
    """🔴 登记（不修）：区①插行数**恰为 2**（footer 27→29 撞区②组标题行 29）时，两趟累积
    归一化对 sheet 尾部非受管区（比例检查块 41-44 + note/conclusion）的 unshift misalign，
    `verify_unmanaged_regions` 判 `managed_sheet_unmanaged_cells` 漂移。

    ═══ 边界刻画（本任务实测扫描）═══

    区① 模板数据区 17-26（10 行）、footer 27；区② 组标题行 29 / 数据区 31-38、footer 39。
    对"区①派生 N 行"逐值实测两趟累积（区②同步插行）后的 verify 结论：
        N=11(插1) ✅  N=13(插3) ✅  N=14(插4) ✅  N=15(插5) ✅  N=16(插6) ✅
        N=12(插2) ❌  —— 且与区②插行数无关（区② +3 / +4 都同样 ❌）
    ⇒ 触发条件精确锁定在「区①插 2 行 ⇒ 区① footer 从 27 位移到 29 == 区②组标题行 29」这一
       footer/header 撞行的临界点。插 1 行（footer→28）或插 ≥3 行（footer→≥30 越过组标题）
       都不触发。

    ═══ 整册（primary=D3-2、D3-7 两区为 sibling）下的第二个表现 ═══

    本任务整册 7 区 materialize 实测另发现同族边界的另一表现：当 D3-7 **作为非主 sibling**
    时，只要**区①（上区）插任意行**（full-book cur=15/16/14 均 DRIFT），累积归一化对同 sheet
    尾部非受管区就 misalign；而**区②（下区）单独插行**（cur=5/post=13）或**两区都不插**
    （cur=5/post=5）都 ✅。与孤立场景（primary=D3-7-current，+5/+5 通过）表现不同——说明
    misalign 与「插行的那一区是不是主 binding + 是不是上区」相关，根仍在
    `_sheet_cumulative_shift` 对同 sheet 多区在**非主 sheet** 上的位移合并。整册验收判据
    `TestFullBookSevenRegionMaterialize` 因此让区①present-no-insert、区②真插行来覆盖 7 区
    verify equivalent；区①作为 sibling 插行的这条边界由下方 `test_fullbook_region1_sibling_
    insertion_hits_boundary` 单独 xfail 钉住。

    ═══ 归因：引擎层累积归一化的边界，非本 spec 声明缺陷 ═══

    这与 D3-4 §7「footer 散落单格差异公式区间不扩张」同类——都是**上游行表引擎**
    （`adapters/excel._sheet_cumulative_shift` / `CompositeRowShift` / footer 归一化）在特定
    位移几何下的真实边界。D3-7 声明层（`phase5_d3_07_voucher_check`）的几何、字段、footer
    marker 全部实测正确（Task 11 openpyxl 复核），无法通过改声明规避——footer 落在哪一行由
    真实插行数决定，不是声明可控的。修复须动引擎累积归一化逻辑（`_sheet_cumulative_shift`
    的 footer/header 撞行处理），blast radius 覆盖全平台同 sheet 多受管区 sheet，跨 lane，
    超出本 spec（纯声明层）范围。按 Task 10 §7 已确立的处置原则「引擎边界登记不修、如实暴露、
    不代为规避」：本判据钉住该边界为 `xfail(strict=True)`（引擎修复后会自动转正、提醒摘除标记），
    生产后果 = 若某项目区① 恰好从模板 10 行增到 12 行（+2），整册 materialize 的 verify 会
    fail-closed 报 `adapter_unmanaged_region_drift`（**不是静默错数据**，是显式拒绝 + 500），
    审计人可退一步重试或等引擎修复；正常接入路径（+5/+5 等）不受影响。
    """

    @pytest.mark.xfail(
        strict=True,
        reason="上游引擎累积归一化在『区①插2行使footer27→撞区②组标题行29』临界点 misalign；"
        "非D3-7声明缺陷，登记不修（同D3-4 §7引擎边界处置），修复须动 _sheet_cumulative_shift 跨lane",
    )
    def test_region1_insert_exactly_two_rows_hits_footer_header_collision_boundary(
        self,
        instrumented: EI.InstrumentedWorkbook,
        contract_with_d307: Any,
        upper_binding: X.ExcelIdentityBinding,
        lower_binding: X.ExcelIdentityBinding,
        tmp_path: Path,
    ) -> None:
        from app.services.workpaper_sync.adapters.base import Projection
        from app.services.workpaper_sync.adapters.excel import build_excel_adapter
        from app.services.workpaper_sync.phase5_row_table_sheet import build_store_projection

        base_path = tmp_path / "d307-boundary-base.xlsx"
        base_path.write_bytes(instrumented.instrumented_bytes)
        definitions = _definitions_with_inventory(contract_with_d307, instrumented)
        adapter = build_excel_adapter(
            definitions=definitions, binding=upper_binding, direction="html_to_oo",
            sibling_bindings=(lower_binding,),
        )

        # 区① 12 行（10 模板 + 插 2）⇒ footer 27→29 撞区②组标题行 29；区② 10 行同步插。
        upper_rows = [
            {
                "rowId": f"vc-current-{i}", "customerName": f"本期{i}", "voucherDate": "2025-06-30",
                "voucherNo": f"记-{i}", "businessContent": "预收", "counterAccount": "1122",
                "counterSubAccount": "明细", "debitAmount": 100.0 + i, "creditAmount": 0.0,
                "supportingDoc": "合同", "check1": "√", "check2": "", "check3": "", "check4": "",
                "check5": "", "indexNo": f"C-{i}", "isAbnormal": "否", "remark": "",
            }
            for i in range(12)
        ]
        lower_rows = [
            {
                "rowId": f"vc-post-{i}", "customerName": f"期后{i}", "voucherDate": "2025-07-15",
                "voucherNo": f"结-{i}", "businessContent": "结转", "counterAccount": "6001",
                "counterSubAccount": "明细", "creditAmount": 200.0 + i, "supportingDoc": "发票",
                "check1": "√", "check2": "", "check3": "", "check4": "", "check5": "",
                "indexNo": f"P-{i}", "isAbnormal": "否", "remark": "",
            }
            for i in range(10)
        ]
        proj_upper = build_store_projection(UPPER, upper_rows, contract=contract_with_d307)
        proj_lower = build_store_projection(LOWER, lower_rows, contract=contract_with_d307)
        combined = Projection(
            contract_id=proj_upper.contract_id,
            semantic_version=proj_upper.semantic_version,
            document_type=proj_upper.document_type,
            values={**proj_upper.values, **proj_lower.values},
            row_keys={**proj_upper.row_keys, **proj_lower.row_keys},
        )
        staged = tmp_path / ".staging" / "d307-boundary.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path, projection=combined, output=staged, contract=contract_with_d307
        )
        report = adapter.verify_unmanaged_regions(
            before=base_path,
            after=staged,
            contract=contract_with_d307,
            row_shift=getattr(result, "row_shift", None),
            total_formula_rows=getattr(result, "total_formula_rows", ()) or (),
            propagation=getattr(result, "workbook_row_change", None),
            per_table_shift=getattr(result, "per_table_shift", None),
        )
        # xfail：引擎修复该边界后此断言会成立 → strict xfail 转红提醒摘除标记。
        assert report.equivalent is True, (
            "区①插 2 行（footer 27→撞区②组标题 29）的累积归一化边界已修复——请摘除 xfail 标记"
        )

    @pytest.mark.xfail(
        strict=True,
        reason="整册（primary=D3-2、D3-7为sibling）下区①作为非主sibling插任意行触发累积归一化"
        "misalign；非D3-7声明缺陷，登记不修（同上边界，根在 _sheet_cumulative_shift 跨lane）",
    )
    def test_fullbook_region1_sibling_insertion_hits_boundary(
        self,
        gate: EI.ExcelIdentityCarrierGate,
        contract_with_d307: Any,
        tmp_path: Path,
    ) -> None:
        """整册场景（primary=D3-2）下 D3-7 区①作为 sibling 插 5 行 ⇒ 引擎累积归一化边界。

        与 `TestFullBookSevenRegionMaterialize` 的区别只有一处：这里区①给 15 行（插 5）而非
        5 行（不插）。用 full-book 完整链路复现「区① sibling 插行 → verify drift」，钉成 xfail。
        """
        from app.services.excel_structure_fingerprint import identity_inventory
        from app.services.workpaper_sync import phase5_d3_04_analysis as D304
        from app.services.workpaper_sync import phase5_d3_05_long_term as D305
        from app.services.workpaper_sync import phase5_d3_06_related_party as D306
        from app.services.workpaper_sync.adapters.base import Projection
        from app.services.workpaper_sync.adapters.excel import build_excel_adapter
        from app.services.workpaper_sync.excel_entry_gate import parse_identity_inventory
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            build_store_projection,
            managed_field_specs,
        )

        full_specs = (ENTRY.instrumentation_spec(),) + tuple(P.instrumentation_specs())
        instrumented = EI.instrument_workbook_bytes_multi(
            ENTRY.read_authoritative_template(), full_specs, gate=gate
        )
        primary_binding = X.ExcelIdentityBinding(
            table_name=ENTRY.TABLE_NAME, uuid_column=ENTRY.UUID_COL, table_key=ENTRY.ROWS_TABLE_KEY,
        )
        sibling_specs = (
            D306.SPEC_D306, D304.SPEC_D304_DEBIT, D304.SPEC_D304_CREDIT, D305.SPEC_D305, UPPER, LOWER,
        )
        sibling_bindings = tuple(
            X.ExcelIdentityBinding(table_name=s.table_name, uuid_column=s.uuid_col, table_key=s.table_key)
            for s in sibling_specs
        )
        base_path = tmp_path / "d3-fb7-boundary-base.xlsx"
        base_path.write_bytes(instrumented.instrumented_bytes)
        base = _synthetic_definitions(contract_with_d307)
        inv_raw = identity_inventory(
            instrumented.instrumented_bytes, expected_table=str(ENTRY.TABLE_NAME),
            uuid_column_letter=str(ENTRY.UUID_COL),
        )
        definitions = base.__class__(
            entry_id=base.entry_id, bundle=base.bundle, contract=base.contract,
            adapter_build=base.adapter_build,
            identity_inventory=parse_identity_inventory(inv_raw),
            business_sheets=(), dynamic_column_keys={}, structure_inventory_size=0,
        )
        adapter = build_excel_adapter(
            definitions=definitions, binding=primary_binding, direction="html_to_oo",
            sibling_bindings=sibling_bindings,
        )

        def _rows(spec: Any, tag: str, n: int) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for i in range(n):
                r: dict[str, Any] = {spec.row_identity_key: f"{tag}-{i}"}
                for _ck, _col, _m, vt, jk, _l, _g in managed_field_specs(spec):
                    if "/" in jk:
                        continue
                    r[jk] = (100.0 + i) if vt in ("number", "amount") else f"{tag}{_ck}{i}"
                out.append(r)
            return out

        values: dict[str, Any] = {}
        row_keys: dict[str, Any] = {}
        for spec, tag, n in (
            (ENTRY.SPEC_D32, "d32", 5), (D306.SPEC_D306, "d36", 5),
            (D304.SPEC_D304_DEBIT, "d34dr", 5), (D304.SPEC_D304_CREDIT, "d34cr", 5),
            (D305.SPEC_D305, "d35", 5), (UPPER, "d37cur", 15), (LOWER, "d37post", 13),
        ):
            proj = build_store_projection(spec, _rows(spec, tag, n), contract=contract_with_d307)
            values.update(proj.values)
            row_keys.update(proj.row_keys)
        combined = Projection(
            contract_id=contract_with_d307.contract_id,
            semantic_version=contract_with_d307.semantic_version,
            document_type=contract_with_d307.document_type,
            values=values, row_keys=row_keys,
        )
        staged = tmp_path / ".staging" / "d3-fb7-boundary.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path, projection=combined, output=staged, contract=contract_with_d307
        )
        report = adapter.verify_unmanaged_regions(
            before=base_path, after=staged, contract=contract_with_d307,
            row_shift=getattr(result, "row_shift", None),
            total_formula_rows=getattr(result, "total_formula_rows", ()) or (),
            propagation=getattr(result, "workbook_row_change", None),
            per_table_shift=getattr(result, "per_table_shift", None),
        )
        # xfail：引擎修复后此断言成立 → strict xfail 转红提醒摘除标记 + 让整册验收判据区①也插行。
        assert report.equivalent is True, (
            "整册下 D3-7 区① sibling 插行的累积归一化边界已修复——请摘除 xfail 并让整册判据区①插行"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 读侧辅助（真字节，不经业务代码；同 test_sibling_table_ref_row_shift 手法）
# ═══════════════════════════════════════════════════════════════════════════


def _table_ref(path: Path, table_name: str) -> str:
    """读产物里指定 Excel Table 的 ref（真字节）。"""
    with zipfile.ZipFile(path) as zf:
        for t in X._tables_of(zf):
            disp = str(t.get("display_name") or t.get("name"))
            if disp == table_name:
                return str(t.get("ref") or "")
    raise AssertionError(f"定位不到 Table {table_name}")


def _ref_rows(ref: str) -> tuple[int, int]:
    head, tail = ref.split(":", 1)
    return (
        int("".join(ch for ch in head if ch.isdigit())),
        int("".join(ch for ch in tail if ch.isdigit())),
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v", "--tb=short"]))
