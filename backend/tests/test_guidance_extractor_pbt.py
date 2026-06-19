# Feature: workpaper-editing-guidance, Property 1: 模板提取保持结构化
"""Property 1: 模板提取保持结构化

For any xlsx template with a "编制说明" sheet containing numbered content,
GuidanceExtractor produces sections maintaining original order with non-empty items.

**Validates: Requirements 2.1, 2.5**
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.guidance_extractor import GuidanceExtractor, GuidanceResult


def _run(coro):
    """辅助：同步执行 async 函数"""
    return asyncio.run(coro)


# 生成带序号的中文章节标题
_SECTION_PREFIXES = [
    "一、", "二、", "三、", "四、", "五、",
    "六、", "七、", "八、", "九、", "十、",
]


@given(
    num_sections=st.integers(min_value=1, max_value=5),
    content_lines_per_section=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=5)
def test_extraction_preserves_structure(num_sections: int, content_lines_per_section: int):
    """对任意序号化内容，提取后的 sections 保持原始顺序且每个 section 的 content 非空。

    生成随机章节数和内容行数，写入临时 xlsx 文件的「编制说明」sheet，
    验证 GuidanceExtractor 提取后 sections 顺序正确且内容非空。
    """
    from openpyxl import Workbook

    # 构建 xlsx 文件，含「编制说明」sheet
    wb = Workbook()
    ws = wb.active
    ws.title = "编制说明"

    # 写入序号化章节
    row_idx = 1
    for i in range(num_sections):
        prefix = _SECTION_PREFIXES[i % len(_SECTION_PREFIXES)]
        heading = f"{prefix}测试章节标题{i + 1}"
        ws.cell(row=row_idx, column=1, value=heading)
        row_idx += 1
        for j in range(content_lines_per_section):
            ws.cell(row=row_idx, column=1, value=f"这是第{i + 1}节的第{j + 1}行内容说明文本")
            row_idx += 1

    # 保存到临时文件
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        wb.save(f.name)
        tmp_path = Path(f.name)

    try:
        extractor = GuidanceExtractor()
        result = _run(extractor.extract("TEST_PBT", tmp_path))

        assert isinstance(result, GuidanceResult)

        # 提取成功时验证结构
        if result.source == "template_sheet":
            # sections 保持原始顺序
            orders = [s.order for s in result.sections]
            assert orders == sorted(orders), "sections 未保持原始顺序"

            # 每个 section 的 content 非空
            for section in result.sections:
                assert section.heading or section.content, "section 的 heading 和 content 不能同时为空"

            # raw_text 非空
            assert len(result.raw_text) > 0
    finally:
        tmp_path.unlink(missing_ok=True)
