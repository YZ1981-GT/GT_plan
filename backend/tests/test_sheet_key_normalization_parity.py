"""前端↔后端 sheet 名归一一致性断言 —— 后端侧（spec formula-manager-closure · Task 1.3）。

验收判据（tasks.md Task 1.3）：
  「若前端本地归一，单测断言其结果与 normalize_sheet_key 对同一组 sheet 名
   （含带排序前缀「五、1 审定表D2-1」、全角空格、大小写敏感 wp_code）产出一致。」

一致性用一张 golden 对照表（``tests/fixtures/sheet_key_normalization_parity.json``）承接：
  - **后端侧**（本文件）：断言 ``normalize_sheet_key(input) == golden.expected``，即 golden 确实
    由后端单一真源产出、未被手改偏离真源。
  - **前端侧**（``audit-platform/frontend/src/components/formula/__tests__/
    sheetKeyNormalizationParity.spec.ts``）：断言 TS ``normalizeSheetKey(input) == golden.expected``。
  两侧同对一张 golden ⇒ 前端 TS 归一 == 后端 Python 归一（传递闭包）。

golden 由 backend 真源重算生成（见文件 _source/_note），禁手改值；本测试即其「未被手改」守卫。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.formula_management.stable_key import normalize_sheet_key

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sheet_key_normalization_parity.json"


def _load_pairs() -> list[dict]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    pairs = data.get("pairs")
    assert isinstance(pairs, list) and pairs, "golden 对照表为空 —— 判据抽不到值（防空转）"
    return pairs


def test_golden_fixture_covers_required_cases():
    """判据抽不到值防空转：golden 必须覆盖任务点名的三类 sheet 名。"""
    inputs = {p["input"] for p in _load_pairs()}
    assert "五、1 审定表D2-1" in inputs, "缺带排序前缀样本"
    assert any("\u3000" in i for i in inputs), "缺全角空格样本"
    assert "E1-1" in inputs and "e1-1" in inputs, "缺大小写敏感 wp_code 样本"


@pytest.mark.parametrize("pair", _load_pairs(), ids=lambda p: repr(p["input"]))
def test_backend_normalize_matches_golden(pair):
    """后端真源对每个 input 的归一结果 == golden.expected（golden 未偏离真源）。"""
    assert normalize_sheet_key(pair["input"]) == pair["expected"]


def test_mutation_tampered_expected_would_be_caught():
    """变异反证：若 golden 的某个 expected 被手改偏离真源，后端一致性断言必打红。

    这里在内存里篡改一条 expected（给带排序前缀的样本保留前缀），断言它 != 后端真源结果。
    反向断言：未篡改的真实 golden 全部与后端真源一致（未注入不命中）。
    """
    pairs = _load_pairs()
    target = next(p for p in pairs if p["input"] == "五、1 审定表D2-1")
    tampered_expected = "五、1 审定表D2-1"  # 偏离：未剥排序前缀
    assert normalize_sheet_key(target["input"]) != tampered_expected  # 篡改态必红
    assert target["expected"] == "审定表D2-1"  # golden 真值（未篡改）
    # 反向断言：真实 golden 全部一致
    for p in pairs:
        assert normalize_sheet_key(p["input"]) == p["expected"]
