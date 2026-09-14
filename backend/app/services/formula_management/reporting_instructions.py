"""公式管理"编报说明 / 说明文档"单一文档源（Req 23.6 / Req 25.3）。

本模块是**唯一**的公式管理说明文档来源，被以下两处同源消费，避免说明两套漂移：

1. **导出模板首区块=编报说明**（Req 23.2）：``formula_import_export`` 导出模板时，
   把本文档渲染为工作簿首个 sheet「编报说明」（``instructions_as_rows``）。
2. **公式预设库说明文档弹窗**（Req 25.2/25.3）：前端 ``GtFormulaPresetDialog``
   经 ``GET /api/formula-management/reporting-instructions`` 拉取本文档（结构化
   ``instructions_as_dict`` / Markdown ``instructions_as_markdown``）渲染。

说明内容覆盖（Req 23.2 / Req 25.2）：
- 三类型公式 auto_calc / logic_check / reasonability 的语义与填法；
- 引用地址格式（ACNR ``addr_id`` / ``formula_ref``：``TB()`` / ``ROW()`` /
  ``PREV()`` / ``AUX()`` / ``WP()``，经 ``full_resolve`` 可解析，禁裸坐标串）；
- 预设库用法、导入导出与编报说明、一键刷新与初稿语义；
- 注意事项。

**修改说明只改本文件**——模板编报说明与弹窗文档随之一致（单一源不分叉）。

Requirements: 23.2, 23.6, 25.2, 25.3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 文档版本：编报说明与说明文档弹窗共享同一版本号，便于核对同源。
DOC_VERSION = "2025-R1"

DOC_TITLE = "公式管理编报说明"


@dataclass
class DocSection:
    """说明文档的一个区块（标题 + 若干行文本）。"""

    key: str
    title: str
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "title": self.title, "lines": list(self.lines)}


# ── 单一文档源（结构化） ──────────────────────────────────────────────────────
# 修改说明内容只改这里；导出模板编报说明与前端说明弹窗均从此派生（Req 23.6/25.3）。
_SECTIONS: list[DocSection] = [
    DocSection(
        key="overview",
        title="一、总述",
        lines=[
            "公式管理库统一治理底稿 / 报表 / 附注三处公式的编辑、计算、保存三能力。",
            "每条公式由：目标单元(target_cell) + 表达式(expression) + 公式类型(formula_type)",
            "+ 引用(refs) 构成；引用一律经 ACNR full_resolve 解析，保证跨底稿/报表/附注可追溯。",
            "离线批量编辑：导出模板 → 按本说明填写 → 导入数据回填；导入时逐条校验引用，",
            "悬空引用（无法解析）的公式将被报告并跳过，不会静默入库。",
        ],
    ),
    DocSection(
        key="formula_types",
        title="二、三类型公式语义与填法",
        lines=[
            "公式类型 formula_type 只能取以下三值之一：",
            "1) auto_calc（计算回填）：求值后把结果写入目标单元。",
            "   填法示例：表达式 = TB('1001') + TB('1002')，目标单元填被回填的单元/行标识。",
            "   注意：目标单元不得指向四表库叶子源（trial_balance/tb_balance/tb_ledger/tb_aux_balance）。",
            "2) logic_check（逻辑校验）：表达式为一个布尔条件；不通过时产出问题清单(Issue)，绝不改值。",
            "   填法示例：表达式 = ABS(ROW('assets_total') - (ROW('liabilities_total') + ROW('equity_total'))) <= 1，",
            "   说明(description) 填不通过时的提示文案（如「资产合计 = 负债合计 + 所有者权益合计」）。",
            "3) reasonability（合理性提示）：表达式为触发条件；命中时产出提醒(Hint)，绝不改值。",
            "   填法示例：有效税率≈25% 偏离过大时提示核查，说明填提醒文案。",
            "口诀：auto_calc 改值、logic_check 与 reasonability 只提示不改值。",
        ],
    ),
    DocSection(
        key="reference_format",
        title="三、引用地址格式（ACNR）",
        lines=[
            "引用 refs 以规范化形态填写，每项为 addr_id 或 formula_ref，经 full_resolve 可解析；",
            "禁止直接拼接 wp_code + sheet + cell 的裸坐标字符串。",
            "常用取数/引用函数：",
            "· TB('科目编码')      —— 取试算表审定数（四表库统一入口，借正贷负 v1 口径由系统处理）",
            "· PREV('科目编码')    —— 取上期数",
            "· AUX('科目','维度')  —— 取辅助维度余额（按 aux_type 分组）",
            "· ROW('报表行编码')   —— 取报表行值（如 ROW('assets_total') / ROW('IS-017')）",
            "· WP(wp_code, cell)   —— 引用另一底稿单元（经 ACNR 追溯解析）",
            "引用示例（refs 列，JSON 数组）：",
            "[{\"formula_ref\": \"TB('1001')\"}, {\"addr_id\": \"D2/D2/C15\"}]",
            "若 refs 列留空，系统会尝试从表达式中自动提取引用再校验。",
        ],
    ),
    DocSection(
        key="preset_library",
        title="四、预设库用法",
        lines=[
            "预设库按 页面键(page_key) 组织，page_key 格式为 scope:key：",
            "· workpaper:{wp_code}  底稿页（如 workpaper:D2）",
            "· report:{key}         报表页（如 report:cross_check）",
            "· note:{section}       附注页（如 note:货币资金）",
            "同一 page_key 下 target_cell 唯一；预设库按 (page_key, target_cell) 去重（幂等）。",
            "一键刷新 / 底稿生成会按 page_key 套用预设为初稿公式；未预设页保留现状。",
        ],
    ),
    DocSection(
        key="import_export",
        title="五、导入导出与编报说明",
        lines=[
            "导出模板：生成含本编报说明区 + 空白/示例公式行的模板，供离线填写。",
            "导出数据：导出当前页面/模块已有公式（目标单元、表达式、公式类型、引用、最近计算时间）。",
            "导入数据：解析文件并逐条经 ACNR full_resolve 校验引用；悬空项报告并跳过，有效项入库。",
            "文件为 .xlsx；导入以列头匹配，列顺序可变，多余列忽略。",
            "公式类型列必须为 auto_calc / logic_check / reasonability 之一，否则该行按无效跳过。",
        ],
    ),
    DocSection(
        key="draft_refresh",
        title="六、一键刷新与初稿语义",
        lines=[
            "一键刷新（合伙人专属）：从四表库未审数一次生成未审报表 + 底稿 + 附注初稿，",
            "生成结果打「初稿(draft)」标记，并留不可篡改的刷新审计；可回滚到刷新前状态。",
            "recalc（团队可触发）：仅重算既有公式，不生成初稿、不打 Draft 标记。",
            "被人工编辑过的单元在未确认覆盖时不会被一键刷新覆盖，标记为「已人工编辑」。",
        ],
    ),
    DocSection(
        key="notes",
        title="七、注意事项",
        lines=[
            "1. 目标单元不得指向四表库叶子源（只读），否则该 auto_calc 公式会被拒绝。",
            "2. 引用必须能经 full_resolve 解析；悬空引用导入时会被跳过并在结果中报告。",
            "3. logic_check / reasonability 绝不修改数据，只产出问题/提醒清单。",
            "4. 交付导出（报表/附注/报告）会把公式解析为静态值，产物不保留可重算表达式。",
            "5. 中文文件名下载采用 RFC 5987 编码，避免乱码。",
        ],
    ),
]


def get_reporting_instructions() -> list[DocSection]:
    """返回结构化说明文档（单一源）。"""
    return _SECTIONS


def instructions_as_dict() -> dict[str, Any]:
    """结构化字典形态（供 API / 前端说明弹窗消费，Req 25.2/25.3）。"""
    return {
        "title": DOC_TITLE,
        "version": DOC_VERSION,
        "sections": [s.to_dict() for s in _SECTIONS],
    }


def instructions_as_markdown() -> str:
    """Markdown 形态（供前端说明弹窗直接渲染，单一源）。"""
    parts: list[str] = [f"# {DOC_TITLE}", "", f"> 版本：{DOC_VERSION}", ""]
    for s in _SECTIONS:
        parts.append(f"## {s.title}")
        parts.append("")
        for line in s.lines:
            parts.append(line)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def instructions_as_rows() -> list[list[str]]:
    """扁平行形态（供导出模板首区块「编报说明」sheet 写入，Req 23.2）。

    每行一个单元格文本；区块标题单独成行，便于阅读。
    """
    rows: list[list[str]] = [[DOC_TITLE], [f"版本：{DOC_VERSION}"], [""]]
    for s in _SECTIONS:
        rows.append([s.title])
        for line in s.lines:
            rows.append([line])
        rows.append([""])
    return rows
