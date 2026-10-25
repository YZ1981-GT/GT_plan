"""与上级企业关系（子公司 / 分公司）的取值规范与默认判定。

spec consol-tree-three-code-autobuild 需求 2 / 属性 P11。

- ``normalize_relation``：把任意输入收敛为 ``"subsidiary" | "branch" | None``，非法值抛 ``ValueError``。
- ``infer_relation_from_name``：按企业名称给出默认关系（只作默认值，用户手选优先）。
- ``effective_parent_code`` / ``self_reference_kind``：上级代码填成本企业代码 = 本企业就是上级企业
  （需求 1.5，用户确认后保存；三码相同即最终控制方），不当作上级使用。
- ``resolve_relation``：建项/导入时的最终取值 —— 没有有效上级 ⇒ ``None``；
  显式值优先；缺省按名称判定。

🔴 前端 ``src/utils/groupRelation.ts`` 实现同一规则，两端测试逐条跑共享夹具
``backend/data/relation_to_parent_cases.json``，改规则必须两端同改并补用例。
"""

from __future__ import annotations

import re

RELATION_SUBSIDIARY = "subsidiary"
RELATION_BRANCH = "branch"
RELATIONS: tuple[str, ...] = (RELATION_SUBSIDIARY, RELATION_BRANCH)

RELATION_LABELS: dict[str, str] = {
    RELATION_SUBSIDIARY: "子公司",
    RELATION_BRANCH: "分公司",
}

# 分支机构常见名称结尾（顺序无关；「店」覆盖「门店/分店/药店」等）
_BRANCH_SUFFIXES: tuple[str, ...] = (
    "分公司", "分店", "分厂", "营业部", "经营部", "办事处",
    "分行", "支行", "分所", "门店", "店",
)

# 名称末尾的括号注记，如「（筹）」「（特殊普通合伙）」「(有限合伙)」
_TRAILING_PAREN = re.compile(r"[（(][^（()）]*[）)]\s*$")


def normalize_relation(value: str | None) -> str | None:
    """规范化关系取值；空值 ⇒ None，非法值 ⇒ ValueError（由调用方转 400/422）。"""
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    if v in ("子公司",):
        return RELATION_SUBSIDIARY
    if v in ("分公司",):
        return RELATION_BRANCH
    if v not in RELATIONS:
        raise ValueError(f"与上级关系只能是 子公司 或 分公司，收到 {value!r}")
    return v


def _strip_trailing_parens(name: str) -> str:
    """反复去掉名称末尾的括号注记（最多 3 层，防病态输入）。"""
    out = name
    for _ in range(3):
        stripped = _TRAILING_PAREN.sub("", out).rstrip()
        if stripped == out:
            break
        out = stripped
    return out


def infer_relation_from_name(name: str | None) -> str:
    """按企业名称推断默认关系。

    规则（需求 2.1）：去掉末尾括号注记后，
    - 以分支机构结尾词结尾 ⇒ 分公司；
    - 「公司」二字之后仍有字符（如「……有限公司新健康大药房临港店」）⇒ 分公司；
    - 其余（含空名称）⇒ 子公司。
    """
    core = _strip_trailing_parens((name or "").strip())
    if not core:
        return RELATION_SUBSIDIARY
    if core.endswith(_BRANCH_SUFFIXES):
        return RELATION_BRANCH
    idx = core.rfind("公司")
    if idx != -1 and idx + len("公司") < len(core):
        return RELATION_BRANCH
    return RELATION_SUBSIDIARY


def _clean_code(code: object) -> str | None:
    if code is None:
        return None
    s = str(code).strip()
    return s or None


def effective_parent_code(company_code: str | None, parent_company_code: str | None) -> str | None:
    """有效上级代码（需求 1.5）：空 ⇒ None；等于本企业代码 ⇒ None。

    上级代码填成本企业代码 = 用户确认「本企业就是上级企业」：本企业是集团顶层，没有另外的上级，
    企业树只出这一个节点、不建自环边。树构建、关系默认、控制方补齐、批量预校验都经此判定，
    不各自比较字符串。原值照存（回填时用户看到的仍是自己填的），只是不当作上级使用。
    """
    parent = _clean_code(parent_company_code)
    if parent is None or parent == _clean_code(company_code):
        return None
    return parent


SELF_TOP = "top"            # 上级=本企业：本企业就是上级企业（集团顶层企业）
SELF_ULTIMATE = "ultimate"  # 三码相同：本企业即为最终控制方（集团总部或母公司）

SELF_REFERENCE_NOTICES: dict[str, str] = {
    SELF_TOP: "上级企业代码与本企业相同，已按「本企业就是上级企业」处理：本企业为集团顶层企业，不另建上级节点",
    SELF_ULTIMATE: "三个代码相同，已按「本企业即为最终控制方（集团总部或母公司）」处理",
}


def self_reference_kind(
    company_code: str | None,
    parent_company_code: str | None,
    ultimate_company_code: str | None,
) -> str | None:
    """上级代码等于本企业代码时的含义（需求 1.5）：三码相同 ⇒ ``ultimate``；否则 ⇒ ``top``；不等 ⇒ None。

    只看「上级=本企业」这一种自引用；上级为空而控制方=本企业是常规的集团顶层写法，不算自引用。
    """
    own = _clean_code(company_code)
    if own is None or _clean_code(parent_company_code) != own:
        return None
    return SELF_ULTIMATE if _clean_code(ultimate_company_code) == own else SELF_TOP


def resolve_relation(
    explicit: str | None,
    parent_company_code: str | None,
    company_name: str | None,
    company_code: str | None = None,
) -> str | None:
    """建项/导入时的最终关系取值（需求 1.3 / 2.3 / 2.4）。

    - 没有有效上级（上级代码为空，或等于本企业代码）⇒ None；
    - 显式值（已规范化）优先；
    - 否则按名称默认。
    """
    if effective_parent_code(company_code, parent_company_code) is None:
        return None
    normalized = normalize_relation(explicit)
    if normalized is not None:
        return normalized
    return infer_relation_from_name(company_name)


__all__ = [
    "RELATIONS",
    "RELATION_BRANCH",
    "RELATION_LABELS",
    "RELATION_SUBSIDIARY",
    "SELF_REFERENCE_NOTICES",
    "SELF_TOP",
    "SELF_ULTIMATE",
    "effective_parent_code",
    "infer_relation_from_name",
    "normalize_relation",
    "resolve_relation",
    "self_reference_kind",
]
