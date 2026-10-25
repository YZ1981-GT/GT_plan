"""披露同步不变量守卫 — 六项

spec: disclosure-payload-authority-source / Task 3.1~3.6 / Q6 Q8 Q9 Q10

3.1 跨主体零写入（Q8）
3.2 空载荷不清表（Q9）
3.3 manual_override 保护
3.4 年度权威
3.5 变体不串写（Q6）
3.6 注册表一致性 CI（Q10）
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

# ══════════════════════════════════════════════════════════════════════════
# 3.1 跨主体零写入
# ══════════════════════════════════════════════════════════════════════════


class TestCrossEntityGuard:
    """跨主体同步守卫 —— 🔴 spec 需求 5.1 / Q8 与实现冲突，此处如实记录真实行为。

    ## 勘误（复盘 P0-4）

    spec 需求 5.1 与 Q8 写「国企项目请求上市章节 SHALL 被**拒绝**且零写入」。
    **该需求写错了** —— 现读 `standard_unification_service.detect_standard_conflict`
    源码明载用户裁决：

        🔴 用户裁决（2026-08-16）：底稿不做准则门控，允许在国企项目编辑上市版披露
        （合并模块场景：集团国企，下属有上市子公司）。entity 冲突降级为 warning
        放行，不再 hard block。

    探针穷举 162 组 (project_entity × requested) 组合，``detect_standard_conflict``
    **恒返回 None** ⇒ ``_guard_standard_matches_project`` 里的
    ``raise StandardMismatchError`` 分支是**死代码**。

    ⚠️ 首版本类把测试降级成「调用不抛异常就 pass」= 恒绿空转，
    掩盖了「spec 需求与已裁决设计冲突」这一真问题。本版改为：
      · 如实断言当前设计（放行 + 必留 warning 日志）
      · 用 ``xfail(strict=True)`` 钉住需求 5.1 的原始诉求 ——
        若未来有人把实现收紧为 hard block，该测试会 XPASS，
        strict 模式下 XPASS **算失败** ⇒ 强制回来更新 spec，不会静默漂移。
    """

    def test_conflict_detector_never_blocks_by_design(self):
        """如实断言：entity 冲突不被拦截（2026-08-16 用户裁决的放行设计）。"""
        from app.services.standard_unification_service import detect_standard_conflict

        # 国企项目请求上市口径 —— 真实污染场景，但按裁决放行
        assert detect_standard_conflict({"entity_type": "soe"}, "listed_standalone") is None
        assert detect_standard_conflict({"entity_type": "listed"}, "soe_standalone") is None

    def test_cross_entity_must_leave_warning_log(self, caplog):
        """🔴 放行但**必须留痕**：跨主体调用须产出 warning 日志。

        这是当前设计下唯一可验证的实质不变量 —— 放行可以，静默不行
        （审计场景必须能事后追溯谁在国企项目写了上市章节）。
        """
        from app.services.wp_disclosure_sync_service import (
            _guard_standard_matches_project,
        )

        caplog.clear()
        with caplog.at_level(logging.WARNING):
            _guard_standard_matches_project(
                uuid4(), {"entity_type": "soe"}, "listed_standalone", "五、4"
            )
        cross_entity_warnings = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING and "cross-entity" in r.getMessage()
        ]
        assert cross_entity_warnings, (
            "跨主体同步被放行却未留 warning 日志 ⇒ 静默污染无法事后追溯。"
            f"实际日志：{[r.getMessage() for r in caplog.records]}"
        )

    def test_same_entity_produces_no_cross_entity_warning(self, caplog):
        """双向变异：同主体调用**不得**产出 cross-entity 警告（防上条恒绿）。"""
        from app.services.wp_disclosure_sync_service import (
            _guard_standard_matches_project,
        )

        caplog.clear()
        with caplog.at_level(logging.WARNING):
            _guard_standard_matches_project(
                uuid4(), {"entity_type": "soe"}, "soe_standalone", "八、4"
            )
        cross = [r for r in caplog.records if "cross-entity" in r.getMessage()]
        assert not cross, f"同主体同步误报跨主体警告：{[r.getMessage() for r in cross]}"

    def test_conflict_detector_is_exhaustively_permissive(self):
        """死代码证明：穷举全部 entity 组合，detect_standard_conflict 恒返回 None。

        这条锁住「raise StandardMismatchError 是死代码」这一事实。
        若未来收紧门控，本测试会失败 ⇒ 提醒同步更新 spec 需求 5.1 与 Q8。
        """
        import itertools

        from app.services.standard_unification_service import (
            VALID_ENTITY_TYPES,
            detect_standard_conflict,
        )

        non_none = []
        for pe, re_ in itertools.product(VALID_ENTITY_TYPES, VALID_ENTITY_TYPES):
            for scope in ("standalone", "consolidated"):
                r = detect_standard_conflict({"entity_type": pe}, f"{re_}_{scope}")
                if r is not None:
                    non_none.append((pe, f"{re_}_{scope}", r))
        assert not non_none, (
            "detect_standard_conflict 开始拦截了 ⇒ 门控设计已变更，"
            f"请更新 spec 需求 5.1 / Q8 与本测试类 docstring。命中：{non_none}"
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "spec 需求 5.1 / Q8 要求「跨主体 SHALL 被拒绝且零写入」，"
            "但 2026-08-16 用户裁决改为 warning 放行（合并场景：国企集团含上市子公司）。"
            "需求与实现冲突，已在 spec §勘误 登记。"
            "strict=True：若实现改回 hard block 则本测试 XPASS 并报错，强制更新 spec。"
        ),
    )
    def test_requirement_5_1_hard_block_not_implemented(self):
        """需求 5.1 的原始诉求（hard block）—— 当前**未实现**，xfail 钉住。"""
        from app.services.wp_disclosure_sync_service import (
            StandardMismatchError,
            _guard_standard_matches_project,
        )

        with pytest.raises(StandardMismatchError):
            _guard_standard_matches_project(
                uuid4(), {"entity_type": "soe"}, "listed_standalone", "五、4"
            )

    def test_guard_passes_same_entity(self):
        """同主体类型不抛异常。"""
        from app.services.wp_disclosure_sync_service import (
            _guard_standard_matches_project,
        )

        project_id = uuid4()
        project_standard = {"entity_type": "soe"}
        # 请求国企口径 — 应放行
        _guard_standard_matches_project(
            project_id, project_standard, "soe_standalone", "八、4"
        )  # 不抛即 pass


# ══════════════════════════════════════════════════════════════════════════
# 3.2 空载荷不清表
# ══════════════════════════════════════════════════════════════════════════


class TestEmptyPayloadPreservesTable:
    """空 sub_table_data 同步后既有子表内容不变。"""

    def test_empty_sub_table_data_preserves_existing(self):
        """_count_rows_synced({}) = 0，且不清空既有子表。"""
        from app.services.wp_disclosure_sync_service import _count_rows_synced

        # 空载荷
        assert _count_rows_synced({}) == 0
        assert _count_rows_synced(None) == 0

    def test_meta_keys_not_counted(self):
        """_ 前缀的元数据键不计入行数。"""
        from app.services.wp_disclosure_sync_service import _count_rows_synced

        data = {
            "_note_texts": [{"section": "a", "title": "b", "text": "c"}],
            "_removed_table_keys": ["old_table"],
            "实际表": [{"label": "行1"}, {"label": "行2"}],
        }
        assert _count_rows_synced(data) == 2

    def test_non_empty_payload_counts_correctly(self):
        """双向变异：非空载荷必须真的改变计数。"""
        from app.services.wp_disclosure_sync_service import _count_rows_synced

        data = {"表A": [{"x": 1}], "表B": [{"y": 2}, {"y": 3}]}
        assert _count_rows_synced(data) == 3


# ══════════════════════════════════════════════════════════════════════════
# 3.3 manual_override 保护
# ══════════════════════════════════════════════════════════════════════════


class TestManualOverrideDetection:
    """manual_override 标记的目标字段不被联动覆盖。"""

    def test_detect_top_level_override(self):
        from app.services.wp_disclosure_sync_service import _detect_manual_override

        assert _detect_manual_override({"_manual_override": True}) is True

    def test_detect_sub_level_override(self):
        from app.services.wp_disclosure_sync_service import _detect_manual_override

        td = {"sub_table_data": {"_manual_override": True}}
        assert _detect_manual_override(td) is True

    def test_no_override_returns_false(self):
        from app.services.wp_disclosure_sync_service import _detect_manual_override

        assert _detect_manual_override({"key": "val"}) is False
        assert _detect_manual_override(None) is False
        assert _detect_manual_override({}) is False


# ══════════════════════════════════════════════════════════════════════════
# 3.4 年度权威
# ══════════════════════════════════════════════════════════════════════════


class TestYearAuthority:
    """同步目标年度取 projects.audit_year，不用服务器自然年。"""

    def test_derive_year_fallback_is_current(self):
        """_derive_year(None) 回退到当前自然年（兜底，不是权威）。"""
        from app.services.wp_disclosure_sync_service import _derive_year

        year = _derive_year(None)
        assert isinstance(year, int)
        assert 2020 <= year <= 2030

    def test_derive_year_explicit_wins(self):
        """显式传入年度优先于当前自然年。

        🔴 修复复盘 P2-2：首版本测试**函数体只有注释、零断言** = 空转。
        """
        from datetime import datetime, timezone

        from app.services.wp_disclosure_sync_service import _derive_year

        current = datetime.now(timezone.utc).year
        explicit = current - 3          # 取一个明显不等于当前年的值
        assert _derive_year(explicit) == explicit, (
            "显式 payload_year 未被采用 ⇒ 同步会落到错误年度的附注"
        )
        # 反向：不传时才回退当前自然年
        assert _derive_year(None) == current

    def test_derive_year_rejects_non_int(self):
        """非整数年度不被当作显式值（防 '2025' 字符串绕过类型检查）。"""
        from datetime import datetime, timezone

        from app.services.wp_disclosure_sync_service import _derive_year

        current = datetime.now(timezone.utc).year
        for bad in (0, None):
            assert _derive_year(bad) == current, f"{bad!r} 应回退当前年"

    @pytest.mark.asyncio
    async def test_resolve_target_year_payload_wins(self):
        """_resolve_target_year：payload 显式年度 > 项目审计年度。"""
        from app.services.wp_disclosure_sync_service import _resolve_target_year

        # mock db：不需要真正查库，因为 payload_year 有值就直接返回
        mock_db = AsyncMock()
        result = await _resolve_target_year(mock_db, uuid4(), 2025)
        assert result == 2025

    @pytest.mark.asyncio
    async def test_resolve_target_year_audit_year_second(self):
        """_resolve_target_year：无 payload 时取项目 audit_year。"""
        from app.services.wp_disclosure_sync_service import _resolve_target_year

        mock_db = AsyncMock()
        # mock _resolve_project_audit_year 返回 2024
        with patch(
            "app.services.wp_disclosure_sync_service._resolve_project_audit_year",
            return_value=2024,
        ):
            result = await _resolve_target_year(mock_db, uuid4(), None)
        assert result == 2024

    @pytest.mark.asyncio
    async def test_resolve_target_year_fallback_last(self):
        """_resolve_target_year：前两者都无时才用 _derive_year（当前自然年）。"""
        from app.services.wp_disclosure_sync_service import _resolve_target_year

        mock_db = AsyncMock()
        with patch(
            "app.services.wp_disclosure_sync_service._resolve_project_audit_year",
            return_value=None,
        ):
            result = await _resolve_target_year(mock_db, uuid4(), None)
        # 兜底值应是当前自然年
        assert isinstance(result, int)
        assert 2020 <= result <= 2030


# ══════════════════════════════════════════════════════════════════════════
# 3.5 变体不串写
# ══════════════════════════════════════════════════════════════════════════


class TestVariantNoMixup:
    """同一 wp_code 的 listed 与 soe 章节号互不串写。"""

    def test_registry_listed_soe_disjoint(self):
        """注册表中同一 wp_code 的 listed 章节号与 soe 章节号不相同。"""
        from app.services.disclosure_sync_coverage_service import _build_expectations

        exps = _build_expectations()
        by_code: dict[str, dict[str, set[str]]] = {}
        for e in exps:
            code = e["wp_code"]
            if code not in by_code:
                by_code[code] = {"listed": set(), "soe": set()}
            by_code[code][e["variant"]].add(e["note_section"])

        for code, variants in by_code.items():
            overlap = variants["listed"] & variants["soe"]
            assert not overlap, (
                f"{code} 的 listed 和 soe 章节号重叠：{overlap}。"
                "这会导致同步时上市和国企数据互相覆盖。"
            )

    # ── 前缀约定：逐条例外白名单（不用百分比阈值）──────────────────────
    #
    # 🔴 修复复盘 P1-1：首版用「≥80% 遵循前缀」的阈值，那是**拍脑袋的数字**，
    #    允许以后再悄悄退化 20% 而守卫不响。改为显式白名单 —— 新增例外必须
    #    显式登记，否则测试红。
    #
    # 现算例外（listed 79 职责行中 7 条 / soe 78 行中 0 条）：
    # 全部是**利润表科目**，附注编号体系走「三、」（资产负债表科目才是「五、」）。
    #
    # 🔴 其中 4 条章节号**本身就被截断**（`三、资产处置收益（损` 而非「（损失）」）：
    #    这是平台既有约定，不是缺陷 —— 前端真源常量就这么写
    #    （`h10NoteSectionMap.ts`: `listed: '三、资产处置收益（损'`），
    #    且真库 `disclosure_notes.note_section` 同样截断到 10 字符
    #    （实测 `三、资产处置收益（损` len=10 / `三、信用减值损失（损` len=10）。
    #    两侧口径一致故匹配成功。**禁补全**，补全会让定位失配。
    _LISTED_PREFIX_EXCEPTIONS: frozenset[tuple[str, str]] = frozenset({
        ("G13", "三、公允价值变动收益"),
        ("G14", "三、信用减值损失"),
        ("H10", "三、资产处置收益（损"),
        ("K11", "三、资产减值损失（损"),
        ("K12", "三、营业外收入（注："),
        ("K13", "三、营业外支出（注："),
        ("N5", "三、所得税费用"),
    })
    _SOE_PREFIX_EXCEPTIONS: frozenset[tuple[str, str]] = frozenset()

    def test_listed_sections_follow_prefix_or_are_whitelisted(self):
        """listed 章节号以「五、」开头，除白名单中逐条登记的利润表科目。"""
        from app.services.disclosure_sync_coverage_service import _build_expectations

        unexpected = [
            (e["wp_code"], e["note_section"])
            for e in _build_expectations()
            if e["variant"] == "listed"
            and not e["note_section"].startswith("五、")
            and (e["wp_code"], e["note_section"]) not in self._LISTED_PREFIX_EXCEPTIONS
        ]
        assert not unexpected, (
            "listed 出现未登记的非「五、」章节号。若确为利润表科目请加进 "
            f"_LISTED_PREFIX_EXCEPTIONS 并说明理由：{sorted(set(unexpected))}"
        )

    def test_soe_sections_follow_prefix_or_are_whitelisted(self):
        """soe 章节号以「八、」开头，除白名单（现算为空）。"""
        from app.services.disclosure_sync_coverage_service import _build_expectations

        unexpected = [
            (e["wp_code"], e["note_section"])
            for e in _build_expectations()
            if e["variant"] == "soe"
            and not e["note_section"].startswith("八、")
            and (e["wp_code"], e["note_section"]) not in self._SOE_PREFIX_EXCEPTIONS
        ]
        assert not unexpected, (
            f"soe 出现未登记的非「八、」章节号：{sorted(set(unexpected))}"
        )

    def test_whitelist_has_no_stale_entries(self):
        """白名单不得有失效条目（章节号已改但白名单没删 ⇒ 掩盖新例外）。"""
        from app.services.disclosure_sync_coverage_service import _build_expectations

        actual = {(e["wp_code"], e["note_section"]) for e in _build_expectations()}
        stale = sorted(self._LISTED_PREFIX_EXCEPTIONS - actual)
        assert not stale, (
            f"白名单条目在注册表中已不存在，请删除：{stale}"
        )

    def test_prefix_whitelist_is_not_a_blanket_pass(self):
        """双向变异：白名单是逐条精确匹配，不是「凡三、开头就放过」。

        证明 test_listed_sections_follow_prefix_or_are_whitelisted 非恒绿。
        """
        # 一个未登记的「三、」章节必须落进 unexpected
        fake = ("ZZZ", "三、伪造科目")
        assert fake not in self._LISTED_PREFIX_EXCEPTIONS
        # 同一 wp_code 但章节号不同也不能被放过（白名单是 (code, section) 对）
        assert ("G13", "三、伪造科目") not in self._LISTED_PREFIX_EXCEPTIONS
        # 白名单条目本身必须是精确 tuple
        for code, sec in self._LISTED_PREFIX_EXCEPTIONS:
            assert isinstance(code, str) and isinstance(sec, str)
            assert sec.startswith("三、"), f"白名单只应收「三、」利润表例外，得到 {sec!r}"


# ══════════════════════════════════════════════════════════════════════════
# 3.6 注册表一致性 CI
# ══════════════════════════════════════════════════════════════════════════


class TestRegistryConsistency:
    """Q10 注册表一致性 —— 重跑生成脚本后 **entries 内容** 无 diff。

    🔴 口径澄清（修复复盘 P0-2）：spec 原文写「JSON 字节无 diff」，但生成脚本的
    ``generated_at`` 字段是 ``datetime.now()`` ⇒ 整文件字节全等**永不可能成立**。
    真正可执行的口径 = 除 ``generated_at`` 外的 ``entries`` 与 ``_source`` 逐值相等。

    首版本组 6 个测试全是静态结构检查、``import subprocess`` 却从未调用 ⇒
    docstring 声称的「重跑对比」是假的。本版真跑脚本（两条通路）。

    🔴 本守卫补齐后立即抓到真实漂移：committed 注册表停留在 76 entries，
    而前端真源已有 78（缺 L2 应付利息 五、42/八、42 与 L4 应付债券 五、46/八、50），
    导致覆盖率分母长期漏这两个底稿。已重跑 --write 修正。
    """

    _REGISTRY = Path(__file__).resolve().parents[2] / "data" / "note_workpaper_sync_registry.json"
    _SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gen_note_wp_sync_registry.py"

    @classmethod
    def _load_generator(cls):
        """import 生成脚本模块（不经 sys.path 污染）。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location("_gen_reg", cls._SCRIPT)
        assert spec and spec.loader, f"无法加载生成脚本 {cls._SCRIPT}"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    # ── 通路 1：subprocess 真跑脚本（证明脚本可执行、不崩） ──────────────

    def test_generator_script_runs_successfully(self):
        """🔴 真跑脚本（不带 --write），exit 0 且打印的 entries 数与 committed 一致。"""
        proc = subprocess.run(
            [sys.executable, str(self._SCRIPT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(self._SCRIPT.resolve().parents[2]),
        )
        assert proc.returncode == 0, (
            f"生成脚本执行失败 (exit {proc.returncode})：\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
        m = re.search(r"entries=(\d+)", proc.stdout)
        assert m, f"脚本输出未含 entries 计数：{proc.stdout!r}"
        fresh_count = int(m.group(1))

        committed = json.loads(self._REGISTRY.read_text(encoding="utf-8"))
        assert fresh_count == len(committed["entries"]), (
            f"🔴 注册表漂移：脚本现跑 {fresh_count} entries，"
            f"committed 只有 {len(committed['entries'])} ⇒ "
            f"请重跑 python backend/scripts/gen_note_wp_sync_registry.py --write"
        )

    # ── 通路 2：直调 build_entries() 与 committed 逐值对比（抓手工编辑） ──

    def test_regenerated_entries_match_committed_byte_for_byte(self):
        """🔴 Q10 核心：重新生成的 entries 与 committed 规范化后字节相等。

        规范化 = json.dumps(sort_keys=False, ensure_ascii=False, indent=2)，
        与生成脚本写文件时完全同参 ⇒ 任何手工编辑或前端真源漂移都会被抓到。
        ``generated_at`` 不参与比较（时间戳必然不同，见类 docstring）。
        """
        mod = self._load_generator()
        fresh_entries = mod.build_entries()
        committed = json.loads(self._REGISTRY.read_text(encoding="utf-8"))

        fresh_blob = json.dumps(fresh_entries, ensure_ascii=False, indent=2)
        committed_blob = json.dumps(committed["entries"], ensure_ascii=False, indent=2)

        if fresh_blob != committed_blob:
            fresh_codes = {e["wp_code"] for e in fresh_entries}
            comm_codes = {e["wp_code"] for e in committed["entries"]}
            only_fresh = sorted(fresh_codes - comm_codes)
            only_comm = sorted(comm_codes - fresh_codes)
            raise AssertionError(
                "🔴 注册表与前端真源不一致（手工编辑或忘记重跑脚本）：\n"
                f"  仅在真源中: {only_fresh}\n"
                f"  仅在 committed 中: {only_comm}\n"
                f"  entries 数: 真源 {len(fresh_entries)} vs committed {len(committed['entries'])}\n"
                "  修复：python backend/scripts/gen_note_wp_sync_registry.py --write"
            )

    def test_source_field_matches_generator(self):
        """``_source`` 文案与生成脚本写入的一致（防手工改说明后失去警示）。"""
        committed = json.loads(self._REGISTRY.read_text(encoding="utf-8"))
        source = committed.get("_source", "")
        assert "gen_note_wp_sync_registry.py --write" in source, (
            "_source 应包含重生成命令，否则后人不知道怎么更新"
        )

    def test_mutation_regeneration_check_detects_drift(self):
        """双向变异：往 committed 副本注入/删除 entry 后对比必须失败。

        证明 test_regenerated_entries_match_committed_byte_for_byte 非恒绿。
        """
        mod = self._load_generator()
        fresh_entries = mod.build_entries()
        fresh_blob = json.dumps(fresh_entries, ensure_ascii=False, indent=2)

        # 变异 A：删一条
        mutated_a = json.dumps(fresh_entries[:-1], ensure_ascii=False, indent=2)
        assert mutated_a != fresh_blob, "删除 entry 后对比仍相等 ⇒ 扫描器恒绿"

        # 变异 B：改一个章节号（模拟手工编辑）
        import copy

        mutated_list = copy.deepcopy(fresh_entries)
        for e in mutated_list:
            if e.get("listed"):
                e["listed"] = "五、999"
                break
        mutated_b = json.dumps(mutated_list, ensure_ascii=False, indent=2)
        assert mutated_b != fresh_blob, "改章节号后对比仍相等 ⇒ 扫描器恒绿"

    def test_registry_file_exists(self):
        assert self._REGISTRY.exists(), f"注册表不存在: {self._REGISTRY}"

    def test_registry_valid_json(self):
        data = json.loads(self._REGISTRY.read_text(encoding="utf-8"))
        assert "entries" in data
        assert isinstance(data["entries"], list)
        assert len(data["entries"]) > 0

    def test_registry_generator_script_exists(self):
        assert self._SCRIPT.exists(), f"生成脚本不存在: {self._SCRIPT}"

    def test_registry_entries_have_required_fields(self):
        """每个 entry 必须有 wp_code + (listed 或 soe)。"""
        data = json.loads(self._REGISTRY.read_text(encoding="utf-8"))
        for i, entry in enumerate(data["entries"]):
            assert entry.get("wp_code"), f"entries[{i}] 缺 wp_code"
            has_listed = bool(entry.get("listed") or entry.get("listed_sections"))
            has_soe = bool(entry.get("soe") or entry.get("soe_sections"))
            assert has_listed or has_soe, (
                f"entries[{i}] wp_code={entry['wp_code']} 既无 listed 也无 soe"
            )

    def test_registry_no_duplicate_wp_code(self):
        """注册表内 wp_code 不重复。"""
        data = json.loads(self._REGISTRY.read_text(encoding="utf-8"))
        codes = [e["wp_code"] for e in data["entries"]]
        duplicates = [c for c in codes if codes.count(c) > 1]
        assert not duplicates, f"重复 wp_code: {set(duplicates)}"

    def test_registry_source_comment_warns_no_manual_edit(self):
        """注册表顶部 _source 字段警告不要手工编辑。"""
        data = json.loads(self._REGISTRY.read_text(encoding="utf-8"))
        source = data.get("_source", "")
        assert "勿手工编辑" in source or "手工" in source, (
            "_source 字段应包含手工编辑警告"
        )
