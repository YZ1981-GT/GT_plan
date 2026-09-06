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

#: design.md「分母断言」表的 Wave 0 复算值。改这里必须同时改 design.md，两侧锁死。
EXPECTED_DENOMINATORS: dict[str, int] = {
    "xlsx_total": 351,
    "templates_with_cross_sheet": 182,
    "cross_sheet_sites": 144154,
    "cross_sheet_formulas": 72825,
    "three_d_sites": 0,
    "external_sites": 2908,
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
    """🔴 `_rewrite_formula_refs` 的行为与冻结基线逐字相同。"""
    problems = G.diff_baseline(current, stored)
    assert not problems, (
        f"`_rewrite_formula_refs` 行为已偏离冻结基线（{len(problems)} 处差异）。\n"
        "若这是 Task 27（Requirement 10 修 fill-down）导致的**有意**变更：\n"
        "  1. 确认差异全部落在 `filldown` 情景且都是跨 sheet 相对引用；\n"
        "  2. `insert_ctx` / `insert_no_ctx` 不得变；\n"
        "  3. 再跑 --apply 重新冻结并在 commit 里写明理由。\n"
        "否则这是真回归。\n差异（前 20）：\n  " + "\n  ".join(problems[:20])
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
