"""B23 业务层面控制 item_id round-trip 属性测试（Property 1 后端侧）

验证：
- B23 item_id 生成逻辑对全部合法输入组合恒产出非空 `B23-` 前缀键
- 保存→载入 round-trip 等价（纯数据结构层级，无真实 DB）

**Validates: Requirements 10.1, 10.5**
"""
from __future__ import annotations

import re
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# =============================================================================
# B23 cycle codes（与前端 b23CycleConfig.ts B23_CYCLES 对齐）
# =============================================================================

B23_CYCLE_CODES: list[str] = [
    "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8",
    "c9", "c10", "c11", "c12", "c13", "c14", "c15", "cxx5",
]

# =============================================================================
# item_id 类型枚举（与前端 IdType 对齐）
# =============================================================================

ID_TYPES_NO_INDEX = ["applicability", "cycle-conclusion", "conclusion-override", "ctrl-count", "def-count"]
ID_TYPES_WITH_INDEX_AND_FIELD = ["ctrl", "wt", "ct", "def"]
ID_TYPE_SUBPROC = "subproc"

# 控制矩阵字段（与前端 CTRL_FIELDS / CTRL_ENUM_FIELDS 对齐）
CTRL_FIELDS = [
    "subProcess", "ctrlNo", "ctrlName", "ctrlDesc", "affectedItems",
    "assertion", "wcgwRef", "wcgwDetail", "ctrlAttr", "frequency",
    "itApp", "preventDetect", "designEffective", "ctrlTypeL1", "ctrlTypeL2",
    "executor", "executorOrg", "hasDoc", "isKeyControl", "doControlTest",
]

# 穿行测试字段
WT_FIELDS = [
    "method", "interviewee", "procedure", "evidence",
    "result", "asDesigned", "deficiencyFound",
]

# 控制测试字段
CT_FIELDS = [
    "riskJudgment", "testNature", "testTiming", "testScope",
    "operatingEffective", "deviation", "substantiveImpact",
]

# 缺陷字段
DEF_FIELDS = [
    "subProcess", "description", "deficiencyType", "severity", "impact",
]


# =============================================================================
# 纯函数：镜像前端 generateItemId 逻辑（Python 实现）
# =============================================================================

def generate_item_id(
    cycle_code: str,
    id_type: str,
    a: int | None = None,
    b: int | None = None,
    field: str | None = None,
) -> str:
    """Mirror of frontend generateItemId for backend PBT validation."""
    p = f"B23-{cycle_code}"
    if id_type == "applicability":
        return f"{p}-applicability"
    elif id_type == "cycle-conclusion":
        return f"{p}-cycle-conclusion"
    elif id_type == "conclusion-override":
        return f"{p}-conclusion-override"
    elif id_type == "ctrl-count":
        return f"{p}-ctrl-count"
    elif id_type == "ctrl":
        return f"{p}-ctrl-{a}-{field}"
    elif id_type == "wt":
        return f"{p}-wt-{a}-{field}"
    elif id_type == "ct":
        return f"{p}-ct-{a}-{field}"
    elif id_type == "def-count":
        return f"{p}-def-count"
    elif id_type == "def":
        return f"{p}-def-{a}-{field}"
    elif id_type == "subproc":
        return f"{p}-subproc-{a}-name"
    else:
        raise ValueError(f"Unknown id_type: {id_type}")


# =============================================================================
# 模拟持久化存储（dict[item_id, {conclusion, remark}]）
# =============================================================================

class MockStore:
    """Simulates checklist_responses as a dict for round-trip testing."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}

    def save(self, items: list[dict[str, Any]]) -> None:
        """Save items (mirrors PUT checklist-responses)."""
        for item in items:
            item_id = item["item_id"]
            self.data[item_id] = {
                "conclusion": item.get("conclusion"),
                "remark": item.get("remark"),
            }

    def load(self, item_id: str) -> dict[str, Any]:
        """Load a single item (mirrors GET responses_snapshot)."""
        return self.data.get(item_id, {"conclusion": None, "remark": None})


# =============================================================================
# Hypothesis strategies
# =============================================================================

cycle_code_st = st.sampled_from(B23_CYCLE_CODES)
ctrl_index_st = st.integers(min_value=0, max_value=29)
def_index_st = st.integers(min_value=0, max_value=49)
subproc_index_st = st.integers(min_value=1, max_value=20)

# Conclusion values for enum fields (subset of B23 allowed values)
conclusion_values_st = st.sampled_from([
    None, "是", "否", "有效", "无效",
    "存在", "发生", "完整性", "准确性", "计价分摊", "权利义务", "列报",
    "预防性", "检查性",
    "重大缺陷", "重要缺陷", "一般缺陷",
    "缺乏控制", "设计不合理", "未执行",
    "Y", "N",
    "设计有效且已实施", "设计有效但未有效实施", "设计无效", "不适用",
])

# Remark (free text)
remark_st = st.one_of(st.none(), st.text(min_size=0, max_size=50))

# A control point field with its value
ctrl_field_st = st.sampled_from(CTRL_FIELDS)
wt_field_st = st.sampled_from(WT_FIELDS)
ct_field_st = st.sampled_from(CT_FIELDS)
def_field_st = st.sampled_from(DEF_FIELDS)


# =============================================================================
# Property 1: All generated item_ids start with B23- and are non-empty
# =============================================================================

class TestB23ItemIdPrefix:
    """Property 10 (backend side): item_id prefix completeness."""

    @given(code=cycle_code_st)
    @settings(max_examples=5)
    def test_applicability_id_prefix(self, code: str) -> None:
        item_id = generate_item_id(code, "applicability")
        assert item_id, "item_id must be non-empty"
        assert item_id.startswith("B23-"), f"Expected B23- prefix, got: {item_id}"

    @given(code=cycle_code_st)
    @settings(max_examples=5)
    def test_cycle_conclusion_id_prefix(self, code: str) -> None:
        item_id = generate_item_id(code, "cycle-conclusion")
        assert item_id, "item_id must be non-empty"
        assert item_id.startswith("B23-"), f"Expected B23- prefix, got: {item_id}"

    @given(code=cycle_code_st, idx=ctrl_index_st, field=ctrl_field_st)
    @settings(max_examples=5)
    def test_ctrl_field_id_prefix(self, code: str, idx: int, field: str) -> None:
        item_id = generate_item_id(code, "ctrl", a=idx, field=field)
        assert item_id, "item_id must be non-empty"
        assert item_id.startswith("B23-"), f"Expected B23- prefix, got: {item_id}"
        # Verify structure: B23-{code}-ctrl-{index}-{field}
        assert f"-ctrl-{idx}-{field}" in item_id

    @given(code=cycle_code_st, idx=ctrl_index_st, field=wt_field_st)
    @settings(max_examples=5)
    def test_wt_field_id_prefix(self, code: str, idx: int, field: str) -> None:
        item_id = generate_item_id(code, "wt", a=idx, field=field)
        assert item_id, "item_id must be non-empty"
        assert item_id.startswith("B23-"), f"Expected B23- prefix, got: {item_id}"
        assert f"-wt-{idx}-{field}" in item_id

    @given(code=cycle_code_st, idx=ctrl_index_st, field=ct_field_st)
    @settings(max_examples=5)
    def test_ct_field_id_prefix(self, code: str, idx: int, field: str) -> None:
        item_id = generate_item_id(code, "ct", a=idx, field=field)
        assert item_id, "item_id must be non-empty"
        assert item_id.startswith("B23-"), f"Expected B23- prefix, got: {item_id}"
        assert f"-ct-{idx}-{field}" in item_id

    @given(code=cycle_code_st, idx=def_index_st, field=def_field_st)
    @settings(max_examples=5)
    def test_def_field_id_prefix(self, code: str, idx: int, field: str) -> None:
        item_id = generate_item_id(code, "def", a=idx, field=field)
        assert item_id, "item_id must be non-empty"
        assert item_id.startswith("B23-"), f"Expected B23- prefix, got: {item_id}"
        assert f"-def-{idx}-{field}" in item_id

    @given(code=cycle_code_st, idx=subproc_index_st)
    @settings(max_examples=5)
    def test_subproc_id_prefix(self, code: str, idx: int) -> None:
        item_id = generate_item_id(code, "subproc", a=idx)
        assert item_id, "item_id must be non-empty"
        assert item_id.startswith("B23-"), f"Expected B23- prefix, got: {item_id}"
        assert f"-subproc-{idx}-name" in item_id

    @given(code=cycle_code_st)
    @settings(max_examples=5)
    def test_all_no_index_types_prefix(self, code: str) -> None:
        """All simple types (no index) produce valid B23- prefixed IDs."""
        for id_type in ID_TYPES_NO_INDEX:
            item_id = generate_item_id(code, id_type)
            assert item_id, f"item_id for {id_type} must be non-empty"
            assert item_id.startswith("B23-"), f"{id_type}: Expected B23- prefix, got: {item_id}"


# =============================================================================
# Property 1 (backend side): Round-trip — save then load produces equivalent data
# =============================================================================

class TestB23RoundTrip:
    """Property 1 (backend side): Persistence round-trip invariant."""

    @given(
        code=cycle_code_st,
        applicable=st.booleans(),
    )
    @settings(max_examples=5)
    def test_applicability_roundtrip(self, code: str, applicable: bool) -> None:
        """Saving applicability and reloading yields the same value."""
        store = MockStore()
        item_id = generate_item_id(code, "applicability")
        conclusion = "Y" if applicable else "N"

        store.save([{"item_id": item_id, "conclusion": conclusion, "remark": None}])
        loaded = store.load(item_id)

        assert loaded["conclusion"] == conclusion
        # Verify derived applicability matches
        loaded_applicable = loaded["conclusion"] != "N"
        assert loaded_applicable == applicable

    @given(
        code=cycle_code_st,
        idx=ctrl_index_st,
        field=ctrl_field_st,
        conclusion=conclusion_values_st,
        remark=remark_st,
    )
    @settings(max_examples=5)
    def test_ctrl_field_roundtrip(
        self, code: str, idx: int, field: str, conclusion: str | None, remark: str | None,
    ) -> None:
        """Saving a control point field and reloading yields the same value."""
        store = MockStore()
        item_id = generate_item_id(code, "ctrl", a=idx, field=field)

        store.save([{"item_id": item_id, "conclusion": conclusion, "remark": remark}])
        loaded = store.load(item_id)

        assert loaded["conclusion"] == conclusion
        assert loaded["remark"] == remark

    @given(
        code=cycle_code_st,
        idx=ctrl_index_st,
        field=wt_field_st,
        conclusion=conclusion_values_st,
        remark=remark_st,
    )
    @settings(max_examples=5)
    def test_wt_field_roundtrip(
        self, code: str, idx: int, field: str, conclusion: str | None, remark: str | None,
    ) -> None:
        """Saving a walkthrough test field and reloading yields the same value."""
        store = MockStore()
        item_id = generate_item_id(code, "wt", a=idx, field=field)

        store.save([{"item_id": item_id, "conclusion": conclusion, "remark": remark}])
        loaded = store.load(item_id)

        assert loaded["conclusion"] == conclusion
        assert loaded["remark"] == remark

    @given(
        code=cycle_code_st,
        idx=ctrl_index_st,
        field=ct_field_st,
        conclusion=conclusion_values_st,
        remark=remark_st,
    )
    @settings(max_examples=5)
    def test_ct_field_roundtrip(
        self, code: str, idx: int, field: str, conclusion: str | None, remark: str | None,
    ) -> None:
        """Saving a control test field and reloading yields the same value."""
        store = MockStore()
        item_id = generate_item_id(code, "ct", a=idx, field=field)

        store.save([{"item_id": item_id, "conclusion": conclusion, "remark": remark}])
        loaded = store.load(item_id)

        assert loaded["conclusion"] == conclusion
        assert loaded["remark"] == remark

    @given(
        code=cycle_code_st,
        idx=def_index_st,
        field=def_field_st,
        conclusion=conclusion_values_st,
        remark=remark_st,
    )
    @settings(max_examples=5)
    def test_def_field_roundtrip(
        self, code: str, idx: int, field: str, conclusion: str | None, remark: str | None,
    ) -> None:
        """Saving a deficiency field and reloading yields the same value."""
        store = MockStore()
        item_id = generate_item_id(code, "def", a=idx, field=field)

        store.save([{"item_id": item_id, "conclusion": conclusion, "remark": remark}])
        loaded = store.load(item_id)

        assert loaded["conclusion"] == conclusion
        assert loaded["remark"] == remark

    @given(
        code=cycle_code_st,
        idx=subproc_index_st,
        remark=st.text(min_size=1, max_size=30),
    )
    @settings(max_examples=5)
    def test_subproc_roundtrip(self, code: str, idx: int, remark: str) -> None:
        """Saving a sub-process name and reloading yields the same value."""
        store = MockStore()
        item_id = generate_item_id(code, "subproc", a=idx)

        store.save([{"item_id": item_id, "conclusion": None, "remark": remark}])
        loaded = store.load(item_id)

        assert loaded["conclusion"] is None
        assert loaded["remark"] == remark

    @given(code=cycle_code_st)
    @settings(max_examples=5)
    def test_wt_ct_namespace_separation(self, code: str) -> None:
        """Writing wt fields does not overwrite ct fields (namespace separation)."""
        store = MockStore()
        idx = 0

        # Write wt field
        wt_id = generate_item_id(code, "wt", a=idx, field="asDesigned")
        store.save([{"item_id": wt_id, "conclusion": "是", "remark": None}])

        # Write ct field for same index
        ct_id = generate_item_id(code, "ct", a=idx, field="operatingEffective")
        store.save([{"item_id": ct_id, "conclusion": "有效", "remark": None}])

        # Both retain their values — no collision
        assert store.load(wt_id)["conclusion"] == "是"
        assert store.load(ct_id)["conclusion"] == "有效"
        # IDs are distinct
        assert wt_id != ct_id


# =============================================================================
# Property: item_id uniqueness across types for same cycle+index
# =============================================================================

class TestB23ItemIdUniqueness:
    """All generated item_ids for a given cycle are unique across types."""

    @given(code=cycle_code_st, idx=ctrl_index_st)
    @settings(max_examples=5)
    def test_all_types_for_index_produce_unique_ids(self, code: str, idx: int) -> None:
        """ctrl/wt/ct/def item_ids for the same cycle+index never collide."""
        ids = set()
        for field in CTRL_FIELDS[:3]:
            ids.add(generate_item_id(code, "ctrl", a=idx, field=field))
        for field in WT_FIELDS[:3]:
            ids.add(generate_item_id(code, "wt", a=idx, field=field))
        for field in CT_FIELDS[:3]:
            ids.add(generate_item_id(code, "ct", a=idx, field=field))
        for field in DEF_FIELDS[:3]:
            ids.add(generate_item_id(code, "def", a=idx, field=field))
        # All must be distinct (3*4 = 12 distinct IDs)
        assert len(ids) == 12

    @given(code=cycle_code_st)
    @settings(max_examples=5)
    def test_no_index_types_produce_unique_ids(self, code: str) -> None:
        """All no-index type item_ids for a cycle are unique."""
        ids = [generate_item_id(code, t) for t in ID_TYPES_NO_INDEX]
        assert len(ids) == len(set(ids))


# =============================================================================
# Property: item_id format regex validation
# =============================================================================

class TestB23ItemIdFormat:
    """item_id format matches the documented B23-{cycleCode}-{type}-... pattern."""

    B23_ID_PATTERN = re.compile(
        r"^B23-(c\d{1,2}|cxx5)-"
        r"(applicability|cycle-conclusion|conclusion-override|ctrl-count|def-count"
        r"|ctrl-\d+-\w+"
        r"|wt-\d+-\w+"
        r"|ct-\d+-\w+"
        r"|def-\d+-\w+"
        r"|subproc-\d+-name)$"
    )

    @given(
        code=cycle_code_st,
        id_type=st.sampled_from(ID_TYPES_NO_INDEX),
    )
    @settings(max_examples=5)
    def test_no_index_format(self, code: str, id_type: str) -> None:
        item_id = generate_item_id(code, id_type)
        assert self.B23_ID_PATTERN.match(item_id), f"Format mismatch: {item_id}"

    @given(
        code=cycle_code_st,
        idx=ctrl_index_st,
        field=ctrl_field_st,
    )
    @settings(max_examples=5)
    def test_ctrl_format(self, code: str, idx: int, field: str) -> None:
        item_id = generate_item_id(code, "ctrl", a=idx, field=field)
        assert self.B23_ID_PATTERN.match(item_id), f"Format mismatch: {item_id}"

    @given(
        code=cycle_code_st,
        idx=ctrl_index_st,
        field=wt_field_st,
    )
    @settings(max_examples=5)
    def test_wt_format(self, code: str, idx: int, field: str) -> None:
        item_id = generate_item_id(code, "wt", a=idx, field=field)
        assert self.B23_ID_PATTERN.match(item_id), f"Format mismatch: {item_id}"

    @given(
        code=cycle_code_st,
        idx=ctrl_index_st,
        field=ct_field_st,
    )
    @settings(max_examples=5)
    def test_ct_format(self, code: str, idx: int, field: str) -> None:
        item_id = generate_item_id(code, "ct", a=idx, field=field)
        assert self.B23_ID_PATTERN.match(item_id), f"Format mismatch: {item_id}"

    @given(
        code=cycle_code_st,
        idx=def_index_st,
        field=def_field_st,
    )
    @settings(max_examples=5)
    def test_def_format(self, code: str, idx: int, field: str) -> None:
        item_id = generate_item_id(code, "def", a=idx, field=field)
        assert self.B23_ID_PATTERN.match(item_id), f"Format mismatch: {item_id}"
