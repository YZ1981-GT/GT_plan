"""附注模板 markdown 粗体标记 `**` 卫生守卫（平台级）。

`note_template_{listed,soe}.json` 的 `text_sections` / `tables[].guidance` 曾残留
`附注模版/*.md` 的 markdown 粗体标记（`rebuild_note_from_md.py` 搬运产物），
而附注正文 `text_content` 与 docx 导出都按**纯文本**渲染 → `**` 字面显示给用户。

🔴 关键：只能**成对**剥离。实测两段 `**` 是不成对的脱敏占位::

    诉讼金额为**元，截止本报告公告日，此案正在审理过程中。

无脑 `replace('**','')` 会破坏语义。本守卫同时锁死两个方向：
1. 全库不得残留**成对** `**`；
2. 剥离函数对**不成对** `**` 必须原样返回（反向自检）。

spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R1（Property 1/2/3）
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_ROOT = Path(__file__).resolve().parent.parent
_FIX = _ROOT / "scripts" / "fix" / "fix_note_bold_markers.py"
_PATHS = [
    _ROOT / "data" / "note_template_listed.json",
    _ROOT / "data" / "note_template_soe.json",
]


def _load_fix():
    spec = importlib.util.spec_from_file_location("_fix_bold_markers", _FIX)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix()


# ─────────────────────── 单元：strip_pairs 行为 ───────────────────────

@pytest.mark.parametrize(
    "raw,expected,pairs",
    [
        ("**重要**", "重要", 1),
        ("前**中**后", "前中后", 1),
        ("**a** 与 **b**", "a 与 b", 2),
        ("**【提示：xxx。**】", "【提示：xxx。】", 1),
        # 不成对：脱敏占位，原样保留
        ("诉讼金额为**元", "诉讼金额为**元", 0),
        ("**只有开头", "**只有开头", 0),
        ("结尾只有**", "结尾只有**", 0),
        # 无标记
        ("普通文本", "普通文本", 0),
        ("单星*不算", "单星*不算", 0),
        # 跨行
        ("**第一行\n第二行**", "第一行\n第二行", 1),
    ],
)
def test_strip_pairs_cases(raw: str, expected: str, pairs: int) -> None:
    got, n = FIX.strip_pairs(raw)
    assert got == expected
    assert n == pairs


def test_strip_pairs_non_string_passthrough() -> None:
    for v in (None, 123, 4.5, True, [], {}):
        got, n = FIX.strip_pairs(v)
        assert got is v
        assert n == 0


def test_strip_pairs_nested_converges() -> None:
    """`****xxx****` 多轮收敛（幂等循环上限内）。"""
    got, n = FIX.strip_pairs("****xxx****")
    assert "**" not in got
    assert n >= 1


# ─────────────────────── Property 1/2/3 ───────────────────────

#: `alphabet` 的元素必须是单字符（hypothesis 约束），故 `**` 作为 token 由列表拼接产出
_TEXT = st.lists(
    st.sampled_from(["a", "b", "中", "文", " ", "\n", "*", "**", "【", "】", "：", "。"]),
    min_size=0,
    max_size=20,
).map("".join)


@settings(max_examples=5, deadline=None)
@given(_TEXT)
def test_property1_strip_preserves_non_star_content(raw: str) -> None:
    """Property 1: 剥离只删 `*`，其它字符逐字不变；`**` 次数按剥离对数递减。"""
    got, n = FIX.strip_pairs(raw)
    assert got.replace("*", "") == raw.replace("*", "")
    assert FIX.count_markers(got) <= FIX.count_markers(raw)


@settings(max_examples=5, deadline=None)
@given(st.text(alphabet=st.sampled_from(list("ab中文 ")), min_size=1, max_size=20))
def test_property2_single_marker_preserved(body: str) -> None:
    """Property 2: 只含一个 `**` 的文本原样返回（脱敏占位）。"""
    raw = body + "**" + body
    assert FIX.count_markers(raw) == 1
    got, n = FIX.strip_pairs(raw)
    assert got == raw
    assert n == 0


@settings(max_examples=5, deadline=None)
@given(_TEXT)
def test_property3_idempotent(raw: str) -> None:
    """Property 3: 二次剥离必为 0 对。"""
    once, _ = FIX.strip_pairs(raw)
    _, second = FIX.strip_pairs(once)
    assert second == 0


# ─────────────────────── 全库断言 ───────────────────────

def _scan(path: Path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    variant = "listed" if "listed" in path.name else "soe"
    return FIX.scan_doc(doc, variant, apply=False)


@pytest.mark.parametrize("path", _PATHS, ids=lambda p: p.name)
def test_no_paired_bold_markers_in_templates(path: Path) -> None:
    pairs, _odd = _scan(path)
    assert not pairs, (
        f"{path.name} 残留 {len(pairs)} 处成对 `**`（附注正文与 docx 会字面渲染）："
        + " / ".join(str(f) for f in pairs[:8])
        + "；请重跑 python backend/scripts/fix/fix_note_bold_markers.py --apply"
    )


@pytest.mark.parametrize("path", _PATHS, ids=lambda p: p.name)
def test_odd_markers_are_masked_placeholders_only(path: Path) -> None:
    """不成对 `**` 只允许出现在脱敏占位语境（`金额为**元`）。"""
    _pairs, odd = _scan(path)
    bad = [f for f in odd if "**元" not in f.after and "**万元" not in f.after]
    assert not bad, (
        f"{path.name} 出现非脱敏语境的不成对 `**`，需人工确认："
        + " / ".join(str(f) for f in bad[:5])
    )


def test_scan_finds_something_in_reality() -> None:
    """反向自检：扫描器确实能在真实模板里找到不成对占位，否则断言全在空转。"""
    total_odd = 0
    for p in _PATHS:
        _pairs, odd = _scan(p)
        total_odd += len(odd)
    assert total_odd >= 2, (
        "两份模板里已知各有 1 处脱敏占位 `**元`；扫到 0 处说明遍历路径失效"
        f"（实际 {total_odd}）"
    )


def test_scanner_detects_injected_pair() -> None:
    """反向自检：往 fixture 注入成对 `**`，扫描器必须抓到且 apply 后消失。"""
    doc = {
        "sections": [
            {
                "section_number": "测、1",
                "text_sections": ["前**加粗**后"],
                "rows": [{"label": "普通行", "children": [{"label": "**子行**"}]}],
                "tables": [
                    {
                        "name": "替身表",
                        "guidance": "提示：**重点**说明",
                        "headers": ["项目", "**金额**"],
                        "columns": [{"key": "a", "label": "**列名**", "group": "**组**"}],
                        "rows": [{"label": "**表内行**"}],
                    }
                ],
            }
        ]
    }
    pairs, odd = FIX.scan_doc(json.loads(json.dumps(doc)), "fixture", apply=False)
    wheres = {f.where for f in pairs}
    assert len(pairs) == 7, f"应抓到 7 处（含嵌套 children 与 columns），实际 {len(pairs)}：{wheres}"
    assert any("text_sections" in w for w in wheres)
    assert any("children" not in w and "rows.label" in w for w in wheres)
    assert any("guidance" in w for w in wheres)
    assert any("headers" in w for w in wheres)
    assert any("columns" in w and ".label" in w for w in wheres)
    assert any("columns" in w and ".group" in w for w in wheres)
    assert not odd

    mutated = json.loads(json.dumps(doc))
    FIX.scan_doc(mutated, "fixture", apply=True)
    after = json.dumps(mutated, ensure_ascii=False)
    assert "**" not in after, "apply=True 后仍残留 `**`"
    assert "加粗" in after and "重点" in after and "子行" in after, "剥离时误删了内容"


def test_scanner_leaves_odd_marker_in_fixture() -> None:
    """反向自检：fixture 里的不成对 `**` 必须被列为 odd 且原样保留。"""
    doc = {
        "sections": [
            {
                "section_number": "测、2",
                "text_sections": ["诉讼金额为**元，正在审理。"],
                "tables": [],
            }
        ]
    }
    mutated = json.loads(json.dumps(doc))
    pairs, odd = FIX.scan_doc(mutated, "fixture", apply=True)
    assert not pairs
    assert len(odd) == 1
    assert mutated["sections"][0]["text_sections"][0] == "诉讼金额为**元，正在审理。"


def test_check_mode_exit_code_is_zero() -> None:
    """`--check` 语义：全库无成对残迹时 process() 返回 ok。"""
    for path in _PATHS:
        ok, log = FIX.process(path, apply=False, check_only=True)
        assert ok, "\n".join(log)
