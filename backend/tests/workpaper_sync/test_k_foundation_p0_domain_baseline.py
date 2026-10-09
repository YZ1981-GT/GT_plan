# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 0 前置门：K 域文件集基线与扫描口径。

spec: k-cycle-sync-foundation-and-first-canary
Task 0: 建立 K 域文件集（k_domain_files）与 strip_comments 扫描口径基线
Property: KF-P5

═══ 判据 ═══

KF-P5: K 域生产文件现算 **367**（排除 `GtKamWorkpaper.vue`）；含它则 **368**。
       两侧都验 —— 多一个少一个都红。

strip_comments 的行号保留性已在 test_task53_k_cycle_migration.py 的
TestGuardSelfChecks 里有反向自检，这里**不重复**；只做 foundation spec
独有的精确计数断言和口径两侧验证。
"""
from __future__ import annotations

import pathlib
import re

import pytest

# 🔴 只借**删除账本常量**（单一真源）；p0 的扫描逻辑仍自包含。
from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP5_DELETED_COUNT,
    BP5_DELETED_ORPHAN_NAMES,
    BP5_DUALMODE_ENTRIES_REMAINING,
    BP5_K_DOMAIN_FILES_BASELINE,
    bp5_expected_k_domain_files,
)

_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"
CYCLE_COMPOSABLES = FRONTEND / "composables" / "workpaper"

# 口径常量（直接对齐 design.md 的 KC-22①）
EXPECTED_K_DOMAIN_FILE_COUNT = 367
EXPECTED_K_DOMAIN_FILE_COUNT_WITH_KAM = 368
KAM_HOST = "GtKamWorkpaper.vue"


def _k_cycle_files(*, include_kam: bool = False) -> list[pathlib.Path]:
    """K 域生产文件（口径与 slice 的 `scanned_scope` 逐字一致）。

    🔴 `include_kam` 默认 False：排除 `GtKamWorkpaper.vue`。
    KC-22①: 含它则 368，排除则 367。
    """
    out: list[pathlib.Path] = []
    # ── 1. k1..k13 子目录下的 .ts/.vue（排除 __tests__）
    for n in range(1, 14):
        d = WP_COMPONENTS / f"k{n}"
        if d.is_dir():
            for p in d.rglob("*"):
                if (
                    p.is_file()
                    and p.suffix in (".ts", ".vue")
                    and "__tests__" not in p.as_posix()
                ):
                    out.append(p)
    # ── 2. GtK*.vue 宿主（`^GtK\d+` 排除 KAM）
    for p in sorted(WP_COMPONENTS.iterdir()):
        if p.suffix == ".vue" and re.match(r"^GtK\d+", p.name):
            out.append(p)
        elif include_kam and p.name == KAM_HOST:
            out.append(p)
    # ── 3. composables/ 下匹配 K 循环的 .ts
    for p in sorted(WP_COMPOSABLES.iterdir()):
        if p.suffix == ".ts" and re.match(
            r"^(use)?[kK](1[0-3]|[1-9])(?![0-9])", p.name
        ):
            out.append(p)
    # ── 4. composables/workpaper/k{n}/ 子目录
    for n in range(1, 14):
        d = CYCLE_COMPOSABLES / f"k{n}"
        if d.is_dir():
            for p in d.rglob("*.ts"):
                if "__tests__" not in p.as_posix():
                    out.append(p)
    return sorted(set(out))


def _strip_comments(source: str) -> str:
    """剥块注释 / 行注释 / HTML 注释，行号保持不变（同长空白替换）。"""

    def _blank(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    source = re.sub(r"/\*.*?\*/", _blank, source, flags=re.S)
    source = re.sub(r"<!--.*?-->", _blank, source, flags=re.S)
    source = re.sub(
        r"(?<![:\w\"'`\\])//[^\n]*", lambda m: " " * len(m.group(0)), source
    )
    return source


# ════════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return _k_cycle_files(include_kam=False)


@pytest.fixture(scope="module")
def k_files_with_kam() -> list[pathlib.Path]:
    return _k_cycle_files(include_kam=True)


# ════════════════════════════════════════════════════════════════════════════
# Task 0：K 域文件集精确基线（KF-P5）
# ════════════════════════════════════════════════════════════════════════════
class TestKDomainFileBaseline:
    """KF-P5: K 域生产文件**基线** 367（排除 KAM）/ 368（含 KAM）。

    🔴 lane 1 的 BP-5 处置**删掉了 7 个一阶 orphan** ⇒ 现算走删除账本
    （`bp5_expected_k_domain_files()`）。基线是 append-only 的改造前快照：
    直接把 367 改成 360 会丢掉「删了多少、删的是哪些」这条审计轨迹。
    """

    def test_k_domain_file_count_excluding_kam(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """现算 == 基线 367 − 已删 7。"""
        assert EXPECTED_K_DOMAIN_FILE_COUNT == BP5_K_DOMAIN_FILES_BASELINE == 367, (
            "基线被篡改"
        )
        expected = bp5_expected_k_domain_files()
        assert len(k_files) == expected, (
            f"K 域文件数漂移：基线 {BP5_K_DOMAIN_FILES_BASELINE} − 已删 "
            f"{BP5_DELETED_COUNT} = {expected}，实得 {len(k_files)}"
        )

    def test_k_domain_file_count_including_kam(
        self, k_files_with_kam: list[pathlib.Path]
    ) -> None:
        """现算 == 基线 368 − 已删 7。"""
        expected = bp5_expected_k_domain_files(include_kam=True)
        assert len(k_files_with_kam) == expected, (
            f"含 KAM 的 K 域文件数漂移：期望 {expected}，实得 {len(k_files_with_kam)}"
        )

    def test_the_seven_deleted_orphans_are_really_gone(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 删除范围精确：恰好这 7 个消失，其余 `useK*DualMode.ts` 全在。"""
        names = {p.name for p in k_files}
        for n in BP5_DELETED_ORPHAN_NAMES:
            assert n not in names, f"{n} 仍在 ⇒ BP-5 删除未生效"
        remaining = sorted(
            x for x in names if re.fullmatch(r"useK(1[0-3]|[1-9])DualMode\.ts", x)
        )
        assert len(remaining) == len(BP5_DUALMODE_ENTRIES_REMAINING) == 6, (
            f"剩余 DualMode 文件 {remaining}"
        )
        assert remaining == sorted(
            f"useK{n}DualMode.ts" for n in BP5_DUALMODE_ENTRIES_REMAINING
        )

    def test_kam_is_the_only_difference(
        self,
        k_files: list[pathlib.Path],
        k_files_with_kam: list[pathlib.Path],
    ) -> None:
        """含与不含 KAM 的差集恰好是 GtKamWorkpaper.vue 一个文件。"""
        diff = set(k_files_with_kam) - set(k_files)
        assert len(diff) == 1
        sole = diff.pop()
        assert sole.name == KAM_HOST

    def test_kam_exists_on_disk(self) -> None:
        """GtKamWorkpaper.vue 确实存在（排除是主动行为不是缺失）。"""
        assert (WP_COMPONENTS / KAM_HOST).exists()

    def test_no_k11_through_k13_are_lost_by_prefix_regex(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 前缀正则带 (?![0-9]) 负向断言不能吃掉 K10..K13。"""
        for n in (10, 11, 12, 13):
            assert any(f"/k{n}/" in p.as_posix() for p in k_files), (
                f"k{n} 子目录下的文件未被枚举 ⇒ 正则 (?![0-9]) 写错了"
            )
            assert any(
                f"GtK{n}" in p.name for p in k_files if p.suffix == ".vue"
            ), f"GtK{n}*.vue 宿主未被枚举"

    def test_all_13_hosts_are_present(self, k_files: list[pathlib.Path]) -> None:
        """13 个 K 循环宿主一个不少。"""
        hosts = {
            "GtK1OtherReceivables.vue",
            "GtK2OtherCurrentAssets.vue",
            "GtK3OtherPayables.vue",
            "GtK4OtherCurrentLiabilities.vue",
            "GtK5Provisions.vue",
            "GtK6HeldForSale.vue",
            "GtK7DeferredIncome.vue",
            "GtK8SellingExpenses.vue",
            "GtK9AdminExpenses.vue",
            "GtK10OtherIncome.vue",
            "GtK11AssetImpairmentLoss.vue",
            "GtK12NonOperatingIncome.vue",
            "GtK13NonOperatingExpense.vue",
        }
        found = {p.name for p in k_files if p.suffix == ".vue" and p.name.startswith("GtK")}
        assert hosts == found, (
            f"宿主集合不符：多 {sorted(found - hosts)}，缺 {sorted(hosts - found)}"
        )

    def test_composable_barrel_does_not_exist(self) -> None:
        """KA-P5 / KD-1: composables/index.ts 不存在 ⇒ 无 barrel 可躲，二阶 orphan 恒 0。"""
        barrel = WP_COMPOSABLES / "index.ts"
        assert not barrel.exists(), (
            f"barrel 文件出现了：{barrel} ⇒ 所有 orphan 的二阶判据必须重算"
        )

    def test_scan_directories_cover_four_source_pools(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """四个来源池都有文件（不是某池返回 0 导致总数碰巧对）。"""
        pool_1 = [p for p in k_files if "/k" in p.as_posix() and WP_COMPONENTS in p.parents]
        pool_2 = [
            p for p in k_files
            if p.suffix == ".vue" and p.parent == WP_COMPONENTS and p.name.startswith("GtK")
        ]
        pool_3 = [p for p in k_files if p.parent == WP_COMPOSABLES]
        pool_4 = [p for p in k_files if CYCLE_COMPOSABLES in p.parents]
        assert len(pool_1) > 0, "池 1（k{n}/ 子目录）为空"
        assert len(pool_2) == 13, f"池 2（GtK*.vue）期望 13，实得 {len(pool_2)}"
        assert len(pool_3) > 0, "池 3（composables/ K 循环）为空"
        # 池 4 可能为空（取决于 composables/workpaper/k{n}/ 是否存在）
        # 不做强断言，只记录
        total_from_pools = len(set(pool_1) | set(pool_2) | set(pool_3) | set(pool_4))
        assert total_from_pools == len(k_files), (
            f"四池并集 {total_from_pools} ≠ 总数 {len(k_files)} ⇒ 有文件从非预期路径混入"
        )


# ════════════════════════════════════════════════════════════════════════════
# Task 0：strip_comments 口径门
# ════════════════════════════════════════════════════════════════════════════
class TestStripCommentsBaseline:
    """strip_comments 的行号保留性与口径完整性。"""

    def test_line_count_preserved(self) -> None:
        """剥注释后行数不变。"""
        src = "a\n/* el-segmented\nstill comment */\nb // el-segmented\nc\n"
        out = _strip_comments(src)
        assert len(out.split("\n")) == len(src.split("\n"))
        assert "el-segmented" not in out

    def test_url_double_slash_not_eaten(self) -> None:
        """行注释正则不吃 URL 里的 //。"""
        src = "const url = 'https://example.com/api';\n"
        out = _strip_comments(src)
        assert "https://example.com/api" in out

    def test_block_comment_in_k_host_hides_second_segmented(self) -> None:
        """K 循环实况：宿主剥注释前 2 处 el-segmented，剥后 1 处。"""
        host = WP_COMPONENTS / "GtK11AssetImpairmentLoss.vue"
        if not host.exists():
            pytest.skip("K11 宿主不存在")
        raw = host.read_text(encoding="utf-8")
        before = [
            i for i, l in enumerate(raw.split("\n"), 1)
            if "el-segmented" in l
        ]
        after = [
            i for i, l in enumerate(_strip_comments(raw).split("\n"), 1)
            if "el-segmented" in l
        ]
        assert len(before) == 2, f"前提变了：剥注释前应有 2 处，实得 {before}"
        assert after == [before[0]], (
            f"剥注释后应只剩第一处，实得 {after}"
        )

    def test_all_13_hosts_have_exactly_one_segmented_after_strip(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """KC-15 / KD-7: 剥注释后 13/13 宿主恒 1 处 el-segmented。"""
        hosts = [p for p in k_files if p.suffix == ".vue" and p.name.startswith("GtK")]
        assert len(hosts) == 13
        for host in hosts:
            src = host.read_text(encoding="utf-8")
            stripped = _strip_comments(src)
            sites = [
                i for i, l in enumerate(stripped.split("\n"), 1)
                if "el-segmented" in l
            ]
            assert len(sites) == 1, (
                f"{host.name}: 剥注释后 el-segmented 应恰 1 处，实得 {len(sites)} 处 {sites}"
            )
