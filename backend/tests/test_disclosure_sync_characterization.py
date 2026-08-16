"""附注同步写路径 characterization（零回归网）—— **先于任何行级合并改动落地**。

背景：`disclosure-note-row-level-merge` 要在 `wp_disclosure_sync_service` 的
表级浅合并之上加一层行级合并。改的是 90+ 个已接线披露 Tab 共用的核心写路径，
所以先把「无 `_row_scope` 的载荷合并结果」用 golden 快照逐字节钉死。

**Property 1（Requirements 1.2 / 6.1）**：对任意不含 `_row_scope` 的载荷，
合并后的 `table_data` 与改动前实现的输出**逐字节相同**。

覆盖的既有代码路径（每条都是历史上真实修过的缺陷）：

| 路径 | 语义 | 历史依据 |
|------|------|---------|
| 空载荷 no-op | 绝不清空既有子表 | 「表格丢失主因修复」 |
| 表级浅合并 | 同名覆盖 / 未推送保留 | H4 仅推「工程物资」不清空 H2 在建工程 |
| 显式空数组 | `{表:[]}` 是「空行」有效状态，照常覆盖 | 区别于删除 |
| `_note_texts` | 剥离 → `text_content`，`【title】\n{text}` 拼接 | UI 全中文化 |
| `_removed_table_keys` | 删旧表名，**跳过本次推送键** | 底稿改版重命名残留空表 |
| `_sub_table_columns` | 同款浅合并 + 空 no-op | 投影器据此渲染表头 |

🔴 **volatile 字段**（`_last_sync_at` 时间戳）在比对前剔除，其余全部参与比对。

🔴 **本 spec Wave 3 已诚实改动的唯一 golden**：`_note_texts` 缺失时原实现把
`text_content` 置 `None`（多循环共章节时覆盖他人说明），现改为**保留既有**。
见 `test_no_note_texts_keeps_text_content` 的 docstring（原断言与改动理由都在那里）。
其余 golden 一条未动 —— 那是 Property 1 的凭据。
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote
from app.services.wp_disclosure_sync_service import sync_from_workpaper

PROJECT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WP_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
NOTE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
USER_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

#: 与 `wp_disclosure_sync_service` 写入的元数据键一致；时间戳是 volatile，比对前剔除
VOLATILE_KEYS = ("_last_sync_at",)


# ─── 测试替身（沿用 test_wp_disclosure_sync_revive.py 已验证的形态）──────────


def _user() -> MagicMock:
    u = MagicMock()
    u.id = USER_ID
    return u


def _scalar_result(value):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=value)
    return res


def _project_row(audit_year: int, standard: dict) -> MagicMock:
    """`_resolve_project_sync_context` 一次取回 audit_year + 准则四列。"""
    row = MagicMock()
    row.first = MagicMock(return_value=(audit_year, standard, None, None))
    return row


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


def _note(table_data: dict, *, text_content: str | None = None) -> DisclosureNote:
    n = DisclosureNote(
        project_id=PROJECT_ID,
        year=2025,
        note_section="八、1",
        section_title="货币资金",
        table_data=table_data,
        text_content=text_content,
        is_deleted=False,
    )
    n.id = NOTE_ID
    return n


def _canonical(table_data: dict) -> str:
    """稳定序列化：剔除 volatile 时间戳，键排序，中文不转义。"""
    clean = {k: v for k, v in (table_data or {}).items() if k not in VOLATILE_KEYS}
    return json.dumps(clean, sort_keys=True, ensure_ascii=False)


async def _run(
    existing_table_data: dict | None,
    payload: dict,
    *,
    columns: dict | None = None,
    existing_text: str | None = None,
    standard: str = "soe_standalone",
) -> tuple[dict, str | None, dict]:
    """跑一次同步，返回 ``(table_data, text_content, result)``。"""
    note = _note(dict(existing_table_data or {}), text_content=existing_text)
    db = _make_db(note)
    result = await sync_from_workpaper(
        db,
        PROJECT_ID,
        wp_id=WP_ID,
        sheet_name="附注披露信息(国企)",
        section_id="八、1",
        sub_table_data=payload,
        current_standard=standard,
        user=_user(),
        commit=False,
        sub_table_columns=columns,
    )
    return note.table_data, note.text_content, result


# ─── Golden 快照 ─────────────────────────────────────────────────────────────
#
# 每条 golden 是「现状实现」的输出。改动后必须逐字节一致；
# 唯一允许变的是 Wave 3 的 `text_content` 保留语义（见模块 docstring）。


@pytest.mark.asyncio
class TestCharacterizationTableLevelMerge:
    """表级浅合并语义 golden（Property 1）。"""

    async def test_shallow_merge_keeps_unpushed_table(self):
        """H4 范式：仅推「工程物资」不得清空 H2 已同步的「在建工程」。"""
        td, _, _ = await _run(
            {
                "sub_table_data": {
                    "在建工程": [{"label": "厂房", "end_book": 100}],
                    "工程物资": [{"label": "专用材料", "end_book": 1}],
                }
            },
            {"工程物资": [{"label": "专用设备", "end_book": 2}]},
        )
        assert _canonical(td) == json.dumps(
            {
                "_current_standard": "soe_standalone",
                "_last_sync_sheet": "附注披露信息(国企)",
                "_last_sync_wp_id": str(WP_ID),
                "_source": "workpaper",
                "sub_table_data": {
                    "在建工程": [{"label": "厂房", "end_book": 100}],
                    "工程物资": [{"label": "专用设备", "end_book": 2}],
                },
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    async def test_empty_payload_is_noop_keeps_all_tables(self):
        """空载荷绝不清空既有子表（历史「表格丢失主因」）。"""
        existing = {
            "sub_table_data": {
                "货币资金": [{"label": "现金", "end_amount": 1}],
                "受限制的货币资金明细": [{"label": "保证金", "end_amount": 2}],
            }
        }
        td, _, _ = await _run(existing, {})
        assert json.loads(_canonical(td))["sub_table_data"] == existing["sub_table_data"]

    async def test_explicit_empty_array_overwrites(self):
        """`{表:[]}` 是「空行」有效状态，照常覆盖（区别于删除）。"""
        td, _, _ = await _run(
            {"sub_table_data": {"货币资金": [{"label": "现金", "end_amount": 1}]}},
            {"货币资金": []},
        )
        assert json.loads(_canonical(td))["sub_table_data"] == {"货币资金": []}

    async def test_columns_shallow_merge_and_empty_noop(self):
        """`_sub_table_columns` 同款浅合并；空载荷不清空既有列头。"""
        existing = {
            "sub_table_data": {"A": [{"label": "x"}], "B": [{"label": "y"}]},
            "_sub_table_columns": {"A": [{"key": "label", "flat": True}]},
        }
        td, _, _ = await _run(
            existing,
            {"B": [{"label": "y2"}]},
            columns={"B": [{"key": "label", "label": "项目", "flat": True}]},
        )
        cols = json.loads(_canonical(td))["_sub_table_columns"]
        assert cols["A"] == [{"key": "label", "flat": True}]          # 未推送 → 保留
        assert cols["B"] == [{"key": "label", "label": "项目", "flat": True}]

        td2, _, _ = await _run(existing, {"B": [{"label": "y3"}]}, columns=None)
        assert json.loads(_canonical(td2))["_sub_table_columns"] == existing["_sub_table_columns"]


@pytest.mark.asyncio
class TestCharacterizationMetadataKeys:
    """`_note_texts` / `_removed_table_keys` 元数据键 golden。"""

    async def test_note_texts_extracted_to_text_content(self):
        td, text, result = await _run(
            {"sub_table_data": {}},
            {
                "货币资金": [{"label": "现金", "end_amount": 1}],
                "_note_texts": [
                    {"section": "restricted", "title": "受限及境外款项说明", "text": "本期无受限。"},
                    {"section": "blank", "title": "空段", "text": "   "},
                ],
            },
        )
        # 空文本段被过滤，非空段按 `【title】\n{text}` 拼接
        assert text == "【受限及境外款项说明】\n本期无受限。"
        assert result["texts_synced"] == 2
        # `_note_texts` 不留在 sub_table_data 里，而是提到 table_data 顶层
        parsed = json.loads(_canonical(td))
        assert "_note_texts" not in parsed["sub_table_data"]
        assert parsed["_note_texts"][0]["section"] == "restricted"

    async def test_no_note_texts_keeps_text_content(self):
        """🔴 **本 spec Wave 3 诚实改动的唯一 golden**（Requirement 5.2）。

        原断言锁的是「未推送 `_note_texts` → `text_content` 置 `None`」，
        那正是本 spec 要修掉的缺陷：多循环共章节时（G2/G3/K1 共用 五、8/八、9）
        后同步的一方会清掉他人刚推的说明，也会清掉审计师在附注模块
        AI 填充/手工编辑的正文。现语义 = **本次没推叙述就不动 `text_content`**。

        清空仍然可达，但必须显式：推 `_note_texts: []` 或 `_removed_text_sections`
        （见 `test_explicit_empty_note_texts_clears_text_content`）。
        """
        _, text, _ = await _run(
            {"sub_table_data": {}},
            {"货币资金": [{"label": "现金"}]},
            existing_text="审计师先前录的说明",
        )
        assert text == "审计师先前录的说明"

    async def test_explicit_empty_note_texts_clears_text_content(self):
        """显式推空叙述（全空文本）→ 如实清空，保持「底稿联动驱动」语义。"""
        _, text, _ = await _run(
            {"sub_table_data": {}},
            {"货币资金": [{"label": "现金"}], "_note_texts": [{"section": "x", "text": "  "}]},
            existing_text="审计师先前录的说明",
        )
        assert text is None

    async def test_removed_table_keys_drops_old_and_protects_pushed(self):
        """删旧表名，但**本次推送的键绝不删**（推送优先）。"""
        td, _, result = await _run(
            {
                "sub_table_data": {"旧表名": [{"label": "a"}], "新表名": [{"label": "b"}]},
                "_sub_table_columns": {"旧表名": [{"key": "label"}]},
            },
            {
                "新表名": [{"label": "b2"}],
                "_removed_table_keys": ["旧表名", "新表名"],
            },
        )
        parsed = json.loads(_canonical(td))
        assert "旧表名" not in parsed["sub_table_data"]
        assert "旧表名" not in parsed["_sub_table_columns"]
        assert parsed["sub_table_data"]["新表名"] == [{"label": "b2"}]  # 推送优先，未被删
        # 🔴 现状契约：被删表名**只进 logger.info，不在返回值里**
        # （`_drop_removed_tables` 返回 dropped 但调用方只 log）。仍未补进返回值 ——
        # 本 spec 只加行级合并两个字段，`dropped_tables` 属另一笔账。
        assert "dropped_tables" not in result
        # 本 spec（disclosure-note-row-level-merge Task 5）additive 加了两个键：
        # `row_scope_unresolved` 必须进返回值而非只进日志 —— fail closed 是静默跳过，
        # 前端据此提示「这张表没同步成功」，否则又是一个 dead path。
        #
        # 2026-08-12 再 additive 加第三个键 `row_scope_unresolved_reasons`
        # （spec `k-cycle-extraction-formula-and-disclosure-closure` Task 15 /
        # Requirement 11.3）：只给表名说不出**为什么**。三种成因修法完全不同
        # —— 准则未设 / 表名与模板不一致 / 模板缺段首码 —— 只报「解析失败」
        # 等于把三条岔路合成一条死胡同，而审计师看不到后端日志。
        assert set(result) == {
            "success", "section_id", "synced_at", "rows_synced",
            "created", "revived", "blocked_by_manual_override", "texts_synced",
            "row_scoped_tables", "row_scope_unresolved",
            "row_scope_unresolved_reasons",
        }
        # 无 `_row_scope` 的载荷三者恒为空（Property 1 的另一面）
        assert result["row_scoped_tables"] == []
        assert result["row_scope_unresolved"] == []
        assert result["row_scope_unresolved_reasons"] == {}

    async def test_metadata_keys_never_counted_as_rows(self):
        """`_` 前缀元数据键不计入 `rows_synced`。"""
        _, _, result = await _run(
            {"sub_table_data": {}},
            {
                "货币资金": [{"label": "现金"}, {"label": "银行存款"}],
                "_note_texts": [{"section": "s", "title": "t", "text": "x"}],
                "_removed_table_keys": ["不存在的表"],
            },
        )
        assert result["rows_synced"] == 2


@pytest.mark.asyncio
class TestCharacterizationRealPayloadShapes:
    """真实循环载荷形态 golden（不自造结构，取自实测落库形态）。"""

    async def test_e1_monetary_fund_soe_shape(self):
        """E1 国企：主表 + ②受限表 + `_note_texts`（2026-08-02 活体实测形态）。"""
        td, text, result = await _run(
            {"sub_table_data": {}},
            {
                "货币资金": [
                    {"label": "现金", "end_amount": 0, "prior_amount": 0},
                    {"label": "银行存款", "end_amount": 327095.2, "prior_amount": 848871.86},
                    {"label": "其他货币资金", "end_amount": 4140440.92, "prior_amount": 52475713.77},
                    {"label": "数字货币", "end_amount": 0, "prior_amount": 0},
                    {"label": "合计", "end_amount": 4467536.12, "prior_amount": 53324585.63,
                     "is_total": True},
                ],
                "受限制的货币资金明细": [
                    {"label": "信用证保证金", "end_amount": 0, "prior_amount": 31250000},
                    {"label": "银行承兑汇票保证金", "end_amount": 4140440.92,
                     "prior_amount": 21225713.77},
                    {"label": "合计", "end_amount": 4140440.92, "prior_amount": 52475713.77,
                     "is_total": True},
                ],
                "_note_texts": [
                    {"section": "soe-restricted", "title": "受限及境外款项说明", "text": "见明细表。"},
                ],
            },
            columns={
                "货币资金": [
                    {"key": "label", "label": "项目", "is_label": True, "flat": True},
                    {"key": "end_amount", "label": "期末余额", "format": "amount"},
                    {"key": "prior_amount", "label": "期初余额", "format": "amount"},
                ],
            },
        )
        assert result["rows_synced"] == 8
        assert text == "【受限及境外款项说明】\n见明细表。"
        parsed = json.loads(_canonical(td))
        assert parsed["_last_sync_sheet"] == "附注披露信息(国企)"   # 半角括号
        assert parsed["_current_standard"] == "soe_standalone"
        assert parsed["_source"] == "workpaper"
        assert set(parsed["sub_table_data"]) == {"货币资金", "受限制的货币资金明细"}
        # 合计行 is_total 与两位小数原样落库（不做四舍五入/不丢字段）
        assert parsed["sub_table_data"]["货币资金"][-1]["is_total"] is True

    async def test_two_level_group_columns_survive(self):
        """H2 范式：两级表头 `group` 原样落库（投影器据此产出 `_column_groups`）。"""
        td, _, _ = await _run(
            {"sub_table_data": {}},
            {"在建工程": [{"label": "厂房", "end_book": 1, "end_impairment": 0, "end_net": 1}]},
            columns={
                "在建工程": [
                    {"key": "label", "label": "项目", "is_label": True, "flat": True},
                    {"key": "end_book", "label": "账面余额", "group": "期末余额"},
                    {"key": "end_impairment", "label": "减值准备", "group": "期末余额"},
                    {"key": "end_net", "label": "账面价值", "group": "期末余额"},
                ]
            },
        )
        cols = json.loads(_canonical(td))["_sub_table_columns"]["在建工程"]
        assert [c.get("group") for c in cols] == [None, "期末余额", "期末余额", "期末余额"]


@pytest.mark.asyncio
class TestReverseSelfCheck:
    """反向自检：证明上面的 golden 不是恒真。"""

    async def test_wrong_impl_whole_replace_would_break_golden(self):
        """若把表级浅合并改成**整体替换**，「未推送表保留」的 golden 必须不成立。

        这里不改生产代码，而是就地模拟错误实现，断言它与正确输出**不同** ——
        证明 `test_shallow_merge_keeps_unpushed_table` 有鉴别力。
        """
        existing_sub = {
            "在建工程": [{"label": "厂房", "end_book": 100}],
            "工程物资": [{"label": "专用材料", "end_book": 1}],
        }
        incoming = {"工程物资": [{"label": "专用设备", "end_book": 2}]}

        # 正确实现（浅合并）
        td, _, _ = await _run({"sub_table_data": dict(existing_sub)}, dict(incoming))
        correct = json.loads(_canonical(td))["sub_table_data"]

        # 错误实现（整体替换）
        wrong = dict(incoming)

        assert correct != wrong
        assert "在建工程" in correct and "在建工程" not in wrong

    async def test_volatile_filter_actually_removes_timestamp(self):
        """反向自检：`_canonical` 必须真的剔掉时间戳（否则 golden 每次都会变）。"""
        td, _, _ = await _run({"sub_table_data": {}}, {"表": [{"label": "a"}]})
        assert "_last_sync_at" in td, "服务端应写入同步时间戳"
        assert "_last_sync_at" not in json.loads(_canonical(td))
