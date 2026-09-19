"""底稿 xlsx 单元格操作子模块（pass4 拆分自 wp_template_init_service）

职责：prefill 预填充所依赖的 xlsx 单元格级 helper —— 公式列/类型提取、
坐标/公式判定、关键词列定位、数据行定位、预填充/用户公式样式标记、
语义行/数据列定位。

逐字搬运自 wp_template_init_service.py，行为零变更。主文件 import 这些 helper
供 prefill_workpaper_xlsx 调用，并 re-export 以保持导入路径不变。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _extract_tb_column(formula: str) -> str:
    """从 =TB('1122','期末余额') 提取列名"""
    import re
    m = re.search(r"'([^']+)'\s*\)$", formula)
    return m.group(1) if m else "期末余额"


def _extract_adj_type(formula: str) -> str:
    """从 =ADJ('1122','aje_net') 提取类型"""
    import re
    m = re.search(r"'(aje_net|rje_net)'", formula)
    return m.group(1) if m else "aje_net"


def _is_cell_coordinate(ref: str) -> bool:
    """判断 cell_ref 是否为实际单元格坐标（如 E8, AA12）"""
    import re
    return bool(re.match(r'^[A-Z]{1,3}\d{1,5}$', ref, re.IGNORECASE))


def _is_formula_cell(cell) -> bool:
    """E1 spec Task 1.1: 判断单元格是否含 Excel 公式

    用于 prefill 写入前检查 — 凡 cell.value 以 "=" 开头的均视为公式 cell,
    prefill 必须跳过避免覆盖（如 E1-2!B22 = SUM(B15:B21) 合计公式）。
    """
    val = getattr(cell, "value", None)
    if val is None:
        return False
    if not isinstance(val, str):
        return False
    return val.lstrip().startswith("=")


def _find_column_by_keyword(ws, keyword: str) -> int | None:
    """双维度策略：在前 10 行中查找包含关键词的列号

    致同模板标准结构：第 5-6 行是列头（期初数/未审数/账项调整/重分类调整/审定数）。
    找到关键词所在列后，数据写入该列的数据行。
    """
    col_keywords = {
        "期初余额": ["期初", "年初", "期初数", "年初数"],
        "未审数": ["未审", "未审数", "期末数"],
        "AJE调整": ["AJE", "账项调整", "审计调整"],
        "RJE调整": ["RJE", "重分类调整", "重分类"],
        "上年审定数": ["上年", "审定数"],
        # 子科目分项：在 A 列找科目名称行
        "库存现金_期初": ["库存现金", "现金"],
        "银行存款_期初": ["银行存款"],
        "其他货币资金_期初": ["其他货币资金"],
        "原材料_期初": ["原材料"],
        "在产品_期初": ["在产品"],
        "库存商品_期初": ["库存商品"],
        "工程物资_期初": ["工程物资"],
        "委托加工物资_期初": ["委托加工"],
        "存货跌价准备_期初": ["跌价准备"],
        "其他业务成本_期初": ["其他业务成本"],
        "累计折旧_期初": ["累计折旧"],
        "累计摊销_期初": ["累计摊销"],
        "折旧": ["折旧"],
        "薪酬": ["薪酬", "工资"],
        "摊销": ["摊销"],
    }
    # 也处理 _未审数 后缀（与 _期初 共享科目关键词）
    base_keyword = keyword.replace("_未审数", "_期初").replace("_期初", "_期初")
    terms = col_keywords.get(keyword) or col_keywords.get(base_keyword, [keyword])

    for row in ws.iter_rows(min_row=1, max_row=10, max_col=20):
        for cell in row:
            if cell.value and isinstance(cell.value, str):
                if any(t in cell.value for t in terms):
                    return cell.column
    return None


def _find_first_data_row(ws, col_idx: int) -> int | None:
    """找到指定列的第一个数据行（列头下方，跳过标题行）

    从第 7 行开始找（致同模板前 6 行通常是标题+列头），
    返回第一个空单元格或数字单元格的行号。
    """
    for row_num in range(7, 50):
        cell = ws.cell(row=row_num, column=col_idx)
        # 空单元格或已有数字（可覆盖）
        if cell.value is None or isinstance(cell.value, (int, float)):
            return row_num
        # 如果是公式（以=开头），也可以覆盖
        if isinstance(cell.value, str) and cell.value.startswith("="):
            return row_num
    return None


def _mark_prefilled_cell(ws, cell) -> None:
    """P2-1: 为预填充的单元格设置浅蓝色背景标记

    用户可通过背景色识别哪些单元格是系统自动填入的。
    同时在单元格 comment 中记录来源信息。
    """
    from openpyxl.styles import PatternFill
    from openpyxl.comments import Comment

    # 浅蓝色背景（与 AI 内容标记一致）
    prefill_fill = PatternFill(start_color="E8F4FD", end_color="E8F4FD", fill_type="solid")
    try:
        cell.fill = prefill_fill
        # 添加批注说明来源
        if not cell.comment:
            cell.comment = Comment("系统预填充：数据来自试算表", "系统")
    except Exception as e:
        logger.debug("设置预填充 cell 样式失败（只读单元格）: %s", e)


def _mark_user_formula_cell(ws, cell) -> None:
    """E1 spec Task 1.20: 为用户自定义公式 cell 设置浅绿色背景标记

    用户公式与系统预设公式视觉区分:
    - 系统预设(_mark_prefilled_cell): 浅蓝 #E8F4FD
    - 用户自定义(_mark_user_formula_cell): 浅绿 #E6F4EA
    """
    from openpyxl.styles import PatternFill
    from openpyxl.comments import Comment

    user_fill = PatternFill(start_color="E6F4EA", end_color="E6F4EA", fill_type="solid")
    try:
        cell.fill = user_fill
        if not cell.comment:
            cell.comment = Comment("用户自定义公式", "用户")
    except Exception as e:
        logger.debug("设置用户公式 cell 样式失败（只读单元格）: %s", e)


def _find_semantic_row(ws, keyword: str, wp_code: str = "", cell_ref: str = "") -> int | None:
    """在 sheet 中查找包含关键词的位置

    致同模板有两种布局：
    1. 行标签模式：A 列有"期初余额"等标签，数据在同行的 E/F 列
    2. 列头模式：第 5-6 行有"期初数"/"未审数"等列头，数据在该列的数据行

    本函数优先在 A-D 列的行标签中找，其次在前 10 行的列头中找。
    """
    search_terms = {
        "期初余额": ["期初", "年初", "上年末", "期初余额", "年初数", "上年期末", "期初数", "期初金额"],
        "未审数": ["未审", "期末余额", "未审数", "账面余额", "账面数", "未审定", "期末数", "未审金额"],
        "AJE调整": ["AJE", "审计调整", "调整分录", "审计调整数", "账项调整", "审计调整额", "调整数"],
        "RJE调整": ["RJE", "重分类", "重分类调整", "重分类数", "重分类金额", "重分类"],
        "上年审定数": ["上年", "上期", "上年审定", "上年审定数", "上期审定", "上年数", "上年末", "审定数"],
        # 子科目分项（E1/F2 等多科目底稿）
        "库存现金_期初": ["库存现金", "现金"],
        "库存现金_未审数": ["库存现金", "现金"],
        "银行存款_期初": ["银行存款", "银行"],
        "银行存款_未审数": ["银行存款", "银行"],
        "其他货币资金_期初": ["其他货币资金", "其他货币"],
        "其他货币资金_未审数": ["其他货币资金", "其他货币"],
        "原材料_期初": ["原材料"],
        "原材料_未审数": ["原材料"],
        "在产品_期初": ["在产品", "在制品"],
        "在产品_未审数": ["在产品", "在制品"],
        "库存商品_期初": ["库存商品", "产成品"],
        "库存商品_未审数": ["库存商品", "产成品"],
        "工程物资_期初": ["工程物资"],
        "工程物资_未审数": ["工程物资"],
        "委托加工物资_期初": ["委托加工", "委外加工"],
        "委托加工物资_未审数": ["委托加工", "委外加工"],
        "存货跌价准备_期初": ["跌价准备", "存货跌价"],
        "存货跌价准备_未审数": ["跌价准备", "存货跌价"],
        "其他业务成本_期初": ["其他业务成本", "其他成本"],
        "其他业务成本_未审数": ["其他业务成本", "其他成本"],
        "累计折旧_期初": ["累计折旧"],
        "累计折旧_未审数": ["累计折旧"],
        "累计摊销_期初": ["累计摊销"],
        "累计摊销_未审数": ["累计摊销"],
        "折旧": ["折旧", "折旧费", "折旧摊销"],
        "薪酬": ["薪酬", "工资", "职工薪酬", "人工"],
        "摊销": ["摊销", "摊销费", "无形资产摊销"],
    }
    terms = search_terms.get(keyword, [keyword])

    # 策略 1：在 A-D 列的行标签中找（标准行标签模式）
    for row in ws.iter_rows(min_row=1, max_row=80, max_col=4):
        for cell in row:
            if cell.value and isinstance(cell.value, str):
                if any(t in cell.value for t in terms):
                    return cell.row

    # 策略 2：在前 10 行的所有列中找列头（致同列头模式）
    # 如果找到列头，返回该列头所在行+1（数据起始行）
    for row in ws.iter_rows(min_row=1, max_row=10, max_col=20):
        for cell in row:
            if cell.value and isinstance(cell.value, str):
                if any(t in cell.value for t in terms):
                    # 找到列头，返回下一行（数据行）或当前行
                    return cell.row

    logger.warning(
        "prefill 语义行未匹配: wp_code=%s, keyword=%s, cell_ref=%s (请人工复查模板结构)",
        wp_code, keyword, cell_ref,
    )
    return None


def _find_data_column(ws, row_num: int) -> int:
    """找到数据列（第一个数字列或 E 列）"""
    for col in range(3, 20):  # C 列开始找
        cell = ws.cell(row=row_num, column=col)
        if cell.value is None or isinstance(cell.value, (int, float)):
            return col
    return 5  # 默认 E 列
