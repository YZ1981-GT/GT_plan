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


# ─── P9: 归一化（投影结果被回写的容错） ──────────────────────────────────────
#
# 现网数据实证（D2 应收账款「按坏账计提方法分类披露（上年年末金额）」）：
# 子表值被写成投影输出的表对象 {"rows": [...], "_column_groups": ...}，行也是
# 位置化的 {label, values[], is_total}。旧实现 warning 后跳过整表 → 附注与
# Word 导出同时丢表。归一后须解包 + 逆投影回业务键。

_COLS_D2_PRIOR = [
    {"key": "label", "label": "类别", "is_label": True},
    {"key": "book_amount_prior", "label": "账面余额·金额"},
    {"key": "provision_amount_prior", "label": "坏账准备·金额"},
]


def test_p9_unwrap_table_object_wrapper():
    """``{"rows": [...]}`` 包装 → 解包投影，不再跳过整表。"""
    td = {
        "_source": "workpaper",
        "sub_table_data": {
            "按坏账计提方法分类披露（上年年末金额）": {
                "rows": [
                    {"label": "按单项计提坏账准备", "values": [10, 1], "is_total": False},
                    {"label": "合计", "values": [10, 1], "is_total": True},
                ],
                "_column_groups": [{"group": "上年年末金额", "start": 1, "span": 2}],
            },
        },
        "_sub_table_columns": {"按坏账计提方法分类披露（上年年末金额）": _COLS_D2_PRIOR},
    }
    tables = project_sub_tables(td)

    assert len(tables) == 1
    t = tables[0]
    assert t["name"] == "按坏账计提方法分类披露（上年年末金额）"
    assert t["headers"] == ["类别", "账面余额·金额", "坏账准备·金额"]
    assert t["rows"][0]["label"] == "按单项计提坏账准备"
    # 逆投影：values 按列序还原为业务键，不再整表空值
    assert t["rows"][0]["values"] == [10, 1]
    assert t["rows"][-1]["is_total"] is True


def test_p9_inverse_project_positional_values():
    """位置化 ``values`` 行（列表形态）→ 按列头逆投影，不产出整表 None。"""
    td = {
        "_source": "workpaper",
        "sub_table_data": {
            "t": [{"label": "甲", "values": [100, 5], "is_total": False}],
        },
        "_sub_table_columns": {"t": _COLS_D2_PRIOR},
    }
    tables = project_sub_tables(td)
    assert tables[0]["rows"][0]["values"] == [100, 5]


def test_p9_business_keys_win_over_values():
    """行同时含业务键与 ``values`` → 业务键优先（原始值不被位置值覆盖）。"""
    td = {
        "_source": "workpaper",
        "sub_table_data": {
            "t": [{"label": "甲", "book_amount_prior": 999, "values": [100, 5]}],
        },
        "_sub_table_columns": {"t": _COLS_D2_PRIOR},
    }
    tables = project_sub_tables(td)
    assert tables[0]["rows"][0]["values"] == [999, 5]


def test_p9_no_columns_keeps_degrade_branch():
    """包装解包后无列头 → 仍走 P8 降级（label 列可读，不用英文键）。"""
    td = {
        "_source": "workpaper",
        "sub_table_data": {"t": {"rows": [{"label": "甲", "values": [1]}]}},
    }
    tables = project_sub_tables(td)
    assert tables[0]["headers"] == ["项目"]
    assert tables[0]["rows"][0]["values"] == []
    assert tables[0]["_needs_columns"] is True


def test_p9_unusable_value_dropped():
    """既非列表、也取不出 rows 列表 → 丢弃该表（真损坏），其余表不受影响。"""
    td = {
        "_source": "workpaper",
        "sub_table_data": {"坏": {"headers": ["x"]}, "好": [{"label": "甲"}]},
    }
    tables = project_sub_tables(td)
    assert [t["name"] for t in tables] == ["好"]


def test_p9_normalize_is_pure():
    """归一化不修改入参（P1 在含包装形态下同样成立）。"""
    td = {
        "_source": "workpaper",
        "sub_table_data": {"t": {"rows": [{"label": "甲", "values": [1, 2]}]}},
        "_sub_table_columns": {"t": _COLS_D2_PRIOR},
    }
    snapshot = copy.deepcopy(td)
    r1 = project_sub_tables(td)
    r2 = project_sub_tables(td)
    assert r1 == r2
    assert td == snapshot


# ---------------------------------------------------------------------------
# ColumnDef.flat 三态语义（disclosure-columns-coverage-rollout R3 / Property 5）
#
# 源模板本就是单行表头的表（如房企开发成本/开发产品/周转房），不声明 flat 时
# `_infer_groups_from_headers` 会把 `本期增加`/`本期减少` 归到凭空的「本期」下。
# ---------------------------------------------------------------------------


def _flat_defs() -> list[dict]:
    return [
        {"key": "project_name", "label": "项目名称", "is_label": True, "flat": True},
        {"key": "opening", "label": "期初余额"},
        {"key": "increase", "label": "本期增加"},
        {"key": "decrease", "label": "本期减少"},
        {"key": "ending", "label": "期末余额"},
    ]


def test_extract_column_groups_flat_returns_empty_list() -> None:
    """任一列 flat=True → 返回 []（显式单级），区别于 None（未声明）。"""
    from app.services.note_sub_table_projector import _extract_column_groups

    assert _extract_column_groups(_flat_defs()) == []


def test_extract_column_groups_undeclared_returns_none() -> None:
    """无 group 也无 flat → 返回 None，调用方仍可回退前缀推断（存量行为不变）。"""
    from app.services.note_sub_table_projector import _extract_column_groups

    defs = [d for d in _flat_defs()]
    defs[0] = {"key": "project_name", "label": "项目名称", "is_label": True}
    assert _extract_column_groups(defs) is None


def test_extract_column_groups_explicit_group_unaffected_by_flat_branch() -> None:
    """显式 group 仍产出非空区间（flat 分支不得抢占）。"""
    from app.services.note_sub_table_projector import _extract_column_groups

    defs = [
        {"key": "label", "label": "项目", "is_label": True},
        {"key": "end_gross", "label": "账面余额", "group": "期末余额"},
        {"key": "end_net", "label": "账面价值", "group": "期末余额"},
    ]
    assert _extract_column_groups(defs) == [
        {"group": "期末余额", "start": 1, "span": 2}
    ]


def test_flat_table_projection_suppresses_inferred_parent_header() -> None:
    """端到端：flat 表投影后 _column_groups 为空，不出现推断的「本期」父表头。"""
    from app.services.note_sub_table_projector import project_sub_tables

    td = {
        "_source": "workpaper",
        "sub_table_data": {
            "周转房": [
                {"project_name": "A 项目", "opening": 1, "increase": 2,
                 "decrease": 0, "ending": 3},
            ],
        },
        "_sub_table_columns": {"周转房": _flat_defs()},
    }

    tables = project_sub_tables(td)
    assert tables is not None and len(tables) == 1
    t = tables[0]
    assert t["headers"] == ["项目名称", "期初余额", "本期增加", "本期减少", "期末余额"]
    assert t["_column_groups"] == []


def test_undeclared_table_still_gets_inferred_groups() -> None:
    """反例：同一张表去掉 flat → 仍走前缀推断（证明 flat 是唯一开关）。"""
    from app.services.note_sub_table_projector import project_sub_tables

    defs = [d.copy() for d in _flat_defs()]
    defs[0].pop("flat")
    td = {
        "_source": "workpaper",
        "sub_table_data": {
            "周转房": [
                {"project_name": "A 项目", "opening": 1, "increase": 2,
                 "decrease": 0, "ending": 3},
            ],
        },
        "_sub_table_columns": {"周转房": defs},
    }

    groups = project_sub_tables(td)[0]["_column_groups"]
    # 推断结果可能为 None 或含「本期」分组，但一定不是 flat 的 []
    assert groups != []


def test_flat_column_groups_ranges_are_valid_when_present() -> None:
    """Property 4：产出的分组区间 start>=1、不越界、不重叠。"""
    from app.services.note_sub_table_projector import _extract_column_groups

    defs = [
        {"key": "label", "label": "项目", "is_label": True},
        {"key": "a", "label": "账面余额", "group": "期末余额"},
        {"key": "b", "label": "跌价准备", "group": "期末余额"},
        {"key": "c", "label": "账面余额", "group": "期初余额"},
        {"key": "d", "label": "跌价准备", "group": "期初余额"},
    ]
    groups = _extract_column_groups(defs)
    assert groups is not None and groups != []

    n_headers = 1 + sum(1 for d in defs if not d.get("is_label"))
    occupied: set[int] = set()
    for g in groups:
        start, span = int(g["start"]), int(g["span"])
        assert start >= 1
        assert start + span <= n_headers
        rng = set(range(start, start + span))
        assert not (rng & occupied)
        occupied |= rng


# ---------------------------------------------------------------------------
# Property-Based Tests：flat 三态（P5）+ _column_groups 区间合法（P4）
#
# 上面的样例测试固定了几个真实表形态；下面用 hypothesis 把契约推广到任意
# ColumnDef 组合，避免"只在样例上成立"。max_examples 沿用本文件既有约定。
# ---------------------------------------------------------------------------

# None = 不声明 group；"" = 声明空串（应视为未声明）；含 "/" = 多级分组
_ST_GROUP = st.sampled_from(
    [None, "", "期末余额", "期初余额", "本期变动", "期末余额/账面余额", "期末余额/减值准备"]
)
_ST_GROUP_NONEMPTY = st.sampled_from(
    ["期末余额", "期初余额", "本期变动", "期末余额/账面余额", "期末余额/减值准备"]
)
# None = 不声明 flat；False = 显式声明为假（应等同未声明）
_ST_FLAT = st.sampled_from([None, True, False])


@st.composite
def st_arbitrary_column_defs(draw) -> list[dict]:
    """任意 ColumnDef 列表：``is_label`` / ``group``（含 None / 空串 / 多级）/ ``flat`` 随机组合。

    唯一保证：每项是含 ``key`` 的 dict —— 这正是 production 侧 ``_clean_defs``
    的后置条件，投影器只会拿到这种形状。
    """
    n = draw(st.integers(min_value=0, max_value=6))
    defs: list[dict] = []
    for i in range(n):
        d: dict = {"key": f"c{i}", "label": draw(st_cn_label)}
        if draw(st.booleans()):
            d["is_label"] = draw(st.booleans())  # 含显式 False（假值应按数据列处理）
        g = draw(_ST_GROUP)
        if g is not None:
            d["group"] = g
        f = draw(_ST_FLAT)
        if f is not None:
            d["flat"] = f
        defs.append(d)
    return defs


@st.composite
def st_grouped_column_defs(draw) -> list[dict]:
    """恰有标签列声明 + 至少一列带 ``group`` 的 ColumnDef 列表（必产出非空分组）。

    ⚠️ 前置条件「至少一列 ``is_label``」不是放松属性，而是 Property 4 的定义域：
    ``start >= 1（不覆盖标签列）`` 本身预设了标签列存在（Requirement 1.3 强制声明，
    前端 Property 2 契约测试守护）。
    """
    n = draw(st.integers(min_value=2, max_value=6))
    label_at = draw(st.integers(min_value=0, max_value=n - 1))
    non_label = [i for i in range(n) if i != label_at]
    forced = draw(st.sampled_from(non_label))  # 保证至少一个分组，避免恒 None

    defs: list[dict] = []
    for i in range(n):
        d: dict = {"key": f"c{i}", "label": draw(st_cn_label)}
        if i == label_at:
            d["is_label"] = True
        else:
            g = draw(_ST_GROUP_NONEMPTY) if i == forced else draw(_ST_GROUP)
            if g:
                d["group"] = g
        defs.append(d)
    return defs


def _leaf_intervals(entries: list[dict]):
    """把 ``_column_groups`` 的两种形态（扁平 start/span、多级 children 树）摊平成叶子区间。"""
    for e in entries:
        if "children" in e:
            yield from _leaf_intervals(e["children"])
        elif "start" in e:
            yield int(e["start"]), int(e["span"])
        elif "headerIdx" in e:
            yield int(e["headerIdx"]), 1


@h_settings(max_examples=10, deadline=None)
@given(defs=st_arbitrary_column_defs())
def test_pbt_p5_flat_three_state_contract(defs) -> None:
    """Property 5: flat 三态语义对任意 ColumnDef 组合成立。

    - 任一列 ``flat`` 为真 → ``[]``（显式单级，调用方禁止前缀推断）
    - 否则任一**非标签列**带非空 ``group`` → 非空列表（显式分组）
    - 两者皆无 → ``None``（未声明，调用方回退 ``_infer_groups_from_headers``）

    三态必须可区分：``[]`` 与 ``None`` 不得混同，否则 flat 表会被凭空加父表头。

    **Validates: Requirements 3.1, 3.2, 3.3**
    """
    from app.services.note_sub_table_projector import _extract_column_groups

    result = _extract_column_groups(defs)

    has_flat = any(d.get("flat") for d in defs)
    # is_label 列在归组时被跳过，其 group 声明不参与分组
    has_group = any(d.get("group") for d in defs if not d.get("is_label"))

    if has_flat:
        assert result == [], f"flat 表应返回 []（显式单级），实得 {result!r}"
        assert result is not None, "[] 与 None 必须可区分"
    elif has_group:
        assert isinstance(result, list) and result != [], (
            f"声明了 group 应产出非空分组，实得 {result!r}"
        )
    else:
        assert result is None, f"既无 group 也无 flat 应返回 None（允许前缀推断），实得 {result!r}"


@h_settings(max_examples=10, deadline=None)
@given(defs=st_grouped_column_defs())
def test_pbt_p4_column_groups_intervals_are_valid(defs) -> None:
    """Property 4: 产出的 ``_column_groups`` 区间恒合法。

    对任意声明了 ``group`` 的列定义（端到端走 ``project_sub_tables``，headers 由
    production 产出，不复刻公式）：

    - ``start >= 1``：绝不覆盖标签列（headers[0]）
    - ``start + span <= len(headers)``：不越界
    - 叶子区间两两不重叠
    - 区间按 ``start`` 升序（前端按序嵌套 el-table-column，乱序会错位）

    **Validates: Requirements 2.3**
    """
    td = {
        "_source": "workpaper",
        "sub_table_data": {"t": [{d["key"]: 1 for d in defs}]},
        "_sub_table_columns": {"t": defs},
    }
    tables = project_sub_tables(td)
    assert tables is not None and len(tables) == 1

    headers = tables[0]["headers"]
    groups = tables[0]["_column_groups"]
    assert groups, f"已声明 group 却未产出分组：{defs!r}"

    intervals = list(_leaf_intervals(groups))
    assert intervals, f"分组结构未摊平出任何区间：{groups!r}"

    occupied: set[int] = set()
    starts: list[int] = []
    for start, span in intervals:
        assert span >= 1, f"span 必须 >=1，实得 {span}（{groups!r}）"
        assert start >= 1, f"分组不得覆盖标签列，实得 start={start}（{groups!r}）"
        assert start + span <= len(headers), (
            f"区间越界：start={start} span={span} headers={headers}（{groups!r}）"
        )
        rng = set(range(start, start + span))
        assert not (rng & occupied), f"区间重叠：{start}..{start + span - 1}（{groups!r}）"
        occupied |= rng
        starts.append(start)

    assert starts == sorted(starts), f"区间未按 start 升序：{starts}（{groups!r}）"
