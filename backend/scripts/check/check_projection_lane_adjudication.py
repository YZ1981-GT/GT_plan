#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""projection lane 裁决与首版发布链的回归门（F4）。

**Spec: published-representation-production-path-and-lane-adjudication** · Task 9.1
Requirements: 8.1, 8.4, 8.5, 8.8, 9.3, 9.4, 12.1, 12.2, 12.3, 12.4, 12.5, 7.8

═══ 本门只做四件事 ═══════════════════════════════════════════════════════════════

R1  **复用** Task 44 门的读数（不另造）—— 直接消费它 `--json` 的
    `pilots.<entry>.finalize_signals.{adapter_registered, capability_enabled}` 与顶层
    `result_distribution`。
R2  PG 只读现查：至少一条 representation 绑定 `projection_contract` bundle，且其
    `entry_id` 是 manifest entry（非 `opaque-` 命名空间）。
R3  结构判据：candidate 路径产不出首版；本 spec 范围边界的**结构缺席**。
R4  capability 变更纪律：manifest 出现 `bidirectional` 时，overlay 必须已 reviewed 且
    `approved_source_digest` 复核门未被绕过。

═══ 🔴 R1 按 Requirement 12.6 拆两阶段（2026-09-03 Open Gates 裁决）═══════════════

**阶段一（本 spec 交付，本门判它）**：只证「**供给门放行**」——
`registry._describe_entry_supply` 对该 entry 返回 `None`。
判据落在**供给门返回值**上，**不**落在 `adapter_registered`。

**阶段二（本 spec 不做）**：capability 翻转致 `adapter_registered` False→True。
它需要 manifest 重生成，而更新 `approved_source_digest` 须人工复核 mount diff
（owner = Task 67 登记的「1/67 复核方」）。

⇒ 本门**不得**把 `adapter_registered=True` 写成阶段一的通过条件。那会让本 spec 永远无法
收口，或诱导去绕 `approved_source_digest` 复核门 —— 后者已被 Requirement 7.8 明令禁止。
`adapter_registered` 仍**如实报告**，只是不作为通过条件（Requirement 12.6）。

用法（仓库根，Windows PowerShell）::

    python backend/scripts/check/check_projection_lane_adjudication.py
    python backend/scripts/check/check_projection_lane_adjudication.py --json out.json
    python backend/scripts/check/check_projection_lane_adjudication.py \\
        --task44-json backend/data/task44.json --baseline old.json
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

_REPO: Final[Path] = Path(__file__).resolve().parents[3]
_BACKEND: Final[Path] = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))

GATE_VERSION: Final[str] = "projection-lane-adjudication-gate/1"

#: 本 spec 的交付物 —— R3 的范围边界判据在这些文件上做**结构缺席**检查
#: 🔴 **测试文件也必须在内**（F6~F9）。首版只收 F1~F5 五个生产/脚本文件，
#: 而越界同样可以发生在测试里 —— 例如某条判据为了「让它过」而去读
#: `allow_external_relationships`，或在测试里新写一处 `startswith("opaque-")`
#: 判定（那正是 `_OUT_OF_SCOPE_SYMBOLS` 要拦的第二真源形态）。
#: F8 尤其需要在内：它按名字引用 `backend/migrations/V*.sql`，是最容易越界的一个。
_SPEC_DELIVERABLES: Final[tuple[str, ...]] = (
    "backend/app/services/workpaper_sync/projection_lane_registry.py",
    "backend/app/services/workpaper_sync/projection_first_publication.py",
    "backend/scripts/fix/fix_projection_first_publication.py",
    "backend/scripts/check/check_projection_lane_adjudication.py",
    "backend/scripts/diagnose/mutate_projection_first_publication_guards.py",
    "backend/tests/workpaper_sync/test_projection_lane_registry.py",
    "backend/tests/workpaper_sync/test_projection_first_publication.py",
    "backend/tests/workpaper_sync/test_projection_first_publication_pg.py",
    "backend/tests/workpaper_sync/test_projection_lane_regression_gate.py",
)

#: 本 spec **不得**触碰的东西（Requirements 12.1~12.5）。
#: 判据形态是「交付物里对这些符号零引用」，而不是「仓库里不存在它们」。
_OUT_OF_SCOPE_SYMBOLS: Final[tuple[tuple[str, str], ...]] = (
    ("allow_external_relationships", "Task 74 的 OOXML 策略放宽 —— 不属本 spec"),
    ("multi_resolver", "multi_resolver 改动 —— 不属本 spec"),
    ("MultiResolver", "multi_resolver 改动 —— 不属本 spec"),
    ("migrate_writer", "Task 74 的 writer 迁移 —— 不属本 spec"),
    ("WriterMigrationPlan", "Task 74 的 writer 迁移 —— 不属本 spec"),
)


class GateError(RuntimeError):
    """门自身失效（取数、结构、环境）—— 与「判据不成立」严格区分。"""


# ═══════════════════════════════════════════════════════════════════════════
# R1：复用 Task 44 门的读数
# ═══════════════════════════════════════════════════════════════════════════


def _load_task44(explicit: Path | None) -> dict[str, Any]:
    """取 Task 44 门的报告。给了路径就读它，否则**现跑**一次。

    🔴 现跑而不是读一份陈旧落盘：本门的价值在于「现在还成立吗」，读旧报告会让
    R1 变成一个永远成立的量（假绿第③源）。
    """
    if explicit is not None:
        if not explicit.is_file():
            raise GateError(f"--task44-json 指向的文件不存在: {explicit}")
        return json.loads(explicit.read_text(encoding="utf-8"))

    out = _REPO / "backend/data/_tmp_task44_for_lane_gate.json"
    try:
        subprocess.run(
            [
                sys.executable,
                str(_BACKEND / "scripts/check/check_task44_oo94_excel_pilot_gate.py"),
                "--json",
                str(out),
            ],
            cwd=str(_REPO),
            capture_output=True,
            check=False,
        )
        if not out.is_file():
            raise GateError("Task 44 门没有产出 --json 报告 —— 无法复用其读数")
        return json.loads(out.read_text(encoding="utf-8"))
    finally:
        out.unlink(missing_ok=True)


async def _supply_gate_verdicts() -> dict[str, str | None]:
    """逐 entry 现跑 `registry._describe_entry_supply` —— 阶段一的判据本体。

    返回 `{entry_id: None | 拒绝原因}`。`None` 即放行。
    """
    import inspect

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.services.workpaper_sync.adapters import registry as reg

    describe = getattr(reg, "_describe_entry_supply", None)
    if describe is None:
        raise GateError(
            "`registry._describe_entry_supply` 不存在 —— 阶段一的判据没有落点，"
            "供给门可能已被重命名"
        )

    engine = create_async_engine(
        str(settings.DATABASE_URL),
        poolclass=NullPool,
        connect_args={"ssl": False} if settings.DB_DISABLE_SSL else {},
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    verdicts: dict[str, str | None] = {}
    try:
        async with Session() as session:
            for row in reg.DELIVERED_PER_ENTRY_CONTRACTS:
                entry_id = str(row["entry_id"])
                result = describe(session=session, entry_id=entry_id)
                if inspect.isawaitable(result):
                    result = await result
                verdicts[entry_id] = None if result is None else str(result)
    finally:
        await engine.dispose()
    return verdicts


def _r1(task44: dict[str, Any], verdicts: dict[str, str | None]) -> dict[str, Any]:
    """阶段一：供给门放行。`adapter_registered` 如实报告但不作通过条件。"""
    pilots = task44.get("pilots") or {}
    if not pilots:
        raise GateError("Task 44 报告里没有 pilots —— 读数复用失败")

    rows: list[dict[str, Any]] = []
    for entry_id in sorted(set(pilots) | set(verdicts)):
        signals = (pilots.get(entry_id) or {}).get("finalize_signals") or {}
        verdict = verdicts.get(entry_id, "<未观测>")
        rows.append(
            {
                "entry_id": entry_id,
                "supply_gate_admits": verdict is None,
                "supply_gate_reason": verdict,
                # 如实报告，**不**作为通过条件（Requirement 12.6）
                "adapter_registered_reported_only": signals.get("adapter_registered"),
                "capability_enabled_reported_only": signals.get("capability_enabled"),
            }
        )

    admitted = [r for r in rows if r["supply_gate_admits"]]
    return {
        "requirement": "12.6 阶段一：供给门放行（判据落在供给门返回值，不落在 adapter_registered）",
        "entries_observed": len(rows),
        "entries_admitted_by_supply_gate": len(admitted),
        "admitted_entry_ids": [r["entry_id"] for r in admitted],
        "passed": bool(admitted),
        "rows": rows,
        "stage_two_owner": (
            "capability 翻转 = manifest 重生成 + `approved_source_digest` 人工复核"
            "（Task 67 登记的复核方）—— 不属本 spec，Requirement 7.8 禁止绕过该复核门"
        ),
        "task44_result_distribution": task44.get("result_distribution"),
    }


# ═══════════════════════════════════════════════════════════════════════════
# R2：PG 只读现查
# ═══════════════════════════════════════════════════════════════════════════


async def _r2() -> dict[str, Any]:
    """至少一条 representation 绑 `projection_contract` bundle 且 entry 是 manifest entry。"""
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.services.workpaper_sync.writer_migration import OPAQUE_ENTRY_PREFIX

    engine = create_async_engine(
        str(settings.DATABASE_URL),
        poolclass=NullPool,
        connect_args={"ssl": False} if settings.DB_DISABLE_SSL else {},
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            rows = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT r.entry_id, r.generation, r.adapter_id, "
                            "       a.authority_model_type, "
                            "       LEFT(b.canonical_payload_sha256, 12) AS bundle_sha12 "
                            "FROM working_paper_content_representation r "
                            "JOIN working_paper_sync_definition_bundle b "
                            "  ON b.id = r.definition_bundle_id "
                            "JOIN working_paper_sync_definition_artifact a "
                            "  ON a.id = b.authority_model_definition_id "
                            "ORDER BY r.entry_id"
                        )
                    )
                )
                .mappings()
                .all()
            )
            candidate_rows = int(
                (
                    await session.execute(
                        sa.text(
                            "SELECT COUNT(*) FROM "
                            "working_paper_representation_upgrade_candidate"
                        )
                    )
                ).scalar_one()
            )
    finally:
        await engine.dispose()

    projection = [
        dict(r) for r in rows if str(r["authority_model_type"]) == "projection_contract"
    ]
    manifest_backed = [
        r for r in projection if not str(r["entry_id"]).startswith(OPAQUE_ENTRY_PREFIX)
    ]
    return {
        "requirement": "8.1 / 8.4：至少一条 projection_contract representation 且 entry 非 opaque 命名空间",
        "representation_rows_total": len(rows),
        "projection_contract_rows": len(projection),
        "manifest_backed_projection_rows": len(manifest_backed),
        "manifest_backed_entry_ids": [str(r["entry_id"]) for r in manifest_backed],
        "passed": bool(manifest_backed),
        # 🔴 candidate 表**可能有行**，那是首版落成**之后**的结果，
        #    不作为本门的前置条件（Requirement 8.5）
        "upgrade_candidate_rows_informational_only": candidate_rows,
        "candidate_note": (
            "candidate 表行数只作信息报告 —— 它是首版落成**之后**才可能出现的结果，"
            "不是首版的前置条件"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# R3：结构判据（candidate 产不出首版 + 范围边界结构缺席）
# ═══════════════════════════════════════════════════════════════════════════


async def _candidate_cannot_produce_first_generation() -> dict[str, Any]:
    """`source_representation_id` 为 NOT NULL ⇒ candidate 路径**结构上**产不出首版。

    这是 design.md C1 的可执行判据：candidate 必须指向一个**已存在**的 representation
    作为来源，因此它天然不能是「第一份」。判据现查 `information_schema`，不写死。
    """
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    engine = create_async_engine(
        str(settings.DATABASE_URL),
        poolclass=NullPool,
        connect_args={"ssl": False} if settings.DB_DISABLE_SSL else {},
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            nullable = (
                await session.execute(
                    sa.text(
                        "SELECT is_nullable FROM information_schema.columns "
                        "WHERE table_schema = 'public' "
                        "  AND table_name = "
                        "      'working_paper_representation_upgrade_candidate' "
                        "  AND column_name = 'source_representation_id'"
                    )
                )
            ).scalar_one_or_none()
            has_fk = int(
                (
                    await session.execute(
                        sa.text(
                            "SELECT COUNT(*) FROM information_schema.table_constraints "
                            "WHERE table_schema = 'public' "
                            "  AND constraint_type = 'FOREIGN KEY' "
                            "  AND constraint_name = "
                            "      'working_paper_representation_upgr_source_representation_id_fkey'"
                        )
                    )
                ).scalar_one()
            )
    finally:
        await engine.dispose()

    if nullable is None:
        raise GateError(
            "查不到 `working_paper_representation_upgrade_candidate."
            "source_representation_id` —— 表结构已变，本判据需重新裁决"
        )
    return {
        "requirement": "design.md C1：candidate 路径结构上产不出首版",
        "source_representation_id_is_nullable": str(nullable),
        "source_representation_id_has_fk": bool(has_fk),
        "passed": str(nullable) == "NO" and bool(has_fk),
        "why": (
            "`source_representation_id` NOT NULL + 外键 ⇒ candidate 必须指向一个**已存在**"
            "的 representation 作为来源 ⇒ 它天然不能是「第一份」。首版只能走"
            "`ContentMutationService.commit`"
        ),
    }


def _scope_boundary() -> dict[str, Any]:
    """范围边界的**结构缺席**判据（Requirements 12.1~12.5）。

    判据形态是「本 spec 交付物里对越界符号零引用」，且**剥 docstring 之后**再判 ——
    交付物的注释里正当地叙述了这些名字（解释为什么不碰它们）。
    """
    findings: list[dict[str, Any]] = []
    checked = 0
    for rel in _SPEC_DELIVERABLES:
        path = _REPO / rel
        if not path.is_file():
            continue
        checked += 1
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # 剥 docstring
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]

        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {
            n.slice.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Subscript)
            and isinstance(n.slice, ast.Constant)
            and isinstance(n.slice.value, str)
        }
        for symbol, reason in _OUT_OF_SCOPE_SYMBOLS:
            if symbol in names:
                findings.append({"file": rel, "symbol": symbol, "reason": reason})

    # 本 spec 不得新增迁移文件
    migrations = sorted(
        p.name
        for p in (_REPO / "backend/migrations").glob("V*.sql")
        if _is_untracked(p)
    ) if (_REPO / "backend/migrations").is_dir() else []

    return {
        "requirement": "12.1~12.5：范围边界的结构缺席",
        "deliverables_checked": checked,
        "out_of_scope_references": findings,
        "untracked_new_migrations": migrations,
        "passed": not findings and not migrations,
        "note": (
            "判据在**剥 docstring 之后**做 —— 交付物的注释里正当地叙述了这些名字"
            "（解释为什么不碰），不剥会把叙述当成真实引用"
        ),
    }


def _is_untracked(path: Path) -> bool:
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path.relative_to(_REPO)).replace("\\", "/")],
        cwd=str(_REPO),
        capture_output=True,
    )
    return proc.returncode != 0


# ═══════════════════════════════════════════════════════════════════════════
# R4：capability 变更纪律
# ═══════════════════════════════════════════════════════════════════════════


def _capability_discipline() -> dict[str, Any]:
    """manifest 出现 `bidirectional` 时，复核门不得被绕过（Requirement 7.8）。"""
    from app.services.workpaper_sync.adapters.registry import manifest_entries_by_id
    from app.services.workpaper_sync.entry_profile import (
        Capability,
        capability_of,
        load_entry_manifest,
    )

    manifest = load_entry_manifest()
    entries = manifest_entries_by_id(manifest)
    bidirectional = sorted(
        entry_id
        for entry_id, entry in entries.items()
        if capability_of(entry) is getattr(Capability, "bidirectional", None)
    )
    stats = manifest.get("stats") if isinstance(manifest, dict) else {}
    counts = (stats or {}).get("capability_counts") or {}

    result: dict[str, Any] = {
        "requirement": "7.8 / 9.3：capability 翻转须经 approved_source_digest 人工复核",
        "manifest_capability_counts": counts,
        "bidirectional_entry_ids": bidirectional,
        "bidirectional_present": bool(bidirectional),
    }
    if not bidirectional:
        result["passed"] = True
        result["note"] = (
            "manifest 里没有 `bidirectional` entry ⇒ 本条无需检查（阶段二未发生）。"
            "这**不是**空转豁免：一旦出现，下面的复核判据立即生效"
        )
        return result

    # 出现了 bidirectional ⇒ 复核门必须未被绕过
    digest_gate = _approved_source_digest_state()
    result["approved_source_digest"] = digest_gate
    result["passed"] = (
        bool(digest_gate.get("gate_present"))
        and bool(digest_gate.get("overlay_is_reviewed"))
        and bool(digest_gate.get("approved_matches_current"))
    )
    result["note"] = (
        "出现 `bidirectional` ⇒ overlay 必须已 reviewed 且 `approved_source_digest` "
        "与现读源码一致（复核门未被绕过）"
    )
    return result


#: `approved_source_digest` 复核门的**真源**。
#:
#: 🔴 首版我猜成 `entry_profile.APPROVED_SOURCE_DIGEST` / `current_source_digest()`
#: 两个模块属性，实测**都不存在** —— 自我变异的第 ⑧ 条（注入一个 bidirectional entry）
#: 把它抓了出来：R4 会以「找不到复核门」fail closed，方向对但理由是假的。
#: 真源是 `generate_workpaper_sync_manifest.build_manifest()` 里那道门：
#:     overlay["approved_source_digest"] != discovery["sourceDigest"] ⇒ 拒绝
_OVERLAY_PATH: Final[str] = "backend/data/workpaper_sync_entry_overlay.json"


def _approved_source_digest_state() -> dict[str, Any]:
    """现读 `approved_source_digest` 复核门的状态（不改它，只报告）。

    两侧各自现读，**不**写死任何 digest 字面量：

    * approved 侧 = `workpaper_sync_entry_overlay.json` 的 `approved_source_digest`
    * current 侧  = mount discovery 的 `sourceDigest`
    """
    overlay_path = _REPO / _OVERLAY_PATH
    if not overlay_path.is_file():
        return {
            "gate_present": False,
            "note": f"overlay 文件不存在: {_OVERLAY_PATH}",
        }
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    approved = str(overlay.get("approved_source_digest") or "")
    review_status = str(overlay.get("review_status") or "")

    # current 侧走生成器的 `discover_source()` —— 与复核门自己用的是同一个函数，
    # 因此两侧比的是同一个量（不是我另算一份）。
    try:
        import importlib.util

        gen_path = _BACKEND / "scripts/gen/generate_workpaper_sync_manifest.py"
        spec = importlib.util.spec_from_file_location("_gen_manifest", gen_path)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules["_gen_manifest"] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        discovery = module.discover_source()  # type: ignore[attr-defined]
        current = str((discovery or {}).get("sourceDigest") or "")
    except Exception as exc:  # noqa: BLE001
        return {
            "gate_present": True,
            "approved": approved[:12],
            "overlay_review_status": review_status,
            "overlay_is_reviewed": review_status == "reviewed",
            "error": f"取 current sourceDigest 失败: {type(exc).__name__}: {exc}",
            "approved_matches_current": False,
        }

    return {
        "gate_present": True,
        "overlay_path": _OVERLAY_PATH,
        "overlay_review_status": review_status,
        "overlay_is_reviewed": review_status == "reviewed",
        "approved": approved[:12],
        "current": current[:12],
        "approved_matches_current": bool(approved) and approved == current,
        "gate_source": (
            "generate_workpaper_sync_manifest.build_manifest() 的复核门："
            "overlay['approved_source_digest'] != discovery['sourceDigest'] ⇒ 拒绝"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════════════════════════════════


#: `--offline` 下**跳过**的判据，以及各自为什么必须跳过。
#:
#: 🔴 这不是「太麻烦所以不跑」的豁免清单，而是**环境事实**：这三项判据度量的是
#: 「本仓库的 dev 库里首版已经落成」，而 CI 上是一个崭新的空库。
#: 2026-09-05 实测（空临时 schema + 跑完 V151/V152/V153 三个迁移）：
#:   `working_paper_content_representation` 0 行 · `..._definition_bundle` 0 行
#: ⇒ R2 的「≥1 条 projection_contract representation」必不成立；
#: ⇒ R1 的供给判据 B（current published representation 存在）为假 ⇒ 四个 entry 全被拒。
#: 把它们挂进 CI 只会得到一个恒红的 job，而恒红的门与没有门等价（很快会被 skip 掉）。
_OFFLINE_SKIPPED: Final[Mapping[str, str]] = {
    "R1_supply_gate_admits_stage_one": (
        "需要 dev 库里已落成的首版（供给判据 B）—— CI 的崭新库上四个 entry 全被拒"
    ),
    "R2_projection_representation_exists": (
        "需要 ≥1 条 projection_contract representation —— CI 的崭新库上该表 0 行"
    ),
    "R3a_candidate_cannot_produce_first_generation": (
        "查 information_schema 的列属性，需要跑过迁移的库；"
        "它在崭新库上**本可成立**，但与 R1/R2 共用一次连库，"
        "单独为它起 service 换不来判据强度（结构事实已由 F7 的 AST 判据覆盖）"
    ),
}


def build_report(
    task44_json: Path | None, *, offline: bool = False
) -> dict[str, Any]:
    """五项判据的汇总报告。

    :param offline: 只跑不连库的 R3b / R4。报告里会逐项写明**哪些没验证**，
        并把 `gate_version` 打上 `+offline` 后缀 —— 让 offline 报告在任何场合
        都不可能被误读成完整验收。
    """
    checks: dict[str, Any] = {}
    task44: dict[str, Any] = {}

    if offline:
        for name, reason in _OFFLINE_SKIPPED.items():
            checks[name] = {
                "skipped_offline": True,
                # 🔴 `passed` 缺席而不是 `True`：`failing` 用 `.get("passed")` 判，
                #    写 True 会让跳过的项在计数上等同于通过。缺席 + 下面的
                #    `checks_skipped` 让「未验证」在报告里是可见的第三态。
                "reason": reason,
            }
    else:
        task44 = _load_task44(task44_json)
        checks["R1_supply_gate_admits_stage_one"] = _r1(
            task44, asyncio.run(_supply_gate_verdicts())
        )
        checks["R2_projection_representation_exists"] = asyncio.run(_r2())
        checks["R3a_candidate_cannot_produce_first_generation"] = asyncio.run(
            _candidate_cannot_produce_first_generation()
        )

    checks["R3b_scope_boundary_structural_absence"] = _scope_boundary()
    checks["R4_capability_change_discipline"] = _capability_discipline()

    skipped = sorted(k for k, v in checks.items() if v.get("skipped_offline"))
    failing = sorted(
        k
        for k, v in checks.items()
        if not v.get("skipped_offline") and not v.get("passed")
    )
    verified = sorted(set(checks) - set(skipped))
    if not verified:
        raise GateError(
            "一项判据都没验证 —— 门退化成恒真。检查 `--offline` 的跳过清单是否过宽"
        )

    return {
        "gate_version": GATE_VERSION + ("+offline" if offline else ""),
        "spec": "published-representation-production-path-and-lane-adjudication",
        "task": "9.1",
        "offline": offline,
        "task44_gate_version": task44.get("gate_version"),
        "checks": checks,
        "checks_verified": verified,
        "checks_skipped": skipped,
        "checks_failing": failing,
        "passed": not failing,
    }


def _render(report: dict[str, Any]) -> str:
    lines = [f"projection lane 裁决回归门（{report['gate_version']}）"]
    lines.append(f"  复用 Task 44 读数: {report.get('task44_gate_version')}")
    lines.append("")

    # 🔴 offline 下把「未验证」显式列出来。缺了这一段，offline 报告看起来会像
    #    「两项判据全过」而读者无从知道另外三项根本没跑。
    if report.get("checks_skipped"):
        lines.append("  ⚠ 未验证（--offline，需要 dev 库里已落成的首版）:")
        for name in report["checks_skipped"]:
            reason = report["checks"][name].get("reason", "")
            lines.append(f"      · {name}")
            lines.append(f"          {reason}")
        lines.append("")

    r1 = report["checks"]["R1_supply_gate_admits_stage_one"]
    if not r1.get("skipped_offline"):
        lines.append("  R1 阶段一 —— 供给门放行（判据不落在 adapter_registered）")
        for row in r1["rows"]:
            mark = "PASS" if row["supply_gate_admits"] else "----"
            lines.append(f"    {mark} {row['entry_id']}")
            if not row["supply_gate_admits"] and row["supply_gate_reason"]:
                lines.append(f"          {str(row['supply_gate_reason'])[:110]}")
            lines.append(
                f"          （仅报告）adapter_registered="
                f"{row['adapter_registered_reported_only']} "
                f"capability_enabled={row['capability_enabled_reported_only']}"
            )
        lines.append(
            f"    放行 {r1['entries_admitted_by_supply_gate']}/{r1['entries_observed']}"
            f"  Task 44 四态={r1['task44_result_distribution']}"
        )
        lines.append("")

    r2 = report["checks"]["R2_projection_representation_exists"]
    if not r2.get("skipped_offline"):
        lines.append("  R2 projection_contract representation（PG 只读现查）")
        lines.append(
            f"    representation 共 {r2['representation_rows_total']} 行 · "
            f"projection_contract {r2['projection_contract_rows']} 行 · "
            f"其中 manifest entry {r2['manifest_backed_projection_rows']} 行"
        )
        for entry_id in r2["manifest_backed_entry_ids"]:
            lines.append(f"      + {entry_id}")
        lines.append(
            f"    （仅信息）upgrade candidate "
            f"{r2['upgrade_candidate_rows_informational_only']} 行"
        )
        lines.append("")

    c = report["checks"]["R3a_candidate_cannot_produce_first_generation"]
    if not c.get("skipped_offline"):
        lines.append(
            f"  R3a candidate 产不出首版: source_representation_id "
            f"is_nullable={c['source_representation_id_is_nullable']} "
            f"fk={c['source_representation_id_has_fk']}"
        )
    s = report["checks"]["R3b_scope_boundary_structural_absence"]
    lines.append(
        f"  R3b 范围边界: 交付物 {s['deliverables_checked']} 个 · "
        f"越界引用 {len(s['out_of_scope_references'])} 处 · "
        f"新增迁移 {len(s['untracked_new_migrations'])} 个"
    )
    for item in s["out_of_scope_references"]:
        lines.append(f"      ! {item['file']} 引用 {item['symbol']} —— {item['reason']}")

    r4 = report["checks"]["R4_capability_change_discipline"]
    lines.append(
        f"  R4 capability 纪律: bidirectional {len(r4['bidirectional_entry_ids'])} 个 · "
        f"counts={r4['manifest_capability_counts']}"
    )
    lines.append("")

    verified = report.get("checks_verified") or []
    if report["passed"]:
        # 🔴 报「已验证 N 项」而不是恒定的「五项」—— offline 下只跑了两项，
        #    印「五项判据全部成立」就是在报告里说谎。
        lines.append(f"[OK] 已验证的 {len(verified)} 项判据全部成立: {verified}")
        if report.get("checks_skipped"):
            lines.append(
                f"     ⚠ 另有 {len(report['checks_skipped'])} 项未验证"
                f"（见上）—— 本次**不是**完整验收"
            )
    else:
        lines.append(f"[BLOCKED] 未通过: {report['checks_failing']}")
    return "\n".join(lines)


def _diff_baseline(report: dict[str, Any], baseline: Path) -> dict[str, Any]:
    """与旧基线比差集 —— `failed` 计数不得因本 spec 交付而增加。"""
    old = json.loads(baseline.read_text(encoding="utf-8"))
    old_dist = (
        (old.get("checks") or {})
        .get("R1_supply_gate_admits_stage_one", {})
        .get("task44_result_distribution")
    ) or {}
    new_dist = (
        report["checks"]["R1_supply_gate_admits_stage_one"]["task44_result_distribution"]
    ) or {}
    old_failed = int(old_dist.get("failed", 0))
    new_failed = int(new_dist.get("failed", 0))
    return {
        "baseline_path": str(baseline),
        "old_failed": old_failed,
        "new_failed": new_failed,
        "failed_did_not_increase": new_failed <= old_failed,
        "old_checks_failing": old.get("checks_failing"),
        "new_checks_failing": report["checks_failing"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_path", help="报告落盘路径")
    parser.add_argument(
        "--task44-json",
        help="已有的 Task 44 报告（不给则现跑一次 —— 读旧报告会让 R1 变成恒真量）",
    )
    parser.add_argument("--baseline", help="与该基线比差集（failed 不得增加）")
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "只跑不连库的 R3b / R4（CI 用）。R1/R2/R3a 需要 dev 库里已落成的首版，"
            "在崭新库上必不成立 —— 报告会逐项写明未验证的部分"
        ),
    )
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, OSError, ValueError):
            pass

    if args.offline and args.baseline:
        print(
            "[FATAL] `--offline` 与 `--baseline` 不可同用：基线差集取自 R1 的 "
            "Task 44 四态分布，而 offline 下 R1 没跑 —— 硬算会拿 0 去比旧基线，"
            "得出「failed 从 28 降到 0」这种假好消息"
        )
        return 2

    try:
        report = build_report(
            Path(args.task44_json) if args.task44_json else None,
            offline=args.offline,
        )
    except GateError as exc:
        print(f"[FATAL] 门自身失效：{exc}")
        return 2
    except Exception as exc:  # noqa: BLE001 - 任何未预期错误都 fail closed
        import traceback

        print(f"[FATAL] {type(exc).__name__}: {exc}")
        print(traceback.format_exc()[-1200:])
        return 2

    if args.baseline:
        baseline = Path(args.baseline)
        if baseline.is_file():
            report["baseline_diff"] = _diff_baseline(report, baseline)

    print(_render(report))
    if "baseline_diff" in report:
        diff = report["baseline_diff"]
        print(
            f"  基线差集: failed {diff['old_failed']} → {diff['new_failed']} "
            f"（未增加: {diff['failed_did_not_increase']}）"
        )

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"  报告已落盘：{args.json_path}")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
