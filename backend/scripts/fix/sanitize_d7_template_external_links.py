# -*- coding: utf-8 -*-
"""净化 D7 合同负债权威模板的孤儿外链（过 OOXML external_relationships 门）。

G5-1 Phase 5 · 对齐 DEC-11（B60 净化范式）：`backend/wp_templates/` 运行时只读，模板真要
升级必须显式净化 + 留 .bak 作门负例 + 重算 sentinel 重发布。

净化对象（全部 Task1 逐格核实为**断链孤儿**，不影响受管 sheet 明细表D7-2）：
  ① 删 22 个 xl/externalLinks/externalLink*.xml + 22 个 _rels/externalLink*.xml.rels
  ② [Content_Types].xml 删 22 个 <Override .../externalLink*.xml>
  ③ xl/_rels/workbook.xml.rels 删 22 个 externalLink <Relationship>
  ④ xl/workbook.xml 删 <externalReferences> 块 + 删 82 个含 [n] 的 defined name（删外链后
     dangle）；#REF! 的 388 个与 Nvs 垃圾**不动**（不触门、最小爆破面）；Print_Area/
     Print_Titles 等合法打印布局名保留
  ⑤ sheet3.xml(5 格) + sheet5.xml(1 格) 去 <f>[n]...</f> 保 <v> 缓存值（可见内容不变）

用法（仓库根，PowerShell）：
  校验预演（写 temp、不碰权威模板）: & .venv/Scripts/python.exe backend/scripts/fix/sanitize_d7_template_external_links.py --check
  真净化（写权威模板 + .bak）:        & .venv/Scripts/python.exe backend/scripts/fix/sanitize_d7_template_external_links.py --apply

🔴 判成败一律用 openpyxl 打开 + D7-2 逐格 diff + 门判据，不看退出码。
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
import zipfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
TEMPLATE = _REPO / "backend" / "wp_templates" / "D" / "D7 合同负债.xlsx"

_EXT_LINK_PART_RE = re.compile(r"^xl/externalLinks/externalLink\d+\.xml$")
_EXT_LINK_RELS_RE = re.compile(r"^xl/externalLinks/_rels/externalLink\d+\.xml\.rels$")
_MANAGED_SHEET = "明细表D7-2"


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
    # 删 <externalReferences>...</externalReferences> 整块
    xml = re.sub(r"<externalReferences>.*?</externalReferences>", "", xml, flags=re.S)
    # 删含 [n] 的 defined name（删外链后 dangle）；#REF! / Nvs / Print_* 一律保留
    def _drop_bracket_dn(m: re.Match) -> str:
        return "" if re.search(r"\[\d+\]", m.group(0)) else m.group(0)

    xml = re.sub(r"<definedName [^>]*>.*?</definedName>", _drop_bracket_dn, xml, flags=re.S)
    return xml


def _neutralize_external_formulas(xml: str) -> str:
    """去掉含 [n] 的 <f>...</f>，保留同 <c> 内的 <v> 缓存值（公式格→静态值格）。"""
    return re.sub(r"<f>[^<]*\[\d+\][^<]*</f>", "", xml)


def sanitize_bytes(src: bytes) -> bytes:
    import io

    zin = zipfile.ZipFile(io.BytesIO(src))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    for info in zin.infolist():
        name = info.filename
        if _EXT_LINK_PART_RE.match(name) or _EXT_LINK_RELS_RE.match(name):
            continue  # ① 丢弃外链部件 + 其 rels
        data = zin.read(name)
        if name == "[Content_Types].xml":
            data = _strip_external_from_content_types(data.decode("utf-8")).encode("utf-8")
        elif name == "xl/_rels/workbook.xml.rels":
            data = _strip_external_from_workbook_rels(data.decode("utf-8")).encode("utf-8")
        elif name == "xl/workbook.xml":
            data = _strip_external_from_workbook(data.decode("utf-8")).encode("utf-8")
        elif name in ("xl/worksheets/sheet3.xml", "xl/worksheets/sheet5.xml"):
            data = _neutralize_external_formulas(data.decode("utf-8")).encode("utf-8")
        # 保留原压缩信息里的名字/权限，用默认压缩重写
        zout.writestr(name, data)
    zout.close()
    zin.close()
    return out.getvalue()


def _snapshot_managed(path_or_bytes) -> tuple[dict, list]:
    import openpyxl
    import io

    src = path_or_bytes if isinstance(path_or_bytes, (str, Path)) else io.BytesIO(path_or_bytes)
    wb = openpyxl.load_workbook(src, data_only=False)
    ws = wb[_MANAGED_SHEET]
    snap = {}
    for r in range(1, 24):
        for c in range(1, 28):
            v = ws.cell(r, c).value
            if v is not None:
                snap[f"{openpyxl.utils.get_column_letter(c)}{r}"] = str(v)
    merged = sorted(str(m) for m in ws.merged_cells.ranges)
    wb.close()
    return snap, merged


def _gate_ext_count(data: bytes) -> int:
    import io

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

    # 校验：门 + D7-2 逐格 + openpyxl 可开
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
    print(f"D7-2 managed cells before={len(before_snap)} after={len(after_snap)} diffs={len(diffs)}")
    for k, b, a in diffs[:30]:
        print(f"  {k}: {b!r} -> {a!r}")
    print(f"D7-2 merged same={before_merged == after_merged}")

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
        print("[check] 判据全过（门 PASS + D7-2 0 diff + merge 不变）；--apply 才写盘")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
