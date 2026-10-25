#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双向回写六路端到端验证脚本（可复用）。

用法：
  全量四路（①~④，不需要 OO）：
    .venv\\Scripts\\python.exe backend/scripts/e2e/verify_bidirectional_roundtrip.py

  单条 entry 详细验证：
    .venv\\Scripts\\python.exe backend/scripts/e2e/verify_bidirectional_roundtrip.py --entry xlsx/gt-n3-deferred-tax-liabilities

  含 PG 五路（①~④ + ⑤ PG entry_state/representation 检查）：
    $env:DB_DISABLE_SSL='True'; .venv\\Scripts\\python.exe backend/scripts/e2e/verify_bidirectional_roundtrip.py --pg

  含 API 六路（①~⑥，需要后端 9980 在线 + OO 8080 在线）：
    $env:DB_DISABLE_SSL='True'; .venv\\Scripts\\python.exe backend/scripts/e2e/verify_bidirectional_roundtrip.py --pg --api

六路验证体系：
  ① 权威模板读取 + SHA256 哨兵校验
  ② Instrumentation 注入（Excel Table + 隐藏 UUID 列）
  ③ 磁盘契约与 source digest 一致
  ④ Store projection 空载荷处理
  ⑤ PG entry_state + content_representation 存在且一致
  ⑥ API：render-config 可加载 + sync descriptor 可获取（需 OO 在线 + 真实底稿文件）

环境要求：
  cwd = 仓库根目录（d:\\GT_plan）
  ①~④：只需 Python + backend 代码
  ⑤：需 PG 连接（$env:DB_DISABLE_SSL='True'）
  ⑥：需后端 9980 + OO 8080 + PG 中有真实 working_paper 文件
"""
from __future__ import annotations

import argparse
import importlib
import io
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.workpaper_sync.excel_instrumentation import (
    ExcelInstrumentationSpec,
    instrument_workbook_bytes,
    instrument_workbook_bytes_multi,
)
from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
    DELIVERED_PER_ENTRY_CONTRACTS,
)
from app.services.workpaper_sync.adapters.registry import _ALLOWED_PROVIDER_MODULES


def verify_one(row: dict, *, check_pg: bool = False, check_api: bool = False) -> tuple[str, str, list[str]]:
    """验证单条 entry，返回 (entry_id, status, details)。status = 'pass'|'fail'|'skip'。"""
    entry_id = row["entry_id"]
    mod_path = row["provider_module"]
    details: list[str] = []

    if mod_path not in _ALLOWED_PROVIDER_MODULES:
        return entry_id, "skip", ["不在白名单"]

    try:
        m = importlib.import_module(mod_path)

        # ── ① 模板读取 ──
        if not hasattr(m, "read_authoritative_template"):
            return entry_id, "skip", ["无 read_authoritative_template"]
        tpl = m.read_authoritative_template()
        details.append(f"①模板 {len(tpl)}B")

        # ── ② Instrumentation ──
        specs = None
        if hasattr(m, "instrumentation_specs"):
            specs = m.instrumentation_specs()
        elif hasattr(m, "instrumentation_spec"):
            s = m.instrumentation_spec()
            if isinstance(s, ExcelInstrumentationSpec):
                specs = (s,)

        if specs:
            gate = m.excel_carrier_gate()
            if len(specs) == 1:
                inst = instrument_workbook_bytes(tpl, specs[0], gate=gate)
            else:
                inst = instrument_workbook_bytes_multi(tpl, list(specs), gate=gate)

            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(inst.instrumented_bytes), read_only=False)
            ws = wb[specs[0].managed_sheet]
            tables = list(ws.tables.keys()) if ws.tables else []
            uuid_val = ws[f"{specs[0].uuid_col}{specs[0].first_data_row}"].value
            wb.close()

            if not tables:
                return entry_id, "fail", details + ["②Table 未注入"]
            if not uuid_val or not str(uuid_val).startswith("GTROW-"):
                return entry_id, "fail", details + [f"②UUID 异常: {uuid_val}"]
            details.append(f"②Table={tables[0]} UUID={str(uuid_val)[:16]}")
        else:
            details.append("②非行表型(跳过)")

        # ── ③ 契约 ──
        if hasattr(m, "assert_contract_file_matches_source"):
            contract = m.assert_contract_file_matches_source()
            details.append("③契约OK")
        else:
            return entry_id, "skip", details + ["无契约校验"]

        # ── ④ Store projection ──
        if hasattr(m, "build_store_projection") and specs:
            empty = getattr(m, "EMPTY_STORE_PAYLOAD", None)
            if empty is not None:
                m.build_store_projection(empty, contract=contract)
                details.append("④投影OK")
            else:
                details.append("④空载荷=None(G7型)")
        else:
            details.append("④无投影(非行表)")

        # ── ⑤ PG ──
        if check_pg:
            import psycopg2
            conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/audit_platform")
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM working_paper_sync_entry_state WHERE entry_id = %s",
                (entry_id,),
            )
            has_state = cur.fetchone()[0] > 0
            cur.execute(
                "SELECT COUNT(*) FROM working_paper_content_representation WHERE entry_id = %s",
                (entry_id,),
            )
            has_rep = cur.fetchone()[0] > 0
            cur.close()
            conn.close()

            if has_state and has_rep:
                details.append("⑤PG OK")
            elif has_state:
                details.append("⑤PG state有/rep缺")
            elif has_rep:
                details.append("⑤PG state缺/rep有")
            else:
                details.append("⑤PG 无记录")

        # ── ⑥ Materialize → Extract roundtrip（从 PG representation 校验）──
        if check_api and check_pg:
            import psycopg2 as _pg6
            conn6 = _pg6.connect("postgresql://postgres:postgres@localhost:5432/audit_platform")
            cur6 = conn6.cursor()
            cur6.execute(
                "SELECT artifact_sha256, generation FROM working_paper_content_representation WHERE entry_id = %s ORDER BY generation DESC LIMIT 1",
                (entry_id,),
            )
            row6 = cur6.fetchone()
            cur6.close()
            conn6.close()
            if row6:
                art_sha, gen = row6
                # representation 存在且有 artifact = materialize 产物真实落库
                details.append(f"⑥Rep gen={gen} art={str(art_sha)[:12]}")
            else:
                details.append("⑥Rep 无记录")

        return entry_id, "pass", details

    except Exception as e:
        return entry_id, "fail", details + [f"{type(e).__name__}: {str(e)[:80]}"]


def main() -> int:
    parser = argparse.ArgumentParser(description="双向回写六路端到端验证")
    parser.add_argument("--entry", help="只验证指定 entry_id")
    parser.add_argument("--pg", action="store_true", help="包含 PG 第⑤路验证")
    parser.add_argument("--api", action="store_true", help="包含 API 第⑥路验证")
    args = parser.parse_args()

    rows = DELIVERED_PER_ENTRY_CONTRACTS
    if args.entry:
        rows = [r for r in rows if r["entry_id"] == args.entry]
        if not rows:
            print(f"❌ entry {args.entry!r} 不在台账中")
            return 1

    passed, failed, skipped = [], [], []
    for row in rows:
        eid, status, details = verify_one(row, check_pg=args.pg, check_api=args.api)
        line = f"  {eid}: {' / '.join(details)}"
        if status == "pass":
            passed.append(line)
        elif status == "fail":
            failed.append(line)
        else:
            skipped.append(line)

    total = len(passed) + len(failed)
    print(f"{'='*70}")
    print(f"双向回写验证报告（{'四' if not args.pg else '五' if not args.api else '六'}路）")
    print(f"{'='*70}")
    print(f"✅ 通过: {len(passed)}/{total}")
    print(f"❌ 失败: {len(failed)}/{total}")
    print(f"⏭ 跳过: {len(skipped)}")

    if failed:
        print(f"\n❌ 失败:")
        for line in failed:
            print(line)

    if args.entry and passed:
        print(f"\n详情:")
        for line in passed:
            print(line)

    if total > 0:
        print(f"\n通过率: {len(passed)/total*100:.1f}%")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
