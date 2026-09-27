"""幂等：把 G slice / 删除清册里**已经失真**的两条登记改成现算事实。

spec: `.kiro/specs/g-cycle-sync-foundation-and-first-canary`（Task 9）

═══ 为什么要改「冻结」的 slice 与清册 ═══

两条登记的 `status` / 形态描述已与代码实况不符，而上游守卫
`tests/workpaper_sync/test_task49_g_cycle_migration.py` 正按它们断言 ⇒ **守卫已红**。
两条断言消息本身都明写了「若已修好/形态已变，请更新登记与本判据」——
即这两个字段就是为「事实变了要回填」设计的，不是 append-only 的审计轨迹。

① **BP-5.status: `REGISTERED_NOT_FIXED` → `FIXED`**
   本 spec Task 5 已把 `g1SheetLabels.G1_SHEET_LABEL_MAP` 的 5 条错名改成模板真名
   （含 `交易性金融资产实质性程序表G1A ` 的尾部空格）。
   守卫 `test_bp5_g1_fallback_sheet_labels_point_at_nonexistent_tabs` 的断言消息：
   「兜底标签与权威 tab 不符的集合实测为 []，与 BP-5 冻结结论不符。**若已修好，请更新
   BP-5 的 status 与本判据**」。

② **`unreachable_stub_to_delete.registry_homonymous_alias`：别名已不存在**
   清册登记 `htmlRendererRegistry.ts#L378` 有
   `const GtG6OtherBondEcl = defineAsyncComponent(() => import('./GtG6OtherBondInvestmentEcl.vue'))`。
   现算：`htmlRendererRegistry.ts` 在 commit `82f58ea44` 被**拆分重构**
   （1465 行 → 361 行，组件登记移到 `registry/entries/{core,forms,programs,
   confirmations,reports,specialized}.ts`），该同名别名**随之消失**。
   G6-ecl 组件现在在 `registry/entries/specialized.ts` 以**直接 import** 登记：
   `componentType: 'g6-other-bond-investment-ecl'` →
   `defineAsyncComponent(() => import('../../GtG6OtherBondInvestmentEcl.vue'))`。
   ⇒ 生产行为正常；「按符号名判会误报旧桩被救活」这个坑**已被重构消除**。
   旧桩 `GtG6OtherBondEcl.vue` 仍在磁盘、仍零入边（BP-11 结论不变）。

用法：
    python backend/scripts/fix/fix_g_slice_bp5_status_and_registry_alias.py --check
    python backend/scripts/fix/fix_g_slice_bp5_status_and_registry_alias.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
SLICE = BACKEND / "data" / "workpaper_sync_g_cycle_manifest_slice.json"
PLAN = BACKEND / "data" / "workpaper_sync_g_cycle_deletion_plan.json"

REGISTRY_TS = (
    ROOT / "audit-platform/frontend/src/components/workpaper/htmlRendererRegistry.ts"
)
SPECIALIZED_TS = (
    ROOT
    / "audit-platform/frontend/src/components/workpaper/registry/entries/specialized.ts"
)

BP5_FIXED_STATUS = "FIXED"
BP5_FIX_NOTE = (
    "🔴 2026-09-27 已修（spec `g-cycle-sync-foundation-and-first-canary` Task 5）："
    "`g1SheetLabels.G1_SHEET_LABEL_MAP` 的 5 条错名逐条改为模板真名 —— "
    "`G1A → '交易性金融资产实质性程序表G1A '`（**保留尾部空格**，空格是源模板事实）、"
    "`G1-8 → '业务模式分析G1-8'`、`G1-10 → '合同现金流量特征分析G1-10'`、"
    "`G1-12 → '有价证券盘点倒轧表G1-12'`、`附注国企 → '附注披露信息（国企）'`；"
    "其余 13 条改前即命中。"
    "原 `why_not_fixed_here` 的理由①（「改成带空格的值会让按『编码紧贴表名、无空格』约定写的比对行为改变」）"
    "经按值复核**不成立**：`resolveG1SheetLabel` 的正则是 "
    "`new RegExp(`${escaped}\\\\s*$`)`，本就容忍尾随空白；`extractG1SheetCode` 用 "
    "`sheetName.match(/(G1A|G1-\\\\d+)/i)`，对 `…G1A ` 照样返回 `G1A`。"
    "另有平台级旁证：ACNR 权威目录 `backend/data/acnr/global_catalog.json` 早已把这三个错名"
    "（`合同现金流量特征测试表G1-10` / `业务模式评估问卷G1-8` / `盘点倒轧表G1-12`）"
    "登记为 `sheet_name_aliases`、真名登记为 `sheet_name` ⇒ 平台命名真源与修后值一致，"
    "`g1SheetLabels.ts` 是唯一偏离方。"
    "理由②（把兜底表换成 render-config 下发）仍未做，但它是**另一条**更彻底的修法，"
    "不是本条的阻塞。守卫见 "
    "`tests/workpaper_sync/test_g_foundation_p4_p8_p17_p18_red_baselines.py::TestGfP4Bp5G1SheetLabels`。"
)


def _alias_block_now() -> dict[str, Any]:
    return {
        "declared_in": None,
        "declared_at": None,
        "alias_name": "GtG6OtherBondEcl",
        "alias_still_exists": False,
        "resolves_to": "GtG6OtherBondInvestmentEcl.vue",
        "is_an_inbound_edge_to_the_stub": False,
        "verbatim": None,
        "removed_by": (
            "commit 82f58ea44 把 htmlRendererRegistry.ts **拆分重构**（1465 行 → 361 行）："
            "组件登记移到 `registry/entries/{core,forms,programs,confirmations,reports,"
            "specialized}.ts` 六个子模块，原 `htmlRendererRegistry.ts#L378` 的同名局部别名"
            "`const GtG6OtherBondEcl = defineAsyncComponent(() => import('./GtG6OtherBondInvestmentEcl.vue'))`"
            "随之消失。2026-09-27 现算：`htmlRendererRegistry.ts` 全文 `GtG6OtherBond` **零命中**。"
        ),
        "live_registration_now": {
            "file": "audit-platform/frontend/src/components/workpaper/registry/entries/specialized.ts",
            "component_type": "g6-other-bond-investment-ecl",
            "import_specifier": "../../GtG6OtherBondInvestmentEcl.vue",
            "form": "direct_import_no_homonymous_alias",
        },
        "why_name_based_probes_misfire": (
            "【历史】重构前 `htmlRendererRegistry.ts#L378` 有一个**同名局部常量** "
            "`GtG6OtherBondEcl`，指向的却是真正在用的 `GtG6OtherBondInvestmentEcl.vue`"
            "（短名变量 + 长名文件）。任何按**符号名**判「旧桩是否被引用」的探针都会在这里命中"
            "并误报「旧桩被救活」—— Task 49 首轮守卫正是这么红的。"
            "【现状】该别名已随 registry 拆分消失，`specialized.ts` 用的是直接 import ⇒ "
            "这个特定的误报源**已消除**。但判据形态**不改回按符号名**："
            "`components.d.ts`（unplugin-vue-components 生成物）与 "
            "`workpaperSyncManifest.generated.ts`（把旧桩登记为 hostPath）里仍有该字符串，"
            "按符号名判照样会误报。按**模块边**判这条纪律与别名在不在无关。"
        ),
        "measured": (
            "2026-09-27 现算：① `htmlRendererRegistry.ts` 的 `GtG6OtherBond` 命中 0 处"
            "（重构后该文件只留 6 条子模块 import 与类型/工具导出）；"
            "② `registry/entries/specialized.ts` 有 `componentType: 'g6-other-bond-investment-ecl'` "
            "→ `import('../../GtG6OtherBondInvestmentEcl.vue')`，为**直接 import**、无同名别名；"
            "③ 旧桩 `GtG6OtherBondEcl.vue` 仍在磁盘，全仓按模块边扫入边仍为 0（BP-11 结论不变）。"
        ),
    }


def _plan_changes(plan: dict[str, Any]) -> list[str]:
    """就地改 plan，返回变更说明。"""
    changes: list[str] = []
    stub = plan["unreachable_stub_to_delete"]
    want = _alias_block_now()
    if stub.get("registry_homonymous_alias") != want:
        changes.append(
            "unreachable_stub_to_delete.registry_homonymous_alias："
            "同名别名已随 htmlRendererRegistry 拆分消失 ⇒ 改登记为 "
            "alias_still_exists=false + live_registration_now(specialized.ts 直接 import)"
        )
        stub["registry_homonymous_alias"] = want

    # `guard` 字段的第②条描述也已失真（它说「registry 里那条同名别名必须仍然指向…」）
    guard = stub.get("guard", "")
    marker = "② registry 里那条同名别名必须仍然指向 GtG6OtherBondInvestmentEcl.vue（形态一变即红，见 registry_homonymous_alias）"
    new_clause = (
        "② G6-ecl 组件必须仍在 `registry/entries/specialized.ts` 以**直接 import** 登记"
        "（2026-09-27：原 htmlRendererRegistry.ts 的同名别名已随拆分重构消失，"
        "见 registry_homonymous_alias.removed_by）"
    )
    if marker in guard:
        changes.append("unreachable_stub_to_delete.guard 的第②条：改为按拆分后的子模块登记判")
        stub["guard"] = guard.replace(marker, new_clause)
    return changes


def _slice_changes(sl: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    bp5 = next(b for b in sl["blocking_preconditions"] if b.get("id") == "BP-5")
    if bp5.get("status") != BP5_FIXED_STATUS:
        changes.append(f"BP-5.status {bp5.get('status')!r} → {BP5_FIXED_STATUS!r}")
        bp5["status"] = BP5_FIXED_STATUS
    if bp5.get("fixed_note") != BP5_FIX_NOTE:
        changes.append("BP-5.fixed_note：写入逐条改名清单 + 原不修理由的复核结论 + ACNR 旁证")
        bp5["fixed_note"] = BP5_FIX_NOTE
    return changes


def _assert_reality() -> list[str]:
    """写盘前先现算核实，事实不成立就**不改**（防把登记改成另一种失真）。"""
    problems: list[str] = []
    if not REGISTRY_TS.is_file():
        problems.append(f"找不到 {REGISTRY_TS}")
    elif "GtG6OtherBond" in REGISTRY_TS.read_text(encoding="utf-8"):
        problems.append(
            "htmlRendererRegistry.ts 里又出现 GtG6OtherBond ⇒ 「别名已消失」的前提不成立，"
            "不得按本脚本改登记"
        )
    if not SPECIALIZED_TS.is_file():
        problems.append(f"找不到 {SPECIALIZED_TS}")
    else:
        src = SPECIALIZED_TS.read_text(encoding="utf-8")
        if "g6-other-bond-investment-ecl" not in src:
            problems.append("specialized.ts 里没有 g6-other-bond-investment-ecl 登记")
        if "GtG6OtherBondInvestmentEcl.vue" not in src:
            problems.append("specialized.ts 里没有 GtG6OtherBondInvestmentEcl.vue 的 import")
    labels = (
        ROOT
        / "audit-platform/frontend/src/components/workpaper/composables/g1SheetLabels.ts"
    )
    if not labels.is_file():
        problems.append(f"找不到 {labels}")
    elif "交易性金融资产实质性程序表G1A '" not in labels.read_text(encoding="utf-8"):
        problems.append(
            "g1SheetLabels.ts 的 G1A 标签不带尾部空格 ⇒ BP-5 未修好，不得把 status 改 FIXED"
        )
    return problems


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

    problems = _assert_reality()
    if problems:
        print("[FAIL] 现算前提不成立，拒绝改登记：", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        return 2

    sl = json.loads(SLICE.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    changes = _slice_changes(sl) + _plan_changes(plan)

    if not changes:
        print("0 项欠账，无需修改")
        return 0
    for c in changes:
        print("  -", c)
    if args.check:
        print(f"共 {len(changes)} 项欠账（--apply 写盘）")
        return 1
    _write(SLICE, sl)
    _write(PLAN, plan)
    print(f"[WRITTEN] {SLICE.name} / {PLAN.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
