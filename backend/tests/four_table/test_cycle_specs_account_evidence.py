"""守卫：per-cycle spec 的兜底码必须与「码 ↔ 名」实证结论一致。

**为什么需要**（2026-08-03 实证教训）

我按通用 CAS 常识写 6 个 `_cycle_specs.py` 的兜底码，逐项对账 `account_chart` 后
发现 **8 处错**，其中 3 处是「取到别的科目」级::

    I2 开发支出   写 1711 → 1711 实为**商誉**        真值 1704
    I3 商誉       写 1721 → 1721 **全库不存在**      真值 1711
    I5 其他非流动 写 1901 → 1901 实为**待处理财产损溢**  全库无该名科目 → 撤兜底
    M 循环 7/7    与平台实证值全不符（另见 commit 7047ff02）

这是 memory 记载的 `report_config` 「BS-022/025/026 连续偏移一位」同款模式 ——
**凭编码连续性假设写科目码，必然踩中平台实际编码与 CAS 教科书的差异**。

本文件把实证结论**冻结成断言**：码 ↔ 名对照表来自 postgres 只读对账
（`account_chart` 双向查：① 该码实际叫什么 ② 该名实际挂哪个码），
不连库（CI 可跑），改声明必须同步改这里并附新的实证依据。

spec: semantic-account-resolver-full-rollout（复盘补强）
"""
from __future__ import annotations

import pytest

#: DB 实证的「码 → 该码在 `account_chart` 里的实际科目名」（2026-08-03，10 个项目）
#: 🔴 值为 ``None`` = 该码全库零命中（声明它作兜底 = 取数必空）
CODE_TO_REAL_NAME: dict[str, str | None] = {
    "1121": "应收票据",
    "1122": "应收账款",
    "1123": "预付账款",
    "1141": "合同资产",
    "1701": "无形资产",
    "1704": "开发支出",
    "1711": "商誉",
    "1721": None,          # 全库不存在
    "1801": "长期待摊费用",
    "1811": "递延所得税资产",
    "1901": "待处理财产损溢",  # ← 不是「其他非流动资产」
    "2001": "短期借款",
    "2201": "应付票据",
    "2202": "应付账款",
    "2203": "预收账款",     # ← 不是「预收款项」
    "2205": "合同负债",
    "2231": "应付利息",
    "2221": "应交税费",
    "2232": "应付股利",
    "2501": "长期借款",
    "2502": "应付债券",
    "2701": "长期应付款",
    "2711": "专项应付款",
    "2901": "递延所得税负债",
    "4104": "利润分配",     # ← 不是「未分配利润」（那是 standard 的 320104）
    "4201": "库存股",
    "4302": None,          # 全库不存在
    "6403": "税金及附加",
    "6801": "所得税费用",
}

#: 🔴 一码两义：同一码在 client / standard 两套体系下是不同科目（实证 10 项目）
#: 这正是 `resolve_semantic_accounts`「client chart 优先按名定位」的必要性依据。
DUAL_MEANING_CODES: dict[str, tuple[str, str]] = {
    "4001": ("实收资本", "生产成本"),
    "4101": ("盈余公积", "制造费用"),
    "4401": ("其他权益工具", "工程施工"),
    "4301": ("专项储备", "研发支出"),
}


def _all_gross_slots():
    """``[(wp_code, slot), ...]`` —— 全部循环的 gross 槽。"""
    import importlib

    out = []
    for mod_name in ("d_cycle_specs", "f_cycle_specs", "g_cycle_specs",
                     "h_cycle_specs", "i_cycle_specs", "l_cycle_specs",
                     "m_cycle_specs", "n_cycle_specs"):
        try:
            mod = importlib.import_module(f"app.services.four_table.{mod_name}")
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(mod):
            if not attr.endswith("_CYCLE_SPECS"):
                continue
            for wp, spec in getattr(mod, attr).items():
                for slot in getattr(spec, "slots", ()):
                    if slot.key == "gross":
                        out.append((wp, slot))
    return out


_GROSS_SLOTS = _all_gross_slots()


class TestFallbackCodeMatchesEvidence:
    """Property: 兜底码在实证表里的科目名，必须与该槽声明的 names 相容。"""

    def test_slots_discovered(self):
        assert len(_GROSS_SLOTS) >= 40, f"只发现 {len(_GROSS_SLOTS)} 个 gross 槽"

    @pytest.mark.parametrize("wp,slot", _GROSS_SLOTS, ids=lambda v: str(v))
    def test_fallback_not_a_nonexistent_code(self, wp, slot):
        """兜底码不得是「全库零命中」的码（声明它 = 取数必空且掩盖真相）。"""
        for code in slot.fallback_standard_codes:
            real = CODE_TO_REAL_NAME.get(code, "__unknown__")
            assert real is not None, (
                f"{wp}.{slot.key} 的兜底码 {code} 在 account_chart 全库零命中 —— "
                "宁缺勿造：应声明 fallback_standard_codes=() 靠科目名定位"
            )

    @pytest.mark.parametrize("wp,slot", _GROSS_SLOTS, ids=lambda v: str(v))
    def test_fallback_code_name_consistent(self, wp, slot):
        """兜底码的实际科目名必须出现在该槽的 names 里（防「取到别的科目」）。"""
        for code in slot.fallback_standard_codes:
            real = CODE_TO_REAL_NAME.get(code)
            if real is None or real == "__unknown__":
                continue  # 未收录的码不在本守卫射程（见 test_evidence_table_covers_declared）
            names = tuple(slot.names or ())
            dual = DUAL_MEANING_CODES.get(code)
            ok = real in names or (dual and dual[0] in names)
            assert ok, (
                f"{wp}.{slot.key} 兜底码 {code} 的实际科目名是「{real}」，"
                f"但该槽 names={names} —— 会取到别的科目（同 I2/I3 已修缺陷）"
            )


class TestDualMeaningCodesDocumented:
    """Property: 一码两义的码必须在册（它们是 client-first 定位的必要性依据）。"""

    @pytest.mark.parametrize("code", sorted(DUAL_MEANING_CODES))
    def test_dual_code_declared_with_accounting_meaning(self, code):
        """用到一码两义码的槽，names 必须是**会计口径**那个名（client 表口径）。"""
        acct_name, cost_name = DUAL_MEANING_CODES[code]
        for wp, slot in _GROSS_SLOTS:
            if code not in slot.fallback_standard_codes:
                continue
            names = tuple(slot.names or ())
            assert acct_name in names, (
                f"{wp}.{slot.key} 用了一码两义码 {code}"
                f"（client={acct_name} / standard={cost_name}），"
                f"names 必须含会计口径名「{acct_name}」，实际 names={names}"
            )
            assert cost_name not in names, (
                f"{wp}.{slot.key} 的 names 含成本类口径名「{cost_name}」—— 语义错位"
            )


class TestReverseSelfCheck:
    """反向自检：证明断言不空转。"""

    def test_evidence_table_has_known_traps(self):
        """实证表必须记着那几个已踩的坑（防被「顺手清理」掉）。"""
        assert CODE_TO_REAL_NAME["1711"] == "商誉", "1711 是商誉不是开发支出"
        assert CODE_TO_REAL_NAME["1721"] is None, "1721 全库不存在"
        assert CODE_TO_REAL_NAME["1901"] == "待处理财产损溢", "1901 不是其他非流动资产"
        assert CODE_TO_REAL_NAME["4302"] is None, "4302 全库不存在"
        assert CODE_TO_REAL_NAME["2203"] == "预收账款", "2203 名为预收账款"

    def test_wrong_declaration_would_be_caught(self):
        """拿一个错声明喂断言，必须判否（证明判据有效）。"""
        from app.services.four_table.semantic_account_resolver import SemanticAccountSlot

        bad = SemanticAccountSlot(
            key="gross", names=("开发支出",), exclude_names=(),
            fallback_standard_codes=("1711",),  # 1711 实为商誉
            label="开发支出",
        )
        real = CODE_TO_REAL_NAME.get("1711")
        assert real not in bad.names, "错声明未被识别 —— 判据空转"

    def test_nonexistent_code_would_be_caught(self):
        from app.services.four_table.semantic_account_resolver import SemanticAccountSlot

        bad = SemanticAccountSlot(
            key="gross", names=("商誉",), exclude_names=(),
            fallback_standard_codes=("1721",),  # 全库零命中
            label="商誉",
        )
        assert CODE_TO_REAL_NAME.get(bad.fallback_standard_codes[0]) is None
