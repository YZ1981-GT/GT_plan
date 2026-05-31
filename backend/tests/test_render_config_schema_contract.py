"""render-config / prefill-context 的 schema 契约回归测试。

背景：render-config 与 prefill-context 端点历史上 SELECT 了 projects 表不存在的列
（template_version_id / year）以及 materiality.materiality_level / users.display_name。
在 PostgreSQL 中，首条 UndefinedColumn 语句会让整个事务进入 aborted 状态，
后续查询全部失败 → 对所有底稿/项目普适 500（wp-ai-review-ux-fix task 8 记录的总闸 bug）。

本测试用静态源码契约锁定这些错误查询不再复发（SQLite 无法复现 PG 事务 aborted
语义，故采用源码级契约而非运行时断言）。
"""

from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
_RENDER_CONFIG = _BACKEND / "app" / "routers" / "wp_render_config.py"
_PREFILL_CTX = _BACKEND / "app" / "routers" / "wp_prefill_context.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class TestProjectsColumnContract:
    """projects 表无 year / template_version_id 列，禁止直接 SELECT 它们。"""

    def test_render_config_no_projects_template_version_id(self):
        src = _src(_RENDER_CONFIG)
        assert "template_version_id FROM projects" not in src, (
            "projects 表无 template_version_id 列；该查询会使 PG 事务 aborted 致普适 500"
        )

    def test_render_config_no_select_year_from_projects(self):
        src = _src(_RENDER_CONFIG)
        assert "SELECT year FROM projects" not in src, (
            "projects 表无 year 列；年度须用 EXTRACT(YEAR FROM audit_period_end)"
        )

    def test_prefill_context_no_select_year_from_projects(self):
        src = _src(_PREFILL_CTX)
        # 允许 EXTRACT(YEAR FROM audit_period_end) AS year，但不得裸 SELECT name, year
        assert "name, year," not in src, (
            "projects 表无 year 列；年度须用 EXTRACT(YEAR FROM audit_period_end)"
        )

    def test_prefill_context_no_materiality_level_column(self):
        src = _src(_PREFILL_CTX)
        assert "SELECT materiality_level" not in src, (
            "materiality 表列名为 overall_materiality，非 materiality_level"
        )

    def test_prefill_context_no_users_display_name(self):
        src = _src(_PREFILL_CTX)
        assert "u.display_name" not in src, (
            "users 表无 display_name 列；项目人员姓名在 staff_members.name"
        )

    def test_prefill_context_no_assignment_user_id_join(self):
        src = _src(_PREFILL_CTX)
        assert "u.id = pa.user_id" not in src, (
            "project_assignments 无 user_id 列；应 JOIN staff_members ON id = pa.staff_id"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
