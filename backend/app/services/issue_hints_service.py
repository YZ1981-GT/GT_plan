"""issue_hints_service — 舞弊/违规计数启发式 API

提供 get_issue_hints() 供 A17/A18 完成底稿 guidance 显示。

当前策略：纯标题关键词启发式（无 reason_code 写入端确证），
heuristic_only=True，召回不完备仅供提示。
"""

from uuid import UUID

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase15_models import IssueTicket

# 中文关键词
_FRAUD_KEYWORDS = ["舞弊", "虚假", "伪造", "篡改"]
_LEGAL_KEYWORDS = ["违法", "违规", "处罚", "法律"]

# severity 过滤
_SERIOUS_SEVERITIES = ("major", "blocker")


async def get_issue_hints(db: AsyncSession, project_id: UUID) -> dict:
    """查询项目 issue_tickets，按舞弊/违规映射返回计数+标题列表。

    映射策略（P1 纯标题关键词启发式）:
    - 舞弊: severity IN (major, blocker) AND title 含关键词(舞弊/虚假/伪造/篡改)
    - 违规: severity IN (major, blocker) AND title 含关键词(违法/违规/处罚/法律)

    reason_code='fraud'/'legal_compliance' 无写入端，退化为纯启发式。
    """
    # 构建舞弊查询条件
    fraud_title_filters = [IssueTicket.title.ilike(f"%{kw}%") for kw in _FRAUD_KEYWORDS]
    fraud_condition = and_(
        IssueTicket.project_id == project_id,
        IssueTicket.severity.in_(_SERIOUS_SEVERITIES),
        or_(*fraud_title_filters),
    )

    # 构建违规查询条件
    legal_title_filters = [IssueTicket.title.ilike(f"%{kw}%") for kw in _LEGAL_KEYWORDS]
    legal_condition = and_(
        IssueTicket.project_id == project_id,
        IssueTicket.severity.in_(_SERIOUS_SEVERITIES),
        or_(*legal_title_filters),
    )

    # 执行查询
    fraud_stmt = select(
        IssueTicket.id, IssueTicket.title, IssueTicket.severity
    ).where(fraud_condition)
    legal_stmt = select(
        IssueTicket.id, IssueTicket.title, IssueTicket.severity
    ).where(legal_condition)

    fraud_result = await db.execute(fraud_stmt)
    legal_result = await db.execute(legal_stmt)

    fraud_rows = fraud_result.all()
    legal_rows = legal_result.all()

    fraud_items = [
        {"id": str(row.id), "title": row.title, "severity": row.severity}
        for row in fraud_rows
    ]
    legal_items = [
        {"id": str(row.id), "title": row.title, "severity": row.severity}
        for row in legal_rows
    ]

    return {
        "fraud": {
            "count": len(fraud_items),
            "items": fraud_items,
            "heuristic_only": True,
            "note": "仅标题关键词启发式，召回不完备，仅供提示",
        },
        "legal_violation": {
            "count": len(legal_items),
            "items": legal_items,
            "heuristic_only": True,
            "note": "仅标题关键词启发式，召回不完备，仅供提示",
        },
    }
