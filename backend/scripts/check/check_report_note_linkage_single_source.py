#!/usr/bin/env python
"""report→note linkage 单一真源守卫（disclosure-note-formula-and-report-sync Task 6.2）

断言「报表行 row_code → 附注单元格」映射只有唯一真源 ``ReportNoteLinkage``
（``report_note_linkage.py`` + 回退配置 ``data/disclosure/report_note_linkage.json``），
禁止在 ``backend/app/services`` 其它文件出现：

  ① **第二处硬编码映射**：把报表行码映射到附注章节+单元格坐标的字面量
     （signature = ``note_section`` 与 ``R{n}C{n}`` 风格 ``cell`` 邻近共现）。
  ② **绕过 ReportNoteLinkage 的 report→note 单元格写入**：同一文件既读报表金额
     （``FinancialReport`` / ``current_period_amount``）又写附注单元格
     （``DisclosureNote`` 上下文 + 单元格写标记），却未引用 ``ReportNoteLinkage``。

Validates: Requirements 4.4 / 8.1（单一真源，同步与求值共用；无第二处映射）

用法:
    python backend/scripts/check/check_report_note_linkage_single_source.py [--strict]

--strict：发现违规 → 退出码 1（阻断 CI）。非 strict 仅报告不阻断。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# UTF-8 stdout（防 Windows GBK 控制台崩溃）
try:  # pragma: no cover - 环境相关
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

# 仓库根：本文件位于 backend/scripts/check/
ROOT = Path(__file__).resolve().parents[3]
SERVICES_DIR = ROOT / "backend" / "app" / "services"

# linkage 唯一真源（映射所有者）+ 唯一允许的消费者
LINKAGE_OWNER = "report_note_linkage.py"
LINKAGE_CONSUMER = "report_note_sync_service.py"

# ── 检测标记 ──
# report→note 映射字面量 signature：note_section 与 R{n}C{n} 风格 cell 邻近共现
_NOTE_SECTION_RE = re.compile(r"['\"]?note_section['\"]?\s*[:=]")
_CELL_COORD_RE = re.compile(r"['\"][Rr]\d+[Cc]\d+['\"]")  # "R9C2"

# 报表金额来源标记
_REPORT_SOURCE_MARKERS = ("FinancialReport", "current_period_amount")
# 附注单元格写入标记（在 DisclosureNote 上下文中改单元格）
_NOTE_CELL_WRITE_MARKERS = (
    "merge_table_data_preserving_cell_modes",
    ".table_data =",
    "_cell_meta",
    "_cell_modes",
)
_LINKAGE_REF = "ReportNoteLinkage"

# 合法的 report→note 写入机制（单一真源一致）：
#   ① 经 ReportNoteLinkage（集中真源）
#   ② 经附注「逐格 Cell_Binding / REPORT 公式 token」——按 Design 决策3，就地绑定
#      是优先真源（ReportNoteLinkage.report_targets_in_note 扫的正是这些 binding），
#      逐格公式求值（dispatch_resolver / resolve_formula / NoteFormulaEvaluator /
#      execute_note_formulas / REPORT(...) token / report_row_code 逐行字段）与集中真源
#      同源，不构成「第二处硬编码外部映射」。
# 只有既读报表、又写附注单元格、且不经上述任一机制的文件才判为绕过。
_ALLOWED_MECHANISM_MARKERS = (
    _LINKAGE_REF,
    "dispatch_resolver",
    "resolve_formula",
    "NoteFormulaEvaluator",
    "execute_note_formulas",
    "REPORT(",
    "report_row_code",
)

# 显式豁免（相对 services 的文件名 → 原因）
ALLOWLIST: dict[str, str] = {
    LINKAGE_OWNER: "linkage 单一真源所有者",
    LINKAGE_CONSUMER: "唯一允许经 ReportNoteLinkage 消费的同步服务",
    "triple_format_adapter.py": (
        "多模块格式适配器：FinancialReport 引用属 report_to_structure（财报↔结构）"
        "另一模块，note 写入来自编辑器 structure 而非报表金额，非 report→note 映射"
    ),
}


def _find_second_mapping(text: str) -> bool:
    """检测硬编码 report→note 映射字面量：note_section 与 R{n}C{n} cell 在 300 字符窗口内共现。"""
    for m in _CELL_COORD_RE.finditer(text):
        window = text[max(0, m.start() - 300): m.end() + 300]
        if _NOTE_SECTION_RE.search(window):
            return True
    return False


def _is_bypass_write(text: str) -> bool:
    """检测绕过 linkage 的 report→note 单元格写入：读报表 + 写附注单元格 + 未引用 linkage。"""
    reads_report = any(mk in text for mk in _REPORT_SOURCE_MARKERS)
    if not reads_report:
        return False
    if "DisclosureNote" not in text:
        return False
    writes_note_cell = any(mk in text for mk in _NOTE_CELL_WRITE_MARKERS)
    if not writes_note_cell:
        return False
    # 经合法机制（集中 linkage 或逐格 binding/公式）→ 非绕过
    if any(mk in text for mk in _ALLOWED_MECHANISM_MARKERS):
        return False
    return True


def main() -> int:
    strict = "--strict" in sys.argv
    if not SERVICES_DIR.is_dir():
        print(f"[skip] services dir not found: {SERVICES_DIR}")
        return 0

    owner_present = (SERVICES_DIR / LINKAGE_OWNER).exists()
    violations: list[tuple[str, str]] = []
    scanned = 0

    for path in sorted(SERVICES_DIR.glob("*.py")):
        name = path.name
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        if name in ALLOWLIST:
            continue
        if _find_second_mapping(text):
            violations.append((name, "硬编码 report→note 映射字面量（note_section+RxCx）"))
        if _is_bypass_write(text):
            violations.append((name, "绕过 ReportNoteLinkage 的 report→note 单元格写入"))

    print("=" * 70)
    print("report→note linkage 单一真源守卫 (Task 6.2)")
    print("=" * 70)
    print(f"扫描 services *.py: {scanned}")
    print(f"linkage 单一真源存在: {'是' if owner_present else '否'}  ({LINKAGE_OWNER})")
    print("豁免:")
    for fn, reason in ALLOWLIST.items():
        print(f"  [~] {fn}  # {reason}")

    if not owner_present:
        print(f"\n[FAIL] 缺少 linkage 单一真源 {LINKAGE_OWNER}")
        return 1 if strict else 0

    if violations:
        print(f"\n-- 违规（第二处映射 / 绕过写入，共 {len(violations)}）--")
        for fn, reason in violations:
            print(f"  [X] {fn}  # {reason}")
        if strict:
            print(f"\n[FAIL] {len(violations)} 处违反 report→note 单一真源（--strict）")
            return 1
        print("\n[WARN] 存在违规（非 strict 不阻断）")
        return 0

    print("\n[OK] report→note 映射唯一真源为 ReportNoteLinkage，无第二处硬编码/绕过写入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
