"""scope / capability / ApprovalIntent 守卫。

Feature: custom-workpaper-template-ingestion-and-sync-closure
Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 11.7, 16.4
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.base import UserRole
from app.services.custom_template_ingestion.authorization import (
    APPROVER_CLASSES,
    AuthorizationEpoch,
    AuthorizationEpochMismatch,
    ApprovalIntent,
    ApprovalIntentStale,
    Capability,
    CAPABILITY_MATRIX,
    CUSTOM_DOMAIN_ACTORS,
    GC0_FINALIZED_ONLY_FIELDS,
    GC0_IDENTITY_FIELDS_CANDIDATE,
    GC0_IDENTITY_FIELDS_FINALIZED,
    InitiatorApproverSameSubject,
    ORIGINATOR_CLASSES,
    PLATFORM_TENANT_ID,
    Scope,
    ScopeError,
    TEMPLATE_ADMIN_ROLE,
    SystemClock,
    build_authority_identity_candidate,
    compute_authorization_epoch,
    derive_implicit_scope,
    is_permitted,
    organization_id_from_user,
    role_of,
)


class FakeClock:
    """可注入时钟 —— 测试不得依赖真实墙钟或 sleep（Requirement 6.7）。"""

    def __init__(self, at: str) -> None:
        from datetime import datetime, timezone

        y, m, d, H, M, S = (int(x) for x in at.split(":"))
        self._now = datetime(y, m, d, H, M, S, tzinfo=timezone.utc)

    def now(self):
        return self._now

    def advance(self, **kw) -> None:
        from datetime import datetime, timezone

        self._now = (self._now + timedelta(**kw)).replace(tzinfo=timezone.utc)


class FakeUser:
    def __init__(self, role: str = "manager", *, office_code: str | None = "BJ1",
                 is_active: bool = True) -> None:
        self.role = UserRole(role)
        self.office_code = office_code
        self.is_active = is_active


def _intent(**overrides) -> ApprovalIntent:
    base = dict(
        approval_intent_id="ai-1",
        scope="organization",
        organization_id="org:bj1",
        project_id=None,
        candidate_id="cand-1",
        candidate_digest="deadbeef",
        policy_version="1.0.0",
        requested_action="publish_organization",
        initiator_id="u-admin",
        initiator_role=TEMPLATE_ADMIN_ROLE,
        required_approver_class="partner",
        authorization_epoch=1,
        created_at=FakeClock("2026:9:8:0:0:0").now(),
        expires_at=FakeClock("2026:9:15:0:0:0").now(),
    )
    base.update(overrides)
    return ApprovalIntent(**base)


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 2.1 —— scope 绑定且服务端推导
# ─────────────────────────────────────────────────────────────────────────────


def test_scope_is_bound_to_org_and_project_when_local() -> None:
    scope = derive_implicit_scope(user=FakeUser(), project_id="p-9")
    assert scope.tenant_id == PLATFORM_TENANT_ID
    assert scope.organization_id == "org:bj1"
    assert scope.project_id == "p-9"
    assert scope.to_dict() == {
        "tenantId": "default",
        "organizationId": "org:bj1",
        "projectId": "p-9",
    }


def test_implicit_scope_never_accepts_client_supplied_values() -> None:
    """🔴 签名不接受任何客户端 scope 字段 —— 从客户端文件名/wp_code 推断即违规。"""
    import inspect

    params = inspect.signature(derive_implicit_scope).parameters
    assert set(params) == {"user", "project_id"}
    assert all(p.kind == inspect.Parameter.KEYWORD_ONLY for p in params.values())


def test_scope_rejects_inactive_user() -> None:
    with pytest.raises(ScopeError):
        derive_implicit_scope(user=FakeUser(is_active=False))


def test_organization_id_is_deterministic_and_casefolded() -> None:
    assert organization_id_from_user(FakeUser(office_code="BJ1")) == "org:bj1"
    assert organization_id_from_user(FakeUser(office_code="bj1 ")) == "org:bj1"


def test_missing_office_code_falls_back_to_stable_default_not_error() -> None:
    """存量用户大量无 office_code；抛错会让 legacy 数据全不可迁移。"""
    assert organization_id_from_user(FakeUser(office_code=None)) == "org:default"
    assert organization_id_from_user(FakeUser(office_code="   ")) == "org:default"


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 2.4 —— 角色矩阵
# ─────────────────────────────────────────────────────────────────────────────


def test_auditor_can_only_upload_and_edit_draft_mapping() -> None:
    """审计助理只能上传与编辑 draft mapping —— 不能确认/发布/实例化/写入。"""
    caps = CAPABILITY_MATRIX["auditor"]
    assert Capability.UPLOAD in caps
    for forbidden in (
        Capability.CONFIRM_MAPPING,
        Capability.PUBLISH_ORGANIZATION,
        Capability.FINALIZE_PROJECT,
        Capability.INSTANTIATE,
        Capability.WRITE_MUTATION,
    ):
        assert forbidden not in caps, f"auditor 不应拥有 {forbidden}"
        assert not is_permitted("auditor", forbidden)


def test_manager_can_finalize_project_but_not_publish_organization() -> None:
    assert is_permitted("manager", Capability.FINALIZE_PROJECT)
    assert is_permitted("manager", Capability.WRITE_MUTATION)
    assert not is_permitted("manager", Capability.PUBLISH_ORGANIZATION)


def test_only_template_admin_can_publish_organization() -> None:
    """组织级发布只有模板管理员能发起（Requirement 2.3/2.4）。"""
    for actor, caps in CAPABILITY_MATRIX.items():
        expected = actor == TEMPLATE_ADMIN_ROLE
        assert (Capability.PUBLISH_ORGANIZATION in caps) is expected, (
            f"{actor} 的 publish_organization 期望 {expected}"
        )


def test_template_admin_role_is_declared_but_not_provisioned_in_pg_enum() -> None:
    """🔴 显式锁死基线事实：PG enum `userrole` 只有 7 值、无 template_admin。

    矩阵声明它是合法 actor，但 `users.role` 永远取不到它 —— 「方法论/模板管理员
    发起发布」这条路径在迁移落地前**结构性不可达**。本测试防止有人误以为权限
    已就绪（memory: 任务标记不能假绿）。
    """
    assert TEMPLATE_ADMIN_ROLE in CUSTOM_DOMAIN_ACTORS
    assert TEMPLATE_ADMIN_ROLE not in (r.value for r in UserRole)
    assert TEMPLATE_ADMIN_ROLE in ORIGINATOR_CLASSES
    # role_of 从真实 ORM 枚举取值，永远无法产出 template_admin
    assert role_of(FakeUser(role="admin")) == "admin"
    assert role_of(FakeUser(role="partner")) == "partner"


def test_is_permitted_is_deny_by_default() -> None:
    assert not is_permitted("unknown_role", Capability.UPLOAD)
    assert not is_permitted("auditor", "custom_template.nonexistent")
    assert not is_permitted("readonly", Capability.UPLOAD)
    assert CAPABILITY_MATRIX["readonly"] == frozenset()


def test_matrix_actors_equal_platform_roles_plus_template_admin() -> None:
    assert CUSTOM_DOMAIN_ACTORS == frozenset(r.value for r in UserRole) | {TEMPLATE_ADMIN_ROLE}


def test_approver_classes_are_partner_and_qc() -> None:
    assert APPROVER_CLASSES == frozenset({"partner", "qc"})


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 2.6 / 2.7 —— capability 前置且不升级
# ─────────────────────────────────────────────────────────────────────────────


def test_read_only_high_risk_roles_cannot_download_raw_quarantine() -> None:
    """业务合伙人/QC/EQCR 只有项目读取权限时，不得自动获得 raw quarantine 下载权。"""
    for role in ("partner", "qc", "eqcr", "readonly", "auditor"):
        assert not is_permitted(role, Capability.READ_RAW_QUARANTINE), (
            f"{role} 不应获得 raw quarantine 下载权（Requirement 2.7）"
        )
    assert is_permitted(TEMPLATE_ADMIN_ROLE, Capability.READ_RAW_QUARANTINE)


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 2.2 / 2.3 / 2.5 —— ApprovalIntent
# ─────────────────────────────────────────────────────────────────────────────


def test_approval_intent_is_immutable() -> None:
    """frozen dataclass：任何原地修改必须抛 FrozenInstanceError。"""
    intent = _intent()
    with pytest.raises(Exception):
        intent.candidate_digest = "changed"  # type: ignore[misc]
    with pytest.raises(Exception):
        intent.initiator_id = "someone-else"  # type: ignore[misc]


def test_approval_intent_validates_scope_project_pairing() -> None:
    with pytest.raises(ValueError, match="project_id"):
        _intent(scope="project", project_id=None)
    with pytest.raises(ValueError, match="project_id"):
        _intent(scope="organization", project_id="p-1")
    with pytest.raises(ValueError, match="scope"):
        _intent(scope="tenant")  # type: ignore[arg-type]


def test_approval_intent_requires_candidate_digest_and_policy() -> None:
    with pytest.raises(ValueError, match="candidate"):
        _intent(candidate_digest="")
    with pytest.raises(ValueError, match="policy_version"):
        _intent(policy_version="")


def test_unauthorized_initiator_role_is_rejected() -> None:
    """发起角色不在 capability 矩阵内即拒绝 —— 不能在 finalize 末尾补权限。"""
    with pytest.raises(PermissionError):
        _intent(initiator_role="auditor", requested_action="publish_organization")


def test_expiry_must_be_after_creation() -> None:
    with pytest.raises(ValueError, match="expires_at"):
        _intent(
            created_at=FakeClock("2026:9:15:0:0:0").now(),
            expires_at=FakeClock("2026:9:8:0:0:0").now(),
        )


def test_same_initiator_and_approver_is_rejected() -> None:
    """Requirement 2.3：组织级发布 initiator 与 approver 必须不同主体。"""
    from app.services.custom_template_ingestion.authorization import approve_intent

    intent = _intent(initiator_id="u-admin")
    clock = FakeClock("2026:9:9:0:0:0")
    with pytest.raises(InitiatorApproverSameSubject):
        approve_intent(
            intent,
            approver_id="u-admin",
            approver_role="partner",
            candidate_digest="deadbeef",
            policy_version="1.0.0",
            authorization_epoch=1,
            clock=clock,
        )


def test_wrong_approver_class_is_rejected() -> None:
    from app.services.custom_template_ingestion.authorization import approve_intent

    intent = _intent(required_approver_class="partner")
    with pytest.raises(PermissionError, match="审批角色类"):
        approve_intent(
            intent,
            approver_id="u-qc",
            approver_role="qc",
            candidate_digest="deadbeef",
            policy_version="1.0.0",
            authorization_epoch=1,
            clock=FakeClock("2026:9:9:0:0:0"),
        )


def test_stale_candidate_digest_invalidates_intent() -> None:
    """Requirement 2.5：candidate digest 变化必须创建新 intent。"""
    from app.services.custom_template_ingestion.authorization import approve_intent

    intent = _intent()
    with pytest.raises(ApprovalIntentStale):
        approve_intent(
            intent,
            approver_id="u-qc",
            approver_role="partner",
            candidate_digest="CHANGED",
            policy_version="1.0.0",
            authorization_epoch=1,
            clock=FakeClock("2026:9:9:0:0:0"),
        )


def test_stale_policy_version_invalidates_intent() -> None:
    from app.services.custom_template_ingestion.authorization import approve_intent

    intent = _intent()
    with pytest.raises(ApprovalIntentStale):
        approve_intent(
            intent,
            approver_id="u-qc",
            approver_role="partner",
            candidate_digest="deadbeef",
            policy_version="2.0.0",
            authorization_epoch=1,
            clock=FakeClock("2026:9:9:0:0:0"),
        )


def test_stale_authorization_epoch_invalidates_intent() -> None:
    from app.services.custom_template_ingestion.authorization import approve_intent

    intent = _intent(authorization_epoch=1)
    with pytest.raises(ApprovalIntentStale):
        approve_intent(
            intent,
            approver_id="u-qc",
            approver_role="partner",
            candidate_digest="deadbeef",
            policy_version="1.0.0",
            authorization_epoch=2,
            clock=FakeClock("2026:9:9:0:0:0"),
        )


def test_expired_intent_is_rejected_via_injected_clock() -> None:
    from app.services.custom_template_ingestion.authorization import approve_intent

    intent = _intent(
        created_at=FakeClock("2026:9:8:0:0:0").now(),
        expires_at=FakeClock("2026:9:10:0:0:0").now(),
    )
    clock = FakeClock("2026:9:10:0:0:0")
    assert intent.is_expired(clock)
    with pytest.raises(ApprovalIntentStale, match="已过期"):
        approve_intent(
            intent,
            approver_id="u-qc",
            approver_role="partner",
            candidate_digest="deadbeef",
            policy_version="1.0.0",
            authorization_epoch=1,
            clock=clock,
        )


def test_valid_approval_succeeds() -> None:
    from app.services.custom_template_ingestion.authorization import approve_intent

    intent = _intent()
    approve_intent(
        intent,
        approver_id="u-partner",
        approver_role="partner",
        candidate_digest="deadbeef",
        policy_version="1.0.0",
        authorization_epoch=1,
        clock=FakeClock("2026:9:9:0:0:0"),
    )


def test_intent_fingerprint_is_stable_across_time_fields() -> None:
    """🔴 fingerprint 不纳入 created_at/expires_at —— 否则重签同一意图无法幂等识别。"""
    a = _intent()
    b = _intent(
        created_at=FakeClock("2026:9:8:1:0:0").now(),
        expires_at=FakeClock("2026:9:16:0:0:0").now(),
    )
    assert a.fingerprint() == b.fingerprint()
    c = _intent(candidate_digest="other")
    assert c.fingerprint() != a.fingerprint()


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 2.5 / 11.7 —— epoch 与 content fingerprint 分离
# ─────────────────────────────────────────────────────────────────────────────


def test_authorization_epoch_carries_no_content_fields() -> None:
    """🔴 epoch 只由组织/项目身份构成，绝不包含文件字节或角色 ——
    否则「换人审批」会被误判成「文件变了」，制造假 artifact 冲突。
    """
    import inspect

    params = inspect.signature(compute_authorization_epoch).parameters
    assert set(params) == {"organization_id", "project_id"}
    epoch = compute_authorization_epoch(organization_id="org:bj1", project_id="p-1")
    assert isinstance(epoch, AuthorizationEpoch)
    assert epoch.epoch == 1
    # 🔴 basis 必须是可读的规范 JSON 事实串（变异 M8：塞入 fileSha256 必须打红）
    assert epoch.basis.startswith("{") and epoch.basis.endswith("}")
    assert "org:bj1" in epoch.basis
    assert "p-1" in epoch.basis
    # 只有这两个键 —— 任何文件字节/角色字段都是违规
    import json as _json

    fact = _json.loads(epoch.basis)
    assert set(fact) == {"organizationId", "projectId"}
    for forbidden in ("fileSha256", "sha256", "role", "permission", "artifact"):
        assert forbidden not in fact, (
            f"epoch basis 含 content/权限字段 {forbidden!r} —— "
            f"Requirement 11.7 要求 epoch 与 content fingerprint 分离"
        )
    # basis_digest 由 basis 派生，不可手写
    import hashlib as _hash

    assert epoch.basis_digest == _hash.sha256(epoch.basis.encode()).hexdigest()[:8]


def test_authorization_epoch_mismatch_is_a_dedicated_error() -> None:
    assert issubclass(AuthorizationEpochMismatch, ValueError)
    with pytest.raises(AuthorizationEpochMismatch):
        raise AuthorizationEpochMismatch("epoch 1 -> 2")


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 16.4 —— 不复制 G-C0 字段定义
# ─────────────────────────────────────────────────────────────────────────────


def test_gc0_candidate_identity_field_set_matches_frontend_bundle() -> None:
    """字段名集合等值判据（非字符串存在）—— 与 G-C0 漂移即红。

    真源 = audit-platform/frontend/src/shared/contracts/gc0/index.ts
    """
    assert GC0_IDENTITY_FIELDS_CANDIDATE == frozenset({
        "contractVersion", "phase", "scope", "organizationId", "projectId",
        "candidateId", "candidateRevision", "workbookLineageId",
        "artifactSha256", "policyVersion",
    })
    assert GC0_IDENTITY_FIELDS_FINALIZED == frozenset({
        "contractVersion", "phase", "scope", "organizationId", "projectId",
        "templateId", "templateVersionId", "finalizationId",
        "workbookLineageId", "artifactSha256", "policyVersion", "manifestVersion",
    })


def test_gc0_candidate_never_carries_finalized_only_fields() -> None:
    """Requirement 9.4：candidate 不得填充 finalized-only 字段。"""
    payload = build_authority_identity_candidate(
        scope="project",
        organization_id="org:bj1",
        project_id="p-1",
        candidate_id="cand-1",
        candidate_revision="r-3",
        workbook_lineage_id="wb-1",
        artifact_sha256="a" * 64,
        policy_version="1.0.0",
    )
    keys = frozenset(payload)
    assert keys == GC0_IDENTITY_FIELDS_CANDIDATE
    assert not (keys & GC0_FINALIZED_ONLY_FIELDS)
    assert payload["phase"] == "candidate"
    assert payload["contractVersion"] == "1.0"


def test_gc0_identity_builder_rejects_extra_fields() -> None:
    """构造器内部做形状校验：多字段必须被拒绝（禁止静默丢弃）。"""
    import app.services.custom_template_ingestion.authorization as az

    original = az.GC0_IDENTITY_FIELDS_CANDIDATE
    # 模拟 G-C0 新增字段后本地未同步 —— 必须红
    with pytest.raises(ValueError, match="字段集合不符"):
        az._assert_identity_shape(
            {"contractVersion": "1.0", "phase": "candidate", "extra": 1},
            original,
            allow_extra=False,
        )
