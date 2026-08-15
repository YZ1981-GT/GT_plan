"""变异应用、备份与还原（`finally` + md5 逐字核验）。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Requirements: 6.1 · Property 20

## 还原的三条硬约束

1. **写在 `finally`** —— 任何异常都不能留下污染文件，否则后续变异全变 WRONG-TEST
2. **md5 逐字核验** —— 不信「写回成功」。`write_text` 在 Windows 上会把 LF 写成 CRLF，
   内容对而 md5 不符（本 spec Wave 1 实测踩过），故全程 bytes 读写并比对
3. **运行前扫残留** —— 上一轮被 `^C` 中断可能留下 `.mutbak`，此时基线已被污染
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .anchor import (
    AnchorMiss,
    eol_of,
    find_anchor,
    md5_bytes,
    read_lines,
    write_lines,
    block_range,
)
from .spec import Mutation

BAK_SUFFIX = ".mutbak"


def apply_mutation(m: Mutation, repo: Path) -> None:
    """把一条变异写进目标文件。定位失败抛 :class:`AnchorMiss`（不落盘）。"""
    target = m.abspath(repo)
    lines = read_lines(target)

    if m.kind == "replace":
        i = find_anchor(lines, m.anchor, m.line)
        lines[i] = m.new + eol_of(lines[i])
    elif m.kind == "delete":
        i = find_anchor(lines, m.anchor, m.line)
        del lines[i]
    elif m.kind == "insert":
        i = find_anchor(lines, m.anchor, m.line)
        eol = eol_of(lines[i]) or "\n"
        payload = [s + eol for s in m.new.rstrip("\n").split("\n")]
        lines[i + 1 : i + 1] = payload
    elif m.kind in ("swap", "move"):
        ia = find_anchor(lines, m.anchor, m.line)
        ib = find_anchor(lines, m.anchor2)
        a0, a1 = block_range(lines, ia, m.block_open)
        b0, b1 = block_range(lines, ib, m.block_open)
        if a0 == b0:
            raise AnchorMiss("两个锚点落在同一块内")
        blk_a, blk_b = lines[a0:a1], lines[b0:b1]
        if m.kind == "swap":
            if a0 < b0:
                lines = lines[:a0] + blk_b + lines[a1:b0] + blk_a + lines[b1:]
            else:
                lines = lines[:b0] + blk_a + lines[b1:a0] + blk_b + lines[a1:]
        else:  # move：blk_a 挪到 blk_b 之后
            if a0 < b0:
                lines = lines[:a0] + lines[a1:b1] + blk_a + lines[b1:]
            else:
                lines = lines[:b0] + blk_b + blk_a + lines[b1:a0] + lines[a1:]
    else:
        raise AnchorMiss(f"未知 kind：{m.kind}")

    write_lines(target, lines)


def stale_backups(repo: Path) -> list[Path]:
    """残留备份文件（上一轮被中断的痕迹）。"""
    return sorted(repo.rglob(f"*{BAK_SUFFIX}"))


def restore_all(repo: Path, verbose: bool = True) -> int:
    """还原全部 `.mutbak`，返回还原数。"""
    n = 0
    for bak in stale_backups(repo):
        target = Path(str(bak)[: -len(BAK_SUFFIX)])
        target.write_bytes(bak.read_bytes())
        bak.unlink()
        n += 1
        if verbose:
            try:
                shown = target.relative_to(repo)
            except ValueError:
                shown = target
            print(f"[RESTORE] {shown}")
    return n


class RestoreFailed(RuntimeError):
    """还原后 md5 与变异前不符 —— 必须中止全部后续变异。"""


@contextmanager
def mutated(m: Mutation, repo: Path) -> Iterator[bytes]:
    """在上下文内使目标文件处于变异态，退出时无条件还原并核验 md5。

    yield 出**变异后的文件字节**，供调用方做作用域自证（:attr:`Mutation.scope_check`）。

    ``AnchorMiss`` 在 apply 阶段抛出时，备份仍会被清理 —— 因为此时文件未被改动
    （:func:`apply_mutation` 定位失败即抛，不落盘）。
    """
    target = m.abspath(repo)
    bak = Path(str(target) + BAK_SUFFIX)
    before = target.read_bytes()
    bak.write_bytes(before)
    try:
        apply_mutation(m, repo)
        after = target.read_bytes()
        if md5_bytes(after) == md5_bytes(before):
            raise AnchorMiss("变异后 md5 未变 —— 改动未落盘（无效变异）")
        yield after
    finally:
        target.write_bytes(bak.read_bytes())
        bak.unlink()
        if md5_bytes(target.read_bytes()) != md5_bytes(before):
            raise RestoreFailed(
                f"{m.id} 还原后 md5 不符：{md5_bytes(target.read_bytes())} "
                f"!= {md5_bytes(before)}（目标 {m.path}）"
            )
