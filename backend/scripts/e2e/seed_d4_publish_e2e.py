"""D4「发布到试算表」端到端隔离测试项目 seed（P0-3b · spec d4-dual-mode-formula-governance）。

目的：在一个**明确隔离的测试项目**上端到端验证"审定表 → 发布到试算表"链路，
      绝不触碰任何真实审计项目 / 真实金额。

幂等：全部 upsert（固定确定性 UUID / ON CONFLICT），反复跑不新增、不重复污染。

造什么（全部对齐真实契约，见脚本头部常量）：
  1. 隔离测试项目（固定 UUID，name/client 带明显测试标识；audit_year=2099 保证与真实项目年度不撞）。
  2. admin 用户为该项目 edit 成员（admin 系统角色已全局放行 authorize_wp_edit，此处仍写入以保对称/幂等）。
  3. 若干 trial_balance 行（standard_account_code = 测试收入类科目 6001/6051；year 对齐 2099）。
  4. wp_index(wp_code='D4-1') + working_paper（sheet 名含 D4-1）→ 拿到 wp_id 供发布端点。

用法（backend 目录，venv python）:
    ../.venv/Scripts/python.exe scripts/e2e/seed_d4_publish_e2e.py --dry-run   # 离线打印将造什么，不写库
    ../.venv/Scripts/python.exe scripts/e2e/seed_d4_publish_e2e.py             # 真跑（幂等）
    ../.venv/Scripts/python.exe scripts/e2e/seed_d4_publish_e2e.py --purge     # 清除本 seed 造的测试数据

执行后打印 project_id / wp_id / year / 科目清单 供 API/UI E2E 使用。
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
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

# ─── 确定性隔离常量（反复跑幂等 / 明确测试标识 / 不撞真实项目年度）─────────────
TEST_PROJECT_ID = uuid.UUID("d4e2e000-0000-4000-8000-00000000d401")
TEST_PROJECT_NAME = "E2E-D4发布测试项目_请勿动_2099"
TEST_CLIENT_NAME = "E2E测试客户（隔离·非真实）"
TEST_YEAR = 2099  # 明显测试年度，真实项目均为 2024/2025，绝不相撞
TEST_COMPANY_CODE = "E2E"
TEST_WP_CODE = "D4-1"
TEST_WP_NAME = "E2E应收账款审定表(D4-1)"
TEST_SHEET_NAME = "审定表D4-1"  # extract_determination_wp_code 正则 ([D-N]\d+-1)\b 能解出 D4-1
# 固定 wp_index / working_paper UUID → 幂等
TEST_WP_INDEX_ID = uuid.UUID("d4e2e000-0000-4000-8000-00000000d402")
TEST_WP_ID = uuid.UUID("d4e2e000-0000-4000-8000-00000000d403")

# 测试科目（收入类），unadjusted/audited 初值。account_code 须与发布 audit_rows 对齐。
TEST_ACCOUNTS = [
    # (standard_account_code, account_name, account_category, unadjusted, audited初值)
    ("6001", "主营业务收入(E2E)", "revenue", "1000000.00", "0.00"),
    ("6051", "其他业务收入(E2E)", "revenue", "200000.00", "0.00"),
]

# ─── D4-1 审定表 checklist_responses seed（使前端审定表渲染出可编辑审定行 + TB 对账行有值）──
#
# 前端 useD4Adjudication 契约（dynamicAdjudicationRows 新模型，prefix='D4-1'）：
#   D4-1-rows                    → JSON 行清单 [{rowId, label, source, accountCode}]
#   D4-1-{rowId}-{field}         → 该行各列值（currentUnadjusted/currentAje/currentRje/prior*）
#   D4-1-adj-tb-6001 / -6051     → TB 对账行影子值（trialBalanceRow computed 读此两键）
#
# 行归段规则（d4AccountScope）：accountCode 以 6051 开头 → 其他段；否则默认主营段。
# 主营小计 currentUnadjusted 汇入发布 audit_rows 的 6001，其他小计汇入 6051。
# 这里 AJE/RJE 全 0 → 审定数=未审数（确定性），发布后 TB 6001=1000000、6051=200000。
_SEED_MAIN_ROW_ID = "seedmain"
_SEED_OTHER_ROW_ID = "seedother"
_SEED_MAIN_UNADJ = "1000000"
_SEED_OTHER_UNADJ = "200000"

TEST_CHECKLIST_RESPONSES: list[tuple[str, str]] = [
    # (item_id, remark)
    (
        "D4-1-rows",
        json.dumps(
            [
                {"rowId": _SEED_MAIN_ROW_ID, "label": "主营业务收入(E2E)", "source": "manual", "accountCode": "6001"},
                {"rowId": _SEED_OTHER_ROW_ID, "label": "其他业务收入(E2E)", "source": "manual", "accountCode": "6051"},
            ],
            ensure_ascii=False,
        ),
    ),
    (f"D4-1-{_SEED_MAIN_ROW_ID}-currentUnadjusted", _SEED_MAIN_UNADJ),
    (f"D4-1-{_SEED_MAIN_ROW_ID}-currentAje", "0"),
    (f"D4-1-{_SEED_MAIN_ROW_ID}-currentRje", "0"),
    (f"D4-1-{_SEED_OTHER_ROW_ID}-currentUnadjusted", _SEED_OTHER_UNADJ),
    (f"D4-1-{_SEED_OTHER_ROW_ID}-currentAje", "0"),
    (f"D4-1-{_SEED_OTHER_ROW_ID}-currentRje", "0"),
    # TB 对账行影子值（使「试算平衡表数（6001+6051）」= 1,200,000，差异=0 核对一致）
    ("D4-1-adj-tb-6001", _SEED_MAIN_UNADJ),
    ("D4-1-adj-tb-6051", _SEED_OTHER_UNADJ),
]


def _print_plan() -> None:
    print("=" * 72)
    print("  [DRY-RUN] D4 发布 E2E 隔离 seed — 将造以下数据（不写库）")
    print("=" * 72)
    print(f"  项目 project_id : {TEST_PROJECT_ID}")
    print(f"       name       : {TEST_PROJECT_NAME}")
    print(f"       client     : {TEST_CLIENT_NAME}")
    print(f"       audit_year : {TEST_YEAR}  audit_period_end: {TEST_YEAR}-12-31")
    print(f"  成员            : admin → 该项目 edit（admin 系统角色本已全局放行）")
    print(f"  底稿 wp_index_id: {TEST_WP_INDEX_ID}  wp_code={TEST_WP_CODE} name={TEST_WP_NAME}")
    print(f"       wp_id      : {TEST_WP_ID}  sheet_name(发布用)={TEST_SHEET_NAME}")
    print(f"  trial_balance   : year={TEST_YEAR} company_code={TEST_COMPANY_CODE}")
    for code, name, cat, unadj, aud in TEST_ACCOUNTS:
        print(f"     - {code:<6} {name:<18} {cat:<8} unadjusted={unadj} audited(初值)={aud}")
    print("=" * 72)
    print("  说明：发布 audit_rows 的 account_code 须为 6001/6051 才能命中上述 TB 行。")


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

    out: dict = {}
    async with Session() as db:
        # ① admin 用户 id
        admin_id = (
            await db.execute(sa.text("SELECT id FROM users WHERE username='admin' AND is_deleted=false LIMIT 1"))
        ).scalar_one_or_none()
        if admin_id is None:
            raise RuntimeError("未找到 admin 用户；请先 seed 系统用户（create_admin.py）")
        out["admin_id"] = str(admin_id)

        # ② 隔离测试项目（upsert：ON CONFLICT(id) 更新关键字段，保幂等）
        await db.execute(
            sa.text(
                """
                INSERT INTO projects
                    (id, name, client_name, audit_period_start, audit_period_end,
                     audit_year, status, scenario, has_foreign_currency, consol_level,
                     consol_lock, version, is_large_soe, is_deleted, created_at, updated_at)
                VALUES
                    (:id, :name, :client, :ps, :pe,
                     :yr, 'execution', 'normal', false, 1,
                     false, 1, false, false, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    client_name = EXCLUDED.client_name,
                    audit_year = EXCLUDED.audit_year,
                    audit_period_end = EXCLUDED.audit_period_end,
                    consol_lock = false,
                    is_deleted = false
                """
            ),
            {
                "id": str(TEST_PROJECT_ID),
                "name": TEST_PROJECT_NAME,
                "client": TEST_CLIENT_NAME,
                "ps": date(TEST_YEAR, 1, 1),
                "pe": date(TEST_YEAR, 12, 31),
                "yr": TEST_YEAR,
            },
        )
        out["project_id"] = str(TEST_PROJECT_ID)

        # ③ admin 为该项目 edit 成员（幂等：唯一 partial idx(project_id,user_id) where is_deleted=false）
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
                sa.text(
                    """
                    INSERT INTO project_users
                        (id, project_id, user_id, role, permission_level, is_deleted, created_at, updated_at)
                    VALUES
                        (:id, :pid, :uid, 'manager', 'edit', false, NOW(), NOW())
                    """
                ),
                {"id": str(uuid.uuid4()), "pid": str(TEST_PROJECT_ID), "uid": str(admin_id)},
            )
        else:
            await db.execute(
                sa.text("UPDATE project_users SET permission_level='edit' WHERE id=:id"),
                {"id": str(exists_pu)},
            )

        # ④ trial_balance 行（幂等：唯一键 project_id/year/company_code/standard_account_code）
        acct_out = []
        for code, name, cat, unadj, aud in TEST_ACCOUNTS:
            await db.execute(
                sa.text(
                    """
                    INSERT INTO trial_balance
                        (id, project_id, year, company_code, standard_account_code, account_name,
                         account_category, unadjusted_amount, rje_adjustment, aje_adjustment,
                         audited_amount, currency_code, is_deleted, created_at, updated_at)
                    VALUES
                        (:id, :pid, :yr, :cc, :code, :name,
                         CAST(:cat AS account_category), :unadj, 0, 0,
                         :aud, 'CNY', false, NOW(), NOW())
                    ON CONFLICT (project_id, year, company_code, standard_account_code) DO UPDATE SET
                        account_name = EXCLUDED.account_name,
                        unadjusted_amount = EXCLUDED.unadjusted_amount,
                        audited_amount = EXCLUDED.audited_amount,
                        is_deleted = false
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "pid": str(TEST_PROJECT_ID),
                    "yr": TEST_YEAR,
                    "cc": TEST_COMPANY_CODE,
                    "code": code,
                    "name": name,
                    "cat": cat,
                    "unadj": unadj,
                    "aud": aud,
                },
            )
            acct_out.append({"account_code": code, "unadjusted": unadj, "audited_init": aud})
        out["accounts"] = acct_out

        # ⑤ wp_index(D4-1)（幂等：唯一 uq(project_id,wp_code)；固定 id 便于关联）
        await db.execute(
            sa.text(
                """
                INSERT INTO wp_index
                    (id, project_id, wp_code, wp_name, audit_cycle, status, is_deleted, created_at, updated_at)
                VALUES
                    (:id, :pid, :code, :name, 'D', 'not_started', false, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    wp_name = EXCLUDED.wp_name, is_deleted = false
                """
            ),
            {"id": str(TEST_WP_INDEX_ID), "pid": str(TEST_PROJECT_ID), "code": TEST_WP_CODE, "name": TEST_WP_NAME},
        )
        out["wp_index_id"] = str(TEST_WP_INDEX_ID)

        # ⑥ working_paper（幂等：固定 id；file_path 用占位空文件路径，发布链路不读盘）
        wp_file_path = str(
            Path("storage") / "projects" / str(TEST_PROJECT_ID) / "workpapers" / "D" / f"{TEST_WP_CODE}.xlsx"
        )
        await db.execute(
            sa.text(
                """
                INSERT INTO working_paper
                    (id, project_id, wp_index_id, file_path, source_type, status, review_status,
                     file_version, content_revision, prefill_stale, is_deleted, created_at, updated_at)
                VALUES
                    (:id, :pid, :widx, :fp, 'template', 'draft', 'not_submitted',
                     1, 0, false, false, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    file_path = EXCLUDED.file_path, is_deleted = false
                """
            ),
            {"id": str(TEST_WP_ID), "pid": str(TEST_PROJECT_ID), "widx": str(TEST_WP_INDEX_ID), "fp": wp_file_path},
        )
        out["wp_id"] = str(TEST_WP_ID)

        # ⑦ D4-1 审定表 checklist_responses（幂等：唯一 (wp_id,item_id)）——
        #    使前端审定表渲染出主营/其他可编辑审定行 + TB 对账行有值（否则渲染全空）。
        for item_id, remark in TEST_CHECKLIST_RESPONSES:
            await db.execute(
                sa.text(
                    """
                    INSERT INTO checklist_responses
                        (id, project_id, wp_id, item_id, conclusion, remark, content_version, created_at, updated_at)
                    VALUES
                        (:id, :pid, :wid, :iid, NULL, :rm, 1, NOW(), NOW())
                    ON CONFLICT (wp_id, item_id) DO UPDATE SET
                        remark = EXCLUDED.remark,
                        content_version = checklist_responses.content_version + 1,
                        updated_at = NOW()
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "pid": str(TEST_PROJECT_ID),
                    "wid": str(TEST_WP_ID),
                    "iid": item_id,
                    "rm": remark,
                },
            )
        out["checklist_items"] = len(TEST_CHECKLIST_RESPONSES)

        await db.commit()

    await engine.dispose()
    out["year"] = TEST_YEAR
    out["sheet_name"] = TEST_SHEET_NAME
    out["wp_code"] = TEST_WP_CODE
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
            ("tb_publish_ack", "project_id=:pid"),
            ("checklist_responses", "project_id=:pid"),
            ("working_paper", "project_id=:pid"),
            ("wp_index", "project_id=:pid"),
            ("trial_balance", "project_id=:pid"),
            ("project_users", "project_id=:pid"),
            ("projects", "id=:pid"),
        ]:
            r = await db.execute(sa.text(f"DELETE FROM {tbl} WHERE {where}"), {"pid": str(TEST_PROJECT_ID)})
            deleted[tbl] = r.rowcount
        await db.commit()
    await engine.dispose()
    return deleted


async def _check_tb() -> dict:
    """查当前隔离项目 trial_balance 6001/6051 的 audited_amount + tb_publish_ack 计数（发布前后取证）。"""
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings

    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    out: dict = {}
    async with Session() as db:
        rows = (
            await db.execute(
                sa.text(
                    "SELECT standard_account_code, audited_amount FROM trial_balance "
                    "WHERE project_id=:pid AND is_deleted=false "
                    "AND standard_account_code IN ('6001','6051') ORDER BY standard_account_code"
                ),
                {"pid": str(TEST_PROJECT_ID)},
            )
        ).all()
        out["tb"] = {r[0]: str(r[1]) for r in rows}
        ack = (
            await db.execute(
                sa.text("SELECT COUNT(*) FROM tb_publish_ack WHERE project_id=:pid"),
                {"pid": str(TEST_PROJECT_ID)},
            )
        ).scalar_one()
        out["tb_publish_ack_count"] = int(ack)
    await engine.dispose()
    return out


async def _reset_tb() -> dict:
    """把隔离项目 6001/6051 的 audited_amount 归零 + 清 tb_publish_ack（复位供重复实测）。"""
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings

    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    out: dict = {}
    async with Session() as db:
        r1 = await db.execute(
            sa.text(
                "UPDATE trial_balance SET audited_amount=0, updated_at=NOW() "
                "WHERE project_id=:pid AND standard_account_code IN ('6001','6051')"
            ),
            {"pid": str(TEST_PROJECT_ID)},
        )
        r2 = await db.execute(
            sa.text("DELETE FROM tb_publish_ack WHERE project_id=:pid"),
            {"pid": str(TEST_PROJECT_ID)},
        )
        await db.commit()
        out["tb_rows_reset"] = r1.rowcount
        out["tb_publish_ack_deleted"] = r2.rowcount
    await engine.dispose()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="D4 发布到试算表 E2E 隔离 seed")
    parser.add_argument("--dry-run", action="store_true", help="离线打印将造什么，不写库")
    parser.add_argument("--purge", action="store_true", help="清除本 seed 造的测试数据（含 tb_publish_ack / checklist_responses）")
    parser.add_argument("--check", action="store_true", help="查当前 TB 6001/6051 audited + ack 计数（发布前后取证）")
    parser.add_argument("--reset-tb", action="store_true", help="TB 6001/6051 audited 归零 + 清 ack（复位供重复实测）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    if args.dry_run:
        _print_plan()
        return 0

    if args.check:
        res = asyncio.run(_check_tb())
        print("[CHECK]", json.dumps(res, ensure_ascii=False))
        return 0

    if args.reset_tb:
        res = asyncio.run(_reset_tb())
        print("[RESET-TB]", json.dumps(res, ensure_ascii=False))
        return 0

    if args.purge:
        deleted = asyncio.run(_purge())
        print("[PURGE] 已清除测试数据:", json.dumps(deleted, ensure_ascii=False))
        return 0

    out = asyncio.run(_seed())
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print("  [OK] D4 发布 E2E 隔离 seed 完成")
        print("=" * 72)
        print(f"  project_id : {out['project_id']}")
        print(f"  wp_id      : {out['wp_id']}   (sheet_name={out['sheet_name']}  wp_code={out['wp_code']})")
        print(f"  year       : {out['year']}")
        print(f"  admin_id   : {out['admin_id']}")
        print("  科目清单   :")
        for a in out["accounts"]:
            print(f"     - {a['account_code']}  unadjusted={a['unadjusted']}  audited(初值)={a['audited_init']}")
        print("-" * 72)
        print("  API/UI E2E 提示：POST /api/workpapers/{wp_id}/audit-determination/publish-to-tb")
        print(f"    wp_id={out['wp_id']}  sheet_name={out['sheet_name']}")
        print("    audit_rows 用 account_code 6001/6051 + current_unadjusted/adj_amount/reclass_amount")
    return 0


if __name__ == "__main__":
    sys.exit(main())
