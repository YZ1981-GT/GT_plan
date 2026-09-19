# -*- coding: utf-8 -*-
"""OnlyOffice callback / Command Service 真值表的**生产侧**加载器。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 21
Requirements: 4.7, 4.9, 4.10, 10.2, 10.3, 10.4；Property 15 / 63

═══ 为什么必须有这个模块 ═══

Task 4 把 OO 9.4 的真实行为固化成 `backend/data/onlyoffice_callback_state_contract.json`
（status 真值表 / userdata 规则 / JWT claim schema / 下载安全策略 / 计时器 / 多人语义 /
correlation 判据）。但在 Task 4 收尾时，**读它的只有三个守卫和一个变异脚本**：

    backend/tests/test_workpaper_callback_state_contract.py
    backend/tests/test_workpaper_callback_download_security.py
    backend/scripts/diagnose/mutate_task4_callback_contract_guards.py

生产代码零消费方。这正是 memory 里记的「假绿第①源：additive 注入即死代码」的形状 ——
契约再详细，只要没有唯一消费方，Task 21/22/24 就会各自在代码里另写一份
`TIMEOUT = 120` / `MAX_BYTES = 200 * 1024 * 1024`，然后契约与实现悄悄漂移。契约自己的
`timers.notes[0]` 已经把这条写成硬要求：

    「所有数值是 Task 4 定义的契约默认值，实现（Task 22/24）必须从本文件读取，
      不得在代码里另写常量。」

所以本模块是**唯一**解析入口：room/request/callback/Command Service 一律经它取值，
守卫再反向断言「同步域内除本模块外不得出现这些数值字面量」。

═══ fail-closed 的三处 ═══

1. **schema/claim 版本未知即拒**。契约的 `jwt_claim_schema.unknown_or_missing_version`
   = `reject_before_download`，所以 :func:`load_callback_contract` 见到不认识的
   `schema_version` / `claim_schema_version` 直接抛，而不是「按已知字段尽力解析」。
2. **未知 callback status 抛专属异常**。:meth:`CallbackContract.status_rule` 对未登记
   status 抛 :class:`UnknownCallbackStatusError`，与「契约文件坏了」的
   :class:`CallbackContractError` **分成两个类型**：共用一个类型时，把 status 表清空
   也会被「文件非法」分支遮蔽，变异检验判 GREEN。
3. **不提供任何默认值**。没有 `dict.get(..., 120)` 这类兜底 —— 缺键即抛。契约缺字段
   属于「真源坏了」，用兜底值继续跑等于把错值锁进运行态。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT
from app.services.workpaper_sync.models import SyncDomainError

#: Task 4 真值表（唯一真源）。本模块只读，永不写。
CALLBACK_CONTRACT_PATH: Final[Path] = (
    BACKEND_ROOT / "data" / "onlyoffice_callback_state_contract.json"
)

#: 本模块支持的契约 schema 版本。契约升级必须同步改这里并复核解析逻辑。
SUPPORTED_SCHEMA_VERSION: Final[int] = 1

#: 本模块支持的 JWT claim schema 版本（契约 `jwt_claim_schema.claim_schema_version`）。
SUPPORTED_CLAIM_SCHEMA_VERSION: Final[int] = 1


class CallbackContractError(SyncDomainError):
    """真值表缺失 / 非法 / 版本不支持（fail closed，不得 fallback 到默认值）。"""

    error_code = "callback_contract_invalid"


class UnknownCallbackStatusError(SyncDomainError):
    """收到未登记的 callback status（Requirement 4.9：fail visible）。

    🔴 刻意与 :class:`CallbackContractError` 分型。二者都让调用方「拿不到规则」，
    但语义完全不同：本异常是**运行时收到了没见过的 status**（要留原始 payload +
    告警 + delivery 落 error），前者是**契约文件本身坏了**（部署/真源问题）。
    """

    error_code = "callback_status_unknown"

    def __init__(self, status: object, known: tuple[int, ...]) -> None:
        self.status = status
        self.known = known
        super().__init__(
            f"未登记的 OnlyOffice callback status={status!r}（已登记 {list(known)}）—— "
            "Requirement 4.9 要求 fail visible：必须持久化原始 payload、告警、"
            "delivery 落 error 终态，且不得创建 application"
        )


def normalize_callback_status(raw_status: object) -> int | None:
    """不可信 callback payload 的 status 归一化：**只认严格 int**，其余返回 ``None``。

    这是**唯一**的归一化点。刻意不写 `int(raw_status)`：那会把 `"6"` / `6.0` / `Decimal(6)`
    悄悄猜成已知 status，正是契约 `unknown_status_policy.forbidden[1]`「按最近似 status
    猜测处理」禁止的行为。`bool` 也必须排除 —— 它是 `int` 的子类，`True` 会被当成 1
    （= `editing`），于是一个布尔字段的拼写错误会变成「有人连接了文档」这种看起来正常
    的语义。
    """
    if isinstance(raw_status, bool) or not isinstance(raw_status, int):
        return None
    return raw_status


class Presence(str, Enum):
    """契约里 `url_present` / `userdata_present` 的封闭三值。"""

    always = "always"
    never = "never"
    optional = "optional"


@dataclass(frozen=True)
class CallbackStatusRule:
    """一行 status 真值表。字段与契约 `callback_statuses[]` 一一对应。"""

    status: int
    oo_name: str
    url_present: Presence
    userdata_present: Presence
    download_required: bool
    oo_response_error: int
    room_transition: str
    delivery_terminal_state: str
    request_correlation: str
    recovery_outcome: str
    application_allowed: bool
    oo94_observed: bool

    @property
    def may_carry_userdata(self) -> bool:
        return self.userdata_present is not Presence.never


@dataclass(frozen=True)
class UnknownStatusPolicy:
    """未知 status 的处置（Requirement 4.9）。"""

    mode: str
    oo_response_error: int
    delivery_terminal_state: str
    application_allowed: bool
    must_alert: bool
    must_persist_raw_payload: bool


@dataclass(frozen=True)
class Timers:
    """全部计时器/TTL 的唯一取值处（契约 `timers`）。"""

    command_service_http_timeout_seconds: int
    forcesave_callback_wait_timeout_seconds: int
    in_flight_grace_seconds: int
    download_connect_timeout_seconds: int
    download_read_timeout_seconds: int
    pending_mutation_token_seconds: int
    callback_download_url_validity_seconds: int
    recovery_case_claim_ttl_hours: int


@dataclass(frozen=True)
class JwtClaimSchema:
    """callback route token 的 claim schema（Requirement 5.1/5.2）。"""

    claim_schema_version: int
    algorithm: str
    header: str
    scheme: str
    required_claims: tuple[str, ...]
    optional_claims: tuple[str, ...]
    claim_constants: Mapping[str, Any]
    action_enum: tuple[str, ...]
    url_bound_claims: tuple[str, ...]
    verification_order: tuple[str, ...]


@dataclass(frozen=True)
class DownloadSecurityPolicy:
    """durable 之前必须全部生效的下载控制（Requirement 5.6/5.7/10.7）。"""

    policy_version: int
    allowlist_mode: str
    dns_recheck_after_resolve: bool
    follow_redirects: bool
    max_redirects: int
    streaming_size_cap_bytes: int
    connect_timeout_seconds: int
    read_timeout_seconds: int
    ooxml_checks: tuple[str, ...]


@dataclass(frozen=True)
class RevocationPolicy:
    """participant 撤销的裁决（Task 4 实证：drop 不证明内容已移除）。"""

    decision: str
    oo_drop_proves: tuple[str, ...]
    oo_drop_does_not_prove: tuple[str, ...]

    @property
    def requires_generation_rotation(self) -> bool:
        """撤销是否必须旋转 generation（而不是「按 participant 选择性剔除内容」）。"""
        return self.decision == "write_fence_plus_generation_rotation"


@dataclass(frozen=True)
class MultiUserSemantics:
    """shared room 的 callback 归属语义（Property 63）。"""

    callback_scope: str
    users_field_semantics: str
    contributor_snapshot_source: str
    participant_bound_authorization_allowed: bool
    revocation: RevocationPolicy


@dataclass(frozen=True)
class CorrelationDeterminism:
    """delivery/application key 的成分清单（Property 64）。"""

    delivery_key_components: tuple[str, ...]
    application_key_components: tuple[str, ...]
    application_key_forbidden_components: tuple[str, ...]


@dataclass(frozen=True)
class CallbackContract:
    """整份真值表的类型化投影。"""

    schema_version: int
    statuses: Mapping[int, CallbackStatusRule]
    unknown_status_policy: UnknownStatusPolicy
    timers: Timers
    jwt: JwtClaimSchema
    download: DownloadSecurityPolicy
    multi_user: MultiUserSemantics
    correlation: CorrelationDeterminism

    @property
    def known_statuses(self) -> tuple[int, ...]:
        return tuple(sorted(self.statuses))

    def status_rule(self, status: object) -> CallbackStatusRule:
        """按 status 取规则；未登记即 :class:`UnknownCallbackStatusError`。

        `status` 刻意声明为 `object`：真实 callback body 的 `status` 来自不可信 JSON，
        可能是字符串、浮点、`None` 甚至嵌套结构。把类型收窄成 `int` 只会让调用方在
        外面自己 `int(...)`，而 `int("6.0")` / `int(True)` 这类隐式转换正是「按最近似
        status 猜测处理」的入口（契约 `unknown_status_policy.forbidden[1]` 明确禁止）。
        归一化收敛到 :func:`normalize_callback_status` 一处，便于单点验证与变异。
        """
        normalized = normalize_callback_status(status)
        if normalized is None:
            raise UnknownCallbackStatusError(status, self.known_statuses)
        rule = self.statuses.get(normalized)
        if rule is None:
            raise UnknownCallbackStatusError(status, self.known_statuses)
        return rule


# ═══════════════════════════════════════════════════════════════════════════
# 解析
# ═══════════════════════════════════════════════════════════════════════════


def _require(raw: Mapping[str, Any], key: str, expected: type, where: str) -> Any:
    if key not in raw:
        raise CallbackContractError(f"{where} 缺键 {key!r}")
    value = raw[key]
    # bool 是 int 的子类：`download_required: 1` 不该被当成 True，反之亦然。
    if expected is int and isinstance(value, bool):
        raise CallbackContractError(f"{where}.{key} 必须是整数，实得 bool")
    if expected is bool and not isinstance(value, bool):
        raise CallbackContractError(f"{where}.{key} 必须是布尔，实得 {type(value).__name__}")
    if not isinstance(value, expected):
        raise CallbackContractError(
            f"{where}.{key} 必须是 {expected.__name__}，实得 {type(value).__name__}"
        )
    return value


def _require_mapping(raw: Mapping[str, Any], key: str, where: str) -> Mapping[str, Any]:
    return _require(raw, key, dict, where)


def _require_str_tuple(raw: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    seq = _require(raw, key, list, where)
    if not seq:
        raise CallbackContractError(f"{where}.{key} 不得为空列表")
    out: list[str] = []
    for item in seq:
        if not isinstance(item, str) or not item.strip():
            raise CallbackContractError(f"{where}.{key} 只接受非空字符串元素")
        out.append(item)
    return tuple(out)


def _presence(raw: Mapping[str, Any], key: str, where: str) -> Presence:
    value = _require(raw, key, str, where)
    try:
        return Presence(value)
    except ValueError as exc:
        raise CallbackContractError(
            f"{where}.{key} 取值 {value!r} 不在封闭域 "
            f"{sorted(item.value for item in Presence)} 内"
        ) from exc


def _parse_statuses(raw: Mapping[str, Any]) -> Mapping[int, CallbackStatusRule]:
    rows = _require(raw, "callback_statuses", list, "<root>")
    if not rows:
        raise CallbackContractError("callback_statuses 不得为空 —— 真值表被削空即 fail closed")
    out: dict[int, CallbackStatusRule] = {}
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CallbackContractError(f"callback_statuses[{idx}] 必须是对象")
        where = f"callback_statuses[{idx}]"
        status = _require(row, "status", int, where)
        if status in out:
            raise CallbackContractError(f"callback_statuses 中 status={status} 重复")
        out[status] = CallbackStatusRule(
            status=status,
            oo_name=_require(row, "oo_name", str, where),
            url_present=_presence(row, "url_present", where),
            userdata_present=_presence(row, "userdata_present", where),
            download_required=_require(row, "download_required", bool, where),
            oo_response_error=_require(row, "oo_response_error", int, where),
            room_transition=_require(row, "room_transition", str, where),
            delivery_terminal_state=_require(row, "delivery_terminal_state", str, where),
            request_correlation=_require(row, "request_correlation", str, where),
            recovery_outcome=_require(row, "recovery_outcome", str, where),
            application_allowed=_require(row, "application_allowed", bool, where),
            oo94_observed=_require(row, "oo94_observed", bool, where),
        )
    for rule in out.values():
        # 内部一致性：需要下载却声明「永远没有 url」是自相矛盾的真值表。
        if rule.download_required and rule.url_present is Presence.never:
            raise CallbackContractError(
                f"status={rule.status} 声明 download_required 但 url_present=never"
            )
        # application 只可能建立在已下载并 sealing 为 durable 的 incoming 之上。
        if rule.application_allowed and not rule.download_required:
            raise CallbackContractError(
                f"status={rule.status} 允许 application 却不要求下载 —— "
                "application 只能以 durable incoming 为 substrate"
            )
    return out


def _parse_timers(raw: Mapping[str, Any]) -> Timers:
    timers = _require_mapping(raw, "timers", "<root>")
    ttl = _require_mapping(timers, "delivery_ttl", "timers")
    parsed = Timers(
        command_service_http_timeout_seconds=_require(
            timers, "command_service_http_timeout_seconds", int, "timers"
        ),
        forcesave_callback_wait_timeout_seconds=_require(
            timers, "forcesave_callback_wait_timeout_seconds", int, "timers"
        ),
        in_flight_grace_seconds=_require(timers, "in_flight_grace_seconds", int, "timers"),
        download_connect_timeout_seconds=_require(
            timers, "download_connect_timeout_seconds", int, "timers"
        ),
        download_read_timeout_seconds=_require(
            timers, "download_read_timeout_seconds", int, "timers"
        ),
        pending_mutation_token_seconds=_require(
            ttl, "pending_mutation_token_seconds", int, "timers.delivery_ttl"
        ),
        callback_download_url_validity_seconds=_require(
            ttl, "callback_download_url_validity_seconds", int, "timers.delivery_ttl"
        ),
        recovery_case_claim_ttl_hours=_require(
            timers, "recovery_case_claim_ttl_hours", int, "timers"
        ),
    )
    for name in (
        "command_service_http_timeout_seconds",
        "forcesave_callback_wait_timeout_seconds",
        "in_flight_grace_seconds",
        "download_connect_timeout_seconds",
        "download_read_timeout_seconds",
        "pending_mutation_token_seconds",
        "callback_download_url_validity_seconds",
        "recovery_case_claim_ttl_hours",
    ):
        if getattr(parsed, name) <= 0:
            raise CallbackContractError(f"timers.{name} 必须为正数")
    if parsed.in_flight_grace_seconds >= parsed.forcesave_callback_wait_timeout_seconds:
        raise CallbackContractError(
            "in_flight_grace_seconds 必须小于 forcesave_callback_wait_timeout_seconds，"
            "否则 grace 永远吃掉超时判定，operation 不可能落可重试 timeout"
        )
    return parsed


def _parse_jwt(raw: Mapping[str, Any]) -> JwtClaimSchema:
    jwt = _require_mapping(raw, "jwt_claim_schema", "<root>")
    version = _require(jwt, "claim_schema_version", int, "jwt_claim_schema")
    if version != SUPPORTED_CLAIM_SCHEMA_VERSION:
        raise CallbackContractError(
            f"jwt_claim_schema.claim_schema_version={version} 不受支持"
            f"（本模块支持 {SUPPORTED_CLAIM_SCHEMA_VERSION}）—— 契约的 "
            "`unknown_or_missing_version=reject_before_download` 要求未知版本在下载前拒绝"
        )
    if _require(jwt, "unknown_or_missing_version", str, "jwt_claim_schema") != (
        "reject_before_download"
    ):
        raise CallbackContractError(
            "jwt_claim_schema.unknown_or_missing_version 必须是 reject_before_download"
        )
    transport = _require_mapping(jwt, "transport", "jwt_claim_schema")
    required = _require_mapping(jwt, "required_claims", "jwt_claim_schema")
    optional = _require_mapping(jwt, "optional_claims", "jwt_claim_schema")
    url_binding = _require_mapping(jwt, "url_binding", "jwt_claim_schema")

    constants: dict[str, Any] = {}
    action_enum: tuple[str, ...] = ()
    for claim, spec in required.items():
        if not isinstance(spec, dict):
            raise CallbackContractError(f"jwt_claim_schema.required_claims.{claim} 必须是对象")
        if "must_equal" in spec:
            constants[claim] = spec["must_equal"]
        if claim == "act":
            action_enum = _require_str_tuple(spec, "enum", f"required_claims.{claim}")
    if "cbv" not in required:
        raise CallbackContractError(
            "jwt_claim_schema.required_claims 必须含 cbv —— claim 版本不可省略"
            "（Requirement 5.2 禁止 claim_version=None 绕过）"
        )
    if constants.get("cbv") != version:
        raise CallbackContractError(
            f"required_claims.cbv.must_equal={constants.get('cbv')!r} 与 "
            f"claim_schema_version={version} 脱钩 —— 二者必须锁死"
        )
    if not action_enum:
        raise CallbackContractError("jwt_claim_schema.required_claims.act 必须声明 enum")

    rule = _require(url_binding, "rule", str, "jwt_claim_schema.url_binding")
    bound = tuple(
        claim
        for claim in ("room_id", "generation", "doc_key", "route_credential_id")
        if f"`{claim}`" in rule
    )
    if len(bound) != 4:
        raise CallbackContractError(
            "jwt_claim_schema.url_binding.rule 必须逐项声明 room_id/generation/doc_key/"
            f"route_credential_id 的 URL 绑定，实得 {list(bound)}"
        )
    return JwtClaimSchema(
        claim_schema_version=version,
        algorithm=_require(jwt, "algorithm", str, "jwt_claim_schema"),
        header=_require(transport, "header", str, "jwt_claim_schema.transport"),
        scheme=_require(transport, "scheme", str, "jwt_claim_schema.transport"),
        required_claims=tuple(sorted(required)),
        optional_claims=tuple(sorted(optional)),
        claim_constants=dict(constants),
        action_enum=action_enum,
        url_bound_claims=bound,
        verification_order=_require_str_tuple(
            jwt, "verification_order", "jwt_claim_schema"
        ),
    )


def _parse_download(raw: Mapping[str, Any]) -> DownloadSecurityPolicy:
    sec = _require_mapping(raw, "download_security", "<root>")
    controls = _require_mapping(sec, "required_controls", "download_security")
    allowlist = _require_mapping(controls, "url_allowlist", "download_security.required_controls")
    dns = _require_mapping(
        controls, "dns_recheck_after_resolve", "download_security.required_controls"
    )
    redirect = _require_mapping(
        controls, "redirect_policy", "download_security.required_controls"
    )
    policy = DownloadSecurityPolicy(
        policy_version=_require(sec, "policy_version", int, "download_security"),
        allowlist_mode=_require(allowlist, "mode", str, "required_controls.url_allowlist"),
        # DNS 复核在契约里以「有 rule 文本」表达；这里把它归一成布尔并要求非空。
        dns_recheck_after_resolve=bool(
            _require(dns, "rule", str, "required_controls.dns_recheck_after_resolve").strip()
        ),
        follow_redirects=_require(
            redirect, "follow_redirects", bool, "required_controls.redirect_policy"
        ),
        max_redirects=_require(
            redirect, "max_redirects", int, "required_controls.redirect_policy"
        ),
        streaming_size_cap_bytes=_require(
            controls, "streaming_size_cap_bytes", int, "download_security.required_controls"
        ),
        connect_timeout_seconds=_require(
            controls, "connect_timeout_seconds", int, "download_security.required_controls"
        ),
        read_timeout_seconds=_require(
            controls, "read_timeout_seconds", int, "download_security.required_controls"
        ),
        ooxml_checks=_require_str_tuple(
            controls, "ooxml_checks", "download_security.required_controls"
        ),
    )
    if policy.follow_redirects or policy.max_redirects != 0:
        raise CallbackContractError(
            "download_security 必须禁止重定向（follow_redirects=false, max_redirects=0）："
            "3xx 跟随会把 allowlist 与已校验 IP 全部绕过"
        )
    if not policy.dns_recheck_after_resolve:
        raise CallbackContractError("download_security 必须声明解析后 DNS 复核（防 rebinding）")
    if policy.streaming_size_cap_bytes <= 0:
        raise CallbackContractError("download_security.streaming_size_cap_bytes 必须为正数")
    return policy


def _parse_multi_user(raw: Mapping[str, Any]) -> MultiUserSemantics:
    mus = _require_mapping(raw, "multi_user_semantics", "<root>")
    pba = _require_mapping(
        mus, "participant_bound_callback_authorization", "multi_user_semantics"
    )
    rev = _require_mapping(mus, "revocation", "multi_user_semantics")
    allowed = _require(
        pba, "allowed", bool, "multi_user_semantics.participant_bound_callback_authorization"
    )
    if allowed:
        raise CallbackContractError(
            "participant_bound_callback_authorization.allowed 必须为 false —— Task 4 已实证 "
            "callback 是 room/generation 级服务事件，route participant / forcesave initiator / "
            "contributors 三者不同一（Property 63）"
        )
    revocation = RevocationPolicy(
        decision=_require(rev, "decision", str, "multi_user_semantics.revocation"),
        oo_drop_proves=_require_str_tuple(
            rev, "oo_drop_proves", "multi_user_semantics.revocation"
        ),
        oo_drop_does_not_prove=_require_str_tuple(
            rev, "oo_drop_does_not_prove", "multi_user_semantics.revocation"
        ),
    )
    if not revocation.requires_generation_rotation:
        raise CallbackContractError(
            f"revocation.decision={revocation.decision!r} 不是 "
            "write_fence_plus_generation_rotation —— 撤销裁决被改写后，"
            "「按 participant 选择性剔除内容」这条被 Task 4 证伪的方案就会复活"
        )
    return MultiUserSemantics(
        callback_scope=_require(mus, "callback_scope", str, "multi_user_semantics"),
        users_field_semantics=_require(
            mus, "users_field_semantics", str, "multi_user_semantics"
        ),
        contributor_snapshot_source=_require(
            mus, "contributor_snapshot_source", str, "multi_user_semantics"
        ),
        participant_bound_authorization_allowed=allowed,
        revocation=revocation,
    )


def _parse_correlation(raw: Mapping[str, Any]) -> CorrelationDeterminism:
    cor = _require_mapping(raw, "correlation_determinism", "<root>")
    parsed = CorrelationDeterminism(
        delivery_key_components=_require_str_tuple(
            cor, "delivery_key_components", "correlation_determinism"
        ),
        application_key_components=_require_str_tuple(
            cor, "application_key_components", "correlation_determinism"
        ),
        application_key_forbidden_components=_require_str_tuple(
            cor, "application_key_forbidden_components", "correlation_determinism"
        ),
    )
    overlap = set(parsed.application_key_components) & set(
        parsed.application_key_forbidden_components
    )
    if overlap:
        raise CallbackContractError(
            f"application_key 的成分与禁用成分重叠: {sorted(overlap)}"
        )
    if "callback_status" not in parsed.delivery_key_components:
        raise CallbackContractError(
            "delivery_key_components 必须含 callback_status —— status 6 与 2 是两条独立 delivery"
        )
    if "callback_status" not in parsed.application_key_forbidden_components:
        raise CallbackContractError(
            "application_key_forbidden_components 必须含 callback_status（Property 64）"
        )
    return parsed


def _parse(raw: Mapping[str, Any]) -> CallbackContract:
    if _require(raw, "contract_id", str, "<root>") != "onlyoffice_callback_state_contract":
        raise CallbackContractError("contract_id 不是 onlyoffice_callback_state_contract")
    schema_version = _require(raw, "schema_version", int, "<root>")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise CallbackContractError(
            f"真值表 schema_version={schema_version} 不受支持"
            f"（本模块支持 {SUPPORTED_SCHEMA_VERSION}）—— 未知版本必须 fail closed，"
            "不得按已知字段尽力解析"
        )
    unknown = _require_mapping(raw, "unknown_status_policy", "<root>")
    policy = UnknownStatusPolicy(
        mode=_require(unknown, "mode", str, "unknown_status_policy"),
        oo_response_error=_require(unknown, "oo_response_error", int, "unknown_status_policy"),
        delivery_terminal_state=_require(
            unknown, "delivery_terminal_state", str, "unknown_status_policy"
        ),
        application_allowed=_require(
            unknown, "application_allowed", bool, "unknown_status_policy"
        ),
        must_alert=_require(unknown, "must_alert", bool, "unknown_status_policy"),
        must_persist_raw_payload=_require(
            unknown, "must_persist_raw_payload", bool, "unknown_status_policy"
        ),
    )
    if policy.mode != "fail_visible" or policy.application_allowed:
        raise CallbackContractError(
            "unknown_status_policy 必须是 fail_visible 且不允许 application（Requirement 4.9）"
        )
    if not policy.must_persist_raw_payload or not policy.must_alert:
        raise CallbackContractError(
            "unknown_status_policy 必须要求持久化原始 payload 并告警 —— "
            "「静默返回 error=0 且不留痕」是契约明令禁止的形态"
        )
    return CallbackContract(
        schema_version=schema_version,
        statuses=_parse_statuses(raw),
        unknown_status_policy=policy,
        timers=_parse_timers(raw),
        jwt=_parse_jwt(raw),
        download=_parse_download(raw),
        multi_user=_parse_multi_user(raw),
        correlation=_parse_correlation(raw),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 加载（mtime 缓存；与 limits.py / retention.py 同范式）
# ═══════════════════════════════════════════════════════════════════════════

_LOCK: Final[threading.Lock] = threading.Lock()
_CACHE: dict[str, Any] = {"mtime": None, "value": None}


def _read_json(target: Path) -> Mapping[str, Any]:
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CallbackContractError(
            f"OO callback 真值表不存在: {target} —— 没有真值表时不得处理任何 callback"
        ) from exc
    except json.JSONDecodeError as exc:
        raise CallbackContractError(f"OO callback 真值表不是合法 JSON: {target} ({exc})") from exc
    if not isinstance(raw, dict):
        raise CallbackContractError(f"OO callback 真值表根必须是对象: {target}")
    return raw


def load_callback_contract(
    path: Path | None = None, *, force: bool = False
) -> CallbackContract:
    """读取（mtime 缓存）Task 4 真值表。缺失/非法/版本未知一律抛，不 fallback。"""
    target = path or CALLBACK_CONTRACT_PATH
    if path is not None or force:
        return _parse(_read_json(target))
    with _LOCK:
        try:
            mtime = target.stat().st_mtime_ns
        except OSError as exc:
            raise CallbackContractError(f"OO callback 真值表不可读: {target}") from exc
        if _CACHE["mtime"] != mtime or _CACHE["value"] is None:
            _CACHE["value"] = _parse(_read_json(target))
            _CACHE["mtime"] = mtime
        value = _CACHE["value"]
    assert isinstance(value, CallbackContract)
    return value


__all__ = [
    "CALLBACK_CONTRACT_PATH",
    "SUPPORTED_SCHEMA_VERSION",
    "SUPPORTED_CLAIM_SCHEMA_VERSION",
    "CallbackContractError",
    "UnknownCallbackStatusError",
    "Presence",
    "CallbackStatusRule",
    "UnknownStatusPolicy",
    "Timers",
    "JwtClaimSchema",
    "DownloadSecurityPolicy",
    "RevocationPolicy",
    "MultiUserSemantics",
    "CorrelationDeterminism",
    "CallbackContract",
    "normalize_callback_status",
    "load_callback_contract",
]
