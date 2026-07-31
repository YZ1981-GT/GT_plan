"""D1 应收票据科目定位 —— 报表规则映射驱动（替代硬编码科目前缀）.

spec: .kiro/specs/d1-extraction-chain-completion/
      (Requirements 1.1~1.6 / Property 1, 2, 3)

**为什么不能硬编码 `1121` / `1231` + 名称含「应收票据」**

四表库入库后的科目关系是三层，实证（DB 只读核查）如下::

    tb_balance.account_code          = 客户**原始码**   1121 / 1121.01 / 1231.01
            │  account_mapping(project_id, original_account_code → standard_account_code)
            ▼
    trial_balance.standard_account_code = **标准码**     1121 / 1231-01
            │  report_config.formula（按 applicable_standard）
            ▼
    报表行 BS-005「应收票据」
       soe_standalone       : TB('1121','期末余额') - TB('1231-01','期末余额')
       listed_* / soe_consol: TB('1121','期末余额')

即客户把「坏账准备_应收票据」编在 `1231.01`，平台标准码是 `1231-01`，而 `soe_standalone`
的 BS-005 公式正是引用 `1231-01` —— 所以**坏账科目应由报表规则映射解析，而不是名称猜测**。
名称猜测在客户科目命名不含「应收票据」（如「坏账准备_票据」）时会静默取不到数。

同时 `tb_balance` 存的是**原始码**，故解析出标准码后还须经 `account_mapping` 反解回该项目
的原始码集合，才能正确前缀匹配（`1231-01` 直接当前缀匹配不到 `1231.01`）。

**fail-open 铁律**：任一环失败（report_config 无该行 / account_chart 空 / account_mapping
空 / DB 异常）一律回退到与改动前等价的行为（`1121` 原值 + `1231` 坏账前缀），并在
`resolved_from` 标注来源，绝不阻断 render。
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

import sqlalchemy as sa

from app.services.report_account_mapping import resolve_report_line_account_codes

logger = logging.getLogger(__name__)

# 报表行次（DB 实证：listed_standalone / listed_consolidated / soe_standalone /
# soe_consolidated 四个准则的「应收票据」行 row_code 均为 BS-005）
D1_REPORT_ROW_CODE = "BS-005"

# 兜底科目（标准码口径）：原值 1121、坏账准备 1231-01
D1_FALLBACK_GROSS = "1121"
D1_FALLBACK_PROVISION = "1231-01"
D1_FALLBACK_CODES = [D1_FALLBACK_GROSS, D1_FALLBACK_PROVISION]

# 备抵科目名称判定关键字（account_chart.account_name）
_PROVISION_NAME_HINTS = ("坏账准备", "减值准备", "信用减值")

# 备抵科目码族兜底（account_chart 不可用时的启发判定）：1231 = 坏账准备
_PROVISION_CODE_PREFIXES = ("1231",)

# 坏账侧名称过滤（仅在 fallback 口径下叠加，防把应收账款/其他应收款坏账算进 D1）
D1_PROVISION_NAME_FILTER = "应收票据"

RESOLVED_FROM_REPORT = "report_config"
RESOLVED_FROM_FALLBACK = "fallback"


@dataclass(frozen=True)
class D1AccountCodes:
    """D1 科目定位结果。

    Attributes:
        gross: 原值科目 —— **原始码**前缀集（用于 `tb_balance` / `tb_aux_balance`）。
        provision: 坏账准备科目 —— 原始码前缀集。
        gross_standard: 原值科目 —— **标准码**集（用于 `trial_balance`）。
        provision_standard: 坏账准备科目 —— 标准码集。
        resolved_from: `report_config`（报表规则映射解析成功）或 `fallback`（兜底）。
    """

    gross: list[str] = field(default_factory=list)
    provision: list[str] = field(default_factory=list)
    gross_standard: list[str] = field(default_factory=list)
    provision_standard: list[str] = field(default_factory=list)
    resolved_from: str = RESOLVED_FROM_FALLBACK
    provision_resolved_from: str = RESOLVED_FROM_FALLBACK

    @property
    def use_provision_name_filter(self) -> bool:
        """坏账侧是否需要叠加名称过滤。

        报表映射已把坏账精确到 `1231-01`（该标准码语义就是「坏账准备-应收票据」），
        再叠名称过滤会把客户命名不含「应收票据」的子科目误杀 → 只有 fallback
        （拿的是宽口径 `1231` 前缀）才需要名称过滤把其它应收科目的坏账剔掉。
        """
        return self.provision_resolved_from == RESOLVED_FROM_FALLBACK

    def as_dict(self) -> dict:
        """供 render 输出 `tb_source_codes`（取数溯源，前端展示）。"""
        return asdict(self)


def normalize_standard_prefix(code: str) -> str:
    """标准码 → 可直接前缀匹配 `tb_balance` 的兜底前缀。

    平台标准码用 `-` 分级（`1231-01`），客户原始码用 `.` 分级（`1231.01`），
    故无 `account_mapping` 时取标准码的**一级科目段**作前缀（`1231-01` → `1231`）。
    区间码（`1401~1499`）原样返回（由调用方按区间语义处理，D1 不涉及）。
    """
    c = (code or "").strip()
    if not c or "~" in c:
        return c
    return c.split("-")[0].strip() or c


def _is_provision_code(code: str, name_by_code: dict[str, str], direction_by_code: dict[str, str]) -> bool:
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
        chart_rows: `[{"account_code","account_name","direction"}, ...]`（source='standard'）。

    Returns:
        `(gross, provision)`。两集合无交集，并集 == 去重后的 `codes`（保持入参顺序）。
    """
    rows = chart_rows or []
    name_by_code = {
        str(r.get("account_code") or "").strip(): str(r.get("account_name") or "")
        for r in rows
    }
    direction_by_code = {
        str(r.get("account_code") or "").strip(): str(r.get("direction") or "")
        for r in rows
    }
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


async def _fetch_applicable_standards(ctx) -> list[str]:
    """取该项目的适用准则列表（`derive_applicable_standards` 口径）。失败返 []。

    🔴 必须按准则挑公式：实证 `BS-005` 在 `soe_standalone` 下是
    `TB('1121','期末余额') - TB('1231-01','期末余额')`（含坏账），而 `listed_*` /
    `soe_consolidated` 只有 `TB('1121','期末余额')`。不按准则匹配时
    `resolve_report_line_account_codes` 的 `LIMIT 1`（无 ORDER BY）会任取一条，
    坏账科目随行序丢失 —— 真实项目 0ec33ac9（soe_standalone）实测即命中该问题。
    """
    try:
        from app.services.standard_unification_service import derive_applicable_standards

        row = (
            await ctx.db.execute(
                sa.text(
                    "SELECT applicable_standard_v2 FROM projects WHERE id = :pid"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        raw = getattr(row, "applicable_standard_v2", None) if row is not None else None
        return list(derive_applicable_standards(raw if isinstance(raw, dict) else None))
    except Exception as e:  # noqa: BLE001 — 准则未知则退回「任取一条配置」路径
        logger.debug("D1 科目解析: 适用准则派生失败（不按准则匹配）: %s", e)
        return []


async def _fetch_standard_chart_rows(ctx) -> list[dict]:
    """取该项目的标准科目表行（source='standard'），供备抵方向判定。失败返 []。"""
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
        logger.debug("D1 科目解析: account_chart 查询失败（降级码族启发）: %s", e)
        return []


async def to_original_codes(ctx, standard_codes: list[str]) -> list[str]:
    """标准码集 → 该项目的**原始码**前缀集（经 `account_mapping` 反解）。

    多个原始码可映射到同一标准码（`1121` / `1121.01` / `1121.02` / `1121.03` → `1121`），
    此时返回**最短的那些**（互不为前缀的极小集），避免同一叶子被多个前缀重复覆盖。

    无映射记录 / 查询异常 → `normalize_standard_prefix` 兜底（等价改动前行为）。
    """
    codes, _exact = await _to_original_codes_with_flag(ctx, standard_codes)
    return codes


async def _to_original_codes_with_flag(
    ctx, standard_codes: list[str]
) -> tuple[list[str], bool]:
    """同 `to_original_codes`，另返回「是否精确反解」标志。

    `exact=False` 表示退化为 `normalize_standard_prefix` 兜底 —— 此时前缀**比标准码更宽**
    （`1231-01` → `1231` 会把应收账款/其他应收款的坏账一并纳入），调用方必须叠加名称过滤。
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
        logger.debug("D1 科目解析: account_mapping 反解失败（用标准码前缀兜底）: %s", e)
        return fallback, False
    if not originals:
        return fallback, False
    # 取极小前缀集：若 a 是 b 的前缀则丢弃 b（前缀匹配时 a 已覆盖 b）
    minimal: list[str] = []
    for c in originals:
        if any(c != o and c.startswith(o) for o in originals):
            continue
        if c not in minimal:
            minimal.append(c)
    return (minimal, True) if minimal else (fallback, False)


async def resolve_d1_account_codes(ctx) -> D1AccountCodes:
    """解析 D1 原值 / 坏账准备科目（报表规则映射驱动，全程 fail-open）。

    Returns:
        `D1AccountCodes`；任一环失败均返回可用结果（兜底 `1121` / `1231`），
        `resolved_from` 标注实际来源。`gross` 恒非空（Property 1）。
    """
    # 🔴 fallback 传空列表而非 D1_FALLBACK_CODES：`resolve_report_line_account_codes`
    # 在无配置时原样返回 fallback，若传兜底码就无法区分「真从公式解析出来」与「回退」
    # （soe_standalone 的 BS-005 公式恰好解析出 ['1121','1231-01'] = 兜底值本身）。
    codes: list[str] = []
    try:
        standards = await _fetch_applicable_standards(ctx)
        codes = list(
            await resolve_report_line_account_codes(
                ctx.db,
                ctx.project_id,
                D1_REPORT_ROW_CODE,
                fallback=[],
                applicable_standards=standards,
            )
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("D1 科目解析: 报表映射解析失败（用兜底科目）: %s", e)
        codes = []

    chart_rows = await _fetch_standard_chart_rows(ctx)
    gross_std, provision_std = split_gross_provision(codes, chart_rows)

    # 两侧各自标注来源：报表公式可能只引用原值（实证 listed 侧 BS-005 =
    # TB('1121','期末余额') 未减坏账，与 soe_standalone 不一致）→ 坏账侧补兜底
    # 标准码，且该侧口径退化为 fallback（坏账取数仍叠名称过滤，等价改动前行为）。
    gross_from = RESOLVED_FROM_REPORT if gross_std else RESOLVED_FROM_FALLBACK
    provision_from = RESOLVED_FROM_REPORT if provision_std else RESOLVED_FROM_FALLBACK
    if not gross_std:
        gross_std = [D1_FALLBACK_GROSS]
    if not provision_std:
        provision_std = [D1_FALLBACK_PROVISION]

    gross, _gross_exact = await _to_original_codes_with_flag(ctx, gross_std)
    provision, provision_exact = await _to_original_codes_with_flag(ctx, provision_std)

    # 🔴 反解退化为宽前缀时坏账侧必须叠名称过滤：标准码 `1231-01` 的兜底前缀是
    # `1231`，会把应收账款(1231.02)/其他应收款(1231.03) 的坏账一并纳入 D1
    # （实测项目 2aa00f57 无 1231 映射记录即走到这条路径）。
    if not provision_exact:
        provision_from = RESOLVED_FROM_FALLBACK

    return D1AccountCodes(
        gross=gross or [D1_FALLBACK_GROSS],
        provision=provision or [normalize_standard_prefix(D1_FALLBACK_PROVISION)],
        gross_standard=gross_std,
        provision_standard=provision_std,
        resolved_from=gross_from,
        provision_resolved_from=provision_from,
    )
