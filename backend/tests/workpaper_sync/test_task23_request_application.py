# -*- coding: utf-8 -*-
"""Task 23 离线守卫：resolve 裁决顺序、accepted 凭据、读路径类型强制与结构判据。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 23
Requirements: 2.9, 4.1, 4.3, 4.10, 4.11, 5.4, 5.5, 5.10, 8.5, 10.5, 10.11, 14.3
Properties: **P18 / P36 / P56 / P62 / P64**

═══ 本模块与 `_pg.py` 的分工 ═══

真库那份测「行为」（并发收敛、约束归因、schema 形态）。本模块测**纯判定与结构**：

* :func:`~app.services.workpaper_sync.request_application.arbitrate_resolve` 的
  裁决顺序矩阵 —— 它是纯函数，真库跑一遍只会覆盖到其中一条分支；
* accepted 凭据的自证；
* 「authorization-first 由参数类型强制」的类型判据；
* 结构判据：本模块不得依赖 Command Service / HTTP（AC 4.1 的「先落库再调 OO」
  在代码层的形态），以及 `application_key` 不得出现在 operation 侧。

═══ 判据形态上的两条自律 ═══

1. **负向承诺必须注入反例**。「同 app 更高 sequence 永不 stale」只断言真实输入不 stale
   是不够的 —— 把 identity 比较整条删掉后，真实输入照样不 stale（因为没有更高的
   不同 application）。所以每条负向承诺都配一个「把顺序调换后会给出不同结论」的
   构造输入（见 :func:`test_identity_must_be_compared_before_sequence` 家族）。
2. **绝不写「断言真实数据仍有缺陷」的守卫**。分支覆盖一律用合成输入证明。
"""
from __future__ import annotations

import ast
import inspect
import os
import sys
import uuid
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import request_application as ra  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    IdentityError,
    OperationShape,
    SyncDomainError,
)

MODULE_PATH = _BACKEND / "app" / "services" / "workpaper_sync" / "request_application.py"

APP_A = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
APP_B = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
DIGEST = "a" * 63 + "b"
OTHER_DIGEST = "c" * 63 + "d"


def _fence(**over: object) -> ra.ResolveFence:
    base: dict[str, object] = {
        "expected_current_revision": 7,
        "room_generation": 3,
        "client_edit_epoch": 11,
        "canonical_application_id": APP_A,
        "application_effective_request_sequence": 5,
        "room_latest_durable_application_id": APP_A,
        "room_latest_durable_sequence": 5,
        "conflict_set_digest": DIGEST,
    }
    base.update(over)
    return ra.ResolveFence(**base)  # type: ignore[arg-type]


def _arbitrate(**over: object) -> ra.ResolveArbitration:
    """裁决入参的**唯一**构造点。

    散参数意味着某个场景可以少传一项而不报错，于是「这个场景真的只动了那一维」
    无法保证 —— 一个场景同时违反两条谓词时，打红了也分不清是哪条在工作。
    """
    fence_over = {k[6:]: v for k, v in over.items() if k.startswith("fence_")}
    rest = {k: v for k, v in over.items() if not k.startswith("fence_")}
    base: dict[str, object] = {
        "fence": _fence(**fence_over),
        "current_revision": 7,
        "current_room_generation": 3,
        "current_write_fence_epoch": 2,
        "request_write_fence_epoch": 2,
        "current_client_edit_epoch": 11,
        "canonical_application_id": APP_A,
        "canonical_effective_request_sequence": 5,
        "room_latest_durable_application_id": APP_A,
        "room_latest_durable_sequence": 5,
        "current_conflict_set_digest": DIGEST,
    }
    base.update(rest)
    return ra.arbitrate_resolve(**base)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# 一、裁决顺序矩阵（Property 36 / AC 8.5）
# ═══════════════════════════════════════════════════════════════════════════


def test_unchanged_world_proceeds() -> None:
    """基线场景必须 `proceed`。

    这条是全部否定判据的前置：没有它，「某个改动导致拒绝」可能只是因为基线本来就拒。
    """
    out = _arbitrate()
    assert out.verdict is ra.ResolveVerdict.proceed
    assert out.stale is False
    assert out.normalized_effective_sequence == 5


# 🔴 `ids=` 必须显式给，nodeid 才是稳定契约。
# 不给时 pytest 会按**全部**参数拼 id（dict 参数变成 `over0`），实得
# `[generation-over0-room_generation]` —— 变异脚本的 `want=[generation]` 定位不到，
# 判定退化成 WRONG-TEST（本轮实测 10 条）。参数化 nodeid 一旦被变异脚本引用，
# 它就是接口的一部分。
@pytest.mark.parametrize(
    "over,expected_last_compared",
    [
        ({"current_room_generation": 4}, "room_generation"),
        ({"current_write_fence_epoch": 3}, "write_fence_epoch"),
        ({"current_client_edit_epoch": 12}, "client_edit_epoch"),
    ],
    ids=["generation", "write_fence", "client_epoch"],
)
def test_fence_changes_are_refused_before_anything_else(
    over: dict[str, object], expected_last_compared: str
) -> None:
    """fence 三项各自独立拒绝，且**在 digest/identity 之前**。

    逐项参数化而不是合成一条：三项共用一个 `fence_changed` verdict，合成写法下
    删掉任一项的判据都会被另两项遮蔽（Task 22 M04/M10 的同一形态）。
    `compared` 的最后一项证明它是在哪一步停下的 —— 这才把「顺序」变成可判据的。
    """
    out = _arbitrate(**over)
    assert out.verdict is ra.ResolveVerdict.fence_changed, over
    assert out.compared[-1] == expected_last_compared
    assert "canonical_application_identity" not in out.compared


def test_conflict_digest_mismatch_is_refused_before_identity() -> None:
    out = _arbitrate(current_conflict_set_digest=OTHER_DIGEST)
    assert out.verdict is ra.ResolveVerdict.conflict_digest_stale
    assert out.compared[-1] == "conflict_set_digest"
    assert "canonical_application_identity" not in out.compared


def test_same_application_with_higher_sequence_only_folds() -> None:
    """Property 18/36 的核心负向承诺：同 canonical application 的更高 sequence **只 fold**。

    `stale is False` 与 `verdict is fold_and_proceed` 都要断言：只看 verdict 时，
    把 `stale` 属性改成 `verdict is not proceed` 不会被发现，而 API 消费方读的是 `stale`。
    """
    out = _arbitrate(
        canonical_effective_request_sequence=9,
        room_latest_durable_sequence=9,
    )
    assert out.verdict is ra.ResolveVerdict.fold_and_proceed
    assert out.stale is False
    assert out.normalized_effective_sequence == 9
    assert out.compared[-1] == "same_application_sequence_fold"
    # 同 app 分支下**不得**出现「按 sequence 判 supersede」那一步
    assert "effective_request_sequence" not in out.compared


def test_different_newer_application_supersedes() -> None:
    out = _arbitrate(
        room_latest_durable_application_id=APP_B,
        room_latest_durable_sequence=9,
    )
    assert out.verdict is ra.ResolveVerdict.superseded
    assert out.stale is True
    assert out.compared[-1] == "effective_request_sequence"


def test_different_but_not_newer_application_does_not_supersede() -> None:
    """「只有**较新且不同**的 durable snapshot 才可 supersede」——「不同」不足以 supersede。

    没有这条时，把 sequence 比较整条删掉（只要 identity 不同就 supersede）会保持全绿。
    """
    out = _arbitrate(
        room_latest_durable_application_id=APP_B,
        room_latest_durable_sequence=4,
    )
    assert out.verdict is ra.ResolveVerdict.proceed
    assert out.stale is False
    assert out.compared[-1] == "effective_request_sequence"


def test_equal_sequence_on_different_application_does_not_supersede() -> None:
    """边界：sequence **相等**的不同 application 也不 supersede（要求严格更高）。"""
    out = _arbitrate(
        room_latest_durable_application_id=APP_B,
        room_latest_durable_sequence=5,
    )
    assert out.verdict is ra.ResolveVerdict.proceed


def test_current_revision_change_without_newer_application_rebases() -> None:
    out = _arbitrate(current_revision=8)
    assert out.verdict is ra.ResolveVerdict.rebase_required
    assert out.compared[-1] == "current_revision"


def test_room_without_durable_pointer_is_treated_as_same_canonical() -> None:
    """room 还没有 durable 指针（首次 application 尚未落地）不得判 supersede。"""
    out = _arbitrate(room_latest_durable_application_id=None)
    assert out.verdict is ra.ResolveVerdict.proceed
    assert out.stale is False


# ── 注入反例：证明「identity 先于 sequence」不是重言式 ────────────────────


def test_identity_must_be_compared_before_sequence() -> None:
    """反例注入：同一组输入，两种比较顺序给出**不同**结论。

    输入 = 同 canonical application + room durable sequence 更高。

    * 正确顺序（identity 先）⇒ `fold_and_proceed`（不 stale）；
    * 错误顺序（sequence 先）⇒ 会看到「有更高 sequence」而判 `superseded`，
      也就是 AC 5.5 明令禁止的 self-supersede。

    这条断言的价值就在于这组输入是**判别性的**：把源码里两步调换，本条必红。
    与之配套的 `test_same_application_with_higher_sequence_only_folds` 断言结论，
    本条断言的是「结论对顺序敏感」——少了它，「顺序」只是注释。
    """
    out = _arbitrate(
        canonical_effective_request_sequence=9,
        room_latest_durable_sequence=9,
    )
    assert out.verdict is not ra.ResolveVerdict.superseded
    ident = out.compared.index("canonical_application_identity")
    # 同 app 分支：identity 之后只允许出现 fold 那一步，绝不能出现 supersede 比较
    assert out.compared[ident + 1] == "same_application_sequence_fold"


def test_self_supersede_is_impossible_for_every_higher_sequence() -> None:
    """把「更高 sequence」在一段区间内穷举：同 app 时**没有任何**取值会 stale。

    单点断言只能证明某一个 sequence 不 stale；`>` / `>=` 写错时单点可能刚好落在正确侧。
    """
    for higher in range(6, 40):
        out = _arbitrate(
            canonical_effective_request_sequence=higher,
            room_latest_durable_sequence=higher,
        )
        assert out.stale is False, higher
        assert out.verdict is ra.ResolveVerdict.fold_and_proceed, higher
        assert out.normalized_effective_sequence == higher


def test_fold_never_lowers_the_normalized_sequence() -> None:
    """fold 是 `GREATEST`：客户端报的 sequence 比服务端高时不得回退。"""
    out = _arbitrate(
        fence_application_effective_request_sequence=12,
        canonical_effective_request_sequence=5,
    )
    assert out.normalized_effective_sequence == 12
    assert out.verdict in (ra.ResolveVerdict.proceed, ra.ResolveVerdict.rebase_required)


def test_zero_sequence_is_refused_by_the_fold_primitive() -> None:
    """sequence 必须 >= 1：0/负数是「没冻结过」的信号，不能被当成合法最小值。"""
    with pytest.raises(IdentityError):
        _arbitrate(
            fence_application_effective_request_sequence=0,
            canonical_effective_request_sequence=0,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 二、accepted 凭据（AC 4.1）
# ═══════════════════════════════════════════════════════════════════════════


def _accepted(**over: object) -> ra.AcceptedRequest:
    base: dict[str, object] = {
        "request": object(),
        "operation": object(),
        "operation_shape": OperationShape.pre_correlation,
        "application_count": 0,
        "cache_hit": False,
        "request_sequence": 4,
        "frozen_request_fingerprint": DIGEST,
    }
    base.update(over)
    return ra.AcceptedRequest(**base)  # type: ignore[arg-type]


def test_clean_accepted_receipt_is_dispatchable() -> None:
    _accepted().assert_dispatchable()  # 不抛即通过


@pytest.mark.parametrize(
    "over",
    [
        {"operation_shape": OperationShape.primary},
        {"operation_shape": OperationShape.duplicate},
        {"application_count": 1},
    ],
    ids=["primary_shape", "duplicate_shape", "precreated_application"],
)
def test_receipt_refuses_to_dispatch_when_application_already_exists(
    over: dict[str, object],
) -> None:
    """三种形态各自独立拒绝。

    shape 与 count 两条判据必须分开：只留 count 时，「shell 已经是 primary 但
    application 计数查错表返回 0」会放行；只留 shape 时，并发下别人替这个 request
    建了 application 的情形看不见。
    """
    with pytest.raises(ra.ApplicationPrecreatedError):
        _accepted(**over).assert_dispatchable()


def test_precreated_error_is_a_sync_domain_error() -> None:
    """必须挂在 :class:`SyncDomainError` 下，否则会被上游宽泛 except 吞成成功。"""
    assert issubclass(ra.ApplicationPrecreatedError, SyncDomainError)
    assert ra.ApplicationPrecreatedError.error_code == "application_precreated"


# ═══════════════════════════════════════════════════════════════════════════
# 二之二、收敛形态四条不变量（Property 18）—— 合成输入逐条覆盖
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么用合成输入而不是真实 correlation：真实 correlation 永远走 happy path，
# 这四条分支在真库守卫里一条都触发不到。绝不能写成「断言真实数据仍有缺陷」——
# 分支覆盖一律用合成输入证明。

OP_P = uuid.UUID("11111111-0000-4000-8000-000000000001")
OP_D = uuid.UUID("22222222-0000-4000-8000-000000000002")


def _converge(**over: object) -> OperationShape:
    base: dict[str, object] = {
        "reported_shape": OperationShape.primary,
        "application_id": APP_A,
        "duplicate_of_operation_id": None,
        "state": "application_bound",
        "canonical_application_id": APP_A,
        "canonical_primary_operation_id": OP_P,
        "origin_request_sequence": 3,
        "effective_request_sequence": 7,
    }
    base.update(over)
    return ra.assert_correlation_convergence(**base)  # type: ignore[arg-type]


def test_convergence_accepts_a_clean_primary() -> None:
    assert _converge() is OperationShape.primary


def test_convergence_accepts_a_clean_direct_duplicate() -> None:
    assert (
        _converge(
            reported_shape=OperationShape.duplicate,
            application_id=None,
            duplicate_of_operation_id=OP_P,
            state="duplicate",
        )
        is OperationShape.duplicate
    )


@pytest.mark.parametrize(
    "over",
    [
        # ① 报告的 shape 与行实际形态不一致
        {
            "reported_shape": OperationShape.duplicate,
            "application_id": APP_A,
            "duplicate_of_operation_id": None,
            "state": "application_bound",
        },
        # ② primary 绑的不是本次 canonical application
        {"canonical_application_id": APP_B},
        # ③ duplicate 没有直指 canonical primary（= 链/环的入口）
        {
            "reported_shape": OperationShape.duplicate,
            "application_id": None,
            "duplicate_of_operation_id": OP_D,
            "state": "duplicate",
            "canonical_primary_operation_id": OP_P,
        },
        # ④ 仍停在 pre-correlation（= 停在 waiting_application）
        {
            "reported_shape": OperationShape.pre_correlation,
            "application_id": None,
            "duplicate_of_operation_id": None,
            "state": "waiting_application",
        },
        # ⑤ effective < origin（GREATEST 语义被破坏）
        {"origin_request_sequence": 9},
    ],
    ids=[
        "shape_mismatch",
        "primary_wrong_application",
        "duplicate_not_direct",
        "left_in_pre_correlation",
        "effective_below_origin",
    ],
)
def test_convergence_refuses_each_broken_shape(over: dict[str, object]) -> None:
    with pytest.raises(ra.ConvergenceError):
        _converge(**over)


def _claim_shape(**over: object) -> None:
    base: dict[str, object] = {
        "operation_shape": OperationShape.primary,
        "application_id": APP_A,
        "case_application_id": APP_A,
    }
    base.update(over)
    ra.assert_recovery_claim_shape(**base)  # type: ignore[arg-type]


def test_recovery_claim_shape_accepts_primary_and_direct_duplicate() -> None:
    _claim_shape()
    _claim_shape(operation_shape=OperationShape.duplicate)


@pytest.mark.parametrize(
    "over",
    [
        {"operation_shape": OperationShape.pre_correlation},
        {"application_id": None, "case_application_id": None},
        {"case_application_id": APP_B},
    ],
    ids=["pre_correlation", "no_application", "case_binds_another_application"],
)
def test_recovery_claim_shape_refuses_each_broken_case(over: dict[str, object]) -> None:
    """三条分支各一条。

    `no_application` 刻意把 case 也设成 None：只改 `application_id` 时会先撞第三条
    （case 与 claim 不等），于是第二条永远不可达 —— 「一个场景只违反一个谓词」。
    """
    with pytest.raises(ra.RecoveryClaimShapeError):
        _claim_shape(**over)


# ═══════════════════════════════════════════════════════════════════════════
# 三、403 与 404 分型（AC 10.5）
# ═══════════════════════════════════════════════════════════════════════════


def test_scope_denied_and_scope_not_visible_are_distinct_types() -> None:
    """两者**互不为子类** —— 否则 `pytest.raises` 会被继承关系放过。

    Task 22 的 M04/M10 就是这个形态：两条拒绝共用一个类型时，先声明的那条永久不可达，
    定向变异判 GREEN。这里 403/404 的语义差别正是 AC 10.5 的要求
    （「仅 scope 可见但 action 不允许时返回统一 403」）。
    """
    assert not issubclass(ra.ScopeAuthorizationDeniedError, ra.OperationScopeNotVisibleError)
    assert not issubclass(ra.OperationScopeNotVisibleError, ra.ScopeAuthorizationDeniedError)
    assert (
        ra.ScopeAuthorizationDeniedError.error_code
        != ra.OperationScopeNotVisibleError.error_code
    )


def test_unbound_and_multibound_are_sibling_types() -> None:
    """「canonical primary 未绑定」与「被多个 operation 绑定」必须互不为子类。

    这两条拒绝在源码里**紧挨着**，而第二条会吞掉第一条的场景：`app_id is None` 时
    若第一条不拒，紧接着的 `count(... application_id == app_id)` 被 SQLAlchemy 渲染成
    `IS NULL` ⇒ 统计到全部 pre-correlation shell ⇒ `bound != 1` 照样抛。
    共用类型时定向变异实测 GREEN（本轮 M25），拆开后才可证。
    """
    assert not issubclass(ra.CanonicalPrimaryUnboundError, ra.CanonicalBindingError)
    assert not issubclass(ra.CanonicalBindingError, ra.CanonicalPrimaryUnboundError)


def test_every_domain_error_carries_its_own_error_code() -> None:
    """每个异常类型一个独立 `error_code`（禁共用，理由同上）。"""
    classes = [
        ra.RequestApplicationDomainError,
        ra.ScopeAuthorizationDeniedError,
        ra.OperationScopeNotVisibleError,
        ra.ApplicationPrecreatedError,
        ra.RecoveryClaimShapeError,
        ra.CanonicalPrimaryUnboundError,
        ra.CanonicalBindingError,
        ra.ConvergenceError,
    ]
    codes = [c.error_code for c in classes]
    assert len(set(codes)) == len(codes), codes
    assert all(issubclass(c, SyncDomainError) for c in classes)


# ═══════════════════════════════════════════════════════════════════════════
# 四、authorization-first 的类型强制与源码形态（AC 10.5）
# ═══════════════════════════════════════════════════════════════════════════


def test_authorized_ref_is_the_only_way_into_canonicalize() -> None:
    """`canonicalize_authorized` 的形参注解必须是 `AuthorizedOperationRef`。

    这条是「authorization-first 由参数类型强制」的静态一半；运行期一半在 PG 守卫里
    （裸对象与缺阶段的 ref 都被拒）。少了静态这一半，把注解放宽成 `Any` 之后
    运行期检查若被同时删掉就没有任何判据会红。
    """
    sig = inspect.signature(ra.RequestApplicationService.canonicalize_authorized)
    ann = sig.parameters["ref"].annotation
    assert ann in (ra.AuthorizedOperationRef, "AuthorizedOperationRef"), ann


def test_authorization_stage_calls_only_resolve_scope() -> None:
    assert ra.assert_authorization_first_source_shape() == ("resolve_scope",)


def test_read_stage_order_is_declared_once_and_is_total() -> None:
    """阶段枚举的声明序就是执行序 —— 它是 PG 守卫里那两条顺序断言的真源。"""
    assert [s.value for s in ra.ReadStage] == [
        "requested_scope_resolved",
        "requested_action_authorized",
        "requested_operation_loaded",
        "direct_primary_verified",
        "canonicalized",
        "canonical_application_bound",
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 五、结构判据：落库与「调 OO」之间的界（AC 4.1）
# ═══════════════════════════════════════════════════════════════════════════

_COMMAND_SERVICE_SYMBOLS = (
    "httpx",
    "aiohttp",
    "requests",
    "urllib",
    "CommandService",
    "command_service",
    "forcesave_command",
    "sign_command_jwt",
)


def test_module_has_no_command_service_or_http_dependency() -> None:
    """AC 4.1「**先**落库、**再**调 Command Service」的代码层形态。

    本模块是 Task 24 的前置；只要它自己能发 HTTP，「先落库」就可以被一次内联调用
    绕过而无人察觉。判据落在 import 图上（不是注释）：本模块不得引入任何
    HTTP 客户端或 Command Service 符号。
    """
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
            imported.update(a.name for a in node.names)
    hits = sorted(s for s in _COMMAND_SERVICE_SYMBOLS if s in imported)
    assert hits == [], hits


def _call_order(func: object) -> list[str]:
    """按源码行序取出方法体里的**方法调用名**序列。

    只取 `foo.bar(...)` 的 `bar` 与 `bar(...)` 的 `bar`；这已足够表达
    「A 在 B 之前被调用」这类顺序判据，也不会因为参数里嵌套表达式而错序
    （`ast` 的 `lineno` 就是调用点所在行）。
    """
    src = inspect.getsource(func)  # type: ignore[arg-type]
    lines = src.splitlines()
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    cut = min(indents) if indents else 0
    tree = ast.parse("\n".join(l[cut:] if len(l) >= cut else l for l in lines))
    calls: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                calls.append((node.lineno, node.col_offset, node.func.attr))
            elif isinstance(node.func, ast.Name):
                calls.append((node.lineno, node.col_offset, node.func.id))
    return [name for _l, _c, name in sorted(calls)]


_FREEZE_ORDER = (
    "assert_can_initiate_request",   # ① authorization-first
    "build_request_freeze",          # ② 从已通过门的三行冻结
    "create_forcesave_request_with_shell",  # ③ 同事务落 request + shell
    "assert_dispatchable",           # ④ 落库后自证「零 application」
)


def test_freeze_and_persist_calls_the_four_steps_in_order() -> None:
    """AC 4.1 的顺序判据：授权 → 冻结 → 落库 → 自证，且**每一步都在**。

    🔴 这条是「先落库再调 Command Service」在本模块能给到的最强判据。
    Task 24 会在拿到凭据后才签 JWT/调 OO；而凭据只能由 ④ 通过后产生。
    没有这条时，把 ① 挪到 ③ 之后（先落库再授权）不会有任何测试变红 ——
    happy path 两种顺序结果完全相同。

    同时它也覆盖「④ 被整条删掉」：`assert_dispatchable` 在 happy path 恒通过，
    删掉它没有任何行为差异，只有本条会红。
    """
    order = _call_order(ra.RequestApplicationService.freeze_and_persist_request)
    positions = []
    for name in _FREEZE_ORDER:
        assert name in order, f"{name} 未被调用（AC 4.1 的四步缺一）"
        positions.append(order.index(name))
    assert positions == sorted(positions), list(zip(_FREEZE_ORDER, positions))


def test_call_order_helper_detects_a_swap() -> None:
    """反向自检：顺序提取器必须真的能看出顺序。

    否则 `_call_order` 退化成返回排序后的列表时，上一条断言恒真。
    """

    def _sample() -> None:
        b = dict()
        a = list()
        _ = (a, b)

    order = _call_order(_sample)
    assert order.index("dict") < order.index("list")


def test_correlate_delegates_to_the_repository_and_self_certifies() -> None:
    """`correlate` 必须委派仓储实现并做收敛自证 —— 不许自己再写一份 create-or-hit。"""
    order = _call_order(ra.RequestApplicationService.correlate)
    assert "correlate_durable_incoming" in order
    assert "_assert_convergence" in order
    assert order.index("correlate_durable_incoming") < order.index("_assert_convergence")


def test_claim_recovery_delegates_and_checks_shape_before_returning() -> None:
    order = _call_order(ra.RequestApplicationService.claim_recovery)
    assert "claim_recovery_case" in order
    assert "assert_recovery_claim_shape" in order
    assert order.index("claim_recovery_case") < order.index("assert_recovery_claim_shape")


def test_module_never_commits_the_transaction() -> None:
    """事务边界属 coordinator：本模块不得 `commit()`/`rollback()`。

    自己 commit 会把「request + shell 同一事务」变成两段 —— AC 4.1 的原子性正是
    靠调用方持有事务边界实现的。
    """
    src = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("commit", "rollback"):
                bad.append(f"L{node.lineno}:{node.func.attr}")
    assert bad == [], bad


def test_module_does_not_declare_an_application_key_field() -> None:
    """Property 64：`application_key` 只存在于 application。

    本模块是 operation 侧的服务层；它一旦持有/传递 `application_key`，下一步就是
    有人把它写进 operation 行。schema 级判据在 PG 守卫里，本条是服务层的一半。
    """
    src = MODULE_PATH.read_text(encoding="utf-8")
    stripped = _strip_comments_and_docstrings(src)
    assert "application_key" not in stripped, "服务层出现 application_key 字面量"


def _strip_comments_and_docstrings(src: str) -> str:
    """剥注释与 docstring 后的源码（用于「代码里不得出现 X」这类判据）。

    🔴 不剥的话，本文件与被测模块的**解释性文字**里出现的 `application_key`
    会让判据恒红；反过来只做朴素 `#` 切分会把字符串里的 `#` 误伤。这里用 AST
    定位 docstring + `tokenize` 去注释，两者都不猜。
    """
    import io
    import tokenize

    out: list[str] = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        out.append(tok.string if tok.type != tokenize.STRING else '""')
    return " ".join(out)


def test_strip_helper_actually_removes_comments_and_strings() -> None:
    """反向自检：剥离函数必须真的剥掉，否则上一条判据恒绿。

    「守卫依赖的辅助函数是否正确」必须单独证明 —— 若 `_strip_comments_and_docstrings`
    退化成 `return ""`，上一条断言恒真而没有任何判据会红。
    """
    sample = 'x = 1  # application_key here\ny = "application_key"\n'
    stripped = _strip_comments_and_docstrings(sample)
    assert "application_key" not in stripped
    # 同时必须保留真实代码标识符，否则它剥得太多（也是一种缺陷）
    assert "x" in stripped and "y" in stripped
    assert "application_key" in _strip_comments_and_docstrings("application_key = 1")


# ═══════════════════════════════════════════════════════════════════════════
# 六、`__all__` 与消费面自洽
# ═══════════════════════════════════════════════════════════════════════════


def test_all_names_exist() -> None:
    """`__all__` 里的每个名字都真的存在。

    Task 22 修过同一形态的缺陷：`__all__` 列了两个不存在的名字，`import *` 直接
    AttributeError，而按名字 grep「这条拒绝实现了吗」会得到**假阳性**。
    """
    missing = [n for n in ra.__all__ if not hasattr(ra, n)]
    assert missing == [], missing


def test_service_exposes_both_split_and_combined_read_entries() -> None:
    """两段式与合一入口都必须在。

    只留合一入口时，Task 27 的 resolve 需要在「授权后、canonicalize 前」插入 fence
    比对，于是它会绕过本模块自己拼一遍顺序 —— 那正是本模块要消灭的东西。
    """
    for name in (
        "authorize_operation_scope",
        "canonicalize_authorized",
        "read_operation",
        "freeze_and_persist_request",
        "correlate",
        "claim_recovery",
        "retry_eligibility",
    ):
        assert callable(getattr(ra.RequestApplicationService, name)), name
