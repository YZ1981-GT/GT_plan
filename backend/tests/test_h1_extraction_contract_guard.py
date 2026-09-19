"""H1 四表取数契约守卫（Wave 7 Task 8.2）。

断言：
- H1 后端四表查询统一经 get_active_filter（数据集隔离单一入口，禁裸 is_deleted=false）
- 明细取数只有 _build_h1_detail_prefill 一个入口函数（无第二套口径）
"""
import inspect
import re

from app.routers.wp_render_strategies import _h1_fixed_assets as h1


def _source_of(fn) -> str:
    return inspect.getsource(fn)


def test_all_four_table_queries_use_active_filter():
    """四表查询函数统一使用 get_active_filter（不裸写 is_deleted=false）。"""
    fns = [
        h1._build_h1_detail_prefill,
        h1._build_h1_ledger_movement,
        h1._build_h1_depreciation_movement,
        h1._probe_counterpart_availability,
    ]
    for fn in fns:
        src = _source_of(fn)
        assert "get_active_filter" in src, f"{fn.__name__} 未使用 get_active_filter"
        # 确认不含裸 is_deleted 过滤（注释除外）
        code_lines = [l for l in src.splitlines() if not l.strip().startswith("#")]
        code_text = "\n".join(code_lines)
        assert "is_deleted" not in code_text, (
            f"{fn.__name__} 含裸 is_deleted 过滤，应统一使用 get_active_filter"
        )


def test_single_detail_prefill_entry_point():
    """明细取数只有 _build_h1_detail_prefill 一个入口（禁第二套口径）。"""
    module_src = inspect.getsource(h1)
    # 搜索所有"向 tb_balance 取 1601/1602 数据并组装 rows"的函数
    detail_builders = re.findall(r"async def (_build_h1_\w*prefill\w*)\(", module_src)
    # 只允许 _build_h1_detail_prefill + _build_h1_four_table_prefill（编排层）
    allowed = {"_build_h1_detail_prefill", "_build_h1_four_table_prefill"}
    unexpected = set(detail_builders) - allowed
    assert not unexpected, f"发现第二套明细取数入口：{unexpected}"
