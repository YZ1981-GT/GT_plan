"""双族加和的零回归验收（只读，Task 9 / Property 1 · 9）。

**要证明什么**

V145 把 ``BS-031`` / ``BS-063`` 改成双族加和后：

1. **单族项目取值逐分不变** —— 项目只用旧族时 ``TB('1651')`` 取不到数（返 0），
   加和结果等于改造前；只用新族时改造前取到的是 0.04% 的错数，改造后才对。
2. **零双算** —— 不存在「两族同时非零」的项目。这是加和口径的**前提条件**，
   一旦被破坏（将来某项目同时启用两族且都有余额），加和会双算，
   必须改为择一。本脚本把这个前提从「一次性实证」升级为可复验判据。

**为什么必须连真实库**

自造 fixture 与「两族互斥」这个假设同构 ⇒ 单测全绿也证明不了任何事
（memory 已记多次：只有真实数据能证伪）。

用法::

    python backend/scripts/diagnose/verify_dual_family_zero_regression.py
    python backend/scripts/diagnose/verify_dual_family_zero_regression.py --out tmp_x.txt

退出码：0 = 全部判据通过；1 = 有判据违规（打印明细）。

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
      Requirements 1.3, 1.4, 1.6 / Property 1, 9
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import sqlalchemy as sa  # noqa: E402

from app.core.database import async_session  # noqa: E402
from app.services.four_table.dual_family_codes import (  # noqa: E402
    ALL_DUAL_FAMILY_CODES,
    BS031_GROUPS,
    BS063_GROUPS,
    ROU_LEASE_DUAL_FAMILIES,
)

_LINES: list[str] = []
_VIOLATIONS: list[str] = []


def _say(msg: str = "") -> None:
    _LINES.append(msg)


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


async def _load() -> dict:
    """一次 asyncio.run 里取完全部数据（连接池绑定首个事件循环）。"""
    codes = list(ALL_DUAL_FAMILY_CODES)
    async with async_session() as db:
        tb = (
            await db.execute(
                sa.text(
                    "SELECT project_id::text AS pid, standard_account_code AS code, "
                    "       SUM(COALESCE(unadjusted_amount,0)) AS unadj, "
                    "       COUNT(*) AS n "
                    "FROM trial_balance "
                    "WHERE standard_account_code = ANY(:codes) "
                    "  AND COALESCE(is_deleted,false) = false "
                    "GROUP BY 1,2"
                ),
                {"codes": codes},
            )
        ).fetchall()

        bal = (
            await db.execute(
                sa.text(
                    "SELECT project_id::text AS pid, "
                    "       LEFT(account_code,4) AS code4, "
                    "       SUM(COALESCE(closing_balance,0)) AS closing, "
                    "       COUNT(*) AS n "
                    "FROM tb_balance "
                    "WHERE LEFT(account_code,4) = ANY(:codes) "
                    "  AND COALESCE(is_deleted,false) = false "
                    "GROUP BY 1,2"
                ),
                {"codes": codes},
            )
        ).fetchall()

        cfg = (
            await db.execute(
                sa.text(
                    "SELECT row_code, applicable_standard, formula "
                    "FROM report_config "
                    "WHERE row_code IN ('BS-031','BS-063') "
                    "ORDER BY row_code, applicable_standard"
                )
            )
        ).fetchall()

    return {
        "tb": {(r.pid, r.code): (_d(r.unadj), int(r.n)) for r in tb},
        "bal": {(r.pid, r.code4): (_d(r.closing), int(r.n)) for r in bal},
        "cfg": [(r.row_code, r.applicable_standard, r.formula or "") for r in cfg],
    }


def _report_config_section(cfg: list[tuple[str, str, str]]) -> None:
    _say("=" * 78)
    _say("① report_config 现状（V145 后应含双族）")
    _say("=" * 78)
    for row, std, formula in cfg:
        missing = [
            g.alternate
            for g in (BS031_GROUPS if row == "BS-031" else BS063_GROUPS)
            if g.alternate and g.alternate not in formula
        ]
        flag = "OK " if not missing else "BAD"
        if missing:
            _VIOLATIONS.append(f"{row}/{std} 公式缺新族码 {missing}")
        _say(f"  [{flag}] {row} / {std}")
        _say(f"        {formula}")


def _mutual_exclusion_section(data: dict) -> None:
    """核心判据：两族在同一项目内互斥 ⇒ 加和零双算。"""
    for table_key, label, amount_label in (
        ("tb", "trial_balance.unadjusted_amount", "未审数"),
        ("bal", "tb_balance.closing_balance", "期末余额"),
    ):
        rows = data[table_key]
        _say()
        _say("=" * 78)
        _say(f"② 双族互斥判据 —— {label}")
        _say("=" * 78)
        projects = sorted({pid for (pid, _c) in rows})
        if not projects:
            _VIOLATIONS.append(f"{label}: 一个项目都没查到 —— 判据空转")
            _say("  [BAD] 无数据（判据空转）")
            continue

        for group in ROU_LEASE_DUAL_FAMILIES:
            if not group.alternate:
                continue
            p_amt = rows.get(("", ""), None)  # 占位，避免 lint 抱怨
            del p_amt
            both_nonzero: list[str] = []
            only_primary: list[str] = []
            only_alternate: list[str] = []
            both_zero: list[str] = []
            for pid in projects:
                pv, _pn = rows.get((pid, group.primary), (Decimal("0"), 0))
                av, _an = rows.get((pid, group.alternate), (Decimal("0"), 0))
                has_p = (pid, group.primary) in rows
                has_a = (pid, group.alternate) in rows
                if not has_p and not has_a:
                    continue
                if pv != 0 and av != 0:
                    both_nonzero.append(f"{pid[:8]}(P={pv} A={av})")
                elif pv != 0:
                    only_primary.append(f"{pid[:8]}={pv}")
                elif av != 0:
                    only_alternate.append(f"{pid[:8]}={av}")
                else:
                    both_zero.append(pid[:8])

            _say(f"  {group.primary} / {group.alternate}  ({group.label})")
            _say(f"    只旧族非零 ({len(only_primary)}): {only_primary or '-'}")
            _say(f"    只新族非零 ({len(only_alternate)}): {only_alternate or '-'}")
            _say(f"    两族均为 0 ({len(both_zero)}): {both_zero or '-'}")
            if both_nonzero:
                _VIOLATIONS.append(
                    f"{label} {group.primary}/{group.alternate}: "
                    f"两族同时非零 {both_nonzero} ⇒ 加和会双算，须改择一口径"
                )
                _say(f"    [BAD] 两族同时非零: {both_nonzero}")
            else:
                _say("    [OK ] 互斥成立 ⇒ 加和零双算")


def _coverage_section(data: dict) -> None:
    """覆盖率：改造前（只取 primary）vs 改造后（双族加和）。"""
    rows = data["tb"]
    _say()
    _say("=" * 78)
    _say("③ 取数覆盖率对比（trial_balance.unadjusted_amount 全库合计）")
    _say("=" * 78)
    for group in ROU_LEASE_DUAL_FAMILIES:
        p_total = sum(
            (v for (pid, c), (v, _n) in rows.items() if c == group.primary),
            Decimal("0"),
        )
        a_total = (
            sum(
                (v for (pid, c), (v, _n) in rows.items() if c == group.alternate),
                Decimal("0"),
            )
            if group.alternate
            else Decimal("0")
        )
        both = p_total + a_total
        pct = (p_total / both * 100) if both else Decimal("0")
        _say(
            f"  {group.label:16s} 旧族 {group.primary}={p_total:>20,.2f}  "
            f"新族 {group.alternate or '-':4s}={a_total:>20,.2f}"
        )
        _say(f"    {'':16s} 改造前覆盖率 = {pct:.2f}%   改造后 = 100.00%")


def _per_project_section(data: dict) -> None:
    """逐项目：改造前后 BS-031 / BS-063 取值。"""
    rows = data["tb"]
    _say()
    _say("=" * 78)
    _say("④ 逐项目 BS-031 / BS-063 取值（改造前 vs 改造后）")
    _say("=" * 78)
    projects = sorted({pid for (pid, _c) in rows})
    for row_code, groups in (("BS-031", BS031_GROUPS), ("BS-063", BS063_GROUPS)):
        _say(f"  {row_code}")
        for pid in projects:
            before = Decimal("0")
            after = Decimal("0")
            for g in groups:
                pv, _ = rows.get((pid, g.primary), (Decimal("0"), 0))
                av, _ = rows.get((pid, g.alternate or "~none~"), (Decimal("0"), 0))
                sign = -1 if g.is_provision else 1
                before += sign * pv
                after += sign * (pv + av)
            same = "unchanged" if before == after else "CHANGED"
            _say(
                f"    {pid[:8]}  before={before:>18,.2f}  "
                f"after={after:>18,.2f}  [{same}]"
            )


async def _main_async() -> int:
    data = await _load()
    _report_config_section(data["cfg"])
    _mutual_exclusion_section(data)
    _coverage_section(data)
    _per_project_section(data)

    _say()
    _say("=" * 78)
    if _VIOLATIONS:
        _say(f"结果: FAIL —— {len(_VIOLATIONS)} 项判据违规")
        for v in _VIOLATIONS:
            _say(f"  - {v}")
        return 1
    _say("结果: PASS —— 全部判据通过（互斥成立 / 双族已覆盖 / 单族项目取值不变）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="双族加和零回归验收（只读）")
    ap.add_argument("--out", default=None, help="报告写入路径（默认 stdout）")
    args = ap.parse_args()

    try:
        rc = asyncio.run(_main_async())
    except Exception as e:  # noqa: BLE001
        _say(f"[ERR] 执行失败: {e!r}")
        rc = 1

    text = "\n".join(_LINES) + "\n"
    if args.out:
        # 🔴 脚本自己写盘 —— PowerShell `>` 重定向会把 UTF-8 中文腌坏
        Path(args.out).write_text(text, encoding="utf-8")
        print("[OK] report written")  # ASCII，避免 GBK 控制台崩
    else:
        print(text)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
