"""底稿表头填充服务 — 生成底稿时自动填写表头信息和交叉索引

致同标准底稿表头包含：
- 事务所名称（致同会计师事务所）
- 编制单位（client_name）
- 审计期间（audit_period_start ~ audit_period_end）
- 底稿名称
- 索引号（wp_code）
- 编制人 / 编制日期
- 复核人 / 复核日期
- 交叉索引（关联底稿编号和名称）
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.workpaper_models import WorkingPaper, WpIndex

_logger = logging.getLogger(__name__)

# 致同标准底稿表头区域定义（行号从1开始）
# 实际模板中表头位置可能不同，这里定义兜底的空白底稿表头布局
_HEADER_LAYOUT = {
    "firm_name": {"row": 1, "col": 1, "value": "致同会计师事务所（特殊普通合伙）"},
    "client_label": {"row": 2, "col": 1, "value": "编制单位："},
    "client_name": {"row": 2, "col": 2},
    "period_label": {"row": 2, "col": 4, "value": "审计期间："},
    "period_value": {"row": 2, "col": 5},
    "wp_name_label": {"row": 3, "col": 1, "value": "底稿名称："},
    "wp_name_value": {"row": 3, "col": 2},
    "index_label": {"row": 3, "col": 4, "value": "索引号："},
    "index_value": {"row": 3, "col": 5},
    "preparer_label": {"row": 4, "col": 1, "value": "编制人："},
    "preparer_value": {"row": 4, "col": 2},
    "prep_date_label": {"row": 4, "col": 3, "value": "日期："},
    "prep_date_value": {"row": 4, "col": 4},
    "reviewer_label": {"row": 4, "col": 5, "value": "复核人："},
    "reviewer_value": {"row": 4, "col": 6},
    "rev_date_label": {"row": 4, "col": 7, "value": "日期："},
    "rev_date_value": {"row": 4, "col": 8},
    "xref_label": {"row": 5, "col": 1, "value": "交叉索引："},
    "xref_value": {"row": 5, "col": 2},
}

# 审计阶段中文名
_CYCLE_NAMES = {
    "B": "准备阶段（初步业务活动/风险评估）",
    "C": "准备阶段（风险应对）",
    "D": "实施阶段（销售与收款循环）",
    "E": "实施阶段（货币资金循环）",
    "F": "实施阶段（采购与存货循环）",
    "G": "实施阶段（投资循环）",
    "H": "实施阶段（固定资产循环）",
    "I": "实施阶段（无形资产循环）",
    "J": "实施阶段（薪酬循环）",
    "K": "实施阶段（管理费用与其他循环）",
    "L": "实施阶段（债务循环）",
    "M": "实施阶段（权益循环）",
    "N": "实施阶段（税金循环）",
    "A": "完成阶段",
    "S": "特殊事项",
    "Q": "关联方",
}


#: 多页底稿的表头页：各页表头格是 ``=底稿目录!A2`` 这类引用，表头只有填在这一页各页才显示得出来。
#: 名字不一（底稿目录 / 表头（请先填写） / 表头 / 目录），A1 都是同一句「底稿开列时，可先在以下单元格填写有关内容…」
_HUB_SHEET = "底稿目录"
_HUB_A1_PREFIX = "底稿开列时"
#: 在模板里找表头标签的范围（前 10 行、前 12 列）
_HEADER_ROWS, _HEADER_COLS = 10, 12
_BLANK_RE = re.compile(r"[\s\u3000]+")
_COLON_RE = re.compile(r"[：:]")
_LABEL_RE = re.compile(r"^(?P<label>[^：:]{1,16})[：:](?P<rest>.*)$", re.S)
#: 整格就是一个跨页单格引用：``=底稿目录!A2`` / ``='表头（请先填写）'!$A$2``（外部链接 ``=[4]底稿目录!A2``、复合公式不算）
_REF_RE = re.compile(
    r"^=\s*(?:'(?P<quoted>(?:[^']|'')+)'|(?P<plain>[^'!\[\]=(),+\-*/&\s]+))!\$?(?P<col>[A-Z]{1,3})\$?(?P<row>\d+)\s*$"
)
#: 引用另一个工作簿的格：``=[4]底稿目录!$A$2`` / ``='[1]表头'!A2``。模板从别的文件拆出来时留下的，被引用的那一页不在本册，
#: 打开时只显示模板里缓存的示例（「会计期间：202X年度」）
_EXTERNAL_REF_RE = re.compile(r"^=\s*'?\[\d+\]")
#: 整格就是一个外部链接单格引用（复合公式不算），拆出页签名与地址
_EXTERNAL_SINGLE_REF_RE = re.compile(
    r"^=\s*(?:'\[\d+\](?P<quoted>(?:[^']|'')+)'|\[\d+\](?P<plain>[^'!\[\]=(),+\-*/&\s]+))"
    r"!(?P<addr>\$?[A-Z]{1,3}\$?\d+)\s*$"
)
#: 底稿索引号的写法（F2-18 / F2-21A / A1-14-1）：外部引用缓存的是该页自己的索引
_WP_CODE_TEXT_RE = re.compile(r"^[A-Z]{1,2}\d{1,2}(?:-\d+)*[A-Z]?(?:-\d+)*[A-Z]?$")
_EXTERNAL_HEADER_REASON = "表头引用了其他模板文件（外部链接），编制单位 / 期间没法自动填写，请在底稿里手工填写"
_SKIPPED_HEADER_REASON = "表头有 {n} 格是共享公式，没法自动填写，请在底稿里手工填写"

#: 表头标签（去掉空白后冒号前的部分，按全名匹配）→ 填哪一项。
#: 🔴 只认带冒号的标签：表格列头「索引号」「复核人」「工作底稿索引」不带冒号。原先按「以关键词结尾」匹配、
#:    不要求冒号 ⇒ 把底稿编码写进程序表表头行「索引号」列头右边那一格。
_LABEL_FIELDS: dict[str, str] = {
    "编制单位": "client", "被审计单位": "client", "被审计单位名称": "client", "客户名称": "client",
    "审计期间": "period", "会计期间": "period", "截止日/会计期间": "period",
    "截止日": "cutoff", "截止日期": "cutoff",
    "底稿名称": "wp_name",
    "索引号": "code", "索引": "code",
    "交叉索引": "xref",
    "编制人": "preparer", "复核人": "reviewer",
}
#: 冒号后已有文字也换成本项目值的项：模板里「被审计单位：ABC公司」「会计期间：201X年度」「截止日：202X年12月31日」
#: 都是示例；索引号冒号后是模板自己的（各页不同），编制人 / 复核人生成时没有值，都不动
_REPLACE_INLINE = frozenset({"client", "period", "cutoff"})
#: 外部引用缓存里冒号后只会是示例的标签（「编制人：张XX」「复核日期：2025-5-1」）：改成静态文字时去掉示例
_EXAMPLE_REST_LABELS = frozenset({"编制人", "复核人", "编制日期", "复核日期", "日期"})
#: 认作表头标签的全部标签（外部引用归类用）
_HEADER_LABELS = frozenset(_LABEL_FIELDS) | _EXAMPLE_REST_LABELS


def get_cross_ref_text(wp_code: str, mapping_data: list[dict]) -> str:
    """根据底稿编码生成交叉索引文本

    规则：
    1. 同循环的其他底稿（如 E1-1 引用 E1-2、E1-3）
    2. 通过 wp_account_mapping 关联的底稿
    3. 通用引用（审定表引用程序表、程序表引用审定表）
    """
    cycle = wp_code[0] if wp_code else ""
    refs = []

    # 同循环底稿
    for m in mapping_data:
        if m.get("cycle") == cycle and m.get("wp_code") != wp_code:
            refs.append(f"{m['wp_code']}({m.get('wp_name', '')})")

    # 通用交叉引用
    if wp_code.endswith("-1") or "审定表" in str(mapping_data):
        # 审定表通常引用程序表
        prog_code = wp_code.split("-")[0] if "-" in wp_code else wp_code
        refs.append(f"{prog_code}(程序表)")

    # 限制长度
    if len(refs) > 5:
        refs = refs[:5] + [f"等共{len(refs)}项"]

    return "、".join(refs) if refs else ""


async def fill_workpaper_header(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
    file_path: str,
    wp_code: str,
    wp_name: str,
    cycle: str | None = None,
    assigned_to_name: str | None = None,
    reviewer_name: str | None = None,
    is_custom: bool = False,
    from_template: bool = True,
) -> dict[str, Any]:
    """填充底稿表头信息

    对于从模板复制的底稿（``from_template``）：在活动页与「底稿目录」页找表头标签填值（见 ``_fill_header_labels``），
    找不到可填的位置就保持模板原样 —— 不写标准布局（会盖掉模板第 1~5 行的内容），也不重存文件。
    对于空白底稿（``from_template=False``，找不到模板时建的空白册）：找不到标签就按标准布局写入表头。
    对于自定义底稿(is_custom=True)：按标准布局写入表头。

    返回 ``status``：``ok``（``filled`` 列出写了哪些格，可能为空 —— 模板本来就没有表头）/ ``partial``（表头靠外部链接
    显示、填不进去，``message`` 写明）/ ``error``（``message`` 写明原因）。后两种调用方要回报（生成回执 header_failures）。

    通用规则（适用于所有底稿）：
    1. 编制单位 = Project.client_name
    2. 审计期间 = audit_period_start ~ audit_period_end
    3. 索引号 = wp_code
    4. 底稿名称 = wp_name
    5. 交叉索引 = 同循环关联底稿自动生成
    6. 审计阶段 = 根据循环前缀映射中文名
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    except ImportError:
        return {"status": "error", "message": "openpyxl 未安装"}

    # 返回的 message 会进生成回执给用户看（header_failures）：只写原因，路径与异常细节记日志
    fp = Path(file_path)
    if not fp.exists():
        _logger.warning("fill_header: wp=%s 文件不存在 %s", wp_id, fp)
        return {"status": "error", "message": "底稿文件不存在"}

    # 获取项目信息
    proj = (await db.execute(
        sa.select(Project).where(Project.id == project_id)
    )).scalar_one_or_none()

    client_name = proj.client_name if proj else "未知单位"
    ws_data = proj.wizard_state or {} if proj else {}
    basic_info = ws_data.get("steps", {}).get("basic_info", {}).get("data", {})
    from app.services.project_audit_year import resolve_project_audit_year
    audit_year = resolve_project_audit_year(proj) if proj else None
    if audit_year is None:
        audit_year = (basic_info.get("audit_year") if basic_info else None)
    if audit_year is None:
        return {"status": "error", "message": "未设置审计年度，请先在项目基本信息中填写"}
    period_start = proj.audit_period_start if proj else None
    period_end = proj.audit_period_end if proj else None

    if not period_start:
        period_start = date(audit_year, 1, 1)
    if not period_end:
        period_end = date(audit_year, 12, 31)

    period_text = f"{period_start.strftime('%Y年%m月%d日')}至{period_end.strftime('%Y年%m月%d日')}"

    # 加载交叉索引数据
    mapping_path = Path(__file__).parent.parent.parent / "data" / "wp_account_mapping.json"
    mapping_data = []
    if mapping_path.exists():
        try:
            with open(mapping_path, "r", encoding="utf-8-sig") as f:
                mapping_data = json.load(f).get("mappings", [])
        except Exception as e:
            _logger.warning("加载 wp_account_mapping.json 失败: %s", e)

    xref_text = get_cross_ref_text(wp_code, mapping_data)

    # 打开 Excel：只用来读与规划写哪些格；模板底稿落盘只改目标格（xlsx_cell_patch），不整册重存
    try:
        wb = openpyxl.load_workbook(str(fp))
        # 外部链接格的显示值只在缓存里（归类要看它）；表头区没有外部引用就不必再读一遍。
        # 按公式判，不按外部链接部件判：N5 的「=[4]底稿目录!A2」没有对应的链接部件（链接已断）
        wbv = openpyxl.load_workbook(str(fp), data_only=True) if _header_has_external_refs(wb) else None
    except Exception:
        _logger.warning("fill_header: wp=%s 打开 %s 失败", wp_id, fp, exc_info=True)
        return {"status": "error", "message": "打开底稿文件失败"}

    ws = wb.active
    values = {
        "client": client_name, "period": period_text, "cutoff": period_end.strftime("%Y年%m月%d日"),
        "wp_name": wp_name, "code": wp_code, "xref": xref_text,
        "preparer": assigned_to_name or "", "reviewer": reviewer_name or "",
    }

    # 自定义底稿(is_custom)强制写入标准表头；其余先把表头外部引用归类改写，再按模板表头标签填（见 _fill_workbook_header）
    ext_edits, filled = ([], []) if is_custom else _fill_workbook_header(wb, values, wbv)
    # 活动页表头仍靠外部链接显示、又没有别处把客户名填进活动页看得到的位置 ⇒ 不算成功，回执里写明（status=partial）
    issue = None if is_custom or not from_template else _unfillable_external_header(wb, wbv, filled)

    standard_layout = is_custom or (not filled and not ext_edits and not from_template)
    if standard_layout:
        # 空白底稿或自定义底稿：按标准布局写入表头（这两种册本就由 openpyxl 生成，整册存无损）
        if fp.suffix.lower() == ".xlsm":
            wb.close()
            return {"status": "error", "message": "含宏的底稿不按标准布局写表头"}
        _write_standard_header(
            ws, client_name, period_text, wp_name, wp_code,
            cycle, assigned_to_name, reviewer_name, xref_text,
        )
        try:
            wb.save(str(fp))
        except Exception:
            _logger.warning("fill_header: wp=%s 保存 %s 失败", wp_id, fp, exc_info=True)
            return {"status": "error", "message": "保存底稿文件失败"}
        finally:
            wb.close()
        _logger.info("fill_header: wp=%s code=%s client=%s 标准布局", wp_id, wp_code, client_name)
        return {"status": "partial" if issue else "ok", "message": issue,
                "filled": [], "standard_layout": True, "filled_by_search": False}

    if not filled and not ext_edits:
        # 模板里没有可填的表头位置：保持原样
        wb.close()
        _logger.info("fill_header: wp=%s code=%s 模板表头里没有可填写的位置，保持原样（%s）", wp_id, wp_code, issue or "-")
        return {"status": "partial" if issue else "ok", "message": issue,
                "filled": [], "standard_layout": False, "filled_by_search": False}

    from app.services.xlsx_cell_patch import patch_cells

    patches = _plan_cell_patches(wb, ext_edits + filled)
    active_title = ws.title
    wb.close()
    try:
        outcome = patch_cells(fp, patches)
    except Exception:
        _logger.warning("fill_header: wp=%s 保存 %s 失败", wp_id, fp, exc_info=True)
        return {"status": "error", "message": "保存底稿文件失败"}
    skipped = {(p.sheet, p.cell) for p, _reason in outcome.skipped}
    if skipped:
        _logger.warning("fill_header: wp=%s code=%s 跳过 %d 格：%s", wp_id, wp_code, len(skipped),
                        [(p.sheet, p.cell, r) for p, r in outcome.skipped][:10])
        filled = [f for f in filled if (f["sheet"], f["cell"]) not in skipped]
        ext_edits = [f for f in ext_edits if (f["sheet"], f["cell"]) not in skipped]
        on_active = sum(1 for s, _c in skipped if s == active_title)
        if on_active and issue is None:
            issue = _SKIPPED_HEADER_REASON.format(n=on_active)

    _logger.info("fill_header: wp=%s code=%s client=%s filled=%d external=%d calc_chain_removed=%s",
                 wp_id, wp_code, client_name, len(filled), len(ext_edits), outcome.calc_chain_removed)
    return {"status": "partial" if issue else "ok", "message": issue,
            "filled": ext_edits + filled, "standard_layout": False, "filled_by_search": bool(filled)}


async def fill_generated_workpaper_header(
    db: AsyncSession, *, project_id: UUID, wp_id: UUID, path: Path, wp_code: str, wp_name: str,
    cycle: str | None, from_template: bool,
) -> str | None:
    """生成底稿后填表头，返回没填上的原因（None = 填好了，或模板本来就没有表头），调用方写进回执 / 日志。

    动 xlsx 与 xlsm（只改目标格，宏与数据验证原样保留，见 ``xlsx_cell_patch``；docx 不是工作簿）；没填上不阻断生成。
    原先调用方各自 try/except 只记 warning、返回的错误状态也没人看 ⇒ 表头静默缺失（按编码生成、准则转换建底稿两处）。
    """
    if path.suffix.lower() not in (".xlsx", ".xlsm"):
        return None
    try:
        res = await fill_workpaper_header(
            db=db, project_id=project_id, wp_id=wp_id, file_path=str(path), wp_code=wp_code,
            wp_name=wp_name, cycle=cycle, from_template=from_template,
        )
    except Exception:
        _logger.warning("fill_header: wp=%s code=%s 填写表头出错", wp_id, wp_code, exc_info=True)
        return "填写表头时出错，详见服务日志"
    if (res or {}).get("status") == "ok":
        return None
    return (res or {}).get("message") or "原因未知"


def describe_header_failures(header_failures: list[dict[str, str]]) -> str:
    """回执 message 的一段：「N 个底稿表头未填上：J2A（原因）、…」（最多列 5 个）；没有返回空串。"""
    if not header_failures:
        return ""
    shown = "、".join(f"{h['wp_code']}（{h['reason']}）" for h in header_failures[:5])
    return f"{len(header_failures)} 个底稿表头未填上：{shown}{' 等' if len(header_failures) > 5 else ''}"


def _merged_range_at(ws, row: int, col: int):
    """(row, col) 所在的合并区域；不在任何合并区域里返回 None。"""
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
            return rng
    return None


def _writable_cell(ws, row: int, col: int):
    """可写的格：落在合并区域里就取该区域左上角格。

    🔴 openpyxl 里合并区域除左上角外都是 ``MergedCell``，读值恒为 None、写值抛
    ``AttributeError: 'MergedCell' object attribute 'value' is read-only`` —— 模板表头的标签 / 值区
    多半是合并格，原先直接写右邻格，一碰合并格整份表头就因异常没填（调用方只记 warning）。
    """
    rng = _merged_range_at(ws, row, col)
    if rng is None:
        return ws.cell(row=row, column=col)
    return ws.cell(row=rng.min_row, column=rng.min_col)


def _looks_like_label(value: Any) -> bool:
    """另一个表头标签（「编制人：」「索引号：A10」「页  次：」）：带冒号的文字，不是公式。"""
    return isinstance(value, str) and not value.startswith("=") and bool(_COLON_RE.search(value))


def _is_hub(ws) -> bool:
    """表头页（底稿目录 / 表头（请先填写） …）：按页名或 A1 的固定说明认。"""
    if ws.title.strip() == _HUB_SHEET:
        return True
    a1 = ws["A1"].value
    return isinstance(a1, str) and a1.strip().startswith(_HUB_A1_PREFIX)


def _fill_workbook_header(wb, values: dict[str, str], wbv=None) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """模板底稿按表头标签填值：活动页（它若就是表头页则只写冒号后）、表头页、被引用到的其他页标签格。

    先把各页表头区的外部链接单格引用归类改写（``_resolve_external_header_refs``：改本册引用 / 静态标签），
    再找引用、填值。返回 ``(外部引用改写, 标签填写)``，都只改了内存里的 ``wb``，落盘由调用方做。
    """
    ws = wb.active
    hubs = [s for s in wb.worksheets if _is_hub(s)]
    ext_edits, ext_targets, converted = _resolve_external_header_refs(wb, wbv)
    referenced = _referenced_label_cells(wb, ws)  # 先找引用（读），再写
    # 整册通用的三项（编制单位 / 期间 / 截止日）；索引号 / 底稿名称各页不同，只填活动页
    shared = {k: (v if k in _REPLACE_INLINE else "") for k, v in values.items()}
    filled: list[dict[str, str]] = []
    # 外部引用改成的静态标签：模板原先整格显示「标签：示例」⇒ 值写进冒号后，不写右边一格
    for title, coords in converted.items():
        filled += _fill_header_labels(wb[title], values if title == ws.title else shared,
                                      inline_only=True, cells=coords)
    filled += _fill_header_labels(ws, values, inline_only=any(h is ws for h in hubs))
    done = {ws.title}
    for hub in hubs:
        if hub.title not in done:
            filled += _fill_header_labels(hub, values, inline_only=True)
            done.add(hub.title)
    # 被引用的格（活动页表头引用到的 + 外部引用改成本册引用后指向的）与改成静态标签的格：只写冒号后
    pending: dict[str, set[str]] = {}
    for group in (referenced, ext_targets, converted):
        for title, coords in group.items():
            pending.setdefault(title, set()).update(coords)
    for title, coords in pending.items():
        if title not in done:
            filled += _fill_header_labels(wb[title], values, inline_only=True, cells=coords)
    # 其余各页：整册通用的编制单位 / 期间 / 截止日写进标签冒号后（示例文字「截止日：202X年12月31日」换成本项目的值）。
    # 只写冒号后、只填这三项：索引号 / 底稿名称各页不同，右边一格可能是表格，都不动。
    # 原先只填活动页与表头页，活动页是「编制说明」的多页底稿（A3-7 / A3-8）与各页自带表头的函证底稿（E0）其余各页
    # 仍显示模板示例（spec post-push-residual-defect-closure R3.4）。
    for sheet in wb.worksheets:
        if sheet.title not in done:
            filled += _fill_header_labels(sheet, shared, inline_only=True)
    return ext_edits, filled


def _header_has_external_refs(wb) -> bool:
    """任一页表头区（前 10 行 × 12 列）有引用其他工作簿的公式。"""
    from openpyxl.cell.cell import MergedCell

    return any(
        not isinstance(c, MergedCell) and isinstance(c.value, str) and _EXTERNAL_REF_RE.match(c.value)
        for ws in wb.worksheets
        for row in ws.iter_rows(min_row=1, max_row=_HEADER_ROWS, max_col=_HEADER_COLS) for c in row
    )


def _header_label(value: Any) -> str | None:
    """「编制人：张XX」→ 编制人（只认已知表头标签；公式、非文字、不认识的标签 → None）。"""
    if not isinstance(value, str) or value.startswith("="):
        return None
    m = _LABEL_RE.match(_BLANK_RE.sub("", value))
    return m.group("label") if m and m.group("label") in _HEADER_LABELS else None


#: 同页单格引用 ``=A2`` / ``=$A$2``（表头右侧常把左边的「被审计单位：」再引一次）
_SAME_SHEET_REF_RE = re.compile(r"^=\s*\$?(?P<col>[A-Z]{1,3})\$?(?P<row>\d+)\s*$")
#: 表头格引用链最多跟几层（B13-4 的「被审计单位」经 4 页转引才到底稿目录）
_MAX_REF_HOPS = 8


def _final_cell(wb, title: str, coord: str, depth: int = 0) -> tuple[str, str] | None:
    """顺着本册单格引用（跨页 ``=页签!A2`` 或同页 ``=A2``）找到最终的非公式格（最多跟 8 层）；
    遇到外部链接 / 复合公式 / 合并格 / 循环 → None。"""
    from openpyxl.cell.cell import MergedCell

    cell = wb[title][coord]
    if isinstance(cell, MergedCell):
        return None
    if isinstance(cell.value, str) and cell.value.startswith("="):
        if depth >= _MAX_REF_HOPS:
            return None
        hop = _follow_reference(wb, cell.value)
        if hop is not None:
            return _final_cell(wb, hop[0].title, hop[1], depth + 1)
        same = _SAME_SHEET_REF_RE.match(cell.value)
        if same and f"{same.group('col')}{same.group('row')}" != coord:
            return _final_cell(wb, title, f"{same.group('col')}{same.group('row')}", depth + 1)
        return None
    return title, coord


def _final_value(wb, title: str, coord: str) -> Any:
    final = _final_cell(wb, title, coord)
    return None if final is None else wb[final[0]][final[1]].value


def _strip_example(text: str, label: str) -> str:
    """外部引用缓存的标签文字改成静态时，冒号后的示例（ABC公司 / 202X年度 / 张XX / 2025-4-1）去掉。"""
    field = _LABEL_FIELDS.get(label)
    if field in _REPLACE_INLINE or label in _EXAMPLE_REST_LABELS:
        colon = _COLON_RE.search(text)
        return text[: colon.end()] if colon else text
    return text


def _resolve_external_header_refs(wb, wbv) -> tuple[list[dict[str, str]], dict[str, set[str]], dict[str, set[str]]]:
    """各页表头区（前 10 行 × 12 列）的外部链接单格引用按缓存值归类改写（spec post-push-residual-defect-closure R3）。

    * 缓存是表头标签、本册有同名页签且那一格是同一标签（缓存为空时只要那一格是表头标签）⇒ 改成本册引用，
      那一格随表头页一起填；
    * 缓存是表头标签、本册找不到对应的格 ⇒ 改成静态标签（示例去掉），随后按标签填值；
    * 缓存是底稿索引号（F2-18）⇒ 改成静态文字（该页自己的索引）；
    * 其余（金额、银行名称、复合公式）不动。

    模板从别的文件拆出来时留下这些引用，被引用的工作簿不在本册，打开只显示缓存的示例（「会计期间：202X年度」
    「编制人：张XX」）。返回 ``(改写清单, 本册引用目标 {页签: 坐标}, 改成静态标签的格 {页签: 坐标})``。
    """
    from openpyxl.cell.cell import MergedCell

    edits: list[dict[str, str]] = []
    targets: dict[str, set[str]] = {}
    converted: dict[str, set[str]] = {}
    if wbv is None:
        return edits, targets, converted
    for ws in wb.worksheets:
        for row in ws.iter_rows(min_row=1, max_row=_HEADER_ROWS, max_col=_HEADER_COLS):
            for cell in row:
                if isinstance(cell, MergedCell) or not isinstance(cell.value, str):
                    continue
                m = _EXTERNAL_SINGLE_REF_RE.match(cell.value)
                if not m:
                    continue
                cached = wbv[ws.title][cell.coordinate].value
                quoted = m.group("quoted") is not None
                name = m.group("quoted").replace("''", "'") if quoted else m.group("plain")
                addr = m.group("addr")
                coord = addr.replace("$", "")
                internal_label = _header_label(_final_value(wb, name, coord)) if name in wb.sheetnames else None
                cached_label = _header_label(cached)
                if internal_label and (internal_label == cached_label or cached is None):
                    sheet_ref = "'" + name.replace("'", "''") + "'" if quoted else name
                    cell.value = f"={sheet_ref}!{addr}"
                    targets.setdefault(name, set()).add(coord)
                    kind = "external_redirect"
                elif cached_label:
                    cell.value = _strip_example(cached, cached_label)
                    converted.setdefault(ws.title, set()).add(cell.coordinate)
                    kind = "external_label"
                elif isinstance(cached, str) and _WP_CODE_TEXT_RE.match(cached.strip()):
                    cell.value = cached.strip()
                    kind = "external_index"
                else:
                    continue  # 数据：不动
                edits.append({"sheet": ws.title, "cell": cell.coordinate, "field": kind})
    return edits, targets, converted


def _plan_cell_patches(wb, edits: list[dict[str, str]]):
    """内存里改过的格 → 补丁；另把「本册单格引用指向被改格」的表头格一并写新缓存值
    （按缓存值读的 HTML 渲染要与重算后的显示一致，原先只有表头页那一格变、各页仍显示模板示例）。"""
    from openpyxl.cell.cell import MergedCell

    from app.services.xlsx_cell_patch import CellPatch

    touched: dict[tuple[str, str], Any] = {}
    for e in edits:
        touched[(e["sheet"], e["cell"])] = wb[e["sheet"]][e["cell"]].value
    patches = []
    for (title, coord), value in touched.items():
        if isinstance(value, str) and value.startswith("="):
            shown = _final_value(wb, title, coord)
            patches.append(CellPatch(title, coord, formula=value[1:], cached=shown if isinstance(shown, str) else None))
        else:
            patches.append(CellPatch(title, coord, text="" if value is None else str(value)))
    texts = {k for k, v in touched.items() if not (isinstance(v, str) and v.startswith("="))}
    for ws in wb.worksheets:
        for row in ws.iter_rows(min_row=1, max_row=_HEADER_ROWS, max_col=_HEADER_COLS):
            for cell in row:
                key = (ws.title, cell.coordinate)
                if isinstance(cell, MergedCell) or key in touched or not (
                        isinstance(cell.value, str) and cell.value.startswith("=")):
                    continue
                final = _final_cell(wb, ws.title, cell.coordinate)
                if final in texts:
                    shown = wb[final[0]][final[1]].value
                    if isinstance(shown, str):
                        patches.append(CellPatch(ws.title, cell.coordinate, cached=shown))
    return patches


def _follow_reference(wb, value: Any):
    """``=页签!A2`` 这类跨页单格引用 → (页签, 坐标)；不是 / 引用的页签不在本册 → None。"""
    m = _REF_RE.match(value) if isinstance(value, str) else None
    if not m:
        return None
    name = m.group("quoted").replace("''", "'") if m.group("quoted") is not None else m.group("plain")
    if name not in wb.sheetnames:
        return None
    return wb[name], f"{m.group('col')}{m.group('row')}"


def _referenced_label_cells(wb, ws) -> dict[str, set[str]]:
    """活动页表头区的跨页单格引用顺着找到最终的文字格（最多跟 3 层），按页签归集坐标（不含活动页自己）。

    多页底稿常把表头放在一页（底稿目录 / 表头（请先填写） / 表头 / 目录 …），其余各页的表头格只是
    ``='表头（请先填写）'!A2`` 这样的引用 ⇒ 值只能写进被引用的那一格，各页才显示得出来。
    """
    from openpyxl.cell.cell import MergedCell

    found: dict[str, set[str]] = {}
    for row in ws.iter_rows(min_row=1, max_row=_HEADER_ROWS, max_col=_HEADER_COLS):
        for cell in row:
            hop = None if isinstance(cell, MergedCell) else _follow_reference(wb, cell.value)
            for _ in range(3):
                if hop is None:
                    break
                sheet, coord = hop
                target = sheet[coord]
                if isinstance(target, MergedCell):
                    break
                if isinstance(target.value, str) and target.value.startswith("="):
                    hop = _follow_reference(wb, target.value)
                    continue
                if sheet is not ws:
                    found.setdefault(sheet.title, set()).add(coord)
                break
    return found


def _unfillable_external_header(wb, wbv, filled: list[dict[str, str]]) -> str | None:
    """活动页表头区仍有没处理掉的外部链接格、且客户名没写进活动页看得到的格 ⇒ 返回原因，否则 None。

    外部引用先经 ``_resolve_external_header_refs`` 改写；剩下的是复合公式、缓存为空又找不到本册对应格的引用
    （缓存是金额等数据的不算表头）。看得到 = 写在活动页上，或写在活动页表头引用到的那一格（表头页 / 其他页）。
    原先这类模板（D2-5 / D4-5 / D4-12 / D4-21 …）按「没有可填位置」静默返回成功，界面上是模板缓存的示例。
    """
    from openpyxl.cell.cell import MergedCell

    ws = wb.active

    def _pending(c) -> bool:
        if isinstance(c, MergedCell) or not isinstance(c.value, str) or not _EXTERNAL_REF_RE.match(c.value):
            return False
        cached = wbv[ws.title][c.coordinate].value if wbv is not None else None
        return cached is None or _header_label(cached) is not None

    if not any(_pending(c) for row in ws.iter_rows(min_row=1, max_row=_HEADER_ROWS, max_col=_HEADER_COLS) for c in row):
        return None
    refs = _referenced_label_cells(wb, ws)
    if any(f["field"] == "client" and (f["sheet"] == ws.title or f["cell"] in refs.get(f["sheet"], ()))
           for f in filled):
        return None
    return _EXTERNAL_HEADER_REASON


def _fill_header_labels(
    ws, values: dict[str, str], *, inline_only: bool, cells: set[str] | None = None,
) -> list[dict[str, str]]:
    """在一页的表头区（前 10 行 × 12 列；给了 ``cells`` 就只看这些格）按标签填值，返回写了哪些格。
    先定好全部写入再写，写入的值不会被当成标签。

    模板表头三种写法（2026-10-26 现扫 351 个模板）：
    1. 标签 + 右边空格：值写进右边那一格；标签自己可能是合并格（``A3:B3`` 合并的「被审计单位：」），
       右边 = 标签区域之后的第一列，那一格在合并区域里就写区域左上角格；
    2. 标签右边紧挨下一个标签（「客户名称：」右边就是「编制人：」）：值写进标签格冒号后（「客户名称：XX公司」）；
    3. 被各页引用的表头格（``inline_only``：底稿目录页、活动页表头引用到的格）：只能写进标签格冒号后；
       底稿目录的右边是目录表格，不能写。
    冒号后已有示例文字（ABC公司 / 201X年度 / 202X年12月31日）的客户名称、期间、截止日换成本项目的值；
    右边是公式或模板自带的值（如「索引号：」右边的 ``A10``）不动。

    🔴 openpyxl 里合并区域除左上角外都是只读的 ``MergedCell``：原先直接写「右边一格」，一碰合并格就抛
    ``AttributeError``，整份表头一格都没填，调用方只记 warning（约一成模板：J2A / K11-4 / B10-2 / L1-1 …）。
    """
    from openpyxl.cell.cell import MergedCell

    if cells is not None:
        candidates = [ws[c] for c in sorted(cells)]
    else:
        candidates = [c for row in ws.iter_rows(min_row=1, max_row=_HEADER_ROWS, max_col=_HEADER_COLS) for c in row]
    plan: list[tuple[Any, str, str]] = []  # (目标格, 新值, 项)
    planned: set[str] = set()  # 已定要写的格：两个标签落到同一块合并值区时，后一个改写进自己冒号后，不覆盖前一个
    for cell in candidates:
        if isinstance(cell, MergedCell) or not isinstance(cell.value, str) or cell.value.startswith("="):
            continue
        m = _LABEL_RE.match(_BLANK_RE.sub("", cell.value))
        field = _LABEL_FIELDS.get(m.group("label")) if m else None
        value = values.get(field or "") or ""
        if not field or not value:
            continue
        rest = m.group("rest")
        colon = _COLON_RE.search(cell.value)
        inline = f"{cell.value[:colon.start()]}{colon.group(0)}{value}"  # 原标签（含原有空格）+ 冒号 + 值
        if inline_only or rest:
            if not rest or field in _REPLACE_INLINE:
                plan.append((cell, inline, field))
            continue
        label_rng = _merged_range_at(ws, cell.row, cell.column)
        right = _writable_cell(ws, cell.row, (label_rng.max_col if label_rng else cell.column) + 1)
        if right.coordinate in planned:
            plan.append((cell, inline, field))
        elif right.value is None or (isinstance(right.value, str) and not right.value.strip()):
            plan.append((right, value, field))
            planned.add(right.coordinate)
        elif _looks_like_label(right.value):
            plan.append((cell, inline, field))
        # 右边是公式 / 模板自带的值：不动
    filled = []
    for target, new_value, field in plan:
        if target.value == new_value:
            continue
        target.value = new_value
        filled.append({"sheet": ws.title, "cell": target.coordinate, "field": field})
    return filled


def _write_standard_header(
    ws, client_name: str, period_text: str, wp_name: str, wp_code: str,
    cycle: str | None, preparer: str | None, reviewer: str | None, xref_text: str,
):
    """空白底稿写入标准表头"""
    from openpyxl.styles import Font, Alignment, PatternFill

    header_font = Font(name="仿宋_GB2312", size=10)
    title_font = Font(name="仿宋_GB2312", size=12, bold=True)
    header_fill = PatternFill(start_color="F4F0FA", end_color="F4F0FA", fill_type="solid")

    # 第1行：事务所名称
    ws.cell(row=1, column=1, value="致同会计师事务所（特殊普通合伙）").font = title_font
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)
    ws.cell(row=1, column=1).alignment = Alignment(horizontal="center")

    # 第2行：编制单位 + 审计期间
    ws.cell(row=2, column=1, value="编制单位：").font = header_font
    ws.cell(row=2, column=2, value=client_name).font = header_font
    ws.cell(row=2, column=5, value="审计期间：").font = header_font
    ws.cell(row=2, column=6, value=period_text).font = header_font

    # 第3行：底稿名称 + 索引号
    ws.cell(row=3, column=1, value="底稿名称：").font = header_font
    ws.cell(row=3, column=2, value=wp_name).font = header_font
    ws.cell(row=3, column=5, value="索引号：").font = header_font
    ws.cell(row=3, column=6, value=wp_code).font = Font(name="Arial Narrow", size=11, bold=True)

    # 第4行：编制人 + 复核人
    ws.cell(row=4, column=1, value="编制人：").font = header_font
    ws.cell(row=4, column=2, value=preparer or "").font = header_font
    ws.cell(row=4, column=3, value="日期：").font = header_font
    ws.cell(row=4, column=4, value="").font = header_font
    ws.cell(row=4, column=5, value="复核人：").font = header_font
    ws.cell(row=4, column=6, value=reviewer or "").font = header_font
    ws.cell(row=4, column=7, value="日期：").font = header_font

    # 第5行：交叉索引
    ws.cell(row=5, column=1, value="交叉索引：").font = header_font
    ws.cell(row=5, column=2, value=xref_text).font = header_font

    # 第6行：审计阶段
    stage = _CYCLE_NAMES.get(cycle, "") if cycle else ""
    if stage:
        ws.cell(row=5, column=5, value="审计阶段：").font = header_font
        ws.cell(row=5, column=6, value=stage).font = header_font

    # 第7行空行分隔
    # 第8行开始是数据区域（审定表的列标题）

    # 设置列宽
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 8
    ws.column_dimensions["D"].width = 14
    ws.column_dimensions["E"].width = 12
    ws.column_dimensions["F"].width = 20
    ws.column_dimensions["G"].width = 8
    ws.column_dimensions["H"].width = 14

    # 表头区域浅紫色背景
    for r in range(1, 6):
        for c in range(1, 9):
            cell = ws.cell(row=r, column=c)
            cell.fill = header_fill
