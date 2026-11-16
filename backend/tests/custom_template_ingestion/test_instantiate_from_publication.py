"""ACTIVE publication → 整册 workbook 实例化（落库）判据。

Spec: custom-workpaper-template-ingestion-and-sync-closure, Task 10

## 为什么必须落库级判据

`workbook_instance.create_workbook_instance` 是**纯函数**：它返回 dataclass 就
算「成功」，即使一张表都没写。本文件用真 SQLite（V158 两张表）断言行真的落了。

判据分五层：
1. **状态门禁**：非 ACTIVE 拒绝（与 `assert_instantiate_allowed` 同判据）；
2. **sheet 白名单**：sheetUid 必须出现在 preflight 报告里，凭空造的拒绝；
3. **隐藏页拒绝**：`state != visible` 不纳入（纳入会得到空 tab）；
4. **一份整册一个 instance**：child 共享 artifact / generation；
5. **重复建册拒绝**：同一 wp 已建册则 422，不得静默建第二份。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.orm import Session

from app.models.custom_template_publication import (
    CustomTemplatePublication,
    CustomTemplatePublicationPin,
)
from app.models.project_workbook_models import (
    ProjectWorkbookInstanceRow,
    ProjectWorkbookSheetEntryRow,
)
from app.services.custom_template_ingestion.instantiate_from_publication import (
    InstantiateError,
    SheetSeedInput,
    build_sheet_seeds,
    instantiate_publication,
)
from app.services.custom_template_ingestion.lifecycles import PublicationState
from app.services.custom_template_ingestion.publication_registry_store import (
    PublicationStoreError,
    StoredPublication,
)

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
ORG = "org-inst"
DIGEST_A = "a" * 64


def _stored(state: PublicationState = PublicationState.ACTIVE, org: str = ORG) -> StoredPublication:
    return StoredPublication(
        id=uuid.uuid4(),
        publication_key="pub-1",
        organization_id=org,
        candidate_id="art-1",
        candidate_digest=DIGEST_A,
        authority_ref="auth-1",
        artifact_digest=DIGEST_A,
        state=state,
        reason=None,
        handoff={"phase": "finalized"},
        created_at=NOW,
        updated_at=NOW,
    )


PREFLIGHT_SHEETS = [
    {"sheetUid": "sheet-0-alpha", "sheetName": "甲表", "order": 0, "state": "visible"},
    {"sheetUid": "sheet-1-beta", "sheetName": "乙表", "order": 1, "state": "visible"},
    {"sheetUid": "sheet-2-hidden", "sheetName": "隐藏表", "order": 2, "state": "hidden"},
]


def _input(uid: str, wp: str = "F3") -> SheetSeedInput:
    return SheetSeedInput(
        sheet_uid=uid,
        wp_code=wp,
        component_type="audit-sheet",
        projection_mode="editable_grid",
        sheet_code=wp,
    )


@pytest.fixture()
def session() -> Session:
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
    engine = sa.create_engine("sqlite://")

    # 🔴 `project_workbook_models` 的 created_at 用 server_default=text("now()")，
    # 而 SQLite 没有 now() 函数 ⇒ 插入即 OperationalError。注册一个等价实现
    # （返回当前 UTC 时间字符串）到所有新建连接上，不改生产 DDL。
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _register_now(dbapi_conn, _rec):  # noqa: ANN001
        dbapi_conn.create_function(
            "now", 0, lambda: datetime.now(timezone.utc).isoformat(" ")
        )

    for table in (
        CustomTemplatePublication.__table__,
        CustomTemplatePublicationPin.__table__,
        ProjectWorkbookInstanceRow.__table__,
        ProjectWorkbookSheetEntryRow.__table__,
    ):
        table.create(engine, checkfirst=True)
    with Session(engine) as s:
        yield s


class TestBuildSheetSeeds:
    def test_valid_seeds(self) -> None:
        seeds = build_sheet_seeds(
            inputs=[_input("sheet-0-alpha")],
            preflight_sheets=PREFLIGHT_SHEETS,
            lineage_id="lin-1",
            version_id="pub-1",
        )
        assert len(seeds) == 1
        assert seeds[0].sheet.sheet_uid == "sheet-0-alpha"
        assert seeds[0].wp_code == "F3"

    def test_empty_inputs_rejected(self) -> None:
        with pytest.raises(InstantiateError, match="至少需要一个 sheet"):
            build_sheet_seeds(
                inputs=[], preflight_sheets=PREFLIGHT_SHEETS,
                lineage_id="l", version_id="v",
            )

    def test_unknown_sheet_uid_rejected(self) -> None:
        """🔴 凭空造的 sheetUid 必须拒绝 —— 否则能给不存在的页建 entry。"""
        with pytest.raises(InstantiateError, match="不在 preflight 报告中"):
            build_sheet_seeds(
                inputs=[_input("sheet-9-invented")],
                preflight_sheets=PREFLIGHT_SHEETS,
                lineage_id="l", version_id="v",
            )

    def test_duplicate_sheet_uid_rejected(self) -> None:
        with pytest.raises(InstantiateError, match="重复 sheetUid"):
            build_sheet_seeds(
                inputs=[_input("sheet-0-alpha"), _input("sheet-0-alpha")],
                preflight_sheets=PREFLIGHT_SHEETS,
                lineage_id="l", version_id="v",
            )

    def test_hidden_sheet_rejected(self) -> None:
        with pytest.raises(InstantiateError, match="不可纳入"):
            build_sheet_seeds(
                inputs=[_input("sheet-2-hidden")],
                preflight_sheets=PREFLIGHT_SHEETS,
                lineage_id="l", version_id="v",
            )

    def test_empty_preflight_sheet_list_rejected(self) -> None:
        with pytest.raises(InstantiateError, match="缺少 sheet 列表"):
            build_sheet_seeds(
                inputs=[_input("sheet-0-alpha")],
                preflight_sheets=[],
                lineage_id="l", version_id="v",
            )


class TestInstantiatePersists:
    def test_rows_are_written(self, session: Session) -> None:
        result = instantiate_publication(
            session,
            publication=_stored(),
            organization_id=ORG,
            project_id=str(uuid.uuid4()),
            wp_id=str(uuid.uuid4()),
            sheet_inputs=[_input("sheet-0-alpha"), _input("sheet-1-beta", "G1")],
            preflight_sheets=PREFLIGHT_SHEETS,
        )
        session.commit()

        inst_count = session.execute(
            sa.select(sa.func.count()).select_from(ProjectWorkbookInstanceRow)
        ).scalar_one()
        entry_count = session.execute(
            sa.select(sa.func.count()).select_from(ProjectWorkbookSheetEntryRow)
        ).scalar_one()
        assert inst_count == 1
        assert entry_count == 2
        assert result.sheet_count == 2

        row = session.execute(sa.select(ProjectWorkbookInstanceRow)).scalar_one()
        assert row.pinned_template_version_id == "pub-1"
        assert row.workbook_generation == 1
        assert row.current_artifact_id == "art-1"

    def test_children_share_artifact_and_generation(self, session: Session) -> None:
        """一份整册只建一个 instance：child 不复制 artifact / room。"""
        instantiate_publication(
            session,
            publication=_stored(),
            organization_id=ORG,
            project_id=str(uuid.uuid4()),
            wp_id=str(uuid.uuid4()),
            sheet_inputs=[_input("sheet-0-alpha"), _input("sheet-1-beta")],
            preflight_sheets=PREFLIGHT_SHEETS,
        )
        rows = session.execute(sa.select(ProjectWorkbookSheetEntryRow)).scalars().all()
        assert {r.workbook_instance_id for r in rows} == {
            session.execute(sa.select(ProjectWorkbookInstanceRow.workbook_instance_id)).scalar_one()
        }
        assert all(r.projection_generation == 1 for r in rows)

    def test_non_active_rejected(self, session: Session) -> None:
        with pytest.raises(PublicationStoreError, match="仅允许 ACTIVE"):
            instantiate_publication(
                session,
                publication=_stored(PublicationState.PENDING_VISIBILITY),
                organization_id=ORG,
                project_id="p", wp_id="w",
                sheet_inputs=[_input("sheet-0-alpha")],
                preflight_sheets=PREFLIGHT_SHEETS,
            )
        assert session.execute(
            sa.select(sa.func.count()).select_from(ProjectWorkbookInstanceRow)
        ).scalar_one() == 0

    def test_cross_org_rejected(self, session: Session) -> None:
        with pytest.raises(InstantiateError, match="不属于当前组织"):
            instantiate_publication(
                session,
                publication=_stored(org="other-org"),
                organization_id=ORG,
                project_id="p", wp_id="w",
                sheet_inputs=[_input("sheet-0-alpha")],
                preflight_sheets=PREFLIGHT_SHEETS,
            )

    def test_duplicate_wp_rejected(self, session: Session) -> None:
        """🔴 同一 wp 不得静默建第二份整册。"""
        wp_id = str(uuid.uuid4())
        project_id = str(uuid.uuid4())
        instantiate_publication(
            session, publication=_stored(), organization_id=ORG,
            project_id=project_id, wp_id=wp_id,
            sheet_inputs=[_input("sheet-0-alpha")],
            preflight_sheets=PREFLIGHT_SHEETS,
        )
        session.commit()
        with pytest.raises(InstantiateError, match="已建册"):
            instantiate_publication(
                session, publication=_stored(), organization_id=ORG,
                project_id=project_id, wp_id=wp_id,
                sheet_inputs=[_input("sheet-0-alpha")],
                preflight_sheets=PREFLIGHT_SHEETS,
            )
        session.rollback()
        assert session.execute(
            sa.select(sa.func.count()).select_from(ProjectWorkbookInstanceRow)
        ).scalar_one() == 1

    def test_entry_id_uses_unified_namespace(self, session: Session) -> None:
        instantiate_publication(
            session, publication=_stored(), organization_id=ORG,
            project_id="p", wp_id="w",
            sheet_inputs=[_input("sheet-0-alpha")],
            preflight_sheets=PREFLIGHT_SHEETS,
        )
        row = session.execute(sa.select(ProjectWorkbookSheetEntryRow)).scalar_one()
        assert row.entry_id.startswith("pwi-")
        assert "sheet-0-alpha" in row.entry_id
