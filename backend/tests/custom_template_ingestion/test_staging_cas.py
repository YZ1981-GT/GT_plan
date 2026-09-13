"""Task 13 守卫：staging CAS，禁止原地写 current。"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.custom_template_ingestion.staging_cas import (
    DefaultStagingCasGate,
    GridMutationPayload,
    InMemoryAuthoritativeWriter,
    StagingCasError,
    assert_no_inplace_current_write,
    run_staging_cas,
)


def _payload(**kw) -> GridMutationPayload:
    base = dict(
        workbook_instance_id="wid-1",
        sheet_uid="s1",
        entry_id="pwi-wid-1:s1",
        managed_values={"A1": 1},
        client_content_revision="rev-0",
        client_representation_revision="rrep-0",
        authorization_epoch=1,
        operation_id="op-1",
        reason="grid_mutation",
    )
    base.update(kw)
    return GridMutationPayload(**base)


def test_cas_success_advances_revision():
    writer = InMemoryAuthoritativeWriter(current_revision="rev-0")
    result = run_staging_cas(
        base_bytes=b"PK\x03\x04fake-xlsx",
        payload=_payload(),
        current_revision="rev-0",
        authorization_fence=1,
        writer=writer,
    )
    assert result.committed is True
    assert result.new_content_revision is not None
    assert writer.current_revision == result.new_content_revision
    assert len(writer.commits) == 1


def test_client_base_mismatch_discards_staging_keeps_current():
    writer = InMemoryAuthoritativeWriter(current_revision="rev-server")
    with pytest.raises(StagingCasError, match="client base"):
        run_staging_cas(
            base_bytes=b"base",
            payload=_payload(client_content_revision="rev-stale"),
            current_revision="rev-server",
            authorization_fence=1,
            writer=writer,
        )
    assert writer.current_revision == "rev-server"
    assert writer.commits == []


def test_cas_reject_when_writer_revision_raced():
    writer = InMemoryAuthoritativeWriter(current_revision="rev-0")

    def _apply_then_race(path: Path, values):
        path.write_bytes(path.read_bytes() + b"-patched")
        writer.current_revision = "rev-raced"  # 模拟并发推进

    result = run_staging_cas(
        base_bytes=b"base",
        payload=_payload(),
        current_revision="rev-0",
        authorization_fence=1,
        writer=writer,
        apply_fn=_apply_then_race,
    )
    assert result.committed is False
    assert result.discarded_staging is True
    assert writer.current_revision == "rev-raced"
    assert writer.commits == []


def test_rejects_opaque_entry_namespace():
    writer = InMemoryAuthoritativeWriter(current_revision="rev-0")
    with pytest.raises(StagingCasError, match="pwi-"):
        run_staging_cas(
            base_bytes=b"base",
            payload=_payload(entry_id="opaque-CX-1"),
            current_revision="rev-0",
            authorization_fence=1,
            writer=writer,
        )


def test_module_forbids_inplace_write_cells():
    src = Path(__file__).resolve().parents[2] / "app/services/custom_template_ingestion/staging_cas.py"
    assert assert_no_inplace_current_write(src.read_text(encoding="utf-8")) == []
