# -*- coding: utf-8 -*-
"""净化 D6 合同资产权威模板的孤儿外链（过 OOXML external_relationships 门）。

G5-1 Phase 5 · 对齐 DEC-11（B60/D7/D3 净化范式）：`backend/wp_templates/` 运行时只读。

Task 探查（tmp_d6_template_probe）：
  - **21 个 externalLink**（TargetMode=External），**0 个 [n] 公式格**（同 D3，比 D7 干净，
    无需中和公式）。609 defined name：492 #REF! 孤儿（保留）+ 99 bracket[n]（删外链后 dangle，删）。
  - 受管 sheet = `明细表D6-2`（32 列 A-AF，两级表头 行 12 组标题 / 行 13 账龄子标题）。

净化 4 处（zip 级精准删除，同 D3；worksheet 分支 0 命中的兜底保留通用性）。

用法（仓库根，PowerShell）：
  校验预演: & .venv/Scripts/python.exe backend/scripts/fix/sanitize_d6_template_external_links.py --check
  真净化:   & .venv/Scripts/python.exe backend/scripts/fix/sanitize_d6_template_external_links.py --apply

🔴 判成败一律用 openpyxl 打开 + D6-2 逐格 diff + 门判据，不看退出码。
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
TEMPLATE = _REPO / "backend" / "wp_templates" / "D" / "D6 合同资产.xlsx"

_EXT_LINK_PART_RE = re.compile(r"^xl/externalLinks/externalLink\d+\.xml$")
_EXT_LINK_RELS_RE = re.compile(r"^xl/externalLinks/_rels/externalLink\d+\.xml\.rels$")
_WORKSHEET_RE = re.compile(r"^xl/worksheets/sheet\d+\.xml$")
_MANAGED_SHEET = "明细表D6-2"


def _strip_external_from_content_types(xml: str) -> str:
    return re.sub(
        r'<Override PartName="/xl/externalLinks/externalLink\d+\.xml"[^>]*/>',
        "",
        xml,
    )


def _strip_external_from_workbook_rels(xml: str) -> str:
    return re.sub(
        r'<Relationship [^>]*Target="externalLinks/externalLink\d+\.xml"[^>]*/>',
        "",
        xml,
    )


def _strip_external_from_workbook(xml: str) -> str:
    xml = re.sub(r"<externalReferences>.*?</externalReferences>", "", xml, flags=re.S)

    def _drop_bracket_dn(m: re.Match) -> str:
        return "" if re.search(r"\[\d+\]", m.group(0)) else m.group(0)

    xml = re.sub(r"<definedName [^>]*>.*?</definedName>", _drop_bracket_dn, xml, flags=re.S)
    return xml


def _neutralize_external_formulas(xml: str) -> str:
    """去 [n] 公式保 <v> 缓存值。D6 实测 0 命中（无副作用）。"""
    return re.sub(r"<f>[^<]*\[\d+\][^<]*</f>", "", xml)


def sanitize_bytes(src: bytes) -> bytes:
    zin = zipfile.ZipFile(io.BytesIO(src))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    for info in zin.infolist():
        name = info.filename
        if _EXT_LINK_PART_RE.match(name) or _EXT_LINK_RELS_RE.match(name):
            continue
        data = zin.read(name)
        if name == "[Content_Types].xml":
            data = _strip_external_from_content_types(data.decode("utf-8")).encode("utf-8")
        elif name == "xl/_rels/workbook.xml.rels":
            data = _strip_external_from_workbook_rels(data.decode("utf-8")).encode("utf-8")
        elif name == "xl/workbook.xml":
            data = _strip_external_from_workbook(data.decode("utf-8")).encode("utf-8")
        elif _WORKSHEET_RE.match(name):
            data = _neutralize_external_formulas(data.decode("utf-8")).encode("utf-8")
        zout.writestr(name, data)
    zout.close()
    zin.close()
    return out.getvalue()


def _snapshot_managed(path_or_bytes) -> tuple[dict, list]:
    import openpyxl

    src = path_or_bytes if isinstance(path_or_bytes, (str, Path)) else io.BytesIO(path_or_bytes)
    wb = openpyxl.load_workbook(src, data_only=False)
    ws = wb[_MANAGED_SHEET]
    snap = {}
    for r in range(1, 39):
        for c in range(1, 33):
            v = ws.cell(r, c).value
            if v is not None:
                snap[f"{openpyxl.utils.get_column_letter(c)}{r}"] = str(v)
    merged = sorted(str(m) for m in ws.merged_cells.ranges)
    wb.close()
    return snap, merged


def _gate_ext_count(data: bytes) -> int:
    z = zipfile.ZipFile(io.BytesIO(data))
    n = 0
    for name in z.namelist():
        if name.endswith(".rels"):
            if 'TargetMode="External"' in z.read(name).decode("utf-8", "replace"):
                n += 1
    z.close()
    return n


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    src = TEMPLATE.read_bytes()
    before_snap, before_merged = _snapshot_managed(TEMPLATE)
    before_sha = hashlib.sha256(src).hexdigest()

    out = sanitize_bytes(src)
    after_sha = hashlib.sha256(out).hexdigest()

    ext_before = _gate_ext_count(src)
    ext_after = _gate_ext_count(out)
    after_snap, after_merged = _snapshot_managed(out)
    diffs = [
        (k, before_snap.get(k), after_snap.get(k))
        for k in sorted(set(before_snap) | set(after_snap))
        if before_snap.get(k) != after_snap.get(k)
    ]

    print(f"before sha256={before_sha}")
    print(f"after  sha256={after_sha}")
    print(f"external .rels: before={ext_before} after={ext_after} → 门:{'PASS' if ext_after == 0 else 'REJECT'}")
    print(f"D6-2 managed cells before={len(before_snap)} after={len(after_snap)} diffs={len(diffs)}")
    for k, b, a in diffs[:30]:
        print(f"  {k}: {b!r} -> {a!r}")
    print(f"D6-2 merged same={before_merged == after_merged}")

    ok = ext_after == 0 and len(diffs) == 0 and before_merged == after_merged
    if not ok:
        print("[FAIL] 净化不满足判据（门未过 / 受管 sheet 有 diff / merge 变了）—— 不写盘")
        return 1

    if apply:
        bak = TEMPLATE.with_suffix(TEMPLATE.suffix + ".preclean.bak")
        if not bak.exists():
            shutil.copy2(TEMPLATE, bak)
            print(f"[apply] 备份门负例 → {bak.name}")
        TEMPLATE.write_bytes(out)
        print(f"[apply] 已净化写盘 {TEMPLATE.name}  new_sha256={after_sha}")
    else:
        print("[check] 判据全过（门 PASS + D6-2 0 diff + merge 不变）；--apply 才写盘")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
