# -*- coding: utf-8 -*-
"""source-profile-derived required scenario set + 服务端 evidence 重算。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 29
Requirements: 12.10, 12.11, 12.12, 14.16
Properties: **P69 / P70 / P71**

═══ 三件事，三个理由 ═══

1. **required scenario set 只能从机器事实推导**（P69）
   Task 73 把 `editability / room_model / scenario_profile` 做成 source-backed 并计入
   manifest digest。所以「这个 entry 需要跑哪些场景」不是清单里的一行自由文本，而是
   :func:`derive_required_scenarios` 对 `(profile, capability, authority_model)` 的
   **纯函数**。把 profile 从 shared 改成 exclusive 就少几个 close 场景 —— 那正是 P71
   点名要禁的保鲜手法，因此 profile digest 与 required set digest 都进 test run，
   任一变化即 stale。

2. **evidence 不信自己写的 aggregate result**（P69）
   :class:`EvidenceRecomputer` 从 DB/artifact/timeline 逐项重算：required set 是否齐、
   每条 scenario 的外键是否真存在、hash 是否与 artifact 行一致、bundle/authority model
   是否与 run 冻结值一致、download-only 是否真的三实体为 0。写进 `aggregate_result` 的
   `passed` 只是被检查的输入之一。

3. **不得跨 entry / 跨 scenario 复用**（P70）
   同一个 operation/application/recovery case 被两条 scenario 或两个 entry 的 run 引用，
   意味着「逐 scenario 证据」是假的 —— 一条 applied operation 被复制成十条。
   :meth:`EvidenceRecomputer.recompute` 因此同时做**同 run 内**与**跨 run**两侧的复用检查。

═══ 为什么 base set 对 custom/opaque 也基本保留 ═══

AC 12.12 的原文只允许一处替换：「只能由 bundle 中枚举型 authority model 把**字段级两
场景**替换为『并发 authoritative artifact revision conflict + 无静默覆盖』；替换规则由
服务端 registry 守卫，禁止自由文本豁免」。也就是说 close / recovery / authorization /
dedupe / rollback 这些场景对 custom 与 opaque **一个都不能省**。
:data:`FIELD_LEVEL_SCENARIOS` 与 :data:`AUTHORITY_SUBSTITUTE_SCENARIOS` 是唯一的替换
对，:data:`NON_REPLACEABLE_SCENARIOS` 由 :func:`_apply_authority_substitution` 反向自检 ——
替换集合若碰到不可替换项就抛，而不是「悄悄少跑几个场景」。

═══ stale 的判据面 ═══

AC 14.16 列了七类变化：环境、source commit、runner、manifest source digest、
`editable/room_model/scenario_profile`、authority model definition、immutable definition
bundle/typed child、required scenario set。:class:`EvidenceEnvironment` 把前三类打成一个
可比对的指纹，后面几类逐字段比。**每类一个独立 stale 码** —— 共用一个码会让靠后的
检查被靠前的遮蔽（本 spec 已三次踩到）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final, Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import (
    WorkpaperArtifact,
    WorkpaperCallbackRecoveryCase,
    WorkpaperContentApplication,
    WorkpaperContentRepresentation,
    WorkpaperContentVersion,
    WorkpaperEntryEvidenceScenario,
    WorkpaperSyncOperation,
    WorkpaperSyncTestRun,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import (
    Capability,
    Editability,
    EntryProfile,
    EntryProfileError,
    RoomModel,
    assert_profile_consistent_with_capability,
    capability_of,
    extract_entry_profile,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.models import AuthorityModel, SyncDomainError

#: 推导算法版本。改推导规则**必须** +1：它进 required set digest，于是旧 evidence 自动
#: stale（否则「规则变了但旧证据仍算 verified」）。
DERIVATION_VERSION: Final[int] = 1


class EvidenceError(SyncDomainError):
    error_code = "sync_evidence_invalid"


class ScenarioDerivationError(EvidenceError):
    """推导输入非法（profile/capability/authority model 组合不可能存在）。"""

    error_code = "sync_scenario_derivation_invalid"


class ScenarioSubstitutionError(EvidenceError):
    """试图替换不可替换的场景（close/recovery/authorization）。"""

    error_code = "sync_scenario_substitution_forbidden"


class ScenarioKind(str, Enum):
    """`working_paper_entry_evidence_scenario.scenario_kind` 的取值域。

    🔴 与 V151 的 `ck_wpees_scenario_kind` **同域**，一个不多一个不少：

        CHECK (scenario_kind IN
            ('standard', 'download_only', 'recovery_reject', 'recovery_claim',
             'close_capture'))

    第一版这里写的是语义分类（direction/identity/merge/…12 个值），真库插入直接
    `CheckViolationError` —— 而离线守卫全绿，因为没有任何判据把这个字段与 DDL 对上。
    语义分组另有 :class:`ScenarioFamily` 承担；这个枚举只负责**DB 取值域**，因为 V151
    的三条 entity 约束（`ck_wpees_download_only_zero_entities` /
    `ck_wpees_standard_requires_entities` / `ck_wpees_recovery_claim_requires_case`）
    全部按它分支。
    """

    standard = "standard"
    download_only = "download_only"
    recovery_reject = "recovery_reject"
    recovery_claim = "recovery_claim"
    close_capture = "close_capture"


class ScenarioFamily(str, Enum):
    """语义分组。**不入库**，只用于推导「哪些场景不可替换」。"""

    direction = "direction"
    identity = "identity"
    merge = "merge"
    conflict = "conflict"
    dedupe = "dedupe"
    authorization = "authorization"
    recovery = "recovery"
    close = "close"
    rollback = "rollback"
    dynamic = "dynamic"
    word = "word"
    single_mode = "single_mode"


@dataclass(frozen=True)
class RequiredScenario:
    """一条必需场景。`why` 指到具体 AC，避免「这条到底为什么要跑」靠记忆。"""

    scenario_id: str
    family: ScenarioFamily
    requirement: str
    why: str
    #: 该场景是否**必须**有 operation + application（download-only/reject 类为 False）。
    expects_application: bool = True
    #: 该场景是否**必须**三实体为 0（download-only 类为 True）。
    expects_zero_entities: bool = False
    #: 该场景是否必须有 recovery case。
    expects_recovery_case: bool = False
    #: 期望的 close-capture 数（None = 本场景不检查 close capture）。
    expected_close_captures: int | None = None

    @property
    def kind(self) -> ScenarioKind:
        """入库用的 V151 `scenario_kind`，由 entity 期望**单点推导**。

        不让声明处各自手填：V151 的三条 entity 约束按 kind 分支，手填就会出现
        「kind 说 standard、entity 期望却是零」这种自相矛盾的行，插入时才炸。
        判定顺序即 V151 约束的分支顺序，不可交换。
        """
        if self.expects_zero_entities:
            return ScenarioKind.download_only
        if self.expects_recovery_case and not self.expects_application:
            return ScenarioKind.recovery_reject
        if self.expects_recovery_case:
            return ScenarioKind.recovery_claim
        if self.family is ScenarioFamily.close:
            return ScenarioKind.close_capture
        return ScenarioKind.standard

    @property
    def schema_representable_as_passed(self) -> bool:
        """该场景能否以 `result='passed'` 存进 V151。

        `standard` / `recovery_claim` / `close_capture` 三类在 `passed` 时被
        `ck_wpees_standard_requires_entities` 要求 `operation_ids>=1 AND
        application_ids>=1`。因此「零 application 且不属于 download_only/recovery_reject」
        的场景在当前 schema 下**无法**记成 passed —— 见
        :data:`SCHEMA_UNREPRESENTABLE_SCENARIOS`。
        """
        if self.kind in (ScenarioKind.download_only, ScenarioKind.recovery_reject):
            return True
        return self.expects_application


_S = RequiredScenario
_K = ScenarioFamily

#: projection-based 双向 entry 的无条件基础集（AC 12.12 第一句逐项）。
PROJECTION_BASE_SCENARIOS: Final[tuple[RequiredScenario, ...]] = (
    _S("html_to_oo", _K.direction, "3.1", "HTML 提交后 canonical artifact 可见"),
    _S("oo_to_html", _K.direction, "4.1", "durable callback 后结构化内容可见"),
    _S("identity_retention", _K.identity, "6.16", "identity 载体经 OO 往返仍保留"),
    _S("different_field_merge", _K.merge, "6.8", "不同字段并行修改自动合并"),
    _S(
        "same_field_conflict_resolve", _K.conflict, "6.8",
        "同字段异值进冲突预览并可人工裁决",
    ),
    _S(
        "frozen_base_status_6_2_dedupe", _K.dedupe, "4.3",
        "status 6/2 与网络重试命中同一 frozen identity 只应用一次",
    ),
    _S(
        "same_application_higher_sequence_fold", _K.dedupe, "5.5",
        "同 canonical application 的更高 sequence 只 fold，不 self-stale、origin 不改写",
    ),
    _S(
        "cross_participant_idempotency_409", _K.authorization, "4.1",
        "跨 participant 复用同 Idempotency-Key 及不同 kind/payload 均 409 且不泄露旧 ID。"
        "本场景**自带** operation+application：要有 key 可撞，A 侧那次 forcesave 必须先"
        "成功；「B 没有产生第二个实体」由场景 oracle 断言，不是靠 ID 列表为空表达",
    ),
    _S(
        "quarantined_rejects_application_and_engine", _K.authorization, "5.6",
        "quarantined incoming 在 application FK、coordinator 入口与 engine 三层各自被拒。"
        "按 AC 5.6 它**永不**创建 application，因此 application_ids 恒空",
        expects_application=False,
    ),
    _S(
        "opaque_version_rollback_no_numeric_collision", _K.rollback, "10.6",
        "rollback 只接受 opaque version UUID；跨 wp 相同 numeric revision 不碰撞",
    ),
    _S(
        "browser_crash_no_userdata_recovery_case", _K.recovery, "4.10",
        "无 userdata 的 crash close 建 recovery case，claim 前三实体为 0",
        expects_application=False,
        expects_recovery_case=True,
    ),
    _S(
        "authorization_first_recovery_claim", _K.recovery, "5.8",
        "authorization-first claim 在一个事务内建 request+shell 并创建/命中 application",
        expects_recovery_case=True,
    ),
    _S(
        "wrong_prior_confirmation_bundle_fence_contributor_rejected", _K.authorization, "5.8",
        "错误 prior confirmation / bundle / fence / contributor 一律拒绝且不产生 operation",
        expects_application=False,
        expects_recovery_case=True,
    ),
    _S(
        "download_only_zero_three_entities", _K.recovery, "12.11",
        "download-only 只终结 case 并签下载，request/application/operation 恒为 0",
        expects_application=False,
        expects_zero_entities=True,
        expects_recovery_case=True,
    ),
    _S(
        "refresh_required_reopen", _K.conflict, "4.11",
        "merged≠incoming ⇒ refresh_required，supersede/reopen 后才接受下一次 request",
    ),
    _S("rollback", _K.rollback, "14.2", "回滚到历史 content version 并重物化"),
)

#: `editable=true AND (capability=bidirectional OR room_model=shared)` 的无条件追加集。
CLOSE_SCENARIOS: Final[tuple[RequiredScenario, ...]] = (
    _S(
        "single_participant_close", _K.close, "4.10",
        "单用户 clean close 最终恰一个 close-capture",
        expected_close_captures=1,
    ),
    _S(
        "two_user_close_order_a_then_b", _K.close, "4.10",
        "两用户按 A→B 顺序关闭，最终恰一个 close-capture",
        expected_close_captures=1,
    ),
    _S(
        "two_user_close_order_b_then_a", _K.close, "4.10",
        "两用户按 B→A 顺序关闭，最终恰一个 close-capture",
        expected_close_captures=1,
    ),
    _S(
        "b_close_before_a_forcesave_terminal", _K.close, "4.10",
        "A 的普通 forcesave terminal **之前** B close：barrier 必须等前置 forcesave 安全终结",
        expected_close_captures=1,
    ),
    _S(
        "b_close_after_a_forcesave_terminal", _K.close, "4.10",
        "A 的普通 forcesave terminal **之后** B close",
        expected_close_captures=1,
    ),
    _S(
        "close_leader_revoked_successor_exactly_one", _K.close, "4.10",
        "leader promotion 前被 revoke/expire，存在合法 successor ⇒ 仍恰一个 capture",
        expected_close_captures=1,
    ),
    _S(
        "close_leader_revoked_no_successor_recovery_required", _K.close, "4.10",
        "无合法 successor ⇒ 零 capture + generation supersede + 显式 recovery_required。"
        "「零 capture」由 `expected_close_captures=0` 表达；场景本身仍有 A 侧普通 "
        "forcesave 的 operation+application（barrier 是在它之后才失去 leader 资格的）",
        expected_close_captures=0,
    ),
    _S(
        "close_reconciler_reentrant_exactly_one_capture", _K.close, "4.10",
        "`reconcile_close_intents()` 重入（同 eligibility snapshot 重放）不换 leader、不产生第二 capture",
        expected_close_captures=1,
    ),
)

#: 动态结构追加集（profile `mount_cardinality == dynamic`）。
DYNAMIC_SCENARIOS: Final[tuple[RequiredScenario, ...]] = (
    _S(
        "dynamic_row_add_delete_reorder_copy", _K.dynamic, "6.9",
        "动态行增删重排复制按 row identity 合并，不误判为整表覆盖",
    ),
    _S(
        "dynamic_column_stable_keys", _K.dynamic, "6.4",
        "横向动态列用稳定 key `{slot}_{seq}`，不写死列数、不用 label 作 identity",
    ),
)

#: Word-only 追加集（profile `document_type == docx`）。
WORD_SCENARIOS: Final[tuple[RequiredScenario, ...]] = (
    _S(
        "word_sdt_tag_row_uuid_retention", _K.word, "14.4",
        "SDT 的 tag/row_uuid 集合与层级经 OO 往返仍保留",
    ),
    _S(
        "word_free_body_isolation", _K.word, "6.19",
        "SDT 外自由正文只属于 Word，不反向覆盖 HTML 字段",
    ),
)

#: `single_html` 且无 room 的 entry：唯一必需场景。
SINGLE_HTML_SCENARIOS: Final[tuple[RequiredScenario, ...]] = (
    _S(
        "single_html_no_blank_oo_artifact", _K.single_mode, "3.9",
        "single_html entry 不创建空白 OO artifact，也不显示不可兑现的切换",
        expects_application=False,
        expects_zero_entities=True,
    ),
)

#: 唯一允许被 authority model 替换掉的两条字段级场景。
FIELD_LEVEL_SCENARIOS: Final[tuple[str, ...]] = (
    "different_field_merge",
    "same_field_conflict_resolve",
)

#: 替换进来的两条（AC 12.12 的「并发 authoritative artifact revision conflict + 无静默覆盖」）。
AUTHORITY_SUBSTITUTE_SCENARIOS: Final[tuple[RequiredScenario, ...]] = (
    _S(
        "authoritative_revision_conflict", _K.conflict, "12.12",
        "并发 authoritative artifact revision 冲突（custom/opaque 的字段级替代）",
    ),
    _S(
        "no_silent_overwrite", _K.conflict, "12.12",
        "冲突时不得静默覆盖权威文件（custom/opaque 的字段级替代）",
    ),
)

#: 🔴 **永不**可替换的场景 —— 反向自检用。按**语义家族**而不是入库 kind 判定：
#: 入库 kind 只有五个值且由 entity 形态推导，用它会把 `download_only` 与
#: `cross_participant_idempotency_409` 混在一起。
NON_REPLACEABLE_SCENARIOS: Final[frozenset[str]] = frozenset(
    scenario.scenario_id
    for scenario in PROJECTION_BASE_SCENARIOS + CLOSE_SCENARIOS
    if scenario.family
    in (ScenarioFamily.close, ScenarioFamily.recovery, ScenarioFamily.authorization)
)

#: 🔴 **当前 V151 schema 无法以 `result='passed'` 表达**的必需场景 + 原因 + owner。
#:
#: 这不是豁免：这些场景仍然在 required set 里，仍然必须跑，且它们的 entry **不会**被判
#: verified —— :class:`EvidenceRecomputer` 对它们记
#: :attr:`EvidenceDefect.scenario_kind_unrepresentable`，entry 保持未验收。登记在这里
#: 只是为了让「为什么永远差这一条」可归因，而不是每次重算都被当成新缺陷去查。
#:
#: 具体冲突：`ck_wpees_standard_requires_entities` 要求 `standard/recovery_claim/
#: close_capture` 的 passed 行必须 `application_ids>=1`，而 AC 5.6 明文规定 quarantined
#: incoming **永不**创建 application。两条同时成立时该行只能落 `failed/unverifiable`。
#: 解法属于 evidence schema 的 owner（Task 9 建表 / Task 39 harness / Task 70 全量刷新），
#: 例如给 V151 增加一个 `authorization_reject` kind。
SCHEMA_UNREPRESENTABLE_SCENARIOS: Final[Mapping[str, str]] = {
    "quarantined_rejects_application_and_engine": (
        "AC 5.6 要求 quarantined incoming 永不创建 application（application_ids 恒空），"
        "而 V151 的 ck_wpees_standard_requires_entities 要求非 download_only/"
        "recovery_reject 的 passed 行 application_ids>=1；两者当前不可同时满足。"
        "owner: evidence schema（V151 需要一个 authorization_reject kind）"
    ),
}

#: 允许把字段级两场景替换掉的 authority model（**枚举**，不是自由文本）。
SUBSTITUTING_AUTHORITY_MODELS: Final[frozenset[AuthorityModel]] = frozenset(
    {AuthorityModel.custom_authoritative_ooxml, AuthorityModel.opaque_single_onlyoffice}
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 推导
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RequiredScenarioSet:
    """一个 entry 的 required scenario set + 可复现 digest。"""

    entry_id: str
    scenarios: tuple[RequiredScenario, ...]
    capability: Capability
    authority_model: AuthorityModel
    editability: Editability
    room_model: RoomModel
    scenario_profile_digest: str
    substituted: bool
    close_required: bool

    @property
    def scenario_ids(self) -> tuple[str, ...]:
        return tuple(scenario.scenario_id for scenario in self.scenarios)

    def by_id(self, scenario_id: str) -> RequiredScenario | None:
        for scenario in self.scenarios:
            if scenario.scenario_id == scenario_id:
                return scenario
        return None

    @property
    def digest(self) -> str:
        """canonical digest。刻意含推导版本与全部输入身份 —— 任一变化即让旧 run stale。"""
        return canonical_digest(
            {
                "derivation_version": DERIVATION_VERSION,
                "entry_id": self.entry_id,
                "capability": self.capability.value,
                "authority_model": self.authority_model.value,
                "editability": self.editability.value,
                "room_model": self.room_model.value,
                "scenario_profile_digest": self.scenario_profile_digest,
                "scenario_ids": list(self.scenario_ids),
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "capability": self.capability.value,
            "authority_model": self.authority_model.value,
            "editability": self.editability.value,
            "room_model": self.room_model.value,
            "scenario_profile_digest": self.scenario_profile_digest,
            "substituted": self.substituted,
            "close_required": self.close_required,
            "scenario_ids": list(self.scenario_ids),
            "required_scenario_set_digest": self.digest,
        }


def close_scenarios_required(
    *, profile: EntryProfile, capability: Capability
) -> bool:
    """AC 12.12 的机器谓词：`editable=true AND (capability=bidirectional OR room_model=shared)`。

    单独成函数是为了让这条谓词只有**一处**定义、一处可变异。它是 179 个 shared-room
    entry 之所以必须跑 close 场景的唯一理由 —— 把 `or` 写成 `and` 会让绝大多数 entry
    悄悄少八个场景，而「场景都跑过了」的计数仍然满分。
    """
    return profile.editable and (
        capability is Capability.bidirectional or profile.room_model is RoomModel.shared
    )


def _apply_authority_substitution(
    scenarios: Sequence[RequiredScenario], *, authority_model: AuthorityModel
) -> tuple[RequiredScenario, ...]:
    """把字段级两场景替换为 authoritative-artifact 两场景。

    反向自检：替换目标只能是 :data:`FIELD_LEVEL_SCENARIOS`。若某天有人把
    `download_only_zero_three_entities` 加进替换名单，这里抛
    :class:`ScenarioSubstitutionError` 而不是少跑一个场景。
    """
    forbidden = sorted(set(FIELD_LEVEL_SCENARIOS) & NON_REPLACEABLE_SCENARIOS)
    if forbidden:
        raise ScenarioSubstitutionError(
            f"替换名单 {forbidden} 落在不可替换集合里 —— AC 12.12 只允许替换字段级两场景，"
            "close/recovery/authorization 一个都不能省"
        )
    if authority_model not in SUBSTITUTING_AUTHORITY_MODELS:
        raise ScenarioSubstitutionError(
            f"authority model {authority_model.value} 不在允许替换的枚举 "
            f"{sorted(m.value for m in SUBSTITUTING_AUTHORITY_MODELS)} 内 —— "
            "替换规则由服务端 registry 守卫，禁止自由文本豁免"
        )
    kept = [s for s in scenarios if s.scenario_id not in FIELD_LEVEL_SCENARIOS]
    removed = len(scenarios) - len(kept)
    if removed != len(FIELD_LEVEL_SCENARIOS):
        raise ScenarioSubstitutionError(
            f"字段级场景应恰被移除 {len(FIELD_LEVEL_SCENARIOS)} 条，实际 {removed} 条 —— "
            "基础集与替换名单已经不一致"
        )
    return tuple(kept) + AUTHORITY_SUBSTITUTE_SCENARIOS


def derive_required_scenarios(
    *,
    profile: EntryProfile,
    capability: Capability,
    authority_model: AuthorityModel,
) -> RequiredScenarioSet:
    """从 source-backed profile + capability + authority model 推导 required set。

    纯函数、无 IO、结果确定。**不读** manifest 里任何自由文本字段（`evidence`、
    `migration_state`、`legacy_reasons` 都不参与）。
    """
    # 🔴 交叉一致性**复用** Task 13 的唯一规则，不在这里再写一份。
    #
    # 第一版这里自带了「single_html 只允许 room_model=none」「unreachable 只允许
    # editability=unreachable」两条判断 —— 那正是同一条规则的第二份拷贝，将来
    # `_CAPABILITY_ROOM_MODEL` 改了这里不会跟着改。实测代价立刻可见：真 manifest 里有
    # 5 个 docx entry 是 `single_html + room_model=exclusive`（`room_model_fact =
    # frontend_endpoint_without_backend_route`），第二份拷贝把它们判成 derivation 错误
    # 并让整条推导崩掉；而委派给单一规则后它们变成一条可归因的 profile drift，由
    # `EvidenceRecomputer` 记成 unverified（欠账 owner 是 Task 1/67，不是本任务）。
    assert_profile_consistent_with_capability(profile, capability)

    if capability is Capability.unreachable:
        return RequiredScenarioSet(
            entry_id=profile.entry_id,
            scenarios=(),
            capability=capability,
            authority_model=authority_model,
            editability=profile.editability,
            room_model=profile.room_model,
            scenario_profile_digest=profile.scenario_profile.digest,
            substituted=False,
            close_required=False,
        )

    if capability is Capability.single_html:
        return RequiredScenarioSet(
            entry_id=profile.entry_id,
            scenarios=SINGLE_HTML_SCENARIOS,
            capability=capability,
            authority_model=authority_model,
            editability=profile.editability,
            room_model=profile.room_model,
            scenario_profile_digest=profile.scenario_profile.digest,
            substituted=False,
            close_required=False,
        )

    substituted = authority_model in SUBSTITUTING_AUTHORITY_MODELS
    base: tuple[RequiredScenario, ...] = PROJECTION_BASE_SCENARIOS
    if substituted:
        base = _apply_authority_substitution(base, authority_model=authority_model)

    scenarios: list[RequiredScenario] = list(base)
    close_required = close_scenarios_required(profile=profile, capability=capability)
    if close_required:
        scenarios.extend(CLOSE_SCENARIOS)

    payload = profile.scenario_profile.payload
    if str(payload.get("mount_cardinality") or "") == "dynamic":
        scenarios.extend(DYNAMIC_SCENARIOS)
    if str(payload.get("document_type") or "") == "docx":
        scenarios.extend(WORD_SCENARIOS)

    missing_non_replaceable = sorted(
        NON_REPLACEABLE_SCENARIOS
        - {s.scenario_id for s in scenarios}
        - (set() if close_required else {s.scenario_id for s in CLOSE_SCENARIOS})
    )
    if missing_non_replaceable:
        raise ScenarioSubstitutionError(
            f"{profile.entry_id}: 推导结果缺不可替换场景 {missing_non_replaceable}"
        )
    return RequiredScenarioSet(
        entry_id=profile.entry_id,
        scenarios=tuple(scenarios),
        capability=capability,
        authority_model=authority_model,
        editability=profile.editability,
        room_model=profile.room_model,
        scenario_profile_digest=profile.scenario_profile.digest,
        substituted=substituted,
        close_required=close_required,
    )


def derive_for_manifest_entry(
    entry: Mapping[str, Any], *, authority_model: AuthorityModel
) -> RequiredScenarioSet:
    """manifest entry → required set（profile 缺失时由 `extract_entry_profile` fail closed）。"""
    return derive_required_scenarios(
        profile=extract_entry_profile(entry),
        capability=capability_of(entry),
        authority_model=authority_model,
    )


def manifest_source_digest(manifest: Mapping[str, Any] | None = None) -> str:
    """manifest 的 source digest（进 test run，AC 14.16 的 stale 判据之一）。"""
    payload = manifest if manifest is not None else load_entry_manifest()
    digest = str(payload.get("source_digest") or "").strip()
    if not digest:
        raise EvidenceError(
            "manifest 缺 source_digest —— 没有它就无法判定 evidence 是否随源码变化 stale"
        )
    return digest


# ═══════════════════════════════════════════════════════════════════════════
# 2. 重算
# ═══════════════════════════════════════════════════════════════════════════


class StaleReason(str, Enum):
    """AC 14.16 逐类失效原因。逐条独立，禁止合并。"""

    manifest_source_digest_changed = "manifest_source_digest_changed"
    editability_changed = "editability_changed"
    room_model_changed = "room_model_changed"
    scenario_profile_changed = "scenario_profile_changed"
    required_scenario_set_changed = "required_scenario_set_changed"
    authority_model_changed = "authority_model_changed"
    definition_bundle_changed = "definition_bundle_changed"
    #: bundle 的 template/instrumentation/contract typed child identities 变了
    #: （AC 14.16 把「bundle」与「任一非-null definition child」列成两条独立轴）。
    #: emit 点在 :func:`evidence_freshness.bundle_stale_reasons` —— recomputer 拿不到
    #: bundle 输入，只能比同一批写入的两个副本，因此这三条轴由 Task 39 的 freshness
    #: guard 承担；合成一个码会让「child 被换掉而 bundle digest 未变」（篡改）与
    #: 「bundle 整体升级」（正常）分不出来。
    definition_bundle_child_changed = "definition_bundle_child_changed"
    source_commit_changed = "source_commit_changed"
    runner_changed = "runner_changed"
    onlyoffice_build_changed = "onlyoffice_build_changed"
    browser_build_changed = "browser_build_changed"
    environment_digest_changed = "environment_digest_changed"


class EvidenceDefect(str, Enum):
    """重算发现的缺陷分型。逐条独立。"""

    missing_scenario = "missing_scenario"
    extra_scenario = "extra_scenario"
    duplicate_scenario_row = "duplicate_scenario_row"
    ordinal_not_contiguous = "ordinal_not_contiguous"
    scenario_not_passed = "scenario_not_passed"
    dangling_operation_fk = "dangling_operation_fk"
    dangling_application_fk = "dangling_application_fk"
    dangling_recovery_case_fk = "dangling_recovery_case_fk"
    dangling_content_version_fk = "dangling_content_version_fk"
    dangling_representation_fk = "dangling_representation_fk"
    dangling_trace_bundle = "dangling_trace_bundle"
    trace_bundle_hash_mismatch = "trace_bundle_hash_mismatch"
    bundle_digest_mismatch = "bundle_digest_mismatch"
    authority_model_digest_mismatch = "authority_model_digest_mismatch"
    entity_scope_mismatch = "entity_scope_mismatch"
    download_only_has_entities = "download_only_has_entities"
    missing_recovery_case = "missing_recovery_case"
    missing_application = "missing_application"
    reused_within_run = "reused_within_run"
    reused_across_entry = "reused_across_entry"
    representation_not_published = "representation_not_published"
    run_manifest_hash_mismatch = "run_manifest_hash_mismatch"
    #: 必需场景在当前 evidence schema 下无法记成 passed
    #: （见 :data:`SCHEMA_UNREPRESENTABLE_SCENARIOS`）。**不是**豁免：entry 保持未验收。
    scenario_kind_unrepresentable = "scenario_kind_unrepresentable"
    #: source-backed profile 与 capability 交叉矛盾（Task 13 的单一规则判定）。
    #: 这类 entry **无法**推导 required set，因此恒 unverified —— 而不是让整个 gate 抛异常。
    profile_cross_rule_drift = "profile_cross_rule_drift"


class EvidenceResult(str, Enum):
    verified = "verified"
    unverified = "unverified"
    stale = "stale"


@dataclass(frozen=True)
class EvidenceEnvironment:
    """重算时的环境指纹。与 run 行逐字段比对（AC 14.16）。"""

    source_commit: str
    runner_version: str
    onlyoffice_build: str
    browser_build: str

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "source_commit": self.source_commit,
                "runner_version": self.runner_version,
                "onlyoffice_build": self.onlyoffice_build,
                "browser_build": self.browser_build,
            }
        )


@dataclass(frozen=True)
class EvidenceVerdict:
    """一次服务端重算的结论。`result` 由缺陷/stale 集合**推导**，不接受写入值。"""

    entry_id: str
    run_id: uuid.UUID | None
    required_scenario_ids: tuple[str, ...]
    observed_scenario_ids: tuple[str, ...]
    defects: tuple[EvidenceDefect, ...] = ()
    stale_reasons: tuple[StaleReason, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def result(self) -> EvidenceResult:
        if self.defects:
            return EvidenceResult.unverified
        if self.stale_reasons:
            return EvidenceResult.stale
        if not self.run_id:
            return EvidenceResult.unverified
        return EvidenceResult.verified

    @property
    def verified(self) -> bool:
        return self.result is EvidenceResult.verified

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "run_id": None if self.run_id is None else str(self.run_id),
            "required_scenario_ids": list(self.required_scenario_ids),
            "observed_scenario_ids": list(self.observed_scenario_ids),
            "defects": [d.value for d in self.defects],
            "stale_reasons": [s.value for s in self.stale_reasons],
            "notes": list(self.notes),
            "result": self.result.value,
        }


class EvidenceRecomputer:
    """服务端 evidence 重算器。

    输入是 `entry_id` 与（可选的）`run_id`；输出是 :class:`EvidenceVerdict`。
    **不写库** —— 重算是只读判定，写 `aggregate_result` 是 harness（Task 39）的事。
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        manifest: Mapping[str, Any] | None = None,
    ) -> None:
        self._session = session
        self._manifest = manifest if manifest is not None else load_entry_manifest()
        self._entries = manifest_entries_by_id(self._manifest)

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    async def recompute(
        self,
        *,
        entry_id: str,
        authority_model: AuthorityModel,
        environment: EvidenceEnvironment,
        run_id: uuid.UUID | None = None,
    ) -> EvidenceVerdict:
        entry = self._entries.get(entry_id)
        if entry is None:
            raise EvidenceError(
                f"manifest 里没有 entry {entry_id!r} —— 未登记入口不得产出 evidence"
            )
        try:
            required = derive_for_manifest_entry(entry, authority_model=authority_model)
        except EntryProfileError as exc:
            # profile 与 capability 交叉矛盾 ⇒ required set 不可推导 ⇒ 恒 unverified。
            # 刻意**不**上抛：一个 entry 的 manifest 欠账不该让整批重算失败，而「跳过它」
            # 会让它从计数里消失（那正是 AC 12.13 的五类计数最容易被做假的地方）。
            return EvidenceVerdict(
                entry_id=entry_id,
                run_id=None,
                required_scenario_ids=(),
                observed_scenario_ids=(),
                defects=(EvidenceDefect.profile_cross_rule_drift,),
                notes=(
                    f"source-backed profile 与 capability 矛盾，无法推导 required set："
                    f"{exc}",
                ),
            )

        run = await self._load_run(entry_id=entry_id, run_id=run_id)
        if run is None:
            return EvidenceVerdict(
                entry_id=entry_id,
                run_id=None,
                required_scenario_ids=required.scenario_ids,
                observed_scenario_ids=(),
                notes=("该 entry 没有任何 test run —— 未验收",),
            )

        stale = self._stale_reasons(run=run, required=required, environment=environment)
        defects: list[EvidenceDefect] = []
        notes: list[str] = []

        rows = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperEntryEvidenceScenario)
                    .where(WorkpaperEntryEvidenceScenario.run_id == run.id)
                    .order_by(WorkpaperEntryEvidenceScenario.ordinal)
                )
            ).scalars()
        )
        observed = tuple(str(row.scenario_id) for row in rows)

        defects.extend(self._set_defects(required=required, rows=rows, notes=notes))
        defects.extend(await self._row_defects(run=run, required=required, rows=rows, notes=notes))
        defects.extend(await self._reuse_defects(run=run, rows=rows, notes=notes))
        defects.extend(await self._run_manifest_defects(run=run, notes=notes))

        return EvidenceVerdict(
            entry_id=entry_id,
            run_id=run.id,
            required_scenario_ids=required.scenario_ids,
            observed_scenario_ids=observed,
            defects=tuple(_dedupe(defects)),
            stale_reasons=tuple(stale),
            notes=tuple(notes),
        )

    # ------------------------------------------------------------------
    # stale（AC 14.16）
    # ------------------------------------------------------------------

    def _stale_reasons(
        self,
        *,
        run: WorkpaperSyncTestRun,
        required: RequiredScenarioSet,
        environment: EvidenceEnvironment,
    ) -> list[StaleReason]:
        reasons: list[StaleReason] = []
        if str(run.manifest_source_digest) != manifest_source_digest(self._manifest):
            reasons.append(StaleReason.manifest_source_digest_changed)
        if str(run.editability) != required.editability.value:
            reasons.append(StaleReason.editability_changed)
        if str(run.room_model) != required.room_model.value:
            reasons.append(StaleReason.room_model_changed)
        if str(run.scenario_profile_digest) != required.scenario_profile_digest:
            reasons.append(StaleReason.scenario_profile_changed)
        if str(run.required_scenario_set_digest) != required.digest:
            reasons.append(StaleReason.required_scenario_set_changed)
        if str(run.source_commit) != environment.source_commit:
            reasons.append(StaleReason.source_commit_changed)
        if str(run.runner_version) != environment.runner_version:
            reasons.append(StaleReason.runner_changed)
        if str(run.onlyoffice_build) != environment.onlyoffice_build:
            reasons.append(StaleReason.onlyoffice_build_changed)
        if str(run.browser_build) != environment.browser_build:
            reasons.append(StaleReason.browser_build_changed)
        if str(run.environment_digest) != environment.digest:
            reasons.append(StaleReason.environment_digest_changed)
        return reasons

    # ------------------------------------------------------------------
    # 集合层缺陷
    # ------------------------------------------------------------------

    def _set_defects(
        self,
        *,
        required: RequiredScenarioSet,
        rows: Sequence[WorkpaperEntryEvidenceScenario],
        notes: list[str],
    ) -> list[EvidenceDefect]:
        defects: list[EvidenceDefect] = []
        observed_ids = [str(row.scenario_id) for row in rows]
        required_ids = set(required.scenario_ids)

        missing = sorted(required_ids - set(observed_ids))
        if missing:
            defects.append(EvidenceDefect.missing_scenario)
            notes.append(f"缺场景 {missing}")
        extra = sorted(set(observed_ids) - required_ids)
        if extra:
            defects.append(EvidenceDefect.extra_scenario)
            notes.append(
                f"多出未登记场景 {extra} —— required set 只能由推导产生，不接受追加自由项"
            )
        duplicates = sorted({sid for sid in observed_ids if observed_ids.count(sid) > 1})
        if duplicates:
            defects.append(EvidenceDefect.duplicate_scenario_row)
            notes.append(f"同一 scenario_id 出现多行 {duplicates}")
        ordinals = [int(row.ordinal) for row in rows]
        if ordinals and ordinals != list(range(1, len(ordinals) + 1)):
            defects.append(EvidenceDefect.ordinal_not_contiguous)
            notes.append(f"ordinal 不连续: {ordinals}")
        # 未 passed 的场景分两类，各自独立的缺陷码：
        #  ① schema 层无法表达（已登记，可归因）；
        #  ② 真的失败/UNVERIFIABLE。
        # 合成一个码会让「schema 欠账」把真实失败淹掉，反之则每次重算都要重新排查那条。
        unrepresentable: list[str] = []
        failed: list[str] = []
        for row in rows:
            if str(row.result) == "passed":
                continue
            sid = str(row.scenario_id)
            (unrepresentable if sid in SCHEMA_UNREPRESENTABLE_SCENARIOS else failed).append(sid)
        if unrepresentable:
            defects.append(EvidenceDefect.scenario_kind_unrepresentable)
            for sid in sorted(unrepresentable):
                notes.append(
                    f"{sid}: 当前 evidence schema 无法记成 passed —— "
                    f"{SCHEMA_UNREPRESENTABLE_SCENARIOS[sid]}"
                )
        if failed:
            defects.append(EvidenceDefect.scenario_not_passed)
            notes.append(f"未通过/UNVERIFIABLE 场景 {sorted(failed)}")
        return defects

    # ------------------------------------------------------------------
    # 行层缺陷（逐项重算外键与 hash）
    # ------------------------------------------------------------------

    async def _row_defects(
        self,
        *,
        run: WorkpaperSyncTestRun,
        required: RequiredScenarioSet,
        rows: Sequence[WorkpaperEntryEvidenceScenario],
        notes: list[str],
    ) -> list[EvidenceDefect]:
        defects: list[EvidenceDefect] = []
        for row in rows:
            scenario = required.by_id(str(row.scenario_id))
            label = f"scenario {row.scenario_id}"

            if str(row.definition_bundle_sha256) != str(run.definition_bundle_sha256):
                defects.append(EvidenceDefect.bundle_digest_mismatch)
                notes.append(f"{label}: bundle digest 与 run 冻结值不符")
            if str(row.authority_model_definition_sha256) != str(
                run.authority_model_definition_sha256
            ):
                defects.append(EvidenceDefect.authority_model_digest_mismatch)
                notes.append(f"{label}: authority model digest 与 run 冻结值不符")

            operation_ids = _uuids(row.operation_ids)
            application_ids = _uuids(row.application_ids)
            recovery_ids = _uuids(row.recovery_case_ids)
            version_ids = _uuids(row.content_version_ids)
            representation_ids = _uuids(row.representation_ids)

            if scenario is not None:
                if scenario.expects_zero_entities and (operation_ids or application_ids):
                    defects.append(EvidenceDefect.download_only_has_entities)
                    notes.append(
                        f"{label}: 该场景要求 operation/application 恒为 0，实得 "
                        f"{len(operation_ids)}/{len(application_ids)}"
                    )
                if scenario.expects_recovery_case and not recovery_ids:
                    defects.append(EvidenceDefect.missing_recovery_case)
                    notes.append(f"{label}: 该场景必须有 recovery case")
                if scenario.expects_application and not (operation_ids and application_ids):
                    defects.append(EvidenceDefect.missing_application)
                    notes.append(
                        f"{label}: 该场景必须同时有 operation 与 application"
                    )

            defects.extend(
                await self._fk_defects(
                    label=label,
                    run=run,
                    operation_ids=operation_ids,
                    application_ids=application_ids,
                    recovery_ids=recovery_ids,
                    version_ids=version_ids,
                    representation_ids=representation_ids,
                    notes=notes,
                )
            )
            defects.extend(await self._trace_defects(label=label, row=row, notes=notes))
        return defects

    async def _fk_defects(
        self,
        *,
        label: str,
        run: WorkpaperSyncTestRun,
        operation_ids: tuple[uuid.UUID, ...],
        application_ids: tuple[uuid.UUID, ...],
        recovery_ids: tuple[uuid.UUID, ...],
        version_ids: tuple[uuid.UUID, ...],
        representation_ids: tuple[uuid.UUID, ...],
        notes: list[str],
    ) -> list[EvidenceDefect]:
        defects: list[EvidenceDefect] = []
        entry_id = str(run.entry_id)

        found_ops = await self._fetch(WorkpaperSyncOperation, operation_ids)
        if len(found_ops) != len(operation_ids):
            defects.append(EvidenceDefect.dangling_operation_fk)
            notes.append(f"{label}: operation 外键悬挂")
        for op in found_ops:
            if str(op.entry_id) != entry_id:
                defects.append(EvidenceDefect.entity_scope_mismatch)
                notes.append(f"{label}: operation {op.id} 属于别的 entry {op.entry_id}")

        found_apps = await self._fetch(WorkpaperContentApplication, application_ids)
        if len(found_apps) != len(application_ids):
            defects.append(EvidenceDefect.dangling_application_fk)
            notes.append(f"{label}: application 外键悬挂")
        for application in found_apps:
            if str(application.entry_id) != entry_id:
                defects.append(EvidenceDefect.entity_scope_mismatch)
                notes.append(
                    f"{label}: application {application.id} 属于别的 entry "
                    f"{application.entry_id}"
                )
            if str(application.definition_bundle_sha256) != str(run.definition_bundle_sha256):
                defects.append(EvidenceDefect.bundle_digest_mismatch)
                notes.append(
                    f"{label}: application {application.id} 的 frozen bundle 与 run 不符"
                )

        found_cases = await self._fetch(WorkpaperCallbackRecoveryCase, recovery_ids)
        if len(found_cases) != len(recovery_ids):
            defects.append(EvidenceDefect.dangling_recovery_case_fk)
            notes.append(f"{label}: recovery case 外键悬挂")
        for case in found_cases:
            if str(case.entry_id) != entry_id:
                defects.append(EvidenceDefect.entity_scope_mismatch)
                notes.append(f"{label}: recovery case {case.id} 属于别的 entry")

        found_versions = await self._fetch(WorkpaperContentVersion, version_ids)
        if len(found_versions) != len(version_ids):
            defects.append(EvidenceDefect.dangling_content_version_fk)
            notes.append(f"{label}: content version 外键悬挂")

        found_reprs = await self._fetch(WorkpaperContentRepresentation, representation_ids)
        if len(found_reprs) != len(representation_ids):
            defects.append(EvidenceDefect.dangling_representation_fk)
            notes.append(f"{label}: representation 外键悬挂")
        for representation in found_reprs:
            if str(representation.entry_id) != entry_id:
                defects.append(EvidenceDefect.entity_scope_mismatch)
                notes.append(f"{label}: representation {representation.id} 属于别的 entry")
            artifact = (
                await self._session.execute(
                    sa.select(WorkpaperArtifact).where(
                        WorkpaperArtifact.id == representation.artifact_id
                    )
                )
            ).scalar_one_or_none()
            if artifact is None or str(artifact.state) != "published":
                # candidate 不得作为结果（AC 6.18 / 14.6）。这里不是「取不到就跳过」，
                # 而是明确记一条缺陷 —— 取不到本身就证明 evidence 不可重算。
                defects.append(EvidenceDefect.representation_not_published)
                notes.append(
                    f"{label}: representation {representation.id} 的 artifact 未 published"
                )
                continue
            if str(artifact.sha256) != str(representation.artifact_sha256):
                defects.append(EvidenceDefect.trace_bundle_hash_mismatch)
                notes.append(
                    f"{label}: representation artifact sha256 与登记值不符"
                )
        return defects

    async def _trace_defects(
        self,
        *,
        label: str,
        row: WorkpaperEntryEvidenceScenario,
        notes: list[str],
    ) -> list[EvidenceDefect]:
        defects: list[EvidenceDefect] = []
        artifact = (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(
                    WorkpaperArtifact.id == row.trace_bundle_artifact_id
                )
            )
        ).scalar_one_or_none()
        if artifact is None:
            defects.append(EvidenceDefect.dangling_trace_bundle)
            notes.append(f"{label}: trace bundle artifact 不存在")
            return defects
        if str(artifact.sha256) != str(row.trace_bundle_sha256):
            defects.append(EvidenceDefect.trace_bundle_hash_mismatch)
            notes.append(f"{label}: trace bundle sha256 与登记值不符")
        return defects

    # ------------------------------------------------------------------
    # 复用检查（Property 70）
    # ------------------------------------------------------------------

    async def _reuse_defects(
        self,
        *,
        run: WorkpaperSyncTestRun,
        rows: Sequence[WorkpaperEntryEvidenceScenario],
        notes: list[str],
    ) -> list[EvidenceDefect]:
        defects: list[EvidenceDefect] = []
        seen_ops: dict[uuid.UUID, str] = {}
        seen_apps: dict[uuid.UUID, str] = {}
        seen_cases: dict[uuid.UUID, str] = {}
        for row in rows:
            scenario_id = str(row.scenario_id)
            for bucket, values in (
                (seen_ops, _uuids(row.operation_ids)),
                (seen_apps, _uuids(row.application_ids)),
                (seen_cases, _uuids(row.recovery_case_ids)),
            ):
                for value in values:
                    if value in bucket and bucket[value] != scenario_id:
                        defects.append(EvidenceDefect.reused_within_run)
                        notes.append(
                            f"实体 {value} 同时被 {bucket[value]} 与 {scenario_id} 引用 —— "
                            "一条 applied operation 不能冒充多个互不等价的场景"
                        )
                    bucket.setdefault(value, scenario_id)

        all_ids = sorted(set(seen_ops) | set(seen_apps) | set(seen_cases))
        if not all_ids:
            return defects
        other_rows = list(
            (
                await self._session.execute(
                    sa.select(
                        WorkpaperEntryEvidenceScenario.operation_ids,
                        WorkpaperEntryEvidenceScenario.application_ids,
                        WorkpaperEntryEvidenceScenario.recovery_case_ids,
                        WorkpaperSyncTestRun.entry_id,
                        WorkpaperSyncTestRun.id,
                    )
                    .join(
                        WorkpaperSyncTestRun,
                        WorkpaperSyncTestRun.id == WorkpaperEntryEvidenceScenario.run_id,
                    )
                    .where(WorkpaperSyncTestRun.entry_id != run.entry_id)
                )
            ).all()
        )
        mine = set(all_ids)
        for op_ids, app_ids, case_ids, other_entry, other_run in other_rows:
            overlap = mine & (set(_uuids(op_ids)) | set(_uuids(app_ids)) | set(_uuids(case_ids)))
            if overlap:
                defects.append(EvidenceDefect.reused_across_entry)
                notes.append(
                    f"实体 {sorted(str(o) for o in overlap)} 同时出现在 entry "
                    f"{other_entry}（run {other_run}）的证据里 —— 跨 entry 复制证据"
                )
        return defects

    # ------------------------------------------------------------------
    # run manifest
    # ------------------------------------------------------------------

    async def _run_manifest_defects(
        self, *, run: WorkpaperSyncTestRun, notes: list[str]
    ) -> list[EvidenceDefect]:
        artifact = (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(
                    WorkpaperArtifact.id == run.run_manifest_artifact_id
                )
            )
        ).scalar_one_or_none()
        if artifact is None or str(artifact.sha256) != str(run.run_manifest_sha256):
            notes.append("run manifest artifact 缺失或 sha256 不符")
            return [EvidenceDefect.run_manifest_hash_mismatch]
        return []

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    async def _load_run(
        self, *, entry_id: str, run_id: uuid.UUID | None
    ) -> WorkpaperSyncTestRun | None:
        stmt = sa.select(WorkpaperSyncTestRun).where(
            WorkpaperSyncTestRun.entry_id == entry_id
        )
        if run_id is not None:
            stmt = stmt.where(WorkpaperSyncTestRun.id == run_id)
        stmt = stmt.order_by(WorkpaperSyncTestRun.started_at.desc()).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _fetch(self, model: Any, ids: Sequence[uuid.UUID]) -> list[Any]:
        if not ids:
            return []
        return list(
            (
                await self._session.execute(sa.select(model).where(model.id.in_(list(ids))))
            ).scalars()
        )


def _uuids(raw: Any) -> tuple[uuid.UUID, ...]:
    """JSONB 里的 id 列表 → UUID 元组。非法值 fail closed（不静默丢）。"""
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise EvidenceError(f"scenario id 列表必须是数组，实得 {type(raw).__name__}")
    out: list[uuid.UUID] = []
    for item in raw:
        try:
            out.append(item if isinstance(item, uuid.UUID) else uuid.UUID(str(item)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise EvidenceError(f"scenario id 列表含非法 UUID: {item!r}") from exc
    return tuple(out)


def _dedupe(items: Sequence[EvidenceDefect]) -> list[EvidenceDefect]:
    seen: list[EvidenceDefect] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


__all__ = [
    "AUTHORITY_SUBSTITUTE_SCENARIOS",
    "CLOSE_SCENARIOS",
    "DERIVATION_VERSION",
    "DYNAMIC_SCENARIOS",
    "FIELD_LEVEL_SCENARIOS",
    "NON_REPLACEABLE_SCENARIOS",
    "PROJECTION_BASE_SCENARIOS",
    "SCHEMA_UNREPRESENTABLE_SCENARIOS",
    "SINGLE_HTML_SCENARIOS",
    "SUBSTITUTING_AUTHORITY_MODELS",
    "WORD_SCENARIOS",
    "EvidenceDefect",
    "EvidenceEnvironment",
    "EvidenceError",
    "EvidenceRecomputer",
    "EvidenceResult",
    "EvidenceVerdict",
    "RequiredScenario",
    "RequiredScenarioSet",
    "ScenarioDerivationError",
    "ScenarioFamily",
    "ScenarioKind",
    "ScenarioSubstitutionError",
    "StaleReason",
    "close_scenarios_required",
    "derive_for_manifest_entry",
    "derive_required_scenarios",
    "manifest_source_digest",
]
