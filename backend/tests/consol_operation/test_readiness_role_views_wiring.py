"""批 6.4：readiness 装载层接证据充分性 + 壳复核状态（SQLite，真实壳 + 证据真源）。

验证 `_load_shell_evidence_and_review`（readiness 装载层的新接点）：
- 无壳 ⇒ 证据 unknown（无从挂证据）、复核无壳；不伪装成"充分/已复核"。
- 有壳、A3-CONSOL 无声明需求 ⇒ 证据四态 not_declared（= 充分），与
  wp_evidence_service.check_sufficiency / 归档 / 签发同一真源（EvidenceReadinessService）。
- 复核状态随壳状态机变化（提交 → 退回 → 重新提交）被装载层如实反映。

不重建充分性判定：证据状态来自 EvidenceReadinessService.evaluate_workpaper（壳的 working_paper_id）。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # noqa: E305

import tests.conftest  # noqa: F401,E402
from app.models.base import Base, ProjectStatus, UserRole  # noqa: E402
from app.models.consol_workpaper_instance_models import ConsolWorkpaperInstance  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex, WpReviewStatus  # noqa: E402
from app.services import consol_workpaper_shell as shell  # noqa: E402
from app.services.consol_readiness_service import (  # noqa: E402
    _load_shell_evidence_and_review,
    build_readiness,
    build_role_views,
)

YEAR = 2025
pytestmark = pytest.mark.asyncio

_TABLES = [
    User.__table__, Project.__table__,
    WpIndex.__table__, WorkingPaper.__table__, ConsolWorkpaperInstance.__table__,
]


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _project() -> Project:
    return Project(
        id=uuid.uuid4(), name="【测试】readiness 接点_2025", client_name="【测试】readiness 接点",
        company_code="SH", audit_year=YEAR, report_scope="consolidated",
        status=ProjectStatus.execution,
    )


def _user(name: str) -> User:
    return User(
        id=uuid.uuid4(), username=name, email=f"{name}@readiness.test",
        hashed_password="x", role=UserRole.auditor, is_active=True,
    )


async def test_no_shell_evidence_unknown_review_no_shell(db: AsyncSession):
    p = _project()
    db.add(p)
    await db.commit()
    evidence, review = await _load_shell_evidence_and_review(db, p.id)
    # 无壳：证据状态未知（不伪装成充分），复核无壳
    assert evidence["status"] == "unknown"
    assert evidence["sufficient"] is False
    assert evidence["has_shell"] is False
    assert review["review_status"] is None
    assert review["has_shell"] is False


async def test_shell_evidence_not_declared_is_sufficient(db: AsyncSession):
    """A3-CONSOL 无声明需求 ⇒ 统一四态 not_declared ⇒ 视为充分（与 check_sufficiency 同口径）。"""
    p = _project()
    db.add(p)
    await db.commit()
    await shell.ensure_consol_workpaper_shell(db, p.id)
    await db.commit()
    evidence, review = await _load_shell_evidence_and_review(db, p.id)
    assert evidence["status"] == "not_declared"
    assert evidence["sufficient"] is True
    assert evidence["has_shell"] is True
    # 新建壳复核状态 = not_submitted
    assert review["review_status"] == WpReviewStatus.not_submitted.value
    assert review["has_shell"] is True


async def test_review_status_tracks_state_machine(db: AsyncSession):
    p = _project()
    owner = _user("owner")
    reviewer = _user("rev")
    db.add_all([p, owner, reviewer])
    await db.commit()
    await shell.ensure_consol_workpaper_shell(db, p.id)
    await db.commit()

    # 提交复核 ⇒ pending_level1
    await shell.submit_consol_workpaper_review(db, p.id, actor_user_id=owner.id)
    await db.commit()
    _ev, review = await _load_shell_evidence_and_review(db, p.id)
    assert review["review_status"] == WpReviewStatus.pending_level1.value

    # 退回 ⇒ level1_rejected + 原因
    await shell.review_consol_workpaper(
        db, p.id, approved=False, actor_user_id=reviewer.id, rejection_reason="抵销不完整",
    )
    await db.commit()
    _ev2, review2 = await _load_shell_evidence_and_review(db, p.id)
    assert review2["review_status"] == WpReviewStatus.level1_rejected.value
    assert review2["rejection_reason"] == "抵销不完整"


async def test_role_views_reflect_real_shell_review(db: AsyncSession):
    """端到端：真实壳退回复核 ⇒ 质控桶出现 review_rejected 阻断。"""
    p = _project()
    owner = _user("owner2")
    reviewer = _user("rev2")
    db.add_all([p, owner, reviewer])
    await db.commit()
    await shell.ensure_consol_workpaper_shell(db, p.id)
    await db.commit()
    await shell.submit_consol_workpaper_review(db, p.id, actor_user_id=owner.id)
    await db.commit()
    await shell.review_consol_workpaper(
        db, p.id, approved=False, actor_user_id=reviewer.id, rejection_reason="差额表未平",
    )
    await db.commit()

    evidence, review = await _load_shell_evidence_and_review(db, p.id)
    domains = build_readiness({
        "tree": {"has_tree": True, "node_count": 3},
        "worksheet": {"has_worksheet_data": True, "evidence_status": evidence["status"]},
        "lifecycle": {"has_snapshot": True, "review_status": review["review_status"]},
    })
    payload = build_role_views(domains, evidence=evidence, review=review)
    qc = next(v for v in payload["views"] if v["role"] == "qc")
    assert any(t["code"] == "review_rejected" for t in qc["todos"])
    assert qc["status"] == "not_ready"
    # 证据 not_declared ⇒ 不额外产生证据阻断
    assert not any(t["code"] == "evidence_insufficient" for t in qc["todos"])
