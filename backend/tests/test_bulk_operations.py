"""bulk_execute savepoint 隔离测试

验证 bulk_execute 使用 db.begin_nested() 为每个操作创建 savepoint，
确保部分失败不影响其他操作的成功提交。

Validates: Requirements P0.3
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.bulk_operations import BulkResult, bulk_execute, bulk_soft_delete


# ---------------------------------------------------------------------------
# 测试用 ORM 模型（独立 Base，不污染全局 metadata）
# ---------------------------------------------------------------------------

class _TestBase(DeclarativeBase):
    pass


class _Item(_TestBase):
    """测试用简单模型，带 soft_delete 支持。"""
    __tablename__ = "bulk_test_items"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    value: Mapped[int] = mapped_column(sa.Integer, default=0)
    is_deleted: Mapped[bool] = mapped_column(sa.Boolean, default=False)

    def soft_delete(self) -> None:
        self.is_deleted = True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def engine():
    """SQLite 内存引擎，每个测试独立。"""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine):
    """提供一个 AsyncSession，测试结束后回滚。"""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.fixture
async def items(session: AsyncSession):
    """预插入 3 条测试记录，返回 UUID 列表。"""
    records = [
        _Item(id=uuid.uuid4(), name=f"item-{i}", value=i * 10)
        for i in range(3)
    ]
    session.add_all(records)
    await session.commit()
    return records


# ---------------------------------------------------------------------------
# 辅助 action_fn
# ---------------------------------------------------------------------------

async def _increment_value(db: AsyncSession, row: _Item) -> None:
    """正常操作：将 value +1。"""
    row.value += 1


async def _always_fail(db: AsyncSession, row: _Item) -> None:
    """总是抛出异常的操作。"""
    raise ValueError("故意失败")


def _fail_for_ids(*fail_ids: uuid.UUID):
    """返回一个 action_fn：对指定 ID 抛异常，其余正常 +1。"""
    async def _action(db: AsyncSession, row: _Item) -> None:
        if row.id in fail_ids:
            raise ValueError(f"id={row.id} 故意失败")
        row.value += 1
    return _action


# ---------------------------------------------------------------------------
# 测试：全部成功
# ---------------------------------------------------------------------------

class TestBulkExecuteAllSucceed:
    """所有操作成功时的基本行为。"""

    async def test_returns_all_succeeded(self, session: AsyncSession, items: list[_Item]):
        ids = [item.id for item in items]
        result = await bulk_execute(session, _Item, ids, _increment_value)

        assert result["success_count"] == 3
        assert result["fail_count"] == 0
        assert len(result["succeeded"]) == 3
        assert result["failed"] == []

    async def test_total_equals_input_count(self, session: AsyncSession, items: list[_Item]):
        ids = [item.id for item in items]
        result = await bulk_execute(session, _Item, ids, _increment_value)
        assert result["total"] == len(ids)

    async def test_values_updated_after_commit(self, session: AsyncSession, items: list[_Item]):
        """成功操作的变更在 commit 后持久化。"""
        ids = [item.id for item in items]
        original_values = {item.id: item.value for item in items}

        await bulk_execute(session, _Item, ids, _increment_value)
        await session.commit()

        # 重新查询验证
        for item in items:
            await session.refresh(item)
            assert item.value == original_values[item.id] + 1


# ---------------------------------------------------------------------------
# 测试：全部失败
# ---------------------------------------------------------------------------

class TestBulkExecuteAllFail:
    """所有操作失败时的行为。"""

    async def test_returns_all_failed(self, session: AsyncSession, items: list[_Item]):
        ids = [item.id for item in items]
        result = await bulk_execute(session, _Item, ids, _always_fail)

        assert result["success_count"] == 0
        assert result["fail_count"] == 3
        assert result["succeeded"] == []
        assert len(result["failed"]) == 3

    async def test_failed_items_have_error_message(self, session: AsyncSession, items: list[_Item]):
        ids = [item.id for item in items]
        result = await bulk_execute(session, _Item, ids, _always_fail)

        for failed_item in result["failed"]:
            assert "error" in failed_item
            assert failed_item["error"] == "故意失败"

    async def test_no_changes_after_all_fail(self, session: AsyncSession, items: list[_Item]):
        """全部失败时，数据库不应有任何变更。"""
        ids = [item.id for item in items]
        original_values = {item.id: item.value for item in items}

        await bulk_execute(session, _Item, ids, _always_fail)
        await session.commit()

        for item in items:
            await session.refresh(item)
            assert item.value == original_values[item.id], (
                f"item {item.id} 的 value 不应改变"
            )


# ---------------------------------------------------------------------------
# 测试：部分失败 — savepoint 隔离核心验证
# ---------------------------------------------------------------------------

class TestBulkExecutePartialFailure:
    """部分失败时，savepoint 隔离确保成功操作不受影响。"""

    async def test_partial_failure_correct_counts(
        self, session: AsyncSession, items: list[_Item]
    ):
        """1 个失败，2 个成功 — 计数正确。"""
        fail_id = items[0].id
        ids = [item.id for item in items]

        result = await bulk_execute(session, _Item, ids, _fail_for_ids(fail_id))

        assert result["success_count"] == 2
        assert result["fail_count"] == 1
        assert str(fail_id) in [f["id"] for f in result["failed"]]

    async def test_successful_items_persisted_after_partial_failure(
        self, session: AsyncSession, items: list[_Item]
    ):
        """关键测试：部分失败后，成功的操作应被持久化（savepoint 隔离）。"""
        fail_id = items[0].id
        success_ids = [item.id for item in items[1:]]
        ids = [item.id for item in items]

        original_values = {item.id: item.value for item in items}

        await bulk_execute(session, _Item, ids, _fail_for_ids(fail_id))
        await session.commit()

        # 成功的 2 条应该 +1
        for item in items[1:]:
            await session.refresh(item)
            assert item.value == original_values[item.id] + 1, (
                f"成功操作 {item.id} 的变更应被持久化"
            )

        # 失败的 1 条不应改变
        await session.refresh(items[0])
        assert items[0].value == original_values[fail_id], (
            f"失败操作 {fail_id} 的数据不应改变（savepoint 已回滚）"
        )

    async def test_failed_item_not_persisted(
        self, session: AsyncSession, items: list[_Item]
    ):
        """失败操作的脏数据不应被 flush（savepoint rollback 保证）。"""
        # 使用一个会修改数据后再抛异常的 action_fn
        async def _modify_then_fail(db: AsyncSession, row: _Item) -> None:
            row.value = 99999  # 修改数据
            raise RuntimeError("修改后失败")

        target = items[0]
        original_value = target.value
        ids = [target.id]

        await bulk_execute(session, _Item, ids, _modify_then_fail)
        await session.commit()

        await session.refresh(target)
        assert target.value == original_value, (
            "savepoint rollback 应撤销修改后失败的脏数据"
        )

    async def test_middle_item_fails_others_succeed(
        self, session: AsyncSession, items: list[_Item]
    ):
        """中间一条失败，前后两条都应成功。"""
        fail_id = items[1].id  # 中间那条
        ids = [item.id for item in items]
        original_values = {item.id: item.value for item in items}

        result = await bulk_execute(session, _Item, ids, _fail_for_ids(fail_id))
        await session.commit()

        assert result["success_count"] == 2
        assert result["fail_count"] == 1

        # 第 0 条和第 2 条应成功
        for item in [items[0], items[2]]:
            await session.refresh(item)
            assert item.value == original_values[item.id] + 1

        # 第 1 条（失败）不应改变
        await session.refresh(items[1])
        assert items[1].value == original_values[fail_id]


# ---------------------------------------------------------------------------
# 测试：不存在的 ID
# ---------------------------------------------------------------------------

class TestBulkExecuteNonExistentIds:
    """不存在的 ID 应被标记为失败。"""

    async def test_nonexistent_id_in_failed(self, session: AsyncSession, items: list[_Item]):
        ghost_id = uuid.uuid4()
        ids = [items[0].id, ghost_id]

        result = await bulk_execute(session, _Item, ids, _increment_value)

        assert result["fail_count"] == 1
        assert result["success_count"] == 1
        failed_ids = [f["id"] for f in result["failed"]]
        assert str(ghost_id) in failed_ids

    async def test_nonexistent_id_error_message(self, session: AsyncSession, items: list[_Item]):
        ghost_id = uuid.uuid4()
        result = await bulk_execute(session, _Item, [ghost_id], _increment_value)

        assert result["failed"][0]["error"] == "记录不存在"

    async def test_all_nonexistent(self, session: AsyncSession):
        ids = [uuid.uuid4(), uuid.uuid4()]
        result = await bulk_execute(session, _Item, ids, _increment_value)

        assert result["success_count"] == 0
        assert result["fail_count"] == 2
        assert result["total"] == 2


# ---------------------------------------------------------------------------
# 测试：bulk_soft_delete 集成
# ---------------------------------------------------------------------------

class TestBulkSoftDelete:
    """bulk_soft_delete 使用 bulk_execute，验证 savepoint 隔离在软删除场景下正常工作。"""

    async def test_soft_delete_marks_is_deleted(self, session: AsyncSession, items: list[_Item]):
        ids = [item.id for item in items]
        result = await bulk_soft_delete(session, _Item, ids)
        await session.commit()

        assert result["success_count"] == 3
        for item in items:
            await session.refresh(item)
            assert item.is_deleted is True

    async def test_soft_delete_already_deleted_fails(
        self, session: AsyncSession, items: list[_Item]
    ):
        """已删除的记录再次软删除应失败，其他记录不受影响。"""
        # 先删除第一条
        items[0].is_deleted = True
        await session.commit()

        ids = [item.id for item in items]
        result = await bulk_soft_delete(session, _Item, ids)
        await session.commit()

        # 第一条失败（已删除），其余两条成功
        assert result["fail_count"] == 1
        assert result["success_count"] == 2

        # 验证其余两条确实被软删除
        for item in items[1:]:
            await session.refresh(item)
            assert item.is_deleted is True
