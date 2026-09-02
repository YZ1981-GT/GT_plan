# -*- coding: utf-8 -*-
"""ContentMutationService：所有业务内容 writer 的**唯一** commit 边界。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 15
Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.6, 6.18, 8.10, 8.12, 13.1
Properties: P4（业务版本与 representation generation 正交）/ P5（无悬空可见态）/
P10（单次 commit 与 representation 幂等）/ P61（所有 writer 进入唯一 revision 域）/
P65（projection 与同 revision representation 等值）/ P67（candidate 先行、approved 后 finalize）

═══ 一、被明令禁止的形态：projection-only commit + 二次 revision ═══

Requirement 3.1 / Property 10 的原文是「不得先提交 projection-only revision 再补
artifact」。这不是「别那样写」的建议，而是**否定式承诺** —— 它必须被证明*不可能*，
而不是「当前代码里没有」。本模块用四道互相独立的机制落实：

1. **单一 commit 出口**：整个 `commit()` 里只有一处 `await self._session.commit()`，
   并由 :class:`_CommitLatch` 计数；第二次调用即 :class:`DoubleCommitError`。
2. **单事务见证**：每一步写入后取一次 `pg_current_xact_id()`
   （:class:`_TransactionWitness`）。任何中途 commit/rollback 都会让后续步骤落到
   **另一个** xid ⇒ :class:`TransactionSplitError`。这条判据不看源码、不看调用次数，
   直接看数据库事务身份，因此「换个名字调 commit」也躲不过。
3. **步骤完整性**：`revision / content_version / representation / entry_pointer /
   outbox` 五步必须都在同一事务里留下见证。少任何一步 ⇒
   :class:`TransactionStepMissingError`。删掉 representation 写入而只提交 projection，
   正是被禁形态的第一半，它在这里就红。
4. **revision 域门面**：:class:`RevisionLockedRepository` 让「纯表示路径」在**构造上**
   碰不到 `bump_content_revision` / `set_current_content_version` /
   `create_content_version`。所以第二次 revision 递增不可能来自
   `RepresentationService`。

变异检验 M20~M23 分别注入「第二次 commit」「representation 路径里的 revision bump」
「finalize 中途 commit」「纯表示路径去动 current pointer」四条反例，逐条证明上面四道
机制可 falsify（否定式承诺无法用短路式变异证明 —— 参见 Task 12 的 M51 与 Task 14 的
M74~M78）。M38 另外注入第二处 `bump_content_revision(` 调用点，证明「唯一 revision 域」
这条也是可 falsify 的（脚本：`backend/scripts/diagnose/mutate_task15_commit_representation_guards.py`）。

═══ 二、文件系统与数据库不是同一个事务，这里也不假装是 ═══

design §Filesystem Layout 的发布协议是**可恢复协议**：

* artifact 先流式落 `.staging` → 校验 digest → roundtrip 反读 → publish 到 `.versions`；
* **然后**开一个短数据库事务写 content version / representation / revision / pointer /
  outbox；
* 事务失败 ⇒ 文件已经 publish 但**没有任何 DB 行引用它** ⇒ 它是不可见 orphan，由
  Task 11 的 reconciliation 收（Requirement 2.4 / Property 5）。

因此「rollback 后留下不可见 orphan」不是缺陷而是**设计承诺**：宁可留垃圾文件，也不
留「pointer 指向缺失 artifact」的半成功态。

═══ 三、adapter 在这里被当作纯函数使用 ═══

`SyncContext`（Task 13）刻意不含 session/repository/outbox，`assert_no_mutation_surface`
逐字段实测这一点。本模块调用 adapter 的四个方法
（`read_current_projection` / `materialize` / `extract` / `verify_unmanaged_regions`）
全部发生在**数据库事务之外**：事务内禁止远程下载与 OOXML 大解析
（design §Filesystem Layout 第 3 条）。

═══ 四、Property 65 的 roundtrip 等值判据用 Task 14 的类型规范化 ═══

「写进 OOXML 的受管值反读回来必须等值」这条判据的难点不是比较本身，而是**比较口径**：
`"1,234.50"` 与 `Decimal("1234.5")` 是同一个金额，`None` 与 MISSING 不是同一件事。
本模块直接复用 `merge.values_equal()`（金额 Decimal / 日期 ISO / 文本仅归一 CRLF），
不自己写第二套比较 —— 两套口径必然漂移，而漂移的那一天两边都「全绿」。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Protocol, Sequence, runtime_checkable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import EventType
from app.models.workpaper_sync_models import (
    WorkpaperContentRepresentation,
    WorkpaperPendingMutation,
    WorkpaperSyncEntryState,
)
from app.services.workpaper_sync.adapters.base import (
    MaterializeResult,
    Projection,
    SubstrateRole,
    SyncContext,
    UnmanagedRegionReport,
    assert_no_mutation_surface,
    assert_substrate_usable,
)
from app.services.workpaper_sync.artifacts import (
    CanonicalArtifactRepository,
    PublishedArtifact,
)
from app.services.workpaper_sync.conflicts import (
    ResolutionChoice,
    UnresolvedConflictError,
    assert_all_conflicts_resolved,
)
from app.services.workpaper_sync.contracts import FieldMode, SyncContract
from app.services.workpaper_sync.definitions import canonical_json_bytes, json_safe
from app.services.workpaper_sync.entry_profile import Capability
from app.services.workpaper_sync.merge import (
    MergeOutcome,
    apply_resolutions,
    projection_requires_client_refresh,
    values_equal,
)
from app.services.workpaper_sync.models import (
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    PendingMutationState,
    RoomState,
    SyncDomainError,
    assert_transition,
    is_digest,
)
from app.services.workpaper_sync.outbox import DurableEventOutboxService, PendingPublication
from app.services.workpaper_sync.repository import WorkpaperSyncRepository
from app.services.workpaper_sync.representations import (
    assert_bundle_snapshot_finalizable,
    next_representation_generation,
)
from app.services.workpaper_sync.resolution import (
    CanonicalResolutionService,
    DefinitionBundleSnapshot,
)

__all__ = [
    "ContentMutationError",
    "TransactionSplitError",
    "TransactionStepMissingError",
    "DoubleCommitError",
    "RevisionBumpForbiddenError",
    "RevisionTargetError",
    "RoundtripEquivalenceError",
    "AdjudicationNotFoldedError",
    "AuthorityModelMismatchError",
    "ContractRequiredError",
    "PendingMutationScopeError",
    "PendingMutationExpiredError",
    "PendingMutationPayloadError",
    "PendingMutationStateError",
    "RepresentationLaneRequiredError",
    "HtmlOnlyCapabilityMismatchError",
    "HtmlOnlyEntryHasRepresentationError",
    "ContentSource",
    "ContentCommitPlan",
    "BusinessMutation",
    "ContentCommitReceipt",
    "CommitTransactionFacts",
    "CommitFenceHook",
    "HtmlOnlyCommitPlan",
    "StagedHtmlProjection",
    "HtmlOnlyCommitReceipt",
    "RevisionLockedRepository",
    "ContentMutationService",
    "CONTENT_COMMIT_STEPS",
    "HTML_ONLY_COMMIT_STEPS",
    "HTML_ONLY_ENTRY_PREFIX",
    "HTML_PROJECTION_SCHEMA_VERSION",
    "EVENT_PAYLOAD_REQUIRED_KEYS",
    "HTML_ONLY_EVENT_PAYLOAD_REQUIRED_KEYS",
    "REVISION_DOMAIN_WRITE_METHODS",
    "html_only_entry_id",
    "build_html_content_mutation_service",
    "projection_canonical_digest",
]


def _now() -> datetime:
    """服务端时钟（aware）。timestamptz 必须在 Python 侧构造 datetime。"""
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常：每条拒绝原因一个类型
# ═══════════════════════════════════════════════════════════════════════════


class ContentMutationError(SyncDomainError):
    error_code = "content_commit_failed"


class TransactionSplitError(ContentMutationError):
    """同一次 commit 的写入落在了**多个**数据库事务里（Requirement 2.4 / 13.1）。

    只要有人在中途 `commit()` / `rollback()`，后续步骤就会取到新的
    `pg_current_xact_id()` ⇒ 本异常。它是「projection-only commit 后再补一次」的
    直接判据。
    """

    error_code = "content_commit_transaction_split"


class TransactionStepMissingError(ContentMutationError):
    """必需步骤没有在事务里留下见证 —— 有人把它移出事务或删掉了。

    🔴 与 :class:`TransactionSplitError` 分成两类：把 representation 写入整段删掉时，
    xid 集合仍然只有一个（剩下的步骤确实同事务），共用类型会让「只提交 projection」
    这条判据被「事务未分裂」遮蔽成不可达分支。
    """

    error_code = "content_commit_step_missing"


class DoubleCommitError(ContentMutationError):
    """一次 `commit()` 试图提交两次（Requirement 3.1 的「不得二次 commit」）。"""

    error_code = "content_commit_double_commit"


class RevisionBumpForbiddenError(ContentMutationError):
    """纯表示路径试图碰 business revision 域（Property 4）。"""

    error_code = "content_revision_bump_forbidden"


class RevisionTargetError(ContentMutationError):
    """CAS 推进后的 revision 不等于本次 commit 预定的目标值。

    发生它意味着「文件命名用的 revision」与「数据库里的 revision」已经不一致 ——
    artifact 路径里带 revision，错位后历史读取会取到别的版本。
    """

    error_code = "content_revision_target_mismatch"


class RoundtripEquivalenceError(ContentMutationError):
    """staged representation 反读出来的受管 projection 与要提交的 projection 不等值。

    Property 65 的落点。必须在 DB 事务**之前**失败：这一步失败还提交 HTML projection，
    就是 Requirement 8.11 明令禁止的「只提交一半」。
    """

    error_code = "roundtrip_projection_mismatch"


class AdjudicationNotFoldedError(ContentMutationError):
    """带人工裁决却提交了**未收敛**的 projection（`merge.merged` 而不是裁决结果）。

    🔴 这是 2026-08-27 审计抓到的静默错值路径在 commit 边界上的第二道锁。
    `merge.merged` 对每个冲突字段保留的是 **current** 侧值（`merge.py` 模块头原话），
    所以「校验裁决覆盖了每条冲突」通过之后直接落 `merge.merged`，等于把审计师的
    「取 incoming」静默换成 current；而 rematerialize 反读等值比的是「result 与提交的
    projection 一致」（两边同为错值必等）、fence 只看授权与身份 ⇒ 四道关全绿。

    因此本模块**独立重算** :func:`~merge.apply_resolutions` 并逐字节比对：调用方折叠
    错了、忘了折叠、或折叠用了另一份 contract，都在这里 fail closed。与
    :class:`UnresolvedConflictError`（一条裁决都没给）分两个类型 —— 共用一个
    `error_code` 会让靠前那条判据永久不可达。
    """

    error_code = "adjudication_projection_not_folded"


class AuthorityModelMismatchError(ContentMutationError):
    """business mutation 形态与 bundle 的 approved authority model 不符。

    `projection_contract` 必须给 projection；`custom_authoritative_ooxml` /
    `opaque_single_onlyoffice` 必须给 authoritative 字节且**不得**被 JSON projection
    writer 改写（Requirement 2.11 / 6.19）。
    """

    error_code = "authority_model_mismatch"


class ContractRequiredError(ContentMutationError):
    """projection-based 入口缺 per-entry contract（Requirement 3.3）。

    🔴 与 :class:`AuthorityModelMismatchError` 分两类：前者是「authority model 说要
    contract 但没给」，后者是「给的内容形态与 authority model 不匹配」。共用类型时
    短路其中一条会被另一条遮蔽。
    """

    error_code = "per_entry_contract_required"


class PendingMutationScopeError(ContentMutationError):
    """pending mutation 的 project/wp/entry/user 与本次 commit 不同 scope（Property 10）。"""

    error_code = "pending_mutation_scope_mismatch"


class PendingMutationExpiredError(ContentMutationError):
    """pending mutation 已过 TTL（Property 10 的「过期必须拒绝」）。"""

    error_code = "pending_mutation_expired"


class PendingMutationPayloadError(ContentMutationError):
    """同 Idempotency-Key 但 payload digest / expected revision 不同（Property 10）。"""

    error_code = "pending_mutation_payload_mismatch"


class PendingMutationStateError(ContentMutationError):
    """pending mutation 处于不可消费状态（invalidated / 已被别的 commit 占用）。"""

    error_code = "pending_mutation_state_invalid"


class RepresentationLaneRequiredError(ContentMutationError):
    """`bidirectional` entry 走了 html-only lane（Requirement 3.1 明令禁止的形态）。

    Task 18 的第一条硬约束是「bidirectional flush 只形成 pending mutation，由
    :meth:`ContentMutationService.commit` 单次提交 projection **与** representation」。
    如果 bidirectional entry 能走 html-only lane，那就等于「先提交 projection-only
    revision，再补 artifact」—— design 明确拒绝的方案 #20。这条异常让那个禁令有
    可执行判据。
    """

    error_code = "bidirectional_requires_representation_lane"


class HtmlOnlyCapabilityMismatchError(ContentMutationError):
    """html-only lane 收到了 `single_onlyoffice` / `unreachable` 声明。

    🔴 与 :class:`RepresentationLaneRequiredError` 分两类，理由与本模块其他成对异常
    一致：**两条拒绝必须能被独立 falsify**。共用一个类型时，把 bidirectional 那条
    `if` 短路掉会被这一条接住、抛出同样的 `error_code`，于是「bidirectional 不得走
    projection-only lane」这条判据变成不可达分支（本任务变异检验 M10 实测到这一点）。
    """

    error_code = "html_only_lane_capability_mismatch"


class HtmlOnlyEntryHasRepresentationError(ContentMutationError):
    """html-only lane 被用在**已有 published representation** 的 entry 上。

    🔴 与 :class:`RepresentationLaneRequiredError` 分两类，因为判据来源不同、可被
    独立 falsify：前者判的是**调用方声明的 capability**（可以写错），后者判的是
    **数据库事实**（该 entry 已经有 OO 侧 current pointer）。只留声明侧判据的话，
    某个 entry 日后被真的接上 OO、而调用方仍传 `single_html`，就会静默地让 HTML 与
    OO 分叉 —— 那正是本 spec 要消灭的形态。
    """

    error_code = "html_only_entry_has_representation"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 常量
# ═══════════════════════════════════════════════════════════════════════════

#: 业务 commit 事务内必须留下见证的五步。**顺序即语义**：先 CAS 推进 revision（乐观锁
#: 在此生效），再写不可变行，最后写 pointer 与 outbox。
CONTENT_COMMIT_STEPS: tuple[str, ...] = (
    "revision",
    "content_version",
    "representation",
    "entry_pointer",
    "outbox",
)

#: `single_html` 业务 commit 事务内必须留下见证的四步。**刻意比
#: :data:`CONTENT_COMMIT_STEPS` 少两步**：`single_html` entry 按定义没有 OO
#: representation，也就没有 entry pointer 可写（Requirement 3.9：「single_html entry
#: SHALL 不创建空白 OO artifact」）。
#:
#: 🔴 为什么不复用 :data:`CONTENT_COMMIT_STEPS` 再「跳过」两步：那样 bidirectional
#: 路径的「representation 必须同事务写」这条判据就会多出一个可绕过的分支 ——
#: 只要谁把 mutation 声明成 html-only，representation 缺失就不再打红。两个**互不
#: 重叠**的必需步骤元组才能让两条 lane 各自可 falsify。
HTML_ONLY_COMMIT_STEPS: tuple[str, ...] = (
    "revision",
    "content_version",
    "current_pointer",
    "outbox",
)

#: html-only lane 的 scope entry_id 命名空间。单一声明处：`wp_html_save` 经
#: :func:`html_only_entry_id` 取值，不在 router 里再拼一次字面量（否则两处一漂移，
#: 同一底稿会落到两个 scope 下）。前缀同时保证它与 Task 1 manifest 的 `entry_id`
#: （形如 `<host>#<mount>`）不可能撞键。
HTML_ONLY_ENTRY_PREFIX: str = "html-only:"

#: html-only projection 的 canonical 载荷 schema 版本。它进内容寻址 digest，所以
#: 载荷结构变化必须同时 +1，否则同一份业务内容在新旧代码下算出同一个 hash。
HTML_PROJECTION_SCHEMA_VERSION: str = "workpaper-html-projection:v1"

#: design §outbox 明列的 payload 键。守卫按**集合包含**断言，多余的扩展键允许
#: （Requirement 13.2：typed replay 不得丢 `extra`）。
EVENT_PAYLOAD_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "wp_id",
        "project_id",
        "revision",
        "operation_id",
        "source",
        "adapter_id",
        "file_sha256",
    }
)

#: html-only lane 的 outbox payload 必填键。没有 `adapter_id` / `representation_*`
#: （这条 lane 按定义没有 adapter 与 OOXML representation），但 `revision` 与
#: `file_sha256`（= projection digest）必须在，否则下游无从判断「按哪个版本刷新」。
HTML_ONLY_EVENT_PAYLOAD_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "wp_id",
        "project_id",
        "revision",
        "source",
        "file_sha256",
        "entry_id",
        "content_version_id",
        "authority_model",
    }
)

#: business revision 域的写入方法。:class:`RevisionLockedRepository` 对它们恒抛。
REVISION_DOMAIN_WRITE_METHODS: frozenset[str] = frozenset(
    {
        "bump_content_revision",
        "set_current_content_version",
        "create_content_version",
    }
)

#: `working_paper_content_version.source` 的封闭词表（与 V152 `ck_wpcv_source` 同集合）。
#:
#: 🔴 `upload` / `wopi` 由 Task 19 的 V152 迁移补入。它们不能折进 `onlyoffice`：
#: `source` 是 evidence 与 timeline 的分桶依据，把「桌面 Excel 离线改完上传」和
#: 「Office online WOPI PutFile」都记成 `onlyoffice`，事后就无法再区分走的哪条协议
#: （无 room/generation/forcesave request 的两条路径与 OO room 生命周期完全不同）。
_ALLOWED_SOURCES: frozenset[str] = frozenset(
    {"html", "onlyoffice", "conflict_resolution", "rollback", "custom", "upload", "wopi"}
)

#: room 进入 `refresh_required` 的原因（V151 `ck_wpoor_refresh_reason` 禁止静默 refresh）。
REFRESH_REASON_MERGED_NOT_EQUAL_INCOMING: str = "merged_projection_differs_from_incoming"


class ContentSource(str):
    """业务内容来源。值域与 V151 `ck_wpcv_source` 逐字一致。

    刻意不是 `Enum` 而是带校验的 `str` 子类：writer 迁移期（Tasks 18/19）会从既有代码
    里传字符串过来，`ContentSource("upload")` 应当在**构造点**就报错，而不是等到
    数据库 CHECK 才炸出一个看不出哪来的 `IntegrityError`。
    """

    __slots__ = ()

    def __new__(cls, value: str) -> "ContentSource":
        text = str(value)
        if text not in _ALLOWED_SOURCES:
            raise ContentMutationError(
                f"content version source={text!r} 不在封闭词表 "
                f"{sorted(_ALLOWED_SOURCES)} 内（V151 ck_wpcv_source）"
            )
        return super().__new__(cls, text)


HTML = ContentSource("html")
ONLYOFFICE = ContentSource("onlyoffice")
CONFLICT_RESOLUTION = ContentSource("conflict_resolution")
ROLLBACK = ContentSource("rollback")
CUSTOM = ContentSource("custom")
UPLOAD = ContentSource("upload")
WOPI = ContentSource("wopi")


# ═══════════════════════════════════════════════════════════════════════════
# 2. 单事务见证与 commit 计数
# ═══════════════════════════════════════════════════════════════════════════


class _TransactionWitness:
    """记录每一步写入所在的 PostgreSQL 事务 id，用来证明它们真在**同一个**事务里。

    为什么不用「数一数源码里有几个 `commit()`」：那是字符串判据（假绿第②源），改个
    变量名、走个 helper、或者让 `publish_pending(commit=True)` 顺手提交，都能绕过。
    `pg_current_xact_id()` 是数据库对「你现在在哪个事务里」的回答，绕不过去。

    非 PostgreSQL 方言上这条 SQL 会直接报错 —— 刻意不 fallback：本模块的原子性承诺
    依赖真实事务语义，静默降级等于把唯一判据抹掉。
    """

    __slots__ = ("_required", "_stamps")

    def __init__(self, required_steps: Sequence[str] = CONTENT_COMMIT_STEPS) -> None:
        self._required: tuple[str, ...] = tuple(required_steps)
        self._stamps: list[tuple[str, str]] = []

    async def stamp(self, session: AsyncSession, step: str) -> str:
        xid = (
            await session.execute(sa.text("SELECT pg_current_xact_id()::text"))
        ).scalar_one()
        self._stamps.append((step, str(xid)))
        return str(xid)

    @property
    def stamps(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._stamps)

    @property
    def transaction_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for _, xid in self._stamps:
            if xid not in seen:
                seen.append(xid)
        return tuple(seen)

    def assert_single_transaction(self) -> None:
        """必需步骤齐全 **且** 全部落在同一个事务里。

        两条判据、两个异常类型：缺步骤是「写入被移出/删掉」，多事务是「中途提交」。
        """
        seen_steps = {step for step, _ in self._stamps}
        missing = [step for step in self._required if step not in seen_steps]
        if missing:
            raise TransactionStepMissingError(
                f"业务 commit 事务里缺少步骤 {missing} —— 只提交一部分就是 "
                "Requirement 3.1 禁止的「projection-only commit 后再补」的前半段"
                f"（实际见证: {self._stamps}）"
            )
        distinct = self.transaction_ids
        if len(distinct) != 1:
            raise TransactionSplitError(
                f"业务 commit 的写入落在 {len(distinct)} 个数据库事务里 {distinct} —— "
                "content version / revision / representation / entry pointer / outbox "
                "必须同生共死（Requirement 2.4 / 13.1）"
                f"；逐步见证: {self._stamps}"
            )


class _CommitLatch:
    """一次 `commit()` 只允许一次 `session.commit()`。"""

    __slots__ = ("_count",)

    def __init__(self) -> None:
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    async def commit_once(self, session: AsyncSession) -> None:
        if self._count:
            raise DoubleCommitError(
                "一次业务 mutation 只允许一次 commit —— 第二次提交必然意味着"
                "「先提交 projection-only version，再补 artifact/revision」"
                "（Requirement 3.1 / Property 10）"
            )
        self._count += 1
        await session.commit()


# ═══════════════════════════════════════════════════════════════════════════
# 3. revision 域门面
# ═══════════════════════════════════════════════════════════════════════════


class RevisionLockedRepository:
    """把 business revision 域的写入面从仓储上**摘掉**的门面。

    `RepresentationService`（纯表示升级）拿到的就是它。三个被摘掉的方法不是「约定
    不要调」，而是调用即抛 —— 于是「纯定义升级递增 content revision」这条禁令有了
    可执行判据，变异检验能证明它可 falsify（往 `representations.py` 注入一次
    `bump_content_revision` ⇒ 守卫红）。

    其余方法一律透传，因此它不是第二套仓储：没有复制任何写入逻辑。
    """

    __slots__ = ("_inner",)

    def __init__(self, inner: WorkpaperSyncRepository) -> None:
        self._inner = inner

    @property
    def inner(self) -> WorkpaperSyncRepository:
        return self._inner

    @property
    def session(self) -> AsyncSession:
        return self._inner.session

    def __getattr__(self, name: str) -> Any:
        if name in REVISION_DOMAIN_WRITE_METHODS:
            raise RevisionBumpForbiddenError(
                f"`{name}` 属 business revision 域，纯表示/definition 升级路径不得调用 —— "
                "content revision 只由 ContentMutationService.commit(...) 的唯一业务"
                "事务推进（Requirement 2.1 / Property 4）"
            )
        return getattr(self._inner, name)


# ═══════════════════════════════════════════════════════════════════════════
# 4. 输入 / 输出
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ContentCommitPlan:
    """一次业务 commit 的**冻结身份**。构造后不可变，且不携带任何写入能力面。

    `assert_no_mutation_surface` 在 `__post_init__` 里逐字段实测「没有 session /
    repository / outbox」：plan 会被塞进 operation/evidence 做审计快照，一旦它握着
    session，"adapter 与 plan 都不能 commit" 这条边界就只是注释。
    """

    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    source: ContentSource
    expected_revision: int
    bundle: DefinitionBundleSnapshot
    adapter_id: str
    adapter_build_digest: str
    document_type: str
    substrate_path: Path
    substrate_role: SubstrateRole
    substrate_kind: ArtifactKind
    substrate_state: ArtifactState
    actor_id: uuid.UUID | None = None
    operation_id: uuid.UUID | None = None
    parent_version_id: uuid.UUID | None = None
    contract: SyncContract | None = None
    room_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    pending_mutation_id: uuid.UUID | None = None
    idempotency_key: str | None = None
    reason: str = "content_commit"

    def __post_init__(self) -> None:
        assert_no_mutation_surface(self, label="ContentCommitPlan")
        if self.expected_revision < 0:
            raise ContentMutationError(
                f"expected_revision 不得为负: {self.expected_revision}"
            )
        if not isinstance(self.source, ContentSource):
            # 直接构造 `source="html"` 的调用方也要走封闭词表校验。
            object.__setattr__(self, "source", ContentSource(self.source))
        if not is_digest(self.adapter_build_digest):
            raise ContentMutationError(
                f"adapter_build_digest 必须是 64 位小写 hex，实得 {self.adapter_build_digest!r}"
            )
        if self.reason not in ("content_commit", "rollback", "rematerialize"):
            raise ContentMutationError(
                f"业务 commit 的 representation reason 只能是 content_commit / rollback / "
                f"rematerialize（definition_upgrade 属 RepresentationService），实得 {self.reason!r}"
            )
        if not self.entry_id or not self.entry_id.strip():
            raise ContentMutationError("entry_id 不得为空")

    @property
    def target_revision(self) -> int:
        """本次 commit 预定推进到的 revision。

        artifact 的内容寻址文件名里带 revision，所以它必须在 stage 阶段就确定；
        真正的并发裁决由事务内的 CAS（`bump_content_revision`）做，两者不一致即
        :class:`RevisionTargetError`。
        """
        return self.expected_revision + 1

    @property
    def authority_model(self) -> AuthorityModel:
        return self.bundle.authority_model

    @property
    def is_projection_based(self) -> bool:
        return self.authority_model is AuthorityModel.projection_contract


@dataclass(frozen=True)
class BusinessMutation:
    """要应用的业务内容本体。projection 与 authoritative 字节**二选一**。

    `merge` 只在 OO→HTML 出现：它带着三方合并的结论（冲突集、word_only 键、
    `requires_client_refresh` 判据）。本模块不重跑 merge —— 那是 Task 26 coordinator
    的活；这里只消费它的结论并**拒绝**未裁决冲突。
    """

    projection: Projection | None = None
    authoritative_payload: bytes | None = None
    merge: MergeOutcome | None = None
    incoming: Projection | None = None
    #: 人工裁决。`merge` 有冲突时**必填**且必须逐条覆盖，否则拒绝提交
    #: （判据走 Task 14 的 `assert_all_conflicts_resolved`）。
    resolution_choices: tuple[ResolutionChoice, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        assert_no_mutation_surface(self, label="BusinessMutation")
        if (self.projection is None) == (self.authoritative_payload is None):
            raise AuthorityModelMismatchError(
                "business mutation 必须**恰好**给一种内容：projection（标准结构化）"
                "或 authoritative_payload（custom/opaque 权威 OOXML）"
                f"；实得 projection={self.projection is not None} "
                f"authoritative={self.authoritative_payload is not None}"
            )
        # 🔴 三方 merge 只存在于 projection 路径。允许 `merge` 与 authoritative 字节共存，
        #    `_advance_room` 就得在「没有 settled projection」时决定 refresh —— 而唯一
        #    能拿到的替代品就是 `merge.merged`，那正是本轮要消灭的错值来源。
        if self.merge is not None and self.projection is None:
            raise AuthorityModelMismatchError(
                "带 MergeOutcome 的 business mutation 必须走 projection 路径 —— "
                "authoritative 字节路径没有受管 projection，三方 merge 无从落地"
            )
        if self.resolution_choices and self.merge is None:
            raise AuthorityModelMismatchError(
                f"给了 {len(self.resolution_choices)} 条人工裁决却没有 MergeOutcome —— "
                "裁决必须逐条对应某个 conflict set，否则无从核对折叠结果"
            )


@dataclass(frozen=True)
class ContentCommitReceipt:
    """一次业务 commit 的结果（含证明单事务与幂等所需的全部事实）。"""

    wp_id: uuid.UUID
    entry_id: str
    content_version_id: uuid.UUID
    revision: int
    representation_id: uuid.UUID
    representation_generation: int
    artifact_sha256: str
    projection_sha256: str | None
    definition_bundle_id: uuid.UUID
    definition_bundle_sha256: str
    authority_model: str
    operation_id: uuid.UUID | None
    replayed: bool
    requires_client_refresh: bool
    commit_count: int
    transaction_ids: tuple[str, ...]
    pending_event: PendingPublication | None
    event_payload: Mapping[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "wp_id": str(self.wp_id),
            "entry_id": self.entry_id,
            "content_version_id": str(self.content_version_id),
            "revision": self.revision,
            "representation_id": str(self.representation_id),
            "representation_generation": self.representation_generation,
            "artifact_sha256": self.artifact_sha256,
            "projection_sha256": self.projection_sha256,
            "definition_bundle_id": str(self.definition_bundle_id),
            "definition_bundle_sha256": self.definition_bundle_sha256,
            "authority_model": self.authority_model,
            "operation_id": str(self.operation_id) if self.operation_id else None,
            "replayed": self.replayed,
            "requires_client_refresh": self.requires_client_refresh,
            "commit_count": self.commit_count,
            "transaction_ids": list(self.transaction_ids),
        }


def html_only_entry_id(*, wp_code: str | None, wp_id: uuid.UUID) -> str:
    """html-only lane 的 scope entry_id（唯一构造处）。

    `wp_code` 是底稿的稳定业务身份，优先用它；`wp_index` 缺行时退回 `wp_id`
    （两者都非空 —— V151 的 `ck_wpssi_entry_non_empty` 不接受空串）。
    """
    stem = (wp_code or "").strip() or str(wp_id)
    return f"{HTML_ONLY_ENTRY_PREFIX}{stem}"[:200]


@dataclass(frozen=True)
class HtmlOnlyCommitPlan:
    """一次 `single_html` 业务 commit 的冻结身份。

    与 :class:`ContentCommitPlan` 的差别不是「简化版」，而是**另一条 authority
    model**：`single_html` entry 没有 approved definition bundle、没有 adapter、没有
    per-entry contract，也没有 OOXML representation。硬塞一个空 bundle 才是造假
    （Requirement 2.3 禁止空串/全零 hash 进 canonical bytes），所以这里根本不带
    bundle 字段。
    """

    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    expected_revision: int
    capability: Capability
    sheet_name: str
    schema_version: str
    actor_id: uuid.UUID | None = None
    parent_version_id: uuid.UUID | None = None
    trigger: str = "html_save"
    #: 🔴 Task 19：本次 projection 的业务来源，进 `working_paper_content_version.source`。
    #:
    #: 改造前这条 lane 把 `source` 写死成 `html`。那对 `wp_html_save` 是对的，但 Task 19
    #: 把「模板迁移回滚」与「历史快照回滚」两条恢复 writer 也接到了同一条 lane —— 它们
    #: 写的是同一种载荷（结构化 projection，无 OOXML 本体），来源却是 `rollback`。
    #: `source` 是 evidence 与 timeline 的分桶依据（Requirement 2.3 点名它必须落库），
    #: 写死会让一次回滚在审计轨迹里长得和一次用户编辑一模一样。
    #:
    #: 默认值保持 `html`，因此 `wp_html_save` 的行为逐字节不变。
    source: ContentSource = HTML

    def __post_init__(self) -> None:
        assert_no_mutation_surface(self, label="HtmlOnlyCommitPlan")
        object.__setattr__(
            self,
            "source",
            self.source if isinstance(self.source, ContentSource) else ContentSource(self.source),
        )
        if self.expected_revision < 0:
            raise ContentMutationError(
                f"expected_revision 不得为负: {self.expected_revision}"
            )
        if not self.entry_id or not self.entry_id.strip():
            raise ContentMutationError("entry_id 不得为空")
        if not self.sheet_name or not self.sheet_name.strip():
            raise ContentMutationError("sheet_name 不得为空")
        capability = (
            self.capability
            if isinstance(self.capability, Capability)
            else Capability(self.capability)
        )
        object.__setattr__(self, "capability", capability)
        if capability is Capability.bidirectional:
            raise RepresentationLaneRequiredError(
                f"entry {self.entry_id} 是 bidirectional —— HTML flush 只能形成 pending "
                "mutation，由 ContentMutationService.commit(...) 在**一次**业务事务里同时"
                "发布 projection 与兼容 representation。走 html-only lane 等于先提交一次"
                "projection-only revision 再补 artifact（Requirement 3.1 / design 明确"
                "拒绝的方案 #20）"
            )
        if capability is not Capability.single_html:
            raise HtmlOnlyCapabilityMismatchError(
                f"html-only lane 只服务 capability=single_html，实得 {capability.value} —— "
                "single_onlyoffice/custom 的权威内容是 OOXML 本体（Requirement 2.11），"
                "unreachable 入口不该有任何业务写入（Requirement 1.7）"
            )

    @property
    def target_revision(self) -> int:
        """本次 commit 预定推进到的 business revision。

        artifact 文件名里带 revision，因此它必须在 stage 阶段就确定；真正的并发裁决
        由事务内的 CAS 做，不一致即 :class:`RevisionTargetError`。
        """
        return self.expected_revision + 1

    @property
    def authority_model(self) -> AuthorityModel:
        """`single_html` 的权威内容就是 HTML 结构化 projection 本身。"""
        return AuthorityModel.projection_contract


@dataclass(frozen=True)
class StagedHtmlProjection:
    """事务**之前**已 publish 的 projection artifact（此刻无任何 DB 行引用它）。

    单独成型而不是塞进 commit：Requirement 2.4 的 staged artifact 协议要求
    「artifact 先耐久校验，随后在一个短数据库事务内写 pointer」。把 stage 与 commit
    做成两次调用，「文件先耐久」这条次序才在调用点可见、可断言。
    """

    artifact: PublishedArtifact
    payload_sha256: str
    payload_bytes: int
    revision: int


@dataclass(frozen=True)
class HtmlOnlyCommitReceipt:
    """一次 `single_html` 业务 commit 的结果。"""

    wp_id: uuid.UUID
    entry_id: str
    content_version_id: uuid.UUID
    revision: int
    projection_sha256: str
    authority_model: str
    commit_count: int
    transaction_ids: tuple[str, ...]
    pending_event: PendingPublication | None
    event_payload: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "wp_id": str(self.wp_id),
            "entry_id": self.entry_id,
            "content_version_id": str(self.content_version_id),
            "revision": self.revision,
            "projection_sha256": self.projection_sha256,
            "authority_model": self.authority_model,
            "commit_count": self.commit_count,
            "transaction_ids": list(self.transaction_ids),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 4b. commit fence hook（Task 26 追加；`fence=None` 时行为逐字节不变）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CommitTransactionFacts:
    """**已写入本事务、尚未 commit** 的结果身份。

    存在的唯一理由是 AC 8.12/10.10 要求 application result、operation timeline 与
    business projection/version/representation/pointer/outbox **同一个事务**。
    Task 26 的 coordinator 需要在这些行已经落盘、而事务还没提交的那个瞬间追加
    application/operation 的结果行 —— 拿不到这些 id 就只能在 commit **之后**补写，
    那正是「pointer 已发布而 application 还停在 rematerializing」的半成功态。
    """

    revision: int
    content_version_id: uuid.UUID
    representation_id: uuid.UUID
    representation_generation: int
    artifact_sha256: str
    projection_sha256: str | None
    requires_client_refresh: bool


@runtime_checkable
class CommitFenceHook(Protocol):
    """业务 commit 的三个**不可交换**回调点（Task 26 的最终授权 fence 挂在这里）。

    为什么是 hook 而不是让 coordinator 自己拼一遍事务：Requirement 2.1 / Property 61
    要求全平台**唯一** commit 边界就在 :meth:`ContentMutationService.commit`。
    coordinator 若为了「在 publish 前再验一次权限」而自建事务，`_CommitLatch` 与
    `_TransactionWitness` 这两道自证就绕过去了。所以顺序由本模块持有，判据由调用方注入。

    三个点各自对应 Task 26 正文的一句话：

    * :meth:`before_publish` —— 「先按同一 frozen bundle extract 等值并校验未管理区域，
      **再**重验 final authorization / generation·write fence / eligibility /
      artifact·bundle digest，全部通过后**才**发布新的 representation」；
    * :meth:`before_write` —— 「DB commit 前再次重验 project/visibility/workflow、
      generation/write fence、initiator epoch/contributors 与 bundle identity」，
      发生在 wp advisory+row lock **之后**、任何写入**之前**；
    * :meth:`after_pointers` —— 「单事务提交 …… application/operation timeline 与 outbox」。

    抛异常即中止：`_commit_once` 的 `except` 会 rollback 整个事务，`_stage_and_verify`
    抛出时连 publish 都不会发生（文件侧只剩 staging 临时目录）。
    """

    async def before_publish(
        self,
        *,
        artifact_sha256: str,
        structure_hash: str,
        identity_inventory_sha256: str,
        extracted_key_count: int,
    ) -> None: ...

    async def before_write(self, *, current_revision: int) -> None: ...

    async def after_pointers(self, facts: CommitTransactionFacts) -> None: ...


@dataclass(frozen=True)
class _StagedContent:
    """事务前已 publish 的文件侧产物（尚无任何 DB 行引用它 ⇒ 此刻是不可见 orphan）。"""

    representation: PublishedArtifact
    projection: PublishedArtifact | None
    materialize: MaterializeResult | None
    unmanaged: UnmanagedRegionReport | None
    structure_hash: str
    identity_inventory_sha256: str
    extracted_key_count: int


# ═══════════════════════════════════════════════════════════════════════════
# 5. 服务
# ═══════════════════════════════════════════════════════════════════════════


def _iter_file(path: Path, chunk: int = 1 << 20) -> Iterator[bytes]:
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                return
            yield block


class ContentMutationService:
    """业务内容的唯一提交边界。

    所有 writer（HTML save、上传、WOPI、OnlyOffice callback、冲突裁决、rollback）
    最终都要走 :meth:`commit`。Property 61 的守卫按 writer 清册核对这一点：任何
    生产写路径自己 `commit()` 或自己动 `file_version/_version` 都打红。
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: WorkpaperSyncRepository,
        artifacts: CanonicalArtifactRepository,
        resolution: CanonicalResolutionService,
        outbox: type[DurableEventOutboxService] = DurableEventOutboxService,
    ) -> None:
        self._session = session
        self._repo = repository
        self._artifacts = artifacts
        self._resolution = resolution
        self._outbox = outbox

    # ─────────────────────────────────────────────────────────────────
    # 5.1 唯一入口
    # ─────────────────────────────────────────────────────────────────

    async def commit(
        self,
        *,
        plan: ContentCommitPlan,
        mutation: BusinessMutation,
        adapter: Any = None,
        fence: CommitFenceHook | None = None,
    ) -> ContentCommitReceipt:
        """在一次 lock/expected revision 中提交业务 projection **与** 兼容 representation。

        `adapter` 是 Task 13 的 :class:`WorkpaperSyncAdapter`
        （projection-based 必填；custom/opaque 权威文件路径可为 None —— 那条路径没有
        受管 projection 可 materialize，xlsx 本体就是权威）。

        `fence` 是 Task 26 追加的**可选** :class:`CommitFenceHook`：
        `None`（HTML→OO、上传、rollback、html-only 全部如此）时本方法行为逐字节不变。
        OO→HTML 传入它，把「publish 前重验授权」「写库前重验授权」「同事务落
        application/operation 结果」三件事挂在本模块持有的固定顺序上。

        顺序即判据：

        1. 冻结身份校验（bundle approved + typed slots + contract↔bundle + substrate 准入）
        2. 幂等重放：pending mutation 已 committed ⇒ 直接返回既有 version/operation，
           **不产生第二个 revision**（Property 10）
        3. 未裁决冲突一律拒绝（不自动选边 —— 那是 Task 14 域的承诺）
        4. materialize → roundtrip 反读等值 → 未管理区域比对（全在事务外）
        5. publish artifact（文件侧；此刻还是不可见 orphan）
        6. **一个** DB 事务：revision CAS → content version → representation →
           entry pointer → room 基线 → outbox → 恰一次 commit
        """
        ctx = self._build_context(plan)
        ctx.assert_frozen_identity_consistent()
        assert_bundle_snapshot_finalizable(plan.bundle)
        assert_substrate_usable(
            role=plan.substrate_role,
            artifact_kind=plan.substrate_kind,
            artifact_state=plan.substrate_state,
        )
        self._assert_authority_shape(plan, mutation, adapter)

        replay = await self._replay_if_committed(plan)
        if replay is not None:
            return replay

        projection = self._settle_projection(plan, mutation)
        staged = await self._stage_and_verify(
            plan=plan, mutation=mutation, projection=projection, adapter=adapter, fence=fence
        )
        return await self._commit_once(
            plan=plan, mutation=mutation, projection=projection, staged=staged, fence=fence
        )

    # ─────────────────────────────────────────────────────────────────
    # 5.1b `single_html` lane（Task 18 / Requirement 2.1, 2.2, 3.9）
    # ─────────────────────────────────────────────────────────────────

    def stage_html_projection(
        self, *, plan: HtmlOnlyCommitPlan, html_data: Mapping[str, Any]
    ) -> StagedHtmlProjection:
        """把本次 HTML 业务内容 canonical 化、内容寻址发布成 projection artifact。

        **纯文件侧，不碰数据库。** 失败时数据库一行没动，调用方可以直接 5xx；成功后
        文件已耐久但对数据库不可见（Requirement 2.4 的 staged artifact 协议），
        commit 失败它就是 orphan，由 Task 11 的 reconciliation 收。
        """
        payload = canonical_json_bytes(
            {
                "schema_version": HTML_PROJECTION_SCHEMA_VERSION,
                "entry_id": plan.entry_id,
                "sheet_name": plan.sheet_name,
                "html_schema_version": plan.schema_version,
                "html_data": _json_safe(html_data),
            }
        )
        staged = self._artifacts.stage_bytes(
            project_id=plan.project_id,
            wp_id=plan.wp_id,
            payload=payload,
            document_type="json.gz",
            filename="html-projection.tmp",
        )
        published = self._artifacts.publish_projection(
            revision=plan.target_revision, staged=staged
        )
        return StagedHtmlProjection(
            artifact=published,
            payload_sha256=published.sha256,
            payload_bytes=published.size_bytes,
            revision=plan.target_revision,
        )

    async def commit_html_projection(
        self, *, plan: HtmlOnlyCommitPlan, staged: StagedHtmlProjection
    ) -> HtmlOnlyCommitReceipt:
        """`single_html` 业务内容的唯一提交出口 —— 恰**一次** business revision。

        与 :meth:`commit` 共用四道机制（单一 commit 出口 + 单事务见证 + 步骤完整性 +
        `bump_content_revision` CAS），只是必需步骤少了 `representation` 与
        `entry_pointer`：`single_html` entry 没有 OO artifact，凭空造一个空白 xlsx 正是
        Requirement 3.9 禁止的。

        调用方**必须**已经在同一 session 里写完业务内容（`parsed_data`）与
        `after_save` 的副作用行，且**不得**自己 commit —— 本方法是这笔事务的唯一提交
        出口，所以「HTML 内容 + 审计日志 + 耐久事件 + content version + revision」同生
        共死（Requirement 13.1）。

        Raises:
            RevisionConflictError: 并发保存（CAS 命中 0 行）⇒ 调用方应回 409。
            HtmlOnlyEntryHasRepresentationError: 该 entry 已有 published representation。
            TransactionSplitError / TransactionStepMissingError / DoubleCommitError:
                有人在中途 commit、把某一步移出事务，或提交了第二次。
        """
        if staged.revision != plan.target_revision:
            raise RevisionTargetError(
                f"staged projection 按 revision={staged.revision} 命名，本次 commit 预定 "
                f"{plan.target_revision} —— artifact 路径里的 revision 已错位"
            )
        witness = _TransactionWitness(HTML_ONLY_COMMIT_STEPS)
        latch = _CommitLatch()
        try:
            await self._assert_entry_has_no_representation(plan)

            # ① 乐观锁：advisory + 行锁 + expected 比对，随后 CAS 递增。
            #    这是**真**乐观锁（单条 `UPDATE ... WHERE content_revision = :expected`），
            #    取代旧实现里「拿 parsed_data['_version'] 去比 wp.file_version」的跨域断言。
            current = await self._repo.assert_expected_revision(
                plan.wp_id, plan.expected_revision
            )
            new_revision = await self._repo.bump_content_revision(plan.wp_id, current)
            await witness.stamp(self._session, "revision")
            if new_revision != plan.target_revision:
                raise RevisionTargetError(
                    f"CAS 后 revision={new_revision}，与本次 commit 预定的 "
                    f"{plan.target_revision} 不符 —— artifact 文件名里的 revision 已错位"
                )

            # ② projection artifact 行（文件已 publish，此前对 DB 不可见）
            proj_artifact = await self._repo.register_artifact(
                project_id=plan.project_id,
                wp_id=plan.wp_id,
                kind=ArtifactKind.projection,
                state=ArtifactState.published,
                relative_path=staged.artifact.relative_path,
                sha256=staged.artifact.sha256,
                size_bytes=staged.artifact.size_bytes,
                document_type=staged.artifact.document_type,
            )

            # ③ immutable content version
            version = await self._repo.create_content_version(
                project_id=plan.project_id,
                wp_id=plan.wp_id,
                entry_id=plan.entry_id,
                revision=new_revision,
                source=str(plan.source),
                parent_version_id=plan.parent_version_id,
                projection_artifact_id=proj_artifact.id,
                projection_sha256=staged.artifact.sha256,
                actor_id=plan.actor_id,
            )
            await witness.stamp(self._session, "content_version")

            # ④ current pointer（**只有** wp 级 current content version；没有 entry
            #    pointer —— 那是 representation 的 pointer，这条 lane 不产生 representation）
            await self._repo.set_current_content_version(plan.wp_id, version.id)
            await witness.stamp(self._session, "current_pointer")

            # ⑤ outbox：与 pointer 发布同事务（Requirement 13.1）
            payload = self._html_only_event_payload(
                plan=plan, revision=new_revision, version_id=version.id, staged=staged
            )
            pending_event = await self._outbox.enqueue(
                self._session,
                event_type=EventType.WORKPAPER_CONTENT_UPDATED,
                project_id=plan.project_id,
                payload=payload,
            )
            await witness.stamp(self._session, "outbox")

            # ⑥ 单事务自证 + 唯一提交出口
            witness.assert_single_transaction()
            await latch.commit_once(self._session)
        except Exception:
            await self._session.rollback()
            raise

        return HtmlOnlyCommitReceipt(
            wp_id=plan.wp_id,
            entry_id=plan.entry_id,
            content_version_id=version.id,
            revision=new_revision,
            projection_sha256=staged.artifact.sha256,
            authority_model=plan.authority_model.value,
            commit_count=latch.count,
            transaction_ids=witness.transaction_ids,
            pending_event=pending_event,
            event_payload=payload,
        )

    async def _assert_entry_has_no_representation(self, plan: HtmlOnlyCommitPlan) -> None:
        """数据库事实判据：该 entry 不得已有 current representation pointer。

        `plan.capability` 是**调用方声明**（可以写错、可以过期）。这一条查的是
        `working_paper_sync_entry_state` —— 一旦某个 entry 真的被接上 OO 并发布了
        representation，html-only lane 立刻打红而不是静默地让 HTML 与 OO 分叉。
        两条判据来源不同，因此可以各自被独立 falsify。
        """
        existing = (
            await self._session.execute(
                sa.select(sa.func.count())
                .select_from(WorkpaperSyncEntryState)
                .where(WorkpaperSyncEntryState.wp_id == plan.wp_id)
            )
        ).scalar_one()
        if int(existing or 0):
            raise HtmlOnlyEntryHasRepresentationError(
                f"wp {plan.wp_id} 已有 {existing} 个 entry representation pointer —— "
                "它不再是 single_html。HTML 保存必须走 pending mutation + "
                "ContentMutationService.commit(...) 的单次业务事务，否则 HTML 与 OO 分叉"
            )

    @staticmethod
    def _html_only_event_payload(
        *,
        plan: HtmlOnlyCommitPlan,
        revision: int,
        version_id: uuid.UUID,
        staged: StagedHtmlProjection,
    ) -> dict[str, Any]:
        """html-only lane 的 outbox payload。

        `file_sha256` 故意与 :meth:`_event_payload` 同名同义（「本次内容的权威 artifact
        digest」），下游 consumer 不必按 lane 分叉解析。
        """
        return {
            "wp_id": str(plan.wp_id),
            "project_id": str(plan.project_id),
            "revision": int(revision),
            "operation_id": None,
            # Task 19：与 content version 的 `source` 同一个事实来源。写死 `html` 会让
            # 下游 consumer 把一次回滚当成一次用户编辑（两者的刷新语义不同）。
            "source": str(plan.source),
            "adapter_id": None,
            "file_sha256": staged.artifact.sha256,
            "entry_id": plan.entry_id,
            "content_version_id": str(version_id),
            "projection_sha256": staged.artifact.sha256,
            "authority_model": plan.authority_model.value,
            "capability": plan.capability.value,
            "sheet_name": plan.sheet_name,
            "trigger": plan.trigger,
            "requires_client_refresh": False,
            "content_revision_advanced": True,
            "reason": "content_commit",
        }

    # ─────────────────────────────────────────────────────────────────
    # 5.2 提交后发布（Requirement 13.1）
    # ─────────────────────────────────────────────────────────────────

    async def publish_committed_events(
        self, receipt: ContentCommitReceipt | HtmlOnlyCommitReceipt
    ) -> Mapping[str, Any]:
        """把本次 commit 的耐久事件发布出去。**必须**在 :meth:`commit` 之后调用。

        为什么不放在 `commit()` 里：`publish_pending` 自己要 commit 一次发布状态，
        混在业务事务里会让「一次业务 commit 恰有一次数据库提交」这条判据无法断言，
        也会把「发布失败」变成「业务回滚」（Requirement 13.4 要求相反：业务已提交、
        事件落 failed 由 worker 重放）。
        """
        if receipt.pending_event is None:
            return {"attempted": 0}
        report = await self._outbox.publish_pending(self._session, [receipt.pending_event])
        return report.as_dict()

    # ─────────────────────────────────────────────────────────────────
    # 5.3 身份与形态
    # ─────────────────────────────────────────────────────────────────

    def _build_context(self, plan: ContentCommitPlan) -> SyncContext:
        """构造 adapter 上下文。它**没有** session/repository/outbox 字段（Task 13 已实测）。"""
        return SyncContext(
            project_id=plan.project_id,
            wp_id=plan.wp_id,
            entry_id=plan.entry_id,
            adapter_id=plan.adapter_id,
            adapter_build_digest=plan.adapter_build_digest,
            # 事务前尚无新 content version/representation id：用 expected/当前代
            # 作为「基底身份」，adapter 只用它做只读校验，不写库。
            content_version_id=plan.parent_version_id or uuid.UUID(int=0),
            content_revision=plan.expected_revision,
            representation_id=uuid.UUID(int=0),
            representation_generation=1,
            document_type=plan.document_type,
            bundle=plan.bundle,
            substrate_path=plan.substrate_path,
            substrate_role=plan.substrate_role,
            contract=plan.contract,
            room_id=plan.room_id,
            application_id=plan.application_id,
        )

    def _assert_authority_shape(
        self, plan: ContentCommitPlan, mutation: BusinessMutation, adapter: Any
    ) -> None:
        """authority model ↔ 内容形态 ↔ contract 三者必须自洽。"""
        if plan.is_projection_based:
            if mutation.projection is None:
                raise AuthorityModelMismatchError(
                    "authority model=projection_contract 必须提交业务 projection，"
                    "不得用 authoritative OOXML 字节代替"
                )
            if plan.contract is None:
                raise ContractRequiredError(
                    f"projection-based entry {plan.entry_id} 缺 per-entry contract —— "
                    "不得降级为 contract-less 模式（Requirement 3.3）"
                )
            if adapter is None:
                raise ContractRequiredError(
                    "projection-based commit 必须给 adapter：materialize/extract/未管理区域"
                    "比对三步缺一不可（Requirement 3.4）"
                )
            mutation.projection.assert_matches_contract(plan.contract)
            return

        if mutation.authoritative_payload is None:
            raise AuthorityModelMismatchError(
                f"authority model={plan.authority_model.value} 的权威内容是 OOXML 本体，"
                "必须提交 authoritative_payload；标准结构化 JSON projection writer 不得改写它"
                "（Requirement 2.11）"
            )
        if plan.contract is not None:
            raise AuthorityModelMismatchError(
                f"authority model={plan.authority_model.value} 不得携带 per-entry contract "
                "—— custom/opaque 入口的 contract slot 必须是版本化 typed null marker"
            )

    # ─────────────────────────────────────────────────────────────────
    # 5.4 幂等重放（Property 10）
    # ─────────────────────────────────────────────────────────────────

    async def _load_pending_mutation(
        self, plan: ContentCommitPlan
    ) -> WorkpaperPendingMutation | None:
        if plan.pending_mutation_id is None:
            return None
        row = (
            await self._session.execute(
                sa.select(WorkpaperPendingMutation)
                .where(WorkpaperPendingMutation.id == plan.pending_mutation_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise PendingMutationStateError(
                f"pending mutation 不存在: {plan.pending_mutation_id}"
            )
        # 🔴 四条拒绝各自一个异常类型：Property 10 要求「跨 scope、过期、同 key 不同
        #    payload」都必须拒绝，共用类型时短路任一条都会被其余条遮蔽。
        if (
            row.project_id != plan.project_id
            or row.wp_id != plan.wp_id
            or row.entry_id != plan.entry_id
        ):
            raise PendingMutationScopeError(
                f"pending mutation {row.id} 属于 scope "
                f"({row.project_id}/{row.wp_id}/{row.entry_id})，"
                f"与本次 commit ({plan.project_id}/{plan.wp_id}/{plan.entry_id}) 不同 —— "
                "token 跨 scope 一律拒绝"
            )
        if row.expires_at <= _now():
            raise PendingMutationExpiredError(
                f"pending mutation {row.id} 已过期（expires_at={row.expires_at.isoformat()}）"
                " —— 过期 token 不得被消费，请重新 flush"
            )
        if int(row.expected_revision) != int(plan.expected_revision):
            raise PendingMutationPayloadError(
                f"pending mutation {row.id} 冻结的 expected_revision="
                f"{row.expected_revision}，本次 commit 声明 {plan.expected_revision} —— "
                "同 Idempotency-Key 不同 content base 必须拒绝"
            )
        if plan.idempotency_key is not None and row.idempotency_key != plan.idempotency_key:
            raise PendingMutationPayloadError(
                f"pending mutation {row.id} 的 idempotency_key={row.idempotency_key!r} "
                f"与本次 commit 的 {plan.idempotency_key!r} 不同"
            )
        return row

    async def _replay_if_committed(
        self, plan: ContentCommitPlan
    ) -> ContentCommitReceipt | None:
        """已 committed 的 token 重放：返回**既有**结果，绝不产生第二个 revision。"""
        row = await self._load_pending_mutation(plan)
        if row is None:
            return None
        state = PendingMutationState(row.state)
        if state is PendingMutationState.committed:
            rep = (
                await self._session.execute(
                    sa.select(WorkpaperContentRepresentation)
                    .where(
                        WorkpaperContentRepresentation.content_version_id
                        == row.result_content_version_id,
                        WorkpaperContentRepresentation.entry_id == plan.entry_id,
                    )
                    .order_by(WorkpaperContentRepresentation.generation.desc())
                )
            ).scalars().first()
            if rep is None:
                raise PendingMutationStateError(
                    f"pending mutation {row.id} 标记 committed 但找不到 result "
                    "representation —— 这正是「projection-only commit」留下的半成功态"
                )
            revision = (
                await self._session.execute(
                    sa.text(
                        "SELECT revision FROM working_paper_content_version WHERE id = :cv"
                    ),
                    {"cv": str(row.result_content_version_id)},
                )
            ).scalar_one()
            return ContentCommitReceipt(
                wp_id=plan.wp_id,
                entry_id=plan.entry_id,
                content_version_id=row.result_content_version_id,  # type: ignore[arg-type]
                revision=int(revision),
                representation_id=rep.id,
                representation_generation=int(rep.generation),
                artifact_sha256=rep.artifact_sha256,
                projection_sha256=None,
                definition_bundle_id=rep.definition_bundle_id,
                definition_bundle_sha256=rep.definition_bundle_sha256,
                authority_model=plan.authority_model.value,
                operation_id=row.result_operation_id,
                replayed=True,
                requires_client_refresh=False,
                commit_count=0,
                transaction_ids=(),
                pending_event=None,
                event_payload=None,
            )
        if state in (PendingMutationState.expired, PendingMutationState.invalidated):
            raise PendingMutationStateError(
                f"pending mutation {row.id} state={state.value}，不可消费"
            )
        return None

    # ─────────────────────────────────────────────────────────────────
    # 5.5 冲突门与 roundtrip（Property 65）
    # ─────────────────────────────────────────────────────────────────

    def _settle_projection(
        self, plan: ContentCommitPlan, mutation: BusinessMutation
    ) -> Projection | None:
        """取出要落库的 projection；冲突未裁决、或裁决未真正折叠进来即拒绝。

        判据直接用 Task 14 的 `assert_all_conflicts_resolved`（不写第二套）：

        * 一条冲突没有对应裁决 ⇒ :class:`UnresolvedConflictError`（**绝不**自动选边）；
        * 裁决指向不存在的冲突 ⇒ `UnknownConflictResolutionError`（防「裁决了别的
          conflict set」这种跨 application 串台）。

        🔴 覆盖率过了**还不够**。这里额外独立重算 `apply_resolutions` 并逐字节比对
        调用方交来的 projection：只校验覆盖率、然后把 `merge.merged` 原样落库，就是
        「审计师点了取 incoming、落库的是 current」那条静默错值路径
        （:class:`AdjudicationNotFoldedError` 的 docstring 写了四道关为什么都不拦）。
        重算而不是信任，是本模块对 roundtrip 一贯的做法。

        没有 `merge` 的路径（HTML→OO、上传、rollback）本就没有三方冲突，直接放行。
        """
        if mutation.merge is None or not mutation.merge.has_conflicts:
            return mutation.projection
        if not mutation.resolution_choices:
            raise UnresolvedConflictError(
                f"仍有 {mutation.merge.conflict_count} 条未裁决冲突，不得提交内容 —— "
                "merge 域绝不自动选边，必须先经人工裁决（apply_resolutions）"
            )
        assert_all_conflicts_resolved(
            mutation.merge.conflicts, mutation.resolution_choices
        )
        if plan.contract is None:
            raise ContractRequiredError(
                "带人工裁决的 commit 必须给 per-entry contract —— 折叠结果要按 contract "
                "的行身份/保护策略重算才能核对，缺 contract 就只能盲信调用方"
            )
        folded = apply_resolutions(
            mutation.merge, mutation.resolution_choices, contract=plan.contract
        )
        given = mutation.projection
        if given is None or projection_canonical_digest(
            given
        ) != projection_canonical_digest(folded):
            raise AdjudicationNotFoldedError(
                f"裁决覆盖率已过，但提交的 projection 与 `apply_resolutions` 的重算结果"
                f"不一致（提交 {projection_canonical_digest(given) if given else None}，"
                f"重算 {projection_canonical_digest(folded)}）—— "
                "`merge.merged` 对每个冲突字段保留 current 侧值，直接落它等于把审计师的"
                "选择静默换成 current（AC 8.3 / 8.12）"
            )
        return given

    async def _stage_and_verify(
        self,
        *,
        plan: ContentCommitPlan,
        mutation: BusinessMutation,
        projection: Projection | None,
        adapter: Any,
        fence: CommitFenceHook | None = None,
    ) -> _StagedContent:
        """materialize → 反读等值 → 未管理区域比对 → publish。**全部在 DB 事务之外。**"""
        if not plan.is_projection_based:
            return await self._stage_authoritative(plan, mutation, fence=fence)

        assert projection is not None and plan.contract is not None  # 由形态门保证
        stage_id = uuid.uuid4()
        work_dir = self._artifacts.layout.staging_dir(plan.project_id, plan.wp_id, stage_id)
        work_dir.mkdir(parents=True, exist_ok=True)
        output = work_dir / f"materialized.{plan.document_type}"

        materialized = adapter.materialize(
            substrate=plan.substrate_path,
            projection=projection,
            output=output,
            contract=plan.contract,
        )
        if not isinstance(materialized, MaterializeResult):
            raise ContentMutationError(
                f"adapter.materialize 必须返回 MaterializeResult，实得 {type(materialized)!r}"
            )

        extracted = adapter.extract(artifact=output, contract=plan.contract)
        self._assert_roundtrip_equivalent(
            intended=projection, extracted=extracted, contract=plan.contract
        )
        unmanaged = adapter.verify_unmanaged_regions(
            before=plan.substrate_path, after=output, contract=plan.contract
        )
        unmanaged.assert_equivalent()

        # 🔴 Task 26 的「publish 前最后一道 fence」就在这里：extract 等值与未管理区域
        # 都已通过、artifact 尚未进入 `.versions` 命名空间。放到 publish 之后就只剩
        # 「已发布再回滚」，而 publish 是内容寻址的不可变发布，回滚只能留 orphan。
        if fence is not None:
            await fence.before_publish(
                artifact_sha256=materialized.artifact_sha256,
                structure_hash=materialized.structure_hash,
                identity_inventory_sha256=materialized.identity_inventory_sha256,
                extracted_key_count=len(extracted.values),
            )

        staged_rep = self._artifacts.stage_stream(
            project_id=plan.project_id,
            wp_id=plan.wp_id,
            chunks=_iter_file(output),
            document_type=plan.document_type,
            filename="representation.tmp",
            expected_sha256=materialized.artifact_sha256,
        )
        published_rep = self._artifacts.publish_representation(
            entry_id=plan.entry_id,
            generation=await self._next_generation_probe(plan),
            staged=staged_rep,
        )
        projection_bytes = canonical_json_bytes(_projection_payload(projection))
        staged_proj = self._artifacts.stage_bytes(
            project_id=plan.project_id,
            wp_id=plan.wp_id,
            payload=projection_bytes,
            document_type="json.gz",
            filename="projection.tmp",
        )
        published_proj = self._artifacts.publish_projection(
            revision=plan.target_revision, staged=staged_proj
        )
        return _StagedContent(
            representation=published_rep,
            projection=published_proj,
            materialize=materialized,
            unmanaged=unmanaged,
            structure_hash=materialized.structure_hash,
            identity_inventory_sha256=materialized.identity_inventory_sha256,
            extracted_key_count=len(extracted.values),
        )

    async def _stage_authoritative(
        self,
        plan: ContentCommitPlan,
        mutation: BusinessMutation,
        *,
        fence: CommitFenceHook | None = None,
    ) -> _StagedContent:
        """custom/opaque：xlsx 本体是唯一权威，不 materialize、不投影、不改写。"""
        assert mutation.authoritative_payload is not None
        staged = self._artifacts.stage_bytes(
            project_id=plan.project_id,
            wp_id=plan.wp_id,
            payload=mutation.authoritative_payload,
            document_type=plan.document_type,
            filename="authoritative.tmp",
        )
        if fence is not None:
            # custom/opaque 也要过同一道 fence：它没有受管 projection 可反读，但
            # 「publish 前重验授权」这条与 authority model 无关（AC 10.10 无例外）。
            await fence.before_publish(
                artifact_sha256=staged.sha256,
                structure_hash=staged.sha256,
                identity_inventory_sha256=staged.sha256,
                extracted_key_count=0,
            )
        published = self._artifacts.publish_representation(
            entry_id=plan.entry_id,
            generation=await self._next_generation_probe(plan),
            staged=staged,
        )
        return _StagedContent(
            representation=published,
            projection=None,
            materialize=None,
            unmanaged=None,
            # custom 路径没有 instrumented identity 清册：用权威文件自身 digest 作为
            # 结构身份（Requirement 6.19：不得强行 instrumentation，也不得留空 hash）。
            structure_hash=published.sha256,
            identity_inventory_sha256=published.sha256,
            extracted_key_count=0,
        )

    async def _next_generation_probe(self, plan: ContentCommitPlan) -> int:
        """新 content version 的首个 generation 恒为 1。

        文件名里带 generation，所以要在 stage 阶段确定。业务 commit 一定伴随**新**
        content version（`uq_wpcr_generation` 按 content version 分组），故恒为 1；
        写成方法而不是字面量是为了让「有人把它改成按 entry 全局递增」这类回归有落点。
        """
        return 1

    def _assert_roundtrip_equivalent(
        self, *, intended: Projection, extracted: Projection, contract: SyncContract
    ) -> None:
        """反读出来的受管 projection 必须与要提交的逐字段等值（Property 65）。

        比较口径复用 `merge.values_equal`（金额 Decimal / 日期 ISO / 文本仅归一
        CRLF），不自己写第二套。`word_only` 字段被排除：它们按定义永不进 HTML
        projection，拿它们比较会让 Word 底稿恒判不等值。
        """
        word_only = {
            spec.stable_field_key
            for spec in contract.all_fields()
            if spec.mode is FieldMode.word_only
        }

        def _managed(proj: Projection) -> dict[str, Any]:
            return {
                key: value
                for key, value in proj.values.items()
                if not any(
                    key == tpl or key.startswith(tpl.split("{row_uuid}")[0])
                    for tpl in word_only
                    if "{row_uuid}" in tpl
                )
                and key not in word_only
            }

        left = _managed(intended)
        right = _managed(extracted)
        missing = sorted(set(left) - set(right))
        if missing:
            raise RoundtripEquivalenceError(
                f"staged representation 反读后缺少受管字段 {missing[:5]}"
                f"（共 {len(missing)} 个）—— materialize 没有把它们写进 OOXML，"
                "或 extract 找不到 identity 载体"
            )
        extra = sorted(set(right) - set(left))
        if extra:
            raise RoundtripEquivalenceError(
                f"staged representation 反读出未提交的受管字段 {extra[:5]}"
                f"（共 {len(extra)} 个）—— 受管区域被写入了不属于本次 projection 的值"
            )
        for key in sorted(left):
            mine, theirs = left[key], right[key]
            if not values_equal(mine.value, theirs.value, mine.value_type):
                raise RoundtripEquivalenceError(
                    f"受管字段 {key} 反读不等值：提交 {mine.value!r} → 反读 {theirs.value!r}"
                    f"（value_type={mine.value_type.value}）—— Property 65 要求 projection "
                    "与同 revision representation 等值"
                )

    # ─────────────────────────────────────────────────────────────────
    # 5.6 唯一事务
    # ─────────────────────────────────────────────────────────────────

    async def _commit_once(
        self,
        *,
        plan: ContentCommitPlan,
        mutation: BusinessMutation,
        projection: Projection | None,
        staged: _StagedContent,
        fence: CommitFenceHook | None = None,
    ) -> ContentCommitReceipt:
        """content version / revision / representation / entry pointer / outbox 同生共死。"""
        witness = _TransactionWitness(CONTENT_COMMIT_STEPS)
        latch = _CommitLatch()
        try:
            pending_row = await self._load_pending_mutation(plan)
            if pending_row is not None:
                state = PendingMutationState(pending_row.state)
                assert_transition(
                    "pending_mutation", state, PendingMutationState.committing
                )
                pending_row.state = PendingMutationState.committing.value
                await self._session.flush()
                if plan.operation_id is None:
                    raise PendingMutationStateError(
                        "消费 pending mutation 必须给 operation_id：V151 的 "
                        "`ck_wppm_committed_result` 要求 committed 同时留下可重放的 "
                        "operation + content version，否则重放会二次提交"
                    )

            # ① 乐观锁：advisory + 行锁 + expected 比对，随后 CAS 递增
            current = await self._repo.assert_expected_revision(
                plan.wp_id, plan.expected_revision
            )
            # 🔴 Task 26 的「DB commit 前最后一次授权重验」：**在 wp 锁之内、任何写之前**。
            # 放在锁之前会留出「验完到取锁之间被撤权」的窗口；放在第一次写之后则一旦
            # fence 失败就要靠 rollback 撤销已写行，而 revision CAS 是外部可观测的。
            if fence is not None:
                await fence.before_write(current_revision=current)
            new_revision = await self._repo.bump_content_revision(plan.wp_id, current)
            await witness.stamp(self._session, "revision")
            if new_revision != plan.target_revision:
                raise RevisionTargetError(
                    f"CAS 后 revision={new_revision}，与本次 commit 预定的 "
                    f"{plan.target_revision} 不符 —— artifact 文件名里的 revision 已错位"
                )

            # ② artifact 行（文件已 publish，此前对 DB 不可见）
            rep_artifact = await self._repo.register_artifact(
                project_id=plan.project_id,
                wp_id=plan.wp_id,
                kind=ArtifactKind.canonical,
                state=ArtifactState.published,
                relative_path=staged.representation.relative_path,
                sha256=staged.representation.sha256,
                size_bytes=staged.representation.size_bytes,
                document_type=staged.representation.document_type,
                created_by_operation_id=plan.operation_id,
            )
            proj_artifact = None
            if staged.projection is not None:
                proj_artifact = await self._repo.register_artifact(
                    project_id=plan.project_id,
                    wp_id=plan.wp_id,
                    kind=ArtifactKind.projection,
                    state=ArtifactState.published,
                    relative_path=staged.projection.relative_path,
                    sha256=staged.projection.sha256,
                    size_bytes=staged.projection.size_bytes,
                    document_type=staged.projection.document_type,
                    created_by_operation_id=plan.operation_id,
                )

            # ③ immutable content version
            version = await self._repo.create_content_version(
                project_id=plan.project_id,
                wp_id=plan.wp_id,
                entry_id=plan.entry_id,
                revision=new_revision,
                source=str(plan.source),
                parent_version_id=plan.parent_version_id,
                projection_artifact_id=proj_artifact.id if proj_artifact else None,
                projection_sha256=staged.projection.sha256 if staged.projection else None,
                authoritative_artifact_id=(
                    rep_artifact.id if staged.projection is None else None
                ),
                authoritative_artifact_sha256=(
                    staged.representation.sha256 if staged.projection is None else None
                ),
                operation_id=plan.operation_id,
                actor_id=plan.actor_id,
            )
            await witness.stamp(self._session, "content_version")

            # ④ 兼容 representation（**同一次** commit，不是第二次）
            generation = await next_representation_generation(
                self._session,
                wp_id=plan.wp_id,
                entry_id=plan.entry_id,
                content_version_id=version.id,
            )
            representation = await self._repo.create_representation(
                project_id=plan.project_id,
                wp_id=plan.wp_id,
                entry_id=plan.entry_id,
                content_version_id=version.id,
                generation=generation,
                document_type=plan.document_type,
                artifact_id=rep_artifact.id,
                artifact_sha256=staged.representation.sha256,
                definition_bundle_id=plan.bundle.bundle_id,
                authority_model_definition_id=plan.bundle.authority_model_definition_id,
                adapter_id=plan.adapter_id,
                adapter_build_digest=plan.adapter_build_digest,
                structure_hash=staged.structure_hash,
                identity_inventory_sha256=staged.identity_inventory_sha256,
                reason=plan.reason,
            )
            await witness.stamp(self._session, "representation")

            # ⑤ current pointers
            await self._repo.set_entry_pointer(
                wp_id=plan.wp_id,
                entry_id=plan.entry_id,
                representation_id=representation.id,
                generation=generation,
            )
            await self._repo.set_current_content_version(plan.wp_id, version.id)
            await witness.stamp(self._session, "entry_pointer")

            # ⑥ room 双基线（server last-applied 总推进；client-confirmed 只在等值时推进）
            requires_refresh = await self._advance_room(
                plan=plan, mutation=mutation, settled=projection, version_id=version.id
            )

            # ⑥b Task 26：application result + operation timeline 与上面各行**同事务**
            if fence is not None:
                await fence.after_pointers(
                    CommitTransactionFacts(
                        revision=new_revision,
                        content_version_id=version.id,
                        representation_id=representation.id,
                        representation_generation=generation,
                        artifact_sha256=staged.representation.sha256,
                        projection_sha256=(
                            staged.projection.sha256 if staged.projection else None
                        ),
                        requires_client_refresh=requires_refresh,
                    )
                )

            # ⑦ pending mutation 落 committed（重放从此返回既有结果）
            if pending_row is not None:
                assert_transition(
                    "pending_mutation",
                    PendingMutationState.committing,
                    PendingMutationState.committed,
                )
                pending_row.state = PendingMutationState.committed.value
                pending_row.result_operation_id = plan.operation_id
                pending_row.result_content_version_id = version.id
                pending_row.committed_at = _now()
                await self._session.flush()

            # ⑧ outbox：与 pointer 发布同事务（Requirement 13.1）
            payload = self._event_payload(
                plan=plan,
                revision=new_revision,
                version_id=version.id,
                representation=representation,
                artifact_sha256=staged.representation.sha256,
                projection_sha256=(
                    staged.projection.sha256 if staged.projection else None
                ),
                requires_client_refresh=requires_refresh,
            )
            pending_event = await self._outbox.enqueue(
                self._session,
                event_type=EventType.WORKPAPER_CONTENT_UPDATED,
                project_id=plan.project_id,
                payload=payload,
            )
            await witness.stamp(self._session, "outbox")

            # ⑨ 单事务自证 + 唯一提交出口
            witness.assert_single_transaction()
            await latch.commit_once(self._session)
        except Exception:
            await self._session.rollback()
            raise

        return ContentCommitReceipt(
            wp_id=plan.wp_id,
            entry_id=plan.entry_id,
            content_version_id=version.id,
            revision=new_revision,
            representation_id=representation.id,
            representation_generation=generation,
            artifact_sha256=staged.representation.sha256,
            projection_sha256=staged.projection.sha256 if staged.projection else None,
            definition_bundle_id=plan.bundle.bundle_id,
            definition_bundle_sha256=plan.bundle.bundle_sha256,
            authority_model=plan.authority_model.value,
            operation_id=plan.operation_id,
            replayed=False,
            requires_client_refresh=requires_refresh,
            commit_count=latch.count,
            transaction_ids=witness.transaction_ids,
            pending_event=pending_event,
            event_payload=payload,
        )

    async def _advance_room(
        self,
        *,
        plan: ContentCommitPlan,
        mutation: BusinessMutation,
        settled: Projection | None,
        version_id: uuid.UUID,
    ) -> bool:
        """推进 room 的 server last-applied；返回是否需要编辑器重载新基线。

        AC 2.9 / 8.12：`last_applied_version_id` 每次成功应用都原子推进；
        `client_confirmed_base_version_id` **只在**「真正落库的受管 projection」与
        incoming 等值时才可推进，否则 room 进 `refresh_required` 并等 supersede/reopen。
        本模块只负责「判断 + 推进 server 侧」，generation rotation 归 Task 21/26。

        🔴 判据取 `settled`（= `_settle_projection` 的返回值，也就是**真正写进 content
        version 的那份**），不取 `mutation.merge.merged`。带人工裁决时两者不同：
        `merged` 对每个冲突字段保留 current 侧值，用它算 refresh 会得出「与 incoming
        等值、不必重载」，于是 client-confirmed 基线被推进到一份客户端从未见过的内容上
        （AC 8.12 末句正是禁止这个）。
        """
        requires_refresh = False
        if mutation.merge is not None and mutation.incoming is not None:
            if settled is None:  # pragma: no cover - BusinessMutation.__post_init__ 已保证
                raise AuthorityModelMismatchError(
                    "带 merge 的 business mutation 必须走 projection 路径 —— "
                    "没有 settled projection 就无法判定 client-confirmed 是否可推进"
                )
            requires_refresh = projection_requires_client_refresh(
                settled=settled,
                incoming=mutation.incoming,
                word_only_keys=mutation.merge.word_only_keys,
            )
        if plan.room_id is None:
            return requires_refresh
        room = await self._repo.lock_room(plan.room_id)
        # server last-applied：每次成功应用都推进（AC 2.9 前半句）。
        room.last_applied_version_id = version_id
        if requires_refresh and RoomState(room.state) is not RoomState.refresh_required:
            # 走登记的状态边而不是裸赋值：非法边（如 closed → refresh_required）必须抛。
            assert_transition("room", room.state, RoomState.refresh_required)
            room.state = RoomState.refresh_required.value
            # V151 的 `ck_wpoor_refresh_reason` 要求 refresh 必须留下原因与时间 ——
            # 「静默 refresh」会让审计师看到「要求重开」却查不到为什么。
            room.refresh_required_at = _now()
            room.refresh_reason = REFRESH_REASON_MERGED_NOT_EQUAL_INCOMING
        room.updated_at = _now()
        await self._session.flush()
        return requires_refresh

    # ─────────────────────────────────────────────────────────────────
    # 5.7 事件 payload
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _event_payload(
        *,
        plan: ContentCommitPlan,
        revision: int,
        version_id: uuid.UUID,
        representation: WorkpaperContentRepresentation,
        artifact_sha256: str,
        projection_sha256: str | None,
        requires_client_refresh: bool,
    ) -> dict[str, Any]:
        """design §outbox 的 payload（7 个必填键）+ 同步域扩展键。

        扩展键不是可选装饰：AC 8.12 要求 applied content version **同时**绑定 merged
        projection hash 与 result representation/bundle/authority identity，下游
        （evidence recomputer、前端 descriptor 校验）就靠它们做一致性核对。
        Requirement 13.2 要求 typed replay 原样保留 `extra`，所以这些键必须进 payload
        本体，而不是只写进日志。
        """
        return {
            "wp_id": str(plan.wp_id),
            "project_id": str(plan.project_id),
            "revision": int(revision),
            "operation_id": str(plan.operation_id) if plan.operation_id else None,
            "source": str(plan.source),
            "adapter_id": plan.adapter_id,
            "file_sha256": artifact_sha256,
            "entry_id": plan.entry_id,
            "content_version_id": str(version_id),
            "projection_sha256": projection_sha256,
            "representation_id": str(representation.id),
            "representation_generation": int(representation.generation),
            "definition_bundle_id": str(plan.bundle.bundle_id),
            "definition_bundle_sha256": plan.bundle.bundle_sha256,
            "authority_model": plan.authority_model.value,
            "adapter_build_digest": plan.adapter_build_digest,
            "requires_client_refresh": bool(requires_client_refresh),
            "content_revision_advanced": True,
            "reason": plan.reason,
        }


#: Task 26：本函数的实现已下沉到 `definitions.json_safe`（与 `canonical_json_bytes`
#: 同一模块），因为 `conflicts.ValueEnvelope.to_jsonb()` 也必须用它 —— 少了那一步，
#: 任何金额/日期字段的冲突在算 `conflict_set_digest` 时直接 `TypeError`。
#: 这里保留旧名做别名：输出对每个输入逐字节相同（Decimal 仍走 `format(v, "f")`），
#: 因此既有 projection artifact / event payload 的 digest 一个都不变。
_json_safe = json_safe


def projection_canonical_digest(projection: Projection) -> str:
    """projection 的 canonical digest —— 与落盘 projection artifact **同一口径**。

    Task 26 追加。存在的理由是防第二套口径：`_stage_and_verify` 用
    `stage_bytes(canonical_json_bytes(_projection_payload(p)))` 得到 projection artifact
    的 sha256，而 `working_paper_content_application.merged_projection_sha256` 必须与它
    逐字节相同（AC 8.12 要求 applied content version 同时绑定 merged projection hash 与
    result representation identity；两个 hash 出自两套序列化就等于没绑定）。

    因此本函数**只是**把那条链路的前两步提出来复用，绝不新写一份 payload 形态。
    PG 守卫 `test_application_merged_digest_equals_published_projection_artifact`
    正面比对这两个值。
    """
    import hashlib

    return hashlib.sha256(canonical_json_bytes(_projection_payload(projection))).hexdigest()


def _projection_payload(projection: Projection) -> dict[str, Any]:
    """把 projection 序列化成 canonical 可寻址载荷（内容寻址 digest 的输入）。

    只含语义：contract identity + 按 stable key 排序的值与类型 + 行序。**不含**
    UUID/时间戳/机器路径 —— 否则同一份业务内容每次算出不同 digest，
    「相同 projection ⇒ 幂等复用」（AC 3.6）永远不成立。
    """
    return {
        "schema_version": "workpaper-projection:v1",
        "contract_id": projection.contract_id,
        "semantic_version": projection.semantic_version,
        "document_type": projection.document_type,
        "values": {
            key: {
                "value": _json_safe(value.value),
                "value_type": value.value_type.value,
                "mode": value.mode.value,
                "row_key": value.row_key,
            }
            for key, value in sorted(projection.values.items())
        },
        "row_keys": {
            table: list(rows) for table, rows in sorted((projection.row_keys or {}).items())
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. 生产装配（Task 18：`wp_html_save` 的唯一构造处）
# ═══════════════════════════════════════════════════════════════════════════


def build_html_content_mutation_service(session: AsyncSession) -> ContentMutationService:
    """给 HTML save 路径装配 :class:`ContentMutationService`。

    `base_root` 取 `canonical_paths.BACKEND_ROOT` —— 与 `legacy_storage_root()` 同一个
    真源，因此 sync 命名空间（`storage/{project}/workpapers/.versions|.staging|...`）
    与 legacy 项目存储（`storage/projects/{project}`）落在同一卷、同一根下。
    Task 7 已实测同卷 `os.replace` 才能原子发布，跨卷会以 `CROSS_VOLUME_RENAME` 失败。

    🔴 为什么是函数而不是模块级单例：`ContentMutationService` 持有 session，而 session
    是 per-request 的。做成单例就会让第一个请求的事务边界被后续请求复用 —— 那类缺陷
    在单元测试里看不见，只在并发下表现为「偶发提交到别人的事务」。
    """
    from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT

    artifacts = CanonicalArtifactRepository(BACKEND_ROOT)
    return ContentMutationService(
        session=session,
        repository=WorkpaperSyncRepository(session),
        artifacts=artifacts,
        resolution=CanonicalResolutionService(session, artifacts),
    )
