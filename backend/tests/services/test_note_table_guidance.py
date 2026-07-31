"""附注子表 guidance 读时回填守卫。

对应 spec `n1-deferred-tax-disclosure-template-alignment` R4.6 / Task 8.6。

背景：`_source=workpaper` 的记录读取时走 `note_sub_table_projector` 投影，
投影只认推送来的 `sub_table_data` + `_sub_table_columns`，模板 `tables[].guidance`
完全不参与 → 项目同步过一次后附注 TAB 编制提示永久变空（浏览器 + API 实测）。
`note_table_guidance.carry_template_guidance` 在读端按表名贴回。

不变式：
1. 表名逐字命中才贴（不按位置对齐、不猜）
2. 已有非空 guidance 不被覆盖
3. 模板 / 章节 / 表名任一对不上 → 原样返回（零回归：此前是空，最坏还是空）
4. 模板文件被幂等脚本改写后缓存失效（mtime 参与缓存键）
"""

from __future__ import annotations

import pytest

from app.services.note_table_guidance import (
    carry_template_guidance,
    load_section_guidance,
    resolve_template_type,
)

# 本 spec 已为这两章节写好全表 guidance，作为真实数据锚点
_LISTED_SECTION = "五、30"
_SOE_SECTION = "八、31"
_UNOFFSET = "未经抵销的递延所得税资产和递延所得税负债"
_OFFSET_DETAIL = "递延所得税资产和递延所得税负债互抵明细"


def test_load_section_guidance_returns_all_tables_for_listed() -> None:
    m = load_section_guidance("listed", _LISTED_SECTION)
    assert len(m) == 4
    assert _UNOFFSET in m
    assert m[_UNOFFSET].strip()


def test_load_section_guidance_returns_five_tables_for_soe() -> None:
    m = load_section_guidance("soe", _SOE_SECTION)
    assert len(m) == 5
    # 源模板（2）B 互抵明细（本 spec 新增的第 5 张表）
    assert _OFFSET_DETAIL in m


def test_soe_and_listed_do_not_leak_into_each_other() -> None:
    """章节号跨模板重号时不得串味：listed 无 八、31，soe 无 五、30。"""
    assert load_section_guidance("listed", _SOE_SECTION) == {}
    assert load_section_guidance("soe", _LISTED_SECTION) == {}


@pytest.mark.parametrize("bad", ["", "unknown", None])
def test_unknown_template_type_returns_empty(bad) -> None:
    assert load_section_guidance(bad, _LISTED_SECTION) == {}


def test_carry_fills_by_exact_table_name() -> None:
    tables = [{"name": _UNOFFSET, "headers": ["项目"]}]
    filled = carry_template_guidance(tables, "listed", _LISTED_SECTION)
    assert filled == 1
    assert tables[0]["guidance"].strip()


def test_carry_skips_unknown_table_name() -> None:
    """表名对不上不猜、不按位置对齐（否则会把别的表提示贴错位）。"""
    tables = [{"name": "不存在的表"}]
    assert carry_template_guidance(tables, "listed", _LISTED_SECTION) == 0
    assert "guidance" not in tables[0]


def test_carry_does_not_overwrite_existing_guidance() -> None:
    tables = [{"name": _UNOFFSET, "guidance": "推送侧自带提示"}]
    assert carry_template_guidance(tables, "listed", _LISTED_SECTION) == 0
    assert tables[0]["guidance"] == "推送侧自带提示"


def test_carry_overwrites_blank_guidance() -> None:
    """投影结果里 guidance 是空串（非缺失），必须视为未填。"""
    tables = [{"name": _UNOFFSET, "guidance": "   "}]
    assert carry_template_guidance(tables, "listed", _LISTED_SECTION) == 1
    assert tables[0]["guidance"].strip()


def test_carry_fills_all_soe_tables() -> None:
    names = list(load_section_guidance("soe", _SOE_SECTION).keys())
    tables = [{"name": n} for n in names]
    assert carry_template_guidance(tables, "soe", _SOE_SECTION) == len(names)


@pytest.mark.parametrize(
    ("tables", "tpl", "sec"),
    [
        (None, "soe", _SOE_SECTION),
        ([], "soe", _SOE_SECTION),
        ([{"name": _UNOFFSET}], None, _SOE_SECTION),
        ([{"name": _UNOFFSET}], "soe", None),
        ([{"name": _UNOFFSET}], "soe", "不存在的章节"),
    ],
)
def test_carry_is_noop_on_missing_inputs(tables, tpl, sec) -> None:
    assert carry_template_guidance(tables, tpl, sec) == 0


def test_carry_tolerates_non_dict_entries() -> None:
    tables = ["junk", {"name": _UNOFFSET}, None]
    assert carry_template_guidance(tables, "listed", _LISTED_SECTION) == 1


# ── source_template 记错时的纠正（实证缺陷）────────────────────────────────


def test_resolve_keeps_correct_template_type() -> None:
    """记录正确时原样返回（绝大多数情况，零行为变化）。"""
    assert resolve_template_type("soe", _SOE_SECTION) == "soe"
    assert resolve_template_type("listed", _LISTED_SECTION) == "listed"


def test_resolve_corrects_misrecorded_source_template() -> None:
    """🔴 项目用国企版模板生成时，连上市章节号也被标 soe → 必须纠正为 listed。"""
    assert resolve_template_type("soe", _LISTED_SECTION) == "listed"
    assert resolve_template_type("listed", _SOE_SECTION) == "soe"


def test_resolve_returns_declared_when_no_template_has_the_section() -> None:
    """两个模板都没有该章节（或章节号为空）→ 不猜，原样返回。"""
    assert resolve_template_type("soe", "不存在的章节") == "soe"
    assert resolve_template_type("soe", "") == "soe"
    assert resolve_template_type(None, "不存在的章节") is None


def test_resolve_infers_template_when_declared_is_missing() -> None:
    """`source_template` 为空但章节号只在一份模板里 → 推断出该模板（比返回 None 更有用）。"""
    assert resolve_template_type(None, _SOE_SECTION) == "soe"
    assert resolve_template_type("", _LISTED_SECTION) == "listed"


def test_carry_fills_listed_section_even_when_source_template_says_soe() -> None:
    """端到端：错记 soe 的上市章节也能拿到 guidance（此前 guidance 恒空）。"""
    names = list(load_section_guidance("listed", _LISTED_SECTION).keys())
    tables = [{"name": n} for n in names]
    assert carry_template_guidance(tables, "soe", _LISTED_SECTION) == len(names)
    assert all(t["guidance"].strip() for t in tables)


def test_cache_invalidates_on_template_mtime(tmp_path, monkeypatch) -> None:
    """幂等脚本改写模板后读端必须拿到新 guidance（mtime 参与缓存键）。"""
    import json

    from app.services import note_table_guidance as mod

    fake = tmp_path / "note_template_listed.json"
    fake.write_text(
        json.dumps(
            {"sections": [{"section_number": "X、1", "tables": [{"name": "T", "guidance": "v1"}]}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    assert mod.load_section_guidance("listed", "X、1") == {"T": "v1"}

    fake.write_text(
        json.dumps(
            {"sections": [{"section_number": "X、1", "tables": [{"name": "T", "guidance": "v2"}]}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    import os

    st = fake.stat()
    os.utime(fake, (st.st_atime, st.st_mtime + 10))
    assert mod.load_section_guidance("listed", "X、1") == {"T": "v2"}
