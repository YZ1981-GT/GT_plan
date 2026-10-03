# -*- coding: utf-8 -*-
"""H 循环权威模板安全净化的防回归判据。

不放宽 `embedded_objects` / `external_relationships` 安全门：
* H2/H3/H4/H5/H7 删除 Equation.3 可执行 OLE 包，保留 VML+WMF/EMF 静态预览；
* H8 把 115 个断开的 enhanced-workbook 公式改成本册同 sheet 引用，再删外链包。
"""
from __future__ import annotations

import importlib.util
import io
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import openpyxl
import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_H_ROOT = _BACKEND / "wp_templates" / "H"
_SCRIPT = _BACKEND / "scripts" / "fix" / "sanitize_h_cycle_unsafe_ooxml.py"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_spec = importlib.util.spec_from_file_location("_h_sanitize_test", _SCRIPT)
assert _spec is not None and _spec.loader is not None
S = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = S
_spec.loader.exec_module(S)

_EXPECTED_PREVIEWS = {
    "H2 在建工程.xlsx": 2,
    "H3 投资性房地产.xlsx": 2,
    "H4 工程物资.xlsx": 2,
    "H5 油气资产.xlsx": 2,
    "H7 生产性生物资产.xlsx": 3,
}


def _relationships(data: bytes) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if not name.endswith(".rels"):
                continue
            root = ET.fromstring(zf.read(name))
            out.extend(dict(rel.attrib) for rel in root)
    return out


def test_all_six_authority_templates_are_idempotently_clean() -> None:
    report = S.run(apply=False)
    assert len(report["templates"]) == 6
    assert {r["file"] for r in report["templates"]} == {
        *_EXPECTED_PREVIEWS,
        "H8 使用权资产.xlsx",
    }
    for row in report["templates"]:
        assert row["state"] == "already_clean", row
        assert row["changed"] is False, row
        assert row["before_sha256"] == row["after_sha256"]


@pytest.mark.parametrize("file_name,preview_count", _EXPECTED_PREVIEWS.items())
def test_equation_ole_is_gone_but_static_preview_remains(
    file_name: str, preview_count: int
) -> None:
    data = (_H_ROOT / file_name).read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert not any(n.startswith("xl/embeddings/") for n in names)
        worksheet_xml = "\n".join(
            zf.read(n).decode("utf-8", errors="replace")
            for n in names
            if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
        )
        assert "<oleObjects>" not in worksheet_xml
        vml = "\n".join(
            zf.read(n).decode("utf-8", errors="replace")
            for n in names
            if n.startswith("xl/drawings/") and n.endswith(".vml")
        )
        assert len(re.findall(r'<x:ClientData\s+ObjectType="Pict">', vml)) >= preview_count
        media = [n for n in names if n.startswith("xl/media/")]
        assert len(media) >= preview_count
    rels = _relationships(data)
    assert not any(r.get("Type", "").endswith("/oleObject") for r in rels)
    assert sum(r.get("Type", "").endswith("/image") for r in rels) >= preview_count


def test_h8_external_links_are_internalized_not_staticized() -> None:
    path = _H_ROOT / "H8 使用权资产.xlsx"
    data = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert not any(n.startswith("xl/externalLinks/") for n in zf.namelist())
    assert not any(
        r.get("Type", "").endswith("/externalLink")
        or r.get("TargetMode") == "External"
        for r in _relationships(data)
    )

    wb = openpyxl.load_workbook(path, data_only=False, read_only=False, keep_links=True)
    try:
        plain = wb["折旧测算表（不含减值）H8-8"]
        impaired = wb["折旧测算表（含减值）H8-8"]
        # 三种原公式形态都钉住：不带引号单格 / 带引号单格 / 直接区域引用。
        assert plain["A3"].value == "=底稿目录!A2"
        assert plain["A9"].value == "='明细表H8-2'!A12"
        assert plain["A15"].value == "='明细表H8-2'!A33:C33"
        assert impaired["A19"].value == "='明细表H8-2'!A33:C33"
        external = [
            (ws.title, cell.coordinate, cell.value)
            for ws in wb.worksheets
            for row in ws.iter_rows()
            for cell in row
            if isinstance(cell.value, str)
            and cell.value.startswith("=")
            and re.search(r"\[\d+\]", cell.value)
        ]
        assert external == []
    finally:
        wb.close()


def test_sanitizer_fails_closed_on_an_unreviewed_embedding_shape() -> None:
    """反向判据：出现第 3 个未复核 OLE 包时，不得顺手删除并报绿。"""
    original = (_H_ROOT / "H2 在建工程.xlsx").read_bytes()
    src = io.BytesIO(original)
    out = io.BytesIO()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info, zin.read(info.filename))
        zout.writestr("xl/embeddings/unknown.bin", b"not-reviewed")
    with pytest.raises(S.HTemplateSanitizationError, match="embedding 实测 1"):
        S.sanitize_ole_equations(out.getvalue(), S._OLE_TEMPLATES[0])


def test_sanitizer_fails_closed_on_a_new_external_formula_shape() -> None:
    """反向判据：净化后若重新出现 1 条外链，不能按旧 115 条口径自动吞掉。"""
    original = (_H_ROOT / "H8 使用权资产.xlsx").read_bytes()
    src = io.BytesIO(original)
    out = io.BytesIO()
    injected = False
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if not injected and info.filename.startswith("xl/worksheets/sheet") and info.filename.endswith(".xml"):
                text = data.decode("utf-8")
                if "</worksheet>" in text:
                    # 不要求构造合法 cell；采集器只看 <f>，目的是证实**计数门**会拒绝新形态。
                    text = text.replace("</worksheet>", "<f>[9]不存在!A1</f></worksheet>")
                    data = text.encode("utf-8")
                    injected = True
            zout.writestr(info, data)
    assert injected
    with pytest.raises(S.HTemplateSanitizationError, match="外链公式实测 1"):
        S.sanitize_h8_external_links(out.getvalue())
