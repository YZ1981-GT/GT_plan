# -*- coding: utf-8 -*-
"""Task 19：上传 / WOPI / custom / F2 / rollback / 历史恢复 writer 的统一入口装配。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 19
Requirements: 2.2（所有 writer 经统一 `ContentMutationService.commit(...)`）、
2.11（custom 保持 xlsx 单一权威，不得被 JSON projection writer 改写）、
9.11（rollback / 历史版本读取共用 canonical resolver，按 content version + entry +
representation generation 解析，不得解析 candidate）、12.6（custom 接入统一
room/durable ack/状态/evidence）、12.7（F2 专用端点迁到统一协议）
Properties: P50（custom 保持 xlsx 权威且进入统一 representation 协议）/
P61（所有 writer 进入唯一 revision 域）

═══ 一、为什么本模块存在：Task 15 的 lane 已经够了，缺的是「装配」═══

`ContentMutationService.commit(...)` 早就支持权威 OOXML 形态
（`BusinessMutation(authoritative_payload=...)` + `adapter=None`，见
`_stage_authoritative`）。Task 19 迁不动的原因不是缺 lane，而是缺三样**装配件**：

1. **approved definition bundle 从哪来**。`create_representation` 强制 approved 非空
   bundle；而上传 / WOPI / custom 这三条路径都没有 per-entry contract，也不该有
   （Requirement 2.11 / 6.19：不得强行 instrumentation）。它们需要的是
   `custom_authoritative_ooxml` / `opaque_single_onlyoffice` authority model + 三个
   **版本化 typed null marker** 的 bundle —— 由 :class:`OpaqueAuthorityProvisioner`
   幂等发布/复用。
2. **rollback 的源从哪定位**。Requirement 9.11 / 10.6 要求 rollback 只接受该 scope 下
   的 immutable opaque `version_id`；numeric revision 只作显示与乐观锁，禁止当 route/
   scope/resource key。定位与拒绝集中在 :class:`RollbackSourceLocator`。
3. **每条 writer 的调用形状要一样**。24 行清册各自拼一遍 plan 必然漂移，于是
   :class:`AuthoritativeContentWriter` 只暴露两个方法
   （:meth:`commit_bytes` / :meth:`commit_restore`），writer 侧改动就是一次 await。

═══ 二、拒绝分成独立异常类型，不共用 error_code ═══

Task 18 的变异检验实测到一条真实缺陷：两条拒绝共用一个 `error_code` 时，短路掉第一个
`if` 会被第二个接住并抛出**同样的**码，于是第一条判据退化成不可达分支、变异判 GREEN。
本模块因此为 rollback 的每一种非法源各设一个异常类型：

* :class:`RollbackSourceNotFoundError` —— 该 scope 下没有这个 version（404 oracle）；
* :class:`RollbackSourceScopeMismatchError` —— version 存在但属于另一个 wp/project；
* :class:`RollbackSourceIncomingError` —— 源是 incoming（durable 或 quarantined）；
* :class:`RollbackSourceCandidateError` —— 源是 upgrade candidate；
* :class:`RollbackSourceNotPublishedError` —— 源 artifact 不是 published canonical；
* :class:`NumericRevisionIsNotAResourceKeyError` —— 调用方拿 numeric revision 当 key。

前五条各自能被单点变异 falsify；最后一条是 Requirement 10.6 的「numeric revision 禁作
resource_id/route key」的可执行判据 —— 它必须在**任何**数据库查询之前拒绝，否则
「revision 1」在两个 wp 上都存在，第一个查到的就会被当成源。

═══ 三、authority model 的选择由「有没有 HTML 对端」决定，不由调用方随口传 ═══

`custom_authoritative_ooxml` 与 `opaque_single_onlyoffice` 都是「OOXML 本体即权威」，
差别在语义：前者是 custom 底稿（平台生成的 xlsx，有 HTML 投影视图但投影只读），后者是
纯 OO 入口（没有 HTML 对端）。两者都**不得**接 per-entry contract。选错不会造成数据
损坏，但会让 evidence 的 authority model 分桶失真，所以
:data:`OPAQUE_AUTHORITY_MODELS` 把可选集合封闭掉，`projection_contract` 直接拒绝
（:class:`ProjectionAuthorityNotAllowedError`）—— 那条路必须走 Task 15 的
`commit(..., adapter=...)` 全量协议。
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import (
    WorkpaperArtifact,
    WorkpaperContentRepresentation,
    WorkpaperContentVersion,
    WorkpaperRepresentationUpgradeCandidate,
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncDefinitionBundle,
)
from app.services.workpaper_sync.adapters.base import SubstrateRole
from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
from app.services.workpaper_sync.content_mutation import (
    BusinessMutation,
    ContentCommitPlan,
    ContentCommitReceipt,
    ContentMutationError,
    ContentMutationService,
    ContentSource,
    HtmlOnlyCommitPlan,
    HtmlOnlyCommitReceipt,
)
from app.services.workpaper_sync.entry_profile import Capability
from app.services.workpaper_sync.definitions import (
    DefinitionPublisher,
    canonical_json_bytes,
    marker_slot_spec,
)
from app.services.workpaper_sync.models import (
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleSlot,
    DefinitionState,
    SyncDomainError,
    is_digest,
    is_uuid_text,
)
from app.services.workpaper_sync.repository import WorkpaperSyncRepository
from app.services.workpaper_sync.resolution import (
    CanonicalResolutionService,
    DefinitionBundleSnapshot,
)

__all__ = [
    "OPAQUE_AUTHORITY_MODELS",
    "OPAQUE_AUTHORITY_SOURCE_COMMIT",
    "OPAQUE_AUTHORITY_SEMANTIC_VERSION",
    "WriterMigrationError",
    "ProjectionAuthorityNotAllowedError",
    "NumericRevisionIsNotAResourceKeyError",
    "RollbackSourceNotFoundError",
    "RollbackSourceScopeMismatchError",
    "RollbackSourceIncomingError",
    "RollbackSourceCandidateError",
    "RollbackSourceNotPublishedError",
    "OpaqueAuthorityProvisioner",
    "LocatedRollbackSource",
    "RollbackSourceLocator",
    "AuthoritativeContentWriter",
    "build_content_mutation_service_writer",
    "opaque_entry_id",
    "OPAQUE_ENTRY_PREFIX",
    "RESTORE_SHEET_SCOPE",
    "RESTORE_SCHEMA_VERSION_FALLBACK",
]


# ═══════════════════════════════════════════════════════════════════════════
# 0. 常量
# ═══════════════════════════════════════════════════════════════════════════

#: 「OOXML 本体即权威」的两个 authority model。`projection_contract` 不在其中 ——
#: 它必须走 Task 15 的全量协议（materialize → roundtrip 等值 → 未管理区域比对）。
OPAQUE_AUTHORITY_MODELS: tuple[AuthorityModel, ...] = (
    AuthorityModel.custom_authoritative_ooxml,
    AuthorityModel.opaque_single_onlyoffice,
)

#: definition artifact 的 `source_commit`。写成常量而不是字面量散落各处：它进
#: definition row，事后追「这个 authority model 是谁发布的」靠它。
OPAQUE_AUTHORITY_SOURCE_COMMIT: str = "task19-writer-migration"
OPAQUE_AUTHORITY_SEMANTIC_VERSION: str = "1.0.0"

#: authority-model definition 的 canonical payload schema 版本。它进内容寻址 digest，
#: 所以载荷结构变化必须同时 +1。
AUTHORITY_MODEL_SCHEMA_VERSION: str = "authority-model-definition:v1"

#: opaque(非 projection) writer 的 scope entry_id 命名空间。单一声明处，理由与
#: `content_mutation.HTML_ONLY_ENTRY_PREFIX` 完全相同：两处一漂移，同一底稿会落到
#: 两个 scope 下，rollback 与 evidence 就查不到对方的行。
#:
#: 🔴 分隔符是 `-` 而**不是** `:`。`entry_id` 会被
#: `CanonicalArtifactLayout.representation_dir()` 原样当**目录名**用，而 `:` 在
#: Windows 上是非法路径字符 —— Task 19 实测到 `opaque:{uuid}` 直接 `NotADirectoryError`
#: （WinError 267）。html-only lane 用 `:` 没暴露，只因为那条 lane 不发布
#: representation，它的 projection 路径里不含 entry_id。
OPAQUE_ENTRY_PREFIX: str = "opaque-"

#: 整份 projection 恢复（rollback / 历史快照回滚）的 `sheet_name` scope 标记。
#:
#: 🔴 它**不是**一个 sheet 名。`HtmlOnlyCommitPlan` 要求 `sheet_name` 非空，而一次
#: 「把整份 parsed_data / checklist_responses 恢复到某个快照」的写入根本不针对某一个
#: sheet。随便填第一个 sheet 名会让 canonical 载荷谎报作用域（它进内容寻址 digest，
#: 事后无法区分「只恢复了这张表」与「恢复了全部」）。所以这里用一个**显式的 scope
#: 记号**，且只声明一次 —— 两条恢复 writer 共用它，digest 才可比。
RESTORE_SHEET_SCOPE: str = "<whole-projection>"

#: 恢复载荷的 `schema_version` 兜底值。
#:
#: 历史快照store（`wp_migration_snapshots` / `workpaper_snapshots`）成型于本 spec 之前，
#: 行里没有 schema 版本列。凭空写一个当前版本号是造假（会让「这份内容按哪个 schema 解
#: 释」这条事实指向错的 schema），所以显式记成「来自未版本化的历史快照」。
RESTORE_SCHEMA_VERSION_FALLBACK: str = "restore/unversioned-legacy-snapshot"

#: `entry_id` 允许出现的字符。白名单而非黑名单：它同时是**路径片段**，`/` `\` `:`
#: `..` 任何一个漏掉都是目录穿越或不可创建目录。
_ENTRY_ID_SAFE = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)


def opaque_entry_id(*, wp_code: str | None, wp_id: uuid.UUID) -> str:
    """opaque writer 的 scope entry_id（唯一构造处）。

    与 `html_only_entry_id` 同形：优先用稳定业务身份 `wp_code`，缺行退回 `wp_id`
    （V151 的 `ck_wpssi_entry_non_empty` 不接受空串），并截到 VARCHAR(200)。

    额外做一步**路径片段归一**：非白名单字符换成 `_`，并把 `..` 折掉。`entry_id` 在
    `.versions/{wp_id}/representations/{entry_id}/` 里是目录名，wp_code 里出现 `/`
    或 `..` 就是目录穿越（Requirement 9.6）。
    """
    stem = (wp_code or "").strip() or str(wp_id)
    safe = "".join(char if char in _ENTRY_ID_SAFE else "_" for char in stem)
    while ".." in safe:
        safe = safe.replace("..", "._")
    safe = safe.strip("._-") or str(wp_id)
    return f"{OPAQUE_ENTRY_PREFIX}{safe}"[:200]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常：每条拒绝一个类型
# ═══════════════════════════════════════════════════════════════════════════


class WriterMigrationError(SyncDomainError):
    error_code = "writer_migration_failed"


class ProjectionAuthorityNotAllowedError(WriterMigrationError):
    """`projection_contract` 走了 opaque 权威装配（会跳过 roundtrip 等值判据）。"""

    error_code = "projection_authority_requires_full_protocol"


class NumericRevisionIsNotAResourceKeyError(WriterMigrationError):
    """rollback 用 numeric revision 当 resource key（Requirement 10.6 明令禁止）。

    🔴 必须在**任何**数据库查询之前抛。numeric revision 不是全局唯一：两个 wp 都可以
    有 revision=1，先查库再判断等于让「第一个匹配到的」成为回滚源 —— 那是跨 scope
    数据泄露，不只是参数校验问题。
    """

    error_code = "numeric_revision_is_not_a_resource_key"


class RollbackSourceNotFoundError(WriterMigrationError):
    """该 scope 下不存在这个 content version（与「不可见」共用 404 oracle）。"""

    error_code = "rollback_source_not_found"


class RollbackSourceScopeMismatchError(WriterMigrationError):
    """version 存在，但属于另一个 project/wp/entry。

    🔴 与 :class:`RollbackSourceNotFoundError` 分成两类**不是**为了对外暴露差异
    （对外都是 404），而是为了让「跨 scope 组合」这条判据能被独立 falsify：合成一类时
    删掉 scope 比对会被 not-found 分支接住，变异判 GREEN。
    """

    error_code = "rollback_source_scope_mismatch"


class RollbackSourceIncomingError(WriterMigrationError):
    """rollback 源是 incoming artifact（durable 或 quarantined）。

    Requirement 5.6 / Property 65：incoming 永不 published、永不 resolver-visible，
    因此也永远不能当回滚源。durable 与 quarantined 都算 —— 「已耐久」只证明可恢复，
    不证明它被应用过。
    """

    error_code = "rollback_source_is_incoming"


class RollbackSourceCandidateError(WriterMigrationError):
    """rollback 源是 representation upgrade candidate（Requirement 6.18）。"""

    error_code = "rollback_source_is_candidate"


class RollbackSourceNotPublishedError(WriterMigrationError):
    """rollback 源 artifact 不是 published canonical（orphaned/deleted/staging 等）。"""

    error_code = "rollback_source_not_published"


# ═══════════════════════════════════════════════════════════════════════════
# 2. opaque authority bundle 幂等装配
# ═══════════════════════════════════════════════════════════════════════════


def _authority_payload(model: AuthorityModel) -> dict[str, Any]:
    """authority-model definition 的 canonical payload。

    刻意只有两个键：`schema_version` 与 `authority_model`。**不含**自身 UUID/hash
    （Requirement 6.1 / Task 13：contract/definition semantic payload 禁止内嵌自身
    identity，否则同一语义在不同环境算出不同 digest，bundle 就无法跨环境复现）。
    """
    return {
        "schema_version": AUTHORITY_MODEL_SCHEMA_VERSION,
        "authority_model": model.value,
    }


def _marker_slots() -> dict[BundleSlot, Any]:
    """三个 slot 全部使用 registry 版本化 typed null marker。

    opaque authority model 下这是**唯一**合法形态：
    `validate_bundle_slots` 只对 `projection_contract` 要求三 child 均为 approved
    definition；而 SQL NULL / 空串 / 全零 hash 在 canonicalizer、repository validator
    与 V151 trigger 三层都被拒（Requirement 2.3）。
    """
    return {slot: marker_slot_spec(slot) for slot in BundleSlot}


class OpaqueAuthorityProvisioner:
    """opaque authority model 的 approved definition bundle：**解析**与**发布**分成两个方法。

    ═══ 为什么必须拆开（Task 65 改造）═══

    改造前只有一个 `ensure()`：先查复用、查不到就 `publish_bundle(..., approved=True)`。
    它的唯一调用者是 :meth:`AuthoritativeContentWriter.commit_bytes` —— **业务内容写入
    的那一次**。于是「AC 6.19 要求先发布 approved authority-model definition 与 non-null
    approved bundle」这条承诺没有任何可 falsify 的判据：写路径自己给自己发证，任何时刻
    库里都恰好有它需要的 bundle。

    拆开之后：

    * :meth:`resolve` —— **只查**。经 Task 65 的 `OpaqueEntryGate` 跑完五条判据
      （lane 已登记 / authority model 属 opaque / 库里已有 approved 双侧 / 三 slot 全
      registry typed null marker / frozen digest 一致），查不到即
      `OpaqueBundleNotProvisionedError` 并指向唯一 provision 宿主脚本。
      `commit_bytes` 只调这个。
    * :meth:`provision` —— 查+发布。唯一宿主是
      `backend/scripts/fix/fix_task65_provision_opaque_authority_bundles.py`
      （与 Task 76 的 `fix_task76_provision_projection_definitions.py` 同款）。

    两个方法都**不 commit** —— 事务边界属于调用方（与 `WorkpaperSyncRepository` 只
    flush 不 commit 的约定一致），因此 bundle 与随后的 content version/representation
    落在**同一个**业务事务里，Task 15 的单事务见证仍然成立。
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: WorkpaperSyncRepository,
        artifacts: CanonicalArtifactRepository,
        resolution: CanonicalResolutionService,
    ) -> None:
        self._session = session
        self._repo = repository
        self._artifacts = artifacts
        self._resolution = resolution

    async def resolve(self, *, lane_id: str) -> DefinitionBundleSnapshot:
        """按 lane 解析**已发布**的 approved bundle 快照；不发布任何东西。

        🔴 `bundle_id` 取自 gate 的返回值而**不是**本方法自己再查一遍。这让 gate 的五条
        判据无法退化成装饰：把 `gate.resolve_approved_bundle(...)` 这一行删掉，下一行就
        拿不到 `resolved.bundle_id`（NameError），变异必红。若这里改成自己查 id、只把
        gate 当"顺便校验一下"，删掉 gate 调用后本方法照样返回一个 snapshot ⇒ 变异判
        GREEN（本 spec 反复实测的假绿第②源）。
        """
        # 延迟 import：`opaque_entry_gate` 在 import 期要读本模块的
        # `OPAQUE_AUTHORITY_MODELS`（它是那个封闭集的唯一真源）。放在模块顶层会形成
        # 循环 import。
        from app.services.workpaper_sync.opaque_entry_gate import OpaqueEntryGate

        gate = OpaqueEntryGate(session=self._session)
        resolved = await gate.resolve_approved_bundle(lane_id=lane_id)
        return await self._resolution.load_bundle_snapshot(resolved.bundle_id)

    async def provision(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        authority_model: AuthorityModel | str,
    ) -> DefinitionBundleSnapshot:
        """幂等发布某个 opaque authority model 的 approved definition + bundle。

        只应由 `fix_task65_provision_opaque_authority_bundles.py` 调用。业务写入路径调
        :meth:`resolve`。
        """
        model = (
            authority_model
            if isinstance(authority_model, AuthorityModel)
            else AuthorityModel(authority_model)
        )
        if model not in OPAQUE_AUTHORITY_MODELS:
            raise ProjectionAuthorityNotAllowedError(
                f"authority model={model.value} 不是 OOXML 本体权威形态 —— "
                "projection-based entry 必须走 ContentMutationService.commit(..., adapter=...) "
                "的全量协议（materialize → roundtrip 等值 → 未管理区域比对），"
                "不得用 opaque 装配跳过（Requirement 2.3 / 3.3）"
            )

        existing = await self._find_approved_bundle(model)
        if existing is not None:
            return await self._resolution.load_bundle_snapshot(existing)

        publisher = DefinitionPublisher(
            artifacts=self._artifacts,
            repository=self._repo,
            project_id=project_id,
            wp_id=wp_id,
            source_commit=OPAQUE_AUTHORITY_SOURCE_COMMIT,
        )
        authority = await publisher.publish_definition(
            kind="authority_model",
            payload=_authority_payload(model),
            logical_id=f"authority.{model.value}",
            semantic_version=OPAQUE_AUTHORITY_SEMANTIC_VERSION,
            approved=True,
        )
        bundle = await publisher.publish_bundle(
            authority_model_definition_id=authority.definition_id,
            authority_model=model,
            authority_model_definition_sha256=authority.sha256,
            slots=_marker_slots(),
            approved=True,
        )
        return await self._resolution.load_bundle_snapshot(bundle.bundle_id)

    async def _find_approved_bundle(self, model: AuthorityModel) -> uuid.UUID | None:
        """找一个可复用的 approved bundle。

        判据逐项落在**列**上（authority model 枚举 + 两侧 approved + 三个 slot 的
        marker type/digest 与当前 registry 等值），不是「按 logical_id 猜」：marker
        registry 换版本后旧 bundle 的 digest 不再等值，于是自动重新发布而不是复用一个
        身份已漂移的 bundle（Requirement 9.8）。

        `ORDER BY created_at, id` 让并发下即使产生两个等价 bundle，后续调用也收敛到
        同一个 —— 两者 canonical payload 逐字节相同，故不构成第二权威。
        """
        slots = _marker_slots()
        query = (
            sa.select(WorkpaperSyncDefinitionBundle.id)
            .join(
                WorkpaperSyncDefinitionArtifact,
                WorkpaperSyncDefinitionArtifact.id
                == WorkpaperSyncDefinitionBundle.authority_model_definition_id,
            )
            .where(
                WorkpaperSyncDefinitionArtifact.authority_model_type == model.value,
                WorkpaperSyncDefinitionArtifact.state == DefinitionState.approved.value,
                WorkpaperSyncDefinitionBundle.state == DefinitionState.approved.value,
                WorkpaperSyncDefinitionBundle.template_slot_type
                == slots[BundleSlot.template].slot_type,
                WorkpaperSyncDefinitionBundle.template_slot_digest
                == slots[BundleSlot.template].slot_digest,
                WorkpaperSyncDefinitionBundle.instrumentation_slot_type
                == slots[BundleSlot.instrumentation].slot_type,
                WorkpaperSyncDefinitionBundle.instrumentation_slot_digest
                == slots[BundleSlot.instrumentation].slot_digest,
                WorkpaperSyncDefinitionBundle.contract_slot_type
                == slots[BundleSlot.contract].slot_type,
                WorkpaperSyncDefinitionBundle.contract_slot_digest
                == slots[BundleSlot.contract].slot_digest,
            )
            .order_by(
                WorkpaperSyncDefinitionBundle.created_at,
                WorkpaperSyncDefinitionBundle.id,
            )
            .limit(1)
        )
        return (await self._session.execute(query)).scalars().first()


# ═══════════════════════════════════════════════════════════════════════════
# 3. rollback 源定位
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class LocatedRollbackSource:
    """一次合法 rollback 源的完整身份（全部来自 DB 列，无一项现算）。"""

    version_id: uuid.UUID
    revision: int
    entry_id: str
    representation_id: uuid.UUID
    representation_generation: int
    document_type: str
    artifact_id: uuid.UUID
    artifact_sha256: str
    artifact_relative_path: str
    artifact_path: Path
    definition_bundle_id: uuid.UUID
    payload: bytes

    def as_dict(self) -> dict[str, Any]:
        return {
            "version_id": str(self.version_id),
            "revision": self.revision,
            "entry_id": self.entry_id,
            "representation_id": str(self.representation_id),
            "representation_generation": self.representation_generation,
            "document_type": self.document_type,
            "artifact_sha256": self.artifact_sha256,
            "definition_bundle_id": str(self.definition_bundle_id),
            "payload_bytes": len(self.payload),
        }


class RollbackSourceLocator:
    """按 immutable opaque `version_id` 定位一个**已发布**的回滚源。

    顺序即语义，每一步在下一步之前失败：

    1. resource key 形态（numeric revision 立刻拒绝，**在查库之前**）；
    2. content version 存在性（该 scope 下）；
    3. scope 归属（project/wp 逐项比对）；
    4. representation 定位（entry + 该 version 下最新 generation）；
    5. artifact 准入（candidate / incoming / 非 published 各自一个拒绝）；
    6. 读字节（内容寻址校验 digest —— 磁盘上的东西必须与 DB 说的一致）。

    第 5 步的三条拒绝顺序刻意固定为 candidate → incoming → not-published：前两条是
    **语义**禁令（这类 artifact 永远不能当源），第三条是**状态**禁令（这一个碰巧还没
    发布/已 orphan）。反过来排会让语义禁令被状态禁令遮蔽成不可达分支。
    """

    def __init__(
        self, *, session: AsyncSession, artifacts: CanonicalArtifactRepository
    ) -> None:
        self._session = session
        self._artifacts = artifacts

    async def locate(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        version_id: Any,
    ) -> LocatedRollbackSource:
        resolved_version_id = self._coerce_version_id(version_id)

        version = (
            await self._session.execute(
                sa.select(WorkpaperContentVersion).where(
                    WorkpaperContentVersion.id == resolved_version_id
                )
            )
        ).scalar_one_or_none()
        if version is None:
            raise RollbackSourceNotFoundError(
                f"content version {resolved_version_id} 不存在 —— rollback 只接受本 scope 下的 "
                "immutable opaque version_id（Requirement 10.6）"
            )
        if version.wp_id != wp_id:
            raise RollbackSourceScopeMismatchError(
                f"content version {resolved_version_id} 属于 wp {version.wp_id}，"
                f"请求 scope 是 wp {wp_id} —— 跨 scope 组合必须失败且与不存在同一 oracle"
            )

        representation = await self._locate_representation(
            wp_id=wp_id, entry_id=entry_id, version_id=resolved_version_id
        )
        artifact = await self._assert_artifact_publishable(
            representation.artifact_id, version_id=resolved_version_id
        )
        payload = self._read_verified_bytes(artifact)

        return LocatedRollbackSource(
            version_id=resolved_version_id,
            revision=int(version.revision),
            entry_id=representation.entry_id,
            representation_id=representation.id,
            representation_generation=int(representation.generation),
            document_type=representation.document_type,
            artifact_id=artifact.id,
            artifact_sha256=artifact.sha256,
            artifact_relative_path=artifact.relative_path,
            artifact_path=self._artifacts.resolve_relative_path(artifact.relative_path),
            definition_bundle_id=representation.definition_bundle_id,
            payload=payload,
        )

    @staticmethod
    def _coerce_version_id(value: Any) -> uuid.UUID:
        """把调用方给的 resource key 归一成 UUID，numeric revision 立刻拒绝。

        `bool` 先判：`isinstance(True, int)` 为真，不先排掉的话 `rollback(version_id=True)`
        会走进 numeric 分支报一句看不懂的话。
        """
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, bool) or isinstance(value, int):
            raise NumericRevisionIsNotAResourceKeyError(
                f"rollback 收到 numeric resource key {value!r} —— numeric revision 只用于显示与"
                "乐观锁，两个 wp 都可以有 revision=1，拿它当 key 会回滚到别人的版本"
                "（Requirement 10.6）"
            )
        text = str(value).strip()
        if not is_uuid_text(text):
            raise NumericRevisionIsNotAResourceKeyError(
                f"rollback 的 version_id 必须是 immutable opaque UUID，实得 {value!r}"
            )
        return uuid.UUID(text)

    async def _locate_representation(
        self, *, wp_id: uuid.UUID, entry_id: str, version_id: uuid.UUID
    ) -> WorkpaperContentRepresentation:
        row = (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation)
                .where(
                    WorkpaperContentRepresentation.wp_id == wp_id,
                    WorkpaperContentRepresentation.entry_id == entry_id,
                    WorkpaperContentRepresentation.content_version_id == version_id,
                )
                .order_by(WorkpaperContentRepresentation.generation.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise RollbackSourceNotFoundError(
                f"content version {version_id} 在 entry {entry_id!r} 下没有 published "
                "representation —— 只有已发布过 OOXML 的版本才能作回滚源"
            )
        return row

    async def _assert_artifact_publishable(
        self, artifact_id: uuid.UUID, *, version_id: uuid.UUID
    ) -> WorkpaperArtifact:
        artifact = (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(WorkpaperArtifact.id == artifact_id)
            )
        ).scalar_one_or_none()
        if artifact is None:
            raise RollbackSourceNotFoundError(
                f"representation 的 artifact {artifact_id} 行不存在（version {version_id}）"
            )

        candidate_hit = (
            await self._session.execute(
                sa.select(sa.func.count())
                .select_from(WorkpaperRepresentationUpgradeCandidate)
                .where(
                    WorkpaperRepresentationUpgradeCandidate.staged_artifact_id == artifact.id
                )
            )
        ).scalar_one()
        if (
            artifact.kind == ArtifactKind.upgrade_candidate.value
            or artifact.state == ArtifactState.candidate.value
            or int(candidate_hit or 0)
        ):
            raise RollbackSourceCandidateError(
                f"artifact {artifact.id} 是 representation upgrade candidate "
                f"(kind={artifact.kind} state={artifact.state} candidate_rows={candidate_hit}) —— "
                "candidate 永不进 resolver/room/current pointer/evidence，也不能当回滚源"
                "（Requirement 6.18）"
            )
        if artifact.kind == ArtifactKind.incoming.value:
            raise RollbackSourceIncomingError(
                f"artifact {artifact.id} 是 incoming（state={artifact.state}）—— "
                "incoming 永不 published、永不 resolver-visible，durable 只证明可恢复，"
                "不证明它曾被应用（Requirement 5.6 / Property 65）"
            )
        if (
            artifact.kind != ArtifactKind.canonical.value
            or artifact.state != ArtifactState.published.value
            or artifact.deleted_at is not None
        ):
            raise RollbackSourceNotPublishedError(
                f"artifact {artifact.id} 不是 published canonical"
                f"（kind={artifact.kind} state={artifact.state} deleted_at={artifact.deleted_at}）"
            )
        return artifact

    def _read_verified_bytes(self, artifact: WorkpaperArtifact) -> bytes:
        """读源字节并逐字节校验 digest。

        DB 说的 sha256 与磁盘实际内容不符时**必须**失败而不是照搬：那说明 artifact 已被
        改写或替换，内容寻址的不可变承诺已经破了，把它当回滚源等于把损坏内容发布成新
        版本。
        """
        path = self._artifacts.resolve_relative_path(artifact.relative_path)
        payload = path.read_bytes()
        actual = hashlib.sha256(payload).hexdigest()
        if not is_digest(artifact.sha256) or actual != artifact.sha256:
            raise RollbackSourceNotPublishedError(
                f"artifact {artifact.id} 磁盘内容 digest={actual} 与登记的 "
                f"{artifact.sha256!r} 不符 —— 内容寻址不可变承诺已破，不得作为回滚源"
            )
        return payload


# ═══════════════════════════════════════════════════════════════════════════
# 4. 统一 writer 装配
# ═══════════════════════════════════════════════════════════════════════════


class AuthoritativeContentWriter:
    """上传 / WOPI / custom / F2 / rollback / 历史恢复 writer 的**唯一**调用面。

    它自己不写任何一行、不 commit、不递增任何计数器 —— 只把调用方给的权威字节装配成
    `ContentCommitPlan` + `BusinessMutation` 并交给
    :meth:`ContentMutationService.commit`。因此「每个 writer 经统一入口提交」这条承诺
    在**调用点**就可断言（writer 里只有一次 await，没有 revision 赋值、没有 commit）。
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        mutation: ContentMutationService,
        repository: WorkpaperSyncRepository,
        provisioner: OpaqueAuthorityProvisioner,
        locator: RollbackSourceLocator,
    ) -> None:
        self._session = session
        self._mutation = mutation
        self._repo = repository
        self._provisioner = provisioner
        self._locator = locator

    @property
    def mutation_service(self) -> ContentMutationService:
        return self._mutation

    async def current_revision(self, wp_id: uuid.UUID) -> int:
        """读当前 business content revision（**不推进**、不加 advisory lock）。

        writer 的「早失败 + 给用户可读冲突信息」用它；真正的并发裁决是
        `commit()` 事务内的 CAS。两者缺一不可（与 `wp_html_save` 的 Step 2b 同形）。
        """
        row = (
            await self._session.execute(
                sa.text(
                    "SELECT COALESCE(content_revision, 0) FROM working_paper WHERE id = :wp"
                ),
                {"wp": str(wp_id)},
            )
        ).scalar_one_or_none()
        return int(row or 0)

    async def commit_bytes(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        source: ContentSource | str,
        payload: bytes,
        document_type: str,
        expected_revision: int,
        substrate_path: Path,
        lane_id: str,
        actor_id: uuid.UUID | None = None,
        adapter_id: str = "opaque.authoritative.v1",
        parent_version_id: uuid.UUID | None = None,
        operation_id: uuid.UUID | None = None,
        reason: str = "content_commit",
        idempotency_key: str | None = None,
    ) -> ContentCommitReceipt:
        """把权威 OOXML 字节提交成一个新 content version + published representation。

        `payload` 就是权威本体，**原样**落盘（Requirement 2.11：custom 底稿不得被标准
        结构化 JSON projection writer 改写）。`_stage_authoritative` 用它自身的 digest
        当 `structure_hash` / `identity_inventory_sha256` —— 既不强行 instrumentation，
        也不留空/全零 hash（Requirement 6.19）。

        🔴 `lane_id` 取代了原先的 `authority_model` 参数（Task 65）。原签名是
        `authority_model: AuthorityModel | str = AuthorityModel.custom_authoritative_ooxml`
        —— 一个**有默认值**的身份参数：user-upload 的 opaque 文件漏传即静默落成
        `custom_authoritative_ooxml`，四层静态检查（Volar / vitest / `get_diagnostics` /
        HEAD-swap）全都查不出，只有事后翻 evidence 的 authority model 分桶才会发现分桶
        失真。现在 authority model 由 lane 登记单向决定
        （`opaque_entry_gate.authority_model_for_lane`），调用方**无法**传一个与自己 lane
        不符的 authority model —— 那条参数已经不存在了。
        """
        if not payload:
            raise WriterMigrationError(
                "权威 OOXML 载荷为空 —— 空字节的 digest 是一个合法但毫无意义的身份，"
                "会让 representation 指向一个打不开的文件（Requirement 2.3）"
            )
        bundle = await self._provisioner.resolve(lane_id=lane_id)
        plan = ContentCommitPlan(
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            source=source if isinstance(source, ContentSource) else ContentSource(source),
            expected_revision=expected_revision,
            bundle=bundle,
            adapter_id=adapter_id,
            adapter_build_digest=_adapter_build_digest(adapter_id),
            document_type=document_type,
            substrate_path=substrate_path,
            substrate_role=SubstrateRole.published_representation,
            substrate_kind=ArtifactKind.canonical,
            substrate_state=ArtifactState.published,
            actor_id=actor_id,
            operation_id=operation_id,
            parent_version_id=parent_version_id,
            # 🔴 contract 恒为 None：opaque authority model 携带 per-entry contract 会被
            #    `_assert_authority_shape` 拒（Requirement 2.11）。写死在这里而不是
            #    透传参数，是为了让「custom 不得转 JSON 三方 projection」在**装配层**
            #    就不可表达。
            contract=None,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        return await self._mutation.commit(
            plan=plan,
            mutation=BusinessMutation(authoritative_payload=payload),
            adapter=None,
        )

    async def commit_restore(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        version_id: Any,
        expected_revision: int,
        lane_id: str,
        actor_id: uuid.UUID | None = None,
    ) -> tuple[LocatedRollbackSource, ContentCommitReceipt]:
        """按 immutable opaque `version_id` 回滚：产生**新**版本，不改写旧行。

        Requirement 8.9 / 9.7：rollback 是 forward-only 的 —— 它把旧内容作为**新**
        content version + **新** published representation 发布出来，旧 version/
        representation 一个字节都不动。因此「回滚过头了」还能再回滚回去，且 timeline
        完整保留（不可变审计轨迹）。
        """
        located = await self._locator.locate(
            project_id=project_id, wp_id=wp_id, entry_id=entry_id, version_id=version_id
        )
        receipt = await self.commit_bytes(
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            source=ContentSource("rollback"),
            payload=located.payload,
            document_type=located.document_type,
            expected_revision=expected_revision,
            substrate_path=located.artifact_path,
            lane_id=lane_id,
            actor_id=actor_id,
            parent_version_id=located.version_id,
            reason="rollback",
        )
        return located, receipt

    async def commit_projection(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        capability: Capability | str,
        html_data: Mapping[str, Any],
        expected_revision: int,
        source: ContentSource | str = ContentSource("rollback"),
        sheet_name: str = RESTORE_SHEET_SCOPE,
        schema_version: str = RESTORE_SCHEMA_VERSION_FALLBACK,
        actor_id: uuid.UUID | None = None,
        parent_version_id: uuid.UUID | None = None,
        trigger: str = "content_restore",
    ) -> HtmlOnlyCommitReceipt:
        """把一份**结构化 projection**（无 OOXML 本体）提交成一次业务 revision。

        这是 Task 15 另一条 lane 的装配面：`stage_html_projection()`（文件先耐久）→
        `commit_html_projection()`（一次 DB 事务 + 唯一一次 commit）。它与
        :meth:`commit_bytes` 的必需步骤集合**互斥** —— 这条没有 `representation` 与
        `entry_pointer`，那条没有 `current_pointer`；因此谁也无法借另一条的完整性检查
        蒙混过关，也不存在「跳过 representation」的开关。

        `capability` **必须由调用方声明、不在这里写死**。写死等于把
        `HtmlOnlyCommitPlan.__post_init__` 那道拒绝变成不可达分支（Task 18 实测过的真实
        缺陷形态：判据存在但永远走不到）。两道拒绝各有独立来源：

        * 声明侧 —— `single_onlyoffice` / `custom` / `bidirectional` 立即抛；
        * 数据库事实侧 —— `commit_html_projection` 查该 entry 是否已有 representation
          pointer。一旦这个底稿真的接上 OO 发布过 representation，恢复它的 JSON 投影就
          是背着权威 OOXML 改内容（Requirement 2.11），必须 fail closed。

        调用方**必须**已在同一 session 里写完业务行（`parsed_data` /
        `checklist_responses`）且**不得**自己 commit —— 本方法是那笔事务的唯一提交出口。
        """
        plan = HtmlOnlyCommitPlan(
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            expected_revision=expected_revision,
            capability=capability if isinstance(capability, Capability) else Capability(capability),
            sheet_name=sheet_name,
            schema_version=schema_version,
            actor_id=actor_id,
            parent_version_id=parent_version_id,
            trigger=trigger,
            source=source if isinstance(source, ContentSource) else ContentSource(source),
        )
        staged = self._mutation.stage_html_projection(plan=plan, html_data=html_data)
        return await self._mutation.commit_html_projection(plan=plan, staged=staged)

    async def publish_committed_events(
        self, receipt: ContentCommitReceipt | HtmlOnlyCommitReceipt
    ) -> Mapping[str, Any]:
        """提交后发布耐久事件（必须在 commit 之后 —— Requirement 13.1 / Property 52）。"""
        return await self._mutation.publish_committed_events(receipt)


def _adapter_build_digest(adapter_id: str) -> str:
    """opaque 路径的 adapter build digest。

    opaque writer 没有真正的 adapter（没有 materialize/extract），但
    `working_paper_content_representation.adapter_build_digest` 是 NOT NULL 且必须是
    合法 digest。这里用 `adapter_id` 的 sha256 作为**稳定**身份：同一个装配版本恒等，
    改名即变 —— 比填全零 hash（伪身份，Requirement 2.3 明令禁止）诚实。
    """
    return hashlib.sha256(adapter_id.encode("utf-8")).hexdigest()


def build_content_mutation_service_writer(session: AsyncSession) -> AuthoritativeContentWriter:
    """给 opaque writer 路径装配整条链。

    与 `build_html_content_mutation_service` 同理由做成函数而不是模块级单例：
    `session` 是 per-request 的，单例会让第一个请求的事务边界被后续请求复用。
    """
    from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT

    artifacts = CanonicalArtifactRepository(BACKEND_ROOT)
    repository = WorkpaperSyncRepository(session)
    resolution = CanonicalResolutionService(session, artifacts)
    mutation = ContentMutationService(
        session=session,
        repository=repository,
        artifacts=artifacts,
        resolution=resolution,
    )
    return AuthoritativeContentWriter(
        session=session,
        mutation=mutation,
        repository=repository,
        provisioner=OpaqueAuthorityProvisioner(
            session=session,
            repository=repository,
            artifacts=artifacts,
            resolution=resolution,
        ),
        locator=RollbackSourceLocator(session=session, artifacts=artifacts),
    )
