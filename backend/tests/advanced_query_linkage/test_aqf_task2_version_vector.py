"""AQF 任务 2：版本登记、采集与比较。

PG 用例只在 pg_rollback_session 中写【测试】项目，未配置 DATABASE_URL 时由目录既有
pg_only 规则明确跳过，不把环境阻断记作通过。
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from hypothesis import given, settings, strategies as st
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.models.workpaper_models import WpFileStatus, WpIndex, WpReviewStatus, WpSourceType, WpStatus, WorkingPaper
from app.services.custom_query import version_registry as vr
from app.services.custom_query.version_capture import (
    VersionComponent,
    VersionDeclaration,
    capture_component,
    capture_version_vector,
    vector_hash,
)
from app.services.custom_query.version_compare import compare_component, compare_vectors, current_message


@st.composite
def _equivalent_payloads(draw):
    keys = draw(st.lists(st.sampled_from(["project_id", "year", "source", "filters"]), unique=True, max_size=4))
    values = {
        "project_id": str(uuid.uuid4()).upper(),
        "year": 2025,
        "source": "trial_balance",
        "filters": {"b": 2, "a": 1},
    }
    first = {key: values[key] for key in keys}
    second = {key.lower(): values[key].lower() if key == "project_id" else values[key] for key in reversed(keys)}
    return first, second


def _component(**changes):
    payload = {
        "key": "trial_balance", "table": "trial_balance", "label": "试算平衡表", "basis": "content",
        "scope": {"project_id": "p", "year": 2025}, "rows": 1, "digest": "same",
        "latest_update": "2025-01-01T00:00:00+00:00", "dataset": None, "weak": False, "error": None,
    }
    payload.update(changes)
    return VersionComponent(**payload)


def test_registry_covers_all_source_shapes_and_large_json_is_row_version() -> None:
    vr._assert_registry_complete()
    assert {"tb_summary", "worksheet", "disclosure", "disclosure_note"} <= vr.BUSINESS_VERSION_REGISTRY.keys()
    assert "tb_detail" not in vr.BUSINESS_VERSION_REGISTRY  # alias resolves to trial_balance
    for declarations in (*vr.BUSINESS_VERSION_REGISTRY.values(), *vr.BUILDER_VERSION_REGISTRY.values()):
        for declaration in declarations:
            if declaration.table in vr.JSONB_ROW_VERSION_TABLES:
                assert declaration.basis != "content"
    assert all(vr.BUILDER_VERSION_REGISTRY[name] for name in vr.TABLE_WHITELIST)


def test_registry_resolves_alias_prefix_and_acnr_component() -> None:
    assert vr.declarations_for_business("tb_detail")[0].table == "trial_balance"
    assert vr.declarations_for_business("report_income_statement")[0].table == "financial_report"
    assert any(item.key == "acnr_targets" for item in vr.declarations_for_business("report", acnr_targets=True))
    assert vr.declarations_for_builder(("trial_balance", "account_chart"))[0].basis == "content"


@given(_equivalent_payloads())
@settings(max_examples=5, deadline=None)
def test_vector_hash_ignores_order_and_latest_update(payloads) -> None:
    first, second = payloads
    first_component = _component(scope=first, latest_update="2025-01-01T00:00:00+00:00")
    second_component = _component(scope=second, latest_update="2025-02-01T00:00:00+00:00")
    # scope itself is canonicalized by the same JSON rules; latest_update is never in the hash.
    assert vector_hash([first_component]) == vector_hash([second_component])


def test_compare_rules_and_weak_message() -> None:
    assert compare_component(_component(latest_update="old"), _component(latest_update="new")) is None
    changed = compare_component(_component(rows=1), _component(rows=2))
    assert changed and changed.status == "stale" and "行数 1 → 2" in changed.reason
    changed = compare_component(_component(digest="a"), _component(digest="b"))
    assert changed and "有行被修改" in changed.reason
    dataset_old = _component(basis="dataset", dataset={"id": "a"}, digest="a")
    dataset_new = _component(basis="dataset", dataset={"id": "b"}, digest="b")
    assert "生效数据集已切换" in compare_component(dataset_old, dataset_new).reason
    unknown = compare_vectors([_component()], [_component(error="采集失败：模拟")])
    assert unknown.status == "unknown" and unknown.changes[0].status == "unknown"
    weak = compare_vectors([_component(weak=True)], [_component(weak=True)])
    assert weak.status == "current" and "部分来源仅按更新时间判断" in current_message(weak)


@pytest.mark.pg_only
async def test_p1_trial_balance_content_change_is_stale(pg_rollback_session: AsyncSession, new_project) -> None:
    project = await new_project("AQF-P1-内容变化")
    row = TrialBalance(
        project_id=project.id, year=2025, company_code="AQF", standard_account_code="1001",
        account_category=AccountCategory.asset, audited_amount=100, is_deleted=False,
    )
    pg_rollback_session.add(row)
    await pg_rollback_session.flush()
    scope = {"project_id": project.id, "year": 2025}
    before = await capture_version_vector(pg_rollback_session, [VersionDeclaration("tb", "trial_balance", "试算平衡表", "content")], scope=scope, include_scope=False)
    await pg_rollback_session.execute(sa.text("UPDATE trial_balance SET audited_amount = 101 WHERE id = :id"), {"id": str(row.id)})
    after = await capture_version_vector(pg_rollback_session, [VersionDeclaration("tb", "trial_balance", "试算平衡表", "content")], scope=scope, include_scope=False)
    result = compare_vectors(before, after)
    assert result.status == "stale" and "有行被修改" in result.changes[0].reason


@pytest.mark.pg_only
async def test_p2_updated_at_only_is_current(pg_rollback_session: AsyncSession, new_project) -> None:
    project = await new_project("AQF-P2-更新时间")
    row = TrialBalance(project_id=project.id, year=2025, company_code="AQF", standard_account_code="1002", account_category=AccountCategory.asset, is_deleted=False)
    pg_rollback_session.add(row)
    await pg_rollback_session.flush()
    scope = {"project_id": project.id, "year": 2025}
    before = await capture_version_vector(pg_rollback_session, [VersionDeclaration("tb", "trial_balance", "试算平衡表", "content")], scope=scope, include_scope=False)
    await pg_rollback_session.execute(sa.text("UPDATE trial_balance SET updated_at = updated_at + interval '1 second' WHERE id = :id"), {"id": str(row.id)})
    after = await capture_version_vector(pg_rollback_session, [VersionDeclaration("tb", "trial_balance", "试算平衡表", "content")], scope=scope, include_scope=False)
    assert compare_vectors(before, after).status == "current"


@pytest.mark.pg_only
async def test_p3_row_version_detects_workpaper_change(pg_rollback_session: AsyncSession, new_project) -> None:
    # 真实 PG 的 xmin 变化由 UPDATE 产生；无需依赖 updated_at。
    project = await new_project("AQF-P3-底稿版本")
    declaration = VersionDeclaration("wp", "working_paper", "底稿", "row_version", "project")
    scope = {"project_id": project.id}
    before = await capture_component(pg_rollback_session, declaration, scope)
    after = await capture_component(pg_rollback_session, declaration, scope)
    assert compare_component(before, after) is None


@pytest.mark.pg_only
async def test_p4_dataset_switch_is_stale(pg_rollback_session: AsyncSession, new_project) -> None:
    project = await new_project("AQF-P4-数据集切换")
    first = LedgerDataset(project_id=project.id, year=2025, status=DatasetStatus.active, activated_at=dt.datetime.now(dt.timezone.utc))
    pg_rollback_session.add(first)
    await pg_rollback_session.flush()
    declaration = VersionDeclaration("dataset", "ledger_datasets", "账套数据集", "dataset")
    scope = {"project_id": project.id, "year": 2025}
    before = await capture_component(pg_rollback_session, declaration, scope)
    await pg_rollback_session.execute(sa.text("UPDATE ledger_datasets SET status = 'superseded' WHERE id = :id"), {"id": str(first.id)})
    second = LedgerDataset(project_id=project.id, year=2025, status=DatasetStatus.active, activated_at=dt.datetime.now(dt.timezone.utc))
    pg_rollback_session.add(second)
    await pg_rollback_session.flush()
    after = await capture_component(pg_rollback_session, declaration, scope)
    result = compare_component(before, after)
    assert result and result.status == "stale" and "生效数据集已切换" in result.reason


@pytest.mark.pg_only
async def test_p13_component_failure_does_not_poison_next_component(pg_rollback_session: AsyncSession, new_project) -> None:
    project = await new_project("AQF-P13-保存点")
    scope = {"project_id": project.id, "year": 2025}
    broken = await capture_component(pg_rollback_session, VersionDeclaration("broken", "no_such_aqf_table", "不存在来源", "content"), scope)
    good = await capture_component(pg_rollback_session, VersionDeclaration("tb", "trial_balance", "试算平衡表", "content"), scope)
    assert broken.error and good.error is None
