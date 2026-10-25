"""附注模板表名正名（空名 / 表头首格泄漏名 / 章节内重名 / 名字含 HTML）—— 幂等。

spec: note-template-columns-and-legacy-snapshot-closure（Task 5）

判据真源 = ``backend/data/note_table_name_corrections.json``
（由 ``backend/scripts/diagnose/build_note_table_name_corrections.py`` 生成，可评审）

唯一动作
--------
改 ``sections[].tables[].name`` + 追加 ``tables[].legacy_aliases``（**只增不删**）
+ 给被触及的 section 盖 ``_aligned_by``。另有静态清单 ``RESTORES``：把被 Word 同步改坏的表名按整组快照
复位（不追加 alias，见该常量注释）。

**不动** ``rows`` / ``headers`` / ``columns`` / ``guidance``（行集与列元数据分别归
per-cycle spec 与本 spec 的 Wave 3）。

🔴 为什么不走 ``_note_structure_kit.apply_plan``
------------------------------------------------
那条通路要求一次性给出整表的 ``cols`` / ``rows`` / ``guidance`` 目标态（它会重写
``headers`` 与 ``columns``）—— 用在「只改名」上等于顺手改掉列元数据，违反 R10.1。
本脚本只复用 kit 的 ``stamp`` / ``find_section``。

用法
----
    python backend/scripts/fix/fix_note_table_names.py                 # dry-run（默认）
    python backend/scripts/fix/fix_note_table_names.py --check         # 欠账数，0 则 exit 0
    python backend/scripts/fix/fix_note_table_names.py --apply         # 写盘
    python backend/scripts/fix/fix_note_table_names.py --variant soe   # 限定变体

约束
----
* **round-trip 自检**：写盘前若 ``json.dumps(原对象)`` 不能逐字复现原文 → exit 2
  （防全文件重排、防并发会话改动被本脚本覆盖）。
* **输出禁 emoji**（GBK 控制台会在写盘之后抛 ``UnicodeEncodeError``，
  让人误判 apply 失败 —— 判成败一律查数据不看退出码）。
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
BACKEND_ROOT = _HERE.parents[2]
REPO_ROOT = _HERE.parents[3]
DATA_DIR = BACKEND_ROOT / "data"
CORRECTIONS = DATA_DIR / "note_table_name_corrections.json"
FRONTEND_MAPS = (
    REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "composables"
)

ALIGNED_BY = "note-template-columns-and-legacy-snapshot-closure"
VARIANTS = ("listed", "soe")
_HTML_RE = re.compile(r"<[^>]+>")

# 表名整组复位（R8.4 批 9b-2，2026-10-25）：5914e315b 的 Word 同步把本脚本名下两节的表名改成了 Word 表前的
# 提示段 / 错一位的小节标题（五、74 T3 成了 T2 的名字、T4 成了 T3 的名字）。按 section_id 登记（受损快照, 目标），
# 经 ``KIT.restore_table_names`` 只在表名序列恰为受损快照时改，已复位或被人改过都不动。目标 = 5914e315b 之前
# 的表名（逐字核对过）。🔴 不追加 legacy_aliases：五、74 T3 的受损名就是 T2 的真名，登记即撞名（Property 8）；
# 旧库快照读时由 ``note_table_enrichment`` 按位置回填模板表名。不重跑真源生成器：它会顺带改错别处的表名。
_LEASE_UNDISCOUNTED = (
    "②资产负债表日后连续五个会计年度每年将收到的未折现租赁收款额，以及剩余年度将收到的未折现租赁收款额总额"
)
_LEASE_RECONCILE = "③未折现租赁收款额与租赁投资净额的调节表"
RESTORES: dict[str, dict[str, tuple[list[str], list[str]]]] = {
    "listed": {
        # 五、3：单表节按章节名命名；G1 前端一直推「衍生金融资产」，国企 八、3 同名
        "chapter-05-he-bing-cai-wu-bao-biao-xiang-mu-zhu-shi-yan-sheng-jin-rong-zi-chan": (
            ["（提示：企业衍生金融工具业务具有重要性的，单独披露衍生金融资产。）"],
            ["衍生金融资产"],
        ),
        # 五、74：T0 / T3 / T4 受损，T1 / T2 / T5 未动（T5 比 T2 多一个句号，是经营租赁那张）
        "chapter-05-he-bing-cai-wu-bao-biao-xiang-mu-zhu-shi-zu-lin": (
            [
                "（公司作为承租人的租赁，应披露未纳入租赁负债计量的可变租赁付款额、简化处理的短期租赁费用和"
                "低价值资产租赁费用、与租赁相关的现金流出总额等相关信息。涉及售后租回交易的，应披露是否满足"
                "销售及其判断依据。）",
                "①销售损益、租赁投资净额的融资收益以及与未纳入租赁投资净额的可变租赁付款额相关的收入",
                _LEASE_UNDISCOUNTED,
                _LEASE_UNDISCOUNTED,
                _LEASE_RECONCILE,
                _LEASE_UNDISCOUNTED + "。",
            ],
            [
                "作为承租人",
                "①销售损益、租赁投资净额的融资收益以及与未纳入租赁投资净额的可变租赁付款额相关的收入",
                _LEASE_UNDISCOUNTED,
                _LEASE_RECONCILE,
                "①租赁收入",
                _LEASE_UNDISCOUNTED + "。",
            ],
        ),
    },
}

# 表名复位后要摘掉 `#### ` 前缀的段落（与 `RESTORES` 成对，R8.4 批 9b-2，2026-10-25）。
# 5914e315b 把提示段当成表名后，有人给那条提示段加了 `#### ` 当标题，让「每张表都有小节标题」类守卫过关；
# 表名复位后一节里标题比表多一个 ⇒ `disclosure_engine` 段落游标多走一格、把后续提示段错配到别的表
# （H1 五、22 实测打红 `test_listed_cursor_inference_leaves_gaps_and_misattribution`）。
# 🔴 **独立于复位是否还需要做**：复位早已落盘时上面的循环会 `continue`，摘前缀仍须执行 ⇒ 单独一轮、
# 幂等（`KIT.untitleize_text_sections` 只动 `#` 开头且正文逐字命中的段）。
# 只登记「受损前是普通正文段」的那几条；受损前**就是**标题的（五、28 业绩承诺 / 五、31 / 八、29 / 八、32 /
# 八、54）一律不动 —— 逐条取证见 design §17.6。
UNTITLE_AFTER_RESTORE: dict[str, dict[str, list[str]]] = {
    "listed": {
        "chapter-05-he-bing-cai-wu-bao-biao-xiang-mu-zhu-shi-yan-sheng-jin-rong-zi-chan": [
            "（提示：企业衍生金融工具业务具有重要性的，单独披露衍生金融资产。）",
        ],
    },
}


def _kit():
    path = BACKEND_ROOT / "scripts" / "fix" / "_note_structure_kit.py"
    spec = importlib.util.spec_from_file_location("note_structure_kit_for_names", path)
    assert spec and spec.loader, path
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


KIT = _kit()


# ---------------------------------------------------------------------------
# 纯函数（供守卫复用）
# ---------------------------------------------------------------------------


def plan_table_rename(
    table: dict[str, Any], entry: dict[str, Any]
) -> tuple[str, dict[str, Any] | None]:
    """判定单张表的正名动作。

    Returns:
        ``(verdict, patch)``，verdict 取值：

        * ``"rename"``  —— 需要改名，`patch` 给出目标 `name` 与 `legacy_aliases`
        * ``"noop"``    —— 已是目标名且旧名已登记进 alias（幂等）
        * ``"alias_only"`` —— 名字已对但 alias 缺旧名 → 只补 alias
        * ``"drift"``   —— 当前名既不是 `current_name` 也不是 `correct_name`
                           （有人改过 / 并发会话）→ **跳过不动**并上报
    """
    cur = str(table.get("name") or "")
    want = str(entry["correct_name"])
    was = str(entry["current_name"])
    aliases = [str(a) for a in (table.get("legacy_aliases") or [])]

    if cur == want:
        if was and was != want and was not in aliases:
            return "alias_only", {"legacy_aliases": [*aliases, was]}
        return "noop", None
    if cur != was:
        return "drift", None
    new_aliases = list(aliases)
    if was and was not in new_aliases:
        new_aliases.append(was)
    return "rename", {"name": want, "legacy_aliases": new_aliases}


def aliases_do_not_collide(section: dict[str, Any]) -> list[str]:
    """Property 8：同一 section 内 alias 并集 ∩ 当前表名集合必须为空。"""
    tables = section.get("tables") or []
    names = {str(t.get("name") or "") for t in tables if isinstance(t, dict)}
    bad: list[str] = []
    for t in tables:
        if not isinstance(t, dict):
            continue
        for a in t.get("legacy_aliases") or []:
            if str(a) in names:
                bad.append(str(a))
    return sorted(set(bad))


def section_names_unique(section: dict[str, Any]) -> bool:
    names = [str(t.get("name") or "") for t in (section.get("tables") or [])]
    return len(names) == len(set(names)) and all(n.strip() for n in names)


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


def _load_template(variant: str) -> tuple[dict[str, Any], str, Path]:
    path = DATA_DIR / f"note_template_{variant}.json"
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw), raw, path


def _serialize(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def run_variant(
    variant: str, corrections: dict[str, Any], *, apply: bool
) -> dict[str, Any]:
    doc, raw, path = _load_template(variant)

    # round-trip 自检：本脚本只做增量补丁，不得引入全文件重排
    if _serialize(doc) != raw:
        return {
            "variant": variant,
            "fatal": (
                "round-trip 自检失败：json.dumps(indent=2) 不能逐字复现原文 —— "
                "模板格式已变（并发会话改动？），拒绝写盘"
            ),
        }

    plans = corrections.get("corrections", {}).get(variant, {})
    changes: list[str] = []
    drifts: list[str] = []
    warnings: list[str] = []
    touched_sections: set[str] = set()
    by_id = {
        str(s.get("section_id") or ""): s
        for s in (doc.get("sections") or [])
        if isinstance(s, dict)
    }

    for section_number, spec in plans.items():
        # 🔴 按 section_id 定位，不用 KIT.find_section（它按 section_number 且
        # 只返回**第一个**匹配 —— listed 有两个 `三、研发支出`，第二个会被静默漏掉）
        section = by_id.get(section_number)
        if section is None:
            warnings.append(f"[{variant}] 章节不存在：{section_number} → 跳过")
            continue
        tables = section.get("tables") or []
        for entry in spec.get("tables") or []:
            idx = int(entry["index"])
            if idx >= len(tables) or not isinstance(tables[idx], dict):
                warnings.append(
                    f"[{variant}] {section_number} #{idx} 越界（表数 {len(tables)}）→ 跳过"
                )
                continue
            verdict, patch = plan_table_rename(tables[idx], entry)
            if verdict == "noop":
                continue
            if verdict == "drift":
                drifts.append(
                    f"[{variant}] {section_number} #{idx} 当前名 "
                    f"{tables[idx].get('name')!r} 既非 {entry['current_name']!r} "
                    f"也非 {entry['correct_name']!r} → 跳过（需重新生成真源）"
                )
                continue
            changes.append(
                f"[{variant}] {section_number} #{idx} "
                f"{tables[idx].get('name')!r} -> {entry['correct_name']!r} "
                f"({verdict}, basis={entry['basis']})"
            )
            if apply:
                tables[idx].update(patch or {})
                touched_sections.add(section_number)

    restores = RESTORES.get(variant, {})
    for section_id, (damaged, target) in restores.items():
        section = by_id.get(section_id)
        if section is None:
            warnings.append(f"[{variant}] 章节不存在：{section_id} → 跳过复位")
            continue
        names = [str(t.get("name") or "") for t in (section.get("tables") or [])]
        if names == list(target):
            continue
        if names != list(damaged):
            drifts.append(
                f"[{variant}] {section.get('section_number')} 表名序列既非受损快照也非目标 → 跳过复位（需重新核对）"
            )
            continue
        # dry-run / check 在副本上复位，只为拿到与写盘一致的变更清单
        lines = KIT.restore_table_names(section if apply else copy.deepcopy(section), (damaged, target))
        changes.extend(f"[{variant}] {section.get('section_number')} {x} (restore, basis=5914e315b)" for x in lines)
        if apply and lines:
            touched_sections.add(section_id)

    # 摘掉当初为受损表名加的 `#### ` 前缀 —— 与上面的复位成对，但**不依赖**复位本轮是否发生
    # （复位已落盘时上面会 continue）。幂等，见 `UNTITLE_AFTER_RESTORE` 注释。
    for section_id, paragraphs in UNTITLE_AFTER_RESTORE.get(variant, {}).items():
        section = by_id.get(section_id)
        if section is None:
            warnings.append(f"[{variant}] 章节不存在：{section_id} → 跳过摘标题前缀")
            continue
        lines = KIT.untitleize_text_sections(
            section if apply else copy.deepcopy(section), paragraphs
        )
        changes.extend(f"[{variant}] {section.get('section_number')} {x}" for x in lines)
        if apply and lines:
            touched_sections.add(section_id)

    if apply and touched_sections:
        for section_number in sorted(touched_sections):
            section = by_id.get(section_number)
            if section is not None:
                KIT.stamp(section, ALIGNED_BY)

    # 落地后校验：唯一性 + alias 不撞名
    post_errors: list[str] = []
    for section_number in [*plans, *restores]:
        section = by_id.get(section_number)
        if section is None:
            continue
        if apply or not changes:
            if not section_names_unique(section):
                post_errors.append(f"[{variant}] {section_number} 表名仍不唯一/含空名")
            collide = aliases_do_not_collide(section)
            if collide:
                post_errors.append(
                    f"[{variant}] {section_number} alias 与当前表名冲突：{collide}"
                )

    if apply and changes and not post_errors:
        path.write_text(_serialize(doc), encoding="utf-8")

    return {
        "variant": variant,
        "changes": changes,
        "drifts": drifts,
        "warnings": warnings,
        "post_errors": post_errors,
        "written": bool(apply and changes and not post_errors),
    }


def scan_frontend_references(corrections: dict[str, Any]) -> list[str]:
    """R4.7：被改名的**章节**若被前端 ``*NoteSectionMap.ts`` 消费，必须上报。

    🔴 判据是**章节号**不是表名：表名里的 `项  目` / `期初余额` 同时是大量映射文件的
    列 key / label，按表名字面量扫会产出一大片假阳性（首版实测 9 个文件全是列 key）。
    章节号（`三、现金流量表项目注` 这类 md 截断值）才唯一标识「这张表属于谁」。

    正常情况下这里应为空 —— 本 spec 只改 `unregistered` 章节，而被前端映射消费的章节
    一律是 `registry_covered`（已排除）。非空即说明排除判据漏了。
    """
    if not FRONTEND_MAPS.exists():
        return ["[WARN] 前端 composables 目录不存在，跳过前端引用扫描"]
    targets: dict[str, list[str]] = {}
    for variant in VARIANTS:
        for spec in corrections.get("corrections", {}).get(variant, {}).values():
            num = str(spec.get("section_number") or "").strip()
            if num:
                targets.setdefault(num, []).append(variant)
    hits: list[str] = []
    for f in sorted(FRONTEND_MAPS.glob("*NoteSectionMap.ts")):
        src = f.read_text(encoding="utf-8", errors="replace")
        for num, variants in targets.items():
            if f"'{num}'" in src or f'"{num}"' in src:
                hits.append(
                    f"[FRONTEND] {f.name} 消费被改名章节 {num!r}（{'/'.join(variants)}）"
                    " -> 该章节应移出本 spec 作用域"
                )
    return hits or ["[OK] 前端映射未消费任何被改名章节（预期结果）"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="附注模板表名正名（幂等）")
    ap.add_argument("--apply", action="store_true", help="写盘（默认 dry-run）")
    ap.add_argument("--check", action="store_true", help="CI 模式：有欠账则 exit 1")
    ap.add_argument("--variant", choices=[*VARIANTS, "both"], default="both")
    args = ap.parse_args(argv)

    if not CORRECTIONS.exists():
        print(
            f"[ERR] 缺少真源 {CORRECTIONS}；"
            "先跑 backend/scripts/diagnose/build_note_table_name_corrections.py"
        )
        return 2
    corrections = json.loads(CORRECTIONS.read_text(encoding="utf-8"))
    variants = VARIANTS if args.variant == "both" else (args.variant,)

    total_changes = 0
    fatal = False
    for variant in variants:
        res = run_variant(variant, corrections, apply=args.apply)
        if res.get("fatal"):
            print(f"[ERR] {res['fatal']}")
            fatal = True
            continue
        total_changes += len(res["changes"])
        for line in res["changes"][:40]:
            print("  " + line)
        if len(res["changes"]) > 40:
            print(f"  ... 另 {len(res['changes']) - 40} 条")
        for line in res["drifts"] + res["warnings"] + res["post_errors"]:
            print("  " + line)
        if res["post_errors"]:
            fatal = True
        print(
            f"[OK] {variant}: pending={len(res['changes'])} "
            f"drift={len(res['drifts'])} warn={len(res['warnings'])} "
            f"written={res['written']}"
        )

    for line in scan_frontend_references(corrections):
        print("  " + line)

    if fatal:
        return 2
    if args.check:
        print(f"[{'OK' if total_changes == 0 else 'ERR'}] check: 欠账 {total_changes} 项")
        return 0 if total_changes == 0 else 1
    if not args.apply:
        print(f"[OK] dry-run: 待正名 {total_changes} 项；加 --apply 写盘")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
