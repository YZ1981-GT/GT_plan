"""Chat Run citation/delta/history 共用一个服务端消息 ID。"""

from types import SimpleNamespace
from uuid import uuid4

from app.models.ai_models import ChatEngineName
from app.services.ai_chat.engine import AuthorizedChatRunRequest
from app.services.ai_chat.run_contract import capabilities_for
from app.services.ai_chat.run_coordinator import RunExecution


def test_run_execution_message_id_survives_engine_coercion() -> None:
    actor_id = uuid4()
    creation = SimpleNamespace(
        run_id=uuid4(),
        session_id=uuid4(),
        request_id=uuid4(),
        host=SimpleNamespace(principal_id=actor_id),
        request=SimpleNamespace(
            query="测试",
            review_mode=False,
            sheet_name=None,
            mention_pairs=lambda: [],
            attachment_ids=[],
            project_attachment_ids=[],
        ),
        engine=ChatEngineName.native,
        capabilities=capabilities_for(ChatEngineName.native),
    )
    execution = RunExecution.from_creation(creation)
    authorized = AuthorizedChatRunRequest.coerce(execution)
    assert authorized.assistant_message_id == execution.assistant_message_id
    assert authorized.run_id == execution.run_id


def test_each_run_gets_a_distinct_message_id() -> None:
    actor_id = uuid4()
    def make():
        creation = SimpleNamespace(
            run_id=uuid4(), session_id=uuid4(), request_id=uuid4(),
            host=SimpleNamespace(principal_id=actor_id),
            request=SimpleNamespace(
                query="测试", review_mode=False, sheet_name=None,
                mention_pairs=lambda: [], attachment_ids=[], project_attachment_ids=[],
            ),
            engine=ChatEngineName.native,
            capabilities=capabilities_for(ChatEngineName.native),
        )
        return RunExecution.from_creation(creation)
    assert make().assistant_message_id != make().assistant_message_id


async def _chunks():
    import asyncio
    await asyncio.sleep(0.002)
    yield "第一段"
    await asyncio.sleep(0.002)
    yield "第二段"


class _TimedModel:
    served_model = "fake"
    served_route = None

    async def resolve_model(self):
        return "fake"

    def stream_chat(self, messages, *, model):
        return _chunks()


def test_stream_records_real_ttft_not_total_latency() -> None:
    import asyncio

    from app.services.ai_chat.engine import EngineOutcome, NEVER_CANCELLED
    from app.services.ai_chat.native_engine import NativeEngine

    actor_id = uuid4()
    creation = SimpleNamespace(
        run_id=uuid4(), session_id=uuid4(), request_id=uuid4(),
        host=SimpleNamespace(principal_id=actor_id),
        request=SimpleNamespace(
            query="测试", review_mode=False, sheet_name=None,
            mention_pairs=lambda: [], attachment_ids=[], project_attachment_ids=[],
        ),
        engine=ChatEngineName.native,
        capabilities=capabilities_for(ChatEngineName.native),
    )
    request = AuthorizedChatRunRequest.coerce(RunExecution.from_creation(creation))
    outcome = EngineOutcome()

    async def drive():
        engine = NativeEngine(None, model=_TimedModel())
        return [event async for event in engine._stream_model(
            request, NEVER_CANCELLED, outcome, [{"role": "user", "content": "测试"}]
        )]

    events = asyncio.run(drive())
    assert len(events) == 2
    assert outcome.ttft_ms is not None and outcome.ttft_ms >= 0
    assert outcome.generation_ms is not None and outcome.generation_ms >= 1
    assert outcome.ttft_ms != outcome.ttft_ms + outcome.generation_ms
