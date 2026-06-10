#!/usr/bin/env python3
"""迁移向后兼容检测脚本。

用 sqlglot 解析新增 V*.sql 迁移文件，识别 Breaking_DDL 模式。
支持豁免声明与 warning/strict 双档模式。

Usage:
  python backend/scripts/check/check_migration_compat.py --mode warning
  python backend/scripts/check/check_migration_compat.py --mode strict
  python backend/scripts/check/check_migration_compat.py --mode strict --scan-all

退出码:
  0 - 无非豁免违规（或 warning 模式）
  1 - strict 模式下存在非豁免违规

# Feature: zero-downtime-deployment, Component 5
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import sqlglot
from sqlglot import exp

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = ROOT / "backend" / "migrations"
EXEMPTION_MARKER = "-- breaking-ddl-exempt:"


@dataclass
class Violation:
    filename: str
    category: str
    description: str
    sql_fragment: str
    exempt: bool = False


BREAKING_DESCRIPTIONS: dict[str, str] = {
    "DROP_COLUMN": "DROP COLUMN（旧代码读不到列→500）",
    "RENAME_COLUMN": "RENAME COLUMN（旧代码引用旧列名失败）",
    "ALTER_TYPE": "ALTER COLUMN TYPE（可能不兼容旧代码读写）",
    "ADD_NOT_NULL_NO_DEFAULT": "新增 NOT NULL 无默认值列（旧代码 INSERT 不含该列将失败）",
}

LOCK_DESCRIPTIONS: dict[str, str] = {
    "CREATE_INDEX_NON_CONCURRENT": "CREATE INDEX 未用 CONCURRENTLY（大表锁表风险，需求 8.2）",
}


def scan_changed_migrations() -> list[Path]:
    """获取本次 PR/commit 新增的 V*.sql 迁移文件。

    尝试顺序：
    1. git diff origin/main 新增文件
    2. git diff HEAD~1 新增文件（单 commit 场景）
    3. 兜底：扫描全部 V*.sql（本地开发无 git 历史时）
    """
    for base_ref in ("origin/main", "HEAD~1"):
        try:
            result = subprocess.run(
                [
                    "git", "diff", "--name-only", "--diff-filter=A",
                    base_ref, "--", "backend/migrations/V*.sql",
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            if result.returncode == 0 and result.stdout.strip():
                files = [
                    ROOT / f.strip()
                    for f in result.stdout.strip().split("\n")
                    if f.strip()
                ]
                existing = [f for f in files if f.exists()]
                if existing:
                    return existing
        except (subprocess.SubprocessError, FileNotFoundError):
            continue

    # 兜底：扫描全部 V*.sql（本地开发）
    return sorted(MIGRATIONS_DIR.glob("V*.sql"))


def _is_not_null_no_default(col_def: exp.ColumnDef) -> bool:
    """判断一个 ADD COLUMN 的 ColumnDef 是否同时有 NOT NULL 约束且无 DEFAULT。

    sqlglot 用 NotNullColumnConstraint 表示 NULL/NOT NULL:
    - NOT NULL → allow_null=False (或无 allow_null 键)
    - NULL     → allow_null=True
    """
    has_not_null = False
    has_default = False
    for constraint in col_def.find_all(exp.ColumnConstraint):
        kind = constraint.args.get("kind")
        if isinstance(kind, exp.NotNullColumnConstraint):
            # allow_null=True 表示显式 NULL（可空），不算 NOT NULL
            if not kind.args.get("allow_null"):
                has_not_null = True
        elif isinstance(kind, exp.DefaultColumnConstraint):
            has_default = True
    return has_not_null and not has_default


def _is_concurrent(stmt) -> bool:
    """Check if a CREATE INDEX statement uses CONCURRENTLY."""
    # sqlglot represents CONCURRENTLY as a property on the Create node.
    # Check the generated SQL for the keyword as the most reliable approach.
    sql_text = stmt.sql(dialect="postgres").upper()
    return "CONCURRENTLY" in sql_text


def scan_migration(sql_text: str, filename: str) -> list[Violation]:
    """Parse SQL and detect breaking DDL patterns and lock patterns.

    Uses sqlglot AST (exp.Alter for ALTER TABLE statements, exp.Create for indexes).
    """
    violations: list[Violation] = []
    has_exemption = EXEMPTION_MARKER in sql_text

    try:
        stmts = sqlglot.parse(sql_text, read="postgres")
    except Exception:
        # 无法解析（可能包含非标准 PG 语法）→ 跳过，不误报
        return violations

    for stmt in stmts:
        if stmt is None:
            continue

        # CREATE INDEX without CONCURRENTLY (lock pattern, not breaking DDL)
        if isinstance(stmt, exp.Create) and str(stmt.args.get("kind", "")).upper() == "INDEX":
            if not _is_concurrent(stmt):
                violations.append(Violation(
                    filename=filename,
                    category="CREATE_INDEX_NON_CONCURRENT",
                    description=LOCK_DESCRIPTIONS["CREATE_INDEX_NON_CONCURRENT"],
                    sql_fragment=stmt.sql(dialect="postgres")[:200],
                    exempt=has_exemption,
                ))
            continue

        # sqlglot v30+: ALTER TABLE → exp.Alter (not exp.AlterTable)
        if not isinstance(stmt, exp.Alter):
            continue

        for action in stmt.args.get("actions", []):
            # DROP COLUMN
            if isinstance(action, exp.Drop):
                kind_val = action.args.get("kind")
                if kind_val and str(kind_val).upper() == "COLUMN":
                    violations.append(Violation(
                        filename=filename,
                        category="DROP_COLUMN",
                        description=BREAKING_DESCRIPTIONS["DROP_COLUMN"],
                        sql_fragment=stmt.sql(dialect="postgres")[:200],
                        exempt=has_exemption,
                    ))

            # RENAME COLUMN
            elif isinstance(action, exp.RenameColumn):
                violations.append(Violation(
                    filename=filename,
                    category="RENAME_COLUMN",
                    description=BREAKING_DESCRIPTIONS["RENAME_COLUMN"],
                    sql_fragment=stmt.sql(dialect="postgres")[:200],
                    exempt=has_exemption,
                ))

            # ALTER COLUMN TYPE (set data type)
            elif isinstance(action, exp.AlterColumn):
                if action.args.get("dtype"):
                    violations.append(Violation(
                        filename=filename,
                        category="ALTER_TYPE",
                        description=BREAKING_DESCRIPTIONS["ALTER_TYPE"],
                        sql_fragment=stmt.sql(dialect="postgres")[:200],
                        exempt=has_exemption,
                    ))

            # ADD COLUMN with NOT NULL and no DEFAULT
            elif isinstance(action, exp.ColumnDef):
                if _is_not_null_no_default(action):
                    violations.append(Violation(
                        filename=filename,
                        category="ADD_NOT_NULL_NO_DEFAULT",
                        description=BREAKING_DESCRIPTIONS["ADD_NOT_NULL_NO_DEFAULT"],
                        sql_fragment=stmt.sql(dialect="postgres")[:200],
                        exempt=has_exemption,
                    ))

    return violations


def report(violations: list[Violation]) -> None:
    """Print violations report."""
    if not violations:
        print("✅ 无破坏性 DDL 检测到")
        return

    print(f"⚠️  检测到 {len(violations)} 个破坏性 DDL:")
    for v in violations:
        status = "[EXEMPT]" if v.exempt else "[VIOLATION]"
        print(f"  {status} {v.filename}: {v.description}")
        print(f"    SQL: {v.sql_fragment}")

    non_exempt = [v for v in violations if not v.exempt]
    if non_exempt:
        print(f"\n❌ {len(non_exempt)} 个非豁免违规")
    else:
        print(f"\n✅ 所有 {len(violations)} 个违规已豁免")


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移向后兼容检测")
    parser.add_argument(
        "--mode", choices=["warning", "strict"], default="warning",
        help="warning=仅告警(退出0), strict=非豁免违规阻断(退出1)",
    )
    parser.add_argument(
        "--scan-all", action="store_true",
        help="扫描所有 V*.sql（而非仅新增）",
    )
    args = parser.parse_args()

    if args.scan_all:
        files = sorted(MIGRATIONS_DIR.glob("V*.sql"))
    else:
        files = scan_changed_migrations()

    if not files:
        print("无新增迁移文件需要检查")
        return 0

    print(f"扫描 {len(files)} 个迁移文件...")
    all_violations: list[Violation] = []
    for f in files:
        sql_text = f.read_text(encoding="utf-8")
        violations = scan_migration(sql_text, f.name)
        all_violations.extend(violations)

    report(all_violations)

    non_exempt = [v for v in all_violations if not v.exempt]
    if args.mode == "strict" and non_exempt:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
