#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G4/G6 六条 lane 的 E2E 隔离 seed（spec: g4-g6-shared-workbook-three-entry-lanes · Task 16）。

用法：
  seed:    python backend/scripts/e2e/seed_g4_g6_publish_e2e.py seed
  purge:   python backend/scripts/e2e/seed_g4_g6_publish_e2e.py purge
  dry-run: python backend/scripts/e2e/seed_g4_g6_publish_e2e.py --dry-run

🔴 六条主表真库全零或仅空数组 ⇒ 本脚本种**最小非空载荷**（每条 1 行 + 必填字段），
    使验收脚本能区分「seed 后有数据」与「seed 前空载荷」。幂等（ON CONFLICT DO UPDATE）。
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
TEST_PROJECT_ID = uuid.UUID("e2e0b046-0046-4000-b000-000000000099")
TEST_PROJECT_NAME = "G4G6_E2E隔离_三条lane"
TEST_CLIENT_NAME = "GT_E2E_G4G6_LANES"
TEST_YEAR = 2025

# 六条 entry 的 fixture（两册各三条）
LANE_FIXTURES = [
    # ── G4 债权投资 ──────────────────────────────────────────
    {
        "code": "G4-main",
        "wp_code": "G4",
        "wp_name": "G4 债权投资",
        "wp_index_id": uuid.UUID("e2e0b046-0401-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0b046-0401-4000-b001-000000000099"),
        "template_path": "G/G4 债权投资.xlsx",
        "store_items": [
            # G4-2 明细表 → conclusion（conclusion_canonical_remark_mirror）
            ("G4-2-rows", "conclusion", json.dumps([{
                "id": "e2e-g4d-001",
                "seq": 1,
                "investProject": "E2E测试债权投资1",
                "section": "other_non_current",
            }], ensure_ascii=False)),
        ],
    },
    {
        "code": "G4-sppi",
        "wp_code": "G4",
        "wp_name": "G4 债权投资",
        "wp_index_id": uuid.UUID("e2e0b046-0401-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0b046-0401-4000-b001-000000000099"),
        "template_path": "G/G4 债权投资.xlsx",
        "store_items": [
            # G4-7 盘点表 → dual_write
            ("G4-7-items", "conclusion", json.dumps([{
                "id": "e2e-g4inv-001",
                "seq": 1,
                "securityName": "E2E测试债券",
                "faceValue": 100,
                "quantity": 10,
            }], ensure_ascii=False)),
        ],
    },
    {
        "code": "G4-ecl",
        "wp_code": "G4",
        "wp_name": "G4 债权投资",
        "wp_index_id": uuid.UUID("e2e0b046-0401-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0b046-0401-4000-b001-000000000099"),
        "template_path": "G/G4 债权投资.xlsx",
        "store_items": [
            # G4-9 ECL 转置表 → dual_write
            ("G4-9-rows", "conclusion", json.dumps([{
                "id": "e2e-g4ecl-inv1",
                "investName": "E2E投资1",
                "fields": {"internalPriceIndicator": "无显著变化", "rateOrTermChange": "无变化"},
            }], ensure_ascii=False)),
        ],
    },
    # ── G6 其他债权投资 ──────────────────────────────────────
    {
        "code": "G6-main",
        "wp_code": "G6",
        "wp_name": "G6 其他债权投资",
        "wp_index_id": uuid.UUID("e2e0b046-0601-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0b046-0601-4000-b001-000000000099"),
        "template_path": "G/G6 其他债权投资.xlsx",
        "store_items": [
            # G6-2 明细表 → dual_write（真库唯一有行的）
            ("G6-2-rows", "conclusion", json.dumps([{
                "id": "e2e-g6d-001",
                "seq": 1,
                "investProject": "E2E测试其他债权投资1",
            }], ensure_ascii=False)),
        ],
    },
    {
        "code": "G6-sppi",
        "wp_code": "G6",
        "wp_name": "G6 其他债权投资",
        "wp_index_id": uuid.UUID("e2e0b046-0601-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0b046-0601-4000-b001-000000000099"),
        "template_path": "G/G6 其他债权投资.xlsx",
        "store_items": [
            # G6-5 公允价值测试 → conclusion_only
            ("G6-5-fair-value-data", "conclusion", json.dumps([{
                "id": "e2e-g6fv-001",
                "seq": 1,
            }], ensure_ascii=False)),
        ],
    },
    {
        "code": "G6-ecl",
        "wp_code": "G6",
        "wp_name": "G6 其他债权投资",
        "wp_index_id": uuid.UUID("e2e0b046-0601-4000-b000-000000000099"),
        "wp_id": uuid.UUID("e2e0b046-0601-4000-b001-000000000099"),
        "template_path": "G/G6 其他债权投资.xlsx",
        "store_items": [
            # G6-11 ECL 转置表 → dual_write
            ("G6-11-rows", "conclusion", json.dumps([{
                "id": "e2e-g6ecl-inv1",
                "investName": "E2E投资1",
                "fields": {"internalPriceIndicator": "无显著变化"},
            }], ensure_ascii=False)),
        ],
    },
]

# 去重 wp_index/working_paper（G4 三条共享一个 wp，G6 三条共享一个 wp）
_SEEN_WP: set[str] = set()


def _print_plan() -> None:
    print("=" * 72)
    print("  [DRY-RUN] G4/G6 六条 lane E2E 隔离 seed — 将造以下数据")
    print("=" * 72)
    print(f"  项目: {TEST_PROJECT_NAME} ({TEST_PROJECT_ID})")
    print(f"  年度: {TEST_YEAR}")
    wp_seen: set[str] = set()
    for f in LANE_FIXTURES:
        if f["wp_code"] not in wp_seen:
            print(f"  底稿 {f['wp_code']}: wp_id={f['wp_id']}")
            wp_seen.add(f["wp_code"])
        for item_id, col, val in f["store_items"]:
            print(f"    [{f['code']}] store: {item_id} ({col}) = {val[:60]}...")
    print("=" * 72)


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
        wp_done: set[str] = set()
        for f in LANE_FIXTURES:
            wp_key = f"{f['wp_code']}:{f['wp_id']}"
            if wp_key not in wp_done:
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
                tpl_name = f["template_path"].split("/")[-1]
                wp_file_path = f"storage/projects/{TEST_PROJECT_ID}/workpapers/G/{tpl_name}"
                await db.execute(
                    sa.text("""
                        INSERT INTO working_paper
                            (id, project_id, wp_index_id, file_path, source_type, status, review_status,
                             file_version, content_revision, prefill_stale, is_deleted, created_at, updated_at)
                        VALUES
                            (:id, :pid, :wix, :fp, 'template', 'draft', 'not_submitted',
                             1, 0, false, false, NOW(), NOW())
                        ON CONFLICT (id) DO UPDATE SET file_path = EXCLUDED.file_path, is_deleted = false
                    """),
                    {
                        "id": str(f["wp_id"]), "pid": str(TEST_PROJECT_ID),
                        "wix": str(f["wp_index_id"]), "fp": wp_file_path,
                    },
                )
                wp_done.add(wp_key)

            # checklist_responses（store item）
            for item_id, col, val in f["store_items"]:
                cr_id = uuid.uuid5(TEST_PROJECT_ID, f"{f['wp_id']}:{item_id}")
                await db.execute(
                    sa.text("""
                        INSERT INTO checklist_responses
                            (id, project_id, wp_id, item_id, conclusion, remark, content_version, created_at, updated_at)
                        VALUES (:id, :pid, :wid, :iid, :conc, :rem, 1, NOW(), NOW())
                        ON CONFLICT (id) DO UPDATE SET
                            conclusion = COALESCE(EXCLUDED.conclusion, checklist_responses.conclusion),
                            remark = COALESCE(EXCLUDED.remark, checklist_responses.remark),
                            updated_at = NOW()
                    """),
                    {
                        "id": str(cr_id),
                        "pid": str(TEST_PROJECT_ID),
                        "wid": str(f["wp_id"]),
                        "iid": item_id,
                        "conc": val if col == "conclusion" else None,
                        "rem": val if col == "remark" else None,
                    },
                )
                out["fixtures"].append({"code": f["code"], "item_id": item_id, "col": col, "bytes": len(val)})

        await db.commit()
    await engine.dispose()
    return out


async def _purge() -> dict:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings

    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, poolclass=None)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        pid = str(TEST_PROJECT_ID)
        # 逆序删除（FK 安全）
        r1 = await db.execute(sa.text(
            "DELETE FROM checklist_responses WHERE wp_id IN (SELECT id FROM working_paper WHERE project_id=:pid)"
        ), {"pid": pid})
        r2 = await db.execute(sa.text("DELETE FROM working_paper WHERE project_id=:pid"), {"pid": pid})
        r3 = await db.execute(sa.text("DELETE FROM wp_index WHERE project_id=:pid"), {"pid": pid})
        r4 = await db.execute(sa.text("DELETE FROM project_users WHERE project_id=:pid"), {"pid": pid})
        r5 = await db.execute(sa.text("DELETE FROM projects WHERE id=:pid"), {"pid": pid})
        await db.commit()
    await engine.dispose()
    return {
        "checklist_responses": r1.rowcount,
        "working_paper": r2.rowcount,
        "wp_index": r3.rowcount,
        "project_users": r4.rowcount,
        "projects": r5.rowcount,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="G4/G6 六条 lane E2E seed")
    parser.add_argument("action", nargs="?", choices=["seed", "purge"], default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run or args.action is None:
        _print_plan()
        return 0
    if args.action == "seed":
        result = asyncio.run(_seed())
        print(f"[seed] done: {len(result['fixtures'])} store items seeded")
        for f in result["fixtures"]:
            print(f"  {f['code']}: {f['item_id']} ({f['col']}) {f['bytes']} B")
        return 0
    if args.action == "purge":
        result = asyncio.run(_purge())
        print(f"[purge] done: {result}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
