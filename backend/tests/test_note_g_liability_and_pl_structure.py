"""守卫：G10/G11/G13/G14 附注披露表 columns 与 guidance 结构完整。

锁定 `fix_note_g_liability_and_pl_structure.py` 的对齐结果，防 md 重建 / 并发会话回退：

- 幂等脚本 --check 返回 0 项欠账（exit code 0）；
- 所有 12 张表 columns 非空、首列 flat=True；
- 所有 12 张表 guidance 非空；
- G11/G13/G14 列键一致（current_amount / prior_amount），G10 按变体区分。

章节落点：
  G10: listed 五、34 / soe 八、34
  G11: listed 五、69 / soe 八、70
  G13: listed 三、公允价值变动收益 / soe 八、72
  G14: listed 三、信用减值损失 / soe 八、73

spec: g-cycle-extraction-mapping-and-disclosure-alignment
"""
from __future__ import annotations

import importlib.util
import json
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
    "g10_soe": (SOE_PATH, "八、34"),
    "g11_listed": (LISTED_PATH, "五、69"),
    "g11_soe": (SOE_PATH, "八、70"),
    "g13_listed": (LISTED_PATH, "三、公允价值变动收益"),
    "g13_soe": (SOE_PATH, "八、72"),
    "g14_listed": (LISTED_PATH, "三、信用减值损失"),
    "g14_soe": (SOE_PATH, "八、73"),
}


# ═══════════════════════════ 核心守卫：--check 返回 0 项欠账 ═══════════════════════════


def test_check_returns_zero_outstanding():
    """幂等脚本 --check 应返回 0 项欠账。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True, text=True, cwd=str(BACKEND),
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

# G10 按变体区分
_G10_LISTED_AMOUNT_KEYS = ["begin_balance", "current_increase", "current_decrease", "end_balance"]
_G10_SOE_AMOUNT_KEYS = ["end_fv", "begin_fv"]


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


def test_property_13_g10_listed_column_keys():
    """Property 13 补充：G10 上市主表列键为 begin_balance/current_increase/current_decrease/end_balance。"""
    sec = _get_section(LISTED_PATH, "五、34")
    assert sec is not None
    tables = sec.get("tables") or []
    for tbl in tables:
        cols = tbl.get("columns") or []
        amount_keys = [c.get("key") for c in cols[1:]]
        assert amount_keys == _G10_LISTED_AMOUNT_KEYS, (
            f"G10 listed/{tbl.get('name')} 金额列键不一致：{amount_keys}"
        )


def test_property_13_g10_soe_column_keys():
    """Property 13 补充：G10 国企主表列键为 end_fv/begin_fv。"""
    sec = _get_section(SOE_PATH, "八、34")
    assert sec is not None
    tables = sec.get("tables") or []
    for tbl in tables:
        cols = tbl.get("columns") or []
        amount_keys = [c.get("key") for c in cols[1:]]
        assert amount_keys == _G10_SOE_AMOUNT_KEYS, (
            f"G10 soe/{tbl.get('name')} 金额列键不一致：{amount_keys}"
        )


# ═══════════════════════════ 表数量锚点（反向自检防空转） ═══════════════════════════


_EXPECTED_TABLE_COUNTS = {
    "g10_listed": 3,
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
