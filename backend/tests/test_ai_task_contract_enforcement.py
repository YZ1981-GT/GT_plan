"""AiTaskSpec 声明字段真实生效 + 事实验证器口径（spec llm-linkage-audit-practice-closure 任务 7/9/14）。

覆盖：动作能力、任务超时、可复现 envelope、Prompt 版本哈希锁、Decimal/日期/主体核对、
事实包派生变动额与变动率、变动分析拒收客户端事实。
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.services import ai_task_executor
from app.services.ai_task_executor import invoke_ai_task
from app.services.ai_task_registry import get_ai_task_spec
from app.services.ai_task_verifier import verify_ai_output
from app.services.llm_client import LLMInvocationResult, LLMInvocationStatus


def _ok(text: str) -> LLMInvocationResult:
    return LLMInvocationResult(
        status=LLMInvocationStatus.success, text=text, model_name="fake", deployment="local"
    )


def _verify(task: str, output: str, prompt: str, docs=(), facts=()):
    return verify_ai_output(
        get_ai_task_spec(task), output, user_prompt=prompt,
        system_addendum=None, context_documents=list(docs), allowed_facts=list(facts),
    )


# ── 动作 / 超时 / envelope ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_action_outside_task_declaration_is_rejected_before_model() -> None:
    model = AsyncMock()
    with patch("app.services.ai_task_executor.chat_completion_result", new=model):
        invocation = await invoke_ai_task(
            "review.workpaper", user_prompt="底稿", role="qc", action="draft"
        )
    assert invocation.result.status is LLMInvocationStatus.rejected
    assert invocation.result.error_code == "ai_action_denied"
    model.assert_not_called()
    assert invocation.envelope["action"] == "draft"


def test_review_panel_roles_match_review_task_declaration() -> None:
    """复核面板的启动按钮角色集合必须与 ``review.workpaper`` 任务声明逐值一致（ADR-LLM-008）。

    前端只显示后端会放行的入口：两边任何一侧单独改动都会让按钮显示却 403，或该放行的角色看不到。
    """
    import re
    from pathlib import Path

    vue = (
        Path(__file__).resolve().parents[2]
        / "audit-platform/frontend/src/components/workpaper/review/AiReviewPanel.vue"
    ).read_text(encoding="utf-8")
    match = re.search(r"const allowedRoles = \[([^\]]*)\]", vue)
    assert match, "AiReviewPanel.vue 未找到 allowedRoles 角色集合"
    frontend_roles = set(re.findall(r"'([a-z_]+)'", match.group(1)))
    assert frontend_roles == set(get_ai_task_spec("review.workpaper").allowed_roles)


@pytest.mark.asyncio
async def test_missing_role_or_action_is_rejected_before_model() -> None:
    """调用方漏传角色 / 动作时不得放行：否则角色与动作门禁形同虚设（ADR-LLM-008）。"""
    model = AsyncMock()
    with patch("app.services.ai_task_executor.chat_completion_result", new=model):
        no_role = await invoke_ai_task("note.policy_draft", user_prompt="事实", action="draft")
        no_action = await invoke_ai_task("note.policy_draft", user_prompt="事实", role="auditor")
        blank_role = await invoke_ai_task(
            "note.policy_draft", user_prompt="事实", role="", action="draft"
        )
    assert no_role.result.error_code == "ai_role_missing"
    assert no_action.result.error_code == "ai_action_denied"
    assert blank_role.result.error_code == "ai_role_missing"
    for invocation in (no_role, no_action, blank_role):
        assert invocation.result.status is LLMInvocationStatus.rejected
        assert invocation.result.text is None
    model.assert_not_called()


def test_every_production_call_site_declares_role_and_action() -> None:
    """生产调用点必须显式传 role 与 action —— 漏传会被执行器拒绝，页面只会看到「不能执行」。"""
    import ast
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[1] / "app"
    missing: list[str] = []
    seen = 0
    for path in sorted(app_dir.rglob("*.py")):
        # 仓库里有带 BOM 的历史文件：按 utf-8-sig 读，否则 ast.parse 报 U+FEFF
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            if name != "invoke_ai_task":
                continue
            seen += 1
            kwargs = {kw.arg for kw in node.keywords}
            if not {"role", "action"} <= kwargs:
                missing.append(f"{path.relative_to(app_dir.parent).as_posix()}:{node.lineno}")
    assert seen >= 13, f"只扫到 {seen} 个调用点，扫描口径可能失效"
    assert missing == [], f"这些调用点没显式声明角色 / 动作：{missing}"


def test_task_actions_follow_output_semantics() -> None:
    assert get_ai_task_spec("review.workpaper").allowed_actions == {"review"}
    assert get_ai_task_spec("note.completeness_review").allowed_actions == {"review"}
    assert get_ai_task_spec("chat.general").allowed_actions == {"ask"}
    assert get_ai_task_spec("note.policy_draft").allowed_actions == {"draft"}
    # 外层超时随输出上限放宽，不再一律 90 秒（3000 token 的复核在本机模型上会被误杀）
    assert get_ai_task_spec("review.workpaper").timeout_seconds >= 300


@pytest.mark.asyncio
async def test_task_timeout_is_typed_and_never_a_draft(monkeypatch) -> None:
    spec = dataclasses.replace(get_ai_task_spec("note.policy_draft"), timeout_seconds=0.05)
    monkeypatch.setattr(ai_task_executor, "get_ai_task_spec", lambda _code: spec)

    async def slow(*_args, **_kwargs):
        await asyncio.sleep(1)
        return _ok("迟到的正文")

    with patch("app.services.ai_task_executor.chat_completion_result", new=slow):
        invocation = await invoke_ai_task(
            "note.policy_draft", user_prompt="事实", role="auditor", action="draft"
        )
    assert invocation.result.status is LLMInvocationStatus.timeout
    assert invocation.result.error_code == "task_timeout"
    assert invocation.result.text is None


@pytest.mark.asyncio
async def test_envelope_hashes_inputs_without_storing_text() -> None:
    secret = "客户机密事实 123456.78"
    doc = "参照资料 机密段落"
    with patch(
        "app.services.ai_task_executor.chat_completion_result",
        new=AsyncMock(return_value=_ok("政策草稿")),
    ):
        invocation = await invoke_ai_task(
            "note.policy_draft", user_prompt=secret, context_documents=[doc],
            role="auditor", action="draft", temperature=0.1,
        )
    meta = invocation.audit_metadata()
    envelope = meta["envelope"]
    dumped = json.dumps(meta, ensure_ascii=False)
    assert secret not in dumped and doc not in dumped and "政策草稿" not in dumped
    assert envelope["prompt"]["sha256"] == invocation.prompt_hash
    assert envelope["parameters"]["temperature"] == 0.1
    assert envelope["parameters"]["max_output_tokens"] == invocation.spec.max_output_tokens
    assert len(envelope["context"]["document_sha256"]) == 1
    assert envelope["output_sha256"] == invocation.verifier.output_hash
    assert envelope["verifier"]["status"] == "passed"
    assert meta["envelope_hash"] and len(meta["envelope_hash"]) == 64


def test_estimated_cost_uses_configured_unit_price_only(monkeypatch) -> None:
    from app.services.ai_chat.metrics import estimate_task_cost

    monkeypatch.delenv("GT_AI_TOKEN_UNIT_COST", raising=False)
    assert estimate_task_cost("server", 1000, 500) == 0  # 未配置单价：只记 token，不臆造成本
    monkeypatch.setenv("GT_AI_TOKEN_UNIT_COST", '{"local": 0, "server": 0.002}')
    assert estimate_task_cost("server", 1000, 500) == 0.003
    assert estimate_task_cost("local", 1000, 500) == 0
    monkeypatch.setenv("GT_AI_TOKEN_UNIT_COST", "not-json")
    assert estimate_task_cost("server", 1000, 500) == 0


# ── Prompt 版本 append-only ─────────────────────────────────────────────


def test_published_prompt_versions_match_hash_lock() -> None:
    from scripts.check.check_ai_prompt_versions import compare, load_lock, registry_hashes

    diff = compare(registry_hashes(), load_lock())
    assert diff == {"changed": [], "removed": [], "unlocked": []}


def test_editing_a_published_prompt_in_place_is_detected() -> None:
    from scripts.check.check_ai_prompt_versions import compare, registry_hashes

    current = registry_hashes()
    locked = dict(current)
    key = next(iter(current))
    mutated = {**current, key: "0" * 64}
    assert compare(mutated, locked)["changed"] == [key]
    removed = dict(current)
    removed.pop(key)
    assert compare(removed, locked)["removed"] == [key]
    assert compare({**current, "new.prompt@1.0.0": "a" * 64}, locked)["unlocked"] == ["new.prompt@1.0.0"]


# ── 事实验证器 ─────────────────────────────────────────────────────────


def test_numbers_compare_by_decimal_value() -> None:
    assert _verify("note.change_analysis", "本期余额 1,000.00 元，占比 12.50%。", "余额 1000，占比 12.5%").status == "passed"
    failed = _verify("note.change_analysis", "本期余额 1,000.01 元。", "余额 1000")
    assert failed.status == "failed" and "1000.01" in failed.message


def test_dates_must_come_from_facts_or_period_end() -> None:
    prompt = "本期（2025 年）余额 1000"
    assert _verify("note.change_analysis", "截至2025年12月31日余额1000元。", prompt).status == "passed"
    assert _verify("note.change_analysis", "上年末即2024年12月31日。", prompt).status == "passed"
    invented = _verify("note.change_analysis", "于2025年6月30日完成转让。", prompt)
    assert invented.status == "failed" and "2025-06-30" in invented.message


def test_entities_must_come_from_facts() -> None:
    prompt = "主要客户：重庆医药（集团）股份有限公司，余额 1000"
    assert _verify(
        "note.change_analysis", "本期向重庆医药（集团）股份有限公司销售，余额1000元。", prompt
    ).status == "passed"
    assert _verify("note.change_analysis", "各子公司均为有限公司。", prompt).status == "passed"
    invented = _verify("note.change_analysis", "主要客户为蓝海科技有限公司。", prompt)
    assert invented.status == "failed" and "蓝海科技有限公司" in invented.message


def test_change_analysis_ignores_numbers_only_in_reference_docs() -> None:
    prompt = "本期余额 1000，上期余额 800"
    docs = ["上年附注：其他应收款 777777 元"]
    assert _verify("note.change_analysis", "余额为777777元。", prompt, docs).status == "failed"
    # 改写 / 续写可以沿用参照资料原文里的数字
    assert _verify("note.rewrite", "余额为777777元。", prompt, docs).status == "passed"


def test_derived_change_amount_and_rate_are_verifiable() -> None:
    from app.services.note_ai_fact_pack import NoteFactPack

    pack = NoteFactPack(
        note_id=None, note_section="五、1", section_title="货币资金", account_name="货币资金",
        year=2025, current_data={"rows": [{"期末": "1,500.00"}]}, prior_data={"rows": [{"期初": 1000}]},
        source_refs=(),
    )
    facts = pack.derived_fact_tokens()
    output = "期末余额1,500.00元，较上期增加500.00元，增幅50.00%。"
    assert _verify("note.change_analysis", output, pack.prompt_text()).status == "failed"
    assert _verify("note.change_analysis", output, pack.prompt_text(), facts=facts).status == "passed"
    wrong = _verify("note.change_analysis", "较上期增加600.00元。", pack.prompt_text(), facts=facts)
    assert wrong.status == "failed"


def test_change_analysis_rejects_client_supplied_facts() -> None:
    from app.routers.note_ai import AnalysisGenerateRequest

    with pytest.raises(ValidationError, match="服务端"):
        AnalysisGenerateRequest(section_number="五、1", current_data={"期末": 1})
    assert AnalysisGenerateRequest(section_number="五、1", current_data=None).current_data is None
