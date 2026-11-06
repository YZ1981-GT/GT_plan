# -*- coding: utf-8 -*-
"""K 循环 foundation spec — Task 14 的 notice 符号判据（KF-P35）。

spec: k-cycle-sync-foundation-and-first-canary
Task 14: KC-14 —— 判据必须写明用组件名还是模块名（两个口径都对，符号不同）
Property: KF-P35

🔴 为什么单独一个文件：这一节原在
`test_k_foundation_p7_gates_and_storage.py` 里。2026-11-05 补完「模块名已无生产面 /
文案只许一个声明点 / 冻结计划禁止删除兼容模块」三条判据后那个文件 846 行、超过 800
行门禁 ⇒ 按仓库口径**拆模块而不是抬白名单**，整节搬到这里（判据内容一字未改）。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP5_INDEXES,
    BP6_INDEXES,
    BP7_NOTICE_MOUNTED_ENTRIES,
    DATA,
    FRONTEND,
    K_HOSTS,
    K_INDEXES,
    cached_text,
    host_path,
    strip_comments,
)

NOTICE_COMPONENT_NAME = "GtEntrySyncCapabilityNotice"
NOTICE_MODULE_NAME = "workpaperEntrySyncNotice"


@pytest.fixture(scope="module")
def all_frontend() -> list[pathlib.Path]:
    return [
        p for p in FRONTEND.rglob("*")
        if p.is_file()
        and p.suffix in (".ts", ".vue")
        and "__tests__" not in p.as_posix()
    ]


# ════════════════════════════════════════════════════════════════════════════
# Task 14 / KF-P35：BP-7 notice 从零补
# ════════════════════════════════════════════════════════════════════════════
class TestKFP35NoticeSymbols:
    """🔴 KC-14：判据必须写明用组件名还是模块名（两个口径都对，符号不同）。"""

    #: 🔴 已挂 notice 的 entry（逐条推进 —— **现已全集**）。
    #: K10 = foundation canary（Task 26）；K8/K9/K11/K12/K13 = lane 2（Task 6）；
    #: K1~K7 = lane 1（Task 8）⇒ BP-7 在 K 循环**全部兑现**。
    MOUNTED_ENTRIES = BP7_NOTICE_MOUNTED_ENTRIES

    def test_unmounted_hosts_have_neither_symbol(self) -> None:
        """🔴 BP-7 的未兑现部分：未挂载的 12 宿主两符号都是 0。

        分型判据：`MOUNTED_ENTRIES` 里的已挂，其余仍未挂。挂一条就挪进清单 ——
        不是放宽判据，是把「13 宿主全未挂」改成逐条推进的可复算清单。
        """
        for n in K_INDEXES:
            if n in self.MOUNTED_ENTRIES:
                continue
            src = strip_comments(cached_text(host_path(n)))
            for sym in (NOTICE_COMPONENT_NAME, NOTICE_MODULE_NAME):
                assert sym not in src, (
                    f"{K_HOSTS[n]} 已挂 {sym} ⇒ 须挪进 MOUNTED_ENTRIES"
                )

    def test_mounted_hosts_use_the_component_with_entry_id(self) -> None:
        """🔴 已挂载的宿主按 KC-14 口径用**组件名** + `entry-id` 绑定。

        守卫正则（`docs/operations/evidence/suite-triage/ac14-honest-mode-notice.md`）
        要求 `entry-id` 紧邻组件名 —— 中间插 `v-if` 会让平台守卫失配。
        """
        for n in self.MOUNTED_ENTRIES:
            src = cached_text(host_path(n))
            assert NOTICE_COMPONENT_NAME in src, (
                f"{K_HOSTS[n]} 未挂 {NOTICE_COMPONENT_NAME}"
            )
            # import 存在
            assert re.search(
                rf"import\s+{NOTICE_COMPONENT_NAME}\s+from", src
            ), f"{K_HOSTS[n]} 缺 {NOTICE_COMPONENT_NAME} 的 import"
            # 模板里 entry-id 紧邻组件名
            m = re.search(
                rf"<{NOTICE_COMPONENT_NAME}\s+entry-id=\"([^\"]+)\"\s*/?>", src
            )
            assert m, (
                f"{K_HOSTS[n]}: `<{NOTICE_COMPONENT_NAME} entry-id=\"...\" />` "
                "形态不符（entry-id 须紧邻组件名，中间不得插 v-if）"
            )
            # entry_id 正确（🔴 全 13 条 —— BP-7 已全部兑现）
            expected_ids = {
                1: "xlsx/gt-k1-other-receivables",
                2: "xlsx/gt-k2-other-current-assets",
                3: "xlsx/gt-k3-other-payables",
                4: "xlsx/gt-k4-other-current-liabilities",
                5: "xlsx/gt-k5-provisions",
                6: "xlsx/gt-k6-held-for-sale",
                7: "xlsx/gt-k7-deferred-income",
                8: "xlsx/gt-k8-selling-expenses",
                9: "xlsx/gt-k9-admin-expenses",
                10: "xlsx/gt-k10-other-income",
                11: "xlsx/gt-k11-asset-impairment-loss",
                12: "xlsx/gt-k12-non-operating-income",
                13: "xlsx/gt-k13-non-operating-expense",
            }
            assert m.group(1) == expected_ids[n], (
                f"{K_HOSTS[n]}: entry-id 是 {m.group(1)!r}，期望 {expected_ids[n]!r}"
            )

    def test_notice_is_inside_the_mode_toolbar_block(self) -> None:
        """notice 必须挂在模式切换工具栏块内（不是随便放）。"""
        for n in self.MOUNTED_ENTRIES:
            src = strip_comments(cached_text(host_path(n)))
            lines = src.split("\n")
            seg_line = next(
                (i for i, row in enumerate(lines) if "el-segmented" in row), None
            )
            notice_line = next(
                (i for i, row in enumerate(lines) if NOTICE_COMPONENT_NAME in row
                 and "import" not in row), None
            )
            assert seg_line is not None, f"{K_HOSTS[n]} 找不到 el-segmented"
            assert notice_line is not None, f"{K_HOSTS[n]} 模板里找不到 notice"
            assert abs(notice_line - seg_line) <= 12, (
                f"{K_HOSTS[n]}: notice 距 el-segmented {abs(notice_line-seg_line)} 行"
                " ⇒ 不在同一工具栏块内"
            )

    def test_mount_progress_is_13_of_13(self) -> None:
        """🔴 BP-7 进度 **13/13**（三份 spec 各交付自己那部分）。

        foundation 1 条（K10 canary）+ lane 2 五条（BP-6 余集）+ lane 1 七条（BP-5 全集）。
        """
        mounted = [
            n for n in K_INDEXES
            if NOTICE_COMPONENT_NAME in strip_comments(cached_text(host_path(n)))
        ]
        assert tuple(mounted) == self.MOUNTED_ENTRIES, (
            f"实际已挂 {mounted}，清单登记 {list(self.MOUNTED_ENTRIES)}"
        )
        assert len(mounted) == 13
        remaining = [n for n in K_INDEXES if n not in mounted]
        assert remaining == [], f"仍未挂载：{remaining}"
        # 三份 spec 的交付量分摊
        assert len([n for n in mounted if n == 10]) == 1
        assert len([n for n in mounted if n in BP6_INDEXES and n != 10]) == 5
        assert len([n for n in mounted if n in BP5_INDEXES]) == 7

    def test_mounted_set_is_now_the_whole_k_cycle(self) -> None:
        """🔴 已挂载集合 == **全 13 条**（BP-7 在 K 循环全部兑现）。

        推进轨迹：BP-6 全集 6 条（foundation + lane 2）→ 加上 BP-5 全集 7 条
        （lane 1 Task 8）= 13。两个 lane 的并集恰好覆盖全集，无重叠无遗漏。
        """
        assert set(self.MOUNTED_ENTRIES) == set(K_INDEXES), (
            f"已挂载 {sorted(self.MOUNTED_ENTRIES)} != 全集 {sorted(K_INDEXES)}"
        )
        assert set(BP6_INDEXES) | set(BP5_INDEXES) == set(K_INDEXES)
        assert set(BP6_INDEXES) & set(BP5_INDEXES) == set()

    def test_component_symbol_is_the_only_caliber_with_production_surface(
        self, all_frontend: list[pathlib.Path]
    ) -> None:
        """🔴 组件名是**唯一**还有生产面的口径 ⇒ BP-7 挂载判据 SHALL 用组件名。

        原判据写的是「组件名 46 / 模块名 1，分母大得多」。模块名那 1 个命中来自
        `42d2f6e6f` 的 `GtEntrySyncCapabilityNotice.vue`（它当时 import
        `entrySyncNotice()`）。`eaa655686` 把提示改成消费 runtime readiness 之后，
        组件转去用 `useEntrySyncReadiness` → `deriveEntrySyncPresentation`，
        模块名的生产命中**归零** —— 原判据的 `>= 1` 就红在这里。

        处置：不把 0 写成「分母塌了」，也不去给死模块硬塞一个 import。现算结论比
        原来**更强**：模块名已无任何生产面，组件名是唯一可用口径。
        0 这个数字本身写进断言（恒等，不是区间），模块名一旦被重新接线就打红，
        逼迫重新论证口径选型。
        """
        comp = [
            p.name for p in all_frontend
            if NOTICE_COMPONENT_NAME in strip_comments(cached_text(p))
        ]
        mod = [
            p.name for p in all_frontend
            if NOTICE_MODULE_NAME in strip_comments(cached_text(p))
        ]
        assert len(comp) >= 40, (
            f"组件名全平台命中 {len(comp)} ⇒ 分母塌了，判据选型依据失效"
        )
        assert mod == [], (
            f"模块名重新长出生产面 {mod} ⇒ 「只能选组件名」的理由须重新论证"
        )

    def test_notice_single_source_module_exists(self) -> None:
        """AC 1.4 文案真源模块与组件都存在（BP-7 有东西可挂）。"""
        sync_dir = FRONTEND / "components" / "workpaper" / "sync"
        module = sync_dir / f"{NOTICE_MODULE_NAME}.ts"
        component = sync_dir / f"{NOTICE_COMPONENT_NAME}.vue"
        assert module.exists(), f"文案真源模块不存在：{module}"
        assert component.exists(), f"提示组件不存在：{component}"

    def test_frozen_plan_forbids_deleting_the_compat_module(self) -> None:
        """🔴 0 调用方也不许删：冻结删除计划把它列在 `must_not_delete`。

        「grep 0 调用方 ⇒ 删」是仓库常规铁律，但本文件被 Task 57 的冻结计划
        明令保留。判据直接读那份计划，而不是把「不删」写成注释里的口头约定 ——
        计划哪天把它移出 `must_not_delete`，这条自然失效。
        """
        plan = json.loads(
            (DATA / "workpaper_sync_abcs_cycle_deletion_plan.json").read_text("utf-8")
        )
        kept = {row["path"] for row in plan["must_not_delete"]}
        rel = (
            "audit-platform/frontend/src/components/workpaper/sync/"
            f"{NOTICE_MODULE_NAME}.ts"
        )
        assert rel in kept, f"{rel} 不在 must_not_delete ⇒ 保留它的依据没了"
        assert plan["delete_files"] == [], "delete_files 非空 ⇒ 删除计划已换形态"

    def test_notice_text_has_exactly_one_declaration_site(self) -> None:
        """🔴 文案只能有一个声明点：兼容入口再导出活路径的常量。

        `eaa655686` 把两句中文**又抄了一份**进 `entrySyncPresentation.ts` 的
        `capability === null` 分支，于是同一句话有两个声明点（兼容模块的常量 +
        活路径的字面量），改一处另一处静默不动、用户看到的和兼容面说的能对不上。
        现在声明点在活路径，兼容模块 `export { ... } from` 再导出。
        """
        sync_dir = FRONTEND / "components" / "workpaper" / "sync"
        presentation = (sync_dir / "entrySyncPresentation.ts").read_text("utf-8")
        compat = (sync_dir / f"{NOTICE_MODULE_NAME}.ts").read_text("utf-8")
        for name in ("ENTRY_SYNC_NOTICE_LABEL", "ENTRY_SYNC_NOTICE_SUMMARY"):
            assert re.search(rf"^export const {name} = '", presentation, re.M), (
                f"{name} 不在 entrySyncPresentation.ts 里声明 ⇒ 活路径不是真源"
            )
            assert not re.search(rf"^export const {name} = '", compat, re.M), (
                f"{name} 在兼容模块里又声明了一次 ⇒ 两个声明点会各自漂移"
            )
        assert re.search(
            r"export \{\s*ENTRY_SYNC_NOTICE_LABEL,\s*ENTRY_SYNC_NOTICE_SUMMARY,"
            r"\s*\} from '\./entrySyncPresentation'",
            compat,
        ), "兼容模块未从 entrySyncPresentation 再导出文案 ⇒ 兼容面会与界面脱钩"
        # 活路径分支里不得再出现字面量（否则常量白声明）
        body = presentation.split("export const ENTRY_SYNC_NOTICE_SUMMARY")[1]
        assert "'两侧数据未互通'" not in body, (
            "deriveEntrySyncPresentation 里仍写着字面量 ⇒ 常量没被用上"
        )
