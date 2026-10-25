# -*- coding: utf-8 -*-
"""生成前端的「受管 sheet 清单」投影 —— Property 15 的 provider 派生真源。

spec: d567-sync-coverage-via-row-table-engine · Task 22 · Property 15
（同族需求见 umbrella `workpaper-html-onlyoffice-bidirectional-writeback-closure`）

═══ 为什么需要这个产物（Property 15 的裁决依据）═══

三个宿主（D5/D6/D7）原来把受管 sheet **写死成一张**：

    const D5_MANAGED_SHEET_KEY = 'd52-managed'
    const isD5DetailSheet = computed(() => currentSheet.value === 'D5-2')

而 provider 侧受管区早已扩到 **D5 3 张 / D6 7 张 / D7 6 张**。写死的后果是：其余受管 sheet
在前端根本进不了在线编辑通道 —— 声明层扩了、UI 不认，是典型的「两个真源」缺陷
（同 `workpaperEntrySyncNotice.ts` docstring 记载过的那次：手工数组漏抄一行，
真双向底稿上一直显示「两侧数据未互通」）。

═══ 为什么落在这个新产物、而不是别的三条路 ═══

| 候选 | 裁决 | 理由 |
|---|---|---|
| render-config 加字段 | ❌ | 它是 **per-workpaper 运行时**配置；受管清单是 **per-entry 静态声明**，放进去等于把静态事实塞进运行时链路，还要多一层后端拼装 + 前端解析 |
| 新端点 | ❌ | 静态声明不需要运行时端点；且同类信息（capability / migration_state）早已走生成产物下发 |
| 扩 `workpaperSyncManifest.generated.ts` | ❌ | 那是 **155 entry** 的 CI 门控共享产物，加字段会动 `manifest_digest`，波及面大；且它的输入是 discoverer + overlay，**不读契约**，要接契约得改它的取数骨架 |
| **新建本产物** | ✅ | 与既有「一个关注点一个 generated 文件」约定一致（manifest / contract / legacyBaseline / canonicalGolden / programMilestones 已各自独立）；输入只有契约链，爆炸半径最小 |

═══ 取数链（零新增声明，三段全是既有真源）═══

    entry_id
      → `adapters.registry.DELIVERED_PER_ENTRY_CONTRACTS`（L3 判据用的同一张表）→ contract_id
      → `contracts.contract_path_for(contract_id)`（全仓唯一拼契约路径处）→ 契约 JSON
      → `sheets[].{sheet_key, excel_name}` → 受管 sheet 清单

🔴 **关键点：这条链不依赖 adapter 是否已注册**。`DELIVERED_PER_ENTRY_CONTRACTS` 的行里
`adapter_registered` 是**独立字段**（D5/D6/D7 当前均为 `False`），所以「契约已交付」与
「adapter 已注册」是两个分母 —— 受管 sheet 清单属前者，现在就能下发；OO 能否真用属后者，
由 manifest 的 `capability` 与 `GtEntrySyncCapabilityNotice` 各自表达。**不要把两者混成一个门**。

🔴 **`excel_name` 是权威 sheet 名，不做任何字符串推演**（裁决 G3：`managed_sheet` 逐个实测、
禁按模式推演）。前端拿到 `excelName` 后用它**自己已有的**循环归一函数（`resolveD5SheetCode` 等）
换成页签码 —— 归一规则留在前端，本产物只负责把后端事实原样送过去。

输出**幂等**：内容只由上面那条链决定，不含时间戳/随机量 ⇒ `--check` 可作 CI 漂移门。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_TARGET = (
    _REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "workpaperSyncManagedSheets.generated.ts"
)


class ManagedSheetsGenerationError(RuntimeError):
    """取数链任一段不成立即 fail closed（不产半份产物）。"""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def collect_facts() -> dict[str, Any]:
    """现算 entry_id → 受管 sheet 清单。任一段缺失即抛（不静默跳过）。"""
    from app.services.workpaper_sync.adapters.registry import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )
    from app.services.workpaper_sync.contracts import contract_path_for

    rows = list(DELIVERED_PER_ENTRY_CONTRACTS)
    if not rows:
        raise ManagedSheetsGenerationError(
            "DELIVERED_PER_ENTRY_CONTRACTS 为空 —— 取数链断了，不产空产物"
        )

    entries: list[dict[str, Any]] = []
    for row in rows:
        entry_id = row.get("entry_id")
        contract_id = row.get("contract_id")
        if not entry_id or not contract_id:
            raise ManagedSheetsGenerationError(
                f"登记行缺 entry_id/contract_id: {row!r}"
            )
        path = contract_path_for(contract_id)
        if not path.is_file():
            raise ManagedSheetsGenerationError(
                f"{entry_id}: 契约文件不存在 {path} —— 登记表与磁盘不一致"
            )
        contract = json.loads(path.read_text(encoding="utf-8"))
        sheets = contract.get("sheets") or []
        if not sheets:
            raise ManagedSheetsGenerationError(f"{entry_id}: 契约无 sheets")
        managed: list[dict[str, str]] = []
        for sheet in sheets:
            sheet_key = sheet.get("sheet_key")
            excel_name = sheet.get("excel_name")
            if not sheet_key or not excel_name:
                raise ManagedSheetsGenerationError(
                    f"{entry_id}/{contract_id}: sheet 缺 sheet_key 或 excel_name -> {sheet!r}"
                )
            managed.append({"sheetKey": sheet_key, "excelName": excel_name})
        managed.sort(key=lambda item: item["sheetKey"])
        entries.append(
            {
                "entryId": entry_id,
                "contractId": contract_id,
                # 🔴 独立字段：受管清单**不**因它为 False 而缺省（见模块 docstring）
                "adapterRegistered": bool(row.get("adapter_registered")),
                "managedSheets": managed,
            }
        )
    entries.sort(key=lambda item: item["entryId"])
    payload = json.dumps(entries, ensure_ascii=False, indent=2, sort_keys=True)
    return {
        "entries": entries,
        "payload_json": payload,
        "digest": _sha256_text(payload),
        "entry_count": len(entries),
        "sheet_count": sum(len(e["managedSheets"]) for e in entries),
    }


def render(facts: dict[str, Any]) -> str:
    return f'''/**
 * 本文件由 `backend/scripts/gen/generate_workpaper_sync_managed_sheets.py` 生成，请勿手工编辑。
 *
 * 真源链（三段全是既有真源，零新增声明）：
 *   `adapters.registry.DELIVERED_PER_ENTRY_CONTRACTS` → contract_id
 *   → `contracts.contract_path_for` → `backend/data/workpaper_sync_contracts/*.json`
 *   → `sheets[].{{sheet_key, excel_name}}`
 *
 * spec: d567-sync-coverage-via-row-table-engine · Task 22 · Property 15
 *
 * 🔴 `adapterRegistered` 与 `managedSheets` 是**两个分母**：受管清单来自「契约已交付」，
 *    adapter 是否注册另算。前端判「这张 sheet 是否受管」只看 `managedSheets`；
 *    判「OO 能否真用」看 manifest 的 `capability`。别把两者混成一个门。
 *
 * 🔴 `excelName` 是**后端权威 sheet 名**，不要在前端做字符串推演拼页签码 ——
 *    用各循环自己的归一函数（`resolveD5SheetCode` 等）换算。
 */

export interface WorkpaperSyncManagedSheet {{
  /** 契约里的受管区键（如 `d52-managed`） */
  readonly sheetKey: string
  /** 模板册里的真实 Excel sheet 名（如 `应收款项融资明细表D5-2`） */
  readonly excelName: string
}}

export interface WorkpaperSyncManagedSheetsEntry {{
  readonly entryId: string
  readonly contractId: string
  /** adapter 是否已注册 —— **不影响** managedSheets 是否下发 */
  readonly adapterRegistered: boolean
  readonly managedSheets: readonly WorkpaperSyncManagedSheet[]
}}

export const WORKPAPER_SYNC_MANAGED_SHEETS_DIGEST = "{facts['digest']}"

export const WORKPAPER_SYNC_MANAGED_SHEETS: readonly WorkpaperSyncManagedSheetsEntry[] =
{facts['payload_json']} as const

/** entry_id → 受管 sheet 清单（未登记 entry 返回空数组，fail-closed 为「无受管 sheet」）。 */
export function managedSheetsForEntry(
  entryId: string,
): readonly WorkpaperSyncManagedSheet[] {{
  const hit = WORKPAPER_SYNC_MANAGED_SHEETS.find((e) => e.entryId === entryId)
  return hit ? hit.managedSheets : []
}}
'''


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成受管 sheet 清单前端投影")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="校验产物是否最新")
    mode.add_argument("--apply", action="store_true", help="原子重生成")
    args = parser.parse_args(argv)

    facts = collect_facts()
    content = render(facts)
    print(
        f"[SOURCE] entries={facts['entry_count']} managed_sheets={facts['sheet_count']}"
    )
    if args.check:
        if not _TARGET.is_file():
            print(f"[FAIL] missing: {_TARGET.relative_to(_REPO)}")
            return 2
        if _TARGET.read_text(encoding="utf-8") != content:
            print(f"[FAIL] stale: {_TARGET.relative_to(_REPO)}")
            print(
                "       run: py -3 backend/scripts/gen/"
                "generate_workpaper_sync_managed_sheets.py --apply"
            )
            return 2
        print(f"[OK] managed sheets digest {facts['digest']}")
        return 0
    _atomic_write(_TARGET, content)
    print(f"[APPLIED] {_TARGET.relative_to(_REPO)}")
    print(f"[OK] managed sheets digest {facts['digest']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManagedSheetsGenerationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
