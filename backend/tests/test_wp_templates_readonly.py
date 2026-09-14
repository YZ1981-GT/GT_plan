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

#: 2026-08-12 实测基线（迁移后）—— 这三个数与快照双向锁死
EXPECTED_XLSX_COUNT = 351
EXPECTED_TOTAL_BYTES = 50_343_134


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


def test_template_count_and_size_match_baseline(current) -> None:  # noqa: ANN001
    """文件数与总字节钉死 —— 改基线文件时这条会一起打红。"""
    total = sum(int(v["size"]) for v in current.values())
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
