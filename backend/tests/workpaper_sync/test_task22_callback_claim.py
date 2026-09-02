# -*- coding: utf-8 -*-
"""Task 22 离线守卫：route claim、流式下载安全、delivery 去重、归组决策、隔离与轨迹。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 22
Requirements: 4.3, 4.9, 4.10, 5.1, 5.2, 5.3, 5.6, 5.7, 5.12, 10.2, 10.3, 10.7, 10.8, 10.9
Properties: P16 / P17 / P18 / P19 / P44 / P63 / P64

═══ 本文件与 `_pg.py` 的分工 ═══

这里只放**不需要数据库**就能真执行的判据：纯函数、策略构造、异常分支、真值表结构。
凡涉及"归属约束是否真被库拒绝""并发下是否恰一个 primary"的，一律在
`test_task22_callback_claim_pg.py` 里对真实 PostgreSQL 跑 —— 那些判据 mock 不出来。

═══ 为什么下载判据用注入 transport 而不是真网络 ═══

被测的东西是 **allowlist / 逐 IP 复核 / 3xx 拒绝 / 流式计数**，它们全在
`callback_download` 模块内；transport 只提供字节与状态码。所以这不是"用 mock 测判据"，
而是"用替身提供被测判据的输入"。另有一条独立判据（:func:`test_production_transport_...`）
钉住生产 transport 的构造参数，防止替身把生产配置的漂移遮住。
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import os
import re
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.callback_delivery import (  # noqa: E402
    DELIVERY_OWNERSHIP_TRUTH_TABLE,
    QUARANTINE_ALLOWED_OPERATIONS,
    QUARANTINE_FORBIDDEN_OPERATIONS,
    CallbackActionNotWritableError,
    CallbackDeliveryService,
    CallbackPayload,
    CallbackPayloadShapeError,
    CallbackStage,
    CallbackStageJournal,
    CallbackStageOrderError,
    CallbackStatusUnsupportedError,
    ContributorAttributionUnsafeError,
    CorrelationFamily,
    CorrelationMode,
    CorrelationPlan,
    OwnershipVerdict,
    QuarantineOperationForbiddenError,
    assert_incoming_admissible_for_application,
    assert_payload_matches_status_rule,
    assert_quarantine_operation_allowed,
    build_delivery_key,
    classify_delivery_ownership,
    compute_delivery_discriminator,
    correlation_family,
    plan_correlation,
)
from app.services.workpaper_sync.callback_download import (  # noqa: E402
    DEFAULT_OO_PATH_PREFIXES,
    METADATA_ADDRESSES,
    AllowlistEntry,
    DownloadAddressRejectedError,
    DownloadHttpStatusError,
    DownloadMetrics,
    DownloadPathRejectedError,
    DownloadPolicyConfigError,
    DownloadRedirectRefusedError,
    DownloadRequest,
    DownloadResolutionError,
    DownloadSizeExceededError,
    DownloadUrlNotAllowlistedError,
    assert_address_allowed,
    assert_transport_is_leak_free,
    assert_url_allowlisted,
    build_download_policy,
    build_httpx_transport,
    resolve_and_verify,
    stream_download,
)
from app.services.workpaper_sync.callback_route import (  # noqa: E402  # isort: skip
    CallbackSecretMissingError,
    CallbackTokenExpiredError,
)
from app.services.workpaper_sync.callback_route import (  # noqa: E402
    URL_BOUND_PARAMS,
    CallbackAuthorshipMisuseError,
    CallbackClaimSchemaError,
    CallbackClaimVersionError,
    CallbackDocKeyMismatchError,
    CallbackGenerationStaleError,
    CallbackRouteClaim,
    CallbackTokenMissingError,
    CallbackTokenSignatureError,
    CallbackUrlBindingError,
    RoomRouteFacts,
    build_callback_url,
    parse_callback_claims,
    sign_callback_route_token,
    verify_callback_route,
)
from app.services.workpaper_sync.models import (  # noqa: E402
    ArtifactState,
    ContributorConfidence,
    CorrelationResult,
    DeliveryOwnershipError,
    DeliveryState,
    IncomingNotDurableError,
    QuarantinedIncomingError,
    RecoveryReason,
)
from app.services.workpaper_sync.oo_contract import load_callback_contract  # noqa: E402
from app.services.workpaper_sync.rooms import derive_doc_key  # noqa: E402

_MIGRATION = (
    _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
)
SECRET = "task22-callback-route-secret"
CONTRACT = load_callback_contract()
WP_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ENTRY = "xlsx/gt-d2-accounts-receivable"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 夹具：room 事实 / claim / URL
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def room() -> RoomRouteFacts:
    room_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    return RoomRouteFacts(
        room_id=room_id,
        generation=3,
        doc_key=derive_doc_key(wp_id=WP_ID, entry_id=ENTRY, generation=3),
        wp_id=WP_ID,
        entry_id=ENTRY,
        write_fence_epoch=7,
        accepts_callback=True,
    )


def _credential(room: RoomRouteFacts) -> uuid.UUID:
    from app.services.workpaper_sync.rooms import mint_route_credential

    return mint_route_credential(
        room_id=room.room_id, generation=room.generation, doc_key=room.doc_key
    ).credential_id


def _token(room: RoomRouteFacts, **over: Any) -> str:
    kwargs: dict[str, Any] = dict(
        secret=SECRET,
        room_id=room.room_id,
        generation=room.generation,
        doc_key=room.doc_key,
        route_credential_id=_credential(room),
        action="callback_write",
        ttl_seconds=300,
    )
    kwargs.update(over)
    return sign_callback_route_token(**kwargs)


def _url(room: RoomRouteFacts, **over: Any) -> str:
    kwargs: dict[str, Any] = dict(
        base_url="https://platform.example.test",
        path="/api/wp-sync/callback",
        room_id=room.room_id,
        generation=room.generation,
        doc_key=room.doc_key,
        route_credential_id=_credential(room),
    )
    kwargs.update(over)
    return build_callback_url(**kwargs)


def _verify(room: RoomRouteFacts, *, token: str | None = None, **over: Any) -> CallbackRouteClaim:
    kwargs: dict[str, Any] = dict(
        authorization_header=f"Bearer {token or _token(room)}",
        callback_url=_url(room),
        payload_doc_key=room.doc_key,
        room=room,
        secret=SECRET,
        contract=CONTRACT,
    )
    kwargs.update(over)
    return verify_callback_route(**kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Property 16：claim version 真校验（下载前）
# ═══════════════════════════════════════════════════════════════════════════


def test_missing_claim_version_rejected_before_download(room: RoomRouteFacts) -> None:
    """`cbv` 缺失 ⇒ 拒（Requirement 5.2 禁止 `claim_version=None` 绕过）。"""
    from jose import jwt

    payload = {
        "act": "callback_write",
        "room_id": str(room.room_id),
        "generation": room.generation,
        "doc_key": room.doc_key,
        "route_credential_id": str(_credential(room)),
        "callback_token_id": str(uuid.uuid4()),
        "iat": 1,
        "exp": 2**31,
        "iss": CONTRACT.jwt.claim_constants["iss"],
        "aud": CONTRACT.jwt.claim_constants["aud"],
    }
    token = jwt.encode(payload, SECRET, algorithm=CONTRACT.jwt.algorithm)
    with pytest.raises(CallbackClaimVersionError) as exc:
        parse_callback_claims(token, secret=SECRET, contract=CONTRACT)
    assert "cbv" in str(exc.value)


@pytest.mark.parametrize("bad", ["1", 1.0, True, None, [1]])
def test_claim_version_refuses_coercion(room: RoomRouteFacts, bad: Any) -> None:
    """`"1"` / `1.0` / `True` 都不是严格 int ⇒ 拒；**不得**隐式转换成已知版本。"""
    from jose import jwt

    payload = {
        "cbv": bad,
        "act": "callback_write",
        "room_id": str(room.room_id),
        "generation": room.generation,
        "doc_key": room.doc_key,
        "route_credential_id": str(_credential(room)),
        "callback_token_id": str(uuid.uuid4()),
        "iat": 1,
        "exp": 2**31,
        "iss": CONTRACT.jwt.claim_constants["iss"],
        "aud": CONTRACT.jwt.claim_constants["aud"],
    }
    token = jwt.encode(payload, SECRET, algorithm=CONTRACT.jwt.algorithm)
    with pytest.raises(CallbackClaimVersionError):
        parse_callback_claims(token, secret=SECRET, contract=CONTRACT)


def test_unknown_claim_version_rejected(room: RoomRouteFacts) -> None:
    """已知形状但版本号不是本部署支持的 ⇒ 拒。"""
    from jose import jwt

    payload = {
        "cbv": CONTRACT.jwt.claim_schema_version + 41,
        "act": "callback_write",
        "room_id": str(room.room_id),
        "generation": room.generation,
        "doc_key": room.doc_key,
        "route_credential_id": str(_credential(room)),
        "callback_token_id": str(uuid.uuid4()),
        "iat": 1,
        "exp": 2**31,
        "iss": CONTRACT.jwt.claim_constants["iss"],
        "aud": CONTRACT.jwt.claim_constants["aud"],
    }
    token = jwt.encode(payload, SECRET, algorithm=CONTRACT.jwt.algorithm)
    with pytest.raises(CallbackClaimVersionError):
        parse_callback_claims(token, secret=SECRET, contract=CONTRACT)


def test_claim_version_error_is_distinct_from_signature_error(room: RoomRouteFacts) -> None:
    """版本判据与签名判据必须是**不同类型**。

    合并成一个类型时，"删掉版本判据"的变异会被签名分支遮蔽 —— 伪造 token 反正也过不了
    签名，于是守卫恒绿。这条判据同时证明两个分支都可达。
    """
    with pytest.raises(CallbackTokenSignatureError):
        parse_callback_claims(
            _token(room), secret="another-secret-entirely", contract=CONTRACT
        )
    assert not issubclass(CallbackClaimVersionError, CallbackTokenSignatureError)
    assert not issubclass(CallbackTokenSignatureError, CallbackClaimVersionError)


def test_missing_secret_fails_closed(room: RoomRouteFacts) -> None:
    """未配置 secret 时**不放行**（legacy `if not JWT_SECRET: return True` 的反面）。

    🔴 必须断言**专属**类型。断成 `CallbackTokenSignatureError` 时，删掉这道门后
    `jwt.decode(token, "")` 照样因签名不过抛同一类型 ⇒ 判据恒绿（M04 首轮实测 GREEN）。
    再加一条正交断言：该类型与签名类型互不为子类，否则 `pytest.raises` 会被继承关系放过。
    """
    with pytest.raises(CallbackSecretMissingError):
        parse_callback_claims(_token(room), secret="", contract=CONTRACT)
    assert not issubclass(CallbackSecretMissingError, CallbackTokenSignatureError)
    assert not issubclass(CallbackTokenSignatureError, CallbackSecretMissingError)


def test_missing_authorization_header_rejected(room: RoomRouteFacts) -> None:
    with pytest.raises(CallbackTokenMissingError):
        _verify(room, authorization_header=None)
    with pytest.raises(CallbackTokenMissingError):
        _verify(room, authorization_header="Bearer   ")


def test_action_enum_enforced(room: RoomRouteFacts) -> None:
    with pytest.raises(CallbackClaimSchemaError):
        sign_callback_route_token(
            secret=SECRET,
            room_id=room.room_id,
            generation=room.generation,
            doc_key=room.doc_key,
            route_credential_id=_credential(room),
            action="callback_do_whatever",
            ttl_seconds=60,
        )


def test_expired_token_rejected(room: RoomRouteFacts) -> None:
    """过期 token 必须被拒。jose 侧与平台显式判据**各测一次**，且类型不同。"""
    stale = _token(room, ttl_seconds=1, issued_at=1)
    # jose 自己就会拦住这种（iat/exp 都在很久以前）
    with pytest.raises(CallbackTokenSignatureError):
        _verify(room, token=stale, now_epoch=10**9)


def test_explicit_clock_check_rejects_token_that_jose_accepts(
    room: RoomRouteFacts,
) -> None:
    """显式时钟判据必须在 jose **不**报错的情形下独立生效。

    🔴 这条是 M10 判 GREEN 之后补的。原来只有上面那条：token 的 `exp` 早已过期，
    于是 jose 先抛，显式判据被完全遮蔽 —— 把它删掉守卫照样绿。可显式判据存在的全部
    理由就是「jose 允许 leeway、`options` 被改成 `verify_exp=False` 会静默失效」，
    也就是说它必须能在 jose 放行时自己拦住。构造方式：签一个 jose 眼里**仍然有效**
    的 token（exp 在真实未来），再把平台参考时钟推到 exp 之后。
    """
    import time

    now = int(time.time())
    fresh = _token(room, ttl_seconds=3600, issued_at=now)
    # 前置：jose 放行（不给 now_epoch 时用真实时钟，必须能通过）
    assert _verify(room, token=fresh).expires_at == now + 3600
    # 平台参考时钟越过 exp ⇒ 只有显式判据能拦住
    with pytest.raises(CallbackTokenExpiredError):
        _verify(room, token=fresh, now_epoch=now + 7200)


# ═══════════════════════════════════════════════════════════════════════════
# 2. URL / room 绑定（逐项）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("param", URL_BOUND_PARAMS)
def test_each_url_bound_param_is_checked(room: RoomRouteFacts, param: str) -> None:
    """四项绑定**逐项**校验：改任一项都必须拒。

    逐项参数化而不是只测一项：只绑 room 时 generation 旋转后旧 URL 仍合法，AC 2.8 的
    supersede 就形同虚设。
    """
    tampered = {
        "room_id": uuid.uuid4(),
        "generation": room.generation + 1,
        "doc_key": derive_doc_key(wp_id=WP_ID, entry_id=ENTRY, generation=99),
        "route_credential_id": uuid.uuid4(),
    }[param]
    with pytest.raises(CallbackUrlBindingError):
        _verify(room, callback_url=_url(room, **{param: tampered}))


def test_payload_key_must_equal_claim_doc_key(room: RoomRouteFacts) -> None:
    with pytest.raises(CallbackDocKeyMismatchError):
        _verify(room, payload_doc_key="some-other-key")
    # `None` 不得被 `str(None) == "None"` 蒙过去
    with pytest.raises(CallbackDocKeyMismatchError):
        _verify(room, payload_doc_key=None)


def test_doc_key_must_derive_from_room_identity(room: RoomRouteFacts) -> None:
    """doc_key 必须由 room 的 (wp_id, entry_id) 派生 —— 跨底稿 key 不得进入本 room。"""
    foreign = derive_doc_key(wp_id=uuid.uuid4(), entry_id=ENTRY, generation=3)
    facts = RoomRouteFacts(
        room_id=room.room_id,
        generation=room.generation,
        doc_key=foreign,
        wp_id=room.wp_id,
        entry_id=room.entry_id,
        write_fence_epoch=room.write_fence_epoch,
        accepts_callback=True,
    )
    with pytest.raises(CallbackDocKeyMismatchError):
        verify_callback_route(
            authorization_header=f"Bearer {_token(facts)}",
            callback_url=_url(facts),
            payload_doc_key=foreign,
            room=facts,
            secret=SECRET,
            contract=CONTRACT,
        )


def test_superseded_room_and_stale_fence_rejected(room: RoomRouteFacts) -> None:
    dead = RoomRouteFacts(
        room_id=room.room_id,
        generation=room.generation,
        doc_key=room.doc_key,
        wp_id=room.wp_id,
        entry_id=room.entry_id,
        write_fence_epoch=room.write_fence_epoch,
        accepts_callback=False,
    )
    # `_verify(dead)` 已经把 `dead` 当 room 传进去了；再写 `room=dead` 会撞
    # `_verify(room, *, **over)` 的第一个位置参数 ⇒ TypeError，测的就不再是拒绝分支。
    with pytest.raises(CallbackGenerationStaleError):
        _verify(dead)
    with pytest.raises(CallbackGenerationStaleError):
        _verify(room, expected_write_fence_epoch=room.write_fence_epoch + 1)


def test_route_claim_carries_no_authorship(room: RoomRouteFacts) -> None:
    """route claim 既不是作者也不是授权依据（Task 4 §3 / Requirement 10.2 / P63）。"""
    claim = _verify(room, token=_token(room, audit_participant_hint=uuid.uuid4()))
    assert claim.audit_participant_hint is not None
    with pytest.raises(CallbackAuthorshipMisuseError):
        claim.assert_not_authorship(where="test")
    fields = set(CallbackRouteClaim.__dataclass_fields__)
    assert not {"user_id", "author_participant_id", "participant_id"} & fields
    params = set(inspect.signature(verify_callback_route).parameters)
    assert not {"participant_id", "user_id", "user", "actor"} & params


# ═══════════════════════════════════════════════════════════════════════════
# 3. Property 17：下载安全（全部在 durable 之前）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def policy() -> Any:
    return build_download_policy(
        onlyoffice_url="http://localhost:8080", contract=CONTRACT
    )


def test_empty_allowlist_refuses_instead_of_falling_back() -> None:
    """`ONLYOFFICE_URL` 为空时**不得**回退到"host 由 payload 决定"。"""
    with pytest.raises(DownloadPolicyConfigError):
        build_download_policy(onlyoffice_url=None, contract=CONTRACT)
    with pytest.raises(DownloadPolicyConfigError):
        build_download_policy(onlyoffice_url="   ", contract=CONTRACT)


def test_host_not_allowlisted_rejected(policy: Any) -> None:
    with pytest.raises(DownloadUrlNotAllowlistedError):
        assert_url_allowlisted("http://evil.example.com/cache/files/x.xlsx", policy=policy)
    with pytest.raises(DownloadUrlNotAllowlistedError):
        assert_url_allowlisted("http://localhost:9999/cache/files/x.xlsx", policy=policy)
    with pytest.raises(DownloadUrlNotAllowlistedError):
        assert_url_allowlisted("file:///etc/passwd", policy=policy)


@pytest.mark.parametrize(
    "path",
    [
        "/cache/files/../../etc/passwd",
        "/cache/files/a\\b.xlsx",
        "/admin/settings",
        "/cache//files/x.xlsx",
    ],
)
def test_path_gate_is_independent_of_host_gate(policy: Any, path: str) -> None:
    """path 判据与 host 判据**分型**。

    Task 4 实测的生产 gap 恰恰是"netloc 被换成 ONLYOFFICE_URL 但 path 原样保留"，
    所以 host 合法 + path 恶意必须由 :class:`DownloadPathRejectedError` 单独拦下。
    """
    with pytest.raises(DownloadPathRejectedError):
        assert_url_allowlisted(f"http://localhost:8080{path}", policy=policy)
    assert not issubclass(DownloadPathRejectedError, DownloadUrlNotAllowlistedError)


@pytest.mark.parametrize("addr", sorted(METADATA_ADDRESSES))
def test_metadata_addresses_rejected_even_when_private_allowed(addr: str) -> None:
    """元数据端点在**任何** allowlist 条目下都拒 —— 它是特权凭证端点，不是"私网的一种"。"""
    permissive = AllowlistEntry(
        scheme="http", host="localhost", port=8080, allow_private_ip=True
    )
    with pytest.raises(DownloadAddressRejectedError):
        assert_address_allowed(addr, entry=permissive)


def test_dns_rebinding_blocked_by_post_resolve_recheck(policy: Any) -> None:
    """解析后逐 IP 复核：公网 host 解析到私网 ⇒ 拒（DNS rebinding 的典型形态）。"""
    remote = build_download_policy(
        onlyoffice_url="https://oo.example.test:443", contract=CONTRACT
    )
    with pytest.raises(DownloadAddressRejectedError):
        resolve_and_verify(
            "https://oo.example.test/cache/files/x.xlsx",
            policy=remote,
            resolver=lambda host, port: ["10.1.2.3"],
        )
    with pytest.raises(DownloadResolutionError):
        resolve_and_verify(
            "http://localhost:8080/cache/files/x.xlsx",
            policy=policy,
            resolver=lambda host, port: [],
        )


def test_resolved_ip_is_pinned_for_connection(policy: Any) -> None:
    """已验证 IP 必须固定给连接使用，连接阶段不得二次解析。"""
    target = resolve_and_verify(
        "http://localhost:8080/cache/files/x.xlsx",
        policy=policy,
        resolver=lambda host, port: ["127.0.0.1"],
    )
    assert target.pinned_address == "127.0.0.1"
    assert "127.0.0.1" in target.pinned_url
    assert target.host_header.startswith("localhost")


class _FakeResponse:
    def __init__(self, status: int, chunks: list[bytes], headers: dict[str, str] | None = None):
        self.status_code = status
        self.headers = headers or {"content-type": "application/octet-stream"}
        self._chunks = chunks
        self.iterated = 0

    def iter_bytes(self, chunk_size: int) -> Iterator[bytes]:
        for c in self._chunks:
            self.iterated += 1
            yield c


class _FakeTransport:
    """可编程 transport。`used` 让"根本没被调用"成为可断言事实。"""

    def __init__(self, response: _FakeResponse):
        self.response = response
        self.used = 0
        self.last_request: DownloadRequest | None = None

    @contextmanager
    def stream(self, request: DownloadRequest) -> Iterator[_FakeResponse]:
        self.used += 1
        self.last_request = request
        yield self.response


def _target(policy: Any) -> Any:
    return resolve_and_verify(
        "http://localhost:8080/cache/files/x.xlsx",
        policy=policy,
        resolver=lambda host, port: ["127.0.0.1"],
    )


def test_redirect_refused_and_body_not_consumed(policy: Any) -> None:
    """3xx 一律拒，且**不得**把 3xx body 当文件写盘。"""
    resp = _FakeResponse(302, [b"<html>redirect</html>"], {"location": "http://evil/x"})
    transport = _FakeTransport(resp)
    with pytest.raises(DownloadRedirectRefusedError):
        list(stream_download(_target(policy), policy=policy, transport=transport))
    assert resp.iterated == 0, "3xx 时不得读取 body"


def test_non_2xx_rejected(policy: Any) -> None:
    with pytest.raises(DownloadHttpStatusError):
        list(
            stream_download(
                _target(policy), policy=policy, transport=_FakeTransport(_FakeResponse(500, [b"x"]))
            )
        )


def test_size_cap_aborts_mid_stream(policy: Any) -> None:
    """超限**立即中止**，不整包入内存。

    判据落在"已产出的块数远小于总块数"：整包读取的实现会先把所有块拉完再判断，
    于是 `iterated` 等于块总数。
    """
    chunk = b"\0" * (1024 * 1024)
    total_chunks = policy.size_cap_bytes // len(chunk) + 5
    resp = _FakeResponse(200, [chunk] * total_chunks)
    metrics = DownloadMetrics()
    transport = _FakeTransport(resp)
    produced = 0
    with pytest.raises(DownloadSizeExceededError):
        for _ in stream_download(
            _target(policy), policy=policy, transport=transport, metrics=metrics
        ):
            produced += 1
    assert resp.iterated < total_chunks
    assert metrics.bytes_read > policy.size_cap_bytes


def test_download_carries_no_platform_credential(policy: Any) -> None:
    """下载请求不得带 Authorization/Cookie（Requirement 10.7）。"""
    transport = _FakeTransport(_FakeResponse(200, [b"PK\x03\x04payload"]))
    list(stream_download(_target(policy), policy=policy, transport=transport))
    assert transport.last_request is not None
    lowered = {k.lower() for k in transport.last_request.headers}
    assert not lowered & {"authorization", "cookie", "x-api-key"}


def test_production_transport_is_proxy_and_redirect_free() -> None:
    """生产 transport 必须显式关 `trust_env` 并禁重定向。"""
    assert_transport_is_leak_free(build_httpx_transport())

    class _Leaky:
        def stream(self, request: DownloadRequest) -> Any:  # pragma: no cover - 只测拒绝
            raise AssertionError

    with pytest.raises(Exception):
        assert_transport_is_leak_free(_Leaky())


def test_contract_and_capacity_budget_locked_together() -> None:
    """契约上限与容量预算必须锁死，否则下载门与解压门各按一个上限工作。

    🔴 两个方向都要断言。只留「预算侧漂移必抛」那半段时，**契约侧**被改回漂移值
    （首版的 200 MiB）不会有任何判据发现：`build_download_policy` 会在所有用到
    `policy` fixture 的用例里抛 —— 而那些用例变成 pytest **ERROR** 而不是 FAILED，
    失败集合差集看不见 ERROR ⇒ 定向变异被判 GREEN（M20 首轮实测就是这样）。
    因此正向断言必须独立存在，且不依赖 `policy` fixture。
    """
    from dataclasses import replace

    from app.services.workpaper_sync.limits import load_limits

    lim = load_limits()
    assert CONTRACT.download.streaming_size_cap_bytes == lim.max_compressed_bytes, (
        "契约 streaming_size_cap_bytes 必须逐字节等于 Requirement 14.11 的 "
        f"max_compressed_bytes；实得契约 {CONTRACT.download.streaming_size_cap_bytes} "
        f"vs 预算 {lim.max_compressed_bytes}"
    )
    assert lim.max_compressed_bytes == 50 * 1024 * 1024

    drifted = replace(lim, max_compressed_bytes=lim.max_compressed_bytes + 1)
    with pytest.raises(DownloadPolicyConfigError):
        build_download_policy(
            onlyoffice_url="http://localhost:8080", contract=CONTRACT, limits=drifted
        )


def test_default_path_prefixes_non_empty() -> None:
    """前缀清单不得为空 —— 空清单会让 path 判据恒真。"""
    assert DEFAULT_OO_PATH_PREFIXES
    with pytest.raises(DownloadPolicyConfigError):
        build_download_policy(
            onlyoffice_url="http://localhost:8080", path_prefixes=(), contract=CONTRACT
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. payload 投影与真值表 presence
# ═══════════════════════════════════════════════════════════════════════════


def _body(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "key": "docKey",
        "status": 6,
        "url": "http://localhost:8080/cache/files/data/x_1/output.xlsx/output.xlsx?md5=a",
        "userdata": str(uuid.uuid4()),
        "users": ["bob"],
        "actions": [{"type": 0, "userid": "bob"}],
        "filetype": "xlsx",
        "history": {"changes": [{"user": {"id": "alice"}}, {"user": {"id": "bob"}}]},
        "token": "oo-self-signed-jwt",
    }
    body.update(over)
    return body


def test_status_coercion_refused() -> None:
    """`"6"` 不得被 `int()` 强转成 6（契约 fail_visible）。"""
    with pytest.raises(CallbackStatusUnsupportedError):
        CallbackPayload.from_mapping(_body(status="6"), contract=CONTRACT)
    with pytest.raises(CallbackStatusUnsupportedError):
        CallbackPayload.from_mapping(_body(status=99), contract=CONTRACT)
    with pytest.raises(CallbackStatusUnsupportedError):
        CallbackPayload.from_mapping(_body(status=None), contract=CONTRACT)


def test_users_and_contributors_are_separate_projections() -> None:
    """`users`（最后编辑者）与 `history.changes`（全体贡献者）必须分开投影。

    Task 4 实证：status 6 的 `users` 只有 `['bob']`，而 artifact 同时含 alice 的编辑。
    把两者混成一个字段就会把"谁写的"记错。
    """
    payload = CallbackPayload.from_mapping(_body(), contract=CONTRACT)
    assert payload.users == ("bob",)
    assert set(payload.contributors) == {"alice", "bob"}
    assert payload.users_digest() != payload.contributor_digest()


def test_contributor_confidence_never_exact() -> None:
    """OO 派生 contributor 永远不是 `exact`（drop 过的用户仍在 history.changes 里）。"""
    svc = CallbackDeliveryService.__new__(CallbackDeliveryService)
    for body in (_body(), _body(history={}, users=["bob"]), _body(history={}, users=[])):
        payload = CallbackPayload.from_mapping(body, contract=CONTRACT)
        assert svc.contributor_confidence_of(payload) is not ContributorConfidence.exact


def test_contributor_attribution_refuses_when_no_signal_at_all() -> None:
    """既无 `users` 也无 `history.changes` 且未声明 notmodified ⇒ 归属无法判定，必须拒。

    Requirement 10.3 / Property 44：这种 callback 不得产生 content application，
    要由上层隔离/旋转 generation。三个分支都要驱动，否则「拒绝」那一支是死代码：

    * 有 contributor 信号 ⇒ 放行；
    * 无信号但 `notmodified=true` ⇒ 放行（OO 明说内容没变）；
    * 无信号且声称有内容 ⇒ **拒**。
    """
    svc = CallbackDeliveryService.__new__(CallbackDeliveryService)
    blind = CallbackPayload.from_mapping(
        _body(users=[], history={"changes": []}), contract=CONTRACT
    )
    with pytest.raises(ContributorAttributionUnsafeError):
        svc._assert_contributor_attribution_safe(blind)
    assert svc.contributor_confidence_of(blind) is ContributorConfidence.unknown

    quiet = CallbackPayload.from_mapping(
        _body(users=[], history={"changes": []}, notmodified=True), contract=CONTRACT
    )
    svc._assert_contributor_attribution_safe(quiet)  # 不得抛

    signalled = CallbackPayload.from_mapping(_body(), contract=CONTRACT)
    svc._assert_contributor_attribution_safe(signalled)  # 不得抛
    assert svc.contributor_confidence_of(signalled) is ContributorConfidence.aggregate


def test_payload_presence_must_match_truth_table() -> None:
    """status 声明 url_present=always/never 时，payload 形态必须一致。"""
    rule6 = CONTRACT.status_rule(6)
    with pytest.raises(CallbackPayloadShapeError):
        assert_payload_matches_status_rule(
            CallbackPayload.from_mapping(_body(url=None), contract=CONTRACT), rule6
        )
    rule1 = CONTRACT.status_rule(1)
    with pytest.raises(CallbackPayloadShapeError):
        assert_payload_matches_status_rule(
            CallbackPayload.from_mapping(_body(status=1), contract=CONTRACT), rule1
        )
    with pytest.raises(CallbackPayloadShapeError):
        assert_payload_matches_status_rule(
            CallbackPayload.from_mapping(
                _body(status=1, url=None, userdata=str(uuid.uuid4())), contract=CONTRACT
            ),
            rule1,
        )


def test_non_uuid_userdata_degrades_to_absent() -> None:
    """非 UUID `userdata` 按"无 userdata"处理，而不是让 durable 内容无法恢复。"""
    payload = CallbackPayload.from_mapping(_body(userdata="req-001-by-alice"), contract=CONTRACT)
    assert payload.userdata == "req-001-by-alice"
    assert payload.request_id is None


# ═══════════════════════════════════════════════════════════════════════════
# 5. delivery 去重
# ═══════════════════════════════════════════════════════════════════════════


def test_network_retry_of_same_delivery_dedupes(room: RoomRouteFacts) -> None:
    """同一投递重发（含 OO 重签 body token）必须落同一 delivery row。

    🔴 必须由**同一个 body dict** 派生两份 payload，只改 `token`。`_body()` 每次调用都
    生成新的随机 `userdata`，写成 `_body()` 与 `_body(token=...)` 就同时变了两个成分，
    于是这条断言测的是「userdata 变了 discriminator 会变」（那是 T4 §7 要求的行为），
    与「重签 token 不影响去重」毫无关系 —— 判据被自己的 fixture 遮蔽。
    """
    base = _body()
    a = CallbackPayload.from_mapping(base, contract=CONTRACT)
    b = CallbackPayload.from_mapping({**base, "token": "oo-resigned-jwt"}, contract=CONTRACT)
    assert a.userdata == b.userdata, "前置：两份 payload 只许在 token 上不同"
    assert compute_delivery_discriminator(a) == compute_delivery_discriminator(b)
    assert build_delivery_key(
        room_id=room.room_id, generation=room.generation, payload=a
    ) == build_delivery_key(room_id=room.room_id, generation=room.generation, payload=b)


def test_distinct_deliveries_get_distinct_keys(room: RoomRouteFacts) -> None:
    """Task 4 实测：同 userdata 连发两次 forcesave 的 url 与字节都不同 ⇒ 必须两行。"""
    ud = str(uuid.uuid4())
    first = CallbackPayload.from_mapping(
        _body(userdata=ud, url="http://localhost:8080/cache/files/data/x_6785/o.xlsx?md5=a"),
        contract=CONTRACT,
    )
    second = CallbackPayload.from_mapping(
        _body(userdata=ud, url="http://localhost:8080/cache/files/data/x_6104/o.xlsx?md5=b"),
        contract=CONTRACT,
    )
    keys = {
        build_delivery_key(room_id=room.room_id, generation=room.generation, payload=p)
        for p in (first, second)
    }
    assert len(keys) == 2


def test_discriminator_separates_same_url_with_different_body() -> None:
    """url 与 userdata 都复用、只有 body 其余字段变化 ⇒ 仍须是两条 delivery。

    这条专为隔离 `canonical_digest` 那一项而写。`test_distinct_deliveries_get_distinct_keys`
    改的是 `url`，所以即使 digest 成分被削空，`url` 那一项也照样把两者分开 ⇒ 定向变异
    判 GREEN（M24 首轮实测）。一个场景只许违反一个谓词，故这里 url/userdata 逐字不变。
    """
    base = _body()
    a = CallbackPayload.from_mapping(base, contract=CONTRACT)
    b = CallbackPayload.from_mapping({**base, "notmodified": True}, contract=CONTRACT)
    assert a.url == b.url and a.userdata == b.userdata, "前置：只许 body 其余字段不同"
    assert compute_delivery_discriminator(a) != compute_delivery_discriminator(b)


def test_build_delivery_key_wires_the_payload_status_through(
    room: RoomRouteFacts,
) -> None:
    """`build_delivery_key` 必须把 **payload 自己的 status** 传给 key 函数。

    🔴 判据形态是**接线等值**而不是「值会不会变」。原因是实测出来的：
    `canonical_digest()` 摘的是整个 raw body，而 `status` 就在 body 里，所以任何
    「只改 status」的场景都会被 digest 那一项分开 ⇒ 把外层 `callback_status=` 削成常量
    在**值**层面完全不可观测（M25 首轮判 GREEN 正是如此）。

    外层那一项是纵深防御：`_DISCRIMINATOR_EXCLUDED_FIELDS` 将来若扩容到 `status`，
    delivery key 仍必须按 status 分行。要锁住它，只能断言接线：`build_delivery_key`
    的结果必须逐字节等于「拿 payload.status 显式调用 `compute_delivery_key`」。
    传常量 0 时这条等值立刻破。
    """
    from app.services.workpaper_sync.models import compute_delivery_key

    payload = CallbackPayload.from_mapping(_body(), contract=CONTRACT)
    expected = compute_delivery_key(
        room_id=room.room_id,
        generation=room.generation,
        callback_status=payload.status,
        discriminator=compute_delivery_discriminator(payload),
    )
    assert (
        build_delivery_key(
            room_id=room.room_id, generation=room.generation, payload=payload
        )
        == expected
    )
    # 同时证明 key 函数**真的**按 status 分行（否则上面那条等值是恒真的重言式）
    other = compute_delivery_key(
        room_id=room.room_id,
        generation=room.generation,
        callback_status=payload.status + 1,
        discriminator=compute_delivery_discriminator(payload),
    )
    assert other != expected


def test_delivery_key_includes_status_and_scope(room: RoomRouteFacts) -> None:
    """delivery key 含 status/room/generation：status 6 与 2 各自成行。"""
    p6 = CallbackPayload.from_mapping(_body(), contract=CONTRACT)
    p2 = CallbackPayload.from_mapping(_body(status=2, userdata=None), contract=CONTRACT)
    k6 = build_delivery_key(room_id=room.room_id, generation=room.generation, payload=p6)
    k2 = build_delivery_key(room_id=room.room_id, generation=room.generation, payload=p2)
    other_gen = build_delivery_key(
        room_id=room.room_id, generation=room.generation + 1, payload=p6
    )
    other_room = build_delivery_key(
        room_id=uuid.uuid4(), generation=room.generation, payload=p6
    )
    assert len({k6, k2, other_gen, other_room}) == 4


def test_delivery_discriminator_excludes_credentials() -> None:
    """discriminator 不得包含 token（凭证不落库，且重签不应破坏去重）。"""
    payload = CallbackPayload.from_mapping(_body(), contract=CONTRACT)
    assert "oo-self-signed-jwt" not in str(payload.canonical_digest())
    import json

    assert "token" not in json.dumps(
        {k: v for k, v in payload.raw.items() if k != "token"}
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. 归属真值表（结构 + 与 V151 双向锁死）
# ═══════════════════════════════════════════════════════════════════════════


def _row_kwargs(row: Any) -> dict[str, Any]:
    cr = {
        CorrelationFamily.absent: None,
        CorrelationFamily.correlated: CorrelationResult.request,
        CorrelationFamily.unresolved: CorrelationResult.unmatched,
    }[row.family]
    return dict(
        state=row.state,
        durable_at_is_set=row.durable_at_is_set,
        application_id=uuid.uuid4() if row.has_application else None,
        callback_recovery_case_id=uuid.uuid4() if row.has_recovery else None,
        forcesave_request_id=uuid.uuid4() if row.has_request else None,
        incoming_artifact_id=uuid.uuid4() if row.has_incoming else None,
        correlation_result=cr,
    )


def test_every_truth_table_row_is_individually_reachable() -> None:
    """每一行都必须能被谓词唯一命中 —— 否则该行的判据静默丢失。"""
    for row in DELIVERY_OWNERSHIP_TRUTH_TABLE:
        kwargs = _row_kwargs(row)
        if row.verdict is OwnershipVerdict.allowed:
            assert classify_delivery_ownership(**kwargs).row_id == row.row_id
        else:
            with pytest.raises(DeliveryOwnershipError) as exc:
                classify_delivery_ownership(**kwargs)
            assert row.row_id in str(exc.value)


def test_truth_table_predicates_are_unique() -> None:
    seen: dict[tuple[object, ...], str] = {}
    for row in DELIVERY_OWNERSHIP_TRUTH_TABLE:
        assert row.predicate not in seen, f"{row.row_id} 与 {seen.get(row.predicate)} 谓词重复"
        seen[row.predicate] = row.row_id


def test_truth_table_covers_the_three_mandated_semantics() -> None:
    """三条 Task 22 明文语义都必须在表里有对应行。"""
    by_id = {r.row_id: r for r in DELIVERY_OWNERSHIP_TRUTH_TABLE}
    # ① pre-durable 零 owner 合法
    pre_zero = [
        r for r in DELIVERY_OWNERSHIP_TRUTH_TABLE
        if not r.durable_at_is_set
        and not r.has_application
        and not r.has_recovery
        and r.verdict is OwnershipVerdict.allowed
    ]
    assert {r.state for r in pre_zero} >= {
        DeliveryState.received,
        DeliveryState.downloading,
        DeliveryState.rejected,
        DeliveryState.error,
    }
    # ② 双 owner 任何阶段禁止
    assert by_id["T09"].verdict is OwnershipVerdict.forbidden
    assert by_id["T09"].db_constraint == "ck_wpcd_no_double_owner"
    # ③ request 与 application 可同时存在（不做 XOR）
    both = [
        r for r in DELIVERY_OWNERSHIP_TRUTH_TABLE
        if r.has_application and r.has_request and r.verdict is OwnershipVerdict.allowed
    ]
    assert both, "必须有一行同时带 request 与 application 且合法"


def test_truth_table_constraint_names_exist_in_v151() -> None:
    """表里声明的每条约束名都必须在 V151 里真实存在（双向锁死）。

    这条判据的方向很关键：它把"表漂移"和"约束被重命名/删除"都变成红灯。只在
    Python 侧维护一张表、不与迁移交叉核对时，两边可以各自自洽地漂移。
    """
    sql = _MIGRATION.read_text(encoding="utf-8")
    for row in DELIVERY_OWNERSHIP_TRUTH_TABLE:
        assert re.search(
            rf"\b{re.escape(row.db_constraint)}\b", sql
        ), f"{row.row_id} 声明的约束 {row.db_constraint} 不在 V151 中"


def test_uncovered_combination_fails_visibly() -> None:
    """表未覆盖的组合必须**可见地**失败，不得静默放行。"""
    with pytest.raises(DeliveryOwnershipError):
        classify_delivery_ownership(
            state=DeliveryState.acknowledged,
            durable_at_is_set=True,
            application_id=None,
            callback_recovery_case_id=None,
            forcesave_request_id=None,
            incoming_artifact_id=uuid.uuid4(),
            correlation_result=None,
        )


def test_correlation_family_projection() -> None:
    assert correlation_family(None) is CorrelationFamily.absent
    for cr in (
        CorrelationResult.request,
        CorrelationResult.existing_application,
        CorrelationResult.close_capture,
    ):
        assert correlation_family(cr) is CorrelationFamily.correlated
    for cr in (CorrelationResult.unmatched, CorrelationResult.ambiguous):
        assert correlation_family(cr) is CorrelationFamily.unresolved


# ═══════════════════════════════════════════════════════════════════════════
# 7. quarantined incoming（Property 17）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("op", QUARANTINE_FORBIDDEN_OPERATIONS)
def test_every_forbidden_quarantine_operation_rejected(op: str) -> None:
    """逐条驱动禁止清单 —— 只写 allowlist 时容易漏掉真实存在的入口。"""
    with pytest.raises(QuarantineOperationForbiddenError):
        assert_quarantine_operation_allowed(op)


@pytest.mark.parametrize("op", sorted(QUARANTINE_ALLOWED_OPERATIONS))
def test_allowed_quarantine_operations_pass(op: str) -> None:
    assert_quarantine_operation_allowed(op)


def test_quarantine_error_is_caught_by_task10_type() -> None:
    """新异常必须被 Task 10 已有的 catch 点接住，否则上层漏网。"""
    assert issubclass(QuarantineOperationForbiddenError, QuarantinedIncomingError)


def _sealed(state: ArtifactState) -> Any:
    from app.services.workpaper_sync.artifacts import SealedIncoming

    return SealedIncoming(
        delivery_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        wp_id=WP_ID,
        state=state,
        path=Path("x.xlsx"),
        relative_path="x.xlsx",
        sha256=_d("incoming"),
        size_bytes=1024,
        document_type="xlsx",
        durable_at=None,
        quarantined_at=None,
        report=None,
        rejection_error_code="ooxml_external_relationship" if state is ArtifactState.quarantined else None,
        rejection_gate="external_relationship" if state is ArtifactState.quarantined else None,
        rejection_detail=None,
    )


def test_quarantined_and_staged_incoming_fail_with_distinct_types() -> None:
    """隔离（永久安全终态）与"尚未 durable"（暂态）必须是不同异常类型。"""
    with pytest.raises(QuarantinedIncomingError):
        assert_incoming_admissible_for_application(_sealed(ArtifactState.quarantined))
    with pytest.raises(IncomingNotDurableError):
        assert_incoming_admissible_for_application(_sealed(ArtifactState.staged))
    assert not issubclass(IncomingNotDurableError, QuarantinedIncomingError)


def test_quarantined_cannot_be_released_or_published() -> None:
    """`release` / `promote_to_published` 恒抛（Task 11 已实现，这里锁住它没被放开）。"""
    from app.services.workpaper_sync.artifacts import (
        CanonicalArtifactRepository,
        IncomingNotResolvableError,
        QuarantineReleaseForbiddenError,
    )

    repo = CanonicalArtifactRepository.__new__(CanonicalArtifactRepository)
    with pytest.raises(QuarantineReleaseForbiddenError):
        repo.release_quarantined(_sealed(ArtifactState.quarantined))
    with pytest.raises(IncomingNotResolvableError):
        repo.promote_incoming_to_published(_sealed(ArtifactState.durable))


# ═══════════════════════════════════════════════════════════════════════════
# 8. 归组决策（request-first）
# ═══════════════════════════════════════════════════════════════════════════


def _claim(room: RoomRouteFacts, action: str = "callback_write") -> CallbackRouteClaim:
    return _verify(room, token=_token(room, action=action))


def test_userdata_present_takes_request_first(room: RoomRouteFacts) -> None:
    rid = uuid.uuid4()
    payload = CallbackPayload.from_mapping(_body(userdata=str(rid)), contract=CONTRACT)
    plan = plan_correlation(
        payload=payload, rule=CONTRACT.status_rule(6), claim=_claim(room)
    )
    assert plan.mode is CorrelationMode.request
    assert plan.request_id == rid


def test_status2_without_userdata_binds_unique_close_capture(room: RoomRouteFacts) -> None:
    capture = uuid.uuid4()
    payload = CallbackPayload.from_mapping(_body(status=2, userdata=None), contract=CONTRACT)
    plan = plan_correlation(
        payload=payload,
        rule=CONTRACT.status_rule(2),
        claim=_claim(room),
        eligible_close_capture_ids=[capture, capture],
    )
    assert plan.mode is CorrelationMode.close_capture
    assert plan.request_id == capture


def test_status2_without_eligible_request_defers_to_frozen_identity(
    room: RoomRouteFacts,
) -> None:
    payload = CallbackPayload.from_mapping(_body(status=2, userdata=None), contract=CONTRACT)
    plan = plan_correlation(
        payload=payload, rule=CONTRACT.status_rule(2), claim=_claim(room)
    )
    assert plan.mode is CorrelationMode.frozen_identity
    assert plan.request_id is None


def test_status2_with_multiple_candidates_goes_to_recovery(room: RoomRouteFacts) -> None:
    payload = CallbackPayload.from_mapping(_body(status=2, userdata=None), contract=CONTRACT)
    plan = plan_correlation(
        payload=payload,
        rule=CONTRACT.status_rule(2),
        claim=_claim(room),
        eligible_close_capture_ids=[uuid.uuid4(), uuid.uuid4()],
    )
    assert plan.mode is CorrelationMode.recovery
    assert plan.recovery_reason is RecoveryReason.ambiguous_close


def test_status6_without_userdata_never_guesses_base(room: RoomRouteFacts) -> None:
    """status 6 无 userdata ⇒ recovery，**不得**按到达时 room 指针猜 base。"""
    payload = CallbackPayload.from_mapping(_body(userdata=None), contract=CONTRACT)
    plan = plan_correlation(
        payload=payload,
        rule=CONTRACT.status_rule(6),
        claim=_claim(room),
        eligible_close_capture_ids=[uuid.uuid4()],
    )
    assert plan.mode is CorrelationMode.recovery
    assert plan.recovery_reason is RecoveryReason.missing_request


@pytest.mark.parametrize("status", [1, 3, 4, 7])
def test_non_download_statuses_produce_no_content_plan(
    room: RoomRouteFacts, status: int
) -> None:
    rule = CONTRACT.status_rule(status)
    body = _body(status=status, url=None, userdata=None)
    payload = CallbackPayload.from_mapping(body, contract=CONTRACT)
    plan = plan_correlation(payload=payload, rule=rule, claim=_claim(room))
    assert plan.mode is CorrelationMode.no_content
    assert plan.download_required is False
    assert plan.application_allowed is False


def test_notify_action_cannot_drive_content_download(room: RoomRouteFacts) -> None:
    payload = CallbackPayload.from_mapping(_body(), contract=CONTRACT)
    with pytest.raises(CallbackActionNotWritableError):
        plan_correlation(
            payload=payload,
            rule=CONTRACT.status_rule(6),
            claim=_claim(room, action="callback_notify"),
        )


def test_pre_download_plan_cannot_express_incoming_first_dedupe() -> None:
    """结构性判据：下载前的计划**没有**任何 incoming 身份入参/字段。

    Requirement 4.3 禁止"先按 incoming hash 命中旧 application 再读 request"。这里用
    "连表达能力都不给"来落实 —— 若有人给 :func:`plan_correlation` 加上 incoming sha
    参数，本条立刻打红。
    """
    banned = {"incoming", "sha", "digest", "artifact", "application_key", "hash"}
    params = " ".join(inspect.signature(plan_correlation).parameters)
    fields = " ".join(CorrelationPlan.__dataclass_fields__)
    for token in banned:
        assert token not in params, f"plan_correlation 入参出现 {token}"
        assert token not in fields, f"CorrelationPlan 字段出现 {token}"


# ═══════════════════════════════════════════════════════════════════════════
# 9. 执行轨迹（application key 只能在 durable 之后）
# ═══════════════════════════════════════════════════════════════════════════


def test_correlation_requires_recorded_durable_fact() -> None:
    j = CallbackStageJournal()
    j.record(CallbackStage.route_verified)
    j.record(CallbackStage.download_finished)
    with pytest.raises(CallbackStageOrderError) as exc:
        j.assert_correlation_precondition()
    assert "durable" in str(exc.value)


def test_correlation_refused_after_quarantine() -> None:
    j = CallbackStageJournal()
    j.record(CallbackStage.route_verified)
    j.record(CallbackStage.sealed_quarantined, "ooxml_macro_policy")
    with pytest.raises(QuarantineOperationForbiddenError):
        j.assert_correlation_precondition()


def test_correlation_requires_route_verification() -> None:
    j = CallbackStageJournal()
    j.record(CallbackStage.sealed_durable, _d("x"))
    with pytest.raises(CallbackStageOrderError):
        j.assert_correlation_precondition()


def test_happy_path_order_accepted() -> None:
    j = CallbackStageJournal()
    for stage in (
        CallbackStage.route_verified,
        CallbackStage.status_resolved,
        CallbackStage.plan_decided,
        CallbackStage.request_bound,
        CallbackStage.delivery_recorded,
        CallbackStage.download_started,
        CallbackStage.download_finished,
        CallbackStage.sealed_durable,
    ):
        j.record(stage)
    j.assert_correlation_precondition()
    j.assert_request_first()


def test_request_first_violation_detected() -> None:
    j = CallbackStageJournal()
    j.record(CallbackStage.route_verified)
    j.record(CallbackStage.download_started)
    j.record(CallbackStage.request_bound)
    with pytest.raises(CallbackStageOrderError):
        j.assert_request_first()


# ═══════════════════════════════════════════════════════════════════════════
# 10. router 只委派（结构形态；行为判据在 PG 守卫里）
# ═══════════════════════════════════════════════════════════════════════════


def test_service_entry_takes_only_raw_transport_inputs() -> None:
    """`handle_callback` 只吃原始传输层输入 + room id；没有"已判定"的语义参数。"""
    params = set(inspect.signature(CallbackDeliveryService.handle_callback).parameters)
    params.discard("self")
    assert params == {
        "authorization_header",
        "callback_url",
        "body",
        "room_id",
        "secret",
        "expected_write_fence_epoch",
        "journal",
    }
    # route 不承担作者语义：入口不得出现 participant/user
    assert not {"participant_id", "user_id", "user", "actor", "initiator"} & params


def _jose_jwt_bindings(tree: ast.AST) -> set[str]:
    """模块里绑到 `jose.jwt` 的局部名（含 `as` 别名与 `import jose` 后的 `jose.jwt`）。"""
    names: set[str] = {"jose"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("jose"):
            for alias in node.names:
                if alias.name == "jwt":
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("jose"):
                    names.add((alias.asname or alias.name).split(".")[0])
    return names


def _jose_call_sites(tree: ast.AST, method: str) -> int:
    """`<jose-jwt-binding>.<method>(...)` 的调用次数（AST，不数 import、不数文案）。"""
    bindings = _jose_jwt_bindings(tree)
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != method:
            continue
        target = node.func.value
        if isinstance(target, ast.Name) and target.id in bindings:
            count += 1
        elif (
            isinstance(target, ast.Attribute)
            and target.attr == "jwt"
            and isinstance(target.value, ast.Name)
            and target.value.id in bindings
        ):
            count += 1
    return count


def test_jwt_decoding_lives_only_in_callback_route() -> None:
    """同步域内只有 `callback_route` **解** callback route token；只有 `command_service` **签**。

    ## 🔴 判据形态为什么改了（Task 30 独立门实测）

    原判据是「谁 `import` 了 jose 就算解 token」。那是**代理判据**，把两件不同的事混成
    一件：Task 24 的 `command_service.sign_command_token()` 也必须 import jose，因为契约
    `command_service.jwt.required=true` 要求出站 Command Service 请求带签名 token，而那是
    **encode**、不是 decode。于是原判据在 Task 24 落地后必然打红一个**正确**的模块，
    并且反过来**漏掉**真缺陷：在 `callback_delivery.py` 里写
    `from jose.jwt import decode as d` 之后调 `d(...)`，正则 `^\\s*(from jose|import jose)`
    照样命中「from jose」这一行 —— 只是它把 `callback_delivery.py` 记进 offenders，
    而这个列表本来就已经是红的，新缺陷混不出来。

    改成对**调用点**断言，并且两侧都给正向下限（否则「谁都不解」也满足「只有 route 解」）：

    * `decode` 调用点集合 == {`callback_route.py`} —— 解 token 是**校验**，Task 22 要求它
      只有一处实现；且 route 侧至少 1 处，否则「谁都不解」也满足这条。
    * `encode` 调用点集合 == {`callback_route.py`, `command_service.py`} —— 同步域里只有
      **两种** token，各有唯一签发者：route token 由 `callback_route.mint_callback_token()`
      签（与它自己的校验同源，claim 常量取自契约），出站 Command Service token 由
      `command_service.sign_command_token()` 签（契约 `command_service.jwt.required=true`）。
      多一个签发者（例如让 `callback_delivery` 自己签一个 route token）即打红。
    """
    sync_dir = _BACKEND / "app" / "services" / "workpaper_sync"
    modules = sorted(sync_dir.glob("*.py"))
    assert len(modules) > 20, f"同步域只扫到 {len(modules)} 个模块 ⇒ 判据分母塌了"

    decoders: dict[str, int] = {}
    encoders: dict[str, int] = {}
    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if (hits := _jose_call_sites(tree, "decode")):
            decoders[path.name] = hits
        if (hits := _jose_call_sites(tree, "encode")):
            encoders[path.name] = hits

    assert sorted(decoders) == ["callback_route.py"], f"意外的 token 解码者: {decoders}"
    assert decoders["callback_route.py"] >= 1, decoders
    assert sorted(encoders) == ["callback_route.py", "command_service.py"], (
        f"意外的 token 签发者: {encoders}"
    )
    assert min(encoders.values()) >= 1, encoders
