# -*- coding: utf-8 -*-
"""L 循环 canary 载荷的 e2e seed（L0~L8 八条 entry 共用一个脚本）。

spec: l-cycle-sync-foundation-and-first-canary · Task 29
      l2-l3-l4-orphan-twins-and-sheet-granularity-collapse · Task 21
      l5-l8-inert-switch-and-child-tab-carriers · Task 25
      l-cycle-true-adapter-registration · Task 1（LR-P3 登记读数的可复算来源）

═══ 为什么要有这个脚本（2026-10-01 新建）═══

三份 L spec 的 tasks.md 都写着「seed 数据已注入 PG」，但**注入动作当时是一次性探针做的、
用完即删**，于是本地 PG 数据一旦丢失（实测 2026-10-01：`checklist_responses` 全表只剩 42 行、
`item_id ~ '^L[0-9]'` **0 行**），七条依赖真库的守卫集体变红，而仓库里**没有任何工具**能把它
恢复 —— 这正是「现算结论不可复算」的典型代价。本脚本把那次注入变成**可复算的正式工具**。

🔴 **边界声明（必须读）**：本脚本造的行是**测试夹具**，不是业务证据。
`backend/tests/workpaper_sync/l1_adapter_facts.py::MEASURED_L_PAYLOAD_2026_09_28` 登记的读数
里，L6/L7/L8 在原 spec 里就自述是「E2E seed 行（已造数据）」⇒ 用本脚本复现它们是等价的；
但任何「按真库行数回填裁决证据」的动作都必须先剔除 `wp_ref = SEED_TAG` 的行。

🔴 **本脚本刻意不造的东西：LC-22 的 L2→G8 跨 entry 污染行。**
那是一条**缺陷现象登记**（lane2 spec Task 7~9*，清理待业务确认）。数据既已随库清空而消失，
再人工造一条出来只是为了让守卫变绿 —— 那是伪造证据。正确处置是把那条守卫改成两态：
不变量（隔离）必须成立 + 显式登记「原违例样本已不在库」+ 配变异证明（扫描器对人造违例必命中）。
见 `test_l_lane2_orphan_and_collapse.py::TestTask7to8CrossEntryPollution`。

═══ 安全设计：只填空、不覆盖（沿用 seed_f345_canary_rows.py 的裁决）═══

  · 目标 key 已有**非本脚本造的行**（`wp_ref` ≠ SEED_TAG）⇒ 跳过并报告（除非 `--force`）
  · 目标 key 已有**本脚本造的行**                        ⇒ 幂等更新（id 不变）
  · 目标 key 无行                                        ⇒ 插入

═══ 载荷形态（与登记读数逐值对齐，禁随手改）═══

    域   行数  remark 非空   组成
    L0     1        1       L0-chk-conclusion
    L1    33       33       L1-adj-{1..4}-{8 字段} = 32 + L1-chk-conclusion
    L2     7        7       L2-adj-1-{4 字段} + L2-chk-conclusion + 2 条备注
                           （登记读数 8 行里第 8 行是 G8 污染行，本脚本不造 ⇒ 这里 7）
    L3    11        7       L3-adj-1-{4 字段} + 3 条备注 + 4 条空 remark（2 NULL / 2 空串）
    L4     6        6       L4-adj-1-{4 字段} + L4-chk-conclusion + L4-3-note
    L5     7        7       L5-adj-1-{4 字段} + L5-chk-conclusion + 2 条备注
    L6/L7/L8 各 5  各 5     L{n}-adj-1-{4 字段} + L{n}-chk-conclusion

  🔴 `L1-adj-*` 只有**第 1 行有真数值**，第 2~4 行八字段**全为字符串 `'0'`** ——
  这是 `test_only_row1_has_real_values` 的判据形态，不是随意填的。
  🔴 `conclusion` 列**一律不写**（全 L 域 conclusion 结构性零是 LR-P4 沿用的结论）。

用法（仓库根，venv python）::

    .venv\\Scripts\\python.exe backend/scripts/e2e/seed_l_cycle_canary_rows.py --check
    .venv\\Scripts\\python.exe backend/scripts/e2e/seed_l_cycle_canary_rows.py --apply
    .venv\\Scripts\\python.exe backend/scripts/e2e/seed_l_cycle_canary_rows.py --apply --cycle L6
    .venv\\Scripts\\python.exe backend/scripts/e2e/seed_l_cycle_canary_rows.py --purge
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Final

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from sqlalchemy import text  # noqa: E402

from app.core.database import engine  # noqa: E402

#: 本脚本造的行都把 `wp_ref` 置成这个值 —— 区分「夹具行」与「真实业务行」的唯一依据。
SEED_TAG: Final[str] = "l-cycle-canary-e2e"

#: `L1-adj-*` 的 8 个字段段（真库实测全集，见 l1_adapter_facts.L1_ADJ_REAL_FIELDS）。
L1_ADJ_FIELDS: Final[tuple[str, ...]] = (
    "beginning",
    "unadjusted",
    "aje",
    "rje",
    "audited",
    "creditAmount",
    "debitAmount",
    "endBalance",
)

#: 简化域（L2~L8）各自 `adj-1-` 行用的 4 个字段段。
SHORT_ADJ_FIELDS: Final[tuple[str, ...]] = ("beginning", "creditAmount", "debitAmount", "endBalance")

#: 第 1 行的真数值（负债口径：期末 = 期初 + 贷方 - 借方）。
_ROW1: Final[dict[str, str]] = {
    "beginning": "1200000.00",
    "unadjusted": "1500000.00",
    "aje": "0",
    "rje": "0",
    "audited": "1500000.00",
    "creditAmount": "800000.00",
    "debitAmount": "500000.00",
    "endBalance": "1500000.00",
}

_SHORT_ROW1: Final[dict[str, str]] = {
    "beginning": "600000.00",
    "creditAmount": "250000.00",
    "debitAmount": "100000.00",
    "endBalance": "750000.00",
}


def _blank(index: int) -> str | None:
    """L3 的 4 条空 remark：2 条 NULL / 2 条空串（铁律⑧：两者必须分开造）。"""
    return None if index < 2 else ""


def build_plan() -> dict[str, list[tuple[str, str | None]]]:
    """返回 {wp_code: [(item_id, remark), ...]}。remark 为 None 表示写 NULL。"""
    plan: dict[str, list[tuple[str, str | None]]] = {}

    plan["L0"] = [("L0-chk-conclusion", "L0 底稿目录已复核，科目归属与循环分类一致。")]

    l1: list[tuple[str, str | None]] = []
    for row in range(1, 5):
        for field in L1_ADJ_FIELDS:
            value = _ROW1[field] if row == 1 else "0"
            l1.append((f"L1-adj-{row}-{field}", value))
    l1.append(
        (
            "L1-chk-conclusion",
            "短期借款审定表已与明细表 SUMIF 取数核对一致，期末余额与试算表无差异。",
        )
    )
    plan["L1"] = l1

    # L2：登记读数 8 行里第 8 行是 LC-22 的 G8 污染行，本脚本刻意不造（见模块 docstring）。
    plan["L2"] = [
        *[(f"L2-adj-1-{f}", _SHORT_ROW1[f]) for f in SHORT_ADJ_FIELDS],
        ("L2-chk-conclusion", "应付利息审定表已复核，计提与支付匹配。"),
        ("L2-int-1-note", "按合同利率与实际天数重算，差异在重要性水平以下。"),
        ("L2-ovd-1-note", "无逾期应付利息。"),
    ]

    l3: list[tuple[str, str | None]] = [
        *[(f"L3-adj-1-{f}", _SHORT_ROW1[f]) for f in SHORT_ADJ_FIELDS],
        ("L3-chk-conclusion", "长期借款审定表已复核，一年内到期部分已重分类。"),
        ("L3-ovd-1-note", "无逾期长期借款。"),
        ("L3-det-1-note", "抽取 3 份借款合同核对本金、利率与期限，一致。"),
    ]
    for i in range(4):
        l3.append((f"L3-blank-{i + 1}", _blank(i)))
    plan["L3"] = l3

    plan["L4"] = [
        *[(f"L4-adj-1-{f}", _SHORT_ROW1[f]) for f in SHORT_ADJ_FIELDS],
        ("L4-chk-conclusion", "应付债券审定表已复核，溢折价摊销按实际利率法计算。"),
        ("L4-3-note", "债券利息调整期末余额已与摊销表核对一致。"),
    ]

    plan["L5"] = [
        *[(f"L5-adj-1-{f}", _SHORT_ROW1[f]) for f in SHORT_ADJ_FIELDS],
        ("L5-chk-conclusion", "长期应付款审定表已复核，未确认融资费用摊销无误。"),
        ("L5-1-note", "专项应付款与政府补助文件核对一致。"),
        ("L5-2-note", "无需重分类至一年内到期的非流动负债。"),
    ]

    for code, note in (
        ("L6", "专项应付款审定表已复核，拨款文件与用途一致。"),
        ("L7", "其他非流动负债审定表已复核，期末余额与明细一致。"),
        ("L8", "财务费用审定表已复核，利息支出与借款测算表一致。"),
    ):
        plan[code] = [
            *[(f"{code}-adj-1-{f}", _SHORT_ROW1[f]) for f in SHORT_ADJ_FIELDS],
            (f"{code}-chk-conclusion", note),
        ]

    return plan


_TARGET_SQL = """
SELECT wp.id::text AS wp_id, wp.project_id::text AS project_id
FROM working_paper wp JOIN wp_index wi ON wi.id = wp.wp_index_id
WHERE wi.wp_code = :code
  AND COALESCE(wp.is_deleted, false) = false
  AND COALESCE(wp.file_path, '') <> ''
ORDER BY wp.created_at, wp.id
LIMIT 1
"""


async def resolve_targets(codes: list[str]) -> dict[str, dict[str, str]]:
    """每个 wp_code 取「有真实 file_path 的最早一条」—— 确定性排序，重跑选同一条。

    🔴 用 `COALESCE(file_path,'') <> ''` 而不是 `file_path IS NOT NULL`：
    真库里 L1-2 / L2-2 之类索引行的 file_path 是**空字符串**，按 NOT NULL 判会选中没有
    工作簿的索引行（该陷阱已在 `workpaper_sync_entry_wp_code_adjudication.json` 里登记过一次）。
    """
    out: dict[str, dict[str, str]] = {}
    for code in codes:
        async with engine.connect() as conn:
            row = (await conn.execute(text(_TARGET_SQL), {"code": code})).first()
        if row is None:
            out[code] = {"error": f"wp_code={code} 无可用底稿（未删除且 file_path 非空）"}
        else:
            out[code] = {"wp_id": row.wp_id, "project_id": row.project_id}
    return out


_EXISTING_SQL = """
SELECT item_id, wp_ref FROM checklist_responses
WHERE wp_id = CAST(:wp_id AS uuid) AND item_id = ANY(:item_ids)
"""

_UPSERT_SQL = """
INSERT INTO checklist_responses (project_id, wp_id, item_id, remark, wp_ref)
VALUES (CAST(:project_id AS uuid), CAST(:wp_id AS uuid), :item_id, :remark, :wp_ref)
"""

_UPDATE_SQL = """
UPDATE checklist_responses SET remark = :remark, wp_ref = :wp_ref, updated_at = now()
WHERE wp_id = CAST(:wp_id AS uuid) AND item_id = :item_id
"""

_PURGE_SQL = """
DELETE FROM checklist_responses WHERE wp_ref = :wp_ref AND item_id ~ '^L[0-8]-'
"""


async def run(*, mode: str, cycles: list[str], force: bool) -> dict[str, Any]:
    plan = build_plan()
    codes = [c for c in plan if not cycles or c in cycles]
    targets = await resolve_targets(codes)

    report: dict[str, Any] = {"mode": mode, "cycles": codes, "entries": [], "errors": []}

    if mode == "purge":
        async with engine.begin() as conn:
            result = await conn.execute(text(_PURGE_SQL), {"wp_ref": SEED_TAG})
        report["purged_rows"] = result.rowcount
        return report

    for code in codes:
        target = targets[code]
        if "error" in target:
            report["errors"].append({"cycle": code, "error": target["error"]})
            continue
        rows = plan[code]
        item_ids = [item for item, _ in rows]
        async with engine.connect() as conn:
            existing = {
                r.item_id: r.wp_ref
                for r in (
                    await conn.execute(
                        text(_EXISTING_SQL), {"wp_id": target["wp_id"], "item_ids": item_ids}
                    )
                ).fetchall()
            }
        foreign = sorted(k for k, ref in existing.items() if ref != SEED_TAG)
        entry: dict[str, Any] = {
            "cycle": code,
            "wp_id": target["wp_id"][:8],
            "planned": len(rows),
            "existing_seed": sum(1 for ref in existing.values() if ref == SEED_TAG),
            "existing_foreign": foreign,
            "would_insert": sum(1 for item in item_ids if item not in existing),
            "would_update": sum(1 for item in item_ids if existing.get(item) == SEED_TAG),
        }
        if foreign and not force:
            entry["action"] = "skipped_foreign_payload"
            report["entries"].append(entry)
            continue
        if mode == "check":
            entry["action"] = "would_apply"
            report["entries"].append(entry)
            continue

        inserted = updated = 0
        async with engine.begin() as conn:
            for item_id, remark in rows:
                params = {
                    "project_id": target["project_id"],
                    "wp_id": target["wp_id"],
                    "item_id": item_id,
                    "remark": remark,
                    "wp_ref": SEED_TAG,
                }
                if item_id in existing:
                    await conn.execute(text(_UPDATE_SQL), params)
                    updated += 1
                else:
                    await conn.execute(text(_UPSERT_SQL), params)
                    inserted += 1
        entry["action"] = "applied"
        entry["inserted"] = inserted
        entry["updated"] = updated
        report["entries"].append(entry)

    return report


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="L 循环 canary 载荷 seed（幂等，只填空不覆盖）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="只预演（默认）")
    group.add_argument("--apply", action="store_true", help="真写库")
    group.add_argument("--purge", action="store_true", help="删除本脚本造的所有 L 域 seed 行")
    parser.add_argument("--cycle", action="append", default=[], help="只处理这些域，如 --cycle L6")
    parser.add_argument(
        "--force", action="store_true", help="目标 key 已有非 seed 载荷时仍覆盖（默认拒绝）"
    )
    args = parser.parse_args(argv)
    mode = "apply" if args.apply else "purge" if args.purge else "check"

    try:
        report = await run(mode=mode, cycles=[c.upper() for c in args.cycle], force=args.force)
    finally:
        await engine.dispose()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report.get("errors") else 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(list(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":
    raise SystemExit(main())
