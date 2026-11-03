"""P2.3：真实 ORM 查询验证索引负责人姓名关联，不写共享数据库。"""
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.base import UserRole
from app.models.core import User
from app.models.staff_models import StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType
from app.routers.wp_relation_router import list_wp_index


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for model in (User, StaffMember, WpIndex, WorkingPaper):
            await connection.run_sync(model.__table__.create)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_index_names_follow_staff_user_relation_and_fallback(db):
    users = [User(username=f"auditor_{n}", email=f"{n}@test.invalid",
                  hashed_password="x", role=UserRole.auditor) for n in range(3)]
    db.add_all(users)
    await db.flush()
    db.add_all([
        StaffMember(user_id=users[0].id, name="张审计"),
        StaffMember(user_id=users[2].id, name="已删除姓名", is_deleted=True),
    ])
    project_id = uuid4()
    entries = []
    for n, code in enumerate(("S32-1", "S33-1", "S34-1", "S35-1")):
        entry = WpIndex(project_id=project_id, wp_code=code, wp_name="测试底稿",
                        assigned_to=users[n].id if n < 3 else None,
                        reviewer=users[1].id if n == 0 else None)
        db.add(entry)
        entries.append(entry)
    await db.flush()
    paper = WorkingPaper(project_id=project_id, wp_index_id=entries[0].id,
                         file_path="test.xlsx", source_type=WpSourceType.template)
    db.add(paper)
    await db.flush()
    result = await list_wp_index(project_id, db=db, current_user=users[0])
    assert [item["assignee_name"] for item in result] == [
        "张审计", users[1].username, users[2].username, None,
    ]
    assert result[0]["reviewer_name"] == users[1].username
    assert result[0]["wp_id"] == str(paper.id)
    assert result[1]["wp_id"] is None
    assert result[0]["assigned_to"] == str(users[0].id)
    assert await list_wp_index(uuid4(), db=db, current_user=users[0]) == []
