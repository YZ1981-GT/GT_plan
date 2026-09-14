"""D2~D7 科目定位 —— 报表规则映射驱动（D1 薄壳的参数化推广）。

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.1~1.3, 2.1~2.7

为什么是「推广」而不是「迁移」
------------------------------
2026-08-05 实证澄清了 D 类的真实现状（立项时按 ``grep resolve_semantic_accounts``
得 0 就判「D 类完全没接科目映射」，**判据选错了**）：

- **D1 早已有完整链路**，走共享件 :mod:`app.services.four_table.report_line_accounts`
  （``d1_account_resolver`` 只是放 D1 参数的薄壳），且已实现名称过滤、双态标注、
  fail-open 与零回归守卫。K1/K2/F1 是同一共享件的其它消费者。
- **该能力只有 D1 有** —— ``use_provision_name_filter`` 全库只命中 ``d1_*``，
  D2~D7 的 render 全在用硬编码前缀。
- **D 类科目码在项目间基本一致**（``1121`` / ``1122`` / ``2203`` / ``6001``
  各项目相同）⇒ 换成 :func:`resolve_semantic_accounts` 买不到东西；而唯一码不一致的
  D7（client ``2204`` vs standard ``2205``）靠 ``account_mapping`` 反解已足够。
- 机械换解析器有已实证风险：F3/F4 曾因「下游读 ``accounts.gross`` 而新类型没有该字段」
  被弄坏，且 962 例测试全绿一个没抓到。

故本模块把 D1 的薄壳范式**参数化推广**到 D2~D7，委托同一个共享件，口径天然一致。
``four_table/d_cycle_specs.py`` 的语义规格保留但**当前不接线**（理由见该文件头）。

D1 为什么不并进来
-----------------
``d1_account_resolver`` 有自己的返回类型 ``D1AccountCodes``、专属常量与守卫测试，
且 ``_d1_notes_receivable`` / ``d1_detail_seed`` 已在消费。并进来只有「代码整齐」
的收益，却要动一条已跑通的链路 —— 本 spec 把 D1 定为**零回归红线**。
两者委托同一个 ``resolve_report_line_accounts``，故口径同源，不构成双真源。

D4 为什么不在本模块
-------------------
D4 已有自己的 ``D4AccountScope`` + ``build_d4_tb_values`` + ``tb_source_codes``
（是 D 类现状最完整的一个），且其报表行 ``IS-001`` 的公式是**区间函数**
``SUM_TB('6001~6099','本期发生额')``，与本模块面向的单码/多码离散形态不同。
在此另立一份 ``ReportLineAccountSpec`` 会形成双真源，故 D4 只在下方登记为
「有意不纳入」并说明去处。

备抵过滤的三种成因（本模块与既有机制的分工）
--------------------------------------------
共享件已提供 ``use_provision_name_filter``（保守口径）与 ``provision_exact``
（精确判定），其 docstring 自述备抵污染有两种成因：① 报表公式没引用备抵科目
② ``account_mapping`` 反解退化为宽前缀。

本模块补**第三种**：**反解成功但映射数据本身错** —— 实证 ``account_mapping`` 有
``1231.05 坏账准备_长期应收款 → 1231-02``（``auto_fuzzy``，2 个项目）。此时
``provision_resolved_from='report_config'`` ⇒ ``use_provision_name_filter`` 为
**False** ⇒ 既有机制不叠过滤 ⇒ 长期应收款的坏账进入 D2 备抵。
故 :attr:`DCycleAccountCodes.subject_keywords` 供调用方**无条件**叠加
:func:`four_table.d_provision_filter.filter_provision_codes`。
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from app.services.four_table.report_line_accounts import (
    RESOLVED_FROM_FALLBACK,
    ReportLineAccountSpec,
    resolve_report_line_accounts,
)

logger = logging.getLogger(__name__)

# ─────────────────────────── 每循环的定位参数（DB 实证）───────────────────────────
#
# report_config 实证（2026-08-05，四准则逐条查）：
#   D2 BS-006 应收账款      listed_standalone : TB('1122') - TB('1231')      ← 🔴 用整个 1231
#                          soe_standalone    : TB('1122') - TB('1231-02')   ← 正确
#                          两个 consolidated : TB('1122')                   ← 不减备抵
#   D3 BS-046 预收款项      四准则一律 TB('2203')
#   D5 BS-007 应收款项融资  四准则一律 TB('1124')  ← 1124 与「应收款项融资」在两张科目表零命中
#   D6 BS-011 合同资产      四准则一律 TB('1141')  ← tb_balance 全库 0 行
#      IMP-004 合同资产减值准备  四准则 formula **全 NULL** → 只能靠兜底码
#   D7 BS-047 合同负债      四准则一律 TB('2205')  ← tb_balance 全库 0 行；
#                          唯一有数据的项目用 client 码 2204，account_mapping 已有 2205←2204
#
# `BS-006 listed_standalone` 用整个 1231 是 report_config 自身缺陷（归
# report-config-account-code-integrity spec）。本模块不改该表，而是靠
# `subject_keywords` 的名称过滤把非应收账款的坏账剔掉 —— 这也是为什么 D2 的过滤
# 必须**无条件**生效而不能依赖 `use_provision_name_filter`。

D2_SPEC = ReportLineAccountSpec(
    row_code="BS-006",
    fallback_gross=("1122",),
    fallback_provision=("1231-02",),
    provision_name_filter="应收账款",
)

D3_SPEC = ReportLineAccountSpec(
    row_code="BS-046",
    fallback_gross=("2203",),
    # 预收款项无备抵科目
    is_liability=True,
)

D5_SPEC = ReportLineAccountSpec(
    row_code="BS-007",
    # `1124` 是 CAS 里应收款项融资的**正确**科目码（财会[2019]6 号新增），不是错码 ——
    # 它在活体 `account_chart` 两个 source 下零命中、`account_mapping` 零反解、
    # `tb_balance` 零数据行，是**业务事实**（这批项目没有应收款项融资业务）。
    #
    # 🔴 曾一度刻意留空 `fallback_gross=()`，理由是「宁缺勿造」。复核后改回给兜底码：
    #   ① 「本项目无此科目」应由 `tb_source_codes.slots[*].found` / `tb_rows_count`
    #      表达（四态机制），**不靠 fallback 为空**来表达 —— 后者会连 `trial_balance`
    #      都不查，让审定表连「查过、没有」都区分不出来；
    #   ② 留空会让 `report_config` 解析失败时 `gross_standard` 为空 ⇒ 不查
    #      `trial_balance` ⇒ `tb_amount` 恒 0，破坏「Tier A seed 值 ≡
    #      project_context.tb_amount」这条既有不变式（Property 7）。
    fallback_gross=("1124",),
)

D6_SPEC = ReportLineAccountSpec(
    row_code="BS-011",
    fallback_gross=("1141",),
    # 两个候选备抵码：`1142 合同资产减值准备`（standard 6 项目）与
    # `1231-05 坏账准备-合同资产`（standard 10 项目）。两者在 tb_balance 均无数据行。
    fallback_provision=("1142", "1231-05"),
    # `IMP-004` 当前四准则 formula 全 NULL（解析必失败 → 走 fallback）。仍声明它，
    # 是为了在该报表行将来被补上公式时自动生效，而不必再改代码。
    provision_row_code="IMP-004",
    provision_name_filter="合同资产",
)

D7_SPEC = ReportLineAccountSpec(
    row_code="BS-047",
    fallback_gross=("2205",),
    # 合同负债无备抵科目
    is_liability=True,
)

#: wp_code → 定位规格。**不含 D1**（走 `d1_account_resolver`）与 **D4**（走 `D4AccountScope`）
D_ACCOUNT_SPECS: dict[str, ReportLineAccountSpec] = {
    "D2": D2_SPEC,
    "D3": D3_SPEC,
    "D5": D5_SPEC,
    "D6": D6_SPEC,
    "D7": D7_SPEC,
}

#: 备抵侧名称过滤的主体关键词（**无条件**叠加，补第三种污染成因）
#:
#: 🔴 关键词粒度必须足以区分同族科目：D2 只能用「应收账款」，**不能**用「应收」——
#:    错映射进来的那条名叫「坏账准备_长期应收款」，它含「应收」但不含「应收账款」，
#:    正是靠这个差别拦住的。关键词写宽一格，这道过滤就完全空转。
D_SUBJECT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "D2": ("应收账款",),
    "D6": ("合同资产",),
    # D3 / D5 / D7 无备抵科目，不需要关键词
}

#: 有意不纳入本模块的 D 循环及去处（供守卫断言，防后续会话「顺手统一」）
NOT_IN_SCOPE: dict[str, str] = {
    "D1": "走 d_cycle_extraction.d1_account_resolver（零回归红线，委托同一共享件）",
    "D4": "走 _d4_operating_revenue 的 D4AccountScope（报表行 IS-001 是 SUM_TB 区间形态）",
}


@dataclass(frozen=True)
class DCycleAccountCodes:
    """D2~D7 科目定位结果（字段与 ``D1AccountCodes`` 同构 + 本 spec 新增项）。

    Attributes:
        wp_code: 所属循环。
        gross: 原值科目 —— **原始码**前缀集（用于 `tb_balance`）。
        provision: 备抵科目 —— 原始码前缀集（未过滤，过滤由调用方叠加）。
        gross_standard / provision_standard: **标准码**集（用于 `trial_balance`）。
        resolved_from / provision_resolved_from: ``report_config`` 或 ``fallback``。
        provision_exact: 备抵侧反解是否精确（见共享件同名字段）。
        subject_keywords: 备抵名称过滤的主体关键词；空 ⇒ 该循环无备抵科目。
        row_code / provision_row_code: 报表行（溯源展示）。
    """

    wp_code: str = ""
    gross: list[str] = field(default_factory=list)
    provision: list[str] = field(default_factory=list)
    gross_standard: list[str] = field(default_factory=list)
    provision_standard: list[str] = field(default_factory=list)
    resolved_from: str = RESOLVED_FROM_FALLBACK
    provision_resolved_from: str = RESOLVED_FROM_FALLBACK
    provision_exact: bool = False
    subject_keywords: tuple[str, ...] = ()
    row_code: str = ""
    provision_row_code: str | None = None

    @property
    def has_provision_slot(self) -> bool:
        """该循环是否有备抵科目（按 spec 声明，而非按取数结果）。"""
        return bool(self.subject_keywords) or bool(self.provision_standard)

    def as_dict(self) -> dict:
        """供 render 输出 `tb_source_codes` 的基础部分（四态字段由 `d_tb_fetch` 追加）。"""
        out = asdict(self)
        out["subject_keywords"] = list(self.subject_keywords)
        out["has_provision_slot"] = self.has_provision_slot
        return out


def spec_of(wp_code: str) -> ReportLineAccountSpec | None:
    """取某循环的定位规格；不在本模块范围内（D1/D4）返回 ``None``。"""
    return D_ACCOUNT_SPECS.get(str(wp_code or "").strip().upper())


async def resolve_d_cycle_account_codes(ctx, wp_code: str) -> DCycleAccountCodes:
    """解析 D2~D7 的原值 / 备抵科目（全程 fail-open）。

    Args:
        ctx: `RenderContext`（需含 ``db`` / ``project_id`` / ``year``）。
        wp_code: 循环编码（``D2`` ~ ``D7``，不含 D1/D4）。

    Returns:
        :class:`DCycleAccountCodes`。wp_code 不在范围内、或任一环失败时均返回可用结果
        （空集或兜底码），``resolved_from`` 标注实际来源 —— **绝不抛异常阻断 render**。

    .. note::
       返回的 ``provision`` 是**未过滤**的反解结果。调用方必须再经
       :func:`four_table.d_provision_filter.filter_provision_codes` 叠加
       ``subject_keywords`` 过滤（无条件，不以 ``use_provision_name_filter`` 为门），
       否则 D2 会在那 2 个含 ``auto_fuzzy`` 错映射的项目上把长期应收款坏账算进来。
    """
    code = str(wp_code or "").strip().upper()
    spec = spec_of(code)
    if spec is None:
        logger.warning(
            "D 循环科目解析: wp_code=%s 不在本模块范围（%s）",
            code,
            NOT_IN_SCOPE.get(code, "未登记"),
        )
        return DCycleAccountCodes(wp_code=code)

    try:
        acc = await resolve_report_line_accounts(ctx, spec)
    except Exception as e:  # noqa: BLE001 — fail-open，取数失败不阻断 render
        logger.warning("D 循环科目解析失败 wp_code=%s（fail-open 用兜底码）: %s", code, e)
        return DCycleAccountCodes(
            wp_code=code,
            gross=list(spec.fallback_gross),
            gross_standard=list(spec.fallback_gross),
            provision=list(spec.fallback_provision),
            provision_standard=list(spec.fallback_provision),
            subject_keywords=D_SUBJECT_KEYWORDS.get(code, ()),
            row_code=spec.row_code,
            provision_row_code=spec.provision_row_code,
        )

    return DCycleAccountCodes(
        wp_code=code,
        gross=list(acc.gross),
        provision=list(acc.provision),
        gross_standard=list(acc.gross_standard),
        provision_standard=list(acc.provision_standard),
        resolved_from=acc.resolved_from,
        provision_resolved_from=acc.provision_resolved_from,
        provision_exact=bool(getattr(acc, "provision_exact", False)),
        subject_keywords=D_SUBJECT_KEYWORDS.get(code, ()),
        row_code=spec.row_code,
        provision_row_code=spec.provision_row_code,
    )


__all__ = [
    "D2_SPEC",
    "D3_SPEC",
    "D5_SPEC",
    "D6_SPEC",
    "D7_SPEC",
    "D_ACCOUNT_SPECS",
    "D_SUBJECT_KEYWORDS",
    "NOT_IN_SCOPE",
    "DCycleAccountCodes",
    "resolve_d_cycle_account_codes",
    "spec_of",
]
