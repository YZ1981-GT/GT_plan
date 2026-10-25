# -*- coding: utf-8 -*-
r"""检测 checklist_responses 的「跨循环命名空间污染」（NC-19 / LC-22 的平台级汇聚点）。

症状：某条 `checklist_responses` 行的 `item_id` 命名空间（如 `N1-3-entries` 的 `N`）与它
所挂宿主底稿的 `wp_code` 循环字母（如 `G8` 的 `G`）**不一致** —— 即「N 的数据落在 G 的底稿
上」。历史上 L/N 两轮 slice 的 `cross_entry_isolation` 都**只扫代码不查库**，漏检了这类只在
真库里才看得见的污染。

🔴 **只查不删**：本脚本永远只报告，不删除任何真实数据（删除需用户显式授权）。

🔴 **正确的 join 链**（曾被写错导致误报/漏报）：
    checklist_responses.wp_id → working_paper.id
                              → working_paper.wp_index_id → wp_index.id → wp_index.wp_code
  **不是** `wp_index.id = checklist_responses.wp_id`（那个 join 对所有行返回 NULL，
  既测不出真污染、又会把「全是 NULL」误读成某种结论）。

用法（仓库根）::

    .\.venv\Scripts\python.exe backend/scripts/analyze/detect_cross_cycle_namespace_pollution.py
    # 指定命名空间前缀（默认 N 与 L）：
    .\.venv\Scripts\python.exe backend/scripts/analyze/detect_cross_cycle_namespace_pollution.py --prefix N

退出码：有污染→2；无污染→0；连不上库→3（并打印原因，不静默成 0）。
"""

from __future__ import annotations

import argparse
import os
import sys

# NC-19 的统一检测 SQL（供脚本与守卫测试共用，避免两份口径漂移）。
POLLUTION_SQL = r"""
WITH j AS (
  SELECT cr.item_id,
         wi.wp_code,
         substring(cr.item_id from '^([A-Za-z]+)') AS ns_letter,
         substring(wi.wp_code from '^([A-Za-z]+)')  AS host_letter
  FROM checklist_responses cr
  JOIN working_paper wp ON wp.id = cr.wp_id
  JOIN wp_index wi      ON wi.id = wp.wp_index_id
  WHERE cr.item_id ~ %(ns_regex)s
)
SELECT item_id, wp_code, ns_letter, host_letter
FROM j
WHERE ns_letter IS DISTINCT FROM host_letter
ORDER BY wp_code, item_id
"""


def _ns_regex(prefixes: list[str]) -> str:
    # 形如 `^(N[0-9]+|L[0-9]+)-` —— 命名空间字母后跟数字再接 `-`
    alts = "|".join(f"{p}[0-9]+" for p in prefixes)
    return f"^({alts})-"


def find_pollution(conn, prefixes: list[str]) -> list[dict]:
    cur = conn.cursor()
    cur.execute(POLLUTION_SQL, {"ns_regex": _ns_regex(prefixes)})
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _dsn() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/audit_platform",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--prefix", action="append", default=None,
        help="命名空间字母前缀（可重复）；默认 N 与 L",
    )
    args = ap.parse_args()
    prefixes = args.prefix or ["N", "L"]

    try:
        import psycopg2  # noqa: PLC0415
    except ImportError:
        try:
            import psycopg as psycopg2  # type: ignore  # noqa: PLC0415
        except ImportError:
            print("连不上库：psycopg2/psycopg 未安装", file=sys.stderr)
            return 3

    try:
        conn = psycopg2.connect(_dsn())
    except Exception as exc:  # noqa: BLE001
        print(f"连不上库（{_dsn()}）：{exc}", file=sys.stderr)
        return 3

    try:
        rows = find_pollution(conn, prefixes)
    finally:
        conn.close()

    if not rows:
        print(f"[OK] 命名空间 {prefixes} 无跨循环污染（item_id 命名空间 == 宿主 wp_code 循环字母）")
        return 0

    print(f"[POLLUTION] 发现 {len(rows)} 条跨循环污染（只报告，不删除）：")
    for r in rows:
        print(f"  item_id={r['item_id']!r} 落在 wp_code={r['wp_code']!r} "
              f"（命名空间 {r['ns_letter']} ≠ 宿主 {r['host_letter']}）")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
