"""普通底稿 content version / export / archive evidence 守卫。

spec platform-global-display-settings-closure 任务 10 / AC-22。
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

ROOT = Path(__file__).resolve().parents[1]


class TestEvidenceBuilder:
    @pytest.mark.asyncio
    async def test_formal_builder_uses_policy_snapshot_digest(self, monkeypatch):
        from app.services.workpaper_sync import export_evidence

        snapshot = json.dumps(
            {
                "_digest": "a" * 64,
                "_project_id": "11111111-2222-3333-4444-555555555555",
                "unit": "yuan",
                "divisor": 1,
                "regions": [],
            }
        )

        async def fake_snapshot(_db, *, project_id):
            assert project_id == UUID("11111111-2222-3333-4444-555555555555")
            return snapshot

        monkeypatch.setattr(
            "app.services.export_policy_snapshot.resolve_policy_snapshot_for_project",
            fake_snapshot,
        )
        evidence = await export_evidence.build_formal_content_export_evidence(
            object(), project_id=UUID("11111111-2222-3333-4444-555555555555")
        )
        assert evidence.export_surface_class == "formal"
        assert evidence.unit_policy_digest == "a" * 64
        assert evidence.unit_policy_snapshot["unit"] == "yuan"
        assert evidence.source_storage_unit is None


class TestExportAndArchiveConsumers:
    def test_workpaper_export_validates_current_content_evidence(self):
        src = (ROOT / "app/routers/wp_xlsx_export.py").read_text(encoding="utf-8")
        assert "resolve_current_content_export_evidence" in src
        assert "current_content_version_id" in src
        assert "WorkpaperExportEvidenceError" in src

    def test_archive_binds_content_evidence(self):
        src = (ROOT / "app/services/archive_inventory.py").read_text(encoding="utf-8")
        for key in (
            "content_version_id",
            "representation_id",
            "artifact_id",
            "artifact_sha256",
            "policy_digest",
        ):
            assert key in src
        assert "resolve_current_content_export_evidence" in src

    def test_formal_content_evidence_is_not_data_exchange(self):
        src = (ROOT / "app/services/workpaper_sync/export_evidence.py").read_text(encoding="utf-8")
        assert 'export_surface_class="formal"' in src
        assert "source_storage_unit=None" in src


class _FakeResult:
    """脚本化 `db.execute()` 返回：按队列给出 (kind, value)。"""

    def __init__(self, kind: str, value):
        self._kind = kind
        self._value = value

    def scalar_one_or_none(self):
        assert self._kind in {"scalar", "none"}, self._kind
        return self._value

    def scalar_one(self):
        assert self._kind == "scalar", self._kind
        return self._value

    def first(self):
        assert self._kind in {"row", "none"}, self._kind
        return self._value


class _FakeDialect:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeBind:
    def __init__(self, name: str) -> None:
        self.dialect = _FakeDialect(name)


class _FakeSession:
    """只实现 `resolve_current_content_export_evidence` 用到的那两个方法。"""

    def __init__(self, dialect: str, results: list[_FakeResult]) -> None:
        self.bind = _FakeBind(dialect)
        self._results = list(results)
        self.executed = 0

    async def execute(self, _stmt):
        self.executed += 1
        assert self._results, f"第 {self.executed} 次 execute 没有脚本化结果（夹具失锚）"
        return self._results.pop(0)


class _FakeContentVersion:
    def __init__(self, **kw) -> None:
        self.id = kw.get("id", UUID("aaaaaaaa-0000-0000-0000-000000000001"))
        self.export_surface_class = kw.get("export_surface_class")
        self.unit_policy_snapshot = kw.get("unit_policy_snapshot")
        self.unit_policy_digest = kw.get("unit_policy_digest")
        self.source_storage_unit = kw.get("source_storage_unit")


_GOOD_SNAPSHOT = {
    "_digest": "b" * 64,
    "_project_id": "11111111-2222-3333-4444-555555555555",
    "unit": "yuan",
    "divisor": 1,
    "regions": [],
}


class TestDialectCompatibilityBranch:
    """`dialect_name != "postgresql"` 的兼容分支必须**只**在旧 schema 上生效。

    🔴 这条分支是本批唯一「按方言放行」的旁路，没有守卫就是新的静默脱管口
    （memory 铁律 ㉔③：每条收窄都要配反向断言）。三条判据：

    1. 非 PG + 四列全空 ⇒ 返回 ``None``（旧导出行为，不阻断历史库回归）；
    2. **PG** + 四列全空 ⇒ 必须 fail closed（生产库缺 evidence 不得放行）；
    3. 非 PG 但四列**有值** ⇒ 不得因方言提前返回，仍按正式规则校验。
    """

    @pytest.mark.asyncio
    async def test_non_pg_legacy_schema_returns_none(self):
        from app.services.workpaper_sync.export_evidence import (
            resolve_current_content_export_evidence,
        )

        db = _FakeSession(
            "sqlite",
            [
                _FakeResult("scalar", UUID("aaaaaaaa-0000-0000-0000-000000000001")),
                _FakeResult("scalar", _FakeContentVersion()),
            ],
        )
        assert (
            await resolve_current_content_export_evidence(
                db,
                project_id=UUID("11111111-2222-3333-4444-555555555555"),
                wp_id=UUID("cccccccc-0000-0000-0000-000000000001"),
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_postgres_missing_evidence_fails_closed(self):
        from app.services.workpaper_sync.export_evidence import (
            WorkpaperExportEvidenceError,
            resolve_current_content_export_evidence,
        )

        db = _FakeSession(
            "postgresql",
            [
                _FakeResult("scalar", UUID("aaaaaaaa-0000-0000-0000-000000000001")),
                _FakeResult("scalar", _FakeContentVersion()),
            ],
        )
        with pytest.raises(WorkpaperExportEvidenceError) as excinfo:
            await resolve_current_content_export_evidence(
                db,
                project_id=UUID("11111111-2222-3333-4444-555555555555"),
                wp_id=UUID("cccccccc-0000-0000-0000-000000000001"),
            )
        assert "export_surface_class" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_non_pg_with_evidence_still_validated(self):
        """非 PG 方言不得成为「有 evidence 也跳过校验」的后门。"""
        from app.services.workpaper_sync.export_evidence import (
            WorkpaperExportEvidenceError,
            resolve_current_content_export_evidence,
        )

        # formal 但 digest 与 snapshot 不一致 ⇒ 无论方言都必须拒绝
        bad = _FakeContentVersion(
            export_surface_class="formal",
            unit_policy_snapshot={**_GOOD_SNAPSHOT, "_digest": "c" * 64},
            unit_policy_digest="d" * 64,
        )
        db = _FakeSession(
            "sqlite",
            [
                _FakeResult("scalar", UUID("aaaaaaaa-0000-0000-0000-000000000001")),
                _FakeResult("scalar", bad),
            ],
        )
        with pytest.raises(WorkpaperExportEvidenceError) as excinfo:
            await resolve_current_content_export_evidence(
                db,
                project_id=UUID("11111111-2222-3333-4444-555555555555"),
                wp_id=UUID("cccccccc-0000-0000-0000-000000000001"),
            )
        assert "digest" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_no_current_content_version_returns_none(self):
        """历史底稿（无 current version）是合法空态，不是失败。"""
        from app.services.workpaper_sync.export_evidence import (
            resolve_current_content_export_evidence,
        )

        db = _FakeSession("postgresql", [_FakeResult("none", None)])
        assert (
            await resolve_current_content_export_evidence(
                db,
                project_id=UUID("11111111-2222-3333-4444-555555555555"),
                wp_id=UUID("cccccccc-0000-0000-0000-000000000001"),
            )
            is None
        )


class TestEvidenceValidationMatrix:
    """formal / data_exchange 两条合法路径 + 四类 fail-closed 形态。"""

    @pytest.mark.asyncio
    async def test_data_exchange_requires_yuan_and_no_policy_pair(self):
        from app.services.workpaper_sync.export_evidence import (
            resolve_current_content_export_evidence,
        )

        cv = _FakeContentVersion(
            export_surface_class="data_exchange",
            source_storage_unit="yuan",
            unit_policy_snapshot=None,
            unit_policy_digest=None,
        )
        db = _FakeSession(
            "postgresql",
            [
                _FakeResult("scalar", cv.id),
                _FakeResult("scalar", cv),
                _FakeResult("none", None),  # 没有 current representation
            ],
        )
        evidence = await resolve_current_content_export_evidence(
            db,
            project_id=UUID("11111111-2222-3333-4444-555555555555"),
            wp_id=UUID("cccccccc-0000-0000-0000-000000000001"),
        )
        assert evidence is not None
        assert evidence.export_surface_class == "data_exchange"
        assert evidence.source_storage_unit == "yuan"
        assert evidence.unit_policy_snapshot is None
        assert evidence.representation_id is None

    @pytest.mark.asyncio
    async def test_data_exchange_rejects_missing_yuan(self):
        from app.services.workpaper_sync.export_evidence import (
            WorkpaperExportEvidenceError,
            resolve_current_content_export_evidence,
        )

        cv = _FakeContentVersion(
            export_surface_class="data_exchange", source_storage_unit="wan"
        )
        db = _FakeSession(
            "postgresql",
            [
                _FakeResult("scalar", cv.id),
                _FakeResult("scalar", cv),
            ],
        )
        with pytest.raises(WorkpaperExportEvidenceError) as excinfo:
            await resolve_current_content_export_evidence(
                db,
                project_id=UUID("11111111-2222-3333-4444-555555555555"),
                wp_id=UUID("cccccccc-0000-0000-0000-000000000001"),
            )
        assert "source_storage_unit" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_formal_rejects_source_storage_unit(self):
        from app.services.workpaper_sync.export_evidence import (
            WorkpaperExportEvidenceError,
            resolve_current_content_export_evidence,
        )

        cv = _FakeContentVersion(
            export_surface_class="formal",
            unit_policy_snapshot=_GOOD_SNAPSHOT,
            unit_policy_digest="b" * 64,
            source_storage_unit="yuan",
        )
        db = _FakeSession(
            "postgresql",
            [
                _FakeResult("scalar", cv.id),
                _FakeResult("scalar", cv),
            ],
        )
        with pytest.raises(WorkpaperExportEvidenceError) as excinfo:
            await resolve_current_content_export_evidence(
                db,
                project_id=UUID("11111111-2222-3333-4444-555555555555"),
                wp_id=UUID("cccccccc-0000-0000-0000-000000000001"),
            )
        assert "source_storage_unit" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_formal_with_representation_must_match_content_version(self):
        from app.services.workpaper_sync.export_evidence import (
            WorkpaperExportEvidenceError,
            resolve_current_content_export_evidence,
        )

        cv = _FakeContentVersion(
            export_surface_class="formal",
            unit_policy_snapshot=_GOOD_SNAPSHOT,
            unit_policy_digest="b" * 64,
        )
        other_cv_id = UUID("aaaaaaaa-0000-0000-0000-0000000000ff")
        rep_id = UUID("dddddddd-0000-0000-0000-000000000001")
        db = _FakeSession(
            "postgresql",
            [
                _FakeResult("scalar", cv.id),
                _FakeResult("scalar", cv),
                _FakeResult("row", (rep_id, UUID(int=1), "e" * 64)),
                _FakeResult("scalar", other_cv_id),  # 属于另一个 content version
            ],
        )
        with pytest.raises(WorkpaperExportEvidenceError) as excinfo:
            await resolve_current_content_export_evidence(
                db,
                project_id=UUID("11111111-2222-3333-4444-555555555555"),
                wp_id=UUID("cccccccc-0000-0000-0000-000000000001"),
            )
        assert "representation" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_unpublished_artifact_fails_closed(self):
        from app.services.workpaper_sync.export_evidence import (
            WorkpaperExportEvidenceError,
            resolve_current_content_export_evidence,
        )

        cv = _FakeContentVersion(
            export_surface_class="formal",
            unit_policy_snapshot=_GOOD_SNAPSHOT,
            unit_policy_digest="b" * 64,
        )
        rep_id = UUID("dddddddd-0000-0000-0000-000000000001")

        class _Artifact:
            state = "staged"
            sha256 = "e" * 64

        db = _FakeSession(
            "postgresql",
            [
                _FakeResult("scalar", cv.id),
                _FakeResult("scalar", cv),
                _FakeResult("row", (rep_id, UUID(int=1), "e" * 64)),
                _FakeResult("scalar", cv.id),
                _FakeResult("scalar", _Artifact()),
            ],
        )
        with pytest.raises(WorkpaperExportEvidenceError) as excinfo:
            await resolve_current_content_export_evidence(
                db,
                project_id=UUID("11111111-2222-3333-4444-555555555555"),
                wp_id=UUID("cccccccc-0000-0000-0000-000000000001"),
            )
        assert "artifact" in str(excinfo.value)
