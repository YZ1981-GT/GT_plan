"""填充 report_config 表的 formula 字段。

核心策略：按 row_name 匹配，而非 row_code。
wp_account_mapping 的 row_code 编号与 report_config_seed 不一致。

用法：python scripts/fill_report_formulas.py [--dry-run] [--standard soe|listed|all]
运行环境：从 backend/ 目录执行
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.report_models import ReportConfig, FinancialReportType

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_json(filename: str):
    with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_name(name: str) -> str:
    name = re.sub(r"[△▲]", "", name)
    name = re.sub(r"^[一二三四五六七八九十]+、\s*", "", name)
    name = re.sub(r"^(加：|减：|其中：|加:|减:|其中:)\s*", "", name)
    name = name.replace("：", "").replace(":", "").replace(" ", "").replace("　", "").strip()
    return name


# ---------------------------------------------------------------------------
# 特殊公式规则（手工精确定义，最高优先级）
# ---------------------------------------------------------------------------

BS_SPECIAL = {
    "货币资金": "TB('1001','期末余额')+TB('1002','期末余额')+TB('1012','期末余额')",
    "交易性金融资产": "TB('1101','期末余额')",
    "应收票据": "TB('1121','期末余额')",
    "应收账款": "TB('1122','期末余额')-TB('1231','期末余额')",
    "预付款项": "TB('1123','期末余额')",
    "其他应收款": "TB('1221','期末余额')",
    "存货": "SUM_TB('1400~1499','期末余额')",
    "合同资产": "TB('1141','期末余额')",
    "长期股权投资": "TB('1511','期末余额')",
    "投资性房地产": "TB('1521','期末余额')",
    "固定资产": "TB('1601','期末余额')-TB('1602','期末余额')",
    "在建工程": "TB('1604','期末余额')",
    "无形资产": "TB('1701','期末余额')-TB('1702','期末余额')",
    "商誉": "TB('1711','期末余额')",
    "长期待摊费用": "TB('1801','期末余额')",
    "递延所得税资产": "TB('1811','期末余额')",
    "使用权资产": "TB('1641','期末余额')",
    "开发支出": "TB('1703','期末余额')",
    "债权投资": "TB('1504','期末余额')",
    "其他权益工具投资": "TB('1503','期末余额')",
    "其他非流动金融资产": "TB('1509','期末余额')",
    "短期借款": "TB('2001','期末余额')",
    "应付票据": "TB('2201','期末余额')",
    "应付账款": "TB('2202','期末余额')",
    "预收款项": "TB('2203','期末余额')",
    "合同负债": "TB('2205','期末余额')",
    "应付职工薪酬": "TB('2211','期末余额')",
    "应交税费": "TB('2221','期末余额')",
    "其他应付款": "TB('2241','期末余额')",
    "长期借款": "TB('2501','期末余额')",
    "应付债券": "TB('2502','期末余额')",
    "租赁负债": "TB('2601','期末余额')",
    "长期应付款": "TB('2701','期末余额')",
    "预计负债": "TB('2801','期末余额')",
    "递延收益": "TB('2401','期末余额')",
    "递延所得税负债": "TB('2901','期末余额')",
    "实收资本": "TB('4001','期末余额')",
    "股本": "TB('4001','期末余额')",
    "资本公积": "TB('4002','期末余额')",
    "其他综合收益": "TB('3102','期末余额')",
    "专项储备": "TB('4103','期末余额')",
    "盈余公积": "TB('4101','期末余额')",
    "未分配利润": "TB('4104','期末余额')",
    "一年内到期的非流动资产": "TB('1503','期末余额')",
    "一年内到期的非流动负债": "TB('2502','期末余额')",
    "其他流动资产": "TB('1901','期末余额')",
    "其他流动负债": "TB('2301','期末余额')",
    "其他非流动负债": "TB('2901','期末余额')",
    "应收款项融资": "TB('1124','期末余额')",
}

IS_SPECIAL = {
    "营业收入": "TB('6001','本期发生额')+TB('6051','本期发生额')",
    "营业总收入": "TB('6001','本期发生额')+TB('6051','本期发生额')",
    "营业成本": "TB('6401','本期发生额')+TB('6402','本期发生额')",
    "税金及附加": "TB('6403','本期发生额')",
    "销售费用": "TB('6601','本期发生额')",
    "管理费用": "TB('6602','本期发生额')",
    "研发费用": "TB('6604','本期发生额')",
    "财务费用": "TB('6603','本期发生额')",
    "投资收益": "TB('6111','本期发生额')",
    "公允价值变动收益": "TB('6101','本期发生额')",
    "信用减值损失": "TB('6701','本期发生额')",
    "资产减值损失": "TB('6702','本期发生额')",
    "资产处置收益": "TB('6115','本期发生额')",
    "其他收益": "TB('6117','本期发生额')",
    "营业外收入": "TB('6301','本期发生额')",
    "营业外支出": "TB('6711','本期发生额')",
    "所得税费用": "TB('6801','本期发生额')",
}

EQ_SPECIAL = {
    "实收资本": "TB('4001','期末余额')",
    "资本公积": "TB('4002','期末余额')",
    "其他综合收益": "TB('3102','期末余额')",
    "专项储备": "TB('4103','期末余额')",
    "盈余公积": "TB('4101','期末余额')",
    "未分配利润": "TB('4104','期末余额')",
}


def get_special(row_name: str, report_type: str):
    norm = normalize_name(row_name)
    if report_type == "balance_sheet":
        return BS_SPECIAL.get(norm)
    elif report_type == "income_statement":
        return IS_SPECIAL.get(norm)
    elif report_type == "equity_statement":
        return EQ_SPECIAL.get(norm)
    return None


# ---------------------------------------------------------------------------
# CAS 公式转换
# ---------------------------------------------------------------------------

def build_cas_name_formulas():
    data = load_json("multi_standard_report_formats.json")
    cas = data.get("standards", {}).get("CAS", {})
    result = {}
    for key, rows in cas.items():
        name_map = {}
        for row in rows:
            name = normalize_name(row.get("row_name", ""))
            formula = row.get("formula")
            if name:
                name_map[name] = formula
        result[key] = name_map
    return result


def convert_formula(formula, col):
    """TB(1001) → TB('1001','col'), ROW(X:Y) → SUM_ROW('X','Y')"""
    if not formula:
        return None
    result = formula
    # SUM_TB
    def _sum_tb(m):
        cr = m.group(1)
        if "~" in cr:
            return f"SUM_TB('{cr}','{col}')"
        p = cr
        return f"SUM_TB('{p}00~{p}99','{col}')" if len(p) == 2 else f"SUM_TB('{p}0~{p}9','{col}')"
    result = re.sub(r"SUM_TB\(([^)]+)\)", _sum_tb, result)
    # ROW range
    result = re.sub(r"ROW\(([A-Z]+-\d+):([A-Z]+-\d+)\)",
                    lambda m: f"SUM_ROW('{m.group(1)}','{m.group(2)}')", result)
    # ROW single
    result = re.sub(r"ROW\(([A-Z]+-\d+)\)",
                    lambda m: f"ROW('{m.group(1)}')", result)
    # TB
    result = re.sub(r"TB\((\d+)\)",
                    lambda m: f"TB('{m.group(1)}','{col}')", result)
    return result


# ---------------------------------------------------------------------------
# 合计行公式
# ---------------------------------------------------------------------------

def generate_sum_formula(configs, current_idx):
    current = configs[current_idx]
    ci = current.indent_level
    child_codes = []
    for i in range(current_idx - 1, -1, -1):
        row = configs[i]
        if row.indent_level <= ci:
            break
        child_codes.append(row.row_code)
    if not child_codes:
        for i in range(current_idx - 1, -1, -1):
            row = configs[i]
            if row.indent_level < ci:
                break
            if row.indent_level == ci:
                rn = row.row_name or ""
                if any(k in rn for k in ("：", ":", "合计", "小计")):
                    break
                child_codes.append(row.row_code)
    if len(child_codes) >= 2:
        return f"SUM_ROW('{child_codes[-1]}','{child_codes[0]}')"
    elif len(child_codes) == 1:
        return f"ROW('{child_codes[0]}')"
    return None


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

async def fill_formulas(dry_run=False, standard_filter="all"):
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("DATABASE_URL="):
                    database_url = line.split("=", 1)[1].strip().strip('"')
                    break
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    cas_formulas = build_cas_name_formulas()

    if standard_filter == "all":
        standards = ["soe_consolidated", "soe_standalone", "listed_consolidated", "listed_standalone"]
    elif standard_filter == "soe":
        standards = ["soe_consolidated", "soe_standalone"]
    elif standard_filter == "listed":
        standards = ["listed_consolidated", "listed_standalone"]
    else:
        standards = [standard_filter]

    type_to_cas = {"balance_sheet": "BS", "income_statement": "IS",
                   "cash_flow_statement": "CFS", "equity_statement": "EQ"}
    type_to_col = {"balance_sheet": "期末余额", "income_statement": "本期发生额",
                   "cash_flow_statement": "期末余额", "equity_statement": "期末余额",
                   "cash_flow_supplement": "期末余额", "impairment_provision": "期末余额"}

    stats = {"updated": 0, "skipped": 0, "total": 0, "no_formula": 0}

    async with async_session() as db:
        for std in standards:
            print(f"\n{'='*60}\n处理标准: {std}\n{'='*60}")
            result = await db.execute(
                sa.select(ReportConfig).where(
                    ReportConfig.applicable_standard == std,
                    ReportConfig.is_deleted == sa.false(),
                ).order_by(ReportConfig.report_type, ReportConfig.row_number)
            )
            configs = result.scalars().all()
            if not configs:
                print(f"  ⚠️  未找到 {std} 的配置行")
                continue

            by_type = {}
            for cfg in configs:
                rt = cfg.report_type.value if hasattr(cfg.report_type, "value") else str(cfg.report_type)
                by_type.setdefault(rt, []).append(cfg)

            for report_type, type_configs in by_type.items():
                print(f"\n  📊 {report_type} ({len(type_configs)} 行)")
                cas_key = type_to_cas.get(report_type, "")
                col = type_to_col.get(report_type, "期末余额")
                cas_map = cas_formulas.get(cas_key, {})

                updated_count = 0
                for idx, cfg in enumerate(type_configs):
                    stats["total"] += 1
                    row_name = cfg.row_name or ""
                    norm = normalize_name(row_name)

                    if cfg.formula:
                        stats["skipped"] += 1
                        continue

                    formula = None
                    source = None

                    # 策略 1: 特殊公式表
                    formula = get_special(row_name, report_type)
                    if formula:
                        source = "special"

                    # 策略 2: CAS 标准公式
                    if not formula and norm in cas_map:
                        raw = cas_map[norm]
                        formula = convert_formula(raw, col)
                        if formula:
                            source = "cas"

                    # 策略 3: 合计行
                    if not formula and any(kw in row_name for kw in ("合计", "小计", "总计", "总额")):
                        formula = generate_sum_formula(type_configs, idx)
                        if formula:
                            source = "auto_total"

                    # 策略 4: is_total_row
                    if not formula and cfg.is_total_row:
                        formula = generate_sum_formula(type_configs, idx)
                        if formula:
                            source = "auto_total_flag"

                    if formula:
                        if not dry_run:
                            cfg.formula = formula
                            cfg.formula_source = source
                            cfg.formula_category = "auto_calc"
                        updated_count += 1
                        stats["updated"] += 1
                        if updated_count <= 10:
                            print(f"    ✅ {cfg.row_code} {row_name}: {formula} [{source}]")
                    else:
                        stats["no_formula"] += 1

                if updated_count > 10:
                    print(f"    ... 共 {updated_count} 行已填充")
                else:
                    print(f"    共 {updated_count} 行已填充")

        if not dry_run:
            await db.commit()
            print(f"\n✅ 已提交到数据库")
        else:
            print(f"\n⚠️  DRY RUN 模式，未写入数据库")

    await engine.dispose()
    print(f"\n{'='*60}")
    print(f"统计: 总={stats['total']} 填充={stats['updated']} 跳过={stats['skipped']} 无公式={stats['no_formula']}")
    coverage = stats["updated"] / max(stats["total"] - stats["skipped"], 1) * 100
    print(f"覆盖率: {coverage:.1f}%")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="填充 report_config formula")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--standard", default="all",
                        choices=["all", "soe", "listed", "soe_consolidated",
                                 "soe_standalone", "listed_consolidated", "listed_standalone"])
    args = parser.parse_args()
    asyncio.run(fill_formulas(dry_run=args.dry_run, standard_filter=args.standard))
