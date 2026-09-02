# -*- coding: utf-8 -*-
"""Task 24（上半）：OnlyOffice Command Service `forcesave` 的**唯一出站落点**。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 24
Requirements: 4.1, 4.4, 4.7, 4.10, 5.5, 10.10
Properties: **P12 / P13 / P15 / P43 / P64**

═══ 为什么出站调用必须自成一个模块 ═══

AC 4.1 的措辞是顺序：「**先**在一个数据库事务中持久化冻结…的 forcesave request，
并创建 operation shell，**再**由后端调用 OnlyOffice Command Service」。Task 23 把前半段
做成了不可绕过的入口 :meth:`~.request_application.RequestApplicationService.freeze_and_persist_request`，
并**刻意让 `request_application.py` 的 import 图里不出现任何 HTTP/Command Service 符号**
（`test_task24`/`test_task23` 双侧都有结构判据）。于是后半段只能落在别处 —— 就是这里。

这个切分不是洁癖。它让「没落库就去调 OO」在**类型层**不可表达：
:meth:`CommandServiceClient.forcesave` 的第一个参数类型是
:class:`~.request_application.AcceptedRequest`，而该凭据只能由 Task 23 的入口产出，
且本模块在出站**之前**必须调用它的 :meth:`~.request_application.AcceptedRequest.assert_dispatchable`
（真查过库的「零 application + pre-correlation shell」自证）。

═══ HTTP 200 只代表 accepted ═══

Task 4 实测并写进契约（`command_service.http_semantics`）：

    `http_status_always_200_even_on_error: true`
    「必须解析 body 的 `error` 字段判成败；HTTP 200 不代表成功」

所以本模块**没有**任何「200 即成功」的路径：:class:`CommandDispatch` 只有
:attr:`CommandDispatch.outcome`（来自 body 的 `error` 经契约真值表映射），
而且它连一个叫 "saved"/"applied" 的字段都不提供 —— 想把命令回执当保存完成，
调用方得自己造字段，那会被 Property 12 的守卫看见。

═══ 契约是唯一真源，本模块不写第二份常量 ═══

契约 `timers.notes[0]` 是硬要求：

    「所有数值是 Task 4 定义的契约默认值，实现（Task 22/24）必须从本文件读取，
      不得在代码里另写常量。」

因此：

* **超时**取自 :class:`~.oo_contract.Timers`（`load_callback_contract().timers`）——
  本模块**不自己解析** `timers`，只解析别人没投影过的 `command_service` 小节。
  两处解析同一批数值就是漂移入口，`assert_timer_single_source` 把这条钉成判据。
* **返回码语义**取自 `command_service.return_codes[].platform_outcome / retryable /
  callback_expected`。Task 24 给契约补上了前两个**机器可读**字段：原本只有中文
  `platform_handling` 散文，而「按散文关键词猜分类」等于在代码里另写一份真值表。
  补字段是 additive 的（`schema_version` 仍为 1，Task 4 的守卫是子集校验）。

═══ 拒绝一律分型 ═══

🔴 本 spec 已为「两条拒绝共用一个 error_code」付过三次代价（Task 22 M04/M10、
Task 23 M25）：共用类型时先声明的那条永久不可达，定向变异判 GREEN。本模块的每一条
拒绝各自一个类型，且**互不为子类**（:func:`assert_refusals_are_disjoint` 逐对断言）。
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Final, Mapping, Protocol

from .models import RequestState, SyncDomainError, is_terminal
from .oo_contract import (
    CALLBACK_CONTRACT_PATH,
    CallbackContractError,
    Timers,
    load_callback_contract,
)
from .request_application import AcceptedRequest

__all__ = [
    "CommandDispatch",
    "CommandOutcome",
    "CommandRequest",
    "CommandResponse",
    "CommandServiceClient",
    "CommandServiceConfigError",
    "CommandServiceCredentialError",
    "CommandServicePolicy",
    "CommandServiceProtocolError",
    "CommandServiceTargetMismatchError",
    "CommandServiceTransportError",
    "CommandTarget",
    "CommandTransport",
    "CommandReturnCodeRule",
    "DestroyDecision",
    "DestroyVerdict",
    "DispatchRecord",
    "UnknownCommandReturnCodeError",
    "assert_refusals_are_disjoint",
    "assert_timer_single_source",
    "build_httpx_command_transport",
    "classify_editor_destroy",
    "load_command_service_policy",
    "sign_command_token",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 拒绝类型（逐条分型，互不为子类）
# ═══════════════════════════════════════════════════════════════════════════


class CommandServiceDomainError(SyncDomainError):
    """Task 24 出站域基类。"""

    error_code = "command_service_error"


class CommandServiceConfigError(CommandServiceDomainError):
    """配置缺失：`ONLYOFFICE_URL` 为空或 JWT secret 缺失。

    🔴 **不 fail-open**。平台里已有的旧实现（`wp_onlyoffice_router._sign_jwt`）在
    secret 缺失时 `return ""`，等于「没配密钥就不签名」—— 那是把鉴权降级成可选。
    契约 `command_service.jwt.required = true`，故此处只能拒绝。
    """

    error_code = "command_service_not_configured"


class CommandServiceCredentialError(CommandServiceDomainError):
    """出站入参不是 Task 23 的 :class:`AcceptedRequest` 凭据。

    与 :class:`CommandServiceConfigError` 分型：前者是「调用方没落库就想调 OO」
    （AC 4.1 的顺序违规），后者是「环境没配好」。合成一类会让顺序判据无法被证明。
    """

    error_code = "command_service_credential_invalid"


class CommandServiceTargetMismatchError(CommandServiceDomainError):
    """doc_key/room/generation 与凭据里冻结的 request 不属于同一 room 代际。

    单独分型的理由：它是「用 A 的 request id 配 B 的 doc_key」这类串线，
    与凭据本身合法但形态不对（:class:`CommandServiceCredentialError`）是两件事。
    """

    error_code = "command_service_target_mismatch"


class CommandServiceTransportError(CommandServiceDomainError):
    """网络/超时/非 200 —— 传输层异常，未拿到可解释的 body。"""

    error_code = "command_service_transport_failed"


class CommandServiceProtocolError(CommandServiceDomainError):
    """拿到了响应但 body 不是可解释的 JSON 对象，或缺 `error` 字段。

    与 :class:`UnknownCommandReturnCodeError` 分型：前者「读不出 error」，
    后者「读出了但契约没登记」。契约 `unknown_status_policy` 的同一条精神：
    未知必须 fail visible，且两种未知的诊断动作不同（前者查网关/代理，
    后者补契约行）。
    """

    error_code = "command_service_protocol_invalid"


class UnknownCommandReturnCodeError(CommandServiceDomainError):
    """契约未登记的返回码 —— fail visible，不得按最近似码猜处理。"""

    error_code = "command_service_unknown_return_code"

    def __init__(self, code: object, known: tuple[int, ...]) -> None:
        super().__init__(
            f"Command Service 返回未登记的 error={code!r}（契约已登记 {list(known)}）——"
            "未知返回码必须 fail visible，不得按最近似码猜处理"
        )
        self.code = code
        self.known = known


#: 全部拒绝类型。:func:`assert_refusals_are_disjoint` 的分母。
_REFUSALS: Final[tuple[type[CommandServiceDomainError], ...]] = (
    CommandServiceConfigError,
    CommandServiceCredentialError,
    CommandServiceTargetMismatchError,
    CommandServiceTransportError,
    CommandServiceProtocolError,
    UnknownCommandReturnCodeError,
)


def assert_refusals_are_disjoint() -> tuple[str, ...]:
    """逐对断言拒绝类型**互不为子类**，返回类型名清单（守卫的分母）。

    只断言「每条拒绝都有自己的 error_code」不够：两个类共用 code 会被发现，但
    `class B(A)` 这种「A 的 except 顺手吃掉 B」不会 —— 而后者正是 Task 22 M04/M10
    的真实形态（`pytest.raises(A)` 在 B 抛出时也通过 ⇒ 先声明的那条永久不可达）。
    """
    names = tuple(sorted(t.__name__ for t in _REFUSALS))
    codes: dict[str, str] = {}
    for t in _REFUSALS:
        code = str(getattr(t, "error_code", ""))
        if not code:
            raise CommandServiceConfigError(f"{t.__name__} 未声明 error_code")
        if code in codes:
            raise CommandServiceConfigError(
                f"{t.__name__} 与 {codes[code]} 共用 error_code={code!r} —— "
                "两条拒绝共用一个 code 会让先声明的那条永久不可达"
            )
        codes[code] = t.__name__
    for a in _REFUSALS:
        for b in _REFUSALS:
            if a is b:
                continue
            if issubclass(a, b):
                raise CommandServiceConfigError(
                    f"{a.__name__} 是 {b.__name__} 的子类 —— "
                    f"捕获 {b.__name__} 会顺手吃掉 {a.__name__}，两条拒绝无法被分别证明"
                )
    return names


# ═══════════════════════════════════════════════════════════════════════════
# 2. 契约投影：只解析 `command_service` 小节
# ═══════════════════════════════════════════════════════════════════════════


class CommandOutcome(str, Enum):
    """`command_service.return_codes[].platform_outcome` 的封闭域。

    值与契约字面量一一对应；契约出现本枚举没有的值时 :func:`load_command_service_policy`
    直接抛（fail closed），而不是落进一个「其他」桶 —— 「其他」桶会让新返回码悄悄
    获得旧语义。
    """

    accepted = "accepted"
    """error 0：命令已排入。**只**标 accepted，绝不等于保存完成（AC 4.1）。"""

    no_changes = "no_changes"
    """error 4：距上次保存无新变更。契约明确「直接放行离开；不得无限等 callback」。"""

    doc_not_online = "doc_not_online"
    """error 1：doc key 不在线。提示重开编辑器，不进入 waiting_callback。"""

    configuration_error = "configuration_error"
    """error 2/6：callback url 或 token 配置故障。落 error 并告警，不重试到超时。"""

    server_error = "server_error"
    """error 3：OO 内部错误。可重试，保持 OO 模式。"""

    implementation_defect = "implementation_defect"
    """error 5：命令不正确 —— 平台自身缺陷，落 error 并告警。"""


@dataclass(frozen=True)
class CommandReturnCodeRule:
    """一行返回码真值表。字段与契约 `return_codes[]` 一一对应。"""

    error: int
    outcome: CommandOutcome
    callback_expected: bool
    retryable: bool
    oo94_observed: bool
    meaning: str
    platform_handling: str

    @property
    def terminal_without_callback(self) -> bool:
        """该返回码是否「不会再有 callback，request 就地终结」。

        它不是 `not callback_expected` 的同义词 —— :attr:`CommandOutcome.server_error`
        也没有 callback，但它**可重试**，request 不得就地终结（契约「保持 OO 模式」）。
        """
        return not self.callback_expected and not self.retryable


@dataclass(frozen=True)
class CommandServicePolicy:
    """`command_service` 小节 + 复用自 :class:`Timers` 的超时。"""

    endpoint_template: str
    jwt_required: bool
    jwt_header: str
    jwt_scheme: str
    jwt_claim_shape: str
    http_status_always_200: bool
    codes: Mapping[int, CommandReturnCodeRule]
    timers: Timers

    @property
    def known_codes(self) -> tuple[int, ...]:
        return tuple(sorted(self.codes))

    def rule_for(self, error: object) -> CommandReturnCodeRule:
        """按 body 的 `error` 取规则；未登记即 :class:`UnknownCommandReturnCodeError`。

        `error` 声明为 `object`：它来自 OO 的响应体，可能是字符串、浮点或 `None`。
        只认**严格 int**（`bool` 也拒 —— `True == 1` 会把布尔悄悄读成 error 1）。
        """
        if isinstance(error, bool) or not isinstance(error, int):
            raise UnknownCommandReturnCodeError(error, self.known_codes)
        rule = self.codes.get(int(error))
        if rule is None:
            raise UnknownCommandReturnCodeError(error, self.known_codes)
        return rule

    def endpoint(self, onlyoffice_url: str) -> str:
        """把契约里的 `{ONLYOFFICE_URL}` 占位替换成实际基址。"""
        base = str(onlyoffice_url or "").strip().rstrip("/")
        if not base:
            raise CommandServiceConfigError(
                "ONLYOFFICE_URL 为空 —— 不得回退到「由调用方/payload 决定 host」，"
                "只能拒绝发出 Command Service 请求"
            )
        template = self.endpoint_template
        if "{ONLYOFFICE_URL}" not in template:
            raise CallbackContractError(
                f"command_service.endpoint 缺 {{ONLYOFFICE_URL}} 占位: {template!r}"
            )
        _method, _sep, path = template.partition(" ")
        target = (path or template).replace("{ONLYOFFICE_URL}", base)
        return target


def _require(raw: Mapping[str, Any], key: str, expected: type, where: str) -> Any:
    if key not in raw:
        raise CallbackContractError(f"{where} 缺键 {key!r}")
    value = raw[key]
    if expected is int and isinstance(value, bool):
        raise CallbackContractError(f"{where}.{key} 应为 {expected.__name__}，实得 bool")
    if not isinstance(value, expected):
        raise CallbackContractError(
            f"{where}.{key} 应为 {expected.__name__}，实得 {type(value).__name__}"
        )
    if expected is str and not str(value).strip():
        raise CallbackContractError(f"{where}.{key} 不得为空串")
    return value


def _parse_return_codes(raw: Mapping[str, Any]) -> Mapping[int, CommandReturnCodeRule]:
    rows = _require(raw, "return_codes", list, "command_service")
    if not rows:
        raise CallbackContractError("command_service.return_codes 为空")
    out: dict[int, CommandReturnCodeRule] = {}
    for idx, row in enumerate(rows):
        where = f"command_service.return_codes[{idx}]"
        if not isinstance(row, dict):
            raise CallbackContractError(f"{where} 不是对象")
        error = _require(row, "error", int, where)
        outcome_raw = _require(row, "platform_outcome", str, where)
        try:
            outcome = CommandOutcome(outcome_raw)
        except ValueError as exc:
            raise CallbackContractError(
                f"{where}.platform_outcome={outcome_raw!r} 不在封闭域 "
                f"{[o.value for o in CommandOutcome]} 内 —— 未知语义不得落进「其他」桶"
            ) from exc
        rule = CommandReturnCodeRule(
            error=int(error),
            outcome=outcome,
            callback_expected=bool(_require(row, "callback_expected", bool, where)),
            retryable=bool(_require(row, "retryable", bool, where)),
            oo94_observed=bool(_require(row, "oo94_observed", bool, where)),
            meaning=str(_require(row, "meaning", str, where)),
            platform_handling=str(_require(row, "platform_handling", str, where)),
        )
        if rule.error in out:
            raise CallbackContractError(f"{where}.error={rule.error} 重复登记")
        if rule.outcome is CommandOutcome.accepted and not rule.callback_expected:
            raise CallbackContractError(
                f"{where}: outcome=accepted 却声明不会有 callback —— "
                "accepted 的全部意义就是「等 callback」（AC 4.1/4.2）"
            )
        if rule.outcome is not CommandOutcome.accepted and rule.callback_expected:
            raise CallbackContractError(
                f"{where}: 非 accepted 却声明会有 callback —— 前端会无限等待"
            )
        out[rule.error] = rule
    return out


def _parse_policy(raw: Mapping[str, Any], *, timers: Timers) -> CommandServicePolicy:
    cs = _require(raw, "command_service", dict, "<root>")
    jwt_raw = _require(cs, "jwt", dict, "command_service")
    http_raw = _require(cs, "http_semantics", dict, "command_service")
    shapes = _require(jwt_raw, "accepted_claim_shapes", list, "command_service.jwt")
    platform_rule = str(_require(jwt_raw, "platform_rule", str, "command_service.jwt"))
    # 契约明说「平台统一使用 payload_wrapped，不得因 flat 也被接受而放宽签名要求」。
    # 从 `platform_rule` 里定位 shape，而不是在代码里写死 "payload_wrapped"：
    # 后者会让契约改了平台还按老 shape 签。
    chosen = [s for s in shapes if isinstance(s, str) and s and s in platform_rule]
    if len(chosen) != 1:
        raise CallbackContractError(
            "command_service.jwt.platform_rule 必须**恰好**点名 accepted_claim_shapes "
            f"中的一种（实得 {chosen} / 候选 {shapes}）—— 平台不得同时接受多种 shape"
        )
    if not _require(jwt_raw, "required", bool, "command_service.jwt"):
        raise CallbackContractError(
            "command_service.jwt.required=false —— Command Service 出站必须签名，"
            "契约不得声明鉴权可选"
        )
    if not _require(http_raw, "http_status_always_200_even_on_error", bool, "command_service.http_semantics"):
        raise CallbackContractError(
            "契约声明 HTTP 状态码可判成败 —— Task 4 实测 OO 9.4 恒返回 200，"
            "该声明会让实现把 200 当成功（AC 4.1 明令禁止）"
        )
    return CommandServicePolicy(
        endpoint_template=str(_require(cs, "endpoint", str, "command_service")),
        jwt_required=True,
        jwt_header=str(_require(jwt_raw, "header", str, "command_service.jwt")),
        jwt_scheme=str(_require(jwt_raw, "scheme", str, "command_service.jwt")),
        jwt_claim_shape=chosen[0],
        http_status_always_200=True,
        codes=_parse_return_codes(cs),
        timers=timers,
    )


_LOCK: Final[threading.Lock] = threading.Lock()
_CACHE: dict[str, Any] = {"mtime": None, "value": None}


def load_command_service_policy(
    path: Path | None = None, *, force: bool = False
) -> CommandServicePolicy:
    """加载 `command_service` 投影（mtime 热重载，与 :func:`load_callback_contract` 同约定）。

    **超时不在这里解析** —— 直接取 :func:`load_callback_contract` 的
    :class:`Timers`。同一批数值解析两遍就是漂移入口（契约 `timers.notes[0]`）。
    """
    target = Path(path) if path is not None else CALLBACK_CONTRACT_PATH
    try:
        mtime = target.stat().st_mtime_ns
    except OSError as exc:
        raise CallbackContractError(f"读不到真值表 {target}: {exc}") from exc
    with _LOCK:
        if not force and _CACHE["mtime"] == (str(target), mtime):
            cached = _CACHE["value"]
            if isinstance(cached, CommandServicePolicy):
                return cached
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CallbackContractError(f"真值表 {target} 解析失败: {exc}") from exc
    if not isinstance(raw, dict):
        raise CallbackContractError(f"真值表 {target} 顶层必须是对象")
    timers = load_callback_contract(target, force=force).timers
    policy = _parse_policy(raw, timers=timers)
    with _LOCK:
        _CACHE["mtime"] = (str(target), mtime)
        _CACHE["value"] = policy
    return policy


def assert_timer_single_source(policy: CommandServicePolicy) -> None:
    """本模块的 :class:`Timers` 必须与 :func:`load_callback_contract` 逐项等值。

    判据落在**对象等值**而不是源码字符串：有人在本模块另抄一份 `timers` 解析时，
    只要抄错任何一项就会被这条抓到；抄对了也仍然是两份（那由
    `test_task24_*::test_command_service_module_does_not_reparse_timers`
    的源码判据管）。两条一起才是完整的「单一真源」。
    """
    canonical = load_callback_contract().timers
    if policy.timers != canonical:
        raise CallbackContractError(
            "command_service policy 的 timers 与 oo_contract 的不等值 —— "
            f"{policy.timers!r} != {canonical!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 出站请求 / 传输
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CommandTarget:
    """出站目标：doc_key 与它所属的 room 代际。

    做成一个对象而不是三个散参：`forcesave` 要断言「凭据里冻结的 request 与本次
    doc_key 属于同一 room/generation」。散参形态下调用点很容易把 A 的 request id
    配上 B 的 doc_key（两者都是合法值，DB 层也拦不住），而 OO 只认 doc_key ——
    结果是 B 的文档被强存，却记在 A 的 request 上。
    """

    room_id: uuid.UUID
    generation: int
    doc_key: str

    def __post_init__(self) -> None:
        if not str(self.doc_key or "").strip():
            raise CommandServiceTargetMismatchError("doc_key 不得为空")


@dataclass(frozen=True)
class CommandRequest:
    """交给 transport 的**已固定**请求。transport 不得再改 body/headers/超时。"""

    url: str
    body: Mapping[str, Any]
    headers: Mapping[str, str]
    timeout_seconds: float


@dataclass(frozen=True)
class CommandResponse:
    """transport 返回的响应（只暴露判据需要的两项）。"""

    status_code: int
    text: str


class CommandTransport(Protocol):
    """HTTP 落点。生产实现见 :func:`build_httpx_command_transport`。

    真实 OO 9.4 的端到端验收是 Task 44/70；本任务的判据全部用**可编程 stand-in**
    （测试内的确定性 transport）来 discharge，这一点在证据 README 里明写。
    """

    async def post(self, request: CommandRequest) -> CommandResponse: ...


@dataclass
class _HttpxCommandTransport:
    """生产 transport：httpx，`trust_env=False`、不跟随重定向、单段超时。"""

    verify: bool = True

    async def post(self, request: CommandRequest) -> CommandResponse:
        import httpx

        timeout = httpx.Timeout(
            connect=float(request.timeout_seconds),
            read=float(request.timeout_seconds),
            write=float(request.timeout_seconds),
            pool=float(request.timeout_seconds),
        )
        client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            # 与 callback 下载同因：Windows 未关 trust_env 时会读系统代理并劫持请求
            # （Task 4 实测 127.0.0.1:7897 返回 502）。出站命令带 JWT，尤其不能流经第三方。
            trust_env=False,
            verify=self.verify,
        )
        try:
            resp = await client.post(
                request.url, json=dict(request.body), headers=dict(request.headers)
            )
            return CommandResponse(status_code=int(resp.status_code), text=resp.text)
        except httpx.HTTPError as exc:
            raise CommandServiceTransportError(
                f"Command Service 传输失败（{type(exc).__name__}）: {exc}"
            ) from exc
        finally:
            await client.aclose()


def build_httpx_command_transport(*, verify: bool = True) -> CommandTransport:
    """生产 transport 工厂（唯一构造点，供接线与判据共同引用）。"""
    return _HttpxCommandTransport(verify=verify)


def sign_command_token(
    *,
    secret: str,
    body: Mapping[str, Any],
    ttl_seconds: int,
    claim_shape: str,
    issued_at: int | None = None,
) -> str:
    """签短期出站 token。

    `ttl_seconds` 由调用方从契约 `timers.command_service_http_timeout_seconds` 取：
    token 的有效期恰好覆盖「这次调用最长可能持续多久」。写成入参而不是在函数里读契约，
    是为了让「TTL 从哪来」在调用点可见、可变异。

    `claim_shape` 同样是入参且**必须**是契约 `platform_rule` 点名的那一种。Task 4 实测
    OO 对 `jwt({"payload": body})` 与 `jwt(body)` 都放行，但契约明确
    「不得因 flat 也被接受而放宽签名要求」。
    """
    from jose import jwt as jose_jwt

    if not str(secret or "").strip():
        raise CommandServiceConfigError(
            "Command Service JWT secret 缺失 —— 契约 `command_service.jwt.required=true`，"
            "不得像旧实现那样在无密钥时返回空 token（等于把鉴权降级成可选）"
        )
    if int(ttl_seconds) <= 0:
        raise CommandServiceConfigError(
            f"出站 token 必须有正的短 TTL，实得 {ttl_seconds}"
        )
    iat = int(issued_at if issued_at is not None else _now().timestamp())
    if claim_shape == "payload_wrapped":
        claims: dict[str, Any] = {"payload": dict(body)}
    elif claim_shape == "flat_body":
        claims = dict(body)
    else:
        raise CallbackContractError(
            f"未知 claim shape {claim_shape!r} —— 只能是契约 accepted_claim_shapes 之一"
        )
    claims["iat"] = iat
    claims["exp"] = iat + int(ttl_seconds)
    return jose_jwt.encode(claims, secret, algorithm="HS256")


# ═══════════════════════════════════════════════════════════════════════════
# 4. 出站结果
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CommandDispatch:
    """一次 Command Service 调用的**可审计回执**。

    🔴 刻意**没有** `saved` / `applied` / `success` 字段。AC 4.1 末句：
    「不得把 `customization.forcesave=true` 或 Command Service HTTP 200 当成保存完成」。
    只要这里出现一个布尔叫「成功」，调用点就会拿它当保存完成 —— 于是本类只提供
    「命令被接受了吗」（:attr:`accepted`）与「还会不会有 callback」
    （:attr:`awaits_callback`）两个语义明确的判定。
    """

    outcome: CommandOutcome
    error_code: int
    http_status: int
    callback_expected: bool
    retryable: bool
    forcesave_request_id: uuid.UUID
    operation_id: uuid.UUID
    doc_key: str
    dispatched_at: datetime
    platform_handling: str

    @property
    def accepted(self) -> bool:
        """命令已排入 —— 仅此而已，**不代表**文件已耐久或内容已应用。"""
        return self.outcome is CommandOutcome.accepted

    @property
    def awaits_callback(self) -> bool:
        return bool(self.callback_expected)

    @property
    def terminal_without_callback(self) -> bool:
        return not self.callback_expected and not self.retryable


@dataclass(frozen=True)
class DispatchRecord:
    """「先落库、再出站」这一对事实的载体（供上层与证据引用）。"""

    accepted: AcceptedRequest
    dispatch: CommandDispatch


class CommandServiceClient:
    """Command Service 出站客户端。**不碰数据库**、**不 commit**。

    不碰 DB 是刻意的：本类只负责「把已落库的 request 送出去」。它一旦能写库，
    「先落库再出站」就退化成同一个对象内部的两行代码顺序，而顺序在代码里没有类型。
    """

    def __init__(
        self,
        *,
        onlyoffice_url: str,
        jwt_secret: str,
        transport: CommandTransport,
        policy: CommandServicePolicy | None = None,
    ) -> None:
        self._policy = policy if policy is not None else load_command_service_policy()
        assert_timer_single_source(self._policy)
        self._url = str(onlyoffice_url or "").strip()
        self._secret = str(jwt_secret or "")
        self._transport = transport

    @property
    def policy(self) -> CommandServicePolicy:
        return self._policy

    async def forcesave(
        self,
        accepted: AcceptedRequest,
        *,
        target: CommandTarget,
        issued_at: int | None = None,
    ) -> CommandDispatch:
        """出站 `c=forcesave`（AC 4.1 的「**再**」那一半）。

        顺序固定，前三步都在网络之前：

        1. :meth:`AcceptedRequest.assert_dispatchable` —— 凭据自证（shell 仍是
           pre-correlation、库里零 application）。**必须**在出站前调用：
           它是「已落库」的唯一凭证，跳过它就等于回到「先调 OO 再落库」；
        2. target 与凭据里冻结的 request 同 room/generation；
        3. 签短期 JWT（TTL 取契约 HTTP 超时）；
        4. POST，超时取契约；
        5. 解析 body 的 `error` 并按契约真值表分类 —— HTTP 200 **不**参与成败判定。
        """
        if not isinstance(accepted, AcceptedRequest):
            raise CommandServiceCredentialError(
                "forcesave 只接受 Task 23 的 AcceptedRequest 凭据，实得 "
                f"{type(accepted).__name__} —— 「先落库再调 Command Service」"
                "由参数类型强制（AC 4.1）"
            )
        accepted.assert_dispatchable()
        request = accepted.request
        same_scope = request.room_id == target.room_id and int(
            request.generation
        ) == int(target.generation)
        if not same_scope:
            raise CommandServiceTargetMismatchError(
                f"凭据里的 request 属于 room={request.room_id}/gen={request.generation}，"
                f"本次 target 是 room={target.room_id}/gen={target.generation} —— "
                "doc_key 与 request 必须同一 room 代际"
            )
        if request.initiated_by_participant_id is None:
            raise CommandServiceCredentialError(
                "request 的 initiating participant 为空 —— null initiator 必须在 "
                "Command Service **之前**被拒（AC 10.10：system/route identity "
                "不可替代用户授权）"
            )

        # Task 4 实证：Command Service 请求体只含 `c` / `key` / `userdata`
        # （`commands.jsonl`）；OO 侧没有「发起人」字段，所以 request id 必须由
        # `userdata` 带回来，callback 才能 request-first 精确绑定（AC 4.3）。
        body: dict[str, Any] = {
            "c": "forcesave",
            "key": target.doc_key,
            "userdata": json.dumps(
                {"request_id": str(request.id), "operation_id": str(accepted.operation.id)},
                ensure_ascii=False,
                sort_keys=True,
            ),
        }
        timeout = int(self._policy.timers.command_service_http_timeout_seconds)
        token = sign_command_token(
            secret=self._secret,
            body=body,
            ttl_seconds=timeout,
            claim_shape=self._policy.jwt_claim_shape,
            issued_at=issued_at,
        )
        headers = {
            self._policy.jwt_header: f"{self._policy.jwt_scheme} {token}",
            "Content-Type": "application/json",
        }
        response = await self._transport.post(
            CommandRequest(
                url=self._policy.endpoint(self._url),
                body=body,
                headers=headers,
                timeout_seconds=float(timeout),
            )
        )
        return self._classify(response, accepted=accepted, target=target)

    def _classify(
        self,
        response: CommandResponse,
        *,
        accepted: AcceptedRequest,
        target: CommandTarget,
    ) -> CommandDispatch:
        """把响应映射成回执。**HTTP 状态码不参与成败判定。**

        非 200 归 transport 层异常而不是「某个 error 码」：契约实测 OO 恒返回 200，
        所以非 200 意味着请求没到 OO（网关/代理/反代配置），诊断动作完全不同。
        """
        if int(response.status_code) != 200:
            raise CommandServiceTransportError(
                f"Command Service 返回 HTTP {response.status_code} —— 契约实测 OO 9.4 恒返 200，"
                "非 200 说明请求未达 OO（网关/代理/反代），不得按返回码语义处理"
            )
        try:
            parsed = json.loads(response.text)
        except ValueError as exc:
            raise CommandServiceProtocolError(
                f"Command Service 响应不是合法 JSON: {response.text[:200]!r}"
            ) from exc
        if not isinstance(parsed, dict):
            raise CommandServiceProtocolError(
                f"Command Service 响应顶层不是对象: {type(parsed).__name__}"
            )
        if "error" not in parsed:
            raise CommandServiceProtocolError(
                "Command Service 响应缺 `error` 字段 —— "
                "契约要求必须解析 body 的 error 判成败，缺失不得默认成功"
            )
        rule = self._policy.rule_for(parsed.get("error"))
        return CommandDispatch(
            outcome=rule.outcome,
            error_code=rule.error,
            http_status=int(response.status_code),
            callback_expected=rule.callback_expected,
            retryable=rule.retryable,
            forcesave_request_id=accepted.request.id,
            operation_id=accepted.operation.id,
            doc_key=target.doc_key,
            dispatched_at=_now(),
            platform_handling=rule.platform_handling,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. editor destroy 闸 / 超时保持 OO（Property 13 / AC 4.4）
# ═══════════════════════════════════════════════════════════════════════════


class DestroyVerdict(str, Enum):
    """销毁编辑器的裁决。每一条都独立可变异、独立可断言。"""

    allowed_request_terminal = "allowed_request_terminal"
    """对应 request 已达 durable terminal ⇒ 可销毁（AC 4.2 的时序末端）。"""

    allowed_no_changes = "allowed_no_changes"
    """OO 返回 error 4「无新变更」⇒ 契约明确「直接放行离开」。"""

    allowed_recovery_case = "allowed_recovery_case"
    """无 request（浏览器崩溃 / OO 自发 close）但 incoming 已 durable 且已建 recovery
    case ⇒ 只允许这一种恢复路径（AC 4.10 末段 / 5.8）。"""

    refused_request_open = "refused_request_open"
    """request 仍未终结（accepted / waiting callback，且在 grace 内）⇒ 保持 OO。"""

    refused_timeout_keep_oo = "refused_timeout_keep_oo"
    """等待已超过契约超时 ⇒ 落可重试 timeout 但**保持 OO 模式**（Property 13）。"""

    refused_retryable_error = "refused_retryable_error"
    """OO 返回可重试错误（error 3）⇒ 保持 OO 并允许重试。"""

    refused_no_request_no_incoming = "refused_no_request_no_incoming"
    """无 request 且 incoming 未 durable ⇒ 既不能销毁也不能造 operation。"""


@dataclass(frozen=True)
class DestroyDecision:
    """裁决 + 两个前端必须遵守的布尔。"""

    verdict: DestroyVerdict
    keep_onlyoffice: bool
    reload_html_allowed: bool
    reason: str

    @property
    def allowed(self) -> bool:
        return self.verdict.value.startswith("allowed_")


@dataclass(frozen=True)
class DestroyRequestFacts:
    """destroy 判定需要的 request 事实（只读投影，不含内容）。"""

    request_id: uuid.UUID
    state: RequestState
    outcome: CommandOutcome | None
    waited_seconds: float


def classify_editor_destroy(
    *,
    request: DestroyRequestFacts | None,
    incoming_durable: bool,
    recovery_case_open: bool,
    timers: Timers,
) -> DestroyDecision:
    """「对应 request 达 durable terminal 后才允许 editor destroy」的唯一判定点。

    分支顺序固定，每条独立可变异：

    0. 无 request ⇒ 只有「incoming 已 durable 且已建 recovery case」可放行
       （浏览器崩溃 / OO 自发 close）；否则拒绝且**不得**伪造 operation；
    1. OO 返回可重试错误 ⇒ 保持 OO（契约「request 落可重试 error；保持 OO 模式」）；
    2. `no_changes` ⇒ 放行（契约「直接放行离开；不得无限等 callback」）；
    3. request 已 terminal（FSM 出边为空）⇒ 放行；
    4. 等待超过 `forcesave_callback_wait_timeout_seconds` ⇒ 拒绝但保持 OO
       （Property 13：mode 仍是 OO、reloadHtml 次数为 0）；
    5. 其余 ⇒ 仍在等 callback，拒绝且保持 OO。

    🔴 第 1 步在第 3 步之前：`RequestState.rejected` 也是 FSM terminal，若先判
    terminal，可重试错误会被读成「已终结，放心走」—— 内容随之丢失。
    """
    if request is None:
        if incoming_durable and recovery_case_open:
            return DestroyDecision(
                verdict=DestroyVerdict.allowed_recovery_case,
                keep_onlyoffice=False,
                reload_html_allowed=False,
                reason=(
                    "无 request（崩溃/OO 自发 close）但 incoming 已 durable 且已建 "
                    "recovery case —— 只允许经 authorization-first claim 恢复，"
                    "不得直接 reload HTML"
                ),
            )
        return DestroyDecision(
            verdict=DestroyVerdict.refused_no_request_no_incoming,
            keep_onlyoffice=True,
            reload_html_allowed=False,
            reason=(
                "无 request 且 incoming 未 durable —— 不得销毁编辑器，"
                "也不得伪造 operation（AC 5.8）"
            ),
        )
    if request.outcome is not None and request.outcome is CommandOutcome.server_error:
        return DestroyDecision(
            verdict=DestroyVerdict.refused_retryable_error,
            keep_onlyoffice=True,
            reload_html_allowed=False,
            reason=f"Command Service 返回可重试错误（{request.outcome.value}）—— 保持 OO 模式",
        )
    if request.outcome is CommandOutcome.no_changes:
        return DestroyDecision(
            verdict=DestroyVerdict.allowed_no_changes,
            keep_onlyoffice=False,
            reload_html_allowed=True,
            reason="OO 报告距上次保存无新变更 —— 契约明确直接放行离开，不得无限等 callback",
        )
    if is_terminal("request", request.state):
        return DestroyDecision(
            verdict=DestroyVerdict.allowed_request_terminal,
            keep_onlyoffice=False,
            reload_html_allowed=True,
            reason=f"request 已达 durable terminal（{request.state.value}）",
        )
    if float(request.waited_seconds) >= float(
        timers.forcesave_callback_wait_timeout_seconds
    ):
        return DestroyDecision(
            verdict=DestroyVerdict.refused_timeout_keep_oo,
            keep_onlyoffice=True,
            reload_html_allowed=False,
            reason=(
                f"已等待 {request.waited_seconds}s ≥ 契约超时 "
                f"{timers.forcesave_callback_wait_timeout_seconds}s —— operation 落可重试 "
                "timeout，但 mode 保持 OO 且不得 reloadHtml（Property 13 / AC 4.4）"
            ),
        )
    return DestroyDecision(
        verdict=DestroyVerdict.refused_request_open,
        keep_onlyoffice=True,
        reload_html_allowed=False,
        reason=(
            f"request state={request.state.value} 尚未终结（已等待 "
            f"{request.waited_seconds}s，grace "
            f"{timers.in_flight_grace_seconds}s）—— 保持 OO 并继续轮询"
        ),
    )
