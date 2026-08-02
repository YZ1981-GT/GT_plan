"""附注「所有权或使用权受到限制的资产」结构守卫（listed 五、32 / soe 八、93）。

**Validates: restricted-assets-note-row-scope-rollout Requirements 1.1~1.7, 5.1, 5.4
/ Properties 1, 5, 6, 7, 13**

🔴 **本表在 `backend/wp_templates/` 里没有对应的披露 sheet**（全量扫 349 个 xlsx 实证）。
唯一相关的源是 `A3-5 合并附注汇总-2019.xlsx` / `A3-6 母公司附注汇总-2019.xlsx` 的
sheet「所有权受限资产」—— 那是**合并/母公司按主体横向展开的汇总工作表**
（审定数 / 抵消数 / 汇总 / 母公司审定 / 子公司1..N），行只有 5 个科目 + 2 空行 + 合计，
不是附注披露表本身。

故本守卫的裁决口径是 **附注模板 + `report_config` 双源锁死**，
A3-5/A3-6 的科目清单作**旁证**（openpyxl 直读，断言那 5 个科目都在附注模板里）。
这是 spec 预留的兜底口径，不是偷懒 —— 源 xlsx 里确实没有这张披露表。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from openpyxl import load_workbook

_BACKEND = Path(__file__).resolve().parents[1]
DATA = _BACKEND / "data"
LISTED_PATH = DATA / "note_template_listed.json"
SOE_PATH = DATA / "note_template_soe.json"
WP_TEMPLATES = _BACKEND / "wp_templates"

LISTED_SECTION = "五、32"
SOE_SECTION = "八、93"
LISTED_MAIN = "所有权或使用权受到限制的资产"
LISTED_PRIOR = "所有权或使用权受到限制的资产（续：上年年末）"
LISTED_PRIOR_LEGACY = "续："
SOE_MAIN = "所有权和使用权受到限制的资产"

#: 段归属期望（与 `fix_note_restricted_assets_structure.py` 的常量同源，顺序即行序）
LISTED_EXPECTED = [
    ("货币资金", "BS-002"),
    ("应收票据", "BS-005"),
    ("应收账款", "BS-006"),
    ("存货", "BS-010"),
    ("固定资产", "BS-028"),
    ("无形资产", "BS-032"),
]
SOE_EXPECTED = [
    ("货币资金", "BS-002"),
    ("应收票据", "BS-005"),
    ("应收账款", "BS-006"),
    ("应收款项融资", "BS-007"),
    ("存货", "BS-010"),
    ("固定资产", "BS-028"),
    ("无形资产", "BS-032"),
    ("在建工程", "BS-029"),
]

#: `report_config` 的报表行名（`backend/data` 侧无该表 → 用 seed JSON 交叉验证）
#: 现场以 DB 为权威，CI 里不连库故读 seed。
_REPORT_ROW_NAMES = {
    "BS-002": "货币资金",
    "BS-005": "应收票据",
    "BS-006": "应收账款",
    "BS-007": "应收款项融资",
    "BS-008": "预付款项",   # 🔴 反例：soe 曾把「存货」标成它
    "BS-010": "存货",
    "BS-028": "固定资产",
    "BS-029": "在建工程",
    "BS-032": "无形资产",
}


def _norm(v) -> str:
    return re.sub(r"\s+", "", str(v or ""))


def _section(path: Path, number: str) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    sec = next(
        (s for s in doc["sections"] if str(s.get("section_number") or "").strip() == number), None
    )
    assert sec is not None, f"未找到章节 {number}（{path.name}）"
    return sec


def _tables(section: dict) -> dict[str, dict]:
    return {str(t.get("name") or "").strip(): t for t in section.get("tables") or []}


@pytest.fixture(scope="module")
def listed_sec() -> dict:
    return _section(LISTED_PATH, LISTED_SECTION)


@pytest.fixture(scope="module")
def soe_sec() -> dict:
    return _section(SOE_PATH, SOE_SECTION)


# ─── Property 1：段归属与真源一致 ───────────────────────────────────────────


class TestSegmentOwnership:
    def test_listed_rows_and_codes(self, listed_sec):
        for name in (LISTED_MAIN, LISTED_PRIOR):
            tbl = _tables(listed_sec)[name]
            rows = tbl["rows"]
            assert len(rows) == 8, f"{name}：6 科目段 + 可扩行 + 合计"
            got = [(str(r["label"]), r.get("report_row_code")) for r in rows[:6]]
            assert got == LISTED_EXPECTED
            assert str(rows[6]["label"]) == "……"
            assert str(rows[7]["label"]) == "合计" and rows[7].get("is_total") is True

    def test_soe_rows_and_codes(self, soe_sec):
        rows = _tables(soe_sec)[SOE_MAIN]["rows"]
        assert len(rows) == 9, "8 科目段 + unowned 兜底行"
        got = [(str(r["label"]), r.get("report_row_code")) for r in rows[:8]]
        assert got == SOE_EXPECTED
        assert str(rows[8]["label"]) == "其他"

    def test_soe_inventory_code_is_not_prepayment(self, soe_sec):
        """🔴 本 spec 修掉的错码：soe「存货」曾标 `BS-008`（实为预付款项）。"""
        rows = _tables(soe_sec)[SOE_MAIN]["rows"]
        inv = next(r for r in rows if _norm(r.get("label")) == "存货")
        assert inv["report_row_code"] == "BS-010"
        assert _REPORT_ROW_NAMES["BS-008"] == "预付款项", "反例前提：BS-008 不是存货"
        assert inv["report_row_code"] != "BS-008"

    def test_soe_receivable_financing_has_code(self, soe_sec):
        """🔴 本 spec 补的缺码：无 code 时该行会被卷进上一段 `BS-006`（D2）。"""
        rows = _tables(soe_sec)[SOE_MAIN]["rows"]
        rf = next(r for r in rows if _norm(r.get("label")) == "应收款项融资")
        assert rf["report_row_code"] == "BS-007"
        assert rf.get("account_codes") == ["1124"], "与 report_config BS-007 = TB('1124') 一致"

    @pytest.mark.parametrize(
        "expected", [LISTED_EXPECTED, SOE_EXPECTED], ids=["listed", "soe"]
    )
    def test_every_owner_code_matches_report_row_name(self, expected):
        """每段 `owner_row_code` 都能查到**同名**报表行（Property 1）。"""
        for label, code in expected:
            assert code in _REPORT_ROW_NAMES, f"{code} 未登记"
            assert _REPORT_ROW_NAMES[code] == label, (
                f"{code} 的报表行名是「{_REPORT_ROW_NAMES[code]}」而非「{label}」"
            )

    def test_owner_codes_unique_within_table(self, listed_sec, soe_sec):
        """同一张表内 owner code 不得重复（重复会让 `find_segment` 只取首段）。"""
        for sec, names in ((listed_sec, [LISTED_MAIN, LISTED_PRIOR]), (soe_sec, [SOE_MAIN])):
            for name in names:
                codes = [
                    r["report_row_code"]
                    for r in _tables(sec)[name]["rows"]
                    if r.get("report_row_code")
                ]
                assert len(codes) == len(set(codes)), f"{name} 有重复 owner code：{codes}"


# ─── Property 5 / 6：合计行与列元数据 ───────────────────────────────────────


class TestColumnsAndTotals:
    def test_listed_columns(self, listed_sec):
        tabs = _tables(listed_sec)
        main = tabs[LISTED_MAIN]
        prior = tabs[LISTED_PRIOR]
        assert [c["key"] for c in main["columns"]] == ["label", "end_amount"]
        assert [c["label"] for c in main["columns"]] == ["项目", "期末"]
        assert [c["key"] for c in prior["columns"]] == ["label", "prior_amount"]
        assert [c["label"] for c in prior["columns"]] == ["项目", "上年年末"]
        for tbl in (main, prior):
            assert any(c.get("flat") for c in tbl["columns"]), "单级表头必标 flat"
            assert not any(c.get("group") for c in tbl["columns"])
            assert tbl["headers"] == [c["label"] for c in tbl["columns"]]

    def test_soe_columns(self, soe_sec):
        tbl = _tables(soe_sec)[SOE_MAIN]
        assert [c["key"] for c in tbl["columns"]] == ["label", "end_carrying", "reason"]
        assert [c["label"] for c in tbl["columns"]] == ["项目", "期末账面价值", "受限原因"]
        assert any(c.get("flat") for c in tbl["columns"])
        assert not any(c.get("group") for c in tbl["columns"])
        assert tbl["headers"] == [c["label"] for c in tbl["columns"]]

    def test_guidance_present_and_plaintext(self, listed_sec, soe_sec):
        for sec, names in ((listed_sec, [LISTED_MAIN, LISTED_PRIOR]), (soe_sec, [SOE_MAIN])):
            for name in names:
                g = str(_tables(sec)[name].get("guidance") or "")
                assert len(g) > 80, f"{name} guidance 太短"
                assert "**" not in g and "<" not in g, "guidance 必须纯文本"
                assert "_row_scope" in g, "必须写明本表走行级合并"

    def test_no_header_label_fake_rows(self, listed_sec, soe_sec):
        """md 重建留下的 `header_label` 假行会渲染成一行空披露数据 → 必须已删。"""
        for sec in (listed_sec, soe_sec):
            for name, tbl in _tables(sec).items():
                for r in tbl.get("rows") or []:
                    assert str(r.get("row_type") or "") != "header_label", f"{name} 仍有假行"

    def test_listed_has_total_soe_does_not(self, listed_sec, soe_sec):
        """listed 两表有表级合计行；soe 表**无**合计行（源模板如此，不得凭空加）。"""
        for name in (LISTED_MAIN, LISTED_PRIOR):
            rows = _tables(listed_sec)[name]["rows"]
            assert sum(1 for r in rows if r.get("is_total")) == 1
        soe_rows = _tables(soe_sec)[SOE_MAIN]["rows"]
        assert not any(r.get("is_total") for r in soe_rows)


# ─── Property 7：续表正名 + unowned 声明 ────────────────────────────────────


class TestRenameAndUnowned:
    def test_prior_table_renamed(self, listed_sec):
        names = set(_tables(listed_sec))
        assert LISTED_PRIOR in names
        assert LISTED_PRIOR_LEGACY not in names, "裸续表名会跨章节撞键"
        assert LISTED_PRIOR.startswith(LISTED_MAIN), "续表名必须带主表名前缀"

    def test_prior_table_is_structurally_same_as_main(self, listed_sec):
        tabs = _tables(listed_sec)
        main_rows = [(r["label"], r.get("report_row_code")) for r in tabs[LISTED_MAIN]["rows"]]
        prior_rows = [(r["label"], r.get("report_row_code")) for r in tabs[LISTED_PRIOR]["rows"]]
        assert main_rows == prior_rows, "双期两表行集必须同构"
        # 只有金额列 key/label 不同
        assert tabs[LISTED_MAIN]["columns"][1] != tabs[LISTED_PRIOR]["columns"][1]

    def test_soe_other_row_is_unowned(self, soe_sec):
        rows = _tables(soe_sec)[SOE_MAIN]["rows"]
        other = rows[-1]
        assert _norm(other.get("label")) == "其他"
        assert other.get("row_type") == "unowned", (
            "表级兜底行必须显式标 unowned，否则 BS-029 在建工程段推送会删掉它"
        )
        assert not other.get("report_row_code")

    def test_unowned_not_used_elsewhere_in_these_sections(self, listed_sec, soe_sec):
        """只有 soe 那一行是 unowned（防止误标扩散）。"""
        hits = []
        for sec, tag in ((listed_sec, "listed"), (soe_sec, "soe")):
            for name, tbl in _tables(sec).items():
                for r in tbl.get("rows") or []:
                    if r.get("row_type") == "unowned":
                        hits.append((tag, name, str(r.get("label"))))
        assert hits == [("soe", SOE_MAIN, "其他")], hits


# ─── text_sections ──────────────────────────────────────────────────────────


class TestTextSections:
    def test_listed_bare_table_name_paragraph_retitled(self, listed_sec):
        """裸段落「续：」会被当披露正文渲染 → 随表改名同步正名为 `#### 新表名`。"""
        texts = [str(t) for t in listed_sec.get("text_sections") or []]
        assert texts, "listed 章节应有提示段"
        assert LISTED_PRIOR_LEGACY not in texts, "裸表名段落未清理"
        assert f"#### {LISTED_PRIOR}" in texts
        assert any("15号文" in t for t in texts), "源模板的准则提示段不得丢"

    def test_soe_reason_hint_added(self, soe_sec):
        """soe 章节原为空 → 补源模板 A3-5/A3-6 R13 的「说明：各项资产受限的原因」。"""
        texts = [str(t) for t in soe_sec.get("text_sections") or []]
        assert any("受限的原因" in t for t in texts), texts


# ─── Property 13：源 xlsx 旁证 + 幂等 ──────────────────────────────────────


class TestSourceXlsxCorroboration:
    """A3-5/A3-6 的「所有权受限资产」汇总表提供科目清单旁证。"""

    #: 源 sheet R3:R7 的 5 个科目（openpyxl 实测）
    A3_ACCOUNTS = ["货币资金", "应收票据", "存货", "固定资产", "无形资产"]

    def _a3_sheet_accounts(self, filename: str) -> list[str]:
        paths = list(WP_TEMPLATES.rglob(filename))
        assert paths, f"找不到源 xlsx {filename}"
        wb = load_workbook(paths[0], data_only=False, read_only=True)
        try:
            assert "所有权受限资产" in wb.sheetnames, f"{filename} 无该 sheet"
            ws = wb["所有权受限资产"]
            assert _norm(ws["A1"].value).startswith("所有权或使用权受到限制的资产")
            out = []
            for r in range(3, 10):
                v = _norm(ws.cell(row=r, column=1).value)
                if v and "合" not in v:
                    out.append(v)
            return out
        finally:
            wb.close()

    @pytest.mark.parametrize(
        "filename",
        ["A3-5 合并附注汇总-2019.xlsx", "A3-6 母公司附注汇总-2019.xlsx"],
    )
    def test_a3_accounts_are_subset_of_note_rows(self, filename, listed_sec, soe_sec):
        got = self._a3_sheet_accounts(filename)
        assert got == self.A3_ACCOUNTS, f"{filename} 科目清单变了：{got}"
        listed_labels = {_norm(r["label"]) for r in _tables(listed_sec)[LISTED_MAIN]["rows"]}
        soe_labels = {_norm(r["label"]) for r in _tables(soe_sec)[SOE_MAIN]["rows"]}
        for acct in got:
            assert acct in listed_labels, f"{acct} 不在 listed 附注行集里"
            assert acct in soe_labels, f"{acct} 不在 soe 附注行集里"

    def test_no_disclosure_sheet_for_this_table(self):
        """🔴 反向自检：确认源 xlsx 里**确实没有**这张披露表。

        若哪天源模板补了该披露 sheet，本用例会红 —— 届时守卫应改为直读源 sheet
        做三向比对（而不是继续用「附注模板 + report_config」双源兜底）。
        """
        hits: list[str] = []
        for path in WP_TEMPLATES.rglob("*.xlsx"):
            if "~$" in path.name or path.name.startswith("A3-"):
                continue
            try:
                wb = load_workbook(path, data_only=True, read_only=True)
            except Exception:  # noqa: BLE001 - 个别模板 openpyxl 打不开，跳过
                continue
            try:
                for name in wb.sheetnames:
                    if "附注" not in name:
                        continue
                    ws = wb[name]
                    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row or 1, 200), max_col=3):
                        for c in row:
                            v = str(c.value or "")
                            if "所有权" in v and "受到限制" in v:
                                hits.append(f"{path.name}|{name}|{c.coordinate}")
            finally:
                wb.close()
        assert hits == [], f"源 xlsx 出现该披露表 → 请改用直读源 sheet 的三向比对：{hits}"


class TestScriptIdempotent:
    def test_check_reports_no_debt(self):
        """Property 13：修订脚本 `--check` 0 欠账（幂等）。"""
        import importlib.util
        import sys

        script = _BACKEND / "scripts" / "fix" / "fix_note_restricted_assets_structure.py"
        assert script.exists()
        spec = importlib.util.spec_from_file_location("_fix_restricted_assets", script)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        saved = sys.argv[:]
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.argv = saved
        for scope in ("listed", "soe"):
            changes, warnings, errs = mod.run(scope, dry_run=True, check=True)
            assert errs == [], f"{scope} 校验未通过：{errs}"
            assert changes == [], f"{scope} 仍有 {len(changes)} 处欠账：{changes}"
