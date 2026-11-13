"""启用 / 更新「当前不可用」的本机或企业预设模型时的提示（`routers.ai_models._local_unavailable_warning`）。

提交 `a15d5590e`（企业预设离线可启用）给提示加了企业预设分支，用到 `deployment_of` 与 `AIDeployment` 却没有导入 ⇒
只要验证失败（``failure`` 非空）就 NameError：启用 / 更新不可用的本机或企业预设模型恒 500 —— 正是该提交要放开的场景。
由全应用函数全局名棘轮（``test_function_global_names_ratchet``）在合并后的提交树上发现（spec formula-fetch-followup-defect-closure 7.3）。
"""
from __future__ import annotations

import uuid
from contextlib import nullcontext

import pytest

from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.routers import ai_models as router
from app.services.ai_service import AIService, ModelValidationFailure

FAILURE = ModelValidationFailure(code="model_unavailable", message="连接被拒绝", kind="unavailable")


class _Db:
    """只用到 ``no_autoflush``（兜底候选查询由下面的替身回答）。"""

    no_autoflush = nullcontext()


def _model(*, deployment: str, preset_key: str | None = None,
           model_type: AIModelType = AIModelType.chat) -> AIModelConfig:
    return AIModelConfig(id=uuid.uuid4(), model_name="m", model_type=model_type, provider=AIProvider.openai_compatible,
                         endpoint_url="http://127.0.0.1:8100/v1", deployment=deployment, preset_key=preset_key)


@pytest.fixture
def fallback(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """替身：记录被问的部署位置，按 ``answer`` 回答有没有可兜底的候选。"""
    state: dict[str, object] = {"answer": False, "asked": []}

    async def _route_slot_taken(_db, *, model_type, deployment, ocr_capability, exclude_id):  # noqa: ANN001
        state["asked"].append(deployment)  # type: ignore[union-attr]
        return state["answer"]

    monkeypatch.setattr(AIService, "route_slot_taken", staticmethod(_route_slot_taken))
    return state


@pytest.mark.asyncio
async def test_no_failure_means_no_warning(fallback) -> None:
    assert await router._local_unavailable_warning(_Db(), _model(deployment="local"), None) is None


@pytest.mark.asyncio
async def test_local_model_unavailable_names_the_server_fallback(fallback) -> None:
    fallback["answer"] = True
    text = await router._local_unavailable_warning(_Db(), _model(deployment="local"), FAILURE)
    assert text.startswith("本机模型当前不可用（连接被拒绝），已启用"), text
    # 需求 4.4：兜底提示点明实际去向（服务器模型），不只说「另一候选」
    assert "服务器模型兜底" in text, text
    assert fallback["asked"] == ["server"], "本机模型不可用时应问有没有服务器候选"


@pytest.mark.asyncio
async def test_preset_unavailable_without_fallback_says_calls_will_fail(fallback) -> None:
    text = await router._local_unavailable_warning(_Db(), _model(deployment="server", preset_key="corp-chat"), FAILURE)
    assert text.startswith("企业预设当前不可达（连接被拒绝）") and "AI 调用会失败" in text, text
    assert fallback["asked"] == ["local"], "服务器侧的企业预设不可达时应问有没有本机候选"


@pytest.mark.asyncio
async def test_embedding_never_falls_back_across_models(fallback) -> None:
    text = await router._local_unavailable_warning(
        _Db(), _model(deployment="local", model_type=AIModelType.embedding), FAILURE)
    assert "向量模型不跨模型兜底" in text and fallback["asked"] == [], text


# ── spec enterprise-embedding-rerank-closure R11.1 / R11.2：按类型与部署位置如实说明后果 ──────────────


@pytest.mark.asyncio
async def test_embedding_preset_names_its_own_recovery_condition(fallback) -> None:
    text = await router._local_unavailable_warning(
        _Db(), _model(deployment="server", preset_key="gt_wemm_embedding_4b", model_type=AIModelType.embedding),
        FAILURE,
    )
    assert "连上公司网络后自动生效" in text and "在此之前语义检索不可用" in text and "词法召回" in text, text
    assert "本机恢复前" not in text, "服务器端企业预设不该说「本机恢复前」"


@pytest.mark.asyncio
async def test_local_embedding_says_until_the_local_service_recovers(fallback) -> None:
    text = await router._local_unavailable_warning(
        _Db(), _model(deployment="local", model_type=AIModelType.embedding), FAILURE)
    assert "本机服务恢复前语义检索不可用" in text, text


@pytest.mark.asyncio
async def test_rerank_without_fallback_is_fail_open_not_a_failed_call(fallback) -> None:
    text = await router._local_unavailable_warning(
        _Db(), _model(deployment="server", preset_key="gt_qwen3_reranker_4b", model_type=AIModelType.rerank), FAILURE)
    assert "知识检索不重排" in text and "AI 调用会失败" not in text, text
    assert fallback["asked"] == ["local"]


@pytest.mark.asyncio
async def test_rerank_with_fallback_names_the_fallback(fallback) -> None:
    fallback["answer"] = True
    text = await router._local_unavailable_warning(
        _Db(), _model(deployment="server", preset_key="gt_qwen3_reranker_4b", model_type=AIModelType.rerank), FAILURE)
    assert "本机模型兜底" in text, text


def test_update_path_allows_unreachable_presets_like_activation() -> None:
    preset = _model(deployment="server", preset_key="gt_wemm_embedding_4b", model_type=AIModelType.embedding)
    custom_server = _model(deployment="server")
    assert router._local_unavailable(preset, FAILURE) is True
    assert router._local_unavailable(custom_server, FAILURE) is False
    config_error = ModelValidationFailure(code="provider_auth_failed", message="401", kind="config")
    assert router._local_unavailable(preset, config_error) is False
