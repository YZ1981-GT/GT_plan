"""test_l0a_program_template.py — L0A 程序表模板守卫.

spec: l0-confirmation-source-alignment
  Requirements 1.1 ~ 1.9 / 10.3
  Property 1（模板可解析且忠于源模板）
  Property 2（编码解析落到 L0A，含反向自检）
  Property 3（新增不污染既有程序表）
  Property 4（银行借款排除声明可见）

## 修复前的缺陷链（本文件即回归防线）

`L0A` 只存在于 `procedure_table_templates.json` 的**根级**，而 `get_template`
只读 `tables` → 返回 None → `resolve_program_template_code('函证程序表F0A','L0')`
的「循环前缀不同则试 `{wp_code}A`」兜底失败 → **回退 `F0A`** →
L0 程序表实际加载「采购存货循环函证程序表」12 条，`ref_index` 全为 `F0-1`/`F0-2`。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import openpyxl
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.routers.wp_render_strategies._a_program import (  # noqa: E402
    resolve_program_template_code,
)
from app.services.procedure_table_auto_service import get_template  # noqa: E402

TEMPLATES_JSON = _REPO_ROOT / "backend" / "data" / "procedure_table_templates.json"
L0_XLSX = _REPO_ROOT / "backend" / "wp_templates" / "L" / "L0 债务循环函证.xlsx"
FIX_SCRIPT = _REPO_ROOT / "backend" / "scripts" / "fix" / "fix_l0a_program_template.py"

PROGRAM_SHEET = "函证程序表F0A"
PROGRAM_FIRST_ROW = 7

#: 其余六枢纽的函证程序表 —— 本 spec 的加法式约束要求它们逐字节不变
SIBLING_PROGRAM_CODES = ["D0A", "E0A", "F0A", "G0A", "H0A", "K0A"]

#: 修复前 `tables` 的条目数（新增 L0A 后应为 122）
TABLES_COUNT_AFTER = 122


def _load_fix_module():
    spec = importlib.util.spec_from_file_location("_fix_l0a", FIX_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def fix_mod():
    return _load_fix_module()


@pytest.fixture(scope="module")
def raw_json():
    return TEMPLATES_JSON.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tables(raw_json):
    return json.loads(raw_json)["tables"]


@pytest.fixture(scope="module")
def src_ws():
    assert L0_XLSX.exists(), f"源模板缺失: {L0_XLSX}"
    wb = openpyxl.load_workbook(L0_XLSX, data_only=False)
    yield wb[PROGRAM_SHEET]
    wb.close()


# ─── Property 1：模板可解析且忠于源模板 ─────────────────────────────────────


class TestTemplateResolvable:
    def test_get_template_returns_entry(self):
        t = get_template("L0A")
        assert t is not None, (
            "get_template('L0A') 为 None → resolve_program_template_code 会回退 F0A，"
            "L0 程序表将显示采购存货循环的程序"
        )
        assert len(t["items"]) == 12

    def test_table_name_from_source(self, src_ws):
        t = get_template("L0A")
        assert t["name"] == str(src_ws["A2"].value).strip()

    @pytest.mark.parametrize("seq", range(1, 13))
    def test_item_content_starts_with_source_desc(self, src_ws, seq):
        """`content` 以源模板 B 列原文开头（批注以 `\\n【提示】` 追加在后）。"""
        t = get_template("L0A")
        item = t["items"][seq - 1]
        assert item["seq"] == seq
        src_desc = str(src_ws[f"B{PROGRAM_FIRST_ROW + seq - 1}"].value or "").strip()
        assert src_desc
        assert item["content"].startswith(src_desc), f"seq={seq} content 首段不符源模板"

    @pytest.mark.parametrize("seq", range(1, 13))
    def test_item_category_and_ref_from_source(self, src_ws, seq):
        t = get_template("L0A")
        item = t["items"][seq - 1]
        r = PROGRAM_FIRST_ROW + seq - 1
        assert item["program_category"] == str(src_ws[f"D{r}"].value or "").strip()
        src_ref = str(src_ws[f"E{r}"].value or "").strip()
        assert (item["ref_index"] or "") == src_ref, f"seq={seq} ref_index"

    def test_ref_index_never_points_to_f0(self):
        """全部索引号指 L0-* —— 出现 F0- 即说明又回退到 F0A 模板。"""
        t = get_template("L0A")
        for item in t["items"]:
            ref = item.get("ref_index") or ""
            assert "F0-" not in ref, f"seq={item['seq']} ref_index 指向 F0：{ref}"
            if ref:
                assert ref.startswith("L0-"), ref

    def test_field_names_match_tables_convention(self):
        """字段名与 `tables` 既有形态一致 —— `content` 必填、无 description/hint。

        `ProcedureTableService` 以 `item["content"]` 读取（非 `.get`），写成
        `description` 会 KeyError；`hint` 无透传通道会被静默丢弃。
        """
        t = get_template("L0A")
        for item in t["items"]:
            assert "content" in item, "缺 content（服务侧必填读取）"
            assert "description" not in item, "不应有 description（服务侧不读）"
            assert "hint" not in item, "不应有 hint（无透传通道，会被静默丢弃）"
            assert item.get("applicable_default") == "yes"

    def test_content_field_is_consumable_by_service(self):
        """镜像 `ProcedureTableService` 的读取方式，确保不会 KeyError。"""
        t = get_template("L0A")
        for item in t["items"]:
            _ = item["content"]                      # 服务侧原样写法
            _ = item.get("ref_index", "")
            _ = item.get("category") or item.get("program_category") or ""

    def test_category_distribution(self):
        t = get_template("L0A")
        cats = [i["program_category"] for i in t["items"]]
        assert cats.count("常规★") == 9
        assert cats.count("舞弊应对/IPO/上市/新三板/重组") == 1
        assert cats.count("备选") == 2


# ─── Property 2：编码解析落到 L0A（含反向自检） ─────────────────────────────


class TestProgramCodeResolution:
    def test_resolves_to_l0a(self):
        assert resolve_program_template_code(PROGRAM_SHEET, "L0") == "L0A"

    def test_f0_sheet_in_f0_workbook_still_resolves_to_f0a(self):
        """同名 sheet 在 F0 工作簿内仍解析 F0A（循环前缀一致 → 不走兜底）。"""
        assert resolve_program_template_code(PROGRAM_SHEET, "F0") == "F0A"

    def test_reverse_selfcheck_without_l0a_falls_back_to_f0a(self, monkeypatch):
        """反向自检：`tables.L0A` 不可用时复现修复前行为（返回 F0A）。

        证明 `test_resolves_to_l0a` 不是空转 —— 它确实依赖本 spec 新增的条目。
        用 monkeypatch 替换 `get_template`，不触碰磁盘文件。
        """
        import app.routers.wp_render_strategies._a_program as ap
        import app.services.procedure_table_auto_service as svc

        real = svc.get_template

        def fake(code):
            return None if code == "L0A" else real(code)

        monkeypatch.setattr(svc, "get_template", fake)
        monkeypatch.setattr(ap, "resolve_program_template_code",
                            ap.resolve_program_template_code)
        assert resolve_program_template_code(PROGRAM_SHEET, "L0") == "F0A"

    def test_source_sheet_name_carries_the_typo(self, src_ws):
        """兜底之所以必要：源模板 tab 名带 F0A（索引号笔误），不能改 tab 名。"""
        assert PROGRAM_SHEET.endswith("F0A")
        assert src_ws.title == PROGRAM_SHEET


# ─── Property 3：新增不污染既有程序表 ───────────────────────────────────────


class TestAdditiveOnly:
    def test_tables_count(self, tables):
        assert len(tables) == TABLES_COUNT_AFTER
        assert "L0A" in tables

    @pytest.mark.parametrize("code", SIBLING_PROGRAM_CODES)
    def test_sibling_program_tables_intact(self, tables, code):
        """六枢纽程序表仍可解析且 items 非空（未被 L0A 新增波及）。"""
        t = tables.get(code)
        assert t is not None, f"tables.{code} 缺失"
        assert t.get("items"), f"tables.{code}.items 为空"
        assert t.get("name")

    def test_f0a_name_and_item_count_unchanged(self, tables):
        assert tables["F0A"]["name"] == "采购存货循环函证程序表"
        assert len(tables["F0A"]["items"]) == 12

    def test_f0a_refs_still_point_to_f0(self, tables):
        """F0A 的索引号仍指 F0-*（反向确认两套模板未串味）。"""
        refs = [i.get("ref_index") or "" for i in tables["F0A"]["items"]]
        assert any(r.startswith("F0-") for r in refs)
        assert not any(r.startswith("L0-") for r in refs)

    def test_root_level_l0a_untouched(self, raw_json):
        """根级 L0A（10 items，自造版）保持不动 —— 属平台级收敛议题，本 spec 不碰。"""
        data = json.loads(raw_json)
        assert "L0A" in data, "根级 L0A 不应被删除"
        assert data["L0A"]["name"] == "筹资循环函证实质性程序表"
        assert len(data["L0A"]["items"]) == 10
        assert data["L0A"] is not data["tables"]["L0A"]

    def test_file_round_trip_stable(self, raw_json):
        """文件序列化格式未被改写（indent=2 / ensure_ascii=False / 无末尾换行）。"""
        data = json.loads(raw_json)
        assert json.dumps(data, ensure_ascii=False, indent=2) == raw_json


# ─── Property 4：银行借款排除声明可见 ───────────────────────────────────────


class TestBankLoanExclusion:
    def test_seq1_content_carries_exclusion_hint(self, src_ws):
        t = get_template("L0A")
        content = t["items"][0]["content"]
        src_hint = str(src_ws[f"G{PROGRAM_FIRST_ROW}"].value or "").strip()
        assert src_hint
        assert "【提示】" in content
        assert src_hint in content

    def test_seq8_content_carries_platform_hint(self, src_ws):
        t = get_template("L0A")
        content = t["items"][7]["content"]
        src_hint = str(src_ws[f"G{PROGRAM_FIRST_ROW + 7}"].value or "").strip()
        assert src_hint
        assert src_hint in content

    def test_bank_wording_only_in_exclusion_declaration(self):
        """「银行」二字只出现在排除声明处 —— 别处出现即说明混入了借款循环内容。"""
        t = get_template("L0A")
        hits = [i["seq"] for i in t["items"] if "银行" in i["content"]]
        assert hits == [1], f"「银行」应只出现在 seq 1，实得 {hits}"

    def test_excluded_bank_loan_codes_not_referenced(self, fix_mod):
        """反向断言：模板内容不引用被排除的 2001/2501（公式预设侧由另一守卫覆盖）。"""
        t = get_template("L0A")
        blob = json.dumps(t, ensure_ascii=False)
        for code in ("2001", "2501"):
            assert code not in blob, f"L0A 模板不应引用银行借款科目 {code}"
        assert fix_mod.WP_CODE == "L0A"


# ─── 幂等脚本自身 ────────────────────────────────────────────────────────────


class TestFixScript:
    def test_check_reports_zero_gaps(self, fix_mod, tables):
        gaps = fix_mod.diff_entry(tables.get("L0A"), fix_mod.build_l0a_entry())
        assert gaps == [], f"欠账未归零: {gaps}"

    def test_build_entry_shape(self, fix_mod):
        entry = fix_mod.build_l0a_entry()
        assert entry["name"] == fix_mod.TABLE_NAME
        assert len(entry["items"]) == 12
        assert len(fix_mod.SOURCE_ITEMS) == 12

    def test_diff_detects_missing_entry(self, fix_mod):
        """反向自检：条目缺失时必须报欠账（防 diff 恒返空）。"""
        gaps = fix_mod.diff_entry(None, fix_mod.build_l0a_entry())
        assert len(gaps) == 1 and "缺失" in gaps[0]

    def test_diff_detects_content_drift(self, fix_mod):
        """反向自检：内容漂移时必须报欠账。"""
        expected = fix_mod.build_l0a_entry()
        mutated = json.loads(json.dumps(expected, ensure_ascii=False))
        mutated["items"][0]["content"] = "被篡改的程序描述"
        gaps = fix_mod.diff_entry(mutated, expected)
        assert any("content" in g for g in gaps), gaps

    def test_round_trip_guard_exists(self, fix_mod, raw_json):
        """round-trip 自检对当前文件成立（否则 --apply 会拒绝写盘）。"""
        assert fix_mod._round_trip_ok(raw_json, json.loads(raw_json))

    def test_hint_prefix_constant(self, fix_mod):
        assert fix_mod.HINT_PREFIX == "\n【提示】"
