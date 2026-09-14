#!/usr/bin/env python
"""给 K 循环共享附注表的段首行补 ``report_row_code``（幂等）。

``report_row_code`` 是**行级**字段，也是 `note_shared_table_segments.split_segments`
唯一的切段依据。一张表里凡出现该字段的行即为「段首」，段区间到下一个段首为止。
底稿推送声明 ``_row_scope`` 时 `find_segment` 按 owner 的码定位段；**查不到就整表
跳过写入**（fail closed，不退化成整表覆盖 —— 那会抹掉他循环已录的段）。

实测：K 类章节的 `report_row_code` 几乎全缺 ⇒ K1/K3 一旦接 `_row_scope`，
推送**静默失效**。本脚本补齐它，是 Task 19（`_row_scope` 声明）的硬前置。

作业面只有 **4 张表**（而非「26 章节」）—— 依据 `note_workpaper_sync_registry.json`
实扫：13 个 K 章节里只有两对章节是多 owner 共享的，其余 11 个是单 owner 独占，
按 Requirement 11.5 登记豁免、不需要段：

===========  ==========================  ====================================
章节          owners                      表
===========  ==========================  ====================================
五、8         G2 · G3 · K1                其他应收款（主汇总表）
八、9         G2 · G3 · K1                其他应收款
五、42        K3 · M1                     其他应付款
八、42        K3 · M1                     其他应付款
===========  ==========================  ====================================

判据真源 = **`report_config` 连库实查**（Requirement 11.2 明令「SHALL NOT 按行名猜」）。
查询：``row_name`` 精确/模糊匹配 + 排除 ``applicable_standard LIKE 'project:%'``。
2026-08-12 实查结果：

===============  ==============  =================================================
行名              码              出现的准则
===============  ==============  =================================================
其他应收款         ``BS-009``      listed_consolidated / listed_standalone /
                                 soe_consolidated / soe_standalone（**四侧同码**）
其他应付款         ``BS-050``      四侧同码（soe 侧另有 ``BS-075`` 同名但 formula
                                 为 NULL —— K3 声明取有公式的 ``BS-050``）
应付股利           ``BS-055``      **仅 listed** 两侧（= M1 声明值）
其中：应付股利      ``BS-076``      **仅 soe** 两侧
其中：应收股利      ``BS-016``      **仅 soe** 两侧
应收利息           —              **四侧零行**
应付利息           —              **四侧零行**
===============  ==============  =================================================

由此得到两条**必须逐变体分开**的结论：

1. **`应收利息` / `应付利息` 不填码。** CAS 2019 修订后资产负债表已无这两行
   （并入其他应收款 / 其他应付款），`report_config` 四侧零命中。按平台「宁缺勿造」
   铁律：造一个码等于造假勾稽。它们在主表里位于**首个段首之前**，`split_segments`
   本就不把这段并入任何 owner ⇒ 无码不影响 K1/K3 写自己的段，也不会被覆盖。
2. **股利行的码两侧不同名不同码**：listed 用 ``应付股利 BS-055``、soe 用
   ``其中：应付股利 BS-076``；应收股利**只有 soe** 有码（``BS-016``），listed 侧
   零行故不填。🔴 ``BS-016`` 是平台已知的**两侧异义**码（listed 侧 BS-016 是
   「一年内到期的非流动资产」），故它**只能**写进 soe 模板；写进 listed 即错行。

用法::

    python backend/scripts/fix/fix_note_k_report_row_codes.py --check
    python backend/scripts/fix/fix_note_k_report_row_codes.py --dry-run
    python backend/scripts/fix/fix_note_k_report_row_codes.py --apply

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 11.1, 11.2, 11.5 / Property 39
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parents[2] / "data"
LISTED_PATH = _DATA / "note_template_listed.json"
SOE_PATH = _DATA / "note_template_soe.json"

#: 段首行补码计划。``stamps`` 逐行给码 + 证据；``no_code`` 登记「确实无码」的行。
#:
#: 每条 ``evidence`` 写的是 `report_config` 实查结论，**不是**行名相似度。
PLAN: list[dict[str, Any]] = [
    {
        "owner_cycle": "K1",
        "variant": "listed",
        "section": "五、8",
        "table": "其他应收款",
        "stamps": [
            {
                "label": "其他应收款",
                "row_code": "BS-009",
                "owner": "K1",
                "report_row_name": "其他应收款",
                "evidence": "report_config 四侧均 其他应收款=BS-009（listed 侧公式 TB('1221','期末余额')）",
            },
        ],
        "no_code": [
            {
                "label": "应收利息",
                "absent_name_like": "%应收利息%",
                "reason": "report_config 四侧零行（CAS2019 已并入其他应收款）；造码=造假勾稽",
            },
            {
                "label": "应收股利",
                "absent_name_like": "%应收股利%",
                "reason": "listed 侧零行（仅 soe 有「其中：应收股利」BS-016，两侧异义不可挪用）",
            },
        ],
    },
    {
        "owner_cycle": "K1",
        "variant": "soe",
        "section": "八、9",
        "table": "其他应收款",
        "stamps": [
            {
                "label": "应收股利",
                "row_code": "BS-016",
                "owner": "G3",
                "report_row_name": "其中：应收股利",
                "evidence": "report_config soe 两侧「其中：应收股利」=BS-016；🔴 listed 侧 BS-016 异义（一年内到期的非流动资产），故只写 soe",
            },
            {
                "label": "其他应收款项",
                "row_code": "BS-009",
                "owner": "K1",
                "report_row_name": "其他应收款",
                "evidence": "report_config soe 两侧 其他应收款=BS-009（模板行名带「项」，映射按 owner 不按字面）",
            },
        ],
        "no_code": [
            {
                "label": "应收利息",
                "absent_name_like": "%应收利息%",
                "reason": "report_config 四侧零行（CAS2019 已并入其他应收款）；造码=造假勾稽",
            },
        ],
    },
    {
        "owner_cycle": "K3",
        "variant": "listed",
        "section": "五、42",
        "table": "其他应付款",
        "stamps": [
            {
                "label": "应付股利",
                "row_code": "BS-055",
                "owner": "M1",
                "report_row_name": "应付股利",
                "evidence": "report_config listed 两侧 应付股利=BS-055；与 M_CYCLE_SPECS['M1'].row_code 一致",
            },
            {
                "label": "其他应付款",
                "row_code": "BS-050",
                "owner": "K3",
                "report_row_name": "其他应付款",
                "evidence": "report_config 四侧 其他应付款=BS-050（本行本已有码，脚本只做幂等校验）",
            },
        ],
        "no_code": [
            {
                "label": "应付利息",
                "absent_name_like": "%应付利息%",
                "reason": "report_config 四侧零行（CAS2019 已并入其他应付款）；造码=造假勾稽",
            },
        ],
    },
    {
        "owner_cycle": "K3",
        "variant": "soe",
        "section": "八、42",
        "table": "其他应付款",
        "stamps": [
            {
                "label": "应付股利",
                "row_code": "BS-076",
                "owner": "M1",
                "report_row_name": "其中：应付股利",
                "evidence": "report_config soe 两侧「其中：应付股利」=BS-076（listed 侧无此码，故与 listed 不同）",
            },
            {
                "label": "其他应付款项",
                "row_code": "BS-050",
                "owner": "K3",
                "report_row_name": "其他应付款",
                "evidence": "report_config soe 两侧 其他应付款=BS-050（另有同名 BS-075 但 formula 为 NULL，取有公式者）",
            },
        ],
        "no_code": [
            {
                "label": "应付利息",
                "absent_name_like": "%应付利息%",
                "reason": "report_config 四侧零行（CAS2019 已并入其他应付款）；造码=造假勾稽",
            },
        ],
    },
]


#: Requirement 11.5：单 owner 独占整表的循环**登记豁免**（不需要段、不需要段首码）。
#:
#: 覆盖面不靠这份名单判断 —— `_check_coverage` 从
#: `note_workpaper_sync_registry.json` 反查每个 K 章节的 owner 数：
#: >1 个 owner 必须出现在 :data:`PLAN`，恰好 1 个必须出现在本名单。
#: 于是将来任何一个 K 章节被别的循环挤进来共用，`--check` 立刻打红。
SINGLE_OWNER_EXEMPT: dict[str, str] = {
    "K2": "五、13 / 八、14 其他流动资产：owner 仅 K2，整表独占",
    "K4": "五、44 / 八、48 其他流动负债：owner 仅 K4，整表独占",
    "K5": "五、50 / 八、55 预计负债：owner 仅 K5，整表独占",
    "K6": "五、11 / 八、12 持有待售资产和负债：owner 仅 K6，整表独占",
    "K7": "五、51 / 八、56 递延收益：owner 仅 K7，整表独占",
    "K8": "五、64 / 八、65 销售费用：owner 仅 K8，整表独占",
    "K9": "五、65 / 八、66 管理费用：owner 仅 K9，整表独占",
    "K10": "五、68 / 八、69 其他收益：owner 仅 K10，整表独占",
    "K11": "资产减值损失章节：owner 仅 K11，整表独占",
    "K12": "营业外收入章节：owner 仅 K12，整表独占",
    "K13": "营业外支出章节：owner 仅 K13，整表独占",
}

_SYNC_REGISTRY = _DATA / "note_workpaper_sync_registry.json"


def _owner_map() -> dict[tuple[str, str], set[str]]:
    """``{(variant, section_number): {wp_code, ...}}``（真源 = 同步登记表）。"""
    doc = json.loads(_SYNC_REGISTRY.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], set[str]] = {}
    for e in doc.get("entries") or []:
        wp = str(e.get("wp_code") or "").upper()
        for variant in ("listed", "soe"):
            num = str(e.get(variant) or "").strip()
            if num:
                out.setdefault((variant, num), set()).add(wp)
    return out


def _check_coverage() -> list[str]:
    """覆盖面自检：多 owner 的 K 章节必须进 PLAN，单 owner 的必须进豁免名单。"""
    problems: list[str] = []
    owners = _owner_map()
    planned = {(e["variant"], e["section"]) for e in PLAN}
    k_sections = {
        key: wps
        for key, wps in owners.items()
        if any(w.startswith("K") for w in wps)
    }
    if len(k_sections) < 20:  # 13 循环 × 2 变体 ≈ 26，明显偏少即真源可疑
        problems.append(f"同步登记表只解析到 {len(k_sections)} 个 K 章节，判据源可疑")
    for key, wps in sorted(k_sections.items()):
        k_owners = sorted(w for w in wps if w.startswith("K"))
        if len(wps) > 1:
            if key not in planned:
                problems.append(
                    f"{key[0]} §{key[1]} 有多个 owner {sorted(wps)} 却不在补码计划里 "
                    "—— 段首码缺失会让 owner 推送整表 fail-closed"
                )
        else:
            wp = k_owners[0]
            if wp not in SINGLE_OWNER_EXEMPT and key not in planned:
                problems.append(
                    f"{key[0]} §{key[1]} 单 owner {wp} 既未登记豁免也不在计划里"
                )
    stale = [wp for wp in SINGLE_OWNER_EXEMPT if not any(
        wp in wps and len(wps) == 1 for wps in k_sections.values()
    )]
    if stale:
        problems.append(
            f"豁免名单里的 {stale} 实际已不是单 owner（或章节没了）—— 豁免理由失效"
        )
    return problems


def _utf8_stdout() -> None:
    """把 stdout/stderr 钉成 UTF-8。

    🔴 本脚本输出含中文，Windows 上被 `capture_output=True` 捕获时子进程按 locale
    （GBK）写管道，而守卫用 UTF-8 解码 ⇒ 「0 项欠账」被腌成乱码、断言恒假。
    在脚本内自愈而不依赖 `PYTHONIOENCODING`，才能同时覆盖 CI / 人工 / 守卫三条路径。
    """
    for s in (sys.stdout, sys.stderr):
        rc = getattr(s, "reconfigure", None)
        if rc is None:
            continue
        try:
            rc(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _find_section(doc: dict, number: str) -> dict | None:
    for sec in doc.get("sections") or []:
        if isinstance(sec, dict) and str(sec.get("section_number") or "").strip() == number:
            return sec
    return None


def _find_table(section: dict, name: str) -> dict | None:
    for tbl in section.get("tables") or []:
        if isinstance(tbl, dict) and str(tbl.get("name") or "").strip() == name:
            return tbl
    return None


def _rows_by_label(tbl: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in tbl.get("rows") or []:
        if isinstance(row, dict):
            out.setdefault(str(row.get("label") or "").strip(), []).append(row)
    return out


def plan_changes(docs: dict[str, dict]) -> tuple[list[str], list[str]]:
    """返回 ``(changes, errors)``。

    ``changes`` 是待写入的补码项；``errors`` 是**结构性问题**（表/行找不到、
    行数不唯一、`no_code` 行被人偷偷填了码）—— 有 errors 一律拒绝写盘。
    """
    changes: list[str] = []
    errors: list[str] = list(_check_coverage())
    for entry in PLAN:
        variant = entry["variant"]
        doc = docs[variant]
        tag = f"{entry['owner_cycle']} {variant} §{entry['section']} / {entry['table']}"
        section = _find_section(doc, entry["section"])
        if section is None:
            errors.append(f"{tag}：找不到章节")
            continue
        tbl = _find_table(section, entry["table"])
        if tbl is None:
            errors.append(f"{tag}：找不到表")
            continue
        by_label = _rows_by_label(tbl)

        for stamp in entry["stamps"]:
            label, want = stamp["label"], stamp["row_code"]
            hits = by_label.get(label) or []
            if len(hits) != 1:
                errors.append(f"{tag}：行 {label!r} 命中 {len(hits)} 条（须为 1）")
                continue
            cur = str(hits[0].get("report_row_code") or "").strip()
            if cur == want:
                continue
            if cur and cur != want:
                errors.append(
                    f"{tag}：行 {label!r} 已有码 {cur!r} 与计划 {want!r} 冲突 —— "
                    "先核对 report_config 再决定，脚本不擅自改已有码"
                )
                continue
            changes.append(f"{tag}：行 {label!r} 补码 {want}（owner={stamp['owner']}）")

        for none in entry["no_code"]:
            label = none["label"]
            hits = by_label.get(label) or []
            if len(hits) != 1:
                errors.append(f"{tag}：登记无码行 {label!r} 命中 {len(hits)} 条（须为 1）")
                continue
            cur = str(hits[0].get("report_row_code") or "").strip()
            if cur:
                errors.append(
                    f"{tag}：行 {label!r} 被填了码 {cur!r}，但 report_config 该行零命中 —— "
                    f"{none['reason']}"
                )
    return changes, errors


def apply_changes(docs: dict[str, dict]) -> tuple[int, set[str]]:
    """写入补码，返回 ``(变更行数, 脏变体集合)``。"""
    n = 0
    dirty: set[str] = set()
    for entry in PLAN:
        variant = entry["variant"]
        section = _find_section(docs[variant], entry["section"])
        if section is None:
            continue
        tbl = _find_table(section, entry["table"])
        if tbl is None:
            continue
        by_label = _rows_by_label(tbl)
        for stamp in entry["stamps"]:
            hits = by_label.get(stamp["label"]) or []
            if len(hits) != 1:
                continue
            if str(hits[0].get("report_row_code") or "").strip() == stamp["row_code"]:
                continue
            hits[0]["report_row_code"] = stamp["row_code"]
            n += 1
            dirty.add(variant)
    return n, dirty


def main() -> int:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description="K 循环共享附注表段首行补码（幂等）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="只报欠账，有欠账 exit 1")
    g.add_argument("--dry-run", action="store_true", help="打印将补的码，不写盘")
    g.add_argument("--apply", action="store_true", help="写盘")
    args = ap.parse_args()

    raws = {
        "listed": LISTED_PATH.read_text(encoding="utf-8"),
        "soe": SOE_PATH.read_text(encoding="utf-8"),
    }
    docs = {k: json.loads(v) for k, v in raws.items()}

    changes, errors = plan_changes(docs)
    for e in errors:
        print(f"  ✗ {e}")
    if errors:
        print(f"[fix_note_k_report_row_codes] {len(errors)} 项结构性问题，拒绝写盘")
        return 2

    if not changes:
        print("[fix_note_k_report_row_codes] 0 项欠账（段首码已齐备）")
        return 0

    for c in changes:
        print(f"  + {c}")

    if args.check:
        print(f"[fix_note_k_report_row_codes] {len(changes)} 项欠账")
        return 1
    if args.dry_run or not args.apply:
        print(f"[fix_note_k_report_row_codes] dry-run：{len(changes)} 项待补（加 --apply 写盘）")
        return 0

    # 🔴 round-trip 闸门：先证明「原样 dump 能逐字复现原文」，再写盘。
    #    否则一次写入会顺带重排整个 700KB~1MB 文件，与并发会话互相回退。
    for key, raw in raws.items():
        trailing = "\n" if raw.endswith("\n") else ""
        again = json.dumps(json.loads(raw), ensure_ascii=False, indent=2) + trailing
        if again != raw:
            print(f"[fix_note_k_report_row_codes] round-trip 不一致（{key}），拒绝写盘")
            return 2

    n, dirty = apply_changes(docs)
    for key in sorted(dirty):
        path = LISTED_PATH if key == "listed" else SOE_PATH
        trailing = "\n" if raws[key].endswith("\n") else ""
        path.write_text(
            json.dumps(docs[key], ensure_ascii=False, indent=2) + trailing, encoding="utf-8"
        )
        print(f"  已写入 {path}")
    print(f"[fix_note_k_report_row_codes] 已补 {n} 个段首码")
    print(
        "  ⚠ 段集合变了 ⇒ 请重跑 "
        "`python backend/scripts/gen/gen_note_shared_table_segments.py --write`"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
