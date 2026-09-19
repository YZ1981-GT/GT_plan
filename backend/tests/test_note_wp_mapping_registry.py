"""附注-底稿映射从权威 registry 派生（修早期 DEFAULT_WP_MAPPING 编号错乱）。

背景：note_wp_mapping_service.DEFAULT_WP_MAPPING 早期硬编码错乱
（五、2→E2[不存在]、五、3→D1[应收账款实为 D2/五、5]、五、9→H1[固定资产实为 五、22]），
被 note_validation_executors（完整性）/ note_stale_service（stale）/ disclosure_notes
（schema 反查）三处直接消费 → 校验/标记/取数按错误映射进行。改为从
backend/data/note_workpaper_sync_registry.json 派生 section→wp_code（listed+soe）。
"""
from __future__ import annotations

import pathlib

from app.services.note_wp_mapping_service import (
    DEFAULT_WP_MAPPING,
    _LEGACY_DEFAULT_WP_MAPPING,
    _build_default_wp_mapping,
)


class TestDefaultWpMappingFromRegistry:
    def test_authoritative_listed_entries(self):
        """权威 listed 编号正确（对照 registry）。"""
        assert DEFAULT_WP_MAPPING.get("五、4") == "D1"  # 应收票据
        assert DEFAULT_WP_MAPPING.get("五、5") == "D2"  # 应收账款
        assert DEFAULT_WP_MAPPING.get("五、1") == "E1"  # 货币资金

    def test_soe_dual_numbering_covered(self):
        """soe（八、N）编号也纳入（listed+soe 双编号）。"""
        assert DEFAULT_WP_MAPPING.get("八、4") == "D1"
        assert DEFAULT_WP_MAPPING.get("八、5") == "D2"

    def test_legacy_erroneous_entries_gone(self):
        """旧错乱条目不再存在（五、2→E2、五、3→D1）。"""
        # 五、2 要么不在映射（registry 无该 section），要么绝不再是错误的 "E2"
        assert DEFAULT_WP_MAPPING.get("五、2") != "E2"
        # 应收账款权威是 D2/五、5，绝非旧的 五、3→D1
        assert DEFAULT_WP_MAPPING.get("五、3") != "D1"

    def test_richer_than_legacy(self):
        """派生映射覆盖面显著大于旧 10 条硬编码。"""
        assert len(DEFAULT_WP_MAPPING) > len(_LEGACY_DEFAULT_WP_MAPPING)
        assert len(DEFAULT_WP_MAPPING) >= 20

    def test_all_values_are_wp_codes(self):
        """所有值为形如 ``[A-Z]+\\d+`` 的底稿编号（供 startswith 前缀匹配）。"""
        import re

        for sec, code in DEFAULT_WP_MAPPING.items():
            assert isinstance(sec, str) and sec.strip()
            assert re.match(r"^[A-Z]+\d", code), f"{sec}->{code} 非底稿编号形态"

    def test_idempotent(self):
        """重复构建结果一致（幂等）。"""
        a = _build_default_wp_mapping()
        b = _build_default_wp_mapping()
        assert a == b

    def test_fail_open_falls_back_to_legacy(self, monkeypatch):
        """registry 读取失败 → fail-open 回退旧硬编码，不抛、非空。"""
        def _boom(self, *a, **k):  # noqa: ANN001
            raise OSError("registry unavailable")

        monkeypatch.setattr(pathlib.Path, "read_text", _boom)
        result = _build_default_wp_mapping()
        assert result == _LEGACY_DEFAULT_WP_MAPPING
        assert len(result) > 0
