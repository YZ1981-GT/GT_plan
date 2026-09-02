# -*- coding: utf-8 -*-
"""callback delivery 去重、request-first correlation、durable 归属与 recovery case。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 22
Requirements: 4.3, 4.9, 4.10, 5.1~5.8, 5.11, 5.12, 10.2, 10.3, 10.6~10.9
Properties: **P17** / **P18** / **P19** / **P44** / **P45** / **P63** / **P64**

本模块是 Task 22 的第三段。前两段已在磁盘上，职责边界不重叠：

* :mod:`callback_route` —— claim/URL/room 绑定校验（durable 前的第一道门）；
* :mod:`callback_download` —— allowlist/DNS/重定向/超时/流式上限（durable 前的第二道门）；
* **本模块** —— delivery 去重、归属真值表、request-first correlation、recovery case。

═══ 一、为什么归属规则要写成**数据**而不是散落的 if ═══

Requirement 5.4 的归属规则是一张按 `(state, durable_at, application, recovery, request)`
取值的真值表，而 V151 已经用 5 条 CHECK + 2 个 trigger 把它锁在库里。同一张表若在
Python 侧再用一串 `if` 复述一遍，就有两个后果：

1. 两侧漂移时**没有任何判据**能发现（两边都"自洽"）；
2. 守卫只能逐条手写场景，漏掉哪一行谁也不知道 —— 而漏掉的恰恰是禁止行。

所以这里把它写成 :data:`DELIVERY_OWNERSHIP_TRUTH_TABLE`：每行显式带
:attr:`DeliveryOwnershipRow.db_constraint`，即"这一行由库里哪条约束兜底"。PG 守卫
遍历这张表，对 `allowed` 行断言真能插入，对 `forbidden` 行断言真被拒**且拒它的正是
声明的那条约束**。于是"表漂移"与"约束被删"都会打红，而不是只有其中一种。

:func:`classify_delivery_ownership` 是同一张表的纯函数投影，供 durable 之前的服务层
自证（库那道锁只在 flush 时才响，服务层需要在写之前就知道自己算出来的组合合法）。

═══ 二、request-first 的结构性落点 ═══

Requirement 4.3 禁止"先按 incoming hash 命中旧 application 再读 request"。要让这条
禁令**不可能**被悄悄违反，本模块把归组决策拆成两个签名互不兼容的阶段：

* :func:`plan_correlation` —— 在**下载之前**决定走哪条路。它的入参里**没有**任何
  incoming 字节/digest 字段，所以"先用 incoming 命中 application"在这一阶段连表达
  能力都没有；
* :meth:`CallbackDeliveryService._resolve_durable` —— 只在 sealing 成 durable **之后**
  执行，且入口第一句就是 :meth:`CallbackStageJournal.assert_correlation_precondition`。

第二条不是注释级约定：journal 是**真实执行轨迹**，`sealed_durable` 没有落进 journal
时它直接抛 :class:`CallbackStageOrderError`。把 correlation 挪到 sealing 之前的变异会
在运行期炸掉，而不是只让某条断言的措辞不再成立。

═══ 三、Task 4 实证如何约束 delivery 去重 ═══

`evidence/task4-oo94-multiuser-callback/callbacks.jsonl` 的实测（15 条 callback，
status ∈ {1,2,4,6}）给了三条硬事实：

1. **同一 `userdata` 被 OO 原样回显两次**（`req-001-initiated-by-alice` 出现在
   phase1#3 与 phase1#9），两次产出的 artifact sha256 不同 ⇒ `userdata` 绝不可作幂等键；
2. 每次投递的 `url` 都带互不相同的 cache 路径段与 `md5=` 参数
   （`..._6785/` vs `..._6104/`）⇒ payload 本身足以区分"不同投递"与"同一投递的网络重试"；
3. status 6 的 `users` 只含最后编辑者（`['bob']` 而内容含 alice 的编辑）⇒
   `oo_users_digest` 只能是审计信号，contributor 置信度永远不是 `exact`。

因此 delivery discriminator = 规范化 payload（**剔除 `token`**）的 digest。剔 token 有
两个理由：它是凭证（Requirement 10.7 不得落库），且 OO 重投时可能重签，含它会把重试
误判成新投递。方向性也要说清：多算一行 delivery 只是多留一份证据（application 仍由
frozen key 收敛成一个）；少算一行才会**丢证据**，所以宁可多分不可少分。

═══ 四、不做的事 ═══

* **不发 HTTP**、不签 token、不建 room/participant —— 分别属 Task 24/25/28；
* **不做 extract/merge/apply** —— 属 Task 26；本模块到"application 已创建/命中"为止；
* **不实现 close-intent 仲裁** —— 属 Task 24；本模块只**消费** room 里已存在的唯一
  open close-capture request（status=2 无 userdata 的第一优先级）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Final, Mapping, Sequence

import sqlalchemy as sa

from app.models.workpaper_sync_models import (
    WorkpaperCallbackDelivery,
    WorkpaperCallbackRecoveryCase,
    WorkpaperContentApplication,
    WorkpaperForcesaveRequest,
    WorkpaperOoRoom,
    WorkpaperSyncOperation,
)
from app.services.workpaper_sync.artifacts import (
    CanonicalArtifactRepository,
    SealedIncoming,
)
from app.services.workpaper_sync.callback_download import (
    CallbackDownloadError,
    CallbackDownloadPolicy,
    CallbackDownloadTransport,
    download_to_staging,
)
from app.services.workpaper_sync.callback_route import (
    CallbackRouteClaim,
    RoomRouteFacts,
    verify_callback_route,
)
from app.services.workpaper_sync.models import (
    ActorType,
    ArtifactKind,
    ArtifactState,
    ContributorConfidence,
    CorrelationResult,
    DeliveryOwnershipError,
    DeliveryState,
    QuarantinedIncomingError,
    RecoveryReason,
    RequestKind,
    SyncDomainError,
    compute_delivery_key,
)
from app.services.workpaper_sync.oo_contract import (
    CallbackContract,
    CallbackStatusRule,
    Presence,
    load_callback_contract,
    normalize_callback_status,
)
from app.services.workpaper_sync.repository import (
    CorrelationOutcome,
    WorkpaperSyncRepository,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常：每条拒绝一个类型
# ═══════════════════════════════════════════════════════════════════════════


class CallbackDeliveryDomainError(SyncDomainError):
    """delivery/correlation 域基类。"""

    error_code = "callback_delivery_invalid"


class CallbackStatusUnsupportedError(CallbackDeliveryDomainError):
    """status 未登记在真值表内（Requirement 4.9：fail visible，不猜最近似 status）。"""

    error_code = "callback_status_unsupported"


class CallbackPayloadShapeError(CallbackDeliveryDomainError):
    """payload 的 `url`/`userdata` 出现与真值表 presence 声明矛盾的形态。

    🔴 与 :class:`CallbackStatusUnsupportedError` 分型：前者是"这个 status 我不认识"，
    本条是"status 认识，但它声称 `url_present=always` 而 payload 没给 url"。合并成一
    个类型时，删掉 presence 判据会被 status 判据遮蔽而判 GREEN。
    """

    error_code = "callback_payload_shape_invalid"


class CallbackActionNotWritableError(CallbackDeliveryDomainError):
    """claim 的 `act` 只允许通知，却收到需要下载/可产生 application 的 status。"""

    error_code = "callback_action_not_writable"


class RequestBindingError(CallbackDeliveryDomainError):
    """`userdata` 指向的 frozen request 不存在 / 跨 room / 跨 generation。"""

    error_code = "callback_request_binding_failed"


class RequestFrozenIdentityError(CallbackDeliveryDomainError):
    """已绑定 request 的冻结 identity 与 room 当前 approved bundle/authority 不一致。

    与 :class:`RequestBindingError` 分型：前者是"找不到/不属于本 room"，本条是"找到了
    但它冻结的 bundle/authority 已经不是 room 现在批准的那个"。
    """

    error_code = "callback_request_identity_drift"


class RequestFenceStaleError(CallbackDeliveryDomainError):
    """request 冻结的 write fence / permission epoch 已陈旧（AC 4.7 / 10.4）。"""

    error_code = "callback_request_fence_stale"


class FrozenIdentityAmbiguousError(CallbackDeliveryDomainError):
    """按 frozen identity 去重时候选不唯一，或存在更高 sequence 的**不同** canonical application。"""

    error_code = "callback_frozen_identity_ambiguous"


class ContributorAttributionUnsafeError(CallbackDeliveryDomainError):
    """contributor 含只读/被撤销 writer，或归属无法安全判定（Requirement 10.3 / P44）。"""

    error_code = "callback_contributor_attribution_unsafe"


class QuarantineOperationForbiddenError(QuarantinedIncomingError):
    """quarantined incoming 上执行了 download-only/expire/retention 之外的操作。

    刻意继承 Task 10 的 :class:`QuarantinedIncomingError`：上层（engine 入口、
    application FK 前置）已经在 catch 那个类型，新增一个平级类型会让它们漏网。
    """

    error_code = "quarantined_operation_forbidden"


class CallbackStageOrderError(CallbackDeliveryDomainError):
    """执行轨迹违反不可交换顺序（例如 sealing 成 durable 之前就去 correlate）。"""

    error_code = "callback_stage_order_violation"


class RecoveryClaimAuthorizationError(CallbackDeliveryDomainError):
    """claim 的 authorization-first 重验失败（claim 前三实体保持为 0）。"""

    error_code = "recovery_claim_authorization_failed"


# ═══════════════════════════════════════════════════════════════════════════
# 1. payload 投影
# ═══════════════════════════════════════════════════════════════════════════

#: 计算 delivery discriminator 时**剔除**的 payload 字段。
#:
#: `token` 是 OO 自签的 body JWT：它是凭证（Requirement 10.7 禁止落库/落日志），且 OO
#: 重投时可能重签 —— 含它会把"同一投递的网络重试"算成两条 delivery，白丢一次去重。
_DISCRIMINATOR_EXCLUDED_FIELDS: Final[frozenset[str]] = frozenset({"token"})


@dataclass(frozen=True)
class CallbackPayload:
    """OO callback body 的**投影**（原文不落库，只留 digest）。

    刻意保留 `raw` 供 discriminator 计算，但 :meth:`canonical_digest` 会剔除
    :data:`_DISCRIMINATOR_EXCLUDED_FIELDS`，因此 token 既不进 digest 也不进任何行。
    """

    status: int
    key: object
    url: str | None
    userdata: str | None
    users: tuple[str, ...]
    contributors: tuple[str, ...]
    actions: tuple[Mapping[str, Any], ...]
    notmodified: bool
    forcesavetype: int | None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_mapping(cls, body: Mapping[str, Any], *, contract: CallbackContract) -> "CallbackPayload":
        """从不可信 JSON 投影。

        `status` 走 :func:`normalize_callback_status`：它**拒绝**把 `"6"` 强转成 6
        （Task 4 契约 `unknown_status_policy.mode=fail_visible`）。返回 None 时抛
        :class:`CallbackStatusUnsupportedError`，绝不猜最近似 status。
        """
        if not isinstance(body, Mapping):
            raise CallbackPayloadShapeError(
                f"callback body 必须是 JSON object，实得 {type(body).__name__}"
            )
        status = normalize_callback_status(body.get("status"))
        if status is None:
            raise CallbackStatusUnsupportedError(
                f"callback status={body.get('status')!r} 未登记在真值表内 —— "
                "契约要求 fail visible（不得按最近似 status 猜测处理，也不得静默 error=0）"
            )
        if status not in contract.statuses:
            raise CallbackStatusUnsupportedError(
                f"callback status={status} 不在契约已登记状态 {list(contract.known_statuses)} 内"
            )
        url_raw = body.get("url")
        url = str(url_raw).strip() if isinstance(url_raw, str) and url_raw.strip() else None
        ud_raw = body.get("userdata")
        userdata = str(ud_raw).strip() if isinstance(ud_raw, str) and ud_raw.strip() else None
        users = tuple(
            str(u) for u in (body.get("users") or []) if isinstance(u, (str, int))
        )
        # Task 4 §3：`history.changes[].user` 才是全体贡献者（且含已被 drop 的用户），
        # `users` 只有最后编辑者。两者分别投影，绝不混成一个字段。
        contributors: list[str] = []
        history = body.get("history")
        if isinstance(history, Mapping):
            for change in history.get("changes") or []:
                if not isinstance(change, Mapping):
                    continue
                user = change.get("user")
                if isinstance(user, Mapping):
                    ident = user.get("id") or user.get("name")
                elif isinstance(user, (str, int)):
                    ident = user
                else:
                    ident = None
                if ident is not None and str(ident) not in contributors:
                    contributors.append(str(ident))
        actions = tuple(a for a in (body.get("actions") or []) if isinstance(a, Mapping))
        fst = body.get("forcesavetype")
        return cls(
            status=status,
            key=body.get("key"),
            url=url,
            userdata=userdata,
            users=users,
            contributors=tuple(contributors),
            actions=actions,
            notmodified=bool(body.get("notmodified") or False),
            forcesavetype=int(fst) if isinstance(fst, int) and not isinstance(fst, bool) else None,
            raw=dict(body),
        )

    def canonical_digest(self) -> str:
        """规范化 payload digest（剔 token；递归键排序；UTF-8）。"""
        scrubbed = {
            k: v for k, v in sorted(self.raw.items())
            if k not in _DISCRIMINATOR_EXCLUDED_FIELDS
        }
        blob = json.dumps(scrubbed, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def users_digest(self) -> str | None:
        """`users` 的审计 digest（**不是**作者依据 —— Task 4：只含最后编辑者）。"""
        if not self.users:
            return None
        return hashlib.sha256(
            ("oo-users:v1|" + ",".join(sorted(self.users))).encode("utf-8")
        ).hexdigest()

    def contributor_digest(self) -> str | None:
        """`history.changes[].user` 的审计 digest（含已被 drop 的用户）。"""
        if not self.contributors:
            return None
        return hashlib.sha256(
            ("oo-contributors:v1|" + ",".join(sorted(self.contributors))).encode("utf-8")
        ).hexdigest()

    @property
    def request_id(self) -> uuid.UUID | None:
        """`userdata` 携带的 frozen request id；不是 UUID 即视为无（并留 WARNING）。

        不抛：Task 4 实测 OO 原样回显任意 `userdata`，第三方/旧版本可能塞非 UUID 文本。
        把它当致命错误会让 durable 内容无法进入 recovery；正确处置是"当作无 userdata"，
        由归组规则决定去 recovery 还是 close-capture。
        """
        if self.userdata is None:
            return None
        try:
            return uuid.UUID(self.userdata)
        except (ValueError, AttributeError, TypeError):
            logger.warning("callback userdata 不是 UUID，按无 userdata 处理: %r", self.userdata)
            return None


def assert_payload_matches_status_rule(
    payload: CallbackPayload, rule: CallbackStatusRule
) -> None:
    """payload 形态必须与真值表的 presence 声明一致（Requirement 4.9）。"""
    if rule.url_present is Presence.always and not payload.url:
        raise CallbackPayloadShapeError(
            f"status={rule.status}（{rule.oo_name}）契约声明 url_present=always，"
            "但 payload 未给 url —— 缺 url 不得按「无内容」静默 ack"
        )
    if rule.url_present is Presence.never and payload.url:
        raise CallbackPayloadShapeError(
            f"status={rule.status}（{rule.oo_name}）契约声明 url_present=never，"
            f"却带了 url —— 不得下载未在真值表授权的内容"
        )
    if rule.userdata_present is Presence.never and payload.userdata:
        raise CallbackPayloadShapeError(
            f"status={rule.status}（{rule.oo_name}）契约声明 userdata_present=never，"
            "却带了 userdata —— 不得据此精确绑定 request"
        )
    if rule.download_required and not payload.url:
        raise CallbackPayloadShapeError(
            f"status={rule.status} 要求下载但 payload 无 url"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. delivery 去重
# ═══════════════════════════════════════════════════════════════════════════


def compute_delivery_discriminator(payload: CallbackPayload) -> str:
    """delivery discriminator：同一投递的网络重试相同，不同投递必然不同。

    成分固定为 `url + userdata + canonical payload digest`。三者都取自 payload：

    * `url` —— Task 4 实测每次投递的 cache 路径段与 `md5=` 参数互不相同；
    * `userdata` —— 同一 request 的 status 6/2 各自成行（真值表要求"各自留证据"）；
    * canonical digest —— 兜住"url 复用但 body 其余字段变化"的形态。

    🔴 显式成分里**不含** room/generation/status：那三项已经在
    :func:`compute_delivery_key` 里，在这里重复只会让"discriminator 被削空"这件事被
    外层成分掩盖。

    ⚠️ 一处必须说清的实况：`canonical_digest()` 摘的是**整个** raw body，而 `status`
    就在 body 里 —— 所以 status 事实上**经由 digest**进入了 discriminator。外层
    `compute_delivery_key(callback_status=...)` 因此是纵深防御而非唯一来源。后果有两条：
    (a) 任何「只改 status」的场景都无法单独观测外层那一项，锁它只能用接线等值判据
    （见 `test_build_delivery_key_wires_the_payload_status_through`）；
    (b) 若将来把 `status` 加进 :data:`_DISCRIMINATOR_EXCLUDED_FIELDS`，外层那一项就
    从冗余变成唯一来源，届时删掉它会真的让 status 6/2 折叠成一行。
    """
    return hashlib.sha256(
        "|".join(
            [
                "callback-delivery-discriminator:v1",
                payload.url or "",
                payload.userdata or "",
                payload.canonical_digest(),
            ]
        ).encode("utf-8")
    ).hexdigest()


def build_delivery_key(
    *, room_id: uuid.UUID, generation: int, payload: CallbackPayload
) -> str:
    """`delivery_key = sha256(room|generation|status|discriminator)`（Requirement 5.4）。"""
    return compute_delivery_key(
        room_id=room_id,
        generation=generation,
        callback_status=payload.status,
        discriminator=compute_delivery_discriminator(payload),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 归属真值表（Requirement 5.4 / Property 18）
# ═══════════════════════════════════════════════════════════════════════════


class OwnershipVerdict(str, Enum):
    allowed = "allowed"
    forbidden = "forbidden"


class CorrelationFamily(str, Enum):
    """`correlation_result` 在归属约束里的**三值**投影。

    为什么不用 5 个枚举值直接进真值表：`ck_wpcd_ambiguous_zero_entities` 只区分
    `unmatched/ambiguous` 与"其余"，按 5 值展开会让表里出现三行完全等价的
    `correlated` 行 —— 冗余行不增加判据，却让"某一行被漏写"更难发现。
    """

    absent = "absent"
    correlated = "correlated"
    unresolved = "unresolved"


def correlation_family(
    value: CorrelationResult | str | None,
) -> CorrelationFamily:
    """把 `correlation_result` 投影成 :class:`CorrelationFamily`。"""
    if value is None:
        return CorrelationFamily.absent
    cr = value if isinstance(value, CorrelationResult) else CorrelationResult(value)
    if cr in (CorrelationResult.unmatched, CorrelationResult.ambiguous):
        return CorrelationFamily.unresolved
    return CorrelationFamily.correlated


@dataclass(frozen=True)
class DeliveryOwnershipRow:
    """归属真值表的一行。

    :param db_constraint: 兜住这一行的 V151 约束/trigger 名。`allowed` 行填"哪条约束
        必须**放行**它"，`forbidden` 行填"哪条约束必须**拒绝**它"。PG 守卫据此断言拒绝
        原因确实来自声明的那条约束 —— 否则"被另一条约束偶然挡住"会伪装成守卫有效。

    🔴 谓词维度必须**足以唯一定位**一行。少一维就会出现"两行谓词相同、裁决相反"，
    于是先声明的那行永久遮蔽后声明的那行（本 spec 已为"两个拒绝共用一个 error_code
    让前者不可达"付过一次代价）。:data:`DELIVERY_OWNERSHIP_TRUTH_TABLE` 的导入期自检
    会拒绝重复谓词。

    🔴 每行还必须**只**违反自己声明的那条约束。durable + 双 owner 这类组合会同时触发
    `ck_wpcd_no_double_owner` 与 `ck_wpcd_durable_exactly_one_owner`，两者谁先报由 PG
    内部顺序决定 ⇒ 无法归因，故这类"合取组合"不入表（各自的正交事实由 T09/T11 覆盖）。
    """

    row_id: str
    state: DeliveryState
    durable_at_is_set: bool
    has_application: bool
    has_recovery: bool
    has_request: bool
    has_incoming: bool
    family: CorrelationFamily
    verdict: OwnershipVerdict
    db_constraint: str
    rationale: str

    @property
    def predicate(self) -> tuple[object, ...]:
        return (
            self.state,
            self.durable_at_is_set,
            self.has_application,
            self.has_recovery,
            self.has_request,
            self.has_incoming,
            self.family,
        )


#: 归属真值表。**唯一真源**在 V151；这里是它的可遍历投影。
#:
#: 三条不可动摇的语义（Task 22 正文逐字要求）：
#: 1. `durable_at IS NULL` 的 received/downloading/rejected/error 可零 owner，但**禁双 owner**；
#: 2. durable fact 存在 ⇒ 恰属 application 或 recovery 之一，post-durable error **保留** owner；
#: 3. request 与 application **可同时存在** —— 不做 XOR。
DELIVERY_OWNERSHIP_TRUTH_TABLE: Final[tuple[DeliveryOwnershipRow, ...]] = (
    # ── durable_at IS NULL：可零 owner，可保留已精确绑定的 request ──────────
    DeliveryOwnershipRow(
        "T01", DeliveryState.received, False, False, False, False, False,
        CorrelationFamily.absent,
        OwnershipVerdict.allowed, "ck_wpcd_durable_exactly_one_owner",
        "刚收到、尚未归组：零 owner 合法（该 CHECK 以 durable_at IS NULL 短路放行）",
    ),
    DeliveryOwnershipRow(
        "T02", DeliveryState.received, False, False, False, True, False,
        CorrelationFamily.absent,
        OwnershipVerdict.allowed, "ck_wpcd_durable_exactly_one_owner",
        "request-first 已精确绑定 frozen request，但还没 durable ⇒ 保留 request、零 owner",
    ),
    DeliveryOwnershipRow(
        "T03", DeliveryState.downloading, False, False, False, True, False,
        CorrelationFamily.absent,
        OwnershipVerdict.allowed, "ck_wpcd_durable_exactly_one_owner",
        "下载中：同上",
    ),
    DeliveryOwnershipRow(
        "T04", DeliveryState.rejected, False, False, False, True, False,
        CorrelationFamily.absent,
        OwnershipVerdict.allowed, "ck_wpcd_durable_exactly_one_owner",
        "pre-durable 鉴权/下载/OOXML 失败：零 application/recovery owner（AC 5.7）",
    ),
    DeliveryOwnershipRow(
        "T05", DeliveryState.error, False, False, False, True, False,
        CorrelationFamily.absent,
        OwnershipVerdict.allowed, "ck_wpcd_durable_exactly_one_owner",
        "pre-durable error：同上，不得伪造 recovery/application",
    ),
    # ── durable fact 存在：恰属 application 或 recovery 之一 ────────────────
    DeliveryOwnershipRow(
        "T06", DeliveryState.durable, True, True, False, True, True,
        CorrelationFamily.correlated,
        OwnershipVerdict.allowed, "ck_wpcd_durable_exactly_one_owner",
        "correlated：application 非空 + recovery 空 + request 同时存在"
        "（request/application 不做 XOR —— 这是本行的核心判据）",
    ),
    DeliveryOwnershipRow(
        "T07", DeliveryState.acknowledged, True, True, False, False, True,
        CorrelationFamily.correlated,
        OwnershipVerdict.allowed, "ck_wpcd_durable_exactly_one_owner",
        "status=2 无 userdata 走 frozen-identity 去重：application 非空而 request 可空",
    ),
    DeliveryOwnershipRow(
        "T08", DeliveryState.unmatched, True, False, True, False, True,
        CorrelationFamily.unresolved,
        OwnershipVerdict.allowed, "ck_wpcd_unmatched_zero_entities",
        "unmatched：recovery 非空且 request/application/operation 全空",
    ),
    # ── 禁止行。每行只违反自己声明的那条约束（合取组合不入表，见类 docstring）──
    DeliveryOwnershipRow(
        "T09", DeliveryState.received, False, True, True, False, False,
        CorrelationFamily.absent,
        OwnershipVerdict.forbidden, "ck_wpcd_no_double_owner",
        "双 owner：任何阶段都禁止。刻意取 pre-durable ——"
        " durable + 双 owner 会同时触发 XOR 那条，无法归因",
    ),
    DeliveryOwnershipRow(
        "T10", DeliveryState.durable, True, False, False, True, True,
        CorrelationFamily.correlated,
        OwnershipVerdict.forbidden, "ck_wpcd_durable_exactly_one_owner",
        "durable 却零 owner ⇒ 无所有者死路，禁止（只有 request 不算归组）",
    ),
    DeliveryOwnershipRow(
        "T11", DeliveryState.durable, False, True, False, True, True,
        CorrelationFamily.correlated,
        OwnershipVerdict.forbidden, "ck_wpcd_durable_state_requires_fact",
        "state=durable 但 durable_at 为空 ⇒ 把泛化 terminal 当 durable，禁止",
    ),
    DeliveryOwnershipRow(
        "T12", DeliveryState.unmatched, True, False, True, True, True,
        CorrelationFamily.absent,
        OwnershipVerdict.forbidden, "ck_wpcd_unmatched_zero_entities",
        "unmatched 却留着 request ⇒ 违反「claim 前三实体为 0」。"
        "correlation_result 取 NULL 以短路 ambiguous 那条，保证只有本条约束会报",
    ),
    DeliveryOwnershipRow(
        "T13", DeliveryState.durable, True, True, False, True, True,
        CorrelationFamily.unresolved,
        OwnershipVerdict.forbidden, "ck_wpcd_ambiguous_zero_entities",
        "correlation_result ∈ {unmatched, ambiguous} 时禁止任何 request/application/operation",
    ),
    DeliveryOwnershipRow(
        "T14", DeliveryState.durable, True, True, False, False, False,
        CorrelationFamily.correlated,
        OwnershipVerdict.forbidden, "ck_wpcd_durable_requires_incoming",
        "durable 却没绑 incoming artifact ⇒ pointer 指向缺失字节，禁止",
    ),
)


def _assert_truth_table_unshadowed() -> None:
    """导入期自检：谓词不得重复，否则后声明的行永久不可达（判据静默丢失）。"""
    seen: dict[tuple[object, ...], str] = {}
    for row in DELIVERY_OWNERSHIP_TRUTH_TABLE:
        prior = seen.get(row.predicate)
        if prior is not None:
            raise DeliveryOwnershipError(
                f"归属真值表 {row.row_id} 与 {prior} 谓词完全相同 —— "
                "后声明的那行永远不会被 classify_delivery_ownership 命中，判据静默丢失"
            )
        seen[row.predicate] = row.row_id


_assert_truth_table_unshadowed()


def classify_delivery_ownership(
    *,
    state: DeliveryState | str,
    durable_at_is_set: bool,
    application_id: uuid.UUID | None,
    callback_recovery_case_id: uuid.UUID | None,
    forcesave_request_id: uuid.UUID | None = None,
    incoming_artifact_id: uuid.UUID | None = None,
    correlation_result: CorrelationResult | str | None = None,
) -> DeliveryOwnershipRow:
    """把一个归属组合投影到真值表的某一行；找不到匹配行即抛。

    与 :func:`app.services.workpaper_sync.models.assert_delivery_ownership` 的分工：
    那个函数是**规则**（三条断言），本函数是**表**（可遍历、带约束归属）。服务层在
    写库之前先过这里，拿到的不只是"合法/非法"，还有"这一行由哪条 DB 约束兜底"，
    从而能在诊断里指出真正的锁在哪。
    """
    st = state if isinstance(state, DeliveryState) else DeliveryState(state)
    probe = (
        st,
        bool(durable_at_is_set),
        application_id is not None,
        callback_recovery_case_id is not None,
        forcesave_request_id is not None,
        incoming_artifact_id is not None,
        correlation_family(correlation_result),
    )
    for row in DELIVERY_OWNERSHIP_TRUTH_TABLE:
        if row.predicate == probe:
            if row.verdict is OwnershipVerdict.forbidden:
                raise DeliveryOwnershipError(
                    f"delivery 归属组合 {row.row_id} 被真值表禁止：{row.rationale}"
                    f"（DB 侧由 {row.db_constraint} 兜底）"
                )
            return row
    # 表未覆盖的组合：先用规则函数判一次；规则放行说明表缺行（守卫缺陷），必须可见。
    from app.services.workpaper_sync.models import assert_delivery_ownership

    assert_delivery_ownership(
        state=st,
        durable_at_is_set=durable_at_is_set,
        application_id=application_id,
        callback_recovery_case_id=callback_recovery_case_id,
        forcesave_request_id=forcesave_request_id,
    )
    # 🔴 诊断文本只用 `probe` 里已算好的布尔量。原实现引用了三个从未定义的名字
    # （`has_app` / `has_rec` / `has_req`），于是「表缺行」这条路径抛的是 NameError
    # 而不是 DeliveryOwnershipError —— 调用方 `except SyncDomainError` 抓不住它，
    # 表缺行会以 500 的形态出现在一个与归属毫无关系的位置。
    raise DeliveryOwnershipError(
        f"归属组合 (state={st.value}, durable={probe[1]}, app={probe[2]}, "
        f"recovery={probe[3]}, request={probe[4]}, incoming={probe[5]}, "
        f"family={probe[6].value}) 未被真值表覆盖 —— 真值表缺行即判据缺失"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. quarantined incoming 的允许操作
# ═══════════════════════════════════════════════════════════════════════════

#: quarantined incoming 的**全部**允许操作（Requirement 5.6）。
QUARANTINE_ALLOWED_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"download_only", "expire", "retention"}
)

#: 明确禁止的操作。写成显式清单而不是"除允许之外全部"，是为了让守卫能逐条驱动 ——
#: 只写 allowlist 时，守卫作者容易漏掉某个真实存在的入口（例如 `rematerialize`）。
QUARANTINE_FORBIDDEN_OPERATIONS: Final[tuple[str, ...]] = (
    "release",
    "promote_durable",
    "publish",
    "application",
    "extract",
    "merge",
    "retry",
    "rematerialize",
    "resolver_substrate",
)


def assert_quarantine_operation_allowed(operation: str) -> None:
    """quarantined incoming 上只允许 download-only / expire / retention。"""
    op = str(operation or "").strip()
    if op in QUARANTINE_ALLOWED_OPERATIONS:
        return
    raise QuarantineOperationForbiddenError(
        f"quarantined incoming 不允许操作 {op!r} —— 只允许 "
        f"{sorted(QUARANTINE_ALLOWED_OPERATIONS)}；"
        "永不得 release/转 durable/创建 application/进入 engine/作为 result 来源"
        "（Requirement 5.6）"
    )


def assert_incoming_admissible_for_application(sealed: SealedIncoming) -> None:
    """application/engine 入口的 fail-closed 断言（第一层，纯内存）。

    与 :meth:`WorkpaperSyncRepository.assert_incoming_durable`（第二层，读 DB 行）和
    `trg_wpca_identity`（第三层，库内 trigger）构成三层。三层都要有，理由是它们各自
    覆盖不同的绕过路径：内存对象直传 engine / 用 artifact id 绕过服务层 / 直接写 SQL。
    """
    if sealed.state is ArtifactState.quarantined:
        assert_quarantine_operation_allowed("application")
    sealed.raise_if_not_durable()


# ═══════════════════════════════════════════════════════════════════════════
# 5. 归组决策（**下载之前**，入参不含任何 incoming 身份）
# ═══════════════════════════════════════════════════════════════════════════


class CorrelationMode(str, Enum):
    """归组路径。`frozen_identity` 是**延后**决策：durable 之后才能查。"""

    request = "request"
    close_capture = "close_capture"
    frozen_identity = "frozen_identity"
    recovery = "recovery"
    no_content = "no_content"


@dataclass(frozen=True)
class CorrelationPlan:
    """下载前的归组计划。

    🔴 字段与入参里都**没有** incoming sha / artifact id / application key ——
    Requirement 4.3 禁止"先按 incoming hash 命中旧 application 再读 request"，这里用
    "连表达能力都不给"来落实，而不是靠注释约定。
    """

    mode: CorrelationMode
    request_id: uuid.UUID | None
    recovery_reason: RecoveryReason | None
    download_required: bool
    application_allowed: bool
    rationale: str


def plan_correlation(
    *,
    payload: CallbackPayload,
    rule: CallbackStatusRule,
    claim: CallbackRouteClaim,
    eligible_close_capture_ids: Sequence[uuid.UUID] = (),
) -> CorrelationPlan:
    """按 Task 4 真值表决定归组路径（纯函数，无 IO）。

    固定优先级：

    1. **有 `userdata`** ⇒ `request`（request-first，契约 `userdata_rules.present`）；
    2. status=2 无 userdata ⇒ 唯一 open close-capture ⇒ `close_capture`；
       零个 ⇒ `frozen_identity`（延后到 durable 后按 frozen identity 去重）；
       多个 ⇒ `recovery(ambiguous_close)`；
    3. status=6 无 userdata ⇒ `recovery(missing_request)` —— **不得猜 base**；
    4. 不需要下载的 status ⇒ `no_content`。
    """
    if not rule.download_required:
        return CorrelationPlan(
            mode=CorrelationMode.no_content,
            request_id=None,
            recovery_reason=None,
            download_required=False,
            application_allowed=False,
            rationale=(
                f"status={rule.status}（{rule.oo_name}）真值表声明无需下载"
                f"（delivery_terminal={rule.delivery_terminal_state}）"
            ),
        )
    if not claim.allows_content_write:
        raise CallbackActionNotWritableError(
            f"claim.act={claim.action!r} 只允许通知类处理，却收到需要下载的 "
            f"status={rule.status} —— 不得用 notify 凭证写内容"
        )
    request_id = payload.request_id
    if request_id is not None:
        return CorrelationPlan(
            mode=CorrelationMode.request,
            request_id=request_id,
            recovery_reason=None,
            download_required=True,
            application_allowed=rule.application_allowed,
            rationale="payload 带 userdata ⇒ request-first：先精确绑定并校验该 frozen request",
        )
    unique = list(dict.fromkeys(eligible_close_capture_ids))
    if rule.status == 2:
        if len(unique) == 1:
            return CorrelationPlan(
                mode=CorrelationMode.close_capture,
                request_id=unique[0],
                recovery_reason=None,
                download_required=True,
                application_allowed=rule.application_allowed,
                rationale="status=2 无 userdata ⇒ 优先绑定 generation 内唯一 open close-capture",
            )
        if len(unique) == 0:
            return CorrelationPlan(
                mode=CorrelationMode.frozen_identity,
                request_id=None,
                recovery_reason=None,
                download_required=True,
                application_allowed=rule.application_allowed,
                rationale=(
                    "status=2 无 userdata 且无 eligible close-capture ⇒ 延后到 durable 后"
                    "按 frozen identity 唯一性去重；不唯一即 recovery"
                ),
            )
        return CorrelationPlan(
            mode=CorrelationMode.recovery,
            request_id=None,
            recovery_reason=RecoveryReason.ambiguous_close,
            download_required=True,
            application_allowed=rule.application_allowed,
            rationale=(
                f"status=2 无 userdata 但有 {len(unique)} 个 open close-capture ⇒ 候选不唯一，"
                "durable 后建零 operation recovery case"
            ),
        )
    return CorrelationPlan(
        mode=CorrelationMode.recovery,
        request_id=None,
        recovery_reason=RecoveryReason.missing_request,
        download_required=True,
        application_allowed=rule.application_allowed,
        rationale=(
            f"status={rule.status} 无 userdata ⇒ 不得猜 base（契约 "
            "userdata_rules.absent.status_6）；durable 后建零 operation recovery case"
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. 执行轨迹（真实顺序判据，不是注释）
# ═══════════════════════════════════════════════════════════════════════════


class CallbackStage(str, Enum):
    route_verified = "route_verified"
    status_resolved = "status_resolved"
    plan_decided = "plan_decided"
    delivery_recorded = "delivery_recorded"
    request_bound = "request_bound"
    download_started = "download_started"
    download_finished = "download_finished"
    sealed_durable = "sealed_durable"
    sealed_quarantined = "sealed_quarantined"
    correlated = "correlated"
    recovery_case_created = "recovery_case_created"
    responded = "responded"


@dataclass
class CallbackStageJournal:
    """一次 callback 处理的**有序**阶段轨迹。

    存在的理由是把"不可交换顺序"变成运行期事实：
    :meth:`assert_correlation_precondition` 在 correlate 之前无条件调用，
    `sealed_durable` 不在轨迹里就直接抛。于是"把 application key 计算挪到 sealing 之前"
    这类变异会在**运行时**炸掉，而不是仅让某条断言的措辞不再成立。
    """

    entries: list[tuple[CallbackStage, str]] = field(default_factory=list)

    def record(self, stage: CallbackStage, detail: str = "") -> None:
        self.entries.append((stage, detail))

    @property
    def order(self) -> tuple[CallbackStage, ...]:
        return tuple(s for s, _ in self.entries)

    def has(self, stage: CallbackStage) -> bool:
        return stage in self.order

    def index_of(self, stage: CallbackStage) -> int:
        return self.order.index(stage)

    def assert_correlation_precondition(self) -> None:
        """correlate（= 唯一计算 application key 的地方）的前置轨迹断言。"""
        if self.has(CallbackStage.sealed_quarantined):
            raise QuarantineOperationForbiddenError(
                "本次 callback 已 sealing 为 quarantined —— 不得进入 correlation/application"
            )
        if not self.has(CallbackStage.sealed_durable):
            raise CallbackStageOrderError(
                "correlation 必须在 incoming 完整下载、校验并 sealing 为 durable **之后**"
                f"执行；当前轨迹={[s.value for s in self.order]}（Requirement 4.3/5.5："
                "application_key 只能在 durable fact 之后计算，不得由 incoming 或 "
                "operation 反猜）"
            )
        if not self.has(CallbackStage.route_verified):
            raise CallbackStageOrderError("correlation 前必须已完成 route claim 校验")

    def assert_request_first(self) -> None:
        """有精确绑定时，`request_bound` 必须早于 `download_started` 与 `correlated`。"""
        if not self.has(CallbackStage.request_bound):
            return
        bound = self.index_of(CallbackStage.request_bound)
        for later in (CallbackStage.download_started, CallbackStage.correlated):
            if self.has(later) and self.index_of(later) < bound:
                raise CallbackStageOrderError(
                    f"request-first 被破坏：{later.value} 早于 request_bound"
                )


# ═══════════════════════════════════════════════════════════════════════════
# 7. 结果
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CallbackHandleOutcome:
    """一次 callback 的处理结果。`response_error` 就是返回给 OO 的 `error` 值。

    pre-durable 失败 ⇒ 非零（OO 不重发，前端靠 operation 终态/timeout）；
    durable 之后的任何失败 ⇒ 0（返回非零等于静默丢件，Task 4 实测 OO 不重投）。
    """

    response_error: int
    delivery_id: uuid.UUID
    delivery_state: DeliveryState
    correlation_result: CorrelationResult | None
    plan: CorrelationPlan
    journal: CallbackStageJournal
    incoming_artifact_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    operation_id: uuid.UUID | None = None
    recovery_case_id: uuid.UUID | None = None
    quarantined_artifact_id: uuid.UUID | None = None
    error_code: str | None = None
    error_stage: str | None = None

    @property
    def durable(self) -> bool:
        return self.delivery_state in (
            DeliveryState.durable,
            DeliveryState.acknowledged,
            DeliveryState.unmatched,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. 服务
# ═══════════════════════════════════════════════════════════════════════════


class CallbackDeliveryService:
    """callback 的**唯一**业务入口；router 只做参数搬运。

    "router 只委派"的三条可验证形态：

    1. 校验/归组/去重/recovery 的实现全在服务侧，router 不得自己 `jwt.decode` 后比字段；
    2. :meth:`handle_callback` 的入参只有**原始传输层输入**（header/URL/body）与 room
       事实，没有任何"已判定"的语义参数（例如"这是不是 forcesave"）；
    3. 入参里没有 `participant_id`/`user_id` —— route 不承担作者语义（Task 4 §3）。
    """

    def __init__(
        self,
        repo: WorkpaperSyncRepository,
        *,
        artifacts: CanonicalArtifactRepository,
        download_policy: CallbackDownloadPolicy,
        transport: CallbackDownloadTransport,
        contract: CallbackContract | None = None,
    ) -> None:
        self._repo = repo
        self._artifacts = artifacts
        self._policy = download_policy
        self._transport = transport
        self._contract = contract or load_callback_contract()

    # ─────────────────────────────────────────────────────────────────
    # 8.1 room 事实
    # ─────────────────────────────────────────────────────────────────

    @property
    def contract(self) -> CallbackContract:
        return self._contract

    async def room_route_facts(self, room_id: uuid.UUID) -> RoomRouteFacts:
        """把 room 行投影成 :class:`RoomRouteFacts`（callback_route 不查库）。

        🔴 刻意**不加行锁**：它发生在 claim 校验**之前**（claim 必须与 room 行逐项比对，
        没有 room 事实就无法校验）。此处若用 `lock_room`，未鉴权请求就能让任意 room 行
        进入锁等待 —— 一个不需要凭证的阻塞面。写路径（`_bind_request` / correlation）
        自己会取锁。
        """
        room = (
            await self._repo.session.execute(
                sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room_id)
            )
        ).scalar_one_or_none()
        if room is None:
            raise RequestBindingError(f"room {room_id} 不存在")
        return RoomRouteFacts(
            room_id=room.id,
            generation=int(room.generation),
            doc_key=room.doc_key,
            wp_id=room.wp_id,
            entry_id=room.entry_id,
            write_fence_epoch=int(room.write_fence_epoch),
            accepts_callback=str(room.state) not in ("superseded", "closed"),
        )

    # ─────────────────────────────────────────────────────────────────
    # 8.2 主流程
    # ─────────────────────────────────────────────────────────────────

    async def handle_callback(
        self,
        *,
        authorization_header: str | None,
        callback_url: str,
        body: Mapping[str, Any],
        room_id: uuid.UUID,
        secret: str,
        expected_write_fence_epoch: int | None = None,
        journal: CallbackStageJournal | None = None,
    ) -> CallbackHandleOutcome:
        """全流程：route → 真值表 → delivery → request-first → 下载 → sealing → 归组。

        任何 pre-durable 失败都以非零 `response_error` 返回（并留 delivery 痕迹）；
        durable 之后的失败一律 `error=0`，把失败留在 operation/recovery 上可重试。
        """
        j = journal if journal is not None else CallbackStageJournal()
        room_facts = await self.room_route_facts(room_id)

        # ── ① route claim（durable 前第一道门；失败时**不留 delivery 行**）
        #
        # 刻意不在校验前落 delivery：未鉴权请求若能写行，等于给出存在性泄露与无界写入。
        claim = verify_callback_route(
            authorization_header=authorization_header,
            callback_url=callback_url,
            payload_doc_key=body.get("key") if isinstance(body, Mapping) else None,
            room=room_facts,
            secret=secret,
            expected_write_fence_epoch=expected_write_fence_epoch,
            contract=self._contract,
        )
        j.record(CallbackStage.route_verified, str(claim.route_credential.credential_id))

        # ── ② 真值表
        payload = CallbackPayload.from_mapping(body, contract=self._contract)
        rule = self._contract.status_rule(payload.status)
        assert_payload_matches_status_rule(payload, rule)
        j.record(CallbackStage.status_resolved, f"status={payload.status}")

        # ── ③ 归组计划（**在下载之前**）
        eligible = (
            await self._open_close_capture_ids(room_facts)
            if payload.status == 2 and payload.request_id is None
            else ()
        )
        plan = plan_correlation(
            payload=payload, rule=rule, claim=claim, eligible_close_capture_ids=eligible
        )
        j.record(CallbackStage.plan_decided, plan.mode.value)

        # ── ④ delivery 行（含 status + discriminator；网络重试命中同一行）
        delivery_key = build_delivery_key(
            room_id=room_facts.room_id, generation=room_facts.generation, payload=payload
        )
        bound_request: WorkpaperForcesaveRequest | None = None
        if plan.mode in (CorrelationMode.request, CorrelationMode.close_capture):
            # request-first：**先**绑定并校验 request，再 record delivery，使 delivery 一
            # 出生就带 request 归属（T02 行）。顺序反了就会出现"先落无归属行再补"的窗口。
            bound_request = await self._bind_request(plan, room_facts=room_facts)
            j.record(CallbackStage.request_bound, str(bound_request.id))
        shell = (
            await self._shell_of(bound_request.id) if bound_request is not None else None
        )
        # 🔴 pre-durable 的 delivery 行**只**带 request 指针，不带 operation 指针。
        # 不是风格选择，是 V151 的硬约束：`trg_wpcd_operation_link` 是 DEFERRABLE
        # INITIALLY DEFERRED，在 COMMIT 时才跑，且它读的是 operation 行的**当前**状态而
        # NEW 是 INSERT 当时的值。若这里就写 `operation_id=shell.id`（其时
        # `delivery.application_id IS NULL`），correlation 一旦把同一 shell 绑成 primary，
        # COMMIT 时 trigger 就会看到「未归组的 delivery 引用了已绑定 application 的
        # primary operation」并整笔回滚 —— 即成功路径**必然**失败。
        # operation 指针由 `bind_delivery_to_application` 在归组同一条 UPDATE 里写入；
        # request↔shell 是 1:1（`uq_wpso_request`），保留 request 已给足可追溯性
        # （这也正是 `mark_delivery_pre_durable_failure` 清 operation 指针的同一条理由）。
        delivery = await self._repo.record_delivery(
            project_id=await self._project_of(room_facts.wp_id),
            wp_id=room_facts.wp_id,
            entry_id=room_facts.entry_id,
            room_id=room_facts.room_id,
            generation=room_facts.generation,
            route_credential_id=claim.route_credential.credential_id,
            callback_status=payload.status,
            delivery_key=delivery_key,
            payload_sha256=payload.canonical_digest(),
            oo_users_digest=payload.users_digest(),
            forcesave_request_id=bound_request.id if bound_request else None,
            operation_id=None,
        )
        j.record(CallbackStage.delivery_recorded, str(delivery.id))
        classify_delivery_ownership(
            state=DeliveryState(delivery.state),
            durable_at_is_set=delivery.durable_at is not None,
            application_id=delivery.application_id,
            callback_recovery_case_id=delivery.callback_recovery_case_id,
            forcesave_request_id=delivery.forcesave_request_id,
            incoming_artifact_id=delivery.incoming_artifact_id,
            correlation_result=delivery.correlation_result,
        )
        j.assert_request_first()

        # ── ⑤ 无内容 status：真值表说不下载就不下载
        if not plan.download_required:
            j.record(CallbackStage.responded, "no_content")
            return CallbackHandleOutcome(
                response_error=rule.oo_response_error,
                delivery_id=delivery.id,
                delivery_state=DeliveryState(delivery.state),
                correlation_result=None,
                plan=plan,
                journal=j,
            )

        # ── ⑥ 下载 + sealing（全部安全控制都在 durable 之前）
        await self._repo.mark_delivery_downloading(delivery_id=delivery.id)
        j.record(CallbackStage.download_started, "")
        try:
            staged, metrics = download_to_staging(
                url=payload.url or "",
                project_id=delivery.project_id,
                wp_id=room_facts.wp_id,
                delivery_id=delivery.id,
                document_type=self._document_type_of(payload),
                artifacts=self._artifacts,
                policy=self._policy,
                transport=self._transport,
            )
        except CallbackDownloadError as exc:
            # durable 前失败 ⇒ 非零 error；delivery 落 pre-durable rejected 且零 owner。
            await self._repo.mark_delivery_pre_durable_failure(
                delivery_id=delivery.id, state=DeliveryState.rejected, response_error=1
            )
            j.record(CallbackStage.responded, f"pre_durable_rejected:{exc.error_code}")
            return CallbackHandleOutcome(
                response_error=1,
                delivery_id=delivery.id,
                delivery_state=DeliveryState.rejected,
                correlation_result=None,
                plan=plan,
                journal=j,
                error_code=exc.error_code,
                error_stage="download",
            )
        j.record(CallbackStage.download_finished, f"bytes={metrics.bytes_read}")

        sealed = self._artifacts.seal_incoming(staged, delivery_id=delivery.id)
        if not sealed.durable:
            j.record(CallbackStage.sealed_quarantined, sealed.rejection_error_code or "")
            quarantined = await self._register_incoming(
                delivery=delivery, sealed=sealed, state=ArtifactState.quarantined
            )
            await self._repo.mark_delivery_pre_durable_failure(
                delivery_id=delivery.id, state=DeliveryState.rejected, response_error=1
            )
            j.record(CallbackStage.responded, "quarantined")
            return CallbackHandleOutcome(
                response_error=1,
                delivery_id=delivery.id,
                delivery_state=DeliveryState.rejected,
                correlation_result=None,
                plan=plan,
                journal=j,
                quarantined_artifact_id=quarantined,
                error_code=sealed.rejection_error_code,
                error_stage=sealed.rejection_gate or "ooxml",
            )
        j.record(CallbackStage.sealed_durable, sealed.sha256)
        incoming_id = await self._register_incoming(
            delivery=delivery, sealed=sealed, state=ArtifactState.durable
        )

        # ── ⑦ durable 之后：归组。此后一律 error=0。
        return await self._resolve_durable(
            plan=plan,
            payload=payload,
            claim=claim,
            room_facts=room_facts,
            delivery=delivery,
            bound_request=bound_request,
            shell=shell,
            incoming_artifact_id=incoming_id,
            incoming_sha256=sealed.sha256,
            journal=j,
        )

    # ─────────────────────────────────────────────────────────────────
    # 8.3 durable 之后的归组
    # ─────────────────────────────────────────────────────────────────

    async def _resolve_durable(
        self,
        *,
        plan: CorrelationPlan,
        payload: CallbackPayload,
        claim: CallbackRouteClaim,
        room_facts: RoomRouteFacts,
        delivery: WorkpaperCallbackDelivery,
        bound_request: WorkpaperForcesaveRequest | None,
        shell: WorkpaperSyncOperation | None,
        incoming_artifact_id: uuid.UUID,
        incoming_sha256: str,
        journal: CallbackStageJournal,
    ) -> CallbackHandleOutcome:
        """durable fact 已存在 ⇒ 创建/命中 application，或建 recovery case。

        入口第一句是轨迹断言：application key 只能在 durable 之后计算。
        """
        journal.assert_correlation_precondition()

        if plan.mode in (CorrelationMode.request, CorrelationMode.close_capture):
            assert bound_request is not None and shell is not None
            try:
                self._assert_contributor_attribution_safe(payload)
                corr = await self._repo.correlate_durable_incoming(
                    operation_id=shell.id,
                    incoming_artifact_id=incoming_artifact_id,
                    current_revision=await self._current_revision(room_facts.wp_id),
                    adapter_id=await self._adapter_of(bound_request),
                    delivery_id=delivery.id,
                    actor_type=ActorType.callback,
                )
            except SyncDomainError as exc:
                # durable 之后的处理失败：已有关联 operation ⇒ error=0 + 保留 incoming。
                await self._repo.mark_delivery_post_durable_error(delivery_id=delivery.id)
                journal.record(CallbackStage.responded, f"post_durable_error:{exc.error_code}")
                return CallbackHandleOutcome(
                    response_error=0,
                    delivery_id=delivery.id,
                    delivery_state=DeliveryState(delivery.state),
                    correlation_result=None,
                    plan=plan,
                    journal=journal,
                    incoming_artifact_id=incoming_artifact_id,
                    operation_id=shell.id,
                    error_code=exc.error_code,
                    error_stage="correlation",
                )
            journal.record(CallbackStage.correlated, str(corr.application.id))
            result = (
                CorrelationResult.request
                if plan.mode is CorrelationMode.request
                else CorrelationResult.close_capture
            )
            await self._bind_correlated_delivery(
                delivery=delivery,
                incoming_artifact_id=incoming_artifact_id,
                corr=corr,
                forcesave_request_id=bound_request.id,
                correlation_result=result,
            )
            journal.record(CallbackStage.responded, "correlated")
            return CallbackHandleOutcome(
                response_error=0,
                delivery_id=delivery.id,
                delivery_state=DeliveryState.durable,
                correlation_result=result,
                plan=plan,
                journal=journal,
                incoming_artifact_id=incoming_artifact_id,
                application_id=corr.application.id,
                operation_id=corr.operation.id,
            )

        if plan.mode is CorrelationMode.frozen_identity:
            try:
                app = await self._unique_frozen_identity_application(
                    room_facts=room_facts, incoming_sha256=incoming_sha256
                )
                self._assert_contributor_attribution_safe(payload)
            except SyncDomainError as exc:
                return await self._to_recovery(
                    plan=plan,
                    payload=payload,
                    room_facts=room_facts,
                    delivery=delivery,
                    incoming_artifact_id=incoming_artifact_id,
                    reason=RecoveryReason.ambiguous_close,
                    journal=journal,
                    error_code=exc.error_code,
                )
            primary = await self._primary_of(app.id)
            await self._repo.bind_delivery_to_application(
                delivery_id=delivery.id,
                incoming_artifact_id=incoming_artifact_id,
                application_id=app.id,
                operation_id=primary.id,
                forcesave_request_id=None,
                correlation_result=CorrelationResult.existing_application,
            )
            journal.record(CallbackStage.correlated, str(app.id))
            journal.record(CallbackStage.responded, "existing_application")
            return CallbackHandleOutcome(
                response_error=0,
                delivery_id=delivery.id,
                delivery_state=DeliveryState.durable,
                correlation_result=CorrelationResult.existing_application,
                plan=plan,
                journal=journal,
                incoming_artifact_id=incoming_artifact_id,
                application_id=app.id,
                operation_id=primary.id,
            )

        return await self._to_recovery(
            plan=plan,
            payload=payload,
            room_facts=room_facts,
            delivery=delivery,
            incoming_artifact_id=incoming_artifact_id,
            reason=plan.recovery_reason or RecoveryReason.missing_request,
            journal=journal,
        )

    async def _to_recovery(
        self,
        *,
        plan: CorrelationPlan,
        payload: CallbackPayload,
        room_facts: RoomRouteFacts,
        delivery: WorkpaperCallbackDelivery,
        incoming_artifact_id: uuid.UUID,
        reason: RecoveryReason,
        journal: CallbackStageJournal,
        error_code: str | None = None,
    ) -> CallbackHandleOutcome:
        """durable 但无法唯一归组 ⇒ 只建 recovery case（claim 前三实体为 0）。"""
        case = await self._repo.create_recovery_case(
            project_id=delivery.project_id,
            wp_id=room_facts.wp_id,
            entry_id=room_facts.entry_id,
            room_id=room_facts.room_id,
            generation=room_facts.generation,
            source_delivery_key=delivery.delivery_key,
            incoming_artifact_id=incoming_artifact_id,
            reason=reason,
            candidate_confirmation_digest=await self._candidate_confirmation_digest(room_facts),
            candidate_contributor_digest=payload.contributor_digest(),
        )
        journal.record(CallbackStage.recovery_case_created, str(case.id))
        await self._repo.bind_delivery_to_recovery(
            delivery_id=delivery.id,
            incoming_artifact_id=incoming_artifact_id,
            recovery_case_id=case.id,
        )
        journal.record(CallbackStage.responded, "recovery_case")
        return CallbackHandleOutcome(
            response_error=0,
            delivery_id=delivery.id,
            delivery_state=DeliveryState.unmatched,
            correlation_result=CorrelationResult.unmatched,
            plan=plan,
            journal=journal,
            incoming_artifact_id=incoming_artifact_id,
            recovery_case_id=case.id,
            error_code=error_code,
            error_stage="correlation" if error_code else None,
        )

    # ─────────────────────────────────────────────────────────────────
    # 8.4 recovery claim / download-only（authorization-first）
    # ─────────────────────────────────────────────────────────────────

    async def claim_recovery_case(
        self,
        *,
        case_id: uuid.UUID,
        claiming_participant_id: uuid.UUID,
        prior_confirmation_id: uuid.UUID,
        idempotency_key: str,
        adapter_id: str,
        adapter_build_digest: str,
        contributor_snapshot_digest: str,
        actor_id: uuid.UUID | None = None,
    ) -> Any:
        """authorization-first claim：先校验当前授权，再做任何业务写。

        授权门复用 :meth:`RoomService.assert_can_initiate_request`（room 状态 /
        participant lease / mode=edit / fence / confirmation / bundle 八条判据）——
        本模块**不**自写第二份。校验失败时不产生 request/application/operation。
        """
        from app.services.workpaper_sync.rooms import RoomService

        case = await self._load_case(case_id)
        rooms = RoomService(self._repo)
        try:
            await rooms.assert_can_initiate_request(
                room_id=case.room_id,
                participant_id=claiming_participant_id,
                kind=RequestKind.forcesave,
            )
        except SyncDomainError as exc:
            raise RecoveryClaimAuthorizationError(
                f"recovery claim 的授权重验失败（{exc.error_code}）—— "
                "claim 前不得创建 request/application/operation"
            ) from exc
        return await self._repo.claim_recovery_case(
            case_id=case_id,
            claiming_participant_id=claiming_participant_id,
            prior_confirmation_id=prior_confirmation_id,
            idempotency_key=idempotency_key,
            current_revision=await self._current_revision(case.wp_id),
            adapter_id=adapter_id,
            adapter_build_digest=adapter_build_digest,
            contributor_snapshot_digest=contributor_snapshot_digest,
            actor_id=actor_id,
        )

    async def terminate_download_only(
        self, *, case_id: uuid.UUID, actor_id: uuid.UUID | None = None
    ) -> WorkpaperCallbackRecoveryCase:
        """download-only 终结：三实体恒为 0（Requirement 5.8）。"""
        return await self._repo.terminate_recovery_download_only(
            case_id=case_id, actor_id=actor_id
        )

    # ─────────────────────────────────────────────────────────────────
    # 8.5 内部
    # ─────────────────────────────────────────────────────────────────

    def _document_type_of(self, payload: CallbackPayload) -> str:
        """下载文档类型只取自 payload 的 `filetype`，且必须在契约支持集内。"""
        raw = str(payload.raw.get("filetype") or "").strip().lower()
        if raw in ("xlsx", "docx"):
            return raw
        raise CallbackPayloadShapeError(
            f"callback filetype={raw!r} 不受支持（只处理 xlsx/docx）"
        )

    async def _project_of(self, wp_id: uuid.UUID) -> uuid.UUID:
        row = (
            await self._repo.session.execute(
                sa.text(
                    # 🔴 `CAST(:wp AS uuid)` 不是装饰。`sa.text()` 不带类型信息，
                    # SQLAlchemy 把 bind 当文本发出，而 asyncpg 是**强类型**驱动：
                    # `WHERE id = $1::VARCHAR` 对 uuid 列直接
                    # `operator does not exist: uuid = character varying`。
                    # 这条在离线守卫里永远看不见（那里没有真库），只有真实 PostgreSQL
                    # 会暴露 —— 修之前整条 handle_callback 在 PG 上一次都跑不通。
                    "SELECT project_id FROM working_paper WHERE id = CAST(:wp AS uuid)"
                ).bindparams(wp=str(wp_id))
            )
        ).first()
        if row is None:
            raise RequestBindingError(f"working_paper {wp_id} 不存在")
        return uuid.UUID(str(row[0]))

    async def _current_revision(self, wp_id: uuid.UUID) -> int:
        row = (
            await self._repo.session.execute(
                sa.text(
                    "SELECT file_version FROM working_paper WHERE id = CAST(:wp AS uuid)"
                ).bindparams(wp=str(wp_id))
            )
        ).first()
        return int(row[0]) if row is not None else 1

    async def _open_close_capture_ids(
        self, room_facts: RoomRouteFacts
    ) -> tuple[uuid.UUID, ...]:
        """generation 内仍 open 的 close-capture request（status=2 无 userdata 的第一优先级）。"""
        rows = (
            (
                await self._repo.session.execute(
                    sa.select(WorkpaperForcesaveRequest.id).where(
                        WorkpaperForcesaveRequest.room_id == room_facts.room_id,
                        WorkpaperForcesaveRequest.generation == room_facts.generation,
                        WorkpaperForcesaveRequest.kind == RequestKind.close_capture.value,
                        WorkpaperForcesaveRequest.state.in_(
                            ("frozen", "pending", "accepted")
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        return tuple(rows)

    async def _bind_request(
        self, plan: CorrelationPlan, *, room_facts: RoomRouteFacts
    ) -> WorkpaperForcesaveRequest:
        """精确绑定 frozen request 并逐项校验（在下载之前 —— Requirement 4.3）。"""
        assert plan.request_id is not None
        req = (
            await self._repo.session.execute(
                sa.select(WorkpaperForcesaveRequest).where(
                    WorkpaperForcesaveRequest.id == plan.request_id
                )
            )
        ).scalar_one_or_none()
        if req is None:
            raise RequestBindingError(
                f"userdata 指向的 frozen request {plan.request_id} 不存在 —— "
                "不得退化成按 incoming 去重"
            )
        if req.room_id != room_facts.room_id:
            raise RequestBindingError(
                f"request {req.id} 属于 room {req.room_id}，与 callback 的 "
                f"{room_facts.room_id} 不符"
            )
        if int(req.generation) != int(room_facts.generation):
            raise RequestBindingError(
                f"request {req.id} 冻结于 generation {req.generation}，callback 为 "
                f"{room_facts.generation} —— 跨代际 artifact 不得应用"
            )
        if int(req.write_fence_epoch) != int(room_facts.write_fence_epoch):
            raise RequestFenceStaleError(
                f"request 冻结 fence={req.write_fence_epoch}，room 当前 fence="
                f"{room_facts.write_fence_epoch} —— 期间有 participant 被撤销/代际旋转"
            )
        room = await self._repo.lock_room(room_facts.room_id)
        await self._assert_request_bundle_current(req, room)
        return req

    async def _assert_request_bundle_current(
        self, req: WorkpaperForcesaveRequest, room: WorkpaperOoRoom
    ) -> None:
        """request 冻结的 approved bundle/authority 必须仍是 room client-confirmed 的那一个。

        🔴 三条判据都读**真实列**，不用 `getattr(..., None)` 兜底：不存在的列名配合
        `None` 兜底会让整条判据变成恒真（改错列名后守卫照样绿），这正是本 spec 反复
        付过代价的假绿第③源。room 侧的 approved bundle 真源是
        `client_confirmed_definition_bundle_id/_sha256`（Task 21 在 confirm_descriptor
        里写入），不是任何"当前 registry alias"。
        """
        bundle = await self._repo.assert_bundle_usable(req.definition_bundle_id)
        if bundle.canonical_payload_sha256 != req.definition_bundle_sha256:
            raise RequestFrozenIdentityError(
                f"request {req.id} 冻结的 bundle digest 与 bundle 行不一致 —— "
                "历史 request 必须原样使用冻结值，registry alias 不得重新解析"
            )
        if (
            bundle.authority_model_definition_sha256
            != req.authority_model_definition_sha256
        ):
            raise RequestFrozenIdentityError(
                f"request {req.id} 的 authority model digest 与 bundle child 不一致"
            )
        if room.client_confirmed_definition_bundle_id is None:
            raise RequestFrozenIdentityError(
                f"room {room.id} 尚无 client-confirmed bundle 基线 —— "
                "callback 不得按到达时的可变 room pointer 补齐 bundle"
            )
        if room.client_confirmed_definition_bundle_id != req.definition_bundle_id:
            raise RequestFrozenIdentityError(
                f"request {req.id} 冻结 bundle {req.definition_bundle_id} 与 room "
                f"client-confirmed bundle {room.client_confirmed_definition_bundle_id} "
                "不同 —— bundle 漂移后旧 request 不得应用"
            )
        if room.client_confirmed_definition_bundle_sha256 != req.definition_bundle_sha256:
            raise RequestFrozenIdentityError(
                f"request {req.id} 冻结 bundle digest 与 room client-confirmed digest 不同"
            )

    async def _shell_of(self, request_id: uuid.UUID) -> WorkpaperSyncOperation:
        shell = (
            await self._repo.session.execute(
                sa.select(WorkpaperSyncOperation).where(
                    WorkpaperSyncOperation.forcesave_request_id == request_id
                )
            )
        ).scalar_one_or_none()
        if shell is None:
            raise RequestBindingError(
                f"request {request_id} 缺 pre-correlation operation shell —— "
                "冻结 request 的事务必须同时建 shell（AC 4.1）"
            )
        return shell

    async def _adapter_of(self, req: WorkpaperForcesaveRequest) -> str:
        rep = (
            await self._repo.session.execute(
                sa.text(
                    "SELECT adapter_id FROM working_paper_content_representation "
                    "WHERE id = CAST(:rid AS uuid)"
                ).bindparams(rid=str(req.client_base_representation_id))
            )
        ).first()
        if rep is None:
            raise RequestFrozenIdentityError(
                f"request {req.id} 冻结的 representation 不存在"
            )
        return str(rep[0])

    def _assert_contributor_attribution_safe(self, payload: CallbackPayload) -> None:
        """contributor 归属安全性（Requirement 10.3 / Property 44）。

        Task 4 实证：`history.changes` 含**已被 drop 的用户**，`users` 只有最后编辑者
        ⇒ OO 派生的 contributor 置信度永远不是 `exact`。因此这里唯一能安全判定的是
        "有没有 contributor 信号"；真正的授权重验在 Task 26 的最终 fence（读 participant
        lease/permission epoch）。若连 aggregate 信号都没有且 payload 声称有内容变化，
        归属无法判定 ⇒ 拒绝并让上层旋转 generation。
        """
        if payload.contributors or payload.users:
            return
        if payload.notmodified:
            return
        raise ContributorAttributionUnsafeError(
            "callback 既无 `users` 也无 `history.changes` contributor 信号，且未声明 "
            "notmodified —— 归属无法安全判定，不得产生 content application"
            "（Requirement 10.3：隔离/supersede generation，而不是把 route participant 当作者）"
        )

    def contributor_confidence_of(self, payload: CallbackPayload) -> ContributorConfidence:
        """OO 派生 contributor 的置信度：**永不** `exact`（Task 4 已实证）。"""
        if payload.contributors:
            return ContributorConfidence.aggregate
        if payload.users:
            return ContributorConfidence.aggregate
        return ContributorConfidence.unknown

    async def _unique_frozen_identity_application(
        self, *, room_facts: RoomRouteFacts, incoming_sha256: str
    ) -> WorkpaperContentApplication:
        """status=2 无 userdata 且无 eligible request 时的最后一条去重路径。

        允许命中的条件（契约 `userdata_rules.absent.status_2`）：同 room/generation、
        同 incoming sha 的既有 application **恰好一个**，且不存在 sequence 更高的
        **不同** canonical application。任何一条不满足即 ambiguous ⇒ 建 recovery case。
        """
        apps = (
            (
                await self._repo.session.execute(
                    sa.select(WorkpaperContentApplication).where(
                        WorkpaperContentApplication.room_id == room_facts.room_id,
                        WorkpaperContentApplication.generation == room_facts.generation,
                        WorkpaperContentApplication.incoming_sha256 == incoming_sha256,
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(apps) != 1:
            raise FrozenIdentityAmbiguousError(
                f"同 incoming sha 的既有 application 数={len(apps)}（要求恰 1）—— "
                "相同 incoming 在不同 frozen base/representation/bundle/authority model 下"
                "必须是不同 application，不得被 incoming-first 去重"
            )
        app = apps[0]
        room = await self._repo.lock_room(room_facts.room_id)
        latest_id = room.latest_durable_application_id
        latest_seq = int(room.latest_durable_sequence or 0)
        if (
            latest_id is not None
            and latest_id != app.id
            and latest_seq > int(app.effective_request_sequence)
        ):
            raise FrozenIdentityAmbiguousError(
                f"room 最新 durable canonical application {latest_id} 的 sequence "
                f"{latest_seq} 高于候选 {app.id} 的 {app.effective_request_sequence} —— "
                "存在更高的不同 canonical application 时不得去重"
            )
        return app

    async def _primary_of(self, application_id: uuid.UUID) -> WorkpaperSyncOperation:
        primary = (
            await self._repo.session.execute(
                sa.select(WorkpaperSyncOperation).where(
                    WorkpaperSyncOperation.application_id == application_id
                )
            )
        ).scalar_one_or_none()
        if primary is None:
            raise FrozenIdentityAmbiguousError(
                f"application {application_id} 没有绑定它的 primary operation —— "
                "delivery 必须以 canonical primary 校验同 application"
            )
        return primary

    async def _bind_correlated_delivery(
        self,
        *,
        delivery: WorkpaperCallbackDelivery,
        incoming_artifact_id: uuid.UUID,
        corr: CorrelationOutcome,
        forcesave_request_id: uuid.UUID | None,
        correlation_result: CorrelationResult,
    ) -> None:
        """delivery 绑 canonical application；operation 可为 primary 或直指它的 duplicate。"""
        classify_delivery_ownership(
            state=DeliveryState.durable,
            durable_at_is_set=True,
            application_id=corr.application.id,
            callback_recovery_case_id=None,
            forcesave_request_id=forcesave_request_id,
            incoming_artifact_id=incoming_artifact_id,
            correlation_result=correlation_result,
        )
        await self._repo.bind_delivery_to_application(
            delivery_id=delivery.id,
            incoming_artifact_id=incoming_artifact_id,
            application_id=corr.application.id,
            operation_id=corr.operation.id,
            forcesave_request_id=forcesave_request_id,
            correlation_result=correlation_result,
        )

    async def _register_incoming(
        self,
        *,
        delivery: WorkpaperCallbackDelivery,
        sealed: SealedIncoming,
        state: ArtifactState,
    ) -> uuid.UUID:
        """登记 incoming artifact 行。durable/quarantined 两支共用同一路径命名空间。"""
        artifact = await self._repo.register_artifact(
            project_id=delivery.project_id,
            wp_id=delivery.wp_id,
            kind=ArtifactKind.incoming,
            state=state,
            relative_path=sealed.relative_path,
            sha256=sealed.sha256,
            size_bytes=sealed.size_bytes,
            document_type=sealed.document_type,
            source_delivery_id=delivery.id,
        )
        return artifact.id

    async def _candidate_confirmation_digest(
        self, room_facts: RoomRouteFacts
    ) -> str | None:
        """同 generation prior confirmations 的确定性候选摘要（recovery list 用）。"""
        rows = (
            (
                await self._repo.session.execute(
                    sa.text(
                        "SELECT id FROM working_paper_oo_client_confirmation "
                        "WHERE room_id = CAST(:room AS uuid) AND generation = :gen "
                        "AND invalidated_at IS NULL ORDER BY id"
                    ).bindparams(room=str(room_facts.room_id), gen=room_facts.generation)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return None
        return hashlib.sha256(
            ("candidate-confirmations:v1|" + ",".join(str(r) for r in rows)).encode("utf-8")
        ).hexdigest()

    async def _load_case(self, case_id: uuid.UUID) -> WorkpaperCallbackRecoveryCase:
        case = (
            await self._repo.session.execute(
                sa.select(WorkpaperCallbackRecoveryCase).where(
                    WorkpaperCallbackRecoveryCase.id == case_id
                )
            )
        ).scalar_one_or_none()
        if case is None:
            raise RecoveryClaimAuthorizationError(f"recovery case {case_id} 不存在")
        return case


__all__ = [
    # 异常
    "CallbackDeliveryDomainError",
    "CallbackStatusUnsupportedError",
    "CallbackPayloadShapeError",
    "CallbackActionNotWritableError",
    "RequestBindingError",
    "RequestFrozenIdentityError",
    "RequestFenceStaleError",
    # 🔴 `__all__` 只许列**本模块真实定义**的名字。原实现还列了
    # `CloseCaptureAmbiguousError` 与 `RouteParticipantAuthorshipError` 两个不存在的
    # 类型：`from callback_delivery import *` 直接 AttributeError，而按名字去 grep
    # 「这条拒绝有没有实现」会得到假阳性。授权误用那条实际叫
    # `callback_route.CallbackAuthorshipMisuseError`（在 route 层，不在本模块）。
    "FrozenIdentityAmbiguousError",
    "ContributorAttributionUnsafeError",
    "QuarantineOperationForbiddenError",
    "CallbackStageOrderError",
    "RecoveryClaimAuthorizationError",
    # payload / delivery
    "CallbackPayload",
    "assert_payload_matches_status_rule",
    "compute_delivery_discriminator",
    "build_delivery_key",
    # 归属真值表
    "OwnershipVerdict",
    "CorrelationFamily",
    "correlation_family",
    "DeliveryOwnershipRow",
    "DELIVERY_OWNERSHIP_TRUTH_TABLE",
    "classify_delivery_ownership",
    # quarantine
    "QUARANTINE_ALLOWED_OPERATIONS",
    "QUARANTINE_FORBIDDEN_OPERATIONS",
    "assert_quarantine_operation_allowed",
    "assert_incoming_admissible_for_application",
    # 归组
    "CorrelationMode",
    "CorrelationPlan",
    "plan_correlation",
    # 轨迹
    "CallbackStage",
    "CallbackStageJournal",
    # 服务
    "CallbackHandleOutcome",
    "CallbackDeliveryService",
]
