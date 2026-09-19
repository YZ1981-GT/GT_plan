"""HTTP-wiring integration tests — Wave 9 UAT upstream fixes.

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R2, R3, R4, R12, R15
Design: §5.1 (streaming upload / read path), §6.2 (endpoints), §7.2 (stable failure classes)
Properties: P1 (项目隔离), P2 (存储边界封闭), P6 (EvidenceRef 完整性)

These tests exercise the *actual* mounted FastAPI app (httpx ASGITransport) against a
real PostgreSQL 16 connection, proving the previously-false-green wiring defects are
fixed and the endpoints are reachable (non-404) and behave per contract:

  * evidence_ref_router POST /references for a cross-project / nonexistent target →
    CLEAN 4xx SCOPE_NOT_FOUND_OR_FORBIDDEN (NOT 500) with no target project leak.
  * evidence_ref_router POST /references same-scope valid create → persists an
    evidence_ref + evidence_dependency + command-root.
  * secure upload endpoint forms an UploadAttempt BEFORE content validation, and an
    invalid (MIME-mismatch) file yields no usable Attachment/AttachmentVersion.
  * secure read endpoint denies out-of-boundary reads before any byte I/O.

Isolation: everything runs on one connection inside an outer transaction that is rolled
back at the end (savepoint join mode), so the shared DB is left untouched. Non-PG
environments skip.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

# ─────────────────────────────────────────────────────────────────────────────
# PG url (reuse the repo-wide convention: env DATABASE_URL else settings)
# ─────────────────────────────────────────────────────────────────────────────


def _pg_async_url() -> str | None:
    import os

    url = os.getenv("DATABASE_URL", "")
    if not url or "postgresql" not in url:
        try:
            from app.core.config import settings

            url = settings.DATABASE_URL or ""
        except Exception:
            url = ""
    if not url or "postgresql" not in url:
        return None
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


class _FakeUser:
    """Minimal current_user stand-in (role is authoritative from DB elsewhere;
    here we use a global-visibility role so scope membership needs no seeding)."""

    def __init__(self, uid: uuid.UUID, role: str = "partner") -> None:
        self.id = uid
        self.role = role


async def _seed_project(conn, name: str) -> uuid.UUID:
    pid = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO projects (id, name, client_name, status, version) "
            "VALUES (:id, :n, :c, 'planning', 1)"
        ),
        {"id": str(pid), "n": name, "c": "WIRING-TEST"},
    )
    return pid


async def _seed_user(conn) -> uuid.UUID:
    uid = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO users (id, username, email, hashed_password, role, is_active, is_deleted) "
            "VALUES (:id, :u, :e, 'x', 'partner', true, false)"
        ),
        {"id": str(uid), "u": f"wiring-{uid}", "e": f"{uid}@wiring.local"},
    )
    return uid


async def _seed_membership(conn, *, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Seed a project_users row so the typed adapters' can_read (which checks
    project membership, not system role) permits reads for the valid-create path."""
    await conn.execute(
        sa.text(
            "INSERT INTO project_users "
            "(id, project_id, user_id, role, permission_level, is_deleted) "
            "VALUES (:id, :pid, :uid, 'partner', 'edit', false)"
        ),
        {"id": str(uuid.uuid4()), "pid": str(project_id), "uid": str(user_id)},
    )


async def _seed_available_attachment_version(
    conn,
    *,
    project_id: uuid.UUID,
    audit_year: int,
    actor_user_id: uuid.UUID,
    file_path: str,
    content_hash: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed an available Attachment + AttachmentVersion (bypassing the gateway) for
    ref/read tests. Returns (attachment_id, version_id)."""
    att_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO attachments "
            "(id, project_id, audit_year, file_name, file_path, version, state, "
            " is_deleted, is_key_evidence, metadata_status, original_creator_unknown, "
            " current_version_id, storage_type, actor_type, actor_user_id) "
            "VALUES (:id, :pid, :yr, 'seed.pdf', :fp, 1, 'available', "
            " false, false, 'complete', false, :vid, 'local', 'user', :uid)"
        ),
        {
            "id": str(att_id), "pid": str(project_id), "yr": audit_year, "fp": file_path,
            "vid": str(ver_id), "uid": str(actor_user_id),
        },
    )
    await conn.execute(
        sa.text(
            "INSERT INTO attachment_versions "
            "(id, attachment_id, project_id, audit_year, version_no, storage_type, "
            " storage_key, media_type, byte_size, content_hash, availability, "
            " original_creator_unknown, actor_type, actor_user_id, created_at) "
            "VALUES (:id, :aid, :pid, :yr, 1, 'local', :sk, 'application/pdf', 3, :ch, "
            " 'available', false, 'user', :uid, NOW())"
        ),
        {
            "id": str(ver_id), "aid": str(att_id), "pid": str(project_id), "yr": audit_year,
            "sk": file_path, "ch": content_hash, "uid": str(actor_user_id),
        },
    )
    return att_id, ver_id


def _unwrap(body: dict) -> dict:
    """ResponseWrapperMiddleware wraps 2xx JSON as {code,message,data}; unwrap it."""
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    return body


# ═════════════════════════════════════════════════════════════════════════════
# ASGI + real-PG harness
# ═════════════════════════════════════════════════════════════════════════════


class _Harness:
    def __init__(self, engine, conn, session_factory, project_a, project_b, user_id):
        self.engine = engine
        self.conn = conn
        self.session_factory = session_factory
        self.project_a = project_a
        self.project_b = project_b
        self.user_id = user_id


@pytest.fixture
async def harness():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    url = _pg_async_url()
    if url is None:
        pytest.skip("requires PostgreSQL 16")

    engine = create_async_engine(url, echo=False)
    conn = await engine.connect()
    outer = await conn.begin()

    def _factory() -> AsyncSession:
        # New session per request, all bound to the SAME connection so committed
        # (savepoint-released) rows are visible across requests; outer txn rolled back.
        return AsyncSession(bind=conn, join_transaction_mode="create_savepoint")

    # Seed FK deps on the shared connection (visible to every request session).
    seed = _factory()
    project_a = await _seed_project(conn, f"wiring-A-{uuid.uuid4().hex[:8]}")
    project_b = await _seed_project(conn, f"wiring-B-{uuid.uuid4().hex[:8]}")
    user_id = await _seed_user(conn)
    # Membership in both projects (adapters' can_read checks project_users, not role).
    await _seed_membership(conn, project_id=project_a, user_id=user_id)
    await _seed_membership(conn, project_id=project_b, user_id=user_id)
    await seed.close()

    try:
        yield _Harness(engine, conn, _factory, project_a, project_b, user_id)
    finally:
        await outer.rollback()
        await conn.close()
        await engine.dispose()


async def _client(harness: "_Harness"):
    """Build an httpx AsyncClient over the real ASGI app with get_db/get_current_user
    overridden to the transaction-scoped connection + a global-visibility fake user."""
    import httpx

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.main import app

    async def _override_get_db():
        session = harness.session_factory()
        try:
            yield session
        finally:
            await session.close()

    def _override_current_user():
        return _FakeUser(harness.user_id, role="partner")

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user

    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    return client, app


def _cleanup_overrides(app):
    from app.core.database import get_db
    from app.deps import get_current_user

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


# ═════════════════════════════════════════════════════════════════════════════
# Task 4.4 — evidence_ref_router POST /references
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_cross_project_ref_create_returns_clean_4xx_not_500(harness):
    """Cross-project / nonexistent target → CLEAN 4xx SCOPE_NOT_FOUND_OR_FORBIDDEN,
    NOT 500, and the response must not leak the target project id.

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 1
    """
    # Seed an attachment_version that belongs to project B.
    foreign_att, foreign_ver = await _seed_available_attachment_version(
        harness.conn,
        project_id=harness.project_b,
        audit_year=2025,
        actor_user_id=harness.user_id,
        file_path="/api/attachments/x/download",
        content_hash="a" * 64,
    )

    client, app = await _client(harness)
    try:
        resp = await client.post(
            f"/api/projects/{harness.project_a}/years/2025/evidence/refs/references",
            json={
                "source_type": "attachment_version",
                "source_id": str(foreign_ver),
                "evidence_type": "attachment_version",
                "evidence_id": str(foreign_ver),
            },
            headers={"Idempotency-Key": f"cross-{uuid.uuid4().hex}"},
        )
    finally:
        _cleanup_overrides(app)
        await client.aclose()

    assert resp.status_code != 500, f"must not 500; body={resp.text}"
    assert resp.status_code == 404, f"expected clean 404; got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("error_code") == "SCOPE_NOT_FOUND_OR_FORBIDDEN", body
    # No target project leak.
    assert str(harness.project_b) not in resp.text
    assert str(foreign_att) not in resp.text


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_same_scope_valid_ref_create_persists_ref_dependency_command_root(harness):
    """Same-scope valid create → 201 and persists evidence_ref + evidence_dependency +
    command-root.

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 6
    """
    # Two available attachment_versions in project A.
    _, ver_src = await _seed_available_attachment_version(
        harness.conn, project_id=harness.project_a, audit_year=2025,
        actor_user_id=harness.user_id, file_path="/api/attachments/s/download",
        content_hash="b" * 64,
    )
    _, ver_tgt = await _seed_available_attachment_version(
        harness.conn, project_id=harness.project_a, audit_year=2025,
        actor_user_id=harness.user_id, file_path="/api/attachments/t/download",
        content_hash="c" * 64,
    )

    client, app = await _client(harness)
    try:
        resp = await client.post(
            f"/api/projects/{harness.project_a}/years/2025/evidence/refs/references",
            json={
                "source_type": "attachment_version",
                "source_id": str(ver_src),
                "evidence_type": "attachment_version",
                "evidence_id": str(ver_tgt),
            },
            headers={"Idempotency-Key": f"valid-{uuid.uuid4().hex}"},
        )
    finally:
        _cleanup_overrides(app)
        await client.aclose()

    assert resp.status_code == 201, f"expected 201; got {resp.status_code}: {resp.text}"
    data = _unwrap(resp.json())
    ref_id = data["id"]
    assert data["command_root_id"]

    # Verify persistence on the shared connection.
    ref_row = (
        await harness.conn.execute(
            sa.text("SELECT status, project_id FROM evidence_refs WHERE id = :rid"),
            {"rid": ref_id},
        )
    ).mappings().first()
    assert ref_row is not None and ref_row["status"] == "active"
    assert str(ref_row["project_id"]) == str(harness.project_a)

    dep_cnt = (
        await harness.conn.execute(
            sa.text("SELECT count(*) FROM evidence_dependencies WHERE evidence_ref_id = :rid"),
            {"rid": ref_id},
        )
    ).scalar()
    assert dep_cnt == 1, "must persist exactly one dependency edge"

    root_cnt = (
        await harness.conn.execute(
            sa.text(
                "SELECT count(*) FROM evidence_audit_command_roots "
                "WHERE id = :cid AND command_type = 'evidence_ref.create'"
            ),
            {"cid": data["command_root_id"]},
        )
    ).scalar()
    assert root_cnt == 1, "must persist exactly one command-root"


# ═════════════════════════════════════════════════════════════════════════════
# Task 3.2/3.3 — secure upload endpoint
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_upload_forms_attempt_first_and_invalid_file_yields_no_usable_attachment(harness):
    """Upload endpoint forms an UploadAttempt (converged, non-pending) even for an
    invalid (MIME-mismatch) file, and creates NO available Attachment/AttachmentVersion.

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 1/3
    """
    client, app = await _client(harness)
    try:
        # declared application/pdf but bytes are a PNG → media type mismatch (415).
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        resp = await client.post(
            f"/api/projects/{harness.project_a}/years/2025/evidence/attachments",
            files={"file": ("evil.pdf", png_bytes, "application/pdf")},
            data={"declared_media_type": "application/pdf"},
            headers={"Idempotency-Key": f"upl-{uuid.uuid4().hex}"},
        )
    finally:
        _cleanup_overrides(app)
        await client.aclose()

    assert resp.status_code != 500, resp.text
    # MIME mismatch → 415 (stable failure class, design §7.2).
    assert resp.status_code == 415, f"expected 415; got {resp.status_code}: {resp.text}"
    body = _unwrap(resp.json())
    assert body.get("outcome") in ("rejected", "quarantined", "failed"), body

    # UploadAttempt exists for project A and is converged (not pending) — attempt-first.
    att_rows = (
        await harness.conn.execute(
            sa.text(
                "SELECT validation_outcome FROM evidence_upload_attempts "
                "WHERE project_id = :pid"
            ),
            {"pid": str(harness.project_a)},
        )
    ).mappings().all()
    assert att_rows, "must persist at least one UploadAttempt before validation"
    assert all(r["validation_outcome"] != "pending" for r in att_rows), att_rows

    # No available attachment/version created for project A.
    avail_att = (
        await harness.conn.execute(
            sa.text(
                "SELECT count(*) FROM attachments "
                "WHERE project_id = :pid AND state = 'available'"
            ),
            {"pid": str(harness.project_a)},
        )
    ).scalar()
    assert avail_att == 0, "invalid upload must not create an available Attachment"
    avail_ver = (
        await harness.conn.execute(
            sa.text(
                "SELECT count(*) FROM attachment_versions "
                "WHERE project_id = :pid AND availability = 'available'"
            ),
            {"pid": str(harness.project_a)},
        )
    ).scalar()
    assert avail_ver == 0, "invalid upload must not create an available AttachmentVersion"


# ═════════════════════════════════════════════════════════════════════════════
# Task 3.4 — secure read endpoint (endpoint contract)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_secure_read_endpoint_denies_out_of_boundary(harness):
    """GET /attachments/{id}/content for an out-of-boundary storage key → desensitized
    SCOPE_NOT_FOUND_OR_FORBIDDEN, no absolute path leaked.

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 2
    """
    out_of_boundary = "/nonexistent-root/evil-secret.bin"
    att_id, _ver = await _seed_available_attachment_version(
        harness.conn, project_id=harness.project_a, audit_year=2025,
        actor_user_id=harness.user_id, file_path=out_of_boundary,
        content_hash="d" * 64,
    )

    client, app = await _client(harness)
    try:
        resp = await client.get(
            f"/api/projects/{harness.project_a}/years/2025/evidence/attachments/{att_id}/content",
        )
    finally:
        _cleanup_overrides(app)
        await client.aclose()

    assert resp.status_code != 500, resp.text
    assert resp.status_code == 404, f"expected 404; got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("error_code") == "SCOPE_NOT_FOUND_OR_FORBIDDEN", body
    assert out_of_boundary not in resp.text, "must not leak absolute path"


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_secure_read_denies_before_byte_io_spy(harness):
    """Gateway-level proof (C2): boundary failure ⇒ byte reader open/stat/read count = 0.

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 2
    """
    from app.services.evidence_governance.frozen_contracts import (
        ActorContext,
        EvidenceErrorCode,
        EvidenceGovernanceError,
    )
    from app.services.evidence_governance.secure_attachment_gateway import (
        LocalByteReader,
        SecureAttachmentGateway,
    )

    class _SpyReader(LocalByteReader):
        def __init__(self) -> None:
            self.read_calls = 0
            self.stat_calls = 0

        def read(self, path: str) -> bytes:  # pragma: no cover - must never run
            self.read_calls += 1
            return b"x"

        def stat(self, path: str) -> int:  # pragma: no cover - must never run
            self.stat_calls += 1
            return 1

    out_of_boundary = "/nonexistent-root/secret.bin"
    att_id, _ver = await _seed_available_attachment_version(
        harness.conn, project_id=harness.project_a, audit_year=2025,
        actor_user_id=harness.user_id, file_path=out_of_boundary,
        content_hash="e" * 64,
    )

    spy = _SpyReader()
    session = harness.session_factory()
    try:
        gateway = SecureAttachmentGateway(
            session,
            boundary_roots=["/an-isolated-boundary-root-only"],
            byte_reader=spy,
        )
        actor = ActorContext.for_user(harness.user_id)
        with pytest.raises(EvidenceGovernanceError) as ei:
            await gateway.read_attachment_content(
                attachment_id=att_id,
                actor=actor,
                actor_role="partner",
                requested_project_id=harness.project_a,
                requested_year=2025,
            )
        assert ei.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN
    finally:
        await session.close()

    assert spy.read_calls == 0, "byte read must NOT be called on boundary failure (C2)"
    assert spy.stat_calls == 0, "byte stat must NOT be called on boundary failure (C2)"
