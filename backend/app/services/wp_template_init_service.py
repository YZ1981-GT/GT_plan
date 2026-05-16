"""底稿模板初始化服务

生成底稿时从 wp_templates/ 目录复制模板 xlsx 文件到项目底稿存储目录。
支持 prefill 预填充叠加。

流程：
1. 根据 wp_code 查找模板文件
2. 复制到项目底稿存储目录（backend/{project_id}/{wp_id}.xlsx）
3. 可选：执行 prefill 写入 =TB/=WP 计算值
4. 返回底稿文件路径供 Univer 前端加载
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BACKEND_DIR / "wp_templates"
INDEX_FILE = TEMPLATES_DIR / "_index.json"
STORAGE_DIR = BACKEND_DIR / "wp_storage"

# 缓存模板索引
_index_cache: list[dict] | None = None


def _load_index() -> list[dict]:
    """加载模板索引（带缓存）"""
    global _index_cache
    if _index_cache is not None:
        return _index_cache
    if not INDEX_FILE.exists():
        logger.warning("模板索引文件不存在: %s", INDEX_FILE)
        return []
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    _index_cache = data.get("files", [])
    return _index_cache


def find_template_file(wp_code: str) -> Path | None:
    """根据 wp_code 查找主模板文件

    优先匹配：含"审定表"或"常规程序"的文件 > 文件名最短的。
    对于多文件底稿（如 D2 有 D2-1至D2-4），返回审定表文件。
    对于子表（如 D2-2/E1-3），如果独立文件不存在，回退到主表文件
    （主表 xlsx 通常包含所有子表 sheet，如 "D2-1至D2-4 应收账款-审定表明细表"）。
    """
    index = _load_index()
    # 精确匹配
    candidates = [
        e for e in index
        if e["wp_code"] == wp_code and e["format"] in ("xlsx", "xlsm")
    ]
    if candidates:
        # 优先选择含"审定表"或"常规程序"的文件
        for c in candidates:
            if "审定表" in c["filename"] or "常规程序" in c["filename"]:
                full_path = TEMPLATES_DIR / c["relative_path"]
                if full_path.exists():
                    return full_path
        # 其次选择文件名最短的
        candidates.sort(key=lambda e: len(e["filename"]))
        rel_path = candidates[0]["relative_path"]
        full_path = TEMPLATES_DIR / rel_path
        if full_path.exists():
            return full_path

    # 模糊匹配：文件名以 wp_code 开头
    prefix = wp_code[0]
    template_subdir = TEMPLATES_DIR / prefix
    if template_subdir.exists():
        # 优先含"审定表"
        for f in sorted(template_subdir.iterdir()):
            if f.name.startswith(wp_code) and f.suffix.lower() in (".xlsx", ".xlsm"):
                if "审定表" in f.name or "常规程序" in f.name:
                    return f
        # 其次最短文件名
        for f in sorted(template_subdir.iterdir(), key=lambda x: len(x.name)):
            if f.name.startswith(wp_code) and f.suffix.lower() in (".xlsx", ".xlsm"):
                return f

        # 子表回退：如 D2-2 找不到，尝试包含范围式命名的文件（D2-1至D2-4）
        if "-" in wp_code:
            primary = wp_code.split("-")[0]
            sub_num = wp_code.split("-")[1]
            for f in sorted(template_subdir.iterdir()):
                if f.suffix.lower() not in (".xlsx", ".xlsm"):
                    continue
                # 匹配模式: 文件名含 "{primary}-N至{primary}-M" 且 sub_num 在范围内
                if f.name.startswith(primary + "-") and "至" in f.name:
                    # 简单包含检查
                    return f
            # 终极回退：用主表
            for f in sorted(template_subdir.iterdir()):
                if f.name.startswith(primary + " ") and f.suffix.lower() in (".xlsx", ".xlsm"):
                    return f

    return None


def find_all_template_files(wp_code: str) -> list[Path]:
    """查找 wp_code 对应的所有模板文件（多文件底稿）"""
    index = _load_index()
    candidates = [
        e for e in index
        if e["wp_code"] == wp_code and e["format"] in ("xlsx", "xlsm", "docx")
    ]
    results = []
    for c in candidates:
        full_path = TEMPLATES_DIR / c["relative_path"]
        if full_path.exists():
            results.append(full_path)
    return results


def find_template_file_any(wp_code: str) -> Path | None:
    """Find template file of any format (xlsx/xlsm/docx/doc)

    P2-2: 扩展模板查找支持 docx/doc 格式。
    优先返回 xlsx/xlsm，其次 docx/doc。
    """
    # 先尝试 xlsx/xlsm
    result = find_template_file(wp_code)
    if result:
        return result
    # 再尝试 docx/doc
    index = _load_index()
    candidates = [
        e for e in index
        if e["wp_code"] == wp_code and e["format"] in ("docx", "doc")
    ]
    if candidates:
        rel_path = candidates[0]["relative_path"]
        full_path = TEMPLATES_DIR / rel_path
        if full_path.exists():
            return full_path
    return None


def get_workpaper_storage_path(project_id: UUID, wp_id: UUID) -> Path:
    """获取底稿文件存储路径"""
    storage = STORAGE_DIR / str(project_id)
    storage.mkdir(parents=True, exist_ok=True)
    return storage / f"{wp_id}.xlsx"


def init_workpaper_from_template(
    project_id: UUID,
    wp_id: UUID,
    wp_code: str,
    merge_all_files: bool = True,
) -> Optional[Path]:
    """从模板初始化底稿文件

    复制模板 xlsx 到项目底稿存储目录。
    P1-2: 多文件底稿支持——如果 wp_code 对应多个 xlsx 文件，合并所有 sheet 到一个 workbook。
    P2-1: xlsm 文件只复制不 prefill（避免 openpyxl 损坏 VBA 宏）
    P2-2: docx/doc 文件直接复制（不做 xlsx 转换）

    Args:
        project_id: 项目 ID
        wp_id: 底稿 ID
        wp_code: 底稿编码（如 D2）
        merge_all_files: 是否合并多文件底稿的所有 sheet

    Returns:
        底稿文件路径，如果模板不存在返回 None
    """
    # P2-2: 尝试查找任意格式模板（xlsx/xlsm/docx/doc）
    template_path = find_template_file_any(wp_code)
    if not template_path:
        logger.warning("模板文件不存在: wp_code=%s", wp_code)
        return None

    # P2-2: docx/doc 模板直接复制，不做 xlsx 转换
    if template_path.suffix.lower() in ('.docx', '.doc'):
        target_path = get_workpaper_storage_path(project_id, wp_id).with_suffix(template_path.suffix)
        shutil.copy2(template_path, target_path)
        logger.info(
            "底稿从 Word 模板初始化: wp_code=%s, template=%s, target=%s",
            wp_code, template_path.name, target_path,
        )
        return target_path

    # P2-1: xlsm 文件只复制不 prefill（openpyxl 会损坏 VBA 宏）
    if template_path.suffix.lower() == '.xlsm':
        target_path = get_workpaper_storage_path(project_id, wp_id).with_suffix('.xlsm')
        shutil.copy2(template_path, target_path)
        logger.info(
            "Skipping prefill for xlsm template: %s (VBA macros preserved)",
            wp_code,
        )
        return target_path

    # xlsx: 复制主文件
    target_path = get_workpaper_storage_path(project_id, wp_id)
    shutil.copy2(template_path, target_path)

    # P1-2: 多文件底稿合并——将其他文件的 sheet 追加到主 workbook
    if merge_all_files:
        all_files = find_all_template_files(wp_code)
        other_files = [f for f in all_files if f != template_path and f.suffix.lower() in ('.xlsx',)]
        if other_files:
            try:
                _merge_sheets_from_other_files(target_path, other_files)
                logger.info(
                    "多文件底稿合并: wp_code=%s, merged %d additional files",
                    wp_code, len(other_files),
                )
            except Exception as e:
                logger.warning("多文件合并失败（非阻断）: wp_code=%s, error=%s", wp_code, e)

    logger.info(
        "底稿从模板初始化: wp_code=%s, template=%s, target=%s",
        wp_code, template_path.name, target_path,
    )
    return target_path


def _merge_sheets_from_other_files(target_path: Path, other_files: list[Path]) -> None:
    """将其他 xlsx 文件的 sheet 追加到目标 workbook（P1-2 多文件底稿支持）"""
    from openpyxl import load_workbook
    from copy import copy

    target_wb = load_workbook(str(target_path))
    existing_names = set(target_wb.sheetnames)

    for other_file in other_files:
        try:
            src_wb = load_workbook(str(other_file), read_only=True, data_only=True)
            for sheet_name in src_wb.sheetnames:
                if sheet_name in existing_names or sheet_name == "GT_Custom":
                    continue  # 跳过重复 sheet 和 GT 内部 sheet
                # 创建新 sheet 并复制数据（简化版：只复制值不复制格式）
                new_ws = target_wb.create_sheet(title=sheet_name[:31])  # Excel sheet 名最长 31 字符
                existing_names.add(sheet_name)
                src_ws = src_wb[sheet_name]
                for row in src_ws.iter_rows():
                    for cell in row:
                        if cell.value is not None:
                            new_ws.cell(row=cell.row, column=cell.column, value=cell.value)
            src_wb.close()
        except Exception as e:
            logger.debug("合并 sheet 失败: %s (%s)", other_file.name, e)

    target_wb.save(str(target_path))
    target_wb.close()


def prefill_workpaper_xlsx(
    target_path: Path,
    wp_code: str,
    tb_data: dict[str, dict[str, float]],
    adj_data: dict[str, dict[str, float]] | None = None,
) -> int:
    """在已复制的底稿 xlsx 中写入预填充数据

    根据 prefill_formula_mapping.json 的配置，用 openpyxl 打开 xlsx，
    找到对应 sheet 和语义行，写入试算表/调整分录的值。

    Args:
        target_path: 底稿 xlsx 文件路径
        wp_code: 底稿编码
        tb_data: 试算表数据 {科目编码: {列名: 值}}
        adj_data: 调整分录数据 {科目编码: {aje_net: 值, rje_net: 值}}

    Returns:
        写入的单元格数量
    """
    from openpyxl import load_workbook

    # 加载公式映射
    mapping_file = BACKEND_DIR / "data" / "prefill_formula_mapping.json"
    if not mapping_file.exists():
        logger.warning("prefill_formula_mapping.json 不存在")
        return 0

    with open(mapping_file, "r", encoding="utf-8") as f:
        mapping_data = json.load(f)

    # 找到当前 wp_code 的映射
    wp_mapping = next(
        (m for m in mapping_data.get("mappings", []) if m["wp_code"] == wp_code),
        None,
    )
    if not wp_mapping:
        logger.debug("wp_code=%s 无公式映射配置", wp_code)
        return 0

    try:
        wb = load_workbook(str(target_path))
    except Exception as e:
        logger.error("无法打开底稿 xlsx: %s (%s)", target_path, e)
        return 0

    sheet_name = wp_mapping.get("sheet", "")
    ws = None
    if sheet_name and sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    elif wb.sheetnames:
        # 尝试找包含"审定表"的 sheet
        for sn in wb.sheetnames:
            if "审定表" in sn:
                ws = wb[sn]
                break
        if not ws:
            ws = wb.active

    if not ws:
        wb.close()
        return 0

    filled_count = 0
    account_codes = wp_mapping.get("account_codes", [])
    primary_code = account_codes[0] if account_codes else ""

    for cell_def in wp_mapping.get("cells", []):
        formula_type = cell_def.get("formula_type", "")
        cell_ref = cell_def.get("cell_ref", "")
        value = None

        if formula_type == "TB" and primary_code:
            # =TB('code','列名') → 从 tb_data 取值
            col_name = _extract_tb_column(cell_def.get("formula", ""))
            value = tb_data.get(primary_code, {}).get(col_name)
        elif formula_type == "TB_SUM" and account_codes:
            # =TB_SUM('start~end','列名') → 汇总多科目
            col_name = _extract_tb_column(cell_def.get("formula", ""))
            value = sum(
                tb_data.get(code, {}).get(col_name, 0)
                for code in account_codes
            )
        elif formula_type == "ADJ" and primary_code and adj_data:
            # =ADJ('code','type') → 从 adj_data 取值
            adj_type = _extract_adj_type(cell_def.get("formula", ""))
            value = adj_data.get(primary_code, {}).get(adj_type, 0)

        if value is not None:
            # P0-1 双策略：先尝试坐标写入，再降级语义匹配
            written = False

    # 策略 1：如果 cell_ref 是实际坐标（如 "E8"），直接写入
            if _is_cell_coordinate(cell_ref):
                try:
                    ws[cell_ref] = value
                    _mark_prefilled_cell(ws, ws[cell_ref])
                    filled_count += 1
                    written = True
                except Exception:
                    pass

            # 策略 2：双维度定位（列头+数据行）— 致同模板标准结构
            if not written:
                col_idx = _find_column_by_keyword(ws, cell_ref)
                if col_idx:
                    # 找到列后，写入第一个数据行（列头下方第一个空行或合计行上方）
                    data_row = _find_first_data_row(ws, col_idx)
                    if data_row:
                        cell_obj = ws.cell(row=data_row, column=col_idx, value=value)
                        _mark_prefilled_cell(ws, cell_obj)
                        filled_count += 1
                        written = True

            # 策略 3：降级到语义行匹配
            if not written:
                row_num = _find_semantic_row(ws, cell_ref, wp_code, cell_ref)
                if row_num:
                    data_col = _find_data_column(ws, row_num)
                    cell_obj = ws.cell(row=row_num, column=data_col, value=value)
                    _mark_prefilled_cell(ws, cell_obj)
                    filled_count += 1

    try:
        wb.save(str(target_path))
    except Exception as e:
        logger.error("保存底稿 xlsx 失败: %s (%s)", target_path, e)

    wb.close()
    logger.info("prefill 写入: wp_code=%s, filled=%d cells", wp_code, filled_count)
    return filled_count


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
    except Exception:
        pass  # 某些只读单元格无法设置样式


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


def get_workpaper_file(project_id: UUID, wp_id: UUID) -> Optional[Path]:
    """获取已存在的底稿文件路径（如果存在）"""
    path = get_workpaper_storage_path(project_id, wp_id)
    return path if path.exists() else None


def list_available_templates() -> list[dict]:
    """列出所有可用模板（供前端选择）"""
    index = _load_index()
    # 按 wp_code 去重，只返回主文件
    seen = set()
    result = []
    for e in sorted(index, key=lambda x: (x["wp_code"], len(x["filename"]))):
        code = e["wp_code"]
        if code in seen or code == "_ref":
            continue
        seen.add(code)
        result.append({
            "wp_code": code,
            "filename": e["filename"],
            "format": e["format"],
            "size_kb": e["size_kb"],
        })
    return result
