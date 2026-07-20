"""LLM 复核输出结构化解析器

将 LLM 返回的复核文本解析为结构化 ReviewFinding 列表，
并判定整体通过状态。

Requirements: 8.1, 8.2, 8.3, 8.4
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ReviewFinding:
    """单条复核发现"""

    id: str  # UUID
    description: str  # 问题描述
    risk_level: str  # "high" | "medium" | "low" | "unknown"
    pass_status: bool  # 该项是否通过
    category: str  # 发现类别
    sheet_location: str | None = None  # 涉及底稿定位
    suggestion: str | None = None  # 整改建议


@dataclass
class ParseResult:
    """解析结果"""

    findings: list[ReviewFinding] = field(default_factory=list)
    raw_text: str = ""
    parse_success: bool = False


# 风险等级关键词 → risk_level 映射
_RISK_LEVEL_KEYWORDS: dict[str, str] = {
    "高风险": "high",
    "high": "high",
    "中风险": "medium",
    "medium": "medium",
    "低风险": "low",
    "low": "low",
}

# section 标题正则：匹配包含风险等级关键词的 heading
_SECTION_HEADING_RE = re.compile(
    r"^#{1,4}\s+.*?(高风险|中风险|低风险|high|medium|low)",
    re.IGNORECASE,
)

# checklist 未勾选项：- [ ] xxx
_UNCHECKED_RE = re.compile(r"^-\s*\[\s*\]\s*(.+)$")

# checklist 已勾选项：- [x] xxx 或 - [X] xxx
_CHECKED_RE = re.compile(r"^-\s*\[[xX]\]\s*(.+)$")

# category 推断：从 section 标题中提取类别
_CATEGORY_KEYWORDS: dict[str, str] = {
    "认定": "认定检查",
    "程序": "程序执行",
    "数据": "数据完整性",
    "勾稽": "数据完整性",
    "风险": "风险评估",
    "计价": "计价分摊",
    "完整性": "完整性检查",
    "存在": "存在性检查",
    "截止": "截止测试",
    "分类": "分类检查",
    "披露": "披露检查",
    "减值": "减值测试",
    "样本": "抽样检查",
}


class LlmResponseParser:
    """LLM 复核输出解析器"""

    @staticmethod
    def parse(raw_text: str) -> ParseResult:
        """解析 LLM 输出为结构化发现

        识别策略：
        1. 找 section 标题包含"高风险/中风险/低风险"以推断当前 risk_level
        2. 找 checklist 标记（- [ ] / - [x]）
        3. 未勾选项 → ReviewFinding（pass_status=False）
        4. 已勾选项 → ReviewFinding（pass_status=True）
        5. 解析失败（无有效项）→ 降级为单条 unknown finding

        Requirements: 8.1, 8.2, 8.4

        Args:
            raw_text: LLM 输出的原始文本

        Returns:
            ParseResult 包含解析后的发现列表
        """
        try:
            return LlmResponseParser._do_parse(raw_text)
        except Exception as e:
            # 解析失败降级：存储原文为单条 unknown finding (Req 8.4)
            logger.warning("LLM response parse failed: %s", e)
            return LlmResponseParser._degrade_to_unknown(raw_text)

    @staticmethod
    def determine_pass_status(findings: list[ReviewFinding]) -> str:
        """判定整体通过状态

        Rules (Requirement 8.3):
        - zero high-risk findings AND fewer than 3 medium-risk findings → "pass"
        - otherwise → "fail"

        只统计 pass_status=False 的发现（即未通过的问题项）。

        Args:
            findings: ReviewFinding 列表

        Returns:
            "pass" 或 "fail"
        """
        high_count = 0
        medium_count = 0

        for f in findings:
            if not f.pass_status:
                if f.risk_level == "high":
                    high_count += 1
                elif f.risk_level == "medium":
                    medium_count += 1

        if high_count == 0 and medium_count < 3:
            return "pass"
        return "fail"

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    @staticmethod
    def _try_parse_json(raw_text: str) -> ParseResult | None:
        """尝试从 JSON 格式解析复核结果"""
        import json as _json

        # 尝试直接解析
        text = raw_text.strip()
        # 处理可能被 markdown 代码块包裹的情况
        if text.startswith("```"):
            # 去掉 ```json ... ``` 包裹
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.strip() == "```" and in_block:
                    break
                elif in_block:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        try:
            data = _json.loads(text)
        except _json.JSONDecodeError:
            # 尝试提取 JSON 子串 (LLM 可能在 JSON 前后加文字)
            json_match = re.search(r'\{[\s\S]*"findings"[\s\S]*\}', text)
            if not json_match:
                return None
            try:
                data = _json.loads(json_match.group())
            except _json.JSONDecodeError:
                return None

        if not isinstance(data, dict) or "findings" not in data:
            return None

        findings_raw = data["findings"]
        if not isinstance(findings_raw, list):
            return None

        findings: list[ReviewFinding] = []
        for item in findings_raw:
            if not isinstance(item, dict):
                continue
            findings.append(
                ReviewFinding(
                    id=str(uuid.uuid4()),
                    description=item.get("description", ""),
                    risk_level=item.get("risk_level", "unknown"),
                    pass_status=bool(item.get("passed", True)),
                    category=item.get("category", "general"),
                    sheet_location=item.get("location"),
                    suggestion=item.get("suggestion"),
                )
            )

        if not findings:
            return None

        return ParseResult(
            findings=findings,
            raw_text=raw_text,
            parse_success=True,
        )

    @staticmethod
    def _do_parse(raw_text: str) -> ParseResult:
        """实际解析逻辑 — 优先尝试 JSON，降级到 checklist 正则"""
        if not raw_text or not raw_text.strip():
            return LlmResponseParser._degrade_to_unknown(raw_text or "")

        # 优先尝试 JSON 解析
        json_result = LlmResponseParser._try_parse_json(raw_text)
        if json_result:
            return json_result

        # 降级到 checklist 正则解析（兼容旧格式）

        findings: list[ReviewFinding] = []
        current_risk_level = "unknown"
        current_category = "general"
        current_section_title = ""

        lines = raw_text.split("\n")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 检测 section 标题以推断 risk_level
            heading_match = _SECTION_HEADING_RE.match(stripped)
            if heading_match:
                keyword = heading_match.group(1)
                current_risk_level = _RISK_LEVEL_KEYWORDS.get(
                    keyword, "unknown"
                )
                current_section_title = stripped.lstrip("#").strip()
                current_category = LlmResponseParser._infer_category(
                    current_section_title
                )
                continue

            # 也检查非 heading 行但包含风险关键词的标题式行
            # 如 "**高风险项目**" 或 "### 高风险检查项"
            if not heading_match:
                for kw, level in _RISK_LEVEL_KEYWORDS.items():
                    if kw in stripped and (
                        stripped.startswith("**")
                        or stripped.startswith("###")
                        or stripped.startswith("##")
                    ):
                        current_risk_level = level
                        current_section_title = stripped.strip("*#").strip()
                        current_category = (
                            LlmResponseParser._infer_category(
                                current_section_title
                            )
                        )
                        break

            # 识别未勾选项 → ReviewFinding (pass_status=False)
            unchecked_match = _UNCHECKED_RE.match(stripped)
            if unchecked_match:
                description = unchecked_match.group(1).strip()

                # 尝试提取 | 分隔的 定位 和 建议
                sheet_location = None
                suggestion = None
                if '|' in description:
                    parts = [p.strip() for p in description.split('|')]
                    description = parts[0]
                    for part in parts[1:]:
                        if part.startswith('定位:') or part.startswith('定位：'):
                            sheet_location = part.split(':', 1)[1].strip() if ':' in part else part.split('：', 1)[1].strip()
                        elif part.startswith('建议:') or part.startswith('建议：'):
                            suggestion = part.split(':', 1)[1].strip() if ':' in part else part.split('：', 1)[1].strip()

                findings.append(
                    ReviewFinding(
                        id=str(uuid.uuid4()),
                        description=description,
                        risk_level=current_risk_level,
                        pass_status=False,
                        category=current_category,
                        sheet_location=sheet_location,
                        suggestion=suggestion,
                    )
                )
                continue

            # 识别已勾选项 → ReviewFinding (pass_status=True)
            checked_match = _CHECKED_RE.match(stripped)
            if checked_match:
                description = checked_match.group(1).strip()
                findings.append(
                    ReviewFinding(
                        id=str(uuid.uuid4()),
                        description=description,
                        risk_level=current_risk_level,
                        pass_status=True,
                        category=current_category,
                        sheet_location=None,
                        suggestion=None,
                    )
                )
                continue

        # 无有效 findings → 降级
        if not findings:
            return LlmResponseParser._degrade_to_unknown(raw_text)

        return ParseResult(
            findings=findings,
            raw_text=raw_text,
            parse_success=True,
        )

    @staticmethod
    def _degrade_to_unknown(raw_text: str) -> ParseResult:
        """解析失败降级：存储原文前 500 字符为单条 unknown finding

        Requirement 8.4: 如果 LLM 输出无法解析为结构化发现，
        存储原文为单条 finding，risk_level="unknown"，pass_status=False
        """
        truncated = raw_text[:500] if raw_text else "(空输出)"
        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            description=truncated,
            risk_level="unknown",
            pass_status=False,
            category="general",
            sheet_location=None,
            suggestion=None,
        )
        return ParseResult(
            findings=[finding],
            raw_text=raw_text or "",
            parse_success=False,
        )

    @staticmethod
    def _infer_category(section_title: str) -> str:
        """从 section 标题推断发现类别"""
        for keyword, category in _CATEGORY_KEYWORDS.items():
            if keyword in section_title:
                return category
        return "general"
