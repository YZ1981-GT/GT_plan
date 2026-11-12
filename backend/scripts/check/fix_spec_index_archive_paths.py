#!/usr/bin/env python3
"""`.kiro/specs/INDEX.md` 归档路径漂移的**检测 + 自动修复**工具。

背景（2026-11-08 用户要求：推送前自动修复归档路径变更问题，避免出错）
----------------------------------------------------------------------
spec 归档时目录从 `.kiro/specs/<name>/` 移进 `.kiro/specs/_archive/NNN-<name>/`
（或 `_archive/NNN-<分类>/<name>/`），但 INDEX.md 这边的三处常常没跟着改，
于是漂移在仓库里一直累积（守卫 `backend/tests/test_spec_index_consistency.py`
长期现扫到这类问题）：

  A. 顶部速递区 / 正文里的本地链接仍指向旧的活跃路径 `name/tasks.md`，点不开；
  B. 「一、Active Specs」第一张表里仍留着已归档 spec 的行；
  C. 统计行 `**统计**：Active **N** / Archived **M**` 的两个数对不上现扫值。

这三类都是「归档动作只做了一半」留下的**确定性**漂移，可以安全自动修复：
  A → 把链接改向 `_archive/<rel>/<原链接剩余段>`（目标文件必须真的存在才改）；
  B → 删掉活跃表里已归档 spec 的那一行（**前提**：顶部速递区已有该 spec 的记录，
      否则删行会丢信息 ⇒ 只报告、不删）；
  C → 按**已入库**口径重算两个数并改正（与守卫 test_statistics_line_matches 同口径）。

**不**自动修复、只报告并以非 0 退出的情况（需要人判断，自动改会造出假信息）：
  · 新建 spec 没在活跃表登记行（描述 / 进度无法安全生成）；
  · INDEX.md 里有编码损坏（mojibake）；
  · 活跃表里的归档 spec 在速递区没有任何记录（删行会丢信息）。

与守卫的关系：守卫负责**判定**（恒绿则无债），本工具负责**消解**可安全自动化的那部分。
两者共用同一套「归档 spec 目录识别 / 活跃表解析」规则，避免口径漂移。

用法
----
  python backend/scripts/check/fix_spec_index_archive_paths.py --check
      只检测：发现任何漂移 → 退出码 2（可自动修 / 需人工各自列出）；干净 → 0
  python backend/scripts/check/fix_spec_index_archive_paths.py --apply
      自动修复可安全修的部分并写回 INDEX.md；若仍有需人工处理的残留 → 退出码 2

被 `.git-hooks/pre-push` 调用（见该钩子「归档路径自动修复」一节）。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2].parent  # backend/scripts/check -> repo root
SPECS_DIR = REPO_ROOT / ".kiro" / "specs"
INDEX_PATH = SPECS_DIR / "INDEX.md"
ARCHIVE_DIR = SPECS_DIR / "_archive"

_ARCHIVE_NAME = re.compile(r"^(\d+)-(.+)$")
# 本地链接 `](target)`（排除外链与锚点内链）
_LOCAL_LINK = re.compile(r"\]\((?!https?://)([^)#]+)\)")
_SPEC_BACKTICK_LINK = re.compile(r"\[`([^`]+)`\]")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_STAT_LINE = re.compile(r"^\*\*统计\*\*：Active \*\*(\d+)\*\*.*?Archived \*\*(\d+)\*\*")
_SPEC_NAME_IN_QUOTE = re.compile(r"\[`([^`]+)`\]|`([^`]+)`")

ACTIVE_TABLE_HEADING = "## 一、Active Specs"
_SPEC_DOCS = ("tasks.md", "design.md", "requirements.md")

# 两代同名 spec（上一代已归档、当前这一代仍在活跃区）。它们在活跃表里**合法**出现，
# 归档路径修复绝不能把这类行删掉。与守卫 test_spec_index_consistency.py 的
# _ACTIVE_AND_ARCHIVED_SAME_NAME 同一份名单 —— 守卫侧另有「豁免必须可伪证」的反向断言
# （两边都真的存在且都有 tasks.md），这里只需读取同一集合即可。
_ACTIVE_AND_ARCHIVED_SAME_NAME = {
    "workpaper-html-onlyoffice-bidirectional-writeback-closure",
}


# ---------------------------------------------------------------- 归档 / 活跃目录
def archived_specs() -> dict[str, str]:
    """spec 名 -> `_archive` 下的相对目录（与守卫 archived_specs 同口径，递归一层）。"""
    out: dict[str, str] = {}
    if not ARCHIVE_DIR.exists():
        return out
    for d in sorted(ARCHIVE_DIR.iterdir()):
        if not d.is_dir():
            continue
        if any((d / f).exists() for f in _SPEC_DOCS):  # 自身即一个归档 spec
            m = _ARCHIVE_NAME.match(d.name)
            out[m.group(2) if m else d.name] = d.name
            continue
        for sub in sorted(d.iterdir()):  # 分类目录 ⇒ 下一层才是 spec
            if sub.is_dir():
                out.setdefault(sub.name, f"{d.name}/{sub.name}")
    return out


def active_spec_dirs() -> set[str]:
    return {
        d.name for d in SPECS_DIR.iterdir() if d.is_dir() and d.name != "_archive"
    }


# ---------------------------------------------------------------- git 入库口径
def tracked_spec_paths() -> list[str] | None:
    """`.kiro/specs/` 下**已入库**的路径（repo 相对、posix）。git 不可用返回 None。"""
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--", ".kiro/specs/"],
            capture_output=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.decode("utf-8", errors="replace").splitlines()
    return [p.strip() for p in out if p.strip()] or None


def specs_from_paths(paths: list[str]) -> tuple[set[str], dict[str, str]]:
    """按入库路径集合算（活跃 spec 名（带 tasks.md），归档 spec 名 -> `_archive` 下相对目录）。"""
    prefix, arch = ".kiro/specs/", ".kiro/specs/_archive/"
    active: set[str] = set()
    arch_docs: dict[str, set[str]] = defaultdict(set)
    for p in paths:
        if p.startswith(arch):
            rest = p[len(arch):].split("/")
            if len(rest) >= 2:
                arch_docs["/".join(rest[:1])].add("/".join(rest[1:]))
            continue
        rest = p[len(prefix):].split("/")
        if len(rest) == 2 and rest[1] == "tasks.md":
            active.add(rest[0])
    archived: dict[str, str] = {}
    for top, rels in arch_docs.items():
        if any(r in _SPEC_DOCS for r in rels):
            m = _ARCHIVE_NAME.match(top)
            archived[m.group(2) if m else top] = top
            continue
        for r in rels:
            if "/" not in r:
                continue
            sub = r.split("/")[0]
            archived.setdefault(sub, f"{top}/{sub}")
    return active, archived


# ---------------------------------------------------------------- 活跃表解析
def _first_cell(line: str) -> str:
    parts = [p.strip() for p in _UNESCAPED_PIPE.split(line)]
    cells = parts[1:-1] if len(parts) > 2 else parts
    return cells[0] if cells else ""


def _active_table_span(lines: list[str]) -> tuple[int, int]:
    start = next((i for i, l in enumerate(lines) if l.strip() == ACTIVE_TABLE_HEADING), None)
    if start is None:
        raise ValueError(f"INDEX.md 里找不到标题 {ACTIVE_TABLE_HEADING!r}")
    end = next((i for i, l in enumerate(lines) if i > start and l.startswith("## ")), len(lines))
    return start, end


def _active_table_rows(lines: list[str]) -> list[tuple[int, str]]:
    """「一、Active Specs」第一张表的数据行 -> [(0-based 行索引, 第一格)]。"""
    start, end = _active_table_span(lines)
    sep = next((i for i in range(start, end) if lines[i].startswith("|---")), None)
    if sep is None:
        raise ValueError("「一、Active Specs」里找不到表格分隔行")
    rows: list[tuple[int, str]] = []
    for i in range(sep + 1, end):
        if not lines[i].strip().startswith("|"):
            break
        rows.append((i, _first_cell(lines[i])))
    return rows


def _row_spec_name(cell: str) -> str | None:
    m = _SPEC_BACKTICK_LINK.search(cell)
    if m:
        return m.group(1)
    bare = re.fullmatch(r"~{0,2}`([^`]+)`~{0,2}", cell.strip())
    return bare.group(1) if bare else None


# ---------------------------------------------------------------- mojibake（只检测）
def _looks_like_mojibake(line: str) -> bool:
    def cjk(s: str) -> int:
        return sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")

    try:
        rolled = line.encode("latin-1").decode("utf-8", errors="ignore")
    except UnicodeEncodeError:
        return False
    return cjk(rolled) >= 4 and cjk(rolled) > cjk(line) + 2


# ---------------------------------------------------------------- 诊断结果
class Findings:
    def __init__(self) -> None:
        # 可自动修
        self.link_fixes: list[tuple[int, str, str]] = []   # (行索引, 旧 target, 新 target)
        self.row_deletes: list[tuple[int, str]] = []        # (行索引, spec 名)
        self.stat_fix: tuple[int, int, int, int, int] | None = None  # (行索引, 旧A, 旧M, 新A, 新M)
        # 需人工
        self.unregistered_active: list[str] = []            # 新建未登记活跃表
        self.rows_without_quote: list[tuple[int, str]] = [] # 活跃表归档行但速递区无记录
        self.mojibake_lines: list[int] = []

    @property
    def has_autofix(self) -> bool:
        return bool(self.link_fixes or self.row_deletes or self.stat_fix)

    @property
    def has_manual(self) -> bool:
        return bool(self.unregistered_active or self.rows_without_quote or self.mojibake_lines)


def _quote_spec_names(lines: list[str]) -> set[str]:
    """顶部速递区（第一个 `## ` 之前）里以 `> ` 开头的行提到的 spec 名。"""
    first_heading = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
    names: set[str] = set()
    for i in range(first_heading):
        line = lines[i]
        if not line.startswith(">"):
            continue
        for m in _SPEC_NAME_IN_QUOTE.finditer(line):
            names.add(m.group(1) or m.group(2))
    return names


def diagnose(lines: list[str]) -> Findings:
    f = Findings()
    arch = archived_specs()
    active = active_spec_dirs()

    # A. 失效的归档路径链接 —— 链接第一段是已归档 spec、活跃路径不存在、归档路径存在才改
    for idx, line in enumerate(lines):
        for target in _LOCAL_LINK.findall(line):
            head = target.split("/")[0]
            if head not in arch:
                continue
            if (SPECS_DIR / target).exists():
                continue  # 已经能点开，不动
            rel_rest = target[len(head):].lstrip("/")
            new_target = f"_archive/{arch[head]}/{rel_rest}" if rel_rest else f"_archive/{arch[head]}"
            if (SPECS_DIR / new_target).exists():
                f.link_fixes.append((idx, target, new_target))

    # B. 活跃表里的已归档 spec 行（两代同名的当前活跃行除外 —— 它合法地在活跃表里）
    quote_names = _quote_spec_names(lines)
    for idx, cell in _active_table_rows(lines):
        name = _row_spec_name(cell)
        if not name or name not in arch or name in _ACTIVE_AND_ARCHIVED_SAME_NAME:
            continue
        if name in quote_names:
            f.row_deletes.append((idx, name))
        else:
            f.rows_without_quote.append((idx, name))

    # 新建未登记活跃表（只报告）：活跃目录里带 tasks.md 的 spec 没出现在活跃表链接里
    listed = {
        n for _, cell in _active_table_rows(lines)
        if (m := _SPEC_BACKTICK_LINK.search(cell)) and (n := m.group(1))
    }
    expected = {d for d in active if (SPECS_DIR / d / "tasks.md").exists()}
    f.unregistered_active = sorted(expected - listed)

    # C. 统计行
    paths = tracked_spec_paths()
    if paths is not None:
        tracked_active, tracked_archived = specs_from_paths(paths)
        exp_a, exp_m = len(tracked_active), len(tracked_archived)
        for idx, line in enumerate(lines):
            m = _STAT_LINE.match(line)
            if m:
                cur_a, cur_m = int(m.group(1)), int(m.group(2))
                if (cur_a, cur_m) != (exp_a, exp_m):
                    f.stat_fix = (idx, cur_a, cur_m, exp_a, exp_m)
                break

    # mojibake（只检测）
    f.mojibake_lines = [i + 1 for i, l in enumerate(lines) if _looks_like_mojibake(l)]
    return f


# ---------------------------------------------------------------- 应用修复
def apply_fixes(lines: list[str], f: Findings) -> list[str]:
    """把可自动修的三类改动写进 lines 副本并返回（不触碰需人工的部分）。"""
    out = list(lines)

    # A. 链接改向（同一行可能多处，逐个替换字面量）
    per_line: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for idx, old, new in f.link_fixes:
        per_line[idx].append((old, new))
    for idx, pairs in per_line.items():
        line = out[idx]
        for old, new in pairs:
            line = line.replace(f"]({old})", f"]({new})")
        out[idx] = line

    # C. 统计行（只改两个数字，其余文案不动）
    if f.stat_fix:
        idx, old_a, old_m, new_a, new_m = f.stat_fix
        line = out[idx]
        line = line.replace(f"Active **{old_a}**", f"Active **{new_a}**", 1)
        line = line.replace(f"Archived **{old_m}**", f"Archived **{new_m}**", 1)
        out[idx] = line

    # B. 删行（从大到小删，避免索引偏移）
    for idx, _name in sorted(f.row_deletes, key=lambda t: t[0], reverse=True):
        del out[idx]

    return out


# ---------------------------------------------------------------- 报告
def _print_report(f: Findings) -> None:
    tag = "[spec-index-archive]"
    if f.link_fixes:
        print(f"{tag} 可自动修：{len(f.link_fixes)} 个链接指向已归档 spec 的旧活跃路径")
        for idx, old, new in f.link_fixes[:20]:
            print(f"    行 {idx + 1}: {old}  ->  {new}")
        if len(f.link_fixes) > 20:
            print(f"    …另有 {len(f.link_fixes) - 20} 个")
    if f.row_deletes:
        print(f"{tag} 可自动修：活跃表有 {len(f.row_deletes)} 行的 spec 已归档（速递区已有记录，删行安全）")
        for idx, name in f.row_deletes:
            print(f"    行 {idx + 1}: {name}")
    if f.stat_fix:
        idx, oa, om, na, nm = f.stat_fix
        print(f"{tag} 可自动修：统计行（行 {idx + 1}）Active {oa}->{na}、Archived {om}->{nm}")

    if f.rows_without_quote:
        print(f"{tag} ⚠️ 需人工：活跃表有 {len(f.rows_without_quote)} 行的 spec 已归档，但速递区没有记录"
              f"（删行会丢信息，请先补速递行再删）：")
        for idx, name in f.rows_without_quote:
            print(f"    行 {idx + 1}: {name}")
    if f.unregistered_active:
        print(f"{tag} ⚠️ 需人工：{len(f.unregistered_active)} 个活跃 spec 没在活跃表登记行"
              f"（新建 / 恢复 spec 要补一行，进度写现扫 tasks.md 的 [x]/总数）：")
        print(f"    {f.unregistered_active}")
    if f.mojibake_lines:
        print(f"{tag} ⚠️ 需人工：{len(f.mojibake_lines)} 行疑似编码损坏（mojibake），请用显式 UTF-8 还原："
              f"行 {f.mojibake_lines}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="INDEX.md 归档路径漂移检测 + 自动修复")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只检测，发现漂移退出码 2")
    mode.add_argument("--apply", action="store_true", help="自动修复可安全修的部分并写回")
    args = parser.parse_args(argv)
    # 默认 --check
    do_apply = args.apply

    tag = "[spec-index-archive]"
    if not INDEX_PATH.exists():
        print(f"{tag} INDEX.md 不存在：{INDEX_PATH}")
        return 0

    raw = INDEX_PATH.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(newline) if newline in raw else raw.splitlines()
    # 用 splitlines 口径解析，但写回保持原换行与结尾
    parse_lines = raw.splitlines()

    try:
        f = diagnose(parse_lines)
    except ValueError as exc:
        print(f"{tag} ❌ 解析 INDEX.md 失败：{exc}")
        return 1

    if not f.has_autofix and not f.has_manual:
        print(f"{tag} ✅ INDEX.md 归档路径一致，无漂移")
        return 0

    _print_report(f)

    if not do_apply:
        if f.has_autofix:
            print(f"{tag} 以上「可自动修」项运行一次即修复："
                  f"python backend/scripts/check/fix_spec_index_archive_paths.py --apply")
        return 2

    # --apply：只修可自动化的部分
    # 🔴 统计行与「活跃表逐行相等」是一对联动判据：若还有「需人工」项（新建未登记 / 速递区无记录
    #    的归档行），此刻活跃表并不完整，改统计数只会制造「表 N 行、统计说 M」的新矛盾。
    #    ⇒ 有需人工项时，本轮不动统计行，等人工补齐后统计行自然由下一次 --apply / 守卫对账。
    if f.has_manual and f.stat_fix:
        print(f"{tag} ⏸ 暂不改统计行：仍有需人工处理的活跃表项，补齐后统计数才能对账")
        f.stat_fix = None

    if f.has_autofix:
        fixed = apply_fixes(parse_lines, f)
        # 保持原文件的换行风格与末尾换行
        text = newline.join(fixed)
        if raw.endswith(newline) and not text.endswith(newline):
            text += newline
        INDEX_PATH.write_bytes(text.encode("utf-8"))
        print(f"{tag} ✅ 已自动修复 INDEX.md（链接 {len(f.link_fixes)} 处 / 删行 "
              f"{len(f.row_deletes)} 处 / 统计行 {'1' if f.stat_fix else '0'} 处）")

    if f.has_manual:
        print(f"{tag} ⚠️ 仍有需人工处理的项（见上），不能自动修复")
        return 2
    print(f"{tag} ✅ 全部可自动修项已修复，无需人工处理")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
