"""D1 应收票据 — 导入导出三级端点（按域拆分 facade）

原 _d1_import_export.py（~2989 行）按域拆分为子模块：
- _config.py    : Sheet 配置常量（表头、item_id 映射、行限制等）
- _helpers.py   : 共享辅助函数（_safe_float/_safe_str/_col_val/_validate_sheet 等）
- _template.py  : 模板创建逻辑（_create_template_wb/_write_flat_headers 等）
- _parsers.py   : 行解析函数（_parse_d1_X_row 系列）
- _exporters.py : 行导出函数（_export_d1_X_row 系列）
- _export.py    : 导出端点逻辑（_export_d1_X_data / d1_export_template / d1_export_data）
- _import.py    : 导入端点逻辑（_import_d1_X_data / d1_import_data）
- _impl.py      : 原始完整实现（内部使用）

外部行为不变：router 仍可通过原路径导入。
所有内部符号为测试向后兼容而全量 re-export（通过 sys.modules 代理）。
"""
import importlib
import sys

# 将 _impl 模块的所有属性代理到本包的命名空间
# 这样 `from app.routers.wp_render_strategies._d1_import_export import _xxx` 仍有效
_impl = importlib.import_module("app.routers.wp_render_strategies._d1_import_export._impl")

# 复制所有属性到当前模块命名空间
_current = sys.modules[__name__]
for _attr in dir(_impl):
    if not _attr.startswith("__"):
        setattr(_current, _attr, getattr(_impl, _attr))

# 确保 router 在顶层可见
router = _impl.router
