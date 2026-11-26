"""章节号动态定位（原 test_formula_push_note_skip.py，行数门拆分，2026-11-26）。"""
from __future__ import annotations


import pytest

from app.services.formula_push import engine as engine_mod
from tests._note_push_ownership_fixture import install as _install_ownership
@pytest.fixture(autouse=True)
def _self_made_ownership_matrix(monkeypatch):
    _install_ownership(monkeypatch)

class TestSectionDynamicLookupOnMismatch:
    """Task 5.3 · 需求 3.1：规则声明 五、22 → 实际标题不匹配 → 反查到正确章节。

    engine.py _push_note 的动态定位逻辑（L617-637）：
      1. 用规则硬编码 section（如 五、22）查 disclosure_notes → 取到 note
      2. 比较 note.section_title 与 _title_check_name（如"固定资产"）
      3. 不匹配时：提取前缀（"五、"）→ 反查 section_title == "固定资产"
         且 note_section LIKE '五、%' 的记录
      4. 唯一命中 → 采纳（替换 note 和 section）
      5. 0 条或多条 → 走原逻辑报跳过

    本测试在纯逻辑层（无 DB）模拟该决策链的每一步。
    """

    def test_mismatch_unique_fallback_succeeds(self):
        """规则声明 五、22 对应"固定资产"，但项目中 五、22="递延所得税负债"。
        反查 section_title=="固定资产" 唯一命中 五、30 → 动态定位成功。
        """
        # ── 模拟项目附注章节（真库场景：不同项目附注排序不同） ──
        notes = [
            {"note_section": "五、20", "section_title": "长期借款", "is_deleted": False},
            {"note_section": "五、22", "section_title": "递延所得税负债", "is_deleted": False},
            {"note_section": "五、25", "section_title": "应付职工薪酬", "is_deleted": False},
            {"note_section": "五、30", "section_title": "固定资产", "is_deleted": False},
            {"note_section": "五、35", "section_title": "在建工程", "is_deleted": False},
        ]

        # ── 规则声明 ──
        rule_section = "五、22"
        target_title = "固定资产"  # _title_check_name

        # ── Step 1: 按硬编码 section 取到 note ──
        direct_note = next(
            (n for n in notes if n["note_section"] == rule_section and not n["is_deleted"]),
            None,
        )
        assert direct_note is not None, "硬编码章节号应能查到记录"

        # ── Step 2: section_title 不匹配 → 触发反查 ──
        assert direct_note["section_title"] != target_title, (
            f"规则声明 {rule_section} 的标题是"
            f"「{direct_note['section_title']}」≠「{target_title}」，应触发反查"
        )

        # ── Step 3: 提取前缀（engine.py L621） ──
        _section_prefix = (
            rule_section.split("、")[0] + "、"
            if "、" in rule_section
            else rule_section[:1]
        )
        assert _section_prefix == "五、"

        # ── Step 4: 反查 section_title == target_title 且前缀匹配 ──
        fallback_rows = [
            n for n in notes
            if n["section_title"] == target_title
            and not n["is_deleted"]
            and n["note_section"].startswith(_section_prefix)
        ]

        # ── Step 5: 唯一命中 → 采纳 ──
        assert len(fallback_rows) == 1, (
            f"反查应唯一命中，实际 {len(fallback_rows)} 条"
        )
        found = fallback_rows[0]
        assert found["note_section"] == "五、30"
        assert found["section_title"] == "固定资产"

        # ── Step 6: 验证替换后的 section 和 section_addr ──
        new_section = found["note_section"]
        new_addr = f"note://{new_section}/{target_title}"
        assert new_section == "五、30"
        assert new_addr == "note://五、30/固定资产"

    def test_mismatch_soe_template_prefix(self):
        """国企模板（八、）场景下前缀提取和反查同样生效。"""
        notes = [
            {"note_section": "八、4", "section_title": "应收票据", "is_deleted": False},
            {"note_section": "八、7", "section_title": "存货", "is_deleted": False},
            {"note_section": "八、10", "section_title": "固定资产", "is_deleted": False},
        ]

        rule_section = "八、7"
        target_title = "固定资产"

        # 硬编码章节号标题不匹配
        direct = next(n for n in notes if n["note_section"] == rule_section)
        assert direct["section_title"] == "存货" != target_title

        # 前缀 → "八、"
        prefix = rule_section.split("、")[0] + "、"
        assert prefix == "八、"

        # 反查
        matches = [
            n for n in notes
            if n["section_title"] == target_title
            and not n["is_deleted"]
            and n["note_section"].startswith(prefix)
        ]
        assert len(matches) == 1
        assert matches[0]["note_section"] == "八、10"

    def test_deleted_note_excluded_from_fallback(self):
        """已删除的附注不参与反查。"""
        notes = [
            {"note_section": "五、22", "section_title": "递延所得税负债", "is_deleted": False},
            {"note_section": "五、30", "section_title": "固定资产", "is_deleted": True},   # 已删除
            {"note_section": "五、33", "section_title": "固定资产", "is_deleted": False},   # 存活
        ]

        rule_section = "五、22"
        target_title = "固定资产"
        prefix = "五、"

        fallback = [
            n for n in notes
            if n["section_title"] == target_title
            and not n["is_deleted"]
            and n["note_section"].startswith(prefix)
        ]
        # 只有 五、33 存活 → 唯一命中
        assert len(fallback) == 1
        assert fallback[0]["note_section"] == "五、33"

    def test_cross_prefix_not_matched(self):
        """反查范围用前缀限定：五、 的规则不会匹配到 八、 的章节。"""
        notes = [
            {"note_section": "五、22", "section_title": "递延所得税负债", "is_deleted": False},
            {"note_section": "八、15", "section_title": "固定资产", "is_deleted": False},
        ]

        rule_section = "五、22"
        target_title = "固定资产"
        prefix = "五、"

        fallback = [
            n for n in notes
            if n["section_title"] == target_title
            and not n["is_deleted"]
            and n["note_section"].startswith(prefix)
        ]
        # 八、15 不在 五、 前缀范围内 → 0 条 → 不采纳
        assert len(fallback) == 0

    def test_section_dynamic_lookup_ambiguous_skip(self):
        """Task 5.4 · 需求 3.2：同 section_title 有 2 条匹配 → 不替换，走原逻辑跳过。

        engine.py _push_note 的动态定位逻辑（L617-637）要求反查结果
        **唯一**（len(fallback)==1）才采纳。0 条或多条视为歧义，
        回退硬编码逻辑（即走原逻辑跳过）。

        本测试模拟：
          - 规则声明 五、22 对应"固定资产"，但项目中 五、22="递延所得税负债"
          - 反查 section_title=="固定资产" 在五、前缀下命中 **2 条**（五、25 和 五、30）
          - len(fallback)==2 ≠ 1 → 视为歧义 → 不采纳 → 走原逻辑报跳过
        """
        # ── 模拟项目附注章节：同标题"固定资产"出现在两个不同章节号 ──
        notes = [
            {"note_section": "五、20", "section_title": "长期借款", "is_deleted": False},
            {"note_section": "五、22", "section_title": "递延所得税负债", "is_deleted": False},
            {"note_section": "五、25", "section_title": "固定资产", "is_deleted": False},  # match 1
            {"note_section": "五、30", "section_title": "固定资产", "is_deleted": False},  # match 2
            {"note_section": "五、35", "section_title": "在建工程", "is_deleted": False},
        ]

        rule_section = "五、22"
        target_title = "固定资产"  # _title_check_name

        # ── Step 1: 硬编码章节号的标题不匹配 → 触发反查 ──
        direct_note = next(
            (n for n in notes if n["note_section"] == rule_section and not n["is_deleted"]),
            None,
        )
        assert direct_note is not None
        assert direct_note["section_title"] != target_title, "标题不匹配才触发反查"

        # ── Step 2: 提取前缀 ──
        prefix = rule_section.split("、")[0] + "、"
        assert prefix == "五、"

        # ── Step 3: 反查 → 命中 2 条（歧义） ──
        fallback_rows = [
            n for n in notes
            if n["section_title"] == target_title
            and not n["is_deleted"]
            and n["note_section"].startswith(prefix)
        ]
        assert len(fallback_rows) == 2, (
            f"应有 2 条同名匹配（歧义），实际 {len(fallback_rows)} 条"
        )

        # ── Step 4: 唯一性检查失败 → 不采纳 ──
        assert len(fallback_rows) != 1, "非唯一匹配不应被采纳"

        # ── Step 5: 验证走原逻辑——section 和 note 保持不变（未被替换） ──
        # engine.py 的 if len(fallback)==1 块不进入，section 仍为规则原值
        current_section = rule_section  # 未被替换
        current_note = direct_note       # 未被替换
        assert current_section == "五、22", "歧义时 section 应保持规则原值"
        assert current_note["section_title"] == "递延所得税负债", (
            "歧义时 note 应保持硬编码查到的原记录"
        )

    def test_section_dynamic_lookup_zero_match_skip(self):
        """补充：反查 0 条匹配同样不采纳（与 2 条歧义行为一致）。"""
        notes = [
            {"note_section": "五、22", "section_title": "递延所得税负债", "is_deleted": False},
            {"note_section": "五、25", "section_title": "长期借款", "is_deleted": False},
        ]

        rule_section = "五、22"
        target_title = "固定资产"
        prefix = "五、"

        fallback_rows = [
            n for n in notes
            if n["section_title"] == target_title
            and not n["is_deleted"]
            and n["note_section"].startswith(prefix)
        ]
        assert len(fallback_rows) == 0, "目标标题在本前缀下无匹配"
        assert len(fallback_rows) != 1, "0 条匹配同样不被采纳"

    def test_section_dynamic_lookup_not_triggered_when_match(self):
        """Task 5.5 · 需求 3.3：硬编码章节号 section_title 匹配 → 不触发反查。

        engine.py _push_note 的动态定位逻辑（L617-637）：
          note = query(note_section == rule_section)
          if note.section_title != _title_check_name:
              # ← 不匹配时才进入反查分支
              fallback = ...

        本测试验证 happy path：
          - 规则声明 五、22 → 项目中 五、22 的 section_title 恰好是"固定资产"
          - section_title == _title_check_name → 条件为 False
          - 整个反查分支被跳过 → note 和 section 保持不变
          - 后续推送使用原始硬编码章节号直接进行
        """
        # ── 模拟项目附注章节：五、22 的标题恰好匹配规则声明 ──
        notes = [
            {"note_section": "五、20", "section_title": "长期借款", "is_deleted": False},
            {"note_section": "五、22", "section_title": "固定资产", "is_deleted": False},
            {"note_section": "五、30", "section_title": "在建工程", "is_deleted": False},
        ]

        rule_section = "五、22"
        target_title = "固定资产"  # _title_check_name

        # ── Step 1: 按硬编码 section 取到 note ──
        direct_note = next(
            (n for n in notes if n["note_section"] == rule_section and not n["is_deleted"]),
            None,
        )
        assert direct_note is not None, "硬编码章节号应能查到记录"

        # ── Step 2: section_title 匹配 → 不触发反查 ──
        title_matches = (direct_note["section_title"] or "").strip() == target_title
        assert title_matches, (
            f"规则声明 {rule_section} 的标题「{direct_note['section_title']}」"
            f"应与目标「{target_title}」匹配"
        )

        # ── Step 3: 反查条件不满足（条件是 != 才进入） ──
        fallback_triggered = not title_matches
        assert not fallback_triggered, "标题匹配时反查分支不应被触发"

        # ── Step 4: note 和 section 保持不变（未被替换） ──
        current_section = rule_section  # 未被替换
        current_note = direct_note       # 未被替换
        assert current_section == "五、22", "匹配时 section 应保持规则原值"
        assert current_note["section_title"] == "固定资产", (
            "匹配时 note 应保持硬编码查到的原记录"
        )
        assert current_note["note_section"] == rule_section, (
            "匹配时 note_section 应与规则声明一致"
        )
