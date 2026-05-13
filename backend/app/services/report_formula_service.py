"""报表公式填充服务。

将 fill_report_formulas.py 脚本的核心逻辑封装为可复用的 Service 类，
供 API 端点和 seed 流程调用。

幂等：已有 formula 的行跳过不覆盖。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReportType, ReportConfig

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _load_json(filename: str):
    with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_name(name: str) -> str:
    """标准化行名：去除特殊前缀、标点、空格。"""
    name = re.sub(r"[△▲]", "", name)
    name = re.sub(r"^[一二三四五六七八九十]+、\s*", "", name)
    name = re.sub(r"^(加：|减：|其中：|加:|减:|其中:)\s*", "", name)
    name = name.replace("：", "").replace(":", "").replace(" ", "").replace("\u3000", "").strip()
    return name


# ---------------------------------------------------------------------------
# 特殊公式规则（手工精确定义，最高优先级）
# ---------------------------------------------------------------------------

_BS_SPECIAL: dict[str, str] = {
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

_IS_SPECIAL: dict[str, str] = {
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

_EQ_SPECIAL: dict[str, str] = {
    "实收资本": "TB('4001','期末余额')",
    "资本公积": "TB('4002','期末余额')",
    "其他综合收益": "TB('3102','期末余额')",
    "专项储备": "TB('4103','期末余额')",
    "盈余公积": "TB('4101','期末余额')",
    "未分配利润": "TB('4104','期末余额')",
}


def _get_special(row_name: str, report_type: str) -> str | None:
    """从特殊公式表查找匹配。"""
    norm = _normalize_name(row_name)
    if report_type == "balance_sheet":
        return _BS_SPECIAL.get(norm)
    elif report_type == "income_statement":
        return _IS_SPECIAL.get(norm)
    elif report_type == "equity_statement":
        return _EQ_SPECIAL.get(norm)
    return None


# ---------------------------------------------------------------------------
# CAS 公式转换
# ---------------------------------------------------------------------------


def _build_cas_name_formulas() -> dict[str, dict[str, str | None]]:
    """从 multi_standard_report_formats.json 构建 {report_key: {normalized_name: formula}}。"""
    data = _load_json("multi_standard_report_formats.json")
    cas = data.get("standards", {}).get("CAS", {})
    result: dict[str, dict[str, str | None]] = {}
    for key, rows in cas.items():
        name_map: dict[str, str | None] = {}
        for row in rows:
            name = _normalize_name(row.get("row_name", ""))
            formula = row.get("formula")
            if name:
                name_map[name] = formula
        result[key] = name_map
    return result


def _convert_formula(formula: str | None, col: str) -> str | None:
    """将 CAS 简写公式转换为引擎可执行格式。

    TB(1001) → TB('1001','col')
    SUM_TB(14) → SUM_TB('1400~1499','col')
    ROW(X:Y) → SUM_ROW('X','Y')
    ROW(X) → ROW('X')
    """
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
    result = re.sub(
        r"ROW\(([A-Z]+-\d+):([A-Z]+-\d+)\)",
        lambda m: f"SUM_ROW('{m.group(1)}','{m.group(2)}')",
        result,
    )
    # ROW single
    result = re.sub(
        r"ROW\(([A-Z]+-\d+)\)",
        lambda m: f"ROW('{m.group(1)}')",
        result,
    )
    # TB
    result = re.sub(
        r"TB\((\d+)\)",
        lambda m: f"TB('{m.group(1)}','{col}')",
        result,
    )
    return result


# ---------------------------------------------------------------------------
# 合计行公式
# ---------------------------------------------------------------------------


def _generate_sum_formula(configs: list, current_idx: int) -> str | None:
    """为合计行自动生成 SUM_ROW 公式。"""
    current = configs[current_idx]
    ci = current.indent_level
    child_codes: list[str] = []

    # 向上查找子行
    for i in range(current_idx - 1, -1, -1):
        row = configs[i]
        if row.indent_level <= ci:
            break
        child_codes.append(row.row_code)

    # 如果没有子行，查找同级行
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
# Service 类
# ---------------------------------------------------------------------------

_TYPE_TO_CAS = {
    "balance_sheet": "BS",
    "income_statement": "IS",
    "cash_flow_statement": "CFS",
    "equity_statement": "EQ",
}

_TYPE_TO_COL = {
    "balance_sheet": "期末余额",
    "income_statement": "本期发生额",
    "cash_flow_statement": "期末余额",
    "equity_statement": "期末余额",
    "cash_flow_supplement": "期末余额",
    "impairment_provision": "期末余额",
}

_STANDARD_GROUPS = {
    "all": ["soe_consolidated", "soe_standalone", "listed_consolidated", "listed_standalone"],
    "soe": ["soe_consolidated", "soe_standalone"],
    "listed": ["listed_consolidated", "listed_standalone"],
}


class ReportFormulaService:
    """报表公式填充服务。

    幂等：已有 formula 的行跳过不覆盖。
    返回统计信息：{total, updated, skipped, coverage_pct}
    """

    def __init__(self):
        self._cas_formulas: dict[str, dict[str, str | None]] | None = None

    def _get_cas_formulas(self) -> dict[str, dict[str, str | None]]:
        """懒加载 CAS 公式映射（只读一次 JSON）。"""
        if self._cas_formulas is None:
            self._cas_formulas = _build_cas_name_formulas()
        return self._cas_formulas

    async def fill_all_formulas(
        self,
        db: AsyncSession,
        standard: str = "all",
    ) -> dict:
        """填充 report_config 表的 formula 字段。

        Args:
            db: 异步数据库会话
            standard: "all" | "soe" | "listed" | 具体标准名

        Returns:
            {total, updated, skipped, coverage_pct}
        """
        cas_formulas = self._get_cas_formulas()

        # 解析 standard 参数
        if standard in _STANDARD_GROUPS:
            standards = _STANDARD_GROUPS[standard]
        else:
            standards = [standard]

        stats = {"total": 0, "updated": 0, "skipped": 0, "no_formula": 0}

        for std in standards:
            result = await db.execute(
                sa.select(ReportConfig).where(
                    ReportConfig.applicable_standard == std,
                    ReportConfig.is_deleted == sa.false(),
                ).order_by(ReportConfig.report_type, ReportConfig.row_number)
            )
            configs = result.scalars().all()
            if not configs:
                logger.info("fill_all_formulas: 未找到 %s 的配置行", std)
                continue

            # 按报表类型分组
            by_type: dict[str, list] = {}
            for cfg in configs:
                rt = cfg.report_type.value if hasattr(cfg.report_type, "value") else str(cfg.report_type)
                by_type.setdefault(rt, []).append(cfg)

            for report_type, type_configs in by_type.items():
                cas_key = _TYPE_TO_CAS.get(report_type, "")
                col = _TYPE_TO_COL.get(report_type, "期末余额")
                cas_map = cas_formulas.get(cas_key, {})

                for idx, cfg in enumerate(type_configs):
                    stats["total"] += 1

                    # 幂等：已有公式则跳过
                    if cfg.formula:
                        stats["skipped"] += 1
                        continue

                    row_name = cfg.row_name or ""
                    norm = _normalize_name(row_name)
                    formula: str | None = None
                    source: str | None = None

                    # 策略 1: 特殊公式表（最高优先级）
                    formula = _get_special(row_name, report_type)
                    if formula:
                        source = "special"

                    # 策略 2: CAS 标准公式
                    if not formula and norm in cas_map:
                        raw = cas_map[norm]
                        formula = _convert_formula(raw, col)
                        if formula:
                            source = "cas"

                    # 策略 3: 合计行关键词
                    if not formula and any(kw in row_name for kw in ("合计", "小计", "总计", "总额")):
                        formula = _generate_sum_formula(type_configs, idx)
                        if formula:
                            source = "auto_total"

                    # 策略 4: is_total_row 标记
                    if not formula and cfg.is_total_row:
                        formula = _generate_sum_formula(type_configs, idx)
                        if formula:
                            source = "auto_total_flag"

                    if formula:
                        cfg.formula = formula
                        cfg.formula_source = source
                        cfg.formula_category = "auto_calc"
                        stats["updated"] += 1
                    else:
                        stats["no_formula"] += 1

        # 计算覆盖率
        fillable = stats["total"] - stats["skipped"]
        coverage_pct = round(stats["updated"] / max(fillable, 1) * 100, 1)
        stats["coverage_pct"] = coverage_pct

        logger.info(
            "fill_all_formulas 完成: total=%d updated=%d skipped=%d coverage=%.1f%%",
            stats["total"],
            stats["updated"],
            stats["skipped"],
            coverage_pct,
        )
        return stats


# 模块级单例
report_formula_service = ReportFormulaService()
