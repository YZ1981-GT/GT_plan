from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest

from app.services import wp_generation_staging as staging
from app.services import wp_template_init_service as template_init
from app.services.wp_generate_file import materialize_workpaper_file


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    root = tmp_path / "wp_storage"
    monkeypatch.setattr(template_init, "STORAGE_DIR", root)
    return root


def test_materialize_target_base_writes_only_staging(tmp_path, isolated_storage, monkeypatch):
    template = tmp_path / "D2.xlsx"
    template.write_bytes(b"frozen-template")
    monkeypatch.setattr(template_init, "find_template_file_any", lambda _code: template)
    monkeypatch.setattr(template_init, "find_all_template_files", lambda _code: [template])
    project_id, wp_id, operation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    target = staging.staging_base(project_id, operation_id, wp_id)

    generated = materialize_workpaper_file(
        project_id, wp_id, "D2", "应收账款", target_base_path=target,
    )

    assert generated.path == target.with_suffix(".xlsx")
    assert generated.path.read_bytes() == b"frozen-template"
    assert not template_init.get_workpaper_storage_path(project_id, wp_id).exists()


def test_source_snapshot_changes_when_template_bytes_change(tmp_path, monkeypatch):
    template = tmp_path / "D2.xlsx"
    template.write_bytes(b"v1")
    monkeypatch.setattr(template_init, "find_template_file_any", lambda _code: template)
    monkeypatch.setattr(template_init, "find_all_template_files", lambda _code: [template])
    first, digest1 = staging.source_snapshot("D2", "normal")
    template.write_bytes(b"v2")
    second, digest2 = staging.source_snapshot("D2", "normal")
    assert digest1 != digest2
    assert first["files"][0]["sha256"] != second["files"][0]["sha256"]


def test_promote_is_recoverable_when_final_file_already_exists(isolated_storage):
    project_id, wp_id, operation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    base = staging.staging_base(project_id, operation_id, wp_id)
    source = base.with_suffix(".xlsx")
    source.write_bytes(b"payload")
    digest = _sha(source)

    first = staging.promote_staging(project_id, wp_id, str(source), digest)
    assert first.moved is True and first.path.read_bytes() == b"payload"
    second = staging.promote_staging(project_id, wp_id, str(source), digest)
    assert second.moved is False and second.path == first.path


def test_promote_rejects_conflicting_final_file(isolated_storage):
    project_id, wp_id, operation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    source = staging.staging_base(project_id, operation_id, wp_id).with_suffix(".xlsx")
    source.write_bytes(b"staged")
    target = staging.final_path(project_id, wp_id, ".xlsx")
    target.write_bytes(b"other")
    with pytest.raises(RuntimeError, match="摘要冲突"):
        staging.promote_staging(project_id, wp_id, str(source), _sha(source))
    assert source.exists() and target.read_bytes() == b"other"


def test_atomic_materialize_rejects_changed_source_and_cleans_staging(tmp_path, isolated_storage, monkeypatch):
    template = tmp_path / "D2.xlsx"
    template.write_bytes(b"v1")
    monkeypatch.setattr(template_init, "find_template_file_any", lambda _code: template)
    monkeypatch.setattr(template_init, "find_all_template_files", lambda _code: [template])
    project_id, operation_id = uuid.uuid4(), uuid.uuid4()
    item = staging.StagingItem(uuid.uuid4(), uuid.uuid4(), "D2", "应收账款")
    frozen = staging.snapshot_sources([item], "normal")[0]
    template.write_bytes(b"v2")
    guarded = staging.StagingItem(
        item.item_id, item.wp_id, item.wp_code, item.wp_name,
        expected_source_fingerprint=frozen.fingerprint,
    )
    with pytest.raises(RuntimeError, match="模板来源已变化"):
        staging.materialize_atomic(
            project_id, operation_id, [guarded], scenario="normal", has_foreign_currency=False,
        )
    assert not staging.staging_root(project_id, operation_id, create=False).exists()


def test_cleanup_refuses_path_outside_operation_root(isolated_storage, tmp_path):
    project_id, operation_id = uuid.uuid4(), uuid.uuid4()
    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(b"keep")
    with pytest.raises(ValueError, match="路径越界"):
        staging.discard_staging_file(project_id, operation_id, str(outside))
    assert outside.read_bytes() == b"keep"


def test_per_item_failure_cleans_file_created_before_helper_return(isolated_storage, monkeypatch):
    project_id, operation_id = uuid.uuid4(), uuid.uuid4()
    item = staging.StagingItem(uuid.uuid4(), uuid.uuid4(), "D2", "应收账款")

    def partial_then_fail(_project_id, jobs, **_kwargs):
        path = jobs[0].target_base_path.with_suffix(".xlsx")
        path.write_bytes(b"partial")
        raise RuntimeError("copy interrupted")

    monkeypatch.setattr(staging, "materialize_workpaper_files", partial_then_fail)
    done, failed = staging.materialize_per_item(
        project_id, operation_id, [item], scenario="normal", has_foreign_currency=False,
    )
    root = staging.staging_root(project_id, operation_id, create=False)
    assert done == [] and failed == [(item.item_id, "底稿文件准备失败，请重试；若持续失败请联系管理员")]
    assert "copy interrupted" not in failed[0][1]
    assert not list(root.glob("*")), "helper 返回前的半成品也必须按预留 wp_id 清理"
