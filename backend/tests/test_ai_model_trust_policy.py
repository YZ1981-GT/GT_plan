"""模型信任域、客户数据许可和任务路由过滤。"""

from pathlib import Path
from uuid import uuid4

import pytest

from app.models.ai_model_options import (
    AIMaskPolicy,
    AITrustZone,
    default_trust_zone,
)
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.routers.ai_models import _trust_values
from app.services.llm_provider_registry import provider_profile
from app.services.llm_route import filter_route_by_policy
from app.services.llm_runtime import LLMRuntimeError, ResolvedLLMConfig, RouteCandidate


def _candidate(
    zone: str,
    *,
    client_data_allowed: bool,
    mask_policy: str = "strict",
) -> RouteCandidate:
    config = ResolvedLLMConfig(
        model_name=zone,
        model_type=AIModelType.chat,
        provider=AIProvider.openai_compatible,
        endpoint_url="http://127.0.0.1:8100/v1",
        api_key=None,
        profile=provider_profile(AIProvider.openai_compatible),
        source="test",
        model_id=uuid4(),
        deployment="local" if zone == "local_device" else "server",
        trust_zone=zone,
        client_data_allowed=client_data_allowed,
        mask_policy=mask_policy,
    )
    return RouteCandidate(config.model_name, config.deployment, config.model_id, config)


def test_default_trust_zone_distinguishes_location_and_enterprise_preset() -> None:
    assert default_trust_zone(deployment="local") == "local_device"
    assert default_trust_zone(deployment="server", preset_key="gt-qwen") == "firm_private"
    assert default_trust_zone(deployment="server") == "restricted"


def test_trust_policy_rejects_false_local_and_unsafe_external_data() -> None:
    with pytest.raises(Exception, match="本机端点"):
        _trust_values(
            deployment="local", preset_key=None,
            trust_zone=AITrustZone.restricted,
            client_data_allowed=False, mask_policy=AIMaskPolicy.strict,
        )
    with pytest.raises(Exception, match="严格脱敏"):
        _trust_values(
            deployment="server", preset_key=None,
            trust_zone=AITrustZone.approved_provider,
            client_data_allowed=True, mask_policy=AIMaskPolicy.none,
        )


def test_task_route_filters_restricted_candidate_and_keeps_firm_private() -> None:
    restricted = _candidate("restricted", client_data_allowed=False)
    firm = _candidate("firm_private", client_data_allowed=True)
    result = filter_route_by_policy(
        [restricted, firm],
        allowed_trust_zones=frozenset({"local_device", "firm_private"}),
        client_data=True,
    )
    assert result == [firm]


def test_task_route_fails_closed_when_no_candidate_may_process_client_data() -> None:
    with pytest.raises(LLMRuntimeError) as caught:
        filter_route_by_policy(
            [_candidate("approved_provider", client_data_allowed=False)],
            allowed_trust_zones=frozenset({"approved_provider"}),
            client_data=True,
        )
    assert caught.value.code == "route_policy_denied"


def test_orm_and_migration_have_trust_policy_columns() -> None:
    assert {"trust_zone", "client_data_allowed", "mask_policy"} <= set(AIModelConfig.__table__.c.keys())
    root = Path(__file__).resolve().parents[1]
    up = (root / "migrations" / "V237__ai_model_trust_zone.sql").read_text(encoding="utf-8")
    down = (root / "migrations" / "R237__ai_model_trust_zone.sql").read_text(encoding="utf-8")
    for column in ("trust_zone", "client_data_allowed", "mask_policy"):
        assert column in up
        assert f"DROP COLUMN IF EXISTS {column}" in down


def test_ocr_route_rejects_unapproved_client_data_destination() -> None:
    from app.services.remote_ocr_runtime import (
        OCRRouteCandidate,
        RemoteOCRConfig,
        RemoteOCRRuntimeError,
        filter_ocr_route_for_client_data,
    )

    config = RemoteOCRConfig(
        model_id=uuid4(), model_name="remote-ocr", capability="ocr",
        protocol="paddlex_json", endpoint_url="https://ocr.example.com",
        api_path="/ocr", auth_scheme="none", auth_header_name=None,
        api_key=None, timeout_seconds=60, deployment="server",
        trust_zone="restricted", client_data_allowed=False, mask_policy="strict",
    )
    candidate = OCRRouteCandidate("ocr", "server", "remote-ocr", config.model_id, config)
    with pytest.raises(RemoteOCRRuntimeError) as caught:
        filter_ocr_route_for_client_data([candidate])
    assert caught.value.code == "route_policy_denied"


def test_payload_uses_strictest_policy_across_fallback_route() -> None:
    from app.services.llm_payload_policy import sanitize_messages

    local = _candidate("local_device", client_data_allowed=True, mask_policy="none")
    external = _candidate("approved_provider", client_data_allowed=True, mask_policy="strict")
    sanitized = sanitize_messages(
        [{"role": "user", "content": "重庆测试有限公司余额为 1,500,000.00 元"}],
        task_policy="role_based",
        actor_role="partner",
        route=[local, external],
    )
    assert sanitized.effective_policy == "strict"
    assert sanitized.masked_value_count >= 2
    assert "重庆测试有限公司" not in sanitized.messages[0]["content"]
    assert "1,500,000.00" not in sanitized.messages[0]["content"]


def test_role_based_policy_does_not_widen_unknown_role() -> None:
    from app.services.llm_payload_policy import sanitize_messages

    route = [_candidate("local_device", client_data_allowed=True, mask_policy="role_based")]
    partner = sanitize_messages(
        [{"role": "user", "content": "重庆测试有限公司"}],
        task_policy="role_based", actor_role="partner", route=route,
    )
    unknown = sanitize_messages(
        [{"role": "user", "content": "重庆测试有限公司"}],
        task_policy="role_based", actor_role=None, route=route,
    )
    assert partner.effective_policy == "none"
    assert partner.messages[0]["content"] == "重庆测试有限公司"
    assert unknown.effective_policy == "strict"
    assert unknown.messages[0]["content"] != "重庆测试有限公司"


def test_mask_placeholders_are_scoped_and_restored_exactly() -> None:
    from app.services.llm_payload_policy import restore_masked_values, sanitize_messages

    route = [_candidate("approved_provider", client_data_allowed=True, mask_policy="strict")]
    sanitized = sanitize_messages(
        [
            {"role": "system", "content": "甲方公司余额 1,000,000 元"},
            {"role": "user", "content": "乙方公司余额 2,000,000 元"},
        ],
        task_policy="strict", actor_role="auditor", route=route,
    )
    assert sanitized.restore_mapping
    assert len(sanitized.restore_mapping) == len(set(sanitized.restore_mapping))
    model_text = "；".join(sanitized.restore_mapping.keys())
    restored = restore_masked_values(model_text, sanitized.restore_mapping)
    assert "甲方公司" in restored and "乙方公司" in restored
    assert "1,000,000" in restored and "2,000,000" in restored


def test_model_audit_snapshot_excludes_credentials_and_full_path() -> None:
    from app.routers.ai_models import _audit_model_snapshot

    model = AIModelConfig(
        model_name="private-chat",
        model_type=AIModelType.chat,
        provider=AIProvider.openai_compatible,
        endpoint_url="https://llm.example.com/private/v1?token=secret",
        api_key_ciphertext="encrypted-secret",
        deployment="server",
        trust_zone="firm_private",
        client_data_allowed=True,
        mask_policy="role_based",
        is_active=True,
        is_deleted=False,
    )
    snapshot = _audit_model_snapshot(model)
    serialized = str(snapshot)
    assert "api_key" not in serialized
    assert "encrypted-secret" not in serialized
    assert "/private/v1" not in serialized
    assert snapshot["endpoint_origin"] == "https://llm.example.com"


def test_every_model_mutation_has_business_audit_call() -> None:
    import ast
    import inspect

    from app.routers import ai_models

    for endpoint in (
        ai_models.create_model,
        ai_models.update_model,
        ai_models.delete_model,
        ai_models.activate_model,
        ai_models.deactivate_model,
    ):
        tree = ast.parse(inspect.getsource(endpoint))
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "_audit_model_change" in calls, endpoint.__name__
    seed_tree = ast.parse(inspect.getsource(ai_models.seed_models))
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "append_audit_log"
        for node in ast.walk(seed_tree)
    )
