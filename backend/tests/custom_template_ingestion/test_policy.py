"""ingestion policy / quota / scanner provenance 守卫。

Feature: custom-workpaper-template-ingestion-and-sync-closure
Validates: Requirements 3.3, 3.4, 3.5, 3.6, 3.7, 4.3, 4.4, 4.5, 4.6, 4.7, 6.7
"""
from __future__ import annotations

import hashlib
import json
import math

import pytest

from app.services.custom_template_ingestion.policy import (
    AdmissionResult,
    CustomTemplateIngestionPolicy,
    FeatureDecision,
    Finding,
    FINDING_EMPTY_REPORT,
    FINDING_WITHIN_LIMITS,
    POLICY_VERSION_V1,
    POLICY_V1,
    PreflightResult,
    ResourceObservation,
    ScannerProvenance,
    ScannerProvenanceError,
    Severity,
    Verdict,
    build_provenance,
    check_organization_quota,
    decide_feature,
    derive_verdict,
    finalize_allowed,
    validate_against_policy,
)


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 3.3 —— 政策是唯一真源，阈值齐全且自洽
# ─────────────────────────────────────────────────────────────────────────────


def test_policy_v1_covers_every_threshold_family_in_requirement_3_3() -> None:
    """Requirement 3.3 列举的每一类阈值都必须有对应字段。"""
    policy = POLICY_V1
    # 字节 / 条目 / 比例
    assert policy.max_upload_bytes == 50 * 1024**2
    assert policy.max_expanded_bytes == 512 * 1024**2
    assert policy.max_zip_entries == 20_000
    assert policy.max_entry_compression_ratio == 100.0
    assert policy.max_total_compression_ratio == 100.0
    # sheet / cell / range
    assert policy.max_sheets == 256
    assert policy.max_non_empty_cells == 5_000_000
    assert policy.max_declared_range_cells == 20_000_000
    # XML
    assert policy.max_xml_bytes > 0
    assert policy.max_xml_depth > 0
    assert policy.max_xml_nodes > 0
    assert policy.max_relationships > 0
    # 资源
    assert policy.max_cpu_seconds > 0
    assert policy.max_wall_seconds == 120
    assert policy.max_ram_bytes > 0
    assert policy.max_file_descriptors > 0
    assert policy.max_temp_disk_bytes > 0
    # 组织 quota
    assert policy.organization_concurrency > 0
    assert policy.organization_storage_bytes > 0
    # TTL（Requirement 15.6：24h / 7d / 30d）
    assert policy.incoming_ttl_seconds == 24 * 3600
    assert policy.failed_artifact_ttl_seconds == 7 * 24 * 3600
    assert policy.candidate_ttl_seconds == 30 * 24 * 3600


def test_policy_version_is_explicitly_versioned() -> None:
    version = POLICY_V1.version
    assert version.startswith("custom-template-ingestion-policy/v1")
    assert POLICY_VERSION_V1 == POLICY_V1.version


def test_policy_is_immutable() -> None:
    """frozen + slots：阈值不可原地改，必须新建 policy。"""
    with pytest.raises(Exception):
        POLICY_V1.max_upload_bytes = 1  # type: ignore[misc]


def test_policy_rejects_non_positive_thresholds() -> None:
    """🔴 阈值被写成 0/负数 会静默放行或静默拒绝全部 —— 构造即报错。"""
    for name in ("max_upload_bytes", "max_zip_entries", "max_sheets", "max_wall_seconds"):
        with pytest.raises(ValueError, match=f"{name}"):
            CustomTemplateIngestionPolicy(**{name: 0})
        with pytest.raises(ValueError, match=f"{name}"):
            CustomTemplateIngestionPolicy(**{name: -1})


def test_policy_rejects_non_finite_floats() -> None:
    """NaN/inf 阈值会让比较运算全部返回 False，静默放行 —— 构造即报错。"""
    for name in ("max_entry_compression_ratio", "max_total_compression_ratio", "max_cpu_seconds"):
        with pytest.raises(ValueError, match=f"{name}"):
            CustomTemplateIngestionPolicy(**{name: math.nan})
        with pytest.raises(ValueError, match=f"{name}"):
            CustomTemplateIngestionPolicy(**{name: math.inf})


def test_policy_rejects_empty_version() -> None:
    with pytest.raises(ValueError, match="version"):
        CustomTemplateIngestionPolicy(version="")
    with pytest.raises(ValueError, match="version"):
        CustomTemplateIngestionPolicy(version="   ")


def test_policy_enforces_compression_ratio_consistency() -> None:
    """单项压缩比不得大于总压缩比，否则单项检查形同虚设。"""
    with pytest.raises(ValueError, match="max_entry_compression_ratio"):
        CustomTemplateIngestionPolicy(
            max_entry_compression_ratio=200.0, max_total_compression_ratio=100.0
        )


def test_policy_enforces_upload_not_greater_than_expanded() -> None:
    with pytest.raises(ValueError, match="max_upload_bytes"):
        CustomTemplateIngestionPolicy(
            max_upload_bytes=1024**3, max_expanded_bytes=1024**2
        )


def test_policy_enforces_ttl_strictly_increasing() -> None:
    """TTL 不递增会让 retention 先删后保，违反 Requirement 15.6 期限语义。"""
    with pytest.raises(ValueError, match="TTL"):
        CustomTemplateIngestionPolicy(
            incoming_ttl_seconds=30 * 24 * 3600,
            failed_artifact_ttl_seconds=7 * 24 * 3600,
            candidate_ttl_seconds=24 * 3600,
        )


def test_policy_never_carries_role_or_permission_fields() -> None:
    """🔴 policy 只描述摄取约束，绝不参与权限判断（Requirement 11.7 边界）。"""
    fields = set(CustomTemplateIngestionPolicy.__dataclass_fields__)
    for forbidden in (
        "role", "roles", "permission", "permissions", "capabilities",
        "actor_id", "initiator", "approver", "authorization_epoch",
    ):
        assert forbidden not in fields, f"policy 含权限字段 {forbidden!r}"


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 4.3 – 4.7 —— OOXML 能力矩阵 fail-closed
# ─────────────────────────────────────────────────────────────────────────────


def test_xlsx_is_allowed_to_preflight() -> None:
    assert decide_feature("container.xlsx") is FeatureDecision.ALLOW_TO_PREFLIGHT
    assert finalize_allowed(decide_feature("container.xlsx"))


def test_xlsm_is_preflight_only_and_never_finalize_capable() -> None:
    """Requirement 4.4：.xlsm v1 只允许 quarantine + 只读 preflight，finalize 永久阻断。

    🔴 这里是结构性保证：PREFLIGHT_ONLY 不在 FINALIZE_CAPABLE 中，而不是靠
    散落 if 判断扩展名。
    """
    decision = decide_feature("container.xlsm")
    assert decision is FeatureDecision.PREFLIGHT_ONLY
    assert not finalize_allowed(decision)


def test_macro_dde_activex_ole_are_blocked() -> None:
    """Requirement 4.5：VBA/XLM/DDE/ActiveX/OLE 无条件 BLOCK，无豁免路径。"""
    for feature in (
        "vba_macro", "xlm_macro", "dde_link",
        "activex_control", "ole_embedded_object", "remote_data_connection",
    ):
        assert decide_feature(feature) is FeatureDecision.BLOCK, feature
        assert not finalize_allowed(decide_feature(feature))


def test_external_links_are_permanently_blocked_in_v1() -> None:
    """Requirement 4.6：external link/relationship/data connection v1 永久 BLOCKER。"""
    for feature in ("external_link", "external_relationship", "external_data_connection"):
        assert decide_feature(feature) is FeatureDecision.BLOCK, feature
        assert not finalize_allowed(decide_feature(feature))


def test_encrypted_corrupt_package_is_blocked() -> None:
    for feature in ("encrypted_package", "password_protected", "corrupt_package"):
        assert decide_feature(feature) is FeatureDecision.BLOCK, feature


def test_unknown_feature_is_block_pending_policy_not_allowed() -> None:
    """Requirement 4.7：未知能力 fail-closed，绝不默认 ALLOW。"""
    assert decide_feature("some_new_feature") is FeatureDecision.BLOCK_PENDING_POLICY
    assert decide_feature("") is FeatureDecision.BLOCK_PENDING_POLICY
    assert decide_feature(None) is FeatureDecision.BLOCK_PENDING_POLICY
    assert decide_feature("   ") is FeatureDecision.BLOCK_PENDING_POLICY
    assert not finalize_allowed(decide_feature("never_seen_before"))


def test_decide_feature_is_casefolded_and_trimmed() -> None:
    assert decide_feature("Container.XLSX") is FeatureDecision.ALLOW_TO_PREFLIGHT
    assert decide_feature("  vba_macro  ") is FeatureDecision.BLOCK


def test_allowed_features_require_preservation_inventory() -> None:
    """Requirement 4.7：允许项必须进入 preservation inventory，不得静默丢失。"""
    from app.services.custom_template_ingestion.policy import (
        FEATURE_MATRIX,
        PRESERVATION_INVENTORY_FEATURES,
    )

    preserved = set(PRESERVATION_INVENTORY_FEATURES)
    allowed = {
        key for key, decision in FEATURE_MATRIX.items()
        if decision is FeatureDecision.ALLOW_TO_PREFLIGHT
    }
    # 容器格式不算 preservation inventory；其余允许项必须登记
    assert preserved <= allowed
    assert allowed - {"container.xlsx"} == preserved


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 3.6 / 3.7 —— 空报告永不 valid，超限结构化失败
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_observation_never_yields_valid() -> None:
    """🔴 Requirement 3.6：不得返回空报告或 valid=true。"""
    result = validate_against_policy(ResourceObservation())
    assert result.verdict is Verdict.BLOCKED
    assert not result.is_valid
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.code == FINDING_EMPTY_REPORT
    assert finding.severity is Severity.BLOCKER
    assert result.policy_version == POLICY_VERSION_V1


def test_derive_verdict_has_no_implicit_pass_branch() -> None:
    """🔴 findings 为空时 verdict=BLOCKED，不存在「无 finding 即 valid」。"""
    assert derive_verdict(()) is Verdict.BLOCKED


def test_valid_report_requires_explicit_info_finding() -> None:
    info = Finding(
        code=FINDING_WITHIN_LIMITS,
        severity=Severity.INFO,
        locator="ResourceObservation",
        policy_decision="全部上报项均在政策阈值内",
        remediation="无需处理",
    )
    assert derive_verdict((info,)) is Verdict.PREFLIGHT_READY


def test_within_limits_returns_preflight_ready() -> None:
    obs = ResourceObservation(
        upload_bytes=1024,
        expanded_bytes=2048,
        zip_entries=3,
        entry_compression_ratio=2.0,
        total_compression_ratio=2.0,
        sheets=2,
        non_empty_cells=10,
        max_declared_range_cells=100,
        xml_bytes=512,
        xml_depth=4,
        xml_nodes=50,
        relationships=5,
        cpu_seconds=1.0,
        wall_seconds=2.0,
        ram_bytes=1024 * 1024,
        file_descriptors=8,
        temp_disk_bytes=4096,
        organization_active_preflights=1,
        organization_storage_used_bytes=1024,
    )
    result = validate_against_policy(obs)
    assert result.verdict is Verdict.PREFLIGHT_READY
    assert result.is_valid
    assert result.findings[0].code == FINDING_WITHIN_LIMITS


def test_each_limit_is_enforced_as_structured_blocker() -> None:
    """逐项超限都必须产生 ``POLICY.<field>_exceeded`` 结构化 BLOCKER。"""
    from app.services.custom_template_ingestion.policy import _OBSERVATION_LIMITS

    cases = [
        ("upload_bytes", POLICY_V1.max_upload_bytes + 1),
        ("expanded_bytes", POLICY_V1.max_expanded_bytes + 1),
        ("zip_entries", POLICY_V1.max_zip_entries + 1),
        ("entry_compression_ratio", POLICY_V1.max_entry_compression_ratio + 1),
        ("total_compression_ratio", POLICY_V1.max_total_compression_ratio + 1),
        ("sheets", POLICY_V1.max_sheets + 1),
        ("non_empty_cells", POLICY_V1.max_non_empty_cells + 1),
        ("max_declared_range_cells", POLICY_V1.max_declared_range_cells + 1),
        ("xml_bytes", POLICY_V1.max_xml_bytes + 1),
        ("xml_depth", POLICY_V1.max_xml_depth + 1),
        ("xml_nodes", POLICY_V1.max_xml_nodes + 1),
        ("relationships", POLICY_V1.max_relationships + 1),
        ("cpu_seconds", POLICY_V1.max_cpu_seconds + 1),
        ("wall_seconds", POLICY_V1.max_wall_seconds + 1),
        ("ram_bytes", POLICY_V1.max_ram_bytes + 1),
        ("file_descriptors", POLICY_V1.max_file_descriptors + 1),
        ("temp_disk_bytes", POLICY_V1.max_temp_disk_bytes + 1),
        ("organization_active_preflights", POLICY_V1.organization_concurrency + 1),
        ("organization_storage_used_bytes", POLICY_V1.organization_storage_bytes + 1),
    ]
    # 🔴 用 _OBSERVATION_LIMITS 单一真源查阈值字段名 —— 测试不重抄字段名翻译表。
    obs_to_limit = dict(_OBSERVATION_LIMITS)
    for field_name, bad_value in cases:
        obs = ResourceObservation(**{field_name: bad_value})
        result = validate_against_policy(obs)
        assert result.verdict is Verdict.BLOCKED, field_name
        codes = {f.code for f in result.findings}
        assert f"POLICY.{field_name}_exceeded" in codes, field_name
        hit = next(f for f in result.findings if f.code == f"POLICY.{field_name}_exceeded")
        assert hit.severity is Severity.BLOCKER
        assert hit.observed == bad_value
        assert hit.limit == getattr(POLICY_V1, obs_to_limit[field_name])


def test_missing_fields_are_not_treated_as_zero_pass() -> None:
    """🔴 缺失字段不能当 0 放行 —— 只上报一项超限，其余缺失不应掩盖。"""
    obs = ResourceObservation(upload_bytes=1, sheets=POLICY_V1.max_sheets + 1)
    result = validate_against_policy(obs)
    assert result.verdict is Verdict.BLOCKED
    assert any(f.code == "POLICY.sheets_exceeded" for f in result.findings)
    # 其余缺失字段不得产生伪 INFO 或伪超限
    assert not any(f.code == FINDING_WITHIN_LIMITS for f in result.findings)


def test_negative_observation_is_blocked_not_zeroed() -> None:
    """scanner 崩溃上报负值时必须结构化 BLOCKER，不得当 0 放行。"""
    obs = ResourceObservation(upload_bytes=-1)
    result = validate_against_policy(obs)
    assert result.verdict is Verdict.BLOCKED
    assert result.findings[0].code == "POLICY.invalid_observation"
    assert result.findings[0].severity is Severity.BLOCKER


def test_nan_observation_is_blocked() -> None:
    obs = ResourceObservation(wall_seconds=math.nan)
    result = validate_against_policy(obs)
    assert result.verdict is Verdict.BLOCKED
    assert result.findings[0].code == "POLICY.invalid_observation"


def test_infinity_observation_is_blocked() -> None:
    obs = ResourceObservation(expanded_bytes=None, total_compression_ratio=math.inf)
    result = validate_against_policy(obs)
    assert result.verdict is Verdict.BLOCKED


def test_boolean_observation_is_not_accepted_as_number() -> None:
    """bool 是 int 的子类 —— 必须显式排除，否则 True 会被当 1 放行。"""
    obs = ResourceObservation(zip_entries=True)  # type: ignore[arg-type]
    result = validate_against_policy(obs)
    assert result.verdict is Verdict.BLOCKED
    assert result.findings[0].code == "POLICY.invalid_observation"


def test_exactly_at_limit_is_not_exceeded() -> None:
    """边界语义：等于阈值不算超限（>，不是 >=）。"""
    obs = ResourceObservation(sheets=POLICY_V1.max_sheets)
    result = validate_against_policy(obs)
    assert result.verdict is Verdict.PREFLIGHT_READY


def test_finding_roundtrips_to_dict() -> None:
    """超限 finding 的结构化字段完整序列化（Requirement 3.7 的可解释性）。"""
    result = validate_against_policy(
        ResourceObservation(zip_entries=POLICY_V1.max_zip_entries + 1)
    )
    payload = result.to_dict()
    assert payload["valid"] is False
    assert payload["verdict"] == "BLOCKED"
    assert payload["policyVersion"] == POLICY_VERSION_V1
    assert len(payload["findings"]) == 1
    serialized = payload["findings"][0]
    assert serialized["code"] == "POLICY.zip_entries_exceeded"
    assert serialized["severity"] == "BLOCKER"
    assert serialized["locator"] == "zip_entries"
    assert serialized["limit"] == POLICY_V1.max_zip_entries
    assert serialized["observed"] == POLICY_V1.max_zip_entries + 1
    assert "policyDecision" in serialized and "remediation" in serialized


def test_policy_threshold_change_produces_different_verdict() -> None:
    """阈值收紧后原本通过的观测变 BLOCKED —— 政策是唯一判据。"""
    obs = ResourceObservation(sheets=100)
    loose = CustomTemplateIngestionPolicy(max_sheets=256)
    tight = CustomTemplateIngestionPolicy(max_sheets=50)
    assert validate_against_policy(obs, loose).verdict is Verdict.PREFLIGHT_READY
    assert validate_against_policy(obs, tight).verdict is Verdict.BLOCKED


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 3.3 —— 组织 quota 准入
# ─────────────────────────────────────────────────────────────────────────────


def test_organization_quota_admits_within_limits() -> None:
    result = check_organization_quota(
        organization_id="org:bj1",
        active_preflights=1,
        storage_used_bytes=1024,
        pending_upload_bytes=1024,
    )
    assert isinstance(result, AdmissionResult)
    assert result.admitted
    assert result.findings == ()
    assert result.organization_id == "org:bj1"


def test_organization_concurrency_quota_blocks() -> None:
    result = check_organization_quota(
        organization_id="org:bj1",
        active_preflights=POLICY_V1.organization_concurrency,
        storage_used_bytes=0,
        pending_upload_bytes=0,
    )
    assert not result.admitted
    assert any(f.code == "POLICY.organization_concurrency_exceeded" for f in result.findings)
    assert all(f.severity is Severity.BLOCKER for f in result.findings)


def test_organization_storage_quota_accounts_for_pending_upload() -> None:
    """🔴 pending_upload_bytes 必须累加进已用存储 —— 否则并发请求全通过后存储爆掉。"""
    result = check_organization_quota(
        organization_id="org:bj1",
        active_preflights=0,
        storage_used_bytes=POLICY_V1.organization_storage_bytes,
        pending_upload_bytes=1,
    )
    assert not result.admitted
    assert any(f.code == "POLICY.organization_storage_exceeded" for f in result.findings)


def test_organization_storage_exact_fit_is_admitted() -> None:
    result = check_organization_quota(
        organization_id="org:bj1",
        active_preflights=0,
        storage_used_bytes=POLICY_V1.organization_storage_bytes - 1024,
        pending_upload_bytes=1024,
    )
    assert result.admitted


def test_organization_quota_fails_closed_on_invalid_input() -> None:
    for kwargs in (
        dict(organization_id="", active_preflights=0, storage_used_bytes=0, pending_upload_bytes=0),
        dict(organization_id="org:bj1", active_preflights=-1, storage_used_bytes=0, pending_upload_bytes=0),
        dict(organization_id="org:bj1", active_preflights=0, storage_used_bytes=-5, pending_upload_bytes=0),
        dict(organization_id="org:bj1", active_preflights=0, storage_used_bytes=0, pending_upload_bytes=-1),
        dict(organization_id="org:bj1", active_preflights="many", storage_used_bytes=0, pending_upload_bytes=0),
    ):
        result = check_organization_quota(**kwargs)
        assert not result.admitted, kwargs
        assert result.findings[0].code == "POLICY.quota_input_invalid"


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 3.5 / 3.4 —— scanner provenance 与 stale 判定
# ─────────────────────────────────────────────────────────────────────────────


def _provenance(**overrides) -> ScannerProvenance:
    base = dict(
        policy_version=POLICY_V1.version,
        policy_fingerprint=POLICY_V1.fingerprint(),
        scanner_build_digest="sha256:scanner-build-abc123",
        worker_image_digest="sha256:worker-image-def456",
        parser_versions={"openpyxl": "3.1.5", "lxml": "5.3.0"},
    )
    base.update(overrides)
    return ScannerProvenance(**base)  # type: ignore[arg-type]


def test_provenance_fingerprint_is_derived_not_client_supplied() -> None:
    """🔴 fingerprint 由 policy + scanner build + worker image + parser versions 派生。

    变异项「scanner digest 复用」（Requirement 17.2）必须打红：手工注入一个
    「看起来匹配」的 digest 不改变派生值。
    """
    prov = _provenance()
    expected_payload = json.dumps(
        {
            "policyVersion": prov.policy_version,
            "policyFingerprint": prov.policy_fingerprint,
            "scannerBuildDigest": prov.scanner_build_digest,
            "workerImageDigest": prov.worker_image_digest,
            "parserVersions": prov.parser_versions,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    assert prov.fingerprint() == hashlib.sha256(expected_payload.encode()).hexdigest()
    assert len(prov.fingerprint()) == 64
    # fingerprint 不是任何单一输入的回声
    assert prov.fingerprint() != prov.scanner_build_digest
    assert prov.fingerprint() != prov.worker_image_digest
    assert prov.fingerprint() != prov.policy_fingerprint


def test_provenance_fingerprint_ignores_resource_observations() -> None:
    """🔴 资源用量随运行波动，不得参与 stale 判定。"""
    a = _provenance(resource_observations=ResourceObservation(upload_bytes=1))
    b = _provenance(resource_observations=ResourceObservation(upload_bytes=999999))
    assert a.fingerprint() == b.fingerprint()


def test_policy_threshold_change_makes_old_evidence_stale() -> None:
    """Requirement 3.4：policy 阈值变化必须使旧 evidence stale。"""
    prov = _provenance()
    assert not prov.is_stale_for(
        policy=POLICY_V1,
        scanner_build_digest=prov.scanner_build_digest,
        worker_image_digest=prov.worker_image_digest,
    )
    tightened = CustomTemplateIngestionPolicy(max_sheets=10)
    assert tightened.fingerprint() != POLICY_V1.fingerprint()
    assert prov.is_stale_for(
        policy=tightened,
        scanner_build_digest=prov.scanner_build_digest,
        worker_image_digest=prov.worker_image_digest,
    )


def test_scanner_build_change_makes_old_evidence_stale() -> None:
    """Requirement 3.5：未知构建不得复用旧 PASS。"""
    prov = _provenance()
    assert prov.is_stale_for(
        policy=POLICY_V1,
        scanner_build_digest="sha256:some-other-build",
        worker_image_digest=prov.worker_image_digest,
    )


def test_worker_image_change_makes_old_evidence_stale() -> None:
    prov = _provenance()
    assert prov.is_stale_for(
        policy=POLICY_V1,
        scanner_build_digest=prov.scanner_build_digest,
        worker_image_digest="sha256:rebuilt-worker",
    )


def test_staleness_comparing_fingerprints_not_version_strings() -> None:
    """🔴 version 相同但阈值不同仍判 stale —— 只比 version 字符串会漏。"""
    prov = _provenance()
    same_version_different_threshold = CustomTemplateIngestionPolicy(
        version=POLICY_V1.version, max_sheets=3
    )
    assert same_version_different_threshold.version == prov.policy_version
    assert prov.is_stale_for(
        policy=same_version_different_threshold,
        scanner_build_digest=prov.scanner_build_digest,
        worker_image_digest=prov.worker_image_digest,
    )


def test_build_provenance_derives_policy_fingerprint_from_policy() -> None:
    """🔴 不接受客户端传入的 policy_fingerprint —— 由 policy 唯一计算。"""
    prov = build_provenance(
        policy=POLICY_V1,
        scanner_build_digest="sha256:b1",
        worker_image_digest="sha256:i1",
        parser_versions={"openpyxl": "3.1.5"},
        resource_observations=ResourceObservation(upload_bytes=10),
    )
    assert prov.policy_fingerprint == POLICY_V1.fingerprint()
    assert prov.policy_version == POLICY_V1.version
    assert prov.resource_observations.upload_bytes == 10
    assert not prov.is_stale_for(
        policy=POLICY_V1,
        scanner_build_digest="sha256:b1",
        worker_image_digest="sha256:i1",
    )


def test_provenance_rejects_empty_fields() -> None:
    """policy_version / scanner build / worker image / parser versions 不可为空。"""
    with pytest.raises(ScannerProvenanceError, match="policy_version"):
        _provenance(policy_version="")
    with pytest.raises(ScannerProvenanceError, match="scanner_build_digest"):
        _provenance(scanner_build_digest="")
    with pytest.raises(ScannerProvenanceError, match="worker_image_digest"):
        _provenance(worker_image_digest="   ")
    with pytest.raises(ScannerProvenanceError, match="parser_versions"):
        _provenance(parser_versions={})


def test_provenance_roundtrips_to_dict_with_fingerprint() -> None:
    prov = _provenance()
    payload = prov.to_dict()
    assert payload["provenanceFingerprint"] == prov.fingerprint()
    assert payload["scannerBuildDigest"] == prov.scanner_build_digest
    assert payload["parserVersions"] == prov.parser_versions
    # 资源用量单独序列化供审计
    assert payload["resourceObservations"]["upload_bytes"] is None
