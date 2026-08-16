"""语义槽取数的三口径自检（`parent_check`）—— 跨循环共享纯函数。

**为什么需要三个口径而不是两个**（2026-08-03 H8 实测定论）

design 原本只要求「叶子和 vs 父科目行金额」，但真实数据暴露了第三个口径的必要性：

项目 `2aa00f57`（重庆和平药房）H8 使用权资产::

    tb_balance 叶子（1651.02）  = 176,203,072.87
    tb_balance 父行（1651）     = 176,203,072.87   ← 与叶子相等，勾稽通过
    trial_balance（1651）       = 352,406,145.74   ← **正好 2 倍**

即「叶子和 == 父额」这条勾稽**完全成立**，问题出在 `trial_balance` recalc 把
父科目 `1651` 与叶子 `1651.02` 各算了一遍（违反平台「recalc 只汇总叶子」铁律）。
只比对前两个口径**发现不了这个 1.76 亿的差异**。

故本模块同时下发三个数，三者互不相等时全部暴露，不静默取其一 ——
审计师据此判断是客户科目树被改动、数据集版本不一致，还是 recalc 双算。

**损益类循环（`occurrence=True`）**：余额口径无意义，改用 `debit`/`credit`
的正方向单侧值与 `trial_balance` 发生额对照。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/ Requirement 3.4
"""
from __future__ import annotations

from .leaf_aggregation import (
    CONVENTION_AS_STORED,
    CONVENTION_DIRECTIONAL,
    LeafRow,
    aggregate_leaves,
    leaf_signs,
    parent_totals,
    select_leaves,
    to_leaf_rows,
)
from .slot_trial_amounts import net_trial_for_slot, provision_standard_codes

#: 三口径互认容差（元）
TOLERANCE = 0.01


def _directional_leaf_sum(all_rows: list[LeafRow], codes, field: str = "closing") -> float:
    """按 :func:`leaf_aggregation.leaf_signs` 选定的符号约定聚合叶子。

    🔴 判据真源是 :func:`leaf_aggregation.resolve_leaf_totals`（`leaf_signs` 内部调它）
    —— 该函数选中「原样求和」约定时，本函数返回值与 :func:`aggregate_leaves` **逐分相等**
    （全部符号为 ``+1``）。故本函数只在存在**族内 contra 子科目**时才与裸求和不同。
    """
    total = 0.0
    for raw in codes or []:
        code = str(raw or "").strip()
        if not code:
            continue
        signs = leaf_signs(all_rows, code, field)
        if not signs:
            continue
        for row in all_rows:
            sign = signs.get(row.account_code)
            if sign is None:
                continue
            total += getattr(row, field, 0.0) * sign
    return total


def _trial_by_code(trial_rows, field: str = "unadjusted_amount") -> dict[str, float]:
    """`trial_balance` 行 → ``{标准码: 金额}``（同码累加）。"""
    out: dict[str, float] = {}
    for row in trial_rows or []:
        get = row.get if isinstance(row, dict) else (lambda k, _r=row: getattr(_r, k, None))
        code = str(get("standard_account_code") or "").strip()
        if not code:
            continue
        out[code] = out.get(code, 0.0) + float(get(field) or 0)
    return out


def build_parent_check(
    accounts,
    tb_rows,
    trial_rows,
    slot_keys,
    *,
    occurrence: bool = False,
) -> dict[str, dict[str, float]]:
    """构造各语义槽的三口径自检。纯函数（无 DB）。

    Args:
        accounts: :class:`SemanticAccountResult`。
        tb_rows: `tb_balance` **全量**行（叶子判定需看到全部兄弟行）。
        trial_rows: `trial_balance` 行。
        slot_keys: 要检查的槽键（通常 = ``X_SLOT_KEY_PREFIX`` 的键集）。
        occurrence: 损益类置 ``True`` —— 用发生额而非期末余额。

    Returns:
        ``{slot_key: {"leaf_sum", "parent", "trial_balance",
        "diff_parent", "diff_trial", "consistent"}}``。
        某槽 ``found=False`` 时**不产生该键**（宁缺勿造，与 `tb_values` 同口径）。
    """
    all_rows: list[LeafRow] = to_leaf_rows(tb_rows)
    leaves = select_leaves(all_rows)
    trial_map = _trial_by_code(trial_rows)

    # 🔴 trial 口径的备抵扣减走**共享件** `slot_trial_amounts`（与各循环 render 的
    #    `build_*_tb_values` 同一份判据，禁止两处各写一份 —— 详见该模块 docstring）。
    provision_std = provision_standard_codes(getattr(accounts, "slots", {}))

    out: dict[str, dict[str, float]] = {}
    for slot_key in slot_keys:
        slot = getattr(accounts, "slots", {}).get(slot_key)
        if slot is None or not slot.found:
            continue

        agg = aggregate_leaves(leaves, slot.codes)
        if occurrence:
            # 损益类：正方向单侧（贷方为主的取 credit，借方为主取 debit）
            # 两侧都给，由调用方按科目方向选；leaf_sum 取绝对值较大的一侧
            leaf_sum = agg["credit"] if abs(agg["credit"]) >= abs(agg["debit"]) else agg["debit"]
        else:
            leaf_sum = agg["closing"]

        # tb_balance 父科目行（多码时逐个取并求和）
        parent = 0.0
        for code in slot.codes:
            pt = parent_totals(all_rows, code)
            parent += (
                (pt["credit"] if abs(pt["credit"]) >= abs(pt["debit"]) else pt["debit"])
                if occurrence
                else pt["closing"]
            )

        # 🔴 族内 contra 子科目会让裸求和与父额不平（2026-08-06 H9 实测）：
        #    2651.01 租赁付款额 credit 98,176.48 + 2651.02 未确认融资费用 debit 3,956.64
        #    裸求和 102,133.12 vs 父额 94,219.84（差 2 × 3,956.64）。
        #    此处**只在裸求和不平时**才试方向约定，且仅当它能让勾稽成立才采用
        #    ⇒ 原本已平的调用方输出逐字不变（零回归）。
        convention = CONVENTION_AS_STORED
        if not occurrence and parent != 0.0 and abs(leaf_sum - parent) > TOLERANCE:
            alt = _directional_leaf_sum(all_rows, slot.codes, "closing")
            if abs(alt - parent) <= TOLERANCE:
                leaf_sum = alt
                convention = CONVENTION_DIRECTIONAL

        trial, trial_net_of = net_trial_for_slot(slot, trial_map, provision_std)

        diff_parent = leaf_sum - parent
        diff_trial = leaf_sum - trial
        out[slot_key] = {
            "leaf_sum": leaf_sum,
            "parent": parent,
            "trial_balance": trial,
            "diff_parent": diff_parent,
            "diff_trial": diff_trial,
            "convention": convention,
            # 审计追溯：本槽 trial 口径扣减了哪些备抵标准码（空数组 = 原样求和）
            "trial_net_of": trial_net_of,
            # 三口径一致（父行/trial 缺失时该侧不参与判定）
            "consistent": bool(
                (abs(diff_parent) <= TOLERANCE or parent == 0.0)
                and (abs(diff_trial) <= TOLERANCE or trial == 0.0)
            ),
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# `ReportLineAccounts` 适配层（报表行定位形态复用三口径自检）
# ─────────────────────────────────────────────────────────────────────────────

#: 报表行形态的两个槽键。
#:
#: 🔴 与 D 类 `d_tb_fetch.SLOT_GROSS` / `SLOT_PROVISION` **刻意同名** —— 前端共用件
#: 按槽键读 `parent_check`，两套形态用不同键名会让同一个面板要写两份分支。
SLOT_GROSS = "gross"
SLOT_PROVISION = "provision"

#: 报表行形态的槽键顺序（原值在前，与审定表展示顺序一致）
REPORT_LINE_SLOT_KEYS: tuple[str, ...] = (SLOT_GROSS, SLOT_PROVISION)


class _ReportLineSlotView:
    """把 :class:`ReportLineAccounts` 的一侧适配成 :func:`build_parent_check` 的槽形态。

    共享件只要求槽具备 ``found`` / ``codes`` / ``standard_codes`` / ``is_provision``
    四个属性 —— 与 D 类的 `d_tb_fetch._SlotView` 同一契约。

    ``is_provision`` **必须真实回填**：:func:`slot_trial_amounts.provision_standard_codes`
    靠它收集备抵码集，漏填会让原值槽的 `trial` 侧不做备抵扣减 ⇒ 备抵被记成原值子科目的
    循环（K1 的 `1231.03`）三口径恒不平。
    """

    __slots__ = ("_codes", "_std", "_is_provision")

    def __init__(self, codes, standard_codes, *, is_provision: bool) -> None:
        self._codes = [s for c in (codes or []) if (s := str(c or "").strip())]
        self._std = [s for c in (standard_codes or []) if (s := str(c or "").strip())]
        self._is_provision = bool(is_provision)

    @property
    def found(self) -> bool:
        """无可查前缀 ⇒ 不参与三口径（共享件据此**不产生该键**，三态语义）。"""
        return bool(self._codes)

    @property
    def codes(self) -> list[str]:
        return list(self._codes)

    @property
    def standard_codes(self) -> list[str]:
        return list(self._std)

    @property
    def is_provision(self) -> bool:
        return self._is_provision


class _ReportLineAccountsView:
    """``accounts.slots[key]`` 形态的最小适配（共享件只访问 ``.slots``）。"""

    __slots__ = ("slots",)

    def __init__(self, accounts) -> None:
        self.slots = {
            SLOT_GROSS: _ReportLineSlotView(
                getattr(accounts, "gross", None),
                getattr(accounts, "gross_standard", None),
                is_provision=False,
            ),
            SLOT_PROVISION: _ReportLineSlotView(
                getattr(accounts, "provision", None),
                getattr(accounts, "provision_standard", None),
                is_provision=True,
            ),
        }


def build_report_line_parent_check(
    accounts,
    tb_rows,
    trial_rows,
    *,
    occurrence: bool = False,
) -> dict[str, dict]:
    """:class:`ReportLineAccounts` 形态的三口径自检 —— 委托 :func:`build_parent_check`。

    **为什么要这个适配层而不是各循环自己写**（2026-08-12 实测）

    共享件的 ``accounts`` 形参期望 :class:`SemanticAccountResult`（带 ``.slots``），
    而走「报表行定位」的循环（K 类全部）拿到的是 :class:`ReportLineAccounts`（扁平
    ``gross`` / ``provision``）。K3/K5/K7 各自抄了一份**只有两口径**的本地
    ``build_parent_check``（缺 ``trial_balance`` 侧），三份逐字不同且都漏掉了共享件
    存在的全部理由 —— H8 实测的 `trial_balance` 父子双算（1.76 亿）**只比对前两个
    口径根本发现不了**（叶子和 == 父额完全成立）。

    本轮实证复现了同一形态：K1 在某项目上 ``leaf_sum = 88,596,839.09`` 而
    ``trial_balance = 258,028,708.86``，``leaf == parent`` 成立 ⇒ 本地两口径版恒报
    「勾稽通过」，第三个口径才暴露 1.69 亿差异。

    Args:
        accounts: :class:`ReportLineAccounts`（只读 ``gross`` / ``provision`` /
            ``gross_standard`` / ``provision_standard`` / ``provision_exact``）。
        tb_rows: `tb_balance` **全量**行（含父科目行 —— 父行是 ``parent`` 口径的
            取值来源，预先筛叶子会让 ``parent`` 恒 0、该侧静默退出判定）。
        trial_rows: `trial_balance` 行（:func:`tb_query.fetch_trial_balance_rows`）。
        occurrence: 损益类置 ``True``（用发生额而非期末余额）。

    Returns:
        ``{槽键: 三口径 dict}``；某侧无科目时**不产生该键**。备抵侧反解退化为宽前缀时
        追加 ``wide_prefix_scope=True``。

    Note:
        **``wide_prefix_scope`` 的必要性**：``provision_exact=False`` 时备抵前缀是宽
        口径（K1 的 `1231-03` 退化成 `1231`），而 `1231` 下 `-01/-02/-03/-05` 分属
        D1/D2/K1/长期应收 —— 此时三口径覆盖的是**整个前缀族**，``consistent=True``
        只说明「1231 全族自洽」，**不**说明本循环备抵已勾稽。不标这个位，审计师会把
        宽口径自洽误读成本循环勾稽通过（各循环 `tb_values` 侧另有名称过滤，口径更窄）。
    """
    out = build_parent_check(
        _ReportLineAccountsView(accounts),
        tb_rows,
        trial_rows,
        REPORT_LINE_SLOT_KEYS,
        occurrence=occurrence,
    )
    if SLOT_PROVISION in out and not bool(getattr(accounts, "provision_exact", False)):
        out[SLOT_PROVISION]["wide_prefix_scope"] = True
    return out


__all__ = [
    "REPORT_LINE_SLOT_KEYS",
    "SLOT_GROSS",
    "SLOT_PROVISION",
    "TOLERANCE",
    "build_parent_check",
    "build_report_line_parent_check",
]
