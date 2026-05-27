"""致同附注 Word 排版规范单一真源.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 4 Task 4.4 (R5.2)
Reqs:   v2 §5.4 / D7 / ADR-009 — 21 项排版参数从 ``附注模版/上市报表附注.md``
        与 ``附注模版/国企报表附注.md`` 头部「使用说明」段落沉淀（两版规范完全相同）。

设计目标
--------
1. **数据结构**：``@dataclass(frozen=True)`` 一次构造永不可变，避免运行时被改写。
2. **唯一真源**：所有 Word 导出 / 前端 CSS 变量 / 视觉回归断言共享本配置；
   docx 模板生成器、note_word_exporter、test_note_export_visual 等下游全部
   从 ``DEFAULT_GT_FORMAT`` 取值。
3. **可序列化**：``GET /api/disclosure-notes/format-config`` 端点直接将
   dataclass 转 dict 下发前端，前端 ``useNoteFormatConfig`` composable 注入
   CSS 变量。

21 项字段分组（与 ADR-009 D7 一致）
-----------------------------------
- 页边距 4：margin_top_cm / margin_bottom_cm / margin_left_cm / margin_right_cm
- 页眉页脚 2：header_distance_cm / footer_distance_cm
- 字体 4：font_chinese / font_western / font_size_pt / font_size_table_pt
- 段落间距 4：heading_space_after_lines / body_space_after_lines /
              after_table_space_before_lines / after_table_space_after_lines
- 表格 4：table_top_border_pt / table_bottom_border_pt /
          header_bottom_border_pt / table_row_height_cm
- 标题缩进 2：heading1_left_indent_chars / heading2_left_indent_chars
- 数值格式 1：empty_value_placeholder
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


# ---------------------------------------------------------------------------
# 21 项排版参数 — frozen dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NoteFormatConfig:
    """致同附注 Word 排版规范（21 项参数，frozen 不可变）.

    单位约定（来源于致同 PDF + ADR-009 D7）::

        cm    厘米（页边距 / 行高 / 页眉页脚距离）
        pt    磅（边框线宽，1 磅 = 8 twip = 0.353 mm）
        chars 字符（标题左缩进，按 -2 字符 = 一个汉字宽度后移）
        lines 行（段落间距，致同规范用「半行 / 0.9 行」描述）
    """

    # ── 页面设置（4） — 来源「①页边距：左3、右3.18、上3.2、下2.54」 ──
    margin_top_cm: float = 3.2
    """上页边距（cm）。致同规范固定 3.2 cm。"""

    margin_bottom_cm: float = 2.54
    """下页边距（cm）。"""

    margin_left_cm: float = 3.0
    """左页边距（cm）。"""

    margin_right_cm: float = 3.18
    """右页边距（cm）。"""

    # ── 页眉页脚（2） — 来源「②版式：页眉1.3、页脚1.3」 ──
    header_distance_cm: float = 1.3
    """页眉到顶端距离（cm）。"""

    footer_distance_cm: float = 1.3
    """页脚到底端距离（cm）。"""

    # ── 字体（4） — 来源「中文：仿宋_GB2312，小四 / 数字：Arial Narrow」 ──
    font_chinese: str = "仿宋_GB2312"
    """中文字体名（含页眉页脚）。"""

    font_western: str = "Arial Narrow"
    """西文 / 数字字体名。"""

    font_size_pt: int = 12
    """正文字号（磅）。小四 = 12pt。"""

    font_size_table_pt: int = 12
    """表格内字号（磅）。一般同正文小四，金额过长时可缩为五号 / 小五；
    本字段记录默认值，运行时缩字号是渲染层职责。"""

    # ── 段落间距（4） — 来源 D7 + ADR-009 ──
    heading_space_after_lines: float = 0.9
    """章节标题段后行数（致同标准段后 0.9 行 = 216 twip）。"""

    body_space_after_lines: float = 0.9
    """正文段后行数。"""

    after_table_space_before_lines: float = 0.5
    """表格后说明段前行数（GTNoteAfterTable 段前 0.5 行 = 120 twip）。"""

    after_table_space_after_lines: float = 0.9
    """表格后说明段后行数。"""

    # ── 表格（4） — 来源「④表格边框：上下边框1磅，标题行下边框1/2磅」+ 行高 ──
    table_top_border_pt: float = 1.0
    """三线表顶边框线宽（磅）。"""

    table_bottom_border_pt: float = 1.0
    """三线表底边框线宽（磅）。"""

    header_bottom_border_pt: float = 0.5
    """三线表表头下边框线宽（磅，1/2 磅）。"""

    table_row_height_cm: float = 0.7
    """单行行高（cm）。小四字号下单行 0.7，两行 1.1（本字段为单行默认）。"""

    # ── 标题缩进（2） — 来源 ADR-009 D7「H1 leftChars=-200 / H2 leftChars=-100」──
    heading1_left_indent_chars: float = -2.0
    """一级标题左缩进字符数（负数 = 向左外突）。"""

    heading2_left_indent_chars: float = -1.0
    """二级标题左缩进字符数。"""

    # ── 数值格式（1） — 来源「⑩数字格式0或无文字时应留白」 ──
    empty_value_placeholder: str = ""
    """空值 / 零值的视觉留白（致同规范不允许填 ``0`` / ``-`` / ``/``）。"""

    # -------- 工具方法 --------

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（用于端点响应 / JSON 持久化）."""
        return asdict(self)

    def to_css_variables(self) -> dict[str, str]:
        """生成前端 CSS 变量映射（``useNoteFormatConfig`` 直接 inject 到 :root）.

        命名约定 ``--gt-note-*`` 与 GTNote* 样式命名空间对齐（ADR-009）。
        值附单位（cm / pt / 字号 px 估算 / lines 数）便于前端直接消费。
        """
        return {
            # 页边距
            "--gt-note-margin-top": f"{self.margin_top_cm}cm",
            "--gt-note-margin-bottom": f"{self.margin_bottom_cm}cm",
            "--gt-note-margin-left": f"{self.margin_left_cm}cm",
            "--gt-note-margin-right": f"{self.margin_right_cm}cm",
            # 页眉页脚
            "--gt-note-header-distance": f"{self.header_distance_cm}cm",
            "--gt-note-footer-distance": f"{self.footer_distance_cm}cm",
            # 字体
            "--gt-note-font-chinese": f'"{self.font_chinese}"',
            "--gt-note-font-western": f'"{self.font_western}"',
            "--gt-note-font-size": f"{self.font_size_pt}pt",
            "--gt-note-font-size-table": f"{self.font_size_table_pt}pt",
            # 段落间距（行）
            "--gt-note-heading-space-after": str(self.heading_space_after_lines),
            "--gt-note-body-space-after": str(self.body_space_after_lines),
            "--gt-note-after-table-space-before": str(
                self.after_table_space_before_lines
            ),
            "--gt-note-after-table-space-after": str(
                self.after_table_space_after_lines
            ),
            # 表格
            "--gt-note-table-top-border": f"{self.table_top_border_pt}pt",
            "--gt-note-table-bottom-border": f"{self.table_bottom_border_pt}pt",
            "--gt-note-header-bottom-border": f"{self.header_bottom_border_pt}pt",
            "--gt-note-table-row-height": f"{self.table_row_height_cm}cm",
            # 标题缩进
            "--gt-note-h1-indent": f"{self.heading1_left_indent_chars}",
            "--gt-note-h2-indent": f"{self.heading2_left_indent_chars}",
            # 数值占位
            "--gt-note-empty-placeholder": f'"{self.empty_value_placeholder}"',
        }

    @classmethod
    def field_names(cls) -> list[str]:
        """21 项字段名（按 dataclass 声明顺序）。"""
        return [f.name for f in fields(cls)]


# ---------------------------------------------------------------------------
# 模块级实例 — 唯一真源
# ---------------------------------------------------------------------------


DEFAULT_GT_FORMAT: NoteFormatConfig = NoteFormatConfig()
"""默认致同排版配置（21 项参数全部使用 dataclass 字段默认值）.

下游消费方
----------
- ``backend/app/services/note_word_exporter.py`` — Word 导出
- ``scripts/build_note_export_template.py`` — 模板 docx 生成
- ``GET /api/disclosure-notes/format-config`` — 前端拉取
- ``backend/tests/services/test_note_export_visual.py`` — 视觉回归断言
"""


__all__ = [
    "NoteFormatConfig",
    "DEFAULT_GT_FORMAT",
]
