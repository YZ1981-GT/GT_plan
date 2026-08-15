"""I 类六循环（I1~I6）的报表行科目**动态**解析（单一真源）。

**动态在哪里 —— 三层全部按项目走，无一处写死客户科目**

1. **报表行公式** 优先取项目级覆盖 ``report_config.applicable_standard = 'project:{id}'``，
   其次按项目派生的适用准则精确匹配，最后才是兜底任取一条（且必须过行名校验）。
2. **标准码 → 客户原始码** 经 ``account_mapping(project_id, standard_account_code)`` 反解；
   同一标准码 `1701` 在 A 项目可能是 `1701`、在 B 项目可能是 `170101` 或 `1701.01`。
3. **子科目 → 业务维度** 只按 ``tb_balance.account_name`` 归类（见
   :mod:`.i1_asset_categories`），编码不参与判定；归类不中的叶子**原样透出**给前端建行，
   不塞进任何桶（R4.2）。

**为什么不能沿用各策略里的模块级前缀常量**

改造前六个 render 各自写死 `_I{N}_ACCOUNT_PREFIX(ES)`，只读实证出三个「取错科目族」级缺陷：

======  ==============================  ============================================
循环    改造前硬编码                    `account_chart` 实证
======  ==============================  ============================================
I2      ``1717``                        **全库无此码**；开发支出是 ``1704`` → 取数恒空
I5      ``1911``                        **全库无此码**；其他非流动资产无标准科目 → 恒空
I6      ``6602``                        ``6602`` 是**管理费用**（全库借方 6.24 亿）；
                                        研发费用是 ``6604`` → 数字完全错
======  ==============================  ============================================

另外三个循环（I1/I3/I4）科目码本身对，但取数把**父科目与子科目一起累加** —— 三个真实项目
实证 `1701`/`1702`/`1801` 旧口径 / 叶子口径 = **恰好 2.0000 倍**。正解是
`leaf_aggregation.select_leaves` 的叶子口径（叶子和与父行 `diff=0.00`）。

**两个平台级陷阱（本模块自己绕开，不改共享件）**

- **共享件的最后一级兜底会任取一条配置**：`resolve_report_line_account_codes` 的末级
  （``applicable_standard NOT LIKE 'project:%' ... LIMIT 1``，无 ``ORDER BY``）在
  「该 row_code 于本项目适用准则下 formula 为 NULL」时会**任取另一准则的公式**，从而解析出
  别的科目且 ``resolved_from='report_config'``（看起来很可信）。→ 本模块自己查公式并
  **校验 `row_name`**，行名不符即丢弃（:func:`row_name_matches`）。

  .. warning::
     🔴 **本段原先举的例子是错的，且正是 `I_CYCLE_ROW_CODES` 错值的思想来源**（2026-08-09 修）。
     原文称「``BS-050`` 在 `soe_*` 是『其他非流动资产』、``BS-040`` 反过来」——
     `report_config` 实证 ``BS-050`` **四准则全部**是「其他应付款」
     （``TB('2241')`` / standalone 侧另加 ``TB('2231')``）、``BS-040`` 四准则全部是
     「流动负债：」节标题（formula 为 NULL）。两个码**都不是 I 类的行**。
     当时按此错误认知把 I5 的 row_code 配成了 ``BS-040``/``BS-050``，再靠行名闸把
     解析结果全部丢弃 —— 于是「闸门生效」被误读成「设计正确」。
     ⇒ **行名闸的真实价值是防回退护栏，不是「跨准则语义不同」的补偿**；
     判某个 row_code 属不属于本循环，一律直接查 `report_config` 的 `row_name`。
- **二分 gross/provision 装不下 I1 的三段**：``TB('1701')-TB('1702')`` 经
  `split_gross_provision` 会把 ``1702 累计摊销`` 判成 gross（名称不含「减值准备」）→ 原值口径
  变净额。→ 本模块改用**段化声明** :class:`ISegmentSpec`，每段独立认领 / 独立兜底 / 独立方向。

**`report_config` 与 `account_chart` 冲突时的处置**

实证 ``BS-035 / BS-046 开发支出 = TB('1703','期末余额')``，而 ``1703 = 无形资产减值准备``、
``1704 = 开发支出`` —— 报表配置本身有误（报表模块的开发支出行当前也是错的）。本模块
**不改写 `report_config`**（同 G14 `6701/6702` 先例），而是：段兜底码按 `account_chart` 给正确值，
:func:`detect_chart_conflict` 把冲突诊断出来放进 ``tb_source_codes.chart_conflict``。

spec: .kiro/specs/i-cycle-four-table-extraction-and-disclosure-alignment/
      Requirements 1.1~1.6 / 2.1~2.4 / 3.1，Property 2 / 3
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import sqlalchemy as sa

from app.services.report_account_mapping import extract_codes_from_formula

from .report_line_accounts import (
    RESOLVED_FROM_FALLBACK,
    RESOLVED_FROM_REPORT,
    extract_signed_codes,
    fetch_applicable_standards,
    fetch_standard_chart_rows,
    normalize_standard_prefix,
    to_original_codes_with_flag,
)

logger = logging.getLogger(__name__)

#: 段键
SEGMENT_COST = "cost"
SEGMENT_AMORTIZATION = "amortization"
SEGMENT_IMPAIRMENT = "impairment"
SEGMENT_EXPENSE = "expense"


@dataclass(frozen=True)
class ISegmentSpec:
    """一个取数段的声明（纯数据）。

    Attributes:
        segment: 段键（英文稳定标识）。
        label: 中文段名，逐字取自源模板（审定表 / 披露表的层标题）。
        source_ref: ``'sheet名!单元格'``，守卫用 openpyxl 直读交叉比对 ``label``。
        fallback: 段兜底**标准码**（`account_chart` 实证值）。空 tuple = 宁缺勿造。
        name_keywords: 从报表公式解析出的码集中**认领**本段的科目名关键字。
        exclude_keywords: 认领否决词。
        claim_priority: 认领顺序（数字小者先）。与展示顺序解耦 —— 展示按声明顺序。
        absolute: 备抵段置 True，对**聚合结果**取绝对值（不在行级翻转符号）。
        credit_is_increase: 备抵段置 True —— ``credit_amount`` 是计提（增加）、
            ``debit_amount`` 是转回/核销（减少）。原值段相反。
        occurrence: 损益段置 True —— 取本期发生额（走 `trial_balance`），
            不用 `tb_balance` 的 ``debit - credit``（含结转损益分录时恒为 0）。
    """

    segment: str
    label: str
    source_ref: str = ""
    fallback: tuple[str, ...] = ()
    name_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    claim_priority: int = 0
    absolute: bool = False
    credit_is_increase: bool = False
    occurrence: bool = False


@dataclass(frozen=True)
class ISegmentAccounts:
    """一个段的解析结果。

    Attributes:
        standard: 段的**标准码**集（供 `trial_balance` 查询）。
        original: 段的**客户原始码**前缀集（供 `tb_balance` / `tb_aux_balance` 查询）。
        exact: 标准码是否经 `account_mapping` 精确反解（False = 退化为一级前缀，更宽）。
        resolved_from: ``report_config``（公式认领）或 ``fallback``（段兜底码）。
    """

    segment: str
    label: str
    standard: list[str] = field(default_factory=list)
    original: list[str] = field(default_factory=list)
    exact: bool = False
    resolved_from: str = RESOLVED_FROM_FALLBACK
    absolute: bool = False
    credit_is_increase: bool = False
    occurrence: bool = False


@dataclass(frozen=True)
class ICycleAccounts:
    """I 类某循环的科目定位结果（render 直接 `as_dict()` 成 `tb_source_codes`）。"""

    wp_code: str
    row_code: str = ""
    row_name: str = ""
    formula: str | None = None
    matched_standard: str = ""
    segments: tuple[ISegmentAccounts, ...] = ()
    signed_codes: list[tuple[str, int]] = field(default_factory=list)
    resolved_from: str = RESOLVED_FROM_FALLBACK
    diagnostics: list[dict] = field(default_factory=list)

    def segment(self, key: str) -> ISegmentAccounts | None:
        """按段键取结果；未知段返 ``None``。"""
        for s in self.segments:
            if s.segment == key:
                return s
        return None

    def standard_of(self, key: str) -> list[str]:
        """段的标准码集（未知段返 ``[]``）。"""
        s = self.segment(key)
        return list(s.standard) if s else []

    def original_of(self, key: str) -> list[str]:
        """段的客户原始码前缀集（未知段返 ``[]``）。"""
        s = self.segment(key)
        return list(s.original) if s else []

    @property
    def gross(self) -> list[str]:
        """兼容视图：原值 / 费用段的原始码前缀（供既有溯源面板 props）。"""
        return self.original_of(SEGMENT_COST) or self.original_of(SEGMENT_EXPENSE)

    @property
    def gross_standard(self) -> list[str]:
        """兼容视图：原值 / 费用段的标准码。"""
        return self.standard_of(SEGMENT_COST) or self.standard_of(SEGMENT_EXPENSE)

    @property
    def provision(self) -> list[str]:
        """兼容视图：全部备抵段（累计摊销 + 减值准备）的原始码前缀。"""
        out: list[str] = []
        for s in self.segments:
            if s.absolute:
                out.extend(c for c in s.original if c not in out)
        return out

    @property
    def provision_standard(self) -> list[str]:
        """兼容视图：全部备抵段的标准码。"""
        out: list[str] = []
        for s in self.segments:
            if s.absolute:
                out.extend(c for c in s.standard if c not in out)
        return out

    def sign_of(self, standard_code: str) -> int:
        """该标准码在报表公式中的符号（未出现返 ``0``）。"""
        for code, sign in self.signed_codes:
            if code == standard_code:
                return sign
        return 0

    def as_dict(self) -> dict:
        """供 render 输出 `tb_source_codes`（取数溯源，前端面板消费）。"""
        return {
            "wp_code": self.wp_code,
            "row_code": self.row_code,
            "row_name": self.row_name,
            "formula": self.formula,
            "matched_standard": self.matched_standard,
            "resolved_from": self.resolved_from,
            "signed_codes": [[c, s] for c, s in self.signed_codes],
            "segments": [asdict(s) for s in self.segments],
            "diagnostics": list(self.diagnostics),
            # 兼容键（既有 WpFourTableSourcePanel / tbSourceCodes.ts 在读）
            "gross": self.gross,
            "gross_standard": self.gross_standard,
            "provision": self.provision,
            "provision_standard": self.provision_standard,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 声明（唯一真源）
# ─────────────────────────────────────────────────────────────────────────────

#: 报表行编码。**取值 = `report_config` 逐行对账实证值**（2026-08-09）。
#:
#: I 类**四准则同码同名同公式**（`listed_standalone` / `listed_consolidated` /
#: `soe_standalone` / `soe_consolidated` 四行的 `row_name` 与 `formula` 逐字相同），
#: 故两个键取值相同。**这不是平台通例** —— J/K/L 循环确有「按变体不同」的行
#: （如 J1 listed `BS-051` / soe `BS-069`），故保留 ``dict[str, dict[str, str]]``
#: 结构以表达该维度，不塌成 ``dict[str, str]``。守卫 Property 2 显式断言 I 类两侧同码，
#: 防被按 J1 范式"修正"成两码。
#:
#: 🔴 **改造前 12 个取值里 11 个错**（仅 ``I6.listed`` 正确），且是**整体错位**：
#: listed 侧 ``BS-033/035/037/038/040`` 分别是「开发支出（I2 的行）/ 长期待摊费用（I4 的行）/
#: 其他非流动资产（I5 的行）/ 非流动资产合计（ROW 派生行）/ 流动负债：（节标题，formula NULL）」；
#: soe 侧 ``BS-045/046/047/048/050`` + ``IS-024`` 全是负债段与派生行
#: 「应付账款 / 预收款项 / 合同负债 / 应付职工薪酬 / 其他应付款 / 四、净利润」。
#: 当时未取到错数的唯一原因是 :func:`row_name_matches` 把错公式全部丢弃 →
#: 六循环 ``resolved_from`` 全部退化 ``fallback``，报表行解析层等于空转。
#:
#: **落地前已做 A/B 对照**（8 真实项目 × 6 循环，同进程内 monkeypatch 跑两遍）：
#: ``standard`` / ``original`` 码集、``tb_values``、``parent_check``、
#: ``adjudication_prefill`` **实质差异 0 处**；唯一变化是 ``resolved_from``
#: 由 ``fallback`` 转 ``report_config`` **34 处**（溯源标签，非取数结果）。
I_CYCLE_ROW_CODES: dict[str, dict[str, str]] = {
    # 无形资产 = TB('1701','期末余额') - TB('1702','期末余额')
    "I1": {"listed": "BS-032", "soe": "BS-032"},
    # 开发支出 = TB('1704','期末余额')
    "I2": {"listed": "BS-033", "soe": "BS-033"},
    # 商誉 = TB('1711','期末余额')
    "I3": {"listed": "BS-034", "soe": "BS-034"},
    # 长期待摊费用 = TB('1801','期末余额')
    "I4": {"listed": "BS-035", "soe": "BS-035"},
    # 其他非流动资产 = TB('1911','期末余额')；🔴 `1911` 全库两张科目表都不存在
    # → 段兜底为空 tuple → `found=False`（宁缺勿造），见 I5 段声明
    "I5": {"listed": "BS-037", "soe": "BS-037"},
    # 研发费用 = TB('6604','本期发生额')（损益类，走 trial_balance 发生额）
    "I6": {"listed": "IS-006", "soe": "IS-006"},
}

#: 报表行**行名**期望语义（行名校验闸 + 冲突诊断共用）
I_CYCLE_EXPECTED_NAMES: dict[str, tuple[str, ...]] = {
    "I1": ("无形资产", "累计摊销"),
    "I2": ("开发支出", "研发支出"),
    "I3": ("商誉",),
    "I4": ("长期待摊费用",),
    "I5": ("其他非流动资产",),
    "I6": ("研发费用",),
}

_SRC_I1_SOE = "附注披露信息（国有企业）"

#: 段声明。**声明顺序 = 审定表 / 披露表的展示顺序**；认领顺序看 ``claim_priority``。
I_CYCLE_SEGMENTS: dict[str, tuple[ISegmentSpec, ...]] = {
    "I1": (
        ISegmentSpec(
            segment=SEGMENT_COST,
            label="账面原值",
            source_ref=f"{_SRC_I1_SOE}!A8",  # 一、原价合计
            fallback=("1701",),
            name_keywords=("无形资产",),
            # 「无形资产减值准备」也含「无形资产」→ 必须否决
            exclude_keywords=("减值准备", "累计摊销"),
            claim_priority=30,
        ),
        ISegmentSpec(
            segment=SEGMENT_AMORTIZATION,
            label="累计摊销",
            source_ref=f"{_SRC_I1_SOE}!A21",  # 二、累计摊销合计
            fallback=("1702",),
            name_keywords=("累计摊销",),
            claim_priority=10,
            absolute=True,
            credit_is_increase=True,
        ),
        ISegmentSpec(
            segment=SEGMENT_IMPAIRMENT,
            label="减值准备",
            source_ref=f"{_SRC_I1_SOE}!A34",  # 三、无形资产减值准备合计
            fallback=("1703",),
            name_keywords=("减值准备",),
            claim_priority=20,
            absolute=True,
            credit_is_increase=True,
        ),
    ),
    "I2": (
        ISegmentSpec(
            segment=SEGMENT_COST,
            label="开发支出",
            source_ref="附注披露（国有企业）!A5",
            # 🔴 1704（account_chart 实证）；report_config 写 1703 有误，见模块 docstring
            fallback=("1704",),
            name_keywords=("开发支出", "研发支出"),
            exclude_keywords=("减值准备",),
            claim_priority=10,
        ),
    ),
    "I3": (
        ISegmentSpec(
            segment=SEGMENT_COST,
            label="商誉账面原值",
            source_ref="附注披露（上市公司）!A6",
            fallback=("1711",),
            name_keywords=("商誉",),
            exclude_keywords=("减值",),
            claim_priority=20,
        ),
        ISegmentSpec(
            segment=SEGMENT_IMPAIRMENT,
            label="商誉减值准备",
            source_ref="附注披露（上市公司）!A20",
            # 🔴 `account_chart` **无**「商誉减值准备」科目 → 空兜底（宁缺勿造）
            fallback=(),
            name_keywords=("商誉减值", "减值准备"),
            claim_priority=10,
            absolute=True,
            credit_is_increase=True,
        ),
    ),
    "I4": (
        ISegmentSpec(
            segment=SEGMENT_COST,
            label="长期待摊费用",
            source_ref="附注披露（国有企业）!A5",
            fallback=("1801",),
            name_keywords=("长期待摊费用",),
            claim_priority=10,
        ),
    ),
    "I5": (
        ISegmentSpec(
            segment=SEGMENT_COST,
            label="其他非流动资产",
            source_ref="附注披露（国有企业）!A5",
            # 🔴 无标准科目且 report_config formula 为 None → 空兜底（宁缺勿造，R1.4）
            fallback=(),
            name_keywords=("其他非流动资产",),
            claim_priority=10,
        ),
    ),
    "I6": (
        ISegmentSpec(
            segment=SEGMENT_EXPENSE,
            label="研发费用",
            source_ref="附注披露（上市公司）!A5",
            # 🔴 6604（改造前用 6602 管理费用）
            fallback=("6604",),
            name_keywords=("研发费用",),
            claim_priority=10,
            occurrence=True,
        ),
    ),
}

#: 损益类循环（取数口径为本期发生额）
I_CYCLE_PROFIT_LOSS: frozenset[str] = frozenset(
    code
    for code, segs in I_CYCLE_SEGMENTS.items()
    if any(s.occurrence for s in segs)
)

#: 平台静态标准科目表（`account_chart` 缺行时的名称兜底）
_STATIC_CHART_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "standard_account_chart.json"
)


def _norm(s) -> str:
    return str(s or "").strip()


@lru_cache(maxsize=1)
def static_chart_names() -> dict[str, str]:
    """平台静态标准科目表的 ``{code: name}``（进程级缓存）。读取失败返 ``{}``。

    为什么需要它：`account_chart` 是**按项目**存的，实证 ``1703`` 只在 5 个项目里有记录 →
    只查项目表时 :func:`detect_chart_conflict` 对其余项目一律漏判（`name` 取不到就跳过）。
    静态表兜底后 ``1703 → 无形资产减值准备`` / ``2205 → 合同负债`` 恒可判定。
    """
    try:
        raw = json.loads(_STATIC_CHART_PATH.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — 静态表缺失只降级，不阻断
        logger.debug("I 类科目解析: 静态标准科目表读取失败: %s", e)
        return {}
    out: dict[str, str] = {}
    for item in raw.get("accounts") or []:
        if not isinstance(item, dict):
            continue
        code = _norm(item.get("code"))
        name = _norm(item.get("name"))
        if code and name:
            out.setdefault(code, name)
    return out


def build_name_lookup(chart_rows) -> dict[str, str]:
    """``{标准码: 科目名}``：项目级 `account_chart` **优先**，平台静态表兜底。纯函数。"""
    out = dict(static_chart_names())
    for r in chart_rows or []:
        get = r.get if isinstance(r, dict) else (lambda k, _r=r: getattr(_r, k, None))
        code = _norm(get("account_code"))
        name = _norm(get("account_name"))
        if code and name:
            out[code] = name  # 项目级覆盖静态
    return out


def claim_segments(
    codes,
    name_lookup: dict[str, str],
    segments: tuple[ISegmentSpec, ...],
) -> tuple[dict[str, list[str]], list[str]]:
    """把报表公式解析出的标准码分配到各段。纯函数。

    按 :attr:`ISegmentSpec.claim_priority` 升序，每个码归入首个「命中 ``name_keywords``
    且不命中 ``exclude_keywords``」的段。名称取不到的码**不认领**（进 ``unclaimed``），
    绝不按码序猜段。

    Returns:
        ``(claimed, unclaimed)``：``claimed`` 是 ``{段键: [标准码, ...]}``（保持入参顺序），
        ``unclaimed`` 是没被任何段认领的码。两者并集 == 去重后的 ``codes``。
    """
    ordered = sorted(segments or (), key=lambda s: s.claim_priority)
    claimed: dict[str, list[str]] = {s.segment: [] for s in (segments or ())}
    unclaimed: list[str] = []
    seen: set[str] = set()
    for raw in codes or []:
        code = _norm(raw)
        if not code or code in seen:
            continue
        seen.add(code)
        name = name_lookup.get(code)
        if not name:
            unclaimed.append(code)
            continue
        hit = None
        for spec in ordered:
            if spec.exclude_keywords and any(k in name for k in spec.exclude_keywords):
                continue
            if spec.name_keywords and any(k in name for k in spec.name_keywords):
                hit = spec.segment
                break
        if hit is None:
            unclaimed.append(code)
        else:
            claimed[hit].append(code)
    return claimed, unclaimed


def detect_chart_conflict(
    codes,
    name_lookup: dict[str, str],
    expected_names,
    row_code: str = "",
) -> list[dict]:
    """诊断「报表公式引用的科目与本循环语义不符」。纯函数，只诊断不改写。

    Args:
        codes: 待检查的标准码集（通常是 :func:`claim_segments` 的 ``unclaimed``）。
        name_lookup: :func:`build_name_lookup` 的输出。
        expected_names: 本循环的期望语义关键字（:data:`I_CYCLE_EXPECTED_NAMES`）。
        row_code: 报表行编码（回填诊断项，供溯源展示）。

    Returns:
        ``[{"kind": "chart_conflict", "code", "chart_name", "expected", "row_code"}, ...]``；
        名称取不到的码**不判冲突**（宁漏勿误）。
    """
    keywords = tuple(k for k in (expected_names or ()) if _norm(k))
    if not keywords:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for raw in codes or []:
        code = _norm(raw)
        if not code or code in seen or "~" in code:
            continue
        seen.add(code)
        name = name_lookup.get(code)
        if not name or any(k in name for k in keywords):
            continue
        out.append(
            {
                "kind": "chart_conflict",
                "code": code,
                "chart_name": name,
                "expected": "/".join(keywords),
                "row_code": row_code,
            }
        )
    return out


def resolve_row_code(wp_code: str, standards) -> str:
    """按项目适用准则取报表行编码（命中 ``soe*`` 用国企编号，否则用上市编号）。纯函数。"""
    table = I_CYCLE_ROW_CODES.get(_norm(wp_code).upper()) or {}
    if any(_norm(s).startswith("soe") for s in (standards or ())):
        return table.get("soe") or table.get("listed") or ""
    return table.get("listed") or table.get("soe") or ""


def row_name_matches(row_name: str, expected_names) -> bool:
    """行名校验：``row_name`` 是否命中本循环期望语义。纯函数。

    这是拦住「跨准则取错行」的关键闸 —— 实证 ``BS-050`` 在 soe 下 formula 为 None，
    共享件兜底会取到 listed 的「合同负债」公式；行名不符即丢弃该公式。
    """
    nm = _norm(row_name)
    keywords = tuple(k for k in (expected_names or ()) if _norm(k))
    if not keywords:
        return True
    if not nm:
        return False
    return any(k in nm for k in keywords)


async def _fetch_report_line(
    ctx, row_code: str, standards: list[str]
) -> tuple[str, str | None, str]:
    """取报表行的 ``(row_name, formula, matched_standard)``。全程 fail-open。

    优先级：``project:{id}`` → 逐准则精确匹配 → 兜底任取一条非项目级配置。
    **每级都同时取 `row_name`**，供调用方做行名校验。
    """
    queries: list[tuple[str, dict]] = [
        (
            "SELECT row_name, formula, applicable_standard FROM report_config "
            "WHERE row_code = :rc AND applicable_standard = :std "
            "AND is_deleted = false LIMIT 1",
            {"rc": row_code, "std": f"project:{ctx.project_id}"},
        )
    ]
    queries += [
        (
            "SELECT row_name, formula, applicable_standard FROM report_config "
            "WHERE row_code = :rc AND applicable_standard = :std "
            "AND is_deleted = false LIMIT 1",
            {"rc": row_code, "std": std},
        )
        for std in (standards or [])
        if std
    ]
    queries.append(
        (
            "SELECT row_name, formula, applicable_standard FROM report_config "
            "WHERE row_code = :rc AND applicable_standard NOT LIKE 'project:%' "
            "AND is_deleted = false ORDER BY applicable_standard LIMIT 1",
            {"rc": row_code},
        )
    )
    last_name = ""
    try:
        for sql, params in queries:
            row = (await ctx.db.execute(sa.text(sql), params)).fetchone()
            if row is None:
                continue
            last_name = _norm(row.row_name) or last_name
            if row.formula:
                return (
                    _norm(row.row_name),
                    str(row.formula),
                    _norm(row.applicable_standard),
                )
    except Exception as e:  # noqa: BLE001 — 查询失败一律回退段兜底码
        logger.debug("I 类科目解析: 报表行 %s 查询失败: %s", row_code, e)
    return last_name, None, ""


async def resolve_i_cycle_accounts(ctx, wp_code: str) -> ICycleAccounts:
    """解析某 I 类循环的分段科目定位（按项目动态，全程 fail-open）。

    Args:
        ctx: `RenderContext`（需 `db` / `project_id` / `year`）。
        wp_code: ``'I1'`` ~ ``'I6'``。

    Returns:
        :class:`ICycleAccounts`。任一环失败都返回可用结果（段兜底码），
        ``resolved_from`` 与 ``diagnostics`` 标注实际来源与问题。

    Raises:
        KeyError: `wp_code` 不在 :data:`I_CYCLE_SEGMENTS` 中（编程错误，不 fail-open）。
    """
    code = _norm(wp_code).upper()
    specs = I_CYCLE_SEGMENTS[code]
    expected = I_CYCLE_EXPECTED_NAMES.get(code, ())

    standards = await fetch_applicable_standards(ctx)
    row_code = resolve_row_code(code, standards)
    row_name, formula, matched_std = await _fetch_report_line(ctx, row_code, standards)

    diagnostics: list[dict] = []

    # 🔴 行名校验闸：行名不符即丢弃公式（拦住跨准则取错行）
    if formula and not row_name_matches(row_name, expected):
        diagnostics.append(
            {
                "kind": "row_name_mismatch",
                "row_code": row_code,
                "row_name": row_name,
                "expected": "/".join(expected),
                "formula": formula,
                "matched_standard": matched_std,
            }
        )
        logger.warning(
            "I 类科目解析: %s 报表行 %s 的行名 %r 与本循环语义 %s 不符 → 丢弃公式 %r",
            code,
            row_code,
            row_name,
            expected,
            formula,
        )
        formula, matched_std = None, ""

    codes = extract_codes_from_formula(formula)
    signed = extract_signed_codes(formula)

    chart_rows = await fetch_standard_chart_rows(ctx)
    name_lookup = build_name_lookup(chart_rows)
    claimed, unclaimed = claim_segments(codes, name_lookup, specs)
    diagnostics.extend(
        detect_chart_conflict(unclaimed, name_lookup, expected, row_code=row_code)
    )
    for c in unclaimed:
        if not any(d.get("code") == c for d in diagnostics):
            diagnostics.append(
                {
                    "kind": "unclaimed",
                    "code": c,
                    "chart_name": name_lookup.get(c, ""),
                    "row_code": row_code,
                }
            )

    resolved_segments: list[ISegmentAccounts] = []
    any_from_report = False
    for spec in specs:
        std = list(claimed.get(spec.segment) or ())
        seg_from = RESOLVED_FROM_REPORT if std else RESOLVED_FROM_FALLBACK
        if not std:
            std = list(spec.fallback)
        else:
            any_from_report = True
        original, exact = ([], False)
        if std:
            original, exact = await to_original_codes_with_flag(ctx, std)
            if not original:
                original = [normalize_standard_prefix(c) for c in std]
        resolved_segments.append(
            ISegmentAccounts(
                segment=spec.segment,
                label=spec.label,
                standard=std,
                original=original,
                exact=exact,
                resolved_from=seg_from,
                absolute=spec.absolute,
                credit_is_increase=spec.credit_is_increase,
                occurrence=spec.occurrence,
            )
        )

    return ICycleAccounts(
        wp_code=code,
        row_code=row_code,
        row_name=row_name,
        formula=formula,
        matched_standard=matched_std,
        segments=tuple(resolved_segments),
        signed_codes=signed,
        resolved_from=RESOLVED_FROM_REPORT if any_from_report else RESOLVED_FROM_FALLBACK,
        diagnostics=diagnostics,
    )


__all__ = [
    "I_CYCLE_EXPECTED_NAMES",
    "I_CYCLE_PROFIT_LOSS",
    "I_CYCLE_ROW_CODES",
    "I_CYCLE_SEGMENTS",
    "ICycleAccounts",
    "ISegmentAccounts",
    "ISegmentSpec",
    "SEGMENT_AMORTIZATION",
    "SEGMENT_COST",
    "SEGMENT_EXPENSE",
    "SEGMENT_IMPAIRMENT",
    "build_name_lookup",
    "claim_segments",
    "detect_chart_conflict",
    "resolve_i_cycle_accounts",
    "resolve_row_code",
    "row_name_matches",
    "static_chart_names",
]
