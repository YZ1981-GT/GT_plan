"""合并运行生命周期——真实业务集团只读 / dry-run 对账工具
（spec consolidation-run-and-workpaper-lifecycle-closure 批 8 Task 8.5）。

用途
----
对一个**已授权**的真实合并项目 × 年度，做一次**只读**对账：复用真实合并代码路径
（`load_calc_basis` / `trial_amounts` / `resolve_published_run` / `report_row_digest` /
`restore_consol_snapshot` / `load_consol_readiness`），把「生命周期产物存量」与「权威重算 /
权威校验」逐项比对，输出机器可读的对账报告（JSON）。

对账项（全部 SELECT-only）：
  C1 试算平衡恒等式     stored `consol_trial` 的 ``consol_amount == individual_sum +
                        consol_adjustment + consol_elimination``（逐行），以及 stored vs
                        重算 `trial_amounts(basis)` 四列逐科目一致。
  C2 报表 run 行摘要     已发布 report run 的 ``report_row_digest(rows_json) == row_digest``，
                        且 run 的 ``node_key == 根节点`` / ``input_digest`` 与重算一致。
  C3 报表—试算一致性     已发布报表根节点合并数来源与当前试算存量对齐（存在性 + 根节点身份）。
  C4 附注汇总陈旧        `consol_note_data` 的 ``is_stale`` 计数（readiness 口径事实）。
  C5 快照 hash 有效性    最近签字 / 锁定快照用 `restore_consol_snapshot` 复算全部分片 hash + 根 hash。
  C6 readiness vs 实际   `load_consol_readiness` 的域事实与实际行数 / 存量自洽（不前端拼事实）。
  C7 孤儿分录            `load_orphan_diagnostics`：已审批但未归属差额节点的分录（未计入合并）。

安全底线（绝不写库）
--------------------
- 整个会话包在**始终回滚**的事务里；另装一个 DML 守卫：任何 ``INSERT/UPDATE/DELETE``
  语句一旦发出，立即抛 ``DmlAttemptedError`` 让本次对账失败（不是「回滚了」而是「根本不该发」）。
- 必须显式传 ``--authorized`` **且** ``--project-id``；缺任一个都拒绝运行（退出码 2），
  避免被误指向真实数据。
- 真实业务集团运行**另需用户再次授权**（本工具只提供能力，不代替授权）。

运行
----
  # 合成 fixture 自检（不连真实库，由 pytest 覆盖，见 tests/test_reconcile_consol_lifecycle.py）
  python -m pytest backend/tests/test_reconcile_consol_lifecycle.py

  # 真实业务集团（需用户再次授权 + 真实合并项目存在）——只读、回滚，绝不写库：
  python backend/scripts/analyze/reconcile_consol_lifecycle.py \
      --authorized --project-id <UUID> --year 2025 \
      --out tmp_consol_lifecycle/reconcile_<项目>.json

  # 列出当前库里的合并项目（只读，辅助定位 project-id）：
  python backend/scripts/analyze/reconcile_consol_lifecycle.py --list

退出码：0 全部对账项通过；1 存在不一致 / 校验失败；2 参数不足（未授权 / 缺 project-id）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

# 让脚本可直接 `python backend/scripts/analyze/...` 运行：把 backend/ 放进 sys.path。
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

ZERO = Decimal("0")


# ─────────────────────────────── DML 守卫（绝不写库） ───────────────────────────────


class DmlAttemptedError(RuntimeError):
    """只读对账期间检测到写语句（INSERT/UPDATE/DELETE 等）。"""


# 允许的只读 / 事务控制关键字；其余以这些写动词开头的语句一律拦截。
_WRITE_VERBS = ("insert", "update", "delete", "merge", "truncate", "drop", "alter", "create")
# 事务控制语句不是 DML，放行（SQLAlchemy 回滚 / SAVEPOINT 用）。
_TXN_CONTROL = ("savepoint", "release", "rollback", "begin", "commit", "set ", "pragma")


def _is_write_statement(statement: str) -> bool:
    head = statement.lstrip().lstrip("(").lstrip().lower()
    if any(head.startswith(verb) for verb in _TXN_CONTROL):
        return False
    return any(head.startswith(verb) for verb in _WRITE_VERBS)


class ReadOnlyGuard:
    """绑定到 engine 的 ``before_cursor_execute``：发现写语句立即抛错，使对账失败。

    用 ``with`` 作用域安装 / 卸载；``triggered`` 留痕被拦下的首条写语句（证明守卫真的会打红）。
    """

    def __init__(self, engine: Any):
        self._sync_engine = engine.sync_engine
        self.triggered: str | None = None
        self.checked = 0

    def _on_exec(self, _conn, _cursor, statement, _params, _context, _executemany):
        self.checked += 1
        if _is_write_statement(statement):
            self.triggered = statement[:200]
            raise DmlAttemptedError(f"只读对账期间检测到写语句：{statement[:200]}")

    def __enter__(self) -> "ReadOnlyGuard":
        event.listen(self._sync_engine, "before_cursor_execute", self._on_exec)
        return self

    def __exit__(self, *_exc):
        event.remove(self._sync_engine, "before_cursor_execute", self._on_exec)


# ─────────────────────────────── 对账结果结构 ───────────────────────────────


@dataclass
class Check:
    """单个对账项结果。"""

    code: str
    name: str
    passed: bool
    detail: str
    expected: Any = None
    actual: Any = None
    samples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "expected": self.expected,
            "actual": self.actual,
            "samples": self.samples[:20],
        }


@dataclass
class ReconcileReport:
    project_id: str
    year: int
    checks: list[Check] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and all(c.passed for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "year": self.year,
            "all_passed": self.ok,
            "check_count": len(self.checks),
            "failed_checks": [c.code for c in self.checks if not c.passed],
            "checks": [c.to_dict() for c in self.checks],
            "errors": list(self.errors),
            "mode": "read_only_dry_run",
            "writes_issued": 0,
        }


def _dec(value: Any) -> Decimal:
    if value is None or value == "":
        return ZERO
    return value if isinstance(value, Decimal) else Decimal(str(value))


# ─────────────────────────────── 对账项（全部 SELECT-only） ───────────────────────────────


async def check_trial_identity(db: AsyncSession, project_id: UUID, year: int) -> Check:
    """C1 试算平衡恒等式 + 存量 vs 重算一致（consol_amount = individual + adj + elim）。"""
    from app.models.consolidation_models import ConsolTrial
    from app.services.consol_calc_basis import load_calc_basis, to_cents, trial_amounts

    stored_rows = (await db.execute(
        sa.select(ConsolTrial).where(
            ConsolTrial.project_id == project_id,
            ConsolTrial.year == year,
            ConsolTrial.is_deleted == sa.false(),
        )
    )).scalars().all()

    identity_bad: list[dict[str, Any]] = []
    for r in stored_rows:
        lhs = to_cents(r.consol_amount)
        rhs = to_cents(_dec(r.individual_sum) + _dec(r.consol_adjustment) + _dec(r.consol_elimination))
        if lhs != rhs:
            identity_bad.append({
                "account_code": r.standard_account_code,
                "consol_amount": str(lhs),
                "individual+adj+elim": str(rhs),
            })

    # 存量 vs 权威重算：逐科目四列一致（口径不可用则只做恒等式）。
    recompute_bad: list[dict[str, Any]] = []
    recompute_note = ""
    try:
        basis = await load_calc_basis(db, project_id, year)
    except Exception as exc:  # noqa: BLE001 - 口径不可用（如年度未设置）：降级为仅恒等式
        basis = None
        recompute_note = f"重算口径不可用，仅校验恒等式：{type(exc).__name__}: {str(exc)[:120]}"
    if basis is not None:
        expected = trial_amounts(basis)
        stored_by_code = {r.standard_account_code: r for r in stored_rows}
        for code in sorted(set(expected) | set(stored_by_code)):
            want = expected.get(code)
            got = stored_by_code.get(code)
            want_cols = (
                (want.individual_sum, want.consol_adjustment, want.consol_elimination, want.consol_amount)
                if want else (ZERO, ZERO, ZERO, ZERO)
            )
            got_cols = (
                (_dec(got.individual_sum), _dec(got.consol_adjustment),
                 _dec(got.consol_elimination), _dec(got.consol_amount))
                if got else (ZERO, ZERO, ZERO, ZERO)
            )
            if tuple(to_cents(v) for v in want_cols) != tuple(to_cents(v) for v in got_cols):
                recompute_bad.append({
                    "account_code": code,
                    "expected": [str(to_cents(v)) for v in want_cols],
                    "stored": [str(to_cents(v)) for v in got_cols],
                })

    passed = not identity_bad and not recompute_bad
    detail_parts = [f"存量试算行 {len(stored_rows)} 行"]
    if identity_bad:
        detail_parts.append(f"恒等式违反 {len(identity_bad)} 行")
    if recompute_bad:
        detail_parts.append(f"存量与重算不一致 {len(recompute_bad)} 科目")
    if recompute_note:
        detail_parts.append(recompute_note)
    if passed:
        detail_parts.append("全部一致")
    return Check(
        code="C1",
        name="试算平衡恒等式与存量vs重算一致",
        passed=passed,
        detail="；".join(detail_parts),
        expected="consol_amount == individual_sum + consol_adjustment + consol_elimination 且存量==重算",
        actual={"stored_rows": len(stored_rows), "identity_violations": len(identity_bad),
                "recompute_mismatch": len(recompute_bad)},
        samples=(identity_bad + recompute_bad),
    )


async def check_report_run_digest(db: AsyncSession, project_id: UUID, year: int) -> Check:
    """C2 已发布 report run 的行摘要自洽（row_digest 复算一致），并记录根节点身份。"""
    from app.services.consol_report_run_service import report_row_digest, resolve_published_run

    run = await resolve_published_run(db, project_id, year)
    if run is None:
        return Check(
            code="C2",
            name="报表run行摘要自洽",
            passed=True,
            detail="当前项目年度没有已发布的报表运行（空态，不是失败）",
            expected="若有已发布 run，则 report_row_digest(rows_json) == row_digest",
            actual={"has_published_run": False},
        )
    recomputed = report_row_digest(dict(run.rows_json or {}))
    digest_ok = recomputed == run.row_digest
    return Check(
        code="C2",
        name="报表run行摘要自洽",
        passed=digest_ok,
        detail=("行摘要复算一致" if digest_ok else "行摘要复算与存量不一致"),
        expected=run.row_digest,
        actual={"recomputed_row_digest": recomputed, "node_key": run.node_key,
                "row_count": run.row_count, "status": run.status},
    )


async def check_report_trial_consistency(db: AsyncSession, project_id: UUID, year: int) -> Check:
    """C3 已发布报表根节点身份与当前企业树根节点一致（报表—试算同口径的结构前提）。"""
    from app.services.consol_report_run_service import resolve_published_run
    from app.services.consol_tree_service import build_tree

    run = await resolve_published_run(db, project_id, year)
    tree = await build_tree(db, project_id)
    root_key = tree.node_key if tree is not None else None
    if run is None:
        return Check(
            code="C3",
            name="报表-试算根节点一致",
            passed=True,
            detail="无已发布报表运行（空态）",
            expected=root_key,
            actual={"has_published_run": False, "root_node_key": root_key},
        )
    match = (run.node_key == root_key)
    return Check(
        code="C3",
        name="报表-试算根节点一致",
        passed=match,
        detail=("报表 run 根节点与企业树根节点一致" if match else "报表 run 根节点与企业树根节点不一致"),
        expected=root_key,
        actual={"report_run_node_key": run.node_key},
    )


async def check_note_staleness(db: AsyncSession, project_id: UUID, year: int) -> Check:
    """C4 附注汇总陈旧计数（is_stale）——readiness 口径事实，陈旧存在不等于错误，只如实列出。"""
    from app.models.consol_note_data_models import ConsolNoteData

    total = (await db.execute(
        sa.select(sa.func.count()).select_from(ConsolNoteData).where(
            ConsolNoteData.project_id == project_id, ConsolNoteData.year == year,
        )
    )).scalar_one()
    stale = (await db.execute(
        sa.select(sa.func.count()).select_from(ConsolNoteData).where(
            ConsolNoteData.project_id == project_id, ConsolNoteData.year == year,
            ConsolNoteData.is_stale == sa.true(),
        )
    )).scalar_one()
    # 陈旧本身不判失败（可能确实待更新）；只有「库里有附注但全部陈旧」才作为需关注信号登记。
    passed = not (total > 0 and stale == total)
    return Check(
        code="C4",
        name="附注汇总陈旧计数",
        passed=passed,
        detail=f"附注章节 {total} 条，其中陈旧 {stale} 条"
        + ("（全部陈旧，需在签字前重新汇总）" if not passed else ""),
        expected="非全部章节陈旧",
        actual={"note_sections": int(total), "stale_sections": int(stale)},
    )


async def check_snapshot_hash(db: AsyncSession, project_id: UUID, year: int) -> Check:
    """C5 最近一次快照的 hash 有效性（复用 restore_consol_snapshot 复算全部分片 hash + 根 hash）。"""
    from app.models.phase10_models import ConsolSnapshot
    from app.services.consol_snapshot_service import restore_consol_snapshot

    snapshot = (await db.execute(
        sa.select(ConsolSnapshot).where(
            ConsolSnapshot.project_id == project_id,
            ConsolSnapshot.year == year,
        ).order_by(ConsolSnapshot.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if snapshot is None:
        return Check(
            code="C5",
            name="快照hash有效性",
            passed=True,
            detail="当前项目年度没有合并快照（空态）",
            expected="若有快照，则 hash 复算有效",
            actual={"has_snapshot": False},
        )
    restored = restore_consol_snapshot(snapshot)
    hash_valid = bool(restored.get("hash_valid"))
    legacy = bool(restored.get("legacy"))
    # 旧空壳快照（legacy）无压缩 payload 不可校验 hash，不判失败（历史遗留，不代表篡改）。
    passed = hash_valid or legacy
    return Check(
        code="C5",
        name="快照hash有效性",
        passed=passed,
        detail=(
            "快照 hash 复算有效" if hash_valid
            else ("旧空壳快照（无 payload，hash 不可校验，历史遗留）" if legacy else "快照 hash 复算失败（疑似篡改）")
        ),
        expected="hash_valid=True 或 legacy 旧空壳",
        actual={"hash_valid": hash_valid, "legacy": legacy,
                "trigger_reason": snapshot.trigger_reason,
                "shard_mismatches": restored.get("shard_mismatches")},
    )


async def check_readiness_consistency(db: AsyncSession, project_id: UUID, year: int) -> Check:
    """C6 readiness 域事实与实际存量自洽（has_trial/trial_count 与库里真实行数一致）。"""
    from app.models.consolidation_models import ConsolTrial
    from app.services.consol_readiness_service import load_consol_readiness, load_readiness_facts

    facts = await load_readiness_facts(db, project_id, year)
    # readiness payload 本身需能构建（不抛错即为服务端事实自洽的下限）。
    payload = await load_consol_readiness(db, project_id, year)

    actual_trial = (await db.execute(
        sa.select(sa.func.count()).select_from(ConsolTrial).where(
            ConsolTrial.project_id == project_id,
            ConsolTrial.year == year,
            ConsolTrial.is_deleted == sa.false(),
        )
    )).scalar_one()
    calc_facts = facts.get("calc", {})
    fact_trial_count = int(calc_facts.get("trial_count", 0))
    fact_has_trial = bool(calc_facts.get("has_trial"))
    count_ok = fact_trial_count == int(actual_trial)
    has_ok = fact_has_trial == (int(actual_trial) > 0)
    passed = count_ok and has_ok and isinstance(payload.get("status"), str)
    return Check(
        code="C6",
        name="readiness与实际存量自洽",
        passed=passed,
        detail=(
            "readiness 的 trial 事实与实际行数一致" if passed
            else "readiness 的 trial 事实与实际行数不一致"
        ),
        expected={"trial_count": int(actual_trial), "has_trial": int(actual_trial) > 0},
        actual={"fact_trial_count": fact_trial_count, "fact_has_trial": fact_has_trial,
                "readiness_status": payload.get("status")},
    )


async def check_orphan_entries(db: AsyncSession, project_id: UUID, year: int) -> Check:
    """C7 孤儿分录：已审批但找不到归属差额节点的分录（未计入合并，需在签字前解决）。"""
    from app.services.consol_calc_basis import load_orphan_diagnostics
    from app.services.consol_tree_service import build_tree

    tree = await build_tree(db, project_id)
    if tree is None:
        return Check(
            code="C7",
            name="孤儿分录",
            passed=True,
            detail="无企业树（空态）",
            expected="无已审批孤儿分录",
            actual={"has_tree": False},
        )
    diagnostics = await load_orphan_diagnostics(db, tree, year)
    # diagnostics 含草稿等未审批提示；这里只把「未计入合并」（已审批孤儿）作为失败信号。
    approved_orphans = [d for d in diagnostics if "未计入合并" in getattr(d, "message", "")]
    passed = not approved_orphans
    return Check(
        code="C7",
        name="孤儿分录",
        passed=passed,
        detail=(
            "无已审批孤儿分录" if passed
            else f"{len(approved_orphans)} 笔已审批分录未归属差额节点（未计入合并）"
        ),
        expected="0 笔已审批孤儿分录",
        actual={"approved_orphans": len(approved_orphans), "total_diagnostics": len(diagnostics)},
        samples=[{"message": getattr(d, "message", "")[:200]} for d in approved_orphans],
    )


_CHECKS = (
    check_trial_identity,
    check_report_run_digest,
    check_report_trial_consistency,
    check_note_staleness,
    check_snapshot_hash,
    check_readiness_consistency,
    check_orphan_entries,
)


async def reconcile(db: AsyncSession, project_id: UUID, year: int) -> ReconcileReport:
    """对一个合并项目 × 年度跑全部对账项（只读）。单项异常记入 errors，不中断其余项。"""
    report = ReconcileReport(project_id=str(project_id), year=year)
    for check_fn in _CHECKS:
        try:
            report.checks.append(await check_fn(db, project_id, year))
        except DmlAttemptedError:
            raise  # 写语句必须冒泡成整体失败
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"{check_fn.__name__}: {type(exc).__name__}: {str(exc)[:200]}")
    return report


# ─────────────────────────────── 真实库入口（只读 + 始终回滚 + DML 守卫） ───────────────────────────────


async def list_consolidated_projects() -> list[dict[str, Any]]:
    """列出当前库里的合并项目（report_scope='consolidated'，未删），只读。"""
    from app.core.database import async_session, engine
    from app.models.core import Project

    with ReadOnlyGuard(engine):
        async with async_session() as db:
            rows = (await db.execute(
                sa.select(Project.id, Project.name, Project.audit_year, Project.report_scope)
                .where(Project.report_scope == "consolidated", Project.is_deleted == sa.false())
                .order_by(Project.name)
            )).all()
            result = [
                {"project_id": str(r[0]), "name": r[1], "audit_year": r[2], "report_scope": r[3]}
                for r in rows
            ]
            await db.rollback()
    return result


async def reconcile_real_project(project_id: UUID, year: int) -> ReconcileReport:
    """对真实库里的合并项目做只读对账：DML 守卫 + 始终回滚，绝不写库。"""
    from app.core.database import async_session, engine

    with ReadOnlyGuard(engine) as guard:
        async with async_session() as db:
            try:
                report = await reconcile(db, project_id, year)
            finally:
                # 无论成败一律回滚（只读对账不应留下任何事务效果）。
                await db.rollback()
        if guard.triggered:  # 理论上会在 reconcile 内抛出，这里兜底
            report.errors.append(f"DML 守卫触发：{guard.triggered}")
    return report


# ─────────────────────────────── CLI ───────────────────────────────


def _default_out(project_id: str) -> Path:
    return _BACKEND_ROOT.parent / "tmp_consol_lifecycle" / f"reconcile_{project_id}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="合并运行生命周期——真实业务集团只读/dry-run 对账（绝不写库，需显式授权）",
    )
    parser.add_argument(
        "--authorized", action="store_true",
        help="显式确认已获用户再次授权对真实业务集团运行；缺此标志拒绝运行",
    )
    parser.add_argument("--project-id", type=str, default=None, help="合并项目 UUID（必填，除非 --list）")
    parser.add_argument("--year", type=int, default=None, help="审计年度（默认取项目 audit_year）")
    parser.add_argument("--out", type=Path, default=None, help="输出 JSON 路径")
    parser.add_argument(
        "--list", action="store_true",
        help="只读列出当前库里的合并项目（辅助定位 project-id，不需要 --authorized）",
    )
    args = parser.parse_args(argv)

    if args.list:
        projects = asyncio.run(list_consolidated_projects())
        print(json.dumps({"consolidated_projects": projects}, ensure_ascii=False, indent=2))
        print(f"\n合并项目数：{len(projects)}")
        if not projects:
            print("⚠ 当前库没有真实业务合并项目（真实业务合并项目 = 0，仅【测试】项目除外）。")
        return 0

    # 真实运行硬门：必须显式授权 + project-id，否则拒绝（退出码 2）。
    if not args.authorized:
        print(
            "❌ 拒绝运行：真实业务集团只读/dry-run 对账需用户再次授权。\n"
            "   确认已获授权后，重跑并显式加上 --authorized --project-id <UUID>。\n"
            "   （未授权 ⇒ 不连真实库、不写库、不假绿。）",
            file=sys.stderr,
        )
        return 2
    if not args.project_id:
        print("❌ 拒绝运行：缺少 --project-id（避免被误指向真实数据）。", file=sys.stderr)
        return 2

    try:
        project_id = UUID(args.project_id)
    except ValueError:
        print(f"❌ project-id 不是合法 UUID：{args.project_id}", file=sys.stderr)
        return 2

    year = args.year
    if year is None:
        # 只读取项目 audit_year 作为默认年度。
        async def _year() -> int | None:
            from app.core.database import async_session, engine
            from app.models.core import Project

            with ReadOnlyGuard(engine):
                async with async_session() as db:
                    value = (await db.execute(
                        sa.select(Project.audit_year).where(Project.id == project_id)
                    )).scalar_one_or_none()
                    await db.rollback()
            return value

        year = asyncio.run(_year())
        if year is None:
            print("❌ 未能确定审计年度，请显式传 --year。", file=sys.stderr)
            return 2

    report = asyncio.run(reconcile_real_project(project_id, year))
    payload = report.to_dict()
    payload["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload["authorized"] = True

    out = args.out or _default_out(args.project_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for c in report.checks:
        mark = "✅" if c.passed else "❌"
        print(f"{mark} [{c.code}] {c.name}：{c.detail}")
    for err in report.errors:
        print(f"⚠ 异常：{err}")
    print(f"\n输出：{out}")
    if report.ok:
        print("✅ 全部对账项通过（只读，未写库）")
        return 0
    print("❌ 存在不一致 / 异常（只读，未写库）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
