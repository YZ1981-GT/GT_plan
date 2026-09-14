"""Adapter 自动选优 + JSON 驱动加载测试。

覆盖 Task 2.7 / Task 3.4 验收：
- vendor adapter 分数高于 generic 时自动命中
- 低分 adapter 不自动通过关键列 gate
- adapter_hint 覆盖自动选优
- evidence 结构正确
- sample.json 可加载并参与 alias 映射
- JSON 加载：非法文件跳过、覆盖记录来源
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.ledger_import.adapter_selection import (
    ADAPTER_AUTO_PASS_THRESHOLD,
    AdapterSelectionResult,
    merge_aliases,
    select_adapter,
    write_adapter_evidence,
)
from app.services.ledger_import.adapters import (
    AdapterRegistry,
    JsonDrivenAdapter,
    load_json_adapters,
    registry,
)
from app.services.ledger_import.adapters.generic import GenericAdapter
from app.services.ledger_import.detection_types import (
    ColumnMatch,
    FileDetection,
    SheetDetection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fd(
    filename: str = "test.xlsx",
    table_type: str = "balance",
    table_type_confidence: int = 85,
    headers: list[str] | None = None,
) -> FileDetection:
    """Build a FileDetection with optional column_mappings headers."""
    column_mappings = []
    for i, h in enumerate(headers or []):
        column_mappings.append(
            ColumnMatch(
                column_index=i,
                column_header=h,
                standard_field=None,
                column_tier="extra",
                confidence=50,
                source="header_exact",
            )
        )

    sheet = SheetDetection(
        file_name=filename,
        sheet_name="Sheet1",
        row_count_estimate=100,
        header_row_index=0,
        data_start_row=1,
        table_type=table_type,
        table_type_confidence=table_type_confidence,
        confidence_level="high" if table_type_confidence >= 80 else "medium",
        column_mappings=column_mappings,
        preview_rows=[],
        detection_evidence={},
    )
    return FileDetection(
        file_name=filename,
        file_size_bytes=1024,
        file_type="xlsx",
        sheets=[sheet],
    )


def _make_yonyou_json_adapter() -> dict:
    """Return a JSON adapter definition for yonyou-style files."""
    return {
        "id": "yonyou_json",
        "display_name": "用友 JSON",
        "priority": 80,
        "match_patterns": {
            "filename_regex": ["(?i)(用友|UFIDA|U8)"],
            "signature_columns": {
                "balance": ["科目编码", "科目名称", "方向", "年初余额"],
            },
        },
        "column_aliases": {
            "balance": {
                "account_code": ["科目编码", "科目代码"],
                "opening_balance": ["年初余额", "期初余额"],
            },
        },
    }


# ---------------------------------------------------------------------------
# Task 2.7: vendor adapter 分数高于 generic 时自动命中
# ---------------------------------------------------------------------------


class TestAdapterAutoSelect:
    """Adapter 自动选优测试 (Task 2.1 ~ 2.6)。"""

    def test_vendor_high_score_auto_pass(self):
        """vendor adapter 文件名+签名列命中 → 分数 >= threshold → 自动通过。"""
        reg = AdapterRegistry()
        reg.register(GenericAdapter())
        reg.register(JsonDrivenAdapter(_make_yonyou_json_adapter()))

        # 文件名含"用友" + 签名列全部命中 → score = 0.5 + 0.5 = 1.0
        fd = _make_fd(
            filename="用友U8_余额表.xlsx",
            table_type="balance",
            headers=["科目编码", "科目名称", "方向", "年初余额"],
        )

        result = select_adapter(fd, registry=reg)

        assert result.adapter_id == "yonyou_json"
        assert result.adapter_score >= ADAPTER_AUTO_PASS_THRESHOLD
        assert result.is_auto_pass is True
        assert result.requires_human_confirm is False

    def test_low_score_adapter_not_auto_pass(self):
        """低分 adapter 不自动通过，退回 generic 进入人工确认。"""
        reg = AdapterRegistry()
        reg.register(GenericAdapter())
        # 低 priority adapter 没有 filename_regex
        reg.register(JsonDrivenAdapter({
            "id": "weak_vendor",
            "display_name": "Weak",
            "priority": 50,
            "match_patterns": {
                "signature_columns": {
                    "balance": ["非常罕见的列A", "非常罕见的列B"],
                },
            },
            "column_aliases": {},
        }))

        # 文件名无匹配，签名列也不命中 → score 很低
        fd = _make_fd(
            filename="通用余额表.xlsx",
            table_type="balance",
            table_type_confidence=85,  # 高置信表类型
            headers=["科目编码", "科目名称", "借方", "贷方"],
        )

        result = select_adapter(fd, registry=reg)

        # 低分退回 generic
        assert result.adapter_id == "generic"
        assert result.is_auto_pass is False
        assert result.requires_human_confirm is True
        assert result.evidence.get("fallback_to_generic") is True

    def test_adapter_hint_overrides_auto_detect(self):
        """adapter_hint 存在时跳过自动选优，直接使用指定 adapter。"""
        reg = AdapterRegistry()
        reg.register(GenericAdapter())
        reg.register(JsonDrivenAdapter(_make_yonyou_json_adapter()))

        # 文件名不匹配用友，但 hint 指定
        fd = _make_fd(
            filename="unknown_software.xlsx",
            table_type="balance",
            headers=["科目编码"],
        )

        result = select_adapter(fd, adapter_hint="yonyou_json", registry=reg)

        assert result.adapter_id == "yonyou_json"
        assert result.source == "user_hint"
        assert result.is_auto_pass is True

    def test_adapter_hint_not_found_falls_back(self):
        """adapter_hint 不存在时 fallback 到自动选优。"""
        reg = AdapterRegistry()
        reg.register(GenericAdapter())

        fd = _make_fd(filename="test.xlsx")
        result = select_adapter(fd, adapter_hint="nonexistent", registry=reg)

        # Falls back to generic (only adapter registered)
        assert result.adapter_id == "generic"
        assert result.source == "auto_detect"

    def test_evidence_written_to_detection(self):
        """write_adapter_evidence 将结果写入 detection_evidence.adapter_match。"""
        reg = AdapterRegistry()
        reg.register(GenericAdapter())
        reg.register(JsonDrivenAdapter(_make_yonyou_json_adapter()))

        fd = _make_fd(
            filename="用友U8_余额表.xlsx",
            table_type="balance",
            headers=["科目编码", "科目名称", "方向", "年初余额"],
        )

        result = select_adapter(fd, registry=reg)
        write_adapter_evidence(fd, result)

        # 检查每个 sheet 的 evidence
        for sheet in fd.sheets:
            am = sheet.detection_evidence.get("adapter_match")
            assert am is not None
            assert am["adapter_id"] == "yonyou_json"
            assert am["adapter_score"] >= 0.6
            assert am["source"] == "auto_detect"
            assert am["is_auto_pass"] is True
            assert sheet.adapter_id == "yonyou_json"

    def test_evidence_structure_complete(self):
        """evidence 包含 matched_filename / matched_signature_columns。"""
        reg = AdapterRegistry()
        reg.register(GenericAdapter())
        reg.register(JsonDrivenAdapter(_make_yonyou_json_adapter()))

        fd = _make_fd(
            filename="用友U8_余额表.xlsx",
            table_type="balance",
            headers=["科目编码", "科目名称", "方向", "年初余额"],
        )

        result = select_adapter(fd, registry=reg)

        assert result.evidence["matched_filename"] is True
        assert "科目编码" in result.evidence["matched_signature_columns"]


# ---------------------------------------------------------------------------
# Task 2.4: merge_aliases
# ---------------------------------------------------------------------------


class TestMergeAliases:
    """Adapter aliases 与 generic aliases 合并 (Task 2.4)。"""

    def test_adapter_aliases_override_generic(self):
        """adapter aliases 中的字段优先出现在合并列表前面。"""
        adapter = JsonDrivenAdapter(_make_yonyou_json_adapter())
        merged = merge_aliases(adapter, "balance")

        # adapter 有 account_code → 其 aliases 应在前
        assert "account_code" in merged
        assert "科目编码" in merged["account_code"]

    def test_generic_fields_preserved(self):
        """adapter 没有定义的字段仍从 generic 保留。"""
        adapter = JsonDrivenAdapter({
            "id": "minimal",
            "column_aliases": {"balance": {"account_code": ["代码"]}},
        })
        merged = merge_aliases(adapter, "balance")

        # generic 有很多字段（如 debit_amount），adapter 未覆盖时应保留
        assert "account_code" in merged
        assert "代码" in merged["account_code"]


# ---------------------------------------------------------------------------
# Task 3.4: sample.json 可加载并参与 alias 映射
# ---------------------------------------------------------------------------


class TestJsonAdapterLoading:
    """JSON 驱动适配器加载测试 (Task 3)。"""

    def test_sample_json_loaded_in_global_registry(self):
        """backend/data/ledger_adapters/sample.json 被加载到全局 registry。"""
        # sample.json id="yonyou" — 会覆盖内置 YonyouAdapter（同 id）
        # 但全局 registry 应至少包含它
        adapter = registry.get("yonyou")
        assert adapter is not None
        # 确认它有 aliases
        aliases = adapter.get_column_aliases("balance")
        assert "account_code" in aliases

    def test_load_json_adapters_explicit_directory(self, tmp_path: Path):
        """load_json_adapters 从指定目录加载。"""
        (tmp_path / "test_vendor.json").write_text(
            json.dumps({
                "id": "test_vendor",
                "display_name": "Test Vendor",
                "priority": 70,
                "match_patterns": {"filename_regex": ["(?i)test_vendor"]},
                "column_aliases": {
                    "balance": {"account_code": ["测试科目编码"]},
                },
            }),
            encoding="utf-8",
        )

        reg = AdapterRegistry()
        reg.register(GenericAdapter())
        count = load_json_adapters(directory=tmp_path, target_registry=reg)

        assert count == 1
        adapter = reg.get("test_vendor")
        assert adapter is not None
        aliases = adapter.get_column_aliases("balance")
        assert "测试科目编码" in aliases.get("account_code", [])

    def test_invalid_json_skipped(self, tmp_path: Path):
        """非法 JSON 文件被跳过不影响其他加载 (Task 3.2)。"""
        # 有效文件
        (tmp_path / "good.json").write_text(
            json.dumps({"id": "good_adapter", "priority": 50}),
            encoding="utf-8",
        )
        # 非法 JSON
        (tmp_path / "bad.json").write_text("{ invalid json }", encoding="utf-8")
        # 缺 id
        (tmp_path / "no_id.json").write_text(
            json.dumps({"display_name": "No ID"}), encoding="utf-8"
        )
        # _ 前缀文件跳过
        (tmp_path / "_schema.json").write_text(
            json.dumps({"id": "schema"}), encoding="utf-8"
        )

        reg = AdapterRegistry()
        count = load_json_adapters(directory=tmp_path, target_registry=reg)

        assert count == 1  # only good.json
        assert reg.get("good_adapter") is not None
        assert reg.get("schema") is None

    def test_same_id_replacement_logged(self, tmp_path: Path, caplog):
        """同 id adapter 覆盖时记录来源 (Task 3.3)。"""
        (tmp_path / "v1.json").write_text(
            json.dumps({"id": "dup_test", "priority": 50, "display_name": "V1"}),
            encoding="utf-8",
        )

        reg = AdapterRegistry()
        reg.register(GenericAdapter())
        # 先注册一个同 id 的
        reg.register(JsonDrivenAdapter({"id": "dup_test", "priority": 40}))

        import logging
        with caplog.at_level(logging.INFO):
            load_json_adapters(directory=tmp_path, target_registry=reg)

        # 验证替换日志
        assert any("dup_test" in record.message and "replaced" in record.message
                   for record in caplog.records)

    def test_regex_error_skipped(self, tmp_path: Path):
        """无效 regex 的 adapter 仍然加载成功，但该 regex 不参与匹配。"""
        (tmp_path / "bad_regex.json").write_text(
            json.dumps({
                "id": "bad_regex_adapter",
                "priority": 60,
                "match_patterns": {
                    "filename_regex": ["(?P<invalid"],  # invalid regex
                },
                "column_aliases": {
                    "balance": {"account_code": ["编码"]},
                },
            }),
            encoding="utf-8",
        )

        reg = AdapterRegistry()
        count = load_json_adapters(directory=tmp_path, target_registry=reg)

        # 加载成功（无效 regex 被跳过，不阻止整个 adapter）
        assert count == 1
        adapter = reg.get("bad_regex_adapter")
        assert adapter is not None
        # aliases 仍可用
        aliases = adapter.get_column_aliases("balance")
        assert "编码" in aliases.get("account_code", [])
