"""正式 PDF 数据来源守卫：不得用空 rows 冒充报表成功。

## 为什么需要这个守卫

`PDFExportEngine.execute_export` 曾固定传
`{"rows": [], "paragraphs": {}, "notes": []}`，转换器可用时就产出一份「成功」
的空白 PDF。用户以为拿到报表，实际一个字都没有 —— 属报成功的失败。

本组用例钉住三条行为判据（行为而非源码文本）：

1. 有真实 `financial_report` 行 ⇒ 返回的行数与库内一致，金额按任务冻结的
   policy divisor 折算一次；
2. 无行 / 缺年度 / 缺 policy 快照 ⇒ 抛 `PDFSourceUnavailable`（路由据此
   409/422），**不返回空 sections 冒充成功**；
3. 尚未接入的文档类型（审计报告、附注）⇒ 明确报「尚未接入」，不静默跳过。

Requirements: AC-20、AC-22
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from app.services.pdf_export_sources import (
    PDFSourceUnavailable,
    build_financial_pdf_data,
)

PROJECT_ID = UUID("11111111-2222-3333-4444-555555555555")


class _FakeRow:
    def __init__(self, *, row_code: str, current, prior, is_total: bool = False) -> None:
        self.row_code = row_code
        self.row_name = f"行 {row_code}"
        self.current_period_amount = current
        self.prior_period_amount = prior
        self.is_total_row = is_total
        self.indent_level = 0


class _FakeResult:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeDb:
    """按 report_type 给出脚本化行的最小 AsyncSession 替身。"""

    def __init__(self, rows_by_type: dict[str, list[_FakeRow]]) -> None:
        self._rows_by_type = rows_by_type
        self.queries = 0

    async def execute(self, stmt):  # noqa: ANN001
        self.queries += 1
        # 从 SQL 里取出 report_type 绑定值不现实（替身不做编译），按查询顺序轮转，
        # 顺序与 build_financial_pdf_data 的循环一致。
        key = list(self._rows_by_type)[self.queries - 1]
        return _FakeResult(self._rows_by_type[key])


def _snapshot(unit: str = "yuan", divisor: int = 1) -> dict:
    return {"unit": unit, "divisor": divisor, "_digest": "a" * 64}


class TestRealRows:
    @pytest.mark.asyncio
    async def test_yuan_rows_are_returned_verbatim(self):
        db = _FakeDb(
            {
                "balance_sheet": [
                    _FakeRow(row_code="BS-001", current=Decimal("100.00"), prior=Decimal("80.00")),
                    _FakeRow(
                        row_code="BS-099",
                        current=Decimal("100.00"),
                        prior=Decimal("80.00"),
                        is_total=True,
                    ),
                ]
            }
        )
        data = await build_financial_pdf_data(
            db,
            project_id=PROJECT_ID,
            year=2025,
            document_types=["balance_sheet"],
            unit_policy_snapshot=_snapshot(),
        )
        assert data["report_type"] == "balance_sheet"
        assert data["unit_label"] == "元"
        assert len(data["sections"]) == 1
        rows = data["sections"][0]["rows"]
        assert [row["row_code"] for row in rows] == ["BS-001", "BS-099"]
        assert rows[0]["current_period_amount"] == Decimal("100.00")
        assert rows[1]["is_total"] is True

    @pytest.mark.asyncio
    async def test_wan_rows_are_scaled_exactly_once(self):
        db = _FakeDb(
            {
                "balance_sheet": [
                    _FakeRow(row_code="BS-001", current=Decimal("350"), prior=Decimal("0"))
                ]
            }
        )
        data = await build_financial_pdf_data(
            db,
            project_id=PROJECT_ID,
            year=2025,
            document_types=["balance_sheet"],
            unit_policy_snapshot=_snapshot("wan", 10000),
        )
        row = data["sections"][0]["rows"][0]
        # 350/10000 = 0.035 → 量化到 0.01 得 0.04（与报表导出同口径）
        assert row["current_period_amount"] == Decimal("0.04")
        assert data["unit_label"] == "万元"

    @pytest.mark.asyncio
    async def test_null_amounts_stay_empty(self):
        db = _FakeDb(
            {"balance_sheet": [_FakeRow(row_code="BS-001", current=None, prior=None)]}
        )
        data = await build_financial_pdf_data(
            db,
            project_id=PROJECT_ID,
            year=2025,
            document_types=["balance_sheet"],
            unit_policy_snapshot=_snapshot(),
        )
        row = data["sections"][0]["rows"][0]
        assert row["current_period_amount"] is None
        assert row["prior_period_amount"] is None


class TestFailClosed:
    @pytest.mark.asyncio
    async def test_missing_year_is_422(self):
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_financial_pdf_data(
                _FakeDb({}),
                project_id=PROJECT_ID,
                year=None,
                document_types=["balance_sheet"],
                unit_policy_snapshot=_snapshot(),
            )
        assert excinfo.value.status_code == 422
        assert "审计年度" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_empty_report_rows_is_409(self):
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_financial_pdf_data(
                _FakeDb({"balance_sheet": []}),
                project_id=PROJECT_ID,
                year=2025,
                document_types=["balance_sheet"],
                unit_policy_snapshot=_snapshot(),
            )
        assert excinfo.value.status_code == 409
        assert "没有可导出的正式数据" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_invalid_policy_snapshot_is_422(self):
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_financial_pdf_data(
                _FakeDb({"balance_sheet": []}),
                project_id=PROJECT_ID,
                year=2025,
                document_types=["balance_sheet"],
                unit_policy_snapshot={"unit": "bogus", "divisor": 1},
            )
        assert excinfo.value.status_code == 422
        assert "单位策略" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_zero_divisor_is_rejected(self):
        with pytest.raises(PDFSourceUnavailable):
            await build_financial_pdf_data(
                _FakeDb({"balance_sheet": []}),
                project_id=PROJECT_ID,
                year=2025,
                document_types=["balance_sheet"],
                unit_policy_snapshot={"unit": "yuan", "divisor": 0},
            )

    @pytest.mark.asyncio
    async def test_not_yet_wired_document_type_is_reported(self):
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_financial_pdf_data(
                _FakeDb({"balance_sheet": []}),
                project_id=PROJECT_ID,
                year=2025,
                document_types=["audit_report"],
                unit_policy_snapshot=_snapshot(),
            )
        assert "尚未接入" in str(excinfo.value)
        assert "audit_report" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_empty_document_types_is_422(self):
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_financial_pdf_data(
                _FakeDb({}),
                project_id=PROJECT_ID,
                year=2025,
                document_types=[],
                unit_policy_snapshot=_snapshot(),
            )
        assert excinfo.value.status_code == 422
