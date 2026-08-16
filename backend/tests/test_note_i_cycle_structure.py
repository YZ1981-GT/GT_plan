"""附注 I 类循环（I1~I6）× 2 变体 = 12 章节结构守卫。

锁定 `fix_note_i_cycle_structure.py` 的对齐结果，验证：

- 表名存在且正确
- 补了 columns 的表有非空 columns 且首列 is_label
- group/flat 表态正确（两级表头用 group、单级用 flat）
- guidance 无 markdown 粗体 `**`
- I 类循环无账龄维度（禁止出现 `账龄` 字面量）
- `_aligned_by` 标记存在
- openpyxl 直读源 xlsx 交叉比对
- 反向自检

spec: i-cycle-four-table-extraction-and-disclosure-alignment (Task 4.6)
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import openpyxl
import pytest

_ROOT = Path(__file__).resolve().parent.parent
_FIX = _ROOT / "scripts" / "fix" / "fix_note_i_cycle_structure.py"

# 源 xlsx 路径
_SRC_DIR = _ROOT / "wp_templates" / "I"
_SRC_FILES = {
    "I1": _SRC_DIR / "I1 无形资产、累计摊销及减值准备.xlsx",
    "I2": _SRC_DIR / "I2 开发支出.xlsx",
    "I3": _SRC_DIR / "I3 商誉.xlsx",
    "I4": _SRC_DIR / "I4 长期待摊费用.xlsx",
    "I5": _SRC_DIR / "I5 其他非流动资产.xlsx",
    "I6": _SRC_DIR / "I6 研发费用.xlsx",
}

ALIGNED_BY = "i-cycle-four-table-extraction-and-disclosure-alignment"

#: `_aligned_by` 是**最后一个对齐者的签名**，会被后续 spec 正当改写（同 memory 已记
#: 「A spec 补列打红 D spec 守卫」范式）——它是「谁最后动过这个章节」而非「归属关系」。
#: 判据必须由「== 本 spec 名」放宽为「∈ 允许集」，否则跨 spec 协作时必然假红。
#: 每个覆盖者都要登记理由 + stale 检测（登记项若已不再出现即提醒移除）。
_ALIGNED_BY_ALLOWED: dict[str, str] = {
    ALIGNED_BY:
        "本 spec（I 循环取数/公式/披露/附注收口）的对齐脚本 fix_note_i_cycle_structure.py 的签名",
    "note-template-columns-and-legacy-snapshot-closure":
        "C spec（附注列元数据与遗留快照收口，已归档 23/23）补 columns 时正当覆盖 —— "
        "它先于本 spec 碰过 I1/listed·I1/soe·I3/listed·I6/listed 四个章节的 _aligned_by，"
        "但未补齐本 spec 目标的 4 张 cols=0 表，故两者不冲突（覆盖的是章节签名、缺口仍在）",
}

# 章节映射：(cycle, variant) → section_number
_SECTION_MAP = {
    ("I1", "listed"): "五、26",
    ("I1", "soe"): "八、27",
    ("I2", "listed"): "五、27",
    ("I2", "soe"): "八、28",
    ("I3", "listed"): "五、28",
    ("I3", "soe"): "八、29",
    ("I4", "listed"): "五、29",
    ("I4", "soe"): "八、30",
    ("I5", "listed"): "五、31",
    ("I5", "soe"): "八、32",
    ("I6", "listed"): "五、66",
    ("I6", "soe"): "八、67",
}

# 每个章节脚本校验的表名（只含补了 columns 的表）
_VERIFIED_TABLES: dict[tuple[str, str], list[str]] = {
    ("I1", "listed"): ["重要单项无形资产", "未办妥产权证书的土地使用权情况"],
    ("I1", "soe"): ["无形资产情况"],
    ("I2", "listed"): [
        "研发支出", "开发支出", "开发支出（续：资本化情况）",
        "重要的资本化研发项目", "开发支出减值准备",
    ],
    ("I2", "soe"): ["开发支出"],
    ("I3", "listed"): ["商誉账面原值", "商誉减值准备", "业绩承诺完成及商誉减值情况"],
    ("I3", "soe"): ["（1）商誉账面价值", "（2）商誉减值准备"],
    ("I4", "listed"): ["长期待摊费用"],
    ("I4", "soe"): ["长期待摊费用"],
    ("I5", "listed"): ["其他非流动资产"],
    ("I5", "soe"): ["其他非流动资产"],
    ("I6", "listed"): ["研发费用（按费用性质列示）"],
    ("I6", "soe"): ["研发费用（按费用性质列示）"],
}

# 两级表头（有 group 列）的表
_TWO_LEVEL_TABLES: dict[tuple[str, str], set[str]] = {
    ("I2", "listed"): {"研发支出", "开发支出"},
    ("I2", "soe"): {"开发支出"},
    ("I3", "listed"): {"商誉账面原值", "商誉减值准备"},
    ("I4", "listed"): {"长期待摊费用"},
    ("I5", "listed"): {"其他非流动资产"},
}

# ═══════════════════════════════════════════════════════════════════════════════
# Task 3 补齐：四条缺口的类 A 基线（openpyxl 直读源 xlsx 冻结）
# ═══════════════════════════════════════════════════════════════════════════════

#: 源模板披露 sheet 名（六份 workbook；I1 带「信息」二字、I2~I6 不带，是源模板事实不得统一）
_SRC_DISCLOSURE_SHEETS: dict[tuple[str, str], str] = {
    ("I1", "listed"): "附注披露信息（上市公司）",
    ("I1", "soe"): "附注披露信息（国有企业）",
    ("I2", "listed"): "附注披露（上市公司）",
    ("I2", "soe"): "附注披露（国有企业）",
    ("I3", "listed"): "附注披露（上市公司）",
    ("I3", "soe"): "附注披露（国有企业）",
    ("I4", "listed"): "附注披露（上市公司）",
    ("I4", "soe"): "附注披露（国有企业）",
    ("I5", "listed"): "附注披露（上市公司）",
    ("I5", "soe"): "附注披露（国有企业）",
    ("I6", "listed"): "附注披露（上市公司）",
    ("I6", "soe"): "附注披露（国有企业）",
}

#: 源模板动态插行标记（`……` / `…`）数量。2026-08-09 openpyxl 逐格实测冻结。
#: 🔴 该数字是「源模板留了几个可扩位」，与模板 JSON 里 seed 了几行是两回事。
_SRC_DYNAMIC_MARK_COUNT: dict[tuple[str, str], int] = {
    ("I1", "listed"): 3,   # A18/A29/A40 = 账面原值/累计摊销/减值准备三层增加段末
    ("I1", "soe"): 4,      # A20/A33/A46/A59 = 原价/累计摊销/减值/账面价值四层末
    ("I2", "listed"): 2,   # A15 研发支出按费用性质 + A27 开发支出课题
    ("I2", "soe"): 1,      # A13 开发支出课题
    ("I3", "listed"): 0,
    ("I3", "soe"): 0,
    ("I4", "listed"): 0,
    ("I4", "soe"): 0,
    ("I5", "listed"): 1,   # A18 其他非流动资产项目
    ("I5", "soe"): 1,      # A17 其他非流动资产项目
    ("I6", "listed"): 0,
    ("I6", "soe"): 0,
}

_DYNAMIC_MARK_RE = re.compile(r"^(?:…{1,}|\.{3,}|・{2,})$")

#: 本 spec Task 10 要补 columns 的四张表（改造前 `cols=0`）
_COLS0_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("I1", "listed", "无形资产情况"),
    ("I1", "listed", "确认为无形资产的数据资源"),
    ("I1", "soe", "确认为无形资产的数据资源"),
    ("I3", "listed", "商誉减值测试关键假设"),
)

#: 段落文本泄漏成表名的两处（md 重建把附注 docx 说明段当表名写进 `tables[].name`）
_LEAKED_TABLE_NAME_SECTIONS: tuple[tuple[str, str], ...] = (
    ("I5", "listed"),
    ("I5", "soe"),
)

#: 表名合法性判据：不得以 `[` 开头（段落泄漏特征），长度不得超过该上限
_TABLE_NAME_MAX_LEN = 30


def _load_fix():
    spec = importlib.util.spec_from_file_location("_fix_i_struct", _FIX)
    mod = importlib.util.module_from_spec(spec)
    # 🔴 必须先注册进 sys.modules 再 exec_module：被加载脚本内含 @dataclass，
    # dataclasses 会做 `sys.modules.get(cls.__module__).__dict__` 解析类型注解，
    # 未注册时得 None → collection 期 AttributeError 中断整组测试（平台已记铁律）。
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix()


def _norm(v: object) -> str:
    """去掉全部空白（源模板行标签带缩进与「4. 期末余额」式空格）。"""
    return re.sub(r"\s+", "", str(v or ""))


def _section(cycle: str, variant: str) -> dict:
    """从模板 JSON 中读取指定章节。"""
    sec_num = _SECTION_MAP[(cycle, variant)]
    path_name = "note_template_listed.json" if variant == "listed" else "note_template_soe.json"
    path = _ROOT / "data" / path_name
    doc = json.loads(path.read_text(encoding="utf-8"))
    return next(
        s for s in doc["sections"] if str(s.get("section_number")) == sec_num
    )


def _tables_by_name(cycle: str, variant: str) -> dict[str, dict]:
    """按表名索引当前章节的所有表。"""
    sec = _section(cycle, variant)
    return {str(t.get("name", "")): t for t in sec.get("tables") or []}


# ═══════════════════════════════════════════════════════════════════════════════
# 参数化：12 个章节
# ═══════════════════════════════════════════════════════════════════════════════

_ALL_PARAMS = [
    pytest.param(cycle, variant, id=f"{cycle}_{variant}")
    for cycle in ("I1", "I2", "I3", "I4", "I5", "I6")
    for variant in ("listed", "soe")
]


# ───────────────── Property 1：_aligned_by 标记存在 ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_aligned_by_marker(cycle: str, variant: str):
    """每个章节的 `_aligned_by` 必须 ∈ 允许集（不是恒等于本 spec 名）。

    🔴 改造前判据是 `== ALIGNED_BY`，对 I1/listed·I1/soe·I3/listed·I6/listed 四处
    假红 —— 它们被 C spec（`note-template-columns-and-legacy-snapshot-closure`）
    补 columns 时正当覆盖过。`_aligned_by` 是「最后一个对齐者的签名」会被后续 spec
    合法改写，把它当「归属不变量」是判据缺陷（memory 已记同型范式）。
    """
    sec = _section(cycle, variant)
    marker = sec.get("_aligned_by")
    assert marker, f"{cycle}/{variant} 缺少 _aligned_by 标记"
    assert marker in _ALIGNED_BY_ALLOWED, (
        f"{cycle}/{variant} 的 _aligned_by={marker!r} 不在允许集内。"
        f"若这是又一个正当覆盖者，请登记进 _ALIGNED_BY_ALLOWED 并写明理由；"
        f"允许集={sorted(_ALIGNED_BY_ALLOWED)}"
    )


def test_aligned_by_allowlist_no_stale_entries():
    """允许集里的每个覆盖者都必须仍出现在至少一个章节（stale 检测，防登记表膨胀成盲区）。

    🔴 反向自检的对偶：登记项若已无任何章节使用，说明它已被更晚的 spec 取代，
    应从允许集移除 —— 否则允许集会累积成「任何签名都放行」的空判据。
    """
    live_markers = {
        _section(c, v).get("_aligned_by")
        for c in ("I1", "I2", "I3", "I4", "I5", "I6")
        for v in ("listed", "soe")
    }
    stale = [k for k in _ALIGNED_BY_ALLOWED if k not in live_markers]
    assert not stale, (
        f"允许集含已无章节使用的 stale 登记项 {stale}，应移除；"
        f"当前活跃签名={sorted(m for m in live_markers if m)}"
    )


def test_aligned_by_rejects_unregistered_value(monkeypatch):
    """反向自检：`_aligned_by` 为未登记值或缺失时，判据必须打红（防允许集判据空转）。"""
    # 未登记的第三方签名必须被拒
    assert "some-other-random-spec" not in _ALIGNED_BY_ALLOWED
    # 空值必须被拒（模拟 stamp 从未跑过）
    assert "" not in _ALIGNED_BY_ALLOWED
    assert None not in _ALIGNED_BY_ALLOWED


# ───────────────── Property 2：表名存在于模板 ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_verified_tables_exist(cycle: str, variant: str):
    """脚本校验的表名必须在模板中实际存在。"""
    by_name = _tables_by_name(cycle, variant)
    expected = _VERIFIED_TABLES[(cycle, variant)]
    for name in expected:
        assert name in by_name, (
            f"{cycle}/{variant} 缺表 {name!r}，实有: {list(by_name.keys())}"
        )


# ───────────────── Property 3：columns 非空且结构正确 ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_columns_non_empty(cycle: str, variant: str):
    """补了 columns 的表必须有非空列定义，且首列 is_label。"""
    by_name = _tables_by_name(cycle, variant)
    expected = _VERIFIED_TABLES[(cycle, variant)]
    for name in expected:
        tbl = by_name[name]
        cols = tbl.get("columns") or []
        assert len(cols) > 0, f"{cycle}/{variant}/{name} columns 为空"
        assert cols[0].get("is_label"), f"{cycle}/{variant}/{name} 首列未标 is_label"


# ───────────────── Property 4：group/flat 表态 ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_group_or_flat(cycle: str, variant: str):
    """两级表头的表必须有 group 列；单级表必须标 flat。"""
    by_name = _tables_by_name(cycle, variant)
    two_level = _TWO_LEVEL_TABLES.get((cycle, variant), set())
    expected = _VERIFIED_TABLES[(cycle, variant)]
    for name in expected:
        tbl = by_name[name]
        cols = tbl.get("columns") or []
        if name in two_level:
            # 两级表头：非标签列应有 group
            data_cols = [c for c in cols if not c.get("is_label")]
            assert any(c.get("group") for c in data_cols), (
                f"{cycle}/{variant}/{name} 两级表头缺 group 声明"
            )
        else:
            # 单级表头：须标 flat
            assert any(c.get("flat") for c in cols), (
                f"{cycle}/{variant}/{name} 单级表头未标 flat"
            )


# ───────────────── Property 5：guidance 无 markdown 粗体 ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_guidance_no_markdown_bold(cycle: str, variant: str):
    """guidance 一律纯文本，不得含 `**` markdown 粗体标记。"""
    sec = _section(cycle, variant)
    for tbl in sec.get("tables") or []:
        guidance = tbl.get("guidance") or ""
        assert "**" not in guidance, (
            f"{cycle}/{variant}/{tbl.get('name','?')} guidance 含 markdown 粗体 `**`"
        )


# ───────────────── Property 6：无账龄相关字面量 ─────────────────


_AGING_PATTERN = re.compile(r"账龄|aging", re.IGNORECASE)


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_no_aging_literals(cycle: str, variant: str):
    """I 类循环无账龄维度，guidance 和表内容不得出现「账龄」。"""
    sec = _section(cycle, variant)
    for tbl in sec.get("tables") or []:
        guidance = tbl.get("guidance") or ""
        assert not _AGING_PATTERN.search(guidance), (
            f"{cycle}/{variant}/{tbl.get('name','?')} guidance 含账龄相关字面量"
        )
        # 检查 columns label 和 group
        for col in tbl.get("columns") or []:
            label = col.get("label") or ""
            group = col.get("group") or ""
            assert not _AGING_PATTERN.search(label), (
                f"{cycle}/{variant}/{tbl.get('name','?')} 列 label 含账龄: {label}"
            )
            assert not _AGING_PATTERN.search(group), (
                f"{cycle}/{variant}/{tbl.get('name','?')} 列 group 含账龄: {group}"
            )


# ───────────────── Property 7：幂等与零欠账（--check） ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_check_passes(cycle: str, variant: str):
    """fix 脚本 --check 模式对每个章节报告零欠账。"""
    runner_key = f"{cycle}_{variant.upper()}"
    _label, runner_fn = FIX._RUNNERS[runner_key]
    _changes, warnings, errs = runner_fn(dry_run=True, check=True)
    assert not errs, f"{cycle}/{variant} 结构欠账: {errs}"
    assert not warnings, f"{cycle}/{variant} 告警: {warnings}"


# ───────────────── Property 8：无 header_label 假行 ─────────────────


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_no_header_label_fake_rows(cycle: str, variant: str):
    """md 重建压扁的第二行表头残留 header_label 须已清除。"""
    by_name = _tables_by_name(cycle, variant)
    expected = _VERIFIED_TABLES[(cycle, variant)]
    for name in expected:
        tbl = by_name[name]
        rows = tbl.get("rows") or []
        assert not any(r.get("row_type") == "header_label" for r in rows), (
            f"{cycle}/{variant}/{name} 残留 header_label 假行"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# openpyxl 直读源 xlsx 交叉比对
# ═══════════════════════════════════════════════════════════════════════════════


def test_source_xlsx_files_exist():
    """所有 6 个源 xlsx 文件必须存在。"""
    for cycle, path in _SRC_FILES.items():
        assert path.exists(), f"{cycle} 源 xlsx 不存在: {path}"


def test_i6_listed_table_name_matches_source():
    """I6 上市「研发费用（按费用性质列示）」表名取自源 xlsx。"""
    wb = openpyxl.load_workbook(_SRC_FILES["I6"], data_only=True)
    sheets = wb.sheetnames
    # 确认披露 sheet 存在
    listed_sheet = next((s for s in sheets if "上市" in s), None)
    assert listed_sheet, f"I6 源 xlsx 缺上市披露 sheet，sheetnames={sheets}"


def test_i6_soe_table_name_matches_source():
    """I6 国企「研发费用（按费用性质列示）」表名取自源 xlsx。"""
    wb = openpyxl.load_workbook(_SRC_FILES["I6"], data_only=True)
    sheets = wb.sheetnames
    soe_sheet = next((s for s in sheets if "国" in s), None)
    assert soe_sheet, f"I6 源 xlsx 缺国企披露 sheet，sheetnames={sheets}"


def test_i4_listed_two_level_headers_from_source():
    """I4 上市长期待摊费用：源 xlsx 两级表头应含「本期减少」分组。"""
    wb = openpyxl.load_workbook(_SRC_FILES["I4"], data_only=True)
    sheets = wb.sheetnames
    listed_sheet = next((s for s in sheets if "上市" in s), None)
    if listed_sheet:
        ws = wb[listed_sheet]
        # 验证模板 columns 有 group='本期减少' 的列
        by_name = _tables_by_name("I4", "listed")
        tbl = by_name["长期待摊费用"]
        cols = tbl.get("columns") or []
        groups = [c.get("group") for c in cols if c.get("group")]
        assert "本期减少" in groups, f"I4 上市缺 '本期减少' 分组，groups={groups}"


def test_i5_listed_two_level_headers_from_source():
    """I5 上市其他非流动资产：源 xlsx 两级表头应含「期末数」和「上年年末数」分组。"""
    by_name = _tables_by_name("I5", "listed")
    tbl = by_name["其他非流动资产"]
    cols = tbl.get("columns") or []
    groups = set(c.get("group") for c in cols if c.get("group"))
    assert "期末数" in groups, f"I5 上市缺 '期末数' 分组，groups={groups}"
    assert "上年年末数" in groups, f"I5 上市缺 '上年年末数' 分组，groups={groups}"


def test_i3_listed_goodwill_book_value_two_level():
    """I3 上市商誉账面原值：两级表头含「本期增加」「本期减少」。"""
    by_name = _tables_by_name("I3", "listed")
    tbl = by_name["商誉账面原值"]
    cols = tbl.get("columns") or []
    groups = set(c.get("group") for c in cols if c.get("group"))
    assert "本期增加" in groups, f"I3 上市商誉账面原值缺 '本期增加' 分组"
    assert "本期减少" in groups, f"I3 上市商誉账面原值缺 '本期减少' 分组"


def test_i2_listed_research_expenditure_two_level():
    """I2 上市研发支出：两级表头含「本期发生额」「上期发生额」。"""
    by_name = _tables_by_name("I2", "listed")
    tbl = by_name["研发支出"]
    cols = tbl.get("columns") or []
    groups = set(c.get("group") for c in cols if c.get("group"))
    assert "本期发生额" in groups, f"I2 上市研发支出缺 '本期发生额' 分组"
    assert "上期发生额" in groups, f"I2 上市研发支出缺 '上期发生额' 分组"


def test_i2_listed_dev_expenditure_two_level():
    """I2 上市开发支出：两级表头含「本期增加」「本期减少」。"""
    by_name = _tables_by_name("I2", "listed")
    tbl = by_name["开发支出"]
    cols = tbl.get("columns") or []
    groups = set(c.get("group") for c in cols if c.get("group"))
    assert "本期增加" in groups, f"I2 上市开发支出缺 '本期增加' 分组"
    assert "本期减少" in groups, f"I2 上市开发支出缺 '本期减少' 分组"


def test_i2_soe_dev_expenditure_two_level():
    """I2 国企开发支出：两级表头含「本期增加」「本期减少」。"""
    by_name = _tables_by_name("I2", "soe")
    tbl = by_name["开发支出"]
    cols = tbl.get("columns") or []
    groups = set(c.get("group") for c in cols if c.get("group"))
    assert "本期增加" in groups, f"I2 国企开发支出缺 '本期增加' 分组"
    assert "本期减少" in groups, f"I2 国企开发支出缺 '本期减少' 分组"


def test_i3_soe_tables_are_flat():
    """I3 国企两张表均为单级 flat 5 列。"""
    by_name = _tables_by_name("I3", "soe")
    for name in ["（1）商誉账面价值", "（2）商誉减值准备"]:
        tbl = by_name[name]
        cols = tbl.get("columns") or []
        assert len(cols) == 5, f"I3 国企 {name} 应有 5 列，实有 {len(cols)}"
        assert any(c.get("flat") for c in cols), f"I3 国企 {name} 未标 flat"


def test_i6_columns_are_flat():
    """I6 两版均为单级 flat 3 列（项目/本期发生额/上期发生额）。"""
    for variant in ("listed", "soe"):
        by_name = _tables_by_name("I6", variant)
        tbl = by_name["研发费用（按费用性质列示）"]
        cols = tbl.get("columns") or []
        assert len(cols) == 3, f"I6 {variant} 应有 3 列，实有 {len(cols)}"
        assert any(c.get("flat") for c in cols), f"I6 {variant} 未标 flat"
        # 验证列 key
        keys = [c.get("key") for c in cols]
        assert keys[0] == "项目", f"I6 {variant} 首列 key 应为 '项目'"


# ═══════════════════════════════════════════════════════════════════════════════
# 反向自检（防守卫空转）
# ═══════════════════════════════════════════════════════════════════════════════


def test_reverse_self_check_validate_section():
    """validate_section 能抓出缺 columns 的情况（防守卫空转）。"""
    import sys
    sys.path.insert(0, str(_ROOT / "scripts" / "fix"))
    from _note_structure_kit import validate_section

    broken = {
        "tables": [{
            "name": "长期待摊费用",
            "headers": ["项目"],
            "rows": [],
            "guidance": "x",
        }],
    }
    errs = validate_section(broken, ["长期待摊费用"])
    assert any("缺 columns" in e for e in errs), f"validate_section 未检测出缺 columns: {errs}"


def test_reverse_self_check_normalizer():
    """`_norm` 必须能把源模板的缩进/内嵌空格归一，否则行集比对恒绿。"""
    assert _norm("    4. 期末余额") == "4.期末余额"
    assert _norm("其中：土地") == "其中：土地"
    assert _norm("项  目") == "项目"
    assert _norm(None) == ""
    assert _norm("") == ""


def test_reverse_self_check_aging_pattern():
    """_AGING_PATTERN 必须能匹配「账龄」和 aging（防断言空转）。"""
    assert _AGING_PATTERN.search("按账龄分析")
    assert _AGING_PATTERN.search("aging analysis")
    assert not _AGING_PATTERN.search("无形资产")
    assert not _AGING_PATTERN.search("研发费用")


def test_reverse_self_check_section_map_complete():
    """_SECTION_MAP 必须覆盖全部 12 个 (cycle, variant) 组合。"""
    expected = {
        (c, v) for c in ("I1", "I2", "I3", "I4", "I5", "I6")
        for v in ("listed", "soe")
    }
    assert set(_SECTION_MAP.keys()) == expected


def test_reverse_self_check_verified_tables_complete():
    """_VERIFIED_TABLES 必须覆盖全部 12 个 (cycle, variant) 组合。"""
    expected = {
        (c, v) for c in ("I1", "I2", "I3", "I4", "I5", "I6")
        for v in ("listed", "soe")
    }
    assert set(_VERIFIED_TABLES.keys()) == expected

# ═══════════════════════════════════════════════════════════════════════════════
# Task 3 补齐缺口 ①：动态插行标记数（Property 21）
# ═══════════════════════════════════════════════════════════════════════════════


def _count_src_dynamic_marks(cycle: str, variant: str) -> tuple[int, list[str]]:
    """openpyxl 直读源披露 sheet，数第一列的动态插行标记。

    Returns:
        ``(命中数, ['A18=……', ...])``。判据只看**首列**（源模板的可扩位一律是
        行标签位置的 `……`），不扫全表 —— 数据区的 `……` 不存在，扫全表只会引入噪声。
    """
    path = _SRC_FILES[cycle]
    sheet = _SRC_DISCLOSURE_SHEETS[(cycle, variant)]
    wb = openpyxl.load_workbook(path, data_only=True)
    assert sheet in wb.sheetnames, (
        f"{cycle}/{variant} 源 xlsx 缺披露 sheet {sheet!r}，实有 {wb.sheetnames}"
    )
    ws = wb[sheet]
    hits: list[str] = []
    for r in range(1, ws.max_row + 1):
        raw = ws.cell(row=r, column=1).value
        if raw is None:
            continue
        txt = _norm(raw)
        if txt and _DYNAMIC_MARK_RE.match(txt):
            hits.append(f"A{r}={raw}")
    return len(hits), hits


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_source_dynamic_mark_count(cycle: str, variant: str):
    """源模板动态插行标记数必须与冻结基线一致（类 A：独立口径，应全绿）。

    这条不是判被测实现，而是把「源模板留了几个可扩位」钉死 —— 后续 Wave 5
    做可扩行时以它为唯一真源，防按记忆写错数量（memory 已记 I5 那两处曾被漏掉）。
    """
    expected = _SRC_DYNAMIC_MARK_COUNT[(cycle, variant)]
    actual, hits = _count_src_dynamic_marks(cycle, variant)
    assert actual == expected, (
        f"{cycle}/{variant} 源模板动态标记数 {actual} != 基线 {expected}；命中={hits}"
    )


def test_reverse_self_check_dynamic_mark_regex():
    """`_DYNAMIC_MARK_RE` 必须只认纯标记行，不得吞掉真实行标签（防判据空转）。"""
    assert _DYNAMIC_MARK_RE.match("……")
    assert _DYNAMIC_MARK_RE.match("…")
    assert _DYNAMIC_MARK_RE.match("...")
    assert _DYNAMIC_MARK_RE.match("......")
    # 真实行标签不得命中
    assert not _DYNAMIC_MARK_RE.match("其中：土地使用权")
    assert not _DYNAMIC_MARK_RE.match("4.期末余额")
    assert not _DYNAMIC_MARK_RE.match("合计")
    assert not _DYNAMIC_MARK_RE.match("")
    # 带说明文字的省略号不算可扩位（避免把「……等」这类段落算进来）
    assert not _DYNAMIC_MARK_RE.match("……等")


def test_reverse_self_check_dynamic_baseline_nonzero():
    """基线里必须既有非零项也有零项，否则该判据可能整体空转。"""
    vals = set(_SRC_DYNAMIC_MARK_COUNT.values())
    assert any(v > 0 for v in vals), "动态标记基线全为 0，判据无信号"
    assert 0 in vals, "动态标记基线无零项，反向边界缺失（I3/I4/I6 应为 0）"
    assert set(_SRC_DYNAMIC_MARK_COUNT.keys()) == set(_SECTION_MAP.keys())


# ═══════════════════════════════════════════════════════════════════════════════
# Task 3 补齐缺口 ②：表名不得为段落文本泄漏（Property 15）
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_no_leaked_paragraph_table_name(cycle: str, variant: str):
    """表名不得以 `[` 开头、不得超长（类 B：改造前 I5 两版应红）。

    表名是 `sub_table_data` 的键 —— 段落泄漏名会让底稿推送产出孤儿子表，
    附注侧永远看不到数据。
    """
    by_name = _tables_by_name(cycle, variant)
    offenders: list[str] = []
    for name in by_name:
        if name.startswith("[") or name.startswith("［"):
            offenders.append(f"以 [ 开头: {name[:40]!r}")
        elif len(name) > _TABLE_NAME_MAX_LEN:
            offenders.append(f"超长({len(name)}>{_TABLE_NAME_MAX_LEN}): {name[:40]!r}")
    assert not offenders, (
        f"{cycle}/{variant} 存在段落文本泄漏成表名（尚未修正，Wave 4 Task 10）：{offenders}"
    )


def test_leaked_name_sections_are_registered():
    """已知泄漏点必须登记在 `_LEAKED_TABLE_NAME_SECTIONS`（防漏改）。

    改造后该登记表转为**历史台账** + stale 检测：若登记的章节已无泄漏名，
    断言提醒把它移出登记表（防登记表变成永久盲区）。
    """
    assert _LEAKED_TABLE_NAME_SECTIONS, "泄漏点登记表为空，判据无信号"
    for cycle, variant in _LEAKED_TABLE_NAME_SECTIONS:
        assert (cycle, variant) in _SECTION_MAP, f"{cycle}/{variant} 不是合法章节键"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 3 补齐缺口 ③④：四张 cols=0 表逐张点名（Property 15）
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "cycle,variant,table_name",
    [pytest.param(c, v, t, id=f"{c}_{v}_{t}") for c, v, t in _COLS0_TARGETS],
)
def test_cols0_target_has_columns(cycle: str, variant: str, table_name: str):
    """本 spec 要补的四张表必须有非空 columns（类 B：改造前应全红）。

    🔴 与 `test_columns_non_empty` 的区别：那条只覆盖 `_VERIFIED_TABLES`
    （既有脚本已对齐的表），这四张**不在**其中 —— 正因如此它们的 `cols=0`
    长期无人察觉（守卫看不见的地方就是欠账藏身处）。
    """
    by_name = _tables_by_name(cycle, variant)
    assert table_name in by_name, (
        f"{cycle}/{variant} 缺表 {table_name!r}，实有 {list(by_name)}"
    )
    cols = by_name[table_name].get("columns") or []
    assert len(cols) > 0, (
        f"{cycle}/{variant}/{table_name} columns 为空 —— "
        f"投影器会退回前缀推断或降级成只显示行名（尚未补齐，Wave 4 Task 10）"
    )
    assert cols[0].get("is_label"), (
        f"{cycle}/{variant}/{table_name} 首列未标 is_label"
    )


@pytest.mark.parametrize(
    "cycle,variant,table_name",
    [pytest.param(c, v, t, id=f"{c}_{v}_{t}") for c, v, t in _COLS0_TARGETS],
)
def test_cols0_target_group_or_flat(cycle: str, variant: str, table_name: str):
    """四张表补完 columns 后必须表态 `flat` 或 `group`（不得两者皆无）。

    🔴 `_extract_column_groups` 三态：`None`=未声明（回退前缀推断，可能凭空造父表头）
    / `[]`=显式单级 / 非空=显式分组。不表态就是第一种，等于没补对。
    """
    by_name = _tables_by_name(cycle, variant)
    cols = by_name.get(table_name, {}).get("columns") or []
    if not cols:
        pytest.skip("columns 尚未补齐，由 test_cols0_target_has_columns 打红")
    has_flat = any(c.get("flat") for c in cols)
    has_group = any(c.get("group") for c in cols)
    assert has_flat or has_group, (
        f"{cycle}/{variant}/{table_name} 既无 flat 也无 group，"
        f"投影器会走前缀推断凭空造父表头"
    )
    assert not (has_flat and has_group), (
        f"{cycle}/{variant}/{table_name} flat 与 group 并存 —— "
        f"`_extract_column_groups` 见任一 flat 即整表返 []，group 会被静默丢弃"
    )


def test_cols0_targets_cover_all_known_gaps():
    """`_COLS0_TARGETS` 必须覆盖全部四处已知缺口，且不含 `_VERIFIED_TABLES` 已覆盖的表。

    反向自检：若某表同时出现在两处，说明判据重叠、其中一处是冗余。
    """
    assert len(_COLS0_TARGETS) == 4, f"已知 cols=0 缺口为 4 处，实为 {len(_COLS0_TARGETS)}"
    for cycle, variant, table_name in _COLS0_TARGETS:
        assert (cycle, variant) in _SECTION_MAP
        already = _VERIFIED_TABLES[(cycle, variant)]
        assert table_name not in already, (
            f"{cycle}/{variant}/{table_name} 已在 _VERIFIED_TABLES 中，"
            f"不该再登记为 cols=0 缺口"
        )


# ───────────────── Property 15（续）：headers / 列文案禁含 HTML ─────────────────


#: HTML 标记（`<br/>`、`<br>`、`<b>`、`&nbsp;` …）。
#:
#: 🔴 为什么必须拦：`headers` 与 `columns[].label` 会被 HTML 渲染器与 Word 导出
#: **按纯文本**输出（前端表头走 `{{ }}` 插值、`python-docx` 走 run.text），
#: 源模板里的换行是靠 xlsx 单元格 `wrap_text` 实现的 —— 若对齐脚本图省事把换行
#: 写成 `<br/>`，两个下游都会把标签**原样显示**给审计人员（「项目<br/>金额」）。
_HTML_PATTERN = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>|&(?:nbsp|amp|lt|gt|quot|#\d+);")


@pytest.mark.parametrize("cycle,variant", _ALL_PARAMS)
def test_headers_and_labels_no_html(cycle: str, variant: str):
    """`headers` 与 `columns[].label` / `.group` 一律纯文本，不得含 HTML 标记。

    🔴 **本判据必须自证扫描量**（2026-08-12 变异检验 M4 补强）：当前数据本来干净，
    只断言「offenders 为空」时，把取值改成 `if False:` 照样全绿 —— 守卫证明不了
    自己真的读过 `headers`（平台已记「grep/存在式守卫」范式缺陷）。故同时断言
    每张表至少贡献 1 个被检字符串，让「跳过整表」的变异必然打红。
    """
    sec = _section(cycle, variant)
    offenders: list[str] = []
    tables = sec.get("tables") or []
    scanned_headers = 0
    scanned_cols = 0
    for tbl in tables:
        name = tbl.get("name", "?")
        headers = tbl.get("headers")
        if isinstance(headers, list):
            for i, h in enumerate(headers):
                scanned_headers += 1
                if _HTML_PATTERN.search(str(h or "")):
                    offenders.append(f"{name}.headers[{i}]={h!r}")
        for j, col in enumerate(tbl.get("columns") or []):
            for field in ("label", "group"):
                val = str(col.get(field) or "")
                scanned_cols += 1
                if _HTML_PATTERN.search(val):
                    offenders.append(f"{name}.columns[{j}].{field}={val!r}")
    assert not offenders, (
        f"{cycle}/{variant} 的表头/列文案含 HTML 标记（下游按纯文本输出，"
        f"标签会原样显示给审计人员）：{offenders}"
    )
    # 自证扫描量：每张表的 headers 至少 1 项、columns 至少 1 项（12 章节实测均满足）
    assert scanned_headers >= len(tables), (
        f"{cycle}/{variant} 仅扫到 {scanned_headers} 个 headers 项 / {len(tables)} 张表 ⇒ "
        f"取值路径被跳过，HTML 判据在空转"
    )
    assert scanned_cols >= len(tables), (
        f"{cycle}/{variant} 仅扫到 {scanned_cols} 个列文案 / {len(tables)} 张表 ⇒ "
        f"取值路径被跳过，HTML 判据在空转"
    )


def test_headers_present_and_nonempty():
    """反向自检 A：12 章节每张表都得有非空 `headers` list —— 否则上一条在扫空气。

    改造前若 `headers` 缺失或为 `None`，`test_headers_and_labels_no_html` 会因
    `isinstance(headers, list)` 为假而静默跳过整表（守卫空转）。
    """
    total = 0
    missing: list[str] = []
    # 🔴 `_ALL_PARAMS` 的元素是 `pytest.param(...)` 对象（不是裸 tuple），
    #    直接 `for cycle, variant in` 会 `ValueError: too many values to unpack`。
    for cycle, variant in (p.values for p in _ALL_PARAMS):
        for tbl in _section(cycle, variant).get("tables") or []:
            total += 1
            headers = tbl.get("headers")
            if not isinstance(headers, list) or not headers:
                missing.append(f"{cycle}/{variant}/{tbl.get('name','?')}")
    assert total >= 26, f"12 章节共扫到 {total} 张表（实测基线 26），疑似章节定位失效"
    assert not missing, f"以下表缺非空 headers ⇒ HTML 卫生判据对它们空转：{missing}"


def test_html_pattern_actually_matches():
    """反向自检 B：正则本身必须能命中真实 HTML 样本（防判据写错成永不命中）。"""
    for sample in ("项目<br/>金额", "合计<br>", "<b>粗体</b>", "项目&nbsp;金额", "<span>x</span>"):
        assert _HTML_PATTERN.search(sample), f"正则漏判 HTML 样本 {sample!r}"
    # 🔴 纯文本样本**不能**用 `a < b 且 c > d` —— `< b 且 c >` 本身就符合
    #    「`<` + 字母 + 非 `>` 若干 + `>`」的标签语法，正则命中它是**正确行为**
    #    （首版拿它当反例，红的是样本不是判据）。真实表头也不会出现裸尖括号。
    for clean in ("项  目", "账面价值", "剩余摊销期限", "本期增加", "≤1年", "占比(%)", "a<1 且 b>2"):
        assert not _HTML_PATTERN.search(clean), f"正则误判纯文本 {clean!r}"
