# -*- coding: utf-8 -*-
"""范围边界判据 —— Requirement 9 的六条「本 spec 不做什么」逐条可执行化。

spec: excel-workbook-wide-row-change-propagation / Wave 6 Task 26（X1 的范围边界部分）
Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6

═══ 为什么范围边界需要判据 ═══

Requirement 9 的 User Story 是「范围边界写进需求并各自说明理由，以便后续不因失焦把独立
劳动量并进来」。写进需求只防**立项时**失焦，防不住**实施中**悄悄扩张 —— 而后者才是
真实发生的形态：传播器已经在遍历全工作簿的引用了，顺手支持 reorder 或跨工作簿只差几行。

所以六条边界各自落成一条可复算判据。判据形态遵守本 spec 的纪律：

* **不用「字符不存在」**。「源码里没有 `reorder` 这个词」不是判据 —— 换个变量名就绿了，
  而且它反过来会因为注释里提一句就误红。判据落在**封闭词表的取值域**、**枚举成员集合**、
  **配置真源的值**、**磁盘字节摘要**这四类可复算量上。
* **带分母断言**。每条都先断言被检查的集合非空 —— 空集上「不含 X」恒真，那种判据永远
  绿且没人会发现它从未真正执行。

═══ 六条的落点 ═══

| AC | 边界 | 落点 |
|---|---|---|
| 9.1 | 不做行移动（reorder） | `RowChangeKind` 枚举成员恰 `{INSERT, DELETE}` |
| 9.2 | 不做列方向结构变更 | 同上（无 column kind）+ 计划字段无列位移量 |
| 9.3 | 不放宽 OOXML 安全策略 | `workpaper_sync_limits.json` 的 `ooxml_policy` 三个开关 |
| 9.4 | 不传播跨工作簿引用 | `external_workbook` ∈ `UNPROPAGATED_REASONS` 且 ∉ `PROPAGATION_CARRIERS` |
| 9.5 | 不传播图表与透视 | `chart` / `pivot` 同上 |
| 9.6 | 不改 `backend/wp_templates/` 任何字节 | N1 模块的 AST 里无该目录的写入调用 |

🔴 **9.6 刻意不做「跑一遍再比对目录哈希」**：那需要真实执行传播（Wave 5 未完成，且会写盘），
而本文件必须在门关着时也能跑。改为**结构判据** —— N1 的 AST 里不存在指向
`wp_templates` 的写入调用点。配一条反向自检：喂一份**确实**写模板目录的合成源，
检测器必须命中，否则这条判据分不清「确实没写」与「检测器根本没在看」。
"""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.excel_workbook_row_change import (  # noqa: E402
    PROPAGATION_CARRIERS,
    UNPROPAGATED_REASONS,
    RowChangeKind,
    WorkbookRowChangePlan,
)

#: N1 生产模块 —— 9.6 的结构判据在它的 AST 上跑。
_N1_SOURCE: Path = (
    _BACKEND / "app" / "services" / "workpaper_sync" / "excel_workbook_row_change.py"
)

#: OOXML 安全策略的配置真源。
_LIMITS_CONFIG: Path = _BACKEND / "data" / "workpaper_sync_limits.json"

#: 写盘原语 —— 9.6 检测器认这些方法名/函数名。
_WRITE_PRIMITIVES: frozenset[str] = frozenset(
    {"write_bytes", "write_text", "open", "replace", "copy", "copy2", "copyfile", "unlink", "rmtree"}
)

#: 模板目录的路径记号。出现在**同一个调用链**里才算命中。
_TEMPLATE_MARKERS: tuple[str, ...] = ("wp_templates",)


# ═══════════════════════════════════════════════════════════════════════════
# 9.1 / 9.2 —— 行变更只有插入与删除，没有 reorder、没有列方向
# ═══════════════════════════════════════════════════════════════════════════


def test_row_change_kind_is_exactly_insert_and_delete() -> None:
    """AC 9.1 / 9.2：`RowChangeKind` 的成员集合**恰好**是插入与删除。

    分母断言：成员数 >= 2（空枚举上「不含 reorder」恒真）。

    多一个成员就是范围扩张 —— reorder 的语义与留痕另论（9.1），列方向变更是另一套
    位移代数（9.2）。两者都不能靠「顺手加个枚举值」进来。
    """
    members = {member.name for member in RowChangeKind}
    assert len(members) >= 2, f"枚举成员过少，判据会在近空集上恒真：{members}"
    assert members == {"INSERT", "DELETE"}, (
        "AC 9.1 / 9.2：行变更词表被扩张了。reorder（行移动）与列方向结构变更都在本 spec "
        f"范围之外，实得成员 {sorted(members)}"
    )

    values = {member.value for member in RowChangeKind}
    assert values == {"insert", "delete"}, f"取值域被扩张：{sorted(values)}"


def test_no_column_direction_field_on_the_plan() -> None:
    """AC 9.2：计划的字段里没有列方向的位移量。

    判据落在 `dataclasses.fields` 而不是源码文本 —— 注释里提到「列」不算，
    真多出一个 `column_at` / `col_count` 之类的字段才算。
    """
    import dataclasses

    names = {f.name for f in dataclasses.fields(WorkbookRowChangePlan)}
    assert names, "计划无字段，判据会恒真"

    forbidden = {n for n in names if n.startswith(("column", "col_")) or n.endswith(("_column", "_col"))}
    assert not forbidden, (
        f"AC 9.2：计划上出现了列方向字段 {sorted(forbidden)} —— 列插删是另一套位移代数，"
        "不在本 spec 范围内"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 9.3 —— 不放宽 OOXML 安全策略
# ═══════════════════════════════════════════════════════════════════════════


def test_ooxml_policy_is_not_relaxed() -> None:
    """AC 9.3：外部关系许可与宏许可保持关闭。

    判据读**配置真源**（`workpaper_sync_limits.json`），不读运行时对象的默认值 ——
    真源被改了才是范围扩张，而运行时对象只是它的投影。
    """
    policy = json.loads(_LIMITS_CONFIG.read_text(encoding="utf-8"))["ooxml_policy"]

    assert policy, "ooxml_policy 为空，判据会恒真"
    assert policy["allow_external_relationships"] is False, (
        "AC 9.3：本 spec 不得放宽外部关系许可 —— 传播器会遍历全工作簿的引用，"
        "放开这个开关等于让它把外部目标也一起处理"
    )
    assert policy["allow_macros"] is False, "AC 9.3：宏许可不得放开"
    assert policy["external_relationship_target_mode"] == "External", (
        "AC 9.3：外部关系的 target mode 不得改动"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 9.4 / 9.5 —— 跨工作簿、图表、透视：登记而非传播
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "reason, ac",
    [
        ("external_workbook", "9.4"),
        ("chart", "9.5"),
        ("pivot", "9.5"),
    ],
)
def test_out_of_scope_kinds_are_registered_not_propagated(reason: str, ac: str) -> None:
    """AC 9.4 / 9.5：这三类必须在「未传播原因」词表里，且**不在**传播载体词表里。

    两侧都查才成立：只查前者，有人同时把它加进传播载体也照样绿；只查后者，
    则「静默跳过、不登记」也算通过 —— 而不登记会让「有多少处没被处理」不可见。
    """
    assert UNPROPAGATED_REASONS, "未传播原因词表为空，判据会恒真"
    assert PROPAGATION_CARRIERS, "传播载体词表为空，判据会恒真"

    assert reason in UNPROPAGATED_REASONS, (
        f"AC {ac}：{reason!r} 必须作为「未传播原因」被登记 —— 静默跳过会让"
        "「有多少处引用没被处理」这件事不可见"
    )
    assert reason not in PROPAGATION_CARRIERS, (
        f"AC {ac}：{reason!r} 出现在传播载体词表里 = 本 spec 开始传播它了，超出范围"
    )


def test_propagation_carriers_and_unpropagated_reasons_are_disjoint() -> None:
    """两个词表不得有交集 —— 一个形态不能既被传播又被登记为未传播。"""
    overlap = PROPAGATION_CARRIERS & UNPROPAGATED_REASONS
    assert not overlap, f"载体词表与未传播原因词表相交：{sorted(overlap)}"


# ═══════════════════════════════════════════════════════════════════════════
# 9.6 —— 不改 backend/wp_templates/ 任何字节
# ═══════════════════════════════════════════════════════════════════════════


def _template_tainted_names(tree: ast.AST) -> set[str]:
    """绑定过「含模板目录记号的表达式」的局部变量名集合（一层传播闭包）。

    🔴 **这个函数是反向自检逼出来的。** 首版检测器只看单个 `ast.Call` 子树里是否同时出现
    模板记号与写盘原语，于是

        target = Path('backend/wp_templates')
        (target / 'D2.xlsx').write_bytes(data)

    这种**经变量传递**的写入被漏掉 —— `write_bytes` 那个调用的子树里只有 `target`，
    没有 `wp_templates` 字面量。反向自检当场打红（`assert []`），据此补上变量绑定追踪。
    留这段注释是因为：漏掉的正是**真实代码最可能长成的样子**（谁都会先把目录存进变量）。
    """
    tainted: set[str] = set()
    # 迭代到不动点：`a = Path('…wp_templates'); b = a; b.write_bytes(…)` 也要追到
    for _ in range(4):  # 4 层足够，且避免病态源码上死循环
        grew = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if value is None:
                continue
            dumped = ast.dump(value)
            hit = any(marker in dumped for marker in _TEMPLATE_MARKERS) or any(
                isinstance(sub, ast.Name) and sub.id in tainted
                for sub in ast.walk(value)
            )
            if not hit:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name) and sub.id not in tainted:
                        tainted.add(sub.id)
                        grew = True
        if not grew:
            break
    return tainted


def template_write_callsites(source: str) -> list[str]:
    """返回「同一调用链里既指向模板目录、又调用写盘原语」的调用点描述。

    判据形态说明：查的是 **AST 调用节点**，命中条件二者之一：

    1. 该 `ast.Call` 的可达子树里直接出现模板目录记号（字面量直连）；
    2. 子树里出现**被模板路径污染过**的变量名（见 :func:`_template_tainted_names`）。

    比「两者分别 grep」强：源码里同时出现 `wp_templates`（比如注释说明「不改模板」）
    与别处的 `write_bytes` 不会误报 —— 见 `only_mentioned` 那条反向自检。
    """
    tree = ast.parse(source)
    tainted = _template_tainted_names(tree)
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name not in _WRITE_PRIMITIVES:
            continue
        dumped = ast.dump(node)
        direct = any(marker in dumped for marker in _TEMPLATE_MARKERS)
        via_var = any(
            isinstance(sub, ast.Name) and sub.id in tainted for sub in ast.walk(node)
        )
        if direct or via_var:
            how = "字面量直连" if direct else "经变量传递"
            hits.append(f"L{getattr(node, 'lineno', '?')}: {name}(...) 触及模板目录（{how}）")
    return hits


def test_no_template_directory_write_in_production_module() -> None:
    """AC 9.6：N1 生产模块里不存在指向 `backend/wp_templates/` 的写入调用。

    结构判据而非「跑一遍比对目录哈希」：后者要求真实执行传播（Wave 5 未完成且会写盘），
    而本判据必须在上游门关着时也能跑。
    """
    source = _N1_SOURCE.read_text(encoding="utf-8")
    assert source.strip(), "N1 源为空，判据会恒真"

    hits = template_write_callsites(source)
    assert not hits, (
        "AC 9.6：N1 里出现了对模板目录的写入调用 —— 权威模板是只读的：\n  "
        + "\n  ".join(hits)
    )


def test_boundary_equality_assertions_are_not_downgraded_to_subset() -> None:
    """🔴 元判据：范围边界的**等值**断言不得被悄悄降级成子集断言。

    ═══ 为什么需要它 ═══

    `test_row_change_kind_is_exactly_insert_and_delete` 的承重点是 `==` 那个运算符：
    把它改成 `>=`（`assert members >= {"INSERT", "DELETE"}`）之后，有人往 `RowChangeKind`
    加 `REORDER` 也不会红 —— 而**真实枚举今天仍只有两个成员，所以没有任何测试能观察到
    这次降级**。X1 的变异检验实测过：那条变异判 GREEN，不是因为守卫有缺陷，而是因为
    「判据自身的运算符被改弱」这件事只能由**读自身 AST** 的元判据来锁。

    这条也是「判据必须落在结构而不是字符」的一个实例：它断言的不是源码里有没有 `==`
    这两个字符，而是那条 `assert` 的比较节点类型是 `ast.Eq`。
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))

    target_fn = "test_row_change_kind_is_exactly_insert_and_delete"
    fn = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == target_fn
        ),
        None,
    )
    assert fn is not None, f"{target_fn} 不存在 —— 元判据失去对象，会在空集上恒真"

    # 找形如 `assert <something> == {...}` 的比较，且右侧是含 INSERT / DELETE 的集合
    equality_ops: list[type[ast.cmpop]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            continue
        rendered = ast.dump(test.comparators[0])
        if "INSERT" in rendered and "DELETE" in rendered:
            equality_ops.append(type(test.ops[0]))

    assert equality_ops, (
        f"{target_fn} 里找不到「与 {{INSERT, DELETE}} 比较」的断言 —— "
        "词表判据可能被删或改写，元判据已失去落点"
    )
    downgraded = [op.__name__ for op in equality_ops if not isinstance(op(), ast.Eq)]
    assert not downgraded, (
        f"AC 9.1 / 9.2 的词表判据被降级成 {downgraded}（应为 Eq）—— "
        "子集断言放行「多一个成员」，范围边界即失效。真实枚举仍只有两个成员时，"
        "这次降级不会被任何常规判据观察到，所以必须由本元判据锁住"
    )


def test_template_write_detector_fires_on_synthetic_violation() -> None:
    """🔴 反向自检：喂一份**确实**写模板目录的合成源，检测器必须命中。

    没有这条，上面那条判据在「确实没写」与「检测器根本没在看」之间无法区分 ——
    那正是本平台记录的假绿第②源。
    """
    violating = (
        "from pathlib import Path\n"
        "def _oops(data):\n"
        "    Path('backend/wp_templates/D2.xlsx').write_bytes(data)\n"
    )
    assert template_write_callsites(violating), "检测器漏报了真实的模板目录写入"

    # 变量承载路径的形态也要认出来（不能只认字面量紧邻的情形）
    via_variable = (
        "from pathlib import Path\n"
        "def _oops(data):\n"
        "    target = Path('backend/wp_templates')\n"
        "    (target / 'D2.xlsx').write_bytes(data)\n"
    )
    assert template_write_callsites(via_variable), (
        "检测器只认字面量直连的情形 —— 经变量传递的模板路径写入会漏掉"
    )

    # 只在注释/字符串里提到模板目录、并不写它 ⇒ 不得误报
    only_mentioned = (
        "from pathlib import Path\n"
        "def _fine(data, out):\n"
        '    """本函数不改 backend/wp_templates 的任何字节。"""\n'
        "    Path(out).write_bytes(data)\n"
    )
    assert not template_write_callsites(only_mentioned), (
        "检测器把「注释里提到模板目录」误判成写入 —— 已退化成字符串匹配"
    )
