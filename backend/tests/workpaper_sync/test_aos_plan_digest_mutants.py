"""Property 4 / Property 6 的**变异反证**（`test_aos_plan_selfconsistency_and_digest.py` 伴生件）。

spec: workpaper-sync-adopt-overwrite-and-refresh-source（Task 3.2 + Task 3.3）
Requirements 1.7 / 3.3 · design § Correctness Properties

本文件只承三件事：**九组变异反证**（M1~M9，§5）· **红数收口**（§6）· **「未污染生产模块」**（§7）。
四个判据（`_assert_property_4` / `_assert_property_6_order_free` /
`_assert_property_6_content_sensitive` / `_assert_no_concatenation_ambiguity`）与场景建造器
（`fixed_plan` / `_reordered_plan`）一律从主体文件 import，**不另造第二份** —— 那四个函数是
Property 4 / 6 的唯一实现，两边各写一份就在测不同的东西。

🔴 **import 必须用顶层模块名**（`from test_aos_plan_selfconsistency_and_digest import …`）：
该目录无 `__init__.py`，pytest 以 `prepend` 模式把它塞进 `sys.path`；写成 `tests.workpaper_sync.…`
会拿到**第二个**模块实例，`_P46_MUTANT_REDS` 就此分家 —— §6 的收口判据会读到空 dict、本文件的红
一次都不算数。主体文件交付时 `_expect_red_p46` 的调用点数现算为 **0**，正是那种「写了从未被读的
死累计器」形态（域内 Task 4.4 交付时踩过同一个坑，补 §6 才收口）。

═══ 九组各模拟哪一类真实实现错误（逐组理由见 §4b 的锚点注册表注释）═══

Property 4 面 ① ← **M1**（派生计数读了另一个清单）· 面 ② ← **M2**（不相交门整个摘掉）+
**M3**（那道门只查第一对）。Property 6 面 ①（顺序无关）有三个顺序维度，**M4** 清单元素序 /
**M5** deltas 排列 / **M6** Mapping 键序一人一维；面 ②（内容敏感）← **M7**（某个行清单不进
digest）+ **M8**（逐表行数不进 digest）。拼接歧义三边界 ← **M9**（元素 / 字段 / 表）。

═══ 变异手段：**进程内源码级**，生产文件一字不改 ═══

`inspect.getsource` 取生产对象源码 → 替换**唯一**锚点（`count(old) == 1`，锚点消失即当场打红）
→ 在生产模块 `globals` 的**副本**里 `exec`。域内先例 `test_aos_property_out_of_scope_mutants.py`
的 `_source_mutant` 与 `test_aos_property_ghost_gate.py`。
🔴 **禁 `monkeypatch.setattr` 装回生产模块**：本域有并发会话，即便自动还原，窗口期内也改了共用
模块的行为。
🔴 本轮比先例多一层：被变异的是**类**而不只是函数 ⇒ 两个类必须 exec 进**同一个** namespace，
见 :func:`_model_namespace`。这也是主体文件 `fixed_plan` 收 `delta_cls` / `plan_cls` 的原因。
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import random
import types
from itertools import combinations
from pathlib import Path
from typing import Any, Callable, Final

import pytest

from app.services.workpaper_sync import adopt_overwrite_plan as AOP
from app.services.workpaper_sync.adopt_overwrite_plan import (
    _DISJOINT_FIELDS,
    _ROW_LIST_FIELDS,
    ItemOverwriteDelta,
    OverwritePlanShapeError,
)

# 🔴 四个判据与计划建造器的**唯一**来源（禁抄第二份；顶层模块名形态见 docstring）。
from test_aos_plan_selfconsistency_and_digest import (  # noqa: E402
    ITEM_PREFIX,
    TABLES,
    _MUTANT_GROUPS,
    _P46_MUTANT_REDS,
    _assert_no_concatenation_ambiguity,
    _assert_property_4,
    _assert_property_6_content_sensitive,
    _assert_property_6_order_free,
    _expect_red_p46,
    _reordered_plan,
    fixed_plan,
)

#: 洗牌种子。固定值使「对照组 / 变异生效断言 / 打红」三步看到**同一个**孪生计划 ——
#: 否则三步各洗一次，红到底是变异造成的还是洗法不同造成的就说不清。
_SEED: Final[int] = 46046

# ── 参数化取值域：**全部现算自生产域**（§6 的收口判据拿生产域与本文件装饰器对账） ──────────────

#: M1 / M4 / M7 的取值域 —— 四个行清单字段。少参数化一个就有一个字段的缺陷永远看不见。
_LIST_FIELDS: Final[tuple[str, ...]] = tuple(_ROW_LIST_FIELDS)

#: M2 的取值域 —— 三个「两两不相交」对子（现算，不写死「(added, deleted)」那一对）。
_ALL_PAIRS: Final[tuple[tuple[str, str], ...]] = tuple(combinations(_DISJOINT_FIELDS, 2))

#: M3 的取值域 —— **第一对之外**的对子（第一对在 M3 下仍被拦，是 M3 的变异生效断言）。
_LATER_PAIRS: Final[tuple[tuple[str, str], ...]] = _ALL_PAIRS[1:]

#: M8 的取值域 —— `OverwritePlan` 的两个「存起来的计数」字段（现算自生产 dataclass）。
_MAPPING_FIELDS: Final[tuple[str, ...]] = tuple(
    f.name for f in dataclasses.fields(AOP.OverwritePlan) if f.name != "deltas"
)

#: 字段名 → `fixed_plan` 的 kwarg 名。🔴 配 §6 的「键集合 == 生产域」断言 ⇒ 生产域加字段时
#: 本表不跟着改就当场打红（而不是静默漏掉那个字段）。
_KWARG_OF: Final[dict[str, str]] = {
    "rows_added": "added",
    "rows_deleted": "deleted",
    "rows_updated": "updated",
    "rows_ghost_dropped": "ghost",
}

#: M1 的「读错清单」映射：每个字段读**下一个**字段（环形，现算自生产域顺序）。
_NEXT_FIELD: Final[dict[str, str]] = {
    name: _LIST_FIELDS[(index + 1) % len(_LIST_FIELDS)]
    for index, name in enumerate(_LIST_FIELDS)
}

# ═══════════════════════════════════════════════════════════════════════════
# 4. 变异机制 —— 类级源码变异 + 共享 namespace（🔴 生产文件一个字节都不改）
# ═══════════════════════════════════════════════════════════════════════════

#: 三个被变异的生产对象与它们在 namespace 里的名字（三者 exec 进同一 dict ⇒ 顺序无关）。
_TARGETS: Final[tuple[tuple[str, str], ...]] = (
    ("js", "_canonical_json"),
    ("delta", "ItemOverwriteDelta"),
    ("plan", "OverwritePlan"),
)


def _mutated_source(target: Any, anchors: tuple[tuple[str, str], ...]) -> str:
    """按若干**唯一**锚点替换源码。`anchors` 为空即原样返回（仍要 re-exec，见下）。

    🔴 `count(old) == 1` 不得放宽成「命中就行」：那会让 `str.replace` 静默变成空操作 —— 变异体
    等于生产实现、红一次都打不出，而测试**全绿**。锚点消失说明生产写法变了，反证须重建。
    """
    src = inspect.getsource(target)
    for old, new in anchors:
        hits = src.count(old)
        assert hits == 1, (
            f"变异锚点 {old!r} 在 {getattr(target, '__name__', target)} 源码里命中 {hits} 次"
            "（须恰 1）—— 生产写法已变，本节反证须按新写法重建"
        )
        src = src.replace(old, new)
    return src


def _model_namespace(
    *,
    delta: tuple[tuple[str, str], ...] = (),
    plan: tuple[tuple[str, str], ...] = (),
    js: tuple[tuple[str, str], ...] = (),
) -> dict[str, Any]:
    """在 `vars(adopt_overwrite_plan)` 的**副本**里重建三个模型对象，返回该 namespace。

    🔴 **三者必须进同一个 namespace**：`OverwritePlan.__post_init__` 用
    `isinstance(delta, ItemOverwriteDelta)` 挡裸 dict，而这个名字从它自己的 `__globals__` 取
    —— 只换 delta 不换 plan，生产 plan 会把变异 delta 判成「不是 ItemOverwriteDelta」而抛
    `OverwritePlanShapeError`（测的就变成构造器不是 digest）。`_canonical_json` 同理。
    🔴 **无变异时也 re-exec**（M6 只动 plan 与 json，delta 仍须同源）⇒ 代价是「未变异 re-exec
    与生产逐字符等价」这一前提，由 §7 的 `test_unmutated_reexec_…` 实测。
    """
    namespace = dict(vars(AOP))
    anchors_by_kind = {"delta": delta, "plan": plan, "js": js}
    for kind, name in _TARGETS:
        src = "from __future__ import annotations\n" + _mutated_source(
            getattr(AOP, name), anchors_by_kind[kind]
        )
        exec(  # noqa: S102 —— 变异体只在本进程内存在，不落盘、不回写生产模块
            compile(src, f"<aos-p46 mutant {name}>", "exec"), namespace
        )
    return namespace


def _model_pair(**kwargs: Any) -> tuple[Any, Any]:
    """`_model_namespace` 的薄包装：只要那两个类时用它。"""
    namespace = _model_namespace(**kwargs)
    return namespace["ItemOverwriteDelta"], namespace["OverwritePlan"]

# ── 4b. 九组锚点注册表（锚点唯一性由 §7 独立复核，与 `_mutated_source` 互为第二判据） ─────────

#: **M1**：`rows_X_count` 改读 `rows_<下一个>`。锚点用整条 `return len(self.X)` —— 光用
#: `len(self.rows_deleted)` 会撞上 `_validate_scope_and_skip` 里 f-string 那处（实测命中 2 次）。
_M1_ANCHORS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    name: ((f"return len(self.{name})", f"return len(self.{_NEXT_FIELD[name]})"),)
    for name in _LIST_FIELDS
}

#: M2 / M3 共用锚点 = 构造期那道不相交门的循环头。
_GATE_ANCHOR: Final[str] = "for left, right in combinations(_DISJOINT_FIELDS, 2):"
#: **M2**：门整个摘掉（循环体一次都不进）。
_M2_ANCHORS: Final[tuple[tuple[str, str], ...]] = ((_GATE_ANCHOR, "for left, right in ():"),)
#: **M3**：门**只查第一对** —— 模拟「判据写死 (added, deleted) 一对」那类实现。
_M3_ANCHORS: Final[tuple[tuple[str, str], ...]] = (
    (_GATE_ANCHOR, "for left, right in list(combinations(_DISJOINT_FIELDS, 2))[:1]:"),
)

#: **M4**：`canonical_form` 里某个清单不排序（`sorted` → `list`）⇒ 元素序进 digest。
_M4_ANCHORS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    name: ((f'"{name}": sorted(self.{name}),', f'"{name}": list(self.{name}),'),)
    for name in _LIST_FIELDS
}

#: **M5**：deltas 的排序**键**被中性化成常量。Python 的 sort 稳定 ⇒ 排序退化成恒等、deltas 的
#: 排列直接进 digest。🔴 刻意不摘 `sorted(` 本体：那会留下 `list(生成器, key=…)` 这种 TypeError，
#: 「红」就只是变异体语法炸了而不是判据抓到了东西。
_M5_ANCHORS: Final[tuple[tuple[str, str], ...]] = (
    ("key=_canonical_json", "key=lambda _form: 0"),
)

#: **M6**：键序有**两条**皮带 —— `canonical_form` 的 `dict(sorted(...))` 与 `_canonical_json` 的
#: `sort_keys=True`。只摘一条另一条兜住 ⇒ 红不了（§5 的 M6 用例实测），故必须两条同时摘。
_M6_PLAN_ANCHORS: Final[tuple[tuple[str, str], ...]] = tuple(
    (f'"{name}": dict(sorted(self.{name}.items())),', f'"{name}": dict(self.{name}),')
    for name in _MAPPING_FIELDS
)
_JSON_DUMPS: Final[str] = "return json.dumps(obj, sort_keys=%s, ensure_ascii=False, separators=%s)"
_M6_JSON_ANCHORS: Final[tuple[tuple[str, str], ...]] = (
    (_JSON_DUMPS % ("True", '(",", ":")'), _JSON_DUMPS % ("False", '(",", ":")')),
)

#: **M7**：某个行清单整条从 `canonical_form` 里摘掉（替换成空串 ⇒ dict 字面量里留一行空白，
#: 语法合法）。后果：改那个清单的任何身份 / 长度都不再影响 digest。
_M7_ANCHORS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    name: ((f'"{name}": sorted(self.{name}),', ""),) for name in _LIST_FIELDS
}

#: **M8**：某个逐表行数 Mapping 整条从 `canonical_form` 里摘掉。
_M8_ANCHORS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    name: ((f'"{name}": dict(sorted(self.{name}.items())),', ""),) for name in _MAPPING_FIELDS
}

#: **M9**：三种边界各一个**互相隔离**的变异 —— 每个只踩穿 `_assert_no_concatenation_ambiguity`
#: 的其中一条断言、另两条仍绿。隔离是刻意的：三条断言写在同一个判据里，若变异同时踩穿多条，
#: 红只能证明「那个判据能为 False」，证不出**每一条**都有牙。
#:   · elements = 同一清单内被拼成一串 ⇒ `['a','bc']` 与 `['ab','c']` 都变成 `'abc'`
#:   · fields   = 追加与删除两清单并成一个（元素边界仍在 ⇒ 第一条断言照样绿）
#:   · tables   = 逐表行数换成它的**派生总数** ⇒ 分布不同而总和相同的两份计划撞 digest
_A_ADD: Final[str] = '"rows_added": sorted(self.rows_added),'
_M9_ANCHORS: Final[dict[str, dict[str, tuple[tuple[str, str], ...]]]] = {
    "elements": {"delta": ((_A_ADD, '"rows_added": "".join(sorted(self.rows_added)),'),)},
    "fields": {
        "delta": (
            (
                _A_ADD,
                '"rows_added_or_deleted": sorted(list(self.rows_added) + list(self.rows_deleted)),',
            ),
            ('"rows_deleted": sorted(self.rows_deleted),', ""),
        )
    },
    "tables": {
        "plan": ((
            '"store_rows_by_table": dict(sorted(self.store_rows_by_table.items())),',
            '"store_row_total": sum(self.store_rows_by_table.values()),',
        ),)
    },
}

#: M9 的参数化取值域 —— **由锚点注册表派生**：加一种边界变异，参数化自动跟上。
_M9_BOUNDARIES: Final[tuple[str, ...]] = tuple(_M9_ANCHORS)

#: 各边界被踩穿后，`_assert_no_concatenation_ambiguity` 报出的**专属**文案片段。
#: 红了要核这个 —— 否则「红」可能来自另一条断言，隔离性就没证到。
_M9_RED_MARK: Final[dict[str, str]] = {
    "elements": "清单被拼成一串",
    "fields": "字段边界被抹平了",
    "tables": "摘要只吃了派生总数",
}

# ── 4c. 场景 kwargs（喂给主体文件的 `fixed_plan`，本文件不另造建造器） ─────────────────────────


def _m1_kwargs() -> dict[str, tuple[str, ...]]:
    """M1 专用：四个清单长度**两两不同**（M1 能不能打红的要害）。

    `fixed_plan` 默认四个清单**长度都是 2** ⇒「读错清单」算出的计数仍然是 2、面 ① 照样通过、
    变异完全隐形。故按 `len(_LIST_FIELDS) - index` 造递减长度（现算）并当场断言两两不同。
    """
    total = len(_LIST_FIELDS)
    sizes = {name: total - index for index, name in enumerate(_LIST_FIELDS)}
    assert len(set(sizes.values())) == total, f"长度未两两不同：{sizes} —— M1 会隐形"
    out = {
        _KWARG_OF[name]: tuple(f"m1-{name}-{n}" for n in range(size))
        for name, size in sizes.items()
    }
    # ghost ⊆ added（Property 3 的连带约束）：本文件不测它，但也不制造反例。
    out["ghost"] = out[_KWARG_OF["rows_added"]][: sizes["rows_ghost_dropped"]]
    return out


def _overlap_kwargs(pair: tuple[str, str]) -> dict[str, tuple[str, ...]]:
    """M2 / M3 专用：让 `pair` 两个清单**相交于一个身份**，第三个清单保持不相交。"""
    left, right = pair
    third = next(name for name in _DISJOINT_FIELDS if name not in pair)
    return {
        _KWARG_OF[left]: ("aos46-ov", "aos46-l"),
        _KWARG_OF[right]: ("aos46-ov", "aos46-r"),
        _KWARG_OF[third]: ("aos46-t",), "ghost": (),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5a. Property 4 的变异反证（M1~M3）
# ═══════════════════════════════════════════════════════════════════════════


class TestPropertyFourJudgeCanBeFalse:
    """`_assert_property_4` 的两个面各配变异：面 ① 由 M1 承，面 ② 由 M2 + M3 承。

    🔴 面 ② 的两组不可省其一：M2 证明「门摘了会被抓到」，M3 证明**判据自己**查满三对 —— 若判据
    写死第一对，M2 仍会红（第一对相交也被造出来了）而 M3 的后两对会全绿。
    """

    @pytest.mark.parametrize("field_name", _LIST_FIELDS)
    def test_m1_count_from_wrong_list_is_caught(self, field_name: str) -> None:
        """M1（面 ①）：`rows_X_count` 读了 `rows_<下一个>` 的长度。"""
        kwargs = _m1_kwargs()
        # 对照组：生产实现下判据必绿（否则下面的红不是变异造成的）。
        _assert_property_4(fixed_plan(**kwargs), label=f"M1/{field_name} 对照组")

        delta_cls, plan_cls = _model_pair(delta=_M1_ANCHORS[field_name])
        mutant = fixed_plan(delta_cls=delta_cls, plan_cls=plan_cls, **kwargs)
        rich, wrong = mutant.deltas[0], _NEXT_FIELD[field_name]
        got, bad_len, own_len = (
            getattr(rich, f"{field_name}_count"),
            len(getattr(rich, wrong)),
            len(getattr(rich, field_name)),
        )
        # 变异生效断言：派生计数确实换成了另一个清单的长度，且两者真的不等。
        assert got == bad_len != own_len, (
            f"M1/{field_name}：变异没生效 —— count={got}、len({wrong})={bad_len}、own={own_len}"
        )
        error = _expect_red_p46(
            "M1_count_from_wrong_list",
            lambda: _assert_property_4(mutant, label=f"M1/{field_name}"),
        )
        assert f"{field_name}_count" in str(error), str(error)

    @pytest.mark.parametrize("pair", _ALL_PAIRS)
    def test_m2_disjoint_gate_removed_is_caught(self, pair: tuple[str, str]) -> None:
        """M2（面 ②）：门整个摘掉 ⇒ 相交的计划**造得出来**，正向判据必须当场打红。"""
        kwargs = _overlap_kwargs(pair)
        # 对照组 = 主体文件 `TestDisjointGateIsLive` 那条的另一半：生产构造器当场抛。
        with pytest.raises(OverwritePlanShapeError):
            fixed_plan(**kwargs)

        delta_cls, plan_cls = _model_pair(delta=_M2_ANCHORS)
        mutant = fixed_plan(delta_cls=delta_cls, plan_cls=plan_cls, **kwargs)
        left, right = pair
        rich = mutant.deltas[0]
        # 变异生效断言：门真的没拦住，且相交身份恰是构造时塞进去的那一个。
        overlap = set(getattr(rich, left)) & set(getattr(rich, right))
        assert overlap == {"aos46-ov"}, f"M2/{left}~{right}：变异没生效 —— 实得 {sorted(overlap)}"
        error = _expect_red_p46(
            "M2_disjoint_gate_removed",
            lambda: _assert_property_4(mutant, label=f"M2/{left}~{right}"),
        )
        assert left in str(error) and right in str(error) and "aos46-ov" in str(error), str(error)

    @pytest.mark.parametrize("pair", _LATER_PAIRS)
    def test_m3_only_first_pair_checked_is_caught(self, pair: tuple[str, str]) -> None:
        """M3（面 ②）：门只查第一对 ⇒ 判据必须替它抓住**后两对**。"""
        delta_cls, plan_cls = _model_pair(delta=_M3_ANCHORS)
        # 变异生效断言：第一对**仍然**被构造器拦下 ⇒ 这是「只查第一对」不是「门全没了」。
        with pytest.raises(OverwritePlanShapeError):
            fixed_plan(delta_cls=delta_cls, plan_cls=plan_cls, **_overlap_kwargs(_ALL_PAIRS[0]))

        left, right = pair
        base = fixed_plan(delta_cls=delta_cls, plan_cls=plan_cls)
        _assert_property_4(base, label=f"M3/{left}~{right} 对照组")
        mutant = fixed_plan(delta_cls=delta_cls, plan_cls=plan_cls, **_overlap_kwargs(pair))
        error = _expect_red_p46(
            "M3_only_first_pair_checked",
            lambda: _assert_property_4(mutant, label=f"M3/{left}~{right}"),
        )
        assert left in str(error) and right in str(error), str(error)

# ═══════════════════════════════════════════════════════════════════════════
# 5b. Property 6 的变异反证（M4~M8）与拼接歧义（M9）
# ═══════════════════════════════════════════════════════════════════════════


def _rng() -> random.Random:
    """每次取一条**同种子**的新随机流 ⇒ 对照组 / 生效断言 / 打红三步看到同一个孪生计划。"""
    return random.Random(_SEED)


def _m9_form(delta_cls: Any, **rows: Any) -> dict[str, Any]:
    return delta_cls(item_id=f"{ITEM_PREFIX}-m9", table_key=TABLES[0], **rows).canonical_form()


def _m9_effect_elements(delta_cls: Any, _plan_cls: Any) -> None:
    """元素边界：两种切分方式被拼成同一串。"""
    first = _m9_form(delta_cls, rows_added=("a", "bc"))["rows_added"]
    second = _m9_form(delta_cls, rows_added=("ab", "c"))["rows_added"]
    assert first == second == "abc", f"变异没生效 —— 实得 {first!r} / {second!r}"


def _m9_effect_fields(delta_cls: Any, _plan_cls: Any) -> None:
    """字段边界：追加与删除并成一个清单，而**元素边界仍在**（隔离性的正面判据）。"""
    merged = "rows_added_or_deleted"
    left = _m9_form(delta_cls, rows_added=("a", "b"), rows_deleted=("c", "d"))
    right = _m9_form(delta_cls, rows_added=("c", "d"), rows_deleted=("a", "b"))
    assert "rows_deleted" not in left and merged in left, sorted(left)
    assert left[merged] == right[merged] == ["a", "b", "c", "d"], (left[merged], right[merged])
    assert (
        _m9_form(delta_cls, rows_added=("a", "bc"))[merged]
        != _m9_form(delta_cls, rows_added=("ab", "c"))[merged]
    ), "元素边界也被踩穿了 ⇒ 本组不再隔离，红会来自第一条断言"


def _m9_effect_tables(delta_cls: Any, plan_cls: Any) -> None:
    """表边界：逐表行数被换成派生总数。"""
    form = fixed_plan(
        delta_cls=delta_cls, plan_cls=plan_cls, store={TABLES[0]: 1, TABLES[1]: 22}
    ).canonical_form()
    assert "store_rows_by_table" not in form, sorted(form)
    assert form["store_row_total"] == 23, form["store_row_total"]


#: 每种边界的「变异生效」判据。🔴 少一条 ⇒ §6 的完整性断言打红（不许悄悄加边界不加判据）。
_M9_EFFECT: Final[dict[str, Callable[[Any, Any], None]]] = {
    "elements": _m9_effect_elements, "fields": _m9_effect_fields, "tables": _m9_effect_tables,
}


class TestPropertySixJudgeCanBeFalse:
    """`_assert_property_6_*` 与 `_assert_no_concatenation_ambiguity` 的变异反证。

    面 ①（顺序无关）有**三个**顺序维度，M4 / M5 / M6 一人一维 —— 只做一维会让另两维的
    「顺序泄漏进 digest」永远不可见。面 ② 由 M7（行清单）+ M8（存起来的计数）承。
    """

    @pytest.mark.parametrize("field_name", _LIST_FIELDS)
    def test_m4_list_sort_removed_is_caught(self, field_name: str) -> None:
        """M4（面 ①/清单维）：某个清单不排序 ⇒ 元素序泄漏进 digest。"""
        _assert_property_6_order_free(fixed_plan(), rng=_rng(), label=f"M4/{field_name} 对照组")

        delta_cls, plan_cls = _model_pair(delta=_M4_ANCHORS[field_name])
        mutant = fixed_plan(delta_cls=delta_cls, plan_cls=plan_cls)
        twin, changed = _reordered_plan(mutant, rng=_rng())
        assert any(
            item.startswith("lists:") and item.endswith(f".{field_name}") for item in changed
        ), f"M4/{field_name}：该清单这一轮没真的换序（changed={list(changed)}）⇒ 变异必然隐形"
        assert twin.digest != mutant.digest, f"M4/{field_name}：变异没生效 —— 换序 digest 竟没变"
        _expect_red_p46(
            "M4_list_sort_removed",
            lambda: _assert_property_6_order_free(mutant, rng=_rng(), label=f"M4/{field_name}"),
        )

    def test_m5_delta_sort_neutralised_is_caught(self) -> None:
        """M5（面 ①/deltas 维）：排序键换成常量 ⇒ 稳定排序退化成恒等，delta 排列进 digest。"""
        _assert_property_6_order_free(fixed_plan(), rng=_rng(), label="M5 对照组")

        delta_cls, plan_cls = _model_pair(plan=_M5_ANCHORS)
        mutant = fixed_plan(delta_cls=delta_cls, plan_cls=plan_cls)
        twin, changed = _reordered_plan(mutant, rng=_rng())
        assert "deltas" in changed, f"deltas 这一轮没真的重排（changed={list(changed)}）"
        forms = (twin.canonical_form()["deltas"], mutant.canonical_form()["deltas"])
        assert forms[0] != forms[1], "M5：变异没生效 —— deltas 仍被排回同一个序"
        _expect_red_p46(
            "M5_delta_sort_neutralised",
            lambda: _assert_property_6_order_free(mutant, rng=_rng(), label="M5"),
        )

    def test_m6_key_order_belts_removed_is_caught(self) -> None:
        """M6（面 ①/Mapping 键序维）：**两条**皮带同时摘掉。

        🔴 先实测「只摘一条仍绿」—— 那不是判据没牙，而是键序本来就有两道保护。不先证这一条，
        本组会被读成「摘一条就该红」而误判判据失效。
        """
        _assert_property_6_order_free(fixed_plan(), rng=_rng(), label="M6 对照组")
        one_delta, one_plan = _model_pair(plan=_M6_PLAN_ANCHORS)
        _assert_property_6_order_free(
            fixed_plan(delta_cls=one_delta, plan_cls=one_plan), rng=_rng(), label="M6 只摘一条皮带"
        )

        ns = _model_namespace(plan=_M6_PLAN_ANCHORS, js=_M6_JSON_ANCHORS)
        assert ns["_canonical_json"]({"b": 1, "a": 2}) == '{"b":1,"a":2}', "M6：键仍被排序"
        mutant = fixed_plan(delta_cls=ns["ItemOverwriteDelta"], plan_cls=ns["OverwritePlan"])
        twin, changed = _reordered_plan(mutant, rng=_rng())
        assert any(item.startswith("mapping_keys:") for item in changed), list(changed)
        assert twin.digest != mutant.digest, "M6：两条皮带都摘了，换键序 digest 竟没变"
        _expect_red_p46(
            "M6_key_order_belts_removed",
            lambda: _assert_property_6_order_free(mutant, rng=_rng(), label="M6"),
        )

    @pytest.mark.parametrize("field_name", _LIST_FIELDS)
    def test_m7_field_omitted_from_digest_is_caught(self, field_name: str) -> None:
        """M7（面 ②）：某个行清单根本不进 digest ⇒ 改它的身份 / 长度摘要都无感。"""
        _assert_property_6_content_sensitive(fixed_plan(), label=f"M7/{field_name} 对照组")

        delta_cls, plan_cls = _model_pair(delta=_M7_ANCHORS[field_name])
        mutant = fixed_plan(delta_cls=delta_cls, plan_cls=plan_cls)
        got = set(mutant.deltas[0].canonical_form())
        ref = ItemOverwriteDelta(item_id=f"{ITEM_PREFIX}-ref", table_key=TABLES[0])
        assert got == set(ref.canonical_form()) - {field_name}, f"M7：实得 {sorted(got)}"
        _expect_red_p46(
            "M7_field_omitted_from_digest",
            lambda: _assert_property_6_content_sensitive(mutant, label=f"M7/{field_name}"),
        )

    @pytest.mark.parametrize("field_name", _MAPPING_FIELDS)
    def test_m8_stored_counts_omitted_is_caught(self, field_name: str) -> None:
        """M8（面 ②）：逐表行数不进 digest ⇒ 「存起来的那个计数」变了摘要不变。"""
        _assert_property_6_content_sensitive(fixed_plan(), label=f"M8/{field_name} 对照组")

        delta_cls, plan_cls = _model_pair(plan=_M8_ANCHORS[field_name])
        mutant = fixed_plan(delta_cls=delta_cls, plan_cls=plan_cls)
        got = set(mutant.canonical_form())
        assert got == set(fixed_plan().canonical_form()) - {field_name}, f"M8：实得 {sorted(got)}"
        _expect_red_p46(
            "M8_stored_counts_omitted",
            lambda: _assert_property_6_content_sensitive(mutant, label=f"M8/{field_name}"),
        )

    @pytest.mark.parametrize("boundary", _M9_BOUNDARIES)
    def test_m9_structure_flattened_is_caught(self, boundary: str) -> None:
        """M9：结构被拍平成一个值。三种边界**互相隔离**，各自只踩穿判据里的一条断言。"""
        anchors = _M9_ANCHORS[boundary]
        _assert_no_concatenation_ambiguity(label=f"M9/{boundary} 对照组")

        delta_cls, plan_cls = _model_pair(
            delta=anchors.get("delta", ()), plan=anchors.get("plan", ())
        )
        _M9_EFFECT[boundary](delta_cls, plan_cls)
        error = _expect_red_p46(
            "M9_list_joined_without_separator",
            lambda: _assert_no_concatenation_ambiguity(
                delta_cls=delta_cls, plan_cls=plan_cls, label=f"M9/{boundary}"
            ),
        )
        # 🔴 核专属文案：证明红来自**本边界**那条断言，而不是顺带踩穿了另一条。
        assert _M9_RED_MARK[boundary] in str(error), str(error)

# ═══════════════════════════════════════════════════════════════════════════
# 6. 收口 —— `_P46_MUTANT_REDS` 必须被**读**
# ═══════════════════════════════════════════════════════════════════════════
# 🔴 主体文件只声明了 `_P46_MUTANT_REDS` 与 `_expect_red_p46`，§5 只往里**写**。没有读它的判据
#    时那是个「写了从未被读」的死累计器 —— 九组里任意一组悄悄不再打红（`_expect_red_p46` 被换成
#    直接调用、某组判据退化而 `pytest.raises` 不再触发、参数化被改窄成一个取值……）都不会有人
#    发现。这正是域内 Task 4.4 交付时踩过的坑。


def _red_sites_by_group() -> dict[str, int]:
    """现算各组在本文件里的 `_expect_red_p46(...)` **调用点数**（AST，禁文本匹配）。

    🔴 用它而不是写死「M1 该红 4 次」：红点数是**结构**事实。加 / 删一个红点期望值随之变化，
    收口判据不会因为「常量没跟着改」而误报或漏报。
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    sites: dict[str, int] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_expect_red_p46"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            sites[node.args[0].value] = sites.get(node.args[0].value, 0) + 1
    return sites


def _parametrize_counts() -> tuple[dict[str, int], list[str]]:
    """现算各测试方法 `@pytest.mark.parametrize` 的**取值个数**（AST）。

    返回 `(方法名 → 取值数, 解析不了的装饰器)`。本文件装饰器一律把取值域写成模块级名字
    ⇒ 按 `ast.Name` → `len(globals()[id])` 解析，顺带支持裸 tuple。🔴 第二个返回值必须为空：
    解析不了就等于这条判据看不见那个装饰器，而「看不见」会被静默按「无参数化 ⇒ 1」处理。
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    unresolved: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if not (
                isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Attribute)
                and deco.func.attr == "parametrize"
                and len(deco.args) > 1
            ):
                continue  # 非 parametrize 装饰器（本文件没有，留着让形态变化时不误报）
            values = deco.args[1]
            if isinstance(values, ast.Name) and isinstance(globals().get(values.id), tuple):
                counts[node.name] = len(globals()[values.id])
            elif isinstance(values, ast.Tuple):
                counts[node.name] = len(values.elts)
            else:
                unresolved.append(f"{node.name}: {ast.dump(values)[:80]}")
    return counts, unresolved


def _group_plan() -> tuple[tuple[str, Callable[..., None], tuple[Any, ...] | None, int], ...]:
    """九组的 `(组名, 测试方法, 参数取值域或 None, 生产域现算期望数)`。

    第 3 位来自**本文件的取值域常量**、第 4 位来自**生产域**（`_ROW_LIST_FIELDS` /
    `_DISJOINT_FIELDS` 的对子数 / `OverwritePlan` 的 dataclass 字段），两者刻意分开取：🔴 把装饰器
    改窄成 `("rows_added",)` 时 AST 侧与第 3 位得 1、第 4 位仍得 4 ⇒ 打红。组名顺序对齐主体文件。
    """
    four, six = TestPropertyFourJudgeCanBeFalse(), TestPropertySixJudgeCanBeFalse()
    pairs = len(tuple(combinations(AOP._DISJOINT_FIELDS, 2)))
    fields = len(AOP._ROW_LIST_FIELDS)
    maps = len([f for f in dataclasses.fields(AOP.OverwritePlan) if f.name != "deltas"])
    return (
        ("M1_count_from_wrong_list", four.test_m1_count_from_wrong_list_is_caught, _LIST_FIELDS, fields),
        ("M2_disjoint_gate_removed", four.test_m2_disjoint_gate_removed_is_caught, _ALL_PAIRS, pairs),
        ("M3_only_first_pair_checked", four.test_m3_only_first_pair_checked_is_caught, _LATER_PAIRS, pairs - 1),
        ("M4_list_sort_removed", six.test_m4_list_sort_removed_is_caught, _LIST_FIELDS, fields),
        # M5 / M6 无参数化 ⇒ 期望 1，并由 AST 侧「`params` 不含该方法」独立兑现。
        ("M5_delta_sort_neutralised", six.test_m5_delta_sort_neutralised_is_caught, None, 1),
        ("M6_key_order_belts_removed", six.test_m6_key_order_belts_removed_is_caught, None, 1),
        ("M7_field_omitted_from_digest", six.test_m7_field_omitted_from_digest_is_caught, _LIST_FIELDS, fields),
        ("M8_stored_counts_omitted", six.test_m8_stored_counts_omitted_is_caught, _MAPPING_FIELDS, maps),
        ("M9_list_joined_without_separator", six.test_m9_structure_flattened_is_caught, _M9_BOUNDARIES, len(_M9_ANCHORS)),
    )


class TestMutantRedsAreClosed:
    """九组变异反证的红数收口：逐组红数 = 红点数 × 参数取值数（**两侧全现算**）。"""

    def test_parametrisation_tracks_the_production_domains(self) -> None:
        """AST 侧的参数化取值数 == 生产域现算值；无参数化的两组须**确实**没有装饰器。"""
        params, unresolved = _parametrize_counts()
        assert not unresolved, f"有 parametrize 装饰器解析不了 ⇒ 本判据看不见它：{unresolved}"
        plan = _group_plan()
        assert {name for name, _m, _v, _s in plan} == set(_MUTANT_GROUPS)
        for name, method, values, size in plan:
            if values is None:
                assert method.__name__ not in params and size == 1, (
                    f"{name} 登记为「无参数化」却带了 parametrize 装饰器（或期望数 {size} != 1）"
                )
                continue
            assert params.get(method.__name__) == size == len(values), (
                f"{method.__name__} 按 {params.get(method.__name__)} 参数化、生产域现算 {size}、"
                f"取值域长度 {len(values)} —— 三者须一致；参数化一窄就有一个字段 / 对子 / 边界"
                "从未被这组变异走过"
            )
        # 🔴 `_KWARG_OF` 须覆盖生产域全部字段，否则 `_m1_kwargs` / `_overlap_kwargs` 抛 KeyError
        #    ——那是个坏的失败形态（读起来像笔误），此处显式点名。
        assert set(_KWARG_OF) == set(AOP._ROW_LIST_FIELDS), sorted(_KWARG_OF)
        assert _M9_BOUNDARIES == tuple(_M9_ANCHORS) and set(_M9_EFFECT) == set(_M9_ANCHORS), (
            "M9 的锚点表 / 取值域 / 生效判据表三者不一致 —— 加了边界却没配生效判据"
        )

    def test_every_group_reds_on_every_variant(self) -> None:
        """自跑一轮九组，逐组核对**增量**红数；再核对累计 key 集合 == 登记组名。

        🔴 自跑而不是依赖「§5 已经跑过」：`-k` 定向选择下 §5 可能一条都没执行，那时读累计器
        会得到空 dict 而判据仍「通过」—— 那正是要防的空转。
        """
        plan = _group_plan()
        assert [name for name, _m, _v, _s in plan] == list(_MUTANT_GROUPS), (
            f"本判据自跑的组 {[n for n, _m, _v, _s in plan]} != 登记的 {list(_MUTANT_GROUPS)} —— "
            "新增变异组必须同时接进收口判据，否则它可以永远不打红"
        )
        sites = _red_sites_by_group()
        assert set(sites) == set(_MUTANT_GROUPS), (
            f"`_expect_red_p46` 调用点覆盖 {sorted(sites)}、登记的是 {list(_MUTANT_GROUPS)} —— "
            "某组登记了却一个红点都没写（或写了未登记的组名）"
        )
        before = dict(_P46_MUTANT_REDS)
        for _name, method, values, _size in plan:
            for value in (None,) if values is None else values:
                method() if values is None else method(value)
        gained = {
            name: _P46_MUTANT_REDS.get(name, 0) - before.get(name, 0) for name, _m, _v, _s in plan
        }
        expected = {name: sites[name] * size for name, _m, _v, size in plan}
        assert gained == expected, (
            f"本判据自跑一轮实得红数 {gained}，按「红点数 × 参数取值数」应为 {expected} —— "
            "某一组没打满（= 那类实现错误对本轮两条 property 至少在一个取值上不可见）"
        )
        assert set(_P46_MUTANT_REDS) == set(_MUTANT_GROUPS), (
            f"变异组累计 {sorted(_P46_MUTANT_REDS)} != 登记的 {list(_MUTANT_GROUPS)}"
        )
        # 🔴 反空转：九组红点若被全部删空，`expected` 也会变成全零而 `gained == expected` 恒等。
        assert all(value > 0 for value in expected.values()), (
            f"某组的期望红数为 0（{expected}）—— 那组的 `_expect_red_p46` 调用点被删空了，"
            "「判据能为 False」在它上面已无证明"
        )
        # 🔴 累计器真被读到了非空值（主体文件那份 dict 与本文件是**同一个对象**的直证）。
        assert _P46_MUTANT_REDS and all(value > 0 for value in _P46_MUTANT_REDS.values())

    def test_accumulator_is_the_very_same_object_as_the_main_module(self) -> None:
        """🔴 顶层模块名 import 的直证：两侧拿到的是**同一个** dict，红数不分家。写成
        `tests.workpaper_sync.…` 会得到第二个模块实例 —— 那时本判据的 `is` 当场打红，而不是等到
        「收口判据读到空 dict 却仍然通过」才在下游暴露。
        """
        import test_aos_plan_selfconsistency_and_digest as main_module

        assert main_module._P46_MUTANT_REDS is _P46_MUTANT_REDS
        assert main_module._MUTANT_GROUPS is _MUTANT_GROUPS
        assert len(_MUTANT_GROUPS) == len(set(_MUTANT_GROUPS)) == 9

# ═══════════════════════════════════════════════════════════════════════════
# 7. 生产模块未被污染 + 锚点仍然唯一
# ═══════════════════════════════════════════════════════════════════════════


def _globals_of(obj: Any) -> dict[str, Any]:
    """取对象的 `__globals__`。类本身没有这个属性 ⇒ 借它自己的 `canonical_form` 函数。"""
    if isinstance(obj, type):
        return vars(obj)["canonical_form"].__globals__
    return obj.__globals__


def _all_anchor_sets() -> tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...]:
    """全部九组的锚点集合，展开成 `(标签, 生产对象名, 锚点)`。"""
    out: list[tuple[str, str, tuple[tuple[str, str], ...]]] = [
        ("M2", "ItemOverwriteDelta", _M2_ANCHORS),
        ("M3", "ItemOverwriteDelta", _M3_ANCHORS),
        ("M5", "OverwritePlan", _M5_ANCHORS),
        ("M6/plan", "OverwritePlan", _M6_PLAN_ANCHORS),
        ("M6/json", "_canonical_json", _M6_JSON_ANCHORS),
    ]
    for group, table in (("M1", _M1_ANCHORS), ("M4", _M4_ANCHORS), ("M7", _M7_ANCHORS)):
        out += [(f"{group}/{key}", "ItemOverwriteDelta", value) for key, value in table.items()]
    out += [(f"M8/{key}", "OverwritePlan", value) for key, value in _M8_ANCHORS.items()]
    for boundary, spec in _M9_ANCHORS.items():
        for kind, name in (("delta", "ItemOverwriteDelta"), ("plan", "OverwritePlan")):
            out += [(f"M9/{boundary}", name, spec[kind])] if spec.get(kind) else []
    return tuple(out)


class TestProductionModelsAreNotPolluted:
    """🔴 变异体只在本进程内存在：不回写生产模块、不与生产模块共享 globals。本域有并发会话，
    `monkeypatch.setattr` 即便自动还原窗口期内也改了共用模块的行为 ⇒ §5 一律走「副本 + exec」。
    """

    def test_mutants_are_distinct_objects_and_do_not_alias_production_globals(self) -> None:
        namespace = _model_namespace()
        assert namespace is not vars(AOP), "namespace 就是生产模块的 __dict__ ⇒ exec 已写进生产模块"
        for _kind, name in _TARGETS:
            original, mutant = getattr(AOP, name), namespace[name]
            assert mutant is not original, f"{name}：变异体与生产对象是同一个"
            assert _globals_of(mutant) is namespace, f"{name}：变异体没落在本次 namespace 里"
            assert _globals_of(mutant) is not vars(AOP), f"{name}：变异体与生产模块**共享** globals"
            probe = f"_aos_p46_pollution_probe_{name}"
            _globals_of(mutant)[probe] = object()
            assert probe not in vars(AOP), f"{name}：往变异体 globals 写入后生产模块也长出了 {probe}"
            assert getattr(AOP, name) is original, f"{name}：生产模块的该名字已被换掉 ⇒ 变异体被回写"

    def test_the_no_copy_variant_would_really_pollute(self) -> None:
        """变异对照：同一 `exec` 若写进 `vars(module)` **本身**（不取副本），模块确实会被改。
        🔴 没有这条，上一条可能只是在证明「`exec` 本来就不写模块」。用一个丢弃用的
        :class:`types.ModuleType` 承接污染 —— 生产模块一个字节都不碰。
        """
        dummy = types.ModuleType("aos_p46_dummy_module")
        dummy.__dict__.update(vars(AOP))
        original = AOP.ItemOverwriteDelta
        assert vars(dummy)["ItemOverwriteDelta"] is original
        source = "from __future__ import annotations\n" + inspect.getsource(original)
        exec(  # noqa: S102 —— 只写进 dummy 模块，用于证明判据有区分力
            compile(source, "<aos-p46 leak probe>", "exec"), vars(dummy)
        )
        assert vars(dummy)["ItemOverwriteDelta"] is not original, (
            "写进 `vars(module)` 本身竟没换掉模块里的那个名字 —— 上一条判据无区分力，须重建"
        )
        assert AOP.ItemOverwriteDelta is original and vars(dummy) is not vars(AOP)

    def test_production_sources_still_carry_every_anchor(self) -> None:
        """九组全部锚点在生产源码里仍**恰 1** 次命中（与 `_mutated_source` 互为第二判据）。
        锚点消失说明生产写法变了 ⇒ 反证须按新写法重建。🔴 不得放宽成「命中就行」：那会让
        `str.replace` 静默变成空操作 —— 变异体等于生产实现、红一次都打不出还全绿。
        """
        anchor_sets = _all_anchor_sets()
        # 覆盖面两条（全现算）：九组一个不缺 + 锚点串集合恰等于按生产域拼出来的那一套。
        groups = {label.split("/")[0] for label, _n, _a in anchor_sets}
        assert groups == {group.split("_")[0] for group in _MUTANT_GROUPS}, sorted(groups)
        assert {old for _l, _n, anchors in anchor_sets for old, _new in anchors} == (
            {f"return len(self.{name})" for name in AOP._ROW_LIST_FIELDS}
            | {f'"{name}": sorted(self.{name}),' for name in AOP._ROW_LIST_FIELDS}
            | {f'"{name}": dict(sorted(self.{name}.items())),' for name in _MAPPING_FIELDS}
            | {_GATE_ANCHOR, _M5_ANCHORS[0][0], _M6_JSON_ANCHORS[0][0]}
        ), "锚点串集合与按生产域拼出的那一套不等 —— 某个字段 / Mapping 漏了变异"
        misses: list[str] = []
        for label, name, anchors in anchor_sets:
            src = inspect.getsource(getattr(AOP, name))
            for old, _new in anchors:
                hits = src.count(old)
                if hits != 1:
                    misses.append(f"{label}/{name}: hits={hits} for {old!r}")
        assert not misses, "变异锚点命中数不为 1：\n  " + "\n  ".join(misses)
        # 变异对照：同一计数器对一条**已知不存在**的锚点必须报 0（否则它什么都没在数）
        assert inspect.getsource(AOP.ItemOverwriteDelta).count("_aos_p46_absent_anchor_") == 0

    def test_unmutated_reexec_reproduces_the_production_digest(self) -> None:
        """🔴 `_model_namespace()` 无变异时与生产**逐字符等价** —— 否则 M6 那类「只变一处」的
        用例里，另外两个被 re-exec 的对象本身就成了未声明的变异，红的归因全不可信。
        """
        delta_cls, plan_cls = _model_pair()
        clone, produced = fixed_plan(delta_cls=delta_cls, plan_cls=plan_cls), fixed_plan()
        assert clone.digest == produced.digest, (clone.digest, produced.digest)
        assert clone.canonical_form() == produced.canonical_form()
        assert type(clone) is not type(produced), "两者竟是同一个类 ⇒ 本判据什么都没证"
        # 判据在变异体上必须打红（否则它只是在复述「两次构造相等」）
        rows = dict(added=("z", "a"), ghost=())
        bad_delta, bad_plan = _model_pair(delta=_M4_ANCHORS[_LIST_FIELDS[0]])
        assert (
            fixed_plan(delta_cls=bad_delta, plan_cls=bad_plan, **rows).digest
            != fixed_plan(**rows).digest
        ), "去掉 sorted 的变异体竟与生产算出同一个 digest ⇒ 本判据无区分力"


# ── ── 指针 ── ──────────────────────────────────────────────────────────────────────────── ──
# 主体判据 / 场景建造器 / 反空转（`_SAW` 的 16 条结构性保证）/ digest 形态稳定性 / 拼接歧义
# 三边界判据本体，全在 `test_aos_plan_selfconsistency_and_digest.py`。本文件只承变异反证 +
# 收口 + 未污染；两份合起来才是 Task 3.2 + 3.3 的完整交付。
