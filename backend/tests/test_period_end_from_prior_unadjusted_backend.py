# -*- coding: utf-8 -*-
"""后端复算的期末未审 / 期末余额按模板从「期初未审」起算（spec oo-writeback-template-parity-closure R2）。

前端明细表族已按模板改成期初未审起算（守卫 `periodEndFromPriorUnadjusted.spec.ts` + 模板公式对拍）；
后端另有四处照抄了旧口径（期初审定起算），有期初调整的行与表单 / OnlyOffice 差一个期初调整额：

* D6-2 / D6-3 / D7-2 导入（``_parse_row`` 复算派生列后整表写库，预填锚点直接读写库的 endUnadjusted）；
* D1 附注公式推送（``tier_a._d1_note_rows_from_entries`` 复算分类明细的期末余额，docstring 自称与前端同口径）。

每例都带非零期初调整，旧口径必红（判据不靠随机样本碰运气）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.routers.wp_render_strategies import _d6_import_export as d6  # noqa: E402
from app.routers.wp_render_strategies import _d7_import_export as d7  # noqa: E402
from app.services.formula_push.bindings.tier_a import _d1_note_rows_from_entries  # noqa: E402


def _row(headers: list[str], values: dict[str, object]) -> tuple:
    missing = [h for h in values if h not in headers]
    assert not missing, f"表头里没有 {missing} ⇒ 判据会读成 0、变成空转"
    return tuple(values.get(h) for h in headers)


def test_d6_2_import_end_unadjusted_from_prior_unadjusted() -> None:
    """模板 D6-2 Q = G + O − P（G 期初未审）。"""
    headers = d6._SHEET_HEADERS["D6-2"]
    parsed = d6._parse_row("D6-2", _row(headers, {
        "期初未审数": 1000, "期初AJE": 50, "期初RJE": 25,
        "借方发生": 300, "贷方发生": 200, "期末AJE": 7, "期末RJE": 3,
    }), headers)
    assert parsed["priorAudited"] == pytest.approx(1075)
    assert parsed["endUnadjusted"] == pytest.approx(1100)  # 1000 + 300 − 200（旧口径 1175）
    assert parsed["endAudited"] == pytest.approx(1110)


def test_d6_3_import_end_unadjusted_from_prior_unadjusted() -> None:
    """模板 D6-3 K = B + SUM(F:G) − SUM(H:J)（B 期初未审）。"""
    headers = d6._SHEET_HEADERS["D6-3"]
    parsed = d6._parse_row("D6-3", _row(headers, {
        "项目": "甲合同", "分类": "group", "期初未审余额": 500, "期初AJE": 40, "期初RJE": 10,
        "本期计提": 120, "本期其他增加": 30, "本期转回": 20, "本期核销": 15, "本期其他减少": 5,
        "期末AJE": 6, "期末RJE": 4,
    }), headers)
    assert parsed["category"] == "group"
    assert parsed["priorAudited"] == pytest.approx(550)
    assert parsed["endUnadjusted"] == pytest.approx(610)  # 500 + 150 − 40（旧口径 660）
    assert parsed["endAudited"] == pytest.approx(620)


def test_d7_2_import_end_balance_from_prior_unadjusted() -> None:
    """模板 D7-2 P = F − N + O（F 期初未审；贷方科目）。"""
    headers = d7._SHEET_HEADERS["D7-2"]
    parsed = d7._parse_row("D7-2", _row(headers, {
        "期初未审数": 1000, "期初AJE": 50, "期初RJE": 25,
        "借方发生": 200, "贷方发生": 500, "重分类调整": 10, "期末AJE": 5, "期末RJE": 3,
    }), headers)
    assert parsed["priorAudited"] == pytest.approx(1075)
    assert parsed["endBalance"] == pytest.approx(1300)  # 1000 − 200 + 500（旧口径 1375）
    assert parsed["endUnadjusted"] == pytest.approx(1310)
    assert parsed["endAudited"] == pytest.approx(1318)


def test_d1_note_push_end_balance_from_prior_unadjusted() -> None:
    """D1 附注推送：分类明细期末余额 = 期初未审 + 增加 − 减少 + 期末调整（模板 D1-2 H = B + F − G）。"""
    cat = [{
        "rowId": "fixed-bank", "category": "银行承兑汇票",
        "priorUnadjusted": 500000, "priorAje": 10000, "priorRje": 5000,
        "currentIncrease": 300000, "currentDecrease": 100000,
        "currentAje": 20000, "currentRje": 10000,
    }]
    rows = _d1_note_rows_from_entries({"D1-cat-rows": json.dumps(cat, ensure_ascii=False)})
    assert len(rows) == 1
    assert rows[0]["prior_balance"] == pytest.approx(515000)
    # 500000 + 300000 − 100000 = 700000；+ 20000 + 10000 = 730000（旧口径 745000）
    assert rows[0]["end_balance"] == pytest.approx(730000)
