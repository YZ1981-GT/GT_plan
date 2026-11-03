"""旧编码体系损益科目 → 新准则 6xxx 对照（科目自动映射用）。

平台利润表公式只读新准则 6xxx（营业收入 = TB('6001') + TB('6051')），四套报表配置无一引用 5xxx。
客户若用《企业会计制度》（2001）或《小企业会计准则》（2013）的 5xxx 损益编码，按编码匹配会落到
标准科目表里同号的 5xxx ⇒ 利润表全 0；两套 5xxx 同码不同义，还会错位（5501 营业费用 → 5403 营业税金及附加）。

判定只看编码不看名称：真库客户科目名会整体错位（5101 存成「\\利润分配」），名称不可信。
spec: legacy-pl-account-crosswalk-mapping
"""

from __future__ import annotations

from collections.abc import Iterable

ENTERPRISE_SYSTEM_2001 = "enterprise_system_2001"
SMALL_ENTERPRISE_2013 = "small_enterprise_2013"

#: 一级损益码 → 新准则码
PL_CROSSWALKS: dict[str, dict[str, str]] = {
    # 《企业会计制度》（2001）
    ENTERPRISE_SYSTEM_2001: {
        "5101": "6001",  # 主营业务收入
        "5102": "6051",  # 其他业务收入
        "5201": "6111",  # 投资收益
        "5203": "6117",  # 补贴收入 → 其他收益
        "5301": "6301",  # 营业外收入
        "5401": "6401",  # 主营业务成本
        "5402": "6403",  # 主营业务税金及附加 → 税金及附加
        "5405": "6402",  # 其他业务支出 → 其他业务成本
        "5501": "6601",  # 营业费用 → 销售费用
        "5502": "6602",  # 管理费用
        "5503": "6603",  # 财务费用
        "5601": "6711",  # 营业外支出
        "5701": "6801",  # 所得税 → 所得税费用
        "5801": "6901",  # 以前年度损益调整
    },
    # 《小企业会计准则》（2013）
    SMALL_ENTERPRISE_2013: {
        "5001": "6001",  # 主营业务收入
        "5051": "6051",  # 其他业务收入
        "5111": "6111",  # 投资收益
        "5301": "6301",  # 营业外收入
        "5401": "6401",  # 主营业务成本
        "5402": "6402",  # 其他业务成本
        "5403": "6403",  # 税金及附加
        "5601": "6601",  # 销售费用
        "5602": "6602",  # 管理费用
        "5603": "6603",  # 财务费用
        "5711": "6711",  # 营业外支出
        "5801": "6801",  # 所得税费用
    },
}

#: 判定用特征码：只取两套体系里意思不同（或另一套没有）的码。
#: 5101 不在内 —— 新准则账套的 5101 是制造费用；5001 在小企业一侧，新准则只有成本类时最多命中这 1 个。
_SIGNATURE_CODES: dict[str, frozenset[str]] = {
    ENTERPRISE_SYSTEM_2001: frozenset({"5102", "5201", "5203", "5405", "5501", "5502", "5503", "5701"}),
    SMALL_ENTERPRISE_2013: frozenset({"5001", "5051", "5111", "5403", "5602", "5603", "5711"}),
}

#: 出现任一个 ⇒ 新准则账套（损益已是 6xxx），不套对照表。
_NEW_STANDARD_PL_CODES = frozenset({"6001", "6051", "6401", "6402", "6601", "6602", "6603", "6711", "6801"})

_MIN_SIGNATURE_HITS = 2


def level1_code(code: str | None) -> str:
    """一级码（前 4 位）：兼容 ``1001.0``（Excel 数字编码）、``5101.01``、``5101-01``、``510101``。"""
    s = str(code or "").strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    for sep in (".", "-", "/", "_", "\\", " "):
        s = s.replace(sep, "")
    return s[:4]


def detect_legacy_pl_crosswalk(client_codes: Iterable[str]) -> tuple[str, dict[str, str]] | None:
    """按客户科目编码判定旧编码体系，返回 ``(体系名, 对照表)``；不是旧体系或判不准返回 None。"""
    level1 = {level1_code(c) for c in client_codes}
    if level1 & _NEW_STANDARD_PL_CODES:
        return None
    hits = {system: len(level1 & sig) for system, sig in _SIGNATURE_CODES.items()}
    (best, best_n), (_, other_n) = sorted(hits.items(), key=lambda kv: kv[1], reverse=True)
    if best_n < _MIN_SIGNATURE_HITS or best_n == other_n:
        return None
    return best, PL_CROSSWALKS[best]


def crosswalk_target(code: str | None, crosswalk: dict[str, str] | None) -> str | None:
    """该客户科目（含下级）按对照表应映射到的新准则码；不在表内返回 None。"""
    if not crosswalk:
        return None
    return crosswalk.get(level1_code(code))
