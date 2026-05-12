"""F19 / Sprint 4.18 — ledger_import_view_refactor_enabled feature flag 测试

验证 feature_flags.py 中 Sprint 4.15 新增的 B' 视图重构 flag：
1. 全局默认 True（pilot maturity，但已默认开启）
2. 项目级 override 覆盖全局（set_project_flag 后 is_enabled 变 False）
3. maturity 查询返回 "pilot"

不测试 DatasetService.activate 的行为切换 — 当前 flag 只是定义了，尚未
wire 到 activate 控制流中（wiring 是后续 Sprint 任务）。
"""

from __future__ import annotations

import uuid

import pytest

from app.services.feature_flags import (
    get_all_flags,
    get_feature_maturity,
    is_enabled,
    set_project_flag,
    _project_overrides,
)


FLAG = "ledger_import_view_refactor_enabled"


@pytest.fixture(autouse=True)
def _reset_overrides():
    """每个测试后清理 project-level overrides，避免相互污染。"""
    yield
    _project_overrides.clear()


class TestGlobalDefault:
    def test_global_default_is_true(self):
        """flag 全局默认 True（Sprint 4.15 决策：默认开启，出问题再单项目回退）。"""
        assert is_enabled(FLAG) is True

    def test_flag_present_in_all_flags(self):
        flags = get_all_flags()
        assert FLAG in flags
        assert flags[FLAG] is True

    def test_no_project_id_uses_global(self):
        """未传 project_id 或 None → 取全局默认。"""
        assert is_enabled(FLAG, project_id=None) is True


class TestProjectOverride:
    def test_set_project_flag_to_false_overrides_global(self):
        pid = uuid.uuid4()
        set_project_flag(pid, FLAG, False)
        assert is_enabled(FLAG, project_id=pid) is False

    def test_set_project_flag_to_true_explicit(self):
        pid = uuid.uuid4()
        set_project_flag(pid, FLAG, True)
        assert is_enabled(FLAG, project_id=pid) is True

    def test_override_does_not_leak_across_projects(self):
        pid_a = uuid.uuid4()
        pid_b = uuid.uuid4()
        set_project_flag(pid_a, FLAG, False)
        # A 被 override 为 False
        assert is_enabled(FLAG, project_id=pid_a) is False
        # B 仍然取全局 True
        assert is_enabled(FLAG, project_id=pid_b) is True
        # 显式 None 也回到全局
        assert is_enabled(FLAG, project_id=None) is True

    def test_string_project_id_works(self):
        """is_enabled / set_project_flag 接受 str 和 UUID。"""
        pid_uuid = uuid.uuid4()
        pid_str = str(pid_uuid)
        set_project_flag(pid_str, FLAG, False)
        # 同一 project 的两种形态都能命中 override
        assert is_enabled(FLAG, project_id=pid_str) is False
        assert is_enabled(FLAG, project_id=pid_uuid) is False

    def test_get_all_flags_reflects_project_override(self):
        pid = uuid.uuid4()
        set_project_flag(pid, FLAG, False)
        flags = get_all_flags(project_id=pid)
        assert flags[FLAG] is False


class TestMaturity:
    def test_flag_maturity_is_pilot(self):
        maturity = get_feature_maturity()
        assert FLAG in maturity, (
            f"Missing maturity for {FLAG} — should be classified as 'pilot' in Sprint 4.15"
        )
        assert maturity[FLAG] == "pilot"
