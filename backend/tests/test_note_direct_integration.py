"""NoteDirectBinding 参数化集成测试：57 个批 D 科目全部能实例化 + note_rows 正确。

spec: formula-push-note-rollout-batch-d · Task 7
spec: formula-fetch-and-wp-generation-defect-closure R1 —— L7 其他非流动负债 / M8 一般风险准备没有标准科目
（口径单一来源不给兜底码；原映射表写的 2801 是 K5 预计负债、4301 是专项储备，推的是别的科目的数）：
两者改为「无科目」声明，不取试算表、不推附注主表，规则清单里也不得有它们的取数规则。
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.formula_push.bindings import get_binding, supported_wp_codes
from app.services.formula_push.bindings.note_direct import NoteDirectBinding
from app.services.formula_push.rules import load_rules

# ── 目标清单（现算自 wp_account_mapping，57 个批 D 科目） ─────────────────

_TARGET_CODES = [
    "D5",
    "F1", "F2", "F3", "F4",
    # G1~G10, H1~H10, I1~I5 已迁移到 BalanceAdjudicationBinding（批 C 审定表族）
    "G11", "G12", "G13", "G14",
    "J1", "J2",
    # K2~K7 已迁移到 BalanceAdjudicationBinding（批 C 审定表族）
    "K8", "K9", "K10", "K11", "K12", "K13",
    "L1", "L2", "L3", "L4", "L5", "L8",
    "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M9", "M10",
    "N1", "N2", "N4", "N5",
]
#: 没有标准科目的批 D 科目（R1）：binding 照常注册（底稿 / 附注页面仍能识别），但不取数、不推送
_NO_ACCOUNT_CODES = ["L7", "M8"]

# 规则清单（默认 binding_specs 自动获取）
_RULES = {r.rule_id: r for r in load_rules()}


# ── 1) 全部 57 科目实例化 ───────────────────────────────────────────────────


@pytest.mark.parametrize("code", _TARGET_CODES)
def test_binding_instantiation(code):
    """每个批 D 科目都能通过 get_binding 获取 NoteDirectBinding 实例。"""
    binding = get_binding(code)
    assert isinstance(binding, NoteDirectBinding)
    assert binding.wp_code == code
    assert len(binding.account_prefixes) >= 1
    assert f"{code.lower()}_note_main" in binding.derivations


@pytest.mark.parametrize("code", _NO_ACCOUNT_CODES)
def test_no_account_binding_declares_reason_and_pushes_nothing(code):
    binding = get_binding(code)
    assert isinstance(binding, NoteDirectBinding) and binding.wp_code == code
    assert binding.account_prefixes == ()
    assert binding.no_account_reason.strip(), f"{code} 没有科目却没写原因"
    assert binding.derivations == frozenset(), "没有科目就没有附注主表推送"
    assert [r.rule_id for r in _RULES.values() if r.wp_code == code] == [], f"{code} 不得有取数 / 推送规则"


# ── 2) 每科目都有两条规则（底稿锚点 + 附注推送） ───────────────────────────


@pytest.mark.parametrize("code", _TARGET_CODES)
def test_rules_exist(code):
    """每个批 D 科目至少有底稿锚点规则和附注推送规则。"""
    code_rules = [r for r in _RULES.values() if r.wp_code == code]
    stages = {r.stage for r in code_rules}
    assert "source" in stages, f"{code} 缺少底稿锚点规则（stage=source）"
    assert "note" in stages, f"{code} 缺少附注推送规则（stage=note）"


# ── 3) note_rows 格式校验（代表性科目） ─────────────────────────────────────


def _make_tb(codes, *, ending=100000.0, opening=80000.0, occurrence=20000.0):
    """构造 TB 数据。"""
    return {
        c: {k: Decimal(str(v)) for k, v in {
            "期末余额": ending, "年初余额": opening, "本期发生额": occurrence,
        }.items()}
        for c in codes
    }


_REPRESENTATIVE_CODES = [
    # 非损益单科目
    ("G1", False),
    ("L1", False),
    ("M2", False),
    ("N1", False),
    # 损益类单科目
    ("K8", True),
    ("G11", True),
    ("N5", True),
    # 多科目
    ("F2", False),
    ("D4", True),  # D4 有两个科目码 6001+6051，损益类
]


@pytest.mark.parametrize("code,is_income", _REPRESENTATIVE_CODES)
def test_note_rows_format(code, is_income):
    """代表性科目的 note_rows 返回正确格式。"""
    binding = get_binding(code)
    binding._last_tb_data = _make_tb(binding.account_prefixes)
    rule = SimpleNamespace(rule_id=f"{code}.note.main", target=SimpleNamespace(domain="note"))
    rows = binding.note_rows({}, "listed", rule)
    assert len(rows) >= 1
    for r in rows:
        assert "key" in r and "label" in r and "ending" in r and "opening" in r
        assert "ending_resolved" in r and "opening_resolved" in r
        assert "is_total" in r and "is_memo" in r
        assert isinstance(r["ending"], float)
        assert isinstance(r["opening"], float)
    # 损益类科目取本期发生额
    if is_income and len(binding.account_prefixes) == 1:
        assert rows[0]["ending"] == 20000.0, "损益类应取 '本期发生额'"
    elif not is_income and len(binding.account_prefixes) == 1:
        assert rows[0]["ending"] == 100000.0, "非损益类应取 '期末余额'"
    # 多科目有合计行
    if len(binding.account_prefixes) > 1:
        assert rows[-1]["is_total"] is True


# ── 4) 共享章节测试 ─────────────────────────────────────────────────────────


def test_shared_sections():
    """G2 和 G3 共享 listed=五、8 / soe=八、9；各自 note_rows 独立。"""
    g2 = get_binding("G2")
    g3 = get_binding("G3")
    g2._last_tb_data = _make_tb(g2.account_prefixes, ending=50000.0)
    g3._last_tb_data = _make_tb(g3.account_prefixes, ending=30000.0)
    rule2 = SimpleNamespace(rule_id="G2.note.main", target=SimpleNamespace(domain="note"))
    rule3 = SimpleNamespace(rule_id="G3.note.main", target=SimpleNamespace(domain="note"))
    rows2 = g2.note_rows({}, "listed", rule2)
    rows3 = g3.note_rows({}, "listed", rule3)
    assert len(rows2) >= 1 and len(rows3) >= 1
    assert rows2[0]["ending"] == 50000.0
    assert rows3[0]["ending"] == 30000.0
    assert rows2[0]["key"] != rows3[0]["key"], "共享章节的行 key 必须不同"


# ── 5) 注册表总数守卫 ──────────────────────────────────────────────────────


def test_registry_count():
    """注册表至少 77 个码（20 原有 + 57 批 D）。"""
    codes = supported_wp_codes()
    assert len(codes) >= 77, f"注册表应至少 77 个码，实际 {len(codes)}"


# ── 6) 规则清单总数守卫 ────────────────────────────────────────────────────


def test_rules_count():
    """规则清单至少 176 条且校验通过。"""
    assert len(_RULES) >= 176, f"规则应至少 176 条，实际 {len(_RULES)}"
