# -*- coding: utf-8 -*-
"""D3-4 双区位移链实证（Task 10 · 阶段 2 验收）。

spec: d3-sync-coverage-via-row-table-engine · Task 10 · Requirements 2.2, 2.4, 6.1

═══ 为什么需要这一份 ═══

Task 8 声明 D3-4 双区时把"段①差异公式 `B17='=B11-B13-B14-B15-B16'` 硬编码引用固定 4 行，
插行后是否被行表引擎的位移归一化机制自动纠正"这个悬念明确留给本任务（Task 10）用真实测试
验证（不是让引擎替声明代码兜底修复模板缺陷，而是查清引擎目前的真实行为边界）。

本文件在真实注入产物上驱动**真实**的 `shift_sheet_rows`（生产 materialize 管线用的同一
纯函数），照抄 `test_sibling_table_ref_row_shift.py` 的"duck object 喂 plan"手法与
D4-9/D4-1 已验证的双区位移范式，把结论钉成持久化、可重跑的判据：

1. **Table ref 位移**（同 `test_all_multi_region_sheets_shift_sibling_table_refs` 已覆盖
   的机制，本文件不重复造轮子，只在 Property 5/9 场景下追加一条对 D3-4 的专属确认）。
2. **footer 差异公式区间归一化的真实边界**（本文件新增，核心发现）：`_RANGE_IN_FORMULA_RE`
   只匹配 `A1:B2` 式冒号区间（如 `SUM(B7:B25)`），`=B11-B13-B14-B15-B16` 这种散落单格
   引用相减的公式文本里**没有任何冒号**，`assert_footer_formula_covers_managed_rows` 对它
   的区间扫描恒为空 match 集，**不会报错也不会扩张**——插行后差异公式里被位移覆盖的单格
   引用（如 `B16→B19`）会被 `propagate_reference_side` 正确重映射跟随该行物理位移，但公式
   **不会**被扩张以覆盖新插入的业务行。这是一个真实存在的引擎边界（"footer 合计/差异公式
   区间归一化"目前只覆盖 `SUM(range)` 式结构化冒号区间公式），不是 Task 8/9 的声明缺陷，
   引擎会静默产出一张差异公式漏算新行的审计底稿、且不报错——这正是本文件要钉住并公开暴露
   的真实发现，不代为修复模板或加规避逻辑。
3. **`verify_unmanaged_regions` 累积归一化**（多次插行后仍正确判定受管/非受管边界）。

全程用离线注入产物（不连库、不依赖 adapter 注册），沿用 Task 5 已确认的"真栈端到端不可测，
但支撑它的核心机制是纯函数可离线验证"处置原则（design.md 裁决 F5）。
"""
from __future__ import annotations

import io
import os
import re
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
from app.services.workpaper_sync import phase5_d3_04_analysis as D304
from app.services.workpaper_sync import phase5_d3_expansion as P
from app.services.workpaper_sync import phase5_d3_prepaid_receipts as ENTRY
from app.services.workpaper_sync.excel_materialize import (
    ManagedRegion,
    _managed_table_part,
    assert_footer_formula_covers_managed_rows,
)
from app.services.workpaper_sync.excel_row_shift import RowShiftPlan, shift_sheet_rows

SHEET_NAME = D304.MANAGED_SHEET_D304
UPPER = D304.SPEC_D304_DEBIT  # 段①：借方（数据区 13-15，footer 17）
LOWER = D304.SPEC_D304_CREDIT  # 段②：贷方（数据区 22-23，footer 25）—— 同 sheet 兄弟区


@pytest.fixture(scope="module")
def gate() -> EI.ExcelIdentityCarrierGate:
    return EI.ExcelIdentityCarrierGate.load()


@pytest.fixture(scope="module")
def all_specs() -> tuple[Any, ...]:
    """打开三个 D3 灰度开关后的完整 instrumentation 清单（真实产出，不是近似结构）。"""
    return P.instrumentation_specs()


@pytest.fixture(scope="module")
def instrumented(
    all_specs: tuple[Any, ...], gate: EI.ExcelIdentityCarrierGate
) -> EI.InstrumentedWorkbook:
    return EI.instrument_workbook_bytes_multi(
        ENTRY.read_authoritative_template(), all_specs, gate=gate
    )


@pytest.fixture(scope="module")
def contract_with_d304() -> Any:
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


def _sheet_part(instrumented: EI.InstrumentedWorkbook) -> str:
    with zipfile.ZipFile(io.BytesIO(instrumented.instrumented_bytes)) as zf:
        part = X._sheet_parts(zf).get(SHEET_NAME)
    assert part, f"定位不到 {SHEET_NAME}"
    return part


def _formula_text(xml: str, coord: str) -> str | None:
    """取指定坐标格自身的公式文本；不跨格匹配（`[^<]*?` 而非 `.*?` 防越界吃到下一格）。"""
    m = re.search(rf'<c r="{coord}"[^>]*>(?:(?!</c>).)*?<f[^>]*>([^<]*)</f>', xml, re.S)
    return m.group(1) if m else None


class TestPremiseD304IsRegisteredAsDualZone:
    """前提确认：D3-4 双区已通过灰度开关真实接入且共享同一 sheet_key（同 D4-9 范式）。"""

    def test_two_specs_share_managed_sheet(self) -> None:
        assert UPPER.managed_sheet == LOWER.managed_sheet == SHEET_NAME
        assert UPPER.sheet_key == LOWER.sheet_key, "双区应共享 sheet_key（裁决见 Task 8 证据）"

    def test_appears_in_sibling_shift_parametrized_coverage(self) -> None:
        """D3-4 应自动出现在上游 D1 spec Task 24 参数化后的位移判据覆盖清单里
        （不是本文件重复造一份判定逻辑，只确认接线正确）。"""
        sys.path.insert(0, str(_BACKEND / "tests" / "workpaper_sync"))
        try:
            from test_sibling_table_ref_row_shift import _multi_region_sheets
        finally:
            sys.path.remove(str(_BACKEND / "tests" / "workpaper_sync"))
        multi = _multi_region_sheets()
        assert SHEET_NAME in multi, (
            f"D3-4 应已自动进入同 sheet 多受管区参数化清单（上游 D1 Task 24 已解除），"
            f"实得 {sorted(multi)}"
        )
        assert len(multi[SHEET_NAME]) == 2


class TestFooterFormulaRangeNormalizationRealBoundary:
    """核心发现：段①差异公式硬编码引用固定行，真实插行后**不会**被扩张覆盖新增业务行。

    用真实 `shift_sheet_rows`（生产 materialize 管线同一纯函数）驱动，不是猜测/理论分析。
    """

    def test_reference_to_shifted_row_is_remapped_but_range_not_extended(
        self, instrumented: EI.InstrumentedWorkbook
    ) -> None:
        sheet_part = _sheet_part(instrumented)
        with zipfile.ZipFile(io.BytesIO(instrumented.instrumented_bytes)) as zf:
            xml_before = zf.read(sheet_part).decode("utf-8")

        before_formula = _formula_text(xml_before, "B17")
        assert before_formula == "B11-B13-B14-B15-B16", (
            f"前提不成立：插行前 B17 差异公式应为硬编码引用固定 4 行，实得 {before_formula!r}"
        )

        insert_at = int(UPPER.last_data_row) + 1  # 16（紧贴段①受管区末行之后）
        count = 3
        plan = RowShiftPlan(
            insert_at=insert_at, count=count, style_from=int(UPPER.last_data_row),
            table_key=str(UPPER.table_name),
        )
        xml_after, report = shift_sheet_rows(
            xml_before, plan,
            total_formula_rows=(int(UPPER.footer_row),),
            managed_columns=("A", "B", "C", "D"),
        )
        assert report.inserted_rows == count, f"应真实插入 {count} 行，实得 {report.inserted_rows}"

        new_footer_row = int(UPPER.footer_row) + count  # 20
        after_formula = _formula_text(xml_after, f"B{new_footer_row}")

        # 🔴 关键发现：B16 引用被正确重映射为 B19（跟随该行物理下移 3），但公式**没有**
        #    被扩张以覆盖新插入的 16/17/18 三行业务数据（区间检测器只认冒号区间）。
        assert after_formula == "B11-B13-B14-B15-B19", (
            f"预期观察到「单格引用被重映射但区间未扩张」这个真实边界，实得公式变为 "
            f"{after_formula!r}——若这个断言失败，说明引擎行为已经改变，需要重新核实"
            "这个悬念的答案（不要想当然假设行为不变）"
        )
        # 新插入的 3 行金额单元格（B16/B17/B18）不在这个差异公式的引用范围内 ——
        # 用字符串包含判断即可证明"漏算"（B16 已不在公式里，B17/B18 从未出现过）。
        for orphan_row in (16, 17, 18):
            assert f"B{orphan_row}" not in after_formula, (
                f"若 B{orphan_row} 出现在扩张后的公式里，说明区间**被**扩张了，"
                "与本文件要钉住的『不会被扩张』结论相反"
            )

    def test_assert_footer_formula_covers_managed_rows_does_not_reject_the_gap(
        self, instrumented: EI.InstrumentedWorkbook
    ) -> None:
        """生产两相真实调用点（计划期 + apply 后）都不会拦住这个漏算——用真实函数复现，
        不是自己另写一套判断逻辑。这证明"静默产出漏算底稿"不是理论推测，是真实可复现的
        管线行为。"""
        sheet_part = _sheet_part(instrumented)
        with zipfile.ZipFile(io.BytesIO(instrumented.instrumented_bytes)) as zf:
            xml_before = zf.read(sheet_part).decode("utf-8")

        insert_at = int(UPPER.last_data_row) + 1
        count = 3
        plan = RowShiftPlan(
            insert_at=insert_at, count=count, style_from=int(UPPER.last_data_row),
            table_key=str(UPPER.table_name),
        )
        xml_after, _ = shift_sheet_rows(
            xml_before, plan, total_formula_rows=(int(UPPER.footer_row),),
            managed_columns=("A", "B", "C", "D"),
        )

        region = ManagedRegion(
            table_key=str(UPPER.table_key), table_name=str(UPPER.table_name),
            sheet_name=SHEET_NAME, sheet_part=sheet_part, table_ref="A13:D15",
            first_row=int(UPPER.first_data_row), last_row=int(UPPER.last_data_row),
            first_column="A", last_column="D", uuid_column=str(UPPER.uuid_col),
        )

        # 【计划期】substrate（位移前），footer_row=位移前冻结行，row_shift=plan。
        checked_plan = assert_footer_formula_covers_managed_rows(
            entries={sheet_part: xml_before.encode("utf-8")},
            sheet_part=sheet_part, footer_row=int(UPPER.footer_row),
            region=region, row_shift=plan, carries_total_formula=True,
        )
        assert checked_plan == ("B17",)

        # 【apply 后】staged（位移后），footer_row=位移后实际物理行，row_shift=plan。
        new_footer_row = int(UPPER.footer_row) + count
        checked_apply = assert_footer_formula_covers_managed_rows(
            entries={sheet_part: xml_after.encode("utf-8")},
            sheet_part=sheet_part, footer_row=new_footer_row,
            region=region, row_shift=plan, carries_total_formula=True,
        )
        assert checked_apply == (f"B{new_footer_row}",), (
            "两相真实调用都『通过、未拦截』——静默放行了这个漏算的差异公式，"
            "这正是本文件要如实暴露的引擎边界（不是本任务范围内的 bug）"
        )


class TestSegment2HasNoFormulaHardcodeSoNoAnalogousGap:
    """段②（贷方）无差异计算公式硬编码引用固定行，不涉及本悬念——对照确认，不留遗漏印象。"""

    def test_credit_footer_has_no_formula_at_all(self, instrumented: EI.InstrumentedWorkbook) -> None:
        sheet_part = _sheet_part(instrumented)
        with zipfile.ZipFile(io.BytesIO(instrumented.instrumented_bytes)) as zf:
            xml = zf.read(sheet_part).decode("utf-8")
        assert _formula_text(xml, f"B{LOWER.footer_row}") is None, (
            "段②footer（差异合理性分析）应无任何公式——本表 footer_carries_total_formula=False "
            "正是因为这里没有公式，与段①硬编码引用固定行的场景不同"
        )


def _synthetic_definitions(contract: Any) -> Any:
    """按 D4 姊妹判据 `_make_definitions` 同款手法合成 `FrozenEntryDefinitions`——本地构造
    frozen digest（不走真库 `register_from_manifest()`），绕开 Task 5 确认的 D3 adapter
    未注册阻塞（裁决 F5：真栈实测阻塞，但支撑机制的纯函数/离线路径应照常验证）。
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
        bundle_sha256=_d("d3-04-dual-zone-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("d3-04-dual-zone-authority"),
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
            adapter_build_digest=_d("d3-04-dual-zone-build"),
            document_type="xlsx",
            contract_version=contract.semantic_version,
        ),
        identity_inventory=None,  # type: ignore[arg-type]
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


class TestVerifyUnmanagedRegionsAccumulatesAcrossMultipleInsertions:
    """`verify_unmanaged_regions` 在**多次**插行累积后仍正确判定受管/非受管边界
    （照 D4-9 双区范式：走真实 `build_excel_adapter`/`ExcelSyncAdapter.materialize()` +
    `.verify_unmanaged_regions()` 完整管线——不是手工重写字节位移逻辑。此前用手工
    `_grow_managed_table_ref` 拼字节的做法漏算了同 sheet 第三个非受管区域（段③债务人
    分析，行 26-33，随插行一起物理下移但不属任一 binding）导致误判，改走真实 adapter
    后该区域由 `managed_sheet_unmanaged_cells` aspect 的全表逐格 shift-aware 归一化
    统一处理，不需要本文件额外枚举）。
    """

    def test_upper_zone_insertion_shifts_sibling_table_ref_and_verify_still_passes(
        self,
        instrumented: EI.InstrumentedWorkbook,
        contract_with_d304: Any,
        upper_binding: X.ExcelIdentityBinding,
        lower_binding: X.ExcelIdentityBinding,
        tmp_path: Path,
    ) -> None:
        from app.services.excel_structure_fingerprint import identity_inventory
        from app.services.workpaper_sync.adapters.excel import build_excel_adapter
        from app.services.workpaper_sync.excel_entry_gate import parse_identity_inventory

        base_path = tmp_path / "d304-base.xlsx"
        base_path.write_bytes(instrumented.instrumented_bytes)

        base = _synthetic_definitions(contract_with_d304)
        inv_raw = identity_inventory(
            instrumented.instrumented_bytes,
            expected_table=str(UPPER.table_name),
            uuid_column_letter=str(UPPER.uuid_col),
        )
        definitions = base.__class__(
            entry_id=base.entry_id,
            bundle=base.bundle,
            contract=base.contract,
            adapter_build=base.adapter_build,
            identity_inventory=parse_identity_inventory(inv_raw),
            business_sheets=(),
            dynamic_column_keys={},
            structure_inventory_size=0,
        )

        adapter = build_excel_adapter(
            definitions=definitions,
            binding=upper_binding,
            direction="html_to_oo",
            sibling_bindings=(lower_binding,),
        )

        # 派生行数超过模板占位（段①仅 3 行）⇒ 必然触发结构性插行。
        derived_rows = [
            {
                "rowId": f"debit-p{i}", "label": f"借方派生{i}", "amount": 100.0 + i,
                "source": "tb", "remark": "",
            }
            for i in range(6)
        ]
        from app.services.workpaper_sync.phase5_row_table_sheet import build_store_projection

        proj = build_store_projection(UPPER, derived_rows, contract=contract_with_d304)

        staged = tmp_path / ".staging" / "d304-verify.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path, projection=proj, output=staged, contract=contract_with_d304
        )
        assert staged.is_file() and staged.read_bytes()[:2] == b"PK"

        report = adapter.verify_unmanaged_regions(
            before=base_path,
            after=staged,
            contract=contract_with_d304,
            row_shift=getattr(result, "row_shift", None),
            total_formula_rows=getattr(result, "total_formula_rows", ()) or (),
            propagation=getattr(result, "workbook_row_change", None),
            per_table_shift=getattr(result, "per_table_shift", None),
        )
        assert report.equivalent is True, (
            f"段①插行后，真实 adapter 管线的 verify_unmanaged_regions 应正确判等价"
            f"（含同 sheet 第三个非 binding 区域 段③债务人分析），实得差异：{report.details}"
        )

        # Table ref 位移确认（同 test_all_multi_region_sheets_shift_sibling_table_refs
        # 已验证的机制，这里只做一次针对本场景的具体数值确认，不重复整套判据）。
        with zipfile.ZipFile(staged) as zf:
            lower_region_after = X.resolve_managed_region(
                zf, contract=contract_with_d304, binding=lower_binding
            )
        assert lower_region_after.first_row > int(LOWER.first_data_row), (
            f"段②（兄弟区）首行应随段①插行整体下移，位移前 {LOWER.first_data_row}，"
            f"实得位移后 {lower_region_after.first_row}"
        )

    def test_cumulative_two_pass_insertion_still_verifies_correctly(
        self,
        instrumented: EI.InstrumentedWorkbook,
        contract_with_d304: Any,
        upper_binding: X.ExcelIdentityBinding,
        lower_binding: X.ExcelIdentityBinding,
        tmp_path: Path,
    ) -> None:
        """**两趟**插行累积（段①插一次，段②再插一次）—— 复现 D4-9/D4-1 的
        `CompositeRowShift` 归一化场景（同 sheet 两区都插行才需要累积归一化），走真实
        `adapters/excel.py._sheet_cumulative_shift` 链式路径（`adapter.materialize()`
        单次调用即完成两个 binding 各自的插行判定，不需要本文件手工分两趟拼字节）。
        """
        from app.services.excel_structure_fingerprint import identity_inventory
        from app.services.workpaper_sync.adapters.excel import build_excel_adapter
        from app.services.workpaper_sync.excel_entry_gate import parse_identity_inventory
        from app.services.workpaper_sync.phase5_row_table_sheet import build_store_projection

        base_path = tmp_path / "d304-base2.xlsx"
        base_path.write_bytes(instrumented.instrumented_bytes)

        base = _synthetic_definitions(contract_with_d304)
        inv_raw = identity_inventory(
            instrumented.instrumented_bytes,
            expected_table=str(UPPER.table_name),
            uuid_column_letter=str(UPPER.uuid_col),
        )
        definitions = base.__class__(
            entry_id=base.entry_id,
            bundle=base.bundle,
            contract=base.contract,
            adapter_build=base.adapter_build,
            identity_inventory=parse_identity_inventory(inv_raw),
            business_sheets=(),
            dynamic_column_keys={},
            structure_inventory_size=0,
        )

        adapter = build_excel_adapter(
            definitions=definitions,
            binding=upper_binding,
            direction="html_to_oo",
            sibling_bindings=(lower_binding,),
        )

        # 两区都超模板占位行数 ⇒ 两趟都要插行（累积归一化的复现前提）。
        upper_rows = [
            {"rowId": f"debit-p{i}", "label": f"借方派生{i}", "amount": 100.0 + i,
             "source": "tb", "remark": ""}
            for i in range(5)
        ]
        lower_rows = [
            {"rowId": f"credit-q{i}", "label": f"贷方派生{i}", "amount": 200.0 + i,
             "source": "tb", "remark": ""}
            for i in range(5)
        ]
        proj_upper = build_store_projection(UPPER, upper_rows, contract=contract_with_d304)
        proj_lower = build_store_projection(LOWER, lower_rows, contract=contract_with_d304)
        from app.services.workpaper_sync.adapters.base import Projection

        combined = Projection(
            contract_id=proj_upper.contract_id,
            semantic_version=proj_upper.semantic_version,
            document_type=proj_upper.document_type,
            values={**proj_upper.values, **proj_lower.values},
            row_keys={**proj_upper.row_keys, **proj_lower.row_keys},
        )

        staged = tmp_path / ".staging" / "d304-cumulative.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path, projection=combined, output=staged, contract=contract_with_d304
        )
        assert staged.is_file()

        pts = getattr(result, "per_table_shift", None)
        assert pts, f"两区都插行 ⇒ per_table_shift 应带出两条声明，实得 {pts!r}"
        assert str(UPPER.table_key) in pts and str(LOWER.table_key) in pts, (
            f"两趟位移声明应都存在（累积场景的复现前提），实得 {sorted(pts)}"
        )

        report = adapter.verify_unmanaged_regions(
            before=base_path,
            after=staged,
            contract=contract_with_d304,
            row_shift=getattr(result, "row_shift", None),
            total_formula_rows=getattr(result, "total_formula_rows", ()) or (),
            propagation=getattr(result, "workbook_row_change", None),
            per_table_shift=pts,
        )
        assert report.equivalent is True, (
            f"两趟累积插行（段①+5、段②+5）后，累积归一化（CompositeRowShift）应仍正确"
            f"判定受管/非受管边界，实得差异：{report.details}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 整册 materialize（Task 10 第 3c 段）—— D3-5/D3-6 模板缺陷修复后，全部受管区
# 一次 materialize + verify 应等价（§3e/§6.4/§2.2 一直说的"整册 materialize"，
# 模板修好后这条离线整册链路能真跑；真栈端到端仍受 adapter capability 限制不可测）。
# ═══════════════════════════════════════════════════════════════════════════

from app.services.workpaper_sync import phase5_d3_05_long_term as D305  # noqa: E402
from app.services.workpaper_sync import phase5_d3_06_related_party as D306  # noqa: E402


def _generic_rows(spec: Any, tag: str, n: int) -> list[dict[str, Any]]:
    """按 spec 的 field_specs 造 n 行合成数据（每行填 row_identity_key + 各业务列占位）。

    row_identity_key 用全新 id（orphan）⇒ 相对模板种子行必然触发结构性插行。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs

    rows: list[dict[str, Any]] = []
    for i in range(n):
        row: dict[str, Any] = {spec.row_identity_key: f"{tag}-{i}"}
        for _ck, _col, _mode, value_type, json_key, _label, _grp in managed_field_specs(spec):
            if "/" in json_key:  # nested 路径本合成不覆盖，留空（split 取 None 合法）
                continue
            row[json_key] = (100.0 + i) if value_type in ("number", "amount") else f"{tag}{_ck}{i}"
        rows.append(row)
    return rows


class TestFullBookMaterializeAfterTemplateFooterFix:
    """D3-2 primary + D3-6 / D3-4借 / D3-4贷 / D3-5 全 sibling 一次整册 materialize + verify。

    Task 10 第 3c 段：D3-5（A14 补「合计」）/ D3-6（footer SUM 12:14→12:16）模板缺陷修复后，
    它们进 materialize 不再被 footer 锚点门 / 覆盖门拦。走真实 `build_excel_adapter` +
    `adapter.materialize` + `adapter.verify_unmanaged_regions` 完整离线管线（照抄本文件
    `_synthetic_definitions` + sibling_bindings 范式）。
    """

    def test_all_managed_regions_materialize_and_verify_equivalent(
        self,
        gate: EI.ExcelIdentityCarrierGate,
        contract_with_d304: Any,
        tmp_path: Path,
    ) -> None:
        from app.services.excel_structure_fingerprint import identity_inventory
        from app.services.workpaper_sync.adapters.base import Projection
        from app.services.workpaper_sync.adapters.excel import build_excel_adapter
        from app.services.workpaper_sync.excel_entry_gate import parse_identity_inventory
        from app.services.workpaper_sync.phase5_row_table_sheet import build_store_projection

        # 🔴 整册 substrate 必须含 D3-2 primary 的 Table —— `P.instrumentation_specs()` 只覆盖
        #    扩容面（D3-6/D3-4/D3-5），不含 D3-2；故这里注入 [D3-2 单数声明] + 扩容面全部
        #    （同 evidence §2.1 的 `[instrumentation_spec()] + [_instrumentation_of(s)…]` 手法）。
        full_specs = (ENTRY.instrumentation_spec(),) + tuple(P.instrumentation_specs())
        instrumented = EI.instrument_workbook_bytes_multi(
            ENTRY.read_authoritative_template(), full_specs, gate=gate
        )

        # primary = D3-2（entry 主受管表），siblings = D3-6 / D3-4借 / D3-4贷 / D3-5（Excel 行序）。
        primary_binding = X.ExcelIdentityBinding(
            table_name=ENTRY.TABLE_NAME, uuid_column=ENTRY.UUID_COL,
            table_key=ENTRY.ROWS_TABLE_KEY,
        )
        sibling_specs = (D306.SPEC_D306, UPPER, LOWER, D305.SPEC_D305)
        sibling_bindings = tuple(
            X.ExcelIdentityBinding(
                table_name=s.table_name, uuid_column=s.uuid_col, table_key=s.table_key
            )
            for s in sibling_specs
        )

        base_path = tmp_path / "d3-fullbook-base.xlsx"
        base_path.write_bytes(instrumented.instrumented_bytes)

        base = _synthetic_definitions(contract_with_d304)
        inv_raw = identity_inventory(
            instrumented.instrumented_bytes,
            expected_table=str(ENTRY.TABLE_NAME),
            uuid_column_letter=str(ENTRY.UUID_COL),
        )
        definitions = base.__class__(
            entry_id=base.entry_id,
            bundle=base.bundle,
            contract=base.contract,
            adapter_build=base.adapter_build,
            identity_inventory=parse_identity_inventory(inv_raw),
            business_sheets=(),
            dynamic_column_keys={},
            structure_inventory_size=0,
        )

        adapter = build_excel_adapter(
            definitions=definitions,
            binding=primary_binding,
            direction="html_to_oo",
            sibling_bindings=sibling_bindings,
        )

        # 每区给 5 行真实行数（触发插行）。primary D3-2 也给 5 行（走通用行造法）。
        d32_spec = ENTRY.SPEC_D32
        values: dict[str, Any] = {}
        row_keys: dict[str, Any] = {}
        for spec, tag, n in (
            (d32_spec, "d32", 5),
            (D306.SPEC_D306, "d36", 5),
            (UPPER, "d34dr", 5),
            (LOWER, "d34cr", 5),
            (D305.SPEC_D305, "d35", 5),
        ):
            proj = build_store_projection(spec, _generic_rows(spec, tag, n), contract=contract_with_d304)
            values.update(proj.values)
            row_keys.update(proj.row_keys)

        combined = Projection(
            contract_id=contract_with_d304.contract_id,
            semantic_version=contract_with_d304.semantic_version,
            document_type=contract_with_d304.document_type,
            values=values,
            row_keys=row_keys,
        )

        staged = tmp_path / ".staging" / "d3-fullbook.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path, projection=combined, output=staged, contract=contract_with_d304
        )
        assert staged.is_file() and staged.read_bytes()[:2] == b"PK", (
            "整册 materialize 应产出 staged 工作簿"
        )

        pts = getattr(result, "per_table_shift", None)
        # 五区各插行 ⇒ per_table_shift 应带出多条声明（至少含各 sibling 的 table_key）。
        assert pts, f"整册插行 ⇒ per_table_shift 应非空，实得 {pts!r}"

        report = adapter.verify_unmanaged_regions(
            before=base_path,
            after=staged,
            contract=contract_with_d304,
            row_shift=getattr(result, "row_shift", None),
            total_formula_rows=getattr(result, "total_formula_rows", ()) or (),
            propagation=getattr(result, "workbook_row_change", None),
            per_table_shift=pts,
        )
        assert report.equivalent is True, (
            "D3-5/D3-6 模板缺陷修复后，D3 整册 materialize（D3-2 primary + D3-6/D3-4借/"
            f"D3-4贷/D3-5 全 sibling）的 verify_unmanaged_regions 应判等价，实得：{report.details}"
        )


class TestGtSyncFooterRowReFrozenAfterD34DebitInsertion:
    """§8：D3-4 段①插行后，产物 `_GT_SYNC` 的 `GT_FOOTER_ROW_D34DEBIT` 应重冻结为下移后行号。

    读产物隐藏 `_GT_SYNC` sheet（走唯一读侧入口 `read_runtime_binding_pairs`，不手搓第二份），
    断言 footer 冻结坐标按插入行数下移（声明与物理同源）。
    """

    def test_footer_row_key_shifts_by_inserted_count(
        self,
        instrumented: EI.InstrumentedWorkbook,
        contract_with_d304: Any,
        upper_binding: X.ExcelIdentityBinding,
        lower_binding: X.ExcelIdentityBinding,
        tmp_path: Path,
    ) -> None:
        from app.services.excel_structure_fingerprint import identity_inventory
        from app.services.workpaper_sync.adapters.excel import build_excel_adapter
        from app.services.workpaper_sync.excel_entry_gate import parse_identity_inventory
        from app.services.workpaper_sync.phase5_row_table_sheet import build_store_projection

        footer_key = f"GT_FOOTER_ROW_{D304.TEMPLATE_ID_D304}DEBIT"  # GT_FOOTER_ROW_D34DEBIT

        base_path = tmp_path / "d34-gtsync-base.xlsx"
        base_path.write_bytes(instrumented.instrumented_bytes)

        with zipfile.ZipFile(base_path) as zf:
            before_pairs = X.read_runtime_binding_pairs(zf)
        assert footer_key in before_pairs, (
            f"前提不成立：`_GT_SYNC` 无 {footer_key}，实得 "
            f"{[k for k in before_pairs if k.startswith('GT_FOOTER_ROW')]}"
        )
        footer_before = int(before_pairs[footer_key])
        assert footer_before == int(UPPER.footer_row), (
            f"{footer_key} 冻结值应 == 段① footer 行 {UPPER.footer_row}，实得 {footer_before}"
        )

        base = _synthetic_definitions(contract_with_d304)
        inv_raw = identity_inventory(
            instrumented.instrumented_bytes,
            expected_table=str(UPPER.table_name),
            uuid_column_letter=str(UPPER.uuid_col),
        )
        definitions = base.__class__(
            entry_id=base.entry_id, bundle=base.bundle, contract=base.contract,
            adapter_build=base.adapter_build,
            identity_inventory=parse_identity_inventory(inv_raw),
            business_sheets=(), dynamic_column_keys={}, structure_inventory_size=0,
        )
        adapter = build_excel_adapter(
            definitions=definitions, binding=upper_binding, direction="html_to_oo",
            sibling_bindings=(lower_binding,),
        )

        n = 5  # 段①插 5 行
        rows = [
            {"rowId": f"debit-{i}", "label": f"借方{i}", "amount": 100.0 + i,
             "source": "tb", "remark": ""}
            for i in range(n)
        ]
        proj = build_store_projection(UPPER, rows, contract=contract_with_d304)
        staged = tmp_path / ".staging" / "d34-gtsync.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path, projection=proj, output=staged, contract=contract_with_d304
        )
        # 实际插入行数取自 materialize 冻结产物的 row_shift（RowShiftPlan.count），
        # 不预设 = n（模板种子行可能被复用）。
        row_shift = getattr(result, "row_shift", None)
        assert row_shift is not None, "段①插行 ⇒ result.row_shift 应非空"
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
