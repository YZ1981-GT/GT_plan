"""
统一地址坐标注册表 (Address Registry)

@see address_registry_v2 — 本模块=运行时动态地址目录（公式编辑用）

所有可引用的数据坐标统一管理，供公式编辑、溯源跳转、有效性校验使用。

地址格式: {domain}://{source}/{path}#{cell}
  - report://BS/BS-002#期末       → 报表行次
  - note://五、3/应收账款#合计.期末 → 附注章节
  - wp://E1-1/审定表#B7           → 底稿单元格
  - tb://1001#审定数               → 试算表科目
  - aux://1001.成本中心.001#期末   → 辅助余额
"""
import json
import re
import logging
from dataclasses import asdict, dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AddressEntry:
    """一个可引用的地址坐标"""
    uri: str                    # 完整地址 report://BS/BS-002#期末
    domain: str                 # report / note / wp / tb / aux
    source: str                 # BS / 五、3 / E1-1 / 1001
    path: str                   # BS-002 / 应收账款 / 审定表
    cell: str                   # 期末 / 合计.期末 / B7 / 审定数
    label: str                  # 人类可读标签: "资产负债表 > 货币资金 > 期末"
    value: Optional[float] = None  # 当前值（缓存）
    row_code: str = ""          # 行次编码（报表用）
    account_code: str = ""      # 科目编码（试算表/辅助用）
    note_section: str = ""      # 附注章节（附注用）
    wp_code: str = ""           # 底稿编码（底稿用）
    jump_route: str = ""        # 前端跳转路由
    formula_ref: str = ""       # 公式引用语法: TB('1001','审定数')
    tags: list = field(default_factory=list)  # 标签: ['资产','流动资产','货币资金']


# ═══════════════════════════════════════════
# 地址解析
# ═══════════════════════════════════════════

_URI_PATTERN = re.compile(
    r'^(?P<domain>report|note|wp|tb|aux)://'
    r'(?P<source>[^/]+)'
    r'(?:/(?P<path>[^#]*))?'
    r'(?:#(?P<cell>.+))?$'
)


def parse_uri(uri: str) -> Optional[dict]:
    """解析地址URI为组成部分"""
    m = _URI_PATTERN.match(uri)
    if not m:
        return None
    return {
        'domain': m.group('domain'),
        'source': m.group('source'),
        'path': m.group('path') or '',
        'cell': m.group('cell') or '',
    }


def build_uri(domain: str, source: str, path: str = '', cell: str = '') -> str:
    """构建地址URI"""
    uri = f"{domain}://{source}"
    if path:
        uri += f"/{path}"
    if cell:
        uri += f"#{cell}"
    return uri


# ═══════════════════════════════════════════
# 公式引用语法 ↔ URI 互转
# ═══════════════════════════════════════════

_FORMULA_PATTERNS = {
    'TB': re.compile(r"TB\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"),
    'SUM_TB': re.compile(r"SUM_TB\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"),
    'ROW': re.compile(r"ROW\(\s*'([^']+)'\s*\)"),
    'SUM_ROW': re.compile(r"SUM_ROW\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"),
    'REPORT': re.compile(r"REPORT\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"),
    'NOTE': re.compile(r"NOTE\(\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)"),
    'WP': re.compile(r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"),
    'AUX': re.compile(r"AUX\(\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)"),
    'PREV': re.compile(r"PREV\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"),
}


def formula_ref_to_uri(formula_ref: str) -> Optional[str]:
    """将公式引用语法转为URI
    TB('1001','审定数') → tb://1001#审定数
    ROW('BS-002') → report://BS/BS-002#本期
    NOTE('五、3','合计','期末') → note://五、3/合计#期末
    """
    for fn_name, pattern in _FORMULA_PATTERNS.items():
        m = pattern.search(formula_ref)
        if not m:
            continue
        groups = [g for g in m.groups() if g is not None]

        if fn_name in ('TB', 'SUM_TB', 'PREV'):
            return build_uri('tb', groups[0], cell=groups[1])
        elif fn_name in ('ROW', 'SUM_ROW'):
            # ROW('BS-002') → report://BS/BS-002
            code = groups[0]
            report_type = _row_code_to_report_type(code)
            return build_uri('report', report_type, code, '本期')
        elif fn_name == 'REPORT':
            code = groups[0]
            report_type = _row_code_to_report_type(code)
            return build_uri('report', report_type, code, groups[1])
        elif fn_name == 'NOTE':
            section = groups[0]
            row_label = groups[1] if len(groups) > 1 else ''
            col_label = groups[2] if len(groups) > 2 else '期末'
            return build_uri('note', section, row_label, col_label)
        elif fn_name == 'WP':
            # 单元格/列名走 path，避免 wp://D11#B5 被解析为 source=D11#B5
            return build_uri('wp', groups[0], path=groups[1])
        elif fn_name == 'AUX':
            account = groups[0]
            dim = groups[1] if len(groups) > 1 else ''
            col = groups[2] if len(groups) > 2 else '期末'
            return build_uri('aux', account, dim, col)
    return None


def uri_to_formula_ref(uri: str) -> Optional[str]:
    """将URI转为公式引用语法
    tb://1001#审定数 → TB('1001','审定数')
    report://BS/BS-002#期末 → REPORT('BS-002','期末')
    """
    parts = parse_uri(uri)
    if not parts:
        return None

    domain = parts['domain']
    source = parts['source']
    path = parts['path']
    cell = parts['cell']

    if domain == 'tb':
        return f"TB('{source}','{cell}')"
    elif domain == 'report':
        if cell:
            return f"REPORT('{path}','{cell}')"
        else:
            return f"ROW('{path}')"
    elif domain == 'note':
        if cell:
            return f"NOTE('{source}','{path}','{cell}')"
        else:
            return f"NOTE('{source}','{path}')"
    elif domain == 'wp':
        if path == 'xref' and cell:
            return None
        if not path and not cell:
            rest = uri.split('://', 1)[-1]
            if '#' in rest and '/' not in rest.split('#', 1)[0]:
                wp_source, _, addr = rest.partition('#')
                return f"WP('{wp_source}','{addr}')"
        addr = cell or path
        return f"WP('{source}','{addr}')"
    elif domain == 'aux':
        return f"AUX('{source}','{path}','{cell}')"
    return None


def _row_code_to_report_type(code: str) -> str:
    """从行次编码推断报表类型"""
    prefix = code.split('-')[0] if '-' in code else code[:2]
    mapping = {
        'BS': 'BS', 'IS': 'IS', 'CFS': 'CFS', 'EQ': 'EQ',
        'CFSS': 'CFSS', 'IMP': 'IMP',
    }
    return mapping.get(prefix, 'BS')


# ═══════════════════════════════════════════
# 跳转路由生成
# ═══════════════════════════════════════════

def build_jump_route(uri: str, project_id: str, year: int = 0) -> str:
    """根据地址URI生成前端跳转路由"""
    parts = parse_uri(uri)
    if not parts:
        return ''

    domain = parts['domain']
    source = parts['source']
    path = parts['path']
    cell = parts['cell']
    base = f"/projects/{project_id}"
    qs = f"?year={year}" if year else ""

    if domain == 'report':
        tab = _report_type_to_tab(source)
        return f"{base}/reports{qs}&tab={tab}&highlight={path}"
    elif domain == 'note':
        return f"{base}/disclosure-notes{qs}&section={source}&highlight={path}"
    elif domain == 'wp':
        return f"{base}/workpapers{qs}&highlight={source}"
    elif domain == 'tb':
        return f"{base}/trial-balance{qs}&highlight={source}"
    elif domain == 'aux':
        return f"{base}/ledger{qs}&tab=aux&account={source}"
    return ''


def _report_type_to_tab(report_type: str) -> str:
    mapping = {
        'BS': 'balance_sheet', 'IS': 'income_statement',
        'CFS': 'cash_flow_statement', 'EQ': 'equity_statement',
        'CFSS': 'cash_flow_supplement', 'IMP': 'impairment_provision',
    }
    return mapping.get(report_type, 'balance_sheet')


# ═══════════════════════════════════════════
# 注册表构建（从各数据源加载）
# ═══════════════════════════════════════════

_REPORT_TYPE_LABELS = {
    'BS': '资产负债表', 'IS': '利润表', 'CFS': '现金流量表',
    'EQ': '权益变动表', 'CFSS': '现金流附表', 'IMP': '资产减值准备表',
}

_PERIOD_COLUMNS = {
    'BS': ['期末', '期初'],
    'IS': ['本期', '上期'],
    'CFS': ['本期', '上期'],
    'EQ': ['本年', '上年'],
    'CFSS': ['本期', '上期'],
    'IMP': ['期末', '期初'],
}


async def build_report_entries(db, project_id: str, year: int) -> list[AddressEntry]:
    """从报表配置构建报表地址条目"""
    from sqlalchemy import select
    from app.models.report_models import ReportConfig

    entries = []
    try:
        result = await db.execute(
            select(ReportConfig).where(ReportConfig.is_deleted == False)
        )
        configs = result.scalars().all()

        for cfg in configs:
            rt = cfg.report_type or 'balance_sheet'
            rt_short = _report_type_short(rt)
            rt_label = _REPORT_TYPE_LABELS.get(rt_short, rt)
            periods = _PERIOD_COLUMNS.get(rt_short, ['期末', '期初'])

            for period in periods:
                uri = build_uri('report', rt_short, cfg.row_code or '', period)
                entries.append(AddressEntry(
                    uri=uri,
                    domain='report',
                    source=rt_short,
                    path=cfg.row_code or '',
                    cell=period,
                    label=f"{rt_label} > {cfg.row_name} > {period}",
                    row_code=cfg.row_code or '',
                    formula_ref=f"REPORT('{cfg.row_code}','{period}')",
                    jump_route=build_jump_route(uri, project_id, year),
                    tags=[rt_label, cfg.row_name or ''],
                ))
    except Exception as e:
        logger.warning(f"build_report_entries error: {e}")
    return entries


async def build_trial_balance_entries(db, project_id: str, year: int) -> list[AddressEntry]:
    """从试算表构建地址条目"""
    from sqlalchemy import select
    from app.models.audit_platform_models import TrialBalance

    entries = []
    columns = ['未审数', '审定数', 'AJE调整', 'RJE调整', '期初余额']
    try:
        result = await db.execute(
            select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == False,
            )
        )
        rows = result.scalars().all()

        for row in rows:
            code = row.standard_account_code or ''
            name = row.account_name or code
            for col in columns:
                uri = build_uri('tb', code, cell=col)
                entries.append(AddressEntry(
                    uri=uri,
                    domain='tb',
                    source=code,
                    path='',
                    cell=col,
                    label=f"试算表 > {code} {name} > {col}",
                    account_code=code,
                    formula_ref=f"TB('{code}','{col}')",
                    jump_route=build_jump_route(uri, project_id, year),
                    tags=['试算表', name, row.account_category or ''],
                ))
    except Exception as e:
        logger.warning(f"build_trial_balance_entries error: {e}")
    return entries


async def build_note_entries(db, project_id: str, year: int,
                             template_type: str = 'soe') -> list[AddressEntry]:
    """从附注模板构建地址条目"""
    import json
    from pathlib import Path

    entries = []
    try:
        tpl_file = Path(__file__).parent.parent.parent / 'data' / f'note_template_{template_type}.json'
        if not tpl_file.exists():
            return entries

        with open(tpl_file, 'r', encoding='utf-8-sig') as f:
            sections = json.load(f)

        for sec in sections:
            section_id = sec.get('section_id', sec.get('note_section', ''))
            title = sec.get('section_title', sec.get('title', ''))
            tables = sec.get('tables', [])
            if not tables and sec.get('table_template'):
                tables = [sec['table_template']]

            for tbl_idx, tbl in enumerate(tables):
                tbl_name = tbl.get('name', f'表{tbl_idx + 1}')
                headers = tbl.get('headers', [])
                rows_tpl = tbl.get('rows', [])

                # 为每个表头列+合计行生成地址
                for col_idx, hdr in enumerate(headers):
                    if isinstance(hdr, str) and hdr:
                        uri = build_uri('note', section_id, '合计', hdr)
                        entries.append(AddressEntry(
                            uri=uri,
                            domain='note',
                            source=section_id,
                            path='合计',
                            cell=hdr,
                            label=f"附注 > {title} > {tbl_name} > 合计 > {hdr}",
                            note_section=section_id,
                            formula_ref=f"NOTE('{section_id}','合计','{hdr}')",
                            jump_route=build_jump_route(uri, project_id, year),
                            tags=['附注', title],
                        ))
    except Exception as e:
        logger.warning(f"build_note_entries error: {e}")
    return entries


# ── 自定义底稿 parsed_data 单元格提取（custom-workpaper-formula-binding）──

_CELL_ADDRESS_RE = re.compile(r"^[A-Z]+\d+$")

_PARSED_DATA_META_KEYS = frozenset({
    "html_data",
    "user_formulas",
    "conclusion",
    "schema_version",
    "_version",
    "last_modified_by",
    "last_modified_at",
    "changed_sheets_last_save",
    "cells",
})


@dataclass
class CellRecord:
    """parsed_data 提取出的单元格（集成点 2 纯函数产物）。"""
    sheet: str
    cell: str
    row_label: str
    value: object = None


def _cell_scalar_value(raw: object) -> object:
    """标量或 dict cell 取值。"""
    if isinstance(raw, dict):
        for key in ("v", "value", "val"):
            if key in raw:
                return raw[key]
        label = raw.get("label") or raw.get("name")
        if label is not None:
            return label
        return None
    return raw


def _row_label_for_cell(
    cells_map: dict,
    sheet: str,
    cell_ref: str,
) -> str:
    """同行 A 列文本作 row_label；cell 自带 label/name 优先。"""
    from app.services.note_wp_data_resolver import _split_cell_ref

    parsed = _split_cell_ref(cell_ref)
    if parsed is None:
        return ""
    _col, row_num = parsed
    a_ref = f"A{row_num}"

    def _lookup(ref: str) -> str:
        flat_key = f"{sheet}!{ref}"
        if flat_key in cells_map:
            v = _cell_scalar_value(cells_map[flat_key])
            return str(v).strip() if v is not None else ""
        sheet_block = cells_map.get(sheet)
        if isinstance(sheet_block, dict) and ref in sheet_block:
            v = _cell_scalar_value(sheet_block[ref])
            return str(v).strip() if v is not None else ""
        return ""

    nested_html = cells_map.get("__html_sheet_cells__")
    if isinstance(nested_html, dict):
        sheet_cells = nested_html.get(sheet)
        if isinstance(sheet_cells, dict):
            if cell_ref in sheet_cells:
                raw = sheet_cells[cell_ref]
                if isinstance(raw, dict):
                    lbl = raw.get("label") or raw.get("name")
                    if lbl:
                        return str(lbl).strip()
            if a_ref in sheet_cells:
                v = _cell_scalar_value(sheet_cells[a_ref])
                if v is not None:
                    return str(v).strip()

    return _lookup(a_ref)


def _append_cell_record(
    out: list[CellRecord],
    seen: set[tuple[str, str]],
    sheet: str,
    cell_ref: str,
    raw: object,
    cells_lookup: dict,
) -> None:
    cell_up = cell_ref.strip().upper()
    if not _CELL_ADDRESS_RE.match(cell_up):
        return
    key = (sheet, cell_up)
    if key in seen:
        return
    seen.add(key)
    row_label = ""
    if isinstance(raw, dict):
        row_label = str(raw.get("label") or raw.get("name") or "").strip()
    if not row_label:
        row_label = _row_label_for_cell(cells_lookup, sheet, cell_up)
    out.append(
        CellRecord(
            sheet=sheet,
            cell=cell_up,
            row_label=row_label,
            value=_cell_scalar_value(raw),
        )
    )


def extract_custom_cells(parsed_data: dict | None) -> list[CellRecord]:
    """从 working_paper.parsed_data 提取自定义底稿单元格坐标。

    兼容：
    - 嵌套：``html_data[sheet].cells[cell]``（标量或 ``{value,v,label,name}``）
    - 扁平：``parsed_data[sheet][field]``（field 为单元格地址）
    - 顶层 ``cells`` 扁平/嵌套（与 note_wp_data_resolver 对齐）

    None / {} / 结构异常 → 返回 []，不抛异常。
    """
    if not parsed_data or not isinstance(parsed_data, dict):
        return []

    records: list[CellRecord] = []
    seen: set[tuple[str, str]] = set()
    cells_lookup: dict = {}

    if isinstance(parsed_data.get("cells"), dict):
        cells_lookup.update(parsed_data["cells"])

    html_data = parsed_data.get("html_data")
    if isinstance(html_data, dict):
        nested_store: dict[str, dict] = {}
        for sheet_name, sheet_data in html_data.items():
            if not isinstance(sheet_name, str) or not sheet_name:
                continue
            if not isinstance(sheet_data, dict):
                continue
            sheet_cells = sheet_data.get("cells")
            if isinstance(sheet_cells, dict):
                nested_store[sheet_name] = sheet_cells
                # 须在遍历 cells 前写入，供 _row_label_for_cell 读同行 A 列
                cells_lookup["__html_sheet_cells__"] = nested_store
                for cell_ref, raw in sheet_cells.items():
                    if isinstance(cell_ref, str):
                        _append_cell_record(
                            records, seen, sheet_name, cell_ref, raw, cells_lookup
                        )

    for sheet_name, sheet_data in parsed_data.items():
        if sheet_name in _PARSED_DATA_META_KEYS:
            continue
        if not isinstance(sheet_name, str) or not sheet_name:
            continue
        if not isinstance(sheet_data, dict):
            continue
        for field, raw in sheet_data.items():
            if isinstance(field, str) and _CELL_ADDRESS_RE.match(field.strip().upper()):
                _append_cell_record(
                    records, seen, sheet_name, field, raw, cells_lookup
                )

    return records


async def _build_custom_wp_cell_entries(
    db, project_id: str, year: int
) -> list[AddressEntry]:
    """从 working_paper.parsed_data 构建自定义底稿 WP 域条目。"""
    import uuid as _uuid

    import sqlalchemy as sa

    from app.models.workpaper_models import WorkingPaper, WpIndex

    entries: list[AddressEntry] = []
    try:
        pid = _uuid.UUID(str(project_id))
    except (ValueError, TypeError):
        return entries

    try:
        rows = (
            await db.execute(
                sa.select(
                    WorkingPaper.parsed_data,
                    WpIndex.wp_code,
                    WpIndex.wp_name,
                )
                .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
                .where(
                    WorkingPaper.project_id == pid,
                    WorkingPaper.is_deleted == False,  # noqa: E712
                    WpIndex.is_deleted == False,  # noqa: E712
                )
            )
        ).all()
    except Exception as e:
        logger.warning("_build_custom_wp_cell_entries query error: %s", e)
        return entries

    for parsed_data, wp_code, wp_name in rows:
        if not wp_code:
            continue
        try:
            for rec in extract_custom_cells(parsed_data):
                uri = build_uri("wp", wp_code, path=rec.cell)
                wp_display = (wp_name or wp_code).strip()
                label_parts = [f"底稿 > {wp_code} {wp_display}"]
                if rec.row_label:
                    label_parts.append(f"> {rec.row_label}")
                label_parts.append(f"（{rec.cell}）")
                entries.append(
                    AddressEntry(
                        uri=uri,
                        domain="wp",
                        source=wp_code,
                        path=rec.cell,
                        cell=rec.cell,
                        label=" ".join(label_parts),
                        wp_code=wp_code,
                        formula_ref=f"WP('{wp_code}','{rec.cell}')",
                        jump_route=build_jump_route(uri, project_id, year),
                        tags=["底稿", "自定义", rec.row_label] if rec.row_label else ["底稿", "自定义"],
                    )
                )
        except Exception as e:
            logger.warning(
                "custom wp cell entries skip wp_code=%s: %s", wp_code, e
            )
            continue

    return entries


async def build_workpaper_entries(db, project_id: str, year: int) -> list[AddressEntry]:
    """从底稿映射构建地址条目"""
    import json
    from pathlib import Path

    entries = []
    try:
        mapping_file = Path(__file__).parent.parent.parent / 'data' / 'wp_account_mapping.json'
        if not mapping_file.exists():
            return entries

        with open(mapping_file, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)

        mappings = data.get('mappings', [])
        columns = ['审定数', '未审数', 'AJE调整', 'RJE调整', '期初', '期末']

        for m in mappings:
            wp_code = m.get('wp_code', '')
            wp_name = m.get('wp_name', '')
            for col in columns:
                uri = build_uri('wp', wp_code, path=col)
                entries.append(AddressEntry(
                    uri=uri,
                    domain='wp',
                    source=wp_code,
                    path='',
                    cell=col,
                    label=f"底稿 > {wp_code} {wp_name} > {col}",
                    wp_code=wp_code,
                    account_code=','.join(m.get('account_codes', [])),
                    formula_ref=f"WP('{wp_code}','{col}')",
                    jump_route=build_jump_route(uri, project_id, year),
                    tags=['底稿', m.get('cycle', ''), wp_name],
                ))
    except Exception as e:
        logger.warning(f"build_workpaper_entries error: {e}")

    # 从精细化规则的 cross_references 注册交叉引用条目
    try:
        fine_rules_dir = Path(__file__).parent.parent.parent / 'data' / 'wp_fine_rules'
        if fine_rules_dir.exists():
            for fr_file in fine_rules_dir.glob('*.json'):
                with open(fr_file, 'r', encoding='utf-8-sig') as f:
                    fr = json.load(f)
                wp_code = fr.get('wp_code', '')
                wp_name = fr.get('wp_name', fr.get('name', ''))
                for xref in fr.get('cross_references', []):
                    from_ref = xref.get('from', '')
                    to_ref = xref.get('to', '')
                    desc = xref.get('description', '')
                    if not from_ref or not to_ref:
                        continue
                    uri = build_uri('wp', wp_code, path='xref', cell=from_ref)
                    entries.append(AddressEntry(
                        uri=uri,
                        domain='wp',
                        source=wp_code,
                        path='xref',
                        cell=from_ref,
                        label=f"交叉引用 > {wp_code} {wp_name} > {desc}",
                        wp_code=wp_code,
                        formula_ref=to_ref,
                        jump_route=build_jump_route(uri, project_id, year),
                        tags=['交叉引用', wp_code, wp_name],
                    ))
    except Exception as e:
        logger.warning(f"build_workpaper_entries xref error: {e}")

    try:
        custom_entries = await _build_custom_wp_cell_entries(db, project_id, year)
        entries.extend(custom_entries)
    except Exception as e:
        logger.warning(f"build_workpaper_entries custom cells error: {e}")

    return entries


# ═══════════════════════════════════════════
# 统一注册表服务
# ═══════════════════════════════════════════

import time as _time


@dataclass
class _CacheSlot:
    """缓存槽：按域分别存储，支持独立失效"""
    entries: list[AddressEntry]
    built_at: float  # time.time()
    domain: str


class AddressRegistryService:
    """统一地址坐标注册表

    缓存维度：project_id × year × template_type × domain
    - 切换单位 → project_id 变化 → 全部重建
    - 切换年度 → year 变化 → 试算表/报表重建（附注模板不变）
    - 切换国企/上市 → template_type 变化 → 附注重建（报表/试算表不变）
    - 数据变更 → 按 domain 精准失效（调整分录只失效 tb 域）
    """

    # 缓存TTL（秒）：不同域数据变化频率不同
    _TTL: dict[str, int] = {
        'report': 300,   # 报表配置较稳定，5分钟
        'tb': 60,        # 试算表随调整分录变化，1分钟
        'note': 300,     # 附注模板较稳定，5分钟
        'wp': 120,       # 底稿映射中等频率，2分钟
        'aux': 60,       # 辅助余额随导入变化，1分钟
    }

    # 缓存上限（防止内存泄漏）
    _MAX_CACHE_SLOTS = 500

    # Redis key 前缀
    _REDIS_PREFIX = "addr_reg:"

    def __init__(self):
        # key = "project_id:year:template_type:domain"
        self._slots: dict[str, _CacheSlot] = {}

    # ------------------------------------------------------------------
    # Redis L2 helpers
    # ------------------------------------------------------------------

    async def _get_redis(self):
        """获取 Redis 客户端（降级返回 None）"""
        from app.core.redis import get_redis
        return await get_redis()

    def _redis_key(self, slot_key: str) -> str:
        """Redis key = prefix + slot_key"""
        return f"{self._REDIS_PREFIX}{slot_key}"

    async def _redis_get(self, slot_key: str) -> list[AddressEntry] | None:
        """从 Redis L2 读取缓存，命中反序列化返回，未命中/异常返回 None"""
        redis = await self._get_redis()
        if redis is None:
            return None
        try:
            raw = await redis.get(self._redis_key(slot_key))
            if raw is None:
                return None
            items = json.loads(raw)
            return [AddressEntry(**item) for item in items]
        except Exception as e:
            logger.warning("address_registry Redis L2 get failed (key=%s): %s", slot_key, e)
            return None

    async def _redis_set(self, slot_key: str, entries: list[AddressEntry], domain: str) -> None:
        """回写 Redis L2（TTL 对齐按域 TTL）"""
        redis = await self._get_redis()
        if redis is None:
            return
        try:
            serialized = json.dumps(
                [asdict(e) for e in entries], ensure_ascii=False
            )
            ttl = self._TTL.get(domain, 120)
            await redis.set(self._redis_key(slot_key), serialized, ex=ttl)
        except Exception as e:
            logger.warning("address_registry Redis L2 set failed (key=%s): %s", slot_key, e)

    async def _redis_delete(self, slot_key: str) -> None:
        """删除单个 Redis L2 key"""
        redis = await self._get_redis()
        if redis is None:
            return
        try:
            await redis.delete(self._redis_key(slot_key))
        except Exception as e:
            logger.warning("address_registry Redis L2 delete failed (key=%s): %s", slot_key, e)

    async def _redis_delete_many(self, slot_keys: list[str]) -> None:
        """批量删除 Redis L2 keys"""
        if not slot_keys:
            return
        redis = await self._get_redis()
        if redis is None:
            return
        try:
            redis_keys = [self._redis_key(k) for k in slot_keys]
            await redis.delete(*redis_keys)
        except Exception as e:
            logger.warning("address_registry Redis L2 delete_many failed: %s", e)

    async def _redis_flush_all(self) -> None:
        """删除所有 addr_reg:* keys"""
        redis = await self._get_redis()
        if redis is None:
            return
        try:
            cursor = 0
            while True:
                cursor, keys = await redis.scan(
                    cursor=cursor, match=f"{self._REDIS_PREFIX}*", count=200
                )
                if keys:
                    await redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("address_registry Redis L2 flush_all failed: %s", e)

    def _slot_key(self, project_id: str, year: int,
                  template_type: str, domain: str) -> str:
        return f"{project_id}:{year}:{template_type}:{domain}"

    def _is_expired(self, slot: _CacheSlot) -> bool:
        ttl = self._TTL.get(slot.domain, 120)
        return (_time.time() - slot.built_at) > ttl

    def _evict_if_needed(self):
        """LRU淘汰：超过上限时删除最旧的槽"""
        if len(self._slots) <= self._MAX_CACHE_SLOTS:
            return
        sorted_keys = sorted(
            self._slots.keys(),
            key=lambda k: self._slots[k].built_at
        )
        # 删除最旧的20%
        to_remove = sorted_keys[:len(sorted_keys) // 5 + 1]
        for k in to_remove:
            del self._slots[k]

    async def _get_domain(self, db, project_id: str, year: int,
                          template_type: str, domain: str) -> list[AddressEntry]:
        """获取单个域的地址条目（L1 内存 → L2 Redis → DB 构建）"""
        key = self._slot_key(project_id, year, template_type, domain)

        # L1: 内存缓存
        slot = self._slots.get(key)
        if slot and not self._is_expired(slot):
            return slot.entries

        # L2: Redis 缓存
        redis_entries = await self._redis_get(key)
        if redis_entries is not None:
            # 回填 L1
            self._evict_if_needed()
            self._slots[key] = _CacheSlot(
                entries=redis_entries, built_at=_time.time(), domain=domain
            )
            return redis_entries

        # DB 构建
        entries: list[AddressEntry] = []
        if domain == 'report':
            entries = await build_report_entries(db, project_id, year)
        elif domain == 'tb':
            entries = await build_trial_balance_entries(db, project_id, year)
        elif domain == 'note':
            entries = await build_note_entries(db, project_id, year, template_type)
        elif domain == 'wp':
            entries = await build_workpaper_entries(db, project_id, year)

        # 回写 L1
        self._evict_if_needed()
        self._slots[key] = _CacheSlot(
            entries=entries, built_at=_time.time(), domain=domain
        )

        # 回写 L2 Redis
        await self._redis_set(key, entries, domain)

        return entries

    async def get_all(self, db, project_id: str, year: int,
                      template_type: str = 'soe') -> list[AddressEntry]:
        """获取项目所有可引用地址（按域分别缓存）"""
        all_entries: list[AddressEntry] = []
        for domain in ('report', 'tb', 'note', 'wp'):
            all_entries.extend(
                await self._get_domain(db, project_id, year, template_type, domain)
            )
        return all_entries

    async def get_domain(self, db, project_id: str, year: int,
                         template_type: str, domain: str) -> list[AddressEntry]:
        """获取单个域的地址（供前端按域加载，减少首次加载量）"""
        return await self._get_domain(db, project_id, year, template_type, domain)

    async def search(self, db, project_id: str, year: int,
                     keyword: str = '', domain: str = '',
                     template_type: str = 'soe',
                     limit: int = 100) -> list[AddressEntry]:
        """搜索地址（支持关键词+域过滤）"""
        if domain:
            # 只加载指定域，更快
            results = await self._get_domain(db, project_id, year, template_type, domain)
        else:
            results = await self.get_all(db, project_id, year, template_type)

        if keyword:
            kw = keyword.lower()
            results = [e for e in results if
                       kw in e.label.lower() or
                       kw in e.uri.lower() or
                       kw in e.formula_ref.lower() or
                       kw in e.account_code.lower() or
                       kw in e.row_code.lower()]

        return results[:limit]

    async def resolve(self, db, project_id: str, year: int,
                      uri: str, template_type: str = 'soe') -> Optional[AddressEntry]:
        """解析单个URI为地址条目"""
        # 从URI推断域，只加载对应域
        parts = parse_uri(uri)
        if parts:
            domain_entries = await self._get_domain(
                db, project_id, year, template_type, parts['domain']
            )
            for e in domain_entries:
                if e.uri == uri:
                    return e
        # 降级全量搜索
        all_entries = await self.get_all(db, project_id, year, template_type)
        for e in all_entries:
            if e.uri == uri:
                return e
        return None

    async def validate_formula_refs(self, db, project_id: str, year: int,
                                    formula: str,
                                    template_type: str = 'soe') -> list[dict]:
        """校验公式中所有引用的地址是否有效"""
        # 按需加载涉及的域
        needed_domains: set[str] = set()
        for fn_name in _FORMULA_PATTERNS:
            if fn_name in ('TB', 'SUM_TB', 'PREV'):
                if fn_name in formula:
                    needed_domains.add('tb')
            elif fn_name in ('ROW', 'SUM_ROW', 'REPORT'):
                if fn_name in formula:
                    needed_domains.add('report')
            elif fn_name == 'NOTE':
                if 'NOTE(' in formula:
                    needed_domains.add('note')
            elif fn_name == 'WP':
                if 'WP(' in formula:
                    needed_domains.add('wp')
            elif fn_name == 'AUX':
                if 'AUX(' in formula:
                    needed_domains.add('aux')

        uri_set: set[str] = set()
        for d in needed_domains:
            entries = await self._get_domain(db, project_id, year, template_type, d)
            uri_set.update(e.uri for e in entries)

        issues = []
        for fn_name, pattern in _FORMULA_PATTERNS.items():
            for m in pattern.finditer(formula):
                ref_text = m.group(0)
                uri = formula_ref_to_uri(ref_text)
                if uri and uri not in uri_set:
                    issues.append({
                        'ref': ref_text,
                        'uri': uri,
                        'status': 'not_found',
                        'message': f'引用地址 {uri} 在当前项目中不存在',
                    })
        return issues

    def invalidate(self, project_id: str, year: int = 0,
                   domain: str = '', template_type: str = ''):
        """精准失效缓存（L1 内存 + L2 Redis 同步删除）

        参数组合：
        - invalidate(pid)                    → 该项目全部缓存
        - invalidate(pid, year=2025)         → 该项目该年度全部域
        - invalidate(pid, domain='tb')       → 该项目所有年度的试算表域
        - invalidate(pid, year=2025, domain='tb') → 精准到单个槽
        - invalidate(pid, template_type='listed') → 该项目该模板类型
        """
        to_remove = []
        for key in self._slots:
            parts = key.split(':')  # project_id:year:template_type:domain
            if len(parts) != 4:
                continue
            k_pid, k_year, k_tpl, k_dom = parts

            if k_pid != project_id:
                continue
            if year and k_year != str(year):
                continue
            if domain and k_dom != domain:
                continue
            if template_type and k_tpl != template_type:
                continue
            to_remove.append(key)

        for k in to_remove:
            del self._slots[k]

        # 异步删 Redis L2（fire-and-forget via _invalidate_redis_keys）
        self._pending_redis_invalidations = to_remove

        logger.debug(f"address_registry invalidate: removed {len(to_remove)} slots "
                     f"(pid={project_id}, year={year}, domain={domain}, tpl={template_type})")

    async def invalidate_async(self, project_id: str, year: int = 0,
                               domain: str = '', template_type: str = ''):
        """精准失效缓存（L1 内存 + L2 Redis 同步删除）— async 版本

        与 invalidate 相同逻辑，但同步删除 Redis keys。
        推荐在 async 上下文中使用此方法。
        """
        to_remove = []
        for key in list(self._slots.keys()):
            parts = key.split(':')
            if len(parts) != 4:
                continue
            k_pid, k_year, k_tpl, k_dom = parts

            if k_pid != project_id:
                continue
            if year and k_year != str(year):
                continue
            if domain and k_dom != domain:
                continue
            if template_type and k_tpl != template_type:
                continue
            to_remove.append(key)

        for k in to_remove:
            del self._slots[k]

        # 同步删 Redis L2
        await self._redis_delete_many(to_remove)

        logger.debug(f"address_registry invalidate_async: removed {len(to_remove)} slots "
                     f"(pid={project_id}, year={year}, domain={domain}, tpl={template_type})")

    def invalidate_all(self):
        """清空全部缓存 L1（重启/全量刷新时用）

        注意：同步方法仅清 L1 内存。如需同步清 Redis L2，
        使用 invalidate_all_async()。
        """
        count = len(self._slots)
        self._slots.clear()
        logger.info(f"address_registry invalidate_all: cleared {count} L1 slots")

    async def invalidate_all_async(self):
        """清空全部缓存 L1 + L2 Redis（重启/全量刷新时用）"""
        count = len(self._slots)
        self._slots.clear()
        await self._redis_flush_all()
        logger.info(f"address_registry invalidate_all_async: cleared {count} L1 slots + Redis L2")

    async def get_stats(self, db, project_id: str, year: int,
                        template_type: str = 'soe') -> dict:
        """获取注册表统计"""
        entries = await self.get_all(db, project_id, year, template_type)
        by_domain: dict[str, int] = {}
        for e in entries:
            by_domain[e.domain] = by_domain.get(e.domain, 0) + 1

        # 缓存统计
        cache_stats = {
            'total_slots': len(self._slots),
            'project_slots': sum(1 for k in self._slots if k.startswith(f"{project_id}:")),
            'expired_slots': sum(1 for s in self._slots.values() if self._is_expired(s)),
        }

        return {
            'total': len(entries),
            'by_domain': by_domain,
            'domains': list(by_domain.keys()),
            'cache': cache_stats,
        }


def _report_type_short(report_type: str) -> str:
    """将长报表类型名转为短代码"""
    mapping = {
        'balance_sheet': 'BS', 'income_statement': 'IS',
        'cash_flow_statement': 'CFS', 'equity_statement': 'EQ',
        'cash_flow_supplement': 'CFSS', 'impairment_provision': 'IMP',
    }
    return mapping.get(report_type, report_type.upper()[:3])


# 全局单例
address_registry = AddressRegistryService()
