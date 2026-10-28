# -*- coding: utf-8 -*-
"""公式格被敲成数字、裁决保留服务器值后，写出的文件里该格要恢复公式（spec oo-writeback-template-parity-closure R4）。

用户 2026-10-25：「用户在公式格敲了数字、裁决保留服务器值后，发布出去的文件里那一格仍是数字，公式没有
还原。这是看代码得出的结论，要实测。」

实测路径与生产一致：真 D4（40 binding）world；incoming = 已发布文件上把 N13（期间合计，共享公式从属格）
换成纯数字 999；生产 `adapter.extract` + `merge_projections` 判受保护冲突；保留服务器值（merged 取 current）；
再走生产 `adapter.materialize(substrate=incoming)` 写出文件，逐格读回。
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any, Iterator, Mapping

import openpyxl
import pytest

from app.services.workpaper_sync import parse_cache as PC
from app.services.workpaper_sync.adapters import excel as AX
from app.services.workpaper_sync.conflicts import ConflictKind
from app.services.workpaper_sync.merge import FieldVerdict, merge_projections
from tests.workpaper_sync.d4_materialize_harness import D4World, _text_safe, build_world

SHEET = "主营业务收入明细表D4-2"
ROW = "GTROW-D42-0013"
TOTAL = f"revenue_detail_rows/{ROW}/period_total"
SHARED = '<f t="shared" si="0"/>'


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> D4World:
    return build_world(tmp_path_factory.mktemp("d4-tamper-restore"))


@pytest.fixture(autouse=True)
def _isolated_cache() -> Iterator[None]:
    PC.clear_all_parse_caches()
    yield
    PC.clear_all_parse_caches()


def _sheet_part(data: bytes, name: str) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        workbook = zf.read("xl/workbook.xml").decode("utf-8")
        rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    rid = re.search(r'<sheet [^>]*name="' + re.escape(name) + r'"[^>]*r:id="(rId\d+)"', workbook)
    target = re.search(r'Id="' + rid.group(1) + r'"[^>]*Target="([^"]+)"', rels).group(1).lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def _with_cells(data: bytes, part: str, cells: Mapping[str, str]) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = {name: zf.read(name) for name in zf.namelist()}
    xml = entries[part].decode("utf-8")
    for coord, inner in cells.items():
        pattern = re.compile(rf'<c r="{coord}"(?P<attrs>(?:\s[^>]*?)?)(?:/>|>.*?</c>)', re.S)
        found = pattern.search(xml)
        assert found is not None, f"模板里没有 {coord}"
        style = re.search(r'\ss="(\d+)"', found.group("attrs") or "")
        s_attr = f' s="{style.group(1)}"' if style else ""
        xml = xml[: found.start()] + f'<c r="{coord}"{s_attr}{inner}</c>' + xml[found.end():]
    entries[part] = xml.encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name, payload in entries.items():
            out.writestr(name, payload)
    return buf.getvalue()


@pytest.fixture(scope="module")
def files(world: D4World) -> dict[str, Path]:
    data = world.base.read_bytes()
    part = _sheet_part(data, SHEET)
    root = world.base.parent / "tamper"
    root.mkdir(exist_ok=True)
    base = _with_cells(data, part, {
        "A13": ' t="inlineStr"><is><t>产品甲</t></is>', "B13": "><v>100</v>", "N13": f">{SHARED}<v>100</v>",
    })
    out = {"base": root / "base.xlsx", "literal": root / "literal.xlsx", "rewritten": root / "rewritten.xlsx"}
    out["base"].write_bytes(base)
    out["literal"].write_bytes(_with_cells(base, part, {"N13": "><v>999</v>"}))
    out["rewritten"].write_bytes(_with_cells(base, part, {"N13": "><f>SUM(B13:L13)</f><v>100</v>"}))
    return out


def _adapter(world: D4World, baseline: Path) -> Any:
    a = world.adapter
    return AX.build_excel_adapter(
        definitions=a.definitions, binding=a.binding, sibling_bindings=a.sibling_bindings,
        direction="oo_to_html", baseline_representation=baseline,
    )


def _keep_server(world: D4World, files: Mapping[str, Path], incoming: str) -> Any:
    adapter = _adapter(world, files["base"])
    read = lambda name: _text_safe(adapter.extract(artifact=files[name], contract=world.contract))  # noqa: E731
    base = read("base")
    outcome = merge_projections(base=base, current=base, incoming=read(incoming), contract=world.contract)
    records = [r for r in outcome.conflicts.records if r.locator.stable_field_key == TOTAL]
    if incoming == "literal":
        # 敲成 999：受保护冲突，只能保留服务器值（merged 取 current）
        assert [r.kind for r in records] == [ConflictKind.protected]
        assert outcome.verdicts[TOTAL] is FieldVerdict.conflict_protected
    else:
        # 改写公式但值没变：合并看不见（值相同），这一格照旧保留 current —— 改写后的公式
        # 修订前会原样进文件，见下面的物化断言。
        assert records == [] and outcome.verdicts[TOTAL] is FieldVerdict.kept_current
    assert outcome.merged.get(TOTAL).value == 100
    return adapter, outcome.merged


def _written_cell(path: Path, coord: str) -> tuple[Any, Any]:
    formulas = openpyxl.load_workbook(path, data_only=False)[SHEET]
    values = openpyxl.load_workbook(path, data_only=True)[SHEET]
    return formulas[coord].value, values[coord].value


@pytest.mark.parametrize("incoming", ["literal", "rewritten"])
def test_keep_server_writes_the_template_formula_back(world: D4World, files, tmp_path: Path, incoming) -> None:
    adapter, merged = _keep_server(world, files, incoming)
    output = tmp_path / f"{incoming}-out.xlsx"
    adapter.materialize(substrate=files[incoming], projection=merged, output=output, contract=world.contract)
    formula, value = _written_cell(output, "N13")
    assert formula == "=SUM(B13:M13)", f"N13 应恢复为模板公式，实为 {formula!r}"
    if incoming == "literal":
        assert value == 100  # 整格写回时带上服务器值（缓存值）
    # 只还原这一格：同列其他行的共享公式与本行输入不受影响
    assert _written_cell(output, "N12")[0] == "=SUM(B12:M12)"
    assert _written_cell(output, "B13")[1] == 100
    # 物化反读：受管字段逐个等于合并结果（生产 ContentMutationService 紧随其后的门）
    reread = adapter.extract(artifact=output, contract=world.contract)
    assert reread.get(TOTAL).value == 100


def test_html_to_oo_direction_is_unchanged(world: D4World, files, tmp_path: Path) -> None:
    """作用域外（HTML→OO 以已发布形态为底）不读 base、不还原：substrate 没公式照旧拒写。"""
    a = world.adapter
    adapter = AX.build_excel_adapter(
        definitions=a.definitions, binding=a.binding, sibling_bindings=a.sibling_bindings,
        direction="html_to_oo",
    )
    merged = _text_safe(adapter.extract(artifact=files["base"], contract=world.contract))
    with pytest.raises(Exception, match="没有公式"):
        adapter.materialize(
            substrate=files["literal"], projection=merged, output=tmp_path / "h2o.xlsx", contract=world.contract
        )
