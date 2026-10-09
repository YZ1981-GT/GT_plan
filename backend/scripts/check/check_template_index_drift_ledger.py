# -*- coding: utf-8 -*-
"""模板索引欠账台账：按循环分组输出，并把账本声明值与**现算值**对账。

spec: d1-sync-row-table-engine-and-d1-coverage · X5-j（2026-09-28）

═══ 为什么需要这个工具 ═══

`_template_index_drift_registry.INDEX_DRIFT_LEDGER` 记了 30 份权威模板的
「`_index.json` 声明的 size_kb ≠ 磁盘实际」欠账。既有判据
（`test_template_override_resolution`）只验「集合相等」—— 新增点名、失效点名，
够用但**只看在不在**：

* 账本里的 `index_kb / disk_kb` 是**记账时**的值。模板再改一次，这两个数就过期了，
  而集合语义看不见 —— 欠账条目还在，只是数字已经不对了；
* 30 条欠账平铺着，没有按循环归拢的视图 ⇒ 没法推动任何一条 lane 去清。

本工具补这两块：**现算对账**（过期即报）+ **按循环分组**（可查、可分派）。

═══ 与既有判据的分工 ═══

  既有判据：集合相等（新增/失效）—— 进 pytest，秒级
  本工具  ：数值对账 + 分组视图 —— 手动/按需跑，要读 30 个 xlsx 的 stat（毫秒级）

两者都不重算 `_index.json`。**重算整份索引是本 spec 明确否决的处置** ——
那会把其余 lane 的漂移一起静默吸收。正确做法始终是「只改自己那一条」。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
_TEMPLATES = _BACKEND / "wp_templates"
_INDEX_JSON = _TEMPLATES / "_index.json"

sys.path.insert(0, str(_BACKEND))
from tests.workpaper_sync._template_index_drift_registry import (  # noqa: E402
    INDEX_DRIFT_LEDGER,
)

#: 声明值与现算值允许的误差（KB）。`_index.json` 记的是一位小数，
#: 所以 0.05 足够覆盖四舍五入，再大就会掩盖真实改动。
_TOLERANCE_KB = 0.05


def _index_declared() -> dict[str, float]:
    """`_index.json` 里每份模板声明的 size_kb，key 归一为账本用的 `子目录\\文件名`。

    🔴 结构**现读实证**（2026-09-28）：顶层 `{description, total_files, files}`，
    `files[*]` = `{wp_code, filename, relative_path, format, size_kb, category}`，
    路径字段名是 `relative_path` 且**已经是反斜杠**形式（`A\\A1 财务报告程序表.xlsx`）。

    首版按 `templates[*].path` 猜，结果 30 条全报「索引缺失」—— 分组视图明明是对的，
    所以一眼能看出是解析错而不是数据错。这是「字段路径必现读、禁凭命名习惯推」那条
    铁律的又一次应验。
    """
    data = json.loads(_INDEX_JSON.read_text(encoding="utf-8"))
    out: dict[str, float] = {}
    for entry in data.get("files", []) if isinstance(data, dict) else []:
        rel = str(entry.get("relative_path") or "")
        size = entry.get("size_kb")
        if rel and isinstance(size, (int, float)):
            out[rel.replace("/", "\\")] = float(size)
    return out


def _disk_kb(rel: str) -> float | None:
    p = _TEMPLATES / rel.replace("\\", "/")
    if not p.exists():
        return None
    return round(p.stat().st_size / 1024, 1)


def run() -> dict[str, object]:
    declared = _index_declared()
    rows: list[dict[str, object]] = []
    for rel, entry in sorted(INDEX_DRIFT_LEDGER.items()):
        now_index = declared.get(rel)
        now_disk = _disk_kb(rel)
        stale_index = (
            now_index is not None and abs(now_index - entry.index_kb) > _TOLERANCE_KB
        )
        stale_disk = (
            now_disk is not None and abs(now_disk - entry.disk_kb) > _TOLERANCE_KB
        )
        rows.append(
            {
                "path": rel,
                "cycle": entry.cycle,
                "nature": entry.nature,
                "ledger_index_kb": entry.index_kb,
                "ledger_disk_kb": entry.disk_kb,
                "now_index_kb": now_index,
                "now_disk_kb": now_disk,
                "missing_on_disk": now_disk is None,
                "missing_in_index": now_index is None,
                "stale_index": stale_index,
                "stale_disk": stale_disk,
                # 仍在漂移？现算两值不等才算
                "still_drifted": (
                    now_index is not None
                    and now_disk is not None
                    and abs(now_index - now_disk) > _TOLERANCE_KB
                ),
            }
        )

    problems = [
        r for r in rows
        if r["stale_index"] or r["stale_disk"] or r["missing_on_disk"]
        or r["missing_in_index"] or not r["still_drifted"]
    ]
    by_cycle: dict[str, int] = {}
    for r in rows:
        by_cycle[str(r["cycle"])] = by_cycle.get(str(r["cycle"]), 0) + 1

    return {
        "ok": not problems,
        "total": len(rows),
        "by_cycle": dict(sorted(by_cycle.items())),
        "committed": sum(1 for r in rows if r["nature"] == "committed"),
        "worktree": sum(1 for r in rows if r["nature"] == "worktree"),
        "rows": rows,
        "problems": [r["path"] for r in problems],
    }


def _print_ledger(report: dict[str, object]) -> None:
    rows = list(report["rows"])  # type: ignore[arg-type]
    print(
        f"模板索引欠账台账：{report['total']} 份"
        f"（已提交漂移 {report['committed']} / 工作树临时态 {report['worktree']}）"
    )
    print(f"按循环分组：{report['by_cycle']}")
    last_cycle = None
    for r in rows:
        if r["cycle"] != last_cycle:
            cnt = report["by_cycle"][r["cycle"]]  # type: ignore[index]
            print(f"\n  [{r['cycle']} 循环] {cnt} 份")
            last_cycle = r["cycle"]
        idx, disk = r["now_index_kb"], r["now_disk_kb"]
        if idx is None or disk is None:
            state = "索引缺失" if idx is None else "磁盘缺失"
            print(f"     {r['path']} —— 🔴 {state}")
            continue
        pct = (disk - idx) / idx * 100 if idx else 0.0
        flags = []
        if r["stale_index"] or r["stale_disk"]:
            flags.append(
                f"账本值已过期(账本 {r['ledger_index_kb']}/{r['ledger_disk_kb']})"
            )
        if not r["still_drifted"]:
            flags.append("已不漂移 ⇒ 请从账本移除")
        tail = ("  🔴 " + "；".join(flags)) if flags else ""
        print(
            f"     {r['path']} —— 索引 {idx}KB / 磁盘 {disk}KB ({pct:+.1f}%)"
            f" [{r['nature']}]{tail}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=str, default=None)
    parser.add_argument(
        "--quiet", action="store_true", help="只给结论，不打印逐份台账"
    )
    args = parser.parse_args(argv)

    report = run()
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if not args.quiet:
        _print_ledger(report)

    if report["ok"]:
        print(
            f"\n✅ 台账与现算一致：{report['total']} 份逐份仍在漂移，"
            "声明值无过期，无缺失"
        )
        return 0

    print(
        f"\n❌ {len(report['problems'])} 份与现算不符 —— 逐条处置："
        "\n   · 账本值过期 ⇒ 更新 `INDEX_DRIFT_LEDGER` 里那一条的 index_kb/disk_kb"
        "\n   · 已不漂移   ⇒ 从账本移除（该 lane 已经清了这笔）"
        "\n   · 缺失       ⇒ 模板或索引条目被删，核对后移除账本条目"
        "\n   🔴 **不要**重算整份 `_index.json` —— 那会把其余 lane 的漂移一起吞掉。"
    )
    for p in report["problems"]:
        print(f"   [不符] {p}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
