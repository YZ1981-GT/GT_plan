"""变异声明与**声明期校验**。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Requirements: 6.1 · Property 20

## 为什么校验要放在声明期

平台已有 17 个变异脚本 / 9657 行，其中约三分之二是互相抄来的样板。抄漏哪一项就是
一个假绿入口，而**光把约束写在文档里不管用** —— 本 spec 的 design.md 明文写着
「anchor 非空且不含 `\\n`」，作者（就是写这份 design 的人）在 Wave 2 做变异检验时
仍然写出了多行锚点，在 CRLF 工作树下报了两条 ANCHOR-MISS。

结论：约束必须在**构造 `Mutation` 的那一刻**就拒绝，而不是等运行到定位阶段才发现。
:func:`validate_all` 由 :func:`_mutation_kit.cli.run_cli` 在任何子命令之前无条件调用。

## 三类校验

1. **字段完整性** —— kind 合法、anchor/want/why/path 非空、按 kind 补齐必需字段
2. **锚点形态** —— 不含换行（CRLF 必 MISS）、不是纯空白、`new` 与 `anchor` 不同
3. **声明一致性** —— id 唯一（重复 id 会让 `--run M01` 只跑到第一条）
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

#: 支持的变异种类。
#:
#: - ``replace`` 单行整行替换（``anchor`` 是去掉行尾后的整行文本）
#: - ``delete``  删除单行
#: - ``insert``  在锚点行**之后**插入 ``new``（可多行）
#: - ``swap``    交换 ``anchor`` 与 ``anchor2`` 各自所属的括号块
#: - ``move``    把 ``anchor`` 所属块移到 ``anchor2`` 所属块**之后**
KINDS = ("replace", "delete", "insert", "swap", "move")

#: 执行侧。``be`` 走 pytest，``fe`` 走 vitest。
SIDES = ("be", "fe")


@dataclass
class Mutation:
    """一条变异声明。

    :param id: 变异编号，同一脚本内唯一
    :param side: ``be`` | ``fe``
    :param path: 仓库相对路径（POSIX 风格，`/` 分隔）
    :param kind: 见 :data:`KINDS`
    :param anchor: **行级唯一且不含换行**的整行文本（去掉行尾）
    :param want: 期望打红的测试名（后端按 nodeid 匹配，前端按标题子串匹配）
    :param why: 为什么这条变异有效 —— 必填，用于防「无效变异」
    :param new: 替换/插入内容（``replace``/``insert`` 必填）
    :param anchor2: 第二锚点（``swap``/``move`` 必填）
    :param line: 1-based 行号，仅当 ``anchor`` 多处命中时用于消歧
    :param block_open: 块首标记（``swap``/``move`` 必填）
    :param tags: 自由标签，用于 ``--run`` 的分组筛选
    :param scope_check: 可选的**作用域自证**回调，见下
    """

    id: str
    side: str
    path: str
    kind: str
    anchor: str
    want: str
    why: str
    new: str = ""
    anchor2: str = ""
    line: int = 0
    block_open: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    #: 多目标期望：任一命中即判 RED。与 :attr:`want` 二选一（都给则并集）。
    #:
    #: 迁移 `mutate_trim_decision_guards`（`expect_red: tuple`）与
    #: `mutate_note_conversion_section_mapping_guards`（`expect_tests: list`）时补的能力 ——
    #: 一条变异常常同时打红多条判据，只允许单目标会逼作者挑一条写、丢掉其余信息。
    wants: tuple[str, ...] = field(default_factory=tuple)
    #: **相对定位**：`anchor` 多处命中时，先用 `scope` 锚定附近一个唯一行，
    #: 再取 `scope_idx + offset` 那行并验证它逐字等于 `anchor`。
    #:
    #: 🔴 比 :attr:`line`（绝对行号）更稳：绝对行号一改文件就失效 ——
    #: 本 spec Wave 3 的 M12 就是写了 `line=155` 而那行早已是别的内容
    #: （`--list` 校验当场拦住）。迁移 `mutate_trim_decision_guards` 时把它的
    #: `scope`+`offset` 机制吸收进来。与 :attr:`line` 互斥。
    scope: str = ""
    #: 相对 `scope` 命中行的偏移（可负）。仅当 `scope` 非空时生效。
    offset: int = 0
    #: 变异写盘后立刻调用，入参是变异后的**文件字节**，返回 False 即判 ANCHOR-MISS。
    #:
    #: 🔴 存在的理由（2026-08-15 实测）：四态判定式「新增失败集合是否为空」
    #: **识别不出「锚点落在被测判据的作用域之外」**。本 spec Wave 1 的一条变异把
    #: 豁免表顶部 ``_schema.reason``（一段文档说明）改短了，而被测校验只覆盖
    #: ``exemptions[]`` 内的项 ⇒ 判定报 GREEN（守卫缺陷），实为脚本缺陷。
    #: 调用方用它断言「改动确实落在我关心的结构里」，例如解析 JSON 后检查目标字段。
    scope_check: Callable[[bytes], bool] | None = None

    def abspath(self, repo: Path) -> Path:
        return repo / self.path


def validate_mutation(m: Mutation) -> list[str]:
    """单条声明校验，返回问题列表（空列表 = 合规）。"""
    errs: list[str] = []
    if not m.id:
        errs.append("id 为空")
    if m.side not in SIDES:
        errs.append(f"side={m.side!r} 非法（应为 {SIDES}）")
    if m.kind not in KINDS:
        errs.append(f"kind={m.kind!r} 非法（应为 {KINDS}）")
    if not m.path:
        errs.append("path 为空")
    elif "\\" in m.path:
        errs.append(f"path 应用 POSIX 分隔符：{m.path!r}")

    if not m.anchor:
        errs.append("anchor 为空")
    else:
        if "\n" in m.anchor or "\r" in m.anchor:
            errs.append(
                "anchor 含换行 —— 工作树是 CRLF，跨行锚点在字节/整行匹配下必然 MISS，"
                "改用单行锚点（本 spec Wave 2 实测踩过两次）"
            )
        if not m.anchor.strip():
            errs.append("anchor 是纯空白 —— 无法唯一定位")
        if m.anchor != m.anchor.rstrip("\n\r"):
            errs.append("anchor 带行尾字符 —— 应传去掉行尾后的整行文本")

    if not m.want and not m.wants:
        errs.append("want / wants 都为空 —— 无期望打红的测试则无法判 RED/WRONG-TEST")
    if m.wants and any(not w for w in m.wants):
        errs.append("wants 里有空串 —— 空模式会匹配任何失败名，等于放弃判据")
    if not m.why or len(m.why) < 8:
        errs.append("why 缺失或过短 —— 必须写明为什么这条变异不是无效变异")

    if m.scope:
        if "\n" in m.scope or "\r" in m.scope:
            errs.append("scope 含换行 —— 同 anchor，必须单行")
        if not m.scope.strip():
            errs.append("scope 是纯空白 —— 无法唯一定位")
        if m.line:
            errs.append(
                "scope 与 line 互斥：前者是相对定位（scope 行 + offset），"
                "后者是绝对行号，同时给会让消歧依据不明确"
            )
        if m.scope == m.anchor and m.offset == 0:
            errs.append("scope 等于 anchor 且 offset=0 —— 相对定位退化成无效消歧")
    elif m.offset:
        errs.append("offset 非 0 但未给 scope —— offset 只在相对定位下生效")

    if m.kind in ("replace", "insert"):
        if not m.new:
            errs.append(f"kind={m.kind} 必须给 new")
        elif m.kind == "replace" and m.new == m.anchor:
            errs.append("replace 的 new 与 anchor 相同 = 无效变异（改动不落盘）")
        elif m.kind == "insert" and ("\n" in m.anchor):
            errs.append("insert 的 anchor 仍须单行（new 可多行）")
    if m.kind in ("swap", "move"):
        if not m.anchor2:
            errs.append(f"kind={m.kind} 必须给 anchor2")
        elif "\n" in m.anchor2 or "\r" in m.anchor2:
            errs.append("anchor2 含换行 —— 同 anchor，必须单行")
        if not m.block_open:
            errs.append(f"kind={m.kind} 必须给 block_open（块首标记）")
        if m.anchor2 == m.anchor:
            errs.append("anchor2 与 anchor 相同 —— 两个锚点会落在同一块内")
    if m.kind == "delete" and m.new:
        errs.append("delete 不应给 new（会被忽略，易误以为生效）")
    if m.line < 0:
        errs.append(f"line={m.line} 非法（0 表示不消歧，其余须为 1-based 正整数）")
    return errs


def validate_all(mutations: list[Mutation]) -> list[str]:
    """全量声明校验（含 id 唯一性），返回带 id 前缀的问题列表。"""
    problems: list[str] = []
    if not mutations:
        problems.append("变异清单为空 —— 空清单会让全部子命令恒成功（假绿）")
        return problems

    seen: dict[str, int] = {}
    for m in mutations:
        seen[m.id] = seen.get(m.id, 0) + 1
    for mid, cnt in sorted(seen.items()):
        if cnt > 1:
            problems.append(f"{mid}: id 重复 {cnt} 次 —— `--run {mid}` 只会跑到第一条")

    for m in mutations:
        for e in validate_mutation(m):
            problems.append(f"{m.id or '<无 id>'}: {e}")
    return problems
