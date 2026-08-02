"""语义驱动的**逐项目**科目定位（跨循环共享）。

**为什么不能靠标准码定位（`report_line_accounts` 之外还需要这一层）**

`report_line_accounts` 解决的是「备抵科目要从报表公式解析、不能拿宽前缀一把抓」。
但它拿到的是**标准码**，隐含假设「标准码在各项目一致、且客户科目能反解到它」。
DB 只读实证（2026-08-01，10 个项目）证明这个假设不成立::

    ① account_mapping 同一原始码在不同项目映射到不同标准码
         1532 未实现融资收益 → 1532 (3 项目)   vs → 1541 (2 项目)
         1525 投资性房地产累计折旧 → 1521 (1 项目，并入母科目) vs → 1525 (4 项目)
         1527 投资性房地产减值准备 → 1521 (1 项目)            vs → 1527 (3 项目)

    ② 平台标准科目表（account_chart source='standard'）本身各项目不一致
         4 个项目有 1519 / 2 个只到 1507 / 4 个完全没有这一族
         （项目 2aa00f57 只有 58 个标准科目）

    ③ 客户科目表（source='client'）里压根没有 1504~1507/1519
         唯一有投资类科目的项目用的是**旧准则** 1501 持有至到期投资 / 1503 可供出售金融资产

即：把 `1519`（或任何标准码）写进代码或 `report_config`，在**部分项目必然取空或取错**。

**本模块的定位链**

::

    报表行 / 语义槽（按科目「名称」声明，不写码）
        │  ① account_chart source='client'  按名称匹配  ← 客户真实在用的科目，最权威
        │  ② account_chart source='standard' 按名称匹配 ← 平台标准科目表
        │  ③ report_config 公式给的标准码（仅当它在本项目科目表里**确实存在**）
        │  ④ 调用方兜底码（同样要求在本项目科目表里存在）
        │  ⑤ 都不命中 → 返空（**宁缺勿造**，不取错）
        ▼
    原始码前缀集（→ tb_balance）+ 标准码集（→ trial_balance）

`report_config` 由此**降级为提示 + 冲突检测**：当它给的码与按名称定位的结果不一致时，
以名称结果为准，并在 :attr:`SemanticAccountResult.conflicts` 暴露供溯源面板告警
（实证 `report_config` 有 4 行错码：`BS-022`/`BS-025`/`BS-026` 连续偏移一位、
`IS-016` 与 `IS-017` 整整互换）。

**为什么只在一级科目层做名称匹配**

客户子科目名很随意（实测 `1531.01 押金` / `1531.02 借款` / `1531.03 担保` /
`6701.01 坏账` / `6702.01 坏账`），按名称匹配子科目会误命中；而**一级科目名是规范的**
（`1501 持有至到期投资` / `1503 可供出售金融资产` / `6701 资产减值损失` /
`6702 信用减值损失` 全部规范）。故只匹配一级科目（码内无 ``.``），
子科目由 `leaf_aggregation.filter_by_prefixes` 的点号前缀边界自动纳入。

**不可自动化的边界（调用方必须知道）**

客户仍在用旧准则 `1503 可供出售金融资产` 时，新准则下它会按业务模式与合同现金流量特征
（SPPI）拆分到「交易性金融资产 / 其他债权投资 / 其他权益工具投资」三处 —— 这是**会计判断**
（正是 G6-7 业务模式分析 / G6-8 合同现金流量特征分析底稿在做的事）。本模块
**不做这种跨准则推断**：旧准则科目名不在槽的 ``names`` 里就不命中，
由 :attr:`SemanticAccountResult.unmapped_candidates` 提示「本项目存在同族旧准则科目，
需人工映射」，交审计师在科目映射界面处理。

spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
      Requirements 1, 2 / Property 1~5
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field

import sqlalchemy as sa

logger = logging.getLogger(__name__)

#: 科目表来源优先级（客户真实在用的科目优先于平台标准表）
SOURCE_CLIENT = "client"
SOURCE_STANDARD = "standard"

RESOLVED_FROM_CLIENT_CHART = "account_chart_client"
RESOLVED_FROM_STANDARD_CHART = "account_chart_standard"
RESOLVED_FROM_REPORT_CONFIG = "report_config"
RESOLVED_FROM_FALLBACK = "fallback"
RESOLVED_FROM_NONE = "none"

#: 名称归一时剥离的字符（空格 / 全角空格 / 分隔符 / 各类括号）
_STRIP_CHARS = re.compile(r"[\s\u3000_\-—－/／、,，.．·:：;；()（）\[\]【】「」]")

#: 带符号提取 `TB('code',...)`（与 `report_line_accounts` 同口径）
_SIGNED_TB_RE = re.compile(r"([+\-]?)\s*(?:SUM_)?TB\('([^']+)'")


# ─────────────────────────────────────────────────────────────────────────────
# 声明式规格（调用方只写科目**名称**，不写码）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SemanticAccountSlot:
    """一个语义槽 —— 按科目名称在本项目科目表里定位实际科目码。

    Attributes:
        key: 输出键（如 ``gross`` / ``accum_dep``）。调用方据此取结果，须稳定。
        names: 候选科目名（按优先级）。**精确匹配（归一后相等）优先于包含匹配**。
        exclude_names: 否决词 —— 科目名含其一即排除。
            🔴 必填项，不是可选优化：`投资性房地产累计折旧` **包含** `投资性房地产`，
            无否决词时原值槽会把累计折旧一并纳入（与 G7 的
            `其他权益变动_不属于其他综合收益` 含 `其他综合收益` 同款陷阱）。
        fallback_standard_codes: 兜底**标准码**（仅当它在本项目科目表里确实存在时才用）。
        label: 中文展示名（溯源面板用；缺省取 ``names[0]``）。
        is_provision: 该槽是否为备抵性质（累计折旧 / 累计摊销 / 各类减值准备）。
            仅作元数据下发给前端决定展示口径（取绝对值 / 负号列示），本模块不据此改聚合。
    """

    key: str
    names: tuple[str, ...]
    exclude_names: tuple[str, ...] = ()
    fallback_standard_codes: tuple[str, ...] = ()
    label: str = ""
    is_provision: bool = False

    @property
    def display_label(self) -> str:
        return self.label or (self.names[0] if self.names else self.key)


@dataclass(frozen=True)
class SemanticAccountSpec:
    """某循环 / 某底稿的语义科目定位规格。

    Attributes:
        row_code: 报表行次编码（**提示 + 冲突检测**用，不是定位依据）。
            ``None`` 表示该科目在 `report_config` 里无独立报表行
            （实证：应收利息 `1132` 就没有 —— `BS-009` 的公式含 `1131` 不含 `1132`）。
        slots: 语义槽集合，顺序即展示顺序。
        legacy_standard_names: 同族**旧准则**科目名。命中时不并入任何槽，
            只放 ``unmapped_candidates`` 提示需人工映射（见模块 docstring 的边界说明）。
    """

    row_code: str | None
    slots: tuple[SemanticAccountSlot, ...]
    legacy_standard_names: tuple[str, ...] = ()


# ─────────────────────────────────────────────────────────────────────────────
# 结果
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolvedSlot:
    """单个语义槽的定位结果。

    Attributes:
        codes: **原始码**前缀集（用于 `tb_balance` / `tb_aux_balance`）。
        standard_codes: **标准码**集（用于 `trial_balance`）。
        matched: ``[(码, 科目名), ...]`` 命中明细（溯源展示）。
        resolved_from: 命中来源（``account_chart_client`` / ``account_chart_standard`` /
            ``report_config`` / ``fallback`` / ``none``）。
        exact: 名称是否**精确**命中（归一后相等）。``False`` 表示走了包含匹配，
            调用方展示时应提示审计师复核。
    """

    key: str
    label: str
    is_provision: bool = False
    codes: list[str] = field(default_factory=list)
    standard_codes: list[str] = field(default_factory=list)
    matched: list[tuple[str, str]] = field(default_factory=list)
    resolved_from: str = RESOLVED_FROM_NONE
    exact: bool = False

    @property
    def found(self) -> bool:
        return bool(self.codes or self.standard_codes)


@dataclass(frozen=True)
class SemanticAccountResult:
    """整个规格的定位结果（供 render 输出 `tb_source_codes`）。

    Attributes:
        slots: ``{slot_key: ResolvedSlot}``。
        row_code / formula: 报表行与其公式原文（溯源展示）。
        report_config_codes: 报表公式解析出的标准码（**仅提示**）。
        conflicts: ``[(slot_key, 报表码, 实际码)]`` —— 报表公式给的码与按名称定位的结果
            不一致。溯源面板据此渲染橙色告警。
        unmapped_candidates: ``[(码, 科目名)]`` —— 本项目存在的同族旧准则科目，
            需人工映射（本模块不猜跨准则拆分）。
        chart_available: 本项目科目表是否可用。``False`` 时全部槽退化为兜底码，
            调用方应提示「科目表未导入」而非「无该科目」。
    """

    slots: dict[str, ResolvedSlot] = field(default_factory=dict)
    row_code: str = ""
    formula: str | None = None
    report_config_codes: list[str] = field(default_factory=list)
    conflicts: list[tuple[str, str, str]] = field(default_factory=list)
    unmapped_candidates: list[tuple[str, str]] = field(default_factory=list)
    chart_available: bool = False

    def codes_of(self, key: str) -> list[str]:
        """某槽的原始码前缀集（无该槽返 ``[]``）。"""
        slot = self.slots.get(key)
        return list(slot.codes) if slot else []

    def standard_codes_of(self, key: str) -> list[str]:
        slot = self.slots.get(key)
        return list(slot.standard_codes) if slot else []

    def as_dict(self) -> dict:
        """序列化供 render 下发前端（`tb_source_codes`）。

        🔴 **含向后兼容的扁平投影**：`gross` / `gross_standard` / `provision` /
        `provision_standard` / `resolved_from` 由主槽（``gross`` / ``provision``）派生。

        平台既有前端契约（`composables/shared/tbSourceCodes.ts` 的 `TbSourceCodes`）
        对齐的是 `report_line_accounts.ReportLineAccounts.as_dict()` 的扁平形态，
        被 K1 / K2 / G1 / G5 / G6 / G7 / F1 与共享面板 `WpFourTableSourcePanel.vue`
        广泛消费。语义解析件若只发 `slots`，这些消费点会**静默读到 undefined**
        （TS 里 `html_data` 是 `any`，编译不报错）→ 溯源面板空白、查询口径退化为兜底码。
        故这里同时发扁平键，新增的 `slots` / `conflicts` / `unmapped_candidates` /
        `chart_available` 供新消费点使用。
        """
        gross = self.slots.get("gross")
        provision = self.slots.get("provision")
        return {
            # ── 向后兼容的扁平投影（勿删；改名必同步前端 TbSourceCodes 接口）──
            "row_code": self.row_code,
            "formula": self.formula,
            "gross": list(gross.codes) if gross else [],
            "gross_standard": list(gross.standard_codes) if gross else [],
            "provision": list(provision.codes) if provision else [],
            "provision_standard": list(provision.standard_codes) if provision else [],
            "resolved_from": gross.resolved_from if gross else RESOLVED_FROM_NONE,
            "provision_resolved_from": (
                provision.resolved_from if provision else RESOLVED_FROM_NONE
            ),
            "provision_exact": bool(provision.exact) if provision else False,
            # ── 语义解析专属 ──────────────────────────────────────────────
            "report_config_codes": list(self.report_config_codes),
            "conflicts": [list(c) for c in self.conflicts],
            "unmapped_candidates": [list(c) for c in self.unmapped_candidates],
            "chart_available": self.chart_available,
            "slots": {
                k: {
                    "key": v.key,
                    "label": v.label,
                    "is_provision": v.is_provision,
                    "codes": list(v.codes),
                    "standard_codes": list(v.standard_codes),
                    "matched": [list(m) for m in v.matched],
                    "resolved_from": v.resolved_from,
                    "exact": v.exact,
                    "found": v.found,
                }
                for k, v in self.slots.items()
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（无 DB，可独立单测）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolverContext:
    """解析器所需的**最小上下文**（供 service 层等非 `RenderContext` 调用方复用）。

    :func:`resolve_semantic_accounts` 只读 ``ctx.db`` 与 ``ctx.project_id``
    （`report_config` 公式查询另会读 ``ctx.project_id`` 组 ``project:`` 级键）。
    显式声明本类型比传 ``SimpleNamespace`` 更自证，也让静态检查能发现字段漂移。
    """

    db: object
    project_id: object
    year: int | None = None


@dataclass(frozen=True)
class ChartRow:
    """`account_chart` 单行的定位视图。"""

    account_code: str
    account_name: str
    source: str = ""
    direction: str = ""


def normalize_account_name(name: str) -> str:
    """科目名归一：去空格 / 下划线 / 各类分隔符与括号，全角数字字母转半角。

    ``投资性房地产_房屋建筑物`` → ``投资性房地产房屋建筑物``；
    ``其他应收款（其他）`` → ``其他应收款其他``。

    🔴 归一**不合并**父子名（``投资性房地产`` ≠ ``投资性房地产房屋建筑物``），
    精确匹配因此仍然可靠。
    """
    s = str(name or "")
    # 全角 → 半角（数字 / 字母 / 常见符号）
    s = "".join(
        chr(ord(ch) - 0xFEE0) if 0xFF01 <= ord(ch) <= 0xFF5E else ch for ch in s
    )
    return _STRIP_CHARS.sub("", s).strip().lower()


def is_top_level_code(code: str) -> bool:
    """是否一级科目（码内无点号）。名称匹配只在这一层做，见模块 docstring。"""
    c = str(code or "").strip()
    return bool(c) and "." not in c


def to_chart_rows(rows) -> list[ChartRow]:
    """把 SQLAlchemy Row / dict 序列归一为 :class:`ChartRow`。"""
    out: list[ChartRow] = []
    for r in rows or []:
        get = r.get if isinstance(r, dict) else (lambda k, _r=r: getattr(_r, k, None))
        code = str(get("account_code") or "").strip()
        if not code:
            continue
        out.append(
            ChartRow(
                account_code=code,
                account_name=str(get("account_name") or "").strip(),
                source=str(get("source") or "").strip(),
                direction=str(get("direction") or "").strip(),
            )
        )
    return out


def match_slot_in_chart(
    slot: SemanticAccountSlot,
    rows: list[ChartRow],
) -> tuple[list[ChartRow], bool]:
    """在一批科目表行里按名称匹配某个槽。纯函数。

    判定顺序：① 否决词过滤 → ② 归一后**精确**相等 → ③ 归一后**包含**。
    只考察一级科目（:func:`is_top_level_code`）。

    Returns:
        ``(命中行, 是否精确命中)``。无命中时 ``([], False)``。
    """
    cands = [r for r in rows or [] if is_top_level_code(r.account_code) and r.account_name]
    excludes = [normalize_account_name(x) for x in (slot.exclude_names or ()) if x]
    if excludes:
        cands = [
            r
            for r in cands
            if not any(ex and ex in normalize_account_name(r.account_name) for ex in excludes)
        ]
    if not cands:
        return [], False

    wanted = [normalize_account_name(n) for n in (slot.names or ()) if n]
    if not wanted:
        return [], False

    # ② 精确：按 names 声明顺序取第一个有命中的名字（可能多行同名，全取）
    for w in wanted:
        exact = [r for r in cands if normalize_account_name(r.account_name) == w]
        if exact:
            return _dedup_rows(exact), True

    # ③ 包含：科目名含候选名（宽松兜底，调用方展示时提示复核）
    for w in wanted:
        loose = [r for r in cands if w and w in normalize_account_name(r.account_name)]
        if loose:
            return _dedup_rows(loose), False
    return [], False


def _dedup_rows(rows: list[ChartRow]) -> list[ChartRow]:
    """按科目码去重并按码升序（同码多来源时保留首个）。"""
    seen: dict[str, ChartRow] = {}
    for r in rows:
        seen.setdefault(r.account_code, r)
    return [seen[k] for k in sorted(seen)]


def extract_formula_codes(formula: str | None) -> list[str]:
    """从报表公式提取标准码（保序去重）。与 `report_line_accounts` 同正则。"""
    if not formula:
        return []
    out: list[str] = []
    for _op, code in _SIGNED_TB_RE.findall(formula):
        c = (code or "").strip()
        if c and c not in out:
            out.append(c)
    return out


def find_legacy_candidates(
    spec: SemanticAccountSpec,
    rows: list[ChartRow],
    resolved_codes: set[str],
) -> list[tuple[str, str]]:
    """找出本项目存在但未被任何槽吸收的**旧准则同族科目**（需人工映射）。纯函数。"""
    wanted = [normalize_account_name(n) for n in (spec.legacy_standard_names or ()) if n]
    if not wanted:
        return []
    out: dict[str, str] = {}
    for r in rows or []:
        if not is_top_level_code(r.account_code) or r.account_code in resolved_codes:
            continue
        norm = normalize_account_name(r.account_name)
        if any(w and (norm == w or w in norm) for w in wanted):
            out[r.account_code] = r.account_name
    return [(k, out[k]) for k in sorted(out)]


def build_conflicts(
    slots: dict[str, ResolvedSlot],
    report_codes: list[str],
) -> list[tuple[str, str, str]]:
    """报表公式给的码 vs 按名称定位的实际码，逐槽比对差异。纯函数。

    只在「该槽确实定位到了标准码」且「报表码非空」时判定；
    报表码集合与实际标准码集合无交集时记为冲突（取实际码的首个作为对照展示）。
    """
    if not report_codes:
        return []
    out: list[tuple[str, str, str]] = []
    for key, slot in slots.items():
        actual = [c for c in slot.standard_codes if c]
        if not actual:
            continue
        if set(actual) & set(report_codes):
            continue
        # 该槽的实际码完全不在报表公式里 → 报表公式可能引错科目
        out.append((key, ",".join(report_codes), ",".join(actual)))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# DB 访问（全程 fail-open）
# ─────────────────────────────────────────────────────────────────────────────


async def fetch_project_chart(ctx) -> dict[str, list[ChartRow]]:
    """取本项目科目表，按 source 分桶。失败返 ``{}``（调用方退化为兜底码）。"""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT account_code, account_name, direction, source "
                "FROM account_chart WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )
        rows = to_chart_rows(result.fetchall())
    except Exception as e:  # noqa: BLE001 — 科目表不可用不阻断 render
        logger.debug("语义科目定位: account_chart 查询失败: %s", e)
        return {}
    out: dict[str, list[ChartRow]] = {}
    for r in rows:
        out.setdefault(r.source or "", []).append(r)
    return out


async def to_original_codes(ctx, standard_codes: list[str]) -> list[str]:
    """标准码 → 本项目**原始码**前缀集（`account_mapping` 反解）。失败/无记录返 ``[]``。

    与 `report_line_accounts.to_original_codes_with_flag` 的差别：本函数**不做**
    「退化为标准码一级段」的兜底 —— 本模块的定位起点已经是本项目实际存在的科目，
    退化兜底只会把不属于本项目的宽前缀塞回来。
    """
    codes = [c for c in (standard_codes or []) if c]
    if not codes:
        return []
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT DISTINCT original_account_code FROM account_mapping "
                "WHERE project_id = :pid AND is_deleted = false "
                "AND standard_account_code = ANY(:codes)"
            ),
            {"pid": str(ctx.project_id), "codes": codes},
        )
        return _minimal_prefixes(
            (r.original_account_code or "").strip() for r in result.fetchall()
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("语义科目定位: account_mapping 反解失败: %s", e)
        return []


async def to_standard_codes(ctx, original_codes: list[str]) -> list[str]:
    """原始码 → 本项目标准码集（`account_mapping` 正向查）。失败/无记录返 ``[]``。

    🔴 这一步不能省、也不能用「原始码即标准码」的假设：实证同一原始码
    `1525 投资性房地产累计折旧` 在 1 个项目映射到 `1521`（并入母科目）、
    在 4 个项目映射到 `1525`（独立）。
    """
    codes = [c for c in (original_codes or []) if c]
    if not codes:
        return []
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT DISTINCT standard_account_code FROM account_mapping "
                "WHERE project_id = :pid AND is_deleted = false "
                "AND (original_account_code = ANY(:codes) OR "
                "     EXISTS (SELECT 1 FROM unnest(CAST(:codes AS text[])) p "
                "             WHERE original_account_code LIKE p || '.%'))"
            ),
            {"pid": str(ctx.project_id), "codes": codes},
        )
        return sorted({(r.standard_account_code or "").strip() for r in result.fetchall()} - {""})
    except Exception as e:  # noqa: BLE001
        logger.debug("语义科目定位: account_mapping 正向查失败: %s", e)
        return []


def _minimal_prefixes(codes) -> list[str]:
    """取极小前缀集（``a`` 是 ``b`` 的点号前缀则丢弃 ``b``）。"""
    uniq = sorted({(c or "").strip() for c in codes} - {""})
    out: list[str] = []
    for c in uniq:
        if any(c != o and c.startswith(o + ".") for o in uniq):
            continue
        out.append(c)
    return out


async def _fetch_report_formula(ctx, row_code: str) -> str | None:
    """取报表公式原文（按准则优先级；仅作提示与冲突检测）。失败返 ``None``。"""
    try:
        from .report_line_accounts import fetch_applicable_standards

        standards = await fetch_applicable_standards(ctx)
    except Exception as e:  # noqa: BLE001
        logger.debug("语义科目定位: 准则派生失败: %s", e)
        standards = []
    queries: list[tuple[str, dict]] = [
        (
            "SELECT formula FROM report_config WHERE row_code = :rc "
            "AND applicable_standard = :std AND is_deleted = false LIMIT 1",
            {"rc": row_code, "std": f"project:{ctx.project_id}"},
        )
    ]
    queries += [
        (
            "SELECT formula FROM report_config WHERE row_code = :rc "
            "AND applicable_standard = :std AND is_deleted = false LIMIT 1",
            {"rc": row_code, "std": std},
        )
        for std in standards
        if std
    ]
    queries.append(
        (
            "SELECT formula FROM report_config WHERE row_code = :rc "
            "AND applicable_standard NOT LIKE 'project:%' AND is_deleted = false LIMIT 1",
            {"rc": row_code},
        )
    )
    try:
        for sql, params in queries:
            row = (await ctx.db.execute(sa.text(sql), params)).fetchone()
            if row is not None and row.formula:
                return str(row.formula)
    except Exception as e:  # noqa: BLE001
        logger.debug("语义科目定位: 报表公式查询失败: %s", e)
    return None


async def resolve_semantic_accounts(
    ctx, spec: SemanticAccountSpec
) -> SemanticAccountResult:
    """按语义槽逐项目定位科目（全程 fail-open）。

    定位优先级见模块 docstring。任一环失败都返回可用结果，
    并在 ``resolved_from`` / ``chart_available`` 标注实际来源。

    Returns:
        :class:`SemanticAccountResult`。本项目确实没有某科目时该槽 ``found`` 为 ``False``
        且 ``codes`` 为空 —— **调用方必须据此显示「本项目无此科目」而不是取 0**。
    """
    chart = await fetch_project_chart(ctx)
    chart_available = bool(chart)
    client_rows = chart.get(SOURCE_CLIENT, [])
    standard_rows = chart.get(SOURCE_STANDARD, [])
    all_codes = {r.account_code for rows in chart.values() for r in rows}

    formula = (
        await _fetch_report_formula(ctx, spec.row_code) if spec.row_code else None
    )
    report_codes = extract_formula_codes(formula)

    resolved: dict[str, ResolvedSlot] = {}
    consumed: set[str] = set()

    # 🔴 报表公式兜底（层③）**只对单槽规格生效**。
    #
    # 报表公式给的是**整条报表行**的科目集（如 `BS-002 货币资金` = 1001+1002+1012），
    # 把它整份分配给「按名称没匹配上的那个槽」在单槽规格下等价于「该行就这些科目」，
    # 但在多槽规格下会把**整行金额**塞进某个子项，属数字级错误。E1 真实 DB 实测：
    #
    # - `finance_co` / `digital` 本应 `found=False`（准则解释15号「可增设」，多数项目没有
    #   该科目，故 `fallback_standard_codes=()`），却各自拿到 `['1001','1002','1012']`
    #   → 「存放财务公司款项」「数字货币」两行都等于**货币资金全额**；
    # - 项目 `2aa00f57` 无「库存现金」→ `cash` 槽拿到 `['1002','1012']`
    #   → `total = cash + bank + other` 把 1002/1012 算两遍，
    #     货币资金合计 8,935,072.24 vs 真值 4,467,536.12（**虚增一倍**）。
    #
    # 同款风险在 G/H 循环是潜伏态：G1/G10 的 `derivative`（`fallback=()`）会拿到原值科目；
    # G4/G7 的 `provision` 与 H3 的 `accum_dep`/`accum_amort`/`impairment`
    # 会在层③就拿到**原值科目码**（备抵 == 原值）——层③排在层④之前，own fallback 用不上。
    #
    # 多槽规格下正确语义 = 槽要么按名称命中、要么用**自己声明的**兜底码（层④）、
    # 否则 `found=False` 由调用方显示「本项目无此科目」（宁缺勿造）。
    allow_report_config_tier = len(spec.slots) == 1

    for slot in spec.slots:
        # ① 客户科目表按名称
        rows, exact = match_slot_in_chart(slot, client_rows)
        source = RESOLVED_FROM_CLIENT_CHART
        # ② 平台标准科目表按名称
        if not rows:
            rows, exact = match_slot_in_chart(slot, standard_rows)
            source = RESOLVED_FROM_STANDARD_CHART
        # ③ 报表公式给的码（要求在本项目科目表里确实存在；仅单槽规格）
        if not rows and report_codes and allow_report_config_tier:
            hit = [c for c in report_codes if c in all_codes]
            if hit:
                by_code = {
                    r.account_code: r for rows_ in chart.values() for r in rows_
                }
                rows = [by_code[c] for c in hit if c in by_code]
                exact = False
                source = RESOLVED_FROM_REPORT_CONFIG
        # ④ 调用方兜底码（同样要求存在）
        if not rows and slot.fallback_standard_codes:
            hit = [c for c in slot.fallback_standard_codes if c in all_codes]
            if hit:
                by_code = {
                    r.account_code: r for rows_ in chart.values() for r in rows_
                }
                rows = [by_code[c] for c in hit if c in by_code]
                exact = False
                source = RESOLVED_FROM_FALLBACK
        # ⑤ 科目表整体不可用时才允许裸兜底码（否则宁缺勿造）
        if not rows and not chart_available and slot.fallback_standard_codes:
            resolved[slot.key] = ResolvedSlot(
                key=slot.key,
                label=slot.display_label,
                is_provision=slot.is_provision,
                codes=list(slot.fallback_standard_codes),
                standard_codes=list(slot.fallback_standard_codes),
                matched=[],
                resolved_from=RESOLVED_FROM_FALLBACK,
                exact=False,
            )
            continue
        if not rows:
            resolved[slot.key] = ResolvedSlot(
                key=slot.key,
                label=slot.display_label,
                is_provision=slot.is_provision,
                resolved_from=RESOLVED_FROM_NONE,
            )
            continue

        codes = _minimal_prefixes(r.account_code for r in rows)
        consumed.update(codes)
        if source == RESOLVED_FROM_CLIENT_CHART:
            # 客户码可直接前缀匹配 tb_balance；标准码经正向映射得到
            originals = codes
            standards = await to_standard_codes(ctx, codes) or []
        else:
            # 标准码需反解回本项目原始码；反解不到则保留标准码（同码惯例）
            standards = codes
            originals = await to_original_codes(ctx, codes) or list(codes)
        resolved[slot.key] = ResolvedSlot(
            key=slot.key,
            label=slot.display_label,
            is_provision=slot.is_provision,
            codes=originals,
            standard_codes=standards,
            matched=[(r.account_code, r.account_name) for r in rows],
            resolved_from=source,
            exact=exact,
        )

    all_rows = [r for rows in chart.values() for r in rows]
    return SemanticAccountResult(
        slots=resolved,
        row_code=spec.row_code or "",
        formula=formula,
        report_config_codes=report_codes,
        conflicts=build_conflicts(resolved, report_codes),
        unmapped_candidates=find_legacy_candidates(spec, all_rows, consumed),
        chart_available=chart_available,
    )


async def resolve_primary_code(ctx, spec: SemanticAccountSpec, slot_key: str = "gross") -> str:
    """取某槽在本项目的**主科目码**（供 render 下发 `account_code` 展示 / 事件载荷）。

    多码命中时取首个（升序）。本项目无该科目时返回 ``""`` —— **宁缺勿造**：
    展示空值比展示一个属于别的循环的科目码正确（实证 G4-ECL / G4-SPPI 曾下发
    ``1501 持有至到期投资``、G6-ECL 下发 ``1503 可供出售金融资产``）。

    ⚠️ 只用于**展示 / 元数据**。真正的取数请用 :func:`resolve_semantic_accounts`
    拿到完整的 `codes` / `standard_codes` 集合，别用单个码去前缀匹配。
    """
    try:
        result = await resolve_semantic_accounts(ctx, spec)
    except Exception as e:  # noqa: BLE001 — 展示字段不得阻断 render
        logger.debug("语义科目定位: 主科目码解析失败: %s", e)
        return ""
    codes = result.codes_of(slot_key)
    return codes[0] if codes else ""


__all__ = [
    "RESOLVED_FROM_CLIENT_CHART",
    "RESOLVED_FROM_FALLBACK",
    "RESOLVED_FROM_NONE",
    "RESOLVED_FROM_REPORT_CONFIG",
    "RESOLVED_FROM_STANDARD_CHART",
    "SOURCE_CLIENT",
    "SOURCE_STANDARD",
    "ChartRow",
    "ResolvedSlot",
    "ResolverContext",
    "SemanticAccountResult",
    "SemanticAccountSlot",
    "SemanticAccountSpec",
    "build_conflicts",
    "extract_formula_codes",
    "fetch_project_chart",
    "find_legacy_candidates",
    "is_top_level_code",
    "match_slot_in_chart",
    "normalize_account_name",
    "resolve_primary_code",
    "resolve_semantic_accounts",
    "to_chart_rows",
    "to_original_codes",
    "to_standard_codes",
]
