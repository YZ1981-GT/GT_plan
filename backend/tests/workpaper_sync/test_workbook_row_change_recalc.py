# -*- coding: utf-8 -*-
"""Task 25 —— Property 31：传播产物在**真实 Excel** 里重算指向正确数据。

spec: excel-workbook-wide-row-change-propagation / Wave 5 Task 25
Requirements: 8.1, 8.2（产物可打开 + 被传播公式求值正确）

═══ 这一层验的是什么，不验什么 ═══

| 层 | 手段 | 已在哪 |
|---|---|---|
| 字节级：改对了没有 | 逐处比对声明 | Task 10/11/13 |
| 结构级：产物是不是合法 xlsx | openpyxl 加载 | Task 13/18 |
| **语义级：公式重算指向对不对** | **真实 Excel COM 重算** | **本文件** |

🔴 前两层**都不能**替代本层。一份把 `'明细表D2-2'!$S$13:$S$25` 改成
`$S$14:$S$26` 的产物，即便字节与声明逐字吻合、openpyxl 也能打开，仍然可能**指错数据**
—— 只有让 Excel 自己重算、再核对结果，才能证明「引用跟着数据走了」。

═══ 环境不可得时的纪律（AC 11.8 同源）═══

**标 `UNVERIFIABLE` 并 skip，绝不用 fixture 冒充。** `_excel_engine()` 现探 COM 桥与
Excel 本体，探不到就在 skip 理由里写明缺什么。本机实测 **Excel 16.0（
CalculationVersion 162913）可用**，所以这些判据在本机是**真跑**的，不是长期 skip。

⚠ 本层**不**验「OnlyOffice 编辑器里所见即所愿」—— 那需要人工在真实编辑器里看，
不冒充。
"""

from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import (  # noqa: E402
    _normalise_part,
    _parse_workbook_xml,
)
from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402

TEMPLATE_ROOT = _BACKEND / "wp_templates"
D2_REL = "D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx"
D2_SHEET = "明细表D2-2"
D2_REGION = (13, 25)


def _excel_engine() -> tuple[bool, str]:
    """现探真实 Excel 能力。返回 `(可用, 详情)`；不可用时详情以 `UNVERIFIABLE:` 起头。

    与 `test_excel_row_insertion_openability._onlyoffice_engine()` 同形 —— 那是本仓
    既有的「环境不可得就诚实标记」范式，这里沿用而不另造一套。
    """
    if sys.platform != "win32":
        return False, f"UNVERIFIABLE: 非 Windows 平台（{sys.platform}），无 Excel COM"
    try:
        import win32com.client  # type: ignore  # noqa: F401
    except ImportError:
        return False, "UNVERIFIABLE: 缺 pywin32（win32com.client 导不进来）"
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore

        pythoncom.CoInitialize()
        try:
            app = win32com.client.DispatchEx("Excel.Application")
        except Exception as exc:  # noqa: BLE001
            return False, f"UNVERIFIABLE: Excel COM 启动失败（{type(exc).__name__}: {exc}）"
        try:
            version = str(app.Version)
            calc_version = str(app.CalculationVersion)
        finally:
            app.Quit()
        return True, f"Excel {version} / CalculationVersion {calc_version}"
    except Exception as exc:  # noqa: BLE001
        return False, f"UNVERIFIABLE: COM 初始化异常（{type(exc).__name__}: {exc}）"
    finally:
        try:
            import pythoncom  # type: ignore

            pythoncom.CoUninitialize()
        except Exception:  # noqa: BLE001,S110 - 清理失败不该改变判据结论
            pass


def _recalc_and_read(path: Path, cells: dict[str, list[str]]) -> dict[str, Any]:
    """在真实 Excel 里**强制全量重算**，读回指定单元格的值与公式。

    Args:
        path: xlsx 绝对路径。
        cells: `{sheet 名: [A1 坐标, ...]}`。

    Returns:
        `{f"{sheet}!{cell}": {"value": ..., "formula": ...}}`

    🔴 `CalculateFullRebuild()` 而不是 `Calculate()`：后者只重算「脏」单元格，而我们
    刚改的是**公式文本**，Excel 打开时可能直接用缓存的 `<v>` ⇒ 读到的是**改前**的值，
    判据会假绿。全量重建强制它按新公式重新求值。
    """
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore

    pythoncom.CoInitialize()
    out: dict[str, Any] = {}
    app = win32com.client.DispatchEx("Excel.Application")
    try:
        app.Visible = False
        app.DisplayAlerts = False
        app.AskToUpdateLinks = False
        # 外部链接不去解析（D2 有指向别的工作簿的引用）—— 否则会弹框或长时间等待
        wb = app.Workbooks.Open(
            str(path), UpdateLinks=0, ReadOnly=True, IgnoreReadOnlyRecommended=True
        )
        try:
            app.CalculateFullRebuild()
            for sheet_name, coords in cells.items():
                ws = wb.Worksheets(sheet_name)
                for coord in coords:
                    cell = ws.Range(coord)
                    out[f"{sheet_name}!{coord}"] = {
                        "value": cell.Value,
                        "formula": cell.Formula,
                    }
        finally:
            wb.Close(SaveChanges=False)
    finally:
        app.Quit()
        try:
            pythoncom.CoUninitialize()
        except Exception:  # noqa: BLE001,S110
            pass
    return out


@pytest.fixture(scope="module")
def engine() -> tuple[bool, str]:
    return _excel_engine()


@pytest.fixture(scope="module")
def d2_propagated(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """在 D2 上插一行，产出 `(改前路径, 改后路径, 计划)`。"""
    src = TEMPLATE_ROOT / D2_REL
    if not src.is_file():  # pragma: no cover
        pytest.skip(f"D2 权威模板不在磁盘上：{D2_REL}")
    data = src.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sheets, defined = _parse_workbook_xml(zf)
        parts = {s["name"]: _normalise_part(s["rel_target"]) for s in sheets}
        scan = N1.scan_reference_carriers(
            zf, target_sheet=D2_SHEET, sheet_parts=parts, defined_names=defined
        )
    plan = N1.build_insert_plan(
        scan,
        managed_sheet_name=D2_SHEET,
        managed_sheet_part=parts[D2_SHEET],
        at=15,
        count=1,
        style_from=14,
        region_first_row=D2_REGION[0],
        region_last_row=D2_REGION[1],
    )
    produced, report = N1.apply_workbook_row_change(data, plan, sheet_parts=parts)
    report.assert_matches_plan(plan)

    workdir = tmp_path_factory.mktemp("d2_recalc")
    before = workdir / "before.xlsx"
    after = workdir / "after.xlsx"
    before.write_bytes(data)
    after.write_bytes(produced)
    return {
        "before": before,
        "after": after,
        "plan": plan,
        "parts": parts,
        "report": report,
    }
