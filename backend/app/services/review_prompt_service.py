"""底稿级提示词匹配加载服务

按 wp_code + sheet_name 匹配加载底稿级提示词，支持三级降级（sheet → subject → base）。
提供覆盖率统计能力，用于推广进度追踪。
"""
from __future__ import annotations

import functools
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 默认位置：backend/data/tsj_review_prompts/
_DEFAULT_TSJ_DIR = Path(__file__).resolve().parents[2] / "data" / "tsj_review_prompts"

# sheet 级提示词目录 = 单个大写循环字母（与 load_prompt 按 wp_code[0] 取目录同一规则）。
# 🔴 原先是写死的 D~N+S 集合，A/B/C 目录的提示词能被加载却不进覆盖率统计。
_CYCLE_DIR_RE = re.compile(r"[A-Z]")

# 底稿清单与科目名的权威源：致同 2025 编码表 ``wp_account_mapping.json``（D~N 前缀 89 个，与模板库
# ``gt_template_library.json`` 逐个一致）。覆盖率分母与科目级降级都按它取。
# 🔴 原先是手写的 ``_AUDIT_CYCLE_ALIASES``：按旧编码写成（G1=长期股权投资、M1=实收资本、N5=投资收益…），
#    与 2025 编码 40 个前缀错位 ⇒ 整本底稿复核（不带 sheet 名，wp_ai 即如此）加载的是别的科目的提示词；
#    覆盖率分母也只认它的键 ⇒ 7 本函证底稿（D0/E0/F0/G0/H0/K0/L0）没有提示词却从不进缺口。
_PREFIX_RE = re.compile(r"([A-Z]\d+)", re.IGNORECASE)

# 科目名与根目录科目级文件名用词不同、但确是同一科目的对照（逐条核对）。其余一律按名称精确匹配，
# 不做包含匹配：「收入」会命中「营业外收入」，「其他权益工具」（M10 权益）会命中 G8「其他权益工具投资」。
_SUBJECT_FILE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "营业收入": ("收入",),
    "营业成本": ("成本",),
    "实收资本": ("实收资本或股本",),
    "资产处置损益": ("资产处置收益",),
    "持有待售资产和负债": ("持有待售资产", "持有待售负债"),
}
# 根目录科目级文件名 = 科目名 + 后缀（「货币资金提示词」没有「审计复核」）
_SUBJECT_FILE_SUFFIXES = ("审计复核提示词", "提示词")


@dataclass(frozen=True)
class _Workpaper:
    """权威编码表里的一本底稿（以 wp_code 前缀为单位）。"""

    name: str                       # 底稿名，覆盖率缺口显示用
    subject_names: tuple[str, ...]  # 科目级降级候选：科目名 → 底稿名去「审定表」→ 同义名


@functools.lru_cache(maxsize=1)
def _authoritative_workpapers() -> dict[str, _Workpaper]:
    """wp_code 前缀 → 底稿。取前缀本身那一条（D2）；编码表没有时取该前缀的第一条（B22 → B22A-1）。"""
    from app.services.wp_mapping_service import WpMappingService  # 延迟导入：该模块带 ORM 依赖

    chosen: dict[str, dict] = {}
    for entry in WpMappingService().get_all_mappings():
        code = str(entry.get("wp_code") or "").upper()
        match = _PREFIX_RE.match(code)
        if match and (code == match.group(1) or match.group(1) not in chosen):
            chosen[match.group(1)] = entry
    out: dict[str, _Workpaper] = {}
    for prefix, entry in chosen.items():
        account = str(entry.get("account_name") or "").strip()
        wp_name = str(entry.get("wp_name") or "").strip()
        names: list[str] = []
        for name in (account, wp_name.removesuffix("审定表")):
            for candidate in (name, *_SUBJECT_FILE_SYNONYMS.get(name, ())):
                if candidate and candidate not in names:
                    names.append(candidate)
        out[prefix] = _Workpaper(name=wp_name or account or prefix, subject_names=tuple(names))
    return out


def _subject_of(stem: str) -> str:
    """根目录科目级文件 stem → 科目名。"""
    for suffix in _SUBJECT_FILE_SUFFIXES:
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _prefix_order(prefix: str) -> tuple[str, int]:
    """按循环字母、编号排序（D2 在 D10 前）。"""
    return prefix[0], int(prefix[1:])


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
    """提示词覆盖率统计（单位：底稿 = wp_code 前缀，见 ``get_coverage``）"""
    total_subjects: int               # 底稿总数（权威编码表 ∪ 有提示词的前缀）
    subjects_with_sheet_prompts: int  # 其中有 sheet 级提示词的底稿数
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

    def _resolve_note_suffix(self, wp_code: str, sheet_name: str | None) -> str | None:
        """按 wp_code 前缀派生附注 sheet 的提示词后缀（对全部循环通用）。

        "附注上市"/"附注（上市公司）K8"/"附注(上市)" → {prefix}-note-listed
        "附注国企"/"附注（国企）"                    → {prefix}-note-soe
        非附注 sheet 返回 None（交由 resolve_sheet_suffix 处理）。
        """
        if not sheet_name or not wp_code:
            return None
        lower = sheet_name.lower()
        if not (
            "附注" in sheet_name
            or "披露" in sheet_name
            or "note" in lower
            or "disclosure" in lower
        ):
            return None
        prefix_match = re.match(r"([A-Z]\d+)", wp_code, re.IGNORECASE)
        if not prefix_match:
            return None
        prefix = prefix_match.group(1).upper()
        if "国企" in sheet_name or "soe" in lower:
            return f"{prefix}-note-soe"
        if "上市" in sheet_name or "listed" in lower:
            return f"{prefix}-note-listed"
        # 单一附注（无上市/国企变体，如 N3）默认按 note-listed
        return f"{prefix}-note-listed"

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
            # 附注 sheet 名（"附注上市"/"附注（国企）"等）不含底稿编码，
            # 无法由 resolve_sheet_suffix 提取，故按 wp_code 前缀派生
            # {prefix}-note-listed / {prefix}-note-soe（对全部循环通用，
            # 与 D2 既有的 _SHEET_NAME_ALIASES 行为一致且向后兼容）。
            suffix = self._resolve_note_suffix(wp_code, sheet_name) or \
                self.resolve_sheet_suffix(sheet_name)
            if suffix:
                cycle_letter = wp_code[0].upper() if wp_code else ""
                sheet_path = self._base_dir / cycle_letter / f"{suffix}.md"
                if sheet_path.is_file():
                    content = self._read_file(sheet_path)
                    if content:
                        return self._build_result(
                            content, "sheet", str(sheet_path)
                        )

        # Level 1b: 裸 wp_code 作为底稿级文件名（单 sheet 底稿，如 A9/B15/C1/B1A/A17-5-1）。
        # A/B/C 循环大量底稿是单 sheet（sheet_name 无 "-N" 后缀，resolve_sheet_suffix
        # 提取不到），故按 wp_code 直接匹配 {cycle}/{wp_code}.md。对 D~N 无影响
        # （这些循环不存在裸 wp_code 的 .md 文件，命中 is_file() 失败后照常降级）。
        if wp_code:
            cyc = wp_code[0].upper()
            bare_path = self._base_dir / cyc / f"{wp_code}.md"
            if bare_path.is_file():
                content = self._read_file(bare_path)
                if content:
                    return self._build_result(content, "sheet", str(bare_path))

        # Level 2: Subject-level prompt (keyword matching)
        subject_result = self._load_subject_prompt(wp_code)
        if subject_result:
            return subject_result

        # Level 3: Base template
        return self._build_result(
            _BASE_REVIEW_PROMPT, "base", None
        )

    def _load_subject_prompt(self, wp_code: str) -> PromptResult | None:
        """按权威编码表里该底稿的科目名，精确匹配根目录科目级文件（D2-1 → D2 → 应收账款）。

        编码表里没有的前缀、或该科目没有科目级文件 ⇒ None（交给 base），不拿相近科目顶替。
        """
        prefix_match = _PREFIX_RE.match(wp_code or "")
        if not prefix_match or not self._base_dir.is_dir():
            return None
        workpaper = _authoritative_workpapers().get(prefix_match.group(1).upper())
        if workpaper is None:
            return None

        by_subject = {_subject_of(f.stem): f for f in sorted(self._base_dir.glob("*.md"))}
        for name in workpaper.subject_names:
            path = by_subject.get(name)
            content = self._read_file(path) if path else None
            if content:
                return self._build_result(content, "subject", str(path))
        return None

    # ------------------------------------------------------------------
    # Task 2.3: get_coverage
    # ------------------------------------------------------------------

    def get_coverage(self) -> CoverageReport:
        """统计提示词覆盖率，四个字段统一以底稿（wp_code 前缀，如 D2 / G10）为单位。

        - sheet_breakdown: {前缀: [sheet 后缀]}，扫描全部单字母循环目录（与 load_prompt 同一规则）
        - total_subjects: 底稿总数 = 权威编码表全部底稿（A~N 与 S，D~N 89 本全在内）∪ 有 sheet 级文件的前缀
        - subjects_with_sheet_prompts: 有 sheet 级文件的底稿数
        - missing_gaps: 还没有 sheet 级文件的底稿（附底稿名），按循环、编号排序

        恒有 ``total_subjects == subjects_with_sheet_prompts + len(missing_gaps)``。
        🔴 preexisting-test-failures-closure G12 两轮：① total 原数根目录科目级文件（67）、with_sheet
        数前缀（82），单位混比；② 改成前缀后分母取手写别名表的键 —— 表外底稿（7 本函证、A/B/C/S）
        有没有提示词都不进统计，缺口只剩 S1 一条。
        """
        sheet_breakdown: dict[str, list[str]] = {}
        if self._base_dir.is_dir():
            for cycle_dir in sorted(self._base_dir.iterdir()):
                if not (cycle_dir.is_dir() and _CYCLE_DIR_RE.fullmatch(cycle_dir.name)):
                    continue
                for md_file in sorted(cycle_dir.glob("*.md")):
                    fname = md_file.stem  # e.g. "D2-1", "D2-note-listed"
                    prefix_match = re.match(r"([A-Z]\d+)", fname, re.IGNORECASE)
                    if not prefix_match:
                        continue  # 无 wp_code 前缀的说明文件（如 F/_RESERVED_SHEETS.md）
                    prefix = prefix_match.group(1).upper()
                    suffix = fname[len(prefix):]
                    if suffix.startswith("-"):
                        suffix = suffix[1:]  # 去掉前导 -
                    sheet_breakdown.setdefault(prefix, []).append(suffix or fname)

        covered = set(sheet_breakdown)
        authoritative = _authoritative_workpapers()
        known = covered | set(authoritative)
        # known - covered ⊆ authoritative：缺口只可能是编码表里的底稿
        missing_gaps = [
            f"{prefix} ({authoritative[prefix].name})"
            for prefix in sorted(known - covered, key=_prefix_order)
        ]

        return CoverageReport(
            total_subjects=len(known),
            subjects_with_sheet_prompts=len(covered),
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
