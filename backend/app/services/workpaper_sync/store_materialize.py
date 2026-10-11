"""store 型 entry 的服务端直取物化 + store 指纹直通。

spec: workpaper-sync-switch-performance · P5 + P2（需求 3）

═══ 为什么 ═══

原路径（HTML → OO）：浏览器 GET store-projection（服务端从库里现算 ~2.9 万字段）→ 原样 POST 回
pending-mutations → materialize。那份投影本来就是服务端算的，经浏览器转一圈只多付两次大载荷传输与
一次重复解析（实测 GET ≈3.2 s + POST ≈4.5 s，复用命中时它们是整趟耗时的大头）。

本模块把三步收进一个请求：服务端读 store → 构造投影（与 store-projection **同一实现**，并经
`_flatten_projection_values` → `build_projection` 往返，保证与客户端路径逐字节同源）→ 自建 pending
mutation → materialize。

═══ 指纹直通（P2）═══

正常路径**判定复用命中**（投影已与当前 content version 逐字节或骨架无关地比过、相同）后，记录
「store 原始载荷 + 契约 canonical 摘要 + adapter」的指纹，以及被比对的 content version 与其 substrate
字节摘要。下次请求指纹相同、且 preflight 看到的 content version 与 substrate 字节也相同 ⇒ 投影是这些
输入的纯函数、必与上次相同 ⇒ 复用判定的结果也必相同 ⇒ 跳过构造与物化，直接复用当前 representation
开 room（零 revision）。

🔴 **只在复用命中时记录，提交 / 重放之后不记**：提交之后「投影 vs 新版本」从未被比对过 —— 新版本
来自本次投影，但「从新 substrate 重新构造的投影是否仍等于它」取决于 materialize→extract 往返是不是
不动点（P1 修的正是它在 D2 上不成立）。记了就等于把一次没做过的校验当成做过。所以提交后的下一次
仍走正常路径、真比一次；命中后才开始直通。

指纹表在**进程内**（有界 LRU）：重启 / 发版即清空 ⇒ 构造代码变了也不会让旧指纹误命中；多 worker 各自
独立 —— 未命中只是回落正常路径，不影响正确性。
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hashlib
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa

from app.services.workpaper_sync.definitions import canonical_json_bytes
from app.services.workpaper_sync.endpoint_payloads import build_projection, scope_only_projection
from app.services.workpaper_sync.entry_profile import capability_of, manifest_entries_by_id
from app.services.workpaper_sync.materialize_coordinator import (
    MaterializeOutcome,
    MaterializeRequest,
    build_materialize_coordinator,
    classify_materialize_rejection,
)
from app.services.workpaper_sync.materialize_reuse_verdict import (
    ReuseDecision,
    ReuseVerdict,
    single_pass_decline_scope,
)
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.parse_cache import BoundedLruCache
from app.services.workpaper_sync.store_projection_response import (
    StorePayloadRead,
    StoreProjectionContractRequiredError,
    _flatten_projection_values,
    _overlay_with_published_substrate,
    read_store_payload,
    resolve_store_projection_provider,
)
from app.services.workpaper_sync.sync_timing import mark

_LOGGER = logging.getLogger(__name__)

#: 指纹 schema（构造口径变化必须 +1）。
STORE_FINGERPRINT_SCHEMA = "wp-sync-store-fingerprint:v1"

#: 指纹直通的判词（decision=hit，指标落既有 `REUSE_METRIC` 的 hit 格）。
FINGERPRINT_HIT = ReuseVerdict(
    decision=ReuseDecision.hit,
    differences=(
        "store_fingerprint_reused: store 原始载荷、契约、adapter 与当前内容版本均未变，"
        "跳过投影构造与物化",
    ),
)


class EntryNotInManifestError(SyncDomainError):
    """entry 不在 manifest：未登记 entry 不得按 bidirectional 处理（AC 1.1 / 3.9）。"""

    error_code = "entry_not_in_manifest"


class DescriptorUnavailableError(SyncDomainError):
    """materialize 未产出 descriptor —— 不得挂载半个 descriptor。"""

    error_code = "descriptor_unavailable"


@dataclass(frozen=True)
class StoreFingerprintRecord:
    fingerprint: str
    content_version_id: uuid.UUID
    artifact_sha256: str


#: (wp_id, entry_id) → 上次**复用命中**（投影已与该 content version 比过且相同）时的指纹记录。
STORE_FINGERPRINTS: "BoundedLruCache[tuple[str, str], StoreFingerprintRecord]" = (
    BoundedLruCache(maxsize=4096)
)


@dataclass(frozen=True)
class StoreMaterializeResult:
    outcome: MaterializeOutcome
    fast_path: bool
    declines: tuple[Any, ...]


def store_fingerprint(*, read: StorePayloadRead, contract: Any, adapter_id: str) -> str:
    """store 原始载荷（逐字节）+ 契约 canonical 摘要 + adapter 的摘要。"""
    body = {
        "schema": STORE_FINGERPRINT_SCHEMA,
        "multi": bool(read.multi),
        "payload": read.payload,
        "contract_id": str(contract.contract_id),
        "contract_sha256": str(contract.canonical_sha256),
        "adapter_id": str(adapter_id),
    }
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


class StorePhaseRejectedError(SyncDomainError):
    """store 阶段（读 store / 构造投影 / manifest）的域拒绝。

    原样保留 `error_code` 与文案（前端按 error_code 判「非 store 型 ⇒ 回落旧路径」），只把
    「它来自哪一段」带给状态码映射：store 阶段与 `GET store-projection` 同口径一律 422。
    """

    error_code = "store_phase_rejected"

    def __init__(self, cause: SyncDomainError) -> None:
        super().__init__(str(cause))
        self.error_code = str(getattr(cause, "error_code", "") or type(self).error_code)


@contextlib.contextmanager
def _store_phase() -> Iterator[None]:
    try:
        yield
    except StorePhaseRejectedError:
        raise
    except SyncDomainError as exc:
        raise StorePhaseRejectedError(exc) from exc


def classify_store_materialize_rejection(exc: BaseException) -> int:
    """store 阶段 → 422（同 `GET store-projection`）；物化阶段 → 与 `/materialize` **逐字**同一映射
    （`classify_materialize_rejection`：未登记 ⇒ 500，未知失败 fail visible）。"""
    if isinstance(exc, (StorePhaseRejectedError, DescriptorUnavailableError)):
        return 422
    return classify_materialize_rejection(exc)


def _capability(entry_id: str) -> Any:
    entry = manifest_entries_by_id().get(str(entry_id))
    if entry is None:
        raise EntryNotInManifestError(
            f"entry {entry_id!r} 不在 workpaper_sync_entry_manifest 中 —— 未登记 entry 不得按 "
            "bidirectional 处理（AC 1.1 / 3.9）"
        )
    return capability_of(entry)


async def _server_projection(
    *, session: Any, resolution: Any, registration: Any, provider: Any, read: StorePayloadRead,
    project_id: uuid.UUID, wp_id: uuid.UUID, entry_id: str,
) -> Any:
    contract = registration.contract
    if read.multi:
        store_projection = provider.build_combined_store_projection(read.payload, contract=contract)
    else:
        store_projection = provider.build_store_projection(read.payload, contract=contract)
    overlaid, _applied = await _overlay_with_published_substrate(
        resolution=resolution, project_id=project_id, wp_id=wp_id, entry_id=entry_id,
        registration=registration, store_projection=store_projection,
    )
    # 🔴 经「拍平 → build_projection」往返：与客户端路径（GET 拍平 → POST → build_projection）
    #    逐字节同源，pending digest 与复用判据才与原路径一致。
    wire = {
        "values": _flatten_projection_values(overlaid),
        "row_keys": {str(t): [str(r) for r in ids] for t, ids in overlaid.row_keys.items()},
    }
    return await asyncio.to_thread(build_projection, payload=wire, contract=contract)


async def materialize_from_store(
    *,
    session: Any,
    resolution: Any,
    registration: Any,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    user_id: uuid.UUID,
    sheet_key: str,
    client_edit_epoch: int,
    idempotency_key: str,
    secret: str,
) -> StoreMaterializeResult:
    contract = registration.contract
    with _store_phase():
        if contract is None:
            raise StoreProjectionContractRequiredError(
                f"entry {entry_id!r} 的 registration 没有 approved contract —— 无从按 stable key 投影 store"
            )
        capability = _capability(entry_id)
        provider = resolve_store_projection_provider(str(registration.adapter_id))
        read = await read_store_payload(session=session, wp_id=wp_id, provider=provider)
    fingerprint = store_fingerprint(read=read, contract=contract, adapter_id=str(registration.adapter_id))
    mark("store_read")
    coordinator = build_materialize_coordinator(session, secret=secret)
    base = dict(
        project_id=project_id, wp_id=wp_id, entry_id=str(entry_id), sheet_key=str(sheet_key),
        user_id=user_id, idempotency_key=str(idempotency_key), capability=capability,
        contract=contract, adapter=registration.adapter, adapter_id=str(registration.adapter_id),
        client_edit_epoch=int(client_edit_epoch),
    )
    key = (str(wp_id), str(entry_id))
    record = STORE_FINGERPRINTS.get(key)
    if record is not None and record.fingerprint == fingerprint:
        probe = MaterializeRequest(
            **base, pending_mutation_token=None, expected_revision=0,
            projection=scope_only_projection(),
        )
        outcome = await coordinator.reuse_for_unchanged_store(
            await coordinator.authorize_create(probe),
            expected_content_version_id=record.content_version_id,
            expected_artifact_sha256=record.artifact_sha256,
            verdict=FINGERPRINT_HIT,
        )
        if outcome is not None:
            mark("fingerprint_reused")
            return StoreMaterializeResult(outcome=outcome, fast_path=True, declines=())
        STORE_FINGERPRINTS.invalidate(key)

    with _store_phase():
        projection = await _server_projection(
            session=session, resolution=resolution, registration=registration, provider=provider,
            read=read, project_id=project_id, wp_id=wp_id, entry_id=str(entry_id),
        )
    mark("projection_built")
    revision = (
        await session.execute(
            sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"), {"wp": str(wp_id)}
        )
    ).scalar_one()
    first = MaterializeRequest(
        **base, pending_mutation_token=None, expected_revision=int(revision), projection=projection
    )
    receipt = await coordinator.create_pending_mutation(await coordinator.authorize_create(first))
    mark("pending_mutation")
    second = dataclasses.replace(first, pending_mutation_token=receipt.pending_mutation_token)
    authorized = await coordinator.authorize(second)
    with single_pass_decline_scope() as declines:
        outcome = await coordinator.materialize(authorized)
    if outcome.descriptor is None:
        raise DescriptorUnavailableError("materialize 未产出 descriptor —— 不得挂载半个 descriptor")
    if verified_against_current_version(outcome):
        STORE_FINGERPRINTS.put(
            key,
            StoreFingerprintRecord(
                fingerprint=fingerprint,
                content_version_id=outcome.content_version_id,
                artifact_sha256=str(outcome.descriptor.artifact_sha256),
            ),
        )
    else:
        STORE_FINGERPRINTS.invalidate(key)
    return StoreMaterializeResult(outcome=outcome, fast_path=False, declines=tuple(declines))


def verified_against_current_version(outcome: MaterializeOutcome) -> bool:
    """本次投影是否**真的**与当前 content version 比过且相同（复用命中；提交 / 重放都不算）。

    判词（归因面）与 revision 记账面必须**同时**说「复用」：两者由同一条 `_settle_reuse` 路径一起
    产出，若哪天出现「判词 hit 而记账说没复用」的不一致结果，宁可不记（下一次真比一次）。
    重放的判词是 `replayed`、记账是 `business_identity_reused=False`，两腿都已排除，不再单列。
    """
    return outcome.reuse_verdict.decision is ReuseDecision.hit and bool(
        outcome.business_identity_reused
    )


def response_body(
    result: StoreMaterializeResult, *, project_id: uuid.UUID, wp_id: uuid.UUID, entry_id: str
) -> dict[str, Any]:
    """emit 复用判词 / 单趟回落指标（与 `/materialize` 端点同一指标与 result 口径），返回响应体。

    `result` 显式取自 `outcome.reuse_verdict.metric_result`（不用 getattr 默认值）。
    """
    from app.services.workpaper_sync.materialize_reuse_verdict import (
        REUSE_METRIC,
        SINGLE_PASS_DECLINE_METRIC,
    )
    from app.services.workpaper_sync.metrics import sync_metrics

    labels = {"project_id": project_id, "wp_id": wp_id, "entry_id": str(entry_id)}
    outcome = result.outcome
    sync_metrics.record_outcome(
        REUSE_METRIC, result=outcome.reuse_verdict.metric_result, landed=True, **labels
    )
    if outcome.reuse_verdict.is_defect:
        # 与 `/materialize` 同口径：缺陷类未命中不抛（物化已成功），落 error 日志供 CI 门 / 排障。
        _LOGGER.error(
            "[reuse_verdict] 🔴 缺陷类未命中 %s（wp=%s entry=%s）：%s",
            outcome.reuse_verdict.metric_result, wp_id, entry_id,
            " ｜ ".join(outcome.reuse_verdict.differences),
        )
    for decline_class in result.declines:
        sync_metrics.record_outcome(
            SINGLE_PASS_DECLINE_METRIC, result=decline_class.value, landed=True, **labels
        )
    assert outcome.descriptor is not None  # materialize_from_store 已保证
    body = outcome.descriptor.as_dict()
    body["replayed"] = bool(outcome.replayed)
    body["fast_path"] = bool(result.fast_path)
    body["reuse_verdict"] = outcome.reuse_verdict.metric_result
    return body


__all__ = [
    "DescriptorUnavailableError",
    "EntryNotInManifestError",
    "FINGERPRINT_HIT",
    "STORE_FINGERPRINTS",
    "STORE_FINGERPRINT_SCHEMA",
    "StoreFingerprintRecord",
    "StoreMaterializeResult",
    "StorePhaseRejectedError",
    "classify_store_materialize_rejection",
    "materialize_from_store",
    "response_body",
    "store_fingerprint",
    "verified_against_current_version",
]
