"""wp_template_finder：D4 多文件前缀防碰撞 + 审定表主模板优先。"""

from __future__ import annotations

from app.services import wp_template_finder as finder


def setup_function() -> None:
    finder._index_cache = None


def test_d4_primary_prefers_adjudication_workbook() -> None:
    path = finder.find_template_file("D4")
    assert path is not None
    assert "审定表" in path.name
    assert path.name.startswith("D4-1")
    assert "D4-12" not in path.name


def test_d4_1_does_not_resolve_to_d4_12() -> None:
    path = finder.find_template_file("D4-1")
    assert path is not None
    assert "D4-1" in path.name and "至" in path.name
    assert "合同" not in path.name


def test_d4_2_does_not_resolve_to_d4_21() -> None:
    path = finder.find_template_file("D4-2")
    assert path is not None
    assert "D4-1" in path.name and "至" in path.name


def test_d4a_falls_back_to_adjudication_workbook() -> None:
    path = finder.find_template_file("D4A")
    assert path is not None
    assert "审定表" in path.name


def test_d4_12_resolves_to_contract_check() -> None:
    path = finder.find_template_file("D4-12")
    assert path is not None
    assert path.name.startswith("D4-12")


def test_wp_code_prefix_no_collision() -> None:
    assert finder._wp_code_filename_prefix_ok("D4-1至D4-4 foo.xlsx", "D4-1")
    assert not finder._wp_code_filename_prefix_ok("D4-12 合同.xlsx", "D4-1")
    assert not finder._wp_code_filename_prefix_ok("D4-21关联.xlsx", "D4-2")


def test_whole_excel_d4_income_pack() -> None:
    path = finder.find_whole_workbook_template("D4")
    assert path is not None
    assert path.name == "D4收入底稿.xlsx"
    assert finder._is_whole_excel_template_name(path.name)
    assert not finder._is_whole_excel_template_name(
        "D4-1至D4-4 营业收入 - 审定表明细表.xlsx"
    )


def test_whole_excel_f2_inventory_pack() -> None:
    path = finder.find_whole_workbook_template("F2")
    assert path is not None
    assert path.name == "F2存货.xlsx"
    assert finder._is_whole_excel_template_name(path.name)
    # 拆分包文件名含「存货」字样，但不是专用合并短名
    assert not finder._is_whole_excel_template_name(
        "F2-1至F2-14 存货实质性程序-审定表明细表类.xlsx"
    )
    # 合并本不得进入普通 all_template_files
    assert all(p.name != "F2存货.xlsx" for p in finder.find_all_template_files("F2"))


def test_f2a_falls_back_to_adjudication_workbook() -> None:
    path = finder.find_template_file("F2A")
    assert path is not None
    assert path.name.startswith("F2-1")
    assert "至" in path.name


def test_f2_16_resolves_to_policy_workbook() -> None:
    path = finder.find_template_file("F2-16")
    assert path is not None
    assert path.name.startswith("F2-16")


def test_f2_2_does_not_resolve_to_f2_29_check_pack() -> None:
    """F2-2 明细汇总必须落在审定明细表类，不得误绑检查类 F2-29～F2-35。"""
    path = finder.find_template_file("F2-2")
    assert path is not None
    assert "F2-1" in path.name and "至" in path.name
    assert "F2-29" not in path.name
    assert "检查" not in path.name
    assert finder._wp_code_filename_prefix_ok("F2-29至F2-35 检查.xlsx", "F2-2") is False
    assert finder._wp_code_filename_prefix_ok("F2-21至F2-26 盘点.xlsx", "F2-2") is False


def test_f2_22_onlyoffice_prefers_g2_6_2_docx() -> None:
    """F2-22 在线编辑挂载 G2-6-2 存货监盘计划（Word），而非盘点包内近空 sheet。"""
    path = finder.find_template_file_any("F2-22")
    assert path is not None
    assert path.suffix.lower() == ".docx"
    assert path.name.startswith("F2-22")
    assert "监盘计划" in path.name


def test_f2_23_onlyoffice_prefers_g2_6_1_docx() -> None:
    """F2-23 在线编辑挂载 G2-6-1 存货监盘小结（Word）。"""
    path = finder.find_template_file_any("F2-23")
    assert path is not None
    assert path.suffix.lower() == ".docx"
    assert path.name.startswith("F2-23")
    assert "监盘小结" in path.name
