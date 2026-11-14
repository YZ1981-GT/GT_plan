"""`.kiro/specs/INDEX.md` 的漂移 / 重复守卫。

2026-11-01 立：用户「刚从 git 同步拉取下来，表格存在漂移重复问题」。现算出的真问题是
归档动作只做了一半 —— spec 目录已移进 `_archive/NNN-<name>/`，但 INDEX 里
①「一、Active Specs」表的那一行没删（活跃表 24 行里 12 行的 spec 已归档）
②顶部速递行的链接还指向旧的活跃路径（17 个路径 / 20 处引用全部点不开）。
两者都不会被任何现有门禁看见，所以会一直累积。

本文件把"归档必须三件齐"写成可执行判据：目录移走、活跃表删行、链接改向。

2026-11-05 续：用户「你先修复表格漂移问题」。现扫出上面三条判据都盖不住的第二类漂移 ——
①活跃表只有 9 行带链接的活跃 spec，而活跃目录（含 tasks.md）有 27 个 ⇒ **18 个 spec 没有行**；
②同一张表从中间起接了 81 行「已完成 / 已归档」的历史行，其中 62 行是**裸反引号**（没有链接），
  所以"活跃表里不得有归档 spec"这条判据一行都看不见它们；
③两个进度格是坏的（截断、括号不配平、数字对不上 tasks.md）。
⇒ INDEX 把历史行拆成 §一.1 独立表格、活跃表补齐 18 行，本文件相应加两条硬判据：
  活跃表与活跃目录**逐行相等**；活跃表里的归档 spec **连裸反引号写法一起抓**。

对**历史债**用棘轮（只许减少）而不是硬断言 —— 恒红门禁等于没有门禁：
  · 归档区表格里重复出现的 spec（2026-07/08 的历史轨迹，append-only 不回填改写）
  · `_archive` 序号撞号（改目录名会断其他文档里的引用）
  · 活跃 spec 未被 INDEX 收录（别人在建的 spec，不代写其状态）
每条棘轮都配"基线条目必须真的还成立"的反向断言，防止基线变成加一行就能变绿的后门。
"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = REPO_ROOT / ".kiro" / "specs"
INDEX_PATH = SPECS_DIR / "INDEX.md"
ARCHIVE_DIR = SPECS_DIR / "_archive"

_ARCHIVE_NAME = re.compile(r"^(\d+)-(.+)$")
_LOCAL_LINK = re.compile(r"\]\((?!https?://)([^)#]+)\)")
_SPEC_BACKTICK_LINK = re.compile(r"\[`([^`]+)`\]")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
# 交叉引用写法不统一会让守卫假红：既有文案有「见下条」「见上条」「见上一条」等
_CROSS_REF = re.compile(r"见(?:上|下)(?:一)?条")

ACTIVE_TABLE_HEADING = "## 一、Active Specs"

# ---------------------------------------------------------------- 历史债棘轮基线
# 归档区表格里同一 spec 出现多次（只许减少）
_ARCHIVE_DUP_SPEC_BASELINE = {"procedure-delegation-visibility-isolation"}
# `_archive` 下的序号撞号（只许减少）
_ARCHIVE_NUMBER_COLLISION_BASELINE = {"04", "18", "52", "112", "121"}
# 带日期的速递条目落在了第一个 `## ` 标题之后（只许减少）。
# 注意不能把「> **`spec`(24/24)** 已于 2026-08-15 归档（见下）」这类注记算进来 ——
# 那是归档区里有意写的说明，不是漂移；只有"带日期的速递条目"才是放错了位置。
_STRAY_DATED_QUOTE_BASELINE = {
    "d4-ipo-fraud-writeback-formula-io",
    "m-cycle-bidirectional-pipeline",
}
# 活跃 spec 目录未被 INDEX 任何链接提及（只许减少）。
# 2026-11-05 清零：原 5 条都是"只在速递区被提过、活跃表里没有行"，随本轮补齐活跃表一并收录。
# 现在这条棘轮的基线为空 ⇒ 与硬断言等价：新建 spec 必须在活跃表登记一行（见
# test_active_table_lists_exactly_the_active_specs 的报错信息）。
_UNINDEXED_ACTIVE_SPEC_BASELINE: set[str] = set()

# 同一个 spec 名既在活跃区、又在 `_archive` 下（两代同名）。这不是漂移，但会让"活跃表里不得有
# 归档 spec"误报 ⇒ 显式豁免 + 反向断言（下面 test_same_name_active_and_archived_exemption_is_real
# 要求两边都真的存在且都有 tasks.md），不是写个名字就能放行的后门。
_ACTIVE_AND_ARCHIVED_SAME_NAME = {
    # 平台总纲：上一代 66/66 已归档 `_archive/17-2026-10-03-verified-batch/`，
    # 当前这一代仍在办（活跃区 46/50）
    "workpaper-html-onlyoffice-bidirectional-writeback-closure",
}


# ---------------------------------------------------------------- 读取与解析
@pytest.fixture(scope="module")
def index_lines() -> list[str]:
    if not INDEX_PATH.exists():
        pytest.skip(f"INDEX.md 不存在：{INDEX_PATH}")
    return INDEX_PATH.read_bytes().decode("utf-8").splitlines()


#: spec 三件套文件名（用来区分"归档的 spec 目录"与"归档分类目录"）
_SPEC_DOCS = ("tasks.md", "design.md", "requirements.md")


def _tracked_spec_paths() -> list[str] | None:
    """`.kiro/specs/` 下**已入库**的文件路径（repo 相对、posix）。git 不可用返回 None。

    统计行要跟它对账而不是跟磁盘：磁盘上可能有并发会话还没提交的归档目录（现场就有 4 个），
    按磁盘数对账会在别人有在办归档时变红，且报错指向统计行、指不到真因。
    """
    try:
        proc = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files", "--", ".kiro/specs/"],
                              capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.decode("utf-8", errors="replace").splitlines()
    return [p.strip() for p in out if p.strip()] or None


def _specs_from_paths(paths: list[str]) -> tuple[set[str], dict[str, str]]:
    """按路径集合算出（活跃 spec 名（带 tasks.md），归档 spec 名 -> `_archive` 下相对目录）。

    与 `archived_specs` 走同一条「自身含三件套即 spec 目录、否则是分类目录」的规则，只是输入从磁盘换成 git。
    """
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
        if any(r in _SPEC_DOCS for r in rels):  # 自身就是一个归档的 spec
            m = _ARCHIVE_NAME.match(top)
            archived[m.group(2) if m else top] = top
            continue
        for r in rels:  # 分类目录 ⇒ 再下一层才是 spec（分类目录里直接放的说明文件不是 spec）
            if "/" not in r:
                continue
            sub = r.split("/")[0]
            archived.setdefault(sub, f"{top}/{sub}")
    return active, archived


@pytest.fixture(scope="module")
def archived_specs() -> dict[str, str]:
    """spec 名 -> `_archive` 下的相对目录。

    归档区两种布局并存：`_archive/NNN-<spec>/`（直接归档）与 `_archive/NNN-<分类>/<spec>/`（按批分类）。
    只扫一级会把后者整批看不见 —— 现算 775 个归档 spec 里绝大多数是后者 ⇒ 必须递归一层。
    """
    if not ARCHIVE_DIR.exists():
        pytest.skip(f"_archive 不存在：{ARCHIVE_DIR}")
    out: dict[str, str] = {}
    for d in sorted(ARCHIVE_DIR.iterdir()):
        if not d.is_dir():
            continue
        if any((d / f).exists() for f in _SPEC_DOCS):  # 自身就是一个归档的 spec
            m = _ARCHIVE_NAME.match(d.name)
            out[m.group(2) if m else d.name] = d.name
            continue
        for sub in sorted(d.iterdir()):  # 分类目录 ⇒ 再下一层才是 spec
            if sub.is_dir():
                out.setdefault(sub.name, f"{d.name}/{sub.name}")
    return out


@pytest.fixture(scope="module")
def active_spec_dirs() -> set[str]:
    return {
        d.name
        for d in SPECS_DIR.iterdir()
        if d.is_dir() and d.name != "_archive"
    }


def _active_table_span(lines: list[str]) -> tuple[int, int]:
    """返回「一、Active Specs」表的行区间（0-based，半开）。"""
    start = next(
        (i for i, l in enumerate(lines) if l.strip() == ACTIVE_TABLE_HEADING), None
    )
    assert start is not None, f"INDEX.md 里找不到标题 {ACTIVE_TABLE_HEADING!r}"
    end = next(
        (i for i, l in enumerate(lines) if i > start and l.startswith("## ")), len(lines)
    )
    return start, end


def _table_segments(lines: list[str]) -> list[list[tuple[int, str]]]:
    """按"连续的表格行"切段（空行 / 说明行会切断，同一标题下可有多段）。"""
    segments: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    for i, l in enumerate(lines, 1):
        if l.strip().startswith("|"):
            cur.append((i, l))
        elif cur:
            segments.append(cur)
            cur = []
    if cur:
        segments.append(cur)
    return segments


def _first_cell(line: str) -> str:
    parts = [p.strip() for p in _UNESCAPED_PIPE.split(line)]
    cells = parts[1:-1] if len(parts) > 2 else parts
    return cells[0] if cells else ""


def _is_separator(cell: str) -> bool:
    return bool(cell) and set(cell) <= set("-: ")


def _active_table_rows(lines: list[str]) -> list[tuple[int, str]]:
    """「一、Active Specs」里**第一张**表的数据行 -> [(行号, 第一格)]。

    该节里现在有两张表：活跃表，和 §一.1 的历史轨迹表（append-only，允许出现已归档 spec）。
    对账只能针对第一张；拿整节去对账会把历史行也当成活跃行（这正是本轮之前的状况）。
    """
    start, end = _active_table_span(lines)
    sep = next((i for i in range(start, end) if lines[i].startswith("|---")), None)
    assert sep is not None, "「一、Active Specs」里找不到表格分隔行"
    rows: list[tuple[int, str]] = []
    for i in range(sep + 1, end):
        if not lines[i].strip().startswith("|"):
            break  # 空行 / §一.1 的小标题 ⇒ 第一张表到此结束
        rows.append((i + 1, _first_cell(lines[i])))
    return rows


def _row_spec_name(cell: str) -> str | None:
    """表格第一格里的 spec 名：`[`name`](…)`（链接）或 `` `name` ``（裸反引号）都认。"""
    m = _SPEC_BACKTICK_LINK.search(cell)
    if m:
        return m.group(1)
    bare = re.fullmatch(r"~{0,2}`([^`]+)`~{0,2}", cell.strip())
    return bare.group(1) if bare else None


# ================================================================ 硬断言（基线 0）
def test_index_has_no_broken_local_links(index_lines: list[str]) -> None:
    """INDEX 里的本地链接必须都能点开。

    归档时漏改链接正是本轮抓到的主缺陷：17 个路径全部指向已被移走的活跃目录。
    """
    broken: dict[str, list[int]] = defaultdict(list)
    for lineno, line in enumerate(index_lines, 1):
        for target in _LOCAL_LINK.findall(line):
            if not (SPECS_DIR / target).exists():
                broken[target].append(lineno)

    assert not broken, (
        f"INDEX.md 有 {len(broken)} 个本地链接点不开。spec 归档后要把链接改成 "
        f"`_archive/NNN-<name>/...`：\n"
        + "\n".join(f"  {t}  （行 {ls}）" for t, ls in sorted(broken.items()))
    )


def test_active_specs_table_contains_no_archived_spec(
    index_lines: list[str], archived_specs: dict[str, str]
) -> None:
    """活跃表（§一 第一张表）里不得出现已经归档的 spec。

    删行前要先确认它在速递区已有记录，否则信息会丢 —— 2026-11-01 那 2 个速递区无记录的
    就是先补了速递行才删的。
    2026-11-05 两处收紧：①范围限定为第一张表（§一.1 的历史表本就该有归档 spec）
    ②裸反引号写法一起抓 —— 原判据只认 `[`name`](…)`，而混进活跃表的 81 行历史行里有 62 行
    是裸反引号，判据对它们一行都没看见。
    """
    rows = _active_table_rows(index_lines)
    assert rows, "活跃表一行都没取到：判据的分母是空的，再怎么断言都恒绿"
    stale = [
        (ln, name)
        for ln, cell in rows
        if (name := _row_spec_name(cell))
        and name in archived_specs
        and name not in _ACTIVE_AND_ARCHIVED_SAME_NAME
    ]

    assert not stale, (
        f"活跃表里有 {len(stale)} 行的 spec 已经归档，归档时漏删：\n"
        + "\n".join(
            f"  行 {ln}  {name}  -> _archive/{archived_specs[name]}/" for ln, name in stale
        )
    )


def test_active_table_lists_exactly_the_active_specs(
    index_lines: list[str], active_spec_dirs: set[str]
) -> None:
    """活跃表的行集合必须**恰好等于**活跃 spec 目录（带 tasks.md 的）。

    2026-11-05 立：上一版判据只要求"活跃 spec 在 INDEX 里被某个链接提到过"，
    于是只在顶部速递区写一行、活跃表里没有行也算合规 —— 现扫 27 个活跃 spec 里 **18 个**
    就是这样；表变成了"9 行的样子"，而速递区那 18 条的进度数还是立项时的旧值。
    表是对账用的，少一行就等于这个 spec 的状态没人对账。
    """
    expected = {d for d in active_spec_dirs if (SPECS_DIR / d / "tasks.md").exists()}
    assert expected, "没有任何带 tasks.md 的活跃 spec：分母为空，判据恒绿"
    rows = _active_table_rows(index_lines)
    listed: dict[str, int] = {}
    bad_form: list[tuple[int, str]] = []
    for ln, cell in rows:
        m = _SPEC_BACKTICK_LINK.search(cell)
        if not m:
            bad_form.append((ln, cell[:60]))
            continue
        listed[m.group(1)] = ln

    missing = sorted(expected - set(listed))
    extra = sorted(set(listed) - expected)
    assert not missing, (
        f"有 {len(missing)} 个活跃 spec 在活跃表里没有行（新建 / 恢复 spec 要补一行，"
        f"进度写现扫 `tasks.md` 的 `[x]` / 总数）：{missing}"
    )
    assert not extra, (
        f"活跃表有 {len(extra)} 行的 spec 目录已不在活跃区（归档后要删行并把链接改向 "
        f"`_archive/NNN-<name>/`）：{extra}"
    )
    assert not bad_form, (
        "活跃表的每一行都必须是能点开的链接 `[`name`](name/tasks.md)`，"
        f"下面这些行不是（裸反引号 / 删除线写法属 §一.1 历史表）：{bad_form}"
    )


def test_repeated_quote_entries_carry_a_cross_reference(index_lines: list[str]) -> None:
    """同一 spec 在顶部速递区有多条时，必须有交叉引用把它们串起来。

    仓库惯例是「立项快照 + 完成态」两条并写「见下条」。没有交叉引用的两条读起来就是
    自相矛盾的重复——本轮两组真重复里，有一组的旧条还写着已被证伪的「未推送」。
    """
    positions: dict[str, list[int]] = defaultdict(list)
    for lineno, line in enumerate(index_lines, 1):
        if not line.startswith(">"):
            continue
        m = _SPEC_BACKTICK_LINK.search(line)
        if m:
            positions[m.group(1)].append(lineno)

    offenders: dict[str, list[int]] = {}
    for name, lines_ in positions.items():
        if len(lines_) < 2:
            continue
        if not any(_CROSS_REF.search(index_lines[n - 1]) for n in lines_):
            offenders[name] = lines_

    assert not offenders, (
        f"顶部速递区有 {len(offenders)} 个 spec 出现多条却没有任何交叉引用"
        f"（至少一条要写「见上条」/「见下条」）：\n"
        + "\n".join(f"  {n}  行 {ls}" for n, ls in sorted(offenders.items()))
    )


def test_table_segments_have_uniform_column_count(index_lines: list[str]) -> None:
    """同一段表格内每行的未转义 pipe 数必须一致。

    说明格里写裸 `|` 会让该行多一个 pipe、表格当场错位，而肉眼看不出来
    （既有纪律：表格第三格内禁裸 pipe，要写 `\\|`）。
    """
    bad: list[str] = []
    for seg in _table_segments(index_lines):
        counts = {len(_UNESCAPED_PIPE.findall(l)) for _, l in seg}
        if len(counts) > 1:
            head = seg[0][0]
            detail = ", ".join(
                f"行{ln}={len(_UNESCAPED_PIPE.findall(l))}" for ln, l in seg
            )
            bad.append(f"  起始行 {head}: pipe 数不一致 {sorted(counts)} —— {detail}")

    assert not bad, "INDEX.md 表格列数错位（多半是说明格里写了裸 `|`）：\n" + "\n".join(bad)


# ================================================================ 棘轮（只许减少）
def _archive_duplicate_specs(index_lines: list[str]) -> dict[str, list[int]]:
    """归档区（活跃表之后）表格里同一 spec 出现多次。"""
    _, end = _active_table_span(index_lines)
    positions: dict[str, list[int]] = defaultdict(list)
    for lineno in range(end + 1, len(index_lines) + 1):
        line = index_lines[lineno - 1]
        if not line.strip().startswith("|"):
            continue
        cell = _first_cell(line)
        if not cell or _is_separator(cell) or cell.lower() in {"spec", "spec 名", "名称"}:
            continue
        positions[cell].append(lineno)
    return {k: v for k, v in positions.items() if len(v) > 1}


def test_archive_duplicate_specs_only_shrinks(index_lines: list[str]) -> None:
    dup = _archive_duplicate_specs(index_lines)
    new = set(dup) - _ARCHIVE_DUP_SPEC_BASELINE
    assert not new, (
        f"归档区表格新增了重复 spec（不得新增）：{sorted(new)}。"
        f"归档区是 append-only 的历史轨迹，新记录请另起一行归档批次而不是重复登记同一 spec"
    )


def test_archive_duplicate_spec_baseline_has_no_stale_entry(index_lines: list[str]) -> None:
    """反向断言：基线里的条目必须真的还重复着，否则它是失效条目、必须从基线删掉。"""
    dup = set(_archive_duplicate_specs(index_lines))
    stale = _ARCHIVE_DUP_SPEC_BASELINE - dup
    assert not stale, (
        f"_ARCHIVE_DUP_SPEC_BASELINE 有 {len(stale)} 个失效条目（已经不重复了）："
        f"{sorted(stale)} —— 请从基线里删掉，别让基线变成放行后门"
    )


def _archive_number_collisions() -> dict[str, list[str]]:
    by_number: dict[str, list[str]] = defaultdict(list)
    for d in sorted(ARCHIVE_DIR.iterdir()):
        if not d.is_dir():
            continue
        m = _ARCHIVE_NAME.match(d.name)
        if m:
            by_number[m.group(1)].append(d.name)
    return {k: v for k, v in by_number.items() if len(v) > 1}


def test_archive_number_collisions_only_shrink() -> None:
    collisions = _archive_number_collisions()
    new = set(collisions) - _ARCHIVE_NUMBER_COLLISION_BASELINE
    assert not new, (
        "`_archive` 新增了序号撞号（归档序号应唯一，新归档请取 max+1）：\n"
        + "\n".join(f"  {n}: {collisions[n]}" for n in sorted(new))
    )


def test_archive_number_collision_baseline_has_no_stale_entry() -> None:
    collisions = set(_archive_number_collisions())
    stale = _ARCHIVE_NUMBER_COLLISION_BASELINE - collisions
    assert not stale, (
        f"_ARCHIVE_NUMBER_COLLISION_BASELINE 有失效条目（已不撞号）：{sorted(stale)}"
        f" —— 请从基线里删掉"
    )


def _unindexed_active_specs(index_lines: list[str], active: set[str]) -> set[str]:
    """返回已有 ``tasks.md`` 的活跃 spec 中尚未在 INDEX 出现的目录名。

    ``.kiro/specs`` 下允许暂存调查材料目录（例如只有 ``basis/``、尚未形成
    三件套）。它们不是活跃 spec，不能因为目录存在就要求活跃表登记；活跃表和
    统计行的正式分母都以 ``tasks.md`` 为准。
    """
    text = "\n".join(index_lines)
    mentioned = {
        t.split("/")[0] for t in _LOCAL_LINK.findall(text) if t.split("/")[0]
    }
    return {
        n for n in active
        if (SPECS_DIR / n / "tasks.md").exists() and n not in mentioned
    }


def test_unindexed_active_specs_only_shrink(
    index_lines: list[str], active_spec_dirs: set[str]
) -> None:
    missing = _unindexed_active_specs(index_lines, active_spec_dirs)
    new = missing - _UNINDEXED_ACTIVE_SPEC_BASELINE
    assert not new, (
        f"有 {len(new)} 个活跃 spec 没被 INDEX 收录（新建 spec 要在 INDEX 登记一行）："
        f"{sorted(new)}"
    )


def test_unindexed_active_spec_baseline_has_no_stale_entry(
    index_lines: list[str], active_spec_dirs: set[str]
) -> None:
    """反向断言：基线条目要么仍未收录、要么目录已不在活跃区；两者都不成立就是失效条目。"""
    missing = _unindexed_active_specs(index_lines, active_spec_dirs)
    stale = {
        n
        for n in _UNINDEXED_ACTIVE_SPEC_BASELINE
        if n not in missing and n in active_spec_dirs
    }
    assert not stale, (
        f"_UNINDEXED_ACTIVE_SPEC_BASELINE 有 {len(stale)} 个失效条目（已经被收录了）："
        f"{sorted(stale)} —— 请从基线里删掉"
    )


_DATED_QUOTE = re.compile(r"^> \*\*\d{4}-\d{2}-\d{2}")
_SPEC_NAME_IN_LINE = re.compile(r"\[`([^`]+)`\]|`([^`]+)`")


def _stray_dated_quotes(lines: list[str]) -> dict[str, int]:
    """带日期的速递条目落在第一个 `## ` 标题之后 -> {spec 名: 行号}。"""
    first_heading = next(
        (i for i, l in enumerate(lines) if l.startswith("## ")), len(lines)
    )
    out: dict[str, int] = {}
    for i in range(first_heading, len(lines)):
        line = lines[i]
        if not _DATED_QUOTE.match(line):
            continue
        m = _SPEC_NAME_IN_LINE.search(line)
        out[(m.group(1) or m.group(2)) if m else f"(无 spec 名)@{i + 1}"] = i + 1
    return out


def test_stray_dated_quote_entries_only_shrink(index_lines: list[str]) -> None:
    """速递条目要留在顶部速递区。

    本轮踩过：往"最后一条 `>` 行"后面插入，结果被文件尾部两条孤立速递行带偏，
    新条目落到了「## 四、索引规约」后面。插入点要按"第一个 `## ` 之前"定位。
    """
    stray = _stray_dated_quotes(index_lines)
    new = set(stray) - _STRAY_DATED_QUOTE_BASELINE
    assert not new, (
        f"有 {len(new)} 条带日期的速递条目落在第一个 `## ` 标题之后（应在顶部速递区）："
        + ", ".join(f"{n}（行 {stray[n]}）" for n in sorted(new))
    )


def test_stray_dated_quote_baseline_has_no_stale_entry(index_lines: list[str]) -> None:
    stray = set(_stray_dated_quotes(index_lines))
    stale = _STRAY_DATED_QUOTE_BASELINE - stray
    assert not stale, (
        f"_STRAY_DATED_QUOTE_BASELINE 有失效条目（已经不在错误位置了）：{sorted(stale)}"
        f" —— 请从基线里删掉"
    )


_STAT_LINE = re.compile(
    r"^\*\*统计\*\*：Active \*\*(\d+)\*\*.*?Archived \*\*(\d+)\*\*"
)


def test_statistics_line_matches_the_live_counts(
    index_lines: list[str], active_spec_dirs: set[str], archived_specs: dict[str, str]
) -> None:
    """统计行的两个数必须等于现扫值。

    2026-11-05 现场：写着 Active **31** / Archived **121**，而现扫是 **27** / **775** ——
    两个数都没人对账，于是"表里 9 行、统计说 31、速递区还有第三个数"三处互相矛盾。
    加这一行判据的成本很低：新建 / 归档 spec 时本来就要动活跃表那一行，顺手改同一处数字。
    """
    hits = [(i + 1, m) for i, line in enumerate(index_lines) if (m := _STAT_LINE.match(line))]
    assert len(hits) == 1, f"统计行应恰好一条（现算 {len(hits)} 条）：{[h[0] for h in hits]}"
    lineno, m = hits[0]
    active_n, archived_n = int(m.group(1)), int(m.group(2))
    paths = _tracked_spec_paths()
    if paths is None:
        pytest.skip("git 不可用，无法按入库口径对账统计行（见 test_tracked_spec_paths_is_available_here）")
    tracked_active, tracked_archived = _specs_from_paths(paths)
    expected_active, expected_archived = len(tracked_active), len(tracked_archived)
    untracked_archive = sorted(set(archived_specs) - set(tracked_archived))
    assert (active_n, archived_n) == (expected_active, expected_archived), (
        f"统计行（行 {lineno}）与已入库口径不一致：Active {active_n} vs {expected_active}、"
        f"Archived {archived_n} vs {expected_archived}。口径：Active = 已入库的 `.kiro/specs/*/tasks.md`，"
        f"Archived = 已入库的 `_archive/` 递归去重名 spec 目录数"
        + (f"。另注：磁盘上还有 {len(untracked_archive)} 个未入库的归档目录（不参与对账，"
           f"但归档没提交本身就是半截动作）：{untracked_archive[:5]}" if untracked_archive else "")
    )


def test_tracked_spec_paths_is_available_here() -> None:
    """反向断言：本仓库里 git 必须可用，否则上面那条判据会长期静默 skip。"""
    paths = _tracked_spec_paths()
    assert paths, "`git ls-files .kiro/specs/` 取不到已入库路径：统计行判据会被 skip 掉"
    assert any(p.endswith("/tasks.md") for p in paths)
    active, archived = _specs_from_paths(paths)
    assert active and archived, f"入库口径算出的集合不该为空：active={len(active)} archived={len(archived)}"


def test_statistics_line_pattern_matches_the_wording_actually_used() -> None:
    """判据自检：统计行的正则必须认仓库里真实的写法，也不能把别的现扫行误当统计行。"""
    real = ("**统计**：Active **27**（2026-11-05 现扫 `.kiro/specs/*/tasks.md`）"
            " / Archived **775**（现扫 `_archive/` 递归去重名）")
    m = _STAT_LINE.match(real)
    assert m and m.group(1) == "27" and m.group(2) == "775"
    assert not _STAT_LINE.match("> ⏱ **2026-09-28 第十六次现扫**：Active **65 → 66**")


def test_same_name_active_and_archived_exemption_is_real(
    active_spec_dirs: set[str], archived_specs: dict[str, str]
) -> None:
    """反向断言：豁免名单里的 spec 必须真的"两边都有、且都是完整的一代"。

    否则这个名单就是"写上名字即放行"的后门（本仓既有纪律：豁免必须可伪证）。
    """
    bad: list[str] = []
    for name in _ACTIVE_AND_ARCHIVED_SAME_NAME:
        if name not in active_spec_dirs:
            bad.append(f"{name}：已不在活跃区 ⇒ 豁免是失效条目，请删")
        elif name not in archived_specs:
            bad.append(f"{name}：`_archive` 下没有同名 spec ⇒ 不存在同名冲突，请删")
        elif not (SPECS_DIR / name / "tasks.md").exists():
            bad.append(f"{name}：活跃区那份没有 tasks.md")
        elif not (ARCHIVE_DIR / archived_specs[name] / "tasks.md").exists():
            bad.append(f"{name}：归档那份没有 tasks.md ⇒ 不是真的一代产物")
    assert not bad, "_ACTIVE_AND_ARCHIVED_SAME_NAME 有站不住的条目：\n  " + "\n  ".join(bad)


def test_active_table_row_parser_reads_both_writings() -> None:
    """判据自检：第一格的两种写法都要认出来，顺手的格式（加粗 / 删除线）不能让它漏。"""
    assert _row_spec_name("[`a-spec`](a-spec/tasks.md)") == "a-spec"
    assert _row_spec_name("`a-spec`") == "a-spec"
    assert _row_spec_name("~~`a-spec`~~") == "a-spec"
    assert _row_spec_name("进度说明，没有 spec 名") is None


def test_active_table_checks_catch_a_fabricated_drift(
    index_lines: list[str], archived_specs: dict[str, str], active_spec_dirs: set[str]
) -> None:
    """判据自检（双向）：现状必须干净，而人为造出的两种漂移必须被抓。

    只证明"现在是绿的"不够 —— 本轮之前那条判据对 62 行裸反引号的归档行就是绿的。
    """
    rows = _active_table_rows(index_lines)
    expected = {d for d in active_spec_dirs if (SPECS_DIR / d / "tasks.md").exists()}
    listed = {n for _, cell in rows if (n := _row_spec_name(cell))}
    assert listed == expected, "现状自检：活跃表与活跃目录应已逐行相等"

    start, _ = _active_table_span(index_lines)
    sep = next(i for i in range(start, len(index_lines)) if index_lines[i].startswith("|---"))
    some_archived = sorted(n for n in archived_specs if n not in _ACTIVE_AND_ARCHIVED_SAME_NAME)[0]

    # 形态一：往活跃表里塞一行裸反引号的归档 spec
    polluted = list(index_lines)
    polluted.insert(sep + 1, f"| `{some_archived}` | ✅ 已归档 | 混进活跃表的历史行 |")
    names = {n for _, cell in _active_table_rows(polluted) if (n := _row_spec_name(cell))}
    assert some_archived in names, "裸反引号的归档行没被判据看见（正是本轮修的那个盲区）"

    # 形态二：删掉活跃表的一行
    trimmed = [line for i, line in enumerate(index_lines) if i != sep + 1]
    trimmed_names = {n for _, cell in _active_table_rows(trimmed) if (n := _row_spec_name(cell))}
    assert trimmed_names != expected and len(trimmed_names) == len(expected) - 1, (
        "删掉一行后判据应当察觉差集"
    )


def _looks_like_mojibake(line: str) -> bool:
    """本质判据：按 latin-1 回卷后 CJK 字符显著增加 ⇒ 这行是 UTF-8 被误解后存盘的产物。

    不用"高位字符计数"这类表面判据 —— INDEX 正常行大量使用 U+00B7（`·`）作分隔符，
    计数法分不开（实测正常行有 29~39 个高位字符，比部分损坏行还多）。
    """

    def cjk(s: str) -> int:
        return sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")

    try:
        rolled = line.encode("latin-1").decode("utf-8", errors="ignore")
    except UnicodeEncodeError:
        return False
    return cjk(rolled) >= 4 and cjk(rolled) > cjk(line) + 2


def test_index_has_no_mojibake(index_lines: list[str]) -> None:
    """INDEX.md 不得有编码损坏的行。

    2026-11-01 现场：9 行（2 条归档记录）在入库前就已损坏 —— UTF-8 字节被按 latin-1
    误解、多字节字符被切在行与行之间且丢了首字节，表格结构和中文都坏掉，
    而 80 个历史版本里都找不到完好原文。既有纪律的由来：中文内容禁用
    PowerShell `-replace` / `Set-Content`，一律用显式 UTF-8 读写。
    """
    bad = [i for i, l in enumerate(index_lines, 1) if _looks_like_mojibake(l)]
    assert not bad, (
        f"INDEX.md 有 {len(bad)} 行疑似编码损坏（UTF-8 被按 latin-1 误解）：行 {bad}\n"
        f"写中文内容请用显式 UTF-8 读写，不要经 PowerShell 的 -replace / Set-Content"
    )


# ================================================================ 判据自检
def test_mojibake_detector_separates_real_damage_from_normal_lines() -> None:
    """mojibake 判据要能分开"真损坏"和"正常的中文行"。

    正常行里 `·`、`—`、`→` 很常见，表面判据会误报；所以判据必须是"回卷后更像中文"。
    """
    normal = (
        "| `sampling-compliance-closure` | ✅ **25/25** 已归档 "
        "`_archive/41-x/` | **抽样合规闭环**：dataset 版本绑定 · 推断错报持久化 · "
        "删 legacy 引擎 → 新引擎；后端 236 passed。 |"
    )
    assert not _looks_like_mojibake(normal), "正常中文表格行被误判为 mojibake"

    damaged = "统一公式注册表：_REGISTRY 单一真源".encode("utf-8").decode("latin-1")
    assert _looks_like_mojibake(damaged), "真实 mojibake 没被判出来"


def test_dated_quote_pattern_does_not_match_archive_notes() -> None:
    """「带日期的速递条目」判据不得命中归档区里的说明性注记。

    第一版只看 `> **` 开头，把 7 条「> **`spec`(24/24)** 已于 2026-08-15 归档（见下）」
    误报成漂移 —— 那是有意写在归档区的注记。
    """
    note = "> **`g7-column-alignment-and-extraction-closure`(24/24)** 已于 2026-08-15 归档（见下）。"
    assert not _DATED_QUOTE.match(note), "归档注记被误判为放错位置的速递条目"
    entry = "> **2026-09-13 新建｜`d4-ipo-fraud-writeback-formula-io`（0/11）**：第三批"
    assert _DATED_QUOTE.match(entry), "真实速递条目没被判出来"


def test_cross_reference_pattern_matches_the_wordings_actually_used() -> None:
    """交叉引用正则必须覆盖仓库里真实出现过的写法。

    第一版只认「见下条」「见上条」，而本轮新写的文案是「见上一条」⇒ 守卫假红。
    判据自身也要有判据。
    """
    for wording in ("见下条", "见上条", "见上一条", "见下一条"):
        assert _CROSS_REF.search(f"……{wording}……"), f"交叉引用正则漏了写法：{wording}"
    for wording in ("见下文", "参见上面", "条见"):
        assert not _CROSS_REF.search(wording), f"交叉引用正则误命中：{wording}"
