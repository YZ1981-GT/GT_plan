"""按 **frozen bundle 的 contract slot** 把冻结契约读回来 —— 历史 operation 的唯一读法。

═══ 它解决什么（spec frozen-contract-read-path ADR-FC-001） ═══

一条 `state=conflict` 的历史 operation 冻结的是**旧版**契约。此后所有读侧入口
（冲突预览 / 裁决 / retry）都要求调用方**传**一份 contract 进来，而调用方只能从
registry / 磁盘现取 ⇒ 恒得新契约 ⇒ 恒撞 `frozen_contract_digest_drift`：

    operation 11809f53…  contract_slot_digest = 75fca57d…
    该 entry 当前契约                          = 645e0500…
    ⇒ 任何读侧入口都拒绝，24 条冲突永远不能裁决

**这个拒绝是正确的**（按 registry 当前 alias 渲染历史 operation，审计师看到的业务标签与
单元格地址会漂到新模板上）。缺的只是「按冻结 slot 把那份旧契约读回来」这一步 ——
实测旧契约在库里完好：definition 行 `approved`、blob `published`、磁盘 352 KB 在位。

═══ 唯一读法（三步，顺序即判据） ═══

1. `bundle.slots[BundleSlot.contract].slot_ref`（形如 `definition:<uuid>`）→ definition 行；
2. 该行 `blob_artifact_id` → artifact row → 仓储 `resolve_relative_path()` → 读字节；
3. `json.loads` → `parse_contract()` → 断言 `canonical_sha256 == slot_digest`。

🔴 **禁止**按 `logical_id` + 最新版本取。实测同一 `logical_id` 已有多代并存
（`d4.revenue_detail` **46 代**、`d2.inspection` **5 行**，全库 89 个 logical_id 存在多代）
⇒ 「取最新」会安静地拿到新契约，正是本缺陷的成因。

🔴 **禁止**按 `contract_id` 从磁盘现取 —— 那是 registry 当前 alias，同一问题。

═══ 错误分型（R1.3：四类必须各自可辨） ═══

| 失败 | 类型 | 用户该去查什么 |
| --- | --- | --- |
| slot 不是 definition child | `FrozenContractSlotNotDefinitionError` | bundle 的 typed null marker（合法但无契约） |
| definition 行不存在 | `FrozenContractDefinitionMissingError` | 数据链（definition 表） |
| definition 非 approved | `FrozenContractNotApprovedError` | 审核态（不该被冻结进 bundle） |
| blob 行/文件读不到 | `FrozenContractBlobUnreadableError` | 存储卷 |
| payload 与 slot digest 不符 | `FrozenContractDigestDriftError` | 数据被改写 |
| payload 过不了当前解析器 | `FrozenContractUnparsableError` | 契约演化不向后兼容 |

**不得统一报「契约漂移」** —— 那会把「数据链断了」和「文件丢了」碾成一团。
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping as AbcMapping
from dataclasses import dataclass
from typing import Any, Final, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import WorkpaperSyncDefinitionArtifact
from app.services.workpaper_sync.contracts import (
    ContractError,
    SyncContract,
    parse_contract,
)
from app.services.workpaper_sync.frozen_definition_blob import (
    FrozenDefinitionBlobDigestMismatchError,
    FrozenDefinitionBlobError,
    FrozenDefinitionBlobMissingError,
    FrozenDefinitionBlobUnreadableError,
    read_definition_payload,
)
from app.services.workpaper_sync.models import (
    BundleSlot,
    DefinitionKind,
    DefinitionState,
    SyncDomainError,
)

__all__ = [
    "FrozenContractReaderError",
    "FrozenContractSlotNotDefinitionError",
    "FrozenContractDefinitionMissingError",
    "FrozenContractNotApprovedError",
    "FrozenContractBlobUnreadableError",
    "FrozenContractDigestDriftError",
    "FrozenContractUnparsableError",
    "FrozenContractSnapshot",
    "FrozenContractReader",
    "read_frozen_contract",
]

_DEFINITION_REF_PREFIX: Final[str] = "definition:"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 错误
# ═══════════════════════════════════════════════════════════════════════════


class FrozenContractReaderError(SyncDomainError):
    """读冻结契约失败的基类。``diagnostics`` 逐条说清是哪个对象出的问题。"""

    error_code = "frozen_contract_read_failed"

    def __init__(self, message: str, *, diagnostics: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.diagnostics: Mapping[str, Any] = dict(diagnostics)

    def as_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": str(self),
            **dict(self.diagnostics),
        }


class FrozenContractSlotNotDefinitionError(FrozenContractReaderError):
    """bundle 的 contract slot 是 typed null marker（`contract:none:v1`）。

    这**不是**缺陷：`custom` / `opaque` 权威模型的 entry 本来就没有 per-entry contract。
    但对「我要读契约」的调用方来说它必须是一个**可辨**的答案，而不是空对象或异常崩溃。
    """

    error_code = "frozen_contract_slot_not_definition"


class FrozenContractDefinitionMissingError(FrozenContractReaderError):
    """`slot_ref` 指向的 definition 行不存在 —— 数据链断了。"""

    error_code = "frozen_contract_definition_missing"


class FrozenContractNotApprovedError(FrozenContractReaderError):
    """definition 行的 `state` 不是 `approved`。

    理论上不可能被冻结进 approved bundle（bundle 侧有 `assert_child_approved`），
    所以出现即说明有写入方绕过了门 —— 必须点名 state 而不是笼统报「不可用」。
    """

    error_code = "frozen_contract_not_approved"


class FrozenContractBlobUnreadableError(FrozenContractReaderError):
    """blob artifact row 不存在，或磁盘文件读不到 —— 存储层问题。"""

    error_code = "frozen_contract_blob_unreadable"


class FrozenContractDigestDriftError(FrozenContractReaderError):
    """读回的 payload 的 canonical digest 与 `contract_slot_digest` 不符。

    与 :class:`FrozenContractUnparsableError` 分开：这里是「字节变了」，
    那里是「字节没变但解析器不认」。两者的处置完全不同（查数据 vs 查契约演化）。
    """

    error_code = "frozen_contract_digest_drift"


class FrozenContractUnparsableError(FrozenContractReaderError):
    """旧 payload 过不了**当前** `parse_contract` —— 契约演化不向后兼容。

    按 design §4 与勘误 E.7：**如实拒绝，不写兼容层**。
    静默降级（例如「跳过校验继续用」）会让审计师看到一份来路不明的契约。
    """

    error_code = "frozen_contract_unparsable"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 结果
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FrozenContractSnapshot:
    """读回来的一份冻结契约 + 它的出处（每项都可复核）。"""

    contract: SyncContract
    #: bundle 上冻结的 slot digest（= `contract.canonical_sha256`，读路径已断言相等）
    slot_digest: str
    #: `slot_ref` 里的 definition 行 id
    definition_id: uuid.UUID
    #: definition 行上冻结的 `semantic_version`
    semantic_version: str
    #: blob artifact 行 id（诊断用）
    blob_artifact_id: uuid.UUID | None = None

    @property
    def contract_id(self) -> str:
        return self.contract.contract_id


# ═══════════════════════════════════════════════════════════════════════════
# 3. 读取
# ═══════════════════════════════════════════════════════════════════════════


def _parse_definition_ref(slot_ref: str, *, diagnostics: Mapping[str, Any]) -> uuid.UUID:
    """`definition:<uuid>` → UUID。

    🔴 不 `strip()` 之后又 `split`：`slot_ref` 是 DB 列上的冻结值，
    带前导空格说明它被谁改过 —— 那要报错，不是宽容处理。
    """
    ref = str(slot_ref or "")
    if not ref.startswith(_DEFINITION_REF_PREFIX):
        raise FrozenContractSlotNotDefinitionError(
            f"contract slot 的 ref {ref!r} 不是 `definition:<uuid>` 形态",
            diagnostics={**dict(diagnostics), "slot_ref": ref},
        )
    raw = ref[len(_DEFINITION_REF_PREFIX) :]
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError) as exc:
        raise FrozenContractSlotNotDefinitionError(
            f"contract slot 的 ref {ref!r} 里的 uuid 无法解析: {exc}",
            diagnostics={**dict(diagnostics), "slot_ref": ref},
        ) from exc


class FrozenContractReader:
    """按 frozen bundle 的 contract slot 读回 `SyncContract`。

    用法::

        reader = FrozenContractReader(session=session, artifacts=repo)
        snapshot = await reader.read(bundle=bundle_snapshot)
        contract = snapshot.contract

    🔴 本类**只读**：不写 definition、不写 artifact、不碰 registry。
    """

    def __init__(self, *, session: AsyncSession, artifacts: Any) -> None:
        self._session = session
        self._artifacts = artifacts

    async def read(self, *, bundle: Any) -> FrozenContractSnapshot:
        """读回该 bundle 冻结的 per-entry contract。

        Args:
            bundle: :class:`~app.services.workpaper_sync.resolution.DefinitionBundleSnapshot`
                （只需 `bundle_id` 与 `slots`；不要求是完整快照，便于测试注入）。

        Raises:
            FrozenContractSlotNotDefinitionError: slot 是 typed null marker / ref 形态非法。
            FrozenContractDefinitionMissingError: definition 行不存在。
            FrozenContractNotApprovedError: definition 非 approved。
            FrozenContractBlobUnreadableError: blob 行或磁盘文件读不到。
            FrozenContractDigestDriftError: payload digest 与 slot digest 不符。
            FrozenContractUnparsableError: payload 过不了当前 `parse_contract`。
        """
        bundle_id = getattr(bundle, "bundle_id", None)
        base: dict[str, Any] = {"bundle_id": "" if bundle_id is None else str(bundle_id)}

        slot = self._contract_slot(bundle=bundle, diagnostics=base)
        base["contract_slot_digest"] = slot.slot_digest
        base["contract_slot_ref"] = slot.slot_ref

        definition_id = _parse_definition_ref(slot.slot_ref, diagnostics=base)
        base["definition_id"] = str(definition_id)

        child = await self._load_definition_row(
            definition_id=definition_id, diagnostics=base
        )
        base["blob_artifact_id"] = "" if child.blob_artifact_id is None else str(
            child.blob_artifact_id
        )

        # 读 payload（公共模块统一做 decode + digest 复核，见 ADR-FC-002）
        try:
            payload = await read_definition_payload(
                session=self._session,
                artifacts=self._artifacts,
                child=child,
                diagnostics=base,
            )
        except FrozenDefinitionBlobMissingError as exc:
            raise FrozenContractBlobUnreadableError(
                str(exc), diagnostics={**base, **dict(exc.diagnostics)}
            ) from exc
        except FrozenDefinitionBlobUnreadableError as exc:
            raise FrozenContractBlobUnreadableError(
                str(exc), diagnostics={**base, **dict(exc.diagnostics)}
            ) from exc
        except FrozenDefinitionBlobDigestMismatchError as exc:
            raise FrozenContractDigestDriftError(
                str(exc), diagnostics={**base, **dict(exc.diagnostics)}
            ) from exc
        except FrozenDefinitionBlobError as exc:
            # decode / 根类型失败：字节在但内容不是合法 JSON 对象
            raise FrozenContractUnparsableError(
                str(exc), diagnostics={**base, **dict(exc.diagnostics)}
            ) from exc

        contract = self._parse(payload=payload, child=child, diagnostics=base)

        # 最后一道：`parse_contract` 现算的 canonical digest 必须等于 slot digest。
        # 🔴 这不是与上面重复：上面比的是「磁盘 payload ↔ definition 行 sha256」，
        #    这里比的是「**重新解析后的** canonical payload ↔ bundle 上冻结的 slot digest」。
        #    两者之间的差别正是「definition 行与 bundle 不同步」这一类缺陷的可见处。
        if contract.canonical_sha256.strip() != str(slot.slot_digest).strip():
            raise FrozenContractDigestDriftError(
                f"bundle {base['bundle_id']} 的 contract slot digest "
                f"{slot.slot_digest!r} 与读回契约的 canonical digest "
                f"{contract.canonical_sha256!r} 不一致",
                diagnostics={
                    **base,
                    "slot_digest": str(slot.slot_digest),
                    "contract_canonical_sha256": contract.canonical_sha256,
                },
            )

        return FrozenContractSnapshot(
            contract=contract,
            slot_digest=str(slot.slot_digest),
            definition_id=definition_id,
            semantic_version=str(child.semantic_version or ""),
            blob_artifact_id=child.blob_artifact_id,
        )

    # ── 内部 ──────────────────────────────────────────────────────────

    @staticmethod
    def _contract_slot(*, bundle: Any, diagnostics: Mapping[str, Any]) -> Any:
        """取 contract slot spec；`None` / 非 definition 都归「slot 不是契约」。"""
        slots = getattr(bundle, "slots", None)
        if not isinstance(slots, AbcMapping):
            raise FrozenContractSlotNotDefinitionError(
                "bundle 没有 `slots` 映射 —— 无法定位 contract slot",
                diagnostics=dict(diagnostics),
            )
        spec = slots.get(BundleSlot.contract)
        if spec is None:
            raise FrozenContractSlotNotDefinitionError(
                "bundle 的 slots 里没有 contract 项",
                diagnostics=dict(diagnostics),
            )
        if not spec.is_definition:
            raise FrozenContractSlotNotDefinitionError(
                f"bundle 的 contract slot 是 typed null marker "
                f"（type={spec.slot_type!r}）—— 该 entry 没有 per-entry contract，"
                "不是读取失败",
                diagnostics={
                    **dict(diagnostics),
                    "slot_type": str(spec.slot_type),
                },
            )
        return spec

    async def _load_definition_row(
        self, *, definition_id: uuid.UUID, diagnostics: Mapping[str, Any]
    ) -> WorkpaperSyncDefinitionArtifact:
        """按 id 读 definition 行，并校验 kind / state（两类失败各自点名）。"""
        row = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id == definition_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise FrozenContractDefinitionMissingError(
                f"contract slot 指向的 definition {definition_id} 不存在 —— "
                "数据链断了（不是契约漂移）",
                diagnostics=dict(diagnostics),
            )
        if str(row.kind) != DefinitionKind.contract.value:
            raise FrozenContractDefinitionMissingError(
                f"definition {definition_id} 的 kind={row.kind!r} 不是 contract —— "
                "bundle 的 contract slot 指向了别的 child",
                diagnostics={**dict(diagnostics), "kind": str(row.kind)},
            )
        if str(row.state) != DefinitionState.approved.value:
            raise FrozenContractNotApprovedError(
                f"definition {definition_id} 的 state={row.state!r} 不是 approved —— "
                "未 approved 的契约不得用于历史 operation 读侧",
                diagnostics={**dict(diagnostics), "state": str(row.state)},
            )
        return row

    @staticmethod
    def _parse(
        *,
        payload: Mapping[str, Any],
        child: WorkpaperSyncDefinitionArtifact,
        diagnostics: Mapping[str, Any],
    ) -> SyncContract:
        """`parse_contract` 的失败必须自成一类（契约演化不兼容 ≠ 数据漂移）。

        🔴 **不传** `adapter_id`：那是「contract_id 必须等于文件名」的双向锁（CS-2），
        只有**从磁盘按文件名读**的调用方才该传。本读法的身份真源是 bundle 的
        `contract_slot_ref` + `slot_digest`（见方法末尾的 digest 对账），不是文件名。
        传 `child.logical_id` 会额外引入一类「logical_id 与 contract_id 不相等」的
        失败形态 —— 那与「契约读不回来」无关，不该在这里拦。

        🔴 catch `SyncDomainError` 而不是只 catch `ContractError`：`parse_contract` 的
        第一段（`validate_contract_payload`）抛的是 `IdentityError`，它与
        `ContractError` 是**兄弟**（都直接继承 `SyncDomainError`），只 catch 后者会让
        「payload 缺 schema_version」这类失败冒泡成 500。
        但必须**排除**本模块自己的错误类型（否则自己抛的会被自己再包一层）。
        """
        try:
            return parse_contract(payload)
        except FrozenContractReaderError:
            raise
        except SyncDomainError as exc:
            raise FrozenContractUnparsableError(
                f"definition {child.id} 的冻结契约 payload 过不了当前 `parse_contract`: {exc}"
                " —— 契约演化不向后兼容（如实拒绝，不写兼容层）",
                diagnostics={
                    **dict(diagnostics),
                    "logical_id": str(child.logical_id or ""),
                    "parse_error": f"{type(exc).__name__}: {exc}",
                },
            ) from exc


async def read_frozen_contract(
    *, session: AsyncSession, artifacts: Any, bundle: Any
) -> FrozenContractSnapshot:
    """一次性读法（无状态调用的便捷入口）。

    🔴 不要为此在调用方新建 reader 实例后长期持有 —— `FrozenContractReader` 只持有
    session 与仓储两个引用，复用它是安全的；本函数只是省一行。
    """
    return await FrozenContractReader(session=session, artifacts=artifacts).read(
        bundle=bundle
    )
