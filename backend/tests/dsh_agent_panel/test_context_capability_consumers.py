"""Capability 必须对应 ContextPlan 的真实生产 consumer。"""

import ast
import inspect

from app.models.ai_models import ChatEngineName
from app.services.ai_chat import context_plan
from app.services.ai_chat.context_capabilities import CONTEXT_CAPABILITY_ADAPTERS
from app.services.ai_chat.run_contract import capabilities_for


def _called_names(fn) -> set[str]:
    tree = ast.parse(inspect.getsource(fn))
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def test_declared_context_capabilities_have_real_production_calls() -> None:
    source = inspect.getsource(context_plan.build_context_plan)
    calls = _called_names(context_plan.build_context_plan)
    for capability, adapter in CONTEXT_CAPABILITY_ADAPTERS.items():
        leaf = adapter.rsplit(".", 1)[-1]
        assert leaf in calls or leaf in source, f"{capability} 声明可用但 ContextPlan 未调用 {adapter}"


def test_both_engines_publish_only_registered_optional_capabilities() -> None:
    for engine in ChatEngineName:
        caps = capabilities_for(engine)
        assert caps.attachments == ("attachments" in CONTEXT_CAPABILITY_ADAPTERS)
        assert caps.review_mode == ("review_mode" in CONTEXT_CAPABILITY_ADAPTERS)
