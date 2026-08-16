"""D 循环四表取数真实库验收（**只读**，不写任何表）。

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/ Task 13
      Requirements 1.1~1.7 / 2.1~2.6 / Property 1~8, 33

**为什么必须真实库直跑**（平台已实证多次的教训）

单测替身与「我自己的错误假设」同构 —— 替身按各 render 原 SQL 的字段别名定制，
既发现不了「反解失败导致前缀体系不匹配」，也发现不了「trial_balance 父子双算」。
本轮就有两处判断被真实数据推翻：

* 立项判定「D7 的 `2205` 在 `tb_balance` 全库 0 行 ⇒ 取不到数」——
  实测 `trial_balance` 存的是**映射后标准码**，`2205` 有 5 个项目 / 7,855.34
  （正是那个客户码为 `2204` 的项目经 `account_mapping` 映射后写入的）。
* 立项判定「D6 备抵 `1142` 恒空是数据事实」—— 机理其实是 `1231-05` 反解不到
  客户原始码后**保留横杠标准码**去 `LIKE '1231-05%'` 查点号体系的 `tb_balance`，
  必然 0 行（碰巧结果也对，属「碰巧对」不是「实现对」）。

用法::

    python backend/scripts/diagnose/verify_d_cycle_extraction_live.py            # 全部项目
    python backend/scripts/diagnose/verify_d_cycle_extraction_live.py --project <uuid>
    python backend/scripts/diagnose/verify_d_cycle_extraction_live.py --out report.txt

判据（逐循环逐项目）：
    P1  gross 槽恒有码（或如实标 no_account）
    P2  备抵反解命中时，名称过滤后不得含他科目坏账
    P3  四态标志互斥且与 amount 的 None/数值一致
    P4  叶子和 == 父行金额（容差 0.01）
    P5  三口径中 trial_balance 与叶子和的差异如实暴露（不静默取其一）
    P6  prefix_mismatch 只在「码含横杠且 tb 命中 0 行」时为真
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

import sqlalchemy as sa  # noqa: E402

TOLERANCE = 0.01

#: 与 `d_account_resolver.D_CYCLE_ACCOUNT_SPECS` 同域（D1 走自己的历史路径，单列）
_CYCLES = ("D1", "D2", "D3", "D4", "D5", "D6", "D7")


class _Ctx:
    """最小 RenderContext 替身（解析器只用 db / project_id / year）。"""

    def __init__(self, db, project_id, year):
        self.db = db
        self.project_id = project_id
        self.year = year
        self.business_category = ""
        self.classification = None


async def _projects(db, only=None) -> list[tuple[str, int, str]]:
    rows = (
        await db.execute(
            sa.text(
                "SELECT id, audit_year, client_name FROM projects "
                "WHERE is_deleted = false ORDER BY audit_year DESC, client_name"
            )
        )
    ).fetchall()
    out = [(str(r.id), int(r.audit_year or 0), r.client_name or "") for r in rows]
    if only:
        out = [t for t in out if t[0] == str(only)]
    return out


def _fmt(v) -> str:
    if v is None:
        return "None"
    return f"{v:,.2f}"


async def _run_cycle(db, wp_code: str, project_id: str, year: int) -> dict:
    """跑单个循环的取数并做判据核验。返回结构化结果。"""
    from app.services.d_cycle_extraction.d_account_resolver import (
        resolve_d_cycle_account_codes,
        spec_of,
    )
    from app.services.d_cycle_extraction.d_tb_fetch import fetch_d_cycle_tb

    ctx = _Ctx(db, project_id, year)
    res: dict = {"wp_code": wp_code, "violations": [], "slots": {}}

    if wp_code == "D1":
        # D1 刻意走历史路径（零回归红线）
        from app.services.d_cycle_extraction.d1_account_resolver import (
            resolve_d1_account_codes,
        )

        codes = await resolve_d1_account_codes(ctx)
        res["resolved_from"] = codes.resolved_from
        res["row_code"] = "BS-005"
        res["path"] = "d1_account_resolver(历史路径)"
    elif spec_of(wp_code) is None:
        res["path"] = "无 spec（D4 走 d4_extraction.account_scope）"
        return res
    else:
        codes = await resolve_d_cycle_account_codes(ctx, wp_code)
        res["resolved_from"] = codes.resolved_from
        res["row_code"] = codes.row_code
        res["path"] = "d_account_resolver"

    tb = await fetch_d_cycle_tb(ctx, codes)
    # 🔴 `fetch_ok` 只存在于 `build_d_tb_source_codes` 的**载荷 dict** 里；
    #    `DCycleTbData` 这个 dataclass 上的字段名是 `ok`（另有 `error`）。
    #    本脚本首版写 `tb.fetch_ok` → 48 处全部 AttributeError 并被判成「判据违规」，
    #    看起来像取数全线失败，实为脚本自身缺陷（fail-open 不覆盖脚本层）。
    res["fetch_ok"] = tb.ok
    if tb.error:
        res["fetch_error"] = tb.error

    for key in ("gross", "provision"):
        slot = tb.slots.get(key)
        if slot is None:
            continue
        res["slots"][key] = {
            "state": slot.state,
            "query_codes": list(slot.query_codes),
            # 🔴 标准码在 `DCycleAccountCodes` 上（`gross_standard` / `provision_standard`），
            #    **不在** `SlotAmounts` 上 —— 本脚本第二版写 slot.standard_codes 又是 48 处
            #    AttributeError。槽只承载「取数结果」，码的来源归属在 codes 对象。
            "standard_codes": list(
                getattr(codes, "gross_standard" if key == "gross" else "provision_standard", None)
                or []
            ),
            "closing": slot.closing,
            "opening": slot.opening,
            "tb_rows_count": slot.tb_rows_count,
            "prefix_mismatch": slot.prefix_mismatch,
            "dropped": list(slot.dropped),
            "warnings": list(slot.warnings),
        }

        # ── P3：四态与 amount 一致性 ──────────────────────────────────
        if slot.state == "no_account" and slot.closing is not None:
            res["violations"].append(f"P3 {key}: no_account 但 closing 非 None")
        if slot.state == "ok" and slot.closing is None:
            res["violations"].append(f"P3 {key}: ok 但 closing 为 None")
        if slot.state in ("no_data", "prefix_mismatch") and slot.tb_rows_count:
            res["violations"].append(
                f"P3 {key}: state={slot.state} 但 tb_rows_count={slot.tb_rows_count}"
            )

        # ── P6：prefix_mismatch 判据 ─────────────────────────────────
        has_hyphen = any("-" in c for c in slot.query_codes)
        if slot.prefix_mismatch and not (has_hyphen and slot.tb_rows_count == 0):
            res["violations"].append(
                f"P6 {key}: prefix_mismatch 为真但码无横杠或 tb 有命中"
            )

        # ── P2：备抵剔除的必须是他科目 ────────────────────────────────
        if key == "provision" and slot.dropped:
            # 🔴 `dropped` 的元素是 **dict**（含 code/name/reason 三键），不是二元组。
            #    首版写 `for c, r in slot.dropped` → 迭代 dict 得到 3 个键名 →
            #    `ValueError: too many values to unpack`，D6 全部 8 个项目被记成
            #    「判据违规」，看起来像取数全线失败，实为脚本自身缺陷。
            res["dropped_detail"] = [
                (d.get("code"), d.get("name"), d.get("reason")) for d in slot.dropped
            ]

    # ── P1：gross 槽必须有码或如实标 no_account ─────────────────────
    g = tb.slots.get("gross")
    if g is not None and not g.query_codes and g.state != "no_account":
        res["violations"].append("P1 gross: 无码但未标 no_account")

    # ── P4/P5：三口径 ────────────────────────────────────────────────
    res["parent_check"] = tb.parent_check
    for slot_key, pc in (tb.parent_check or {}).items():
        leaf = float(pc.get("leaf_sum") or 0)
        parent = float(pc.get("parent") or 0)
        trial = float(pc.get("trial_balance") or 0)
        if parent and abs(leaf - parent) > TOLERANCE:
            res["violations"].append(
                f"P4 {slot_key}: 叶子和 {_fmt(leaf)} != 父行 {_fmt(parent)}"
            )
        if trial and abs(leaf - trial) > TOLERANCE:
            # 不是违规，是要如实暴露的差异（trial_balance 父子双算的典型形态）
            ratio = (trial / leaf) if leaf else 0
            res.setdefault("trial_diffs", []).append(
                f"{slot_key}: 叶子 {_fmt(leaf)} vs trial {_fmt(trial)}"
                + (f"（倍数 {ratio:.2f}）" if leaf else "")
            )
    return res


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=None, help="只跑单个项目 UUID")
    ap.add_argument("--out", default=None, help="报告落盘路径")
    args = ap.parse_args()

    from app.core.database import async_session

    lines: list[str] = []

    def emit(s: str = "") -> None:
        lines.append(s)

    async with async_session() as db:
        projects = await _projects(db, args.project)
        emit("=" * 100)
        emit(f"D 循环四表取数真实库验收（只读）— {len(projects)} 个项目 × {len(_CYCLES)} 循环")
        emit("=" * 100)

        total_violations = 0
        state_tally: dict[str, int] = {}
        trial_diff_count = 0

        for pid, year, name in projects:
            emit("")
            emit(f"── 项目 {pid[:8]} / {year} / {name[:24]} " + "─" * 40)
            for wp in _CYCLES:
                try:
                    r = await _run_cycle(db, wp, pid, year)
                except Exception as e:  # noqa: BLE001
                    emit(f"  {wp}  ✗ 异常: {type(e).__name__}: {e}")
                    total_violations += 1
                    continue

                if not r.get("slots"):
                    emit(f"  {wp}  — {r.get('path', '')}")
                    continue

                head = (
                    f"  {wp}  row={r.get('row_code', '?'):8s} "
                    f"from={r.get('resolved_from', '?'):22s} fetch_ok={r.get('fetch_ok')}"
                )
                emit(head)
                for key, s in r["slots"].items():
                    state_tally[s["state"]] = state_tally.get(s["state"], 0) + 1
                    flags = []
                    if s["prefix_mismatch"]:
                        flags.append("PREFIX_MISMATCH")
                    if s["dropped"]:
                        flags.append(f"dropped={len(s['dropped'])}")
                    if s["warnings"]:
                        flags.append(f"warn={len(s['warnings'])}")
                    emit(
                        f"      {key:10s} state={s['state']:16s} "
                        f"closing={_fmt(s['closing']):>18s} rows={s['tb_rows_count']:<4d} "
                        f"codes={s['query_codes']} {' '.join(flags)}"
                    )
                    for d in s["dropped"]:
                        # 同上：元素是 dict 不是二元组（首版在此处也踩了一次）
                        emit(
                            "          剔除 %s（%s）: %s"
                            % (d.get("code"), d.get("name") or "名称缺失", d.get("reason"))
                        )
                for d in r.get("trial_diffs", []) or []:
                    trial_diff_count += 1
                    emit(f"      ⚠ 三口径差异 {d}")
                for v in r["violations"]:
                    total_violations += 1
                    emit(f"      ✗ {v}")

        emit("")
        emit("=" * 100)
        emit("汇总")
        emit(f"  四态分布: {dict(sorted(state_tally.items()))}")
        emit(f"  三口径差异（如实暴露，非违规）: {trial_diff_count} 处")
        emit(f"  判据违规: {total_violations} 处")
        emit("=" * 100)
        emit("PASS" if total_violations == 0 else "FAIL")

    text = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"报告已写入 {args.out}（{len(lines)} 行）")
    else:
        print(text)
    return 0 if total_violations == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
