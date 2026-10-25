"""adopt 覆盖计划 —— Property 2 的**变异反证**（`test_aos_property_out_of_scope_rows.py` 伴生件）。

spec: workpaper-sync-adopt-overwrite-and-refresh-source（Task 4.4）
Requirements 1.2 / 1.4 · design § Correctness Properties · ADR-AOS-002

本文件只承两件事：**四组变异反证**（M1~M4，§5）与**「未污染生产模块」/ 红数收口**判据（§6）。
判据（`_assert_property_2`）与场景建造器（`_b_payload` / `_b_readers` / `_p2_spec` /
`_section_field` / `_identity_seq`）一律从主体文件 import，**不另造第二份** —— 两边的判据一漂
就在测不同的东西了。切分理由与「为什么不复用 Task 4.3 的 `_MUTANT_REDS`」见主体文件模块
docstring 与其末尾的指针注释。

🔴 **import 必须用顶层模块名**（`from test_aos_property_out_of_scope_rows import …`）：该目录无
`__init__.py`，pytest 以 `prepend` 模式把它塞进 `sys.path`；写成 `tests.workpaper_sync.…` 会拿到
**第二个**模块实例，模块级累计器 `_P2_MUTANT_REDS` 就会分家 —— §6 的收口判据会取到空 dict 而
本文件的红一次都不算数（这类「写了但从未被读」的累计器正是假绿的标准形态）。
"""
from __future__ import annotations

import ast
import inspect
import types
from pathlib import Path
from typing import Any, Iterator, Mapping

import pytest

from app.services.workpaper_sync import adopt_overwrite_compute as AOC
from app.services.workpaper_sync import adopt_overwrite_plan as AOP
from app.services.workpaper_sync import adopt_row_reader_r3 as R3
from app.services.workpaper_sync.adopt_overwrite_plan import (
    ItemOverwriteDelta,
    prune_undeclared_rows,
)
from app.services.workpaper_sync.adopt_row_reader_r3 import EngineRowReader

# 🔴 Property 2 判据与 (b) 维建造器的**唯一**来源（禁抄第二份；顶层模块名形态见 docstring）。
from test_aos_property_out_of_scope_rows import (  # noqa: E402
    _P2_MUTANT_REDS,
    _SEG_IN,
    _TABLE_IN,
    _TABLE_OUT,
    _assert_property_2,
    _b_payload,
    _b_readers,
    _identity_seq,
    _p2_spec,
    _section_field,
)
from test_aos_property_plan_rowsets import (  # noqa: E402
    _plan_for,
    _rows_of,
    _scenario,
)
from test_aos_property_row_identity import (  # noqa: E402
    IDENTITY_KEYS,
    ITEM,
    _readers,
    _row,
    _spec,
)

# ═══════════════════════════════════════════════════════════════════════════
# 5. 变异反证 —— 判据必须能为 False（🔴 全部**进程内**，一个共用文件都不改）
# ═══════════════════════════════════════════════════════════════════════════
#
# 手段沿用 Task 4.5 的源码级进程内变异：`inspect.getsource` 取生产函数源码 → 替换**唯一**锚点
# 子串 → 在生产模块 globals 的**副本**里 exec → 得到独立函数对象，**不**回写模块。
# 理由（比 4.5 又多一条）：本域有并发会话（Task 4.6 / 4.7 正在另两个文件上跑），
# `monkeypatch.setattr` 即便自动还原，窗口期内也改了共用模块的行为。
# 锚点是子串不是行号；`count(old) == 1` 让锚点消失时当场打红 —— 那说明门的写法变了，反证须重建。


def _source_mutant(func: Any, *, anchors: tuple[tuple[str, str], ...], module: Any) -> Any:
    """按若干**唯一**锚点做源码级变异，返回独立函数对象（不回写 module）。"""
    src = inspect.getsource(func)
    for old, new in anchors:
        hits = src.count(old)
        assert hits == 1, (
            f"变异锚点 {old!r} 在 {func.__name__} 源码里命中 {hits} 次（须恰 1）—— 生产写法已变，"
            "本节反证须按新写法重建；不得放宽成「命中就行」"
        )
        src = src.replace(old, new)
    namespace = dict(vars(module))  # 🔴 副本 —— exec 不得写进生产模块的 globals
    exec(  # noqa: S102 —— 变异体只在本进程内存在，不落盘、不回写生产模块
        compile(
            "from __future__ import annotations\n" + src,
            f"<aos-p2 mutant {func.__name__}>",
            "exec",
        ),
        namespace,
    )
    return namespace[func.__name__]


#: **M1 —— 空值二分踩错**：`table_key in row_keys` 换成 `.get(table_key) or ()`。
#: 后果：**未声明**的表被压成「声明为空」⇒ 整表清空（(a) 维）。两条锚点必须一起换 ——
#: 只换判断会让 `row_keys[table_key]` 抛 KeyError，那不是 `.get()` 实现的行为。
_M1_PRUNE = (
    ("if table_key not in row_keys:  # 🔴 未声明 ⇒ 一个字节都不碰", "if False:"),
    (
        "_declared_identities(row_keys[table_key], table_key=table_key)",
        "_declared_identities(row_keys.get(table_key) or (), table_key=table_key)",
    ),
)
_M1_COMPUTE = (
    ("if table_key not in row_keys:  # 🔴 未声明 ⇒ 一个字节都不碰", "if False:"),
    (
        "declared = _declared_identities(row_keys[table_key], table_key=table_key)",
        "declared = _declared_identities(row_keys.get(table_key) or (), table_key=table_key)",
    ),
)
#: **M2 —— 分区门整个去掉**：不按行的分区查表，改对全部 in-scope 身份做**全量差集**。
#: 后果：兄弟分区的行被删（(b) 维）。design 六道保护第 2 条点名的那件事
#: （「引擎 `iter_store_rows` 明写三段读同一个数组 ⇒ 做全量差集就会删掉兄弟分区」）。
_M2_NO_SECTION_GATE = (
    (
        "declared = in_scope.get(reader.section_of(row))",
        "declared = set().union(*in_scope.values())",
    ),
)
#: **M3 —— 分区值归一**：`section_value_of` 做 `strip()`（该函数 docstring 点名禁止的那一条，
#: 理由是引擎的过滤式不 strip）。后果：**未声明**的分区值 `" X"` 被归一进已声明桶 `"X"`
#: ⇒ 作用域外的行混进在 scope 桶被误删（(b) 维）。
#: 🔴 这是任务书那条「归一成 `None`」在生产接线下**可达**的同型形态 ——
#: 后者不可达，依据见 :class:`TestNoneCollapseIsUnreachable`。
_M3_STRIP_SECTION = (
    ('return str(row.get(field) or "") or None', 'return str(row.get(field) or "").strip() or None'),
)
#: **M4 —— 按 `reader.iter_rows` 重建载荷**（而不是按位置摘）。
#: 后果两条：① 未被任何 spec 覆盖的分区值**凭空消失**（reader 枚举不到它）；
#: ② 多段 reader 逐 spec yield ⇒ 保留行被按分区重排，原序丢失。逐元素/对象身份判据据此打红。
_M4_REBUILD_FROM_READER = (
    (
        "kept = [element for ordinal, element in enumerate(rows) if ordinal not in doomed]",
        "kept = [row for identity, row in reader.iter_rows(rows) if identity not in deleted]",
    ),
)

_MUTANT_GROUPS: tuple[str, ...] = (
    "M1_get_instead_of_in",
    "M2_section_gate_removed",
    "M3_section_value_stripped",
    "M4_rebuilt_from_reader",
)


def _expect_red_p2(name: str, run: Any) -> AssertionError:
    """跑变异体，要求 Property 2 的判据**打红**；红了就记一次。"""
    assert name in _MUTANT_GROUPS, f"未登记的变异组名 {name!r}"
    with pytest.raises(AssertionError) as excinfo:
        run()
    _P2_MUTANT_REDS[name] = _P2_MUTANT_REDS.get(name, 0) + 1
    return excinfo.value


class _SectionProxyReader:
    """把 `section_of` 路由到**变异后的** `section_value_of`，其余成员原样转发真 reader。

    🔴 为什么要它：`EngineRowReader.section_of` 走模块全局 `section_value_of`，而变异体是个独立
    函数对象（没有也不该被装回 `adopt_row_reader_r3`）⇒ 用代理把生产的那条杆子接上，
    生产模块一字不动。代理自己不做任何分区判断。
    """

    def __init__(self, inner: Any, section_fn: Any) -> None:
        self._inner = inner
        self._section_fn = section_fn
        self.item_id = inner.item_id
        self.section_field = inner.section_field
        self.declared_scopes = tuple(inner.declared_scopes)

    def iter_rows(self, payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
        return self._inner.iter_rows(payload)

    def section_of(self, row: Mapping[str, Any]) -> str | None:
        return self._section_fn(row, field=self.section_field, item_id=self.item_id)


#: M1~M4 共用的确定性 (b) 维输入（固定取值，便于逐行对账）。
_FIX_UPD, _FIX_DEL = ["upd-a1"], ["del-z9", "del-运输费用"]
_FIX_SIB, _FIX_UNENUM = ["sib-s1", "sib-s2"], ["unenum-u1"]


def _fixed_b_case(identity_key: str, reader_index: int):
    payload, outside = _b_payload(
        identity_key=identity_key,
        in_updated=_FIX_UPD,
        in_deleted=_FIX_DEL,
        siblings=_FIX_SIB,
        unenumerated=_FIX_UNENUM,
    )
    label, reader = _b_readers(identity_key)[reader_index]
    return payload, outside, label, reader, {_TABLE_IN: tuple(_FIX_UPD)}


class TestPropertyTwoJudgeCanBeFalse:
    """四个变异体各对应一类真实实现错误，Property 2 的判据必须逐个打红。"""

    @pytest.mark.parametrize("reader_index", range(3))
    def test_m1_get_instead_of_in_is_caught(self, reader_index: int) -> None:
        """M1（(a) 维）：`.get()` 塌缩 ⇒ 未声明的整表被清空。红两次（delta 侧 + 行侧）。"""
        identity_key = IDENTITY_KEYS[0]
        spec = _spec(identity_key=identity_key)
        payload, row_keys, store_ids, declared = _scenario(
            mode="undeclared",
            both=["upd-a1"],
            only_substrate=["add-x1"],
            only_store=["del-z9", "del-运输费用"],
            identity_key=identity_key,
            as_json_text=False,
        )
        assert declared is None
        rows_before = list(payload)
        label, reader = _readers(spec)[reader_index]
        outside_tables = frozenset({spec.table_key})
        base = dict(
            payload_before=payload,
            rows_before=rows_before,
            outside=rows_before,
            outside_tables=outside_tables,
            identity_key=identity_key,
            by_object=True,
        )
        # 对照组：生产实现既不产 delta 也不删一行（否则下面的红没有意义）。
        pruned, deleted = prune_undeclared_rows(payload, row_keys=row_keys, reader=reader)
        _assert_property_2(
            label=f"{label} / M1 对照组",
            pruned=pruned,
            deleted=deleted,
            deltas=_plan_for(row_keys=row_keys, payload=payload, reader=reader).deltas,
            **base,
        )
        # 变异体①：计划侧 —— 用变异后的 `_in_scope_by_section` 现算，证明未声明的表真进了作用域。
        mutant_buckets = _source_mutant(
            AOC._in_scope_by_section, anchors=_M1_COMPUTE, module=AOC
        )(
            ITEM,
            tuple(reader.declared_scopes),
            section_field=str(getattr(reader, "section_field", "") or ""),
            row_keys=row_keys,
        )
        assert [t for t, _ids in mutant_buckets.values()] == [spec.table_key], (
            f"{label}：`.get()` 塌缩后未声明的表竟没进作用域（实得 {mutant_buckets}）—— "
            "变异没生效，反证前提已变"
        )
        _expect_red_p2(
            "M1_get_instead_of_in",
            lambda: _assert_property_2(
                label=f"{label} / M1 计划侧",
                pruned=pruned,
                deleted=deleted,
                deltas=(
                    ItemOverwriteDelta(
                        item_id=ITEM,
                        table_key=spec.table_key,
                        rows_deleted=tuple(sorted(store_ids)),
                    ),
                ),
                **base,
            ),
        )
        # 变异体②：删除侧 —— 变异后的 prune 把整表删空。
        m_pruned, m_deleted = _source_mutant(
            AOP.prune_undeclared_rows, anchors=_M1_PRUNE, module=AOP
        )(payload, row_keys=row_keys, reader=reader)
        assert set(m_deleted) == set(store_ids) and not _rows_of(m_pruned), (
            f"{label}：`.get()` 塌缩后没清空整表（删 {list(m_deleted)}）—— 变异没造出它要模拟的危害"
        )
        _expect_red_p2(
            "M1_get_instead_of_in",
            lambda: _assert_property_2(
                label=f"{label} / M1 删除侧", pruned=m_pruned, deleted=m_deleted, deltas=(), **base
            ),
        )

    @pytest.mark.parametrize("reader_index", (0, 1))
    def test_m2_section_gate_removed_is_caught(self, reader_index: int) -> None:
        """M2（(b) 维）：全量差集 ⇒ 兄弟分区被删。"""
        identity_key = IDENTITY_KEYS[0]
        payload, outside, label, reader, row_keys = _fixed_b_case(identity_key, reader_index)
        m_pruned, m_deleted = _source_mutant(
            AOP.prune_undeclared_rows, anchors=_M2_NO_SECTION_GATE, module=AOP
        )(payload, row_keys=row_keys, reader=reader)
        assert set(_FIX_SIB) <= set(m_deleted), (
            f"{label}：去掉分区门后兄弟分区竟没被删（实删 {list(m_deleted)}）—— 变异没生效"
        )
        _expect_red_p2(
            "M2_section_gate_removed",
            lambda: _assert_property_2(
                label=f"{label} / M2 全量差集",
                payload_before=payload,
                rows_before=payload,
                outside=outside,
                outside_tables=frozenset({_TABLE_OUT}),
                pruned=m_pruned,
                deleted=m_deleted,
                deltas=(),
                identity_key=identity_key,
                by_object=True,
            ),
        )

    @pytest.mark.parametrize("reader_index", (0, 1))
    def test_m3_section_value_stripped_is_caught(self, reader_index: int) -> None:
        """M3（(b) 维）：`section_value_of` 做 strip ⇒ 未声明分区值 `" X"` 归一进已声明桶 `"X"`。

        构造：兄弟分区的分区值 = 声明分区值**加一个前导空格**（真实数据里存在这种取值 ——
        B/C 两轮已实证 sheet 名带前导空格且禁 `strip()`）。引擎的过滤式按**逐字相等**匹配
        ⇒ 这些行确实被 yield 出来，`section_of` 判出 `" X"`、不在 `in_scope` ⇒ 生产保留。
        """
        identity_key = IDENTITY_KEYS[0]
        field = _section_field()
        ws_section = f" {_SEG_IN}"  # 🔴 未声明的分区值：只比声明值多一个前导空格
        specs = (
            _p2_spec(table_key=_TABLE_IN, section_value=_SEG_IN, identity_key=identity_key),
            _p2_spec(table_key=_TABLE_OUT, section_value=ws_section, identity_key=identity_key),
        )
        scopes = tuple((s.table_key, s.row_section_value) for s in specs)
        reader = EngineRowReader(
            item_id=ITEM, specs=specs, section_field=field, declared_scopes=scopes
        )
        payload = [
            _row(identity_key, "ws-out-1", noise={}, section=(field, ws_section)),
            _row(identity_key, "upd-a1", noise={}, section=(field, _SEG_IN)),
            _row(identity_key, "del-z9", noise={}, section=(field, _SEG_IN)),
        ]
        outside = [payload[0]]
        row_keys = {_TABLE_IN: ("upd-a1",)}
        base = dict(
            payload_before=payload,
            rows_before=payload,
            outside=outside,
            outside_tables=frozenset({_TABLE_OUT}),
            identity_key=identity_key,
            by_object=True,
        )
        pruned, deleted = prune_undeclared_rows(payload, row_keys=row_keys, reader=reader)
        assert deleted == ("del-z9",), f"对照组实删 {list(deleted)} —— 应只删作用域内未声明的那条"
        _assert_property_2(label="M3 对照组", pruned=pruned, deleted=deleted, deltas=(), **base)
        proxy = _SectionProxyReader(
            reader, _source_mutant(R3.section_value_of, anchors=_M3_STRIP_SECTION, module=R3)
        )
        assert proxy.section_of(payload[0]) == _SEG_IN, (
            f"strip 变异后 {ws_section!r} 没被归一成 {_SEG_IN!r}（实得 "
            f"{proxy.section_of(payload[0])!r}）—— 变异没生效"
        )
        m_pruned, m_deleted = prune_undeclared_rows(payload, row_keys=row_keys, reader=proxy)
        assert "ws-out-1" in m_deleted, f"归一后作用域外的行竟没被误删（实删 {list(m_deleted)}）"
        _expect_red_p2(
            "M3_section_value_stripped",
            lambda: _assert_property_2(
                label=f"M3 归一（reader_index={reader_index}）",
                pruned=m_pruned,
                deleted=m_deleted,
                deltas=(),
                **base,
            ),
        )

    @pytest.mark.parametrize("reader_index", (0, 1))
    def test_m4_rebuilt_from_reader_is_caught(self, reader_index: int) -> None:
        """M4（逐元素 / 对象身份）：按 `iter_rows` 重建载荷 ⇒ 未枚举到的分区值消失 + 原序丢失。"""
        identity_key = IDENTITY_KEYS[0]
        payload, outside, label, reader, row_keys = _fixed_b_case(identity_key, reader_index)
        m_pruned, m_deleted = _source_mutant(
            AOP.prune_undeclared_rows, anchors=_M4_REBUILD_FROM_READER, module=AOP
        )(payload, row_keys=row_keys, reader=reader)
        got = _identity_seq(_rows_of(m_pruned), identity_key)
        assert set(_FIX_UNENUM).isdisjoint(got), (
            f"{label}：重建后未被枚举的分区值竟还在（{got}）—— 变异没生效（引擎的分区过滤口径变了？）"
        )
        assert set(m_deleted) == set(_FIX_DEL), (
            f"{label}：M4 只该改「怎么保留」不该改「删谁」，实删 {list(m_deleted)}"
        )
        _expect_red_p2(
            "M4_rebuilt_from_reader",
            lambda: _assert_property_2(
                label=f"{label} / M4 按 reader 重建",
                payload_before=payload,
                rows_before=payload,
                outside=outside,
                outside_tables=frozenset({_TABLE_OUT}),
                pruned=m_pruned,
                deleted=m_deleted,
                deltas=(),
                identity_key=identity_key,
                by_object=True,
            ),
        )

# ═══════════════════════════════════════════════════════════════════════════
# 6. 收口 —— 红数闭合 + 生产模块未被污染
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么必须有本节：§5 只往 `_P2_MUTANT_REDS` **写**。没有读它的判据时，那个 dict 是个
#    「写了从未被读」的死累计器 —— 四组里任意一组悄悄不再打红（比如 `_expect_red_p2` 被换成
#    直接调用、或某组的 `pytest.raises` 因判据退化而不再触发）都不会有人发现。
#    主体文件末尾的指针注释也把「未污染生产模块」判据落点写在本文件。


def _red_sites_by_group() -> dict[str, int]:
    """现算各组在本文件里的 `_expect_red_p2(...)` **调用点数**（AST，禁文本匹配）。

    🔴 用它而不是写死「M1 该红 2 次」：M1 有计划侧 + 删除侧两个红点，而那是**结构**事实
    （源码里就是两处调用），不是拍脑袋的常量。哪天有人加/删一个红点，期望值随之变化，
    收口判据不会因为「常量没跟着改」而误报或漏报。
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    sites: dict[str, int] = {}
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_expect_red_p2"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            continue
        sites[node.args[0].value] = sites.get(node.args[0].value, 0) + 1
    return sites


def _parametrize_counts() -> dict[str, int]:
    """现算各测试方法 `@pytest.mark.parametrize("reader_index", …)` 的**取值个数**（AST）。

    支持本文件实际出现的两种写法：`range(3)` 与 `(0, 1)`。取到的数须与现算 reader 实现数相等
    —— 那条断言就是「参数化没跟着 reader 实现数走」的卡点（域内先例：
    `test_aos_declared_table_binary.py` 的 `_READER_COUNT` 同步判据）。
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
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
                continue
            values = deco.args[1]
            if isinstance(values, ast.Tuple):
                counts[node.name] = len(values.elts)
            elif (
                isinstance(values, ast.Call)
                and isinstance(values.func, ast.Name)
                and values.func.id == "range"
                and len(values.args) == 1
                and isinstance(values.args[0], ast.Constant)
            ):
                counts[node.name] = int(values.args[0].value)
    return counts


class TestMutantRedsAreClosed:
    """四组变异反证的红数收口：逐组红数 = 该组红点数 × 该组 reader 实现数（**全现算**）。"""

    def test_every_group_reds_on_every_reader(self) -> None:
        """自跑一轮四组变异，逐组核对增量红数；再核对累计 key 集合 == 登记组名。

        🔴 自跑而不是依赖「§5 已经跑过」：`-k` 定向选择下 §5 可能一条都没执行，那时读累计器
        会得到空 dict 而判据仍「通过」—— 那正是要防的空转。
        """
        readers_a = len(_readers(_spec(identity_key=IDENTITY_KEYS[0])))
        readers_b = len(_b_readers(IDENTITY_KEYS[0]))
        assert readers_a and readers_b, f"reader 实现数现算为空：(a)={readers_a} (b)={readers_b}"

        suite = TestPropertyTwoJudgeCanBeFalse()
        plan = (
            ("M1_get_instead_of_in", suite.test_m1_get_instead_of_in_is_caught, readers_a),
            ("M2_section_gate_removed", suite.test_m2_section_gate_removed_is_caught, readers_b),
            (
                "M3_section_value_stripped",
                suite.test_m3_section_value_stripped_is_caught,
                readers_b,
            ),
            ("M4_rebuilt_from_reader", suite.test_m4_rebuilt_from_reader_is_caught, readers_b),
        )
        assert [name for name, _m, _r in plan] == list(_MUTANT_GROUPS), (
            f"本判据自跑的组 {[n for n, _m, _r in plan]} != 登记的 {list(_MUTANT_GROUPS)} —— "
            "新增变异组必须同时接进收口判据，否则它可以永远不打红"
        )

        # 参数化取值个数须与现算 reader 实现数一致（否则某个 reader 从未被变异体走过）。
        params = _parametrize_counts()
        for name, method, runs in plan:
            assert params.get(method.__name__) == runs, (
                f"{method.__name__} 按 {params.get(method.__name__)} 参数化，而 {name} 的 reader "
                f"实现数现算 {runs} —— 须同步；少一个就有一个 reader 实现从未被这组变异走过"
            )

        sites = _red_sites_by_group()
        assert set(sites) == set(_MUTANT_GROUPS), (
            f"本文件里的 `_expect_red_p2` 调用点覆盖 {sorted(sites)}，登记的是 "
            f"{list(_MUTANT_GROUPS)} —— 某组登记了却一个红点都没写（或写了未登记的组名）"
        )

        before = dict(_P2_MUTANT_REDS)
        for _name, method, runs in plan:
            for index in range(runs):
                method(index)
        gained = {
            name: _P2_MUTANT_REDS.get(name, 0) - before.get(name, 0)
            for name, _m, _r in plan
        }
        expected = {name: sites[name] * runs for name, _m, runs in plan}
        assert gained == expected, (
            f"本判据自跑一轮实得红数 {gained}，按「红点数 × reader 实现数」应为 {expected} —— "
            "某一组没打满（= 那类实现错误对 Property 2 至少在一个 reader 上不可见）"
        )
        assert set(_P2_MUTANT_REDS) == set(_MUTANT_GROUPS), (
            f"变异组累计 {sorted(_P2_MUTANT_REDS)} != 登记的 {list(_MUTANT_GROUPS)}"
        )
        # 🔴 反空转：累计器真被写过（全零时上面的 `gained == expected` 会在 expected 非零时打红，
        #    但若哪天四组红点全被删光，expected 也会变成全零而恒等 —— 这条堵住那个口子）。
        assert all(v > 0 for v in expected.values()), (
            f"某组的期望红数为 0（{expected}）—— 那组的 `_expect_red_p2` 调用点被删空了，"
            "「判据能为 False」在它上面已无证明"
        )


class TestProductionModulesAreNotPolluted:
    """🔴 变异体只在本进程内存在：不回写生产模块、不与生产模块共享 globals。

    本域有并发会话（同批另两个文件同时在跑），`monkeypatch.setattr` 即便自动还原，窗口期内也
    改了共用模块的行为 ⇒ §5 一律走「`globals` 副本 + `exec`」。本类是那句承诺的判据。
    """

    def test_mutants_are_distinct_objects_and_do_not_alias_production_globals(self) -> None:
        """三个被变异的生产函数：变异体 `is not` 原对象，且 `__globals__` 不是生产模块的 dict。"""
        cases = (
            ("AOP.prune_undeclared_rows", AOP, AOP.prune_undeclared_rows, _M4_REBUILD_FROM_READER),
            ("AOC._in_scope_by_section", AOC, AOC._in_scope_by_section, _M1_COMPUTE),
            ("R3.section_value_of", R3, R3.section_value_of, _M3_STRIP_SECTION),
        )
        for label, module, func, anchors in cases:
            mutant = _source_mutant(func, anchors=anchors, module=module)
            assert mutant is not func, f"{label}：变异体与生产函数是同一个对象"
            assert mutant.__globals__ is not vars(module), (
                f"{label}：变异体与生产模块**共享** globals ⇒ `exec` 已经写进生产模块的命名空间"
            )
            probe = f"_aos_p2_pollution_probe_{label.replace('.', '_')}"
            mutant.__globals__[probe] = object()
            assert probe not in vars(module), (
                f"{label}：往变异体 globals 写入后生产模块也长出了 {probe} —— 是同一个 dict"
            )
            # 生产模块的那个名字仍绑在原对象上（`_source_mutant` 没有 setattr 回去）
            assert getattr(module, func.__name__) is func, (
                f"{label}：生产模块的 {func.__name__} 已被换成别的对象 —— 变异体被回写了"
            )

    def test_the_no_copy_variant_would_really_pollute(self) -> None:
        """变异对照：同一 `exec` 若写进 `vars(module)` **本身**（不取副本），模块确实会被改。

        🔴 没有这条，上一条可能只是在证明「`exec` 本来就不写模块」。用一个丢弃用的
        :class:`types.ModuleType` 承接污染 —— 生产模块一个字节都不碰。
        """
        dummy = types.ModuleType("aos_p2_dummy_module")
        dummy.__dict__.update(vars(AOP))
        original = AOP.prune_undeclared_rows
        assert vars(dummy)["prune_undeclared_rows"] is original

        src = inspect.getsource(original)
        exec(  # noqa: S102 —— 只写进 dummy 模块，用于证明判据有区分力
            compile("from __future__ import annotations\n" + src, "<aos-p2 leak probe>", "exec"),
            vars(dummy),
        )
        assert vars(dummy)["prune_undeclared_rows"] is not original, (
            "写进 `vars(module)` 本身竟没换掉模块里的那个名字 —— 上一条判据无区分力，须重建"
        )
        # 生产模块仍原样（dummy 的 `__dict__` 是 update 出来的副本，不是 AOP 的那个 dict）
        assert AOP.prune_undeclared_rows is original and vars(dummy) is not vars(AOP)

    def test_production_sources_still_carry_every_anchor(self) -> None:
        """全部变异锚点在生产源码里仍**恰 1** 次命中。

        锚点消失说明门的写法变了 ⇒ 反证须按新写法重建。🔴 不得放宽成「命中就行」（那会让
        `src.replace` 静默变成空操作，变异体等于生产实现，红一次都打不出还全绿）。
        """
        anchor_sets = (
            ("_M1_PRUNE", AOP.prune_undeclared_rows, _M1_PRUNE),
            ("_M1_COMPUTE", AOC._in_scope_by_section, _M1_COMPUTE),
            ("_M2_NO_SECTION_GATE", AOP.prune_undeclared_rows, _M2_NO_SECTION_GATE),
            ("_M3_STRIP_SECTION", R3.section_value_of, _M3_STRIP_SECTION),
            ("_M4_REBUILD_FROM_READER", AOP.prune_undeclared_rows, _M4_REBUILD_FROM_READER),
        )
        misses: list[str] = []
        for group, func, anchors in anchor_sets:
            src = inspect.getsource(func)
            for old, _new in anchors:
                hits = src.count(old)
                if hits != 1:
                    misses.append(f"{group}/{func.__name__}: hits={hits} for {old!r}")
        assert not misses, "变异锚点命中数不为 1：\n  " + "\n  ".join(misses)
        # 变异对照：同一计数器对一条**已知不存在**的锚点必须报 0（否则它什么都没在数）
        assert inspect.getsource(AOP.prune_undeclared_rows).count("_aos_p2_absent_anchor_") == 0
