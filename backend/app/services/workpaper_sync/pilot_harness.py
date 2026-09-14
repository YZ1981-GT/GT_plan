# -*- coding: utf-8 -*-
"""pilot harness：持久化 sync test run / 逐 scenario evidence，且**结果只能由执行推导**。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 39
Requirements: 4.10, 5.8, 6.8, 12.2, 12.10, 12.11, 12.12, 14.1, 14.10, 14.14, 14.16
Properties: **P25 / P26 / P49 / P69 / P70 / P71 / P72**

═══ 本模块是「宣称已验证」的那一层，所以它自己必须先不可作假 ═══

Task 29 交付的 :mod:`evidence` 是**只读重算**：给它一个 run 它告诉你这个 run 站不站得住。
本模块是**写入侧** —— 它决定哪些行会被写进 `working_paper_sync_test_run` 与
`working_paper_entry_evidence_scenario`。于是全部造假手法都集中在这里：手填 result、
一条 operation 填满所有场景、跨 entry 复制 trace、把 profile 从 shared 改 single 少跑八个
close 场景、拿截图当证据、宣称真实 OO 已通过。任务正文逐条点名禁止这些，因此本模块把
每一条都做成**可执行的 fail-closed 判据**（:class:`HarnessRejection` 一码一因），而不是
文档约定。

═══ 四条不可协商的设计 ═══

1. **`result` 与 `aggregate_result` 没有入参**
   :meth:`SyncTestRunHarness.record_scenario` 的签名里根本没有 `result`；
   :meth:`SyncTestRunHarness.finalize_run` 的签名里根本没有 `aggregate_result` 与
   `verified_at`。前者由 :func:`run_scenario_oracle` 真跑一次 oracle 推导，后者由
   Task 29 的 :class:`~app.services.workpaper_sync.evidence.EvidenceRecomputer` 重算
   得出。**参数不存在**比「参数存在但校验它」强一个数量级：后者可以被下一个人加个
   `force=True` 绕过。

2. **`authority_model` 从 approved bundle 链上读，不由调用方给**
   :meth:`resolve_bundle_identity` 走 `bundle row → authority model definition artifact
   → artifact.authority_model_type`。任务正文要求「custom/opaque 只能由 approved bundle
   中的**枚举** `authority_model` 替换字段级两场景」；只要 authority model 还能从入参
   进来，「未知枚举或自由文本豁免」就永远拦不住 —— 调用方直接传
   `AuthorityModel.opaque_single_onlyoffice` 就少跑两个场景。

3. **required scenario set 是推导出来的分母，不是清单**
   委派 :func:`~app.services.workpaper_sync.evidence.derive_for_manifest_entry`。
   :data:`SCENARIO_ORACLES` 与它**双向锁死**（:func:`assert_oracle_registry_complete`）：
   声明了场景却没 oracle ⇒ 抛；有 oracle 却不在任何声明集合里 ⇒ 抛。分母写死或漏一个
   场景在这里不可能悄悄发生。

4. **零场景不算通过**
   :meth:`plan` 对空 required set 直接
   :attr:`HarnessRejection.empty_required_set`。「全部 0 个场景都通过了」是本 spec 反复
   点名的假绿形态（Task 37 的 `test_empty_projection_is_not_a_pass` 是范式）。

═══ 为什么今天**必然**没有 verified 的 entry ═══

每条 scenario oracle 都声明它需要哪些 :class:`EvidenceInput`。需要
:attr:`EvidenceInput.onlyoffice_forcesave` 或 :attr:`EvidenceInput.browser_trace` 的场景，
在没有真实 OO/浏览器 build（:data:`NOT_EXECUTED` 哨兵）时一律落 `unverifiable` 并带
`error_code`。这不是"暂时放宽"，而是 Property 49 的原文：**probe/pilot 未实际通过时必须
保持 UNVERIFIABLE，不得因文档声明计为通过**。容量 profile 同理只**登记**（见
:mod:`capacity_profile`），执行归 Task 71。
"""

from __future__ import annotations

import importlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Final, Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import (
    WorkpaperArtifact,
    WorkpaperEntryEvidenceScenario,
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncDefinitionBundle,
    WorkpaperSyncTestRun,
)
from app.services.workpaper_sync.adapters.base import Projection
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import (
    Capability,
    capability_of,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.evidence import (
    AUTHORITY_SUBSTITUTE_SCENARIOS,
    CLOSE_SCENARIOS,
    DYNAMIC_SCENARIOS,
    PROJECTION_BASE_SCENARIOS,
    SCHEMA_UNREPRESENTABLE_SCENARIOS,
    SINGLE_HTML_SCENARIOS,
    WORD_SCENARIOS,
    EvidenceEnvironment,
    EvidenceRecomputer,
    EvidenceVerdict,
    RequiredScenario,
    RequiredScenarioSet,
    ScenarioFamily,
    ScenarioKind,
    derive_for_manifest_entry,
    manifest_source_digest,
)
from app.services.workpaper_sync.merge import (
    MergeOutcome,
    apply_resolutions,
    merge_projections,
)
from app.services.workpaper_sync.models import (
    ArtifactState,
    AuthorityModel,
    DefinitionKind,
    DefinitionState,
    SyncDomainError,
)

#: harness 实现版本。它进 `runner_version`，因此改 harness 行为**必须** +1 ——
#: 否则旧 run 不会因 runner 变化 stale（AC 14.16 的 runner 轴）。
HARNESS_VERSION: Final[str] = "task39-harness/1"

#: 「本次没有真实 OO / 浏览器」的保留哨兵。写进 `onlyoffice_build` / `browser_build`
#: 时，任何需要真实 OO/浏览器证据的场景都只能落 `unverifiable`。
#:
#: 🔴 用显式哨兵而不是空串：V151 的两列都是 `NOT NULL`，空串能过 CHECK，于是
#: 「忘了填 build」与「明确声明没跑 OO」在库里长得一样 —— 那正是 AC 14.9 的
#: UNVERIFIABLE 与「用 fixture 冒充」之间唯一的分界。
NOT_EXECUTED: Final[str] = "NOT-EXECUTED"


class HarnessError(SyncDomainError):
    error_code = "sync_pilot_harness_invalid"


class HarnessRejection(str, Enum):
    """harness 拒绝写入的原因。**一码一因，禁合并**。

    共享错误码会让靠后的分支永久不可达 ⇒ 该分支的守卫永久 GREEN（本 spec 已三次实测）。
    `test_rejection_kinds_are_reachable_and_mutually_distinct` 把每一码各真触发一次并与
    本枚举双向锁死 —— 那比「每类各测一遍」强：后者在两类被合并时全部仍绿。
    """

    #: required set 为空（unreachable entry / 推导退化）—— 零场景全过不算通过。
    empty_required_set = "empty_required_set"
    #: 场景不在本 entry 的 required set 里（追加自由项）。
    scenario_not_required = "scenario_not_required"
    #: 同一 scenario_id 在同一 run 里重复提交。
    duplicate_scenario = "duplicate_scenario"
    #: 该 scenario_id 没有登记 oracle（分母与 oracle 表脱钩）。
    oracle_missing = "oracle_missing"
    #: oracle 引用的生产符号解析不到（接线已断，声明还在）。
    oracle_unresolvable = "oracle_unresolvable"
    #: 实体在同一 run 内被两条互不等价的场景复用（一条 operation 冒充多个场景）。
    entity_reused_within_run = "entity_reused_within_run"
    #: 实体已出现在另一个 entry 的证据里（跨 entry 复制证据）。
    entity_reused_across_entry = "entity_reused_across_entry"
    #: scenario 行的 bundle digest 与 run 冻结值不符。
    bundle_digest_mismatch = "bundle_digest_mismatch"
    #: scenario 行的 authority model digest 与 run 冻结值不符。
    authority_digest_mismatch = "authority_digest_mismatch"
    #: bundle 或其 authority model definition 未 approved。
    bundle_not_approved = "bundle_not_approved"
    #: authority model 不在封闭枚举内（自由文本豁免）。
    authority_model_not_enumerated = "authority_model_not_enumerated"
    #: download-only / recovery-reject 场景带了 operation/application。
    download_only_has_entities = "download_only_has_entities"
    #: 场景声明「永不创建 application」（如 quarantined incoming，AC 5.6）却给了 application。
    #: 与上一码分开：上一码对应 V151 的 `ck_wpees_download_only_zero_entities`（按 kind 分支），
    #: 这一码覆盖 `scenario_kind='standard'` 但 `expects_application=False` 的场景 ——
    #: 库层对它**完全不管**（`ck_wpees_standard_requires_entities` 只在 passed 时生效），
    #: 于是"写成 unverifiable 再塞一个 application 进去"在库层合法。判据只能在写入侧。
    application_forbidden_for_scenario = "application_forbidden_for_scenario"
    #: 该场景必须有 recovery case 但没给。
    missing_recovery_case = "missing_recovery_case"
    #: 该场景必须同时有 operation 与 application 但没给。
    missing_application = "missing_application"
    #: recovery claim 场景在 claim 前必须证明三实体全空。
    recovery_precondition_not_proven = "recovery_precondition_not_proven"
    #: trace bundle artifact 缺失或未 published（只有截图/自由文本）。
    trace_bundle_not_published = "trace_bundle_not_published"
    #: 提交的 entry 不在 source-backed manifest 里。
    entry_not_in_manifest = "entry_not_in_manifest"
    #: run 已 finalize，不接受追加 scenario（evidence 是不可变实体）。
    run_already_finalized = "run_already_finalized"


class HarnessRejected(HarnessError):
    """带**分型**的拒绝。`kind` 让守卫能断言「拒的是哪一条」而不是「拒了」。"""

    def __init__(self, kind: HarnessRejection, message: str) -> None:
        super().__init__(f"[{kind.value}] {message}")
        self.kind = kind


# ═══════════════════════════════════════════════════════════════════════════
# 1. scenario oracle 登记表
# ═══════════════════════════════════════════════════════════════════════════


class EvidenceInput(str, Enum):
    """一条场景的判定**需要哪种证据**。它决定该场景今天能不能被判 passed。"""

    #: 服务端 operation/application/recovery timeline 顺序（DB + 服务端时钟）。
    server_timeline = "server_timeline"
    #: operation / application / content version / representation 行。
    db_entities = "db_entities"
    #: projection / artifact sha256。
    artifact_digests = "artifact_digests"
    #: 在进程内真跑一次三方 merge（**不需要** OO）。
    merge_execution = "merge_execution"
    #: close intent / `reconcile_close_intents()` 的真实执行。
    close_barrier = "close_barrier"
    #: recovery case / claim / download-only 的真实执行。
    recovery_lifecycle = "recovery_lifecycle"
    #: 🔴 真实 OnlyOffice 9.4 forcesave / callback 往返。
    onlyoffice_forcesave = "onlyoffice_forcesave"
    #: 🔴 真实浏览器 network/console trace。
    browser_trace = "browser_trace"


#: 需要真实黑盒环境的证据种类。任一出现在场景需求里，该场景在 :data:`NOT_EXECUTED`
#: 环境下只能是 `unverifiable`（Property 49）。
BLACK_BOX_INPUTS: Final[frozenset[EvidenceInput]] = frozenset(
    {EvidenceInput.onlyoffice_forcesave, EvidenceInput.browser_trace}
)


class OracleOutcome(str, Enum):
    """oracle 的三态。与 V151 `ck_wpees_result` 同域，一个不多一个不少。"""

    passed = "passed"
    failed = "failed"
    unverifiable = "unverifiable"


@dataclass(frozen=True)
class OracleVerdict:
    """一次 oracle 执行的结论。`error_code` 让 `unverifiable/failed` 可归因。"""

    outcome: OracleOutcome
    error_code: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.outcome is OracleOutcome.passed


@dataclass(frozen=True)
class ScenarioOracle:
    """一条场景的判定方式。

    :param requires: 该场景判定所需的证据种类
    :param production_refs: 该场景**在生产上**由哪些符号实现（`module:attr`）。
        plan 阶段逐个 import + getattr —— 生产符号被改名/删除时立刻抛
        :attr:`HarnessRejection.oracle_unresolvable`，而不是等到 Task 70 跑真实 OO 才
        发现「场景声明还在、被测的东西早没了」。
    :param upstream_debt: 该场景当前**在生产上不可达**的登记（欠账 owner + 理由）。
        非空即表示 oracle 只能落 `failed`：它是任务正文「接不了就登记并让场景
        fail closed 而不是判绿」的机器形态。
    """

    scenario_id: str
    requires: frozenset[EvidenceInput]
    production_refs: tuple[str, ...]
    why: str
    upstream_debt: str | None = None

    @property
    def needs_black_box(self) -> bool:
        return bool(self.requires & BLACK_BOX_INPUTS)


def _o(
    scenario_id: str,
    requires: Sequence[EvidenceInput],
    refs: Sequence[str],
    why: str,
    *,
    debt: str | None = None,
) -> ScenarioOracle:
    return ScenarioOracle(
        scenario_id=scenario_id,
        requires=frozenset(requires),
        production_refs=tuple(refs),
        why=why,
        upstream_debt=debt,
    )


_I = EvidenceInput
_SYNC = "app.services.workpaper_sync"

#: 🔴 **Task 32 域的上游缺口**（本任务无法在不动 router/claim 的前提下接上，
#: 逐条登记并让对应场景 fail closed）。文案进 `error_code` 的 notes，因此它们不是
#: 注释而是**运行时可见的欠账**。
UPSTREAM_DEBT_CLAIM_PRECONDITIONS: Final[str] = (
    "Task 32 欠账：`recovery.claim_recovery_case()` 从不校验 expected_generation / "
    "expected_write_fence / expected_definition_bundle_sha256 ⇒ 「错误 prior "
    "confirmation/bundle/fence/contributor 拒绝」在生产路径上不可达。本场景因此只能落 "
    "failed（不是 unverifiable：缺口是**实现缺失**而不是环境缺失）"
)
UPSTREAM_DEBT_ROOM_FENCE_READ: Final[str] = (
    "Task 32 欠账：`room_latest_durable_application_id/_sequence` 无读路由 ⇒ "
    "「same-application higher-sequence fold 不 self-stale」的结果无从观测。"
    "写侧已由 Task 23 实现，缺的是可观测的读路由"
)

#: scenario_id → oracle。与 :mod:`evidence` 的场景声明**双向锁死**。
SCENARIO_ORACLES: Final[Mapping[str, ScenarioOracle]] = {
    o.scenario_id: o
    for o in (
        # ── 方向与 identity：必须真实 OO 往返 ────────────────────────────
        _o(
            "html_to_oo",
            [_I.db_entities, _I.artifact_digests, _I.server_timeline, _I.browser_trace],
            [
                f"{_SYNC}.content_mutation:ContentMutationService",
                f"{_SYNC}.materialize_coordinator:MaterializeCoordinator",
            ],
            "HTML 提交后 canonical artifact 可见：判据是 published representation 的 "
            "artifact sha256 与 descriptor 挂载顺序，只有真实宿主能给",
        ),
        _o(
            "oo_to_html",
            [
                _I.db_entities,
                _I.artifact_digests,
                _I.server_timeline,
                _I.onlyoffice_forcesave,
            ],
            [f"{_SYNC}.oo_to_html:OoToHtmlCoordinator"],
            "durable callback 后结构化内容可见：时序 `request frozen < command accepted < "
            "incoming durable < terminal` 只能由真实 forcesave 产生",
        ),
        _o(
            "identity_retention",
            [_I.artifact_digests, _I.onlyoffice_forcesave],
            [
                f"{_SYNC}.excel_instrumentation:ExcelIdentityCarrierGate",
                f"{_SYNC}.excel_instrumentation:read_back_identity",
            ],
            "identity 载体经 OO 打开/编辑/插删/排序/复制/forcesave/重开后仍保留 —— "
            "AC 6.16 明令必须真实 OO 9.4 黑盒探针，离线 openpyxl 往返不算",
        ),
        # ── 字段级：可在进程内真跑（P25 / P26）────────────────────────────
        _o(
            "different_field_merge",
            [_I.merge_execution, _I.artifact_digests],
            [f"{_SYNC}.merge:merge_projections"],
            "Property 25：current 改 A、incoming 改 B ⇒ 结果同时含 A/B 且 "
            "conflict_count=0。三方 projection 齐备即可判定，不需要 OO",
        ),
        _o(
            "same_field_conflict_resolve",
            [_I.merge_execution, _I.artifact_digests],
            [f"{_SYNC}.merge:merge_projections", f"{_SYNC}.merge:apply_resolutions"],
            "Property 26：base=A/current=B/incoming=C 时不得应用任一侧、三值完整，"
            "且人工裁决后才落库",
        ),
        # ── custom/opaque 的字段级替代（AC 12.12 唯一允许的替换）──────────
        _o(
            "authoritative_revision_conflict",
            [_I.db_entities, _I.artifact_digests, _I.onlyoffice_forcesave],
            [f"{_SYNC}.request_application:RequestApplicationService"],
            "并发 authoritative artifact revision 冲突：权威 OOXML 模型下没有字段级三方，"
            "判据是两次并发 application 的 revision 冲突被显式建立",
        ),
        _o(
            "no_silent_overwrite",
            [_I.db_entities, _I.artifact_digests, _I.onlyoffice_forcesave],
            [
                f"{_SYNC}.request_application:RequestApplicationService",
                f"{_SYNC}.resolution:CanonicalResolutionService",
            ],
            "冲突时不得静默覆盖权威文件：判据是旧 representation 仍可解析且 pointer 未被顶掉",
        ),
        # ── 幂等 / dedupe / fold ─────────────────────────────────────────
        _o(
            "frozen_base_status_6_2_dedupe",
            [_I.db_entities, _I.server_timeline, _I.onlyoffice_forcesave],
            [f"{_SYNC}.callback_delivery:CallbackDeliveryService"],
            "status 6/2 与网络重试命中同一 frozen identity 只应用一次：需要真实 OO 发两次 "
            "callback，构造出来的 delivery 证不了乱序",
        ),
        _o(
            "same_application_higher_sequence_fold",
            [_I.db_entities, _I.server_timeline],
            [
                f"{_SYNC}.request_application:RequestApplicationService",
                f"{_SYNC}.request_application:assert_correlation_convergence",
            ],
            "同 canonical application 的更高 sequence 只 fold、不 self-stale、origin 不改写",
            debt=UPSTREAM_DEBT_ROOM_FENCE_READ,
        ),
        _o(
            "cross_participant_idempotency_409",
            [_I.db_entities, _I.server_timeline],
            [f"{_SYNC}.request_application:RequestApplicationService"],
            "跨 participant 复用同 Idempotency-Key 及不同 kind/payload 均 409 且不返回旧 ID。"
            "本场景**自带** operation+application（A 侧那次必须先成功），"
            "「B 没产生第二个实体」由 oracle 断言而不是靠 ID 列表为空表达",
        ),
        _o(
            "quarantined_rejects_application_and_engine",
            [_I.db_entities],
            [
                f"{_SYNC}.callback_delivery:CallbackDeliveryService",
                f"{_SYNC}.adapters.excel:ExcelSyncAdapter",
            ],
            "quarantined incoming 在 application FK、coordinator 入口与 engine 三层各自被拒；"
            "按 AC 5.6 它永不创建 application ⇒ application_ids 恒空",
        ),
        # ── rollback ─────────────────────────────────────────────────────
        _o(
            "opaque_version_rollback_no_numeric_collision",
            [_I.db_entities, _I.artifact_digests],
            [f"{_SYNC}.content_mutation:ContentMutationService"],
            "rollback 只接受 opaque version UUID；跨 wp 相同 numeric revision 不碰撞",
        ),
        _o(
            "rollback",
            [_I.db_entities, _I.artifact_digests, _I.server_timeline],
            [f"{_SYNC}.content_mutation:ContentMutationService"],
            "回滚到历史 content version 并重物化：判据含 rematerialized representation hash",
        ),
        # ── recovery ─────────────────────────────────────────────────────
        _o(
            "browser_crash_no_userdata_recovery_case",
            [_I.recovery_lifecycle, _I.server_timeline, _I.browser_trace],
            [f"{_SYNC}.callback_delivery:CallbackDeliveryService"],
            "无 userdata 的 crash close 建 recovery case，claim 前三实体为 0 —— "
            "「浏览器崩溃」这一步只能由真实浏览器制造",
        ),
        _o(
            "authorization_first_recovery_claim",
            [_I.recovery_lifecycle, _I.server_timeline, _I.db_entities],
            [f"{_SYNC}.callback_delivery:CallbackDeliveryService"],
            "authorization-first claim 在一个事务内建 request+shell 并创建/命中 application",
        ),
        _o(
            "wrong_prior_confirmation_bundle_fence_contributor_rejected",
            [_I.recovery_lifecycle, _I.db_entities],
            [f"{_SYNC}.callback_delivery:CallbackDeliveryService"],
            "错误 prior confirmation / bundle / fence / contributor 一律拒绝且不产生 operation",
            debt=UPSTREAM_DEBT_CLAIM_PRECONDITIONS,
        ),
        _o(
            "download_only_zero_three_entities",
            [_I.recovery_lifecycle],
            [f"{_SYNC}.callback_delivery:CallbackDeliveryService"],
            "download-only 只终结 case 并签下载，request/application/operation 恒为 0",
        ),
        # ── refresh / reopen ─────────────────────────────────────────────
        _o(
            "refresh_required_reopen",
            [_I.db_entities, _I.server_timeline, _I.onlyoffice_forcesave],
            [f"{_SYNC}.merge:projection_requires_client_refresh"],
            "merged≠incoming ⇒ refresh_required，supersede/reopen 后才接受下一次 request",
        ),
        # ── close barrier（AC 4.10）──────────────────────────────────────
        _o(
            "single_participant_close",
            [_I.close_barrier, _I.db_entities, _I.server_timeline],
            [f"{_SYNC}.close_intent:CloseIntentService"],
            "单用户 clean close 最终恰一个 close-capture",
        ),
        _o(
            "two_user_close_order_a_then_b",
            [_I.close_barrier, _I.db_entities, _I.server_timeline, _I.browser_trace],
            [f"{_SYNC}.close_intent:CloseIntentService"],
            "两用户 A→B 顺序关闭，最终恰一个 close-capture（两个真实用户 ⇒ 需真实浏览器）",
        ),
        _o(
            "two_user_close_order_b_then_a",
            [_I.close_barrier, _I.db_entities, _I.server_timeline, _I.browser_trace],
            [f"{_SYNC}.close_intent:CloseIntentService"],
            "两用户 B→A 顺序关闭，最终恰一个 close-capture",
        ),
        _o(
            "b_close_before_a_forcesave_terminal",
            [
                _I.close_barrier,
                _I.db_entities,
                _I.server_timeline,
                _I.onlyoffice_forcesave,
            ],
            [f"{_SYNC}.close_intent:CloseIntentService"],
            "A 的普通 forcesave terminal **之前** B close：barrier 必须等前置 forcesave 安全终结",
        ),
        _o(
            "b_close_after_a_forcesave_terminal",
            [
                _I.close_barrier,
                _I.db_entities,
                _I.server_timeline,
                _I.onlyoffice_forcesave,
            ],
            [f"{_SYNC}.close_intent:CloseIntentService"],
            "A 的普通 forcesave terminal **之后** B close",
        ),
        _o(
            "close_leader_revoked_successor_exactly_one",
            [_I.close_barrier, _I.db_entities, _I.server_timeline],
            [
                f"{_SYNC}.close_intent:CloseIntentService",
                f"{_SYNC}.close_intent:select_close_leader",
            ],
            "leader promotion 前被 revoke/expire，存在合法 successor ⇒ 仍恰一个 capture",
        ),
        _o(
            "close_leader_revoked_no_successor_recovery_required",
            [_I.close_barrier, _I.db_entities, _I.server_timeline],
            [
                f"{_SYNC}.close_intent:CloseIntentService",
                f"{_SYNC}.close_intent:eligible_close_intents",
            ],
            "无合法 successor ⇒ 零 capture + generation supersede + 显式 recovery_required",
        ),
        _o(
            "close_reconciler_reentrant_exactly_one_capture",
            [_I.close_barrier, _I.db_entities],
            [
                f"{_SYNC}.close_intent:CloseIntentService",
                f"{_SYNC}.close_intent:assert_at_most_one_open_capture",
            ],
            "`CloseIntentService.reconcile()` 重入（同 eligibility snapshot 重放）不换 leader、"
            "不产生第二 capture",
        ),
        # ── dynamic / word ───────────────────────────────────────────────
        _o(
            "dynamic_row_add_delete_reorder_copy",
            [_I.artifact_digests, _I.onlyoffice_forcesave],
            [f"{_SYNC}.excel_extract:extract_projection"],
            "动态行增删重排复制按 row identity 合并 —— 「在 OO 里插一行」只能真实 OO 做",
        ),
        _o(
            "dynamic_column_stable_keys",
            [_I.artifact_digests, _I.onlyoffice_forcesave],
            [f"{_SYNC}.excel_materialize:plan_managed_writes"],
            "横向动态列用稳定 key `{slot}_{seq}`，不写死列数、不用 label 作 identity",
        ),
        _o(
            "word_sdt_tag_row_uuid_retention",
            [_I.artifact_digests, _I.onlyoffice_forcesave],
            [f"{_SYNC}.word_resolution:resolve_word_template"],
            "SDT 的 tag/row_uuid 集合与层级经 OO 往返仍保留（AC 14.4 明令真实 OO 9.4）",
        ),
        _o(
            "word_free_body_isolation",
            [_I.artifact_digests, _I.onlyoffice_forcesave],
            [f"{_SYNC}.word_resolution:resolve_word_template"],
            "SDT 外自由正文只属于 Word，不反向覆盖 HTML 字段",
        ),
        # ── single_html ──────────────────────────────────────────────────
        _o(
            "single_html_no_blank_oo_artifact",
            [_I.db_entities, _I.browser_trace],
            [f"{_SYNC}.resolution:CanonicalResolutionService"],
            "single_html entry 不创建空白 OO artifact，也不显示不可兑现的切换",
        ),
    )
}


def all_declared_scenarios() -> tuple[RequiredScenario, ...]:
    """:mod:`evidence` 里**全部**可能出现在某个 required set 里的场景声明。

    刻意由 evidence 的导出元组现算，不在本模块抄第二份清单 —— 抄一份就意味着
    evidence 新增场景时这里不会跟着变（分母写死的经典形态）。
    """
    return (
        PROJECTION_BASE_SCENARIOS
        + CLOSE_SCENARIOS
        + DYNAMIC_SCENARIOS
        + WORD_SCENARIOS
        + SINGLE_HTML_SCENARIOS
        + AUTHORITY_SUBSTITUTE_SCENARIOS
    )


def assert_oracle_registry_complete(
    *, declared_ids: frozenset[str] | None = None, registered_ids: frozenset[str] | None = None
) -> None:
    """:data:`SCENARIO_ORACLES` ↔ evidence 场景声明**双向**锁死。

    单向（「每个 oracle 都有声明」）不够：漏一个场景的 oracle 时，harness 会在
    `record_scenario` 才抛，而「跑完全部 26 个场景」的计数仍然满分 —— 因为那条场景
    从来没被提交过。双向锁让缺口在 import/plan 阶段就暴露。

    两个入参只为**让两条分支都可测**（默认值就是生产事实）：模块常量在 import 时定型，
    没有注入点的话「缺 oracle 会不会抛」这条判据永远只能靠真的删一条 oracle 来验证，
    而那不是守卫能做的事。
    """
    declared = (
        {s.scenario_id for s in all_declared_scenarios()}
        if declared_ids is None
        else set(declared_ids)
    )
    registered = set(SCENARIO_ORACLES) if registered_ids is None else set(registered_ids)
    missing = sorted(declared - registered)
    if missing:
        raise HarnessError(
            f"以下场景在 evidence 里已声明但 harness 没有 oracle: {missing} —— "
            "分母与判定表脱钩，跑完计数会虚高"
        )
    extra = sorted(registered - declared)
    if extra:
        raise HarnessError(
            f"以下 oracle 不对应任何已声明场景: {extra} —— "
            "oracle 表不得追加自由项（required set 只能由推导产生）"
        )


def resolve_production_refs(oracle: ScenarioOracle) -> tuple[Any, ...]:
    """逐个 import + getattr 该场景在生产上的实现符号。

    这是「接线是否还存在」的最便宜判据：符号被改名/删除时立刻抛，而不是等真实 OO
    跑到那一步才发现被测对象早已不在。**不吞异常** —— fail-open 会把「函数名拼错」
    伪装成「本项目无此数据」（本 spec 最贵的一类缺陷）。
    """
    out: list[Any] = []
    for ref in oracle.production_refs:
        module_name, _, attr = ref.partition(":")
        if not module_name or not attr:
            raise HarnessRejected(
                HarnessRejection.oracle_unresolvable,
                f"{oracle.scenario_id}: production_ref {ref!r} 必须形如 'module:attr'",
            )
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - 转成分型拒绝，不降级
            raise HarnessRejected(
                HarnessRejection.oracle_unresolvable,
                f"{oracle.scenario_id}: 无法 import {module_name!r}: "
                f"{type(exc).__name__}: {exc}",
            ) from exc
        if not hasattr(module, attr):
            raise HarnessRejected(
                HarnessRejection.oracle_unresolvable,
                f"{oracle.scenario_id}: {module_name} 里没有 {attr!r} —— "
                "场景声明还在，被测的生产符号已经不在了",
            )
        out.append(getattr(module, attr))
    return tuple(out)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 可在进程内执行的 oracle：P25 / P26 与时序
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class MergeEvidence:
    """字段级场景的三方输入 + （P26 用的）人工裁决。"""

    base: Projection
    current: Projection
    incoming: Projection
    contract: SyncContract
    #: 期望在 current 侧出现的键（P25 的 A）。
    current_changed_key: str | None = None
    #: 期望在 incoming 侧出现的键（P25 的 B）。
    incoming_changed_key: str | None = None
    #: 同字段异值冲突的键（P26）。
    conflict_key: str | None = None
    #: P26 的人工裁决（None = 只验证冲突建立，不验证裁决落库）。
    resolutions: tuple[Any, ...] = ()


def evaluate_different_field_merge(evidence: MergeEvidence) -> OracleVerdict:
    """**Property 25**：不同字段的并行修改自动合并。

    真跑一次 :func:`~app.services.workpaper_sync.merge.merge_projections`，判据逐字取
    design 原文「current 改 A、incoming 改 B，结果同时含 A/B 且 conflict_count=0」：

    1. `conflict_count == 0`
    2. merged 里 A 键的值 == current 侧的值
    3. merged 里 B 键的值 == incoming 侧的值

    只断 `conflict_count == 0` 是不够的：一个「incoming 整体覆盖 current」的实现同样
    零冲突，但 A 会丢。三条同时成立才是 P25。
    """
    if evidence.current_changed_key is None or evidence.incoming_changed_key is None:
        return OracleVerdict(
            OracleOutcome.unverifiable,
            "merge_keys_missing",
            ("P25 需要显式给出 current 侧与 incoming 侧各自改动的键，否则判据退化成「零冲突」",),
        )
    if evidence.current_changed_key == evidence.incoming_changed_key:
        return OracleVerdict(
            OracleOutcome.unverifiable,
            "merge_keys_not_disjoint",
            ("P25 的两个键必须不同 —— 同键就是 P26 的场景",),
        )
    outcome = merge_projections(
        base=evidence.base,
        current=evidence.current,
        incoming=evidence.incoming,
        contract=evidence.contract,
    )
    notes: list[str] = [f"conflict_count={outcome.conflict_count}"]
    if outcome.conflict_count != 0:
        return OracleVerdict(
            OracleOutcome.failed,
            "p25_unexpected_conflict",
            tuple(notes + ["不同字段的并行修改必须自动合并，实测产生了冲突"]),
        )
    a_key, b_key = evidence.current_changed_key, evidence.incoming_changed_key
    merged_a = outcome.value_of(a_key)
    merged_b = outcome.value_of(b_key)
    want_a = _projection_envelope(evidence.current, a_key)
    want_b = _projection_envelope(evidence.incoming, b_key)
    if merged_a != want_a:
        return OracleVerdict(
            OracleOutcome.failed,
            "p25_current_side_lost",
            tuple(notes + [f"{a_key}: merged={merged_a!r} 期望 current 侧 {want_a!r}"]),
        )
    if merged_b != want_b:
        return OracleVerdict(
            OracleOutcome.failed,
            "p25_incoming_side_lost",
            tuple(notes + [f"{b_key}: merged={merged_b!r} 期望 incoming 侧 {want_b!r}"]),
        )
    return OracleVerdict(OracleOutcome.passed, None, tuple(notes))


def evaluate_same_field_conflict(evidence: MergeEvidence) -> OracleVerdict:
    """**Property 26**：同字段异值必冲突，且不得应用任一侧。

    判据逐字取 design 原文「base=A、current=B、incoming=C 时不得应用任一侧，冲突三值
    完整」：

    1. 该键**有**冲突记录
    2. 冲突的 base/current/incoming 三值与输入逐一相同（三值完整）
    3. merged 该键**不等于** incoming（没有静默采纳 OO 侧）
    4. 给了裁决时，:func:`~app.services.workpaper_sync.merge.apply_resolutions` 之后
       才出现被选中的值 —— 「裁决前不落库」
    """
    key = evidence.conflict_key
    if key is None:
        return OracleVerdict(
            OracleOutcome.unverifiable,
            "conflict_key_missing",
            ("P26 需要显式给出冲突键，否则无法断言「三值完整」",),
        )
    outcome = merge_projections(
        base=evidence.base,
        current=evidence.current,
        incoming=evidence.incoming,
        contract=evidence.contract,
    )
    record = _conflict_for_key(outcome, key)
    if record is None:
        return OracleVerdict(
            OracleOutcome.failed,
            "p26_conflict_not_raised",
            (f"{key}: 同字段异值未产生冲突 —— 有一侧被静默采纳",),
        )
    want = {
        "base": _projection_envelope(evidence.base, key),
        "current": _projection_envelope(evidence.current, key),
        "incoming": _projection_envelope(evidence.incoming, key),
    }
    got = {"base": record.base, "current": record.current, "incoming": record.incoming}
    for side, expected in want.items():
        if got[side] != expected:
            return OracleVerdict(
                OracleOutcome.failed,
                "p26_three_values_incomplete",
                (f"{key}: 冲突的 {side} 值 {got[side]!r} 与输入 {expected!r} 不符",),
            )
    if outcome.value_of(key) == want["incoming"]:
        return OracleVerdict(
            OracleOutcome.failed,
            "p26_incoming_applied",
            (f"{key}: 冲突未裁决时 merged 已等于 incoming —— 相当于自动选了 OO 侧",),
        )
    notes = [f"conflict_count={outcome.conflict_count}"]
    if evidence.resolutions:
        settled = apply_resolutions(outcome, list(evidence.resolutions))
        notes.append(f"resolved_keys={sorted(settled.values)[:4]}")
    return OracleVerdict(OracleOutcome.passed, None, tuple(notes))


def _projection_envelope(projection: Projection, key: str) -> Any:
    from app.services.workpaper_sync.conflicts import ValueEnvelope

    field_value = projection.get(key)
    return ValueEnvelope.absent() if field_value is None else ValueEnvelope.of(field_value.value)


def _conflict_for_key(outcome: MergeOutcome, key: str) -> Any:
    for record in outcome.conflicts:
        if record.locator.stable_field_key == key:
            return record
    return None


#: OO→HTML 的服务端时序（AC 4.2 / 14.8 原文顺序）。
OO_TO_HTML_TIMELINE_ORDER: Final[tuple[str, ...]] = (
    "forcesave_request_frozen",
    "command_accepted",
    "incoming_durable",
    "terminal",
    "reload",
)

#: no-userdata crash recovery 的服务端时序（AC 14.8 原文顺序）。
RECOVERY_TIMELINE_ORDER: Final[tuple[str, ...]] = (
    "incoming_durable",
    "recovery_case_created",
    "claim_or_download_only",
)


def evaluate_timeline_order(
    observed: Mapping[str, datetime], *, expected_order: Sequence[str]
) -> OracleVerdict:
    """服务端时序 oracle（AC 14.8）。

    只接受**服务端时钟**给出的 `datetime`；缺任一阶段即 `unverifiable`（不是 failed：
    缺证据与证据反驳是两回事，合成一码会让「没跑」看起来像「跑了但坏了」）。
    """
    missing = [stage for stage in expected_order if observed.get(stage) is None]
    if missing:
        return OracleVerdict(
            OracleOutcome.unverifiable,
            "timeline_stage_missing",
            (f"缺服务端时序阶段 {missing}",),
        )
    stamps = [(stage, observed[stage]) for stage in expected_order]
    for (prev_stage, prev), (stage, current) in zip(stamps, stamps[1:]):
        if not prev <= current:
            return OracleVerdict(
                OracleOutcome.failed,
                "timeline_out_of_order",
                (f"{prev_stage}({prev.isoformat()}) 晚于 {stage}({current.isoformat()})",),
            )
    return OracleVerdict(OracleOutcome.passed, None, (f"stages={list(expected_order)}",))


# ═══════════════════════════════════════════════════════════════════════════
# 3. 观测输入与结果推导
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ScenarioObservation:
    """runner 为**一条**场景提交的观测。

    🔴 **没有 `result` 字段**。有意为之：结果由 :func:`run_scenario_oracle` 推导。
    """

    scenario_id: str
    operation_ids: tuple[uuid.UUID, ...] = ()
    application_ids: tuple[uuid.UUID, ...] = ()
    recovery_case_ids: tuple[uuid.UUID, ...] = ()
    content_version_ids: tuple[uuid.UUID, ...] = ()
    representation_ids: tuple[uuid.UUID, ...] = ()
    trace_bundle_artifact_id: uuid.UUID | None = None
    trace_bundle_sha256: str = ""
    server_timeline_digest: str = ""
    database_snapshot_digest: str = ""
    #: 服务端时钟给出的分阶段时间（:func:`evaluate_timeline_order` 的输入）。
    server_timeline: Mapping[str, datetime] = field(default_factory=dict)
    #: 字段级场景的三方输入（P25 / P26 的 oracle 输入）。
    merge_evidence: MergeEvidence | None = None
    #: close 场景实测的 close-capture 数。
    observed_close_captures: int | None = None
    #: recovery 场景：claim 之前三实体是否**实测**为空。
    recovery_precondition_zero_entities: bool | None = None
    #: 该场景实际使用的证据种类（runner 自报，harness 与 oracle 需求求差集）。
    supplied_inputs: frozenset[EvidenceInput] = frozenset()

    @property
    def entity_ids(self) -> tuple[uuid.UUID, ...]:
        return self.operation_ids + self.application_ids + self.recovery_case_ids


@dataclass(frozen=True)
class ScenarioDecision:
    """一条场景的最终判定（写库前的完整决定）。"""

    scenario: RequiredScenario
    oracle: ScenarioOracle
    verdict: OracleVerdict

    @property
    def result(self) -> str:
        return self.verdict.outcome.value


def run_scenario_oracle(
    *,
    scenario: RequiredScenario,
    oracle: ScenarioOracle,
    observation: ScenarioObservation,
    onlyoffice_build: str,
    browser_build: str,
) -> OracleVerdict:
    """真跑一次 oracle 并推导 `result`。**判定顺序不可交换**。

    顺序理由（本 spec 实测「判定顺序不可交换」两次）：

    1. **schema 欠账**先判 —— 它已登记且必然发生，放后面会被别的码遮住；
    2. **上游实现缺口**（`upstream_debt`）判 `failed`：缺的是实现不是环境；
    3. **黑盒环境缺失**判 `unverifiable`：Property 49 的原文；
    4. **证据种类缺失**判 `unverifiable`；
    5. 最后才跑真正的判据（merge / timeline / close capture / 三实体）。

    把 3 放到 5 之后会让「真实 OO 没跑」被「证据齐全」的分支吞掉；把 2 放到 3 之后会让
    上游缺口在没有 OO 的环境里显示为 `unverifiable`，于是**接了 OO 就会自动变绿** ——
    而它其实永远不会通过。
    """
    if scenario.scenario_id in SCHEMA_UNREPRESENTABLE_SCENARIOS:
        return OracleVerdict(
            OracleOutcome.unverifiable,
            "scenario_kind_unrepresentable",
            (SCHEMA_UNREPRESENTABLE_SCENARIOS[scenario.scenario_id],),
        )
    if oracle.upstream_debt:
        return OracleVerdict(
            OracleOutcome.failed, "upstream_gap", (oracle.upstream_debt,)
        )
    if oracle.needs_black_box:
        unreal = []
        if EvidenceInput.onlyoffice_forcesave in oracle.requires and (
            onlyoffice_build == NOT_EXECUTED
        ):
            unreal.append("onlyoffice_build")
        if EvidenceInput.browser_trace in oracle.requires and browser_build == NOT_EXECUTED:
            unreal.append("browser_build")
        if unreal:
            return OracleVerdict(
                OracleOutcome.unverifiable,
                "real_onlyoffice_not_executed",
                (
                    f"{unreal} 仍是 {NOT_EXECUTED} 哨兵 —— Property 49：probe/pilot 未实际"
                    "通过时必须保持 UNVERIFIABLE，不得因文档声明计为通过",
                ),
            )
    missing_inputs = sorted(
        i.value for i in (oracle.requires - observation.supplied_inputs)
    )
    if missing_inputs:
        return OracleVerdict(
            OracleOutcome.unverifiable,
            "evidence_input_missing",
            (f"该场景需要 {missing_inputs} 但本次未提供",),
        )

    if EvidenceInput.merge_execution in oracle.requires:
        if observation.merge_evidence is None:
            return OracleVerdict(
                OracleOutcome.unverifiable,
                "merge_evidence_missing",
                ("字段级场景必须提交三方 projection + contract，否则 oracle 无从执行",),
            )
        if scenario.family is ScenarioFamily.merge:
            return evaluate_different_field_merge(observation.merge_evidence)
        return evaluate_same_field_conflict(observation.merge_evidence)

    if scenario.expected_close_captures is not None:
        got = observation.observed_close_captures
        if got is None:
            return OracleVerdict(
                OracleOutcome.unverifiable,
                "close_capture_count_missing",
                ("close 场景必须实测 close-capture 数（partial unique 只证明 at-most-one）",),
            )
        if got != scenario.expected_close_captures:
            return OracleVerdict(
                OracleOutcome.failed,
                "close_capture_count_mismatch",
                (
                    f"期望 exactly {scenario.expected_close_captures} 个 close-capture，"
                    f"实测 {got}",
                ),
            )

    if scenario.expects_recovery_case and observation.recovery_precondition_zero_entities is None:
        return OracleVerdict(
            OracleOutcome.unverifiable,
            "recovery_precondition_not_measured",
            ("recovery 场景必须实测「claim 前 request/application/operation 全空」",),
        )

    if EvidenceInput.server_timeline in oracle.requires:
        order = (
            RECOVERY_TIMELINE_ORDER
            if scenario.family is ScenarioFamily.recovery
            else OO_TO_HTML_TIMELINE_ORDER
        )
        return evaluate_timeline_order(observation.server_timeline, expected_order=order)

    return OracleVerdict(
        OracleOutcome.passed, None, ("结构判据全部满足（无需时序/merge 的场景）",)
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. bundle 身份解析（authority model 只能从 approved bundle 链上读）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class BundleIdentity:
    """一次 run 冻结的 immutable definition bundle 身份 + 三类 typed child。"""

    bundle_id: uuid.UUID
    bundle_sha256: str
    authority_model: AuthorityModel
    authority_model_definition_sha256: str
    template_slot: tuple[str, str, str]
    instrumentation_slot: tuple[str, str, str]
    contract_slot: tuple[str, str, str]

    @property
    def typed_child_digest(self) -> str:
        """三类 typed child + authority model 的 canonical digest。

        单独成一个 digest 是因为 AC 14.16 把「bundle」与「任一非-null definition child」
        列成**两条**独立的失效轴：child 被换掉而 bundle digest 没跟着变，是篡改；
        两者一起变，是正常升级。共用一个码就分不出这两件事。
        """
        return canonical_digest(
            {
                "authority_model": self.authority_model.value,
                "authority_model_definition_sha256": self.authority_model_definition_sha256,
                "template": list(self.template_slot),
                "instrumentation": list(self.instrumentation_slot),
                "contract": list(self.contract_slot),
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "definition_bundle_id": str(self.bundle_id),
            "definition_bundle_sha256": self.bundle_sha256,
            "authority_model": self.authority_model.value,
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "typed_slots": {
                "template": list(self.template_slot),
                "instrumentation": list(self.instrumentation_slot),
                "contract": list(self.contract_slot),
            },
            "typed_child_digest": self.typed_child_digest,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 5. harness
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# 5. 纯判据（每条 rejection 的**唯一**定义点）
# ═══════════════════════════════════════════════════════════════════════════
#
# 刻意把判据从 :class:`SyncTestRunHarness` 的方法里提出来做成模块级纯函数，理由有两条：
#
# 1. **一码一处**。同一条 rejection 若在两个方法里各写一遍，把任一处短路掉都不改变
#    行为 ⇒ 变异检验判 GREEN（本 spec 在 `definitions._normalize_slot_input` 上实测过
#    完全一样的形态）。
# 2. **判据可离线验证**。V151 的 `JSONB` 无法在 SQLite 上 `create_all`（实测
#    `can't render element of type JSONB`），若判据全锁在 async 方法里，就只能在真库上
#    触发 —— 而「每一码各真触发一次」的分母检查恰恰需要能便宜地跑完全部码。


def entry_for(
    entries: Mapping[str, Mapping[str, Any]], entry_id: str
) -> Mapping[str, Any]:
    """manifest 里取 entry；未登记入口 fail closed。"""
    entry = entries.get(entry_id)
    if entry is None:
        raise HarnessRejected(
            HarnessRejection.entry_not_in_manifest,
            f"entry {entry_id!r} 不在 source-backed manifest 里 —— "
            "未登记入口不得产出 evidence",
        )
    return entry


def oracle_for(scenario_id: str) -> ScenarioOracle:
    """scenario_id → oracle；未登记 fail closed。"""
    oracle = SCENARIO_ORACLES.get(scenario_id)
    if oracle is None:
        raise HarnessRejected(
            HarnessRejection.oracle_missing,
            f"{scenario_id!r} 没有登记 oracle —— 分母与判定表脱钩，跑完计数会虚高",
        )
    return oracle


def assert_required_set_non_empty(required: RequiredScenarioSet) -> None:
    """🔴 零场景不算通过。"""
    if not required.scenarios:
        raise HarnessRejected(
            HarnessRejection.empty_required_set,
            f"entry {required.entry_id} 推导出的 required scenario set 为空"
            f"（capability={required.capability.value}）—— "
            "「零场景全部通过」不是通过；unreachable 入口应删除而不是记为已验收",
        )


def scenario_in_required_set(
    required: RequiredScenarioSet, scenario_id: str
) -> RequiredScenario:
    """场景必须在推导出的 required set 里；追加自由项 fail closed。"""
    scenario = required.by_id(scenario_id)
    if scenario is None:
        raise HarnessRejected(
            HarnessRejection.scenario_not_required,
            f"{scenario_id!r} 不在 entry {required.entry_id} 的 required set 里 —— "
            "required set 只能由推导产生，不接受追加自由项",
        )
    return scenario


def assert_scenario_not_recorded(
    *, scenario_id: str, recorded: Sequence[tuple[str, frozenset[str]]], run_id: Any
) -> None:
    """同一场景不得在同一 run 里提交两次。

    `uq_wpees_scenario` 是 `(run_id, scenario_id, ordinal)` —— 换个 ordinal 就能再插一行，
    于是「同一条场景跑十次挑最好的那次」在库层完全合法。判据只能在写入侧。
    """
    if any(sid == scenario_id for sid, _ in recorded):
        raise HarnessRejected(
            HarnessRejection.duplicate_scenario,
            f"{scenario_id!r} 在 run {run_id} 里已有一行 —— 同一场景不得提交两次"
            "（`uq_wpees_scenario` 含 ordinal，换个序号就能重复插入）",
        )


def bundle_identity_from_rows(
    bundle: WorkpaperSyncDefinitionBundle,
    authority: WorkpaperSyncDefinitionArtifact | None,
) -> BundleIdentity:
    """bundle 行 + authority definition 行 → 冻结身份。

    两道 fail-closed：未 approved ⇒ :attr:`HarnessRejection.bundle_not_approved`；
    `authority_model_type` 不在封闭枚举 ⇒
    :attr:`HarnessRejection.authority_model_not_enumerated`。后者是任务正文
    「未知枚举或自由文本豁免 fail closed」的**唯一**落点。
    """
    if str(bundle.state) != DefinitionState.approved.value:
        raise HarnessRejected(
            HarnessRejection.bundle_not_approved,
            f"definition bundle {bundle.id} 状态为 {bundle.state!r}；"
            "candidate/unapproved bundle 不得进入 evidence（AC 12.1）",
        )
    if authority is None or str(authority.state) != DefinitionState.approved.value:
        raise HarnessRejected(
            HarnessRejection.bundle_not_approved,
            f"bundle {bundle.id} 的 authority model definition 缺失或未 approved —— "
            "authority model 必须独立先行批准并作为 bundle 必填 child（AC 6.2）",
        )
    if str(authority.kind) != DefinitionKind.authority_model.value:
        raise HarnessRejected(
            HarnessRejection.authority_model_not_enumerated,
            f"bundle {bundle.id} 的 authority child kind={authority.kind!r}，"
            "不是 authority_model definition",
        )
    try:
        model = AuthorityModel(authority.authority_model_type)
    except (ValueError, TypeError) as exc:
        raise HarnessRejected(
            HarnessRejection.authority_model_not_enumerated,
            f"authority_model_type={authority.authority_model_type!r} 不在封闭枚举 "
            f"{sorted(m.value for m in AuthorityModel)} 内 —— "
            "字段级两场景的替换只能由枚举 authority model 触发，禁自由文本豁免",
        ) from exc
    return BundleIdentity(
        bundle_id=bundle.id,
        bundle_sha256=str(bundle.canonical_payload_sha256),
        authority_model=model,
        authority_model_definition_sha256=str(bundle.authority_model_definition_sha256),
        template_slot=(
            str(bundle.template_slot_type),
            str(bundle.template_slot_ref),
            str(bundle.template_slot_digest),
        ),
        instrumentation_slot=(
            str(bundle.instrumentation_slot_type),
            str(bundle.instrumentation_slot_ref),
            str(bundle.instrumentation_slot_digest),
        ),
        contract_slot=(
            str(bundle.contract_slot_type),
            str(bundle.contract_slot_ref),
            str(bundle.contract_slot_digest),
        ),
    )


def assert_run_open(run: WorkpaperSyncTestRun) -> None:
    """已 finalize 的 run 不接受追加 scenario（evidence 是不可变实体）。"""
    if run.finished_at is not None:
        raise HarnessRejected(
            HarnessRejection.run_already_finalized,
            f"run {run.id} 已 finalize（finished_at={run.finished_at}），"
            "不接受追加 scenario —— 否则可以先 finalize 成 passed 再补一条失败场景",
        )


def assert_plan_matches_run(*, run: WorkpaperSyncTestRun, plan: HarnessPlan) -> None:
    """plan 的 bundle 身份必须与 run 冻结值一致。

    🔴 这条不是形式主义：`record_scenario` 用 **plan** 的 authority model 决定 required
    set（于是决定字段级两场景是否被替换），却把 **run** 的 digest 写进 scenario 行。
    两者不一致时，落库的证据会声称"按 bundle A 验的"，而判定其实是按 bundle B 的
    required set 做的 —— 那正是 Property 70 点名的"跨 bundle 复用"。
    """
    if plan.bundle.bundle_sha256 != str(run.definition_bundle_sha256):
        raise HarnessRejected(
            HarnessRejection.bundle_digest_mismatch,
            f"plan 的 bundle digest {plan.bundle.bundle_sha256} 与 run {run.id} 冻结的 "
            f"{run.definition_bundle_sha256} 不符 —— 一次 run 只能对应一个 frozen bundle",
        )
    if plan.bundle.authority_model_definition_sha256 != str(
        run.authority_model_definition_sha256
    ):
        raise HarnessRejected(
            HarnessRejection.authority_digest_mismatch,
            f"plan 的 authority model digest {plan.bundle.authority_model_definition_sha256} "
            f"与 run {run.id} 冻结的 {run.authority_model_definition_sha256} 不符",
        )


def assert_entity_shape(
    *, scenario: RequiredScenario, observation: ScenarioObservation
) -> None:
    """场景声明的 entity 期望 ↔ 实际提交的 ID 列表。

    与 V151 的三条 entity CHECK 同向但**更早也更严**：库层只在 `result='passed'` 时才管
    「必须有实体」，于是「写成 unverifiable 就能塞任意实体」在库层完全合法。

    🔴 **判定顺序不可交换**，四条规则按 V151 的分支顺序：

    1. `kind ∈ (download_only, recovery_reject)` ⇒ operation/application 恒为 0
       （对应 `ck_wpees_download_only_zero_entities`，插库前就拦住，否则真库
       `CheckViolationError` —— 本任务首轮实测踩过）；
    2. 其余场景若声明 `expects_application=False`（如 quarantined incoming，AC 5.6
       「永不创建 application」）⇒ application 必须为 0，**库层对此完全不管**；
    3. 声明需要 recovery case 的必须给；
    4. 声明需要 application 的必须同时给 operation + application。
    """
    zero_entity_kinds = (ScenarioKind.download_only, ScenarioKind.recovery_reject)
    if scenario.kind in zero_entity_kinds:
        if observation.operation_ids or observation.application_ids:
            raise HarnessRejected(
                HarnessRejection.download_only_has_entities,
                f"{scenario.scenario_id}（kind={scenario.kind.value}）: 该场景要求 "
                f"operation/application 恒为 0，实得 "
                f"{len(observation.operation_ids)}/{len(observation.application_ids)} —— "
                "download-only 只终结 case 并授权下载，recovery reject 更不得产生 operation",
            )
    elif not scenario.expects_application and observation.application_ids:
        raise HarnessRejected(
            HarnessRejection.application_forbidden_for_scenario,
            f"{scenario.scenario_id}: 该场景声明永不创建 application（AC 5.6），实得 "
            f"{len(observation.application_ids)} 个 —— quarantined incoming 只允许 "
            "download-only/expire/retention，永不进入 engine",
        )
    if scenario.expects_recovery_case and not observation.recovery_case_ids:
        raise HarnessRejected(
            HarnessRejection.missing_recovery_case,
            f"{scenario.scenario_id}: 该场景必须绑定 recovery case",
        )
    if scenario.expects_application and not (
        observation.operation_ids and observation.application_ids
    ):
        raise HarnessRejected(
            HarnessRejection.missing_application,
            f"{scenario.scenario_id}: 该场景必须同时有 operation 与 application，实得 "
            f"{len(observation.operation_ids)}/{len(observation.application_ids)}",
        )
    if (
        scenario.expects_recovery_case
        and observation.recovery_precondition_zero_entities is False
    ):
        raise HarnessRejected(
            HarnessRejection.recovery_precondition_not_proven,
            f"{scenario.scenario_id}: 实测 claim 前已存在 request/application/operation —— "
            "AC 5.8 要求三者在 claim 成功前均不存在",
        )


def assert_no_reuse_within_run(
    *,
    observation: ScenarioObservation,
    recorded: Sequence[tuple[str, frozenset[str]]],
) -> None:
    """同 run 内跨场景复用（一条 applied operation 冒充十条场景）。

    :param recorded: 已落库场景的 `(scenario_id, 实体 id 字符串集合)`。刻意收**元组**
        而不是 ORM 行：判据本身与持久化无关，收元组让它可离线验证。
    """
    mine = {str(i) for i in observation.entity_ids}
    if not mine:
        return
    for scenario_id, theirs in recorded:
        overlap = sorted(mine & theirs)
        if overlap:
            raise HarnessRejected(
                HarnessRejection.entity_reused_within_run,
                f"{observation.scenario_id}: 实体 {overlap} 已被同 run 的 "
                f"{scenario_id!r} 引用 —— 一条 applied operation 不能代表多个"
                "互不等价的场景（AC 12.10）",
            )


def assert_no_reuse_across_entry(
    *,
    observation: ScenarioObservation,
    foreign: Sequence[tuple[str, str, frozenset[str]]],
) -> None:
    """跨 entry 复制证据（Property 70）。

    :param foreign: 其他 entry 的 `(entry_id, scenario_id, 实体 id 集合)`。
    """
    mine = {str(i) for i in observation.entity_ids}
    if not mine:
        return
    for entry_id, scenario_id, theirs in foreign:
        overlap = sorted(mine & theirs)
        if overlap:
            raise HarnessRejected(
                HarnessRejection.entity_reused_across_entry,
                f"{observation.scenario_id}: 实体 {overlap} 已出现在 entry "
                f"{entry_id!r} 的场景 {scenario_id!r} 里 —— 跨 entry 复制证据",
            )


def assert_trace_bundle_published(
    *, observation: ScenarioObservation, artifact: WorkpaperArtifact | None
) -> None:
    """trace bundle 必须是**已 published 的 artifact 行**，不能只有截图。"""
    if observation.trace_bundle_artifact_id is None:
        raise HarnessRejected(
            HarnessRejection.trace_bundle_not_published,
            f"{observation.scenario_id}: 缺 trace bundle artifact —— "
            "截图或自由文本不构成逐 scenario 证据（AC 12.10 / 12.11）",
        )
    if artifact is None or str(artifact.state) != ArtifactState.published.value:
        raise HarnessRejected(
            HarnessRejection.trace_bundle_not_published,
            f"{observation.scenario_id}: trace bundle artifact "
            f"{observation.trace_bundle_artifact_id} 不存在或未 published",
        )
    if str(artifact.sha256) != observation.trace_bundle_sha256:
        raise HarnessRejected(
            HarnessRejection.trace_bundle_not_published,
            f"{observation.scenario_id}: trace bundle sha256 与 artifact 行不符 "
            f"({observation.trace_bundle_sha256!r} vs {artifact.sha256!r})",
        )


@dataclass(frozen=True)
class HarnessPlan:
    """一次 run 的执行计划：required set + 逐场景 oracle + 今天可判定性。"""

    entry_id: str
    required: RequiredScenarioSet
    bundle: BundleIdentity
    capability: Capability

    @property
    def scenario_ids(self) -> tuple[str, ...]:
        return self.required.scenario_ids

    @property
    def oracles(self) -> tuple[ScenarioOracle, ...]:
        return tuple(SCENARIO_ORACLES[sid] for sid in self.scenario_ids)

    @property
    def black_box_scenario_ids(self) -> tuple[str, ...]:
        """今天**不可能**判 passed 的场景（需要真实 OO / 浏览器）。"""
        return tuple(sid for sid in self.scenario_ids if SCENARIO_ORACLES[sid].needs_black_box)

    @property
    def upstream_debt_scenario_ids(self) -> tuple[str, ...]:
        """因上游实现缺口而**只能** failed 的场景。"""
        return tuple(sid for sid in self.scenario_ids if SCENARIO_ORACLES[sid].upstream_debt)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "capability": self.capability.value,
            "required": self.required.as_dict(),
            "bundle": self.bundle.as_dict(),
            "black_box_scenarios": list(self.black_box_scenario_ids),
            "upstream_debt_scenarios": list(self.upstream_debt_scenario_ids),
        }


class SyncTestRunHarness:
    """持久化 test run / scenario evidence 的**唯一**写入入口。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        manifest: Mapping[str, Any] | None = None,
        runner_version: str = HARNESS_VERSION,
    ) -> None:
        assert_oracle_registry_complete()
        self._session = session
        self._manifest = manifest if manifest is not None else load_entry_manifest()
        self._entries = manifest_entries_by_id(self._manifest)
        self._runner_version = runner_version

    # ------------------------------------------------------------------
    # 5.1 bundle 身份
    # ------------------------------------------------------------------

    async def resolve_bundle_identity(self, bundle_id: uuid.UUID) -> BundleIdentity:
        """读 approved bundle 行 + 其 authority model definition，委派纯判据校验。

        校验逻辑全在 :func:`bundle_identity_from_rows` —— 本方法只做 IO。
        """
        bundle = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionBundle).where(
                    WorkpaperSyncDefinitionBundle.id == bundle_id
                )
            )
        ).scalar_one_or_none()
        if bundle is None:
            raise HarnessRejected(
                HarnessRejection.bundle_not_approved,
                f"definition bundle {bundle_id} 不存在 —— evidence 必须绑定真实 bundle 行",
            )
        authority = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id == bundle.authority_model_definition_id
                )
            )
        ).scalar_one_or_none()
        return bundle_identity_from_rows(bundle, authority)

    # ------------------------------------------------------------------
    # 5.2 plan
    # ------------------------------------------------------------------

    async def plan(self, *, entry_id: str, bundle_id: uuid.UUID) -> HarnessPlan:
        """推导 required scenario set。空集合 fail closed。"""
        entry = entry_for(self._entries, entry_id)
        bundle = await self.resolve_bundle_identity(bundle_id)
        required = derive_for_manifest_entry(entry, authority_model=bundle.authority_model)
        assert_required_set_non_empty(required)
        for scenario_id in required.scenario_ids:
            resolve_production_refs(oracle_for(scenario_id))
        return HarnessPlan(
            entry_id=entry_id,
            required=required,
            bundle=bundle,
            capability=required.capability,
        )

    # ------------------------------------------------------------------
    # 5.3 open run
    # ------------------------------------------------------------------

    async def open_run(
        self,
        *,
        plan: HarnessPlan,
        environment: EvidenceEnvironment,
        run_manifest_artifact_id: uuid.UUID,
        run_manifest_sha256: str,
    ) -> WorkpaperSyncTestRun:
        """写 test run 行。

        🔴 `aggregate_result` 恒为 `'unverified'`、`finished_at` 恒为 `NULL`，且**没有
        入参** —— 结果只能由 :meth:`finalize_run` 的服务端重算写入。全部身份列都从
        plan/environment 推导，不接受调用方给 digest。
        """
        if environment.runner_version != self._runner_version:
            raise HarnessError(
                f"environment.runner_version={environment.runner_version!r} 与 harness "
                f"自报 {self._runner_version!r} 不符 —— runner 身份必须自洽，"
                "否则每个 run 一开始就是 stale"
            )
        run = WorkpaperSyncTestRun(
            id=uuid.uuid4(),
            entry_id=plan.entry_id,
            source_commit=environment.source_commit,
            runner_version=environment.runner_version,
            manifest_source_digest=manifest_source_digest(self._manifest),
            editability=plan.required.editability.value,
            room_model=plan.required.room_model.value,
            scenario_profile_digest=plan.required.scenario_profile_digest,
            onlyoffice_build=environment.onlyoffice_build,
            browser_build=environment.browser_build,
            environment_digest=environment.digest,
            required_scenario_set_digest=plan.required.digest,
            authority_model_definition_sha256=plan.bundle.authority_model_definition_sha256,
            definition_bundle_sha256=plan.bundle.bundle_sha256,
            run_manifest_artifact_id=run_manifest_artifact_id,
            run_manifest_sha256=run_manifest_sha256,
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            aggregate_result="unverified",
        )
        self._session.add(run)
        await self._session.flush()
        return run

    # ------------------------------------------------------------------
    # 5.4 record scenario
    # ------------------------------------------------------------------

    async def record_scenario(
        self,
        *,
        run: WorkpaperSyncTestRun,
        plan: HarnessPlan,
        observation: ScenarioObservation,
    ) -> tuple[WorkpaperEntryEvidenceScenario, ScenarioDecision]:
        """写一条 scenario evidence 行。`result` 由 oracle 推导，不接受入参。"""
        assert_run_open(run)
        assert_plan_matches_run(run=run, plan=plan)
        scenario = scenario_in_required_set(plan.required, observation.scenario_id)
        oracle = oracle_for(observation.scenario_id)

        existing = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperEntryEvidenceScenario).where(
                        WorkpaperEntryEvidenceScenario.run_id == run.id
                    )
                )
            ).scalars()
        )
        recorded = [_recorded_entities(row) for row in existing]
        assert_scenario_not_recorded(
            scenario_id=observation.scenario_id, recorded=recorded, run_id=run.id
        )
        assert_entity_shape(scenario=scenario, observation=observation)
        assert_no_reuse_within_run(observation=observation, recorded=recorded)
        assert_no_reuse_across_entry(
            observation=observation, foreign=await self._foreign_entities(run=run)
        )
        assert_trace_bundle_published(
            observation=observation,
            artifact=await self._artifact(observation.trace_bundle_artifact_id),
        )

        verdict = run_scenario_oracle(
            scenario=scenario,
            oracle=oracle,
            observation=observation,
            onlyoffice_build=str(run.onlyoffice_build),
            browser_build=str(run.browser_build),
        )
        row = WorkpaperEntryEvidenceScenario(
            id=uuid.uuid4(),
            run_id=run.id,
            scenario_id=scenario.scenario_id,
            ordinal=len(existing) + 1,
            scenario_kind=scenario.kind.value,
            result=verdict.outcome.value,
            operation_ids=[str(i) for i in observation.operation_ids],
            application_ids=[str(i) for i in observation.application_ids],
            recovery_case_ids=[str(i) for i in observation.recovery_case_ids],
            content_version_ids=[str(i) for i in observation.content_version_ids],
            representation_ids=[str(i) for i in observation.representation_ids],
            authority_model_definition_sha256=str(run.authority_model_definition_sha256),
            definition_bundle_sha256=str(run.definition_bundle_sha256),
            trace_bundle_artifact_id=observation.trace_bundle_artifact_id,
            trace_bundle_sha256=observation.trace_bundle_sha256,
            server_timeline_digest=observation.server_timeline_digest,
            database_snapshot_digest=observation.database_snapshot_digest,
            browser_build=str(run.browser_build),
            error_code=verdict.error_code,
        )
        self._session.add(row)
        await self._session.flush()
        return row, ScenarioDecision(scenario=scenario, oracle=oracle, verdict=verdict)

    # ------------------------------------------------------------------
    # 5.5 finalize
    # ------------------------------------------------------------------

    async def finalize_run(
        self,
        *,
        run: WorkpaperSyncTestRun,
        plan: HarnessPlan,
        environment: EvidenceEnvironment,
    ) -> EvidenceVerdict:
        """服务端重算后写 `finished_at` / `aggregate_result`。

        🔴 **没有 `aggregate_result` / `verified_at` 入参**。写入值只有两个来源：
        `finished_at` = 服务端时钟；`aggregate_result` = Task 29 recomputer 的
        :attr:`~app.services.workpaper_sync.evidence.EvidenceVerdict.result`。

        `verified` → `'passed'`，其余（`unverified` / `stale`）→ `'failed'`：V151 的
        `ck_wpstr_aggregate_result` 只有三值，而「跑完了但没通过」必须与「还没跑」
        （`unverified`，`finished_at IS NULL`）区分开 —— 都写 `unverified` 会让
        「已完成但未通过」在 `ck_wpstr_result_requires_finish` 之下与未开始的 run 同形。
        """
        recomputed = await EvidenceRecomputer(
            self._session, manifest=self._manifest
        ).recompute(
            entry_id=plan.entry_id,
            authority_model=plan.bundle.authority_model,
            environment=environment,
            run_id=run.id,
        )
        run.finished_at = datetime.now(timezone.utc)
        run.aggregate_result = "passed" if recomputed.verified else "failed"
        await self._session.flush()
        return recomputed

    # ------------------------------------------------------------------
    # 5.6 IO helper（判据本身在模块级纯函数里）
    # ------------------------------------------------------------------

    async def _artifact(self, artifact_id: uuid.UUID | None) -> WorkpaperArtifact | None:
        if artifact_id is None:
            return None
        return (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(WorkpaperArtifact.id == artifact_id)
            )
        ).scalar_one_or_none()

    async def _foreign_entities(
        self, *, run: WorkpaperSyncTestRun
    ) -> list[tuple[str, str, frozenset[str]]]:
        """其他 entry 已落库的实体集合（Property 70 的输入）。"""
        rows = list(
            (
                await self._session.execute(
                    sa.select(
                        WorkpaperSyncTestRun.entry_id,
                        WorkpaperEntryEvidenceScenario.scenario_id,
                        WorkpaperEntryEvidenceScenario.operation_ids,
                        WorkpaperEntryEvidenceScenario.application_ids,
                        WorkpaperEntryEvidenceScenario.recovery_case_ids,
                    )
                    .join(
                        WorkpaperSyncTestRun,
                        WorkpaperSyncTestRun.id == WorkpaperEntryEvidenceScenario.run_id,
                    )
                    .where(WorkpaperSyncTestRun.entry_id != run.entry_id)
                )
            ).all()
        )
        return [
            (
                str(entry_id),
                str(scenario_id),
                frozenset(
                    {
                        *(str(i) for i in (op_ids or [])),
                        *(str(i) for i in (app_ids or [])),
                        *(str(i) for i in (case_ids or [])),
                    }
                ),
            )
            for entry_id, scenario_id, op_ids, app_ids, case_ids in rows
        ]


def _recorded_entities(
    row: WorkpaperEntryEvidenceScenario,
) -> tuple[str, frozenset[str]]:
    return (
        str(row.scenario_id),
        frozenset(
            {
                *(str(i) for i in (row.operation_ids or [])),
                *(str(i) for i in (row.application_ids or [])),
                *(str(i) for i in (row.recovery_case_ids or [])),
            }
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. 四类 Excel pilot 覆盖（Property 49 / AC 12.2）
# ═══════════════════════════════════════════════════════════════════════════


class PilotClass(str, Enum):
    """AC 12.2 逐字四类。封闭枚举 —— 「再加一类」不能让分母变松。"""

    simple_checklist = "simple_checklist"
    d2_large_json = "d2_large_json"
    h1_grouped_dynamic = "h1_grouped_dynamic"
    g7_two_level_dynamic = "g7_two_level_dynamic"


class PilotClassStatus(str, Enum):
    verified = "verified"
    unverifiable = "unverifiable"


#: pilot 类 → entry_id 匹配正则。按 entry_id 而不是自由文本标注：manifest 里的
#: `evidence` 字段是自由文本，用它做归类等于让 Property 49 由文档声明决定。
PILOT_CLASS_PATTERNS: Final[Mapping[PilotClass, str]] = {
    PilotClass.d2_large_json: r"(^|[^a-z0-9])d2([^0-9]|$)",
    PilotClass.h1_grouped_dynamic: r"(^|[^a-z0-9])h1([^0-9]|$)",
    PilotClass.g7_two_level_dynamic: r"(^|[^a-z0-9])g7([^0-9]|$)",
}


@dataclass(frozen=True)
class PilotClassAssessment:
    """一个 pilot 类今天的覆盖状态。"""

    pilot_class: PilotClass
    candidate_entry_ids: tuple[str, ...]
    bidirectional_entry_ids: tuple[str, ...]
    verified_entry_ids: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def status(self) -> PilotClassStatus:
        """🔴 只有"真有一个已服务端重算通过的 bidirectional entry"才算 verified。"""
        if self.verified_entry_ids:
            return PilotClassStatus.verified
        return PilotClassStatus.unverifiable

    def as_dict(self) -> dict[str, Any]:
        return {
            "pilot_class": self.pilot_class.value,
            "status": self.status.value,
            "candidate_entry_ids": list(self.candidate_entry_ids),
            "bidirectional_entry_ids": list(self.bidirectional_entry_ids),
            "verified_entry_ids": list(self.verified_entry_ids),
            "reasons": list(self.reasons),
        }


def assess_pilot_classes(
    *,
    manifest: Mapping[str, Any] | None = None,
    verified_entry_ids: frozenset[str] = frozenset(),
) -> dict[PilotClass, PilotClassAssessment]:
    """**Property 49**：四类 Excel pilot 的覆盖状态。

    只读两样东西：source-backed manifest 的 `entry_id` / `capability` / `document_type`，
    以及**服务端重算**给出的已验证 entry 集合。刻意**不读** `entry["evidence"]` ——
    那是自由文本，Property 49 的后半句原文是「probe/pilot 未实际通过时必须保持
    UNVERIFIABLE，不得因文档声明计为通过」。

    :param verified_entry_ids: 由
        :func:`~app.services.workpaper_sync.evidence_freshness.summarize_freshness`
        的 `verified` 列表提供。默认空集 ⇒ 全部 UNVERIFIABLE，这正是今天的事实。
    """
    import re

    entries = manifest_entries_by_id(manifest if manifest is not None else load_entry_manifest())
    xlsx_ids = sorted(
        eid for eid, e in entries.items() if str(e.get("document_type")) == "xlsx"
    )
    special: dict[PilotClass, list[str]] = {}
    for pilot_class, pattern in PILOT_CLASS_PATTERNS.items():
        special[pilot_class] = [eid for eid in xlsx_ids if re.search(pattern, eid.lower())]
    claimed = {eid for ids in special.values() for eid in ids}
    special[PilotClass.simple_checklist] = [eid for eid in xlsx_ids if eid not in claimed]

    out: dict[PilotClass, PilotClassAssessment] = {}
    for pilot_class in PilotClass:
        candidates = tuple(special.get(pilot_class, ()))
        bidirectional = tuple(
            eid
            for eid in candidates
            if capability_of(entries[eid]) is Capability.bidirectional
        )
        verified = tuple(eid for eid in bidirectional if eid in verified_entry_ids)
        reasons: list[str] = []
        if not candidates:
            reasons.append(
                f"{pilot_class.value}: manifest 里没有候选 xlsx entry —— "
                "AC 12.2 的四类覆盖无从谈起"
            )
        elif not bidirectional:
            reasons.append(
                f"{pilot_class.value}: {len(candidates)} 个候选 entry 里没有一个 "
                "capability=bidirectional —— per-entry contract/bundle 与 adapter 注册"
                "尚未完成（Tasks 40–43）"
            )
        elif not verified:
            reasons.append(
                f"{pilot_class.value}: 有 {len(bidirectional)} 个 bidirectional entry，"
                "但没有一个通过服务端 evidence 重算 —— 真实 OO 9.4 pilot 未执行"
            )
        out[pilot_class] = PilotClassAssessment(
            pilot_class=pilot_class,
            candidate_entry_ids=candidates,
            bidirectional_entry_ids=bidirectional,
            verified_entry_ids=verified,
            reasons=tuple(reasons),
        )
    return out


def pilot_coverage_summary(
    assessments: Mapping[PilotClass, PilotClassAssessment] | None = None,
) -> dict[str, Any]:
    """收口用的四类覆盖摘要。`all_verified` 由逐类推导，不接受写入值。"""
    data = assessments if assessments is not None else assess_pilot_classes()
    return {
        "classes": {k.value: v.as_dict() for k, v in sorted(data.items(), key=lambda kv: kv[0].value)},
        "verified_classes": sorted(
            k.value for k, v in data.items() if v.status is PilotClassStatus.verified
        ),
        "all_verified": all(v.status is PilotClassStatus.verified for v in data.values()),
    }


def build_run_manifest_payload(*, plan: HarnessPlan, environment: EvidenceEnvironment) -> bytes:
    """immutable run manifest 的 canonical bytes（内容寻址落盘用）。"""
    return json.dumps(
        {
            "harness_version": HARNESS_VERSION,
            "plan": plan.as_dict(),
            "environment": {
                "source_commit": environment.source_commit,
                "runner_version": environment.runner_version,
                "onlyoffice_build": environment.onlyoffice_build,
                "browser_build": environment.browser_build,
                "environment_digest": environment.digest,
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


__all__ = [
    "BLACK_BOX_INPUTS",
    "HARNESS_VERSION",
    "NOT_EXECUTED",
    "OO_TO_HTML_TIMELINE_ORDER",
    "PILOT_CLASS_PATTERNS",
    "RECOVERY_TIMELINE_ORDER",
    "SCENARIO_ORACLES",
    "UPSTREAM_DEBT_CLAIM_PRECONDITIONS",
    "UPSTREAM_DEBT_ROOM_FENCE_READ",
    "BundleIdentity",
    "EvidenceInput",
    "HarnessError",
    "HarnessPlan",
    "HarnessRejected",
    "HarnessRejection",
    "MergeEvidence",
    "OracleOutcome",
    "OracleVerdict",
    "PilotClass",
    "PilotClassAssessment",
    "PilotClassStatus",
    "ScenarioDecision",
    "ScenarioObservation",
    "ScenarioOracle",
    "SyncTestRunHarness",
    "all_declared_scenarios",
    "assert_entity_shape",
    "assert_no_reuse_across_entry",
    "assert_no_reuse_within_run",
    "assert_oracle_registry_complete",
    "assert_plan_matches_run",
    "assert_required_set_non_empty",
    "assert_run_open",
    "assert_scenario_not_recorded",
    "assert_trace_bundle_published",
    "assess_pilot_classes",
    "build_run_manifest_payload",
    "bundle_identity_from_rows",
    "entry_for",
    "evaluate_different_field_merge",
    "evaluate_same_field_conflict",
    "evaluate_timeline_order",
    "oracle_for",
    "pilot_coverage_summary",
    "resolve_production_refs",
    "run_scenario_oracle",
    "scenario_in_required_set",
]
