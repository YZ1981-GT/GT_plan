"""test_k0_source_template_facts.py — K0 源模板事实守卫（xlsx 为唯一裁决者）.

spec: k0-confirmation-source-alignment
  Requirements 1.1~1.17 / 6.1 / 6.3 / 6.4 / 7.1 / 7.5 / 7.6
  Property 1（sheet 与目录）+ 全部结构断言

本文件是 K0 全部改造的**事实基线**：openpyxl 直读源模板 xlsx（不连库、可进 CI），
后续会话不必重新精读源模板，也不能凭「常识」改动 K0 结构。

🔴 **判 DV 必须 ``coord in dv.sqref`` 逐格测试** —— openpyxl 打印的
``JF/JK/JN/TG/ACX`` 等远端列范围是 Excel 列重复产生的**残留 sqref**，
**不落在真实列上**。K0-1 上就有三组这类镜像 DV（``"√,×"`` /
``"跟函,邮寄,电邮,其他"`` / ``"纸质原件,传真件,电子邮件,其他介质"``），
按打印顺序取第一个 sqref 会得出「K0-1!G 列（函证方式）DV = 跟函/邮寄/电邮/其他」
的错误结论（真实的渠道 DV 在 ``K0-2!C7:C24``，经 VLOOKUP 带入 K0-1!G）。
见 ``TestMirrorDataValidationTrap``。

🔴 **源模板笔误一律登记不改写**（``SOURCE_TEMPLATE_TYPOS``）：按意图实现 + tooltip
标注原值，绝不改动源 xlsx，也绝不「顺手修正」常量（否则三向比对会打红）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl
import pytest
from openpyxl.utils import get_column_letter

_REPO_ROOT = Path(__file__).resolve().parents[2]
K0_XLSX = _REPO_ROOT / "backend" / "wp_templates" / "K" / "K0 管理循环函证.xlsx"
WP_CODE_OVERRIDES = _REPO_ROOT / "backend" / "app" / "data" / "wp_code_overrides.json"

# ─── sheet 层（10 visible + 1 hidden GT_Custom） ──────────────────────────────

#: 10 张可见 sheet，顺序逐字
EXPECTED_VISIBLE_SHEETS = [
    "底稿目录",
    "函证程序表K0A",
    "函证结果汇总表K0-1",
    "核实被函证单位信息K0-2",
    "跟函函证过程控制K0-3",
    "函证差异调节表K0-4",
    "其他应收款替代程序K0-5",
    "其他应付款替代程序K0-6",
    "邮件传真回函可靠性验证K0-7",
    "函证程序舞弊风险评价表K0-8",
]

#: 唯一 hidden sheet —— 与 E0 的「10 张隐藏表被渲染成页签」情形不同，K0 无该议题
EXPECTED_HIDDEN_SHEETS = ["GT_Custom"]

#: 底稿目录 `D5:F13`：(序号, 内容, 索引号)。
#: 🔴 序号序列 `[1,2,3,4,5,7,8,9,10]` —— **6 缺失、9 行末号为 10**（源模板跳号事实）
INDEX_SHEET_ROWS = [
    (1, "函证程序表", "K0A"),
    (2, "函证结果汇总表", "K0-1"),
    (3, "核实被函证单位信息", "K0-2"),
    (4, "跟函函证过程控制", "K0-3"),
    (5, "函证差异调节表", "K0-4"),
    (7, "其他应收款替代程序检查表", "K0-5"),
    (8, "其他应付款替代程序检查表", "K0-6"),
    (9, "邮件传真回函可靠性验证", "K0-7"),
    (10, "函证程序舞弊风险评价表", "K0-8"),
]

# ─── K0-1 上区 28 列 → 平台列 key（本表即证据表；改一侧必须同步另一侧） ────────

SUMMARY_COLUMN_MAP: list[tuple[str, str, str]] = [
    ("A", "序号", "seq"),
    ("B", "询证函索引号", "confirm_index"),
    ("C", "选取样本目的", "sample_purpose"),
    ("D", "被询证单位名称", "entity_name"),
    ("E", "账户/交易", "account_type"),
    ("F", "金额", "amount"),
    ("G", "函证方式", "send_channel"),
    ("H", "发函日期", "send_date"),
    ("I", "发函单号/跟函记录索引号", "send_doc_no"),
    ("J", "收件地址", "entity_address"),
    ("K", "地址核查是否一致", "send_addr_match"),
    ("L", "是否收到回函", "is_replied"),
    ("M", "回函方式", "reply_method"),
    ("N", "是否相符", "match_status"),
    ("O", "回函日期", "reply_date"),
    ("P", "回函快递单号", "reply_courier_no"),
    ("Q", "回函发出地址", "reply_from_addr"),
    ("R", "发函地址与回函地址是否一致", "send_reply_addr_match"),
    ("S", "回函金额", "reply_amount"),
    ("T", "差异", "difference"),
    ("U", "可确认金额", "confirmed_amount"),
    ("V", "调节索引（K1-12）", "diff_ref_index"),
    ("W", "其他说明/备注", "remark"),
    ("X", "是否采取替代程序", "use_alternative"),
    ("Y", "替代后可确认金额", "alt_confirmed"),
    ("Z", "替代后不可确认金额", "alt_unconfirmed"),
    ("AA", "替代程序索引号", "alt_ref_index"),
    ("AB", "审计结论", "row_conclusion"),
]

#: K0-1 上区六段（源模板 R5 合并区）；`AB5:AB6` 是与前五段并列的独立段
SUMMARY_GROUP_HEADERS = [
    ("C5:F5", "发函询证纪要"),
    ("G5:K5", "1、发函信息"),
    ("L5:R5", "2、收到回函"),
    ("S5:W5", "3、回函金额确认"),
    ("X5:AA5", "4、未收到回函的替代程序"),
    ("AB5:AB6", "审计结论"),
]

#: 源模板 K0-1 **没有**的三列（平台 BASE 有 → 必须剔除，否则空列噪声）。
#: 联系人 / 联系电话在 K0-2 的 `F`/`G` 列；币种源模板压根没有。
COLUMNS_ABSENT_IN_SOURCE = ["contact_person", "contact_phone", "currency"]

#: 七条 VLOOKUP（K0-1 ← K0-2），值即源模板第三参 col_index_num
EXPECTED_VLOOKUP_COL_INDEX = {
    "D": 2,   # 被询证单位名称 ← K0-2!B 被询证单位全称
    "G": 3,   # 函证方式(渠道) ← K0-2!C
    "J": 4,   # 收件地址       ← K0-2!D
    "K": 10,  # 地址核查是否一致 ← K0-2!J
    "M": 16,  # 回函方式       ← K0-2!P
    "Q": 19,  # 回函发出地址   ← K0-2!S
    "R": 22,  # 发函地址与回函地址是否一致 ← K0-2!V
}

# ─── K0-1 下区四块 ───────────────────────────────────────────────────────────

LOWER_ZONE_BLOCKS = [
    ("C27", "一、函证情况"),
    ("I27", "二、样本选择"),
    ("S27", "三、审计说明"),
    ("C38", "四、审计结论"),
]

#: 矩阵品种列头（源 E28/F28）—— **固定 2 个**，无 `……` 可扩位
MATRIX_CATEGORIES = [("E28", "其他应收款"), ("F28", "其他应付款")]

#: 8 指标（源 C29:C36，含行尾冒号）
MATRIX_METRIC_CELLS = [
    ("C29", "本期（期末）账面金额："),
    ("C30", "抽取样本的发函金额："),
    ("C31", "发函金额占账面金额的比例(%)："),
    ("C32", "回函确认金额："),
    ("C33", "回函可确认金额占发函金额的比例(%)："),
    ("C34", "回函可确认金额占账面金额的比例(%)："),
    ("C35", "替代测试确认金额："),
    ("C36", "回函和替代确认金额占账面金额的比例(%)："),
]

#: 矩阵公式（E 列 = 其他应收款；criteria 为 E28）
MATRIX_FORMULAS_E = {
    "E30": "=SUMIF(E7:E26,E28,F7:F26)",
    "E31": "=IF(ISERROR(E30/E29),0,E30/E29)",
    "E32": "=SUMIF(E7:E26,E28,U7:U26)",
    "E33": "=IF(ISERROR(E32/E30),0,E32/E30)",
    "E34": "=IF(ISERROR(E32/E29),0,E32/E29)",
    "E35": "=SUMIF(E7:E26,E28,Y7:Y26)",
    # 🔴 末行**无 ISERROR 兜底**（源模板如此）→ 平台侧必须自己保证不产出 NaN/Inf
    "E36": "=(E35+E32)/E29",
}
MATRIX_FORMULAS_F = {
    "F30": "=SUMIF(E7:E26,F28,F7:F26)",
    "F31": "=IF(ISERROR(F30/F29),0,F30/F29)",
    "F32": "=SUMIF(E7:E26,F28,U7:U26)",
    "F33": "=IF(ISERROR(F32/F30),0,F32/F30)",
    "F34": "=IF(ISERROR(F32/F29),0,F32/F29)",
    "F35": "=SUMIF(E7:E26,F28,Y7:Y26)",
    "F36": "=(F35+F32)/F29",
}

#: 「二、样本选择」6 项（`I32` **为空**，`J32` 承载样本计算器提示）
SAMPLE_SELECTION_CELLS = [
    ("I28", "测试范围："),
    ("I29", "特定样本："),
    ("I30", "抽样总体："),
    ("I31", "确定的抽样样本量："),
    ("I33", "抽样方法："),
    ("I34", "抽样过程："),
]

#: 「三、审计说明」5 项标题（`role=title`，永不参与拼接）
AUDIT_NOTE_TITLE_CELLS = [
    ("S28", "1.对询证函保持的控制的说明"),
    ("X28", "2.对误差的分析"),
    # 🔴 源写「（K0-6）」而回函可靠性验证表实为 K0-7（K0-6 是其他应付款替代程序）
    ("S32", "3.对以传真或电子邮件形式收到的回函的可靠性的考虑（K0-6）"),
    ("X32", "4.针对不符事项的程序"),
    ("S36", "5.针对未回函的替代程序"),
]

#: 全下区**唯一**需要拼接的 hint —— 第 2 项的界定条件被源模板拆成 `X29`+`X30` 两格
AUDIT_NOTE_HINT_X29_X30 = (
    "界定误差构成条件：［不符事项的金额高于或低于账户余额人民币"
    "（）万元，并且被审计单位不能合理解释其差异并提供相应依据］"
)

#: 第 3 项的补充说明（独立 hint，**不与标题拼接**，否则出错句）
AUDIT_NOTE_HINT_S33 = "如果回函中存在未函证的其他信息，应考虑未函证信息的影响，并考虑实施进一步审计程序"

#: 准则 1312 第十条**六项**选样要求（源 A46:A51；含全角空格缩进）
STANDARD_1312_SELECTION_ITEMS = [
    ("A46", "（一）金额较大的项目；"),
    ("A47", "（二）账龄较长的项目；"),
    ("A48", "（三）交易频繁但期末余额较小的项目；"),
    ("A49", "（四）重大关联方交易；"),
    ("A50", "（五）重大或异常的交易；"),
    ("A51", "（六）可能存在争议以及产生重大舞弊或错误的交易。"),
]

#: 函证注意事项 **8 条**（源 B53:B60 —— 🔴 在 **B 列**，只扫 A 列会整段漏掉）
CONFIRMATION_TIPS = [
    ("B53", "①严格控制发函过程（亲自发函；直接回函）；"),
    ("B54", "②传真件、电子邮件回函可以作为证据，但可靠性低于原件且需严格控制并记录函证过程；"),
    ("B55", "③同一客户的多项往来在同一张询证函列示；"),
    ("B56", "④关联往来核对一致；"),
    ("B57", "⑤收信人尽量写清楚；"),
    ("B58", "⑥收到回函编制函证控制表（函证结果汇总表），保留回函信封，注明选样标准；"),
    ("B59", "⑦回函有差异须进一步核对原因；"),
    ("B60", "⑧未回函的全部执行替代程序。"),
]

#: 参考结论 A/B/C —— 🔴 **内容在 B 列**，A 列只是 `A、`/`B、`/`C、` 标签
REFERENCE_CONCLUSIONS = [
    ("A", "A64", "B64", "未见异常。"),
    ("B", "A65", "B65", "除以下重大不符事项应当作为调整事项予以调整外，其余未见异常。"),
    ("C", "A66", "B66", "由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。"),
]

# ─── 源模板笔误登记（不改源 xlsx；按意图实现 + tooltip 标原值） ────────────────

#: (源锚点, 源模板字面, 实际所指, 说明)
SOURCE_TEMPLATE_TYPOS = [
    ("函证结果汇总表K0-1!V6", "调节索引（K1-12）", "K0-4",
     "函证差异调节表实为 K0-4；K1-12 是 K1 循环底稿，与 K0 无关"),
    ("函证结果汇总表K0-1!S32", "3.对以传真或电子邮件形式收到的回函的可靠性的考虑（K0-6）", "K0-7",
     "回函可靠性验证表实为 K0-7；K0-6 是其他应付款替代程序"),
    ("核实被函证单位信息K0-2!AA6", "跟函函证控制过程（K1-11）", "K0-3",
     "跟函函证过程控制实为 K0-3；K1-11 是 K1 循环底稿"),
    ("底稿目录!D5:D13", "序号 [1,2,3,4,5,7,8,9,10]", "9 张底稿",
     "序号 6 缺失且末号为 10 而仅 9 行 → 以索引号为定位与展示真源，不依赖序号"),
    ("其他应收款替代程序K0-5!M46", "=SUM(M40:M45)", "不实现",
     "对「索引号」文本列求和，无业务含义；K0-6 同位置无此公式（旁证为笔误）"),
]

# ─── fixtures / helpers ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def wb():
    if not K0_XLSX.exists():
        pytest.fail(f"源模板不存在，无法裁决: {K0_XLSX}")
    # 🔴 `~$` 锁文件（用户开着 WPS 时会出现）不是模板，命中即提示而非静默读错文件
    lock = K0_XLSX.with_name("~$" + K0_XLSX.name)
    if lock.exists():
        pytest.fail(f"检测到 Excel 锁文件 {lock.name}，源模板可能有未保存改动，先关闭 WPS/Excel")
    return openpyxl.load_workbook(K0_XLSX, data_only=False)


def norm(v) -> str:
    """归一：仅去首尾空白 + 统一换行。

    🔴 **不做过度归一**（不去内部空格、不转全半角）——
    源模板的「合  计」「页 次」等空格差异本身就是要钉住的事实。
    """
    if v is None:
        return ""
    return str(v).replace("\r\n", "\n").strip()


def header_label(ws, col: str) -> str:
    """取该列表头：R6 有值取 R6，否则取 R5（A/B/AB 是 rowspan 合并）。"""
    v6 = ws[f"{col}6"].value
    v5 = ws[f"{col}5"].value
    return norm(v6 if norm(v6) else v5)


def dv_formulas_at(ws, coord: str) -> list[str]:
    """🔴 逐格测试：只返回**真正覆盖** `coord` 的 DV（排除镜像残留 sqref）。"""
    return [dv.formula1 for dv in ws.data_validations.dataValidation if coord in dv.sqref]


def dv_options_at(ws, coord: str) -> list[str]:
    out: list[str] = []
    for f in dv_formulas_at(ws, coord):
        if f and f.startswith('"') and f.endswith('"'):
            out.extend(x.strip() for x in f[1:-1].split(","))
    return out


def all_dv_formulas(ws) -> list[str]:
    return [dv.formula1 for dv in ws.data_validations.dataValidation]


# ═══════════════════════════════════════════════════════════════════════════════
# Task 1 / Property 1: sheet 与底稿目录层
# ═══════════════════════════════════════════════════════════════════════════════


class TestSheetsAndIndex:
    def test_eleven_sheets_ten_visible_one_hidden(self, wb):
        """11 张 sheet：10 visible（顺序逐字）+ `GT_Custom` hidden（R1.1）。"""
        assert wb.sheetnames == EXPECTED_VISIBLE_SHEETS + EXPECTED_HIDDEN_SHEETS
        for name in EXPECTED_VISIBLE_SHEETS:
            assert wb[name].sheet_state == "visible", f"{name} 不是 visible"
        for name in EXPECTED_HIDDEN_SHEETS:
            assert wb[name].sheet_state == "hidden", f"{name} 不是 hidden"

    def test_no_adjudication_sheet(self, wb):
        """`审定表K0-1` **不存在** —— 公式预设 sheet 名贴错标签的依据（R5.1）。"""
        assert "审定表K0-1" not in wb.sheetnames
        assert "函证结果汇总表K0-1" in wb.sheetnames

    def test_index_sheet_nine_rows(self, wb):
        """底稿目录 `D5:F13` 共 9 行，(序号, 内容, 索引号) 逐字（R1.2）。"""
        ws = wb["底稿目录"]
        rows = [
            (ws.cell(r, 4).value, norm(ws.cell(r, 5).value), norm(ws.cell(r, 6).value))
            for r in range(5, 14)
        ]
        assert rows == INDEX_SHEET_ROWS
        # 第 14 行起不应再有条目
        assert not norm(ws.cell(14, 6).value)

    def test_index_sheet_seq_skips_six(self, wb):
        """🔴 序号序列 `[1,2,3,4,5,7,8,9,10]` —— 6 缺失、9 行末号为 10（R1.2 / R6.3）。"""
        ws = wb["底稿目录"]
        seqs = [ws.cell(r, 4).value for r in range(5, 14)]
        assert seqs == [1, 2, 3, 4, 5, 7, 8, 9, 10]
        assert 6 not in seqs, "源模板序号 6 缺失是既有事实，出现即模板被改过"
        assert len(seqs) == 9 and seqs[-1] == 10, "9 行而末号为 10 = 跳号事实"

    def test_index_codes_match_sheet_suffixes(self, wb):
        """9 个索引号与 9 张实体 sheet 的后缀一一对应（K0A + K0-1..K0-8）。"""
        codes = [c for _, _, c in INDEX_SHEET_ROWS]
        assert codes == ["K0A"] + [f"K0-{i}" for i in range(1, 9)]
        entity_sheets = [s for s in EXPECTED_VISIBLE_SHEETS if s != "底稿目录"]
        assert len(entity_sheets) == len(codes)
        for sheet, code in zip(entity_sheets, codes):
            assert sheet.endswith(code), f"{sheet!r} 不以索引号 {code} 结尾"

    def test_wp_code_overrides_cover_nine_codes_without_skip(self):
        """`wp_code_overrides.json` 覆盖 9 个索引号且无一为 `skip`（R6.4）。"""
        data = json.loads(WP_CODE_OVERRIDES.read_text(encoding="utf-8"))
        overrides = data.get("overrides", data)
        for _, _, code in INDEX_SHEET_ROWS:
            assert code in overrides, f"wp_code_overrides 缺 {code}"
            assert overrides[code] != "skip", f"{code} 被标为 skip（K0 无隐藏 sheet 议题）"
        # 工作簿级 hub 条目也在册（`confirmation-hub` 是合法 placeholder）
        assert overrides.get("K0") == "confirmation-hub"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 2 / Property 2 的源侧事实：K0-1 上区
# ═══════════════════════════════════════════════════════════════════════════════


class TestSummaryUpperZone:
    def test_exactly_28_columns(self, wb):
        """A..AB 共 28 列，表头逐字；第 29 列（AC）无表头（R1.3）。"""
        ws = wb["函证结果汇总表K0-1"]
        labels = [header_label(ws, get_column_letter(c)) for c in range(1, 29)]
        assert all(labels), f"A..AB 应全部有表头，实得: {labels}"
        assert labels == [lbl for _, lbl, _ in SUMMARY_COLUMN_MAP]
        assert not header_label(ws, "AC")

    @pytest.mark.parametrize("rng,label", SUMMARY_GROUP_HEADERS)
    def test_group_headers(self, wb, rng: str, label: str):
        """六段合并表头逐字（R1.3）。`AB5:AB6` 是与前五段并列的独立段。"""
        ws = wb["函证结果汇总表K0-1"]
        merged = {str(r) for r in ws.merged_cells.ranges}
        assert rng in merged, f"合并区 {rng} 不存在"
        assert norm(ws[rng.split(":")[0]].value) == label

    def test_rowspan_columns(self, wb):
        """序号 / 询证函索引号 / 审计结论 是 rowspan=2（不属任何段）。"""
        ws = wb["函证结果汇总表K0-1"]
        merged = {str(r) for r in ws.merged_cells.ranges}
        for rng in ("A5:A6", "B5:B6", "AB5:AB6"):
            assert rng in merged, f"{rng} 应为 rowspan 合并"
        assert not norm(ws["AB6"].value), "AB6 应为空（AB5 承载表头）"

    def test_data_rows_are_r7_to_r26(self, wb):
        """数据行 `r7:r26` = 20 行；序号列 1..20（R1.4）。"""
        ws = wb["函证结果汇总表K0-1"]
        seqs = [ws.cell(r, 1).value for r in range(7, 27)]
        assert seqs == list(range(1, 21))
        assert norm(ws.cell(27, 1).value) == "", "r27 起是下区，不应有序号"

    @pytest.mark.parametrize("col,col_index", sorted(EXPECTED_VLOOKUP_COL_INDEX.items()))
    def test_vlookup_columns(self, wb, col: str, col_index: int):
        """七列 VLOOKUP 自 K0-2，col_index_num 逐条一致（R1.4）。"""
        ws = wb["函证结果汇总表K0-1"]
        for r in (7, 15, 26):
            f = norm(ws[f"{col}{r}"].value)
            # 查找键恒为 `$B{r}`（询证函索引号），查找区恒为 K0-2 的 $A:$AL
            expected = f"=VLOOKUP($B{r},'核实被函证单位信息K0-2'!$A:$AL,{col_index},0)"
            assert f == expected, f"{col}{r} 公式不符：{f!r} != {expected!r}"

    def test_difference_formula(self, wb):
        """`T` 列 = `IF(L="是",S-F,"未回函")`（R1.4）—— 未回函不算差异。"""
        ws = wb["函证结果汇总表K0-1"]
        for r in (7, 20, 26):
            assert norm(ws[f"T{r}"].value) == f'=IF(L{r}="是",S{r}-F{r},"未回函")'

    def test_no_formula_on_confirmed_amount(self, wb):
        """`U 可确认金额` / `Y 替代后可确认金额` 源模板无公式（手工/平台派生）。"""
        ws = wb["函证结果汇总表K0-1"]
        for coord in ("U7", "U26", "Y7", "Y26", "S7", "F7"):
            assert norm(ws[coord].value) == "", f"{coord} 源模板应为空"


class TestMirrorDataValidationTrap:
    """🔴 镜像 DV 陷阱（H0 已命名的平台级坑，K0 上有三组）。"""

    def test_real_dv_on_summary(self, wb):
        """K0-1 真实 DV 只有三处：`C`（选样目的 5 项）+ `L/N/X`（是/否）。"""
        ws = wb["函证结果汇总表K0-1"]
        assert dv_options_at(ws, "C7") == ["A. 大额", "B.异常", "C.余额为0", "D.账龄长", "E.随机"]
        for coord in ("L7", "N7", "X7", "L26", "N26", "X26"):
            assert dv_options_at(ws, coord) == ["是", "否"], f"{coord} DV 应为 是/否"

    def test_reply_method_column_has_no_dv(self, wb):
        """`M 回函方式` **无** DV —— 它由 VLOOKUP 自 K0-2!P 带入。"""
        ws = wb["函证结果汇总表K0-1"]
        for coord in ("M7", "M26", "G7", "G26"):
            assert dv_formulas_at(ws, coord) == [], f"{coord} 不应有 DV（VLOOKUP 带入）"

    def test_channel_dv_exists_only_on_mirror_columns(self, wb):
        """反向自检：`"跟函,邮寄,电邮,其他"` 确实存在于文件中，但**不覆盖任何真实格**。

        它落在 `JK:JL` 等列重复残留 sqref 上。按打印顺序取第一个 sqref 会得出
        「K0-1!G 列 DV = 跟函/邮寄/电邮/其他」的错误结论（真实渠道 DV 在 K0-2!C）。
        """
        ws = wb["函证结果汇总表K0-1"]
        mirror = '"跟函,邮寄,电邮,其他"'
        assert mirror in all_dv_formulas(ws), "镜像 DV 消失 = 模板被改过，本自检失效"
        covering = [dv for dv in ws.data_validations.dataValidation if dv.formula1 == mirror]
        assert covering, "未找到该镜像 DV"
        for dv in covering:
            for real in ("G7", "M7", "C7", "L7", "N7", "X7", "A7", "AB7"):
                assert real not in dv.sqref, f"镜像 DV 竟覆盖真实格 {real}"

    def test_broken_dv_o32_registered(self, wb):
        """`O32` 的 DV 指向 `#REF!`（源模板坏引用）—— 登记，不实现。"""
        ws = wb["函证结果汇总表K0-1"]
        assert dv_formulas_at(ws, "O32") == ["#REF!"]


# ═══════════════════════════════════════════════════════════════════════════════
# Task 2 / Property 5 / 10 的源侧事实：K0-1 下区四块
# ═══════════════════════════════════════════════════════════════════════════════


class TestSummaryLowerZone:
    @pytest.mark.parametrize("coord,title", LOWER_ZONE_BLOCKS)
    def test_block_anchors(self, wb, coord: str, title: str):
        """四块锚点与标题逐字（R1.5 / R3.1）。"""
        ws = wb["函证结果汇总表K0-1"]
        assert norm(ws[coord].value) == title

    def test_matrix_categories_are_exactly_two(self, wb):
        """品种列头恰 2 个（源 E28/F28），**无 `……` 可扩位**（R1.5 / R3.2）。"""
        ws = wb["函证结果汇总表K0-1"]
        for coord, name in MATRIX_CATEGORIES:
            assert norm(ws[coord].value) == name
        assert norm(ws["G28"].value) == "", "G28 应为空（K0 品种固定 2 个，不像 H0/G0 有可扩位）"
        assert norm(ws["C28"].value) == "项目"

    @pytest.mark.parametrize("coord,text", MATRIX_METRIC_CELLS)
    def test_matrix_metric_labels(self, wb, coord: str, text: str):
        """8 指标逐字（源 C29:C36，含行尾冒号）（R1.5 / R3.2）。"""
        ws = wb["函证结果汇总表K0-1"]
        assert norm(ws[coord].value) == text

    def test_metric_count_is_eight(self, wb):
        """C29:C36 恰 8 行，C37 为空（防指标增减无声漂移）。"""
        ws = wb["函证结果汇总表K0-1"]
        assert len(MATRIX_METRIC_CELLS) == 8
        assert norm(ws["C37"].value) == ""

    @pytest.mark.parametrize("coord,formula", sorted({**MATRIX_FORMULAS_E, **MATRIX_FORMULAS_F}.items()))
    def test_matrix_formulas(self, wb, coord: str, formula: str):
        """矩阵 14 个公式逐字（3 SUMIF + 3 ISERROR 比例 + 末行无兜底）× 2 品种。"""
        ws = wb["函证结果汇总表K0-1"]
        assert norm(ws[coord].value) == formula

    def test_book_amount_row_has_no_formula(self, wb):
        """「本期（期末）账面金额」行（R29）源模板**无公式** → 手填（R3.5）。"""
        ws = wb["函证结果汇总表K0-1"]
        assert norm(ws["E29"].value) == ""
        assert norm(ws["F29"].value) == ""

    def test_last_metric_has_no_iserror_guard(self, wb):
        """🔴 末行 `(E35+E32)/E29` **无 ISERROR** → 平台侧必须自己保证不产 NaN/Inf。"""
        ws = wb["函证结果汇总表K0-1"]
        for coord in ("E36", "F36"):
            f = norm(ws[coord].value)
            assert "ISERROR" not in f, f"{coord} 竟带 ISERROR，与源模板不符"

    @pytest.mark.parametrize("coord,label", SAMPLE_SELECTION_CELLS)
    def test_sample_selection_labels(self, wb, coord: str, label: str):
        """「二、样本选择」6 项标签逐字（R1.6 / R3.6）。"""
        ws = wb["函证结果汇总表K0-1"]
        assert norm(ws[coord].value) == label

    def test_sample_selection_i32_is_empty_and_j32_holds_hint(self, wb):
        """🔴 `I32` 为空、`J32` 承载样本计算器提示 —— 6 项不是连续 6 行（R1.6）。"""
        ws = wb["函证结果汇总表K0-1"]
        assert norm(ws["I32"].value) == ""
        assert norm(ws["J32"].value) == "（如果使用了样本计算器计算样本量，样本量计算过程见<XX>底稿）"
        assert norm(ws["J36"].value) == "抽样工具中的样本选择过程和结果见<XX>底稿"

    def test_sample_process_placeholder_spans_two_cells(self, wb):
        """「抽样过程」示例被拆成 `J34`+`J35` 两格 → 拼接后才是完整句（R3.9 同族）。"""
        ws = wb["函证结果汇总表K0-1"]
        j34 = norm(ws["J34"].value)
        j35 = norm(ws["J35"].value)
        assert j34.endswith("，"), "J34 以逗号结尾 = 半句话，必须与 J35 拼接"
        assert j34 + j35 == (
            "使用IDEA（XX抽样工具）选取样本进行函证，其他应收款选择XX个债务人、金额XX的样本，"
            "其他应付款选择XX个债权人、金额XX的样本，……"
        )

    @pytest.mark.parametrize("coord,title", AUDIT_NOTE_TITLE_CELLS)
    def test_audit_note_titles(self, wb, coord: str, title: str):
        """「三、审计说明」5 项标题逐字（R1.7 / R3.7）。"""
        ws = wb["函证结果汇总表K0-1"]
        assert norm(ws[coord].value) == title

    def test_audit_note_hint_x29_x30_merged_sentence(self, wb):
        """🔴 第 2 项界定条件由 `X29`+`X30` 拼成一句（R1.7 / R3.9）。"""
        ws = wb["函证结果汇总表K0-1"]
        x29 = norm(ws["X29"].value)
        x30 = norm(ws["X30"].value)
        assert not x29.endswith("］"), "X29 单独渲染是半句话"
        assert x29 + x30 == AUDIT_NOTE_HINT_X29_X30

    def test_audit_note_hint_s33_is_standalone(self, wb):
        """第 3 项的补充说明在 `S33`，是**独立 hint**，不与标题拼接（否则出错句）。"""
        ws = wb["函证结果汇总表K0-1"]
        assert norm(ws["S33"].value) == AUDIT_NOTE_HINT_S33

    @pytest.mark.parametrize("coord,text", STANDARD_1312_SELECTION_ITEMS)
    def test_standard_1312_six_items(self, wb, coord: str, text: str):
        """编制说明含准则 1312 第十条**六项**选样要求（R1.8）。"""
        ws = wb["函证结果汇总表K0-1"]
        assert norm(ws[coord].value) == text

    @pytest.mark.parametrize("coord,text", CONFIRMATION_TIPS)
    def test_confirmation_tips_eight_items(self, wb, coord: str, text: str):
        """函证注意事项 **8 条在 B 列**（R1.8）—— 只扫 A 列会整段漏掉。"""
        ws = wb["函证结果汇总表K0-1"]
        assert norm(ws[coord].value) == text

    def test_tips_count_is_eight(self, wb):
        """B53:B60 恰 8 条，B61 无内容。"""
        ws = wb["函证结果汇总表K0-1"]
        assert len(CONFIRMATION_TIPS) == 8
        assert norm(ws["B61"].value) == ""

    @pytest.mark.parametrize("code,label_coord,text_coord,text", REFERENCE_CONCLUSIONS)
    def test_reference_conclusions_text_in_column_b(
        self, wb, code: str, label_coord: str, text_coord: str, text: str
    ):
        """🔴 参考结论内容在 **B 列**，A 列只是 `A、`/`B、`/`C、` 标签（R1.8 / R3.10）。"""
        ws = wb["函证结果汇总表K0-1"]
        assert norm(ws[label_coord].value) == f"{code}、"
        assert norm(ws[text_coord].value) == text

    def test_preparation_note_anchors(self, wb):
        """编制说明结构锚点：`A40` 提示 / `A42` 编制说明 / `A67` 后附审计证据（R1.8）。"""
        ws = wb["函证结果汇总表K0-1"]
        assert norm(ws["A40"].value).startswith("提示：如果被询证者以传真、电子邮件等方式回函")
        assert norm(ws["A42"].value) == "编制说明："
        assert norm(ws["A43"].value) == "1、函证样本的选择："
        assert norm(ws["A52"].value) == "2、函证注意事项："
        assert norm(ws["A63"].value) == "参考结论："
        assert norm(ws["A67"].value) == "后附审计证据：询证函回函、不符事项相关资料、替代程序资料等。"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 2：K0-2 / K0-4 / K0-7 / K0-8 / K0A
# ═══════════════════════════════════════════════════════════════════════════════

#: K0-2 五段（源 R5）；`AB/AC/AD/AE/AL` 各为 rowspan 单列段
ENTITY_VERIFY_SEGMENTS = [
    ("A5:A6", "函证索引"),
    ("B5:O5", "被审计单位提供的被函证单位信息及核对（核实被函证单位信息）（注1）"),
    ("P5:AA5", "回函信息情况（回函核对记录）"),
    ("AB5:AB6", "第一次发函结果？（送抵/退回）（注2）"),
    ("AC5:AC6", "经核实的原因"),
    ("AD5:AD6", "该原因是否合理（是/否）\n（注3）"),
    ("AE5:AE6", "是否进行第二次发函？\n（是/否）"),
    ("AF5:AK5", "第二次发函的被函证单位信息"),
    ("AL5:AL6", "第二次发函结果？（送抵/退回）\n（注4）"),
]

#: K0-2 第二次发函六个叶子列（源 AF6:AK6）
SECOND_SEND_LEAF_COLUMNS = [
    ("AF", "地址"),
    ("AG", "邮编"),
    ("AH", "联系人"),
    ("AI", "联系电话"),
    ("AJ", "传真"),
    ("AK", "信息是否核查一致"),
]

#: K0-2 编制说明五条（源 `A28:A41`，标题在 `A28/A34/A36/A38/A40`，正文在其下）。
#: 说明 1 有四条子要点（`A30:A33`），其余各一条。
#: 🔴 说明 3 的「记录工号（若有）」与 K0-3 的工号要求交叉呼应（R8.4）。
ENTITY_VERIFY_GUIDANCE = [
    (
        "说明1：",
        "A28",
        [
            ("A29", "进行核实的信息应该包括单位名称，地址，以及联系人和电话。"),
            (
                "A30",
                "1.项目组可利用函证中心对接的企查查获取被函证单位地址，如果不一致的应使用多种"
                "方法来核实被函证单位的信息，如查找相关发票/合同，网站搜索，电话确认，邮件确认等，"
                "请详细记录核实的方式",
            ),
            ("A31", "2.若检查了相关支持性文件或其他公开信息，请记录所检查的详细内容。"),
            (
                "A32",
                "3.请记录确认联系人身份的过程。注意：在银行函证中，也应注意核实联系人的身份并"
                "记录工号（若有）",
            ),
            (
                "A33",
                "4.在核实结果中，应注明所检查的信息（包括单位名称、地址、联系人及电话等）"
                "是否与被函证单位信息相符。",
            ),
        ],
    ),
    (
        "说明2：",
        "A34",
        [("A35", "请详细记录核实函证被退回原因所进行的程序， 例如：询问，检查等程序的具体内容")],
    ),
    (
        "说明3：",
        "A36",
        [
            (
                "A37",
                "若退回的原因不合理或存在舞弊可能，审计项目组人员应及时告知项目负责人，"
                "并咨询有关针对舞弊的审计应对措施",
            )
        ],
    ),
    (
        "说明4：",
        "A38",
        [
            (
                "A39",
                "请跟进第二次发函的结果，记录是否送抵被函证方，对于仍被退回的函证，"
                "应进行进一步调查并考虑舞弊的可能，同时在相应底稿中记录与之相关的审计风险与"
                "对审计的影响。",
            )
        ],
    ),
    (
        "说明5：",
        "A40",
        [
            (
                "A41",
                "如果被询证者以传真、电子邮件方式回函，审计项目组应当直接接收，并验证传真、"
                "电子邮件回函的可靠性，要求被询证者在审计报告日之前寄回询证函原件",
            )
        ],
    ),
]

#: K0-2 DV 覆盖行区**非对称**：提供信息段到 24 行，回函段与二次发函段到 26 行
DV_TO_ROW24 = ["C", "J", "L", "N"]
DV_TO_ROW26 = ["P", "Q", "R", "V", "W", "X", "AB", "AD", "AE", "AK", "AL"]


class TestEntityVerify:
    def test_38_columns_five_segments(self, wb):
        """K0-2 共 38 列（A..AL），五段表头逐字（R1.9）。"""
        ws = wb["核实被函证单位信息K0-2"]
        merged = {str(r) for r in ws.merged_cells.ranges}
        for rng, label in ENTITY_VERIFY_SEGMENTS:
            assert rng in merged, f"合并区 {rng} 不存在"
            assert norm(ws[rng.split(":")[0]].value) == label
        # 列宽度校验：AL = 第 38 列
        assert get_column_letter(38) == "AL"
        assert not norm(ws["AM5"].value) and not norm(ws["AM6"].value)

    def test_preparation_guidance_five_notes(self, wb):
        """K0-2 编制说明五条逐字（R8.4）。

        🔴 `A27` 是「编制说明：」总标题，五条说明各自的标题在 `A28/A34/A36/A38/A40`。
        本常量是前端 `entityVerifyGuidance.ts` 的裁决真源，前端守卫读它交叉锁死。
        """
        ws = wb["核实被函证单位信息K0-2"]
        assert norm(ws["A27"].value) == "编制说明："
        for title, title_coord, items in ENTITY_VERIFY_GUIDANCE:
            assert norm(ws[title_coord].value) == title, (
                f"{title_coord} 应为 {title}，实际 {norm(ws[title_coord].value)!r}"
            )
            for coord, text in items:
                assert norm(ws[coord].value) == text, (
                    f"{coord} 与源模板不符：\n期望 {text!r}\n实际 {norm(ws[coord].value)!r}"
                )

    def test_guidance_note3_mentions_staff_no(self, wb):
        """说明 3 逐字含「记录工号（若有）」—— 与 K0-3 的工号要求交叉呼应（R8.4）。"""
        ws = wb["核实被函证单位信息K0-2"]
        assert "记录工号（若有）" in norm(ws["A32"].value)

    @pytest.mark.parametrize("col,label", SECOND_SEND_LEAF_COLUMNS)
    def test_second_send_leaf_columns(self, wb, col: str, label: str):
        """二次发函六个叶子列逐字（R1.9 / R8.1）。"""
        ws = wb["核实被函证单位信息K0-2"]
        assert norm(ws[f"{col}6"].value) == label

    def test_contact_columns_live_here_not_on_summary(self, wb):
        """联系人 / 联系电话在 K0-2 的 `F`/`G` 列（K0-1 剔除三列的依据，R2.6）。"""
        ws = wb["核实被函证单位信息K0-2"]
        assert norm(ws["F6"].value) == "联系人"
        assert norm(ws["G6"].value) == "联系电话"
        # 币种在整册 K0-2 表头中不存在
        headers = [norm(ws.cell(6, c).value) for c in range(1, 39)]
        assert "币种" not in headers

    def test_send_channel_dv_is_the_real_channel_source(self, wb):
        """🔴 `C7:C24` DV = 渠道 `邮寄/跟函/电子函证/其他`，经 VLOOKUP 带入 K0-1!G（R2.7）。"""
        ws = wb["核实被函证单位信息K0-2"]
        assert dv_options_at(ws, "C7") == ["邮寄", "跟函", "电子函证", "其他"]
        assert norm(ws["C6"].value) == "函证方式"

    def test_reply_medium_dv(self, wb):
        """`P7:P26` 回函方式 DV = `纸质原件/电子函证/其他介质`。"""
        ws = wb["核实被函证单位信息K0-2"]
        assert dv_options_at(ws, "P7") == ["纸质原件", "电子函证", "其他介质"]

    def test_address_verify_method_dv_six_options(self, wb):
        """`L7:L24` 地址不一致核实方式 6 项（R1.10）。"""
        ws = wb["核实被函证单位信息K0-2"]
        assert dv_options_at(ws, "L7") == [
            "发票/合同地址核实", "电话核实", "官网/公告查询", "地图查询", "邮件确认", "其他方式",
        ]

    @pytest.mark.parametrize("col", DV_TO_ROW24)
    def test_dv_coverage_stops_at_row24(self, wb, col: str):
        """🔴 提供信息段 DV 只到 **24 行**（非对称，R1.10）。"""
        ws = wb["核实被函证单位信息K0-2"]
        assert dv_formulas_at(ws, f"{col}24"), f"{col}24 应有 DV"
        assert not dv_formulas_at(ws, f"{col}25"), f"{col}25 不应有 DV（源模板只到 24 行）"

    @pytest.mark.parametrize("col", DV_TO_ROW26)
    def test_dv_coverage_reaches_row26(self, wb, col: str):
        """🔴 回函段与二次发函段 DV 到 **26 行**（非对称，R1.10）。"""
        ws = wb["核实被函证单位信息K0-2"]
        assert dv_formulas_at(ws, f"{col}26"), f"{col}26 应有 DV"

    def test_five_preparation_notes(self, wb):
        """五条编制说明锚点 `A28/A34/A36/A38/A40`（R8.4）。"""
        ws = wb["核实被函证单位信息K0-2"]
        for coord, text in [
            ("A27", "编制说明："),
            ("A28", "说明1："),
            ("A34", "说明2："),
            ("A36", "说明3："),
            ("A38", "说明4："),
            ("A40", "说明5："),
        ]:
            assert norm(ws[coord].value) == text

    def test_staff_no_requirement_in_note1(self, wb):
        """说明 1 第 3 条要求记录联系人**工号**（与 K0-3 交叉呼应，R8.4 / R10.1）。"""
        ws = wb["核实被函证单位信息K0-2"]
        assert norm(ws["A32"].value) == (
            "3.请记录确认联系人身份的过程。注意：在银行函证中，也应注意核实联系人的身份并记录工号（若有）"
        )

    def test_followup_index_typo(self, wb):
        """`AA6` 写「跟函函证控制过程（K1-11）」= 索引号笔误（真值 K0-3，R6.1）。"""
        ws = wb["核实被函证单位信息K0-2"]
        assert norm(ws["AA6"].value) == "跟函函证控制过程（K1-11）"


class TestDiffReconcile:
    def test_nine_columns(self, wb):
        """K0-4 共 9 列逐字（R1.12）。"""
        ws = wb["函证差异调节表K0-4"]
        labels = [norm(ws.cell(5, c).value) for c in range(1, 10)]
        assert labels == [
            "询证函索引号", "被询证单位名称", "账户/交易", "发函金额",
            "回函金额", "差异", "差异原因", "相关支持性证据", "是否调整",
        ]
        assert norm(ws.cell(5, 10).value) == ""

    def test_15_data_rows_and_total(self, wb):
        """数据行 `r6:r20`（15 行）+ 合计行 `r21`；`F=D-E`；三处 SUM（R1.12）。"""
        ws = wb["函证差异调节表K0-4"]
        for r in range(6, 21):
            assert norm(ws[f"F{r}"].value) == f"=D{r}-E{r}"
        assert norm(ws["A21"].value) == "合计"
        for col in ("D", "E", "F"):
            assert norm(ws[f"{col}21"].value) == f"=SUM({col}6:{col}20)"


class TestReliability:
    def test_14_columns_with_parent_header(self, wb):
        """K0-7 共 14 列，`G5:M5` 父表头「期末未收回原件函证可靠性验证」（R1.14 / R9.2）。"""
        ws = wb["邮件传真回函可靠性验证K0-7"]
        merged = {str(r) for r in ws.merged_cells.ranges}
        assert "G5:M5" in merged
        assert norm(ws["G5"].value) == "期末未收回原件函证可靠性验证"
        base = [norm(ws[f"{c}5"].value) for c in ("A", "B", "C", "D", "E", "F")]
        assert base == ["序号", "函证索引号", "被询证单位名称", "回函方式",
                        "是否由审计项目组直接接收", "是否寄回原件"]
        leaves = [norm(ws[f"{c}6"].value) for c in ("G", "H", "I", "J", "K", "L", "M")]
        assert leaves == [
            "被函证者身份确认（注1）", "发函及回函传真信息及验证", "发函邮箱", "回函邮箱",
            "邮箱可靠性验证（注2）", "是否致电被函证者确认", "对函证信息可靠性的考虑（注3）",
        ]
        assert norm(ws["N5"].value) == "回函可靠性结论"
        assert norm(ws["O5"].value) == "" and norm(ws["O6"].value) == ""

    def test_no_reply_date_column(self, wb):
        """🔴 K0-7 源模板**无「回函日期」列**（R1.14 / R9.3）。"""
        ws = wb["邮件传真回函可靠性验证K0-7"]
        headers = {norm(ws.cell(r, c).value) for r in (5, 6) for c in range(1, 15)}
        assert "回函日期" not in headers

    def test_reply_method_dv_only_two_options(self, wb):
        """`D7:D16` 回函方式 DV 只有 `传真/电子邮件`（本表只管电子形式回函）。"""
        ws = wb["邮件传真回函可靠性验证K0-7"]
        assert dv_options_at(ws, "D7") == ["传真", "电子邮件"]


class TestFraudRisk:
    def test_19_indicators_plus_extensible_row_and_summary(self, wb):
        """19 条迹象（r6:r24）+ `A25 ……` 可扩行 + `A26` 汇总行且 `H26='B50'`（R1.15）。"""
        ws = wb["函证程序舞弊风险评价表K0-8"]
        items = [norm(ws.cell(r, 1).value) for r in range(6, 25)]
        assert len(items) == 19
        assert all(items), "19 条迹象不得有空行"
        assert items[0] == "1.管理层不允许寄发询证函；"
        assert items[-1].startswith("19.第三方对函证信息有误的询证函")
        assert norm(ws["A25"].value) == "……"
        assert norm(ws["A26"].value).startswith("汇总上述所有已发现的舞弊迹象")
        assert norm(ws["H26"].value) == "B50"

    def test_column_headers(self, wb):
        ws = wb["函证程序舞弊风险评价表K0-8"]
        assert norm(ws["A5"].value) == "与函证程序有关的舞弊风险迹象"
        assert [norm(ws[f"{c}5"].value) for c in ("G", "H", "I")] == [
            "是否存在", "索引号或信息来源", "应对措施",
        ]

    def test_two_tooltip_examples(self, wb):
        """两条 tooltip 举例位于 `J19`/`J20`（第 14 / 15 条，R1.15）。"""
        ws = wb["函证程序舞弊风险评价表K0-8"]
        assert norm(ws["J19"].value).startswith("例如：银行函证未回函；")
        assert norm(ws["J20"].value).startswith("例如：被审计单位及其管理层能够对被询证者施加重大影响")
        assert norm(ws["A19"].value) == "14.不正常的回函率；"
        assert norm(ws["A20"].value).startswith("15.被询证者缺乏独立性；")


class TestProgramTable:
    def test_twelve_procedures(self, wb):
        """K0A 共 12 条程序（r6:r17），第 13 行无内容（R1.16）。"""
        ws = wb["函证程序表K0A"]
        seqs = [norm(ws.cell(r, 1).value) for r in range(6, 18)]
        assert seqs == [str(i) for i in range(1, 13)]
        assert norm(ws.cell(18, 1).value) == ""

    def test_program_category_values(self, wb):
        """D 列「程序分类」取值集合 + 第 12 条为 `常规★`（R1.16）。"""
        ws = wb["函证程序表K0A"]
        cats = [norm(ws.cell(r, 4).value) for r in range(6, 18)]
        assert set(cats) == {"常规★", "备选", "舞弊应对/IPO/上市/新三板/重组"}
        assert cats[1] == "舞弊应对/IPO/上市/新三板/重组", "第 2 条是舞弊应对/IPO 类"
        assert cats[11] == "常规★", "第 12 条为常规★"

    def test_workpaper_index_column(self, wb):
        """E 列底稿索引号逐字，含 `K0-1/K0-2//K0-4` 双斜杠事实；第 8、12 条无索引（R1.16）。"""
        ws = wb["函证程序表K0A"]
        refs = [norm(ws.cell(r, 5).value) for r in range(6, 18)]
        assert refs == [
            "K0-1",
            "K0-1",
            "K0-2",
            "K0-1/K0-3",
            "K0-1/K0-2",
            "K0-1/K0-2//K0-4",   # 🔴 源模板双斜杠，按原样登记
            "K0-1/K0-7",
            "",                   # 第 8 条（第三方平台评估）无底稿索引
            "K0-1/K0-2",
            "K0-1/K0-5/K0-6",
            "K0-8",
            "",                   # 第 12 条（管理层不允许寄发）无底稿索引
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# Task 3：K0-3 跟函 / K0-5·K0-6 替代程序 / 笔误登记
# ═══════════════════════════════════════════════════════════════════════════════

#: K0-3 三个控制点（源 A23:A25，DV `是,否` 在 C 列）
FOLLOWUP_CONTROL_POINTS = [
    ("A23", "是否了解处理函证的通常流程和处理人员"),
    ("A24", "是否确认询证函处理人员的身份及权限"),
    ("A25", "处理人员是否按正常流程处理"),
]


class TestFollowup:
    def test_two_scenario_scripts(self, wb):
        """两套话术锚点：即时确认 `A10:A13` / 留函待寄回 `A15:A17`（R1.11）。"""
        ws = wb["跟函函证过程控制K0-3"]
        assert norm(ws["A5"].value).startswith("直接至被函证方公司进行函证（“跟函”）程序的记录")
        assert norm(ws["A10"].value).startswith("审计项目组成员[XXX…]于[202X年XX月XX日]")
        assert norm(ws["A14"].value).startswith("*若被函证单位无法即时确认函证")
        assert norm(ws["A15"].value).startswith("审计项目组成员[XX…]于[202X年XX月XX日]至[被函证单位全称]")

    def test_staff_no_placeholder_in_both_scripts(self, wb):
        """🔴 `A13`/`A17` 逐字含「工号为[XX]（如有）」（R1.11 / R10.1）。"""
        ws = wb["跟函函证过程控制K0-3"]
        assert "工号为[XX]（如有）" in norm(ws["A13"].value)
        assert "工号为[XX]（如有）" in norm(ws["A17"].value)

    def test_phone_revisit_confirms_visit_fact(self, wb):
        """🔴 电话回访段 `A18`+`A19` 要求确认「确实于[日期]接待我们的跟函人员」（R1.11 / R10.2）。"""
        ws = wb["跟函函证过程控制K0-3"]
        a18 = norm(ws["A18"].value)
        a19 = norm(ws["A19"].value)
        assert a18.endswith("确认其确实于"), "A18 单独渲染是半句话，须与 A19 拼接"
        assert (a18 + a19).endswith("接待我们的跟函人员，确认[发函公司名称]的函证。")
        assert "对外公开电话" in a18

    def test_post_hoc_record(self, wb):
        """事后收回补记段（`A20` 提示 + `A21` 话术）（R1.11）。"""
        ws = wb["跟函函证过程控制K0-3"]
        assert norm(ws["A20"].value).startswith("注：如果在完成本备忘录之后才收回函证")
        assert norm(ws["A21"].value).startswith("该函证于[202X年XX月XX日]寄回致同会计师事务XX办公室")

    @pytest.mark.parametrize("coord,text", FOLLOWUP_CONTROL_POINTS)
    def test_three_control_points(self, wb, coord: str, text: str):
        """3 个控制点逐字（R1.11）。"""
        ws = wb["跟函函证过程控制K0-3"]
        assert norm(ws[coord].value) == text

    def test_control_point_dv_and_signature(self, wb):
        """控制点 DV 在 **C 列**（`C23:C25` = 是/否）+ 签名行 `A27`（R1.11）。"""
        ws = wb["跟函函证过程控制K0-3"]
        for r in (23, 24, 25):
            assert dv_options_at(ws, f"C{r}") == ["是", "否"], f"C{r} DV 应为 是/否"
        assert norm(ws["A27"].value).startswith("审计项目组成员签名：")


# ─── K0-5 / K0-6 替代程序 ─────────────────────────────────────────────────────

#: 四张检查表锚点（两表同构）
ALT_BLOCK_ANCHORS = {
    "K0-5": [
        ("A14", "1.其他应收款检查-检查期后收款"),
        ("A25", "2.其他应收款检查-形成期末余额的合同、付款审批单、支出凭单等支持性证据检查"),
        ("A37", "（1）本期借方发生额"),
        ("A47", "（2）本期贷方发生额"),
    ],
    "K0-6": [
        ("A14", "1.其他应付款检查-检查期后付款"),
        ("A25", "2.其他应付款检查-形成期末余额的合同、支出凭单、发票等支持性证据检查"),
        ("A37", "（1）本期借方发生额"),
        ("A47", "（2）本期贷方发生额"),
    ],
}

#: 样本选取 6 项（两表同构；标签在 A/H 列交错）
ALT_SAMPLING_LABELS = [
    ("A7", "测试范围："),
    ("H7", "特定样本："),
    ("A8", "抽样总体："),
    ("H8", "确定的抽样样本量："),
    ("A9", "抽样方法："),
    ("H9", "抽样过程："),
]

#: 段① 证据组（🔴 两侧对方当事人**必须不同**：K0-5「付款方」/ K0-6「收款方」）
ALT_BLOCK1_EVIDENCE = {
    "K0-5": {
        "groups": [("A15", "记账凭证"), ("F15", "银行回单"), ("I15", "支持性文件1")],
        "leaves": [
            ("F16", "日期"), ("G16", "付款方"), ("H16", "金额"),
            ("I16", "识别特征"), ("J16", "信息1"), ("K16", "信息2"),
        ],
        "counterparty": ("G16", "付款方"),
    },
    "K0-6": {
        "groups": [("A15", "记账凭证"), ("F15", "付款审批单"), ("H15", "银行回单")],
        "leaves": [
            ("F16", "日期/编号"), ("G16", "是否经过恰当审批"),
            ("H16", "日期"), ("I16", "收款方"), ("J16", "金额"),
        ],
        "counterparty": ("I16", "收款方"),
    },
}

#: 源模板红字（三处，作方法论上下文就地展示，R7.3）
ALT_RED_HINT = "检查的关键证据和要素根据被审计单位具体情况修改"
ALT_RED_HINT_CELLS = ["O15", "O26", "O38"]

#: 编制说明 3 条替代程序要点（源 B68:B70，两表逐字相同）
ALT_PREPARATION_ITEMS = [
    ("B68", "①检查本期付款、期后收货或回收；"),
    ("B69", "②检查原始凭证：合同、订货单、发票或收据、银行回单、支票存根等；"),
    ("B70", "③对回函可能性不高的、余额重大的，发函同时执行替代程序。"),
]

ALT_SHEETS = {"K0-5": "其他应收款替代程序K0-5", "K0-6": "其他应付款替代程序K0-6"}


class TestAlternativePrograms:
    @pytest.mark.parametrize("code", ["K0-5", "K0-6"])
    def test_four_check_blocks(self, wb, code: str):
        """各含 **4 张检查表**（段③按借贷拆两表）（R1.13）。"""
        ws = wb[ALT_SHEETS[code]]
        anchors = ALT_BLOCK_ANCHORS[code]
        assert len(anchors) == 4
        for coord, title in anchors:
            assert norm(ws[coord].value) == title
        assert norm(ws["A36"].value) == "3.检查本期发生额："

    @pytest.mark.parametrize("code", ["K0-5", "K0-6"])
    @pytest.mark.parametrize("coord,label", ALT_SAMPLING_LABELS)
    def test_sampling_six_items(self, wb, code: str, coord: str, label: str):
        """「一、样本选取标准与规模」6 项逐字（R1.13）。"""
        ws = wb[ALT_SHEETS[code]]
        assert norm(ws["A6"].value) == "一、样本选取标准与规模："
        assert norm(ws[coord].value) == label

    @pytest.mark.parametrize("code", ["K0-5", "K0-6"])
    def test_balance_summary_table(self, wb, code: str):
        """余额表 `A11:E11` + `E12=B12+C12-D12`（R1.13）。"""
        ws = wb[ALT_SHEETS[code]]
        assert [norm(ws.cell(11, c).value) for c in range(1, 6)] == [
            "函证项目", "年初余额", "借方发生额", "贷方发生额", "期末余额",
        ]
        assert norm(ws["E12"].value) == "=B12+C12-D12"
        assert norm(ws["A12"].value) == ("其他应收款" if code == "K0-5" else "其他应付款")

    @pytest.mark.parametrize("code", ["K0-5", "K0-6"])
    def test_block1_evidence_groups(self, wb, code: str):
        """段①证据组与叶子列逐字（R1.13 / R7.1 / R7.2）。"""
        ws = wb[ALT_SHEETS[code]]
        spec = ALT_BLOCK1_EVIDENCE[code]
        for coord, label in spec["groups"]:
            assert norm(ws[coord].value) == label
        for coord, label in spec["leaves"]:
            assert norm(ws[coord].value) == label
        # 记账凭证组固定五列（两表相同）
        assert [norm(ws.cell(16, c).value) for c in range(1, 6)] == [
            "日期", "凭证编号", "业务内容", "对方科目", "金额",
        ]

    def test_block1_counterparty_labels_must_differ(self, wb):
        """🔴🔴 K0-5「付款方」vs K0-6「收款方」**必须不同**（R7.1 / R7.6）。

        反向自检：两侧统一成同一个词即打红 —— 其他应收款是收回款项（对方是付款方），
        其他应付款是对外付款（对方是收款方），统一用词等于把业务方向搞反。
        """
        ws5 = wb[ALT_SHEETS["K0-5"]]
        ws6 = wb[ALT_SHEETS["K0-6"]]
        coord5, decl5 = ALT_BLOCK1_EVIDENCE["K0-5"]["counterparty"]
        coord6, decl6 = ALT_BLOCK1_EVIDENCE["K0-6"]["counterparty"]
        v5 = norm(ws5[coord5].value)
        v6 = norm(ws6[coord6].value)
        # 常量声明必须与源模板逐字一致（否则改常量不打红 = 断言空转）
        assert (decl5, decl6) == (v5, v6), f"常量声明与源模板漂移: {(decl5, decl6)} != {(v5, v6)}"
        assert v5 == "付款方" and v6 == "收款方"
        assert v5 != v6, "两侧对方当事人用词相同 = 业务方向被搞反"

    @pytest.mark.parametrize("code", ["K0-5", "K0-6"])
    def test_support_doc_triplets_in_block2_and_3(self, wb, code: str):
        """段②/③ 的 `支持性文件1/2` 各三列（识别特征/信息1/信息2）（R7.2 同族）。"""
        ws = wb[ALT_SHEETS[code]]
        for grow, lrow in ((26, 27), (38, 39), (48, 49)):
            assert norm(ws[f"F{grow}"].value) == "支持性文件1"
            assert norm(ws[f"I{grow}"].value) == "支持性文件2"
            assert [norm(ws.cell(lrow, c).value) for c in range(6, 12)] == [
                "识别特征", "信息1", "信息2", "识别特征", "信息1", "信息2",
            ]

    @pytest.mark.parametrize("code", ["K0-5", "K0-6"])
    @pytest.mark.parametrize("coord", ALT_RED_HINT_CELLS)
    def test_red_hint_three_places(self, wb, code: str, coord: str):
        """源模板红字三处（`O15`/`O26`/`O38`）；`O48` **没有**（R7.3）。"""
        ws = wb[ALT_SHEETS[code]]
        assert norm(ws[coord].value) == ALT_RED_HINT
        assert norm(ws["O48"].value) == "", "O48 源模板无红字提示，勿凭空补第 4 处"

    @pytest.mark.parametrize("code", ["K0-5", "K0-6"])
    def test_note_and_conclusion_anchors(self, wb, code: str):
        """`A57 三、审计说明` / `A61 四、审计结论`（R1.13）。"""
        ws = wb[ALT_SHEETS[code]]
        assert norm(ws["A57"].value) == "三、审计说明："
        assert norm(ws["A61"].value) == "四、审计结论："
        assert norm(ws["A10"].value) == "二、检查过程记录："

    @pytest.mark.parametrize("code", ["K0-5", "K0-6"])
    @pytest.mark.parametrize("coord,text", ALT_PREPARATION_ITEMS)
    def test_preparation_three_items(self, wb, code: str, coord: str, text: str):
        """编制说明 3 条替代程序要点逐字（R1.13 / R7.4）。"""
        ws = wb[ALT_SHEETS[code]]
        assert norm(ws["A66"].value) == "编制说明："
        assert norm(ws["A67"].value) == "1、函证替代程序："
        assert norm(ws[coord].value) == text

    def test_k05_m46_sum_over_index_text_column_is_a_typo(self, wb):
        """🔴 `K0-5!M46 = SUM(M40:M45)` 对「索引号」文本列求和 = 源模板笔误（R7.5）。

        旁证：K0-6 同位置**无**该公式；且 M 列表头是「索引号」。→ 不实现该合计。
        """
        ws5 = wb[ALT_SHEETS["K0-5"]]
        ws6 = wb[ALT_SHEETS["K0-6"]]
        assert norm(ws5["M38"].value) == "索引号", "M 列是索引号（文本列）"
        assert norm(ws5["M46"].value) == "=SUM(M40:M45)"
        assert norm(ws6["M46"].value) == "", "K0-6 同位置无该公式 → 旁证 K0-5 是笔误"
        # 各表金额合计只在 E 列（与 M 列文本求和形成对照）
        for coord in ("E23", "E34", "E46", "E56"):
            assert norm(ws5[coord].value).startswith("=SUM(")


# ═══════════════════════════════════════════════════════════════════════════════
# 笔误登记 + 反向自检（Property 1.17 / 13）
# ═══════════════════════════════════════════════════════════════════════════════


class TestSourceTemplateTypos:
    def test_registry_has_five_entries(self):
        """5 条笔误逐条登记（供前端 `K0_INDEX_TYPO_MAP` 交叉锁死，R6.4）。"""
        assert len(SOURCE_TEMPLATE_TYPOS) == 5
        for ref, literal, intended, note in SOURCE_TEMPLATE_TYPOS:
            assert ref and literal and intended and note
            assert len(note) >= 10, f"{ref} 的说明过短，必须写清判据"

    def test_three_index_typos_literal_still_in_source(self, wb):
        """三处索引号笔误的**源模板原值仍在**（防「顺手修正」源 xlsx，R6.2）。"""
        assert norm(wb["函证结果汇总表K0-1"]["V6"].value) == "调节索引（K1-12）"
        assert "（K0-6）" in norm(wb["函证结果汇总表K0-1"]["S32"].value)
        assert norm(wb["核实被函证单位信息K0-2"]["AA6"].value) == "跟函函证控制过程（K1-11）"

    def test_intended_targets_exist_as_sheets(self, wb):
        """三处笔误的**意图目标**都是真实存在的 sheet（R6.1）。"""
        for target in ("K0-4", "K0-7", "K0-3"):
            assert any(s.endswith(target) for s in wb.sheetnames), f"意图目标 {target} 不存在"

    def test_intended_differs_from_literal(self):
        """反向自检：`intended` 若被改成与 `literal` 同值即打红（Property 13）。"""
        for ref, literal, intended, _ in SOURCE_TEMPLATE_TYPOS[:3]:
            assert intended not in literal, f"{ref}: intended={intended} 已出现在 literal 中 = 未修正"


class TestReverseSelfChecks:
    """反向自检：断言基准被改一字即打红（Property 1.17）。"""

    def test_norm_does_not_over_normalize(self):
        """`norm` 只去首尾空白 —— 内部空格 / 全半角差异必须保留。"""
        assert norm("  合  计 ") == "合  计"
        assert norm("页 次：") == "页 次："
        assert norm("(%)") == "(%)"          # 半角括号不得转全角
        assert norm("（一）") == "（一）"      # 全角不得转半角
        assert norm("\u3000\u3000（二）x") == "（二）x"  # 全角空格属首尾空白，会被剥离

    def test_column_map_is_bijective(self):
        """28 列的列字母 / 源标签 / 平台 key 三者各自唯一（防复制粘贴重复）。"""
        cols = [c for c, _, _ in SUMMARY_COLUMN_MAP]
        labels = [l for _, l, _ in SUMMARY_COLUMN_MAP]
        keys = [k for _, _, k in SUMMARY_COLUMN_MAP]
        assert len(SUMMARY_COLUMN_MAP) == 28
        assert len(set(cols)) == 28 and len(set(labels)) == 28 and len(set(keys)) == 28

    def test_absent_columns_are_not_in_source_labels(self, wb):
        """`COLUMNS_ABSENT_IN_SOURCE` 对应的中文列名确实不在 K0-1 表头里（R2.6）。"""
        ws = wb["函证结果汇总表K0-1"]
        headers = {header_label(ws, get_column_letter(c)) for c in range(1, 29)}
        for zh in ("联系人", "联系电话", "币种"):
            assert zh not in headers, f"K0-1 竟有「{zh}」列，剔除依据不成立"
        assert COLUMNS_ABSENT_IN_SOURCE == ["contact_person", "contact_phone", "currency"]

    def test_send_memo_is_a_group_header_not_a_column(self, wb):
        """🔴🔴 「发函询证纪要」在 `merged_cells` 里且跨 4 列 ⇒ **段头不是数据列**（R2.1）。

        这是「伪列」的判据：源 xlsx 该单元格在合并区中且跨多列 ⇒ 分组表头。
        """
        ws = wb["函证结果汇总表K0-1"]
        merged = {str(r) for r in ws.merged_cells.ranges}
        assert "C5:F5" in merged
        assert norm(ws["C5"].value) == "发函询证纪要"
        # 该段下辖 4 个真实叶子列，逐字即 R6 的 C..F
        assert [norm(ws[f"{c}6"].value) for c in ("C", "D", "E", "F")] == [
            "选取样本目的", "被询证单位名称", "账户/交易", "金额",
        ]
        # 反向自检：R6 里没有任何一列叫「发函询证纪要」
        leaves = {norm(ws.cell(6, c).value) for c in range(1, 29)}
        assert "发函询证纪要" not in leaves, "它出现在叶子行 ⇒ 不是段头，本判据失效"

    def test_entity_verify_guidance_anchors_are_in_column_a(self, wb):
        """K0-2 五条编制说明确实在 **A 列**（防把 `C26` 那类别列文字当成说明抄进来）。

        反向自检：`C26` 有内容但**不属于**编制说明段（它是回函核对块的列内提示），
        若把它算进 `ENTITY_VERIFY_GUIDANCE` 则本断言打红。
        """
        ws = wb["核实被函证单位信息K0-2"]
        assert norm(ws["C26"].value).startswith("2.采用电子函证方式的")
        c26 = norm(ws["C26"].value)
        for _, _, items in ENTITY_VERIFY_GUIDANCE:
            for _, text in items:
                assert text != c26, "C26 是列内提示、不是编制说明，不得混入"
        # 五条说明的锚点必须落在 A 列且连续覆盖 A28..A41
        anchors = [anchor for _, anchor, _ in ENTITY_VERIFY_GUIDANCE]
        assert anchors == ["A28", "A34", "A36", "A38", "A40"]
        assert all(a.startswith("A") for a in anchors)

    def test_dv_helper_rejects_mirror_sqref(self, wb):
        """`dv_formulas_at` 的逐格判定确实排除了镜像 sqref（helper 自检）。"""
        ws = wb["函证结果汇总表K0-1"]
        all_f = all_dv_formulas(ws)
        # 文件里有 5 组 DV，但真实格上最多命中 1 组
        assert len(all_f) >= 5, f"DV 组数异常：{len(all_f)}"
        assert len(dv_formulas_at(ws, "C7")) == 1
        assert len(dv_formulas_at(ws, "M7")) == 0
