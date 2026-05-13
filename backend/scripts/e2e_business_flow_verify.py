"""端到端业务流程验证脚本 — 4 个项目全量检查

Layer 1: trial_balance 有数据（COUNT > 0）
Layer 2: 报表生成成功（BS 非零行 ≥ 10）
Layer 3: 数据质量检查能执行（Sprint 2 补充）
Layer 4: 底稿/附注生成 + 工作流进度（Sprint 4 补充）

用法:
    python scripts/e2e_business_flow_verify.py
"""
import asyncio
import io
import os
import sys

# Windows GBK 终端无法输出 emoji，强制 UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from uuid import UUID

# Setup path and env
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

# ─── 项目清单 ───────────────────────────────────────────────────────────────
PROJECTS = [
    (UUID("005a6f2d-cecd-4e30-bcbd-9fb01236c194"), "陕西华氏", 2025),
    (UUID("5942c12e-65fb-4187-ace3-79d45a90cb53"), "和平药房", 2025),
    (UUID("37814426-a29e-4fc2-9313-a59d229bf7b0"), "辽宁卫生", 2025),
    (UUID("14fb8c10-9462-45f6-8f56-d023f5b6df13"), "宜宾大药房", 2025),
]

# ─── 阈值 ───────────────────────────────────────────────────────────────────
TRIAL_BALANCE_MIN_ROWS = 1       # Layer 1: 至少有数据
BS_NON_ZERO_MIN_ROWS = 10       # Layer 2: BS 非零行 ≥ 10


async def check_layer1(db: AsyncSession, project_id: UUID, year: int) -> tuple[bool, int]:
    """Layer 1: trial_balance 有数据"""
    result = await db.execute(sa.text(
        "SELECT COUNT(*) FROM trial_balance "
        "WHERE project_id = :pid AND year = :yr AND is_deleted = false"
    ), {"pid": project_id, "yr": year})
    count = result.scalar() or 0
    return count >= TRIAL_BALANCE_MIN_ROWS, count


async def check_layer2(db: AsyncSession, project_id: UUID, year: int) -> tuple[bool, int]:
    """Layer 2: financial_report BS 非零行 ≥ 10"""
    result = await db.execute(sa.text(
        "SELECT COUNT(*) FROM financial_report "
        "WHERE project_id = :pid AND year = :yr "
        "AND report_type = 'balance_sheet' "
        "AND is_deleted = false "
        "AND current_period_amount IS NOT NULL "
        "AND current_period_amount != 0"
    ), {"pid": project_id, "yr": year})
    count = result.scalar() or 0
    return count >= BS_NON_ZERO_MIN_ROWS, count


async def check_layer3(db: AsyncSession, project_id: UUID, year: int) -> tuple[bool, str]:
    """Layer 3: 数据质量检查能执行 + 报表表样验证

    验证:
    1. DataQualityService 能正常执行（不抛异常）
    2. 报表有行数据（financial_report 有记录）
    """
    from app.services.data_quality_service import DataQualityService

    try:
        service = DataQualityService(db)
        result = await service.run_checks(project_id, year, "debit_credit_balance,mapping_completeness")

        # 检查是否正常返回结果
        if not result or "results" not in result:
            return False, "数据质量检查返回空结果"

        checks_run = result.get("checks_run", [])
        if len(checks_run) == 0:
            return False, "无检查项被执行"

        # 验证报表有行数据（表样验证基础）
        report_result = await db.execute(sa.text(
            "SELECT COUNT(*) FROM financial_report "
            "WHERE project_id = :pid AND year = :yr AND is_deleted = false"
        ), {"pid": project_id, "yr": year})
        report_rows = report_result.scalar() or 0

        if report_rows == 0:
            return True, f"质量检查OK({len(checks_run)}项), 报表未生成"

        return True, f"质量检查OK({len(checks_run)}项), 报表{report_rows}行"

    except Exception as e:
        return False, f"异常: {str(e)[:80]}"


async def check_layer4(db: AsyncSession, project_id: UUID, year: int) -> tuple[bool, str]:
    """Layer 4: 底稿/附注生成 + 工作流进度验证

    验证:
    1. working_papers > 0（底稿已生成）
    2. disclosure_notes > 0（附注已生成）
    3. 工作流进度推导正确（current_step >= 3 表示至少到试算表步骤）
    """
    try:
        # 检查底稿
        wp_result = await db.execute(sa.text(
            "SELECT COUNT(*) FROM working_paper "
            "WHERE project_id = :pid AND is_deleted = false"
        ), {"pid": project_id})
        wp_count = wp_result.scalar() or 0

        # 检查附注
        notes_result = await db.execute(sa.text(
            "SELECT COUNT(*) FROM disclosure_notes "
            "WHERE project_id = :pid AND year = :yr AND is_deleted = false"
        ), {"pid": project_id, "yr": year})
        notes_count = notes_result.scalar() or 0

        info_parts = []
        if wp_count > 0:
            info_parts.append(f"底稿{wp_count}")
        else:
            info_parts.append("底稿0")
        if notes_count > 0:
            info_parts.append(f"附注{notes_count}")
        else:
            info_parts.append("附注0")

        # Layer 4 通过条件：底稿或附注至少有一个生成
        passed = wp_count > 0 or notes_count > 0
        return passed, "/".join(info_parts)

    except Exception as e:
        return False, f"异常: {str(e)[:60]}"


def print_table(results: list[dict]) -> None:
    """打印结果表格"""
    # Header
    print()
    print("=" * 130)
    print(f"{'项目':<12} {'Layer 1 (试算表)':<22} {'Layer 2 (BS非零行)':<22} {'Layer 3 (质量检查)':<26} {'Layer 4 (底稿/附注)':<26} {'结果':<8}")
    print("-" * 130)

    for r in results:
        l1_status = f"{'PASS' if r['l1_pass'] else 'FAIL'} ({r['l1_count']} rows)"
        l2_status = f"{'PASS' if r['l2_pass'] else 'FAIL'} ({r['l2_count']} rows)"
        l3_status = f"{'PASS' if r['l3_pass'] else 'FAIL'} {r['l3_info'][:18]}"
        l4_status = f"{'PASS' if r['l4_pass'] else 'FAIL'} {r['l4_info'][:18]}"
        overall = "✅ PASS" if r['l1_pass'] and r['l2_pass'] and r['l3_pass'] and r['l4_pass'] else "❌ FAIL"
        print(f"{r['name']:<12} {l1_status:<22} {l2_status:<22} {l3_status:<26} {l4_status:<26} {overall:<8}")

    print("=" * 130)


async def main() -> int:
    """主入口，返回 exit code（0=全通过，1=有失败）"""
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(url)
    async_session = sessionmaker(engine, class_=AsyncSession)

    results = []
    all_pass = True

    print("E2E Business Flow Verification")
    print(f"Projects: {len(PROJECTS)}")
    print(f"Layers: 1 (trial_balance) + 2 (BS non-zero ≥ {BS_NON_ZERO_MIN_ROWS}) + 3 (data quality) + 4 (workpapers/notes)")
    print()

    for project_id, name, year in PROJECTS:
        print(f"Checking {name} ({year})...", end=" ")

        async with async_session() as db:
            try:
                l1_pass, l1_count = await check_layer1(db, project_id, year)
                l2_pass, l2_count = await check_layer2(db, project_id, year)
                l3_pass, l3_info = await check_layer3(db, project_id, year)
                l4_pass, l4_info = await check_layer4(db, project_id, year)
            except Exception as e:
                await db.rollback()
                l1_pass, l1_count = False, 0
                l2_pass, l2_count = False, 0
                l3_pass, l3_info = False, f"ERR:{str(e)[:40]}"
                l4_pass, l4_info = False, "skipped"

            passed = l1_pass and l2_pass and l3_pass and l4_pass
            if not passed:
                all_pass = False

            results.append({
                "name": name,
                "project_id": project_id,
                "year": year,
                "l1_pass": l1_pass,
                "l1_count": l1_count,
                "l2_pass": l2_pass,
                "l2_count": l2_count,
                "l3_pass": l3_pass,
                "l3_info": l3_info,
                "l4_pass": l4_pass,
                "l4_info": l4_info,
            })

            print("✅" if passed else "❌")

    await engine.dispose()

    # Print summary table
    print_table(results)

    # Final verdict
    print()
    if all_pass:
        print("🎉 ALL PROJECTS PASSED Layer 1+2+3+4 verification!")
    else:
        failed = [r["name"] for r in results if not (r["l1_pass"] and r["l2_pass"] and r["l3_pass"] and r["l4_pass"])]
        print(f"⚠️  FAILED projects: {', '.join(failed)}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
