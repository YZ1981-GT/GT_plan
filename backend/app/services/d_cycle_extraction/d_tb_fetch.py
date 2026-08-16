"""D 循环四表取数编排 —— 只串联共享件，不重造查询与聚合。

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.4~1.8, 2.1, 2.3, 2.4, 3.1~3.3, 3.6

为什么本模块几乎没有算法
------------------------
2026-08-05 逐个 ``inspect.signature`` 实证：平台的四表取数工具链**已经完备**::

    resolve_report_line_accounts / resolve_semantic_accounts  科目定位
    tb_query.fetch_tb_subtree            宽取子树含父行 + get_active_filter 四参 + fail-open
    tb_query.fetch_trial_balance_rows    trial_balance 行（本 spec 新增的共享件）
    leaf_aggregation.resolve_leaf_totals 双符号约定各算一遍，取与父额勾稽成立的那种
    parent_check.build_parent_check      三口径（叶子和 / 父行 / trial_balance）
    d_provision_filter.filter_provision_codes  备抵名称过滤（本 spec 新增）

故本模块的职责只有三件：**串联**、**把备抵过滤插进「反解 → 查库」之间**、
**把结果整理成四态载荷**。任何看起来像「自己写聚合」的代码都是重复造轮子。

四态（为什么不是三态）
----------------------
``resolve_report_line_accounts`` 在 ``account_mapping`` 反解不到时会**保留标准码**
（横杠体系 ``1231-04``），而 ``tb_balance`` 是点号体系 ⇒ ``LIKE '1231-04%'`` 必然
命中 0 行。实证 ``1231-04``（预付账款坏账）与 ``1231-05``（合同资产坏账）在
``account_mapping`` 中**零反解**，D6 备抵走的正是这条路：结果恰好正确（该备抵全库
确实无数据）但机理是「碰巧对」—— 一旦某项目真有数据就会静默取空。

故必须把「前缀体系不匹配」单独成态::

    态 1   found=False                              本项目无此科目          amount=None
    态 2a  found + rows=0 + query_codes 含横杠      反解失败，前缀对不上    amount=None + prefix_mismatch
    态 2b  found + rows=0 + 无横杠                  科目表有但四表无数据    amount=None
    态 3   found + rows>0 + 聚合为 0                余额确实为 0            amount=0.0
    态 4   载荷中无该槽键                            未取数（灰度关等）

态 2a 必须以 ``warning`` 级提示，**不得**显示成「无数据」。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.services.four_table.d_provision_filter import (
    FilterResult,
    filter_provision_codes,
)
from app.services.four_table.leaf_aggregation import (
    LeafRow,
    filter_by_prefixes,
    resolve_leaf_totals,
    sql_prefixes_for_specs,
)
from app.services.four_table.parent_check import build_parent_check
from app.services.four_table.tb_query import (
    fetch_tb_subtree,
    fetch_trial_balance_amounts,
    fetch_trial_balance_rows,
)

logger = logging.getLogger(__name__)

#: 槽键
SLOT_GROSS = "gross"
SLOT_PROVISION = "provision"
SLOT_KEYS = (SLOT_GROSS, SLOT_PROVISION)

#: 标准码的分隔符 —— 出现在 `query_codes` 里说明反解失败（`tb_balance` 用点号）
_STANDARD_CODE_SEP = "-"


@dataclass(frozen=True)
class SlotAmounts:
    """单个槽的取数结果（四态由 `found` / `tb_rows_count` / `amount` 联合表达）。

    Attributes:
        key: 槽键（``gross`` / ``provision``）。
        found: 科目定位是否有落点（码集非空）。
        query_codes: 实际用于查 `tb_balance` 的前缀（已过名称过滤）。
        tb_rows_count: 这些前缀在 `tb_balance` 的命中行数（含父行）。
        prefix_mismatch: 反解失败导致前缀体系不匹配（态 2a），须 warning 级提示。
        opening / closing: 期初 / 期末（``None`` = 无数据，区别于 ``0.0``）。
        debit / credit: 借贷发生额（损益类用）。
        convention: `resolve_leaf_totals` 判定的符号约定（溯源展示）。
        parent_diff: 叶子和与父额的差（``None`` = 无父行可比）。
        dropped / warnings: 名称过滤的剔除与待确认记录。
        filter_applied: 名称过滤是否真的执行过（关键词为空则为 False）。
    """

    key: str
    found: bool = False
    query_codes: tuple[str, ...] = ()
    tb_rows_count: int = 0
    prefix_mismatch: bool = False
    opening: float | None = None
    closing: float | None = None
    debit: float | None = None
    credit: float | None = None
    convention: dict = field(default_factory=dict)
    parent_diff: float | None = None
    dropped: tuple[dict, ...] = ()
    warnings: tuple[dict, ...] = ()
    filter_applied: bool = False

    @property
    def state(self) -> str:
        """四态的可读标识（供前端与守卫断言，避免各处重复推导）。"""
        if not self.found:
            return "no_account"          # 态 1
        if self.tb_rows_count == 0:
            return "prefix_mismatch" if self.prefix_mismatch else "no_data"  # 态 2a / 2b
        return "ok"                      # 态 3（含余额为 0）

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "found": self.found,
            "state": self.state,
            "query_codes": list(self.query_codes),
            "tb_rows_count": self.tb_rows_count,
            "prefix_mismatch": self.prefix_mismatch,
            "opening": self.opening,
            "closing": self.closing,
            "debit": self.debit,
            "credit": self.credit,
            "convention": dict(self.convention or {}),
            "parent_diff": self.parent_diff,
            "dropped": [dict(d) for d in self.dropped],
            "warnings": [dict(w) for w in self.warnings],
            "filter_applied": self.filter_applied,
        }


@dataclass(frozen=True)
class DCycleTbData:
    """一个 D 循环的完整取数结果。"""

    wp_code: str = ""
    slots: dict[str, SlotAmounts] = field(default_factory=dict)
    parent_check: dict = field(default_factory=dict)
    tb_rows: tuple[LeafRow, ...] = ()
    trial_rows: tuple = ()
    ok: bool = True
    error: str | None = None

    def amount_of(self, slot_key: str) -> float | None:
        """某槽期末金额；无该槽或无数据返回 ``None``（**不是 0**）。"""
        slot = self.slots.get(slot_key)
        return slot.closing if slot else None


def _has_standard_sep(codes) -> bool:
    """码集中是否存在含横杠的码（= `account_mapping` 反解失败保留了标准码）。"""
    return any(_STANDARD_CODE_SEP in str(c or "") for c in codes or ())


def _count_rows(rows: list[LeafRow], prefixes) -> int:
    """这些前缀在行集中的命中行数（含父行）。"""
    if not prefixes:
        return 0
    return len(filter_by_prefixes(rows, list(prefixes)))


def _sum_slot(
    rows: list[LeafRow], prefixes, *, absolute: bool
) -> tuple[dict, dict, float | None]:
    """逐前缀 `resolve_leaf_totals` 并求和。

    🔴 **不得先 `select_leaves`** —— 父科目行是符号约定的判定依据，预先筛掉父行会让
    「取与父额勾稽成立的那种约定」永久失效（见 `resolve_leaf_totals` docstring）。

    每个科目族各自判自己的符号约定，故多前缀时逐个调用再加总，而不是合并成一次。

    Returns:
        ``(totals, convention, parent_diff)``；无有效前缀时 totals 各项为 ``None``。
    """
    if not prefixes:
        return {"opening": None, "closing": None, "debit": None, "credit": None}, {}, None

    acc = {"opening": 0.0, "closing": 0.0, "debit": 0.0, "credit": 0.0}
    convention: dict = {}
    parent_diff: float | None = None
    hit = False
    for prefix in prefixes:
        totals = resolve_leaf_totals(rows, str(prefix), absolute=absolute)
        if not totals.leaf_codes:
            continue
        hit = True
        acc["opening"] += totals.opening
        acc["closing"] += totals.closing
        acc["debit"] += totals.debit
        acc["credit"] += totals.credit
        convention[str(prefix)] = dict(totals.convention or {})
        d = (totals.diff or {}).get("closing")
        if d is not None:
            parent_diff = (parent_diff or 0.0) + float(d)

    if not hit:
        return {"opening": None, "closing": None, "debit": None, "credit": None}, {}, None
    return acc, convention, parent_diff


def _build_slot(
    key: str,
    raw_codes,
    rows: list[LeafRow],
    *,
    subject_keywords: tuple[str, ...],
    absolute: bool,
) -> SlotAmounts:
    """构造单个槽的取数结果（含名称过滤与四态判定）。"""
    codes = [str(c or "").strip() for c in (raw_codes or []) if str(c or "").strip()]
    if not codes:
        return SlotAmounts(key=key, found=False)

    # 名称过滤 —— **无条件**叠加（不以 use_provision_name_filter 为门）。
    # name_by_code 只覆盖**顶层反解码**：子科目名未必含主体关键词
    # （如 `1231.02.01 某客户`），按数据行层面过滤会误剔真实备抵。
    name_by_code = {
        r.account_code: r.account_name for r in rows if r.account_code in set(codes)
    }
    fr: FilterResult = filter_provision_codes(codes, name_by_code, subject_keywords)
    kept = fr.kept

    if not kept:
        # 过滤把该槽剔空 —— 仍算 found（科目表有落点），但无可查前缀
        return SlotAmounts(
            key=key,
            found=True,
            query_codes=(),
            tb_rows_count=0,
            prefix_mismatch=False,
            dropped=tuple(fr.dropped_dicts),
            warnings=tuple(fr.warning_dicts),
            filter_applied=fr.applied,
        )

    rows_count = _count_rows(rows, kept)
    totals, convention, parent_diff = _sum_slot(rows, kept, absolute=absolute)
    return SlotAmounts(
        key=key,
        found=True,
        query_codes=tuple(kept),
        tb_rows_count=rows_count,
        # 态 2a：查不到数据 且 前缀里还带着标准码的横杠 ⇒ 反解失败
        prefix_mismatch=bool(rows_count == 0 and _has_standard_sep(kept)),
        opening=totals["opening"],
        closing=totals["closing"],
        debit=totals["debit"],
        credit=totals["credit"],
        convention=convention,
        parent_diff=parent_diff,
        dropped=tuple(fr.dropped_dicts),
        warnings=tuple(fr.warning_dicts),
        filter_applied=fr.applied,
    )


async def fetch_d_cycle_tb(ctx, codes, *, occurrence: bool = False) -> DCycleTbData:
    """按已解析的科目码取 D 循环四表数据（全程 fail-open）。

    Args:
        ctx: `RenderContext`（需 ``db`` / ``project_id`` / ``year``）。
        codes: :class:`DCycleAccountCodes` 或 ``D1AccountCodes``（两者字段同构）。
        occurrence: 损益类置 ``True``（`parent_check` 用发生额口径）。

    Returns:
        :class:`DCycleTbData`；任一环失败返回 ``ok=False`` 且 slots 尽可能填充。
    """
    wp_code = str(getattr(codes, "wp_code", "") or "")
    gross_codes = list(getattr(codes, "gross", None) or [])
    provision_codes = list(getattr(codes, "provision", None) or [])
    subject_keywords = tuple(getattr(codes, "subject_keywords", ()) or ())

    all_prefixes = sorted({*gross_codes, *provision_codes})
    if not all_prefixes:
        return DCycleTbData(
            wp_code=wp_code,
            slots={
                SLOT_GROSS: SlotAmounts(key=SLOT_GROSS, found=False),
                SLOT_PROVISION: SlotAmounts(key=SLOT_PROVISION, found=False),
            },
        )

    try:
        rows = await fetch_tb_subtree(ctx.db, ctx.project_id, ctx.year, all_prefixes)
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning(
            "D 循环取数[%s] 阶段=fetch_tb_subtree 失败（fail-open）: %s", wp_code, e
        )
        return DCycleTbData(wp_code=wp_code, ok=False, error=str(e))

    slots = {
        SLOT_GROSS: _build_slot(
            SLOT_GROSS, gross_codes, rows,
            # 原值侧不做主体关键词过滤（关键词是备抵专用）
            subject_keywords=(), absolute=False,
        ),
        SLOT_PROVISION: _build_slot(
            SLOT_PROVISION, provision_codes, rows,
            subject_keywords=subject_keywords,
            # 备抵取绝对值归一为「计提」口径（贷方存负 / 存正两种约定并存）
            absolute=True,
        ),
    }

    trial_rows: list = []
    standard_codes = sorted(
        {
            *(getattr(codes, "gross_standard", None) or []),
            *(getattr(codes, "provision_standard", None) or []),
        }
    )
    if standard_codes:
        try:
            trial_rows = await fetch_trial_balance_rows(
                ctx.db, ctx.project_id, ctx.year, standard_codes
            )
        except Exception as e:  # noqa: BLE001 — fail-open
            logger.warning(
                "D 循环取数[%s] 阶段=fetch_trial_balance_rows 失败（fail-open）: %s",
                wp_code, e,
            )

    standard_by_slot = {
        SLOT_GROSS: list(getattr(codes, "gross_standard", None) or []),
        SLOT_PROVISION: list(getattr(codes, "provision_standard", None) or []),
    }
    pc: dict = {}
    try:
        pc = build_parent_check(
            _ParentCheckView(slots, standard_by_slot),
            rows,
            trial_rows,
            SLOT_KEYS,
            occurrence=occurrence,
        )
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning(
            "D 循环取数[%s] 阶段=build_parent_check 失败（fail-open）: %s", wp_code, e
        )

    return DCycleTbData(
        wp_code=wp_code,
        slots=slots,
        parent_check=pc,
        tb_rows=tuple(rows),
        trial_rows=tuple(trial_rows),
    )


class _ParentCheckView:
    """把 :class:`SlotAmounts` 适配成 `build_parent_check` 期望的 ``accounts`` 形态。

    共享件只要求 ``accounts.slots[key]`` 具备 ``found`` / ``codes`` / ``standard_codes``
    三个属性。

    两个刻意的选择：

    - ``codes`` 用**过滤后的** ``query_codes`` —— 否则被名称过滤剔掉的码会重新进入
      三口径比对，让 ``diff_parent`` 与实际取数口径不一致。
    - ``standard_codes`` 必须**真实回填**。留空会让 ``trial`` 侧恒 0，
      ``consistent`` 判定虽会跳过该侧不误报，但三口径就退化成两口径 ——
      而实证 H8 那 1.76 亿的 `trial_balance` 父子双算，**只比对前两个口径根本发现不了**
      （叶子和 == 父额完全成立）。这正是本模块要三口径并列的全部意义。
    """

    __slots__ = ("slots",)

    def __init__(
        self,
        slots: dict[str, SlotAmounts],
        standard_by_slot: dict[str, list[str]],
    ) -> None:
        self.slots = {
            k: _SlotView(v, standard_by_slot.get(k) or []) for k, v in slots.items()
        }


class _SlotView:
    __slots__ = ("_s", "_std")

    def __init__(self, s: SlotAmounts, standard_codes: list[str]) -> None:
        self._s = s
        self._std = list(standard_codes)

    @property
    def found(self) -> bool:
        # 无可查前缀时不参与三口径（与「found=False 时不产生该键」同口径）
        return bool(self._s.found and self._s.query_codes)

    @property
    def codes(self) -> list[str]:
        return list(self._s.query_codes)

    @property
    def standard_codes(self) -> list[str]:
        return list(self._std)


def build_d_tb_source_codes(codes, data: DCycleTbData) -> dict:
    """构造 render 下发的 `tb_source_codes`（科目定位 + 四态取数 + 溯源）。

    在 :meth:`DCycleAccountCodes.as_dict` 基础上**追加**取数侧信息，并保留
    ``gross`` / ``provision`` / ``gross_standard`` / ``provision_standard`` /
    ``resolved_from`` 这几个**既有消费方已在读的扁平键**（前端 `html_data` 在 TS 里是
    ``any``，改键名不会编译报错、只会静默读到 undefined）。
    """
    out = dict(codes.as_dict()) if hasattr(codes, "as_dict") else {}
    out["slots"] = {k: v.as_dict() for k, v in (data.slots or {}).items()}
    out["parent_check"] = dict(data.parent_check or {})
    out["fetch_ok"] = bool(data.ok)
    if data.error:
        out["fetch_error"] = data.error
    # 便于前端一行判断是否要出 warning 条
    out["has_prefix_mismatch"] = any(
        s.prefix_mismatch for s in (data.slots or {}).values()
    )
    out["has_dropped"] = any(bool(s.dropped) for s in (data.slots or {}).values())
    return out


async def build_parent_check_for_specs(
    ctx,
    code_by_slot: dict[str, list[str]],
    standard_by_slot: dict[str, list[str]],
    *,
    occurrence: bool = False,
) -> dict:
    """给「不用 :class:`DCycleAccountCodes` 的循环」构造三口径自检（当前是 D4）。

    D4 有自己的 ``D4AccountScope``，且 ``fetch_d4_leaf_rows`` 返回的是**已筛叶子**
    —— 直接喂给 :func:`build_parent_check` 会让 ``parent`` 侧恒 0（父行不在集合里）。
    本函数按规格集重新宽取一次子树（含父行）再比对，使三口径都有效。

    Args:
        ctx: `RenderContext`。
        code_by_slot: ``{槽键: 原始码/规格集}`` —— 支持 ``1401~1499`` 区间形态。
        standard_by_slot: ``{槽键: 标准码集}``（trial 侧按标准码归集）。
        occurrence: 损益类置 ``True``（用发生额而非期末余额）。

    Returns:
        ``{槽键: {leaf_sum, parent, trial_balance, diff_parent, diff_trial, consistent}}``；
        任一环失败返回 ``{}``（fail-open）。
    """
    all_specs: list[str] = []
    for v in code_by_slot.values():
        all_specs.extend(str(c) for c in (v or []))
    if not all_specs:
        return {}

    try:
        prefixes = sql_prefixes_for_specs(all_specs)
        rows = await fetch_tb_subtree(ctx.db, ctx.project_id, ctx.year, prefixes)
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("三口径自检: tb_balance 宽取失败（fail-open）: %s", e)
        return {}

    all_standard: list[str] = []
    for v in standard_by_slot.values():
        all_standard.extend(str(c) for c in (v or []))
    trial_rows: list = []
    if all_standard:
        try:
            trial_rows = await fetch_trial_balance_rows(
                ctx.db, ctx.project_id, ctx.year, sorted(set(all_standard))
            )
        except Exception as e:  # noqa: BLE001 — fail-open
            logger.warning("三口径自检: trial_balance 取行失败（fail-open）: %s", e)

    slots = {
        k: SlotAmounts(key=k, found=bool(v), query_codes=tuple(str(c) for c in (v or [])))
        for k, v in code_by_slot.items()
    }
    try:
        return build_parent_check(
            _ParentCheckView(slots, standard_by_slot),
            rows,
            trial_rows,
            tuple(code_by_slot.keys()),
            occurrence=occurrence,
        )
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("三口径自检: build_parent_check 失败（fail-open）: %s", e)
        return {}


async def seed_tb_amount_scalars(
    ctx,
    codes,
    project_context: dict,
    *,
    net_of_provision: bool = False,
    write_zero_when_missing: bool = False,
) -> dict:
    """按解析出的**标准码**查 `trial_balance`，写 `project_context` 的 TB 核对标量。

    收敛 D2/D3/D5/D6/D7 五个 render 里形态相同的裸 SQL（D1 保留自己的实现，是零回归红线）。

    写入的键（与既有循环逐字一致，前端 seed 回退按这些键名读）::

        tb_amount / tb_amount_unadjusted / tb_amount_audited
        tb_provision_amount / tb_provision_amount_unadjusted / tb_provision_amount_audited

    Args:
        ctx: `RenderContext`。
        codes: :class:`DCycleAccountCodes`。
        project_context: 原地写入的字典。
        net_of_provision: 置 True 时把 ``tb_amount`` 归一为**净额**（原值 − 备抵），
            原值移入 ``tb_amount_gross*``。仅 D2 需要（其审定表被比较项是「三、应收账款净值」）。
        write_zero_when_missing: 无记录时是否仍写 ``tb_amount=0``。

            置 **True** 用于改造前就**无条件**写该键的循环（D5/D6/D7）——
            它们的原实现是 ``tb_amount = 0`` 初始化后无条件赋值，改成「不写键」会让前端
            从「读到 0」变成「读不到」，属行为回归。四态信息由新增的
            ``tb_source_codes.slots`` 表达，不必牺牲旧键的兼容性。

            置 **False**（默认）用于改造前「有记录才写键」的循环（D2）。

    Returns:
        ``{"gross": {...} | None, "provision": {...} | None}`` 供调用方记日志/断言。

    .. note::
       **本函数顺带修掉两个既有缺陷**（2026-08-05 实证）：

       1. **D5 / D6 的原查询缺 ``year`` 过滤** —— ``WHERE project_id = :pid AND
          standard_account_code LIKE '1141%'`` 没有年度条件 ⇒ 多年度项目把**所有年份**
          加总。本函数经 :func:`fetch_trial_balance_amounts` 一律带 ``year``。
       2. **D5 原用 ``LIMIT 1`` 取第一行而非 ``SUM``** ⇒ 该科目有多行时漏数。

       故对多年度项目，改造后 ``tb_amount`` 的数值**会变**（变正确）。这不是回归。
    """
    result: dict = {"gross": None, "provision": None}

    if write_zero_when_missing:
        # 先占位再查 —— 保证「压根解析不出标准码」（如 D5 的 `fallback_gross=()`
        # 在 report_config 解析失败时）也不会让键缺失。真实取到值时下方会覆盖。
        project_context.setdefault("tb_amount", 0.0)

    gross_standard = list(getattr(codes, "gross_standard", None) or [])
    if gross_standard:
        try:
            amounts = await fetch_trial_balance_amounts(
                ctx.db, ctx.project_id, ctx.year, gross_standard
            )
        except Exception as e:  # noqa: BLE001 — fail-open
            logger.warning(
                "D 循环取数[%s] 阶段=trial_balance(原值) 失败（fail-open）: %s",
                getattr(codes, "wp_code", ""), e,
            )
            amounts = None
        if amounts is not None:
            aud = float(amounts.get("audited") or 0)
            unadj = float(amounts.get("unadjusted") or 0)
            # 审定优先；审定为 0 时回退未审（TB 尚未回写审定数的场景）
            project_context["tb_amount"] = aud if aud else unadj
            project_context["tb_amount_unadjusted"] = unadj
            project_context["tb_amount_audited"] = aud
            result["gross"] = dict(amounts)

    provision_standard = list(getattr(codes, "provision_standard", None) or [])
    if provision_standard:
        try:
            amounts = await fetch_trial_balance_amounts(
                ctx.db, ctx.project_id, ctx.year, provision_standard
            )
        except Exception as e:  # noqa: BLE001 — fail-open
            logger.warning(
                "D 循环取数[%s] 阶段=trial_balance(备抵) 失败（fail-open）: %s",
                getattr(codes, "wp_code", ""), e,
            )
            amounts = None
        if amounts is not None:
            # 备抵在 trial_balance v2 正数口径下存正值，取绝对值归一为「计提」口径
            p_aud = abs(float(amounts.get("audited") or 0))
            p_unadj = abs(float(amounts.get("unadjusted") or 0))
            project_context["tb_provision_amount"] = p_aud if p_aud else p_unadj
            project_context["tb_provision_amount_unadjusted"] = p_unadj
            project_context["tb_provision_amount_audited"] = p_aud
            result["provision"] = dict(amounts)

    if net_of_provision:
        # 复用 D1 已实测的净额归一（无备抵数据时空操作）——刻意不复制一份实现，
        # 避免「同一口径两处各写一遍」的双真源（D1 是该口径的原产地）。
        from app.routers.wp_render_strategies._d1_notes_receivable import _net_tb_amount

        _net_tb_amount(project_context)

    return result


__all__ = [
    "SLOT_GROSS",
    "SLOT_KEYS",
    "SLOT_PROVISION",
    "DCycleTbData",
    "SlotAmounts",
    "build_d_tb_source_codes",
    "build_parent_check_for_specs",
    "fetch_d_cycle_tb",
    "seed_tb_amount_scalars",
]
