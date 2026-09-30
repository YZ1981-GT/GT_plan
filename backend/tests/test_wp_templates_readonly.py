"""模板库只读守卫 —— Wave 5 Task 20

spec: workpaper-import-export-lifecycle-closure（R6.1、R6.2）

## 为什么需要这条守卫

``backend/wp_templates/`` 是**运行时权威**：`wp_template_init_service` 据它生成
底稿、`wp_template_finder` 以 `_index.json` 索引它。它被改一个字节，此后所有新建
项目都继承那个改动。

Task 19 迁移前的实测显示这个风险是真的：**956 份底稿的 `file_path` 直接指向模板
库**，且 955 份与其他项目共享路径 —— 任一项目保存 xlsx 就写进模板库。迁移已把
它们改成项目内独立副本（迁移后实测 `仍指模板库 = 0`、`仍跨项目共享路径 = 0`），
本守卫负责**钉住这个状态不再回退**。

## 判据：内容快照，不是「有没有人写代码去改」

只查「代码里有没有对 wp_templates 的写操作」是 grep 式判据 —— 绕过方式太多
（拼路径、经 `shutil`、经 `openpyxl.save`）。这里直接对 351 个 xlsx 做
``(相对路径, size, sha256)`` 快照比对：**谁改的都拦得住**。

快照基线落 ``backend/tests/_snapshots/wp_templates_baseline.json``，
首次运行自动生成（并打印提示）；此后任何差异都打红。

🔴 基线文件本身也可能被人"顺手更新"以让守卫变绿。故额外断言：
文件数、总字节、以及 `_index.json` 的存在性单独钉死，改基线时这三条会一起变，
不可能悄无声息。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_TEMPLATES = _REPO / "backend" / "wp_templates"
_SNAPSHOT = Path(__file__).resolve().parent / "_snapshots" / "wp_templates_baseline.json"

#: 实测基线 —— 这两个数与快照双向锁死。
#:
#: 🔴 2026-09-30 重算（D4 重复本删除 + 补齐早已提交但从未回填的净化改动）。
#: 上一版常量写的是 `50_343_134`，而当时快照文件逐份加总只有 `50_325_282`
#: —— **常量与快照本就互相矛盾 17,852 B**，两条断言分别对着两个不同的事实，
#: 谁都说不清哪个是真的。本次两者一起重算，逐份归因如下（合计 −902,367 B）：
#:
#:   + `D/D4 收入底稿.xlsx`      199,176 B  基线之后才入库（`d3b3d80d9` 2026-09-14）
#:   - `D/D4收入底稿.xlsx`      −352,950 B  与上面那份是同一底稿的重复入库，
#:                                          **本次删除**（未净化，36 个 externalLink 部件）
#:   ~ `D/D3 预收账款.xlsx`      −58,714 B  ┐
#:   ~ `D/D5 应收款项融资.xlsx`  −59,476 B  │ 净化（去外部链接）后**早已提交**，
#:   ~ `D/D6 合同资产.xlsx`     −296,101 B  │ 只是基线一直没回填：
#:   ~ `D/D7 合同负债.xlsx`     −290,774 B  │ D 循环 `1a0b55651`（2026-09-12）
#:   ~ `L/L5 长期应付款.xlsx`    −25,740 B  │ L 循环 `3036967ea`（2026-09-27）
#:   ~ `L/L6 专项应付款.xlsx`    −17,788 B  ┘ 现算六份 externalLink 部件均为 0
#:
#: 数量不变（删 1 份、基线补记 1 份）。
EXPECTED_XLSX_COUNT = 351
EXPECTED_TOTAL_BYTES = 49_422_915

#: 允许与基线不符的**未提交工作树改动**（不是永久豁免）。
#:
#: 基线描述的是**已提交状态**；别条 lane 在工作树里改了模板但还没提交时，本守卫会把
#: 那份差异报成「内容被改」。直接豁免文件名等于开后门，所以每条都必须**可伪证**：
#: `test_worktree_drift_allowlist_entries_are_really_uncommitted` 会去查 `git status`，
#: 一旦该 lane 提交了（或撤销了）改动，条目立刻失效并打红，逼着回来重算基线。
#:
#: `M/M10 其他权益工具.xlsx`：M 循环 lane 的 openpyxl 往返改写（139,234 → 115,677 B）。
#: 实测它**丢部件**——`xl/printerSettings/*.bin`（11 个）、`xl/calcChain.xml`、
#: `xl/sharedStrings.xml`、8 个 worksheet `_rels`；comments 从 `xl/comments1.xml`
#: 迁到 `xl/comments/comment1.xml`、`vmlDrawing` 迁到 `commentsDrawing`。
#: 属有损改写，**本轮不代它提交**、也不把它固化进基线。
WORKTREE_DRIFT_ALLOWLIST: dict[str, str] = {
    "M/M10 其他权益工具.xlsx": "M 循环 lane 未提交的 openpyxl 往返改写（丢 printerSettings/calcChain）",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _snapshot() -> dict[str, dict[str, object]]:
    """当前模板库快照：相对路径 → {size, sha256}。"""
    assert _TEMPLATES.is_dir(), (
        f"模板库目录不存在：{_TEMPLATES}（守卫必须打红，不是跳过）"
    )
    out: dict[str, dict[str, object]] = {}
    for path in sorted(_TEMPLATES.rglob("*.xlsx")):
        # 跳过 Office/WPS 锁文件（用户开着文件时产生，不属模板内容）
        if path.name.startswith("~$"):
            continue
        rel = path.relative_to(_TEMPLATES).as_posix()
        out[rel] = {"size": path.stat().st_size, "sha256": _sha256(path)}
    assert out, "扫不到任何 xlsx —— 扫描逻辑失效，后续断言会全体假绿"
    return out


@pytest.fixture(scope="module")
def current() -> dict[str, dict[str, object]]:
    return _snapshot()


def _uncommitted_template_paths() -> set[str]:
    """`wp_templates/` 下**未提交**（工作树或暂存区与 HEAD 不同）的模板相对路径。"""
    import subprocess

    out = subprocess.run(
        ["git", "status", "--porcelain", "--", "backend/wp_templates"],
        cwd=str(_REPO), capture_output=True,
    ).stdout.decode("utf-8", "replace")
    paths: set[str] = set()
    for line in out.splitlines():
        if len(line) < 4:
            continue
        p = line[3:].strip().strip('"')
        # 重命名形如 `old -> new`，取新名
        if " -> " in p:
            p = p.split(" -> ", 1)[1]
        prefix = "backend/wp_templates/"
        if p.startswith(prefix):
            paths.add(p[len(prefix):])
    return paths


def test_worktree_drift_allowlist_entries_are_really_uncommitted() -> None:
    """🔴 白名单必须可伪证：每条都得**真的**是未提交改动，否则条目失效即打红。

    没有这一条，白名单就是「写上名字就变绿」的后门 —— 别的 lane 一提交（或撤销），
    基线与磁盘就重新自洽，而那条豁免会继续静默吞掉此后**任何**对该文件的改动。
    """
    if not WORKTREE_DRIFT_ALLOWLIST:
        pytest.skip("白名单为空 —— 无条目需要核验（这是期望的终态）")
    uncommitted = _uncommitted_template_paths()
    stale = sorted(set(WORKTREE_DRIFT_ALLOWLIST) - uncommitted)
    assert not stale, (
        f"白名单里这些条目已经不是未提交改动了：{stale}\n"
        "→ 对应 lane 已提交或已撤销 ⇒ 请从 WORKTREE_DRIFT_ALLOWLIST 删掉该条，"
        "并重算 EXPECTED_TOTAL_BYTES 与快照基线（提交了就该进基线）"
    )


def test_template_count_and_size_match_baseline(current) -> None:  # noqa: ANN001
    """文件数与总字节钉死 —— 改基线文件时这条会一起打红。

    总字节按**提交态**比对：白名单里的未提交改动按其 HEAD 字节折算回去，
    否则别 lane 的在途改写会让这条常年红（而常年红等于没有门）。
    """
    import subprocess

    total = sum(int(v["size"]) for v in current.values())
    for rel in WORKTREE_DRIFT_ALLOWLIST:
        path = _TEMPLATES / rel
        if not path.is_file():
            continue
        head = subprocess.run(
            ["git", "show", f"HEAD:backend/wp_templates/{rel}"],
            cwd=str(_REPO), capture_output=True,
        )
        if head.returncode == 0:
            total += len(head.stdout) - path.stat().st_size
    assert len(current) == EXPECTED_XLSX_COUNT, (
        f"模板库 xlsx 数量从 {EXPECTED_XLSX_COUNT} 变成 {len(current)}\n"
        "→ 新增/删除模板属有意变更时，请同时更新 EXPECTED_XLSX_COUNT 与快照基线，"
        "并在 spec 里说明来源（模板库是运行时权威，改动会影响此后所有新建项目）"
    )
    assert total == EXPECTED_TOTAL_BYTES, (
        f"模板库总字节从 {EXPECTED_TOTAL_BYTES} 变成 {total}（差 {total - EXPECTED_TOTAL_BYTES:+d}）\n"
        "→ 有文件内容被改动。若是有意更新模板，请更新基线并说明"
    )


def test_index_json_present() -> None:
    """`_index.json` 必须在 —— `wp_template_finder` 靠它索引，丢了模板库即失效。"""
    idx = _TEMPLATES / "_index.json"
    assert idx.is_file(), f"{idx} 缺失 ⇒ wp_template_finder 无法索引模板库"
    data = json.loads(idx.read_text(encoding="utf-8"))
    assert data, "_index.json 为空"


def test_snapshot_matches_baseline(current) -> None:  # noqa: ANN001
    """🔴 逐文件 (相对路径, size, sha256) 与基线相等。

    首次运行会生成基线并**跳过**本条（并打印路径）；此后任何差异都打红。
    """
    if not _SNAPSHOT.is_file():
        _SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        _SNAPSHOT.write_text(
            json.dumps(current, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
        )
        pytest.skip(f"基线首次生成：{_SNAPSHOT}（请提交它，此后本条即生效）")

    baseline = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))

    added = sorted(set(current) - set(baseline))
    removed = sorted(set(baseline) - set(current))
    changed = sorted(
        rel
        for rel in set(current) & set(baseline)
        if current[rel]["sha256"] != baseline[rel]["sha256"]
        # 白名单条目的「真的没提交」由上面那条独立断言看守，这里只做减法
        and rel not in WORKTREE_DRIFT_ALLOWLIST
    )

    problems: list[str] = []
    if added:
        problems.append(f"新增 {len(added)} 个: {added[:5]}")
    if removed:
        problems.append(f"删除 {len(removed)} 个: {removed[:5]}")
    if changed:
        problems.append(f"内容被改 {len(changed)} 个: {changed[:5]}")

    assert not problems, (
        "模板库发生变化（它是运行时权威，改动会影响此后所有新建项目）：\n"
        + "\n".join(f"  {p}" for p in problems)
        + "\n→ 若是有意更新模板：删除基线文件重新生成 + 同步 EXPECTED_* 常量 + "
        "在 spec 写明变更来源"
    )


def test_guard_detects_single_byte_change(tmp_path: Path) -> None:
    """反向自检：改一个字节必须能被检出。

    不动真模板库 —— 用真实模板复制到 tmp_path，改 1 字节后比对哈希。
    这验证的是「哈希判据本身有效」，而非「我相信 sha256 有效」。
    """
    src = next(
        (p for p in sorted(_TEMPLATES.rglob("*.xlsx")) if not p.name.startswith("~$")),
        None,
    )
    assert src is not None, "模板库里找不到 xlsx —— 无法做反向自检"

    copy = tmp_path / src.name
    copy.write_bytes(src.read_bytes())
    assert _sha256(copy) == _sha256(src), "复制后哈希应相同"

    data = bytearray(copy.read_bytes())
    data[len(data) // 2] ^= 0xFF  # 翻转中间一个字节
    copy.write_bytes(bytes(data))

    assert _sha256(copy) != _sha256(src), (
        "改了一个字节但哈希没变 ⇒ 哈希判据失效，上面的快照断言全体不可信"
    )
    assert copy.stat().st_size == src.stat().st_size, (
        "本自检故意只改内容不改长度 —— 若长度也变了，说明验的不是纯内容判据"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 连库断言 —— 🔴 一次 asyncio.run 取全部快照
#
# memory 铁律：连库守卫必须用**一次** `asyncio.run` 取全部快照。每个测试各自
# `asyncio.run` 会各建一个连接池并在退出时关掉 event loop，第二个测试起就报
# `Event loop is closed` / `NoneType has no attribute send` —— 表现为「某条断言
# 无关地失败」，很容易被误判成业务缺陷。本文件初版就踩了这个坑。
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def db_snapshot() -> dict[str, object]:
    """一次连库取齐全部需要的事实。"""
    import asyncio
    import os

    os.environ.setdefault("DB_DISABLE_SSL", "True")

    async def _collect() -> dict[str, object]:
        from sqlalchemy import text

        from app.core.database import engine

        async with engine.connect() as conn:
            tpl_refs = int(
                (
                    await conn.execute(
                        text(
                            "SELECT count(*) FROM working_paper "
                            "WHERE file_path LIKE '%wp_templates%'"
                        )
                    )
                ).scalar()
                or 0
            )
            shared_rows = (
                await conn.execute(
                    text(
                        """
                        SELECT file_path, count(DISTINCT project_id) AS proj_n
                        FROM working_paper
                        WHERE file_path IS NOT NULL AND btrim(file_path) <> ''
                        GROUP BY file_path
                        HAVING count(DISTINCT project_id) > 1
                        ORDER BY 2 DESC
                        LIMIT 10
                        """
                    )
                )
            ).all()
            migrated = int(
                (
                    await conn.execute(
                        text(
                            "SELECT count(*) FROM working_paper WHERE file_path ~ "
                            "'^storage/projects/[^/]+/workpapers/[A-Z]/'"
                        )
                    )
                ).scalar()
                or 0
            )
        return {
            "template_refs": tpl_refs,
            "shared": [(r[0], int(r[1])) for r in shared_rows],
            "migrated_shape": migrated,
        }

    return asyncio.run(_collect())


def test_no_workpaper_points_into_template_library(db_snapshot) -> None:  # noqa: ANN001
    """🔴 库里不得再有 `file_path` 指向模板库（Task 19 迁移成果）。

    行为判据：迁移前 956 份指向模板库，迁移后 0 份。
    有人新建底稿时若又把 `file_path` 写成模板库路径，这里立刻打红。
    """
    n = db_snapshot["template_refs"]
    assert n == 0, (
        f"有 {n} 份底稿的 file_path 仍指向模板库 ⇒ 保存底稿会写坏运行时权威模板，"
        "且多项目共享同一路径会串数据。\n"
        "→ 跑 python backend/scripts/fix/fix_wp_template_deref.py --check 看作业面"
    )


def test_no_file_path_shared_across_projects(db_snapshot) -> None:  # noqa: ANN001
    """同一 `file_path` 不得被多个项目共用（Task 19 迁移成果）。

    迁移前 303 个源路径被 2~4 个项目共享；迁移后 0。
    共享路径 = A 项目改完 B 项目看到 A 的内容，属静默串数据。
    """
    shared = db_snapshot["shared"]
    assert not shared, (
        "以下 file_path 被多个项目共用（改一处会串到别的项目）：\n"
        + "\n".join(f"  {p[:90]} ← {n} 个项目" for p, n in shared)  # type: ignore[misc]
    )


def test_migration_result_still_in_place(db_snapshot) -> None:  # noqa: ANN001
    """迁移成果规模不得缩水 —— 防有人批量改回或删记录。

    2026-08-12 迁移产出 956 份「带 cycle 子目录」形态。
    """
    n = db_snapshot["migrated_shape"]
    assert n >= 956, (
        f"迁移形态的底稿只剩 {n} 份（基线 956）⇒ 迁移成果被回退或记录被删"
    )
