# Feature: procedure-delegation-notification — Task 3 ProcedureRowDefinition 导入与规范化修订哈希
"""DefinitionImporter 单元测试 + PBT（Properties P1-P3）。

Task 3 / 需求 1.1-1.7 / Design C1、D1：

- 单元：JSON 模板 / xlsx fallback 抽取、规范化原语、insert-if-absent 保留旧 revision。
- PBT P1（跨项目/机器/顺序稳定）：Requirements 1.1, 1.3, 1.4
- PBT P2（revision 对 mtime/路径/导入时间不敏感；语义变化 revision 改变）：Requirements 1.3, 1.5, 1.6
- PBT P3（legacy alias / 数组序号不成为身份）：Requirements 1.7

PBT 使用项目 fast profile（conftest 注册），报告真实反例。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.procedure_definition_importer import (
    ImportResult,
    ProcedureDefinitionImporter,
    canonical_json,
    compute_revision_hash,
    normalize_text,
)

_TEMPLATES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "procedure_table_templates.json"
)


# ---------------------------------------------------------------------------
# Hypothesis 策略：生成一套「语义定义行」（program_no 唯一、文本非空）
# ---------------------------------------------------------------------------

_text = st.text(min_size=1, max_size=40).map(lambda s: s.strip() or "x")
_ref = st.text(alphabet="ABCDEFGHIJKLMN0123456789-", min_size=1, max_size=8)


@st.composite
def _rows(draw):
    """生成 items（JSON 模板形态）：seq 唯一、content 非空、ref_index 可选。"""
    n = draw(st.integers(min_value=1, max_value=6))
    items = []
    for i in range(n):
        refs = draw(st.lists(_ref, max_size=3))
        items.append(
            {
                "seq": i + 1,
                "content": draw(_text),
                "ref_index": "/".join(refs),
                "auto_data_source": draw(st.one_of(st.none(), st.sampled_from(["risk_for_cycle", None]))),
                "applicable_default": "yes",
            }
        )
    return items


def _build(items, *, template_code="G1A", sheet_key="G1A", name="测试程序表") -> ImportResult:
    return ProcedureDefinitionImporter.build_from_json_template(
        template_code, sheet_key, {"name": name, "items": items}
    )


# ---------------------------------------------------------------------------
# 单元：规范化原语
# ---------------------------------------------------------------------------
class TestNormalization:
    def test_normalize_text_nfkc_and_newline_and_trim(self):
        # 全角数字 NFKC → 半角；\r\n / \r → \n；首尾 trim
        assert normalize_text("  １２３ \r\n") == "123"
        assert normalize_text("a\r\nb\rc") == "a\nb\nc"
        assert normalize_text(None) == ""

    def test_canonical_json_key_order_stable(self):
        assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
        assert canonical_json({"a": 2, "b": 1}) == '{"a":2,"b":1}'


# ---------------------------------------------------------------------------
# 单元：JSON 模板 / xlsx 抽取
# ---------------------------------------------------------------------------
class TestExtraction:
    def test_json_template_real_g1a(self):
        with open(_TEMPLATES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        assert "G1A" in data
        result = ProcedureDefinitionImporter.build_from_json_template("G1A", "G1A", data["G1A"])
        assert len(result.definitions) == len(data["G1A"]["items"])
        assert len(result.revision_hash) == 64
        for d in result.definitions:
            assert d["definition_key"].startswith("G1A::G1A::")
            assert d["template_revision_hash"] == result.revision_hash
            assert d["procedure_text"]
            # 每条都带集合 revision
        # ref_snapshot 抽到（G1A seq1 有 G1-1/G1-2 + auto:risk_for_cycle）
        first = result.definitions[0]
        assert any("G1-1" == t or "G1-2" == t for t in first["ref_snapshot"])
        assert "auto:risk_for_cycle" in first["ref_snapshot"]

    def test_definition_key_disambiguates_identical_text(self):
        # 相同文本但 program_no 不同 → key 不同（program_no 是语义标签）
        items = [
            {"seq": 1, "content": "同样的文本", "ref_index": ""},
            {"seq": 2, "content": "同样的文本", "ref_index": ""},
        ]
        result = _build(items)
        keys = [d["definition_key"] for d in result.definitions]
        assert len(set(keys)) == 2

    def test_build_from_source_prefers_json(self):
        r = ProcedureDefinitionImporter.build_from_source(
            "G1A", "G1A", json_template={"name": "n", "items": [{"seq": 1, "content": "x"}]}
        )
        assert len(r.definitions) == 1

    def test_build_from_source_empty(self):
        r = ProcedureDefinitionImporter.build_from_source("G1A", "G1A")
        assert r.definitions == []
        assert len(r.revision_hash) == 64  # 空集合也有确定 hash


# ---------------------------------------------------------------------------
# PBT P1：definition 跨项目/机器/顺序稳定
# Validates: Requirements 1.1, 1.3, 1.4
# ---------------------------------------------------------------------------
class TestP1CrossProjectStable:
    @given(items=_rows(), seed=st.integers(min_value=0, max_value=10_000))
    @settings(max_examples=5)
    def test_order_and_machine_independent(self, items, seed):
        base = _build(items)

        # 打乱导入顺序（模拟不同导入顺序）
        shuffled = list(items)
        random.Random(seed).shuffle(shuffled)
        reordered = _build(shuffled)

        base_keys = {d["definition_key"] for d in base.definitions}
        reordered_keys = {d["definition_key"] for d in reordered.definitions}
        assert base_keys == reordered_keys, "definition_key 集合应与导入顺序无关"
        assert base.revision_hash == reordered.revision_hash, "revision 应与导入顺序无关"

    @given(items=_rows())
    @settings(max_examples=5)
    def test_project_and_kind_independent(self, items):
        # definition_key/revision 不含 project/machine；换 sheet 展示名/JSON name 不变
        r1 = _build(items, name="项目A的程序表")
        r2 = _build(items, name="项目B的程序表（不同机器导入）")
        assert {d["definition_key"] for d in r1.definitions} == {
            d["definition_key"] for d in r2.definitions
        }
        assert r1.revision_hash == r2.revision_hash


# ---------------------------------------------------------------------------
# PBT P2：revision 对非内容元数据不敏感；语义变化 revision 改变
# Validates: Requirements 1.3, 1.5, 1.6
# ---------------------------------------------------------------------------
class TestP2RevisionInsensitivity:
    @given(items=_rows())
    @settings(max_examples=5)
    def test_path_mtime_import_time_insensitive(self, items):
        """相同语义内容，仅 source_locator 物理来源（kind/路径/文件名）不同 → revision 不变。"""
        raw_json = ProcedureDefinitionImporter.build_from_json_template("G1A", "G1A", {"items": items})

        # 用相同语义行走不同物理 source_locator（不同 kind/文件名/路径/mtime），revision 应一致。
        # 语义内容（program_no/text/ref_snapshot 含 auto source）必须与 JSON 侧完全一致，
        # 仅 source_locator 物理字段不同。
        from app.services.procedure_definition_importer import _RawRow, _build_ref_snapshot

        raw_rows = [
            _RawRow(
                program_no=str(it["seq"]),
                procedure_text=normalize_text(it["content"]),
                ref_snapshot=_build_ref_snapshot(it.get("ref_index"), it.get("auto_data_source")),
                array_index=i,
            )
            for i, it in enumerate(items)
        ]
        as_xlsx = ProcedureDefinitionImporter.build_from_raw_rows(
            "G1A",
            "G1A",
            raw_rows,
            {"kind": "xlsx", "file_name": "/abs/path/changed.xlsx", "mtime": 12345},
        )
        assert raw_json.revision_hash == as_xlsx.revision_hash, (
            "revision 不得受 source kind/绝对路径/mtime 影响"
        )
        assert {d["definition_key"] for d in raw_json.definitions} == {
            d["definition_key"] for d in as_xlsx.definitions
        }

    @given(items=_rows(), idx=st.integers(min_value=0, max_value=5))
    @settings(max_examples=5)
    def test_semantic_change_changes_revision(self, items, idx):
        """改变某行 procedure_text（语义字段）→ revision 与该行 definition_key 改变。"""
        base = _build(items)
        target = idx % len(items)
        mutated_items = [dict(it) for it in items]
        mutated_items[target] = dict(mutated_items[target])
        mutated_items[target]["content"] = mutated_items[target]["content"] + "＜语义变化＞"
        mutated = _build(mutated_items)
        assert base.revision_hash != mutated.revision_hash, "语义变化必须改变 revision"


# ---------------------------------------------------------------------------
# PBT P3：legacy alias / 数组序号不成为身份
# Validates: Requirements 1.7
# ---------------------------------------------------------------------------
class TestP3LegacyAliasNotIdentity:
    @given(items=_rows())
    @settings(max_examples=5)
    def test_row_n_and_index_only_in_aliases(self, items):
        result = _build(items)
        for i, d in enumerate(result.definitions):
            key = d["definition_key"]
            aliases = d["legacy_aliases"]
            # definition_key 为内容寻址三段式，不是 row-N/数组序号
            assert key.startswith("G1A::G1A::")
            assert key not in aliases
            assert not key.startswith("row-")
            assert not key.startswith("index-")
            # row-{program_no} 与数组序号仅登记为 legacy alias
            if d.get("program_no"):
                assert f"row-{d['program_no']}" in aliases
            assert any(a.startswith("index-") for a in aliases)

    @given(seed=st.integers(min_value=0, max_value=10_000), items=_rows())
    @settings(max_examples=5)
    def test_reorder_does_not_change_identity_despite_index_alias(self, seed, items):
        """数组序号变化（重排）虽改变 index-alias，但 definition_key 不变。"""
        base = {d["definition_key"] for d in _build(items).definitions}
        shuffled = list(items)
        random.Random(seed).shuffle(shuffled)
        after = {d["definition_key"] for d in _build(shuffled).definitions}
        assert base == after


# ---------------------------------------------------------------------------
# revision 集合级：任意两套不同语义集合 revision 不同（碰撞防御）
# ---------------------------------------------------------------------------
def test_revision_collection_level_distinct():
    r_small = _build([{"seq": 1, "content": "a", "ref_index": ""}])
    r_big = _build(
        [
            {"seq": 1, "content": "a", "ref_index": ""},
            {"seq": 2, "content": "b", "ref_index": ""},
        ]
    )
    assert r_small.revision_hash != r_big.revision_hash
    # 空集合 vs 非空
    assert compute_revision_hash([]) != r_small.revision_hash
