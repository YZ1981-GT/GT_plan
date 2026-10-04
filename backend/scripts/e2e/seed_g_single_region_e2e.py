#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G 循环九条 single-region lane 的 E2E 隔离 seed。

spec: `g-cycle-single-region-detail-lanes` · Task 15

用法：
  seed:   python backend/scripts/e2e/seed_g_single_region_e2e.py seed
  purge:  python backend/scripts/e2e/seed_g_single_region_e2e.py purge
  dry-run: python backend/scripts/e2e/seed_g_single_region_e2e.py --dry-run

🔴 **只有 G9 不 seed**（真库 605 B 有真实载荷）；其余八条未 seed 时验收脚本显式失败。
🔴 **G1/G3 是「键不存在」（0 B / 0 wp）** ⇒ seed 须先建键。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

# ── 隔离测试常量 ──────────────────────────────────────────────────────────────
TEST_PROJECT_ID = uuid.UUID("e2e0a000-0000-4000-b000-000000000099")
TEST_PROJECT_NAME = "G循环E2E隔离_single_region"
TEST_CLIENT_NAME = "GT_E2E_G_SINGLE_REGION"
TEST_YEAR = 2025
TEST_COMPANY_CODE = "0001"

# 九条 entry 对应的 wp_index / working_paper 固定 id
LANE_FIXTURES = [
    {
        "code": "G1",
        "wp_code": "G1",
        "wp_name": "G1 交易性金融资产",
        "wp_index_id": uuid.UUID("e2e0a001-0001-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0a001-0001-4000-b001-000000000099"),
        "template_path": "G/G1 交易性金融资产.xlsx",
        "store_items": [
            ("G1-2-rows", "conclusion", "[]"),
        ],
    },
    {
        "code": "G3",
        "wp_code": "G3",
        "wp_name": "G3 应收股利",
        "wp_index_id": uuid.UUID("e2e0a003-0003-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0a003-0003-4000-b001-000000000099"),
        "template_path": "G/G3 应收股利.xlsx",
        "store_items": [
            ("G3-2-detail-rows", "conclusion", "[]"),
        ],
    },
    {
        "code": "G8",
        "wp_code": "G8",
        "wp_name": "G8 其他权益工具投资",
        "wp_index_id": uuid.UUID("e2e0a008-0008-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0a008-0008-4000-b001-000000000099"),
        "template_path": "G/G8 其他权益工具投资.xlsx",
        "store_items": [
            ("G8-detail-rows", "remark", "[]"),
        ],
    },
    {
        "code": "G10",
        "wp_code": "G10",
        "wp_name": "G10 交易性金融负债",
        "wp_index_id": uuid.UUID("e2e0a010-0010-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0a010-0010-4000-b001-000000000099"),
        "template_path": "G/G10 交易性金融负债.xlsx",
        "store_items": [
            ("G10-detail-rows", "remark", "[]"),
        ],
    },
    {
        "code": "G11",
        "wp_code": "G11",
        "wp_name": "G11 投资收益",
        "wp_index_id": uuid.UUID("e2e0a011-0011-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0a011-0011-4000-b001-000000000099"),
        "template_path": "G/G11 投资收益.xlsx",
        "store_items": [
            ("G11-detail-rows", "remark", "[]"),
        ],
    },
    {
        "code": "G12",
        "wp_code": "G12",
        "wp_name": "G12 净敞口套期收益",
        "wp_index_id": uuid.UUID("e2e0a012-0012-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0a012-0012-4000-b001-000000000099"),
        "template_path": "G/G12 净敞口套期收益.xlsx",
        "store_items": [
            ("G12-hedge-detail-rows", "remark", "[]"),
        ],
    },
    {
        "code": "G13",
        "wp_code": "G13",
        "wp_name": "G13 公允价值变动收益",
        "wp_index_id": uuid.UUID("e2e0a013-0013-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0a013-0013-4000-b001-000000000099"),
        "template_path": "G/G13 公允价值变动收益.xlsx",
        "store_items": [
            ("G13-detail-skeleton", "remark", "[]"),
        ],
    },
    {
        "code": "G14",
        "wp_code": "G14",
        "wp_name": "G14 信用减值损失",
        "wp_index_id": uuid.UUID("e2e0a014-0014-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0a014-0014-4000-b001-000000000099"),
        "template_path": "G/G14 信用减值损失.xlsx",
        "store_items": [
            ("G14-detail-rows", "remark", "[]"),
        ],
    },
]
# 🔴 G9 不在此列表中（真库已有 605 B 载荷）


def _print_plan() -> None:
    print("=" * 72)
    print("  [DRY-RUN] G single-region 发布 E2E 隔离 seed — 将造以下数据")
    print("=" * 72)
    print(f"  项目: {TEST_PROJECT_NAME} ({TEST_PROJECT_ID})")
    print(f"  年度: {TEST_YEAR}")
    for f in LANE_FIXTURES:
        print(f"  底稿 {f['code']}: wp_code={f['wp_code']} wp_id={f['wp_id']}")
        for item_id, col, val in f["store_items"]:
            print(f"    store: {item_id} ({col}) = {val[:50]}...")
    print("=" * 72)
    print("  🔴 G9 不在 seed 列表（真库已有 605 B 载荷）")


async def _seed() -> dict:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings

    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, poolclass=None)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    out: dict = {"fixtures": []}
    async with Session() as db:
        # ① admin 用户 id
        admin_id = (
            await db.execute(
                sa.text("SELECT id FROM users WHERE username='admin' AND is_deleted=false LIMIT 1")
            )
        ).scalar_one_or_none()
        if admin_id is None:
            raise RuntimeError("未找到 admin 用户")
        out["admin_id"] = str(admin_id)

        # ② 隔离测试项目
        await db.execute(
            sa.text("""
                INSERT INTO projects
                    (id, name, client_name, audit_period_start, audit_period_end,
                     audit_year, status, scenario, has_foreign_currency, consol_level,
                     consol_lock, version, is_large_soe, is_deleted, created_at, updated_at)
                VALUES
                    (:id, :name, :client, :ps, :pe,
                     :yr, 'execution', 'normal', false, 1,
                     false, 1, false, false, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name, client_name = EXCLUDED.client_name,
                    audit_year = EXCLUDED.audit_year, is_deleted = false
            """),
            {
                "id": str(TEST_PROJECT_ID), "name": TEST_PROJECT_NAME,
                "client": TEST_CLIENT_NAME,
                "ps": date(TEST_YEAR, 1, 1), "pe": date(TEST_YEAR, 12, 31),
                "yr": TEST_YEAR,
            },
        )

        # ③ admin 为该项目 edit 成员
        exists_pu = (
            await db.execute(
                sa.text(
                    "SELECT id FROM project_users WHERE project_id=:pid AND user_id=:uid AND is_deleted=false LIMIT 1"
                ),
                {"pid": str(TEST_PROJECT_ID), "uid": str(admin_id)},
            )
        ).scalar_one_or_none()
        if exists_pu is None:
            await db.execute(
                sa.text("""
                    INSERT INTO project_users
                        (id, project_id, user_id, role, permission_level, is_deleted, created_at, updated_at)
                    VALUES (:id, :pid, :uid, 'manager', 'edit', false, NOW(), NOW())
                """),
                {"id": str(uuid.uuid4()), "pid": str(TEST_PROJECT_ID), "uid": str(admin_id)},
            )

        # ④ 逐条 fixture 建 wp_index + working_paper + checklist_responses
        for f in LANE_FIXTURES:
            # wp_index
            await db.execute(
                sa.text("""
                    INSERT INTO wp_index
                        (id, project_id, wp_code, wp_name, audit_cycle, status, is_deleted, created_at, updated_at)
                    VALUES (:id, :pid, :code, :name, 'G', 'not_started', false, NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE SET wp_name = EXCLUDED.wp_name, is_deleted = false
                """),
                {
                    "id": str(f["wp_index_id"]), "pid": str(TEST_PROJECT_ID),
                    "code": f["wp_code"], "name": f["wp_name"],
                },
            )

            # working_paper
            wp_file_path = f"storage/projects/{TEST_PROJECT_ID}/workpapers/G/{f['template_path'].split('/')[-1]}"
            await db.execute(
                sa.text("""
                    INSERT INTO working_paper
                        (id, project_id, wp_index_id, file_path, source_type, status, review_status,
                         file_version, content_revision, prefill_stale, is_deleted, created_at, updated_at)
                    VALUES
                        (:id, :pid, :widx, :fp, 'template', 'draft', 'not_submitted',
                         1, 0, false, false, NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE SET file_path = EXCLUDED.file_path, is_deleted = false
                """),
                {
                    "id": str(f["wp_id"]), "pid": str(TEST_PROJECT_ID),
                    "widx": str(f["wp_index_id"]), "fp": wp_file_path,
                },
            )

            # checklist_responses（store items 建键）
            for item_id, col, val in f["store_items"]:
                payload = {"conclusion": val} if col == "conclusion" else {"remark": val}
                await db.execute(
                    sa.text("""
                        INSERT INTO checklist_responses
                            (id, project_id, wp_id, item_id, conclusion, remark, content_version, created_at, updated_at)
                        VALUES (:id, :pid, :wid, :iid, :conc, :rem, 1, NOW(), NOW())
                        ON CONFLICT (wp_id, item_id) DO UPDATE SET
                            conclusion = EXCLUDED.conclusion, remark = EXCLUDED.remark,
                            content_version = checklist_responses.content_version + 1, updated_at = NOW()
                    """),
                    {
                        "id": str(uuid.uuid4()), "pid": str(TEST_PROJECT_ID),
                        "wid": str(f["wp_id"]), "iid": item_id,
                        "conc": payload.get("conclusion"), "rem": payload.get("remark"),
                    },
                )

            out["fixtures"].append({
                "code": f["code"], "wp_id": str(f["wp_id"]),
                "items": [s[0] for s in f["store_items"]],
            })

        await db.commit()
    await engine.dispose()
    out["project_id"] = str(TEST_PROJECT_ID)
    return out


async def _purge() -> dict:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings

    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    deleted = {}
    async with Session() as db:
        for tbl, where in [
            ("checklist_responses", "project_id=:pid"),
            ("working_paper", "project_id=:pid"),
            ("wp_index", "project_id=:pid"),
            ("project_users", "project_id=:pid"),
            ("projects", "id=:pid"),
        ]:
            r = await db.execute(sa.text(f"DELETE FROM {tbl} WHERE {where}"), {"pid": str(TEST_PROJECT_ID)})
            deleted[tbl] = r.rowcount
        await db.commit()
    await engine.dispose()
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="seed", choices=["seed", "purge"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        _print_plan()
        return 0

    if args.action == "seed":
        result = asyncio.run(_seed())
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.action == "purge":
        result = asyncio.run(_purge())
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
