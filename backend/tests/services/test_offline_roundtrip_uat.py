"""C.0.23 — Offline Export → Import Round-Trip UAT (E2E).

直接调 service 函数验证整个 D15 离线分发流程，确保数据无丢失。
"""
from __future__ import annotations

import os
import tempfile
from io import BytesIO
from uuid import uuid4

import pytest

from app.services.note_offline_export_service import export_sections_to_xlsx
from app.services.note_offline_import_service import (
    ConflictResolution,
    apply_import,
    diff_sections,
    validate_import_file,
)


def _make_realistic_section(section_id: str, title: str, n_rows: int = 10) -> dict:
    """模拟现实附注章节（货币资金、应收账款等结构）."""
    return {
        "section_id": section_id,
        "section_title": title,
        "table_data": {
            "headers": ["项目", "期末余额", "期初余额"],
            "rows": [
                {
                    "row_type": "data",
                    "label": f"项目{r}",
                    "cells": [f"项目{r}", float(r * 100000), float(r * 95000)],
                }
                for r in range(1, n_rows + 1)
            ],
        },
        "_cell_meta": {
            "0:1": {"source": "trial_balance"},
            "0:2": {"source": "trial_balance"},
        },
        "_formulas": {},
        "_cell_provenance": {
            "0:1": {"source": "trial_balance", "account_codes": ["1001"]},
        },
        "_bindings": {},
        "_row_meta": [],
        "_dynamic_regions": [],
        "_cell_modes": {},
    }


class TestOfflineRoundTripUAT:
    """C.0.23 端到端 round-trip：partner 导出 → 模拟成员填写 → 一键导回."""

    def test_export_60_sections_then_import_back(self):
        """完整 round-trip：60 章节导出 → 验证 → diff → 导入决策."""
        # Step 1: 准备 60 章节数据（模拟 partner 已编辑的附注）
        sections = [
            _make_realistic_section(f"section_{i}", f"章节{i}", n_rows=5)
            for i in range(60)
        ]

        # Step 2: 导出为 xlsx 包
        xlsx_bytes, file_hash = export_sections_to_xlsx(
            sections,
            include_formulas=True,
            include_provenance=True,
            exporter_name="partner_test",
            project_name="UAT 测试项目",
            year=2025,
        )

        assert len(xlsx_bytes) > 5000  # xlsx should be non-trivial size
        assert len(file_hash) == 64  # SHA-256

        # Step 3: 验证导入文件
        validation = validate_import_file(xlsx_bytes)
        assert validation.valid is True
        assert len(validation.section_ids) == 60
        assert validation.binding_hash != ""
        assert validation.format_version == "1.0"

        # Step 4: 对比 imported vs existing（应零差异，因为是同份数据）
        diffs = diff_sections(xlsx_bytes, sections, validation.meta_data)

        # 60 个 matched + 0 import_only + 0 system_only
        from app.services.note_offline_import_service import MatchStatus
        matched = [d for d in diffs if d.match_status == MatchStatus.MATCHED]
        assert len(matched) == 60

        # Step 5: 应用导入（全部 keep — 完整 round-trip 应无变化）
        decisions = {
            f"section_{i}": ConflictResolution.OVERWRITE for i in range(60)
        }
        result = apply_import(xlsx_bytes, sections, decisions)
        assert result.success is True
        assert result.sections_imported == 60

    def test_modified_sections_diff_detected(self):
        """成员修改部分章节 → diff 应正确检测出修改."""
        # 原始 partner 数据
        original = [_make_realistic_section(f"s{i}", f"x{i}", n_rows=3) for i in range(5)]

        # 模拟成员修改：把 s0 的第 0 行第 1 列从原值改为 999
        modified = [_make_realistic_section(f"s{i}", f"x{i}", n_rows=3) for i in range(5)]
        modified[0]["table_data"]["rows"][0]["cells"][1] = 999.0

        # 成员导出修改后的版本
        modified_xlsx, _ = export_sections_to_xlsx(modified)

        # Partner 导入：对比 modified vs original
        validation = validate_import_file(modified_xlsx)
        diffs = diff_sections(modified_xlsx, original, validation.meta_data)

        # s0 应有 cell 级 diff，其他应无
        s0_diff = next(d for d in diffs if d.section_id == "s0")
        assert s0_diff.cell_diffs, "s0 应有差异"
        assert any(cd.cell_key == "0:1" for cd in s0_diff.cell_diffs)
        # imported 999, local 100000
        cd = next(cd for cd in s0_diff.cell_diffs if cd.cell_key == "0:1")
        assert cd.imported_value == 999.0
        assert cd.local_value == 100000.0

        # 其他章节应无 diff
        for d in diffs:
            if d.section_id != "s0":
                assert len(d.cell_diffs) == 0

    def test_aes_encrypted_round_trip(self):
        """AES 加密导出 → 解密 → 验证 round-trip 数据无丢失."""
        from app.services.note_offline_export_service import _decrypt_bytes

        sections = [_make_realistic_section(f"s{i}", f"x{i}") for i in range(3)]

        # Export with password
        encrypted_bytes, _ = export_sections_to_xlsx(sections, password="test_password_123")

        # Decrypt
        decrypted_bytes = _decrypt_bytes(encrypted_bytes, "test_password_123")

        # Validate decrypted xlsx
        validation = validate_import_file(decrypted_bytes)
        assert validation.valid is True
        assert len(validation.section_ids) == 3

    def test_import_only_section_detected(self):
        """导入包含本地系统没有的章节 → 标记 IMPORT_ONLY."""
        from app.services.note_offline_import_service import MatchStatus

        # Local has 3 sections
        local = [_make_realistic_section(f"s{i}", f"x{i}") for i in range(3)]

        # Import has 5 sections (s0-s4), 2 are new
        imported = [_make_realistic_section(f"s{i}", f"x{i}") for i in range(5)]
        xlsx_bytes, _ = export_sections_to_xlsx(imported)

        validation = validate_import_file(xlsx_bytes)
        diffs = diff_sections(xlsx_bytes, local, validation.meta_data)

        import_only = [d for d in diffs if d.match_status == MatchStatus.IMPORT_ONLY]
        assert len(import_only) == 2
        assert {d.section_id for d in import_only} == {"s3", "s4"}

    def test_system_only_section_kept(self):
        """系统有但导入包没有的章节 → 标记 SYSTEM_ONLY，本地保留."""
        from app.services.note_offline_import_service import MatchStatus

        # Local has 5 sections
        local = [_make_realistic_section(f"s{i}", f"x{i}") for i in range(5)]

        # Import has only 3 sections (s0-s2)
        imported = [_make_realistic_section(f"s{i}", f"x{i}") for i in range(3)]
        xlsx_bytes, _ = export_sections_to_xlsx(imported)

        validation = validate_import_file(xlsx_bytes)
        diffs = diff_sections(xlsx_bytes, local, validation.meta_data)

        system_only = [d for d in diffs if d.match_status == MatchStatus.SYSTEM_ONLY]
        assert len(system_only) == 2
        assert {d.section_id for d in system_only} == {"s3", "s4"}

    def test_merge_resolution_with_cell_selection(self):
        """章节级冲突 MERGE 选项 + cell-level 勾选."""
        original = [_make_realistic_section("s1", "Test", n_rows=3)]

        modified = [_make_realistic_section("s1", "Test", n_rows=3)]
        # Modify two cells in modified
        modified[0]["table_data"]["rows"][0]["cells"][1] = 999.0
        modified[0]["table_data"]["rows"][1]["cells"][1] = 888.0
        modified_xlsx, _ = export_sections_to_xlsx(modified)

        # Apply MERGE: only import cell 0:1 (not 1:1)
        result = apply_import(
            modified_xlsx,
            original,
            decisions={"s1": ConflictResolution.MERGE},
            merge_cells={"s1": ["0:1"]},
        )
        assert result.success is True
        assert result.sections_imported == 1
        assert result.conflicts == 1
