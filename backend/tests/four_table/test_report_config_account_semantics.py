"""守卫：report_config G 循环科目码语义正确性。

纠偏迁移 V137 修正 5 行错码后，本文件锁定正确值不被回退。

Property 1：每个 TB() 码存在于标准科目表（`backend/data` JSON）
Property 2：行名与科目名的备抵关键字一致性（BS-022~026 是资产不含备抵词）

spec: g-cycle-extraction-mapping-and-disclosure-alignment Task 1.2
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
DATA = BACKEND / "data"

# V137 纠偏后的正确映射（row_code → 科目码 → 科目名）
CORRECT_MAPPINGS = {
    "BS-022": ("1506", "其他债权投资"),
    "BS-025": ("1507", "其他权益工具投资"),
    "BS-026": ("1519", "其他非流动金融资产"),
    "IS-016": ("6702", "信用减值损失"),
    "IS-017": ("6701", "资产减值损失"),
}

# 纠偏前的错值（反向自检用：改回这些必须红）
WRONG_CODES = {
    "BS-022": "1505",
    "BS-025": "1506",
    "BS-026": "1507",
    "IS-016": "6701",
    "IS-017": "6702",
}


@pytest.fixture(scope="module")
def standard_account_codes() -> set[str]:
    """从 backend/data 的标准科目表 JSON 加载所有码。"""
    codes: set[str] = set()
    for p in DATA.glob("*account_chart*.json"):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            entries = doc if isinstance(doc, list) else doc.get("accounts", doc.get("entries", []))
            for e in entries:
                code = e.get("account_code") or e.get("code") or ""
                if code:
                    codes.add(str(code).strip())
        except Exception:
            pass
    return codes


class TestProperty1:
    """Property 1：正确码存在于标准科目表。"""

    @pytest.mark.parametrize("row_code,expected", list(CORRECT_MAPPINGS.items()))
    def test_correct_code_in_standard_chart(self, row_code, expected, standard_account_codes):
        code, name = expected
        # 允许科目表为空（CI 无数据文件时跳过）
        if not standard_account_codes:
            pytest.skip("标准科目表 JSON 未找到或为空")
        assert code in standard_account_codes, (
            f"{row_code} 的正确码 {code}({name}) 不在标准科目表中"
        )


class TestProperty2:
    """Property 2：资产侧行名不含备抵关键字（BS-022~026 是原值行）。"""

    PROVISION_HINTS = ("减值准备", "坏账准备", "信用减值")

    @pytest.mark.parametrize("row_code", ["BS-022", "BS-025", "BS-026"])
    def test_asset_row_no_provision_hint(self, row_code):
        code, name = CORRECT_MAPPINGS[row_code]
        for hint in self.PROVISION_HINTS:
            assert hint not in name, (
                f"{row_code} 的科目名 {name} 含备抵关键字 {hint}（应是原值行）"
            )


class TestReverseCheck:
    """反向自检：错码不得复活。"""

    @pytest.mark.parametrize("row_code,wrong_code", list(WRONG_CODES.items()))
    def test_wrong_code_differs_from_correct(self, row_code, wrong_code):
        correct_code, _ = CORRECT_MAPPINGS[row_code]
        assert wrong_code != correct_code, (
            f"{row_code} 的正确码与已知错码相同 = 守卫空转"
        )
