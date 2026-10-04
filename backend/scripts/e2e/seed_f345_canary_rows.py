# -*- coding: utf-8 -*-
"""F3 / F4 / F5 canary 受管行表的 e2e seed（三 spec 共用一个脚本）。

spec: f3-sync-coverage-and-first-canary · Task 12
      f4-sync-coverage-and-first-canary · Task 11
      f5-sync-coverage-and-first-canary · Task 11

═══ 为什么三 spec 共用一个脚本（而不是 seed_f3/f4/f5 三份）═══

三份 spec 各自写了「照 D4/E1 lane 的 seed 范式」，但三者要造的东西**逐字同构**：
往 `checklist_responses` 写一条 `(wp_id, item_id)` 的行数组载荷。分成三份文件会造三处
重复实现，而 seed 脚本的风险点（覆盖真实数据、行身份不稳定、非幂等）需要一次修对、
三处生效。故做成 `--entry f3|f4|f5|all` 单脚本；三份 tasks.md 均指向本文件。

═══ 🔴 安全设计：默认**绝不覆盖**已有载荷 ═══

`g-cycle-sync-foundation-and-first-canary` 的裁决 GF-H2 拒绝交付 seed 脚本，理由是
「seed 会覆盖真实数据，且掩盖『空表往返也算 store_mirrored』的假绿」。这两条都成立，
但结论不必是"不做 seed" —— 可以做成**只填空、不覆盖**：

  · 目标 key 已有 **非 seed 行**（缺少 `_seed` 标记）  ⇒ 直接拒绝（除非 `--force`）
  · 目标 key 已有 **本脚本造的 seed 行**              ⇒ 幂等覆盖（行身份不变）
  · 目标 key 无载荷                                   ⇒ 写入

F3 的 canary（`F3-5-rows`）真库**已有 2 行真实行身份**（业务值为空），所以 `--entry f3`
默认按 **no_seed** 处置并如实报告；只有显式 `--fill-blank-values` 才会补业务值，且仍
**保留原 rowId**（不新造行）—— 行身份是 roundtrip 的锚，换 id 等于把 A 行的值并进 B 行。

═══ 真库实测（2026-09-27，PG `audit_platform`）═══

    item_id                      bytes  rows   处置
    F3-5-rows                      675     2   已有真行身份（业务值空）⇒ 默认 no_seed
    F4-6-rows                        -     -   不存在 ⇒ 需 seed
    F5-8-rows                        -     -   不存在 ⇒ 需 seed
    F5-1-adj-other-rows              -     -   不存在 ⇒ 需 seed（Task 21 受管区）

F4 全库仅 `F4-2-rows`(3485B) / `F4-7-estimated-inbound-rows`(1211B) 有载荷 —— 都**不是**
canary 选的 F4-6；F5 全库 **零** F5-* 载荷（与 spec「F5 是零载荷 entry」一致）。

三个目标 wp 取同一项目 `0ec33ac9-…`（G2 lane 用的也是它），便于 e2e 串起来跑。

用法（backend 目录，venv python）:
    ..\\.venv\\Scripts\\python.exe scripts/e2e/seed_f345_canary_rows.py --dry-run
    ..\\.venv\\Scripts\\python.exe scripts/e2e/seed_f345_canary_rows.py --entry f4
    ..\\.venv\\Scripts\\python.exe scripts/e2e/seed_f345_canary_rows.py --check --json
    ..\\.venv\\Scripts\\python.exe scripts/e2e/seed_f345_canary_rows.py --purge --entry f5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Final

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

#: 本脚本造的行都带这个标记键 —— 用于区分「seed 行」与「真实行」，是不覆盖真数据的依据。
#:
#: 🔴 边界：带此标记的载荷**不构成业务载荷证据**。
#: `backend/data/workpaper_sync_entry_wp_code_adjudication.json` 的
#: `store_payload_evidence.max_payload_bytes=0`（F5）记的是**真实业务载荷**为 0，
#: 该 note 本身已预告「验收前必须先 seed」⇒ seed 后真库非 0 是预期行为，不是证据过时。
#: 任何按真库行数回填裁决证据的脚本都必须先剔除带此标记的行。
SEED_MARKER: Final[str] = "_seed"
SEED_TAG: Final[str] = "f345-canary-e2e"

#: 三个 canary 目标（wp_id / project_id 来自真库实测，见模块 docstring）。
PROJECT_ID: Final[str] = "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49"

TARGETS: Final[dict[str, dict[str, Any]]] = {
    "f3": {
        "wp_id": "5424b674-ce48-44d2-917e-2bd763fe827f",
        "wp_code": "F3",
        "item_id": "F3-5-rows",
        "sheet": "逾期票据检查F3-5",
        "row_identity_key": "rowId",
        # 🔴 真库已有 2 行真实行身份 ⇒ 默认不 seed（见 docstring 安全设计）。
        "policy": "no_seed_has_real_identity",
        "rows": [
            {
                "rowId": "f3-canary-e2e-0001",
                "seq": 1,
                "billType": "银行承兑汇票",
                "drawer": "E2E 测试出票人",
                "billNo": "F3-E2E-0001",
                "faceAmount": 100000,
                "overdueDays": 30,
            }
        ],
    },
    "f4": {
        "wp_id": "e4f00fc1-de91-4f8b-89d8-a968268c250e",
        "wp_code": "F4",
        "item_id": "F4-6-rows",
        "sheet": "关联方及交易检查表F4-6",
        "row_identity_key": "rowId",
        "policy": "seed_required_zero_payload",
        "rows": [
            {
                "rowId": "f4-canary-e2e-0001",
                "relatedPartyName": "E2E 关联方甲",
                "relationship": "合并范围内关联方",
                # C/E/D → F 由模板公式 =C+E-D 算（不 seed F 列，验证公式未被投影覆盖）
                "openingBalance": 50000,
                "currentDebit": 20000,
                "currentCredit": 30000,
            },
            {
                "rowId": "f4-canary-e2e-0002",
                "relatedPartyName": "E2E 关联方乙",
                "relationship": "合并范围外关联方",
                "openingBalance": 10000,
                "currentDebit": 0,
                "currentCredit": 5000,
            },
        ],
    },
    "f5": {
        "wp_id": "b751f499-f005-4ffe-a939-99fd7544fe9a",
        "wp_code": "F5",
        "item_id": "F5-8-rows",
        "sheet": "重大调整核查表F5-8",
        # 🔴 F5-2/3/5/8 行身份是 `id`（不是 rowId）——按值实测所得。
        "row_identity_key": "id",
        "policy": "seed_required_zero_payload",
        "rows": [
            {
                "id": "f5-canary-e2e-0001",
                "date": "2099-12-31",
                "voucherNo": "E2E-JE-0001",
                "itemContent": "E2E 重大成本调整事项",
                "debitAmount": 80000,
                "creditAmount": 0,
                "adjustmentReason": "e2e 往返验证用",
                "reasonAdequate": "是",
            }
        ],
    },
    #: Task 21 新增的 F5-1 其他业务区（行身份是 `rowKey`，与同册 F5-8 的 `id` 不同）。
    "f5-1": {
        "wp_id": "b751f499-f005-4ffe-a939-99fd7544fe9a",
        "wp_code": "F5",
        "item_id": "F5-1-adj-other-rows",
        "sheet": "营业务成本审定表F5-1",
        "row_identity_key": "rowKey",
        "policy": "seed_required_zero_payload",
        "rows": [
            {
                "rowKey": "other-canary-e2e-0001",
                "label": "E2E 运输成本",
                "isFixed": False,
                "currentUnadjusted": 120000,
                "currentAje": 0,
                "currentRje": 0,
                "priorUnadjusted": 100000,
                "priorAje": 0,
                "priorRje": 0,
                "indexRef": "F5-3",
            }
        ],
    },
}

ENTRY_CHOICES: Final[tuple[str, ...]] = ("f3", "f4", "f5", "f5-1", "all")


def _selected(entry: str) -> list[str]:
    if entry == "all":
        return [k for k in TARGETS if k != "f3"] + ["f3"]
    return [entry]


def _tagged_rows(target: dict[str, Any]) -> list[dict[str, Any]]:
    """给每行打 seed 标记（用于后续识别"这是 seed 造的、可安全覆盖"）。"""
    out: list[dict[str, Any]] = []
    for row in target["rows"]:
        merged = dict(row)
        merged[SEED_MARKER] = SEED_TAG
        out.append(merged)
    return out


def _is_seed_payload(payload: str | None) -> bool:
    """载荷里**每一行**都带本脚本标记 ⇒ 可安全幂等覆盖。"""
    if not payload:
        return False
    try:
        rows = json.loads(payload)
    except (ValueError, TypeError):
        return False
    if not isinstance(rows, list) or not rows:
        return False
    return all(
        isinstance(r, dict) and r.get(SEED_MARKER) == SEED_TAG for r in rows
    )


def _row_count(payload: str | None) -> int:
    if not payload:
        return 0
    try:
        rows = json.loads(payload)
    except (ValueError, TypeError):
        return 0
    return len(rows) if isinstance(rows, list) else 0


def _print_plan(entry: str) -> None:
    print("=" * 78)
    print("[dry-run] 不写库，仅打印将要造的载荷")
    for key in _selected(entry):
        t = TARGETS[key]
        rows = _tagged_rows(t)
        print("-" * 78)
        print(f"entry={key}  policy={t['policy']}")
        print(f"  wp_id      = {t['wp_id']}  (project {PROJECT_ID}, {t['wp_code']})")
        print(f"  item_id    = {t['item_id']}   sheet = {t['sheet']}")
        print(f"  行身份键   = {t['row_identity_key']}")
        print(f"  行数       = {len(rows)}")
        print(f"  载荷字节   = {len(json.dumps(rows, ensure_ascii=False))}")
        if t["policy"] == "no_seed_has_real_identity":
            print(
                "  🔴 默认 **不写**：真库已有真实行身份，覆盖会毁掉 roundtrip 的锚。\n"
                "     只有 --fill-blank-values 才补业务值（且保留原行身份）。"
            )
        for r in rows:
            print(f"    · {r[t['row_identity_key']]}")
    print("=" * 78)


async def _fetch_existing(session: Any, wp_id: str, item_id: str) -> str | None:
    import sqlalchemy as sa

    row = (
        await session.execute(
            sa.text(
                "SELECT remark FROM checklist_responses "
                "WHERE wp_id = CAST(:wp AS uuid) AND item_id = :item"
            ),
            {"wp": wp_id, "item": item_id},
        )
    ).first()
    return None if row is None else row[0]


async def _seed(entry: str, *, force: bool, fill_blank: bool) -> dict[str, Any]:
    import sqlalchemy as sa

    from app.core.database import async_session

    results: list[dict[str, Any]] = []
    async with async_session() as session:
        for key in _selected(entry):
            t = TARGETS[key]
            existing = await _fetch_existing(session, t["wp_id"], t["item_id"])
            existing_rows = _row_count(existing)
            is_seed = _is_seed_payload(existing)

            # ── 决策：写 / 跳过 / 拒绝 ──────────────────────────────────────
            if t["policy"] == "no_seed_has_real_identity" and not fill_blank:
                results.append(
                    {
                        "entry": key,
                        "item_id": t["item_id"],
                        "action": "skipped_no_seed",
                        "existing_rows": existing_rows,
                        "reason": "真库已有真实行身份；按 no_seed 处置（--fill-blank-values 可补业务值）",
                    }
                )
                continue

            if existing_rows > 0 and not is_seed and not force:
                results.append(
                    {
                        "entry": key,
                        "item_id": t["item_id"],
                        "action": "refused_would_overwrite_real_data",
                        "existing_rows": existing_rows,
                        "reason": "载荷存在且不含 seed 标记 ⇒ 疑为真实数据，拒绝覆盖（--force 可强制）",
                    }
                )
                continue

            payload = json.dumps(_tagged_rows(t), ensure_ascii=False)
            await session.execute(
                sa.text(
                    "INSERT INTO checklist_responses "
                    "  (project_id, wp_id, item_id, conclusion, remark) "
                    "VALUES (CAST(:pid AS uuid), CAST(:wp AS uuid), :item, NULL, :remark) "
                    "ON CONFLICT (wp_id, item_id) DO UPDATE "
                    "SET remark = EXCLUDED.remark, updated_at = now()"
                ),
                {
                    "pid": PROJECT_ID,
                    "wp": t["wp_id"],
                    "item": t["item_id"],
                    "remark": payload,
                },
            )
            results.append(
                {
                    "entry": key,
                    "item_id": t["item_id"],
                    "action": "upserted",
                    "rows": len(t["rows"]),
                    "bytes": len(payload),
                    "was_seed": is_seed,
                }
            )
        await session.commit()
    return {"seed": results}


async def _purge(entry: str) -> dict[str, Any]:
    """只删本脚本造的载荷（逐行核 seed 标记；真实数据一律不动）。"""
    import sqlalchemy as sa

    from app.core.database import async_session

    results: list[dict[str, Any]] = []
    async with async_session() as session:
        for key in _selected(entry):
            t = TARGETS[key]
            existing = await _fetch_existing(session, t["wp_id"], t["item_id"])
            if existing is None:
                results.append({"entry": key, "item_id": t["item_id"], "action": "absent"})
                continue
            if not _is_seed_payload(existing):
                results.append(
                    {
                        "entry": key,
                        "item_id": t["item_id"],
                        "action": "kept_not_seed",
                        "existing_rows": _row_count(existing),
                        "reason": "载荷不含 seed 标记 ⇒ 是真实数据，purge 不动它",
                    }
                )
                continue
            await session.execute(
                sa.text(
                    "DELETE FROM checklist_responses "
                    "WHERE wp_id = CAST(:wp AS uuid) AND item_id = :item"
                ),
                {"wp": t["wp_id"], "item": t["item_id"]},
            )
            results.append({"entry": key, "item_id": t["item_id"], "action": "deleted"})
        await session.commit()
    return {"purge": results}


async def _check(entry: str) -> dict[str, Any]:
    from app.core.database import async_session

    results: list[dict[str, Any]] = []
    async with async_session() as session:
        for key in _selected(entry):
            t = TARGETS[key]
            existing = await _fetch_existing(session, t["wp_id"], t["item_id"])
            results.append(
                {
                    "entry": key,
                    "item_id": t["item_id"],
                    "wp_id": t["wp_id"],
                    "exists": existing is not None,
                    "rows": _row_count(existing),
                    "bytes": len(existing) if existing else 0,
                    "is_seed_payload": _is_seed_payload(existing),
                    "row_identity_key": t["row_identity_key"],
                }
            )
    return {"check": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", choices=ENTRY_CHOICES, default="all")
    parser.add_argument("--dry-run", action="store_true", help="离线打印将造什么，不写库")
    parser.add_argument("--check", action="store_true", help="查三个 canary key 的当前载荷")
    parser.add_argument("--purge", action="store_true", help="删本脚本造的载荷（真实数据不动）")
    parser.add_argument(
        "--force",
        action="store_true",
        help="🔴 强制覆盖已有的**非 seed** 载荷（会毁真实数据，慎用）",
    )
    parser.add_argument(
        "--fill-blank-values",
        action="store_true",
        help="对 policy=no_seed 的 entry（F3）也写入（仍用脚本内声明的行身份）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    if args.dry_run:
        _print_plan(args.entry)
        return 0

    if args.purge:
        out = asyncio.run(_purge(args.entry))
    elif args.check:
        out = asyncio.run(_check(args.entry))
    else:
        out = asyncio.run(
            _seed(args.entry, force=args.force, fill_blank=args.fill_blank_values)
        )

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for section, rows in out.items():
            print(f"── {section} ──")
            for r in rows:
                print("  " + json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
