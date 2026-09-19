"""D 循环账龄空骨架（配置驱动，不塞首段）守卫 —— Phase 2 / Task 12.

spec: .kiro/specs/four-table-extraction-entry-completion/  (Task 12, Requirements 2.5, 7.1, 7.2, 7.3)
Properties: 5（无账龄来源不伪造：sum(agingAudited)==0，不整额落首段）
            8（账龄骨架与枚举联动：骨架键集逐项 == get_effective_segments 返回）

审计结论（本文件的前提事实，见 evidence/task12-d-cycle-aging-skeleton-audit.md）：
  * D3/D7 明细行账龄为 **nested keyed**（agingPrior/agingAudited，2-period），
    前端 useD3Detail/useD7Detail 经 useAgingConfig 配置驱动 → 后端骨架也应 nested keyed
    且段键来自 get_effective_segments。本文件断言的正是这两家端点**行为**。
  * D5 明细表（D5-2 应收款项融资）源模板无账龄列 → 不生成账龄骨架（N/A）。
  * D6 明细行账龄为 **flat legacy keys**（agePrior1y/ageEnd1y），前端 useD6Detail 未接
    useAgingConfig → 配置驱动骨架同步 deferred；仅保证不塞首段（builder 不写 aging 键，
    前端默认 0）。见 test_d6_detail_aggregation.py 的 test_build_rows_only_record_columns。

🔴 断言的是**行为**（端点真 emit 的行结构 / 骨架键集），不是"函数存在"。
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.services.aging_config_service import (
    PRESET_SEGMENTS,
    AgingPreset,
    resolve_segments,
)
from app.services.d_cycle_extraction.d_aux_import import (
    build_two_period_aging_skeleton,
    _empty_aging,
    _segment_keys,
)
from app.services.four_table.aux_aggregation import AuxEntry


def _run(coro):
    return asyncio.run(coro)


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数：build_two_period_aging_skeleton / _empty_aging / _segment_keys
# ─────────────────────────────────────────────────────────────────────────────


def test_skeleton_only_two_groups_no_current():
    """2-period 科目只生成 agingPrior/agingAudited 两组，**不含** agingCurrent（Requirement 7.2）."""
    segs = PRESET_SEGMENTS[AgingPreset.THREE_YEAR]
    skel = build_two_period_aging_skeleton(segs)
    assert set(skel.keys()) == {"agingPrior", "agingAudited"}
    assert "agingCurrent" not in skel


def test_skeleton_keys_equal_segments_in_order():
    """骨架每组键集逐项等于 segments 的 key（顺序一致，Property 8）."""
    segs = PRESET_SEGMENTS[AgingPreset.THREE_YEAR]
    expected_keys = [s.key for s in segs]
    skel = build_two_period_aging_skeleton(segs)
    assert list(skel["agingPrior"].keys()) == expected_keys
    assert list(skel["agingAudited"].keys()) == expected_keys


def test_skeleton_all_zero_never_stuffs_first_segment():
    """每段值=0，sum(agingAudited)==0，不存在整额落首段（Property 5，红基线④）."""
    segs = PRESET_SEGMENTS[AgingPreset.FIVE_YEAR]
    skel = build_two_period_aging_skeleton(segs)
    assert sum(skel["agingPrior"].values()) == 0.0
    assert sum(skel["agingAudited"].values()) == 0.0
    # 首段绝不带余额（红基线④伪造账龄分布）
    first_key = segs[0].key
    assert skel["agingPrior"][first_key] == 0.0
    assert skel["agingAudited"][first_key] == 0.0


def test_skeleton_key_count_follows_preset():
    """三年段=4 键、五年段=6 键（随枚举变化，Property 8）."""
    three = build_two_period_aging_skeleton(PRESET_SEGMENTS[AgingPreset.THREE_YEAR])
    five = build_two_period_aging_skeleton(PRESET_SEGMENTS[AgingPreset.FIVE_YEAR])
    assert len(three["agingAudited"]) == 4
    assert len(five["agingAudited"]) == 6


def test_segment_keys_accepts_objects_dicts_strings():
    """_segment_keys 兼容段对象/字典/字符串，去重保序."""
    assert _segment_keys(PRESET_SEGMENTS[AgingPreset.THREE_YEAR]) == [
        "within1", "y1to2", "y2to3", "over3",
    ]
    assert _segment_keys([{"key": "a"}, {"key": "b"}, {"key": "a"}]) == ["a", "b"]
    assert _segment_keys(["x", "y", "x"]) == ["x", "y"]


def test_empty_aging_all_zero():
    """_empty_aging 每段值=0."""
    bucket = _empty_aging(["within1", "y1to2"])
    assert bucket == {"within1": 0.0, "y1to2": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# 端点行为：D3/D7 端点 emit 的行携带配置驱动的空账龄骨架
# ─────────────────────────────────────────────────────────────────────────────


class _RowsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _EndpointSession:
    """驱动生产 D3/D7 端点的假会话（不查真库、不解析报表映射）.

    resolve_d_cycle_segments 会尝试 get_effective_segments(UUID(project_id), ...)；
    这里 project_id 非法 UUID → 内部抛异常被 try/except 捕获 → 走 DEFAULT_SUBJECT_PRESETS
    兜底（D3/D7 = THREE_YEAR，4 段），正是我们期望的"配置读取失败按 subject 默认 preset
    兜底、不回退单段"路径（Requirement 7.6）。
    """

    def __init__(self, existing_rows: list[dict]):
        self._existing_remark = json.dumps(existing_rows, ensure_ascii=False)
        self.captured_remark: str | None = None

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "audit_year" in sql:
            return _RowsResult([SimpleNamespace(project_id="proj-1", audit_year=2025)])
        if "SELECT remark" in sql:
            return _RowsResult([SimpleNamespace(remark=self._existing_remark)])
        if "INSERT INTO checklist_responses" in sql:
            self.captured_remark = (params or {}).get("remark")
            return _RowsResult([])
        return _RowsResult([])

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _drive_endpoint(module, endpoint_name, incoming_names, monkeypatch, wp_code):
    import app.services.d_cycle_extraction.d_aux_import as dai

    async def _fake_agg(db, project_id, year, code):
        entries = [AuxEntry(nm, 100.0, 0.0, 0.0, 100.0) for nm in incoming_names]
        return dai.DAuxImportResult(entries, "客户", "ok", ["2203"], "BS-046", "report_config")

    monkeypatch.setattr(dai, "aggregate_d_cycle_aux", _fake_agg, raising=True)

    session = _EndpointSession([])
    endpoint = getattr(module, endpoint_name)
    _run(endpoint("wp-1", db=session, current_user=object()))
    assert session.captured_remark is not None, "端点未写入 remark"
    return json.loads(session.captured_remark)


# 兜底段（配置读取失败 → THREE_YEAR）的键集
_FALLBACK_KEYS = [s.key for s in resolve_segments(AgingPreset.THREE_YEAR, None)]


def test_d3_endpoint_row_carries_empty_skeleton(monkeypatch):
    """D3 端点 emit 的行带 nested keyed 空骨架，键集 == 段键，值全 0（Property 5/8）."""
    import app.routers.wp_render_strategies._d3_import_export as d3mod

    rows = _drive_endpoint(d3mod, "d3_import_aux_balance", ["甲公司"], monkeypatch, "D3")
    row = next(r for r in rows if r["customerName"] == "甲公司")
    assert set(row.keys()) >= {"agingPrior", "agingAudited"}
    assert "agingCurrent" not in row
    assert list(row["agingPrior"].keys()) == _FALLBACK_KEYS
    assert list(row["agingAudited"].keys()) == _FALLBACK_KEYS
    assert sum(row["agingPrior"].values()) == 0.0
    assert sum(row["agingAudited"].values()) == 0.0


def test_d7_endpoint_row_carries_empty_skeleton(monkeypatch):
    """D7 端点 emit 的行带 nested keyed 空骨架，键集 == 段键，值全 0（Property 5/8）."""
    import app.routers.wp_render_strategies._d7_import_export as d7mod

    rows = _drive_endpoint(d7mod, "d7_import_aux_balance", ["某单位"], monkeypatch, "D7")
    row = next(r for r in rows if r["companyName"] == "某单位")
    assert set(row.keys()) >= {"agingPrior", "agingAudited"}
    assert "agingCurrent" not in row
    assert list(row["agingPrior"].keys()) == _FALLBACK_KEYS
    assert list(row["agingAudited"].keys()) == _FALLBACK_KEYS
    assert sum(row["agingPrior"].values()) == 0.0
    assert sum(row["agingAudited"].values()) == 0.0
