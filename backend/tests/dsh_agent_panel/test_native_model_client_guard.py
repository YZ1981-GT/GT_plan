"""``native_model_client`` 守卫（spec llm-ocr-local-first-routing）。

模型接缝 ``ModelClient`` / ``AIServiceModelClient`` 为行数门禁从 ``native_engine.py`` 原样抽出；
``test_task6_native_engine`` 的两条结构性约束只扫 ``NativeEngine`` / ``EngineStream`` 所在模块，
抽文件会让这部分代码静默脱管 ⇒ 在这里对新模块施加同样的约束（复用同一个 AST 判据）。
"""

from __future__ import annotations

from app.services.ai_chat import native_engine
from app.services.ai_chat.native_model_client import AIServiceModelClient, ModelClient
from tests.dsh_agent_panel.test_task6_native_engine import _code_identifiers


def test_seam_lives_in_its_own_module_and_is_still_exported_by_the_engine():
    # 反向断言：锚点真的指向抽出的文件（否则下面的扫描范围仍是 native_engine.py）
    assert AIServiceModelClient.__module__ == "app.services.ai_chat.native_model_client"
    assert native_engine.AIServiceModelClient is AIServiceModelClient
    assert native_engine.ModelClient is ModelClient


def test_seam_writes_no_messages_and_no_run_state():
    identifiers = _code_identifiers(AIServiceModelClient)
    for forbidden in (
        "append_message", "finish_success", "finish_error", "finish_cancelled",
        "transition", "AIChatRun", "AIChatMessage",
    ):
        assert forbidden not in identifiers, f"模型接缝引用了 {forbidden} —— 终态只能由 ChatRunService 写"


def test_seam_has_no_second_http_client():
    identifiers = _code_identifiers(AIServiceModelClient)
    for forbidden in ("httpx", "AsyncClient", "requests", "aiohttp"):
        assert forbidden not in identifiers, f"模型接缝引用了 {forbidden} —— 模型 HTTP 调用只经平台统一路由"
    # 判据本身没空转：同一函数对真正做 HTTP 的模块能扫出 httpx
    from app.services.llm_runtime import ResolvedLLMConfig

    assert "httpx" in _code_identifiers(ResolvedLLMConfig)
