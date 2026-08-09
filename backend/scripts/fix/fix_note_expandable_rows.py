"""把附注模板里源模板留的**可扩位行**标成 `row_type: "expandable"`（幂等）。

**为什么要标而不是删**：源模板在这些位置留了「可继续加行」的意图
（`……` / `可无限量添加行`）。删掉会丢失位置信息，前端将来做不出「增行入口」；
留着不标又会被当普通空数据行渲染成一行占位披露行（memory 已记）。
故 additive 新增第 6 个 `row_type` 取值 —— 数据侧标记这一层由本脚本落地，
UI 接线归各 per-cycle spec（Requirement 11.5）。

**判据真源** = `backend/app/services/note_expandable_markers.py`（词表 + 匹配函数，
纯函数无 IO）。源侧命中证据落在 `backend/data/note_expandable_markers.json`
（由 `backend/scripts/diagnose/build_note_expandable_markers.py` 从
`backend/wp_templates/**` 的披露 sheet 全量扫出，含逐词 `source_ref`）。

🔴 判据必须在 service 层、不能留在本脚本里 —— `row_type` 有**多个写者**：本脚本、
共享行构造器 `_note_structure_kit.data_row()`、以及若干 per-cycle 幂等脚本
（`fix_note_h_policy_chapter_structure.py` 用 `tables[0] != want` **深比较整表**后
整表重写 rows）。判据分散 ⇒ 写者互相翻转：实测 soe `四、生物资产` 的 4 行 `……`
被翻回 `data`（2026-08-08）。

🔴 **行标签判据是「恰等于」不是「包含」**，且词表排除 `可改名` ——
`项目1（可改名）` 是**示例行名可改**而非可扩位，标成零可见内容会藏掉一条合法数据行。
见 `app.services.note_expandable_markers.match_label_marker` 的 docstring。

spec: note-template-columns-and-legacy-snapshot-closure Requirement 11 / Property 33~34
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
BACKEND_ROOT = _HERE.parents[2]
DATA_DIR = BACKEND_ROOT / "data"
MARKERS_JSON = DATA_DIR / "note_expandable_markers.json"
ALIGNED_BY = "note-template-columns-and-legacy-snapshot-closure"
VARIANTS = ("listed", "soe")

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# 🔴 判据从 service 层取（单一真源），本脚本不得再声明一份词表或匹配函数。
from app.services.note_expandable_markers import (  # noqa: E402
    EXPANDABLE_ROW_TYPE,
    match_label_marker,
)

#: 只允许把**当前是 `data`** 的行改标 —— 合计/小计/表头假行/无主行各有既定语义，
#: 误改会打断合计回填、段边界与行级合并（fail-closed）。
CONVERTIBLE_FROM = ("data", "")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


KIT = _load(_HERE.parent / "_note_structure_kit.py", "_expand_kit")
PROBE = _load(
    BACKEND_ROOT / "scripts" / "diagnose" / "diagnose_note_columns_coverage.py",
    "_expand_probe",
)


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------

def plan_row(row: Any) -> tuple[str, str | None]:
    """单行判定：返回 (verdict, marker)。

    * ``mark``    当前是 `data`（或缺省）且 label 恰为可扩位标记 → 应改标
    * ``noop``    已是 `expandable`（幂等）
    * ``skip``    label 是可扩位但 `row_type` 是别的既定语义 → 不动并上报
    * ``none``    不是可扩位行
    """
    if not isinstance(row, dict):
        return "none", None
    marker = match_label_marker(row.get("label"))
    if marker is None:
        return "none", None
    rt = str(row.get("row_type") or "")
    if rt == EXPANDABLE_ROW_TYPE:
        return "noop", marker
    if rt in CONVERTIBLE_FROM:
        return "mark", marker
    return "skip", marker


def _serialize(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_variant(variant: str, *, apply: bool) -> dict[str, Any]:
    path = DATA_DIR / f"note_template_{variant}.json"
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    if _serialize(doc) != raw:
        return {
            "variant": variant,
            "fatal": "round-trip 自检失败：json.dumps(indent=2) 不能逐字复现原文，拒绝写盘",
        }

    parents = PROBE._load_parent_sections()
    registry = PROBE._load_registry_sections()

    marks: list[str] = []
    skips: list[str] = []
    by_scope: Counter = Counter()
    by_marker: Counter = Counter()
    noop = 0
    touched: list[dict[str, Any]] = []

    for section in doc.get("sections") or []:
        if not isinstance(section, dict):
            continue
        num = str(section.get("section_number") or "")
        scope = PROBE.classify_section(
            section_number=num, variant=variant,
            parent_sections=parents, registry_sections=registry,
        )
        for ti, table in enumerate(section.get("tables") or []):
            if not isinstance(table, dict):
                continue
            rows = table.get("rows") if isinstance(table.get("rows"), list) else []
            name = str(table.get("name") or "")
            for ri, row in enumerate(rows):
                verdict, marker = plan_row(row)
                if verdict == "none":
                    continue
                if verdict == "noop":
                    noop += 1
                    continue
                # R10.2：母公司章一律排除（归 A spec）
                if scope == PROBE.SCOPE_PARENT:
                    skips.append(
                        "[%s] %s #%d r%d 排除（母公司章 → A spec）：%r"
                        % (variant, num, ti, ri, row.get("label"))
                    )
                    continue
                if verdict == "skip":
                    skips.append(
                        "[%s] %s #%d %s r%d 跳过：label %r 是可扩位但 row_type=%r"
                        "（既定语义，fail-closed 不动）"
                        % (variant, num, ti, name[:20], ri,
                           row.get("label"), row.get("row_type"))
                    )
                    continue
                by_scope[scope] += 1
                by_marker[marker] += 1
                marks.append(
                    "[%s] %s #%d %r r%d %r -> expandable [%s]"
                    % (variant, num, ti, name[:26], ri, row.get("label"), scope)
                )
                if apply:
                    row["row_type"] = EXPANDABLE_ROW_TYPE
                    touched.append(section)

    if apply and marks:
        seen: set[int] = set()
        for sec in touched:
            if id(sec) in seen:
                continue
            seen.add(id(sec))
            KIT.stamp(sec, ALIGNED_BY)
        path.write_text(_serialize(doc), encoding="utf-8")

    return {
        "variant": variant,
        "marks": marks,
        "skips": skips,
        "noop": noop,
        "by_scope": dict(by_scope),
        "by_marker": dict(by_marker),
        "written": bool(apply and marks),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="附注模板可扩位行标记（幂等）")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true", help="CI 模式：有欠账则 exit 1")
    ap.add_argument("--variant", choices=[*VARIANTS, "both"], default="both")
    args = ap.parse_args(argv)

    if not MARKERS_JSON.exists():
        print(
            "[ERR] 缺少真源 %s；先跑 "
            "backend/scripts/diagnose/build_note_expandable_markers.py" % MARKERS_JSON
        )
        return 2
    facts = json.loads(MARKERS_JSON.read_text(encoding="utf-8"))
    zero = [m for m, n in (facts.get("source_hits") or {}).items() if not n]
    if zero:
        print("[ERR] 词表在源披露 sheet 零命中（词表失效或源模板变更）：%s" % zero)
        return 2

    variants = VARIANTS if args.variant == "both" else (args.variant,)
    total = 0
    fatal = False
    for variant in variants:
        res = run_variant(variant, apply=args.apply)
        if res.get("fatal"):
            print("[ERR] %s" % res["fatal"])
            fatal = True
            continue
        total += len(res["marks"])
        for line in res["marks"][:20]:
            print("  " + line)
        if len(res["marks"]) > 20:
            print("  ... 另 %d 条" % (len(res["marks"]) - 20))
        for line in res["skips"][:20]:
            print("  " + line)
        print(
            "[OK] %s: mark=%d noop=%d skip=%d by_scope=%s by_marker=%s written=%s"
            % (variant, len(res["marks"]), res["noop"], len(res["skips"]),
               res["by_scope"], res["by_marker"], res["written"])
        )

    if fatal:
        return 2
    if args.check:
        print("[%s] check: 欠账 %d 项" % ("OK" if total == 0 else "ERR", total))
        return 0 if total == 0 else 1
    if not args.apply:
        print("[OK] dry-run: 待标 %d 行；加 --apply 写盘" % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
