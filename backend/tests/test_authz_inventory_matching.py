# Feature: partner-manager-edit-permission, Property 18: 前端调用匹配取字面段最多者
"""前端调用与后端端点的匹配性质测试。

**Validates: Requirements 1.3**

固定样例覆盖：
- 插值段（``${...}``）对应任一后端段
- ``{x:path}`` 对一段及以上
- 并列歧义
- 附加或改变查询串不影响匹配结果
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 把 backend/scripts/gen 放到 sys.path，以便导入 authz_inventory 包
_SCRIPTS_GEN = str(Path(__file__).resolve().parents[1] / "scripts" / "gen")
if _SCRIPTS_GEN not in sys.path:
    sys.path.insert(0, _SCRIPTS_GEN)

sys.dont_write_bytecode = True

from authz_inventory.frontend import MatchResult, match_call  # noqa: E402

# ─── 后端端点样本（模拟真实端点结构）─────────────────────────────────────────


# 注意：后端路径里的 {project_id}、{year}、{note_section}、{note_id} 都是普通路径参数，
# 只有 {x:path} 才匹配一段及以上。
SAMPLE_ENDPOINTS: list[tuple[str, str]] = [
    # 附注 CRUD
    ("POST", "/api/disclosure-notes/generate"),
    ("PUT", "/api/disclosure-notes/{note_id}"),
    ("DELETE", "/api/disclosure-notes/{project_id}/{year}/sections/{note_section}"),
    ("PATCH", "/api/disclosure-notes/{project_id}/{year}/sections/{note_section}"),
    ("PATCH", "/api/disclosure-notes/{project_id}/{year}/restore/{note_id}"),
    # 附注操作
    ("POST", "/api/disclosure-notes/{project_id}/{year}/pull-from-workpapers"),
    ("POST", "/api/disclosure-notes/{project_id}/{year}/validate"),
    ("PUT", "/api/disclosure-notes/findings/{validation_id}/confirm"),
    # 公式
    ("POST", "/api/disclosure-notes/{project_id}/{year}/{note_section}/clear-formulas"),
    ("POST", "/api/disclosure-notes/{project_id}/{year}/{note_section}/restore-auto"),
    ("POST", "/api/disclosure-notes/{project_id}/{year}/{note_section}/apply-formulas"),
    ("PUT", "/api/disclosure-notes/{project_id}/{year}/{note_section}/formulas"),
    # 内容模板
    ("POST", "/api/projects/{project_id}/note-content-templates/snapshot-preview"),
    ("POST", "/api/projects/{project_id}/note-content-templates"),
    ("DELETE", "/api/projects/{project_id}/note-content-templates/{template_id}"),
    # 批量导入
    ("POST", "/api/projects/{project_id}/disclosure-note-import/parse-upload"),
    ("POST", "/api/projects/{project_id}/disclosure-note-import/parse-knowledge"),
    ("POST", "/api/projects/{project_id}/disclosure-note-text-batch/preview"),
    ("POST", "/api/projects/{project_id}/disclosure-note-text-batch/apply"),
    # {x:path} 示例（模拟通用资源端点）
    ("GET", "/api/resources/{resource_path:path}"),
    ("DELETE", "/api/resources/{resource_path:path}"),
    # 会产生歧义的一对端点：同方法、同段数、字面段一样多
    ("POST", "/api/projects/{project_id}/actions/sync"),
    ("POST", "/api/projects/{project_id}/actions/push"),
]


# ─── 固定样例测试 ────────────────────────────────────────────────────────────


class TestInterpolationSegment:
    """插值段（``${...}``）匹配后端路径的任一段。"""

    def test_single_interpolation_matches_param(self) -> None:
        """前端 `${projectId}` 对应后端 `{project_id}`。"""
        result = match_call(
            "POST",
            "/api/disclosure-notes/${projectId}/${year}/pull-from-workpapers",
            SAMPLE_ENDPOINTS,
        )
        assert result.matches == ("/api/disclosure-notes/{project_id}/{year}/pull-from-workpapers",)
        assert not result.ambiguous

    def test_multiple_interpolations(self) -> None:
        """多个插值段各自对应一个后端参数段。"""
        result = match_call(
            "DELETE",
            "/api/disclosure-notes/${pid}/${yr}/sections/${sec}",
            SAMPLE_ENDPOINTS,
        )
        assert result.matches == ("/api/disclosure-notes/{project_id}/{year}/sections/{note_section}",)
        assert not result.ambiguous
        # 字面段：api, disclosure-notes, sections = 3
        assert result.literal_segments == 3

    def test_interpolation_matches_literal_segment(self) -> None:
        """插值段也能对应后端的字面段（但字面段计数不计入）。"""
        # 前端 ${action} 对应后端 sync / push
        result = match_call(
            "POST",
            "/api/projects/${pid}/actions/${action}",
            SAMPLE_ENDPOINTS,
        )
        # 两个端点都匹配：actions/sync 和 actions/push
        assert len(result.matches) == 2
        assert "/api/projects/{project_id}/actions/sync" in result.matches
        assert "/api/projects/{project_id}/actions/push" in result.matches
        assert result.ambiguous


class TestPathParamMultiSegment:
    """`{x:path}` 匹配一段及以上。"""

    def test_path_param_one_segment(self) -> None:
        """{x:path} 可以只匹配一段。"""
        result = match_call(
            "GET",
            "/api/resources/document.pdf",
            SAMPLE_ENDPOINTS,
        )
        assert result.matches == ("/api/resources/{resource_path:path}",)
        assert not result.ambiguous

    def test_path_param_multiple_segments(self) -> None:
        """{x:path} 匹配多段。"""
        result = match_call(
            "GET",
            "/api/resources/projects/abc/files/readme.md",
            SAMPLE_ENDPOINTS,
        )
        assert result.matches == ("/api/resources/{resource_path:path}",)
        assert not result.ambiguous
        # 字面段：api, resources = 2
        assert result.literal_segments == 2

    def test_path_param_method_must_match(self) -> None:
        """方法不同不匹配。"""
        result = match_call(
            "POST",
            "/api/resources/any/path",
            SAMPLE_ENDPOINTS,
        )
        assert result.matches == ()


class TestAmbiguousMatch:
    """并列歧义：字面段数相同的多个命中全部列出。"""

    def test_tied_literal_count_marks_ambiguous(self) -> None:
        """两个端点段数相同、字面段相同数目 → 标歧义。"""
        result = match_call(
            "POST",
            "/api/projects/${pid}/actions/${action}",
            SAMPLE_ENDPOINTS,
        )
        assert result.ambiguous
        assert len(result.matches) >= 2

    def test_more_literal_segments_wins(self) -> None:
        """字面段更多的唯一命中不标歧义。"""
        # clear-formulas 的字面段比 validate 多（多了 note_section 后面那一段字面量 clear-formulas）
        result = match_call(
            "POST",
            "/api/disclosure-notes/${pid}/${yr}/${sec}/clear-formulas",
            SAMPLE_ENDPOINTS,
        )
        assert result.matches == (
            "/api/disclosure-notes/{project_id}/{year}/{note_section}/clear-formulas",
        )
        assert not result.ambiguous
        # 字面段：api, disclosure-notes, clear-formulas = 3
        assert result.literal_segments == 3


class TestQueryStringIgnored:
    """附加或改变查询串不影响匹配结果。"""

    def test_no_query_string(self) -> None:
        """不带查询串的基线。"""
        result_base = match_call(
            "POST",
            "/api/disclosure-notes/generate",
            SAMPLE_ENDPOINTS,
        )
        assert result_base.matches == ("/api/disclosure-notes/generate",)
        assert not result_base.ambiguous

    def test_adding_query_string(self) -> None:
        """附加查询串不改变匹配。"""
        result_qs = match_call(
            "POST",
            "/api/disclosure-notes/generate?force=true&version=2",
            SAMPLE_ENDPOINTS,
        )
        assert result_qs.matches == ("/api/disclosure-notes/generate",)
        assert not result_qs.ambiguous

    def test_different_query_strings_same_match(self) -> None:
        """改变查询串内容不影响匹配结果。"""
        result_a = match_call(
            "POST",
            "/api/disclosure-notes/generate?a=1",
            SAMPLE_ENDPOINTS,
        )
        result_b = match_call(
            "POST",
            "/api/disclosure-notes/generate?b=2&c=3",
            SAMPLE_ENDPOINTS,
        )
        assert result_a.matches == result_b.matches
        assert result_a.literal_segments == result_b.literal_segments
        assert result_a.ambiguous == result_b.ambiguous

    def test_query_string_on_interpolated_path(self) -> None:
        """带插值段的路径同样忽略查询串。"""
        result_no_qs = match_call(
            "PUT",
            "/api/disclosure-notes/${noteId}",
            SAMPLE_ENDPOINTS,
        )
        result_with_qs = match_call(
            "PUT",
            "/api/disclosure-notes/${noteId}?_t=123",
            SAMPLE_ENDPOINTS,
        )
        assert result_no_qs.matches == result_with_qs.matches
        assert result_no_qs.matches == ("/api/disclosure-notes/{note_id}",)


class TestNoMatch:
    """无匹配的情况。"""

    def test_nonexistent_path(self) -> None:
        result = match_call(
            "POST",
            "/api/does-not-exist/foo",
            SAMPLE_ENDPOINTS,
        )
        assert result.matches == ()
        assert not result.ambiguous
        assert result.literal_segments == 0

    def test_wrong_method(self) -> None:
        """路径存在但方法不同。"""
        result = match_call(
            "GET",
            "/api/disclosure-notes/generate",
            SAMPLE_ENDPOINTS,
        )
        assert result.matches == ()

    def test_segment_count_mismatch(self) -> None:
        """段数不同不匹配（非 {x:path} 端点）。"""
        result = match_call(
            "POST",
            "/api/disclosure-notes/generate/extra",
            SAMPLE_ENDPOINTS,
        )
        assert result.matches == ()


class TestLiteralSegmentCounting:
    """字面段计数准确性。"""

    def test_all_literal_path(self) -> None:
        """完全字面路径的字面段数 = 路径段数。"""
        result = match_call(
            "POST",
            "/api/disclosure-notes/generate",
            SAMPLE_ENDPOINTS,
        )
        # api, disclosure-notes, generate = 3
        assert result.literal_segments == 3

    def test_mixed_literal_and_interpolation(self) -> None:
        """混合路径的字面段数只计两侧均为字面量的段。"""
        result = match_call(
            "POST",
            "/api/projects/${pid}/note-content-templates/snapshot-preview",
            SAMPLE_ENDPOINTS,
        )
        # api, projects, note-content-templates, snapshot-preview = 4（${pid} 对 {project_id} 不计）
        assert result.literal_segments == 4
        assert result.matches == ("/api/projects/{project_id}/note-content-templates/snapshot-preview",)

    def test_best_wins_among_multiple_candidates(self) -> None:
        """多候选里字面段最多者胜出。"""
        # 构造一组端点：同方法同段数，但字面段数不同
        endpoints = [
            ("POST", "/api/items/{id}/status"),      # 字面段：api, items, status = 3
            ("POST", "/api/{group}/{id}/{action}"),   # 字面段：api = 1
        ]
        result = match_call(
            "POST",
            "/api/items/${itemId}/status",
            endpoints,
        )
        assert result.matches == ("/api/items/{id}/status",)
        assert result.literal_segments == 3
        assert not result.ambiguous
