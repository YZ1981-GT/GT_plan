"""事件处理器注册 — 按域拆分

原 event_handlers.py（~1725 行）按事件域拆分为子模块：
- _core.py              : 基础设施（_make_handler / _make_tb_handler / subscribe_many）
- _trial_balance.py     : 试算表相关 handlers
- _report_disclosure.py : 报表 + 附注 stale/更新 handlers
- _formula_cache.py     : 公式缓存失效 handlers
- _workpaper_stale.py   : 底稿预填过期标记 handlers
- _procedure_cache.py   : 程序表 auto_data 缓存失效
- _address_registry.py  : 地址坐标注册表缓存失效
- _stale_engine.py      : Stale Propagation Engine 统一入口
- _sse_linkage.py       : 企业联动 SSE 推送
- _cycle_backfill.py    : H/I 循环反向回填
- _workpaper_events.py  : 底稿保存/B51-5/B51-4 高风险触发
- _review_compensate.py : 复核退回工单补偿
- _impl.py              : 原始完整实现

外部行为不变：`from app.services.event_handlers import register_event_handlers` 仍可用。
monkeypatch 仍可对 `app.services.event_handlers.xxx` 生效（模块替换策略）。
"""
import sys
import importlib

# 将 _impl 模块安装为本包的模块身份
# 这确保 monkeypatch("app.services.event_handlers.X", ...) 能直接修改
# 运行时使用的那个对象（因为 _impl 中的闭包引用的是模块级变量）
_impl = importlib.import_module("app.services.event_handlers._impl")
_impl.__package__ = __name__
_impl.__path__ = __path__  # type: ignore[attr-defined]
# 保留子模块可达性
_impl._core = None  # placeholder for future sub-modules
sys.modules[__name__] = _impl  # type: ignore[assignment]
