# -*- coding: utf-8 -*-
"""canary 开表验收：D1-8 贴现区按**已提交契约**真删物理行。

spec: workpaper-sync-row-deletion-multi-region-propagation
Requirements: 8.1~8.4 · 1.11 · 2.x（兄弟表 ref 收缩）
用户 2026-09-30 授权开表。

═══ 与既有判据的分工（为什么还要这一份）═══

`test_row_deletion_convergence_dispatch` 里那批真实链路判据全部经
`_plan_with_convergence(world, "delete"|"clear"|None)` 在**测试期**把契约的
`row_convergence` 覆盖成想要的值 —— 它们验证的是「分流会跟着契约翻」，
是**机制**判据。机制对了不等于**开关真的打开了**：契约文件里少写那一个键，
那批判据照样全绿，而生产行为一点没变。

本文件一个字都不覆盖，直接吃磁盘上已提交的契约，验收的是「开表这件事本身生效了」。
⇒ 把 `row_convergence: "delete"` 从 `phase5_d1_08_endorsement.SPEC_D108_DISCOUNT`
   摘掉，本文件**必须**打红；而那批机制判据不会。

═══ 为什么选 D1-8 贴现区（开表依据，登记在 `test_row_deletion_contract_gate.OPENED_TABLES`）═══

* 开表准入体检（`backend/scripts/check/check_row_deletion_readiness.py --table
  endorse_discount_rows`）现算：受管数据区 14..21 共 8 行，`--count 1` 与 `--count 3`
  均 **8/8 可删、0 锁死** ⇒ 没有跨 sheet 单格引用指着这些行，门面不会 fail-closed；
* 本 sheet 是**双区**（兄弟区 `endorse_transfer_rows` 26..33 **刻意仍为 clear**）
  ⇒ 删行会真实触发「兄弟 Table ref 收缩」这条 G2 症状链第一环，
  而不是在退化的单区表上验一个空壳；同 sheet 保留 clear 对照便于逐区比对；
* CS-21 两个前提本就齐备：`row_identity=field(/rows/*/rowId)` + `delete_policy=tombstone`。

🔴 体检工具量的是**原始模板**。本文件跑的是**插桩后**的工作簿（引用面更大，
   多出 `_GT_SYNC` 等载体）—— 两个口径都过，开表依据才算完整（见 design 勘误 E.10.1）。
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

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402

#: 开了表的区 / 刻意没开的兄弟区。
OPEN_TABLE = "endorse_discount_rows"
SIBLING_TABLE = "endorse_transfer_rows"
SIBLING_TABLE_NAME = "GT_D18_TRANSFER_ROWS"
#: 兄弟区受管数据行（模板口径，位移前）。
SIBLING_FIRST_ROW = 26
SIBLING_LAST_ROW = 33


@pytest.fixture(scope="module")
def world() -> dict[str, Any]:
    """D1-8 真实插桩世界（复用 dispatch 那份，不造第二个固件）。"""
    import test_row_deletion_convergence_dispatch as DSP

    return DSP._build_d18_world()


@pytest.fixture(scope="module")
def committed_contract(world: dict[str, Any]) -> Any:
    """**磁盘已提交**的契约，零测试期覆盖。"""
    import test_row_deletion_convergence_dispatch as DSP

    return C.parse_contract(
        world["contract_payload_of"](), adapter_id=DSP._d1_adapter_id()
    )


def _rows_of(data: bytes, part: str) -> list[int]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read(part).decode("utf-8", "replace")
    return [int(m.group(1)) for m in re.finditer(r'<row r="(\d+)"', xml)]


def _table_ref(data: bytes, table_name: str) -> str | None:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if not name.startswith("xl/tables/"):
                continue
            xml = zf.read(name).decode("utf-8", "replace")
            if f'name="{table_name}"' in xml or f'displayName="{table_name}"' in xml:
                m = re.search(r'ref="([^"]+)"', xml)
                return m.group(1) if m else None
    return None


@pytest.fixture(scope="module")
def planned(world: dict[str, Any], committed_contract: Any) -> dict[str, Any]:
    """用已提交契约算一次计划并 apply 到字节。"""
    import test_row_deletion_convergence_dispatch as DSP

    projection = DSP._projection_missing_the_minted_row(world["outcome"])
    plan = M.plan_managed_writes(
        projection=projection,
        contract=committed_contract,
        binding=world["binding"],
        region=world["outcome"].region,
        scan=world["outcome"].scan,
        substrate_entries=world["entries"],
        substrate_formulas=world["outcome"].formula_inventory,
        runtime_binding=world["runtime_binding"],
    )
    base = world["base"].read_bytes()
    staged, report = M.apply_plan_zip_with_report(base, plan)
    return {"plan": plan, "base": base, "staged": staged, "report": report}


class TestTheSwitchIsActuallyOn:
    """① 开关真的开了 —— 磁盘契约说 delete。"""

    def test_discount_region_is_open_and_sibling_is_not(
        self, committed_contract: Any
    ) -> None:
        modes = {
            t.table_key: t.row_convergence.value
            for sheet in committed_contract.sheets
            for t in sheet.tables
            if t.table_key in (OPEN_TABLE, SIBLING_TABLE)
        }
        assert modes == {OPEN_TABLE: "delete", SIBLING_TABLE: "clear"}, (
            f"已提交契约的收敛声明不对：{modes} —— "
            "要么 canary 没生效（贴现区不是 delete），"
            "要么兄弟区被一起开了（同 sheet 的 clear 对照丢了）"
        )

    def test_the_open_table_reports_physical_deletion(
        self, committed_contract: Any
    ) -> None:
        """分流入口 `deletes_physical_rows` 必须为真（而不是只有枚举值对）。"""
        spec = next(
            t
            for sheet in committed_contract.sheets
            for t in sheet.tables
            if t.table_key == OPEN_TABLE
        )
        assert spec.deletes_physical_rows is True
        sib = next(
            t
            for sheet in committed_contract.sheets
            for t in sheet.tables
            if t.table_key == SIBLING_TABLE
        )
        assert sib.deletes_physical_rows is False


class TestPlanFallsIntoTheDeleteBranch:
    """② 同一份 substrate + projection ⇒ 计划落在删行分支且双声明齐备。"""

    def test_stale_rows_are_deleted_not_cleared(self, planned: dict[str, Any]) -> None:
        plan = planned["plan"]
        assert plan.stale_deleted, (
            "开表了却没走删行分支 —— canary 未生效（或 stale 行没造出来，判据空转）"
        )
        assert plan.stale_cleared == (), (
            f"既删又清：{plan.stale_cleared} —— 两个分支应互斥"
        )

    def test_both_shift_carriers_are_present(self, planned: dict[str, Any]) -> None:
        """Requirement 1.11：删行计划必须**同时**带 `row_deletion` 与 `deletion_change`。"""
        plan = planned["plan"]
        assert plan.row_deletion is not None, "缺位移载体 row_deletion"
        assert plan.deletion_change is not None, "缺工作簿级传播 deletion_change"
        declared = tuple(plan.row_deletion.deleted_rows)
        assert declared == tuple(sorted(plan.stale_deleted)), (
            f"载体声明 {declared} != stale_deleted {sorted(plan.stale_deleted)}"
        )

    def test_no_degradation_reason_on_the_delete_path(
        self, planned: dict[str, Any]
    ) -> None:
        """走成删行就不该有降级原因（有就说明其实降级回清空了）。"""
        assert planned["plan"].stale_clear_reason == "", (
            f"走删行却写了降级原因：{planned['plan'].stale_clear_reason!r}"
        )


class TestBytesReallyLoseTheRow:
    """③ 字节侧：物理行真的少了，且两张表的 ref 同步收缩。"""

    def test_managed_sheet_loses_exactly_the_deleted_rows(
        self, world: dict[str, Any], planned: dict[str, Any]
    ) -> None:
        part = world["outcome"].region.sheet_part
        before = _rows_of(planned["base"], part)
        after = _rows_of(planned["staged"], part)
        removed = len(planned["plan"].stale_deleted)
        assert len(after) == len(before) - removed, (
            f"受管 sheet 行数 {len(before)} → {len(after)}，"
            f"而计划要删 {removed} 行 —— 物理删行没真发生"
        )
        assert max(after) == max(before) - removed, (
            f"最大行号 {max(before)} → {max(after)}：位移量与删除行数不符"
        )

    def test_own_table_ref_shrinks(
        self, world: dict[str, Any], planned: dict[str, Any]
    ) -> None:
        name = world["binding"].table_name
        before = _table_ref(planned["base"], name)
        after = _table_ref(planned["staged"], name)
        assert before and after, f"取不到 {name} 的 ref：{before} / {after}"
        assert before != after, f"本表 Table ref 没收缩：{before}"

    def test_sibling_table_ref_shifts_up(self, planned: dict[str, Any]) -> None:
        """🔴 G2 症状链第一环：兄弟表的 ref 必须整体上移。

        这一条是选 D1-8 当 canary 的**理由本身** —— 单区表上它恒真空转。
        """
        before = _table_ref(planned["base"], SIBLING_TABLE_NAME)
        after = _table_ref(planned["staged"], SIBLING_TABLE_NAME)
        assert before and after, f"取不到兄弟表 ref：{before} / {after}"
        assert before != after, (
            f"兄弟表 ref 没随删行收缩（仍 {before}）—— "
            "G2 症状链第一环没接上：兄弟区会指到错行"
        )
        shift = len(planned["plan"].stale_deleted)

        def head_row(ref: str) -> int:
            m = re.match(r"[A-Z]+(\d+)", ref.split(":")[0])
            assert m, ref
            return int(m.group(1))

        assert head_row(after) == head_row(before) - shift, (
            f"兄弟表 ref 起点位移不对：{before} → {after}（应上移 {shift}）"
        )


class TestSiblingRegionIsUntouched:
    """④ 未开表的兄弟区：受管行一行都没少（只是整体上移）。"""

    def test_sibling_row_count_is_conserved(
        self, world: dict[str, Any], planned: dict[str, Any]
    ) -> None:
        part = world["outcome"].region.sheet_part
        before = _rows_of(planned["base"], part)
        after = _rows_of(planned["staged"], part)
        shift = len(planned["plan"].stale_deleted)
        sib_before = [r for r in before if SIBLING_FIRST_ROW <= r <= SIBLING_LAST_ROW]
        sib_after = [
            r
            for r in after
            if (SIBLING_FIRST_ROW - shift) <= r <= (SIBLING_LAST_ROW - shift)
        ]
        assert sib_before, "兄弟区在删行前就是空的 ⇒ 本条判据空转"
        assert len(sib_after) == len(sib_before), (
            f"兄弟区行数变了：{len(sib_before)} → {len(sib_after)} —— "
            "未开表的区不该丢行"
        )
        assert sib_after == [r - shift for r in sib_before], (
            f"兄弟区行号不是整体上移 {shift}：{sib_before} → {sib_after}"
        )

    def test_deletion_happened_above_the_sibling_region(
        self, planned: dict[str, Any]
    ) -> None:
        """前一条的前提：删除点必须在兄弟区**之上**（否则位移方向判据不成立）。"""
        assert max(planned["plan"].stale_deleted) < SIBLING_FIRST_ROW, (
            f"删除点 {planned['plan'].stale_deleted} 不在兄弟区 "
            f"{SIBLING_FIRST_ROW}..{SIBLING_LAST_ROW} 之上 ⇒ 上一条的位移方向假设不成立"
        )
