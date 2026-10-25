"""单体项目不得出现「合并专属」附注章节 —— 写入口 / 读入口 / 存量清理三处同一判据。

背景（真库实测，2026-09-30）：
Word 权威模板里 ``soe_standalone.docx`` 11 个 H1 **既无**「企业合并及合并财务报表」
**也无**「母公司财务报表的主要项目附注」；``listed_standalone.docx`` 16 个 H1 无
「公司财务报表主要项目注释」但**有**「补充资料」及其 3 个子标题。而种子 JSON 里这
4 个章的一级章节是 ``migrate_note_template_section_id.py`` 合成的，硬编码
``scope="both"`` ⇒ 章自身放行（``section_applies_to_scope`` 逐节扁平、不继承父章）。

叠加三条**从不按口径过滤**的旁路：
  · ``sync_from_workpaper``（底稿披露同步，新建 + 软删行复活）
  · ``WpDisclosureSyncService.sync_from_html``（同上，HTML 渲染器路径）
  · ``DisclosureEngine.get_notes_tree``（目录树读侧，直接返回 DB 行）
⇒ 单体项目里长出并显示合并专属章节（真库 19 行）。

Properties:
- P1 判据本身：soe/listed × standalone/consolidated 四象限逐章判定正确
- P2 fail-open：变体不可判（空 / custom）⇒ 放行，绝不按 soe 口径误杀 listed
- P3 读侧：单体项目目录树不含合并专属章；合并项目照常返回
- P4 写侧（workpaper 路径）：不新建 **且不复活**软删行
- P5 写侧（html 路径）：同 P4
- P6 存量清理：按**项目自身** template_type 选行（listed 的「七」保留、soe 的「七」删）
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote
from app.services.disclosure_engine import DisclosureEngine
from app.services.note_section_catalog import section_allowed_for_project
from app.services.wp_disclosure_sync_service import (
    sync_from_workpaper,
    wp_disclosure_sync_service,
)

PROJECT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WP_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
NOTE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

# 合并专属（Word 单体册里没有这一章）
SOE_CONSOLIDATED_ONLY = ("七", "十二")
LISTED_CONSOLIDATED_ONLY = ("十六",)
# 同号不同义：soe「七」=合并范围的变化（合并专属） / listed「七」=在其他主体中的权益（两册都有）
LISTED_BOTH_SAME_CODE = ("七", "十二")
# 实测 scope=both 的普通章（soe 的 八、90/八、91 种子里本就是 consolidated_only，不可当样本）
ORDINARY_SOE = "八、81"


# ─────────────────────────── P1 / P2：判据本身 ───────────────────────────


class TestSectionAllowedForProject:
    @pytest.mark.parametrize("code", SOE_CONSOLIDATED_ONLY)
    def test_soe_standalone_blocks_consolidated_only_chapter(self, code: str) -> None:
        assert section_allowed_for_project(code, "soe", "standalone") is False

    @pytest.mark.parametrize("code", SOE_CONSOLIDATED_ONLY)
    def test_soe_consolidated_allows_them(self, code: str) -> None:
        assert section_allowed_for_project(code, "soe", "consolidated") is True

    @pytest.mark.parametrize("code", LISTED_CONSOLIDATED_ONLY)
    def test_listed_standalone_blocks_parent_company_chapter(self, code: str) -> None:
        assert section_allowed_for_project(code, "listed", "standalone") is False

    @pytest.mark.parametrize("code", LISTED_BOTH_SAME_CODE)
    def test_listed_standalone_keeps_same_numbered_but_different_chapter(
        self, code: str
    ) -> None:
        """🔴 最贵的一条：两套编号同号不同义。

        soe「七」是合并范围的变化（合并专属），listed「七」是在其他主体中的权益
        （单体册也有）。判据若把 template_type 归一成默认 soe，listed 单体项目的
        这两章会被误杀 —— 真库里它们有 1582 / 1074 字的真实业务内容。
        """
        assert section_allowed_for_project(code, "listed", "standalone") is True

    def test_listed_standalone_keeps_supplementary_children(self) -> None:
        """listed 十七「补充资料」的子节：单体 Word 里有 ⇒ 必须放行（反向缺陷）。"""
        for code in ("十七、1", "十七、2", "十七、3"):
            assert section_allowed_for_project(code, "listed", "standalone") is True

    @pytest.mark.parametrize("variant", [None, "", "  ", "custom", "unknown"])
    def test_unknown_variant_fails_open(self, variant) -> None:
        """P2：变体不可判 ⇒ 放行。猜成 soe 会拿国企编号裁上市 / 自定义模板项目。"""
        for code in (*SOE_CONSOLIDATED_ONLY, *LISTED_CONSOLIDATED_ONLY, ORDINARY_SOE):
            assert section_allowed_for_project(code, variant, "standalone") is True

    def test_empty_report_scope_is_treated_as_standalone(self) -> None:
        """口径缺失按 standalone（与生成链 normalize_report_scope 一致）。"""
        assert section_allowed_for_project("十二", "soe", None) is False
        assert section_allowed_for_project("十二", "soe", "") is False

    def test_ordinary_chapters_are_never_blocked(self) -> None:
        """反向自检：普通章在四象限都放行（否则判据是「全拦」而非「按 scope 拦」）。

        🔴 样本不能随手挑：soe 的 `八、90` / `八、91`（资产负债表中列报项目）种子里
        **本来就是** `consolidated_only`（实测自 e2d6ab449 起一路如此，与本轮改动、
        与 56acf363d 的陈旧覆盖都无关），拿它当"普通章"会得出判据全拦的错结论。
        故用实测 `both` 的 `八、81` / `五、1`。
        """
        for variant, scope in (
            ("soe", "standalone"), ("soe", "consolidated"),
            ("listed", "standalone"), ("listed", "consolidated"),
        ):
            assert section_allowed_for_project(ORDINARY_SOE, variant, scope) is True
            assert section_allowed_for_project("五、1", variant, scope) is True


# ─────────────────────────── P3：读侧目录树 ───────────────────────────


def _note_row(note_section: str) -> SimpleNamespace:
    return SimpleNamespace(
        note_section=note_section,
        id=uuid.uuid4(),
        section_title="标题",
        account_name=None,
        content_type=None,
        status=None,
        sort_order=0,
        is_empty=False,
        text_content="有内容",
        table_data=None,
    )


def _tree(notes: list[SimpleNamespace], template_type, report_scope) -> list[dict]:
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = notes

    async def _execute(*_a, **_k):
        return fake_result

    eng = DisclosureEngine.__new__(DisclosureEngine)
    eng.db = SimpleNamespace(execute=_execute)

    async def _basic_info(_pid):
        return {"template_type": template_type, "report_scope": report_scope}

    eng._get_project_basic_info = _basic_info  # type: ignore[method-assign]
    return asyncio.run(eng.get_notes_tree(PROJECT_ID, 2025))


class TestNotesTreeFiltersByProjectScope:
    def test_soe_standalone_tree_drops_consolidated_only(self) -> None:
        notes = [_note_row(c) for c in (ORDINARY_SOE, "七", "十二")]
        codes = [n["note_section"] for n in _tree(notes, "soe", "standalone")]
        assert codes == [ORDINARY_SOE]

    def test_soe_consolidated_tree_keeps_everything(self) -> None:
        notes = [_note_row(c) for c in (ORDINARY_SOE, "七", "十二")]
        codes = [n["note_section"] for n in _tree(notes, "soe", "consolidated")]
        assert codes == [ORDINARY_SOE, "七", "十二"]

    def test_listed_standalone_drops_only_parent_chapter(self) -> None:
        notes = [_note_row(c) for c in ("五、1", "七", "十二", "十六")]
        codes = [n["note_section"] for n in _tree(notes, "listed", "standalone")]
        assert codes == ["五、1", "七", "十二"], "listed 的七/十二 与 soe 同号不同义"

    def test_unknown_template_type_does_not_filter(self) -> None:
        notes = [_note_row(c) for c in (ORDINARY_SOE, "七", "十二")]
        codes = [n["note_section"] for n in _tree(notes, None, "standalone")]
        assert len(codes) == 3

    def test_basic_info_failure_does_not_empty_the_tree(self) -> None:
        """fail-open：口径解析抛错时退回全量返回，绝不把目录树整棵清空。"""
        fake_result = MagicMock()
        fake_result.scalars.return_value.all.return_value = [
            _note_row(c) for c in (ORDINARY_SOE, "七")
        ]

        async def _execute(*_a, **_k):
            return fake_result

        eng = DisclosureEngine.__new__(DisclosureEngine)
        eng.db = SimpleNamespace(execute=_execute)

        async def _boom(_pid):
            raise RuntimeError("boom")

        eng._get_project_basic_info = _boom  # type: ignore[method-assign]
        tree = asyncio.run(eng.get_notes_tree(PROJECT_ID, 2025))
        assert [n["note_section"] for n in tree] == [ORDINARY_SOE, "七"]


# ─────────────────────── P4：写侧（sync_from_workpaper） ───────────────────────


def _user() -> MagicMock:
    u = MagicMock()
    u.id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    return u


def _scalar_result(value):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=value)
    return res


def _project_row(
    template_type: str | None,
    report_scope: str | None,
    *,
    v2: dict | None = None,
) -> MagicMock:
    """`_resolve_project_sync_facts` 一次取回 (audit_year, v2 准则, template_type, report_scope)。

    ``v2`` 显式传入时**故意与两列不一致** —— 真库项目 0ec33ac9（重药控股安徽_2025）
    正是 ``template_type='listed'`` 而 ``applicable_standard_v2.entity_type='soe'``。
    """
    row = MagicMock()
    row.first = MagicMock(
        return_value=(
            2025,
            v2 if v2 is not None else {"entity_type": template_type, "scope": report_scope},
            template_type,
            report_scope,
        )
    )
    return row


def _soft_deleted(section: str) -> DisclosureNote:
    note = DisclosureNote(
        project_id=PROJECT_ID,
        year=2025,
        note_section=section,
        section_title=section,
        table_data={},
        is_deleted=True,
    )
    note.id = NOTE_ID
    return note


def _wp_db(
    *,
    deleted: DisclosureNote | None,
    template_type: str,
    report_scope: str,
    v2: dict | None = None,
):
    db = MagicMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _project_row(template_type, report_scope, v2=v2),
            _scalar_result(None),          # 无 active 行
            _scalar_result(deleted),       # 软删行（守卫生效时这一次不该被消耗）
        ]
    )
    return db


async def _sync_wp(db, section: str, standard: str):
    return await sync_from_workpaper(
        db,
        PROJECT_ID,
        wp_id=WP_ID,
        sheet_name="X",
        section_id=section,
        sub_table_data={"表": [{"label": "a"}]},
        current_standard=standard,
        user=_user(),
        commit=False,
    )


class TestSyncFromWorkpaperRespectsScope:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("section", SOE_CONSOLIDATED_ONLY)
    async def test_does_not_create_consolidated_only_for_standalone(self, section) -> None:
        db = _wp_db(deleted=None, template_type="soe", report_scope="standalone")
        result = await _sync_wp(db, section, "soe_standalone")

        assert result["success"] is True
        assert result["skipped"] is True
        assert result["reason"] == "section_not_applicable_to_report_scope"
        assert result["created"] is False
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_revive_soft_deleted_consolidated_only(self) -> None:
        """🔴 守卫必须在**复活之前**：否则存量清理软删的行会被下一次底稿保存复活。

        唯一索引 ``uq_disclosure_notes_project_year_section`` 不含 ``is_deleted``
        ⇒ 复活是无 active 行时的必经分支，守卫放它后面等于没放。
        """
        note = _soft_deleted("十二")
        db = _wp_db(deleted=note, template_type="soe", report_scope="standalone")

        result = await _sync_wp(db, "十二", "soe_standalone")

        assert result["skipped"] is True
        assert note.is_deleted is True, "被软删的合并专属章节又被复活了"
        db.add.assert_not_called()
        # 项目行 + active 查询 = 2 次；软删查询**没被发起**（守卫在它之前返回）
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_consolidated_project_still_creates(self) -> None:
        """零回归：合并项目照常新建。"""
        db = _wp_db(deleted=None, template_type="soe", report_scope="consolidated")
        result = await _sync_wp(db, "十二", "soe_consolidated")

        assert result.get("skipped") is not True
        assert result["created"] is True
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_listed_standalone_same_code_still_creates(self) -> None:
        """零回归 + 反向自检：listed 单体的「十二」（股份支付）不该被 soe 口径误杀。"""
        db = _wp_db(deleted=None, template_type="listed", report_scope="standalone")
        result = await _sync_wp(db, "十二", "listed_standalone")

        assert result.get("skipped") is not True
        assert result["created"] is True

    @pytest.mark.asyncio
    async def test_ordinary_section_still_creates_for_standalone(self) -> None:
        db = _wp_db(deleted=None, template_type="soe", report_scope="standalone")
        result = await _sync_wp(db, ORDINARY_SOE, "soe_standalone")

        assert result.get("skipped") is not True
        assert result["created"] is True

    @pytest.mark.asyncio
    async def test_variant_comes_from_columns_not_v2_standard(self) -> None:
        """🔴 变体必须取 ``projects.template_type``，**不是** ``applicable_standard_v2``。

        真库项目 0ec33ac9（重药控股安徽有限公司_2025）两者不一致：列是 ``listed``、
        v2 的 ``entity_type`` 是 ``soe``。按 v2 取就会拿国企编号裁上市项目 ⇒ listed 单体的
        「十二 股份支付」（真库 1074 字）「七 在其他主体中的权益」（1582 字）被误判为
        合并专属而拒写。

        这条用例是变异检验 M10 抓出来的：原先全部 fake 都让两个源**一致**，
        把取数源从列换成 v2 后 30 条判据一条都不红 —— 典型的「mock 只验接线不验语义」。
        """
        for section in LISTED_BOTH_SAME_CODE:
            db = _wp_db(
                deleted=None,
                template_type="listed",
                report_scope="standalone",
                v2={"entity_type": "soe", "scope": "standalone"},
            )
            result = await _sync_wp(db, section, "listed_standalone")
            assert result.get("skipped") is not True, (
                f"listed 单体项目的「{section}」被拦了 ⇒ 变体取的是 v2 而非 template_type 列"
            )
            assert result["created"] is True

    @pytest.mark.asyncio
    async def test_v2_disagreeing_does_not_let_soe_consolidated_only_through(self) -> None:
        """对偶方向：列是 soe 而 v2 说 listed 时，soe 的合并专属章仍须拦住。

        只验一个方向会让「永远放行」也通过（放行在上一条里是期望结果）。
        """
        db = _wp_db(
            deleted=None,
            template_type="soe",
            report_scope="standalone",
            v2={"entity_type": "listed", "scope": "standalone"},
        )
        result = await _sync_wp(db, "十二", "soe_standalone")
        assert result["skipped"] is True
        db.add.assert_not_called()


# ─────────────────────── P5：写侧（sync_from_html） ───────────────────────


def _html_db(*, deleted: DisclosureNote | None, template_type: str, report_scope: str):
    db = MagicMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _project_row(template_type, report_scope),   # _resolve_target_year
            _project_row(template_type, report_scope),   # _resolve_project_sync_facts（守卫）
            _scalar_result(deleted),                     # 软删行（守卫生效时不该被消耗）
        ]
    )
    return db


class TestSyncFromHtmlRespectsScope:
    @pytest.mark.asyncio
    async def test_skips_consolidated_only_for_standalone(self) -> None:
        db = _html_db(deleted=None, template_type="soe", report_scope="standalone")
        service = wp_disclosure_sync_service

        async def _mapping(*_a, **_k):
            return {"section_id": "十二", "last_sync_at": None}

        async def _get_note(*_a, **_k):
            return None

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(service, "_get_section_mapping", _mapping)
            mp.setattr(service, "_get_note", _get_note)
            result = await service.sync_from_html(
                db, wp_id=WP_ID, sheet_name="母公司附注",
                sub_table_data={"t": [{"v": 1}]},
                project_id=PROJECT_ID, user=_user(),
            )

        assert result["success"] is True
        assert result["synced"] is False
        assert result["reason"] == "section_not_applicable_to_report_scope"
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_revive_soft_deleted(self) -> None:
        note = _soft_deleted("十二")
        db = _html_db(deleted=note, template_type="soe", report_scope="standalone")
        service = wp_disclosure_sync_service

        async def _mapping(*_a, **_k):
            return {"section_id": "十二", "last_sync_at": None}

        async def _get_note(*_a, **_k):
            return None

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(service, "_get_section_mapping", _mapping)
            mp.setattr(service, "_get_note", _get_note)
            result = await service.sync_from_html(
                db, wp_id=WP_ID, sheet_name="母公司附注",
                sub_table_data={"t": [{"v": 1}]},
                project_id=PROJECT_ID, user=_user(),
            )

        assert result["synced"] is False
        assert note.is_deleted is True, "html 路径把软删的合并专属章节复活了"


# ─────────────────────── 源码级：守卫必须在复活之前 ───────────────────────


class TestGuardIsBeforeReviveInSource:
    """位置判据：守卫早于复活。行为判据已在 P4/P5 覆盖，这条防「重构时顺手挪位置」。"""

    def test_workpaper_path_guard_precedes_revive(self) -> None:
        import inspect

        from app.services import wp_disclosure_sync_service as svc

        src = inspect.getsource(svc.sync_from_workpaper)
        guard_at = src.index("_section_blocked_for_project(")
        revive_at = src.index("DisclosureNote.is_deleted == sa.true()")
        assert guard_at < revive_at, (
            "口径守卫落在软删复活之后 ⇒ 存量清理软删的章节会被下次同步复活"
        )

    def test_html_path_guard_precedes_revive(self) -> None:
        import inspect

        from app.services.wp_disclosure_sync_service import WpDisclosureSyncService

        src = inspect.getsource(WpDisclosureSyncService.sync_from_html)
        guard_at = src.index("_section_blocked_for_project(")
        revive_at = src.index("DisclosureNote.is_deleted == sa.true()")
        assert guard_at < revive_at


# ─────────────────── 权威源守卫：Word 事实 + 模板不变量 ───────────────────


class TestScopeTruthAgainstWordTemplates:
    """scope 的判据真源是 **Word 权威模板**（单体册有没有这个 Heading 1），不是标题启发式。

    这三条把 `scripts/fix/fix_note_chapter_scope.py` 的 `--check` 搬进测试面：CI 那边也挂了
    同一个脚本，但只有 CI 挂着的门禁，在本机改模板时不会当场红。
    """

    @staticmethod
    def _module():
        import importlib.util
        import sys
        from pathlib import Path

        path = (
            Path(__file__).resolve().parent.parent
            / "scripts" / "fix" / "fix_note_chapter_scope.py"
        )
        assert path.is_file(), f"脚本不在：{path}"
        spec = importlib.util.spec_from_file_location("_fix_note_chapter_scope", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_word_facts_still_support_the_registries(self) -> None:
        """两张登记表的每一条都仍被 Word 支持（Word 或登记表一改即红）。"""
        mod = self._module()
        errs = mod.check_word_facts()
        assert not errs, "Word 事实与登记表不符：\n  " + "\n  ".join(errs)

    def test_registries_are_not_empty(self) -> None:
        """反向自检：登记表非空。空表会让上面那条恒绿（一条都不校验）。"""
        mod = self._module()
        assert mod.CHAPTER_ONLY_IN_CONSOLIDATED, "consolidated_only 登记表空 ⇒ 判据空转"
        assert mod.CHAPTER_IN_BOTH, "both 登记表空 ⇒ 判据空转"

    def test_templates_have_no_scope_debt(self) -> None:
        """两份种子都无欠账：章与全部后代 scope 自洽（= 脚本 --check 的退出码判据）。"""
        import json

        mod = self._module()
        problems: list[str] = []
        for variant, path in mod.TEMPLATES.items():
            doc = json.loads(path.read_text(encoding="utf-8"))
            changes, structural = mod.plan(doc, variant)
            problems += [f"[{variant}] 待改 {old}→{new}: {s.get('section_number')}"
                         for s, old, new in changes]
            problems += [f"[{variant}] {e}" for e in structural]
            problems += [f"[{variant}] {e}" for e in mod.check_invariants(doc, variant)]
        assert not problems, "种子 scope 仍有欠账：\n  " + "\n  ".join(problems)
