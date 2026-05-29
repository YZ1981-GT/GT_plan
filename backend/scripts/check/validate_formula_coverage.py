"""验证 report_config 表的公式覆盖率。

扫描 4 个标准 × 多种报表类型，统计公式覆盖率并列出缺失行次。
覆盖率 < 95% 时以非零退出码退出。

用法：
    python scripts/validate_formula_coverage.py [--standard all|soe_consolidated|...] [--verbose]

运行环境：从 backend/ 目录执行
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.report_models import ReportConfig


ALL_STANDARDS = [
    "soe_consolidated",
    "soe_standalone",
    "listed_consolidated",
    "listed_standalone",
]


def _is_title_row(row_name: str) -> bool:
    """判断是否为标题行（以冒号结尾）"""
    return row_name.endswith("：") or row_name.endswith(":")


def _get_database_url() -> str:
    """获取数据库连接 URL"""
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("DATABASE_URL="):
                    database_url = line.split("=", 1)[1].strip().strip('"')
                    break
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(2)

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)

    return database_url


async def validate_coverage(
    standard: str = "all",
    verbose: bool = False,
) -> dict[str, dict[str, Any]]:
    """扫描 report_config 表，返回覆盖率统计

    Returns: {
        "soe_consolidated": {
            "balance_sheet": {"total": N, "with_formula": N, "missing": [...], "pct": float},
            ...
        },
        ...
    }
    """
    database_url = _get_database_url()
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    if standard == "all":
        standards = ALL_STANDARDS
    else:
        standards = [standard]

    results: dict[str, dict[str, Any]] = {}

    async with async_session() as db:
        for std in standards:
            result = await db.execute(
                sa.select(ReportConfig).where(
                    ReportConfig.applicable_standard == std,
                    ReportConfig.is_deleted == sa.false(),
                ).order_by(ReportConfig.report_type, ReportConfig.row_number)
            )
            configs = result.scalars().all()

            if not configs:
                results[std] = {}
                continue

            # 按报表类型分组
            by_type: dict[str, list] = {}
            for cfg in configs:
                rt = cfg.report_type.value if hasattr(cfg.report_type, "value") else str(cfg.report_type)
                by_type.setdefault(rt, []).append(cfg)

            std_results: dict[str, Any] = {}
            for report_type, type_configs in by_type.items():
                # 排除标题行后统计
                non_title_rows = [
                    cfg for cfg in type_configs
                    if not _is_title_row(cfg.row_name or "")
                ]
                total = len(non_title_rows)
                with_formula = sum(1 for cfg in non_title_rows if cfg.formula)
                missing = [
                    {"row_code": cfg.row_code, "row_name": cfg.row_name}
                    for cfg in non_title_rows
                    if not cfg.formula
                ]
                pct = (with_formula / total * 100) if total > 0 else 100.0

                std_results[report_type] = {
                    "total": total,
                    "with_formula": with_formula,
                    "missing": missing,
                    "pct": pct,
                }

            results[std] = std_results

    await engine.dispose()
    return results


def _print_results(results: dict[str, dict[str, Any]], verbose: bool) -> bool:
    """打印覆盖率结果，返回是否全部达标（>= 95%）"""
    all_pass = True

    for std, std_results in results.items():
        print(f"\n{'='*60}")
        print(f"标准: {std}")
        print(f"{'='*60}")

        if not std_results:
            print("  ⚠️  未找到配置数据")
            continue

        std_total = 0
        std_with_formula = 0

        for report_type, stats in std_results.items():
            total = stats["total"]
            with_formula = stats["with_formula"]
            pct = stats["pct"]
            missing_count = len(stats["missing"])

            std_total += total
            std_with_formula += with_formula

            status = "✅" if pct >= 95.0 else "❌"
            print(f"  {status} {report_type}: {pct:.1f}% ({with_formula}/{total})")

            if pct < 95.0:
                all_pass = False
                print(f"      ⚠️  覆盖率不足 95%，缺失 {missing_count} 行")

            if verbose and stats["missing"]:
                for item in stats["missing"]:
                    print(f"      - {item['row_code']}: {item['row_name']}")

        # 标准总覆盖率
        std_pct = (std_with_formula / std_total * 100) if std_total > 0 else 100.0
        print(f"\n  📊 标准总覆盖率: {std_pct:.1f}% ({std_with_formula}/{std_total})")
        if std_pct < 95.0:
            all_pass = False

    return all_pass


def main():
    parser = argparse.ArgumentParser(
        description="验证 report_config 表的公式覆盖率"
    )
    parser.add_argument(
        "--standard",
        default="all",
        choices=["all"] + ALL_STANDARDS,
        help="指定标准（默认 all）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出缺失行次详情",
    )
    args = parser.parse_args()

    results = asyncio.run(validate_coverage(standard=args.standard, verbose=args.verbose))

    if not results:
        print("⚠️  未找到任何 report_config 数据")
        sys.exit(0)

    all_pass = _print_results(results, verbose=args.verbose)

    if not all_pass:
        print("\n❌ 覆盖率未达标（< 95%），退出码 1")
        sys.exit(1)
    else:
        print("\n✅ 所有标准覆盖率均达标（>= 95%）")
        sys.exit(0)


if __name__ == "__main__":
    main()
