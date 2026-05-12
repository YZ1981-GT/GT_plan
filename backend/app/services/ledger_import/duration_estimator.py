"""F17 / Sprint 4.13 — 导入前耗时预估。

基于 9 家真实样本实测的 P50 吞吐：

| 样本           | 行数       | 总耗时 |
|----------------|-----------|--------|
| YG4001-30      | 4k 行     | 15s    |
| YG36           | 22k 行    | 30s    |
| 辽宁卫生        | 406k 行   | 791s   |
| YG2101         | 2M 行     | 400-482s（含 calamine 加速） |

档位策略：
- ``S`` < 10k 行：小文件，整体 15s 足够（detect + create_staged 主导）
- ``M`` 10k-100k 行：~3k rows/s 吞吐（解析主导）
- ``L`` 100k-500k 行：~5k rows/s（calamine 提速）
- ``XL`` ≥ 500k 行：~4.5k rows/s（含 activate 波动）

目标误差 ±30%（真实项目验收口径）。估算只作前端提示用，不参与任何业务决策。
"""

from __future__ import annotations


def estimate_duration_seconds(total_rows: int) -> int:
    """按 total_rows 估算完整导入耗时（含 detect/parse/validate/write/activate）。

    Args:
        total_rows: 预估总行数（所有 sheet 累计 row_count_estimate）。
            非 table_type 的 sheet 通常被排除在外。

    Returns:
        预估秒数（int），空文件/负数兜底 15s。
    """
    if total_rows <= 0:
        return 15  # 空文件也给 15s 兜底
    if total_rows < 10_000:
        return 15
    if total_rows < 100_000:
        return int(30 + total_rows / 3_000)
    if total_rows < 500_000:
        return int(90 + total_rows / 5_000)
    return int(180 + total_rows / 4_500)


def estimate_duration_bucket(total_rows: int) -> str:
    """返回规模档位标签（供前端粗分类展示）。

    Returns:
        ``"S"`` / ``"M"`` / ``"L"`` / ``"XL"``
    """
    if total_rows < 10_000:
        return "S"
    if total_rows < 100_000:
        return "M"
    if total_rows < 500_000:
        return "L"
    return "XL"


__all__ = [
    "estimate_duration_seconds",
    "estimate_duration_bucket",
]
