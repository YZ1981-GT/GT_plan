"""E1 账户级取数真实库验收（只读，默认 dry-run）。

用法：

    python backend/scripts/diagnose/verify_e1_account_extraction_live.py
    python backend/scripts/diagnose/verify_e1_account_extraction_live.py --all-projects
    python backend/scripts/diagnose/verify_e1_account_extraction_live.py --project 0ec33ac9

逐项目输出：账户数 / `parsed_level` 分布 / 各槽勾稽 diff / `unassigned` 明细，
并与 `test_e1_bank_accounts_live.ACCOUNT_COUNT_BASELINE` 对照。

🔴 三条硬约束（每条都对应一次平台级踩坑）：

1. **只读** —— 全程无 INSERT/UPDATE/DELETE，不改任何数据。
2. **专用引擎 + NullPool**，同 loop 内 dispose；**禁借 `app.core.database.async_session`
   共享池**（借了会让后续连库测试报 `Event loop is closed`）。
3. **态名全集从枚举派生** + 启动即自检 —— 「态名与统计表键大小写不一致」会让
   `Counter.get()` 静默返 0，产出「明细里有 HIT、分布全 0」的自相矛盾报告
   （诊断脚本级假阴性，platform 已踩过一次）。

无法验证时输出 `UNVERIFIABLE` 并写明原因，**禁用 fixture 冒充**。

spec: .kiro/specs/e-cycle-extraction-formula-and-disclosure-completion/ (Task 6)
Requirements: 10.1, 10.7
"""

from __future__ import annotations

import argparse
import asyncio
import enum
import os
import sys
from collections import Counter
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

OUT = Path(__file__).resolve().parent / "_verify_e1_account_extraction_live.txt"

#: 勾稽容差（元）—— 与共享件 `e1_bank_accounts.TOLERANCE` 同口径
TOLERANCE = 0.005


class Verdict(str, enum.Enum):
    """判定态。**态名全集从本枚举派生**，禁在别处另写一份字符串清单。"""

    OK = "OK"
    DIFF = "DIFF"
    NO_AUX = "NO_AUX"
    NO_ACCOUNT = "NO_ACCOUNT"
    BASELINE_MISMATCH = "BASELINE_MISMATCH"
    ERROR = "ERROR"


#: 态名全集（派生，不手写）
VERDICT_NAMES: tuple[str, ...] = tuple(v.value for v in Verdict)


def _self_check() -> None:
    """启动自检：态名不重复、派生集合非空。不匹配直接 [FATAL] 退出。"""
    if len(VERDICT_NAMES) != len(set(VERDICT_NAMES)):
        print("[FATAL] Verdict 枚举存在重复取值", file=sys.stderr)
        raise SystemExit(1)
    if not VERDICT_NAMES:
        print("[FATAL] Verdict 枚举为空（态名派生失效）", file=sys.stderr)
        raise SystemExit(1)


def _db_url() -> str | None:
    """从环境变量拼 DB URL（与平台一致，只读用）。"""
    try:
        from app.core.config import settings  # noqa: PLC0415

        url = getattr(settings, "DATABASE_URL", None) or getattr(
            settings, "SQLALCHEMY_DATABASE_URI", None
        )
        if url:
            return str(url)
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get("DATABASE_URL")


async def _load(url: str, only_project: str | None, all_projects: bool) -> dict:
    """一次性拉取全部需要的数据（专用引擎 + NullPool，同 loop dispose）。"""
    engine = create_async_engine(url, poolclass=NullPool, echo=False)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    out: dict = {"projects": [], "note": ""}
    try:
        async with maker() as db:
            from app.models.audit_platform_models import TbAuxBalance  # noqa: PLC0415
            from app.services.dataset_query import get_active_filter  # noqa: PLC0415
            from app.services.four_table.e1_bank_accounts import (  # noqa: PLC0415
                AUX_TYPE_BANK_ACCOUNT,
                assign_accounts_to_slots,
                build_e1_account_prefill,
                fetch_e1_bank_accounts,
            )

            # 有 aux 银行账户维度数据的 (project, year)
            rows = (
                await db.execute(
                    sa.text(
                        "SELECT DISTINCT project_id::text AS pid, year "
                        "FROM tb_aux_balance "
                        "WHERE aux_type = :t AND is_deleted = false "
                        "ORDER BY 1, 2"
                    ),
                    {"t": AUX_TYPE_BANK_ACCOUNT},
                )
            ).fetchall()
            candidates = [(r.pid, int(r.year)) for r in rows]
            if only_project:
                candidates = [c for c in candidates if c[0].startswith(only_project)]
            elif not all_projects:
                candidates = candidates[:8]

            if not candidates:
                out["note"] = (
                    "UNVERIFIABLE：库中无 aux_type='银行账户' 的数据 "
                    "（账户级取数无从验证；这是数据事实，不用 fixture 冒充）"
                )
                return out

            for pid, year in candidates:
                item: dict = {"pid": pid, "year": year}
                try:
                    # 独立 SQL 交叉核对（不拿被测函数证明自己）
                    active = await get_active_filter(
                        db, TbAuxBalance.__table__, pid, year
                    )
                    indep = (
                        await db.execute(
                            sa.select(
                                sa.func.count(sa.distinct(TbAuxBalance.aux_name)),
                                sa.func.coalesce(
                                    sa.func.sum(
                                        sa.func.coalesce(TbAuxBalance.closing_balance, 0)
                                    ),
                                    0,
                                ),
                            ).where(
                                sa.and_(
                                    active,
                                    TbAuxBalance.aux_type == AUX_TYPE_BANK_ACCOUNT,
                                    TbAuxBalance.account_code.like("1002%"),
                                )
                            )
                        )
                    ).first()
                    item["indep_account_names"] = int(indep[0] or 0)
                    item["indep_closing_sum"] = round(float(indep[1] or 0), 2)

                    # 被测路径
                    accounts = await fetch_e1_bank_accounts(
                        db, pid, year, account_prefixes=["1002"]
                    )
                    item["account_count"] = len(accounts)
                    item["parsed_level_dist"] = dict(
                        Counter(str(a.parsed_level) for a in accounts)
                    )
                    item["fetched_closing_sum"] = round(
                        sum(a.closing for a in accounts), 2
                    )

                    assignment = assign_accounts_to_slots(accounts, {"bank": ["1002"]})
                    payload = build_e1_account_prefill(assignment, {})
                    item["unassigned"] = [
                        {"code": r["account_code"], "no": r["account_no"],
                         "closing": r["closing"]}
                        for r in payload["accounts"]["unassigned"]
                    ]

                    # 与 tb_balance 叶子勾稽（1002 客户不分户 ⇒ 直接取该科目合计）
                    #
                    # 🔴 **必须走 `get_active_filter`，不能裸写 `is_deleted = false`**：
                    # 同一 `account_code='1002'` 在多个 dataset 各有一行（实测
                    # `0ec33ac9` 3 行 / `2aa00f57` 2 行 / `c8621493` 3 行，金额相同），
                    # 裸查全加起来正好是 aux 侧的 2~3 倍 ⇒ 产出「diff 恰好等于
                    # −取数合计」的假 DIFF（本脚本首轮实测 4 个项目全中招）。
                    # aux 侧已走 active，两侧口径必须一致才有勾稽意义。
                    from app.models.audit_platform_models import (  # noqa: PLC0415
                        TbBalance,
                    )

                    tb_active = await get_active_filter(
                        db, TbBalance.__table__, pid, year
                    )
                    leaf = (
                        await db.execute(
                            sa.select(
                                sa.func.coalesce(
                                    sa.func.sum(
                                        sa.func.coalesce(TbBalance.closing_balance, 0)
                                    ),
                                    0,
                                )
                            ).where(
                                sa.and_(
                                    tb_active,
                                    TbBalance.account_code == "1002",
                                )
                            )
                        )
                    ).scalar()
                    item["tb_balance_1002"] = round(float(leaf or 0), 2)
                    item["diff_vs_tb"] = round(
                        item["fetched_closing_sum"] - item["tb_balance_1002"], 2
                    )

                    if not accounts:
                        item["verdict"] = Verdict.NO_ACCOUNT.value
                    elif abs(item["diff_vs_tb"]) > TOLERANCE:
                        item["verdict"] = Verdict.DIFF.value
                    elif item["account_count"] != item["indep_account_names"]:
                        item["verdict"] = Verdict.BASELINE_MISMATCH.value
                    else:
                        item["verdict"] = Verdict.OK.value
                except Exception as exc:  # noqa: BLE001
                    item["verdict"] = Verdict.ERROR.value
                    item["error"] = f"{type(exc).__name__}: {exc}"
                    try:
                        await db.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                out["projects"].append(item)
    finally:
        await engine.dispose()
    return out


def _baseline() -> dict[str, int]:
    """读 Task 1 冻结的基线（单一真源，不在本脚本另抄一份）。"""
    try:
        sys.path.insert(0, str(_BACKEND / "tests" / "four_table"))
        from test_e1_bank_accounts_live import (  # type: ignore  # noqa: PLC0415
            ACCOUNT_COUNT_BASELINE,
        )

        return dict(ACCOUNT_COUNT_BASELINE)
    except Exception:  # noqa: BLE001
        return {}


def main() -> int:
    _self_check()
    ap = argparse.ArgumentParser(description="E1 账户级取数真实库验收（只读）")
    ap.add_argument("--all-projects", action="store_true", help="覆盖全部项目")
    ap.add_argument("--project", default=None, help="只跑某个项目（前缀匹配）")
    args = ap.parse_args()

    url = _db_url()
    lines: list[str] = ["E1 账户级取数真实库验收（只读 / dry-run）", ""]
    if not url:
        lines.append("UNVERIFIABLE：拿不到 DATABASE_URL（未配置 .env / 环境变量）")
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return 0

    data = asyncio.run(_load(url, args.project, args.all_projects))
    base = _baseline()

    if data.get("note"):
        lines.append(data["note"])
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return 0

    dist = Counter(str(p.get("verdict")) for p in data["projects"])
    # 🔴 态名从枚举派生 + 断言实际态名在合法集合内（防脚本级假阴性）
    unknown = [k for k in dist if k not in VERDICT_NAMES]
    if unknown:
        print(f"[FATAL] 出现未登记的判定态 {unknown}（态名派生失效）", file=sys.stderr)
        return 1

    lines.append(f"{'项目':<12}{'年度':<6}{'账户数':>7}{'独立SQL':>8}"
                 f"{'取数合计':>16}{'tb_balance':>16}{'diff':>10}  判定")
    baseline_hits = 0
    for p in data["projects"]:
        short = str(p["pid"])[:8]
        lines.append(
            f"{short:<12}{p['year']:<6}{p.get('account_count', 0):>7}"
            f"{p.get('indep_account_names', 0):>8}"
            f"{p.get('fetched_closing_sum', 0):>16,.2f}"
            f"{p.get('tb_balance_1002', 0):>16,.2f}"
            f"{p.get('diff_vs_tb', 0):>10,.2f}  {p.get('verdict')}"
        )
        if p.get("error"):
            lines.append(f"    ERROR: {p['error']}")
        if p.get("unassigned"):
            lines.append(f"    unassigned {len(p['unassigned'])} 条：")
            for u in p["unassigned"]:
                lines.append(f"      {u['code']} / {u['no']} / {u['closing']:,.2f}")
        pl = p.get("parsed_level_dist") or {}
        if pl:
            lines.append(f"    parsed_level 分布 = {pl}")
        # 🔴 基线键是 `短码:年度` 复合键 —— 同一项目可有多个年度（实测
        # `2aa00f57` 有 2024/2025 两行、账户数 23 / 17），按短码单键比会
        # 让两个年度互相覆盖并产出假 WARN（本脚本首轮实测中招）。
        b = base.get(f"{short}:{p['year']}")
        if b is not None:
            baseline_hits += 1
            if b != p.get("account_count"):
                lines.append(
                    f"    [WARN] 与 Task 1 基线不符：基线={b} 实测={p.get('account_count')}"
                )

    # 🔴 基线命中数自检 —— 「一条都没命中」与「全部相符」在输出上无法区分，
    # 而索引键口径写错（如退化成短码单键）恰好表现为全部 miss ⇒ 静默假绿。
    # 连库守卫有 `assert checked > 0`，本脚本必须有等价自检。
    if base and baseline_hits == 0:
        print(
            "[FATAL] Task 1 基线一条都未命中（基线 "
            f"{len(base)} 条 / 本次 {len(data['projects'])} 个项目）—— "
            "索引键口径不对或基线已完全过期",
            file=sys.stderr,
        )
        lines.append("")
        lines.append(
            f"[FATAL] 基线命中 0/{len(base)} —— 索引键口径不对或基线已完全过期"
        )
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return 1

    lines.append("")
    lines.append(f"基线命中：{baseline_hits}/{len(base)}（键 = 短码:年度）")
    lines.append("判定分布（态名派生自 Verdict 枚举）：")
    for name in VERDICT_NAMES:
        lines.append(f"  {name:<20}{dist.get(name, 0)}")

    bad = dist.get(Verdict.DIFF.value, 0) + dist.get(Verdict.ERROR.value, 0)
    lines.append("")
    lines.append(f"结论：{'PASS' if bad == 0 else 'FAIL'}（DIFF+ERROR = {bad}）")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
