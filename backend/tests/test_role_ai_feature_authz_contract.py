"""角色 AI 路由的项目级权限必须与实际用途一致。"""

import inspect

import pytest

from app.routers import role_ai_features


EXPECTED = {
    "stale_reminders": "readonly",
    "weekly_report": "edit",
    "qc_trend": "review",
    "project_summary": "review",
}


def _captured_level(endpoint) -> str:
    dependency = inspect.signature(endpoint).parameters["current_user"].default.dependency
    cells = dict(
        zip(
            dependency.__code__.co_freevars,
            (cell.cell_contents for cell in dependency.__closure__ or ()),
        )
    )
    return cells["min_permission"]


@pytest.mark.parametrize(("name", "level"), EXPECTED.items())
def test_role_ai_endpoint_has_project_permission(name: str, level: str) -> None:
    endpoint = getattr(role_ai_features, name)
    assert _captured_level(endpoint) == level


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "level"), EXPECTED.items())
async def test_real_dependency_calls_authoritative_project_gate(
    name: str, level: str, monkeypatch
) -> None:
    endpoint = getattr(role_ai_features, name)
    dependency = inspect.signature(endpoint).parameters["current_user"].default.dependency
    sentinel = object()
    calls = []

    async def gate(db, user, project_id, min_permission):
        calls.append((db, user, project_id, min_permission))
        return sentinel

    monkeypatch.setattr("app.deps.assert_project_permission", gate)
    project_id = __import__("uuid").uuid4()
    result = await dependency(
        project_id=project_id,
        current_user=object(),
        db=object(),
    )
    assert result is sentinel
    assert calls[0][2:] == (project_id, level)


def test_review_metrics_is_admin_only() -> None:
    from app.routers import review_prompt

    dependency = inspect.signature(review_prompt.get_review_metrics).parameters[
        "current_user"
    ].default.dependency
    cells = dict(
        zip(
            dependency.__code__.co_freevars,
            (cell.cell_contents for cell in dependency.__closure__ or ()),
        )
    )
    allowed = cells.get("allowed_roles") or cells.get("roles")
    assert set(allowed) == {"admin"}
