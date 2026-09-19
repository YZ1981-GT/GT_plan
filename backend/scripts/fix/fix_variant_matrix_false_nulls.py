"""把 variant_matrix 里判定为 FALSE_NULL 的 null 补记为真实落点（additive）.

Spec: .kiro/specs/soe-listed-note-conversion-correctness/ Task 12
Requirements: 7.2, 7.3 / design Property 26

做什么
------
`note_template_variant_matrix.json` 里 35 条 null 已由
``app/services/note_variant_matrix_null_audit.py`` 三态裁决完毕。
本脚本只处理 ``FALSE_NULL``（目标模板确有落点、只是归在别的章）：
把裁决表里的 ``target_section`` 写进该科目的 ``variants``。

  listed 侧 null  -> 写 variants.listed_standalone / listed_consolidated
  soe    侧 null  -> 写 variants.soe_standalone    / soe_consolidated

两个变体写**同一个值**：实证事实是单体/合并两变体取值完全相同（差异 0，
由 `test_variant_matrix_null_audit.TestAuditCoversAllNulls
::test_standalone_equals_consolidated` 冻结）。

不做什么（硬约束，违反即 exit 2 且不写盘）
-----------------------------------------
1. **不动 CROSS_GRAIN / TRUE_NULL**：前者粒度不对称需业务确认对应关系，
   后者是「该准则下确不列报」的正确 null。
2. **不改既有非 null 取值**：additive only（Requirement 7.3；A spec 需求 10.4
   同样要求「其余 100 个非母公司科目取值不变」）。
3. **不新增/删除变体键**：``variants`` 恒为 4 键。
4. **不编造落点**：每个 ``target_section`` 必须在目标模板里真实存在，
   且必须是**可作披露落点的叶子节**（无子节）。指向章标题行（如 listed
   第十二章「股份支付」level=1 / 6 子节 / 0 表）会让底稿同步取不到任何
   披露表 —— 这正是该科目被改判 CROSS_GRAIN 的原因。
5. **不硬编码章节号**：一律从裁决表取，裁决表本身由
   `test_variant_matrix_null_audit.py` 与两份模板交叉锁死。

判据说明：为什么不用「tables > 0」
---------------------------------
listed 模板有 48 个 ``level=2 且 tables=0`` 的节，它们是**纯文字披露节**
（会计政策章下的政策描述，带 text_sections），是合法落点 —— 现有落点里
``五、72`` 就是这种形态且已被 2 处引用。真正不能当落点的是**章标题容器**，
判据是「有子节」而非「无表格」。

输出约定
--------
控制台不使用 emoji（Windows GBK 控制台会 UnicodeEncodeError，且崩点在写盘
之后 → 判 apply 成败一律查数据不看退出码）。

退出码
------
0 = 无欠账 / 已完成；1 = 有欠账（--check / --dry-run 且有变更）；
2 = round-trip 自检或前置断言失败（**不写盘**）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend"
DATA_DIR = BACKEND / "data"
MATRIX_PATH = DATA_DIR / "note_template_variant_matrix.json"
TEMPLATE_PATH = {
    "listed": DATA_DIR / "note_template_listed.json",
    "soe": DATA_DIR / "note_template_soe.json",
}

# 裁决表是 backend/app 下的服务模块，脚本从仓库根跑时需要显式加 backend 到 path
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.note_variant_matrix_null_audit import (  # noqa: E402
    LISTED_NULL_AUDIT,
    SOE_NULL_AUDIT,
)

SIDES = ("listed", "soe")
VARIANT_KEYS = (
    "soe_standalone",
    "soe_consolidated",
    "listed_standalone",
    "listed_consolidated",
)
#: side -> 该侧要写的两个变体键（单体/合并同值）
SIDE_VARIANTS: dict[str, tuple[str, ...]] = {
    "listed": ("listed_standalone", "listed_consolidated"),
    "soe": ("soe_standalone", "soe_consolidated"),
}
AUDIT = {"listed": LISTED_NULL_AUDIT, "soe": SOE_NULL_AUDIT}


# --------------------------------------------------------------------------- #
# 序列化：必须逐字节复现原文格式（indent=2 / ensure_ascii=False / CRLF / 末尾换行）
# --------------------------------------------------------------------------- #
def serialize(doc: Any) -> bytes:
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    return text.replace("\n", "\r\n").encode("utf-8")


def assert_round_trip(raw: bytes) -> None:
    """json.dumps 必须逐字节复现原文，否则 exit 2（防全文件重排）。

    该文件被 D/G/H/K/L/N 与 A spec 多方共享，是回退高发文件；一次重排会让
    并发会话的改动在 merge 时整体丢失。
    """
    doc = json.loads(raw.decode("utf-8"))
    again = serialize(doc)
    if again == raw:
        return
    print("[ERR] round-trip self-check failed: json.dumps cannot reproduce the")
    print("      original byte-for-byte. Refusing to write.")
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
# 目标模板：落点存在性 + 是否为可作披露落点的叶子节
# --------------------------------------------------------------------------- #
def load_landing_index(side: str) -> dict[str, dict]:
    """返回 {section_number: {"level":…, "child_count":…, "table_count":…}}。

    section_number 在模板里可能重复（md 重建产物），取首个命中并记录重复数。
    """
    doc = json.loads(TEMPLATE_PATH[side].read_text(encoding="utf-8"))
    sections = [s for s in (doc.get("sections") or []) if isinstance(s, dict)]
    child_count: dict[str, int] = {}
    for s in sections:
        parent = s.get("parent_section_id")
        if parent:
            child_count[str(parent)] = child_count.get(str(parent), 0) + 1

    out: dict[str, dict] = {}
    for s in sections:
        number = str(s.get("section_number") or "")
        if not number or number in out:
            continue
        out[number] = {
            "level": s.get("level"),
            "section_id": str(s.get("section_id") or ""),
            "child_count": child_count.get(str(s.get("section_id") or ""), 0),
            "table_count": len(s.get("tables") or []),
            "scope": s.get("scope"),
        }
    return out


def assert_landing_usable(side: str, key: str, target: str, index: dict[str, dict]) -> None:
    """落点必须存在、必须是叶子节（无子节）。不合格 exit 2。"""
    info = index.get(target)
    if info is None:
        print(
            f"[ERR] {side}/{key}: landing {target!r} not found in "
            f"note_template_{side}.json -> fabricated section number"
        )
        sys.exit(2)
    if info["child_count"] > 0:
        print(
            f"[ERR] {side}/{key}: landing {target!r} has {info['child_count']} "
            f"child section(s) (level={info['level']}, tables={info['table_count']}) "
            "-> it is a chapter container, not a disclosure section. "
            "Pointing variant_matrix at it makes workpaper sync resolve zero tables. "
            "Re-judge as CROSS_GRAIN and confirm the real mapping."
        )
        sys.exit(2)


# --------------------------------------------------------------------------- #
# 计划
# --------------------------------------------------------------------------- #
def build_expected() -> dict[str, dict[str, str]]:
    """返回 {account_key: {variant_key: section_number}}（只含 FALSE_NULL）。"""
    index = {side: load_landing_index(side) for side in SIDES}
    expected: dict[str, dict[str, str]] = {}
    for side in SIDES:
        for entry in AUDIT[side]:
            if entry.verdict != "FALSE_NULL":
                continue
            target = entry.target_section
            if not target:
                print(f"[ERR] {side}/{entry.account_key}: FALSE_NULL without target_section")
                sys.exit(2)
            assert_landing_usable(side, entry.account_key, target, index[side])
            slot = expected.setdefault(entry.account_key, {})
            for vk in SIDE_VARIANTS[side]:
                if vk in slot and slot[vk] != target:
                    print(
                        f"[ERR] {entry.account_key}: conflicting targets for {vk}: "
                        f"{slot[vk]!r} vs {target!r}"
                    )
                    sys.exit(2)
                slot[vk] = target
    return expected


def assert_no_code_collision(doc: dict, expected: dict[str, dict[str, str]]) -> None:
    """撞码闸：补记后同一变体下不得有两个 account 共用一个 section_number。

    🔴 这条闸是实测踩出来的：``tou_zi_shou_yi`` 与
    ``tou_zi_shou_yi_xia_biao_zhong_bu_shi_yong_d`` 在矩阵里是**同一科目被拆成
    两条**（成因见 A spec 的 `T10_PARENT_SIDE_WITHOUT_MERGED` 登记：
    `build_variant_matrix.normalize_title` 只剥【】符号不剥括注文本，
    「投资收益【下表中不适用的项目，删除】」与「投资收益」归一后不相等 ⇒ 未配对）。
    两条各自的 null 侧若都按「模板里找得到同名章节」补记，就会双双指向
    listed 五、69 / soe 八、70 ⇒ HEAD 侧 0 组撞码变成 4 组。

    撞码的下游后果：`variant_matrix` 是「科目 → 附注章节」的定位真源，
    一码两主时任何反查（章节 → 科目）都会二选一，底稿同步与附注反跳都可能落错。
    ⇒ 补记前必须先解决「拆成两条」这个上游缺陷（改 normalize_title 剥括注，
    属既有矩阵缺陷、不在本 spec 范围），故这两条改判 CROSS_GRAIN。
    """
    merged: dict[str, dict[str, list[str]]] = {vk: {} for vk in VARIANT_KEYS}
    for acct in doc["accounts"]:
        key = str(acct.get("account_key"))
        want = expected.get(key, {})
        for vk in VARIANT_KEYS:
            code = want.get(vk) or (acct.get("variants") or {}).get(vk)
            if code:
                merged[vk].setdefault(str(code), []).append(key)

    bad: list[str] = []
    for vk, by_code in merged.items():
        for code, owners in sorted(by_code.items()):
            if len(owners) > 1:
                bad.append(f"  {vk} {code!r}: {sorted(owners)}")
    if bad:
        print("[ERR] section_number collision after back-filling (one code, many accounts):")
        print("\n".join(bad))
        print(
            "      A section number must have exactly one owner per variant, otherwise "
            "reverse lookup (section -> account) is ambiguous. If the colliding accounts "
            "are the same real subject split in two, fix the split upstream "
            "(build_variant_matrix.normalize_title) instead of back-filling both."
        )
        sys.exit(2)


def build_plan(doc: dict, expected: dict[str, dict[str, str]]) -> tuple[dict, list[str]]:
    """返回 (新 doc, 变更说明列表)。变更列表为空即无欠账。"""
    changes: list[str] = []
    by_key = {str(a.get("account_key")): a for a in doc["accounts"]}
    for key in sorted(expected):
        if key not in by_key:
            print(f"[ERR] audit table references unknown account_key {key!r}")
            sys.exit(2)
    assert_no_code_collision(doc, expected)

    new_accounts: list[dict] = []
    for acct in doc["accounts"]:
        key = str(acct.get("account_key"))
        want = expected.get(key)
        if not want:
            new_accounts.append(acct)
            continue
        new_acct = dict(acct)
        variants = dict(new_acct["variants"])
        for vk, target in want.items():
            current = variants.get(vk)
            if current == target:
                continue
            if current is not None:
                # 既有非 null 取值绝不覆盖（additive 红线）
                print(
                    f"[ERR] {key}.{vk} already has {current!r}; refusing to overwrite "
                    f"with {target!r} (additive only). Re-check the audit table."
                )
                sys.exit(2)
            variants[vk] = target
            changes.append(f"{key}.{vk}: null -> {target!r}")
        new_acct["variants"] = variants
        new_accounts.append(new_acct)

    new_doc = dict(doc)
    new_doc["accounts"] = new_accounts
    return new_doc, changes


def assert_additive(old_doc: dict, new_doc: dict, expected: dict[str, dict[str, str]]) -> None:
    """零回归闸：account 数/顺序不变，只有 expected 声明的槽位从 null 变非 null。"""
    old_a, new_a = old_doc["accounts"], new_doc["accounts"]
    if len(old_a) != len(new_a):
        print(f"[ERR] account count changed: {len(old_a)} -> {len(new_a)}")
        sys.exit(2)

    def canon(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)

    for o, n in zip(old_a, new_a):
        key = str(o.get("account_key"))
        if key != str(n.get("account_key")):
            print(f"[ERR] account order changed: {key} -> {n.get('account_key')}")
            sys.exit(2)
        for field in ("section_title", "legacy_aliases", "parent_company_sections"):
            if canon(o.get(field)) != canon(n.get(field)):
                print(f"[ERR] {key}: field {field!r} changed (must stay byte-identical)")
                sys.exit(2)
        if tuple(n["variants"].keys()) != VARIANT_KEYS:
            print(f"[ERR] {key}: variants keys changed -> {list(n['variants'].keys())}")
            sys.exit(2)
        allowed = expected.get(key, {})
        for vk in VARIANT_KEYS:
            ov, nv = o["variants"].get(vk), n["variants"].get(vk)
            if ov == nv:
                continue
            if vk not in allowed:
                print(f"[ERR] {key}.{vk} changed {ov!r} -> {nv!r} but is not in the plan")
                sys.exit(2)
            if ov is not None:
                print(f"[ERR] {key}.{vk} was non-null ({ov!r}); additive only")
                sys.exit(2)
            if nv != allowed[vk]:
                print(f"[ERR] {key}.{vk} set to {nv!r}, expected {allowed[vk]!r}")
                sys.exit(2)

    for field in ("version", "description", "source", "generator"):
        if old_doc.get(field) != new_doc.get(field):
            print(f"[ERR] top-level field {field!r} changed")
            sys.exit(2)


def count_non_null(doc: dict) -> int:
    return sum(
        1
        for a in doc["accounts"]
        for vk in VARIANT_KEYS
        if (a.get("variants") or {}).get(vk) is not None
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="只打印计划（默认）")
    g.add_argument("--apply", action="store_true", help="写盘")
    g.add_argument("--check", action="store_true", help="仅校验，0 欠账 exit 0")
    args = ap.parse_args()
    mode = "apply" if args.apply else ("check" if args.check else "dry-run")

    raw = MATRIX_PATH.read_bytes()
    assert_round_trip(raw)
    doc = json.loads(raw.decode("utf-8"))
    print(
        f"[INFO] matrix: {len(doc['accounts'])} accounts, {len(raw)} bytes, "
        f"non-null slots={count_non_null(doc)}, round-trip OK"
    )

    expected = build_expected()
    total_slots = sum(len(v) for v in expected.values())
    print(f"[INFO] FALSE_NULL accounts={len(expected)} slots={total_slots}")
    for key in sorted(expected):
        print(f"       {key}: {json.dumps(expected[key], ensure_ascii=False)}")

    new_doc, changes = build_plan(doc, expected)
    assert_additive(doc, new_doc, expected)

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
            print(f"[INFO] dry-run: nothing written. non-null slots would become "
                  f"{count_non_null(new_doc)}. Re-run with --apply.")
            return 1
        print("[OK] already up to date")
        return 0

    if not changes:
        print("[OK] already up to date, nothing written")
        return 0

    payload = serialize(new_doc)
    if serialize(json.loads(payload.decode("utf-8"))) != payload:
        print("[ERR] new content is not round-trip stable, refusing to write")
        return 2
    MATRIX_PATH.write_bytes(payload)
    print(
        f"[OK] applied {len(changes)} change(s), {len(payload)} bytes written, "
        f"non-null slots={count_non_null(new_doc)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
