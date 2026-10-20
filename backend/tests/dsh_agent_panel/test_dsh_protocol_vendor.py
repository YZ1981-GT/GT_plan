"""DSH 协议与进程管理对齐 vendor 真实实现（spec dsh-kb-ocr-local-first-routing Task 3 / 4 / 6）。

驱动方式：真 ``DshEngine._run`` + 真 Cordis 写盘 + 真子进程 env 构造 + 假运行时
``_fake_dsh_runtime.py``（按 vendor 协议应答，事件形状取自 2026-10-20 真实运行抓包）。
只替换两处：拉起哪个可执行文件（node 闭包 → 假运行时）、本 run 选哪个模型（不打真实端点）。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models.ai_models import ChatEngineName
from app.services.ai_chat import dsh_engine as D
from app.services.ai_chat.dsh_model_bridge import DshModelRoute, verify_token
from app.services.ai_chat.dsh_process import _drain_stderr, _process_group_kwargs
from app.services.ai_chat.engine import (
    NEVER_CANCELLED,
    AuthorizedChatRunRequest,
    EngineCancelled,
    EngineFailure,
    EventCancelSignal,
)
from app.services.ai_chat.run_contract import CAPABILITIES_BY_ENGINE, ChatErrorCode, ChatEventType

FAKE_RUNTIME = Path(__file__).with_name("_fake_dsh_runtime.py")
MODEL = "Kbenkhaled/Qwen3.5-27B-NVFP4"


class _Cfg:
    model_name = MODEL
    deployment = "local"
    identity = f"chat|openai_compatible|http://127.0.0.1:8100/v1|{MODEL}"


def _request(query: str = "列出本项目底稿") -> AuthorizedChatRunRequest:
    host = MagicMock()
    host.principal_id = uuid4()
    host.project_id = uuid4()
    host.permission_binding = "auditor"
    host.cycle_scope = frozenset({"D"})
    host.project_tools_enabled = True
    return AuthorizedChatRunRequest(
        run_id=uuid4(), session_id=uuid4(), request_id=uuid4(), host=host, query=query,
        engine=ChatEngineName.dsh, capabilities=CAPABILITIES_BY_ENGINE[ChatEngineName.dsh],
        assistant_message_id=uuid4(),
    )


def _available():
    from app.services.ai_chat.dsh_discovery import DshDiscoveryResult, DshDiscoveryStatus

    return DshDiscoveryResult(status=DshDiscoveryStatus.available, vendor_root=Path("."))


class _Harness:
    """记录假运行时收到的请求、子进程句柄与写盘的 Cordis 配置。"""

    def __init__(self, tmp_path: Path, scenario: str) -> None:
        self.scenario = scenario
        self.record = tmp_path / "requests.jsonl"
        self.procs: list[asyncio.subprocess.Process] = []
        self.session_dirs: list[Path] = []
        self.configs: list[list[dict[str, Any]]] = []
        self.envs: list[dict[str, str]] = []

    async def spawn(self, ctx: D.DshRunContext, **_kw: Any) -> asyncio.subprocess.Process:
        config_path = D._write_platform_cordis_config(ctx)
        self.configs.append(json.loads(Path(config_path).read_text(encoding="utf-8")))
        env = D._build_dsh_env(
            cordis_config=config_path, session_dir=str(ctx.session_dir), llm_token=ctx.llm_token or ""
        )
        self.envs.append(dict(env))
        env.update(FAKE_DSH_SCENARIO=self.scenario, FAKE_DSH_RECORD=str(self.record))
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(FAKE_RUNTIME),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=env, cwd=str(ctx.session_dir),
            **_process_group_kwargs(),
        )
        ctx.dsh_process = proc
        ctx.stderr_task = asyncio.create_task(_drain_stderr(ctx, proc.stderr))
        self.procs.append(proc)
        self.session_dirs.append(ctx.session_dir)
        return proc

    def requests(self) -> list[dict[str, Any]]:
        if not self.record.exists():
            return []
        return [json.loads(line) for line in self.record.read_text(encoding="utf-8").splitlines() if line]


async def _run(harness: _Harness, request: AuthorizedChatRunRequest, cancel=NEVER_CANCELLED):
    route = DshModelRoute(_Cfg(), 32768)  # type: ignore[arg-type]

    async def _select(_self):  # noqa: ANN001
        return route

    events: list[Any] = []
    with patch("app.services.ai_chat.dsh_discovery.discover_dsh_sdk", return_value=_available()), \
         patch.object(D.DshEngine, "_select_model", _select), \
         patch.object(D.DshProcessManager, "spawn_dsh_root", harness.spawn):
        engine = D.DshEngine(db=None, pool=D.DshWorkerPool())
        stream = engine.run(request, cancel)
        try:
            async for event in stream:
                events.append(event)
                if cancel is not NEVER_CANCELLED and event.type == ChatEventType.context_ready:
                    cancel.cancel()
        except (EngineFailure, EngineCancelled):
            pass  # 终态意图已作为最后一个事件产出；失败原因在 stream.outcome.failure
    return events, stream


def _types(events: list[Any]) -> list[str]:
    return [e.type.value for e in events]


@pytest.mark.asyncio
async def test_ok_turn_uses_real_protocol_and_records_served_model(tmp_path: Path) -> None:
    harness = _Harness(tmp_path, "ok")
    request = _request()
    events, _ = await _run(harness, request)

    assert _types(events) == ["context_ready", "delta", "delta", "done"], _types(events)
    assert [e.payload["text"] for e in events if e.type == ChatEventType.delta] == ["你好", "，审计师"]
    done = events[-1].payload
    assert done["model"] == MODEL and done["deployment"] == "local"
    assert done["usage"]["inputTokens"] == 36 and done["usage"]["outputTokens"] == 12

    methods = [r["method"] for r in harness.requests()]
    assert methods == ["initialize", "session/prompt", "shutdown"], methods
    init, prompt = harness.requests()[0]["params"], harness.requests()[1]["params"]
    # vendor 只注册 deepseek-official（旧值 local-vllm 每次握手必败，spec D2）
    assert init["provider"] == "deepseek-official" and init["model"] == MODEL
    assert prompt == {
        "sessionId": f"run-{request.run_id.hex}",
        "contentBlocks": [{"type": "text", "text": request.query}],
    }


@pytest.mark.asyncio
async def test_child_env_carries_run_token_not_upstream_key(tmp_path: Path) -> None:
    """子进程 env：只有 run 转发令牌（能解出本 run 与候选身份），没有任何上游 Key / DEEPSEEK_*。"""
    harness = _Harness(tmp_path, "ok")
    request = _request()
    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-should-not-leak"}):
        await _run(harness, request)
    env = harness.envs[0]
    assert "DEEPSEEK_API_KEY" not in env and "DEEPSEEK_BASE_URL" not in env
    claims = verify_token(env["GT_DSH_LLM_TOKEN"])
    assert claims.run_id == request.run_id and claims.identity == _Cfg.identity
    llm = next(i for i in harness.configs[0] if i["name"] == "@deepseek-ai/dsh-llm-deepseek")
    assert "sk-" not in json.dumps(harness.configs[0])
    assert llm["config"]["models"] == [{"id": MODEL, "contextWindow": 32768, "maxTokens": 8192}]


@pytest.mark.asyncio
async def test_tool_events_mapped_from_session_log(tmp_path: Path) -> None:
    events, _ = await _run(_Harness(tmp_path, "tools"), _request())
    started = [e.payload for e in events if e.type == ChatEventType.tool_started]
    finished = [e.payload for e in events if e.type == ChatEventType.tool_finished]
    assert started == [
        {"tool_name": "wp_list", "call_index": 1},
        {"tool_name": "tb_query", "call_index": 2},
    ]
    assert finished == [
        {"tool_name": "wp_list", "call_index": 1, "success": True},
        {"tool_name": "tb_query", "call_index": 2, "success": False},
    ]


@pytest.mark.asyncio
async def test_subagent_tools_counted_but_its_text_not_streamed(tmp_path: Path) -> None:
    events, _ = await _run(_Harness(tmp_path, "subagent"), _request())
    texts = "".join(e.payload["text"] for e in events if e.type == ChatEventType.delta)
    assert texts == "你好，审计师"  # 子 Agent 与无关 session 的文本都不进最终回答
    assert [e.payload["tool_name"] for e in events if e.type == ChatEventType.tool_started] == ["tb_query"]


@pytest.mark.asyncio
async def test_fallback_to_assistant_message_when_no_chunks(tmp_path: Path) -> None:
    events, _ = await _run(_Harness(tmp_path, "fallback_text"), _request())
    assert [e.payload["text"] for e in events if e.type == ChatEventType.delta] == ["整段回答"]
    assert events[-1].type == ChatEventType.done


@pytest.mark.asyncio
async def test_max_tokens_turn_end_counts_as_success(tmp_path: Path) -> None:
    """sdk-jsonrpc-server 配了 maxTokensAsSuccess：写满输出上限结束的一轮按成功收尾，已输出的回答保留。"""
    events, stream = await _run(_Harness(tmp_path, "max_tokens"), _request())
    assert _types(events) == ["context_ready", "delta", "delta", "done"], _types(events)
    assert stream.outcome.failure is None


@pytest.mark.asyncio
async def test_idle_status_before_turn_does_not_end_run(tmp_path: Path) -> None:
    """会话初始 / 刚收下 prompt 时的 idle 不是本轮结束：要等本轮 turn/end 之后的那次 idle。"""
    events, _ = await _run(_Harness(tmp_path, "spurious_idle"), _request())
    assert _types(events) == ["context_ready", "delta", "delta", "done"], _types(events)


@pytest.mark.asyncio
async def test_model_error_turn_end_fails_run_without_switching(tmp_path: Path) -> None:
    harness = _Harness(tmp_path, "model_error")
    events, stream = await _run(harness, _request())
    assert events[-1].type == ChatEventType.error
    failure = stream.outcome.failure
    assert isinstance(failure, EngineFailure) and failure.code == ChatErrorCode.engine_unavailable
    assert "max_tokens too large" in failure.detail and "HTTP 400" in failure.detail
    assert len(harness.procs) == 1  # 运行中失败不换候选重跑


def _leftover_session_dirs(request: AuthorizedChatRunRequest) -> list[Path]:
    import tempfile

    return list(Path(tempfile.gettempdir()).glob(f"dsh_run_{request.run_id.hex[:8]}_*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("fault,code", [
    ("secret", ChatErrorCode.engine_unavailable),  # 平台密钥缺失
    ("role", ChatErrorCode.access_denied),         # 未知角色 fail-closed（Req 11.9）
])
async def test_scoped_token_failure_is_typed_and_leaves_no_session_dir(tmp_path: Path, monkeypatch, fault, code) -> None:
    """MCP scoped token 签不出：run 以 typed error 结束，不拉起子进程，也不留会话临时目录。"""
    from app.services.ai_chat import mcp_token as M

    if fault == "secret":
        monkeypatch.setattr(M.settings, "JWT_SECRET_KEY", "")
    else:
        monkeypatch.setattr(D, "_resolve_role", lambda _request: "intern")
    harness = _Harness(tmp_path, "ok")
    request = _request()
    events, stream = await _run(harness, request)
    assert events[-1].type == ChatEventType.error
    failure = stream.outcome.failure
    assert isinstance(failure, EngineFailure) and failure.code == code, failure
    assert harness.procs == []
    assert _leftover_session_dirs(request) == [], "失败的 run 留下了会话目录"


@pytest.mark.asyncio
async def test_forward_token_failure_is_typed_engine_error(tmp_path: Path, monkeypatch) -> None:
    """模型转发令牌签不出：typed error（engine_unavailable），不拉起子进程，会话目录随 run 清理。"""
    from app.services.ai_chat import dsh_model_bridge as B

    def _no_key() -> bytes:
        raise B.DshTokenError("平台未配置 JWT_SECRET_KEY，不能签发或校验 DSH 转发令牌")

    monkeypatch.setattr(B, "_signing_key", _no_key)
    harness = _Harness(tmp_path, "ok")
    request = _request()
    events, stream = await _run(harness, request)
    assert events[-1].type == ChatEventType.error
    failure = stream.outcome.failure
    assert isinstance(failure, EngineFailure) and failure.code == ChatErrorCode.engine_unavailable
    assert "JWT_SECRET_KEY" in failure.detail
    assert harness.procs == []
    assert _leftover_session_dirs(request) == []


@pytest.mark.asyncio
async def test_runtime_exit_is_engine_unavailable(tmp_path: Path) -> None:
    events, stream = await _run(_Harness(tmp_path, "exit_after_prompt"), _request())
    assert events[-1].type == ChatEventType.error
    assert "提前退出" in stream.outcome.failure.detail


@pytest.mark.asyncio
async def test_cancel_terminates_process_and_cleans_session(tmp_path: Path) -> None:
    harness = _Harness(tmp_path, "hang")
    events, stream = await _run(harness, _request(), cancel=EventCancelSignal())
    assert events[-1].type == ChatEventType.cancelled
    assert isinstance(stream.outcome.failure, EngineCancelled)
    proc = harness.procs[0]
    assert proc.returncode is not None, "取消后 DSH 进程仍在运行"
    assert not harness.session_dirs[0].exists(), "取消后会话目录未清理"


@pytest.mark.asyncio
async def test_terminate_all_kills_grandchildren(tmp_path: Path) -> None:
    """进程树终止：DSH 根进程下的子进程（真实场景 = mcp-client 拉起的 MCP）一并结束。"""
    beat = tmp_path / "beat.txt"
    grandchild = f"import time\nwhile True:\n    open(r'{beat}', 'w').write(str(time.time()))\n    time.sleep(0.1)\n"
    parent = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
        "time.sleep(300)\n"
    )
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", parent, **_process_group_kwargs()
    )
    for _ in range(100):
        if beat.exists():
            break
        await asyncio.sleep(0.05)
    assert beat.exists(), "孙进程未启动"
    ctx = D.DshRunContext(run_id=uuid4(), principal_id=uuid4(), project_id=uuid4(), session_dir=tmp_path / "s")
    ctx.dsh_process = proc
    await D.DshProcessManager.terminate_all(ctx)
    assert proc.returncode is not None
    await asyncio.sleep(0.5)
    first = beat.stat().st_mtime_ns
    await asyncio.sleep(0.6)
    assert beat.stat().st_mtime_ns == first, "根进程终止后孙进程仍在运行（进程树未结束）"
    assert ctx.cleanup_errors == []


def test_session_dir_and_home_layout(tmp_path: Path) -> None:
    """DSH_HOME / 临时目录 / 会话日志都在本 run 会话目录下（不读写用户目录的 .dsh）。"""
    env = D._build_dsh_env(cordis_config="c.json", session_dir=str(tmp_path), llm_token="t")
    for key in ("DSH_HOME", "DSH_CWD", "DSH_SESSION_ROOT", "TEMP", "TMP"):
        assert Path(env[key]).is_relative_to(tmp_path), (key, env[key])
