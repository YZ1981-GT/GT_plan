"""spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirement 1.3 · design § prework 合并记录「1.3 降为 P1 的边界」· ADR-AOS-002 · 六道保护第 1/3 道

**Task 4.7：`in` 与空元组的显式对照** —— 两个具体例子，**不是 property**（本文件无 `@given`）。

| 输入 | 期望 |
| --- | --- |
| `table_key` **不在** `row_keys` 键集合 | 不碰（返回**入参对象本身**，`is` 相等；`deleted == ()`） |
| `table_key` **在**键集合但值为 `()` | 清空该表的受管行（`deleted` 含全部 store 侧身份） |

═══ 为什么这两例要单独写成例子级单测 ═══

prework 把 Requirement 1.3 降为 Property 1 的边界（「declared 为空 ⇒ 结果为空，由 P1 生成器
覆盖」），同时明写「另配一个**显式对照单测**钉死『不在键集合』与『在键集合但空』行为不同」。
本文件就是那个**可读性锚点**：读代码的人一眼看到两种输入的行为差异，不必去推 P1 的生成器。

⇒ 本文件**不重复** `test_aos_property_plan_rowsets.py`（Task 4.3）的 P1 断言：那边测
`compute_overwrite_plan` 的**计划期**三清单（`empty_declared` / `undeclared` 是它的生成器维度
之一），本文件直接测 `prune_undeclared_rows` 的**返回对象身份**与删除清单。

═══ 两例必须放在一起断言「行为不同」═══

各自独立通过没有意义 —— 把两种输入**混成一种**的实现（`.get(table_key) or ()`）会让
「不碰」那例静默变成「清空」，而它自己的等式仍自洽。故本文件的收口判据是
:meth:`TestDeclaredTableBinaryContrast.test_the_two_inputs_do_not_collapse_into_one_behaviour`：
同一份载荷、同一个 reader，只换 `row_keys`，断言 `deleted` 一侧为空、另一侧非空，
**且两侧删除条数不等**。混成一种即当场打红。

═══ 为什么不是追加进 `test_aos_skip_whitelist_guard.py` ═══

Task 4.8 在其文末留了 4.7 落点与**余量约 93 行**（交付时现算 707 行 / `.py` 门禁 800），并写明
「若判据超出这个余量，另开伴生文件，不要挤到门禁边缘」。本文件 = 两例 + 对照 + 两组源码级变异
反证 + 反空转判据，远超 93 行 ⇒ 按它给的处置抽伴生（域内第五次同样处置）。

═══ 建造器不抄第二份 ═══

`_spec` / `_readers` / `_row` / `IDENTITY_KEYS` 从 `test_aos_property_row_identity` import，
`_source_mutant` 从 `test_aos_property_ghost_gate` import —— 两个文件的文末指针都明写
「禁抄第二份」。import 用**顶层模块名**形态：`backend/tests/workpaper_sync/` 无 `__init__.py`
⇒ pytest 以 `prepend` 模式把该目录塞进 `sys.path`；写成 `tests.workpaper_sync.…` 会得到
**第二个**模块实例，模块级累计器就会分家。
"""
from __future__ import annotations

import inspect
from typing import Any, Callable, Mapping

import pytest

from app.services.workpaper_sync import adopt_overwrite_plan as AOC
from app.services.workpaper_sync.adopt_overwrite_plan import prune_undeclared_rows

# 🔴 禁抄第二份：变异手段与建造器全部复用既有实现（见模块 docstring）。
from test_aos_property_ghost_gate import _source_mutant  # noqa: E402
from test_aos_property_row_identity import (  # noqa: E402
    IDENTITY_KEYS,
    _readers,
    _row,
    _spec,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. 两例共用的坐标（只有 `row_keys` 不同 —— 这是「对照」成立的前提）
# ═══════════════════════════════════════════════════════════════════════════

#: 行身份键取自**现算**域的第一个取值（`IDENTITY_KEYS` 现算 7 种）—— 本文件不写键名字面量
#: （Requirement 4.5）。
_IDENTITY_KEY: str = IDENTITY_KEYS[0]

#: store 侧受管行身份。**三行**：让「删除条数不等」这条断言有可数的差（0 vs 3）。
_STORE_IDENTITIES: tuple[str, ...] = ("aos47-r1", "aos47-r2", "aos47-r3")

#: 「不在键集合」那例里 projection 改去声明的**另一张**表。它不在本 reader 的 `declared_scopes`
#: 里 ⇒ 本 item 的 table 恰好落在「不在 `row_keys` 键集合」上（ADR-AOS-002：声明了才动）。
#: 🔴 刻意**不用空 `row_keys`**：空字典也满足「不在键集合」，但那样就分不清「作用域门生效」
#: 与「入参恰好是空的」——留一个真声明在里面，判据才有区分力。
_OTHER_TABLE = "aos47_other_table_rows"

#: 每个 `_stage` 都跑三个已落地的 `RowReader` 实现（门面路 / R3 路 / 对账包装）。
_READER_COUNT = 3


def _stage(reader_index: int) -> tuple[str, Any, Any, list[dict[str, Any]]]:
    """造 `(reader 名, spec, reader, store 载荷)`。

    🔴 返回的载荷是**一个** list 对象，两例共用它（见
    `test_the_two_inputs_do_not_collapse_into_one_behaviour`）——「不碰」那例的最强断言是
    `is` 相等（`prune_undeclared_rows` docstring：「零删除时第一个元素是入参对象本身」，
    连重序列化都不发生），而 `is` 只有在两例喂同一个对象时才可对照。

    行由 `_row` 造 ⇒ 其余 6 个现算键名全被布成 `DECOY-*`：任何「按已知键名嗅探」的实现会取到
    诱饵而不是真身份，于是本文件的期望身份清单当场不成立。
    """
    spec = _spec(identity_key=_IDENTITY_KEY)
    label, reader = _readers(spec)[reader_index]
    payload = [
        _row(_IDENTITY_KEY, identity, noise={}, section=("", ""))
        for identity in _STORE_IDENTITIES
    ]
    return label, spec, reader, payload


def _identities_of(rows: Any) -> list[str]:
    """从载荷里逐行取身份（顺序保留）—— 判「清空」与「原序未动」都靠它。"""
    return [row[_IDENTITY_KEY] for row in rows]


# ═══════════════════════════════════════════════════════════════════════════
# 2. 两例的**唯一**判据实现（变异体喂进来必须打红 ⇒ 判据能为 False）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 判据写成「吃一个 `prune` 可调用对象」的函数，而不是内联在 test 里：变异反证要拿**同一条**
#    判据去跑变异体，两处各写一份就成了「变异体跑的是另一套宽松断言」。


def _judge_untouched(
    prune: Callable[..., Any], stage: tuple[str, Any, Any, list[dict[str, Any]]]
) -> tuple[str, ...]:
    """例 ①「`table_key` **不在** `row_keys` 键集合 ⇒ 不碰」。

    最强断言是 `new_payload is payload`（不是 `==`）—— Requirement 1.2 的「保持原样不变」按
    字面兑现：返回入参对象本身，调用方连重序列化都不会触发。
    """
    label, spec, reader, payload = stage
    row_keys: Mapping[str, tuple[str, ...]] = {_OTHER_TABLE: _STORE_IDENTITIES}
    assert spec.table_key not in row_keys, (
        f"{label}：前提已破 —— 本例要的就是 table {spec.table_key!r} **不在**键集合里"
    )
    new_payload, deleted = prune(payload, row_keys=row_keys, reader=reader)
    assert new_payload is payload, (
        f"{label}：未声明的表被返回了**新对象**（`is` 不相等）—— 作用域门失效"
        "（ADR-AOS-002 / 六道保护第 1 道 / Requirement 1.2）。最典型的成因是把 `in` 判键集合"
        "换成了 `.get(table_key) or ()`，那会把「未声明」压成「声明为空」而整表清空"
    )
    assert deleted == (), (
        f"{label}：未声明的表被删了 {len(deleted)} 行（{list(deleted)}）—— 未声明一律不碰"
    )
    assert _identities_of(new_payload) == list(_STORE_IDENTITIES), (
        f"{label}：行集或原序变了 —— 实得 {_identities_of(new_payload)}"
    )
    return deleted


def _judge_cleared(
    prune: Callable[..., Any], stage: tuple[str, Any, Any, list[dict[str, Any]]]
) -> tuple[str, ...]:
    """例 ②「`table_key` **在**键集合但值为 `()` ⇒ 清空」。

    这条正是 `declared is None` 与真值判断的分界：清空态是**空 set 不是 None**，
    写 `if not declared` 会让「清空」退化成「不碰」（六道保护第 3 道 / Requirement 1.3）。
    """
    label, spec, reader, payload = stage
    row_keys: Mapping[str, tuple[str, ...]] = {spec.table_key: ()}
    assert spec.table_key in row_keys and row_keys[spec.table_key] == (), (
        f"{label}：前提已破 —— 本例要的是「在键集合但值为空元组」"
    )
    before = _identities_of(payload)
    new_payload, deleted = prune(payload, row_keys=row_keys, reader=reader)
    assert deleted == tuple(sorted(_STORE_IDENTITIES)), (
        f"{label}：声明为空元组却只删了 {list(deleted)} —— 应清空**全部** store 侧受管行"
        "（Requirement 1.3）。退化成「不碰」的典型成因是把 `declared is None` 写成 `not declared`"
    )
    assert _identities_of(new_payload) == [], (
        f"{label}：受管行没被清空，仍剩 {_identities_of(new_payload)}"
    )
    assert new_payload is not payload, (
        f"{label}：清空竟返回了入参对象本身 —— 有删除时应是**保留行的新 list**"
    )
    assert _identities_of(payload) == before, (
        f"{label}：入参被原地改动了（{_identities_of(payload)}）—— `prune_undeclared_rows` 是纯函数"
    )
    return deleted


# ═══════════════════════════════════════════════════════════════════════════
# 3. 两例 + 对照（本任务的本体）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("reader_index", range(_READER_COUNT))
class TestDeclaredTableBinaryContrast:
    """Requirement 1.3 的显式对照。三个 reader 实现各跑一遍（口径差异会在这里暴露）。"""

    def test_table_not_in_row_keys_leaves_the_rows_untouched(self, reader_index: int) -> None:
        """例 ①：不在键集合 ⇒ `new is payload` 且 `deleted == ()`。"""
        _judge_untouched(prune_undeclared_rows, _stage(reader_index))

    def test_table_in_row_keys_with_empty_tuple_clears_them(self, reader_index: int) -> None:
        """例 ②：在键集合但值为 `()` ⇒ 受管行清空、`deleted` 含全部 store 侧身份。"""
        _judge_cleared(prune_undeclared_rows, _stage(reader_index))

    def test_the_two_inputs_do_not_collapse_into_one_behaviour(self, reader_index: int) -> None:
        """🔴 **对照本体**：同一载荷、同一 reader，只换 `row_keys` ⇒ 两侧行为必须不同。

        「把两种输入混成一种」的实现会让这条当场打红 —— 它是本文件存在的理由，两例各自独立
        通过并不能排除混同（`.get()` 塌缩后例 ② 的等式仍自洽）。
        """
        stage = _stage(reader_index)
        label, _spec_obj, _reader, payload = stage
        untouched = _judge_untouched(prune_undeclared_rows, stage)
        cleared = _judge_cleared(prune_undeclared_rows, stage)
        assert untouched == () and cleared != (), (
            f"{label}：两种输入的删除清单没分开 —— 不碰侧 {list(untouched)} / 清空侧 {list(cleared)}"
        )
        assert len(untouched) != len(cleared), (
            f"{label}：两侧删除条数相等（各 {len(untouched)} 条）⇒ 「不在键集合」与「在键集合但空」"
            "被混成了同一种语义（Requirement 1.3 / ADR-AOS-002 当场破）"
        )
        assert (len(untouched), len(cleared)) == (0, len(_STORE_IDENTITIES)), (
            f"{label}：实得 (不碰, 清空) = ({len(untouched)}, {len(cleared)})，"
            f"应为 (0, {len(_STORE_IDENTITIES)})"
        )
        assert _identities_of(payload) == list(_STORE_IDENTITIES), (
            f"{label}：两次调用之后入参载荷被改动了 ⇒ 纯函数语义破（对照前提也随之失效）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 变异反证 —— 两组，各只打红一侧（这正是「对照」有区分力的证明）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 手段 = **进程内**源码级变异（复用 Task 4.5 的 `_source_mutant`）：取生产函数源码 → 换一个
#    **唯一**锚点子串 → 在生产模块 globals 的**副本**里 exec。不用 `monkeypatch.setattr` 装回
#    模块 —— 本域有并发会话，装回去即便自动还原也在窗口期内改了共用模块的行为。生产文件一字不动
#    （判据见 `test_mutation_did_not_touch_the_production_module`）。锚点是子串不是行号（行号会漂）；
#    `_source_mutant` 内的 `count(old) == 1` 让锚点消失时当场打红。

#: **M1 —— `in` 判键集合换成 `.get(table_key) or ()`**（六道保护第 3 道「不得混用」的反面）。
#: 🔴 用**五行整块**单锚点而不是「摘掉守卫」：只摘守卫会在 `row_keys[table_key]` 撞 `KeyError`，
#: 那不是要模拟的危害；整块换成字面的 `.get(table_key) or ()` 才是真实会被写出来的那种代码。
#: 预期：例 ① 打红（未声明的整表被清空）、例 ② **不受影响**。
_M1_GET_INSTEAD_OF_IN: tuple[str, str] = (
    (
        "        if table_key not in row_keys:  # 🔴 未声明 ⇒ 一个字节都不碰\n"
        "            continue\n"
        "        in_scope.setdefault(section, set()).update(\n"
        "            _declared_identities(row_keys[table_key], table_key=table_key)\n"
        "        )\n"
    ),
    (
        "        in_scope.setdefault(section, set()).update(\n"
        "            _declared_identities(row_keys.get(table_key) or (), table_key=table_key)\n"
        "        )\n"
    ),
)

#: **M2 —— 空集判据换成真值判断**（`declared is None` ⇒ `not declared`）。清空态是**空 set
#: 不是 None** ⇒ 真值判断会让「清空」退化成「不碰」。预期：例 ② 打红、例 ① **不受影响**。
_M2_TRUTHY_INSTEAD_OF_IS_NONE: tuple[str, str] = (
    "if declared is None or identity in declared:",
    "if not declared or identity in declared:",
)

#: 变异组名 → 判据打红次数（收口判据会核对）。
_MUTANT_REDS: dict[str, int] = {}

_MUTANT_GROUPS: tuple[str, ...] = (
    "M1_get_instead_of_in",
    "M2_truthy_instead_of_is_none",
)


def _prune_mutant(anchor: tuple[str, str]) -> Callable[..., Any]:
    """`prune_undeclared_rows` 的变异体（生产模块一字不动）。"""
    return _source_mutant(
        prune_undeclared_rows, old=anchor[0], new=anchor[1], module=AOC
    )


def _expect_red(name: str, run: Callable[[], Any]) -> AssertionError:
    """跑变异体，要求判据**打红**；红了就记一次。"""
    with pytest.raises(AssertionError) as excinfo:
        run()
    _MUTANT_REDS[name] = _MUTANT_REDS.get(name, 0) + 1
    return excinfo.value


@pytest.mark.parametrize("reader_index", range(_READER_COUNT))
class TestBinaryJudgeCanBeFalse:
    """两组变异各只打红一侧 ⇒ 两例互为变异证明，缺任一例都会放过一类真实实现错误。"""

    def test_m1_get_instead_of_in_reds_the_untouched_example_only(self, reader_index: int) -> None:
        """M1：`in` → `.get(table_key) or ()` ⇒ 例 ① 红、例 ② 绿。

        ⇒ **只写例 ②** 的测试会把 M1 判绿，而 M1 正是本 spec 唯一破坏性路径上最严重的一种错
        （未声明的整表被清空）。
        """
        mutant = _prune_mutant(_M1_GET_INSTEAD_OF_IN)
        error = _expect_red(
            "M1_get_instead_of_in", lambda: _judge_untouched(mutant, _stage(reader_index))
        )
        assert "`is` 不相等" in str(error) or "被删了" in str(error), str(error)
        # 另一侧必须仍绿：变异是单侧的，否则「两例互为变异证明」这句话不成立。
        _judge_cleared(mutant, _stage(reader_index))

    def test_m2_truthy_check_reds_the_cleared_example_only(self, reader_index: int) -> None:
        """M2：`declared is None` → `not declared` ⇒ 例 ② 红、例 ① 绿。

        ⇒ **只写例 ①** 的测试会把 M2 判绿（「清空」静默退化成「不碰」，用户点了覆盖却没删行）。
        """
        mutant = _prune_mutant(_M2_TRUTHY_INSTEAD_OF_IS_NONE)
        error = _expect_red(
            "M2_truthy_instead_of_is_none", lambda: _judge_cleared(mutant, _stage(reader_index))
        )
        assert "只删了" in str(error) or "没被清空" in str(error), str(error)
        _judge_untouched(mutant, _stage(reader_index))


class TestMutationHygiene:
    """变异手段自身的验收：锚点实时唯一、生产文件未被回写。"""

    def test_mutation_did_not_touch_the_production_module(self) -> None:
        """🔴 两个锚点在**实时**生产源码里仍各恰 1 处、且未出现变异串。

        本域有并发会话 ⇒ 「用进程内变异而不是改文件」这件事本身需要判据：变异体若被回写，
        锚点就不在了。
        """
        live = inspect.getsource(getattr(AOC, prune_undeclared_rows.__name__))
        for old, new in (_M1_GET_INSTEAD_OF_IN, _M2_TRUTHY_INSTEAD_OF_IS_NONE):
            assert live.count(old) == 1, (
                f"锚点在实时源码里命中 {live.count(old)} 次（须恰 1）—— 生产写法已变，"
                f"本文件的变异反证须按新写法重建：{old!r}"
            )
            assert new not in live, (
                f"实时源码里出现了变异串 {new!r} —— 变异体被回写进了生产模块"
            )

    def test_both_gates_live_in_the_same_function(self) -> None:
        """两道门必须都在 `prune_undeclared_rows` 里：散到别处就是第二真源，对照测不到它。"""
        whole = inspect.getsource(AOC)
        body = inspect.getsource(prune_undeclared_rows)
        gates = (
            "if table_key not in row_keys:",
            "if declared is None or identity in declared:",
        )
        for token in gates:
            assert whole.count(token) == body.count(token) == 1, (
                f"{token!r} 全模块 {whole.count(token)} 处 / 函数体内 {body.count(token)} 处 "
                "⇒ 门被复制到了别处（第二真源）"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 5. 反空转判据（定义在最后 ⇒ 上面两例与两组变异已跑过）
# ═══════════════════════════════════════════════════════════════════════════


class TestContrastDidNotRunVacuously:
    """判据不是恒真：两组变异都真被打红，且两例的坐标本身不是空的。"""

    def test_every_mutant_group_was_caught(self) -> None:
        """🔴 **不 skip**：累计器空时（如 `-k` 定向只选了本条）自己把两组跑满。

        期望红数由 reader 实现数**推导**，不写死。
        """
        expected = len(_readers(_spec(identity_key=_IDENTITY_KEY)))
        assert expected == _READER_COUNT, (
            f"reader 实现数现算 {expected} 而本文件按 {_READER_COUNT} 参数化 —— 须同步"
        )
        before = dict(_MUTANT_REDS)
        mutants = TestBinaryJudgeCanBeFalse()
        for index in range(expected):
            mutants.test_m1_get_instead_of_in_reds_the_untouched_example_only(index)
            mutants.test_m2_truthy_check_reds_the_cleared_example_only(index)
        gained = {
            name: _MUTANT_REDS.get(name, 0) - before.get(name, 0) for name in _MUTANT_GROUPS
        }
        assert all(gained[name] == expected for name in _MUTANT_GROUPS), (
            f"本判据自跑一轮实得红数 {gained}，应逐个等于 reader 实现数 {expected} —— "
            "某一组没打满（= 那类实现错误对本对照至少在一个 reader 上不可见）"
        )
        assert set(_MUTANT_REDS) == set(_MUTANT_GROUPS), (
            f"变异组累计 {sorted(_MUTANT_REDS)} != 登记的 {list(_MUTANT_GROUPS)}"
        )

    def test_the_two_examples_have_non_empty_coordinates(self) -> None:
        """坐标非空：store 侧真有多行、`_OTHER_TABLE` 真不在 reader 的 scope 里。

        少了这条，两例在「载荷本来就是空的」「reader 本来就声明了 _OTHER_TABLE」上恒真。
        """
        label, spec, reader, payload = _stage(0)
        assert len(payload) == len(_STORE_IDENTITIES) >= 2, (label, len(payload))
        scopes = tuple(getattr(reader, "declared_scopes", ()) or ())
        tables = {table for table, _section in scopes}
        assert tables == {spec.table_key}, f"{label}：reader 的 scope 不止本表 —— {sorted(tables)}"
        assert _OTHER_TABLE not in tables, (
            f"{label}：对照用的 {_OTHER_TABLE!r} 竟在 reader 的 scope 里 ⇒ 例 ① 测的不是「未声明」"
        )

    def test_identity_key_came_from_the_live_census(self) -> None:
        """身份键来自**现算**域（Property 10 的 `IDENTITY_KEYS`），不是本文件的字面量。"""
        assert len(IDENTITY_KEYS) >= 7, (
            f"现算身份键域收窄到 {len(IDENTITY_KEYS)} 种（design 记 7）—— 须回 spec 登记差异"
        )
        assert _IDENTITY_KEY in IDENTITY_KEYS
        decoys = {
            key for key in IDENTITY_KEYS if key != _IDENTITY_KEY
        }
        row = _stage(0)[3][0]
        assert all(str(row[key]).startswith("DECOY-") for key in decoys), (
            "诱饵没布上 ⇒ 「按已知键名嗅探」的实现也能让本文件两例通过"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 本文件到此为止 = Task 4.7 全部内容。后续任务不要往这里追加：它只承载 Requirement 1.3 的
# 两例对照。Property 2（Task 4.4）落在 `test_aos_property_plan_rowsets.py` 或其伴生，
# Property 8（Task 4.6）落在 `test_aos_property_ghost_gate.py` 或其伴生。
#
# 可复用（禁抄第二份）：`_stage(reader_index)` / `_judge_untouched(prune, stage)` /
#    `_judge_cleared(prune, stage)` / `_prune_mutant(anchor)` / `_expect_red(name, run)`。
# ══════════════════════════════════════════════════════════════════════════════
