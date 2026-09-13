#!/usr/bin/env python
"""D4 C4 逐表验收登记守卫（governance spec Task 6 + Task 7 / Property 5）。

核对：

1. C4 登记恰好 36 行，wp_code 与 owner 与 d4_owner_matrix.json 逐行一致（同一真源，
   不得漂移出第二套 owner 归属）。
2. 每行六维取值都在词汇表 {GREEN, OWNER, UNVERIFIABLE} 内。
3. **不假绿判据**：playwright 维度不得标 GREEN（本治理 spec 无运行时浏览器证据，
   只能是 OWNER 或 UNVERIFIABLE）—— 防「无证据却标绿」（假绿三源之③）。
4. D4-1（own）的 source/contract/formula_conflict/permission 必须 GREEN
   （本 spec 已产出可复现判据）；其 playwright 必须 UNVERIFIABLE（诚实）。
5. UNVERIFIABLE 计数如实回报，不计入 GREEN 总数。
6. 反向自检：把 playwright 改成 GREEN 必被拦。

只读；退出码 1 表示登记漂移或假绿。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_C4 = _BACKEND / "data" / "d4_c4_acceptance_registry.json"
_MATRIX = _BACKEND / "data" / "d4_owner_matrix.json"

_VOCAB = {"GREEN", "OWNER", "UNVERIFIABLE"}
_DIMS = ("source", "contract", "roundtrip", "formula_conflict", "permission", "playwright")


def _check(c4: dict, matrix: dict, errs: list[str]) -> None:
    rows = c4.get("rows") or []
    if len(rows) != 36:
        errs.append(f"C4 行数 {len(rows)} != 36")

    matrix_owner = {r["wp_code"]: r["owner"] for r in matrix.get("rows") or []}
    for row in rows:
        code = row.get("wp_code")
        # 1+2. owner 与矩阵一致 + 词汇合法
        if matrix_owner.get(code) != row.get("owner"):
            errs.append(
                f"{code} owner 与 owner_matrix 漂移："
                f"C4={row.get('owner')!r} vs matrix={matrix_owner.get(code)!r}"
            )
        for dim in _DIMS:
            val = row.get(dim)
            if val not in _VOCAB:
                errs.append(f"{code}.{dim}={val!r} 不在词汇表 {sorted(_VOCAB)}")
        # 3. 不假绿：playwright 不得 GREEN
        if row.get("playwright") == "GREEN":
            errs.append(
                f"{code}.playwright=GREEN —— 本治理 spec 无运行时浏览器证据，"
                "不得标 GREEN（假绿三源之③）"
            )

    # 4. D4-1 own 行的强断言
    d41 = next((r for r in rows if r.get("wp_code") == "D4-1"), None)
    if d41 is None:
        errs.append("C4 缺 D4-1 行")
    else:
        for dim in ("source", "contract", "formula_conflict", "permission"):
            if d41.get(dim) != "GREEN":
                errs.append(f"D4-1.{dim} 应 GREEN（本 spec 已产判据），实为 {d41.get(dim)!r}")
        if d41.get("playwright") != "UNVERIFIABLE":
            errs.append(
                f"D4-1.playwright 应 UNVERIFIABLE（诚实），实为 {d41.get('playwright')!r}"
            )


def _reverse_selfcheck() -> list[str]:
    problems: list[str] = []
    bad_c4 = {"rows": [{"wp_code": "D4-1", "owner": "x", "playwright": "GREEN"}]}
    bad_matrix = {"rows": [{"wp_code": "D4-1", "owner": "x"}]}
    e: list[str] = []
    _check(bad_c4, bad_matrix, e)
    if not any("playwright=GREEN" in x for x in e):
        problems.append("反向自检失败：playwright=GREEN 未被拦")
    return problems


def main() -> int:
    errs: list[str] = []
    c4 = json.loads(_C4.read_text(encoding="utf-8"))
    matrix = json.loads(_MATRIX.read_text(encoding="utf-8"))
    _check(c4, matrix, errs)
    errs.extend(_reverse_selfcheck())

    if errs:
        print(f"[FAIL] D4 C4 验收登记守卫检出 {len(errs)} 项问题：")
        for e in errs:
            print(f"  - {e}")
        return 1

    rows = c4["rows"]
    green = sum(1 for r in rows for d in _DIMS if r.get(d) == "GREEN")
    owner = sum(1 for r in rows for d in _DIMS if r.get(d) == "OWNER")
    unver = sum(1 for r in rows for d in _DIMS if r.get(d) == "UNVERIFIABLE")
    print(
        f"[OK] D4 C4 验收登记：36 行 owner 与矩阵锁死；六维取值合法；playwright 无假绿。"
        f" 统计 GREEN={green} / OWNER={owner} / UNVERIFIABLE={unver}（UNVERIFIABLE 不计 GREEN）。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
