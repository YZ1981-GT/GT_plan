# -*- coding: utf-8 -*-
"""D3-6 离线"整册 materialize + verify_unmanaged_regions"（Task 7 接入验收）。

spec: d3-sync-coverage-via-row-table-engine · Task 7 · Requirements 1.4, 6.1, 6.3

═══ 为什么需要这一份，"整册 materialize" 到底是什么 ═══

Task 5 证据（`evidence/task5-performance-baseline-and-adapter-status.md`）已精确定位"整册
materialize"= `MaterializeCoordinator.materialize()`（`materialize_coordinator.py:1770`），
它与 `wp_sync_router.py` 的三端点共享同一前置门 `_registration()`——该门依赖真库
`register_from_manifest()` 成功注册 D3 的 adapter，而 Task 5 已两次独立实测确认这条路径
在到达 D3 之前就会先因 D2 的契约漂移而中断（`ContractDriftError`），即使解除该阻塞，D3 自身
manifest 的 `capability="single_onlyoffice"` 仍会短路 `attach_adapters()`。⇒ 端到端真栈整册
materialize 在当前环境**确认不可测**（Task 5 结论，本任务不重复验证这一点，直接引用）。

但"整册 materialize"背后真正做的事——**把受管区的 identity 载体（Excel Table / UUID 隐藏列 /
defined names）注入模板字节，再校验受管区之外的任何字节都不受影响**——这件事的核心机制
（`excel_instrumentation.instrument_workbook_bytes` + `excel_extract.verify_unmanaged_regions`）
是**纯函数**，只吃/吐 bytes，不连库、不依赖 adapter 注册（`instrument_workbook_bytes` 的
docstring 明写"结构上碰不到 backend/wp_templates/ 里的文件"，`verify_unmanaged_regions` 只需
两份 xlsx 字节 + 解析后的 contract/region/binding）。这正是 `test_task42_h1_grouped_dynamic_pilot.py`
（H1 首次接入时）采用的离线验证范式（该文件 docstring 第 5 条："插删重排复制真的跑在真实模板上：
真实权威模板 → 真实注入产物 → 真实 extract"）——本文件把同一范式套用到 D3-6，是 D3/E1/D1 三个
姊妹 spec 里**第一个**把这条路径真的跑通并验证的（D1 Task 25/26、E1 Task 11 目前均仍是
`[ ]*`/未开工，本任务不能等它们先做出示例再抄）。

**本文件验证的是"注入 + 未管理区域校验"这条机制本身在 D3-6 上真实可用、且不是恒真的空集比较**，
不是端到端真栈往返（那部分仍如实标 `[ ]*`，理由见 Task 5 证据 + design.md 裁决 F5）。
"""
from __future__ import annotations

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
from app.services.workpaper_sync import phase5_d3_06_related_party as D306
from app.services.workpaper_sync import phase5_d3_expansion as P
from app.services.workpaper_sync import phase5_d3_prepaid_receipts as ENTRY


@pytest.fixture(scope="module")
def gate() -> EI.ExcelIdentityCarrierGate:
    return EI.ExcelIdentityCarrierGate.load()


@pytest.fixture(scope="module")
def d306_instrumentation_spec() -> EI.ExcelInstrumentationSpec:
    """`phase5_d3_expansion._instrumentation_of(SPEC_D306)`——与开关打开后真实产出的对象
    完全一致（不是本文件另造一份近似结构）。"""
    return P._instrumentation_of(D306.SPEC_D306)


@pytest.fixture(scope="module")
def instrumented(
    d306_instrumentation_spec: EI.ExcelInstrumentationSpec,
    gate: EI.ExcelIdentityCarrierGate,
) -> EI.InstrumentedWorkbook:
    """真实权威模板字节 → 真实注入产物（只吃/吐 bytes，不连库、不依赖 adapter 注册）。"""
    return EI.instrument_workbook_bytes(
        ENTRY.read_authoritative_template(), d306_instrumentation_spec, gate=gate
    )


@pytest.fixture(scope="module")
def instrumented_path(
    instrumented: EI.InstrumentedWorkbook, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    path = tmp_path_factory.mktemp("d3_06_task7") / "instrumented.xlsx"
    path.write_bytes(instrumented.instrumented_bytes)
    return path


@pytest.fixture(scope="module")
def contract_with_d306() -> Any:
    """D3-6 已接入后的真实契约 —— 磁盘契约本身（且与源码现算逐字节一致）。

    ✅ Task 10 迁移：D3-6/D3-4/D3-5 开关已默认打开并重生成磁盘契约，这里不再 monkeypatch
    出一份「D3-2 + D3-6」两张 sheet 的形状（那是 Task 7 时开关仍默认 False 的权宜做法，
    现在会与真实发布面不符）。断言按 sheet_key 查 D3-6 在场，不按总张数（总张数随后续
    D3-7/D3-1 接入还会变，与本文件验证的 D3-6 机制无关）。
    """
    contract = ENTRY.assert_contract_file_matches_source()
    sheet_keys = [sheet.sheet_key for sheet in contract.sheets]
    assert D306.SHEET_KEY_D306 in sheet_keys, f"默认契约应含 D3-6（{D306.SHEET_KEY_D306}），实得 {sheet_keys}"
    assert sheet_keys[0] == ENTRY.SHEET_KEY, "D3-2 自身应保持为契约第一张 sheet（扩容面只追加）"
    return contract


@pytest.fixture(scope="module")
def d306_binding(d306_instrumentation_spec: EI.ExcelInstrumentationSpec) -> X.ExcelIdentityBinding:
    return X.ExcelIdentityBinding(
        table_name=D306.SPEC_D306.table_name,
        uuid_column=D306.SPEC_D306.uuid_col,
        table_key=D306.SPEC_D306.table_key,
    )


class TestInjectionProducesRealIdentityCarrier:
    """注入前原始模板没有任何 D3-6 的 Table/UUID 列/defined name（真实缺失，不是假设）；
    注入后必须真实出现，且 `resolve_managed_region` 能在注入产物上定位到它。
    """

    def test_raw_template_has_no_d306_table_before_injection(self) -> None:
        raw = ENTRY.read_authoritative_template()
        with zipfile.ZipFile(__import__("io").BytesIO(raw)) as zf:
            tables = X._tables_of(zf)
        names = {t.get("name") or t.get("display_name") for t in tables}
        assert D306.SPEC_D306.table_name not in names, (
            f"原始权威模板不该已经含有 {D306.SPEC_D306.table_name!r}——"
            "它必须由 instrumentation 注入，若模板已自带说明本判据的前提假设错了"
        )

    def test_instrumented_bytes_contain_the_declared_table(
        self, instrumented: EI.InstrumentedWorkbook
    ) -> None:
        with zipfile.ZipFile(__import__("io").BytesIO(instrumented.instrumented_bytes)) as zf:
            tables = X._tables_of(zf)
        names = {t.get("name") or t.get("display_name") for t in tables}
        assert D306.SPEC_D306.table_name in names, (
            f"注入后必须真实出现 {D306.SPEC_D306.table_name!r}，实测 Table 清单：{sorted(n for n in names if n)}"
        )

    def test_resolve_managed_region_locates_it_on_instrumented_bytes(
        self,
        instrumented: EI.InstrumentedWorkbook,
        contract_with_d306: Any,
        d306_binding: X.ExcelIdentityBinding,
    ) -> None:
        """这是"整册 materialize"链路里 `verify_unmanaged_regions` 真正依赖的定位步骤——
        在原始模板上必 fail-closed（上一条已证），在注入产物上必须真实定位到。
        """
        with zipfile.ZipFile(__import__("io").BytesIO(instrumented.instrumented_bytes)) as zf:
            region = X.resolve_managed_region(zf, contract=contract_with_d306, binding=d306_binding)
        assert region is not None
        assert region.sheet_part, "受管区必须解析出一个具体的 sheet part"


class TestVerifyUnmanagedRegionsIsRealNotVacuous:
    """`verify_unmanaged_regions` 的覆盖计数必须落到非空/非零的实测值——防"手搓最小 xlsx
    上未管理区域恒为空集，比对必然通过"这一类假绿（同 test_task42 的"不是空集恒等价"判据）。
    """

    def test_identity_before_equals_after_is_equivalent(
        self,
        instrumented_path: Path,
        contract_with_d306: Any,
        d306_binding: X.ExcelIdentityBinding,
    ) -> None:
        with zipfile.ZipFile(instrumented_path) as zf:
            region = X.resolve_managed_region(zf, contract=contract_with_d306, binding=d306_binding)
        report = X.verify_unmanaged_regions(
            before=instrumented_path,
            after=instrumented_path,
            contract=contract_with_d306,
            region=region,
            binding=d306_binding,
        )
        assert report.equivalent is True, report.details

    def test_coverage_counts_are_not_all_zero(
        self,
        instrumented_path: Path,
        contract_with_d306: Any,
        d306_binding: X.ExcelIdentityBinding,
    ) -> None:
        """至少要有非零的覆盖计数——否则这条"未管理区域比对"根本没有实质性地比较任何东西。"""
        with zipfile.ZipFile(instrumented_path) as zf:
            region = X.resolve_managed_region(zf, contract=contract_with_d306, binding=d306_binding)
        report = X.verify_unmanaged_regions(
            before=instrumented_path,
            after=instrumented_path,
            contract=contract_with_d306,
            region=region,
            binding=d306_binding,
        )
        coverage = dict(report.details["coverage"])
        positive = {name: count for name, count in coverage.items() if count > 0}
        assert positive, f"全部 aspect 覆盖计数为 0——未管理区域比对没有实质比较到任何字节：{coverage}"
        assert coverage.get("other_sheet_parts", 0) > 0, (
            "D3 模板还有其余 11 张 sheet（D3-2/D3-1/程序表/附注等），它们的 part 必须落在"
            "『其余 sheet』这个 aspect 里，否则说明比对面被削掉了"
        )

    def test_mutation_touching_an_unrelated_sheet_is_detected(
        self,
        instrumented: EI.InstrumentedWorkbook,
        instrumented_path: Path,
        contract_with_d306: Any,
        d306_binding: X.ExcelIdentityBinding,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """变异（design.md Property 10 反证）：改动一个与 D3-6 完全无关的其他 sheet
        （D3-1 审定表 A1，注入产物里两者都是未管理区域）的一个字面量字符串，
        `verify_unmanaged_regions` 必须判**不等价**并指出具体差异位置——证明这不是
        "手搓最小 xlsx 上未管理区域恒为空集，比对必然通过"那种假绿。
        """
        from app.services.workpaper_sync.excel_extract import _sheet_part_map

        with zipfile.ZipFile(instrumented_path) as zf:
            sheets, _ = _sheet_part_map(zf)
        d31_entry = next((s for s in sheets if s.get("name") == "审定表D3-1"), None)
        assert d31_entry, "定位不到 D3-1 的 sheet part（未管理区域变异的目标 sheet）"
        target = d31_entry["rel_target"].lstrip("/")
        d31_part = target if target.startswith("xl/") else f"xl/{target}"

        def _flip_a1_text(data: bytes, *, sheet_part: str) -> bytes:
            import io

            src = io.BytesIO(data)
            out = io.BytesIO()
            with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    raw = zin.read(item.filename)
                    if item.filename == sheet_part:
                        text = raw.decode("utf-8")
                        # 用最不依赖具体字面量内容的方式扰动：在 sheetData 开始标签后插入
                        # 一个新的 <row> 元素（结构性变化，任何 xlsx 都必然可插且必被检测到）。
                        marker = "<sheetData>"
                        assert marker in text, f"{sheet_part} 缺 <sheetData> 标签"
                        mutated_text = text.replace(
                            marker,
                            marker + '<row r="9999"><c r="A9999" t="str"><v>__task7_probe__</v></c></row>',
                            1,
                        )
                        raw = mutated_text.encode("utf-8")
                    zout.writestr(item, raw)
            return out.getvalue()

        mutated_bytes = _flip_a1_text(instrumented.instrumented_bytes, sheet_part=d31_part)
        assert mutated_bytes != instrumented.instrumented_bytes, "变异未生效（字节逐字节相同）"
        mutated_path = tmp_path_factory.mktemp("d3_06_mutation") / "mutated_unmanaged_sheet.xlsx"
        mutated_path.write_bytes(mutated_bytes)

        with zipfile.ZipFile(instrumented_path) as zf:
            region = X.resolve_managed_region(zf, contract=contract_with_d306, binding=d306_binding)
        report = X.verify_unmanaged_regions(
            before=instrumented_path,
            after=mutated_path,
            contract=contract_with_d306,
            region=region,
            binding=d306_binding,
        )
        assert report.equivalent is False, (
            "改动了与 D3-6 无关的另一张 sheet（D3-1）的字节内容，"
            "verify_unmanaged_regions 必须判不等价 —— 若仍判等价说明比对面被削掉了"
        )
        assert report.details, "不等价时必须给出首个差异位置的细节"
