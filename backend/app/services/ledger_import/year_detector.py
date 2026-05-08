"""年度自动识别 — 文件名 → sheet 名 → 元信息 → 内容众数 → 默认上年。

职责（见 design.md §16 / Sprint 1 Task 8 / requirements 需求 13）：

优先级（首个命中即返回；多源命中时高优先级胜出，低优先级作为冲突证据记录）：

| P | 来源              | 置信度 | 算法                                              |
|---|-------------------|--------|---------------------------------------------------|
| 1 | 文件名            | 95     | ``r"(20[0-9]{2})\\s*(?:年度?|年|YEAR)?"``          |
| 2 | Sheet 名          | 90     | 同上                                              |
| 3 | 表头前 10 行文本  | 85     | ``会计期间[:：]?\\s*(20\\d{2})[-/年]\\s*(\\d{1,2})`` |
|   |                   |        | 或 ``(20\\d{2})\\s*年度``                          |
| 4 | 数据区日期众数    | 75     | ``(20\\d{2})[-/年](\\d{1,2})`` 跨单元格统计众数    |
| 5 | 默认当前年-1      | 30     | ``datetime.now().year - 1``（审计通常做上年账套） |

冲突处理：高优先级命中覆盖低优先级，若低优先级与高优先级年份不一致，evidence
字段中记录 ``"conflict": True``，供前端弹警告。

范围约束：有效年份 2000-2100（规避 "20000" / "20999" 等假阳性）。

使用示例::

    from backend.app.services.ledger_import.year_detector import detect_year
    year, confidence, evidence = detect_year(files)
    if evidence.get("conflict"):
        # 提示用户确认
        ...
"""

import re
from collections import Counter
from datetime import datetime
from typing import Optional

from .detection_types import FileDetection

__all__ = ["detect_year", "detect_year_from_text"]


# ---------------------------------------------------------------------------
# 正则（模块级编译，复用）
# ---------------------------------------------------------------------------

# P1 / P2：文件名、sheet 名中的 4 位年份（可选尾缀"年"/"年度"/"YEAR"）
_YEAR_NAME_RE = re.compile(r"(20[0-9]{2})\s*(?:年度?|年|YEAR)?")

# P3：会计期间元信息（"会计期间: 2025-01 ~ 2025-12"）
_METADATA_PERIOD_RE = re.compile(r"会计期间[:：]?\s*(20\d{2})[-/年]\s*(\d{1,2})")

# P3：年度声明（"2025 年度"）
_METADATA_YEAR_RE = re.compile(r"(20\d{2})\s*年度")

# P4：数据区日期单元格（"2025-01-01" / "2025/1/1" / "2025年1月1日"）
_DATE_CELL_RE = re.compile(r"(20\d{2})[-/年](\d{1,2})")

# 独立 4 位年份（供 ``detect_year_from_text`` 导出）
_STANDALONE_YEAR_RE = re.compile(r"\b(20\d{2})\b")

_YEAR_MIN = 2000
_YEAR_MAX = 2100


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _valid_year(y: int) -> bool:
    """年份是否在合法区间 [2000, 2100]。"""

    return _YEAR_MIN <= y <= _YEAR_MAX


def _mode_year(years: list[int]) -> Optional[tuple[int, Counter]]:
    """返回 (众数年份, 全量计数器)；无有效年份返回 ``None``。"""

    valid = [y for y in years if _valid_year(y)]
    if not valid:
        return None
    counter: Counter = Counter(valid)
    year, _ = counter.most_common(1)[0]
    return year, counter


def _scan_names(names: list[str]) -> tuple[Optional[int], list[str]]:
    """对一批名称（文件名或 sheet 名）跑 P1/P2 正则。

    返回 ``(众数年份, 命中原串列表)``；无命中时第一个元素为 ``None``。
    """

    years: list[int] = []
    matches: list[str] = []
    for name in names:
        if not name:
            continue
        hit = False
        for m in _YEAR_NAME_RE.finditer(name):
            y = int(m.group(1))
            if _valid_year(y):
                years.append(y)
                hit = True
        if hit:
            matches.append(name)
    picked = _mode_year(years)
    if picked is None:
        return None, matches
    return picked[0], matches


def _scan_metadata(files: list[FileDetection]) -> tuple[Optional[int], list[str]]:
    """扫描每个 sheet 的 ``preview_rows[:10]`` 找元信息年份（P3）。"""

    years: list[int] = []
    matches: list[str] = []
    for fd in files:
        for sheet in fd.sheets:
            parts: list[str] = []
            for row in sheet.preview_rows[:10]:
                for cell in row:
                    if cell is None:
                        continue
                    parts.append(str(cell))
            text = " ".join(parts)
            if not text:
                continue
            for m in _METADATA_PERIOD_RE.finditer(text):
                y = int(m.group(1))
                if _valid_year(y):
                    years.append(y)
                    matches.append(m.group(0))
            for m in _METADATA_YEAR_RE.finditer(text):
                y = int(m.group(1))
                if _valid_year(y):
                    years.append(y)
                    matches.append(m.group(0))
    picked = _mode_year(years)
    if picked is None:
        return None, matches
    return picked[0], matches


def _scan_content(files: list[FileDetection]) -> tuple[Optional[int], dict[int, int]]:
    """扫描 ``preview_rows[data_start_row:]`` 中的日期单元格并计算众数（P4）。"""

    years: list[int] = []
    for fd in files:
        for sheet in fd.sheets:
            start = max(0, sheet.data_start_row)
            for row in sheet.preview_rows[start:]:
                for cell in row:
                    if cell is None:
                        continue
                    s = str(cell)
                    if not s:
                        continue
                    for m in _DATE_CELL_RE.finditer(s):
                        y = int(m.group(1))
                        if _valid_year(y):
                            years.append(y)
    picked = _mode_year(years)
    if picked is None:
        return None, {}
    year, counter = picked
    # dict(counter) 按插入顺序序列化，对调用方友好
    return year, dict(counter)


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


def detect_year_from_text(text: str) -> Optional[int]:
    """从任意文本中提取首个合法 4 位年份（2000-2100）。

    作为通用工具函数，供其他模块（如 identifier）在探测到"年度"字眼
    时复用，无需重新拼正则。返回 ``None`` 表示无命中。
    """

    if not text:
        return None
    for m in _STANDALONE_YEAR_RE.finditer(text):
        y = int(m.group(1))
        if _valid_year(y):
            return y
    return None


def detect_year(
    files: list[FileDetection],
) -> tuple[Optional[int], int, dict]:
    """识别账套年度。

    参数：
        files: 预检阶段识别到的文件列表。

    返回：
        ``(detected_year, confidence_0_100, evidence)``。

        - ``detected_year``：识别到的年份；无文件时为 ``None``
        - ``confidence``：0-100，参见模块文档表格
        - ``evidence``：证据字典，仅包含实际命中的优先级条目 +
          ``chosen_priority`` 字段（字符串）；多源年份不一致时追加
          ``"conflict": True``；无文件时为 ``{"empty": True}``

    示例返回::

        (
            2025,
            95,
            {
                "p1_filename": {"year": 2025, "matches": ["2025年度 科目.xlsx"]},
                "p4_content_mode": {"year": 2024, "counts": {2024: 120, 2025: 3}},
                "conflict": True,
                "chosen_priority": "p1_filename",
            },
        )
    """

    if not files:
        return None, 0, {"empty": True}

    evidence: dict = {}
    chosen_year: Optional[int] = None
    chosen_conf: int = 0
    chosen_priority: Optional[str] = None

    # ---- P1：文件名 ----
    p1_year, p1_matches = _scan_names([fd.file_name for fd in files])
    if p1_year is not None:
        evidence["p1_filename"] = {"year": p1_year, "matches": p1_matches}
        chosen_year, chosen_conf, chosen_priority = p1_year, 95, "p1_filename"

    # ---- P2：Sheet 名 ----
    sheet_names: list[str] = [s.sheet_name for fd in files for s in fd.sheets]
    p2_year, p2_matches = _scan_names(sheet_names)
    if p2_year is not None:
        evidence["p2_sheet_name"] = {"year": p2_year, "matches": p2_matches}
        if chosen_priority is None:
            chosen_year, chosen_conf, chosen_priority = p2_year, 90, "p2_sheet_name"

    # ---- P3：元信息 ----
    p3_year, p3_matches = _scan_metadata(files)
    if p3_year is not None:
        evidence["p3_metadata"] = {"year": p3_year, "matches": p3_matches}
        if chosen_priority is None:
            chosen_year, chosen_conf, chosen_priority = p3_year, 85, "p3_metadata"

    # ---- P4：内容众数 ----
    p4_year, p4_counts = _scan_content(files)
    if p4_year is not None:
        evidence["p4_content_mode"] = {"year": p4_year, "counts": p4_counts}
        if chosen_priority is None:
            chosen_year, chosen_conf, chosen_priority = p4_year, 75, "p4_content_mode"

    # ---- 冲突检测：各优先级命中年份不一致 ----
    hit_years = {
        info["year"]
        for key, info in evidence.items()
        if isinstance(info, dict) and "year" in info
    }
    if len(hit_years) > 1:
        evidence["conflict"] = True

    # ---- P5：默认上年 ----
    if chosen_priority is None:
        default_year = datetime.now().year - 1
        evidence["p5_default"] = {"year": default_year}
        chosen_year, chosen_conf, chosen_priority = default_year, 30, "p5_default"

    evidence["chosen_priority"] = chosen_priority

    return chosen_year, chosen_conf, evidence
