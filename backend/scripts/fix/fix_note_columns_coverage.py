"""附注模板 `columns` 补齐（幂等）。

spec: note-template-columns-and-legacy-snapshot-closure（Task 9~11）

判据真源 = ``backend/data/note_columns_rules.json``
（由 ``backend/scripts/diagnose/build_note_columns_rules.py`` 从 ``docs/模版/`` 两份
源 docx 生成，可评审；每条带 ``source_ref`` 指向 docx 的 heading 路径与表序）

唯一动作
--------
给 ``columns`` 为空的表写入 ``columns``（逐列 ``flat: true``，首列另带 ``is_label``）
+ 给被触及的 section 盖 ``_aligned_by``。

**不动** ``rows`` / ``headers`` / ``guidance`` / ``name``。
（行集修订归各 per-cycle spec 与 A spec；`guidance` 归本 spec Wave 4；表名归 Wave 2。）

为什么必须显式 `flat`
---------------------
``note_sub_table_projector._extract_column_groups`` 三态：``None``（未声明）会回退
``_infer_groups_from_headers`` **按前缀猜父表头** —— 实测会给「本期增加/本期减少」
凭空推出一个「本期」父表头。声明 ``flat`` 才返回 ``[]``（显式单级）。

用法
----
    python backend/scripts/fix/fix_note_columns_coverage.py                 # dry-run
    python backend/scripts/fix/fix_note_columns_coverage.py --check        # 欠账数
    python backend/scripts/fix/fix_note_columns_coverage.py --apply
    python backend/scripts/fix/fix_note_columns_coverage.py --apply --variant soe
    python backend/scripts/fix/fix_note_columns_coverage.py --deficits     # 打印欠账清单

约束
----
* **round-trip 自检**：写盘前 ``json.dumps(原对象, indent=2)`` 不能逐字复现原文即 exit 2。
* **输出禁 emoji**（GBK 控制台会在写盘之后抛 ``UnicodeEncodeError``）。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
BACKEND_ROOT = _HERE.parents[2]
DATA_DIR = BACKEND_ROOT / "data"
RULES = DATA_DIR / "note_columns_rules.json"
GUIDANCE_RULES = DATA_DIR / "note_guidance_rules.json"
ALIGNED_BY = "note-template-columns-and-legacy-snapshot-closure"
VARIANTS = ("listed", "soe")


def _kit():
    path = BACKEND_ROOT / "scripts" / "fix" / "_note_structure_kit.py"
    spec = importlib.util.spec_from_file_location("note_structure_kit_for_columns", path)
    assert spec and spec.loader, path
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


KIT = _kit()


# ---------------------------------------------------------------------------
# 纯函数（供守卫复用）
# ---------------------------------------------------------------------------


def plan_table_columns(
    table: dict[str, Any], entry: dict[str, Any]
) -> tuple[str, list[dict[str, Any]] | None]:
    """判定单张表的补列动作。

    Returns:
        ``(verdict, columns)``：

        * ``"fill"``       —— ``columns`` 为空，写入规则给的列
        * ``"noop"``       —— 已与规则逐字段一致（幂等）
        * ``"drift"``      —— 已有 ``columns`` 但与规则不一致 → **跳过不动**并上报
        * ``"name_drift"`` —— 表名与规则登记的不一致（Wave 2 之后有人又改过名）→ 跳过
        * ``"len_drift"``  —— ``headers`` 长度与规则列数不等 → 跳过
    """
    want = entry["columns"]
    if str(table.get("name") or "") != str(entry.get("table_name") or ""):
        return "name_drift", None
    headers = table.get("headers") if isinstance(table.get("headers"), list) else []
    if len(headers) != len(want):
        return "len_drift", None
    cur = table.get("columns")
    if isinstance(cur, list) and cur:
        return ("noop", None) if cur == want else ("drift", None)
    return "fill", [dict(c) for c in want]


def columns_are_flat(columns: list[dict[str, Any]]) -> bool:
    """本 spec 只补单级表头：每列必须 ``flat`` 且不得声明 ``group``。"""
    return bool(columns) and all(
        isinstance(c, dict) and c.get("flat") is True and not c.get("group")
        for c in columns
    )


def plan_table_guidance(
    table: dict[str, Any], entry: dict[str, Any]
) -> tuple[str, str | None]:
    """判定单张表的补 guidance 动作（Task 12）。

    Returns:
        ``(verdict, guidance)``：

        * ``"fill"``       —— 当前 ``guidance`` 为空，写入规则给的文本
        * ``"noop"``       —— 已与规则逐字相同（幂等）
        * ``"drift"``      —— 已有 ``guidance`` 但与规则不同 → **跳过不动**并上报
                              （别人已写过口径，fail-closed 不覆盖）
        * ``"name_drift"`` —— 表名与规则登记的不一致 → 跳过
    """
    if str(table.get("name") or "") != str(entry.get("table_name") or ""):
        return "name_drift", None
    want = str(entry.get("guidance") or "")
    if not want:
        return "noop", None
    cur = str(table.get("guidance") or "").strip()
    if not cur:
        return "fill", want
    return ("noop", None) if cur == want else ("drift", None)


def guidance_is_plain_text(text: str) -> bool:
    """R3.4 / R3.5：guidance 必须纯文本 —— 无 markdown 粗体、无 HTML 标签。

    禁 ``**`` 的理由：平台级脚本 ``fix_note_bold_markers.py`` 会剥离它，
    两个幂等脚本互相打架会让同一 guidance 一天内被改两次（memory 已记）。
    """
    return "**" not in text and not re.search(r"<[^>]+>", text)


def keys_match_headers(columns: list[dict[str, Any]], headers: list[Any]) -> bool:
    """``columns[].key`` 必须与 ``headers`` **同序逐字**对应（改 key 会让数据丢落点）。"""
    return [str(c.get("key") or "") for c in columns] == [str(h or "") for h in headers]


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


def _serialize(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def run_variant(
    variant: str,
    rules: dict[str, Any],
    *,
    apply: bool,
    guidance_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = DATA_DIR / f"note_template_{variant}.json"
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    if _serialize(doc) != raw:
        return {
            "variant": variant,
            "fatal": "round-trip 自检失败：json.dumps(indent=2) 不能逐字复现原文，拒绝写盘",
        }

    by_id = {
        str(s.get("section_id") or ""): s
        for s in (doc.get("sections") or [])
        if isinstance(s, dict)
    }
    plans = rules.get("rules", {}).get(variant, {})
    changes: list[str] = []
    skips: list[str] = []
    touched: set[str] = set()

    for sid, spec in plans.items():
        section = by_id.get(sid)
        if section is None:
            skips.append(f"[{variant}] 章节不存在：{sid}")
            continue
        tables = section.get("tables") or []
        for entry in spec.get("tables") or []:
            idx = int(entry["index"])
            if idx >= len(tables) or not isinstance(tables[idx], dict):
                skips.append(f"[{variant}] {spec['section_number']} #{idx} 越界")
                continue
            verdict, cols = plan_table_columns(tables[idx], entry)
            if verdict == "noop":
                continue
            if verdict != "fill":
                skips.append(
                    f"[{variant}] {spec['section_number']} #{idx} "
                    f"{tables[idx].get('name')!r} -> {verdict}（跳过不动）"
                )
                continue
            assert cols is not None
            if not columns_are_flat(cols) or not keys_match_headers(
                cols, tables[idx].get("headers") or []
            ):
                skips.append(
                    f"[{variant}] {spec['section_number']} #{idx} 规则自检不过"
                    "（非 flat 或 key 与 headers 不同序）→ 跳过"
                )
                continue
            changes.append(
                f"[{variant}] {spec['section_number']} #{idx} "
                f"{entry['table_name']!r} 补 {len(cols)} 列 [{entry['source_ref']}]"
            )
            if apply:
                tables[idx]["columns"] = cols
                touched.add(sid)

    # ------------------------------------------------------------------
    # guidance 通道（Task 12）——与 columns 通道**同一份脚本、同一次写盘**
    # ------------------------------------------------------------------
    # R3.2 只许三种来源（源模板红字/括注 · 准则或财会文号条款 · 「勾稽：」工具提示），
    # 故真源是 `note_guidance_rules.json`（由 build_note_guidance_rules.py 从源 docx
    # **紧邻表前的段落缓冲**里抽括注/条款/提示型段落，逐表精准配对）。
    #
    # 🔴 为什么不按「同章有指引段」批量贴：章级判据会把第 1 张表的指引贴到第 9 张表上
    # （`三、现金流量表项目注释` 一章 9 张表）= 自造披露口径。
    guid_changes: list[str] = []
    guid_skips: list[str] = []
    if guidance_rules:
        for sid, spec in (guidance_rules.get("rules", {}).get(variant, {})).items():
            section = by_id.get(sid)
            if section is None:
                guid_skips.append(f"[{variant}] guidance 章节不存在：{sid}")
                continue
            tables = section.get("tables") or []
            for entry in spec.get("tables") or []:
                idx = int(entry["index"])
                if idx >= len(tables) or not isinstance(tables[idx], dict):
                    guid_skips.append(
                        f"[{variant}] guidance {spec['section_number']} #{idx} 越界"
                    )
                    continue
                verdict, text = plan_table_guidance(tables[idx], entry)
                if verdict == "noop":
                    continue
                if verdict != "fill":
                    guid_skips.append(
                        f"[{variant}] guidance {spec['section_number']} #{idx} "
                        f"{tables[idx].get('name')!r} -> {verdict}（跳过不动）"
                    )
                    continue
                assert text is not None
                guid_changes.append(
                    f"[{variant}] {spec['section_number']} #{idx} "
                    f"{entry['table_name']!r} 补 guidance {len(text)} 字 "
                    f"[{entry['source_ref']}]"
                )
                if apply:
                    tables[idx]["guidance"] = text
                    touched.add(sid)

    if apply and touched:
        for sid in sorted(touched):
            sec = by_id.get(sid)
            if sec is not None:
                KIT.stamp(sec, ALIGNED_BY)
        if changes or guid_changes:
            path.write_text(_serialize(doc), encoding="utf-8")

    return {
        "variant": variant,
        "changes": changes,
        "skips": skips,
        "guidance_changes": guid_changes,
        "guidance_skips": guid_skips,
        "written": bool(apply and (changes or guid_changes)),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="附注模板 columns 补齐（幂等）")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true", help="CI 模式：有欠账则 exit 1")
    ap.add_argument("--variant", choices=[*VARIANTS, "both"], default="both")
    ap.add_argument("--deficits", action="store_true", help="打印欠账清单（不生成规则的表）")
    args = ap.parse_args(argv)

    if not RULES.exists():
        print(f"[ERR] 缺少真源 {RULES}；先跑 backend/scripts/diagnose/build_note_columns_rules.py")
        return 2
    rules = json.loads(RULES.read_text(encoding="utf-8"))

    # guidance 真源（Task 12）缺失时降级为「只补 columns」并明确报告，不静默跳过
    guidance_rules: dict[str, Any] | None = None
    if GUIDANCE_RULES.exists():
        guidance_rules = json.loads(GUIDANCE_RULES.read_text(encoding="utf-8"))
    else:
        print(
            f"[INFO] 未找到 {GUIDANCE_RULES.name}；本轮只补 columns。"
            "guidance 真源生成器 = backend/scripts/diagnose/build_note_guidance_rules.py"
        )

    if args.deficits:
        for variant in VARIANTS:
            items = rules.get("deficits", {}).get(variant, [])
            print(f"[OK] {variant} 欠账 {len(items)} 张：")
            for d in items:
                print(
                    f"    {d['section_number']} #{d['index']} {d['table_name']!r} "
                    f"hdr={d['json_header_count']} | {d['reason']}"
                )
        return 0

    variants = VARIANTS if args.variant == "both" else (args.variant,)
    total = 0
    fatal = False
    for variant in variants:
        res = run_variant(variant, rules, apply=args.apply, guidance_rules=guidance_rules)
        if res.get("fatal"):
            print(f"[ERR] {res['fatal']}")
            fatal = True
            continue
        total += len(res["changes"])
        for line in res["changes"][:30]:
            print("  " + line)
        if len(res["changes"]) > 30:
            print(f"  ... 另 {len(res['changes']) - 30} 条")
        for line in res["skips"]:
            print("  " + line)
        print(
            f"[OK] {variant}: pending={len(res['changes'])} "
            f"skip={len(res['skips'])} written={res['written']}"
        )

    n_def = sum(len(rules.get("deficits", {}).get(v, [])) for v in VARIANTS)
    print(f"[INFO] 规则外欠账 {n_def} 张（源真源不可用，见 --deficits；不得按 JSON headers 兜底补）")

    if fatal:
        return 2
    if args.check:
        print(f"[{'OK' if total == 0 else 'ERR'}] check: 规则内欠账 {total} 项")
        return 0 if total == 0 else 1
    if not args.apply:
        print(f"[OK] dry-run: 待补 {total} 张；加 --apply 写盘")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
