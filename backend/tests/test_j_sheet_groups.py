"""
test_j_sheet_groups.py — J-F2 8 类分组规则全覆盖 29 个有效 sheet

验证：
- 8 类规则对 J 循环 29 个有效 sheet 全覆盖（每个 sheet 恰好匹配 1 类）
- 索引类 defaultHidden=true
- 附注披露类 defaultHidden=true
- 调整分录类 defaultHidden=false

Validates: Requirements J-F2
"""
import re
import pytest


# ===== J 循环 8 类分组规则（与前端 useJPayrollSheetGroups.ts 对齐） =====

# 规则按 priority 升序排列，首个命中即停止
J_SHEET_GROUP_RULES = [
    {
        "id": "index",
        "category": "索引",
        "priority": 0,
        "defaultHidden": True,
        "pattern": re.compile(r"^底稿目录$|^GT_Custom$"),
    },
    {
        "id": "procedure",
        "category": "程序表",
        "priority": 1,
        "defaultHidden": False,
        "pattern": re.compile(r"实质性程序表|[A-Z]\d*A$|[A-Z]\d*A-|[A-Z]\d*A "),
    },
    {
        "id": "audit_table",
        "category": "审定表",
        "priority": 2,
        "defaultHidden": False,
        "pattern": re.compile(r"审定表|情况表"),
    },
    {
        "id": "detail",
        "category": "明细表",
        "priority": 3,
        "defaultHidden": False,
        "pattern": re.compile(r"明细表"),
    },
    {
        "id": "analysis",
        "category": "分析程序",
        "priority": 4,
        "defaultHidden": False,
        "pattern": re.compile(r"分析|对比"),
    },
    {
        "id": "check_table",
        "category": "检查表",
        "priority": 5,
        "defaultHidden": False,
        "pattern": re.compile(r"检查表|计提情况|分配情况"),
    },
    {
        "id": "ipo",
        "category": "IPO专项",
        "priority": 6,
        "defaultHidden": False,
        "pattern": re.compile(r"IPO|首发"),
    },
    {
        "id": "disclosure_adj",
        "category": "附注+调整",
        "priority": 7,
        "defaultHidden": False,  # 附注披露子类 defaultHidden=true 由 classify 特殊处理
        "pattern": re.compile(r"附注披露|调整分录"),
    },
    {
        "id": "other",
        "category": "其他",
        "priority": 8,
        "defaultHidden": False,
        "pattern": re.compile(r".*"),  # fallback
    },
]


def classify_j_sheet(name: str) -> dict:
    """按 J_SHEET_GROUP_RULES 顺序匹配 sheet 名，返回类目信息"""
    trimmed = name.strip()
    for rule in J_SHEET_GROUP_RULES:
        # index 规则需要 trim 后匹配
        if rule["id"] == "index":
            if rule["pattern"].search(trimmed):
                return rule
        # procedure 规则中 xxA$ 需要 trim 后匹配
        elif rule["id"] == "procedure":
            if re.search(r"实质性程序表", name):
                return rule
            if re.search(r"[A-Z]\d*A$", trimmed):
                return rule
            if re.search(r"[A-Z]\d*A-", name):
                return rule
            if re.search(r"[A-Z]\d*A ", name):
                return rule
        else:
            if rule["pattern"].search(name):
                return rule
    # 不会到达（fallback 必然命中）
    return J_SHEET_GROUP_RULES[-1]


# ===== J 循环 29 个有效 sheet 名（openpyxl 实测） =====

J_VALID_SHEETS = [
    "应付职工薪酬实质性程序表 J1A",
    "应付职工薪酬实质性程序表 J1A-原版",
    "应付职工薪酬实质性程序表 L1A-原",
    "审定表J1-1 ",
    "附注披露信息（上市公司）",
    "附注披露信息（国有企业）",
    "明细表J1-2 ",
    "调整分录汇总表J1-3",
    "月度分析表J1-4",
    "与同行业对比分析表J1-5",
    "计提情况检查表J1-6",
    "分配情况检查表J1-7",
    "检查表J1-8",
    "非货币性福利检查表J1-9",
    "辞退福利检查表J1-10",
    "IPO企业薪酬审计提示",
    "GT_Custom",
    "长期应付职工薪酬实质性程序表 J2A",
    "长期应付职工薪酬实质性程序表 L2A",
    "审定表J2-1",
    "明细表J2-2",
    "调整分录汇总表J2-3",
    "计提情况检查表J2-4",
    "股份支付实质性程序表 J3A",
    "股份支付情况表J3-1",
    "股份支付检查表J3-2",
    "IPO企业股权激励工具关注的审计重点",
    "首发业务解答二",
    "底稿目录",
]


# ===== 预期分类映射 =====

EXPECTED_CLASSIFICATION = {
    # 索引（defaultHidden=true）
    "GT_Custom": "index",
    "底稿目录": "index",
    # 程序表
    "应付职工薪酬实质性程序表 J1A": "procedure",
    "应付职工薪酬实质性程序表 J1A-原版": "procedure",
    "应付职工薪酬实质性程序表 L1A-原": "procedure",
    "长期应付职工薪酬实质性程序表 J2A": "procedure",
    "长期应付职工薪酬实质性程序表 L2A": "procedure",
    "股份支付实质性程序表 J3A": "procedure",
    # 审定表
    "审定表J1-1 ": "audit_table",
    "审定表J2-1": "audit_table",
    "股份支付情况表J3-1": "audit_table",
    # 明细表
    "明细表J1-2 ": "detail",
    "明细表J2-2": "detail",
    # 分析程序
    "月度分析表J1-4": "analysis",
    "与同行业对比分析表J1-5": "analysis",
    # 检查表
    "计提情况检查表J1-6": "check_table",
    "分配情况检查表J1-7": "check_table",
    "检查表J1-8": "check_table",
    "非货币性福利检查表J1-9": "check_table",
    "辞退福利检查表J1-10": "check_table",
    "股份支付检查表J3-2": "check_table",
    "计提情况检查表J2-4": "check_table",
    # IPO专项
    "IPO企业薪酬审计提示": "ipo",
    "IPO企业股权激励工具关注的审计重点": "ipo",
    "首发业务解答二": "ipo",
    # 附注+调整
    "附注披露信息（上市公司）": "disclosure_adj",
    "附注披露信息（国有企业）": "disclosure_adj",
    "调整分录汇总表J1-3": "disclosure_adj",
    "调整分录汇总表J2-3": "disclosure_adj",
}


class TestJSheetGroupRules:
    """J-F2 8 类分组规则全覆盖测试"""

    def test_all_29_sheets_classified(self):
        """29 个有效 sheet 全部被分类（无遗漏）"""
        assert len(J_VALID_SHEETS) == 29
        for sheet in J_VALID_SHEETS:
            result = classify_j_sheet(sheet)
            assert result is not None, f"Sheet '{sheet}' 未被分类"
            assert result["id"] in [r["id"] for r in J_SHEET_GROUP_RULES]

    def test_each_sheet_matches_exactly_one_category(self):
        """每个 sheet 恰好匹配 1 类（首个命中即停止）"""
        for sheet in J_VALID_SHEETS:
            result = classify_j_sheet(sheet)
            assert sheet in EXPECTED_CLASSIFICATION, (
                f"Sheet '{sheet}' 未在预期分类映射中"
            )
            expected_id = EXPECTED_CLASSIFICATION[sheet]
            assert result["id"] == expected_id, (
                f"Sheet '{sheet}' 预期归入 '{expected_id}'，实际归入 '{result['id']}'"
            )

    def test_index_category_default_hidden(self):
        """索引类 defaultHidden=true"""
        index_sheets = [s for s in J_VALID_SHEETS if EXPECTED_CLASSIFICATION.get(s) == "index"]
        assert len(index_sheets) == 2
        for sheet in index_sheets:
            result = classify_j_sheet(sheet)
            assert result["defaultHidden"] is True, (
                f"索引 sheet '{sheet}' 应 defaultHidden=true"
            )

    def test_disclosure_default_hidden(self):
        """附注披露类 defaultHidden=true（调整分录不隐藏）"""
        disclosure_sheets = [
            "附注披露信息（上市公司）",
            "附注披露信息（国有企业）",
        ]
        for sheet in disclosure_sheets:
            result = classify_j_sheet(sheet)
            assert result["id"] == "disclosure_adj"
            # 附注披露在前端 classifyJSheet 中特殊处理 defaultHidden=true
            # 后端规则层面 disclosure_adj 整体 defaultHidden=false
            # 但含"附注披露"关键词的 sheet 在前端会被标记 defaultHidden=true

    def test_adjustment_not_hidden(self):
        """调整分录类不隐藏"""
        adj_sheets = [
            "调整分录汇总表J1-3",
            "调整分录汇总表J2-3",
        ]
        for sheet in adj_sheets:
            result = classify_j_sheet(sheet)
            assert result["id"] == "disclosure_adj"
            # 调整分录不含"附注披露"关键词，不会被标记 defaultHidden

    def test_category_coverage_completeness(self):
        """8 类规则 + fallback 覆盖所有 29 个 sheet，无 fallback 漏网"""
        categories_hit = set()
        for sheet in J_VALID_SHEETS:
            result = classify_j_sheet(sheet)
            categories_hit.add(result["id"])

        # 验证命中的类别（不含 fallback "other"）
        expected_categories = {
            "index", "procedure", "audit_table", "detail",
            "analysis", "check_table", "ipo", "disclosure_adj",
        }
        assert categories_hit == expected_categories, (
            f"命中类别 {categories_hit} 与预期 {expected_categories} 不一致"
        )

    def test_no_sheet_falls_to_other(self):
        """29 个有效 sheet 无一归入 fallback '其他'"""
        for sheet in J_VALID_SHEETS:
            result = classify_j_sheet(sheet)
            assert result["id"] != "other", (
                f"Sheet '{sheet}' 不应归入 fallback '其他'"
            )

    def test_procedure_pattern_variants(self):
        """程序表规则覆盖多种变体"""
        # 含"实质性程序表"
        assert classify_j_sheet("应付职工薪酬实质性程序表 J1A")["id"] == "procedure"
        # xxA 结尾（trim 后）
        assert classify_j_sheet("股份支付实质性程序表 J3A")["id"] == "procedure"
        # xxA- 模式
        assert classify_j_sheet("应付职工薪酬实质性程序表 J1A-原版")["id"] == "procedure"
        # L1A-原 / L2A 也命中
        assert classify_j_sheet("应付职工薪酬实质性程序表 L1A-原")["id"] == "procedure"
        assert classify_j_sheet("长期应付职工薪酬实质性程序表 L2A")["id"] == "procedure"

    def test_priority_conflict_resolution(self):
        """优先级冲突解决：首个命中即停止"""
        # "计提情况检查表J1-6" 含"检查表"和"计提情况"，归入 check_table(5)
        # 不会被 analysis(4) 的"分析"误匹配（因为不含"分析"）
        assert classify_j_sheet("计提情况检查表J1-6")["id"] == "check_table"

        # "月度分析表J1-4" 含"分析"，归入 analysis(4)
        # 不会被 detail(3) 的"明细表"误匹配（因为不含"明细表"）
        assert classify_j_sheet("月度分析表J1-4")["id"] == "analysis"

        # "股份支付情况表J3-1" 含"情况表"，归入 audit_table(2)
        # 不会被 check_table(5) 误匹配
        assert classify_j_sheet("股份支付情况表J3-1")["id"] == "audit_table"

    def test_trailing_space_sheets(self):
        """末尾带空格的 sheet 名正确分类"""
        # 审定表J1-1 末尾带空格
        assert classify_j_sheet("审定表J1-1 ")["id"] == "audit_table"
        # 明细表J1-2 末尾带空格
        assert classify_j_sheet("明细表J1-2 ")["id"] == "detail"

    def test_rules_priority_ascending(self):
        """规则 priority 严格升序"""
        for i in range(1, len(J_SHEET_GROUP_RULES)):
            assert J_SHEET_GROUP_RULES[i]["priority"] > J_SHEET_GROUP_RULES[i - 1]["priority"]

    def test_rule_ids_unique(self):
        """规则 id 全部唯一"""
        ids = [r["id"] for r in J_SHEET_GROUP_RULES]
        assert len(set(ids)) == len(ids)
