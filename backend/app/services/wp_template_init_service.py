"""底稿模板初始化服务

生成底稿时从 wp_templates/ 目录复制模板 xlsx 文件到项目底稿存储目录。
支持 prefill 预填充叠加。

流程：
1. 根据 wp_code 查找模板文件
2. 复制到项目底稿存储目录（backend/{project_id}/{wp_id}.xlsx）
3. 可选：执行 prefill 写入 =TB/=WP 计算值
4. 返回底稿文件路径供 Univer 前端加载

pass4 拆分（spec workpaper-module-large-file-split-pass4 Req 1）：
- 模板查找域 → ``wp_template_finder.py``（find_*/_load_index/_normalize_sheet_name 等）
- xlsx 单元格 helper 域 → ``wp_template_xlsx_ops.py``（_find_*/_mark_*/_extract_*/_is_* 等）
- 主文件保留 init/prefill/IPO 加载/多文件合并/场景过滤主流程，并 re-export 子模块
  对外符号，使 ``from app.services.wp_template_init_service import ...`` 导入路径全部不变。
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

# pass4: 模板查找域子模块（re-export 保导入路径不变）
from app.services.wp_template_finder import (  # noqa: F401
    BACKEND_DIR,
    INDEX_FILE,
    TEMPLATES_DIR,
    _find_docx_by_index_or_disk,
    _find_docx_on_disk,
    _load_index,
    _match_filename_prefix,
    _normalize_sheet_name,
    _should_skip_historical_sheet,
    find_all_template_files,
    find_template_file,
    find_template_file_any,
    list_available_templates,
)

# pass4: xlsx 单元格 helper 域子模块（prefill 依赖 + re-export 保导入路径不变）
from app.services.wp_template_xlsx_ops import (  # noqa: F401
    _extract_adj_type,
    _extract_tb_column,
    _find_column_by_keyword,
    _find_data_column,
    _find_first_data_row,
    _find_semantic_row,
    _is_cell_coordinate,
    _is_formula_cell,
    _mark_prefilled_cell,
    _mark_user_formula_cell,
)

logger = logging.getLogger(__name__)

STORAGE_DIR = BACKEND_DIR / "wp_storage"


# ---------------------------------------------------------------------------
# F4 scenario 文件级裁剪规则（spec workpaper-d-sales-cycle ADR D4 / 任务 2.1）
#
# 5 档 scenario：normal 排除 IPO/上市/新三板/重组/舞弊应对 关键字命中的文件；
# 其他档（ipo/listed/transfer/restructure/fraud_response）加载全部 17 文件。
# 字典 + 帮助函数定义在此（实际文件加载位置），从 chain_orchestrator 重新导出
# 以满足 spec 任务 2.1 文本"在 chain_orchestrator.py 加 SCENARIO_TO_FILE_FILTER"
# 的模块位置约定（避开循环导入，与 _normalize_sheet_name 复用同一模式）。
# ---------------------------------------------------------------------------

SCENARIO_TO_FILE_FILTER: dict[str, dict[str, list[str]]] = {
    "normal": {
        "exclude_patterns": [
            "IPO",
            "上市",
            "新三板",
            "重组",
            "舞弊应对",
            "舞弊",
            "反舞弊",
        ],
    },
    "ipo": {},            # 加载全部
    "listed": {},         # 加载全部
    "transfer": {},       # 新三板挂牌：加载全部
    "restructure": {},    # 加载全部
    "fraud_response": {}, # 加载全部
}


def _filter_files_by_scenario(file_paths: list[Path], scenario: str) -> list[Path]:
    """按 scenario 过滤模板文件（spec F4 ADR D4 / 任务 2.1）。

    规则：当 scenario='normal' 时，排除文件名含任一 exclude_patterns 关键字
    的文件；其他 scenario 不过滤（加载全部）。未知 scenario 退化为 normal
    以保守为主（避免误加载 IPO 应对类文件给普通项目）。

    Args:
        file_paths: 模板文件路径列表
        scenario: 项目场景（normal/ipo/listed/transfer/restructure/fraud_response）

    Returns:
        过滤后的文件路径列表（保持原顺序）
    """
    rules = SCENARIO_TO_FILE_FILTER.get(scenario)
    if rules is None:
        # 未知 scenario 退化为 normal（保守过滤）
        rules = SCENARIO_TO_FILE_FILTER.get("normal", {})

    exclude_patterns = rules.get("exclude_patterns") or []
    if not exclude_patterns:
        return list(file_paths)

    return [
        p for p in file_paths
        if not any(kw in p.name for kw in exclude_patterns)
    ]


# ---------------------------------------------------------------------------
# H-F2 计量模式 sheet 显隐控制（spec workpaper-h-fixed-assets-cycle ADR-H2）
#
# H3 投资性房地产 + H7 生产性生物资产支持「成本模式」或「公允价值模式」。
# 独立于 SCENARIO_TO_FILE_FILTER（两者并行运行）。
# 前端 useHFixedAssetSheetGroups 读取 project.measurement_model 后
# 对命中 hide_patterns 的 sheet 设 visible=false。
# ---------------------------------------------------------------------------

MEASUREMENT_MODEL_FILTER: dict[str, dict[str, list[str]]] = {
    "cost": {
        "hide_patterns": ["（公允价值模式）", "(公允价值模式)"],
    },
    "fair_value": {
        "hide_patterns": ["（成本模式）", "(成本模式)"],
    },
}


# ---------------------------------------------------------------------------
# F4 / 任务 2.2 — B51-5 高风险触发 D4-22~D4-32 IPO 应对类底稿强制加载
# spec workpaper-d-sales-cycle ADR D4
# ---------------------------------------------------------------------------

# D4-22 至 D4-32 IPO 应对子表（含 D4-22A 总控台）
D4_IPO_CODES: list[str] = [
    "D4-22",
    "D4-22A",
    "D4-23",
    "D4-24",
    "D4-25",
    "D4-26",
    "D4-27",
    "D4-28",
    "D4-29",
    "D4-30",
    "D4-31",
    "D4-32",
]

# F2-61 至 F2-72 IPO 应对子表（存货及跌价准备 IPO/上市/新三板/重组/舞弊应对）
F2_IPO_CODES: list[str] = [
    "F2-61",
    "F2-62",
    "F2-63",
    "F2-64",
    "F2-65",
    "F2-66",
    "F2-67",
    "F2-68",
    "F2-69",
    "F2-70",
    "F2-71",
    "F2-72",
]

# IPO 配置注册表：prefix → (code 列表, audit_cycle, default_name_prefix)
_IPO_CONFIG: dict[str, dict] = {
    "D4": {
        "codes": D4_IPO_CODES,
        "audit_cycle": "D",
        "name_prefix": "营业收入 IPO 应对底稿",
    },
    "F2": {
        "codes": F2_IPO_CODES,
        "audit_cycle": "F",
        "name_prefix": "存货及跌价准备 IPO 应对底稿",
    },
    "H1": {
        "codes": [],
        "audit_cycle": "H",
        "name_prefix": "固定资产评估增值 IPO 应对底稿",
    },
    "J1": {
        "codes": [],
        "audit_cycle": "J",
        "name_prefix": "职工薪酬 IPO 应对底稿",
    },
    "K8": {
        "codes": [],
        "audit_cycle": "K",
        "name_prefix": "销售费用 IPO 应对底稿",
    },
    "L1": {
        "codes": [],
        "audit_cycle": "L",
        "name_prefix": "筹资循环 IPO 应对底稿",
    },
    "M2": {
        "codes": [],
        "audit_cycle": "M",
        "name_prefix": "权益循环 IPO 应对底稿",
    },
    "N2": {
        "codes": [],
        "audit_cycle": "N",
        "name_prefix": "应交税费 IPO 应对底稿",
    },
}


async def _ensure_ipo_loaded(
    db,  # AsyncSession (避免顶层依赖触发循环导入)
    project_id: UUID,
    year: int,
    wp_code_prefix: str = "D4",
) -> dict:
    """通用 IPO 应对底稿加载函数（D4 / F2 等多前缀参数化）。

    spec workpaper-f-purchase-inventory F-F14 / ADR-F4。

    支持的 prefix（见 ``_IPO_CONFIG``）:
      - "D4": D 销售循环 D4-22~D4-32（B51-5 高风险触发）
      - "F2": F 采购存货循环 F2-61~F2-72（B51-4 高风险触发）
      - "H1": H 固定资产循环（占位，codes=[]，暂无事件触发）

    实现策略（最小破坏式）:
      1. 对每个 IPO wp_code：
         - 查 ``wp_index`` 是否已存在 → 已存在则计入 ``skipped_existing``
         - 否则创建 ``WpIndex`` + ``WorkingPaper`` 记录，并强制以
           ``scenario='ipo'`` 调 ``init_workpaper_from_template`` 复制模板
           （绕过 ``scenario='normal'`` 的 IPO 文件过滤规则）
      2. 任一 wp_code 创建失败时回滚到该 wp_code 子事务，记录到 errors，继续下一个

    幂等：已存在的 wp_code 不会重复创建。

    Args:
        db: 异步 SQLAlchemy 会话（``AsyncSession``）
        project_id: 项目 UUID
        year: 财政年度（保留参数，未来按年度区分时使用）
        wp_code_prefix: IPO 配置 key，必须在 ``_IPO_CONFIG`` 中

    Returns:
        dict 含 ``added_codes`` / ``skipped_existing`` / ``errors`` / ``skipped_trimmed_codes`` /
        ``in_recycle_codes`` / ``blank_codes`` 列表、``generation_receipt``（统一回执，见 wp_generation_receipt），
        以及 ``prefix`` 标识本次加载的循环。
    """
    cfg = _IPO_CONFIG.get(wp_code_prefix.upper())
    if not cfg:
        return {
            "prefix": wp_code_prefix,
            "added_codes": [],
            "skipped_existing": [],
            "errors": [{"code": "*", "error": f"unsupported prefix: {wp_code_prefix}"}],
        }

    codes: list[str] = cfg["codes"]
    audit_cycle: str = cfg["audit_cycle"]
    name_prefix: str = cfg["name_prefix"]

    result: dict[str, Any] = {
        "prefix": wp_code_prefix,
        "added_codes": [],
        "skipped_existing": [],
        "errors": [],
        "skipped_trimmed_codes": [],
        "in_recycle_codes": [],
        "blank_codes": [],
    }

    # year 参数当前未做按年度筛选（wp_index 不带 year 字段），保留供未来扩展
    _ = year

    if not codes:
        return result
    # 保留范围：已裁（科目被裁则 IPO 子表跟随）/ 在回收站的不建；读不到裁剪结果即抛出、不加载
    from app.services.procedure_scope_retention import plan_generation
    from app.services.wp_generate_file import create_template_workpaper
    from app.services.wp_generation_receipt import GenerationReceipt

    plan = await plan_generation(db, project_id, codes)
    receipt = GenerationReceipt.from_plan(plan)
    # 单码保存点内建行 + 落文件（强制 scenario='ipo' 绕过 normal 的 IPO 文件过滤）；复制失败回滚该码、进 errors，
    # 不再计入 added_codes（spec procedure-chain-hardening-and-java-contracts R11.4：原先复制在保存点外、失败照样算新增）
    for code in plan.to_create:
        await create_template_workpaper(db, receipt, project_id=project_id, wp_code=code,
                                        wp_name=f"{name_prefix} {code}", audit_cycle=audit_cycle, scenario="ipo")
    result.update(plan.receipt(), added_codes=receipt.created_codes, skipped_existing=list(plan.existing_codes),
                  errors=[{"code": f["wp_code"], "error": f["error"]} for f in receipt.failures],
                  blank_codes=receipt.blank_codes, generation_receipt=receipt.to_payload())
    return result


async def _ensure_d4_ipo_loaded(
    db,  # AsyncSession (避免顶层依赖触发循环导入)
    project_id: UUID,
    year: int,
) -> dict:
    """B51-5 高风险触发：确保 D4-22~D4-32 IPO 应对类底稿已加载到当前项目。

    spec workpaper-d-sales-cycle 任务 2.2 / ADR D4。

    向后兼容包装：转发到通用 ``_ensure_ipo_loaded(prefix='D4')``。
    保留独立函数名以避免破坏 D spec 既有调用点；返回值剥离 ``prefix`` 与 ``generation_receipt``，
    透传已裁 / 在回收站 / 空白册（spec procedure-chain-hardening-and-java-contracts R11.4：原先只留三键，
    被裁剪挡下的编码对调用方不可见）。
    """
    raw = await _ensure_ipo_loaded(db, project_id, year, wp_code_prefix="D4")
    keys = ("added_codes", "skipped_existing", "errors", "skipped_trimmed_codes", "in_recycle_codes", "blank_codes")
    return {k: raw.get(k, []) for k in keys}


def _merge_sheets_dedup(
    target_path: Path,
    other_files: list[Path],
) -> dict:
    """合并多个 xlsx 文件的 sheet 到 target workbook，按"先过滤历史 → 再归一化去重"流程。

    spec workpaper-d-sales-cycle F2 + F3 主入口（ADR D2 + D3 + D14 双总控台过滤）。

    流程（每条 source sheet）:
      1. 若 `_should_skip_historical_sheet(name)` → 跳过（历史遗留过滤）
      2. 计算 `_normalize_sheet_name(name)`，若已存在归一化名 → 跳过（去重）
      3. 否则按原始 sheet_name（截断到 31 字符以满足 Excel 限制）创建新 sheet 并复制值

    Args:
        target_path: 主 workbook 路径（已存在）
        other_files: 待合并的 xlsx 路径列表

    Returns:
        {"merged": int, "skipped_dup": int, "skipped_historical": int} 统计信息
    """
    from openpyxl import load_workbook

    from app.services.xlsx_cell_patch import ValueSheet, XlsxPatchError, append_value_sheets, workbook_sheet_names

    stats = {"merged": 0, "skipped_dup": 0, "skipped_historical": 0}

    # 用归一化名集合去重（含 target 自身已有 sheet）
    existing_normalized: set[str] = {
        _normalize_sheet_name(s) for s in workbook_sheet_names(target_path)
    }
    pending: list[ValueSheet] = []

    for other_file in other_files:
        try:
            src_wb = load_workbook(str(other_file), read_only=True, data_only=True)
            try:
                collected: list[tuple[str, ValueSheet]] = []
                for sheet_name in src_wb.sheetnames:
                    # 1. 历史遗留 sheet 过滤（修订前 / （原））
                    if _should_skip_historical_sheet(sheet_name):
                        stats["skipped_historical"] += 1
                        logger.debug(
                            "merge_sheets_dedup: 跳过历史遗留 sheet '%s' from %s",
                            sheet_name, other_file.name,
                        )
                        continue

                    # 2. 归一化去重（覆盖 GT_Custom / 底稿目录 / 中英文圆括号变体）
                    normalized = _normalize_sheet_name(sheet_name)
                    if normalized in existing_normalized or any(n == normalized for n, _ in collected):
                        stats["skipped_dup"] += 1
                        logger.debug(
                            "merge_sheets_dedup: 跳过重复 sheet '%s' (normalized='%s') from %s",
                            sheet_name, normalized, other_file.name,
                        )
                        continue

                    # 3. 只取值（公式取缓存结果，与原先一致）；Excel sheet 名最长 31 字符
                    cells = [(cell.row, cell.column, cell.value)
                             for row in src_wb[sheet_name].iter_rows() for cell in row if cell.value is not None]
                    collected.append((normalized, ValueSheet(title=sheet_name[:31], cells=cells)))
            finally:
                src_wb.close()
        except Exception as e:
            logger.debug(
                "merge_sheets_dedup: 合并失败 %s (%s)",
                other_file.name, e,
            )
            continue
        # 一个源文件整份读完才计入（读到一半出错不留半个文件的页）
        for normalized, sheet in collected:
            existing_normalized.add(normalized)
            pending.append(sheet)
            stats["merged"] += 1

    if not pending:
        return stats
    # 追加到主文件末尾：主文件原有部件逐字节不动（原先 openpyxl 整册重存，主文件的 x14 数据验证、公式缓存值等全丢；
    # spec post-push-residual-defect-closure R4.5）
    try:
        append_value_sheets(target_path, pending)
    except XlsxPatchError:
        logger.warning("merge_sheets_dedup: %s 结构不认识，改用 openpyxl 整册重存合并（会丢数据验证扩展等）",
                       target_path.name, exc_info=True)
        _append_value_sheets_openpyxl(target_path, pending)
    return stats


def _append_value_sheets_openpyxl(target_path: Path, sheets: list) -> None:
    """``append_value_sheets`` 认不出工作簿结构时的退路（原先的合并写法：openpyxl 建页写值后整册重存）。"""
    from openpyxl import load_workbook

    target_wb = load_workbook(str(target_path))
    try:
        for sheet in sheets:
            new_ws = target_wb.create_sheet(title=sheet.title)
            for r, c, v in sheet.cells:
                new_ws.cell(row=r, column=c, value=v)
        target_wb.save(str(target_path))
    finally:
        target_wb.close()


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
    scenario: str = "normal",
    has_foreign_currency: bool = False,
) -> Optional[Path]:
    """从模板初始化底稿文件

    复制模板 xlsx 到项目底稿存储目录。
    P1-2: 多文件底稿支持——如果 wp_code 对应多个 xlsx 文件，合并所有 sheet 到一个 workbook。
    P2-1: xlsm 文件只复制不 prefill（避免 openpyxl 损坏 VBA 宏）
    P2-2: docx/doc 文件直接复制（不做 xlsx 转换）

    E1 Sprint 2 Task 2.2: scenario 文件级裁剪（F1.2）
    - normal: 仅加载 F1+F2+F3
    - 非 normal (ipo/listed/transfer/restructure/fraud_response): 加载 F1+F2+F3+F4

    Args:
        project_id: 项目 ID
        wp_id: 底稿 ID
        wp_code: 底稿编码（如 D2）
        merge_all_files: 是否合并多文件底稿的所有 sheet
        scenario: 项目场景（normal/ipo/listed/transfer/restructure/fraud_response）
        has_foreign_currency: 是否有外币业务（保留参数，未来用于 sheet 级裁剪）

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
        # spec workpaper-d-sales-cycle 任务 2.1（F4 ADR D4）：
        # 通用 scenario 文件级裁剪——替换 E1 spec 的硬编码"E1 + normal"过滤。
        # 现行规则对所有 wp_code 一致：scenario='normal' 时排除 IPO/上市/新三板/
        # 重组/舞弊应对 关键字命中的文件；其他 scenario 加载全部。
        other_files = _filter_files_by_scenario(other_files, scenario)
        if other_files:
            try:
                _merge_sheets_from_other_files(target_path, other_files)
                logger.info(
                    "多文件底稿合并: wp_code=%s, scenario=%s, merged %d additional files",
                    wp_code, scenario, len(other_files),
                )
            except Exception as e:
                logger.warning("多文件合并失败（非阻断）: wp_code=%s, error=%s", wp_code, e)

    logger.info(
        "底稿从模板初始化: wp_code=%s, template=%s, target=%s",
        wp_code, template_path.name, target_path,
    )
    return target_path


def _merge_sheets_from_other_files(target_path: Path, other_files: list[Path]) -> None:
    """将其他 xlsx 文件的 sheet 追加到目标 workbook（P1-2 多文件底稿支持）。

    spec workpaper-d-sales-cycle F2/F3 重构：委派给 ``_merge_sheets_dedup``，
    新增中英文圆括号归一化 + 修订前/（原）历史 sheet 过滤。
    返回值仍保持 None（向后兼容现有 callers）；统计信息通过 logger.info 输出。
    """
    stats = _merge_sheets_dedup(target_path, other_files)
    logger.info(
        "merge_sheets_dedup stats target=%s merged=%d skipped_dup=%d skipped_historical=%d",
        target_path.name,
        stats["merged"],
        stats["skipped_dup"],
        stats["skipped_historical"],
    )


def prefill_workpaper_xlsx(
    target_path: Path,
    wp_code: str,
    tb_data: dict[str, dict[str, float]],
    adj_data: dict[str, dict[str, float]] | None = None,
    user_formulas: dict[str, dict] | None = None,
    mapping_overrides: dict[str, str] | None = None,
    prev_values: dict[str, Any] | None = None,
) -> int:
    """在已复制的底稿 xlsx 中写入预填充数据

    根据 prefill_formula_mapping.json 的配置，用 openpyxl 打开 xlsx，
    找到对应 sheet 和语义行，写入试算表/调整分录的值。

    E1 spec Sprint 1 Task 1.20 执行优先级:
        user_formulas(覆盖)> prefill_formula_mapping(预设)> 模板内置公式
    具体实现: 当 cell_key (sheet!cell_ref) 在 user_formulas 中时,跳过预设写入,
    交由 xlsx 自身的公式引擎在前端展示阶段计算用户公式。

    Args:
        target_path: 底稿 xlsx 文件路径
        wp_code: 底稿编码
        tb_data: 试算表数据 {科目编码: {列名: 值}}
        adj_data: 调整分录数据 {科目编码: {aje_net: 值, rje_net: 值}}
        user_formulas: 用户自定义公式 {sheet!cell_ref: {formula, formula_type, ...}}
        mapping_overrides: 映射单元格的有效公式（本项目 / 全局改过）{sheet!cell_ref: formula}，按它取值
        prev_values: 三参 PREV 格的上年同底稿取数 {sheet!cell_ref: PrevPrefill}（``prev3_prefill_locator.resolve_prev_prefill``）；
            三参 PREV 格（全部块）按定位表落格，不按列头关键词猜；不传则这些格不动

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

    # E1 spec Task 1.20: user_formulas 优先级 — 收集本 sheet 内被用户覆盖的 cell_ref
    user_formulas = user_formulas or {}
    user_overridden_cells: set[str] = set()
    if user_formulas:
        sheet_prefix = f"{ws.title}!"
        for key in user_formulas:
            if key.startswith(sheet_prefix):
                cell_ref_only = key[len(sheet_prefix):]
                user_overridden_cells.add(cell_ref_only)
        if user_overridden_cells:
            # 在 sheet 上写入用户公式(让 xlsx 自带公式引擎计算)
            for key, ufmt in user_formulas.items():
                if not key.startswith(sheet_prefix):
                    continue
                cell_ref_only = key[len(sheet_prefix):]
                if not _is_cell_coordinate(cell_ref_only):
                    continue
                user_formula_text = ufmt.get("formula") if isinstance(ufmt, dict) else str(ufmt)
                if not user_formula_text:
                    continue
                try:
                    target = ws[cell_ref_only]
                    target.value = user_formula_text
                    _mark_user_formula_cell(ws, target)
                    filled_count += 1
                except Exception as e:
                    logger.debug("user_formula 写入失败 %s: %s", key, e)

    from app.services import prev3_prefill_locator as prev3

    prev3_slots = prev3.slot_keys(wp_code)  # 三参 PREV 公式位只按定位表落格（见下方 apply_prefills）
    for cell_def in wp_mapping.get("cells", []):
        formula_type = cell_def.get("formula_type", "")
        cell_ref = cell_def.get("cell_ref", "")
        # E1 spec Task 1.20: 用户自定义已覆盖此 cell,跳过预设写入
        if cell_ref in user_overridden_cells or (sheet_name.strip(), cell_ref.strip()) in prev3_slots:
            continue
        # 占位 cell_ref(以下划线开头)是"汇总驱动 cell",不写入 Univer
        if cell_ref.startswith("_"):
            continue
        value = None
        override = (mapping_overrides or {}).get(f"{sheet_name}!{cell_ref}")

        if override is not None:  # formula-global-settings-sync：全局 > 预设映射
            from app.services.formula_settings.wp_effective import override_value

            value = override_value(override, cell_def.get("formula", ""), tb_data, adj_data, account_codes)
        elif formula_type == "TB" and primary_code:
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
                    target_cell = ws[cell_ref]
                    # E1 spec Task 1.1: 不覆盖已有公式 cell
                    if _is_formula_cell(target_cell):
                        logger.debug(
                            "prefill 跳过公式 cell: wp_code=%s sheet=%s ref=%s formula=%s",
                            wp_code, ws.title, cell_ref, target_cell.value,
                        )
                    else:
                        ws[cell_ref] = value
                        _mark_prefilled_cell(ws, ws[cell_ref])
                        filled_count += 1
                    written = True
                except Exception as e:
                    logger.warning("prefill 写入 cell 失败 wp_code=%s ref=%s: %s", wp_code, cell_ref, e)

            # 策略 2：双维度定位（列头+数据行）— 致同模板标准结构
            if not written:
                col_idx = _find_column_by_keyword(ws, cell_ref)
                if col_idx:
                    # 找到列后，写入第一个数据行（列头下方第一个空行或合计行上方）
                    data_row = _find_first_data_row(ws, col_idx)
                    if data_row:
                        cell_obj = ws.cell(row=data_row, column=col_idx)
                        # E1 spec Task 1.1: 不覆盖已有公式 cell
                        if _is_formula_cell(cell_obj):
                            logger.debug(
                                "prefill 跳过公式 cell: wp_code=%s sheet=%s row=%d col=%d formula=%s",
                                wp_code, ws.title, data_row, col_idx, cell_obj.value,
                            )
                        else:
                            cell_obj.value = value
                            _mark_prefilled_cell(ws, cell_obj)
                            filled_count += 1
                        written = True

            # 策略 3：降级到语义行匹配
            if not written:
                row_num = _find_semantic_row(ws, cell_ref, wp_code, cell_ref)
                if row_num:
                    data_col = _find_data_column(ws, row_num)
                    cell_obj = ws.cell(row=row_num, column=data_col)
                    # E1 spec Task 1.1: 不覆盖已有公式 cell
                    if _is_formula_cell(cell_obj):
                        logger.debug(
                            "prefill 跳过公式 cell: wp_code=%s sheet=%s row=%d col=%d formula=%s",
                            wp_code, ws.title, row_num, data_col, cell_obj.value,
                        )
                    else:
                        cell_obj.value = value
                        _mark_prefilled_cell(ws, cell_obj)
                        filled_count += 1

    prefills = {**(prev_values or {}),
                **prev3.override_prefills(mapping_data, wp_code, mapping_overrides, tb_data, adj_data)}
    user_cells = {(k.split("!", 1)[0].strip(), k.split("!", 1)[1].strip().upper()) for k in user_formulas if "!" in k}
    filled_count += prev3.apply_prefills(wb, wp_code, prefills, skip_cells=user_cells)

    try:
        wb.save(str(target_path))
    except Exception as e:
        logger.error("保存底稿 xlsx 失败: %s (%s)", target_path, e)

    wb.close()
    logger.info("prefill 写入: wp_code=%s, filled=%d cells", wp_code, filled_count)
    return filled_count


def get_workpaper_file(project_id: UUID, wp_id: UUID) -> Optional[Path]:
    """获取已存在的底稿文件路径（如果存在）"""
    path = get_workpaper_storage_path(project_id, wp_id)
    return path if path.exists() else None
