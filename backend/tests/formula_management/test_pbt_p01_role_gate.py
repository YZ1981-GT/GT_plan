# Feature: formula-management-library, Property 1: 合伙人门禁授权且拒绝时不写数据（仅全局刷新）
"""属性测试 P1：合伙人一键刷新门禁——授权且拒绝时不写数据。

**Property 1: 合伙人门禁授权且拒绝时不写数据（仅全局刷新）**

*对任意*系统角色，全局 ``/draft-refresh`` 一键刷新入口所施加的
``require_role(["partner", "signing_partner"])`` 门禁：

- **当且仅当**角色 ∈ ``{partner, signing_partner}`` 时依赖放行（返回该用户）；
- 否则在**依赖解析阶段**抛 ``HTTPException(status_code=403)``，
  该拦截先于任何数据写入发生（依赖解析失败 → 端点函数体从不执行 →
  ``refresh`` 编排器/任何写库逻辑都不会被触及）。

被测：``app.deps.require_role``（`wp_render_config.py` 全局 ``/draft-refresh``
一键刷新门禁 ``["partner", "signing_partner"]``，见 Task 5.5）。

构造最小 ``User`` 替身（``role.value`` 为随机角色，含 UserRole 枚举成员与
枚举外的 ``signing_partner``），以门禁列表成员资格判定期望结果。
``signing_partner`` 可能不在 ``UserRole`` 枚举内——测试仅按门禁列表成员判断即可。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。

**Validates: Requirements 1.1, 1.2, 1.5**
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from hypothesis import given
from hypothesis import strategies as st

from app.deps import require_role

# 全局 /draft-refresh 一键刷新门禁列表（Task 5.5：wp_render_config.py 统一入口）。
_GATE_ROLES = ["partner", "signing_partner"]

# 候选角色：UserRole 枚举全体 + 门禁列表特有的 signing_partner（枚举外）+ 若干噪声值。
# 按门禁列表成员资格判定期望，不依赖角色是否在 UserRole 枚举内。
_CANDIDATE_ROLES = st.sampled_from(
    [
        "admin",
        "partner",
        "manager",
        "auditor",
        "qc",
        "readonly",
        "signing_partner",
        "assistant",
        "",
        "PARTNER",  # 大小写敏感：不等于 "partner"
    ]
)


def _make_user(role: str):
    """构造最小 User 替身：仅需 ``role.value``（require_role 只读该字段）。"""
    return SimpleNamespace(role=SimpleNamespace(value=role))


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Feature: formula-management-library, Property 1: 合伙人门禁授权且拒绝时不写数据（仅全局刷新）
@given(role=_CANDIDATE_ROLES)
def test_p1_gate_allows_iff_partner_roles(role):
    """当且仅当角色 ∈ {partner, signing_partner} 时门禁放行，否则 403。

    **Validates: Requirements 1.1, 1.2**
    """
    dependency = require_role(_GATE_ROLES)
    user = _make_user(role)

    if role in _GATE_ROLES:
        # 授权路径：依赖放行并原样返回该用户（端点函数体方可执行 → 允许写入）。
        result = _run(dependency(current_user=user))
        assert result is user
    else:
        # 拒绝路径：依赖解析阶段即抛 403，先于任何写入。
        with pytest.raises(HTTPException) as exc_info:
            _run(dependency(current_user=user))
        assert exc_info.value.status_code == 403


# Feature: formula-management-library, Property 1: 合伙人门禁授权且拒绝时不写数据（仅全局刷新）
@given(role=_CANDIDATE_ROLES)
def test_p1_non_partner_blocked_before_any_write(role):
    """非合伙人被依赖解析阶段拦截，先于任何写入逻辑（Req 1.5）。

    以「写入探针」验证：门禁拒绝时，依赖抛出 403，模拟端点体内的写入探针
    从不被调用（依赖解析失败 → 端点函数体不执行）。授权时写入探针方可执行。

    **Validates: Requirements 1.5**
    """
    dependency = require_role(_GATE_ROLES)
    user = _make_user(role)
    write_probe = {"called": False}

    async def _endpoint_with_write():
        # 模拟真实端点：先解析门禁依赖，通过后才执行写入。
        current = await dependency(current_user=user)
        write_probe["called"] = True  # 任何数据写入发生在门禁之后
        return current

    if role in _GATE_ROLES:
        result = _run(_endpoint_with_write())
        assert result is user
        assert write_probe["called"] is True
    else:
        with pytest.raises(HTTPException) as exc_info:
            _run(_endpoint_with_write())
        assert exc_info.value.status_code == 403
        # 关键不变量：拒绝时写入探针从未被触及（先于任何写入拦截）。
        assert write_probe["called"] is False
