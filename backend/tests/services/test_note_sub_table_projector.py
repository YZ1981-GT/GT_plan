"""投影器 project_sub_tables 的纯函数属性测试（P1~P8）

spec: disclosure-table-sync-convergence — design §Correctness Properties
Task 1.2

- P1 纯函数：同输入多次输出相等 + 不改入参
- P2 列序保持：headers == _columns 声明序，label 列置首
- P3 缺字段空单元：行缺 def.key → 单元格为 None，不丢列
- P4 额外字段忽略：行含未声明键 → 不新增列
- P5 合计行保持：is_total 透传
- P6 多表键序：按 sub_table_data 键插入序逐张投影
- P7 来源优先级：非 workpaper → None；workpaper 空 sub → []
- P8 降级不杜撰：无 _columns → headers 不含英文字段键
"""

from __future__ import annotations

import copy
import string

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from app.services.note_sub_table_projector import project_sub_tables


# ─── Strategies ──────────────────────────────────────────────────────────────

st_field_key = st.text(alphabet=string.ascii_lowercase + "_", min_size=1, max_size=8)
st_cn_label = st.sampled_from(["期末账面余额", "期末跌价准备", "期末净额", "本期计提", "本期转回", "存货类别"])
st_scalar = st.one_of(
    st.integers(min_value=-10000, max_value=10000),
    st.text(max_size=8),
    st.none(),
)


def _make_table_data(sub_key="存货分类", with_columns=True, source="workpaper"):
    rows = [
        {"label": "原材料", "end_gross": 100, "end_impairment": 5},
        {"label": "库存商品", "end_gross": 200, "end_impairment": 10},
        {"label": "合计", "end_gross": 300, "end_impairment": 15, "is_total": True},
    ]
    td = {"_source": source, "sub_table_data": {sub_key: rows}}
    if with_columns:
        td["_sub_table_columns"] = {
            sub_key: [
                {"key": "label", "label": "存货类别", "is_label": True},
                {"key": "end_gross", "label": "期末账面余额"},
                {"key": "end_impairment", "label": "期末跌价准备"},
            ]
        }
    return td


# ─── P1: 纯函数 ──────────────────────────────────────────────────────────────

def test_p1_pure_no_mutation_and_stable():
    td = _make_table_data()
    snapshot = copy.deepcopy(td)
    r1 = project_sub_tables(td)
    r2 = project_sub_tables(td)
    assert r1 == r2, "同输入多次调用输出应相等"
    assert td == snapshot, "投影不得修改入参"


# ─── P2: 列序保持 + label 列置首 ─────────────────────────────────────────────

def test_p2_header_order_label_first():
    td = _make_table_data()
    tables = project_sub_tables(td)
    assert tables is not None and len(tables) == 1
    assert tables[0]["headers"] == ["存货类别", "期末账面余额", "期末跌价准备"]


def test_p2_label_by_is_label_not_position():
    # label 列声明在中间，仍应置首
    td = {
        "_source": "workpaper",
        "sub_table_data": {"t": [{"a": 1, "label": "行1", "b": 2}]},
        "_sub_table_columns": {
            "t": [
                {"key": "a", "label": "甲"},
                {"key": "label", "label": "名称", "is_label": True},
                {"key": "b", "label": "乙"},
            ]
        },
    }
    tables = project_sub_tables(td)
    assert tables[0]["headers"] == ["名称", "甲", "乙"]
    assert tables[0]["rows"][0]["label"] == "行1"
    assert tables[0]["rows"][0]["values"] == [1, 2]


# ─── P3: 缺字段空单元 ────────────────────────────────────────────────────────

def test_p3_missing_field_empty_cell_no_drop():
    td = {
        "_source": "workpaper",
        "sub_table_data": {"t": [{"label": "行1", "end_gross": 100}]},  # 缺 end_impairment
        "_sub_table_columns": {
            "t": [
                {"key": "label", "label": "类别", "is_label": True},
                {"key": "end_gross", "label": "余额"},
                {"key": "end_impairment", "label": "减值"},
            ]
        },
    }
    tables = project_sub_tables(td)
    assert tables[0]["headers"] == ["类别", "余额", "减值"]  # 列不丢
    assert tables[0]["rows"][0]["values"] == [100, None]  # 缺字段 → None


# ─── P4: 额外字段忽略 ────────────────────────────────────────────────────────

def test_p4_extra_field_ignored():
    td = {
        "_source": "workpaper",
        "sub_table_data": {"t": [{"label": "行1", "end_gross": 100, "extra_x": 999}]},
        "_sub_table_columns": {
            "t": [
                {"key": "label", "label": "类别", "is_label": True},
                {"key": "end_gross", "label": "余额"},
            ]
        },
    }
    tables = project_sub_tables(td)
    assert tables[0]["headers"] == ["类别", "余额"]  # extra_x 不成列
    assert tables[0]["rows"][0]["values"] == [100]


# ─── P5: 合计行保持 ──────────────────────────────────────────────────────────

def test_p5_is_total_preserved():
    tables = project_sub_tables(_make_table_data())
    rows = tables[0]["rows"]
    assert rows[-1]["is_total"] is True
    assert rows[0]["is_total"] is False


# ─── P6: 多表键序 ────────────────────────────────────────────────────────────

def test_p6_multi_table_key_order():
    td = {
        "_source": "workpaper",
        "sub_table_data": {
            "表A": [{"label": "a"}],
            "表B": [{"label": "b"}],
            "表C": [{"label": "c"}],
            "_note_texts": [{"text": "meta"}],  # 元数据键应跳过
        },
        "_sub_table_columns": {
            "表A": [{"key": "label", "label": "L", "is_label": True}],
            "表B": [{"key": "label", "label": "L", "is_label": True}],
            "表C": [{"key": "label", "label": "L", "is_label": True}],
        },
    }
    tables = project_sub_tables(td)
    assert [t["name"] for t in tables] == ["表A", "表B", "表C"]  # 键序保持，_note_texts 跳过


# ─── P7: 来源优先级 ──────────────────────────────────────────────────────────

def test_p7_non_workpaper_returns_none():
    td = _make_table_data(source="engine_fill")
    assert project_sub_tables(td) is None


def test_p7_no_source_returns_none():
    td = {"sub_table_data": {"t": [{"label": "x"}]}}  # 无 _source
    assert project_sub_tables(td) is None


def test_p7_workpaper_empty_sub_returns_empty_list():
    assert project_sub_tables({"_source": "workpaper", "sub_table_data": {}}) == []
    assert project_sub_tables({"_source": "workpaper_html", "sub_table_data": {}}) == []


def test_p7_non_dict_returns_none():
    assert project_sub_tables(None) is None
    assert project_sub_tables("x") is None
    assert project_sub_tables([]) is None


# ─── P8: 降级不杜撰列头 ──────────────────────────────────────────────────────

def test_p8_degrade_no_english_headers():
    td = _make_table_data(with_columns=False)  # 无 _sub_table_columns
    tables = project_sub_tables(td)
    assert len(tables) == 1
    t = tables[0]
    assert t["_needs_columns"] is True
    assert t["headers"] == ["项目"]  # 仅标签列，非英文字段键
    # 关键：headers 不含任何英文字段键
    for h in t["headers"]:
        assert h not in ("end_gross", "end_impairment", "label", "is_total")
    # 降级不产出数据值列
    assert all(r["values"] == [] for r in t["rows"])
    # 但 label 与 is_total 仍保留
    assert t["rows"][-1]["is_total"] is True


def test_p8_degrade_no_label_empty_headers():
    td = {"_source": "workpaper", "sub_table_data": {"t": [{"amount": 1}]}}  # 行无 label 无 columns
    tables = project_sub_tables(td)
    assert tables[0]["headers"] == []  # 无 label → 空表头，不用英文键


@h_settings(max_examples=10, deadline=None)
@given(
    keys=st.lists(st_field_key, min_size=1, max_size=4, unique=True),
    labels=st.lists(st_cn_label, min_size=1, max_size=4),
)
def test_p8_pbt_headers_never_equal_field_keys_when_no_columns(keys, labels):
    """无 _columns 降级时，headers 恒不含任何行字段键（P8 泛化）。"""
    row = {"label": "行"}
    for k in keys:
        row[k] = 1
    td = {"_source": "workpaper", "sub_table_data": {"t": [row]}}
    tables = project_sub_tables(td)
    headers = tables[0]["headers"]
    for k in keys:
        assert k not in headers


# ─── Task 4.2: get_note_detail 读时注入语义（镜像 router glue，P7） ───────────


def _apply_router_injection(table_data):
    """复刻 disclosure_notes.get_note_detail 的注入逻辑：projected 非空才注入 _tables。"""
    projected = project_sub_tables(table_data)
    if projected and table_data is not None:
        return {**table_data, "_tables": projected}
    return table_data


def test_router_injects_tables_for_workpaper_source():
    td = _make_table_data()
    out = _apply_router_injection(td)
    assert "_tables" in out
    assert out["_tables"][0]["headers"] == ["存货类别", "期末账面余额", "期末跌价准备"]
    # 原 sub_table_data 保留（投影不替换权威存储）
    assert out["sub_table_data"] == td["sub_table_data"]


def test_router_no_injection_for_engine_source():
    td = {"_source": "engine_fill", "_tables": [{"name": "既有", "headers": ["a"], "rows": []}]}
    out = _apply_router_injection(td)
    assert out is td  # 非 workpaper 来源 → 不投影、不改（P7 / Req6.2）
    assert out["_tables"][0]["name"] == "既有"


def test_router_no_injection_when_workpaper_empty_sub():
    td = {"_source": "workpaper", "sub_table_data": {}}
    out = _apply_router_injection(td)
    # 空 sub → projected=[]（falsy）→ 不注入 _tables，不遮蔽任何既有内容
    assert "_tables" not in out


# ─── label 兜底：labelKey 值缺失时回退通用 label（合计行常用 label） ───────────

def test_label_key_falls_back_to_label_for_total_row():
    td = {
        "_source": "workpaper",
        "sub_table_data": {"t": [
            {"borrower": "甲公司", "end_balance": 100},
            {"label": "合计", "end_balance": 100, "is_total": True},  # 合计行用 label 非 borrower
        ]},
        "_sub_table_columns": {"t": [
            {"key": "borrower", "label": "借款单位", "is_label": True},
            {"key": "end_balance", "label": "期末余额"},
        ]},
    }
    tables = project_sub_tables(td)
    rows = tables[0]["rows"]
    assert rows[0]["label"] == "甲公司"
    assert rows[1]["label"] == "合计"  # 兜底回退到 label，不显示空
    assert rows[1]["is_total"] is True
