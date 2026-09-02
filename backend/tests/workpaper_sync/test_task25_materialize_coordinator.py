# -*- coding: utf-8 -*-
"""Task 25 离线守卫：pending token、descriptor 完整性与授权顺序的**纯函数**判据。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 25
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 6.18
Properties: **P8 / P9 / P10 / P11 / P67**

═══ 为什么要有一个不连库的守卫文件 ═══

Task 25 的四类判据里有三类**不需要数据库**，把它们塞进 PG 文件反而会削弱判据：

1. **token 编解码与逐项比对** —— 五类拒绝（scope / TTL / digest / revision /
   Idempotency-Key）各一个异常类型。真库路径只会走到其中一条（第一个失败的），
   剩下四条会被遮蔽成不可达分支；离线合成输入才能逐条 falsify。
2. **descriptor 字段完整性** —— Property 11 的「字段完整后才 mount」是构造期判据。
   真库 happy path 永远给出完整 descriptor，所以「缺 slot digest 会被拒」只能靠
   合成输入证明。
3. **授权顺序的源码形态** —— Requirement 10.5 禁止的是代码形态，行为观察证明不了
   （见 :func:`assert_authorization_first_shape` 的 docstring）。

真库侧（room 行数、revision 变化、operation 终态、单事务）在
`test_task25_materialize_coordinator_pg.py`。

═══ 判别性：`_canonical_projection_bytes` 必须与 Task 15 同源 ═══

AC 3.6 的第二条幂等路径（不同 token、相同业务身份）依赖「flush 算的 digest ==
commit 落盘的 digest」。写第二套 canonicalizer 的后果不是「偶尔不等」，而是
**幂等复用永远命中不了** —— 而那在只测 token 重放的守卫下全绿。
:func:`test_canonical_projection_bytes_is_task15_implementation` 用**函数身份**
（不是「结果碰巧相等」）锁死这一点，另有一条实测两者对同一 projection 给出同一 digest。
"""
from __future__ import annotations

import hashlib
import inspect
import itertools
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.workpaper_sync import content_mutation as cm
from app.services.workpaper_sync import materialize_coordinator as mc
from app.services.workpaper_sync.adapters.base import FieldValue, Projection
from app.services.workpaper_sync.contracts import FieldMode, ValueType
from app.services.workpaper_sync.entry_profile import Capability
from app.services.workpaper_sync.models import AuthorityModel, BundleSlot

SECRET = "task25-offline-secret"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _projection(*, amount: str = "1234.50") -> Projection:
    return Projection(
        contract_id="d2.receivables.v1",
        semantic_version="1.0.0",
        document_type="xlsx",
        values={
            "summary/total": FieldValue(
                stable_key="summary/total",
                value=Decimal(amount),
                value_type=ValueType.amount,
                mode=FieldMode.editable,
            ),
        },
        row_keys={"summary": ("r1",)},
    )


def _token_payload(**over: object) -> mc.PendingMutationTokenPayload:
    base = dict(
        schema_version=mc.TOKEN_SCHEMA_VERSION,
        pending_mutation_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        entry_id="xlsx/gt-d2-accounts-receivable",
        sheet_key="AR-1",
        user_id=uuid.uuid4(),
        expected_revision=11,
        payload_sha256=_d("payload"),
        idempotency_key="idem-1",
        expires_at=_now() + timedelta(minutes=5),
    )
    base.update(over)
    return mc.PendingMutationTokenPayload(**base)  # type: ignore[arg-type]


def _request(token: str | None, payload: mc.PendingMutationTokenPayload, **over: object):
    base = dict(
        project_id=payload.project_id,
        wp_id=payload.wp_id,
        entry_id=payload.entry_id,
        sheet_key=payload.sheet_key,
        user_id=payload.user_id,
        pending_mutation_token=token,
        idempotency_key=payload.idempotency_key,
        expected_revision=payload.expected_revision,
        capability=Capability.bidirectional,
        projection=_projection(),
    )
    base.update(over)
    return mc.MaterializeRequest(**base)  # type: ignore[arg-type]


def _descriptor(**over: object) -> mc.EditorLaunchDescriptor:
    base = dict(
        operation_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        participant_id=uuid.uuid4(),
        doc_key="wpsync-abc123-g1",
        generation=1,
        server_applied_revision=12,
        client_confirmed_base_revision=None,
        content_version_id=uuid.uuid4(),
        representation_id=uuid.uuid4(),
        representation_generation=1,
        artifact_sha256=_d("artifact"),
        write_fence_epoch=1,
        authority_model=AuthorityModel.projection_contract.value,
        authority_model_definition_sha256=_d("authority"),
        definition_bundle_id=uuid.uuid4(),
        definition_bundle_sha256=_d("bundle"),
        definition_bundle_slots={
            "template": {"type": "definition", "sha256": _d("tpl")},
            "instrumentation": {"type": "definition", "sha256": _d("instr")},
            "contract": {"type": "definition", "sha256": _d("contract")},
        },
        document_type="xlsx",
        mode="edit",
        onlyoffice_config={"document": {"key": "wpsync-abc123-g1"}},
    )
    base.update(over)
    return mc.EditorLaunchDescriptor(**base)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# 1. token codec 与逐项比对（Property 10）
# ═══════════════════════════════════════════════════════════════════════════


def test_token_roundtrip_preserves_every_frozen_field() -> None:
    """签名往返后十一个字段逐项相等 —— token 是**完整**身份快照，不是一个 id。"""
    codec = mc.PendingMutationTokenCodec(SECRET)
    payload = _token_payload()
    decoded = codec.decode(codec.encode(payload))
    assert decoded.canonical_mapping() == payload.canonical_mapping()


def test_missing_token_is_refused_before_anything_else() -> None:
    """P8：没有 token ⇒ `PendingTokenRequiredError`，且它**不是** signature 错。

    「压根没 flush」与「flush 了但 token 坏了」是两件事：前者对应 Requirement 3.2
    的「模式切换停留在 HTML，room 与挂载次数均为 0」，后者是伪造。共用一个类型时，
    把空 token 分支删掉会被 signature 分支接住 ⇒ P8 的判据变成不可达分支。
    """
    codec = mc.PendingMutationTokenCodec(SECRET)
    for empty in (None, "", "   "):
        with pytest.raises(mc.PendingTokenRequiredError):
            codec.decode(empty)


@pytest.mark.parametrize(
    "mutate",
    ["flip_body", "flip_signature", "drop_signature", "extra_dot", "not_base64"],
    ids=["flip_body", "flip_signature", "drop_signature", "extra_dot", "not_base64"],
)
def test_tampered_token_fails_closed_before_any_db_read(mutate: str) -> None:
    """篡改一律 :class:`PendingTokenSignatureError`（验签在读库之前）。"""
    codec = mc.PendingMutationTokenCodec(SECRET)
    token = codec.encode(_token_payload())
    body, sig = token.split(".", 1)
    broken = {
        "flip_body": f"{body[:-2]}AA.{sig}",
        "flip_signature": f"{body}.{sig[:-2]}AA",
        "drop_signature": body,
        "extra_dot": f"{body}.{sig}.x",
        "not_base64": "!!!.???",
    }[mutate]
    with pytest.raises(mc.PendingTokenSignatureError):
        codec.decode(broken)


def test_token_signed_by_another_secret_is_refused() -> None:
    """密钥不同即拒 —— 否则任意进程都能签出可消费的 token。"""
    token = mc.PendingMutationTokenCodec("secret-a").encode(_token_payload())
    with pytest.raises(mc.PendingTokenSignatureError):
        mc.PendingMutationTokenCodec("secret-b").decode(token)


def test_empty_secret_is_refused_at_construction() -> None:
    """空密钥 = 不签名。构造期就拒，不留「运行时才发现」的窗口。"""
    with pytest.raises(mc.MaterializeCoordinatorError):
        mc.PendingMutationTokenCodec("")


def test_unknown_token_schema_version_fails_closed() -> None:
    """未登记 schema version 一律拒（Requirement 5.1 的同一原则）。"""
    with pytest.raises(mc.PendingTokenSignatureError):
        _token_payload(schema_version="wp-sync-pending-mutation:v99")


#: token ↔ request 五类不匹配 → 期望异常类型。**逐条独立**，共用类型会互相遮蔽。
_TOKEN_MISMATCH_CASES = {
    "project": (dict(project_id=uuid.uuid4()), mc.PendingTokenScopeError),
    "wp": (dict(wp_id=uuid.uuid4()), mc.PendingTokenScopeError),
    "entry": (dict(entry_id="xlsx/other-entry"), mc.PendingTokenScopeError),
    "sheet": (dict(sheet_key="OTHER"), mc.PendingTokenScopeError),
    "user": (dict(user_id=uuid.uuid4()), mc.PendingTokenScopeError),
    "idempotency_key": (dict(idempotency_key="idem-2"), mc.IdempotencyKeyMismatchError),
    "expected_revision": (dict(expected_revision=12), mc.PendingTokenRevisionError),
    "payload": (
        dict(projection=_projection(amount="9999.00")),
        mc.PendingTokenPayloadError,
    ),
}


@pytest.mark.parametrize(
    "case", sorted(_TOKEN_MISMATCH_CASES), ids=sorted(_TOKEN_MISMATCH_CASES)
)
def test_token_request_mismatch_has_its_own_refusal_type(case: str) -> None:
    """八种不匹配、四个异常类型，每一条都能被独立 falsify。

    payload digest 那一条刻意用**真的** projection 变体（金额从 1234.50 改成
    9999.00）而不是硬塞一个假 digest：真源是 canonicalization，硬塞 digest 测不出
    「两套 canonicalizer 漂移」这一类缺陷。
    """
    over, expected = _TOKEN_MISMATCH_CASES[case]
    coordinator = _bare_coordinator()
    payload = _token_payload(
        payload_sha256=hashlib.sha256(
            mc._canonical_projection_bytes(_projection())
        ).hexdigest()
    )
    request = _request("unused", payload, **over)
    with pytest.raises(expected):
        coordinator._assert_token_matches_request(payload, request)


def test_expired_token_is_refused_with_its_own_type() -> None:
    """TTL 过期是**第五**类拒绝，与 scope/payload/revision/key 都不同。"""
    coordinator = _bare_coordinator()
    payload = _token_payload(
        expires_at=_now() - timedelta(seconds=1),
        payload_sha256=hashlib.sha256(
            mc._canonical_projection_bytes(_projection())
        ).hexdigest(),
    )
    with pytest.raises(mc.PendingTokenExpiredError):
        coordinator._assert_token_matches_request(payload, _request("t", payload))


def test_matching_token_and_request_passes() -> None:
    """反向自检：全部相同必须放行。

    没有这一条，前面八条「必须抛」可以被一个恒抛实现全部满足（守卫缺陷）。
    """
    coordinator = _bare_coordinator()
    payload = _token_payload(
        payload_sha256=hashlib.sha256(
            mc._canonical_projection_bytes(_projection())
        ).hexdigest()
    )
    coordinator._assert_token_matches_request(payload, _request("t", payload))


def _bare_coordinator() -> mc.MaterializeCoordinator:
    """只装 token codec 的 coordinator。

    纯函数判据不需要 session/repository —— 传 `None` 让「这条判据偷偷读了库」当场
    `AttributeError`，比传一个宽容的 mock 更强（mock 会把误读静默吸收）。
    """
    return mc.MaterializeCoordinator(
        session=None,  # type: ignore[arg-type]
        repository=None,  # type: ignore[arg-type]
        artifacts=None,  # type: ignore[arg-type]
        resolution=None,  # type: ignore[arg-type]
        mutations=None,  # type: ignore[arg-type]
        rooms=object(),  # type: ignore[arg-type]
        token_codec=mc.PendingMutationTokenCodec(SECRET),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. canonicalization 同源（AC 3.6 第二条幂等路径的前提）
# ═══════════════════════════════════════════════════════════════════════════


def test_canonical_projection_bytes_is_task15_implementation() -> None:
    """判别性判据：coordinator **调用** Task 15 的 `_projection_payload`，而不是抄一份。

    只断言「两者结果相等」是不够的 —— 抄一份的初期结果也相等，漂移发生在半年后。
    这里用**函数身份**：源码里必须真的引用 `_projection_payload` 这个对象。
    """
    src = inspect.getsource(mc._canonical_projection_bytes)
    assert "_projection_payload(projection)" in src, (
        "coordinator 必须直接调用 content_mutation._projection_payload —— "
        "第二套 canonicalizer 会让「相同业务身份 ⇒ 幂等复用」永远命中不了，"
        "而那在只测 token 重放的守卫下全绿"
    )
    assert mc._projection_payload is cm._projection_payload


def test_coordinator_digest_equals_task15_projection_digest() -> None:
    """行为侧复核：同一 projection 两边算出同一个 digest。"""
    from app.services.workpaper_sync.definitions import canonical_json_bytes

    projection = _projection()
    mine = hashlib.sha256(mc._canonical_projection_bytes(projection)).hexdigest()
    theirs = hashlib.sha256(
        canonical_json_bytes(cm._projection_payload(projection))
    ).hexdigest()
    assert mine == theirs


def test_digest_changes_when_business_value_changes() -> None:
    """反向自检：改一个金额必须换 digest。

    否则「业务身份相同即复用」会把**不同**内容判成同一件事 —— 比命中不了更糟。
    """
    a = hashlib.sha256(
        mc._canonical_projection_bytes(_projection(amount="1.00"))
    ).hexdigest()
    b = hashlib.sha256(
        mc._canonical_projection_bytes(_projection(amount="2.00"))
    ).hexdigest()
    assert a != b


# ═══════════════════════════════════════════════════════════════════════════
# 3. descriptor 完整性（Property 11）
# ═══════════════════════════════════════════════════════════════════════════


def test_complete_descriptor_constructs_and_is_mountable() -> None:
    """反向自检：完整 descriptor 必须能构造（否则「必须拒绝」可被恒抛满足）。"""
    descriptor = _descriptor()
    assert descriptor.mountable is True
    assert set(descriptor.as_dict()) >= set(mc.DESCRIPTOR_REQUIRED_FIELDS)


def test_descriptor_required_fields_cover_requirement_3_7() -> None:
    """Requirement 3.7 逐项点名的字段必须都在必填清单里。

    清单漂移（有人删一项）会让「字段完整才 mount」出现盲区，所以这条是**对清单本身**
    的判据，不是对某个实例的。
    """
    for name in (
        "room_id", "participant_id", "doc_key", "generation",
        "server_applied_revision", "client_confirmed_base_revision",
        "representation_id", "representation_generation", "artifact_sha256",
        "write_fence_epoch", "authority_model", "definition_bundle_id",
        "definition_bundle_sha256", "definition_bundle_slots", "onlyoffice_config",
    ):
        assert name in mc.DESCRIPTOR_REQUIRED_FIELDS, (
            f"Requirement 3.7 点名的 {name!r} 不在 DESCRIPTOR_REQUIRED_FIELDS 里"
        )


#: 每一类缺陷一条用例。`ids=` 必给（parametrize 无 ids 时报告只有下标）。
_INCOMPLETE_DESCRIPTORS = {
    "zero_room_uuid": dict(room_id=uuid.UUID(int=0)),
    "zero_participant_uuid": dict(participant_id=uuid.UUID(int=0)),
    "zero_representation_uuid": dict(representation_id=uuid.UUID(int=0)),
    "zero_bundle_uuid": dict(definition_bundle_id=uuid.UUID(int=0)),
    "empty_artifact_digest": dict(artifact_sha256=""),
    "all_zero_artifact_digest": dict(artifact_sha256="0" * 64),
    "short_bundle_digest": dict(definition_bundle_sha256="abc"),
    "uppercase_authority_digest": dict(authority_model_definition_sha256="A" * 64),
    "generation_zero": dict(generation=0),
    "representation_generation_zero": dict(representation_generation=0),
    "revision_zero": dict(server_applied_revision=0),
    "fence_zero": dict(write_fence_epoch=0),
    "empty_doc_key": dict(doc_key="   "),
    "empty_mode": dict(mode=""),
    "empty_document_type": dict(document_type=""),
    "empty_authority_model": dict(authority_model=""),
    "missing_contract_slot": dict(
        definition_bundle_slots={
            "template": {"type": "definition", "sha256": _d("tpl")},
            "instrumentation": {"type": "definition", "sha256": _d("instr")},
        }
    ),
    "missing_instrumentation_slot": dict(
        definition_bundle_slots={
            "template": {"type": "definition", "sha256": _d("tpl")},
            "contract": {"type": "definition", "sha256": _d("contract")},
        }
    ),
    "empty_slot_type": dict(
        definition_bundle_slots={
            "template": {"type": "", "sha256": _d("tpl")},
            "instrumentation": {"type": "definition", "sha256": _d("instr")},
            "contract": {"type": "definition", "sha256": _d("contract")},
        }
    ),
    "zero_slot_digest": dict(
        definition_bundle_slots={
            "template": {"type": "definition", "sha256": "0" * 64},
            "instrumentation": {"type": "definition", "sha256": _d("instr")},
            "contract": {"type": "definition", "sha256": _d("contract")},
        }
    ),
    "slots_not_mapping": dict(definition_bundle_slots=[]),
    "empty_config": dict(onlyoffice_config={}),
}


@pytest.mark.parametrize(
    "case", sorted(_INCOMPLETE_DESCRIPTORS), ids=sorted(_INCOMPLETE_DESCRIPTORS)
)
def test_incomplete_descriptor_cannot_be_constructed(case: str) -> None:
    """22 类缺陷全部在**构造期**被拒 ⇒ 半个 descriptor 挂不上去（Property 11）。"""
    with pytest.raises(mc.DescriptorFieldMissingError):
        _descriptor(**_INCOMPLETE_DESCRIPTORS[case])


def test_confirm_payload_echoes_every_identity_the_server_checks() -> None:
    """`confirm_payload()` 必须覆盖 design §API 列出的十项回传字段。

    少一项就意味着服务端拿不到它、也就无法判「陈旧或篡改」—— Property 11 的
    409 判据会出现一个盲区。
    """
    payload = _descriptor().confirm_payload()
    assert sorted(payload) == sorted(
        [
            "participant_id", "generation", "doc_key", "representation_id",
            "artifact_sha256", "content_revision", "write_fence_epoch",
            "authority_model_definition_sha256", "definition_bundle_id",
            "definition_bundle_sha256",
        ]
    )


def test_onlyoffice_config_never_enables_editor_side_forcesave() -> None:
    """AC 4.1：`customization.forcesave=true` 不得被当成保存完成 ⇒ 一律 false。

    编辑器侧自动 forcesave 会产生**无 frozen request** 的孤儿 callback，
    只能进 recovery case（Requirement 5.8），对用户表现为「保存了但没回写」。
    """
    coordinator = _bare_coordinator()

    class _Room:
        doc_key = "wpsync-abc-g1"
        generation = 1
        write_fence_epoch = 1

    class _Rep:
        entry_id = "xlsx/gt-d2"
        document_type = "xlsx"

    config = coordinator._onlyoffice_config(
        room=_Room(), representation=_Rep(), document_type="xlsx"  # type: ignore[arg-type]
    )
    assert config["editorConfig"]["customization"]["forcesave"] is False
    assert config["document"]["key"] == "wpsync-abc-g1"


# ═══════════════════════════════════════════════════════════════════════════
# 4. 拒绝类型两两可分（本 spec 已付三次代价的形态）
# ═══════════════════════════════════════════════════════════════════════════

_REFUSALS = tuple(mc.MATERIALIZE_REJECTION_STATUS)


def test_every_refusal_has_a_distinct_error_code() -> None:
    """两条拒绝共用 `error_code` ⇒ 第一条永久不可达、其变异永久 GREEN。"""
    codes = [cls.error_code for cls in _REFUSALS]
    duplicates = sorted({code for code in codes if codes.count(code) > 1})
    assert not duplicates, f"以下 error_code 被多个拒绝类型共用: {duplicates}"


def test_refusals_are_pairwise_disjoint_except_the_declared_preflight_group() -> None:
    """除显式声明的 preflight 分组基类外，任意两个拒绝类型不得互为父子。

    `pytest.raises(A)` 会顺手吃掉 A 的子类 —— 于是「B 这条判据是否在起作用」永久
    不可分辨。唯一允许的例外是 :class:`MaterializePreflightError`（router 需要一个
    「这一类都是 422 且都零 operation」的可捕获边界），它在下一条测试里被单独锁死。
    """
    offenders = []
    for a, b in itertools.permutations(_REFUSALS, 2):
        if issubclass(a, b) and b is not mc.MaterializePreflightError:
            offenders.append(f"{a.__name__} 是 {b.__name__} 的子类")
    assert not offenders, "\n".join(offenders)


def test_preflight_group_is_exactly_the_422_family() -> None:
    """preflight 分组基类的成员集合 == 状态码 422 的集合（两侧互锁）。

    一侧漂移（新加一条 422 拒绝却没继承分组基类，或反之）就打红 —— 这防的是
    「router 用 `except MaterializePreflightError` 捕获，却漏掉一条 422」。
    """
    group = {
        cls.__name__
        for cls in _REFUSALS
        if issubclass(cls, mc.MaterializePreflightError)
        and cls is not mc.MaterializePreflightError
    }
    status_422 = {
        cls.__name__
        for cls, code in mc.MATERIALIZE_REJECTION_STATUS.items()
        if code == 422 and issubclass(cls, mc.MaterializePreflightError)
    }
    assert group == status_422
    assert group == {
        "EntryNotMaterializableError",
        "PerEntryContractMissingError",
        "BundleNotApprovedError",
        "RepresentationStillCandidateError",
        "SubstrateNotPublishedError",
    }


def test_unknown_exception_classifies_as_500_not_400() -> None:
    """未登记的失败必须 fail visible（500），不得静默降级成 4xx。"""
    assert mc.classify_materialize_rejection(RuntimeError("boom")) == 500
    assert mc.classify_materialize_rejection(mc.PendingTokenExpiredError("x")) == 409
    assert mc.classify_materialize_rejection(mc.BundleNotApprovedError("x")) == 422
    assert mc.classify_materialize_rejection(mc.MaterializeAuthorizationError("x")) == 403
    assert mc.classify_materialize_rejection(mc.MaterializeScopeNotVisibleError("x")) == 404


# ═══════════════════════════════════════════════════════════════════════════
# 5. authorization-before-idempotency（顺序由类型强制）
# ═══════════════════════════════════════════════════════════════════════════


def test_authorization_phase_reads_only_the_scope_index() -> None:
    """AST 判据：授权阶段只调 `resolve_scope`，且不引任何业务表符号。"""
    assert mc.assert_authorization_first_shape() == ("resolve_scope",)


def test_authorization_phase_covers_more_than_the_entry_method() -> None:
    """判据范围必须含 helper —— 否则把业务读挪进 helper 就绕过了。"""
    assert "authorize" in mc._AUTHORIZATION_PHASE_METHODS
    assert "_assert_token_matches_request" in mc._AUTHORIZATION_PHASE_METHODS


@pytest.mark.parametrize(
    "stages",
    [
        (),
        (mc.MaterializeStage.scope_resolved,),
        (mc.MaterializeStage.action_authorized,),
        (mc.MaterializeStage.token_verified,),
    ],
    ids=["none", "scope_only", "action_only", "token_only"],
)
def test_unauthorized_request_cannot_reach_idempotency(stages: tuple) -> None:
    """缺任一授权阶段 ⇒ 拒绝。`materialize` 拿不到未授权请求。"""
    payload = _token_payload()
    ref = mc.AuthorizedMaterializeRequest(
        request=_request("t", payload), stages=stages
    )
    with pytest.raises(mc.MaterializeAuthorizationError):
        ref.assert_token_verified()


def test_create_path_product_cannot_consume_a_pending_mutation() -> None:
    """`authorize_create()` 的产物只能用于 flush，不得用来消费 pending mutation。

    这是 Task 25 正文「任何重放先经过 authorization-before-idempotency guard」的
    第二半：create 路径按定义没有 token（还没有 pending mutation），若它的产物能进
    `materialize`，就等于「未验签 token 消费 pending mutation」。
    """
    payload = _token_payload()
    create_product = mc.AuthorizedMaterializeRequest(
        request=_request("t", payload),
        stages=(
            mc.MaterializeStage.scope_resolved,
            mc.MaterializeStage.action_authorized,
        ),
    )
    create_product.assert_authorized()  # flush 合法
    with pytest.raises(mc.MaterializeAuthorizationError):
        create_product.assert_token_verified()  # materialize 非法


def test_fully_authorized_request_passes_both_gates() -> None:
    """反向自检：两阶段齐全必须放行（否则上面几条可被恒抛满足）。"""
    payload = _token_payload()
    ref = mc.AuthorizedMaterializeRequest(
        request=_request("t", payload),
        stages=(
            mc.MaterializeStage.scope_resolved,
            mc.MaterializeStage.action_authorized,
            mc.MaterializeStage.token_verified,
        ),
    )
    ref.assert_authorized()
    ref.assert_token_verified()


def test_request_carries_no_mutation_surface() -> None:
    """请求对象会进 operation/evidence 快照 —— 它不得握着 session/outbox 能力面。"""
    from app.services.workpaper_sync.adapters.base import AdapterSideEffectError

    class _Session:
        def commit(self) -> None: ...

    payload = _token_payload()
    with pytest.raises(AdapterSideEffectError):
        _request("t", payload, adapter=_Session())


def test_request_requires_an_idempotency_key() -> None:
    """Requirement 3.1：pending mutation 与 commit 共用同一个 key，缺它即拒。"""
    payload = _token_payload()
    with pytest.raises(mc.MaterializeCoordinatorError):
        _request("t", payload, idempotency_key="  ")


# ═══════════════════════════════════════════════════════════════════════════
# 6. capability 门（Requirement 3.9 / 1.7）
# ═══════════════════════════════════════════════════════════════════════════


def test_non_materializable_capabilities_are_exactly_single_html_and_unreachable() -> None:
    """`single_html` 不得造空白 OO artifact；`unreachable` 不该有任何写入。

    集合两侧都断言：漏一个会放行造假，多一个会把合法入口锁死
    （`single_onlyoffice`/custom 有各自的权威模型，Requirement 3.9 明确要求返回 descriptor）。
    """
    assert mc._NON_MATERIALIZABLE == frozenset(
        {Capability.single_html, Capability.unreachable}
    )
    assert Capability.bidirectional not in mc._NON_MATERIALIZABLE
    assert Capability.single_onlyoffice not in mc._NON_MATERIALIZABLE


# ═══════════════════════════════════════════════════════════════════════════
# 7. Property 67：definitions-only 升级只能由 Task 15 finalize
# ═══════════════════════════════════════════════════════════════════════════


class _FakeFinalizeOutcome:
    """只带 Property 67 判据所需字段的合成结果。

    刻意不用真的 :class:`RepresentationFinalizeOutcome`（它要求十几个真 UUID）——
    本条判据只关心 `revision_unchanged`，多造的字段会掩盖判据本身。
    """

    def __init__(self, before: int, after: int) -> None:
        self.content_revision_before = before
        self.content_revision_after = after

    @property
    def revision_unchanged(self) -> bool:
        return self.content_revision_before == self.content_revision_after


class _FakeRepresentations:
    def __init__(self, outcome: object) -> None:
        self._outcome = outcome
        self.calls = 0

    async def finalize_candidate(self, **kwargs: object) -> object:
        self.calls += 1
        return self._outcome


def _coordinator_with(representations: object | None) -> mc.MaterializeCoordinator:
    return mc.MaterializeCoordinator(
        session=None,  # type: ignore[arg-type]
        repository=None,  # type: ignore[arg-type]
        artifacts=None,  # type: ignore[arg-type]
        resolution=None,  # type: ignore[arg-type]
        mutations=None,  # type: ignore[arg-type]
        rooms=object(),  # type: ignore[arg-type]
        token_codec=mc.PendingMutationTokenCodec(SECRET),
        representations=representations,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_definition_upgrade_that_moved_revision_is_refused() -> None:
    """纯定义升级递增 business revision ⇒ :class:`DefinitionUpgradeRevisionError`。

    Property 67 / Requirement 3.6：隐形载体升级只产生新 representation generation，
    `content_revision` 必须不变。
    """
    fake = _FakeRepresentations(_FakeFinalizeOutcome(11, 12))
    coordinator = _coordinator_with(fake)
    with pytest.raises(mc.DefinitionUpgradeRevisionError):
        await coordinator.finalize_definition_upgrade(candidate_id=uuid.uuid4())
    assert fake.calls == 1, "必须真的委派了 finalize_candidate 才谈得上断言其结果"


@pytest.mark.asyncio
async def test_definition_upgrade_with_unchanged_revision_is_returned_as_is() -> None:
    """反向自检：revision 不变时原样返回（否则上一条可被恒抛满足）。"""
    outcome = _FakeFinalizeOutcome(11, 11)
    coordinator = _coordinator_with(_FakeRepresentations(outcome))
    assert await coordinator.finalize_definition_upgrade() is outcome


@pytest.mark.asyncio
async def test_materialize_path_cannot_publish_representations_by_itself() -> None:
    """未装配 `RepresentationService` 时 definitions-only 升级必须**拒绝**而不是绕道。

    Property 67 的落点是「唯一出口」：materialize 路径不得顺手发布一个新
    representation generation。
    """
    coordinator = _coordinator_with(None)
    with pytest.raises(mc.MaterializeCoordinatorError):
        await coordinator.finalize_definition_upgrade()


def test_representation_service_is_revision_locked_by_construction() -> None:
    """Property 67 的构造侧：`RepresentationService` 拿不到 revision 域写入面。

    它在 `__init__` 里无条件把 repository 包成 `RevisionLockedRepository`，
    三个 revision 域方法调用即抛。这条判据锁的是「构造上不可能」，
    与上面的行为断言互补 —— 少任何一半都留缺口。
    """
    src = inspect.getsource(mc.RepresentationService.__init__)
    assert "RevisionLockedRepository" in src
    locked = cm.RevisionLockedRepository(object())  # type: ignore[arg-type]
    for name in sorted(cm.REVISION_DOMAIN_WRITE_METHODS):
        with pytest.raises(cm.RevisionBumpForbiddenError):
            getattr(locked, name)


# ═══════════════════════════════════════════════════════════════════════════
# 8. flush 的返回形态（Requirement 3.1 / design §API）
# ═══════════════════════════════════════════════════════════════════════════


def test_pending_mutation_receipt_returns_exactly_the_four_documented_fields() -> None:
    """`flushHtml()` 的响应体恰为四项 —— 多一项就会诱使前端把 flush 当成提交。"""
    receipt = mc.PendingMutationReceipt(
        pending_mutation_id=uuid.uuid4(),
        pending_mutation_token="tok",
        expected_revision=11,
        payload_sha256=_d("p"),
        expires_at=_now(),
        idempotency_key="idem-1",
        replayed=False,
    )
    assert sorted(receipt.as_dict()) == sorted(
        ["pending_mutation_token", "expected_revision", "payload_sha256", "expires_at"]
    )
    for leaked in ("content_version_id", "representation_id", "revision", "room_id"):
        assert leaked not in receipt.as_dict()


def test_flush_never_touches_the_revision_domain() -> None:
    """`create_pending_mutation` 必须经 `RevisionLockedRepository` 访问仓储。

    构造侧判据：门面让三个 revision 域方法**调用即抛**，所以「flush 不推进 revision」
    不是「我没写那三行」，而是碰不到。真库侧另有 revision 前后相等的行为断言。
    """
    src = inspect.getsource(mc.MaterializeCoordinator.create_pending_mutation)
    assert "RevisionLockedRepository(self._repo)" in src
    assert "locked.create_pending_mutation(" in src, (
        "pending mutation 的写入必须走 revision-locked 门面 —— 直接用 self._repo "
        "会让 flush 重新拿到 revision 域写入面"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 9. preflight 拒绝映射（真库里**不可构造**的那几条分支）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么这几条只能离线证：V151 让「current representation 指向未 approved bundle」
# 在库里**不存在** —— `wpsync_check_representation_bundle_approved` 拒绝这样的 INSERT、
# `wpsync_check_bundle_immutable` 拒绝 `approved → candidate`、`trg_wpcr_immutable`
# 又禁止 UPDATE representation。要在真库里造出它只能禁用触发器，那等于测一个不可能
# 发生的世界。这里改用 stub resolution 喂**同一段生产映射代码**，逐条 falsify。


class _RaisingResolution:
    """`resolve()` 恒抛指定异常的 stub。只替换**数据来源**，映射逻辑仍是生产代码。"""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc
        self.calls = 0

    async def resolve(self, **_kwargs: object) -> object:
        self.calls += 1
        raise self._exc


class _ReturningResolution:
    def __init__(self, resolution: object) -> None:
        self._resolution = resolution
        self.calls = 0

    async def resolve(self, **_kwargs: object) -> object:
        self.calls += 1
        return self._resolution


def _bundle_snapshot(*, state=None, drop_slot=None, marker_contract: bool = False):
    from app.services.workpaper_sync.models import BundleSlotSpec, DefinitionState
    from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot

    slots = {
        BundleSlot.template: BundleSlotSpec(
            BundleSlot.template, "definition", f"definition:{uuid.uuid4()}", _d("tpl")
        ),
        BundleSlot.instrumentation: BundleSlotSpec(
            BundleSlot.instrumentation,
            "definition",
            f"definition:{uuid.uuid4()}",
            _d("instr"),
        ),
        BundleSlot.contract: (
            BundleSlotSpec(
                BundleSlot.contract, "contract:none:v1", "marker:contract:none:v1",
                _d("marker"),
            )
            if marker_contract
            else BundleSlotSpec(
                BundleSlot.contract, "definition", f"definition:{uuid.uuid4()}",
                _d("contract"),
            )
        ),
    }
    if drop_slot is not None:
        slots.pop(drop_slot)
    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("bundle"),
        schema_version="wp-sync-definition-bundle:v1",
        state=state or DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("authority"),
        slots=slots,
    )


def _canonical_resolution(bundle: object):
    from app.services.workpaper_sync.resolution import CanonicalResolution, ResolutionIntent

    return CanonicalResolution(
        intent=ResolutionIntent.materialize,
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        entry_id="xlsx/gt-d2-accounts-receivable",
        content_version_id=uuid.uuid4(),
        content_revision=3,
        representation_id=uuid.uuid4(),
        representation_generation=1,
        document_type="xlsx",
        artifact_id=uuid.uuid4(),
        artifact_sha256=_d("artifact"),
        artifact_relative_path="storage/x/y.xlsx",
        artifact_path=Path("storage/x/y.xlsx"),
        adapter_id="excel.d2.v1",
        adapter_build_digest=_d("adapter"),
        structure_hash=_d("structure"),
        identity_inventory_sha256=_d("identity"),
        bundle=bundle,  # type: ignore[arg-type]
    )


def _authorized(**over: object) -> mc.AuthorizedMaterializeRequest:
    payload = _token_payload()
    return mc.AuthorizedMaterializeRequest(
        request=_request("t", payload, **over),
        stages=(
            mc.MaterializeStage.scope_resolved,
            mc.MaterializeStage.action_authorized,
            mc.MaterializeStage.token_verified,
        ),
    )


def _coordinator_with_resolution(resolution: object) -> mc.MaterializeCoordinator:
    return mc.MaterializeCoordinator(
        session=None,  # type: ignore[arg-type]
        repository=None,  # type: ignore[arg-type]
        artifacts=None,  # type: ignore[arg-type]
        resolution=resolution,  # type: ignore[arg-type]
        mutations=None,  # type: ignore[arg-type]
        rooms=object(),  # type: ignore[arg-type]
        token_codec=mc.PendingMutationTokenCodec(SECRET),
    )


@pytest.mark.asyncio
async def test_preflight_maps_missing_entry_pointer_to_substrate_not_published() -> None:
    """entry 还没有 published representation ⇒ 422 且**不是** candidate 那一类。

    Requirement 6.18：首个 representation 只能由版本化 template upgrader 产生，
    HTML→OO 不是它的替代路径。
    """
    from app.services.workpaper_sync.resolution import EntryPointerMissingError

    resolution = _RaisingResolution(EntryPointerMissingError("no pointer"))
    coordinator = _coordinator_with_resolution(resolution)
    with pytest.raises(mc.SubstrateNotPublishedError):
        await coordinator.preflight(_authorized())
    assert resolution.calls == 1, "必须真的调用过 resolver 才谈得上映射它的异常"


@pytest.mark.asyncio
async def test_preflight_maps_candidate_resolution_to_representation_still_candidate() -> None:
    """resolver 判定目标是未 finalize candidate ⇒ P67 的 422。"""
    from app.services.workpaper_sync.resolution import CandidateNotFinalizableError

    resolution = _RaisingResolution(CandidateNotFinalizableError("candidate"))
    coordinator = _coordinator_with_resolution(resolution)
    with pytest.raises(mc.RepresentationStillCandidateError):
        await coordinator.preflight(_authorized())
    assert resolution.calls == 1


@pytest.mark.asyncio
async def test_preflight_maps_bundle_integrity_failure_to_bundle_not_approved() -> None:
    """resolver 的 bundle 完整性失败（含 alias 漂移）⇒ 422 `definition_bundle_not_approved`。"""
    from app.services.workpaper_sync.models import BundleIntegrityError

    resolution = _RaisingResolution(BundleIntegrityError("digest drift"))
    coordinator = _coordinator_with_resolution(resolution)
    with pytest.raises(mc.BundleNotApprovedError):
        await coordinator.preflight(_authorized())
    assert resolution.calls == 1


@pytest.mark.asyncio
async def test_preflight_rejects_a_bundle_that_is_not_approved() -> None:
    """bundle `state=candidate` ⇒ 422。

    这是「未 approved bundle 不得进 materialize」这条判据在**代码层**的唯一落点 ——
    真库里该状态不可构造（见本节顶部说明）。
    """
    from app.services.workpaper_sync.models import DefinitionState

    resolution = _ReturningResolution(
        _canonical_resolution(_bundle_snapshot(state=DefinitionState.candidate))
    )
    coordinator = _coordinator_with_resolution(resolution)
    with pytest.raises(mc.BundleNotApprovedError):
        await coordinator.preflight(_authorized())


@pytest.mark.asyncio
async def test_preflight_rejects_a_bundle_with_a_missing_typed_slot() -> None:
    """typed slot 缺失（omission）⇒ 422。

    与「未 approved」分开测：两者在生产代码里是**两个** except 分支
    （`RepresentationSlotError` / `RepresentationBundleError`），只测一条时删掉另一条
    不会有任何测试变红。
    """
    resolution = _ReturningResolution(
        _canonical_resolution(_bundle_snapshot(drop_slot=BundleSlot.instrumentation))
    )
    coordinator = _coordinator_with_resolution(resolution)
    with pytest.raises(mc.BundleNotApprovedError):
        await coordinator.preflight(_authorized())


@pytest.mark.asyncio
async def test_preflight_rejects_marker_contract_slot_for_projection_entry() -> None:
    """`projection_contract` 入口的 contract slot 是 typed null marker ⇒ 422。

    Requirement 2.3 / 6.19：marker 只属于 custom/opaque，不得冒充 per-entry contract。
    """
    resolution = _ReturningResolution(
        _canonical_resolution(_bundle_snapshot(marker_contract=True))
    )
    coordinator = _coordinator_with_resolution(resolution)
    with pytest.raises(mc.BundleNotApprovedError):
        await coordinator.preflight(_authorized())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capability",
    [Capability.single_html, Capability.unreachable],
    ids=["single_html", "unreachable"],
)
async def test_preflight_refuses_non_materializable_capability_before_resolving(
    capability: Capability,
) -> None:
    """capability 门在 resolver **之前** —— `single_html` 连一次解析都不该发生。

    顺序即判据：Requirement 3.9 要求 `single_html` entry 不得创建空白 OO artifact，
    而「先解析再判 capability」会让一个不该有 OO 侧的 entry 也走一遍 artifact 解析。
    """
    resolution = _RaisingResolution(RuntimeError("resolver 不该被调用"))
    coordinator = _coordinator_with_resolution(resolution)
    with pytest.raises(mc.EntryNotMaterializableError):
        await coordinator.preflight(_authorized(capability=capability))
    assert resolution.calls == 0, "capability 门必须先于 resolver"


@pytest.mark.asyncio
async def test_preflight_refuses_projection_entry_without_a_contract() -> None:
    """`projection_contract` 入口缺 per-entry contract ⇒ 422，且**不得**按 alias 补齐。

    判据落在 contract 门**之后**的位置：bundle 形态合法（三 slot 齐、approved），
    唯一缺的是调用方没给 `SyncContract` 对象。
    """
    resolution = _ReturningResolution(_canonical_resolution(_bundle_snapshot()))
    coordinator = _coordinator_with_resolution(resolution)
    with pytest.raises(mc.PerEntryContractMissingError):
        await coordinator.preflight(_authorized(contract=None))


# ═══════════════════════════════════════════════════════════════════════════
# 10. 记账自证：四条纯判据（合成输入）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么必须用合成输入：这四条判据在**正确实现下恒不触发** —— 真实场景里
# `commit_count` 就是 1、revision delta 就是 1、flush 就是不动 revision。于是把它们
# 内联成 `if` 时，「短路它」在任何真实场景里都观察不到差异，定向变异必判 GREEN
# （本任务首轮实测 M28~M31/M51 五条全 GREEN）。抽成模块级纯函数并喂合成输入之后，
# 判据才可证伪。这与 Task 24 把 `assert_at_most_one_open_capture` 抽出来同一个决定。


@pytest.mark.parametrize(
    "before,after", [(11, 12), (11, 10), (0, 1)], ids=["up", "down", "zero_to_one"]
)
def test_flush_that_moved_the_revision_is_refused(before: int, after: int) -> None:
    """flush 前后 revision 不等 ⇒ `FlushRevisionDriftError`（Requirement 3.1）。"""
    with pytest.raises(mc.FlushRevisionDriftError):
        mc.assert_flush_revision_neutral(before, after)


def test_flush_with_an_unchanged_revision_passes() -> None:
    """反向自检：相等必须放行（否则上一条可被恒抛满足）。"""
    mc.assert_flush_revision_neutral(11, 11)
    mc.assert_flush_revision_neutral(0, 0)


@pytest.mark.parametrize(
    "count,txids",
    [
        (2, ("x1",)),
        (0, ("x1",)),
        (1, ("x1", "x2")),
        (1, ()),
    ],
    ids=["two_commits", "zero_commits", "two_transactions", "no_transaction"],
)
def test_non_single_business_commit_is_refused(count: int, txids: tuple) -> None:
    """提交次数或事务数不为 1 ⇒ `SingleCommitAccountingError`。

    四类输入覆盖两个维度各两侧：Requirement 3.1 禁止的「先提交 projection-only
    revision 再补 artifact」在观察面上正是「commit_count=2」或「两个 xid」。
    """
    with pytest.raises(mc.SingleCommitAccountingError):
        mc.assert_single_business_commit(commit_count=count, transaction_ids=txids)


def test_single_commit_in_single_transaction_passes() -> None:
    """反向自检：1/1 必须放行。"""
    mc.assert_single_business_commit(commit_count=1, transaction_ids=("xid-1",))


@pytest.mark.parametrize(
    "actual,base", [(11, 11), (13, 11), (10, 11)], ids=["same", "skipped", "backwards"]
)
def test_revision_target_other_than_base_plus_one_is_refused(
    actual: int, base: int
) -> None:
    """commit 报告的 revision ≠ base+1 ⇒ `RevisionTargetAccountingError`。

    与 :func:`test_non_single_business_commit_is_refused` 分开：一个判「提交了几次」，
    一个判「提交到了哪个版本」。artifact 文件名里带 revision，错位后历史读取会取到
    别的版本。
    """
    with pytest.raises(mc.RevisionTargetAccountingError):
        mc.assert_revision_target(actual=actual, base_revision=base)


def test_revision_target_of_base_plus_one_passes() -> None:
    """反向自检：base+1 必须放行。"""
    mc.assert_revision_target(actual=12, base_revision=11)
    mc.assert_revision_target(actual=1, base_revision=0)


@pytest.mark.parametrize(
    "delta,replayed,reused",
    [
        (2, False, False),
        (0, False, False),
        (1, True, False),
        (1, False, True),
        (-1, False, False),
    ],
    ids=[
        "two_revisions_on_commit",
        "zero_revisions_on_commit",
        "commit_on_replay",
        "commit_on_reuse",
        "revision_went_backwards",
    ],
)
def test_wrong_revision_delta_is_refused(
    delta: int, replayed: bool, reused: bool
) -> None:
    """数据库前后差不符协议 ⇒ `RevisionDeltaAccountingError`。

    五类输入把两条协议都测到两侧：提交路径必须恰 +1（`2` 与 `0` 都错），
    重放/复用路径必须恰 0（`1` 错）。
    """
    with pytest.raises(mc.RevisionDeltaAccountingError):
        mc.assert_revision_delta(
            delta=delta, replayed=replayed, business_identity_reused=reused
        )


@pytest.mark.parametrize(
    "delta,replayed,reused",
    [(1, False, False), (0, True, False), (0, False, True), (0, True, True)],
    ids=["commit", "replay", "reuse", "both"],
)
def test_correct_revision_delta_passes(
    delta: int, replayed: bool, reused: bool
) -> None:
    """反向自检：四种合法组合必须放行。"""
    mc.assert_revision_delta(
        delta=delta, replayed=replayed, business_identity_reused=reused
    )


def test_accounting_refusals_are_four_distinct_types() -> None:
    """四条记账判据各自一个类型/一个 error_code —— 否则短路其一会被其余遮蔽。"""
    types = (
        mc.FlushRevisionDriftError,
        mc.SingleCommitAccountingError,
        mc.RevisionTargetAccountingError,
        mc.RevisionDeltaAccountingError,
    )
    assert len({cls.error_code for cls in types}) == 4
    for a, b in itertools.permutations(types, 2):
        assert not issubclass(a, b), f"{a.__name__} 是 {b.__name__} 的子类"


def test_coordinator_delegates_to_the_pure_accounting_functions() -> None:
    """生产代码必须**调用**这四个纯函数，而不是自己内联一遍。

    内联形态就是它们被抽出来之前的样子 —— 在正确实现下恒不触发、定向变异必 GREEN。
    """
    for func_name, method in (
        ("assert_flush_revision_neutral", mc.MaterializeCoordinator.create_pending_mutation),
        ("assert_single_business_commit", mc.MaterializeCoordinator._commit_and_settle),
        ("assert_revision_target", mc.MaterializeCoordinator._commit_and_settle),
        ("assert_revision_delta", mc.MaterializeCoordinator.materialize),
    ):
        assert f"{func_name}(" in inspect.getsource(method), (
            f"{method.__qualname__} 没有调用 {func_name} —— 记账判据不得内联"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 11. authorization-first 白名单本身的判据
# ═══════════════════════════════════════════════════════════════════════════


def test_scope_only_repo_call_whitelist_is_exactly_resolve_scope() -> None:
    """白名单**两侧**都断言：放宽它（加一项）与收紧它（删空）都必须打红。

    🔴 只断言 `assert_authorization_first_shape() == ('resolve_scope',)` 是不够的：
    那看的是**实际调用**，把 `lock_room` 加进白名单不会改变实际调用 ⇒ 判据看不出
    白名单被放宽（本任务实测 GREEN 过一次）。
    """
    assert mc._SCOPE_ONLY_REPO_CALLS == frozenset({"resolve_scope"}), (
        "授权阶段只允许读非敏感 scope index —— 白名单里多一项就等于允许「先锁业务行」"
    )


def test_business_table_denylist_covers_every_sync_business_table() -> None:
    """禁用名单必须覆盖授权阶段可能误读的全部业务表。

    漏登记一张表 ⇒ 在授权阶段 `sa.select(那张表)` 不会被 AST 判据抓到。
    """
    for name in (
        "WorkpaperPendingMutation",
        "WorkpaperSyncOperation",
        "WorkpaperContentVersion",
        "WorkpaperContentRepresentation",
        "WorkpaperOoRoom",
        "WorkpaperOoParticipant",
    ):
        assert name in mc._BUSINESS_TABLES, f"业务表 {name} 未登记进禁用名单"


# ═══════════════════════════════════════════════════════════════════════════
# 12. stale-substrate 的两个 raise 点必须可分辨
# ═══════════════════════════════════════════════════════════════════════════


def test_stale_substrate_has_two_distinguishable_raise_sites() -> None:
    """两处共用一个异常类型，但消息带**不同**标记，故「哪一条在起作用」可分辨。

    🔴 这条判据存在的理由是本任务实测过的一次 GREEN：删掉重放侧那条判据后，流程会
    往下走到 room 打开侧并抛出**同样**的类型，只断言类型的守卫因此判 GREEN。
    """
    assert mc.STALE_ON_REPLAY_MARKER != mc.STALE_ON_ROOM_OPEN_MARKER
    replay_src = inspect.getsource(mc.MaterializeCoordinator._replay_committed)
    room_src = inspect.getsource(mc.MaterializeCoordinator._open_room_and_descriptor)
    assert "STALE_ON_REPLAY_MARKER" in replay_src
    assert "STALE_ON_ROOM_OPEN_MARKER" in room_src
    assert "STALE_ON_ROOM_OPEN_MARKER" not in replay_src
    assert "STALE_ON_REPLAY_MARKER" not in room_src
