"""QC 抽查服务单元测试

Validates: Requirements 4 (Round 3)
- POST /api/qc/inspections 按策略生成批次 + items
- 四策略 random / risk_based / full_cycle / mixed 纯函数
- POST /inspections/{id}/items/{item_id}/verdict 质控人录入结论
- 抽查独立于项目组 wp_review_records
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.qc_inspection_models import QcInspection, QcInspectionItem
from app.models.workpaper_models import WorkingPaper, WpIndex

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ID = uuid.uuid4()
REVIEWER_ID = uuid.uuid4()


async def _seed_workpapers(
    db: AsyncSession,
    project_id: uuid.UUID = PROJECT_ID,
    count: int = 10,
    cycles: list[str] | None = None,
    review_statuses: list[str] | None = None,
) -> list[uuid.UUID]:
    """插入测试底稿，返回 wp_id 列表。"""
    if cycles is None:
        cycles = ["D", "F", "K", "N", "D", "F", "K", "N", "D", "F"]
    if review_statuses is None:
        review_statuses = ["not_submitted"] * count

    wp_ids = []
    for i in range(count):
        wp_index_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        idx = WpIndex(
            id=wp_index_id,
            project_id=project_id,
            wp_code=f"{cycles[i % len(cycles)]}-{i+1:03d}",
            wp_name=f"测试底稿 {i+1}",
            audit_cycle=cycles[i % len(cycles)],
            status="not_started",
        )
        db.add(idx)

        wp = WorkingPaper(
            id=wp_id,
            project_id=project_id,
            wp_index_id=wp_index_id,
            file_path=f"/tmp/wp_{i}.xlsx",
            source_type="upload",
            status="draft",
            review_status=review_statuses[i % len(review_statuses)],
        )
        db.add(wp)
        wp_ids.append(wp_id)

    await db.flush()
    return wp_ids


# ---------------------------------------------------------------------------
# 策略纯函数测试
# ---------------------------------------------------------------------------


class TestStrategyFunctions:
    """测试四种抽样策略纯函数。"""

    def _make_workpapers(self, count: int = 10) -> list[dict]:
        """生成测试底稿数据。"""
        cycles = ["D", "F", "K", "N"]
        wps = []
        for i in range(count):
            cycle = cycles[i % len(cycles)]
            complexity = {"D": 1, "F": 1, "K": 3, "N": 3}.get(cycle, 2)
            wps.append({
                "id": uuid.uuid4(),
                "audit_cycle": cycle,
                "complexity": complexity,
                "has_rejection": i % 5 == 0,  # 每 5 个有一个退回
                "wp_code": f"{cycle}-{i+1:03d}",
            })
        return wps

    def test_random_strategy_ratio(self):
        """随机策略按比例抽样。"""
        from app.services.qc_inspection_service import _sample_random

        wps = self._make_workpapers(20)
        result = _sample_random(wps, {"ratio": 0.1})
        # 10% of 20 = 2
        assert len(result) == 2
        # 所有结果都是有效 UUID
        assert all(isinstance(r, uuid.UUID) for r in result)

    def test_random_strategy_full_ratio(self):
        """随机策略 ratio=1.0 返回全部。"""
        from app.services.qc_inspection_service import _sample_random

        wps = self._make_workpapers(5)
        result = _sample_random(wps, {"ratio": 1.0})
        assert len(result) == 5

    def test_random_strategy_zero_ratio(self):
        """随机策略 ratio=0 返回空。"""
        from app.services.qc_inspection_service import _sample_random

        wps = self._make_workpapers(5)
        result = _sample_random(wps, {"ratio": 0})
        assert len(result) == 0

    def test_risk_based_strategy(self):
        """风险导向策略抽取高复杂度 + 退回底稿。"""
        from app.services.qc_inspection_service import _sample_risk_based

        wps = self._make_workpapers(20)
        result = _sample_risk_based(wps, {"complexity_threshold": 3, "include_rejected": True})

        # K/N 循环 complexity=3，加上退回的
        high_complexity_ids = {wp["id"] for wp in wps if wp["complexity"] >= 3}
        rejected_ids = {wp["id"] for wp in wps if wp["has_rejection"]}
        expected = high_complexity_ids | rejected_ids

        assert set(result) == expected

    def test_risk_based_no_rejected(self):
        """风险导向策略不包含退回底稿。"""
        from app.services.qc_inspection_service import _sample_risk_based

        wps = self._make_workpapers(20)
        result = _sample_risk_based(wps, {"complexity_threshold": 3, "include_rejected": False})

        high_complexity_ids = {wp["id"] for wp in wps if wp["complexity"] >= 3}
        assert set(result) == high_complexity_ids

    def test_full_cycle_strategy(self):
        """全循环策略抽取指定循环全部底稿。"""
        from app.services.qc_inspection_service import _sample_full_cycle

        wps = self._make_workpapers(20)
        result = _sample_full_cycle(wps, {"cycles": ["D", "K"]})

        expected = {wp["id"] for wp in wps if wp["audit_cycle"] in ("D", "K")}
        assert set(result) == expected

    def test_full_cycle_empty_cycles(self):
        """全循环策略无循环参数返回空。"""
        from app.services.qc_inspection_service import _sample_full_cycle

        wps = self._make_workpapers(10)
        result = _sample_full_cycle(wps, {"cycles": []})
        assert len(result) == 0

    def test_mixed_strategy(self):
        """混合策略组合三种策略结果（去重）。"""
        from app.services.qc_inspection_service import _sample_mixed

        wps = self._make_workpapers(20)
        result = _sample_mixed(wps, {
            "random_ratio": 0.1,
            "cycles": ["D"],
            "complexity_threshold": 3,
            "include_rejected": True,
        })

        # 结果应包含 D 循环全部 + 高复杂度 + 退回 + 随机部分
        # 至少包含 D 循环和高复杂度的
        d_ids = {wp["id"] for wp in wps if wp["audit_cycle"] == "D"}
        high_ids = {wp["id"] for wp in wps if wp["complexity"] >= 3}
        assert d_ids.issubset(set(result))
        assert high_ids.issubset(set(result))


# ---------------------------------------------------------------------------
# Service 集成测试（使用 SQLite 内存数据库）
# ---------------------------------------------------------------------------


class TestQcInspectionServiceCreate:
    """测试 create_inspection 方法。"""

    @pytest.mark.asyncio
    async def test_create_random_inspection(self, db_session: AsyncSession):
        """创建随机抽查批次。"""
        from app.services.qc_inspection_service import qc_inspection_service

        await _seed_workpapers(db_session, count=10)

        result = await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="random",
            params={"ratio": 0.3},
            reviewer_id=REVIEWER_ID,
        )

        assert result["strategy"] == "random"
        assert result["status"] == "created"
        assert result["project_id"] == str(PROJECT_ID)
        assert result["reviewer_id"] == str(REVIEWER_ID)
        # 30% of 10 = 3
        assert result["item_count"] == 3
        assert len(result["items"]) == 3

    @pytest.mark.asyncio
    async def test_create_risk_based_inspection(self, db_session: AsyncSession):
        """创建风险导向抽查批次。"""
        from app.services.qc_inspection_service import qc_inspection_service

        # 创建底稿，部分有退回状态
        review_statuses = [
            "not_submitted", "not_submitted", "level1_rejected",
            "not_submitted", "not_submitted", "level2_rejected",
            "not_submitted", "not_submitted", "not_submitted", "not_submitted",
        ]
        await _seed_workpapers(
            db_session, count=10, review_statuses=review_statuses
        )

        result = await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="risk_based",
            params={"complexity_threshold": 3, "include_rejected": True},
            reviewer_id=REVIEWER_ID,
        )

        assert result["strategy"] == "risk_based"
        # K/N 循环（index 2,3,6,7）+ 退回的（index 2,5）
        # K at index 2 (rejected), N at index 3, K at index 6, N at index 7
        # Rejected: index 2 (K, already counted), index 5 (F, complexity=1 but rejected)
        # So: K(2), N(3), F-rejected(5), K(6), N(7) = 5 items
        assert result["item_count"] >= 4  # At least K/N cycles

    @pytest.mark.asyncio
    async def test_create_full_cycle_inspection(self, db_session: AsyncSession):
        """创建全循环抽查批次。"""
        from app.services.qc_inspection_service import qc_inspection_service

        await _seed_workpapers(db_session, count=10)

        result = await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="full_cycle",
            params={"cycles": ["D"]},
            reviewer_id=REVIEWER_ID,
        )

        assert result["strategy"] == "full_cycle"
        # D 循环在 cycles=["D","F","K","N","D","F","K","N","D","F"] 中出现 3 次
        assert result["item_count"] == 3

    @pytest.mark.asyncio
    async def test_create_mixed_inspection(self, db_session: AsyncSession):
        """创建混合抽查批次。"""
        from app.services.qc_inspection_service import qc_inspection_service

        await _seed_workpapers(db_session, count=20)

        result = await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="mixed",
            params={"random_ratio": 0.1, "cycles": ["D"]},
            reviewer_id=REVIEWER_ID,
        )

        assert result["strategy"] == "mixed"
        # 至少包含 D 循环的底稿
        assert result["item_count"] >= 5  # D cycle items + risk + random

    @pytest.mark.asyncio
    async def test_invalid_strategy_raises(self, db_session: AsyncSession):
        """无效策略返回 422。"""
        from fastapi import HTTPException

        from app.services.qc_inspection_service import qc_inspection_service

        await _seed_workpapers(db_session, count=5)

        with pytest.raises(HTTPException) as exc_info:
            await qc_inspection_service.create_inspection(
                db_session,
                project_id=PROJECT_ID,
                strategy="invalid_strategy",
                params={},
                reviewer_id=REVIEWER_ID,
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_no_workpapers_raises(self, db_session: AsyncSession):
        """项目无底稿返回 404。"""
        from fastapi import HTTPException

        from app.services.qc_inspection_service import qc_inspection_service

        with pytest.raises(HTTPException) as exc_info:
            await qc_inspection_service.create_inspection(
                db_session,
                project_id=uuid.uuid4(),  # 不存在的项目
                strategy="random",
                params={"ratio": 0.1},
                reviewer_id=REVIEWER_ID,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_max_50_items_cap(self, db_session: AsyncSession):
        """每批次最多 50 张底稿。"""
        from app.services.qc_inspection_service import qc_inspection_service

        # 创建 60 张底稿
        cycles = ["D"] * 60
        await _seed_workpapers(db_session, count=60, cycles=cycles)

        result = await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="random",
            params={"ratio": 1.0},  # 全部抽取
            reviewer_id=REVIEWER_ID,
        )

        # 应被限制为 50
        assert result["item_count"] <= 50


class TestQcInspectionServiceVerdict:
    """测试 record_verdict 方法。"""

    @pytest.mark.asyncio
    async def test_record_pass_verdict(self, db_session: AsyncSession):
        """录入 pass 结论。"""
        from app.services.qc_inspection_service import qc_inspection_service

        await _seed_workpapers(db_session, count=5)

        # 先创建抽查
        inspection = await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="random",
            params={"ratio": 1.0},
            reviewer_id=REVIEWER_ID,
        )

        item_id = uuid.UUID(inspection["items"][0]["id"])
        inspection_id = uuid.UUID(inspection["id"])

        # 录入结论
        result = await qc_inspection_service.record_verdict(
            db_session,
            inspection_id=inspection_id,
            item_id=item_id,
            verdict="pass",
            findings=None,
        )

        assert result["qc_verdict"] == "pass"
        assert result["status"] == "completed"
        assert result["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_record_fail_verdict_with_findings(self, db_session: AsyncSession):
        """录入 fail 结论并附带发现。"""
        from app.services.qc_inspection_service import qc_inspection_service

        await _seed_workpapers(db_session, count=3)

        inspection = await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="random",
            params={"ratio": 1.0},
            reviewer_id=REVIEWER_ID,
        )

        item_id = uuid.UUID(inspection["items"][0]["id"])
        inspection_id = uuid.UUID(inspection["id"])

        findings = {
            "issues": [
                {"cell": "E5", "message": "金额不平衡", "severity": "blocking"}
            ]
        }

        result = await qc_inspection_service.record_verdict(
            db_session,
            inspection_id=inspection_id,
            item_id=item_id,
            verdict="fail",
            findings=findings,
        )

        assert result["qc_verdict"] == "fail"
        assert result["findings"] == findings

    @pytest.mark.asyncio
    async def test_all_items_completed_updates_inspection(self, db_session: AsyncSession):
        """所有子项完成后 inspection 状态变为 completed。"""
        from app.services.qc_inspection_service import qc_inspection_service

        # 只创建 2 张底稿
        await _seed_workpapers(db_session, count=2, cycles=["D", "D"])

        inspection = await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="random",
            params={"ratio": 1.0},
            reviewer_id=REVIEWER_ID,
        )

        inspection_id = uuid.UUID(inspection["id"])

        # 录入所有子项结论
        for item in inspection["items"]:
            await qc_inspection_service.record_verdict(
                db_session,
                inspection_id=inspection_id,
                item_id=uuid.UUID(item["id"]),
                verdict="pass",
            )

        # 检查 inspection 状态
        updated = await qc_inspection_service.get_inspection(db_session, inspection_id)
        assert updated["status"] == "completed"
        assert updated["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_first_verdict_sets_in_progress(self, db_session: AsyncSession):
        """第一个结论录入后 inspection 状态变为 in_progress。"""
        from app.services.qc_inspection_service import qc_inspection_service

        await _seed_workpapers(db_session, count=5)

        inspection = await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="random",
            params={"ratio": 1.0},
            reviewer_id=REVIEWER_ID,
        )

        inspection_id = uuid.UUID(inspection["id"])
        item_id = uuid.UUID(inspection["items"][0]["id"])

        await qc_inspection_service.record_verdict(
            db_session,
            inspection_id=inspection_id,
            item_id=item_id,
            verdict="pass",
        )

        updated = await qc_inspection_service.get_inspection(db_session, inspection_id)
        assert updated["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_invalid_verdict_raises(self, db_session: AsyncSession):
        """无效结论返回 422。"""
        from fastapi import HTTPException

        from app.services.qc_inspection_service import qc_inspection_service

        await _seed_workpapers(db_session, count=3)

        inspection = await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="random",
            params={"ratio": 1.0},
            reviewer_id=REVIEWER_ID,
        )

        with pytest.raises(HTTPException) as exc_info:
            await qc_inspection_service.record_verdict(
                db_session,
                inspection_id=uuid.UUID(inspection["id"]),
                item_id=uuid.UUID(inspection["items"][0]["id"]),
                verdict="invalid",
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_nonexistent_item_raises(self, db_session: AsyncSession):
        """不存在的 item 返回 404。"""
        from fastapi import HTTPException

        from app.services.qc_inspection_service import qc_inspection_service

        await _seed_workpapers(db_session, count=3)

        inspection = await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="random",
            params={"ratio": 1.0},
            reviewer_id=REVIEWER_ID,
        )

        with pytest.raises(HTTPException) as exc_info:
            await qc_inspection_service.record_verdict(
                db_session,
                inspection_id=uuid.UUID(inspection["id"]),
                item_id=uuid.uuid4(),  # 不存在的 item
                verdict="pass",
            )
        assert exc_info.value.status_code == 404


class TestQcInspectionServiceQuery:
    """测试查询方法。"""

    @pytest.mark.asyncio
    async def test_list_inspections(self, db_session: AsyncSession):
        """列出抽查批次。"""
        from app.services.qc_inspection_service import qc_inspection_service

        await _seed_workpapers(db_session, count=5)

        # 创建两个批次
        await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="random",
            params={"ratio": 0.5},
            reviewer_id=REVIEWER_ID,
        )
        await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="full_cycle",
            params={"cycles": ["D"]},
            reviewer_id=REVIEWER_ID,
        )

        result = await qc_inspection_service.list_inspections(
            db_session, project_id=PROJECT_ID
        )

        assert result["total"] == 2
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_inspections_filter_by_project(self, db_session: AsyncSession):
        """按项目过滤抽查批次。"""
        from app.services.qc_inspection_service import qc_inspection_service

        await _seed_workpapers(db_session, count=5)

        await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="random",
            params={"ratio": 0.5},
            reviewer_id=REVIEWER_ID,
        )

        # 查询不存在的项目
        result = await qc_inspection_service.list_inspections(
            db_session, project_id=uuid.uuid4()
        )
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_get_inspection_detail(self, db_session: AsyncSession):
        """获取抽查详情。"""
        from app.services.qc_inspection_service import qc_inspection_service

        await _seed_workpapers(db_session, count=5)

        created = await qc_inspection_service.create_inspection(
            db_session,
            project_id=PROJECT_ID,
            strategy="random",
            params={"ratio": 0.5},
            reviewer_id=REVIEWER_ID,
        )

        detail = await qc_inspection_service.get_inspection(
            db_session, uuid.UUID(created["id"])
        )

        assert detail["id"] == created["id"]
        assert detail["strategy"] == "random"
        assert len(detail["items"]) > 0

    @pytest.mark.asyncio
    async def test_get_nonexistent_inspection_raises(self, db_session: AsyncSession):
        """获取不存在的抽查返回 404。"""
        from fastapi import HTTPException

        from app.services.qc_inspection_service import qc_inspection_service

        with pytest.raises(HTTPException) as exc_info:
            await qc_inspection_service.get_inspection(db_session, uuid.uuid4())
        assert exc_info.value.status_code == 404
