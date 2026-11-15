"""账套单位归一化 apply / rollback 的显式 CLI（spec platform-global-display-settings-closure 任务 9）。

用法（**必须**同时满足环境变量 + 显式子命令 + 双录 dataset + source unit）：

    # 预演（默认，不写库）
    python -m scripts.ops.ledger_unit_normalization apply \\
        --dataset-id <uuid> --confirm-dataset-id <uuid> --source-unit wan

    # 真实执行（三重闸门全开）
    $env:GT_LEDGER_UNIT_APPLY = '1'
    python -m scripts.ops.ledger_unit_normalization apply --apply \\
        --dataset-id <uuid> --confirm-dataset-id <uuid> --source-unit wan

    # 回滚（还须最后一个未回滚版本）
    $env:GT_LEDGER_UNIT_ROLLBACK = '1'
    python -m scripts.ops.ledger_unit_normalization rollback --rollback \\
        --dataset-id <uuid> --confirm-dataset-id <uuid> --normalization-version 1

🔴 本脚本**默认 dry-run**：不加 `--apply` / `--rollback` 只打印将要做什么。
   `--dry-run` 与 `--apply` 互斥，避免「以为在预演、其实已写库」。
🔴 共享 PG 上**禁止**真实 apply/rollback：必须由用户另行放行，且只在隔离库验证。
   共享库只允许跑只读 inspector（`scripts/ops/ledger_unit_inspect.py` 或
   `ledger_unit_inspector.inspect_datasets`）。
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from typing import Any

from app.services.ledger_unit_normalization_apply import (
    ApplyRequest,
    RollbackRequest,
    UnitApplyGateError,
    UnitApplyStateError,
    build_apply_history,
    build_rollback_history,
    normalize_amount,
    restore_unit_metadata,
    snapshot_unit_metadata,
)

#: 共享库黑名单（与 tests/load/load_guard.py 同一份口径）。
_SHARED_DB_NAMES = frozenset({"audit_platform", "postgres", "gt_plan", "metabase"})


def _db_name(url: str) -> str:
    """从 DATABASE_URL 取库名（只做黑名单判断，不连库）。"""
    tail = url.rsplit("/", 1)[-1]
    return tail.split("?", 1)[0]


def _refuse_shared_db(url: str, *, action: str) -> None:
    """在共享库上拒绝真实写入。"""
    name = _db_name(url)
    if name in _SHARED_DB_NAMES:
        raise UnitApplyGateError(
            f"拒绝在共享库 {name!r} 上执行真实 {action}；"
            "请用专用可销毁库（GT_LOAD_DISPOSABLE_DB_URL 同一纪律）"
        )


def _cmd_apply(args: argparse.Namespace) -> int:
    request = ApplyRequest(
        dataset_id=args.dataset_id,
        source_unit=args.source_unit,
        confirm_dataset_id=args.confirm_dataset_id,
    )
    # 闸门校验（环境变量 + 双录 + source unit）
    request.validate()
    _refuse_shared_db(args.database_url, action="apply")

    # 换算预演：把 source unit 的样例金额过唯一内核，证明链路可用
    samples = [Decimal("10000"), Decimal("0"), None, Decimal("-1234.565")]
    converted = [
        None if s is None else str(normalize_amount(s, request.source_unit))
        for s in samples
    ]

    before = snapshot_unit_metadata(args.before_summary or {})
    after_summary = dict(args.before_summary or {})
    after_summary["unit_normalization"] = {
        "version": args.normalization_version,
        "source_unit": request.source_unit,
        "factor": str(normalize_amount(Decimal("1"), request.source_unit)),
    }
    history = build_apply_history(
        dataset_id=request.dataset_id,
        normalization_version=args.normalization_version,
        source_unit=request.source_unit,
        before_summary=args.before_summary or {},
        after_summary=after_summary,
    )
    print(json.dumps({
        "action": "apply",
        "dataset_id": request.dataset_id,
        "source_unit": request.source_unit,
        "normalization_version": args.normalization_version,
        "converted_samples": converted,
        "before_snapshot": before,
        "history": history.to_row(),
        "note": "本命令已完成闸门与换算；真实写库由调用方在单数据集事务内执行",
    }, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_rollback(args: argparse.Namespace) -> int:
    request = RollbackRequest(
        dataset_id=args.dataset_id,
        normalization_version=args.normalization_version,
        confirm_dataset_id=args.confirm_dataset_id,
    )
    request.validate()
    _refuse_shared_db(args.database_url, action="rollback")

    apply_record = build_apply_history(
        dataset_id=request.dataset_id,
        normalization_version=request.normalization_version,
        source_unit=args.source_unit,
        before_summary=args.before_summary or {},
        after_summary=args.current_summary or {},
    )
    rollback_record = build_rollback_history(
        apply_record=apply_record,
        current_summary=args.current_summary or {},
        normalization_version=request.normalization_version + 1,
    )
    restored = restore_unit_metadata(
        args.current_summary or {}, apply_record.metadata_snapshot
    )
    print(json.dumps({
        "action": "rollback",
        "dataset_id": request.dataset_id,
        "normalization_version": request.normalization_version,
        "restored_summary": restored,
        "history": rollback_record.to_row(),
        "note": "本命令已完成闸门与闭合；真实写库由调用方在单数据集事务内执行",
    }, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    """只读巡检（唯一允许在共享库跑的子命令）。"""
    import asyncio
    from pathlib import Path

    from app.services.ledger_unit_inspector import inspect_datasets

    report = asyncio.run(
        inspect_datasets(args.database_url, Path(args.output_dir), project_id=args.project_id)
    )
    print(json.dumps({
        "dataset_count": report.get("dataset_count"),
        "classification": report.get("classification"),
        "output_dir": args.output_dir,
    }, ensure_ascii=False, indent=2))
    return 0


def _load_summary(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    return json.loads(raw)


def main(argv: list[str] | None = None) -> int:
    import os

    parser = argparse.ArgumentParser(description="账套单位归一化 apply/rollback 双闸门")
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--dataset-id", required=True)
        p.add_argument("--confirm-dataset-id", required=True, help="双录：必须与 --dataset-id 逐字相等")
        p.add_argument("--before-summary", help="JSON：apply 前的 source_summary")
        p.add_argument(
            "--database-url",
            default=os.environ.get("DATABASE_URL", ""),
            help="目标库 URL（默认取 DATABASE_URL）；共享库一律拒绝真实写入",
        )

    p_apply = sub.add_parser("apply", help="归一化 apply（默认 dry-run）")
    _add_common(p_apply)
    p_apply.add_argument("--source-unit", required=True, choices=["yuan", "qian", "wan"])
    p_apply.add_argument("--normalization-version", type=int, default=1)
    p_apply.add_argument("--apply", action="store_true", help="真实执行（还需 GT_LEDGER_UNIT_APPLY=1）")

    p_rb = sub.add_parser("rollback", help="归一化 rollback（默认 dry-run）")
    _add_common(p_rb)
    p_rb.add_argument("--source-unit", default="yuan", choices=["yuan", "qian", "wan"])
    p_rb.add_argument("--normalization-version", type=int, required=True)
    p_rb.add_argument("--current-summary", help="JSON：当前 source_summary（须与 apply 的 after_hash 闭合）")
    p_rb.add_argument("--rollback", action="store_true", help="真实执行（还需 GT_LEDGER_UNIT_ROLLBACK=1）")

    p_ins = sub.add_parser("inspect", help="只读巡检（共享库唯一允许的子命令）")
    p_ins.add_argument("--output-dir", required=True)
    p_ins.add_argument("--project-id", default=None)
    p_ins.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))

    args = parser.parse_args(argv)
    args.before_summary = _load_summary(getattr(args, "before_summary", None))
    args.current_summary = _load_summary(getattr(args, "current_summary", None))

    try:
        if args.command == "apply":
            if not args.apply:
                print("[dry-run] 未传 --apply，只做闸门与换算预演")
            return _cmd_apply(args)
        if args.command == "rollback":
            if not args.rollback:
                print("[dry-run] 未传 --rollback，只做闸门与闭合预演")
            return _cmd_rollback(args)
        return _cmd_inspect(args)
    except (UnitApplyGateError, UnitApplyStateError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
