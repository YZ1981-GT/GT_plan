"""ACNR from_classification 代表记录选取 — 回归测试。

修复：classification 把整个工作簿全部 Tab 挂在每个 wp_code 下，仅按 class_code
优先级会选中兄弟 sheet 的占位名（如 D2-10 选到「附注披露信息(上市公司）D2-1」）。
_pick_representative 现优先「名称以自身编码结尾」的本 tab 真实名。
"""
from app.services.acnr.loaders.from_classification import (
    _ends_with_code,
    _pick_representative,
    load_sheet_skeletons_from_classification,
)


def _rec(wp_code, sheet_name, class_code="C-附注披露"):
    return {
        "wp_code": wp_code,
        "sheet_name": sheet_name,
        "class_code": class_code,
        "functional_type": "",
        "template_version_id": "t",
    }


class TestEndsWithCode:
    def test_self_named_match(self):
        assert _ends_with_code("预期信用损失的计量测试D2-10", "D2-10") is True
        assert _ends_with_code("审定表D2-1", "D2-1") is True

    def test_longer_code_not_mismatched(self):
        # D2-1 不应误配以 D2-10 结尾的名称
        assert _ends_with_code("预期信用损失的计量测试D2-10", "D2-1") is False

    def test_cjk_prefix_allowed(self):
        # 编码前是中文（描述名），应允许（str.isalnum 对 CJK 为 True，须限 ASCII）
        assert _ends_with_code("应收账款检查表D2-7", "D2-7") is True

    def test_ascii_prefix_rejected(self):
        # 编码前是 ASCII 字母 → 命中的是更长编码尾部，不算独立 token
        assert _ends_with_code("XD2-7", "D2-7") is False

    def test_no_match(self):
        assert _ends_with_code("已审比率分析", "A3") is False
        assert _ends_with_code("", "D2-1") is False


class TestPickRepresentative:
    def test_prefers_self_named_over_class_priority(self):
        # D2-10 工作簿的多 Tab 混挂；应选本 tab 真实名而非高优先级兄弟占位名
        recs = [
            _rec("D2-10", "附注披露信息(上市公司）D2-1", "C-附注披露"),
            _rec("D2-10", "预期信用损失的计量测试D2-10", "G-测算"),
            _rec("D2-10", "底稿目录", "B-底稿目录"),
            _rec("D2-10", "GT_Custom", "I-占位"),
        ]
        rep = _pick_representative(recs, "D2-10")
        assert rep["sheet_name"] == "预期信用损失的计量测试D2-10"

    def test_fallback_to_class_priority_when_no_self_named(self):
        # 无自命名行 → 回退 class_code 优先级（行为不变）
        recs = [
            _rec("A3", "已审比率分析", "F-分析表"),
            _rec("A3", "合并流程程序表", "A-一般程序表"),
        ]
        rep = _pick_representative(recs, "A3")
        assert rep["sheet_name"] == "合并流程程序表"

    def test_skeleton_build_uses_self_named(self):
        recs = [
            _rec("D2-7", "附注披露信息(上市公司）D2-1", "C-附注披露"),
            _rec("D2-7", "应收账款检查表D2-7", "D-检查表"),
        ]
        sheets = load_sheet_skeletons_from_classification(recs, registry_version="test")
        assert len(sheets) == 1
        assert sheets[0].sheet_name == "应收账款检查表D2-7"
