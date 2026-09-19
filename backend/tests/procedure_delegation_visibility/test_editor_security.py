# Feature: procedure-delegation-visibility-isolation — Task 11 EditorSecurity（组件 C11）
"""OnlyOffice/WOPI 令牌绑定、文件权限与 callback 重校验测试。

Task 11 / Requirements 8.8–8.9, 10.1–10.11, 16.14–16.17 /
Design 组件 C11 EditorSecurity / Property 10 / Property 13。

- **Property 13**（editor tokens remain bound through callback execution）：
  OnlyOffice/WOPI token 完整、签名、过期、URL/resource/action 绑定正确；callback 执行时
  重新校验版本、动作和撤权状态。
- **Property 10**（binding/claim conflict fail-closed）：token claim 任一冲突在写/副作用前拒绝。

纯令牌校验（签名/过期/jti/非空/逐 claim 绑定/写权限）无需 DB；gate 集成（signed_token 全量校验
经统一门）在真实 PostgreSQL（audit_platform）验证，非 sqlite。冻结 JWT_Lifetime 有限正值。
"""
from __future__ import annotations

import time
from uuid import uuid4

import pytest
from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st
from jose import jwt

from app.core.config import settings as app_settings
from app.services.wp_visibility.denial import DenialReason, ExternalNotFound
from app.services.wp_visibility.editor_security import (
    JWT_LIFETIME_CONFIG_ID,
    READ_ACTIONS,
    REQUIRED_EDITOR_CLAIMS,
    WRITE_ACTIONS,
    claims_bound_to,
    compute_user_can_write,
    frozen_jwt_lifetime_seconds,
    sign_editor_token,
    validate_editor_token,
    verify_callback_preconditions,
)
from app.services.wp_visibility.wp_bound_gate import (
    BindingAdapters,
    resolve_wp_binding_and_access,
)

from ._factories import (
    IS_PG,
    mk_project,
    mk_project_user,
    mk_staff,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)
from .test_wp_bound_gate import CapturingResponder, _lead_scenario

_SECRET = "task11-editor-test-secret"
_BA = BindingAdapters()


def _expected(**over) -> dict:
    base = {
        "project_id": "p1",
        "wp_id": "w1",
        "sheet_name": "D2A",
        "wp_code": "D2-1",
        "version": "1",
        "action": "editor_config",
    }
    base.update(over)
    return base


def _sign(**over) -> str:
    kw = dict(
        secret=_SECRET,
        sub="user-1",
        project_id="p1",
        wp_id="w1",
        sheet_name="D2A",
        wp_code="D2-1",
        version="1",
        action="editor_config",
    )
    kw.update(over)
    return sign_editor_token(**kw)


# ===========================================================================
# 冻结 JWT_Lifetime（Req 10.10/10.11）
# ===========================================================================
class TestFrozenJwtLifetime:
    def test_lifetime_is_finite_positive(self):
        val = frozen_jwt_lifetime_seconds()
        assert isinstance(val, int)
        assert val >= 1  # 有限正值，绝非 0/负/无限

    def test_lifetime_config_id_stable(self):
        assert JWT_LIFETIME_CONFIG_ID == "ONLYOFFICE_JWT_LIFETIME_SECONDS"
        assert getattr(app_settings, JWT_LIFETIME_CONFIG_ID) == frozen_jwt_lifetime_seconds()


# ===========================================================================
# 令牌签发 + 全量校验（Req 10.1–10.5, 10.8, 10.9；Property 13）
# ===========================================================================
class TestEditorTokenValidation:
    def test_sign_and_validate_roundtrip(self):
        token = _sign()
        res = validate_editor_token(token, secret=_SECRET, expected=_expected())
        assert res.ok is True
        assert res.reason is None
        # 全 claim 完整非空
        for k in REQUIRED_EDITOR_CLAIMS:
            assert str(res.claims.get(k) or "").strip() != ""

    def test_signed_token_carries_all_required_claims(self):
        token = _sign()
        claims = jwt.decode(token, _SECRET, algorithms=["HS256"])
        for k in REQUIRED_EDITOR_CLAIMS:
            assert k in claims and str(claims[k]).strip() != ""

    def test_missing_secret_fail_closed(self):
        token = _sign()
        res = validate_editor_token(token, secret="", expected=_expected())
        assert res.ok is False and res.reason == "secret_missing"

    def test_empty_token_fail_closed(self):
        for tok in (None, "", "   "):
            res = validate_editor_token(tok, secret=_SECRET, expected=_expected())
            assert res.ok is False and res.reason == "token_missing"

    def test_bad_signature_fail_closed(self):
        token = _sign()
        res = validate_editor_token(token, secret="other-secret", expected=_expected())
        assert res.ok is False and res.reason == "bad_signature"

    def test_expired_token_fail_closed(self):
        past = int(time.time()) - 10_000
        token = _sign()  # normal
        # forge an expired token by signing with now far in past + tiny lifetime
        expired = sign_editor_token(
            secret=_SECRET, sub="u", project_id="p1", wp_id="w1", sheet_name="D2A",
            wp_code="D2-1", version="1", action="editor_config",
            lifetime_seconds=1, now=past,
        )
        res = validate_editor_token(expired, secret=_SECRET, expected=_expected())
        assert res.ok is False and res.reason == "expired"
        # sanity: fresh token not expired
        assert validate_editor_token(token, secret=_SECRET, expected=_expected()).ok

    def test_empty_claim_fail_closed(self):
        # manually craft token with empty required claim (sheet_name="")
        iat = int(time.time())
        payload = {
            "sub": "u", "project_id": "p1", "wp_id": "w1", "sheet_name": "",
            "wp_code": "D2-1", "version": "1", "action": "editor_config",
            "iat": iat, "exp": iat + 900, "jti": "jti-1",
        }
        token = jwt.encode(payload, _SECRET, algorithm="HS256")
        res = validate_editor_token(token, secret=_SECRET, expected=_expected(sheet_name=""))
        assert res.ok is False and res.reason == "empty_claim"

    def test_missing_claim_fail_closed(self):
        iat = int(time.time())
        payload = {  # 缺 jti
            "sub": "u", "project_id": "p1", "wp_id": "w1", "sheet_name": "D2A",
            "wp_code": "D2-1", "version": "1", "action": "editor_config",
            "iat": iat, "exp": iat + 900,
        }
        token = jwt.encode(payload, _SECRET, algorithm="HS256")
        res = validate_editor_token(token, secret=_SECRET, expected=_expected())
        assert res.ok is False and res.reason == "missing_claim"

    def test_jti_required_non_empty(self):
        iat = int(time.time())
        payload = {
            "sub": "u", "project_id": "p1", "wp_id": "w1", "sheet_name": "D2A",
            "wp_code": "D2-1", "version": "1", "action": "editor_config",
            "iat": iat, "exp": iat + 900, "jti": "",
        }
        token = jwt.encode(payload, _SECRET, algorithm="HS256")
        res = validate_editor_token(token, secret=_SECRET, expected=_expected())
        assert res.ok is False and res.reason == "empty_claim"

    @pytest.mark.parametrize(
        "field", ["project_id", "wp_id", "sheet_name", "wp_code", "version", "action"]
    )
    def test_cross_resource_replay_claim_mismatch(self, field):
        """为资源 A 签发的令牌用于资源 B（任一绑定 claim 不一致）→ claim_mismatch。"""
        token = _sign()
        exp = _expected(**{field: "TAMPERED-DIFFERENT"})
        res = validate_editor_token(token, secret=_SECRET, expected=exp)
        assert res.ok is False and res.reason == "claim_mismatch"

    def test_readonly_token_rejected_for_write(self):
        """只读令牌（action=editor_read）请求写 → readonly_token（Req 10.8）。"""
        token = _sign(action="editor_read")
        res = validate_editor_token(
            token, secret=_SECRET, expected=_expected(action="editor_read"),
            require_write=True,
        )
        assert res.ok is False and res.reason == "readonly_token"

    def test_write_token_allowed_for_write(self):
        token = _sign(action="editor_write")
        res = validate_editor_token(
            token, secret=_SECRET, expected=_expected(action="editor_write"),
            require_write=True,
        )
        assert res.ok is True

    def test_version_conflict_via_claim_binding(self):
        """token version 与服务端 Current_Version 不一致 → claim_mismatch（版本冲突）。"""
        token = _sign(version="1")
        res = validate_editor_token(token, secret=_SECRET, expected=_expected(version="7"))
        assert res.ok is False and res.reason == "claim_mismatch"

    def test_sign_requires_secret(self):
        with pytest.raises(ValueError):
            sign_editor_token(
                secret="", sub="u", project_id="p", wp_id="w", sheet_name="s",
                wp_code="c", version="1", action="editor_config",
            )

    def test_read_write_action_sets_disjoint(self):
        assert READ_ACTIONS.isdisjoint(WRITE_ACTIONS)


# ===========================================================================
# claims_bound_to（Req 10.4/10.5）
# ===========================================================================
class TestClaimsBinding:
    def test_all_bound_keys_match(self):
        claims = {k: _expected()[k] for k in _expected()}
        assert claims_bound_to(claims, _expected()) is True

    def test_missing_expected_key_skipped(self):
        # expected 不含 version → 不校验 version
        claims = {"project_id": "p1", "wp_id": "w1"}
        assert claims_bound_to(claims, {"project_id": "p1", "wp_id": "w1"}) is True

    def test_none_claim_rejected(self):
        assert claims_bound_to({"wp_id": None}, {"wp_id": "w1"}) is False


# ===========================================================================
# UserCanWrite = gate allow ∩ file state ∩ lock（Design C11）
# ===========================================================================
class TestUserCanWrite:
    @pytest.mark.parametrize(
        "gate,state,lock,expected",
        [
            (True, True, True, True),
            (False, True, True, False),
            (True, False, True, False),
            (True, True, False, False),
            (False, False, False, False),
        ],
    )
    def test_truth_table(self, gate, state, lock, expected):
        assert (
            compute_user_can_write(
                gate_allow=gate, file_state_writable=state, lock_ok=lock
            )
            is expected
        )


# ===========================================================================
# callback/PutFile 落盘前重校验（Req 10.6/10.7/10.8）
# ===========================================================================
class TestCallbackPreconditions:
    def test_all_pass(self):
        ok, reason = verify_callback_preconditions(
            claim_action="callback", server_action="callback",
            claim_version="1", current_version="1",
            gate_allow_write=True, epoch_valid=True,
        )
        assert ok is True and reason is None

    def test_version_conflict(self):
        ok, reason = verify_callback_preconditions(
            claim_action="callback", server_action="callback",
            claim_version="1", current_version="5",
            gate_allow_write=True,
        )
        assert ok is False and reason == "version_conflict"

    def test_readonly_token_rejected(self):
        ok, reason = verify_callback_preconditions(
            claim_action="editor_read", server_action="callback",
            claim_version=None, current_version="1", gate_allow_write=True,
        )
        assert ok is False and reason == "readonly_token"

    def test_action_mismatch(self):
        ok, reason = verify_callback_preconditions(
            claim_action="convert_write", server_action="callback",
            claim_version=None, current_version="1", gate_allow_write=True,
        )
        assert ok is False and reason == "action_denied"

    def test_revoked_session_not_delegated(self):
        ok, reason = verify_callback_preconditions(
            claim_action="callback", server_action="callback",
            claim_version="1", current_version="1", gate_allow_write=False,
        )
        assert ok is False and reason == "not_delegated"

    def test_stale_epoch(self):
        ok, reason = verify_callback_preconditions(
            claim_action="callback", server_action="callback",
            claim_version="1", current_version="1",
            gate_allow_write=True, epoch_valid=False,
        )
        assert ok is False and reason == "epoch_stale"


# ===========================================================================
# PBT：有效令牌恒通过；任一绑定 claim 篡改恒拒绝（Property 13 fail-closed）
# ===========================================================================
class TestEditorTokenPBT:
    @given(
        wp=st.uuids(),
        sheet=st.text(min_size=1, max_size=12).filter(lambda s: s.strip() != ""),
        ver=st.integers(min_value=1, max_value=999),
    )
    @hyp_settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_valid_token_roundtrip(self, wp, sheet, ver):
        token = sign_editor_token(
            secret=_SECRET, sub="u", project_id="p", wp_id=str(wp),
            sheet_name=sheet, wp_code="D2-1", version=str(ver), action="editor_config",
        )
        exp = {
            "project_id": "p", "wp_id": str(wp), "sheet_name": sheet,
            "wp_code": "D2-1", "version": str(ver), "action": "editor_config",
        }
        assert validate_editor_token(token, secret=_SECRET, expected=exp).ok is True

    @given(bad_wp=st.uuids())
    @hyp_settings(deadline=None)  # Task 14: profile-driven max_examples (smoke=5 / correctness>=100)
    def test_tampered_wp_always_rejected(self, bad_wp):
        token = sign_editor_token(
            secret=_SECRET, sub="u", project_id="p", wp_id="real-wp",
            sheet_name="D2A", wp_code="D2-1", version="1", action="editor_config",
        )
        exp = _expected(project_id="p", wp_id=str(bad_wp))
        res = validate_editor_token(token, secret=_SECRET, expected=exp)
        assert res.ok is False and res.reason == "claim_mismatch"


# ===========================================================================
# Gate 集成：signed_token 经统一门全量校验（真实 PostgreSQL）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")
@pytest.mark.asyncio
class TestGateSignedTokenIntegration:
    async def test_signed_token_editor_config_allow(self, session, monkeypatch):
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", _SECRET)
        proj, user, wi, wp = await _lead_scenario(session)
        token = sign_editor_token(
            secret=_SECRET, sub=str(user.id), project_id=str(proj.id),
            wp_id=str(wp.id), sheet_name="D2A", wp_code="D2-1",
            version=str(wp.file_version), action="editor_config",
        )
        req = _BA.wp(
            entrypoint="editor.config", action="editor_config", method="GET",
            wp_id=wp.id, project_id=proj.id, signed_token=token,
        )
        ctx = await resolve_wp_binding_and_access(
            session, user, req, responder=CapturingResponder()
        )
        assert "lead" in ctx.access_kinds

    async def test_signed_token_cross_resource_replay_denied(self, session, monkeypatch):
        """为其它 wp 签发的令牌用于本 wp → token_invalid（跨资源重放）。"""
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", _SECRET)
        proj, user, wi, wp = await _lead_scenario(session)
        token = sign_editor_token(
            secret=_SECRET, sub=str(user.id), project_id=str(proj.id),
            wp_id=str(uuid4()), sheet_name="D2A", wp_code="D2-1",
            version=str(wp.file_version), action="editor_config",
        )
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint="editor.config", action="editor_config", method="GET",
            wp_id=wp.id, project_id=proj.id, signed_token=token,
        )
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        assert resp.last_reason() == DenialReason.token_invalid.value

    async def test_signed_token_expired_denied(self, session, monkeypatch):
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", _SECRET)
        proj, user, wi, wp = await _lead_scenario(session)
        past = int(time.time()) - 10_000
        token = sign_editor_token(
            secret=_SECRET, sub=str(user.id), project_id=str(proj.id),
            wp_id=str(wp.id), sheet_name="D2A", wp_code="D2-1",
            version=str(wp.file_version), action="editor_config",
            lifetime_seconds=1, now=past,
        )
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint="editor.config", action="editor_config", method="GET",
            wp_id=wp.id, project_id=proj.id, signed_token=token,
        )
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        assert resp.last_reason() == DenialReason.token_invalid.value

    async def test_signed_token_secret_missing_denied(self, session, monkeypatch):
        """secret 缺失（JWT disabled bypass）→ signed_token 全量校验 fail-closed（Req 10.9）。"""
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")
        proj, user, wi, wp = await _lead_scenario(session)
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint="editor.config", action="editor_config", method="GET",
            wp_id=wp.id, project_id=proj.id, signed_token="any.token.value",
        )
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        assert resp.last_reason() == DenialReason.token_invalid.value

    async def test_signed_token_version_conflict_denied(self, session, monkeypatch):
        """token version 与 Current_Version 不一致 → token_invalid（版本冲突）。"""
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", _SECRET)
        proj, user, wi, wp = await _lead_scenario(session)
        token = sign_editor_token(
            secret=_SECRET, sub=str(user.id), project_id=str(proj.id),
            wp_id=str(wp.id), sheet_name="D2A", wp_code="D2-1",
            version=str(wp.file_version + 99), action="editor_config",
        )
        resp = CapturingResponder()
        req = _BA.wp(
            entrypoint="editor.config", action="editor_config", method="GET",
            wp_id=wp.id, project_id=proj.id, signed_token=token,
        )
        with pytest.raises(ExternalNotFound):
            await resolve_wp_binding_and_access(session, user, req, responder=resp)
        assert resp.last_reason() == DenialReason.token_invalid.value
