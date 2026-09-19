"""锚点定位与文件字节读写（CRLF 安全）。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Requirements: 6.1 · Property 20

## 四重断言

:func:`find_anchor` 不是「找到第一处」，而是四条同时成立才返回：

1. 锚点**不含换行** —— 工作树是 CRLF，跨行锚点必然 MISS
2. 匹配是**整行相等**（去行尾后逐字），不是子串包含 —— 子串会把缩进不同的相邻行算进来
   （本 spec Wave 1 实测：`strip()` 后匹配把 6 空格与 4 空格两行合成 HITS=2）
3. 命中数**恰好 1**（未给消歧行号时）
4. 给了消歧行号时，该行内容**逐字等于**锚点

## 为什么读写走 bytes

`Path.read_text()` 默认 universal newlines 会把 `\\r\\n` 读成 `\\n`，`write_text()` 又按
`os.linesep` 写回 —— 于是「内容没变但 md5 变了」。本 spec Wave 1 的临时脚本正是这样
让还原核验失败的。故一律 `read_bytes().decode("utf-8")` +
`splitlines(keepends=True)`，写回 `encode("utf-8")`。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


class AnchorMiss(RuntimeError):
    """锚点无法唯一定位，或变异未落在预期作用域 —— **脚本缺陷**，不是生产代码问题。

    与 GREEN（守卫缺陷）严格区分：把 ANCHOR-MISS 当成 GREEN 会得出
    「守卫没拦住」的错误结论，实际是变异根本没打到目标。
    """


def md5_of(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def read_lines(path: Path) -> list[str]:
    """按字节读入并保留行尾（CRLF 原样）。"""
    return path.read_bytes().decode("utf-8").splitlines(keepends=True)


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_bytes("".join(lines).encode("utf-8"))


def eol_of(line: str) -> str:
    for e in ("\r\n", "\n", "\r"):
        if line.endswith(e):
            return e
    return ""


def strip_eol(line: str) -> str:
    e = eol_of(line)
    return line[: len(line) - len(e)] if e else line


def find_anchor(
    lines: list[str],
    anchor: str,
    want_line: int = 0,
    scope: str = "",
    offset: int = 0,
) -> int:
    """返回锚点行下标（0-based）。四重断言任一不成立即抛 :class:`AnchorMiss`。

    三种消歧方式，优先级 scope > want_line > 唯一命中：

    - ``scope`` **相对定位**：`scope` 必须唯一命中，取 `scope_idx + offset` 那行并
      验证它逐字等于 `anchor`。比绝对行号稳 —— 文件上下增删行不影响它。
    - ``want_line`` 绝对行号（1-based），该行必须逐字等于 `anchor`
    - 都不给时要求 `anchor` 在全文唯一命中
    """
    if "\n" in anchor or "\r" in anchor:
        raise AnchorMiss("锚点含换行 —— CRLF 工作树下必然 MISS，改用单行锚点")

    if scope:
        if "\n" in scope or "\r" in scope:
            raise AnchorMiss("scope 含换行 —— 同 anchor，必须单行")
        shits = [i for i, ln in enumerate(lines) if strip_eol(ln) == scope]
        if len(shits) != 1:
            raise AnchorMiss(
                f"scope 命中 {len(shits)} 次（应为 1），行号："
                f"{'; '.join(str(h + 1) for h in shits[:8]) or '无'}\n  {scope!r}"
            )
        idx = shits[0] + offset
        if not (0 <= idx < len(lines)):
            raise AnchorMiss(
                f"scope+offset 越界：scope 在 L{shits[0] + 1}，offset={offset}，"
                f"文件 {len(lines)} 行"
            )
        if strip_eol(lines[idx]) != anchor:
            raise AnchorMiss(
                f"scope+offset 指向的 L{idx + 1} 不是 anchor\n"
                f"  期望 {anchor!r}\n  实为 {strip_eol(lines[idx])!r}"
            )
        return idx

    hits = [i for i, ln in enumerate(lines) if strip_eol(ln) == anchor]
    if want_line:
        idx = want_line - 1
        if not (0 <= idx < len(lines)):
            raise AnchorMiss(f"消歧行号 {want_line} 越界（文件 {len(lines)} 行）")
        if strip_eol(lines[idx]) != anchor:
            raise AnchorMiss(
                f"消歧行号 {want_line} 内容不符\n"
                f"  期望 {anchor!r}\n  实为 {strip_eol(lines[idx])!r}"
            )
        return idx
    if len(hits) != 1:
        preview = "; ".join(str(h + 1) for h in hits[:8])
        raise AnchorMiss(
            f"锚点命中 {len(hits)} 次（应为 1），行号：{preview or '无'}\n  {anchor!r}"
        )
    return hits[0]


_STR_RE = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"|\'[^\'\\]*(?:\\.[^\'\\]*)*\'')


def _paren_delta(line: str) -> int:
    """一行的圆括号净增量。**先剥字符串** —— `source_ref="…(国企)…"` 会骗到计数。"""
    bare = _STR_RE.sub('""', strip_eol(line))
    return bare.count("(") - bare.count(")")


def block_range(lines: list[str], anchor_idx: int, block_open: str) -> tuple[int, int]:
    """由块内锚点行反查整块行区间 ``[start, end)``（含尾随逗号行）。

    用括号配对而非固定行数窗口：固定窗口在块内新增一行后就会切错。
    """
    start = -1
    for i in range(anchor_idx, -1, -1):
        if block_open in lines[i]:
            start = i
            break
    if start < 0:
        raise AnchorMiss(f"锚点上方未找到块首标记 {block_open!r}")
    depth = 0
    for i in range(start, len(lines)):
        depth += _paren_delta(lines[i])
        if depth <= 0:
            return start, i + 1
    raise AnchorMiss("块括号未闭合 —— 计数被字符串或注释干扰")
