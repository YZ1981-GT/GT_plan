"""Grammar 源完整性测试 — Req-2

校验:
- 路径正确指向 backend/data/acnr/grammar_v1.json
- _validate_grammar 检测缺失项
- validate_grammar_on_startup 对非法输入 fail-fast
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


# ─── 路径正确性 ───────────────────────────────────────────────────────────────

class TestGrammarFilePath:
    """Req-2.1: 路径 SHALL 正确指向 backend/data/acnr/grammar_v1.json"""

    def test_grammar_file_exists(self):
        """grammar_v1.json 文件应存在于正确路径"""
        from app.services.acnr.grammar import _GRAMMAR_FILE

        assert _GRAMMAR_FILE.exists(), (
            f"grammar_v1.json 不存在: {_GRAMMAR_FILE}"
        )

    def test_grammar_file_path_points_to_backend_data(self):
        """路径应在 backend/data/acnr/ 下"""
        from app.services.acnr.grammar import _GRAMMAR_FILE

        resolved = _GRAMMAR_FILE.resolve()
        # 路径应包含 backend/data/acnr/grammar_v1.json
        parts = resolved.parts
        # 找到 "backend" 后面应紧跟 "data", "acnr", "grammar_v1.json"
        try:
            idx = list(parts).index("backend")
        except ValueError:
            pytest.fail(f"路径中不含 'backend': {resolved}")

        tail = parts[idx:]
        assert tail == ("backend", "data", "acnr", "grammar_v1.json"), (
            f"路径末端不符合预期: {tail}"
        )

    def test_grammar_file_is_valid_json(self):
        """文件内容应为合法 JSON"""
        from app.services.acnr.grammar import _GRAMMAR_FILE

        with open(_GRAMMAR_FILE, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)


# ─── _validate_grammar 校验逻辑 ──────────────────────────────────────────────

class TestValidateGrammar:
    """Req-2.3, Req-2.4: 校验 5 域/11ns/STANDARD_WP_CODE_RE/registry_version"""

    def test_valid_grammar_passes(self):
        """完整的 grammar_v1.json 应通过校验"""
        from app.services.acnr.grammar import _GRAMMAR_FILE, _validate_grammar

        with open(_GRAMMAR_FILE, encoding="utf-8") as f:
            data = json.load(f)

        missing = _validate_grammar(data)
        assert missing == [], f"校验不应失败: {missing}"

    def test_missing_version(self):
        """缺少 version → 报告 registry_version 缺失"""
        from app.services.acnr.grammar import _validate_grammar

        data = {
            "uri_profiles": {f"d{i}": {} for i in range(5)},
            "index_namespaces": {f"ns{i}": {} for i in range(11)},
            "constants": {"STANDARD_WP_CODE_RE": "^[A-S]\\d"},
        }
        missing = _validate_grammar(data)
        assert any("version" in m for m in missing)

    def test_insufficient_domains(self):
        """域定义 <5 → 报告不足"""
        from app.services.acnr.grammar import _validate_grammar

        data = {
            "version": "1",
            "uri_profiles": {"wp": {}, "tb": {}},  # 只有 2 个
            "index_namespaces": {f"ns{i}": {} for i in range(11)},
            "constants": {"STANDARD_WP_CODE_RE": "^[A-S]\\d"},
        }
        missing = _validate_grammar(data)
        assert any("uri_profiles" in m for m in missing)

    def test_insufficient_namespaces(self):
        """命名空间 <11 → 报告不足"""
        from app.services.acnr.grammar import _validate_grammar

        data = {
            "version": "1",
            "uri_profiles": {f"d{i}": {} for i in range(5)},
            "index_namespaces": {"wp": {}, "cell": {}},  # 只有 2 个
            "constants": {"STANDARD_WP_CODE_RE": "^[A-S]\\d"},
        }
        missing = _validate_grammar(data)
        assert any("index_namespaces" in m for m in missing)

    def test_missing_standard_wp_code_re(self):
        """缺少 STANDARD_WP_CODE_RE → 报告缺失"""
        from app.services.acnr.grammar import _validate_grammar

        data = {
            "version": "1",
            "uri_profiles": {f"d{i}": {} for i in range(5)},
            "index_namespaces": {f"ns{i}": {} for i in range(11)},
            "constants": {},
        }
        missing = _validate_grammar(data)
        assert any("STANDARD_WP_CODE_RE" in m for m in missing)

    def test_empty_data_reports_all_missing(self):
        """空数据应报告所有缺失项"""
        from app.services.acnr.grammar import _validate_grammar

        missing = _validate_grammar({})
        assert len(missing) == 4, f"应报告 4 项缺失, 实际: {missing}"


# ─── validate_grammar_on_startup fail-fast ────────────────────────────────────

class TestValidateGrammarOnStartup:
    """Req-2.2, Req-2.4: 启动时文件异常或校验失败 → sys.exit(1)"""

    def test_file_not_exists_exits(self, tmp_path):
        """文件不存在 → sys.exit(1)"""
        fake_path = tmp_path / "nonexistent.json"
        with patch(
            "app.services.acnr.grammar._GRAMMAR_FILE", fake_path
        ), pytest.raises(SystemExit) as exc_info:
            from app.services.acnr.grammar import validate_grammar_on_startup
            validate_grammar_on_startup()
        assert exc_info.value.code == 1

    def test_invalid_json_exits(self, tmp_path):
        """JSON 解析失败 → sys.exit(1)"""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json {{{", encoding="utf-8")
        with patch(
            "app.services.acnr.grammar._GRAMMAR_FILE", bad_file
        ), pytest.raises(SystemExit) as exc_info:
            from app.services.acnr.grammar import validate_grammar_on_startup
            validate_grammar_on_startup()
        assert exc_info.value.code == 1

    def test_incomplete_grammar_exits(self, tmp_path):
        """校验项缺失 → sys.exit(1)"""
        incomplete_file = tmp_path / "incomplete.json"
        incomplete_file.write_text(
            json.dumps({"version": "1"}), encoding="utf-8"
        )
        with patch(
            "app.services.acnr.grammar._GRAMMAR_FILE", incomplete_file
        ), pytest.raises(SystemExit) as exc_info:
            from app.services.acnr.grammar import validate_grammar_on_startup
            validate_grammar_on_startup()
        assert exc_info.value.code == 1

    def test_valid_grammar_does_not_exit(self):
        """正确的 grammar_v1.json → 不 sys.exit"""
        from app.services.acnr.grammar import validate_grammar_on_startup

        # 应该不抛出 SystemExit
        validate_grammar_on_startup()


# ─── 模块级常量加载正确性 ─────────────────────────────────────────────────────

class TestModuleConstants:
    """验证模块成功加载后常量正确"""

    def test_standard_wp_code_re_is_compiled(self):
        """STANDARD_WP_CODE_RE 应为编译后的正则"""
        from app.services.acnr.grammar import STANDARD_WP_CODE_RE

        import re as re_mod

        assert isinstance(STANDARD_WP_CODE_RE, re_mod.Pattern)

    def test_standard_wp_code_re_matches_d2(self):
        """应匹配 D2 等标准底稿编码"""
        from app.services.acnr.grammar import STANDARD_WP_CODE_RE

        assert STANDARD_WP_CODE_RE.search("D2")
        assert STANDARD_WP_CODE_RE.search("K13")
        assert STANDARD_WP_CODE_RE.search("S3")

    def test_standard_wp_code_re_rejects_non_standard(self):
        """应拒绝非标准编码"""
        from app.services.acnr.grammar import STANDARD_WP_CODE_RE

        assert not STANDARD_WP_CODE_RE.search("Z1")
        assert not STANDARD_WP_CODE_RE.search("123")
