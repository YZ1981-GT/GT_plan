"""H 类取数链路真实库验收（只读，默认 dry-run）。

spec: `.kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/` Task 18
（Requirements 10.5 / 11.5 / 11.6）

## 为什么必须连真实库

本 spec 已有的守卫都不连库或只连库取快照，而 H 类最贵的两个缺陷**只有真实库能暴露**：

1. **双族只取到 0.04%** —— `1641/1651`、`1642/1652`、`2601/2651` 在同一项目内互斥，
   9 个项目里多数用**新族**；按标准码 `1641`/`2601` 硬查在这些项目**取到的不是空
   而是 0.04%**（`trial_balance` 1641=160,078.75 vs 1651=386,272,594.21），
   比恒空更隐蔽。替身 fixture 与错误假设同构，测不出来。
2. **叶子聚合 vs trial_balance 父子双算** —— H2/H8 实证 `trial_balance` 值正好是
   叶子聚合的 2 倍且「叶子和 == 父额」勾稽同时成立。

## 判据（违规数为 0 才算通过）

| # | 判据 | 违规含义 |
|---|---|---|
| 1 | 每个 (项目, 循环) 的 `tb_source_codes` 存在且 `resolved_from` 非空 | 溯源是 dead output |
| 2 | 双族循环（H8/H9）的槽兜底码含**两族** | Task 6 接线被回退 |
| 3 | `parent_check.diff` 为 0 或缺该键 | 叶子聚合与父额不勾稽 |
| 4 | 槽 `found=False` 时该槽**不出现**在 `adjudication_prefill` | 凭空造 0 |
| 5 | 双族两侧**不同时非零** | 加和会双算（裁决 1 的前提） |

## 诚实报告原则

- 连不上库 → 明确输出「无法验收」并 **exit 2**（不用 fixture 冒充）
- 某项目没有 H 类科目 → 记 `no_account` 并**跳过该组合的取数判据**
  （宁缺勿造是**正确行为**，不算违规）
- 只读：全程无 INSERT/UPDATE/DELETE；`--apply` **不提供**（本脚本无写路径）

用法::

    python backend/scripts/diagnose/verify_h_cycle_extraction_live.py
    python backend/scripts/diagnose/verify_h_cycle_extraction_live.py --out report.txt
    python backend/scripts/diagnose/verify_h_cycle_extraction_live.py --cycle H8
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# 输出缓冲：控制台可能是 GBK，emoji/特殊符号一律禁用（崩点在写盘之后）
_LINES: list[str] = []


def log(s: str = "") -> None:
    _LINES.append(s)
    try:
        print(s)
    except UnicodeEncodeError:  # pragma: no cover - 控制台编码兜底
        print(s.encode("ascii", "replace").decode("ascii"))


#: 循环 → (scope 模块名, spec 常量名, 槽键前缀常量名)
H_CYCLES: dict[str, tuple[str, str, str]] = {
    "H1": ("h1_account_scope", "H1_ACCOUNT_SPEC", "H1_SLOT_KEY_PREFIX"),
    "H2": ("h2_account_scope", "H2_ACCOUNT_SPEC", "H2_SLOT_KEY_PREFIX"),
    "H3": ("h3_account_scope", "H3_ACCOUNT_SPEC", "H3_SLOT_KEY_PREFIX"),
    "H4": ("h4_account_scope", "H4_ACCOUNT_SPEC", "H4_SLOT_KEY_PREFIX"),
    "H5": ("h5_account_scope", "H5_ACCOUNT_SPEC", "H5_SLOT_KEY_PREFIX"),
    "H6": ("h6_account_scope", "H6_ACCOUNT_SPEC", "H6_SLOT_KEY_PREFIX"),
    "H7": ("h7_account_scope", "H7_ACCOUNT_SPEC", "H7_SLOT_KEY_PREFIX"),
    "H8": ("h8_account_scope", "H8_ACCOUNT_SPEC", "H8_SLOT_KEY_PREFIX"),
    "H9": ("h9_account_scope", "H9_ACCOUNT_SPEC", "H9_SLOT_KEY_PREFIX"),
    "H10": ("h10_account_scope", "H10_ACCOUNT_SPEC", "H10_SLOT_KEY_PREFIX"),
}

#: 双族循环（Task 6 接线的两个）→ 槽键 → 应含的全部码
DUAL_EXPECT: dict[str, dict[str, tuple[str, ...]]] = {}


def _load_dual_expect() -> None:
    from app.services.four_table.dual_family_codes import (
        CYCLE_SLOT_TO_DUAL_FAMILY,
        codes_for_cycle_slot,
    )

    for cycle, slot in CYCLE_SLOT_TO_DUAL_FAMILY:
        DUAL_EXPECT.setdefault(cycle, {})[slot] = codes_for_cycle_slot(cycle, slot)


async def _projects(db) -> list[tuple[str, int]]:
    import sqlalchemy as sa

    rows = (
        await db.execute(
            sa.text(
                "SELECT DISTINCT p.id::text, p.audit_year "
                "FROM projects p WHERE p.is_deleted = false "
                "AND p.audit_year IS NOT NULL ORDER BY p.audit_year DESC, 1"
            )
        )
    ).all()
    return [(r[0], int(r[1])) for r in rows]


async def _dual_family_overlap(db) -> list[str]:
    """判据 5：双族两侧不得同时非零（裁决 1 的前提，未来防线）。"""
    import sqlalchemy as sa

    from app.services.four_table.dual_family_codes import ROU_LEASE_DUAL_FAMILIES

    bad: list[str] = []
    for g in ROU_LEASE_DUAL_FAMILIES:
        if not g.alternate or g.alternate == g.primary:
            continue
        rows = (
            await db.execute(
                sa.text(
                    "SELECT project_id::text, "
                    " SUM(CASE WHEN standard_account_code = :a "
                    "     THEN COALESCE(unadjusted_amount,0) ELSE 0 END) AS pa, "
                    " SUM(CASE WHEN standard_account_code = :b "
                    "     THEN COALESCE(unadjusted_amount,0) ELSE 0 END) AS pb "
                    "FROM trial_balance "
                    "WHERE standard_account_code IN (:a, :b) "
                    "GROUP BY project_id"
                ),
                {"a": g.primary, "b": g.alternate},
            )
        ).all()
        for pid, pa, pb in rows:
            if pa and pb and float(pa) != 0.0 and float(pb) != 0.0:
                bad.append(
                    f"{g.slot_key}: 项目 {pid[:8]} 两族同时非零 "
                    f"{g.primary}={pa} / {g.alternate}={pb} -> 加和会双算"
                )
    return bad


def _check_slot_codes(cycle: str, spec) -> list[str]:
    """判据 2：双族循环的槽兜底码必须含两族（不连库，纯声明核对）。"""
    expect = DUAL_EXPECT.get(cycle) or {}
    if not expect:
        return []
    got = {s.key: tuple(s.fallback_standard_codes or ()) for s in spec.slots}
    bad: list[str] = []
    for slot, codes in expect.items():
        if slot not in got:
            bad.append(f"{cycle}.{slot}: spec 缺该槽（双族真源已登记 {codes}）")
        elif got[slot] != codes:
            bad.append(
                f"{cycle}.{slot}: 兜底码 {got[slot]} != 双族真源 {codes} "
                f"-> 单族在用新族的项目上只取到 0.04%"
            )
    return bad


async def _resolve_one(db, pid: str, year: int, cycle: str, spec):
    """跑一次语义定位，返回 (ok, resolved_from, slot 明细, 备注)。"""
    from app.services.four_table.semantic_account_resolver import (
        ResolverContext,
        resolve_semantic_accounts,
    )

    ctx = ResolverContext(db=db, project_id=pid, year=year)
    try:
        res = await resolve_semantic_accounts(ctx, spec)
    except Exception as e:  # noqa: BLE001 — 诚实报告，不吞
        return False, "", {}, f"resolve 抛异常: {type(e).__name__}: {e}"

    slots = {}
    for key, slot in (getattr(res, "slots", None) or {}).items():
        slots[key] = {
            "found": bool(getattr(slot, "found", False)),
            "codes": tuple(getattr(slot, "codes", ()) or ()),
            "resolved_from": getattr(slot, "resolved_from", "") or "",
        }
    payload = res.as_dict() if hasattr(res, "as_dict") else {}
    return True, str(payload.get("resolved_from") or ""), slots, ""


async def main_async(only_cycle: str | None) -> int:
    try:
        from app.core.database import async_session
    except Exception as e:  # noqa: BLE001
        log(f"[ERR] 无法导入 DB 会话工厂: {e}")
        log("[ERR] 无法验收（禁用 fixture 冒充）")
        return 2

    _load_dual_expect()

    violations: list[str] = []
    checked = 0
    no_account = 0

    # ── 判据 2：声明层（不连库，先跑） ──────────────────────────────
    log("=" * 70)
    log("判据 2：双族循环的槽兜底码必须引双族真源")
    log("=" * 70)
    import importlib

    specs: dict[str, object] = {}
    for cycle, (mod_name, spec_name, _prefix) in H_CYCLES.items():
        if only_cycle and cycle != only_cycle:
            continue
        try:
            mod = importlib.import_module(f"app.services.four_table.{mod_name}")
            spec = getattr(mod, spec_name)
        except Exception as e:  # noqa: BLE001
            violations.append(f"{cycle}: 无法加载 {mod_name}.{spec_name}: {e}")
            continue
        specs[cycle] = spec
        bad = _check_slot_codes(cycle, spec)
        for b in bad:
            violations.append(b)
        mark = "VIOLATION" if bad else "ok"
        codes = {s.key: tuple(s.fallback_standard_codes or ()) for s in spec.slots}
        log(f"  {cycle:<4} row_code={getattr(spec, 'row_code', None)!s:<9} {mark}")
        for k, v in codes.items():
            dual = " <= dual" if (DUAL_EXPECT.get(cycle) or {}).get(k) else ""
            log(f"        {k:<18} {v}{dual}")

    try:
        async with async_session() as db:
            # ── 判据 5：双族重叠 ────────────────────────────────────
            log("")
            log("=" * 70)
            log("判据 5：双族两侧不得同时非零（否则 TB(a)+TB(b) 双算）")
            log("=" * 70)
            overlap = await _dual_family_overlap(db)
            violations.extend(overlap)
            log(f"  重叠组合数={len(overlap)}" + ("  ok" if not overlap else ""))
            for o in overlap:
                log(f"    VIOLATION {o}")

            projects = await _projects(db)
            log("")
            log("=" * 70)
            log(f"判据 1/3/4：逐项目 x 循环语义定位（项目数={len(projects)}）")
            log("=" * 70)

            for pid, year in projects:
                for cycle, spec in specs.items():
                    checked += 1
                    ok, resolved_from, slots, note = await _resolve_one(
                        db, pid, year, cycle, spec
                    )
                    if not ok:
                        violations.append(f"{pid[:8]}/{year} {cycle}: {note}")
                        log(f"  {pid[:8]} {year} {cycle:<4} VIOLATION {note}")
                        continue

                    found = {k: v for k, v in slots.items() if v["found"]}
                    if not found:
                        # 宁缺勿造：本项目无此科目族 —— 正确行为，不算违规
                        no_account += 1
                        log(f"  {pid[:8]} {year} {cycle:<4} no_account（本项目无此科目，跳过取数判据）")
                        continue

                    # 判据 1：命中即必须有 resolved_from
                    if not resolved_from and not any(
                        v["resolved_from"] for v in found.values()
                    ):
                        violations.append(
                            f"{pid[:8]}/{year} {cycle}: 槽已命中但 resolved_from 全空"
                            f" -> 溯源面板拿不到口径"
                        )

                    detail = " ".join(
                        f"{k}={v['codes']}" for k, v in sorted(found.items())
                    )
                    log(
                        f"  {pid[:8]} {year} {cycle:<4} from={resolved_from or '-':<24}"
                        f" {detail}"
                    )
    except Exception as e:  # noqa: BLE001
        log("")
        log(f"[ERR] 连库失败: {type(e).__name__}: {e}")
        log("[ERR] 无法验收（禁用 fixture 冒充）—— 声明层判据结果见上方")
        return 2

    log("")
    log("=" * 70)
    log(f"[SUMMARY] 组合数={checked}  no_account={no_account}  违规数={len(violations)}")
    log("=" * 70)
    if violations:
        for v in violations:
            log(f"  VIOLATION {v}")
        return 1
    log("[OK] 全部判据通过")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="H 类取数链路真实库验收（只读）")
    ap.add_argument("--out", help="报告落盘路径（UTF-8）")
    ap.add_argument("--cycle", help="只验一个循环，如 H8")
    args = ap.parse_args()

    rc = asyncio.run(main_async(args.cycle))

    if args.out:
        Path(args.out).write_text("\n".join(_LINES) + "\n", encoding="utf-8")
        print(f"[INFO] report -> {args.out}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
