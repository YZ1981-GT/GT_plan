"""P5 + P2 零库判据：服务端直取物化的编排分支 + store 指纹口径 + 状态码分段。

spec: workpaper-sync-switch-performance · 需求 3 / 6

真库那份（``test_store_materialize_pg.py``）证「同源 / 直通前提成立 / 世界前进时让路」。本文件用假协调器把
每条分支单独钉住（真库世界里分不开的：直通被拒后物化又失败、记录按 wp 隔离、store 阶段与物化阶段的
状态码口径），并给变异检验一个秒级的靶子。
"""
from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.workpaper_sync import store_materialize as SM
from app.services.workpaper_sync.endpoint_payloads import scope_only_projection
from app.services.workpaper_sync.materialize_coordinator import (
    MaterializeOutcome,
    PendingTokenSignatureError,
    SubstrateNotPublishedError,
)
from app.services.workpaper_sync.materialize_reuse_verdict import (
    HIT,
    REPLAYED,
    ReuseDecision,
    ReuseMissReason,
    ReuseVerdict,
)
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.store_projection_response import (
    StorePayloadRead,
    StoreProjectionNotBackedError,
)

ENTRY = "xlsx/gt-d2-accounts-receivable"
PROJECT, WP, OTHER_WP, USER = (uuid.uuid4() for _ in range(4))
V1, V2 = uuid.uuid4(), uuid.uuid4()
SHA1, SHA2 = "1" * 64, "2" * 64
MISS = ReuseVerdict(decision=ReuseDecision.miss, miss_reason=ReuseMissReason.content_changed)


class _JsonPathMissing(SyncDomainError):
    """provider 投影阶段的域错误（未在物化码表登记）。"""

    error_code = "json_path_missing_segment"


class _Unregistered(SyncDomainError):
    """物化阶段一个**未登记**的域错误 —— `/materialize` 记 500。"""

    error_code = "some_new_materialize_failure"


def _contract(*, cid: str = "c.d2", sha: str = "a" * 64) -> Any:
    return SimpleNamespace(contract_id=cid, canonical_sha256=sha, document_type="xlsx")


def _registration(contract: Any = "default") -> Any:
    return SimpleNamespace(
        contract=_contract() if contract == "default" else contract,
        adapter=object(),
        adapter_id="c.d2",
    )


def _outcome(
    *, version: uuid.UUID = V1, sha: str = SHA1, verdict: ReuseVerdict = HIT,
    reused: bool = True, replayed: bool = False, descriptor: bool = True,
) -> MaterializeOutcome:
    return MaterializeOutcome(
        descriptor=(
            SimpleNamespace(artifact_sha256=sha, as_dict=lambda: {"room_id": "room-1"})
            if descriptor else None
        ),
        operation_id=uuid.uuid4(), content_version_id=version, revision=3,
        representation_id=uuid.uuid4(), representation_generation=1, replayed=replayed,
        business_identity_reused=reused, commit_count=0 if reused else 1, transaction_ids=(),
        rooms_opened=0, revision_delta=0 if reused else 1, receipt=None, reuse_verdict=verdict,
    )


class _Coordinator:
    """按调用顺序记账的假协调器（生产协调器的公开面：authorize_create / authorize / ...）。"""

    def __init__(self, *, materialize: Any = None, fast: Any = None) -> None:
        self.calls: list[str] = []
        self.fast_kwargs: dict[str, Any] = {}
        self._materialize, self._fast = materialize, fast
        self.pending_request: Any = None
        self.authorized_token: Any = None

    async def authorize_create(self, request: Any) -> Any:
        self.calls.append("authorize_create")
        return SimpleNamespace(request=request)

    async def reuse_for_unchanged_store(self, authorized: Any, **kwargs: Any) -> Any:
        self.calls.append("fast")
        self.fast_kwargs = kwargs
        return self._fast

    async def create_pending_mutation(self, authorized: Any) -> Any:
        self.calls.append("pending")
        self.pending_request = authorized.request
        return SimpleNamespace(pending_mutation_token="tok-1")

    async def authorize(self, request: Any) -> Any:
        self.calls.append("authorize")
        self.authorized_token = request.pending_mutation_token
        return SimpleNamespace(request=request)

    async def materialize(self, authorized: Any) -> Any:
        self.calls.append("materialize")
        if isinstance(self._materialize, BaseException):
            raise self._materialize
        return self._materialize


class _Session:
    def __init__(self) -> None:
        self.executes = 0

    async def execute(self, *_a: Any, **_k: Any) -> Any:
        self.executes += 1
        return SimpleNamespace(scalar_one=lambda: 7)


NORMAL = ["authorize_create", "pending", "authorize", "materialize"]


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Any:
    """store 读取 / 投影构造 / 协调器装配全部换成可观测的假实现。"""
    SM.STORE_FINGERPRINTS.clear()
    state = SimpleNamespace(
        payload='[{"rowId": "r1", "amount": 1}]', multi=False, reads=0, builds=0,
        read_error=None, build_error=None, coordinator=None, projection=scope_only_projection(),
    )

    async def read_store_payload(*, session: Any, wp_id: Any, provider: Any) -> StorePayloadRead:
        state.reads += 1
        if state.read_error is not None:
            raise state.read_error
        return StorePayloadRead(payload=state.payload, multi=state.multi, empty=False)

    async def server_projection(**_kwargs: Any) -> Any:
        state.builds += 1
        if state.build_error is not None:
            raise state.build_error
        return state.projection

    monkeypatch.setattr(SM, "resolve_store_projection_provider", lambda _adapter_id: object())
    monkeypatch.setattr(SM, "read_store_payload", read_store_payload)
    monkeypatch.setattr(SM, "_server_projection", server_projection)
    monkeypatch.setattr(SM, "build_materialize_coordinator", lambda _s, secret: state.coordinator)
    yield state
    SM.STORE_FINGERPRINTS.clear()


async def _run(
    state: Any, coordinator: _Coordinator, *, wp: uuid.UUID = WP, registration: Any = None,
    entry_id: str = ENTRY,
) -> Any:
    state.coordinator = coordinator
    return await SM.materialize_from_store(
        session=_Session(), resolution=object(), registration=registration or _registration(),
        project_id=PROJECT, wp_id=wp, entry_id=entry_id, user_id=USER, sheet_key="d22-managed",
        client_edit_epoch=0, idempotency_key="k-1", secret="s",
    )


def _record(wp: uuid.UUID = WP) -> Any:
    return SM.STORE_FINGERPRINTS.get((str(wp), ENTRY))


def _read(payload: Any = "[]", *, multi: bool = False) -> StorePayloadRead:
    return StorePayloadRead(payload=payload, multi=multi, empty=False)


class TestFingerprint:
    def test_the_same_inputs_give_the_same_fingerprint(self) -> None:
        a = SM.store_fingerprint(read=_read('[{"a": 1}]'), contract=_contract(), adapter_id="c.d2")
        b = SM.store_fingerprint(read=_read('[{"a": 1}]'), contract=_contract(), adapter_id="c.d2")
        assert a == b and len(a) == 64

    @pytest.mark.parametrize(
        "changed",
        [
            dict(read=_read('[{"a": 2}]')),
            dict(read=_read('[{"a":1}]')),  # 逐字节：同义 JSON 的不同写法也算变化（只省不错）
            dict(read=_read('[{"a": 1}]', multi=True)),
            dict(contract=_contract(cid="c.other")),
            dict(contract=_contract(sha="b" * 64)),
            dict(adapter_id="c.other"),
        ],
        ids=["payload", "payload-bytes", "multi", "contract-id", "contract-sha", "adapter"],
    )
    def test_every_input_moves_the_fingerprint(self, changed: dict[str, Any]) -> None:
        base = dict(read=_read('[{"a": 1}]'), contract=_contract(), adapter_id="c.d2")
        assert SM.store_fingerprint(**base) != SM.store_fingerprint(**{**base, **changed})

    def test_multi_store_item_order_is_irrelevant(self) -> None:
        """多 store 载荷是 {item_id: 文本}：键序不是内容（canonical 递归排序）。"""
        first = SM.store_fingerprint(read=_read({"a": "1", "b": "2"}, multi=True), contract=_contract(), adapter_id="x")
        second = SM.store_fingerprint(read=_read({"b": "2", "a": "1"}, multi=True), contract=_contract(), adapter_id="x")
        assert first == second


@pytest.mark.asyncio
class TestOrchestration:
    async def test_a_verified_reuse_records_and_the_next_call_goes_straight_through(self, world: Any) -> None:
        first = _Coordinator(materialize=_outcome(verdict=HIT))
        result = await _run(world, first)
        assert result.fast_path is False and first.calls == NORMAL
        assert (_record().content_version_id, _record().artifact_sha256) == (V1, SHA1)

        fast = _Coordinator(fast=_outcome(verdict=SM.FINGERPRINT_HIT))
        result = await _run(world, fast)
        assert result.fast_path is True
        assert fast.calls == ["authorize_create", "fast"], "直通仍走了 pending / materialize"
        assert fast.fast_kwargs == {
            "expected_content_version_id": V1,
            "expected_artifact_sha256": SHA1,
            "verdict": SM.FINGERPRINT_HIT,
        }
        assert world.builds == 1, "直通仍构造了投影"

    async def test_the_pending_mutation_carries_the_server_projection_and_revision(self, world: Any) -> None:
        coordinator = _Coordinator(materialize=_outcome())
        await _run(world, coordinator)
        assert coordinator.pending_request.projection is world.projection
        assert coordinator.pending_request.expected_revision == 7
        assert coordinator.pending_request.pending_mutation_token is None
        assert coordinator.authorized_token == "tok-1", "materialize 没有消费 pending 回执的 token"

    @pytest.mark.parametrize(
        "outcome",
        [
            _outcome(verdict=MISS, reused=False),
            _outcome(verdict=REPLAYED, reused=False, replayed=True),
            # 判词与记账不一致（任一腿单独说「复用」都不算）：宁可下一次真比一次。
            _outcome(verdict=HIT, reused=False),
            _outcome(verdict=MISS, reused=True),
        ],
        ids=["commit", "replay", "hit-without-reuse", "reuse-without-hit"],
    )
    async def test_anything_but_a_verified_reuse_is_not_recorded(self, world: Any, outcome: Any) -> None:
        await _run(world, _Coordinator(materialize=outcome))
        assert _record() is None
        follow_up = _Coordinator(materialize=_outcome())
        await _run(world, follow_up)
        assert follow_up.calls == NORMAL, "提交 / 重放之后的下一次必须真比一次"

    async def test_a_store_change_skips_the_fast_path(self, world: Any) -> None:
        await _run(world, _Coordinator(materialize=_outcome()))
        world.payload = '[{"rowId": "r1", "amount": 2}]'
        changed = _Coordinator(materialize=_outcome(version=V2, sha=SHA2, verdict=MISS, reused=False))
        await _run(world, changed)
        assert changed.calls == NORMAL
        assert _record() is None

    async def test_a_declined_fast_path_invalidates_before_falling_back(self, world: Any) -> None:
        """直通被协调器拒（世界已前进）且随后物化失败 ⇒ 旧记录不得残留。"""
        await _run(world, _Coordinator(materialize=_outcome()))
        failing = _Coordinator(fast=None, materialize=SubstrateNotPublishedError("gone"))
        with pytest.raises(SubstrateNotPublishedError):
            await _run(world, failing)
        assert failing.calls == ["authorize_create", "fast", *NORMAL]
        assert _record() is None

    async def test_records_are_per_workpaper(self, world: Any) -> None:
        await _run(world, _Coordinator(materialize=_outcome()))
        other = _Coordinator(materialize=_outcome(version=V2))
        await _run(world, other, wp=OTHER_WP)
        assert other.calls == NORMAL, "另一张底稿命中了这张底稿的指纹"
        assert _record().content_version_id == V1 and _record(OTHER_WP).content_version_id == V2

    async def test_a_missing_descriptor_is_refused_and_not_recorded(self, world: Any) -> None:
        with pytest.raises(SM.DescriptorUnavailableError) as raised:
            await _run(world, _Coordinator(materialize=_outcome(descriptor=False)))
        assert _record() is None
        assert SM.classify_store_materialize_rejection(raised.value) == 422


@pytest.mark.asyncio
class TestRejectionPhases:
    """store 阶段与 `GET store-projection` 同口径 422；物化阶段与 `/materialize` 逐字同一映射。"""

    async def test_a_missing_contract_is_refused_before_any_store_read(self, world: Any) -> None:
        coordinator = _Coordinator(materialize=_outcome())
        with pytest.raises(SM.StorePhaseRejectedError) as raised:
            await _run(world, coordinator, registration=_registration(contract=None))
        assert raised.value.error_code == "per_entry_contract_required"
        assert SM.classify_store_materialize_rejection(raised.value) == 422
        assert world.reads == 0 and coordinator.calls == []

    async def test_an_entry_outside_the_manifest_is_refused(self, world: Any) -> None:
        with pytest.raises(SM.StorePhaseRejectedError) as raised:
            await _run(world, _Coordinator(materialize=_outcome()), entry_id="xlsx/not-a-manifest-entry")
        assert raised.value.error_code == "entry_not_in_manifest"
        assert world.reads == 0

    @pytest.mark.parametrize(
        ("slot", "error", "code"),
        [
            ("read_error", StoreProjectionNotBackedError("不是 store 型"), "entry_not_store_backed"),
            ("build_error", _JsonPathMissing("缺 fields 段"), "json_path_missing_segment"),
        ],
        ids=["store-read", "projection-build"],
    )
    async def test_store_phase_errors_keep_their_code_and_map_to_422(
        self, world: Any, slot: str, error: SyncDomainError, code: str
    ) -> None:
        """error_code 与文案原样保留（前端按它判「非 store 型 ⇒ 回落旧路径」）。"""
        setattr(world, slot, error)
        coordinator = _Coordinator(materialize=_outcome())
        with pytest.raises(SM.StorePhaseRejectedError) as raised:
            await _run(world, coordinator)
        assert raised.value.error_code == code and str(raised.value) == str(error)
        assert raised.value.__cause__ is error
        assert SM.classify_store_materialize_rejection(raised.value) == 422
        assert "pending" not in coordinator.calls

    @pytest.mark.parametrize(
        ("error", "status"),
        [
            (SubstrateNotPublishedError("首版未发布"), 422),
            (PendingTokenSignatureError("坏 token"), 409),
            (_Unregistered("新失败"), 500),
        ],
        ids=["registered-422", "registered-409", "unregistered-500"],
    )
    async def test_materialize_phase_errors_are_not_wrapped(
        self, world: Any, error: SyncDomainError, status: int
    ) -> None:
        """物化阶段原样抛出：未登记 ⇒ 500（与 `/materialize` 同口径，不被 store 阶段的 422 吞掉）。"""
        with pytest.raises(type(error)) as raised:
            await _run(world, _Coordinator(materialize=error))
        assert raised.value is error
        assert SM.classify_store_materialize_rejection(error) == status

    async def test_non_domain_errors_propagate_untouched(self, world: Any) -> None:
        world.build_error = ValueError("provider bug")
        with pytest.raises(ValueError, match="provider bug"):
            await _run(world, _Coordinator(materialize=_outcome()))


class TestResponseBody:
    """与 `/materialize` 同一指标与 result 口径；响应体多带 fast_path / reuse_verdict。"""

    @pytest.fixture
    def recorded(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
        from app.services.workpaper_sync.metrics import sync_metrics

        calls: list[tuple[str, dict[str, Any]]] = []
        monkeypatch.setattr(
            sync_metrics, "record_outcome", lambda metric, **kw: calls.append((metric, kw))
        )
        return calls

    def _body(self, outcome: Any, *, fast_path: bool, declines: tuple[Any, ...] = ()) -> dict[str, Any]:
        result = SM.StoreMaterializeResult(outcome=outcome, fast_path=fast_path, declines=declines)
        return SM.response_body(result, project_id=PROJECT, wp_id=WP, entry_id=ENTRY)

    def test_fast_path_body_and_reuse_metric(self, recorded: list[Any]) -> None:
        from app.services.workpaper_sync.materialize_reuse_verdict import REUSE_METRIC

        body = self._body(_outcome(verdict=SM.FINGERPRINT_HIT), fast_path=True)
        assert body == {"room_id": "room-1", "replayed": False, "fast_path": True, "reuse_verdict": "hit"}
        assert recorded == [(REUSE_METRIC, {
            "result": "hit", "landed": True, "project_id": PROJECT, "wp_id": WP, "entry_id": ENTRY,
        })]

    def test_single_pass_declines_are_emitted(self, recorded: list[Any]) -> None:
        from app.services.workpaper_sync.materialize_reuse_verdict import (
            SINGLE_PASS_DECLINE_METRIC,
            SinglePassDeclineClass,
        )

        decline = next(iter(SinglePassDeclineClass))
        body = self._body(_outcome(verdict=MISS, reused=False), fast_path=False, declines=(decline,))
        assert body["reuse_verdict"] == "miss_content_changed" and body["fast_path"] is False
        assert [m for m, _ in recorded][-1] == SINGLE_PASS_DECLINE_METRIC
        assert recorded[-1][1]["result"] == decline.value

    def test_a_defect_class_miss_is_logged(self, recorded: list[Any], caplog: pytest.LogCaptureFixture) -> None:
        defect = ReuseVerdict(
            decision=ReuseDecision.miss, miss_reason=ReuseMissReason.digest_representation_drift,
            differences=("x: '1.0' -> '1'",),
        )
        with caplog.at_level(logging.ERROR, logger=SM.__name__):
            self._body(_outcome(verdict=defect, reused=False), fast_path=False)
        assert any("缺陷类未命中" in r.getMessage() for r in caplog.records)


def test_frontend_fallback_codes_match_the_backend_error_codes() -> None:
    """前端「非 store 型 ⇒ 回落客户端路径」的码必须逐字等于后端真实 error_code（后端改名即红）。

    设计稿原写 `store_projection_not_backed` —— 后端根本没有这个码；照抄进前端，回落分支就永远不触发。
    """
    import re
    from pathlib import Path

    from app.services.workpaper_sync.store_projection_response import (
        StoreProjectionProviderNotAllowedError,
    )

    source = (
        Path(__file__).resolve().parents[3]
        / "audit-platform/frontend/src/components/workpaper/sync/workpaperSyncBridgeFailure.ts"
    ).read_bytes().decode("utf-8")
    block = source.split("export const SERVER_STORE_FALLBACK_CODES", 1)[1].split("])", 1)[0]
    assert set(re.findall(r"'([a-z_]+)'", block)) == {
        StoreProjectionNotBackedError.error_code,
        StoreProjectionProviderNotAllowedError.error_code,
    }
