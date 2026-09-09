"""底稿编制说明提取器。

``extract_exact_static`` 只探测当前 code 的 canonical JSON；``extract`` 才执行
static → template → typed → generic 的完整链。两者分开后，child 请求不会被父模板或
类型化 fallback 伪装成 child exact。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.services.guidance_inventory import (
    GUIDANCE_DIR,
    infer_section_key,
    normalize_source_refs,
    section_content,
)

logger = logging.getLogger(__name__)

_SHEET_NAMES = {"编制说明", "说明", "instructions"}
_SECTION_PATTERN = re.compile(
    r"^(?:"
    r"[一二三四五六七八九十]+、"
    r"|[①②③④⑤⑥⑦⑧⑨⑩]"
    r"|\d+[\.、\)]"
    r"|第[一二三四五六七八九十\d]+步"
    r"|步骤\s*\d+"
    r")"
)
_IO_TIMEOUT = 5.0


@dataclass
class GuidanceSection:
    """编制说明结构化章节。"""

    heading: str
    content: str
    order: int = 0
    key: str | None = None
    source_refs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GuidanceResult:
    """编制说明提取结果；source 是事实来源，不等同于 exact 完成状态。"""

    wp_code: str
    wp_name: str = ""
    source: Literal[
        "template_sheet",
        "template_header",
        "docx_instructions",
        "static_json",
        "typed_fallback",
        "fallback",
    ] = "fallback"
    complexity: Literal["high", "medium", "low"] = "low"
    sections: list[GuidanceSection] = field(default_factory=list)
    raw_text: str = ""
    source_path: str | None = None


class GuidanceExtractor:
    """从 canonical static guidance 或权威模板提取编制说明。"""

    async def extract_exact_static(
        self,
        wp_code: str,
        *,
        validated_entry: Any | None = None,
    ) -> GuidanceResult | None:
        """只消费已通过 contextual source_ref 校验的 static contract。"""
        if validated_entry is None or getattr(validated_entry, "exact_status", None) != "exact":
            return None
        entry_code = (
            getattr(validated_entry, "sheet_code", None)
            or getattr(validated_entry, "wp_code", None)
        )
        if entry_code != wp_code:
            return None
        source_ref_status = getattr(validated_entry, "source_ref_status", None)
        if source_ref_status is not None and source_ref_status != "valid":
            return None
        source_facts = tuple(getattr(validated_entry, "source_facts", ()) or ())
        if source_facts:
            has_static = any(getattr(item, "kind", None) == "static_guidance" for item in source_facts)
            has_validated_refs = any(
                getattr(item, "kind", None) == "source_ref_validation"
                and getattr(item, "origin", None) == "valid"
                for item in source_facts
            )
            if not has_static or not has_validated_refs:
                return None
        elif source_ref_status != "valid":
            return None

        result = await self._try_with_timeout(self._extract_static_json, wp_code)
        if result is None or not result.sections or not result.raw_text.strip():
            return None
        return result

    async def extract(self, wp_code: str, template_path: Path | None) -> GuidanceResult:
        """执行当前 code 的完整解析链，保证有可展示结果但不保证 exact。"""
        # parent full chain 保留 legacy static 的专家内容，由 response metadata 如实标
        # missing；不能复用 child exact probe，否则会静默丢弃已有方法论。
        result = await self._try_with_timeout(self._extract_static_json, wp_code)
        if result:
            return result

        if template_path and template_path.exists():
            suffix = template_path.suffix.lower()
            if suffix in (".xlsx", ".xls", ".xlsm"):
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
            elif suffix == ".docx":
                result = await self._try_with_timeout(
                    self._extract_docx_instructions, template_path, wp_code
                )
                if result:
                    return result

        typed_fallback = self._typed_fallback(wp_code)
        if typed_fallback:
            return typed_fallback

        text = "请参照模板格式填写，注意数据来源的可追溯性。"
        return GuidanceResult(
            wp_code=wp_code,
            source="fallback",
            raw_text=text,
            sections=[GuidanceSection(heading="通用提示", content=text, order=0)],
        )

    async def extract_full(self, wp_code: str, template_path: Path | None) -> GuidanceResult:
        """语义化别名，供 resolution service 明确表达 parent full chain。"""
        return await self.extract(wp_code, template_path)

    async def _try_with_timeout(self, func, *args) -> GuidanceResult | None:
        try:
            return await asyncio.wait_for(asyncio.to_thread(func, *args), timeout=_IO_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("提取超时(%.1fs): func=%s, args=%s", _IO_TIMEOUT, func.__name__, args[:2])
            return None
        except Exception as exc:  # noqa: BLE001 — 解析链继续，但 route metadata 会记录 invalid
            logger.warning("提取异常: func=%s, error=%s", func.__name__, exc)
            return None

    @staticmethod
    def _file_ref(path: Path, *, kind: str, sheet: str | None = None, cell_range: str | None = None) -> dict[str, str]:
        ref = {"kind": kind, "path": str(path)}
        if sheet:
            ref["sheet"] = sheet
        if cell_range:
            ref["range"] = cell_range
        return ref

    def _extract_xlsx_sheet(self, path: Path, wp_code: str) -> GuidanceResult | None:
        from python_calamine import CalamineWorkbook

        wb = CalamineWorkbook.from_path(str(path))
        target_sheet_idx = next(
            (idx for idx, name in enumerate(wb.sheet_names) if name.strip().lower() in _SHEET_NAMES),
            None,
        )
        if target_sheet_idx is None:
            return None
        target_name = wb.sheet_names[target_sheet_idx]
        rows = wb.get_sheet_by_index(target_sheet_idx).to_python()
        if not rows:
            return None

        sections: list[GuidanceSection] = []
        current_heading = ""
        current_lines: list[str] = []
        order = 0

        def append_current() -> None:
            nonlocal order
            if not current_heading and not current_lines:
                return
            heading = current_heading or f"第{order + 1}节"
            sections.append(GuidanceSection(
                heading=heading,
                content="\n".join(current_lines),
                order=order,
                key=infer_section_key(heading),
                source_refs=[self._file_ref(path, kind="xlsx", sheet=target_name)],
            ))
            order += 1

        for row in rows:
            parts = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
            line = " ".join(parts)
            if not line:
                continue
            if _SECTION_PATTERN.match(line):
                append_current()
                current_heading = line
                current_lines = []
            else:
                current_lines.append(line)
        append_current()
        if not sections:
            return None
        raw_text = "\n\n".join(f"{s.heading}\n{s.content}" if s.heading else s.content for s in sections)
        return GuidanceResult(
            wp_code=wp_code,
            source="template_sheet",
            sections=sections,
            raw_text=raw_text,
            source_path=str(path),
        )

    def _extract_xlsx_header(self, path: Path, wp_code: str) -> GuidanceResult | None:
        from python_calamine import CalamineWorkbook

        wb = CalamineWorkbook.from_path(str(path))
        if not wb.sheet_names:
            return None
        rows = wb.get_sheet_by_index(0).to_python()
        header_texts = [
            str(cell).strip()
            for row in rows[:5]
            for cell in row
            if cell is not None and len(str(cell).strip()) > 20
        ]
        raw_text = "\n".join(header_texts)
        if len(raw_text) < 50:
            return None
        heading = "编制说明"
        return GuidanceResult(
            wp_code=wp_code,
            source="template_header",
            sections=[GuidanceSection(
                heading=heading,
                content=raw_text,
                order=0,
                key=infer_section_key(heading),
                source_refs=[self._file_ref(path, kind="xlsx", sheet=wb.sheet_names[0], cell_range="A1:XFD5")],
            )],
            raw_text=raw_text,
            source_path=str(path),
        )

    def _extract_docx_instructions(self, path: Path, wp_code: str) -> GuidanceResult | None:
        from docx import Document

        doc = Document(str(path))
        instruction_texts: list[str] = []
        for element in doc.element.body:
            if element.tag.endswith("}tbl"):
                break
            if element.tag.endswith("}p"):
                texts: list[str] = []
                for child in element.iter():
                    if child.text:
                        texts.append(child.text)
                    if child.tail:
                        texts.append(child.tail)
                text = "".join(texts).strip()
                if text and len(text) > 10:
                    instruction_texts.append(text)
        raw_text = "\n".join(instruction_texts)
        if len(raw_text) < 30:
            return None
        source_ref = self._file_ref(path, kind="docx", cell_range="before_first_table")
        sections = self._split_into_sections(raw_text, source_ref=source_ref)
        if not sections:
            sections = [GuidanceSection(
                heading="编制说明",
                content=raw_text,
                order=0,
                source_refs=[source_ref],
            )]
        return GuidanceResult(
            wp_code=wp_code,
            source="docx_instructions",
            sections=sections,
            raw_text=raw_text,
            source_path=str(path),
        )

    def _extract_static_json(self, wp_code: str) -> GuidanceResult | None:
        json_path = GUIDANCE_DIR / f"{wp_code}.json"
        if not json_path.exists():
            return None
        with open(json_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict) or "wp_codes" in data:
            return None
        declared_code = str(data.get("wp_code") or "").strip()
        if declared_code and declared_code != wp_code:
            raise ValueError(f"guidance wp_code mismatch: requested={wp_code}, declared={declared_code}")

        sections: list[GuidanceSection] = []
        for raw in data.get("sections") or []:
            if not isinstance(raw, dict):
                continue
            heading = str(raw.get("heading") or raw.get("title") or "").strip()
            content = section_content(raw)
            if not content:
                continue
            explicit_key = str(raw.get("key") or "").strip()
            sections.append(GuidanceSection(
                heading=heading,
                content=content,
                order=len(sections),
                key=explicit_key or infer_section_key(heading),
                source_refs=[dict(ref) for ref in normalize_source_refs(raw.get("source_refs"))],
            ))
        # 迁移未能高置信归类的专家正文仍须在 full chain 可见；key 强制为 None，
        # 防止展示层的标题推断绕过 inventory 的“待裁决” blocker。
        for raw in data.get("unmapped_sections") or []:
            if not isinstance(raw, dict):
                continue
            heading = str(raw.get("heading") or raw.get("title") or "").strip()
            content = section_content(raw)
            if not content:
                continue
            sections.append(GuidanceSection(
                heading=heading,
                content=content,
                order=len(sections),
                key=None,
                source_refs=[dict(ref) for ref in normalize_source_refs(raw.get("source_refs"))],
            ))
        raw_text = "\n\n".join(f"{s.heading}\n{s.content}" if s.heading else s.content for s in sections)
        if not raw_text:
            return None
        return GuidanceResult(
            wp_code=wp_code,
            source="static_json",
            sections=sections,
            raw_text=raw_text,
            source_path=str(json_path),
        )

    def _split_into_sections(
        self,
        text: str,
        *,
        source_ref: dict[str, str] | None = None,
    ) -> list[GuidanceSection]:
        lines = text.split("\n")
        sections: list[GuidanceSection] = []
        current_heading = ""
        current_lines: list[str] = []
        order = 0

        def append_current() -> None:
            nonlocal order
            if not current_heading and not current_lines:
                return
            sections.append(GuidanceSection(
                heading=current_heading,
                content="\n".join(current_lines),
                order=order,
                key=infer_section_key(current_heading),
                source_refs=[source_ref] if source_ref else [],
            ))
            order += 1

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _SECTION_PATTERN.match(stripped):
                append_current()
                current_heading = stripped
                current_lines = []
            else:
                current_lines.append(stripped)
        append_current()
        return sections

    def _typed_fallback(self, wp_code: str) -> GuidanceResult | None:
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
                    key="steps",
                ),
                GuidanceSection(
                    heading="二、常用操作",
                    content=(
                        "• 点击金额单元格可查看取数来源\n"
                        "• 审计调整通过 AJE/RJE 分录录入\n"
                        "• 审定金额 = 未审数 + AJE调整 + RJE调整"
                    ),
                    order=1,
                    key="formulas",
                ),
            ]
            return GuidanceResult(
                wp_code=wp_code,
                source="typed_fallback",
                sections=sections,
                raw_text="\n\n".join(f"{s.heading}\n{s.content}" for s in sections),
            )

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
                    key="steps",
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
                    key="common_errors",
                ),
            ]
            return GuidanceResult(
                wp_code=wp_code,
                source="typed_fallback",
                sections=sections,
                raw_text="\n\n".join(f"{s.heading}\n{s.content}" for s in sections),
            )
        return None
