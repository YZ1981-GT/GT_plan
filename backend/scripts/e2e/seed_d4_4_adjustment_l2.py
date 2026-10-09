# -*- coding: utf-8 -*-
"""D4-4 调整分录汇总 L2 验收 seed（spec d4-4-adjustment-summary-bidirectional-writeback Task 15*）。

═══ 为什么需要它 ═══

L2 验收要在真 OO canvas 里改一个受管格再看它回到 HTML store。若 `D4-4-rows` 为空或
全空白，OO→HTML 回写会落进 `empty_payload_skip`（mirror 的护栏：`applied <= 0 and
base_rows` 就跳过写库），于是 L2 既不报错也没有可观察结果 —— 那是**假通过**。

现查（2026-09-28）：
  · wp `b3ab3c46-…`（项目 `0ec33ac9-…`，54 个 D4 item，本轮 T10* 发布链的目标）
    **没有** `D4-4-rows`；
  · wp `21d8089b-…`（另一个项目）有 `D4-4-rows`，但 3 行全空白
    （`category` 是默认值「账项调整」、金额全 0、其余字段空串）。

本脚本给 **T10* 的那个 wp** 造带借贷金额的业务行，使 L2 有可观察载荷。

═══ 数据的性质（不是伪造审计结论）═══

造的是**可识别的验收样本**：`description` 前缀 `[L2验收]`、`indexRef` 指向 D4-2、
借贷金额成对且合计相等（满足 D4-4 的借贷平衡语义，否则前端「确认调整」按钮 disabled、
页面状态与真实使用不符）。**不冒充任何审计判断**，且 `--purge` 可完整撤销。

rowId 用前端 `generateRowId()` 的真实形态 `d4a-{base36}-{7位随机}`，
并**固定**取值（不随机）以保证幂等与可追溯 —— 两种行身份格式并存是本表特性
（另一种是导入侧的 uuid4），这里选前端格式因为 L2 模拟的是用户在页面上建行。

用法：
    python backend/scripts/e2e/seed_d4_4_adjustment_l2.py --check     # 只看现状
    python backend/scripts/e2e/seed_d4_4_adjustment_l2.py --dry-run   # 打印将写什么
    python backend/scripts/e2e/seed_d4_4_adjustment_l2.py --apply     # 写库（幂等）
    python backend/scripts/e2e/seed_d4_4_adjustment_l2.py --purge     # 撤销
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
os.environ.setdefault("DB_DISABLE_SSL", "True")

import sqlalchemy as sa  # noqa: E402

#: T10* 发布链的目标（`fix_task76_provision...--check` 解析出的 wp，非硬编码猜测）。
PROJECT_ID = "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49"
WP_ID = "b3ab3c46-828f-4f48-950e-aee9bbdc923f"
ITEM_ID = "D4-4-rows"

#: 验收样本前缀 —— `--purge` 与人工辨识都靠它。
MARK = "[L2验收]"

#: 三行成对分录，借贷各自合计 168000.00（借贷平衡，与前端 computed 一致）。
#: rowId 固定（不随机）以保幂等；形态取前端 generateRowId() 的 `d4a-{base36}-{rand}`。
SEED_ROWS: list[dict[str, Any]] = [
    {
        "rowId": "d4a-l2seed001-a1b2c3d",
        "description": f"{MARK}跨期收入调整：12月已发货未开票收入补记",
        "category": "账项调整",
        "reportItem": "营业收入",
        "accountName": "主营业务收入",
        "noteItem": "五、1 营业收入",
        "placeholder": "见 D4-2 产品明细第 3 行",
        "debitAmount": 0.0,
        "creditAmount": 120000.0,
        "indexRef": "D4-2",
        "remark": "已取得发货单与验收签收记录",
    },
    {
        "rowId": "d4a-l2seed002-d4e5f6g",
        "description": f"{MARK}跨期收入调整：对应应收账款",
        "category": "账项调整",
        "reportItem": "应收账款",
        "accountName": "应收账款",
        "noteItem": "五、3 应收账款",
        "placeholder": "与上一行为同一笔分录",
        "debitAmount": 120000.0,
        "creditAmount": 0.0,
        "indexRef": "D1-2",
        "remark": "同笔分录借方",
    },
    {
        "rowId": "d4a-l2seed003-h7i8j9k",
        "description": f"{MARK}其他业务收入重分类（报表调整）",
        "category": "报表调整",
        "reportItem": "其他业务收入",
        "accountName": "其他业务收入",
        "noteItem": "五、1 营业收入",
        "placeholder": "",
        "debitAmount": 48000.0,
        "creditAmount": 48000.0,
        "indexRef": "D4-3",
        "remark": "仅影响报表列报，不动科目余额",
    },
]


def _balance_check(rows: list[dict[str, Any]]) -> tuple[float, float, bool]:
    d = sum(float(r.get("debitAmount") or 0) for r in rows)
    c = sum(float(r.get("creditAmount") or 0) for r in rows)
    return d, c, abs(d - c) < 0.005


async def _read_current(db: Any) -> tuple[list[dict[str, Any]], int | None]:
    row = (
        await db.execute(
            sa.text(
                "SELECT remark, content_version FROM checklist_responses "
                "WHERE wp_id = :wid AND item_id = :iid"
            ),
            {"wid": WP_ID, "iid": ITEM_ID},
        )
    ).fetchone()
    if row is None:
        return [], None
    raw, ver = row
    try:
        parsed = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        parsed = []
    return (parsed if isinstance(parsed, list) else []), ver


def _describe(rows: list[dict[str, Any]]) -> dict[str, Any]:
    d, c, ok = _balance_check(rows)
    nonempty = [
        r
        for r in rows
        if isinstance(r, dict)
        and (
            str(r.get("description") or "").strip()
            or float(r.get("debitAmount") or 0)
            or float(r.get("creditAmount") or 0)
        )
    ]
    return {
        "row_count": len(rows),
        "nonempty_row_count": len(nonempty),
        "seed_row_count": sum(
            1 for r in rows if isinstance(r, dict) and MARK in str(r.get("description") or "")
        ),
        "debit_total": d,
        "credit_total": c,
        "balanced": ok,
        "row_ids": [str(r.get("rowId")) for r in rows if isinstance(r, dict)],
    }


async def run(*, mode: str) -> dict[str, Any]:
    from app.core.database import async_session

    out: dict[str, Any] = {"mode": mode, "wp_id": WP_ID, "item_id": ITEM_ID}
    async with async_session() as db:
        before, ver = await _read_current(db)
        out["before"] = _describe(before)
        out["content_version_before"] = ver

        if mode == "check":
            return out

        if mode == "purge":
            kept = [
                r
                for r in before
                if not (isinstance(r, dict) and MARK in str(r.get("description") or ""))
            ]
            if len(kept) == len(before):
                out["changed"] = False
                out["note"] = "没有带标记的 seed 行，无需清理"
                return out
            if kept:
                await db.execute(
                    sa.text(
                        "UPDATE checklist_responses SET remark = :rm, "
                        "content_version = content_version + 1, updated_at = NOW() "
                        "WHERE wp_id = :wid AND item_id = :iid"
                    ),
                    {"rm": json.dumps(kept, ensure_ascii=False), "wid": WP_ID, "iid": ITEM_ID},
                )
            else:
                await db.execute(
                    sa.text(
                        "DELETE FROM checklist_responses "
                        "WHERE wp_id = :wid AND item_id = :iid"
                    ),
                    {"wid": WP_ID, "iid": ITEM_ID},
                )
            await db.commit()
            after, ver2 = await _read_current(db)
            out["after"] = _describe(after)
            out["content_version_after"] = ver2
            out["changed"] = True
            return out

        # ── apply / dry-run ──────────────────────────────────────────
        # 幂等：按 rowId 覆盖同 id 行，保留其它行（含用户自己建的）。
        by_id = {
            str(r.get("rowId")): dict(r)
            for r in before
            if isinstance(r, dict) and r.get("rowId")
        }
        order = [str(r.get("rowId")) for r in before if isinstance(r, dict) and r.get("rowId")]
        for r in SEED_ROWS:
            rid = r["rowId"]
            if rid not in by_id:
                order.append(rid)
            by_id[rid] = dict(r)
        merged = [by_id[i] for i in order]

        d, c, ok = _balance_check(merged)
        out["planned"] = _describe(merged)
        if not ok:
            out["status"] = "refused"
            out["reason"] = (
                f"合并后借贷不平（借 {d} / 贷 {c}）—— D4-4 的「确认调整」按钮要求平衡，"
                "不平的 seed 会让页面状态与真实使用不符，拒绝写入"
            )
            return out

        if mode == "dry-run":
            out["status"] = "would_write"
            out["payload_preview"] = json.dumps(merged, ensure_ascii=False)[:600]
            return out

        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses
                    (id, project_id, wp_id, item_id, conclusion, remark,
                     content_version, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :pid, :wid, :iid, NULL, :rm, 1, NOW(), NOW())
                ON CONFLICT (wp_id, item_id) DO UPDATE SET
                    remark = EXCLUDED.remark,
                    content_version = checklist_responses.content_version + 1,
                    updated_at = NOW()
                """
            ),
            {
                "pid": PROJECT_ID,
                "wid": WP_ID,
                "iid": ITEM_ID,
                "rm": json.dumps(merged, ensure_ascii=False),
            },
        )
        await db.commit()
        after, ver2 = await _read_current(db)
        out["after"] = _describe(after)
        out["content_version_after"] = ver2
        out["status"] = "written"
        return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="只读现状")
    g.add_argument("--dry-run", action="store_true", help="打印将写什么，不写库")
    g.add_argument("--apply", action="store_true", help="写库（幂等，按 rowId 覆盖）")
    g.add_argument("--purge", action="store_true", help="删掉带 [L2验收] 标记的行")
    p.add_argument("--json-out", default=None)
    args = p.parse_args()

    mode = (
        "check"
        if args.check
        else "dry-run"
        if args.dry_run
        else "apply"
        if args.apply
        else "purge"
    )
    report = asyncio.run(run(mode=mode))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    return 0 if report.get("status") != "refused" else 1


if __name__ == "__main__":
    raise SystemExit(main())
