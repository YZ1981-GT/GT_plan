"""单元测试：fix_note_per_table_guidance 纯迁移逻辑。

Feature: note-per-table-guidance (Phase 3 / 3.1 / 3.2)

只测纯函数（plan_section_changes / apply_plan_to_table_data / _already_migrated），
不依赖 DB。DB 路径（dry-run/execute/savepoint）需真实 PG，单独标注。
"""

from __future__ import annotations

import os
import sys

# Ensure backend app importable
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from scripts.fix.fix_note_per_table_guidance import (  # noqa: E402
    ORIG_BACKUP_KEY,
    SectionPlan,
    _already_migrated,
    apply_plan_to_table_data,
    plan_section_changes,
)


def _money_funds_row() -> dict:
    """货币资金（2 表）：tables[0] 含 注+提示，标题行推进到 tables[1]。"""
    text_content = (
        "（注：如有因抵押、质押或冻结等对使用有限制的款项，应在附注中披露。）\n"
        "（提示：企业持有的货币资金应按存放地点分类列示。）\n"
        "### 受限制的货币资金明细"
    )
    return {
        "note_section": "八、1",
        "text_content": text_content,
        "table_data": {
            "_tables": [
                {"name": "货币资金", "headers": ["项目", "期末余额"], "rows": []},
                {
                    "name": "受限制的货币资金明细",
                    "headers": ["项目", "期末余额"],
                    "rows": [],
                },
            ]
        },
    }


def test_money_funds_two_tables_guidance_to_table0():
    """货币资金：注+提示归 tables[0]，标题行移除推进到 tables[1]，tables[1] 无 guidance。"""
    plan = plan_section_changes(_money_funds_row())

    assert plan.has_changes
    # 标题行被识别为待移除
    assert any("受限制的货币资金明细" in t for t in plan.title_rows_removed)
    # 两条提示归到 tables[0]
    assert 0 in plan.per_table_guidance
    name0, g0 = plan.per_table_guidance[0]
    assert name0 == "货币资金"
    assert "注：" in g0 and "提示：" in g0
    # tables[1] 无 guidance（标题行后无提示段）
    assert 1 not in plan.per_table_guidance
    # 标题行不留在正文里
    assert plan.new_text_content is None or "###" not in plan.new_text_content


def test_apply_plan_writes_guidance_and_backup():
    """apply_plan：写 _tables[idx].guidance + tables[0] 行内备份原文。"""
    row = _money_funds_row()
    plan = plan_section_changes(row)
    table_data = dict(row["table_data"])

    apply_plan_to_table_data(table_data, plan)

    tables = table_data["_tables"]
    assert ORIG_BACKUP_KEY in tables[0]
    assert tables[0][ORIG_BACKUP_KEY] == row["text_content"]
    assert "注：" in tables[0]["guidance"]
    assert "guidance" not in tables[1]


def test_apply_plan_idempotent_backup_not_overwritten():
    """幂等：已有备份则不覆盖（二次 apply 不破坏原始备份）。"""
    row = _money_funds_row()
    plan = plan_section_changes(row)
    table_data = dict(row["table_data"])
    table_data["_tables"][0][ORIG_BACKUP_KEY] = "ORIGINAL_BACKUP"

    apply_plan_to_table_data(table_data, plan)

    assert table_data["_tables"][0][ORIG_BACKUP_KEY] == "ORIGINAL_BACKUP"


def test_already_migrated_detection():
    assert _already_migrated(
        {"_tables": [{"name": "x", ORIG_BACKUP_KEY: "old"}]}
    )
    assert not _already_migrated({"_tables": [{"name": "x"}]})
    assert not _already_migrated({})
    assert not _already_migrated(None)


def test_receivables_all_titles_no_guidance():
    """应收账款（多表，全短标题无 guidance）：各表 guidance 均为空，标题行全移除。

    注：标题用 ≤20 字短行，符合生产 `_is_table_title_paragraph` 判定。
    """
    text_content = (
        "（1）应收账款分类披露\n"
        "（2）按账龄披露\n"
        "#### 期末单项金额重大"
    )
    row = {
        "note_section": "八、5",
        "text_content": text_content,
        "table_data": {
            "_tables": [
                {"name": "应收账款分类", "headers": [], "rows": []},
                {"name": "按账龄披露", "headers": [], "rows": []},
                {"name": "期末单项金额重大", "headers": [], "rows": []},
            ]
        },
    }
    plan = plan_section_changes(row)

    # 全是标题行 → 无 per-table guidance，正文为空
    assert plan.per_table_guidance == {}
    assert plan.new_text_content is None
    assert len(plan.title_rows_removed) == 3


def test_long_hash_heading_IS_treated_as_title():
    """✅ 修复后行为：生产 `_is_table_title_paragraph` 先判 `#` 前缀再判 len>20，

    故任意长度的 `####` markdown 标题都被识别为标题行 → 从 text_content 移除。
    （此前先判 len>20 导致 >20 字的长标题漏判，已修正：`#` 前缀检测提到长度判定之前。）
    """
    long_heading = "#### 期末单项金额重大并单独计提坏账准备"  # 21 字 > 20
    row = {
        "note_section": "八、5b",
        "text_content": long_heading,
        "table_data": {
            "_tables": [
                {"name": "应收账款分类", "headers": [], "rows": []},
                {"name": "按账龄披露", "headers": [], "rows": []},
            ]
        },
    }
    plan = plan_section_changes(row)

    # 长 #### 标题现在被识别为标题行 → 移除，正文清空
    assert plan.new_text_content is None
    assert len(plan.title_rows_removed) == 1
    assert "期末单项金额重大" in plan.title_rows_removed[0]


def test_single_table_guidance_goes_section_level():
    """单表章节：guidance 走章节级（section_guidance），不进 per-table。"""
    row = {
        "note_section": "八、3",
        "text_content": (
            "（注：本项目期末余额按公允价值列示。）\n"
            "### 其他应收款"
        ),
        "table_data": {
            "_tables": [
                {"name": "其他应收款", "headers": [], "rows": []},
            ]
        },
    }
    plan = plan_section_changes(row)

    assert plan.per_table_guidance == {}
    assert plan.section_guidance is not None
    assert "注：" in plan.section_guidance


def test_substantive_text_retained():
    """实质正文（非提示非标题）保留在 text_content。"""
    row = {
        "note_section": "八、9",
        "text_content": (
            "### 长期股权投资\n"
            "本公司对子公司的长期股权投资采用成本法核算，"
            "在编制合并财务报表时按权益法调整。"
        ),
        "table_data": {
            "_tables": [
                {"name": "长期股权投资", "headers": [], "rows": []},
                {"name": "投资明细", "headers": [], "rows": []},
            ]
        },
    }
    plan = plan_section_changes(row)

    assert plan.new_text_content is not None
    assert "成本法核算" in plan.new_text_content
    assert "###" not in plan.new_text_content


def test_no_tables_structure_safe():
    """无 _tables 结构：plan 不崩，apply 也不崩（至少不抛异常）。"""
    row = {
        "note_section": "一、",
        "text_content": "### 某标题\n（注：提示文字）",
        "table_data": {},
    }
    plan = plan_section_changes(row)
    # 无表 → 单表/无表逻辑：提示归章节级
    assert isinstance(plan, SectionPlan)
    table_data: dict = {}
    apply_plan_to_table_data(table_data, plan)  # 不应抛异常
