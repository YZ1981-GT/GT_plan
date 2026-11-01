"""AI 任务链金标确定性回放（spec llm-linkage-audit-practice-closure 任务 16）。

金标在 ``backend/data/ai_golden_cases.json``，无客户数据；本测试用 ``fake_output`` 替换模型，
真实模型的同一批用例由 ``scripts/check/ai_live_canary.py`` 跑（发布前、需模型可达）。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai_task_executor import invoke_ai_task
from app.services.ai_task_registry import get_ai_task_spec, get_prompt
from app.services.llm_client import LLMInvocationResult, LLMInvocationStatus

GOLDEN = Path(__file__).resolve().parents[1] / "data" / "ai_golden_cases.json"
CASES = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]
REQUIRED_CATEGORIES = {"citation", "number", "final_opinion", "injection", "permission", "fallback", "ocr"}


def test_golden_set_covers_required_categories_and_registered_tasks() -> None:
    assert REQUIRED_CATEGORIES <= {case["category"] for case in CASES}
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids)), "金标 id 重复"
    for case in CASES:
        get_ai_task_spec(case["task_code"])  # 未登记任务直接抛错


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
async def test_golden_case(case) -> None:
    fake = LLMInvocationResult(
        status=LLMInvocationStatus.success,
        text=case["fake_output"],
        model_name="golden-fake",
        deployment=case.get("fake_deployment", "local"),
        fallback_used=bool(case.get("fake_fallback_used", False)),
    )
    model = AsyncMock(return_value=fake)
    with patch("app.services.ai_task_executor.chat_completion_result", new=model):
        invocation = await invoke_ai_task(
            case["task_code"],
            user_prompt=case["user_prompt"],
            context_documents=case.get("context_documents") or None,
            role=case["role"],
            action=case.get("action"),
            verifier_facts=case.get("verifier_facts"),
        )
    expect = case["expect"]
    result = invocation.result
    assert result.status.value == expect["status"], (result.error_code, result.error_message)
    if "error_code" in expect:
        assert result.error_code == expect["error_code"]
    if expect["status"] == "success":
        assert result.text == case["fake_output"]
    else:
        assert result.text is None, "失败结果不得携带可采纳正文"
    if expect.get("model_called") is False:
        model.assert_not_called()
    elif model.await_count:
        # 注入用例也只能把输入当数据：系统提示词必须是登记版本，不被用户文本改写
        sent = model.await_args.args[0]
        spec = get_ai_task_spec(case["task_code"])
        assert sent[0]["content"].startswith(get_prompt(spec.prompt_id, spec.prompt_version).content)
    if "deployment" in expect:
        assert invocation.envelope["model"]["deployment"] == expect["deployment"]
        assert invocation.envelope["model"]["fallback_used"] is expect["fallback_used"]
        assert invocation.audit_metadata()["fallback_used"] is expect["fallback_used"]


def test_live_canary_dry_run_validates_golden_file() -> None:
    from scripts.check.ai_live_canary import load_cases, main

    live = [case for case in load_cases() if case.get("live")]
    assert live and all(case["id"] for case in live)
    assert main(["--dry-run"]) == 0
