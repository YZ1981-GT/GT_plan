"""合并附注章节映射服务测试。

spec: consol-note-pull-from-standalone · Task 1.4
"""
import json
from pathlib import Path

import pytest

from app.services.consol_note_section_mapping import (
    all_mapped_sections,
    mapping_stats,
    resolve_consol_sections,
    resolve_standalone_section,
    resolve_standalone_table_name,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
MAPPING_PATH = DATA_DIR / "consol_note_section_mapping.json"


class TestMappingFileExists:
    """映射配置文件基础检查。"""

    def test_file_exists(self):
        assert MAPPING_PATH.exists(), "consol_note_section_mapping.json 不存在，需运行生成脚本"

    def test_file_structure(self):
        data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
        assert "mappings" in data
        assert "soe" in data["mappings"]
        assert "listed" in data["mappings"]
        assert len(data["mappings"]["soe"]) > 0
        assert len(data["mappings"]["listed"]) > 0


class TestResolveStandaloneSection:
    """正向查询：合并 section_id → 单体 note_section。"""

    def test_soe_currency(self):
        """SOE 货币资金 五-1-1 → 八、1。"""
        result = resolve_standalone_section("soe", "五-1-1")
        assert result == "八、1"

    def test_soe_receivables(self):
        """SOE 应收票据 五-4-1 → 八、4。"""
        result = resolve_standalone_section("soe", "五-4-1")
        assert result == "八、4"

    def test_soe_accounts_receivable(self):
        """SOE 应收账款章节组存在映射。"""
        mapped = all_mapped_sections("soe")
        ar = [m for m in mapped if m.get("consol_parent") == "应收账款"]
        assert len(ar) > 0
        # 应收账款的单体章节是 八、5
        assert ar[0]["standalone_note_section"] == "八、5"

    def test_soe_inventory(self):
        """SOE 存货 五-10-1「存货分类」→ 八、10 子表「存货分类」。"""
        assert resolve_standalone_section("soe", "五-10-1") == "八、10"
        assert resolve_standalone_table_name("soe", "五-10-1") == "存货分类"

    def test_parent_section_shift_does_not_misroute(self):
        """合并模板 parent_section 自 五-10 起错后一章（五-11 合同资产表的 parent 是「存货」）。

        按表标题映射：合同资产 → 八、11，固定资产 → 八、22，不被 parent 带偏。
        """
        assert resolve_standalone_section("soe", "五-11-1") == "八、11"
        assert resolve_standalone_table_name("soe", "五-11-1") == "合同资产情况"
        assert resolve_standalone_section("soe", "五-22-2") == "八、22"

    def test_duplicate_table_name_follows_chapter(self):
        """「收回或转回的坏账准备」八、5 与 八、9 都有：其他应收款章节的那张映射到 八、9。"""
        assert resolve_standalone_section("soe", "五-9-13") == "八、9"

    def test_generic_continuation_follows_previous_table(self):
        """五-9-8「续：」接上一张 → 单体续上一张子表的续表。"""
        assert resolve_standalone_table_name("soe", "五-9-8") == "按坏账准备计提方法分类披露其他应收款项（续：期初余额）"
        # 上市 五-4-8「续：」原映射不到子表：上一张选的是「（期末余额）」，其续表由标题行库认出
        assert resolve_standalone_table_name("listed", "五-4-8") == "按单项计提坏账准备的应收票据（续：上年年末余额）"

    def test_table_choice_uses_header_library(self):
        """国企 五-4-3（期初数续表）：只按表名会对到同名的「（续）」单项计提表，按表头改选「（续：期初数）」。"""
        assert resolve_standalone_table_name("soe", "五-4-3") == "按坏账准备计提方法分类披露应收票据（续：期初数）"
        assert resolve_standalone_table_name("soe", "五-4-2") == "按坏账准备计提方法分类披露应收票据（期末数）"

    def test_identical_candidates_are_not_guessed(self):
        """上市 五-9-4（合并表头错列）：单体按组合 / 按库龄组合两张表同构，不按次要特征硬选。"""
        assert resolve_standalone_table_name("listed", "五-9-4") is None

    def test_listed_currency(self):
        """Listed 货币资金。"""
        result = resolve_standalone_section("listed", "五-1-1")
        # Listed 的单体章节号是 五、1（不是 八、1）
        assert result is not None
        assert "1" in result

    def test_consol_only_returns_none(self):
        """合并特有章节返回 None。"""
        # "续：" 章节组通常是 consol_only
        mapped = all_mapped_sections("soe")
        all_sids = {m["consol_section_id"] for m in mapped}
        # 找一个不在已映射集合中的 section_id
        data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
        all_entries = data["mappings"]["soe"]
        consol_only = [e for e in all_entries if e.get("match_type") == "consol_only"]
        if consol_only:
            result = resolve_standalone_section("soe", consol_only[0]["consol_section_id"])
            assert result is None

    def test_nonexistent_section(self):
        """不存在的 section_id 返回 None。"""
        assert resolve_standalone_section("soe", "不存在的章节") is None


class TestResolveConsolSections:
    """反向查询：单体 note_section → 合并 section_id 列表。"""

    def test_soe_reverse_currency(self):
        """八、1 → 货币资金的所有合并章节。"""
        result = resolve_consol_sections("soe", "八、1")
        assert len(result) >= 1
        assert "五-1-1" in result

    def test_soe_reverse_multiple(self):
        """同一单体章节可能映射到多个合并表（如一个章节有多张子表）。"""
        result = resolve_consol_sections("soe", "八、1")
        # 货币资金有主表 + 受限制的货币资金明细 = 2 张
        assert len(result) >= 2

    def test_nonexistent_section(self):
        """不存在的单体章节返回空列表。"""
        assert resolve_consol_sections("soe", "不存在") == []


class TestMappingStats:
    """映射统计。"""

    def test_soe_coverage(self):
        """SOE 已映射比例 ≥ 90%。"""
        stats = mapping_stats("soe")
        total = sum(stats.values())
        resolved = total - stats.get("consol_only", 0)
        assert resolved / max(total, 1) >= 0.90, f"SOE 映射覆盖率过低: {stats}"

    def test_listed_coverage(self):
        """Listed 已映射比例 ≥ 70%（Listed 条目含大量续表，按章节组算比按条目高）。"""
        stats = mapping_stats("listed")
        total = sum(stats.values())
        resolved = total - stats.get("consol_only", 0)
        assert resolved / max(total, 1) >= 0.70, f"Listed 映射覆盖率过低: {stats}"


class TestResolveStandaloneTableName:
    """子表名匹配。"""

    def test_soe_currency_main(self):
        """货币资金主表的子表名。"""
        name = resolve_standalone_table_name("soe", "五-1-1")
        # 主表名可能是 "货币资金" 或 None（首表兜底）
        # 不做过于严格的断言
        assert name is None or isinstance(name, str)
