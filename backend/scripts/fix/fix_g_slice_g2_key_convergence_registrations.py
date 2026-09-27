"""幂等：把 G slice 里因 **G2 键收敛** 而失真的登记改成现算事实。

spec: `.kiro/specs/g-cycle-sync-foundation-and-first-canary`（Task 13 的后果 / Task 18 收口）

═══ 为什么要改「冻结」的 slice ═══

本 spec Task 13 把 `G2-2-detail-rows` 从「5 个模块各写一份字面量」收敛成
「`g2StorageContract.G2_ITEM_IDS` 单一真源 + 各模块派生别名」（范式照 G5/G6）。
这是 BP-10 明文要求的修法，但它让 slice 里三组登记与源码脱钩，上游守卫
`tests/workpaper_sync/test_task49_g_cycle_migration.py` 随即 4 条红 ——
且每条断言消息都写着「若已开始收敛，请更新登记与本判据」，即这些字段就是为
「事实变了要回填」设计的，不是 append-only 审计轨迹。

① **G2 `transport_key_kind`: `literal_item_id` → `storage_contract_member_item_id`**
   连带 `primary_table` 的三个字段改指 storage contract：
   `owner_module` → `composables/g2StorageContract.ts`、
   `owner_constant` → `G2_ITEM_IDS.G2_2_DETAIL_ROWS`、
   `owner_declaration_kind` → `storage_contract_object_member`。
   取值逐字照既有两条同族样本（G5-2-rows / G6-11-rows），不自造新枚举值。
   连带摘要 `transport_key_kind_counts`：`literal_item_id` −1、
   `storage_contract_member_item_id` +1（总数不变）。

② **两处 `#L` 行号前移**（源码插入注释 + 派生声明后整体下移）
   · `payload_column_source`  `useG2Detail.ts#L517` → `#L519`
     守卫取 `[line-1 : line+3]` 四行窗口判 remark/conclusion；停在 L517 时窗口落在
     `function persistRows` 声明处，remark/conclusion 双双扫不到 ⇒ 把 `remark_only`
     误判成「两列都没写」。现测写入点：L519 `allResponses.value.set(STORAGE_KEY, {`
     / L520 `item_id` / L521 `conclusion: null` / L522 `remark: JSON.stringify(rows)`。
   · `row_identity_generator_source` `#L146` → `#L150`（`function generateId()` 现址）。
     该 ref 的守卫只用它解析**文件**、不读行号，故它不是红因；一并改正是为了不留
     「看着像精确其实过期」的行号。

③ **BP-10 规模数 80 → 79**
   收敛后 `G2-2-detail-rows` 不再是「多模块重复字面量」⇒ 现扫从 80 降到 79。
   `status` **仍是** `REGISTERED_NOT_FIXED`：79 条未收敛，本 spec 只按需动了 G2 那条，
   不得因动了一条就把整条阻断项标已修。改为补一个 `partial_progress` 子字段记录进度。

🔴 不改的：`payload_column` / `payload_column_mode` / `payload_null_placeholder_columns`
   —— 收敛只换了键的**声明位置**，没有改写入列的形态（仍是 remark 单写 + conclusion 空占位）。

用法：
    python backend/scripts/fix/fix_g_slice_g2_key_convergence_registrations.py --check
    python backend/scripts/fix/fix_g_slice_g2_key_convergence_registrations.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
SLICE = BACKEND / "data" / "workpaper_sync_g_cycle_manifest_slice.json"

FE = ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
G2_DETAIL = FE / "composables" / "useG2Detail.ts"
G2_CONTRACT = FE / "composables" / "g2StorageContract.ts"

G2_ENTRY_ID = "xlsx/gt-g2-interest-receivable"
ITEM_ID = "G2-2-detail-rows"

WANT_KIND = "storage_contract_member_item_id"
WANT_OWNER_MODULE = (
    "audit-platform/frontend/src/components/workpaper/composables/g2StorageContract.ts"
)
WANT_OWNER_CONSTANT = "G2_ITEM_IDS.G2_2_DETAIL_ROWS"
WANT_OWNER_DECL_KIND = "storage_contract_object_member"
WANT_PAYLOAD_SOURCE = (
    "audit-platform/frontend/src/components/workpaper/composables/useG2Detail.ts#L519"
)
WANT_GENERATOR_SOURCE = (
    "audit-platform/frontend/src/components/workpaper/composables/useG2Detail.ts#L150"
)
WANT_DUPLICATED_COUNT = 79

BP10_PARTIAL_NOTE = (
    "🔴 2026-09-27 **部分收敛**（spec `g-cycle-sync-foundation-and-first-canary` Task 13）："
    "`G2-2-detail-rows` 从 5 处各写一份字面量"
    "（`g2CrossHelpers.G2_DETAIL_STORAGE_KEY` / `useG2Detail.STORAGE_KEY` / "
    "`useG2DisclosureListed.ITEM_DETAIL` / `useG2DisclosureSoe.ITEM_DETAIL` / "
    "`useG2InterestCalc.DETAIL_KEY`）收敛成 `composables/g2StorageContract.ts` 的 "
    "`G2_ITEM_IDS.G2_2_DETAIL_ROWS` 单一真源，五处改**派生别名**（保留原常量名以免动调用方签名）；"
    "范式照既有正面样本 G5/G6 的 `g*StorageContract.ts`。"
    "`status` 仍为 REGISTERED_NOT_FIXED —— 现扫剩 79 条多模块重复字面量未收敛，"
    "本 spec 只按 canary 需要动了 G2 的主受管键（发布 per-entry contract 的硬前置），"
    "其余按 lane 逐个跟进，**不因动了一条就把整条阻断项标已修**。"
)


def _reality_problems() -> list[str]:
    """写盘前现算核实：事实不成立就不改（防把登记改成另一种失真）。"""
    problems: list[str] = []
    if not G2_CONTRACT.is_file():
        problems.append(f"找不到单一真源模块 {G2_CONTRACT}")
    else:
        src = G2_CONTRACT.read_text(encoding="utf-8")
        if not re.search(r"G2_2_DETAIL_ROWS\s*:\s*'" + re.escape(ITEM_ID) + r"'", src):
            problems.append(
                f"{G2_CONTRACT.name} 里找不到 G2_2_DETAIL_ROWS: '{ITEM_ID}' ⇒ 收敛未落地"
            )
        if "G2_ITEM_IDS" not in src:
            problems.append(f"{G2_CONTRACT.name} 里找不到 G2_ITEM_IDS 对象声明")
    if not G2_DETAIL.is_file():
        problems.append(f"找不到 {G2_DETAIL}")
        return problems

    lines = G2_DETAIL.read_text(encoding="utf-8").splitlines()
    # 派生别名（而非字面量）——收敛的正向证据
    if not any(
        re.search(r"const\s+STORAGE_KEY\s*=\s*G2_ITEM_IDS\.G2_2_DETAIL_ROWS", ln)
        for ln in lines
    ):
        problems.append(
            "useG2Detail.ts 的 STORAGE_KEY 不是 G2_ITEM_IDS 派生 ⇒ 收敛未落地，不得改 transport_key_kind"
        )
    if re.search(r"const\s+STORAGE_KEY\s*=\s*['\"]" + re.escape(ITEM_ID), "\n".join(lines)):
        problems.append("useG2Detail.ts 里仍有 STORAGE_KEY 字面量声明 ⇒ 收敛不彻底")

    # 行号前提：新 payload_column_source 的四行窗口必须真含 conclusion 空占位 + remark 写入
    want_line = int(WANT_PAYLOAD_SOURCE.rsplit("#L", 1)[1])
    window = "\n".join(lines[want_line - 1 : want_line + 3])
    if "remark:" not in window:
        problems.append(f"L{want_line} 起四行窗口里没有 `remark:` ⇒ 行号仍不对：\n{window}")
    if not re.search(r"conclusion\s*:\s*null", window):
        problems.append(f"L{want_line} 起四行窗口里没有 `conclusion: null` ⇒ 行号仍不对")

    gen_line = int(WANT_GENERATOR_SOURCE.rsplit("#L", 1)[1])
    if "function generateId" not in lines[gen_line - 1]:
        problems.append(
            f"L{gen_line} 不是 `function generateId()` 声明行，实为：{lines[gen_line - 1]!r}"
        )
    return problems


def _recount_duplicated_literals() -> int:
    """按上游守卫同口径现扫「多模块重复声明的 G 前缀 item_id」条数。

    口径逐字照 `test_duplicated_item_id_literal_scale_is_recomputable`：同一正则、同样
    排除 `__tests__` 与 G7，去注释后按 (item_id → 声明文件集合) 聚合，取集合大小 > 1 的。
    自己复算一遍是为了**不把守卫的数字抄进登记** —— 抄数字等于两处各写一份真源。
    """
    decl = re.compile(
        r"(?:const\s+[A-Za-z0-9_]+\s*=|[A-Z0-9_]+\s*:)\s*['\"](G\d+[A-Za-z0-9\-]*)['\"]"
    )
    frontend_src = ROOT / "audit-platform" / "frontend" / "src"
    owners: dict[str, set[str]] = {}
    for path in frontend_src.rglob("*.ts"):
        rel = path.relative_to(ROOT).as_posix()
        if "__tests__" in rel or "G7" in path.name or "/g7" in rel.lower():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"/\*(?:.|\n)*?\*/", "", text)
        text = "\n".join(
            ln for ln in text.splitlines() if not ln.strip().startswith(("//", "*"))
        )
        for match in decl.finditer(text):
            owners.setdefault(match.group(1), set()).add(rel)
    return len({k: v for k, v in owners.items() if len(v) > 1})


def _changes(sl: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    entry = next(
        e for e in sl["independent_entries"] if e["entry_id"] == G2_ENTRY_ID
    )
    hc = entry["html_counterpart"]
    old_kind = hc.get("transport_key_kind")

    if old_kind != WANT_KIND:
        changes.append(f"G2.transport_key_kind {old_kind!r} → {WANT_KIND!r}")
        hc["transport_key_kind"] = WANT_KIND
        counts = sl["honest_adjudication_summary"]["transport_key_kind_counts"]
        counts[old_kind] = counts.get(old_kind, 0) - 1
        if counts[old_kind] == 0:
            del counts[old_kind]
        counts[WANT_KIND] = counts.get(WANT_KIND, 0) + 1
        changes.append(
            f"摘要 transport_key_kind_counts：{old_kind} −1 / {WANT_KIND} +1"
        )

    pt = hc["primary_table"]
    for key, want in (
        ("owner_module", WANT_OWNER_MODULE),
        ("owner_constant", WANT_OWNER_CONSTANT),
        ("owner_declaration_kind", WANT_OWNER_DECL_KIND),
    ):
        if pt.get(key) != want:
            changes.append(f"G2.primary_table.{key} {pt.get(key)!r} → {want!r}")
            pt[key] = want

    for key, want in (
        ("payload_column_source", WANT_PAYLOAD_SOURCE),
        ("row_identity_generator_source", WANT_GENERATOR_SOURCE),
    ):
        if hc.get(key) != want:
            changes.append(f"G2.{key} {hc.get(key)!r} → {want!r}")
            hc[key] = want

    summary = sl["honest_adjudication_summary"]
    live = _recount_duplicated_literals()
    if live != WANT_DUPLICATED_COUNT:
        raise SystemExit(
            f"[FAIL] 现扫重复字面量 {live} 条，与本脚本声明的 {WANT_DUPLICATED_COUNT} 不符 ⇒ "
            "收敛面已再变动，请先复核口径再改登记（不得让脚本盲改成硬编码数字）"
        )
    if summary.get("duplicated_item_id_literals_in_g_cycle") != live:
        changes.append(
            f"摘要 duplicated_item_id_literals_in_g_cycle "
            f"{summary.get('duplicated_item_id_literals_in_g_cycle')} → {live}（现扫复算）"
        )
        summary["duplicated_item_id_literals_in_g_cycle"] = live

    bp10 = next(b for b in sl["blocking_preconditions"] if b.get("id") == "BP-10")
    if bp10.get("status") != "REGISTERED_NOT_FIXED":
        raise SystemExit(
            f"[FAIL] BP-10.status 实为 {bp10.get('status')!r} —— 本脚本假定它仍是 "
            "REGISTERED_NOT_FIXED（79 条未收敛），前提变了要重判"
        )
    if bp10.get("partial_progress") != BP10_PARTIAL_NOTE:
        changes.append("BP-10.partial_progress：记录 G2 主受管键已收敛 + 为何 status 不动")
        bp10["partial_progress"] = BP10_PARTIAL_NOTE
    return changes


def _write(path: Path, doc: dict[str, Any]) -> None:
    # 口径实测：indent=2 / sort_keys=False 能逐字节复现原文
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    problems = _reality_problems()
    if problems:
        print("[FAIL] 现算前提不成立，拒绝改登记：", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        return 2

    sl = json.loads(SLICE.read_text(encoding="utf-8"))
    changes = _changes(sl)
    if not changes:
        print("0 项欠账，无需修改")
        return 0
    for c in changes:
        print("  -", c)
    if args.check:
        print(f"共 {len(changes)} 项欠账（--apply 写盘）")
        return 1
    _write(SLICE, sl)
    print(f"[WRITTEN] {SLICE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
