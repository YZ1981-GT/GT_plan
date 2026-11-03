#!/usr/bin/env python3
"""从 section_code_index.json 生成 note_template_variant_matrix.json.

权威源：``backend/data/audit_report_templates/section_code_index.json``
（四变体 → sections[]，每节含 section_code / section_title / legacy_aliases）。

矩阵覆盖**主要账户节**，即「财务报表主要项目注释」章（国企 ``八``、上市 ``五``），
**不含**会计政策章（国企 ``四``、上市 ``三``）。同一账户在国企用 ``八、N``、
上市用 ``五、N``，本脚本按归一化标题跨变体配对。

account_key 为稳定英文 slug（取自 section_id 的拼音尾段）；legacy_aliases 直接
取自 index 节的 ``legacy_aliases`` 字段（不硬编码，国企 ``八、1`` ↔ ``五、1`` 等）。

Usage:
    python scripts/build_variant_matrix.py            # dry-run，打印统计
    python scripts/build_variant_matrix.py --write    # 写入矩阵文件
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent
DATA = _BACKEND / "data"
INDEX_PATH = DATA / "audit_report_templates" / "section_code_index.json"
OUT_PATH = DATA / "note_template_variant_matrix.json"

VARIANT_ORDER = (
    "soe_standalone",
    "soe_consolidated",
    "listed_standalone",
    "listed_consolidated",
)

# 各变体「项目注释」章前缀（即主要账户节所在大章）
PROJECT_NOTE_CHAPTER = {
    "soe_standalone": "八",
    "soe_consolidated": "八",
    "listed_standalone": "五",
    "listed_consolidated": "五",
}

# 标题归一化时剔除的连接词 / 标点（仅用于跨变体配对，不改原始标题）
# 例：「营业收入、营业成本」↔「营业收入和营业成本」；
#     「递延所得税资产和…」↔「…与…」；「所有权和…」↔「所有权或…」
_NORMALIZE_STRIP = set(" 、，,（）()【】「」/和与及或")

# section_id 中账户拼音之前的公共片段（soe/listed 一致）
_PINYIN_SPLIT = "xiang-mu-zhu-shi-"

#: 旧 section_id 曾把标题尾部编制提示拼进 slug；标题清理后仍必须沿用既有语义 account_key。
#: 只登记有实证的单项，不按标题重算全部键，也不改变 section_id。
ACCOUNT_KEY_ALIASES = {
    "tou_zi_shou_yi_xia_biao_zhong_bu_shi_yong_d": "tou_zi_shou_yi",
}


def canonical_account_key(key: str) -> str:
    return ACCOUNT_KEY_ALIASES.get(key, key)


def _chapter_prefix(code: str) -> str:
    return code.split("、")[0] if "、" in code else code


def normalize_title(title: str) -> str:
    """归一化标题用于跨变体配对（去连接词/标点，保留数字与核心字）."""
    return "".join(ch for ch in (title or "") if ch not in _NORMALIZE_STRIP)


def slug_from_section_id(section_id: str | None, fallback: str) -> str:
    """从 section_id 拼音尾段派生稳定 English slug."""
    if section_id and _PINYIN_SPLIT in section_id:
        tail = section_id.split(_PINYIN_SPLIT, 1)[1]
    elif section_id:
        # 兜底：取最后若干段拼音
        tail = section_id
    else:
        tail = fallback
    tail = tail.strip("-").replace("-", "_")
    return tail or fallback


def load_index() -> dict[str, Any]:
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def project_note_sections(index: dict[str, Any], variant_key: str) -> list[dict[str, Any]]:
    """返回某变体「项目注释」章节（按文档顺序）."""
    chapter = PROJECT_NOTE_CHAPTER[variant_key]
    variant = index.get("variants", {}).get(variant_key) or {}
    out: list[dict[str, Any]] = []
    for s in variant.get("sections", []):
        code = s.get("section_code", "")
        if _chapter_prefix(code) == chapter:
            out.append(s)
    return out


def build_matrix(index: dict[str, Any]) -> dict[str, Any]:
    # norm_title -> account record (insertion-ordered, soe variants processed first)
    accounts: dict[str, dict[str, Any]] = {}
    used_slugs: set[str] = set()

    for variant_key in VARIANT_ORDER:
        for s in project_note_sections(index, variant_key):
            code = s.get("section_code", "")
            title = s.get("section_title", "")
            norm = normalize_title(title)
            if not norm:
                continue
            rec = accounts.get(norm)
            if rec is None:
                # 首见此账户：派生稳定 slug + 记录展示标题
                base_slug = canonical_account_key(slug_from_section_id(s.get("section_id"), norm))
                slug = base_slug
                n = 2
                while slug in used_slugs:
                    slug = f"{base_slug}_{n}"
                    n += 1
                used_slugs.add(slug)
                rec = {
                    "account_key": slug,
                    "section_title": title,
                    "variants": {vk: None for vk in VARIANT_ORDER},
                    "legacy_aliases": {},
                }
                accounts[norm] = rec
            # 填入本变体 code
            rec["variants"][variant_key] = code
            # legacy_aliases 直接取自 index 节（非硬编码）
            aliases = s.get("legacy_aliases") or []
            if aliases:
                rec["legacy_aliases"][variant_key] = list(aliases)

    matrix_accounts = list(accounts.values())
    return {
        "version": "2026-1",
        "description": (
            "附注变体矩阵：主要账户节（项目注释章，国企八/上市五）在四变体中的 "
            "section_code 对照。由 build_variant_matrix.py 从 section_code_index.json 生成。"
        ),
        "source": "audit_report_templates/section_code_index.json",
        "generator": "scripts/build_variant_matrix.py",
        "accounts": matrix_accounts,
    }


# 本生成器**不产出**的 additive 字段：由别的脚本按母公司章追加
# (backend/scripts/fix/fix_variant_matrix_parent_sections.py, spec
#  parent-company-note-chapter-and-sourcing Task 10)。
# 重生成时必须原样搬过来，否则 --write 一次就把母公司维度静默抹掉。
ADDITIVE_ACCOUNT_FIELDS = ("parent_company_sections",)


def carry_over_existing_variants(
    matrix: dict[str, Any], existing: dict[str, Any] | None
) -> dict[str, Any]:
    """补回 POC index 未覆盖、但既有正式矩阵已验证的非空落点。

    只作用于本次生成仍存在的 canonical account；新生成值与既有值冲突时拒绝，不用旧值覆盖新事实。
    历史投资收益长/短 key 会先规范为同一 key，四个变体取并集。
    """
    if not existing:
        return matrix
    old_by_key: dict[str, dict[str, str | None]] = {}
    for account in existing.get("accounts") or []:
        key = canonical_account_key(str(account.get("account_key") or ""))
        if not key:
            continue
        merged = old_by_key.setdefault(key, {variant: None for variant in VARIANT_ORDER})
        for variant in VARIANT_ORDER:
            value = (account.get("variants") or {}).get(variant)
            if value and merged.get(variant) not in (None, value):
                raise ValueError(f"canonical account {key!r} 的 {variant} 既有值冲突")
            if value:
                merged[variant] = value
    for account in matrix.get("accounts") or []:
        key = canonical_account_key(str(account.get("account_key") or ""))
        account["account_key"] = key
        for variant, old_value in old_by_key.get(key, {}).items():
            current = (account.get("variants") or {}).get(variant)
            if current and old_value and current != old_value:
                raise ValueError(f"canonical account {key!r} 的 {variant} 新旧值冲突: {current!r} != {old_value!r}")
            if current is None and old_value:
                account["variants"][variant] = old_value
    return matrix


def carry_over_additive_fields(
    matrix: dict[str, Any], existing: dict[str, Any] | None
) -> dict[str, Any]:
    """把既有输出里 additive 的 account 级字段搬进新生成的矩阵（按 account_key）.

    纯函数（不读盘、不写盘），便于守卫直接断言。``existing`` 为 None 时原样返回。
    只搬 ``ADDITIVE_ACCOUNT_FIELDS`` 列出的字段；本生成器自己产出的
    ``variants`` / ``legacy_aliases`` 一律不碰。
    """
    if not existing:
        return matrix
    extras: dict[str, dict[str, Any]] = {}
    for acct in existing.get("accounts", []) or []:
        key = canonical_account_key(str(acct.get("account_key") or ""))
        if not key:
            continue
        kept = {f: acct[f] for f in ADDITIVE_ACCOUNT_FIELDS if f in acct}
        for field, value in kept.items():
            if field in extras.get(key, {}) and extras[key][field] != value:
                raise ValueError(f"canonical account {key!r} 的 additive 字段 {field!r} 冲突")
            extras.setdefault(key, {})[field] = value
    for acct in matrix.get("accounts", []) or []:
        key = canonical_account_key(str(acct.get("account_key") or ""))
        acct["account_key"] = key
        for field, value in extras.get(key, {}).items():
            acct[field] = value
    return matrix


def load_existing_matrix() -> dict[str, Any] | None:
    if not OUT_PATH.exists():
        return None
    try:
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover
        print(f"[WARN] cannot read existing matrix for additive carry-over: {exc}")
        return None


def validate_matrix(matrix: dict[str, Any]) -> None:
    """生成前硬门：稳定键唯一、每个变体的章节号只有一个 owner。"""
    accounts = matrix.get("accounts") or []
    keys = [a.get("account_key") for a in accounts]
    if not all(keys) or len(keys) != len(set(keys)):
        raise ValueError("variant matrix account_key 为空或重复")
    for variant in VARIANT_ORDER:
        owners: dict[str, list[str]] = {}
        for account in accounts:
            code = (account.get("variants") or {}).get(variant)
            if code:
                owners.setdefault(code, []).append(account["account_key"])
        duplicates = {code: owner for code, owner in owners.items() if len(owner) > 1}
        if duplicates:
            raise ValueError(f"{variant} 同一 section_code 有多个 owner: {duplicates}")

    investment = [a for a in accounts if a.get("account_key") == "tou_zi_shou_yi"]
    if len(investment) != 1:
        raise ValueError(f"投资收益 canonical account 应恰有 1 条，实为 {len(investment)}")
    expected = {
        "soe_standalone": "八、70", "soe_consolidated": "八、70",
        "listed_standalone": "五、69", "listed_consolidated": "五、69",
    }
    if investment[0].get("variants") != expected:
        raise ValueError(f"投资收益四变体不完整: {investment[0].get('variants')}")


def print_stats(matrix: dict[str, Any]) -> None:
    accounts = matrix["accounts"]
    print(f"Total accounts emitted: {len(accounts)}")
    for vk in VARIANT_ORDER:
        cnt = sum(1 for a in accounts if a["variants"].get(vk))
        print(f"  {vk}: {cnt} accounts")
    with_alias = sum(1 for a in accounts if a["legacy_aliases"])
    print(f"  accounts with legacy_aliases: {with_alias}")
    for field in ADDITIVE_ACCOUNT_FIELDS:
        carried = sum(1 for a in accounts if field in a)
        print(f"  accounts carrying additive field {field}: {carried}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build note_template_variant_matrix.json from section_code_index.json")
    parser.add_argument("--write", action="store_true", help="Write matrix to disk")
    args = parser.parse_args()

    index = load_index()
    existing = load_existing_matrix()
    matrix = build_matrix(index)
    matrix = carry_over_existing_variants(matrix, existing)
    matrix = carry_over_additive_fields(matrix, existing)
    validate_matrix(matrix)
    print_stats(matrix)

    if args.write:
        OUT_PATH.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OUT_PATH}")
    else:
        print("(dry-run; pass --write to save)")


if __name__ == "__main__":
    main()
