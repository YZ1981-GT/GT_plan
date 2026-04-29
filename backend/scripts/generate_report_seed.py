"""生成致同标准报表行次种子数据

致同两套标准 × 两种口径 = 4 套报表格式：
- soe_consolidated: 国企版合并报表
- soe_standalone: 国企版单体报表
- listed_consolidated: 上市版合并报表
- listed_standalone: 上市版单体报表

每套含 4 张报表：BS(资产负债表) / IS(利润表) / CFS(现金流量表) / EQ(权益变动表)

用法：python backend/scripts/generate_report_seed.py
输出：backend/data/report_config_seed.json
"""

import json
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "report_config_seed.json"


# ═══════════════════════════════════════════════════════════════════
# 资产负债表行次（国企版/上市版共用，合并版多少数股东权益）
# ═══════════════════════════════════════════════════════════════════

def _bs_rows(is_consolidated: bool, is_listed: bool) -> list[dict]:
    """生成资产负债表行次"""
    rows = [
        # ── 流动资产 ──
        {"row_code": "BS-001", "row_number": 1, "row_name": "流动资产：", "indent_level": 0, "formula": None, "is_total_row": False},
        {"row_code": "BS-002", "row_number": 2, "row_name": "货币资金", "indent_level": 1, "formula": "TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')"},
        {"row_code": "BS-003", "row_number": 3, "row_name": "交易性金融资产", "indent_level": 1, "formula": "TB('1101','期末余额')"},
        {"row_code": "BS-004", "row_number": 4, "row_name": "衍生金融资产", "indent_level": 1, "formula": "TB('1102','期末余额')"},
        {"row_code": "BS-005", "row_number": 5, "row_name": "应收票据", "indent_level": 1, "formula": "TB('1121','期末余额')"},
        {"row_code": "BS-006", "row_number": 6, "row_name": "应收账款", "indent_level": 1, "formula": "TB('1122','期末余额')"},
        {"row_code": "BS-007", "row_number": 7, "row_name": "应收款项融资", "indent_level": 1, "formula": "TB('1124','期末余额')"},
        {"row_code": "BS-008", "row_number": 8, "row_name": "预付款项", "indent_level": 1, "formula": "TB('1123','期末余额')"},
        {"row_code": "BS-009", "row_number": 9, "row_name": "其他应收款", "indent_level": 1, "formula": "TB('1221','期末余额')"},
        {"row_code": "BS-010", "row_number": 10, "row_name": "存货", "indent_level": 1, "formula": "SUM_TB('1401~1499','期末余额')"},
        {"row_code": "BS-011", "row_number": 11, "row_name": "合同资产", "indent_level": 1, "formula": "TB('1141','期末余额')"},
        {"row_code": "BS-012", "row_number": 12, "row_name": "持有待售资产", "indent_level": 1, "formula": "TB('1481','期末余额')"},
        {"row_code": "BS-013", "row_number": 13, "row_name": "一年内到期的非流动资产", "indent_level": 1, "formula": "TB('1503','期末余额')"},
        {"row_code": "BS-014", "row_number": 14, "row_name": "其他流动资产", "indent_level": 1, "formula": "TB('1901','期末余额')"},
        {"row_code": "BS-015", "row_number": 15, "row_name": "流动资产合计", "indent_level": 0, "formula": "ROW('BS-002') + ROW('BS-003') + ROW('BS-004') + ROW('BS-005') + ROW('BS-006') + ROW('BS-007') + ROW('BS-008') + ROW('BS-009') + ROW('BS-010') + ROW('BS-011') + ROW('BS-012') + ROW('BS-013') + ROW('BS-014')", "is_total_row": True},
        # ── 非流动资产 ──
        {"row_code": "BS-020", "row_number": 20, "row_name": "非流动资产：", "indent_level": 0, "formula": None},
        {"row_code": "BS-021", "row_number": 21, "row_name": "债权投资", "indent_level": 1, "formula": "TB('1504','期末余额')"},
        {"row_code": "BS-022", "row_number": 22, "row_name": "其他债权投资", "indent_level": 1, "formula": "TB('1505','期末余额')"},
        {"row_code": "BS-023", "row_number": 23, "row_name": "长期应收款", "indent_level": 1, "formula": "TB('1531','期末余额')"},
        {"row_code": "BS-024", "row_number": 24, "row_name": "长期股权投资", "indent_level": 1, "formula": "TB('1511','期末余额')"},
        {"row_code": "BS-025", "row_number": 25, "row_name": "其他权益工具投资", "indent_level": 1, "formula": "TB('1506','期末余额')"},
        {"row_code": "BS-026", "row_number": 26, "row_name": "其他非流动金融资产", "indent_level": 1, "formula": "TB('1507','期末余额')"},
        {"row_code": "BS-027", "row_number": 27, "row_name": "投资性房地产", "indent_level": 1, "formula": "TB('1521','期末余额')"},
        {"row_code": "BS-028", "row_number": 28, "row_name": "固定资产", "indent_level": 1, "formula": "TB('1601','期末余额') - TB('1602','期末余额')"},
        {"row_code": "BS-029", "row_number": 29, "row_name": "在建工程", "indent_level": 1, "formula": "TB('1604','期末余额')"},
        {"row_code": "BS-030", "row_number": 30, "row_name": "生产性生物资产", "indent_level": 1, "formula": "TB('1621','期末余额')"},
        {"row_code": "BS-031", "row_number": 31, "row_name": "使用权资产", "indent_level": 1, "formula": "TB('1641','期末余额')"},
        {"row_code": "BS-032", "row_number": 32, "row_name": "无形资产", "indent_level": 1, "formula": "TB('1701','期末余额') - TB('1702','期末余额')"},
        {"row_code": "BS-033", "row_number": 33, "row_name": "开发支出", "indent_level": 1, "formula": "TB('1703','期末余额')"},
        {"row_code": "BS-034", "row_number": 34, "row_name": "商誉", "indent_level": 1, "formula": "TB('1711','期末余额')"},
        {"row_code": "BS-035", "row_number": 35, "row_name": "长期待摊费用", "indent_level": 1, "formula": "TB('1801','期末余额')"},
        {"row_code": "BS-036", "row_number": 36, "row_name": "递延所得税资产", "indent_level": 1, "formula": "TB('1811','期末余额')"},
        {"row_code": "BS-037", "row_number": 37, "row_name": "其他非流动资产", "indent_level": 1, "formula": "TB('1911','期末余额')"},
        {"row_code": "BS-038", "row_number": 38, "row_name": "非流动资产合计", "indent_level": 0, "formula": "ROW('BS-021') + ROW('BS-022') + ROW('BS-023') + ROW('BS-024') + ROW('BS-025') + ROW('BS-026') + ROW('BS-027') + ROW('BS-028') + ROW('BS-029') + ROW('BS-030') + ROW('BS-031') + ROW('BS-032') + ROW('BS-033') + ROW('BS-034') + ROW('BS-035') + ROW('BS-036') + ROW('BS-037')", "is_total_row": True},
        {"row_code": "BS-039", "row_number": 39, "row_name": "资产总计", "indent_level": 0, "formula": "ROW('BS-015') + ROW('BS-038')", "is_total_row": True},
        # ── 流动负债 ──
        {"row_code": "BS-040", "row_number": 40, "row_name": "流动负债：", "indent_level": 0, "formula": None},
        {"row_code": "BS-041", "row_number": 41, "row_name": "短期借款", "indent_level": 1, "formula": "TB('2001','期末余额')"},
        {"row_code": "BS-042", "row_number": 42, "row_name": "交易性金融负债", "indent_level": 1, "formula": "TB('2101','期末余额')"},
        {"row_code": "BS-043", "row_number": 43, "row_name": "衍生金融负债", "indent_level": 1, "formula": "TB('2102','期末余额')"},
        {"row_code": "BS-044", "row_number": 44, "row_name": "应付票据", "indent_level": 1, "formula": "TB('2201','期末余额')"},
        {"row_code": "BS-045", "row_number": 45, "row_name": "应付账款", "indent_level": 1, "formula": "TB('2202','期末余额')"},
        {"row_code": "BS-046", "row_number": 46, "row_name": "预收款项", "indent_level": 1, "formula": "TB('2203','期末余额')"},
        {"row_code": "BS-047", "row_number": 47, "row_name": "合同负债", "indent_level": 1, "formula": "TB('2205','期末余额')"},
        {"row_code": "BS-048", "row_number": 48, "row_name": "应付职工薪酬", "indent_level": 1, "formula": "TB('2211','期末余额')"},
        {"row_code": "BS-049", "row_number": 49, "row_name": "应交税费", "indent_level": 1, "formula": "TB('2221','期末余额')"},
        {"row_code": "BS-050", "row_number": 50, "row_name": "其他应付款", "indent_level": 1, "formula": "TB('2241','期末余额')"},
        {"row_code": "BS-051", "row_number": 51, "row_name": "持有待售负债", "indent_level": 1, "formula": "TB('2245','期末余额')"},
        {"row_code": "BS-052", "row_number": 52, "row_name": "一年内到期的非流动负债", "indent_level": 1, "formula": "TB('2501','期末余额')"},
        {"row_code": "BS-053", "row_number": 53, "row_name": "其他流动负债", "indent_level": 1, "formula": "TB('2901','期末余额')"},
    ]
    rows.append({"row_code": "BS-054", "row_number": 54, "row_name": "流动负债合计", "indent_level": 0, "formula": "ROW('BS-041') + ROW('BS-042') + ROW('BS-043') + ROW('BS-044') + ROW('BS-045') + ROW('BS-046') + ROW('BS-047') + ROW('BS-048') + ROW('BS-049') + ROW('BS-050') + ROW('BS-051') + ROW('BS-052') + ROW('BS-053')", "is_total_row": True})
    # ── 非流动负债 ──
    rows.extend([
        {"row_code": "BS-060", "row_number": 60, "row_name": "非流动负债：", "indent_level": 0, "formula": None},
        {"row_code": "BS-061", "row_number": 61, "row_name": "长期借款", "indent_level": 1, "formula": "TB('2501','期末余额')"},
        {"row_code": "BS-062", "row_number": 62, "row_name": "应付债券", "indent_level": 1, "formula": "TB('2502','期末余额')"},
        {"row_code": "BS-063", "row_number": 63, "row_name": "租赁负债", "indent_level": 1, "formula": "TB('2601','期末余额')"},
        {"row_code": "BS-064", "row_number": 64, "row_name": "长期应付款", "indent_level": 1, "formula": "TB('2701','期末余额')"},
        {"row_code": "BS-065", "row_number": 65, "row_name": "预计负债", "indent_level": 1, "formula": "TB('2801','期末余额')"},
        {"row_code": "BS-066", "row_number": 66, "row_name": "递延收益", "indent_level": 1, "formula": "TB('2811','期末余额')"},
        {"row_code": "BS-067", "row_number": 67, "row_name": "递延所得税负债", "indent_level": 1, "formula": "TB('2901','期末余额')"},
        {"row_code": "BS-068", "row_number": 68, "row_name": "其他非流动负债", "indent_level": 1, "formula": "TB('2911','期末余额')"},
        {"row_code": "BS-069", "row_number": 69, "row_name": "非流动负债合计", "indent_level": 0, "formula": "ROW('BS-061') + ROW('BS-062') + ROW('BS-063') + ROW('BS-064') + ROW('BS-065') + ROW('BS-066') + ROW('BS-067') + ROW('BS-068')", "is_total_row": True},
        {"row_code": "BS-070", "row_number": 70, "row_name": "负债合计", "indent_level": 0, "formula": "ROW('BS-054') + ROW('BS-069')", "is_total_row": True},
    ])
    # ── 所有者权益 ──
    rows.extend([
        {"row_code": "BS-080", "row_number": 80, "row_name": "所有者权益：", "indent_level": 0, "formula": None},
        {"row_code": "BS-081", "row_number": 81, "row_name": "实收资本（或股本）", "indent_level": 1, "formula": "TB('4001','期末余额')"},
        {"row_code": "BS-082", "row_number": 82, "row_name": "其他权益工具", "indent_level": 1, "formula": "TB('4003','期末余额')"},
        {"row_code": "BS-083", "row_number": 83, "row_name": "资本公积", "indent_level": 1, "formula": "TB('4002','期末余额')"},
        {"row_code": "BS-084", "row_number": 84, "row_name": "减：库存股", "indent_level": 1, "formula": "TB('4005','期末余额')"},
        {"row_code": "BS-085", "row_number": 85, "row_name": "其他综合收益", "indent_level": 1, "formula": "TB('4102','期末余额')"},
        {"row_code": "BS-086", "row_number": 86, "row_name": "专项储备", "indent_level": 1, "formula": "TB('4103','期末余额')"},
        {"row_code": "BS-087", "row_number": 87, "row_name": "盈余公积", "indent_level": 1, "formula": "TB('4101','期末余额')"},
        {"row_code": "BS-088", "row_number": 88, "row_name": "未分配利润", "indent_level": 1, "formula": "TB('4104','期末余额')"},
    ])
    if is_consolidated:
        rows.extend([
            {"row_code": "BS-089", "row_number": 89, "row_name": "归属于母公司所有者权益合计", "indent_level": 0, "formula": "ROW('BS-081') + ROW('BS-082') + ROW('BS-083') - ROW('BS-084') + ROW('BS-085') + ROW('BS-086') + ROW('BS-087') + ROW('BS-088')", "is_total_row": True},
            {"row_code": "BS-090", "row_number": 90, "row_name": "少数股东权益", "indent_level": 1, "formula": "TB('4201','期末余额')"},
            {"row_code": "BS-091", "row_number": 91, "row_name": "所有者权益合计", "indent_level": 0, "formula": "ROW('BS-089') + ROW('BS-090')", "is_total_row": True},
        ])
    else:
        rows.append({"row_code": "BS-089", "row_number": 89, "row_name": "所有者权益合计", "indent_level": 0, "formula": "ROW('BS-081') + ROW('BS-082') + ROW('BS-083') - ROW('BS-084') + ROW('BS-085') + ROW('BS-086') + ROW('BS-087') + ROW('BS-088')", "is_total_row": True})
        rows.append({"row_code": "BS-091", "row_number": 91, "row_name": "所有者权益合计", "indent_level": 0, "formula": "ROW('BS-089')", "is_total_row": True})

    equity_total_code = "BS-091"
    rows.append({"row_code": "BS-099", "row_number": 99, "row_name": "负债和所有者权益总计", "indent_level": 0, "formula": f"ROW('BS-070') + ROW('{equity_total_code}')", "is_total_row": True})

    # 补全默认字段
    for r in rows:
        r.setdefault("is_total_row", False)
        r.setdefault("parent_row_code", None)
    return rows


# ═══════════════════════════════════════════════════════════════════
# 利润表行次
# ═══════════════════════════════════════════════════════════════════

def _is_rows(is_consolidated: bool, is_listed: bool) -> list[dict]:
    """生成利润表行次"""
    rows = [
        {"row_code": "IS-001", "row_number": 1, "row_name": "一、营业收入", "indent_level": 0, "formula": "SUM_TB('6001~6099','本期发生额')"},
        {"row_code": "IS-002", "row_number": 2, "row_name": "减：营业成本", "indent_level": 1, "formula": "SUM_TB('6401~6499','本期发生额')"},
        {"row_code": "IS-003", "row_number": 3, "row_name": "税金及附加", "indent_level": 1, "formula": "TB('6403','本期发生额')"},
        {"row_code": "IS-004", "row_number": 4, "row_name": "销售费用", "indent_level": 1, "formula": "TB('6601','本期发生额')"},
        {"row_code": "IS-005", "row_number": 5, "row_name": "管理费用", "indent_level": 1, "formula": "TB('6602','本期发生额')"},
        {"row_code": "IS-006", "row_number": 6, "row_name": "研发费用", "indent_level": 1, "formula": "TB('6604','本期发生额')"},
        {"row_code": "IS-007", "row_number": 7, "row_name": "财务费用", "indent_level": 1, "formula": "TB('6603','本期发生额')"},
        {"row_code": "IS-008", "row_number": 8, "row_name": "其中：利息费用", "indent_level": 2, "formula": None},
        {"row_code": "IS-009", "row_number": 9, "row_name": "利息收入", "indent_level": 2, "formula": None},
        {"row_code": "IS-010", "row_number": 10, "row_name": "加：其他收益", "indent_level": 1, "formula": "TB('6117','本期发生额')"},
        {"row_code": "IS-011", "row_number": 11, "row_name": "投资收益", "indent_level": 1, "formula": "TB('6111','本期发生额')"},
        {"row_code": "IS-012", "row_number": 12, "row_name": "其中：对联营企业和合营企业的投资收益", "indent_level": 2, "formula": None},
        {"row_code": "IS-013", "row_number": 13, "row_name": "以摊余成本计量的金融资产终止确认收益", "indent_level": 2, "formula": None},
        {"row_code": "IS-014", "row_number": 14, "row_name": "净敞口套期收益", "indent_level": 1, "formula": None},
        {"row_code": "IS-015", "row_number": 15, "row_name": "公允价值变动收益", "indent_level": 1, "formula": "TB('6101','本期发生额')"},
        {"row_code": "IS-016", "row_number": 16, "row_name": "信用减值损失", "indent_level": 1, "formula": "TB('6701','本期发生额')"},
        {"row_code": "IS-017", "row_number": 17, "row_name": "资产减值损失", "indent_level": 1, "formula": "TB('6702','本期发生额')"},
        {"row_code": "IS-018", "row_number": 18, "row_name": "资产处置收益", "indent_level": 1, "formula": "TB('6115','本期发生额')"},
        {"row_code": "IS-019", "row_number": 19, "row_name": "二、营业利润", "indent_level": 0, "formula": "ROW('IS-001') - ROW('IS-002') - ROW('IS-003') - ROW('IS-004') - ROW('IS-005') - ROW('IS-006') - ROW('IS-007') + ROW('IS-010') + ROW('IS-011') + ROW('IS-015') + ROW('IS-016') + ROW('IS-017') + ROW('IS-018')", "is_total_row": True},
        {"row_code": "IS-020", "row_number": 20, "row_name": "加：营业外收入", "indent_level": 1, "formula": "TB('6301','本期发生额')"},
        {"row_code": "IS-021", "row_number": 21, "row_name": "减：营业外支出", "indent_level": 1, "formula": "TB('6711','本期发生额')"},
        {"row_code": "IS-022", "row_number": 22, "row_name": "三、利润总额", "indent_level": 0, "formula": "ROW('IS-019') + ROW('IS-020') - ROW('IS-021')", "is_total_row": True},
        {"row_code": "IS-023", "row_number": 23, "row_name": "减：所得税费用", "indent_level": 1, "formula": "TB('6801','本期发生额')"},
        {"row_code": "IS-024", "row_number": 24, "row_name": "四、净利润", "indent_level": 0, "formula": "ROW('IS-022') - ROW('IS-023')", "is_total_row": True},
    ]
    if is_consolidated:
        rows.extend([
            {"row_code": "IS-025", "row_number": 25, "row_name": "（一）归属于母公司所有者的净利润", "indent_level": 1, "formula": None},
            {"row_code": "IS-026", "row_number": 26, "row_name": "（二）少数股东损益", "indent_level": 1, "formula": None},
        ])
    # 其他综合收益
    rows.extend([
        {"row_code": "IS-030", "row_number": 30, "row_name": "五、其他综合收益的税后净额", "indent_level": 0, "formula": None},
        {"row_code": "IS-031", "row_number": 31, "row_name": "六、综合收益总额", "indent_level": 0, "formula": "ROW('IS-024') + ROW('IS-030')", "is_total_row": True},
    ])
    if is_consolidated:
        rows.extend([
            {"row_code": "IS-032", "row_number": 32, "row_name": "（一）归属于母公司所有者的综合收益总额", "indent_level": 1, "formula": None},
            {"row_code": "IS-033", "row_number": 33, "row_name": "（二）归属于少数股东的综合收益总额", "indent_level": 1, "formula": None},
        ])
    if is_listed:
        rows.extend([
            {"row_code": "IS-040", "row_number": 40, "row_name": "七、每股收益：", "indent_level": 0, "formula": None},
            {"row_code": "IS-041", "row_number": 41, "row_name": "（一）基本每股收益（元/股）", "indent_level": 1, "formula": None},
            {"row_code": "IS-042", "row_number": 42, "row_name": "（二）稀释每股收益（元/股）", "indent_level": 1, "formula": None},
        ])
    for r in rows:
        r.setdefault("is_total_row", False)
        r.setdefault("parent_row_code", None)
    return rows


# ═══════════════════════════════════════════════════════════════════
# 现金流量表行次（简化版，CFS 通常手工编制）
# ═══════════════════════════════════════════════════════════════════

def _cfs_rows(is_consolidated: bool, is_listed: bool) -> list[dict]:
    """生成现金流量表行次"""
    rows = [
        {"row_code": "CFS-001", "row_number": 1, "row_name": "一、经营活动产生的现金流量：", "indent_level": 0, "formula": None},
        {"row_code": "CFS-002", "row_number": 2, "row_name": "销售商品、提供劳务收到的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-003", "row_number": 3, "row_name": "收到的税费返还", "indent_level": 1, "formula": None},
        {"row_code": "CFS-004", "row_number": 4, "row_name": "收到其他与经营活动有关的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-005", "row_number": 5, "row_name": "经营活动现金流入小计", "indent_level": 0, "formula": "ROW('CFS-002') + ROW('CFS-003') + ROW('CFS-004')", "is_total_row": True},
        {"row_code": "CFS-006", "row_number": 6, "row_name": "购买商品、接受劳务支付的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-007", "row_number": 7, "row_name": "支付给职工以及为职工支付的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-008", "row_number": 8, "row_name": "支付的各项税费", "indent_level": 1, "formula": None},
        {"row_code": "CFS-009", "row_number": 9, "row_name": "支付其他与经营活动有关的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-010", "row_number": 10, "row_name": "经营活动现金流出小计", "indent_level": 0, "formula": "ROW('CFS-006') + ROW('CFS-007') + ROW('CFS-008') + ROW('CFS-009')", "is_total_row": True},
        {"row_code": "CFS-011", "row_number": 11, "row_name": "经营活动产生的现金流量净额", "indent_level": 0, "formula": "ROW('CFS-005') - ROW('CFS-010')", "is_total_row": True},
        {"row_code": "CFS-020", "row_number": 20, "row_name": "二、投资活动产生的现金流量：", "indent_level": 0, "formula": None},
        {"row_code": "CFS-021", "row_number": 21, "row_name": "收回投资收到的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-022", "row_number": 22, "row_name": "取得投资收益收到的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-023", "row_number": 23, "row_name": "处置固定资产、无形资产和其他长期资产收回的现金净额", "indent_level": 1, "formula": None},
        {"row_code": "CFS-024", "row_number": 24, "row_name": "收到其他与投资活动有关的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-025", "row_number": 25, "row_name": "投资活动现金流入小计", "indent_level": 0, "formula": "ROW('CFS-021') + ROW('CFS-022') + ROW('CFS-023') + ROW('CFS-024')", "is_total_row": True},
        {"row_code": "CFS-026", "row_number": 26, "row_name": "购建固定资产、无形资产和其他长期资产支付的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-027", "row_number": 27, "row_name": "投资支付的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-028", "row_number": 28, "row_name": "支付其他与投资活动有关的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-029", "row_number": 29, "row_name": "投资活动现金流出小计", "indent_level": 0, "formula": "ROW('CFS-026') + ROW('CFS-027') + ROW('CFS-028')", "is_total_row": True},
        {"row_code": "CFS-030", "row_number": 30, "row_name": "投资活动产生的现金流量净额", "indent_level": 0, "formula": "ROW('CFS-025') - ROW('CFS-029')", "is_total_row": True},
        {"row_code": "CFS-040", "row_number": 40, "row_name": "三、筹资活动产生的现金流量：", "indent_level": 0, "formula": None},
        {"row_code": "CFS-041", "row_number": 41, "row_name": "吸收投资收到的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-042", "row_number": 42, "row_name": "取得借款收到的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-043", "row_number": 43, "row_name": "收到其他与筹资活动有关的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-044", "row_number": 44, "row_name": "筹资活动现金流入小计", "indent_level": 0, "formula": "ROW('CFS-041') + ROW('CFS-042') + ROW('CFS-043')", "is_total_row": True},
        {"row_code": "CFS-045", "row_number": 45, "row_name": "偿还债务支付的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-046", "row_number": 46, "row_name": "分配股利、利润或偿付利息支付的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-047", "row_number": 47, "row_name": "支付其他与筹资活动有关的现金", "indent_level": 1, "formula": None},
        {"row_code": "CFS-048", "row_number": 48, "row_name": "筹资活动现金流出小计", "indent_level": 0, "formula": "ROW('CFS-045') + ROW('CFS-046') + ROW('CFS-047')", "is_total_row": True},
        {"row_code": "CFS-049", "row_number": 49, "row_name": "筹资活动产生的现金流量净额", "indent_level": 0, "formula": "ROW('CFS-044') - ROW('CFS-048')", "is_total_row": True},
        {"row_code": "CFS-050", "row_number": 50, "row_name": "四、汇率变动对现金及现金等价物的影响", "indent_level": 0, "formula": None},
        {"row_code": "CFS-051", "row_number": 51, "row_name": "五、现金及现金等价物净增加额", "indent_level": 0, "formula": "ROW('CFS-011') + ROW('CFS-030') + ROW('CFS-049') + ROW('CFS-050')", "is_total_row": True},
        {"row_code": "CFS-052", "row_number": 52, "row_name": "加：期初现金及现金等价物余额", "indent_level": 1, "formula": None},
        {"row_code": "CFS-053", "row_number": 53, "row_name": "六、期末现金及现金等价物余额", "indent_level": 0, "formula": "ROW('CFS-051') + ROW('CFS-052')", "is_total_row": True},
    ]
    for r in rows:
        r.setdefault("is_total_row", False)
        r.setdefault("parent_row_code", None)
    return rows


# ═══════════════════════════════════════════════════════════════════
# 权益变动表行次
# ═══════════════════════════════════════════════════════════════════

def _eq_rows(is_consolidated: bool, is_listed: bool) -> list[dict]:
    """生成权益变动表行次（列为科目，行为变动项目）"""
    rows = [
        {"row_code": "EQ-001", "row_number": 1, "row_name": "一、上期期末余额", "indent_level": 0, "formula": None},
        {"row_code": "EQ-002", "row_number": 2, "row_name": "加：会计政策变更", "indent_level": 1, "formula": None},
        {"row_code": "EQ-003", "row_number": 3, "row_name": "前期差错更正", "indent_level": 1, "formula": None},
        {"row_code": "EQ-004", "row_number": 4, "row_name": "二、本期期初余额", "indent_level": 0, "formula": "ROW('EQ-001') + ROW('EQ-002') + ROW('EQ-003')", "is_total_row": True},
        {"row_code": "EQ-005", "row_number": 5, "row_name": "三、本期增减变动金额：", "indent_level": 0, "formula": None},
        {"row_code": "EQ-006", "row_number": 6, "row_name": "（一）综合收益总额", "indent_level": 1, "formula": None},
        {"row_code": "EQ-007", "row_number": 7, "row_name": "（二）所有者投入和减少资本", "indent_level": 1, "formula": None},
        {"row_code": "EQ-008", "row_number": 8, "row_name": "1.所有者投入的普通股", "indent_level": 2, "formula": None},
        {"row_code": "EQ-009", "row_number": 9, "row_name": "2.其他权益工具持有者投入资本", "indent_level": 2, "formula": None},
        {"row_code": "EQ-010", "row_number": 10, "row_name": "3.股份支付计入所有者权益的金额", "indent_level": 2, "formula": None},
        {"row_code": "EQ-011", "row_number": 11, "row_name": "（三）利润分配", "indent_level": 1, "formula": None},
        {"row_code": "EQ-012", "row_number": 12, "row_name": "1.提取盈余公积", "indent_level": 2, "formula": None},
        {"row_code": "EQ-013", "row_number": 13, "row_name": "2.对所有者（或股东）的分配", "indent_level": 2, "formula": None},
        {"row_code": "EQ-014", "row_number": 14, "row_name": "（四）所有者权益内部结转", "indent_level": 1, "formula": None},
        {"row_code": "EQ-015", "row_number": 15, "row_name": "（五）专项储备", "indent_level": 1, "formula": None},
        {"row_code": "EQ-016", "row_number": 16, "row_name": "（六）其他", "indent_level": 1, "formula": None},
        {"row_code": "EQ-017", "row_number": 17, "row_name": "四、本期期末余额", "indent_level": 0, "formula": "ROW('EQ-004') + ROW('EQ-006') + ROW('EQ-007') + ROW('EQ-011') + ROW('EQ-014') + ROW('EQ-015') + ROW('EQ-016')", "is_total_row": True},
    ]
    for r in rows:
        r.setdefault("is_total_row", False)
        r.setdefault("parent_row_code", None)
    return rows


# ═══════════════════════════════════════════════════════════════════
# 主函数：生成 4 套报表
# ═══════════════════════════════════════════════════════════════════

def _categorize_formula(row: dict) -> None:
    """给每行自动添加公式分类、说明和来源标注。

    三类公式：
    - auto_calc: 自动运算（从试算表取数或行次求和）
    - logic_check: 逻辑审核（平衡校验、勾稽关系）
    - reasonability: 提示合理性（变动率异常、占比异常）
    """
    formula = row.get("formula")
    if not formula:
        row["formula_category"] = None
        row["formula_description"] = None
        row["formula_source"] = None
        return

    # 分类逻辑
    if "TB(" in formula or "SUM_TB(" in formula:
        row["formula_category"] = "auto_calc"
        row["formula_source"] = "试算表审定数"
        # 生成说明
        if "SUM_TB(" in formula:
            row["formula_description"] = "从试算表按科目范围汇总期末余额"
        elif " + " in formula or " - " in formula:
            row["formula_description"] = "从试算表取多个科目余额合计"
        else:
            row["formula_description"] = "从试算表取单科目期末余额"
    elif "ROW(" in formula:
        row["formula_category"] = "auto_calc"
        row["formula_source"] = "报表行次引用"
        if row.get("is_total_row"):
            row["formula_description"] = "合计行：引用上方明细行求和"
        else:
            row["formula_description"] = "引用其他报表行次计算"
    else:
        row["formula_category"] = "auto_calc"
        row["formula_source"] = "自定义公式"
        row["formula_description"] = "自定义计算公式"

    # 特殊行的逻辑审核标记
    row_name = row.get("row_name", "")
    if "合计" in row_name or "总计" in row_name:
        # 合计行同时具有逻辑审核属性（验证子项之和=合计）
        pass  # 保持 auto_calc，逻辑审核在校验引擎中处理


def generate_all() -> list[dict]:
    """生成致同标准 4 套报表种子数据"""
    configs = [
        ("soe", "consolidated", True, False),
        ("soe", "standalone", False, False),
        ("listed", "consolidated", True, True),
        ("listed", "standalone", False, True),
    ]

    result = []
    for variant, scope, is_consol, is_listed in configs:
        standard = f"{variant}_{scope}"
        for report_type, gen_fn in [
            ("balance_sheet", _bs_rows),
            ("income_statement", _is_rows),
            ("cash_flow_statement", _cfs_rows),
            ("equity_change", _eq_rows),
        ]:
            rows = gen_fn(is_consol, is_listed)
            # 给每行添加公式分类
            for row in rows:
                _categorize_formula(row)
            result.append({
                "report_type": report_type,
                "applicable_standard": standard,
                "template_variant": variant,
                "scope": scope,
                "description": f"{report_type} — 致同{'国企' if variant == 'soe' else '上市'}版{'合并' if is_consol else '单体'}",
                "rows": rows,
            })

    return result


if __name__ == "__main__":
    data = generate_all()
    total_rows = sum(len(block["rows"]) for block in data)
    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ 生成完成: {OUTPUT_PATH}")
    print(f"   {len(data)} 个报表配置块（4套×4张）")
    print(f"   共 {total_rows} 行报表行次")
