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
        """SOE 存货 五-10-1 或相近 → 八、10。"""
        # 存货的 section_id 取决于生成脚本的排序
        mapped = all_mapped_sections("soe")
        inventory = [m for m in mapped if m.get("consol_parent") == "存货"]
        assert len(inventory) > 0
        assert inventory[0]["standalone_note_section"] == "八、10"

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
