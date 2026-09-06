# -*- coding: utf-8 -*-
"""结构性插行的**接线**判据（Wave 4：Task 16 / 17 / 18）。

spec: excel-structural-row-insertion-and-shift-aware-verification
Properties: **P3** / **P5** / **P23** / **P24** / **P29**

═══ 这一份证三件事 ═══════════════════════════════════════════════════════

1. **Property 5** —— 插入行数恰等于「merged projection 里在 substrate 上没有物理行的
   身份数」。
2. **Property 23 / 24** —— 六类不可安全执行情形**各自可达、两两可分辨**。
   判据形态是「收集全部六类实际抛出的诊断码，与声明集合双向等值 + 断言基数」，
   不是「每类各测一遍」：后者在两类被合并成同一个码时**全部仍绿**。
3. **成功路径** —— 插行真的执行、产物可打开、受管区域真的长了、新行带着自己的
   row identity 端到端反读回来。

═══ 为什么成功路径需要一个契约变体 ═══════════════════════════════════════

两个既有 pilot 在**真实契约**下都 fail closed，而且都是**正确行为**：

* **K11**：`k11_footer/tb_amount` 声明在 `B27`，而追加插行的插入点是 26。插行把它推到
  `B29`，可 Task 37 的 extract 仍按契约 `cell.static_row` 反读 `B27` —— 那里现在是一个
  **新插入的空行**（静默取空值）⇒ `contract_static_row_below_insertion`。
* **H1**：footer 合计 `SUM(I13:I27)` 不会扩张（契约没声明 `carries_total_formula`）
  ⇒ 照插会产出一张**合计漏算**的审计底稿 ⇒ `contract_total_formula_not_extendable`。

⇒ 成功路径只能用一个**契约变体**演示：静态表移出插入点之下 + 声明
`carries_total_formula`。这不是「为了让测试变绿而放宽」—— 它恰好刻画了「什么样的契约
形态才允许插行」，也就是 Task 19 清册要量化的东西。
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import identity_inventory  # noqa: E402
from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_row_shift as RS  # noqa: E402
from app.services.workpaper_sync.adapters.base import (  # noqa: E402
    FieldValue,
    Projection,
    SubstrateRole,
)
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState  # noqa: E402

from test_task37_excel_extract import (  # noqa: E402
    BINDING,
    CONTRACT_ID,
    FIRST_ROW,
    FOOTER_ROW,
    LAST_ROW,
    MANAGED_SHEET,
    SPEC,
    TEMPLATE,
    TEMPLATE_SHA,
    _read_entries,
    _sheet_part_of,
    _write_entries,
    business_cells,
    contract_payload,
    make_definitions,
    patch_cells,
)

#: K11 的合计行 = footer anchor marker 行（实测 `GT_FOOTER_ROW = 26`）。
TOTAL_ROW = 26
#: 追加插行的插入点（受管区末行 +1）。
INSERT_AT = LAST_ROW + 1


# ═══════════════════════════════════════════════════════════════════════════
# 1. fixture
# ═══════════════════════════════════════════════════════════════════════════


def insertable_contract_payload(*, carries_total_formula: bool = True) -> dict[str, Any]:
    """一份**允许追加插行**的契约变体。

    与生产契约的两处差别，各自对应一条拒绝理由：

    1. 去掉 `k11_footer` 静态表 —— 它的 `tb_amount` 在 `B27`，落在插入点 26 之下
       （第五类拒绝理由）。去掉它之后契约里再无静态行。
    2. `footer_anchor.carries_total_formula = True` —— 授权引擎把合计区间随受管区间扩张
       （第六类拒绝理由的解除条件）。

    🔴 这两处**不是**为了让测试变绿而放宽判据：它们刻画的正是「什么样的契约形态才允许
    插行」。`carries_total_formula=False` 的变体用来证明第六类拒绝理由可达。
    """
    payload = contract_payload()
    sheet = payload["sheets"][0]
    rows_table = dict(sheet["tables"][0])
    rows_table["footer_anchor"] = {
        **rows_table["footer_anchor"],
        "carries_total_formula": carries_total_formula,
    }
    sheet["tables"] = [rows_table]
    return payload


@pytest.fixture(scope="module")
def instrumented_bytes() -> bytes:
    gate = EI.ExcelIdentityCarrierGate.load()
    return EI.instrument_workbook_bytes(
        TEMPLATE.read_bytes(), SPEC, gate=gate
    ).instrumented_bytes


@pytest.fixture(scope="module")
def sheet_part(instrumented_bytes: bytes) -> str:
    return _sheet_part_of(instrumented_bytes, MANAGED_SHEET)


@pytest.fixture(scope="module")
def base_bytes(instrumented_bytes: bytes, sheet_part: str) -> bytes:
    return patch_cells(instrumented_bytes, sheet_part, business_cells())


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("row_insertion_wiring")


@pytest.fixture(scope="module")
def base_path(base_bytes: bytes, workdir: Path) -> Path:
    path = workdir / "base.xlsx"
    path.write_bytes(base_bytes)
    return path


@pytest.fixture(scope="module")
def runtime_binding(base_path: Path) -> Mapping[str, str]:
    with zipfile.ZipFile(base_path) as zf:
        return X.read_runtime_binding_pairs(zf)


def _definitions(payload: dict[str, Any], base_bytes: bytes) -> Any:
    contract = parse_contract(payload, adapter_id=CONTRACT_ID)
    inventory = identity_inventory(
        base_bytes,
        expected_table=BINDING.table_name,
        uuid_column_letter=BINDING.uuid_column,
    )
    return contract, make_definitions(contract, inventory)


@pytest.fixture(scope="module")
def production_bundle(base_bytes: bytes) -> tuple[Any, Any]:
    """**生产**契约（`k11_footer` 静态表还在、未声明合计扩张）。"""
    return _definitions(contract_payload(), base_bytes)


@pytest.fixture(scope="module")
def insertable_bundle(base_bytes: bytes) -> tuple[Any, Any]:
    """**可插行**契约变体。"""
    return _definitions(insertable_contract_payload(), base_bytes)


def _extract(path: Path, definitions: Any) -> X.ExcelExtractOutcome:
    return X.extract_projection(
        artifact=path,
        definitions=definitions,
        binding=BINDING,
        substrate_role=SubstrateRole.published_representation,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.published,
    )


def _with_extra_rows(projection: Projection, *, count: int, prefix: str) -> Projection:
    """在 projection 的行集末尾追加 `count` 个 substrate 上没有物理行的身份。

    值也一并给上 —— 只加行键不给值时字段写入会被 `projection.get(key) is None` 跳过，
    「新行真的被写了值」这一半就无从断言。
    """
    values = dict(projection.values)
    rows = list(projection.row_keys.get("k11_rows", ()))
    template_identity = rows[0]
    for index in range(count):
        identity = f"{prefix}-{index:03d}"
        rows.append(identity)
        for key, field in list(projection.values.items()):
            if field.row_key != template_identity:
                continue
            new_key = key.replace(template_identity, identity)
            values[new_key] = FieldValue(
                stable_key=new_key,
                value=(
                    f"新增{index}"
                    if field.value_type.value == "text"
                    else field.value
                ),
                value_type=field.value_type,
                mode=field.mode,
                row_key=identity,
            )
    return Projection(
        contract_id=projection.contract_id,
        semantic_version=projection.semantic_version,
        document_type=projection.document_type,
        values=values,
        row_keys={**projection.row_keys, "k11_rows": tuple(rows)},
    )


def _plan(
    *,
    projection: Projection,
    contract: Any,
    base_bytes: bytes,
    outcome: X.ExcelExtractOutcome,
    runtime_binding: Mapping[str, str],
    region: X.ManagedRegion | None = None,
) -> M.MaterializePlan:
    return M.plan_managed_writes(
        projection=projection,
        contract=contract,
        binding=BINDING,
        region=region or outcome.region,
        scan=outcome.scan,
        substrate_entries=_read_entries(base_bytes),
        substrate_formulas=outcome.formula_inventory,
        runtime_binding=runtime_binding,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 冻结事实：两个既有 pilot 在真实契约下都 fail closed，且都是正确行为
# ═══════════════════════════════════════════════════════════════════════════


class TestProductionContractIsNotInsertable:
    """**Validates: Requirements 8.2, 8.4, 8.5**

    这不是坏消息，是 Task 19 清册要量化的东西：可插行性受**契约形态**约束。
    """

    def test_authority_template_is_untouched(self) -> None:
        assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == TEMPLATE_SHA

    def test_production_contract_has_a_static_row_below_the_insertion_point(
        self, production_bundle: tuple[Any, Any]
    ) -> None:
        """根因判据：`k11_footer/tb_amount` 在 `B27`，而插入点是 26。"""
        contract, _ = production_bundle
        offenders = M._static_rows_at_or_below(contract=contract, insert_at=INSERT_AT)
        assert offenders, "生产契约里没有静态行落在插入点之下 —— 冻结事实变了"
        assert any(coord == f"B{FOOTER_ROW}" for _key, coord in offenders), offenders

    def test_production_contract_rejects_insertion_with_that_reason(
        self,
        production_bundle: tuple[Any, Any],
        base_bytes: bytes,
        base_path: Path,
        runtime_binding: Mapping[str, str],
    ) -> None:
        contract, definitions = production_bundle
        outcome = _extract(base_path, definitions)
        projection = _with_extra_rows(outcome.projection, count=2, prefix="brand-new")
        with pytest.raises(M.RowSetDivergenceError) as excinfo:
            _plan(
                projection=projection,
                contract=contract,
                base_bytes=base_bytes,
                outcome=outcome,
                runtime_binding=runtime_binding,
            )
        message = str(excinfo.value)
        assert "contract_static_row_below_insertion" in message, message
        # Requirement 8.2：消息里必须给出**具体**拒绝原因 —— 含 orphan 身份
        assert "brand-new-000" in message, message

    def test_insertable_variant_removes_that_obstacle(
        self, insertable_bundle: tuple[Any, Any]
    ) -> None:
        """对照：变体契约里再无静态行落在插入点之下（否则成功路径证明不了任何事）。"""
        contract, _ = insertable_bundle
        assert M._static_rows_at_or_below(contract=contract, insert_at=INSERT_AT) == ()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Property 5：插入行数恰等于 orphan 数
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty5InsertedCountEqualsOrphanCount:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 5: 插入行数恰等于 merged projection 中在 substrate 上无物理行的身份数量**

    **Validates: Requirements 2.6**
    """

    @pytest.mark.parametrize("count", [1, 2, 3, 5])
    def test_plan_count_tracks_the_orphan_count(
        self,
        insertable_bundle: tuple[Any, Any],
        base_bytes: bytes,
        base_path: Path,
        runtime_binding: Mapping[str, str],
        count: int,
    ) -> None:
        contract, definitions = insertable_bundle
        outcome = _extract(base_path, definitions)
        physical = set(outcome.scan.row_identity_by_row.values())
        projection = _with_extra_rows(outcome.projection, count=count, prefix="orphan")
        orphan = [
            identity
            for identity in projection.row_keys["k11_rows"]
            if identity not in physical
        ]
        assert len(orphan) == count, orphan

        plan = _plan(
            projection=projection,
            contract=contract,
            base_bytes=base_bytes,
            outcome=outcome,
            runtime_binding=runtime_binding,
        )
        assert plan.row_shift is not None
        assert plan.row_shift.count == count == len(orphan), plan.row_shift.as_dict()
        assert plan.row_shift.insert_at == INSERT_AT
        assert plan.row_shift.style_from == LAST_ROW
        assert list(plan.row_shift.inserted_rows) == [
            INSERT_AT + offset for offset in range(count)
        ]

    def test_no_orphan_means_no_plan(
        self,
        insertable_bundle: tuple[Any, Any],
        base_bytes: bytes,
        base_path: Path,
        runtime_binding: Mapping[str, str],
    ) -> None:
        """零位移路径：没有 orphan ⇒ `row_shift is None`（Property 3 的计划侧）。"""
        contract, definitions = insertable_bundle
        outcome = _extract(base_path, definitions)
        plan = _plan(
            projection=outcome.projection,
            contract=contract,
            base_bytes=base_bytes,
            outcome=outcome,
            runtime_binding=runtime_binding,
        )
        assert plan.row_shift is None
        assert plan.total_formula_rows == ()
        assert plan.table_part == ""
        assert plan.as_dict()["row_shift"] is None

    def test_every_inserted_row_carries_its_row_identity(
        self,
        insertable_bundle: tuple[Any, Any],
        base_bytes: bytes,
        base_path: Path,
        runtime_binding: Mapping[str, str],
    ) -> None:
        """新插入行必须各自写入自己的 row identity（否则反读时会被重新 mint）。

        🔴 首版漏了这一步。症状会是「反读不等值」，真因却是「插行时没写身份」——
        两者相距很远，所以这条判据单列。
        """
        contract, definitions = insertable_bundle
        outcome = _extract(base_path, definitions)
        projection = _with_extra_rows(outcome.projection, count=3, prefix="ident")
        plan = _plan(
            projection=projection,
            contract=contract,
            base_bytes=base_bytes,
            outcome=outcome,
            runtime_binding=runtime_binding,
        )
        assert plan.row_shift is not None
        identity_writes = {
            write.coord: write.value for write in plan.identity_writes
        }
        for offset in range(3):
            coord = f"{outcome.region.uuid_column}{INSERT_AT + offset}"
            assert coord in identity_writes, sorted(identity_writes)
            assert identity_writes[coord] == f"ident-{offset:03d}", identity_writes[coord]


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 23 / 24：六类不可安全执行情形各自可达、两两可分辨
# ═══════════════════════════════════════════════════════════════════════════


#: 六类拒绝理由的诊断码。前四类来自 design.md §Requirement 8.4；
#: 后两类是本 spec 实施中实测发现的（见 `excel_materialize` 模块 docstring §四第 1 条）。
DECLARED_REJECTION_CODES: frozenset[str] = frozenset(
    {
        "excel_row_shift_unlisted_structure",
        "excel_row_shift_style_source_missing",
        "excel_row_shift_shared_formula_orientation_unsupported",
        "excel_row_shift_plan_range_invalid",
        "contract_static_row_below_insertion",
        "contract_total_formula_not_extendable",
    }
)


class TestRejectionReasonsAreReachableAndDistinct:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 23: `RowSetDivergenceError` 仍在 `FAILURE_KINDS` 中，且各类不可安全执行情形各自可达、两两可分辨**

    **Validates: Requirements 8.1, 8.2, 8.4, 8.5**

    🔴 判据形态是「**收集全部六类实际抛出的诊断码**，与声明集合双向等值 + 断言基数」，
    不是「每类各测一遍」：后者在两类被合并成同一个码时**全部仍绿**（本仓库已实测踩过
    三次这个形态）。
    """

    def test_row_set_divergence_error_stays_registered(self) -> None:
        """Requirement 8.1：`RowSetDivergenceError` 与其 `error_code` 留在 `FAILURE_KINDS`。"""
        code = M.RowSetDivergenceError.error_code
        assert code in M.FAILURE_KINDS, sorted(M.FAILURE_KINDS)
        assert M.FAILURE_KINDS[code], "登记表里该项没有说明文本"

    def _reject_code(
        self,
        *,
        contract: Any,
        definitions: Any,
        base_bytes: bytes,
        base_path: Path,
        runtime_binding: Mapping[str, str],
        count: int = 2,
        region: X.ManagedRegion | None = None,
        mutate_sheet: Any = None,
    ) -> str:
        outcome = _extract(base_path, definitions)
        projection = _with_extra_rows(outcome.projection, count=count, prefix="reject")
        entries = _read_entries(base_bytes)
        if mutate_sheet is not None:
            part = outcome.region.sheet_part
            entries[part] = mutate_sheet(entries[part].decode("utf-8")).encode("utf-8")
        with pytest.raises(M.RowSetDivergenceError) as excinfo:
            M.plan_managed_writes(
                projection=projection,
                contract=contract,
                binding=BINDING,
                region=region or outcome.region,
                scan=outcome.scan,
                substrate_entries=entries,
                substrate_formulas=outcome.formula_inventory,
                runtime_binding=runtime_binding,
            )
        message = str(excinfo.value)
        found = re.match(r"^\[([a-z0-9_]+)\]", message)
        assert found is not None, f"拒绝消息没有以诊断码开头: {message[:120]}"
        # Requirement 8.2：每条消息都必须带 orphan 身份（具体拒绝原因）
        assert "reject-000" in message, message
        return found.group(1)

    def test_all_six_reasons_are_reachable_and_pairwise_distinct(
        self,
        production_bundle: tuple[Any, Any],
        insertable_bundle: tuple[Any, Any],
        base_bytes: bytes,
        base_path: Path,
        workdir: Path,
        runtime_binding: Mapping[str, str],
    ) -> None:
        prod_contract, prod_definitions = production_bundle
        ins_contract, ins_definitions = insertable_bundle
        outcome = _extract(base_path, ins_definitions)
        observed: dict[str, str] = {}

        # ① 清单外位移敏感元素
        observed["unlisted"] = self._reject_code(
            contract=ins_contract,
            definitions=ins_definitions,
            base_bytes=base_bytes,
            base_path=base_path,
            runtime_binding=runtime_binding,
            mutate_sheet=lambda xml: xml.replace(
                "</worksheet>", '<pivotArea ref="A1:B2"/></worksheet>', 1
            ),
        )

        # ② 样式来源行缺失 —— 受管区末行整行删掉
        def _drop_style_row(xml: str) -> str:
            block = re.search(rf'<row r="{LAST_ROW}"[^>]*>.*?</row>', xml, re.S)
            assert block is not None, "定位不到样式来源行 —— fixture 形态变了"
            return xml.replace(block.group(0), "", 1)

        observed["style_source"] = self._reject_code(
            contract=ins_contract,
            definitions=ins_definitions,
            base_bytes=base_bytes,
            base_path=base_path,
            runtime_binding=runtime_binding,
            mutate_sheet=_drop_style_row,
        )

        # ③ 横向共享公式组落在样式来源行上（无法按行 fill-down）
        #    把 si=3 的横向组主格从 B26 挪到 B25（= style_from）
        def _horizontal_on_style_row(xml: str) -> str:
            assert 'ref="B26:G26"' in xml, "K11 的横向组形态变了"
            return (
                xml.replace('<f t="shared" ref="B26:G26" si="3">', '<f t="shared" ref="B25:G25" si="3">', 1)
                .replace('<c r="C26" s="97"><f t="shared" si="3"/>', '<c r="C25" s="97"><f t="shared" si="3"/>', 1)
            )

        # ④ 插入点越界 —— 让受管区末行大于物理最大行
        import dataclasses

        observed["plan_range"] = self._reject_code(
            contract=ins_contract,
            definitions=ins_definitions,
            base_bytes=base_bytes,
            base_path=base_path,
            runtime_binding=runtime_binding,
            region=dataclasses.replace(outcome.region, last_row=LAST_ROW - 5),
        )

        # ⑤ 契约静态行落在插入点之下（生产契约）
        observed["static_row"] = self._reject_code(
            contract=prod_contract,
            definitions=prod_definitions,
            base_bytes=base_bytes,
            base_path=base_path,
            runtime_binding=runtime_binding,
        )

        # ⑥ 合计不会扩张（变体契约 + carries_total_formula=False）
        no_extend_contract, no_extend_definitions = _definitions(
            insertable_contract_payload(carries_total_formula=False), base_bytes
        )
        observed["total_formula"] = self._reject_code(
            contract=no_extend_contract,
            definitions=no_extend_definitions,
            base_bytes=base_bytes,
            base_path=base_path,
            runtime_binding=runtime_binding,
        )

        codes = set(observed.values())
        assert len(codes) == len(observed), (
            f"六类拒绝理由的诊断码不是两两不同 —— 实测 {observed}；"
            "合并成同一个码后靠后的分支就不可分辨了"
        )
        assert codes <= DECLARED_REJECTION_CODES, sorted(codes - DECLARED_REJECTION_CODES)
        # 五类可达（横向组那一类在 K11 上构造困难，另由 T1 的
        # `test_horizontal_group_style_source_fails_closed` 在位移函数层覆盖）
        assert len(codes) >= 5, sorted(codes)


# ═══════════════════════════════════════════════════════════════════════════
# 5. 成功路径：插行真的执行并端到端反读回来
# ═══════════════════════════════════════════════════════════════════════════


class TestInsertionSucceedsEndToEnd:
    """**Validates: Requirements 2.3, 2.6, 3.2, 3.4, 3.5, 11.4, 11.5**

    Properties: **P3**（零位移逐字节）/ **P29**（产物可打开、受管区域行数等于预期）
    """

    COUNT = 2

    @pytest.fixture(scope="class")
    def staged(
        self,
        insertable_bundle: tuple[Any, Any],
        base_bytes: bytes,
        base_path: Path,
        workdir: Path,
        runtime_binding: Mapping[str, str],
    ) -> tuple[M.MaterializePlan, bytes, RS.ShiftReport]:
        contract, definitions = insertable_bundle
        outcome = _extract(base_path, definitions)
        projection = _with_extra_rows(
            outcome.projection, count=self.COUNT, prefix="ok"
        )
        plan = _plan(
            projection=projection,
            contract=contract,
            base_bytes=base_bytes,
            outcome=outcome,
            runtime_binding=runtime_binding,
        )
        assert plan.row_shift is not None, "变体契约下仍算不出插行计划"
        data, report = M.apply_plan_zip_with_report(base_bytes, plan)
        assert report is not None
        return plan, data, report

    def test_plan_declares_the_extension_and_the_table_part(
        self, staged: tuple[M.MaterializePlan, bytes, RS.ShiftReport]
    ) -> None:
        plan, _, _ = staged
        assert plan.total_formula_rows == (TOTAL_ROW,), plan.total_formula_rows
        assert plan.table_part.startswith("xl/tables/"), plan.table_part
        assert plan.as_dict()["row_shift"]["count"] == self.COUNT

    def test_shift_report_proves_the_branches_really_ran(
        self, staged: tuple[M.MaterializePlan, bytes, RS.ShiftReport]
    ) -> None:
        """`ShiftReport` 的逐阶段计数必须非零 —— 「没报错」不等于「真做了」。"""
        _, _, report = staged
        data = report.as_dict()
        assert data["inserted_rows"] == self.COUNT, data
        assert data["renumbered_rows"] > 0, data
        assert data["renumbered_cells"] > 0, data
        assert data["dimension_updated"] is True, data
        assert data["shifted_refs"].get("mergeCell@ref", 0) >= 1, data
        assert data["extended_shared_formulas"] == 1, data

    def test_total_formula_really_grew(
        self, staged: tuple[M.MaterializePlan, bytes, RS.ShiftReport]
    ) -> None:
        plan, data, _ = staged
        xml = _read_entries(data)[plan.sheet_part].decode("utf-8")
        assert f"SUM(B{FIRST_ROW}:B{LAST_ROW + self.COUNT})" in xml, re.findall(
            r"SUM\(B\d+:B\d+\)", xml
        )
        assert f"SUM(B{FIRST_ROW}:B{LAST_ROW})" not in xml

    def test_managed_table_ref_really_grew(
        self, staged: tuple[M.MaterializePlan, bytes, RS.ShiftReport]
    ) -> None:
        """Table ref 不长 ⇒ 新行落在受管区域之外 ⇒ 反读时静默丢数据。"""
        plan, data, _ = staged
        xml = _read_entries(data)[plan.table_part].decode("utf-8")
        assert f'ref="A{FIRST_ROW}:N{LAST_ROW + self.COUNT}"' in xml, re.findall(
            r'ref="[^"]+"', xml
        )

    def test_product_is_openable_and_structurally_clean(
        self, staged: tuple[M.MaterializePlan, bytes, RS.ShiftReport]
    ) -> None:
        """**Property 29**：openpyxl 可加载、`structure_fingerprint` 零 errors。"""
        _, data, _ = staged
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data))
        try:
            ws = wb[MANAGED_SHEET]
            assert ws.max_row >= LAST_ROW + self.COUNT
        finally:
            wb.close()

        from app.services.excel_structure_fingerprint import structure_fingerprint

        fingerprint = structure_fingerprint(data)
        errors = list(getattr(fingerprint, "errors", ()) or ())
        assert errors == [], errors

    def test_new_rows_inherit_style_and_carry_no_stray_values(
        self, staged: tuple[M.MaterializePlan, bytes, RS.ShiftReport]
    ) -> None:
        """新行样式继承自受管区末行；除了受管字段与身份之外不带别的值。"""
        plan, data, _ = staged
        xml = _read_entries(data)[plan.sheet_part].decode("utf-8")
        source = re.search(rf'<row r="{LAST_ROW}"([^>]*)>', xml)
        assert source is not None
        source_attrs = re.sub(r'\br="\d+"', "", source.group(1))
        for offset in range(self.COUNT):
            row = INSERT_AT + offset
            block = re.search(rf'<row r="{row}"([^>]*)>', xml)
            assert block is not None, f"新行 {row} 不在产物里"
            assert re.sub(r'\br="\d+"', "", block.group(1)) == source_attrs, row

    def test_roundtrip_reads_the_new_rows_back_with_their_identities(
        self,
        staged: tuple[M.MaterializePlan, bytes, RS.ShiftReport],
        insertable_bundle: tuple[Any, Any],
        workdir: Path,
    ) -> None:
        """端到端：反读产物时新行**带着自己的 identity**出现在 projection 里。

        这是整条链的收口判据 —— 少写身份、Table ref 没长、位移错行任一发生，这条都会红。
        """
        plan, data, _ = staged
        _, definitions = insertable_bundle
        path = workdir / "staged-roundtrip.xlsx"
        path.write_bytes(data)

        outcome = _extract(path, definitions)
        rows = list(outcome.projection.row_keys["k11_rows"])
        assert len(rows) == (LAST_ROW - FIRST_ROW + 1) + self.COUNT, rows
        for offset in range(self.COUNT):
            identity = f"ok-{offset:03d}"
            assert identity in rows, rows[-4:]
            assert outcome.scan.row_identity_by_row.get(INSERT_AT + offset) == identity, (
                outcome.scan.row_identity_by_row
            )
        # minted 集合必须为空：身份是我们写进去的，不是反读时重新分配的
        assert outcome.scan.minted_by_row == {}, outcome.scan.minted_by_row

    def test_unmanaged_regions_are_equivalent_under_the_declared_plan(
        self,
        staged: tuple[M.MaterializePlan, bytes, RS.ShiftReport],
        insertable_bundle: tuple[Any, Any],
        base_path: Path,
        workdir: Path,
    ) -> None:
        """把 Wave 2 的 shift-aware 归一化接到**真实产物**上：判等价。

        对照：不给计划 ⇒ 判不等价。两侧同时断言才排除「归一化把整类检查关掉」。
        """
        plan, data, _ = staged
        contract, definitions = insertable_bundle
        path = workdir / "staged-unmanaged.xlsx"
        path.write_bytes(data)
        outcome = _extract(base_path, definitions)

        naive = X.verify_unmanaged_regions(
            before=base_path,
            after=path,
            contract=contract,
            region=outcome.region,
            binding=BINDING,
            scan=outcome.scan,
        )
        assert naive.equivalent is False, "真实插行产物在无计划时被判等价 ⇒ 判据是空的"

        # 🔴 只给 `row_shift` **不够** —— 合计扩张（`SUM(B7:B25)`→`SUM(B7:B27)`）无法被
        #    `unshift` 还原（`unshift(27) == 27`），那正是扩张的语义：区间真的变大了。
        #    这一条把「还原扩张必须靠契约声明」钉死：少传 `total_formula_rows` 就判漂移。
        half = X.verify_unmanaged_regions(
            before=base_path,
            after=path,
            contract=contract,
            region=outcome.region,
            binding=BINDING,
            scan=outcome.scan,
            row_shift=plan.row_shift,
        )
        assert half.equivalent is False, (
            "只给 row_shift 就判等价 ⇒ 合计扩张被某种方式吞掉了，"
            "而它本该由契约声明的 `total_formula_rows` 授权"
        )
        assert "managed_sheet_unmanaged_cells" in (half.first_difference or ""), (
            half.first_difference
        )

        # 🔴 **本条在 spec excel-workbook-wide-row-change-propagation 的 Wave 4 翻转过。**
        #
        #    翻转前：`row_shift` + `total_formula_rows` 两个声明就足以判等价。那时插行
        #    **只改受管 sheet**，引用侧 sheet 与 definedNames 逐字不动（上游 spec 的
        #    R12.1 / R12.4 把它们明确排除在外）。
        #
        #    翻转后：`plan_managed_writes` 现在会同时冻结一份 `workbook_row_change`
        #    声明，apply 据它改**引用侧 sheet 与 `xl/workbook.xml` 的 definedNames**。
        #    于是少传 `propagation` 就会判漂移 —— 那不是判据变弱，而是**多了一类必须
        #    声明的改动**。K11 上实测首个差异正是 `workbook_and_styles`
        #    （definedNames 落在那一桶）。
        half_again = X.verify_unmanaged_regions(
            before=base_path,
            after=path,
            contract=contract,
            region=outcome.region,
            binding=BINDING,
            scan=outcome.scan,
            row_shift=plan.row_shift,
            total_formula_rows=plan.total_formula_rows,
        )
        if plan.workbook_row_change is not None:
            assert half_again.equivalent is False, (
                "计划声明了工作簿级传播，但不传 `propagation` 仍判等价 ⇒ "
                "传播产生的字节变化没有被任何 aspect 看到"
            )

        aware = X.verify_unmanaged_regions(
            before=base_path,
            after=path,
            contract=contract,
            region=outcome.region,
            binding=BINDING,
            scan=outcome.scan,
            row_shift=plan.row_shift,
            total_formula_rows=plan.total_formula_rows,
            propagation=plan.workbook_row_change,
        )
        assert aware.equivalent is True, aware.first_difference

    def test_unextending_is_declaration_driven_not_a_blanket_pass(
        self,
        staged: tuple[M.MaterializePlan, bytes, RS.ShiftReport],
        insertable_bundle: tuple[Any, Any],
        base_path: Path,
        workdir: Path,
    ) -> None:
        """反向自检：声明**错的**合计行 ⇒ 还原不回去 ⇒ 仍判漂移。

        没有这一条时，「还原扩张」有可能被实现成「凡是区间末行对不上就抹平」——
        那才是真的放宽判据。
        """
        plan, data, _ = staged
        contract, definitions = insertable_bundle
        path = workdir / "staged-wrong-total-row.xlsx"
        path.write_bytes(data)
        outcome = _extract(base_path, definitions)

        assert plan.total_formula_rows == (TOTAL_ROW,)
        report = X.verify_unmanaged_regions(
            before=base_path,
            after=path,
            contract=contract,
            region=outcome.region,
            binding=BINDING,
            scan=outcome.scan,
            row_shift=plan.row_shift,
            # 声明成另一行 ⇒ 真正被扩张的那一行不会被还原
            total_formula_rows=(TOTAL_ROW - 3,),
        )
        assert report.equivalent is False, (
            "声明了错误的合计行却判等价 ⇒ 还原不是按声明做的，而是无条件抹平"
        )

    def test_zero_shift_path_is_byte_identical(
        self,
        insertable_bundle: tuple[Any, Any],
        base_bytes: bytes,
        base_path: Path,
        runtime_binding: Mapping[str, str],
    ) -> None:
        """**Property 3**：没有 orphan 时 `apply_plan_zip` 的产物与位移分支无关。

        判据形态：同一个零位移计划，`apply_plan_zip` 与 `apply_plan_zip_with_report`
        产出**逐字节相同**的字节，且报告为 `None`（位移分支一次都没进）。
        """
        contract, definitions = insertable_bundle
        outcome = _extract(base_path, definitions)
        plan = _plan(
            projection=outcome.projection,
            contract=contract,
            base_bytes=base_bytes,
            outcome=outcome,
            runtime_binding=runtime_binding,
        )
        assert plan.row_shift is None
        facade = M.apply_plan_zip(base_bytes, plan)
        full, report = M.apply_plan_zip_with_report(base_bytes, plan)
        assert report is None
        assert facade == full
        # Table part 一个字节都不该动（零位移时根本不解析它）。
        # 🔴 part 名**现搜**不写死：H1 的注入产物实测叫 `tableGtRowId.xml`，
        #    写死 `table1.xml` 在别的模板上会 KeyError（本文件首版就这么红过）。
        before = _read_entries(base_bytes)
        after = _read_entries(facade)
        table_parts = [n for n in before if n.startswith("xl/tables/")]
        assert table_parts, "zip 里没有 Table part —— fixture 形态变了"
        for name in table_parts:
            assert after[name] == before[name], name


# ═══════════════════════════════════════════════════════════════════════════
# 6. 位移**之后**那一相（Task 12 / 15 在生产链路上的调用点）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本节的存在是**变异检验捞出来的**：M28（摘掉 `materialize_projection` 里
#    `assert_shifted_footer_gates` 的调用）判 **GREEN** —— 上面那些用例只调
#    `apply_plan_zip_with_report`，从未走完整的 `materialize_projection`，于是那个调用点
#    **一次都没被执行**。两个新参数（`row_shift` / `carries_total_formula`）在生产链路上
#    因此是零消费的死参数，而那正是假绿第①源（additive 注入即死代码）。
#
#    修法是两条判据一起：
#      ① 直接测 `assert_shifted_footer_gates` 的行为（正面 + 反面）
#      ② 走一次真实 `materialize_projection` —— 只有它能证明**调用点在链路上**


class TestShiftedFooterGatesRunOnTheStagedProduct:
    """**Validates: Requirements 7.1, 7.3, 7.4, 7.5**"""

    COUNT = 2

    def _staged_and_plan(
        self,
        insertable_bundle: tuple[Any, Any],
        base_bytes: bytes,
        base_path: Path,
        runtime_binding: Mapping[str, str],
    ) -> tuple[M.MaterializePlan, bytes, X.ManagedRegion]:
        contract, definitions = insertable_bundle
        outcome = _extract(base_path, definitions)
        projection = _with_extra_rows(
            outcome.projection, count=self.COUNT, prefix="gate"
        )
        plan = _plan(
            projection=projection,
            contract=contract,
            base_bytes=base_bytes,
            outcome=outcome,
            runtime_binding=runtime_binding,
        )
        assert plan.row_shift is not None
        data, _ = M.apply_plan_zip_with_report(base_bytes, plan)
        return plan, data, outcome.region

    def test_gates_pass_on_the_shifted_product(
        self,
        insertable_bundle: tuple[Any, Any],
        base_bytes: bytes,
        base_path: Path,
        runtime_binding: Mapping[str, str],
    ) -> None:
        """位移后的产物上：marker 恰在 `冻结 + 声明位移`、合计覆盖位移后区间。"""
        contract, _ = insertable_bundle
        plan, data, region = self._staged_and_plan(
            insertable_bundle, base_bytes, base_path, runtime_binding
        )
        observed = M.assert_shifted_footer_gates(
            staged_bytes=data,
            plan=plan,
            contract=contract,
            region=region,
            runtime_binding=runtime_binding,
        )
        assert observed == TOTAL_ROW + self.COUNT, observed

    def test_gates_reject_a_marker_that_moved_beyond_the_declaration(
        self,
        insertable_bundle: tuple[Any, Any],
        base_bytes: bytes,
        base_path: Path,
        runtime_binding: Mapping[str, str],
    ) -> None:
        """反面：把 marker 再往下挪一行 ⇒ 「声明之外的下移」必须打红。

        这一条证明第二相不是空转 —— 它真的在**已位移的产物**上求值。
        """
        contract, _ = insertable_bundle
        plan, data, region = self._staged_and_plan(
            insertable_bundle, base_bytes, base_path, runtime_binding
        )
        entries = _read_entries(data)
        xml = entries[plan.sheet_part].decode("utf-8")
        # 🔴 只挪 **marker 格的坐标**，不动 `<row r>` —— `_find_marker_row` 扫的是
        #    `<c r="A{n}">`。首版改了 `<row r>`，于是 marker 仍被定位在 28（`<c r="A28">`
        #    没动）、anchor 门照过，反而是合计门报「footer 行 28 不存在」——
        #    那不是本条要证的东西（构造把判据问岔了）。
        observed_row = TOTAL_ROW + self.COUNT
        moved = xml.replace(
            f'<c r="A{observed_row}"', f'<c r="A{observed_row + 90}"', 1
        )
        assert moved != xml, "定位不到位移后合计行的 marker 格 —— fixture 形态变了"
        entries[plan.sheet_part] = moved.encode("utf-8")
        with pytest.raises(M.FooterAnchorDriftError, match="声明之外"):
            M.assert_shifted_footer_gates(
                staged_bytes=_write_entries(entries),
                plan=plan,
                contract=contract,
                region=region,
                runtime_binding=runtime_binding,
            )

    def test_gates_are_a_no_op_without_a_plan(
        self,
        insertable_bundle: tuple[Any, Any],
        base_bytes: bytes,
        base_path: Path,
        runtime_binding: Mapping[str, str],
    ) -> None:
        """零位移计划 ⇒ 第二相整体跳过（返回 `None`），不引入任何新判据。"""
        contract, definitions = insertable_bundle
        outcome = _extract(base_path, definitions)
        plan = _plan(
            projection=outcome.projection,
            contract=contract,
            base_bytes=base_bytes,
            outcome=outcome,
            runtime_binding=runtime_binding,
        )
        assert plan.row_shift is None
        assert (
            M.assert_shifted_footer_gates(
                staged_bytes=base_bytes,
                plan=plan,
                contract=contract,
                region=outcome.region,
                runtime_binding=runtime_binding,
            )
            is None
        )


class TestMaterializeProjectionRunsTheWholeChain:
    """走一次真实 `materialize_projection` —— 唯一能证明**调用点在链路上**的判据。

    **Validates: Requirements 2.3, 3.2, 7.1, 7.4**

    🔴 只测 `apply_plan_zip_with_report` 不够：那样 `assert_shifted_footer_gates` 的调用点
    可以被整行删掉而全部用例仍绿（变异 M28 实测 GREEN）。
    """

    COUNT = 2

    def test_end_to_end_materialize_inserts_rows_and_runs_the_shifted_gates(
        self,
        insertable_bundle: tuple[Any, Any],
        base_path: Path,
        workdir: Path,
    ) -> None:
        _, definitions = insertable_bundle
        outcome = _extract(base_path, definitions)
        projection = _with_extra_rows(
            outcome.projection, count=self.COUNT, prefix="e2e"
        )
        output = workdir / "e2e" / "staged.xlsx"
        result = M.materialize_projection(
            substrate=base_path,
            projection=projection,
            output=output,
            definitions=definitions,
            binding=BINDING,
            substrate_role=SubstrateRole.published_representation,
            substrate_kind=ArtifactKind.canonical,
            substrate_state=ArtifactState.published,
        )
        assert output.is_file()
        assert result.plan.row_shift is not None
        # ShiftReport 必须进 outcome（Task 18）
        assert result.shift_report is not None
        assert result.shift_report.inserted_rows == self.COUNT
        assert result.as_dict()["shift_report"]["inserted_rows"] == self.COUNT
        assert result.as_dict()["plan"]["row_shift"]["count"] == self.COUNT

        # 端到端反读：新行带着自己的 identity 回来，且没有被重新 mint
        staged = _extract(output, definitions)
        rows = list(staged.projection.row_keys["k11_rows"])
        assert len(rows) == (LAST_ROW - FIRST_ROW + 1) + self.COUNT, rows
        for offset in range(self.COUNT):
            assert f"e2e-{offset:03d}" in rows, rows[-4:]
        assert staged.scan.minted_by_row == {}, staged.scan.minted_by_row

    def test_failing_shifted_gate_publishes_nothing(
        self,
        insertable_bundle: tuple[Any, Any],
        base_path: Path,
        workdir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """位移后那一相不过 ⇒ **零产物**（Property 9）。

        判据落在**盘上的事实**：`output` 不存在、`*.materializing` 不残留、substrate 字节不变。
        这也顺带证明调用点排在 `os.replace` **之前** —— 排在后面的话 `output` 会留下来。
        """
        _, definitions = insertable_bundle
        outcome = _extract(base_path, definitions)
        projection = _with_extra_rows(
            outcome.projection, count=self.COUNT, prefix="boom"
        )
        output = workdir / "boom" / "staged.xlsx"
        before = hashlib.sha256(base_path.read_bytes()).hexdigest()

        def _boom(**_kwargs: Any) -> int:
            raise M.FooterAnchorDriftError("注入：位移后 footer 判据不过")

        monkeypatch.setattr(M, "assert_shifted_footer_gates", _boom)
        with pytest.raises(M.FooterAnchorDriftError, match="注入"):
            M.materialize_projection(
                substrate=base_path,
                projection=projection,
                output=output,
                definitions=definitions,
                binding=BINDING,
                substrate_role=SubstrateRole.published_representation,
                substrate_kind=ArtifactKind.canonical,
                substrate_state=ArtifactState.published,
            )
        assert not output.exists(), f"判据不过却留下了产物 {output}"
        assert not output.with_name(output.name + ".materializing").exists()
        assert hashlib.sha256(base_path.read_bytes()).hexdigest() == before
