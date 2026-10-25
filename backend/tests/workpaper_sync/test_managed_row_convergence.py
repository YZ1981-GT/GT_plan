"""受管行收敛 + 模板骨架豁免的判据守卫。

spec: workpaper-sync-managed-row-convergence（Requirement 4 / 更正 4·6 / E3）

本文件锁三组不变量，每组都配**变异反证**（去掉被测那一半即打红）：

A. `is_template_skeleton_identity` 的域划分 —— 模板预生成 vs 运行期 mint 刻意不同域
B. roundtrip 的模板骨架豁免是**合取**条件，不弱化 fail-closed
C. 收敛判据与 overlay 严格对偶（store 未声明的 table 一律不碰）

🔴 为什么这些判据必须存在：D4 实测过全部三条的反面后果 ——
   A 反面：把骨架行当 stale 删 ⇒ `IdentityRetentionError`（4 个既有测试打红）
   B 反面：只按「是骨架」豁免 ⇒ store 声明了却缺字段也被放过 ⇒ 静默丢数据
   C 反面：不判 table 是否被声明 ⇒ 误删 store 根本没管的表
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.contracts import (  # noqa: E402
    is_template_skeleton_identity,
)
from app.services.workpaper_sync.excel_extract import (  # noqa: E402
    MINTED_ROW_IDENTITY_PREFIX,
)


class TestSkeletonIdentityDomain:
    """A：模板预生成身份与运行期 mint 身份必须可分辨（两者刻意不同域）。"""

    @pytest.mark.parametrize(
        "identity",
        [
            "GTROW-D410-0013",
            "GTROW-D41MAIN-0009",
            "GTROW-D422-0012",
            "GTROW-D49C-0014",
        ],
    )
    def test_template_pregenerated_identities_are_skeleton(self, identity: str) -> None:
        assert is_template_skeleton_identity(identity) is True

    @pytest.mark.parametrize(
        "identity",
        [
            # 运行期 mint —— **不是**骨架，必须参与全部判据
            "GTROW-MINTED-0001",
            "GTROW-MINTED-abc123",
            # 前端生成的行身份
            "d4r-muks1021-6q6wuvm",
            "xsheet-main-L2MARK-D4-2-nmna",
            # 形态不符（位数不是 4 / 缺段 / 空）
            "GTROW-D410-013",
            "GTROW-D410",
            "GTROW--0013",
            "",
        ],
    )
    def test_non_template_identities_are_not_skeleton(self, identity: str) -> None:
        assert is_template_skeleton_identity(identity) is False

    def test_minted_prefix_is_excluded_by_construction(self) -> None:
        """🔴 变异反证：minted 前缀若被判成骨架，OO 新增行会被误豁免/误删。

        这条断言把 `excel_extract.MINTED_ROW_IDENTITY_PREFIX` 与本判据绑在一起 ——
        将来任一侧改了前缀命名，这里立刻红，而不是等到「OO 新增行静默丢失」。
        """
        minted = f"{MINTED_ROW_IDENTITY_PREFIX}0001"
        assert minted.startswith("GTROW-MINTED-")
        assert is_template_skeleton_identity(minted) is False


class TestRoundtripSkeletonExemptionIsConjunctive:
    """B：豁免 = 「是骨架」∧「store 未声明该行」。缺任一半都必须仍然报错。"""

    @staticmethod
    def _filter(extra: list[str], declared: set[str]) -> list[str]:
        """复刻 `content_mutation._assert_roundtrip_equivalent` 的豁免过滤。

        🔴 刻意**复刻而非 import 私有方法**：判据的形态本身就是被守护的对象；
        直接调生产私有函数会让「生产改了形态」与「判据改了形态」同步漂移，
        守卫就永远绿（本平台反复踩过的假绿形态）。
        下方 `test_production_filter_shape_matches` 用源码断言两者未漂移。
        """
        retained = []
        for key in extra:
            parts = key.split("/")
            identity = parts[1] if len(parts) >= 3 else ""
            if (
                identity
                and identity not in declared
                and is_template_skeleton_identity(identity)
            ):
                continue
            retained.append(key)
        return retained

    def test_skeleton_row_not_declared_by_store_is_exempt(self) -> None:
        """模板骨架行 + store 未声明 ⇒ 豁免（这是 D4 的 77→0 那条路）。"""
        extra = ["d4_10_rows/GTROW-D410-0013/customer"]
        assert self._filter(extra, declared=set()) == []

    def test_skeleton_row_declared_by_store_still_reported(self) -> None:
        """🔴 变异反证之一：store **声明了**该骨架行却缺字段 ⇒ 仍须报错。

        否则「store 认领了一行却没把字段写全」会被静默放过 —— 那是真实的数据丢失。
        """
        extra = ["d4_10_rows/GTROW-D410-0013/customer"]
        declared = {"GTROW-D410-0013"}
        assert self._filter(extra, declared=declared) == extra

    @pytest.mark.parametrize(
        "identity",
        ["d4r-muks1021-6q6wuvm", "xsheet-main-x", "GTROW-MINTED-0001"],
    )
    def test_non_skeleton_orphan_still_reported(self, identity: str) -> None:
        """🔴 变异反证之二：非骨架孤儿 ⇒ 仍须报错（由收敛逻辑删除，不是豁免）。"""
        extra = [f"revenue_detail_rows/{identity}/product"]
        assert self._filter(extra, declared=set()) == extra

    def test_production_filter_shape_matches(self) -> None:
        """生产侧豁免仍是**合取三条件**，且仍调共享真源。

        判据形态漂移（例如有人把 `and identity not in declared` 删掉以「简化」）
        会让上面两条变异反证仍绿（它们测的是本文件的复刻件），故在此直接锁源码。

        🔴 **本锁必须跟随间接层**（删行 spec 复盘）：`_assert_roundtrip_equivalent`
        现在是**薄壳**，真实现搬到了模块级 `assert_roundtrip_equivalent`。只 getsource
        那个方法会读到 3 行转发代码 ⇒ 三条 `assert ... in src` 全部落空，
        锁变**空转**（而不是打红）。因此这里把薄壳与被转发函数的源码**并起来**看：
        实现无论留在方法里还是搬到模块级，本锁都成立。
        """
        import inspect

        from app.services.workpaper_sync import content_mutation

        src = inspect.getsource(
            content_mutation.ContentMutationService._assert_roundtrip_equivalent
        ) + inspect.getsource(content_mutation.assert_roundtrip_equivalent)
        assert "is_template_skeleton_identity" in src, (
            "roundtrip 豁免不再调共享真源 —— 模板骨架判定可能被抄了第二份"
        )
        assert "identity not in declared" in src, (
            "豁免不再要求「store 未声明该行」—— 合取退化成单条件，"
            "store 声明了却缺字段会被静默放过"
        )
        assert "intended.row_keys" in src, (
            "豁免不再从 intended.row_keys 取已声明身份 —— declared 集合来源可疑"
        )


class TestConvergenceIsDualToOverlay:
    """C：收敛判据与 overlay 严格对偶 —— store 未声明的 table 一律不碰。"""

    def test_plan_managed_writes_guards_table_declaration(self) -> None:
        """源码锁：收敛必须在 `table_key in projection.row_keys` 前提下才发生。

        🔴 用 `in` 而不是 `get(...)`：`table_key 不在 row_keys`（store 没声明这张表）
        与 `row_keys[table_key] == ()`（store 声明了且为空 ⇒ 该清空整表）**语义不同**，
        用 `get` 取空值会把两者混成一个，于是「store 没管的表」会被误收敛。
        """
        import inspect

        from app.services.workpaper_sync import excel_materialize

        src = inspect.getsource(excel_materialize.plan_managed_writes)
        assert "in projection.row_keys" in src, (
            "收敛不再判「store 是否声明了该 table」—— 会误删 store 根本没管的表"
        )
        assert "is_template_skeleton_identity" in src, (
            "收敛不再排除模板骨架行 —— 会删掉模板预置行并触发 IdentityRetentionError"
        )

    def test_convergence_clears_cells_and_never_deletes_rows(self) -> None:
        """源码锁：收敛动作是**清空 editable 业务格**，不删物理行（G2 裁决）。

        ═══ 为什么不删行（两条实测依据）═══

        ① 删行牵动整套行号位移联动，插行路径为此有专门处理（`_shift_sibling_table_refs`
           同 sheet 兄弟 Table ref / footer 重冻结 / `_apply_workbook_propagation` 的
           definedName 与跨 sheet 公式）。只补了自己那一个 Table ref 收缩就导致 other 区
           出现 uuid 空行 ⇒ 反读被重新 mint `GTROW-MINTED-*` ⇒ 又一轮 extra。
        ② D4-31 的受管区**就是一行**（`table_ref='A5:K5'`），任何把受管区减到 0 行的动作
           都会让 extract 抛 `IdentityCarrierMissingError`。清空天然不触碰行数。

        🔴 断言「清空分支存在」而非「删行分支不存在」：`stale_deleted` 与 apply 期的
        `shrink_sheet_rows` 路径**刻意保留**（留给后续独立 spec 补齐多区位移联动后再启用），
        所以不能断言它们被删掉；要锁的是**收敛实际走清空**这件事。

        ═══ 🔴 2026-09-29 前提反转（spec workpaper-sync-row-deletion-multi-region-propagation）═══

        上面①说的「多区位移联动尚未补齐」**已经补齐**（A1~A8 八条欠账全部落地）。于是原来
        那条反向断言 `"stale_deleted = tuple(sorted(stale_rows))" not in src` 的前提不再成立：
        它现在拦的不是缺陷，而是**已经做对的事**。

        按 Requirement 12 的要求，这条反向断言被**替换**而不是删掉 —— 三条正向断言接管它
        （见本类下面三个 `test_deletion_*`）：删行计划必带两份声明 / 必落在契约门控之内 /
        apply 必须依次经过五个位移动作。

        清空**仍然是默认分支**（契约不声明 `row_convergence=delete` 就走清空），所以本条
        判据的正面部分（`stale_cleared` 那两行）原样保留、且实施期现读确认仍成立。
        """
        import inspect

        from app.services.workpaper_sync import excel_materialize

        src = inspect.getsource(excel_materialize.plan_managed_writes)
        assert "stale_cleared = tuple(sorted(stale_rows))" in src, (
            "收敛不再把全部 stale 行登记为 cleared —— 可能改回了删行分支"
        )
        # 清空必须跳过受保护格（否则毁模板公式）
        assert "spec.mode in PROTECTED_MODES" in src, (
            "清空不再跳过公式/auto_source 格 —— 会毁模板公式"
        )
        # 🔴 原「收敛不得产出删行计划」的反向断言已被下面三条正向断言替换
        #    （spec workpaper-sync-row-deletion-multi-region-propagation Requirement 12）。
        #    这里补一条**默认性**断言顶上它的位置：清空必须是**无条件**可达的分支，
        #    不得被契约门控包住 —— 否则未开启删行的表连清空都不做，stale 行被静默留下
        #    ⇒ 又一轮 extra（那正是原断言真正想防的后果）。
        assert "if stale_rows and not stale_deleted:" in src, (
            "清空分支的门变了 —— 它必须是「有 stale 且没走删行就清空」这个**兜底**形态，"
            "不得变成需要额外条件才进入"
        )


class TestDeletionLaneIsNowPositivelyAsserted:
    """**Validates: Requirement 12**（反向守卫 → 三条正向判据）

    spec: workpaper-sync-row-deletion-multi-region-propagation

    🔴 为什么是**替换**而不是**删除**：那条反向断言承载的是一个真实约束
    「删行不得在联动补齐之前启用」。约束的**前提**变了（联动已补齐），但「删行必须是
    完整联动下的删行」这件事没变。直接删掉等于把约束一起丢了；替换成正向判据才是把它
    从「禁止」升级成「要求」。
    """

    def test_deletion_plan_carries_both_declarations(self) -> None:
        """正向①：删行计划必带 `row_deletion` + `deletion_change` 两份声明。

        只有前者 ⇒ definedName 与跨 sheet 公式仍指旧行号；只有后者 ⇒ 物理行没删。
        """
        import ast
        import inspect
        import textwrap

        from app.services.workpaper_sync import excel_materialize

        tree = ast.parse(
            textwrap.dedent(inspect.getsource(excel_materialize.plan_managed_writes))
        )
        assigns = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", "") == "_plan_row_deletion"
        ]
        assert len(assigns) == 1, f"`_plan_row_deletion` 调用点应恰 1 处，实得 {len(assigns)}"
        targets = ast.unparse(assigns[0].targets[0])
        for name in ("row_deletion", "deletion_change", "stale_deleted"):
            assert name in targets, f"删行支没赋值 {name}：{targets}"

    def test_deletion_is_inside_the_contract_gate(self) -> None:
        """正向②：删行计划的产出落在契约门控 `deletes_physical_rows` 之内。

        判据取调用的**祖先条件链**（不是字符串 grep —— 那个名字在同一函数的注释里
        也出现过好几次）。
        """
        import ast
        import inspect
        import textwrap

        from app.services.workpaper_sync import excel_materialize

        tree = ast.parse(
            textwrap.dedent(inspect.getsource(excel_materialize.plan_managed_writes))
        )
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        target = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", "") == "_plan_row_deletion"
        )
        conditions: list[str] = []
        cursor: ast.AST | None = target
        while cursor is not None:
            parent = parents.get(cursor)
            if isinstance(parent, ast.If):
                conditions.append(ast.unparse(parent.test))
            cursor = parent
        assert any("deletes_physical_rows" in c for c in conditions), (
            f"删行不在契约门控之内 —— 祖先条件链实测 {conditions}"
        )
        assert any("stale_rows" in c for c in conditions), conditions

    def test_apply_runs_all_five_shift_actions_in_order(self) -> None:
        """正向③：apply 依次经过五个位移动作 —— 用**实测计数**，不用「没有抛错」。

        五个动作（现算于 `apply_plan_zip_with_report` 的删行支）：
        `shrink_sheet_rows`（物理删行）→ `_shift_managed_sheet_bare_refs`（A5 裸引用）
        → `_shift_managed_sheet_structures`（A8 结构块）→ `_shrink_managed_table_ref`
        （A1 本表 + 兄弟）→ `_apply_workbook_propagation`（A3/A4 工作簿级）
        → `_refresh_gt_sync_runtime_binding`（A2 冻结值）。

        🔴「没有抛错」不构成判据：这六个动作里任何一个被整行删掉，apply 都**不会**抛 ——
        产物只是少改了几处（症状要等到下一次物化或反读时才冒出来）。
        """
        import ast
        import inspect
        import textwrap

        from app.services.workpaper_sync import excel_materialize

        src = textwrap.dedent(
            inspect.getsource(excel_materialize.apply_plan_zip_with_report)
        )
        calls: list[tuple[int, str]] = []
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name:
                    calls.append((node.lineno, name))
        order = [name for _lineno, name in sorted(calls)]

        expected = [
            "shrink_sheet_rows",
            "_shift_managed_sheet_bare_refs",
            "_shift_managed_sheet_structures",
            "_shrink_managed_table_ref",
            "_apply_workbook_propagation",
            "_refresh_gt_sync_runtime_binding",
        ]
        positions = {}
        for name in expected:
            idx = [i for i, got in enumerate(order) if got == name]
            assert idx, f"删行支缺动作 `{name}` —— 实测调用序 {order}"
            positions[name] = idx[0]
        ordered = [positions[name] for name in expected]
        assert ordered == sorted(ordered), (
            f"六个动作的顺序变了：{ {k: positions[k] for k in expected} }。\n"
            "顺序是正确性的一部分：A5/A8 必须在 `shrink_sheet_rows` **之后**（它们要在"
            "已删行的行号上改写），传播与冻结值刷新必须在 Table ref 收缩之后。"
        )

    def test_shrink_sheet_rows_has_production_consumers(self) -> None:
        """🔴 现算 `shrink_sheet_rows` 的生产消费方数并断言 **> 0**。

        ⚠ 这里**故意不**写成「必须有生产消费方」那种原始形态的死代码守卫：现算它已有
        **2** 个生产调用点（`excel_materialize.apply_plan_zip_with_report` 与
        `excel_workbook_row_change.build_delete_plan` 一侧）⇒ 那种守卫恒真、是空转。
        改为「现算 > 0」并把实测数写进文案，让「哪天它退回零消费方」这件事可见，
        而不是立一条永远不会响的警报。
        """
        import ast
        from pathlib import Path

        root = Path(excel_materialize_root())
        hits: list[str] = []
        for path in root.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "id", None) or getattr(
                        node.func, "attr", None
                    )
                    if name == "shrink_sheet_rows":
                        hits.append(f"{path.name}:{node.lineno}")
        assert len(hits) > 0, (
            "`shrink_sheet_rows` 退回零生产消费方 ⇒ 删行能力又变成死代码"
        )
        assert len(hits) >= 2, (
            f"生产消费方从 2 个降到 {len(hits)} 个（实测 {hits}）—— "
            "本 spec 交付时是 2 个；减少说明某条链路被摘了"
        )


def excel_materialize_root() -> str:
    """`app/` 目录 —— 消费方普查的根（不硬编码绝对路径）。"""
    from pathlib import Path

    from app.services.workpaper_sync import excel_materialize

    return str(Path(excel_materialize.__file__).resolve().parents[2])

    def test_clearing_uses_blank_kind_not_empty_string(self) -> None:
        """🔴 清空必须用 `CellWriteKind.blank`（真空格），**不是**写空串。

        实测根因（500 从 7 个 extra 降到 1 个就卡在这里）：`inline_text` 对 `None` 与 `""`
        都渲染成 `<is><t xml:space="preserve"></t></is>` —— 一个「存在且值为空串」的格。
        extract 反读它得到 `""` ⇒ **cell 仍算有值** ⇒ 仍产 key ⇒ extra 消不掉。

        amount 字段当时「恰好」好了是巧合：`_render_number("")` 落成 `<v></v>` 空数值节点，
        openpyxl 读回 `None`。靠巧合不能作为判据，所以收敛对**所有** value_type 统一 blank。
        """
        import inspect

        from app.services.workpaper_sync import excel_materialize

        src = inspect.getsource(excel_materialize.plan_managed_writes)
        assert "kind=CellWriteKind.blank" in src, (
            "收敛清空不再用 blank kind —— text 字段会被写成「存在的空串格」，"
            "extract 反读仍算有值 ⇒ extra 消不掉（500 复发）"
        )
        assert '_write_kind_for(spec),\n                        value=""' not in src, (
            "收敛清空退回了「按 value_type 的 kind + 空串」—— 那正是失败形态"
        )

    def test_blank_kind_renders_a_truly_empty_cell(self) -> None:
        """blank 必须渲染成 `<c r=".." s=".."/>`：无 `t`、无 `<v>`、无 `<is>`，但**保留样式**。

        同时变异反证：`inline_text` 写 `None` **仍然**产出 `<is><t>` —— 证明两者不可互换，
        这条判据有真实区分力（不是在断言一个恒真的事）。
        """
        from app.services.workpaper_sync.excel_materialize import (
            CellWrite,
            CellWriteKind,
            _cell_xml,
        )

        blank = _cell_xml(
            coord="A22",
            style="42",
            write=CellWrite(
                coord="A22", kind=CellWriteKind.blank, value=None, stable_field_key=None
            ),
        )
        assert blank == '<c r="A22" s="42"/>', f"blank 渲染形态不对: {blank}"
        assert "<is>" not in blank and "<v>" not in blank and "t=" not in blank

        # 变异反证：同样传 None，inline_text 产出的是「存在的空串格」
        as_text = _cell_xml(
            coord="A22",
            style="42",
            write=CellWrite(
                coord="A22",
                kind=CellWriteKind.inline_text,
                value=None,
                stable_field_key=None,
            ),
        )
        assert "<is>" in as_text and 'xml:space="preserve"' in as_text, (
            "inline_text 对 None 不再产出空串格 —— 那 blank 与它就没有区别了，"
            "本条判据失去区分力（请复核 _cell_xml 是否被改过）"
        )
        assert as_text != blank, "blank 与 inline_text(None) 渲染相同 —— 清空语义丢失"

    def test_plan_carries_both_convergence_branches(self) -> None:
        """`MaterializePlan` 必须同时承载两个分支，且默认为空（不影响既有路径）。"""
        import dataclasses

        from app.services.workpaper_sync.excel_materialize import MaterializePlan

        names = {f.name: f for f in dataclasses.fields(MaterializePlan)}
        assert "stale_deleted" in names and "stale_cleared" in names
        for key in ("stale_deleted", "stale_cleared"):
            assert names[key].default == (), (
                f"{key} 默认值必须是空元组 —— 否则既有构造点行为被改变"
            )


class TestOverlayTableSegmentAgreement:
    """D：overlay 的 values 清理判据必须是**逐 table** 的，不是 row_keys 全集。

    spec workpaper-sync-managed-row-convergence F1。

    🔴 为什么必须逐 table：D4-1 有 main / other 两个受管区（uuid 列 W / X，
    区间 R8~R22 / R25~R36）。实测 substrate 的 **W22**（main 区末行）被写入了 other 段身份
    `xsheet-other-g5d43680692`，于是 extract 用 **main 表的 specs** 实例化它，产出
    `adjudication_main_rows/xsheet-other-g5d43680692/…`。该身份确实在
    `adjudication_other_rows` 的 row_keys 里 ⇒ **全集判据放它过** ⇒ 错位 key 进 intended
    ⇒ materialize 在 main 区找不到物理行 ⇒ `反读后缺少受管字段`（500）。

    且它是**自我强化**的：错位 key 进 intended ⇒ materialize 按 main 表把它当 orphan 插进
    main 区 ⇒ 下次 extract 又读出来。全集判据无法打破这个循环。
    """

    def test_overlay_filters_by_owning_table_not_global_set(self) -> None:
        """源码锁：清理必须按「身份在 row_keys 里的实际归属 table」判，而非全集。

        变异反证覆盖不到这条（本文件不复刻 overlay 的完整实现），故直接锁源码形态：
        有人把逐 table 判据「简化」回全集判据时立刻红。
        """
        import inspect

        from app.services.workpaper_sync import projection_first_publication as P

        src = inspect.getsource(P.overlay_store_on_baseline_projection)
        assert "owner_tables" in src, (
            "overlay 不再构建「身份 → 归属 table」映射 —— 清理退回 row_keys 全集判据，"
            "同 sheet 多受管区的错位 key 会被放过（D4-1 的 W22 形态）"
        )
        assert "_table_segment_agrees" in src, (
            "overlay 不再校验字段 key 的 table 段与身份归属一致 —— "
            "错位 key 会进 intended 并导致 materialize 反读缺失"
        )
        # 全集判据仍须保留（两条判据是**合取**，不是替换）
        assert "final_row_id_set" in src, (
            "overlay 丢掉了 row_keys 全集判据 —— 「身份完全不在任何 row_keys 里」的"
            "基线残留会被放过"
        )

    def test_table_segment_rule_semantics(self) -> None:
        """判据语义的独立复刻：table 段与归属不符即丢，归属未知则不表态。

        🔴 复刻而非调私有闭包：判据形态本身是被守护对象（见 B 组同款说明）。
        """
        owner_tables = {
            "xsheet-other-g5d43680692": {"adjudication_other_rows"},
            "xsheet-main-x": {"adjudication_main_rows"},
        }

        def agrees(key: str, row_key: str) -> bool:
            owners = owner_tables.get(row_key)
            if not owners:
                return True  # 归属未知 ⇒ 不表态
            segment = key.split("/", 1)[0]
            if segment == key:
                return True  # 无 table 段 ⇒ 不适用
            return segment in owners

        # 错位：other 身份挂 main 前缀 ⇒ 判否（会被丢弃）
        assert agrees(
            "adjudication_main_rows/xsheet-other-g5d43680692/label",
            "xsheet-other-g5d43680692",
        ) is False
        # 正位 ⇒ 判是
        assert agrees(
            "adjudication_other_rows/xsheet-other-g5d43680692/label",
            "xsheet-other-g5d43680692",
        ) is True
        # 归属未知 ⇒ 不表态（交给全集判据）
        assert agrees("some_table/unknown-ident/label", "unknown-ident") is True
        # 无 table 段（静态字段）⇒ 不适用
        assert agrees("d413_erp_check_fixed", "d413_erp_check_fixed") is True
