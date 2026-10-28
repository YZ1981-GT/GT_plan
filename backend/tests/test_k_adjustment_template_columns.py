"""K3 ~ K7「调整分录汇总」导入导出按模板补列（spec oo-writeback-template-parity-closure R3 批 B2c）。

模板 B 类别 / C 报表项目 / E 附注项目 / I 索引（K5 另有 J 备注）前端原来没有，OO 侧填了回 HTML 下一次保存
就被擦掉；前端补列后，导入导出也得带上这几列，否则「导出 → 改 → 导入」整表替换时又把它们清空。

钉住：
  1. 导入导出列 ⊇ OO 写回契约的受管键（F「……」占位列除外）—— OO 侧能填的列，导出能带出、导入能带回；
  2. 后加的列登记为 optional_headers：旧版导出文件没有这几列照常导入，缺的列**不写键**
     （写成空串会盖掉前端按缺键给的缺省，如「类别」按分录类型）；
  3. 其余列仍须齐：缺一列原有列照旧拒收（optional_headers 不是「缺列放行」）。
"""
from __future__ import annotations

import importlib
import io
import json
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from fastapi import UploadFile

from app.routers.wp_render_strategies._cycle_import_export_common import parse_upload_xlsx

_CONTRACTS = Path(__file__).resolve().parents[1] / "data" / "workpaper_sync_contracts"

# sheet → (导入导出模块, _SPECS 名, OO 写回契约文件, 补的列)
_CASES: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "K3-3": ("_k3_import_export", "_K3_SPECS", "k3.other_payables_adjustment.json", ("类别", "报表项目", "附注项目", "索引")),
    "K4-3": ("_k4_import_export", "_K4_SPECS", "k4.other_current_liabilities_adjustment.json", ("类别", "报表项目", "附注项目", "索引")),
    "K5-3": ("_k5_import_export", "_K5_SPECS", "k5.provisions_adjustment.json", ("类别", "报表项目", "附注项目", "备注")),
    "K6-3": ("_k6_import_export", "_K6_SPECS", "k6.held_for_sale_adjustment.json", ("类别", "报表项目", "附注项目", "索引")),
    "K7-3": ("_k7_import_export", "_K7_SPECS", "k7.deferred_income_adjustment.json", ("类别",)),
}
_WP_ID = "33333333-3333-3333-3333-333333333333"


def _spec(sheet: str) -> tuple[dict, Any]:
    mod_name, attr, _c, _a = _CASES[sheet]
    mod = importlib.import_module(f"app.routers.wp_render_strategies.{mod_name}")
    return getattr(mod, attr)[sheet], mod


def _contract_keys(sheet: str, item_id: str) -> list[str]:
    doc = json.loads((_CONTRACTS / _CASES[sheet][2]).read_text(encoding="utf-8"))
    return [
        f["json_pointer"].rsplit("/", 1)[-1]
        for s in doc["sheets"] for t in s.get("tables", []) for f in t["fields"]
        if f["store_item_id"] == item_id and f["header_text"] != "……"
    ]


@pytest.mark.parametrize("sheet", sorted(_CASES))
def test_ie_columns_cover_oo_contract_keys(sheet):
    spec, _ = _spec(sheet)
    keys = _contract_keys(sheet, spec["item_id"])
    assert len(keys) == 9, keys
    assert [k for k in keys if k not in spec["field_keys"]] == []


@pytest.mark.parametrize("sheet", sorted(_CASES))
def test_added_columns_are_optional_headers(sheet):
    spec, _ = _spec(sheet)
    added = _CASES[sheet][3]
    assert tuple(spec["optional_headers"]) == added
    assert set(added) <= set(spec["headers"])
    assert len(spec["headers"]) == len(spec["field_keys"])


class _Result:
    def __init__(self, value: Any = None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def fetchone(self):
        return None

    def all(self):
        return []


class _CaptureDB:
    def __init__(self):
        self.writes: list[dict] = []

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if "SELECT project_id FROM working_paper" in sql:
            return _Result("44444444-4444-4444-4444-444444444444")
        if not sql.strip().upper().startswith("SELECT"):
            self.writes.append(dict(params or {}))
        return _Result()

    async def commit(self):
        return None

    async def flush(self):
        return None

    async def rollback(self):
        return None


def _workbook(sheet: str, headers: list[str], values: list[Any]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append([f"{sheet} 调整分录汇总"])
    ws.append(headers)
    ws.append(values)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def _import(sheet: str, content: bytes) -> tuple[dict, _CaptureDB]:
    _, mod = _spec(sheet)
    endpoint = next(r.endpoint for r in mod.router.routes if r.path.endswith("/import-data"))
    db = _CaptureDB()
    out = await endpoint(
        wp_id=_WP_ID, sheet=sheet, file=UploadFile(filename=f"{sheet}.xlsx", file=io.BytesIO(content)),
        db=db, current_user=None,
    )
    return out, db


def _legacy(spec: dict, added: tuple[str, ...]) -> tuple[list[str], list[str]]:
    pairs = [(h, k) for h, k in zip(spec["headers"], spec["field_keys"]) if h not in added]
    return [h for h, _ in pairs], [k for _, k in pairs]


@pytest.mark.parametrize("sheet", sorted(_CASES))
async def test_legacy_file_without_added_columns_imports_without_writing_them(sheet):
    spec, _ = _spec(sheet)
    added = _CASES[sheet][3]
    headers, keys = _legacy(spec, added)
    values = [100.0 if k in {"seq", "debit", "credit", "debitAmount", "creditAmount"} else f"{k}-值" for k in keys]
    out, db = await _import(sheet, _workbook(sheet, headers, values))
    assert out["ok"] is True and out["imported_count"] == 1, out
    row = json.loads(db.writes[-1]["payload"])[0]
    dropped = {k for h, k in zip(spec["headers"], spec["field_keys"]) if h in added}
    assert dropped and not (dropped & set(row)), f"{sheet} 旧版文件缺的列写进了行：{sorted(dropped & set(row))}"
    for k, v in zip(keys, values):
        assert row[k] == v, (k, row[k], v)


@pytest.mark.parametrize("sheet", sorted(_CASES))
async def test_current_file_carries_added_columns(sheet):
    spec, _ = _spec(sheet)
    values = [f"{h}-值" if h in _CASES[sheet][3] else (1.0 if k in {"seq", "debit", "credit", "debitAmount", "creditAmount"} else "x")
              for h, k in zip(spec["headers"], spec["field_keys"])]
    out, db = await _import(sheet, _workbook(sheet, list(spec["headers"]), values))
    assert out["ok"] is True, out
    row = json.loads(db.writes[-1]["payload"])[0]
    for h, k in zip(spec["headers"], spec["field_keys"]):
        if h in _CASES[sheet][3]:
            assert row[k] == f"{h}-值", (k, row.get(k))


@pytest.mark.parametrize("sheet", sorted(_CASES))
async def test_missing_original_column_still_rejected(sheet):
    spec, _ = _spec(sheet)
    headers, keys = _legacy(spec, _CASES[sheet][3])
    drop = headers.index("摘要")
    headers = headers[:drop] + headers[drop + 1:]
    out, db = await _import(sheet, _workbook(sheet, headers, ["x"] * len(headers)))
    assert out["ok"] is False and "摘要" in out["errors"][0], out
    assert db.writes == []


def test_parse_upload_optional_headers_only_relaxes_listed_columns():
    content = _workbook("T", ["A", "B"], [1, 2])
    actual, rows = parse_upload_xlsx(content, ["A", "B", "C"], header_row=2, optional_headers=("C",))
    assert actual == ["A", "B"] and len(rows) == 1
    with pytest.raises(ValueError, match="缺少列: B"):
        parse_upload_xlsx(_workbook("T", ["A"], [1]), ["A", "B", "C"], header_row=2, optional_headers=("C",))
