"""守卫：G10/G11/G13/G14 附注披露表 columns 与 guidance 结构完整。

锁定 `fix_note_g_liability_and_pl_structure.py` 的对齐结果，防 md 重建 / 并发会话回退：

- 幂等脚本 --check 返回 0 项欠账（exit code 0）；
- 所有 13 张表 columns 非空、首列 flat=True；
- 所有 13 张表 guidance 非空；
- G11/G13/G14 列键一致（current_amount / prior_amount），G10 逐表按底稿（R8.4 批 9b-2：原先主表列套给本节每张表）。

章节落点：
  G10: listed 五、34 + 五、35（衍生金融负债）/ soe 八、34
  G11: listed 五、69 / soe 八、70
  G13: listed 五、75 / soe 八、72
  G14: listed 五、76 / soe 八、73

spec: g-cycle-extraction-mapping-and-disclosure-alignment
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND / "scripts" / "fix" / "fix_note_g_liability_and_pl_structure.py"
DATA_DIR = BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"


# ═══════════════════════════ Helper: load fix module ═══════════════════════════


def _load_fix():
    """动态加载幂等脚本模块，供后续 Property 测试直接调用内部函数。"""
    spec = importlib.util.spec_from_file_location("_fix_g_struct", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix()


def _get_section(path: Path, section_number: str) -> dict | None:
    """从模板 JSON 中读取指定章节。"""
    doc = json.loads(path.read_text(encoding="utf-8"))
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    return None


# 章节映射：(path, section_number) per chapter key
_CHAPTER_MAP: dict[str, tuple[Path, str]] = {
    "g10_listed": (LISTED_PATH, "五、34"),
    "g10_listed_derivative": (LISTED_PATH, "五、35"),
    "g10_soe": (SOE_PATH, "八、34"),
    "g11_listed": (LISTED_PATH, "五、69"),
    "g11_soe": (SOE_PATH, "八、70"),
    "g13_listed": (LISTED_PATH, "五、75"),
    "g13_soe": (SOE_PATH, "八、72"),
    "g14_listed": (LISTED_PATH, "五、76"),
    "g14_soe": (SOE_PATH, "八、73"),
}


# ═══════════════════════════ 核心守卫：--check 返回 0 项欠账 ═══════════════════════════


def test_check_returns_zero_outstanding():
    """幂等脚本 --check 应返回 0 项欠账。

    子进程输出按 UTF-8 读（同 test_note_m_equity_structure）：原写法 ``text=True`` 在 Windows 按 GBK 解码，脚本的
    中文输出解码失败 ⇒ ``stdout`` 为 None、本用例恒红（HEAD 即红，R8.4 批 9b-2 修）。
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(BACKEND),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, f"--check failed:\n{result.stdout}\n{result.stderr}"
    assert "0 项欠账" in result.stdout


# ═══════════════════════════ 反向自检：脚本文件自身存在且可导入 ═══════════════════════════


def test_script_exists_and_importable():
    """幂等脚本文件存在且可成功加载（防止意外删除）。"""
    assert SCRIPT.exists(), f"脚本不存在：{SCRIPT}"
    assert hasattr(FIX, "main"), "脚本缺少 main 入口"
    assert hasattr(FIX, "_runner"), "脚本缺少 _runner 调度函数"
    assert hasattr(FIX, "_CHAPTER_DEFS"), "脚本缺少 _CHAPTER_DEFS 定义"


# ═══════════════════════════ Property 11: 所有 12 张表有非空 columns 且首列 flat ═══════════════════════════


ALL_CHAPTER_KEYS = list(_CHAPTER_MAP.keys())


@pytest.mark.parametrize("chapter_key", ALL_CHAPTER_KEYS)
def test_property_11_columns_nonempty_and_first_flat(chapter_key: str):
    """Property 11：每张表 columns 非空，首列标 flat=True。"""
    path, section_number = _CHAPTER_MAP[chapter_key]
    sec = _get_section(path, section_number)
    assert sec is not None, f"章节 {section_number} 不存在（{path.name}）"

    tables = sec.get("tables") or []
    assert len(tables) > 0, f"{chapter_key} 无表"

    for tbl in tables:
        name = tbl.get("name", "<unnamed>")
        cols = tbl.get("columns") or []
        assert len(cols) > 0, f"{chapter_key}/{name} columns 为空"
        # 首列必须 flat=True
        first_col = cols[0]
        assert first_col.get("flat") is True, (
            f"{chapter_key}/{name} 首列缺 flat:true（实际: {first_col}）"
        )


# ═══════════════════════════ Property 12: 所有 12 张表有非空 guidance ═══════════════════════════


@pytest.mark.parametrize("chapter_key", ALL_CHAPTER_KEYS)
def test_property_12_guidance_nonempty(chapter_key: str):
    """Property 12：每张表 guidance 非空。"""
    path, section_number = _CHAPTER_MAP[chapter_key]
    sec = _get_section(path, section_number)
    assert sec is not None, f"章节 {section_number} 不存在（{path.name}）"

    tables = sec.get("tables") or []
    assert len(tables) > 0, f"{chapter_key} 无表"

    for tbl in tables:
        name = tbl.get("name", "<unnamed>")
        guidance = tbl.get("guidance") or ""
        assert guidance.strip(), f"{chapter_key}/{name} guidance 为空"


# ═══════════════════════════ Property 13: G11/G13/G14 列键一致 ═══════════════════════════


# G11/G13/G14 所有变体的非标签列键一律为 current_amount / prior_amount
_CONSISTENT_AMOUNT_KEYS = ["current_amount", "prior_amount"]

#: G10 逐表（表名, 非标签列键）—— 与底稿 G10 两张披露 sheet、前端载荷 g10DisclosureSyncPayload.ts 一致。
#: 原守卫断言「本节每张表都是主表列」，钉住的正是脚本把主表列套给每张表的缺陷（R8.4 批 9b-2）。
_G10_FV_KEYS = ["fv_change_amount", "credit_risk_current", "credit_risk_cumulative"]
_G10_TABLE_KEYS: dict[str, list[tuple[str, list[str]]]] = {
    "g10_listed": [
        (FIX.G10_LISTED_MAIN_TABLE, ["begin_balance", "current_increase", "current_decrease", "end_balance"]),
        (FIX.G10_LISTED_DESIGNATED_TABLE, ["begin_balance", "end_balance", "designation_reason"]),
        (FIX.G10_LISTED_FV_TABLE, _G10_FV_KEYS),
    ],
    "g10_listed_derivative": [(FIX.G10_LISTED_DERIVATIVE_TABLE, ["end_balance", "prior_balance"])],
    "g10_soe": [
        (FIX.G10_SOE_MAIN_TABLE, ["end_fv", "begin_fv"]),
        (FIX.G10_SOE_FV_TABLE, _G10_FV_KEYS),
    ],
}


@pytest.mark.parametrize("chapter_key", [
    "g11_listed", "g11_soe", "g13_listed", "g13_soe", "g14_listed", "g14_soe",
])
def test_property_13_g11_g13_g14_column_keys_consistent(chapter_key: str):
    """Property 13：G11/G13/G14 各表金额列键一致为 current_amount/prior_amount。"""
    path, section_number = _CHAPTER_MAP[chapter_key]
    sec = _get_section(path, section_number)
    assert sec is not None, f"章节 {section_number} 不存在（{path.name}）"

    tables = sec.get("tables") or []
    for tbl in tables:
        name = tbl.get("name", "<unnamed>")
        cols = tbl.get("columns") or []
        # 排除首列标签列，取金额列 key
        amount_keys = [c.get("key") for c in cols[1:]]
        assert amount_keys == _CONSISTENT_AMOUNT_KEYS, (
            f"{chapter_key}/{name} 金额列键不一致：{amount_keys} ≠ {_CONSISTENT_AMOUNT_KEYS}"
        )


@pytest.mark.parametrize("chapter_key", sorted(_G10_TABLE_KEYS))
def test_property_13_g10_tables_follow_workpaper(chapter_key: str):
    """Property 13 补充：G10 逐表表名与列键按底稿（指定类明细、公允价值变动表不再套主表列）。"""
    path, section_number = _CHAPTER_MAP[chapter_key]
    sec = _get_section(path, section_number)
    assert sec is not None
    actual = [(t.get("name"), [c.get("key") for c in (t.get("columns") or [])[1:]]) for t in sec.get("tables") or []]
    assert actual == _G10_TABLE_KEYS[chapter_key]


def test_g10_main_rows_follow_workpaper():
    """主表行按底稿：两组「其中」各带父行（上市不再是 Word 的空「其中：」占位，国企补「衍生金融负债」与指定类「其他」）。"""
    for path, section_number, want in (
        (LISTED_PATH, "五、34", ["交易性金融负债", "其中：发行的交易性债券", "衍生金融负债", "其他",
                                 "指定为以公允价值计量且其变动计入当期损益的金融负债", "其中：债券", "其他", "合计"]),
        (SOE_PATH, "八、34", ["交易性金融负债", "其中：发行的交易性债券", "衍生金融负债", "其他",
                              "指定为以公允价值计量且其变动计入当期损益的金融负债", "其他", "合计"]),
    ):
        sec = _get_section(path, section_number)
        assert sec is not None
        assert [r.get("label") for r in sec["tables"][0]["rows"]] == want, section_number
        assert sec["tables"][0]["rows"][-1].get("is_total") is True


def test_g10_fv_table_names_keep_word_year_literal():
    """公允价值变动表名逐字取两版 Word（上市 2025 年 / 国企 202X 年）：表名是模板表标识，前端按常量推送、不随审计年度拼。"""
    assert "2025年" in FIX.G10_LISTED_FV_TABLE
    assert "202X年" in FIX.G10_SOE_FV_TABLE
    assert FIX.G10_LISTED_FV_TABLE.replace("2025年", "202X年") == FIX.G10_SOE_FV_TABLE


# ═══════════════════════════ 表数量锚点（反向自检防空转） ═══════════════════════════


_EXPECTED_TABLE_COUNTS = {
    "g10_listed": 3,
    "g10_listed_derivative": 1,
    "g10_soe": 2,
    "g11_listed": 2,
    "g11_soe": 1,
    "g13_listed": 2,
    "g13_soe": 1,
    "g14_listed": 1,
    "g14_soe": 1,
}


@pytest.mark.parametrize("chapter_key", ALL_CHAPTER_KEYS)
def test_table_count_anchor(chapter_key: str):
    """反向自检：各章节表数量与脚本预期一致（防守卫遍历空表列表空转）。"""
    path, section_number = _CHAPTER_MAP[chapter_key]
    sec = _get_section(path, section_number)
    assert sec is not None, f"章节 {section_number} 不存在（{path.name}）"
    actual_count = len(sec.get("tables") or [])
    expected = _EXPECTED_TABLE_COUNTS[chapter_key]
    assert actual_count == expected, (
        f"{chapter_key} 表数量漂移：实际 {actual_count} ≠ 预期 {expected}"
    )
