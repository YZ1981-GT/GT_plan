# -*- coding: utf-8 -*-
"""A6 verify 侧归一化载体接线（Property 15 + 变异反证 + 空集显式断言）。

spec: workpaper-sync-row-deletion-multi-region-propagation
Tasks: 13.1 · 13.2 · 13.3 · 11.4
Requirements: 6.1~6.7 · 4.8

═══ 🔴 A6 的欠账比 design 描述的多一类（勘误节 E.3）═══

design「§ 七条欠账逐条」A6 原文只说「受管 sheet 里**未管理**的格行号变了」。实测（K11、
删 r=20）打红源精确分三类：

| # | 打红源 | `unshift` 能否表达 |
|---|---|---|
| ① | **被删行上的未管理格整体消失**（7 个） | 🔴 **不能** —— 格没了，不是行号变了 |
| ② | 受管 sheet 上未管理格里的**裸引用**没平移（3 处） | 由 **A5** 解决 |
| ③ | 合计区间（`SUM(B7:B25)`） | 由 **A5** 解决 |

⇒ 本文件的判据必须**同时**验两件事：载体（②③的归一化）与
:func:`deleted_row_coordinates`（①的两侧对称排除）。只验载体会永远打红，
只验排除会把②③的缺陷放过。
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

from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402

import test_row_deletion_apply_propagation as AP  # noqa: E402
import test_sibling_table_ref_row_shift as SIB  # noqa: E402

ASPECTS = ("managed_sheet_unmanaged_cells", "managed_sheet_structure")


# ═══════════════════════════════════════════════════════════════════════════
# 1. D1-8 世界 + before/after 落盘（verify 只吃 Path）
# ═══════════════════════════════════════════════════════════════════════════

world = AP.world  # pytest fixture 转发


@pytest.fixture(scope="module")
def verify_ctx(world: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """contract / binding / region / before 路径 —— verify 的必需入参。"""
    workdir = tmp_path_factory.mktemp("row-deletion-verify")
    before = workdir / "before.xlsx"
    before.write_bytes(world["bytes"])
    contract = AP.build_contract()
    binding = AP.build_binding()
    with zipfile.ZipFile(before) as zf:
        region = X.resolve_managed_region(zf, contract=contract, binding=binding)
    return {
        "workdir": workdir,
        "before": before,
        "contract": contract,
        "binding": binding,
        "region": region,
    }


def _write(workdir: Path, name: str, data: bytes) -> Path:
    path = workdir / name
    path.write_bytes(data)
    return path


def _digest(
    path: Path,
    ctx: dict[str, Any],
    *,
    row_shift: Any = None,
    total_formula_rows: tuple[int, ...] = (),
    propagation: Any = None,
    extra: frozenset[str] = frozenset(),
    collapse: frozenset[int] = frozenset(),
) -> Any:
    """一侧 digest。

    🔴 `collapse` 要**两侧都传**：结构块里端点落在被删行上的区间不可逆（E.6），
    排除必须对称。生产侧由 `verify_unmanaged_regions` 自己从载体导出（并进 before
    digest 缓存键），本 helper 是两侧分别调 ⇒ 由调用方显式传，值取自同一个公开函数
    `X.deletion_collapse_rows`（不在测试里手抄第二份口径）。
    生产侧真的这么接线，由 `TestStructureCollapseWiring` 判据钉死。
    """
    return X.unmanaged_region_digest(
        path,
        contract=ctx["contract"],
        region=ctx["region"],
        binding=ctx["binding"],
        row_shift=row_shift,
        total_formula_rows=total_formula_rows,
        propagation=propagation,
        extra_managed_coords=extra,
        structure_collapse_rows=collapse,
    )


def test_context_is_non_degenerate(verify_ctx: dict[str, Any]) -> None:
    """🔴 前提：region 解析到的就是 DISCOUNT 区 14..21。"""
    region = verify_ctx["region"]
    assert (region.first_row, region.last_row) == (AP.FIRST_ROW, AP.LAST_ROW), (
        f"region 实得 {region.first_row}..{region.last_row}，"
        f"应为 {AP.FIRST_ROW}..{AP.LAST_ROW}"
    )
    assert region.table_name == AP.TABLE


# ═══════════════════════════════════════════════════════════════════════════
# 2. Property 15：验证归一化等价且不被弱化
# ═══════════════════════════════════════════════════════════════════════════


def _delete_product(world: dict[str, Any], deleted: tuple[int, ...]) -> tuple[bytes, Any]:
    plan = AP._plan(world, deleted, total_formula_rows=(AP.FOOTER_ROW,))
    product, _ = M.apply_plan_zip_with_report(world["bytes"], plan)
    return product, plan


def _exclusions(
    world: dict[str, Any], ctx: dict[str, Any], deleted: tuple[int, ...]
) -> frozenset[str]:
    """两侧对称排除的坐标并集 —— 两类，各有各的不可归一化理由。

    * ①「被删行上的格整体消失」：`unshift` 是行号映射，表达不了「格不存在了」；
    * ②「合计区间端点塌陷」：`unshift` 是**存活行之间的双射**，塌陷端点没有区分得开的前像
      （design 勘误节 E.3 + E.6）。
    """
    vanished = X.deleted_row_coordinates(
        ctx["before"], sheet_part=world["sheet_part"], deleted_rows=deleted
    )
    collapsed = X.collapsed_total_formula_coordinates(
        ctx["before"], sheet_part=world["sheet_part"], total_formula_rows=(AP.FOOTER_ROW,)
    )
    return frozenset(vanished | collapsed)


class TestProperty15NormalisationIsEquivalentAndNotLoosened:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 15: 验证归一化等价且不被弱化**

    **Validates: Requirements 6.2, 6.4, 6.7**
    """

    @pytest.mark.parametrize(
        "deleted", [(AP.LAST_ROW,), (AP.FIRST_ROW,), (AP.FIRST_ROW + 2,), (AP.FIRST_ROW, AP.LAST_ROW)]
    )
    def test_two_aspects_are_equivalent_after_normalisation(
        self, world: dict[str, Any], verify_ctx: dict[str, Any], deleted: tuple[int, ...]
    ) -> None:
        """归一化（载体 + 被删行坐标排除 + 传播声明）后两个 aspect 判等价。"""
        product, plan = _delete_product(world, deleted)
        after = _write(verify_ctx["workdir"], f"after-{'-'.join(map(str, deleted))}.xlsx", product)
        extra = _exclusions(world, verify_ctx, deleted)
        assert extra, f"被删行 {list(deleted)} 上一个格都没有 ⇒ 排除是空转"
        collapse = X.deletion_collapse_rows(plan.row_deletion)
        assert collapse, "塌陷邻域为空 ⇒ 载体没在导出它"
        base = _digest(verify_ctx["before"], verify_ctx, extra=extra, collapse=collapse)
        target = _digest(
            after,
            verify_ctx,
            row_shift=plan.row_deletion,
            total_formula_rows=(AP.FOOTER_ROW,),
            propagation=plan.deletion_change,
            extra=extra,
            collapse=collapse,
        )
        for aspect in ASPECTS:
            assert target.aspects[aspect] == base.aspects[aspect], (
                f"删 {list(deleted)} 后 {aspect} 判漂移："
                f"before 覆盖 {base.coverage[aspect]} / after {target.coverage[aspect]}"
            )

    def test_without_the_carrier_it_judges_drift(
        self, world: dict[str, Any], verify_ctx: dict[str, Any]
    ) -> None:
        """🔴 变异反证：不传载体（`row_shift=None`）⇒ 必须判漂移。

        没有这条，「归一化把整类检查关掉了」也会让上面那条通过。
        """
        deleted = (AP.FIRST_ROW + 2,)
        product, plan = _delete_product(world, deleted)
        after = _write(verify_ctx["workdir"], "after-nocarrier.xlsx", product)
        extra = _exclusions(world, verify_ctx, deleted)
        base = _digest(verify_ctx["before"], verify_ctx, extra=extra)
        naive = _digest(
            after,
            verify_ctx,
            row_shift=None,
            propagation=plan.deletion_change,
            extra=extra,
        )
        assert any(naive.aspects[a] != base.aspects[a] for a in ASPECTS), (
            "不传载体也判等价 ⇒ 载体没在起作用，Property 15 恒真"
        )

    def test_deleted_row_exclusion_is_an_empty_denominator_on_this_fixture(
        self, world: dict[str, Any], verify_ctx: dict[str, Any]
    ) -> None:
        """🔴 如实登记：①类（被删行上的格消失）在 D1-8 上是**空分母**。

        `deleted_row_coordinates` 返回的坐标集**非空**（那一行当然有格），但它们
        **全部落在受管坐标里** —— D1-8 契约 16 个 field 覆盖了受管区整行宽度
        （A..Q），于是这些格从来就没进过 `managed_sheet_unmanaged_cells` 这个桶，
        排不排除都一样。所以这里**不能**写成「不排除就判漂移」的变异反证：
        那条断言在本 fixture 上恒假，写了就是把判据写死成红。

        ⚠️ 这条是**可伪证**的：哪天契约 field 缩窄、或者受管行上多出契约外的列，
        差集就非空 ⇒ 本条当场打红，逼迫重新判断（而不是静默继续按空分母走）。
        ①类**真实存在**的证明在下一条（注入式变异）。
        """
        deleted = (AP.FIRST_ROW + 2,)
        vanished = X.deleted_row_coordinates(
            verify_ctx["before"], sheet_part=world["sheet_part"], deleted_rows=deleted
        )
        assert vanished, f"被删行 {deleted[0]} 上一个格都没有 ⇒ fixture 不对"
        managed = X._managed_coordinates(
            contract=verify_ctx["contract"],
            region=verify_ctx["region"],
            binding=verify_ctx["binding"],
            scan=None,
        )
        assert not (vanished - managed), (
            f"被删行 {deleted[0]} 上出现了契约之外的格 {sorted(vanished - managed)[:8]} ⇒ "
            "①类在本 fixture 上不再是空分母，请把上一条变异反证改回『不排除即判漂移』"
        )

    def test_the_deleted_row_exclusion_really_catches_a_vanishing_unmanaged_cell(
        self, world: dict[str, Any], verify_ctx: dict[str, Any]
    ) -> None:
        """🔴 变异反证之二（注入式）：受管行上真有未管理格时，不排除**必须**判漂移。

        上一条说明 D1-8 天然碰不到 ①类；这条把 ①类**造出来** —— 往被删行注入一个
        契约之外的列（`AB`），于是 before 有它、after 因整行删除而没有：
        * 不排除 ⇒ 判漂移（证明扫描器真的会看见这一类，不是被关掉了）；
        * 排除   ⇒ 判等价（证明排除是这一类的正解）。

        没有这一条，上一条的「空分母」就是一句无法验证的自述。
        """
        deleted = (AP.FIRST_ROW + 2,)
        injected_col = "AB"
        coord = f"{injected_col}{deleted[0]}"

        entries = dict(world["entries"])
        xml = entries[world["sheet_part"]].decode("utf-8")
        row_re = re.compile(rf'(<row\b[^>]*\br="{deleted[0]}"[^>]*>)(.*?)(</row>)', re.S)
        m = row_re.search(xml)
        assert m is not None, f"定位不到 <row r=\"{deleted[0]}\">"
        mutated_xml = (
            xml[: m.start()]
            + m.group(1)
            + m.group(2)
            + f'<c r="{coord}"><v>424242</v></c>'
            + m.group(3)
            + xml[m.end() :]
        )
        entries[world["sheet_part"]] = mutated_xml.encode("utf-8")
        mutated_bytes = M._write_entries(entries)
        mutated_world = {**world, "bytes": mutated_bytes, "entries": entries}
        before = _write(verify_ctx["workdir"], "before-injected-unmanaged.xlsx", mutated_bytes)

        managed = X._managed_coordinates(
            contract=verify_ctx["contract"],
            region=verify_ctx["region"],
            binding=verify_ctx["binding"],
            scan=None,
        )
        assert coord not in managed, f"{coord} 居然是受管坐标 ⇒ 换一个契约外的列"
        vanished = X.deleted_row_coordinates(
            before, sheet_part=world["sheet_part"], deleted_rows=deleted
        )
        assert coord in vanished, f"注入的 {coord} 没被 deleted_row_coordinates 看见"

        product, plan = _delete_product(mutated_world, deleted)
        after = _write(verify_ctx["workdir"], "after-injected-unmanaged.xlsx", product)
        assert coord not in X.deleted_row_coordinates(
            after, sheet_part=world["sheet_part"], deleted_rows=deleted
        ), f"{coord} 在产物里还在 ⇒ 整行没被真删掉，本条判据空转"

        collapsed = X.collapsed_total_formula_coordinates(
            before, sheet_part=world["sheet_part"], total_formula_rows=(AP.FOOTER_ROW,)
        )
        collapse = X.deletion_collapse_rows(plan.row_deletion)
        kwargs: dict[str, Any] = dict(
            row_shift=plan.row_deletion,
            total_formula_rows=(AP.FOOTER_ROW,),
            propagation=plan.deletion_change,
            collapse=collapse,
        )
        # ① 不排除被删行坐标 ⇒ 必须判漂移
        naive_base = _digest(before, verify_ctx, extra=collapsed, collapse=collapse)
        naive = _digest(after, verify_ctx, extra=collapsed, **kwargs)
        assert (
            naive.aspects["managed_sheet_unmanaged_cells"]
            != naive_base.aspects["managed_sheet_unmanaged_cells"]
        ), "注入了消失的未管理格却仍判等价 ⇒ ①类扫描器被关掉了"
        # ② 排除后 ⇒ 判等价
        extra = frozenset(vanished | collapsed)
        fixed_base = _digest(before, verify_ctx, extra=extra, collapse=collapse)
        fixed = _digest(after, verify_ctx, extra=extra, **kwargs)
        assert (
            fixed.aspects["managed_sheet_unmanaged_cells"]
            == fixed_base.aspects["managed_sheet_unmanaged_cells"]
        ), "排除被删行坐标后仍判漂移 ⇒ 排除不是 ①类的正解"

    def test_without_the_collapsed_total_exclusion_it_judges_drift(
        self, world: dict[str, Any], verify_ctx: dict[str, Any]
    ) -> None:
        """🔴 变异反证之三：不排除合计格 ⇒ 必须判漂移（②类：端点塌陷不可逆）。

        这条把「Requirement 6.4 的『还原收缩』不可能由行号逆映射实现」钉成判据。
        """
        deleted = (AP.LAST_ROW,)
        product, plan = _delete_product(world, deleted)
        after = _write(verify_ctx["workdir"], "after-nocollapse.xlsx", product)
        vanished = X.deleted_row_coordinates(
            verify_ctx["before"], sheet_part=world["sheet_part"], deleted_rows=deleted
        )
        base = _digest(verify_ctx["before"], verify_ctx, extra=vanished)
        target = _digest(
            after,
            verify_ctx,
            row_shift=plan.row_deletion,
            total_formula_rows=(AP.FOOTER_ROW,),
            propagation=plan.deletion_change,
            extra=vanished,
        )
        assert target.aspects["managed_sheet_unmanaged_cells"] != base.aspects[
            "managed_sheet_unmanaged_cells"
        ], "不排除合计格也判等价 ⇒ ②类不存在（换靶子或登记为空分母）"

    def test_injected_change_outside_the_declaration_still_judges_drift(
        self, world: dict[str, Any], verify_ctx: dict[str, Any]
    ) -> None:
        """🔴 归一化**不放宽**与行变更无关的判据：声明之外的任何字节改动仍判漂移。

        这是 Requirement 6.7 的实质：否则「归一化」就变成了「整桶放行」。
        """
        deleted = (AP.FIRST_ROW + 2,)
        product, plan = _delete_product(world, deleted)
        entries = AP._entries_of(product)
        xml = entries[world["sheet_part"]].decode("utf-8")
        # 在受管区**之上**（不受删行影响、也不在受管坐标里）注入一处值改写
        target_cell = None
        for m in re.finditer(r'<c\b[^>]*\br="([A-Z]+)(\d+)"[^>]*>(?:(?!</c>).)*?<v>([^<]*)</v>', xml, re.S):
            if int(m.group(2)) < AP.FIRST_ROW:
                target_cell = m
                break
        assert target_cell is not None, "受管区之上没有带 <v> 的格可改 ⇒ 本条判据空转"
        mutated_xml = (
            xml[: target_cell.start()]
            + target_cell.group(0).replace(f"<v>{target_cell.group(3)}</v>", "<v>999777</v>")
            + xml[target_cell.end() :]
        )
        assert mutated_xml != xml
        entries[world["sheet_part"]] = mutated_xml.encode("utf-8")
        mutated = _write(verify_ctx["workdir"], "after-injected.xlsx", M._write_entries(entries))
        extra = _exclusions(world, verify_ctx, deleted)
        base = _digest(verify_ctx["before"], verify_ctx, extra=extra)
        got = _digest(
            mutated,
            verify_ctx,
            row_shift=plan.row_deletion,
            total_formula_rows=(AP.FOOTER_ROW,),
            propagation=plan.deletion_change,
            extra=extra,
        )
        assert got.aspects["managed_sheet_unmanaged_cells"] != base.aspects[
            "managed_sheet_unmanaged_cells"
        ], "注入的、声明之外的值改写被归一化抹平了 ⇒ 判据被弱化（Requirement 6.7）"

    def test_collapse_is_provably_not_invertible_by_a_row_remap(self) -> None:
        """🔴 把「Requirement 6.4 的还原不可能由行号逆映射实现」证成判据（双射性质）。

        ═══ 这条推翻了本 spec 勘误节 E.3 的结论（我自己的错，记录在此）═══

        E.3 当时的探针只删了**区内**一行（K11 的 r=20，区 7..25），那时 `SUM(B7:B25)`
        收缩成 `SUM(B7:B24)`，而 24 是**存活行**、前像恰好是 25 ⇒ `unshift` 还原成功
        ⇒ 我据此写下「删行侧不需要 unextend 对偶」。
        **样本缺了边界**：删区**末行**（或区**首行**）时端点自己塌陷，塌陷后的端点是一个
        **存活行**，它的前像就是它自己，不是被删的那个端点 ⇒ 还原不回去。

        这不是实现缺陷而是**双射性质**：`unshift` 是「删后存活行 ↔ 删前行」的双射，
        塌陷端点在删前有两个候选（它自己 / 被删的原端点），一个双射分辨不出来。
        ⇒ 诚实的落法是把合计格两侧对称排除，收缩的正确性交给 A7 的 footer 两门
        （那是更强的判据：检查「区间是否恰好覆盖受管行」而非「文本能否还原」）。
        """
        from app.services.workpaper_sync.excel_row_shift import remap_a1_rows

        # ① 删**区内**行：`unshift` 能还原（E.3 当时看到的那一态）
        inner = N1.RowDeletionShift(
            deleted_rows=(AP.FIRST_ROW + 2,),
            region_first_row=AP.FIRST_ROW,
            region_last_row=AP.LAST_ROW,
        )
        shrunk = f"SUM(F{AP.FIRST_ROW}:F{AP.LAST_ROW - 1})"
        assert remap_a1_rows(shrunk, remap=inner.unshift) == (
            f"SUM(F{AP.FIRST_ROW}:F{AP.LAST_ROW})"
        ), "区内删行本应可还原 —— 若这条红了，E.3 的那一半也不成立了"

        # ② 删**区末行**：`unshift` 还原不回去（E.3 漏掉的边界）
        tail_del = N1.RowDeletionShift(
            deleted_rows=(AP.LAST_ROW,),
            region_first_row=AP.FIRST_ROW,
            region_last_row=AP.LAST_ROW,
        )
        assert remap_a1_rows(shrunk, remap=tail_del.unshift) == shrunk, (
            "删区末行后 `unshift` 竟然还原了末行 —— 与双射性质矛盾，先复核载体实现"
        )

        # ③ 删**区首行**：首行方向同样不可逆，而 `_rewrite_formula_refs` 没有
        #    `extend_start_at` 钩子（且 Requirement 10.1 禁止改它）⇒ 连「补一次修正」都做不到
        head_del = N1.RowDeletionShift(
            deleted_rows=(AP.FIRST_ROW,),
            region_first_row=AP.FIRST_ROW,
            region_last_row=AP.LAST_ROW,
        )
        assert head_del.shift_range_start(AP.FIRST_ROW) == AP.FIRST_ROW
        assert head_del.unshift(AP.FIRST_ROW) != AP.FIRST_ROW, (
            "删区首行后 after 的首行 unshift 回到了自己 —— 那本条的论证前提不成立"
        )
        import inspect

        from app.services.workpaper_sync import excel_row_shift as RS

        params = inspect.signature(RS._rewrite_formula_refs).parameters
        assert "extend_end_at" in params, "末行钩子不见了 ⇒ 本条的对照论证失效"
        assert "extend_start_at" not in params, (
            "改写器有了 `extend_start_at` ⇒ 本条的「连补一次修正都做不到」已过时，"
            "请重新评估是否改用「还原」而非「排除」"
        )

        # ④ 删行侧**没有**引入 unextend 对偶（排除路线的必然推论）
        #
        # 🔴 判据用 AST 不用文本 `in`（工作区铁律 ㉖）：首版写成 `"unextend" not in src`
        #    当场命中**本模块自己 docstring 里**提到 `unextend_total_formula` 的那句话，
        #    是个纯假红。注释与 docstring 在 AST 里是 `Expr(Constant)`，不产生 `Name`/
        #    `Attribute` 节点 ⇒ 天然被排除，只有**真的调用它**才会命中。
        import ast

        path = _BACKEND / "app/services/workpaper_sync/excel_workbook_row_change.py"
        tree = ast.parse(path.read_bytes().decode("utf-8"))
        calls = sorted(
            {
                name
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                for name in (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.attr if isinstance(node.func, ast.Attribute) else "",
                )
                if name.startswith("unextend")
            }
        )
        assert not calls, (
            f"删行侧引入了 unextend 对偶（{calls}）—— 本 spec 走的是「排除 + footer 两门」"
            "路线，两条路线并存会重复减一次"
        )
        # 反向变异：同一个扫描器在**真有**该调用的模块上必须命中，否则它是恒真的
        verifier = ast.parse(
            (_BACKEND / "app/services/workpaper_sync/excel_extract.py")
            .read_bytes()
            .decode("utf-8")
        )
        assert any(
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Name) and node.func.id.startswith("unextend"))
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr.startswith("unextend")
                )
            )
            for node in ast.walk(verifier)
        ), (
            "AST 扫描器在插行侧 verifier（真的调 unextend_total_formula_chain）上也零命中 "
            "⇒ 扫描器本身失效，上面那条断言是恒真的"
        )


class TestCarrierEmptyInsertedSetIsAssertedAtVerify:
    """**Validates: Requirements 6.5, 6.6**

    🔴 `_normalise_cell_ref` 里有 `if row in inserted: return ""`。删行路径上 `inserted`
    恒空 ⇒ 该分支不可达。**在 verify 入参处显式断言空集**，否则将来有人把被删行填进
    `inserted_rows`，症状是 after 侧的格被静默跳过 ⇒ 真实漂移被抹平（假绿）。
    """

    def test_inserted_rows_is_empty_at_the_verify_boundary(
        self, world: dict[str, Any]
    ) -> None:
        _product, plan = _delete_product(world, (AP.FIRST_ROW + 1,))
        assert plan.row_deletion.inserted_rows == frozenset()

    def test_annotation_accepts_the_deletion_carrier(self) -> None:
        """🔴 注解也要认它：运行期鸭子兼容 ≠ 静态类型认账。

        7 处入参收敛成一个别名 `RowChangeCarrier` —— 在 7 处各列三个类型时，
        漏改一处会让删行载体在**那一处**被判非法而运行期照样跑（注解与实现不符）。
        """
        import typing

        args = typing.get_args(X.RowChangeCarrier)
        names = {getattr(a, "__name__", None) or getattr(a, "__forward_arg__", None) for a in args}
        assert names == {"RowShiftPlan", "CompositeRowShift", "RowDeletionShift"}, names
        src = (
            _BACKEND / "app/services/workpaper_sync/excel_extract.py"
        ).read_bytes().decode("utf-8")
        assert "RowShiftPlan | CompositeRowShift" not in src, (
            "还有地方写着两载体的旧注解 —— 收敛没做完"
        )
        assert src.count("RowChangeCarrier") >= 8


# ═══════════════════════════════════════════════════════════════════════════
# 4. 结构块两条平台级收口（A8 属主表 + 塌陷排除的生产侧接线）
# ═══════════════════════════════════════════════════════════════════════════


class TestStructureAttrOwnership:
    """**Validates: Requirement 6.2**（A8 的属主表，design 勘误节 E.7）

    🔴 `dimension@ref` 同时落在两处：
    * `STRUCTURE_ROW_BEARING_ATTRS`（它确实携带行号，verifier 要归一化它）；
    * `shrink_sheet_rows` 的改写范围（它是删行的**本职**动作）。

    A8 照派生表无脑遍历 ⇒ 同一属性被收缩两次。实测 D1-8：`A1:AD38` 先被
    `shrink_sheet_rows` 正确改成 `A1:AD37`，再被 A8 改成 `A1:AD36`，而 verify 侧
    `unshift` 只能还原一次 ⇒ `managed_sheet_structure` 判漂移。产物侧的真实后果是
    `<dimension>` 比实际行数少一行。

    所以本类要同时立**正向**（属主真的在改它）与**反向**（A8 真的不碰它）两条。
    """

    def test_ownership_table_is_a_subset_of_the_derived_table(self) -> None:
        """登记项必须真的是派生表里的项 —— 否则是一条失效的豁免（铁律：豁免须可伪证）。"""
        from app.services.workpaper_sync.excel_row_shift import (
            STRUCTURE_ROW_BEARING_ATTRS,
        )

        assert M.STRUCTURE_ATTRS_OWNED_BY_SHRINK, "属主表空了 ⇒ 这条收口没了"
        for tag, attr in M.STRUCTURE_ATTRS_OWNED_BY_SHRINK:
            assert attr in STRUCTURE_ROW_BEARING_ATTRS.get(tag, ()), (
                f"{tag}@{attr} 已不在派生表里 ⇒ 这条豁免失效了，请删掉它"
                "（留着就是掩盖『A8 漏改一个真携带行号的属性』）"
            )

    def test_shrink_sheet_rows_really_owns_dimension(self) -> None:
        """🔴 正向：属主真的在改它。属主不改而 A8 也跳过 = 两边都不管，静默漏改。"""
        xml = (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<dimension ref="A1:AD38"/><sheetData>'
            '<row r="16"><c r="A16"><v>1</v></c></row>'
            '<row r="17"><c r="A17"><v>2</v></c></row>'
            "</sheetData></worksheet>"
        )
        shrunk, _ = N1.shrink_sheet_rows(xml, delete_at=16, count=1)
        assert 'ref="A1:AD37"' in shrunk, (
            f"`shrink_sheet_rows` 没有收缩 <dimension> ⇒ 属主表的前提不成立：{shrunk[:200]}"
        )

    def test_a8_does_not_touch_owned_attrs(self, world: dict[str, Any]) -> None:
        """🔴 反向：A8 单独跑一遍，`dimension` 必须逐字不变。"""
        plan = AP._plan(world, (16,), total_formula_rows=(AP.FOOTER_ROW,))
        xml = (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<dimension ref="A1:AD38"/>'
            '<mergeCells count="1"><mergeCell ref="N24:N25"/></mergeCells>'
            "</worksheet>"
        )
        out, changed = M._shift_managed_sheet_structures(xml, plan=plan)
        assert 'ref="A1:AD38"' in out, f"A8 动了 <dimension> ⇒ 会二次收缩：{out}"
        # 同一次调用里**别的**结构必须真被改了 —— 否则「没动 dimension」只是因为 A8 空转
        assert 'ref="N23:N24"' in out, f"A8 连 mergeCell 都没改 ⇒ 本条是空转：{out}"
        assert changed == 1, f"改动处数应为 1（只 mergeCell），实得 {changed}"


class TestStructureCollapseWiring:
    """**Validates: Requirements 6.2, 6.3**（塌陷排除的**生产侧**接线，勘误节 E.6）

    上面 Property 15 的 helper 是两侧分别调 digest、由测试显式传 `collapse`。
    那证明不了**生产入口**也这么接线 —— 这里直接走 `verify_unmanaged_regions`。
    """

    def _ctx_kwargs(self, verify_ctx: dict[str, Any]) -> dict[str, Any]:
        return dict(
            contract=verify_ctx["contract"],
            region=verify_ctx["region"],
            binding=verify_ctx["binding"],
        )

    def test_production_entrypoint_judges_equivalent(
        self, world: dict[str, Any], verify_ctx: dict[str, Any]
    ) -> None:
        """🔴 真实链路：删受管末行（端点塌陷最狠的一档）⇒ 生产入口判等价。"""
        deleted = (AP.LAST_ROW,)
        product, plan = _delete_product(world, deleted)
        after = _write(verify_ctx["workdir"], "after-entrypoint.xlsx", product)
        report = X.verify_unmanaged_regions(
            before=verify_ctx["before"],
            after=after,
            **self._ctx_kwargs(verify_ctx),
            row_shift=plan.row_deletion,
            total_formula_rows=(AP.FOOTER_ROW,),
            propagation=plan.deletion_change,
            extra_managed_coords=_exclusions(world, verify_ctx, deleted),
        )
        assert report.equivalent, report.first_difference

    def test_entrypoint_still_catches_an_undeclared_change(
        self, world: dict[str, Any], verify_ctx: dict[str, Any]
    ) -> None:
        """🔴 变异反证：往结构块注入一处声明之外的改动 ⇒ 生产入口必须判漂移。

        没有这条，上一条的「判等价」可能只是因为整个 aspect 被排干净了。
        """
        deleted = (AP.LAST_ROW,)
        product, plan = _delete_product(world, deleted)
        entries = AP._entries_of(product)
        xml = entries[world["sheet_part"]].decode("utf-8")
        m = re.search(r'<mergeCell ref="([A-Z]+\d+:[A-Z]+\d+)"/>', xml)
        assert m is not None, "产物里没有 mergeCell ⇒ 本条判据空转，换注入点"
        mutated = xml.replace(m.group(0), '<mergeCell ref="AA2:AA3"/>', 1)
        assert mutated != xml
        entries[world["sheet_part"]] = mutated.encode("utf-8")
        after = _write(
            verify_ctx["workdir"], "after-struct-tampered.xlsx", M._write_entries(entries)
        )
        report = X.verify_unmanaged_regions(
            before=verify_ctx["before"],
            after=after,
            **self._ctx_kwargs(verify_ctx),
            row_shift=plan.row_deletion,
            total_formula_rows=(AP.FOOTER_ROW,),
            propagation=plan.deletion_change,
            extra_managed_coords=_exclusions(world, verify_ctx, deleted),
        )
        assert not report.equivalent, (
            "改了一个 mergeCell 还判等价 ⇒ 塌陷排除把整个结构 aspect 放行了"
        )
        assert "managed_sheet_structure" in (report.first_difference or "")

    def test_before_side_gets_collapse_rows_but_no_carrier(
        self, world: dict[str, Any], verify_ctx: dict[str, Any], monkeypatch: Any
    ) -> None:
        """🔴 before 侧只收排除集合、**不**收载体（Requirement 6.3：只归一化 after）。"""
        deleted = (AP.LAST_ROW,)
        product, plan = _delete_product(world, deleted)
        after = _write(verify_ctx["workdir"], "after-spy.xlsx", product)
        calls: list[dict[str, Any]] = []
        real = X.unmanaged_region_digest

        def _spy(path: Path, **kwargs: Any) -> Any:
            calls.append({"path": path, **kwargs})
            return real(path, **kwargs)

        monkeypatch.setattr(X, "unmanaged_region_digest", _spy)
        from app.services.workpaper_sync.parse_cache import BEFORE_DIGEST_CACHE

        BEFORE_DIGEST_CACHE.clear()
        X.verify_unmanaged_regions(
            before=verify_ctx["before"],
            after=after,
            **self._ctx_kwargs(verify_ctx),
            row_shift=plan.row_deletion,
            total_formula_rows=(AP.FOOTER_ROW,),
            propagation=plan.deletion_change,
            extra_managed_coords=_exclusions(world, verify_ctx, deleted),
        )
        before_calls = [c for c in calls if c["path"] == verify_ctx["before"]]
        assert len(before_calls) == 1, f"before 侧调用了 {len(before_calls)} 次"
        got = before_calls[0]
        assert got.get("structure_collapse_rows") == X.deletion_collapse_rows(
            plan.row_deletion
        ), f"before 侧没拿到塌陷集合：{got.get('structure_collapse_rows')}"
        assert got.get("row_shift") is None, "before 侧拿到了载体 ⇒ 两侧都归一化 = 都没归一化"

    def test_before_digest_cache_key_separates_different_deletions(
        self, world: dict[str, Any], verify_ctx: dict[str, Any], monkeypatch: Any
    ) -> None:
        """🔴 塌陷集合必须进 before digest 缓存键，否则**跨声明串味**。

        同一份 before 字节、两组不同的被删行 ⇒ 排除集合不同 ⇒ before digest 不同。
        键里不带它就会拿上一组的 digest 跟本组 after 比。
        """
        from app.services.workpaper_sync.parse_cache import BEFORE_DIGEST_CACHE

        keys: list[str] = []
        # 🔴 `BoundedLruCache` 带 `__slots__` ⇒ 实例属性只读，只能 patch **类**上的方法。
        cache_cls = type(BEFORE_DIGEST_CACHE)
        real_put = cache_cls.put

        def _spy_put(self: Any, key: str, value: Any) -> Any:
            if self is BEFORE_DIGEST_CACHE:
                keys.append(key)
            return real_put(self, key, value)

        monkeypatch.setattr(cache_cls, "put", _spy_put)
        cases = ((AP.LAST_ROW,), (AP.FIRST_ROW + 2,))
        # 🔴 `extra_managed_coords` 两组**取并集后固定**：它本来也会随被删行变化，不固定
        # 的话键里有两段都不同，就证明不了「差异来自塌陷集合」。
        extra = frozenset().union(*(_exclusions(world, verify_ctx, d) for d in cases))
        for deleted in cases:
            BEFORE_DIGEST_CACHE.clear()
            product, plan = _delete_product(world, deleted)
            after = _write(
                verify_ctx["workdir"], f"after-key-{deleted[0]}.xlsx", product
            )
            X.verify_unmanaged_regions(
                before=verify_ctx["before"],
                after=after,
                **self._ctx_kwargs(verify_ctx),
                row_shift=plan.row_deletion,
                total_formula_rows=(AP.FOOTER_ROW,),
                propagation=plan.deletion_change,
                extra_managed_coords=extra,
            )
        assert len(keys) == 2, f"before digest 没被算两次：{len(keys)}"
        assert keys[0] != keys[1], (
            "两组不同被删行算出了同一个 before 缓存键 ⇒ 塌陷集合没进键，会跨声明串味"
        )
        # 且差异必须**就是**塌陷集合那一段（不是别的字段碰巧不同）
        a, b = (k.rsplit("|", 1) for k in keys)
        assert a[0] == b[0], f"键的其余部分也不同 ⇒ 本条没在测塌陷集合：{keys}"
        assert a[1] != b[1]
