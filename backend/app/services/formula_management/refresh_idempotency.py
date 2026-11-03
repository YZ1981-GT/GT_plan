"""Draft Refresh 幂等判定（spec formula-hub-integrity-closure 任务 20 第一段 A-2c-1；ADR-FHIC-08「幂等」）。

纯函数与一个异常类：不连库、不发事件、不 import 业务服务与模型（只用标准库、``formula_runtime.contracts`` 与
``refresh_outcome`` / ``refresh_report_scope`` 的常量）；取数、查找 SQL、编排器接线与路由 409 在 A-2c-2。

- :func:`plan_fp`：计划指纹 = 排序去重的 scopes + 事务模式 + 覆盖确认 + 四表快照指纹 + runtime 的公式 / 预设 revision，
  勾选报表范围时再加 :class:`ReportBasis` 四项。🔴 对 ADR 的收紧：ADR 的组成项里没有 ``transaction_mode`` /
  ``confirm_overwrite``，这里二者都进指纹 —— 事务模式决定有失败时保留哪些写入、覆盖确认决定人工编辑是否被覆盖，
  只差这两项的两次请求写入结果不同，不能互相命中；
- :func:`rows_hash`：一组行的哈希（逐字段规范化、行序无关），A-2c-2 用来算试算表行与有效报表定义；
- :func:`effective_key`：有效键 = 请求键（超 64 字符取其 sha256）或 ``plan_fp``；
- :func:`latest` / :func:`decide`：按有效键查到的最近一条审计判定执行 / 命中 / 409（:class:`RefreshInProgress`）；
- :func:`write_key`：写进审计 ``idempotency_key`` 列的值，不撞部分唯一索引 ``(project_id, year, idempotency_key)``；
- :func:`hit_result` / :func:`hit_preset_application`：命中时由首次运行的审计记录构造响应（命中不写入、不发事件）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Protocol, TypeVar

from app.services.formula_management.refresh_outcome import IDEMPOTENT_HIT_STATUS
from app.services.formula_management.refresh_report_scope import REPORT_SCOPE, ROLLBACK_UNAVAILABLE_WARNING
from app.services.formula_runtime.contracts import ExecutionResult

#: 审计 ``detail`` 增写的两个键（A-2c-2 写入）：有效键（查找条件 = 列 = 有效键 或 ``detail.idempotency_base`` = 有效键）
#: 与本次计划指纹
DETAIL_BASE_KEY = "idempotency_base"
DETAIL_FP_KEY = "plan_fp"
#: 审计 ``idempotency_key`` 列是 ``varchar(64)``（PG 按字符计）
KEY_MAX_LENGTH = 64
#: 首次运行的 ``detail.outcome`` 是其中之一 ⇒ 命中；``partial`` / ``failed`` 重新执行
HIT_OUTCOMES: tuple[str, ...] = ("applied", "recomputed", "draft_marked", "no_effect")
IN_PROGRESS_ERROR_CODE = "DRAFT_REFRESH_IN_PROGRESS"

Decision = Literal["execute", "hit"]


class AuditRecordLike(Protocol):
    """判定读取审计记录的四个字段（``DraftRefreshAudit`` 满足本协议）。"""

    id: Any
    operated_at: datetime | None
    result_status: str
    detail: Any


R = TypeVar("R", bound=AuditRecordLike)


class RefreshInProgress(Exception):
    """同一有效键的首次运行仍在执行（审计 ``result_status == "executing"``）。

    路由在通用 ``except Exception`` 之前捕获并返回 409、不 commit。
    """

    status_code = 409
    code = IN_PROGRESS_ERROR_CODE

    def __init__(self, run_id: Any) -> None:
        self.run_id = str(run_id)
        self.message = (
            f"相同的刷新请求正在执行（首次运行 {self.run_id}），本次未执行、未写入任何数据；"
            "请等首次运行结束后再查看结果，不要重复提交。"
        )
        super().__init__(self.message)

    def to_detail(self) -> dict[str, Any]:
        return {"error_code": self.code, "message": self.message, "run_id": self.run_id}


@dataclass(frozen=True)
class ReportBasis:
    """勾选报表范围时进指纹的四项（A-2c-2 取数）：试算表行哈希（科目码, 审定, 未审, 期初）、有效报表定义哈希
    （类型, 行次, 规范化公式）、``report_freshness.CALC_VERSION``、过期行数（``stale_clause()``）。"""

    tb_rows_hash: str
    definitions_hash: str
    calc_version: int
    stale_count: int


def plan_fp(*, scopes: Iterable[str], transaction_mode: str, confirm_overwrite: bool, tb_snapshot_hash: str,
            formula_revision: str, preset_revision: str, report: ReportBasis | None = None) -> str:
    """计划指纹：sha256(规范 JSON) 的 64 位小写十六进制。

    勾选报表范围而 ``report`` 缺失或其中有项为 None ⇒ ValueError；未勾选时 ``report`` 不进指纹（给了也一样）。
    """
    selected = sorted(set(scopes))
    payload: dict[str, Any] = {
        "scopes": selected, "transaction_mode": transaction_mode, "confirm_overwrite": bool(confirm_overwrite),
        "tb_snapshot_hash": tb_snapshot_hash, "formula_revision": formula_revision, "preset_revision": preset_revision,
    }
    if REPORT_SCOPE in selected:
        basis = asdict(report) if report is not None else None
        if basis is None or None in basis.values():
            raise ValueError("勾选了报表范围，计划指纹须给报表四项（试算表行哈希、有效报表定义哈希、calc_version、"
                             f"过期行数）：{basis}")
        payload["report"] = basis
    return _sha256_text(_dumps(payload))


def rows_hash(rows: Iterable[Sequence[Any]]) -> str:
    """一组行的哈希：每行逐字段规范化后编码成规范 JSON，按编码排序，再 sha256(整个 JSON 数组) 的十六进制。

    行序无关、字段序有关、重复行计数。字段规范化：``None`` ⇒ ``null``；``Decimal`` / ``int`` / ``float``（``bool`` 除外）
    ⇒ 去尾零的定点字符串（``1.10`` 与 ``1.1``、``1`` 与 ``1.00`` 同串，``-0`` ⇒ ``"0"``，``1E+2`` ⇒ ``"100"``；不按上下文
    精度舍入；``float`` 先取 ``str()`` 的最短十进制写法）；字符串原样；枚举取 ``.value`` 再规范化；``bool`` 原样（不同于
    1 / 0）；其他类型 ⇒ TypeError。同一列的类型固定，故数字与同形字符串不区分（``Decimal("1.1")`` 与 ``"1.1"`` 同值）。
    """
    encoded = sorted(_dumps([_canonical_field(value) for value in row]) for row in rows)
    return _sha256_text("[" + ",".join(encoded) + "]")


def _canonical_field(value: Any) -> str | bool | None:
    if isinstance(value, Enum):
        value = value.value
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (Decimal, int, float)):
        text = format(Decimal(str(value)) if isinstance(value, float) else Decimal(value), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return "0" if text == "-0" else text
    raise TypeError(f"行哈希不支持字段类型 {type(value).__name__}：{value!r}")


def effective_key(request_key: str | None, plan_fingerprint: str) -> str:
    """有效键：请求键去首尾空白后非空 ⇒ 用它（超过 :data:`KEY_MAX_LENGTH` 个字符 ⇒ 用它的 sha256 十六进制，恰 64 位）；
    否则用 ``plan_fp``（ADR-FHIC-08：请求未带键时以 ``plan_fp`` 为键）。"""
    key = (request_key or "").strip()
    if not key:
        return plan_fingerprint
    return key if len(key) <= KEY_MAX_LENGTH else _sha256_text(key)


def latest(records: Iterable[R]) -> R | None:
    """最近一条：按 ``(operated_at, id)`` 降序取第一条，``operated_at`` 为 None 的排最后；空 ⇒ None。

    A-2c-2 的查找 SQL 用同一排序 ``ORDER BY operated_at DESC NULLS LAST, id DESC``（PG 的 DESC 默认 NULLS FIRST）。
    """
    return max(records, key=_recency, default=None)


def _recency(record: AuditRecordLike) -> tuple[bool, Any, Any]:
    at = record.operated_at
    return (at is not None, at if at is not None else 0, record.id)


def decide(prior: AuditRecordLike | None) -> Decision:
    """按有效键查到的最近一条审计（与 :func:`latest` 同排序）判定执行还是命中。

    ``result_status == "executing"`` ⇒ 抛 :class:`RefreshInProgress`；``"rolled_back"`` ⇒ 执行；``detail.outcome`` ∈
    :data:`HIT_OUTCOMES` ⇒ 命中；其余（partial / failed、``detail`` 不是 dict、改造前无 ``outcome`` 键、无记录）⇒ 执行。
    """
    if prior is None:
        return "execute"
    if prior.result_status == "executing":
        raise RefreshInProgress(prior.id)
    if prior.result_status == "rolled_back":
        return "execute"
    return "hit" if _detail(prior).get("outcome") in HIT_OUTCOMES else "execute"


def write_key(effective: str, occupied: int) -> str:
    """写进审计 ``idempotency_key`` 列的值：``occupied`` 为 0 ⇒ 有效键本身，否则 ``sha256(f"{有效键}#{occupied}")``。

    ``occupied`` = 本项目年度已有、属于这个有效键的记录条数，与查找同一条件（列 = 有效键 或
    ``detail.idempotency_base`` = 有效键），A-2c-2 在项目锁内计数 ⇒ 每重新执行一次占一个新列值，不撞部分唯一索引。
    🔴 只数「列 = 有效键」不够：唯一索引下它恒 ≤ 1，第三次执行会与第二次写同一个值。负数 ⇒ ValueError。
    """
    if occupied < 0:
        raise ValueError(f"已占用条数不能为负：{occupied}")
    return effective if occupied == 0 else _sha256_text(f"{effective}#{occupied}")


def hit_result(prior: AuditRecordLike) -> ExecutionResult:
    """命中时的结果：run_id = 首次运行的审计 id，``outcome`` 与三个计数取其 ``detail``（缺键按 0）。

    ``status = "idempotent_hit"``（``to_dict`` 给出 ``idempotent=True``、``affected_count = applied + recomputed``）；
    ``failures`` / ``post_commit_events`` 为空；首次运行含报表范围（``detail.scopes``，缺失按空）⇒
    ``rollback_available=False``、``warnings`` 带 :data:`ROLLBACK_UNAVAILABLE_WARNING`。
    """
    detail = _detail(prior)
    report_ran = REPORT_SCOPE in (detail.get("scopes") or [])
    return ExecutionResult(
        run_id=prior.id, status=IDEMPOTENT_HIT_STATUS, outcome=detail.get("outcome"),
        applied_count=_count(detail, "applied_count"), recomputed_count=_count(detail, "recomputed_count"),
        draft_marked_count=_count(detail, "draft_marked_count"), failures=[], post_commit_events=[],
        rollback_available=not report_ran, warnings=[ROLLBACK_UNAVAILABLE_WARNING] if report_ran else [],
    )


def hit_preset_application(prior: AuditRecordLike) -> dict[str, Any] | None:
    """命中时回放首次运行的 ``detail.preset_application``（是 dict 才返回，否则 None）。"""
    value = _detail(prior).get("preset_application")
    return value if isinstance(value, dict) else None


def _detail(prior: AuditRecordLike) -> dict[str, Any]:
    return prior.detail if isinstance(prior.detail, dict) else {}


def _count(detail: dict[str, Any], key: str) -> int:
    return int(detail.get(key) or 0)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def runtime_revisions(runtime_mutations: Iterable[Any], preset_units: Iterable[Any]) -> tuple[str, str]:
    """计划指纹里 runtime 的两个 revision ``(formula_revision, preset_revision)``（A-2c-2 由编排器 ``_execute_governed`` 的
    runtime 分支原样搬来，算法与 JSON 写法逐字不变；编排器在判定前算一次，指纹与 ``execute_refresh`` 共用）。

    ``formula_revision`` = 去重后 runtime mutation 的（来源公式 id, 目标 addr_id, after 的 ``str``, expected_version）列表的
    sha256，没有 runtime mutation 时按空列表算；``preset_revision`` = 预设初稿单元的（unit_scope, after_value）列表的 sha256。
    """
    revision_payload = [
        {
            "source_formula_id": str(m.source_formula_id or ""),
            "target": m.target.addr_id,
            "after": str(m.after_value),
            "version": m.expected_version,
        }
        for m in runtime_mutations
    ]
    formula_revision = hashlib.sha256(
        json.dumps(revision_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    preset_revision = hashlib.sha256(
        json.dumps(
            [
                {"unit_scope": unit.unit_scope, "after": unit.after_value}
                for unit in preset_units
            ],
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return formula_revision, preset_revision
