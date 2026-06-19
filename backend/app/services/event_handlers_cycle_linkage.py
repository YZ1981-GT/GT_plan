"""循环联动事件处理器 — C/F/D~N 类底稿保存联动。

从 event_handlers.py 拆出（#3 改进），保持主文件体积可控。
由 register_event_handlers() 末尾调用 register_cycle_linkage_handlers() 完成注册。

联动链路：
- C2~C15 控制测试 → field_overrides scope=control_test_result:{cycle}
- C{n}-2 偏差评价 → IssueTicket + control_test_result 联动更新
- C22 ITGC → C21-1 findings
- F2-21~58 子底稿结论 → f_procedure_status:{wp_code}
- D~N {cycle}{n}-1 审定表 → trial_balance.audited_amount 回写
"""
from __future__ import annotations

import logging
import re

from app.core.database import async_session as async_session_factory
from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.event_bus import event_bus
from app.services.procedure_table_auto_service import invalidate_auto_cache

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# C 类联动
# ═══════════════════════════════════════════════════════════════════════════════

_C_CYCLE_NAMES: dict[str, str] = {
    "C2": "销售收入", "C3": "货币资金", "C4": "采购存货",
    "C5": "投资", "C6": "固定资产", "C7": "在建工程",
    "C8": "无形资产", "C9": "研发", "C10": "职工薪酬",
    "C11": "管理", "C12": "税费", "C13": "债务",
    "C14": "租赁", "C15": "关联方",
}


async def _on_c_control_test_saved(payload: EventPayload) -> None:
    """C2~C15 控制测试保存 → 写入控制测试结论到 field_overrides。"""
    wp_code = payload.extra.get("wp_code", "") if payload.extra else ""
    m = re.match(r"^C(\d{1,2})$", wp_code)
    if not m:
        return
    n = int(m.group(1))
    if not (2 <= n <= 15):
        return

    cycle = _C_CYCLE_NAMES.get(wp_code, "")
    if not cycle:
        return

    project_id = payload.project_id
    year = payload.year
    if not project_id or not year:
        return

    parsed_data = payload.extra.get("parsed_data") or {} if payload.extra else {}
    conclusion = (
        parsed_data.get("conclusion")
        or parsed_data.get("summary_conclusion")
        or parsed_data.get("overall_conclusion")
    )
    tested_controls = parsed_data.get("tested_controls", 0)
    deviation_count = parsed_data.get("deviation_count", 0)

    async with async_session_factory() as session:
        try:
            from app.services.field_override_service import FieldOverrideService
            svc = FieldOverrideService(session)
            scope = f"control_test_result:{cycle}"

            if conclusion:
                await svc.set(project_id=project_id, year=year, scope=scope,
                              item_key=wp_code, field="conclusion", value=str(conclusion))
            if tested_controls:
                await svc.set(project_id=project_id, year=year, scope=scope,
                              item_key=wp_code, field="tested_controls", value=str(tested_controls))
            await svc.set(project_id=project_id, year=year, scope=scope,
                          item_key=wp_code, field="deviation_count", value=str(deviation_count))
            await session.commit()
            logger.info("[C→D~N] Control test result saved for %s (%s) project=%s conclusion=%s",
                        wp_code, cycle, project_id, conclusion)
            invalidate_auto_cache(project_id, year)
        except Exception:
            await session.rollback()
            logger.warning("[C→D~N] Failed to save control test result for %s project=%s",
                           wp_code, project_id, exc_info=True)


async def _on_c_deviation_saved(payload: EventPayload) -> None:
    """C{n}-2 偏差评价保存 → 自动创建问题工单 + 联动更新控制测试结论。"""
    wp_code = payload.extra.get("wp_code", "") if payload.extra else ""
    m = re.match(r"^C(\d{1,2})-2$", wp_code)
    if not m:
        return
    n = int(m.group(1))
    if not (2 <= n <= 15):
        return

    parent_wp_code = f"C{n}"
    cycle = _C_CYCLE_NAMES.get(parent_wp_code, "")
    if not cycle:
        return

    project_id = payload.project_id
    year = payload.year
    if not project_id or not year:
        return

    parsed_data = payload.extra.get("parsed_data") or {} if payload.extra else {}
    rows = parsed_data.get("rows", [])
    if not rows:
        return

    async with async_session_factory() as session:
        try:
            from app.models.phase15_models import IssueTicket

            issues_created = 0
            conclusion_override = None

            for idx, row in enumerate(rows):
                step7 = row.get("step7_report_deficiency") or row.get("report_deficiency")
                if step7 == "是":
                    ticket = IssueTicket(
                        project_id=project_id,
                        source="consistency",
                        severity="major",
                        category="control_deficiency",
                        title=f"控制偏差-{cycle}-{row.get('control_name', f'偏差{idx+1}')}",
                        description=row.get("deviation_description", ""),
                        owner_id=project_id,
                        trace_id=f"c_deviation:{wp_code}:{idx}",
                    )
                    session.add(ticket)
                    issues_created += 1

                deviation_conclusion = row.get("conclusion") or row.get("deviation_conclusion")
                if deviation_conclusion in ("无效需扩大测试", "无效且已放弃信赖"):
                    if deviation_conclusion == "无效且已放弃信赖":
                        conclusion_override = "无效"
                    elif conclusion_override != "无效":
                        conclusion_override = "部分有效"

            if conclusion_override:
                from app.services.field_override_service import FieldOverrideService
                svc = FieldOverrideService(session)
                scope = f"control_test_result:{cycle}"
                await svc.set(project_id=project_id, year=year, scope=scope,
                              item_key=wp_code, field="deviation_conclusion", value=conclusion_override)
                await svc.set(project_id=project_id, year=year, scope=scope,
                              item_key=parent_wp_code, field="conclusion", value=conclusion_override)

            await session.commit()
            if issues_created:
                logger.info("[C偏差→IssueTicket] Created %d tickets for %s (%s) project=%s",
                            issues_created, wp_code, cycle, project_id)
            if conclusion_override:
                logger.info("[C偏差→结论] Updated control_test_result for %s → %s project=%s",
                            cycle, conclusion_override, project_id)
                invalidate_auto_cache(project_id, year)
        except Exception:
            await session.rollback()
            logger.warning("[C偏差] Failed to process deviation for %s project=%s",
                           wp_code, project_id, exc_info=True)


async def _on_c22_itgc_saved(payload: EventPayload) -> None:
    """C22 ITGC 测试保存 → 当步骤结论"无效"时写入 C21-1 发现记录。"""
    wp_code = payload.extra.get("wp_code", "") if payload.extra else ""
    if wp_code != "C22":
        return

    project_id = payload.project_id
    year = payload.year
    if not project_id or not year:
        return

    parsed_data = payload.extra.get("parsed_data") or {} if payload.extra else {}
    steps = parsed_data.get("step_conclusions") or parsed_data.get("steps", [])
    if not steps:
        return

    findings = []
    if isinstance(steps, dict):
        for step_name, conclusion in steps.items():
            if conclusion == "无效":
                findings.append({"source": "C22", "step": step_name, "conclusion": "无效"})
    elif isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict) and step.get("conclusion") == "无效":
                findings.append({
                    "source": "C22",
                    "step": step.get("name", step.get("step_name", "")),
                    "domain": step.get("domain", ""),
                    "conclusion": "无效",
                })

    if not findings:
        return

    async with async_session_factory() as session:
        try:
            from app.services.field_override_service import FieldOverrideService
            svc = FieldOverrideService(session)

            for idx, finding in enumerate(findings):
                item_key = f"finding_{idx + 1}"
                await svc.set(project_id=project_id, year=year, scope="c21_1_findings",
                              item_key=item_key, field="source", value=finding["source"])
                await svc.set(project_id=project_id, year=year, scope="c21_1_findings",
                              item_key=item_key, field="step", value=finding.get("step", ""))
                await svc.set(project_id=project_id, year=year, scope="c21_1_findings",
                              item_key=item_key, field="domain", value=finding.get("domain", ""))
                await svc.set(project_id=project_id, year=year, scope="c21_1_findings",
                              item_key=item_key, field="conclusion", value="无效")

            await session.commit()
            logger.info("[C22→C21-1] Created %d finding records for project=%s", len(findings), project_id)
        except Exception:
            await session.rollback()
            logger.warning("[C22→C21-1] Failed to create findings for project=%s", project_id, exc_info=True)


# ═══════════════════════════════════════════════════════════════════════════════
# F 类联动
# ═══════════════════════════════════════════════════════════════════════════════

_F_CONCLUSION_RANGES = [(21, 26), (29, 35), (38, 44), (47, 49), (55, 58)]


def _is_f_conclusion_wp(wp_code: str) -> bool:
    """判断 wp_code 是否属于 F 类结论底稿范围。"""
    m = re.match(r"^F2-(\d+)$", wp_code)
    if not m:
        return False
    n = int(m.group(1))
    return any(start <= n <= end for start, end in _F_CONCLUSION_RANGES)


async def _on_f_workpaper_conclusion_saved(payload: EventPayload) -> None:
    """F 类子底稿保存 → 写入结论到 field_overrides，供 F2A 程序表展示步骤状态。"""
    wp_code = payload.extra.get("wp_code", "") if payload.extra else ""
    if not _is_f_conclusion_wp(wp_code):
        return

    project_id = payload.project_id
    year = payload.year
    if not project_id or not year:
        return

    parsed_data = payload.extra.get("parsed_data") or {} if payload.extra else {}
    conclusion = (
        parsed_data.get("conclusion")
        or parsed_data.get("summary_conclusion")
        or parsed_data.get("overall_conclusion")
        or parsed_data.get("audit_conclusion")
    )
    status = parsed_data.get("status", "in_progress")

    async with async_session_factory() as session:
        try:
            from app.services.field_override_service import FieldOverrideService
            svc = FieldOverrideService(session)
            scope = f"f_procedure_status:{wp_code}"

            if conclusion:
                await svc.set(project_id=project_id, year=year, scope=scope,
                              item_key=wp_code, field="conclusion", value=str(conclusion))
            await svc.set(project_id=project_id, year=year, scope=scope,
                          item_key=wp_code, field="status",
                          value=str(status) if conclusion else "in_progress")
            await session.commit()
            logger.info("[F→F2A] Conclusion saved for %s project=%s conclusion=%s",
                        wp_code, project_id, conclusion)
            invalidate_auto_cache(project_id, year)
        except Exception:
            await session.rollback()
            logger.warning("[F→F2A] Failed to save conclusion for %s project=%s",
                           wp_code, project_id, exc_info=True)


# ═══════════════════════════════════════════════════════════════════════════════
# D~N 审定表回写
# ═══════════════════════════════════════════════════════════════════════════════


async def _on_d_audit_determination_saved(payload: EventPayload) -> None:
    """D~N 类审定表保存 → 回写 audited_amount 到 trial_balance。"""
    wp_code = payload.extra.get("wp_code", "") if payload.extra else ""
    if not re.match(r"^[D-N]\d+-1$", wp_code):
        return

    project_id = payload.project_id
    year = payload.year
    if not project_id or not year:
        logger.warning("_on_d_audit_determination_saved: missing project_id or year, wp_code=%s", wp_code)
        return

    parsed_data = payload.extra.get("parsed_data") or {} if payload.extra else {}
    rows = parsed_data.get("rows", [])
    if not rows:
        return

    async with async_session_factory() as session:
        try:
            from decimal import Decimal
            from sqlalchemy import update as _update
            from app.models.trial_balance_models import TrialBalance
            import sqlalchemy as sa

            updated_count = 0
            for row in rows:
                account_code = row.get("account_code") or row.get("standard_account_code")
                audited = row.get("audited_amount")
                if account_code and audited is not None:
                    try:
                        audited_val = Decimal(str(audited))
                    except Exception:
                        continue

                    stmt = (
                        _update(TrialBalance)
                        .where(
                            TrialBalance.project_id == project_id,
                            TrialBalance.year == year,
                            TrialBalance.standard_account_code == account_code,
                        )
                        .values(audited_amount=audited_val)
                    )
                    result = await session.execute(stmt)
                    if result.rowcount > 0:
                        updated_count += 1

            await session.commit()
            if updated_count:
                logger.info("[%s→TB] Wrote back audited_amount for %d accounts from %s project=%s year=%s",
                            wp_code[0], updated_count, wp_code, project_id, year)
                await event_bus.publish_immediate(EventPayload(
                    event_type=EventType.TRIAL_BALANCE_UPDATED,
                    project_id=project_id,
                    year=year,
                    account_codes=payload.account_codes,
                    extra={"source": f"d_audit_determination:{wp_code}"},
                ))
        except Exception:
            await session.rollback()
            logger.warning("[%s→TB] Failed to write back audited_amount for %s project=%s",
                           wp_code[0] if wp_code else "?", wp_code, project_id, exc_info=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 注册入口
# ═══════════════════════════════════════════════════════════════════════════════


def register_cycle_linkage_handlers() -> None:
    """注册所有循环联动 handlers 到全局 EventBus。

    由 event_handlers.register_event_handlers() 末尾调用。
    """
    event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_c_control_test_saved)
    event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_c_deviation_saved)
    event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_c22_itgc_saved)
    event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_f_workpaper_conclusion_saved)
    event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_d_audit_determination_saved)
    logger.debug("Cycle linkage handlers registered (C/F/D~N)")
