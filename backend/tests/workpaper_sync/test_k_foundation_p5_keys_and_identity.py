# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 1 Task 7~8 + 10：键全集 / 行身份四族 / removeRow。

spec: k-cycle-sync-foundation-and-first-canary
Task 7:  KC-5 三个命名空间必须分清
Task 8:  KC-6 行身份四族判别器（与 J 统一判别式）
Task 10: KC-7 removeRow 契约需四元组
Property: KF-P16, KF-P17, KF-P18, KF-P19, KF-P20, KF-P21, KF-P22, KF-P24, KF-P25

═══ 判据口径（🔴 两处与 design.md 的口径差异已如实登记）═══

**① 键全集**：design.md 的 1065 是**真库现读**口径（`checklist_responses` 表里
   实际落库的键）。前端源码字面量扫描得 **753**（纯字面量）/ **899**（含 `${}`
   插值模板）。三个口径都对，混用会算错。本文件验前端侧两个口径 + 它们的差集
   形态；真库侧 1065 归 Task 9（需 PG）。

**② removeRow**：design.md 的「36 种 / 124 站点」是定义 + 调用点的混合口径。
   实测：**函数定义处 13 种**（arity=1 8 种 / arity=2 5 种）、
   **定义+调用点 34 种 / 199 站点**。契约字段的四元组按**定义处**取，
   因为那才是 API 形状。

═══ 改造前基线（append-only，不随收敛回填）═══

- 四族 a=32 / b=13 / c=3 / total=48 / defect=45
- 逐 entry defect 9 条：K1 3 · K3 1 · K5 7 · K6 7 · K7 6 · K8 8 · K9 7 · K11 4 · K12 2
- 零缺陷 4 条：K2 / K4 / K10 / K13
- 三份 spec 切分：lane1 24 / lane2 21 / foundation(K10) 0
- derived_total 尾部 77 / 尾部+中置 83 / 仅中置 6 个键逐个等值

🔴 **位置化行身份是逐 lane 推进的**（lane 2 的 5 条已在其 Task 13 收敛）。
本文件的 defect 判据一律走 **收敛账本**（`bp8_expected_*`）：
「现算 == 基线 − 已收敛量」+「基线未被篡改」+「未收敛部分没退化」三侧同验。
直接把 45 改成 24 会丢掉基线这条审计轨迹，写死 45 则一收敛就假红。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP5_INDEXES,
    BP8_BASELINE_DEFECT,
    BP8_BASELINE_DEFECT_BY_ENTRY,
    BP8_BASELINE_FAMILY,
    BP8_BASELINE_TOTAL_HITS,
    BP8_BASELINE_ZERO_DEFECT_ENTRIES,
    BP8_CONVERGED_ENTRIES,
    BP8_CONVERGED_FAMILY,
    BP8_CONVERGED_FAMILY_BY_LANE,
    DATA,
    K_INDEXES,
    ROOT,
    arity_of,
    bp8_expected_defect_by_entry,
    bp8_expected_defect_total,
    bp8_expected_family,
    business_keys,
    cached_text,
    defect_by_entry,
    derived_total_keys,
    display_seq_hits,
    entry_of_path,
    family_census,
    family_of,
    k_domain_files,
    positional_identity_hits,
    positional_remove_row_sites,
    remove_row_definitions,
    remove_row_sites,
    strip_comments,
    WP_COMPONENTS,
    WP_COMPOSABLES,
)


SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


# ════════════════════════════════════════════════════════════════════════════
# Task 7 / KF-P16~P17：三个命名空间
# ════════════════════════════════════════════════════════════════════════════
class TestKFP16BusinessKeyUniverse:
    """KC-5：业务持久化键全集（前端字面量口径）。"""

    #: 前端纯字面量口径逐 entry 分布（现算）
    EXPECTED_BY_ENTRY = {
        1: 118, 5: 98, 6: 79, 2: 64, 3: 63, 9: 58, 8: 54,
        7: 49, 4: 41, 10: 40, 12: 30, 13: 30, 11: 29,
    }

    def test_literal_key_universe_is_753(self, k_files: list[pathlib.Path]) -> None:
        keys = business_keys(k_files)
        assert len(keys) == 753, f"前端字面量键全集：期望 753，实得 {len(keys)}"

    def test_per_entry_distribution_matches(self, k_files: list[pathlib.Path]) -> None:
        keys = business_keys(k_files)
        by_entry: dict[int, int] = {}
        for key in keys:
            m = re.match(r"^K(1[0-3]|[1-9])(?![0-9])", key)
            if m:
                n = int(m.group(1))
                by_entry[n] = by_entry.get(n, 0) + 1
        assert by_entry == self.EXPECTED_BY_ENTRY, (
            f"逐 entry 键分布漂移：\n实得 {dict(sorted(by_entry.items()))}"
        )
        assert sum(by_entry.values()) == 753

    def test_all_13_entries_have_keys(self, k_files: list[pathlib.Path]) -> None:
        """13 条 entry 全部有业务键（无空分母）。"""
        assert set(self.EXPECTED_BY_ENTRY) == set(K_INDEXES)

    def test_interpolated_template_keys_are_a_separate_caliber(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 含 `${}` 插值的模板键是**另一口径**（899 vs 753，多 146）。

        它们不是独立键，是**运行时拼出来的键模板**（如 `K1-1-${prefix}-${rowKey}-begin`）。
        判据混用两个口径会把模板当实键算。
        """
        rx_wide = re.compile(r"['\"`](K(?:1[0-3]|[1-9])-[^'\"`\s]+)['\"`]")
        wide: set[str] = set()
        for p in k_files:
            src = strip_comments(cached_text(p))
            wide |= {m.group(1) for m in rx_wide.finditer(src)}
        narrow = set(business_keys(k_files))
        assert len(wide) == 899, f"宽口径期望 899，实得 {len(wide)}"
        extra = wide - narrow
        assert len(extra) == 146, f"差集期望 146，实得 {len(extra)}"
        # 🔴 差集是两类非键内容，各自都不是业务键：
        #   ① 含 `${}` 插值的**键模板**（运行时拼装）
        #   ② 含中文的**提示文案 / 文件名**（如 `K6-2数据解析失败` / `K5-5_弃置费用_模板.xlsx`）
        interp = [k for k in extra if "${" in k]
        chinese = [k for k in extra if re.search(r"[\u4e00-\u9fff]", k)]
        unexplained = [
            k for k in extra
            if "${" not in k and not re.search(r"[\u4e00-\u9fff]", k)
        ]
        assert interp, "差集里没有插值模板 ⇒ 口径解释①失效"
        assert chinese, "差集里没有中文文案 ⇒ 口径解释②失效"
        assert unexplained == [], (
            f"差集里有既非插值也非中文的项 {unexplained[:5]}"
            " ⇒ 窄口径正则可能漏了真实键"
        )
        assert len(interp) + len(chinese) >= len(extra) - 5, (
            "两类解释覆盖不了差集的绝大部分 ⇒ 须补口径说明"
        )


class TestKFP17ReviewSessionNamespace:
    """🔴 KC-5：复核会话键属另一命名空间，须显式排除。"""

    def test_review_session_keys_are_not_in_frontend_literals(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """`K{n}-review-session-{14位时间戳}` 在前端源码里 0 命中。

        🔴 它们是**运行时生成**的键（时间戳），只存在于真库。design.md 的
        9 个是真库现读值。前端侧应查「生成该键的模板」而不是键本身。
        """
        keys = business_keys(k_files)
        literal_sessions = [k for k in keys if "review-session" in k]
        assert literal_sessions == [], (
            f"前端字面量里出现了 review-session 键 {literal_sessions}"
            " ⇒ 它们不再是运行时生成，口径须改"
        )

    def test_review_session_keys_are_generated_by_backend_not_frontend(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 生成点在**后端**（`review_prompt` 服务），前端 K 域 0 命中。

        这解释了为什么前端字面量扫描找不到这 9 个键：它们由后端在写
        `checklist_responses` 时生成 `item_id`，前端只是被动读取。
        ⇒ 契约排除这批键时不能指望前端侧有锚点可查。
        """
        # 前端 K 域 0 命中（已在上一条验过，此处两侧都验）
        fe_hits = [
            p.name for p in k_files
            if "review-session" in strip_comments(cached_text(p))
        ]
        assert fe_hits == [], f"前端 K 域出现 review-session：{fe_hits}"
        # 后端有生成点
        backend_dir = ROOT / "backend" / "app"
        rx = re.compile(r"review-session")
        be_hits: list[str] = []
        for p in backend_dir.rglob("*.py"):
            try:
                if rx.search(p.read_text(encoding="utf-8")):
                    be_hits.append(p.relative_to(ROOT).as_posix())
            except (UnicodeDecodeError, OSError):
                continue
        assert be_hits, (
            "后端也找不到 review-session 生成点 ⇒ 真库里的 9 个键来源不明，"
            "契约的「显式排除」缺乏可复算依据"
        )

    def test_per_row_split_keys_are_runtime_generated_too(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """per-row 拆键 `K{n}-1-r-{base36}-{begin|unadj}` 同样是运行时生成。"""
        keys = business_keys(k_files)
        literal_per_row = [
            k for k in keys
            if re.match(r"^K(?:1[0-3]|[1-9])-\d+-r-[0-9a-z]{6}-(?:begin|unadj)$", k)
        ]
        assert literal_per_row == [], (
            f"前端字面量里出现了 per-row 实键 {literal_per_row} ⇒ 口径须改"
        )
        # 但生成模板必须存在
        rx = re.compile(r"-r\$\{|-\$\{.*rowKey|r\$\{i\}")
        hit = [p.name for p in k_files if rx.search(strip_comments(cached_text(p)))]
        assert hit, "找不到 per-row 键的生成模板"


# ════════════════════════════════════════════════════════════════════════════
# Task 8 / KF-P18~P22：行身份四族判别器
# ════════════════════════════════════════════════════════════════════════════
class TestKFP18FamilyDiscriminator:
    """KC-6：三族互斥且并集 == total。"""

    def test_family_census_follows_the_convergence_ledger(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 现算 == 改造前基线 − 已收敛量（收敛账本，见 `k_foundation_facts`）。

        位置化行身份逐 lane 推进 ⇒ 判据不能写死 32/13/45，否则 lane 2 一收敛
        就假红；也不能直接改成 19/5/24，否则丢掉改造前基线这条审计轨迹。
        """
        cen = family_census(k_files)
        exp = bp8_expected_family()
        for fam in ("a", "b", "c"):
            assert cen[fam] == exp[fam], (
                f"family_{fam}：基线 {BP8_BASELINE_FAMILY[fam]} "
                f"− 已收敛 {BP8_CONVERGED_FAMILY.get(fam, 0)} = {exp[fam]}，"
                f"实得 {cen[fam]}"
            )
        assert cen["defect"] == bp8_expected_defect_total()
        assert cen["total"] == sum(exp.values())

    def test_baseline_is_not_tampered_with(self) -> None:
        """🔴 改造前基线与 slice 登记逐条等值（防止把基线改小来「通过」）。"""
        inv = json.loads(SLICE_PATH.read_text(encoding="utf-8"))[
            "dynamic_row_identity"
        ]["positional_identity_inventory"]
        assert inv["total_hits"] == BP8_BASELINE_TOTAL_HITS
        assert inv["defect_hits_total"] == BP8_BASELINE_DEFECT
        assert inv["family_a_pure_ordinal"]["count"] == BP8_BASELINE_FAMILY["a"]
        assert inv["family_b_index_as_fallback"]["count"] == BP8_BASELINE_FAMILY["b"]
        assert (
            inv["family_c_generated_opaque_must_not_be_flagged"]["count"]
            == BP8_BASELINE_FAMILY["c"]
        )

    def test_family_c_is_untouched_by_convergence(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 family_c 不参与修复（非缺陷）⇒ 收敛前后恒等 3 处。"""
        assert family_census(k_files)["c"] == BP8_BASELINE_FAMILY["c"] == 3

    def test_three_families_are_mutually_exclusive(self) -> None:
        """判别式是三行布尔表达式，互斥且穷尽。"""
        cases = {
            "`row-${idx}-${Date.now()}`": "c",
            "`row-${idx}`": "a",
            "raw.rowKey ?? `row-${idx}`": "b",
            "String(raw?.id || `grant-${idx}-${Date.now()}`)": "b",
        }
        for value, expected in cases.items():
            assert family_of(value) == expected, (
                f"{value!r} 应归 family_{expected}，实得 family_{family_of(value)}"
            )

    def test_union_equals_total(self, k_files: list[pathlib.Path]) -> None:
        cen = family_census(k_files)
        assert cen["a"] + cen["b"] + cen["c"] == cen["total"]
        assert cen["a"] + cen["b"] == cen["defect"]


class TestKFP19DefectByEntry:
    """KC-6：逐 entry defect 9 条 + 零缺陷 4 条。"""

    #: 改造前基线（9 条有缺陷的 entry）—— append-only，不随收敛回填
    BASELINE = BP8_BASELINE_DEFECT_BY_ENTRY
    ZERO_DEFECT_BASELINE = BP8_BASELINE_ZERO_DEFECT_ENTRIES

    def test_defect_distribution_follows_the_ledger(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """现算分布 == 基线去掉已收敛 entry（一条不多、一条不少）。"""
        actual = dict(defect_by_entry(k_files))
        expected = bp8_expected_defect_by_entry()
        assert actual == expected, (
            f"逐 entry defect 漂移：\n实得 {dict(sorted(actual.items()))}"
            f"\n期望 {dict(sorted(expected.items()))}"
            f"\n（基线 {dict(sorted(self.BASELINE.items()))}，"
            f"已收敛 {BP8_CONVERGED_ENTRIES}）"
        )
        assert sum(actual.values()) == bp8_expected_defect_total()

    def test_converged_entries_have_no_residue(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 已收敛的 entry 一处残留都不许有。"""
        actual = defect_by_entry(k_files)
        residue = {
            n: actual[n] for n in BP8_CONVERGED_ENTRIES if actual.get(n, 0)
        }
        assert residue == {}, f"已收敛 entry 仍有缺陷残留：{residue}"

    def test_unconverged_entries_did_not_regress(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 未收敛的 entry 必须**原样保留**基线值（防止顺手改了不在范围内的）。"""
        actual = defect_by_entry(k_files)
        for n, c in self.BASELINE.items():
            if n in BP8_CONVERGED_ENTRIES:
                continue
            assert actual.get(n, 0) == c, (
                f"K{n} 基线 {c} 实得 {actual.get(n, 0)} ⇒ 越界改动或退化"
            )

    def test_zero_defect_entries_grow_by_the_converged_set(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """零缺陷集合 == 基线零缺陷 ∪ 已收敛（两侧都验）。"""
        actual = defect_by_entry(k_files)
        zeros = {n for n in K_INDEXES if actual.get(n, 0) == 0}
        expected = set(self.ZERO_DEFECT_BASELINE) | set(BP8_CONVERGED_ENTRIES)
        assert zeros == expected, (
            f"零缺陷 entry：期望 {sorted(expected)}，实得 {sorted(zeros)}"
        )

    def test_spec_split_of_the_baseline_is_24_21_0(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 **基线** 45 按 BP-5/BP-6 分界恰好二分成 24 / 21，K10 为 0。

        三份 spec 的交付边界由基线切分定义 —— 这个切分是 spec 的结构事实，
        不随收敛进度变化，所以按基线判而不是按现算判。
        """
        lane1 = sum(self.BASELINE.get(n, 0) for n in BP5_INDEXES)
        lane2 = sum(self.BASELINE.get(n, 0) for n in (8, 9, 11, 12, 13))
        foundation = self.BASELINE.get(10, 0)
        assert lane1 == 24, f"lane1（K1~K7）基线期望 24，实得 {lane1}"
        assert lane2 == 21, f"lane2 基线期望 21，实得 {lane2}"
        assert foundation == 0, f"foundation（K10）基线期望 0，实得 {foundation}"
        assert lane1 + lane2 + foundation == BP8_BASELINE_DEFECT

    def test_convergence_progress_is_lane2_only(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 进度判据：**两 lane 都已收敛** ⇒ 全 13 条零缺陷。

        推进轨迹（两 lane 各交付自己那半）：
          · lane 2 Task 13 修 21 处（a 13 + b 8）
          · lane 1 Task 15 修 24 处（a 19 + b 5）
          · 合计 45 == 基线 defect ⇒ 全域归零
        """
        assert set(BP8_CONVERGED_ENTRIES) == set(range(1, 14))
        actual = defect_by_entry(k_files)
        assert sum(actual.values()) == 0, f"仍有位置化缺陷：{dict(actual)}"
        # 两 lane 的族分解相加 == 基线
        l1 = BP8_CONVERGED_FAMILY_BY_LANE["lane1"]
        l2 = BP8_CONVERGED_FAMILY_BY_LANE["lane2"]
        assert l1["a"] + l2["a"] == BP8_BASELINE_FAMILY["a"] == 32
        assert l1["b"] + l2["b"] == BP8_BASELINE_FAMILY["b"] == 13
        assert (l1["a"] + l1["b"], l2["a"] + l2["b"]) == (24, 21)


class TestKFP20FamilyDDisplaySeq:
    """🔴 KC-6：family_d 展示序号**不计入 total_hits**。"""

    def test_display_seq_keys_are_counted_separately(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """`seq` / `seqNo` / `index` 三个键名各自现算。"""
        counts = {k: display_seq_hits(k_files, k) for k in ("seq", "seqNo", "index")}
        assert counts["seq"] > 0, "seq 展示序号分母为空"
        assert counts["seqNo"] > 0, "seqNo 展示序号分母为空"
        assert counts["index"] > 0, "index 展示序号分母为空"
        # 三者合计远大于 0 ⇒ 若计入 total_hits 会把 48 撑大
        assert sum(counts.values()) > 48, (
            "展示序号合计小于 total_hits ⇒ 「不计入」这条判据失去意义"
        )

    def test_display_seq_is_not_in_identity_hits(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """展示序号键名（seq/seqNo）不在身份键（rowId/rowKey/id）集合里。"""
        hits = positional_identity_hits(k_files)
        keys_used = {key for _ref, key, _val in hits}
        assert keys_used <= {"rowId", "rowKey", "id"}, (
            f"身份键集合出现了非预期键名：{keys_used - {'rowId','rowKey','id'}}"
        )
        assert "seq" not in keys_used and "seqNo" not in keys_used


class TestKFP21EntropyPlusFallbackGoesToB:
    """🔴 KC-6：同时含 ENTROPY 与 FALLBACK ⇒ family_b（是缺陷），不是放过。"""

    def test_entropy_plus_fallback_goes_to_b_by_discriminator(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 判据锚**判别式**而不是具体站点。

        原判据锚在 `K7TabDisclosureSoe.vue` 的
        `String(raw?.id || \\`grant-${idx}-${Date.now()}\\`)` 上 —— 那处已被
        lane 1 Task 15 修掉（改成 `newRowIdentity('grant')`）。
        站点会被修，**判别式不会** ⇒ 锚判别式才是稳定判据。
        """
        assert family_of("raw?.id || `grant-${idx}-${Date.now()}`") == "b", (
            "同时含熵与兜底应归 family_b（是缺陷，不是放过）"
        )
        assert family_of("`grant-${idx}-${Date.now()}`") == "c", (
            "只含熵无兜底才归 family_c"
        )
        assert family_of("raw?.id || `grant-${idx}`") == "b"
        # 🔴 两侧都验：那处确已修好（不留旧形态）
        for p in k_files:
            if p.name != "K7TabDisclosureSoe.vue":
                continue
            src = strip_comments(cached_text(p))
            assert not re.search(
                r"raw\?\.id\s*\|\|\s*`grant-\$\{\s*idx\s*\}", src
            ), "该处仍是旧的位置化兜底 ⇒ lane 1 Task 15 未收敛"
            assert "newRowIdentity('grant')" in src, "该处未改走值化身份工厂"
        return

    def test_legacy_site_probe_kept_for_reference(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """（保留原站点扫描逻辑作参考；已修后 target 为 None 属预期。）"""
        target = None
        for p in k_files:
            if p.name != "K7TabDisclosureSoe.vue":
                continue
            src = strip_comments(cached_text(p))
            for line in src.split("\n"):
                if "grant-" in line and "Date.now()" in line and (
                    "||" in line or "??" in line
                ):
                    target = line.strip()
                    break
        assert target is None, (
            f"旧的「熵+兜底」形态仍在：{target!r} ⇒ Task 15 未收敛"
        )
        return
        # 提取身份值部分并判族
        m = re.search(r"(?<![\w$])(?:rowId|rowKey|id)\s*:\s*([^,\n]+)", target)
        value = m.group(1).strip() if m else target
        assert family_of(value) == "b", (
            f"该处应归 family_b（是缺陷），实得 family_{family_of(value)}：{value!r}"
        )

    def test_discriminator_order_matters(self) -> None:
        """判别式顺序：先查 ENTROPY∧¬FALLBACK，再查 FALLBACK。"""
        # 只有熵 ⇒ c（安全）
        assert family_of("`row-${idx}-${Date.now()}`") == "c"
        # 熵 + 兜底 ⇒ b（缺陷）—— 若顺序写错会误判成 c
        assert family_of("raw.id || `row-${idx}-${Date.now()}`") == "b"


class TestKFP22ScanScopeCoversBothOwnerDirs:
    """KC-6：扫描范围必须覆盖两处 owner 目录。"""

    def test_both_owner_dirs_contribute_hits(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """composables/ 与 k{n}/ 两处都有位置化命中（只扫一处会漏一半）。"""
        hits = positional_identity_hits(k_files)
        from_composables = [
            r for r, _k, _v in hits if "/composables/" in r
        ]
        from_entry_dirs = [
            r for r, _k, _v in hits if re.search(r"/workpaper/k(1[0-3]|[1-9])/", r)
        ]
        assert from_composables, "composables/ 目录 0 命中 ⇒ 扫描范围漏了一半"
        assert from_entry_dirs, "k{n}/ 目录 0 命中 ⇒ 扫描范围漏了一半"
        assert len(from_composables) + len(from_entry_dirs) == len(hits), (
            "有命中落在两个 owner 目录之外 ⇒ 扫描范围定义须更新"
        )

    def test_prefix_regex_negative_lookahead_protects_k10_to_k13(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 `(?![0-9])` 负向断言：K1 不能吃掉 K10..K13。"""
        for n in (10, 11, 12, 13):
            found = [p for p in k_files if entry_of_path(p) == n]
            assert found, f"entry_of_path 无法识别 K{n} ⇒ 负向断言写错了"
        # 反证：去掉负向断言后 K10..K13 的文件会被误判成 K1
        naive_rx = re.compile(r"^(?:use|Gt)?[kK](1[0-3]|[1-9])")
        for n in (10, 11, 12, 13):
            files_n = [p for p in k_files if entry_of_path(p) == n]
            assert files_n, f"K{n} 分母为空"
            # 带断言的正则把它们归到 K{n}；朴素正则（贪婪优先 1[0-3]）也对，
            # 真正的陷阱是把 `1[0-3]` 放在 `[1-9]` 之后 —— 那时 K10 会被判成 K1
            bad_rx = re.compile(r"^(?:use|Gt)?[kK]([1-9]|1[0-3])")
            for p in files_n:
                m = bad_rx.match(p.name)
                if m and m.group(1) != str(n):
                    # 确认这就是「交替顺序写错」的陷阱
                    assert m.group(1) == "1", (
                        f"{p.name}: 顺序陷阱应把它误判成 1，实得 {m.group(1)}"
                    )
                    break

    def test_file_name_prefix_wins_over_embedded_other_entry_code(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 真实歧义：`k1AdjK11Writeback.ts` 是 **K1 的文件**（写回 K11）。

        `entry_of_path` 按**文件名前缀**判 owner，不按文件名里出现的其他
        entry 码判。这类跨 entry 写回文件在 K 域真实存在。
        """
        cross = [p for p in k_files if p.name == "k1AdjK11Writeback.ts"]
        assert cross, "k1AdjK11Writeback.ts 不存在 ⇒ 这条歧义登记须撤"
        assert entry_of_path(cross[0]) == 1, (
            "跨 entry 写回文件的 owner 应按前缀判为 K1"
        )
        # 它确实提到 K11（证明歧义是真的不是假想）
        src = strip_comments(cached_text(cross[0]))
        assert "K11" in src, "该文件不提 K11 ⇒ 命名歧义不成立"


# ════════════════════════════════════════════════════════════════════════════
# Task 10 / KF-P24~P25：removeRow 四元组
# ════════════════════════════════════════════════════════════════════════════
class TestKFP24RemoveRowQuadruple:
    """KC-7：契约字段 `row_delete_api_kind` 单值枚举装不下，须四元组。"""

    def test_definition_signatures_are_13_kinds(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """函数定义处 13 种签名（arity=1 8 种 + arity=2 5 种）。"""
        defs = remove_row_definitions(k_files)
        assert len(defs) == 13, (
            f"定义处签名种数：期望 13，实得 {len(defs)}\n{sorted(defs)}"
        )
        by_arity: dict[int, set[str]] = {}
        for params in defs:
            by_arity.setdefault(arity_of(params), set()).add(params)
        assert len(by_arity[1]) == 8, f"arity=1 期望 8 种，实得 {sorted(by_arity[1])}"
        assert len(by_arity[2]) == 5, f"arity=2 期望 5 种，实得 {sorted(by_arity[2])}"

    def test_wide_caliber_is_34_kinds_199_sites(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """定义 + 调用点宽口径：34 种 / 199 站点。

        🔴 design.md 的「36 种 / 124 站点」是混合口径。两个口径都对，
        契约的四元组按**定义处**取（那才是 API 形状）。
        """
        sites = remove_row_sites(k_files)
        assert len(sites) == 34, f"宽口径种数：期望 34，实得 {len(sites)}"
        total = sum(len(v) for v in sites.values())
        assert total == 199, f"宽口径站点数：期望 199，实得 {total}"

    def test_arity_2_signatures_need_param_order_and_family(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """arity=2 的 5 种签名各有不同的参数名族 ⇒ 单值枚举装不下。"""
        defs = remove_row_definitions(k_files)
        arity2 = {p for p in defs if arity_of(p) == 2}
        assert len(arity2) == 5
        # 五种的第一个参数名各不相同（section / block / tableKey / side / groupId）
        first_params = set()
        for params in arity2:
            first = params.split(",")[0].strip()
            name = first.split(":")[0].strip()
            first_params.add(name)
        assert len(first_params) == 5, (
            f"arity=2 的首参名应有 5 种，实得 {sorted(first_params)}"
        )

    def test_single_value_enum_cannot_represent_all(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """反证：单值枚举（只记 arity）会把 8 种 arity=1 压成 1 个值。"""
        defs = remove_row_definitions(k_files)
        arity_only = {arity_of(p) for p in defs}
        assert len(arity_only) == 2, "arity 只有 2 个取值"
        assert len(defs) == 13, (
            "13 种签名压成 2 个 arity 值 ⇒ 信息丢失 11 种，必须用四元组"
        )


class TestKFP25PositionalRemoveRowFamily:
    """🔴 KC-7：K **有**下标族（J 无），站点集中在 K2~K7。"""

    def test_positional_family_exists(self, k_files: list[pathlib.Path]) -> None:
        sites = positional_remove_row_sites(k_files)
        assert sites, "下标族 removeRow 站点为 0 ⇒ 与 KC-7 登记矛盾（J 才是 0）"

    def test_positional_sites_concentrate_in_k2_to_k7(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """站点集中在 K2~K7 —— 正是 BP-8 位置化的重叠 entry。"""
        sites = positional_remove_row_sites(k_files)
        entries = set(sites)
        assert entries <= set(range(2, 8)), (
            f"下标族站点出现在 K2~K7 之外：{sorted(entries - set(range(2, 8)))}"
        )
        assert entries == set(range(2, 8)), (
            f"下标族应覆盖 K2~K7 全部，缺 {sorted(set(range(2, 8)) - entries)}"
        )

    def test_positional_param_names_are_the_four_forms(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """四种下标族参数名形态都存在。"""
        defs = remove_row_definitions(k_files)
        all_params = " ".join(defs)
        for name in ("idx", "index", "tableIndex"):
            assert name in all_params, (
                f"下标族参数名 {name} 在定义处 0 命中 ⇒ KC-7 的形态清单须更新"
            )

    def test_positional_identity_and_index_delete_overlap(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 双重叠风险**已消解一半**：身份维度归零，下标删行维度仍在。

        改造前：同一批 entry（K5/K6/K7 等）既有位置化身份又有下标删行 ⇒ 双重叠。
        lane 1 Task 15 把**身份维度**修完 ⇒ 重叠集合为空。
        🔴 但「下标删行」本身**一处没动**（19 个 `idx: number` 签名还在）——
        它归 Task 14 的组合判据管，不是本条的交付物。
        ⇒ 判据翻面为「重叠已空 ∧ 下标族仍非空 ∧ 身份族已空」三条同验。
        """
        idx_entries = set(positional_remove_row_sites(k_files))
        defect_entries = {
            n for n, c in defect_by_entry(k_files).items() if c > 0
        }
        overlap = idx_entries & defect_entries
        assert overlap == set(), (
            f"仍有双重叠 {sorted(overlap)} ⇒ 身份维度未修完"
        )
        # 🔴 下标族**仍在**（这是重叠消解的原因不是「两边都没了」）
        assert idx_entries, "下标族 removeRow 全消失 ⇒ 双重叠登记的前提变了"
        assert {5, 6, 7} <= idx_entries, (
            f"K5/K6/K7 应仍在下标族集里，实得 {sorted(idx_entries)}"
        )
        # 身份族已空
        assert defect_entries == set(), f"身份族残留 {sorted(defect_entries)}"


# ════════════════════════════════════════════════════════════════════════════
# KF-P37：derived_total 双正则（Task 15 的判据，与键全集同源故并入本文件）
# ════════════════════════════════════════════════════════════════════════════
class TestKFP37DerivedTotalDualRegex:
    """🔴 KC-16：正则必须覆盖中置形态（J 轮 7 个，K 放大到 83 个）。"""

    #: 6 个仅中置命中的键（design.md 逐个等值）
    INFIX_ONLY = {
        "K1-8-calc-total-provision",
        "K11-2-total-occurrence",
        "K4-1-subtotal-credit",
        "K4-1-subtotal-debit",
        "K8-2-total-audited",
        "K9-2-total-audited",
    }

    def test_tail_only_regex_gets_77(self, k_files: list[pathlib.Path]) -> None:
        tail = derived_total_keys(k_files, include_infix=False)
        assert len(tail) == 77, f"尾部口径：期望 77，实得 {len(tail)}"

    def test_full_regex_gets_83(self, k_files: list[pathlib.Path]) -> None:
        full = derived_total_keys(k_files, include_infix=True)
        assert len(full) == 83, f"尾部+中置：期望 83，实得 {len(full)}"

    def test_the_six_infix_only_keys_match_design(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 6 个仅中置命中的键逐个等值。"""
        tail = derived_total_keys(k_files, include_infix=False)
        full = derived_total_keys(k_files, include_infix=True)
        infix_only = full - tail
        assert infix_only == self.INFIX_ONLY, (
            f"多 {sorted(infix_only - self.INFIX_ONLY)}，"
            f"缺 {sorted(self.INFIX_ONLY - infix_only)}"
        )
        assert len(infix_only) == 6

    def test_infix_split_across_two_lanes_is_3_and_3(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """6 个仅中置键：lane1 3 个 + lane2 3 个。"""
        lane1 = {"K1-8-calc-total-provision", "K4-1-subtotal-credit", "K4-1-subtotal-debit"}
        lane2 = {"K11-2-total-occurrence", "K8-2-total-audited", "K9-2-total-audited"}
        assert lane1 | lane2 == self.INFIX_ONLY
        assert lane1 & lane2 == set()
        assert len(lane1) == 3 and len(lane2) == 3

    def test_83_keys_are_property_24_non_empty_denominator(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 这 83 个键是 Property 24 的非空分母。"""
        full = derived_total_keys(k_files, include_infix=True)
        assert len(full) > 0, (
            "derived_total 分母为空 ⇒ Property 24 的「回写时不得把派生值当用户录入」"
            "这条在 K 就没有对象可验"
        )
        assert len(full) == 83
