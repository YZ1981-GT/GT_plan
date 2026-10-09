# -*- coding: utf-8 -*-
"""受保护单元格（`read_only_masked_cell`）判定必须是**格级**，不是整列。

spec: d4-html-to-oo-store-contract-alignment · 真栈②覆盖往返（需求 1.5 / 6.2）

═══ 被修复的缺陷 ═══

`merge.ContractIndex._protection` 的第三类判定原本写成::

    column_in_ranges(spec.cell.column, template.formula_mask)

`contracts.column_in_ranges` 的语义是「列是否落在任一 A1 区域的**列跨度**内」——
它**不看行**。对 mask 恰好覆盖整个数据区的底稿（D2 `Q13:Q25`、D6/D7 同形）列判定
等价于格判定，没问题；但对**逐格声明**的 mask 就会把数据区之外那几行（小计 / 合计 /
差异 / 别的区域）的列整列带进来。

真栈实测（2026-09-24，D4-1 审定表）：OO 里改派生行金额 → forcesave → callback 到达 →
extract → merge，最后被判 `conflict_kind='protected'` /
`protection_policy='read_only_masked_cell'` 挡在 store 之外，`stored` 永不改变。
于是**需求 1.5（OO 改动 SHALL 生效并成为权威值）在后端完全不可达**，需求 6.2 的
S2/S4（都以 `stored ≠ snap` 为前提）永不出现，Task 15 已实现的四态 UI 成了死代码。

═══ 全仓盘点（修复前实测，一次性脚本已删）═══

遍历 `DELIVERED_PER_ENTRY_CONTRACTS` 全部 10 个 entry 的真实契约：

* **9 个非 D4 entry 误伤 = 0** —— 它们的 mask 都是 `{col}{FIRST}:{col}{LAST}` 形态，
  与 editable 字段的列不相交 ⇒ 本次收紧对它们**零影响**；
* 误伤全部集中在 D4 这一个 entry 的 9 张表、**311 个字段**：
  其中**静态格 286 个「该格其实不在 mask 里」（0 个例外）**，动态行 25 个的同列 mask 格
  全部落在数据区之外（D4-1 小计行 B12../B18..、D4-9 合计行 `C23:F23`/`C37:F37`、
  d4_7_products 合计行 B26..O26、D4-14 的 G37/G39/X37/AF37 而首数据行是 15）。

⇒ 当前的列判定**没有保护任何一个真该保护的 editable 格**，它的全部效果就是那 311 个误伤。

═══ 收紧后的语义 ═══

* **静态格字段**（`cell.row_from == "static"`，带 `static_row`）⇒ 做**精确格级**判定：
  只有 `(column, static_row)` 真的落在某个 mask 区间内才只读。这比原来更严格也更准。
* **动态行字段**（`cell.row_from == "row_identity"`）⇒ 不再用 mask 推翻字段自己的 `mode`。
  理由是结构性的：Requirement 6.5 **强制**行域字段不得写死行号，行号运行时才定；而契约里
  mask 的行号是**模板坐标**，materialize 插行之后它已经指向别的行（D4-1 实测：模板小计行 12
  在插入 7 行后移到 19，而 12 变成了数据行）。拿一个已经失效的坐标去否决 `editable` 声明，
  只会误伤。真正整列是公式的动态行字段，CS-13 要求它声明 `mode=formula`，走第一类判定。
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any

import pytest

from app.services.workpaper_sync import merge as M
from app.services.workpaper_sync.adapters.registry import DELIVERED_PER_ENTRY_CONTRACTS
from app.services.workpaper_sync.conflicts import ProtectionPolicy
from app.services.workpaper_sync.contracts import FieldMode

_D4_ENTRY = "xlsx/gt-d4-operating-revenue"
_LOADERS = ("load_pilot_contract", "load_contract", "load_entry_contract")
_BUILDERS = ("build_contract_payload", "contract_payload")


@lru_cache(maxsize=None)
def _contract_for(module_path: str) -> Any:
    """按 provider 模块加载**真实已交付契约**（不构造替身 —— 替身测不出真 mask 形态）。

    各 provider 的入口名与签名不统一（有的 `load_pilot_contract()` 无参，有的
    `load_contract(adapter_id)` 要参），所以逐个试并吞掉签名不匹配的候选；
    全部试完仍拿不到才 `pytest.fail`（**不能** skip —— 静默跳过等于判据空转）。
    """
    module = importlib.import_module(module_path)
    attempts: list[str] = []
    for name in _LOADERS:
        fn = getattr(module, name, None)
        if not callable(fn):
            continue
        try:
            return fn()
        except TypeError as exc:  # 签名不匹配（如需要 adapter_id）
            attempts.append(f"{name}: {exc}")
    for name in _BUILDERS:
        fn = getattr(module, name, None)
        if not callable(fn):
            continue
        try:
            from app.services.workpaper_sync.contracts import parse_contract

            return parse_contract(fn())
        except TypeError as exc:
            attempts.append(f"{name}: {exc}")
    pytest.fail(
        f"{module_path}: 找不到可用的契约 loader/builder，判据会空转。尝试过：{attempts}"
    )


def _entries() -> list[tuple[str, str]]:
    return [
        (str(row["entry_id"]), str(row["provider_module"]))
        for row in DELIVERED_PER_ENTRY_CONTRACTS
    ]


def _masked_editable_fields(contract: Any) -> list[tuple[str, str, str]]:
    """返回被判 `read_only_masked_cell` 的 **editable** 字段 `(sheet, table, stable_key)`。

    走 `ContractIndex._protection` 真入口（不重算一份判定逻辑 —— 抄第二份会让判据
    在实现改动时静默失效）。
    """
    index = M.ContractIndex(contract)
    out: list[tuple[str, str, str]] = []
    for template in index._templates:  # noqa: SLF001 — 判据要的就是逐 template 的判定
        spec = template.spec
        if spec.mode is not FieldMode.editable:
            continue
        if index._protection(template) is ProtectionPolicy.read_only_masked_cell:  # noqa: SLF001
            out.append(
                (
                    str(template.sheet_key),
                    str(template.table_key),
                    str(spec.stable_field_key),
                )
            )
    return out


class TestD41AmountFieldsAreWritable:
    """D4-1 六个金额字段声明 `editable`，就不得被 mask 判成只读（需求 1.5 的后端前提）。"""

    def test_d41_amount_fields_are_not_masked(self) -> None:
        contract = _contract_for(
            "app.services.workpaper_sync.phase5_d4_revenue_detail"
        )
        masked = [
            key.rsplit("/", 1)[-1]
            for _sheet, table, key in _masked_editable_fields(contract)
            if table in ("adjudication_main_rows", "adjudication_other_rows")
        ]
        assert masked == [], (
            "D4-1 审定表的金额字段在契约里全部声明 `editable`（provider 注释：受管数据行 "
            "B/C/D/F/G/H 绝不入 mask），却被判成 read_only_masked_cell ⇒ OO 侧改动会被"
            f"当 protected conflict 挡住、`stored` 永不改变，需求 1.5 不可达。"
            f"被误判 {len(masked)} 个：{sorted(set(masked))}"
        )

    def test_d41_audited_amount_columns_stay_protected(self) -> None:
        """反面：E/I 审定数（`=SUM` 内部公式）**不在契约字段里**，本判据不该把它们放出来。

        这条是防「修过头」—— 如果哪天有人把 E/I 补进契约且声明 editable，
        它们的格确实落在 mask 里（`E{r}` / `I{r}` 逐格声明），格级判定必须仍然拦住。
        """
        contract = _contract_for(
            "app.services.workpaper_sync.phase5_d4_revenue_detail"
        )
        for sheet in contract.sheets:
            for table in sheet.tables:
                if table.table_key not in ("adjudication_main_rows", "adjudication_other_rows"):
                    continue
                cols = {
                    spec.cell.column
                    for spec in table.fields
                    if spec.cell is not None
                }
                assert "E" not in cols and "I" not in cols, (
                    "E/I 审定数已进契约字段 —— 请同时确认格级 mask 判定仍拦得住它们"
                )


class TestNonD4EntriesAreUnaffected:
    """不变式：9 个非 D4 entry 的保护判定**一个字段都不许变**。

    修复前实测它们的「被 mask 误判的 editable 字段」= 0，所以收紧判定对它们必须零影响。
    这条同时也是「改动没把别的底稿的真公式格放开」的守卫。
    """

    @pytest.mark.parametrize(
        ("entry_id", "module_path"),
        [(e, m) for e, m in _entries() if e != _D4_ENTRY],
    )
    def test_no_masked_editable_fields(self, entry_id: str, module_path: str) -> None:
        contract = _contract_for(module_path)
        masked = _masked_editable_fields(contract)
        assert masked == [], (
            f"{entry_id} 出现了被 mask 判只读的 editable 字段 —— 修复前它是 0，"
            f"说明本次收紧改变了这个 entry 的行为：{masked}"
        )

    @pytest.mark.parametrize(
        ("entry_id", "module_path"),
        [(e, m) for e, m in _entries() if e != _D4_ENTRY],
    )
    def test_formula_fields_still_read_only(self, entry_id: str, module_path: str) -> None:
        """`mode=formula` 的字段走第一类判定，与 mask 收紧无关，必须仍然只读。"""
        contract = _contract_for(module_path)
        index = M.ContractIndex(contract)
        checked = 0
        for template in index._templates:  # noqa: SLF001
            if template.spec.mode is not FieldMode.formula:
                continue
            checked += 1
            assert (
                index._protection(template) is ProtectionPolicy.read_only_formula  # noqa: SLF001
            ), f"{entry_id}: formula 字段 {template.spec.stable_field_key} 不再只读"
        if checked == 0:
            pytest.skip(f"{entry_id} 没有 formula 模式字段")


class TestWholeRepoHasNoMaskedEditableField:
    """全仓收口：**动态**遍历所有已交付 entry，被 mask 判只读的 editable 字段必须为 0。

    刻意不硬编码「311」这个修复前的数字 —— 硬编码会在新增受管区时静默漏掉新的误伤。
    """

    def test_no_entry_has_masked_editable_fields(self) -> None:
        offenders: dict[str, list[str]] = {}
        for entry_id, module_path in _entries():
            masked = _masked_editable_fields(_contract_for(module_path))
            if masked:
                offenders[entry_id] = [f"{t}/{k}" for _s, t, k in masked]
        # 失败消息只抽样 —— 修复前这里有 311 条，全量铺屏会把真正有用的信息冲掉。
        summary = {
            entry: f"{len(keys)} 个，例：{keys[:6]}" for entry, keys in offenders.items()
        }
        assert offenders == {}, (
            "仍有 editable 字段被 formula_mask 判成只读。若这些字段确实该只读，"
            "应当在契约里把它们声明成 `mode=formula`（CS-13 会校验其列已被 mask 覆盖），"
            f"而不是靠 mask 的列跨度去否决 editable 声明。共 "
            f"{sum(len(v) for v in offenders.values())} 个：{summary}"
        )


try:  # 收紧判定所需的新纯函数；未实现时让下面两个 class 跳过而不掩盖上面的判据
    from app.services.workpaper_sync.contracts import cell_in_ranges as _cell_in_ranges
except ImportError:  # pragma: no cover — 实现落地后这一支不再走到
    _cell_in_ranges = None  # type: ignore[assignment]

_needs_cell_in_ranges = pytest.mark.skipif(
    _cell_in_ranges is None,
    reason="contracts.cell_in_ranges 尚未实现（格级 mask 判定的纯函数）",
)


@_needs_cell_in_ranges
class TestCellInRanges:
    """格级判定纯函数：必须同时看列**和**行。"""

    def test_single_cell_hit_and_miss(self) -> None:
        mask = ("B12", "E8", "I8")
        assert _cell_in_ranges("B", 12, mask) is True
        # 同列不同行 —— 这正是整列判定错掉的地方
        assert _cell_in_ranges("B", 9, mask) is False
        assert _cell_in_ranges("E", 8, mask) is True
        assert _cell_in_ranges("E", 9, mask) is False

    def test_multi_column_range(self) -> None:
        """跨列区间（D4-9 的 `C23:F23`）：列在跨度内且行相等才算命中。"""
        mask = ("C23:F23",)
        for col in ("C", "D", "E", "F"):
            assert _cell_in_ranges(col, 23, mask) is True, col
            assert _cell_in_ranges(col, 22, mask) is False, col
        assert _cell_in_ranges("B", 23, mask) is False
        assert _cell_in_ranges("G", 23, mask) is False

    def test_multi_row_range(self) -> None:
        """跨行区间（D2 的 `Q13:Q25`）：行在跨度内才算命中。"""
        mask = ("Q13:Q25",)
        assert _cell_in_ranges("Q", 13, mask) is True
        assert _cell_in_ranges("Q", 19, mask) is True
        assert _cell_in_ranges("Q", 25, mask) is True
        assert _cell_in_ranges("Q", 12, mask) is False
        assert _cell_in_ranges("Q", 26, mask) is False
        assert _cell_in_ranges("P", 19, mask) is False

    def test_empty_mask(self) -> None:
        assert _cell_in_ranges("A", 1, ()) is False

    def test_multi_letter_column(self) -> None:
        """D4-14 用到 `AF37` 这类双字母列，不能按字符序比较。"""
        mask = ("AF37",)
        assert _cell_in_ranges("AF", 37, mask) is True
        assert _cell_in_ranges("AF", 38, mask) is False
        assert _cell_in_ranges("F", 37, mask) is False
        assert _cell_in_ranges("Z", 37, mask) is False


@_needs_cell_in_ranges
class TestStaticCellTrulyInMaskStaysProtected:
    """防修过头：静态格**真的**落在 mask 里时，必须仍判 `read_only_masked_cell`。

    真实契约里这种字段一个都没有（286 个静态格误伤全部是「该格其实不在 mask 里」），
    所以只能构造 payload 来钉住它 —— 否则收紧之后「受保护单元格」这一类会永不被测到，
    正是原实现 docstring 担心的那种假绿。
    """

    @staticmethod
    def _index_for(mask: list[str], static_row: int) -> tuple[Any, Any]:
        from app.services.workpaper_sync.contracts import parse_a1_range  # noqa: F401

        spec = type(
            "Spec",
            (),
            {
                "mode": FieldMode.editable,
                "stable_field_key": "t/probe",
                "cell": type(
                    "Cell",
                    (),
                    {"column": "B", "row_from": "static", "static_row": static_row},
                )(),
            },
        )()
        template = M._FieldTemplate(  # noqa: SLF001
            spec=spec,
            sheet_key="s",
            sheet_excel_name="S",
            table_key="t",
            formula_mask=tuple(mask),
        )
        return template, M.ContractIndex._protection(template)  # noqa: SLF001

    def test_static_cell_inside_mask_is_protected(self) -> None:
        _t, policy = self._index_for(["B12", "C12"], static_row=12)
        assert policy is ProtectionPolicy.read_only_masked_cell, (
            "静态格 B12 真的在 mask 里却被放开 —— 收紧改过头了，真公式格会被 OO 覆盖"
        )

    def test_static_cell_outside_mask_is_editable(self) -> None:
        _t, policy = self._index_for(["B12", "C12"], static_row=9)
        assert policy is ProtectionPolicy.editable, (
            "静态格 B9 不在 mask 里（只有同列的 B12 在），不该被判只读"
        )

    def test_static_cell_inside_multi_row_range_is_protected(self) -> None:
        _t, policy = self._index_for(["B10:B20"], static_row=15)
        assert policy is ProtectionPolicy.read_only_masked_cell


@_needs_cell_in_ranges
class TestDynamicRowWholeColumnMaskStaysProtected:
    """动态行字段：mask 用**多行区间**把整列数据区声明只读（如 G7 `K8:K200`）时仍受保护。

    这条守住 `test_task14` 的 `masked_note`（K 列 `K8:K200`，首数据行 9）——
    它是「editable 但整列受保护」的合法形态，收紧判定不得把它放开；同时又不能把 D4-1 的
    `B12`（单格模板小计行坐标）判成保护。两者的区别是「多行区间且覆盖首数据行」。
    """

    @staticmethod
    def _protection(mask: list[str], first_data_row: int) -> Any:
        spec = type(
            "Spec",
            (),
            {
                "mode": FieldMode.editable,
                "stable_field_key": "t/{row_uuid}/probe",
                "cell": type(
                    "Cell",
                    (),
                    {"column": "K", "row_from": "row_identity", "static_row": None},
                )(),
            },
        )()
        template = M._FieldTemplate(  # noqa: SLF001
            spec=spec,
            sheet_key="s",
            sheet_excel_name="S",
            table_key="t",
            formula_mask=tuple(mask),
            first_data_row=first_data_row,
        )
        return M.ContractIndex._protection(template)  # noqa: SLF001

    def test_whole_column_data_region_mask_protects_dynamic_row(self) -> None:
        # G7 masked_note 的真实形态：K8:K200，首数据行 9
        assert (
            self._protection(["I8:I200", "K8:K200"], first_data_row=9)
            is ProtectionPolicy.read_only_masked_cell
        )

    def test_single_cell_template_row_mask_does_not_protect_dynamic_row(self) -> None:
        # D4-1 main 的真实形态：B12 单格（模板小计行），首数据行 9 ⇒ 不保护
        assert (
            self._protection(["B12"], first_data_row=9) is ProtectionPolicy.editable
        )

    def test_single_row_footer_mask_does_not_protect_dynamic_row(self) -> None:
        # D4-9 的真实形态：C23:F23 单行合计行（此处取 K 列不命中列，改用覆盖 K 的单行）
        assert (
            self._protection(["J23:M23"], first_data_row=13)
            is ProtectionPolicy.editable
        )

    def test_multi_row_range_not_covering_first_data_row_does_not_protect(self) -> None:
        # 多行区间但落在数据区之外（如 mask 到了下一个 section）⇒ 不保护
        assert (
            self._protection(["K30:K40"], first_data_row=9)
            is ProtectionPolicy.editable
        )
