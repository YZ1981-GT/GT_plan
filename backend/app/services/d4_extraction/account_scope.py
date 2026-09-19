"""D4 营业收入 / 营业成本的**动态**科目定位（报表行驱动，逐项目反解）。

设计要点（为什么必须动态）
--------------------------

不同客户的收入科目结构完全不同，DB 只读实证：

===================  ==========================================================
项目                 ``6001`` 子科目形态
===================  ==========================================================
``0ec33ac9`` 等 8 个 ``.11 批发`` / ``.12 零售`` / ``.14 物流`` / ``.15 物业与
                     租赁`` / ``.16 医疗收入`` / ``.17 服务费及其他``（含三级）
另 1 个              ``.01 车辆租金收入`` / ``.02 服务费收入`` /
                     ``.03 车辆销售收入`` / ``.04 车辆销售增值服务收入``
===================  ==========================================================

→ **任何写死的科目码集合都是错的**。定位链路固定为::

    report_config（按准则）      IS-001 = SUM_TB('6001~6099','本期发生额')
                                 IS-002 = SUM_TB('6401~6499','本期发生额')
        ↓ resolve_report_line_accounts（共享件；区间码原样返回）
    标准码规格集（含区间）
        ↓ to_original_codes_with_flag（共享件；account_mapping 反解，逐项目）
    客户原始码前缀集
        ↓ sql_prefixes_for_specs + filter_by_code_specs + select_leaves（共享件）
    叶子科目行

收入 / 成本镜像配对
-------------------

实证：客户把收入与成本挂在**后缀完全镜像**的子科目上::

    6001.11    营业收入_批发        ↔  6401.11    营业成本_批发
    6001.11.02 营业收入_批发_分销   ↔  6401.11.02 营业成本_批发_分销
    6001.16    营业收入_医疗收入    ↔  6401.16    营业成本_医疗支出   ← 名称不等！
    6001.15    营业收入_物业与租赁  ↔  （无对应成本子科目）          ← 镜像有缺口！

故配对规则：**后缀优先、名称仅作校验不否决、配不上留空**（宁缺勿造）。
分部标签一律取 ``account_name`` —— 编码语义在项目间冲突（同 N4 ``6403`` /
F2 ``14xx`` 铁律），禁按编码归类。

spec: .kiro/specs/d4-four-table-extraction-and-disclosure-alignment/
      Requirements 2.1~2.7 / Property 1, 2, 7, 8
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table import (
    RESOLVED_FROM_FALLBACK,
    LeafRow,
    ReportLineAccountSpec,
    filter_by_code_specs,
    resolve_report_line_accounts,
    select_leaves,
    sql_prefixes_for_specs,
    to_leaf_rows,
    to_original_codes_with_flag,
)

#: 标准科目名里表示「收入」/「成本」语义的关键字 —— 用于把报表行的**宽区间**收敛到
#: D4 真正关心的根科目。
#:
#: 🔴 为什么必须收敛（实测证据）：`report_config` 的
#: ``IS-002 减：营业成本 = SUM_TB('6401~6499','本期发生额')`` 区间**过宽**，
#: 把 ``6403 税金及附加`` 一并括进来了。不收敛的话，项目 ``52c04ed1`` 的分部配对
#: 会凭空多出 5 行税金及附加（城建税 547,270.10 / 教育费附加 234,544.33 /
#: 地方教育费附加 156,362.88 / 车船使用税 2,094.70 / 印花税 1,094,010.52），
#: 而税金及附加属 N4 循环、报表行是 ``IS-003``、附注是独立章节。
#: 「税金及附加」不含「成本」二字 → 名称语义判定天然把它排除。
_REVENUE_NAME_HINTS: tuple[str, ...] = ("营业收入", "业务收入")
_COST_NAME_HINTS: tuple[str, ...] = ("营业成本", "业务成本")

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 报表行与兜底（唯一真源；兜底码只在 report_config 解析落空时生效）
# ─────────────────────────────────────────────────────────────────────────────

#: 一、营业收入 —— `report_config` 实证四准则一致：``SUM_TB('6001~6099','本期发生额')``
D4_REVENUE_ROW_CODE = "IS-001"
#: 减：营业成本 —— ``SUM_TB('6401~6499','本期发生额')``
D4_COST_ROW_CODE = "IS-002"

#: 🔴 兜底是**区间**不是单码 —— 与报表行公式同形，写单码会漏掉 6002+ / 6402+
D4_REVENUE_FALLBACK: tuple[str, ...] = ("6001~6099",)
D4_COST_FALLBACK: tuple[str, ...] = ("6401~6499",)

#: 收入 ↔ 成本的**标准科目**配对（会计准则层面的对应，非项目特异）。
#: 项目特异的部分是子科目后缀，由 `account_mapping` 反解得到。
#: 元组：``(收入标准码, 成本标准码, 分段标签)``
D4_ROOT_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("6001", "6401", "主营业务"),
    ("6051", "6402", "其他业务"),
)

#: 分部标签归一时要剥掉的科目名前缀（只影响**名称校验**，不影响配对成立）
_SEGMENT_NAME_PREFIXES: tuple[str, ...] = (
    "主营业务收入", "主营业务成本",
    "其他业务收入", "其他业务成本",
    "营业收入", "营业成本",
    "收入", "成本",
)
#: 剥前缀后可能残留的分隔符
_SEGMENT_NAME_SEPARATORS = "_-—－·:：/ 　"


# ─────────────────────────────────────────────────────────────────────────────
# 数据模型
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class D4AccountScope:
    """D4 收入 / 成本科目定位结果（供 render 输出 ``tb_source_codes``）。

    Attributes:
        revenue_standard: 收入标准码规格集（可能含区间，如 ``('6001~6099',)``）。
        cost_standard: 成本标准码规格集。
        revenue_original: 收入客户原始码前缀集（`account_mapping` 反解，逐项目）。
        cost_original: 成本客户原始码前缀集。
        revenue_resolved_from / cost_resolved_from: ``report_config`` 或 ``fallback``。
        revenue_exact / cost_exact: 是否**精确**反解出原始码（有 `account_mapping` 记录）。
        revenue_formula / cost_formula: 命中的报表公式原文（溯源展示）。
    """

    revenue_standard: tuple[str, ...] = ()
    cost_standard: tuple[str, ...] = ()
    revenue_original: tuple[str, ...] = ()
    cost_original: tuple[str, ...] = ()
    revenue_resolved_from: str = RESOLVED_FROM_FALLBACK
    cost_resolved_from: str = RESOLVED_FROM_FALLBACK
    revenue_exact: bool = False
    cost_exact: bool = False
    revenue_formula: str | None = None
    cost_formula: str | None = None
    #: 标准码有、`account_mapping` 无映射记录（暴露映射缺口，供 UI 提示）
    unmapped_standard: tuple[str, ...] = ()
    #: 报表行区间内**该项目实际存在**的标准码（区间展开结果，逐项目不同）
    revenue_standard_expanded: tuple[str, ...] = ()
    cost_standard_expanded: tuple[str, ...] = ()
    #: 落在报表行区间内但被 D4 语义收敛剔除的标准码（如 ``6403 税金及附加`` 属 N4）
    excluded_standard: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict:
        out = asdict(self)
        for k, v in list(out.items()):
            if isinstance(v, tuple):
                out[k] = list(v)
        return out


@dataclass(frozen=True)
class SegmentPair:
    """一个分部（行业 / 产品类型）的收入 + 成本配对行。

    对应附注（2）「营业收入、营业成本按行业（或产品类型）划分」的一个数据行。
    """

    label: str
    #: 配对依据 —— 剥掉根科目后的后缀（根本身为叶子时是空串）
    suffix: str
    #: 所属分段标签（主营业务 / 其他业务），取自 :data:`D4_ROOT_PAIRS`
    section: str = ""
    revenue_code: str | None = None
    cost_code: str | None = None
    revenue_name: str = ""
    cost_name: str = ""
    revenue_amount: float | None = None
    cost_amount: float | None = None
    #: 后缀配对成立但名称不等（如「医疗收入」/「医疗支出」）—— 仅提示，不解除配对
    name_mismatch: bool = False
    #: 该分部只有收入侧 / 只有成本侧
    cost_missing: bool = False
    revenue_missing: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（无 DB，可独立单测）
# ─────────────────────────────────────────────────────────────────────────────


def split_leaf_head_suffix(account_code: str, roots) -> tuple[str, str] | None:
    """把叶子科目码按**最长匹配**的根科目拆成 ``(root, suffix)``。

    严格点号边界：``root`` 或 ``root + '.'`` 开头才算命中，
    否则前缀 ``6001`` 会误命中 ``60010``（不同科目）。

    Returns:
        ``(root, suffix)``；``suffix`` 为剥掉 ``root.`` 后的剩余部分，
        根科目自身为叶子时是空串。无根命中时返回 ``None``。
    """
    code = (account_code or "").strip()
    if not code:
        return None
    best: tuple[str, str] | None = None
    for raw in roots or ():
        root = (raw or "").strip()
        if not root:
            continue
        if code == root:
            cand = (root, "")
        elif code.startswith(root + "."):
            cand = (root, code[len(root) + 1 :])
        else:
            continue
        if best is None or len(cand[0]) > len(best[0]):
            best = cand
    return best


def strip_segment_name_prefix(name: str) -> str:
    """剥掉科目名里的「营业收入_」「营业成本_」等前缀，得到分部名。

    用于**名称校验**与分部标签展示。实证 ``营业收入_批发`` → ``批发``、
    ``营业成本_医疗支出`` → ``医疗支出``。
    """
    s = (name or "").strip()
    if not s:
        return ""
    for p in _SEGMENT_NAME_PREFIXES:
        if s.startswith(p) and len(s) > len(p):
            rest = s[len(p) :].lstrip(_SEGMENT_NAME_SEPARATORS)
            if rest:
                return rest
    return s


def pair_revenue_cost_leaves(
    revenue_leaves: list[LeafRow],
    cost_leaves: list[LeafRow],
    *,
    revenue_amount_of=None,
    cost_amount_of=None,
    root_pairs: tuple[tuple[str, str, str], ...] = D4_ROOT_PAIRS,
) -> list[SegmentPair]:
    """按**后缀镜像**把收入叶子与成本叶子配对成分部行。纯函数。

    算法（顺序即优先级）：

    1. 对每个根科目配对 ``(收入根, 成本根)``，把两侧叶子按 ``suffix`` 建索引；
    2. ``suffix`` 相等即配对成立 —— **名称不等不解除配对**，只标
       :attr:`SegmentPair.name_mismatch`（实证 ``.16`` 收入侧「医疗收入」/
       成本侧「医疗支出」是合法命名差异）；
    3. 仅收入侧命中 → ``cost_amount=None`` + ``cost_missing=True``（宁缺勿造，
       实证 ``2aa00f57`` 的 ``6001.15 物业与租赁`` 有收入无对应成本子科目）；
       仅成本侧命中 → 反之；
    4. 不属于任何根科目配对的叶子（如客户把收入挂 ``6002``）单独成行，
       不丢弃、不硬塞进已有分部。

    不变量（Property 7）：每个输入叶子恰好出现在一个 :class:`SegmentPair` 中。

    Args:
        revenue_amount_of / cost_amount_of: ``LeafRow -> float | None`` 取额函数；
            默认取 ``credit``（收入）/ ``debit``（成本）—— 损益类单侧发生额口径。
        root_pairs: 根科目配对表，默认 :data:`D4_ROOT_PAIRS`。

    Returns:
        分部行列表；按 ``(section 顺序, suffix)`` 稳定排序。
    """
    rev_amt = revenue_amount_of or (lambda r: r.credit)
    cost_amt = cost_amount_of or (lambda r: r.debit)

    rev_roots = [rp[0] for rp in root_pairs]
    cost_roots = [rp[1] for rp in root_pairs]

    # (root, suffix) -> LeafRow
    rev_idx: dict[tuple[str, str], LeafRow] = {}
    rev_orphans: list[LeafRow] = []
    for r in revenue_leaves or []:
        hit = split_leaf_head_suffix(r.account_code, rev_roots)
        if hit is None:
            rev_orphans.append(r)
        else:
            rev_idx[hit] = r

    cost_idx: dict[tuple[str, str], LeafRow] = {}
    cost_orphans: list[LeafRow] = []
    for c in cost_leaves or []:
        hit = split_leaf_head_suffix(c.account_code, cost_roots)
        if hit is None:
            cost_orphans.append(c)
        else:
            cost_idx[hit] = c

    out: list[SegmentPair] = []
    for rev_root, cost_root, section in root_pairs:
        suffixes: list[str] = []
        for (root, sfx) in rev_idx:
            if root == rev_root and sfx not in suffixes:
                suffixes.append(sfx)
        for (root, sfx) in cost_idx:
            if root == cost_root and sfx not in suffixes:
                suffixes.append(sfx)
        for sfx in sorted(suffixes):
            r = rev_idx.get((rev_root, sfx))
            c = cost_idx.get((cost_root, sfx))
            r_seg = strip_segment_name_prefix(r.account_name) if r is not None else ""
            c_seg = strip_segment_name_prefix(c.account_name) if c is not None else ""
            label = r_seg or c_seg or (sfx or section)
            out.append(
                SegmentPair(
                    label=label,
                    suffix=sfx,
                    section=section,
                    revenue_code=r.account_code if r is not None else None,
                    cost_code=c.account_code if c is not None else None,
                    revenue_name=r.account_name if r is not None else "",
                    cost_name=c.account_name if c is not None else "",
                    revenue_amount=rev_amt(r) if r is not None else None,
                    cost_amount=cost_amt(c) if c is not None else None,
                    name_mismatch=bool(r is not None and c is not None and r_seg != c_seg),
                    cost_missing=c is None,
                    revenue_missing=r is None,
                )
            )

    # 不属于任何根配对的叶子 —— 不丢弃（Property 7：并集覆盖全部输入）
    for r in rev_orphans:
        out.append(
            SegmentPair(
                label=strip_segment_name_prefix(r.account_name) or r.account_code,
                suffix=r.account_code,
                section="",
                revenue_code=r.account_code,
                revenue_name=r.account_name,
                revenue_amount=rev_amt(r),
                cost_missing=True,
            )
        )
    for c in cost_orphans:
        out.append(
            SegmentPair(
                label=strip_segment_name_prefix(c.account_name) or c.account_code,
                suffix=c.account_code,
                section="",
                cost_code=c.account_code,
                cost_name=c.account_name,
                cost_amount=cost_amt(c),
                revenue_missing=True,
            )
        )
    return out


def code_in_specs(standard_code: str, specs) -> bool:
    """标准码是否落在科目规格集内（单码前缀 or ``lo~hi`` 区间）。纯函数。

    区间语义与共享件 :func:`~app.services.four_table.filter_by_code_specs` 一致：
    取一级科目段（首个 ``.`` / ``-`` 之前）作字符串比较。
    """
    code = (standard_code or "").strip()
    if not code:
        return False
    head = code.split(".", 1)[0].split("-", 1)[0]
    for raw in specs or ():
        spec = str(raw or "").strip()
        if not spec:
            continue
        if "~" in spec:
            lo, _, hi = (p.strip() for p in spec.partition("~"))
            if lo <= head <= hi:
                return True
        elif code == spec or code.startswith(spec + ".") or code.startswith(spec + "-"):
            return True
    return False


def converge_to_d4_semantics(
    candidates: list[tuple[str, str]],
    *,
    want: str,
    root_pairs: tuple[tuple[str, str, str], ...] = D4_ROOT_PAIRS,
) -> tuple[list[str], list[tuple[str, str]]]:
    """把区间展开出的标准码按**科目名语义**收敛到 D4 关心的根科目。纯函数。

    收敛规则（顺序即优先级）：

    1. 已在 :data:`D4_ROOT_PAIRS` 中显式声明的标准码 → 保留（准则层面的确定对应）；
    2. 科目名含收入 / 成本语义关键字 → 保留（动态发现客户的变体根科目，
       如把主营收入挂在 ``6002 主营业务收入-工程``）；
    3. 其余一律剔除并返回，供溯源展示 —— 实测 ``IS-002`` 的区间 ``6401~6499``
       会括进 ``6403 税金及附加``（属 N4 循环），必须剔除。

    Args:
        candidates: ``[(标准码, 科目名), ...]``，通常来自区间展开。
        want: ``"revenue"`` 或 ""cost""。

    Returns:
        ``(保留的标准码, [(剔除的标准码, 科目名), ...])``
    """
    if want == "revenue":
        declared = {rp[0] for rp in root_pairs}
        hints = _REVENUE_NAME_HINTS
    elif want == "cost":
        declared = {rp[1] for rp in root_pairs}
        hints = _COST_NAME_HINTS
    else:
        raise ValueError(f"converge_to_d4_semantics: 非法 want={want!r}")

    kept: list[str] = []
    dropped: list[tuple[str, str]] = []
    for code, name in candidates or ():
        c = (code or "").strip()
        if not c:
            continue
        n = (name or "").strip()
        if c in declared or any(h in n for h in hints):
            if c not in kept:
                kept.append(c)
        else:
            dropped.append((c, n))
    return kept, dropped


def rollup_asymmetric_pairs(pairs: list[SegmentPair]) -> list[SegmentPair]:
    """把**层级不对称**的收入 / 成本行归并成一个分部行。纯函数、幂等。

    🔴 为什么需要（实测形态，项目 ``c8621493``）：客户把零售收入挂在**父级**
    ``6001.12 营业收入_零售``（10,145,723.55），却把零售成本挂在**子级**
    ``6401.12.01 货物成本``（9,788,302.25）+ ``6401.12.02 成本差异``（-18,768.92）。
    纯叶子后缀配对会把同一个业务板块拆成 3 行（一行只有收入、两行只有成本），
    而附注（2）「按行业（或产品类型）划分」要的是**「零售」一行**（收入 + 成本各一列）。

    归并规则：某个只有收入的行，其后缀 ``S`` 是若干「只有成本」行后缀 ``S.x`` 的
    **严格祖先**时（同一 ``section``），把这些子行的成本求和并入父行，子行移除；
    反向（成本在父级、收入在子级）同样处理。

    不归并的情形（保持拆分，交由 UI 提示）：
      * 两侧都是叶子且后缀不同族 —— 本就是不同分部；
      * 两侧都已配对成功 —— 不动。

    归并后仍满足「金额不丢」：被移除子行的金额全部进入父行。
    """
    out: list[SegmentPair] = []
    consumed: set[int] = set()
    for i, p in enumerate(pairs or []):
        if i in consumed:
            continue
        if p.cost_missing and not p.revenue_missing and p.suffix:
            kids = [
                (j, q)
                for j, q in enumerate(pairs)
                if j != i
                and j not in consumed
                and q.revenue_missing
                and not q.cost_missing
                and q.section == p.section
                and q.suffix.startswith(p.suffix + ".")
            ]
            if kids:
                total = sum(q.cost_amount or 0 for _j, q in kids)
                consumed.update(j for j, _q in kids)
                out.append(
                    SegmentPair(
                        label=p.label,
                        suffix=p.suffix,
                        section=p.section,
                        revenue_code=p.revenue_code,
                        cost_code="+".join(q.cost_code or "" for _j, q in kids),
                        revenue_name=p.revenue_name,
                        cost_name="；".join(q.cost_name for _j, q in kids),
                        revenue_amount=p.revenue_amount,
                        cost_amount=total,
                        name_mismatch=True,
                        cost_missing=False,
                        revenue_missing=False,
                    )
                )
                continue
        if p.revenue_missing and not p.cost_missing and p.suffix:
            kids = [
                (j, q)
                for j, q in enumerate(pairs)
                if j != i
                and j not in consumed
                and q.cost_missing
                and not q.revenue_missing
                and q.section == p.section
                and q.suffix.startswith(p.suffix + ".")
            ]
            if kids:
                total = sum(q.revenue_amount or 0 for _j, q in kids)
                consumed.update(j for j, _q in kids)
                out.append(
                    SegmentPair(
                        label=p.label,
                        suffix=p.suffix,
                        section=p.section,
                        revenue_code="+".join(q.revenue_code or "" for _j, q in kids),
                        cost_code=p.cost_code,
                        revenue_name="；".join(q.revenue_name for _j, q in kids),
                        cost_name=p.cost_name,
                        revenue_amount=total,
                        cost_amount=p.cost_amount,
                        name_mismatch=True,
                        cost_missing=False,
                        revenue_missing=False,
                    )
                )
                continue
        out.append(p)
    return out


def build_d4_source_codes(scope: D4AccountScope) -> dict:
    """供 render 输出 ``tb_source_codes``（取数溯源，前端 `WpFourTableSourcePanel` 消费）。

    🔴 必须有前端消费方，否则是 dead output（H1 曾踩过）。
    """
    d = scope.as_dict()
    d["revenue_row_code"] = D4_REVENUE_ROW_CODE
    d["cost_row_code"] = D4_COST_ROW_CODE
    return d


# ─────────────────────────────────────────────────────────────────────────────
# DB 依赖
# ─────────────────────────────────────────────────────────────────────────────


async def expand_specs_to_project_standards(ctx, specs) -> list[tuple[str, str]]:
    """把科目规格集（含**区间**）展开为**该项目实际存在**的标准码 + 科目名。

    🔴 为什么必须先展开再反解（实测证据）：直接把区间码 ``'6001~6099'`` 丢给
    :func:`~app.services.four_table.to_original_codes_with_flag` 去查
    `account_mapping`，表里当然没有叫 ``6001~6099`` 的 ``standard_account_code``
    → 反解落空 → 退化成前缀兜底 → ``exact=False``，**「逐项目反解」实际没生效**。

    数据源取并集：`account_mapping.standard_account_code`（映射侧）
    ∪ `trial_balance.standard_account_code`（报表侧），并带上科目名供语义收敛。
    """
    rows: list[tuple[str, str]] = []
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT DISTINCT standard_account_code AS c, "
                "       COALESCE(MAX(account_name), '') AS n "
                "FROM trial_balance "
                "WHERE project_id = :pid AND is_deleted = false "
                "GROUP BY standard_account_code "
                "UNION "
                "SELECT DISTINCT standard_account_code AS c, "
                "       COALESCE(MAX(original_account_name), '') AS n "
                "FROM account_mapping "
                "WHERE project_id = :pid AND is_deleted = false "
                "GROUP BY standard_account_code"
            ),
            {"pid": str(ctx.project_id)},
        )
        seen: dict[str, str] = {}
        for r in result.fetchall():
            code = (r.c or "").strip()
            if not code or not code_in_specs(code, specs):
                continue
            name = (r.n or "").strip()
            if code not in seen or (name and not seen[code]):
                seen[code] = name
        rows = sorted(seen.items())
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("D4 取数: 区间展开失败（退化为规格集原样）: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return []
    return rows


async def resolve_d4_accounts(ctx) -> D4AccountScope:
    """解析 D4 收入 / 成本科目（报表行驱动 → 区间展开 → 语义收敛 → 逐项目反解）。

    全程 fail-open：任一环失败均返回可用结果并在 ``*_resolved_from`` 标注来源。

    Args:
        ctx: 需具备 ``db`` / ``project_id`` / ``year``（`RenderContext` 或等价对象）。
    """
    rev = await resolve_report_line_accounts(
        ctx,
        ReportLineAccountSpec(
            row_code=D4_REVENUE_ROW_CODE, fallback_gross=D4_REVENUE_FALLBACK
        ),
    )
    cost = await resolve_report_line_accounts(
        ctx,
        ReportLineAccountSpec(
            row_code=D4_COST_ROW_CODE, fallback_gross=D4_COST_FALLBACK
        ),
    )

    rev_spec = tuple(rev.gross_standard) or D4_REVENUE_FALLBACK
    cost_spec = tuple(cost.gross_standard) or D4_COST_FALLBACK

    # 区间 → 该项目实际标准码（逐项目不同）→ 按科目名语义收敛（剔除 6403 等）
    rev_kept, rev_dropped = converge_to_d4_semantics(
        await expand_specs_to_project_standards(ctx, rev_spec), want="revenue"
    )
    cost_kept, cost_dropped = converge_to_d4_semantics(
        await expand_specs_to_project_standards(ctx, cost_spec), want="cost"
    )

    # 收敛后为空（项目还没导四表 / 科目名不含语义词）→ 回退到声明的根科目，
    # 保证下游取数有前缀可用（宁缺勿造由取数结果为空体现，而非这里返回空集）
    rev_std = tuple(rev_kept) or tuple(rp[0] for rp in D4_ROOT_PAIRS)
    cost_std = tuple(cost_kept) or tuple(rp[1] for rp in D4_ROOT_PAIRS)

    rev_orig, rev_exact = await to_original_codes_with_flag(ctx, list(rev_std))
    cost_orig, cost_exact = await to_original_codes_with_flag(ctx, list(cost_std))

    unmapped: list[str] = []
    if not rev_exact:
        unmapped.extend(rev_std)
    if not cost_exact:
        unmapped.extend(cost_std)

    return D4AccountScope(
        revenue_standard=rev_spec,
        cost_standard=cost_spec,
        revenue_standard_expanded=rev_std,
        cost_standard_expanded=cost_std,
        revenue_original=tuple(rev_orig),
        cost_original=tuple(cost_orig),
        revenue_resolved_from=rev.resolved_from,
        cost_resolved_from=cost.resolved_from,
        revenue_exact=rev_exact,
        cost_exact=cost_exact,
        revenue_formula=rev.formula,
        cost_formula=cost.formula,
        unmapped_standard=tuple(dict.fromkeys(unmapped)),
        excluded_standard=tuple(dict.fromkeys(rev_dropped + cost_dropped)),
    )


async def fetch_d4_rows(ctx, specs) -> list[LeafRow]:
    """按科目规格集（**支持区间**）从 `tb_balance` 取 active 数据集的**全量行（含父行）**。

    🔴 与 :func:`fetch_d4_leaf_rows` 的区别很重要：共享件
    :func:`~app.services.four_table.resolve_leaf_totals` 明确要求
    「rows 是该科目族的**全部**行（含父科目行本身）—— 父行是判定依据，不可预先剔除」。
    传已筛叶子的集合会让 ``parent_abs`` 全为 0 → ``diff`` 等于叶子和 →
    父额勾稽**假失败**（本 spec 首轮活体验证即踩此坑）。

    做父额勾稽 / 符号约定识别用本函数；只要分部明细用 :func:`fetch_d4_leaf_rows`。
    """
    prefixes = [p for p in sql_prefixes_for_specs(specs) if p]
    if not prefixes:
        return []
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
        )
        prefix_filter = sa.or_(*[TbBalance.account_code.like(f"{p}%") for p in prefixes])
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_direction,
                TbBalance.opening_direction,
                TbBalance.dataset_id,
            ).where(sa.and_(active_filter, prefix_filter))
        )
        return to_leaf_rows(result.fetchall())
    except Exception as e:  # noqa: BLE001 — fail-open，取数失败不阻断 render
        logger.warning("D4 取数: tb_balance 查询失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return []


async def fetch_d4_leaf_rows(ctx, specs) -> list[LeafRow]:
    """按科目规格集（**支持区间**）从 `tb_balance` 取 active 数据集的叶子行。

    🔴 两条硬约束：

    * 必须 ``get_active_filter`` —— `tb_balance` / `tb_ledger` 有 ``dataset_id``，
      裸写 ``is_deleted = false`` 会跨数据集双算（实证 ``0ec33ac9`` 的
      `tb_ledger` 6001 贷方 1,801,755,477.21 = `trial_balance` 权威值
      895,804,876.83 的 **2.01 倍**）。
    * 必须把整棵子树（含父行）取回来才能判叶子，故 SQL 用 ``LIKE '{prefix}%'``
      宽取，再由 :func:`filter_by_code_specs` / :func:`select_leaves` 做
      严格点号边界与区间收敛。
    """
    rows = await fetch_d4_rows(ctx, specs)
    return filter_by_code_specs(select_leaves(rows), specs)
