"""AgingConfigService get_config / save_config / get_effective_segments 单元测试

覆盖：
- 默认配置推断逻辑（无 wizard_state.aging_config 时）
- subject_overrides 覆盖逻辑（如 D3→THREE_YEAR）
- 无 wizard_state / 空项目时的兜底行为
- save → get 往返保存

Validates: Requirements 1.2, 2.5, 10.1
"""

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# SQLite JSONB compat（与其它 service 测试一致）
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.models.base import Base  # noqa: E402
from app.models.core import Project  # noqa: E402
from app.services import aging_config_service as svc  # noqa: E402
from app.services.aging_config_service import (  # noqa: E402
    AgingConfigPayload,
    AgingPreset,
    AgingSegment,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话（每次重建表）。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


async def _make_project(
    db_session: AsyncSession, wizard_state: dict | None = None
) -> Project:
    """创建一个最小化 Project 记录，可选注入 wizard_state。"""
    project = Project(
        id=uuid.uuid4(),
        name="测试项目_2024",
        client_name="测试客户",
        wizard_state=wizard_state,
    )
    db_session.add(project)
    await db_session.flush()
    return project


# ===================================================================
# get_config —— 默认配置推断 / 兜底
# ===================================================================


class TestGetConfigDefaults:
    """Validates: Requirements 1.2, 2.5, 10.1"""

    @pytest.mark.asyncio
    async def test_no_wizard_state_returns_default_five_year(
        self, db_session: AsyncSession
    ):
        """wizard_state 为 None 时返回默认 FIVE_YEAR（6段）配置。"""
        project = await _make_project(db_session, wizard_state=None)

        resp = await svc.get_config(project.id, db_session)

        assert resp.preset == AgingPreset.FIVE_YEAR
        assert len(resp.effective_segments) == 6
        assert resp.subject_overrides == {}
        # 段标签有序且正确
        labels = [s.label for s in resp.effective_segments]
        assert labels == ["1年以内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上"]

    @pytest.mark.asyncio
    async def test_wizard_state_without_aging_config_returns_default(
        self, db_session: AsyncSession
    ):
        """wizard_state 存在但无 aging_config 键时返回默认配置。"""
        project = await _make_project(
            db_session, wizard_state={"steps": {"basic_info": {"completed": True}}}
        )

        resp = await svc.get_config(project.id, db_session)

        assert resp.preset == AgingPreset.FIVE_YEAR
        assert len(resp.effective_segments) == 6
        assert resp.subject_overrides == {}

    @pytest.mark.asyncio
    async def test_get_config_project_not_found(self, db_session: AsyncSession):
        """项目不存在时抛 404。"""
        with pytest.raises(HTTPException) as exc_info:
            await svc.get_config(uuid.uuid4(), db_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_config_reads_stored_three_year(
        self, db_session: AsyncSession
    ):
        """已存储 THREE_YEAR 配置时正确解析（4段）。"""
        project = await _make_project(
            db_session,
            wizard_state={
                "aging_config": {
                    "preset": "THREE_YEAR",
                    "custom_segments": None,
                    "subject_overrides": {},
                }
            },
        )

        resp = await svc.get_config(project.id, db_session)

        assert resp.preset == AgingPreset.THREE_YEAR
        assert len(resp.effective_segments) == 4
        assert [s.label for s in resp.effective_segments] == [
            "1年以内",
            "1-2年",
            "2-3年",
            "3年以上",
        ]

    @pytest.mark.asyncio
    async def test_get_config_reads_stored_custom(self, db_session: AsyncSession):
        """已存储 CUSTOM 配置时返回自定义段列表。"""
        project = await _make_project(
            db_session,
            wizard_state={
                "aging_config": {
                    "preset": "CUSTOM",
                    "custom_segments": [
                        {"key": "s1", "label": "6个月以内", "dayFrom": 0, "dayTo": 180},
                        {"key": "s2", "label": "6个月-1年", "dayFrom": 181, "dayTo": 365},
                        {"key": "s3", "label": "1年以上", "dayFrom": 366, "dayTo": None},
                    ],
                    "subject_overrides": {},
                }
            },
        )

        resp = await svc.get_config(project.id, db_session)

        assert resp.preset == AgingPreset.CUSTOM
        assert len(resp.effective_segments) == 3
        assert [s.label for s in resp.effective_segments] == [
            "6个月以内",
            "6个月-1年",
            "1年以上",
        ]

    @pytest.mark.asyncio
    async def test_get_config_returns_stored_subject_overrides(
        self, db_session: AsyncSession
    ):
        """subject_overrides 被正确读取并返回。"""
        project = await _make_project(
            db_session,
            wizard_state={
                "aging_config": {
                    "preset": "FIVE_YEAR",
                    "custom_segments": None,
                    "subject_overrides": {"D3": "THREE_YEAR", "F1": "THREE_YEAR"},
                }
            },
        )

        resp = await svc.get_config(project.id, db_session)

        assert resp.subject_overrides == {
            "D3": AgingPreset.THREE_YEAR,
            "F1": AgingPreset.THREE_YEAR,
        }


# ===================================================================
# get_effective_segments —— 默认推断 + subject_overrides 覆盖
# ===================================================================


class TestGetEffectiveSegments:
    """Validates: Requirements 1.2, 2.5, 10.1"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("subject", ["D2", "K1", "K3", "G5"])
    async def test_no_config_receivable_subjects_default_five_year(
        self, db_session: AsyncSession, subject: str
    ):
        """无配置时 D2/K1/K3/G5 推断 FIVE_YEAR（6段）。"""
        project = await _make_project(db_session, wizard_state=None)

        segments = await svc.get_effective_segments(project.id, subject, db_session)

        assert len(segments) == 6
        assert segments[-1].label == "5年以上"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("subject", ["D3", "F1"])
    async def test_no_config_advance_subjects_default_three_year(
        self, db_session: AsyncSession, subject: str
    ):
        """无配置时 D3/F1 推断 THREE_YEAR（4段）。"""
        project = await _make_project(db_session, wizard_state=None)

        segments = await svc.get_effective_segments(project.id, subject, db_session)

        assert len(segments) == 4
        assert segments[-1].label == "3年以上"

    @pytest.mark.asyncio
    async def test_unknown_subject_falls_back_to_five_year(
        self, db_session: AsyncSession
    ):
        """未知 subject 无配置时兜底 FIVE_YEAR。"""
        project = await _make_project(db_session, wizard_state=None)

        segments = await svc.get_effective_segments(project.id, "ZZ", db_session)

        assert len(segments) == 6

    @pytest.mark.asyncio
    async def test_subject_override_takes_precedence_over_global(
        self, db_session: AsyncSession
    ):
        """subject_overrides 覆盖全局 preset：全局 FIVE_YEAR，D3 覆盖为 THREE_YEAR。"""
        project = await _make_project(
            db_session,
            wizard_state={
                "aging_config": {
                    "preset": "FIVE_YEAR",
                    "custom_segments": None,
                    "subject_overrides": {"D3": "THREE_YEAR"},
                }
            },
        )

        # D3 命中覆盖 → THREE_YEAR (4段)
        d3_segments = await svc.get_effective_segments(project.id, "D3", db_session)
        assert len(d3_segments) == 4
        assert d3_segments[-1].label == "3年以上"

        # D2 未命中覆盖 → 全局 FIVE_YEAR (6段)
        d2_segments = await svc.get_effective_segments(project.id, "D2", db_session)
        assert len(d2_segments) == 6
        assert d2_segments[-1].label == "5年以上"

    @pytest.mark.asyncio
    async def test_no_override_uses_global_preset(self, db_session: AsyncSession):
        """存在配置但无 subject_overrides 时，所有 subject 用全局 preset。"""
        project = await _make_project(
            db_session,
            wizard_state={
                "aging_config": {
                    "preset": "THREE_YEAR",
                    "custom_segments": None,
                    "subject_overrides": {},
                }
            },
        )

        # 即使 D2 默认是 FIVE_YEAR，有全局配置时应遵从全局 THREE_YEAR
        segments = await svc.get_effective_segments(project.id, "D2", db_session)
        assert len(segments) == 4

    @pytest.mark.asyncio
    async def test_global_custom_preset_applies_when_no_override(
        self, db_session: AsyncSession
    ):
        """全局 CUSTOM 配置在无覆盖科目上生效。"""
        project = await _make_project(
            db_session,
            wizard_state={
                "aging_config": {
                    "preset": "CUSTOM",
                    "custom_segments": [
                        {"key": "s1", "label": "近期", "dayFrom": 0, "dayTo": 90},
                        {"key": "s2", "label": "远期", "dayFrom": 91, "dayTo": None},
                    ],
                    "subject_overrides": {},
                }
            },
        )

        segments = await svc.get_effective_segments(project.id, "D2", db_session)
        assert len(segments) == 2
        assert [s.label for s in segments] == ["近期", "远期"]

    @pytest.mark.asyncio
    async def test_get_effective_segments_project_not_found(
        self, db_session: AsyncSession
    ):
        """项目不存在时抛 404。"""
        with pytest.raises(HTTPException) as exc_info:
            await svc.get_effective_segments(uuid.uuid4(), "D2", db_session)
        assert exc_info.value.status_code == 404


# ===================================================================
# save_config —— 持久化与往返
# ===================================================================


class TestSaveConfig:
    """Validates: Requirements 1.2, 2.5, 10.1（save→get 往返）"""

    @pytest.mark.asyncio
    async def test_save_then_get_roundtrip_five_year(
        self, db_session: AsyncSession
    ):
        """保存 FIVE_YEAR 后读取一致。"""
        project = await _make_project(db_session, wizard_state=None)
        payload = AgingConfigPayload(
            preset=AgingPreset.FIVE_YEAR,
            custom_segments=None,
            subject_overrides={"D3": AgingPreset.THREE_YEAR},
        )

        save_resp = await svc.save_config(project.id, payload, db_session)
        assert save_resp.preset == AgingPreset.FIVE_YEAR
        assert save_resp.subject_overrides == {"D3": AgingPreset.THREE_YEAR}

        get_resp = await svc.get_config(project.id, db_session)
        assert get_resp.preset == AgingPreset.FIVE_YEAR
        assert len(get_resp.effective_segments) == 6
        assert get_resp.subject_overrides == {"D3": AgingPreset.THREE_YEAR}

    @pytest.mark.asyncio
    async def test_save_custom_then_get_roundtrip(self, db_session: AsyncSession):
        """保存 CUSTOM 段后读取保留段定义。"""
        project = await _make_project(db_session, wizard_state=None)
        custom = [
            AgingSegment(key="a", label="A段", dayFrom=0, dayTo=100),
            AgingSegment(key="b", label="B段", dayFrom=101, dayTo=None),
        ]
        payload = AgingConfigPayload(
            preset=AgingPreset.CUSTOM,
            custom_segments=custom,
            subject_overrides=None,
        )

        await svc.save_config(project.id, payload, db_session)
        get_resp = await svc.get_config(project.id, db_session)

        assert get_resp.preset == AgingPreset.CUSTOM
        assert [s.label for s in get_resp.effective_segments] == ["A段", "B段"]

    @pytest.mark.asyncio
    async def test_save_preserves_other_wizard_state_keys(
        self, db_session: AsyncSession
    ):
        """保存 aging_config 不覆盖 wizard_state 其它字段。"""
        project = await _make_project(
            db_session,
            wizard_state={"steps": {"basic_info": {"completed": True}}},
        )
        payload = AgingConfigPayload(
            preset=AgingPreset.THREE_YEAR, custom_segments=None, subject_overrides=None
        )

        await svc.save_config(project.id, payload, db_session)

        assert "steps" in project.wizard_state
        assert project.wizard_state["steps"]["basic_info"]["completed"] is True
        assert project.wizard_state["aging_config"]["preset"] == "THREE_YEAR"

    @pytest.mark.asyncio
    async def test_save_config_project_not_found(self, db_session: AsyncSession):
        """项目不存在时抛 404。"""
        payload = AgingConfigPayload(
            preset=AgingPreset.FIVE_YEAR, custom_segments=None, subject_overrides=None
        )
        with pytest.raises(HTTPException) as exc_info:
            await svc.save_config(uuid.uuid4(), payload, db_session)
        assert exc_info.value.status_code == 404
