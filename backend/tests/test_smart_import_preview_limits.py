"""Ledger preview 的 CPU/RSS 预算防回退。"""
from __future__ import annotations

import csv
from unittest.mock import patch

from app.services import smart_import_engine as engine


def test_csv_preview_buffers_at_most_requested_rows(monkeypatch):
    header = "科目编码,科目名称,期末余额\n"
    body = "".join(f"{1000 + index},科目{index},{index}\n" for index in range(2000))
    seen_batches: list[int] = []
    real_reader = csv.reader

    def tracking_reader(lines, *args, **kwargs):
        if isinstance(lines, list):
            seen_batches.append(len(lines))
        return real_reader(lines, *args, **kwargs)

    monkeypatch.setattr(csv, "reader", tracking_reader)
    parsed = engine._parse_csv_for_preview(
        (header + body).encode("utf-8"),
        "余额表.csv",
        max_rows=5,
    )

    assert parsed["row_count"] == 5
    assert len(parsed["rows"]) == 5
    assert parsed["total_lines_est"] >= 2001
    assert max(seen_batches) <= 5


def test_large_complex_workbook_preview_never_opens_full_mode(monkeypatch):
    class Sheet:
        title = "数据"

        def iter_rows(self, **_kwargs):
            return iter([(1, 2)])  # <=3 列触发 needs_full_mode

    class Workbook:
        worksheets = [Sheet()]

        def close(self):
            pass

    opened: list[dict] = []

    def load_workbook(_source, **kwargs):
        opened.append(kwargs)
        return Workbook()

    monkeypatch.setattr("openpyxl.load_workbook", load_workbook)
    monkeypatch.setattr(
        engine,
        "_source_size_bytes",
        lambda _source: 31 * 1024 * 1024,
    )
    with patch(
        "app.core.config.settings.LEDGER_IMPORT_FULL_MODE_MAX_FILE_MB",
        30,
    ):
        result = engine.smart_parse_files(
            [("复杂表.xlsx", b"fake")],
            preview_mode=True,
            preview_rows=10,
        )

    assert len(opened) == 1
    assert opened[0]["read_only"] is True
    assert result["diagnostics"][0]["status"] == "error"
    assert "内存保护阈值" in result["diagnostics"][0]["message"]
