"""附注模板文本卫生（幂等）：`text_sections` 裸表名标题化 + md 重建假行清理。

**为什么这是真实交付件缺陷、不是化妆品**（2026-08-08 实证）：

* 裸表名 —— `disclosure_engine._is_table_title_paragraph` 只认 `#` 开头
  或 `（N）xxx` / `N. xxx` 且 ≤20 字；一个「只有表名」的裸段落两条都不满足
  ⇒ 落进 `text_content`，附注正文与 Word 导出凭空多出一段「只有表名」的正文。
* `header_label` 假行 —— `note_word_exporter._render_table` **完全不读 `row_type`**，
  把 `rows` 全部渲染成可见行 ⇒ 假行在 Word 交付件里是可见的一行
  （label 列显示表头文字、数值列全空）。

**与 Requirement 10.1「不改行集」的边界**：只删「可由该表 `headers` 证明为表头
文字残留」的行（`_prove_header_artifact`），不增行、不改任何业务行 ⇒ 属残留清理。
证明不了的一律跳过并上报（fail-closed，Requirement 12.3）。

**与 Requirement 11「可扩位标 expandable」的边界**：label 命中可扩位判据的行
**永不删除**（Requirement 12.4），由 `fix_note_expandable_rows.py` 标 `expandable`。
两条处置的作用行集合交集必须为空（守卫 Property 36 钉死）。

spec: note-template-columns-and-legacy-snapshot-closure Requirement 12 / Property 35~37
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
BACKEND_ROOT = _HERE.parents[2]
DATA_DIR = BACKEND_ROOT / "data"
ALIGNED_BY = "note-template-columns-and-legacy-snapshot-closure"
VARIANTS = ("listed", "soe")

_HTML_RE = re.compile(r"<[^>]+>")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = mod  # dataclass 需要（memory 铁律）
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


KIT = _load(_HERE.parent / "_note_structure_kit.py", "_hygiene_kit")
PROBE = _load(
    BACKEND_ROOT / "scripts" / "diagnose" / "diagnose_note_columns_coverage.py",
    "_hygiene_probe",
)
MARKERS_MOD = _load(
    BACKEND_ROOT / "scripts" / "diagnose" / "build_note_expandable_markers.py",
    "_hygiene_markers",
)


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------

def _norm_ws(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def prove_header_artifact(label: Any, headers: list[Any]) -> str | None:
    """证明该 label 是「表头文字残留」；证明不了返回 None（Requirement 12.3）。

    两条判据（任一成立即可证）：

    * ``equals_header``   归一化（去全部空白）后与 ``headers`` 任一项相等
    * ``html_in_label``   label 含 HTML 标签 —— 数据行的 label 不可能带 ``<br/>``，
                          那是两级表头被 md 重建压扁后残留的铁证

    **有意不做「子串」判据**：`项目` 是 `项目名称` 的子串，按子串会把业务行误判成残留。
    """
    text = str(label or "")
    if not text.strip():
        return None
    if _HTML_RE.search(text):
        return "html_in_label"
    if _norm_ws(text) in {_norm_ws(h) for h in headers if str(h or "").strip()}:
        return "equals_header"
    return None


def plan_header_label_rows(table: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """返回 (保留行, 变更说明)。幂等：无假行时返回原 rows 的同值列表与空说明。"""
    t = table if isinstance(table, dict) else {}
    rows = t.get("rows") if isinstance(t.get("rows"), list) else []
    headers = t.get("headers") if isinstance(t.get("headers"), list) else []
    kept: list[dict[str, Any]] = []
    notes: list[str] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            kept.append(row)
            continue
        if str(row.get("row_type") or "") != "header_label":
            kept.append(row)
            continue
        label = row.get("label")
        # R12.4：可扩位行永不删（归 Requirement 11 标 expandable）
        if MARKERS_MOD.match_label_marker(label) is not None:
            kept.append(row)
            notes.append(
                "r%d 保留：label %r 是可扩位标记（归 expandable 处置）" % (idx, label)
            )
            continue
        proof = prove_header_artifact(label, headers)
        if proof is None:
            kept.append(row)
            notes.append(
                "r%d 保留：label %r 无法证明是表头残留（headers=%r）→ fail-closed"
                % (idx, label, [str(h) for h in headers][:4])
            )
            continue
        notes.append("r%d 删除：label %r（%s）" % (idx, label, proof))
    return kept, notes


def _serialize(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------------------
# text_sections= 冲突面（R12.5）
# ---------------------------------------------------------------------------

_SECTION_CODE_RE = re.compile(r"[一二三四五六七八九十]+、\d+")


def section_code_of(section_number: str) -> str:
    """取章节号的 `X、N` 前缀。

    模板里有 md 截断的 section_number（`九、1、或有负债` / `三、资产减值损失（损`），
    直接整串比对会漏判 ⇒ 一律按前缀比（memory 已记的截断值坑）。
    """
    m = _SECTION_CODE_RE.match(str(section_number or "").strip())
    return m.group(0) if m else str(section_number or "").strip()


def sections_with_text_sections_declared() -> set[str]:
    """扫 `fix_note_*.py`，返回 `text_sections` 已被别的脚本管着的章节号前缀集合。

    两类都要排除（对它们做标题化会被对方 `--apply` 回退或反复来回改）：

    * ``run_section(text_sections=[...])`` —— **整表替换**语义；
    * ``ensure_text_sections([...])`` / ``missing_text_sections([...])`` ——
      按 ``str(p).strip()`` 逐字比对判「缺段」，而加了 ``#### `` 前缀后
      stripped 文本不再相等 ⇒ 对方会把裸段落**再补一遍**（无限来回）。

    Requirement 12.5
    """
    out: set[str] = set()
    fix_dir = _HERE.parent
    for path in sorted(fix_dir.glob("fix_note_*.py")):
        if path.name == _HERE.name:
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        manages = bool(
            re.search(r"text_sections\s*=\s*(?!None)[\[A-Za-z_]", src)
            or re.search(r"\b(?:ensure|missing)_text_sections\s*\(", src)
        )
        if not manages:
            continue
        out.update(_SECTION_CODE_RE.findall(src))
    return out


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
    declared = sections_with_text_sections_declared()

    titleized: list[str] = []
    deleted: list[str] = []
    skips: list[str] = []
    touched: list[dict[str, Any]] = []
    seg_impacted: list[str] = []

    for section in doc.get("sections") or []:
        if not isinstance(section, dict):
            continue
        num = str(section.get("section_number") or "")
        scope = PROBE.classify_section(
            section_number=num, variant=variant,
            parent_sections=parents, registry_sections=registry,
        )
        # R10.2 / R12.5：母公司章一律排除（归 A spec）
        if scope == PROBE.SCOPE_PARENT:
            bare = KIT.find_bare_table_name_paragraphs(section)
            if bare:
                skips.append(
                    "[%s] %s 排除（母公司章 → A spec）：裸表名 %d 处"
                    % (variant, num, len(bare))
                )
            continue

        # ---- ① text_sections 裸表名标题化 -----------------------------
        bare = KIT.find_bare_table_name_paragraphs(section)
        if bare:
            if section_code_of(num) in declared:
                skips.append(
                    "[%s] %s 跳过标题化：已有 per-cycle 脚本声明 text_sections=（整表替换）"
                    % (variant, num)
                )
            else:
                before = len(section.get("text_sections") or [])
                changes = KIT.titleize_text_sections(section)
                after = len(section.get("text_sections") or [])
                if before != after:  # Property 35：只加前缀不删段
                    return {
                        "variant": variant,
                        "fatal": "标题化改变了 text_sections 段数 (%d → %d) at %s"
                                 % (before, after, num),
                    }
                for c in changes:
                    titleized.append("[%s] %s %s" % (variant, num, c))
                if changes:
                    touched.append(section)

        # ---- ② header_label 假行清理 ---------------------------------
        for ti, table in enumerate(section.get("tables") or []):
            if not isinstance(table, dict):
                continue
            rows = table.get("rows") if isinstance(table.get("rows"), list) else []
            if not any(
                isinstance(r, dict) and str(r.get("row_type") or "") == "header_label"
                for r in rows
            ):
                continue
            kept, notes = plan_header_label_rows(table)
            removed = len(rows) - len(kept)
            name = str(table.get("name") or "")
            for n in notes:
                if n.startswith(("r",)) and "保留：" in n:
                    skips.append("[%s] %s #%d %s %s" % (variant, num, ti, name[:24], n))
            if removed <= 0:
                continue
            codes = {
                str(r.get("report_row_code"))
                for r in rows
                if isinstance(r, dict) and r.get("report_row_code")
            }
            if len(codes) >= 2:
                seg_impacted.append(
                    "[%s] %s #%d %s（多段共享表，段码 %d 个）"
                    % (variant, num, ti, name[:24], len(codes))
                )
            deleted.append(
                "[%s] %s #%d %r rows %d -> %d（删 %d 个表头残留假行）"
                % (variant, num, ti, name[:28], len(rows), len(kept), removed)
            )
            if apply:
                table["rows"] = kept
                touched.append(section)

    if apply and (titleized or deleted):
        seen: set[int] = set()
        for sec in touched:
            if id(sec) in seen:
                continue
            seen.add(id(sec))
            KIT.stamp(sec, ALIGNED_BY)
        path.write_text(_serialize(doc), encoding="utf-8")

    return {
        "variant": variant,
        "titleized": titleized,
        "deleted": deleted,
        "skips": skips,
        "seg_impacted": seg_impacted,
        "written": bool(apply and (titleized or deleted)),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="附注模板文本卫生（裸表名标题化 + 假行清理）")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true", help="CI 模式：有欠账则 exit 1")
    ap.add_argument("--variant", choices=[*VARIANTS, "both"], default="both")
    args = ap.parse_args(argv)

    variants = VARIANTS if args.variant == "both" else (args.variant,)
    total = 0
    fatal = False
    seg_all: list[str] = []
    for variant in variants:
        res = run_variant(variant, apply=args.apply)
        if res.get("fatal"):
            print("[ERR] %s" % res["fatal"])
            fatal = True
            continue
        n = len(res["titleized"]) + len(res["deleted"])
        total += n
        for line in res["titleized"][:40]:
            print("  " + line)
        for line in res["deleted"][:40]:
            print("  " + line)
        for line in res["skips"][:40]:
            print("  " + line)
        seg_all.extend(res["seg_impacted"])
        print(
            "[OK] %s: titleize=%d delete_tables=%d skip=%d written=%s"
            % (variant, len(res["titleized"]), len(res["deleted"]),
               len(res["skips"]), res["written"])
        )

    if seg_all:
        print("[WARN] 触及多段共享表 %d 张 —— 落地后必须重生成派生段清单：" % len(seg_all))
        for s in seg_all:
            print("    " + s)
        print(
            "    python backend/scripts/gen/gen_note_shared_table_segments.py --write"
            "  然后跑 backend/tests/test_note_shared_table_segments.py"
        )

    if fatal:
        return 2
    if args.check:
        print("[%s] check: 欠账 %d 项" % ("OK" if total == 0 else "ERR", total))
        return 0 if total == 0 else 1
    if not args.apply:
        print("[OK] dry-run: 待处理 %d 项；加 --apply 写盘" % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
