# -*- coding: utf-8 -*-
"""check_tb_writeback_no_direct_call.py 单元测试。

spec: tb-writeback-explicit-publish-gate Task 18 / Req 9.1, 9.2。

验证守卫「真能拦、不误报」：
- 活代码 `.put/.post(...trial-balance/writeback...)` 被检出（legacy）
- 活代码 `.post(.../trial_balance)` G6 变体端点被检出（variant）
- **收口注释**里的字面量不被误报（先剥注释）
- **测试断言字符串**里的字面量不被误报（排除测试文件）
- `trial_balance.updated` 事件名 / `table: 'trial_balance'` 值不被误报
- 全 clean 仓库 exit 0；含违规 exit 1
"""

import sys
from pathlib import Path

import pytest

# 确保 scripts/check 可 import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "check"))

import check_tb_writeback_no_direct_call as guard  # noqa: E402


# ─── strip_comments ──────────────────────────────────────────────────────────

class TestStripComments:
    def test_line_comment_stripped_string_kept(self):
        src = "const x = 1 // trial-balance/writeback\nawait api.put('/x/trial-balance/writeback')\n"
        out = guard.strip_comments(src)
        # 注释里的字面量被剥（替换为空格），字符串里的保留
        assert "// trial-balance/writeback" not in out
        assert "'/x/trial-balance/writeback'" in out

    def test_block_comment_stripped(self):
        src = "/* api.put('/x/trial-balance/writeback') */\nconst y = 2\n"
        out = guard.strip_comments(src)
        assert "api.put" not in out
        assert "const y = 2" in out

    def test_jsdoc_star_comment_stripped(self):
        # 复刻 useE1Adjudication.ts 收口注释形态
        src = "  /**\n   * 里**自动** `api.put('/projects/{pid}/trial-balance/writeback')` 三科目\n   */\n"
        out = guard.strip_comments(src)
        assert "api.put" not in out

    def test_vue_html_comment_stripped(self):
        src = "<!-- api.post('/api/projects/x/trial_balance') -->\n<div/>\n"
        out = guard.strip_comments(src)
        assert "api.post" not in out
        assert "<div/>" in out

    def test_line_numbers_preserved(self):
        src = "a\n// c\nawait api.put('/x/trial-balance/writeback')\n"
        out = guard.strip_comments(src)
        # 第 3 行仍是调用行
        assert out.splitlines()[2].strip().startswith("await api.put")


# ─── _is_test_file ───────────────────────────────────────────────────────────

class TestIsTestFile:
    def test_tests_dir(self):
        assert guard._is_test_file(Path("a/__tests__/x.ts")) is True

    def test_spec_suffix(self):
        assert guard._is_test_file(Path("a/foo.spec.ts")) is True

    def test_test_suffix(self):
        assert guard._is_test_file(Path("a/foo.test.ts")) is True

    def test_stories(self):
        assert guard._is_test_file(Path("a/Foo.stories.ts")) is True

    def test_normal_source(self):
        assert guard._is_test_file(Path("a/composables/useX.ts")) is False


# ─── scan_file ───────────────────────────────────────────────────────────────

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


class TestScanFile:
    def test_live_legacy_put_detected(self, tmp_path):
        p = _write(tmp_path, "useX.ts",
                   "async function w(pid){ await api.put(`/api/projects/${pid}/trial-balance/writeback`, {}) }\n")
        hits = guard.scan_file(p)
        assert len(hits) == 1
        assert hits[0]["kind"] == "legacy"

    def test_live_legacy_post_detected(self, tmp_path):
        p = _write(tmp_path, "useX.ts",
                   "api.post('/api/projects/p1/trial-balance/writeback', { items: [] })\n")
        hits = guard.scan_file(p)
        assert [h["kind"] for h in hits] == ["legacy"]

    def test_variant_post_detected(self, tmp_path):
        p = _write(tmp_path, "useG6.ts",
                   "await api.post(`/api/projects/${pid}/trial_balance`, { rows })\n")
        hits = guard.scan_file(p)
        assert [h["kind"] for h in hits] == ["variant"]

    def test_closure_comment_not_flagged(self, tmp_path):
        # 收口注释形态：字面量在注释里，无活调用
        p = _write(tmp_path, "useX.ts",
                   "// 此前直调旧端点 api.put('/projects/{pid}/trial-balance/writeback')（已移除）\n"
                   "function w(){ return 1 }\n")
        assert guard.scan_file(p) == []

    def test_jsdoc_closure_comment_not_flagged(self, tmp_path):
        p = _write(tmp_path, "useE1.ts",
                   "  /**\n"
                   "   * 里**自动** `api.put('/projects/{pid}/trial-balance/writeback')` 三科目直写。\n"
                   "   */\n"
                   "  function syncOnly(){ /* no-op */ }\n")
        assert guard.scan_file(p) == []

    def test_trial_balance_updated_event_not_flagged(self, tmp_path):
        # SSE 事件名，非端点调用
        p = _write(tmp_path, "sse.ts",
                   "conn._emit('trial_balance.updated', {})\nbus.on('trial_balance.updated', fn)\n")
        assert guard.scan_file(p) == []

    def test_trial_balance_table_value_not_flagged(self, tmp_path):
        # 查询 DSL 的 table 值，非端点调用
        p = _write(tmp_path, "q.ts",
                   "dsl.table = 'trial_balance'\napi.post('/api/custom-query/execute', { table: 'trial_balance' })\n")
        assert guard.scan_file(p) == []

    def test_freeze_endpoint_not_flagged(self, tmp_path):
        # 合法的 trial-balance 子端点（freeze），非 writeback
        p = _write(tmp_path, "tb.ts",
                   "await api.put(`/api/projects/${pid}/trial-balance/freeze`, { is_frozen: true })\n")
        assert guard.scan_file(p) == []

    def test_publish_to_tb_not_flagged(self, tmp_path):
        # 正解端点：显式发布门
        p = _write(tmp_path, "useX.ts",
                   "await api.post(`/api/workpapers/${wpId}/audit-determination/publish-to-tb`, body)\n")
        assert guard.scan_file(p) == []

    def test_both_kinds_in_one_file(self, tmp_path):
        p = _write(tmp_path, "useX.ts",
                   "api.put('/api/projects/p/trial-balance/writeback', {})\n"
                   "api.post('/api/projects/p/trial_balance', {})\n")
        kinds = sorted(h["kind"] for h in guard.scan_file(p))
        assert kinds == ["legacy", "variant"]


# ─── iter_source_files + main（monkeypatch 模块级路径）───────────────────────

class TestMainIntegration:
    def test_clean_repo_exits_0(self, tmp_path, monkeypatch, capsys):
        src = tmp_path / "audit-platform" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "useOk.ts").write_text(
            "await api.post(`/api/workpapers/${wpId}/audit-determination/publish-to-tb`, {})\n",
            encoding="utf-8",
        )
        # 收口注释 + 测试文件均不应触发
        (src / "useClosure.ts").write_text(
            "// 此前 api.put('/projects/x/trial-balance/writeback') 已移除\nfunction f(){}\n",
            encoding="utf-8",
        )
        tdir = src / "__tests__"
        tdir.mkdir()
        (tdir / "x.spec.ts").write_text(
            "expect(url).not.toContain('trial-balance/writeback')\n", encoding="utf-8",
        )
        monkeypatch.setattr(guard, "_REPO", tmp_path)
        monkeypatch.setattr(guard, "FRONTEND_SRC", src)
        rc = guard.main([])
        assert rc == 0

    def test_violation_exits_1(self, tmp_path, monkeypatch):
        src = tmp_path / "audit-platform" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "useBad.ts").write_text(
            "await api.put(`/api/projects/${pid}/trial-balance/writeback`, {})\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(guard, "_REPO", tmp_path)
        monkeypatch.setattr(guard, "FRONTEND_SRC", src)
        rc = guard.main([])
        assert rc == 1

    def test_test_files_excluded_from_scan(self, tmp_path, monkeypatch):
        src = tmp_path / "audit-platform" / "frontend" / "src"
        (src / "__tests__").mkdir(parents=True)
        # 只有测试文件含字面量 → 不算违规
        (src / "__tests__" / "y.test.ts").write_text(
            "api.put('/api/projects/p/trial-balance/writeback', {})\n", encoding="utf-8",
        )
        monkeypatch.setattr(guard, "_REPO", tmp_path)
        monkeypatch.setattr(guard, "FRONTEND_SRC", src)
        assert guard.main([]) == 0

    def test_missing_src_dir_fails_closed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(guard, "FRONTEND_SRC", tmp_path / "nope")
        with pytest.raises(RuntimeError):
            guard.iter_source_files()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
