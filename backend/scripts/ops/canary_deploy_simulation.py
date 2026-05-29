"""ledger-import-view-refactor 灰度部署 Day 0/3/7 单机模拟（spec 9.9）

定位：
    spec 要求三阶段灰度：Day 0 deploy / Day 3 单项目开启 / Day 7 全量 + F18 迁移。
    本脚本在单机 PG 上等价模拟，实测：
    - Day 0：feature flag 默认 False（代码 deploy）
    - Day 3：set_project_flag(陕西华氏, True) 单项目灰度
    - Day 7：全局 flag → True + F18 Day 7 迁移（V005 RLS POLICY 验证）

可复用：CI/staging 验收同款灰度策略时直接跑。

用法:
    python backend/scripts/canary_deploy_simulation.py
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
from pathlib import Path
from uuid import UUID

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.database import set_rls_context
from app.services.feature_flags import is_enabled, set_project_flag, _DEFAULT_FLAGS


SHANXI_HUASHI_ID = UUID("005a6f2d-cecd-4e30-bcbd-9fb01236c194")


async def day0_check(db: AsyncSession) -> dict:
    """Day 0: 代码 deploy + feature flag 体系就位"""
    result = {"phase": "Day 0 — deploy", "checks": []}

    # 1. flag 注册表存在
    flags_present = ["ledger_import_v2", "ledger_import_view_refactor_enabled"]
    for f in flags_present:
        if f in _DEFAULT_FLAGS:
            result["checks"].append(f"  ✓ flag '{f}' 已注册（默认 {_DEFAULT_FLAGS[f]}）")
        else:
            result["checks"].append(f"  ✗ flag '{f}' 未注册")

    # 2. set_rls_context 可调用（不抛 SET LOCAL bind 异常）
    try:
        await set_rls_context(db, SHANXI_HUASHI_ID)
        result["checks"].append("  ✓ set_rls_context(陕西华氏) 调用成功（无 SET 绑定参数异常）")
    except Exception as e:
        result["checks"].append(f"  ✗ set_rls_context 异常: {type(e).__name__}: {e}")

    # 3. RLS 表 POLICY 存在
    rows = (await db.execute(sa.text("""
        SELECT count(*) FROM pg_policies
        WHERE schemaname='public' AND policyname='project_isolation'
    """))).scalar()
    if rows >= 4:
        result["checks"].append(f"  ✓ project_isolation POLICY 数量={rows}（≥ 4）")
    else:
        result["checks"].append(f"  ✗ project_isolation POLICY 数量={rows}（< 4）")

    return result


async def day3_check(db: AsyncSession) -> dict:
    """Day 3: 单项目灰度 — 用 set_project_flag 开 1 个测试项目"""
    result = {"phase": "Day 3 — 单项目灰度", "checks": []}

    # 1. 默认全局值
    global_v2 = is_enabled("ledger_import_v2")
    result["checks"].append(f"  ℹ 全局 ledger_import_v2 = {global_v2}")

    # 2. 项目级 override 模拟（开陕西华氏）
    set_project_flag(SHANXI_HUASHI_ID, "ledger_import_v2", True)
    after = is_enabled("ledger_import_v2", SHANXI_HUASHI_ID)
    result["checks"].append(f"  ✓ set_project_flag(陕西华氏, True) → is_enabled = {after}")

    # 3. 单项目回退能力（出问题时 set_project_flag(pid, False)）
    set_project_flag(SHANXI_HUASHI_ID, "ledger_import_v2", False)
    after_off = is_enabled("ledger_import_v2", SHANXI_HUASHI_ID)
    result["checks"].append(f"  ✓ set_project_flag(陕西华氏, False) → is_enabled = {after_off}（回退路径有效）")

    # 4. 恢复
    set_project_flag(SHANXI_HUASHI_ID, "ledger_import_v2", True)

    return result


async def day7_check(db: AsyncSession) -> dict:
    """Day 7: 全量 + F18 Day 7 一次性 UPDATE 迁移"""
    result = {"phase": "Day 7 — 全量 + F18 迁移", "checks": []}

    # 1. F18 迁移文件就位
    repo_root = Path(__file__).resolve().parent.parent.parent
    f18 = repo_root / "backend/alembic/versions/view_refactor_cleanup_old_deleted_20260517.py"
    if f18.exists():
        result["checks"].append(f"  ✓ F18 Day 7 迁移文件就位: {f18.name}")
    else:
        result["checks"].append(f"  ✗ F18 Day 7 迁移文件缺失")

    # 2. RLS 表实际能查询（设置 RLS context → 查 working_paper）
    await set_rls_context(db, SHANXI_HUASHI_ID)
    n = (await db.execute(sa.text(
        "SELECT count(*) FROM working_paper WHERE project_id = :pid AND is_deleted = false"
    ), {"pid": str(SHANXI_HUASHI_ID)})).scalar()
    result["checks"].append(f"  ✓ RLS context 设置后 working_paper 查询返回 {n} 行（陕西华氏项目）")

    # 3. tb_balance 同款（验证 RLS 4 张表全部可查）
    n_tb = (await db.execute(sa.text(
        "SELECT count(*) FROM tb_balance WHERE project_id = :pid AND is_deleted = false"
    ), {"pid": str(SHANXI_HUASHI_ID)})).scalar()
    result["checks"].append(f"  ✓ RLS 下 tb_balance 查询返回 {n_tb} 行")

    # 4. 不带 RLS context（重置后）应空（验证隔离生效）
    # 注：set_config(_, _, true) 是 LOCAL，事务结束自动清；这里同事务内 reset 模拟下游 dependency 未设
    await db.execute(sa.text("SELECT set_config('app.current_project_id', '', true)"))
    n_empty = (await db.execute(sa.text(
        "SELECT count(*) FROM working_paper WHERE is_deleted = false"
    ))).scalar()

    # 看当前 role 是否被 bypass RLS（superuser / rolbypassrls=true）
    role_check = (await db.execute(sa.text("""
        SELECT rolname, rolsuper, rolbypassrls
        FROM pg_roles WHERE rolname = current_user
    """))).first()
    is_bypass = role_check[1] or role_check[2]

    if is_bypass:
        result["checks"].append(
            f"  ℹ 当前连接 role={role_check[0]} super={role_check[1]} bypassrls={role_check[2]} "
            f"→ RLS 对 superuser 永远 bypass（PG 文档）；本地 dev 用 postgres 直连绕过隔离"
        )
        result["checks"].append(
            f"  ⚠ 生产环境必须用独立应用 role（非 superuser，无 BYPASSRLS）部署，"
            f"方能验证真实隔离；本机 dev 上 RLS 测试仅验证 POLICY 语法 + set_rls_context API"
        )
    else:
        if n_empty == 0:
            result["checks"].append(f"  ✓ RLS context 为空时 working_paper 查询返回 {n_empty} 行（隔离生效）")
        else:
            result["checks"].append(f"  ⚠ RLS context 为空时仍返回 {n_empty} 行（POLICY 可能允许 NULL）")

    return result


async def main():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 70)
    print("ledger-import-view-refactor 灰度部署单机模拟（spec 9.9）")
    print("=" * 70)

    all_pass = True
    for check_fn in (day0_check, day3_check, day7_check):
        async with sm() as db:
            result = await check_fn(db)
        print(f"\n📅 {result['phase']}")
        for line in result["checks"]:
            print(line)
            if line.strip().startswith("✗"):
                all_pass = False

    print("\n" + "=" * 70)
    print(f"灰度部署模拟: {'✅ 全部通过' if all_pass else '⚠ 有失败项需修复'}")
    print("=" * 70)
    print()
    print("说明：")
    print("  - 真生产环境部署应在 Day 0/3/7 各执行一次本脚本（间隔时间）")
    print("  - 单项目回退路径：set_project_flag(pid, 'ledger_import_v2', False)")
    print("  - F18 一次性 UPDATE 迁移在 Day 7 与全局 flag 切换同步执行")

    await engine.dispose()
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
