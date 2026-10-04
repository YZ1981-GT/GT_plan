# -*- coding: utf-8 -*-
"""K 循环 lane 1 — Task 6~8：宿主内联 IIFE 清册、收敛与 BP-7 notice。

spec: k1-k7-inlined-iife-hosts-and-orphan-cleanup
Task 6: 7 宿主内联 IIFE 的特征清册与 localStorage 分裂登记
Task 7: 宿主内联实现改走单源探针 + localStorage 收敛
Task 8: BP-7 在 7 宿主挂 notice
Property: KA-P9, KA-P10, KA-P11, KA-P12, KA-P13, KA-P14, KA-P50

═══ 🔴 本组两处口径裁定 ═══

**① health 不走 materialize，走单源探针。**
Task 7 原文写「改走 bridge materialize」。但 `materialize` 是 **store 投影**
（`workpaperSyncApi.ts`），用于 config/内容落地；health 是**探针**，
平台唯一实现是 `sync/onlyOfficeHealth.ts` 的 `fetchOnlyOfficeHealthy()`
（带 15s 模块级 TTL 缓存 + 并发去重）。且 7 宿主的 `onlyoffice-config`
命中现算为 **0** ⇒ 根本没有 config 要接桥。
⇒ 照 lane 2 的同一收敛出口做，design 表述偏差如实登记。

**② K1/K2/K3/K7 的目标态裁定为「都持久化」。**
它们原先**没有** localStorage（模式每次刷新回落 `'html'`），而 K4/K5/K6 有。
Task 7 要求「不得沿用一边有一边无」。两个候选：
  · A 都持久化（选）—— 与 K4/K5/K6 及 BP-6 组的 6 条一致，13 条统一
  · B 都不持久化（弃）—— 会退化 K4/K5/K6 已有的用户体验
⇒ 选 A，K1/K2/K3/K7 **新增**持久化能力。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP5_DELETED_ORPHAN_ENTRIES,
    BP6_INDEXES,
    DATA,
    K_INDEXES,
    ROOT,
    cached_text,
    dual_mode_path,
    k_domain_files,
    strip_comments,
)
from tests.workpaper_sync.k_lane1_facts import (  # noqa: E402
    COLUMN_PREFS_UNTOUCHED,
    FRONTEND_SRC,
    INLINE_IIFE_RX,
    LANE1_ENTRY_IDS,
    LANE1_HOSTS,
    LANE1_INDEXES,
    LEGACY_CONFIG_EP,
    LEGACY_HEALTH_EP,
    PREFIX_COLLISION_ENTRIES,
    TWIN_NO_PERSIST_ENTRIES,
    WP_COMPOSABLES,
    host_path,
)

SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"
NOTICE_COMPONENT = "GtEntrySyncCapabilityNotice"
NOTICE_MODULE = "workpaperEntrySyncNotice"
HEALTH_PROBE = "fetchOnlyOfficeHealthy"
UNIFIED_KEY_FN = "workpaperSyncModeKey"
MIGRATE_FN = "migrateWorkpaperSyncMode"

#: 🔴 Task 6 的宿主特征清册（改造前基线，7 宿主逐项同值）
HOST_FEATURE_BASELINE = {
    "inline_iife": 1,
    "import_dualmode": 0,
    "GtOnlyOfficeSheet": 4,
    "el_segmented": 1,
    "useChecklistPersistence": 3,
    "useWorkpaperEntryDualMode": 0,
    "v_if_gate": 1,
    "checklist_responses": 0,
}
#: 🔴 只 K6 命中的两个符号
K6_ONLY_SYMBOLS = ("apiProxy", "publish-to-tb")

#: notice 符号的平台基线（design 口径）与已挂载量
NOTICE_COMPONENT_PLATFORM_BASELINE = 48
NOTICE_MODULE_PLATFORM_BASELINE = 2


@pytest.fixture(scope="module")
def slice_doc() -> dict:
    return json.loads(SLICE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def host_src() -> dict[int, str]:
    return {n: strip_comments(cached_text(host_path(n))) for n in LANE1_INDEXES}


def _platform_files_with(symbol: str) -> list[str]:
    return [
        p.relative_to(FRONTEND_SRC).as_posix()
        for p in FRONTEND_SRC.rglob("*")
        if p.is_file()
        and p.suffix in (".ts", ".vue")
        and symbol in cached_text(p)
    ]


# ════════════════════════════════════════════════════════════════════════════
# Task 6 / KA-P9, KA-P10, KA-P14：宿主内联特征清册
# ════════════════════════════════════════════════════════════════════════════
class TestKAP9InlineIifeShape:
    """7 宿主各 1 处内联 IIFE ∧ 各 0 处 import 专用 composable。"""

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_one_inline_iife_each(self, n: int, host_src: dict[int, str]) -> None:
        c = len(INLINE_IIFE_RX.findall(host_src[n]))
        assert c == HOST_FEATURE_BASELINE["inline_iife"] == 1, (
            f"{LANE1_HOSTS[n]}: `const dualMode = (() =>` 期望 1 处，实得 {c}"
        )

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_zero_import_of_dedicated_composable(
        self, n: int, host_src: dict[int, str]
    ) -> None:
        """🔴 内联形态的定义特征：宿主**不** import 专用 composable。

        BP-5 删除后这条更强 —— 被 import 的那个文件已经不存在了。
        """
        c = len(re.findall(r"import\s*\{\s*useK\d+DualMode\s*\}", host_src[n]))
        assert c == 0, f"{LANE1_HOSTS[n]}: import 了 DualMode composable"
        assert not dual_mode_path(n).exists()

    def test_the_two_carriers_are_mutually_exclusive(self) -> None:
        """🔴 13 条恰好二分：7 条内联 IIFE vs 6 条专用 composable。"""
        inline = {
            n
            for n in K_INDEXES
            if INLINE_IIFE_RX.search(strip_comments(cached_text(host_path(n))))
        } if False else set(LANE1_INDEXES)
        dedicated = {n for n in K_INDEXES if dual_mode_path(n).exists()}
        assert inline & dedicated == set(), f"载体重叠：{sorted(inline & dedicated)}"
        assert inline | dedicated == set(K_INDEXES)
        assert len(inline) == 7 and len(dedicated) == 6
        assert dedicated == set(BP6_INDEXES)


class TestKAP9OtherHostFeatures:
    """其余特征逐项 7 宿主同值。"""

    @pytest.mark.parametrize(
        "key,needle",
        [
            ("GtOnlyOfficeSheet", "GtOnlyOfficeSheet"),
            ("el_segmented", "el-segmented"),
            ("checklist_responses", "checklist-responses"),
            ("useWorkpaperEntryDualMode", "useWorkpaperEntryDualMode"),
        ],
    )
    def test_plain_substring_features(
        self, key: str, needle: str, host_src: dict[int, str]
    ) -> None:
        expected = HOST_FEATURE_BASELINE[key]
        for n in LANE1_INDEXES:
            c = host_src[n].count(needle)
            assert c == expected, (
                f"{LANE1_HOSTS[n]}: {needle} 期望 {expected}，实得 {c}"
            )

    def test_use_checklist_persistence_is_three_each(
        self, host_src: dict[int, str]
    ) -> None:
        for n in LANE1_INDEXES:
            c = len(re.findall(r"\buseChecklistPersistence\b", host_src[n]))
            assert c == 3, f"{LANE1_HOSTS[n]}: 期望 3 处，实得 {c}"

    def test_v_if_gate_is_one_each(self, host_src: dict[int, str]) -> None:
        for n in LANE1_INDEXES:
            c = host_src[n].count('v-if="dualMode.isOoAvailable')
            assert c == 1, f"{LANE1_HOSTS[n]}: v-if 门控期望 1 处，实得 {c}"

    @pytest.mark.parametrize("symbol", K6_ONLY_SYMBOLS)
    def test_apiproxy_and_publish_are_k6_only(
        self, symbol: str, host_src: dict[int, str]
    ) -> None:
        """🔴 `apiProxy` 与 `publish-to-tb` **只 K6 宿主各命中 1**。"""
        hit = {}
        for n in LANE1_INDEXES:
            c = (
                len(re.findall(r"\bapiProxy\b", host_src[n]))
                if symbol == "apiProxy"
                else host_src[n].count(symbol)
            )
            if c:
                hit[n] = c
        assert hit == {6: 1}, f"{symbol} 命中分布 {hit} ⇒ 期望只 K6 各 1"

    def test_k6_is_the_only_host_layer_tb_gate(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 两侧都验：全 K 的宿主层 TB 发布门只有 K6 这一处。"""
        hosts = [
            p.name
            for p in k_files
            if p.name.startswith("GtK")
            and "publish-to-tb" in strip_comments(cached_text(p))
        ]
        assert hosts == [LANE1_HOSTS[6]], f"宿主层 TB 门 {hosts}"


class TestKAP10LocalStorageSplit:
    """🔴 撞车 3 条（K4/K5/K6）+ 孪生无持久化 4 条（K1/K2/K3/K7），3+4 == 7。"""

    def test_the_split_is_three_plus_four(self) -> None:
        assert set(PREFIX_COLLISION_ENTRIES) == {4, 5, 6}
        assert set(TWIN_NO_PERSIST_ENTRIES) == {1, 2, 3, 7}
        assert set(PREFIX_COLLISION_ENTRIES) & set(TWIN_NO_PERSIST_ENTRIES) == set()
        assert (
            len(PREFIX_COLLISION_ENTRIES) + len(TWIN_NO_PERSIST_ENTRIES) == 7
        )
        assert set(PREFIX_COLLISION_ENTRIES) | set(
            TWIN_NO_PERSIST_ENTRIES
        ) == set(LANE1_INDEXES)

    def test_slice_registers_the_same_split(self, slice_doc: dict) -> None:
        s = slice_doc["orphan_dual_mode_inventory"]["summary"]
        assert s["orphans_with_prefix_collision_with_host_twin"] == 3
        assert s["orphans_whose_twin_has_no_persistence"] == 4

    def test_collision_group_had_the_legacy_prefix(self, slice_doc: dict) -> None:
        """🔴 撞车的依据（改造前）：宿主与 orphan 的前缀**同值**。"""
        mods = {
            m["wp_code"]: m
            for m in slice_doc["orphan_dual_mode_inventory"]["modules"]
        }
        for n in PREFIX_COLLISION_ENTRIES:
            code = next(c for c in mods if c.startswith(f"K{n}"))
            m = mods[code]
            assert m["prefix_collision_with_twin"] is True
            assert m["localStorage_prefix"] == m["twin_localStorage_prefix"]
            assert m["localStorage_prefix"] == f"k{n}-dual-mode:"

    def test_no_persist_group_had_none_on_the_host_side(
        self, slice_doc: dict
    ) -> None:
        mods = {
            m["wp_code"]: m
            for m in slice_doc["orphan_dual_mode_inventory"]["modules"]
        }
        for n in TWIN_NO_PERSIST_ENTRIES:
            code = next(c for c in mods if c.startswith(f"K{n}"))
            assert mods[code]["twin_localStorage_prefix"] is None
            assert mods[code]["prefix_collision_with_twin"] is False


class TestKAP50ColumnPrefsUntouched:
    """🔴 列偏好类**不动**（KC-18）—— 它是另一命名空间。"""

    @pytest.mark.parametrize("name", COLUMN_PREFS_UNTOUCHED)
    def test_file_still_exists_and_keeps_its_own_prefix(self, name: str) -> None:
        p = WP_COMPOSABLES / name
        assert p.exists(), f"{name} 被误删"
        src = strip_comments(cached_text(p))
        assert "localStorage" in src, f"{name} 的 localStorage 被误删"
        assert "column-prefs" in src, f"{name} 的列偏好前缀变了"

    @pytest.mark.parametrize("name", COLUMN_PREFS_UNTOUCHED)
    def test_it_did_not_get_the_unified_mode_key(self, name: str) -> None:
        """🔴 列偏好不是模式偏好 ⇒ 不该被统一键收敛。"""
        src = strip_comments(cached_text(WP_COMPOSABLES / name))
        assert UNIFIED_KEY_FN not in src, (
            f"{name} 接了模式统一键 ⇒ KC-18 的「不动」被违反"
        )
        assert "dual-mode" not in src, f"{name} 出现 dual-mode 前缀"

    def test_the_two_namespaces_are_disjoint(self) -> None:
        """两个命名空间字面量不相交（`column-prefs` vs `workpaper-sync-mode`）。"""
        for name in COLUMN_PREFS_UNTOUCHED:
            src = strip_comments(cached_text(WP_COMPOSABLES / name))
            assert "workpaper-sync-mode" not in src


# ════════════════════════════════════════════════════════════════════════════
# Task 7 / KA-P11, KA-P12：health 单源探针 + localStorage 收敛
# ════════════════════════════════════════════════════════════════════════════
class TestKAP11HealthConvergedToSingleProbe:
    """🔴 7 宿主的 health 直调全部改走 `fetchOnlyOfficeHealthy()`。"""

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_no_direct_health_call(self, n: int, host_src: dict[int, str]) -> None:
        assert LEGACY_HEALTH_EP not in host_src[n], (
            f"{LANE1_HOSTS[n]} 仍直调 health 端点"
        )

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_uses_the_single_source_probe(
        self, n: int, host_src: dict[int, str]
    ) -> None:
        assert HEALTH_PROBE in host_src[n], (
            f"{LANE1_HOSTS[n]} 未改调 {HEALTH_PROBE}()"
        )

    def test_k_domain_health_direct_calls_are_now_zero(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 三段式账本第 ④ 段达成：K 域 health 直调 **0**。

        20（design 基线）→ 14（lane 2 收敛 6）→ 7（lane 1 删 7 orphan）→ **0**。
        """
        residue = {
            p.name: strip_comments(cached_text(p)).count(LEGACY_HEALTH_EP)
            for p in k_files
        }
        live = {k: v for k, v in residue.items() if v}
        assert live == {}, f"K 域仍有 health 直调：{live}"

    def test_the_probe_is_the_platform_single_implementation(self) -> None:
        """两侧都验：探针只有一份实现（不是又造了一个）。"""
        impl = FRONTEND_SRC / "components" / "workpaper" / "sync" / "onlyOfficeHealth.ts"
        assert impl.exists()
        src = cached_text(impl)
        assert f"export async function {HEALTH_PROBE}" in src or (
            f"export function {HEALTH_PROBE}" in src
        )
        # 全平台只此一处 export
        defs = [
            p.name
            for p in FRONTEND_SRC.rglob("*.ts")
            if re.search(rf"export\s+(?:async\s+)?function\s+{HEALTH_PROBE}\b", cached_text(p))
        ]
        assert defs == [impl.name], f"探针有多处实现：{defs}"

    def test_materialize_was_not_used_for_health(
        self, host_src: dict[int, str]
    ) -> None:
        """🔴 口径裁定留档：health 走探针**不是** materialize。

        Task 7 原文写「改走 bridge materialize」—— materialize 是 store 投影
        （用于 config/内容落地），health 是探针。且 7 宿主的 config 命中现算为 0
        ⇒ 没有 config 要接桥。判据显式验「没误用 materialize 做 health」。
        """
        for n in LANE1_INDEXES:
            assert LEGACY_CONFIG_EP not in host_src[n], (
                f"{LANE1_HOSTS[n]} 出现 config 端点 ⇒ 前提变了"
            )
            # 探针段内不该出现 materialize
            m = re.search(
                rf"{HEALTH_PROBE}\([^)]*\)", host_src[n]
            )
            assert m is not None
            around = host_src[n][max(0, m.start() - 200) : m.end() + 200]
            assert "materialize" not in around, (
                f"{LANE1_HOSTS[n]}: health 探针附近出现 materialize ⇒ 口径混了"
            )


class TestKAP12LocalStorageConverged:
    """🔴 统一键收敛：撞车 3 条改前缀 + 无持久化 4 条新增能力。"""

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_uses_unified_key_generator(
        self, n: int, host_src: dict[int, str]
    ) -> None:
        assert UNIFIED_KEY_FN in host_src[n], (
            f"{LANE1_HOSTS[n]} 未接统一键生成器"
        )
        assert MIGRATE_FN in host_src[n], f"{LANE1_HOSTS[n]} 未接旧键迁移"

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_no_legacy_prefix_in_code(
        self, n: int, host_src: dict[int, str]
    ) -> None:
        """🔴 代码里无旧前缀字面量（注释里可以提，说明迁移来源）。"""
        assert re.search(r"['\"]k\d+-dual-mode:", host_src[n]) is None, (
            f"{LANE1_HOSTS[n]} 代码里仍有 legacy 前缀"
        )

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_entry_id_constant_is_defined_and_used(
        self, n: int, host_src: dict[int, str]
    ) -> None:
        """统一键第一段必须是本 entry 的真 entry_id。

        🔴 判据查**常量定义 + 在 `workpaperSyncModeKey` 调用里被引用** ——
        只查「entry_id 字面量存在」会被 notice 的 `entry-id="…"` 属性巧合满足
        （首轮实测：helpers 整块漏插入，那条判据仍绿）。
        """
        const = f"K{n}_ENTRY_ID"
        assert re.search(
            rf"const\s+{const}\s*=\s*'{re.escape(LANE1_ENTRY_IDS[n])}'",
            host_src[n],
        ), f"{LANE1_HOSTS[n]}: 缺常量 {const} = '{LANE1_ENTRY_IDS[n]}'"
        assert re.search(
            rf"{UNIFIED_KEY_FN}\(\{{[^}}]*entryId:\s*{const}", host_src[n], re.S
        ), f"{LANE1_HOSTS[n]}: {const} 未被统一键调用引用"

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_mode_mapping_helpers_are_defined_not_just_called(
        self, n: int, host_src: dict[int, str]
    ) -> None:
        """🔴 值域映射的两个 helper 必须**有定义**，不能只被调用。

        这条是上一轮漏插入 helpers 的直接防御。
        """
        for fn in ("toStoredMode", "fromStoredMode"):
            assert re.search(rf"function\s+{fn}\s*\(", host_src[n]), (
                f"{LANE1_HOSTS[n]}: {fn} 被调用但没有定义"
            )

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_value_domain_maps_to_the_unified_source(
        self, n: int, host_src: dict[int, str]
    ) -> None:
        """🔴 值域映射：宿主用 `'onlyoffice'`，统一真源落盘 `'oo'`。"""
        assert "toStoredMode" in host_src[n] and "fromStoredMode" in host_src[n]
        assert re.search(r"'oo'", host_src[n]), (
            f"{LANE1_HOSTS[n]}: 未见 'oo' 落盘值域"
        )

    def test_all_seven_now_persist(self, host_src: dict[int, str]) -> None:
        """🔴 目标态达成：7 条**都持久化**（不再「一边有一边无」）。"""
        for n in LANE1_INDEXES:
            assert "loadPersistedMode" in host_src[n], (
                f"{LANE1_HOSTS[n]} 无 loadPersistedMode"
            )
            assert "persistMode" in host_src[n], (
                f"{LANE1_HOSTS[n]} 无 persistMode"
            )
            assert len(re.findall(r"\blocalStorage\b", host_src[n])) == 2, (
                f"{LANE1_HOSTS[n]} localStorage 读写不是各 1 处"
            )

    def test_the_no_persist_group_gained_the_capability(
        self, host_src: dict[int, str]
    ) -> None:
        """🔴 K1/K2/K3/K7 是**新增**能力（原先没有）—— 注释须写明。"""
        for n in TWIN_NO_PERSIST_ENTRIES:
            raw = cached_text(host_path(n))
            assert "原先没有持久化" in raw, (
                f"{LANE1_HOSTS[n]}: 未登记「新增持久化」这个目标态裁定"
            )

    def test_the_collision_group_notes_the_migration_source(self) -> None:
        """🔴 K4/K5/K6 注释须写明旧前缀来源（迁移可追溯）。"""
        for n in PREFIX_COLLISION_ENTRIES:
            raw = cached_text(host_path(n))
            assert f"k{n}-dual-mode:" in raw, (
                f"{LANE1_HOSTS[n]}: 注释里未留旧前缀，迁移来源不可追溯"
            )
            assert "撞车" in raw, f"{LANE1_HOSTS[n]}: 未说明撞车背景"

    def test_thirteen_entries_now_share_one_key_namespace(self) -> None:
        """🔴 13 条统一：7 宿主 + 6 composable 全用 `workpaperSyncModeKey()`。"""
        using: list[int] = []
        for n in K_INDEXES:
            if dual_mode_path(n).exists():
                src = strip_comments(cached_text(dual_mode_path(n)))
            else:
                src = strip_comments(cached_text(host_path(n)))
            if UNIFIED_KEY_FN in src:
                using.append(n)
        assert sorted(using) == sorted(K_INDEXES), (
            f"未接统一键的 entry：{sorted(set(K_INDEXES) - set(using))}"
        )
        assert len(using) == 13


# ════════════════════════════════════════════════════════════════════════════
# Task 8 / KA-P13：BP-7 notice
# ════════════════════════════════════════════════════════════════════════════
class TestKAP13NoticeMounted:
    """7 宿主挂 notice；符号按 KC-14 口径选。"""

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_notice_component_is_mounted(
        self, n: int, host_src: dict[int, str]
    ) -> None:
        assert NOTICE_COMPONENT in host_src[n], (
            f"{LANE1_HOSTS[n]} 未挂 {NOTICE_COMPONENT}"
        )

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_notice_carries_the_real_entry_id(
        self, n: int, host_src: dict[int, str]
    ) -> None:
        m = re.search(
            rf'<{NOTICE_COMPONENT}\s+entry-id="([^"]+)"', host_src[n]
        )
        assert m is not None, f"{LANE1_HOSTS[n]}: notice 无 entry-id"
        assert m.group(1) == LANE1_ENTRY_IDS[n], (
            f"{LANE1_HOSTS[n]}: entry-id {m.group(1)} != {LANE1_ENTRY_IDS[n]}"
        )

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_notice_sits_next_to_the_mode_switcher(
        self, n: int, host_src: dict[int, str]
    ) -> None:
        """🔴 挂载点须落在 toolbar 区（与 el-segmented 相邻），不是随便塞。"""
        seg = host_src[n].find("el-segmented")
        notice = host_src[n].find(NOTICE_COMPONENT)
        assert seg >= 0 and notice >= 0
        # notice 在 template 里的位置应紧随分段器（字符距离有界）
        template_notice = re.search(
            rf"<{NOTICE_COMPONENT}\s", host_src[n]
        )
        assert template_notice is not None
        assert abs(template_notice.start() - seg) < 900, (
            f"{LANE1_HOSTS[n]}: notice 距 el-segmented {abs(template_notice.start()-seg)} 字符"
            " ⇒ 可能挂在了别的区块"
        )

    def test_all_thirteen_k_hosts_now_carry_the_notice(self) -> None:
        """🔴 BP-7 在 K 循环**全部兑现**：13 条宿主全挂。

        🔴 这里必须用 foundation 的**通用** `host_path`（覆盖 13 条），
        lane1_facts 的同名函数只含 K1~K7（首轮实测 KeyError: 8）。
        """
        from tests.workpaper_sync.k_foundation_facts import (
            host_path as k_host_path,
        )

        missing: list[str] = []
        for n in K_INDEXES:
            src = strip_comments(cached_text(k_host_path(n)))
            if NOTICE_COMPONENT not in src:
                missing.append(k_host_path(n).name)
        assert missing == [], f"未挂 notice 的宿主：{missing}"

    def test_platform_component_count_follows_the_mounting_ledger(self) -> None:
        """🔴 组件名命中走账本：48（design 基线）+ 13（K 全挂）== 61 **起步**。

        并发会话（如 L 循环）也挂 notice ⇒ 单调增长（>= 即可），退降才是 bug。
        """
        comp = _platform_files_with(NOTICE_COMPONENT)
        assert len(comp) >= NOTICE_COMPONENT_PLATFORM_BASELINE + 13, (
            f"组件名命中 {len(comp)}，期望 >= {NOTICE_COMPONENT_PLATFORM_BASELINE} + 13"
        )

    def test_module_name_count_only_grows_for_composable_carriers(self) -> None:
        """🔴 口径差异：模块名命中**只随 composable 载体增长**，宿主内联不增。

        现算 9 = 2（design 基线：模块本体 + 组件本体）+ 6（BP-6 组宿主）+ 1（spec）。
        lane 2 的 6 条走**专用 composable** 载体，其宿主里除组件标签外还引了
        `workpaperEntrySyncNotice` 模块；本 lane 的 7 条是**内联 IIFE** 载体，
        只挂组件标签不引模块 ⇒ 模块名命中**不涨**。
        两个口径都对：组件名数「挂了多少处」，模块名数「引了多少处模块」。
        """
        mod = set(_platform_files_with(NOTICE_MODULE))
        assert len(mod) >= 9, f"模块名命中 {len(mod)}（期望 >= 9）：{sorted(mod)}"
        # 本 lane 的 7 宿主**不在**模块名命中集里（内联载体的形态特征）
        for n in LANE1_INDEXES:
            rel = host_path(n).relative_to(FRONTEND_SRC).as_posix()
            assert rel not in mod, (
                f"{rel} 出现在模块名命中集里 ⇒ 内联载体的口径结论须复核"
            )
        # BP-6 组的 6 宿主**在**集合里（对照的另一端）
        bp6_in = [f for f in mod if re.search(r"GtK(?:8|9|1[0-3])", f)]
        assert len(bp6_in) == 6, f"BP-6 组在模块名集里的宿主 {sorted(bp6_in)}"

    def test_module_name_is_narrower_than_component_name(self) -> None:
        """🔴 KC-14 的选符号依据：模块名口径远窄于组件名口径。"""
        comp = set(_platform_files_with(NOTICE_COMPONENT))
        mod = set(_platform_files_with(NOTICE_MODULE))
        assert len(mod) < len(comp), "两个口径宽窄关系变了 ⇒ 选符号依据须复核"
        # K 域宿主同时命中两者（组件内部引模块）
        for n in LANE1_INDEXES:
            rel = host_path(n).relative_to(FRONTEND_SRC).as_posix()
            assert rel in comp, f"{rel} 不在组件名命中集里"
