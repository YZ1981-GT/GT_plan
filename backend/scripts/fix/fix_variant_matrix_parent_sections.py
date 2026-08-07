"""为 note_template_variant_matrix.json 增加母公司章维度（additive）.

Spec: .kiro/specs/parent-company-note-chapter-and-sourcing/ Task 10
Requirements: 8.1, 10.4 / design Property 19

做什么
------
给「母公司章覆盖的科目」追加顶层可选字段 ``parent_company_sections``：

    {"listed": "<listed 侧母公司子节 section_number>",
     "soe":    "<soe 侧母公司子节 section_number>"}

不做什么（硬约束，违反即退出非零）
---------------------------------
1. 不新增变体键：``variants`` 恒为 4 键
   (soe_standalone / soe_consolidated / listed_standalone / listed_consolidated)。
2. 不改既有取值：102 个 account 的 ``variants`` 与 ``legacy_aliases`` 逐字不变。
3. 不编造落点：某一侧母公司章无该子节时，该键**缺失**（不写 null、不套用另一侧）。
   实证不对称：listed 母公司章独有「应收票据」、soe 独有「现金流量表补充资料」。
4. 不硬编码章节号：章节号一律从 ``note_template_listed.json`` /
   ``note_template_soe.json`` 的母公司章 level-2 子节 ``section_number`` 现取真值。

章节号真值形态（勿"修正"）
--------------------------
两份模板 JSON 是 md 重建产物，``section_number`` 存在 10 字符截断，
母公司章命中两处：listed「十六、投资收益（注：以」、soe「十二、现金流量表补充资」。
下游按 ``section_number`` 精确定位，故必须原样保留截断值。

标题别名（唯一一条，带实证依据）
--------------------------------
母公司章子节标题「营业收入与营业成本」在 variant_matrix 里的科目名是
「营业收入、营业成本」（顿号）。依据：源 docx 该子节标题写
「营业收入和营业成本（披露格式参考附注五、62）」，而
``ying_ye_shou_ru_ying_ye_cheng_ben`` 的 ``variants.listed_standalone`` 恰为
「五、62」，两者指同一科目。除此之外一律按 ``section_title`` 精确匹配。

输出约定
--------
控制台**不使用 emoji**（Windows GBK 控制台会 UnicodeEncodeError，
且崩点在写盘之后 → 判 apply 成败一律查数据不看退出码）。

退出码
------
0 = 无欠账 / 已完成；1 = 有欠账（--check / --dry-run 且有变更）；
2 = round-trip 自检失败或前置断言失败（**不写盘**）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "backend" / "data"
MATRIX_PATH = DATA_DIR / "note_template_variant_matrix.json"
TEMPLATE_PATH = {
    "listed": DATA_DIR / "note_template_listed.json",
    "soe": DATA_DIR / "note_template_soe.json",
}

FIELD = "parent_company_sections"
SIDES = ("listed", "soe")

# 母公司章 level-1 标题。listed 侧 JSON 现值多一个「母」字（源 docx 是
# 「公司财务报表主要项目注释」），该偏差已裁决保留 JSON 现值（需求 3），
# 故两种写法都认，但仍断言每侧恰好命中 1 个 level-1 节。
CHAPTER_TITLES: dict[str, set[str]] = {
    "listed": {"母公司财务报表主要项目注释", "公司财务报表主要项目注释"},
    "soe": {"母公司财务报表的主要项目附注"},
}

# 子节 section_title -> variant_matrix 的 section_title（仅列不相等者）
SECTION_TITLE_ALIASES: dict[str, str] = {
    # 依据：源 docx「营业收入和营业成本（披露格式参考附注五、62）」，
    # 而 ying_ye_shou_ru_ying_ye_cheng_ben.variants.listed_standalone == 「五、62」
    "营业收入与营业成本": "营业收入、营业成本",
}

VARIANT_KEYS = (
    "soe_standalone",
    "soe_consolidated",
    "listed_standalone",
    "listed_consolidated",
)


# --------------------------------------------------------------------------- #
# 序列化：必须逐字节复现原文格式（indent=2 / ensure_ascii=False / CRLF / 末尾换行）
# --------------------------------------------------------------------------- #
def serialize(doc: Any) -> bytes:
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    return text.replace("\n", "\r\n").encode("utf-8")


def assert_round_trip(raw: bytes) -> None:
    """round-trip 自检：json.dumps 必须逐字节复现原文，否则 exit 2.

    防「全文件重排」—— 该文件被 D/G/H/K/L/N 多个 spec 共享，是回退高发文件，
    一次重排会让并发会话的改动在 merge 时整体丢失。
    """
    doc = json.loads(raw.decode("utf-8"))
    again = serialize(doc)
    if again != raw:
        print("[ERR] round-trip self-check failed: json.dumps cannot reproduce the")
        print("      original byte-for-byte. Refusing to write (would reflow the")
        print("      whole file and clobber concurrent edits).")
        print(f"      original={len(raw)} bytes  reserialized={len(again)} bytes")
        for i, (a, b) in enumerate(zip(raw, again)):
            if a != b:
                lo = max(0, i - 60)
                print(f"      first diff at byte {i}")
                print(f"      original    ...{raw[lo:i + 60]!r}")
                print(f"      reserialized...{again[lo:i + 60]!r}")
                break
        sys.exit(2)


# --------------------------------------------------------------------------- #
# 从模板 JSON 取母公司章子节真值
# --------------------------------------------------------------------------- #
def load_parent_subsections(side: str) -> dict[str, str]:
    """返回 {子节 section_title: section_number}（真值，含 md 截断）."""
    doc = json.loads(TEMPLATE_PATH[side].read_text(encoding="utf-8"))
    sections = doc["sections"]
    chapters = [
        s
        for s in sections
        if s.get("level") == 1 and s.get("section_title") in CHAPTER_TITLES[side]
    ]
    if len(chapters) != 1:
        print(
            f"[ERR] {side}: expected exactly 1 level-1 parent-company chapter, "
            f"got {len(chapters)}: {[c.get('section_title') for c in chapters]}"
        )
        sys.exit(2)
    chapter_sid = chapters[0]["section_id"]
    out: dict[str, str] = {}
    for s in sections:
        if s.get("parent_section_id") != chapter_sid:
            continue
        title = s.get("section_title")
        number = s.get("section_number")
        if not title or not number:
            print(f"[ERR] {side}: subsection missing title/number: {s.get('section_id')}")
            sys.exit(2)
        if title in out:
            print(f"[ERR] {side}: duplicate subsection title {title!r}")
            sys.exit(2)
        out[title] = number
    if not out:
        print(f"[ERR] {side}: parent-company chapter has no level-2 subsections")
        sys.exit(2)
    return out


def build_expected(accounts: list[dict]) -> dict[str, dict[str, str]]:
    """返回 {account_key: {side: section_number}}，缺落点的侧**不出现该键**."""
    by_title: dict[str, list[str]] = {}
    for a in accounts:
        by_title.setdefault(a["section_title"], []).append(a["account_key"])

    expected: dict[str, dict[str, str]] = {}
    for side in SIDES:
        for title, number in load_parent_subsections(side).items():
            match_title = SECTION_TITLE_ALIASES.get(title, title)
            hits = by_title.get(match_title, [])
            if len(hits) != 1:
                print(
                    f"[ERR] {side} subsection {title!r} -> matrix section_title "
                    f"{match_title!r}: expected exactly 1 account, got {hits}. "
                    "Declare an alias in SECTION_TITLE_ALIASES with evidence."
                )
                sys.exit(2)
            expected.setdefault(hits[0], {})[side] = number
    return expected


# --------------------------------------------------------------------------- #
# 计划与写入
# --------------------------------------------------------------------------- #
def build_plan(doc: dict, expected: dict[str, dict[str, str]]) -> tuple[dict, list[str]]:
    """返回 (新 doc, 变更说明列表)。变更列表为空即无欠账."""
    changes: list[str] = []
    new_accounts: list[dict] = []
    for acct in doc["accounts"]:
        key = acct["account_key"]
        want = expected.get(key)
        have = acct.get(FIELD)
        new_acct = dict(acct)  # 保持原键顺序
        if want is None:
            if FIELD in new_acct:
                new_acct.pop(FIELD)
                changes.append(f"{key}: remove {FIELD} (not a parent-company account)")
        else:
            ordered = {s: want[s] for s in SIDES if s in want}
            if have != ordered:
                new_acct.pop(FIELD, None)
                new_acct[FIELD] = ordered  # 追加为末键，既有 4 键顺序不动
                verb = "set" if have is None else "update"
                changes.append(f"{key}: {verb} {FIELD}={json.dumps(ordered, ensure_ascii=False)}")
        new_accounts.append(new_acct)

    new_doc = dict(doc)
    new_doc["accounts"] = new_accounts
    return new_doc, changes


def assert_additive(old_doc: dict, new_doc: dict) -> None:
    """零回归闸：account 数/顺序不变，variants 与 legacy_aliases 逐字不变，
    variants 不得出现第 5 个键。任一不成立 exit 2（不写盘）。"""
    old_a, new_a = old_doc["accounts"], new_doc["accounts"]
    if len(old_a) != len(new_a):
        print(f"[ERR] account count changed: {len(old_a)} -> {len(new_a)}")
        sys.exit(2)

    def canon(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)

    for o, n in zip(old_a, new_a):
        if o["account_key"] != n["account_key"]:
            print(f"[ERR] account order changed: {o['account_key']} -> {n['account_key']}")
            sys.exit(2)
        key = o["account_key"]
        for field in ("section_title", "variants", "legacy_aliases"):
            if canon(o.get(field)) != canon(n.get(field)):
                print(f"[ERR] {key}: field {field!r} changed (must stay byte-identical)")
                sys.exit(2)
        if tuple(n["variants"].keys()) != VARIANT_KEYS:
            print(f"[ERR] {key}: variants keys changed -> {list(n['variants'].keys())}")
            sys.exit(2)
        extra = set(n.keys()) - {"account_key", "section_title", "variants", "legacy_aliases", FIELD}
        if extra:
            print(f"[ERR] {key}: unexpected extra keys {sorted(extra)}")
            sys.exit(2)

    for field in ("version", "description", "source", "generator"):
        if old_doc.get(field) != new_doc.get(field):
            print(f"[ERR] top-level field {field!r} changed")
            sys.exit(2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="只打印计划（默认）")
    g.add_argument("--apply", action="store_true", help="写盘")
    g.add_argument("--check", action="store_true", help="仅校验，0 欠账 exit 0")
    args = ap.parse_args()
    mode = "apply" if args.apply else ("check" if args.check else "dry-run")

    raw = MATRIX_PATH.read_bytes()
    assert_round_trip(raw)
    doc = json.loads(raw.decode("utf-8"))
    print(f"[INFO] matrix: {len(doc['accounts'])} accounts, {len(raw)} bytes, round-trip OK")

    expected = build_expected(doc["accounts"])
    print(f"[INFO] parent-company accounts resolved from templates: {len(expected)}")
    for key in sorted(expected):
        sides = expected[key]
        only = f" (only {list(sides)[0]})" if len(sides) == 1 else ""
        print(f"       {key}: {json.dumps(sides, ensure_ascii=False)}{only}")

    new_doc, changes = build_plan(doc, expected)
    assert_additive(doc, new_doc)

    print(f"[INFO] mode={mode} pending changes={len(changes)}")
    for c in changes:
        print(f"       {c}")

    if mode == "check":
        if changes:
            print(f"[FAIL] {len(changes)} outstanding item(s)")
            return 1
        print("[OK] 0 outstanding items")
        return 0

    if mode == "dry-run":
        if changes:
            print("[INFO] dry-run: nothing written. Re-run with --apply.")
            return 1
        print("[OK] already up to date")
        return 0

    if not changes:
        print("[OK] already up to date, nothing written")
        return 0

    payload = serialize(new_doc)
    # 写盘前再确认一次：新内容自身也必须 round-trip 稳定（幂等前提）
    if serialize(json.loads(payload.decode("utf-8"))) != payload:
        print("[ERR] new content is not round-trip stable, refusing to write")
        return 2
    MATRIX_PATH.write_bytes(payload)
    print(f"[OK] applied {len(changes)} change(s), {len(payload)} bytes written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
