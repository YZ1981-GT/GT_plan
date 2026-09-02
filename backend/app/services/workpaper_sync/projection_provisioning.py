# -*- coding: utf-8 -*-
"""生产侧 `projection_contract` definition 链 provisioner 与 candidate 受控 attach 入口。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 4 Task 76
Requirements: 2.1, 2.3, 2.4, 3.3, 3.4, 3.6, 6.2, 6.10, 6.18, 12.1
Properties: **P4 / P5 / P10 / P28 / P67**

═══ 为什么 projection 侧必须自建 provisioner ═══

`writer_migration.OpaqueAuthorityProvisioner.ensure()` 已经能幂等地拿到一个 approved
bundle，但它对非 opaque authority model **显式抛**
:class:`~app.services.workpaper_sync.writer_migration.ProjectionAuthorityNotAllowedError`
—— 因为它给三个 typed slot 全填 registry 版本化 typed null marker，而
`projection_contract` 标准入口要求三 child 全是 approved definition（AC 2.3 / 3.3）。
放宽那个 guard 去复用 opaque 通道，等于让标准 Excel entry 拿到一个「没有 contract 的
bundle」，AC 3.3 的「缺任一 approved child 时不得降级为 contract-less 模式」当场失守。
故本模块自建一条链，**不动** opaque 通道一个字节。

═══ 本模块拥有哪几段、不拥有哪一段 ═══

======================  ==========================================================
阶段                    归属
======================  ==========================================================
template                本模块（经该 entry 自己的 `publish_pilot_definitions`）
instrumentation         本模块（同上）
contract                本模块（同上）
bundle                  本模块（同上）
representation          **不是**本模块 —— 见下
======================  ==========================================================

`representation` 阶段刻意**不**由本模块插行。平台已有两个受管写入面：

* 业务内容首版 → `ContentMutationService.commit(...)`（唯一能推进 `content_revision`
  的业务事务）；
* 纯 definitions 升级 → `RepresentationService.finalize_candidate(...)`（其仓储被
  `RevisionLockedRepository` 包住，拿不到 revision 域写入面），出口是 Task 25 的
  `finalize_definition_upgrade`，门是 Task 36 的 `ExcelEntryFinalizeGate`。

本模块若自己插 representation 行，就是**第三条**写入路径：既要凭空造一份业务
projection（AC 2.3 明令 content version 只由「已应用业务内容变更」产生），又绕开
`assert_candidate_finalizable` 的五条前置 —— Property 4 与 Property 67 都要打红。
因此本模块在 `representation` 阶段只做三件事，一件不多：

1. `assert_publish_order(stage=representation, ...)` —— 证明 DAG 前四段真的 approved；
2. 若该 entry 已有 current published representation 且绑定的正是本次 bundle ⇒ 记
   `reused_current`（幂等重跑走这条）；
3. 若存在 `state=awaiting_contract` 的 candidate ⇒ 经
   :class:`CandidateDefinitionAttachService` 把 approved contract/bundle 绑上去，
   candidate 进 `ready`，**Task 36 的门随后即可 finalize**。

三条都不成立时给**显式原因**并点名归属者，不静默、不伪造（AC 5.12 的 fail-open 禁令
在本模块同样生效：没有一个 `except Exception`）。

═══ 五种伪造供给各有一条 fail-closed 判据 ═══

判据一律**委托单点**，本模块只补单点拿不到的两条 —— 复制一份的后果不是「更安全」，
而是任一侧被短路都不改变行为 ⇒ 变异检验判 GREEN（本 spec 反复实测过）：

==============================  =========================================================
伪造形态                        判据落点
==============================  =========================================================
① 自造 uuid 或 digest           :func:`assert_projection_supply_authentic` 的 DB 现读 +
                                `models.validate_definition_child`（**本模块补**：把
                                `repository.assert_bundle_usable` 的 post-insert 判据
                                提到 **publish 之前**，于是伪造身份根本不落库）
② marker 冒充 contract          `models.validate_bundle_slots` 的 `projection_contract`
                                分支（委托）
③ 空串 / 全零 hash              `definitions._normalize_slot_input` +
                                `models.validate_bundle_slot`（委托）
④ slot omission / SQL NULL      `definitions.normalize_bundle_slot_map`（委托）
⑤ generator 候选冒充已审契约    :func:`assert_projection_supply_authentic` 的
                                `review_status` + 交付登记表双向核对（**本模块补**：
                                `definitions.validate_contract_payload` **不看**
                                `review_status`，故直接把 generator 候选喂给
                                `DefinitionPublisher` 今天是可行的 —— 这就是那一格）
==============================  =========================================================

全部错误都是 :class:`~app.services.workpaper_sync.models.BundleIntegrityError` 的子类
或它本身，且消息里点出**首个**非法 slot（`BundleSlot` 枚举序即「首个」的定义）。

═══ 不变式（失败只留不可见 candidate/orphan）═══

* 不递增 `content_revision`：`ensure()` 前后各读一次并断言逐值相等，不等即
  :class:`ContentRevisionDriftError`（不是文档承诺，是可观察事实）；
* 不改写既有 content version / representation row：本模块一行 UPDATE 都不发给这两张表
  （V151 的 `trg_wpcv_immutable` / `trg_wpcr_immutable` 也会拒）；
* 不切 entry pointer：本模块不调 `set_entry_pointer`；
* 不 commit：事务边界属于调用方（与 `WorkpaperSyncRepository` 只 flush 不 commit 一致）。
"""

from __future__ import annotations

import importlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa

from app.models.workpaper_sync_models import (
    WorkpaperContentRepresentation,
    WorkpaperRepresentationUpgradeCandidate,
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncDefinitionBundle,
    WorkpaperSyncEntryState,
)
from app.services.workpaper_sync.definitions import (
    DefinitionPublisher,
    PublishedBundle,
    PublishedDefinition,
    PublishStage,
    assert_publish_order,
    bundle_canonical_digest,
    canonical_digest,
    definition_slot_spec,
    normalize_bundle_slot_map,
    validate_definition_payload,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleIntegrityError,
    BundleSlot,
    BundleSlotSpec,
    CandidateState,
    DefinitionKind,
    DefinitionState,
    SyncDomainError,
    validate_bundle_slots,
    validate_definition_child,
)

# ═══════════════════════════════════════════════════════════════════════════
# 0. 常量
# ═══════════════════════════════════════════════════════════════════════════

#: 本 provisioner 发布的 definition 的 `source_commit` 标记（与
#: `writer_migration.OPAQUE_AUTHORITY_SOURCE_COMMIT` 同款：一个任务一个稳定标记，
#: 便于按来源分桶审计）。
PROJECTION_PROVISION_SOURCE_COMMIT: str = "task76-projection-provisioning"

#: `representation` 阶段的四种结局（封闭词表 —— 自由文本会让守卫只能比字符串）。
REPRESENTATION_SETTLEMENT_STATES: tuple[str, ...] = (
    "reused_current",
    "reused_candidate",
    "attached_candidate",
    "blocked",
)

#: Task 76 正文点名的四张供给表（守卫按它现算行数变化，不写第二份清单）。
SUPPLY_TABLES: tuple[str, ...] = (
    "working_paper_sync_definition_artifact",
    "working_paper_sync_definition_bundle",
    "working_paper_representation_upgrade_candidate",
    "working_paper_content_representation",
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 错误
# ═══════════════════════════════════════════════════════════════════════════


class ProjectionProvisioningError(SyncDomainError):
    """provisioner / attach 的基类。"""

    error_code = "projection_provisioning_failed"


class ProjectionEntryNotReviewedError(BundleIntegrityError):
    """⑤ 该 entry 没有已人工审核的 per-entry 生产契约（或 contract_id 不符）。

    刻意继承 :class:`BundleIntegrityError` 而不是
    :class:`ProjectionProvisioningError`：调用方对 bundle 供给不足的 fail-closed 分支
    已经在接 `BundleIntegrityError`，另起一支会让「缺 approved child」这条既有分支漏掉
    本形态（AC 3.3 要求同一类拒绝走同一条可见路径）。
    """

    error_code = "projection_contract_not_reviewed"


class ForgedDefinitionIdentityError(BundleIntegrityError):
    """① slot 引用的 definition 在库里不存在，或 kind/state/digest 与声明不符。"""

    error_code = "projection_supply_forged_identity"


class ProjectionAuthorityModelMismatchError(BundleIntegrityError):
    """authority model 不是 `projection_contract` —— 本 provisioner 无权处理。"""

    error_code = "projection_provisioner_authority_mismatch"


class ProviderModuleNotAllowedError(ProjectionProvisioningError):
    """provider 模块不在 registry 的白名单里（禁从登记表任意 import）。"""

    error_code = "projection_provider_module_not_allowed"


class ContentRevisionDriftError(ProjectionProvisioningError):
    """provisioner / attach 期间 `content_revision` 变了（Property 4 的可观察判据）。"""

    error_code = "projection_provisioning_bumped_revision"


class CandidateAttachError(ProjectionProvisioningError):
    """candidate 受控 attach 被拒。"""

    error_code = "candidate_attach_refused"


class CandidateScopeMismatchError(CandidateAttachError):
    """candidate 属于另一个 wp / entry —— 禁跨 entry 复用 contract/bundle/candidate。"""

    error_code = "candidate_attach_scope_mismatch"


class CandidateNotAwaitingContractError(CandidateAttachError):
    """candidate 不在 `awaiting_contract`（含已 finalize）—— 不得改写。"""

    error_code = "candidate_attach_state_not_awaiting_contract"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 供给来源（交付登记表 + 该 entry 自己的 provider 模块）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProjectionSupply:
    """一个 entry 的**已人工审核**生产供给来源。

    `provider` 是该 entry **自己**的 pilot 模块 —— 一 entry 一 provider，不共用：
    复用另一个 entry 的 provider 就等于复用它的 contract/bundle/candidate
    （Tasks 40~57 正文明令禁止）。
    """

    entry_id: str
    contract_id: str
    provider_module: str
    authority_model: AuthorityModel
    provider: Any

    @property
    def contract(self) -> Any:
        """磁盘契约 ↔ 模块现算 payload **双向**锁死后的 :class:`SyncContract`。

        走 provider 自己的 `assert_contract_file_matches_source()`（内部经
        `contracts.parse_contract`，那是 `review_status != reviewed` 的单点拒绝处），
        本模块**不**重写一份解析。
        """
        return self.provider.assert_contract_file_matches_source()


def load_projection_supply(entry_id: str) -> ProjectionSupply:
    """按 entry 定位其已交付的 per-entry 生产供给；未交付即 fail closed。

    两份真源都不复制：
    * 「哪些 entry 有已审核契约」= `registry.DELIVERED_PER_ENTRY_CONTRACTS`；
    * 「允许 import 哪些 provider」= `registry._ALLOWED_PROVIDER_MODULES`（白名单）。
    """
    from app.services.workpaper_sync.adapters import registry as registry_module

    rows = [
        row
        for row in registry_module.DELIVERED_PER_ENTRY_CONTRACTS
        if str(row.get("entry_id") or "").strip() == entry_id
    ]
    if not rows:
        raise ProjectionEntryNotReviewedError(
            f"entry {entry_id!r} 不在 `DELIVERED_PER_ENTRY_CONTRACTS` 里 —— "
            "contract slot 无已人工审核的 per-entry 生产契约可发布；generator 只产 "
            "`review_status=candidate` 的骨架，把它当已审契约发布是伪造供给"
            "（首个非法 slot: contract）"
        )
    if len(rows) > 1:
        raise ProjectionEntryNotReviewedError(
            f"entry {entry_id!r} 在交付登记表里出现 {len(rows)} 次 —— 一个独立 entry 只能"
            "有唯一 per-entry 契约（首个非法 slot: contract）"
        )
    row = rows[0]
    module_path = str(row.get("provider_module") or "").strip()
    if module_path not in registry_module._ALLOWED_PROVIDER_MODULES:
        raise ProviderModuleNotAllowedError(
            f"entry {entry_id}: provider_module {module_path!r} 不在白名单 "
            f"{sorted(registry_module._ALLOWED_PROVIDER_MODULES)} 内 —— "
            "不得从登记表任意 import"
        )
    authority_model = AuthorityModel(str(row.get("authority_model") or ""))
    if authority_model is not AuthorityModel.projection_contract:
        raise ProjectionAuthorityModelMismatchError(
            f"entry {entry_id} 的 authority model={authority_model.value} 不是 "
            "`projection_contract` —— OOXML 本体权威形态走 "
            "`writer_migration.OpaqueAuthorityProvisioner`，本 provisioner 无权处理"
            "（两条通道的 typed slot 规则相反，混用即 AC 2.3 失守）"
        )
    provider = importlib.import_module(module_path)
    for name in ("publish_pilot_definitions", "assert_contract_file_matches_source"):
        if not callable(getattr(provider, name, None)):
            raise ProviderModuleNotAllowedError(
                f"entry {entry_id}: provider {module_path} 没有可调用的 {name!r} —— "
                "provider 是空壳"
            )
    return ProjectionSupply(
        entry_id=entry_id,
        contract_id=str(row.get("contract_id") or ""),
        provider_module=module_path,
        authority_model=authority_model,
        provider=provider,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 五种伪造供给的 fail-closed 判据
# ═══════════════════════════════════════════════════════════════════════════


async def assert_projection_supply_authentic(
    *,
    session: Any,
    entry_id: str,
    authority_model: AuthorityModel | str,
    authority_model_definition_sha256: str,
    slots: Mapping[Any, Any],
    contract_payload: Mapping[str, Any],
) -> dict[BundleSlot, BundleSlotSpec]:
    """把五种伪造供给全部挡在 bundle 落库**之前**，并指出首个非法 slot。

    返回归一化后的 slot map（调用方拿它去 `publish_bundle`，因此本函数不是可跳过的
    装饰 —— 跳过它就拿不到 slot map）。

    顺序即「第一个原因」：`BundleSlot` 枚举序（template → instrumentation → contract）
    决定「首个非法 slot」，形态判据先于身份判据 —— 反过来时一个空串 digest 会先被
    「库里查不到 definition」接住，错误码指向伪造 uuid 而真正原因是空串（AC 6.10 要求
    错误指向真正的第一个原因）。
    """
    # ── 通道归属：本函数只受理 `projection_contract` ────────────────────────
    #    `validate_bundle_slots` 对 opaque/custom 形态**允许** typed null marker，因此
    #    把 opaque authority 喂进来时它不会拒 ⇒ 本模块的「两条通道不得混用」就退化成
    #    「调用顺序恰好经过 `load_projection_supply`」这种偶然性。这里做成结构判据。
    model = (
        authority_model
        if isinstance(authority_model, AuthorityModel)
        else AuthorityModel(str(authority_model))
    )
    if model is not AuthorityModel.projection_contract:
        raise ProjectionAuthorityModelMismatchError(
            f"entry {entry_id}: authority model={model.value} 不是 `projection_contract` "
            "—— OOXML 本体权威形态走 `writer_migration.OpaqueAuthorityProvisioner`，"
            "本判据函数无权受理（首个非法 slot: authority_model）"
        )

    # ── ③ 空串/全零 hash 与 ④ slot omission / SQL NULL：单点在 definitions ─────
    #    本函数**不**复制 `is_digest` / 缺键 / NULL 三类检查（复制一份的后果见模块 docstring）。
    normalized = normalize_bundle_slot_map(slots)

    # ── ② marker 冒充 contract：单点在 models.validate_bundle_slots ────────────
    validate_bundle_slots(
        authority_model=authority_model,
        authority_model_definition_sha256=authority_model_definition_sha256,
        slots=normalized,
    )

    # ── ⑤ generator 候选冒充已人工审核契约（本模块补的一格）──────────────────
    #    `definitions.validate_contract_payload` 只校验 schema_version / 反向引用 /
    #    两个单向 digest，**不看** `review_status` ⇒ 直接把 generator 骨架喂给
    #    `DefinitionPublisher` 今天是可行的。这条判据就把那个口封上。
    review_status = str(contract_payload.get("review_status") or "")
    if review_status != "reviewed":
        raise ProjectionEntryNotReviewedError(
            f"entry {entry_id}: 待发布 contract canonical payload 的 review_status="
            f"{review_status!r} —— generator 只产 `candidate` 骨架，未经人工审核不得作为 "
            "per-entry 生产契约发布（首个非法 slot: contract）"
        )
    declared_contract_id = str(contract_payload.get("contract_id") or "")
    supply = load_projection_supply(entry_id)
    if declared_contract_id != supply.contract_id:
        raise ProjectionEntryNotReviewedError(
            f"entry {entry_id}: 待发布 contract 的 contract_id={declared_contract_id!r} 与"
            f"交付登记表登记的 {supply.contract_id!r} 不符 —— 不得把别的 entry 的契约"
            "发布到本 entry（首个非法 slot: contract）"
        )

    # ── ① 自造 uuid 或 digest：DB 现读 + validate_definition_child（本模块补的一格）──
    for slot in BundleSlot:
        spec = normalized[slot]
        if not spec.is_definition:
            continue
        try:
            child_id = uuid.UUID(spec.slot_ref.split(":", 1)[1])
        except (ValueError, IndexError) as exc:
            raise ForgedDefinitionIdentityError(
                f"{slot.value} slot 的 ref {spec.slot_ref!r} 不是 `definition:<uuid>` —— "
                f"首个非法 slot: {slot.value}"
            ) from exc
        child = (
            await session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id == child_id
                )
            )
        ).scalar_one_or_none()
        if child is None:
            raise ForgedDefinitionIdentityError(
                f"{slot.value} slot 引用的 definition {child_id} 在 "
                "`working_paper_sync_definition_artifact` 里不存在 —— 自造 uuid 不得进入 "
                f"canonical bytes（首个非法 slot: {slot.value}）"
            )
        # kind / state / digest 三项一致性的单点在 models.validate_definition_child；
        # 本函数只负责把 DB 行**读出来**（那是单点拿不到的一步）。
        try:
            validate_definition_child(
                slot=slot,
                child_kind=child.kind,
                child_state=child.state,
                child_sha256=child.sha256,
                slot_digest=spec.slot_digest,
            )
        except BundleIntegrityError as exc:
            raise ForgedDefinitionIdentityError(
                f"{exc} —— 首个非法 slot: {slot.value}"
            ) from exc
    return normalized


# ═══════════════════════════════════════════════════════════════════════════
# 4. 幂等发布器门面（按 canonical bytes 命中既有 artifact/bundle）
# ═══════════════════════════════════════════════════════════════════════════


class ReusingDefinitionPublisher:
    """`DefinitionPublisher` 的幂等门面：同 canonical digest 的 approved 行直接复用。

    ═══ 为什么是门面而不是改 `DefinitionPublisher` ═══

    Task 12 的发布器语义是「发布一份新的」，Tasks 40~43 的
    `publish_pilot_definitions()` 与 Task 19 的 opaque 通道都依赖它这一点。改它会让
    「重复发布」这条既有判据整类失效。本门面只在 **insert 之前**加一步查询，判据
    （payload 校验、DAG 前置、slot 规范化、artifact 内容寻址）一条不少地留在内层。

    ═══ 复用尺度是 canonical bytes，不是 logical_id ═══

    `definition_sha256` = `canonical_digest(payload)`（与内层发布器算的是同一个函数），
    因此「同内容」的定义与 AC 6.2 逐字一致。按 `logical_id` 猜会在语义漂移后复用一个
    身份已变的 definition —— 那正是 Property 28 要打红的形态。
    """

    __slots__ = ("_inner", "_session", "_project_id", "_wp_id", "_reused", "_created")

    def __init__(
        self,
        *,
        session: Any,
        artifacts: Any,
        repository: Any,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        source_commit: str = PROJECTION_PROVISION_SOURCE_COMMIT,
    ) -> None:
        self._session = session
        self._project_id = project_id
        self._wp_id = wp_id
        self._inner = DefinitionPublisher(
            artifacts=artifacts,
            repository=repository,
            project_id=project_id,
            wp_id=wp_id,
            source_commit=source_commit,
        )
        self._reused: list[str] = []
        self._created: list[str] = []

    # ─────────────────────────────────────────────────────────────────

    @property
    def approved_stages(self) -> frozenset[PublishStage]:
        return self._inner.approved_stages

    @property
    def reused_stages(self) -> tuple[str, ...]:
        return tuple(self._reused)

    @property
    def created_stages(self) -> tuple[str, ...]:
        return tuple(self._created)

    def mark_stage_approved(self, stage: PublishStage | str) -> None:
        self._inner.mark_stage_approved(stage)

    # ─────────────────────────────────────────────────────────────────

    async def publish_definition(
        self,
        *,
        kind: DefinitionKind | str,
        payload: Mapping[str, Any],
        logical_id: str,
        semantic_version: str,
        blob_bytes: bytes | None = None,
        structure_hash: str | None = None,
        approved: bool = True,
    ) -> PublishedDefinition:
        k = kind if isinstance(kind, DefinitionKind) else DefinitionKind(kind)
        # payload 校验必须在复用分支**之前**：否则「已存在同 digest 的行」会让一份非法
        # payload 免检通过（单点仍是 definitions.validate_definition_payload）。
        validate_definition_payload(k, payload)
        digest = canonical_digest(payload)
        existing = await self._find_approved_definition(k, digest)
        if existing is None:
            published = await self._inner.publish_definition(
                kind=k,
                payload=payload,
                logical_id=logical_id,
                semantic_version=semantic_version,
                blob_bytes=blob_bytes,
                structure_hash=structure_hash,
                approved=approved,
            )
            self._created.append(k.value)
            return published
        relative_path = (
            await self._session.execute(
                sa.text("SELECT relative_path FROM working_paper_artifact WHERE id = :a"),
                {"a": str(existing.blob_artifact_id)},
            )
        ).scalar_one_or_none()
        if relative_path is None:
            raise ForgedDefinitionIdentityError(
                f"{k.value} definition {existing.id} 的 blob artifact "
                f"{existing.blob_artifact_id} 行不存在 —— definition 与其内容寻址 blob "
                "脱钩，不得按它复用（半成功态必须可见）"
            )
        if approved and k is not DefinitionKind.authority_model:
            # 与内层同一条规则：authority model 不在 PUBLISH_DAG 上，故不标阶段。
            self._inner.mark_stage_approved(PublishStage(k.value))
        self._reused.append(k.value)
        return PublishedDefinition(
            definition_id=existing.id,
            kind=k,
            sha256=digest,
            blob_artifact_id=existing.blob_artifact_id,
            relative_path=str(relative_path),
            state=DefinitionState.approved,
        )

    async def publish_bundle(
        self,
        *,
        authority_model_definition_id: uuid.UUID,
        authority_model: AuthorityModel | str,
        authority_model_definition_sha256: str,
        slots: Mapping[Any, Any],
        approved: bool = True,
    ) -> PublishedBundle:
        # `bundle_canonical_digest` 内部走 `build_bundle_canonical_payload`，故 FC-1~FC-14
        # 在复用分支上同样生效（不是「查到就放行」）。
        digest = bundle_canonical_digest(
            authority_model=authority_model,
            authority_model_definition_sha256=authority_model_definition_sha256,
            slots=slots,
        )
        normalized = normalize_bundle_slot_map(slots)
        existing = await self._find_approved_bundle(digest)
        if existing is None:
            published = await self._inner.publish_bundle(
                authority_model_definition_id=authority_model_definition_id,
                authority_model=authority_model,
                authority_model_definition_sha256=authority_model_definition_sha256,
                slots=slots,
                approved=approved,
            )
            self._created.append(PublishStage.bundle.value)
            return published
        if existing.authority_model_definition_id != authority_model_definition_id:
            raise ForgedDefinitionIdentityError(
                f"已存在同 canonical digest 的 bundle {existing.id}，但它的 authority model "
                f"child 是 {existing.authority_model_definition_id} 而本次声明 "
                f"{authority_model_definition_id} —— canonical bytes 相同却 child 不同"
                "意味着身份漂移，不得复用（首个非法 slot: authority_model）"
            )
        if approved:
            self._inner.mark_stage_approved(PublishStage.bundle)
        self._reused.append(PublishStage.bundle.value)
        return PublishedBundle(
            bundle_id=existing.id,
            canonical_sha256=existing.canonical_payload_sha256,
            canonical_payload_artifact_id=existing.canonical_payload_artifact_id,
            authority_model=(
                authority_model
                if isinstance(authority_model, AuthorityModel)
                else AuthorityModel(authority_model)
            ),
            authority_model_definition_id=authority_model_definition_id,
            slots=normalized,
            state=DefinitionState.approved,
        )

    # ─────────────────────────────────────────────────────────────────

    async def _find_approved_definition(
        self, kind: DefinitionKind, digest: str
    ) -> WorkpaperSyncDefinitionArtifact | None:
        """按 `(kind, sha256, approved)` 找可复用行；并发下按 `(created_at, id)` 收敛。"""
        return (
            (
                await self._session.execute(
                    sa.select(WorkpaperSyncDefinitionArtifact)
                    .where(
                        WorkpaperSyncDefinitionArtifact.kind == kind.value,
                        WorkpaperSyncDefinitionArtifact.sha256 == digest,
                        WorkpaperSyncDefinitionArtifact.state
                        == DefinitionState.approved.value,
                    )
                    .order_by(
                        WorkpaperSyncDefinitionArtifact.created_at,
                        WorkpaperSyncDefinitionArtifact.id,
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    async def _find_approved_bundle(
        self, digest: str
    ) -> WorkpaperSyncDefinitionBundle | None:
        return (
            (
                await self._session.execute(
                    sa.select(WorkpaperSyncDefinitionBundle)
                    .where(
                        WorkpaperSyncDefinitionBundle.canonical_payload_sha256 == digest,
                        WorkpaperSyncDefinitionBundle.state == DefinitionState.approved.value,
                    )
                    .order_by(
                        WorkpaperSyncDefinitionBundle.created_at,
                        WorkpaperSyncDefinitionBundle.id,
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. candidate 受控 attach
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CandidateAttachOutcome:
    """一次受控 attach 的结果（含 append-only 审计事件的定位信息）。"""

    candidate_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    from_state: str
    to_state: str
    contract_definition_id: uuid.UUID
    definition_bundle_id: uuid.UUID
    definition_bundle_sha256: str
    event_id: uuid.UUID
    event_sequence_no: int
    correlation_id: str
    content_revision_before: int
    content_revision_after: int
    entry_pointer_before: str | None
    entry_pointer_after: str | None

    @property
    def revision_unchanged(self) -> bool:
        return self.content_revision_before == self.content_revision_after

    @property
    def pointer_unchanged(self) -> bool:
        return self.entry_pointer_before == self.entry_pointer_after

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": str(self.candidate_id),
            "wp_id": str(self.wp_id),
            "entry_id": self.entry_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "contract_definition_id": str(self.contract_definition_id),
            "definition_bundle_id": str(self.definition_bundle_id),
            "definition_bundle_sha256": self.definition_bundle_sha256,
            "event_id": str(self.event_id),
            "event_sequence_no": self.event_sequence_no,
            "correlation_id": self.correlation_id,
            "content_revision_before": self.content_revision_before,
            "content_revision_after": self.content_revision_after,
            "revision_unchanged": self.revision_unchanged,
            "entry_pointer_before": self.entry_pointer_before,
            "entry_pointer_after": self.entry_pointer_after,
            "pointer_unchanged": self.pointer_unchanged,
        }


class CandidateDefinitionAttachService:
    """把已 approved 的 contract/bundle 绑到 `awaiting_contract` candidate 上的唯一入口。

    ═══ 补的是仓储上真正缺的那一格 ═══

    V151 起 candidate 表允许**创建时**给 `target_contract_definition_id` /
    `target_definition_bundle_id`，但两个 instrumentation upgrader 都恒写 `None`
    （它们无权发布 contract/bundle，`CandidateOnlyRepository` 也把 finalize 面摘掉了）。
    于是 approved 供给到位后没有任何受控入口能把它绑上去 ——
    `assert_candidate_finalizable` 永远停在「缺 approved per-entry contract」。

    ═══ 四条禁令 ═══

    * **不得**修改已 finalize 的 candidate → `assert_transition("candidate", ...)`
      （`finalized` 出边为空集），单点在 `models.CANDIDATE_EDGES`；
    * **不得**绕过 `assert_candidate_finalizable` → 本服务只把状态推到 `ready`，
      finalize 仍必须经 Task 12 的那五条前置（本服务一个字节都不改它）；
    * **不得**因 attach 让 candidate 进入 resolver / room / current pointer / evidence
      → 本服务不调 `set_entry_pointer` / `create_representation` / `finalize_candidate`；
    * **不得**递增 `content_revision` → 前后各读一次并断言逐值相等。
    """

    def __init__(self, *, session: Any, repository: Any) -> None:
        self._session = session
        self._repo = repository

    async def attach(
        self,
        *,
        wp_id: uuid.UUID,
        entry_id: str,
        candidate_id: uuid.UUID,
        contract_definition_id: uuid.UUID,
        definition_bundle_id: uuid.UUID,
        correlation_id: str,
        actor_id: uuid.UUID | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> CandidateAttachOutcome:
        candidate = (
            await self._session.execute(
                sa.select(WorkpaperRepresentationUpgradeCandidate).where(
                    WorkpaperRepresentationUpgradeCandidate.id == candidate_id
                )
            )
        ).scalar_one_or_none()
        if candidate is None:
            raise CandidateAttachError(f"upgrade candidate 不存在: {candidate_id}")
        if candidate.wp_id != wp_id or candidate.entry_id != entry_id:
            raise CandidateScopeMismatchError(
                f"candidate {candidate_id} 属于 (wp={candidate.wp_id}, "
                f"entry={candidate.entry_id!r})，与本次 (wp={wp_id}, entry={entry_id!r}) "
                "不符 —— 禁跨 entry 复用 contract/bundle/candidate"
            )
        if candidate.state != CandidateState.awaiting_contract.value:
            raise CandidateNotAwaitingContractError(
                f"candidate {candidate_id} state={candidate.state} —— 受控 attach 只接受 "
                f"`{CandidateState.awaiting_contract.value}`；已 finalize / ready / rejected "
                "/ orphaned 的 candidate 不得被改写（Requirement 6.18 / Property 67）"
            )
        before = await self._snapshot(wp_id=wp_id, entry_id=entry_id)
        cand, event = await self._repo.attach_candidate_definitions(
            candidate_id=candidate_id,
            contract_definition_id=contract_definition_id,
            definition_bundle_id=definition_bundle_id,
            correlation_id=correlation_id,
            actor_id=actor_id,
            detail=dict(detail or {}),
        )
        after = await self._snapshot(wp_id=wp_id, entry_id=entry_id)
        if before["content_revision"] != after["content_revision"]:
            raise ContentRevisionDriftError(
                f"attach 期间 content_revision 由 {before['content_revision']} 变为 "
                f"{after['content_revision']} —— 纯 definitions 绑定不得推进业务 revision"
                "（Requirement 2.1 / Property 4）"
            )
        if before["pointer"] != after["pointer"]:
            raise CandidateAttachError(
                f"attach 期间 entry current pointer 由 {before['pointer']} 变为 "
                f"{after['pointer']} —— candidate 永不得成为 current（Property 67）"
            )
        return CandidateAttachOutcome(
            candidate_id=candidate_id,
            wp_id=wp_id,
            entry_id=entry_id,
            from_state=str(event.from_state),
            to_state=str(cand.state),
            contract_definition_id=contract_definition_id,
            definition_bundle_id=definition_bundle_id,
            definition_bundle_sha256=str(event.definition_bundle_sha256 or ""),
            event_id=event.id,
            event_sequence_no=int(event.sequence_no),
            correlation_id=correlation_id,
            content_revision_before=int(before["content_revision"]),
            content_revision_after=int(after["content_revision"]),
            entry_pointer_before=before["pointer"],
            entry_pointer_after=after["pointer"],
        )

    async def _snapshot(self, *, wp_id: uuid.UUID, entry_id: str) -> dict[str, Any]:
        return await _revision_and_pointer(self._session, wp_id=wp_id, entry_id=entry_id)


# ═══════════════════════════════════════════════════════════════════════════
# 6. provisioner
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProvisionOutcome:
    """一次 `(project_id, wp_id, entry_id)` 作用域的 provision 结果。"""

    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    contract_id: str
    authority_model: str
    authority_model_definition_id: uuid.UUID
    authority_model_definition_sha256: str
    template_definition_id: uuid.UUID
    template_definition_sha256: str
    instrumentation_definition_id: uuid.UUID
    instrumentation_definition_sha256: str
    contract_definition_id: uuid.UUID
    contract_definition_sha256: str
    definition_bundle_id: uuid.UUID
    definition_bundle_sha256: str
    created_stages: tuple[str, ...]
    reused_stages: tuple[str, ...]
    representation_settlement: str
    representation_reason: str
    attached_candidate_id: uuid.UUID | None
    attach: CandidateAttachOutcome | None
    content_revision_before: int
    content_revision_after: int
    entry_pointer_before: str | None
    entry_pointer_after: str | None

    @property
    def revision_unchanged(self) -> bool:
        return self.content_revision_before == self.content_revision_after

    @property
    def created_anything(self) -> bool:
        return bool(self.created_stages)

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": str(self.project_id),
            "wp_id": str(self.wp_id),
            "entry_id": self.entry_id,
            "contract_id": self.contract_id,
            "authority_model": self.authority_model,
            "authority_model_definition_id": str(self.authority_model_definition_id),
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "template_definition_id": str(self.template_definition_id),
            "template_definition_sha256": self.template_definition_sha256,
            "instrumentation_definition_id": str(self.instrumentation_definition_id),
            "instrumentation_definition_sha256": self.instrumentation_definition_sha256,
            "contract_definition_id": str(self.contract_definition_id),
            "contract_definition_sha256": self.contract_definition_sha256,
            "definition_bundle_id": str(self.definition_bundle_id),
            "definition_bundle_sha256": self.definition_bundle_sha256,
            "created_stages": list(self.created_stages),
            "reused_stages": list(self.reused_stages),
            "representation_settlement": self.representation_settlement,
            "representation_reason": self.representation_reason,
            "attached_candidate_id": (
                str(self.attached_candidate_id) if self.attached_candidate_id else None
            ),
            "attach": self.attach.as_dict() if self.attach is not None else None,
            "content_revision_before": self.content_revision_before,
            "content_revision_after": self.content_revision_after,
            "revision_unchanged": self.revision_unchanged,
            "entry_pointer_before": self.entry_pointer_before,
            "entry_pointer_after": self.entry_pointer_after,
            "created_anything": self.created_anything,
        }


class ProjectionDefinitionProvisioner:
    """按 `(project_id, wp_id)` 作用域幂等发布 `projection_contract` definition 链。

    **不 commit** —— 事务边界属于调用方（与 `WorkpaperSyncRepository` 只 flush 不 commit
    的约定一致），因此「任一步失败只留不可见 candidate/orphan」由调用方的一次 rollback
    落实：本类不自己开事务、不自己救场。
    """

    def __init__(
        self,
        *,
        session: Any,
        repository: Any,
        artifacts: Any,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        source_commit: str = PROJECTION_PROVISION_SOURCE_COMMIT,
    ) -> None:
        self._session = session
        self._repo = repository
        self._artifacts = artifacts
        self._project_id = project_id
        self._wp_id = wp_id
        self._source_commit = source_commit

    async def ensure(
        self,
        *,
        entry_id: str,
        actor_id: uuid.UUID | None = None,
        attach_candidate: bool = True,
    ) -> ProvisionOutcome:
        """幂等地让该 entry 拥有 approved authority model + 三 child 全非空的 approved bundle。"""
        supply = load_projection_supply(entry_id)
        contract = supply.contract
        before = await _revision_and_pointer(
            self._session, wp_id=self._wp_id, entry_id=entry_id
        )
        publisher = ReusingDefinitionPublisher(
            session=self._session,
            artifacts=self._artifacts,
            repository=self._repo,
            project_id=self._project_id,
            wp_id=self._wp_id,
            source_commit=self._source_commit,
        )
        # 🔴 逐 entry 的 payload 组装**只有一份**：该 entry 自己的
        #    `publish_pilot_definitions()`。在这里调它，正是让它不再只被
        #    `test_task4x_*_pg.py` 调用（Task 76 正文明令）——
        #    在测试里另抄一份组装等于让生产那份一次都没被执行（假绿第③源）。
        definitions = await supply.provider.publish_pilot_definitions(publisher)
        slots = {
            BundleSlot.template: definition_slot_spec(
                BundleSlot.template,
                definition_id=definitions.template_definition_id,
                definition_sha256=definitions.template_definition_sha256,
            ),
            BundleSlot.instrumentation: definition_slot_spec(
                BundleSlot.instrumentation,
                definition_id=definitions.instrumentation_definition_id,
                definition_sha256=definitions.instrumentation_definition_sha256,
            ),
            BundleSlot.contract: definition_slot_spec(
                BundleSlot.contract,
                definition_id=definitions.contract_definition_id,
                definition_sha256=definitions.contract_definition_sha256,
            ),
        }
        await assert_projection_supply_authentic(
            session=self._session,
            entry_id=entry_id,
            authority_model=supply.authority_model,
            authority_model_definition_sha256=definitions.authority_model_definition_sha256,
            slots=slots,
            contract_payload=contract.canonical_payload,
        )
        # bundle 落库后再走一次仓储的双向校验（approved + 四 slot + child kind/state/digest）。
        # 与上面那次不重合：这一次读的是**已落库的 bundle 行**，上面读的是**待发布的 slot 声明**。
        bundle_row = await self._repo.assert_bundle_usable(definitions.bundle_id)
        if bundle_row.canonical_payload_sha256 != definitions.bundle_sha256:
            raise ForgedDefinitionIdentityError(
                f"bundle {definitions.bundle_id} 的 canonical digest "
                f"{bundle_row.canonical_payload_sha256} 与发布器返回的 "
                f"{definitions.bundle_sha256} 不一致"
            )
        # DAG 偏序：representation 阶段的直接前置是 bundle，必须真的 approved 才允许进入。
        assert_publish_order(
            stage=PublishStage.representation, approved_stages=publisher.approved_stages
        )
        settlement, reason, attach = await self._settle_representation_stage(
            entry_id=entry_id,
            definitions=definitions,
            actor_id=actor_id,
            attach_candidate=attach_candidate,
        )
        after = await _revision_and_pointer(
            self._session, wp_id=self._wp_id, entry_id=entry_id
        )
        if before["content_revision"] != after["content_revision"]:
            raise ContentRevisionDriftError(
                f"provision 期间 content_revision 由 {before['content_revision']} 变为 "
                f"{after['content_revision']} —— 纯 definition/bundle 发布不得推进业务 "
                "revision（Requirement 2.1 / Property 4）"
            )
        return ProvisionOutcome(
            project_id=self._project_id,
            wp_id=self._wp_id,
            entry_id=entry_id,
            contract_id=supply.contract_id,
            authority_model=supply.authority_model.value,
            authority_model_definition_id=definitions.authority_model_definition_id,
            authority_model_definition_sha256=definitions.authority_model_definition_sha256,
            template_definition_id=definitions.template_definition_id,
            template_definition_sha256=definitions.template_definition_sha256,
            instrumentation_definition_id=definitions.instrumentation_definition_id,
            instrumentation_definition_sha256=definitions.instrumentation_definition_sha256,
            contract_definition_id=definitions.contract_definition_id,
            contract_definition_sha256=definitions.contract_definition_sha256,
            definition_bundle_id=definitions.bundle_id,
            definition_bundle_sha256=definitions.bundle_sha256,
            created_stages=publisher.created_stages,
            reused_stages=publisher.reused_stages,
            representation_settlement=settlement,
            representation_reason=reason,
            attached_candidate_id=None if attach is None else attach.candidate_id,
            attach=attach,
            content_revision_before=int(before["content_revision"]),
            content_revision_after=int(after["content_revision"]),
            entry_pointer_before=before["pointer"],
            entry_pointer_after=after["pointer"],
        )

    # ─────────────────────────────────────────────────────────────────

    async def _settle_representation_stage(
        self,
        *,
        entry_id: str,
        definitions: Any,
        actor_id: uuid.UUID | None,
        attach_candidate: bool,
    ) -> tuple[str, str, CandidateAttachOutcome | None]:
        """`representation` 阶段的结算：复用 / attach / 显式阻塞，**不插 representation 行**。"""
        current = await self._current_representation(entry_id)
        if current is not None and current.definition_bundle_id == definitions.bundle_id:
            return (
                "reused_current",
                (
                    f"entry {entry_id} 的 current published representation {current.id} "
                    f"已绑定本次 approved bundle {definitions.bundle_id} —— 幂等复用，"
                    "不新增 generation（Requirement 3.6 / Property 10）"
                ),
                None,
            )
        ready = await self._candidate_bound_to(entry_id, definitions)
        if ready is not None:
            return (
                "reused_candidate",
                (
                    f"candidate {ready.id} 已绑定本次 contract "
                    f"{definitions.contract_definition_id} 与 bundle "
                    f"{definitions.bundle_id}（state={ready.state}）—— 幂等复用；finalize 由 "
                    "Task 36 的 `ExcelEntryFinalizeGate` 经 Task 25 的唯一出口执行"
                ),
                None,
            )
        pending = await self._candidate_awaiting_contract(entry_id)
        if pending is None:
            return (
                "blocked",
                (
                    f"entry {entry_id} 没有 `state=awaiting_contract` 的 representation "
                    "upgrade candidate 可绑定。approved bundle 已就位，缺的是**表示**侧供给："
                    "①该 entry 若还没有任何 content version/representation，首版只能由 "
                    "`ContentMutationService.commit(...)`（唯一能推进 content_revision 的业务"
                    "事务）产生；②已有 representation 时，纯 definitions 升级须先由 Task 17 的 "
                    "instrumentation upgrader 登记 non-current candidate。本 provisioner "
                    "**不**自建第三条 representation 写入路径（会伪造业务 projection 并绕过 "
                    "`assert_candidate_finalizable`，Property 4 / 67 双打红）"
                ),
                None,
            )
        if not attach_candidate:
            return (
                "blocked",
                (
                    f"candidate {pending.id} 处于 awaiting_contract 且供给已就位，但本次调用"
                    "以 `attach_candidate=False` 运行（只读探测）—— 未做任何绑定"
                ),
                None,
            )
        attach = await CandidateDefinitionAttachService(
            session=self._session, repository=self._repo
        ).attach(
            wp_id=self._wp_id,
            entry_id=entry_id,
            candidate_id=pending.id,
            contract_definition_id=definitions.contract_definition_id,
            definition_bundle_id=definitions.bundle_id,
            correlation_id=f"{PROJECTION_PROVISION_SOURCE_COMMIT}@{self._wp_id}/{entry_id}",
            actor_id=actor_id,
            detail={
                "source_commit": self._source_commit,
                "contract_id": str(getattr(definitions, "contract_definition_id", "")),
                "template_definition_sha256": definitions.template_definition_sha256,
                "instrumentation_definition_sha256": (
                    definitions.instrumentation_definition_sha256
                ),
            },
        )
        return (
            "attached_candidate",
            (
                f"candidate {pending.id} 已由受控 attach 入口绑定 approved contract/bundle 并"
                f"进入 `{attach.to_state}`；finalize 仍必须经 "
                "`assert_candidate_finalizable` 的五条前置与 Task 36 的门"
            ),
            attach,
        )

    async def _current_representation(
        self, entry_id: str
    ) -> WorkpaperContentRepresentation | None:
        representation_id = (
            (
                await self._session.execute(
                    sa.select(WorkpaperSyncEntryState.current_representation_id).where(
                        WorkpaperSyncEntryState.wp_id == self._wp_id,
                        WorkpaperSyncEntryState.entry_id == entry_id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if representation_id is None:
            return None
        return (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation).where(
                    WorkpaperContentRepresentation.id == representation_id
                )
            )
        ).scalar_one_or_none()

    async def _candidate_bound_to(
        self, entry_id: str, definitions: Any
    ) -> WorkpaperRepresentationUpgradeCandidate | None:
        return (
            (
                await self._session.execute(
                    sa.select(WorkpaperRepresentationUpgradeCandidate)
                    .where(
                        WorkpaperRepresentationUpgradeCandidate.wp_id == self._wp_id,
                        WorkpaperRepresentationUpgradeCandidate.entry_id == entry_id,
                        WorkpaperRepresentationUpgradeCandidate.target_definition_bundle_id
                        == definitions.bundle_id,
                        WorkpaperRepresentationUpgradeCandidate.target_contract_definition_id
                        == definitions.contract_definition_id,
                    )
                    .order_by(
                        WorkpaperRepresentationUpgradeCandidate.created_at,
                        WorkpaperRepresentationUpgradeCandidate.id,
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    async def _candidate_awaiting_contract(
        self, entry_id: str
    ) -> WorkpaperRepresentationUpgradeCandidate | None:
        return (
            (
                await self._session.execute(
                    sa.select(WorkpaperRepresentationUpgradeCandidate)
                    .where(
                        WorkpaperRepresentationUpgradeCandidate.wp_id == self._wp_id,
                        WorkpaperRepresentationUpgradeCandidate.entry_id == entry_id,
                        WorkpaperRepresentationUpgradeCandidate.state
                        == CandidateState.awaiting_contract.value,
                    )
                    .order_by(
                        WorkpaperRepresentationUpgradeCandidate.created_at,
                        WorkpaperRepresentationUpgradeCandidate.id,
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )


# ═══════════════════════════════════════════════════════════════════════════
# 7. 共享读取
# ═══════════════════════════════════════════════════════════════════════════


async def _revision_and_pointer(
    session: Any, *, wp_id: uuid.UUID, entry_id: str
) -> dict[str, Any]:
    """`content_revision` 与 entry current pointer 的**同源**快照（前后比对用）。

    只有一份实现：provisioner 与 attach 共用。两处各写一份会让「revision 不变」这条
    判据在其中一处被短路时仍然绿。
    """
    revision = (
        await session.execute(
            sa.text("SELECT content_revision FROM working_paper WHERE id = :w"),
            {"w": str(wp_id)},
        )
    ).scalar_one_or_none()
    pointer = (
        (
            await session.execute(
                sa.select(WorkpaperSyncEntryState.current_representation_id).where(
                    WorkpaperSyncEntryState.wp_id == wp_id,
                    WorkpaperSyncEntryState.entry_id == entry_id,
                )
            )
        )
        .scalars()
        .first()
    )
    return {
        "content_revision": int(revision or 0),
        "pointer": None if pointer is None else str(pointer),
    }


async def count_supply_rows(session: Any) -> dict[str, int]:
    """四张供给表的当前行数（`--check` 与守卫的「0 → N」判据共用一份实现）。"""
    out: dict[str, int] = {}
    for table in SUPPLY_TABLES:
        out[table] = int(
            (
                await session.execute(sa.text(f"SELECT count(*) FROM {table}"))  # noqa: S608
            ).scalar_one()
        )
    return out


__all__ = [
    "PROJECTION_PROVISION_SOURCE_COMMIT",
    "REPRESENTATION_SETTLEMENT_STATES",
    "SUPPLY_TABLES",
    "ProjectionProvisioningError",
    "ProjectionEntryNotReviewedError",
    "ForgedDefinitionIdentityError",
    "ProjectionAuthorityModelMismatchError",
    "ProviderModuleNotAllowedError",
    "ContentRevisionDriftError",
    "CandidateAttachError",
    "CandidateScopeMismatchError",
    "CandidateNotAwaitingContractError",
    "ProjectionSupply",
    "load_projection_supply",
    "assert_projection_supply_authentic",
    "ReusingDefinitionPublisher",
    "CandidateAttachOutcome",
    "CandidateDefinitionAttachService",
    "ProvisionOutcome",
    "ProjectionDefinitionProvisioner",
    "count_supply_rows",
]
