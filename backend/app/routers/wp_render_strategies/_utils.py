"""wp_render_strategies 共享工具函数。"""


def _has_grid_cells(html_data: dict | None) -> bool:
    """判断 sheet html_data 是否已含可渲染的网格 cells。"""
    if not isinstance(html_data, dict):
        return False
    cells = html_data.get("cells")
    return isinstance(cells, dict) and len(cells) > 0
