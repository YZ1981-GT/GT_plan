"""
test_export_meta_marker.py

data_exchange 导出的 `_GT_EXPORT_META` 标记
（spec platform-global-display-settings-closure 任务 10 / AC-21）。

判据（design §6.3）：
1. marker 只用于 `data_exchange`（formal 用它就是误用）。
2. 必须含六个键且 `schema_version` 固定。
3. 必须有一句对用户可见的中文说明。
4. canonical JSON 幂等（同输入逐字节相同）。
5. `source_unit` 闭集（yuan/qian/wan）。
6. 反例：已按万元折算的等比例数据必须被 `assert_raw_yuan` 抓出。
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.services.export_meta_marker import (
    DATA_EXCHANGE_NOTE,
    MARKER_KEY,
    MARKER_SCHEMA_VERSION,
    DataExchangeMetaError,
    ExportMeta,
    assert_raw_yuan,
    marker_rows,
    parse_marker,
)

_REQUIRED_KEYS = {
    "schema_version", "surface_id", "classification",
    "source_unit", "generated_at", "note",
}


# ── 1. 只用于 data_exchange ──────────────────────────────

class TestClassificationGuard:
    def test_rejects_formal(self) -> None:
        with pytest.raises(DataExchangeMetaError, match="只用于 data_exchange"):
            ExportMeta(surface_id="x", classification="formal")

    def test_rejects_template(self) -> None:
        with pytest.raises(DataExchangeMetaError):
            ExportMeta(surface_id="x", classification="template")

    def test_accepts_data_exchange(self) -> None:
        meta = ExportMeta(surface_id="consol_trial_local_export", classification="data_exchange")
        assert meta.classification == "data_exchange"


# ── 2. 六个键 + schema_version ───────────────────────────

class TestJsonShape:
    def _meta(self, **kw) -> ExportMeta:
        base = dict(
            surface_id="consol_trial_local_export",
            classification="data_exchange",
            generated_at="2026-11-16T00:00:00+00:00",
        )
        base.update(kw)
        return ExportMeta(**base)

    def test_has_all_six_keys(self) -> None:
        data = json.loads(self._meta().to_json())
        assert set(data) == _REQUIRED_KEYS

    def test_schema_version_pinned(self) -> None:
        data = json.loads(self._meta().to_json())
        assert data["schema_version"] == MARKER_SCHEMA_VERSION == 1

    def test_default_source_unit_is_yuan(self) -> None:
        data = json.loads(self._meta().to_json())
        assert data["source_unit"] == "yuan"

    def test_note_is_chinese_and_mentions_raw(self) -> None:
        meta = self._meta()
        assert DATA_EXCHANGE_NOTE in meta.to_json()
        assert "原始元值" in DATA_EXCHANGE_NOTE
        assert "数据交换" in DATA_EXCHANGE_NOTE
        assert "不作为正式交付件" in DATA_EXCHANGE_NOTE


# ── 3. canonical JSON 幂等 ───────────────────────────────

class TestCanonicalJson:
    def _meta(self) -> ExportMeta:
        return ExportMeta(
            surface_id="s1", classification="data_exchange",
            generated_at="2026-11-16T00:00:00+00:00",
        )

    def test_idempotent(self) -> None:
        a = self._meta().to_json()
        b = self._meta().to_json()
        assert a == b

    def test_keys_sorted_and_compact(self) -> None:
        out = self._meta().to_json()
        assert " " not in out, "canonical JSON 不应含空格"
        # 键排序：classification 在 generated_at 之前
        assert out.index('"classification"') < out.index('"generated_at"')


# ── 4. source_unit 闭集 ──────────────────────────────────

class TestSourceUnit:
    @pytest.mark.parametrize("unit", ["yuan", "qian", "wan"])
    def test_allowed(self, unit: str) -> None:
        ExportMeta(surface_id="s", classification="data_exchange", source_unit=unit)

    def test_rejects_bogus(self) -> None:
        with pytest.raises(DataExchangeMetaError, match="非法 source_unit"):
            ExportMeta(surface_id="s", classification="data_exchange", source_unit="bogus")

    def test_rejects_empty_surface_id(self) -> None:
        with pytest.raises(DataExchangeMetaError, match="surface_id 不能为空"):
            ExportMeta(surface_id="", classification="data_exchange")


# ── 5. 三行布局 ──────────────────────────────────────────

class TestMarkerRows:
    def test_three_rows_layout(self) -> None:
        meta = ExportMeta(
            surface_id="s", classification="data_exchange",
            generated_at="2026-11-16T00:00:00+00:00",
        )
        rows = marker_rows(meta)
        assert len(rows) == 3
        assert rows[0] == [DATA_EXCHANGE_NOTE]
        assert rows[1][0] == MARKER_KEY
        assert rows[2] == []

    def test_marker_row_parsable(self) -> None:
        meta = ExportMeta(
            surface_id="s", classification="data_exchange",
            generated_at="2026-11-16T00:00:00+00:00",
        )
        rows = marker_rows(meta)
        parsed = parse_marker(rows[1][1])
        assert parsed["surface_id"] == "s"
        assert parsed["schema_version"] == 1


# ── 6. parse_marker 的反向校验 ───────────────────────────

class TestParseMarker:
    def test_rejects_bad_json(self) -> None:
        with pytest.raises(DataExchangeMetaError, match="不是合法 JSON"):
            parse_marker("{not json")

    def test_rejects_non_object(self) -> None:
        with pytest.raises(DataExchangeMetaError, match="必须是 JSON 对象"):
            parse_marker("[1,2]")

    def test_rejects_wrong_classification(self) -> None:
        with pytest.raises(DataExchangeMetaError, match="必须是 data_exchange"):
            parse_marker(json.dumps({"schema_version": 1, "classification": "formal"}))

    def test_rejects_wrong_schema_version(self) -> None:
        with pytest.raises(DataExchangeMetaError, match="schema_version"):
            parse_marker(json.dumps({"schema_version": 99, "classification": "data_exchange"}))


# ── 7. 原始元值启发式防线 ────────────────────────────────

class TestRawYuanGuard:
    def test_normal_values_pass(self) -> None:
        assert_raw_yuan([Decimal("1234.56"), Decimal("0"), None])  # 不抛

    def test_all_multiples_of_10000_rejected(self) -> None:
        """全部能被 10000 整除 ⇒ 疑似已折成万元 ⇒ 必须报。"""
        with pytest.raises(DataExchangeMetaError, match="疑似已按万元折算"):
            assert_raw_yuan([Decimal("10000"), Decimal("20000")])

    def test_zero_only_passes(self) -> None:
        """全 0 不报（0 也是 10000 的倍数，但没有「折算」证据）。"""
        assert_raw_yuan([0, 0, 0])

    def test_empty_passes(self) -> None:
        assert_raw_yuan([])

    def test_mixed_values_pass(self) -> None:
        assert_raw_yuan([Decimal("10000"), Decimal("1234.56")])
