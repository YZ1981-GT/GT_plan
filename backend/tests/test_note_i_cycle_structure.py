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


# ═══════════════════════════════════════════════════════════════════════════════
# Property 18 / 19：I1 上市列集与类别真源 ↔ 源模板交叉锁死
#
# 🔴 **基线一律以 openpyxl 逐格实测为准，不照抄 spec 文本**（2026-08-12 实测）：
#   design.md 的 Property 19 写「`底稿目录!A9:A19`（12 类）」——
#   而 A9:A19 只有 **11** 个单元格、逐格读出的也是 11 个类别名，
#   `i1_asset_categories.I1_ASSET_CATEGORIES` 同样是 11 条。按「12 类」写断言
#   会把错值当基线锁死（平台已记的第三类假绿）。
#
# 源模板实证（`I1 无形资产、累计摊销及减值准备.xlsx`）：
#   `底稿目录!A8`  = 「无形资产类别设置（以下内容请根据实际情况修改）：」
#   `底稿目录!A9:A19` = 土地使用权 / 住房使用权 / 专利权 / 非专利技术 / 商标权 /
#                       著作权 / 特许经营权 / 软件 / 矿产权 / 数据资源 / 其他（11 个）
#   `底稿目录!A20` = 「……」（动态扩位）
#   `附注披露信息（上市公司）!A10:M10` = 「项目」+ 上述 11 类 + 「合计」= **13 列**
#   row10/row11 **无合并单元格** ⇒ 单级表头（不是两级）
# ═══════════════════════════════════════════════════════════════════════════════


#: 类别真源单元格区间（`底稿目录`）—— 起止行由源模板实证冻结
_I1_CATEGORY_SHEET = "底稿目录"
_I1_CATEGORY_FIRST_ROW = 9
_I1_CATEGORY_LAST_ROW = 19
#: 类别区上方的标题格（锚点有效性自检用）
_I1_CATEGORY_TITLE_CELL = "A8"
_I1_CATEGORY_TITLE_TEXT = "无形资产类别设置"
#: 类别区下方的动态扩位格
_I1_CATEGORY_EXPAND_CELL = "A20"

#: 上市披露主表表头行与列区间
_I1_LISTED_HEADER_ROW = 10
_I1_LISTED_LABEL_COL = 1   # A：「项目」
_I1_LISTED_TOTAL_COL = 13  # M：「合计」


def _i1_workbook():
    return openpyxl.load_workbook(_SRC_FILES["I1"], data_only=True)


def _i1_category_labels_from_source() -> list[str]:
    """openpyxl 直读 `底稿目录!A9:A19` 的类别名（去空白 + 去「其中：」前缀）。"""
    ws = _i1_workbook()[_I1_CATEGORY_SHEET]
    out: list[str] = []
    for row in range(_I1_CATEGORY_FIRST_ROW, _I1_CATEGORY_LAST_ROW + 1):
        raw = _norm(ws.cell(row=row, column=1).value)
        out.append(re.sub(r"^其中[:：]", "", raw))
    return out


def _load_i1_categories():
    """导入类别声明模块（延迟导入：避免拉起 DB 依赖）。"""
    from app.services.four_table import i1_asset_categories as mod

    return mod


# ─── Property 19：类别真源派生自源模板，且 source_ref 可回溯 ───────────────────


def test_i1_category_source_anchor_still_valid():
    """反向自检：类别区的标题格与扩位格必须仍在原处 —— 否则行区间已漂移。

    没有这条，`A9:A19` 换了位置时下面几条会静静地读到别的内容（读到空串也算「一致」）。
    """
    ws = _i1_workbook()[_I1_CATEGORY_SHEET]
    title = _norm(ws[_I1_CATEGORY_TITLE_CELL].value)
    assert _I1_CATEGORY_TITLE_TEXT in title, (
        f"{_I1_CATEGORY_SHEET}!{_I1_CATEGORY_TITLE_CELL} 已不含 "
        f"{_I1_CATEGORY_TITLE_TEXT!r}（实为 {title!r}）⇒ 类别区行号漂移，"
        f"_I1_CATEGORY_FIRST_ROW/_LAST_ROW 需重新实测"
    )
    expand = _norm(ws[_I1_CATEGORY_EXPAND_CELL].value)
    assert _DYNAMIC_MARK_RE.fullmatch(expand), (
        f"{_I1_CATEGORY_SHEET}!{_I1_CATEGORY_EXPAND_CELL} 应是动态扩位标记，"
        f"实为 {expand!r} ⇒ 类别区末行漂移"
    )
    labels = _i1_category_labels_from_source()
    assert all(labels), f"类别区有空格：{labels}"
    assert len(labels) == 11, (
        f"源模板 `底稿目录!A9:A19` 实测 {len(labels)} 个类别（冻结基线 11）。"
        f"🔴 spec design.md 写的「12 类」与源模板不符，以本条实测为准：{labels}"
    )


def test_i1_category_labels_match_source_template():
    """`I1_ASSET_CATEGORIES` 按 `seq` 排序后的 label 必须逐字等于源模板行序。

    🔴 用 `seq` 而不是声明顺序：声明顺序是**归类优先级**（`非专利技术` 必须先于
    `专利权`，后者是前者子串），`seq` 才是展示/行序。两者混用会让本条恒红或恒绿。
    """
    mod = _load_i1_categories()
    declared = [c.label for c in sorted(mod.I1_ASSET_CATEGORIES, key=lambda x: x.seq)]
    assert declared == _i1_category_labels_from_source(), (
        f"类别声明（按 seq）与源模板 `底稿目录!A9:A19` 不一致：\n"
        f"  声明 = {declared}\n  源表 = {_i1_category_labels_from_source()}"
    )


def test_i1_category_seq_is_dense_and_one_based():
    """`seq` 必须是 1..N 连续无空洞 —— 否则列序/行序会出现跳号或重叠。"""
    mod = _load_i1_categories()
    seqs = sorted(c.seq for c in mod.I1_ASSET_CATEGORIES)
    assert seqs == list(range(1, len(seqs) + 1)), f"seq 非 1..N 连续：{seqs}"


def test_i1_category_source_ref_not_stale():
    """stale 检测：每个类别的 `source_ref` 指向的单元格必须仍含该 label。

    源模板一改动即打红（对齐平台已有的 `test_note_expandable_rows` 范式）。
    """
    mod = _load_i1_categories()
    wb = _i1_workbook()
    offenders: list[str] = []
    checked = 0
    for cat in mod.I1_ASSET_CATEGORIES:
        assert cat.source_ref, f"类别 {cat.key} 缺 source_ref 证据"
        hit = False
        for ref in cat.source_ref:
            sheet, _, cell = str(ref).partition("!")
            if sheet not in wb.sheetnames:
                offenders.append(f"{cat.key}: sheet {sheet!r} 不存在")
                continue
            checked += 1
            val = re.sub(r"^其中[:：]", "", _norm(wb[sheet][cell].value))
            if _norm(cat.label) in val:
                hit = True
        if not hit:
            refs = [f"{r}={_norm(wb[r.split('!')[0]][r.split('!')[1]].value)!r}"
                    for r in cat.source_ref if r.split("!")[0] in wb.sheetnames]
            offenders.append(f"{cat.key}({cat.label}): 无一命中 —— {refs}")
    assert checked >= len(mod.I1_ASSET_CATEGORIES), (
        f"只校验了 {checked} 个 source_ref 单元格 / {len(mod.I1_ASSET_CATEGORIES)} 个类别 "
        f"⇒ 判据在空转"
    )
    assert not offenders, f"source_ref stale：{offenders}"


def test_i1_category_defs_payload_matches_declaration():
    """下发给前端的 `category_defs_payload()` 必须与声明同序同值（无第二份真源）。"""
    mod = _load_i1_categories()
    payload = mod.category_defs_payload()
    expected = [
        {"key": c.key, "label": c.label, "seq": c.seq}
        for c in sorted(mod.I1_ASSET_CATEGORIES, key=lambda x: x.seq)
    ]
    assert [
        {"key": p["key"], "label": p["label"], "seq": p["seq"]} for p in payload
    ] == expected, f"payload 与声明漂移：\n  payload={payload}\n  expected={expected}"


def test_i1_category_other_is_last_wide_fallback():
    """`其他` 必须是 seq 最大（列尾/行尾）且归类优先级最低（宽兜底放最后）。"""
    mod = _load_i1_categories()
    other = next(c for c in mod.I1_ASSET_CATEGORIES if c.key == mod.CATEGORY_OTHER)
    assert other.seq == max(c.seq for c in mod.I1_ASSET_CATEGORIES), "「其他」不在末位"
    assert other.priority == max(c.priority for c in mod.I1_ASSET_CATEGORIES), (
        "「其他」的 priority 不是最大 ⇒ 会抢在具体类别之前命中"
    )


# ─── Property 18：I1 上市披露主表列集 = 项目 + 11 类 + 合计 = 13 列 ─────────────


def test_i1_listed_header_is_13_columns():
    """`附注披露信息（上市公司）!A10:M10` 必须是 13 个非空列且第 14 列起为空。"""
    ws = _i1_workbook()[_SRC_DISCLOSURE_SHEETS[("I1", "listed")]]
    vals = [
        _norm(ws.cell(row=_I1_LISTED_HEADER_ROW, column=c).value)
        for c in range(1, _I1_LISTED_TOTAL_COL + 1)
    ]
    assert all(vals), f"A10:M10 有空列：{vals}"
    assert len(vals) == 13, f"列数应为 13，实为 {len(vals)}"
    # 反向自检：第 14 列必须为空（否则真实列数 >13，冻结基线过期）
    beyond = _norm(ws.cell(row=_I1_LISTED_HEADER_ROW, column=_I1_LISTED_TOTAL_COL + 1).value)
    assert not beyond, f"N10 非空（{beyond!r}）⇒ 实际列数 >13，基线需重新实测"


def test_i1_listed_header_middle_equals_category_labels():
    """B10:L10 逐格等于类别真源（按 seq 排序），A10=「项目」、M10=「合计」。

    这是 Property 18 的核心：披露主表列集**由类别真源派生**，不是另抄一份。
    """
    ws = _i1_workbook()[_SRC_DISCLOSURE_SHEETS[("I1", "listed")]]
    row = [
        _norm(ws.cell(row=_I1_LISTED_HEADER_ROW, column=c).value)
        for c in range(1, _I1_LISTED_TOTAL_COL + 1)
    ]
    assert row[0] == "项目", f"A10 应为「项目」，实为 {row[0]!r}"
    assert row[-1] == "合计", f"M10 应为「合计」，实为 {row[-1]!r}"
    mod = _load_i1_categories()
    declared = [c.label for c in sorted(mod.I1_ASSET_CATEGORIES, key=lambda x: x.seq)]
    assert row[1:-1] == declared, (
        f"B10:L10 与类别声明（按 seq）不一致：\n"
        f"  表头 = {row[1:-1]}\n  声明 = {declared}"
    )


def test_i1_listed_header_is_single_level():
    """表头行**无合并单元格** ⇒ 单级（flat），不得按两级 group 渲染。

    实测 row10/row11 相关合并为空。若源模板改成两级表头，本条会打红，
    提醒同步改前端 `buildI1ListedColumns` 的表态与附注模板的 `_column_groups`。
    """
    ws = _i1_workbook()[_SRC_DISCLOSURE_SHEETS[("I1", "listed")]]
    merged = [
        str(rng)
        for rng in ws.merged_cells.ranges
        if rng.min_row <= _I1_LISTED_HEADER_ROW + 1 and rng.max_row >= _I1_LISTED_HEADER_ROW
    ]
    assert not merged, (
        f"表头行出现合并单元格 {merged} ⇒ 源模板已改为两级表头，"
        f"前端列表态与附注 _column_groups 需同步改造"
    )


def test_i1_listed_layer_titles_and_expand_marks_align():
    """四个层标题 + 三个动态扩位的相对位置必须成立（扩位在层内、不越层）。

    实证：层标题 A11/A24/A35/A46（一、账面原值 / 二、累计摊销 / 三、减值准备 / 四、账面价值），
    扩位 A18/A29/A40 —— 各落在前三层内部，第四层（账面价值，派生层）无扩位。
    """
    ws = _i1_workbook()[_SRC_DISCLOSURE_SHEETS[("I1", "listed")]]
    layer_rows: list[int] = []
    mark_rows: list[int] = []
    for row in range(_I1_LISTED_HEADER_ROW, ws.max_row + 1):
        text = _norm(ws.cell(row=row, column=1).value)
        if not text:
            continue
        if _DYNAMIC_MARK_RE.fullmatch(text):
            mark_rows.append(row)
        elif re.match(r"^[一二三四五六]、", text):
            layer_rows.append(row)
    assert len(layer_rows) == 4, f"应有 4 个层标题，实测 {layer_rows}"
    assert len(mark_rows) == _SRC_DYNAMIC_MARK_COUNT[("I1", "listed")], (
        f"动态扩位数与冻结基线不一致：实测 {mark_rows}，"
        f"基线 {_SRC_DYNAMIC_MARK_COUNT[('I1', 'listed')]}"
    )
    # 每个扩位都必须落在某层标题之后、下一层标题之前
    for mark in mark_rows:
        enclosing = [r for r in layer_rows if r < mark]
        assert enclosing, f"扩位 A{mark} 出现在第一个层标题之前"
        nxt = [r for r in layer_rows if r > mark]
        assert nxt, f"扩位 A{mark} 落在最后一层之后（第四层是派生层，不该有扩位）"
    # 第四层（账面价值，由前三层推导）不得有扩位
    assert all(m < layer_rows[3] for m in mark_rows), (
        f"第四层（A{layer_rows[3]} 账面价值）内出现扩位 {[m for m in mark_rows if m > layer_rows[3]]}"
        f" —— 该层是派生层，不应可扩"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Requirement 10 / Task 19：源模板缺陷登记的 stale 检测与处置落实
#
# 判据设计要点：
# - **stale 检测**：每条登记的 `source_ref` 指向的单元格必须仍含 `expect_token`
#   （openpyxl 直读）。源模板一改动（缺陷被上游修掉 / 行列漂移）即打红，
#   提醒重新核对而不是继续按旧结论走。
# - **不得反改源 xlsx**（AC 10.7）：守卫只读不写；另有断言钉死「缺陷仍在源模板里」，
#   若有人偷偷改了源模板来「消除」缺陷，本组会红。
# - **处置落实**：`skip` 类必须在 `wp_code_overrides.json` 里真有 `skip` 登记
#   （否则登记表写了 skip 而链路没排除 = 纯注释承诺）。
# ═══════════════════════════════════════════════════════════════════════════════


def _load_defects():
    from app.services.four_table import i_cycle_source_defects as mod

    return mod


def _src_workbook(file_name: str, data_only: bool = False):
    """按登记里的文件名打开源模板。坏公式需 data_only=False 才看得到。"""
    return openpyxl.load_workbook(_SRC_DIR / file_name, data_only=data_only)


def _parse_source_ref(ref: str) -> tuple[str, str, str]:
    """``"<文件>!<sheet>!<单元格>"`` → 三元组。"""
    parts = str(ref).split("!")
    assert len(parts) == 3, f"source_ref 格式应为 `文件!sheet!单元格`，实为 {ref!r}"
    return parts[0], parts[1], parts[2]


def test_source_defects_registry_shape():
    """登记表结构自检：6 条、id 唯一、循环合法、处置合法、字段非空。"""
    mod = _load_defects()
    defects = mod.I_CYCLE_SOURCE_DEFECTS
    assert len(defects) == 6, (
        f"Requirement 10 立项了 6 处源模板缺陷（AC 10.1~10.6），实为 {len(defects)} 条"
    )
    ids = [d.defect_id for d in defects]
    assert len(set(ids)) == len(ids), f"defect_id 重复：{ids}"
    for d in defects:
        assert d.cycle in _SRC_FILES, f"{d.defect_id} 的 cycle={d.cycle!r} 非 I1~I6"
        assert d.disposition in mod.DISPOSITION_LABELS, (
            f"{d.defect_id} 的 disposition={d.disposition!r} 不在 {list(mod.DISPOSITION_LABELS)}"
        )
        assert d.title.strip(), f"{d.defect_id} 缺 title"
        assert d.evidence.strip(), f"{d.defect_id} 缺 evidence（实测证据）"
        assert d.rationale.strip(), f"{d.defect_id} 缺 rationale（处置理由）"
        assert d.source_ref, f"{d.defect_id} 缺 source_ref"


def test_source_defects_cover_all_acceptance_criteria():
    """六条 AC 逐条有对应登记（按 defect_id 点名，防漏登或改名后失联）。"""
    mod = _load_defects()
    expected = {
        "i1_adjudication_tab_missing_suffix",       # AC 10.1
        "i2_listed_ref_error_continuation_table",   # AC 10.2
        "i1_listed_disposal_typo_in_formula",       # AC 10.3
        "i6_index_cross_workbook_by_design",        # AC 10.4
        "i5_index_sequence_number_missing",         # AC 10.5
        "i3_hidden_sheet_stale_market_return",      # AC 10.6
    }
    got = {d.defect_id for d in mod.I_CYCLE_SOURCE_DEFECTS}
    assert got == expected, f"登记项与 AC 不一一对应：缺 {expected - got}，多 {got - expected}"


def test_source_defects_source_ref_resolvable():
    """反向自检：每条 `source_ref` 的文件与 sheet 必须真实存在（否则 stale 检测在空转）。"""
    mod = _load_defects()
    checked = 0
    for d in mod.I_CYCLE_SOURCE_DEFECTS:
        for ref in d.source_ref:
            file_name, sheet, cell = _parse_source_ref(ref)
            path = _SRC_DIR / file_name
            assert path.exists(), f"{d.defect_id}: 源文件不存在 {file_name}"
            wb = _src_workbook(file_name)
            assert sheet in wb.sheetnames, (
                f"{d.defect_id}: sheet {sheet!r} 不在 {file_name} 里（现有 {wb.sheetnames}）"
            )
            # 单元格可寻址（越界会抛）
            wb[sheet][cell]
            checked += 1
    assert checked >= len(mod.I_CYCLE_SOURCE_DEFECTS), (
        f"只校验了 {checked} 个 source_ref ⇒ 判据在空转"
    )


def test_source_defects_expect_token_not_stale():
    """stale 检测：带 `expect_token` 的登记，其单元格必须仍含该文本。

    🔴 打红不代表代码有 bug —— 而是**源模板变了**（缺陷被上游修掉 / 行列漂移），
    需重新核对该条登记的处置是否还成立，而不是删掉断言。
    """
    mod = _load_defects()
    offenders: list[str] = []
    checked = 0
    for d in mod.I_CYCLE_SOURCE_DEFECTS:
        if not d.expect_token:
            continue
        hit = False
        for ref in d.source_ref:
            file_name, sheet, cell = _parse_source_ref(ref)
            val = str(_src_workbook(file_name)[sheet][cell].value or "")
            checked += 1
            if d.expect_token in val:
                hit = True
        if not hit:
            offenders.append(f"{d.defect_id}: 期望 {d.expect_token!r} 未在 {list(d.source_ref)} 命中")
    assert checked >= 3, f"带 expect_token 的登记只校验了 {checked} 格 ⇒ 判据在空转"
    assert not offenders, f"source_ref stale：{offenders}"


def test_i1_adjudication_tab_name_missing_suffix_still_holds():
    """AC 10.1：I1 的审定表 tab 名仍缺 `-1`，其余五个循环仍带 `-1`。"""
    got: dict[str, list[str]] = {}
    for cycle, path in _SRC_FILES.items():
        got[cycle] = [s for s in openpyxl.load_workbook(path).sheetnames if "审定表" in s]
    assert got["I1"] == ["审定表I1"], f"I1 审定表 tab 名已变：{got['I1']}"
    for cycle in ("I2", "I3", "I4", "I5", "I6"):
        assert got[cycle] == [f"审定表{cycle}-1"], f"{cycle} 审定表 tab 名已变：{got[cycle]}"


def test_i2_listed_ref_error_cell_count_frozen():
    """AC 10.2：I2 上市披露续表区的 `#REF!` 格数冻结为 **20**（非 spec 写的 15）。"""
    wb = _src_workbook("I2 开发支出.xlsx")
    sheet = next(s for s in wb.sheetnames if "披露" in s and "上市" in s)
    ws = wb[sheet]
    coords = [
        c.coordinate
        for row in ws.iter_rows()
        for c in row
        if isinstance(c.value, str) and "#REF!" in c.value
    ]
    assert len(coords) == 20, (
        f"`#REF!` 实测 {len(coords)} 格（冻结基线 20）：{coords}。"
        f"🔴 spec AC 10.2 与 tasks.md 写「15 格」与源模板不符，以本条实测为准"
    )
    rows = sorted({int(re.sub(r"[A-Z]", "", x)) for x in coords})
    cols = sorted({re.sub(r"[0-9]", "", x) for x in coords})
    assert rows == [35, 36, 37, 38, 39], f"行范围漂移：{rows}"
    assert cols == ["A", "B", "C", "D"], f"列范围漂移：{cols}"
    # 续表语义锚点（按意图实现的依据）
    assert _norm(ws["A33"].value) == "续："
    assert _norm(ws["A34"].value) == "项目"
    assert _norm(ws["A40"].value) == "合计"


def test_i1_listed_disposal_typo_scope_frozen():
    """AC 10.3：I1 上市「（1）处置」行的笔误范围冻结 —— B/C 正确、D~L 共 9 格误写「购置」。

    同时钉死 row14（「（1）购置」）的 11 格用「购置」是**正确的**，
    防后续会话把它一起「修正」掉。
    """
    wb = _src_workbook("I1 无形资产、累计摊销及减值准备.xlsx")
    ws = wb[_SRC_DISCLOSURE_SHEETS[("I1", "listed")]]
    assert _norm(ws["A20"].value) == "（1）处置", f"A20 语义已变：{ws['A20'].value!r}"
    assert _norm(ws["A19"].value) == "3.本期减少金额"
    assert _norm(ws["A14"].value) == "（1）购置", f"A14 语义已变：{ws['A14'].value!r}"
    assert _norm(ws["A13"].value) == "2.本期增加金额"

    def judge_of(row: int, col: int) -> str | None:
        v = ws.cell(row=row, column=col).value
        if not isinstance(v, str):
            return None
        m = re.search(r'="([^"]+)"', v)
        return m.group(1) if m else None

    row20 = {openpyxl.utils.get_column_letter(c): judge_of(20, c) for c in range(2, 13)}
    correct = [k for k, v in row20.items() if v == "处置"]
    typo = [k for k, v in row20.items() if v == "购置"]
    assert correct == ["B", "C"], f"row20 用「处置」的列已变：{correct}"
    assert typo == ["D", "E", "F", "G", "H", "I", "J", "K", "L"], (
        f"row20 误写「购置」的列已变：{typo}（冻结基线 D~L 共 9 格）"
    )
    # row14 全用「购置」是正确的，不得被一起改
    row14 = {openpyxl.utils.get_column_letter(c): judge_of(14, c) for c in range(2, 13)}
    assert all(v == "购置" for v in row14.values()), (
        f"row14（本期增加·购置）的判定值被改动：{row14} —— 那 11 格本来就该是「购置」"
    )


def test_i6_index_cross_workbook_hint_still_present():
    """AC 10.4：I6 目录第 7~14 项仍指向 `I2-4`~`I2-11`，且 E10 的提示原文仍在。"""
    wb = _src_workbook("I6 研发费用.xlsx")
    ws = wb[next(s for s in wb.sheetnames if "目录" in s)]
    idx = [_norm(ws.cell(row=r, column=4).value) for r in range(10, 18)]
    assert idx == [f"I2-{n}" for n in range(4, 12)], (
        f"I6 目录第 7~14 项索引号已变：{idx}（冻结基线 I2-4~I2-11）"
    )
    hint = _norm(ws["E10"].value)
    assert "该部分底稿模板在开发支出底稿中" in hint, (
        f"E10 的跨 workbook 提示原文丢失（实为 {hint[:60]!r}）⇒ "
        f"「有意设计」的证据没了，需重新判定是否仍不该当笔误改"
    )


def test_i5_index_sequence_gap_frozen():
    """AC 10.5：I5 目录 7 行内容 / 6 个序号，缺口恰在 `B4`。"""
    wb = _src_workbook("I5 其他非流动资产.xlsx")
    ws = wb[next(s for s in wb.sheetnames if "目录" in s)]
    content_rows = [
        r for r in range(4, 12)
        if _norm(ws.cell(row=r, column=3).value)
        and _norm(ws.cell(row=r, column=3).value) != "内容"
    ]
    seq_rows = [r for r in content_rows if _norm(ws.cell(row=r, column=2).value)]
    assert len(content_rows) == 7, f"内容行数已变：{content_rows}"
    assert len(seq_rows) == 6, f"有序号的行数已变：{seq_rows}"
    assert set(content_rows) - set(seq_rows) == {4}, (
        f"序号缺口不在 B4：缺 {sorted(set(content_rows) - set(seq_rows))}"
    )
    assert _norm(ws["D4"].value) == "I5A", "B4 缺序号的那行索引号应为 I5A"


def test_i3_hidden_sheet_registered_skip():
    """AC 10.6：I3 的 hidden sheet 仍在，且**已在 `wp_code_overrides.json` 标 skip**。

    🔴 「登记表写了 disposition=skip」不等于链路真的排除了它 ——
    分类链路只认 `_WP_CODE_OVERRIDE.get(sheet_name) == "skip"`（不读 `sheet_state`，
    `GT_Custom` 是 `wp_classification_service` 里的硬编码特例）。故必须两侧都断言。
    """
    mod = _load_defects()
    defect = mod.defect_by_id("i3_hidden_sheet_stale_market_return")
    assert defect is not None and defect.disposition == "skip"

    wb = _src_workbook("I3 商誉.xlsx")
    hidden = [s for s in wb.sheetnames if wb[s].sheet_state != "visible"]
    assert "市场平均收益率2017" in hidden, f"I3 的 hidden sheet 已变：{hidden}"

    from app.services.wp_code_override_loader import load_wp_code_overrides

    overrides = load_wp_code_overrides()
    assert overrides.get("市场平均收益率2017") == "skip", (
        "「市场平均收益率2017」未在 wp_code_overrides.json 标 skip ⇒ "
        "它会被分类成 `H-辅助说明` 底稿 sheet 暴露给审计人员"
        "（库侧实测过：workpaper_sheet_classification 里确有该行）"
    )


def test_source_defects_skip_dispositions_all_wired():
    """所有 `disposition == 'skip'` 的登记都必须在 overrides 里真有 skip（防纯注释承诺）。"""
    from app.services.wp_code_override_loader import load_wp_code_overrides

    mod = _load_defects()
    overrides = load_wp_code_overrides()
    skips = [d for d in mod.I_CYCLE_SOURCE_DEFECTS if d.disposition == "skip"]
    assert skips, "反向自检：无 skip 类登记 ⇒ 本条在空转"
    offenders: list[str] = []
    for d in skips:
        # skip 类的 source_ref 第一段的 sheet 名即待 skip 的 sheet
        _, sheet, _ = _parse_source_ref(d.source_ref[0])
        if overrides.get(sheet) != "skip":
            offenders.append(f"{d.defect_id}: sheet {sheet!r} 在 overrides 里是 {overrides.get(sheet)!r}")
    assert not offenders, f"登记为 skip 但链路未排除：{offenders}"


def test_source_defects_payload_projection():
    """下发投影字段齐备且不外泄 stale 检测细节（`expect_token` / `evidence` 不出现）。"""
    mod = _load_defects()
    payload = mod.defects_payload()
    assert len(payload) == len(mod.I_CYCLE_SOURCE_DEFECTS)
    for item in payload:
        assert set(item) == {
            "defect_id", "cycle", "title", "disposition", "disposition_label", "source_ref",
        }, f"投影字段集漂移：{sorted(item)}"
        assert item["disposition_label"] == mod.DISPOSITION_LABELS[item["disposition"]]


# ─── AC 10.7：源 xlsx 不得被反改（md5 冻结） ──────────────────────────────────


#: I 循环六份源模板的 md5 冻结基线（2026-08-12 实测）。
#:
#: 🔴 这是 AC 10.7「登记 + 守卫钉死，**不得反改源 xlsx**」的最强判据：
#: 前面几条守卫只钉「某个缺陷仍在」，改坏别处照样绿；md5 把整份文件钉死。
#:
#: 打红时的正确处理 = **先确认改动来源**：
#: - 若是致同下发了新版模板 ⇒ 逐条复核 `I_CYCLE_SOURCE_DEFECTS` 的处置是否仍成立，
#:   再更新本基线（连同 evidence 一起更新）
#: - 若是有人为了「修笔误」直接改了 xlsx ⇒ **回滚**（会让平台与事务所模板分叉，
#:   且 `wp_template_init_service` 生成底稿时直接复制它）
_SRC_XLSX_MD5: dict[str, str] = {
    "I1 无形资产、累计摊销及减值准备.xlsx": "329be34a3300d4795fef7ad58c4d43e6",
    "I2 开发支出.xlsx": "c656c764fa2b0ba1e84f050ad4e02985",
    "I3 商誉.xlsx": "937daf9c1f7df82b3d2aba1edc505afc",
    "I4 长期待摊费用.xlsx": "471cc8cd873f42ebbfa4913034762618",
    "I5 其他非流动资产.xlsx": "c88837d82ea2cb8136f92fbbb01cf21a",
    "I6 研发费用.xlsx": "ba37838369729052e4a03bf551a59662",
}


def test_source_xlsx_md5_frozen():
    """AC 10.7：六份源模板逐字节冻结（禁反改源 xlsx）。"""
    import hashlib

    offenders: list[str] = []
    for name, expect in _SRC_XLSX_MD5.items():
        path = _SRC_DIR / name
        assert path.exists(), f"源模板缺失：{name}"
        got = hashlib.md5(path.read_bytes()).hexdigest()
        if got != expect:
            offenders.append(f"{name}: {got} != {expect}")
    assert not offenders, (
        f"源模板被改动：{offenders}\n"
        f"🔴 AC 10.7 明令「登记 + 守卫钉死，不得反改源 xlsx」。"
        f"若是致同下发新版，请逐条复核 I_CYCLE_SOURCE_DEFECTS 的处置后再更新本基线"
    )


def test_source_xlsx_md5_baseline_covers_all_six():
    """反向自检：md5 基线必须覆盖 `_SRC_FILES` 全部六份（漏一份就有缺口）。"""
    assert set(_SRC_XLSX_MD5) == {p.name for p in _SRC_FILES.values()}, (
        f"md5 基线与 _SRC_FILES 不一致：\n"
        f"  基线 = {sorted(_SRC_XLSX_MD5)}\n"
        f"  实际 = {sorted(p.name for p in _SRC_FILES.values())}"
    )


def test_hidden_sheets_skipped_by_full_name():
    """AC 10.6 补强：hidden sheet 一律按**完整 sheet 名**标 skip（按尾码会误杀）。

    🔴 反例：若用 `endswith('2017')` 之类的尾码规则，会连带误杀其它循环里以年份
    结尾的正常 sheet；`GT_Custom` 同理不能按 `startswith('GT')` 匹配。
    """
    from app.services.wp_code_override_loader import load_wp_code_overrides

    overrides = load_wp_code_overrides()
    hidden_names: set[str] = set()
    for name, path in _SRC_FILES.items():
        wb = openpyxl.load_workbook(path)
        for sheet in wb.sheetnames:
            if wb[sheet].sheet_state != "visible":
                hidden_names.add(sheet)
    assert hidden_names == {"GT_Custom", "市场平均收益率2017"}, (
        f"I 循环 hidden sheet 集合已变：{sorted(hidden_names)}"
    )
    for sheet in sorted(hidden_names):
        assert overrides.get(sheet) == "skip", (
            f"hidden sheet {sheet!r} 未按完整名标 skip（实为 {overrides.get(sheet)!r}）"
        )
        # 完整名而非尾码：确认 overrides 里就是这个整串键
        assert sheet in overrides, f"{sheet!r} 不是 overrides 的整串键 ⇒ 可能用了尾码规则"


# ═══════════════════════════════════════════════════════════════════════════════
# Property 15（补强）：对**生成脚本的常量**断言表名形态
#
# 🔴 **2026-08-12 变异检验 P15 判 GREEN 抓出的判据缺陷**：
# 把 `fix_note_i_cycle_structure._I5_TABLE2_NAME` 从 `"合同取得成本"` 改回 90 字符的
# 泄漏名 `_I5_TABLE2_LEAKED_NAME`，**全组守卫无一条打红**。两个原因叠加：
#
# 1. 既有的「表名不得以 `[` 开头 / 长度 > 30」判据读的是**模板 JSON**
#    （`note_template_*.json`）。改脚本常量不重跑脚本 ⇒ JSON 不变 ⇒ 判据看不到。
# 2. `--check` 判据（`test_check_passes`）比对的是「脚本期望 vs JSON 实际」，
#    而两侧**都由同一个 `_I5_TABLE2_NAME` 常量推导** —— 改了常量两边一起变、
#    仍然自洽 ⇒ `--check` 结构上无法发现「脚本的期望值本身错了」。
#
# 这是「自洽性判据」的固有盲区：它只能保证两侧一致，不能保证两侧都对。
# 补法 = 直接对脚本里的**目标表名常量**断言形态（不经 JSON、不经 --check）。
# ═══════════════════════════════════════════════════════════════════════════════


#: 生成脚本里「最终表名」常量的名字 → 该表名必须满足的形态约束
#:
#: 只登记**正名过的**表（源模板里表名被 docx 指引段落污染、脚本负责正名的那些）。
#: 值 = (最大长度, 禁止的前缀元组)
_FIX_TABLE_NAME_CONSTS: dict[str, tuple[int, tuple[str, ...]]] = {
    "_I5_TABLE2_NAME": (_TABLE_NAME_MAX_LEN, ("[", "［")),
}


def test_fix_script_table_name_constants_are_not_paragraphs():
    """生成脚本的目标表名常量必须是**短表名**，不得是段落文本。

    🔴 与「模板 JSON 的表名」那条是**两个独立层级**：这条钉脚本的期望值，
    那条钉数据的实际值。少了这条，改坏脚本常量后 `--check` 因两侧同源而仍自洽。
    """
    mod = FIX
    offenders: list[str] = []
    checked = 0
    for const_name, (max_len, bad_prefixes) in _FIX_TABLE_NAME_CONSTS.items():
        assert hasattr(mod, const_name), (
            f"生成脚本缺常量 {const_name} ⇒ 锚点失效，本判据在空转"
        )
        value = str(getattr(mod, const_name) or "")
        checked += 1
        if not value:
            offenders.append(f"{const_name} 为空")
            continue
        if len(value) > max_len:
            offenders.append(f"{const_name} 长度 {len(value)} > {max_len}：{value[:50]!r}…")
        for prefix in bad_prefixes:
            if value.startswith(prefix):
                offenders.append(f"{const_name} 以 {prefix!r} 开头：{value[:50]!r}…")
        # 段落特征：含句读符号的多半是指引文本而非表名
        if any(ch in value for ch in "，。；：、"):
            offenders.append(f"{const_name} 含句读符号（疑似段落文本）：{value[:50]!r}…")
    assert checked == len(_FIX_TABLE_NAME_CONSTS), f"只校验了 {checked} 个常量"
    assert not offenders, f"生成脚本的表名常量形态异常：{offenders}"


def test_fix_script_leaked_name_only_used_as_alias():
    """泄漏名常量只能当 `aliases`（定位旧表用），**不得**被当成最终表名。

    反向自检：脚本里必须**同时**存在「泄漏名常量」与「正名后的表名常量」，
    且两者不相等 —— 若有人把正名常量直接赋成泄漏名，本条打红。
    """
    mod = FIX
    assert hasattr(mod, "_I5_TABLE2_LEAKED_NAME"), "缺泄漏名常量 ⇒ 无法做本判据"
    leaked = str(mod._I5_TABLE2_LEAKED_NAME)
    final = str(mod._I5_TABLE2_NAME)
    assert len(leaked) > _TABLE_NAME_MAX_LEN, (
        f"泄漏名常量长度 {len(leaked)} 不像段落文本 ⇒ 锚点可能已失效：{leaked[:60]!r}"
    )
    assert final != leaked, (
        "最终表名被赋成了泄漏名 ⇒ 正名失效，任何底稿推送都会产出孤儿子表"
        f"（表名是 sub_table_data 的键）：{final[:60]!r}"
    )
    assert final in leaked or "合同取得成本" in final, (
        f"最终表名与泄漏名语义无关联（{final!r}）⇒ 正名结果疑似写错对象"
    )


def test_fix_script_table_names_match_template_json():
    """脚本常量 ↔ 模板 JSON 双向一致（把两个层级钉在一起）。

    有了这条，改脚本常量而不重跑脚本 ⇒ 与 JSON 不一致 ⇒ 打红；
    重跑了脚本 ⇒ JSON 变成段落名 ⇒ 被既有的「表名形态」判据打红。两条路都堵死。
    """
    mod = FIX
    final = str(mod._I5_TABLE2_NAME)
    for variant in ("listed", "soe"):
        sec = _section("I5", variant)
        names = [t.get("name") for t in sec.get("tables") or []]
        assert final in names, (
            f"脚本常量 _I5_TABLE2_NAME={final!r} 不在模板 JSON 的 I5/{variant} 表名集里"
            f"（实际 {names}）⇒ 脚本与数据脱钩，需重跑 fix_note_i_cycle_structure.py --apply"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 43：**行维度**第三边（源 xlsx 首列 ↔ 附注模板 rows）
#
# 🔴🔴 为什么必须补这一条（2026-08-15 三向实测抓出真错）：本文件此前的三向比对
# （Property 16）只比**列**（源表头 ↔ 模板 headers ↔ 载荷 columns），
# `_SRC_DYNAMIC_MARK_COUNT`（Property 21）只数**源侧**扩位、从不看模板与前端消费侧。
# 于是下面这处 38 行里的 2 行错**同时逃过全部 38 张列契约 + 12 条扩位基线**：
#
#   源模板 `附注披露信息（上市公司）!A43:A44` = 「（2）失效且终止确认的部分」/「（3）其他减少」
#   改造前模板 JSON 第 33/34 行 = 「（2）其他减少」/「……」
#   改造前前端 `I1_LISTED_MOVEMENT_ROWS` 第 33/34 行 = 同上（同批生成的同一处错）
#
# ⇒ 减值准备减少段**丢了一个真实披露项、并凭空多出第 4 个可扩位**。两侧同错，
# 故任何「模板 ↔ 载荷」自洽型判据都放行（memory 已记「自洽性判据只能保证两侧一致，
# 不能保证两侧都对」）—— 只有拿源 xlsx 当第三边才抓得到。
# 国企侧同表更严重：48 行 / 10 个类别（缺「其他」、「矿产权」被拆成「采矿权+探矿权」、
# 「特许经营权」写成「特许权」、首类别是「软件」而源模板是「土地使用权」）。
#
# 判据范围**只覆盖 I1 两版**，理由见 `_ROW_SKELETON_NOT_ASSERTED`（其余 10 对的
# 「源侧扩位数 ↔ 模板 expandable 数」关系实测**不成立**，把它当不变量断言会锁死错值）。
# ═══════════════════════════════════════════════════════════════════════════════

#: 行骨架经源模板逐格实证、可做逐行断言的表。值 = `(表名, 源 sheet 首列行区间[含端点])`
_ROW_SKELETON_ASSERTED: dict[tuple[str, str], tuple[str, int, int]] = {
    ("I1", "listed"): ("无形资产情况", 11, 48),  # 四层变动行 38 行（类别作列）
    ("I1", "soe"): ("无形资产情况", 8, 59),      # 四层 × (层标题 + 11 类别 + 扩位) = 52 行
}

#: 其余 10 个 (循环, 变体) **不做**行骨架断言的实证理由（2026-08-15 逐对实测）。
#: 🔴 这不是偷懒白名单，而是「源 xlsx 披露 sheet 的行 ↔ 附注模板的行」本就不是 1:1 的
#: 实证结论：源侧是底稿录入表（常按列转置、含表头/说明/多张子表混排），
#: 附注侧是披露表（按 docx 要求组织、可有源 xlsx 没有的独立披露表）。
#: 把不成立的关系写成断言 = 锁死错值（memory 已记的假绿第③源）。
_ROW_SKELETON_NOT_ASSERTED: dict[tuple[str, str], str] = {
    ("I2", "listed"): "源侧 2 处扩位（A15 按费用性质 / A27 课题）落在**动态行表**上，"
                      "模板 rows 为空骨架由推送生成 ⇒ 模板 expandable=0 是正确形态",
    ("I2", "soe"): "源 A13「开发支出课题」扩位同样落在动态行表上，"
                   "模板 rows 为空骨架、由底稿推送生成 ⇒ 模板 expandable=0 是正确形态",
    ("I3", "listed"): "源侧 0 处扩位而模板有 2 处（商誉账面原值 / 商誉减值准备按资产组分项）"
                      "—— 附注 docx 要求按资产组逐项披露，底稿 xlsx 未留标记，模板多出是正确的",
    ("I3", "soe"): "源侧 0 处扩位、模板 expandable 也 0 处，扩位维度无信号；"
                   "两张表（商誉/商誉减值准备）的列结构已由 test_i3_soe_tables_are_flat 覆盖",
    ("I4", "listed"): "源侧 0 处扩位、模板 0 处，扩位维度无信号；源披露 sheet 的行是"
                      "「按项目逐行」的动态区（源模板只给示例行），列结构已由"
                      "test_i4_listed_two_level_headers_from_source 三向覆盖",
    ("I4", "soe"): "同上市侧（源侧 0 / 模板 0），源披露 sheet 行为动态项目区，"
                   "列结构由 _VERIFIED_TABLES 的两级表头判据覆盖",
    ("I5", "listed"): "源侧 1 处扩位（A18 其他非流动资产项目）落在动态项目行表，模板 expandable=0",
    ("I5", "soe"): "源 A17「其他非流动资产项目」扩位同样落在动态项目行表上，"
                   "模板 expandable=0；该章节另有段落泄漏表名的专项判据覆盖",
    ("I6", "listed"): "源侧 0 处而模板 1 处（研发费用按费用性质动态行），附注侧需要可扩位",
    ("I6", "soe"): "源侧 0 处扩位、模板 0 处；国企版研发费用表是固定三列"
                   "（项目/本期发生额/上期发生额），行按费用性质动态生成，"
                   "列结构已由 test_i6_columns_are_flat + test_i6_soe_table_name_matches_source 覆盖",
}


def _src_col_a(cycle: str, variant: str, r1: int, r2: int) -> list[str]:
    """openpyxl 直读源披露 sheet 首列 `[r1, r2]` 区间（去空白归一）。"""
    wb = openpyxl.load_workbook(_SRC_FILES[cycle], data_only=True)
    ws = wb[_SRC_DISCLOSURE_SHEETS[(cycle, variant)]]
    return [_norm(ws.cell(row=r, column=1).value) for r in range(r1, r2 + 1)]


def _template_table(cycle: str, variant: str, table_name: str) -> dict:
    sec = _section(cycle, variant)
    hit = [t for t in (sec.get("tables") or []) if str(t.get("name", "")) == table_name]
    assert len(hit) == 1, (
        f"{cycle}/{variant} 期望恰好一张名为 {table_name!r} 的表，实测 {len(hit)} 张"
    )
    return hit[0]


@pytest.mark.parametrize(
    "cycle,variant", sorted(_ROW_SKELETON_ASSERTED.keys())
)
def test_row_skeleton_matches_source_column_a(cycle: str, variant: str):
    """模板 rows 的 label 序列必须逐行等于源 xlsx 首列（Property 43 主判据）。"""
    table_name, r1, r2 = _ROW_SKELETON_ASSERTED[(cycle, variant)]
    src = _src_col_a(cycle, variant, r1, r2)
    tbl = _template_table(cycle, variant, table_name)
    rows = [_norm(r.get("label")) for r in (tbl.get("rows") or []) if isinstance(r, dict)]
    assert len(rows) == len(src), (
        f"{cycle}/{variant} {table_name} 行数 {len(rows)} != 源模板 "
        f"{_SRC_DISCLOSURE_SHEETS[(cycle, variant)]}!A{r1}:A{r2} 的 {len(src)} 行；"
        f"重跑 fix_note_i_cycle_structure.py --apply 可修"
    )
    bad = [
        f"第 {i} 行：模板「{t}」≠ 源模板 A{r1 + i}「{s}」"
        for i, (s, t) in enumerate(zip(src, rows))
        if s != t
    ]
    assert not bad, f"{cycle}/{variant} {table_name} 行标签与源模板不符：{bad}"


@pytest.mark.parametrize(
    "cycle,variant", sorted(_ROW_SKELETON_ASSERTED.keys())
)
def test_row_skeleton_expandable_count_matches_source(cycle: str, variant: str):
    """模板 `expandable` 行数必须等于源模板首列 `……` 标记数（Property 43 扩位判据）。

    这是把 `_SRC_DYNAMIC_MARK_COUNT`（只锁源侧）延伸到**消费侧**的一条边 ——
    改造前 I1 上市源侧 3 处、模板侧 4 处，旧判据结构上看不见这个差。
    """
    table_name, _r1, _r2 = _ROW_SKELETON_ASSERTED[(cycle, variant)]
    tbl = _template_table(cycle, variant, table_name)
    actual = sum(
        1
        for r in (tbl.get("rows") or [])
        if isinstance(r, dict) and str(r.get("row_type") or "") == "expandable"
    )
    expected = _SRC_DYNAMIC_MARK_COUNT[(cycle, variant)]
    assert actual == expected, (
        f"{cycle}/{variant} {table_name} 模板 expandable 行 {actual} 处 != 源模板首列 "
        f"`……` 标记 {expected} 处 ⇒ 要么凭空多了可扩位、要么真实可扩位被抹掉"
    )


def test_row_skeleton_registry_covers_all_twelve():
    """反向自检：12 个 (循环,变体) 必须**恰好**被两张登记表二分，不漏不重。"""
    asserted = set(_ROW_SKELETON_ASSERTED)
    skipped = set(_ROW_SKELETON_NOT_ASSERTED)
    assert not (asserted & skipped), f"同时出现在两张登记表：{sorted(asserted & skipped)}"
    assert asserted | skipped == set(_SECTION_MAP), (
        "行骨架登记表未覆盖全部 12 个 (循环,变体)："
        f"缺 {sorted(set(_SECTION_MAP) - asserted - skipped)}"
    )
    for key, reason in _ROW_SKELETON_NOT_ASSERTED.items():
        assert len(reason) >= 20, f"{key} 的免断言理由过短（≥20 字），疑似空话：{reason!r}"


def test_row_skeleton_source_anchors_still_valid():
    """反向自检：源侧行区间锚点仍有效（防源模板改版后区间漂移、判据比空气）。

    判据 = 区间**内**首末格非空 + 区间**外**紧邻的下一格不是数据行的延续
    （listed A49 = 「说明：」段落 / soe A60 = 「说明：」段落）。
    """
    for (cycle, variant), (_name, r1, r2) in _ROW_SKELETON_ASSERTED.items():
        rows = _src_col_a(cycle, variant, r1, r2)
        assert rows[0] and rows[-1], (
            f"{cycle}/{variant} 行区间 A{r1}:A{r2} 端点为空 ⇒ 锚点已漂移"
        )
        assert rows[0].startswith("一、"), (
            f"{cycle}/{variant} A{r1} 应是第一层标题（以「一、」开头），实测 {rows[0]!r}"
        )
        nxt = _src_col_a(cycle, variant, r2 + 1, r2 + 1)[0]
        assert nxt.startswith("说明"), (
            f"{cycle}/{variant} A{r2 + 1} 应是「说明：」段落（=数据区结束），实测 {nxt!r}"
        )


def test_row_skeleton_impairment_decrease_has_three_details():
    """点名钉死本轮修的那处：I1 两层减少段结构必须**三层一致**。

    源模板账面原值 / 累计摊销 / 减值准备三层的减少段都是
    「（1）处置 / （2）失效且终止确认的部分 / （3）其他减少」，无扩位。
    改造前只有减值准备层缺了「失效且终止确认的部分」并多了 `……`
    ⇒ 一旦有人按旧形态改回去，本条立刻打红并指名道姓。
    """
    tbl = _template_table("I1", "listed", "无形资产情况")
    rows = [_norm(r.get("label")) for r in (tbl.get("rows") or [])]
    dec_starts = [i for i, lb in enumerate(rows) if lb == "3.本期减少金额"]
    assert len(dec_starts) == 3, f"应有三层减少段，实测 {len(dec_starts)} 处：{rows}"
    want = ("（1）处置", "（2）失效且终止确认的部分", "（3）其他减少")
    for at in dec_starts:
        got = tuple(rows[at + 1 : at + 4])
        assert got == want, (
            f"第 {at} 行「3.本期减少金额」之后三个明细应为 {want}，实测 {got}"
        )
        assert rows[at + 4] == "4.期末余额", (
            f"减少段后应直接是「4.期末余额」（无扩位），实测 {rows[at + 4]!r}"
        )
