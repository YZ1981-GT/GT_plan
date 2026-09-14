"""母公司附注章节取数守卫（Property 19 / 20 / 21 / 22 / 23 + 零回归 characterization）。

被测真源两处：

- ``app/services/parent_company_note_sections.py``（Task 12/13 新建的判定与口径切换）
- ``app/services/disclosure_engine.py``（三处 resolver ctx 构造收敛到
  ``_build_resolver_ctx``；legacy 与 binding 两条路径都换取数源）

五组判据：

1. **Property 19（需求 8.1 / 10.4）** ``variant_matrix`` 的母公司维度是 additive ——
   只新增顶层 ``parent_company_sections``、不新增第五个变体键、102 个科目的
   ``variants`` 取值逐字不变。
2. **Property 20（需求 8.2）** 母公司章取数指向 ``resolve_parent_standalone_project()``
   返回的项目 id，而非合并项目自身；且**本层不重写三条件**（源码级断言 engine 与
   note_sections 都不自己拼 ``company_code``/``audit_year``/``report_scope`` 查询）。
3. **Property 22（需求 8.4）** 兄弟项目缺失 → ``_tb_cache`` 置空 + 标
   ``parent_project_missing``，金额产出 ``None`` 而非 0。**这条是本 spec 最硬的红线** ——
   「回落合并数」比「取不到」更坏，故配一条反向自检复现旧行为必红。
4. **Property 23（需求 8.5）** 载荷含来源项目名 / 企业代码 / 口径三项。
5. **零回归 characterization** 非母公司章的 ctx 与 table_data 与改造前**逐键相同**
   （母公司章判定不命中时不得多出任何键、不得少查任何缓存）。

Property 21（``report_row_code`` 实证对账）的结构侧判据在
``fix_note_parent_company_chapter.py --check``（Task 11 已落地，本文件只断言
「该 check 覆盖 report_row_code」以防它被静默摘掉）。

Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 10.3, 10.4
"""

from __future__ import annotations

import inspect
import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest

import app.services.disclosure_engine as de_mod
import app.services.parent_company_note_sections as pcns
from app.services.disclosure_engine import DisclosureEngine
from app.services.parent_company_note_sections import (
    PARENT_PROJECT_MISSING_KEY,
    PARENT_SECTIONS_FIELD,
    PARENT_SOURCE_META_KEY,
    PARENT_SOURCE_META_KEYS,
    ParentCompanySource,
    ParentScopeCache,
    build_parent_source_meta,
    is_parent_company_section,
    load_parent_company_sections,
    parent_source_payload,
)

# ─────────────────────── 源码定位（哨兵校验，不写死回退级数） ───────────────────────

_PCNS_FILE = inspect.getsourcefile(pcns)
assert _PCNS_FILE, "无法定位 parent_company_note_sections 源文件"
_PCNS_SRC = Path(_PCNS_FILE).read_text(encoding="utf-8")

_DE_FILE = inspect.getsourcefile(de_mod)
assert _DE_FILE, "无法定位 disclosure_engine 源文件"
_DE_SRC = Path(_DE_FILE).read_text(encoding="utf-8")
assert "_build_resolver_ctx" in _DE_SRC, "读到的 disclosure_engine 源码不含被测方法（路径解析失效）"

_BACKEND = Path(_DE_FILE).resolve().parents[2]
assert (_BACKEND / "data").is_dir(), f"backend 根定位失败：{_BACKEND}"

_MATRIX_PATH = _BACKEND / "data" / "note_template_variant_matrix.json"
_FIX_SCRIPT = _BACKEND / "scripts" / "fix" / "fix_note_parent_company_chapter.py"

_MATRIX = json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))
_ACCOUNTS: list[dict[str, Any]] = _MATRIX["accounts"]

_VARIANT_KEYS = (
    "soe_standalone",
    "soe_consolidated",
    "listed_standalone",
    "listed_consolidated",
)


def _strip_comments(src: str) -> str:
    """剥三引号串与 ``#`` 行注释。

    两个被测模块的注释里逐字写着 ``report_scope`` / ``company_code`` /
    ``parent_project_missing`` 等（正是要断言「代码里没有」的字样），不剥离会让
    「本层不重写三条件」这类断言恒红。
    """
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    return re.sub(r"(?m)#.*$", "", out)


_PCNS_CODE = _strip_comments(_PCNS_SRC)
_DE_CODE = _strip_comments(_DE_SRC)


_TOP_DEF_RE = re.compile(r"(?m)^(?:async\s+)?def\s+")
_METHOD_DEF_RE = re.compile(r"(?m)^    (?:async\s+)?def\s+")


def _method_body(src: str, name: str) -> str:
    """按「``def X`` 到下一个同缩进方法定义」切片（禁固定字符窗口）。"""
    head = re.search(rf"(?m)^    (?:async\s+)?def\s+{re.escape(name)}\s*\(", src)
    if head is None:
        raise AssertionError(f"未找到方法 {name}（切片判据失效）")
    nxt = _METHOD_DEF_RE.search(src, head.end())
    body = src[head.start() : nxt.start() if nxt else len(src)]
    assert body.strip(), f"{name} 的方法体切片为空（正则失效）"
    assert len(body.splitlines()) > 3, f"{name} 的方法体切片过短：{body!r}"
    return body


# ─────────────────────── 替身（不连库） ───────────────────────


class _FakeTrialRow:
    def __init__(self, code: str, name: str, audited: float, opening: float) -> None:
        self.standard_account_code = code
        self.account_code = code
        self.account_name = name
        self.standard_account_name = name
        self.audited_amount = audited
        self.unadjusted_amount = audited
        self.opening_balance = opening


class _FakeScalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


class _RecordingSession:
    """记录 execute 次数并按调用序返回预设结果。"""

    def __init__(self, results: list[list[Any]]) -> None:
        self._results = list(results)
        self.calls = 0

    async def execute(self, stmt):  # noqa: ANN001 - 替身
        self.calls += 1
        rows = self._results.pop(0) if self._results else []
        return _FakeResult(rows)

    async def rollback(self) -> None:  # pragma: no cover - 替身
        return None


def _engine(session: Any) -> DisclosureEngine:
    eng = DisclosureEngine(session)
    eng._tb_cache = {"货币资金": {"audited": 100.0, "unadjusted": 100.0, "opening": 90.0}}
    eng._wp_cache = {"E1": {"audited": 7.0, "unadjusted": 7.0, "opening": None}}
    eng._wp_account_cache = {"E1": "货币资金"}
    eng._wp_fine_cache = {"E1": {"rows": {}}}
    eng._prior_notes_cache = {}
    return eng


def _scope(*, consolidated: bool, parent_id: uuid.UUID | None) -> ParentScopeCache:
    src = (
        ParentCompanySource(parent_id, "甲公司（母公司）", "91330000X", False)
        if parent_id is not None
        else ParentCompanySource(None, None, None, True)
    )
    return ParentScopeCache(uuid.uuid4(), 2025, consolidated, src)


# 一个真实存在的母公司章节号（listed 侧），与 matrix 取值逐字一致
_PARENT_SECTION = "十六、应收账款"
_NON_PARENT_SECTION = "五、5"


# ─────────────────── Property 19：variant_matrix 母公司维度 additive ───────────────────


class TestProperty19MatrixAdditive:
    def test_account_count_unchanged(self) -> None:
        assert len(_ACCOUNTS) == 102, f"科目数应为 102，实为 {len(_ACCOUNTS)}"

    def test_no_fifth_variant_key(self) -> None:
        """不得新增第五个变体键（会波及 102 科目 × 全部消费方）。"""
        for acct in _ACCOUNTS:
            keys = set(acct.get("variants", {}))
            extra = keys - set(_VARIANT_KEYS)
            assert not extra, f"{acct['account_key']} 的 variants 多出键：{sorted(extra)}"

    def test_parent_field_only_on_parent_chapter_accounts(self) -> None:
        """带 ``parent_company_sections`` 的科目 == 母公司章覆盖的 7 个科目。"""
        with_field = {
            a["account_key"] for a in _ACCOUNTS if a.get(PARENT_SECTIONS_FIELD)
        }
        assert with_field == {
            "ying_shou_piao_ju",
            "ying_shou_zhang_kuan",
            "qi_ta_ying_shou_kuan",
            "chang_qi_gu_quan_tou_zi",
            "ying_ye_shou_ru_ying_ye_cheng_ben",
            "tou_zi_shou_yi",
            "xian_jin_liu_liang_biao_bu_chong_zi_liao",
        }, sorted(with_field)

    def test_parent_field_values_are_non_empty_strings(self) -> None:
        for acct in _ACCOUNTS:
            sections = acct.get(PARENT_SECTIONS_FIELD)
            if not sections:
                continue
            assert isinstance(sections, dict), acct["account_key"]
            assert set(sections) <= {"listed", "soe"}, sorted(sections)
            for variant, code in sections.items():
                assert isinstance(code, str) and code.strip(), (
                    f"{acct['account_key']}/{variant} 取值为空（应缺省整个键而不是留空串）"
                )

    def test_loader_returns_both_variants_non_empty(self) -> None:
        sections = load_parent_company_sections()
        assert set(sections) == {"listed", "soe"}
        assert len(sections["listed"]) == 6, sorted(sections["listed"])
        assert len(sections["soe"]) == 6, sorted(sections["soe"])

    def test_two_variants_have_no_overlap(self) -> None:
        """两版章节号集合交集为空 —— 缺省 template_type 的并集判定才无歧义。"""
        sections = load_parent_company_sections()
        assert not (sections["listed"] & sections["soe"])

    def test_asymmetry_preserved(self) -> None:
        """listed 独有应收票据、soe 独有现金流量表补充资料（两版不对称，禁对齐）。"""
        sections = load_parent_company_sections()
        assert "十六、应收票据" in sections["listed"]
        assert not any("应收票据" in c for c in sections["soe"])
        assert any("现金流量表补充资" in c for c in sections["soe"])
        assert not any("现金流量表补充资" in c for c in sections["listed"])


# ─────────────────── 章节判定：逐字相等，禁前缀/包含匹配 ───────────────────


class TestSectionMatching:
    @pytest.mark.parametrize(
        "code",
        [
            "十六、应收票据",
            "十六、应收账款",
            "十六、其他应收款",
            "十六、长期股权投资",
            "十六、营业收入与营业成本",
            "十六、投资收益（注：以",
            "十二、应收账款",
            "十二、其他应收款",
            "十二、长期股权投资",
            "十二、营业收入与营业成本",
            "十二、投资收益",
            "十二、现金流量表补充资",
        ],
    )
    def test_parent_sections_recognized(self, code: str) -> None:
        assert is_parent_company_section(code) is True

    @pytest.mark.parametrize(
        "code",
        [
            None,
            "",
            "   ",
            "五、5",
            "八、9",
            "十二、股份支付总体情况",
            "十六、",
        ],
    )
    def test_non_parent_sections_rejected(self, code: str | None) -> None:
        assert is_parent_company_section(code) is False

    def test_truncated_code_requires_exact_match(self) -> None:
        """md 截断值必须逐字命中；补全的「完整」写法**不算**母公司章。

        listed 投资收益的 section_number 实测是 ``十六、投资收益（注：以``；
        若判定放宽成前缀/包含，``十二、投资收益`` 会被 listed 集合误命中（串章）。
        """
        assert is_parent_company_section("十六、投资收益（注：以") is True
        assert is_parent_company_section("十六、投资收益") is False
        assert is_parent_company_section("十六、投资收益（注：以下不存在的项目可以删除）") is False

    def test_variant_scoped_lookup(self) -> None:
        assert is_parent_company_section("十六、应收票据", "listed") is True
        assert is_parent_company_section("十六、应收票据", "soe") is False
        assert is_parent_company_section("十二、应收账款", "soe") is True
        assert is_parent_company_section("十二、应收账款", "listed") is False

    def test_source_code_has_no_prefix_matching(self) -> None:
        """源码级：判定不得用 startswith / in-substring（会串章）。

        🔴 判据必须写成 ``\\bin\\s+code\\b`` 而不是裸子串 ``"in code"`` ——
        后者会被**合法的集合成员判定** ``code in codes`` 命中（``"code in codes"``
        含子串 ``"in code"``），于是这条断言对正确实现恒红、对错误实现也红，
        等于零信号。词边界版本只命中 ``xxx in code``（把章节号当字符串做子串
        包含，会让 ``十二、投资收益`` 命中 ``十六、投资收益（注：以``）。
        """
        body = _method_body(
            _PCNS_CODE.replace("def is_parent", "    def is_parent"),
            "is_parent_company_section",
        )
        assert "startswith" not in body, "章节判定不得用前缀匹配"
        assert "endswith" not in body, "章节判定不得用后缀匹配"
        assert re.search(r"\bin\s+code\b", body) is None, (
            "章节判定不得用子串包含匹配（`x in code` 把章节号当字符串搜）"
        )

    def test_prefix_matching_predicate_is_not_vacuous(self) -> None:
        """反向自检：上一条的判据对「真用了子串匹配」的实现必须打红。

        若判据写错（如漏词边界或正则失效），本条会通过而上一条恒绿 ⇒ 空转。
        """
        mutated = (
            "    def is_parent_company_section(note_section, template_type=None):\n"
            "        code = (note_section or '').strip()\n"
            "        sections = load_parent_company_sections()\n"
            "        return any(c in code for c in sections)\n"
        )
        body = _method_body(mutated, "is_parent_company_section")
        assert re.search(r"\bin\s+code\b", body) is not None, (
            "判据对子串匹配实现未打红 ⇒ 上一条断言是空转"
        )
        # 同时证明合法的集合成员判定不会被误伤
        legit = (
            "    def is_parent_company_section(note_section, template_type=None):\n"
            "        code = (note_section or '').strip()\n"
            "        sections = load_parent_company_sections()\n"
            "        return any(code in codes for codes in sections.values())\n"
        )
        assert re.search(r"\bin\s+code\b", _method_body(legit, "is_parent_company_section")) is None, (
            "判据误伤合法的 `code in codes` 集合成员判定"
        )


# ─────────────────── Property 20：取数指向母公司单体项目 ───────────────────


class TestProperty20SwitchesProject:
    @pytest.mark.asyncio
    async def test_parent_section_switches_project_id_and_tb_cache(self) -> None:
        parent_id = uuid.uuid4()
        # 第一次 execute = _parent_tb_cache 查母公司单体的 trial_balance
        session = _RecordingSession([[_FakeTrialRow("1122", "应收账款", 55.0, 44.0)]])
        eng = _engine(session)
        eng._parent_scope_cache = _scope(consolidated=True, parent_id=parent_id)

        ctx = await eng._build_resolver_ctx(
            eng._parent_scope_cache.project_id, 2025, _PARENT_SECTION
        )

        assert ctx["project_id"] == parent_id, "母公司章的取数 project_id 应换成母公司单体项目"
        assert ctx["_tb_cache"] == {
            "应收账款": {"audited": 55.0, "unadjusted": 55.0, "opening": 44.0},
            "1122": {"audited": 55.0, "unadjusted": 55.0, "opening": 44.0},
        }
        assert PARENT_PROJECT_MISSING_KEY not in ctx

    @pytest.mark.asyncio
    async def test_tb_cache_projection_matches_preload_shape(self) -> None:
        """母公司 tb 缓存的键与字段须与 ``_preload_data_for_notes`` 逐键一致。"""
        session = _RecordingSession([[_FakeTrialRow("1122", "应收账款", 1.0, 2.0)]])
        eng = _engine(session)
        cache = await eng._parent_tb_cache(uuid.uuid4(), 2025)
        assert set(cache) == {"1122", "应收账款"}
        assert set(cache["1122"]) == {"audited", "unadjusted", "opening"}

    @pytest.mark.asyncio
    async def test_parent_tb_cache_is_memoized(self) -> None:
        parent_id = uuid.uuid4()
        session = _RecordingSession([[_FakeTrialRow("1122", "应收账款", 1.0, 2.0)]])
        eng = _engine(session)
        first = await eng._parent_tb_cache(parent_id, 2025)
        second = await eng._parent_tb_cache(parent_id, 2025)
        assert first is second
        assert session.calls == 1, "同一 (project, year) 不应重复查库"

    @pytest.mark.asyncio
    async def test_scope_cache_reused_across_sections(self) -> None:
        parent_id = uuid.uuid4()
        session = _RecordingSession(
            [
                [_FakeTrialRow("1122", "应收账款", 1.0, 2.0)],
                [_FakeTrialRow("1122", "应收账款", 1.0, 2.0)],
            ]
        )
        eng = _engine(session)
        scope = _scope(consolidated=True, parent_id=parent_id)
        eng._parent_scope_cache = scope
        await eng._build_resolver_ctx(scope.project_id, 2025, "十六、应收账款")
        await eng._build_resolver_ctx(scope.project_id, 2025, "十六、其他应收款")
        assert eng._parent_scope_cache is scope, "口径缓存应被复用（每实例只解析一次）"

    def test_engine_does_not_reimplement_locator_conditions(self) -> None:
        """本层不得自己拼 ``(company_code, audit_year, report_scope)`` 三条件。

        定位口径必须完全由 ``parent_company_scope`` helper 承担，否则报表侧与附注侧
        会各有一套判据（需求 7 的单一真源被破坏）。
        """
        for field in ("company_code", "audit_year", "report_scope"):
            assert f"Project.{field}" not in _DE_CODE, (
                f"disclosure_engine 不应自己查询 Project.{field}（应委托 helper）"
            )

    def test_note_sections_delegates_to_shared_helper(self) -> None:
        assert "resolve_parent_standalone_project" in _PCNS_CODE
        for field in ("Project.company_code", "Project.audit_year", "Project.report_scope"):
            assert field not in _PCNS_CODE, (
                f"parent_company_note_sections 不应自己拼 {field}（应委托 helper）"
            )


# ─────────────────── Property 22：缺失留空不填零（本 spec 最硬红线） ───────────────────


class TestProperty22MissingLeavesBlank:
    @pytest.mark.asyncio
    async def test_missing_sibling_blanks_tb_cache_and_flags(self) -> None:
        session = _RecordingSession([])
        eng = _engine(session)
        eng._parent_scope_cache = _scope(consolidated=True, parent_id=None)

        ctx = await eng._build_resolver_ctx(
            eng._parent_scope_cache.project_id, 2025, _PARENT_SECTION
        )

        assert ctx["_tb_cache"] == {}, "兄弟项目缺失时必须清空 tb 缓存（否则显示合并数）"
        assert ctx[PARENT_PROJECT_MISSING_KEY] is True
        assert session.calls == 0, "缺失时不应再查任何 trial_balance"

    @pytest.mark.asyncio
    async def test_missing_sibling_does_not_fall_back_to_consolidated(self) -> None:
        """反向自检：复现「保留合并缓存」的旧行为必须能被本判据抓住。"""
        session = _RecordingSession([])
        eng = _engine(session)
        consolidated_cache = dict(eng._tb_cache)
        eng._parent_scope_cache = _scope(consolidated=True, parent_id=None)

        ctx = await eng._build_resolver_ctx(
            eng._parent_scope_cache.project_id, 2025, _PARENT_SECTION
        )
        assert ctx["_tb_cache"] != consolidated_cache, (
            "母公司章回落合并项目缓存 = 显示错数，比取不到更坏"
        )

    @pytest.mark.asyncio
    async def test_empty_tb_cache_yields_none_not_zero(self) -> None:
        """空缓存经 resolver 产出 ``None``（不是 0）—— 需求 8.4 的行为侧证据。"""
        from app.services.note_source_resolvers import resolve_trial_balance

        val = await resolve_trial_balance(
            {"account_codes": ["1122"], "field": "audited_amount"},
            {"_tb_cache": {}},
        )
        assert val is None, "空 tb 缓存必须返回 None，返回 0 会把「未建母公司单体」显示成零余额"

    @pytest.mark.asyncio
    async def test_scope_resolution_failure_also_blanks(self) -> None:
        class _Boom:
            async def execute(self, stmt):  # noqa: ANN001
                raise RuntimeError("db down")

            async def rollback(self) -> None:
                return None

        eng = _engine(_Boom())
        ctx = await eng._build_resolver_ctx(uuid.uuid4(), 2025, _PARENT_SECTION)
        assert ctx["_tb_cache"] == {}
        assert ctx[PARENT_PROJECT_MISSING_KEY] is True

    @pytest.mark.asyncio
    async def test_tb_query_failure_blanks_cache(self) -> None:
        class _BoomOnSecond:
            def __init__(self) -> None:
                self.calls = 0

            async def execute(self, stmt):  # noqa: ANN001
                self.calls += 1
                raise RuntimeError("tb query failed")

            async def rollback(self) -> None:
                return None

        eng = _engine(_BoomOnSecond())
        cache = await eng._parent_tb_cache(uuid.uuid4(), 2025)
        assert cache == {}, "母公司 tb 查询失败时必须留空，不得回落合并缓存"


# ─────────────────── Property 23：溯源三项 ───────────────────


class TestProperty23Provenance:
    def test_payload_has_three_keys(self) -> None:
        src = ParentCompanySource(uuid.uuid4(), "甲公司（母公司）", "91330000X", False)
        payload = parent_source_payload(src)
        for key in PARENT_SOURCE_META_KEYS:
            assert key in payload, f"溯源载荷缺 {key}"
        assert payload["source_project_name"] == "甲公司（母公司）"
        assert payload["source_company_code"] == "91330000X"
        assert payload["source_scope"] == "standalone"
        assert PARENT_PROJECT_MISSING_KEY not in payload

    def test_missing_payload_marks_flag_and_nulls_scope(self) -> None:
        payload = parent_source_payload(ParentCompanySource(None, None, None, True))
        assert payload[PARENT_PROJECT_MISSING_KEY] is True
        assert payload["source_scope"] is None
        assert payload["source_project_name"] is None

    def test_meta_keys_tuple_matches_payload(self) -> None:
        """常量与实际键集交叉锁死（防改一处漏一处）。"""
        payload = parent_source_payload(
            ParentCompanySource(uuid.uuid4(), "X", "Y", False)
        )
        assert set(PARENT_SOURCE_META_KEYS) == set(payload)

    def test_build_from_scope_delegates(self) -> None:
        scope = _scope(consolidated=True, parent_id=uuid.uuid4())
        assert build_parent_source_meta(scope) == parent_source_payload(scope.source)

    @pytest.mark.asyncio
    async def test_ctx_carries_meta_for_parent_section(self) -> None:
        session = _RecordingSession([[_FakeTrialRow("1122", "应收账款", 1.0, 2.0)]])
        eng = _engine(session)
        eng._parent_scope_cache = _scope(consolidated=True, parent_id=uuid.uuid4())
        ctx = await eng._build_resolver_ctx(
            eng._parent_scope_cache.project_id, 2025, _PARENT_SECTION
        )
        meta = ctx[PARENT_SOURCE_META_KEY]
        assert meta["source_scope"] == "standalone"
        assert meta["source_company_code"] == "91330000X"

    def test_attach_meta_writes_table_level_only(self) -> None:
        table = {"headers": ["项目"], "rows": [{"label": "x", "values": [1]}]}
        before_rows = json.dumps(table["rows"], ensure_ascii=False)
        DisclosureEngine._attach_parent_source_meta(
            table,
            {PARENT_SOURCE_META_KEY: {"source_scope": "standalone"}},
        )
        assert table[PARENT_SOURCE_META_KEY] == {"source_scope": "standalone"}
        assert json.dumps(table["rows"], ensure_ascii=False) == before_rows, (
            "溯源只落表级，不得改 rows（行结构归结构任务所有）"
        )

    def test_attach_meta_is_noop_without_keys(self) -> None:
        table = {"headers": [], "rows": []}
        DisclosureEngine._attach_parent_source_meta(table, {"project_id": uuid.uuid4()})
        assert table == {"headers": [], "rows": []}, "非母公司章必须是空操作"

    def test_attach_meta_marks_missing(self) -> None:
        table: dict[str, Any] = {"headers": [], "rows": []}
        DisclosureEngine._attach_parent_source_meta(
            table, {PARENT_PROJECT_MISSING_KEY: True}
        )
        assert table[PARENT_PROJECT_MISSING_KEY] is True

    def test_both_build_paths_attach_meta(self) -> None:
        """binding 与 legacy 两条路径都必须落溯源（母公司 7 子节里 5 个走 legacy）。"""
        hits = len(re.findall(r"_attach_parent_source_meta\(", _DE_CODE))
        assert hits >= 3, (
            f"_attach_parent_source_meta 调用点应 ≥3（定义 1 + binding 1 + legacy 1），实为 {hits}"
        )


# ─────────────────── legacy 路径也换取数源（母公司 5 个子节走它） ───────────────────


class TestLegacyPathAlsoSwitched:
    def test_legacy_path_consults_parent_ctx(self) -> None:
        body = _method_body(_DE_CODE, "_build_table_data")
        assert "is_parent_company_section(" in body, (
            "legacy 路径未做母公司章判定 → 营业收入/投资收益/现金流量表补充资料"
            "三个子节会静默显示合并数"
        )
        assert "_build_resolver_ctx(" in body, "legacy 路径应复用同一 ctx 构造（禁两套口径）"

    def test_legacy_path_blanks_wp_caches_for_parent(self) -> None:
        """legacy 路径底稿缓存优先于试算表 → 母公司章必须一并清空。"""
        body = _method_body(_DE_CODE, "_build_table_data")
        idx = body.find("is_parent_company_section(")
        assert idx != -1
        tail = body[idx : idx + 900]
        assert "wp_data = {}" in tail, "母公司章须清空 _wp_cache 投影（否则取合并底稿审定数）"
        assert "wp_fine_cache = {}" in tail, "母公司章须清空 fine 缓存"

    @pytest.mark.asyncio
    async def test_legacy_parent_section_uses_parent_tb(self) -> None:
        session = _RecordingSession([[_FakeTrialRow("1122", "应收账款", 77.0, 66.0)]])
        eng = _engine(session)
        eng._parent_scope_cache = _scope(consolidated=True, parent_id=uuid.uuid4())
        out = await eng._build_table_data(
            eng._parent_scope_cache.project_id,
            2025,
            {
                "headers": ["项目", "期末余额", "期初余额"],
                "rows": [{"label": "应收账款", "account_codes": ["1122"]}],
            },
            section_number="十二、现金流量表补充资",
        )
        assert out is not None
        assert out["rows"][0]["values"][:2] == [77.0, 66.0], "legacy 路径应取母公司单体数"
        assert out[PARENT_SOURCE_META_KEY]["source_scope"] == "standalone"

    @pytest.mark.asyncio
    async def test_legacy_parent_section_missing_yields_none(self) -> None:
        session = _RecordingSession([])
        eng = _engine(session)
        eng._parent_scope_cache = _scope(consolidated=True, parent_id=None)
        out = await eng._build_table_data(
            eng._parent_scope_cache.project_id,
            2025,
            {
                "headers": ["项目", "期末余额", "期初余额"],
                "rows": [{"label": "应收账款", "account_codes": ["1122"]}],
            },
            section_number="十二、现金流量表补充资",
        )
        assert out is not None
        assert out["rows"][0]["values"] == [None, None], "缺母公司单体时必须留 None 不填 0"
        assert out[PARENT_PROJECT_MISSING_KEY] is True


# ─────────────────── 零回归 characterization（Property 28 的取数侧） ───────────────────


class TestZeroRegressionNonParentSections:
    @pytest.mark.asyncio
    async def test_non_parent_ctx_keys_and_values_unchanged(self) -> None:
        session = _RecordingSession([])
        eng = _engine(session)
        pid = uuid.uuid4()

        ctx = await eng._build_resolver_ctx(pid, 2025, _NON_PARENT_SECTION)

        assert set(ctx) == {
            "project_id",
            "year",
            "db",
            "section_number",
            "_tb_cache",
            "_wp_cache",
            "_prior_notes_cache",
        }, sorted(ctx)
        assert ctx["project_id"] == pid
        assert ctx["_tb_cache"] is not None and ctx["_tb_cache"] == eng._tb_cache
        assert ctx["_wp_cache"] == eng._wp_cache
        assert session.calls == 0, "非母公司章不得产生任何额外查询（零回归支点）"

    @pytest.mark.asyncio
    async def test_extra_kwargs_are_passed_through(self) -> None:
        """`_evaluate_note_formulas` 侧的两个额外键必须原样进 ctx。"""
        eng = _engine(_RecordingSession([]))
        sentinel = object()
        ctx = await eng._build_resolver_ctx(
            uuid.uuid4(),
            2025,
            _NON_PARENT_SECTION,
            report_data={"a": 1},
            _cell_binding_resolver=sentinel,
        )
        assert ctx["report_data"] == {"a": 1}
        assert ctx["_cell_binding_resolver"] is sentinel

    @pytest.mark.asyncio
    async def test_section_number_omitted_when_none(self) -> None:
        """`refill_sections` 在循环里才逐 note 设 section_number ⇒ 构造时不得塞 None。"""
        eng = _engine(_RecordingSession([]))
        ctx = await eng._build_resolver_ctx(uuid.uuid4(), 2025, None)
        assert "section_number" not in ctx

    @pytest.mark.asyncio
    async def test_non_consolidated_project_keeps_original_source(self) -> None:
        """母公司章出现在单体项目（存量数据）→ 按原路径取数，不清空、不标缺失。"""
        session = _RecordingSession([])
        eng = _engine(session)
        eng._parent_scope_cache = _scope(consolidated=False, parent_id=None)
        ctx = await eng._build_resolver_ctx(
            eng._parent_scope_cache.project_id, 2025, _PARENT_SECTION
        )
        assert ctx["_tb_cache"] == eng._tb_cache
        assert PARENT_PROJECT_MISSING_KEY not in ctx

    @pytest.mark.asyncio
    async def test_legacy_path_returns_table_for_non_parent_section(self) -> None:
        """🔴 P0 回归钉子：legacy 路径对**非**母公司章必须返回表而不是 None / 抛异常。

        实测过的两个形态（改造中期各触发一次，四层验证全绿）：
        1. `_attach_parent_source_meta` 返回 `None` ⇒ `return self._attach_...(...)`
           让**每一张**无 binding 的表变成 `None` ⇒ 整章表格凭空消失；
        2. 它不容忍 `ctx=None` ⇒ 非母公司章 `parent_ctx` 就是 `None` ⇒
           `AttributeError: 'NoneType' object has no attribute 'get'` ⇒ 全线崩。

        两者都不会被「母公司章」相关断言覆盖，故单列一条。
        """
        eng = _engine(_RecordingSession([]))
        eng._tb_cache = {
            "应收账款": {"audited": 10.0, "unadjusted": 10.0, "opening": 8.0},
        }
        out = await eng._build_table_data(
            uuid.uuid4(),
            2025,
            {
                "headers": ["项目", "期末余额", "期初余额"],
                "rows": [{"label": "应收账款", "account_codes": ["1122"]}],
            },
        )
        assert out is not None, "legacy 路径返回 None ⇒ 整章表格消失"
        assert out["rows"][0]["values"] == [10.0, 8.0], "非母公司章仍按合并项目缓存取数"
        assert PARENT_SOURCE_META_KEY not in out, "非母公司章不得落溯源键（零回归）"
        assert PARENT_PROJECT_MISSING_KEY not in out

    def test_attach_meta_returns_table_and_tolerates_none_ctx(self) -> None:
        """上一条的单元级判据：返回值必须是 table_data 本体，且 ctx=None 不抛。"""
        table = {"headers": ["项目"], "rows": []}
        assert DisclosureEngine._attach_parent_source_meta(table, None) is table
        assert table == {"headers": ["项目"], "rows": []}, "ctx=None 必须是空操作"
        assert DisclosureEngine._attach_parent_source_meta(table, {}) is table

    def test_all_three_ctx_sites_converged(self) -> None:
        """三处 ctx 构造必须都走 ``_build_resolver_ctx``（禁再抄一份字典字面量）。"""
        calls = len(re.findall(r"_build_resolver_ctx\(", _DE_CODE))
        assert calls >= 4, f"应为 1 处定义 + ≥3 处调用，实为 {calls}"
        # 不得再出现「手写 _tb_cache/_wp_cache/_prior_notes_cache 三键字典」
        manual = re.findall(
            r'"_tb_cache":\s*(?:getattr\(self|self\._tb_cache)', _DE_CODE
        )
        assert len(manual) <= 1, (
            f"手写 ctx 字典残留 {len(manual)} 处（应只在 _build_resolver_ctx 内一处）"
        )


# ─────────────────── Property 21 的结构侧覆盖（防 check 被静默摘掉） ───────────────────


class TestProperty21CheckCoverage:
    def test_fix_script_checks_report_row_codes(self) -> None:
        assert _FIX_SCRIPT.is_file(), f"幂等脚本缺失：{_FIX_SCRIPT}"
        src = _FIX_SCRIPT.read_text(encoding="utf-8")
        assert "check_report_row_codes" in src, (
            "幂等脚本的 --check 必须覆盖 report_row_code（Task 11 判据）"
        )
        code = _strip_comments(src)
        assert "check_report_row_codes(d, variant)" in code or "check_report_row_codes(doc" in code, (
            "check_report_row_codes 未被 _checks 真实调用（判据空转）"
        )

    def test_parent_chapter_tables_carry_row_codes(self) -> None:
        """母公司章各子节的主表已按实证对账填 ``report_row_code``。"""
        expected = {
            ("listed", "十六、应收票据"): "BS-005",
            ("listed", "十六、其他应收款"): "BS-009",
            ("listed", "十六、长期股权投资"): "BS-024",
            ("listed", "十六、投资收益（注：以"): "IS-011",
            ("soe", "十二、其他应收款"): "BS-009",
            ("soe", "十二、长期股权投资"): "BS-024",
            ("soe", "十二、投资收益"): "IS-011",
        }
        cache: dict[str, dict[str, list[dict]]] = {}
        for variant in ("listed", "soe"):
            data = json.loads(
                (_BACKEND / "data" / f"note_template_{variant}.json").read_text(
                    encoding="utf-8"
                )
            )
            cache[variant] = {
                str(s.get("section_number") or ""): (s.get("tables") or [])
                for s in data.get("sections") or []
            }

        for (variant, section), want in expected.items():
            tables = cache[variant].get(section)
            assert tables, f"{variant} 缺子节 {section}"
            codes = [t.get("report_row_code") for t in tables if t.get("report_row_code")]
            assert codes == [want], (
                f"{variant}/{section} 的 report_row_code 应恰为 [{want}]，实为 {codes}"
                "（同子节两表填同码会让下游取数双算）"
            )
