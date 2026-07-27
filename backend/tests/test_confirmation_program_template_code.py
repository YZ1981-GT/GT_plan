"""resolve_program_template_code 单测 — 程序表模板 key 父码优先（Property 22）

confirmation-hub-workbench-tabs Task 2.4：
- 循环前缀与父 wp_code 不一致时，先试 {wp_code}A（get_template 命中才采用），否则回退提取值
- 同循环场景逐字不变（零回归）
- 提取失败回退父 wp_code

实测约束（不猜）：
- get_template('F0A') 命中（tables 中存在）
- get_template('L0A') 未命中（tables 中不存在）
  → 故 ("函证程序表F0A","L0") 回退 F0A（L0A 无模板，保 xlsx/F0A 兜底，零回归）
"""
from app.routers.wp_render_strategies._a_program import resolve_program_template_code
from app.services.procedure_table_auto_service import get_template


class TestResolveProgramTemplateCode:
    def test_same_cycle_unchanged(self):
        """同循环 sheet：逐字返回提取值（D4A 不变）。"""
        assert resolve_program_template_code("销售与收款循环审计程序表D4A", "D4") == "D4A"

    def test_f0a_parent_is_f0_unchanged(self):
        """父码即 F0（F0A sheet 在 F0 下）：不变。"""
        assert resolve_program_template_code("函证程序表F0A", "F0") == "F0A"

    def test_l0_f0a_falls_back_when_no_l0a_template(self):
        """L0 内的「函证程序表F0A」：L0A 无模板 → 回退提取值 F0A（零回归）。

        实测 get_template('L0A') is None，故按 Property 22 回退原提取值，
        保持既有 xlsx / F0A 提取兜底不丢程序行。
        """
        assert get_template("L0A") is None  # 前提锁定
        assert resolve_program_template_code("函证程序表F0A", "L0") == "F0A"

    def test_parent_code_preferred_when_template_exists(self):
        """构造：父码 A 模板存在时优先采用父码。

        用真实存在的 F0A 验证「命中即采用」分支：sheet 名编码为其它循环 A、
        父 wp_code=F0（F0A 存在）→ 应返回 F0A。
        """
        # sheet 名带 D2A（D2 循环），父 wp_code=F0，F0A 模板存在 → 采用 F0A
        assert get_template("F0A") is not None  # 前提锁定
        assert resolve_program_template_code("某循环程序表D2A", "F0") == "F0A"

    def test_extraction_failure_falls_back_to_wp_code(self):
        """sheet 名无编码：回退父 wp_code。"""
        assert resolve_program_template_code("无编码的程序表", "F0") == "F0"

    def test_empty_sheet_name(self):
        """空 sheet 名：回退父 wp_code。"""
        assert resolve_program_template_code("", "L0") == "L0"
