"""底稿编制说明提取器 — 从模板文件动态提取编制指引

按优先级尝试：
1. xlsx 模板中的「编制说明」/「说明」/「Instructions」sheet
2. xlsx 首 sheet 前 5 行合并单元格说明文本
3. docx 第一个表格之前的段落
4. 静态 JSON 配置 (backend/data/wp_guidance/{wp_code}.json)
5. 通用 fallback 提示

所有文件 I/O 操作通过 asyncio.to_thread 包装，5 秒超时保护。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# 静态 guidance JSON 目录
GUIDANCE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wp_guidance"

# 编制说明 sheet 名称匹配（大小写不敏感）
_SHEET_NAMES = {"编制说明", "说明", "instructions"}

# 序号行匹配模式：中文序号（一、二、...）/ 阿拉伯数字（1. 2.）/ 第N步
_SECTION_PATTERN = re.compile(
    r"^(?:"
    r"[一二三四五六七八九十]+、"  # 一、二、...
    r"|[①②③④⑤⑥⑦⑧⑨⑩]"  # 圈数字
    r"|\d+[\.、\)]"  # 1. 2、3)
    r"|第[一二三四五六七八九十\d]+步"  # 第一步 / 第1步
    r"|步骤\s*\d+"  # 步骤1
    r")"
)

# I/O 超时（秒）
_IO_TIMEOUT = 5.0


@dataclass
class GuidanceSection:
    """编制说明结构化章节"""

    heading: str
    content: str
    order: int = 0


@dataclass
class GuidanceResult:
    """编制说明提取结果"""

    wp_code: str
    wp_name: str = ""
    source: Literal[
        "template_sheet", "template_header", "docx_instructions", "static_json", "typed_fallback", "fallback"
    ] = "fallback"
    complexity: Literal["high", "medium", "low"] = "low"
    sections: list[GuidanceSection] = field(default_factory=list)
    raw_text: str = ""


class GuidanceExtractor:
    """从模板文件提取编制说明文本

    主入口 `extract` 按优先级尝试多种提取方式，所有阻塞 I/O
    通过 asyncio.to_thread 执行并设 5 秒超时。
    """

    async def extract(self, wp_code: str, template_path: Path | None) -> GuidanceResult:
        """主提取入口，按优先级尝试：
        1. xlsx/docx 模板 sheet/段落
        2. 模板首行/首列说明
        3. 静态 JSON 配置
        4. 通用 fallback

        Args:
            wp_code: 底稿编码（如 D2-1, A17）
            template_path: 模板文件路径，可为 None

        Returns:
            GuidanceResult 提取结果（永不为 None/空）
        """
        # 尝试从模板文件提取
        if template_path and template_path.exists():
            suffix = template_path.suffix.lower()

            # xlsx: 先尝试专属 sheet，再尝试 header
            if suffix in (".xlsx", ".xls"):
                result = await self._try_with_timeout(
                    self._extract_xlsx_sheet, template_path, wp_code
                )
                if result:
                    return result

                result = await self._try_with_timeout(
                    self._extract_xlsx_header, template_path, wp_code
                )
                if result:
                    return result

            # docx: 提取第一个表格之前的段落
            elif suffix == ".docx":
                result = await self._try_with_timeout(
                    self._extract_docx_instructions, template_path, wp_code
                )
                if result:
                    return result

        # 降级：静态 JSON
        result = await self._try_with_timeout(
            self._extract_static_json, wp_code
        )
        if result:
            return result

        # 类型化 fallback（审定表/程序表比通用提示更有针对性）
        typed_fallback = self._typed_fallback(wp_code)
        if typed_fallback:
            return typed_fallback

        # 最终 fallback
        return GuidanceResult(
            wp_code=wp_code,
            source="fallback",
            raw_text="请参照模板格式填写，注意数据来源的可追溯性。",
            sections=[
                GuidanceSection(
                    heading="通用提示",
                    content="请参照模板格式填写，注意数据来源的可追溯性。",
                    order=0,
                )
            ],
        )

    async def _try_with_timeout(self, func, *args) -> GuidanceResult | None:
        """用 asyncio.wait_for + to_thread 包装阻塞 I/O，5 秒超时"""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(func, *args),
                timeout=_IO_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("提取超时(%.1fs): func=%s, args=%s", _IO_TIMEOUT, func.__name__, args[:2])
            return None
        except Exception as e:
            logger.warning("提取异常: func=%s, error=%s", func.__name__, e)
            return None

    def _extract_xlsx_sheet(self, path: Path, wp_code: str) -> GuidanceResult | None:
        """python_calamine 读取「编制说明」sheet，按序号行分 section

        匹配 sheet 名称（大小写不敏感）：编制说明 / 说明 / Instructions
        """
        from python_calamine import CalamineWorkbook

        wb = CalamineWorkbook.from_path(str(path))
        sheet_names = wb.sheet_names

        # 查找匹配的 sheet
        target_sheet_idx = None
        for idx, name in enumerate(sheet_names):
            if name.strip().lower() in _SHEET_NAMES:
                target_sheet_idx = idx
                break

        if target_sheet_idx is None:
            return None

        # 读取 sheet 内容
        rows = wb.get_sheet_by_index(target_sheet_idx).to_python()
        if not rows:
            return None

        # 解析行内容，按序号行分 section
        sections: list[GuidanceSection] = []
        current_heading = ""
        current_lines: list[str] = []
        order = 0

        for row in rows:
            # 合并行内所有非空单元格文本
            line_parts = []
            for cell in row:
                if cell is not None:
                    text = str(cell).strip()
                    if text:
                        line_parts.append(text)
            line = " ".join(line_parts) if line_parts else ""

            if not line:
                continue

            # 检测是否为新的 section 标题行
            if _SECTION_PATTERN.match(line):
                # 保存上一个 section
                if current_heading or current_lines:
                    sections.append(GuidanceSection(
                        heading=current_heading or f"第{order + 1}节",
                        content="\n".join(current_lines),
                        order=order,
                    ))
                    order += 1
                current_heading = line
                current_lines = []
            else:
                current_lines.append(line)

        # 保存最后一个 section
        if current_heading or current_lines:
            sections.append(GuidanceSection(
                heading=current_heading or "说明",
                content="\n".join(current_lines),
                order=order,
            ))

        if not sections:
            return None

        raw_text = "\n\n".join(
            f"{s.heading}\n{s.content}" if s.heading else s.content
            for s in sections
        )

        return GuidanceResult(
            wp_code=wp_code,
            source="template_sheet",
            sections=sections,
            raw_text=raw_text,
        )

    def _extract_xlsx_header(self, path: Path, wp_code: str) -> GuidanceResult | None:
        """读取首 sheet 前 5 行合并单元格中的说明文本

        仅当文本长度 > 20 字符时认为有效。
        """
        from python_calamine import CalamineWorkbook

        wb = CalamineWorkbook.from_path(str(path))
        sheet_names = wb.sheet_names
        if not sheet_names:
            return None

        rows = wb.get_sheet_by_index(0).to_python()
        header_texts: list[str] = []

        for row in rows[:5]:
            for cell in row:
                if cell is not None:
                    text = str(cell).strip()
                    if len(text) > 20:
                        header_texts.append(text)

        if not header_texts or len("\n".join(header_texts)) < 50:
            return None

        raw_text = "\n".join(header_texts)
        sections = [
            GuidanceSection(
                heading="编制说明",
                content=raw_text,
                order=0,
            )
        ]

        return GuidanceResult(
            wp_code=wp_code,
            source="template_header",
            sections=sections,
            raw_text=raw_text,
        )

    def _extract_docx_instructions(self, path: Path, wp_code: str) -> GuidanceResult | None:
        """python-docx 提取第一个表格之前的段落文本"""
        from docx import Document

        doc = Document(str(path))
        instruction_texts: list[str] = []

        for element in doc.element.body:
            # 遇到第一个表格停止
            if element.tag.endswith("}tbl"):
                break
            if element.tag.endswith("}p"):
                # 从子元素获取完整文本
                texts: list[str] = []
                for child in element.iter():
                    if child.text:
                        texts.append(child.text)
                    if child.tail:
                        texts.append(child.tail)
                text = "".join(texts).strip()
                if text and len(text) > 10:
                    instruction_texts.append(text)

        if not instruction_texts or len("\n".join(instruction_texts)) < 30:
            return None

        raw_text = "\n".join(instruction_texts)
        # 尝试按序号分 section
        sections = self._split_into_sections(raw_text)
        if not sections:
            sections = [
                GuidanceSection(heading="编制说明", content=raw_text, order=0)
            ]

        return GuidanceResult(
            wp_code=wp_code,
            source="docx_instructions",
            sections=sections,
            raw_text=raw_text,
        )

    def _extract_static_json(self, wp_code: str) -> GuidanceResult | None:
        """从 backend/data/wp_guidance/{wp_code}.json 读取静态配置"""
        json_path = GUIDANCE_DIR / f"{wp_code}.json"
        if not json_path.exists():
            return None

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 解析 sections
        raw_sections = data.get("sections", [])
        sections = [
            GuidanceSection(
                heading=s.get("heading", ""),
                content=s.get("content", ""),
                order=i,
            )
            for i, s in enumerate(raw_sections)
        ]

        raw_text = "\n\n".join(
            f"{s.heading}\n{s.content}" if s.heading else s.content
            for s in sections
        )

        return GuidanceResult(
            wp_code=wp_code,
            source="static_json",
            sections=sections,
            raw_text=raw_text or data.get("title", ""),
        )

    def _split_into_sections(self, text: str) -> list[GuidanceSection]:
        """将纯文本按序号行拆分为结构化 sections"""
        lines = text.split("\n")
        sections: list[GuidanceSection] = []
        current_heading = ""
        current_lines: list[str] = []
        order = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _SECTION_PATTERN.match(stripped):
                if current_heading or current_lines:
                    sections.append(GuidanceSection(
                        heading=current_heading,
                        content="\n".join(current_lines),
                        order=order,
                    ))
                    order += 1
                current_heading = stripped
                current_lines = []
            else:
                current_lines.append(stripped)

        if current_heading or current_lines:
            sections.append(GuidanceSection(
                heading=current_heading,
                content="\n".join(current_lines),
                order=order,
            ))

        return sections

    def _typed_fallback(self, wp_code: str) -> GuidanceResult | None:
        """按 wp_code 模式生成类型化 fallback（比通用 fallback 更有针对性）

        - *-1 → 审定表类提示
        - *A（且长度>1）→ 程序表类提示
        - 其他 → 返回 None（走通用 fallback）
        """
        import re

        # 审定表（wp_code 以 -1 结尾）
        if re.search(r"-1$", wp_code):
            sections = [
                GuidanceSection(
                    heading="一、审定表编制要点",
                    content=(
                        "1. 期初数从上年审定数或本期期初余额表取得\n"
                        "2. 本期数从序时账/明细账汇总，经审计调整后得到审定数\n"
                        "3. 审定金额应与试算平衡表一致\n"
                        "4. 重分类调整仅影响列报不影响损益\n"
                        "5. 关注科目余额方向是否异常"
                    ),
                    order=0,
                ),
                GuidanceSection(
                    heading="二、常用操作",
                    content=(
                        "• 点击金额单元格可查看取数来源\n"
                        "• 审计调整通过 AJE/RJE 分录录入\n"
                        "• 审定金额 = 未审数 + AJE调整 + RJE调整"
                    ),
                    order=1,
                ),
            ]
            raw_text = "\n\n".join(f"{s.heading}\n{s.content}" for s in sections)
            return GuidanceResult(
                wp_code=wp_code,
                source="typed_fallback",
                sections=sections,
                raw_text=raw_text,
            )

        # 程序表（wp_code 以 A 结尾且长度 > 1）
        if wp_code.endswith("A") and len(wp_code) > 1:
            sections = [
                GuidanceSection(
                    heading="一、程序表使用方法",
                    content=(
                        "1. 按顺序逐项执行各审计程序\n"
                        "2. 在「执行情况」列记录执行结果\n"
                        "3. 在「工作底稿索引号」列填写相关底稿编号\n"
                        "4. 不适用的程序注明原因并标记跳过"
                    ),
                    order=0,
                ),
                GuidanceSection(
                    heading="二、注意事项",
                    content=(
                        "• 每个步骤需标注完成状态\n"
                        "• 关联底稿通过索引号链接\n"
                        "• 特殊情况在备注中说明\n"
                        "• 程序适用性应结合项目实际判断"
                    ),
                    order=1,
                ),
            ]
            raw_text = "\n\n".join(f"{s.heading}\n{s.content}" for s in sections)
            return GuidanceResult(
                wp_code=wp_code,
                source="typed_fallback",
                sections=sections,
                raw_text=raw_text,
            )

        return None
