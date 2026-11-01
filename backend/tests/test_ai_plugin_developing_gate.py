"""8 个 AI 插件 stub 只能展示为开发中，不得进入执行链。"""

import ast
import inspect

from app.routers import ai_plugins
from app.services.ai_plugin_service import AIPluginService, PRESET_PLUGIN_IDS


def test_all_presets_are_non_executable_developing() -> None:
    rows = AIPluginService().get_preset_plugins()
    assert len(rows) == 8
    assert {row["plugin_id"] for row in rows} == PRESET_PLUGIN_IDS
    assert all(row["maturity"] == "developing" for row in rows)
    assert all(row["executable"] is False for row in rows)


def test_plugin_management_routes_are_admin_gated() -> None:
    for endpoint in (
        ai_plugins.list_plugins, ai_plugins.get_preset_plugins,
        ai_plugins.get_plugin, ai_plugins.register_plugin,
        ai_plugins.load_preset_plugins, ai_plugins.enable_plugin,
        ai_plugins.disable_plugin, ai_plugins.update_config,
    ):
        tree = ast.parse(inspect.getsource(endpoint))
        dependencies = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Depends"
        ]
        assert any(
            call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "_admin"
            for call in dependencies
        ), endpoint.__name__


def test_enable_route_rejects_developing_before_database_write() -> None:
    source = inspect.getsource(ai_plugins.enable_plugin)
    assert "is_developing_plugin(plugin_id)" in source
    assert source.index("is_developing_plugin(plugin_id)") < source.index("enable_plugin(db")
