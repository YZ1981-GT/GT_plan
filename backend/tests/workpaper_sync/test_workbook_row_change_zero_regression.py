# -*- coding: utf-8 -*-
"""Task 6 零回归基线守卫 —— `_rewrite_formula_refs` 的行为被冻结在磁盘上。

spec: excel-workbook-wide-row-change-propagation / Wave 0 Task 6
Requirements: 7.4, 7.7
Properties: **P28**

═══ 这份基线在防什么 ═══

Requirement 7.4：`propagate_sheets` 未声明传播时，行为与**本 spec 前**逐字相同。
「本 spec 前」是会随时间消失的参照物 —— 上游 spec 正在改 `excel_row_shift.py`，
一旦落地就再也无法取证。所以基线在门**之前**冻结（AC 7.7），本文件是它的守卫。

═══ 为什么是「摘要 + 样本」两层 ═══

🔴 **只存聚合计数会被互相抵消掉**：一处多改一个引用、另一处少改一个，`changed` 总数不变。
所以摘要是**顺序敏感的 `(sheet, 序号, 输入, 输出, 改动数)` 滚动 sha256**。
而 digest 变了只说明「变了」，所以再存**八类的完整输入/输出对**，让人立刻知道是哪一类
误命中回归了。

═══ 三个情景与它们各自的未来 ═══

| 情景 | 语义 | 谁会合法地改变它 |
|---|---|---|
| `insert_ctx` / `insert_no_ctx` | 受管 sheet 插行 | **没有人**。Task 28 加 `propagate_sheets` 后实测逐字不变 ✅ |
| `filldown` | 新行 fill-down | Task 27 已于 2026-09-05 合法改变过一次（Requirement 10） |

✅ **Task 28（2026-09-05）**：加 `propagate_sheets` 后三个情景全部逐字不变 —— 传播是加法，
空集时零回归。

✅ **Task 27（2026-09-05）已落地并重新冻结。** 差异形态经七条机械核验后才 `--apply`：
① 两个 insert 情景逐字不变（0 处变化）② 扫描面指标不变（公式条数 / 引用处数 / 3D / 外部
工作簿全等）③ `filldown` digest 在 **180 / 351** 份模板上变化 ④ `filldown` 的 `changed`
**只增不减**（0 处减少 —— 跨 sheet 相对引用由"不平移"改为"平移"，改动数只可能增加）
⑤ 分类样本的 insert 输出 0 处变化 ⑥ 3D 引用在三个情景下逐字不动 ⑦ 外部工作簿引用
6 条全部不变。

把三个情景分开冻结的价值就在这里：它让「Task 28 是纯加法」与「Task 27 是有意的行为变更」
在同一份基线上可分辨，而不是笼统地「基线变了」。

🔴 **Task 27 顺带暴露了本基线自己的一个盲区，已修**：`filldown` 情景原先**不传**
`translate_qualified_rows`，而真实入口 `translate_formula_rows` 传了 ⇒ fill-down 语义改完
之后基线**没有变红**，与上面「Task 27 必然变红」的声明矛盾。一条声称在观测某函数、参数
却与它不同的判据，观测的是**一条没人走的路**；这类盲区不会以假红暴露，只会让本该变红的
时刻悄悄溜过。现由 `test_filldown_scenario_matches_real_entrypoint_params` 用 AST 锁死
「真实入口传的关键字实参 ⊆ 情景 kwargs」。

═══ 判据纪律 ═══

* 分母断言全部落在 design.md「分母断言」表的 Wave 0 复算值上，**不用** requirements.md
  Introduction 原登记的 176 / 81,955（复算不上，见分工书 §11.1）。
* 八类样本各自断言条数 > 0 —— 3D 全库实测 **0** 处，只能用显式登记的合成用例，
  否则该类判据在空集上恒真。
* 反向自检：扰动现算结果后 `diff_baseline` 必须报出差异；不报 = 比对器坏了。
"""

from __future__ import annotations

import ast
import copy
import inspect
import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
for _p in (str(_BACKEND), str(_BACKEND / "scripts" / "gen")):
    if _p not in sys.path:  # pragma: no cover - import 环境自举
        sys.path.insert(0, _p)
os.environ.setdefault("DB_DISABLE_SSL", "True")

import generate_workbook_row_change_zero_regression_baseline as G  # noqa: E402
from app.services.workpaper_sync import excel_row_shift as RS  # noqa: E402

#: design.md「分母断言」表的复算值。改这里必须同时改 design.md，两侧锁死。
#:
#: 🔴 **2026-09-29 更新（D4 重复文件删除）**：
#: `wp_templates/D/D4收入底稿.xlsx`（无空格）与 `D4 收入底稿.xlsx`（带空格）是**同一份
#: 底稿的重复文件**。用户核实后删掉了无空格那份，保留的是**被净化过**的版本（外部链接
#: 部件已丢弃 ⇒ 该模板 `external_sites` 265→0、`formulas` 438→168）。
#: 基线里那一条已做**手术式**改名（键换名 + 记录换成现算值 + 分母按 `per_template`
#: **重算**而非手填），因此下面这组值与基线内部自洽这件事由构造保证。
#:
#: ⚠ 与上游 `excel-workbook-wide-row-change-propagation/design.md` 的「分母断言」表
#: 存在**两处已知不一致**，且**在本次改动之前就已存在**：
#:   * `xlsx_total` —— design.md 记 **352**（当时两份 D4 并存），本表记 351。
#:     重复文件删除后 351 才是真值；
#:   * `external_sites` —— design.md 记 **2902**，本表记 2643（净化后的 D4 少了 265 处）。
#: 不在本 spec 里改上游 design.md（跨 spec 回填另立工单）；此处**如实登记**该差异，
#: 而不是把它抹平成「两侧一致」。
EXPECTED_DENOMINATORS: dict[str, int] = {
    "xlsx_total": 351,
    "templates_with_cross_sheet": 181,
    "cross_sheet_sites": 144149,
    "cross_sheet_formulas": 72820,
    "three_d_sites": 0,
    "external_sites": 2643,
}

#: 属**别 lane**、已登记的语料漂移：这些模板的**内容**被其它会话/提交改过，
#: 与 `_rewrite_formula_refs` 的行为无关。
#:
#: 🔴 为什么**不**整册 `--apply` 吸收它们（沿用 `d3-sync-coverage-via-row-table-engine`
#: 证据文档已立的先例）：
#:   * `M/M10 其他权益工具.xlsx` 在工作树里还是**未提交**状态 —— 把在飞改动冻进基线，
#:     等那个会话收敛或回滚后基线又对不上；
#:   * `L/L5` / `L/L6` 来自上游提交 `3036967ea`(2026-09-27)，属 L 循环 lane；
#:   * 整册重生成会把这些别 lane 的漂移**一并吸收** ⇒ 掩盖它们，而那正是这份基线
#:     要防的事。
#:
#: ⚠ 本清单是**可伪证**的：`test_registered_corpus_drift_has_no_stale_entries` 断言
#: 每一项**现在真的在漂**。哪条 lane 收敛了（或模板回滚了），该项当场打红，要求删掉它。
REGISTERED_CORPUS_DRIFT: dict[str, str] = {
    "D/D7 合同负债.xlsx": "模板净化 lane（`1a0b55651`）：公式 206→200",
    "L/L5 长期应付款.xlsx": "L 循环 lane（`3036967ea` 2026-09-27）：公式 386→667",
    "L/L6 专项应付款.xlsx": "L 循环 lane（`3036967ea` 2026-09-27）：公式 249→348",
    "M/M10 其他权益工具.xlsx": "并发会话**未提交**改动（`git status` 为 `M`）：公式 165→279",
}

#: 全库为 0、只能用合成用例的类。
SYNTHETIC_ONLY_CLASSES: frozenset[str] = frozenset({"three_d"})


@pytest.fixture(scope="module")
def stored() -> dict[str, Any]:
    assert G.BASELINE_PATH.is_file(), (
        f"零回归基线缺失：{G.BASELINE_PATH.relative_to(_REPO)} —— "
        "它必须入库，否则干净 checkout 下本守卫无从比对（规则 7 第 3 项）"
    )
    return G.load_baseline()


@pytest.fixture(scope="module")
def current() -> dict[str, Any]:
    """现算一次，全模块共用（全库 351 份实测约 9 秒）。"""
    return G.compute_baseline()


# ═══════════════════════════════════════════════════════════════════════════
# 1. 零回归本体
# ═══════════════════════════════════════════════════════════════════════════


def test_behaviour_matches_frozen_baseline(
    current: dict[str, Any], stored: dict[str, Any]
) -> None:
    """🔴 `_rewrite_formula_refs` 的行为与冻结基线逐字相同。

    🔴 差异按来源**分区**（2026-09-29）：`REGISTERED_CORPUS_DRIFT` 里那几份模板的
    **内容**被别的 lane 改过，那不是改写器的行为变化。分区后残留必须为空。

    这不是「加豁免蒙绿」：
    * 清单逐项**可伪证**（下一条判据断言每项现在真的在漂，收敛了就打红要求删除）；
    * `denominators` 那一行被放行，但另有一条判据把**排除登记模板之后**的分母逐键对齐 ——
      于是「别处的分母也变了」照旧打红；
    * 其余 346 份模板仍是逐值相等的硬断言。
    """
    problems = G.diff_baseline(current, stored)
    registered = [
        line
        for line in problems
        if line.startswith("denominators ")
        or any(name in line for name in REGISTERED_CORPUS_DRIFT)
    ]
    residual = [line for line in problems if line not in registered]
    assert not residual, (
        f"`_rewrite_formula_refs` 行为已偏离冻结基线（{len(residual)} 处**未登记**差异，"
        f"另有 {len(registered)} 处属已登记的别 lane 语料漂移）。\n"
        "若这是 Task 27（Requirement 10 修 fill-down）导致的**有意**变更：\n"
        "  1. 确认差异全部落在 `filldown` 情景且都是跨 sheet 相对引用；\n"
        "  2. `insert_ctx` / `insert_no_ctx` 不得变；\n"
        "  3. 再跑 --apply 重新冻结并在 commit 里写明理由。\n"
        "若是别的 lane 改了模板：补进 `REGISTERED_CORPUS_DRIFT` 并写明归因。\n"
        "否则这是真回归。\n未登记差异（前 20）：\n  " + "\n  ".join(residual[:20])
    )


def test_registered_corpus_drift_has_no_stale_entries(
    current: dict[str, Any], stored: dict[str, Any]
) -> None:
    """🔴 `REGISTERED_CORPUS_DRIFT` 每一项**现在真的在漂** —— 豁免须可伪证。

    某条 lane 收敛（或模板回滚）之后，那一项就成了一条谁也不知道还管不管用的豁免。
    本条让它当场打红，要求删掉。
    """
    s_t, c_t = stored["per_template"], current["per_template"]
    stale = [
        name
        for name in REGISTERED_CORPUS_DRIFT
        if name in s_t and name in c_t and s_t[name] == c_t[name]
    ]
    assert not stale, (
        f"这些登记项已经不漂了：{stale} —— 请从 `REGISTERED_CORPUS_DRIFT` 删掉它们"
        "（并确认 `test_behaviour_matches_frozen_baseline` 仍绿）"
    )
    missing = [name for name in REGISTERED_CORPUS_DRIFT if name not in c_t or name not in s_t]
    assert not missing, (
        f"登记项在基线或现算里不存在：{missing} —— 模板被删/改名了，登记要跟着改"
    )


def test_denominators_excluding_registered_drift_still_match(
    current: dict[str, Any], stored: dict[str, Any]
) -> None:
    """🔴 把登记模板**排除**之后，分母逐键仍然相等。

    这是上一条放行 `denominators` 那一行的补偿控制：若别处的分母也变了（那才是真回归），
    本条会打红。没有它，`denominators` 就成了一个把任何聚合变化都吞掉的口子。
    """
    fields = (
        "formulas",
        "cross_sheet_formulas",
        "cross_sheet_sites",
        "external_sites",
        "three_d_sites",
    )

    def _totals(per: dict[str, Any]) -> dict[str, int]:
        rows = [r for name, r in per.items() if name not in REGISTERED_CORPUS_DRIFT]
        out = {f: sum(int(r[f]) for r in rows) for f in fields}
        out["templates"] = len(rows)
        out["templates_with_cross_sheet"] = sum(
            1 for r in rows if int(r["cross_sheet_sites"]) > 0
        )
        return out

    got = _totals(current["per_template"])
    want = _totals(stored["per_template"])
    assert got["templates"] > 300, f"排除后只剩 {got['templates']} 份 ⇒ 判据被缩到无意义"
    assert got == want, (
        f"排除登记模板之后分母仍不相等 ⇒ 别处也变了（真回归）：现算 {got} / 基线 {want}"
    )


def test_denominators_match_design_table(stored: dict[str, Any]) -> None:
    """分母与 design.md「分母断言」表逐个相等 —— 防基线在缩小的样本上恒真。"""
    actual = stored["denominators"]
    for key, expected in EXPECTED_DENOMINATORS.items():
        assert actual.get(key) == expected, (
            f"分母 {key} 与 design.md 的 Wave 0 复算值不一致：期望 {expected}，"
            f"基线里是 {actual.get(key)}"
        )
    assert actual["formula_texts"] > actual["cross_sheet_formulas"] > 0, (
        "公式总条数必须严格大于含跨 sheet 引用的条数（否则说明扫描面被缩小了）"
    )


def test_baseline_covers_every_template(stored: dict[str, Any]) -> None:
    """逐模板都有记录，且记录数 == xlsx 总数。"""
    per_template = stored["per_template"]
    assert len(per_template) == EXPECTED_DENOMINATORS["xlsx_total"], (
        f"基线覆盖 {len(per_template)} 份模板，应为 "
        f"{EXPECTED_DENOMINATORS['xlsx_total']} 份"
    )
    for rel, rec in per_template.items():
        assert set(rec["digest"]) == set(G.SCENARIOS), f"{rel} 缺情景 digest"
        for name in G.SCENARIOS:
            assert len(rec["digest"][name]) == 64, f"{rel}/{name} 的 digest 形态非法"


def test_three_scenarios_are_distinguishable(stored: dict[str, Any]) -> None:
    """三个情景必须真的产出不同结果 —— 否则参数组合没被区分开，基线只覆盖了一种行为。

    判据落在**至少有一份模板**上三者两两不同（而不是全库都不同：无公式的模板三者都相同
    是正常的）。
    """
    distinct = 0
    for rec in stored["per_template"].values():
        digests = {rec["digest"][name] for name in G.SCENARIOS}
        if len(digests) == len(G.SCENARIOS):
            distinct += 1
    assert distinct > 0, (
        "没有任何一份模板让三个情景产出不同 digest —— 说明 remap / current_sheet /"
        " freeze_absolute_rows 三组参数没被真正区分，基线只覆盖了一种行为"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 分类样本
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("side", ["stored", "current"])
def test_every_class_has_samples(
    side: str, stored: dict[str, Any], current: dict[str, Any]
) -> None:
    """八类各自有样本 —— 空集上的样本判据恒真。

    🔴 **两侧都查**（磁盘基线 + 现算）。变异检验实测过：只查 `stored` 时，把
    `SYNTHETIC_THREE_D` 清空这个变异会先被 `test_behaviour_matches_frozen_baseline`
    抓住（判 WRONG-TEST）—— 语义上该由本条报出「某类不再有样本」，而不是笼统地
    「基线变了」。两侧都查之后，问题落在语义正确的那条判据上。
    """
    payload = stored if side == "stored" else current
    samples = payload["class_samples"]
    assert set(samples) == set(G.ALL_CLASSES), (
        f"[{side}] 样本类集合与登记不一致：{sorted(set(samples) ^ set(G.ALL_CLASSES))}"
    )
    for cls, bucket in samples.items():
        assert bucket, f"[{side}] 分类 {cls} 一条样本都没有 —— 该类判据会在空集上恒真"
        for item in bucket:
            assert set(item["outputs"]) == set(G.SCENARIOS)


def test_synthetic_classes_are_declared_synthetic(stored: dict[str, Any]) -> None:
    """全库为 0 的类必须**全部**是显式登记的合成用例；有真实样本的类不得混入合成。"""
    samples = stored["class_samples"]
    for cls in SYNTHETIC_ONLY_CLASSES:
        bucket = samples[cls]
        assert all(item["synthetic"] for item in bucket), (
            f"{cls} 全库实测 0 处，样本必须全部标 synthetic=True"
        )
        assert stored["denominators"]["three_d_sites"] == 0, (
            "3D 引用处数不再是 0 —— 该类已有真实样本，应改用真实样本而非合成用例"
        )
    for cls, bucket in samples.items():
        if cls in SYNTHETIC_ONLY_CLASSES:
            continue
        assert any(not item["synthetic"] for item in bucket), (
            f"{cls} 全是合成用例 —— 该类在真实模板里应有样本，退化成合成说明分类器坏了"
        )


def test_cross_sheet_refs_stay_verbatim_under_insert(stored: dict[str, Any]) -> None:
    """行为判据（不是 digest）：插行情景下跨 sheet 引用逐字不动。

    这是 `_rewrite_formula_refs` 的四类误命中防护里最重要的一条（跨 sheet 目标格不跟本 sheet
    位移）。digest 只能证明「没变」，这条证明「现在的行为是对的」。
    """
    checked = 0
    for item in stored["class_samples"]["cross_sheet_verbatim"]:
        sheet = item["sheet"]
        before = [
            (k, s, t)
            for k, s, t in G._qualified_hits(item["input"])
            if k == "sheet" and s != sheet
        ]
        assert before, f"样本被误分类，没有跨 sheet 引用: {item['input']!r}"
        for scenario in ("insert_ctx", "insert_no_ctx"):
            after = [
                (k, s, t)
                for k, s, t in G._qualified_hits(item["outputs"][scenario])
                if k == "sheet" and s != sheet
            ]
            assert after == before, (
                f"{scenario} 下跨 sheet 引用被改动了（应逐字不动）：\n"
                f"  模板 {item['template']} / sheet {sheet}\n"
                f"  输入 {item['input']!r}\n  输出 {item['outputs'][scenario]!r}"
            )
            checked += 1
    assert checked > 0, "一条都没检到 —— 防空集恒真"


def test_self_qualified_refs_do_shift_with_context(stored: dict[str, Any]) -> None:
    """反面对照：`'本表'!A9` 在 `current_sheet` 匹配时**必须**位移。

    与上一条合起来才说明「跨 sheet 逐字不动」是**有条件的判断**而不是「一律不动」——
    只测前者的话，把整个限定引用分支短路掉也能全绿。
    """
    shifted = 0
    for item in stored["class_samples"]["self_qualified"]:
        if item["outputs"]["insert_ctx"] != item["input"]:
            shifted += 1
    assert shifted > 0, (
        "没有任何自限定引用样本在 `insert_ctx`（current_sheet 匹配）下发生位移 —— "
        "说明自限定分支从未被执行，或样本的行号全部 < "
        f"{G.CANONICAL_INSERT_AT}（该情况须换样本）"
    )


def test_filldown_shifts_cross_sheet_relative_refs(stored: dict[str, Any]) -> None:
    """fill-down 下跨 sheet **相对**行引用必须平移（AC 10.1，Task 27 已落地）。

    ═══ 本判据的来历 ═══

    它的前身是 `test_filldown_currently_does_not_shift_cross_sheet_refs` —— 把
    Requirement 10 要修的**缺陷**冻结成判据，好让 Task 27 落地时必然变红。
    2026-09-05 Task 27 落地后按其 docstring 的要求**翻转**成本条：断言「会平移」。

    留着旧判据不改就是「守卫把错值当基线锁死」那类假绿 —— 缺陷会被永久固化，
    而 AC 10.1 与它不能同时为真。

    ═══ 缺陷是什么 ═══

    修之前 `='明细表K11-2'!F29` fill-down 到下一行**不平移**，于是新插入行与样式来源行
    指向**同一个源格** ⇒ 静默重复取数（看着"有值"但是错的）。Excel 填充柄的真实语义是
    相对引用不论是否带 sheet 前缀都随行平移。

    ⚠ 只断言「至少一处平移了」不够 —— 那条件在「把所有限定引用都无脑位移」时也成立，
    而那会撞坏表名（`'明细表K11-2'` → `'明细表K12-2'`，指向不存在的 sheet）。所以这里
    **同时**断言：目标格行号平移了 **且 sheet 名一个字符都没动**。
    """
    shifted = unshifted = 0
    for item in stored["class_samples"]["cross_sheet_verbatim"]:
        sheet = item["sheet"]
        before = [
            (k, s, t)
            for k, s, t in G._qualified_hits(item["input"])
            if k == "sheet" and s != sheet
        ]
        after = [
            (k, s, t)
            for k, s, t in G._qualified_hits(item["outputs"]["filldown"])
            if k == "sheet" and s != sheet
        ]
        if not before:
            continue

        # sheet 名集合必须逐字相同 —— 平移只动目标格行号，绝不碰表名
        assert [s for _k, s, _t in before] == [s for _k, s, _t in after], (
            "fill-down 平移把 sheet 名改了 —— 表名里的「字母+数字」被当成坐标位移了，"
            "产物会指向不存在的 sheet 当场死掉：\n"
            f"  模板 {item['template']} / sheet {sheet}\n"
            f"  输入 {item['input']!r}\n  输出 {item['outputs']['filldown']!r}"
        )

        for (_kb, _sb, tb), (_ka, _sa, ta) in zip(before, after):
            if not tb:
                continue
            # `$` 全锁的目标格不该动（AC 10.2）；含相对行的应当动
            if "$" in tb and not re.search(r"(?<!\$)\d", tb):
                assert ta == tb, (
                    f"绝对行被平移了（AC 10.2）：{tb!r} → {ta!r}\n"
                    f"  模板 {item['template']} / {item['input']!r}"
                )
            elif ta != tb:
                shifted += 1
            else:
                unshifted += 1

    assert shifted > 0, (
        "fill-down 下没有任何跨 sheet 相对引用被平移 —— AC 10.1 未生效。"
        "若 `translate_formula_rows` 的 `translate_qualified_rows=True` 被去掉，"
        "或基线的 `filldown` 情景没有跟着传这个参数，本条就会红"
    )


def test_filldown_scenario_matches_real_entrypoint_params() -> None:
    """🔴 基线的 `filldown` 情景参数必须与真实入口 `translate_formula_rows` 一致。

    ═══ 为什么需要这一条 ═══

    Task 27 实测踩到的判据盲区：`filldown` 情景原先**不传** `translate_qualified_rows`，
    而真实入口传了。后果是 fill-down 语义改完之后基线**没有变红** —— 而生成器 docstring
    与守卫都写明「Task 27 落地时 filldown 必然变红」。

    一条声称在观测某个函数、而参数与它不同的判据，观测的是**一条没人走的路**。这类盲区
    不会以假红的形式暴露，只会让本该变红的时刻悄悄溜过去。

    判据形态：`translate_formula_rows` 源码里出现的关键字实参名（除 `remap` 外，它是
    情景自带的行映射）必须**全部**出现在 `filldown` 情景的 kwargs 里。用 AST 取实参名
    而不是 grep 字符串 —— docstring 里提到参数名不算。
    """
    source = inspect.getsource(RS.translate_formula_rows)
    tree = ast.parse(textwrap.dedent(source))

    passed_kwargs: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = getattr(callee, "id", None) or getattr(callee, "attr", None)
        if name != "_rewrite_formula_refs":
            continue
        passed_kwargs = {kw.arg for kw in node.keywords if kw.arg}

    assert passed_kwargs, (
        "在 `translate_formula_rows` 里找不到对 `_rewrite_formula_refs` 的调用 —— "
        "本判据的基础失效（函数可能被改名或改成了别的入口），必须先修判据"
    )

    scenario_kwargs = set(G._scenario_kwargs("filldown", "审定表K11-1"))
    missing = sorted((passed_kwargs - {"remap"}) - scenario_kwargs)
    assert not missing, (
        f"基线的 `filldown` 情景缺少真实入口会传的参数 {missing} —— "
        "该情景冻结的不是 `translate_formula_rows` 的行为，是一条没人走的路。"
        f"\n  真实入口传的： {sorted(passed_kwargs)}"
        f"\n  情景 kwargs：  {sorted(scenario_kwargs)}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 反向自检：比对器真的会报差异
# ═══════════════════════════════════════════════════════════════════════════


def test_diff_detects_digest_change(current: dict[str, Any], stored: dict[str, Any]) -> None:
    """扰动一份模板的 digest ⇒ 必须被报出来。"""
    mutated = copy.deepcopy(current)
    rel = sorted(mutated["per_template"])[0]
    mutated["per_template"][rel]["digest"]["insert_ctx"] = "0" * 64
    problems = G.diff_baseline(mutated, stored)
    assert any(rel in p and "digest" in p for p in problems), (
        f"比对器没报出 digest 变化 —— 它坏了。实得 {problems[:5]}"
    )


def test_diff_detects_offsetting_changed_counts(
    current: dict[str, Any], stored: dict[str, Any]
) -> None:
    """🔴 两处相反的 `changed` 变化（总数不变）也必须被报出来。

    这是「只存聚合计数不够」的实证：如果基线只比对全库 `changed` 之和，下面这个扰动
    会完全隐形。逐模板比对 + 顺序敏感 digest 才拦得住。
    """
    mutated = copy.deepcopy(current)
    rels = sorted(mutated["per_template"])
    a, b = rels[0], rels[1]
    mutated["per_template"][a]["changed"]["insert_ctx"] += 1
    mutated["per_template"][b]["changed"]["insert_ctx"] -= 1

    total_before = sum(
        r["changed"]["insert_ctx"] for r in current["per_template"].values()
    )
    total_after = sum(
        r["changed"]["insert_ctx"] for r in mutated["per_template"].values()
    )
    assert total_before == total_after, "构造失败：这个扰动本应让总数不变"

    problems = G.diff_baseline(mutated, stored)
    assert any("changed" in p for p in problems), (
        "相互抵消的 changed 变化没被报出来 —— 说明比对退化成了聚合口径"
    )


def test_diff_detects_sample_change(current: dict[str, Any], stored: dict[str, Any]) -> None:
    """扰动分类样本的输出 ⇒ 必须被报出来。"""
    mutated = copy.deepcopy(current)
    mutated["class_samples"]["cross_sheet_verbatim"][0]["outputs"]["insert_ctx"] = "=BROKEN"
    problems = G.diff_baseline(mutated, stored)
    assert any("cross_sheet_verbatim" in p for p in problems)


def test_diff_detects_denominator_shrink(
    current: dict[str, Any], stored: dict[str, Any]
) -> None:
    """缩小分母（少扫了模板）必须被报出来 —— 防「在更小的样本上恒真」。"""
    mutated = copy.deepcopy(current)
    dropped = sorted(mutated["per_template"])[0]
    del mutated["per_template"][dropped]
    mutated["denominators"]["xlsx_total"] -= 1
    problems = G.diff_baseline(mutated, stored)
    assert any("denominators" in p for p in problems)
    assert any("基线里有而现算没有的模板" in p for p in problems)


def test_diff_is_empty_on_identical_payload(current: dict[str, Any]) -> None:
    """同一份载荷自比必须无差异 —— 防比对器把易变字段（耗时）当行为差异。"""
    assert G.diff_baseline(current, json.loads(json.dumps(G.comparable(current)))) == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. 反向自检：真实行为变化真的会被抓住
# ═══════════════════════════════════════════════════════════════════════════

#: 用 K11 做反向自检 —— 它含 114 处跨 sheet 引用，重算一份是毫秒级。
_PROBE_TEMPLATE = "K/K11 资产减值损失.xlsx"


def test_guard_detects_real_rewriter_behaviour_change(
    monkeypatch: pytest.MonkeyPatch, stored: dict[str, Any]
) -> None:
    """🔴 最关键的一条反向自检：改写器**真的**变了行为 ⇒ digest 必须变。

    上面几条反向自检扰动的是「基线数据」，证明的是**比对器**没坏；这一条扰动的是
    **改写器本身**，证明的是「基线真的挂在被观测对象上」。少了它，整份基线可能只是
    在比对两份互相复制来的数字（假绿第②源）。

    ⚠ 做法刻意是**进程内 monkeypatch**，不改磁盘上的 `excel_row_shift.py` ——
    那个文件归上游 spec 且正被并发会话编辑，变异式改文件再复原会有覆盖对方改动的风险
    （规则 1 / 分工书 §6）。
    """
    path = G.TEMPLATE_ROOT / _PROBE_TEMPLATE
    assert path.is_file(), f"探针模板缺失: {_PROBE_TEMPLATE}"

    frozen = stored["per_template"][_PROBE_TEMPLATE]["digest"]
    clean = G.compute_template(path)["digest"]
    assert clean == frozen, (
        "反向自检的前提不成立：未扰动时该模板的 digest 就已偏离基线"
    )

    original = G._rewrite_formula_refs

    def _perturbed(text: str, **kwargs: Any) -> tuple[str, int]:
        """把「跨 sheet 引用逐字不动」这条防护短路掉：让跨 sheet 目标格也跟着位移。"""
        out, n = original(text, **kwargs)
        if "!" in text:
            return out.replace("F29", "F30"), n
        return out, n

    monkeypatch.setattr(G, "_rewrite_formula_refs", _perturbed)
    perturbed = G.compute_template(path)["digest"]

    assert perturbed != frozen, (
        "改写器行为被扰动后 digest 却没变 —— 基线没有真正挂在 `_rewrite_formula_refs` 上，"
        "它只是在比对两份互相复制来的数字"
    )
    changed_scenarios = [s for s in G.SCENARIOS if perturbed[s] != frozen[s]]
    assert len(changed_scenarios) == len(G.SCENARIOS), (
        f"只有 {changed_scenarios} 变了 —— 三个情景应各自独立感知改写器的变化"
    )


def test_digest_is_order_sensitive() -> None:
    """digest 必须顺序敏感 —— 否则两处互换位置的变化会互相抵消。

    直接用 digest 的配方验证：同一组 `(输入, 输出)` 换个顺序滚进 sha256 必须得到不同结果。
    这条是 `test_diff_detects_offsetting_changed_counts` 的下一层保险。
    """
    import hashlib

    def roll(items: list[tuple[str, int, str, str, int]]) -> str:
        h = hashlib.sha256()
        for sheet, seq, text, new, n in items:
            h.update(f"{sheet}\x1f{seq}\x1f{text}\x1f{new}\x1f{n}\x1e".encode("utf-8"))
        return h.hexdigest()

    a = [("S", 0, "=A7", "=A8", 1), ("S", 1, "=B7", "=B8", 1)]
    assert roll(a) != roll(list(reversed(a))), "digest 不是顺序敏感的"


# ═══════════════════════════════════════════════════════════════════════════
# Property 28 冻结基线看门狗
# （spec workpaper-sync-row-deletion-multi-region-propagation，Task 19）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么本 spec 要给**别人的**冻结基线加看门狗：
#
# 本 spec 的约束之一是「不改 Property 28 冻结基线的被观测对象」。而删行侧要做的事
# （区间端点按方向塌陷）最自然的实现就是去 `_rewrite_formula_refs` 里加一个删行分支 ——
# 一旦那么做，这份基线的语义就变了，而它是插行侧**逐字节零回归**的全部依据。
#
# 「不改」如果只写在 requirements 里，就只是一句承诺。下面这组判据把它变成会打红的事实：
# 基线文件本身、三个被观测符号的源码、以及情景清单，逐个冻结 sha256。
#
# 🔴 判据故意用 **sha256 of source** 而不是「函数还在」或「行数没变」：
#    前者对**任何**改动敏感（包括只加一个 `if`），后两者对语义改动几乎无感。

#: 交付时现算（探针 `_bdelp_p28_freeze.py`）。
#:
#: 🔴 若这里打红且改动是**有意**的：改这里的期望值，并在提交说明里**逐处论证**每一个
#: diff 的合法性 —— 那份基线保护的是插行侧全库 351 份模板的逐字节行为，
#: 「顺手重生成」等于把那层保护静默移除。
#: 🔴 **禁止**在实施中顺手跑生成器的 `--apply`（tasks 19.2 的执行纪律）。
FROZEN_P28_SHA: dict[str, str] = {
    # 2026-09-29 更新：D4 重复文件删除后做了**手术式**改名（见 EXPECTED_DENOMINATORS 注释）。
    # 前值 421e7bf84591da6f960f3ef864bcd9017356c58ad7c682095468aac7ef3a0ffc。
    # 🔴 改动只涉一个 per_template 键与 5 个由记录重算的分母；三个被观测符号的源码 sha
    #    **逐字未变**（下面三条判据现场证明）⇒ 改写器行为没变，这是本次改名合法的依据。
    "baseline_file": "fbe72a9eb8bd8d854aa76d7afb132a509065e0080856a05865683454d817313b",
    "_rewrite_formula_refs": (
        "00330a210600959fc3f184dad8fe88d50633e303ae0a44329eab8a0b4b315cc1"
    ),
    "translate_formula_rows": (
        "8aeee2f8031f7c01c026b5a8c976eaa2a10bba46c15a7949fa5c06f8de9b1a1e"
    ),
    "_scenario_kwargs": (
        "ce3578d8d9f3540bf05d379af9da1262fca5e36aaf83dcf5cbf4085a7960fdb6"
    ),
    "SCENARIOS": "0e8a67233aa76f2181acc87360a4ad480e17989ccedc0fd8050d09b479726f2c",
}

#: 三个情景 —— 全是**插行**侧的。删行有自己的载体与自己的基线
#: （`data/clear_path_byte_baseline.json`），不得混进这里。
EXPECTED_SCENARIOS: tuple[str, ...] = ("insert_ctx", "insert_no_ctx", "filldown")


def _source_sha(obj: Any) -> str:
    import hashlib

    return hashlib.sha256(
        textwrap.dedent(inspect.getsource(obj)).encode("utf-8")
    ).hexdigest()


class TestProperty28BaselineWatchdog:
    """**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5**

    spec: workpaper-sync-row-deletion-multi-region-propagation
    """

    def test_baseline_file_sha_is_frozen(self) -> None:
        """🔴 基线文件本身的 sha256（Requirements 10.3 / 10.4）。"""
        import hashlib

        assert G.BASELINE_PATH.is_file(), G.BASELINE_PATH
        got = hashlib.sha256(G.BASELINE_PATH.read_bytes()).hexdigest()
        assert got == FROZEN_P28_SHA["baseline_file"], (
            f"Property 28 的基线文件被改了：现算 {got} / 冻结 "
            f"{FROZEN_P28_SHA['baseline_file']}。\n"
            "🔴 若是**有意**重生成：改 `FROZEN_P28_SHA['baseline_file']` 的期望值，"
            "并在提交说明里逐处论证每一个 diff 的合法性 —— 这份基线是插行侧全库 351 份"
            "模板逐字节零回归的全部依据。\n"
            "若不是有意的：有人跑了生成器的 `--apply`，请回滚。"
        )

    @pytest.mark.parametrize(
        ("name", "obj_path"),
        [
            ("_rewrite_formula_refs", "RS._rewrite_formula_refs"),
            ("translate_formula_rows", "RS.translate_formula_rows"),
            ("_scenario_kwargs", "G._scenario_kwargs"),
        ],
    )
    def test_observed_symbol_source_is_frozen(self, name: str, obj_path: str) -> None:
        """🔴 被观测对象的**源码**逐字冻结（Requirements 10.1 / 10.2 / 10.5）。

        本 spec 明确不改它们：删行侧的端点方向感知走的是
        `excel_materialize.remap_bare_a1_for_deletion`（把上下文放进 `remap` 自己），
        以及 `excel_workbook_row_change._range_aware_remap` —— 两者都是**实参**层面的，
        改写器一个字都不动。
        """
        module, attr = obj_path.split(".", 1)
        obj = getattr({"RS": RS, "G": G}[module], attr)
        got = _source_sha(obj)
        assert got == FROZEN_P28_SHA[name], (
            f"`{name}` 的源码变了：现算 {got} / 冻结 {FROZEN_P28_SHA[name]}。\n"
            "🔴 本 spec 的约束之一就是**不改**它（Requirement 10.1）。若实施中发现必须改："
            "停下按范围变更处理 —— 先按 Property 28 守卫 docstring 记载的七条机械核验"
            "逐条取证，再显式重新冻结，并在提交说明里论证每一处 diff 的合法性。"
        )

    def test_scenarios_is_still_the_insert_only_triple(self) -> None:
        """🔴 情景清单仍是三元组，且**不含**删行情景（Requirement 10.2）。

        往这里加一个删行情景，看起来是「顺手扩大覆盖」，实际是把插行侧的冻结基线
        与删行侧的新行为绑在一起 —— 此后任何一侧改动都要重生成，那层保护就废了。
        """
        import hashlib

        assert tuple(G.SCENARIOS) == EXPECTED_SCENARIOS, (
            f"SCENARIOS 变了：{tuple(G.SCENARIOS)} —— 删行有自己的基线"
            "（`data/clear_path_byte_baseline.json`），不得混进这里"
        )
        assert len(G.SCENARIOS) == 3
        got = hashlib.sha256(repr(tuple(G.SCENARIOS)).encode("utf-8")).hexdigest()
        assert got == FROZEN_P28_SHA["SCENARIOS"], got
        assert not any(
            token in str(G.SCENARIOS).lower() for token in ("delete", "shrink", "remove")
        ), G.SCENARIOS

    def test_deletion_side_passes_its_remap_as_an_argument(self) -> None:
        """🔴 AST：删行侧的反向映射通过**实参**传入，不是改写器的内部常量。

        这是「不改被观测对象」得以成立的机制：改写器只认 `remap` 这个入参，
        方向语义放在调用方构造的函数里。若哪天有人把 `deleted_rows` 之类的名字写进
        改写器内部，上面的源码 sha 会先打红；本条从**另一侧**钉住同一件事 ——
        调用方必须真的在传 `remap`。
        """
        import ast

        from app.services.workpaper_sync import excel_materialize as M
        from app.services.workpaper_sync import excel_workbook_row_change as N1

        for owner, func in (
            ("excel_materialize.remap_bare_a1_for_deletion", M.remap_bare_a1_for_deletion),
            ("excel_workbook_row_change._range_aware_remap", N1._range_aware_remap),
        ):
            src = textwrap.dedent(inspect.getsource(func))
            tree = ast.parse(src)
            # 该函数里（或它的返回值里）必须出现 `remap=` 关键字实参，或它本身就是 remap 工厂
            has_remap_kwarg = any(
                kw.arg == "remap"
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                for kw in node.keywords
            )
            returns_callable = any(
                isinstance(node, ast.FunctionDef) for node in ast.walk(tree)
            ) or any(isinstance(node, ast.Lambda) for node in ast.walk(tree))
            assert has_remap_kwarg or returns_callable, (
                f"{owner} 既没传 `remap=` 也不产出可调用 ⇒ 方向语义可能被塞进改写器内部"
            )

        # 反面：改写器里不得出现删行侧的名字
        rewriter_src = textwrap.dedent(inspect.getsource(RS._rewrite_formula_refs))
        rewriter_tree = ast.parse(rewriter_src)
        forbidden = {"deleted_rows", "RowDeletionShift", "shift_range_end", "shift_range_start"}
        names = {
            node.id if isinstance(node, ast.Name) else node.attr
            for node in ast.walk(rewriter_tree)
            if isinstance(node, (ast.Name, ast.Attribute))
        }
        leaked = sorted(forbidden & names)
        assert not leaked, (
            f"`_rewrite_formula_refs` 里出现了删行侧的名字 {leaked} ⇒ "
            "被观测对象已被改动（Requirement 10.1）"
        )

    def test_template_set_matches_the_corpus_exactly(
        self, stored: dict[str, Any], current: dict[str, Any]
    ) -> None:
        """🔴 基线的模板**集合**与语料逐项一致（不是只比数量）。

        D4 重复文件删除之后两侧应完全对齐。集合层面对齐是「per_template 只是值变了」
        与「有模板被删/改名而基线没跟上」这两类的分界 —— 后者用数量比对看不出来
        （一删一增时总数不变，本次 D4 就正是如此：351 → 351）。

        🔴 字段路径是 **`per_template`**。首版我按名字猜成了 `templates`，
        于是两个集合都读成空、差集恒空 ⇒ 判据恒绿而当时基线真的有 17 处差异
        （工作区铁律：slice/结构字段路径必须现算验证，不可凭字段名推）。
        """
        assert "per_template" in stored and "per_template" in current, (
            f"基线结构变了，顶层键实测：{sorted(stored)}"
        )
        s_names, c_names = set(stored["per_template"]), set(current["per_template"])
        assert s_names, "基线的 per_template 是空的 ⇒ 判据空转"
        appeared = sorted(c_names - s_names)
        vanished = sorted(s_names - c_names)
        assert not appeared and not vanished, (
            f"基线与语料的模板集合不一致 —— 语料新增 {appeared} / 基线独有 {vanished}。\n"
            "模板被删或改名时，基线必须跟着改（改名 = 换键 + 记录换成现算值 + 分母"
            "按 per_template 重算），而不是整册 `--apply` 把别 lane 的漂移一并吸收。"
        )

    def test_the_watchdog_would_notice_a_changed_symbol(self) -> None:
        """🔴 变异反证（扫描器层）：sha 口径对**任何**源码改动敏感。

        没有这条，`_source_sha` 若因为某种原因恒返回同一个值（例如把 `getsource`
        换成了 `getdoc`），上面那些断言就全是恒真的。
        """

        def _probe_a() -> int:
            return 1

        def _probe_b() -> int:
            return 1 + 0  # 语义相同、文本不同

        assert _source_sha(_probe_a) != _source_sha(_probe_b), (
            "两个文本不同的函数算出同一个 sha ⇒ `_source_sha` 失效，看门狗恒真"
        )
        assert _source_sha(RS._rewrite_formula_refs) == _source_sha(
            RS._rewrite_formula_refs
        ), "同一个对象两次算出不同 sha ⇒ 口径不稳定，看门狗会变成永红门禁"
