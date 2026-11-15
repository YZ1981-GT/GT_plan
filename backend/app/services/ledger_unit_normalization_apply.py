"""账套单位归一化的 apply / rollback 双闸门与可逆证据（spec platform-global-display-settings-closure 任务 9 / AC-18）。

设计要点（design §5、§13 第 9 条、§18）：

1. **写脚本与只读 inspector 物理分离**：本模块只被显式 CLI 调用，巡检路径不 import 它。
2. **apply 三重闸门**：环境变量 + `--apply` + `--dataset-id` 双录 + `--source-unit`，
   四者缺一即拒绝（少一层就等于「误跑一次改掉生产金额」）。
3. **rollback 额外闸门**：还须 `--normalization-version` 且必须是**最后一个未回滚**版本。
4. **presence-aware 快照**：history 存的是「键是否存在」+ 原值，而不是 `None`，
   否则 `source_summary` 里「键缺失」与「显式 null」会被混为一谈、回滚后无法精确复原。
5. **可逆证据**：apply 记 before/after canonical hash；rollback 先闭合
   `after-hash → 反向 before-hash`，再精确恢复原分类，最后追加**独立** history 行。
6. **单数据集事务**：四表金额、单位元数据、history 与 hash 同事务，任一失败整单回滚。

🔴 本模块**不在共享 PG 上运行**：apply/rollback 必须由用户另行放行，且只在隔离库验证。
   共享库只允许跑 `ledger_unit_inspector.inspect_datasets`（只读）。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

UnitName = Literal["yuan", "qian", "wan"]

#: 单位 → 因子（与 design §5 固定的 1 / 1000 / 10000 逐值一致）。
UNIT_FACTORS: dict[str, Decimal] = {
    "yuan": Decimal("1"),
    "qian": Decimal("1000"),
    "wan": Decimal("10000"),
}

#: apply 要求的环境变量（缺一即拒绝）。
APPLY_ENV_FLAG = "GT_LEDGER_UNIT_APPLY"
ROLLBACK_ENV_FLAG = "GT_LEDGER_UNIT_ROLLBACK"

#: 四表金额列（与 inspector 的 `AMOUNT_FIELDS` 同一份口径，不从别处复制）。
from app.services.ledger_unit_inspector import AMOUNT_FIELDS  # noqa: E402

_AMOUNT_FIELDS_BY_TABLE = AMOUNT_FIELDS


class UnitApplyGateError(Exception):
    """apply / rollback 闸门未通过。"""


class UnitApplyStateError(Exception):
    """数据集状态不允许本次操作（非最后版本、快照篡改、分类不符等）。"""


# ── 闸门 ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ApplyRequest:
    """apply 的完整请求；每个字段都是一个独立闸门。"""

    dataset_id: str
    source_unit: str
    confirm_dataset_id: str  # 双录：必须与 dataset_id 逐字相等
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))

    def validate(self) -> None:
        problems: list[str] = []
        if self.env.get(APPLY_ENV_FLAG) != "1":
            problems.append(f"缺少环境变量 {APPLY_ENV_FLAG}=1")
        if not self.dataset_id:
            problems.append("缺少 --dataset-id")
        if self.confirm_dataset_id != self.dataset_id:
            problems.append(
                f"--confirm-dataset-id（{self.confirm_dataset_id!r}）与 --dataset-id"
                f"（{self.dataset_id!r}）不一致（要求双录）"
            )
        if self.source_unit not in UNIT_FACTORS:
            problems.append(
                f"--source-unit={self.source_unit!r} 非法（只接受 {sorted(UNIT_FACTORS)}）"
            )
        if problems:
            raise UnitApplyGateError("apply 闸门未通过：" + "；".join(problems))


@dataclass(frozen=True)
class RollbackRequest:
    """rollback 的完整请求；比 apply 多一层「必须是最新未回滚版本」。"""

    dataset_id: str
    normalization_version: int
    confirm_dataset_id: str
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))

    def validate(self) -> None:
        problems: list[str] = []
        if self.env.get(ROLLBACK_ENV_FLAG) != "1":
            problems.append(f"缺少环境变量 {ROLLBACK_ENV_FLAG}=1")
        if not self.dataset_id:
            problems.append("缺少 --dataset-id")
        if self.confirm_dataset_id != self.dataset_id:
            problems.append("--confirm-dataset-id 与 --dataset-id 不一致（要求双录）")
        if not isinstance(self.normalization_version, int) or self.normalization_version < 1:
            problems.append(
                f"--normalization-version={self.normalization_version!r} 非法（须为正整数）"
            )
        if problems:
            raise UnitApplyGateError("rollback 闸门未通过：" + "；".join(problems))


# ── presence-aware 快照与 canonical hash ────────────────────


def snapshot_unit_metadata(source_summary: Any) -> dict[str, Any]:
    """抓 `source_summary` 里与单位有关的键的 **presence-aware** 快照。

    🔴 为什么不能只存值：`{"unit_normalization": None}` 与「没有这个键」
    在回滚时要恢复成不同状态，两者用 `dict.get()` 读出来都是 `None`。
    所以每个键记 `{"present": bool, "value": ...}`。
    """
    keys = ("unit_normalization", "source_unit", "declared_unit")
    summary = source_summary if isinstance(source_summary, dict) else {}
    return {
        key: {"present": key in summary, "value": summary.get(key)}
        for key in keys
    }


def restore_unit_metadata(base: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    """按 presence-aware 快照恢复 `source_summary`，**保留其他键**。

    返回新 dict（不改入参）：`base` 的其他键原样保留，单位相关的三个键按快照
    精确恢复（`present=False` 的键被删除，而不是写成 null）。
    """
    restored = dict(base) if isinstance(base, dict) else {}
    for key, entry in snapshot.items():
        if entry.get("present"):
            restored[key] = entry.get("value")
        else:
            restored.pop(key, None)
    return restored


def canonical_hash(payload: Any) -> str:
    """稳定的 canonical JSON hash（键排序、无空格、Decimal 转字符串）。"""
    text = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── 单位换算（唯一入口）────────────────────────────────────


def normalize_amount(value: Any, source_unit: str) -> Decimal | None:
    """把 source unit 的金额换成元；`None` 原样保留。

    🔴 三条与设计逐字一致：
    - 只对 **finite Decimal** 执行 `value * factor`，再 `ROUND_HALF_UP` 到 0.01；
    - `None` 原样保留（不是 0）；
    - NaN / ±Infinity 抛 `LEDGER_AMOUNT_NOT_FINITE`，不可解析的非空值抛
      `LEDGER_AMOUNT_INVALID`，错误只含调用方给的定位信息。

    本函数是「唯一金额内核」：两引擎、dry-run 与 hash 都必须经它。
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise UnitApplyStateError(f"LEDGER_AMOUNT_INVALID: {exc}") from exc
    if not amount.is_finite():
        raise UnitApplyStateError("LEDGER_AMOUNT_NOT_FINITE: NaN/Infinity 不接受")
    factor = UNIT_FACTORS.get(source_unit)
    if factor is None:
        raise UnitApplyGateError(f"未知 source_unit: {source_unit!r}")
    from decimal import ROUND_HALF_UP

    return (amount * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── history 行的构造（纯函数，便于单测与对拍）──────────────


@dataclass(frozen=True)
class HistoryRecord:
    """一次 apply 或 rollback 的 history 行（写库由调用方在单数据集事务内完成）。"""

    dataset_id: str
    normalization_version: int
    action: Literal["apply", "rollback"]
    source_unit: str
    before_hash: str
    after_hash: str
    metadata_snapshot: dict[str, Any]

    def to_row(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "normalization_version": self.normalization_version,
            "action": self.action,
            "source_unit": self.source_unit,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "metadata_snapshot": self.metadata_snapshot,
        }


def build_apply_history(
    *,
    dataset_id: str,
    normalization_version: int,
    source_unit: str,
    before_summary: Any,
    after_summary: Any,
) -> HistoryRecord:
    """apply 的 history：before/after 都是**单位元数据**快照的 canonical hash。

    只对单位元数据算 hash（不含四表金额）——金额由四表行数/合计另行核对，
    混进来会让「同一份元数据、不同数据量」的两次 apply 得到不同 hash，
    回滚时就无法判断「元数据是否已被后续操作改过」。
    """
    before_snapshot = snapshot_unit_metadata(before_summary)
    after_snapshot = snapshot_unit_metadata(after_summary)
    return HistoryRecord(
        dataset_id=dataset_id,
        normalization_version=normalization_version,
        action="apply",
        source_unit=source_unit,
        before_hash=canonical_hash(before_snapshot),
        after_hash=canonical_hash(after_snapshot),
        metadata_snapshot=before_snapshot,
    )


def build_rollback_history(
    *,
    apply_record: HistoryRecord,
    current_summary: Any,
    normalization_version: int,
) -> HistoryRecord:
    """rollback 的 history：先闭合 `current → 反向 before`，再追加独立行。

    🔴 `current_summary` 的单位元数据 hash 必须等于 apply 的 `after_hash`，
    否则说明 apply 之后有人改过元数据 ⇒ 拒绝回滚（否则会把别人的改动一起抹掉）。
    """
    current_hash = canonical_hash(snapshot_unit_metadata(current_summary))
    if current_hash != apply_record.after_hash:
        raise UnitApplyStateError(
            "回滚前闭合失败：当前单位元数据 hash 与 apply 的 after_hash 不一致"
            f"（current={current_hash[:12]}…, after={apply_record.after_hash[:12]}…）"
            "；apply 之后元数据已被改动，拒绝回滚"
        )
    return HistoryRecord(
        dataset_id=apply_record.dataset_id,
        normalization_version=normalization_version,
        action="rollback",
        source_unit=apply_record.source_unit,
        before_hash=current_hash,
        after_hash=apply_record.before_hash,  # 反向闭合：回到 apply 之前
        metadata_snapshot=apply_record.metadata_snapshot,
    )


def assert_last_uncancelled_version(
    *, target_version: int, history_versions: list[int], rolled_back: set[int],
) -> None:
    """rollback 只能针对**最后一个未回滚**的 apply 版本。

    非最后版本回滚会让后续 apply 的 before_hash 指向一个已不存在的状态。
    """
    pending = sorted(v for v in history_versions if v not in rolled_back)
    if not pending:
        raise UnitApplyStateError("没有可回滚的 apply 版本")
    if target_version != pending[-1]:
        raise UnitApplyStateError(
            f"只能回滚最后一个未回滚版本（{pending[-1]}），请求的是 {target_version}"
        )
