# -*- coding: utf-8 -*-
"""callback route claim：JWT claim schema、URL 绑定与 room/generation 服务凭证校验。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 22
Requirements: 4.9, 5.1, 5.2, 10.2, 10.7, 10.9
Properties: **P16**（claim version 真校验）/ **P44** / **P63**

═══ 一、本模块为什么独立于 `callback_delivery` ═══

Task 4 的 `jwt_claim_schema.verification_order` 是一条**不可交换**的序列，最后一句是
「以上全部通过后才允许下载」。把它和「下载 + sealing + correlation」写在同一个函数里，
最容易出现的退化是：先算 delivery key 落一行 received、再去校验 claim —— 于是未鉴权的
请求也能往 delivery 表里写行（存在性泄露 + 无界写入）。分模块让「claim 校验先于任何
副作用」变成结构性事实：:class:`CallbackRouteClaim` 是 `callback_delivery` 侧每个入口的
**必填入参**，构造它的唯一途径就是走完本模块的校验。

═══ 二、router 只委派：判据落在哪里 ═══

Task 22 的第一条要求是「router 只委派」。它不是一句风格约定，可验证形态有三条：

1. **校验逻辑的唯一实现**在本模块（:func:`verify_callback_route`），router 不得自己
   `jwt.decode` 后按字段比对；
2. 本模块**不接触** ORM 写入、不下载、不 commit —— 只读 room 行做绑定校验；
3. :func:`verify_callback_route` 的签名里**没有** participant/user 入参，返回值也不含
   「作者」语义字段。Task 4 §3 已实证 callback 是 room/generation 级服务事件：
   `users` 只含最后编辑者、`history.changes` 才是全体贡献者且包含已被 drop 的用户。
   可选 claim `participant_id` 因此只以 :attr:`CallbackRouteClaim.audit_participant_hint`
   出现，名字里写着 hint，并由 :meth:`CallbackRouteClaim.assert_not_authorship` 在任何
   试图把它当授权/作者依据的地方抛错。

═══ 三、Property 16：`claim_version=None` 必须在下载前失败 ═══

Task 4 §9 记下的生产实况是 `verify_callback_preconditions(claim_version=None, ...)`
—— 校验机制在，接线绕过。所以本模块把 claim 版本做成**三段独立判据**：

* `cbv` 缺失 ⇒ :class:`CallbackClaimVersionError`（缺版本）；
* `cbv` 不是严格 int（`"1"` / `1.0` / `True`）⇒ 同类型但不同 detail，**不做隐式转换**；
* `cbv` 已知但不等于契约版本 ⇒ 同类型。

三段共用一个 error_code 是刻意的（它们是同一个语义：claim 版本不可信），但与
「签名坏了」「绑定不符」「credential 不属于本 room」分成**不同类型** —— Task 21 已为
「两个拒绝共用一个 error_code 让前者永久不可达」付过一次代价。

═══ 四、不做的事 ═══

* **不签发** token：签发属 Task 25 的 launch descriptor / Task 28 的 router；本模块只验。
  （测试需要构造 token，故提供 :func:`sign_callback_route_token`，但它标注为
  `test/wiring helper`，且 `act` 只接受契约 enum 内的值。）
* **不判**「这个 status 该不该下载」：那是真值表的事，由 `callback_delivery` 读
  :meth:`CallbackContract.status_rule`。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, Mapping
from urllib.parse import parse_qsl, urlsplit

from jose import JWTError, jwt

from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.oo_contract import (
    CallbackContract,
    JwtClaimSchema,
    load_callback_contract,
)
from app.services.workpaper_sync.rooms import (
    RouteCredential,
    assert_route_credential,
    doc_key_matches,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常：每条拒绝一个类型（去遮蔽）
# ═══════════════════════════════════════════════════════════════════════════


class CallbackRouteError(SyncDomainError):
    """callback route 校验失败基类。durable 之前的失败一律返回 OO 非零 error。"""

    error_code = "callback_route_invalid"


class CallbackTokenMissingError(CallbackRouteError):
    """header 里没有 token（`verification_order` 第一步）。"""

    error_code = "callback_token_missing"


class CallbackTokenSignatureError(CallbackRouteError):
    """签名/alg/exp 校验失败。

    🔴 与 :class:`CallbackClaimVersionError` 分型：签名坏了是「不可信来源」，
    claim 版本不对是「可信来源但协议版本未知」。合并成一个类型时，删掉版本判据的变异
    会被签名分支遮蔽而判 GREEN。
    """

    error_code = "callback_token_signature_invalid"


class CallbackSecretMissingError(CallbackRouteError):
    """未配置 callback route token secret。

    🔴 与 :class:`CallbackTokenSignatureError` 分型，理由是变异检验实测出来的：
    共用一个类型时，删掉「无密钥即拒」那道门，`jwt.decode(token, "")` 仍会因签名不过
    抛 `JWTError` ⇒ 转成同一个 `CallbackTokenSignatureError` ⇒ 守卫恒绿，
    「无密钥 fail closed」这条判据永久不可达（本 spec 已为同一形态付过一次代价）。
    分型后「删掉这道门」立刻打红。
    """

    error_code = "callback_route_secret_missing"


class CallbackTokenExpiredError(CallbackRouteError):
    """token 已过期（平台自己的显式时钟判据，不依赖 jose 的 exp 校验）。

    🔴 同样与 :class:`CallbackTokenSignatureError` 分型：jose 也会校验 `exp`，共用类型
    时删掉显式判据会被 jose 遮蔽而恒绿 —— 可显式判据存在的**全部理由**就是
    「jose 允许 leeway、且 `options` 一旦被改（`verify_exp=False`）就静默失效」，
    也就是说它必须在 jose **不**报错的情形下也能独立生效。
    """

    error_code = "callback_token_expired"


class CallbackClaimVersionError(CallbackRouteError):
    """`cbv` 缺失 / 非严格 int / 与契约版本不符（Property 16）。"""

    error_code = "callback_claim_version_invalid"


class CallbackClaimSchemaError(CallbackRouteError):
    """必填 claim 缺失、常量 claim（iss/aud）不符或 `act` 不在 enum 内。"""

    error_code = "callback_claim_schema_invalid"


class CallbackUrlBindingError(CallbackRouteError):
    """claim 与 callback URL 的 room/generation/doc_key/route_credential 不逐项一致。"""

    error_code = "callback_url_binding_mismatch"


class CallbackDocKeyMismatchError(CallbackRouteError):
    """`payload.key` 与 claim.doc_key 或 room 当前 doc_key 不符。

    与 :class:`CallbackUrlBindingError` 分型：URL 绑定看的是「URL 与 claim 一致」，
    这一条看的是「claim 与 **room 行/payload** 一致」。同一个类型会让「payload.key
    根本没被校验」这件事被 URL 分支遮蔽。
    """

    error_code = "callback_doc_key_mismatch"


class CallbackGenerationStaleError(CallbackRouteError):
    """room 已 supersede / write fence 已提升 ⇒ 该代际 callback 不再可应用。"""

    error_code = "callback_generation_stale"


class CallbackAuthorshipMisuseError(CallbackRouteError):
    """有人把 route claim（或其可选 participant hint）当成聚合 artifact 的作者/授权依据。"""

    error_code = "callback_route_is_not_authorship"


# ═══════════════════════════════════════════════════════════════════════════
# 1. claim 投影
# ═══════════════════════════════════════════════════════════════════════════

#: callback URL 上必须逐项出现并与 claim 一致的查询参数名。
#: 与契约 `jwt_claim_schema.url_binding.rule` 里列出的四项锁死（`_parse_jwt` 已强制
#: 契约文本必须逐项声明这四项，故此处不是第二真源，而是同一份清单的执行形态）。
URL_BOUND_PARAMS: Final[tuple[str, ...]] = (
    "room_id",
    "generation",
    "doc_key",
    "route_credential_id",
)


@dataclass(frozen=True)
class CallbackRouteClaim:
    """已校验的 callback route claim。

    **刻意不含**「作者」语义：没有 `author_participant_id`、没有 `user_id`。
    可选的 participant claim 只以 :attr:`audit_participant_hint` 出现（Task 4
    `optional_claims.participant_id.must_not_be_used_for` 明确列了两条禁用途）。
    """

    claim_version: int
    issuer: str
    audience: str
    action: str
    room_id: uuid.UUID
    generation: int
    doc_key: str
    route_credential: RouteCredential
    callback_token_id: uuid.UUID
    issued_at: int
    expires_at: int
    #: 仅审计线索，永不作为授权/作者依据。
    audit_participant_hint: uuid.UUID | None = None

    @property
    def allows_content_write(self) -> bool:
        """该 action 是否允许把内容写回（`callback_write`）。

        `callback_notify` 只允许 presence/drop 取证类处理 —— status 1/4 那两行。
        """
        return self.action == "callback_write"

    def assert_not_authorship(self, *, where: str) -> None:
        """任何试图把 route claim 当作者/唯一授权依据的调用点都必须过这道门。

        它不是装饰：Task 4 §3 的实证是「A 发起的 forcesave 产出的 artifact 里含 B 的
        并发修改」，所以「用 route claim 的 participant 当作者」会把 B 的内容记成 A 写的。
        授权依据只有 frozen request 的 initiator + participant lease + write fence。
        """
        raise CallbackAuthorshipMisuseError(
            f"{where}: callback route claim 是 room/generation 级服务凭证，"
            "既不是聚合 artifact 的作者也不是授权依据（Task 4 §3 实证：A 发起的 "
            "forcesave 回传 artifact 含 B 的并发修改）。授权只能来自 frozen request "
            "的 initiator + participant lease + write fence"
        )


@dataclass(frozen=True)
class RoomRouteFacts:
    """校验 route claim 所需的 **room 行事实**（由调用方从 DB 读，本模块不查库）。

    做成显式 dataclass 而不是直接吃 ORM 对象：本模块必须能在没有 DB 的离线守卫里
    逐条驱动每个拒绝分支；吃 ORM 对象会把「claim 校验」和「session 生命周期」绑在
    一起，离线守卫就只能 mock，而 mock 掉的正是被测判据。
    """

    room_id: uuid.UUID
    generation: int
    doc_key: str
    wp_id: uuid.UUID
    entry_id: str
    write_fence_epoch: int
    #: room 是否仍接受该代际的 callback（`superseded/closed` 为 False）。
    accepts_callback: bool


# ═══════════════════════════════════════════════════════════════════════════
# 2. token 解析（verification_order 第 1-5 步）
# ═══════════════════════════════════════════════════════════════════════════


def extract_bearer_token(header_value: str | None) -> str:
    """从 `Authorization` 头取原始 token；缺失即拒（`verification_order` 第 1 步）。

    OO 9.4 同时在 header 与 body 放 token（契约 `transport.oo94_facts`）。平台**只**以
    header 为准：body 里的 `token` 是 OO 自己签的 `{"payload": <整个 body>}`，不含平台
    自定义 claim，拿它当授权凭据等于让请求体自证合法。
    """
    if header_value is None or not str(header_value).strip():
        raise CallbackTokenMissingError(
            "callback 缺少 Authorization header —— 契约 verification_order 第一步即拒，"
            "不得回退到 body 内的 OO 自签 token"
        )
    raw = str(header_value).strip()
    # 🔴 先按空白切出 scheme，**不能**先 `strip()` 再判 `startswith("bearer ")`：
    # `"Bearer   "` 被 strip 成 `"Bearer"`，就不再以 `"bearer "`（含尾空格）开头，于是
    # 「只有 scheme 没有 token」那条 raise 变成**不可达代码**，而 `"Bearer"` 这个字面量
    # 会被当成 token 送进 `jwt.decode` —— 拒绝理由从「缺 token」漂成「签名坏了」。
    # 两个拒绝各有独立类型正是为了区分它们，遮蔽掉前者等于把该类型永久判 GREEN。
    head, _, rest = raw.partition(" ")
    if head.lower() == "bearer":
        raw = rest.strip()
        if not raw:
            raise CallbackTokenMissingError(
                "Authorization header 只有 `Bearer` scheme 没有 token —— "
                "不得把 scheme 字面量当作 token 交给签名校验"
            )
    return raw


def _decode(token: str, *, secret: str, schema: JwtClaimSchema) -> Mapping[str, Any]:
    if not secret:
        # 没有 secret 时**不放行**。生产 legacy 路径的 `if not JWT_SECRET: return True`
        # 正是「JWT 校验形同虚设」的入口；本模块 fail closed。
        raise CallbackSecretMissingError(
            "未配置 callback route token secret —— 无密钥时不得处理任何 callback"
        )
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[schema.algorithm],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise CallbackTokenSignatureError(
            f"callback route token 签名/alg/exp 校验失败: {exc}"
        ) from exc


def _require_claim_version(raw: Mapping[str, Any], *, schema: JwtClaimSchema) -> int:
    """Property 16 的三段判据。**不做**任何隐式转换。"""
    if "cbv" not in raw:
        raise CallbackClaimVersionError(
            "callback claim 缺少 `cbv` —— 契约 unknown_or_missing_version="
            "reject_before_download 要求在下载前拒绝（Requirement 5.2 禁止 "
            "claim_version=None 绕过）"
        )
    value = raw["cbv"]
    if isinstance(value, bool) or not isinstance(value, int):
        raise CallbackClaimVersionError(
            f"callback claim `cbv` 必须是严格整数，实得 {type(value).__name__} {value!r} —— "
            "`int(\"1\")` 这类强转会把伪造版本猜成已知版本"
        )
    if value != schema.claim_schema_version:
        raise CallbackClaimVersionError(
            f"callback claim `cbv`={value} 不是本部署支持的 "
            f"{schema.claim_schema_version} —— 未知版本必须在下载前拒绝"
        )
    return value


def _require_uuid(raw: Mapping[str, Any], key: str) -> uuid.UUID:
    if key not in raw:
        raise CallbackClaimSchemaError(f"callback claim 缺少必填项 {key!r}")
    try:
        return uuid.UUID(str(raw[key]))
    except (ValueError, AttributeError, TypeError) as exc:
        raise CallbackClaimSchemaError(
            f"callback claim {key!r} 不是合法 UUID: {raw[key]!r}"
        ) from exc


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    if key not in raw:
        raise CallbackClaimSchemaError(f"callback claim 缺少必填项 {key!r}")
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise CallbackClaimSchemaError(
            f"callback claim {key!r} 必须是整数，实得 {type(value).__name__}"
        )
    return value


def parse_callback_claims(
    token: str, *, secret: str, contract: CallbackContract | None = None
) -> CallbackRouteClaim:
    """解签并投影 claim（`verification_order` 第 2-5 步）；**不**做 URL/room 绑定。

    拆成两步（parse → verify）是为了让「绑定校验被整段删掉」这件事有独立判据：
    合并成一个函数时，删掉绑定段落只会让某几个断言失败，而
    :func:`verify_callback_route` 的存在让「谁必须调用它」可以用调用点判据钉住。
    """
    ct = contract or load_callback_contract()
    schema = ct.jwt
    raw = _decode(token, secret=secret, schema=schema)

    claim_version = _require_claim_version(raw, schema=schema)
    for key, expected in schema.claim_constants.items():
        if key == "cbv":
            continue  # 已由 _require_claim_version 用专属类型处理
        if raw.get(key) != expected:
            raise CallbackClaimSchemaError(
                f"callback claim {key!r}={raw.get(key)!r} 与契约常量 {expected!r} 不符"
            )
    action = raw.get("act")
    if action not in schema.action_enum:
        raise CallbackClaimSchemaError(
            f"callback claim `act`={action!r} 不在契约 enum {list(schema.action_enum)} 内"
        )

    generation = _require_int(raw, "generation")
    if generation < 1:
        raise CallbackClaimSchemaError(f"callback claim `generation` 必须 >= 1，实得 {generation}")
    doc_key = str(raw.get("doc_key") or "").strip()
    if not doc_key:
        raise CallbackClaimSchemaError("callback claim `doc_key` 不得为空")

    hint_raw = raw.get("participant_id")
    hint: uuid.UUID | None = None
    if hint_raw is not None:
        try:
            hint = uuid.UUID(str(hint_raw))
        except (ValueError, AttributeError, TypeError):
            # 可选 audit 线索非法时**不拒绝整条 callback**：它对授权毫无作用，
            # 拿它当拒绝理由等于赋予它授权语义。记 WARNING 后丢弃。
            logger.warning("callback claim 的可选 participant_id 非法，已丢弃: %r", hint_raw)
            hint = None

    room_id = _require_uuid(raw, "room_id")
    credential_id = _require_uuid(raw, "route_credential_id")
    return CallbackRouteClaim(
        claim_version=claim_version,
        issuer=str(raw.get("iss")),
        audience=str(raw.get("aud")),
        action=str(action),
        room_id=room_id,
        generation=generation,
        doc_key=doc_key,
        # 此处只做形状投影；credential 与 room 的绑定由 verify_callback_route 用
        # rooms.assert_route_credential 重算校验（不查表、可重放）。
        route_credential=RouteCredential(
            credential_id=credential_id,
            room_id=room_id,
            generation=generation,
            doc_key=doc_key,
        ),
        callback_token_id=_require_uuid(raw, "callback_token_id"),
        issued_at=_require_int(raw, "iat"),
        expires_at=_require_int(raw, "exp"),
        audit_participant_hint=hint,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. URL / room 绑定（verification_order 第 6-7 步）
# ═══════════════════════════════════════════════════════════════════════════


def _url_bound_values(callback_url: str) -> dict[str, str]:
    parts = urlsplit(callback_url)
    query = {k: v for k, v in parse_qsl(parts.query, keep_blank_values=True)}
    return {key: str(query.get(key, "")).strip() for key in URL_BOUND_PARAMS}


def assert_url_binding(claim: CallbackRouteClaim, *, callback_url: str) -> None:
    """callback URL 的四项必须与 claim 逐项一致（契约 `url_binding.rule`）。

    逐项而不是「至少一项」：只绑 room 时 generation 旋转后旧 URL 仍合法，
    AC 2.8 的 supersede 就形同虚设。
    """
    observed = _url_bound_values(callback_url)
    expected = {
        "room_id": str(claim.room_id),
        "generation": str(claim.generation),
        "doc_key": claim.doc_key,
        "route_credential_id": str(claim.route_credential.credential_id),
    }
    mismatched = {
        key: (observed[key], expected[key])
        for key in URL_BOUND_PARAMS
        if observed[key] != expected[key]
    }
    if mismatched:
        raise CallbackUrlBindingError(
            "callback URL 与 claim 的绑定项不一致（observed, expected）: "
            f"{mismatched} —— 契约要求 room_id/generation/doc_key/route_credential_id "
            "逐项一致"
        )


def verify_callback_route(
    *,
    authorization_header: str | None,
    callback_url: str,
    payload_doc_key: object,
    room: RoomRouteFacts,
    secret: str,
    expected_write_fence_epoch: int | None = None,
    contract: CallbackContract | None = None,
    now_epoch: int | None = None,
) -> CallbackRouteClaim:
    """callback route 的**唯一**校验入口，严格按契约 `verification_order` 执行。

    签名里刻意**没有** participant/user 入参：route 校验不承担作者语义（Task 4 §3）。
    也刻意**不接受** session/repo：本函数零副作用，room 事实由调用方以
    :class:`RoomRouteFacts` 传入。

    Args:
        authorization_header: 原始 `Authorization` 头。
        callback_url: 本次请求的完整 URL（含 query），用于逐项绑定校验。
        payload_doc_key: callback body 的 `key`。声明为 `object`：它来自不可信 JSON，
            收窄成 `str` 只会让调用方在外面 `str(...)`，而 `str(None) == "None"` 会把
            「根本没带 key」变成一个看起来正常的字符串。
        room: room 行事实。
        secret: callback route token 签名密钥。
        expected_write_fence_epoch: descriptor/route token 签发时的 fence。给出时必须与
            room 当前 fence 相等（AC 4.7：fence 提升后旧会话不得再写）。
        now_epoch: 覆盖当前时间（仅守卫用）。

    Returns:
        已校验的 :class:`CallbackRouteClaim`。
    """
    ct = contract or load_callback_contract()
    token = extract_bearer_token(authorization_header)
    claim = parse_callback_claims(token, secret=secret, contract=ct)

    # exp 由 jose 校验；这里额外做一次显式判据，理由是 jose 允许 leeway 且
    # `options` 一旦被改动（例如 verify_exp=False）就会静默失效。
    reference = now_epoch if now_epoch is not None else int(_now().timestamp())
    if claim.expires_at <= reference:
        raise CallbackTokenExpiredError(
            f"callback route token 已过期（exp={claim.expires_at} <= now={reference}）"
        )

    assert_url_binding(claim, callback_url=callback_url)

    # room 行绑定：claim 的三元组必须就是 room 行当前的三元组。
    if claim.room_id != room.room_id or claim.generation != int(room.generation):
        raise CallbackUrlBindingError(
            f"claim 的 room/generation ({claim.room_id}, {claim.generation}) 与 room 行 "
            f"({room.room_id}, {room.generation}) 不符"
        )
    if claim.doc_key != str(room.doc_key or "").strip():
        raise CallbackDocKeyMismatchError(
            f"claim.doc_key={claim.doc_key!r} 与 room 当前 doc_key={room.doc_key!r} 不符"
        )
    if not isinstance(payload_doc_key, str) or payload_doc_key.strip() != claim.doc_key:
        raise CallbackDocKeyMismatchError(
            f"callback payload.key={payload_doc_key!r} 必须等于 claim.doc_key="
            f"{claim.doc_key!r}（契约 url_binding.rule）"
        )
    if not doc_key_matches(doc_key=claim.doc_key, wp_id=room.wp_id, entry_id=room.entry_id):
        raise CallbackDocKeyMismatchError(
            f"doc_key={claim.doc_key!r} 不是由 room 的 (wp_id={room.wp_id}, "
            f"entry_id={room.entry_id!r}) 派生 —— 跨底稿/跨入口的 key 不得进入本 room"
        )

    # route credential 重算校验（确定性 uuid5，无需查表；rooms.py 唯一实现）。
    assert_route_credential(
        claim.route_credential.credential_id,
        room_id=room.room_id,
        generation=int(room.generation),
        doc_key=room.doc_key,
    )

    if not room.accepts_callback:
        raise CallbackGenerationStaleError(
            f"room {room.room_id} generation {room.generation} 已不接受 callback"
            "（superseded/closed）—— 旧代际 artifact 不得应用（AC 2.8）"
        )
    if (
        expected_write_fence_epoch is not None
        and int(expected_write_fence_epoch) != int(room.write_fence_epoch)
    ):
        raise CallbackGenerationStaleError(
            f"write fence 已提升（token={expected_write_fence_epoch} != room="
            f"{room.write_fence_epoch}）—— 有 participant 被撤销/代际旋转，"
            "旧 route 不得再写（AC 4.7 / 10.4）"
        )

    # 契约自证：participant-bound 授权若被改成允许，本模块立刻拒绝处理。
    if ct.multi_user.participant_bound_authorization_allowed:
        raise CallbackAuthorshipMisuseError(
            "契约把 participant_bound_callback_authorization 改成了 allowed —— "
            "Task 4 已实证 callback 是 room/generation 级服务事件，"
            "route participant / initiator / contributors 三者不同一"
        )
    return claim


# ═══════════════════════════════════════════════════════════════════════════
# 4. 签发（wiring/守卫 helper）
# ═══════════════════════════════════════════════════════════════════════════


def build_callback_url(
    *, base_url: str, path: str, claim: CallbackRouteClaim | None = None,
    room_id: uuid.UUID | None = None, generation: int | None = None,
    doc_key: str | None = None, route_credential_id: uuid.UUID | None = None,
) -> str:
    """按 URL 绑定规则组装 callback URL（四项一律进 query）。

    存在的理由是**对称**：`assert_url_binding` 解析四项，这里组装四项。两处各写一份
    参数名清单必然漂移，届时表现为「刚签的 URL 自己校验不过」。
    """
    if claim is not None:
        room_id = claim.room_id
        generation = claim.generation
        doc_key = claim.doc_key
        route_credential_id = claim.route_credential.credential_id
    if room_id is None or generation is None or not doc_key or route_credential_id is None:
        raise CallbackUrlBindingError("build_callback_url 必须给出全部四项绑定值")
    from urllib.parse import urlencode

    query = urlencode(
        {
            "room_id": str(room_id),
            "generation": str(generation),
            "doc_key": doc_key,
            "route_credential_id": str(route_credential_id),
        }
    )
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}?{query}"


def sign_callback_route_token(
    *,
    secret: str,
    room_id: uuid.UUID,
    generation: int,
    doc_key: str,
    route_credential_id: uuid.UUID,
    action: str,
    ttl_seconds: int,
    callback_token_id: uuid.UUID | None = None,
    audit_participant_hint: uuid.UUID | None = None,
    contract: CallbackContract | None = None,
    issued_at: int | None = None,
) -> str:
    """签发短 TTL callback route token（claim 常量与 enum 全部取自契约）。

    签名里同样**没有** user 入参：`audit_participant_hint` 是可选审计线索，名字与
    契约 `optional_claims.participant_id` 对齐，且它进的是 optional claim。
    """
    ct = contract or load_callback_contract()
    schema = ct.jwt
    if action not in schema.action_enum:
        raise CallbackClaimSchemaError(
            f"action={action!r} 不在契约 enum {list(schema.action_enum)} 内"
        )
    if ttl_seconds <= 0:
        raise CallbackClaimSchemaError("callback route token 必须有正的短 TTL（Requirement 10.7）")
    iat = issued_at if issued_at is not None else int(_now().timestamp())
    payload: dict[str, Any] = {
        "cbv": schema.claim_schema_version,
        "act": action,
        "room_id": str(room_id),
        "generation": int(generation),
        "doc_key": doc_key,
        "route_credential_id": str(route_credential_id),
        "callback_token_id": str(callback_token_id or uuid.uuid4()),
        "iat": iat,
        "exp": iat + int(ttl_seconds),
    }
    for key, expected in schema.claim_constants.items():
        if key == "cbv":
            continue
        payload[key] = expected
    if audit_participant_hint is not None:
        payload["participant_id"] = str(audit_participant_hint)
    return jwt.encode(payload, secret, algorithm=schema.algorithm)


__all__ = [
    "URL_BOUND_PARAMS",
    "CallbackRouteError",
    "CallbackTokenMissingError",
    "CallbackTokenSignatureError",
    "CallbackSecretMissingError",
    "CallbackTokenExpiredError",
    "CallbackClaimVersionError",
    "CallbackClaimSchemaError",
    "CallbackUrlBindingError",
    "CallbackDocKeyMismatchError",
    "CallbackGenerationStaleError",
    "CallbackAuthorshipMisuseError",
    "CallbackRouteClaim",
    "RoomRouteFacts",
    "extract_bearer_token",
    "parse_callback_claims",
    "assert_url_binding",
    "verify_callback_route",
    "build_callback_url",
    "sign_callback_route_token",
]
