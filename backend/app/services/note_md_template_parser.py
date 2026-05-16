"""附注 MD 模板解析器

解析 `附注模版/` 目录下 4 套 MD 文件（国企合并/单体 + 上市合并/单体），
提取章节结构、表格定义、文本模板、占位符。

Requirements: 21.1, 21.2, 21.4, 21.5, 21.7, 21.8
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TableColumn:
    """表格列定义"""
    name: str
    alignment: str = "left"  # left / center / right
    data_type: str = "text"  # text / amount / date / percent


@dataclass
class TableDefinition:
    """表格定义"""
    columns: list[TableColumn] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    name: str = ""


@dataclass
class NoteSection:
    """附注章节"""
    title: str
    level: int  # 1=一级, 2=二级, 3=三级 ...
    section_number: str = ""  # e.g. "五、（一）1."
    text_content: str = ""
    tables: list[TableDefinition] = field(default_factory=list)
    placeholders: list[str] = field(default_factory=list)
    children: list["NoteSection"] = field(default_factory=list)
    raw_content: str = ""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

# Blue guidance text patterns (to be removed)
_BLUE_TEXT_PATTERNS = [
    re.compile(r"【[^】]*】"),  # 【蓝色指引文字】
    re.compile(r"\(蓝色[^)]*\)"),  # (蓝色:...)
    re.compile(r"（蓝色[^）]*）"),  # （蓝色:...）
    re.compile(r"\[蓝色[^\]]*\]"),  # [蓝色:...]
    re.compile(r"〔[^〕]*〕"),  # 〔指引文字〕
]

# Placeholder pattern: {xxx} or {{xxx}}
_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")

# MD heading pattern
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# MD table separator pattern
_TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")

# Amount column keywords
_AMOUNT_KEYWORDS = {"余额", "金额", "增加", "减少", "合计", "本期", "上期", "期初", "期末", "借方", "贷方"}


class NoteMDTemplateParser:
    """附注 MD 模板解析器

    支持模板热加载：每次调用 parse() 时检查文件修改时间，
    如果文件未变则返回缓存结果。
    """

    TEMPLATE_FILES: dict[tuple[str, str], str] = {
        ("soe", "consolidated"): "附注模版/国企报表附注.md",
        ("soe", "standalone"): "附注模版/国企报表附注_单体.md",
        ("listed", "consolidated"): "附注模版/上市报表附注.md",
        ("listed", "standalone"): "附注模版/上市报表附注_单体.md",
    }

    def __init__(self, base_dir: str | Path | None = None):
        if base_dir is None:
            # Default: project root (where 附注模版/ lives)
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
        self._base_dir = Path(base_dir)
        # Cache: key -> (mtime, parsed_sections)
        self._cache: dict[tuple[str, str], tuple[float, list[NoteSection]]] = {}

    def _get_template_path(self, template_type: str, scope: str) -> Path | None:
        """Get the full path for a template file."""
        rel_path = self.TEMPLATE_FILES.get((template_type, scope))
        if not rel_path:
            return None
        full_path = self._base_dir / rel_path
        return full_path if full_path.exists() else None

    def parse(self, template_type: str, scope: str) -> list[NoteSection]:
        """Parse a MD template file and return section list.

        Supports hot-reload: checks file mtime and returns cached result
        if file hasn't changed.
        """
        key = (template_type, scope)
        path = self._get_template_path(template_type, scope)
        if path is None:
            logger.warning("Template file not found: %s/%s", template_type, scope)
            return []

        # Hot-reload check
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return []

        cached = self._cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]

        # Parse the file
        start = time.time()
        try:
            content = path.read_text(encoding="utf-8-sig")
        except Exception as e:
            logger.error("Failed to read template %s: %s", path, e)
            return []

        sections = self._parse_content(content)
        elapsed = time.time() - start
        logger.info(
            "Parsed MD template %s/%s: %d sections, %.2fs",
            template_type, scope, len(sections), elapsed,
        )

        self._cache[key] = (mtime, sections)
        return sections

    def _parse_content(self, content: str) -> list[NoteSection]:
        """Parse MD content into a flat list of NoteSection objects."""
        # Remove blue guidance text
        content = self._remove_blue_text(content)

        lines = content.split("\n")
        sections: list[NoteSection] = []
        current_section: NoteSection | None = None
        current_lines: list[str] = []
        in_table = False
        table_lines: list[str] = []

        for line in lines:
            # Check if this is a heading
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                # Finalize previous section
                if current_section is not None:
                    if in_table and table_lines:
                        current_section.tables.append(self._parse_table(table_lines))
                        table_lines = []
                        in_table = False
                    current_section.text_content = "\n".join(current_lines).strip()
                    current_section.raw_content = current_section.text_content
                    current_section.placeholders = self._extract_placeholders(
                        current_section.text_content
                    )
                    sections.append(current_section)

                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                section_number = self._extract_section_number(title)
                current_section = NoteSection(
                    title=title,
                    level=level,
                    section_number=section_number,
                )
                current_lines = []
                in_table = False
                table_lines = []
                continue

            # Check if this is a table line
            if line.strip().startswith("|") and line.strip().endswith("|"):
                if not in_table:
                    in_table = True
                    table_lines = []
                table_lines.append(line)
                continue
            elif in_table:
                # End of table
                if current_section and table_lines:
                    current_section.tables.append(self._parse_table(table_lines))
                table_lines = []
                in_table = False

            # Regular content line
            if current_section is not None:
                current_lines.append(line)

        # Finalize last section
        if current_section is not None:
            if in_table and table_lines:
                current_section.tables.append(self._parse_table(table_lines))
            current_section.text_content = "\n".join(current_lines).strip()
            current_section.raw_content = current_section.text_content
            current_section.placeholders = self._extract_placeholders(
                current_section.text_content
            )
            sections.append(current_section)

        return sections

    def _remove_blue_text(self, content: str) -> str:
        """Remove blue guidance text (bracketed annotations)."""
        for pattern in _BLUE_TEXT_PATTERNS:
            content = pattern.sub("", content)
        return content

    def _extract_placeholders(self, text: str) -> list[str]:
        """Extract {placeholder} patterns from text."""
        return list(set(_PLACEHOLDER_RE.findall(text)))

    def _extract_section_number(self, title: str) -> str:
        """Extract section number from title like '一、公司基本情况' -> '一'."""
        # Chinese numbered patterns
        patterns = [
            r"^([一二三四五六七八九十]+)、",  # 一、
            r"^（([一二三四五六七八九十]+)）",  # （一）
            r"^(\d+)\.",  # 1.
            r"^(\d+)、",  # 1、
        ]
        for p in patterns:
            m = re.match(p, title)
            if m:
                return m.group(1)
        return ""

    def _parse_table(self, lines: list[str]) -> TableDefinition:
        """Parse MD table lines into a TableDefinition."""
        if len(lines) < 2:
            return TableDefinition()

        # First line: headers
        header_line = lines[0]
        headers = [cell.strip() for cell in header_line.strip("|").split("|")]

        # Second line: alignment (separator)
        sep_line = lines[1] if len(lines) > 1 else ""
        alignments = self._parse_alignments(sep_line, len(headers))

        # Build columns
        columns = []
        for i, name in enumerate(headers):
            alignment = alignments[i] if i < len(alignments) else "left"
            data_type = self._infer_data_type(name)
            columns.append(TableColumn(name=name, alignment=alignment, data_type=data_type))

        # Data rows (skip header + separator)
        rows = []
        for line in lines[2:]:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            rows.append(cells)

        return TableDefinition(columns=columns, rows=rows)

    def _parse_alignments(self, sep_line: str, num_cols: int) -> list[str]:
        """Parse alignment from separator line like |:---|:---:|---:|"""
        alignments = []
        if not sep_line.strip():
            return ["left"] * num_cols

        parts = sep_line.strip("|").split("|")
        for part in parts:
            part = part.strip()
            if part.startswith(":") and part.endswith(":"):
                alignments.append("center")
            elif part.endswith(":"):
                alignments.append("right")
            else:
                alignments.append("left")

        # Pad if needed
        while len(alignments) < num_cols:
            alignments.append("left")
        return alignments

    def _infer_data_type(self, col_name: str) -> str:
        """Infer column data type from name."""
        if any(kw in col_name for kw in _AMOUNT_KEYWORDS):
            return "amount"
        if "日期" in col_name or "时间" in col_name:
            return "date"
        if "比例" in col_name or "率" in col_name or "%" in col_name:
            return "percent"
        return "text"

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def extract_tables(self, section: NoteSection) -> list[TableDefinition]:
        """Extract all table definitions from a section."""
        return section.tables

    def extract_placeholders(self, section: NoteSection) -> list[str]:
        """Extract all placeholders from a section."""
        return section.placeholders

    def get_stats(self, template_type: str, scope: str) -> dict[str, int]:
        """Get parsing statistics for a template."""
        sections = self.parse(template_type, scope)
        total_tables = sum(len(s.tables) for s in sections)
        total_placeholders = sum(len(s.placeholders) for s in sections)
        return {
            "chapter_count": len(sections),
            "table_count": total_tables,
            "placeholder_count": total_placeholders,
        }

    def invalidate_cache(self, template_type: str | None = None, scope: str | None = None):
        """Invalidate cache for hot-reload."""
        if template_type and scope:
            self._cache.pop((template_type, scope), None)
        else:
            self._cache.clear()


# Module-level singleton for lazy loading
_parser_instance: NoteMDTemplateParser | None = None


def get_parser(base_dir: str | Path | None = None) -> NoteMDTemplateParser:
    """Get or create the singleton parser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = NoteMDTemplateParser(base_dir=base_dir)
    return _parser_instance
