"""诊断：源 xlsx 披露 sheet ↔ `note_template_*.json` 章节 的结构比对（只读）。

## 用途

`disclosure-sync-path-buildout` 每批开工前的**第一步**（顺序铁律：先读源模板 →
再核对/补模板 JSON → 才写映射与载荷。跳过必然自造列结构）。

产出三块：

1. **源 xlsx 披露 sheet 的小节与表头**：按 `（N）xxx` / `N、xxx` 标题切分小节，
   给出每个小节的推测表头行（含两行表头的合并情形），供人工确认表集合
2. **模板 JSON 对应章节的现状**：表名 / headers / columns 是否齐备 / `group`·`flat` 表态 / guidance
3. **比对提示**：模板缺章节、模板表数与源小节数不符、列数疑似不一致

⚠️ 表边界提取是**启发式**，本脚本定位为「辅助人工核对」，**不自动生成列定义**。
判断以人工读源 xlsx 为准。

## 用法

    python backend/scripts/diagnose/diagnose_disclosure_sheet_vs_template.py --cycle G4
    python ... --cycle G4 --out g4.txt
    python ... --cycle L2 --max-rows 120
    python ... --list-cycles

Spec: .kiro/specs/disclosure-sync-path-buildout/ Task 1.1
"""

from __future__ import annotations

import argparse
import glob
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent

# 🔴 **运行时权威 = `backend/wp_templates/`**（`wp_template_init_service` 生成底稿时从这里
#    复制，`wp_template_finder` 带 `_index.json` 索引）。`基础数据/…` 只是参考副本，
#    且**已实测落后**：G4/G5/G6 三个循环的披露 sheet 两处不一致（新版增补了
#    「项目N（可改名）」占位行、「（预留，可填或在本区内插入行）」预留区、平台编制提示，
#    G4 国企把「坏账准备」正名为「减值准备」，G6 上市去掉了阶段表名里的顿号，
#    G5 删掉了 应收保证金/应收关联方款项 两行）。
#    2026-07-30 曾因先扫参考副本导致 G4/G5/G6 按旧版重建 → 故此处**权威优先**，
#    并在两处都存在且不一致时显式告警。
TPL_BASE = _BACKEND / "wp_templates"
TPL_REFERENCE = (
    _REPO
    / "基础数据"
    / "致同通用审计程序及底稿模板（2025年修订）"
    / "1.致同审计程序及底稿模板（2025年）"
)
NOTE_TPL = {
    "listed": _BACKEND / "data" / "note_template_listed.json",
    "soe": _BACKEND / "data" / "note_template_soe.json",
}
VARIANT_MATRIX = _BACKEND / "data" / "note_template_variant_matrix.json"

# 小节标题：（1）xxx / (1) xxx / 一、xxx / 1、xxx
_SECTION_RE = re.compile(r"^\s*(?:[（(]\s*\d+\s*[）)]|[一二三四五六七八九十]+、|\d+[、.])\s*(.+)$")
# 纯说明性括注（红字提示），不是小节标题
_HINT_RE = re.compile(r"^\s*[（(](?:注|说明|提示|\d+号文|15号文)")


def _scan_xlsx(base: Path, cycle: str) -> list[Path]:
    out = []
    for p in glob.glob(str(base / "**" / "*.xlsx"), recursive=True):
        name = os.path.basename(p)
        if name.startswith("~$"):  # Excel/WPS 锁文件
            continue
        if re.search(rf"(^|[^A-Za-z0-9]){re.escape(cycle)}([^0-9]|$)", name):
            out.append(Path(p))
    return sorted(out)


def _find_xlsx(cycle: str) -> tuple[list[Path], list[str]]:
    """定位源 xlsx（**权威优先**），并在参考副本不一致时告警。

    Returns:
        (权威副本路径列表, 告警行)
    """
    primary = _scan_xlsx(TPL_BASE, cycle)
    reference = _scan_xlsx(TPL_REFERENCE, cycle)
    notes: list[str] = []
    if not primary and reference:
        notes.append(
            f"🔴 权威目录 {TPL_BASE} 无 {cycle} 模板，退回参考副本 —— 结论仅供参考，须人工确认"
        )
        return reference, notes
    ref_by_name = {p.name: p for p in reference}
    for p in primary:
        ref = ref_by_name.get(p.name)
        if ref is None:
            notes.append(f"[{p.name}] 参考副本缺失（只有权威副本）")
        elif ref.stat().st_size != p.stat().st_size:
            notes.append(
                f"🔴 [{p.name}] 两处副本不一致（权威 {p.stat().st_size}B / 参考 "
                f"{ref.stat().st_size}B）→ 以 backend/wp_templates 为准，"
                f"参考副本可能落后"
            )
    return primary, notes


def _disclosure_sheets(wb: Any) -> list[str]:
    return [s for s in wb.sheetnames if "附注披露" in s or "披露" in s]


def _cell(ws: Any, r: int, c: int) -> str:
    v = ws.cell(row=r, column=c).value
    return "" if v is None else str(v).strip()


def _row_values(ws: Any, r: int, ncols: int) -> list[str]:
    return [_cell(ws, r, c) for c in range(1, ncols + 1)]


def _describe_sheet(ws: Any, max_rows: int, max_cols: int) -> list[str]:
    """按小节切分并推测表头行。"""
    lines: list[str] = []
    nrows = min(ws.max_row or 1, max_rows)
    ncols = min(ws.max_column or 1, max_cols)

    sections: list[tuple[int, str]] = []
    for r in range(1, nrows + 1):
        first = _cell(ws, r, 1)
        if not first or _HINT_RE.match(first):
            continue
        m = _SECTION_RE.match(first)
        # 小节标题特征：首格有编号 + 该行其余列基本为空
        if m and sum(1 for c in range(2, ncols + 1) if _cell(ws, r, c)) <= 1:
            sections.append((r, first))

    lines.append(f"  推测小节数 = {len(sections)}")
    for idx, (r, title) in enumerate(sections):
        end = sections[idx + 1][0] if idx + 1 < len(sections) else nrows + 1
        lines.append(f"\n  ── [{idx + 1}] 行{r}: {title[:70]}")
        # 小节内找表头：第一行「≥3 个非空列」的行；再看下一行是否也多列（两行表头）
        hdr_rows: list[int] = []
        for rr in range(r + 1, min(end, r + 8)):
            filled = [c for c in range(1, ncols + 1) if _cell(ws, rr, c)]
            if len(filled) >= 3:
                hdr_rows.append(rr)
                nxt = rr + 1
                if nxt < end:
                    nf = [c for c in range(1, ncols + 1) if _cell(ws, nxt, c)]
                    # 下一行也多列且首格为空 → 典型两级表头的子列行
                    if len(nf) >= 2 and not _cell(ws, nxt, 1):
                        hdr_rows.append(nxt)
                break
        if not hdr_rows:
            lines.append("       表头: 未识别（可能是纯文本小节）")
            continue
        for hr in hdr_rows:
            vals = [v for v in _row_values(ws, hr, ncols)]
            # 去掉尾部空列
            while vals and not vals[-1]:
                vals.pop()
            lines.append(f"       表头行{hr}({len(vals)}列): {vals}")
        data_rows = max(0, end - (hdr_rows[-1] + 1))
        lines.append(f"       数据行约 {data_rows} 行（含合计/说明）")
    return lines


def _matrix_candidates(account_hint: str) -> list[tuple[str, dict[str, str]]]:
    """按科目名在 variant_matrix 里找候选。

    🔴 `note_template_variant_matrix.json` 的真实结构是
    `accounts[] = {account_key, section_title, variants: {listed_standalone, soe_standalone, …}}`
    —— 按**科目名**索引，**不含 wp_code**。故只能用源 xlsx 文件名里的科目名做模糊匹配，
    命中多个或零个时交人工确认（不猜）。
    """
    try:
        doc = json.loads(VARIANT_MATRIX.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    hint = re.sub(r"[（()）\s]", "", account_hint)
    out: list[tuple[str, dict[str, str]]] = []
    for row in doc.get("accounts") or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("section_title") or "")
        norm = re.sub(r"[（()）\s]", "", title)
        if not norm:
            continue
        if norm == hint or norm in hint or hint in norm:
            out.append((title, dict(row.get("variants") or {})))
    return out


def _template_section(
    variant: str, section_no: str | None,
) -> dict[str, Any] | None:
    if not section_no:
        return None
    try:
        doc = json.loads(NOTE_TPL[variant].read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"模板不可读: {exc}"}
    for s in doc.get("sections") or []:
        if str(s.get("section_number") or "") == section_no:
            return s
    return None


def _describe_template(variant: str, section_no: str | None, label: str) -> list[str]:
    sec = _template_section(variant, section_no)
    lines = [f"  variant={variant}  章节号={section_no or '（未确定）'}  科目={label}"]
    if sec is None:
        lines.append("  🔴 模板中未找到该章节 → 必须先补模板章节（R2.5）")
        return lines
    if sec.get("_error"):
        lines.append(f"  {sec['_error']}")
        return lines
    tables = sec.get("tables") or []
    lines.append(f"  section_title={sec.get('section_title')!r}  tables={len(tables)}")
    for i, t in enumerate(tables, 1):
        cols = t.get("columns") or []
        has_group = any(isinstance(c, dict) and c.get("group") for c in cols)
        has_flat = any(isinstance(c, dict) and c.get("flat") for c in cols)
        state = (
            "group" if has_group and not has_flat
            else "flat" if has_flat and not has_group
            else "🔴 未表态" if not cols or not (has_group or has_flat)
            else "🔴 group+flat 冲突"
        )
        hdrs = t.get("headers") or []
        br = [h for h in hdrs if "<" in str(h)]
        lines.append(
            f"    {i:>2}. {t.get('name')}\n"
            f"        headers({len(hdrs)})={hdrs}\n"
            f"        columns={len(cols)} 表态={state} "
            f"guidance={'有' if str(t.get('guidance') or '').strip() else '🔴 无'}"
            + (f" 🔴 headers含HTML={br}" if br else "")
        )
    return lines


def run(args: argparse.Namespace) -> int:
    try:
        import openpyxl
    except ImportError:
        print("需要 openpyxl")
        return 1

    cycle = args.cycle.upper()
    out: list[str] = [f"{'=' * 70}", f"循环 {cycle}", f"{'=' * 70}", ""]

    xlsxs, src_notes = _find_xlsx(cycle)
    out.append(f"源 xlsx 命中 {len(xlsxs)} 个（权威目录 backend/wp_templates 优先）")
    for p in xlsxs:
        out.append(f"  {p.relative_to(_BACKEND.parent) if _BACKEND.parent in p.parents else p}")
    out += [f"  {n}" for n in src_notes]
    if not xlsxs:
        out.append("🔴 未找到源 xlsx → 无法核对列结构，需人工指定路径")

    for p in xlsxs:
        try:
            wb = openpyxl.load_workbook(p, data_only=True, read_only=False)
        except Exception as exc:  # noqa: BLE001
            out.append(f"\n[{p.name}] 打开失败: {exc}")
            continue
        sheets = _disclosure_sheets(wb)
        out.append(f"\n【{p.name}】披露 sheet: {sheets or '无'}")
        for sn in sheets:
            ws = wb[sn]
            out.append(f"\n  ▼ sheet「{sn}」dims={ws.dimensions}")
            out += _describe_sheet(ws, args.max_rows, args.max_cols)
        wb.close()

    out.append(f"\n{'=' * 70}\n模板 JSON 现状\n{'=' * 70}")
    # 科目名来自源 xlsx 文件名（`G4 债权投资.xlsx` → 债权投资）；也可 --account 覆盖
    account_hint = args.account or (
        re.sub(r"^[A-Z]\d+\s*", "", xlsxs[0].stem) if xlsxs else ""
    )
    cands = _matrix_candidates(account_hint)
    out.append(f"\n  variant_matrix 候选（按科目名「{account_hint}」匹配）: {len(cands)}")
    for title, variants in cands:
        out.append(
            f"    {title}: listed={variants.get('listed_standalone')} "
            f"soe={variants.get('soe_standalone')}"
        )
    if len(cands) != 1:
        out.append(
            "  ⚠️ 候选不唯一或为空 → 章节号需人工确认后用 --section-listed / --section-soe 重跑"
            if cands
            else "  🔴 variant_matrix 无匹配科目 → 章节号需人工从 variant_matrix 确认"
        )

    picked = cands[0][1] if len(cands) == 1 else {}
    for variant, key in (("listed", "listed_standalone"), ("soe", "soe_standalone")):
        override = getattr(args, f"section_{variant}", None)
        section_no = override or picked.get(key)
        out.append("")
        out += _describe_template(variant, section_no, account_hint)

    text = "\n".join(out)
    if args.out:
        with io.open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"written -> {args.out}")
    else:
        print(text)
    return 0


def _list_cycles() -> int:
    codes = set()
    for p in glob.glob(str(TPL_BASE / "**" / "*.xlsx"), recursive=True):
        name = os.path.basename(p)
        if name.startswith("~$"):
            continue
        m = re.match(r"([A-Z]\d+)\b", name)
        if m:
            codes.add(m.group(1))
    print(" ".join(sorted(codes, key=lambda c: (c[0], int(c[1:])))))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="源 xlsx 披露 sheet ↔ 附注模板 章节比对（只读）")
    ap.add_argument("--cycle", help="循环号，如 G4 / L2 / M1")
    ap.add_argument("--out", help="输出文件（UTF-8）")
    ap.add_argument("--max-rows", type=int, default=140)
    ap.add_argument("--max-cols", type=int, default=16)
    ap.add_argument("--account", help="科目名（默认取源 xlsx 文件名，用于 variant_matrix 匹配）")
    ap.add_argument("--section-listed", help="显式指定上市章节号，如 五、9")
    ap.add_argument("--section-soe", help="显式指定国企章节号，如 八、10")
    ap.add_argument("--list-cycles", action="store_true", help="列出所有可用循环号")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass
    if args.list_cycles:
        return _list_cycles()
    if not args.cycle:
        ap.error("需要 --cycle 或 --list-cycles")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
