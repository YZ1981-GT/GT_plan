"""QcCaseLibraryService 单元测试

Validates: Requirements 8 (Round 3)
- 案例库 CRUD
- 脱敏函数：客户名替换 + 金额 ±5% 扰动
- 从抽查子项发布案例（自动脱敏）
- 预览脱敏内容
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# Import models so they're registered with Base.metadata
import app.models.core  # noqa: F401
import app.models.workpaper_models  # noqa: F401
import app.models.qc_inspection_models  # noqa: F401
import app.models.qc_case_library_models  # noqa: F401
import app.models.qc_rule_models  # noqa: F401

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

CLIENT_NAME = "北京致同会计师事务所"


async def _seed_project(db: AsyncSession, client_name: str = CLIENT_NAME) -> uuid.UUID:
    """插入测试项目（使用 ORM 避免 SQLite UUID 兼容问题）。"""
    from app.models.core import Project

    project = Project(
        id=uuid.uuid4(),
        name=f"项目-{str(uuid.uuid4())[:8]}",
        client_name=client_name,
    )
    db.add(project)
    await db.flush()
    return project.id


async def _seed_working_paper(
    db: AsyncSession,
    project_id: uuid.UUID,
    parsed_data: dict | None = None,
) -> uuid.UUID:
    """插入测试底稿（使用 ORM 避免 SQLite UUID 兼容问题）。"""
    from app.models.workpaper_models import WpIndex, WorkingPaper

    wp_index = WpIndex(
        id=uuid.uuid4(),
        project_id=project_id,
        wp_code=f"D-{str(uuid.uuid4())[:4]}",
        wp_name="测试底稿",
    )
    db.add(wp_index)
    await db.flush()

    wp = WorkingPaper(
        id=uuid.uuid4(),
        project_id=project_id,
        wp_index_id=wp_index.id,
        file_path="/tmp/test.xlsx",
        source_type="imported",
        parsed_data=parsed_data,
    )
    db.add(wp)
    await db.flush()
    return wp.id


async def _seed_inspection(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> uuid.UUID:
    """插入测试抽查批次。"""
    from app.models.qc_inspection_models import QcInspection

    insp = QcInspection(
        id=uuid.uuid4(),
        project_id=project_id,
        strategy="random",
        reviewer_id=uuid.uuid4(),
        status="in_progress",
    )
    db.add(insp)
    await db.flush()
    return insp.id


async def _seed_inspection_item(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    wp_id: uuid.UUID,
    findings: dict | None = None,
    qc_verdict: str = "fail",
) -> uuid.UUID:
    """插入测试抽查子项。"""
    from app.models.qc_inspection_models import QcInspectionItem

    item = QcInspectionItem(
        id=uuid.uuid4(),
        inspection_id=inspection_id,
        wp_id=wp_id,
        status="completed",
        findings=findings,
        qc_verdict=qc_verdict,
    )
    db.add(item)
    await db.flush()
    return item.id


# ---------------------------------------------------------------------------
# 脱敏函数单元测试
# ---------------------------------------------------------------------------


class TestDesensitizeClientName:
    """客户名脱敏测试。"""

    def test_basic_replacement(self):
        from app.services.qc_case_library_service import desensitize_client_name

        text = "北京致同会计师事务所的审计报告"
        result = desensitize_client_name(text, "北京致同会计师事务所")
        assert result == "[客户A]的审计报告"

    def test_multiple_occurrences(self):
        from app.services.qc_case_library_service import desensitize_client_name

        text = "ABC公司的资产为100万，ABC公司的负债为50万"
        result = desensitize_client_name(text, "ABC公司")
        assert result == "[客户A]的资产为100万，[客户A]的负债为50万"

    def test_empty_text(self):
        from app.services.qc_case_library_service import desensitize_client_name

        result = desensitize_client_name("", "客户名")
        assert result == ""

    def test_empty_client_name(self):
        from app.services.qc_case_library_service import desensitize_client_name

        text = "一些文本"
        result = desensitize_client_name(text, "")
        assert result == "一些文本"

    def test_no_match(self):
        from app.services.qc_case_library_service import desensitize_client_name

        text = "这里没有客户名"
        result = desensitize_client_name(text, "不存在的客户")
        assert result == "这里没有客户名"

    def test_custom_placeholder(self):
        from app.services.qc_case_library_service import desensitize_client_name

        text = "ABC公司的报告"
        result = desensitize_client_name(text, "ABC公司", "[客户B]")
        assert result == "[客户B]的报告"

    def test_special_regex_chars_in_name(self):
        """客户名含正则特殊字符时不报错。"""
        from app.services.qc_case_library_service import desensitize_client_name

        text = "A+B (集团) 有限公司的报告"
        result = desensitize_client_name(text, "A+B (集团) 有限公司")
        assert result == "[客户A]的报告"


class TestDesensitizeAmount:
    """金额脱敏测试。"""

    def test_zero_returns_zero(self):
        from app.services.qc_case_library_service import desensitize_amount

        assert desensitize_amount(0) == 0.0

    def test_positive_amount_within_5_percent(self):
        from app.services.qc_case_library_service import desensitize_amount

        original = 100000.0
        result = desensitize_amount(original)
        # 应在 ±5% 范围内
        assert 95000.0 <= result <= 105000.0
        # 不应完全相等（极小概率相等，但统计上不会）
        # 这里不做严格断言，因为随机可能恰好为 0

    def test_negative_amount_within_5_percent(self):
        from app.services.qc_case_library_service import desensitize_amount

        original = -50000.0
        result = desensitize_amount(original)
        # 负数扰动后仍在 ±5% 范围
        assert -52500.0 <= result <= -47500.0

    def test_preserves_order_of_magnitude(self):
        """保留数量级。"""
        from app.services.qc_case_library_service import desensitize_amount

        original = 1000000.0
        result = desensitize_amount(original)
        # 数量级不变（6 位数）
        assert 950000.0 <= result <= 1050000.0

    def test_small_amount_not_perturbed(self):
        """绝对值 <= 1 的数值不扰动。"""
        from app.services.qc_case_library_service import desensitize_amount

        # desensitize_amount 对所有非零值都扰动
        # 但 _desensitize_parsed_data 中只对 abs > 1 的值扰动
        result = desensitize_amount(0.5)
        # 0.5 * (1 ± 0.05) 仍在合理范围
        assert 0.475 <= result <= 0.525


class TestDesensitizeParsedData:
    """parsed_data 递归脱敏测试。"""

    def test_none_input(self):
        from app.services.qc_case_library_service import _desensitize_parsed_data

        assert _desensitize_parsed_data(None, "客户") is None

    def test_string_values_replaced(self):
        from app.services.qc_case_library_service import _desensitize_parsed_data

        data = {"conclusion": "ABC公司的结论正确"}
        result = _desensitize_parsed_data(data, "ABC公司")
        assert "ABC公司" not in result["conclusion"]
        assert "[客户A]" in result["conclusion"]

    def test_numeric_values_perturbed(self):
        from app.services.qc_case_library_service import _desensitize_parsed_data

        data = {"amount": 100000.0, "count": 0.5}
        result = _desensitize_parsed_data(data, "客户")
        # 大金额被扰动
        assert result["amount"] != 100000.0
        assert 95000.0 <= result["amount"] <= 105000.0
        # 小数值（abs <= 1）不扰动
        assert result["count"] == 0.5

    def test_nested_dict(self):
        from app.services.qc_case_library_service import _desensitize_parsed_data

        data = {
            "header": {"client": "ABC公司"},
            "items": [{"name": "ABC公司应收", "amount": 50000}],
        }
        result = _desensitize_parsed_data(data, "ABC公司")
        assert "[客户A]" in result["header"]["client"]
        assert "[客户A]" in result["items"][0]["name"]
        assert 47500 <= result["items"][0]["amount"] <= 52500

    def test_boolean_not_perturbed(self):
        from app.services.qc_case_library_service import _desensitize_parsed_data

        data = {"is_valid": True, "count": 5}
        result = _desensitize_parsed_data(data, "客户")
        assert result["is_valid"] is True


# ---------------------------------------------------------------------------
# 服务层集成测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_case(db_session: AsyncSession):
    """手动创建案例。"""
    from app.services.qc_case_library_service import qc_case_library_service

    user_id = uuid.uuid4()
    data = {
        "title": "测试案例",
        "category": "底稿完整性",
        "severity": "warning",
        "description": "这是一个测试案例",
        "lessons_learned": "应注意完整性",
    }
    result = await qc_case_library_service.create_case(db_session, data, user_id)
    await db_session.commit()

    assert result["title"] == "测试案例"
    assert result["category"] == "底稿完整性"
    assert result["severity"] == "warning"
    assert result["published_by"] == str(user_id)
    assert result["review_count"] == 0


@pytest.mark.asyncio
async def test_list_cases_with_filters(db_session: AsyncSession):
    """列出案例支持分类/严重度筛选。"""
    from app.services.qc_case_library_service import qc_case_library_service

    user_id = uuid.uuid4()
    # 创建多个案例
    await qc_case_library_service.create_case(
        db_session,
        {"title": "案例1", "category": "底稿完整性", "severity": "warning", "description": "desc1"},
        user_id,
    )
    await qc_case_library_service.create_case(
        db_session,
        {"title": "案例2", "category": "数据准确性", "severity": "blocking", "description": "desc2"},
        user_id,
    )
    await qc_case_library_service.create_case(
        db_session,
        {"title": "案例3", "category": "底稿完整性", "severity": "blocking", "description": "desc3"},
        user_id,
    )
    await db_session.commit()

    # 无筛选
    result = await qc_case_library_service.list_cases(db_session)
    assert result["total"] == 3

    # 按分类筛选
    result = await qc_case_library_service.list_cases(db_session, category="底稿完整性")
    assert result["total"] == 2

    # 按严重度筛选
    result = await qc_case_library_service.list_cases(db_session, severity="blocking")
    assert result["total"] == 2

    # 组合筛选
    result = await qc_case_library_service.list_cases(
        db_session, category="底稿完整性", severity="blocking"
    )
    assert result["total"] == 1
    assert result["items"][0]["title"] == "案例3"


@pytest.mark.asyncio
async def test_get_case_increments_review_count(db_session: AsyncSession):
    """获取案例详情时增加阅读计数。"""
    from app.services.qc_case_library_service import qc_case_library_service

    user_id = uuid.uuid4()
    case = await qc_case_library_service.create_case(
        db_session,
        {"title": "案例", "category": "测试", "severity": "info", "description": "desc"},
        user_id,
    )
    await db_session.commit()

    case_id = uuid.UUID(case["id"])

    # 第一次获取
    result = await qc_case_library_service.get_case(db_session, case_id)
    await db_session.commit()
    assert result["review_count"] == 1

    # 第二次获取
    result = await qc_case_library_service.get_case(db_session, case_id)
    await db_session.commit()
    assert result["review_count"] == 2


@pytest.mark.asyncio
async def test_get_case_not_found(db_session: AsyncSession):
    """获取不存在的案例返回 None。"""
    from app.services.qc_case_library_service import qc_case_library_service

    result = await qc_case_library_service.get_case(db_session, uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_publish_from_inspection(db_session: AsyncSession):
    """从抽查子项发布案例（自动脱敏）。"""
    from app.services.qc_case_library_service import qc_case_library_service

    # 准备数据
    project_id = await _seed_project(db_session, client_name=CLIENT_NAME)
    wp_id = await _seed_working_paper(
        db_session,
        project_id,
        parsed_data={
            "conclusion": f"{CLIENT_NAME}的财务报表公允",
            "total_assets": 1000000,
        },
    )
    inspection_id = await _seed_inspection(db_session, project_id)
    item_id = await _seed_inspection_item(
        db_session,
        inspection_id,
        wp_id,
        findings={"items": [{"message": f"{CLIENT_NAME}结论缺失"}]},
        qc_verdict="fail",
    )
    await db_session.commit()

    # 发布
    user_id = uuid.uuid4()
    result = await qc_case_library_service.publish_from_inspection(
        db_session,
        inspection_id=inspection_id,
        item_id=item_id,
        published_by=user_id,
        title="典型案例：结论缺失",
        category="底稿完整性",
        lessons_learned="应确保结论完整",
    )
    await db_session.commit()

    assert result is not None
    assert result["title"] == "典型案例：结论缺失"
    assert result["category"] == "底稿完整性"
    assert result["severity"] == "blocking"  # fail → blocking
    assert result["lessons_learned"] == "应确保结论完整"
    # 验证脱敏：related_wp_refs 中不应包含原始客户名
    wp_refs = result["related_wp_refs"]
    assert wp_refs is not None
    import json
    refs_str = json.dumps(wp_refs, ensure_ascii=False)
    assert CLIENT_NAME not in refs_str
    assert "[客户A]" in refs_str


@pytest.mark.asyncio
async def test_publish_from_inspection_not_found(db_session: AsyncSession):
    """发布不存在的抽查子项返回 None。"""
    from app.services.qc_case_library_service import qc_case_library_service

    result = await qc_case_library_service.publish_from_inspection(
        db_session,
        inspection_id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        published_by=uuid.uuid4(),
    )
    assert result is None


@pytest.mark.asyncio
async def test_preview_desensitized(db_session: AsyncSession):
    """预览脱敏内容。"""
    from app.services.qc_case_library_service import qc_case_library_service

    project_id = await _seed_project(db_session, client_name=CLIENT_NAME)
    wp_id = await _seed_working_paper(
        db_session,
        project_id,
        parsed_data={"note": f"审计{CLIENT_NAME}时发现问题", "amount": 200000},
    )
    inspection_id = await _seed_inspection(db_session, project_id)
    item_id = await _seed_inspection_item(
        db_session,
        inspection_id,
        wp_id,
        findings={"items": [{"message": f"{CLIENT_NAME}数据异常"}]},
    )
    await db_session.commit()

    result = await qc_case_library_service.preview_desensitized(
        db_session,
        inspection_id=inspection_id,
        item_id=item_id,
    )

    assert result is not None
    assert result["client_name_original"] == CLIENT_NAME
    assert result["client_name_replaced"] == "[客户A]"
    # 脱敏后数据不含原始客户名
    import json
    data_str = json.dumps(result["desensitized_data"], ensure_ascii=False)
    assert CLIENT_NAME not in data_str
    assert "[客户A]" in data_str
    # 金额被扰动
    assert result["desensitized_data"]["amount"] != 200000
    assert 190000 <= result["desensitized_data"]["amount"] <= 210000


@pytest.mark.asyncio
async def test_preview_not_found(db_session: AsyncSession):
    """预览不存在的子项返回 None。"""
    from app.services.qc_case_library_service import qc_case_library_service

    result = await qc_case_library_service.preview_desensitized(
        db_session,
        inspection_id=uuid.uuid4(),
        item_id=uuid.uuid4(),
    )
    assert result is None
