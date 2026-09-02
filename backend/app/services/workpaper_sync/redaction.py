# -*- coding: utf-8 -*-
"""版本化 `RedactionPolicy`：字段 allowlist 投影 + 值形态屏蔽 + URL/异常文本 scrub。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 29
Requirements: 5.10, 5.11, 10.7, 13.8
Properties: P68 / P69（timeline 与 evidence 都必须经本策略后才落盘/出网）

═══ 为什么是 allowlist 而不是 blacklist ═══

Requirement 13.8 的原文是「策略必须对嵌套 payload、异常文本和下载 URL 做 **allowlist
投影**」。这条不是措辞洁癖：

* blacklist 的失效方式是**沉默的** —— 下一个 task 往 event detail 里塞一个新键
  （`incoming_cell_values`、`download_url`、`command_body`），黑名单里没有它，于是原样
  落库。而 allowlist 下这个新键会被丢弃，作者必须显式登记才能出现，登记时就会被 review。
* 本 spec 的载荷天然含业务内容：extract/merge 的 base/current/incoming 三方值就是审计
  底稿的真实金额。timeline 与 trace bundle **不允许**记录它们（只记 digest 与 identity），
  所以默认必须是「丢」。

═══ 三层过滤，缺一层就有真实泄露路径 ═══

1. **键名层**（:meth:`RedactionPolicy.is_secret_key`）—— `Authorization` / `token` /
   `jwt` / `secret` / `cookie` / `signature` 等键名一律整值屏蔽，**且优先于 allowlist**。
   allowlist 不能给敏感键开后门：否则某个 task 只要把 `authorization` 登记进 allowlist
   就能合法泄露长期凭证。
2. **值形态层**（:attr:`ValuePattern`）—— 键名合法但值长得像凭证：`eyJ...` 三段式 JWS、
   `Bearer xxx`、带 query 的 URL、80+ 字符不透明串。OO 的 callback payload 里
   `url` 字段就长这样，而 `url` 这个键名不含任何敏感词。
3. **容器层** —— 递归投影嵌套 dict/list，并在 `max_depth` / `max_container_items` /
   `max_string_chars` 处截断。不截断 = 一条 event detail 能把 866KB 的 D2 载荷整份写进
   `error_detail`（Requirement 5.12 只要求记 identity 与 code）。

═══ URL 为什么连 host 都要过 allowlist ═══

Requirement 10.7 禁止「泄露长期 token、授权 header 或项目敏感内容」，而 callback /
download URL 的 query 里恰好带短期凭证。只保留 `scheme://host/前两段 path`：

* query / fragment / userinfo（`https://user:pass@host/`）一律丢；
* host 不在 allowlist 时降级为 `[redacted-host]` —— 内网拓扑本身是敏感信息，而
  DocServer 的地址在不同部署里不同，写死 host 反而让策略不可移植。

═══ 与 `callback_delivery.canonical_digest` 的分工 ═══

那边剔 token 是为了**算出稳定 digest**（同一逻辑请求的重试要命中同一 key）；这里剔
是为了**不落盘**。两者目的不同、可同时存在：digest 只输出 64 个 hex，本策略把它当
非敏感值放行（见配置 `allowlist.digest`）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Mapping, Sequence
from urllib.parse import urlsplit
from uuid import UUID

from app.services.workpaper_sync.models import SyncDomainError

#: 策略配置真源。与 `workpaper_sync_retention_policy.json` 同目录、同版本化范式。
REDACTION_CONFIG_PATH: Final[Path] = (
    Path(__file__).resolve().parents[3] / "data" / "workpaper_sync_redaction_policy.json"
)

#: allowlist 的分组名。配置里少一组即 fail closed（不是「按缺省组走」）。
ALLOWLIST_GROUPS: Final[tuple[str, ...]] = (
    "identity",
    "digest",
    "protocol",
    "error",
    "timing",
    "environment",
)

#: 浏览器侧证据只能挂在这些前缀下，且**不参与排序**（Requirement 13.10）。
#: 服务端时钟是 timeline 的唯一时间权威，client trace 只是客户端证据。
CLIENT_EVIDENCE_PREFIX: Final[str] = "client_"


class RedactionConfigError(SyncDomainError):
    """策略配置缺失/非法。

    **刻意不 fallback 到内置默认值**：一个「策略读不到就放行」的实现等于把
    Requirement 13.8 变成可选项。读不到策略时唯一安全的行为是拒绝记录。
    """

    error_code = "redaction_config_invalid"


class RedactionUsageError(SyncDomainError):
    """调用协议违规（例如把 client trace 时间当服务端时钟传进 timeline）。"""

    error_code = "redaction_usage_invalid"


@dataclass(frozen=True)
class ValuePattern:
    """一条值形态规则。`rule_id` 会出现在守卫里，逐条可变异。"""

    rule_id: str
    regex: re.Pattern[str]
    why: str


@dataclass(frozen=True)
class RedactionLimits:
    max_depth: int
    max_container_items: int
    max_string_chars: int
    max_exception_chars: int


@dataclass(frozen=True)
class RedactionReport:
    """一次投影里发生了什么 —— 供守卫与告警使用，不含任何被屏蔽的原文。"""

    dropped_keys: tuple[str, ...] = ()
    secret_keys: tuple[str, ...] = ()
    scrubbed_rules: tuple[str, ...] = ()
    truncated_keys: tuple[str, ...] = ()
    depth_exceeded: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "dropped_keys": list(self.dropped_keys),
            "secret_keys": list(self.secret_keys),
            "scrubbed_rules": list(self.scrubbed_rules),
            "truncated_keys": list(self.truncated_keys),
            "depth_exceeded": self.depth_exceeded,
        }

    @property
    def leaked_nothing(self) -> bool:
        """本次投影是否**完全**没有丢弃/屏蔽动作（用于反向泄露测试的对照侧）。"""
        return not (
            self.dropped_keys or self.secret_keys or self.scrubbed_rules or self.truncated_keys
        )


class _Accumulator:
    """投影过程中的可变账本（`RedactionReport` 是它的不可变快照）。"""

    def __init__(self) -> None:
        self.dropped: list[str] = []
        self.secret: list[str] = []
        self.rules: list[str] = []
        self.truncated: list[str] = []
        self.depth_exceeded = False

    def snapshot(self) -> RedactionReport:
        def uniq(items: list[str]) -> tuple[str, ...]:
            return tuple(sorted(set(items)))

        return RedactionReport(
            dropped_keys=uniq(self.dropped),
            secret_keys=uniq(self.secret),
            scrubbed_rules=uniq(self.rules),
            truncated_keys=uniq(self.truncated),
            depth_exceeded=self.depth_exceeded,
        )


class RedactionPolicy:
    """版本化字段级脱敏策略。

    构造只接受**已解析的配置**；生产调用一律走 :func:`load_redaction_policy`（带
    `lru_cache`），测试可以直接构造以驱动否定侧。
    """

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._config = dict(config)
        self.policy_version: str = self._require_str("policy_version")
        self.policy_id: str = self._require_str("policy_id")
        self.schema_version: int = int(self._require("schema_version"))

        placeholders = self._require_mapping("placeholders")
        for name in ("dropped_key", "secret_value", "url_query", "truncated"):
            if not str(placeholders.get(name) or "").strip():
                raise RedactionConfigError(f"placeholders.{name} 缺失 —— 占位符不得为空串")
        self.dropped_placeholder: str = str(placeholders["dropped_key"])
        self.secret_placeholder: str = str(placeholders["secret_value"])
        self.url_query_placeholder: str = str(placeholders["url_query"])
        self.truncated_placeholder: str = str(placeholders["truncated"])

        limits = self._require_mapping("limits")
        try:
            self.limits = RedactionLimits(
                max_depth=int(limits["max_depth"]),
                max_container_items=int(limits["max_container_items"]),
                max_string_chars=int(limits["max_string_chars"]),
                max_exception_chars=int(limits["max_exception_chars"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RedactionConfigError(f"limits 非法: {limits!r}") from exc
        for field_name, value in (
            ("max_depth", self.limits.max_depth),
            ("max_container_items", self.limits.max_container_items),
            ("max_string_chars", self.limits.max_string_chars),
            ("max_exception_chars", self.limits.max_exception_chars),
        ):
            if value <= 0:
                raise RedactionConfigError(
                    f"limits.{field_name} 必须为正数，实得 {value} —— 0/负数会让整份载荷原样通过"
                )

        allowlist = self._require_mapping("allowlist")
        missing_groups = [g for g in ALLOWLIST_GROUPS if g not in allowlist]
        if missing_groups:
            raise RedactionConfigError(
                f"allowlist 缺分组 {missing_groups} —— 分组必须齐全（缺组不得按缺省放行）"
            )
        groups: dict[str, frozenset[str]] = {}
        for group in ALLOWLIST_GROUPS:
            raw = allowlist[group]
            if not isinstance(raw, Mapping):
                raise RedactionConfigError(f"allowlist.{group} 必须是对象")
            keys = raw.get("keys")
            if not isinstance(keys, Sequence) or isinstance(keys, (str, bytes)) or not keys:
                raise RedactionConfigError(
                    f"allowlist.{group}.keys 必须是非空数组 —— 空组等于悄悄放弃该组判据"
                )
            groups[group] = frozenset(str(k) for k in keys)
        self.allowlist_groups: Mapping[str, frozenset[str]] = groups
        self.allowlist: frozenset[str] = frozenset().union(*groups.values())

        error_group = allowlist["error"]
        scrubbed = error_group.get("scrubbed_keys")
        if not isinstance(scrubbed, Sequence) or isinstance(scrubbed, (str, bytes)) or not scrubbed:
            raise RedactionConfigError(
                "allowlist.error.scrubbed_keys 必须是非空数组 —— 异常文本必须有明确的 scrub 入口"
            )
        #: 这些键**保留但走文本 scrub**（异常原文里可能夹着 URL/token）。
        self.scrubbed_keys: frozenset[str] = frozenset(str(k) for k in scrubbed)

        secret_group = self._require_mapping("secret_key_patterns")
        secret_patterns = secret_group.get("patterns")
        if (
            not isinstance(secret_patterns, Sequence)
            or isinstance(secret_patterns, (str, bytes))
            or not secret_patterns
        ):
            raise RedactionConfigError("secret_key_patterns.patterns 必须是非空数组")
        self.secret_key_patterns: tuple[str, ...] = tuple(
            str(p).lower() for p in secret_patterns
        )
        role_suffixes = secret_group.get("non_credential_role_suffixes")
        if (
            not isinstance(role_suffixes, Sequence)
            or isinstance(role_suffixes, (str, bytes))
            or not role_suffixes
        ):
            raise RedactionConfigError(
                "secret_key_patterns.non_credential_role_suffixes 必须是非空数组 —— "
                "空名单会把 `authorization_result` 这类枚举结果列整列屏蔽（删掉 AC 13.5）"
            )
        self.non_credential_role_suffixes: tuple[str, ...] = tuple(
            str(s).lower() for s in role_suffixes
        )
        overlap = sorted(set(self.non_credential_role_suffixes) & set(self.secret_key_patterns))
        if overlap:
            raise RedactionConfigError(
                f"non_credential_role_suffixes 与敏感词重叠 {overlap} —— "
                "角色词一旦本身是凭证词，末段规则就成了凭证放行通道"
            )

        rules_raw = self._require_mapping("value_patterns").get("rules")
        if not isinstance(rules_raw, Sequence) or isinstance(rules_raw, (str, bytes)) or not rules_raw:
            raise RedactionConfigError("value_patterns.rules 必须是非空数组")
        rules: list[ValuePattern] = []
        for item in rules_raw:
            if not isinstance(item, Mapping):
                raise RedactionConfigError("value_patterns.rules[] 元素必须是对象")
            rule_id = str(item.get("rule_id") or "").strip()
            regex = str(item.get("regex") or "")
            why = str(item.get("why") or "").strip()
            if not rule_id or not regex or not why:
                raise RedactionConfigError(
                    f"value_patterns 规则缺 rule_id/regex/why: {item!r}"
                )
            try:
                compiled = re.compile(regex)
            except re.error as exc:
                raise RedactionConfigError(f"value_patterns.{rule_id} 正则非法: {exc}") from exc
            rules.append(ValuePattern(rule_id=rule_id, regex=compiled, why=why))
        self.value_patterns: tuple[ValuePattern, ...] = tuple(rules)

        url_shape = self._require_mapping("url_shape")
        hosts = url_shape.get("host_allowlist")
        if not isinstance(hosts, Sequence) or isinstance(hosts, (str, bytes)):
            raise RedactionConfigError("url_shape.host_allowlist 必须是数组")
        self.host_allowlist: frozenset[str] = frozenset(str(h).lower() for h in hosts)
        self.keep_path_segments: int = int(url_shape.get("keep_path_segments", 1))
        if self.keep_path_segments < 0:
            raise RedactionConfigError("url_shape.keep_path_segments 不得为负")
        self.unlisted_host_placeholder: str = str(
            url_shape.get("unlisted_host_placeholder") or ""
        )
        if not self.unlisted_host_placeholder:
            raise RedactionConfigError("url_shape.unlisted_host_placeholder 不得为空")

        #: allowlist 与敏感键名**不得相交**：相交即等于给凭证开白名单。
        conflicts = sorted(k for k in self.allowlist if self._matches_secret_key(k))
        if conflicts:
            raise RedactionConfigError(
                f"allowlist 里出现敏感键名 {conflicts} —— 键名层优先于 allowlist，"
                "登记它只会造成「以为记下了其实被屏蔽」的错觉，且是明确的泄露入口"
            )

    # ------------------------------------------------------------------
    # 配置读取小工具（逐项 fail closed）
    # ------------------------------------------------------------------

    def _require(self, key: str) -> Any:
        if key not in self._config:
            raise RedactionConfigError(f"策略缺字段 {key!r}")
        return self._config[key]

    def _require_str(self, key: str) -> str:
        value = str(self._require(key) or "").strip()
        if not value:
            raise RedactionConfigError(f"策略字段 {key!r} 不得为空")
        return value

    def _require_mapping(self, key: str) -> Mapping[str, Any]:
        value = self._require(key)
        if not isinstance(value, Mapping):
            raise RedactionConfigError(f"策略字段 {key!r} 必须是对象，实得 {type(value).__name__}")
        return value

    # ------------------------------------------------------------------
    # 键名层
    # ------------------------------------------------------------------

    @staticmethod
    def _segments(key: str) -> tuple[str, ...]:
        return tuple(part for part in re.split(r"[^a-z0-9]+", str(key).lower()) if part)

    def _matches_secret_key(self, key: str) -> bool:
        """键名是否指向凭证本体。

        判据是两个条件的**合取**：命中敏感词 **且** 末段不是非凭证角色词。两步的书写
        顺序只影响短路时机、不影响结果（合取可交换）—— 所以这里**不**声明「顺序不可
        交换」那类不存在的不变量：把它写进注释会让后来的人以为有守卫在盯着顺序，而
        针对顺序的变异必然恒 GREEN。

        真正承载行为、也真正需要守卫的是**角色词只锚定末段**（`segments[-1]`），
        不是「任一段命中即放行」：

        * `token_digest` → 末段 `digest` ⇒ 非凭证。凭证的 SHA-256 不是凭证，放行正确。
        * `digest_token` → 末段 `token` ⇒ **是**凭证。若改成「任一段命中角色词就放行」，
          它会因为首段 `digest` 而被判非凭证，长期凭证原样落库。
          `state_authorization` / `sha256_secret` 同理。

        这三个键是该改动的真实泄露面，故守卫对两个方向都有断言（见
        `test_role_suffix_list_is_closed_both_ways`）。
        """
        lowered = str(key).lower()
        if not any(pattern in lowered for pattern in self.secret_key_patterns):
            return False
        segments = self._segments(key)
        if segments and segments[-1] in self.non_credential_role_suffixes:
            return False
        return True

    def is_secret_key(self, key: str) -> bool:
        """键名是否命中敏感模式。**优先于 allowlist**。"""
        return self._matches_secret_key(key)

    def is_allowed_key(self, key: str) -> bool:
        """键是否可以出现在投影结果里。

        三条独立判据，顺序不可交换：
        1. 敏感键名 → 永不允许（即使被登记）；
        2. `client_` 前缀 → 允许，但由调用方保证不参与排序（Requirement 13.10）；
        3. 其余 → 必须在 allowlist 或 scrubbed_keys 里。
        """
        if self._matches_secret_key(key):
            return False
        if str(key).startswith(CLIENT_EVIDENCE_PREFIX):
            return True
        return key in self.allowlist or key in self.scrubbed_keys

    # ------------------------------------------------------------------
    # URL 层
    # ------------------------------------------------------------------

    def redact_url(self, raw: str) -> str:
        """只保留 `scheme://host/前 N 段 path`；query/fragment/userinfo 一律丢。"""
        text = str(raw)
        try:
            parts = urlsplit(text)
        except ValueError:
            return self.secret_placeholder
        if not parts.scheme or not parts.netloc:
            # 不是 URL 形态：交给值形态层处理，不在这里放行原文。
            return self.secret_placeholder
        host = (parts.hostname or "").lower()
        shown_host = host if host in self.host_allowlist else self.unlisted_host_placeholder
        segments = [seg for seg in parts.path.split("/") if seg][: self.keep_path_segments]
        path = "/" + "/".join(segments) if segments else ""
        suffix = f"?{self.url_query_placeholder}" if (parts.query or parts.fragment) else ""
        return f"{parts.scheme}://{shown_host}{path}{suffix}"

    # ------------------------------------------------------------------
    # 值形态层
    # ------------------------------------------------------------------

    def scrub_text(self, raw: str, acc: _Accumulator | None = None) -> str:
        """按 :attr:`value_patterns` 逐条屏蔽敏感片段；URL 降级为形态。"""
        text = str(raw)
        for pattern in self.value_patterns:
            if not pattern.regex.search(text):
                continue
            if acc is not None:
                acc.rules.append(pattern.rule_id)
            if pattern.rule_id == "url_with_credentials_or_query":
                text = pattern.regex.sub(lambda m: self.redact_url(m.group(0)), text)
            else:
                text = pattern.regex.sub(self.secret_placeholder, text)
        return text

    def redact_exception(self, exc: BaseException | str) -> str:
        """异常文本：先加类型前缀，再 scrub，最后按 `max_exception_chars` 截断。

        保留类型名是刻意的 —— Requirement 5.12 要求「记录 error code、stage」，异常类型
        是最稳定的一种分型；而 `str(exc)` 里可能夹着 URL、SQL 参数与业务值，必须 scrub。
        """
        if isinstance(exc, BaseException):
            text = f"{type(exc).__name__}: {exc}"
        else:
            text = str(exc)
        scrubbed = self.scrub_text(text)
        if len(scrubbed) > self.limits.max_exception_chars:
            return scrubbed[: self.limits.max_exception_chars] + self.truncated_placeholder
        return scrubbed

    # ------------------------------------------------------------------
    # 容器层
    # ------------------------------------------------------------------

    def _scalar(self, key: str, value: Any, acc: _Accumulator) -> Any:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Enum):
            return self._scalar(key, value.value, acc)
        if isinstance(value, (bytes, bytearray, memoryview)):
            # 字节永远不进日志/证据：长度是唯一有用且非敏感的事实。
            acc.secret.append(key)
            return f"{self.secret_placeholder}({len(bytes(value))}B)"
        text = self.scrub_text(str(value), acc)
        if len(text) > self.limits.max_string_chars:
            acc.truncated.append(key)
            text = text[: self.limits.max_string_chars] + self.truncated_placeholder
        return text

    def _project(self, value: Any, *, key: str, depth: int, acc: _Accumulator) -> Any:
        if depth > self.limits.max_depth:
            acc.depth_exceeded = True
            return self.truncated_placeholder
        if isinstance(value, Mapping):
            out: dict[str, Any] = {}
            for raw_key, raw_value in value.items():
                child_key = str(raw_key)
                if self._matches_secret_key(child_key):
                    acc.secret.append(child_key)
                    out[child_key] = self.secret_placeholder
                    continue
                if not self.is_allowed_key(child_key):
                    acc.dropped.append(child_key)
                    continue
                out[child_key] = self._project(
                    raw_value, key=child_key, depth=depth + 1, acc=acc
                )
            return out
        if isinstance(value, (list, tuple, set, frozenset)):
            items = list(value)
            kept = items[: self.limits.max_container_items]
            if len(items) > len(kept):
                acc.truncated.append(key)
            return [
                self._project(item, key=key, depth=depth + 1, acc=acc) for item in kept
            ]
        return self._scalar(key, value, acc)

    def redact(self, payload: Mapping[str, Any]) -> tuple[dict[str, Any], RedactionReport]:
        """对嵌套 payload 做 allowlist 投影，返回 `(投影结果, 报告)`。"""
        if not isinstance(payload, Mapping):
            raise RedactionUsageError(
                f"redact() 只接受 Mapping，实得 {type(payload).__name__} —— "
                "标量/序列请走 scrub_text()/redact_url()"
            )
        acc = _Accumulator()
        projected = self._project(payload, key="<root>", depth=1, acc=acc)
        return projected, acc.snapshot()

    def redact_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """只要结果的便捷形态。"""
        return self.redact(payload)[0]

    # ------------------------------------------------------------------
    # 自证
    # ------------------------------------------------------------------

    def assert_no_leak(self, projected: Any) -> None:
        """反向自证：投影结果里不得残留任何敏感键或凭证形态。

        存在的理由是「守卫不能只测我写的那几个 case」：任何新增的 detail 结构都可以
        在写库前跑一次这个断言。它**不**用来替代反向泄露测试，而是让生产路径自身也
        fail closed。
        """
        for key, value in _walk(projected):
            if self._matches_secret_key(key) and value != self.secret_placeholder:
                raise RedactionUsageError(
                    f"脱敏结果残留敏感键 {key!r} 的原值 —— 键名层未生效"
                )
            if isinstance(value, str):
                for pattern in self.value_patterns:
                    if pattern.rule_id == "url_with_credentials_or_query":
                        # URL 已被降级成形态串（仍含 `scheme://`，所以照样命中该规则）。
                        # 因此这里不是跳过，而是换成**更强**的判据：每个 URL 形态子串
                        # 都必须已经没有 userinfo/query/fragment，且 host 只能是 allowlist
                        # 内的或占位符。裸跳过会让「整条 URL 根本没进 scrub」也判通过。
                        for found in pattern.regex.findall(value):
                            self._assert_url_shape_only(found, key=key)
                        continue
                    if pattern.regex.search(value):
                        raise RedactionUsageError(
                            f"脱敏结果残留 {pattern.rule_id} 形态（键 {key!r}）"
                        )

    def _assert_url_shape_only(self, found: str, *, key: str) -> None:
        try:
            parts = urlsplit(found)
        except ValueError as exc:
            # 解析不了就无法证明它已脱敏 ⇒ fail closed，而不是让 ValueError 穿透调用方。
            raise RedactionUsageError(
                f"脱敏结果里的 URL 形态无法解析（键 {key!r}）：{type(exc).__name__}"
            ) from exc
        if parts.username or parts.password:
            raise RedactionUsageError(f"脱敏结果残留 URL userinfo（键 {key!r}）")
        if parts.query and parts.query != self.url_query_placeholder:
            raise RedactionUsageError(f"脱敏结果残留 URL query（键 {key!r}）")
        if parts.fragment:
            raise RedactionUsageError(f"脱敏结果残留 URL fragment（键 {key!r}）")
        host = (parts.hostname or "").lower()
        if host and host not in self.host_allowlist:
            if self.unlisted_host_placeholder.lower() not in parts.netloc.lower():
                raise RedactionUsageError(
                    f"脱敏结果残留未登记 host {host!r}（键 {key!r}）"
                )

    def fingerprint(self) -> dict[str, Any]:
        """进 evidence 的策略身份（不含策略正文）。"""
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "schema_version": self.schema_version,
            "allowlist_size": len(self.allowlist),
            "value_pattern_ids": [p.rule_id for p in self.value_patterns],
        }


def _walk(node: Any, key: str = "<root>") -> Any:
    """深度优先产出 `(key, value)`，用于 :meth:`RedactionPolicy.assert_no_leak`。"""
    if isinstance(node, Mapping):
        for child_key, child in node.items():
            yield from _walk(child, str(child_key))
    elif isinstance(node, (list, tuple)):
        for child in node:
            yield from _walk(child, key)
    else:
        yield key, node


def load_redaction_config(path: Path | None = None) -> Mapping[str, Any]:
    target = path or REDACTION_CONFIG_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RedactionConfigError(
            f"脱敏策略缺失: {target} —— 无策略时不得记录任何 timeline/trace/evidence"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RedactionConfigError(f"脱敏策略不是合法 JSON: {target}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise RedactionConfigError(f"脱敏策略根节点必须是对象: {target}")
    return payload


@lru_cache(maxsize=1)
def load_redaction_policy() -> RedactionPolicy:
    """生产唯一入口（进程内缓存）。改配置需重启，与 retention 策略同语义。"""
    return RedactionPolicy(load_redaction_config())


__all__ = [
    "ALLOWLIST_GROUPS",
    "CLIENT_EVIDENCE_PREFIX",
    "REDACTION_CONFIG_PATH",
    "RedactionConfigError",
    "RedactionLimits",
    "RedactionPolicy",
    "RedactionReport",
    "RedactionUsageError",
    "ValuePattern",
    "load_redaction_config",
    "load_redaction_policy",
]
