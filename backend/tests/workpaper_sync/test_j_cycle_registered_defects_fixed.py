# -*- coding: utf-8 -*-
r"""J 循环规划期登记的缺陷 —— **已修复，且必须保持修复**。

spec: `j-cycle-sync-foundation-and-first-canary`（Task 23：BP-10 首处 notice + 二级门控）

═══ 为什么从 Task 52 搬到这里（与 I 循环 `test_i_cycle_registered_defects_fixed.py` 同款）═══

`test_task52_j_cycle_migration.py` 是**规划期**快照，判据是「实测命中 == 登记」—— 缺陷**还在**才绿；
Task 23 首轮正是被它的 AC14 两条锁死而回滚。判据于是**翻面**：

  · slice 登记保持原值（append-only，`notice_mounted=False` / `second_level=None` /
    BP-10 `REGISTERED_NOT_FIXED` 是修复前的历史事实；有人改 slice 想让判据自洽 ⇒ 打红）；
  · 现算已修：notice 在 `j1-dual-mode-bar` 区块内、切换器带二级门控；
  · 修法真在源码里，且文案不内联。

🔴 二级门控用的是共享基类 `useWorkpaperEntryDualMode` **真实暴露的** `ooAvailable`。
   spec Task 23 原文写的 `dualMode.isOoAvailable.value` 是 I/L 宿主各自 composable 的名字，
   本基类**没有**这个成员（照抄会恒 undefined ⇒ 切换器永远不显示）。
"""
from __future__ import annotations

import re

import pytest

from tests.workpaper_sync.test_task52_j_cycle_migration import (
    J_HOSTS,
    MANIFEST_SLICE_PATH,
    NOTICE_COMPONENT_NAME,
    SHARED_BASE,
    SYNC_DIR,
    _load,
    _strip_ts_comments,
    _toolbar_block,
    _vue_template,
)

J1_ENTRY = "xlsx/j1/gt-j1-employee-compensation"
NOTICE_TS = SYNC_DIR / "workpaperEntrySyncNotice.ts"
_GATE_RE = re.compile(r"<el-segmented\b[^>]*\bv-if=\"dualMode\.ooAvailable\.value\"")


@pytest.fixture(scope="module")
def the_entry() -> dict:
    entries = _load(MANIFEST_SLICE_PATH)["independent_entries"]
    assert len(entries) == 1
    return entries[0]


@pytest.fixture(scope="module")
def block(the_entry: dict) -> str:
    template = _vue_template(J_HOSTS["j1"].read_text(encoding="utf-8"))
    return _toolbar_block(template, the_entry["ui_toolbar_gate"])


class TestBp10NoticeAndGateFixedInJ1:
    def test_slice_keeps_its_pre_fix_values(self, the_entry: dict) -> None:
        slice_doc = _load(MANIFEST_SLICE_PATH)
        assert the_entry["notice_mounted"] is False
        assert the_entry["ui_toolbar_gate_second_level"] is None
        bp10 = next(bp for bp in slice_doc["blocking_preconditions"] if bp["id"] == "BP-10")
        assert bp10["status"] == "REGISTERED_NOT_FIXED"

    def test_notice_is_mounted_inside_the_toolbar_with_entry_id(self, block: str) -> None:
        code = _strip_ts_comments(J_HOSTS["j1"].read_text(encoding="utf-8"))
        assert re.search(
            r"import\s+GtEntrySyncCapabilityNotice\s+from\s+'\.\./sync/GtEntrySyncCapabilityNotice\.vue'",
            code,
        ), "J1 宿主未 import 提示组件"
        assert f'<{NOTICE_COMPONENT_NAME} entry-id="{J1_ENTRY}"' in block, (
            "提示组件不在 j1-dual-mode-bar 区块内或 entry-id 绑定不对"
        )

    def test_segmented_has_second_level_gate(self, block: str) -> None:
        assert block.count("<el-segmented") == 1
        assert _GATE_RE.search(block), "切换器缺二级门控（OO 不可用时仍显示 = 无声失败）"
        assert "仅结构化视图" in block, "OO 不可用时的兜底 tag 不见了"

    def test_gate_member_really_exists_on_the_shared_base(self) -> None:
        """🔴 防照抄 `isOoAvailable`：门控引用的成员必须在共享基类的 return 里。"""
        shared = SHARED_BASE.read_text(encoding="utf-8")
        ret = shared[shared.rindex("return {") :]
        assert re.search(r"\booAvailable\b", ret)
        assert "isOoAvailable" not in shared

    def test_gate_regex_is_not_vacuous(self) -> None:
        """变异：去掉 v-if 的旧形态必须不命中；用错成员名也必须不命中。"""
        old = "<el-segmented :model-value=\"x\" size=\"small\" />"
        wrong = "<el-segmented v-if=\"dualMode.isOoAvailable.value\" />"
        right = "<el-segmented v-if=\"dualMode.ooAvailable.value\" :options=\"o\" />"
        assert not _GATE_RE.search(old)
        assert not _GATE_RE.search(wrong)
        assert _GATE_RE.search(right)

    def test_notice_text_is_not_inlined_in_the_host(self) -> None:
        notice_src = NOTICE_TS.read_text(encoding="utf-8")
        phrases = set(
            re.findall(r"ENTRY_SYNC_NOTICE_(?:LABEL|SUMMARY)\s*=\s*'([^']+)'", notice_src)
        )
        assert len(phrases) == 2, f"提示文案常量抽取失败（判据防空转）：{phrases}"
        host = J_HOSTS["j1"].read_text(encoding="utf-8")
        assert not [p for p in phrases if p in host], "J1 宿主内联了提示文案"

    def test_j2_j3_hosts_still_have_no_notice(self) -> None:
        """J2/J3 不是 entry（下游 lane JN-1），挂提示就是对非 entry 宣称同步能力。"""
        for key in ("j2", "j3"):
            code = _strip_ts_comments(J_HOSTS[key].read_text(encoding="utf-8"))
            assert NOTICE_COMPONENT_NAME not in code, f"{key} 宿主挂了提示"
