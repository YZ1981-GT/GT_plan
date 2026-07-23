"""B 类承接计划 / C 类控制测试结论 域 resolvers。"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver


@auto_resolver("b2_communication_status")
async def _resolve_b2_comm(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B2 前任注册会计师沟通完成状态。

    数据来源: field_override_service（scope='b2_communication'）
    返回结构: {"summary": str, "status": str}
    """
    from app.services.field_override_service import FieldOverrideService
    svc = FieldOverrideService(db)
    data = await svc.get_batch(project_id, year, scope="b2_communication")
    # data = {item_key: {field: value}}
    status = "pending"
    if data:
        # 取第一条记录的 status 字段
        for _key, fields in data.items():
            if "status" in fields:
                status = fields["status"]
                break
    label_map = {"completed": "已完成沟通", "pending": "待沟通", "not_applicable": "不适用（非首次承接）"}
    return {"summary": label_map.get(status, status), "status": status}


@auto_resolver("b3_independence_status")
async def _resolve_b3_indep(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B3 独立性确认状态。

    数据来源: checklist_responses 表（无 ORM 模型，裸 SQL）。该表按 wp_id 存储，
    经 working_paper→wp_index 关联到 wp_code='B3'。统计条目总数与已填结论数。
    返回结构: {"summary": str, "progress": int}
    """
    row = (await db.execute(sa.text("""
        SELECT
            COUNT(*) AS total,
            COUNT(cr.conclusion) AS confirmed
        FROM checklist_responses cr
        JOIN working_paper wp ON wp.id = cr.wp_id
        JOIN wp_index wi ON wi.id = wp.wp_index_id
        WHERE cr.project_id = :pid
          AND wi.wp_code = 'B3'
    """), {"pid": str(project_id)})).first()
    total = (row.total if row else 0) or 0
    confirmed = (row.confirmed if row else 0) or 0
    if total == 0:
        return {"summary": "未开始", "progress": 0}
    pct = round(confirmed / total * 100)
    return {"summary": f"已确认{confirmed}/{total}项（{pct}%）", "progress": pct}


@auto_resolver("b1_risk_assessment_conclusion")
async def _resolve_b1_risk_conclusion(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B1-1/B1-2 风险评估综合结论（B1A/B1B 程序表步骤 5.1/5.3 自动推进）。

    数据来源: checklist_responses 表（item_id='b1risk-overall-conclusion'，
    经 working_paper→wp_index 关联到 wp_code B1-1/B1-2）。
    返回结构: {"summary": str, "conclusion": str|None}
    """
    row = (await db.execute(sa.text("""
        SELECT cr.conclusion
        FROM checklist_responses cr
        JOIN working_paper wp ON wp.id = cr.wp_id
        JOIN wp_index wi ON wi.id = wp.wp_index_id
        WHERE cr.project_id = :pid
          AND cr.item_id = 'b1risk-overall-conclusion'
          AND wi.wp_code IN ('B1-1', 'B1-2')
        ORDER BY cr.updated_at DESC NULLS LAST
        LIMIT 1
    """), {"pid": str(project_id)})).first()
    conclusion = row.conclusion if row else None
    label_map = {
        "low_risk": "✓ 已完成风险评估—低风险",
        "medium_risk": "⚠️ 已完成风险评估—中风险（需进一步评估审批）",
        "high_risk": "⚠️ 已完成风险评估—高风险（建议拒绝/解除）",
    }
    if not conclusion:
        return {"summary": "风险评估未完成", "conclusion": None}
    return {"summary": label_map.get(conclusion, f"风险评估结论: {conclusion}"), "conclusion": conclusion}


@auto_resolver("b1_3_evaluation_conclusion")
async def _resolve_b1_3_eval(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B1-3 业务评价表 承接承做意见 + 独立性判断（B1A/B1B 程序表步骤 4 自动推进）。

    数据来源: checklist_responses（item_id b1eval-opinion / b1eval-indep-has_independence_issue，
    经 working_paper→wp_index 关联 wp_code B1-3 或父码 B1）。
    返回结构: {"summary": str, "opinion": str|None, "independence_issue": bool}
    """
    rows = (await db.execute(sa.text("""
        SELECT cr.item_id, cr.conclusion
        FROM checklist_responses cr
        JOIN working_paper wp ON wp.id = cr.wp_id
        JOIN wp_index wi ON wi.id = wp.wp_index_id
        WHERE cr.project_id = :pid
          AND wi.wp_code IN ('B1-3', 'B1')
          AND cr.item_id IN ('b1eval-opinion', 'b1eval-indep-has_independence_issue')
    """), {"pid": str(project_id)})).fetchall()
    opinion = None
    indep_issue = False
    for r in rows:
        if r.item_id == "b1eval-opinion":
            opinion = r.conclusion
        elif r.item_id == "b1eval-indep-has_independence_issue" and r.conclusion == "是":
            indep_issue = True
    opinion_label = {"accept": "可以承接", "retain": "可以保持", "reject": "不予承接/保持"}
    if not opinion:
        return {"summary": "业务评价未完成", "opinion": None, "independence_issue": indep_issue}
    tail = "（⚠️独立性存在问题）" if indep_issue else ""
    return {
        "summary": f"✓ 业务评价：{opinion_label.get(opinion, opinion)}{tail}",
        "opinion": opinion,
        "independence_issue": indep_issue,
    }


@auto_resolver("b1_5_kaa_status")
async def _resolve_b1_5_kaa(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B1-5 KAA 检查结论（B1A/B1B 程序表步骤 5.4 自动推进）。

    数据来源: checklist_responses（item_id b1kaa-overall-conclusion 手工覆盖优先；
    否则按 b1kaa-standard-% 任一"是" 判定达到）。
    返回结构: {"summary": str, "reached": bool}
    """
    rows = (await db.execute(sa.text("""
        SELECT cr.item_id, cr.conclusion
        FROM checklist_responses cr
        JOIN working_paper wp ON wp.id = cr.wp_id
        JOIN wp_index wi ON wi.id = wp.wp_index_id
        WHERE cr.project_id = :pid
          AND wi.wp_code IN ('B1-5', 'B1')
          AND (cr.item_id = 'b1kaa-overall-conclusion' OR cr.item_id LIKE 'b1kaa-standard-%')
    """), {"pid": str(project_id)})).fetchall()
    manual = None
    reached = False
    has_any = False
    for r in rows:
        has_any = True
        if r.item_id == "b1kaa-overall-conclusion":
            manual = r.conclusion
        elif r.conclusion == "是":
            reached = True
    if manual:
        reached = manual == "reached"
    if not has_any:
        return {"summary": "KAA 检查未开始", "reached": False}
    return {
        "summary": "⚠️ 已达到 KAA 标准（需审批/报备）" if reached else "未达到 KAA 标准",
        "reached": reached,
    }


@auto_resolver("b19_related_party_count")
async def _resolve_b19_rp(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B19 关联方识别数。

    数据来源: related_party_registry 表
    返回结构: {"summary": str, "count": int}
    """
    from app.models.related_party_models import RelatedPartyRegistry
    count = (await db.execute(sa.select(sa.func.count()).select_from(RelatedPartyRegistry).where(
        RelatedPartyRegistry.project_id == project_id,
    ))).scalar() or 0
    return {"summary": f"已识别{count}个关联方" if count else "暂无已识别关联方", "count": count}


@auto_resolver("b15_materiality_summary")
async def _resolve_b15_materiality(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B15 重要性水平摘要（整体/执行/明显微小三级）。

    数据来源: materiality 表
    返回结构: {"summary": str, "overall_materiality": float|None, "performance_materiality": float, "trivial_amount": float}
    """
    from app.models.audit_platform_models import Materiality
    stmt = sa.select(
        Materiality.overall_materiality,
        Materiality.performance_materiality,
        Materiality.trivial_threshold,
    ).where(
        Materiality.project_id == project_id,
        Materiality.is_deleted == sa.false(),
    ).order_by(Materiality.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    row = result.first()
    if not row or not row.overall_materiality:
        return {"summary": "重要性水平待设置", "overall_materiality": None}
    overall = float(row.overall_materiality)
    perf = float(row.performance_materiality)
    trivial = float(row.trivial_threshold)
    return {
        "summary": f"整体重要性 ¥{overall:,.0f} / 执行重要性 ¥{perf:,.0f} / 明显微小 ¥{trivial:,.0f}",
        "overall_materiality": overall,
        "performance_materiality": perf,
        "trivial_amount": trivial,
    }


@auto_resolver("b22_entity_control_status")
async def _resolve_b22_control(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B22 企业层面控制完成率（5 维度已完成数/总数）。

    数据来源: workpaper_field_override 表（scope LIKE 'b22%'）
    返回结构: {"summary": str, "completed": int, "dimensions": int, "total_overrides": int, "completion_pct": int}
    """
    from app.models.workpaper_field_override_models import WorkpaperFieldOverride
    # 统计所有 B22 相关 scope 的覆盖条目数（总维度）
    total_stmt = sa.select(sa.func.count()).select_from(WorkpaperFieldOverride).where(
        WorkpaperFieldOverride.project_id == project_id,
        WorkpaperFieldOverride.scope.like("b22%"),
    )
    # 统计有非空 conclusion 值的条目（已完成维度）
    completed_stmt = sa.select(sa.func.count()).select_from(WorkpaperFieldOverride).where(
        WorkpaperFieldOverride.project_id == project_id,
        WorkpaperFieldOverride.scope.like("b22%"),
        WorkpaperFieldOverride.field == "conclusion",
        WorkpaperFieldOverride.value.isnot(None),
    )
    total = (await db.execute(total_stmt)).scalar() or 0
    completed = (await db.execute(completed_stmt)).scalar() or 0
    # B22A-1~5 为 5 个维度
    dimensions = 5
    pct = round(completed / dimensions * 100) if dimensions else 0
    return {
        "summary": f"企业层面控制 {completed}/{dimensions} 维度已完成（{pct}%）",
        "completed": completed,
        "dimensions": dimensions,
        "total_overrides": total,
        "completion_pct": pct,
    }


@auto_resolver("b23_walkthrough_progress")
async def _resolve_b23_progress(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B23 穿行测试完成率（14 循环已完成数/总数）。

    数据来源: workpaper_field_override 表（scope LIKE 'b23_walkthrough:%'）
    返回结构: {"summary": str, "completed": int, "total_cycles": int, "completion_pct": int}
    """
    from app.models.workpaper_field_override_models import WorkpaperFieldOverride
    total_cycles = 14  # B23-1~B23-14
    # 统计有 conclusion 字段的 distinct scope（每个 scope 代表一个已完成的 cycle）
    completed_stmt = sa.select(
        sa.func.count(sa.distinct(WorkpaperFieldOverride.scope))
    ).select_from(WorkpaperFieldOverride).where(
        WorkpaperFieldOverride.project_id == project_id,
        WorkpaperFieldOverride.scope.like("b23_walkthrough:%"),
        WorkpaperFieldOverride.field == "conclusion",
        WorkpaperFieldOverride.value.isnot(None),
    )
    completed = (await db.execute(completed_stmt)).scalar() or 0
    pct = round(completed / total_cycles * 100)
    return {
        "summary": f"穿行测试 {completed}/{total_cycles} 循环已完成（{pct}%）",
        "completed": completed,
        "total_cycles": total_cycles,
        "completion_pct": pct,
    }


@auto_resolver("b50_risk_summary")
async def _resolve_b50_risk(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B50 风险汇总统计（认定层次已评估风险数 + 特别风险数）。

    数据来源: checklist_responses（B50 底稿 B50-T3-* 单一真源，经 b50_risk_reader）
    返回结构: {"summary": str, "risk_factors": int, "special_risks": int}
    """
    from app.services.b50_risk_reader import load_b50_risks

    risks = await load_b50_risks(db, project_id)
    if not risks:
        return {"summary": "风险评估未完成", "risk_factors": 0, "special_risks": 0}
    special_count = sum(1 for r in risks if r["is_special_risk"])
    return {
        "summary": f"已识别{len(risks)}项认定层次风险，其中{special_count}项特别风险",
        "risk_factors": len(risks),
        "special_risks": special_count,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# C 类底稿 — 控制测试阶段 resolvers
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("control_test_result_for_cycle")
async def _resolve_control_test_result(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """D~N 读取对应循环控制测试结论。

    数据来源: field_override_service（scope='control_test_result:{cycle}'）
    返回结构: {"summary": str, "conclusion": str|None, "tested_controls": int, "deviation_count": int}
    参数: kw['cycle'] = 循环名称（如 '销售收入'）。
    """
    from app.services.field_override_service import FieldOverrideService
    cycle = kw.get("cycle", "")
    if not cycle:
        return {"summary": "未指定循环", "conclusion": None}
    svc = FieldOverrideService(db)
    scope = f"control_test_result:{cycle}"
    data = await svc.get_batch(project_id, year, scope=scope)
    if not data:
        return {"summary": f"控制测试（{cycle}）未完成", "conclusion": None}

    # Extract conclusion / tested_controls / deviation_count
    conclusion = None
    tested_controls = 0
    deviation_count = 0
    for _item_key, fields in data.items():
        if fields.get("conclusion"):
            conclusion = fields["conclusion"]
        if fields.get("tested_controls"):
            try:
                tested_controls += int(fields["tested_controls"])
            except (ValueError, TypeError):
                pass
        if fields.get("deviation_count"):
            try:
                deviation_count += int(fields["deviation_count"])
            except (ValueError, TypeError):
                pass
        # deviation_conclusion overrides main conclusion
        if fields.get("deviation_conclusion"):
            conclusion = fields["deviation_conclusion"]

    if not conclusion:
        return {"summary": f"控制测试（{cycle}）进行中", "conclusion": None}

    # Map conclusion to summary text
    label_map = {
        "有效": f"✓ 控制测试有效（{cycle}，已测试{tested_controls}项）",
        "部分有效": f"⚠️ 控制测试部分有效（{cycle}，偏差{deviation_count}项）",
        "无效": f"⚠️ 控制测试无效（{cycle}，已放弃信赖）",
    }
    summary = label_map.get(conclusion, f"控制测试结论: {conclusion}（{cycle}）")

    return {
        "summary": summary,
        "conclusion": conclusion,
        "tested_controls": tested_controls,
        "deviation_count": deviation_count,
    }


@auto_resolver("b22_entity_control_list")
async def _resolve_b22_entity_control_list(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B22 企业层面控制清单（C1 企业层面控制测试引用）。

    数据来源: workpaper_field_override 表（scope LIKE 'b22%'）
    返回结构: {"summary": str, "completed": int, "dimensions": int, "total_overrides": int}
    """
    from app.models.workpaper_field_override_models import WorkpaperFieldOverride
    # 统计 B22 维度已完成数
    total_stmt = sa.select(sa.func.count()).select_from(WorkpaperFieldOverride).where(
        WorkpaperFieldOverride.project_id == project_id,
        WorkpaperFieldOverride.scope.like("b22%"),
    )
    completed_stmt = sa.select(sa.func.count()).select_from(WorkpaperFieldOverride).where(
        WorkpaperFieldOverride.project_id == project_id,
        WorkpaperFieldOverride.scope.like("b22%"),
        WorkpaperFieldOverride.field == "conclusion",
        WorkpaperFieldOverride.value.isnot(None),
    )
    total = (await db.execute(total_stmt)).scalar() or 0
    completed = (await db.execute(completed_stmt)).scalar() or 0
    dimensions = 5  # B22A-1~5
    pct = round(completed / dimensions * 100) if dimensions else 0
    return {
        "summary": f"企业层面控制已识别，{completed}/{dimensions}维度已完成（{pct}%）",
        "completed": completed,
        "dimensions": dimensions,
        "total_overrides": total,
    }


@auto_resolver("itgc_test_result")
async def _resolve_itgc_test_result(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """ITGC 测试结论汇总（D~N 实质性程序引用）。

    数据来源: field_override_service（scope='itgc_test_result'）
    返回结构: {"summary": str, "sa": str|None, "pe": str|None, "pm": str|None, "ns": str|None, "overall": str|None, "finding_count": int}
    """
    from app.services.field_override_service import FieldOverrideService
    svc = FieldOverrideService(db)
    data = await svc.get_batch(project_id, year, scope="itgc_test_result")
    if not data:
        return {
            "summary": "IT一般控制测试未完成",
            "sa": None, "pe": None, "pm": None, "ns": None,
            "overall": None, "finding_count": 0,
        }
    # Extract values from the stored data
    fields = {}
    for _item_key, item_fields in data.items():
        fields.update(item_fields)

    sa_result = fields.get("sa")
    pe_result = fields.get("pe")
    pm_result = fields.get("pm")
    ns_result = fields.get("ns")
    overall = fields.get("overall")
    finding_count = int(fields.get("finding_count", 0))

    if overall:
        summary = f"ITGC 整体结论: {overall}（发现{finding_count}项）"
    else:
        summary = "IT一般控制测试进行中"

    return {
        "summary": summary,
        "sa": sa_result, "pe": pe_result, "pm": pm_result, "ns": ns_result,
        "overall": overall, "finding_count": finding_count,
    }
