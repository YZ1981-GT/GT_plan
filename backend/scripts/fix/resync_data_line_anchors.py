"""把 ``backend/data`` 里 JSON 数据文件的 ``路径#L行号`` 锚点，按「基准版本 → 工作区」的行对应关系平移。

用法（在仓库根目录）::

    python backend/scripts/fix/resync_data_line_anchors.py --base HEAD --check
    python backend/scripts/fix/resync_data_line_anchors.py --base HEAD --apply [--only <源文件> ...]

为什么需要：底稿同步各循环的 slice / 删除计划把取证点记成 ``文件#L行号``，判据按行回源
（如 M 循环 ``useM9FormData.ts#L12`` 那一行必须是 ``const ITEM_PREFIX = 'M9-'``）。改前端时
只要在锚点上方增删一行，几十个锚点就整体错位；手改会漏会错（G 循环专用工具
``resync_g_slice_source_refs.py`` 的 docstring 记过同样的教训）。

口径：锚点在 ``--base`` 版本里是对的（改动之前），本工具只做**行对应**——用 difflib 对比
该源文件在 ``--base`` 与工作区的两版，锚点落在未改动的行上就平移到新行号；落在被改写 /
删除的行上不猜，列为「无法平移」交给人判断（``--check`` 与 ``--apply`` 都会列出并以 1 退出）。
只改锚点字符串本身，不重排 JSON（文本替换，一次扫描完成，不会出现 L100→L101→L102 连环改写）。

``--only``：只平移指向这些源文件的锚点（多人同时改前端时，只处理自己改动造成的移位）。
"""
from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = "backend/data"
ANCHOR = re.compile(r'"((?:audit-platform|backend)/[^"\s#]+)#L(\d+)"')


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)


def _base_lines(base: str, path: str) -> list[str] | None:
    r = _git("show", f"{base}:{path}")
    return r.stdout.decode("utf-8").replace("\r\n", "\n").split("\n") if r.returncode == 0 else None


def _line_map(old: list[str], new: list[str]) -> dict[int, int]:
    """旧行号 → 新行号（1-based），只含未改动的行。"""
    out: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                out[i1 + k + 1] = j1 + k + 1
    return out


def apply_moves(text: str, table: dict[str, str]) -> str:
    """一次扫描替换锚点（``table``：带引号的旧锚点 → 新锚点）；不会出现 L100→L101→L102 的连环改写。"""
    return ANCHOR.sub(lambda m: table.get(m.group(0), m.group(0)), text)


def plan(base: str, only: set[str] | None) -> tuple[dict[str, dict[str, str]], list[str]]:
    """返回 ``({数据文件: {旧锚点: 新锚点}}, [无法平移的说明])``。"""
    tracked = _git("ls-files", DATA).stdout.decode("utf-8").split("\n")
    maps: dict[str, dict[int, int] | None] = {}
    moves: dict[str, dict[str, str]] = {}
    stuck: list[str] = []
    for rel in (p for p in tracked if p.endswith(".json")):
        if not (ROOT / rel).is_file():  # 已跟踪但工作区里删掉了（别人的在制改动）：没有锚点可平移
            continue
        text = (ROOT / rel).read_bytes().decode("utf-8")
        for m in sorted(set(ANCHOR.finditer(text)), key=lambda x: x.start()):
            src, line = m.group(1), int(m.group(2))
            if only is not None and src not in only:
                continue
            if src not in maps:
                old = _base_lines(base, src)
                cur_path = ROOT / src
                if old is None or not cur_path.is_file():
                    maps[src] = None
                else:
                    new = cur_path.read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n")
                    maps[src] = None if old == new else _line_map(old, new)
            mapping = maps[src]
            if mapping is None:
                continue
            if line not in mapping:
                stuck.append(f"{rel}: {src}#L{line} 所在行在 {base} 之后被改写或删除，无法平移")
                continue
            if mapping[line] != line:
                moves.setdefault(rel, {})[f'"{src}#L{line}"'] = f'"{src}#L{mapping[line]}"'
    return moves, sorted(set(stuck))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True, help="锚点正确时的版本（通常是 HEAD，即改动之前）")
    ap.add_argument("--only", nargs="*", help="只处理指向这些源文件（仓库相对路径）的锚点")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    moves, stuck = plan(args.base, set(args.only) if args.only else None)
    total = sum(len(v) for v in moves.values())
    for rel, table in sorted(moves.items()):
        print(f"{rel}: {len(table)} 个锚点需平移")
        for old, new in sorted(table.items()):
            print(f"    {old} -> {new}")
    for line in stuck:
        print("无法平移：", line)
    if args.apply:
        for rel, table in moves.items():
            path = ROOT / rel
            text = path.read_bytes().decode("utf-8")  # 按字节读写：保留原有行尾，只改锚点
            path.write_bytes(apply_moves(text, table).encode("utf-8"))
        print(f"已平移 {total} 个锚点（{len(moves)} 个数据文件）")
        return 1 if stuck else 0
    if not total and not stuck:
        print("锚点均无需平移")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
