"""D 类循环 Tier A 预设的**科目码合法性**守卫（Property 1）。

背景（2026-08-01 实证）：预设里的科目码从来没有被任何测试校验过 —— 既有测试只测
「预设能加载 / 锚点合法 / 函数受支持」，**从不校验这个码是不是真科目、是不是该循环的科目**。
后果实测两例：

- **D6 合同资产的预设写 `TB('1402')`**，而 `1402` 是**在途物资**（存货类）；
  `report_config` 的 BS-011 合同资产四准则一律 `TB('1141')` → 合同资产审定表的
  「试算平衡表数」取的是存货科目，取数恒错/恒空。
- **D5 应收款项融资的预设写 `TB('1124')`**，该码在 `account_chart` 里**完全不存在**
  （报表行 BS-007 也引它）→ 取数恒空且无人察觉（同 N1 的 `1812` 缺陷）。

裁决者：`backend/data/standard_account_chart*.json`（标准科目表种子）+ `report_config`
的报表行公式。本守卫只依赖仓库内文件（不连库），故可在 CI 跑。

spec: .kiro/specs/d-cycle-extraction-chain-completion/ Task 1.1
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
DATA_DIR = _BACKEND / "data"
PRESETS_PATH = DATA_DIR / "d_cycle_extraction" / "d_cycle_extraction_presets.json"

# D 类循环 → 该循环的报表行（`report_config.row_code`，DB 实证 2026-08-01）
D_CYCLE_REPORT_ROW = {
    "D1": "BS-005",  # 应收票据
    "D2": "BS-006",  # 应收账款
    "D3": "BS-046",  # 预收款项
    "D5": "BS-007",  # 应收款项融资
    "D6": "BS-011",  # 合同资产
    "D7": "BS-047",  # 合同负债
}

# 各报表行 soe_standalone 公式引用的标准码（DB 实证；listed 侧差异见 spec Notes）
D_CYCLE_EXPECTED_CODES = {
    "D1": {"1121", "1231-01"},
    "D2": {"1122", "1231-02"},
    "D3": {"2203"},
    "D5": {"1124"},  # 🔴 该码在标准科目表不存在 —— 报表配置自身的缺陷，见 test_d5
    "D6": {"1141"},
    "D7": {"2205"},
}

_CODE_RE = re.compile(r"(?:TB|SUM_TB|TB_AUX)\(\s*'([^']+)'")


# ─── 标准科目表 ───────────────────────────────────────────────────────────────

def _load_standard_codes() -> set[str]:
    """标准科目表全部科目码（含带横杠的细分码，如 `1231-01`）。"""
    codes: set[str] = set()
    for path in sorted(DATA_DIR.glob("*account_chart*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 非科目表 JSON 直接跳过
            continue
        items = doc if isinstance(doc, list) else (
            doc.get("accounts") or doc.get("items") or doc.get("data") or []
        )
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            code = it.get("account_code") or it.get("code")
            if code:
                codes.add(str(code).strip())
    return codes


STANDARD_CODES = _load_standard_codes()


def test_standard_chart_loaded() -> None:
    """反向自检：科目表读空时下面所有断言都会退化为恒真。"""
    assert len(STANDARD_CODES) > 100, f"标准科目表只读到 {len(STANDARD_CODES)} 个码"
    for known in ("1121", "1122", "1141", "1231-01", "1231-02", "2203", "2205"):
        assert known in STANDARD_CODES, f"标准科目表缺已实证存在的码 {known}"
    # 反向自检：不存在的码必须判否（否则 `in` 判定失效）
    assert "9999-ZZ" not in STANDARD_CODES


# ─── 预设 ─────────────────────────────────────────────────────────────────────

def _presets() -> dict[str, list[dict]]:
    doc = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in doc.items() if isinstance(v, list)}


PRESETS = _presets()
D_ENTRIES = [
    (wp, e) for wp, entries in sorted(PRESETS.items()) if wp.startswith("D")
    for e in entries
]
D_IDS = [f"{wp}:{e.get('anchor')}" for wp, e in D_ENTRIES]


def test_d_cycle_presets_present() -> None:
    """反向自检：预设读空时逐条断言会全部跳过。"""
    assert D_ENTRIES, "未读到任何 D 类预设（文件结构变了？）"
    assert {wp for wp, _ in D_ENTRIES} >= {"D1", "D2", "D6"}


@pytest.mark.parametrize(("wp", "entry"), D_ENTRIES, ids=D_IDS)
def test_preset_codes_exist_in_standard_chart(wp: str, entry: dict) -> None:
    """Property 1：预设引用的每个科目码都必须是标准科目表里的真科目。"""
    codes = _CODE_RE.findall(str(entry.get("expression") or ""))
    assert codes, f"{wp} 预设 {entry.get('anchor')} 的 expression 未解析出科目码"
    for code in codes:
        if "~" in code:  # 区间口径（SUM_TB('1401~1499')）逐端点校验
            for endpoint in code.split("~"):
                assert endpoint.strip() in STANDARD_CODES, (
                    f"{wp} 引用的区间端点 {endpoint} 不在标准科目表"
                )
            continue
        assert code in STANDARD_CODES, (
            f"{wp} 预设 {entry.get('anchor')} 引用了标准科目表中不存在的科目码 {code}"
        )


@pytest.mark.parametrize(("wp", "entry"), D_ENTRIES, ids=D_IDS)
def test_preset_codes_belong_to_own_cycle(wp: str, entry: dict) -> None:
    """Property 1：预设科目码必须属于**本循环报表行**引用的科目集合。

    这是 D6 `1402`（在途物资，属存货循环）被抓出的那条断言：码是真科目，
    但不是合同资产的科目。
    """
    expected = D_CYCLE_EXPECTED_CODES.get(wp)
    if expected is None:
        pytest.skip(f"{wp} 未登记报表行科目集合")
    codes = {c for c in _CODE_RE.findall(str(entry.get("expression") or "")) if "~" not in c}
    unexpected = codes - expected
    assert not unexpected, (
        f"{wp}（报表行 {D_CYCLE_REPORT_ROW[wp]}）预设引用了不属于本循环的科目 "
        f"{sorted(unexpected)}；本循环科目集合 = {sorted(expected)}"
    )


def test_d2_preset_is_net_of_allowance() -> None:
    """D2 审定表比的是「三、应收账款净值」合计（源模板 A27 / A22=A8−A15）
    → TB 侧必须是净额，取原值会产生恰好等于坏账准备的假差异（D1 同款，已实测）。"""
    entry = next(e for e in PRESETS["D2"] if e["anchor"] == "D2-adj-tb-amount")
    expr = str(entry["expression"])
    assert "TB('1122'" in expr, expr
    assert "- TB('1231-02'" in expr, (
        f"D2 预设仍是原值口径：{expr}（report_config 的 BS-006 soe_standalone 公式为 "
        "TB('1122','期末余额') - TB('1231-02','期末余额')）"
    )
    assert "净额" in str(entry.get("description") or ""), "description 须写明净额口径与依据"


def test_d6_preset_points_to_contract_asset() -> None:
    """D6 = 合同资产 `1141`；`1402` 是在途物资（存货类），取数会恒错。"""
    entry = next(e for e in PRESETS["D6"] if e["anchor"] == "D6-1-tb-amount")
    expr = str(entry["expression"])
    assert "TB('1141'" in expr, f"D6 预设未指向合同资产 1141：{expr}"
    assert "1402" not in expr, f"D6 预设仍引用在途物资 1402：{expr}"


def test_d6_impairment_codes_are_real_allowance_accounts() -> None:
    """D6 减值准备 resolver 的科目码必须是**贷方备抵**科目，不能是资产科目的子科目。

    历史两版都错：`['140201','1402.01']`（1402 = 在途物资，连科目族都错）→
    `['114101','1141.01']`（把借方资产科目 1141 的子科目当备抵）。
    标准科目表实证的真值：`1142 合同资产减值准备`（credit）/
    `1231-05 坏账准备-合同资产`（credit）。
    """
    from app.services.auto_data_resolvers._d6_contract_assets import (
        _IMPAIRMENT_ACCOUNT_CODES,
    )

    assert _IMPAIRMENT_ACCOUNT_CODES, "减值准备科目码清单不得为空"
    for code in _IMPAIRMENT_ACCOUNT_CODES:
        assert code in STANDARD_CODES, f"D6 减值准备引用了不存在的科目码 {code}"
    # 不得再出现「资产科目自身的子科目」或错科目族
    joined = " ".join(_IMPAIRMENT_ACCOUNT_CODES)
    for wrong in ("1402", "114101", "1141.01", "1403"):
        assert wrong not in joined, f"D6 减值准备科目码残留误用值 {wrong}"


def test_d5_nonexistent_code_is_not_silently_kept() -> None:
    """D5 应收款项融资：`1124` 在标准科目表不存在（报表行 BS-007 亦引它）。

    「应收款项融资」是**报表项目**（以公允价值计量且其变动计入其他综合收益的
    应收票据/应收账款），没有独立一级科目 → 无法从四表库干净取数。
    故 D5 SHALL NOT 保留一条恒空的 `TB('1124')` 预设（Requirement 4）。
    """
    assert "1124" not in STANDARD_CODES, (
        "1124 竟在标准科目表中 —— 本判定需重新裁决（可能新增了该科目）"
    )
    entries = PRESETS.get("D5") or []
    offenders = [e for e in entries if "1124" in str(e.get("expression") or "")]
    assert not offenders, (
        "D5 预设仍引用不存在的科目 1124（恒空取数）：Requirement 4 要求"
        "改用可实证科目或移除该预设并在溯源登记写明原因"
    )
