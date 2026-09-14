"""Wave 9 HTTP router wiring — integration tests (real PG16, in-process ASGI).

Spec: attachment-ocr-ai-evidence-governance-hardening
Design: §6.2 主要端点 (Attachment / EvidenceRef / RAG-AI / Review / Archive / Hold rows)

These tests prove the evidence-governance HTTP surfaces mounted in
``router_registry/system.py §135`` are **reachable (non-404)** and behave per the design
§6.2 contract, running the REAL app (``app.main.app``) against the REAL PG16 database via
``httpx.ASGITransport`` (no mocks; ``get_current_user`` overridden to a real admin so we
exercise the true scope/capability/facade path).

Covered surfaces:
  1. Attachment version-replace (POST .../attachments/{id}/versions) + impact (GET .../impact)
     — Task 3.5 / R2 / R9 (newly wired here).
  2. EvidenceRef create admin/partner bypass fix (POST .../refs/references) — R3/R4
     (in-scope create by admin → 201 persisted; foreign scope → clean 404).
  3. AI gate (register/eligibility/confirm) + FormalOutput preflight — R8.
  4. Review evidence bind/close gate — R9/R10.
  5. Archive preflight/build/list + verify — R11.
  6. Legal hold create + purge four-condition veto + hold-active destructive zero-effect — R13.

Isolation: fixtures create their own ephemeral attachment/version rows and delete
everything they create in teardown (best-effort). Audit rows (command-roots/transitions/
outbox) represent real operations and are left in place.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

from app.core.database import async_session
from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole

# All tests + async fixtures share ONE module-scoped event loop so the app's shared
# async engine connection pool (app.core.database.async_session) stays bound to a live
# loop across tests. With the default function-scoped loop, pooled asyncpg connections
# outlive their loop → "Event loop is closed" on the next test's first DB access.
pytestmark = pytest.mark.asyncio(loop_scope="module")

PROJECT_A = "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49"
PROJECT_B = "52c04ed1-efcf-4b7c-9800-ce5a5e840d8d"
YEAR = 2025


class _AdminUser:
    """Minimal real-admin stand-in for get_current_user override.

    ``id`` MUST be a real ``users`` row whose ``users.role='admin'`` so the create-time
    project-access check (typed_adapters._actor_can_access_project → _resolve_system_role)
    resolves the admin bypass from the authoritative DB role.
    """

    def __init__(self, uid: uuid.UUID) -> None:
        self.id = uid
        self.role = UserRole.admin


def _data(resp):
    """Unwrap ResponseWrapperMiddleware envelope ({code,message,data}) for 2xx bodies."""
    body = resp.json()
    if isinstance(body, dict) and "data" in body and set(body.keys()) >= {"code", "data"}:
        return body["data"]
    return body


async def _fetch_admin_id() -> uuid.UUID | None:
    async with async_session() as db:
        row = (
            await db.execute(
                sa.text("SELECT id FROM users WHERE role='admin' LIMIT 1")
            )
        ).first()
    return row[0] if row else None


async def _fetch_two_versions() -> tuple[list[str], str] | None:
    """Return ([version_id_a, version_id_b], attachment_id_of_a) in PROJECT_A/YEAR."""
    async with async_session() as db:
        rows = (
            await db.execute(
                sa.text(
                    "SELECT id, attachment_id FROM attachment_versions "
                    "WHERE project_id=:pid AND audit_year=:yr AND availability='available' "
                    "ORDER BY created_at DESC LIMIT 2"
                ),
                {"pid": PROJECT_A, "yr": YEAR},
            )
        ).all()
    if len(rows) < 2:
        return None
    return [str(rows[0][0]), str(rows[1][0])], str(rows[0][1])


@pytest_asyncio.fixture(loop_scope="module")
async def admin_client():
    admin_id = await _fetch_admin_id()
    if admin_id is None:
        pytest.skip("no admin user in DB")
    app.dependency_overrides[get_current_user] = lambda: _AdminUser(admin_id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, admin_id
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture(loop_scope="module")
async def fresh_attachment(admin_client):
    """Create an ephemeral available attachment + v1 in PROJECT_A/YEAR; clean up after."""
    _, admin_id = admin_client
    att_id = uuid.uuid4()
    v1_id = uuid.uuid4()
    async with async_session() as db:
        await db.execute(
            sa.text(
                "INSERT INTO attachments "
                "(id, project_id, audit_year, file_name, file_path, is_deleted, version, "
                " is_key_evidence, metadata_status, state, original_creator_unknown, "
                " created_by, actor_type, actor_user_id) "
                "VALUES (:id, :pid, :yr, :fn, :fp, false, 1, false, 'complete', "
                " 'available', false, :uid, 'user', :uid)"
            ),
            {
                "id": str(att_id),
                "pid": PROJECT_A,
                "yr": YEAR,
                "fn": "wave9_it_fixture.pdf",
                "fp": "quarantine/wave9_it_fixture.pdf",
                "uid": str(admin_id),
            },
        )
        await db.execute(
            sa.text(
                "INSERT INTO attachment_versions "
                "(id, attachment_id, project_id, audit_year, version_no, storage_type, "
                " storage_key, media_type, byte_size, content_hash, availability, "
                " actor_type, actor_user_id, original_creator_unknown) "
                "VALUES (:id, :aid, :pid, :yr, 1, 'local', :sk, 'application/pdf', 100, "
                " :hash, 'available', 'user', :uid, false)"
            ),
            {
                "id": str(v1_id),
                "aid": str(att_id),
                "pid": PROJECT_A,
                "yr": YEAR,
                "sk": "quarantine/wave9_it_fixture_v1",
                "hash": "a" * 64,
                "uid": str(admin_id),
            },
        )
        await db.execute(
            sa.text("UPDATE attachments SET current_version_id=:v WHERE id=:id"),
            {"v": str(v1_id), "id": str(att_id)},
        )
        await db.commit()

    yield str(att_id), str(v1_id)

    # teardown — detach current version, delete versions + attachment + any refs to them.
    async with async_session() as db:
        await db.execute(
            sa.text("UPDATE attachments SET current_version_id=NULL WHERE id=:id"),
            {"id": str(att_id)},
        )
        await db.execute(
            sa.text(
                "DELETE FROM evidence_dependencies WHERE source_id=:aid OR target_id=:aid"
            ),
            {"aid": str(att_id)},
        )
        await db.execute(
            sa.text("DELETE FROM attachment_versions WHERE attachment_id=:aid"),
            {"aid": str(att_id)},
        )
        await db.execute(
            sa.text("DELETE FROM attachments WHERE id=:id"), {"id": str(att_id)}
        )
        await db.commit()


async def _cleanup_refs(intent_hashes: list[str]) -> None:
    if not intent_hashes:
        return
    async with async_session() as db:
        await db.execute(
            sa.text(
                "DELETE FROM evidence_dependencies WHERE evidence_ref_id IN "
                "(SELECT id FROM evidence_refs WHERE intent_hash = ANY(:ih))"
            ),
            {"ih": intent_hashes},
        )
        await db.execute(
            sa.text("DELETE FROM evidence_refs WHERE intent_hash = ANY(:ih)"),
            {"ih": intent_hashes},
        )
        await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Item 5 — Attachment version-replace + impact
# ─────────────────────────────────────────────────────────────────────────────


async def test_attachment_version_replace_creates_vn_plus_1_and_old_immutable(
    admin_client, fresh_attachment
):
    client, _ = admin_client
    att_id, v1_id = fresh_attachment
    base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/attachments"

    resp = await client.post(
        f"{base}/{att_id}/versions",
        json={"new_content_hash": "b" * 64, "new_media_type": "application/pdf",
              "new_byte_size": 200, "new_storage_key": "quarantine/v2"},
    )
    assert resp.status_code == 201, resp.text
    body = _data(resp)
    assert body["new_version_no"] == 2
    assert body["previous_version_id"] == v1_id
    new_v2 = body["new_version_id"]

    # DB truth: v2 exists at version_no=2; v1 unchanged (immutable); current pointer moved.
    async with async_session() as db:
        v2 = (
            await db.execute(
                sa.text("SELECT version_no, content_hash FROM attachment_versions WHERE id=:id"),
                {"id": new_v2},
            )
        ).first()
        v1 = (
            await db.execute(
                sa.text("SELECT version_no, content_hash FROM attachment_versions WHERE id=:id"),
                {"id": v1_id},
            )
        ).first()
        cur = (
            await db.execute(
                sa.text("SELECT current_version_id, version FROM attachments WHERE id=:id"),
                {"id": att_id},
            )
        ).first()
    assert v2[0] == 2 and v2[1] == "b" * 64
    assert v1[0] == 1 and v1[1] == "a" * 64  # old version untouched
    assert str(cur[0]) == new_v2 and cur[1] == 2


async def test_attachment_impact_endpoint_reachable(admin_client, fresh_attachment):
    client, _ = admin_client
    att_id, _ = fresh_attachment
    base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/attachments"

    resp = await client.get(f"{base}/{att_id}/impact")
    assert resp.status_code == 200, resp.text
    body = _data(resp)
    assert body["attachment_id"] == att_id
    assert body["blocked"] is False  # fresh attachment: no refs/holds/formal outputs
    assert body["total_count"] == 0


async def test_attachment_impact_foreign_scope_denied(admin_client, fresh_attachment):
    client, _ = admin_client
    att_id, _ = fresh_attachment
    # PROJECT_B path but attachment belongs to PROJECT_A → desensitized 404.
    base = f"/api/projects/{PROJECT_B}/years/{YEAR}/evidence/attachments"
    resp = await client.get(f"{base}/{att_id}/impact")
    assert resp.status_code == 404, resp.text
    assert resp.json()["error_code"] == "SCOPE_NOT_FOUND_OR_FORBIDDEN"


# ─────────────────────────────────────────────────────────────────────────────
# Item 6 — EvidenceRef create admin/partner bypass fix (R3/R4)
# ─────────────────────────────────────────────────────────────────────────────


async def test_create_ref_same_scope_by_admin_succeeds_and_persists(admin_client):
    client, _ = admin_client
    pair = await _fetch_two_versions()
    if pair is None:
        pytest.skip("need 2 available attachment_versions in PROJECT_A")
    (v_src, v_tgt), _ = pair
    base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/refs"

    created_intents: list[str] = []
    try:
        resp = await client.post(
            f"{base}/references",
            json={
                "source_type": "attachment_version",
                "source_id": v_src,
                "evidence_type": "attachment_version",
                "evidence_id": v_tgt,
                "label": "wave9-it",
            },
            headers={"Idempotency-Key": "ref-it-" + uuid.uuid4().hex},
        )
        assert resp.status_code == 201, resp.text
        body = _data(resp)
        ref_id = body["id"]
        assert body["intent_hash"]
        assert body["idempotent_hit"] is False

        # persisted in DB
        async with async_session() as db:
            row = (
                await db.execute(
                    sa.text("SELECT status, intent_hash FROM evidence_refs WHERE id=:id"),
                    {"id": ref_id},
                )
            ).first()
        assert row is not None and row[0] == "active"
        created_intents.append(row[1])
    finally:
        await _cleanup_refs(created_intents)


async def test_create_ref_foreign_scope_denied_even_for_admin(admin_client):
    client, _ = admin_client
    pair = await _fetch_two_versions()
    if pair is None:
        pytest.skip("need 2 available attachment_versions in PROJECT_A")
    (v_src, v_tgt), _ = pair
    # PROJECT_B path scope; source/evidence belong to PROJECT_A → resolve None → clean 404.
    base = f"/api/projects/{PROJECT_B}/years/{YEAR}/evidence/refs"
    resp = await client.post(
        f"{base}/references",
        json={
            "source_type": "attachment_version",
            "source_id": v_src,
            "evidence_type": "attachment_version",
            "evidence_id": v_tgt,
        },
        # unique key so this executes business logic (not an idempotency replay of a
        # prior in-scope command that shares source/evidence ids).
        headers={"Idempotency-Key": "ref-foreign-" + uuid.uuid4().hex},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error_code"] == "SCOPE_NOT_FOUND_OR_FORBIDDEN"
    # and nothing persisted
    async with async_session() as db:
        cnt = (
            await db.execute(
                sa.text(
                    "SELECT count(*) FROM evidence_refs WHERE project_id=:pid AND source_id=:sid"
                ),
                {"pid": PROJECT_B, "sid": v_src},
            )
        ).scalar()
    assert cnt == 0


# ─────────────────────────────────────────────────────────────────────────────
# Item 1 — AI evidence gate + FormalOutput (R8)
# ─────────────────────────────────────────────────────────────────────────────


async def test_ai_gate_register_then_unconfirmed_blocks_formal_output(admin_client):
    client, _ = admin_client
    base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/ai"
    content_id = None
    try:
        reg = await client.post(
            f"{base}/generations",
            json={
                "entry_point": "generate_text",  # must be a declared AI entry point (P18)
                "prompt_hash": "wave9-it-" + uuid.uuid4().hex,
                "model_name": "test-model",
                "output": "AI 生成的候选文本",
                "service_status": "available",
            },
            headers={"Idempotency-Key": "ai-gen-" + uuid.uuid4().hex},
        )
        assert reg.status_code == 201, reg.text
        body = _data(reg)
        content_id = body["content_id"]
        assert body["lifecycle_status"] == "draft"

        # Unconfirmed AI content is NOT eligible for FormalOutput (P17 gate blocks).
        elig = await client.get(f"{base}/generations/{content_id}/eligibility")
        assert elig.status_code == 200, elig.text
        ebody = _data(elig)
        assert ebody["eligible"] is False
        assert len(ebody["reasons"]) >= 1

        # Human confirm → draft→confirmed.
        conf = await client.post(f"{base}/generations/{content_id}/confirm")
        assert conf.status_code == 200, conf.text
        assert _data(conf)["confirmed"] is True
    finally:
        if content_id:
            async with async_session() as db:
                await db.execute(
                    sa.text("DELETE FROM ai_content_governance WHERE id=:id"),
                    {"id": content_id},
                )
                await db.commit()


async def test_formal_output_preflight_reachable(admin_client):
    client, _ = admin_client
    base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/ai"
    resp = await client.post(
        f"{base}/formal-output/preflight",
        json={"target_id": "report-" + uuid.uuid4().hex, "target_type": "report"},
    )
    assert resp.status_code == 200, resp.text
    body = _data(resp)
    assert "watermark" in body and "verdict" in body


# ─────────────────────────────────────────────────────────────────────────────
# Item 2 — Review evidence bind / close gate (R9/R10)
# ─────────────────────────────────────────────────────────────────────────────


async def test_review_close_without_nonstale_evidence_is_blocked(admin_client):
    client, _ = admin_client
    review_id = str(uuid.uuid4())
    base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/reviews"
    # Close a review that has NO bound (non-stale) evidence → gate blocks (P21).
    resp = await client.post(
        f"{base}/{review_id}/close",
        json={"closing_explanation": "关闭说明足够充分以满足门禁要求", "severity": "high"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error_code"] == "EVIDENCE_GATE_BLOCKED"


async def test_review_bind_then_close_and_state_readable(admin_client):
    client, _ = admin_client
    pair = await _fetch_two_versions()
    if pair is None:
        pytest.skip("need attachment_versions in PROJECT_A")
    (v_src, v_tgt), _ = pair
    refs_base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/refs"
    rev_base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/reviews"
    review_id = str(uuid.uuid4())
    created_intents: list[str] = []
    try:
        # create a real, active evidence_ref to bind (non-stale)
        cr = await client.post(
            f"{refs_base}/references",
            json={
                "source_type": "attachment_version", "source_id": v_src,
                "evidence_type": "attachment_version", "evidence_id": v_tgt,
                "label": "wave9-review-it",
            },
            headers={"Idempotency-Key": "ref-rev-" + uuid.uuid4().hex},
        )
        assert cr.status_code == 201, cr.text
        ref_id = _data(cr)["id"]
        async with async_session() as db:
            ih = (
                await db.execute(
                    sa.text("SELECT intent_hash FROM evidence_refs WHERE id=:id"),
                    {"id": ref_id},
                )
            ).scalar()
        created_intents.append(ih)

        bind = await client.post(
            f"{rev_base}/{review_id}/evidence",
            json={"evidence_ref_id": ref_id, "target_hash": "h1", "locator": {"page": 1}},
        )
        assert bind.status_code == 201, bind.text

        close = await client.post(
            f"{rev_base}/{review_id}/close",
            json={"closing_explanation": "已核对绑定证据，复核意见可关闭", "severity": "high"},
        )
        assert close.status_code == 200, close.text
        assert _data(close)["status"] == "closed"

        # read endpoint exposes version/hash/stale/locator (QC/EQCR view)
        state = await client.get(f"{rev_base}/{review_id}")
        assert state.status_code == 200, state.text
        sbody = _data(state)
        assert sbody["status"] == "closed"
        assert sbody["closed_by_user_id"] is not None
        assert isinstance(sbody["evidence"], list) and len(sbody["evidence"]) >= 1
    finally:
        async with async_session() as db:
            await db.execute(
                sa.text("DELETE FROM review_evidence_snapshots WHERE review_id=:r"),
                {"r": review_id},
            )
            await db.execute(
                sa.text("DELETE FROM review_closes WHERE review_id=:r"), {"r": review_id}
            )
            await db.commit()
        await _cleanup_refs(created_intents)


# ─────────────────────────────────────────────────────────────────────────────
# Item 3 — Archive manifest preflight / build / verify (R11)
# ─────────────────────────────────────────────────────────────────────────────


async def test_archive_preflight_and_build_invariant(admin_client):
    client, _ = admin_client
    # Use PROJECT_B (empty evidence graph) → fast, isolated; asserts the success⊕blocking
    # invariant: successful archive returns NO blocking report; blocked archive returns one.
    base = f"/api/projects/{PROJECT_B}/years/{YEAR}/evidence/archive"
    created_manifest_ids: list[str] = []
    try:
        pf = await client.post(f"{base}/preflight", json={})
        assert pf.status_code == 200, pf.text
        assert "watermark" in _data(pf)

        build = await client.post(
            f"{base}/manifests", json={},
            headers={"Idempotency-Key": "archive-build-" + uuid.uuid4().hex},
        )
        assert build.status_code == 201, build.text
        b = _data(build)
        created_manifest_ids.append(b["manifest_id"])
        if b.get("success"):
            # successful archive → NO blocking difference report
            assert not b.get("blocked")
            assert not b.get("blocking_difference_report")
            # verify endpoint reachable + validates the returned sealed package
            ver = await client.post(
                f"{base}/verify", json={"package": b["sealed_package"]}
            )
            assert ver.status_code == 200, ver.text
        else:
            # blocked archive → blocking difference report present
            assert b.get("blocked") is True
            assert b.get("blocking_difference_report")

        lst = await client.get(f"{base}/manifests")
        assert lst.status_code == 200, lst.text
        assert isinstance(_data(lst)["items"], list)
    finally:
        async with async_session() as db:
            for mid in created_manifest_ids:
                await db.execute(
                    sa.text("DELETE FROM archive_manifest_edges WHERE archive_manifest_id=:m"),
                    {"m": mid},
                )
                await db.execute(
                    sa.text("DELETE FROM archive_manifest_entries WHERE archive_manifest_id=:m"),
                    {"m": mid},
                )
            await db.execute(
                sa.text("DELETE FROM archive_manifests WHERE project_id=:p AND audit_year=:y"),
                {"p": PROJECT_B, "y": YEAR},
            )
            await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Item 4 — Legal hold create + purge four-condition veto + destructive zero-effect (R13)
# ─────────────────────────────────────────────────────────────────────────────


async def test_legal_hold_vetoes_destructive_and_purge_four_condition(
    admin_client, fresh_attachment
):
    client, _ = admin_client
    att_id, _ = fresh_attachment
    base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/legal-holds"
    att_base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/attachments"
    hold_id = None
    try:
        # create hold seeded with the attachment node
        create = await client.post(
            f"{base}",
            json={
                "reason": "诉讼保全 wave9-it",
                "seed_nodes": [{"node_type": "attachment", "node_id": att_id}],
            },
            headers={"Idempotency-Key": "hold-create-" + uuid.uuid4().hex},
        )
        assert create.status_code == 201, create.text
        cbody = _data(create)
        hold_id = cbody["legal_hold_id"]
        assert cbody["direct_count"] >= 1

        # destructive: version replace under active hold → 423 zero-effect
        repl = await client.post(
            f"{att_base}/{att_id}/versions",
            json={"new_content_hash": "c" * 64},
        )
        assert repl.status_code == 423, repl.text
        assert repl.json()["error_code"] == "LEGAL_HOLD_ACTIVE"
        # confirm no new version created (delta=0)
        async with async_session() as db:
            n = (
                await db.execute(
                    sa.text("SELECT count(*) FROM attachment_versions WHERE attachment_id=:a"),
                    {"a": att_id},
                )
            ).scalar()
        assert n == 1  # still only v1

        # purge four-condition: hold active + retention not expired → allowed=false, delta=0
        purge = await client.post(
            f"{base}/purge-jobs",
            json={"node_type": "attachment", "node_id": att_id, "retention_expired": False},
        )
        assert purge.status_code == 200, purge.text
        pbody = _data(purge)
        assert pbody["allowed"] is False
        assert pbody["delta"] == 0
        assert len(pbody["unmet_conditions"]) >= 1
        assert pbody["tombstone_id"] is None
    finally:
        async with async_session() as db:
            if hold_id:
                await db.execute(
                    sa.text("DELETE FROM legal_hold_scopes WHERE legal_hold_id=:h"),
                    {"h": hold_id},
                )
                await db.execute(
                    sa.text("DELETE FROM legal_holds WHERE id=:h"), {"h": hold_id}
                )
            await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Item 7 — Citation snapshot create + locate + source-replace invalidation (R7/R9)
#   UAT-09. POST .../citations registers an immutable CitationSnapshot from an active
#   EvidenceRef via CitationSnapshotService.create_citation_from_retrieval (no filter
#   relaxation); GET .../citations/{id}/locate re-authenticates and derives status.
# ─────────────────────────────────────────────────────────────────────────────


async def test_citation_create_locate_then_source_deactivation_invalidates(admin_client):
    client, _ = admin_client
    pair = await _fetch_two_versions()
    if pair is None:
        pytest.skip("need attachment_versions in PROJECT_A")
    (v_src, _), _ = pair
    refs_base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/refs"
    cit_base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/citations"

    # target hash/version of the bound attachment version (for exact hash binding, P15)
    async with async_session() as db:
        row = (
            await db.execute(
                sa.text(
                    "SELECT content_hash, version_no FROM attachment_versions WHERE id=:id"
                ),
                {"id": v_src},
            )
        ).mappings().first()
    tgt_hash = row["content_hash"]
    tgt_ver = row["version_no"]

    intents: list[str] = []
    citation_id = None
    acl_id = None
    try:
        # 1. active EvidenceRef bound to the attachment version (evidence side).
        cr = await client.post(
            f"{refs_base}/references",
            json={
                "source_type": "attachment_version", "source_id": v_src,
                "evidence_type": "attachment_version", "evidence_id": v_src,
                "target_version": tgt_ver, "target_hash": tgt_hash,
                "label": "wave9-citation-it",
            },
            headers={"Idempotency-Key": "ref-cit-" + uuid.uuid4().hex},
        )
        assert cr.status_code == 201, cr.text
        ref_id = _data(cr)["id"]
        async with async_session() as db:
            ih = (
                await db.execute(
                    sa.text("SELECT intent_hash FROM evidence_refs WHERE id=:id"),
                    {"id": ref_id},
                )
            ).scalar()
        intents.append(ih)

        # 2. create citation — 201 with precise page/region/version/hash (P15).
        cc = await client.post(
            cit_base,
            json={
                "evidence_ref_id": ref_id,
                "page": 3,
                "region": {"x": 12, "y": 20, "w": 100, "h": 40},
                "excerpt_text": "关键金额 1,234.00",
                "index_version": "idx-v1",
                "locator_version": "loc-v1",
            },
            headers={"Idempotency-Key": "cit-" + uuid.uuid4().hex},
        )
        assert cc.status_code == 201, cc.text
        cbody = _data(cc)
        citation_id = cbody["citation_id"]
        acl_id = cbody["ai_content_log_id"]
        assert cbody["page"] == 3
        assert cbody["region"] == {"x": 12, "y": 20, "w": 100, "h": 40}
        assert cbody["target_hash"] == tgt_hash
        assert cbody["status"] == "active"

        # 3. locate — active + precise version/page/region (R7.3 re-auth passes).
        loc = await client.get(f"{cit_base}/{citation_id}/locate")
        assert loc.status_code == 200, loc.text
        lbody = _data(loc)
        assert lbody["status"] == "active"
        assert lbody["readable"] is True
        assert lbody["version_valid"] is True and lbody["hash_valid"] is True
        assert lbody["page"] == 3
        assert lbody["region"] == {"x": 12, "y": 20, "w": 100, "h": 40}

        # 4. replace/deactivate the source EvidenceRef → citation becomes invalid/stale.
        dz = await client.post(
            f"{refs_base}/references/{ref_id}/deactivate",
            json={"reason": "source replaced (wave9 citation it)"},
            headers={"Idempotency-Key": "deact-cit-" + uuid.uuid4().hex},
        )
        assert dz.status_code == 200, dz.text

        loc2 = await client.get(f"{cit_base}/{citation_id}/locate")
        assert loc2.status_code == 200, loc2.text
        l2 = _data(loc2)
        assert l2["status"] == "invalid"
        assert l2["reason"] == "evidence_ref_deactivated"
        # invalid citation exposes no locatable page/region (must re-verify) — R7.3.
        assert l2["page"] is None and l2["region"] is None
    finally:
        # Delete citation snapshots referencing the ref(s) BEFORE the refs (FK RESTRICT).
        # The ref may be an idempotent reuse shared with other snapshots, so clear all
        # snapshots bound to these intents, not just this test's citation_id.
        async with async_session() as db:
            if intents:
                await db.execute(
                    sa.text(
                        "DELETE FROM citation_snapshots WHERE evidence_ref_id IN "
                        "(SELECT id FROM evidence_refs WHERE intent_hash = ANY(:ih))"
                    ),
                    {"ih": intents},
                )
            if citation_id:
                await db.execute(
                    sa.text("DELETE FROM citation_snapshots WHERE id=:id"),
                    {"id": citation_id},
                )
            if acl_id:
                await db.execute(
                    sa.text("DELETE FROM ai_content_log WHERE id=:id"), {"id": acl_id}
                )
            await db.commit()
        await _cleanup_refs(intents)


async def test_citation_create_unknown_ref_is_desensitized_404(admin_client):
    client, _ = admin_client
    cit_base = f"/api/projects/{PROJECT_A}/years/{YEAR}/evidence/citations"
    resp = await client.post(
        cit_base,
        json={
            "evidence_ref_id": str(uuid.uuid4()),
            "page": 1,
            "region": {"x": 0, "y": 0, "w": 1, "h": 1},
        },
        headers={"Idempotency-Key": "cit-missing-" + uuid.uuid4().hex},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error_code"] == "SCOPE_NOT_FOUND_OR_FORBIDDEN"
