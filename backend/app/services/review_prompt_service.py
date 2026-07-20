"""底稿级提示词匹配加载服务

按 wp_code + sheet_name 匹配加载底稿级提示词，支持三级降级（sheet → subject → base）。
提供覆盖率统计能力，用于推广进度追踪。
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 默认位置：backend/data/tsj_review_prompts/
_DEFAULT_TSJ_DIR = Path(__file__).resolve().parents[2] / "data" / "tsj_review_prompts"

# 支持的 cycle letter 目录
_CYCLE_LETTERS = {"D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "S"}

# wp_code 前缀 → 科目关键词映射（用于 subject-level 降级匹配）
_AUDIT_CYCLE_ALIASES: dict[str, list[str]] = {
    "D1": ["应收票据"],
    "D2": ["应收账款"],
    "D3": ["预收账款", "预收款项", "合同负债"],
    "D4": ["收入", "营业收入"],
    "D5": ["应收款项融资"],
    "D6": ["合同资产"],
    "D7": ["其他应收款", "其他应收"],
    "E1": ["货币资金", "现金"],
    "F1": ["预付账款", "预付款项"],
    "F2": ["存货"],
    "F3": ["应付票据"],
    "F4": ["应付账款"],
    "F5": ["成本", "营业成本"],
    "G1": ["长期股权投资"],
    "G2": ["债权投资"],
    "G3": ["其他债权投资"],
    "G4": ["其他权益工具"],
    "G5": ["长期应收款"],
    "G6": ["持有待售资产"],
    "G7": ["长期股权投资"],
    "G8": ["投资性房地产"],
    "G9": ["固定资产"],
    "G10": ["在建工程"],
    "G11": ["无形资产"],
    "G12": ["开发支出"],
    "G13": ["商誉"],
    "G14": ["长期待摊费用"],
    "H1": ["固定资产"],
    "H2": ["在建工程"],
    "H3": ["投资性房地产"],
    "H4": ["无形资产"],
    "H5": ["固定资产"],
    "H6": ["使用权资产"],
    "H7": ["固定资产"],
    "H8": ["在建工程"],
    "H9": ["无形资产"],
    "H10": ["长期待摊费用"],
    "I1": ["无形资产"],
    "I2": ["研发费用", "开发支出"],
    "I3": ["无形资产"],
    "I4": ["商誉"],
    "I5": ["长期待摊费用"],
    "I6": ["递延所得税"],
    "J1": ["应付职工薪酬"],
    "J2": ["长期应付职工薪酬"],
    "J3": ["股份支付"],
    "K1": ["其他应收款"],
    "K2": ["其他流动资产"],
    "K3": ["其他应付款"],
    "K4": ["其他流动负债"],
    "K5": ["预计负债"],
    "K6": ["持有待售"],
    "K7": ["递延收益"],
    "K8": ["销售费用"],
    "K9": ["管理费用"],
    "K10": ["其他收益"],
    "K11": ["资产减值损失"],
    "K12": ["营业外收入"],
    "K13": ["营业外支出"],
    "L1": ["短期借款"],
    "L2": ["应付利息"],
    "L3": ["长期借款"],
    "L4": ["应付债券"],
    "L5": ["一年内到期的非流动负债"],
    "L6": ["长期应付款"],
    "L7": ["租赁负债"],
    "L8": ["其他非流动负债"],
    "M1": ["实收资本", "股本"],
    "M2": ["资本公积"],
    "M3": ["库存股"],
    "M4": ["盈余公积"],
    "M5": ["未分配利润"],
    "M6": ["未分配利润"],
    "M7": ["其他综合收益"],
    "M8": ["专项储备"],
    "M9": ["少数股东权益"],
    "M10": ["应付股利"],
    "N1": ["财务费用"],
    "N2": ["应交税费", "税金及附加"],
    "N3": ["所得税费用"],
    "N4": ["研发费用"],
    "N5": ["投资收益"],
    "S1": ["审计方案", "总体"],
}

# sheet_suffix 正则：支持"审定表D2-1"、"D2-note-listed"等多种格式
# 匹配规则：字母+数字+可选后续部分（数字后缀或英文标识符）
_SHEET_SUFFIX_RE = re.compile(
    r"([A-Z]\d+(?:-\d+|-[a-z]+(?:-[a-z]+)*))",
    re.IGNORECASE,
)

# 无编码后缀的中文 sheet 名 → 提示词文件 stem（与 GtD2 currentSheet 映射对齐）
_SHEET_NAME_ALIASES: list[tuple[str, str]] = [
    ("截止测试", "D2-cutoff"),
    ("附注上市", "D2-note-listed"),
    ("附注国企", "D2-note-soe"),
]


@dataclass
class RiskArea:
    """风险领域"""
    level: str   # "high" | "medium" | "low"
    text: str


@dataclass
class PromptResult:
    """提示词加载结果"""
    content: str                    # 完整提示词文本
    source_level: str               # "sheet" | "subject" | "base"
    file_path: str | None           # 来源文件路径
    tips: list[str] = field(default_factory=list)
    checklist: list[str] = field(default_factory=list)
    risk_areas: list[RiskArea] = field(default_factory=list)
    version: str = ""               # 提示词版本号（从 YAML front-matter 解析）


@dataclass
class CoverageReport:
    """提示词覆盖率统计"""
    total_subjects: int
    subjects_with_sheet_prompts: int
    sheet_breakdown: dict[str, list[str]]  # {wp_code_prefix: [suffixes]}
    missing_gaps: list[str]


class ReviewPromptService:
    """底稿级提示词匹配加载服务"""

    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir or Path(
            os.environ.get("TSJ_KNOWLEDGE_DIR") or _DEFAULT_TSJ_DIR
        )

    # ------------------------------------------------------------------
    # Task 2.1: resolve_sheet_suffix
    # ------------------------------------------------------------------

    def resolve_sheet_suffix(self, sheet_name: str) -> str | None:
        """从 sheet_name 提取底稿编号后缀

        支持多种格式：
        - "审定表D2-1" → "D2-1"
        - "明细表D2-2" → "D2-2"
        - "D2-note-listed" → "D2-note-listed"
        - "坏账准备D2-3" → "D2-3"
        - "凭证检查表D2-7" → "D2-7"

        Returns:
            提取到的后缀字符串，或 None（无法匹配时）
        """
        if not sheet_name:
            return None

        match = _SHEET_SUFFIX_RE.search(sheet_name)
        if match:
            return match.group(1)

        for keyword, suffix in _SHEET_NAME_ALIASES:
            if keyword in sheet_name:
                return suffix

        return None

    # ------------------------------------------------------------------
    # Task 2.2: load_prompt
    # ------------------------------------------------------------------

    def load_prompt(
        self, wp_code: str, sheet_name: str | None = None
    ) -> PromptResult:
        """三级降级加载提示词

        Level 1 (sheet-level): {base_dir}/{cycle_letter}/{wp_code}-{suffix}.md
        Level 2 (subject-level): 关键词匹配科目级文件
        Level 3 (base): 通用复核基础模板

        Args:
            wp_code: 底稿编码，如 "D2"
            sheet_name: 底稿 sheet 名称（可选），如 "审定表D2-1"

        Returns:
            PromptResult 包含内容、来源级别、文件路径及解析后的结构化段落
        """
        # Level 1: Sheet-level prompt
        if sheet_name:
            suffix = self.resolve_sheet_suffix(sheet_name)
            if suffix:
                cycle_letter = wp_code[0].upper() if wp_code else ""
                sheet_path = self._base_dir / cycle_letter / f"{suffix}.md"
                if sheet_path.is_file():
                    content = self._read_file(sheet_path)
                    if content:
                        return self._build_result(
                            content, "sheet", str(sheet_path)
                        )

        # Level 2: Subject-level prompt (keyword matching)
        subject_result = self._load_subject_prompt(wp_code)
        if subject_result:
            return subject_result

        # Level 3: Base template
        return self._build_result(
            _BASE_REVIEW_PROMPT, "base", None
        )

    def _load_subject_prompt(self, wp_code: str) -> PromptResult | None:
        """按 wp_code 前缀匹配科目级提示词文件"""
        if not wp_code:
            return None

        # 提取 wp_code 前缀（如 D2-1 → D2, D2 → D2）
        prefix_match = re.match(r"([A-Z]\d+)", wp_code, re.IGNORECASE)
        if not prefix_match:
            return None
        prefix = prefix_match.group(1).upper()

        # 获取该前缀对应的科目关键词
        keywords = _AUDIT_CYCLE_ALIASES.get(prefix, [])
        if not keywords:
            # 尝试仅用 cycle_letter 匹配（如 D → 应收相关所有）
            return None

        # 扫描根目录下所有 .md 文件匹配关键词
        if not self._base_dir.is_dir():
            return None

        best_file: Path | None = None
        best_score = 0

        for md_file in self._base_dir.glob("*.md"):
            fname = md_file.stem  # 去掉 .md 后缀
            score = 0
            for kw in keywords:
                # 匹配文件名中的关键词
                name_core = re.sub(r"审计复核提示词$", "", fname)
                if kw in name_core:
                    score += 2
                elif kw in fname:
                    score += 1
            if score > best_score:
                best_score = score
                best_file = md_file

        if best_file and best_score > 0:
            content = self._read_file(best_file)
            if content:
                return self._build_result(content, "subject", str(best_file))

        return None

    # ------------------------------------------------------------------
    # Task 2.3: get_coverage
    # ------------------------------------------------------------------

    def get_coverage(self) -> CoverageReport:
        """统计提示词覆盖率

        扫描文件系统按 cycle_letter 目录聚合，统计：
        - total_subjects: 根级 .md 文件数（69 个科目级）
        - subjects_with_sheet_prompts: 有 sheet-level 提示词的科目数
        - sheet_breakdown: {wp_code_prefix: [suffixes]}
        - missing_gaps: 有科目级但无 sheet-level 的科目列表
        """
        # 统计根级科目文件
        root_md_files: list[str] = []
        if self._base_dir.is_dir():
            for f in self._base_dir.iterdir():
                if f.is_file() and f.suffix == ".md" and "审计复核提示词" in f.stem:
                    root_md_files.append(f.stem)

        total_subjects = len(root_md_files)

        # 扫描各 cycle_letter 子目录
        sheet_breakdown: dict[str, list[str]] = {}
        covered_prefixes: set[str] = set()

        for letter in _CYCLE_LETTERS:
            cycle_dir = self._base_dir / letter
            if not cycle_dir.is_dir():
                continue

            for md_file in cycle_dir.glob("*.md"):
                fname = md_file.stem  # e.g. "D2-1", "D2-note-listed"
                # 提取 wp_code 前缀（字母+数字部分）
                prefix_match = re.match(r"([A-Z]\d+)", fname, re.IGNORECASE)
                if prefix_match:
                    prefix = prefix_match.group(1).upper()
                    if prefix not in sheet_breakdown:
                        sheet_breakdown[prefix] = []
                    # suffix = 前缀之后的部分
                    suffix = fname[len(prefix):]
                    if suffix.startswith("-"):
                        suffix = suffix[1:]  # 去掉前导 -
                    sheet_breakdown[prefix].append(suffix or fname)
                    covered_prefixes.add(prefix)

        subjects_with_sheet_prompts = len(covered_prefixes)

        # 找出缺口（有科目级文件但无 sheet-level）
        # 根据 _AUDIT_CYCLE_ALIASES 列出所有已知 prefix，检查哪些没有 sheet-level
        missing_gaps: list[str] = []
        for prefix in sorted(_AUDIT_CYCLE_ALIASES.keys()):
            if prefix not in covered_prefixes:
                keywords = _AUDIT_CYCLE_ALIASES.get(prefix, [])
                label = f"{prefix} ({keywords[0]})" if keywords else prefix
                missing_gaps.append(label)

        return CoverageReport(
            total_subjects=total_subjects,
            subjects_with_sheet_prompts=subjects_with_sheet_prompts,
            sheet_breakdown=sheet_breakdown,
            missing_gaps=missing_gaps,
        )

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    def _read_file(self, path: Path) -> str | None:
        """安全读取文件内容"""
        try:
            return path.read_text(encoding="utf-8-sig")
        except Exception as e:
            logger.warning("Failed to read file %s: %s", path, e)
            return None

    def _build_result(
        self, content: str, source_level: str, file_path: str | None
    ) -> PromptResult:
        """构建 PromptResult，同时解析 YAML front-matter 和 tips/checklist/risk_areas"""
        version = ""
        content_for_parsing = content

        # Parse YAML front-matter if present
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    try:
                        import yaml
                        meta = yaml.safe_load(parts[1])
                    except ImportError:
                        # Fallback: extract version with regex
                        vm = re.search(r'version:\s*"?([^"\n]+)', parts[1])
                        meta = {"version": vm.group(1).strip() if vm else ""}
                    if isinstance(meta, dict):
                        version = meta.get("version", "")
                    # Remove front-matter from content passed to tips/checklist parsers
                    content_for_parsing = parts[2]
                except Exception:
                    content_for_parsing = content
            else:
                content_for_parsing = content

        tips = self._parse_tips(content_for_parsing)
        checklist = self._parse_checklist(content_for_parsing)
        risk_areas = self._parse_risk_areas(content_for_parsing)

        return PromptResult(
            content=content,  # Keep full content including front-matter for LLM
            source_level=source_level,
            file_path=file_path,
            tips=tips,
            checklist=checklist,
            risk_areas=risk_areas,
            version=version,
        )

    @staticmethod
    def _parse_tips(content: str) -> list[str]:
        """从 ## tips 节提取审计要点"""
        tips: list[str] = []
        in_tips_section = False

        for line in content.split("\n"):
            stripped = line.strip()
            # 进入 tips section
            if re.match(r"^##\s+tips", stripped, re.IGNORECASE):
                in_tips_section = True
                continue
            # 遇到下一个 ## 离开
            if in_tips_section and stripped.startswith("## "):
                break
            if in_tips_section and stripped:
                # 提取编号行（如 "1. **xxx**：..." 或 "- xxx"）
                # 去除 markdown 格式
                text = re.sub(r"^\d+\.\s*", "", stripped)
                text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
                text = text.lstrip("- ").strip()
                if text and len(text) > 4:
                    tips.append(text)

        return tips

    @staticmethod
    def _parse_checklist(content: str) -> list[str]:
        """从 ## checklist 节提取检查清单项"""
        items: list[str] = []
        in_checklist_section = False

        for line in content.split("\n"):
            stripped = line.strip()
            if re.match(r"^##\s+checklist", stripped, re.IGNORECASE):
                in_checklist_section = True
                continue
            if in_checklist_section and re.match(r"^##\s+(?!#)", stripped):
                break
            if in_checklist_section and stripped.startswith("- [ ]"):
                item = stripped[5:].strip()
                if item:
                    items.append(item)

        return items

    @staticmethod
    def _parse_risk_areas(content: str) -> list[RiskArea]:
        """从 ## risk_areas 节提取风险领域"""
        areas: list[RiskArea] = []
        in_risk_section = False
        current_level = ""

        for line in content.split("\n"):
            stripped = line.strip()
            if re.match(r"^##\s+risk_areas", stripped, re.IGNORECASE):
                in_risk_section = True
                continue
            if in_risk_section and re.match(r"^##\s+(?!#)", stripped):
                break
            if not in_risk_section:
                continue

            # 检测风险等级 header
            if re.match(r"^###\s*.*高风险", stripped):
                current_level = "high"
            elif re.match(r"^###\s*.*中风险", stripped):
                current_level = "medium"
            elif re.match(r"^###\s*.*低风险", stripped):
                current_level = "low"
            elif current_level and re.match(r"^\d+\.\s+\*\*(.+?)\*\*", stripped):
                # 提取编号+加粗的风险项
                m = re.match(r"^\d+\.\s+\*\*(.+?)\*\*[：:]\s*(.+)?", stripped)
                if m:
                    text = f"{m.group(1)}：{m.group(2)}" if m.group(2) else m.group(1)
                    areas.append(RiskArea(level=current_level, text=text))
                else:
                    # fallback: 去掉编号和格式
                    text = re.sub(r"^\d+\.\s*", "", stripped)
                    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
                    if text:
                        areas.append(RiskArea(level=current_level, text=text))
            elif current_level and stripped.startswith("- "):
                text = stripped[2:].strip()
                if text:
                    areas.append(RiskArea(level=current_level, text=text))

        return areas


# 通用复核基础模板（Level 3 降级）
_BASE_REVIEW_PROMPT = """你是审计师，请对审计底稿进行智能复核。

## tips

1. 审计认定检查：存在性、完整性、权利和义务、计价或分摊、准确性、分类和截止
2. 程序执行检查：审计程序是否完整执行、样本量是否充分、替代程序是否充分
3. 数据完整性检查：勾稽关系是否正确、小计合计是否准确、期初期末是否连续
4. 风险评估复核：异常事项是否标注、高风险领域是否充分关注、审计结论是否有证据支持

## checklist

- [ ] 审计程序是否完整执行
- [ ] 样本量是否充分（覆盖率≥重要性水平）
- [ ] 勾稽关系是否正确（合计/小计/交叉引用）
- [ ] 异常事项是否充分标注和解释
- [ ] 审计结论是否有充分证据支持
- [ ] 底稿编制是否符合事务所质量标准

## risk_areas

### 高风险

- 审计程序未完整执行可能导致错报未被发现
- 重大异常事项未充分关注可能影响审计意见

### 中风险

- 样本量不充分可能无法推断总体
- 勾稽关系断裂可能影响数据可靠性

### 低风险

- 底稿格式不规范影响复核效率
- 交叉索引不完整增加复核难度
"""
