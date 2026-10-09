"""E1「货币资金」端到端隔离测试项目 seed。

spec: e1-sync-coverage-and-first-canary · Task 12
照搬 D4 的 seed_d4_publish_e2e.py 结构。

目的：在一个**明确隔离的测试项目**上端到端验证 E1 canary → 全盘 L2 链路。

🔴 E1 与 D4 seed 的差异：
  - E1 的 seed 必须额外解除 `missing_adapter`（D4 早已注册 adapter）
  - E1 需要 wp_code='E1'（D4 用 D4-1）
  - audit_year=2098（避免与 D4 的 2099 撞）

幂等：全部 upsert（固定确定性 UUID / ON CONFLICT），反复跑不新增。

造什么：
  1. 隔离测试项目（固定 UUID，name/client 带 E1 测试标识；audit_year=2098）。
  2. admin 用户为该项目 edit 成员。
  3. 若干 trial_balance 行（standard_account_code = 货币资金类 1001/1002；year=2098）。
  4. wp_index(wp_code='E1') + working_paper → 拿到 wp_id 供 E2E 使用。

用法（backend 目录，venv python）:
    ../.venv/Scripts/python.exe scripts/e2e/seed_e1_publish_e2e.py --dry-run
    ../.venv/Scripts/python.exe scripts/e2e/seed_e1_publish_e2e.py
    ../.venv/Scripts/python.exe scripts/e2e/seed_e1_publish_e2e.py --purge
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND))

_env_path = _BACKEND / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)

# ═══════════════════════════════════════════════════════════════════════════
# 固定确定性 UUID（幂等：ON CONFLICT DO NOTHING / DO UPDATE）
# ═══════════════════════════════════════════════════════════════════════════

#: 🔴 与 D4 的 seed UUID 不同（隔离）
E1_SEED_PROJECT_ID = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
E1_SEED_WP_ID = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567891")
E1_SEED_WP_INDEX_ID = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567892")
E1_SEED_ASSIGNMENT_ID = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567893")

AUDIT_YEAR = 2098
WP_CODE = "E1"
ENTRY_ID = "xlsx/gt-e1-monetary-fund"
PROJECT_NAME = "[E1-L2-E2E] 货币资金端到端测试项目"
CLIENT_NAME = "[E1-L2-E2E] 测试客户"

#: 货币资金类科目
TB_ACCOUNTS = [
    {"code": "1001", "name": "库存现金", "direction": "D"},
    {"code": "1002", "name": "银行存款", "direction": "D"},
    {"code": "1012", "name": "其他货币资金", "direction": "D"},
]


def _print_plan() -> None:
    """--dry-run：打印将造什么，不写库。"""
    print("═══ E1 E2E Seed Plan（dry-run）═══")
    print(f"  project_id : {E1_SEED_PROJECT_ID}")
    print(f"  project    : {PROJECT_NAME}")
    print(f"  client     : {CLIENT_NAME}")
    print(f"  audit_year : {AUDIT_YEAR}")
    print(f"  wp_code    : {WP_CODE}")
    print(f"  wp_id      : {E1_SEED_WP_ID}")
    print(f"  entry_id   : {ENTRY_ID}")
    print(f"  tb accounts: {[a['code'] for a in TB_ACCOUNTS]}")
    print()
    print("🔴 E1 seed 须额外解除 `missing_adapter`：")
    print("   1. working_paper_sync_entry_state 须有 E1 行")
    print("   2. adapter_id 须设为 e1.monetary_fund_detail")
    print("   （D4 的 seed 不需要这段——D4 早已注册 adapter）")
    print()
    print("用法：去掉 --dry-run 真跑")


async def _seed() -> dict:
    """真跑：幂等 upsert 测试项目 + TB + WP。"""
    from app.database import get_async_session_factory

    session_factory = get_async_session_factory()

    async with session_factory() as session:
        # 1. 隔离测试项目
        await session.execute(
            __import__("sqlalchemy").text("""
                INSERT INTO projects (id, name, client_name, audit_year, audit_period_end, status)
                VALUES (:id, :name, :client, :year, :period_end, 'active')
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """),
            {
                "id": str(E1_SEED_PROJECT_ID),
                "name": PROJECT_NAME,
                "client": CLIENT_NAME,
                "year": AUDIT_YEAR,
                "period_end": date(AUDIT_YEAR, 12, 31),
            },
        )

        # 2. admin 用户 → edit 成员
        admin_row = await session.execute(
            __import__("sqlalchemy").text(
                "SELECT id FROM users WHERE username = 'admin' LIMIT 1"
            )
        )
        admin = admin_row.scalar()
        if admin:
            await session.execute(
                __import__("sqlalchemy").text("""
                    INSERT INTO project_assignments (id, project_id, staff_id, role)
                    VALUES (:id, :pid, :uid, 'edit')
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": str(E1_SEED_ASSIGNMENT_ID),
                    "pid": str(E1_SEED_PROJECT_ID),
                    "uid": str(admin),
                },
            )

        # 3. trial_balance 行
        for i, acct in enumerate(TB_ACCOUNTS):
            tb_id = uuid.UUID(f"a1b2c3d4-e5f6-7890-abcd-ef12345678{90 + 10 + i:02x}")
            await session.execute(
                __import__("sqlalchemy").text("""
                    INSERT INTO trial_balance (id, project_id, standard_account_code, account_name,
                                               direction, unadjusted_amount, project_year)
                    VALUES (:id, :pid, :code, :name, :dir, 100000, :year)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": str(tb_id),
                    "pid": str(E1_SEED_PROJECT_ID),
                    "code": acct["code"],
                    "name": acct["name"],
                    "dir": acct["direction"],
                    "year": AUDIT_YEAR,
                },
            )

        # 4. wp_index + working_paper
        await session.execute(
            __import__("sqlalchemy").text("""
                INSERT INTO wp_index (id, wp_code, wp_name, cycle_code)
                VALUES (:id, :code, :name, 'E')
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(E1_SEED_WP_INDEX_ID),
                "code": WP_CODE,
                "name": "货币资金",
            },
        )
        await session.execute(
            __import__("sqlalchemy").text("""
                INSERT INTO working_paper (id, project_id, wp_index_id, status, title)
                VALUES (:id, :pid, :wpi, 'active', :title)
                ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title
            """),
            {
                "id": str(E1_SEED_WP_ID),
                "pid": str(E1_SEED_PROJECT_ID),
                "wpi": str(E1_SEED_WP_INDEX_ID),
                "title": "E1 货币资金（E2E 测试）",
            },
        )

        await session.commit()

    return {
        "project_id": str(E1_SEED_PROJECT_ID),
        "wp_id": str(E1_SEED_WP_ID),
        "audit_year": AUDIT_YEAR,
        "wp_code": WP_CODE,
        "entry_id": ENTRY_ID,
        "accounts": [a["code"] for a in TB_ACCOUNTS],
    }


async def _purge() -> dict:
    """清除本 seed 造的测试数据。"""
    from app.database import get_async_session_factory

    session_factory = get_async_session_factory()
    deleted = []

    async with session_factory() as session:
        for table, col in [
            ("working_paper", "id"),
            ("wp_index", "id"),
            ("project_assignments", "id"),
            ("trial_balance", "project_id"),
            ("projects", "id"),
        ]:
            if table == "trial_balance":
                val = str(E1_SEED_PROJECT_ID)
            elif table == "working_paper":
                val = str(E1_SEED_WP_ID)
            elif table == "wp_index":
                val = str(E1_SEED_WP_INDEX_ID)
            elif table == "project_assignments":
                val = str(E1_SEED_ASSIGNMENT_ID)
            else:
                val = str(E1_SEED_PROJECT_ID)
            r = await session.execute(
                __import__("sqlalchemy").text(
                    f"DELETE FROM {table} WHERE {col} = :val"
                ),
                {"val": val},
            )
            deleted.append(f"{table}: {r.rowcount}")
        await session.commit()

    return {"deleted": deleted}


def main() -> int:
    parser = argparse.ArgumentParser(description="E1 E2E seed")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划不写库")
    parser.add_argument("--purge", action="store_true", help="清除测试数据")
    args = parser.parse_args()

    if args.dry_run:
        _print_plan()
        return 0

    if args.purge:
        result = asyncio.run(_purge())
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    result = asyncio.run(_seed())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print()
    print("🔴 下一步：需要 umbrella BP-61-1 解除后，")
    print("   E1 adapter 注册成功才能跑 e1-l2-oo-to-html-all.spec.ts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
