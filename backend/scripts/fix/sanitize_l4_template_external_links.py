# -*- coding: utf-8 -*-
"""净化 L4 应付债券权威模板（过首版发布 OOXML 门 + 让受管表可安全插行）。

spec: `l-cycle-true-adapter-registration` · Task 12

两步，各有独立触发事实（2026-10-01 实测）：

① **外部关系**（与 I/J/D 系同款，算法复用 `sanitize_i_cycle_template_external_links.sanitize_bytes`）：
   首版发布 `--check` 被 `ooxml_security_rejected` 挡下 —— `xl/worksheets/_rels/sheet9.xml.rels`
   里 `权益与负债划分检查表L4-5` 有 **1** 个外部 hyperlink（gt-china.com.cn 文章）。删 Relationship 与
   `<hyperlink r:id=…>`，单元格文字保留。

② **受管表共享公式展开**：真 OO 往返时 materialize 抛
   `excel_row_shift_shared_formula_orientation_unsupported` —— `划分为金融负债的其他金融工具明细表L4-3`
   的逐行公式写成了**共享公式组**，其中 R 列主格 `R13` 的 `ref=R13:S18` 是**横向**组（跨 R/S 两列），
   新增行继承它需要列平移，行位移模块按设计 fail-closed。
   处置：**只在受管 sheet 内**把每个 `<f t="shared">` 成员展开成显式公式（openpyxl `Translator`
   按主格→成员坐标平移），删 `t/ref/si` 属性。语义零变化 —— openpyxl 读模板时本就把共享公式
   展开成同样的逐格公式，判据就是「展开前后 openpyxl 逐格快照 0 diff」。

判成败：①净化后 OOXML 门 PASS 且 `.preclean.bak` 仍 REJECT ②受管 sheet openpyxl 逐格 0 diff +
merge 不变 ③受管 sheet 共享公式残留 0 ④各项计数逐值等于期望（多一处少一处都拒绝写盘）。

用法（仓库根）::

    & .venv/Scripts/python.exe backend/scripts/fix/sanitize_l4_template_external_links.py          # 预演
    & .venv/Scripts/python.exe backend/scripts/fix/sanitize_l4_template_external_links.py --apply  # 写盘 + .bak
"""
from __future__ import annotations

import hashlib
import html
import importlib.util
import io
import re
import shutil
import sys
import zipfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "_sanitize_i_cycle", _HERE / "sanitize_i_cycle_template_external_links.py"
)
assert _SPEC and _SPEC.loader
_I = importlib.util.module_from_spec(_SPEC)
#: 🔴 先登记再执行：被加载模块里有 @dataclass，dataclasses 会按 `cls.__module__` 回查 sys.modules。
sys.modules[_SPEC.name] = _I
_SPEC.loader.exec_module(_I)

TEMPLATE = _I._REPO / "backend" / "wp_templates" / "L" / "L4 应付债券.xlsx"
MANAGED_SHEET = "划分为金融负债的其他金融工具明细表L4-3"

EXPECTED_STEP1 = {"dropped_parts": 0, "neutralized_formulas": 0, "dropped_defined_names": 0,
                  "dropped_hyperlinks": 1, "dropped_ole_objects": 0}
#: 受管表共享公式成员（含主格）展开数 —— 现算后冻结，变了就拒绝写盘。
#: 74 = 净化前受管 sheet 里 `t="shared"` 出现次数（两个口径独立现算、逐值相等）。
EXPECTED_UNSHARED_CELLS = 74

#: 🔴 开标签必须**不是自闭合**（`<c r="X1" s="3"/>` 后面紧跟的 `.*?</c>` 会吞掉下一格 ——
#:    首版就是这样把 AG13/M18 等格的公式错配到别的格上，被 0-diff 判据当场抓住）。
_CELL_F_RE = re.compile(r'(<c\b[^>]*?\br="([A-Z]+\d+)"[^>]*?(?<!/)>)(.*?)(</c>)', re.S)
_F_RE = re.compile(r"<f\b([^>]*?)(?:/>|>(.*?)</f>)", re.S)


def _sheet_part(z: zipfile.ZipFile, sheet_name: str) -> str:
    wb = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    rid = None
    for m in re.finditer(r"<sheet\b[^>]*/>", wb):
        tag = m.group(0)
        name = re.search(r'name="([^"]+)"', tag).group(1)
        if name == sheet_name:
            rid = re.search(r'r:id="([^"]+)"', tag).group(1)
    assert rid, f"找不到 sheet {sheet_name}"
    for m in re.finditer(r"<Relationship\b[^>]*/>", rels):
        tag = m.group(0)
        if re.search(rf'Id="{rid}"', tag):
            target = re.search(r'Target="([^"]+)"', tag).group(1).lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    raise AssertionError(f"rels 里找不到 {rid}")


def _unshare(xml: str) -> tuple[str, int]:
    from openpyxl.formula.translate import Translator

    masters: dict[str, tuple[str, str]] = {}  # si -> (master coord, formula text)
    for cm in _CELL_F_RE.finditer(xml):
        fm = _F_RE.search(cm.group(3))
        if fm and 't="shared"' in fm.group(1) and fm.group(2):
            si = re.search(r'si="(\d+)"', fm.group(1)).group(1)
            masters[si] = (cm.group(2), "=" + html.unescape(fm.group(2)))

    count = 0

    def _one(cm: re.Match) -> str:
        nonlocal count
        fm = _F_RE.search(cm.group(3))
        if not fm or 't="shared"' not in fm.group(1):
            return cm.group(0)
        si = re.search(r'si="(\d+)"', fm.group(1)).group(1)
        origin, formula = masters[si]
        text = Translator(formula, origin=origin).translate_formula(cm.group(2))[1:]
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        count += 1
        body = cm.group(3)[: fm.start()] + f"<f>{text}</f>" + cm.group(3)[fm.end():]
        return cm.group(1) + body + cm.group(4)

    return _CELL_F_RE.sub(_one, xml), count


def sanitize(src: bytes) -> tuple[bytes, dict[str, int], int]:
    step1, stats = _I.sanitize_bytes(src)
    zin = zipfile.ZipFile(io.BytesIO(step1))
    part = _sheet_part(zin, MANAGED_SHEET)
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    unshared = 0
    for info in zin.infolist():
        data = zin.read(info.filename)
        if info.filename == part:
            text, unshared = _unshare(data.decode("utf-8"))
            data = text.encode("utf-8")
        zout.writestr(info, data)
    zout.close()
    zin.close()
    return out.getvalue(), stats, unshared


def _shared_left(data: bytes) -> int:
    z = zipfile.ZipFile(io.BytesIO(data))
    return z.read(_sheet_part(z, MANAGED_SHEET)).decode("utf-8").count('t="shared"')


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    bak = TEMPLATE.with_suffix(TEMPLATE.suffix + ".preclean.bak")
    src = bak.read_bytes() if bak.exists() else TEMPLATE.read_bytes()
    out, stats, unshared = sanitize(src)
    b_snap, b_merged = _I._snapshot(src, MANAGED_SHEET)
    a_snap, a_merged = _I._snapshot(out, MANAGED_SHEET)
    diffs = [k for k in sorted(set(b_snap) | set(a_snap)) if b_snap.get(k) != a_snap.get(k)]
    gb, ga = _I._gate(src), _I._gate(out)
    left = _shared_left(out)
    print(f"before sha256={hashlib.sha256(src).hexdigest()} size={len(src)} gate={gb[1]} "
          f"shared_in_managed={_shared_left(src)}")
    print(f"after  sha256={hashlib.sha256(out).hexdigest()} size={len(out)} gate={ga[1]} "
          f"shared_in_managed={left}")
    print(f"step1 stats={stats} expected={EXPECTED_STEP1}")
    print(f"step2 unshared_cells={unshared} expected={EXPECTED_UNSHARED_CELLS}")
    print(f"managed: cells {len(b_snap)}->{len(a_snap)} diffs={diffs[:8]} merged_same={b_merged == a_merged}")
    ok = ((not gb[0]) and ga[0] and not diffs and b_merged == a_merged and stats == EXPECTED_STEP1
          and unshared == EXPECTED_UNSHARED_CELLS and left == 0)
    if not ok:
        print("[FAIL] 判据不满足 —— 不写盘")
        return 1
    if apply:
        if not bak.exists():
            shutil.copy2(TEMPLATE, bak)
            print(f"[apply] 备份门负例 -> {bak.name}")
        if TEMPLATE.read_bytes() != out:
            TEMPLATE.write_bytes(out)
            print("[apply] 已净化写盘")
        else:
            print("[apply] 已是净化态（幂等）")
    print("ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
