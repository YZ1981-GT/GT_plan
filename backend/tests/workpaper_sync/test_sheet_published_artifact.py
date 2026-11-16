"""Published sheet artifact reader 守卫。"""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from openpyxl import Workbook

from app.services.workpaper_sync.sheet_published_artifact import (
    PublishedSheetArtifactError,
    read_current_published_sheet_artifact,
)


class _Result:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _Session:
    def __init__(self, row):
        self.row = row
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _Result(self.row)


class _Artifacts:
    def __init__(self, path: Path):
        self.path = path
        self.calls = []

    def resolve_published_artifact(self, **kwargs):
        self.calls.append(("resolve", kwargs))
        return self.path

    def sha256_of_file(self, path: Path):
        return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size


def _xlsx(tmp_path: Path) -> tuple[Path, str, int]:
    path = tmp_path / "published.xlsx"
    workbook = Workbook()
    workbook.active.title = "K11-1"
    workbook.create_sheet("Other")
    workbook.save(path)
    raw = path.read_bytes()
    return path, hashlib.sha256(raw).hexdigest(), len(raw)


def _rows(path: Path, digest: str, size: int):
    project_id, wp_id, representation_id, artifact_id = (uuid4() for _ in range(4))
    bundle_id = uuid4()
    representation = SimpleNamespace(
        id=representation_id,
        wp_id=wp_id,
        entry_id="xlsx/gt-k11-asset-impairment-loss",
        artifact_id=artifact_id,
        generation=3,
        definition_bundle_id=bundle_id,
        definition_bundle_sha256="a" * 64,
        adapter_id="k11.asset_impairment_loss_adjustment",
    )
    artifact = SimpleNamespace(
        id=artifact_id,
        kind="canonical",
        state="published",
        relative_path=".versions/wp/representations/k11.xlsx",
        sha256=digest,
        size_bytes=size,
        document_type="xlsx",
    )
    return project_id, wp_id, representation_id, _Session((representation, artifact))


@pytest.mark.asyncio
async def test_reads_current_published_artifact_and_target_sheet(tmp_path: Path):
    path, digest, size = _xlsx(tmp_path)
    project_id, wp_id, representation_id, session = _rows(path, digest, size)
    artifacts = _Artifacts(path)

    async def current(_session, *, entry_id):
        assert entry_id == "xlsx/gt-k11-asset-impairment-loss"
        return representation_id

    result = await read_current_published_sheet_artifact(
        session=session,
        artifact_repository=artifacts,
        project_id=project_id,
        wp_id=wp_id,
        entry_id="xlsx/gt-k11-asset-impairment-loss",
        target_sheet="K11-1",
        whole_workbook=False,
        resolve_representation=current,
    )

    assert result.path == path
    assert result.sheet_names == ("K11-1", "Other")
    assert result.target_sheet == "K11-1"
    assert result.generation == 3
    assert artifacts.calls[0][1]["kind"] == "canonical"
    assert artifacts.calls[0][1]["state"] == "published"


@pytest.mark.asyncio
async def test_missing_target_sheet_fails_without_template_fallback(tmp_path: Path):
    path, digest, size = _xlsx(tmp_path)
    project_id, wp_id, representation_id, session = _rows(path, digest, size)
    artifacts = _Artifacts(path)

    async def current(_session, *, entry_id):
        return representation_id

    with pytest.raises(PublishedSheetArtifactError, match="目标 sheet") as exc:
        await read_current_published_sheet_artifact(
            session=session,
            artifact_repository=artifacts,
            project_id=project_id,
            wp_id=wp_id,
            entry_id="xlsx/gt-k11-asset-impairment-loss",
            target_sheet="Missing",
            whole_workbook=False,
            resolve_representation=current,
        )
    assert exc.value.error_code == "target_sheet_not_in_published_artifact"


@pytest.mark.asyncio
async def test_digest_drift_fails_before_ooxml_read(tmp_path: Path):
    path, _digest, size = _xlsx(tmp_path)
    project_id, wp_id, representation_id, session = _rows(path, "b" * 64, size)
    artifacts = _Artifacts(path)

    async def current(_session, *, entry_id):
        return representation_id

    with pytest.raises(PublishedSheetArtifactError) as exc:
        await read_current_published_sheet_artifact(
            session=session,
            artifact_repository=artifacts,
            project_id=project_id,
            wp_id=wp_id,
            entry_id="xlsx/gt-k11-asset-impairment-loss",
            target_sheet="K11-1",
            whole_workbook=False,
            resolve_representation=current,
        )
    assert exc.value.error_code == "artifact_digest_drift"


@pytest.mark.asyncio
async def test_no_current_representation_is_visible_failure(tmp_path: Path):
    path, digest, size = _xlsx(tmp_path)
    project_id, wp_id, _representation_id, session = _rows(path, digest, size)
    artifacts = _Artifacts(path)

    async def current(_session, *, entry_id):
        return None

    with pytest.raises(PublishedSheetArtifactError) as exc:
        await read_current_published_sheet_artifact(
            session=session,
            artifact_repository=artifacts,
            project_id=project_id,
            wp_id=wp_id,
            entry_id="xlsx/gt-k11-asset-impairment-loss",
            target_sheet="K11-1",
            whole_workbook=False,
            resolve_representation=current,
        )
    assert exc.value.error_code == "current_representation_missing"
