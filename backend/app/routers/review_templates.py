"""复核意见模板库 API — Phase 7 F4

提供复核意见模板的 CRUD + 使用次数递增功能。
- GET /api/review-templates: 列出模板（支持 search + cycle 过滤）
- POST /api/review-templates: 创建模板
- PUT /api/review-templates/{id}: 更新模板
- DELETE /api/review-templates/{id}: 软删除
- POST /api/review-templates/{id}/use: 递增使用次数

预置 10 条常用复核意见模板（seed data）。
注册到 router_registry 协作域 §108。

Validates: Requirements F4.2, F4.3, F4.6, F4.7
"""

import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(
    prefix="/api/review-templates",
    tags=["review-templates"],
)

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ReviewTemplateCreate(BaseModel):
    title: str
    content: str
    applicable_cycles: list[str] = []
    priority_tag: Literal["must_fix", "suggest", "info"] = "suggest"


class ReviewTemplateResponse(BaseModel):
    id: str
    title: str
    content: str
    applicable_cycles: list[str]
    priority_tag: str
    use_count: int
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Seed data: 10 common review templates
# ---------------------------------------------------------------------------

SEED_TEMPLATES = [
    {
        "title": "函证回函差异未调节",
        "content": "函证回函金额与账面金额存在差异，请补充差异调节表并说明差异原因。",
        "applicable_cycles": ["D", "E", "L"],
        "priority_tag": "must_fix",
    },
    {
        "title": "截止测试异常",
        "content": "截止测试发现跨期交易，请核实相关凭证并确认是否需要调整分录。",
        "applicable_cycles": ["D", "F"],
        "priority_tag": "must_fix",
    },
    {
        "title": "减值测试假设不合理",
        "content": "减值测试中使用的折现率/增长率假设缺乏充分依据，建议补充行业对标数据或管理层说明。",
        "applicable_cycles": ["G", "H", "I"],
        "priority_tag": "must_fix",
    },
    {
        "title": "审定表与试算表不一致",
        "content": "审定表合计数与试算表余额存在差异，请核对并修正。",
        "applicable_cycles": ["D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"],
        "priority_tag": "must_fix",
    },
    {
        "title": "抽样范围不足",
        "content": "实质性程序抽样覆盖率偏低，建议扩大抽样范围或补充说明抽样方法的合理性。",
        "applicable_cycles": ["D", "F", "K"],
        "priority_tag": "suggest",
    },
    {
        "title": "关联方交易披露不完整",
        "content": "关联方交易清单与附注披露存在遗漏，请补充完整关联方交易明细。",
        "applicable_cycles": ["D", "F", "G"],
        "priority_tag": "suggest",
    },
    {
        "title": "折旧计提方法变更未说明",
        "content": "本期折旧计提方法或使用年限发生变更，请补充会计估计变更说明及影响分析。",
        "applicable_cycles": ["H"],
        "priority_tag": "suggest",
    },
    {
        "title": "期后事项关注",
        "content": "请关注资产负债表日后事项，确认是否存在需要调整或披露的期后事项。",
        "applicable_cycles": ["D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"],
        "priority_tag": "info",
    },
    {
        "title": "底稿交叉引用缺失",
        "content": "当前底稿缺少与相关底稿的交叉引用，建议补充引用关系以增强审计轨迹完整性。",
        "applicable_cycles": ["D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"],
        "priority_tag": "info",
    },
    {
        "title": "程序执行记录不完整",
        "content": "部分审计程序缺少执行记录或结论，请补充完善程序表中的执行情况说明。",
        "applicable_cycles": ["D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"],
        "priority_tag": "suggest",
    },
]


# ---------------------------------------------------------------------------
# GET /api/review-templates
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ReviewTemplateResponse])
async def list_templates(
    search: str | None = Query(None, description="搜索关键词"),
    cycle: str | None = Query(None, description="循环过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ReviewTemplateResponse]:
    """列出模板（支持搜索+循环过滤）"""
    query = "SELECT id, title, content, applicable_cycles, priority_tag, use_count, created_at, updated_at FROM review_templates WHERE is_deleted = FALSE"
    params: dict = {}

    if search:
        query += " AND (title ILIKE :search OR content ILIKE :search)"
        params["search"] = f"%{search}%"

    if cycle:
        query += " AND applicable_cycles @> :cycle::jsonb"
        params["cycle"] = json.dumps([cycle])

    query += " ORDER BY use_count DESC, created_at DESC"

    result = await db.execute(sql_text(query), params)
    rows = result.fetchall()

    return [
        ReviewTemplateResponse(
            id=str(row[0]),
            title=row[1],
            content=row[2],
            applicable_cycles=row[3] if isinstance(row[3], list) else json.loads(row[3]) if row[3] else [],
            priority_tag=row[4],
            use_count=row[5],
            created_at=row[6].isoformat() if row[6] else "",
            updated_at=row[7].isoformat() if row[7] else "",
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# POST /api/review-templates
# ---------------------------------------------------------------------------


@router.post("", response_model=ReviewTemplateResponse)
async def create_template(
    body: ReviewTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewTemplateResponse:
    """创建模板"""
    template_id = uuid.uuid4()
    now = datetime.utcnow()

    await db.execute(
        sql_text(
            "INSERT INTO review_templates (id, title, content, applicable_cycles, priority_tag, use_count, created_by, is_deleted, created_at, updated_at) "
            "VALUES (:id, :title, :content, :cycles::jsonb, :tag, 0, :uid, FALSE, :now, :now)"
        ),
        {
            "id": str(template_id),
            "title": body.title,
            "content": body.content,
            "cycles": json.dumps(body.applicable_cycles),
            "tag": body.priority_tag,
            "uid": str(current_user.id),
            "now": now,
        },
    )
    await db.commit()

    return ReviewTemplateResponse(
        id=str(template_id),
        title=body.title,
        content=body.content,
        applicable_cycles=body.applicable_cycles,
        priority_tag=body.priority_tag,
        use_count=0,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )


# ---------------------------------------------------------------------------
# PUT /api/review-templates/{template_id}
# ---------------------------------------------------------------------------


@router.put("/{template_id}", response_model=ReviewTemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    body: ReviewTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewTemplateResponse:
    """更新模板"""
    # Check exists
    result = await db.execute(
        sql_text(
            "SELECT id FROM review_templates WHERE id = :id AND is_deleted = FALSE"
        ),
        {"id": str(template_id)},
    )
    if result.first() is None:
        raise HTTPException(status_code=404, detail="模板不存在")

    now = datetime.utcnow()
    await db.execute(
        sql_text(
            "UPDATE review_templates SET title = :title, content = :content, "
            "applicable_cycles = :cycles::jsonb, priority_tag = :tag, updated_at = :now "
            "WHERE id = :id"
        ),
        {
            "id": str(template_id),
            "title": body.title,
            "content": body.content,
            "cycles": json.dumps(body.applicable_cycles),
            "tag": body.priority_tag,
            "now": now,
        },
    )
    await db.commit()

    return ReviewTemplateResponse(
        id=str(template_id),
        title=body.title,
        content=body.content,
        applicable_cycles=body.applicable_cycles,
        priority_tag=body.priority_tag,
        use_count=0,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )


# ---------------------------------------------------------------------------
# DELETE /api/review-templates/{template_id}
# ---------------------------------------------------------------------------


@router.delete("/{template_id}")
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """软删除模板"""
    result = await db.execute(
        sql_text(
            "SELECT id FROM review_templates WHERE id = :id AND is_deleted = FALSE"
        ),
        {"id": str(template_id)},
    )
    if result.first() is None:
        raise HTTPException(status_code=404, detail="模板不存在")

    await db.execute(
        sql_text(
            "UPDATE review_templates SET is_deleted = TRUE, updated_at = :now WHERE id = :id"
        ),
        {"id": str(template_id), "now": datetime.utcnow()},
    )
    await db.commit()

    return {"success": True, "message": "模板已删除"}


# ---------------------------------------------------------------------------
# POST /api/review-templates/{template_id}/use
# ---------------------------------------------------------------------------


@router.post("/{template_id}/use")
async def increment_use_count(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """递增使用次数"""
    result = await db.execute(
        sql_text(
            "UPDATE review_templates SET use_count = use_count + 1, updated_at = :now "
            "WHERE id = :id AND is_deleted = FALSE "
            "RETURNING use_count"
        ),
        {"id": str(template_id), "now": datetime.utcnow()},
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="模板不存在")

    await db.commit()
    return {"success": True, "use_count": row[0]}


# ---------------------------------------------------------------------------
# Seed function: insert 10 common templates if table is empty
# ---------------------------------------------------------------------------


async def seed_review_templates(db: AsyncSession) -> int:
    """预置 10 条常用复核意见模板（仅在表为空时执行）"""
    result = await db.execute(
        sql_text("SELECT COUNT(*) FROM review_templates")
    )
    count = result.scalar()
    if count and count > 0:
        return 0

    inserted = 0
    for tpl in SEED_TEMPLATES:
        await db.execute(
            sql_text(
                "INSERT INTO review_templates (id, title, content, applicable_cycles, priority_tag, use_count, is_deleted, created_at, updated_at) "
                "VALUES (:id, :title, :content, :cycles::jsonb, :tag, 0, FALSE, NOW(), NOW())"
            ),
            {
                "id": str(uuid.uuid4()),
                "title": tpl["title"],
                "content": tpl["content"],
                "cycles": json.dumps(tpl["applicable_cycles"]),
                "tag": tpl["priority_tag"],
            },
        )
        inserted += 1

    await db.commit()
    return inserted
