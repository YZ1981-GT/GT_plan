"""test_l0_source_template_facts.py — L0 源模板事实守卫（xlsx 为唯一裁决者）.

spec: l0-confirmation-source-alignment
  Requirements 8.1 / 8.2
  Property 33（源模板事实守卫以 openpyxl 为裁决者且含反向自检）

本文件是 L0 全部改造的**事实基线**：openpyxl 直读源模板 xlsx（不连库、可进 CI），
后续会话不必重新精读源模板，也不能凭「常识」改动 L0 结构。

🔴 **判 DV 必须 ``coord in dv.sqref`` 逐格测试** —— openpyxl 打印的
``JF/JK/JN/TB/ACX`` 等远端列范围是 Excel 列重复产生的**镜像残留 sqref**，
**不落在真实列上**。L0-1 上就有两组这类镜像 DV（``"跟函,邮寄,电邮,其他"`` /
``"纸质原件,传真件,电子邮件,其他介质"``），按打印顺序取第一个 sqref 会得出
「L0-1!G 列（函证方式）DV = 跟函/邮寄/电邮/其他」的错误结论 —— 真实的渠道 DV 在
``L0-2!C7:C24`` 且用词不同（``邮寄,跟函,电子函证,其他``），经 VLOOKUP 带入 L0-1!G。
见 :class:`TestMirrorDataValidationTrap`。

🔴 **源模板笔误一律登记不改写**（:data:`SOURCE_TEMPLATE_TYPOS`）：按意图实现 +
tooltip 标注原值，绝不改动源 xlsx，也绝不「顺手修正」本文件常量（否则比对会打红）。
"""
from __future__ import annotations

import re
from pathlib import Path

import openpyxl
import pytest
from openpyxl.utils import get_column_letter

_REPO_ROOT = Path(__file__).resolve().parents[2]
L0_XLSX = _REPO_ROOT / "backend" / "wp_templates" / "L" / "L0 债务循环函证.xlsx"

# ─── sheet 层（9 visible + 1 hidden） ────────────────────────────────────────

#: 9 张可见 sheet，顺序逐字。
#: 🔴 程序表 tab 名是 ``函证程序表F0A`` —— 索引号笔误（底稿目录 F4=L0A 才是真源）。
EXPECTED_VISIBLE_SHEETS = [
    "底稿目录",
    "函证程序表F0A",
    "函证结果汇总表L0-1",
    "核实被函证单位信息L0-2",
    "跟函函证过程控制L0-3",
    "函证差异调节表L0-4",
    "长期应付款替代程序L0-5",
    "邮件传真回函可靠性验证L0-6",
    "函证程序舞弊风险评价表L0-7",
]

#: 唯一 hidden sheet。
#: 🔴 该 sheet 名在 **D0 / F0 中是 visible**（三处模板 openpyxl 实证）→
#: 处置**不得**按裸 sheet 名标 skip，必须走 ``{wp_code}-{sheet_name}`` 复合键。
EXPECTED_HIDDEN_SHEETS = ["函证差异检查表（示例）"]

#: L0 **没有** GT_Custom sheet（与 K0/G0 不同，勿照抄那边的断言）
NO_GT_CUSTOM = True

#: 底稿目录 `D4:F11`：(序号, 内容, 索引号)。序号列 D5 起是 `=D{n-1}+1` 递推公式。
#: 🔴 序号 1..8 连续**无跳号**（与 K0 的 `[1..5,7..10]` 跳号不同）。
INDEX_SHEET_ROWS = [
    (1, "函证程序表", "L0A"),
    (2, "函证结果汇总表", "L0-1"),
    (3, "核实被函证单位信息", "L0-2"),
    (4, "跟函函证过程控制", "L0-3"),
    (5, "函证差异调节表", "L0-4"),
    (6, "长期应付款替代程序检查表", "L0-5"),
    (7, "邮件传真回函可靠性验证", "L0-6"),
    (8, "函证程序舞弊风险评价表", "L0-7"),
]

# ─── 源模板自身笔误登记（按意图实现，绝不改源 xlsx） ─────────────────────────

#: (位置, 源模板字面, 正确值, 裁决依据)
SOURCE_TEMPLATE_TYPOS = [
    ("sheet_name:函证程序表F0A", "F0A", "L0A", "底稿目录!F4 是索引号唯一裁决者"),
    ("L0-1!V6", "调节索引（F0-4）", "L0-4", "底稿目录!F8=L0-4"),
    ("L0-2!AA6", "跟函函证控制过程（F0-3）", "L0-3", "底稿目录!F7=L0-3"),
    ("L0-1!S28", "二、审计说明", "三、审计说明", "C28=一、/ J28=二、/ C39=四、"),
]

#: 🔴 `L0-1!S33` 的「（L0-6）」是**正确索引号**，不在笔误之列。
#: 判索引号对错一律回查底稿目录 F4:F11，别看见括号就当笔误。
CORRECT_INDEX_REFS = [("L0-1!S33", "L0-6")]

# ─── L0A 程序表（12 条） ─────────────────────────────────────────────────────

PROGRAM_SHEET = "函证程序表F0A"
PROGRAM_TITLE = "长期应付款/应付债券函证程序"
PROGRAM_FIRST_ROW = 7
PROGRAM_LAST_ROW = 18

#: (seq, 程序分类, 底稿索引号)；索引号为 None 表示源模板该格为空（seq 8 / 12）
PROGRAM_CATEGORY_AND_REF = [
    (1, "常规★", "L0-1"),
    (2, "舞弊应对/IPO/上市/新三板/重组", "L0-1"),
    (3, "常规★", "L0-2"),
    (4, "常规★", "L0-1/L0-3"),
    (5, "常规★", "L0-1/L0-2"),
    (6, "常规★", "L0-1/L0-2/L0-4"),
    (7, "备选", "L0-1/L0-6"),
    (8, "备选", None),
    (9, "常规★", "L0-1/L0-2"),
    (10, "常规★", "L0-1/L0-5"),
    (11, "常规★", "L0-7"),
    (12, "常规★", None),
]

#: 程序描述的起始片段（全文过长，取首 24 字做锚点即可钉死顺序与内容）
PROGRAM_DESC_HEADS = [
    "以积极方式对长期应付款、应付债券进行函证。",
    "比较当年度及以前年度长期应付款、应付债券的增减变动",
    "设计询证函，考虑制作询证函防伪标识，并在发函前核实",
    "注册会计师直接收发询证函，跟函时观察实地场所以及函",
    "留存亲自寄发函证的寄送单回执及被审计单位盖章确认的",
    "收到的回函应为被询证者书面答复，可以采取纸质、电子",
    "如果被询证者以传真、电子邮件等方式回函，审计项目组",
    "如果利用第三方函证平台收发函证的，考虑评估第三方函",
    "分析核实退回或无法寄到的函证、未回函、回函率较低的",
    "针对再次发函未回函的项目，评价其重大错报风险以及其",
    "结合风险评估情况及函证程序执行过程中的舞弊风险迹象",
    "如果管理层不允许寄发询证函的原因不合理、或者认为回",
]

#: 两条批注（G 列）。seq 1 的批注是**银行借款排除声明** —— 公式预设取
#: `2001 短期借款` / `2501 长期借款` 恰恰违反它，是本 spec 要修的 P0 之一。
PROGRAM_HINTS = {
    1: "本函证不包含银行长期借款、银行短期借款函证，与银行借款相关函证详见货币资金循环",
    8: "第三方电子询证函平台的安全性评估内容相关要点详见函证技术提示3号，"
       "链接为：https://www.gt-china.com.cn/article_view.php?id=9682；",
}

#: 该声明明确排除的科目 —— 守卫据此反向断言公式预设不得引用
BANK_LOAN_CODES_EXCLUDED = ("2001", "2501")

# ─── L0-1 上区 28 列 → 平台列 key（本表即证据表；改一侧必须同步另一侧） ──────

SUMMARY_SHEET = "函证结果汇总表L0-1"

SUMMARY_COLUMN_MAP: list[tuple[str, str, str]] = [
    ("A", "序号", "seq"),
    ("B", "询证函索引号", "confirm_index"),
    ("C", "选取样本目的", "sample_purpose"),
    ("D", "被询证单位名称", "entity_name"),
    ("E", "账户/交易", "account_type"),
    ("F", "金额", "amount"),
    ("G", "函证方式", "send_channel"),
    ("H", "发函日期", "send_date"),
    ("I", "发函单号", "send_doc_no"),
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
    ("V", "调节索引（F0-4）", "diff_ref_index"),
    ("W", "其他说明/备注", "remark"),
    ("X", "是否采取替代程序", "use_alternative"),
    ("Y", "替代后可确认金额", "alt_confirmed"),
    ("Z", "替代后不可确认金额", "alt_unconfirmed"),
    ("AA", "替代程序索引号", "alt_ref_index"),
    ("AB", "审计结论", "row_conclusion"),
]

#: L0-1 上区六段（源模板 R5 合并区）。
#: 🔴 `C5:F5 发函询证纪要` 是**跨 4 列的段头**，不是一个数据列 —— 平台把它实现成
#: `send_memo` 单列属「伪列」（Requirement 4.1）。
#: 🔴 `AB5:AB7` 是与前五段并列的**独立末列**（rowspan 3），故 `row_conclusion`
#: 的 group 应为 `row_summary` 而非 `send_memo`（Requirement 4.3）。
SUMMARY_GROUP_HEADERS = [
    ("C5:F5", "发函询证纪要"),
    ("G5:K5", "1、发函信息"),
    ("L5:R5", "2、收到回函"),
    ("S5:W5", "3、回函金额确认"),
    ("X5:AA5", "4、未收到回函的替代程序"),
    ("AB5:AB7", "审计结论"),
]

#: 源模板 L0-1 **没有**的三列（平台 BASE 有 → 必须剔除，否则空列噪声）。
#: 联系人 / 联系电话在 L0-2 的 `F`/`G` 列；币种源模板压根没有。
COLUMNS_ABSENT_IN_SOURCE = ["contact_person", "contact_phone", "currency"]

#: 七条 VLOOKUP（L0-1 ← L0-2），值即源模板第三参 col_index_num
EXPECTED_VLOOKUP_COL_INDEX = {
    "D": 2,   # 被询证单位名称 ← L0-2!B 被询证单位全称
    "G": 3,   # 函证方式(渠道) ← L0-2!C
    "J": 4,   # 收件地址       ← L0-2!D
    "K": 10,  # 地址核查是否一致 ← L0-2!J
    "M": 16,  # 回函方式       ← L0-2!P
    "Q": 19,  # 回函发出地址   ← L0-2!S
    "R": 22,  # 发函地址与回函地址是否一致 ← L0-2!V
}

#: 差异列派生公式（T 列）
DIFFERENCE_FORMULA_TPL = '=IF(L{r}="√",S{r}-F{r},"未回函")'

#: 上区数据行区间
SUMMARY_DATA_FIRST_ROW = 8
SUMMARY_DATA_LAST_ROW = 27

# ─── L0-1 下区四块 ───────────────────────────────────────────────────────────

#: 四块段头。🔴 `S28` 源字面是「二、审计说明」= 序号笔误（见 SOURCE_TEMPLATE_TYPOS）
LOWER_ZONE_BLOCKS = [
    ("C28", "一、函证情况"),
    ("J28", "二、样本选择"),
    ("S28", "二、审计说明"),
    ("C39", "四、审计结论"),
]

#: 矩阵品种列头（源 E29/F29）—— **固定 2 个**，无 `……` 可扩位
MATRIX_CATEGORIES = [("E29", "长期应付款"), ("F29", "应付债券")]

#: 矩阵标签列表头（源 C29）
MATRIX_LABEL_HEADER = ("C29", "项目")

#: 8 指标（源 C30:C37，含行尾冒号）
MATRIX_METRIC_CELLS = [
    ("C30", "本期（期末）账面金额："),
    ("C31", "抽取样本的发函金额："),
    ("C32", "发函金额占账面金额的比例(%)："),
    ("C33", "回函确认金额："),
    ("C34", "回函可确认金额占发函金额的比例(%)："),
    ("C35", "回函可确认金额占账面金额的比例(%)："),
    ("C36", "替代测试确认金额："),
    ("C37", "回函和替代确认金额占账面金额的比例(%)："),
]

#: 矩阵公式模板：`{col}` = 品种列（E/F），`{cat}` = 品种名所在格（E29/F29）。
#: 🔴 与 F0-1 / G0-1 的 8 指标**逐条同构** —— 前端 `buildL0SummaryMatrix` 与
#: `buildF0SummaryMatrix` 的同源性守卫据此成立（Property 9）。
#: 🔴 `{col}30`（账面金额）**无公式** = 录入位，由后端语义科目定位下发种子值。
MATRIX_FORMULA_TPL = {
    31: "=SUMIF(E8:E27,{cat},F8:F27)",
    32: "=IF(ISERROR({col}31/{col}30),0,{col}31/{col}30)",
    33: "=SUMIF(E8:E27,{cat},U8:U27)",
    34: "=IF(ISERROR({col}33/{col}31),0,{col}33/{col}31)",
    35: "=IF(ISERROR({col}33/{col}30),0,{col}33/{col}30)",
    36: "=SUMIF(E8:E27,{cat},Y8:Y27)",
    37: "=({col}36+{col}33)/{col}30",
}

#: 「二、样本选择」6 项（源 J 列标签 / K 列示例文本）。
#: 🔴 `K33` 是 `J32` 的括注、`K36` 是 `K35` 的**续行** —— 不是独立录入项。
SAMPLE_SELECTION_LABELS = [
    ("J29", "测试总体："),
    ("J30", "特定样本："),
    ("J31", "抽样总体："),
    ("J32", "确定的抽样样本量："),
    ("J34", "抽样方法："),
    ("J35", "抽样过程："),
]
SAMPLE_SELECTION_PARENTHETICALS = [
    ("K33", "（如果使用了样本计算器计算样本量，样本量计算过程见<XX>底稿）"),
]
#: 拆两格的续行对（前格以逗号结尾即续行标志）
SAMPLE_SELECTION_CONTINUATIONS = [("K35", "K36")]

#: 「三、审计说明」5 段（源模板序号 1~5）
AUDIT_NOTE_LABELS = [
    ("S29", "1、对询证函保持的控制的说明"),
    ("W29", "2、对误差的分析"),
    ("S33", "3、对以传真或电子邮件形式收到的回函的可靠性的考虑（L0-6）"),
    ("S34", "4、针对不符事项的程序"),
    ("S36", "5、针对未回函的替代程序"),
]
#: 三处「一句话拆两格」—— 只取前格会渲染出半句话
AUDIT_NOTE_CONTINUATIONS = [("W30", "W31"), ("S34", "S35")]

#: 参考结论三条 + 后附证据（源 A65:B68 / A69），只读展示
REFERENCE_CONCLUSION_CELLS = [
    ("A65", "参考结论："),
    ("B66", "未见异常。"),
    ("B67", "除以下重大不符事项应当作为调整事项予以调整外，其余未见异常。"),
    ("B68", "由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。"),
    ("A69", "后附审计证据：询证函回函、不符事项相关资料、替代程序资料等。"),
]

# ─── 数据有效性（真实格 vs 镜像残留） ────────────────────────────────────────

#: L0-1 上**真实**生效的 DV：{首格坐标: 枚举串}
L01_REAL_DV = {
    "C8": "A. 大额,B.异常,C.余额为0,D.账龄长,E.随机",
    "L8": "√,×",
    "N8": "√,×",
    "X8": "√,×",
}

#: L0-1 上的**镜像残留** DV 枚举串 —— 存在于文件中但不落在 A..AB 任何真实格。
#: 🔴 用词与真实渠道 DV 不同（`电邮` vs `电子函证`），是「不可信」的铁证。
L01_MIRROR_ONLY_DV = [
    "跟函,邮寄,电邮,其他",
    "纸质原件,传真件,电子邮件,其他介质",
]

#: L0-2 上真实生效的 DV（与 X0-2 六枢纽同构）
L02_REAL_DV = {
    "C7": "邮寄,跟函,电子函证,其他",
    "L7": "发票/合同地址核实,电话核实,官网/公告查询,地图查询,邮件确认,其他方式",
    "P7": "纸质原件,电子函证,其他介质",
    "J7": "是,否",
    "AB7": "送抵,退回",
}

# ─── L0-5 替代程序段标题 ─────────────────────────────────────────────────────

ALT_SHEET = "长期应付款替代程序L0-5"

#: 源模板段标题。🔴 平台区块标题须对齐这些字面（Requirement 7.1~7.3）：
#: block2 不得含「银行对账单」「借款合同」（与 seq 1 的银行借款排除声明矛盾）。
ALT_SECTION_TITLES = [
    ("A5", "一、样本选取标准与规模："),
    ("A9", "二、检查过程记录："),
    ("A13", "1、检查期后付款"),
    ("A20", "2、检查构成期末长期应付款余额的支持性文件（如合同等）"),
    ("A27", "3、检查期初余额是否与上期期末余额一致："),
    ("A28", "4、测试本期发生额："),
    ("A29", "（1）本期借方发生额"),
    ("A37", "（2）本期贷方发生额"),
    ("A45", "三、审计说明："),
    ("A49", "四、审计结论："),
]

#: L0-5 roll-forward 表：E11 = 年初 + 贷方 − 借方
ALT_ROLLFORWARD_FORMULA = ("E11", "=B11+D11-C11")

#: block2 标题禁用词（与银行借款排除声明矛盾）
ALT_BLOCK2_FORBIDDEN_WORDS = ["银行对账单", "借款合同"]


# ─── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def wb():
    assert L0_XLSX.exists(), f"源模板缺失: {L0_XLSX}"
    book = openpyxl.load_workbook(L0_XLSX, data_only=False)
    yield book
    book.close()


def _norm(v) -> str:
    """归一：去首尾空白 + 折叠内部连续空白（源模板存在「合 计」式空格）。"""
    return re.sub(r"\s+", "", str(v or ""))


# ─── Property 33：sheet 层 ───────────────────────────────────────────────────


class TestSheetLayer:
    def test_visible_sheets_exact(self, wb):
        actual = [s for s in wb.sheetnames if wb[s].sheet_state == "visible"]
        assert actual == EXPECTED_VISIBLE_SHEETS

    def test_hidden_sheets_exact(self, wb):
        actual = [s for s in wb.sheetnames if wb[s].sheet_state != "visible"]
        assert actual == EXPECTED_HIDDEN_SHEETS

    def test_no_gt_custom_sheet(self, wb):
        """L0 没有 GT_Custom（与 K0/G0 不同）——勿照抄那边的断言。"""
        assert NO_GT_CUSTOM
        assert "GT_Custom" not in wb.sheetnames

    def test_sheet_count(self, wb):
        assert len(wb.sheetnames) == 10

    def test_program_sheet_name_carries_f0a_typo(self, wb):
        """程序表 tab 名带 F0A 是源模板事实，不得「顺手修正」。"""
        assert PROGRAM_SHEET in wb.sheetnames
        assert PROGRAM_SHEET.endswith("F0A")
        assert "函证程序表L0A" not in wb.sheetnames


class TestIndexSheet:
    def test_index_rows_content_and_ref(self, wb):
        ws = wb["底稿目录"]
        for i, (_seq, name, ref) in enumerate(INDEX_SHEET_ROWS):
            r = 4 + i
            assert _norm(ws[f"E{r}"].value) == _norm(name), f"E{r}"
            assert _norm(ws[f"F{r}"].value) == _norm(ref), f"F{r}"

    def test_index_seq_is_recursive_formula(self, wb):
        """D4 是字面 1，D5 起是 `=D{n-1}+1` 递推 → 序号 1..8 连续无跳号。"""
        ws = wb["底稿目录"]
        assert ws["D4"].value == 1
        for r in range(5, 12):
            assert ws[f"D{r}"].value == f"=D{r - 1}+1", f"D{r}"
        assert [s for s, _n, _r in INDEX_SHEET_ROWS] == list(range(1, 9))

    def test_index_sheet_is_the_ref_authority(self, wb):
        """底稿目录 F4=L0A 是索引号真源，与 tab 名的 F0A 分歧即笔误登记依据。"""
        ws = wb["底稿目录"]
        assert _norm(ws["F4"].value) == "L0A"
        assert PROGRAM_SHEET.endswith("F0A")


# ─── Property 33：L0A 程序表 ────────────────────────────────────────────────


class TestProgramSheet:
    def test_title(self, wb):
        assert _norm(wb[PROGRAM_SHEET]["A2"].value) == _norm(PROGRAM_TITLE)

    def test_twelve_programs(self, wb):
        ws = wb[PROGRAM_SHEET]
        rows = [
            r for r in range(PROGRAM_FIRST_ROW, PROGRAM_LAST_ROW + 1)
            if str(ws[f"B{r}"].value or "").strip()
        ]
        assert len(rows) == 12
        assert rows == list(range(PROGRAM_FIRST_ROW, PROGRAM_LAST_ROW + 1))

    @pytest.mark.parametrize("idx", range(12))
    def test_program_desc_head(self, wb, idx):
        ws = wb[PROGRAM_SHEET]
        r = PROGRAM_FIRST_ROW + idx
        desc = str(ws[f"B{r}"].value or "")
        assert desc.startswith(PROGRAM_DESC_HEADS[idx]), f"B{r} 首段不符"

    @pytest.mark.parametrize("seq,category,ref", PROGRAM_CATEGORY_AND_REF)
    def test_program_category_and_ref(self, wb, seq, category, ref):
        ws = wb[PROGRAM_SHEET]
        r = PROGRAM_FIRST_ROW + seq - 1
        assert _norm(ws[f"A{r}"].value) == str(seq), f"A{r} 序号"
        assert _norm(ws[f"D{r}"].value) == _norm(category), f"D{r} 程序分类"
        actual_ref = ws[f"E{r}"].value
        if ref is None:
            assert not str(actual_ref or "").strip(), f"E{r} 应为空（源模板事实）"
        else:
            assert _norm(actual_ref) == _norm(ref), f"E{r} 底稿索引号"

    def test_category_distribution(self, wb):
        """常规★ ×9 / 舞弊应对… ×1 / 备选 ×2 = 12。"""
        cats = [c for _s, c, _r in PROGRAM_CATEGORY_AND_REF]
        assert cats.count("常规★") == 9
        assert cats.count("舞弊应对/IPO/上市/新三板/重组") == 1
        assert cats.count("备选") == 2
        assert len(cats) == 12

    def test_ref_index_never_points_to_f0(self, wb):
        """底稿索引号全指 L0-* —— 平台若加载到 F0A 模板，ref 会变 F0-*（P0 判据）。"""
        for _seq, _cat, ref in PROGRAM_CATEGORY_AND_REF:
            if ref:
                assert "F0-" not in ref, f"索引号不应出现 F0-：{ref}"
                assert ref.startswith("L0-"), ref

    @pytest.mark.parametrize("seq,hint", sorted(PROGRAM_HINTS.items()))
    def test_program_hint(self, wb, seq, hint):
        ws = wb[PROGRAM_SHEET]
        r = PROGRAM_FIRST_ROW + seq - 1
        assert _norm(ws[f"G{r}"].value) == _norm(hint), f"G{r} 批注"

    def test_bank_loan_exclusion_declared(self, wb):
        """seq 1 的批注明确排除银行长/短期借款 —— 公式预设取 2001/2501 违反它。"""
        ws = wb[PROGRAM_SHEET]
        hint = str(ws[f"G{PROGRAM_FIRST_ROW}"].value or "")
        assert "不包含银行长期借款" in hint
        assert "银行短期借款" in hint
        assert "货币资金循环" in hint
        assert BANK_LOAN_CODES_EXCLUDED == ("2001", "2501")


# ─── Property 33：L0-1 上区 ────────────────────────────────────────────────


class TestSummaryUpperZone:
    @pytest.mark.parametrize("col,label,key", SUMMARY_COLUMN_MAP)
    def test_column_label(self, wb, col, label, key):
        """28 列字面：`A/B/AB` 在第 5 行（rowspan），其余在第 6 行。"""
        ws = wb[SUMMARY_SHEET]
        row = 5 if col in ("A", "B", "AB") else 6
        assert _norm(ws[f"{col}{row}"].value) == _norm(label), f"{col}{row}"
        assert key  # 平台列 key 非空（证据表两侧齐备）

    def test_column_count(self, wb):
        assert len(SUMMARY_COLUMN_MAP) == 28
        assert [c for c, _l, _k in SUMMARY_COLUMN_MAP] == [
            get_column_letter(i) for i in range(1, 29)
        ]

    @pytest.mark.parametrize("rng,label", SUMMARY_GROUP_HEADERS)
    def test_group_header_merged(self, wb, rng, label):
        ws = wb[SUMMARY_SHEET]
        merged = {str(r) for r in ws.merged_cells.ranges}
        assert rng in merged, f"{rng} 应为合并区"
        anchor = rng.split(":")[0]
        assert _norm(ws[anchor].value) == _norm(label), anchor

    def test_send_memo_is_group_header_not_column(self, wb):
        """`C5:F5 发函询证纪要` 跨 4 列 = 段头（伪列判据，Requirement 4.1）。"""
        ws = wb[SUMMARY_SHEET]
        merged = {str(r) for r in ws.merged_cells.ranges}
        assert "C5:F5" in merged
        assert _norm(ws["C5"].value) == "发函询证纪要"
        # 该段下辖的 4 个真实列各有自己的第 6 行 label
        for col in ("C", "D", "E", "F"):
            assert str(ws[f"{col}6"].value or "").strip(), f"{col}6 应有列名"

    def test_row_conclusion_is_independent_last_column(self, wb):
        """`AB5:AB7` rowspan → 审计结论是五段之外的独立末列（group=row_summary）。"""
        ws = wb[SUMMARY_SHEET]
        merged = {str(r) for r in ws.merged_cells.ranges}
        assert "AB5:AB7" in merged
        assert _norm(ws["AB5"].value) == "审计结论"
        assert not str(ws["AB6"].value or "").strip()

    @pytest.mark.parametrize("key", COLUMNS_ABSENT_IN_SOURCE)
    def test_absent_columns_have_no_source_label(self, wb, key):
        """反向断言：源模板 28 列表头不含联系人/联系电话/币种。"""
        ws = wb[SUMMARY_SHEET]
        labels = {_norm(ws[f"{c}5"].value) + _norm(ws[f"{c}6"].value)
                  for c, _l, _k in SUMMARY_COLUMN_MAP}
        forbidden = {"contact_person": "联系人",
                     "contact_phone": "联系电话",
                     "currency": "币种"}[key]
        assert not any(forbidden in s for s in labels), f"源模板不应有「{forbidden}」列"

    @pytest.mark.parametrize("col,idx", sorted(EXPECTED_VLOOKUP_COL_INDEX.items()))
    def test_vlookup_col_index(self, wb, col, idx):
        ws = wb[SUMMARY_SHEET]
        f = str(ws[f"{col}{SUMMARY_DATA_FIRST_ROW}"].value or "")
        assert "VLOOKUP" in f, f"{col}8 应为 VLOOKUP"
        assert "核实被函证单位信息L0-2" in f, f"{col}8 应引用 L0-2"
        m = re.search(r"A:AL,(\d+),0", f)
        assert m and int(m.group(1)) == idx, f"{col}8 col_index_num 应为 {idx}"

    def test_difference_formula(self, wb):
        ws = wb[SUMMARY_SHEET]
        for r in (SUMMARY_DATA_FIRST_ROW, SUMMARY_DATA_LAST_ROW):
            assert _norm(ws[f"T{r}"].value) == _norm(DIFFERENCE_FORMULA_TPL.format(r=r))

    def test_data_row_range(self, wb):
        """上区 20 行数据位（8~27），与矩阵 SUMIF 的区间一致。"""
        assert SUMMARY_DATA_LAST_ROW - SUMMARY_DATA_FIRST_ROW + 1 == 20
        ws = wb[SUMMARY_SHEET]
        assert _norm(ws[f"A{SUMMARY_DATA_FIRST_ROW}"].value) == "1"
        assert _norm(ws[f"A{SUMMARY_DATA_LAST_ROW}"].value) == "20"

    def test_diff_ref_index_carries_f0_typo(self, wb):
        """V6 字面「调节索引（F0-4）」是笔误 → 平台展示 L0-4（Requirement 4.8）。"""
        ws = wb[SUMMARY_SHEET]
        assert _norm(ws["V6"].value) == _norm("调节索引（F0-4）")


# ─── Property 33：L0-1 下区四块 ────────────────────────────────────────────


class TestSummaryLowerZone:
    @pytest.mark.parametrize("coord,label", LOWER_ZONE_BLOCKS)
    def test_block_headers(self, wb, coord, label):
        assert _norm(wb[SUMMARY_SHEET][coord].value) == _norm(label), coord

    def test_audit_note_section_number_is_a_typo(self, wb):
        """C28=一、/ J28=二、/ S28=二、/ C39=四、→ S28 的「二」是序号笔误。"""
        ws = wb[SUMMARY_SHEET]
        assert str(ws["C28"].value).startswith("一、")
        assert str(ws["J28"].value).startswith("二、")
        assert str(ws["S28"].value).startswith("二、")  # 笔误：应为「三、」
        assert str(ws["C39"].value).startswith("四、")

    @pytest.mark.parametrize("coord,name", MATRIX_CATEGORIES)
    def test_matrix_categories(self, wb, coord, name):
        assert _norm(wb[SUMMARY_SHEET][coord].value) == _norm(name), coord

    def test_matrix_has_exactly_two_categories_no_ellipsis(self, wb):
        """恰 2 品种且 G29 无 `……` 可扩位（与 G0 的 8 品种 + 可扩不同）。"""
        ws = wb[SUMMARY_SHEET]
        assert len(MATRIX_CATEGORIES) == 2
        assert not str(ws["G29"].value or "").strip()
        assert _norm(ws[MATRIX_LABEL_HEADER[0]].value) == _norm(MATRIX_LABEL_HEADER[1])

    @pytest.mark.parametrize("coord,label", MATRIX_METRIC_CELLS)
    def test_matrix_metric_labels(self, wb, coord, label):
        assert _norm(wb[SUMMARY_SHEET][coord].value) == _norm(label), coord

    def test_matrix_metric_count(self, wb):
        assert len(MATRIX_METRIC_CELLS) == 8

    def test_book_amount_row_has_no_formula(self, wb):
        """C30 行（账面金额）是**录入位**，E30/F30 无公式 → 由后端下发种子值。"""
        ws = wb[SUMMARY_SHEET]
        for col in ("E", "F"):
            v = ws[f"{col}30"].value
            assert not (isinstance(v, str) and v.startswith("=")), f"{col}30 不应有公式"

    @pytest.mark.parametrize("row", sorted(MATRIX_FORMULA_TPL))
    @pytest.mark.parametrize("col,cat", [("E", "E29"), ("F", "F29")])
    def test_matrix_formulas(self, wb, row, col, cat):
        ws = wb[SUMMARY_SHEET]
        expected = MATRIX_FORMULA_TPL[row].format(col=col, cat=cat)
        assert _norm(ws[f"{col}{row}"].value) == _norm(expected), f"{col}{row}"

    def test_sumif_criteria_column_is_account_type(self, wb):
        """三条 SUMIF 的 criteria_range 恒为 `E8:E27`（账户/交易列）。"""
        ws = wb[SUMMARY_SHEET]
        for row in (31, 33, 36):
            for col in ("E", "F"):
                f = str(ws[f"{col}{row}"].value or "")
                assert "SUMIF(E8:E27," in f.replace(" ", ""), f"{col}{row}"

    def test_sumif_sum_ranges(self, wb):
        """发函金额取 F 列、回函确认取 U 列、替代确认取 Y 列。"""
        ws = wb[SUMMARY_SHEET]
        assert "F8:F27" in str(ws["E31"].value)
        assert "U8:U27" in str(ws["E33"].value)
        assert "Y8:Y27" in str(ws["E36"].value)

    @pytest.mark.parametrize("coord,label", SAMPLE_SELECTION_LABELS)
    def test_sample_selection_labels(self, wb, coord, label):
        assert _norm(wb[SUMMARY_SHEET][coord].value) == _norm(label), coord

    def test_sample_selection_count(self, wb):
        assert len(SAMPLE_SELECTION_LABELS) == 6

    @pytest.mark.parametrize("coord,text", SAMPLE_SELECTION_PARENTHETICALS)
    def test_sample_parentheticals_are_not_entries(self, wb, coord, text):
        """K33 是 J32 的括注（J33 无标签）→ 作提示文本不作独立录入项。"""
        ws = wb[SUMMARY_SHEET]
        assert _norm(ws[coord].value) == _norm(text), coord
        j_coord = "J" + coord[1:]
        assert not str(ws[j_coord].value or "").strip(), f"{j_coord} 应无标签"

    @pytest.mark.parametrize("head,tail", SAMPLE_SELECTION_CONTINUATIONS)
    def test_sample_continuation_pairs(self, wb, head, tail):
        """K35 以逗号结尾、K36 是其续行 → 必须合并渲染，否则界面出现半句话。"""
        ws = wb[SUMMARY_SHEET]
        h = str(ws[head].value or "").strip()
        t = str(ws[tail].value or "").strip()
        assert h and t
        assert h.endswith(("，", ",")), f"{head} 应以逗号结尾（续行标志）"
        j_tail = "J" + tail[1:]
        assert not str(ws[j_tail].value or "").strip(), f"{j_tail} 应无标签"

    @pytest.mark.parametrize("coord,label", AUDIT_NOTE_LABELS)
    def test_audit_note_labels(self, wb, coord, label):
        assert _norm(wb[SUMMARY_SHEET][coord].value) == _norm(label), coord

    def test_audit_note_count(self, wb):
        assert len(AUDIT_NOTE_LABELS) == 5

    @pytest.mark.parametrize("head,tail", AUDIT_NOTE_CONTINUATIONS)
    def test_audit_note_continuation_pairs(self, wb, head, tail):
        ws = wb[SUMMARY_SHEET]
        assert str(ws[head].value or "").strip()
        assert str(ws[tail].value or "").strip()

    def test_error_threshold_sentence_split_across_two_cells(self, wb):
        """W30+W31 拼成完整句；单取 W30 会得到没有右方括号的半句。"""
        ws = wb[SUMNAME := SUMMARY_SHEET]
        head = str(ws["W30"].value or "")
        tail = str(ws["W31"].value or "")
        assert "［" in head and "］" not in head
        assert "］" in tail
        assert "万元" in tail
        assert SUMNAME == SUMMARY_SHEET

    @pytest.mark.parametrize("coord,text", REFERENCE_CONCLUSION_CELLS)
    def test_reference_conclusions(self, wb, coord, text):
        assert _norm(wb[SUMMARY_SHEET][coord].value) == _norm(text), coord

    def test_s33_index_ref_is_correct_not_typo(self, wb):
        """S33 的「（L0-6）」是正确索引号 —— 别看见括号就当笔误。"""
        ws = wb[SUMMARY_SHEET]
        assert "（L0-6）" in str(ws["S33"].value)
        for loc, ref in CORRECT_INDEX_REFS:
            assert loc == "L0-1!S33" and ref == "L0-6"


# ─── Property 33 / 8.2：数据有效性（真实格 vs 镜像残留） ────────────────────


class TestDataValidations:
    @pytest.mark.parametrize("coord,enum", sorted(L01_REAL_DV.items()))
    def test_l01_real_dv(self, wb, coord, enum):
        """逐格测试 `coord in dv.sqref`，不按打印顺序取第一个 sqref。"""
        ws = wb[SUMMARY_SHEET]
        hits = [
            dv for dv in ws.data_validations.dataValidation
            if coord in dv.sqref and dv.type == "list"
        ]
        assert len(hits) == 1, f"{coord} 应恰命中 1 条 list DV，实得 {len(hits)}"
        assert _norm(hits[0].formula1).strip('"') == _norm(enum)

    @pytest.mark.parametrize("coord,enum", sorted(L02_REAL_DV.items()))
    def test_l02_real_dv(self, wb, coord, enum):
        ws = wb["核实被函证单位信息L0-2"]
        hits = [
            dv for dv in ws.data_validations.dataValidation
            if coord in dv.sqref and dv.type == "list"
        ]
        assert len(hits) == 1, f"{coord} 应恰命中 1 条 list DV"
        assert _norm(hits[0].formula1).strip('"') == _norm(enum)

    def test_l01_send_channel_has_no_local_dv(self, wb):
        """L0-1!G（函证方式）**没有**本地 DV —— 值由 VLOOKUP 自 L0-2!C 带入。"""
        ws = wb[SUMMARY_SHEET]
        hits = [dv for dv in ws.data_validations.dataValidation if "G8" in dv.sqref]
        assert hits == [], "G8 不应有本地 DV（渠道枚举在 L0-2!C7:C24）"


class TestMirrorDataValidationTrap:
    """反向自检（Requirement 8.2）：镜像残留 sqref 存在但不覆盖真实格。

    这是「不能按打印顺序取第一个 sqref」的铁证 —— 若守卫写成取首个 sqref，
    会得出「L0-1!G 列 DV = 跟函/邮寄/电邮/其他」的错误结论。
    """

    @pytest.mark.parametrize("enum", L01_MIRROR_ONLY_DV)
    def test_mirror_dv_exists_in_file(self, wb, enum):
        ws = wb[SUMMARY_SHEET]
        found = [
            dv for dv in ws.data_validations.dataValidation
            if _norm(dv.formula1).strip('"') == _norm(enum)
        ]
        assert found, f"镜像 DV「{enum}」应存在于文件中（证明本自检非空转）"

    @pytest.mark.parametrize("enum", L01_MIRROR_ONLY_DV)
    def test_mirror_dv_covers_no_real_cell(self, wb, enum):
        ws = wb[SUMMARY_SHEET]
        real_cells = [
            f"{get_column_letter(c)}{r}"
            for c in range(1, 29)
            for r in range(SUMMARY_DATA_FIRST_ROW, SUMMARY_DATA_LAST_ROW + 1)
        ]
        for dv in ws.data_validations.dataValidation:
            if _norm(dv.formula1).strip('"') != _norm(enum):
                continue
            covered = [c for c in real_cells if c in dv.sqref]
            assert covered == [], f"镜像 DV「{enum}」不应覆盖真实格，实覆盖 {covered[:5]}"

    def test_mirror_enum_wording_differs_from_real_channel_dv(self, wb):
        """镜像枚举用「电邮」，真实渠道 DV 用「电子函证」→ 两者不可互替。"""
        assert "电邮" in L01_MIRROR_ONLY_DV[0]
        assert "电子函证" in L02_REAL_DV["C7"]
        assert L01_MIRROR_ONLY_DV[0] != L02_REAL_DV["C7"]


# ─── Property 31 / 7.x：L0-5 段标题 ────────────────────────────────────────


class TestAlternativeSheet:
    @pytest.mark.parametrize("coord,label", ALT_SECTION_TITLES)
    def test_section_titles(self, wb, coord, label):
        assert _norm(wb[ALT_SHEET][coord].value) == _norm(label), coord

    def test_rollforward_formula(self, wb):
        coord, formula = ALT_ROLLFORWARD_FORMULA
        assert _norm(wb[ALT_SHEET][coord].value) == _norm(formula)

    def test_block2_title_has_no_bank_wording(self, wb):
        """源模板 A20 说的是「合同等」，不含银行对账单/借款合同（呼应 seq 1 排除声明）。"""
        title = str(wb[ALT_SHEET]["A20"].value or "")
        for word in ALT_BLOCK2_FORBIDDEN_WORDS:
            assert word not in title, f"源模板 A20 不含「{word}」"
        assert "合同等" in title

    def test_block3_is_occurrence_test_not_borrowing(self, wb):
        """A28 是「测试本期发生额」，不是「本期借款检查」。"""
        assert _norm(wb[ALT_SHEET]["A28"].value) == _norm("4、测试本期发生额：")


# ─── 笔误登记完备性 ──────────────────────────────────────────────────────────


class TestTypoRegistry:
    def test_typo_registry_shape(self):
        assert len(SOURCE_TEMPLATE_TYPOS) == 4
        for loc, literal, correct, basis in SOURCE_TEMPLATE_TYPOS:
            assert loc and literal and correct and basis
            assert literal != correct, f"{loc} 笔误与正确值不应相同"
            assert len(basis) >= 8, f"{loc} 裁决依据过短"

    def test_l02_followup_ref_typo(self, wb):
        ws = wb["核实被函证单位信息L0-2"]
        assert _norm(ws["AA6"].value) == _norm("跟函函证控制过程（F0-3）")

    def test_all_registered_typos_are_observable(self, wb):
        """四处笔误逐条可在源 xlsx 观察到（防登记表变成死数据）。"""
        ws1 = wb[SUMMARY_SHEET]
        ws2 = wb["核实被函证单位信息L0-2"]
        observed = {
            "sheet_name:函证程序表F0A": PROGRAM_SHEET,
            "L0-1!V6": str(ws1["V6"].value or ""),
            "L0-2!AA6": str(ws2["AA6"].value or ""),
            "L0-1!S28": str(ws1["S28"].value or ""),
        }
        for loc, literal, _correct, _basis in SOURCE_TEMPLATE_TYPOS:
            assert literal in observed[loc], f"{loc} 的笔误字面未在源模板观察到"
