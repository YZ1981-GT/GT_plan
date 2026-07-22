"""A17-5 核对表版本选择器

根据项目 business_category / scenario 判定哪些 A17-5 版本适用。

Rules（与 A17 程序表 applicable_categories=[A] 及 guidance 对齐）:
- A17-5-1 (财报审计): A 类必做；B 类可选；C 类不适用
- A17-5-2 (内控审计): 整合审计项目（A1/A5/A6 或 scenario 含 integrated）
- A17-5-3 (IPO 特别程序): IPO 项目 (A2 或 scenario='ipo') 必做
- A17-5-4 (新三板特别程序): 新三板项目 (B1) 必做
- A17-5-5 (函证程序): A/B 类推荐（非强制）
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services.business_category_service import get_category_prefix

_logger = logging.getLogger(__name__)

# A17-5 版本定义
_A17_5_VERSIONS: list[dict] = [
    {
        "wp_code": "A17-5-1",
        "title": "审计工作完成核对表（财报审计）",
        "description": "A 类必做；B 类可选",
    },
    {
        "wp_code": "A17-5-2",
        "title": "审计工作完成核对表（内控审计）",
        "description": "整合审计（A1/A5/A6 等）适用",
    },
    {
        "wp_code": "A17-5-3",
        "title": "审计工作完成核对表（IPO 特别程序）",
        "description": "A 类 IPO（A2）必做",
    },
    {
        "wp_code": "A17-5-4",
        "title": "审计工作完成核对表（新三板特别程序）",
        "description": "新三板/北交所（B1）必做",
    },
    {
        "wp_code": "A17-5-5",
        "title": "审计工作完成核对表（函证程序）",
        "description": "A/B 类推荐",
    },
]


def _determine_applicability(
    business_category: str | None,
    scenario: str | None,
) -> list[dict]:
    """纯逻辑：根据业务分类和场景判定各版本适用性。

    返回列表，每项含 wp_code / title / description / applicable / mandatory。
    """
    prefix = get_category_prefix(business_category or "")
    cat = (business_category or "").upper()
    scn = (scenario or "").lower()

    results: list[dict] = []
    for ver in _A17_5_VERSIONS:
        code = ver["wp_code"]
        applicable = False
        mandatory = False

        if code == "A17-5-1":
            # 财报审计：A 类必做，B 类可选
            applicable = prefix in ("A", "B")
            mandatory = prefix == "A"

        elif code == "A17-5-2":
            # 内控审计：整合审计项目（含内控审计的 A 类项目）
            # 整合审计通常是 A 类大型上市公司(A1)、央企(A5)等
            # 简化判定：A1/A5/A6 类或 scenario 含 integrated
            applicable = cat in ("A1", "A5", "A6") or "integrat" in scn
            mandatory = False

        elif code == "A17-5-3":
            # IPO 特别程序：A2 或 scenario='ipo'
            applicable = cat == "A2" or scn == "ipo"
            mandatory = cat == "A2" or scn == "ipo"

        elif code == "A17-5-4":
            # 新三板特别程序：B1
            applicable = cat == "B1"
            mandatory = cat == "B1"

        elif code == "A17-5-5":
            # 函证程序：所有 A/B 类推荐
            applicable = prefix in ("A", "B")
            mandatory = False

        results.append({
            "wp_code": code,
            "title": ver["title"],
            "description": ver["description"],
            "applicable": applicable,
            "mandatory": mandatory,
        })

    return results


async def get_applicable_versions(
    db: AsyncSession,
    project_id: UUID,
) -> list[dict]:
    """查询项目并返回适用的 A17-5 版本列表。

    Returns:
        [{"wp_code": "A17-5-1", "title": "...", "applicable": true, "mandatory": true}, ...]
    """
    stmt = select(Project.business_category, Project.scenario).where(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    )
    row = (await db.execute(stmt)).first()

    if row is None:
        _logger.warning("get_applicable_versions: project %s not found", project_id)
        # 安全默认：返回全部版本，5-1 和 5-5 适用
        return _determine_applicability(None, None)

    business_category, scenario = row
    return _determine_applicability(business_category, scenario)
