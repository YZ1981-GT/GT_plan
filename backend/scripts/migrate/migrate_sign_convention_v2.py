"""存量数据符号约定迁移工具 — v1_net_debit_positive → v2_category_natural_positive。

Spec: ledger-sign-convention-unify（需求 7、11.3）。
设计：design.md 「组件 6 存量数据迁移脚本」。

把已入库的旧约定（借正贷负）四表数据转换为新约定（按科目类别存自然正数）：
- 范围：tb_balance / tb_aux_balance / tb_ledger / tb_aux_ledger（+ 可选重算 trial_balance），
  按 project + year（+ 可选 dataset）。
- 余额表：对 `sign_convention_version != v2`（或为空）的记录，按 direction_resolver 判方向，
  贷方类（负债/权益/收入）当前为旧约定净额则翻为自然正数、补 opening/closing_direction
  + *_direction_source、标 sign_convention_version=v2。借方类金额口径不变（仅补方向字段）。
- 序时账：仅回填 entry_direction + source（金额借贷本身明确，不翻符号），按"借贷分列哪边非零"
  判方向，两侧皆非零/皆空时按类别兜底。idempotent：仅回填 entry_direction IS NULL 的行。
- dry-run（需求 7.3）：只统计将变更行数 + 样例，不写库。
- 幂等（需求 7.5）：已 v2 的余额记录跳过、已有方向的分录跳过，不再翻转。
- 快照 + 回退（需求 7.8/7.9）：迁移前对受影响行做 to_jsonb 快照写入 `_sign_migration_backup`，
  `--rollback --batch-id <id>` 可整批恢复到迁移前状态。
- 无法判定跳过（需求 7.4/7.6）：空编码 / 同编码方向冲突的记录跳过，记入待人工复核清单。
- 审计留痕（需求 7.4）：写 app_audit_log（action=sign_convention_migrate，记录影响行数/时间/操作者）。
- negate 配置防御性扫描（需求 11.3，依赖 Task 5.2）：迁移时顺带扫描
  projects.wizard_state.custom_fetch_rules 的 transform=negate，发现则记入待复核清单
  （Task 5.2 盘点：存量数量=0，见 negate-config-inventory.md）。

PG 运维铁律：
- PG-only（窗口函数 / to_regclass / jsonb_populate_record）→ 启动即检测 dialect，非 PG 直接报错退出。
- 建快照表用 CREATE TABLE IF NOT EXISTS；操作前 to_regclass 探测表是否存在。
- 按 account_category 翻符号用 set-based UPDATE（account_code = ANY(:codes)）。

用法（Windows：python 非 python3）：
    # 预览（不写库）
    python backend/scripts/migrate/migrate_sign_convention_v2.py --project <uuid> --year 2025 --dry-run
    # 执行
    python backend/scripts/migrate/migrate_sign_convention_v2.py --project <uuid> --year 2025 --operator <uuid|name>
    # 仅某数据集
    python backend/scripts/migrate/migrate_sign_convention_v2.py --project <uuid> --year 2025 --dataset <uuid>
    # 回退
    python backend/scripts/migrate/migrate_sign_convention_v2.py --rollback --batch-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# 确保 backend 包可导入（本文件位于 backend/scripts/migrate/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import sqlalchemy as sa  # noqa: E402

import app.models  # noqa: E402,F401  注册全部 ORM metadata
from app.core.database import async_session  # noqa: E402
from app.services.ledger_import.direction_resolver import (  # noqa: E402
    resolve_account_direction,
)
from app.services.ledger_import.sign_convention_types import (  # noqa: E402
    CURRENT_SIGN_CONVENTION,
    LEGACY_SIGN_CONVENTION,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

V2 = CURRENT_SIGN_CONVENTION  # "v2_category_natural_positive"
V1 = LEGACY_SIGN_CONVENTION   # "v1_net_debit_positive"

# 余额表：存净额，需按方向翻符号 + 补 opening/closing 方向字段 + 标版本
BALANCE_TABLES = ["tb_balance", "tb_aux_balance"]
# 序时账：借贷分列，金额不翻，仅回填 entry_direction
LEDGER_TABLES = ["tb_ledger", "tb_aux_ledger"]
# 派生表：可选重算（从已迁移的 tb_balance 重新生成）
TRIAL_BALANCE_TABLE = "trial_balance"

BACKUP_TABLE = "_sign_migration_backup"

# 回退模式
RESTORE_BY_RECORD = "by_record"  # 按 record_id 删除并恢复（四表）
RESTORE_BY_SCOPE = "by_scope"    # 按 project+year 删除并恢复（trial_balance 全量重算）

AUDIT_ACTION = "sign_convention_migrate"


# ---------------------------------------------------------------------------
# 快照备份表 DDL（CREATE TABLE IF NOT EXISTS，PG-only）
# ---------------------------------------------------------------------------

_BACKUP_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL,
    project_id UUID NOT NULL,
    year INTEGER NOT NULL,
    dataset_id UUID,
    table_name VARCHAR(40) NOT NULL,
    record_id UUID,
    snapshot JSONB NOT NULL,
    restore_mode VARCHAR(20) NOT NULL DEFAULT '{RESTORE_BY_RECORD}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_BACKUP_INDEX_DDL = [
    f"CREATE INDEX IF NOT EXISTS idx_sign_backup_batch ON {BACKUP_TABLE} (batch_id);",
    f"CREATE INDEX IF NOT EXISTS idx_sign_backup_project_year "
    f"ON {BACKUP_TABLE} (project_id, year);",
]


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class TableChange:
    """单表迁移统计。"""

    table: str
    candidate_rows: int = 0      # 待迁移的 v1/空版本行数
    flipped_rows: int = 0        # 实际翻符号的贷方类行数（余额表）
    direction_filled_rows: int = 0  # 补方向字段的行数
    skipped_rows: int = 0        # 无法判定跳过的行数
    samples: list[dict] = field(default_factory=list)  # 样例（最多 20 条）


@dataclass
class ReviewItem:
    """待人工复核项（需求 7.6 / 11.3）。"""

    kind: str          # "undeterminable_account" | "direction_conflict" | "negate_config"
    table: str
    project_id: str
    year: Optional[int]
    account_code: str
    account_name: str
    reason: str
    detail: dict = field(default_factory=dict)


@dataclass
class MigrationReport:
    """迁移报告。"""

    batch_id: str
    project_id: str
    year: int
    dataset_id: Optional[str]
    dry_run: bool
    operator: str
    changes: list[TableChange] = field(default_factory=list)
    review_items: list[ReviewItem] = field(default_factory=list)
    negate_scan: dict = field(default_factory=dict)
    trial_balance_recalc: bool = False
    error: Optional[str] = None

    @property
    def total_candidate(self) -> int:
        return sum(c.candidate_rows for c in self.changes)

    @property
    def total_flipped(self) -> int:
        return sum(c.flipped_rows for c in self.changes)

    @property
    def total_skipped(self) -> int:
        return sum(c.skipped_rows for c in self.changes)

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "project_id": self.project_id,
            "year": self.year,
            "dataset_id": self.dataset_id,
            "dry_run": self.dry_run,
            "operator": self.operator,
            "changes": [asdict(c) for c in self.changes],
            "review_items": [asdict(r) for r in self.review_items],
            "negate_scan": self.negate_scan,
            "trial_balance_recalc": self.trial_balance_recalc,
            "error": self.error,
            "summary": {
                "total_candidate": self.total_candidate,
                "total_flipped": self.total_flipped,
                "total_skipped": self.total_skipped,
                "review_count": len(self.review_items),
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str)


# ---------------------------------------------------------------------------
# PG 方言守卫 + 表存在探测
# ---------------------------------------------------------------------------


def _require_postgres(session) -> None:
    """本迁移依赖 PG-only 特性（窗口函数 / to_regclass / jsonb_populate_record /
    to_jsonb），非 PostgreSQL 直接报错退出（PG 运维铁律：PG-only SQL 加方言检测）。"""
    bind = session.get_bind()
    dialect = bind.dialect.name if bind is not None else ""
    if dialect != "postgresql":
        raise RuntimeError(
            f"符号约定迁移仅支持 PostgreSQL（当前 dialect={dialect!r}）。"
            "请在生产 PG 环境运行。"
        )


async def _table_exists(session, table: str) -> bool:
    """to_regclass 探测表是否存在（操作前先查表，避免对不存在表操作）。"""
    exists = (
        await session.execute(
            sa.text("SELECT to_regclass(:t)"), {"t": f"public.{table}"}
        )
    ).scalar()
    return exists is not None


async def _ensure_backup_table(session) -> None:
    """建快照表（CREATE TABLE IF NOT EXISTS）+ 索引。"""
    await session.execute(sa.text(_BACKUP_TABLE_DDL))
    for ddl in _BACKUP_INDEX_DDL:
        await session.execute(sa.text(ddl))


def _dataset_clause(dataset_id: Optional[str], alias: str = "t") -> tuple[str, dict]:
    """构造可选 dataset 过滤子句。"""
    if dataset_id:
        return f" AND {alias}.dataset_id = :dataset_id", {"dataset_id": dataset_id}
    return "", {}


# ---------------------------------------------------------------------------
# 余额表迁移（tb_balance / tb_aux_balance）— 翻符号 + 补方向 + 标版本
# ---------------------------------------------------------------------------


async def _resolve_code_directions(
    session,
    table: str,
    project_id: str,
    year: int,
    dataset_id: Optional[str],
) -> tuple[dict[str, tuple[str, str]], list[ReviewItem], dict[str, int]]:
    """对候选行按科目聚合判方向。

    Returns:
        - code_dir: {account_code: (direction, source)}（可迁移的科目）
        - reviews: 无法判定（空编码）记入待复核
        - code_row_counts: {account_code: 候选行数}（用于统计翻符号行数）
    """
    ds_sql, ds_params = _dataset_clause(dataset_id)
    # 候选 = v1 或空版本（IS DISTINCT FROM v2，含 NULL），未删除
    sql = f"""
        SELECT account_code, MAX(account_name) AS name, COUNT(*) AS cnt
        FROM {table} t
        WHERE t.project_id = :pid AND t.year = :yr
          AND t.is_deleted = false
          AND t.sign_convention_version IS DISTINCT FROM :v2
          {ds_sql}
        GROUP BY account_code
    """  # noqa: S608  表名来自固定白名单常量
    params = {"pid": project_id, "yr": year, "v2": V2, **ds_params}
    rows = (await session.execute(sa.text(sql), params)).all()

    code_dir: dict[str, tuple[str, str]] = {}
    reviews: list[ReviewItem] = []
    code_row_counts: dict[str, int] = {}

    for account_code, name, cnt in rows:
        code = (account_code or "").strip()
        nm = (name or "").strip()
        if not code:
            # 空编码无法可靠判定（需求 7.6）→ 跳过 + 记待复核
            reviews.append(ReviewItem(
                kind="undeterminable_account",
                table=table,
                project_id=project_id,
                year=year,
                account_code=account_code or "",
                account_name=nm,
                reason="account_code 为空，无法判定类别/方向，跳过不翻转",
                detail={"row_count": int(cnt)},
            ))
            continue
        direction, source = resolve_account_direction(code, nm)
        code_dir[code] = (direction, source)
        code_row_counts[code] = int(cnt)

    return code_dir, reviews, code_row_counts


async def _migrate_balance_table(
    session,
    table: str,
    report: MigrationReport,
    *,
    dry_run: bool,
) -> TableChange:
    """迁移一张余额表。"""
    change = TableChange(table=table)
    if not await _table_exists(session, table):
        return change

    project_id = report.project_id
    year = report.year
    dataset_id = report.dataset_id

    code_dir, reviews, code_counts = await _resolve_code_directions(
        session, table, project_id, year, dataset_id
    )
    report.review_items.extend(reviews)

    # 候选总行数（含空编码跳过的）
    ds_sql, ds_params = _dataset_clause(dataset_id)
    cand_sql = f"""
        SELECT COUNT(*) FROM {table} t
        WHERE t.project_id = :pid AND t.year = :yr AND t.is_deleted = false
          AND t.sign_convention_version IS DISTINCT FROM :v2 {ds_sql}
    """  # noqa: S608
    params = {"pid": project_id, "yr": year, "v2": V2, **ds_params}
    change.candidate_rows = int(
        (await session.execute(sa.text(cand_sql), params)).scalar() or 0
    )

    credit_codes = [c for c, (d, _) in code_dir.items() if d == "credit"]
    debit_codes = [c for c, (d, _) in code_dir.items() if d == "debit"]
    change.flipped_rows = sum(code_counts.get(c, 0) for c in credit_codes)
    change.direction_filled_rows = sum(code_counts.get(c, 0) for c in code_dir)
    change.skipped_rows = sum(r.detail.get("row_count", 0) for r in reviews if r.table == table)

    # 样例（最多 20 条科目级）
    for code, (direction, source) in list(code_dir.items())[:20]:
        change.samples.append({
            "account_code": code,
            "direction": direction,
            "source": source,
            "action": "flip_to_positive" if direction == "credit" else "fill_direction_only",
            "rows": code_counts.get(code, 0),
        })

    if dry_run:
        return change

    # ── 执行写库 ──
    # 1. 快照（仅将被更新的科目行），写入 _sign_migration_backup（需求 7.8）
    all_codes = credit_codes + debit_codes
    if all_codes:
        await _snapshot_rows(
            session, table, report, codes=all_codes, restore_mode=RESTORE_BY_RECORD
        )

    # 2. 按方向分桶 set-based UPDATE（贷方类翻符号，借方类仅补方向）
    if credit_codes:
        await _update_balance_bucket(
            session, table, project_id, year, dataset_id,
            codes=credit_codes, direction="credit", flip=True, code_dir=code_dir,
        )
    if debit_codes:
        await _update_balance_bucket(
            session, table, project_id, year, dataset_id,
            codes=debit_codes, direction="debit", flip=False, code_dir=code_dir,
        )

    return change


async def _update_balance_bucket(
    session,
    table: str,
    project_id: str,
    year: int,
    dataset_id: Optional[str],
    *,
    codes: list[str],
    direction: str,
    flip: bool,
    code_dir: dict[str, tuple[str, str]],
) -> None:
    """对一组同方向科目执行 set-based UPDATE。

    source 可能因科目而异（名称推断 vs 低置信度），按 source 再细分桶，
    保证 *_direction_source 准确。
    """
    # 按 source 细分（同方向科目可能来源不同）
    by_source: dict[str, list[str]] = {}
    for code in codes:
        _, source = code_dir[code]
        by_source.setdefault(source, []).append(code)

    ds_sql, ds_params = _dataset_clause(dataset_id)
    flip_open = "-opening_balance" if flip else "opening_balance"
    flip_close = "-closing_balance" if flip else "closing_balance"

    for source, src_codes in by_source.items():
        sql = f"""
            UPDATE {table}
            SET opening_balance = CASE WHEN opening_balance IS NOT NULL
                    THEN {flip_open} ELSE NULL END,
                closing_balance = CASE WHEN closing_balance IS NOT NULL
                    THEN {flip_close} ELSE NULL END,
                opening_direction = :dir,
                closing_direction = :dir,
                opening_direction_source = :src,
                closing_direction_source = :src,
                sign_convention_version = :v2,
                updated_at = now()
            WHERE project_id = :pid AND year = :yr AND is_deleted = false
              AND sign_convention_version IS DISTINCT FROM :v2
              AND account_code = ANY(:codes) {ds_sql}
        """  # noqa: S608  表名固定白名单
        params = {
            "pid": project_id, "yr": year, "v2": V2,
            "dir": direction, "src": source, "codes": src_codes,
            **ds_params,
        }
        await session.execute(sa.text(sql), params)


# ---------------------------------------------------------------------------
# 序时账迁移（tb_ledger / tb_aux_ledger）— 仅回填 entry_direction（金额不翻）
# ---------------------------------------------------------------------------


async def _migrate_ledger_table(
    session,
    table: str,
    report: MigrationReport,
    *,
    dry_run: bool,
) -> TableChange:
    """迁移一张序时账表：仅回填 entry_direction + source，金额口径不变。

    幂等：仅处理 entry_direction IS NULL 的行。
    判定：借贷分列单边非零 → 该侧（split_columns）；两侧皆非零/皆空 → 按科目类别兜底。
    """
    change = TableChange(table=table)
    if not await _table_exists(session, table):
        return change

    project_id = report.project_id
    year = report.year
    dataset_id = report.dataset_id
    ds_sql, ds_params = _dataset_clause(dataset_id)
    base_params = {"pid": project_id, "yr": year, **ds_params}

    # 候选行 = entry_direction 为空且未删除
    cand_sql = f"""
        SELECT COUNT(*) FROM {table} t
        WHERE t.project_id = :pid AND t.year = :yr AND t.is_deleted = false
          AND t.entry_direction IS NULL {ds_sql}
    """  # noqa: S608
    change.candidate_rows = int(
        (await session.execute(sa.text(cand_sql), base_params)).scalar() or 0
    )
    change.direction_filled_rows = change.candidate_rows

    # 需要类别兜底的科目（两侧皆非零/皆空），按 code 判方向
    code_sql = f"""
        SELECT account_code, MAX(account_name) AS name, COUNT(*) AS cnt
        FROM {table} t
        WHERE t.project_id = :pid AND t.year = :yr AND t.is_deleted = false
          AND t.entry_direction IS NULL {ds_sql}
          AND NOT (
            (COALESCE(t.debit_amount, 0) <> 0 AND COALESCE(t.credit_amount, 0) = 0)
            OR (COALESCE(t.credit_amount, 0) <> 0 AND COALESCE(t.debit_amount, 0) = 0)
          )
        GROUP BY account_code
    """  # noqa: S608
    fallback_rows = (await session.execute(sa.text(code_sql), base_params)).all()

    fallback_credit: list[str] = []
    fallback_debit: list[str] = []
    for account_code, name, _cnt in fallback_rows:
        code = (account_code or "").strip()
        if not code:
            report.review_items.append(ReviewItem(
                kind="undeterminable_account",
                table=table,
                project_id=project_id,
                year=year,
                account_code=account_code or "",
                account_name=(name or "").strip(),
                reason="序时账分录借贷双零且 account_code 为空，无法判定方向，跳过",
                detail={"row_count": int(_cnt)},
            ))
            change.skipped_rows += int(_cnt)
            continue
        direction, _ = resolve_account_direction(code, (name or "").strip())
        (fallback_credit if direction == "credit" else fallback_debit).append(code)

    if dry_run:
        return change

    # 快照候选行（整 project+year 范围，需求 7.8）
    await _snapshot_ledger_rows(session, table, report)

    # Pass 1：借贷分列单边非零 → split_columns
    split_sql = f"""
        UPDATE {table}
        SET entry_direction = CASE
                WHEN COALESCE(debit_amount, 0) <> 0 AND COALESCE(credit_amount, 0) = 0 THEN 'debit'
                ELSE 'credit' END,
            entry_direction_source = 'split_columns',
            updated_at = now()
        WHERE project_id = :pid AND year = :yr AND is_deleted = false
          AND entry_direction IS NULL {ds_sql}
          AND (
            (COALESCE(debit_amount, 0) <> 0 AND COALESCE(credit_amount, 0) = 0)
            OR (COALESCE(credit_amount, 0) <> 0 AND COALESCE(debit_amount, 0) = 0)
          )
    """  # noqa: S608
    await session.execute(sa.text(split_sql), base_params)

    # Pass 2：类别兜底（两侧皆非零/皆空），按方向分桶
    for codes, direction in ((fallback_credit, "credit"), (fallback_debit, "debit")):
        if not codes:
            continue
        fb_sql = f"""
            UPDATE {table}
            SET entry_direction = :dir,
                entry_direction_source = 'account_category_inferred',
                updated_at = now()
            WHERE project_id = :pid AND year = :yr AND is_deleted = false
              AND entry_direction IS NULL AND account_code = ANY(:codes) {ds_sql}
        """  # noqa: S608
        await session.execute(
            sa.text(fb_sql), {**base_params, "dir": direction, "codes": codes}
        )

    return change


# ---------------------------------------------------------------------------
# 快照 + 回退（Task 6.2，需求 7.8/7.9）
# ---------------------------------------------------------------------------


async def _snapshot_rows(
    session,
    table: str,
    report: MigrationReport,
    *,
    codes: list[str],
    restore_mode: str,
) -> None:
    """对将被更新的余额行整行快照到 _sign_migration_backup（to_jsonb，PG-only）。"""
    ds_sql, ds_params = _dataset_clause(dataset_id=report.dataset_id)
    sql = f"""
        INSERT INTO {BACKUP_TABLE}
            (batch_id, project_id, year, dataset_id, table_name, record_id,
             snapshot, restore_mode)
        SELECT :batch_id, :pid, :yr, t.dataset_id, :table, t.id,
               to_jsonb(t.*), :mode
        FROM {table} t
        WHERE t.project_id = :pid AND t.year = :yr AND t.is_deleted = false
          AND t.sign_convention_version IS DISTINCT FROM :v2
          AND t.account_code = ANY(:codes) {ds_sql}
    """  # noqa: S608
    params = {
        "batch_id": report.batch_id, "pid": report.project_id, "yr": report.year,
        "table": table, "mode": restore_mode, "v2": V2, "codes": codes, **ds_params,
    }
    await session.execute(sa.text(sql), params)


async def _snapshot_ledger_rows(session, table: str, report: MigrationReport) -> None:
    """对序时账待回填行整行快照（entry_direction IS NULL 的行）。"""
    ds_sql, ds_params = _dataset_clause(dataset_id=report.dataset_id)
    sql = f"""
        INSERT INTO {BACKUP_TABLE}
            (batch_id, project_id, year, dataset_id, table_name, record_id,
             snapshot, restore_mode)
        SELECT :batch_id, :pid, :yr, t.dataset_id, :table, t.id,
               to_jsonb(t.*), :mode
        FROM {table} t
        WHERE t.project_id = :pid AND t.year = :yr AND t.is_deleted = false
          AND t.entry_direction IS NULL {ds_sql}
    """  # noqa: S608
    params = {
        "batch_id": report.batch_id, "pid": report.project_id, "yr": report.year,
        "table": table, "mode": RESTORE_BY_RECORD, "v2": V2, **ds_params,
    }
    await session.execute(sa.text(sql), params)


async def _snapshot_trial_balance(session, report: MigrationReport) -> None:
    """trial_balance 全量快照（按 project+year，回退时整范围恢复）。"""
    if not await _table_exists(session, TRIAL_BALANCE_TABLE):
        return
    sql = f"""
        INSERT INTO {BACKUP_TABLE}
            (batch_id, project_id, year, dataset_id, table_name, record_id,
             snapshot, restore_mode)
        SELECT :batch_id, :pid, :yr, NULL, :table, t.id, to_jsonb(t.*), :mode
        FROM {TRIAL_BALANCE_TABLE} t
        WHERE t.project_id = :pid AND t.year = :yr AND t.is_deleted = false
    """  # noqa: S608
    params = {
        "batch_id": report.batch_id, "pid": report.project_id, "yr": report.year,
        "table": TRIAL_BALANCE_TABLE, "mode": RESTORE_BY_SCOPE,
    }
    await session.execute(sa.text(sql), params)


async def rollback_batch(session, batch_id: str) -> dict[str, Any]:
    """从快照恢复整批迁移到迁移前状态（需求 7.9）。

    by_record 模式（四表）：用快照 JSONB 逐表覆盖回原 record_id 的行；
    by_scope 模式（trial_balance）：删除当前 project+year 范围行后从快照重建。
    """
    _require_postgres(session)
    if not await _table_exists(session, BACKUP_TABLE):
        raise RuntimeError(f"快照表 {BACKUP_TABLE} 不存在，无法回退。")

    # 该批涉及哪些表
    table_rows = (await session.execute(
        sa.text(
            f"SELECT DISTINCT table_name, restore_mode FROM {BACKUP_TABLE} "
            "WHERE batch_id = :b"
        ),
        {"b": batch_id},
    )).all()
    if not table_rows:
        raise RuntimeError(f"批次 {batch_id} 无快照记录，无法回退。")

    restored: dict[str, int] = {}

    for table_name, restore_mode in table_rows:
        cols = await _table_columns(session, table_name)
        col_list = ", ".join(cols)
        if restore_mode == RESTORE_BY_SCOPE:
            # 整范围删除后从快照重建（trial_balance）
            scope = (await session.execute(
                sa.text(
                    f"SELECT DISTINCT project_id, year FROM {BACKUP_TABLE} "
                    "WHERE batch_id = :b AND table_name = :t"
                ),
                {"b": batch_id, "t": table_name},
            )).all()
            for pid, yr in scope:
                await session.execute(
                    sa.text(
                        f"DELETE FROM {table_name} "  # noqa: S608
                        "WHERE project_id = :p AND year = :y"
                    ),
                    {"p": str(pid), "y": yr},
                )
            sql = f"""
                INSERT INTO {table_name} ({col_list})
                SELECT {col_list} FROM (
                    SELECT (jsonb_populate_record(NULL::{table_name}, snapshot)).*
                    FROM {BACKUP_TABLE}
                    WHERE batch_id = :b AND table_name = :t
                ) s
            """  # noqa: S608
            r = await session.execute(sa.text(sql), {"b": batch_id, "t": table_name})
            restored[table_name] = r.rowcount or 0
        else:
            # by_record：DELETE 当前行 + 从快照重插（保留原 id）
            await session.execute(
                sa.text(
                    f"DELETE FROM {table_name} t "  # noqa: S608
                    f"USING {BACKUP_TABLE} b "
                    "WHERE b.batch_id = :b AND b.table_name = :t AND t.id = b.record_id"
                ),
                {"b": batch_id, "t": table_name},
            )
            sql = f"""
                INSERT INTO {table_name} ({col_list})
                SELECT {col_list} FROM (
                    SELECT (jsonb_populate_record(NULL::{table_name}, snapshot)).*
                    FROM {BACKUP_TABLE}
                    WHERE batch_id = :b AND table_name = :t
                ) s
            """  # noqa: S608
            r = await session.execute(sa.text(sql), {"b": batch_id, "t": table_name})
            restored[table_name] = r.rowcount or 0

    await session.commit()
    return {"batch_id": batch_id, "restored": restored}


async def _table_columns(session, table: str) -> list[str]:
    """读取表真实列名（按 ordinal 顺序），用于快照恢复 INSERT。"""
    rows = (await session.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t "
            "ORDER BY ordinal_position"
        ),
        {"t": table},
    )).scalars().all()
    return list(rows)


# ---------------------------------------------------------------------------
# negate transform 配置防御性扫描（Task 6.4，需求 11.3，依赖 Task 5.2）
# ---------------------------------------------------------------------------


async def _scan_negate_configs(
    session,
    report: MigrationReport,
) -> dict:
    """轻量防御性扫描 projects.wizard_state.custom_fetch_rules 的 transform=negate。

    Task 5.2 盘点结论：存量 negate 配置数量 = 0（见 negate-config-inventory.md）。
    本扫描确认当前数据态；若发现 negate/abs 配置则记入待复核清单（不强行改配置）。
    仅扫描本次迁移涉及的 project（按 report.project_id）。
    """
    scan = {"projects_scanned": 0, "negate_count": 0, "abs_count": 0, "rules_total": 0}

    if not await _table_exists(session, "projects"):
        report.negate_scan = scan
        return scan

    row = (await session.execute(
        sa.text("SELECT wizard_state FROM projects WHERE id = :pid"),
        {"pid": report.project_id},
    )).first()
    if row is None:
        report.negate_scan = scan
        return scan

    scan["projects_scanned"] = 1
    wizard_state = row[0]
    if not isinstance(wizard_state, dict):
        report.negate_scan = scan
        return scan

    custom_fetch_rules = wizard_state.get("custom_fetch_rules")
    if not isinstance(custom_fetch_rules, dict):
        report.negate_scan = scan
        return scan

    for target_key, entry in custom_fetch_rules.items():
        rules = (entry or {}).get("rules") if isinstance(entry, dict) else None
        if not isinstance(rules, list):
            continue
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            scan["rules_total"] += 1
            transform = rule.get("transform")
            if transform == "negate":
                scan["negate_count"] += 1
                report.review_items.append(ReviewItem(
                    kind="negate_config",
                    table="projects.wizard_state.custom_fetch_rules",
                    project_id=report.project_id,
                    year=report.year,
                    account_code=str(rule.get("account_code") or rule.get("source") or ""),
                    account_name="",
                    reason="发现 transform=negate 配置，v2 约定下可能反向纠错，"
                           "请按 negate-config-inventory.md 口径人工复核（移除/反置/保留）",
                    detail={"target_key": target_key, "rule": rule},
                ))
            elif transform == "abs":
                scan["abs_count"] += 1

    report.negate_scan = scan
    return scan


# ---------------------------------------------------------------------------
# 审计留痕（Task 6.3，需求 7.4）
# ---------------------------------------------------------------------------


async def _write_audit_log(session, report: MigrationReport) -> None:
    """写 app_audit_log（action=sign_convention_migrate）。

    memory 铁律：审计写 app_audit_log 表（非被 Metabase 占用的 audit_log）。
    best-effort，失败不阻断主流程。
    """
    if not await _table_exists(session, "app_audit_log"):
        return
    details = {
        "batch_id": report.batch_id,
        "project_id": report.project_id,
        "year": report.year,
        "dataset_id": report.dataset_id,
        "from_version": V1,
        "to_version": V2,
        "total_candidate": report.total_candidate,
        "total_flipped": report.total_flipped,
        "total_skipped": report.total_skipped,
        "review_count": len(report.review_items),
        "negate_scan": report.negate_scan,
        "trial_balance_recalc": report.trial_balance_recalc,
        "changes": {c.table: {
            "candidate": c.candidate_rows,
            "flipped": c.flipped_rows,
            "direction_filled": c.direction_filled_rows,
            "skipped": c.skipped_rows,
        } for c in report.changes},
    }
    operator = report.operator
    try:
        user_uuid: Optional[str] = str(uuid.UUID(str(operator)))
    except (ValueError, AttributeError, TypeError):
        user_uuid = None
        details["operator_label"] = operator

    await session.execute(
        sa.text(
            "INSERT INTO app_audit_log "
            "(id, user_id, action, resource_type, resource_id, details, created_at) "
            "VALUES (gen_random_uuid(), :uid, :action, :rtype, :rid, CAST(:details AS JSONB), now())"
        ),
        {
            "uid": user_uuid,
            "action": AUDIT_ACTION,
            "rtype": "ledger_sign_convention",
            "rid": report.project_id,
            "details": json.dumps(details, ensure_ascii=False, default=str),
        },
    )


# ---------------------------------------------------------------------------
# 迁移编排
# ---------------------------------------------------------------------------


async def migrate(
    *,
    project_id: str,
    year: int,
    dataset_id: Optional[str] = None,
    dry_run: bool = True,
    operator: str = "system",
    recalc_trial_balance: bool = False,
) -> MigrationReport:
    """执行符号约定迁移（按 project+year，可选 dataset）。

    步骤：
    1. 方言守卫 + 建快照表。
    2. 余额表（tb_balance / tb_aux_balance）：翻贷方类符号 + 补方向 + 标 v2。
    3. 序时账（tb_ledger / tb_aux_ledger）：回填 entry_direction。
    4. negate 配置防御性扫描（需求 11.3）。
    5. 可选：重算 trial_balance（从已迁移的 tb_balance 重新生成）。
    6. 审计留痕 + commit（dry-run 不写库不留痕）。
    """
    batch_id = str(uuid.uuid4())
    report = MigrationReport(
        batch_id=batch_id,
        project_id=project_id,
        year=year,
        dataset_id=dataset_id,
        dry_run=dry_run,
        operator=operator,
    )

    async with async_session() as session:
        _require_postgres(session)

        if not dry_run:
            await _ensure_backup_table(session)

        try:
            # 余额表
            for table in BALANCE_TABLES:
                report.changes.append(
                    await _migrate_balance_table(session, table, report, dry_run=dry_run)
                )
            # 序时账
            for table in LEDGER_TABLES:
                report.changes.append(
                    await _migrate_ledger_table(session, table, report, dry_run=dry_run)
                )
            # negate 配置扫描（需求 11.3）
            await _scan_negate_configs(session, report)

            # 可选重算 trial_balance
            if recalc_trial_balance and not dry_run:
                await _snapshot_trial_balance(session, report)
                await session.flush()
                from app.services.trial_balance_service import TrialBalanceService
                # company_code 可能多值；按受影响 company 逐一重算
                companies = (await session.execute(
                    sa.text(
                        "SELECT DISTINCT company_code FROM tb_balance "
                        "WHERE project_id = :p AND year = :y AND is_deleted = false"
                    ),
                    {"p": project_id, "y": year},
                )).scalars().all()
                svc = TrialBalanceService(session)
                for cc in companies:
                    await svc.full_recalc(uuid.UUID(project_id), year, cc)
                report.trial_balance_recalc = True

            if not dry_run:
                await _write_audit_log(session, report)
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            report.error = f"{type(exc).__name__}: {exc}"
            raise

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def _run_rollback(batch_id: str) -> dict[str, Any]:
    async with async_session() as session:
        return await rollback_batch(session, batch_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="存量数据符号约定迁移 v1→v2（按 project+year，dry-run/幂等/快照回退）",
    )
    parser.add_argument("--project", help="项目 ID（UUID）")
    parser.add_argument("--year", type=int, help="会计年度")
    parser.add_argument("--dataset", default=None, help="仅迁移指定数据集（UUID，可选）")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只统计将变更行数 + 样例，不写库（需求 7.3）",
    )
    parser.add_argument("--operator", default="system", help="操作者（UUID 或名称，审计留痕）")
    parser.add_argument(
        "--recalc-trial-balance", action="store_true",
        help="迁移后重算 trial_balance（从已迁移 tb_balance 重新生成）",
    )
    parser.add_argument(
        "--rollback", action="store_true",
        help="回退模式：从快照恢复到迁移前状态（需配合 --batch-id）",
    )
    parser.add_argument("--batch-id", default=None, help="回退用：迁移批次 ID")
    parser.add_argument("--json-out", default=None, help="将报告 JSON 写入指定文件路径")
    args = parser.parse_args()

    if args.rollback:
        if not args.batch_id:
            parser.error("--rollback 需配合 --batch-id <uuid>")
        result = asyncio.run(_run_rollback(args.batch_id))
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return

    if not args.project or args.year is None:
        parser.error("迁移需提供 --project <uuid> 和 --year <int>")

    report = asyncio.run(migrate(
        project_id=args.project,
        year=args.year,
        dataset_id=args.dataset,
        dry_run=args.dry_run,
        operator=args.operator,
        recalc_trial_balance=args.recalc_trial_balance,
    ))

    out = report.to_json()
    print(out)
    if args.json_out:
        Path(args.json_out).write_text(out, encoding="utf-8")
        print(f"\n报告已写入: {args.json_out}")

    # 控制台摘要
    mode = "DRY-RUN（未写库）" if args.dry_run else "已执行"
    print(f"\n=== 符号约定迁移 [{mode}] ===")
    print(f"批次: {report.batch_id}")
    print(f"候选行: {report.total_candidate} / 翻符号行: {report.total_flipped} "
          f"/ 跳过: {report.total_skipped}")
    print(f"待复核项: {len(report.review_items)}（含 negate 配置 "
          f"{report.negate_scan.get('negate_count', 0)} 条）")
    if not args.dry_run:
        print(f"回退命令: python {Path(__file__).name} --rollback --batch-id {report.batch_id}")


__all__ = [
    "migrate",
    "rollback_batch",
    "MigrationReport",
    "TableChange",
    "ReviewItem",
    "V1",
    "V2",
]


if __name__ == "__main__":
    main()
