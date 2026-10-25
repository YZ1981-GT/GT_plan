# -*- coding: utf-8 -*-
r"""修 D3 预收账款权威模板的两处 footer 缺陷（过 row-table-engine 的 footer 两道门）。

spec: d3-sync-coverage-via-row-table-engine · Task 10 第 3c 段（用户批准"修模板"）

背景（证据 evidence/task10-d3-05-footer-anchor-investigation.md §2.2 / §3 / §7）：
row-table-engine 把 D3-5 / D3-6 纳入 materialize 时被两道 footer 门恒拦：

  ① D3-6 `关联关系及交易检查表D3-6`（sheet10.xml）合计行 17：
     C17=SUM(C12:C14) / D17=SUM(D12:D14)（D17:F17 shared si=1）只覆盖数据区
     12-16 的**前 3 行**（12-14），漏 15-16 ⇒ `assert_footer_formula_covers_managed_rows`
     覆盖门每次 materialize 都拦（`FooterFormulaRangeError`，与插不插行无关）。
     修法：4 个 SUM 区间 12:14 → 12:16（覆盖全部 5 个数据行）。
       - C17 是**独立公式**：直接改 `<f>SUM(C12:C14)</f>` → `<f>SUM(C12:C16)</f>`。
       - D17:F17 是**共享公式组**（master 在 D17 带 `ref="D17:F17" si="1"`，
         E17/F17 是 `<f t="shared" si="1"/>` slave，靠列偏移派生）⇒ 只改 D17 master
         的 `SUM(D12:D14)` → `SUM(D12:D16)`，E17/F17 自动派生为 E/F 的 12:16。

  ② D3-5 `账龄1年以上的预收账款检查表D3-5`（sheet9.xml）合计行 14：
     B14=SUM(B11:B13) / F14=SUM(F11:F13)，但 A14 空、整个 A 列无「合计」文字。
     引擎靠 A 列文字定位 footer（`_find_marker_row`）⇒ `FooterAnchorDriftError`。
     修法（证据 §7 修法 B，已离线实测跑通且合计不漏算）：A14 写入「合计」。
     A14 现为空自闭合 `<c r="A14" s="12"/>`（style 12）。为不动 sharedStrings.xml
     索引，用 **inlineStr** 写：`<c r="A14" s="12" t="inlineStr"><is><t>合计</t></is></c>`
     （保留 style s="12"）。SUM 区间 11:13 覆盖数据区 11-13 全部 3 行，无需改。

只改这两个 worksheet part（sheet9 = D3-5、sheet10 = D3-6），其余 part 逐字节不动。

用法（仓库根 或 backend；脚本自定位模板）：
  校验预演: ..\.venv\Scripts\python.exe backend/scripts/fix/fix_d3_template_footer_defects.py --check
  真修复:   ..\.venv\Scripts\python.exe backend/scripts/fix/fix_d3_template_footer_defects.py --apply

🔴 判成败一律用 openpyxl 打开 + 逐格 diff + 门判据，不看退出码：
   D3-6 仅 C17/D17/E17/F17 四格公式变（12:14→12:16）、D3-5 仅 A14 空→「合计」；
   两张 sheet merged ranges 不变；其它 10 张 sheet 一格不动。
"""
from __future__ import annotations

import hashlib
import io
import re
import shutil
import sys
import zipfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
TEMPLATE = _REPO / "backend" / "wp_templates" / "D" / "D3 预收账款.xlsx"

_D35_SHEET = "账龄1年以上的预收账款检查表D3-5"   # sheet9.xml
_D36_SHEET = "关联关系及交易检查表D3-6"          # sheet10.xml
_MANAGED_SHEETS = (_D35_SHEET, _D36_SHEET)


def _resolve_sheet_parts(src: bytes) -> dict[str, str]:
    """sheet 名 -> `xl/worksheets/sheetN.xml`（经 workbook.xml r:id + rels 映射）。"""
    z = zipfile.ZipFile(io.BytesIO(src))
    wb_xml = z.read("xl/workbook.xml").decode("utf-8")
    rels_xml = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    z.close()
    sheets = re.findall(r'<sheet[^>]*name="([^"]*)"[^>]*r:id="([^"]*)"', wb_xml)
    rid_target = dict(
        re.findall(r'<Relationship[^>]*Id="([^"]*)"[^>]*Target="([^"]*)"', rels_xml)
    )
    out: dict[str, str] = {}
    for name, rid in sheets:
        tgt = rid_target.get(rid, "")
        out[name] = "xl/" + tgt if not tgt.startswith("/") else tgt.lstrip("/")
    return out


def _patch_d36_footer(xml: str) -> str:
    """D3-6 合计行 17：C17 独立公式 + D17 共享 master，SUM 12:14 → 12:16。"""
    # C17 独立公式：<c r="C17" s="26"><f>SUM(C12:C14)</f>...
    xml, n_c = re.subn(
        r'(<c r="C17"[^>]*><f>)SUM\(C12:C14\)(</f>)',
        r"\1SUM(C12:C16)\2",
        xml,
    )
    # D17 共享 master：<f t="shared" ref="D17:F17" si="1">SUM(D12:D14)</f>
    xml, n_d = re.subn(
        r'(<f t="shared" ref="D17:F17" si="1">)SUM\(D12:D14\)(</f>)',
        r"\1SUM(D12:D16)\2",
        xml,
    )
    if n_c != 1 or n_d != 1:
        raise RuntimeError(
            f"D3-6 footer 公式改写命中数异常：C17={n_c} D17-master={n_d}（各应 1）"
            " —— 模板形态与预期不符，拒绝写盘"
        )
    return xml


def _patch_d35_footer(xml: str) -> str:
    """D3-5 合计行 14：A14 空自闭合 -> inlineStr「合计」（保留 style s=12）。"""
    xml, n = re.subn(
        r'<c r="A14" s="12"/>',
        r'<c r="A14" s="12" t="inlineStr"><is><t>合计</t></is></c>',
        xml,
    )
    if n != 1:
        raise RuntimeError(
            f"D3-5 A14 空格改写命中数异常：{n}（应 1）—— A14 形态与预期不符，拒绝写盘"
        )
    return xml


def fix_bytes(src: bytes) -> bytes:
    parts = _resolve_sheet_parts(src)
    d35_part = parts[_D35_SHEET]
    d36_part = parts[_D36_SHEET]
    zin = zipfile.ZipFile(io.BytesIO(src))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    for info in zin.infolist():
        name = info.filename
        data = zin.read(name)
        if name == d36_part:
            data = _patch_d36_footer(data.decode("utf-8")).encode("utf-8")
        elif name == d35_part:
            data = _patch_d35_footer(data.decode("utf-8")).encode("utf-8")
        zout.writestr(info, data)
    zout.close()
    zin.close()
    return out.getvalue()


def _snapshot(src: bytes) -> dict:
    """全 12 张 sheet 逐格 + 每张 merged ranges。"""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(src), data_only=False)
    snap: dict = {}
    for ws in wb.worksheets:
        cells = {}
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    cells[cell.coordinate] = str(cell.value)
        snap[ws.title] = {
            "cells": cells,
            "merged": sorted(str(m) for m in ws.merged_cells.ranges),
        }
    wb.close()
    return snap


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    src = TEMPLATE.read_bytes()
    before_sha = hashlib.sha256(src).hexdigest()
    before = _snapshot(src)

    out = fix_bytes(src)
    after_sha = hashlib.sha256(out).hexdigest()
    after = _snapshot(out)

    print(f"before sha256={before_sha}  size={len(src)}")
    print(f"after  sha256={after_sha}  size={len(out)}")

    # 逐 sheet 逐格 diff
    changed_sheets: dict[str, list] = {}
    merged_changed: list[str] = []
    for title in before:
        b, a = before[title], after[title]
        diffs = [
            (k, b["cells"].get(k), a["cells"].get(k))
            for k in sorted(set(b["cells"]) | set(a["cells"]))
            if b["cells"].get(k) != a["cells"].get(k)
        ]
        if diffs:
            changed_sheets[title] = diffs
        if b["merged"] != a["merged"]:
            merged_changed.append(title)

    print("\n== 逐 sheet 变动 ==")
    for title, diffs in changed_sheets.items():
        print(f"  [{title}] {len(diffs)} 格:")
        for k, bv, av in diffs:
            print(f"    {k}: {bv!r} -> {av!r}")
    print(f"other sheets untouched: {len(before) - len(changed_sheets)}/12")
    print(f"merged ranges changed sheets: {merged_changed or '(none)'}")

    # 判据：只有 D3-5 / D3-6 两张变；D3-6 恰 C17/D17/E17/F17 四格公式 12:14->12:16；
    #       D3-5 恰 A14 空->「合计」；两张 merged 不变；其它 10 张零 diff。
    ok = True
    if set(changed_sheets) != set(_MANAGED_SHEETS):
        print(f"[FAIL] 变动 sheet 集合 != 期望：{set(changed_sheets)}")
        ok = False
    if merged_changed:
        print(f"[FAIL] merged ranges 变了：{merged_changed}")
        ok = False
    # D3-6 判据
    d36 = dict((k, (bv, av)) for k, bv, av in changed_sheets.get(_D36_SHEET, []))
    exp_d36 = {
        "C17": ("=SUM(C12:C14)", "=SUM(C12:C16)"),
        "D17": ("=SUM(D12:D14)", "=SUM(D12:D16)"),
        "E17": ("=SUM(E12:E14)", "=SUM(E12:E16)"),
        "F17": ("=SUM(F12:F14)", "=SUM(F12:F16)"),
    }
    if d36 != exp_d36:
        print(f"[FAIL] D3-6 变动 != 期望四格公式：{d36}")
        ok = False
    # D3-5 判据
    d35 = dict((k, (bv, av)) for k, bv, av in changed_sheets.get(_D35_SHEET, []))
    if d35 != {"A14": (None, "合计")}:
        print(f"[FAIL] D3-5 变动 != {{A14: None->合计}}：{d35}")
        ok = False

    if not ok:
        print("\n[FAIL] 判据未过 —— 不写盘")
        return 1

    if apply:
        bak = TEMPLATE.with_suffix(TEMPLATE.suffix + ".prefooterfix.bak")
        if not bak.exists():
            shutil.copy2(TEMPLATE, bak)
            print(f"\n[apply] 备份 → {bak.name}")
        TEMPLATE.write_bytes(out)
        print(f"[apply] 已写盘 {TEMPLATE.name}  new_sha256={after_sha}  new_size={len(out)}")
    else:
        print("\n[check] 判据全过（仅 D3-5 A14 + D3-6 四格公式变，merged 不变）；--apply 才写盘")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
