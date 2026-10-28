"""编辑锁「锁语义」用例共用：资源判定放行（这些文件测 409 / 续期 / 释放 / 强抢，用的是合成资源 id）。

资源鉴权（底稿门 / 项目成员 / 强制接管全权身份）另有真库用例：
``tests/procedure_delegation_visibility/test_editing_lock_authz_pg.py``（spec procedure-chain-hardening-and-java-contracts R2）。
放行时仍按 ``_resolve_project_id`` 给出底稿所属项目，SSE 载荷里的 project_id 断言照旧成立。
"""
import pytest


def lock_error_detail(resp_json: dict) -> dict:
    """错误响应里的 detail：全局处理器把 HTTPException 包成 ``{code, message}``（dict 形态的 detail 在 message 里）。

    几个锁语义用例原先读 ``resp.json()["detail"]``，处理器改信封后一直读不到（基线就红，与本 spec 无关，顺带修正）。
    """
    msg = resp_json.get("message")
    if isinstance(msg, dict):
        return msg
    return resp_json.get("detail", resp_json)


@pytest.fixture(autouse=True)
def lock_targets_visible(monkeypatch):
    from app.routers import editing_locks

    async def _allow(db, user, resource_type, resource_id, *, mode):
        return await editing_locks._resolve_project_id(db, resource_type, resource_id)

    monkeypatch.setattr(editing_locks, "_authorize_lock", _allow)
