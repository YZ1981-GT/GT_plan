"""科目名称是否指同一科目（自动匹配防编码撞号用，spec mapping-code-collision-and-fetch-by-mapping）。

客户用《企业会计制度》（2001）等旧编号时，资产负债类与平台标准科目表同码不同义（1501 固定资产 / 1501 持有至到期投资）。
自动匹配按编码命中后先用这里核对一级科目名：兼容才按编码认，否则改按名称找。

兼容 = 归一后全等、一方包含另一方（较短一方 ≥ 2 字）、或在同义表同一组。
同义表只收新旧准则改名 / 常见别称，手工维护；拿不准的（待摊费用、预提费用、递延税款……）不收，留给人工映射。
"""

from __future__ import annotations

import re

#: 同一科目的不同叫法（新旧准则改名、常见别称）。每组第一个是平台标准科目名。
SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("库存现金", "现金"),
    ("周转材料", "低值易耗品", "包装物"),
    ("材料采购", "物资采购"),
    ("在途物资", "在途材料"),
    ("应付职工薪酬", "应付工资", "应付福利费"),
    ("应交税费", "应交税金", "其他应交款"),
    ("长期股权投资", "长期投资"),
    ("交易性金融资产", "短期投资"),
    ("销售费用", "营业费用"),
    ("主营业务收入", "营业收入"),  # 新准则报表行名，客户常拿来当科目名（辽宁 6001 营业收入）
    ("主营业务成本", "营业成本"),
    ("营业税金及附加", "税金及附加", "主营业务税金及附加"),
    ("其他业务成本", "其他业务支出"),
    ("所得税费用", "所得税"),
    ("其他收益", "补贴收入"),
    ("固定资产减值准备", "固定资产跌价准备"),
)

_PREFIX = re.compile(r"^(其中|减|加)[:：]")
_SEPARATORS = ("_", "-", "—", "－", "/")


def name_key(name: str | None) -> str:
    """比较口径：取「\\」路径最后一段、去「其中：」等前缀、全半角括号统一、帐 → 账、去空白。"""
    text = str(name or "").strip().strip("\\")
    text = text.split("\\")[-1] if text else ""
    text = text.replace("（", "(").replace("）", ")").replace("帐", "账")
    text = re.sub(r"\s+", "", text)
    return _PREFIX.sub("", text)


_GROUP_OF: dict[str, int] = {name_key(n): i for i, group in enumerate(SYNONYM_GROUPS) for n in group}


def same_account(a: str | None, b: str | None) -> bool:
    """两个科目名是否指同一科目。"""
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    ga, gb = _GROUP_OF.get(ka), _GROUP_OF.get(kb)
    if ga is not None and ga == gb:
        return True
    short, long_ = sorted((ka, kb), key=len)
    return len(short) >= 2 and short in long_


def current_noncurrent_conflict(a: str | None, b: str | None) -> bool:
    """一方带「非流动」、另一方不带：流动性相反，不能靠字面相似配到一起。"""
    return ("非流动" in name_key(a)) != ("非流动" in name_key(b))


def synonyms_of(name: str | None) -> tuple[str, ...]:
    """同义表里与 ``name`` 同组的全部叫法（含自身）；不在表里返回空。"""
    group = _GROUP_OF.get(name_key(name))
    return SYNONYM_GROUPS[group] if group is not None else ()


def reliable_level1_name(name: str | None) -> str | None:
    """一级科目行的名称是否可用于校验：以「\\」开头的是旧导入把上级科目路径当名称（整表错一行），不可信 ⇒ None。"""
    text = str(name or "").strip()
    if not text or text.startswith("\\"):
        return None
    return text


def level1_name_from_detail(name: str | None) -> str | None:
    """没有一级科目行时，从明细名称推一级科目名：「\\实收资本\\国有」取第一段，「实收资本_国有资本」取分隔符前一段。"""
    text = str(name or "").strip()
    if not text:
        return None
    if "\\" in text:
        parts = [p for p in text.split("\\") if p.strip()]
        return parts[0].strip() if len(parts) > 1 else None
    for sep in _SEPARATORS:
        if sep in text:
            head = text.split(sep)[0].strip()
            return head or None
    return None
