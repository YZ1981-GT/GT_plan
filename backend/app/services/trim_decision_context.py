# -*- coding: utf-8 -*-
"""程序裁剪三维判据上下文装配（只读）。

Feature: procedure-trimming-and-delegation-intelligence — Task 9
Requirements: 3.1, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.5, 5.6

本模块把「风险评估 → 重要性 → 数据存在性」三个法定裁剪判据 + 完整性豁免覆盖 +
底稿已录入探测**一次性**装配成前端决策内核的入参，**只读、不写库**。

═══ 设计约束（每条都有守卫，改动前先读 `backend/tests/procedure_trim/test_trim_decision_context.py`）═══

1. **任一维度取数失败 → 该维度置 ``None``/空 + 往 ``degradations`` 记一条**，不抛异常、
   不伪造默认值。``degradations`` 是前端摘要降级标注的**唯一来源**（Requirement 4.5 的
   前后一致性由此结构性保证 —— 前端不再自行判断"这个维度是不是空的"）。
2. **``performance_materiality`` 缺失但 ``overall_materiality`` 存在时不推算**
   （Requirement 4.6）。整体重要性是财报层面评价基准，不是"单科目要不要做程序"的门槛；
   按比例推算实际执行重要性属会计判断，代码不得代劳 ⇒ 整个重要性维度按缺失处理。
3. **返回值任何层级都不得出现 ``overall_materiality``**。否则"不推算"这条约束会从后端
   漏到前端（前端拿到整体重要性照样能自己乘个比例），Requirement 4.6 形同虚设。
4. **试算表不可用保持阻断语义**（Requirement 4.4）：三种成因都让 ``accounts`` 为空 ⇒
   前端决策内核拿不到金额 ⇒ 不裁。绝不能把「读不到」当「无数据」让前端全裁。

═══ accounts 维度的三态成因（对 spec 两态的**加法式细化**）═══

spec / Property 34 只要求区分 ``query_failed``（读取失败）与 ``not_imported``（未导入）
两态。本模块在此之上**additive** 增加第三态 ``no_material_accounts``，理由：

- 既有两个取数源都把「读取失败」塌进「未导入」 —— ``get_scope_accounts``
  （``routers/b50_scope.py``）异常时返回 ``summary="试算表未导入或查询失败"``；
  ``resolve_subject_data_availability``（``services/procedure_trim_scope.py``）异常时
  ``return {"tb_empty": True, ...}`` 并注释「查询失败：返回 tb_empty=True 让调用方
  fail-safe 不裁」。方向安全（都阻断），但产不出可区分的文案。
- 「试算表有行、但过滤后零个非零科目」是**真实业务事实**（数据已导入而全部科目金额为
  零，通常意味着导错年度/导错主体），不是"不可用"。把它塞进 ``not_imported`` 会重犯
  「把可用当不可用」的对称错误，且前端会提示"请先导入试算表"而用户明明已经导过。

三态**全部阻断裁剪**（AC 4.4 + Property 34）；差别只在前端文案方向：

| cause | 触发条件 | 前端应显示的方向 |
|---|---|---|
| ``query_failed`` | 取数抛异常 | 技术故障，建议重试 |
| ``not_imported`` | 查询成功但试算表零行 | 请先导入试算表 |
| ``no_material_accounts`` | 有行但过滤后零个非零科目 | 试算表已导入而全部科目金额为零，请核实数据 |

``cause`` 是 **accounts 维度专属**可选字段（裁决 2）：其余维度只有 ``dimension`` +
``reason``，防别的维度被顺手加上第二套成因码。

═══ 取数口径 ═══

**accounts 与 ``routers/b50_scope.get_scope_accounts`` 同口径，两处一改必须同改。**
该端点的取数逻辑全写在路由函数体内、无可复用内部函数，故只能在本模块按同口径重实现：

    TrialBalance 表 + get_active_filter(db, tb, project_id, year)
      → 按 account_name 聚合（同名多子科目合并）
      → 金额取 audited_amount 优先、否则 unadjusted_amount
      → 过滤 abs(amount) < 1e-6
      → cycle 由 b50_risk_reader.cycle_for_account(name, code) 映射

``risk_dimension_available`` 口径 = **「至少一个认定有 rmm」**（不是六认定全填）。这与
Task 3 已交付的前端
``audit-platform/frontend/src/components/workpaper/composables/b50Completeness.ts``
的 ``assessedCount`` 同口径 —— 该文件 docstring L18~34 明文警告**不得**与
``useB50RiskMatrix.incompleteAccounts`` 的「六认定全填」口径统一（后者服务矩阵填写完整
性提示，严格口径会让「只填了关键认定」的项目在裁剪页恒显示"B50 未填"而无法使用风险维度）。
"""
from __future__ import annotations

import logging
import math
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.b50_risk_reader import (
    _find_b50_wp_id,
    cycle_for_account,
    load_b50_accounts,
)
from app.services.trim_report_line_amounts import (
    AMOUNT_STANDARD_UNSET,
    ReportLineAmount,
    resolve_trim_report_line_amounts,
)
from app.services.workpaper_entry_probe import probe_workpaper_entries_detailed

logger = logging.getLogger(__name__)

# ── degradations 的 dimension 取值域（守卫按此断言，禁扩散）────────────────────
DIM_ACCOUNTS = "accounts"
DIM_MATERIALITY = "materiality"
DIM_RISK = "risk"
DIM_COMPLETENESS_OVERRIDE = "completeness_override"
DIM_WORKPAPER_ENTRY = "workpaper_entry"
#: 报表行科目金额维度（spec procedure-trim-report-line-account-resolution Task 7）
DIM_REPORT_LINE = "report_line"

DEGRADATION_DIMENSIONS: frozenset[str] = frozenset({
    DIM_ACCOUNTS,
    DIM_MATERIALITY,
    DIM_RISK,
    DIM_COMPLETENESS_OVERRIDE,
    DIM_WORKPAPER_ENTRY,
    DIM_REPORT_LINE,
})

# ── accounts 维度三态成因码（cause 只允许出现在 accounts 维度）─────────────────
CAUSE_QUERY_FAILED = "query_failed"
CAUSE_NOT_IMPORTED = "not_imported"
CAUSE_NO_MATERIAL_ACCOUNTS = "no_material_accounts"

ACCOUNTS_CAUSES: frozenset[str] = frozenset({
    CAUSE_QUERY_FAILED,
    CAUSE_NOT_IMPORTED,
    CAUSE_NO_MATERIAL_ACCOUNTS,
})

# 返回值任何层级都不得出现的键（Requirement 4.6 的结构性保证）
FORBIDDEN_RESULT_KEYS: frozenset[str] = frozenset({"overall_materiality"})

# 完整性清单项目级覆盖的 checklist_responses 键前缀（design.md 持久化落点决策）
#
# 🔴 单一真源：写入侧 `procedure_trim_service.set_completeness_scope_override()` 直接
#    import 本常量（经公开别名 `COMPLETENESS_SCOPE_ITEM_PREFIX`），禁止另写一份字面量 ——
#    两侧前缀漂移会让「写进去的覆盖读不出来」，而两侧各自的单测都会全绿（各自用自己
#    的前缀构造样本），只有真实往返才暴露。守卫 `test_completeness_scope_override.py`
#    按「写入侧引用的就是本常量」断言。
_CSCOPE_PREFIX = "B50-T3-cscope-"

#: 公开别名（跨模块引用用这个，不要引私有名 `_CSCOPE_PREFIX`）。
COMPLETENESS_SCOPE_ITEM_PREFIX = _CSCOPE_PREFIX

_AMOUNT_EPSILON = 1e-6

_RESULT_KEYS: tuple[str, ...] = (
    "accounts",
    "materiality",
    "risk",
    "risk_dimension_available",
    "completeness_override",
    "workpaper_entry",
    # 🔴 additive 第八键（spec procedure-trim-report-line-account-resolution Task 7）——
    #    既有七键的装配逻辑逐字不动。它们有三个现存消费方（档 4 数据存在性 /
    #    复核视图金额未知统计 / resolveAccountName），改结构会三处同时波及。
    "report_line_amounts",
    "degradations",
)


def _degradation(dimension: str, reason: str, cause: str | None = None) -> dict:
    """构造一条降级记录。

    ``cause`` 仅 accounts 维度可带（裁决 2）；其余维度传入即视为编程错误。
    """
    if dimension not in DEGRADATION_DIMENSIONS:
        raise ValueError(f"未登记的 degradation dimension: {dimension!r}")
    entry: dict[str, str] = {"dimension": dimension, "reason": reason}
    if cause is not None:
        if dimension != DIM_ACCOUNTS:
            raise ValueError(
                f"cause 是 accounts 维度专属字段，不得用于 dimension={dimension!r}"
            )
        if cause not in ACCOUNTS_CAUSES:
            raise ValueError(f"未登记的 accounts cause: {cause!r}")
        entry["cause"] = cause
    return entry


def _to_float(raw: Any) -> float | None:
    """转有限浮点；不可解析 / NaN / inf 一律 None（不写 0）。"""
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val):
        return None
    return val


# ═══════════════════════════════════════════════════════════════════════════
# 维度 1：科目金额（数据存在性判据）
# ═══════════════════════════════════════════════════════════════════════════
async def _load_accounts(
    db: AsyncSession, project_id: UUID, year: int, cycles: list[str],
) -> tuple[dict[str, dict], list[dict]]:
    """装配 ``{科目名: {"amount": float, "cycle": str}}``。

    与 ``routers/b50_scope.get_scope_accounts`` 同口径（见模块 docstring）。
    返回 ``(accounts, degradations)``；三种不可用成因都返回空 dict + 一条 degradation。
    """
    try:
        from app.models.audit_platform_models import TrialBalance
        from app.services.dataset_query import get_active_filter

        tb = TrialBalance.__table__
        active = await get_active_filter(db, tb, project_id, year)
        stmt = sa.select(
            tb.c.account_name,
            tb.c.standard_account_code,
            tb.c.unadjusted_amount,
            tb.c.audited_amount,
        ).where(active)
        rows = (await db.execute(stmt)).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "裁剪判据：试算表查询失败 project=%s year=%s: %s", project_id, year, e,
        )
        return {}, [_degradation(
            DIM_ACCOUNTS,
            "试算表读取失败，本次不提供科目金额判据（裁剪已阻断）",
            cause=CAUSE_QUERY_FAILED,
        )]

    if not rows:
        return {}, [_degradation(
            DIM_ACCOUNTS,
            "试算表无数据行，请先导入试算表（裁剪已阻断）",
            cause=CAUSE_NOT_IMPORTED,
        )]

    # 按报表项目名聚合（同名多子科目合并），金额审定优先、否则未审
    agg: dict[str, dict] = {}
    for r in rows:
        name = (r.account_name or "").strip()
        if not name:
            continue
        raw = r.audited_amount if r.audited_amount is not None else r.unadjusted_amount
        parsed = _to_float(raw)
        amt = 0.0 if parsed is None else parsed
        entry = agg.setdefault(
            name,
            {"amount": 0.0, "code": (r.standard_account_code or "").strip()},
        )
        entry["amount"] += amt

    wanted = {str(c).strip().upper() for c in (cycles or []) if str(c).strip()}
    accounts: dict[str, dict] = {}
    for name, entry in agg.items():
        if abs(entry["amount"]) < _AMOUNT_EPSILON:
            continue
        cyc = cycle_for_account(name, entry["code"])
        if wanted and (cyc or "").upper() not in wanted:
            continue
        accounts[name] = {"amount": round(entry["amount"], 2), "cycle": cyc}

    if not accounts:
        # 🔴 第三态：有行但过滤后零个非零科目。这是「试算表已导入而全部科目金额为零」
        # 的真实业务事实，与「未导入」必须可区分（否则前端提示"请先导入"而用户已导过）。
        return {}, [_degradation(
            DIM_ACCOUNTS,
            "试算表已导入而无非零科目（或所选循环下无科目），请核实数据（裁剪已阻断）",
            cause=CAUSE_NO_MATERIAL_ACCOUNTS,
        )]

    return accounts, []


# ═══════════════════════════════════════════════════════════════════════════
# 维度 2：重要性
# ═══════════════════════════════════════════════════════════════════════════
async def _load_materiality(
    db: AsyncSession, project_id: UUID, year: int,
) -> tuple[dict[str, float] | None, list[dict]]:
    """装配 ``{"performance_materiality": float, "trivial_threshold": float} | None``。

    🔴 **结构上不允许半开**：要么两键齐全（都是有限数值），要么整体 ``None``。
    🔴 **绝不返回 ``overall_materiality``** —— 返回它等于把 Requirement 4.6 的「不推算」
    交给前端自觉（前端拿到整体重要性照样能乘个比例算出实际执行重要性）。
    """
    try:
        from app.models.audit_platform_models import Materiality

        m = Materiality.__table__
        # 唯一索引 uq_materiality_project_year (project_id, year) ⇒ 至多 1 行；
        # 软删记录视为「未设置」（不能把已作废的重要性当判据）。
        stmt = sa.select(m.c.performance_materiality, m.c.trivial_threshold).where(
            sa.and_(
                m.c.project_id == project_id,
                m.c.year == year,
                m.c.is_deleted == sa.false(),
            )
        )
        row = (await db.execute(stmt)).fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "裁剪判据：重要性查询失败 project=%s year=%s: %s", project_id, year, e,
        )
        return None, [_degradation(
            DIM_MATERIALITY, "重要性读取失败，本次不使用重要性判据",
        )]

    if row is None:
        return None, [_degradation(
            DIM_MATERIALITY, "本项目本年度未设置重要性水平，本次不使用重要性判据",
        )]

    pm = _to_float(row.performance_materiality)
    tt = _to_float(row.trivial_threshold)
    if pm is None or tt is None:
        # 🔴 不按 overall_materiality × 比例推算（Requirement 4.6）：那是会计判断。
        # 半开状态（只有一个阈值）同样按整个维度缺失处理，避免前端拿半套阈值下判断。
        return None, [_degradation(
            DIM_MATERIALITY,
            "重要性记录缺少实际执行重要性或明显微小错报阈值；不由整体重要性推算，"
            "本次不使用重要性判据",
        )]

    return {"performance_materiality": pm, "trivial_threshold": tt}, []


# ═══════════════════════════════════════════════════════════════════════════
# 维度 3：B50 认定层次风险
# ═══════════════════════════════════════════════════════════════════════════
def _risk_dimension_available(risk: dict[str, dict]) -> bool:
    """「至少一个认定有 rmm」即视为风险维度可用（见模块 docstring 口径说明）。"""
    for item in risk.values():
        cells = item.get("cells") or {}
        for cell in cells.values():
            if isinstance(cell, dict) and cell.get("rmm"):
                return True
    return False


async def _load_risk(
    db: AsyncSession, project_id: UUID,
) -> tuple[dict[str, dict], bool, list[dict]]:
    """装配 ``{科目名: {...load_b50_accounts 科目项原样...}}`` + 维度可用性。"""
    try:
        items = await load_b50_accounts(db, project_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("裁剪判据：B50 风险读取失败 project=%s: %s", project_id, e)
        return {}, False, [_degradation(
            DIM_RISK, "B50 认定层次风险读取失败，本次不使用风险维度",
        )]

    risk = {
        str(it.get("account")): it
        for it in (items or [])
        if it and it.get("account")
    }
    available = _risk_dimension_available(risk)
    if not available:
        # 🔴 措辞覆盖两种成因：`load_b50_accounts` 自身 fail-open（内部 except 返回 []）
        # 使「读取失败」与「无已评估认定」在本模块**不可区分**。这是既有取数源的缺陷，
        # 本任务只读复用它、不改它（改动 b50_risk_reader 会波及 Wave 1 的 23 例守卫），
        # 故不给 risk 维度编造成因码 —— `cause` 是 accounts 维度专属（裁决 2）。
        return risk, False, [_degradation(
            DIM_RISK,
            "B50 无已评估认定（未填写重大错报风险等级）或读取失败，本次不使用风险维度",
        )]
    return risk, True, []


# ═══════════════════════════════════════════════════════════════════════════
# 完整性清单项目级覆盖
# ═══════════════════════════════════════════════════════════════════════════
async def _load_completeness_override(
    db: AsyncSession, project_id: UUID,
) -> tuple[dict[str, bool] | None, list[dict]]:
    """读 ``checklist_responses`` 的 ``B50-T3-cscope-{cycle}``。

    三态可区分：``conclusion == 'Y'`` → ``True``；``'N'`` → ``False``；
    **未覆盖的循环不出现在 dict 里**（前端据此退回平台默认清单）。
    读取失败 → ``None`` + degradation（前端退回平台默认并在复核视图标注）。

    🔴 底稿定位复用 ``b50_risk_reader._find_b50_wp_id``，不另写一份 JOIN。
    🔴 ``checklist_responses`` 的底稿外键列名是 ``wp_id``（不是 ``workpaper_id``），
    唯一约束 ``(wp_id, item_id)`` ⇒ 按该键查天然最多 1 行。
    """
    try:
        b50_wp = await _find_b50_wp_id(db, project_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("裁剪判据：B50 底稿定位失败 project=%s: %s", project_id, e)
        return None, [_degradation(
            DIM_COMPLETENESS_OVERRIDE,
            "B50 底稿定位失败，完整性敏感清单退回平台默认",
        )]
    if not b50_wp:
        # 未建 B50 底稿 = 没有任何项目级覆盖，这是**正常状态**不是降级 ⇒ 返回 {} 不记
        # degradation。⚠️ `_find_b50_wp_id` 自身 fail-open（查询异常也返 None）⇒ 「定位
        # 失败」与「B50 未建」在此不可区分；有意选择按后者处理，因为全库 B50-T3-* 为 0 行
        # （绝大多数项目没建 B50）⇒ 若按前者记 degradation，摘要会长期常亮"降级"而形成
        # 告警疲劳，真降级反而被忽略。显式 cscope 查询失败那条路径是可区分的，仍记降级。
        return {}, []

    try:
        res = await db.execute(
            sa.text(
                "SELECT item_id, conclusion FROM checklist_responses "
                "WHERE wp_id = :wp AND item_id LIKE 'B50-T3-cscope-%'"
            ),
            {"wp": str(b50_wp)},
        )
        rows = res.fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "裁剪判据：完整性清单覆盖读取失败 project=%s: %s", project_id, e,
        )
        return None, [_degradation(
            DIM_COMPLETENESS_OVERRIDE,
            "完整性敏感清单项目级覆盖读取失败，退回平台默认",
        )]

    override: dict[str, bool] = {}
    for r in rows:
        cycle = (r.item_id or "").removeprefix(_CSCOPE_PREFIX)
        if not cycle or cycle == (r.item_id or ""):
            continue
        val = (r.conclusion or "").strip().upper()
        if val == "Y":
            override[cycle] = True
        elif val == "N":
            override[cycle] = False
        # 其它取值（空 / 历史脏值）视为未覆盖，不进 dict —— 三态必须可区分。
    return override, []


# ═══════════════════════════════════════════════════════════════════════════
# 底稿已录入探测（Task 10 接线；探测判据在 workpaper_entry_probe）
# ═══════════════════════════════════════════════════════════════════════════
# 🔴 SQL 首行标记：供测试替身分流（本查询表名 `procedure_instances` 与既有五路都不撞，
#    但标记让替身路由与 SQL 细节解耦）。守卫按此断言，勿删。
PROBE_TARGET_SQL_MARKER = "-- probe_target_wp_codes"

_PROBE_TARGET_SQL_BASE = f"""
{PROBE_TARGET_SQL_MARKER}
SELECT DISTINCT wp_code, audit_cycle
FROM procedure_instances
WHERE project_id = CAST(:pid AS uuid)
  AND is_deleted = false
  AND wp_code IS NOT NULL
  AND btrim(wp_code) <> ''
"""


async def _collect_probe_wp_codes(
    db: AsyncSession, project_id: UUID, cycles: list[str],
) -> list[str]:
    """探测目标 = 本项目待裁决**程序实例**的 ``wp_code``（按 ``cycles`` 过滤）。

    🔴 目标清单取自 ``procedure_instances`` 而非全项目底稿索引 —— 裁剪决策的作用域就是
    程序实例，探测无关底稿等于白查（该表实测 452 行 / 332 个 distinct wp_code）。
    🔴 ``cycles`` 过滤在 Python 侧做（与 ``_load_accounts`` 同款大写归一口径），SQL 不拼
    IN 列表：拼串会让替身分流与守卫都要跟着 cycles 变。
    """
    rows = (
        await db.execute(sa.text(_PROBE_TARGET_SQL_BASE), {"pid": str(project_id)})
    ).fetchall()

    wanted = {str(c).strip().upper() for c in (cycles or []) if str(c).strip()}
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        code = (getattr(r, "wp_code", None) or "").strip()
        if not code or code in seen:
            continue
        if wanted:
            cyc = (getattr(r, "audit_cycle", None) or "").strip().upper()
            if cyc not in wanted:
                continue
        seen.add(code)
        out.append(code)
    return out


async def _load_workpaper_entry(
    db: AsyncSession, project_id: UUID, cycles: list[str],
) -> tuple[dict[str, bool], list[dict]]:
    """装配 ``{wp_code: 是否已有实质录入}``（Requirement 9.1/9.2/9.4/9.5）。

    判据全在 ``workpaper_entry_probe``（顶层 import = **硬依赖**：模块被删则本模块直接
    import 失败、56 条守卫齐声打红，比 importlib 静默降级安全 —— 后者会把接线错误伪装成
    「本项目没有录入」）。

    三条降级路径各自可区分（空 / 全 True 都必须伴随标注，否则与真实结论混淆）：

    - 目标清单查询失败 → ``{}`` + degradation
    - 目标清单为空（本项目无带底稿编号的程序实例）→ ``{}`` + degradation
    - 探测查询失败 → 全 ``True`` + degradation（保守保留，但**必须**告知这是降级；
      不告知则「探测失败导致全保留」与「确实全都有录入」不可区分，而前者意味着智能裁剪
      本次整体失效）
    """
    try:
        codes = await _collect_probe_wp_codes(db, project_id, cycles)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "裁剪判据：底稿已录入探测目标清单查询失败 project=%s: %s", project_id, e,
        )
        return {}, [_degradation(
            DIM_WORKPAPER_ENTRY,
            "底稿已录入探测目标清单查询失败，本次不使用「底稿已有录入」保护判据",
        )]

    if not codes:
        return {}, [_degradation(
            DIM_WORKPAPER_ENTRY,
            "本项目无带底稿编号的程序实例，底稿已录入探测目标为空",
        )]

    result = await probe_workpaper_entries_detailed(db, project_id, codes)
    if result.degraded:
        return result.entries, [_degradation(
            DIM_WORKPAPER_ENTRY,
            result.reason or "底稿已录入探测降级，本次按「可能有录入」保守保留",
        )]
    return result.entries, []


# ═══════════════════════════════════════════════════════════════════════════
# 维度 6：报表行科目金额（重要性判据的金额来源，additive）
# ═══════════════════════════════════════════════════════════════════════════
def _report_line_amount_as_dict(item: ReportLineAmount) -> dict:
    """dataclass → 可 JSON 序列化的 dict（``standard_codes`` 元组转列表）。

    键名与前端 ``TrimReportLineAmount`` 接口逐字对应；``amount`` 为 ``None`` 时
    **保留该键并置 null**（不省略）—— 省略会让前端 `hasOwnProperty` 判空与
    「后端没下发这个维度」不可区分。
    """
    return {
        "status": item.status,
        "amount": item.amount,
        "row_code": item.row_code,
        "row_name": item.row_name,
        "formula": item.formula,
        "standard_codes": list(item.standard_codes),
        "applicable_standard": item.applicable_standard,
        "source_symbol": item.source_symbol,
        "reason": item.reason,
    }


async def _load_report_line_amounts(
    db: AsyncSession, project_id: UUID, year: int, cycles: list[str],
) -> tuple[dict[str, dict], list[dict]]:
    """装配 ``{wp_code: 报表行金额}``（spec Requirement 4.5 / 5.5）。

    目标清单复用 :func:`_collect_probe_wp_codes` —— 与底稿录入探测**同一口径**。
    不新建第二套目标集：两套目标集会让「某程序有录入探测结果但没有金额」这种
    半开状态出现，而两侧各自的守卫都查不出（各自只看自己那套）。

    三条降级路径各自可区分：

    - 目标清单查询失败 → ``{}`` + degradation
    - 目标清单为空（本项目无带底稿编号的程序实例）→ ``{}`` + degradation
    - 金额解析整体失败 → ``{}`` + degradation

    另有一条**非空但整体不可用**的标注：全部项都是「项目准则未确定」时加一条
    degradation，使摘要区能告知审计师「去项目设置里确认适用准则」，
    而不是让他逐条看 61 个相同的 reason。

    🔴 单个 wp_code 解析失败**不**产生 degradation —— 那是该底稿自己的三态之一
    （``reason`` 里已写明成因），前端按行标注即可。把它升级成维度级降级会让
    「一个底稿没落点」看起来像「整个维度失效」。
    """
    try:
        codes = await _collect_probe_wp_codes(db, project_id, cycles)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "裁剪判据：报表行取数目标清单查询失败 project=%s: %s", project_id, e,
        )
        return {}, [_degradation(
            DIM_REPORT_LINE,
            "报表行取数目标清单查询失败，本次不使用报表行映射的科目金额",
        )]

    if not codes:
        return {}, [_degradation(
            DIM_REPORT_LINE,
            "本项目无带底稿编号的程序实例，报表行取数目标为空",
        )]

    try:
        resolved = await resolve_trim_report_line_amounts(db, project_id, year, codes)
    except Exception as e:  # noqa: BLE001
        logger.error(
            "裁剪判据：报表行科目金额解析整体失败 project=%s year=%s: %r",
            project_id, year, e,
        )
        return {}, [_degradation(
            DIM_REPORT_LINE,
            "报表行科目金额解析失败，本次退回按科目名匹配取金额",
        )]

    payload = {code: _report_line_amount_as_dict(item) for code, item in resolved.items()}

    degradations: list[dict] = []
    if payload and all(
        item["status"] == AMOUNT_STANDARD_UNSET for item in payload.values()
    ):
        sample = next(iter(payload.values()))
        degradations.append(_degradation(
            DIM_REPORT_LINE,
            sample.get("reason")
            or "本项目适用会计准则未确定，报表行取数整体不可用，已退回按科目名匹配取金额",
        ))
    return payload, degradations


# ═══════════════════════════════════════════════════════════════════════════
# 装配入口
# ═══════════════════════════════════════════════════════════════════════════
async def build_trim_decision_context(
    db: AsyncSession, project_id: UUID, year: int, cycles: list[str]
) -> dict:
    """一次性装配三维判据上下文（只读，fail-soft 但不静默伪装）。

    返回**恰好**八键::

        {
          "accounts": {科目名: {"amount": float, "cycle": str}},
          "materiality": {"performance_materiality": float, "trivial_threshold": float} | None,
          "risk": {科目名: {...load_b50_accounts 科目项原样...}},
          "risk_dimension_available": bool,
          "completeness_override": {cycle: bool} | None,
          "workpaper_entry": {wp_code: bool},
          "report_line_amounts": {wp_code: {status, amount, row_code, row_name, formula,
                                            standard_codes, applicable_standard,
                                            source_symbol, reason}},
          "degradations": [{"dimension": str, "reason": str, "cause"?: str}],
        }

    ``cycles`` 为空表示「全部科目余额驱动循环」（不过滤）。

    🔴 ``report_line_amounts`` 是 additive 第八键（spec
    procedure-trim-report-line-account-resolution）——前七键的装配逻辑逐字未动，
    故「新键缺失时前端退回科目名兜底」是结构性保证而非约定。
    """
    degradations: list[dict] = []

    accounts, acc_deg = await _load_accounts(db, project_id, year, cycles or [])
    degradations.extend(acc_deg)

    materiality, mat_deg = await _load_materiality(db, project_id, year)
    degradations.extend(mat_deg)

    risk, risk_available, risk_deg = await _load_risk(db, project_id)
    degradations.extend(risk_deg)

    override, ov_deg = await _load_completeness_override(db, project_id)
    degradations.extend(ov_deg)

    entry, entry_deg = await _load_workpaper_entry(db, project_id, cycles or [])
    degradations.extend(entry_deg)

    report_lines, rl_deg = await _load_report_line_amounts(
        db, project_id, year, cycles or []
    )
    degradations.extend(rl_deg)

    return {
        "accounts": accounts,
        "materiality": materiality,
        "risk": risk,
        "risk_dimension_available": risk_available,
        "completeness_override": override,
        "workpaper_entry": entry,
        "report_line_amounts": report_lines,
        "degradations": degradations,
    }
