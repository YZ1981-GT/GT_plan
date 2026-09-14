"""附注同步**行级合并**语义守卫（多段共享表）。

`sub_table_data._row_scope` 声明「本次只负责这张表的这一段」，服务端按模板
`rows[].report_row_code` 切段，段内整段替换、**段外原样保留**。

**Validates: Requirements 1.1, 1.3~1.5, 2.2, 3.1~3.6, 4.1~4.4, 6.3~6.5
/ Properties 2, 3, 5, 6, 7, 8, 9, 10, 13, 17, 18**

实测基线（`八、92 外币货币性项目`，soe 25 行 5 段）：

| 段 | row_code | 区间 | 归属循环 |
|----|----------|------|---------|
| 货币资金 | BS-002 | [0,5) | E1 |
| 应收账款 | BS-006 | [5,10) | D2 |
| 短期借款 | BS-041 | [10,15) | K |
| 长期借款 | BS-061 | [15,20) | L |
| 应付债券 | BS-062 | [20,25) | L |

每段下都有「其中：美元 / 欧元 / 港币 / ……」→ **标签跨段重复**，
故落库侧必须靠 `_seg` 戳定位而不能按标签匹配（Property 6）。

反向自检两条：
1. fail closed 改成「回退整表覆盖」→ Property 2/5 必红
2. `stripComments()` 必须真的剥掉了注释（否则 Property 17 断言空转）
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote
from app.services.note_shared_table_segments import (
    SEG_KEY,
    VARIANT_LISTED,
    VARIANT_SOE,
    split_segments,
    stamp_baseline_rows,
    template_rows,
)
from app.services.wp_disclosure_sync_service import (
    ROW_SCOPE_KEY,
    RowScope,
    _extract_row_scope,
    _merge_rows_by_scope,
    sync_from_workpaper,
    wp_disclosure_sync_service,
)

PROJECT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WP_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
NOTE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
USER_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

FX_TABLE = "外币货币性项目"
FX_SECTION_SOE = "八、92"
FX_SECTION_LISTED = "五、73"
OWNER_E1 = "BS-002"          # 货币资金段（E1）
OWNER_D2 = "BS-006"          # 应收账款段（D2）
SHEET_SOE = "附注披露信息（国企）"

#: soe `八、92` 的段区间（模板实测，变了就要在此同步更新）
SOE_WINDOWS = {
    "BS-002": (0, 5),
    "BS-006": (5, 10),
    # 🔴 2026-08-09：`BS-031` → `BS-041`。`BS-031` 在 report_config 四准则下 row_name
    # 均为**使用权资产**（H8 的报表行），短期借款真值 `BS-041`（`TB('2001')`）。
    # 改动方 = spec `e-cycle-extraction-formula-and-disclosure-completion`
    #（`fix_note_e1_monetary_fund_structure.py` 修正表），本处跟随更新常量。
    "BS-041": (10, 15),
    "BS-061": (15, 20),
    "BS-062": (20, 25),
}


# ─── 测试替身（沿用 characterization 已验证的形态）──────────────────────────


def _user() -> MagicMock:
    u = MagicMock()
    u.id = USER_ID
    return u


def _scalar_result(value):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=value)
    return res


def _project_row(audit_year: int, standard: dict) -> MagicMock:
    row = MagicMock()
    row.first = MagicMock(return_value=(audit_year, standard, None, None))
    return row


def _note(table_data: dict, *, section: str = FX_SECTION_SOE) -> DisclosureNote:
    n = DisclosureNote(
        project_id=PROJECT_ID,
        year=2025,
        note_section=section,
        section_title="外币货币性项目",
        table_data=table_data,
        is_deleted=False,
    )
    n.id = NOTE_ID
    n.last_sync_at = None
    return n


def _make_db(note: DisclosureNote | None, *, entity_type: str = "soe") -> MagicMock:
    db = MagicMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    sequence = [
        _project_row(2025, {"entity_type": entity_type, "scope": "standalone"}),
        _scalar_result(note),
    ]
    if note is None:
        sequence.append(_scalar_result(None))
    db.execute = AsyncMock(side_effect=sequence)
    return db


async def _run(
    existing_sub: dict | None,
    payload: dict,
    *,
    section: str = FX_SECTION_SOE,
    standard: str = "soe_standalone",
    entity_type: str = "soe",
    columns: dict | None = None,
) -> tuple[dict, dict]:
    """跑一次 `sync_from_workpaper`，返回 ``(sub_table_data, result)``。"""
    td = {"sub_table_data": dict(existing_sub)} if existing_sub is not None else {}
    note = _note(td, section=section)
    db = _make_db(note, entity_type=entity_type)
    result = await sync_from_workpaper(
        db,
        PROJECT_ID,
        wp_id=WP_ID,
        sheet_name=SHEET_SOE,
        section_id=section,
        sub_table_data=payload,
        current_standard=standard,
        user=_user(),
        commit=False,
        sub_table_columns=columns,
    )
    return dict(note.table_data.get("sub_table_data") or {}), result


def _scope_payload(rows: list[dict], *, owner: str = OWNER_E1, table: str = FX_TABLE) -> dict:
    return {table: rows, ROW_SCOPE_KEY: {table: {"owner_row_code": owner}}}


def _e1_rows() -> list[dict]:
    return [
        {"label": "货币资金", "fc_amount": None, "rate": None, "rmb_amount": None},
        {"label": "其中：美元", "fc_amount": 14000, "rate": 7.1884, "rmb_amount": 100637.6},
        {"label": "欧元", "fc_amount": 2000, "rate": 7.8592, "rmb_amount": 15718.4},
    ]


def _soe_baseline_with_other_segments() -> list[dict]:
    """落库基线：他四段已有真实数据（用于 Property 2 / 9）。"""
    rows = stamp_baseline_rows(template_rows(VARIANT_SOE, FX_SECTION_SOE, FX_TABLE))
    # D2 已录应收账款段美元
    rows[6] = {**rows[6], "fc_amount": 5000, "rate": 7.2, "rmb_amount": 36000}
    # L 已录应付债券段欧元
    rows[22] = {**rows[22], "fc_amount": 900, "rate": 7.8, "rmb_amount": 7020}
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# `_extract_row_scope`
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractRowScope:
    """Requirement 1.1 / 1.4：声明剥离与非法形态丢弃。"""

    def test_legal_declaration(self):
        data, scopes = _extract_row_scope(_scope_payload(_e1_rows()))
        assert ROW_SCOPE_KEY not in data
        assert set(data) == {FX_TABLE}
        assert scopes == {FX_TABLE: RowScope(table_name=FX_TABLE, owner_row_code=OWNER_E1)}

    def test_absent_declaration_is_noop(self):
        payload = {FX_TABLE: _e1_rows()}
        data, scopes = _extract_row_scope(payload)
        assert scopes == {}
        assert data == payload
        assert data is not payload, "必须返回副本，不得原地改调用方载荷"

    @pytest.mark.parametrize(
        "raw",
        [
            "BS-002",                                  # 整体非 dict
            ["外币货币性项目"],
            {FX_TABLE: "BS-002"},                      # 单条非 dict（不容忍简写）
            {FX_TABLE: {}},                            # 缺 owner_row_code
            {FX_TABLE: {"owner_row_code": "   "}},     # 空白
            {"_note_texts": {"owner_row_code": "BS-002"}},  # 表名是元数据键
            {"": {"owner_row_code": "BS-002"}},        # 空表名
        ],
    )
    def test_illegal_forms_are_discarded(self, raw):
        data, scopes = _extract_row_scope({FX_TABLE: [], ROW_SCOPE_KEY: raw})
        assert scopes == {}, "非法声明必须丢弃 → 该表退回表级覆盖（既有语义）"
        assert ROW_SCOPE_KEY not in data


# ─────────────────────────────────────────────────────────────────────────────
# `_merge_rows_by_scope` 纯函数
# ─────────────────────────────────────────────────────────────────────────────


class TestMergeRowsByScopePure:
    def test_property3_identity(self):
        """Property 3：`result == baseline[:start] + incoming + baseline[end:]`。"""
        baseline = _soe_baseline_with_other_segments()
        incoming = _e1_rows()
        merged, err = _merge_rows_by_scope(
            baseline,
            incoming,
            scope=RowScope(FX_TABLE, OWNER_E1),
            variant=VARIANT_SOE,
            section_number=FX_SECTION_SOE,
        )
        assert err is None
        start, end = SOE_WINDOWS[OWNER_E1]
        expected = (
            baseline[:start]
            + [{**r, SEG_KEY: OWNER_E1} for r in incoming]
            + baseline[end:]
        )
        assert merged == expected
        # 段内行数允许 ≠ 模板段行数（推 3 行 vs 模板 5 行）
        assert len(merged) == len(baseline) - (end - start) + len(incoming)

    def test_property2_other_segments_byte_identical(self):
        """Property 2：段外行逐字段不变（含 `None` 与 `0` 的区别）。"""
        baseline = _soe_baseline_with_other_segments()
        before = json.dumps(baseline[5:], ensure_ascii=False, sort_keys=True)
        merged, err = _merge_rows_by_scope(
            baseline,
            _e1_rows(),
            scope=RowScope(FX_TABLE, OWNER_E1),
            variant=VARIANT_SOE,
            section_number=FX_SECTION_SOE,
        )
        assert err is None
        after = json.dumps(merged[len(_e1_rows()):], ensure_ascii=False, sort_keys=True)
        assert after == before

    def test_property6_duplicate_labels_do_not_bleed(self):
        """Property 6：「其中：美元」在 5 个段里重复，只改 owner 段那一行。"""
        baseline = _soe_baseline_with_other_segments()
        merged, err = _merge_rows_by_scope(
            baseline,
            [
                {"label": "货币资金"},
                {"label": "其中：美元", "fc_amount": 111},
                {"label": "欧元"},
                {"label": "港币"},
                {"label": "……"},
            ],
            scope=RowScope(FX_TABLE, OWNER_E1),
            variant=VARIANT_SOE,
            section_number=FX_SECTION_SOE,
        )
        assert err is None
        usd = [(i, r) for i, r in enumerate(merged) if r.get("label") == "其中：美元"]
        assert len(usd) == 5, "五个段各有一行「其中：美元」"
        assert usd[0][1]["fc_amount"] == 111                      # owner 段被改
        assert usd[1][1]["fc_amount"] == 5000                     # D2 段原值保留
        assert all("fc_amount" not in r or r["fc_amount"] in (None, 5000, 111)
                   for _i, r in usd)

    @pytest.mark.parametrize(
        "variant,section,owner,expect_err",
        [
            (None, FX_SECTION_SOE, OWNER_E1, "variant_unresolved"),
            (VARIANT_SOE, "八、9999", OWNER_E1, "template_table_not_found"),
            (VARIANT_SOE, FX_SECTION_SOE, "BS-9999", "owner_row_code_not_in_template"),
            # 🔴 listed 模板里**没有** `八、92`（soe 专属编号）→ 变体查错必 fail closed
            (VARIANT_LISTED, FX_SECTION_SOE, OWNER_E1, "template_table_not_found"),
        ],
    )
    def test_property5_fail_closed(self, variant, section, owner, expect_err):
        """Property 5：解析失败 → 返回**原样基线** + error，绝不回退整表覆盖。"""
        baseline = _soe_baseline_with_other_segments()
        snapshot = json.dumps(baseline, ensure_ascii=False, sort_keys=True)
        merged, err = _merge_rows_by_scope(
            baseline,
            _e1_rows(),
            scope=RowScope(FX_TABLE, owner),
            variant=variant,
            section_number=section,
        )
        assert err == expect_err
        assert json.dumps(merged, ensure_ascii=False, sort_keys=True) == snapshot

    def test_property5_error_never_returns_incoming(self):
        """🔴 反向自检的正向形式：error 分支返回的**绝不能**是 incoming。

        若哪天有人把 fail closed 改成「回退整表覆盖」（`return incoming, None`
        或 `return incoming, err`），本断言必红 —— 那个改动会让他循环的
        应收账款/短期借款/长期借款/应付债券四段整段消失。
        """
        baseline = _soe_baseline_with_other_segments()
        incoming = _e1_rows()
        merged, err = _merge_rows_by_scope(
            baseline,
            incoming,
            scope=RowScope(FX_TABLE, "BS-9999"),
            variant=VARIANT_SOE,
            section_number=FX_SECTION_SOE,
        )
        assert err
        assert merged != [{**r, SEG_KEY: "BS-9999"} for r in incoming]
        assert len(merged) == len(baseline)
        for head in ("应收账款", "短期借款", "长期借款", "应付债券"):
            assert any(r.get("label") == head for r in merged), (
                f"fail closed 必须保住他段段首「{head}」"
            )

    def test_property8_first_sync_keeps_other_skeleton(self):
        """Property 8：落库无该表 → 基线取模板骨架，他段标签全在、数值为空。"""
        merged, err = _merge_rows_by_scope(
            None,
            _e1_rows(),
            scope=RowScope(FX_TABLE, OWNER_E1),
            variant=VARIANT_SOE,
            section_number=FX_SECTION_SOE,
        )
        assert err is None
        labels = [r["label"] for r in merged]
        for head in ("应收账款", "短期借款", "长期借款", "应付债券"):
            assert head in labels
        others = [r for r in merged if r.get(SEG_KEY) != OWNER_E1]
        assert others, "他段必须有骨架行"
        for r in others:
            assert set(r) <= {"label", SEG_KEY, "is_total", "row_type"}, (
                f"他段骨架行不得预置数值列：{r}"
            )

    def test_property9_existing_data_not_reverted_to_template(self):
        """Property 9：他段已录值不被模板空值覆盖。"""
        baseline = _soe_baseline_with_other_segments()
        merged, err = _merge_rows_by_scope(
            baseline,
            _e1_rows(),
            scope=RowScope(FX_TABLE, OWNER_E1),
            variant=VARIANT_SOE,
            section_number=FX_SECTION_SOE,
        )
        assert err is None
        d2_usd = next(
            r for r in merged if r.get(SEG_KEY) == OWNER_D2 and r["label"] == "其中：美元"
        )
        assert d2_usd["rmb_amount"] == 36000

    def test_property10_empty_push_restores_skeleton(self):
        """Property 10：owner 推 `[]` → 段回到模板骨架（标签留、数值空），段不消失。"""
        baseline = _soe_baseline_with_other_segments()
        baseline[1] = {**baseline[1], "fc_amount": 999}
        merged, err = _merge_rows_by_scope(
            baseline,
            [],
            scope=RowScope(FX_TABLE, OWNER_E1),
            variant=VARIANT_SOE,
            section_number=FX_SECTION_SOE,
        )
        assert err is None
        assert len(merged) == len(baseline), "行数不减少"
        seg_rows = merged[0:5]
        assert [r["label"] for r in seg_rows] == [
            "货币资金", "其中：美元", "欧元", "港币", "……",
        ]
        assert all("fc_amount" not in r for r in seg_rows), "数值置空而非留旧值"
        assert all(r[SEG_KEY] == OWNER_E1 for r in seg_rows)

    def test_stamped_window_beats_template_index(self):
        """Requirement 3.4：落库有 `_seg` 戳时按戳定位（段行数已被扩展过也认）。"""
        baseline = stamp_baseline_rows(template_rows(VARIANT_SOE, FX_SECTION_SOE, FX_TABLE))
        # E1 上次推了 7 行（多加了两个自定义币种）→ 戳区间是 [0,7)
        extra = [
            {"label": "日元", SEG_KEY: OWNER_E1},
            {"label": "澳元", SEG_KEY: OWNER_E1},
        ]
        baseline = baseline[:5] + extra + baseline[5:]
        merged, err = _merge_rows_by_scope(
            baseline,
            _e1_rows(),
            scope=RowScope(FX_TABLE, OWNER_E1),
            variant=VARIANT_SOE,
            section_number=FX_SECTION_SOE,
        )
        assert err is None
        assert [r["label"] for r in merged[:3]] == ["货币资金", "其中：美元", "欧元"]
        assert merged[3]["label"] == "应收账款", "戳区间 [0,7) 被整段替换，日元/澳元一并退场"
        assert len(merged) == len(baseline) - 7 + 3

    def test_short_baseline_is_clipped(self):
        """Requirement 4.3：落库行数 < 模板段 end → 窗口按落库长度裁剪，不 IndexError。"""
        baseline = [{"label": "货币资金"}, {"label": "其中：美元"}]  # 无 `_seg` 戳
        merged, err = _merge_rows_by_scope(
            baseline,
            [{"label": "货币资金"}, {"label": "其中：美元", "fc_amount": 1}],
            scope=RowScope(FX_TABLE, OWNER_E1),
            variant=VARIANT_SOE,
            section_number=FX_SECTION_SOE,
        )
        assert err is None
        assert len(merged) == 2
        assert merged[1]["fc_amount"] == 1


class TestTableLevelTotalRowSurvives:
    """🔴 表级合计行不属于任何段 → owner 推送后必须**原样保留**。

    实测 14 个段的尾部挂着表最后一行的「合计 / 小计」。若把它算进末段，
    末段 owner 一推数据就会把整表合计删掉（附注交付物缺合计 = 表没编完）。
    """

    CASES = [
        (VARIANT_LISTED, "五、32", "所有权或使用权受到限制的资产", "BS-032", "合计"),
        # 「续：」已由 restricted-assets-note-row-scope-rollout Task 3 正名
        (VARIANT_LISTED, "五、32", "所有权或使用权受到限制的资产（续：上年年末）", "BS-032", "合计"),
        (VARIANT_LISTED, "五、71", "资产负债表中的列报项目和相关信息", "BS-050", "合计"),
        (VARIANT_SOE, "八、91", "资产负债表中的列报项目和相关信息", "BS-037", "合计"),
        (VARIANT_SOE, "八、81", "筹资活动产生的各项负债的变动情况", "BS-063", "合计"),
    ]

    @pytest.mark.parametrize("variant,section,table,owner,total_label", CASES)
    def test_last_segment_push_keeps_total_row(
        self, variant, section, table, owner, total_label
    ):
        tpl = template_rows(variant, section, table)
        assert tpl is not None
        baseline = stamp_baseline_rows(tpl)
        assert baseline[-1]["label"] == total_label
        assert baseline[-1][SEG_KEY] == "", "合计行的 `_seg` 必须留空"

        merged, err = _merge_rows_by_scope(
            baseline,
            [{"label": "自定义受限项目", "end_amount": 1234}],
            scope=RowScope(table, owner),
            variant=variant,
            section_number=section,
        )
        assert err is None
        assert merged[-1]["label"] == total_label, "表级合计行被 owner 推送删掉了"
        assert merged[-1].get(SEG_KEY) in ("", None)
        # owner 段内是自己的行；他段行数不变
        own = [r for r in merged if r.get(SEG_KEY) == owner]
        assert [r["label"] for r in own] == ["自定义受限项目"]

    @pytest.mark.parametrize("variant,section,table,owner,total_label", CASES)
    def test_empty_push_also_keeps_total_row(
        self, variant, section, table, owner, total_label
    ):
        """空推送恢复段骨架时同样不得越界吃掉合计行。"""
        tpl = template_rows(variant, section, table)
        baseline = stamp_baseline_rows(tpl)
        merged, err = _merge_rows_by_scope(
            baseline, [], scope=RowScope(table, owner), variant=variant, section_number=section
        )
        assert err is None
        assert merged[-1]["label"] == total_label
        assert len(merged) == len(baseline)

    def test_reverse_check_using_end_would_delete_total(self):
        """🔴 反向自检：用 `end` 而非 `data_end` 做窗口右界，合计行必被删。"""
        variant, section, table, owner = (
            VARIANT_SOE,
            "八、81",
            "筹资活动产生的各项负债的变动情况",
            "BS-063",
        )
        tpl = template_rows(variant, section, table)
        baseline = stamp_baseline_rows(tpl)
        seg = next(s for s in split_segments(tpl) if s.row_code == owner)
        assert seg.data_end < seg.end
        bad = baseline[: seg.start] + [{"label": "x"}] + baseline[seg.end :]
        assert not any(r.get("label") == "合计" for r in bad), "退化口径确实删掉了合计行"
        good = baseline[: seg.start] + [{"label": "x"}] + baseline[seg.data_end :]
        assert good[-1]["label"] == "合计"


class TestMergeRowsPBT:
    """PBT：随机 owner 段 + 随机推送行数 → Property 3 恒等式 + 段外不变。"""

    @settings(max_examples=25, deadline=None)
    @given(
        owner_idx=st.integers(min_value=0, max_value=4),
        n_rows=st.integers(min_value=0, max_value=6),
    )
    def test_identity_and_outside_unchanged(self, owner_idx, n_rows):
        owner = list(SOE_WINDOWS)[owner_idx]
        start, end = SOE_WINDOWS[owner]
        baseline = _soe_baseline_with_other_segments()
        incoming = [{"label": f"r{i}", "fc_amount": i} for i in range(n_rows)]
        merged, err = _merge_rows_by_scope(
            baseline,
            incoming,
            scope=RowScope(FX_TABLE, owner),
            variant=VARIANT_SOE,
            section_number=FX_SECTION_SOE,
        )
        assert err is None
        if incoming:
            seg = [{**r, SEG_KEY: owner} for r in incoming]
        else:
            seg = stamp_baseline_rows(
                template_rows(VARIANT_SOE, FX_SECTION_SOE, FX_TABLE)
            )[start:end]
        assert merged == baseline[:start] + seg + baseline[end:]
        # 段外逐字节不变
        assert merged[:start] == baseline[:start]
        assert merged[start + len(seg):] == baseline[end:]


# ─────────────────────────────────────────────────────────────────────────────
# 服务层
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestServiceRowLevelMerge:
    async def test_scoped_table_merges_and_reports(self):
        baseline = _soe_baseline_with_other_segments()
        sub, result = await _run({FX_TABLE: baseline}, _scope_payload(_e1_rows()))
        assert result["row_scoped_tables"] == [FX_TABLE]
        assert result["row_scope_unresolved"] == []
        rows = sub[FX_TABLE]
        assert [r["label"] for r in rows[:3]] == ["货币资金", "其中：美元", "欧元"]
        assert rows[3]["label"] == "应收账款"
        # 他段数据完好
        assert any(r.get("rmb_amount") == 36000 for r in rows)
        assert any(r.get("rmb_amount") == 7020 for r in rows)

    async def test_property7_seg_stamp_on_every_written_row(self):
        sub, _ = await _run({}, _scope_payload(_e1_rows()))
        rows = sub[FX_TABLE]
        assert all(SEG_KEY in r for r in rows), "写入后每一行都带 `_seg`"
        assert {r[SEG_KEY] for r in rows} == set(SOE_WINDOWS)

    async def test_unscoped_tables_untouched_in_same_payload(self):
        """混合载荷：只有声明了 `_row_scope` 的表走行级合并。"""
        payload = {
            FX_TABLE: _e1_rows(),
            "货币资金分类": [{"label": "银行存款", "end": 1}],
            ROW_SCOPE_KEY: {FX_TABLE: {"owner_row_code": OWNER_E1}},
        }
        sub, result = await _run({FX_TABLE: _soe_baseline_with_other_segments()}, payload)
        assert result["row_scoped_tables"] == [FX_TABLE]
        assert sub["货币资金分类"] == [{"label": "银行存款", "end": 1}], (
            "未声明的表逐字节走原表级覆盖"
        )

    async def test_fail_closed_skips_table_and_keeps_others(self):
        """Property 5 服务层：解析失败 → 该表完全未写、其余表照常。"""
        baseline = _soe_baseline_with_other_segments()
        snapshot = json.dumps(baseline, ensure_ascii=False, sort_keys=True)
        payload = {
            FX_TABLE: _e1_rows(),
            "其他表": [{"label": "x"}],
            ROW_SCOPE_KEY: {FX_TABLE: {"owner_row_code": "BS-9999"}},
        }
        sub, result = await _run({FX_TABLE: baseline}, payload)
        assert result["row_scope_unresolved"] == [FX_TABLE]
        assert result["row_scoped_tables"] == []
        assert json.dumps(sub[FX_TABLE], ensure_ascii=False, sort_keys=True) == snapshot
        assert sub["其他表"] == [{"label": "x"}]

    async def test_fail_closed_does_not_create_table(self):
        """落库本来没有该表 + 解析失败 → 不得凭空创建（半成品表比没表更坏）。"""
        payload = {FX_TABLE: _e1_rows(), ROW_SCOPE_KEY: {FX_TABLE: {"owner_row_code": "BS-9999"}}}
        sub, result = await _run({}, payload)
        assert FX_TABLE not in sub
        assert result["row_scope_unresolved"] == [FX_TABLE]

    async def test_orphan_declaration_ignored(self):
        """Requirement 1.4：声明的表不在本次推送里 → 忽略该条声明。"""
        payload = {
            "货币资金分类": [{"label": "银行存款"}],
            ROW_SCOPE_KEY: {FX_TABLE: {"owner_row_code": OWNER_E1}},
        }
        sub, result = await _run({FX_TABLE: [{"label": "货币资金"}]}, payload)
        assert result["row_scoped_tables"] == []
        assert result["row_scope_unresolved"] == []
        assert sub[FX_TABLE] == [{"label": "货币资金"}], "既有表未被动"

    async def test_property18_variant_from_standard_not_section_number(self):
        """Property 18：变体由 `current_standard` 定，不按章节号推导。

        `八、92` 只存在于 soe 模板。以 `listed_standalone` 推同一章节号必须
        fail closed（而不是"两份模板里谁有取谁"地蒙对）。
        """
        sub, result = await _run(
            {FX_TABLE: _soe_baseline_with_other_segments()},
            _scope_payload(_e1_rows()),
            standard="listed_standalone",
            entity_type="listed",
        )
        assert result["row_scope_unresolved"] == [FX_TABLE]
        assert result["row_scoped_tables"] == []

    async def test_listed_section_works_with_listed_standard(self):
        """listed `五、73` 3 段 16 行同款可用。"""
        sub, result = await _run(
            {},
            _scope_payload(_e1_rows()),
            section=FX_SECTION_LISTED,
            standard="listed_standalone",
            entity_type="listed",
        )
        assert result["row_scoped_tables"] == [FX_TABLE]
        rows = sub[FX_TABLE]
        assert {r[SEG_KEY] for r in rows} == {"BS-002", "BS-006", "BS-061"}


# ─────────────────────────────────────────────────────────────────────────────
# Property 13：两个写入口一致
# ─────────────────────────────────────────────────────────────────────────────


def _make_html_db(note: DisclosureNote) -> MagicMock:
    db = MagicMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    mapping_res = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[note])
    mapping_res.scalars = MagicMock(return_value=scalars)
    db.execute = AsyncMock(
        side_effect=[
            mapping_res,             # _get_section_mapping
            _scalar_result(2025),    # _resolve_project_audit_year
            _scalar_result(note),    # _get_note
        ]
    )
    return db


@pytest.mark.asyncio
class TestBothEntriesConsistent:
    async def test_property13_same_payload_same_sub_table_data(self):
        baseline = _soe_baseline_with_other_segments()
        payload = _scope_payload(_e1_rows())

        sub_wp, res_wp = await _run({FX_TABLE: baseline}, dict(payload))

        html_note = _note(
            {
                "sub_table_data": {FX_TABLE: [dict(r) for r in baseline]},
                "_last_sync_sheet": SHEET_SOE,
                "_current_standard": "soe_standalone",
            }
        )
        html_db = _make_html_db(html_note)
        res_html = await wp_disclosure_sync_service.sync_from_html(
            html_db,
            WP_ID,
            SHEET_SOE,
            dict(payload),
            project_id=PROJECT_ID,
            user=_user(),
        )
        sub_html = dict(html_note.table_data.get("sub_table_data") or {})

        assert res_html["row_scoped_tables"] == res_wp["row_scoped_tables"] == [FX_TABLE]
        assert res_html["row_scope_unresolved"] == res_wp["row_scope_unresolved"] == []
        assert json.dumps(sub_html, ensure_ascii=False, sort_keys=True) == json.dumps(
            sub_wp, ensure_ascii=False, sort_keys=True
        )

    async def test_property7_seg_does_not_leak_into_projection(self):
        """Property 7：`_seg` 是行内元数据，读时投影与列头都不得带它。"""
        from app.services.note_sub_table_projector import project_sub_tables

        columns = {
            FX_TABLE: [
                {"key": "label", "label": "项目", "flat": True},
                {"key": "fc_amount", "label": "期末外币余额", "flat": True},
                {"key": "rate", "label": "折算汇率", "flat": True},
                {"key": "rmb_amount", "label": "期末折算人民币余额", "flat": True},
            ]
        }
        note = _note({"sub_table_data": {}})
        db = _make_db(note)
        await sync_from_workpaper(
            db,
            PROJECT_ID,
            wp_id=WP_ID,
            sheet_name=SHEET_SOE,
            section_id=FX_SECTION_SOE,
            sub_table_data=_scope_payload(_e1_rows()),
            current_standard="soe_standalone",
            user=_user(),
            commit=False,
            sub_table_columns=columns,
        )
        # 落库行确实带戳
        assert all(SEG_KEY in r for r in note.table_data["sub_table_data"][FX_TABLE])
        tables = project_sub_tables(note.table_data)
        assert tables and tables[0]["name"] == FX_TABLE
        tbl = tables[0]
        assert tbl["_column_groups"] == [], "4 列全 flat → 不得凭空推断父表头"
        assert SEG_KEY not in tbl["headers"]
        assert all(d.get("key") != SEG_KEY for d in tbl["columns"])
        for row in tbl["rows"]:
            assert set(row) == {"label", "values", "is_total"}
            assert SEG_KEY not in json.dumps(row, ensure_ascii=False)
        assert all(SEG_KEY not in str(k) for k in note.table_data["_sub_table_columns"])

    async def test_html_entry_fail_closed(self):
        baseline = _soe_baseline_with_other_segments()
        snapshot = json.dumps(baseline, ensure_ascii=False, sort_keys=True)
        html_note = _note(
            {
                "sub_table_data": {FX_TABLE: [dict(r) for r in baseline]},
                "_last_sync_sheet": SHEET_SOE,
                "_current_standard": "soe_standalone",
            }
        )
        db = _make_html_db(html_note)
        res = await wp_disclosure_sync_service.sync_from_html(
            db,
            WP_ID,
            SHEET_SOE,
            {FX_TABLE: _e1_rows(), ROW_SCOPE_KEY: {FX_TABLE: {"owner_row_code": "BS-9999"}}},
            project_id=PROJECT_ID,
            user=_user(),
        )
        assert res["row_scope_unresolved"] == [FX_TABLE]
        sub = html_note.table_data["sub_table_data"]
        assert json.dumps(sub[FX_TABLE], ensure_ascii=False, sort_keys=True) == snapshot


# ─────────────────────────────────────────────────────────────────────────────
# Property 17：JSONB 写入不得用 `type_coerce`
# ─────────────────────────────────────────────────────────────────────────────

_SERVICE_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "services" / "wp_disclosure_sync_service.py"
)
_SEG_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "services" / "note_shared_table_segments.py"
)


def _strip_comments(src: str) -> str:
    """剥掉 `#` 行注释与三引号 docstring —— 说明文字里会写被禁的反例。"""
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = re.sub(r"'''(?:.|\n)*?'''", "", src)
    return re.sub(r"(?m)#.*$", "", src)


class TestNoTypeCoerce:
    def test_service_has_no_type_coerce(self):
        code = _strip_comments(_SERVICE_PATH.read_text(encoding="utf-8"))
        assert "type_coerce" not in code, (
            "JSONB 写入禁 `sa.type_coerce`（asyncpg 下 100% 失败）→ "
            "用 `CAST(:td AS jsonb)` + `json.dumps(ensure_ascii=False)`"
        )

    def test_raw_jsonb_update_uses_cast(self):
        code = _strip_comments(_SERVICE_PATH.read_text(encoding="utf-8"))
        for m in re.finditer(r"sa\.text\(\s*[\"']{1,3}(.{0,400}?)[\"']{1,3}\s*\)", code, re.S):
            stmt = m.group(1)
            if "jsonb" in stmt.lower() and "update" in stmt.lower():
                assert "CAST(" in stmt.upper(), f"raw JSONB 写入未用 CAST：{stmt[:120]}"

    def test_reverse_check_strip_comments_actually_strips(self):
        """🔴 反向自检：`_strip_comments` 必须真的剥掉了注释，否则上面断言空转。"""
        raw = _SEG_MODULE_PATH.read_text(encoding="utf-8")
        stripped = _strip_comments(raw)
        assert "禁止按章节号推导" in raw
        assert "禁止按章节号推导" not in stripped
        assert len(stripped) < len(raw) * 0.8
        # 且不能把代码也剥掉
        assert "def split_segments" in stripped
