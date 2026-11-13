"""D2-7 凭证检查表导出端点契约测试（Task 2）。

所有请求经 TestClient 发往真实 APIRouter；数据库和读门替换为进程内隔离边界，
因此不会连接或修改共享数据库。
"""
from __future__ import annotations

import io
import uuid
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import openpyxl
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers.wp_render_strategies import _d2_vc_import_export as subject


def _allowing_gate(calls: list[dict[str, Any]]) -> Callable[..., Any]:
    async def allow(*_args: Any, **kwargs: Any) -> None:
        calls.append(kwargs)

    return allow


def _client(monkeypatch: pytest.MonkeyPatch, gate: Callable[..., Any]) -> TestClient:
    """构造只含被测路由的隔离 ASGI 应用。"""
    app = FastAPI()
    app.include_router(subject.router)

    async def get_isolated_db():
        yield SimpleNamespace()

    app.dependency_overrides[subject.get_db] = get_isolated_db
    app.dependency_overrides[subject.get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(subject, "enforce_wp_gate", gate)
    return TestClient(app)


def _workbook(response) -> openpyxl.Workbook:
    assert response.headers["content-type"].startswith(subject.XLSX_MEDIA_TYPE)
    return openpyxl.load_workbook(io.BytesIO(response.content), data_only=False)


def _xlsx_bytes(sheets: dict[str, list[list[Any]]]) -> bytes:
    """生成最小 xlsx 上传体，保留调用方指定的工作表和空行。"""
    workbook = openpyxl.Workbook()
    try:
        for index, (sheet_name, rows) in enumerate(sheets.items()):
            sheet = workbook.active if index == 0 else workbook.create_sheet()
            sheet.title = sheet_name
            for row in rows:
                sheet.append(row)
        with io.BytesIO() as stream:
            workbook.save(stream)
            return stream.getvalue()
    finally:
        workbook.close()


def _post_import(
    client: TestClient,
    wp_id: uuid.UUID,
    content: bytes,
    filename: str = "D2-7_凭证检查表.xlsx",
):
    return client.post(
        f"/api/workpapers/{wp_id}/d2/vc-import-data",
        files={"file": (filename, content, subject.XLSX_MEDIA_TYPE)},
    )


def test_export_template_returns_two_standard_sheets_and_calls_read_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """TestClient 真发请求：模板有两个标准表、17 列表头与 checklist 读门。"""
    calls: list[dict[str, Any]] = []
    wp_id = uuid.uuid4()
    with _client(monkeypatch, _allowing_gate(calls)) as client:
        response = client.post(f"/api/workpapers/{wp_id}/d2/vc-export-template")

    assert response.status_code == 200
    assert calls == [{
        "entrypoint": "workpaper.checklist_read",
        "action": "read_checklist",
        "method": "GET",
        "wp_id": wp_id,
        "entry_family": "checklist",
        "route_name": "/api/workpapers/{wp_id}/d2/vc-export-template",
    }]
    disposition = response.headers["content-disposition"]
    assert "filename*=UTF-8''" in disposition
    assert "%E5%87%AD%E8%AF%81" in disposition

    workbook = _workbook(response)
    try:
        assert workbook.sheetnames == [subject.SHEET_CURRENT, subject.SHEET_POST]
        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            assert [sheet.cell(1, index).value for index in range(1, 18)] == list(subject.COLUMN_HEADERS)
            assert sheet.freeze_panes == "A2"
            assert all(sheet.cell(1, index).font.bold for index in range(1, 18))
            assert all(sheet.column_dimensions[sheet.cell(1, index).column_letter].width >= 14 for index in range(1, 18))
    finally:
        workbook.close()


@pytest.mark.parametrize(("status_code", "detail"), [(403, "没有读取权限"), (404, "底稿不存在")])
def test_export_template_propagates_read_gate_rejection(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    detail: str,
) -> None:
    """读门拒绝时不生成工作簿，保留门返回的 HTTP 状态和原因。"""
    async def reject(*_args: Any, **_kwargs: Any) -> None:
        raise HTTPException(status_code=status_code, detail=detail)

    with _client(monkeypatch, reject) as client:
        response = client.post(f"/api/workpapers/{uuid.uuid4()}/d2/vc-export-template")

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


def test_export_template_rejects_invalid_uuid_before_read_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """路径 UUID 由 FastAPI 校验，非法值不能进入底稿读门。"""
    calls: list[dict[str, Any]] = []
    with _client(monkeypatch, _allowing_gate(calls)) as client:
        response = client.post("/api/workpapers/not-a-uuid/d2/vc-export-template")

    assert response.status_code == 422
    assert calls == []


def test_export_data_preserves_two_zone_values_and_neutralizes_formula_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """数据导出保留前端二维数组，四种公式前缀均以文本单元格写出。"""
    current_rows = [
        list(subject.COLUMN_HEADERS),
        [
            "客户A", "2026-11-04", "=1+1", "+SUM(A1)", "-10", "@cmd",
            12, 13.5, None, "核对1", "核对2", "核对3", "核对4", "核对5",
            "D2-7", "否", "备注",
        ],
    ]
    post_rows = [
        list(subject.COLUMN_HEADERS),
        [
            "客户B", "2026-12-01", "P-001", "期后收款", "银行存款", "基本户",
            99, 0, "回单", "是", "是", "是", "是", "是", "D2-7-1", "否", None,
        ],
    ]
    calls: list[dict[str, Any]] = []
    with _client(monkeypatch, _allowing_gate(calls)) as client:
        response = client.post(
            f"/api/workpapers/{uuid.uuid4()}/d2/vc-export-data",
            json={"currentRows": current_rows, "postRows": post_rows},
        )

    assert response.status_code == 200
    assert calls[0]["entrypoint"] == "workpaper.checklist_read"
    assert calls[0]["action"] == "read_checklist"
    assert calls[0]["method"] == "GET"
    assert calls[0]["entry_family"] == "checklist"
    assert calls[0]["route_name"] == "/api/workpapers/{wp_id}/d2/vc-export-data"

    workbook = _workbook(response)
    try:
        current_sheet = workbook[subject.SHEET_CURRENT]
        post_sheet = workbook[subject.SHEET_POST]
        assert [current_sheet.cell(1, column).value for column in range(1, 18)] == current_rows[0]
        assert [current_sheet.cell(2, column).value for column in range(1, 18)] == current_rows[1]
        assert [post_sheet.cell(1, column).value for column in range(1, 18)] == post_rows[0]
        assert [post_sheet.cell(2, column).value for column in range(1, 18)] == post_rows[1]
        assert all(current_sheet.cell(2, column).data_type == "s" for column in (3, 4, 5, 6))
    finally:
        workbook.close()


@pytest.mark.parametrize(
    ("payload", "expected_location"),
    [
        (
            {"currentRows": [["x"] * 18], "postRows": []},
            ["body", "currentRows", 0],
        ),
        (
            {"currentRows": [], "postRows": [[] for _ in range(subject.MAX_EXPORT_ROWS + 1)]},
            ["body", "postRows"],
        ),
        (
            {"currentRows": [[{"not": "a cell"}]], "postRows": []},
            ["body", "currentRows", 0, 0],
        ),
        (
            {"currentRows": "not-a-grid", "postRows": []},
            ["body", "currentRows"],
        ),
    ],
)
def test_export_data_rejects_invalid_grid_with_zone_row_and_cell_location(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    expected_location: list[Any],
) -> None:
    """二维数组、行数和列数越界均返回可定位到区/行/单元格的 422。"""
    calls: list[dict[str, Any]] = []
    with _client(monkeypatch, _allowing_gate(calls)) as client:
        response = client.post(
            f"/api/workpapers/{uuid.uuid4()}/d2/vc-export-data",
            json=payload,
        )

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any(error["loc"][:len(expected_location)] == expected_location for error in errors)
    assert calls == []


def test_d2_voucher_export_router_is_registered_with_other_d2_import_export_routes() -> None:
    """生产 router registry 必须导入并 include D2-7 双区导出 router。"""
    registry = Path(__file__).resolve().parents[1] / "app/router_registry/workpaper.py"
    source = registry.read_text(encoding="utf-8")
    assert "_d2_vc_import_export import router as d2_vc_import_export" in source
    assert "d2_import_export, d2_vc_import_export, d3_import_export" in source


# ---------------------------------------------------------------------------
# Import endpoint (Task 3)
# ---------------------------------------------------------------------------


def test_import_data_calls_write_gate_before_reading_file_and_normalizes_recognized_sheets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """导入先走 checklist 写门，只返回标准双区并按前端可消费的标量归一。"""
    calls: list[dict[str, Any]] = []
    content = _xlsx_bytes({
        subject.SHEET_CURRENT: [
            list(subject.COLUMN_HEADERS),
            [datetime(2026, 11, 4, 13, 30), 1.0, 1.25, None, "文本", None],
            [None, None, None, None, None],
            ["尾行"],
        ],
        subject.SHEET_POST: [[date(2026, 12, 1), 2.0, 2.75, None, "期后"]],
        "本期增减变动检查（副本）": [["不可识别工作表不得进入回执"]],
    })
    wp_id = uuid.uuid4()

    with _client(monkeypatch, _allowing_gate(calls)) as client:
        response = _post_import(client, wp_id, content)

    assert response.status_code == 200
    assert response.json() == {
        "sheets": {
            subject.SHEET_CURRENT: [
                list(subject.COLUMN_HEADERS),
                ["2026-11-04", 1, 1.25, None, "文本"],
                [],
                ["尾行"],
            ],
            subject.SHEET_POST: [["2026-12-01", 2, 2.75, None, "期后"]],
        },
        "warnings": [],
    }
    assert calls == [{
        "entrypoint": "workpaper.checklist_save",
        "action": "save_checklist",
        "method": "PUT",
        "wp_id": wp_id,
        "entry_family": "checklist",
        "route_name": "/api/workpapers/{wp_id}/d2/vc-import-data",
    }]


def test_import_data_preserves_global_gate_rejection_before_upload_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全局门的不可枚举拒绝原样冒泡，不因文件类型校验改成可区分的响应。"""
    async def reject(*_args: Any, **_kwargs: Any) -> None:
        raise HTTPException(status_code=404, detail="资源不存在或不可访问")

    with _client(monkeypatch, reject) as client:
        response = _post_import(client, uuid.uuid4(), b"not-an-xlsx", "未授权文件.xls")

    assert response.status_code == 404
    assert response.json() == {"detail": "资源不存在或不可访问"}


def test_import_data_rejects_invalid_uuid_before_write_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """非法路径 UUID 由 FastAPI 拒绝，不能进入写门。"""
    calls: list[dict[str, Any]] = []
    with _client(monkeypatch, _allowing_gate(calls)) as client:
        response = client.post(
            "/api/workpapers/not-a-uuid/d2/vc-import-data",
            files={"file": ("导入.xlsx", b"not-an-xlsx", subject.XLSX_MEDIA_TYPE)},
        )

    assert response.status_code == 422
    assert calls == []


def test_import_data_accepts_uppercase_xlsx_and_rejects_other_extensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """扩展名比较大小写不敏感，仅接受 xlsx。"""
    content = _xlsx_bytes({subject.SHEET_CURRENT: [["表头"]]})
    with _client(monkeypatch, _allowing_gate([])) as client:
        accepted = _post_import(client, uuid.uuid4(), content, "导入.XLSX")
        rejected = _post_import(client, uuid.uuid4(), content, "导入.xls")

    assert accepted.status_code == 200
    assert rejected.status_code == 400
    assert rejected.json() == {"detail": "仅支持 .xlsx 文件"}


def test_import_data_rejects_oversized_and_unparseable_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """10MB 上限返回 413，损坏的 xlsx 返回中文解析原因。"""
    with _client(monkeypatch, _allowing_gate([])) as client:
        oversized = _post_import(
            client,
            uuid.uuid4(),
            b"x" * (subject.MAX_IMPORT_FILE_BYTES + 1),
        )
        malformed = _post_import(client, uuid.uuid4(), b"not-an-xlsx")

    assert oversized.status_code == 413
    assert oversized.json() == {"detail": "文件大小超过 10MB 限制"}
    assert malformed.status_code == 400
    assert malformed.json() == {"detail": "文件无法解析，请确认上传的是未损坏的 .xlsx 文件"}


def test_import_data_returns_empty_shape_when_no_standard_sheet_is_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没有精确标准表名时正常返回空结果，不能把相近表名交给前端模糊匹配。"""
    content = _xlsx_bytes({"本期增减变动检查（副本）": [["表头"], ["误导数据"]]})
    with _client(monkeypatch, _allowing_gate([])) as client:
        response = _post_import(client, uuid.uuid4(), content)

    assert response.status_code == 200
    assert response.json() == {"sheets": {}, "warnings": []}


def test_import_data_truncates_recognized_sheet_at_5000_rows_with_chinese_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单个标准工作表超过 5000 行时只回传前 5000 行和可见中文警告。"""
    source_rows = [[f"第{row_index}行"] for row_index in range(subject.MAX_IMPORT_ROWS + 1)]
    content = _xlsx_bytes({subject.SHEET_CURRENT: source_rows})

    with _client(monkeypatch, _allowing_gate([])) as client:
        response = _post_import(client, uuid.uuid4(), content)

    assert response.status_code == 200
    body = response.json()
    assert body["sheets"] == {subject.SHEET_CURRENT: source_rows[:subject.MAX_IMPORT_ROWS]}
    assert body["warnings"] == [
        f"工作表“{subject.SHEET_CURRENT}”超过 {subject.MAX_IMPORT_ROWS} 行，只读取前 {subject.MAX_IMPORT_ROWS} 行"
    ]


def test_export_data_then_import_preserves_both_zones_and_formula_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 2 导出后经 data_only 导入，两个区逐格保持，公式前缀仍是文本。"""
    current_rows = [
        list(subject.COLUMN_HEADERS),
        [
            "客户A", "2026-11-04", "=1+1", "+SUM(A1)", "-10", "@cmd", 12, 13.5,
            None, "核对1", "核对2", "核对3", "核对4", "核对5", "D2-7", "否", "备注",
        ],
    ]
    post_rows = [
        list(subject.COLUMN_HEADERS),
        [
            "客户B", "2026-12-01", "P-001", "期后收款", "银行存款", "基本户", 99,
            0, "回单", "是", "是", "是", "是", "是", "D2-7-1", "否", None,
        ],
    ]
    calls: list[dict[str, Any]] = []
    wp_id = uuid.uuid4()

    with _client(monkeypatch, _allowing_gate(calls)) as client:
        exported = client.post(
            f"/api/workpapers/{wp_id}/d2/vc-export-data",
            json={"currentRows": current_rows, "postRows": post_rows},
        )
        imported = _post_import(client, wp_id, exported.content)

    assert exported.status_code == 200
    assert imported.status_code == 200
    # design §3：读单元格时「每行去掉行尾全空单元格」，行内空单元格保持 None。
    # 本期区末列（备注）非空 ⇒ 整行逐格原样返回，且第 9 列的 None 必须存活（证明只裁行尾）。
    # 期后区末列（备注说明）为 None ⇒ 只裁掉这一个行尾空值，长度 17 → 16。
    # 去掉 _import_row_values 的行尾裁剪后，期后区会多回一个 None ⇒ 本用例打红。
    expected_post_rows = [post_rows[0], post_rows[1][:-1]]
    assert len(expected_post_rows[1]) == len(subject.COLUMN_HEADERS) - 1
    assert imported.json() == {
        "sheets": {
            subject.SHEET_CURRENT: current_rows,
            subject.SHEET_POST: expected_post_rows,
        },
        "warnings": [],
    }
    assert imported.json()["sheets"][subject.SHEET_CURRENT][1][8] is None
    assert [call["entrypoint"] for call in calls] == [
        "workpaper.checklist_read",
        "workpaper.checklist_save",
    ]
