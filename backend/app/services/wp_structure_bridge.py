"""
底稿三式联动桥接服务

将底稿 Excel 文件与 structure.json / HTML 三式联动引擎打通：
1. 底稿上传/生成后 → 自动 excel_to_structure 生成 structure.json
2. StructureEditor 编辑后 → structure_to_excel 回写 xlsx
3. 审定表公式自动绑定 → 从 wp_parse_rules 读取列定义，自动为审定数列绑定 TB() 公式
4. 地址注册 → 将底稿单元格注册到 address_registry

依赖：
- excel_html_converter.py（三式联动核心引擎）
- wp_parse_rules.json / wp_parse_rules_extended.json（解析规则）
- wp_account_mapping.json（四级映射）
- address_registry.py（统一地址坐标）
"""
import json
import logging
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load_parse_rules() -> dict[str, dict]:
    """加载底稿解析规则（核心+扩展合并）"""
    rules: dict[str, dict] = {}
    for fname in ("wp_parse_rules.json", "wp_parse_rules_extended.json"):
        fp = _DATA_DIR / fname
        if not fp.exists():
            continue
        try:
            with open(fp, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            for item in data:
                code = item.get("wp_code", "")
                if code:
                    rules[code] = item
        except Exception as e:
            logger.warning("load parse rules %s failed: %s", fname, e)
    return rules


def _load_account_mapping() -> dict[str, dict]:
    """加载底稿↔科目映射"""
    fp = _DATA_DIR / "wp_account_mapping.json"
    if not fp.exists():
        return {}
    try:
        with open(fp, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        mappings = data.get("mappings", [])
        return {m["wp_code"]: m for m in mappings if "wp_code" in m}
    except Exception as e:
        logger.warning("load account mapping failed: %s", e)
        return {}


# ═══════════════════════════════════════════
# 1. 底稿 → structure.json 转换
# ═══════════════════════════════════════════

def generate_structure_for_workpaper(
    file_path: str,
    wp_code: str,
    project_id: str = "",
    year: int = 0,
    max_rows: int = 500,
) -> Optional[dict]:
    """将底稿 Excel 转为 structure.json

    自动识别审定表 Sheet 并绑定 TB() 公式到审定数列。
    """
    from app.services.excel_html_converter import excel_to_structure

    fp = Path(file_path)
    if not fp.exists():
        logger.warning("workpaper file not found: %s", file_path)
        return None

    try:
        structure = excel_to_structure(str(fp), max_rows=max_rows)
    except Exception as e:
        logger.error("excel_to_structure failed for %s: %s", file_path, e)
        return None

    if not structure:
        return None

    # 自动绑定公式
    structure = _auto_bind_formulas(structure, wp_code, project_id, year)

    # 保存 structure.json 到底稿同目录
    structure_path = fp.with_suffix(".structure.json")
    try:
        with open(structure_path, "w", encoding="utf-8") as f:
            json.dump(structure, f, ensure_ascii=False, indent=2)
        logger.info("structure.json saved: %s", structure_path)
    except Exception as e:
        logger.warning("save structure.json failed: %s", e)

    return structure


def generate_structures_for_cycle(
    base_dir: str,
    wp_code: str,
    project_id: str = "",
    year: int = 0,
) -> dict:
    """为底稿循环的所有Excel文件生成structure.json

    E1货币资金有5个Excel文件，每个都需要独立的structure.json。
    从精细化规则的source_files列表获取文件名。
    """
    from app.services.wp_fine_rule_engine import load_fine_rule

    rule = load_fine_rule(wp_code)
    base = Path(base_dir)
    results = {"generated": 0, "skipped": 0, "errors": [], "files": []}

    if rule and rule.get("source_files"):
        for sf in rule["source_files"]:
            fname = sf.get("file", "")
            if not fname:
                continue
            fp = base / fname
            if not fp.exists():
                results["skipped"] += 1
                continue
            try:
                structure = generate_structure_for_workpaper(
                    str(fp), wp_code, project_id, year
                )
                if structure:
                    results["generated"] += 1
                    results["files"].append(fname)
                else:
                    results["skipped"] += 1
            except Exception as e:
                results["errors"].append({"file": fname, "error": str(e)})
    else:
        for fp in sorted(base.glob("*.xlsx")):
            if fp.name.startswith("~$"):
                continue
            try:
                structure = generate_structure_for_workpaper(
                    str(fp), wp_code, project_id, year
                )
                if structure:
                    results["generated"] += 1
                    results["files"].append(fp.name)
            except Exception as e:
                results["errors"].append({"file": fp.name, "error": str(e)})

    return results


def _auto_bind_formulas(
    structure: dict,
    wp_code: str,
    project_id: str,
    year: int,
) -> dict:
    """自动为审定表绑定 TB() 公式

    支持三种审定表类型：
    1. 标准型（E1）：未审/调整/审定 → 绑定审定数列
    2. 三段型（D1/D2）：原值/坏账/净值，含重分类 → 绑定审定数列
    3. 变动表型（F2/H1）：期初/增加/减少/期末 → 绑定期末数列
    """
    rules = _load_parse_rules()
    mapping = _load_account_mapping()

    rule = rules.get(wp_code)
    if not rule:
        prefix = wp_code.split("-")[0] if "-" in wp_code else wp_code
        rule = rules.get(prefix)
    if not rule:
        return structure

    wp_mapping = mapping.get(wp_code) or mapping.get(wp_code.split("-")[0])
    account_codes = wp_mapping.get("account_codes", []) if wp_mapping else []
    primary_account = account_codes[0] if account_codes else ""

    sheets = rule.get("sheet_rules", rule.get("sheets", []))
    summary_sheets = [s for s in sheets if s.get("type") == "summary"]

    for sheet_rule in summary_sheets:
        columns = sheet_rule.get("columns", {})
        if not columns and "layout" in sheet_rule:
            columns = sheet_rule["layout"].get("columns", {})
        if not columns:
            continue

        # 识别审定表类型
        table_type = _detect_table_type(columns)

        # 确定目标列（要绑定公式的列）和取数维度
        if table_type == "movement":
            # 变动表：绑定期末数列
            target_col_key = "closing_balance"
            if "closing" in columns:
                target_col_key = "closing"
            tb_dimension = "审定数"
            opening_col_key = "opening"
            opening_dimension = "期初余额"
        elif table_type == "standard":
            # 标准型/三段型：绑定审定数列
            target_col_key = "closing_balance"
            tb_dimension = "审定数"
            opening_col_key = "opening_audited"
            if opening_col_key not in columns:
                opening_col_key = "opening"
            opening_dimension = "期初余额"
        else:
            target_col_key = "closing_balance"
            tb_dimension = "审定数"
            opening_col_key = "opening"
            opening_dimension = "期初余额"

        # 从精确列号绑定（优先）
        target_col_num = columns.get(target_col_key, {}).get("col")
        opening_col_num = columns.get(opening_col_key, {}).get("col")

        if target_col_num and primary_account:
            _bind_by_col_number(structure, sheet_rule, target_col_num, primary_account, tb_dimension, "closing")
            if opening_col_num:
                _bind_by_col_number(structure, sheet_rule, opening_col_num, primary_account, opening_dimension, "opening")
            continue

        # 降级：从表头关键词识别列
        target_kw = columns.get(target_col_key, {}).get("keywords", [])
        opening_kw = columns.get(opening_col_key, {}).get("keywords", [])

        rows = structure.get("rows", [])
        if not rows:
            continue

        header_row_idx = -1
        col_map: dict[str, int] = {}

        for ri, row in enumerate(rows[:10]):
            cells = row.get("cells", [])
            for ci, cell in enumerate(cells):
                val = str(cell.get("value", "")).strip()
                if not val:
                    continue
                for kw in target_kw:
                    if kw in val:
                        col_map["target"] = ci
                        header_row_idx = ri
                for kw in opening_kw:
                    if kw in val:
                        col_map["opening"] = ci

        if header_row_idx < 0 or "target" not in col_map:
            continue

        target_col = col_map["target"]
        for ri in range(header_row_idx + 1, len(rows)):
            row = rows[ri]
            cells = row.get("cells", [])
            if target_col >= len(cells):
                continue
            cell = cells[target_col]
            if cell.get("formula") or row.get("is_total"):
                continue
            if primary_account:
                cell["formula"] = f"TB('{primary_account}','{tb_dimension}')"
                cell["formula_type"] = "auto_calc"

        if "opening" in col_map and primary_account:
            opening_col = col_map["opening"]
            for ri in range(header_row_idx + 1, len(rows)):
                row = rows[ri]
                cells = row.get("cells", [])
                if opening_col >= len(cells):
                    continue
                cell = cells[opening_col]
                if cell.get("formula") or row.get("is_total"):
                    continue
                cell["formula"] = f"TB('{primary_account}','{opening_dimension}')"
                cell["formula_type"] = "auto_calc"

    return structure


def _detect_table_type(columns: dict) -> str:
    """识别审定表类型"""
    col_keys = set(columns.keys())
    # 变动表：有increase/decrease列
    if "increase" in col_keys or "decrease" in col_keys:
        return "movement"
    # 三段型：有reclass列
    if "opening_reclass" in col_keys or "closing_reclass" in col_keys:
        return "three_section"
    # 标准型
    return "standard"


def _bind_by_col_number(
    structure: dict, sheet_rule: dict,
    col_num: int, account_code: str, dimension: str, bind_type: str,
):
    """按精确列号绑定公式到structure的cells"""
    data_start = sheet_rule.get("data_start_row", 1) - 1  # 转0-indexed
    sheets = structure.get("sheets", [])
    if not sheets:
        return

    # 匹配Sheet
    pattern = sheet_rule.get("name_pattern", sheet_rule.get("exact_name", ""))
    for sheet in sheets:
        if pattern and pattern not in sheet.get("name", ""):
            continue
        cells = sheet.get("cells", {})
        rows_meta = sheet.get("rows", [])
        for ri in range(data_start, len(rows_meta)):
            cell_key = f"{ri}:{col_num - 1}"  # 转0-indexed
            cell = cells.get(cell_key, {})
            if cell.get("formula"):
                continue
            cell["formula"] = f"TB('{account_code}','{dimension}')"
            cell["formula_type"] = "auto_calc"
            cell["fetch_rule_id"] = f"wp:{bind_type}:{ri}"
            cells[cell_key] = cell


# ═══════════════════════════════════════════
# 2. structure.json → Excel 回写
# ═══════════════════════════════════════════

def save_structure_to_excel(
    file_path: str,
    structure: dict,
) -> bool:
    """将编辑后的 structure.json 回写到 Excel 文件"""
    from app.services.excel_html_converter import structure_to_excel

    try:
        excel_bytes = structure_to_excel(structure)
        fp = Path(file_path)
        fp.write_bytes(excel_bytes)
        logger.info("structure saved to excel: %s", file_path)
        return True
    except Exception as e:
        logger.error("save structure to excel failed: %s", e)
        return False


# ═══════════════════════════════════════════
# 3. 获取底稿的 structure.json（缓存优先）
# ═══════════════════════════════════════════

def get_workpaper_structure(
    file_path: str,
    wp_code: str = "",
    project_id: str = "",
    year: int = 0,
    force_rebuild: bool = False,
) -> Optional[dict]:
    """获取底稿的 structure.json

    优先从缓存文件读取，不存在或 force_rebuild 时重新生成。
    """
    fp = Path(file_path)
    structure_path = fp.with_suffix(".structure.json")

    # 缓存命中
    if not force_rebuild and structure_path.exists():
        try:
            # 检查缓存是否过期（Excel 修改时间 > structure 修改时间）
            if fp.exists() and fp.stat().st_mtime > structure_path.stat().st_mtime:
                logger.debug("structure.json stale, rebuilding for %s", file_path)
            else:
                with open(structure_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass

    # 重新生成
    return generate_structure_for_workpaper(
        file_path, wp_code, project_id, year
    )


# ═══════════════════════════════════════════
# 4. 批量生成 structure.json
# ═══════════════════════════════════════════

async def batch_generate_structures(
    db,
    project_id: str,
    year: int = 0,
) -> dict:
    """为项目所有底稿批量生成 structure.json"""
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper, WpIndex

    result = await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    rows = result.all()

    generated = 0
    skipped = 0
    errors = []

    for wp, idx in rows:
        if not wp.file_path:
            skipped += 1
            continue
        fp = Path(wp.file_path)
        if not fp.exists():
            skipped += 1
            continue

        try:
            structure = generate_structure_for_workpaper(
                wp.file_path, idx.wp_code, project_id, year
            )
            if structure:
                generated += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append({"wp_code": idx.wp_code, "error": str(e)})

    return {
        "total": len(rows),
        "generated": generated,
        "skipped": skipped,
        "errors": errors[:10],
    }


# ═══════════════════════════════════════════
# 5. 底稿地址注册到 address_registry
# ═══════════════════════════════════════════

def get_workpaper_addresses(
    file_path: str,
    wp_code: str,
    project_id: str = "",
    year: int = 0,
) -> list[dict]:
    """从底稿 structure.json 提取可引用的地址坐标

    返回格式与 address_registry.AddressEntry 兼容。
    """
    from app.services.address_registry import build_uri, build_jump_route

    structure = get_workpaper_structure(file_path, wp_code, project_id, year)
    if not structure:
        return []

    addresses = []
    rows = structure.get("rows", [])

    for ri, row in enumerate(rows):
        cells = row.get("cells", [])
        for ci, cell in enumerate(cells):
            formula = cell.get("formula")
            if not formula:
                continue

            # 有公式的单元格注册为可引用地址
            addr = cell.get("address", f"{_col_letter(ci)}{ri + 1}")
            uri = build_uri("wp", wp_code, cell=addr)
            addresses.append({
                "uri": uri,
                "domain": "wp",
                "source": wp_code,
                "path": "",
                "cell": addr,
                "label": f"底稿 > {wp_code} > {addr}",
                "formula_ref": f"WP('{wp_code}','{addr}')",
                "jump_route": build_jump_route(uri, project_id, year),
                "wp_code": wp_code,
                "tags": ["底稿", wp_code],
            })

    return addresses


def _col_letter(col_idx: int) -> str:
    """列索引转字母（0→A, 25→Z, 26→AA）"""
    result = ""
    while True:
        result = chr(65 + col_idx % 26) + result
        col_idx = col_idx // 26 - 1
        if col_idx < 0:
            break
    return result
