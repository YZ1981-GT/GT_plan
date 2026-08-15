"""裁剪判据的报表行科目金额解析 —— 四态、一律不兜 0。

Feature: procedure-trim-report-line-account-resolution — Task 5
Requirements: 2.1, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4
守卫: ``backend/tests/procedure_trim/test_trim_report_line_amounts.py``

## 三段映射的最后两段

第一段（``wp_code`` → 报表行编码）在 ``four_table.report_line_index``。本模块承担：

1. 报表行编码 + 项目适用准则 → ``report_config`` 的 ``formula``
2. ``formula`` → 金额（全权委托 ``report_engine.ReportFormulaParser``）

## 🔴 金额一律走报表取数引擎，不自己聚合科目

看起来更"轻"的做法是拿科目码自己 SQL 求和，但那会引入**第二个金额口径** ——
审计师会在报表页看到一个数、在裁剪建议里看到另一个数，且无从判断该信哪个。
``ReportFormulaParser`` 已处理前缀聚合（``TB('2221')`` 自动含 ``222102``）、
``SUM_TB`` 区间、公式符号运算（``TB('1122') - TB('1231')``）。复用它使
「裁剪建议的金额 = 报表上那个数」成为结构性事实而非巧合。

同理**不按语义槽拆分后再合计**：多槽规格下报表公式兜底会把整行金额分配给某个槽，
E1 曾因此把银行存款与其他货币资金算两遍（虚增一倍）。本模块只要行级合计。

## 🔴 非 ``resolved`` 态的金额恒 ``None``，绝不为 ``0``

编造 0 会让该程序被误判成「低于任何阈值」而产生裁剪建议，
而正确结论是「这个判据对它不可用」。前者会裁掉本该做的程序。

## 适用准则：两处声明都读，一致才出数

平台有**两组**准则字段，且它们在真实库已经分叉：

- ``projects.applicable_standard_v2``（结构化，权威真源，``standard_unification_service``
  写入时双写旧字段）
- ``projects.template_type`` + ``report_scope``（旧字段，**报表页实际用的就是这组** ——
  见 ``report_config_service.resolve_applicable_standard``）

实测 32 个项目：24 个两组都未设 · 7 个一致 · **1 个分叉**（``template_type='listed'``
而 ``v2.entity_type='soe'``，且它是程序实例最多的项目）。分叉意味着报表页按上市准则
出数、而平台其他模块按国企 —— 同一底稿的 ``BS-006`` 公式因此不同
（上市个别 ``TB('1122') - TB('1231')`` vs 国企个别 ``TB('1122') - TB('1231-02')``）。

故本模块的判定是：

===================================== ==========================================
项目准则状态                            结果
===================================== ==========================================
两组一致                                按该准则取行与公式（与报表页同口径）
``v2`` 已设而旧字段缺失                  按 ``v2``（它是权威真源）
两组分叉                                ``standard_unset`` + **ERROR 日志**
``v2`` 未设置                           ``standard_unset``
组合不在 ``report_config`` 取值域         ``standard_unset``
===================================== ==========================================

**为什么分叉时宁缺勿造**：报表页必须出一张报表所以它兜底，而裁剪判据是**自动裁掉
审计程序**的依据 —— 用一个说不清的准则算出的金额去裁程序，风险远高于报表上显示一个
可能不准的数。R3.3 明确禁止「默认取某一个变体」。

**为什么不新增第五个状态**：状态取值域恰为四态（R4.1，守卫钉死）。语义上
「未设置」与「自相矛盾」同属「本项目适用准则未确定」，``reason`` 里如实区分成因。

## ``ROW()`` 引用一律拒解析

含 ``ROW()`` 的报表行依赖其它行的计算结果（实证 ``BS-069`` 非流动负债合计的公式
全是 ``ROW()`` 引用，而 J1 在国企准则下声明的就是这个号）。不传伪造的 ``row_cache``
去凑一个部分结果 —— 那个数既不是该科目余额也不是任何有意义的量。

## 异常一律记 ERROR 级

本平台已多次出现 ``except Exception`` 把「函数名/列名拼错、传错客户端形态」吞成
WARNING 甚至静默 ⇒ 表现为「本项目无此数据」，而静态检查与单测四层全绿。
ERROR 级留下可检索的痕迹是事后发现接线错误的唯一手段。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.four_table.report_line_index import (
    REF_NON_BALANCE_DRIVEN,
    REF_RESOLVED,
    ReportLineRef,
    normalize_wp_code,
    resolve_report_line_ref,
)
from app.services.report_engine import ReportFormulaParser

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 状态取值域（恰四态，R4.1）
# ─────────────────────────────────────────────────────────────────────────────
#: 解析成功 —— 取到了该报表行的金额
AMOUNT_RESOLVED = "resolved"
#: 索引无报表行落点（含「该循环不按科目余额驱动」）
AMOUNT_NO_REPORT_LINE = "no_report_line"
#: 报表行存在但公式缺失 / 含 ``ROW()`` 引用 / 求值失败
AMOUNT_FORMULA_UNAVAILABLE = "formula_unavailable"
#: 项目适用准则未确定（未设置 / 两处声明分叉 / 组合无对应配置）
AMOUNT_STANDARD_UNSET = "standard_unset"

#: ``report_config.applicable_standard`` 的四个准则变体
_VALID_STANDARDS: frozenset[str] = frozenset({
    "listed_consolidated",
    "listed_standalone",
    "soe_consolidated",
    "soe_standalone",
})

#: 每态的中文说明模板（不带上下文时的通用文案）
_REASON_TEMPLATES: dict[str, str] = {
    AMOUNT_RESOLVED: "",
    AMOUNT_NO_REPORT_LINE: "该底稿没有报表行落点，无法按报表项目定位科目余额",
    AMOUNT_FORMULA_UNAVAILABLE: "该报表行未配置可独立求值的取数公式",
    AMOUNT_STANDARD_UNSET: "本项目适用会计准则未确定，无法选定报表格式",
}


def reason_for_status(status: str, **ctx: Any) -> str:
    """取某状态的中文说明；``ctx`` 非空时拼上具体成因。

    每态文案互不相同 —— 四态共用一句「取数失败」会让审计师看到的原因与实际成因不符：
    「本项目没填准则」审计师能自己解决，「这个报表行没配公式」得找平台维护者。
    """
    base = _REASON_TEMPLATES.get(str(status), "")
    detail = str(ctx.get("detail") or "").strip()
    if base and detail:
        return f"{base}（{detail}）"
    return detail or base


@dataclass(frozen=True)
class ReportLineAmount:
    """一条底稿的报表行金额解析结果。

    :param wp_code: 归一后的底稿主码
    :param status: 四态之一
    :param amount: 🔴 **非 ``resolved`` 态恒 ``None``，绝不为 ``0``**
    :param row_code: 报表行编码（溯源，R6.1）
    :param row_name: 报表行名（溯源；审计师据它发现「行名与循环语义不符」）
    :param formula: 命中的公式原文（溯源）
    :param standard_codes: 参与计算的标准码（``extract_account_codes`` 产出，溯源）
    :param applicable_standard: 实际使用的准则变体
    :param source_symbol: 报表行编码的取值出处（索引给出）
    :param reason: 非 ``resolved`` 态的中文原因
    """

    wp_code: str
    status: str
    amount: float | None = None
    row_code: str = ""
    row_name: str = ""
    formula: str | None = None
    standard_codes: tuple[str, ...] = field(default_factory=tuple)
    applicable_standard: str = ""
    source_symbol: str = ""
    reason: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# 适用准则
# ─────────────────────────────────────────────────────────────────────────────
_PROJECT_STANDARD_SQL = """
SELECT applicable_standard_v2, template_type, report_scope
FROM projects
WHERE id = :pid AND is_deleted = false
"""


def _combo(entity: Any, scope: Any) -> str:
    e = str(entity or "").strip().lower()
    s = str(scope or "").strip().lower()
    return f"{e}_{s}" if e and s else ""


async def _resolve_project_standard(
    db: AsyncSession, project_id: Any
) -> tuple[str, str]:
    """取项目适用准则；返回 ``(准则变体, 未确定时的中文成因)``。

    🔴 **不能**用 ``derive_applicable_standards`` 判「未设置」—— 它永不为空
    （无法推断时补 ``DEFAULT_STANDARD = soe/standalone``），用它判会把真实库里 24 个
    未填准则的项目静默算成国企个别报表并给出金额，那正是 R3.3 禁止的默认取某变体。
    """
    try:
        row = (
            await db.execute(sa.text(_PROJECT_STANDARD_SQL), {"pid": str(project_id)})
        ).fetchone()
    except Exception as e:  # noqa: BLE001
        logger.error(
            "裁剪判据·报表行金额：项目适用准则查询失败 project=%s: %r", project_id, e,
        )
        return "", "项目适用准则查询失败"

    if row is None:
        return "", "项目不存在或已删除"

    raw_v2 = getattr(row, "applicable_standard_v2", None)
    v2 = _combo(
        raw_v2.get("entity_type") if isinstance(raw_v2, dict) else None,
        raw_v2.get("scope") if isinstance(raw_v2, dict) else None,
    )
    legacy = _combo(
        getattr(row, "template_type", None), getattr(row, "report_scope", None)
    )

    if not v2:
        return "", "本项目尚未设置适用会计准则（主体类型 / 报表范围）"

    if legacy and legacy != v2:
        # 🔴 报表页按 legacy 出数、平台其他模块按 v2 ⇒ 同一底稿的取数公式会不同。
        #    用哪一个都可能与审计师在报表页看到的数不一致 ⇒ 宁缺勿造。
        logger.error(
            "裁剪判据·报表行金额：项目两处准则声明不一致 project=%s "
            "applicable_standard_v2=%s template_type+report_scope=%s"
            "（报表页按后者出数，本次不产出金额）",
            project_id, v2, legacy,
        )
        return "", (
            f"本项目两处准则声明不一致：结构化准则为 {v2}、报表格式字段为 {legacy}，"
            "两者会取到不同的报表取数公式，请先在项目设置中确认适用准则"
        )

    if v2 not in _VALID_STANDARDS:
        return "", f"报表格式配置中没有 {v2} 这个准则变体"

    return v2, ""


# ─────────────────────────────────────────────────────────────────────────────
# report_config 批量读取
# ─────────────────────────────────────────────────────────────────────────────
_REPORT_CONFIG_SQL = """
SELECT row_code, row_name, formula
FROM report_config
WHERE row_code = ANY(:codes)
  AND applicable_standard = :std
  AND is_deleted = false
"""


async def _fetch_report_lines(
    db: AsyncSession, row_codes: list[str], standard: str
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """一次批量取回报表行配置；返回 ``({row_code: {row_name, formula}}, 重复码集合)``。

    唯一索引是 ``(report_type, row_code, applicable_standard)`` ⇒ 同一
    ``(row_code, standard)`` 在不同 ``report_type`` 下理论可有多行。实证 ``BS-*`` /
    ``IS-*`` / ``IMP-*`` 前缀与 ``report_type`` 一一对应故实际唯一，但真出现多行时
    不能随便取一条 —— 那等于随机选一个公式，故登记进重复集合按不可解析处理。
    """
    if not row_codes:
        return {}, set()
    try:
        rows = (
            await db.execute(
                sa.text(_REPORT_CONFIG_SQL), {"codes": list(row_codes), "std": standard}
            )
        ).all()
    except Exception as e:  # noqa: BLE001
        logger.error(
            "裁剪判据·报表行金额：report_config 批量查询失败 standard=%s codes=%s: %r",
            standard, row_codes, e,
        )
        return {}, set()

    out: dict[str, dict[str, Any]] = {}
    duplicated: set[str] = set()
    for r in rows:
        code = str(getattr(r, "row_code", "") or "")
        item = {
            "row_name": str(getattr(r, "row_name", "") or ""),
            "formula": getattr(r, "formula", None),
        }
        prev = out.get(code)
        if prev is not None and prev != item:
            duplicated.add(code)
            continue
        out[code] = item
    if duplicated:
        logger.error(
            "裁剪判据·报表行金额：以下报表行在 standard=%s 下有多条不同配置，"
            "无法确定该用哪个公式：%s",
            standard, sorted(duplicated),
        )
    return out, duplicated


# ─────────────────────────────────────────────────────────────────────────────
# 装配入口
# ─────────────────────────────────────────────────────────────────────────────
def _unavailable(
    ref: ReportLineRef, standard: str, detail: str, *, row_name: str = "",
    formula: str | None = None,
) -> ReportLineAmount:
    return ReportLineAmount(
        wp_code=ref.wp_code,
        status=AMOUNT_FORMULA_UNAVAILABLE,
        row_code=ref.row_code,
        row_name=row_name,
        formula=formula,
        applicable_standard=standard,
        source_symbol=ref.source_symbol,
        reason=reason_for_status(AMOUNT_FORMULA_UNAVAILABLE, detail=detail),
    )


async def resolve_trim_report_line_amounts(
    db: AsyncSession,
    project_id: Any,
    year: int,
    wp_codes: list[str],
) -> dict[str, ReportLineAmount]:
    """按底稿编号批量解析报表行金额（只读，fail-soft 但不静默伪装）。

    :param wp_codes: 底稿编号，可含区间型（``D2-1至D2-4``）与重复项
    :return: ``{传入的原始 wp_code: ReportLineAmount}``；键与入参一一对应

    单个底稿不可解析**不影响其余**（R4.5）；整体准则未确定时全部返
    :data:`AMOUNT_STANDARD_UNSET`（每项各带 ``reason``，而不是返回空 dict —— 空 dict
    与「本项目没有待裁决程序」不可区分）。
    """
    codes = [str(c) for c in (wp_codes or []) if str(c or "").strip()]
    if not codes:
        return {}

    # ── 第 1 步：索引（纯 CPU，无 IO）────────────────────────────────────────
    refs: dict[str, ReportLineRef] = {}
    standards_hint: list[str] = []
    for raw in codes:
        refs[raw] = resolve_report_line_ref(raw)

    # ── 第 2 步：适用准则（一次查询）────────────────────────────────────────
    standard, std_reason = await _resolve_project_standard(db, project_id)
    if not standard:
        return {
            raw: ReportLineAmount(
                wp_code=normalize_wp_code(raw),
                status=AMOUNT_STANDARD_UNSET,
                reason=reason_for_status(AMOUNT_STANDARD_UNSET, detail=std_reason),
            )
            for raw in codes
        }

    # 准则已确定 ⇒ 重跑索引（I / J / K 三循环的报表行按准则不同，R3.1/R3.2）
    standards_hint = [standard, standard.split("_")[0], standard.split("_")[-1]]
    for raw in codes:
        refs[raw] = resolve_report_line_ref(raw, standards_hint)

    # ── 第 3 步：report_config 批量取回（一次查询，不在循环里发）─────────────
    wanted = sorted({r.row_code for r in refs.values() if r.status == REF_RESOLVED and r.row_code})
    config, duplicated = await _fetch_report_lines(db, wanted, standard)

    # ── 第 4 步：逐个求值（parser 单实例，复用其两级缓存即天然批量）──────────
    parser = ReportFormulaParser(db, project_id, year)
    #: 同一报表行只求值一次（多个区间型 wp_code 常落同一底稿主码）
    evaluated: dict[str, tuple[float | None, str]] = {}

    out: dict[str, ReportLineAmount] = {}
    for raw in codes:
        ref = refs[raw]

        if ref.status != REF_RESOLVED:
            out[raw] = ReportLineAmount(
                wp_code=ref.wp_code,
                status=AMOUNT_NO_REPORT_LINE,
                applicable_standard=standard,
                source_symbol=ref.source_symbol,
                reason=reason_for_status(
                    AMOUNT_NO_REPORT_LINE,
                    detail=ref.reason or (
                        "该循环不按科目余额驱动裁剪"
                        if ref.status == REF_NON_BALANCE_DRIVEN else ""
                    ),
                ),
            )
            continue

        if ref.row_code in duplicated:
            out[raw] = _unavailable(
                ref, standard,
                f"报表行 {ref.row_code} 在 {standard} 下有多条不同配置",
            )
            continue

        cfg = config.get(ref.row_code)
        if cfg is None:
            out[raw] = _unavailable(
                ref, standard,
                f"报表格式配置中没有 {ref.row_code} 在 {standard} 下的行",
            )
            continue

        row_name = str(cfg["row_name"] or "")
        formula = cfg["formula"]
        if not str(formula or "").strip():
            out[raw] = _unavailable(
                ref, standard,
                f"报表行 {ref.row_code} {row_name} 未配置取数公式",
                row_name=row_name,
            )
            continue

        if parser.extract_row_refs(formula):
            # 🔴 不传伪造的 row_cache 强行求值 —— 那会得到一个既不是该科目余额、
            #    也不是任何有意义的量的数，而它会被当成裁剪依据。
            out[raw] = _unavailable(
                ref, standard,
                f"报表行 {ref.row_code} {row_name} 的取数公式依赖其它报表行的计算结果",
                row_name=row_name, formula=formula,
            )
            continue

        cached = evaluated.get(ref.row_code)
        if cached is None:
            try:
                value = await parser.execute(formula, {})
                cached = (float(value), "")
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "裁剪判据·报表行金额：公式求值失败 project=%s year=%s wp=%s "
                    "row_code=%s formula=%r: %r",
                    project_id, year, ref.wp_code, ref.row_code, formula, e,
                )
                cached = (None, f"报表行 {ref.row_code} {row_name} 的取数公式求值失败")
            evaluated[ref.row_code] = cached

        amount, err = cached
        if amount is None:
            out[raw] = _unavailable(
                ref, standard, err, row_name=row_name, formula=formula
            )
            continue

        out[raw] = ReportLineAmount(
            wp_code=ref.wp_code,
            status=AMOUNT_RESOLVED,
            amount=amount,
            row_code=ref.row_code,
            row_name=row_name,
            formula=formula,
            standard_codes=tuple(parser.extract_account_codes(formula)),
            applicable_standard=standard,
            source_symbol=ref.source_symbol,
        )

    return out


__all__ = [
    "AMOUNT_FORMULA_UNAVAILABLE",
    "AMOUNT_NO_REPORT_LINE",
    "AMOUNT_RESOLVED",
    "AMOUNT_STANDARD_UNSET",
    "ReportLineAmount",
    "reason_for_status",
    "resolve_trim_report_line_amounts",
]
