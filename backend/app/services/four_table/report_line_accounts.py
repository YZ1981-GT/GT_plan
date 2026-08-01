"""报表映射规则驱动的科目定位（跨循环共享）。

**为什么不能硬编码科目前缀**

四表库入库后的科目关系是三层，DB 只读实证如下::

    tb_balance.account_code             客户**原始码**（点号分级）  1221 / 1221.12 / 1231.03
            │  account_mapping(project_id, original_account_code → standard_account_code)
            ▼
    trial_balance.standard_account_code **标准码**（横杠分级）      1221 / 1231-03 / 1131
            │  report_config.formula（按 applicable_standard）
            ▼
    报表行
      BS-005 应收票据   soe_standalone: TB('1121','期末余额') - TB('1231-01','期末余额')
      BS-009 其他应收款 soe_standalone: TB('1221','期末余额') - TB('1231-03','期末余额')
                                        + TB('1131','期末余额')

即客户把各类应收款的坏账分别编在 `1231.01/.02/.03/.05`，平台标准码是 `1231-01/-02/-03/-05`，
报表公式引用的正是这些**细分标准码** —— 所以备抵科目必须由报表规则映射解析，而不是拿
`1231` 宽前缀一把抓（实测项目 `0ec33ac9`：整个 `1231` 期末 28,464,225.16，其中
26,401,719.77 属**应收账款**；其他应收款真值仅 `1231.03` 的 900,217.36 → 虚增 31.6 倍）。

同时 `tb_balance` 存的是**原始码**，故解析出标准码后还须经 `account_mapping` 反解回该项目
的原始码集合，才能正确前缀匹配（`1231-03` 直接当前缀匹配不到 `1231.03`）。

**fail-open 铁律**：任一环失败（report_config 无该行 / account_chart 空 / account_mapping
空 / DB 异常）一律回退到调用方给的兜底码，并在 `resolved_from` 标注来源，绝不阻断 render。

本模块由 `d_cycle_extraction/d1_account_resolver`（D1）与
`wp_render_strategies/_k1_other_receivables`（K1）共同消费。

spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/
      Requirements 1.1~1.6 / Property 2, 3, 10
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field

import sqlalchemy as sa

from app.services.report_account_mapping import resolve_report_line_account_codes

logger = logging.getLogger(__name__)

#: 备抵科目名称判定关键字（`account_chart.account_name`）
_PROVISION_NAME_HINTS = ("坏账准备", "减值准备", "信用减值")

#: 备抵科目码族兜底（`account_chart` 不可用时的启发判定）：1231 = 坏账准备
_PROVISION_CODE_PREFIXES = ("1231",)

RESOLVED_FROM_REPORT = "report_config"
RESOLVED_FROM_FALLBACK = "fallback"

#: 带符号提取 `TB('code',...)` / `SUM_TB('a~b',...)` —— 捕获前置运算符供报表口径求和
_SIGNED_TB_RE = re.compile(r"([+\-]?)\s*(?:SUM_)?TB\('([^']+)'")


@dataclass(frozen=True)
class ReportLineAccountSpec:
    """某报表行的科目定位规格（调用方声明，纯数据）。

    Attributes:
        row_code: 报表行次编码（如其他应收款 ``BS-009``）。
        fallback_gross: 原值兜底**标准码**（报表映射解析失败时用）。
        fallback_provision: 备抵兜底**标准码**。
        provision_row_code: 备抵科目**独立报表行**编码（可选）。用于「备抵不在原值行公式里、
            而是自成一行」的循环 —— 实证 G7：``BS-024 长期股权投资 = TB('1511','期末余额')``
            不引用备抵，减值准备是独立行 ``IMP-009 八、长期股权投资减值准备 =
            TB('1512','期末余额')``。设了本字段时，仅当 `row_code` 的公式**没解析出备抵码**
            才去解析它；解析成功则 `provision_resolved_from='report_config'` 且
            `provision_exact` 由 `account_mapping` 反解决定。默认 ``None`` = 与本字段
            引入前逐字等价（D1/K1/K2/F1 等既有消费者零回归）。
        provision_name_filter: 备抵侧名称过滤词；仅当反解退化为宽前缀
            （无 `account_mapping` 记录）时由调用方叠加，防把其它科目的坏账算进来。
        extra_standard_codes: 报表公式**未必引用**但底稿需要单列的科目标准码
            （如 K1-1「与经审计的财务报表核对」区要单列 ``1131`` 应收股利 /
            ``1132`` 应收利息）。它们不并入 `gross`，单独放 `extra`。
    """

    row_code: str
    fallback_gross: tuple[str, ...] = ()
    fallback_provision: tuple[str, ...] = ()
    provision_row_code: str | None = None
    provision_name_filter: str | None = None
    extra_standard_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReportLineAccounts:
    """科目定位结果。

    Attributes:
        gross: 原值科目 —— **原始码**前缀集（用于 `tb_balance` / `tb_aux_balance`）。
        provision: 备抵科目 —— 原始码前缀集。
        gross_standard: 原值科目 —— **标准码**集（用于 `trial_balance`）。
        provision_standard: 备抵科目 —— 标准码集。
        extra: ``{标准码: [原始码前缀, ...]}``（`spec.extra_standard_codes` 的反解结果）。
        provision_exact: 备抵标准码是否**精确**反解出原始码（有 `account_mapping` 记录）。
            为 ``False`` 时前缀比标准码更宽（`1231-03` → `1231`），调用方必须叠名称过滤。
        signed_codes: ``[(标准码, +1|-1), ...]`` —— 报表公式里各 `TB()` 的符号，
            供「报表口径合计」按公式符号加权求和（Property 10）。公式缺失时为空。
        formula: 命中的报表公式原文（溯源展示用；无则 ``None``）。
        resolved_from: `report_config`（报表映射解析成功）或 `fallback`（兜底）。
        provision_resolved_from: 备抵侧单独标注（报表公式可能只引用原值）。
    """

    gross: list[str] = field(default_factory=list)
    provision: list[str] = field(default_factory=list)
    gross_standard: list[str] = field(default_factory=list)
    provision_standard: list[str] = field(default_factory=list)
    extra: dict[str, list[str]] = field(default_factory=dict)
    signed_codes: list[tuple[str, int]] = field(default_factory=list)
    formula: str | None = None
    row_code: str = ""
    resolved_from: str = RESOLVED_FROM_FALLBACK
    provision_resolved_from: str = RESOLVED_FROM_FALLBACK
    provision_exact: bool = False
    #: 备抵独立报表行（`spec.provision_row_code` 命中时才非空），供溯源展示
    provision_row_code: str = ""
    provision_formula: str | None = None

    @property
    def use_provision_name_filter(self) -> bool:
        """备抵侧是否需要叠加名称过滤（**保守口径**，与 D1 既有行为逐字等价）。

        报表映射已把备抵精确到 `1231-03`（该标准码语义就是「坏账准备-其他应收款」），
        再叠名称过滤会把客户命名不含关键字的子科目误杀 → 只有 fallback（拿的是宽口径
        `1231` 前缀）才需要名称过滤把其它应收科目的坏账剔掉。

        🔴 注意 ``provision_resolved_from`` 为 ``fallback`` 有**两种**成因：
        ① 报表公式没引用备抵科目（listed 侧 BS-009 即如此）；② `account_mapping`
        反解退化为宽前缀。只有 ② 才真正需要名称过滤 —— 需要精确判定的调用方请读
        :attr:`provision_exact`（``False`` 才是真的宽前缀）。本属性保留保守口径以
        保证 D1 零回归。
        """
        return self.provision_resolved_from == RESOLVED_FROM_FALLBACK

    def sign_of(self, standard_code: str) -> int:
        """该标准码在报表公式中的符号（未出现返 ``0``）。"""
        for code, sign in self.signed_codes:
            if code == standard_code:
                return sign
        return 0

    def as_dict(self) -> dict:
        """供 render 输出 `tb_source_codes`（取数溯源，前端展示）。"""
        out = asdict(self)
        out["signed_codes"] = [[c, s] for c, s in self.signed_codes]
        out["use_provision_name_filter"] = self.use_provision_name_filter
        return out


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（可独立单测，无 DB）
# ─────────────────────────────────────────────────────────────────────────────


def normalize_standard_prefix(code: str) -> str:
    """标准码 → 可直接前缀匹配 `tb_balance` 的兜底前缀。

    平台标准码用 `-` 分级（`1231-03`），客户原始码用 `.` 分级（`1231.03`），
    故无 `account_mapping` 时取标准码的**一级科目段**作前缀（`1231-03` → `1231`）。
    区间码（`1401~1499`）原样返回（由调用方按区间语义处理）。
    """
    c = (code or "").strip()
    if not c or "~" in c:
        return c
    return c.split("-")[0].strip() or c


def minimal_prefix_set(codes) -> list[str]:
    """取极小前缀集：若 ``a`` 是 ``b`` 的前缀则丢弃 ``b``（前缀匹配时 ``a`` 已覆盖 ``b``）。

    多个原始码可映射到同一标准码（`1221` / `1221.11` / `1221.12` → `1221`），
    不去重会让同一叶子被多个前缀重复覆盖。
    """
    uniq = sorted({(c or "").strip() for c in (codes or [])} - {""})
    out: list[str] = []
    for c in uniq:
        if any(c != o and c.startswith(o) for o in uniq):
            continue
        out.append(c)
    return out


def extract_signed_codes(formula: str | None) -> list[tuple[str, int]]:
    """从报表公式提取 ``[(标准码, 符号), ...]``（首项无运算符视为 ``+``）。

    ``TB('1221','期末余额') - TB('1231-03','期末余额') + TB('1131','期末余额')``
    → ``[('1221', 1), ('1231-03', -1), ('1131', 1)]``
    """
    if not formula:
        return []
    out: list[tuple[str, int]] = []
    seen: set[str] = set()
    for op, code in _SIGNED_TB_RE.findall(formula):
        c = (code or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        out.append((c, -1 if op == "-" else 1))
    return out


def _is_provision_code(
    code: str,
    name_by_code: dict[str, str],
    direction_by_code: dict[str, str],
) -> bool:
    """单码备抵判定：方向为贷方，或科目名含备抵关键字，或落在备抵码族。"""
    c = (code or "").strip()
    if not c:
        return False
    if (direction_by_code.get(c) or "").strip().lower() == "credit":
        return True
    name = name_by_code.get(c) or ""
    if any(h in name for h in _PROVISION_NAME_HINTS):
        return True
    return any(c.startswith(p) for p in _PROVISION_CODE_PREFIXES)


def split_gross_provision(
    codes: list[str],
    chart_rows: list[dict] | None = None,
) -> tuple[list[str], list[str]]:
    """把报表公式解析出的标准码集拆为 (原值码集, 备抵码集)。纯函数。

    判定优先级：`account_chart.direction == 'credit'` → 科目名含「坏账准备/减值准备/
    信用减值」→ 码族前缀 `1231`。三者皆不命中即归原值。

    Args:
        codes: 标准码集（`resolve_report_line_account_codes` 的返回值）。
        chart_rows: ``[{"account_code","account_name","direction"}, ...]``（source='standard'）。

    Returns:
        ``(gross, provision)``。两集合无交集，并集 == 去重后的 ``codes``（保持入参顺序）。
    """
    rows = chart_rows or []

    def _get(row, key: str) -> str:
        # 容忍 dict（生产路径 `fetch_standard_chart_rows` 的输出）与 ORM Row /
        # SimpleNamespace（测试与其它调用方常用）两种形态
        v = row.get(key) if isinstance(row, dict) else getattr(row, key, None)
        return str(v or "").strip()

    name_by_code = {_get(r, "account_code"): _get(r, "account_name") for r in rows}
    direction_by_code = {_get(r, "account_code"): _get(r, "direction") for r in rows}
    gross: list[str] = []
    provision: list[str] = []
    seen: set[str] = set()
    for raw in codes or []:
        c = (raw or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        if _is_provision_code(c, name_by_code, direction_by_code):
            provision.append(c)
        else:
            gross.append(c)
    return gross, provision


# ─────────────────────────────────────────────────────────────────────────────
# DB 访问（全程 fail-open）
# ─────────────────────────────────────────────────────────────────────────────


async def fetch_applicable_standards(ctx) -> list[str]:
    """取该项目的适用准则列表（`derive_applicable_standards` 口径）。失败返 ``[]``。

    🔴 必须按准则挑公式：实证 `BS-009` 在 `soe_standalone` 下是
    ``TB('1221') - TB('1231-03') + TB('1131')``（净额口径含坏账），而 `listed_*` /
    `soe_consolidated` 只有 ``TB('1221')``。不按准则匹配时
    `resolve_report_line_account_codes` 的 `LIMIT 1`（无 `ORDER BY`）会任取一条，
    备抵科目随行序丢失。
    """
    try:
        from app.services.standard_unification_service import derive_applicable_standards

        row = (
            await ctx.db.execute(
                sa.text("SELECT applicable_standard_v2 FROM projects WHERE id = :pid"),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        raw = getattr(row, "applicable_standard_v2", None) if row is not None else None
        return list(derive_applicable_standards(raw if isinstance(raw, dict) else None))
    except Exception as e:  # noqa: BLE001 — 准则未知则退回「任取一条配置」路径
        logger.debug("科目解析: 适用准则派生失败（不按准则匹配）: %s", e)
        return []


async def fetch_standard_chart_rows(ctx) -> list[dict]:
    """取该项目的标准科目表行（source='standard'），供备抵方向判定。失败返 ``[]``。"""
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT account_code, account_name, direction FROM account_chart "
                "WHERE project_id = :pid AND source = 'standard' AND is_deleted = false"
            ),
            {"pid": str(ctx.project_id)},
        )
        return [
            {
                "account_code": (r.account_code or "").strip(),
                "account_name": (r.account_name or "").strip(),
                "direction": (r.direction or "").strip(),
            }
            for r in result.fetchall()
        ]
    except Exception as e:  # noqa: BLE001 — 方向判定失败降级为码族启发
        logger.debug("科目解析: account_chart 查询失败（降级码族启发）: %s", e)
        return []


async def to_original_codes(ctx, standard_codes: list[str]) -> list[str]:
    """标准码集 → 该项目的**原始码**前缀集（经 `account_mapping` 反解）。"""
    codes, _exact = await to_original_codes_with_flag(ctx, standard_codes)
    return codes


async def to_original_codes_with_flag(
    ctx, standard_codes: list[str]
) -> tuple[list[str], bool]:
    """同 :func:`to_original_codes`，另返回「是否精确反解」标志。

    ``exact=False`` 表示退化为 :func:`normalize_standard_prefix` 兜底 —— 此时前缀
    **比标准码更宽**（`1231-03` → `1231` 会把应收票据/应收账款的坏账一并纳入），
    调用方必须叠加名称过滤。
    """
    fallback = []
    for c in standard_codes or []:
        p = normalize_standard_prefix(c)
        if p and p not in fallback:
            fallback.append(p)
    if not standard_codes:
        return fallback, False
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT DISTINCT original_account_code FROM account_mapping "
                "WHERE project_id = :pid AND is_deleted = false "
                "AND standard_account_code = ANY(:codes)"
            ),
            {"pid": str(ctx.project_id), "codes": list(standard_codes)},
        )
        originals = sorted(
            {(r.original_account_code or "").strip() for r in result.fetchall()} - {""}
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("科目解析: account_mapping 反解失败（用标准码前缀兜底）: %s", e)
        return fallback, False
    if not originals:
        return fallback, False
    minimal = minimal_prefix_set(originals)
    return (minimal, True) if minimal else (fallback, False)


async def _fetch_formula(ctx, row_code: str, standards: list[str]) -> str | None:
    """取命中的报表公式原文（溯源 + 符号提取用）。失败返 ``None``。

    与 `resolve_report_line_account_codes` 同优先级：项目级 → 按准则 → 任取一条。
    """
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
        logger.debug("科目解析: 报表公式原文查询失败: %s", e)
    return None


async def resolve_report_line_accounts(
    ctx, spec: ReportLineAccountSpec
) -> ReportLineAccounts:
    """解析某报表行的原值 / 备抵 / 附加科目（报表规则映射驱动，全程 fail-open）。

    Returns:
        :class:`ReportLineAccounts`；任一环失败均返回可用结果（用 ``spec`` 的兜底码），
        ``resolved_from`` 标注实际来源。``gross`` 恒非空（Property 3）。
    """
    standards: list[str] = []
    codes: list[str] = []
    try:
        standards = await fetch_applicable_standards(ctx)
        # 🔴 fallback 传空列表而非 spec 兜底码：`resolve_report_line_account_codes`
        # 在无配置时原样返回 fallback，若传兜底码就无法区分「真从公式解析出来」与「回退」。
        codes = list(
            await resolve_report_line_account_codes(
                ctx.db,
                ctx.project_id,
                spec.row_code,
                fallback=[],
                applicable_standards=standards,
            )
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("科目解析: 报表映射解析失败（用兜底科目）: %s", e)
        codes = []

    formula = await _fetch_formula(ctx, spec.row_code, standards)
    signed = extract_signed_codes(formula)

    chart_rows = await fetch_standard_chart_rows(ctx)
    gross_std, provision_std = split_gross_provision(codes, chart_rows)

    # 附加科目（如 1131/1132）不参与原值口径 —— 从 gross 里摘出去单列
    extra_std = [c for c in (spec.extra_standard_codes or ()) if c]
    if extra_std:
        gross_std = [c for c in gross_std if c not in set(extra_std)]

    # 两侧各自标注来源：报表公式可能只引用原值（实证 listed 侧 BS-009 =
    # TB('1221','期末余额') 未减坏账）→ 备抵侧补兜底标准码，该侧口径退化为 fallback。
    gross_from = RESOLVED_FROM_REPORT if gross_std else RESOLVED_FROM_FALLBACK

    # 备抵自成一行的循环（实证 G7：IMP-009 八、长期股权投资减值准备）：原值行公式没引用
    # 备抵时，改从独立报表行解析，避免把 `1512` 这类科目码写死成兜底字面量。
    provision_formula: str | None = None
    if not provision_std and spec.provision_row_code:
        try:
            imp_codes = list(
                await resolve_report_line_account_codes(
                    ctx.db,
                    ctx.project_id,
                    spec.provision_row_code,
                    fallback=[],
                    applicable_standards=standards,
                )
            )
        except Exception as e:  # noqa: BLE001 — 解析失败回退 fallback_provision
            logger.debug("科目解析: 备抵报表行 %s 解析失败: %s", spec.provision_row_code, e)
            imp_codes = []
        if imp_codes:
            # 备抵行公式里的码一律按备抵处理（该行语义即备抵），不再过 split_gross_provision
            provision_std = imp_codes
            provision_formula = await _fetch_formula(ctx, spec.provision_row_code, standards)

    provision_from = RESOLVED_FROM_REPORT if provision_std else RESOLVED_FROM_FALLBACK
    if not gross_std:
        gross_std = list(spec.fallback_gross)
    if not provision_std:
        provision_std = list(spec.fallback_provision)

    gross, _gross_exact = await to_original_codes_with_flag(ctx, gross_std)
    provision, provision_exact = await to_original_codes_with_flag(ctx, provision_std)

    # 🔴 反解退化为宽前缀时备抵侧必须叠名称过滤：标准码 `1231-03` 的兜底前缀是
    # `1231`，会把应收票据(1231.01)/应收账款(1231.02) 的坏账一并纳入。
    if not provision_exact:
        provision_from = RESOLVED_FROM_FALLBACK

    extra: dict[str, list[str]] = {}
    for code in extra_std:
        originals, _ = await to_original_codes_with_flag(ctx, [code])
        extra[code] = originals or [normalize_standard_prefix(code)]

    return ReportLineAccounts(
        gross=gross or [normalize_standard_prefix(c) for c in spec.fallback_gross],
        provision=provision
        or [normalize_standard_prefix(c) for c in spec.fallback_provision],
        gross_standard=gross_std,
        provision_standard=provision_std,
        extra=extra,
        signed_codes=signed,
        formula=formula,
        row_code=spec.row_code,
        resolved_from=gross_from,
        provision_resolved_from=provision_from,
        provision_exact=provision_exact,
        provision_row_code=(
            spec.provision_row_code or "" if provision_formula is not None else ""
        ),
        provision_formula=provision_formula,
    )


__all__ = [
    "RESOLVED_FROM_FALLBACK",
    "RESOLVED_FROM_REPORT",
    "ReportLineAccountSpec",
    "ReportLineAccounts",
    "extract_signed_codes",
    "fetch_applicable_standards",
    "fetch_standard_chart_rows",
    "minimal_prefix_set",
    "normalize_standard_prefix",
    "resolve_report_line_accounts",
    "split_gross_provision",
    "to_original_codes",
    "to_original_codes_with_flag",
]
