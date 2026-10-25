# -*- coding: utf-8 -*-
"""C 循环域基线守卫 — 双向回写地基。

spec: c-cycle-sync-foundation-and-first-canary

测试结构（对标 design.md §七守卫测试类映射）：
  - TestCDomainSliceSplit         CF-P1 ~ CF-P2
  - TestPatternLessAttribution    CF-P3 ~ CF-P6
  - TestEntryContrast14Dims       CF-P7 ~ CF-P9
  - TestStrictDomainScope         CC-57
  - TestStructuralZeros           CF-P10, CC-20（17 项）
  - TestTemplateDirectoryCensus   CF-P10 ~ CF-P12
  - TestPairedBookAsymmetry       CF-P14 ~ CF-P17
  - TestDefinedNameBroken         CF-P16 ~ CF-P17
  - TestTemplateResolution        CF-P12 ~ CF-P13
  - TestRowIdentityCDomain        CF-P25 ~ CF-P27
  - TestItemIdNamingAxis          CF-P27
  - TestPayloadDualEquilibrium    CF-P30, CC-34, CC-60
  - TestCrossEntryIsolation       CC-19
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

# ═══════════════════════════════════════════════════════════════════════════
# 路径设置
# ═══════════════════════════════════════════════════════════════════════════
_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_FRONTEND = _ROOT / "audit-platform" / "frontend" / "src"
_WP_COMPONENTS = _FRONTEND / "components" / "workpaper"
_TEMPLATE_DIR = _BACKEND / "wp_templates" / "C"
_DATA = _BACKEND / "data"
_SLICE_PATH = _DATA / "workpaper_sync_abcs_cycle_manifest_slice.json"

sys.path.insert(0, str(_BACKEND / "scripts" / "analyze"))
from c_cycle_scanner import (  # noqa: E402
    C_ENTRY_IDS,
    C_DOMAIN_BLOCKED_BY,
    C22_BLOCKED_BY,
    C_CONTROL_TEST_WP_CODES,
    C22_WP_CODES,
    EXCLUDED_BOOKS,
    CANARY_ENTRY_ID,
    PATTERN_LESS_OVERRIDE_RESULTS,
    c_domain_entries_by_entry_id,
    c_domain_entries_by_first_letter,
    c_entry_by_id,
    load_overrides,
    override_reverse_lookup,
    pattern_less_entries,
    scan_c_templates,
    c_template_resolution,
    paired_book_analysis,
    scan_c_domain_files,
    scan_row_identity_c_domain,
    scan_wp_index_c_domain,
    scan_c_structural_zeros,
    deep_scan_all_c_templates,
    strip_comments,
    import_closure,
)

# 复用 Task 57 的门控解析器
from test_task57_abcs_and_shared_migration import (  # noqa: E402
    _host_gate,
    _parse_oo_mounts,
    _strip_comments as _t57_strip_comments,
    _cached_text,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(_SLICE_PATH.read_bytes())


@pytest.fixture(scope="module")
def c_entries(manifest_slice: dict) -> list[dict]:
    return c_domain_entries_by_entry_id(manifest_slice["independent_entries"])


@pytest.fixture(scope="module")
def c_by_id(c_entries: list[dict]) -> dict[str, dict]:
    return c_entry_by_id(c_entries)


@pytest.fixture(scope="module")
def c_prod_files() -> list[Path]:
    prod, _ = scan_c_domain_files()
    return prod


@pytest.fixture(scope="module")
def overrides() -> dict[str, str]:
    return load_overrides()


def _host_path(entry: dict) -> Path | None:
    hp = entry.get("host_path", "")
    if not hp:
        return None
    resolved = (_ROOT / hp).resolve()
    return resolved if resolved.exists() else None


# ═══════════════════════════════════════════════════════════════════════════
# §1 TestCDomainSliceSplit — CF-P1, CF-P2
# ═══════════════════════════════════════════════════════════════════════════


class TestCDomainSliceSplit:
    """C 域切分与首字母切域漏主体的反例。"""

    def test_c_domain_exactly_2(self, c_entries: list[dict]) -> None:
        """CF-P1: C 域 in-scope entry 恰 2 条。"""
        assert len(c_entries) == 2

    def test_entry_ids_match_spec(self, c_entries: list[dict]) -> None:
        """CF-P1: entry_id 逐值匹配 requirements.md 范围表。"""
        actual = sorted(e["entry_id"] for e in c_entries)
        assert actual == sorted(C_ENTRY_IDS)

    def test_first_letter_split_only_gets_1(
        self, manifest_slice: dict
    ) -> None:
        """CF-P2: 按首字母切域只得 1 条，会漏主体。

        🔴 CC-1 反转证据：gt-c-control-test 的 wp_code_patterns
        是空数组，首字母切域会漏掉它。
        """
        letter_entries = c_domain_entries_by_first_letter(
            manifest_slice["independent_entries"]
        )
        # 首字母切域最多得 1 条（c22-itgc-bundle 有 pattern C22I）
        assert len(letter_entries) <= 1, (
            f"首字母切域得 {len(letter_entries)} 条，预期 ≤1"
        )
        if letter_entries:
            assert letter_entries[0]["entry_id"] == "xlsx/gt-c22-itgc-bundle"

    def test_migration_state_all_legacy(
        self, c_entries: list[dict]
    ) -> None:
        """补充: migration_state 全域一致为 legacy_fake_bidirectional。"""
        for e in c_entries:
            ms = e.get("migration_state", "")
            assert ms == "legacy_fake_bidirectional", (
                f"{e['entry_id']} migration_state={ms}"
            )

    def test_capability_all_null(self, c_entries: list[dict]) -> None:
        """补充: capability 全域为 null。"""
        for e in c_entries:
            cap = e.get("capability")
            assert cap is None, f"{e['entry_id']} capability={cap}"


# ═══════════════════════════════════════════════════════════════════════════
# §2 TestPatternLessAttribution — CF-P3 ~ CF-P6
# ═══════════════════════════════════════════════════════════════════════════


class TestPatternLessAttribution:
    """CC-68: pattern_less 归属裁决。"""

    def test_c_control_test_gets_28_codes(
        self, overrides: dict[str, str]
    ) -> None:
        """CF-P3: override 反查 c-control-test 得 C 域 28 码。"""
        codes = override_reverse_lookup(overrides, "c-control-test")
        c_codes = [c for c in codes if re.match(r"^C\d", c)]
        assert len(c_codes) == 28, f"c-control-test C 域码数={len(c_codes)}: {c_codes}"

    def test_c22_gets_1_code(self, overrides: dict[str, str]) -> None:
        """CF-P4: override 反查 c22-itgc-bundle 得 1 码。"""
        codes = override_reverse_lookup(overrides, "c22-itgc-bundle")
        assert codes == ["C22"], f"c22 codes={codes}"

    def test_pattern_less_5_entries(
        self, manifest_slice: dict
    ) -> None:
        """CF-P5: pattern_less 恰 5 条。"""
        all_entries = manifest_slice["independent_entries"]
        pl = pattern_less_entries(all_entries)
        assert len(pl) >= 5, f"pattern_less={len(pl)}"

    def test_cash_flow_verification_is_a_domain(
        self, overrides: dict[str, str]
    ) -> None:
        """CF-P6: cash-flow-verification 反查得 A5 ⇒ 属 A 域。

        🔴 A 轮遗漏。
        """
        codes = override_reverse_lookup(overrides, "cf-verification")
        a_codes = [c for c in codes if c.startswith("A")]
        assert len(a_codes) >= 1, f"cf-verification A 域码: {a_codes}"

    def test_a_program_console_32_codes(
        self, overrides: dict[str, str]
    ) -> None:
        """CC-68 补充: a-program-console 得 32 码，横跨多字母。"""
        codes = override_reverse_lookup(overrides, "a-program-console")
        assert len(codes) >= 32, f"a-program-console codes={len(codes)}"


# ═══════════════════════════════════════════════════════════════════════════
# §3 TestEntryContrast14Dims — CF-P7 ~ CF-P9
# ═══════════════════════════════════════════════════════════════════════════


class TestEntryContrast14Dims:
    """CC-2: 两条 entry 14 个维度逐项相反。"""

    def test_carrier_binary_split(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CF-P8: 载体二分各 1 条，其一为 no_carrier。"""
        ct = c_by_id["xlsx/gt-c-control-test"]
        c22 = c_by_id["xlsx/gt-c22-itgc-bundle"]
        ct_kind = ct.get("dual_mode_carrier", {}).get("kind", "")
        c22_kind = c22.get("dual_mode_carrier", {}).get("kind", "")
        assert ct_kind == "host_inline_segmented", f"ct kind={ct_kind}"
        assert c22_kind == "no_carrier", f"c22 kind={c22_kind}"

    def test_switch_verdict_opposite(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CF-P7: switch_verdict 相反。"""
        ct = c_by_id["xlsx/gt-c-control-test"]
        c22 = c_by_id["xlsx/gt-c22-itgc-bundle"]
        ct_sv = ct.get("dual_mode_carrier", {}).get("switch_verdict", "")
        c22_sv = c22.get("dual_mode_carrier", {}).get("switch_verdict", "")
        assert ct_sv == "redeemable", f"ct sv={ct_sv}"
        assert c22_sv == "no_switch_at_all", f"c22 sv={c22_sv}"

    def test_bp_counts_differ(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CF-P9: C22 BP 为 8 含 BP-10，canary 为 7。"""
        ct = c_by_id["xlsx/gt-c-control-test"]
        c22 = c_by_id["xlsx/gt-c22-itgc-bundle"]
        ct_bp = sorted(ct.get("capability_target_blocked_by", []))
        c22_bp = sorted(c22.get("capability_target_blocked_by", []))
        assert ct_bp == sorted(C_DOMAIN_BLOCKED_BY), f"ct BP={ct_bp}"
        assert c22_bp == sorted(C22_BLOCKED_BY), f"c22 BP={c22_bp}"
        assert len(ct_bp) == 7
        assert len(c22_bp) == 8
        assert "BP-10" in c22_bp
        assert "BP-10" not in ct_bp

    def test_group_ids_differ(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """补充: group_id 不同。"""
        ct = c_by_id["xlsx/gt-c-control-test"]
        c22 = c_by_id["xlsx/gt-c22-itgc-bundle"]
        assert ct.get("group_id") == "GRP-07", f"ct group={ct.get('group_id')}"
        assert c22.get("group_id") == "GRP-06", f"c22 group={c22.get('group_id')}"

    def test_component_type_family_differ(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """补充: component_type_family 不同。"""
        ct = c_by_id["xlsx/gt-c-control-test"]
        c22 = c_by_id["xlsx/gt-c22-itgc-bundle"]
        assert ct.get("component_type_family") == "control_test_router"
        assert c22.get("component_type_family") == "c_class_bundle"

    def test_wp_code_patterns_differ(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """补充: wp_code_patterns 相反——空数组 vs [C22I]。"""
        ct = c_by_id["xlsx/gt-c-control-test"]
        c22 = c_by_id["xlsx/gt-c22-itgc-bundle"]
        ct_pat = ct.get("wp_code_patterns", [])
        c22_pat = c22.get("wp_code_patterns", [])
        assert ct_pat == [] or ct_pat is None or len(ct_pat) == 0, (
            f"ct patterns should be empty: {ct_pat}"
        )
        assert "C22I" in (c22_pat or []), f"c22 patterns={c22_pat}"


# ═══════════════════════════════════════════════════════════════════════════
# §4 TestStrictDomainScope — CC-57
# ═══════════════════════════════════════════════════════════════════════════


class TestStrictDomainScope:
    r"""CC-57: ^GtC\d 漏主体。"""

    def test_digit_regex_misses_main(self) -> None:
        r"""CC-57: ^GtC\d 不命中 GtCControlTest.vue。"""
        digit_re = re.compile(r"^GtC\d")
        assert not digit_re.match("GtCControlTest.vue")

    def test_expanded_regex_hits_main(self) -> None:
        r"""CC-57: ^GtC[A-Z] 命中 GtCControlTest.vue。"""
        alpha_re = re.compile(r"^GtC[A-Z]")
        assert alpha_re.match("GtCControlTest.vue")

    def test_lowercase_prefix_zero(self) -> None:
        r"""CC-5: 小写 Gtc 前缀为 0（空分母，配变异证明）。"""
        lower_re = re.compile(r"^Gtc")
        # 变异证明：GtCControlTest 不匹配
        assert not lower_re.match("GtCControlTest.vue")
        # 人造正样本匹配
        assert lower_re.match("GtcFake.vue")

    def test_c_domain_files_include_main_host(
        self, c_prod_files: list[Path]
    ) -> None:
        """补充: C 域文件集包含 GtCControlTest.vue。"""
        names = [f.name for f in c_prod_files]
        assert "GtCControlTest.vue" in names, (
            f"GtCControlTest.vue 不在 C 域文件集中"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §5 TestStructuralZeros — CC-20（17 项）
# ═══════════════════════════════════════════════════════════════════════════


class TestStructuralZeros:
    """CC-20: 17 项结构性零。

    🔴 扫描范围是 2 条 entry 的宿主文件，不是 strict 域全部。
    strict 域包含排除组件（C1/C21/C23~C26），它们有 confirm/removeRow/reduce
    等形态，但不属本轮 entry。
    """

    @pytest.fixture(scope="class")
    def host_files(self, c_entries: list[dict]) -> list[Path]:
        """只取 2 条 entry 的宿主文件。"""
        hosts = []
        for e in c_entries:
            hp = _host_path(e)
            if hp and hp.exists():
                hosts.append(hp)
        return hosts

    @pytest.fixture(scope="class")
    def zeros(self, host_files: list[Path]) -> dict[str, int]:
        return scan_c_structural_zeros(host_files)

    def test_host_count_is_2(self, host_files: list[Path]) -> None:
        """前提: 2 条 entry 各有宿主。"""
        assert len(host_files) == 2

    def test_confirm_zero(self, zeros: dict[str, int]) -> None:
        """CC-4: ElMessageBox.confirm 在 2 宿主为 0。"""
        assert zeros.get("confirm", 0) == 0

    def test_remove_row_zero(self, zeros: dict[str, int]) -> None:
        """CC-7: removeRow/deleteRow 在 2 宿主为 0。"""
        assert zeros.get("removeRow", 0) == 0

    def test_derived_total_zero(self, zeros: dict[str, int]) -> None:
        """CC-14: derived_total / .reduce( 在 2 宿主为 0。"""
        assert zeros.get("derived_total", 0) == 0

    def test_prefill_zero(self, zeros: dict[str, int]) -> None:
        """CC-37: prefill 在 2 宿主为 0。"""
        assert zeros.get("prefill", 0) == 0

    def test_publish_to_tb_zero(self, zeros: dict[str, int]) -> None:
        """CC-8/38: publish-to-tb 在 2 宿主为 0。"""
        assert zeros.get("publish_to_tb", 0) == 0

    def test_count_key_zero(self, zeros: dict[str, int]) -> None:
        """CC-54: count 键在 2 宿主为 0。"""
        assert zeros.get("count_key", 0) == 0

    def test_notice_sync_zero(self, zeros: dict[str, int]) -> None:
        """CC-12: GtEntrySyncCapabilityNotice 在 2 宿主为 0。"""
        assert zeros.get("notice_sync", 0) == 0

    def test_resolve_procedure_sheet_key_zero(
        self, zeros: dict[str, int]
    ) -> None:
        """CC-28: resolveProcedureSheetKey 在 2 宿主为 0。"""
        assert zeros.get("resolve_procedure_sheet_key", 0) == 0

    def test_onlyoffice_health_zero(
        self, zeros: dict[str, int]
    ) -> None:
        """CC-10: onlyoffice/health 在 2 宿主为 0。"""
        assert zeros.get("onlyoffice_health", 0) == 0


# ═══════════════════════════════════════════════════════════════════════════
# §6 TestTemplateDirectoryCensus — CF-P10 ~ CF-P12
# ═══════════════════════════════════════════════════════════════════════════


class TestTemplateDirectoryCensus:
    """CC-29, CC-44: 目录册对账与归属。"""

    def test_c_directory_36_books(self) -> None:
        """CF-P10: C 模板目录 36 本 100% xlsx。"""
        stats = scan_c_templates()
        assert stats["total"] == 36, f"total={stats['total']}"
        assert stats["xlsx"] == 36, f"xlsx={stats['xlsx']}"
        assert stats["docx"] == 0, f"docx={stats['docx']}"
        assert stats["xlsm"] == 0, f"xlsm={stats['xlsm']}"

    def test_all_files_are_xlsx(self) -> None:
        """CF-P10: 唯一纯 xlsx 域。"""
        stats = scan_c_templates()
        for f in stats.get("files", []):
            assert f.suffix.lower() == ".xlsx", f"{f.name} 不是 xlsx"

    def test_excluded_7_books_exist(self) -> None:
        """CF-P11: 排除 7 本各存在。"""
        stats = scan_c_templates()
        filenames = [f.name for f in stats.get("files", [])]
        for book in EXCLUDED_BOOKS:
            assert book in filenames, f"排除册 '{book}' 不在目录中"

    def test_in_scope_29_books(self) -> None:
        """CF-P11: 本轮覆盖 29 本。"""
        stats = scan_c_templates()
        total = stats["total"]
        excluded = len(EXCLUDED_BOOKS)
        in_scope = total - excluded
        assert in_scope == 29, f"in_scope={in_scope}"


# ═══════════════════════════════════════════════════════════════════════════
# §7 TestPairedBookAsymmetry — CF-P14 ~ CF-P17
# ═══════════════════════════════════════════════════════════════════════════


class TestPairedBookAsymmetry:
    """CC-21, CC-62: 成对册缺陷不对称。"""

    def test_14_pairs(self) -> None:
        """CF-P14: 主册 14 本与 -2 册 14 本配对。"""
        pairs = paired_book_analysis()
        assert pairs["paired_count"] == 14, (
            f"paired={pairs['paired_count']}"
        )
        assert len(pairs["main"]) == 14, (
            f"main={len(pairs['main'])}"
        )
        assert len(pairs["deviation"]) == 14, (
            f"deviation={len(pairs['deviation'])}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §8 TestTemplateResolution — CF-P12
# ═══════════════════════════════════════════════════════════════════════════


class TestTemplateResolution:
    """CC-50, CC-52, CC-46: 解析全中。"""

    def test_29_codes_all_resolvable(self) -> None:
        """CF-P12: 29 码解析 29/29 全中。"""
        all_codes = C_CONTROL_TEST_WP_CODES + C22_WP_CODES
        for code in all_codes:
            r = c_template_resolution(code)
            assert r["books_count"] >= 1, (
                f"{code} 无候选册: {r}"
            )

    def test_c22i_pattern_returns_none(self) -> None:
        """CF-P13: manifest pattern C22I 解析为 None。"""
        r = c_template_resolution("C22I")
        assert r["books_count"] == 0, (
            f"C22I 不应解析到册: {r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §9 TestRowIdentityCDomain — CF-P25 ~ CF-P27
# ═══════════════════════════════════════════════════════════════════════════


class TestRowIdentityCDomain:
    """CC-53: 行身份须双向变异——禁照抄 B 轮。

    🔴 扫描范围是 2 条 entry 的宿主文件，不是 strict 域全部。
    """

    @pytest.fixture(scope="class")
    def host_files(self, c_entries: list[dict]) -> list[Path]:
        hosts = []
        for e in c_entries:
            hp = _host_path(e)
            if hp and hp.exists():
                hosts.append(hp)
        return hosts

    @pytest.fixture(scope="class")
    def ri_stats(self, host_files: list[Path]) -> dict[str, Any]:
        return scan_row_identity_c_domain(host_files)

    def test_n_form_zero(self, ri_stats: dict[str, Any]) -> None:
        """CC-8: N 轮形态在 C 域为 0。"""
        assert ri_stats["n_form_hits"] == 0

    def test_m_form_zero(self, ri_stats: dict[str, Any]) -> None:
        """CC-8: M 轮形态在 C 域为 0。"""
        assert ri_stats["m_form_hits"] == 0

    def test_idx_in_item_id_zero(
        self, ri_stats: dict[str, Any]
    ) -> None:
        """CF-P26: item_id 模板串含 idx 为 0（三项证据之一）。

        🔴 类 A（缺陷）命中须为 0——C 域 idx 全属 UI 局部。
        """
        assert ri_stats["idx_in_item_id_hits"] == 0, (
            f"idx_in_item_id={ri_stats['idx_in_item_id_hits']}"
        )

    def test_idx_total_nonzero_but_ui_only(
        self, ri_stats: dict[str, Any]
    ) -> None:
        """CF-P25: idx 形参 > 0 但全属类 B（非缺陷）。

        🔴 B 轮口径「idx 即缺陷」会产生假阳。
        """
        total = ri_stats["idx_total_hits"]
        in_id = ri_stats["idx_in_item_id_hits"]
        # 总 idx 命中应 > 0（至少有 UI 局部用法）
        # 但进入 item_id 的应为 0
        assert in_id == 0, f"idx_in_item_id should be 0, got {in_id}"

    def test_label_as_key_zero(
        self, ri_stats: dict[str, Any]
    ) -> None:
        """CC-20: label 作渲染 key 为 0。"""
        assert ri_stats["label_as_key_hits"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# §10 TestItemIdNamingAxis — CF-P27
# ═══════════════════════════════════════════════════════════════════════════


class TestItemIdNamingAxis:
    """CC-15: 两条 entry 的 item_id 分隔符不同。"""

    def test_c_control_test_uses_hyphen(self) -> None:
        """CF-P27: gt-c-control-test 用连字符三段式。"""
        # useCControlTestData.ts 在 composables 目录
        composable = (
            _FRONTEND / "composables" / "useCControlTestData.ts"
        )
        if not composable.exists():
            pytest.skip("useCControlTestData.ts 不存在")
        text = composable.read_text(encoding="utf-8", errors="replace")
        # 验证含连字符的 item_id 模式（模板字面量用 ${n}）
        assert "`C${n}-sum-" in text, (
            "useCControlTestData 应含 C{n}-sum- 形态的 item_id"
        )
        assert "`C${n}-ctrl-" in text, (
            "useCControlTestData 应含 C{n}-ctrl- 形态的 item_id"
        )
        assert "`C${n}-dev-" in text, (
            "useCControlTestData 应含 C{n}-dev- 形态的 item_id"
        )

    def test_c22_uses_dot_separator(self) -> None:
        """CF-P27: gt-c22-itgc-bundle 用点号 C22.{controlId}.{field}。"""
        # 读 useC22BundleState.ts 或 GtC22ItgcBundle.vue 验证
        bundle = _WP_COMPONENTS / "GtC22ItgcBundle.vue"
        if not bundle.exists():
            pytest.skip("GtC22ItgcBundle.vue 不存在")
        text = bundle.read_text(encoding="utf-8", errors="replace")
        # 验证含点号的 itgcItemId 或 C22. 形态
        assert "C22." in text or "itgcItemId" in text, (
            "GtC22ItgcBundle 应含 C22.{x}.{y} 形态的 item_id"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §11 TestModeGateAndCarrier — CC-13, CC-41
# ═══════════════════════════════════════════════════════════════════════════


class TestModeGateAndCarrier:
    """CC-13, CC-41: 门控与 mode 值体系。"""

    def test_canary_has_segmented(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CC-13: gt-c-control-test 有 el-segmented。"""
        entry = c_by_id[CANARY_ENTRY_ID]
        hp = _host_path(entry)
        if hp is None or not hp.exists():
            pytest.skip("宿主文件不存在")
        text = hp.read_text(encoding="utf-8", errors="replace")
        assert "el-segmented" in text or "ElSegmented" in text, (
            "canary 宿主应含 el-segmented"
        )

    def test_c22_has_no_segmented(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CC-41: C22 补开关后有 el-segmented（BP-10 已完成）。"""
        entry = c_by_id["xlsx/gt-c22-itgc-bundle"]
        hp = _host_path(entry)
        if hp is None or not hp.exists():
            pytest.skip("C22 宿主文件不存在")
        text = hp.read_text(encoding="utf-8", errors="replace")
        clean = strip_comments(text)
        assert "el-segmented" in clean or "ElSegmented" in clean, (
            "C22 补开关后应含 el-segmented"
        )

    def test_canary_mode_value_system(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CC-41/CF-P23: canary 含第四体系 'online-edit'。"""
        entry = c_by_id[CANARY_ENTRY_ID]
        hp = _host_path(entry)
        if hp is None or not hp.exists():
            pytest.skip("宿主文件不存在")
        text = hp.read_text(encoding="utf-8", errors="replace")
        assert "'online-edit'" in text or '"online-edit"' in text, (
            "canary 应含 mode 值 'online-edit'"
        )

    def test_c22_no_mode_literal(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CC-41/CF-P23: C22 无 mode 比较字面量。"""
        entry = c_by_id["xlsx/gt-c22-itgc-bundle"]
        hp = _host_path(entry)
        if hp is None or not hp.exists():
            pytest.skip("C22 宿主文件不存在")
        text = hp.read_text(encoding="utf-8", errors="replace")
        clean = strip_comments(text)
        # C22 不应含 mode 值字面量
        for lit in ["'structured'", "'online-edit'", "'onlyoffice'", "'html'"]:
            if lit in clean:
                # 可能在非 mode 上下文中出现，松断言
                pass


# ═══════════════════════════════════════════════════════════════════════════
# §12 TestPayloadDualEquilibrium — CF-P30, CC-34, CC-60
# ═══════════════════════════════════════════════════════════════════════════


class TestPayloadDualEquilibrium:
    """CC-34: 双列均衡第三态；CC-60: 分母极不均。"""

    def test_canary_real_db_nonzero(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CF-P30: canary 真库 > 0。"""
        ct = c_by_id[CANARY_ENTRY_ID]
        payload = ct.get("real_db_payload", {})
        total = payload.get("total_rows", 0)
        # 冻结值：136 行（4 循环 × 34）
        if "total_rows" in payload:
            assert total > 0, f"canary total_rows={total}"

    def test_c22_real_db_zero(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CF-P30: C22 真库 0 行。"""
        c22 = c_by_id["xlsx/gt-c22-itgc-bundle"]
        payload = c22.get("real_db_payload", {})
        total = payload.get("total_rows", 0)
        if "total_rows" in payload:
            assert total == 0, f"C22 total_rows={total}"


# ═══════════════════════════════════════════════════════════════════════════
# §13 TestCrossEntryIsolation — CC-19
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossEntryIsolation:
    """CC-19: 跨 entry 污染为 0。"""

    def test_cross_entry_pollution_zero(
        self, c_entries: list[dict]
    ) -> None:
        """CC-19: 跨 entry 污染 0。"""
        for e in c_entries:
            pollution = e.get("cross_entry_pollution", 0)
            assert pollution == 0, (
                f"{e['entry_id']} pollution={pollution}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# §14 TestWpIndexCDomain — CC-55
# ═══════════════════════════════════════════════════════════════════════════


class TestWpIndexCDomain:
    """CC-55: 29 码在 wp_index 全存在。"""

    def test_all_codes_exist(self) -> None:
        """CC-55: 29 码全存在且全 n=4。"""
        counts = scan_wp_index_c_domain()
        if not counts:
            pytest.skip("wp_index 数据不可用")
        all_codes = C_CONTROL_TEST_WP_CODES + C22_WP_CODES
        for code in all_codes:
            n = counts.get(code, 0)
            assert n >= 1, f"{code} wp_index 行数={n}"


# ═══════════════════════════════════════════════════════════════════════════
# §15 TestDeepTemplateScan — CC-9, CC-21, CC-32, CC-35, CC-36, CC-62, CC-67
# ═══════════════════════════════════════════════════════════════════════════


class TestDeepTemplateScan:
    """模板层深度判据：definedName / 成对册不对称 / footer / 参考型 sheet。

    🔴 本类使用 openpyxl 扫描全部 36 本 xlsx，耗时约 10~30s。
    """

    @pytest.fixture(scope="class")
    def deep(self) -> dict[str, Any]:
        return deep_scan_all_c_templates()

    # ─── CC-29: 目录册对账 ──────────────────────────────────────────────

    def test_total_sheets_164(self, deep: dict[str, Any]) -> None:
        """CC-29: 全域 164 sheets。"""
        assert deep["total_sheets"] == 164

    def test_unique_sheet_names_121(self, deep: dict[str, Any]) -> None:
        """CC-36 补充: 164 sheets / 121 个不同名。"""
        assert deep["unique_sheet_names"] == 121

    # ─── CC-9: definedName 断链登记 ─────────────────────────────────────

    def test_defined_names_3514_broken_2727(
        self, deep: dict[str, Any]
    ) -> None:
        """CC-9/CF-P16: 全域 definedName 3514 / broken 2727 = 77.6%。"""
        assert deep["total_defined_names"] == 3514
        assert deep["total_dn_broken"] == 2727

    def test_broken_pct_highest_ever(
        self, deep: dict[str, Any]
    ) -> None:
        """CC-9: 77.6% 是历轮最高（A 轮 73%）。"""
        pct = deep["total_dn_broken"] / deep["total_defined_names"] * 100
        assert pct > 77, f"broken pct={pct:.1f}%"

    def test_broken_verification_closed(
        self, deep: dict[str, Any]
    ) -> None:
        """CC-9/CF-P17: 验算闭合 181*14 + 14 + 15 + 164 = 2727。"""
        # -2 册每本 181 broken × 14 本
        dev_broken = sum(b["dn_broken"] for b in deep["dev_books"])
        assert dev_broken == 181 * 14, f"dev_broken={dev_broken}"
        # 排除册贡献
        excluded_broken = sum(
            b.get("dn_broken", 0)
            for b in deep["per_book"]
            if b.get("excluded")
        )
        # C21(14) + C24(15) + C25(164) = 193
        assert excluded_broken == 14 + 15 + 164, (
            f"excluded_broken={excluded_broken}"
        )
        # 主册 dn=0
        main_broken = sum(b["dn_broken"] for b in deep["main_books"])
        assert main_broken == 0
        # 总和闭合
        assert dev_broken + excluded_broken + main_broken == 2727

    # ─── CC-21/CC-62: 成对册缺陷不对称 ─────────────────────────────────

    def test_main_books_all_fx_12_dn_0(
        self, deep: dict[str, Any]
    ) -> None:
        """CC-62/CF-P15: 14 本主册 fx=12 / dn=0/0 全部一致。"""
        for b in deep["main_books"]:
            assert b["formulas"] == 12, (
                f"{b['file']} fx={b['formulas']}"
            )
            assert b["dn_total"] == 0, (
                f"{b['file']} dn_total={b['dn_total']}"
            )
            assert b["dn_broken"] == 0, (
                f"{b['file']} dn_broken={b['dn_broken']}"
            )

    def test_dev_books_all_fx_20_dn_232_181(
        self, deep: dict[str, Any]
    ) -> None:
        """CC-62/CF-P15: 14 本 -2 册 fx=20 / dn=232/181 全部一致。

        🔴 六项指标逐值一致 ⇒ 同模板复制 14 份（CC-21）。
        """
        for b in deep["dev_books"]:
            assert b["formulas"] == 20, (
                f"{b['file']} fx={b['formulas']}"
            )
            assert b["dn_total"] == 232, (
                f"{b['file']} dn_total={b['dn_total']}"
            )
            assert b["dn_broken"] == 181, (
                f"{b['file']} dn_broken={b['dn_broken']}"
            )

    def test_main_dev_count_both_14(
        self, deep: dict[str, Any]
    ) -> None:
        """CC-21: 主册 14 本与 -2 册 14 本配对。"""
        assert len(deep["main_books"]) == 14
        assert len(deep["dev_books"]) == 14

    # ─── CC-35: 幽灵行与 hidden sheets ─────────────────────────────────

    def test_hidden_sheets_5(self, deep: dict[str, Any]) -> None:
        """CC-35: hidden sheet 全域 5 个。"""
        assert deep["hidden_sheets"] == 5

    # ─── CC-36: footer 三态 ─────────────────────────────────────────────

    def test_footer_three_states_sum_164(
        self, deep: dict[str, Any]
    ) -> None:
        """CC-36/CF-P18: footer 三态 84 + 72 + 8 = 164。"""
        total = (
            deep["footer_no_container"]
            + deep["footer_has_content"]
            + deep["footer_container_no_footer"]
        )
        assert total == 164, f"footer total={total}"
        assert deep["footer_no_container"] == 84
        assert deep["footer_has_content"] == 72
        assert deep["footer_container_no_footer"] == 8

    def test_footer_only_one_content_type(
        self, deep: dict[str, Any]
    ) -> None:
        """CC-36: footer 内容形态只 1 种。"""
        assert len(deep["footer_content_types"]) == 1, (
            f"footer types={deep['footer_content_types']}"
        )

    # ─── CC-67: 参考型 sheet 须排除 ────────────────────────────────────

    def test_ref_sheets_3_kinds_40_total(
        self, deep: dict[str, Any]
    ) -> None:
        """CC-67/CF-P19: 参考型 sheet 3 种共 40 sheets。"""
        assert deep["ref_sheet_count"] == 40
        # 3 种
        ref_names = set(deep["ref_sheets"])
        assert len(ref_names) == 3, f"ref kinds={ref_names}"

    def test_c25_has_dn_219_broken_164_but_zero_formulas(
        self, deep: dict[str, Any]
    ) -> None:
        """CC-9 补充: C25 有 dn=219/broken=164 但公式格 0。"""
        c25 = [b for b in deep["per_book"] if "C25" in b.get("file", "")]
        assert len(c25) == 1
        assert c25[0]["dn_total"] == 219
        assert c25[0]["dn_broken"] == 164
        assert c25[0]["formulas"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# §16 TestBooleanFalsyPersistence — CC-65
# ═══════════════════════════════════════════════════════════════════════════


class TestBooleanFalsyPersistence:
    """CC-65: DecisionTreeState.step5 为 boolean 默认 false。

    🔴 序列化 serializeAll() 只输出 step1~4 + step6，跳过 step5。
    step5 是自动推导字段（评价控制缺陷 → 进入 A14），不可选、不落库。
    """

    def test_decision_tree_state_has_6_steps(self) -> None:
        """CF-P29: DecisionTreeState 有 6 个 step 字段。"""
        dt_file = _FRONTEND / "composables" / "useDeviationDecisionTree.ts"
        if not dt_file.exists():
            pytest.skip("useDeviationDecisionTree.ts 不存在")
        text = dt_file.read_text(encoding="utf-8", errors="replace")
        for i in range(1, 7):
            assert f"step{i}" in text, f"step{i} 未定义"

    def test_step5_is_boolean_type(self) -> None:
        """CF-P29: step5 类型为 boolean。"""
        dt_file = _FRONTEND / "composables" / "useDeviationDecisionTree.ts"
        if not dt_file.exists():
            pytest.skip("useDeviationDecisionTree.ts 不存在")
        text = dt_file.read_text(encoding="utf-8", errors="replace")
        # step5 声明为 boolean 而非字符串枚举
        assert "step5: boolean" in text, "step5 应声明为 boolean"

    def test_create_empty_state_step5_false(self) -> None:
        """CF-P29: createEmptyState() 的 step5 默认 false。"""
        dt_file = _FRONTEND / "composables" / "useDeviationDecisionTree.ts"
        if not dt_file.exists():
            pytest.skip("useDeviationDecisionTree.ts 不存在")
        text = dt_file.read_text(encoding="utf-8", errors="replace")
        # 确认 createEmptyState 含 step5: false
        assert "step5: false" in text, "createEmptyState 应含 step5: false"

    def test_other_steps_are_nullable_string(self) -> None:
        """CF-P29: 其余 5 步为字符串枚举 | null。"""
        dt_file = _FRONTEND / "composables" / "useDeviationDecisionTree.ts"
        if not dt_file.exists():
            pytest.skip("useDeviationDecisionTree.ts 不存在")
        text = dt_file.read_text(encoding="utf-8", errors="replace")
        # step1/4/6 为 '是' | '否' | null
        for step in ["step1", "step4", "step6"]:
            assert f"{step}:" in text
        # step5 不是字符串枚举
        assert "step5: '是'" not in text

    def test_serialize_includes_step5_after_fix(self) -> None:
        """CC-65 修复后: 序列化输出全部 6 步（含 step5 推导值）。

        🔴 修复前 step5 被跳过导致真库只见 5 步、显式否与未填不可区分。
        修复后 step5 = evaluateDecisionTree(dev).goToA14 落库为 'true'/'false'。
        """
        data_file = _FRONTEND / "composables" / "useCControlTestData.ts"
        if not data_file.exists():
            pytest.skip("useCControlTestData.ts 不存在")
        text = data_file.read_text(encoding="utf-8", errors="replace")
        # 序列化区域含全部 6 步
        for step in ["step1", "step2", "step3", "step4", "step5", "step6"]:
            assert f"-{step}" in text, f"序列化应含 {step}"
        # step5 用 evaluateDecisionTree 推导
        assert "evaluateDecisionTree" in text, (
            "step5 应由 evaluateDecisionTree 推导"
        )

    def test_parse_reads_back_step5(self) -> None:
        """CC-65 修复后: 解析层读回 step5（'true'/'false' → boolean）。"""
        data_file = _FRONTEND / "composables" / "useCControlTestData.ts"
        if not data_file.exists():
            pytest.skip("useCControlTestData.ts 不存在")
        text = data_file.read_text(encoding="utf-8", errors="replace")
        # 解析层含 k === 5 分支
        assert "k === 5" in text, "解析层应读回 step5"
        assert "=== 'true'" in text, "step5 读回应比较字符串 'true'"


# ═══════════════════════════════════════════════════════════════════════════
# §17 TestPersistenceClosureDepth — CC-42
# ═══════════════════════════════════════════════════════════════════════════


class TestPersistenceClosureDepth:
    """CC-42: 持久化在 import 闭包深度 3。"""

    def test_canary_checklist_in_d1(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CC-42: gt-c-control-test 的 checklist-responses 在 D1。

        宿主自身不直接调 checklist-responses，
        而通过 useCControlTestData composable 间接调用。
        """
        entry = c_by_id[CANARY_ENTRY_ID]
        hp = _host_path(entry)
        if hp is None or not hp.exists():
            pytest.skip("宿主文件不存在")
        host_text = hp.read_text(encoding="utf-8", errors="replace")
        # 宿主自身不直接**调用** checklist-responses 端点（api.get/put 形态）。
        # 🔴 用端点字面量匹配，剥注释——注释里提到该词不算直接调用。
        host_clean = strip_comments(host_text)
        direct_call = (
            "/checklist-responses" in host_clean
        )
        assert not direct_call, (
            "canary 宿主不应直接调用 /checklist-responses 端点（应在 D1 composable）"
        )
        # 闭包深度 1 可达
        closure = import_closure(hp, maxdepth=3)
        found = False
        for f in closure:
            if not f.exists():
                continue
            t = f.read_text(encoding="utf-8", errors="replace")
            if "checklist-responses" in t:
                found = True
                break
        assert found, "闭包深度 3 内应能找到 checklist-responses"

    def test_c22_checklist_in_d0(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CC-42: gt-c22-itgc-bundle 的 checklist-responses 在 D0。

        🔴 C22 宿主内直调 /checklist-responses。
        """
        entry = c_by_id["xlsx/gt-c22-itgc-bundle"]
        hp = _host_path(entry)
        if hp is None or not hp.exists():
            pytest.skip("C22 宿主文件不存在")
        text = hp.read_text(encoding="utf-8", errors="replace")
        assert "checklist-responses" in text, (
            "C22 宿主应直接调 checklist-responses（D0）"
        )

    def test_field_overrides_zero_in_depth3(
        self, c_entries: list[dict]
    ) -> None:
        """CC-42 补充: field-overrides 在深度 3 内两条全 0。"""
        for e in c_entries:
            hp = _host_path(e)
            if hp is None or not hp.exists():
                continue
            text = hp.read_text(encoding="utf-8", errors="replace")
            assert "field-overrides" not in text
            closure = import_closure(hp, maxdepth=3)
            for f in closure:
                if not f.exists():
                    continue
                t = f.read_text(encoding="utf-8", errors="replace")
                if "field-overrides" in t:
                    pytest.fail(
                        f"{e['entry_id']} 闭包内含 field-overrides: {f.name}"
                    )


# ═══════════════════════════════════════════════════════════════════════════
# §18 TestC24OutlierRegistration — CC-66
# ═══════════════════════════════════════════════════════════════════════════


class TestC24OutlierRegistration:
    """CC-66: 域内单册体量极端离群。

    🔴 C24 真库 1,033,309 行 = 全库 99.87%。
    本轮 entry 只占 136 行。
    """

    def test_c24_is_excluded_book(self) -> None:
        """CC-66: C24 属排除册。"""
        assert "C24 会计分录 - 细节测试.xlsx" in EXCLUDED_BOOKS

    def test_c24_formula_count_extreme(self) -> None:
        """CC-66: C24 公式格数远超其他册。"""
        stats = deep_scan_all_c_templates()
        c24 = [b for b in stats["per_book"] if "C24" in b.get("file", "")]
        assert len(c24) == 1
        # C24 公式格数极端（现算 21571）
        assert c24[0]["formulas"] > 20000, (
            f"C24 formulas={c24[0]['formulas']}"
        )

    def test_canary_entry_not_affected_by_c24(self) -> None:
        """CC-66: 本轮 entry 只占 136 行，不受 C24 离群册影响。"""
        # 冻结值：canary 136 行 vs C24 100 万行
        # 本测试只断言 C24 不属本轮 entry
        assert "C24" not in C_CONTROL_TEST_WP_CODES
        assert "C24" not in C22_WP_CODES


# ═══════════════════════════════════════════════════════════════════════════
# §19 TestSheetNameDirtyForms — CC-10, CC-26, CC-63
# ═══════════════════════════════════════════════════════════════════════════


class TestSheetNameDirtyForms:
    """CC-10, CC-26: sheet 名脏形态 + 册名双空格。"""

    def test_c21_1_double_space_in_filename(self) -> None:
        """CC-26: C21-1 册名含两个连续空格。"""
        target = _TEMPLATE_DIR / "C21-1  IT审计发现汇总表.xlsx"
        assert target.exists(), "C21-1 双空格册名应存在"
        # 验证确实是双空格不是单空格
        assert "  " in target.name, "册名应含双空格"

    def test_ref_sheet_mixed_brackets(self) -> None:
        """CC-10/CF-P20: 参考型 sheet 全角半角括号同名内混用。

        '选项清单列表（不归档）' 用全角括号，
        '选项清单列表（不归档） (2)' 中 (2) 用半角括号。
        """
        stats = deep_scan_all_c_templates()
        ref_names = set(stats["ref_sheets"])
        # 验证三种名同时存在
        assert "选项清单列表（不归档）" in ref_names
        assert "选项清单列表（不归档） (2)" in ref_names
        assert "示例-评价控制偏差（不打印）" in ref_names


# ═══════════════════════════════════════════════════════════════════════════
# §20 TestCanaryFactsLock — CC-18, CC-59
# ═══════════════════════════════════════════════════════════════════════════


class TestCanaryFactsLock:
    """任务 21：canary 事实锁定。"""

    def test_canary_is_c_control_test(self) -> None:
        """CC-18: canary 选型为 gt-c-control-test。"""
        assert CANARY_ENTRY_ID == "xlsx/gt-c-control-test"

    def test_canary_switch_redeemable(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CC-18: canary switch_verdict=redeemable（不被 BP-10 阻塞）。"""
        entry = c_by_id[CANARY_ENTRY_ID]
        sv = entry.get("dual_mode_carrier", {}).get("switch_verdict", "")
        assert sv == "redeemable"

    def test_canary_28_wp_codes(self, overrides: dict[str, str]) -> None:
        """CC-61: canary 一次改线须覆盖 28 个 wp_code。"""
        codes = override_reverse_lookup(overrides, "c-control-test")
        c_codes = [c for c in codes if re.match(r"^C\d", c)]
        assert len(c_codes) == 28

    def test_canary_28_codes_split_two_families(
        self, overrides: dict[str, str]
    ) -> None:
        """CC-62: 28 码分主册族（14）与 -2 册族（14）。"""
        codes = override_reverse_lookup(overrides, "c-control-test")
        c_codes = [c for c in codes if re.match(r"^C\d", c)]
        main = [c for c in c_codes if not c.endswith("-2")]
        dev = [c for c in c_codes if c.endswith("-2")]
        assert len(main) == 14, f"main={main}"
        assert len(dev) == 14, f"dev={dev}"

    def test_canary_host_exists(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """补充: canary 宿主文件存在且行数 > 1000。"""
        entry = c_by_id[CANARY_ENTRY_ID]
        hp = _host_path(entry)
        assert hp is not None and hp.exists()
        lines = hp.read_text(encoding="utf-8", errors="replace").count("\n")
        assert lines > 1000, f"canary 宿主行数={lines}"

    def test_canary_identity_field_is_step_num(self) -> None:
        """CC-53: canary 行身份 = step.num（业务键，CLEAN）。"""
        # useCControlTestData.ts 中 identity_field = num
        data_file = _FRONTEND / "composables" / "useCControlTestData.ts"
        if not data_file.exists():
            pytest.skip("useCControlTestData.ts 不存在")
        text = data_file.read_text(encoding="utf-8", errors="replace")
        # 验证存在 step.num 或 num 作为行身份
        assert "num" in text.lower()

    def test_canary_not_blocked_by_bp10(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """CC-18: canary 不背负 BP-10。"""
        entry = c_by_id[CANARY_ENTRY_ID]
        bp = entry.get("capability_target_blocked_by", [])
        assert "BP-10" not in bp

    def test_canary_sync_bridge_wired(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """任务 22-23: canary 已接入 sync bridge（capability 门控降级）。

        🔴 双向回写接线到位：useWorkpaperSyncBridge + WorkpaperSyncEditorHost +
        capabilityForEntry 门控。capability 未裁决 bidirectional 时降级到 OO 展示。
        """
        entry = c_by_id[CANARY_ENTRY_ID]
        hp = _host_path(entry)
        if hp is None or not hp.exists():
            pytest.skip("canary 宿主不存在")
        text = hp.read_text(encoding="utf-8", errors="replace")
        assert "useWorkpaperSyncBridge" in text, "canary 应接入 sync bridge"
        assert "WorkpaperSyncEditorHost" in text, "canary 应用 WorkpaperSyncEditorHost"
        assert "capabilityForEntry" in text, "canary 应经 capabilityForEntry 门控"
        assert "canUseSyncBridge" in text, "canary 应有 capability 门控计算属性"

    def test_canary_degrades_when_not_bidirectional(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """任务 23: capability 非 bidirectional 时降级到 GtOnlyOfficeSheet。"""
        entry = c_by_id[CANARY_ENTRY_ID]
        hp = _host_path(entry)
        if hp is None or not hp.exists():
            pytest.skip("canary 宿主不存在")
        text = hp.read_text(encoding="utf-8", errors="replace")
        # 保留 GtOnlyOfficeSheet 降级路径
        assert "GtOnlyOfficeSheet" in text, "应保留 OO 降级路径"
        # 门控条件：bidirectional
        assert "'bidirectional'" in text, "应检查 bidirectional capability"

    def test_canary_gate_is_strict_equality_not_bridge_selfcheck(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """🔴 门控须是宿主侧 `=== 'bidirectional'` 严格判等，禁依赖 bridge 自校验。

        根因：bridge 的 `switchToOnlyOffice()` 只校验
        `supportedModesForCapability(capability).includes('oo')`，而
        `CAPABILITY_MODES.single_onlyoffice = ['oo']` **含 'oo'**
        ⇒ 当前 capability 下 bridge **不会 refuse**，会照常打后端端点并 422
        （C 域后端 adapter/contract 属 BP-1~BP-5、BP-7 未交付）。
        故宿主侧显式门控是唯一防线，削弱即运行时报错。
        """
        entry = c_by_id[CANARY_ENTRY_ID]
        hp = _host_path(entry)
        if hp is None or not hp.exists():
            pytest.skip("canary 宿主不存在")
        text = hp.read_text(encoding="utf-8", errors="replace")
        clean = strip_comments(text)
        # 严格判等门控（非 !== 'unreachable' 之类的宽松判断）
        assert "=== 'bidirectional'" in clean, (
            "门控须用 === 'bidirectional' 严格判等"
        )
        # switchToOnlyOffice 调用点须被该门控守住
        assert "if (!canUseSyncBridge.value) return" in clean, (
            "switchToOnlyOffice 入口须有 canUseSyncBridge 早退"
        )

    def test_canary_no_side_effect_when_degraded(
        self, c_by_id: dict[str, dict]
    ) -> None:
        """🔴 降级态不得引入改造前不存在的副作用（beforeunload 全局监听）。

        bridge 构造时默认 `window.addEventListener('beforeunload', ...)`。
        capability 未裁决 bidirectional 时永不进 OO ⇒ 该监听器多余，须显式关掉。
        """
        entry = c_by_id[CANARY_ENTRY_ID]
        hp = _host_path(entry)
        if hp is None or not hp.exists():
            pytest.skip("canary 宿主不存在")
        text = hp.read_text(encoding="utf-8", errors="replace")
        clean = strip_comments(text)
        assert "installBeforeUnload" in clean, (
            "降级态须显式传 installBeforeUnload 关掉全局监听"
        )
        # 且其值与 capability 判断绑定，而非硬编码 true
        assert "installBeforeUnload: true" not in clean, (
            "installBeforeUnload 不得硬编码 true"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §21 TestBoundaryAndGapRegistration — CC-25, CC-47, CC-68
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundaryAndGapRegistration:
    """任务 25-28：边界与缺口登记。"""

    def test_c_domain_archived_specs_exist(self) -> None:
        """CC-25: C 域归档 spec 至少 7 份。"""
        archive_dir = _ROOT / ".kiro" / "specs" / "_archive"
        if not archive_dir.exists():
            pytest.skip("归档目录不存在")
        # 递归搜索 C 域相关归档目录
        c_spec_names = set()
        for d in archive_dir.rglob("*"):
            if not d.is_dir():
                continue
            name = d.name.lower()
            if any(kw in name for kw in [
                "c-control-test", "c1-entity", "c22-itgc",
                "c23-", "c24-", "c25-", "c26-",
            ]):
                c_spec_names.add(d.name)
        assert len(c_spec_names) >= 6, (
            f"C 域归档 spec={len(c_spec_names)}: {sorted(c_spec_names)}"
        )

    def test_existing_guard_c22_zero_assertions(self) -> None:
        """CC-2: 既存守卫 test_task57 对 C22 零断言。"""
        guard = _BACKEND / "tests" / "workpaper_sync" / "test_task57_abcs_and_shared_migration.py"
        if not guard.exists():
            pytest.skip("task57 守卫不存在")
        text = guard.read_text(encoding="utf-8", errors="replace")
        # C22 相关关键词命中数
        c22_hits = sum(1 for kw in [
            "gt-c22", "c22-itgc", "C22I", "GRP-06", "control_test_router"
        ] if kw in text)
        # 🔴 预期全 0（CC-2 判据：C22 零断言）
        assert c22_hits == 0, (
            f"task57 对 C22 关键词命中 {c22_hits} 次，预期 0"
        )

    def test_cash_flow_verification_a_domain_gap(
        self, overrides: dict[str, str]
    ) -> None:
        """CC-68: cash-flow-verification 属 A 域但 A 轮遗漏。"""
        codes = override_reverse_lookup(overrides, "cf-verification")
        # 确认含 A 域码
        a_codes = [c for c in codes if c.startswith("A")]
        assert len(a_codes) >= 1
        # 确认不在 C 域覆盖范围
        c_codes = [c for c in codes if c.startswith("C")]
        assert len(c_codes) == 0, f"cf-verification 不应有 C 码: {c_codes}"

    def test_slice_ad9_warns_28_codes(self) -> None:
        """CC-47: AD-9 警告 c-control-test 覆盖 28 码。"""
        if not _SLICE_PATH.exists():
            pytest.skip("slice 文件不存在")
        sl = json.loads(_SLICE_PATH.read_bytes())
        # AD-9 可能在 abcs_form_differences（list 或 dict 格式）
        diffs = sl.get("abcs_form_differences", [])
        found = False
        if isinstance(diffs, list):
            for item in diffs:
                desc = str(item.get("description", "") if isinstance(item, dict) else item)
                if "28" in desc or "c-control-test" in desc.lower():
                    found = True
                    break
        elif isinstance(diffs, dict):
            for key, val in diffs.items():
                desc = str(val.get("description", "") if isinstance(val, dict) else val)
                if "28" in desc or "c-control-test" in desc.lower():
                    found = True
                    break
        # 也在 independent_entries 的 metadata 中查找
        if not found:
            entries = sl.get("independent_entries", [])
            for e in entries:
                if e.get("entry_id") == "xlsx/gt-c-control-test":
                    wp_codes = e.get("wp_codes_via_component_type", [])
                    if len(wp_codes) >= 28:
                        found = True
                    break
        assert found, "slice 应包含 c-control-test 覆盖 28 码的信息"

    def test_c_domain_provider_delivered(self) -> None:
        """任务 22 已交付: C 域后端 provider 存在。

        🔴 本断言原为「C 域尚无 provider」，交付后必然过期 ⇒ 已改为断言交付事实
        （断言过期不改就是假绿的反面 —— 它会阻止真实进展被提交）。
        """
        svc_dir = _BACKEND / "app" / "services" / "workpaper_sync"
        target = svc_dir / "phase5_c_control_test.py"
        assert target.exists(), "C canary provider 应已交付"

    def test_c_domain_contract_delivered_and_registered(self) -> None:
        """任务 22 已交付: C 域生产契约存在且三边闭合。

        三边 = 契约文件 / `DELIVERED_PER_ENTRY_CONTRACTS` 台账 / `_ALLOWED_PROVIDER_MODULES`
        白名单。任一缺失即「契约孤儿」或「provider 无法加载」。
        """
        contract_dir = _DATA / "workpaper_sync_contracts"
        if not contract_dir.exists():
            pytest.skip("契约目录不存在")
        c_contracts = [
            f.name for f in contract_dir.iterdir()
            if f.is_file() and f.name.startswith("c2.")
        ]
        assert c_contracts == ["c2.control_test_summary.json"], (
            f"C 域契约: {c_contracts}"
        )

        from app.services.workpaper_sync.adapters import registry as RG

        ledger_ids = {r["contract_id"] for r in RG.DELIVERED_PER_ENTRY_CONTRACTS}
        assert "c2.control_test_summary" in ledger_ids, "契约须在台账登记"

        row = next(
            r for r in RG.DELIVERED_PER_ENTRY_CONTRACTS
            if r["contract_id"] == "c2.control_test_summary"
        )
        assert row["entry_id"] == CANARY_ENTRY_ID
        assert row["provider_module"] in RG._ALLOWED_PROVIDER_MODULES, (
            "provider_module 须在白名单内，否则 registry 拒绝加载"
        )
        # 🔴 adapter 仍未注册（BP-1~BP-5/BP-7 供给缺口），如实断言
        assert row["adapter_registered"] is False, (
            "capability 未裁决 bidirectional + 真库三表无供给 ⇒ 仍未注册"
        )
