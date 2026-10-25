"""HARD_CAPS 棘轮守卫 —— 让「瘦身后必须同步下调 cap」成为强制约束而非注释。

## 为什么需要这条

`check_file_size.py` 的 `HARD_CAPS` 是「超限即拒」。它有两个方向的失效：

1. **cap < 实际**（墙）：文件已超限时，**任何**触碰它的提交都被拒，包括把它改小的
   提交 ⇒ 门禁事实上禁止改进。2026-09-28 实测：一批把 `DisclosureEditor.vue` 从
   3398 减到 3044 的纯抽取重构被 pre-commit 硬拒。
2. **cap 远大于实际**（松）：瘦身后没人下调 cap ⇒ 留出的余量就是允许静默膨胀的空间。

第 1 种由「填真实值」处置（同 `ReportView.vue` 1110→1949 的既有先例）；
第 2 种此前**只有一句注释**「每完成一批瘦身必须同步下调此值」——
而本轮自己总结的教训 T29 恰恰是「有门禁 ≠ 门禁生效」，注释不是约束。
本文件把它变成断言。

## 判据

* 严格条目：`cap == 实际行数`（零余量）。瘦身后未下调 ⇒ 打红并给出应填的值。
* 刻意留余量的条目：必须在 `_INTENTIONAL_SLACK` 里逐条登记原因与上限。
* `_INTENTIONAL_SLACK` 不得有失效条目（文件已不存在 / 余量已归零）。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "check" / "check_file_size.py"


def _load():
    spec = importlib.util.spec_from_file_location("_cfs", _SCRIPT)
    assert spec and spec.loader, f"无法加载 {_SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_CFS = _load()

# ── 刻意留余量的条目（path -> (最大允许余量, 原因)）─────────────────────────
#
# gtdform-test-and-shrink（2026-05-30）登记这三个 shell 时明确按「实测值 + ~15% 余量」，
# 是那一轮的设计选择，不在本文件的处置范围内 ⇒ 登记豁免而非强行改它的决定。
# 🔴 新增条目一律走严格口径（零余量）；要留余量必须在此登记并写明理由。
_INTENTIONAL_SLACK: dict[str, tuple[int, str]] = {
    "audit-platform/frontend/src/components/workpaper/GtDForm/GtDFormReview.vue": (
        70,
        "gtdform-test-and-shrink 2026-05-30 按「实测 390 + ~15% 余量」登记 450，属该轮设计选择",
    ),
    "audit-platform/frontend/src/components/workpaper/GtDForm/GtDFormConfirmation.vue": (
        70,
        "同上：实测 366 + ~15% 余量 登记 420",
    ),
    "audit-platform/frontend/src/components/workpaper/GtDForm/GtDFormParagraph.vue": (
        70,
        "同上：实测 345 + ~15% 余量 登记 400",
    ),
}


def _actual(rel: str) -> int:
    p = _CFS.ROOT / rel
    return _CFS.count_lines(p) if p.exists() else -1


@pytest.mark.parametrize("rel", sorted(_CFS.HARD_CAPS))
def test_hard_cap_entry_points_at_existing_file(rel: str):
    """每条 cap 必须指向真实存在的文件（防改名后 cap 变成死条目、门禁静默失效）。"""
    assert (_CFS.ROOT / rel).exists(), (
        f"HARD_CAPS 指向不存在的文件：{rel} ⇒ 该条 cap 永不生效，请更新或删除"
    )


@pytest.mark.parametrize("rel", sorted(_CFS.HARD_CAPS))
def test_hard_cap_not_below_actual(rel: str):
    """cap 不得小于实际行数（否则门禁变成"墙"，连改小的提交都拒）。"""
    cap = _CFS.HARD_CAPS[rel]
    actual = _actual(rel)
    if actual < 0:
        pytest.skip("文件不存在，由上一条断言负责")
    assert actual <= cap, (
        f"🔴 {rel}: 实际 {actual} 行 > cap {cap} ⇒ 门禁会拒绝**任何**触碰该文件的提交，"
        f"包括把它改小的重构（2026-09-28 实测踩过）。"
        f"处置：先瘦身，或把 cap 填成真实值 {actual} 作为只许变小的棘轮。"
    )


@pytest.mark.parametrize("rel", sorted(_CFS.HARD_CAPS))
def test_hard_cap_has_no_stale_slack(rel: str):
    """瘦身后必须同步下调 cap —— 余量就是允许静默膨胀的空间。"""
    cap = _CFS.HARD_CAPS[rel]
    actual = _actual(rel)
    if actual < 0:
        pytest.skip("文件不存在，由第一条断言负责")
    slack = cap - actual
    allowed, reason = _INTENTIONAL_SLACK.get(rel, (0, ""))
    assert slack <= allowed, (
        f"🔴 {rel}: cap {cap} 而实际只有 {actual} 行，余量 {slack} > 允许 {allowed}。\n"
        f"   余量 = 允许该文件静默膨胀 {slack} 行，棘轮失效。\n"
        f"   处置：把 cap 下调为 {actual}；确有必要留余量请在 _INTENTIONAL_SLACK 登记并写明理由。"
        + (f"\n   当前登记理由：{reason}" if reason else "")
    )


def test_intentional_slack_has_no_dead_entries():
    """豁免名单不得有失效条目（文件已删 / 余量已归零 ⇒ 该条豁免已无意义）。"""
    dead: list[str] = []
    for rel, (allowed, _reason) in _INTENTIONAL_SLACK.items():
        if rel not in _CFS.HARD_CAPS:
            dead.append(f"{rel}（已不在 HARD_CAPS）")
            continue
        actual = _actual(rel)
        if actual < 0:
            dead.append(f"{rel}（文件不存在）")
            continue
        slack = _CFS.HARD_CAPS[rel] - actual
        if slack <= 0:
            dead.append(f"{rel}（余量已归零，无需豁免）")
    assert not dead, "以下豁免条目已失效，请从 _INTENTIONAL_SLACK 移出：\n  " + "\n  ".join(dead)


def test_intentional_slack_reasons_are_substantive():
    """豁免必须写明理由（防"加一行就绿"的后门）。"""
    thin = [rel for rel, (_a, reason) in _INTENTIONAL_SLACK.items() if len(reason) < 15]
    assert not thin, f"以下豁免条目理由过短：{thin}"


def test_ratchet_detects_artificially_raised_cap():
    """双向变异：人为抬高某条 cap，`test_hard_cap_has_no_stale_slack` 的判据必须打红。

    证明上面那条不是恒绿（它在当前树上全部通过，属"结构性零"，必须配变异）。
    """
    rel = "audit-platform/frontend/src/views/DisclosureEditor.vue"
    assert rel in _CFS.HARD_CAPS, "锚点条目已改名，请更新本变异测试"
    actual = _actual(rel)
    real_cap = _CFS.HARD_CAPS[rel]

    # 正向：当前应无余量
    assert real_cap - actual <= _INTENTIONAL_SLACK.get(rel, (0, ""))[0]

    # 反向：抬高 500 行后判据必须失败
    inflated = actual + 500
    slack = inflated - actual
    allowed = _INTENTIONAL_SLACK.get(rel, (0, ""))[0]
    assert slack > allowed, "变异未生效：抬高 cap 后仍被判为无余量 ⇒ 判据恒绿"
