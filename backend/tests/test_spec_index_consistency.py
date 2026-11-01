"""`.kiro/specs/INDEX.md` 的漂移 / 重复守卫。

2026-11-01 立：用户「刚从 git 同步拉取下来，表格存在漂移重复问题」。现算出的真问题是
归档动作只做了一半 —— spec 目录已移进 `_archive/NNN-<name>/`，但 INDEX 里
①「一、Active Specs」表的那一行没删（活跃表 24 行里 12 行的 spec 已归档）
②顶部速递行的链接还指向旧的活跃路径（17 个路径 / 20 处引用全部点不开）。
两者都不会被任何现有门禁看见，所以会一直累积。

本文件把"归档必须三件齐"写成可执行判据：目录移走、活跃表删行、链接改向。

对**历史债**用棘轮（只许减少）而不是硬断言 —— 恒红门禁等于没有门禁：
  · 归档区表格里重复出现的 spec（2026-07/08 的历史轨迹，append-only 不回填改写）
  · `_archive` 序号撞号（改目录名会断其他文档里的引用）
  · 活跃 spec 未被 INDEX 收录（别人在建的 spec，不代写其状态）
每条棘轮都配"基线条目必须真的还成立"的反向断言，防止基线变成加一行就能变绿的后门。
"""

from __future__ import annotations

import re
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
# 活跃 spec 目录未被 INDEX 任何链接提及（只许减少）
_UNINDEXED_ACTIVE_SPEC_BASELINE = {
    "adjustment-practice-linkage-integrity-closure",
    "attachment-platform-cross-module-closure",
    "consolidation-run-and-workpaper-lifecycle-closure",
    "note-table-structure-formula-pull-closure",
    "platform-heavy-jobs-and-capacity-closure",
    "platform-release-blocker-closure",
}


# ---------------------------------------------------------------- 读取与解析
@pytest.fixture(scope="module")
def index_lines() -> list[str]:
    if not INDEX_PATH.exists():
        pytest.skip(f"INDEX.md 不存在：{INDEX_PATH}")
    return INDEX_PATH.read_bytes().decode("utf-8").splitlines()


@pytest.fixture(scope="module")
def archived_specs() -> dict[str, str]:
    """spec 名 -> `_archive` 下的目录名。"""
    if not ARCHIVE_DIR.exists():
        pytest.skip(f"_archive 不存在：{ARCHIVE_DIR}")
    out: dict[str, str] = {}
    for d in sorted(ARCHIVE_DIR.iterdir()):
        if not d.is_dir():
            continue
        m = _ARCHIVE_NAME.match(d.name)
        out[m.group(2) if m else d.name] = d.name
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
    """「一、Active Specs」表里不得出现已经归档的 spec。

    删行前要先确认它在速递区已有记录，否则信息会丢 —— 本轮那 2 个速递区无记录的
    就是先补了速递行才删的。
    """
    start, end = _active_table_span(index_lines)
    stale: list[tuple[int, str]] = []
    for i in range(start, end):
        line = index_lines[i]
        if not line.strip().startswith("|"):
            continue
        m = _SPEC_BACKTICK_LINK.search(_first_cell(line))
        if m and m.group(1) in archived_specs:
            stale.append((i + 1, m.group(1)))

    assert not stale, (
        f"「一、Active Specs」表里有 {len(stale)} 行的 spec 已经归档，归档时漏删：\n"
        + "\n".join(
            f"  行 {ln}  {name}  -> _archive/{archived_specs[name]}/" for ln, name in stale
        )
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
    text = "\n".join(index_lines)
    mentioned = {
        t.split("/")[0] for t in _LOCAL_LINK.findall(text) if t.split("/")[0]
    }
    return {n for n in active if n not in mentioned}


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
