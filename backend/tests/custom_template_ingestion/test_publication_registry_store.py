"""publication registry 持久化仓储判据（V275）。

Spec: custom-workpaper-template-ingestion-and-sync-closure

## 本文件防的故障形态

`publication_ops.PublicationRegistry` 与 `finalize_saga` 此前**全部是内存实现**：
service 写好了、单测全绿，但零生产调用方，重启即丢。本文件钉住持久化语义。

判据分四层：
1. **不可覆盖**：同 (org, publication_key) 二次登记必须抛，且已有行的
   `artifact_digest` / `authority_ref` 不被改写。
2. **状态门禁**：非 ACTIVE 不能 pin；instantiate 只认 ACTIVE。
3. **一个项目一个 pin**：重复 pin 是改写而非新增。
4. **状态推进单源**：合法转换集合取自 `lifecycles._PUBLICATION_TRANSITIONS`，
   非法转换抛 `InvalidLifecycleTransition`（不另立判据）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.custom_template_publication import (
    CustomTemplatePublication,
    CustomTemplatePublicationPin,
)
from app.services.custom_template_ingestion.lifecycles import (
    InvalidLifecycleTransition,
    PublicationState,
    TemplatePublicationRecord,
)
from app.services.custom_template_ingestion.publication_registry_store import (
    PublicationStoreError,
    assert_instantiate_allowed_persisted,
    get_project_pin,
    get_publication,
    list_publications,
    pin_project,
    register_publication,
    transition_publication,
)

ORG = "org-pub-test"
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


@pytest.fixture()
def session() -> Session:
    """内存 SQLite；只建本文件需要的表。

    🔴 两个坑（首版踩过）：
    ① `custom_template_publication_pins.project_id` 外键指向 `projects`，
       只建两张表时插入 pin 会因外键失败 ⇒ 必须一并建 `projects`。
    ② `handoff` 列是 JSONB，SQLite 无该类型 ⇒ 复用既有先例
       （`tests/acnr/test_wp_cell_target.py`）的
       `SQLiteTypeCompiler.visit_JSONB = visit_JSON` 打补丁。
    """
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
    engine = sa.create_engine("sqlite://")
    from app.models.core import Project

    for table in (Project.__table__, CustomTemplatePublication.__table__, CustomTemplatePublicationPin.__table__):
        table.create(engine, checkfirst=True)
    with Session(engine) as s:
        yield s


def _record(
    *,
    key: str = "pub-1",
    state: PublicationState = PublicationState.ACTIVE,
    candidate_digest: str = DIGEST_A,
    authority_ref: str = "auth-1",
) -> TemplatePublicationRecord:
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    return TemplatePublicationRecord(
        publication_id=key,
        organization_id=ORG,
        candidate_id="cand-1",
        candidate_digest=candidate_digest,
        authority_ref=authority_ref,
        state=state,
        created_at=now,
        updated_at=now,
    )


HANDOFF = {"phase": "finalized", "handoffId": "handoff-1"}


class TestRegisterIsImmutable:
    def test_register_active_and_read_back(self, session: Session) -> None:
        stored = register_publication(
            session,
            record=_record(),
            artifact_digest=DIGEST_A,
            handoff=HANDOFF,
        )
        assert stored.publication_key == "pub-1"
        assert stored.state == PublicationState.ACTIVE
        assert stored.artifact_digest == DIGEST_A
        assert stored.handoff["handoffId"] == "handoff-1"

        again = get_publication(session, organization_id=ORG, publication_key="pub-1")
        assert again is not None
        assert again.artifact_digest == DIGEST_A

    def test_second_register_with_same_key_is_rejected(self, session: Session) -> None:
        register_publication(
            session, record=_record(), artifact_digest=DIGEST_A, handoff=HANDOFF
        )
        with pytest.raises(PublicationStoreError, match="不可覆盖"):
            register_publication(
                session,
                record=_record(authority_ref="auth-OTHER"),
                artifact_digest=DIGEST_B,
                handoff={"phase": "finalized", "handoffId": "handoff-2"},
            )

    def test_rejected_register_does_not_mutate_existing_row(self, session: Session) -> None:
        """🔴 关键：被拒的登记不得留下任何痕迹（不能是「先改后抛」）。"""
        register_publication(
            session, record=_record(), artifact_digest=DIGEST_A, handoff=HANDOFF
        )
        session.commit()  # 先固定基线，否则后面的 rollback 会把它一起回滚
        with pytest.raises(PublicationStoreError):
            register_publication(
                session,
                record=_record(authority_ref="auth-OTHER"),
                artifact_digest=DIGEST_B,
                handoff={"phase": "finalized", "handoffId": "handoff-2"},
            )
        session.rollback()
        row = get_publication(session, organization_id=ORG, publication_key="pub-1")
        assert row is not None
        assert row.artifact_digest == DIGEST_A
        assert row.authority_ref == "auth-1"

    def test_non_active_non_pending_state_rejected(self, session: Session) -> None:
        with pytest.raises(PublicationStoreError, match="只能登记"):
            register_publication(
                session,
                record=_record(state=PublicationState.WITHDRAWN),
                artifact_digest=DIGEST_A,
                handoff=HANDOFF,
            )

    def test_pending_visibility_is_registerable(self, session: Session) -> None:
        """finalize saga 中间态要能落库，否则崩溃后无可恢复锚点。"""
        stored = register_publication(
            session,
            record=_record(state=PublicationState.PENDING_VISIBILITY),
            artifact_digest=DIGEST_A,
            handoff=HANDOFF,
        )
        assert stored.state == PublicationState.PENDING_VISIBILITY

    def test_two_publications_coexist(self, session: Session) -> None:
        """新 version 不覆盖旧 artifact。"""
        register_publication(
            session, record=_record(key="pub-v1"), artifact_digest=DIGEST_A, handoff=HANDOFF
        )
        register_publication(
            session, record=_record(key="pub-v2"), artifact_digest=DIGEST_B, handoff=HANDOFF
        )
        rows = list_publications(session, organization_id=ORG)
        assert {r.publication_key for r in rows} == {"pub-v1", "pub-v2"}
        assert {r.artifact_digest for r in rows} == {DIGEST_A, DIGEST_B}

    def test_list_filter_by_state(self, session: Session) -> None:
        register_publication(
            session,
            record=_record(key="pub-a", state=PublicationState.ACTIVE),
            artifact_digest=DIGEST_A,
            handoff=HANDOFF,
        )
        register_publication(
            session,
            record=_record(key="pub-p", state=PublicationState.PENDING_VISIBILITY),
            artifact_digest=DIGEST_B,
            handoff=HANDOFF,
        )
        active = list_publications(
            session, organization_id=ORG, states=(PublicationState.ACTIVE,)
        )
        assert [r.publication_key for r in active] == ["pub-a"]

    def test_org_isolation(self, session: Session) -> None:
        register_publication(
            session, record=_record(), artifact_digest=DIGEST_A, handoff=HANDOFF
        )
        assert get_publication(
            session, organization_id="other-org", publication_key="pub-1"
        ) is None


class TestTransitionUsesSingleSource:
    def test_pending_to_active_allowed(self, session: Session) -> None:
        register_publication(
            session,
            record=_record(state=PublicationState.PENDING_VISIBILITY),
            artifact_digest=DIGEST_A,
            handoff=HANDOFF,
        )
        updated = transition_publication(
            session,
            organization_id=ORG,
            publication_key="pub-1",
            to_state=PublicationState.ACTIVE,
            reason="all_acks_accepted",
        )
        assert updated.state == PublicationState.ACTIVE
        assert updated.reason == "all_acks_accepted"

    def test_withdrawn_cannot_go_back_to_active(self, session: Session) -> None:
        register_publication(
            session, record=_record(), artifact_digest=DIGEST_A, handoff=HANDOFF
        )
        transition_publication(
            session,
            organization_id=ORG,
            publication_key="pub-1",
            to_state=PublicationState.WITHDRAWN,
            reason="withdrawn",
        )
        with pytest.raises(InvalidLifecycleTransition, match="非法"):
            transition_publication(
                session,
                organization_id=ORG,
                publication_key="pub-1",
                to_state=PublicationState.ACTIVE,
                reason="back",
            )

    def test_transition_unknown_publication(self, session: Session) -> None:
        with pytest.raises(PublicationStoreError, match="不存在"):
            transition_publication(
                session,
                organization_id=ORG,
                publication_key="nope",
                to_state=PublicationState.ACTIVE,
                reason="x",
            )


class TestInstantiateGate:
    def test_active_allowed(self) -> None:
        row = _stored(state=PublicationState.ACTIVE)
        assert_instantiate_allowed_persisted(row)  # 不抛即可

    @pytest.mark.parametrize(
        "state",
        [
            PublicationState.PENDING_VISIBILITY,
            PublicationState.WITHDRAWN,
            PublicationState.SECURITY_REVOKED,
            PublicationState.FAILED,
        ],
    )
    def test_non_active_rejected(self, state: PublicationState) -> None:
        row = _stored(state=state)
        with pytest.raises(PublicationStoreError, match="仅允许 ACTIVE"):
            assert_instantiate_allowed_persisted(row)


def _stored(state: PublicationState):
    from app.services.custom_template_ingestion.publication_registry_store import (
        StoredPublication,
    )

    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    return StoredPublication(
        id=uuid.uuid4(),
        publication_key="pub-1",
        organization_id=ORG,
        candidate_id="cand-1",
        candidate_digest=DIGEST_A,
        authority_ref="auth-1",
        artifact_digest=DIGEST_A,
        state=state,
        reason=None,
        handoff={},
        created_at=now,
        updated_at=now,
    )


def _mk_project(session: Session, name: str = "pub-pin 项目") -> uuid.UUID:
    from app.models.core import Project

    pid = uuid.uuid4()
    # 现算（app.models.core.Project）：NOT NULL 且无默认值的列只有 name / client_name
    session.add(Project(id=pid, name=name, client_name="客户", status="active"))
    session.flush()
    return pid


class TestProjectPin:
    def test_pin_active_publication(self, session: Session) -> None:
        register_publication(
            session, record=_record(), artifact_digest=DIGEST_A, handoff=HANDOFF
        )
        pid = _mk_project(session)
        pin_project(
            session, organization_id=ORG, project_id=pid, publication_key="pub-1"
        )
        pinned = get_project_pin(session, project_id=pid)
        assert pinned is not None
        assert pinned.publication_key == "pub-1"

    def test_cannot_pin_non_active(self, session: Session) -> None:
        register_publication(
            session,
            record=_record(state=PublicationState.PENDING_VISIBILITY),
            artifact_digest=DIGEST_A,
            handoff=HANDOFF,
        )
        pid = _mk_project(session)
        with pytest.raises(PublicationStoreError, match="只能 pin ACTIVE"):
            pin_project(
                session, organization_id=ORG, project_id=pid, publication_key="pub-1"
            )

    def test_cannot_pin_unknown_publication(self, session: Session) -> None:
        pid = _mk_project(session)
        with pytest.raises(PublicationStoreError, match="未知 publication"):
            pin_project(
                session, organization_id=ORG, project_id=pid, publication_key="nope"
            )

    def test_repin_same_project_rewrites_instead_of_adding(self, session: Session) -> None:
        """🔴 一个项目一个 pin：升级是改写，不是新增。"""
        register_publication(
            session, record=_record(key="pub-v1"), artifact_digest=DIGEST_A, handoff=HANDOFF
        )
        register_publication(
            session, record=_record(key="pub-v2"), artifact_digest=DIGEST_B, handoff=HANDOFF
        )
        pid = _mk_project(session)
        first = pin_project(
            session, organization_id=ORG, project_id=pid, publication_key="pub-v1"
        )
        second = pin_project(
            session, organization_id=ORG, project_id=pid, publication_key="pub-v2"
        )
        assert first == second  # 同一行被改写
        count = session.execute(
            sa.select(sa.func.count()).select_from(CustomTemplatePublicationPin)
        ).scalar_one()
        assert count == 1
        assert get_project_pin(session, project_id=pid).publication_key == "pub-v2"

    def test_pin_absent_returns_none(self, session: Session) -> None:
        pid = _mk_project(session)
        assert get_project_pin(session, project_id=pid) is None
