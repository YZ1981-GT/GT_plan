# -*- coding: utf-8 -*-
"""Task 26 离线守卫：substrate 来源、最终授权 fence、双基线裁决与结构判据。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 26
Requirements: 2.9, 4.2, 4.3, 4.5, 4.6, 4.11, 4.12, 5.8, 6.8, 6.9, 6.11,
8.9, 8.10, 8.11, 8.12, 10.10
Properties: **P14 / P19 / P25 / P26 / P27 / P29 / P38 / P43 / P62 / P65**

═══ 本文件与 `_pg.py` 的分工 ═══

放在这里的是**不需要数据库**就能证伪的判据，且每一条都必须是「换掉一个字符就红」的
形态：

* 纯判据函数（`assert_coordinator_substrate_admissible` /
  `assert_final_authorization` / `assert_projection_result_has_approved_contract` /
  `settlement_digest_pair`）—— 用合成输入逐分支喂。这些函数**必须**是模块级纯函数，
  否则「短路其中一条」在真库 happy path 上不可达 ⇒ 变异检验判 GREEN
  （Task 24 已为此把三条判据从方法里抽出来）。
* 结构判据（AST）—— `assert_substrate_resolution_source_shape` /
  `assert_no_command_service_reference`。它们禁止的是**代码形态**，运行期观察不到。
* 状态机与轨迹（`ApplyJournal`）—— 顺序是判据，因此顺序必须可断言。
* 异常分型 —— 「两条拒绝共用 error_code」在本 spec 已付三次代价，这里逐个钉死。

真库行为（三方 merge 走通、单事务、incoming 未被晋升、fence 真的拦住 commit、
retry 不新建 operation/application）在 `test_task26_oo_to_html_pg.py`。

═══ 为什么没有 mock ═══

Excel/Word engine 归 Tasks 36~38 / 59~61，此刻不存在。Task 13 定义 adapter protocol
的目的就是让域逻辑可以在**真写真读**的载体替身上验证：本文件的
:class:`_JsonCarrierAdapter` 真写 zip、真读回来，roundtrip 等值判据因此在真实执行上
生效（与 Task 15 的 PG 守卫同一个替身形态）。repository / session 一律不替身 ——
需要它们的判据全部在 `_pg.py`。
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import textwrap
import uuid
from datetime import datetime, timezone

import pytest

from app.services.workpaper_sync import oo_to_html as OH
from app.services.workpaper_sync.models import (
    APPLICATION_EDGES,
    ApplicationState,
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
    ParticipantState,
    QuarantinedIncomingError,
    RequestKind,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 合成夹具
# ═══════════════════════════════════════════════════════════════════════════

ROOM = uuid.uuid4()
PROJECT = uuid.uuid4()
WP = uuid.uuid4()
ENTRY = "xlsx/gt-d2-accounts-receivable"
APP = uuid.uuid4()
INCOMING = uuid.uuid4()
BUNDLE = uuid.uuid4()
AUTHORITY = uuid.uuid4()
INITIATOR = uuid.uuid4()
USER_A = uuid.uuid4()


def _bundle(*, contract_is_definition: bool = True) -> DefinitionBundleSnapshot:
    """approved projection_contract bundle 快照。

    `contract_is_definition=False` 时把 contract slot 换成版本化 typed null marker ——
    那正是 custom/opaque 专用形态，projection-based result 用它必须立即失败（AC 8.12）。
    """
    contract_slot = (
        BundleSlotSpec(
            BundleSlot.contract,
            "definition",
            f"definition:{uuid.uuid4()}",
            _d("contract-child"),
        )
        if contract_is_definition
        else BundleSlotSpec(
            BundleSlot.contract, "contract:none:v1", "contract:none:v1", _d("null-marker")
        )
    )
    return DefinitionBundleSnapshot(
        bundle_id=BUNDLE,
        bundle_sha256=_d("bundle-canonical"),
        schema_version="gt.sync.bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=AUTHORITY,
        authority_model_definition_sha256=_d("authority-child"),
        slots={
            BundleSlot.template: BundleSlotSpec(
                BundleSlot.template, "definition", f"definition:{uuid.uuid4()}", _d("tpl")
            ),
            BundleSlot.instrumentation: BundleSlotSpec(
                BundleSlot.instrumentation,
                "definition",
                f"definition:{uuid.uuid4()}",
                _d("instr"),
            ),
            BundleSlot.contract: contract_slot,
        },
    )


def _frozen(**over) -> OH.FrozenApplicationIdentity:
    kwargs = dict(
        application_id=APP,
        project_id=PROJECT,
        wp_id=WP,
        entry_id=ENTRY,
        room_id=ROOM,
        generation=3,
        origin_request_id=uuid.uuid4(),
        origin_request_sequence=7,
        effective_request_sequence=7,
        client_edit_epoch=2,
        incoming_artifact_id=INCOMING,
        incoming_sha256=_d("incoming-bytes"),
        base_version_id=uuid.uuid4(),
        base_representation_id=uuid.uuid4(),
        current_revision=11,
        definition_bundle_id=BUNDLE,
        definition_bundle_sha256=_d("bundle-canonical"),
        authority_model_definition_id=AUTHORITY,
        authority_model_definition_sha256=_d("authority-child"),
        adapter_id="excel.d2.v1",
        adapter_build_digest=_d("adapter-build"),
        contributor_snapshot_digest=_d("contributors"),
        state=OH.ApplicationState.rematerializing,
        frozen_write_fence_epoch=5,
        frozen_initiator_participant_id=INITIATOR,
        frozen_initiator_permission_epoch=9,
        frozen_client_base_projection_sha256=_d("client-base-projection"),
        # 默认是普通 forcesave（没有 leader 资格快照）；close-capture 的用例显式覆盖。
        frozen_request_kind=RequestKind.forcesave,
        frozen_close_leader_eligibility_epoch=None,
    )
    kwargs.update(over)
    return OH.FrozenApplicationIdentity(**kwargs)


def _observed(**over) -> OH.LiveAuthorizationFacts:
    """与 `_frozen()` **逐项匹配**的 live 事实（= fence 应当放行的基线）。"""
    kwargs = dict(
        project_visible=True,
        workflow_locked=False,
        room_generation=3,
        room_write_fence_epoch=5,
        room_state="active",
        room_refresh_required=False,
        initiator_participant_id=INITIATOR,
        initiator_permission_epoch=9,
        initiator_state=ParticipantState.active.value,
        contributor_snapshot_digest=_d("contributors"),
        current_definition_bundle_id=BUNDLE,
        current_definition_bundle_sha256=_d("bundle-canonical"),
        close_leader_eligibility_epoch=0,
    )
    kwargs.update(over)
    return OH.LiveAuthorizationFacts(**kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# 一、substrate 来源与三层拒绝的第二层（AC 4.3 / 8.10 / Property 65）
# ═══════════════════════════════════════════════════════════════════════════


def _admissible(**over):
    kwargs = dict(
        origin=OH.LEGAL_SUBSTRATE_ORIGIN,
        artifact_kind=ArtifactKind.incoming,
        artifact_state=ArtifactState.durable,
        durable_at=_now(),
        published_at=None,
        declared_incoming_artifact_id=INCOMING,
        resolved_artifact_id=INCOMING,
    )
    kwargs.update(over)
    return kwargs


class TestSubstrateAdmission:
    def test_durable_incoming_from_application_fk_is_admitted(self) -> None:
        OH.assert_coordinator_substrate_admissible(**_admissible())

    @pytest.mark.parametrize(
        "origin",
        [
            OH.SubstrateOrigin.callback_room_pointer,
            OH.SubstrateOrigin.registry_current_alias,
            OH.SubstrateOrigin.upgrade_candidate,
            OH.SubstrateOrigin.operation_path,
        ],
        ids=["room_pointer", "registry_alias", "upgrade_candidate", "operation_path"],
    )
    def test_every_forbidden_origin_is_rejected(self, origin) -> None:
        """AC 4.3/8.10 逐条点名的四种「猜 substrate」形态都必须独立被拒。

        参数化而不是写一条：合成成一条 `origin != legal` 时，删掉任一枚举值不会让判据
        变红（剩下的值仍然不等），于是「四种都被拒」退化成「至少有一种被拒」。
        """
        with pytest.raises(OH.SubstrateOriginForbiddenError) as exc:
            OH.assert_coordinator_substrate_admissible(**_admissible(origin=origin))
        assert exc.value.error_code == "substrate_origin_forbidden"

    def test_legal_origin_but_different_artifact_id_is_rejected(self) -> None:
        """声明 origin 合法而 id 不符 ⇒ 仍拒。

        这条与上一条不是重复：只查 origin 时，「从 room pointer 查到一个 artifact 再把
        origin 写成 application_incoming_fk」照样过关 —— 声明是意图，id 相等才是事实。
        """
        with pytest.raises(OH.SubstrateOriginForbiddenError):
            OH.assert_coordinator_substrate_admissible(
                **_admissible(resolved_artifact_id=uuid.uuid4())
            )

    def test_quarantined_is_rejected_with_coordinator_specific_type(self) -> None:
        """coordinator 层的隔离拒绝必须是**自己的**类型，不能复用 DB/engine 的那个。

        三层拒绝共用一个异常类型时，删掉中间层会被上下游遮蔽 ⇒ 变异检验判 GREEN。
        """
        with pytest.raises(OH.SubstrateQuarantinedError) as exc:
            OH.assert_coordinator_substrate_admissible(
                **_admissible(artifact_state=ArtifactState.quarantined, durable_at=None)
            )
        assert exc.value.error_code == "substrate_incoming_quarantined_coordinator"
        assert not isinstance(exc.value, QuarantinedIncomingError)

    def test_non_incoming_kind_is_rejected(self) -> None:
        with pytest.raises(OH.SubstrateNotIncomingError) as exc:
            OH.assert_coordinator_substrate_admissible(
                **_admissible(artifact_kind=ArtifactKind.canonical, artifact_state=ArtifactState.published)
            )
        assert exc.value.error_code == "substrate_not_incoming_kind"

    def test_incoming_not_yet_durable_is_a_distinct_transient_type(self) -> None:
        """「尚未 durable」是暂态，与隔离终态分型（否则前者永久不可达）。"""
        with pytest.raises(OH.SubstrateNotDurableError) as exc:
            OH.assert_coordinator_substrate_admissible(
                **_admissible(artifact_state=ArtifactState.staged, durable_at=None)
            )
        assert exc.value.error_code == "substrate_incoming_not_durable"

    def test_durable_state_without_durable_at_is_rejected(self) -> None:
        """`state=durable` 但 `durable_at` 为空 = 半写入态，同样拒。"""
        with pytest.raises(OH.SubstrateNotDurableError):
            OH.assert_coordinator_substrate_admissible(**_admissible(durable_at=None))

    def test_incoming_with_published_at_is_rejected(self) -> None:
        """incoming 带 `published_at` ⇒ 有人试过晋升它（AC 8.10 / Property 65）。"""
        with pytest.raises(OH.SubstrateOriginForbiddenError):
            OH.assert_coordinator_substrate_admissible(
                **_admissible(published_at=_now())
            )

    def test_all_substrate_error_codes_are_distinct(self) -> None:
        codes = [
            OH.SubstrateOriginForbiddenError.error_code,
            OH.SubstrateNotIncomingError.error_code,
            OH.SubstrateNotDurableError.error_code,
            OH.SubstrateQuarantinedError.error_code,
            OH.SubstrateFileMissingError.error_code,
        ]
        assert len(set(codes)) == len(codes), f"error_code 撞车: {codes}"


class TestQuarantineWhitelist:
    @pytest.mark.parametrize(
        "op", sorted(OH.QUARANTINE_ALLOWED_OPERATIONS), ids=lambda v: v
    )
    def test_whitelisted_operations_pass(self, op: str) -> None:
        OH.assert_quarantined_operation_allowed(op)

    @pytest.mark.parametrize(
        "op",
        [
            "release",
            "promote_to_durable",
            "create_application",
            "extract",
            "merge",
            "retry",
            "rematerialize",
        ],
        ids=lambda v: v,
    )
    def test_everything_else_is_refused(self, op: str) -> None:
        with pytest.raises(OH.QuarantinedOperationForbiddenError):
            OH.assert_quarantined_operation_allowed(op)

    def test_whitelist_is_exactly_the_three_allowed_actions(self) -> None:
        """Requirement 5.6 原文三项。白名单被悄悄加一项时本条打红。"""
        assert OH.QUARANTINE_ALLOWED_OPERATIONS == frozenset(
            {"download_only", "expire", "retention"}
        )


# ═══════════════════════════════════════════════════════════════════════════
# 一之二、apply 入口的状态准入：同一 frozen application 只应用一次（AC 4.3 / 8.12）
# ═══════════════════════════════════════════════════════════════════════════


class TestApplyStateAdmission:
    """`APPLICATION_EDGES` 反向可达性推出的准入集合，两条拒绝各自分型。

    为什么必须在入口拦：`APPLICATION_EDGES[applied]` 是空集，于是
    `_walk_application` 的「到不了这一站就跳过」会静默跳过整条 pipeline，
    `_advance_application` 又在 `from_state == to_state` 时提前返回 ——
    一次异常都不抛，Task 15 照常提交第二个 revision（真库实测，见 `_pg` 的 S16）。
    """

    @pytest.mark.parametrize(
        "state",
        sorted(OH.APPLY_ADMISSIBLE_APPLICATION_STATES, key=lambda s: s.value),
        ids=lambda s: s.value,
    )
    def test_every_admissible_state_passes(self, state) -> None:
        OH.assert_application_state_admits_apply(
            state, application_id=APP, attempt=1
        )

    @pytest.mark.parametrize(
        "state,exc_type,code",
        [
            (
                ApplicationState.applied,
                OH.ReapplyForbiddenError,
                "application_already_applied",
            ),
            (
                ApplicationState.refresh_required,
                OH.ReapplyForbiddenError,
                "application_already_applied",
            ),
            (
                ApplicationState.superseded,
                OH.ApplicationTerminalStaleError,
                "application_terminal_not_retryable",
            ),
            (
                ApplicationState.authorization_stale,
                OH.ApplicationTerminalStaleError,
                "application_terminal_not_retryable",
            ),
        ],
        ids=["applied", "refresh_required", "superseded", "authorization_stale"],
    )
    def test_every_inadmissible_state_is_refused_with_its_own_code(
        self, state, exc_type: type, code: str
    ) -> None:
        with pytest.raises(exc_type) as exc:
            OH.assert_application_state_admits_apply(
                state, application_id=APP, attempt=2
            )
        assert exc.value.error_code == code, (
            "「已成功过」与「已作废」后续动作完全不同（reload vs supersede/recovery），"
            "共用 error_code 时靠前那条永久不可达"
        )

    def test_admissible_set_is_derived_from_the_edge_registry(self) -> None:
        """准入集合 = 能（传递地）到达 `applying` 的状态。手写第二份名单即第二真源。"""
        assert OH.APPLY_ADMISSIBLE_APPLICATION_STATES == frozenset(
            {
                ApplicationState.queued,
                ApplicationState.validating,
                ApplicationState.extracting,
                ApplicationState.merging,
                ApplicationState.conflict,
                ApplicationState.rematerializing,
                ApplicationState.applying,
                ApplicationState.error,
            }
        )
        # 与登记表双向锁死：任一终态若长出通往 `applying` 的边，本条立刻红。
        for state in OH.APPLY_ADMISSIBLE_APPLICATION_STATES:
            assert APPLICATION_EDGES.get(state), (
                f"{state.value} 被判为可准入却没有任何出边 —— 反向可达性算错了"
            )

    def test_every_application_state_is_classified(self) -> None:
        """枚举新增终态时必须显式归类（import 期已锁；这里再落一条可读判据）。"""
        classified = OH.APPLY_ADMISSIBLE_APPLICATION_STATES | {
            ApplicationState.applied,
            ApplicationState.refresh_required,
            ApplicationState.superseded,
            ApplicationState.authorization_stale,
        }
        assert classified == frozenset(ApplicationState)

    def test_retry_of_an_error_application_is_admissible(self) -> None:
        """AC 8.9：durable incoming 的 retry 必须能进（`error → extracting` 是登记边）。"""
        OH.assert_application_state_admits_apply(
            ApplicationState.error, application_id=APP, attempt=2
        )


# ═══════════════════════════════════════════════════════════════════════════
# 二、projection-based result 立即要求 approved contract child（AC 8.12）
# ═══════════════════════════════════════════════════════════════════════════


class TestApprovedContractChild:
    def test_approved_definition_contract_slot_passes(self) -> None:
        OH.assert_projection_result_has_approved_contract(_bundle())

    def test_typed_null_marker_contract_slot_fails_immediately(self) -> None:
        with pytest.raises(OH.ApprovedContractChildMissingError) as exc:
            OH.assert_projection_result_has_approved_contract(
                _bundle(contract_is_definition=False)
            )
        assert exc.value.error_code == "projection_result_missing_approved_contract"

    def test_missing_contract_slot_fails(self) -> None:
        bundle = _bundle()
        slots = {k: v for k, v in bundle.slots.items() if k is not BundleSlot.contract}
        with pytest.raises(OH.ApprovedContractChildMissingError):
            OH.assert_projection_result_has_approved_contract(
                DefinitionBundleSnapshot(
                    bundle_id=bundle.bundle_id,
                    bundle_sha256=bundle.bundle_sha256,
                    schema_version=bundle.schema_version,
                    state=bundle.state,
                    authority_model=bundle.authority_model,
                    authority_model_definition_id=bundle.authority_model_definition_id,
                    authority_model_definition_sha256=(
                        bundle.authority_model_definition_sha256
                    ),
                    slots=slots,
                )
            )

    def test_custom_authority_model_is_out_of_scope_and_passes(self) -> None:
        """custom/opaque 的 contract slot 本来就该是 typed null marker ⇒ 不适用本判据。

        没有这条，「对所有 authority model 都要求 approved contract」会把
        Requirement 6.19 反过来违反掉。
        """
        bundle = _bundle(contract_is_definition=False)
        custom = DefinitionBundleSnapshot(
            bundle_id=bundle.bundle_id,
            bundle_sha256=bundle.bundle_sha256,
            schema_version=bundle.schema_version,
            state=bundle.state,
            authority_model=AuthorityModel.custom_authoritative_ooxml,
            authority_model_definition_id=bundle.authority_model_definition_id,
            authority_model_definition_sha256=bundle.authority_model_definition_sha256,
            slots=bundle.slots,
        )
        OH.assert_projection_result_has_approved_contract(custom)


# ═══════════════════════════════════════════════════════════════════════════
# 三、最终授权 fence 的十条独立分支（AC 10.10 / Property 43）
# ═══════════════════════════════════════════════════════════════════════════

#: close-capture 的冻结身份：只有它才带 leader 资格快照。
_CLOSE_CAPTURE = {
    "frozen_request_kind": RequestKind.close_capture,
    "frozen_close_leader_eligibility_epoch": 4,
}

#: 每一行 = (case id, frozen 覆盖, 观测覆盖, 期望异常类型, 期望 error_code)
_FENCE_CASES = [
    (
        "project_revoked",
        {},
        {"project_visible": False},
        OH.ProjectNotVisibleError,
        "final_fence_project_not_visible",
    ),
    (
        "workflow_locked",
        {},
        {"workflow_locked": True},
        OH.WorkflowLockedError,
        "final_fence_workflow_locked",
    ),
    (
        "generation_superseded",
        {},
        {"room_generation": 4},
        OH.GenerationSupersededError,
        "final_fence_generation_superseded",
    ),
    (
        "write_fence_advanced",
        {},
        {"room_write_fence_epoch": 6},
        OH.WriteFenceAdvancedError,
        "final_fence_write_fence_advanced",
    ),
    (
        "initiator_vanished",
        {},
        {"initiator_participant_id": None},
        OH.InitiatorMissingError,
        "final_fence_initiator_missing",
    ),
    (
        "initiator_replaced",
        {},
        {"initiator_participant_id": uuid.uuid4()},
        OH.InitiatorMissingError,
        "final_fence_initiator_missing",
    ),
    (
        "permission_epoch_changed",
        {},
        {"initiator_permission_epoch": 10},
        OH.InitiatorEpochChangedError,
        "final_fence_initiator_epoch_changed",
    ),
    (
        "initiator_revoked",
        {},
        {"initiator_state": ParticipantState.revoked.value},
        OH.InitiatorNotLiveError,
        "final_fence_initiator_not_live",
    ),
    (
        "initiator_expired",
        {},
        {"initiator_state": ParticipantState.expired.value},
        OH.InitiatorNotLiveError,
        "final_fence_initiator_not_live",
    ),
    (
        "contributor_drift",
        {},
        {"contributor_snapshot_digest": _d("someone-else")},
        OH.ContributorSnapshotDriftError,
        "final_fence_contributor_snapshot_drift",
    ),
    (
        "bundle_replaced_id",
        {},
        {"current_definition_bundle_id": uuid.uuid4()},
        OH.ApprovedBundleReplacedError,
        "final_fence_approved_bundle_replaced",
    ),
    (
        "bundle_replaced_digest",
        {},
        {"current_definition_bundle_sha256": _d("другой")},
        OH.ApprovedBundleReplacedError,
        "final_fence_approved_bundle_replaced",
    ),
    # ── eligibility：判据是「promotion 当时冻结的 epoch」↔「room 当下的 epoch」──
    #
    # 🔴 这两行替换了旧的 `close_leader_eligibility_epoch < 0`。那条判据是重言式：
    # `room.close_leader_eligibility_epoch` 是 bigint、server_default 0、全仓库唯一
    # 写入点只做 `+1`（`repository.reconcile_close_intents`），因此**永远非负** ⇒
    # `EligibilityEpochAdvancedError` provably-dead，而 `compared` 里那一项名却在
    # 宣称「eligibility 已重验」。AC 10.10 要重验的是 leader 资格是否仍然成立。
    (
        "close_capture_eligibility_advanced",
        _CLOSE_CAPTURE,
        {"close_leader_eligibility_epoch": 5},
        OH.EligibilityEpochAdvancedError,
        "final_fence_eligibility_epoch_advanced",
    ),
    (
        "close_capture_eligibility_unproven",
        {
            "frozen_request_kind": RequestKind.close_capture,
            "frozen_close_leader_eligibility_epoch": None,
        },
        {"close_leader_eligibility_epoch": 4},
        OH.CloseCaptureEligibilityUnprovenError,
        "final_fence_close_capture_eligibility_unproven",
    ),
]


_FENCE_HEAD = (
    "project_visible",
    "workflow_locked",
    "room_generation",
    "write_fence_epoch",
    "initiator_present",
    "initiator_permission_epoch",
    "initiator_state",
    "contributor_snapshot_digest",
    "approved_bundle_identity",
)


class TestFinalAuthorizationFence:
    def test_matching_facts_pass_and_report_every_compared_item(self) -> None:
        compared = OH.assert_final_authorization(frozen=_frozen(), observed=_observed())
        assert compared == _FENCE_HEAD + ("close_leader_eligibility_not_applicable",), (
            "十条重验的**项名与顺序**是判据本体（AC 10.10 逐项列举）。只断言「抛了 "
            "FinalFenceError」时，删掉其中九条守卫照样绿 —— 剩下那条会顶上来。"
            "末项对普通 forcesave 必须如实报「不适用」：报成 "
            "`close_leader_eligibility_epoch` 就是在宣称比过了一个它根本没有的量。"
        )

    def test_close_capture_reports_a_real_eligibility_comparison(self) -> None:
        """close-capture 走**另一条**项名，且 epoch 相等时放行（正对照）。

        没有这条正对照，把 eligibility 分支写成「close-capture 一律拒」也能让
        `close_capture_eligibility_advanced` 变红 —— 那会让 clean close 恒失败。
        """
        compared = OH.assert_final_authorization(
            frozen=_frozen(**_CLOSE_CAPTURE),
            observed=_observed(close_leader_eligibility_epoch=4),
        )
        assert compared == _FENCE_HEAD + ("close_leader_eligibility_epoch",)

    def test_eligibility_is_not_compared_for_ordinary_forcesave(self) -> None:
        """普通 forcesave 的 epoch 与 room 不同也不该拦（AC 10.10 只约束 leader 资格）。

        普通 forcesave 从不经 leader 仲裁：把 room 的 epoch 拿来跟它比，比的是一个与它
        无关的量。别人的 close leader 失格会推进 room epoch，那时正在飞的普通 forcesave
        由 `write_fence_epoch` 那条负责（撤销 writer 必提升 write fence），不该在这里
        被误杀。
        """
        compared = OH.assert_final_authorization(
            frozen=_frozen(),
            observed=_observed(close_leader_eligibility_epoch=99),
        )
        assert compared[-1] == "close_leader_eligibility_not_applicable"

    @pytest.mark.parametrize(
        "case_id,frozen_override,override,exc_type,code",
        _FENCE_CASES,
        ids=[row[0] for row in _FENCE_CASES],
    )
    def test_each_branch_rejects_independently(
        self,
        case_id: str,
        frozen_override: dict,
        override: dict,
        exc_type: type,
        code: str,
    ) -> None:
        with pytest.raises(exc_type) as exc:
            OH.assert_final_authorization(
                frozen=_frozen(**frozen_override), observed=_observed(**override)
            )
        assert exc.value.error_code == code, (
            f"{case_id}: 期望 error_code={code}，实得 {exc.value.error_code} —— "
            "两条拒绝共用 code 时靠前那条永久不可达"
        )

    def test_closing_initiator_is_still_live(self) -> None:
        """`closing` 必须仍算合法：clean close 的 predecessor forcesave 正是在
        participant 已转 `closing` 之后回调的（AC 4.10）。把它排除会让干净关闭恒失败。"""
        OH.assert_final_authorization(
            frozen=_frozen(),
            observed=_observed(initiator_state=ParticipantState.closing.value),
        )

    def test_every_fence_error_code_is_distinct(self) -> None:
        types = [
            OH.ProjectNotVisibleError,
            OH.WorkflowLockedError,
            OH.GenerationSupersededError,
            OH.WriteFenceAdvancedError,
            OH.InitiatorMissingError,
            OH.InitiatorEpochChangedError,
            OH.InitiatorNotLiveError,
            OH.ContributorSnapshotDriftError,
            OH.ApprovedBundleReplacedError,
            OH.EligibilityEpochAdvancedError,
            OH.CloseCaptureEligibilityUnprovenError,
        ]
        types.append(OH.FrozenInitiatorMissingError)
        codes = [t.error_code for t in types]
        assert len(set(codes)) == len(codes), f"fence error_code 撞车: {codes}"
        assert all(issubclass(t, OH.FinalFenceError) for t in types)
        assert OH.FinalFenceError.error_code not in codes, (
            "具体子类不得复用基类 error_code —— 否则「哪一条在起作用」不可分辨"
        )

    def test_fence_ordering_puts_visibility_before_generation(self) -> None:
        """同时 visibility 撤销 + generation 变化 ⇒ 报 visibility（顺序即诊断）。"""
        with pytest.raises(OH.ProjectNotVisibleError):
            OH.assert_final_authorization(
                frozen=_frozen(),
                observed=_observed(project_visible=False, room_generation=99),
            )

    def test_p43_every_named_revocation_shape_is_covered_by_a_branch(self) -> None:
        """Property 43 逐字点名的**五种**形态，必须一一对应到独立的拒绝分支。

        P43 原文：「打开后撤销授权、改变 visibility/workflow lock、提升 write fence、
        supersede generation 或替换 current approved bundle」。这条守卫是**覆盖率**判据：
        它把 P43 的五个名词与 `_FENCE_CASES` 的分支表对齐，于是「删掉其中一条分支」
        不只让那一条用例红，还让本条红并直接指出**少了哪一种形态** ——
        单看 `_FENCE_CASES` 参数化时，删掉一整行只会让用例数变少，没人会发现。
        """
        shapes = {
            "撤销授权（发起人失活/撤销）": (
                {"initiator_state": ParticipantState.revoked.value},
                OH.InitiatorNotLiveError,
            ),
            "visibility 变化": ({"project_visible": False}, OH.ProjectNotVisibleError),
            "workflow lock 变化": ({"workflow_locked": True}, OH.WorkflowLockedError),
            "提升 write fence": (
                {"room_write_fence_epoch": 6},
                OH.WriteFenceAdvancedError,
            ),
            "supersede generation": ({"room_generation": 4}, OH.GenerationSupersededError),
            "替换 current approved bundle": (
                {"current_definition_bundle_id": uuid.uuid4()},
                OH.ApprovedBundleReplacedError,
            ),
        }
        for name, (override, exc_type) in shapes.items():
            with pytest.raises(exc_type):
                OH.assert_final_authorization(
                    frozen=_frozen(), observed=_observed(**override)
                )
        # 每种形态一个**独立** error_code —— 合并任意两种都会让其中一种不可归因。
        codes = {t.error_code for _, t in shapes.values()}
        assert len(codes) == len(shapes), f"P43 的形态被合并了: {sorted(codes)}"

    def test_p43_fence_runs_at_both_commit_gates(self) -> None:
        """P43 的「即使已 durable/已 rematerialize 也必须在 DB commit 前失败」。

        判据是**两道**回调都调 `assert_final_authorization`：只在 publish 前验一次时，
        publish（可能是几十 MB 的 xlsx IO）到写库之间的撤权就漏了。真库侧由
        `_pg.py::TestFinalAuthorizationFence` 断言两道各自能拦住 commit；这里锁死
        「两道都真的调了那个函数」这一代码事实。
        """
        for method in (
            OH.OoToHtmlCoordinator._fence_before_publish,
            OH.OoToHtmlCoordinator._fence_before_write,
        ):
            src = inspect.getsource(method)
            assert "assert_final_authorization(" in src, (
                f"{method.__name__} 没有调用最终授权判据 —— fence 名存实亡"
            )
            assert "observe_live_authorization(" in src, (
                f"{method.__name__} 没有**现场**观测授权事实 —— 拿冻结值自己跟自己比是重言式"
            )

    def test_frozen_side_null_initiator_has_its_own_error_code(self) -> None:
        """「冻结时就没记下发起人」与「记下了但人不在了」必须可分辨。

        两者共用 error_code 时，删掉 frozen 侧那条检查会被 observed 侧遮蔽 ⇒
        变异检验判 GREEN（M14 首轮实测如此）。语义也确实不同：前者是 system/route
        identity 冒充用户授权（AC 10.10 明令禁止），后者是授权在期间失效。
        """
        with pytest.raises(OH.FrozenInitiatorMissingError) as frozen_side:
            OH.assert_final_authorization(
                frozen=_frozen(frozen_initiator_participant_id=None),
                observed=_observed(initiator_participant_id=None),
            )
        assert frozen_side.value.error_code == "final_fence_frozen_initiator_missing"

        with pytest.raises(OH.InitiatorMissingError) as observed_side:
            OH.assert_final_authorization(
                frozen=_frozen(), observed=_observed(initiator_participant_id=None)
            )
        assert observed_side.value.error_code == "final_fence_initiator_missing"
        assert frozen_side.value.error_code != observed_side.value.error_code


# ═══════════════════════════════════════════════════════════════════════════
# 三b、happy path 上恒不触发的三条判据（抽成纯函数才可证伪）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 这三条在正确实现下**永远不触发**（incoming 没被改、digest 没被偷换、fence 指对了），
# 所以留在 coordinator 方法体里时短路它们在运行期观察不到 ⇒ 变异检验判 GREEN
# （M33/M34/M35 首轮实测如此）。抽成模块级纯函数后每条都能用合成输入逐一喂。
# Task 24 为同一形态把三条 close-leader 判据从方法里抽出来过。


def _incoming_row(**over):
    kwargs = dict(
        artifact_id=INCOMING,
        observed_kind=ArtifactKind.incoming.value,
        observed_state=ArtifactState.durable.value,
        observed_published_at=None,
        observed_relative_path=".incoming/wp/delivery/callback-abc.xlsx",
        observed_sha256=_d("incoming-bytes"),
        expected_relative_path=".incoming/wp/delivery/callback-abc.xlsx",
        expected_sha256=_d("incoming-bytes"),
    )
    kwargs.update(over)
    return kwargs


class TestIncomingRowUnchanged:
    def test_untouched_row_passes(self) -> None:
        OH.assert_incoming_row_unchanged(**_incoming_row())

    @pytest.mark.parametrize(
        "override,fragment",
        [
            ({"observed_kind": ArtifactKind.canonical.value}, "kind"),
            ({"observed_state": ArtifactState.published.value}, "state"),
            ({"observed_published_at": _now()}, "published_at"),
            ({"observed_relative_path": ".versions/wp/x.xlsx"}, "relative_path"),
            ({"observed_sha256": _d("tampered")}, "sha256"),
        ],
        ids=["promoted_kind", "promoted_state", "published_at_set", "moved", "rewritten"],
    )
    def test_every_drift_shape_is_detected(self, override: dict, fragment: str) -> None:
        with pytest.raises(OH.IncomingMutatedError) as exc:
            OH.assert_incoming_row_unchanged(**_incoming_row(**override))
        assert fragment in str(exc.value)
        assert exc.value.error_code == "incoming_artifact_mutated"


class TestPublishedDigestWasApproved:
    def test_matching_digest_passes(self) -> None:
        OH.assert_published_digest_was_approved(
            approved_sha256=_d("result"), published_sha256=_d("result")
        )

    def test_swapped_digest_is_detected(self) -> None:
        with pytest.raises(OH.ResultArtifactDigestError) as exc:
            OH.assert_published_digest_was_approved(
                approved_sha256=_d("result"), published_sha256=_d("other")
            )
        assert exc.value.error_code == "result_artifact_digest_mismatch"

    def test_missing_approval_is_an_order_violation_not_a_digest_mismatch(self) -> None:
        """「fence 根本没跑」与「digest 被偷换」必须分型。

        共用类型时，删掉 `approved is None` 分支会被 digest 分支遮蔽（`None.strip()`
        会抛 AttributeError，那是第三种、不可诊断的失败）。
        """
        with pytest.raises(OH.ApplyStageOrderError) as exc:
            OH.assert_published_digest_was_approved(
                approved_sha256=None, published_sha256=_d("result")
            )
        assert exc.value.error_code == "apply_stage_order_violation"


class TestCanonicalFencePointsAt:
    def test_synchronized_fence_passes(self) -> None:
        OH.assert_canonical_fence_points_at(
            advanced_application_id=APP, expected_application_id=APP
        )

    @pytest.mark.parametrize(
        "advanced", [None, uuid.uuid4()], ids=["fence_never_advanced", "fence_points_elsewhere"]
    )
    def test_desynchronized_fence_is_detected(self, advanced) -> None:
        with pytest.raises(OH.ResultBundleIdentityError) as exc:
            OH.assert_canonical_fence_points_at(
                advanced_application_id=advanced, expected_application_id=APP
            )
        assert exc.value.error_code == "result_bundle_identity_mismatch"


# ═══════════════════════════════════════════════════════════════════════════
# 四、结构判据（AST）
# ═══════════════════════════════════════════════════════════════════════════


class TestStructuralPredicates:
    def test_substrate_resolution_reads_only_the_application_fk(self) -> None:
        assert OH.assert_substrate_resolution_source_shape() == (
            "assert_incoming_durable",
        ), (
            "`open_substrate` 只允许调 `repo.assert_incoming_durable`；多一个仓储调用"
            "就是多读一张业务表，而那种写法不会出现被禁属性名"
        )

    def test_forbidden_attribute_list_covers_all_four_named_guessing_paths(self) -> None:
        """AC 4.3/8.10 点名的四条路径都要在禁用清单里有对应符号。"""
        forbidden = set(OH._SUBSTRATE_FORBIDDEN_ATTRS)
        assert {"last_applied_version_id", "latest_durable_application_id"} & forbidden
        assert {"resolve_alias", "current_alias"} & forbidden
        assert {"staged_artifact_id", "candidate_id"} & forbidden
        assert {"duplicate_of_operation_id"} & forbidden

    def test_fence_callbacks_assert_trace_order_as_their_first_statement(self) -> None:
        """两个 fence 回调的**第一条语句**必须是对应的轨迹前置断言。

        为什么是形态判据：`assert_publish_precondition()` 在正确实现下恒不触发
        （happy path 的轨迹永远齐全），把那一行删掉在运行期观察不到 ⇒ 变异检验判 GREEN
        （M30 首轮实测如此）。它保护的是「publish 前必须先证明三方 extract 与 merge 真的
        发生过」这条**顺序**，因此判据只能落在代码形态上。
        """
        assert OH.assert_fence_callbacks_assert_order_first() == (
            ("_fence_before_publish", "assert_publish_precondition"),
            ("_fence_before_write", "assert_write_precondition"),
        )

    def test_module_never_references_command_service(self) -> None:
        modules = OH.assert_no_command_service_reference()
        assert not any("command_service" in m for m in modules)

    def test_command_service_symbol_list_is_matched_as_whole_identifier(self) -> None:
        """判据必须是**完整标识符**相等，不是子串包含。

        本模块自身就有 `next_forcesave_allowed` 与
        `assert_no_command_service_reference` 两个**包含**被禁子串的合法标识符。
        子串匹配会让这条判据恒红 —— 恒红的守卫和恒绿一样没用。

        🔴 结论必须**经由生产判据**得出。上一版在测试里自己算一遍
        `set(_COMMAND_SERVICE_SYMBOLS) & identifiers`，等于测试自带第二套实现：
        把生产判据换成子串包含时本条照常绿（变异 R05 实测 —— 红的是隔壁
        `test_module_never_references_command_service`，本条纹丝不动），
        于是「本条锁死完整标识符口径」这句话在当时并不成立。
        """
        identifiers = OH._collect_identifiers(ast.parse(inspect.getsource(OH)))
        assert "next_forcesave_allowed" in identifiers
        assert "assert_no_command_service_reference" in identifiers

        # 前提：确实存在「子串命中、整标识符不命中」的合法标识符 —— 两种口径才可区分。
        # 前提失效时本条就不再有判别力，必须显式失败而不是静默变成重言式。
        substring_only = sorted(
            sym
            for sym in OH._COMMAND_SERVICE_SYMBOLS
            if sym not in identifiers and any(sym in name for name in identifiers)
        )
        assert substring_only == ["command_service", "forcesave"], (
            f"前提漂移：当前「仅子串命中」的符号是 {substring_only}，"
            "本条据此才能区分完整标识符/子串两种口径"
        )
        # 结论由生产函数给出：整标识符口径下它必须不抛并返回 import 清单。
        assert OH.assert_no_command_service_reference()
        assert not (set(OH._COMMAND_SERVICE_SYMBOLS) & identifiers)

    def test_collect_identifiers_ignores_string_literals(self) -> None:
        """反向自检：字符串字面量里的符号不得被当成引用。"""
        tree = ast.parse('x = "forcesave"\ndef f(): return "CommandService"\n')
        names = OH._collect_identifiers(tree)
        assert "forcesave" not in names and "CommandService" not in names
        assert {"x", "f"} <= names

    def test_repo_calls_in_detects_both_self_repo_and_bare_repo(self) -> None:
        """反向自检：两种常见写法都要被 `_repo_calls_in` 看到。"""
        tree = ast.parse(
            "async def f(self, repo):\n"
            "    await self._repo.alpha()\n"
            "    await repo.beta()\n"
            "    await other.gamma()\n"
        )
        assert OH._repo_calls_in(tree) == {"alpha", "beta"}


# ═══════════════════════════════════════════════════════════════════════════
# 五、执行轨迹：顺序是判据（AC 8.10 / 8.11）
# ═══════════════════════════════════════════════════════════════════════════


def _journal_upto(*stages: OH.ApplyStage) -> OH.ApplyJournal:
    j = OH.ApplyJournal()
    for stage in stages:
        j.record(stage)
    return j


_MERGE_DONE = (
    OH.ApplyStage.substrate_opened,
    OH.ApplyStage.base_extracted,
    OH.ApplyStage.current_extracted,
    OH.ApplyStage.incoming_extracted,
    OH.ApplyStage.merged,
)


class TestApplyJournal:
    def test_extract_requires_substrate_opened_first(self) -> None:
        with pytest.raises(OH.ApplyStageOrderError):
            _journal_upto().assert_extract_precondition()
        _journal_upto(OH.ApplyStage.substrate_opened).assert_extract_precondition()

    @pytest.mark.parametrize(
        "missing",
        list(_MERGE_DONE),
        ids=[s.value for s in _MERGE_DONE],
    )
    def test_publish_requires_every_earlier_stage(self, missing) -> None:
        """publish 的前置阶段逐条必需。

        合成成「只查 merged」时，删掉三次 extract 中的任意一次都不会变红 —— 而那正是
        「只 extract 了 incoming 就直接发布」这条真实缺陷（base/current 没读 ⇒
        三方 merge 退化成整表覆盖）。
        """
        stages = tuple(s for s in _MERGE_DONE if s is not missing)
        with pytest.raises(OH.ApplyStageOrderError) as exc:
            _journal_upto(*stages).assert_publish_precondition()
        assert missing.value in str(exc.value)

    def test_publish_precondition_passes_after_full_merge(self) -> None:
        _journal_upto(*_MERGE_DONE).assert_publish_precondition()

    def test_publish_fence_cannot_run_twice(self) -> None:
        j = _journal_upto(*_MERGE_DONE, OH.ApplyStage.fence_verified_before_publish)
        with pytest.raises(OH.ApplyStageOrderError):
            j.assert_publish_precondition()

    def test_write_fence_must_come_after_publish_fence(self) -> None:
        with pytest.raises(OH.ApplyStageOrderError):
            _journal_upto(*_MERGE_DONE).assert_write_precondition()
        _journal_upto(
            *_MERGE_DONE, OH.ApplyStage.fence_verified_before_publish
        ).assert_write_precondition()

    def test_write_fence_cannot_run_twice(self) -> None:
        j = _journal_upto(
            *_MERGE_DONE,
            OH.ApplyStage.fence_verified_before_publish,
            OH.ApplyStage.fence_verified_before_write,
        )
        with pytest.raises(OH.ApplyStageOrderError):
            j.assert_write_precondition()

    def test_conflict_forbids_any_later_publish_or_commit(self) -> None:
        j = _journal_upto(*_MERGE_DONE, OH.ApplyStage.conflict_recorded)
        j.assert_no_publish_after_conflict()
        j.record(OH.ApplyStage.business_committed)
        with pytest.raises(OH.ApplyStageOrderError):
            j.assert_no_publish_after_conflict()

    def test_no_conflict_journal_is_unaffected_by_conflict_assertion(self) -> None:
        _journal_upto(
            *_MERGE_DONE,
            OH.ApplyStage.fence_verified_before_publish,
            OH.ApplyStage.business_committed,
        ).assert_no_publish_after_conflict()


# ═══════════════════════════════════════════════════════════════════════════
# 六、双基线裁决口径唯一（Property 62 / AC 2.9 / 4.11）
# ═══════════════════════════════════════════════════════════════════════════

import json  # noqa: E402
import zipfile  # noqa: E402
from decimal import Decimal  # noqa: E402
from pathlib import Path  # noqa: E402

from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync.adapters.base import (  # noqa: E402
    FieldValue,
    MaterializeResult,
    Projection,
    UnmanagedRegionReport,
)
from app.services.workpaper_sync.content_mutation import (  # noqa: E402
    projection_canonical_digest,
)
from app.services.workpaper_sync import conflicts as CF  # noqa: E402
from app.services.workpaper_sync import merge as M  # noqa: E402
from app.services.workpaper_sync.merge import merge_projections  # noqa: E402

PERIOD = "header_block/period_label"
TOTAL = "header_block/total_amount"
NOTE = "header_block/word_note"
ROWS = "ar_rows/{row_uuid}/amount"

_CONTENT_TYPES = (
    b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/'
    b'2006/content-types"><Default Extension="xml" ContentType="application/xml"/>'
    b'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats'
    b'-officedocument.spreadsheetml.sheet.main+xml"/></Types>'
)


def _docx_payload() -> dict:
    """带 `word_only` 字段的 docx 契约。

    `word_only` 只允许出现在 docx 契约里（契约门 CS-19），而 `settlement_digest_pair`
    存在的理由正是 Word 底稿上「受管等值但整份 digest 不等」这一类输入 —— 所以这个
    fixture 必须是 docx，不能给 xlsx 契约硬塞一个 word_only 字段。
    """
    cid = "f2.stocktake.plan"
    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": cid,
        "semantic_version": "1.0.0-sdt1",
        "review_status": "reviewed",
        "document_type": "docx",
        "template_definition_sha256": _d("task26-docx-template"),
        "instrumentation_definition_sha256": _d("task26-docx-instrumentation"),
        "template": {
            "relative_path": "F/F2 存货监盘计划.docx",
            "template_sha256": _d("task26-docx-blob"),
            "normalized_structure_hash": _d("task26-docx-structure"),
        },
        "identity_carriers": ["field_sdt_inline"],
        "fields": [
            {
                "stable_field_key": "plan/location",
                "json_pointer": "/plan/location",
                "sdt_tag": f"gt:field:{cid}:plan/location",
                "mode": "editable",
                "value_type": "text",
                "source_ref": "源docx!监盘地点",
                "instances": "many",
            },
            {
                "stable_field_key": "plan/total_amount",
                "json_pointer": "/plan/totalAmount",
                "sdt_tag": f"gt:field:{cid}:plan/total_amount",
                "mode": "editable",
                "value_type": "amount",
                "source_ref": "源docx!合计",
            },
            {
                "stable_field_key": "plan/free_notes",
                "json_pointer": "/plan/freeNotes",
                "sdt_tag": f"gt:field:{cid}:plan/free_notes",
                "mode": "word_only",
                "value_type": "text",
                "source_ref": "源docx!补充说明",
            },
        ],
    }


def _contract_payload() -> dict:
    fields = [
        {
            "stable_field_key": PERIOD,
            "json_pointer": "/header/periodLabel",
            "column_key": "period_label",
            "cell": {"column": "B", "row_from": 2},
            "mode": "editable",
            "value_type": "text",
            "source_ref": "源xlsx!B2",
        },
        {
            "stable_field_key": TOTAL,
            "json_pointer": "/header/totalAmount",
            "column_key": "total_amount",
            "cell": {"column": "C", "row_from": 3},
            "mode": "editable",
            "value_type": "amount",
            "source_ref": "源xlsx!C3",
        },
    ]
    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": ENTRY,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": _d("task26-template"),
        "instrumentation_definition_sha256": _d("task26-instrumentation"),
        "template": {
            "relative_path": "D/D2 应收账款.xlsx",
            "template_sha256": _d("task26-template-blob"),
            "normalized_structure_hash": _d("task26-template-structure"),
        },
        "identity_carriers": ["hidden_sheet", "defined_name"],
        "sheets": [
            {
                "sheet_key": "d2-detail",
                "excel_name": "D2 明细",
                "locator": {"anchor": "defined_name_ref"},
                "tables": [
                    {"table_key": "header_block", "anchor": "A1", "header_rows": 1, "fields": fields},
                    {
                        "table_key": "ar_rows",
                        "anchor": "A10",
                        "header_rows": 1,
                        "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
                        "delete_policy": "tombstone",
                        "fields": [
                            {
                                "stable_field_key": ROWS,
                                "json_pointer": "/rows/{row_uuid}/amount",
                                "column_key": "amount",
                                "cell": {"column": "C", "row_from": "row_identity"},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "源xlsx!C11",
                            }
                        ],
                    },
                ],
            }
        ],
    }


@pytest.fixture(scope="module")
def contract() -> C.SyncContract:
    return C.parse_contract(_contract_payload())


@pytest.fixture(scope="module")
def docx_contract() -> C.SyncContract:
    return C.parse_contract(_docx_payload())


def _proj(contract: C.SyncContract, values: dict) -> Projection:
    specs = {spec.stable_field_key: spec for spec in contract.all_fields()}
    out: dict[str, FieldValue] = {}
    row_keys: dict[str, list[str]] = {}
    for key, value in values.items():
        if "/" in key and key.count("/") == 2 and key.startswith("ar_rows/"):
            _table, row_uuid, _leaf = key.split("/")
            spec = specs[ROWS]
            out[key] = FieldValue(
                stable_key=key,
                value=value,
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=row_uuid,
            )
            row_keys.setdefault("ar_rows", []).append(row_uuid)
            continue
        spec = specs[key]
        out[key] = FieldValue(
            stable_key=key, value=value, value_type=spec.value_type, mode=spec.mode
        )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=out,
        row_keys={k: tuple(v) for k, v in row_keys.items()},
    )


class TestSettlementDigestPair:
    """`settlement_digest_pair` 必须**如实**翻译 Task 14 的 managed 等值裁决。"""

    def test_managed_equal_reports_equality_to_room_service(
        self, docx_contract: C.SyncContract
    ) -> None:
        """word_only 字段不同、受管字段全等 ⇒ 裁决「等值」，两侧 digest 必须相同。

        这是本函数存在的全部理由：整份 projection 的 digest 在这种输入下**不相等**
        （word_only 键进 payload），直接把两个 digest 丢给
        `settle_client_baseline` 会得到「Task 15 没标 refresh、Task 21 标了」的半状态。
        """
        loc, total, note = "plan/location", "plan/total_amount", "plan/free_notes"
        base = _proj(docx_contract, {loc: "北京仓", total: Decimal("100")})
        current = _proj(docx_contract, {loc: "北京仓", total: Decimal("100")})
        incoming = _proj(
            docx_contract,
            {loc: "北京仓", total: Decimal("100"), note: "OO 里写的自由正文"},
        )
        outcome = merge_projections(
            base=base, current=current, incoming=incoming, contract=docx_contract
        )
        merged_digest = projection_canonical_digest(outcome.merged)
        incoming_digest = projection_canonical_digest(incoming)
        assert merged_digest != incoming_digest, (
            "前置假设：整份 digest 在 word_only 差异下不相等 —— 否则本测试证明不了什么"
        )
        assert outcome.requires_client_refresh(incoming) is False
        left, right = OH.settlement_digest_pair(
            merge=outcome,
            incoming=incoming,
            merged_digest=merged_digest,
            incoming_digest=incoming_digest,
        )
        assert left == right == merged_digest

    def test_managed_difference_reports_inequality(self, contract: C.SyncContract) -> None:
        base = _proj(contract, {PERIOD: "2025", TOTAL: Decimal("100")})
        current = _proj(contract, {PERIOD: "2025", TOTAL: Decimal("250")})
        incoming = _proj(contract, {PERIOD: "2025", TOTAL: Decimal("100")})
        outcome = merge_projections(
            base=base, current=current, incoming=incoming, contract=contract
        )
        merged_digest = projection_canonical_digest(outcome.merged)
        incoming_digest = projection_canonical_digest(incoming)
        assert outcome.requires_client_refresh(incoming) is True
        left, right = OH.settlement_digest_pair(
            merge=outcome,
            incoming=incoming,
            merged_digest=merged_digest,
            incoming_digest=incoming_digest,
        )
        assert left == merged_digest and right == incoming_digest and left != right

    def test_translation_preserves_the_verdict_in_both_directions(
        self, contract: C.SyncContract
    ) -> None:
        """裁决 ⇔ digest 对是否相等 —— 双向一致（这就是「口径唯一」的形式化表述）。"""
        cases = [
            ({TOTAL: Decimal("100")}, {TOTAL: Decimal("100")}, {TOTAL: Decimal("100")}),
            ({TOTAL: Decimal("100")}, {TOTAL: Decimal("100")}, {TOTAL: Decimal("300")}),
            ({TOTAL: Decimal("100")}, {TOTAL: Decimal("250")}, {TOTAL: Decimal("100")}),
        ]
        for b, c, i in cases:
            base = _proj(contract, {PERIOD: "2025", **b})
            current = _proj(contract, {PERIOD: "2025", **c})
            incoming = _proj(contract, {PERIOD: "2025", **i})
            outcome = merge_projections(
                base=base, current=current, incoming=incoming, contract=contract
            )
            md = projection_canonical_digest(outcome.merged)
            idg = projection_canonical_digest(incoming)
            left, right = OH.settlement_digest_pair(
                merge=outcome, incoming=incoming, merged_digest=md, incoming_digest=idg
            )
            verdict_refresh = outcome.requires_client_refresh(incoming)
            assert verdict_refresh == (left != right), (
                f"裁决={verdict_refresh} 与 digest 对是否相等不一致（{b}/{c}/{i}）"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 七、三方 merge 经 coordinator 口径（P25 / P26 / P27）
# ═══════════════════════════════════════════════════════════════════════════


class TestThreeWayMergeSemantics:
    """P25/P26/P27 在 coordinator **消费口径**上的判据。

    Task 14 已单独证明 `merge_projections` 的真值表；这里断言的是 coordinator 实际
    依赖的那三条结论 —— 因为决定「提交还是登记冲突」的正是它们。
    """

    def test_p25_different_fields_auto_merge_with_zero_conflicts(
        self, contract: C.SyncContract
    ) -> None:
        base = _proj(contract, {PERIOD: "2024", TOTAL: Decimal("100")})
        current = _proj(contract, {PERIOD: "2025 已审", TOTAL: Decimal("100")})
        incoming = _proj(contract, {PERIOD: "2024", TOTAL: Decimal("888")})
        outcome = merge_projections(
            base=base, current=current, incoming=incoming, contract=contract
        )
        assert outcome.conflict_count == 0
        assert outcome.merged.get(PERIOD).value == "2025 已审"
        assert outcome.merged.get(TOTAL).value == Decimal("888")
        # coordinator 的分支判据：无冲突 ⇒ 走提交路径
        assert not outcome.has_conflicts

    def test_p26_same_field_three_values_conflicts_and_keeps_all_three(
        self, contract: C.SyncContract
    ) -> None:
        base = _proj(contract, {PERIOD: "A", TOTAL: Decimal("1")})
        current = _proj(contract, {PERIOD: "B", TOTAL: Decimal("1")})
        incoming = _proj(contract, {PERIOD: "C", TOTAL: Decimal("1")})
        outcome = merge_projections(
            base=base, current=current, incoming=incoming, contract=contract
        )
        assert outcome.conflict_count == 1
        record = outcome.conflicts.records[0]
        assert (record.base.value, record.current.value, record.incoming.value) == (
            "A",
            "B",
            "C",
        )
        # 未裁决时 merged 只是「hold 在 current」的快照，绝不能被当成可提交内容
        assert outcome.merged.get(PERIOD).value == "B"
        assert outcome.has_conflicts

    def test_p27_delete_vs_update_conflicts_only_that_row(
        self, contract: C.SyncContract
    ) -> None:
        r1, r2 = str(uuid.uuid4()), str(uuid.uuid4())
        base = _proj(
            contract,
            {
                PERIOD: "2025",
                TOTAL: Decimal("0"),
                f"ar_rows/{r1}/amount": Decimal("10"),
                f"ar_rows/{r2}/amount": Decimal("20"),
            },
        )
        # current 删掉 r1；incoming 改了 r1 并同时改了 r2
        current = _proj(
            contract,
            {PERIOD: "2025", TOTAL: Decimal("0"), f"ar_rows/{r2}/amount": Decimal("20")},
        )
        incoming = _proj(
            contract,
            {
                PERIOD: "2025",
                TOTAL: Decimal("0"),
                f"ar_rows/{r1}/amount": Decimal("11"),
                f"ar_rows/{r2}/amount": Decimal("22"),
            },
        )
        outcome = merge_projections(
            base=base, current=current, incoming=incoming, contract=contract
        )
        conflicted_rows = {rec.locator.row_key for rec in outcome.conflicts.records}
        assert conflicted_rows == {r1}, f"只应 r1 冲突，实得 {conflicted_rows}"
        assert outcome.merged.get(f"ar_rows/{r2}/amount").value == Decimal("22"), (
            "其他行必须照常合并 —— 位置变化不得被误判为整表覆盖（AC 6.9）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 七之二、人工裁决必须 fail closed（2026-08-27 审计发现的静默错值路径）
# ═══════════════════════════════════════════════════════════════════════════


def _imported_and_called(module: object) -> tuple[set[str], set[str]]:
    """模块源码的 AST 里 **import 到的名字** 与 **被调用的名字**。

    🔴 判据必须走 AST 而不是子串：本模块的 docstring 逐处解释接线来历时逐字写着
    `apply_resolutions`，子串匹配会把解释文字当成接线（Task 26 首轮实测假红），
    而「改名残留」又会骗过子串判据的反方向。
    """
    tree = ast.parse(inspect.getsource(module))
    imported: set[str] = set()
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(a.asname or a.name for a in node.names)
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                called.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                called.add(fn.attr)
    return imported, called


class TestManualAdjudicationIsWired:
    """带裁决的调用必须发布**折叠结果**，不得「校验覆盖率后仍发布 `merge.merged`」。

    ═══ 这条守卫在防什么 ═══

    Task 26 交付时 `apply_durable_incoming(resolutions=[...])` 会走无冲突分支，而那条
    分支用的是 `merge.merged` —— 它对每个冲突字段保留 **current 侧**的值。链路上四道关
    都不会拦：

    1. `merge.apply_resolutions` 在 coordinator 里**从未被 import**；
    2. Task 15 的 `_settle_projection` 只校验裁决**覆盖**了每条冲突，覆盖通过后返回的
       仍是那份未收敛的 projection；
    3. rematerialize/extract 等值比的是「result 与 merged 一致」——两边都是错值，必等；
    4. 最终 fence 比的是授权与身份，与字段值无关。

    结果就是「审计师点了取 incoming，落库的是 current」，且 refresh 裁决
    （`requires_client_refresh` 也读 `self.merged`）跟着一起错。

    ═══ Task 27 把判据**翻转**（不是删掉）═══

    Task 26 的形态是「零接线 + fail-closed 闸门 + `deferred` 登记」。Task 27 接线后
    变成「恰一处接线 + 无闸门 + `retired` 登记」，两个方向仍然双向锁死：

    * 登记 `retired` 却搜不到 `apply_resolutions` 的 import/调用 ⇒ 红；
    * 闸门函数偷偷回来（有人把接线回退成 fail closed）⇒ 红。
    """

    def _conflicted(self, contract: C.SyncContract) -> M.MergeOutcome:
        return merge_projections(
            base=_proj(contract, {PERIOD: "A", TOTAL: Decimal("1")}),
            current=_proj(contract, {PERIOD: "B", TOTAL: Decimal("1")}),
            incoming=_proj(contract, {PERIOD: "C", TOTAL: Decimal("1")}),
            contract=contract,
        )

    @staticmethod
    def _choice(outcome: M.MergeOutcome) -> CF.ResolutionChoice:
        record = outcome.conflicts.records[0]
        return CF.ResolutionChoice(
            stable_field_key=record.locator.stable_field_key,
            row_key=record.locator.row_key,
            oo_location=record.locator.oo_location,
            kind=CF.ResolutionKind.take_incoming,
        )

    def test_zero_conflict_zero_adjudication_settles_to_merged(
        self, contract: C.SyncContract
    ) -> None:
        """普通 OO→HTML happy path：零冲突零裁决 ⇒ 就是 `merge.merged`。"""
        same = _proj(contract, {PERIOD: "A", TOTAL: Decimal("1")})
        outcome = merge_projections(
            base=same, current=same, incoming=same, contract=contract
        )
        assert not outcome.has_conflicts
        settled = OH.settle_adjudicated_projection(
            merge=outcome, resolutions=(), contract=contract
        )
        assert settled is outcome.merged

    def test_adjudication_is_folded_not_discarded(
        self, contract: C.SyncContract
    ) -> None:
        """🔴 核心判据：折叠结果必须取 incoming，且与 `merge.merged` **不同**。"""
        outcome = self._conflicted(contract)
        choice = self._choice(outcome)
        settled = OH.settle_adjudicated_projection(
            merge=outcome, resolutions=[choice], contract=contract
        )
        assert outcome.merged.get(PERIOD).value == "B", "merged 保持 current 侧（Task 14 语义）"
        assert settled.get(PERIOD).value == "C", "裁决落地后才是 incoming 侧"
        assert projection_canonical_digest(settled) == projection_canonical_digest(
            M.apply_resolutions(outcome, [choice], contract=contract)
        ), "折叠必须等于 `apply_resolutions` 的结果，不能是另一套自研收敛"
        assert projection_canonical_digest(settled) != projection_canonical_digest(
            outcome.merged
        ), "两份 projection 必须真的不同 —— 否则本守卫拦住的是一个无害路径"

    def test_unresolved_conflict_never_settles(self, contract: C.SyncContract) -> None:
        """有冲突却零裁决 ⇒ 抛，绝不回落到 `merge.merged`（那就是自动选 current）。"""
        outcome = self._conflicted(contract)
        with pytest.raises(CF.UnresolvedConflictError):
            OH.settle_adjudicated_projection(
                merge=outcome, resolutions=(), contract=contract
            )

    def test_adjudication_without_conflict_is_refused(
        self, contract: C.SyncContract
    ) -> None:
        """零冲突却带裁决 ⇒ 客户端的 conflict set 已 stale，静默忽略等于假成功。"""
        same = _proj(contract, {PERIOD: "A", TOTAL: Decimal("1")})
        zero = merge_projections(
            base=same, current=same, incoming=same, contract=contract
        )
        conflicted = self._conflicted(contract)
        with pytest.raises(OH.AdjudicationWithoutConflictError) as exc:
            OH.settle_adjudicated_projection(
                merge=zero,
                resolutions=[self._choice(conflicted)],
                contract=contract,
            )
        assert exc.value.error_code == "adjudication_without_conflict"

    def test_adjudication_without_contract_is_refused(
        self, contract: C.SyncContract
    ) -> None:
        """缺 contract ⇒ 无法按行身份/保护策略折叠，只能 fail closed。"""
        outcome = self._conflicted(contract)
        with pytest.raises(OH.AdjudicationContractRequiredError) as exc:
            OH.settle_adjudicated_projection(
                merge=outcome, resolutions=[self._choice(outcome)], contract=None
            )
        assert exc.value.error_code == "adjudication_requires_contract"

    def test_the_four_branches_use_four_distinguishable_types(self) -> None:
        """四条分支的异常类型两两不遮蔽，且 error_code 在模块内唯一。"""
        codes = [
            cls.error_code
            for name in OH.__all__
            if isinstance(cls := getattr(OH, name), type)
            and issubclass(cls, OH.OoToHtmlError)
        ]
        for code in ("adjudication_without_conflict", "adjudication_requires_contract"):
            assert codes.count(code) == 1, (
                f"error_code {code!r} 被共用 ⇒ 靠前的分支永久不可达；实得 {sorted(codes)}"
            )
        assert not issubclass(
            OH.AdjudicationWithoutConflictError, OH.AdjudicationContractRequiredError
        ) and not issubclass(
            OH.AdjudicationContractRequiredError, OH.AdjudicationWithoutConflictError
        )
        # 未裁决走冲突域的既有类型（不在本模块另造一个同义类）。
        assert not issubclass(CF.UnresolvedConflictError, OH.OoToHtmlError)

    def test_coordinator_really_imports_and_calls_apply_resolutions(self) -> None:
        """结构判据 + 登记表**双向锁死**（Task 26 的 deferred 版在这里翻转成 retired）。

        * 登记为 `retired` ⇒ 模块里必须**真的**出现 `apply_resolutions` 的 import 与调用
          （登记说还了、其实没接 ⇒ 红）；
        * 反过来，接线消失却仍登记 retired ⇒ 同样打红。
        """
        # 🔴 判据走 AST 而不是子串：docstring 里逐处解释接线来历时逐字写着这个符号名，
        # 子串匹配会把解释文字当成接线（Task 26 首轮实测即如此），而这正是
        # 「grep 式守卫」的典型缺陷 —— 它既可能假红，也可能被改名残留骗过。
        imported, called = _imported_and_called(OH)
        assert "apply_resolutions" in imported, (
            f"`apply_resolutions` 未被 import —— 登记声明已接线；"
            f"imported={sorted(n for n in imported if 'resol' in n)}"
        )
        assert "apply_resolutions" in called, (
            f"`apply_resolutions` 只 import 未调用 = 死符号；"
            f"called={sorted(n for n in called if 'resol' in n)}"
        )
        assert OH.RETIRED_ADJUDICATION_CONSUMER["intended_status"] == "retired", (
            "接线已在、登记仍写 deferred —— 两张表必须一致"
        )

    def test_the_fail_closed_gate_did_not_come_back(self) -> None:
        """回退判据：Task 26 的 fail-closed 闸门必须已撤除且不得重现。

        登记里保留了闸门函数名（`retired_fail_closed_gate`），所以「有人把接线改回
        fail closed」这件事有一个机器可核对的锚点 —— 不是靠人记得。
        """
        gate = str(OH.RETIRED_ADJUDICATION_CONSUMER["retired_fail_closed_gate"])
        assert gate, "退役登记必须写明被撤除的闸门函数名"
        assert not hasattr(OH, gate), (
            f"fail-closed 闸门 {gate} 又回来了 —— 裁决被重新拒绝意味着 resolve 端点整条失效"
        )
        assert gate not in OH.__all__

    def test_retirement_registration_is_complete(self) -> None:
        """退役登记必须写明能力/状态/任务/消费方/模块/落库路径/原因，且目标真存在。"""
        entry = OH.RETIRED_ADJUDICATION_CONSUMER
        for field in (
            "capability",
            "intended_status",
            "retired_by_task",
            "consumer",
            "expected_consumer_module",
            "commits_through",
            "retired_fail_closed_gate",
            "wired_by",
            "reason",
        ):
            assert str(entry.get(field, "")).strip(), f"退役登记缺 {field}"
        assert entry["retired_by_task"] == "27"
        assert entry["expected_consumer_module"] == (
            "app/services/workpaper_sync/oo_to_html.py"
        )
        assert entry["commits_through"] == (
            "app/services/workpaper_sync/content_mutation.py"
        )
        # 登记的接线符号必须真的被本模块 import + 调用。
        imported, called = _imported_and_called(OH)
        assert str(entry["wired_by"]) in (imported & called), (
            f"登记的接线符号 {entry['wired_by']!r} 在模块里查不到真实接线"
        )
        assert len(str(entry["reason"])) >= 40

    def test_settle_branches_are_the_single_decision_point(self) -> None:
        """「要发布哪份 projection」只能有一个决策点，且发布分支不得再读 `merge.merged`。

        判据是形态而不是行为：`_apply_settled` 里出现 `merge.merged` 就意味着有人在折叠
        之外又插了一条「直接取未收敛快照」的路 —— 那正是被修掉的那个缺陷。
        """
        src = textwrap.dedent(
            inspect.getsource(OH.OoToHtmlCoordinator._apply_settled)
        )
        fn = ast.parse(src).body[0]
        assert isinstance(fn, ast.AsyncFunctionDef)
        merged_reads = [
            node.lineno
            for node in ast.walk(fn)
            if isinstance(node, ast.Attribute)
            and node.attr == "merged"
            and isinstance(node.value, ast.Name)
            and node.value.id == "merge"
        ]
        assert merged_reads == [], (
            f"发布分支直接读了 `merge.merged`（行 {merged_reads}）—— "
            "唯一决策点必须是 `settle_adjudicated_projection`"
        )
        settle_calls = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "settle_adjudicated_projection"
        ]
        assert len(settle_calls) == 1, (
            f"`settle_adjudicated_projection` 在发布分支里应恰好调用一次，"
            f"实得 {len(settle_calls)}"
        )

    def test_resolutions_reach_the_commit_boundary(self) -> None:
        """裁决必须随 `BusinessMutation` 交到唯一 commit 边界做**独立重算**。

        Task 15 的 `_settle_projection` 会重算 `apply_resolutions` 并逐字节比对；漏传
        `resolution_choices` 时那道第二把锁直接失效（它只在 `resolution_choices` 非空时
        才校验折叠），而行为测试仍全绿 —— 所以判据必须落在这个关键字实参上。
        """
        src = textwrap.dedent(
            inspect.getsource(OH.OoToHtmlCoordinator._apply_settled)
        )
        fn = ast.parse(src).body[0]
        calls = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "BusinessMutation"
        ]
        assert len(calls) == 1, "发布分支应恰好构造一次 BusinessMutation"
        keywords = {kw.arg for kw in calls[0].keywords}
        assert "resolution_choices" in keywords, (
            "`resolution_choices` 没有交给 BusinessMutation ⇒ Task 15 的独立重算恒不触发"
        )

    def test_entry_dispatch_routes_adjudication_away_from_conflict_branch(self) -> None:
        """分派必须读 `state.resolutions`：否则带裁决的调用会被登记成冲突并冻结指针。

        与「发布分支不得读 `merge.merged`」是两条互补判据：前者管「走哪条路」，
        后者管「路上发布什么」。少任何一条都能让静默错值以另一种形态复活。
        """
        src = textwrap.dedent(
            inspect.getsource(OH.OoToHtmlCoordinator.apply_durable_incoming)
        )
        fn = ast.parse(src).body[0]
        assert isinstance(fn, ast.AsyncFunctionDef)
        conflict_ifs = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.If)
            and any(
                isinstance(inner, ast.Attribute)
                and inner.attr == "has_conflicts"
                for inner in ast.walk(node.test)
            )
        ]
        assert conflict_ifs, "找不到 `has_conflicts` 分派 —— 判据失去锚点"
        reads_resolutions = any(
            isinstance(inner, ast.Attribute) and inner.attr == "resolutions"
            for node in conflict_ifs
            for inner in ast.walk(node.test)
        )
        assert reads_resolutions, (
            "冲突分派没有读 `state.resolutions` ⇒ 带裁决的调用会走 `_record_conflict`，"
            "审计师提交的裁决被登记成「仍有冲突」并冻结指针（AC 8.3 失效）"
        )

    def test_entry_still_exposes_the_seam(self) -> None:
        """公开入口的 `resolutions` 形参与默认值不得变 —— Task 27/28 按它调用。"""
        params = inspect.signature(OH.OoToHtmlCoordinator.apply_durable_incoming).parameters
        assert "resolutions" in params
        assert params["resolutions"].default == ()

    def test_conflict_resolution_source_bucket_is_distinguishable(self) -> None:
        """带裁决的应用必须记成 `conflict_resolution` source（AC 8.6 的分桶）。"""
        src = textwrap.dedent(
            inspect.getsource(OH.OoToHtmlCoordinator._apply_settled)
        )
        fn = ast.parse(src).body[0]
        names = {
            node.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Name)
        }
        assert {"CONFLICT_RESOLUTION", "ONLYOFFICE"} <= names, (
            "发布分支必须按有无裁决区分 content version source —— "
            "全记成 onlyoffice 之后无法区分「自动合并」与「人工裁决」"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 八、P29：materialize → extract roundtrip（真写真读的载体替身）
# ═══════════════════════════════════════════════════════════════════════════


def _ooxml(extra: dict[str, bytes]) -> bytes:
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("xl/workbook.xml", b'<?xml version="1.0"?><root/>')
        zf.writestr("xl/unmanaged.xml", b"<formulas/>")
        for name, payload in extra.items():
            zf.writestr(name, payload)
    return buf.getvalue()


class _JsonCarrierAdapter:
    """真 OOXML 容器 + JSON 受管部件的载体替身（真 materialize、真 extract）。

    与 Task 15 PG 守卫用的同一形态。**不是 mock**：`materialize` 真写 zip，
    `extract` 真读回来，因此 roundtrip 等值判据在真实执行上生效。真正的 Excel/Word
    engine 归 Tasks 36~38 / 59~61。

    `drop_keys` / `corrupt_keys` 是**注入缺陷**用的开关，供反向自检证明判据可证伪。
    """

    adapter_id = ENTRY
    document_type = "xlsx"
    contract_version = "1.0.0"

    def __init__(
        self, *, drop_keys: tuple[str, ...] = (), corrupt_keys: tuple[str, ...] = ()
    ) -> None:
        self.drop_keys = drop_keys
        self.corrupt_keys = corrupt_keys
        self.calls: list[str] = []

    async def read_current_projection(self, ctx):  # pragma: no cover - 本任务不用
        raise NotImplementedError

    async def stage_projection_mutation(self, ctx, merged, *, expected_revision):
        raise NotImplementedError  # pragma: no cover - 本任务不用

    def _payload(self, projection: Projection) -> dict:
        out = {}
        for key, value in projection.values.items():
            if key in self.drop_keys:
                continue
            raw = value.value
            if key in self.corrupt_keys:
                raw = f"{raw}-corrupted"
            out[key] = {
                "value": (str(raw) if isinstance(raw, Decimal) else raw),
                "value_type": value.value_type.value,
                "mode": value.mode.value,
                "row_key": value.row_key,
            }
        return out

    def materialize(self, *, substrate, projection, output, contract):
        self.calls.append("materialize")
        blob = _ooxml(
            {
                "_gt_sync/projection.json": json.dumps(
                    {
                        "contract_id": projection.contract_id,
                        "values": self._payload(projection),
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8"),
                "_gt_sync/row_keys.json": json.dumps(
                    {k: list(v) for k, v in (projection.row_keys or {}).items()},
                    sort_keys=True,
                ).encode("utf-8"),
            }
        )
        Path(output).write_bytes(blob)
        return MaterializeResult(
            output_path=Path(output),
            document_type=projection.document_type,
            artifact_sha256=hashlib.sha256(blob).hexdigest(),
            structure_hash=_d("task26-structure"),
            identity_inventory_sha256=_d("task26-identity"),
            managed_field_count=len(projection.values),
        )

    def extract(self, *, artifact, contract):
        self.calls.append("extract")
        with zipfile.ZipFile(artifact) as zf:
            raw = json.loads(zf.read("_gt_sync/projection.json").decode("utf-8"))
            try:
                rows = json.loads(zf.read("_gt_sync/row_keys.json").decode("utf-8"))
            except KeyError:
                rows = {}
        values: dict[str, FieldValue] = {}
        for key, item in raw["values"].items():
            vt = C.ValueType(item["value_type"])
            value = item["value"]
            if vt is C.ValueType.amount and value is not None:
                value = Decimal(str(value))
            values[key] = FieldValue(
                stable_key=key,
                value=value,
                value_type=vt,
                mode=C.FieldMode(item["mode"]),
                row_key=item.get("row_key"),
            )
        return Projection(
            contract_id=raw["contract_id"],
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values=values,
            row_keys={k: tuple(v) for k, v in rows.items()},
        )

    def verify_unmanaged_regions(self, *, before, after, contract):
        self.calls.append("verify_unmanaged_regions")
        with zipfile.ZipFile(before) as zb, zipfile.ZipFile(after) as za:
            same = zb.read("xl/unmanaged.xml") == za.read("xl/unmanaged.xml")
        return UnmanagedRegionReport(
            equivalent=same,
            inspected_aspects=("formula", "style", "drawing"),
            first_difference=None if same else "xl/unmanaged.xml",
        )


class TestRoundtripEquivalence:
    """P29 / AC 6.11：任一有效 projection materialize 后 extract，受管字段类型化相等。"""

    def test_roundtrip_is_typed_equal_for_every_managed_field(
        self, contract: C.SyncContract, tmp_path: Path
    ) -> None:
        row = str(uuid.uuid4())
        projection = _proj(
            contract,
            {
                PERIOD: "2025 年度",
                TOTAL: Decimal("1234567.50"),
                f"ar_rows/{row}/amount": Decimal("0.01"),
            },
        )
        adapter = _JsonCarrierAdapter()
        substrate = tmp_path / "incoming.xlsx"
        substrate.write_bytes(_ooxml({}))
        out = tmp_path / "result.xlsx"
        adapter.materialize(
            substrate=substrate, projection=projection, output=out, contract=contract
        )
        extracted = adapter.extract(artifact=out, contract=contract)
        assert set(extracted.values) == set(projection.values)
        from app.services.workpaper_sync.merge import values_equal

        for key, field in projection.values.items():
            assert values_equal(
                field.value, extracted.values[key].value, field.value_type
            ), f"{key} roundtrip 不等值"

    def test_dropped_managed_field_is_detected_by_the_platform_predicate(
        self, contract: C.SyncContract, tmp_path: Path
    ) -> None:
        """反向自检：注入「materialize 漏写一个受管字段」必须被 Task 15 的判据抓到。

        没有这条，上一条测试只证明「我的替身自洽」，不证明**平台**能发现漂移。
        """
        from app.services.workpaper_sync.content_mutation import (
            ContentMutationService,
            RoundtripEquivalenceError,
        )

        projection = _proj(contract, {PERIOD: "2025", TOTAL: Decimal("1")})
        adapter = _JsonCarrierAdapter(drop_keys=(TOTAL,))
        substrate = tmp_path / "incoming.xlsx"
        substrate.write_bytes(_ooxml({}))
        out = tmp_path / "result.xlsx"
        adapter.materialize(
            substrate=substrate, projection=projection, output=out, contract=contract
        )
        extracted = adapter.extract(artifact=out, contract=contract)
        service = ContentMutationService.__new__(ContentMutationService)
        with pytest.raises(RoundtripEquivalenceError):
            service._assert_roundtrip_equivalent(
                intended=projection, extracted=extracted, contract=contract
            )

    def test_corrupted_value_is_detected(
        self, contract: C.SyncContract, tmp_path: Path
    ) -> None:
        from app.services.workpaper_sync.content_mutation import (
            ContentMutationService,
            RoundtripEquivalenceError,
        )

        projection = _proj(contract, {PERIOD: "2025", TOTAL: Decimal("1")})
        adapter = _JsonCarrierAdapter(corrupt_keys=(PERIOD,))
        substrate = tmp_path / "incoming.xlsx"
        substrate.write_bytes(_ooxml({}))
        out = tmp_path / "result.xlsx"
        adapter.materialize(
            substrate=substrate, projection=projection, output=out, contract=contract
        )
        extracted = adapter.extract(artifact=out, contract=contract)
        service = ContentMutationService.__new__(ContentMutationService)
        with pytest.raises(RoundtripEquivalenceError):
            service._assert_roundtrip_equivalent(
                intended=projection, extracted=extracted, contract=contract
            )


# ═══════════════════════════════════════════════════════════════════════════
# 九、fence hook 的接线形态（Task 15 的三个回调点必须真被调用）
# ═══════════════════════════════════════════════════════════════════════════


class TestCommitFenceHookWiring:
    """`CommitFenceHook` 的三个点必须在 Task 15 的**指定位置**被调用。

    判据是源码形态而不是「跑一遍看它调了没」：hook 为 None 时（HTML→OO 等既有 writer）
    根本不调，跑一遍证明不了「OO→HTML 传了 hook 就会在 publish 前调」。真实执行的判据
    在 `_pg.py`（那里断言轨迹里 `fence_verified_before_publish` 早于 `business_committed`）。
    """

    def test_before_publish_is_called_between_unmanaged_check_and_publish(self) -> None:
        from app.services.workpaper_sync import content_mutation as CM

        src = inspect.getsource(CM.ContentMutationService._stage_and_verify)
        i_unmanaged = src.index("unmanaged.assert_equivalent()")
        i_fence = src.index("fence.before_publish(")
        i_publish = src.index("publish_representation(")
        assert i_unmanaged < i_fence < i_publish, (
            "AC 8.10 的次序：extract 等值/未管理区域 → fence → publish。"
            f"实测偏移 unmanaged={i_unmanaged} fence={i_fence} publish={i_publish}"
        )

    def test_before_write_is_called_after_lock_and_before_any_write(self) -> None:
        from app.services.workpaper_sync import content_mutation as CM

        src = inspect.getsource(CM.ContentMutationService._commit_once)
        i_lock = src.index("assert_expected_revision(")
        i_fence = src.index("fence.before_write(")
        i_bump = src.index("bump_content_revision(")
        assert i_lock < i_fence < i_bump, (
            "写库前的 fence 必须在 wp advisory+row lock 之内、第一次写之前"
        )

    def test_after_pointers_is_called_inside_the_single_transaction(self) -> None:
        from app.services.workpaper_sync import content_mutation as CM

        src = inspect.getsource(CM.ContentMutationService._commit_once)
        i_pointer = src.index('witness.stamp(self._session, "entry_pointer")')
        i_hook = src.index("fence.after_pointers(")
        i_commit = src.index("latch.commit_once(self._session)")
        assert i_pointer < i_hook < i_commit, (
            "application/operation timeline 必须与 pointer/outbox 同事务落库（AC 10.11）"
        )

    def test_hook_is_optional_so_existing_writers_are_untouched(self) -> None:
        from app.services.workpaper_sync import content_mutation as CM

        sig = inspect.signature(CM.ContentMutationService.commit)
        param = sig.parameters["fence"]
        assert param.default is None and param.kind is inspect.Parameter.KEYWORD_ONLY, (
            "`fence` 必须是 keyword-only 且默认 None —— Task 25 与既有 writer 的行为"
            "不得因本任务改变"
        )

    def test_apply_fence_implements_the_protocol(self) -> None:
        from app.services.workpaper_sync.content_mutation import CommitFenceHook

        fence = OH._ApplyFence.__new__(OH._ApplyFence)
        assert isinstance(fence, CommitFenceHook)


# ═══════════════════════════════════════════════════════════════════════════
# 十、无 fail-open：AuthorizationProbe 必填且异常不吞
# ═══════════════════════════════════════════════════════════════════════════


class TestNoFailOpen:
    def test_probe_is_a_required_constructor_argument(self) -> None:
        sig = inspect.signature(OH.OoToHtmlCoordinator.__init__)
        param = sig.parameters["probe"]
        assert param.default is inspect.Parameter.empty, (
            "`probe` 必须是必填参数 —— 可选即等于默认放行，而 AC 10.10 没有例外"
        )

    def test_coordinator_source_has_no_bare_warning_swallow(self) -> None:
        """`except Exception` 只允许出现在**重抛**或**落 error 终态**的位置。

        判据：每个 `except Exception` 处理块里必须出现 `raise` 或
        `_record_post_durable_failure`。写成「记 WARNING 后继续」会把接线错误
        （函数名写错、列名写错、单参调用 async 签名）表现成「本项目无此限制」，
        而四层静态检查全绿（Requirement 5.12 点名禁止）。
        """
        tree = ast.parse(inspect.getsource(OH))
        offenders: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            etype = node.type
            catches_broad = isinstance(etype, ast.Name) and etype.id in (
                "Exception",
                "BaseException",
            )
            if not catches_broad:
                continue
            body_src = "\n".join(
                ast.unparse(stmt) for stmt in node.body
            )
            if "raise" not in body_src and "_record_post_durable_failure" not in body_src:
                offenders.append(node.lineno)
        assert offenders == [], (
            f"第 {offenders} 行的 `except Exception` 既不重抛也不落 error 终态 —— fail-open"
        )

    def test_probe_failure_types_are_distinct_from_fence_failures(self) -> None:
        """「探针本身坏了」与「授权真的失效了」必须可分辨。

        共用一个类型时，接线错误会被当成正常的授权拒绝处理（走 supersede/recovery），
        于是「探针写错了」永远查不出来。
        """
        assert not issubclass(OH.AuthorizationProbeFailedError, OH.FinalFenceError)
        assert OH.AuthorizationProbeFailedError.error_code == "authorization_probe_failed"


# ═══════════════════════════════════════════════════════════════════════════
# 十一、P14：pre-bind shell 不得伪造 result revision
# ═══════════════════════════════════════════════════════════════════════════


class TestReloadFloorRevision:
    def test_outcome_exposes_floor_only_for_applied(self) -> None:
        """`reload_floor_revision` 只在 `applied` 时有值。

        `refresh_required` 也产生了新 revision，但那条路径要求编辑器**重开并重新确认
        descriptor**（AC 2.9），前端不该按旧 room 直接 reload ⇒ 不给 floor。
        """
        outcome = _outcome_stub(result=OH.OoToHtmlResult.applied, revision=42)
        assert outcome.reload_floor_revision == 42
        for result in (
            OH.OoToHtmlResult.conflict,
            OH.OoToHtmlResult.error,
            OH.OoToHtmlResult.authorization_stale,
            OH.OoToHtmlResult.refresh_required,
        ):
            assert _outcome_stub(result=result, revision=42).reload_floor_revision is None

    def test_pre_bind_result_revision_error_is_its_own_type(self) -> None:
        assert (
            OH.PreBindResultRevisionError.error_code
            == "pre_bind_shell_has_no_result_revision"
        )
        assert issubclass(OH.PreBindResultRevisionError, OH.OoToHtmlError)

    def test_callback_response_error_is_always_zero_after_durable(self) -> None:
        """Property 19：durable 之后一律 ack=0（非零 = 静默丢件，OO 不重投）。"""
        for result in OH.OoToHtmlResult:
            assert _outcome_stub(result=result, revision=1).callback_response_error == 0


def _outcome_stub(*, result: OH.OoToHtmlResult, revision: int) -> OH.OoToHtmlOutcome:
    substrate = OH.ReadOnlySubstrate(
        artifact_id=INCOMING,
        kind=ArtifactKind.incoming,
        state=ArtifactState.durable,
        origin=OH.LEGAL_SUBSTRATE_ORIGIN,
        path=Path("/tmp/incoming.xlsx"),
        relative_path=".incoming/x/y/incoming.xlsx",
        sha256=_d("incoming-bytes"),
        size_bytes=1024,
        document_type="xlsx",
        durable_at=_now(),
        published_at=None,
    )
    return OH.OoToHtmlOutcome(
        result=result,
        application_id=APP,
        canonical_operation_id=uuid.uuid4(),
        requested_operation_id=uuid.uuid4(),
        followed_duplicate=False,
        attempt=1,
        substrate=substrate,
        merge=None,
        conflict_count=0,
        conflict_set_digest=None,
        conflict_rows_written=0,
        conflict_rows_superseded=0,
        resolutions_applied=0,
        content_version_id=uuid.uuid4(),
        result_revision=revision,
        result_representation_id=uuid.uuid4(),
        result_artifact_sha256=_d("result"),
        merged_projection_sha256=_d("merged"),
        incoming_projection_sha256=_d("incoming-projection"),
        server_last_applied_advanced=True,
        client_baseline_advanced=True,
        room_refresh_required=False,
        room_superseded=False,
        next_forcesave_allowed=True,
        fence_compared_before_publish=("project_visible",),
        fence_compared_before_write=("project_visible",),
        callback_response_error=0,
        error_code=None,
        error_stage=None,
        error_detail=None,
        stages=(OH.ApplyStage.responded,),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 十二、终态分型：error 可重试 / authorization_stale 不可
# ═══════════════════════════════════════════════════════════════════════════


class TestTerminalTaxonomy:
    def test_error_and_authorization_stale_are_separate_results(self) -> None:
        """AC 10.10 末句：授权失效不得进普通 retry 队列。

        合并成一个终态的后果很具体：retry 按设计复用 frozen identity、不重新取授权，
        于是撤权用户的 application 会被重试着提交进去。
        """
        assert OH.OoToHtmlResult.error is not OH.OoToHtmlResult.authorization_stale
        assert {
            OH.OoToHtmlResult.error.value,
            OH.OoToHtmlResult.authorization_stale.value,
        } <= {s.value for s in OH.ApplicationState}
        assert {
            OH.OoToHtmlResult.error.value,
            OH.OoToHtmlResult.authorization_stale.value,
        } <= {s.value for s in OH.OperationState}

    def test_fence_failure_maps_to_authorization_stale_not_error(self) -> None:
        """源码形态：`FinalFenceError` 的 except 分支必须落 `authorization_stale`。"""
        src = inspect.getsource(OH.OoToHtmlCoordinator.apply_durable_incoming)
        i_fence = src.index("except FinalFenceError")
        i_generic = src.index("except OoToHtmlError")
        assert i_fence < i_generic, (
            "`FinalFenceError` 是 `OoToHtmlError` 的子类 —— 它的 except 必须在前，"
            "否则永远走不到 authorization_stale 分支"
        )
        stale_at = src.index("OoToHtmlResult.authorization_stale", i_fence)
        assert stale_at < i_generic

    def test_result_enum_covers_every_documented_terminal(self) -> None:
        assert {r.value for r in OH.OoToHtmlResult} == {
            "applied",
            "conflict",
            "refresh_required",
            "error",
            "authorization_stale",
        }
