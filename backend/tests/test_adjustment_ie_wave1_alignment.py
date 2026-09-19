"""Wave 1 —— 底稿调整 sheet 三重键对齐 + Round_Trip。

spec: adjustment-import-export-contract / Task 2.6

覆盖：
  * Property 9  三方键一致：遍历 `backend/data/adjustment_ie_contract.json` 的 `sheets`，
                后端 `_SPECS` 的 `item_id` / **有效** `storage_field` / `field_keys` 必须逐字等于清单。
  * Property 10 导出字段完备：清单 `frontend_row_model` 去掉 `frontend_extra_fields` 后，
                必须被 `field_keys` 全覆盖（用户可填列不得漏出导出模板）。
  * Property 13 7 张无漂移 sheet 的 `item_id` / `headers` / `field_keys` 不变
                （逐字节基线在 test_adjustment_ie_characterization.py；此处只做交叉守卫）。
  * Round_Trip  对 Wave 1 施工的 6 张 sheet：导出模板 → 填 → 导入 →
                断言落库到 **前端读取键**（`item_id` 的 `storage_field` 列）且字段逐字对应。
                接口 `ok=True` 不作为通过依据。

不依赖真实 DB：用 fake AsyncSession 捕获 `upsert_json_payload` 的 SQL 文本与参数。
"""
from __future__ import annotations

import importlib
import inspect
import io
import json
import re
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from fastapi import UploadFile

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "data" / "adjustment_ie_contract.json"

_FACTORY_DEFAULT_STORAGE_FIELD = "conclusion"

# sheet → (模块路径, _SPECS 属性名, router 属性名)
_SHEET_MODULES: dict[str, tuple[str, str]] = {
    "K1-4": ("app.routers.wp_render_strategies._k1_import_export", "_K1_SPECS"),
    "K2-3": ("app.routers.wp_render_strategies._k2_import_export", "_K2_SPECS"),
    "K3-3": ("app.routers.wp_render_strategies._k3_import_export", "_K3_SPECS"),
    "K4-3": ("app.routers.wp_render_strategies._k4_import_export", "_K4_SPECS"),
    "K5-3": ("app.routers.wp_render_strategies._k5_import_export", "_K5_SPECS"),
    "K6-3": ("app.routers.wp_render_strategies._k6_import_export", "_K6_SPECS"),
    "K7-3": ("app.routers.wp_render_strategies._k7_import_export", "_K7_SPECS"),
    "K8-3": ("app.routers.wp_render_strategies._k8_import_export", "_K8_SPECS"),
    "K9-3": ("app.routers.wp_render_strategies._k9_import_export", "_K9_SPECS"),
    "K11-3": ("app.routers.wp_render_strategies._k11_import_export", "_K11_SPECS"),
    "K12-3": ("app.routers.wp_render_strategies._k12_import_export", "_K12_SPECS"),
    "K13-3": ("app.routers.wp_render_strategies._k13_import_export", "_K13_SPECS"),
    "I5-3": ("app.routers.wp_render_strategies._i5_import_export", "_I5_SPECS"),
    "I6-3": ("app.routers.wp_render_strategies._i6_import_export", "_I6_SPECS"),
}

# 需做 Round_Trip 的 sheet：Wave 1 施工的 6 张（Task 2.2/2.3/2.4）+ Wave 2 的 K12-3（Task 3.3）
_WAVE1_ROUNDTRIP = ["K2-3", "K3-3", "K4-3", "K5-3", "K7-3", "K8-3", "K12-3"]

# Property 13：本波不得改动的无漂移 sheet
_NO_DRIFT = ["K9-3", "K11-3", "K13-3"]


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _load_spec(sheet: str) -> tuple[dict, Any]:
    mod_path, attr = _SHEET_MODULES[sheet]
    mod = importlib.import_module(mod_path)
    specs = getattr(mod, attr)
    assert sheet in specs, f"{attr} 缺少 {sheet} 条目（注册遗漏 → 前端点导入导出会报「不支持的sheet」）"
    return specs[sheet], mod


def _router_args(mod) -> str:
    src = inspect.getsource(mod)
    marker = "create_cycle_import_export_router("
    idx = src.index(marker)
    i = idx + len(marker)
    depth = 1
    while i < len(src) and depth:
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
        i += 1
    return src[idx + len(marker):i - 1]


def _effective_storage_field(sheet: str) -> str:
    spec, mod = _load_spec(sheet)
    if "storage_field" in spec:
        return spec["storage_field"]
    m = re.search(r'storage_field\s*=\s*"([^"]*)"', _router_args(mod))
    return m.group(1) if m else _FACTORY_DEFAULT_STORAGE_FIELD


# ═══════════════════════════════════════════════════════════════════════════
# Property 9 —— 三方键一致（遍历清单，不硬编码逐条）
# ═══════════════════════════════════════════════════════════════════════════


def test_p9_contract_covers_every_known_adjustment_sheet(contract):
    """清单 sheets 必须覆盖本文件登记的全部调整 sheet（模块表 ⊆ 清单，防漏登记）。"""
    missing = sorted(set(_SHEET_MODULES) - set(contract["sheets"]))
    assert not missing, f"契约清单缺少调整 sheet 条目: {missing}"


@pytest.mark.parametrize("sheet", sorted(_SHEET_MODULES))
def test_p9_item_id_matches_contract(sheet, contract):
    entry = contract["sheets"][sheet]
    if entry["status"] != "aligned":
        pytest.skip(f"{sheet} 仍待对齐（status={entry['status']}，aligns_in_task={entry['aligns_in_task']}）")
    spec, _ = _load_spec(sheet)
    assert spec["item_id"] == entry["item_id"], (
        f"{sheet}.item_id 漂移：后端 {spec['item_id']!r} != 清单 {entry['item_id']!r}"
    )


@pytest.mark.parametrize("sheet", sorted(_SHEET_MODULES))
def test_p9_effective_storage_field_matches_contract(sheet, contract):
    """有效 storage_field（spec 显式 → router 显式 → 工厂默认 conclusion）必须等于清单。"""
    entry = contract["sheets"][sheet]
    if entry["status"] != "aligned":
        pytest.skip(f"{sheet} 仍待对齐（status={entry['status']}）")
    actual = _effective_storage_field(sheet)
    assert actual == entry["storage_field"], (
        f"{sheet}.storage_field 漂移：后端有效值 {actual!r} != 清单 {entry['storage_field']!r}"
        "（写错列 → 前端永远读不到，最隐蔽的 Orphan_Key 形态）"
    )


@pytest.mark.parametrize("sheet", sorted(_SHEET_MODULES))
def test_p9_field_keys_match_contract(sheet, contract):
    entry = contract["sheets"][sheet]
    if entry["status"] != "aligned":
        pytest.skip(f"{sheet} 仍待对齐（status={entry['status']}）")
    spec, _ = _load_spec(sheet)
    assert list(spec["field_keys"]) == entry["field_keys"], (
        f"{sheet}.field_keys 漂移：\n  后端 {list(spec['field_keys'])}\n  清单 {entry['field_keys']}"
    )


@pytest.mark.parametrize("sheet", sorted(_SHEET_MODULES))
def test_p9_headers_and_field_keys_same_length(sheet):
    spec, _ = _load_spec(sheet)
    assert len(spec["headers"]) == len(spec["field_keys"]), (
        f"{sheet} headers/field_keys 长度不一致（导入按名匹配 zip，长度不等会静默丢列）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Property 10 —— 导出字段完备（用户可填列不得漏出导出模板）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("sheet", sorted(_SHEET_MODULES))
def test_p10_field_keys_cover_frontend_user_fillable_fields(sheet, contract):
    entry = contract["sheets"][sheet]
    if entry["status"] != "aligned":
        pytest.skip(f"{sheet} 仍待对齐（status={entry['status']}）")
    expected_cover = [
        f for f in entry["frontend_row_model"]
        if f not in set(entry.get("frontend_extra_fields") or [])
    ]
    missing = [f for f in expected_cover if f not in entry["field_keys"]]
    assert not missing, (
        f"{sheet} 用户可填字段未进导出列: {missing}"
        "（若确为不可填/派生列，须登记到 frontend_extra_fields 并写明原因，不得隐藏）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Property 13 —— 无漂移 sheet 本波不得改动
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("sheet", _NO_DRIFT)
def test_p13_no_drift_sheets_unchanged(sheet, contract):
    """K9-3 / K11-3 / K13-3 三维保持 aligned 且与清单一致（逐字节基线见 characterization）。"""
    entry = contract["sheets"][sheet]
    assert entry["status"] == "aligned", f"{sheet} 本波不得从 aligned 退化"
    spec, _ = _load_spec(sheet)
    assert spec["item_id"] == entry["item_id"]
    assert _effective_storage_field(sheet) == "remark"
    assert list(spec["field_keys"]) == entry["field_keys"]


# ═══════════════════════════════════════════════════════════════════════════
# Round_Trip —— 导出模板 → 填 → 导入 → 落库到前端读取键
# ═══════════════════════════════════════════════════════════════════════════

_WP_ID = "11111111-1111-1111-1111-111111111111"
_PROJECT_ID = "22222222-2222-2222-2222-222222222222"


class _CaptureResult:
    def __init__(self, value: Any = None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def fetchone(self):
        return None

    def all(self):
        return []


class _CaptureDB:
    """捕获 upsert 的 SQL 文本与参数（不触库）。"""

    def __init__(self):
        self.writes: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if "SELECT project_id FROM working_paper" in sql:
            return _CaptureResult(_PROJECT_ID)
        if sql.strip().upper().startswith("SELECT"):
            # 读取既有 payload（导出/回退读）→ 视为无数据
            return _CaptureResult(None)
        self.writes.append((sql, dict(params or {})))
        return _CaptureResult(None)

    async def commit(self):
        return None

    async def flush(self):
        return None

    async def rollback(self):
        return None


def _endpoint(mod, suffix: str):
    router = getattr(mod, "router")
    for route in router.routes:
        if route.path.endswith(suffix):
            return route.endpoint
    raise AssertionError(f"router 无 {suffix} 端点")


async def _export_template_bytes(sheet: str) -> bytes:
    _, mod = _load_spec(sheet)
    resp = await _endpoint(mod, "/export-template")(
        wp_id=_WP_ID, sheet=sheet, db=_CaptureDB(), current_user=None,
    )
    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode())
    return b"".join(chunks)


def _sample_value(key: str, header: str, idx: int) -> Any:
    from app.routers.wp_render_strategies._cycle_import_export_common import (
        is_numeric_field_key,
    )

    if is_numeric_field_key(key):
        return float(1000 + idx)
    return f"{header}-测试值{idx}"


async def _import_bytes(sheet: str, content: bytes) -> tuple[dict, _CaptureDB]:
    _, mod = _load_spec(sheet)
    db = _CaptureDB()
    upload = UploadFile(filename=f"{sheet}.xlsx", file=io.BytesIO(content))
    out = await _endpoint(mod, "/import-data")(
        wp_id=_WP_ID, sheet=sheet, file=upload, db=db, current_user=None,
    )
    return out, db


@pytest.mark.parametrize("sheet", _WAVE1_ROUNDTRIP)
async def test_roundtrip_export_fill_import_lands_on_frontend_key(sheet, contract):
    """导出模板 → 按列头填一行 → 导入 → 断言写到前端读取键（item_id 的 storage_field 列）。

    验收口径：`ok=True` 不算通过，必须落到 **前端会读的那一列**，且字段值逐字对应。
    """
    entry = contract["sheets"][sheet]
    spec, _ = _load_spec(sheet)

    # 1) 导出模板并核对列头（title 占第 1 行 → 列头在第 2 行，与工厂 header_row 默认一致）
    tpl = await _export_template_bytes(sheet)
    wb = openpyxl.load_workbook(io.BytesIO(tpl))
    ws = wb[sheet]
    headers = [
        ws.cell(row=2, column=c).value for c in range(1, len(spec["headers"]) + 1)
    ]
    assert headers == list(spec["headers"]), f"{sheet} 模板列头与 Sheet_Spec 不一致"

    # 2) 填一行数据（按 field_keys 的数值/文本语义造值）
    filled = {
        key: _sample_value(key, header, i)
        for i, (header, key) in enumerate(zip(spec["headers"], spec["field_keys"]))
    }
    ws.append([filled[k] for k in spec["field_keys"]])
    buf = io.BytesIO()
    wb.save(buf)

    # 3) 导入
    out, db = await _import_bytes(sheet, buf.getvalue())
    assert out["ok"] is True and out["imported_count"] == 1, out

    # 4) 断言落库位置 = 前端读取键（item_id + storage_field 列），且字段逐字对应
    assert db.writes, f"{sheet} 导入未产生任何写入"
    sql, params = db.writes[-1]
    assert params["item_id"] == entry["item_id"], (
        f"{sheet} 落库 item_id={params['item_id']!r}，前端读的是 {entry['item_id']!r}"
    )
    field = entry["storage_field"]
    assert f"INSERT INTO checklist_responses" in sql and f" {field}," in sql, (
        f"{sheet} 落库列不是前端读取列 {field!r}；SQL={sql!r}"
    )
    rows = json.loads(params["payload"])
    assert isinstance(rows, list) and len(rows) == 1
    got = rows[0]
    for key, expected in filled.items():
        assert got.get(key) == expected, f"{sheet}.{key} 往返不一致：{got.get(key)!r} != {expected!r}"


@pytest.mark.parametrize("sheet", _WAVE1_ROUNDTRIP)
async def test_roundtrip_rejects_wrong_template(sheet):
    """错表/缺列的 xlsx 必须被拒（可读错误），不得静默导入空数据。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(["标题占位"])
    ws.append(["完全不相干的列A", "完全不相干的列B"])
    ws.append(["x", "y"])
    buf = io.BytesIO()
    wb.save(buf)

    out, db = await _import_bytes(sheet, buf.getvalue())
    assert out["ok"] is False and out["imported_count"] == 0
    assert out["errors"], "必须返回可读错误"
    assert not db.writes, "被拒的导入不得写库"
