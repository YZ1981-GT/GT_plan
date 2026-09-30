# -*- coding: utf-8 -*-
"""A2 `_GT_SYNC` runtime binding 的删行重冻结（Property 9 + 端到端 + 变异反证）。

spec: workpaper-sync-row-deletion-multi-region-propagation
Tasks: 10.1 · 10.2 · 10.3
Requirements: 3.1~3.7

═══ 这一条为什么必须与 A1 同批落地 ═══

`_refresh_gt_sync_runtime_binding` 原为 **insert-only**。删行时那 7 个被重写的键一个都不动
⇒ **下一次** materialize 在计划期就撞 `FooterAnchorDriftError`（可见侧 marker 实测 =
冻结值 − 删行数，而 `row_shift is None` 分支要求两者严格相等）。症状是「删行这次成功了、
下次点在线编辑起 500」—— 时间差让根因极难归位。

所以本文件的**端到端**判据是「连跑两趟」：第一趟删行、第二趟在产物上复核计划期 footer 门。
单看第一趟永远是绿的。
"""

from __future__ import annotations

import io
import os
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

from app.services.workpaper_sync import excel_extract as EE  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync.excel_workbook_row_change import (  # noqa: E402
    RowDeletionShift,
)

import test_row_deletion_sibling_table_ref as A1  # noqa: E402
import test_sibling_table_ref_row_shift as SIB  # noqa: E402

#: `_refresh_gt_sync_runtime_binding` 会**重写**的键（design B6 现算 7 个）。
REWRITTEN_KEYS: tuple[str, ...] = (
    "GT_ROW_UUID_LAST_ROW",
    "GT_FOOTER_ROW",
    "GT_FOOTER_ROW_{TID}",
    "GT_MANAGED_RANGE",
    "GT_MANAGED_TABLE_REF",
    "GT_LAST_SHIFT",
    "GT_STRUCTURE_FINGERPRINT",
)
#: 只读、不重写的那一个（只喂 fingerprint）。
READ_ONLY_KEY = "GT_ROW_UUID_COLUMN"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 复用 A1 的 D4-1 双区世界（不抄第二份 fixture）
# ═══════════════════════════════════════════════════════════════════════════

dual = A1.dual  # pytest fixture 转发


def _binding_pairs(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return dict(EE.read_runtime_binding_pairs(zf))


def _delete(dual: dict[str, Any], rows: tuple[int, ...]) -> bytes:
    return A1._apply_delete(dual, rows)


def _tid_of(pairs: Mapping[str, str], table_name: str) -> str | None:
    return M._template_id_for_table_name(pairs, table_name)


@pytest.fixture(scope="module")
def baseline_pairs(dual: dict[str, Any]) -> dict[str, str]:
    return _binding_pairs(dual["bytes"])


# ═══════════════════════════════════════════════════════════════════════════
# 2. Property 9：重冻结的三条不变量
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty9RefreezeInvariants:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 9: runtime binding 重冻结的三条不变量**

    **Validates: Requirements 3.1, 3.2, 3.3, 3.5**
    """

    def test_key_inventory_matches_the_design_baseline(
        self, baseline_pairs: dict[str, str]
    ) -> None:
        """🔴 先证明这份 artifact 上那 8 个键真的存在 —— 否则下面全是空转。"""
        assert "GT_ROW_UUID_LAST_ROW" in baseline_pairs
        assert "GT_FOOTER_ROW" in baseline_pairs
        assert READ_ONLY_KEY in baseline_pairs
        per_tid = [k for k in baseline_pairs if k.startswith("GT_FOOTER_ROW_")]
        assert len(per_tid) >= 2, f"per-template footer 键只有 {per_tid} ⇒ 兄弟区判据空转"

    def test_same_sheet_sibling_footer_keys_both_move(
        self, dual: dict[str, Any], baseline_pairs: dict[str, str]
    ) -> None:
        """① 受删行影响的键 == 位移载体对其旧值的映射（**含同 sheet 兄弟区**）。

        🔴 这是 A2 的核心：D41MAIN 删行必须同时动 D41OTHER（同 sheet 物理上移），
        而**不同** sheet 的 footer 键一个都不许动。
        """
        region = dual["region_main"]
        row = region.first_row
        after = _binding_pairs(_delete(dual, (row,)))
        shift = RowDeletionShift(
            deleted_rows=(row,),
            region_first_row=region.first_row,
            region_last_row=region.last_row,
        )
        main_tid = _tid_of(baseline_pairs, SIB.A.TABLE_NAME_MAIN)
        other_tid = _tid_of(baseline_pairs, SIB.A.TABLE_NAME_OTHER)
        assert main_tid and other_tid and main_tid != other_tid, (
            f"两区 template_id 解析失败：{main_tid} / {other_tid}"
        )
        for tid in (main_tid, other_tid):
            key = f"GT_FOOTER_ROW_{tid}"
            old = int(baseline_pairs[key])
            want = shift.shift(old)
            assert after[key] == str(want), (
                f"{key}：冻结 {old} → 实得 {after[key]}，载体给 {want}"
            )
        # 兄弟区的 footer 必须**真的动了**（否则这条判据在观测一个不动的值）
        other_key = f"GT_FOOTER_ROW_{other_tid}"
        assert after[other_key] != baseline_pairs[other_key], (
            f"{other_key} 没动 —— 同 sheet 兄弟区 footer 未重冻结（A2 的主症状）"
        )

    def test_other_sheet_footer_keys_are_verbatim(
        self, dual: dict[str, Any], baseline_pairs: dict[str, str]
    ) -> None:
        """② 属于**其它 sheet** 的 per-template footer 键逐字不变。"""
        region = dual["region_main"]
        after = _binding_pairs(_delete(dual, (region.first_row,)))
        main_tid = _tid_of(baseline_pairs, SIB.A.TABLE_NAME_MAIN)
        other_tid = _tid_of(baseline_pairs, SIB.A.TABLE_NAME_OTHER)
        same_sheet = {f"GT_FOOTER_ROW_{main_tid}", f"GT_FOOTER_ROW_{other_tid}"}
        foreign = [
            k
            for k in baseline_pairs
            if k.startswith("GT_FOOTER_ROW_") and k not in same_sheet
        ]
        assert foreign, "这份 artifact 上没有别的 sheet 的 footer 键 ⇒ 本条判据空转"
        for key in foreign:
            assert after[key] == baseline_pairs[key], (
                f"{key} 属于别的 sheet 却被改动了：{baseline_pairs[key]} → {after[key]}"
            )

    def test_row_agnostic_keys_are_verbatim(
        self, dual: dict[str, Any], baseline_pairs: dict[str, str]
    ) -> None:
        """③ 与行号无关的键逐字保留（模板事实不该被行变更动）。"""
        region = dual["region_main"]
        after = _binding_pairs(_delete(dual, (region.first_row,)))
        changed = {k for k in baseline_pairs if after.get(k) != baseline_pairs[k]}
        # 允许变化的只有：本 sheet 的行号键 + 两个派生键
        main_tid = _tid_of(baseline_pairs, SIB.A.TABLE_NAME_MAIN)
        other_tid = _tid_of(baseline_pairs, SIB.A.TABLE_NAME_OTHER)
        allowed = {
            "GT_ROW_UUID_LAST_ROW",
            "GT_FOOTER_ROW",
            "GT_MANAGED_RANGE",
            "GT_MANAGED_TABLE_REF",
            "GT_LAST_SHIFT",
            "GT_STRUCTURE_FINGERPRINT",
            f"GT_FOOTER_ROW_{main_tid}",
            f"GT_FOOTER_ROW_{other_tid}",
        }
        assert changed <= allowed, (
            f"与行号无关的键被改动了：{sorted(changed - allowed)}"
        )
        assert after[READ_ONLY_KEY] == baseline_pairs[READ_ONLY_KEY], (
            f"{READ_ONLY_KEY} 是只读键（只喂 fingerprint），不该被重写"
        )
        assert changed, "一个键都没变 ⇒ 重冻结根本没执行，本条判据恒真"

    def test_last_shift_count_is_negative_and_accumulates_downward(
        self, dual: dict[str, Any], baseline_pairs: dict[str, str]
    ) -> None:
        """`GT_LAST_SHIFT` 形态不变，但删行侧行数为**负** ⇒ 累计可回落。

        不取负的后果：「插 3 行又删 3 行」会被记成累计 +6，模板升级重放时按那个假累计量
        把行数放大一倍。
        """
        region = dual["region_main"]
        after = _binding_pairs(_delete(dual, (region.first_row, region.first_row + 1)))
        raw = after["GT_LAST_SHIFT"]
        parts = raw.split("|")
        assert len(parts) == 3, f"GT_LAST_SHIFT 形态变了：{raw!r}"
        at, count, total = (int(p) for p in parts)
        assert at == region.first_row, f"变更点应为最小被删行 {region.first_row}，实得 {at}"
        assert count == -2, f"删 2 行应记 -2，实得 {count}"
        old_total = 0
        if baseline_pairs.get("GT_LAST_SHIFT"):
            old_total = int(baseline_pairs["GT_LAST_SHIFT"].split("|")[-1])
        assert total == old_total - 2, f"累计应从 {old_total} 回落到 {old_total - 2}，实得 {total}"

    def test_non_primary_trip_leaves_workbook_global_keys_verbatim(
        self, dual: dict[str, Any], baseline_pairs: dict[str, str]
    ) -> None:
        """🔴 非 primary 趟**不得**动那三个 workbook 全局键。

        `GT_ROW_UUID_LAST_ROW` / `GT_MANAGED_RANGE` / `GT_MANAGED_TABLE_REF` 的值取自
        instrumentation 的 **primary** sheet（实测这份 D4 册：`GT_MANAGED_RANGE=A12:V23`
        并不是 D4-1 主营区的区间）。非 primary 趟删行若照插行那样无条件重写，就会把
        **别的 sheet** 的受管区末行凭空缩掉一行 —— 现场看起来与本次操作完全无关。

        🔴 本条配**反向断言**：证明「若没有门控，这两个键确实会变」。不然「值恰好没变」
        与「门控在起作用」分辨不出来。
        """
        import re as _re

        region = dual["region_main"]
        row = region.first_row
        after = _binding_pairs(_delete(dual, (row,)))
        shift = RowDeletionShift(
            deleted_rows=(row,),
            region_first_row=region.first_row,
            region_last_row=region.last_row,
        )
        main_tid = _tid_of(baseline_pairs, SIB.A.TABLE_NAME_MAIN)
        first_tid_key = next(
            (k for k in baseline_pairs if k.startswith("GT_FOOTER_ROW_")), None
        )
        assert first_tid_key != f"GT_FOOTER_ROW_{main_tid}", (
            f"这份 artifact 上 D4-1 主营区**就是** primary（{first_tid_key}）⇒ "
            "本条判据的前提不成立，须换一个非 primary 的区作靶子"
        )
        for key in ("GT_ROW_UUID_LAST_ROW", "GT_MANAGED_RANGE", "GT_MANAGED_TABLE_REF"):
            old = baseline_pairs.get(key)
            if not old:
                continue
            assert after[key] == old, (
                f"{key} 属于 primary 区却被非 primary 趟改动了：{old} → {after[key]}"
            )
        # ── 反向断言：去掉门控的话这两个键**会**变 ──────────────────────
        would_change = []
        for key in ("GT_MANAGED_RANGE", "GT_MANAGED_TABLE_REF"):
            old = baseline_pairs.get(key)
            if not old:
                continue
            if M._remap_range_string(old, shift) != old:
                would_change.append(key)
        old_last = baseline_pairs.get("GT_ROW_UUID_LAST_ROW")
        if old_last and str(shift.shift_range_end(int(old_last))) != old_last:
            would_change.append("GT_ROW_UUID_LAST_ROW")
        assert would_change, (
            f"删 r={row} 在算术上碰不到那三个键（primary 区间 "
            f"{baseline_pairs.get('GT_MANAGED_RANGE')!r}）⇒ 本条判据没有区分力，"
            "须换一个行号更靠后的靶子让门控真的挡住一次改动"
        )

    def test_primary_trip_shrinks_workbook_global_keys_by_direction(
        self, dual: dict[str, Any], baseline_pairs: dict[str, str]
    ) -> None:
        """primary 趟：那三个键按**端点方向**收缩（首行 `<`、末行 `<=`）。"""
        import re as _re

        entries = dual["entries"]
        first_tid_key = next(
            (k for k in baseline_pairs if k.startswith("GT_FOOTER_ROW_")), None
        )
        assert first_tid_key, "没有 per-template footer 键 ⇒ 定不出 primary"
        primary_tid = first_tid_key.removeprefix("GT_FOOTER_ROW_")
        tids = [t for t in str(baseline_pairs.get("GT_TEMPLATE_IDS") or "").split(",") if t]
        tables = [
            t for t in str(baseline_pairs.get("GT_MANAGED_TABLES") or "").split(",") if t
        ]
        assert len(tids) == len(tables), f"平行清册长度不等：{len(tids)} vs {len(tables)}"
        primary_table = tables[tids.index(primary_tid)]
        primary_part = M._managed_table_part(entries, table_name=primary_table)
        primary_ref = A1._split_ref(A1._ref_of(entries, primary_part))
        # primary 区所在 sheet
        primary_sheet_part = next(
            p
            for p in entries
            if p.startswith("xl/worksheets/sheet")
            and p.endswith(".xml")
            and primary_part in M._sheet_table_parts(entries, sheet_part=p)
        )
        row = primary_ref[3]  # 删 primary 区**末行** —— 端点方向之争恰好在这里
        plan = M.MaterializePlan(
            sheet_part=primary_sheet_part,
            sheet_name="primary",
            writes=(),
            preserved_formulas={},
            dynamic_column_columns={},
            table_part=primary_part,
            stale_deleted=(row,),
            managed_table_name=primary_table,
            row_deletion=RowDeletionShift(
                deleted_rows=(row,),
                region_first_row=primary_ref[1],
                region_last_row=primary_ref[3],
            ),
        )
        product, _ = M.apply_plan_zip_with_report(dual["bytes"], plan)
        after = _binding_pairs(product)
        shift = RowDeletionShift(
            deleted_rows=(row,),
            region_first_row=primary_ref[1],
            region_last_row=primary_ref[3],
        )
        changed_any = False
        for key in ("GT_MANAGED_RANGE", "GT_MANAGED_TABLE_REF"):
            old = baseline_pairs.get(key)
            if not old:
                continue
            m = _re.match(r"^([A-Z]{1,3})(\d+):([A-Z]{1,3})(\d+)$", old)
            assert m, f"{key} 形态不是 A1 区间：{old!r}"
            want = (
                f"{m.group(1)}{shift.shift_range_start(int(m.group(2)))}:"
                f"{m.group(3)}{shift.shift_range_end(int(m.group(4)))}"
            )
            assert after[key] == want, f"{key}：{old} → 实得 {after[key]}，应为 {want}"
            changed_any = changed_any or after[key] != old
        old_last = baseline_pairs.get("GT_ROW_UUID_LAST_ROW")
        if old_last:
            assert after["GT_ROW_UUID_LAST_ROW"] == str(
                shift.shift_range_end(int(old_last))
            )
            changed_any = changed_any or after["GT_ROW_UUID_LAST_ROW"] != old_last
        assert changed_any, (
            f"primary 趟删 r={row} 后三个全局键一个都没变 ⇒ 本条判据空转"
            f"（primary 区间 {baseline_pairs.get('GT_MANAGED_RANGE')!r}）"
        )

    def test_structure_fingerprint_changes_with_the_coordinates(
        self, dual: dict[str, Any], baseline_pairs: dict[str, str]
    ) -> None:
        """`GT_STRUCTURE_FINGERPRINT` 必须跟着坐标变 —— 否则它不是「位移后的摘要」。"""
        region = dual["region_main"]
        after = _binding_pairs(_delete(dual, (region.first_row,)))
        assert after["GT_STRUCTURE_FINGERPRINT"] != baseline_pairs.get(
            "GT_STRUCTURE_FINGERPRINT"
        ), "指纹没变 ⇒ 它没在观测重冻结后的坐标"

    def test_insert_branch_arithmetic_is_untouched(self) -> None:
        """🔴 结构锁：insert 分支的四处算术**逐字未变**（零回归按定义成立）。

        判据是源码形态而不是「跑一遍插行」：插行的字节回归由既有的
        `test_sibling_table_ref_row_shift` / `test_excel_row_insertion_*` 承担，
        这里只钉住「没人顺手把插行的算式改了」。
        """
        import inspect
        import textwrap

        src = textwrap.dedent(inspect.getsource(M._refresh_gt_sync_runtime_binding))
        for needle in (
            "old_last_row + shift.count if old_last_row >= shift.insert_at - 1 else old_last_row",
            "shift.count if old_last_row >= shift.insert_at - 1 else 0",
        ):
            assert needle in src, f"插行侧算式被改动了，找不到：{needle!r}"
        # `_grow_range_string` 仍是插行侧的唯一出口且算式未变
        grow = textwrap.dedent(inspect.getsource(M._grow_range_string))
        assert "tail_row + shift.count if tail_row >= shift.insert_at - 1 else tail_row" in grow

    def test_range_remap_is_one_function_dispatched_by_direction(self) -> None:
        """🔴 结构锁：区间改写是**一个**函数按方向分流，不是抄第二份。"""
        import ast
        import inspect
        import textwrap

        src = (
            _BACKEND / "app/services/workpaper_sync/excel_materialize.py"
        ).read_bytes().decode("utf-8")
        names = {
            node.name
            for node in ast.walk(ast.parse(src))
            if isinstance(node, ast.FunctionDef)
        }
        assert "_shrink_range_string" not in names, (
            "出现了 `_shrink_range_string` —— 区间改写有了第二份实现，"
            "「首行边界」这条插行侧踩过坑的规则就有两个真源"
        )
        body = textwrap.dedent(inspect.getsource(M._remap_range_string))
        assert "_grow_range_string" in body, "delete 分支没有把 insert 那半委托回去"
        assert "deleted_rows" in body, "分流点不在 `deleted_rows` 上"

    def test_same_sheet_tids_derivation_is_reused_not_copied(self) -> None:
        """🔴 结构锁：`same_sheet_tids` 的推导只有**一份**（复用既有那一段）。"""
        import inspect
        import textwrap

        src = textwrap.dedent(inspect.getsource(M._refresh_gt_sync_runtime_binding))
        assert src.count("same_sheet_tids: set[str]") == 1, (
            "`same_sheet_tids` 被推导了两次 —— 那一段正是插行侧踩过"
            "「把『同 sheet 兄弟』和『不同 sheet』混成一类」的地方，抄一遍就把坑复制过来"
        )
        assert src.count("_sheet_table_parts(entries, sheet_part=plan.sheet_part)") == 1


# ═══════════════════════════════════════════════════════════════════════════
# 3. 端到端「连跑两趟」+ 变异反证（Requirements 3.6 / 3.7）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 A2 的故障是**时间错位**的：第一趟删行永远成功，第二趟才 500。所以判据必须跑两趟 ——
#    第二趟在删行产物上复核**计划期** footer 门（`row_shift=None` 口径，要求
#    「可见侧 marker 实测 == 冻结值」严格相等）。


def _plan_period_footer_gate(
    dual: dict[str, Any], product: bytes, *, table_name: str, table_key: str
) -> int | None:
    """在产物上复核计划期 footer 门 —— 与 `plan_managed_writes` 的第 2 步同口径。"""
    entries = A1._entries_of(product)
    with zipfile.ZipFile(io.BytesIO(product)) as zf:
        region = EE.resolve_managed_region(
            zf,
            contract=dual["contract"],
            binding=SIB.BINDING_MAIN
            if table_name == SIB.A.TABLE_NAME_MAIN
            else SIB.BINDING_OTHER,
        )
        runtime_binding = dict(EE.read_runtime_binding_pairs(zf))
    return M.assert_footer_anchor_stable(
        entries=entries,
        sheet_part=region.sheet_part,
        contract=dual["contract"],
        runtime_binding=runtime_binding,
        table_key=table_key,
        table_name=table_name,
        search_from_row=region.first_row,
    )


def _restore_per_template_footer_keys(product: bytes, baseline: Mapping[str, str]) -> bytes:
    """把产物里的 per-template footer 键**还原成删行前的值** = 「修复前」态。

    🔴 用**进程内**重写 `_GT_SYNC` 部件制造变异态，不改磁盘上的生产文件
    （归档 README 教训 6：改文件式变异的还原动作被跳过后会把已变异文件当 pristine 快照）。
    这比 monkeypatch 更贴近「那一支被去掉」的形态：其余键仍是重冻结后的新值。
    """
    from app.services.workpaper_sync.excel_instrumentation import _gt_sync_sheet_xml

    entries = A1._entries_of(product)
    part = M._gt_sync_sheet_part(entries, product)
    with zipfile.ZipFile(io.BytesIO(product)) as zf:
        pairs = list(EE.read_runtime_binding_pairs(zf).items())
    mutated = [
        (k, baseline[k] if k.startswith("GT_FOOTER_ROW_") and k in baseline else v)
        for k, v in pairs
    ]
    assert mutated != pairs, "变异没生效（per-template footer 键本来就没被重冻结？）"
    entries[part] = _gt_sync_sheet_xml(mutated)
    return M._write_entries(entries)


class TestEndToEndTwoPasses:
    """**Validates: Requirements 3.6, 3.7**"""

    def test_second_pass_footer_gate_passes_after_delete(
        self, dual: dict[str, Any]
    ) -> None:
        """第一趟删行、第二趟复核计划期 footer 门 ⇒ 通过。

        🔴 用**返回值**（具体行号，非 `None`）断言那道门真的执行过，不用「没有抛错」。
        """
        region = dual["region_main"]
        product = _delete(dual, (region.first_row,))
        footer_row = _plan_period_footer_gate(
            dual,
            product,
            table_name=SIB.A.TABLE_NAME_MAIN,
            table_key=SIB.A.ROWS_TABLE_KEY_MAIN,
        )
        assert isinstance(footer_row, int), (
            f"footer 门返回 {footer_row!r} —— 它没真的求值（契约里没 footer_anchor？）"
            "这条判据会变成「没抛错」式的空转"
        )

    def test_sibling_region_second_pass_footer_gate_also_passes(
        self, dual: dict[str, Any]
    ) -> None:
        """**兄弟区**那一趟也要过 —— A2 的主症状恰恰落在兄弟区上。"""
        region = dual["region_main"]
        product = _delete(dual, (region.first_row,))
        footer_row = _plan_period_footer_gate(
            dual,
            product,
            table_name=SIB.A.TABLE_NAME_OTHER,
            table_key=SIB.A.ROWS_TABLE_KEY_OTHER,
        )
        assert isinstance(footer_row, int), f"兄弟区 footer 门返回 {footer_row!r}"

    def test_mutation_drop_per_template_refreeze_reds_the_second_pass(
        self, dual: dict[str, Any], baseline_pairs: dict[str, str]
    ) -> None:
        """🔴 变异反证：去掉 per-template footer 键的重冻结 ⇒ 第二趟必抛 `FooterAnchorDriftError`。

        这条证明那些键**真的被下游消费**；没有它，「重冻结了」与「重冻结成什么值」
        分辨不出来。
        """
        region = dual["region_main"]
        product = _delete(dual, (region.first_row,))
        mutated = _restore_per_template_footer_keys(product, baseline_pairs)
        with pytest.raises(M.FooterAnchorDriftError) as err:
            _plan_period_footer_gate(
                dual,
                mutated,
                table_name=SIB.A.TABLE_NAME_OTHER,
                table_key=SIB.A.ROWS_TABLE_KEY_OTHER,
            )
        text = str(err.value)
        assert "footer" in text.lower() or "GT_FOOTER_ROW" in text, text

    def test_repeated_delete_keeps_the_gate_passing(self, dual: dict[str, Any]) -> None:
        """连删两次（两趟各删一行）后 footer 门仍过 —— 累计位移可重放。"""
        region = dual["region_main"]
        first = _delete(dual, (region.first_row,))
        # 第二趟：在第一趟产物上再删一行（区间已上移一行）
        with zipfile.ZipFile(io.BytesIO(first)) as zf:
            region2 = EE.resolve_managed_region(
                zf, contract=dual["contract"], binding=SIB.BINDING_MAIN
            )
        plan2 = M.MaterializePlan(
            sheet_part=region2.sheet_part,
            sheet_name=region2.sheet_name,
            writes=(),
            preserved_formulas={},
            dynamic_column_columns={},
            table_part=dual["main_part"],
            stale_deleted=(region2.first_row,),
            managed_table_name=SIB.A.TABLE_NAME_MAIN,
            row_deletion=RowDeletionShift(
                deleted_rows=(region2.first_row,),
                region_first_row=region2.first_row,
                region_last_row=region2.last_row,
            ),
        )
        second, _ = M.apply_plan_zip_with_report(first, plan2)
        footer_row = _plan_period_footer_gate(
            dual,
            second,
            table_name=SIB.A.TABLE_NAME_MAIN,
            table_key=SIB.A.ROWS_TABLE_KEY_MAIN,
        )
        assert isinstance(footer_row, int)
        # 累计位移回落 2
        pairs = _binding_pairs(second)
        assert pairs["GT_LAST_SHIFT"].split("|")[-1] == "-2", pairs["GT_LAST_SHIFT"]


class TestInsertSideGlobalKeysStayUnconditional:
    """🔴 补一条**此前只存在于注释里**的判据（2026-09-30）。

    `_refresh_gt_sync_runtime_binding` 的注释写着：

        ⚠ 插行分支**逐字不变**（零回归按定义成立）；插行侧的同款无条件重写属**既有**形态，
          本 spec 不改它（改了会动插行的冻结字节），只在此登记：见判据
          `test_insert_side_global_keys_stay_unconditional`。

    全仓 grep 该名字 **0 命中** —— 那是一条**断言性注释**（声称有判据守着，其实没有）。
    本轮补齐。它与本 spec 早先抓到的「注释说依赖全在方法体内、实测缺 2 个模块别名」
    是同一形态：注释里的声明不会被任何东西验证，除非把它写成判据。

    ═══ 锁的是什么 ═══

    删行侧对四个 **workbook 全局**键（`GT_ROW_UUID_LAST_ROW` / `GT_MANAGED_RANGE` /
    `GT_MANAGED_TABLE_REF` / `GT_FOOTER_ROW`）按 `is_primary_trip` 门控 —— 理由是删行
    方向会让 primary 的坐标被非 primary 趟凭空缩掉（注释里有 D1-8 删首行把 D1-3 末行
    从 20 缩到 19 的实测例）。

    插行侧**没有**这个门控，且**刻意不加**：插行时 primary 的行号更小
    （`old_last_row >= shift.insert_at - 1` 恒不成立）⇒ 算术根本碰不到它，加门控不改变
    行为却会动插行的冻结字节 ⇒ Property 28 零回归基线要整册重取。

    ⇒ 本判据把「插行侧保持无条件、删行侧保持门控」这个**不对称**钉成事实：
    哪天有人为了「对称好看」给插行也加门控，或把删行的门控删掉，它都会红。
    """

    def _source(self) -> str:
        import inspect

        from app.services.workpaper_sync import excel_materialize as M

        return inspect.getsource(M._refresh_gt_sync_runtime_binding)

    #: 四个 workbook 全局键里，删行侧带 `is_primary_trip` 门控的那三组分支。
    #: （`GT_FOOTER_ROW` 用的是 `if is_primary_trip:` 正向写法，单独一条。）
    GATED_BY_DELETING = (
        "GT_ROW_UUID_LAST_ROW",
        'key in ("GT_MANAGED_RANGE", "GT_MANAGED_TABLE_REF")',
    )

    def test_delete_side_gates_global_keys_by_primary_trip(self) -> None:
        """删行侧：三处 `deleting and not is_primary_trip` 门控必须都在。"""
        src = self._source()
        n = src.count("deleting and not is_primary_trip")
        assert n >= 2, (
            f"`deleting and not is_primary_trip` 只出现 {n} 次 —— "
            "删行侧对 workbook 全局键的门控被拆掉了，"
            "非 primary 趟删行会把 primary sheet 的坐标凭空缩掉"
        )
        assert "if is_primary_trip:" in src, (
            "`GT_FOOTER_ROW` 的 primary 门控（正向写法）不见了"
        )

    def test_insert_side_global_keys_stay_unconditional(self) -> None:
        """🔴 插行侧保持**无条件**重写 —— 不得为了对称而加门控。

        判据形态：`GT_ROW_UUID_LAST_ROW` 的 `else`（插行）分支里出现
        `old_last_row >= shift.insert_at - 1` 这个算式，且该算式**不在**任何
        `is_primary_trip` 条件之下。

        用 AST 而不是文本：文本匹配分不清「算式在 if 里」还是「在 else 里」。
        """
        import ast
        import textwrap

        tree = ast.parse(textwrap.dedent(self._source()))
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))

        # 找到 `key == "GT_ROW_UUID_LAST_ROW"` 那个分支
        target: ast.If | None = None
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            test_src = ast.unparse(node.test)
            if "GT_ROW_UUID_LAST_ROW" in test_src and "key ==" in test_src:
                target = node
                break
        assert target is not None, "找不到 GT_ROW_UUID_LAST_ROW 的分支"

        # 🔴 取分支的方式踩过两次，记下来免得第三次：
        #    ① 顺着 `orelse[0].orelse` 一路走 ⇒ 跨出本 if、落到**整个 key 分派链**末尾的
        #       兜底 `new_value = value`；
        #    ② 取 `target.orelse` ⇒ 那是整条 `elif` 链的**后续键**（`GT_FOOTER_ROW` /
        #       `GT_FOOTER_ROW_*` …），与本键无关。
        #    正确的是 `target.body` —— `key == "GT_ROW_UUID_LAST_ROW"` 成立时执行的那一段，
        #    里面才是「deleting 两支 + 插行一支」。
        inner = [
            ast.unparse(s)
            for node in target.body
            for s in ast.walk(node)
            if isinstance(s, (ast.Assign, ast.AnnAssign))
        ]
        insert_branch = "\n".join(inner)
        # 🔴 必须同时收 `ast.If` 与 `ast.IfExp`（三元表达式）的 test。
        #    变异反证抓到过：只收 `ast.If` 时，把门控写成
        #    `old_last_row + shift.count if is_primary_trip and … else old_last_row`
        #    （插行分支本来就是个三元表达式）**完全不会被发现** —— 判据当场绿着放过。
        inner_tests = [
            ast.unparse(s.test)
            for node in target.body
            for s in ast.walk(node)
            if isinstance(s, (ast.If, ast.IfExp))
        ]

        assert "insert_at" in insert_branch, (
            f"该键分支里没有 `insert_at` 算式（插行侧算术不见了），取到的是："
            f"{insert_branch[:200]!r}"
        )
        # 🔴 该键分支内部只允许出现 `deleting …` 门控；`is_primary_trip` 只能与
        #    `deleting` 合取（`deleting and not is_primary_trip`），不得单独出现
        #    —— 单独出现就意味着它也管到了插行那一支。
        solo_primary = [
            t for t in inner_tests if "is_primary_trip" in t and "deleting" not in t
        ]
        assert not solo_primary, (
            f"`GT_ROW_UUID_LAST_ROW` 分支里出现了不与 `deleting` 合取的 primary 门控："
            f"{solo_primary} —— 那会管到插行那一支，改动插行的冻结字节，"
            "Property 28 零回归基线要整册重取。插行时 primary 行号更小、算术碰不到它，"
            "加门控不改变行为却有代价，故刻意保持无条件（见该函数注释）。"
        )

    def test_the_asymmetry_is_documented_in_the_source(self) -> None:
        """🔴 这个不对称必须在源码里写明理由，否则下一个人会当成疏漏去「修正」。"""
        src = self._source()
        assert "插行分支" in src and "逐字不变" in src, (
            "源码里不再说明「插行分支逐字不变」⇒ 不对称失去依据"
        )
        assert "test_insert_side_global_keys_stay_unconditional" in src, (
            "源码注释不再指向本判据 —— 指向丢了之后，注释就又变成没人验证的声明"
        )
