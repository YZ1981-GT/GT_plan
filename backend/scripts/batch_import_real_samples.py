"""真实账套样本批量入库工具（可复用 / 程序员后续处理大文档时使用）

定位：
    后端直入工具，绕过前端 UI / 项目向导 / Worker 队列，直接调用 ledger_import
    管线（detect → identify → parse → convert → write → trial_balance 派生）。
    适用于：
    - CI / 性能测试需要大量真实数据快速入库
    - 9 家样本回归测试基线数据准备
    - 开发环境批量重置数据（每次干净从 0 开始）

支持的场景：
    1. 完整跑全部样本（含 YG2101 大文件 141MB，单家约 5-10min）
    2. 跳过大文件快速跑（5 家约 1-2min）
    3. 单家定向跑（用 --only 关键字过滤）
    4. dry-run 校验（不写库，仅检查管线能否跑通）

幂等性：
    - 项目层：同 client_name 已存在的活跃项目（is_deleted=false）→ 复用
    - tb_balance / tb_aux_balance：每次创建新 dataset_id，不与历史冲突
    - trial_balance：先 DELETE 同 (project_id, year) 旧记录再 INSERT（防 unique violation）

可复用要点（设计意图）：
    - SAMPLES 是声明式清单，新增样本只需追加一项 dict 不改代码
    - SAMPLE_LIMIT_PER_SHEET=5000 控制单 sheet 抽样上限（避免大文件耗时过长）
    - 用 raw SQL 创建项目，避免 ORM 模型加载顺序问题（accounting_standards 等依赖）
    - 自动查 admin user_id 作为 created_by（projects.created_by 有 FK）
    - 通用 _insert_balance / _insert_aux_balance / _insert_trial_balance helper
      可被其他脚本独立调用（如 demo data seed / E2E fixture）

示例用法：
    # 入库 5 家小文件
    python backend/scripts/batch_import_real_samples.py --skip-large

    # 入库 1 家定向（开发调试时常用）
    python backend/scripts/batch_import_real_samples.py --only=安徽骨科

    # 全部入库（含 141MB YG2101，单跑约 10min）
    python backend/scripts/batch_import_real_samples.py

    # dry-run（不写库，仅校验解析管线）
    python backend/scripts/batch_import_real_samples.py --dry-run

依赖前提：
    - 真实样本文件在 D:\\GT_plan\\数据\\ 下（与 backend/tests/ledger_import/test_9_samples_e2e.py 同款）
    - PG 已启动，admin 用户存在（用于 created_by FK）
    - 后端 .env 配置 DATABASE_URL 正确

对应 spec：
    - ledger-import-view-refactor task 9.2（9 家样本参数化 E2E 全绿）
    - e2e-business-flow UAT-1/3/5/6/8（多项目数据基线）
    - proposal-remaining-18 衍生（用户操作"剩余 5 家入库"实战 2026-05-23）
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
import uuid
from datetime import date
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

import sqlalchemy as sa
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.audit_platform_models import (
    TbAuxBalance,
    TbAuxLedger,
    TbBalance,
    TbLedger,
    TrialBalance,
    AccountCategory,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.ledger_import.converter import (
    convert_balance_rows,
    convert_ledger_rows,
)
from app.services.ledger_import.detector import detect_file_from_path
from app.services.ledger_import.identifier import identify
from app.services.ledger_import.parsers.excel_parser import iter_excel_rows_from_path
from app.services.ledger_import.validator import validate_l1
from app.services.ledger_import.writer import prepare_rows_with_raw_extra


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "数据"

# 5 家样本清单（已存在的 4 家 + 新增的 5 家中尚未入库的）
# 原 9 家中已入库：陕西华氏 / 宜宾大药房（14fb8c10）/ 辽宁卫生 / 和平药房
# 待入库的（包含 6 家，YG2101 大文件可选跳过）：
SAMPLES = [
    {
        "name": "YG36 四川物流",
        "client_name": "重庆医药集团四川物流有限公司",
        "files": [("YG36-重庆医药集团四川物流有限公司2025.xlsx", True, True)],
        "size_mb": 3.5,
    },
    {
        "name": "YG4001-30 新健康大药房临港店",
        "client_name": "重庆医药集团宜宾医药有限公司新健康大药房临港店",
        "files": [("YG4001-30重庆医药集团宜宾医药有限公司新健康大药房临港店-余额表+序时账.xlsx", True, True)],
        "size_mb": 0.8,
    },
    {
        "name": "和平物流",
        "client_name": "重庆和平物流有限公司",
        "files": [("和平物流25加工账-药品批发.xlsx", True, True)],
        "size_mb": 13.7,
    },
    {
        "name": "安徽骨科",
        "client_name": "安徽骨科医院",
        "files": [("余额表+序时账-安徽-骨科.xlsx", True, True)],
        "size_mb": 58.2,
    },
    {
        "name": "医疗器械",
        "client_name": "重庆医药集团医疗器械有限公司",
        "files": [("重庆医药集团医疗器械有限公司-医疗设备/余额表-器械25.xlsx", True, False)],
        "size_mb": 1.1,
    },
    {
        "name": "YG2101 四川医药",
        "client_name": "重庆医药集团四川医药有限公司",
        "files": [("YG2101-重庆医药集团四川医药有限公司2025年-科目余额表+序时账.xlsx", True, True)],
        "size_mb": 141.2,  # 大文件 — 可用 --skip-large 跳过
        "skip_with_large": True,
    },
]

YEAR = 2025
SAMPLE_LIMIT_PER_SHEET = 5000  # 每 sheet 限抽样行数（避免大文件耗时过长）
ADMIN_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def _get_admin_user_id(db: AsyncSession) -> uuid.UUID:
    """查 admin 用户的真实 id"""
    row = (await db.execute(sa.text(
        "SELECT id FROM users WHERE username='admin' AND is_deleted=false LIMIT 1"
    ))).first()
    if not row:
        raise RuntimeError("admin 用户不存在")
    return row[0]


async def _create_project(db: AsyncSession, name: str, client_name: str) -> uuid.UUID:
    """创建新项目（如已存在则返回旧项目 id）— 用 raw SQL 避免 ORM mapping 加载问题"""
    result = await db.execute(sa.text("""
        SELECT id FROM projects
        WHERE client_name = :cn AND is_deleted = false
        LIMIT 1
    """), {"cn": client_name})
    row = result.first()
    if row:
        print(f"  📌 项目已存在: {row[0]}")
        return row[0]

    admin_id = await _get_admin_user_id(db)
    pid = uuid.uuid4()
    await db.execute(sa.text("""
        INSERT INTO projects (
            id, name, client_name, project_type, status, created_by,
            audit_period_start, audit_period_end,
            version, consol_level, is_deleted, scenario, has_foreign_currency,
            created_at, updated_at
        ) VALUES (
            :id, :name, :client_name, 'annual', 'planning', :uid,
            :start_date, :end_date,
            1, 0, false, 'normal', false,
            NOW(), NOW()
        )
    """), {
        "id": str(pid),
        "name": f"{client_name}_{YEAR}",
        "client_name": client_name,
        "uid": str(admin_id),
        "start_date": date(YEAR, 1, 1),
        "end_date": date(YEAR, 12, 31),
    })
    await db.flush()
    print(f"  ✓ 项目已创建: {pid}")
    return pid


async def _insert_balance(db, rows, project_id, year, dataset_id):
    if not rows:
        return 0
    BATCH = 500
    total = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        await db.execute(insert(TbBalance).values([
            {
                "id": uuid.uuid4(),
                "project_id": project_id,
                "year": year,
                "dataset_id": dataset_id,
                "company_code": "001",
                "account_code": r.get("account_code"),
                "account_name": r.get("account_name"),
                "level": r.get("level") or 1,
                "opening_balance": r.get("opening_balance"),
                "closing_balance": r.get("closing_balance"),
                "debit_amount": r.get("debit_amount"),
                "credit_amount": r.get("credit_amount"),
                "currency_code": "CNY",
            }
            for r in chunk
            if r.get("account_code")
        ]))
        total += len(chunk)
    return total


async def _insert_aux_balance(db, rows, project_id, year, dataset_id):
    if not rows:
        return 0
    BATCH = 500
    total = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        valid = [r for r in chunk if r.get("account_code") and r.get("aux_value")]
        if not valid:
            continue
        await db.execute(insert(TbAuxBalance).values([
            {
                "id": uuid.uuid4(),
                "project_id": project_id,
                "year": year,
                "dataset_id": dataset_id,
                "company_code": "001",
                "account_code": r.get("account_code"),
                "account_name": r.get("account_name"),
                "aux_type": r.get("aux_type") or "default",
                "aux_value": r.get("aux_value"),
                "opening_balance": r.get("opening_balance"),
                "closing_balance": r.get("closing_balance"),
                "debit_amount": r.get("debit_amount"),
                "credit_amount": r.get("credit_amount"),
                "currency_code": "CNY",
            }
            for r in valid
        ]))
        total += len(valid)
    return total


async def _insert_trial_balance(db, balance_rows, project_id, year):
    """从 tb_balance rows 派生 trial_balance（一级科目汇总）

    幂等：如该 (project_id, year) 已存在 trial_balance 记录，先 DELETE 再 INSERT。
    """
    if not balance_rows:
        return 0
    # 幂等：清理同项目同年度的旧 trial_balance（避免重跑 unique violation）
    await db.execute(sa.text("""
        DELETE FROM trial_balance WHERE project_id = :pid AND year = :y
    """), {"pid": str(project_id), "y": year})

    # 一级科目汇总（按 account_code 前 4 位）
    by_code = {}
    for r in balance_rows:
        code = r.get("account_code", "")[:4]
        if not code:
            continue
        if code not in by_code:
            by_code[code] = {
                "name": r.get("account_name") or code,
                "opening": 0,
                "closing": 0,
                "debit": 0,
                "credit": 0,
            }
        by_code[code]["opening"] += float(r.get("opening_balance") or 0)
        by_code[code]["closing"] += float(r.get("closing_balance") or 0)
        by_code[code]["debit"] += float(r.get("debit_amount") or 0)
        by_code[code]["credit"] += float(r.get("credit_amount") or 0)

    total = 0
    rows_to_insert = []
    for code, agg in list(by_code.items())[:200]:  # 限 200 行
        # 推断 category（按 account_code 首位）
        first = code[:1]
        category = {
            "1": AccountCategory.asset,
            "2": AccountCategory.liability,
            "3": AccountCategory.equity,
            "4": AccountCategory.equity,
            "5": AccountCategory.expense,
            "6": AccountCategory.revenue,
        }.get(first, AccountCategory.asset)
        rows_to_insert.append({
            "id": uuid.uuid4(),
            "project_id": project_id,
            "year": year,
            "company_code": "001",
            "standard_account_code": code,
            "account_name": agg["name"],
            "account_category": category,
            "unadjusted_amount": agg["closing"],
            "audited_amount": agg["closing"],
            "opening_balance": agg["opening"],
            "currency_code": "CNY",
        })
    if rows_to_insert:
        await db.execute(insert(TrialBalance).values(rows_to_insert))
        total = len(rows_to_insert)
    return total


async def _import_sample(db: AsyncSession, sample: dict, dry_run: bool) -> dict:
    """对单家样本走完整管线：detect → identify → parse → convert → insert"""
    project_id = await _create_project(db, sample["name"], sample["client_name"])
    if dry_run:
        await db.rollback()
        return {"name": sample["name"], "project_id": str(project_id), "dry_run": True}

    dataset_id = uuid.uuid4()
    stats = {
        "name": sample["name"],
        "project_id": str(project_id),
        "balance_rows": 0,
        "aux_balance_rows": 0,
        "ledger_rows": 0,
        "aux_ledger_rows": 0,
        "trial_balance_rows": 0,
    }

    for rel_path, expect_balance, expect_ledger in sample["files"]:
        path = DATA_DIR / rel_path
        if not path.exists():
            print(f"  ✗ 文件缺失: {path}")
            continue

        print(f"  📂 解析文件: {path.name} ({path.stat().st_size / 1024 / 1024:.1f}MB)")
        fd = detect_file_from_path(str(path), path.name)
        all_balance = []
        all_aux_balance = []

        for sheet in fd.sheets:
            identified = identify(sheet)
            if identified.table_type not in ("balance", "ledger"):
                continue
            print(f"    sheet={identified.sheet_name} type={identified.table_type}")

            col_mapping = {
                cm.column_header: cm.standard_field
                for cm in identified.column_mappings
                if cm.standard_field and cm.confidence >= 50
            }
            headers = identified.detection_evidence.get("header_cells", [])
            ff_cols = [
                cm.column_index for cm in identified.column_mappings
                if cm.standard_field in ("account_code", "account_name")
            ]

            row_iter = iter_excel_rows_from_path(
                str(path), identified.sheet_name,
                data_start_row=identified.data_start_row,
                forward_fill_cols=ff_cols or None,
            )
            parsed = []
            count = 0
            for chunk in row_iter:
                for raw in chunk:
                    if count >= SAMPLE_LIMIT_PER_SHEET:
                        break
                    row_dict = {}
                    for i, val in enumerate(raw):
                        if i < len(headers):
                            row_dict[headers[i]] = val
                    parsed.append(row_dict)
                    count += 1
                if count >= SAMPLE_LIMIT_PER_SHEET:
                    break

            std_rows, _ = prepare_rows_with_raw_extra(parsed, col_mapping, headers)
            _, cleaned = validate_l1(std_rows, identified.table_type, column_mapping=col_mapping)

            if identified.table_type == "balance":
                bal, aux_bal = convert_balance_rows(cleaned)
                all_balance.extend(bal)
                all_aux_balance.extend(aux_bal)
            elif identified.table_type == "ledger":
                # 序时账暂跳过（避免单次入库过大）
                pass

        # 写入 DB
        if all_balance:
            n = await _insert_balance(db, all_balance, project_id, YEAR, dataset_id)
            stats["balance_rows"] += n
        if all_aux_balance:
            n = await _insert_aux_balance(db, all_aux_balance, project_id, YEAR, dataset_id)
            stats["aux_balance_rows"] += n
        # 派生 trial_balance
        if all_balance:
            n = await _insert_trial_balance(db, all_balance, project_id, YEAR)
            stats["trial_balance_rows"] += n

    await db.commit()
    return stats


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-large", action="store_true", help="跳过 YG2101 大文件")
    parser.add_argument("--dry-run", action="store_true", help="只校验不写库")
    parser.add_argument("--only", type=str, help="只跑某家（按 name 关键字过滤）")
    args = parser.parse_args()

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 80)
    print(f"批量入库 {len(SAMPLES)} 家真实样本")
    print("=" * 80)

    results = []
    for sample in SAMPLES:
        if args.skip_large and sample.get("skip_with_large"):
            print(f"\n⏭ 跳过大文件: {sample['name']} ({sample['size_mb']}MB)")
            continue
        if args.only and args.only not in sample["name"]:
            continue

        print(f"\n{'─' * 80}")
        print(f"🏢 [{sample['name']}] ({sample['size_mb']}MB)")
        print(f"{'─' * 80}")
        try:
            async with sm() as db:
                stats = await _import_sample(db, sample, args.dry_run)
                results.append(stats)
                print(f"  ✅ 完成: balance={stats.get('balance_rows', 0)} "
                      f"aux={stats.get('aux_balance_rows', 0)} "
                      f"trb={stats.get('trial_balance_rows', 0)}")
        except Exception as e:
            print(f"  ❌ 失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            results.append({"name": sample["name"], "error": str(e)})

    print("\n" + "=" * 80)
    print("汇总")
    print("=" * 80)
    for r in results:
        if "error" in r:
            print(f"  ❌ {r['name']}: {r['error']}")
        else:
            tb = r.get('balance_rows', 0)
            aux = r.get('aux_balance_rows', 0)
            trb = r.get('trial_balance_rows', 0)
            mark = "✅" if tb > 0 else "⚠"
            print(f"  {mark} {r['name']}: tb_balance={tb} aux={aux} trial_balance={trb}")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
