"""归档门禁（spec attachment-archive-and-a-class-evidence ADR-AE-14）：与归档向导「下一步」同一口径，服务端现算。

向导第一步要求两件事都过才放行：就绪检查 ``ready``（导出门禁 + 补充类目：QC 未跑、审计报告未生成…）、完整性
自检 ``can_proceed``（缺失 / 未签字 / 未解决复核意见 / 过期 / 文件缺失）。改造前编排的门禁步骤只认客户端带来的
评估 id，无效或「未就绪」时退回只评导出门禁 ⇒ 向导里明明「存在阻断项，无法继续」，绕过向导直接调接口照样归档，
锁定步骤随即把项目和底稿都锁上（走查实测）。这里每次都现算，不信任客户端带来的评估 id。
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

#: 失败原因里每类最多列几项（完整清单在界面的完整性自检报告里）
_PER_CATEGORY = 20


class ArchiveGateBlocked(RuntimeError):
    """门禁未通过；``problems`` 逐项列出（编排器记进 ``section_progress.gate.problems``）。"""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"归档门禁未通过：{len(problems)} 项阻断（{problems[0]}）" if problems else "归档门禁未通过")


async def archive_gate_problems(db: AsyncSession, project_id: uuid.UUID, actor_id: uuid.UUID | None) -> list[str]:
    """阻断项清单；空列表 = 放行。"""
    from app.services.archive_completeness_service import CATEGORY_LABELS, get_archive_completeness_report
    from app.services.qc_dashboard_service import ArchiveReadinessService

    problems: list[str] = []
    readiness = await ArchiveReadinessService(db).check_readiness(project_id, actor_id=actor_id)
    for group in readiness.get("groups") or []:
        for finding in group.get("findings") or []:
            if finding.get("severity") == "blocking":
                problems.append(f"就绪检查｜{group.get('name') or ''}｜{finding.get('message') or finding.get('rule_code') or ''}")
    if not readiness.get("ready") and not problems:
        problems.append("就绪检查｜导出门禁｜未通过")

    report = await get_archive_completeness_report(db, project_id)
    for cat in report.categories:
        if not (cat.is_blocking and cat.count):
            continue
        label = CATEGORY_LABELS.get(cat.category, cat.category)
        problems.extend(f"完整性自检｜{label}｜{f'{i.wp_code} {i.wp_name}'.strip()}" for i in cat.items[:_PER_CATEGORY])
        if cat.count > _PER_CATEGORY:
            problems.append(f"完整性自检｜{label}｜……共 {cat.count} 项")
    return problems
