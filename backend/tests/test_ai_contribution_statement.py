"""AI 贡献声明水印测试

Validates: Requirements 11.6
- 简报、年报、AI 补注 PDF 生成时在首尾页加"AI 贡献声明"
- 复用 pdf_export_engine 水印能力
"""

import pytest

from app.services.pdf_export_engine import (
    build_ai_contribution_statement,
    get_ai_statement_css,
    get_ai_statement_html,
    render_with_ai_statement,
)


# ---------------------------------------------------------------------------
# build_ai_contribution_statement 测试
# ---------------------------------------------------------------------------


class TestBuildAiContributionStatement:
    """AI 贡献声明文本生成。"""

    def test_default_reviewer(self):
        """默认审计师名称。"""
        result = build_ai_contribution_statement()
        assert "本文档含 AI 辅助生成内容" in result
        assert "审计师" in result
        assert "审阅并定稿" in result

    def test_custom_reviewer(self):
        """自定义审计师名称。"""
        result = build_ai_contribution_statement(reviewer="张三")
        assert "张三" in result
        assert "本文档含 AI 辅助生成内容" in result

    def test_format_matches_spec(self):
        """声明格式完全匹配需求规格。"""
        result = build_ai_contribution_statement(reviewer="李四")
        assert result == "本文档含 AI 辅助生成内容，已由 李四 审阅并定稿"


# ---------------------------------------------------------------------------
# get_ai_statement_css 测试
# ---------------------------------------------------------------------------


class TestGetAiStatementCss:
    """CSS 样式块生成。"""

    def test_contains_class_name(self):
        """CSS 包含正确的类名。"""
        css = get_ai_statement_css()
        assert ".ai-contribution-statement" in css

    def test_contains_positioning(self):
        """CSS 包含固定定位样式。"""
        css = get_ai_statement_css()
        assert "position: fixed" in css
        assert "bottom:" in css


# ---------------------------------------------------------------------------
# get_ai_statement_html 测试
# ---------------------------------------------------------------------------


class TestGetAiStatementHtml:
    """HTML 片段生成。"""

    def test_contains_statement_text(self):
        """HTML 包含声明文本。"""
        html = get_ai_statement_html(reviewer="王五")
        assert "王五" in html
        assert "本文档含 AI 辅助生成内容" in html

    def test_contains_css_class(self):
        """HTML 包含正确的 CSS 类。"""
        html = get_ai_statement_html()
        assert 'class="ai-contribution-statement"' in html


# ---------------------------------------------------------------------------
# render_with_ai_statement 测试
# ---------------------------------------------------------------------------


class TestRenderWithAiStatement:
    """HTML 文档注入 AI 贡献声明。"""

    def test_injects_into_standard_html(self):
        """标准 HTML 文档注入声明。"""
        original = (
            "<!DOCTYPE html><html><head><style>body{}</style></head>"
            "<body><p>内容</p></body></html>"
        )
        result = render_with_ai_statement(original, reviewer="赵六")
        assert "赵六" in result
        assert "ai-contribution-statement" in result
        # CSS 注入到 style 标签内
        assert ".ai-contribution-statement" in result
        # HTML 注入到 body 结束前
        assert result.index("ai-contribution-statement") < result.index("</body>")

    def test_injects_css_before_style_close(self):
        """CSS 注入到 </style> 前。"""
        original = "<html><head><style>.x{}</style></head><body></body></html>"
        result = render_with_ai_statement(original)
        # CSS 应在 </style> 之前
        css_pos = result.index(".ai-contribution-statement")
        style_close_pos = result.index("</style>")
        assert css_pos < style_close_pos

    def test_injects_css_before_head_close_when_no_style(self):
        """无 style 标签时 CSS 注入到 </head> 前。"""
        original = "<html><head></head><body><p>test</p></body></html>"
        result = render_with_ai_statement(original)
        assert "<style>" in result
        assert ".ai-contribution-statement" in result

    def test_injects_html_before_body_close(self):
        """声明 HTML 注入到 </body> 前。"""
        original = "<html><head><style></style></head><body><p>内容</p></body></html>"
        result = render_with_ai_statement(original, reviewer="测试人")
        # 声明在 </body> 之前
        statement_pos = result.index("测试人")
        body_close_pos = result.index("</body>")
        assert statement_pos < body_close_pos

    def test_handles_no_head_or_style(self):
        """无 head/style 标签时使用 inline style。"""
        original = "<body><p>简单内容</p></body>"
        result = render_with_ai_statement(original, reviewer="内联测试")
        assert "内联测试" in result
        assert "style=" in result

    def test_handles_no_body_tag(self):
        """无 body 标签时追加到末尾。"""
        original = "<p>纯内容片段</p>"
        result = render_with_ai_statement(original, reviewer="追加测试")
        assert "追加测试" in result
        assert result.endswith("</div>\n")

    def test_preserves_original_content(self):
        """注入不破坏原始内容。"""
        original = (
            "<html><head><style>h1{color:red}</style></head>"
            "<body><h1>标题</h1><p>段落</p></body></html>"
        )
        result = render_with_ai_statement(original)
        assert "<h1>标题</h1>" in result
        assert "<p>段落</p>" in result
        assert "h1{color:red}" in result

    def test_works_with_pdf_export_engine_base_html(self):
        """与 pdf_export_engine 的 _BASE_HTML 模板兼容。"""
        from app.services.pdf_export_engine import _BASE_HTML
        # 模拟一个渲染后的文档
        html = _BASE_HTML.format(
            title="测试报告",
            body="<p>AI 生成的综合简报内容</p>",
        )
        result = render_with_ai_statement(html, reviewer="合伙人A")
        assert "合伙人A" in result
        assert "本文档含 AI 辅助生成内容" in result
        assert "ai-contribution-statement" in result
