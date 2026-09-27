# -*- coding: utf-8 -*-
"""从各 H provider 的 `build_contract_payload()` 生成/校验磁盘契约（9 条 entry 共用一个生成器）。

spec: `h-cycle-sync-foundation-and-first-canary` · Task 20（发布链第①环）
　　　+ 三份 lane spec 的契约发布任务

用法：
  校验全部: & d:/GT_plan/.venv/Scripts/python.exe backend/scripts/gen/generate_phase5_h_contracts.py
  写盘全部: & …/python.exe backend/scripts/gen/generate_phase5_h_contracts.py --apply
  只作用一条: … generate_phase5_h_contracts.py --only h9 [--apply]

🔴 **为什么 9 条共用一个生成器**：G/F 循环是一条 entry 一个 `generate_phase5_{x}_contract.py`，
到 G2 已有 5 份，其中 90% 逐字相同。H 要接 9 条 ⇒ 再抄 9 份就是 9 个漂移面
（改了 schema 门只改一处、漏一处就静默写出过不了 `parse_contract` 的契约）。
本脚本按 `_PROVIDERS` 登记表驱动，新增一条 entry 只加一行。

🔴 **双向锁**：契约只能从模块 payload 生成，不得手改磁盘 json。
各 provider 的 `assert_contract_file_matches_source()` 会在 adapter 注册路径上现算比对，
磁盘与源不一致即 `HEntrySelectionError`。

🔴 **写盘前必跑 `parse_contract`**：实测 F1 的磁盘契约是一份 `parse_contract` **过不了**的形态
（`tables[related_party_rows]: table anchor 必须是 A1 单元格，实得 None`），
因为它的生成器只写不校验 —— 于是 `assert_contract_file_matches_source()` 在 F1 上从未通过。
H 循环不重复该形态：写盘即经 schema 校验。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402

#: `(标签, provider 模块名)` —— 新增 entry 只加一行。
_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("h9", "phase5_h9_lease_liabilities"),
    ("h6", "phase5_h6_asset_disposal_clearing"),
    ("h4", "phase5_h4_engineering_materials"),
    ("h8", "phase5_h8_right_of_use_assets"),
    ("h2", "phase5_h2_construction_in_progress"),
    #: 🔴 变体轴：一个 entry 两张受管 sheet（成本模式 / 公允价值模式）。
    ("h3", "phase5_h3_investment_property"),
    #: 🔴 映射率最低档（前端行模型远小于模板列数，缺口逐条登记）。
    ("h5", "phase5_h5_oil_gas_assets"),
    ("h7", "phase5_h7_biological_assets"),
    #: 🔴 受管 sheet 是 **H10-3 调整分录汇总**，不是 slice 声明的 明细表H10-2
    #:    （后者是 9 类×12 月矩阵、前端零月度建模 ⇒ 结构性不匹配，见 H10-GAP-1）。
    #:    映射率 6/10 是全 H 最高档；单级表头也是全 H 唯一。
    ("h10", "phase5_h10_asset_disposal_income"),
)


def _run_one(label: str, module_name: str, *, apply: bool) -> int:
    import importlib

    mod = importlib.import_module(f"app.services.workpaper_sync.{module_name}")
    payload = mod.build_contract_payload()

    # 🔴 schema 门：不合法就别写盘（见模块 docstring 的 F1 教训）
    parsed = parse_contract(payload, adapter_id=mod.ADAPTER_ID)
    print(
        f"[{label}][schema] parse_contract OK: "
        f"sheets={[s.sheet_key for s in parsed.sheets]} "
        f"header_rows={[t.header_rows for s in parsed.sheets for t in s.tables]} "
        f"canonical_sha256={parsed.canonical_sha256}"
    )

    path = mod.contract_file_path()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        print(f"[{label}][apply] wrote {path} (canonical_digest={canonical_digest(payload)})")
        return 0
    if not path.exists():
        print(f"[{label}][check] MISSING {path} —— 需 --apply 生成")
        return 1
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    if canonical_digest(on_disk) != canonical_digest(payload):
        print(
            f"[{label}][check] DRIFT disk={canonical_digest(on_disk)} "
            f"source={canonical_digest(payload)}"
        )
        return 1
    print(f"[{label}][check] OK canonical_digest={canonical_digest(payload)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写盘（缺省只校验）")
    ap.add_argument("--only", default="", help="只作用于某个标签（如 h9）")
    args = ap.parse_args()

    rows = [r for r in _PROVIDERS if not args.only or r[0] == args.only]
    if not rows:
        print(f"没有匹配 --only {args.only!r} 的 provider；已登记：{[r[0] for r in _PROVIDERS]}")
        return 2
    rc = 0
    for label, module_name in rows:
        rc |= _run_one(label, module_name, apply=args.apply)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
