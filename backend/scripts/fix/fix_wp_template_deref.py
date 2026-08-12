"""模板库解引用迁移 —— Wave 5 Task 19

spec: workpaper-import-export-lifecycle-closure（R6.1、R6.3~R6.8）

## 要解决什么

实测（2026-08-12）：`working_paper` 里有 **956 份**底稿的 `file_path` 直接指向
``backend/wp_templates/``（模板库本身），且 **955/956 份的路径与其他项目共享**
—— 304 个不同路径被 2~4 个项目复用（159 个路径被 4 个项目共享）。

后果有两层，都不可接受：

1. **写入污染模板库**：任何一个项目在自己的底稿上保存 xlsx，写的是模板库里那份
   文件。模板库是**运行时权威**（`wp_template_init_service` 据它生成底稿、
   `wp_template_finder` 以 `_index.json` 索引），被改一次影响此后所有新建项目。
2. **跨项目串数据**：A 项目改完，B 项目打开同一 `file_path` 看到 A 的内容。

⇒ 本脚本给每份底稿复制一份**项目内独立副本**，并把 `file_path` 指过去。

## 路径决策（2026-08-12 与用户确认）

目标：``backend/storage/projects/{project_id}/workpapers/{audit_cycle}/{wp_code}.xlsx``

两处都是实证后的选择，不是随手定的：

* **写 `backend/` 基准**而非仓库根 —— `wp_file_resolver._relative_bases()` 依次试
  ``Path.cwd()`` / ``BACKEND_ROOT`` / ``REPO_ROOT``，其注释写明「生产 cwd 就是
  BACKEND_ROOT」。写这里生产运行时**第一个候选就命中**，不依赖回退；且
  `backend/storage` 现有 162 个 xlsx，比仓库根的 63 个更像主用目录。
  （既成事实是分裂的：63 份在仓库根、38 份在 backend/，读取端靠三基准兜住了。）
* **沿用既有命名惯例**（带 `audit_cycle` 子目录、不加 wp_id 后缀）—— 平台里已有
  的 101 份正常底稿都是 ``workpapers/{cycle}/{code}.xlsx`` 形态。实测
  ``(project_id, wp_code)`` 在这 956 份里**完全唯一**（956 组 × 1），故无需
  wp_id 后缀去重；换一套命名会让同一目录下两种形态并存，日后排查困难。

## 不在本次范围（有意留白，写进台账 `out_of_scope`）

* **空 `file_path` 的 1564 份** —— 没有可复制的源，属 Task 5 自证层作业面。
* **181 份 `file_path` 指向不存在文件** —— 同样无源可复制（其中 30 份指向
  ``/tmp``、6 份是硬编码绝对路径 ``D:/GT_plan/...``）。属既存缺陷，只登记。
* **C24 那份 1,033,230 行 `checklist_responses`** —— 占全库 checklist 的 99.9%，
  此前实证「非空仅 695」，高度疑似脏数据。本迁移只改 `file_path`、不动 checklist，
  技术上无影响，故不碰，仅在台账 `notes` 标注。

## 安全设计

* 四档命令：``--check``（只读）/ ``--dry-run``（算全量不写盘）/
  ``--apply --confirm-destructive``（真执行）/ ``--rollback <ledger.json>``
* 无 ``--confirm-destructive`` 的 ``--apply`` 直接拒绝并 exit 2
* **幂等**：`file_path` 已不指向 `wp_templates` 即跳过；二次执行零变更
* **逐条隔离**：单条异常记 `failed[]` 继续，不让一条坏数据毁掉整批
* **冲突保护**：目标已存在且 sha256 不同 ⇒ 记 `conflicts[]` 跳过，绝不覆盖
* **回滚只反写 `file_path`，不删新文件** —— 删文件的回滚本身会造成数据丢失
* 迁移前后各跑一次 `resolve_wp_file` 全量 verdict 分布并 diff 落台账

## 🔴 判成败查数据，不看 exit code

`--apply` 可能被 Ctrl+C 中断而写入已提交（memory 记的坑）。跑完请用
``--check`` 复查剩余作业面，或读台账的 `migrated` 计数，不要只看返回值。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 允许从仓库根或 backend/ 直接跑
_THIS = Path(__file__).resolve()
_BACKEND_ROOT = _THIS.parents[2]
_REPO_ROOT = _THIS.parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("DB_DISABLE_SSL", "True")

#: 目标目录基准 —— 见模块 docstring「路径决策」
TARGET_BASE = _BACKEND_ROOT

#: 台账默认落点
LEDGER_DIR = _BACKEND_ROOT / "scripts" / "fix" / "_ledgers"

#: 判定「指向模板库」的子串（与 SQL 的 LIKE 条件同源）
TEMPLATE_MARKER = "wp_templates"

_SELECT_SQL = """
SELECT
  w.id::text          AS wp_id,
  w.project_id::text  AS project_id,
  w.file_path         AS file_path,
  wi.wp_code          AS wp_code,
  wi.audit_cycle      AS audit_cycle,
  (SELECT count(*) FROM checklist_responses cr WHERE cr.wp_id = w.id) AS cr_n
FROM working_paper w
LEFT JOIN wp_index wi ON wi.id = w.wp_index_id
WHERE w.file_path IS NOT NULL
  AND btrim(w.file_path) <> ''
"""


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resolve_source(raw: str) -> Path | None:
    """把库里的相对/绝对 `file_path` 解析成磁盘上真实存在的源文件。

    与 `wp_file_resolver._relative_bases()` 同样试多个基准 —— 库里的路径既有
    仓库根相对也有 backend/ 相对，只试一个必然漏。
    """
    s = str(raw).strip()
    if not s:
        return None
    p = Path(s)
    if p.is_absolute():
        return p if p.is_file() else None
    for base in (_BACKEND_ROOT, _REPO_ROOT, Path.cwd()):
        cand = base / p
        if cand.is_file():
            return cand
    return None


def _target_rel(project_id: str, audit_cycle: str, wp_code: str) -> str:
    """目标**相对**路径（存库用，POSIX 分隔符）。

    存相对路径是有意的：`resolve_wp_file` 会在三个基准下都试，相对路径能在
    「生产从 backend/ 跑」与「脚本/测试从仓库根跑」两种 cwd 下都解析成功；
    存绝对路径会把开发机盘符写进库，换机即失效。
    """
    cycle = (audit_cycle or "").strip() or "_"
    return f"storage/projects/{project_id}/workpapers/{cycle}/{wp_code}.xlsx"


def _is_template_ref(file_path: str | None) -> bool:
    return bool(file_path) and TEMPLATE_MARKER in str(file_path).replace("\\", "/")


def _safe_name(value: str) -> bool:
    """目标名分段合法性（防路径穿越与非法字符写进磁盘）。"""
    bad = set('<>:"|?*\x00') | {"/", "\\"}
    return bool(value) and value not in {".", ".."} and not (set(value) & bad)


# ---------------------------------------------------------------------------
# 数据读取
# ---------------------------------------------------------------------------


async def _load_rows() -> list[dict[str, Any]]:
    from sqlalchemy import text

    from app.core.database import engine

    async with engine.connect() as conn:
        res = await conn.execute(text(_SELECT_SQL))
        return [dict(r) for r in res.mappings()]


def _verdict_distribution(rows: list[dict[str, Any]]) -> dict[str, int]:
    """全量 `resolve_wp_file` verdict 分布（迁移前后各跑一次做 diff）。

    `allow_template_fallback=False` —— 这里要看的是「底稿自己的文件在不在」，
    开回退会把所有缺失都染成 `template_fallback`，diff 就失去意义。
    """
    from app.services.wp_export.wp_file_resolver import resolve_wp_file

    dist: Counter[str] = Counter()
    for r in rows:
        res = resolve_wp_file(
            r.get("file_path"), r.get("wp_code"), allow_template_fallback=False
        )
        dist[res.verdict] += 1
    return dict(dist)


# ---------------------------------------------------------------------------
# 计划
# ---------------------------------------------------------------------------


def _build_plan(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """算出迁移计划（纯函数，不碰磁盘写入、不改库）。"""
    plan: list[dict[str, Any]] = []
    skipped_not_template: list[str] = []
    blocked: list[dict[str, Any]] = []
    out_of_scope: list[dict[str, Any]] = []

    seen_targets: dict[str, str] = {}

    for r in rows:
        wp_id = r["wp_id"]
        raw = r.get("file_path")

        if not _is_template_ref(raw):
            skipped_not_template.append(wp_id)
            src_missing = _resolve_source(str(raw or "")) is None
            if src_missing:
                out_of_scope.append(
                    {
                        "wp_id": wp_id,
                        "file_path": raw,
                        "reason": "file_path 指向不存在的文件（无源可复制，属既存缺陷）",
                    }
                )
            continue

        wp_code = (r.get("wp_code") or "").strip()
        cycle = (r.get("audit_cycle") or "").strip()

        if not wp_code:
            blocked.append({"wp_id": wp_id, "reason": "wp_code 缺失（JOIN 未命中）"})
            continue
        if not (_safe_name(wp_code) and _safe_name(cycle or "_")):
            blocked.append(
                {"wp_id": wp_id, "reason": f"名称含非法字符: cycle={cycle!r} code={wp_code!r}"}
            )
            continue

        src = _resolve_source(str(raw))
        if src is None:
            blocked.append({"wp_id": wp_id, "reason": f"源文件不存在: {raw}"})
            continue

        rel = _target_rel(r["project_id"], cycle, wp_code)
        if rel in seen_targets and seen_targets[rel] != wp_id:
            blocked.append(
                {
                    "wp_id": wp_id,
                    "reason": f"目标路径与 {seen_targets[rel]} 冲突: {rel}",
                }
            )
            continue
        seen_targets[rel] = wp_id

        plan.append(
            {
                "wp_id": wp_id,
                "project_id": r["project_id"],
                "wp_code": wp_code,
                "audit_cycle": cycle,
                "old_path": raw,
                "src_abs": str(src),
                "new_path": rel,
                "src_size": src.stat().st_size,
                "cr_n": int(r.get("cr_n") or 0),
            }
        )

    return {
        "plan": plan,
        "skipped_not_template": len(skipped_not_template),
        "blocked": blocked,
        "out_of_scope": out_of_scope,
    }


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


async def _apply(plan: list[dict[str, Any]], *, ledger_path: Path) -> dict[str, Any]:
    """真执行：复制文件 + 改写 `file_path`。逐条隔离失败。"""
    from sqlalchemy import text

    from app.core.database import engine

    migrated: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for item in plan:
        try:
            src = Path(item["src_abs"])
            dst = TARGET_BASE / item["new_path"]
            sha_before = _sha256(src)

            if dst.exists():
                sha_dst = _sha256(dst)
                if sha_dst != sha_before:
                    conflicts.append(
                        {
                            **{k: item[k] for k in ("wp_id", "new_path")},
                            "reason": "目标已存在且内容不同，跳过（绝不覆盖）",
                            "sha_existing": sha_dst,
                            "sha_source": sha_before,
                        }
                    )
                    continue
                # 内容相同 ⇒ 视为已复制，仅需改库（幂等路径）
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

            sha_after = _sha256(dst)
            if sha_after != sha_before:
                failed.append(
                    {
                        "wp_id": item["wp_id"],
                        "reason": "复制后哈希不符（复制未完整），已跳过改库",
                        "sha_before": sha_before,
                        "sha_after": sha_after,
                    }
                )
                continue

            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE working_paper SET file_path = :p WHERE id = CAST(:i AS uuid)"
                    ),
                    {"p": item["new_path"], "i": item["wp_id"]},
                )

            migrated.append(
                {
                    "wp_id": item["wp_id"],
                    "project_id": item["project_id"],
                    "wp_code": item["wp_code"],
                    "old_path": item["old_path"],
                    "new_path": item["new_path"],
                    "sha256_before": sha_before,
                    "sha256_after": sha_after,
                    "ts": _now(),
                }
            )
        except Exception as exc:  # noqa: BLE001 — 逐条隔离，坏一条不毁整批
            failed.append(
                {
                    "wp_id": item.get("wp_id"),
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )

    return {"migrated": migrated, "conflicts": conflicts, "failed": failed}


async def _rollback(ledger_path: Path) -> dict[str, Any]:
    """按台账反写 `file_path`。

    🔴 **不删新文件** —— 回滚只应撤销「指针」，删数据的回滚本身就是数据丢失风险。
    新文件留在磁盘上，二次 `--apply` 时会因哈希相同走幂等路径，不会重复复制。
    """
    from sqlalchemy import text

    from app.core.database import engine

    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    entries = data.get("migrated") or []
    reverted: list[str] = []
    failed: list[dict[str, Any]] = []

    for e in entries:
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE working_paper SET file_path = :p WHERE id = CAST(:i AS uuid)"
                    ),
                    {"p": e["old_path"], "i": e["wp_id"]},
                )
            reverted.append(e["wp_id"])
        except Exception as exc:  # noqa: BLE001
            failed.append({"wp_id": e.get("wp_id"), "reason": f"{type(exc).__name__}: {exc}"})

    return {"reverted": len(reverted), "failed": failed, "ledger": str(ledger_path)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_report(title: str, payload: dict[str, Any], *, out_dir: Path | None = None) -> None:
    """报告落文件 + 摘要打屏。

    🔴 报告用 `Path.write_text(encoding='utf-8')` 落盘，不靠 PowerShell 重定向
    —— PS 的 `>` / `Out-File` 会把 Python 输出的中文腌成乱码（memory 已记）。

    Args:
        out_dir: 报告落点。默认 `LEDGER_DIR`（版本库内，迁移凭证）。
            **守卫测试必须传临时目录** —— 否则每跑一次 `--check` 就往版本库
            塞一个 JSON，实测半小时内累积了 20 个。只读诊断没有留存价值，
            真正的凭证是 `--dry-run` / `--apply` / `--rollback` 的台账。
    """
    base = out_dir or LEDGER_DIR
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = base / f"deref_{title}_{stamp}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{title}] 报告已落盘: {out}")
    for key in (
        "total_rows",
        "to_migrate",
        "skipped_not_template",
        "blocked_n",
        "out_of_scope_n",
        "migrated_n",
        "conflicts_n",
        "failed_n",
        "copy_mb",
    ):
        if key in payload:
            print(f"    {key:<22} {payload[key]}")
    if "verdict_before" in payload:
        print(f"    verdict_before        {payload['verdict_before']}")
    if "verdict_after" in payload:
        print(f"    verdict_after         {payload['verdict_after']}")


async def main_async(args: argparse.Namespace) -> int:
    out_dir = Path(args.out) if args.out else None

    if args.rollback:
        result = await _rollback(Path(args.rollback))
        _print_report("rollback", result, out_dir=out_dir)
        return 0

    rows = await _load_rows()
    built = _build_plan(rows)
    plan = built["plan"]

    base_payload: dict[str, Any] = {
        "mode": "check" if args.check else ("dry-run" if args.dry_run else "apply"),
        "ts": _now(),
        "target_base": str(TARGET_BASE),
        "total_rows": len(rows),
        "to_migrate": len(plan),
        "skipped_not_template": built["skipped_not_template"],
        "blocked_n": len(built["blocked"]),
        "blocked": built["blocked"][:50],
        "out_of_scope_n": len(built["out_of_scope"]),
        "out_of_scope": built["out_of_scope"][:20],
        "copy_mb": round(sum(i["src_size"] for i in plan) / 1024 / 1024, 1),
        "notes": [
            "空 file_path 的 1564 份不在本迁移范围（无可复制源，属 Task 5 自证层）",
            "C24 那份 1,033,230 行 checklist 未做任何处理（只改 file_path，不动 checklist）",
        ],
    }

    if args.check:
        base_payload["verdict_before"] = _verdict_distribution(rows)
        base_payload["plan_sample"] = plan[:10]
        _print_report("check", base_payload, out_dir=out_dir)
        return 0

    if args.dry_run:
        base_payload["verdict_before"] = _verdict_distribution(rows)
        base_payload["plan_full"] = plan
        _print_report("dryrun", base_payload, out_dir=out_dir)
        return 0

    # ─── apply ────────────────────────────────────────────────────────────
    if not args.confirm_destructive:
        print(
            "拒绝执行：--apply 属破坏性操作（复制 "
            f"{base_payload['copy_mb']} MB + 改写 {len(plan)} 条 file_path），"
            "必须显式加 --confirm-destructive"
        )
        return 2

    verdict_before = _verdict_distribution(rows)
    result = await _apply(plan, ledger_path=LEDGER_DIR)

    rows_after = await _load_rows()
    payload = {
        **base_payload,
        "verdict_before": verdict_before,
        "verdict_after": _verdict_distribution(rows_after),
        "migrated_n": len(result["migrated"]),
        "conflicts_n": len(result["conflicts"]),
        "failed_n": len(result["failed"]),
        "migrated": result["migrated"],
        "conflicts": result["conflicts"],
        "failed": result["failed"],
    }
    _print_report("apply", payload, out_dir=out_dir)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="模板库解引用迁移：把指向 wp_templates 的 file_path 改成项目内独立副本"
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="只读报告（作业面 + verdict 分布）")
    g.add_argument("--dry-run", action="store_true", help="算出全量计划与台账，不写盘不改库")
    g.add_argument("--apply", action="store_true", help="真执行（须配 --confirm-destructive）")
    g.add_argument("--rollback", metavar="LEDGER_JSON", help="按台账反写 file_path（不删文件）")
    ap.add_argument(
        "--confirm-destructive",
        action="store_true",
        help="确认执行破坏性操作（仅 --apply 需要）",
    )
    ap.add_argument(
        "--out",
        metavar="DIR",
        help="报告落点目录（默认版本库内 _ledgers/；守卫测试应传临时目录，"
        "避免只读诊断报告在版本库里无限累积）",
    )
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
