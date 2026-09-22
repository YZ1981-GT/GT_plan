"""room 序号字段（`latest_request_sequence` / `latest_durable_sequence`）的归属守卫。

不变量：**room fence 的序号只由 repository 在 room row lock 内算一次**，服务层
（`app/services/workpaper_sync/rooms.py`）不得成为第二处推进点。
`rooms.py` 模块 docstring 自己把这条禁令写成「本模块**故意不提供** `next_request_sequence()`」，
`RoomService._advance_canonical_fence_locked` 的 docstring 写成「那三行**算术**委派给
`repo.advance_room_durable_fence()`」—— 要守的一直是「算 / 推进」，不是「读」。

🔴 2026-09-22 从 `test_task21_room_service.py` 抽出并同时**收窄 + 扩面**判据。原判据是
「剥注释/字符串后，`rooms.py` 正文里不得出现子串 `latest_request_sequence`」，两个毛病：

1. **过宽**：把「只读观测」和「第二处推进」混为一谈。新增的纯判据 `room_never_took_custody`
   要回答「这一代是否从未接管过内容」，而「从未发起过任何 request」的唯一可观测事实就是
   `latest_request_sequence == 0` —— 一次比较，既不赋值也不做算术。旁证：兄弟字段
   `latest_durable_sequence` 本来就被服务层读着建 `CanonicalFenceAdvance` 快照，
   从未有人认为那违反本不变量。
2. **过窄**：只盯一个字段。`latest_durable_sequence` 同属 repository 独占推进的 room fence，
   此前**一条守卫都没有** —— 服务层写一行 `room.latest_durable_sequence = n` 不会有任何测试发现。

收窄后判据直接对齐不变量：**写 / 算术 / 字符串动态写一律禁止**，只读仅限逐字段登记的
`_SEQUENCE_READ_ALLOWLIST`（fail-closed：新函数想读必须显式登记并写明理由，
这样「服务层到底有几处在看序号」在复审时一眼可见）。

抽成独立文件的另一个理由：`test_task21_room_service.py` 已在文件行数 whitelist 基线上，
本守卫自带 AST 助手约 130 行，继续塞进去会撞「打磨应让文件变小不变大」的门禁。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import ClassVar, Final

import pytest

from app.services.workpaper_sync import rooms as rooms_mod

_ROOMS_PATH: Final[Path] = Path(rooms_mod.__file__)

#: 允许**只读**观测 room 序号字段的函数白名单（逐字段登记，默认空 = 谁都不许读）。
_SEQUENCE_READ_ALLOWLIST: Final[dict[str, frozenset[str]]] = {
    # `room_never_took_custody`：判定「这一代是否从未接管过内容」，其可观测事实之一就是
    # 「从未发起过任何 request」= `latest_request_sequence == 0`。只比较不赋值。
    "latest_request_sequence": frozenset({"room_never_took_custody"}),
    # 同上；另加 `_advance_canonical_fence_locked` —— 它在 repository 推完 fence 之后把结果
    # 读进 `CanonicalFenceAdvance` 快照返回给调用方（读的是既成事实，不参与推进）。
    "latest_durable_sequence": frozenset(
        {"room_never_took_custody", "_advance_canonical_fence_locked"}
    ),
}


def room_field_usages(code: str, field: str) -> list[tuple[str, str]]:
    """`rooms.py` 里对某个 room 序号字段的全部用法，按 `(所在函数, 用法种类)` 归类。

    用法种类：

    - ``write``   —— 出现在赋值/增量赋值/注解赋值的**目标**位置（`room.x = ...` / `room.x += 1`）。
    - ``arith``   —— 参与算术（`room.x + 1`），即「在这里算下一个序号」。
    - ``dynamic`` —— 字段名以**字符串**形态出现在调用实参或 dict 键里
      （`setattr(room, "x", ...)` / `.values(**{"x": ...})`），即绕过属性语法的写路径。
    - ``read``    —— 其余只读取值（比较、`int(...)`、传给 dataclass 作快照）。

    只看**属性**形态（`ast.Attribute.attr`）与上述字符串形态，因此 docstring/注释里提到字段名
    不会被算成用法 —— 这一点与旧判据（剥字符串后做子串匹配）有意不同：旧判据把「提到」和
    「动手」混为一谈。
    """
    tree = ast.parse(code)
    usages: list[tuple[str, str]] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.fn = "<module>"

        def _record_write_targets(self, node: ast.AST) -> None:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute) and sub.attr == field:
                    usages.append((self.fn, "write"))

        def _in_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            previous, self.fn = self.fn, node.name
            self.generic_visit(node)
            self.fn = previous

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._in_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._in_function(node)

        def visit_Assign(self, node: ast.Assign) -> None:
            for target in node.targets:
                self._record_write_targets(target)
            self.generic_visit(node)

        def visit_AugAssign(self, node: ast.AugAssign) -> None:
            self._record_write_targets(node.target)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            self._record_write_targets(node.target)
            self.generic_visit(node)

        def visit_BinOp(self, node: ast.BinOp) -> None:
            for side in (node.left, node.right):
                if isinstance(side, ast.Attribute) and side.attr == field:
                    usages.append((self.fn, "arith"))
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            for arg in [*node.args, *(kw.value for kw in node.keywords)]:
                if isinstance(arg, ast.Constant) and arg.value == field:
                    usages.append((self.fn, "dynamic"))
            self.generic_visit(node)

        def visit_Dict(self, node: ast.Dict) -> None:
            for key in node.keys:
                if isinstance(key, ast.Constant) and key.value == field:
                    usages.append((self.fn, "dynamic"))
            self.generic_visit(node)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if node.attr == field:
                usages.append((self.fn, "read"))
            self.generic_visit(node)

    _Visitor().visit(tree)
    return usages


class TestRoomSequenceStaysRepositoryOwned:
    """两个字段同判据：禁写/禁算术/禁动态写，只读须登记。"""

    fields: ClassVar[tuple[str, ...]] = (
        "latest_request_sequence",
        "latest_durable_sequence",
    )

    @pytest.mark.parametrize("field", fields)
    def test_service_layer_never_advances_the_sequence(self, field: str) -> None:
        """变异反证：在 `RoomService` 任一方法里加 `room.latest_request_sequence = 1`（write）
        或 `room.latest_durable_sequence + 1`（arith），本用例立刻打红（2026-09-22 已实跑两种注入）。
        """
        usages = room_field_usages(_ROOMS_PATH.read_text(encoding="utf-8"), field)
        mutations = [(fn, kind) for fn, kind in usages if kind != "read"]
        assert not mutations, (
            f"服务层出现了第二处 {field} 推进（写/算术/动态写）：{sorted(set(mutations))} —— "
            "room fence 只认 repository 那一份"
        )

    @pytest.mark.parametrize("field", fields)
    def test_only_registered_functions_may_read_the_sequence(self, field: str) -> None:
        """白名单是 fail-closed 的：未登记的函数读了就红，迫使新增读点写明理由。"""
        usages = room_field_usages(_ROOMS_PATH.read_text(encoding="utf-8"), field)
        allowed = _SEQUENCE_READ_ALLOWLIST.get(field, frozenset())
        unexpected = sorted(
            {fn for fn, kind in usages if kind == "read" and fn not in allowed}
        )
        assert not unexpected, (
            f"这些函数未登记就读 {field}：{unexpected}。只读也要显式登记进 "
            "_SEQUENCE_READ_ALLOWLIST 并写明理由，否则「服务层有几处在看序号」会失控"
        )

    def test_the_allowlist_is_not_silently_empty(self) -> None:
        """防守卫自身退化：白名单若被清空，上一条会因「没有任何读点」而空过。

        这里锁死「登记的读点确实存在于源码里」—— 白名单不是可以随手删空的装饰。
        """
        for field, allowed in _SEQUENCE_READ_ALLOWLIST.items():
            assert allowed, f"{field} 的只读白名单为空，等于放弃本守卫"
            readers = {
                fn
                for fn, kind in room_field_usages(
                    _ROOMS_PATH.read_text(encoding="utf-8"), field
                )
                if kind == "read"
            }
            assert readers == set(allowed), (
                f"{field} 的白名单与源码实际读点不一致：登记 {sorted(allowed)}、"
                f"实际 {sorted(readers)}。登记项消失说明代码被改过而白名单没跟上"
            )
