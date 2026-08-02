"""附注「货币资金」章节结构守卫（源 xlsx ↔ 模板 ↔ 同步载荷 三向比对）。

**Validates: Requirements 5.1~5.9, 6.1~6.4**

Property 5（三向一致）、Property 6（单级表必须 flat）

spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/ (Task 12)
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

MAIN_TABLE = "货币资金"
RESTRICTED_TABLE = "受限制的货币资金明细"

SECTIONS = {"listed": ("五、1", LISTED_PATH), "soe": ("八、1", SOE_PATH)}
SOURCE_SHEETS = {
    "listed": "附注披露信息(上市公司)",
    "soe": "附注披露信息(国企)",
}


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

    def test_soe_main_rows_verbatim(self, wb, sections):
        """国企主表 = 源 xlsx R8~R12（**5 行**）。"""
        ws = wb[SOURCE_SHEETS["soe"]]
        want = _col_a(ws, 8, 12)
        got = [_norm(r.get("label")) for r in _tables(sections["soe"])[MAIN_TABLE]["rows"]]
        assert got == want, f"国企主表行集与源 xlsx R8~R12 不一致\n模板={got}\n源={want}"

    def test_soe_first_row_is_cash_not_cash_on_hand(self, wb, sections):
        """🔴 国企首行字面是「现金」，上市是「库存现金」（源模板实证差异，非笔误）。"""
        assert _norm(wb[SOURCE_SHEETS["soe"]]["A8"].value) == "现金"
        assert _norm(wb[SOURCE_SHEETS["listed"]]["A8"].value) == "库存现金"
        assert _tables(sections["soe"])[MAIN_TABLE]["rows"][0]["label"] == "现金"
        assert _tables(sections["listed"])[MAIN_TABLE]["rows"][0]["label"] == "库存现金"

    def test_soe_has_no_overseas_data_row(self, wb, sections):
        """🔴 国企侧「其中：存放在境外的款项总额」是**假行** —— 源 R13 是括注文字。"""
        r13 = str(wb[SOURCE_SHEETS["soe"]]["A13"].value or "")
        assert r13.startswith("（") and "单独说明" in r13, (
            f"源 xlsx 国企 R13 应为括注，实为 {r13!r}"
        )
        labels = [_norm(r.get("label")) for r in _tables(sections["soe"])[MAIN_TABLE]["rows"]]
        assert "其中：存放在境外的款项总额" not in labels
        # 上市侧 R15 是真数据行（对照，证明不是一刀切删）
        assert _norm(wb[SOURCE_SHEETS["listed"]]["A15"].value) == "其中：存放在境外的款项总额"
        listed_labels = [
            _norm(r.get("label")) for r in _tables(sections["listed"])[MAIN_TABLE]["rows"]
        ]
        assert "其中：存放在境外的款项总额" in listed_labels

    def test_listed_main_excludes_reconciliation_row(self, wb, sections):
        """源 xlsx R16 是**勾稽校验行**（`B16=B14-D62`），不是披露行 → 不进模板。"""
        ws = wb[SOURCE_SHEETS["listed"]]
        assert ws["A16"].value in (None, ""), "源 R16 的 A 列应为空（只有 B/C 有校验公式）"
        assert "=B14-D62" in str(ws["B16"].value or "").replace(" ", "")
        assert len(_tables(sections["listed"])[MAIN_TABLE]["rows"]) == 8

    @pytest.mark.parametrize("variant", ["listed", "soe"])
    def test_restricted_rows_verbatim(self, wb, sections, variant):
        """②表 = 源 xlsx（国企）R17~R21 五类 + 合计；R22 的 `…` 是动态插行标记不 seed。"""
        ws = wb[SOURCE_SHEETS["soe"]]
        want = _col_a(ws, 17, 21) + ["合计"]
        got = [
            _norm(r.get("label"))
            for r in _tables(sections[variant])[RESTRICTED_TABLE]["rows"]
        ]
        assert got == want, f"{variant} ②表行集不一致\n模板={got}\n源={want}"

    def test_restricted_excludes_reserve_row_and_ellipsis(self, wb, sections):
        """🔴 源 xlsx **没有**「金融企业法定存款准备金或备付金」；R22 `…` 不得 seed。"""
        ws = wb[SOURCE_SHEETS["soe"]]
        source_labels = {_norm(ws.cell(row=r, column=1).value) for r in range(17, 24)}
        assert "金融企业法定存款准备金或备付金" not in source_labels
        assert _norm(ws["A22"].value) == "…", "源 R22 应是动态插行标记 `…`"
        for variant in ("listed", "soe"):
            labels = [
                _norm(r.get("label"))
                for r in _tables(sections[variant])[RESTRICTED_TABLE]["rows"]
            ]
            assert "金融企业法定存款准备金或备付金" not in labels
            assert "…" not in labels
            assert "" not in labels, "不得 seed 空占位行"

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
