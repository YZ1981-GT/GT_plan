# -*- coding: utf-8 -*-
"""Requirement 14.11 安全预算与 OOXML 安全策略的**唯一加载入口**（无 IO 之外的业务逻辑）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 11
Requirements: 5.6, 10.8, 14.11
Properties: P17 / P60

═══ 为什么必须有这个模块 ═══

design.md §Capacity Budget 明确「预算来自单一 `workpaper_sync_limits` 配置并被
contract/test 读取，禁止代码散落常量」。散落常量的具体危害是**守卫与生产各自一份**：
守卫写 `assert reject_at(20001)`、生产写 `if n > 20000`，之后调预算时只改一处 ⇒
守卫仍绿而真实边界已漂移。故：

* 生产代码（:mod:`.ooxml_security` / :mod:`.artifacts`）里**零**预算数字字面量；
* 守卫测试也从这里取值，`N-1/N/N+1` 三点全部由配置推导；
* 改预算 = 改 JSON（并按 Requirement 14.11 提交 capacity ADR），两侧同时变化。

═══ 为什么 `assert_*` 抛的是带 `error_code` 的异常 ═══

Requirement 14.11「超限必须 fail visible，不得 OOM 或截断」。返回 bool 的校验会被
调用方 `if not ok: pass` 悄悄吞掉；抛 :class:`BudgetExceededError` 并带上
`budget / observed / limit` 三元组，才能在 operation error detail 里定位到具体预算项
（Requirement 5.12 要求 error code + stage）。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app.services.workpaper_sync.models import SyncDomainError

#: 配置真源。`backend/data/workpaper_sync_limits.json`。
LIMITS_CONFIG_PATH: Final[Path] = (
    Path(__file__).resolve().parents[3] / "data" / "workpaper_sync_limits.json"
)


class BudgetExceededError(SyncDomainError):
    """任一 Requirement 14.11 预算被突破（fail visible，不截断、不 OOM）。"""

    error_code = "capacity_budget_exceeded"

    def __init__(self, *, budget: str, observed: int, limit: int, detail: str = "") -> None:
        self.budget = budget
        self.observed = observed
        self.limit = limit
        suffix = f"；{detail}" if detail else ""
        super().__init__(
            f"容量预算 {budget} 超限：observed={observed} > limit={limit}{suffix}"
        )


class LimitsConfigError(SyncDomainError):
    """配置文件缺失/结构非法。**不 fallback 到内置默认值**。

    fallback 会让「配置被删/写坏」表现为「按某个看不见的默认值继续跑」，而
    Requirement 14.11 要求预算由单一配置锁死 —— 静默默认值就是第二真源。
    """

    error_code = "limits_config_invalid"


@dataclass(frozen=True)
class OoxmlPolicy:
    """OOXML 安全策略快照（Requirement 10.8）。"""

    policy_version: str
    zip_magic: bytes
    required_parts: tuple[str, ...]
    document_type_markers: dict[str, str]
    allow_external_relationships: bool
    external_relationship_target_mode: str
    allow_macros: bool
    macro_part_markers: tuple[str, ...]
    macro_content_types: tuple[str, ...]
    allow_embedded_objects: bool
    embedded_object_prefixes: tuple[str, ...]
    forbidden_entry_name_patterns: tuple[str, ...]
    reject_absolute_entry_names: bool


@dataclass(frozen=True)
class SyncLimits:
    """Requirement 14.11 预算 + 流式参数 + OOXML 策略。"""

    config_id: str
    schema_version: int
    max_compressed_bytes: int
    max_expanded_bytes: int
    max_zip_entries: int
    max_compression_ratio: int
    max_table_rows: int
    max_projection_fields: int
    chunk_bytes: int
    peak_memory_budget_bytes: int
    baseline_max_bytes: int
    baseline_max_fields: int
    ooxml: OoxmlPolicy

    # ── 预算门（纯函数，boundary 语义为「> limit 即拒绝」，即 N 合法、N+1 拒绝）──

    def assert_compressed_size(self, observed: int) -> None:
        if observed > self.max_compressed_bytes:
            raise BudgetExceededError(
                budget="max_compressed_bytes",
                observed=observed,
                limit=self.max_compressed_bytes,
                detail="压缩包体积超限；拒绝在解压前发生，避免无界展开",
            )

    def assert_expanded_size(self, observed: int) -> None:
        if observed > self.max_expanded_bytes:
            raise BudgetExceededError(
                budget="max_expanded_bytes",
                observed=observed,
                limit=self.max_expanded_bytes,
                detail="展开总量超限；流式累计到此即刻中止，不继续解压",
            )

    def assert_zip_entries(self, observed: int) -> None:
        if observed > self.max_zip_entries:
            raise BudgetExceededError(
                budget="max_zip_entries",
                observed=observed,
                limit=self.max_zip_entries,
                detail="ZIP entry 数超限",
            )

    def assert_compression_ratio(self, *, compressed: int, expanded: int) -> None:
        """压缩比门。`compressed == 0`（stored 空 entry）时不判定 —— 除零无意义。"""
        if compressed <= 0:
            return
        ratio = expanded / compressed
        if ratio > self.max_compression_ratio:
            raise BudgetExceededError(
                budget="max_compression_ratio",
                observed=int(ratio),
                limit=self.max_compression_ratio,
                detail=f"compressed={compressed} expanded={expanded} ratio={ratio:.2f}",
            )

    def assert_table_rows(self, observed: int, *, table_key: str = "") -> None:
        if observed > self.max_table_rows:
            raise BudgetExceededError(
                budget="max_table_rows",
                observed=observed,
                limit=self.max_table_rows,
                detail=f"table={table_key or '<unnamed>'}",
            )

    def assert_projection_fields(self, observed: int) -> None:
        if observed > self.max_projection_fields:
            raise BudgetExceededError(
                budget="max_projection_fields",
                observed=observed,
                limit=self.max_projection_fields,
                detail="单 projection field 数超限",
            )


_CACHE: dict[str, Any] = {"mtime": None, "value": None}
_LOCK = threading.Lock()


def _require(mapping: dict[str, Any], key: str, kind: type, where: str) -> Any:
    if key not in mapping:
        raise LimitsConfigError(f"{where} 缺少必填键 {key!r}")
    value = mapping[key]
    if kind is int and isinstance(value, bool):
        raise LimitsConfigError(f"{where}.{key} 期望 int，实得 bool")
    if not isinstance(value, kind):
        raise LimitsConfigError(
            f"{where}.{key} 期望 {kind.__name__}，实得 {type(value).__name__}"
        )
    if kind is int and value <= 0:
        raise LimitsConfigError(f"{where}.{key} 必须为正整数，实得 {value}")
    return value


def _parse(raw: dict[str, Any]) -> SyncLimits:
    budgets = raw.get("budgets")
    if not isinstance(budgets, dict):
        raise LimitsConfigError("配置缺少 budgets 段")
    streaming = raw.get("streaming")
    if not isinstance(streaming, dict):
        raise LimitsConfigError("配置缺少 streaming 段")
    baseline = raw.get("baseline_operation")
    if not isinstance(baseline, dict):
        raise LimitsConfigError("配置缺少 baseline_operation 段")
    policy_raw = raw.get("ooxml_policy")
    if not isinstance(policy_raw, dict):
        raise LimitsConfigError("配置缺少 ooxml_policy 段")

    magic_hex = _require(policy_raw, "zip_magic_hex", str, "ooxml_policy")
    try:
        magic = bytes.fromhex(magic_hex)
    except ValueError as exc:
        raise LimitsConfigError(f"ooxml_policy.zip_magic_hex 非法 hex: {magic_hex!r}") from exc
    if not magic:
        raise LimitsConfigError("ooxml_policy.zip_magic_hex 不得为空")

    markers = policy_raw.get("document_type_markers")
    if not isinstance(markers, dict) or not markers:
        raise LimitsConfigError("ooxml_policy.document_type_markers 必须是非空对象")

    for flag in ("allow_external_relationships", "allow_macros", "allow_embedded_objects",
                 "reject_absolute_entry_names"):
        if not isinstance(policy_raw.get(flag), bool):
            raise LimitsConfigError(f"ooxml_policy.{flag} 必须是布尔值")

    policy = OoxmlPolicy(
        policy_version=_require(policy_raw, "policy_version", str, "ooxml_policy"),
        zip_magic=magic,
        required_parts=tuple(policy_raw.get("required_parts") or ()),
        document_type_markers={str(k): str(v) for k, v in markers.items()},
        allow_external_relationships=bool(policy_raw["allow_external_relationships"]),
        external_relationship_target_mode=_require(
            policy_raw, "external_relationship_target_mode", str, "ooxml_policy"
        ),
        allow_macros=bool(policy_raw["allow_macros"]),
        macro_part_markers=tuple(
            str(v).lower() for v in (policy_raw.get("macro_part_markers") or ())
        ),
        macro_content_types=tuple(
            str(v).lower() for v in (policy_raw.get("macro_content_types") or ())
        ),
        allow_embedded_objects=bool(policy_raw["allow_embedded_objects"]),
        embedded_object_prefixes=tuple(
            str(v).lower() for v in (policy_raw.get("embedded_object_prefixes") or ())
        ),
        forbidden_entry_name_patterns=tuple(
            str(v) for v in (policy_raw.get("forbidden_entry_name_patterns") or ())
        ),
        reject_absolute_entry_names=bool(policy_raw["reject_absolute_entry_names"]),
    )
    if not policy.required_parts:
        raise LimitsConfigError("ooxml_policy.required_parts 不得为空")

    limits = SyncLimits(
        config_id=_require(raw, "config_id", str, "<root>"),
        schema_version=_require(raw, "schema_version", int, "<root>"),
        max_compressed_bytes=_require(budgets, "max_compressed_bytes", int, "budgets"),
        max_expanded_bytes=_require(budgets, "max_expanded_bytes", int, "budgets"),
        max_zip_entries=_require(budgets, "max_zip_entries", int, "budgets"),
        max_compression_ratio=_require(budgets, "max_compression_ratio", int, "budgets"),
        max_table_rows=_require(budgets, "max_table_rows", int, "budgets"),
        max_projection_fields=_require(budgets, "max_projection_fields", int, "budgets"),
        chunk_bytes=_require(streaming, "chunk_bytes", int, "streaming"),
        peak_memory_budget_bytes=_require(
            streaming, "peak_memory_budget_bytes", int, "streaming"
        ),
        baseline_max_bytes=_require(baseline, "max_bytes", int, "baseline_operation"),
        baseline_max_fields=_require(baseline, "max_fields", int, "baseline_operation"),
        ooxml=policy,
    )
    if limits.chunk_bytes >= limits.max_expanded_bytes:
        raise LimitsConfigError(
            "streaming.chunk_bytes 必须远小于 max_expanded_bytes，否则单块读取即可撑爆内存"
        )
    return limits


def load_limits(path: Path | None = None, *, force: bool = False) -> SyncLimits:
    """读取（mtime 缓存）容量预算配置。缺失/非法 **抛异常，不 fallback**。"""
    target = path or LIMITS_CONFIG_PATH
    if path is not None or force:
        return _parse(_read_json(target))
    with _LOCK:
        try:
            mtime = target.stat().st_mtime_ns
        except OSError as exc:
            raise LimitsConfigError(f"容量预算配置不可读: {target}") from exc
        if _CACHE["mtime"] != mtime or _CACHE["value"] is None:
            _CACHE["value"] = _parse(_read_json(target))
            _CACHE["mtime"] = mtime
        value = _CACHE["value"]
    assert isinstance(value, SyncLimits)
    return value


def _read_json(target: Path) -> dict[str, Any]:
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LimitsConfigError(f"容量预算配置不存在: {target}") from exc
    except json.JSONDecodeError as exc:
        raise LimitsConfigError(f"容量预算配置不是合法 JSON: {target} ({exc})") from exc
    if not isinstance(raw, dict):
        raise LimitsConfigError(f"容量预算配置根必须是对象: {target}")
    return raw


__all__ = [
    "LIMITS_CONFIG_PATH",
    "BudgetExceededError",
    "LimitsConfigError",
    "OoxmlPolicy",
    "SyncLimits",
    "load_limits",
]
