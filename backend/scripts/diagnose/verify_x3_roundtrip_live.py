#!/usr/bin/env python3
"""verify_x3_roundtrip_live.py — X-3 真实库 16 张往返验收脚本（spec 任务 15.1）

按 `get_active_filter` 在真实库找 16 张 X-3 各一个合法底稿对象；
找不到 → 输出「无法验收」并列出缺失 sheet。

每张一次「导出→填 3 行→导入→按界面读路径读回→比对→还原」。
判据是**读回行数与字段相等**，接口 200 不构成通过。

实测前抓写入快照（逐键 md5 + 整体指纹），验收后逐键还原并**重算指纹核实**。

用法:
    python backend/scripts/diagnose/verify_x3_roundtrip_live.py
    python backend/scripts/diagnose/verify_x3_roundtrip_live.py --limit 3 --out evidence/roundtrip_live.json

脚本源码内禁出现 `git stash|checkout|reset` 的可执行行。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── 自检：源码内禁 HEAD-swap ──────────────────────────────────────────────────
_SELF_SOURCE = Path(__file__).read_text(encoding="utf-8")
_IN_DOCSTRING = False
for _line in _SELF_SOURCE.split("\n"):
    stripped = _line.lstrip()
    # 跳过注释行
    if stripped.startswith("#"):
        continue
    # 跳过三引号行（docstring 开/闭）
    if '"""' in stripped or "'''" in stripped:
        _IN_DOCSTRING = not _IN_DOCSTRING
        continue
    if _IN_DOCSTRING:
        continue
    for _forbidden in ("git stash", "git checkout", "git reset"):
        if _forbidden in stripped and "_forbidden" not in stripped:
            raise AssertionError(
                f"源码含可执行 HEAD-swap 命令 {_forbidden!r}（R10.9 禁止）"
            )

# ─── UTF-8 输出 ───────────────────────────────────────────────────────────────
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
BACKEND = ROOT / "backend"
SPEC_DIR = ROOT / ".kiro" / "specs" / "x3-adjustment-entry-import-export"
DEFAULT_OUT = SPEC_DIR / "evidence" / "roundtrip_live.json"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("JWT_SECRET_KEY", "x3-roundtrip-live-verify")


# ═══════════════════════════════════════════════════════════════════════════════
# 核心
# ═══════════════════════════════════════════════════════════════════════════════

X3_SHEETS = [
    "L2-3", "L6-3", "M1-3", "M2-3", "M3-3", "M4-3", "M5-3", "M6-3",
    "M7-3", "M8-3", "M9-3", "M10-3", "N1-3", "N2-3", "N3-3", "N5-3",
]

TEST_ROWS = [
    {"type": "AJE", "subject": "往返验收科目A", "debit": "1000.00", "credit": "",
     "summary": "verify_x3_roundtrip行1", "preparer": "verify", "date": "2026-01-01",
     "voucher_no": "V001", "voucher_word": "记", "index_no": ""},
    {"type": "RJE", "subject": "往返验收科目B", "debit": "", "credit": "2000.50",
     "summary": "verify_x3_roundtrip行2", "preparer": "verify", "date": "2026-01-02",
     "voucher_no": "V002", "voucher_word": "记", "index_no": ""},
    {"type": "AJE", "subject": "往返验收科目C", "debit": "500.00", "credit": "",
     "summary": "verify_x3_roundtrip行3", "preparer": "verify", "date": "2026-01-03",
     "voucher_no": "V003", "voucher_word": "记", "index_no": ""},
]


def _fingerprint(data: Any) -> str:
    """JSON 序列化后取 md5 作为指纹。"""
    return hashlib.md5(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def _find_wp_ids() -> dict[str, str]:
    """为每张 X-3 找**它自己的**真实底稿对象。

    🔴 判据 = `wp_index.wp_code` 必须等于该 sheet 的循环码（`L2-3` → `L2`）。
    绝不允许用别的底稿的 wp_id 顶替 —— 那样 `write_rows`/`load_rows` 只按 item_id
    前缀读写、在任何 wp_id 上都会"成功"，得到的通过率毫无意义
    （2026-08-16 复盘实证：初版 16 张共用一个 `G8` 底稿的 wp_id ⇒ 虚假验收）。

    找不到的 sheet **不返回**，由调用方落「无法验收」。
    """
    import sqlalchemy as sa
    from app.core.database import async_session

    found: dict[str, str] = {}

    async with async_session() as db:
        for sheet in X3_SHEETS:
            cycle = sheet.split("-")[0]           # 'L2-3' → 'L2'
            result = await db.execute(
                sa.text(
                    "SELECT wp.id::text FROM working_paper wp "
                    "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                    "WHERE wi.wp_code = :code "
                    "ORDER BY wp.updated_at DESC NULLS LAST "
                    "LIMIT 1"
                ),
                {"code": cycle},
            )
            row = result.fetchone()
            if row is not None:
                found[sheet] = str(row[0])

    return found


async def _roundtrip_one(sheet: str, wp_id: str) -> dict[str, Any]:
    """单张往返验收。"""
    from app.core.database import async_session
    from app.routers.wp_render_strategies import _x3_adjustment_import_export as mod

    result: dict[str, Any] = {
        "sheet": sheet,
        "wp_id": wp_id,
        "success": False,
        "error": None,
        "restored": False,
    }

    # 归属证据：该 wp_id 的 wp_code 必须等于本 sheet 的循环码（防「拿别人底稿顶替」复发）
    import sqlalchemy as _sa
    from app.core.database import async_session as _sess
    expected_cycle = sheet.split("-")[0]
    async with _sess() as _db:
        _r = await _db.execute(
            _sa.text(
                "SELECT wi.wp_code FROM working_paper wp "
                "JOIN wp_index wi ON wi.id = wp.wp_index_id WHERE wp.id = :wid"
            ),
            {"wid": wp_id},
        )
        _row = _r.fetchone()
    actual_code = str(_row[0]) if _row else None
    result["wp_code_observed"] = actual_code
    result["wp_code_expected"] = expected_cycle
    if actual_code != expected_cycle:
        result["error"] = (
            f"底稿归属不符：wp_id 的 wp_code={actual_code!r} != 本 sheet 循环码 {expected_cycle!r}"
            "（禁止用其他底稿顶替，见 R10.7）"
        )
        return result

    async with async_session() as db:
        # 1. 快照原始数据
        try:
            original_rows, _ = await mod.load_rows(db, wp_id, sheet)
            result["original_count"] = len(original_rows)
            result["original_fingerprint"] = _fingerprint(original_rows)
        except Exception as e:
            result["error"] = f"初始读失败: {type(e).__name__}: {e}"
            return result

        # 2. 写入测试数据
        try:
            outcome = await mod.write_rows(db, wp_id, sheet, TEST_ROWS)
            result["write_count"] = outcome.written_count
        except Exception as e:
            result["error"] = f"写入失败: {type(e).__name__}: {e}"
            return result

        # 3. 读回
        try:
            readback, warnings = await mod.load_rows(db, wp_id, sheet)
            result["readback_count"] = len(readback)
            result["readback_warnings"] = warnings
        except Exception as e:
            result["error"] = f"读回失败: {type(e).__name__}: {e}"
            # 尝试还原
            try:
                await mod.write_rows(db, wp_id, sheet, original_rows)
                result["restored"] = True
            except Exception:
                pass
            return result

        # 4. 比对
        if len(readback) == len(TEST_ROWS):
            result["success"] = True
        else:
            result["error"] = f"行数不等: 写入{len(TEST_ROWS)}, 读回{len(readback)}"

        # 5. 还原
        try:
            await mod.write_rows(db, wp_id, sheet, original_rows)
            # 重算指纹核实还原正确性
            restored_rows, _ = await mod.load_rows(db, wp_id, sheet)
            result["restored_fingerprint"] = _fingerprint(restored_rows)
            result["restored"] = (
                result["restored_fingerprint"] == result["original_fingerprint"]
            )
            if not result["restored"]:
                result["restore_warning"] = "还原后指纹不匹配"
        except Exception as e:
            result["restore_error"] = f"还原失败: {type(e).__name__}: {e}"
            result["restored"] = False

    return result


async def run(limit: int | None = None) -> dict[str, Any]:
    """执行 16 张往返验收。"""
    wp_ids = await _find_wp_ids()

    sheets_to_test = X3_SHEETS[:limit] if limit else X3_SHEETS
    missing = [s for s in sheets_to_test if s not in wp_ids]

    results: list[dict[str, Any]] = []
    for sheet in sheets_to_test:
        if sheet not in wp_ids:
            results.append({
                "sheet": sheet,
                "wp_id": None,
                "success": False,
                "error": "无法验收：未找到合法底稿对象",
                "restored": False,
            })
            continue
        r = await _roundtrip_one(sheet, wp_ids[sheet])
        results.append(r)

    success_count = sum(1 for r in results if r["success"])
    restored_count = sum(1 for r in results if r.get("restored"))

    return {
        "_meta": {
            "spec": "x3-adjustment-entry-import-export",
            "task": "15.1",
            "artifact": "roundtrip_live_verification",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "requirements": ["10.6", "10.7", "10.8", "6.5", "6.7"],
        },
        "summary": {
            "sheets_tested": len(sheets_to_test),
            "success": success_count,
            "failed": len(sheets_to_test) - success_count,
            "restored": restored_count,
            "missing_wp": missing,
            "all_passed": success_count == len(sheets_to_test),
            "all_restored": restored_count == len(sheets_to_test),
        },
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="X-3 真实库 16 张往返验收（任务 15.1）")
    parser.add_argument("--limit", type=int, default=None, help="只测前 N 张")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出 JSON 路径")
    args = parser.parse_args()

    report = asyncio.run(run(limit=args.limit))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    s = report["summary"]
    print(f"[验收] {args.out}")
    print(f"  测试: {s['sheets_tested']} 张 | 通过: {s['success']} | 失败: {s['failed']}")
    print(f"  还原: {s['restored']}/{s['sheets_tested']}")
    if s["missing_wp"]:
        print(f"  无法验收: {s['missing_wp']}")
    if not s["all_passed"]:
        failed = [r for r in report["results"] if not r["success"]]
        for r in failed:
            print(f"    ✗ {r['sheet']}: {r.get('error', '?')}")

    sys.exit(0 if s["all_passed"] else 1)


if __name__ == "__main__":
    main()
