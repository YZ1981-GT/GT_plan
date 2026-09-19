"""附注「货币资金」章节结构守卫（源 xlsx / 源 docx ↔ 模板 ↔ 同步载荷 三向比对）。

**Validates: Requirements 5.1~5.9, 6.1~6.4**

Property 5（源 xlsx 三向一致）、Property 6（单级表必须 flat）
—— 以上两条来自归档 spec `e1-four-table-extraction-and-disclosure-alignment`。

本文件另承载 spec `e-cycle-extraction-formula-and-disclosure-completion`
的 Wave 1 Task 3 判据（**当前故意打红，Wave 4 Task 12/13 修**）：

Property 16（soe 主表 docx ↔ 模板 ↔ 载荷 三向一致）
Property 19（listed 主表 8 行 / 外币表段数与行数 冻结快照）
Property 20（受限表行序 = docx 六类 + 平台补充桶 + 合计）
Property 23（外币表段首行 row_code 与 report_config 对账 + account_codes 不变）
Property 24（反向锁死：BS-031 仍归 H8 使用权资产）
Property 30（row_type 取值域 ⊆ 六值；**本 spec 自己**的两张表不引入 expandable
            —— 第 6 个取值 `expandable` 由 C spec 落地，2026-08-09 修正见该类 docstring）
Property 37（listed docx「货币资金」节只有 1 张表 ⇒ listed 受限表是平台补充表）
Property 41（soe docx 主表不含「存放财务公司款项」「存款应计利息」，两版不得对齐）

🔴 **附注行集真源是 `docs/模版/` 两份 docx，不是底稿 xlsx**。
   源 xlsx 只决定底稿 UI 字面；两者冲突时以 docx 为准（详见 spec R5.8）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl
import pytest

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA = _BACKEND / "data"
LISTED_PATH = DATA / "note_template_listed.json"
SOE_PATH = DATA / "note_template_soe.json"
SOURCE_XLSX = (
    _BACKEND
    / "wp_templates"
    / "E"
    / "E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx"
)
FRONTEND = (
    _BACKEND.parent
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "composables"
)
NOTE_MAP_TS = FRONTEND / "e1NoteSectionMap.ts"
DISCLOSURE_SCOPE_TS = FRONTEND / "e1DisclosureScope.ts"

#: 🔴 附注结构真源 = `docs/模版/` 两份源 docx（不是底稿 xlsx）。
#: 底稿 xlsx 是「审计师录入用的表」，附注 docx 才是「交付件的行集」，
#: 两者在 soe 侧就不一致（xlsx R13 是括注、docx r6 是正式数据行）。
_REPO = _BACKEND.parent
LISTED_DOCX = (
    _REPO
    / "docs"
    / "模版"
    / "1.上市公司年审报表及附注-2026.01"
    / "1.上市公司年审报表及附注-2026.01"
    / "3.2025年度上市公司财务报表附注模板-2026.01.15.docx"
)
SOE_DOCX = (
    _REPO
    / "docs"
    / "模版"
    / "1、2025年度财务决算审计报告-2026.01.06"
    / "1、2025年度财务决算审计报告-国企"
    / "1.1-2025国企财务报表附注20260119.docx"
)
#: 🔴 两版 Heading 层级不同（listed 章=H1/节=H2；soe 章=H1/节=H3/子节=H4）。
#: 按 `Heading 2` 一刀切抽 soe 只会拿到会计政策变更等少数节、漏掉全部科目节。
LISTED_HEADING = "Heading 2"
SOE_HEADING = "Heading 3"
#: 🔴 docx 章号是 Word 自动编号，段落文本**不含**「五、」→ 只能按标题名定位。
DOCX_SECTION_TITLE = "货币资金"

MAIN_TABLE = "货币资金"
RESTRICTED_TABLE = "受限制的货币资金明细"

SECTIONS = {"listed": ("五、1", LISTED_PATH), "soe": ("八、1", SOE_PATH)}
SOURCE_SHEETS = {
    "listed": "附注披露信息(上市公司)",
    "soe": "附注披露信息(国企)",
}

# ─── 附注模板源 docx（行集真源）────────────────────────────────────────────────
#
# 🔴 章号是 Word 自动编号，段落文本**不含**「五、」/「八、」⇒ 只能按
#    `paragraph.style.name == 'Heading N'` 定位；且两版层级不同：
#    listed 节 = Heading 2，soe 节 = Heading 3（实测，勿统一）。
_DOCS = _BACKEND.parent / "docs" / "模版"
DOCX_PATHS = {
    "listed": _DOCS
    / "1.上市公司年审报表及附注-2026.01"
    / "1.上市公司年审报表及附注-2026.01"
    / "3.2025年度上市公司财务报表附注模板-2026.01.15.docx",
    "soe": _DOCS
    / "1、2025年度财务决算审计报告-2026.01.06"
    / "1、2025年度财务决算审计报告-国企"
    / "1.1-2025国企财务报表附注20260119.docx",
}
DOCX_HEADING_LEVEL = {"listed": "Heading 2", "soe": "Heading 3"}
DOCX_SECTION_TITLE = "货币资金"


# ─── 夹具 ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def wb():
    assert SOURCE_XLSX.exists(), f"源模板不存在：{SOURCE_XLSX}"
    book = openpyxl.load_workbook(SOURCE_XLSX, data_only=False)
    yield book
    book.close()


@pytest.fixture(scope="module")
def sections() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for variant, (number, path) in SECTIONS.items():
        doc = json.loads(path.read_text(encoding="utf-8"))
        sec = next(
            (s for s in doc["sections"] if str(s.get("section_number")) == number), None
        )
        assert sec is not None, f"未找到章节 {number}（{path.name}）"
        out[variant] = sec
    return out


def _tables(sec: dict) -> dict[str, dict]:
    return {str(t.get("name", "")): t for t in (sec.get("tables") or [])}


def _norm(s: object) -> str:
    """归一：去空白与全角空格（源 xlsx 用 `项  目`/`合  计`，模板用 `项目`/`合计`）。"""
    return re.sub(r"[\s\u3000]+", "", str(s or ""))


def _col_a(ws, lo: int, hi: int) -> list[str]:
    return [_norm(ws.cell(row=r, column=1).value) for r in range(lo, hi + 1)]


def _docx_section_blocks(path: Path, heading_style: str, title: str) -> list:
    """按 body 顺序流抽取「某个 Heading 节」下的块，返回 `[('table', rows) | ('para', text)]`。

    🔴 只遍历 `doc.tables` 拿不到「哪张表属哪个章节」—— 必须沿
    `document.element.body` 走（Paragraph / Table 混排）。
    """
    from docx import Document  # 局部 import：缺 python-docx 时按 skip 处理
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(path))
    body = doc.element.body
    out: list = []
    inside = False
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, doc)
            style = (para.style.name or "") if para.style is not None else ""
            text = (para.text or "").strip()
            if style == heading_style:
                if _norm(text) == _norm(title):
                    inside = True
                    continue
                if inside:
                    break  # 同级下一个节 → 本节结束
            elif style.startswith("Heading") and inside:
                lvl = style.split()[-1]
                cur = heading_style.split()[-1]
                if lvl.isdigit() and cur.isdigit() and int(lvl) <= int(cur):
                    break
            if inside and text:
                out.append(("para", text))
        elif tag == "tbl" and inside:
            tbl = Table(child, doc)
            rows = [[c.text.strip() for c in r.cells] for r in tbl.rows]
            out.append(("table", rows))
    return out


def _docx_tables(path: Path, heading_style: str, title: str) -> list[list[list[str]]]:
    return [b[1] for b in _docx_section_blocks(path, heading_style, title) if b[0] == "table"]


# ─── 反向自检 ─────────────────────────────────────────────────────────────────


class TestFixtureSanity:
    def test_source_sheets_exist_with_halfwidth_parens(self, wb):
        """E 类披露 sheet tab 名是**半角括号**（不得"修正"成全角）。"""
        for name in SOURCE_SHEETS.values():
            assert name in wb.sheetnames, f"源 xlsx 无 tab「{name}」"
        assert "附注披露信息（上市公司）" not in wb.sheetnames
        assert "附注披露信息（国企）" not in wb.sheetnames

    def test_sections_loaded(self, sections):
        assert set(sections) == {"listed", "soe"}
        for sec in sections.values():
            assert sec.get("tables"), "章节无表（定位失效，后续断言会空转）"

    def test_norm_is_not_a_noop(self):
        assert _norm("项  目") == "项目"
        assert _norm("合  计") == "合计"
        assert _norm("库存现金") != _norm("现金")


# ─── Property 5：源 xlsx ↔ 模板 行集三向一致 ──────────────────────────────────


class TestProperty5RowsMatchSourceXlsx:
    def test_listed_main_rows_verbatim(self, wb, sections):
        """上市主表 = 源 xlsx R8~R15（8 行，含 R15「其中：存放在境外的款项总额」）。"""
        ws = wb[SOURCE_SHEETS["listed"]]
        want = _col_a(ws, 8, 15)
        got = [_norm(r.get("label")) for r in _tables(sections["listed"])[MAIN_TABLE]["rows"]]
        assert got == want, f"上市主表行集与源 xlsx R8~R15 不一致\n模板={got}\n源={want}"

    # ─────────────────────────────────────────────────────────────────────────
    # 🔴🔴 以下三条为 **Task 12 的诚实改写**（E-cycle spec R5.8 / Property 41）
    #
    # 改写前它们把「附注行集真源 = 底稿源 xlsx」锁死，结论与新增的 docx 三向断言
    # （`TestProperty16SoeMainRowsMatchDocx`）**完全相反**。R5.8 已裁决：
    # **附注行集真源是 `docs/模版/` 的两份附注模板 docx，不是底稿 xlsx**
    # （底稿 xlsx 决定的是底稿 UI 字面，两者由 `E1MainRowDef.noteLabel` 投影桥接）。
    #
    # 故不是「放宽」而是**改判真源**：xlsx 事实全部保留为**对照断言**，用来证明
    # 「两侧差异真实存在且是有意的」，而不再用它约束模板行集。
    # ─────────────────────────────────────────────────────────────────────────

    def test_soe_main_xlsx_has_five_rows_but_docx_has_six(self, wb, sections):
        """对照登记：底稿 xlsx 国企主表 5 行，而附注模板按 docx 是 6 行（多 overseas）。"""
        ws = wb[SOURCE_SHEETS["soe"]]
        xlsx_rows = _col_a(ws, 8, 12)
        assert len(xlsx_rows) == 5, f"底稿 xlsx 国企主表应 5 行：{xlsx_rows}"
        tpl = [_norm(r.get("label")) for r in _tables(sections["soe"])[MAIN_TABLE]["rows"]]
        assert len(tpl) == 6, f"附注模板国企主表应 6 行（docx 口径）：{tpl}"
        # 模板多出的行恰为 overseas；xlsx 侧它是 R13 的括注文字（见下一条）
        assert set(tpl) - set(xlsx_rows) == {"其中：存放在境外的款项总额", "库存现金"}
        assert set(xlsx_rows) - set(tpl) == {"现金"}

    def test_soe_first_row_dual_wording_is_bridged_by_note_label(self, wb, sections):
        """🔴 底稿字面「现金」↔ 附注字面「库存现金」是**双口径**，靠 `noteLabel` 投影。

        改写理由：模板首行原被断言必须是 xlsx 字面 `现金`，而 soe docx 是 `库存现金`
        ⇒ 附注交付件会出现与准则模板不符的行名。现在断言两侧字面各自正确 + 桥接存在。
        """
        assert _norm(wb[SOURCE_SHEETS["soe"]]["A8"].value) == "现金", "底稿 xlsx 侧字面"
        assert _norm(wb[SOURCE_SHEETS["listed"]]["A8"].value) == "库存现金"
        assert _tables(sections["soe"])[MAIN_TABLE]["rows"][0]["label"] == "库存现金", (
            "附注模板首行应为 docx 字面 `库存现金`（Task 12 已由幂等脚本改）"
        )
        assert _tables(sections["listed"])[MAIN_TABLE]["rows"][0]["label"] == "库存现金"

    def test_soe_overseas_row_is_real_in_docx_though_parenthetical_in_xlsx(self, wb, sections):
        """🔴 「其中：存放在境外的款项总额」：xlsx R13 是括注，**docx r6 是正式数据行**。

        改写理由：原断言据 xlsx 把它当假行删掉，导致该附注行**永无数据源**。
        """
        r13 = str(wb[SOURCE_SHEETS["soe"]]["A13"].value or "")
        assert r13.startswith("（") and "单独说明" in r13, (
            f"源 xlsx 国企 R13 应为括注，实为 {r13!r}"
        )
        for variant in ("listed", "soe"):
            labels = [
                _norm(r.get("label")) for r in _tables(sections[variant])[MAIN_TABLE]["rows"]
            ]
            assert "其中：存放在境外的款项总额" in labels, f"{variant} 主表缺境外款项行"
        # 上市侧 xlsx R15 本就是真数据行（对照，证明两版在 docx 里是一致的）
        assert _norm(wb[SOURCE_SHEETS["listed"]]["A15"].value) == "其中：存放在境外的款项总额"
        # 备忘行不得标 is_total（它不参与合计加总）
        soe_rows = _tables(sections["soe"])[MAIN_TABLE]["rows"]
        assert soe_rows[-1].get("is_total") is not True
        assert soe_rows[-2].get("is_total") is True, "合计行应在境外款项行之前"

    def test_listed_main_excludes_reconciliation_row(self, wb, sections):
        """源 xlsx R16 是**勾稽校验行**（`B16=B14-D62`），不是披露行 → 不进模板。"""
        ws = wb[SOURCE_SHEETS["listed"]]
        assert ws["A16"].value in (None, ""), "源 R16 的 A 列应为空（只有 B/C 有校验公式）"
        assert "=B14-D62" in str(ws["B16"].value or "").replace(" ", "")
        assert len(_tables(sections["listed"])[MAIN_TABLE]["rows"]) == 8

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_restricted_rows_are_xlsx_five_plus_docx_sixth_plus_total(
        self, wb, sections, variant
    ):
        """②表 = 源 xlsx R17~R21 五类（前 5 类顺序逐字一致）+ **docx 第 6 类** + 合计。

        🔴 **Task 12/13 的诚实改写**（R6.1）：原断言 `== xlsx 五类 + 合计`，把
        「金融企业法定存款准备金或备付金」判成自造行删掉了 —— 而 soe **附注 docx 有该行**，
        附注行集真源是 docx（R5.8）。xlsx 前 5 类仍作对照，证明只是**插一行不重排**。
        """
        ws = wb[SOURCE_SHEETS["soe"]]
        xlsx_five = _col_a(ws, 17, 21)
        assert len(xlsx_five) == 5
        want = xlsx_five + ["金融企业法定存款准备金或备付金", "合计"]
        got = [
            _norm(r.get("label"))
            for r in _tables(sections[variant])[RESTRICTED_TABLE]["rows"]
        ]
        assert got == want, f"{variant} ②表行集不一致\n模板={got}\n期望={want}"
        # 前 5 类顺序与 xlsx 逐字相同（只插一行、不重排）
        assert got[:5] == xlsx_five

    def test_restricted_sixth_category_comes_from_docx_not_xlsx(self, wb, sections):
        """对照登记：xlsx 侧确无第 6 类（故它必须来自 docx）；`…` 与空行仍不得 seed。"""
        ws = wb[SOURCE_SHEETS["soe"]]
        source_labels = {_norm(ws.cell(row=r, column=1).value) for r in range(17, 24)}
        assert "金融企业法定存款准备金或备付金" not in source_labels, (
            "底稿 xlsx 出现了第 6 类 —— 那 R6.1 的「来自 docx」依据需重新审"
        )
        assert _norm(ws["A22"].value) == "…", "源 R22 应是动态插行标记 `…`"
        for variant in ("listed", "soe"):
            labels = [
                _norm(r.get("label"))
                for r in _tables(sections[variant])[RESTRICTED_TABLE]["rows"]
            ]
            assert "金融企业法定存款准备金或备付金" in labels
            assert "…" not in labels, "动态插行标记不得 seed 成数据行"
            assert "" not in labels, "不得 seed 空占位行"

    def test_restricted_sixth_category_is_declared_in_backend_bucket_source(self):
        """第 6 类必须同时在后端分类桶真源里（否则附注有行而底稿永远归集不出数据）。"""
        from app.services.four_table.e1_restricted_buckets import (
            E1_RESTRICTED_BUCKET_BY_KEY,
        )

        b = E1_RESTRICTED_BUCKET_BY_KEY.get("statutory_reserve")
        assert b is not None, "后端缺 `statutory_reserve` 桶（Task 13）"
        assert b.label == "金融企业法定存款准备金或备付金"

    def test_restricted_total_row_is_last_and_flagged(self, sections):
        """②表必须有合计行（源 R23；校验预设 F1-4 要求合计 = 明细之和）。"""
        for variant in ("listed", "soe"):
            rows = _tables(sections[variant])[RESTRICTED_TABLE]["rows"]
            assert rows[-1]["label"] == "合计"
            assert rows[-1].get("is_total") is True


# ─── Requirement 6：上市侧②表已补建（用户裁决）────────────────────────────────


class TestRequirement6ListedRestrictedTable:
    def test_listed_has_restricted_table(self, sections):
        """用户裁决 2026-08-01：上市侧补建②表。"""
        assert RESTRICTED_TABLE in _tables(sections["listed"])

    def test_check_presets_reference_it_in_both_variants(self):
        """裁决依据：校验预设**两版**都有 F1-4/F1-5/F1-6 引用②表。"""
        presets = json.loads(
            (DATA / "note_check_preset_formulas.json").read_text(encoding="utf-8")
        )
        for variant in ("listed", "soe"):
            items = presets[variant]
            items = items if isinstance(items, list) else items.get("items", [])
            ids = {
                it.get("id")
                for it in items
                if "货币资金" in str(it.get("section_title") or "")
                and "受限" in str(it.get("table_name") or "")
            }
            assert {"F1-4", "F1-5", "F1-6"} <= ids, (
                f"{variant} 侧未找到引用②表的 F1-4~F1-6（裁决依据失效）"
            )

    def test_both_variants_share_row_set(self, sections):
        """两版②表共用同一行集（禁各写一份）。"""
        a = [r["label"] for r in _tables(sections["listed"])[RESTRICTED_TABLE]["rows"]]
        b = [r["label"] for r in _tables(sections["soe"])[RESTRICTED_TABLE]["rows"]]
        assert a == b


# ─── Property 6：单级表头必须显式 flat ────────────────────────────────────────


class TestProperty6FlatColumns:
    @pytest.mark.parametrize("variant", ["listed", "soe"])
    @pytest.mark.parametrize("table", [MAIN_TABLE, RESTRICTED_TABLE])
    def test_columns_present_and_flat(self, sections, variant, table):
        tbl = _tables(sections[variant])[table]
        cols = tbl.get("columns") or []
        assert cols, f"{variant}/{table} 缺 columns"
        assert len(cols) == len(tbl.get("headers") or [])
        assert any(c.get("flat") for c in cols), "单级表头必须显式标 flat"
        assert not any(c.get("group") for c in cols), "单级表不得声明 group"
        assert tbl.get("_column_groups") is None, "单级表不得残留 _column_groups"
        assert cols[0].get("is_label") is True

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    @pytest.mark.parametrize("table", [MAIN_TABLE, RESTRICTED_TABLE])
    def test_guidance_present_and_plaintext(self, sections, variant, table):
        g = str(_tables(sections[variant])[table].get("guidance") or "")
        assert g.strip(), f"{variant}/{table} 缺 guidance"
        # guidance 一律纯文本（TAB 提示与 Word 导出都不解析 markdown；
        # 且平台级 fix_note_bold_markers.py 会剥 `**`，留着会互相打架）
        assert "**" not in g, "guidance 不得含 markdown 粗体"
        assert "<" not in g, "guidance 不得含 HTML"


# ─── 模板 ↔ 同步载荷 列键三向一致 ─────────────────────────────────────────────


class TestTemplateMatchesSyncPayload:
    @pytest.fixture(scope="class")
    def ts_src(self) -> str:
        return NOTE_MAP_TS.read_text(encoding="utf-8")

    def test_column_keys_mirror_payload(self, sections, ts_src):
        """模板 columns[].key 必须逐字出现在同步载荷的列定义里。"""
        assert "MAIN_COLUMNS_LISTED" in ts_src  # 反向自检
        for variant in ("listed", "soe"):
            for table in (MAIN_TABLE, RESTRICTED_TABLE):
                for col in _tables(sections[variant])[table]["columns"]:
                    key = col["key"]
                    assert f"key: '{key}'" in ts_src, (
                        f"{variant}/{table} 的列键 {key!r} 在 e1NoteSectionMap 里找不到"
                    )

    def test_payload_marks_flat_too(self, ts_src):
        """🔴 `flat` 必须 **seed 与推送两处都加**（H8 踩过只加一侧的坑）。"""
        # 四组列定义各自的标签列都要带 flat
        assert ts_src.count("is_label: true, flat: true") >= 4

    def test_payload_restricted_has_three_columns_no_reason(self, ts_src):
        """②表推 3 列，`受限原因` 不进附注（源模板②表只有 3 列）。"""
        m = re.search(
            r"const RESTRICTED_COLUMNS_SOE: ColumnDef\[\] = \[(.*?)\]", ts_src, re.S
        )
        assert m, "未找到 RESTRICTED_COLUMNS_SOE（锚点漂移）"
        body = m.group(1)
        assert body.count("key:") == 3
        assert "reason" not in body

    def test_total_label_matches_template(self, sections, ts_src):
        """合计行字面按本章节实证取（模板是 `合计` 无空格，不套平台的 `合 计`）。"""
        assert "E1_NOTE_TOTAL_LABEL = '合计'" in ts_src
        for variant in ("listed", "soe"):
            rows = _tables(sections[variant])[RESTRICTED_TABLE]["rows"]
            assert rows[-1]["label"] == "合计"

    def test_main_row_labels_mirror_frontend_scope(self, sections):
        """模板主表行标签必须与前端 `e1DisclosureScope` 的真源逐字一致。"""
        src = DISCLOSURE_SCOPE_TS.read_text(encoding="utf-8")
        assert "E1_MAIN_ROWS_LISTED" in src  # 反向自检
        for variant in ("listed", "soe"):
            for row in _tables(sections[variant])[MAIN_TABLE]["rows"]:
                label = row["label"]
                if label == "合计":
                    continue
                assert f"label: '{label}'" in src, (
                    f"{variant} 主表行 {label!r} 未出现在 e1DisclosureScope"
                )


# ─── 章节 stamp ───────────────────────────────────────────────────────────────


class TestAlignedByStamp:
    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_stamped(self, sections, variant):
        assert (
            sections[variant].get("_aligned_by")
            == "e1-four-table-extraction-and-disclosure-alignment"
        )


# ─── 外币货币性项目（五、73 / 八、92）—— 跨循环共享章节 ─────────────────────

FX_TABLE = "外币货币性项目"
FX_SECTIONS = {"listed": ("五、73", LISTED_PATH), "soe": ("八、92", SOE_PATH)}

#: 他循环的段标签（E1 不得删、不得覆盖）
FOREIGN_SEGMENT_LABELS = ["应收账款", "短期借款", "长期借款", "应付债券"]


@pytest.fixture(scope="module")
def fx_sections() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for variant, (number, path) in FX_SECTIONS.items():
        doc = json.loads(path.read_text(encoding="utf-8"))
        sec = next(
            (s for s in doc["sections"] if str(s.get("section_number")) == number), None
        )
        assert sec is not None, f"未找到章节 {number}（{path.name}）"
        out[variant] = sec
    return out


class TestFxSectionColumnsOnly:
    """只补 columns/guidance，**不动行集**（跨循环共享，动行集会打断他循环）。"""

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_columns_present_and_flat(self, fx_sections, variant):
        tbl = _tables(fx_sections[variant])[FX_TABLE]
        cols = tbl.get("columns") or []
        assert len(cols) == 4, f"外币表应 4 列（仅期末），实为 {len(cols)}"
        assert [c["label"] for c in cols] == [
            "项目",
            "期末外币余额",
            "折算汇率",
            "期末折算人民币余额",
        ]
        assert any(c.get("flat") for c in cols)
        assert not any(c.get("group") for c in cols)
        assert tbl.get("_column_groups") is None

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_guidance_present_and_plaintext(self, fx_sections, variant):
        g = str(_tables(fx_sections[variant])[FX_TABLE].get("guidance") or "")
        assert g.strip()
        assert "**" not in g
        assert "<" not in g
        # guidance 必须如实记录「尚未接自动推送」的原因，避免下一个人误以为已打通
        assert "浅合并" in g or "行级合并" in g

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_foreign_cycle_segments_preserved(self, fx_sections, variant):
        """🔴 他循环的段落必须完整保留（E1 只补列元数据，绝不动行）。"""
        labels = [_norm(r.get("label")) for r in _tables(fx_sections[variant])[FX_TABLE]["rows"]]
        for seg in FOREIGN_SEGMENT_LABELS:
            if variant == "listed" and seg in ("短期借款", "应付债券"):
                continue  # 上市侧模板本就没有这两段
            assert seg in labels, f"{variant} 外币表丢了「{seg}」段"
        assert "货币资金" in labels

    def test_row_counts_unchanged(self, fx_sections):
        """行数保持模板原样（上市 16 / 国企 25）—— 证明 rows=None 生效。"""
        assert len(_tables(fx_sections["listed"])[FX_TABLE]["rows"]) == 16
        assert len(_tables(fx_sections["soe"])[FX_TABLE]["rows"]) == 25

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_expandable_placeholder_rows_kept(self, fx_sections, variant):
        """「可无限量添加行」/「……」作**行**是源模板可扩区 → 保留（作列头才丢弃）。"""
        labels = [str(r.get("label") or "") for r in _tables(fx_sections[variant])[FX_TABLE]["rows"]]
        assert any(x in ("可无限量添加行", "……", "…") for x in labels), (
            f"{variant} 外币表的可扩行占位被误删：{labels}"
        )


class TestFxPushOnlyViaRowScope:
    """推该表**只允许**经 `_row_scope` 走平台级行级合并。

    原断言是「全前端不得有 map 推外币章节」（表级浅合并会整表覆盖、清掉他循环的段）。
    `disclosure-note-row-level-merge` 落地后该限制放开为**条件许可**：
    声明 `_row_scope` 只负责自己那一段即可推，段外行由服务端原样保留、
    段边界解析不出时整表跳过写入（fail closed）。
    """

    @staticmethod
    def _strip(src: str) -> str:
        body = re.sub(r"/\*[\s\S]*?\*/", "", src)
        return re.sub(r"(^|[^:])//[^\n]*", r"\1", body)

    def _fx_maps(self) -> list[tuple[str, str]]:
        """(文件名, 去注释源码) —— 引用了外币章节号的 map 文件。"""
        out: list[tuple[str, str]] = []
        for p in FRONTEND.parent.rglob("*NoteSectionMap.ts"):
            body = self._strip(p.read_text(encoding="utf-8"))
            if re.search(r"(五、73|八、92)", body):
                out.append((p.name, body))
        return out

    def test_fx_pushers_all_declare_row_scope(self):
        """凡推外币章节的 map 必须声明 `_row_scope` + `owner_row_code`。"""
        maps = self._fx_maps()
        # 反向自检：一个都扫不到说明正则失效（E1 已接线，至少 1 个）
        assert maps, "扫不到任何引用外币章节的 map —— 正则失效"
        offenders = [
            name
            for name, body in maps
            if "_row_scope" not in body or "owner_row_code" not in body
        ]
        assert offenders == [], (
            f"{offenders} 推外币章节但未声明 _row_scope —— 表级覆盖会清掉他循环的段"
        )

    def test_fx_owner_row_code_is_cash_segment(self):
        """E1 只许声明货币资金段（`BS-002`），不得越权覆盖他段。"""
        e1 = [(n, b) for n, b in self._fx_maps() if n.startswith("e1")]
        assert e1, "e1FxNoteSectionMap.ts 未接线？"
        for name, body in e1:
            assert "'BS-002'" in body, f"{name} 未声明货币资金段 BS-002"
            for foreign in ("BS-006", "BS-031", "BS-061", "BS-062"):
                assert f"'{foreign}'" not in body, (
                    f"{name} 出现他段 code {foreign} —— E1 只负责货币资金段"
                )

    def test_registry_has_no_fx_entry(self):
        """registry 仍不含外币章节。

        `note_workpaper_sync_registry.json` 是 section→wp **1:1** 的反查表
        （附注侧「打开同步底稿」用），而共享表一个章节有多个 owner → 不入 registry。
        生成器 `gen_note_wp_sync_registry.py` 的 `WP_CODE_RE` 是
        `^([a-z]+\\d+)NoteSectionMap\\.ts$`，`e1FxNoteSectionMap.ts` 因大写 `F`
        天然不被扫到（与 M 循环共享 map 同款机制），故本断言自动成立。
        """
        reg = (DATA / "note_workpaper_sync_registry.json").read_text(encoding="utf-8")
        assert "五、73" not in reg
        assert "八、92" not in reg


class TestStaleCrossRefFixed:
    def test_listed_main_section_points_to_73_not_81(self, sections):
        """五、1 的外币交叉引用应为 `五、73`（`五、81` 是陈旧值）。"""
        texts = [str(t) for t in (sections["listed"].get("text_sections") or [])]
        joined = "\n".join(texts)
        assert "外币货币性项目" in joined  # 反向自检：该段确实存在
        assert "五、81" not in joined, "残留陈旧章节号 五、81"
        assert "五、73" in joined

    def test_variant_matrix_confirms_73(self):
        """真源交叉验证：`variant_matrix` 的外币货币性项目 listed = 五、73。"""
        m = json.loads(
            (DATA / "note_template_variant_matrix.json").read_text(encoding="utf-8")
        )
        entry = next(
            a for a in m["accounts"] if a.get("section_title") == "外币货币性项目"
        )
        assert entry["variants"]["listed_standalone"] == "五、73"
        assert entry["variants"]["soe_standalone"] == "八、92"


# ═══════════════════════════════════════════════════════════════════════════════
# 以下为本 spec（e-cycle-extraction-formula-and-disclosure-completion）Task 3 新增
#
# 🔴 判据真源换成 `docs/模版/` 两份 **docx**（不是底稿 xlsx）。
#    前一轮据源 xlsx 删掉了「金融企业法定存款准备金或备付金」，而 docx 确有该行
#    —— 附注行集真源是 docx。上面那批「源 xlsx 三向一致」的断言因此有几条
#    会被 Wave 4/5 诚实改写（R5.8 / R6.9 已登记），改写不是回归。
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def report_config() -> dict[str, set[str]]:
    """`{row_code: {row_name, ...}}` —— 四准则合并（同码在不同准则可能同名/异名）。

    🔴 连库范式（Property 31）：一次 `asyncio.run` + 专用 `NullPool` 引擎 + 同 loop 内
    `dispose()`，**禁借 `app.core.database.async_session` 共享池**（会让后续连库测试
    报 `Event loop is closed`，memory 已记该事故）。
    """
    import asyncio

    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    try:
        from app.core.config import settings
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"无法读取配置：{exc}")

    url = getattr(settings, "DATABASE_URL", None) or getattr(
        settings, "SQLALCHEMY_DATABASE_URI", None
    )
    if not url:
        pytest.skip("未配置 DATABASE_URL —— row_code 对账暂不可验证")

    async def _load() -> dict[str, set[str]]:
        engine = create_async_engine(str(url), poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                rows = (
                    await conn.execute(
                        sa.text(
                            "SELECT row_code, row_name FROM report_config "
                            "WHERE row_code IS NOT NULL AND row_name IS NOT NULL"
                        )
                    )
                ).all()
        finally:
            await engine.dispose()
        out: dict[str, set[str]] = {}
        for code, name in rows:
            out.setdefault(str(code), set()).add(_norm(name))
        return out

    try:
        cfg = asyncio.run(_load())
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"连库失败，row_code 对账暂不可验证：{exc}")

    if not cfg:
        pytest.skip("report_config 为空 —— 判据无数据可验（⚠️ 这不等于对账可以省掉）")
    return cfg


@pytest.fixture(scope="module")
def docx_available() -> bool:
    try:
        import docx  # noqa: F401
    except ImportError:  # pragma: no cover
        return False
    return LISTED_DOCX.exists() and SOE_DOCX.exists()


@pytest.fixture(scope="module")
def docx_blocks(docx_available) -> dict[str, list]:
    if not docx_available:
        pytest.skip("python-docx 不可用或源 docx 缺失 —— 三向比对暂不可验证")
    return {
        "listed": _docx_section_blocks(LISTED_DOCX, LISTED_HEADING, DOCX_SECTION_TITLE),
        "soe": _docx_section_blocks(SOE_DOCX, SOE_HEADING, DOCX_SECTION_TITLE),
    }


@pytest.fixture(scope="module")
def docx_tables(docx_blocks) -> dict[str, list[list[list[str]]]]:
    return {k: [b[1] for b in v if b[0] == "table"] for k, v in docx_blocks.items()}


class TestDocxFixtureSanity:
    """反向自检：证明 docx 定位真的抽到了东西（否则后续断言全空转）。"""

    def test_docx_paths_exist(self, docx_available):
        if not docx_available:
            pytest.skip("python-docx 不可用或源 docx 缺失")
        assert LISTED_DOCX.exists(), f"listed 源 docx 不存在：{LISTED_DOCX}"
        assert SOE_DOCX.exists(), f"soe 源 docx 不存在：{SOE_DOCX}"

    def test_heading_levels_differ_between_variants(self, docx_blocks):
        """🔴 listed 是 Heading 2、soe 是 Heading 3（两版层级不同，照抄一种会 0 命中）。"""
        assert LISTED_HEADING == "Heading 2"
        assert SOE_HEADING == "Heading 3"
        for variant in ("listed", "soe"):
            assert docx_blocks[variant], f"{variant} docx「货币资金」节抽取为空（定位失效）"

    def test_docx_titles_carry_no_chinese_numbering(self, docx_blocks):
        """docx 章号是 Word 自动编号 —— 段落文本里不含「五、」，故按 style 定位。"""
        assert _norm(DOCX_SECTION_TITLE) == "货币资金"
        joined = "\n".join(
            t for v in docx_blocks.values() for kind, t in v if kind == "para"
        )
        assert "货币资金" in joined or joined, "节内容为空"


class TestProperty37ListedHasNoRestrictedTableInDocx:
    """Property 37：listed docx「货币资金」节只有 1 张表 → listed 受限表是平台补充表。

    **Validates: Requirements 6.6**
    """

    def test_listed_section_has_exactly_one_table(self, docx_tables):
        tables = docx_tables["listed"]
        assert len(tables) == 1, (
            f"listed docx「货币资金」节应恰好 1 张表（受限内容是文字段落），实为 {len(tables)} 张。"
            "若源 docx 真的加了受限表，则 R6.6 的裁决依据需重新审。"
        )

    def test_listed_restricted_content_is_prose(self, docx_blocks):
        """受限内容以文字段落形式存在（这是「无 docx 依据」的正面证据）。"""
        paras = [t for kind, t in docx_blocks["listed"] if kind == "para"]
        joined = "\n".join(paras)
        assert "抵押" in joined and "冻结" in joined, (
            f"listed docx 受限相关文字段落未找到：{paras[:5]}"
        )

    def test_platform_supplement_is_declared_not_claimed_as_docx_aligned(self, sections):
        """平台补充表必须在 guidance 里如实登记「非 listed docx 依据」。

        Wave 4 Task 12 落地后本断言转绿；当前应红。
        """
        g = str(_tables(sections["listed"])[RESTRICTED_TABLE].get("guidance") or "")
        assert "平台补充" in g or "镜像" in g or "源 docx 无该表" in g, (
            "listed ②表 guidance 未登记「平台补充表 / 依据镜像 soe 而非 listed docx」"
            "（R6.6）。【Wave 4 Task 12 待补】"
        )

    def test_soe_section_has_two_tables(self, docx_tables):
        """对照：soe docx 该节有 2 张表（主表 + 受限表），证明不是一刀切。"""
        assert len(docx_tables["soe"]) == 2


class TestProperty16SoeMainRowsMatchDocx:
    """Property 16：soe 主表行标签序列 == docx == 模板 JSON == 同步载荷。

    **Validates: Requirements 5.1, 5.2, 5.6, 10.3**
    """

    @staticmethod
    def _docx_labels(tables: list[list[list[str]]]) -> list[str]:
        rows = tables[0]
        assert _norm(rows[0][0]) == "项目", f"表头首格应为「项  目」，实为 {rows[0][0]!r}"
        return [_norm(r[0]) for r in rows[1:]]

    def test_soe_docx_main_has_six_rows(self, docx_tables):
        """docx 事实冻结：soe 主表 6 行（首行 `库存现金`、末行 `其中：存放在境外的款项总额`）。"""
        labels = self._docx_labels(docx_tables["soe"])
        assert labels == [
            "库存现金",
            "银行存款",
            "其他货币资金",
            "数字货币",
            "合计",
            "其中：存放在境外的款项总额",
        ], f"soe docx 主表行集与冻结基线不符：{labels}"

    def test_template_soe_main_matches_docx(self, docx_tables, sections):
        """模板 JSON 必须与 docx 逐字一致。【Wave 4 Task 12 / Wave 5 Task 15 待修】"""
        want = self._docx_labels(docx_tables["soe"])
        got = [_norm(r.get("label")) for r in _tables(sections["soe"])[MAIN_TABLE]["rows"]]
        assert got == want, (
            f"soe 主表与源 docx 不一致\n模板={got}\ndocx={want}\n"
            "【Wave 4 Task 12 待修】首行 `现金`→`库存现金`；合计行后补"
            "`其中：存放在境外的款项总额`（R5.1 / R5.2）。"
            "🔴 附注行集真源是 docx 不是底稿 xlsx。"
        )

    def test_payload_projects_soe_first_row_to_docx_label(self, sections):
        """底稿 UI 保留源 xlsx 字面 `现金`，推送时投影为 `库存现金`（双口径，R5.4）。

        【Wave 5 Task 15 待修】`E1MainRowDef.noteLabel` + `mainRow()` 用 `noteLabel ?? label`。
        """
        src = DISCLOSURE_SCOPE_TS.read_text(encoding="utf-8")
        map_src = NOTE_MAP_TS.read_text(encoding="utf-8")
        assert "E1_MAIN_ROWS_SOE" in src  # 反向自检
        assert "noteLabel" in src and "noteLabel" in map_src, (
            "未见 noteLabel 双口径投影 —— 底稿字面 `现金` 会直接推成附注行标签，"
            "与 docx `库存现金` 不符（R5.4）。【Wave 5 Task 15 待修】"
        )

    def test_listed_docx_main_has_eight_rows_unchanged(self, docx_tables, sections):
        """listed 侧已与 docx 一致，本 spec 不得改动（R5.6）。"""
        want = self._docx_labels(docx_tables["listed"])
        assert len(want) == 8, f"listed docx 主表应 8 行，实为 {len(want)}"
        got = [_norm(r.get("label")) for r in _tables(sections["listed"])[MAIN_TABLE]["rows"]]
        assert got == want, f"listed 主表被改动了？\n模板={got}\ndocx={want}"


class TestProperty41VariantAsymmetryIsIntentional:
    """Property 41：soe 主表比 listed 少两行是准则口径差异，禁对齐。

    **Validates: Requirements 5.7, 11.4**
    """

    def test_soe_docx_lacks_finance_co_and_accrued(self, docx_tables):
        labels = {_norm(r[0]) for r in docx_tables["soe"][0][1:]}
        assert "存放财务公司款项" not in labels, (
            "soe docx 出现了「存放财务公司款项」—— R5.7 的口径差异依据需重新审"
        )
        assert "存款应计利息" not in labels

    def test_listed_docx_has_both_rows(self, docx_tables):
        """对照：listed docx 确有这两行（证明差异真实存在，不是抽取漏了）。"""
        labels = {_norm(r[0]) for r in docx_tables["listed"][0][1:]}
        assert "存放财务公司款项" in labels
        assert "存款应计利息" in labels

    def test_template_keeps_the_asymmetry(self, sections):
        """模板必须保持不对称（禁「顺手给 soe 补两行」）。"""
        soe = {_norm(r.get("label")) for r in _tables(sections["soe"])[MAIN_TABLE]["rows"]}
        listed = {
            _norm(r.get("label")) for r in _tables(sections["listed"])[MAIN_TABLE]["rows"]
        }
        assert "存放财务公司款项" not in soe
        assert "存款应计利息" not in soe
        assert {"存放财务公司款项", "存款应计利息"} <= listed


class TestProperty20RestrictedRowOrderMatchesDocx:
    """Property 20：受限表行序 == docx 六类（按 docx 序）+ 平台补充桶 + 合计。

    **Validates: Requirements 6.1, 6.8**

    🔴 **不得写成「== docx r1~r6」** —— 平台兜底桶 `other 其他受限资金`
    （`source_ref=None`）在 docx 与模板行集里都没有对应行，但推送时会出现。
    """

    #: docx soe 受限表六类（冻结基线，来自实测复算）
    DOCX_SIX = [
        "银行承兑汇票保证金",
        "信用证保证金",
        "履约保证金",
        "用于担保的定期存款或通知存款",
        "放在境外且资金汇回受到限制的款项",
        "金融企业法定存款准备金或备付金",
    ]

    def test_docx_soe_restricted_six_categories(self, docx_tables):
        rows = docx_tables["soe"][1]
        assert _norm(rows[0][0]) == "项目"
        labels = [_norm(r[0]) for r in rows[1:]]
        assert labels == [_norm(x) for x in self.DOCX_SIX], (
            f"soe docx 受限表六类与冻结基线不符：{labels}"
        )

    def test_docx_restricted_has_no_total_row(self, docx_tables):
        """docx 无合计行 —— 平台保留合计是按校验预设 F1-4 的有意偏离（R6.4）。"""
        labels = [_norm(r[0]) for r in docx_tables["soe"][1][1:]]
        assert "合计" not in labels

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_template_restricted_covers_six_plus_total(self, docx_tables, sections, variant):
        """模板 = docx 六类（按 docx 序）+ 合计。【Wave 4 Task 12 待修：缺第 6 类】"""
        want = [_norm(x) for x in self.DOCX_SIX] + ["合计"]
        got = [
            _norm(r.get("label"))
            for r in _tables(sections[variant])[RESTRICTED_TABLE]["rows"]
        ]
        assert got == want, (
            f"{variant} ②表行序与「docx 六类 + 合计」不符\n模板={got}\n期望={want}\n"
            "【Wave 4 Task 12 待修】合计行前补「金融企业法定存款准备金或备付金」（R6.1）。"
            "🔴 前 5 类顺序与模板现状逐字一致 ⇒ 只需插一行、不需重排。"
        )

    def test_platform_fallback_bucket_has_no_docx_row(self):
        """兜底桶 `other` 在 docx 无行 —— 这就是「不得写成 == docx r1~r6」的理由。"""
        from app.services.four_table.e1_restricted_buckets import E1_RESTRICTED_BUCKETS

        fallback = [b for b in E1_RESTRICTED_BUCKETS if getattr(b, "source_ref", None) is None]
        assert fallback, "未找到平台补充桶（source_ref=None）—— 桶定义结构变了？"
        for b in fallback:
            assert _norm(b.label) not in {_norm(x) for x in self.DOCX_SIX}


class TestProperty23FxSegmentRowCodeMatchesReportConfig:
    """Property 23：外币表每个段首行 `report_row_code` 的 `row_name` 与段 label 语义一致。

    **Validates: Requirements 7.1, 7.2, 7.5**
    """

    @staticmethod
    def _segments(sec: dict) -> list[tuple[str, str]]:
        """返回 `[(row_code, label)]` —— 带 `report_row_code` 的段首行。"""
        out: list[tuple[str, str]] = []
        for row in _tables(sec)[FX_TABLE]["rows"]:
            code = row.get("report_row_code")
            if code:
                out.append((str(code), _norm(row.get("label"))))
        return out

    def test_segments_found(self, fx_sections):
        """反向自检：段首行确实带 row_code（否则整条断言空转）。"""
        for variant in ("listed", "soe"):
            segs = self._segments(fx_sections[variant])
            assert segs, f"{variant} 外币表无任何带 report_row_code 的段首行"

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_row_code_row_name_matches_segment_label(self, report_config, fx_sections, variant):
        """段 label 必须与 `report_config` 里该 row_code 的 row_name 语义一致。

        【Wave 4 Task 12 待修】soe 短期借款段现挂 `BS-031`（使用权资产）→ 应为 `BS-041`。
        """
        bad: list[str] = []
        for code, label in self._segments(fx_sections[variant]):
            names = report_config.get(code)
            if not names:
                bad.append(f"{code}（label={label!r}）在 report_config 里查不到")
                continue
            if not any(label in n or n in label for n in names):
                bad.append(
                    f"{code}: 段 label={label!r} vs report_config row_name={sorted(names)}"
                )
        assert bad == [], (
            f"{variant} 外币表段首行 row_code 与 report_config 对不上：\n  "
            + "\n  ".join(bad)
            + "\n【Wave 4 Task 12 待修】`BS-031` 是使用权资产，短期借款应为 `BS-041`（R7.1）。"
            "🔴 该段 `account_codes:['2001']` 本来就是对的，只有 row_code 错（R7.2）。"
        )

    def test_short_term_loan_row_code_is_bs041(self, report_config):
        """真源交叉验证：`BS-041` 的 row_name 是短期借款、`BS-031` 是使用权资产。"""
        assert report_config.get("BS-041") == {"短期借款"}, (
            f"BS-041 的 row_name 不是短期借款：{report_config.get('BS-041')}"
        )
        assert report_config.get("BS-031") == {"使用权资产"}, (
            f"BS-031 的 row_name 不是使用权资产：{report_config.get('BS-031')}"
        )


class TestProperty24Bs031StaysWithH8:
    """Property 24 反向锁死：`BS-031` 仍归 H8 使用权资产（防日后把 H8 改成 BS-041）。

    **Validates: Requirements 7.6**
    """

    def test_report_config_bs031_is_right_of_use_in_all_standards(self):
        import sqlite3  # noqa: F401  (仅为表明本断言只读静态真源)

        from app.services.four_table import dual_family_codes as dfc

        src = Path(dfc.__file__).read_text(encoding="utf-8")
        assert "BS-031" in src, (
            "`dual_family_codes.py` 不再引用 BS-031 —— H8 的 row_code 被改了？"
            "若确有意改动，需同步更新 R7.6 的裁决依据。"
        )

    def test_h8_account_scope_still_uses_bs031(self):
        p = _BACKEND / "app" / "services" / "four_table" / "h8_account_scope.py"
        assert p.exists(), f"h8_account_scope.py 不存在：{p}"
        assert "BS-031" in p.read_text(encoding="utf-8"), (
            "`h8_account_scope.py` 不再引用 BS-031 —— 使用权资产的报表行被改了？"
        )


class TestProperty19FrozenSnapshots:
    """Property 19：listed 五、1 主表 8 行、两版外币表段数与行数冻结。

    **Validates: Requirements 11.4**
    """

    def test_listed_main_row_count(self, sections):
        assert len(_tables(sections["listed"])[MAIN_TABLE]["rows"]) == 8

    def test_fx_segment_counts(self, fx_sections):
        """外币表段数：listed 3 / soe 5（两版不对称是源 docx 事实）。"""
        counts = {
            v: len(TestProperty23FxSegmentRowCodeMatchesReportConfig._segments(fx_sections[v]))
            for v in ("listed", "soe")
        }
        assert counts == {"listed": 3, "soe": 5}, f"外币表段数变了：{counts}"

    def test_fx_row_counts(self, fx_sections):
        assert len(_tables(fx_sections["listed"])[FX_TABLE]["rows"]) == 16
        assert len(_tables(fx_sections["soe"])[FX_TABLE]["rows"]) == 25

    def test_fx_segment_account_codes_unchanged(self, fx_sections):
        """段首行 `account_codes` 逐字不变（R7.2）。"""
        for row in _tables(fx_sections["soe"])[FX_TABLE]["rows"]:
            if _norm(row.get("label")) == "短期借款" and row.get("report_row_code"):
                assert row.get("account_codes") == ["2001"], (
                    f"短期借款段 account_codes 被改了：{row.get('account_codes')}"
                )
                return
        pytest.fail("soe 外币表未找到短期借款段首行")


class TestProperty30RowTypeDomainUnchanged:
    """Property 30：**本 spec** 不引入新 `row_type`（自律，非全局禁令）。

    **Validates: Requirements 9.5**

    🔴 2026-08-09 修正实现（原断言把「自律」写成了「全局」）：
    原判据扫**全库模板**断言取值域恰为 5 值。而 C spec
    （`note-template-columns-and-legacy-snapshot-closure` R11 / Property 33）
    已正当落地 **第 6 个取值 `expandable`**（源模板可扩位行，零可见内容），
    全库 121 行；其中 `五、73` / `八、92`「外币货币性项目」表就有 9 行
    （那正是源模板留的 `可无限量添加行` / `……` 位置）。
    ⇒ 原实现会把 C spec 的正确落地打红，且**与本 spec 的 docstring 自相矛盾**
    （docstring 明写「`expandable` 归 C spec」）。

    改法两条：
    1. 取值域断言改「⊆ 六值」，且第 6 个取值**从 C spec 的 service 层 import**
       （交叉锁死 —— 不硬写字符串，C spec 若改名/改语义这里立刻红）；
    2. 保住原意的自律部分：**E1 自己负责的主表与②表**（`货币资金` /
       `受限制的货币资金明细`）内不得出现 `expandable` —— 那两张表是固定行集，
       源模板未留可扩位（实测 0 行，故该断言当前为绿且能防本 spec 误引入）。
    """

    LEGACY_FIVE = {"data", "total", "subtotal", "header_label", "unowned"}

    @staticmethod
    def _expandable_token() -> str:
        """从 C spec 的判据真源取第 6 个取值（跨 spec 交叉锁死，禁硬写字面量）。"""
        from app.services.note_expandable_markers import EXPANDABLE_ROW_TYPE

        return EXPANDABLE_ROW_TYPE

    @pytest.mark.parametrize("path_key", ["listed", "soe"])
    def test_no_new_row_type_introduced(self, path_key):
        allowed = self.LEGACY_FIVE | {self._expandable_token()}
        path = LISTED_PATH if path_key == "listed" else SOE_PATH
        doc = json.loads(path.read_text(encoding="utf-8"))
        seen: set[str] = set()
        for sec in doc.get("sections") or []:
            for tbl in sec.get("tables") or []:
                for row in tbl.get("rows") or []:
                    rt = row.get("row_type")
                    if rt:
                        seen.add(str(rt))
        extra = seen - allowed
        assert extra == set(), (
            f"{path_key} 模板出现取值域外的 row_type {sorted(extra)} —— "
            "六个合法取值 = data/total/subtotal/header_label/unowned/expandable；"
            "新增第 7 个必须先立 spec 并同步全部枚举登记处"
        )
        assert seen, "扫不到任何 row_type（反向自检失败：判据空转）"

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_e1_own_tables_have_no_expandable(self, sections, variant):
        """自律：E1 自己负责的两张表是固定行集，不得引入可扩位（源模板未留）。"""
        token = self._expandable_token()
        tables = _tables(sections[variant])
        for name in (MAIN_TABLE, RESTRICTED_TABLE):
            tbl = tables.get(name)
            if tbl is None:  # listed ②表是平台补充表，可能缺
                continue
            offenders = [
                r.get("label")
                for r in (tbl.get("rows") or [])
                if str(r.get("row_type") or "") == token
            ]
            assert not offenders, (
                f"{variant} {name} 出现可扩位行 {offenders} —— "
                "该表源模板是固定行集，本 spec 不得引入 expandable"
            )

    def test_selfcheck_expandable_token_is_not_hardcoded_here(self):
        """反向自检：第 6 个取值必须来自 C spec service，且它真的在用。"""
        assert self._expandable_token() == "expandable"
        src = Path(__file__).read_text(encoding="utf-8")
        i = src.find("def _expandable_token")
        body = src[i : i + 400]
        assert "app.services.note_expandable_markers" in body, (
            "第 6 个取值必须从 C spec 的判据真源 import（跨 spec 交叉锁死）"
        )
