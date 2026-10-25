# -*- coding: utf-8 -*-
"""D4-33~36 导入导出/死配置守卫的变异检验 harness（四态判定）。

用法：python backend/scripts/diagnose/mutate_d4_33_36_guards.py
对每个变异：临时改源码 → 跑对应守卫 → 还原 → 判定 RED/GREEN/ANCHOR-MISS/WRONG-TEST。

RED        = 守卫按预期打红（退出非 0 且失败的正是预期那条测试）
GREEN      = 守卫缺陷（变异后仍全绿）
ANCHOR-MISS= 脚本缺陷（锚点未命中，替换次数 != 预期，源码未变）
WRONG-TEST = 打红了但不是预期项
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SRC = Path("backend/app/routers/wp_render_strategies/_d4_import_export.py")
ROUNDTRIP = "backend/tests/test_d4_33_36_import_export_roundtrip.py"
ITEMID = "backend/tests/test_d4_33_36_item_id_and_dead_config.py"

# (name, old, new, expect_replacements, testfile, expect_failed_test_substr)
MUTATIONS = [
    # ① item_id 改回 -rows（打 item_id 守卫）
    ("item_id_d33_rows", 'item_id = "D4-33-data"', 'item_id = "D4-33-rows"', 2, ITEMID, "no_rows_fallback"),
    # ② D4-35 parser 改回 generic（打 dispatch 守卫）
    ("d35_generic", "row_dict = _parse_d4_35_row(row, actual_headers)",
     "row_dict = _parse_generic_row(row, actual_headers)", 1, ROUNDTRIP, "dispatch_uses_dedicated"),
    # ③ D4-36 backward 改按列序（把凭证日期取成第一列"单据日期"）→ 打 backward 列名映射守卫
    ("d36_backward_positional",
     '    voucher_date = _safe_str(_col_val("凭证日期"))\n    doc_date = _safe_str(_col_val("单据日期"))\n    if not (voucher_date or doc_date):\n        return {}\n    return {\n        "id": f"ct-imp-{uuid4().hex[:8]}",\n        "voucherDate": voucher_date,\n        "voucherNo": _safe_str(_col_val("凭证编号")),\n        "voucherProduct": _safe_str(_col_val("凭证品名")),\n        "voucherQty": _safe_str(_col_val("凭证数量")),\n        "voucherAmount": _safe_amount_or_blank(_col_val("凭证金额")),\n        "docDate": doc_date,\n        "docNo": _safe_str(_col_val("单据编号")),\n        "docProduct": _safe_str(_col_val("单据品名")),\n        "docQty": _safe_str(_col_val("单据数量")),\n        "docAmount": _safe_amount_or_blank(_col_val("单据金额")),\n        "isCrossing": "",  # 派生：由前端 autoJudgeBackward 重算\n    }',
     # 变异版：按列序取（凭证= values[5..9]）—— 简化为直接把 voucherDate 取成 docDate 列头
     '    values = list(row) + [None] * (len(actual_headers) - len(row))\n    if all(v is None for v in row):\n        return {}\n    return {\n        "id": f"ct-imp-{uuid4().hex[:8]}",\n        "voucherDate": _safe_str(values[0]),\n        "voucherNo": _safe_str(values[1]),\n        "voucherProduct": _safe_str(values[2]),\n        "voucherQty": _safe_str(values[3]),\n        "voucherAmount": _safe_amount_or_blank(values[4]),\n        "docDate": _safe_str(values[5]),\n        "docNo": _safe_str(values[6]),\n        "docProduct": _safe_str(values[7]),\n        "docQty": _safe_str(values[8]),\n        "docAmount": _safe_amount_or_blank(values[9]),\n        "isCrossing": "",\n    }',
     1, ROUNDTRIP, "backward_by_header_name"),
    # ④ D4-34 合并写回改整对象覆盖（丢 consults）→ 打 merge 守卫
    ("d34_overwrite", 'merged = {"rentals": rows_data, "consults": existing_data.get("consults", [])}',
     'merged = {"rentals": rows_data, "consults": []}', 1, ROUNDTRIP, "merge_writeback_preserves"),
    # ⑤ D4-33 毛利率改回小数比率（打百分比守卫）
    ("d33_margin_ratio", "return round((rev - cost) / rev * 100, 2)",
     "return round((rev - cost) / rev, 2)", 1, ROUNDTRIP, "margin_is_percentage"),
    # ⑥ D4-35 sampling 保护移除（改成不保留）→ 打 sampling 守卫
    ("d35_sampling_lost", '"sampling": existing_data.get("sampling", {}),',
     '"sampling": {},', 1, ROUNDTRIP, "sampling_protected"),
    # ⑦ 死配置 D4-34 主键加回 → 打死配置守卫
    ("readd_d34_master", '"D4-33", "D4-34-rental", "D4-34-consult"',
     '"D4-33", "D4-34", "D4-34-rental", "D4-34-consult"', 1, ITEMID, "master_keys_removed"),
]


def run() -> int:
    orig = SRC.read_text(encoding="utf-8")
    any_bad = False
    for name, old, new, expect_n, testfile, expect_substr in MUTATIONS:
        n = orig.count(old)
        if n != expect_n:
            print(f"[{name}] ANCHOR-MISS: 锚点命中 {n} 次，期望 {expect_n}")
            any_bad = True
            continue
        SRC.write_text(orig.replace(old, new), encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", testfile, "-q", "--no-header", "--tb=no"],
                capture_output=True, text=True,
            )
        finally:
            SRC.write_text(orig, encoding="utf-8")
        out = proc.stdout + proc.stderr
        if proc.returncode == 0:
            print(f"[{name}] GREEN 守卫缺陷！变异后仍全绿")
            any_bad = True
        elif expect_substr in out:
            print(f"[{name}] RED(OK) 变异被 {expect_substr} 打红")
        else:
            print(f"[{name}] WRONG-TEST 打红但非预期项（期望含 {expect_substr}）")
            print("  " + "\n  ".join(l for l in out.splitlines() if "FAILED" in l or "failed" in l)[:400])
            any_bad = True
    print("=== 变异检验", "有问题" if any_bad else "全部 RED，守卫有效", "===")
    return 1 if any_bad else 0


if __name__ == "__main__":
    sys.exit(run())
