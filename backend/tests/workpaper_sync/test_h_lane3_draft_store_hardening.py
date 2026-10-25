# -*- coding: utf-8 -*-
r"""HC-10 第三处客户端存储的**长期一致性归口** —— lane3 Task 5 的 ②③ 两条。

spec: `h2-h6-h10-pilot-cross-reference-lanes` Task 5（HX-P8）

═══ 为什么单独一个文件 ═══════════════════════════════════════════════════════

`test_h_foundation_hc_guards.py::TestHfP10ClientDraftStore` 守的是 HC-10 的**形态**
（草稿键前缀 / `restoreDrafts` 存在 / 只有 H10 有第三处存储），那是 foundation 的作业面，
判据是「现状如此」。本文件守的是 lane3 的**归口结果**（窗口门 + 用户可见计数），
判据是「已经修成什么样」。两者变化频率与读者都不同，且 foundation 那个文件已贴着
行数门禁上限。

═══ 四条 AC 的落点 ═══════════════════════════════════════════════════════════

① PUT 3 次全败后可见上报 —— 现状已成立（`ElMessage.warning` 在落草稿同一分支），
  spec 原文「现状是静默的」已过期，本文件只做回归锁。
② adapter 回写窗口内禁用落草稿 —— 本轮新增。
③ UI 显示「有 N 条未同步草稿」 —— 本轮新增。
④ 回灌后立即重试 PUT，成功即删 —— 现状已成立（`restoreDrafts` → `saveImmediate(…, 1)`）。
"""
from __future__ import annotations

import re

import pytest

from tests.workpaper_sync import h_cycle_facts as F

FORMDATA = "useH10FormData.ts"
HOST = "GtH10AssetDisposalIncome.vue"

#: 草稿落盘那一行的形态（不写死行号 —— 行号会漂）。
_SETITEM_RE = re.compile(r"localStorage\.setItem\(\s*draftKey\(")
#: 窗口门那一行的形态。
_SUSPEND_GATE_RE = re.compile(r"if\s*\(\s*draftsSuspended\.value\s*\)")


@pytest.fixture(scope="module")
def formdata_text() -> str:
    return (F.COMPOSABLES / FORMDATA).read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def host_text() -> str:
    return (F.COMPOSABLES.parent / HOST).read_text(encoding="utf-8", errors="replace")


class TestAcOneAndFourStayDone:
    """①④ 回归锁：它们**在本轮之前就成立**，spec 原文说①「静默」已过期。"""

    def test_all_retries_failed_path_reports_visibly(self, formdata_text: str) -> None:
        """① 落草稿与「可见上报」必须在同一分支里 —— 只落不报就是静默。"""
        m = _SETITEM_RE.search(formdata_text)
        assert m, "找不到落草稿的语句"
        window = formdata_text[m.start() : m.start() + 400]
        assert "ElMessage.warning" in window, (
            "落草稿后没有可见上报（同分支内找不到 ElMessage.warning）"
        )

    def test_restore_retries_put_immediately_and_deletes_on_success(self, formdata_text: str) -> None:
        """④ 回灌 → 立即重试 PUT（retries=1）→ 成功即删。"""
        assert re.search(r"saveImmediate\(itemId,\s*updated,\s*1\)", formdata_text), (
            "restoreDrafts 未以 retries=1 立即重试"
        )
        assert "localStorage.removeItem(key)" in formdata_text


class TestAcTwoAdapterWindowGate:
    """② adapter 回写窗口内不得落草稿。"""

    def test_suspend_flag_is_exposed_by_the_composable(self, formdata_text: str) -> None:
        for name in ("draftsSuspended", "setDraftsSuspended"):
            assert re.search(rf"\b{name}\b", formdata_text), f"{FORMDATA} 未暴露 {name}"

    def test_gate_sits_before_the_setitem_line(self, formdata_text: str) -> None:
        """🔴 位置判据：门必须在落草稿**之前**。

        写在后面等于没写 —— 草稿已经落盘了才判断，正是这条 AC 要防的形态。
        """
        gate = _SUSPEND_GATE_RE.search(formdata_text)
        setitem = _SETITEM_RE.search(formdata_text)
        assert gate, "找不到 `if (draftsSuspended.value)` 窗口门"
        assert setitem, "找不到落草稿的语句"
        assert gate.start() < setitem.start(), (
            f"窗口门在落草稿之后（gate@{gate.start()} > setItem@{setitem.start()}）⇒ 门形同虚设"
        )

    def test_gate_branch_returns_without_persisting(self, formdata_text: str) -> None:
        """门内必须 `return`，且**不得**在门内落草稿。"""
        gate = _SUSPEND_GATE_RE.search(formdata_text)
        assert gate
        body = formdata_text[gate.end() : gate.end() + 400]
        assert "return" in body, "窗口门分支没有 return，会继续往下落草稿"
        head = body.split("return", 1)[0]
        assert "setItem" not in head, "窗口门分支内仍在落草稿"
        assert "ElMessage" in head, "窗口门分支必须明说没保住（否则是另一种静默）"

    def test_host_drives_the_window_from_both_busy_and_oo_mode(self, host_text: str) -> None:
        """🔴 窗口取**并集**：只看 busy 会漏掉 `applied` 之后 reloadHtml 还没跑完那段。"""
        assert "setDraftsSuspended" in host_text, "宿主没有驱动窗口门"
        m = re.search(r"watch\(\s*\(\)\s*=>\s*([^,]+),", host_text, re.S)
        assert m, "宿主找不到驱动窗口的 watch"
        expr = m.group(1)
        assert "busy" in expr and "onlyoffice" in expr, (
            f"窗口表达式必须同时含 busy 与 OO 模式，实测 {expr.strip()!r}"
        )


class TestAcThreeVisibleDraftCount:
    """③ 未同步草稿条数必须用户可见。"""

    def test_count_is_computed_not_accumulated(self, formdata_text: str) -> None:
        """现算：遍历存储按前缀数；累加器看不到别的标签页/上个会话留下的草稿。"""
        assert "pendingDraftCount" in formdata_text
        assert "refreshPendingDraftCount" in formdata_text
        m = re.search(r"function refreshPendingDraftCount[\s\S]{0,600}", formdata_text)
        assert m and "localStorage.length" in m.group(0), "计数不是按存储现算"

    def test_count_refreshes_on_every_transition(self, formdata_text: str) -> None:
        """三个时点都要刷新：落草稿后 / PUT 成功删草稿后 / 回灌后。"""
        assert formdata_text.count("refreshPendingDraftCount()") >= 4, (
            "刷新点少于 4 处（定义 1 + 落草稿 / 删草稿 / 回灌 各 1）"
        )

    def test_host_renders_the_count_for_the_user(self, host_text: str) -> None:
        assert 'data-testid="h10-pending-draft-count"' in host_text
        assert "未同步草稿" in host_text
        assert "pendingDraftCount" in host_text

    def test_host_still_owns_no_client_storage_api(self, host_text: str) -> None:
        """🔴 反向断言：宿主只读计数，**不得**自己碰存储 API。

        HC-10 的分类判据按「文件文本里是否出现该 API 名」统计第三处存储的持有者；
        宿主一旦出现就会被记成新增一处，把 foundation 的清册搞脏。
        """
        assert "localStorage" not in host_text, (
            "宿主出现了客户端存储 API ⇒ 会被 HC-10 判据记成新增第三处存储"
        )
