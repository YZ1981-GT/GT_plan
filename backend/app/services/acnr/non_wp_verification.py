"""ACNR 非底稿域引用的存在性核对（spec formula-fetch-followup-defect-closure R5.1）。

``full_resolve`` 对试算表 / 报表 / 附注 / 辅助余额引用委托 V1 地址库做写法换算（``_delegate_v1``），原先换算成功即
``found=True``：复合表达式取第一个引用照样判存在，引用不看数据一律存在 ⇒ 前端保存前校验被它短路，悬空引用照常入库。
本模块在换算之后判「是不是单个完整引用」与「本项目有没有」：

* 调用方声明只建立引用身份（``verify_existence=False``：附注执行器、高级查询追溯等）⇒ 原样返回，``verified=False``；
* 不是单个完整引用 ⇒ ``found=False, error="not_single_reference"``；
* 没有项目上下文 ⇒ ``found=False, error="project_context_required"``（无法确认，不是存在）；
* 有项目 ⇒ 按地址库校验（``validate_formula_refs``，试算表 / 报表 / 附注三域经 ``formula_ref_check``，与求值同口径）判定，
  不存在 ⇒ ``found=False, error="ref_not_found"`` 并带原因；章节级索引（``Note:五、3``）只看章节在不在。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.acnr.resolver import ResolveResult


def is_single_non_wp_ref(text: str) -> bool:
    """整串是一个完整的试算表 / 报表 / 附注 / 辅助余额引用（复合表达式、写法不全都不算）。"""
    from app.services.formula_ref_check import parse_checked_ref
    from app.services.formula_ref_preload import AUX2_RE, AUX3_RE, AUX4_RE

    s = (text or "").strip()
    return parse_checked_ref(s) is not None or any(p.fullmatch(s) for p in (AUX4_RE, AUX3_RE, AUX2_RE))


async def verify_non_wp(
    result: ResolveResult,
    *,
    formula_ref: str | None,
    project_id: str | None,
    db: AsyncSession | None,
    verify_existence: bool,
    memo: dict | None = None,
) -> ResolveResult:
    """对 V1 换算成功的结果核对单引用与存在性（规则见模块说明）。

    ``memo``（请求级，即 ``full_resolve`` 的 ``_instance_memo``）：同一请求 / 同一次报表生成里逐个解析很多引用时
    复用同一个判定器（试算表科目、报表配置、附注章节各只读一次）。
    """
    if not verify_existence:
        result.verified = False
        return result
    if formula_ref is not None and not is_single_non_wp_ref(formula_ref):
        return ResolveResult(found=False, error="not_single_reference", verified=False, source_layer="V1",
                             reason="不是单个完整的引用（复合表达式请逐个引用校验）")
    if not project_id or db is None:
        result.found, result.error, result.verified = False, "project_context_required", False
        result.reason = "需要项目上下文才能确认该引用在本项目是否存在"
        return result

    from app.services.address_registry import address_registry, parse_uri
    from app.services.formula_ref_check import FormulaRefChecker, parse_checked_ref, project_ref_scope

    parts = parse_uri(result.uri or "") or {}
    section_only = parts.get("domain") == "note" and not parts.get("path")
    ref_text = (formula_ref or result.formula_ref or "").strip()
    if not section_only and not is_single_non_wp_ref(ref_text):
        return ResolveResult(found=False, error="not_single_reference", verified=False, source_layer="V1",
                             uri=result.uri, reason=f"地址 {result.uri} 换算不出完整的引用写法")
    # 读库包在保存点里：调用方（报表生成等）的事务不会因这里的查询失败停在中止状态
    async with db.begin_nested():
        key = ("formula_ref_check", str(project_id))
        checker = memo.get(key) if memo is not None else None
        if checker is None:
            year, template_type = await project_ref_scope(db, project_id)
            checker = FormulaRefChecker(db, project_id, year, template_type)
            if memo is not None:
                memo[key] = checker
        if section_only:
            verdict = await checker.check_note_section(parts["source"])
            reason = "" if verdict.exists else verdict.reason
        elif parse_checked_ref(ref_text) is not None:
            verdict = await checker.check(ref_text)
            reason = "" if verdict is None or verdict.exists else verdict.reason
        else:  # 辅助余额：沿用地址目录（按科目前缀与维度）
            issues = await address_registry.validate_formula_refs(
                db, str(project_id), checker.year, ref_text, checker.template_type)
            reason = (issues[0].get("message") or "引用在本项目中不存在") if issues else ""
    if reason:
        return ResolveResult(found=False, error="ref_not_found", reason=reason, verified=True,
                             formula_ref=result.formula_ref, uri=result.uri, entry_type=result.entry_type,
                             source_layer="V1")
    result.verified = True
    return result
