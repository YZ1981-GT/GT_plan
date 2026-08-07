"""真实库验收：逐条求值 `WP()` 预设锚点，按**六态**分组输出（只读）。

spec: .kiro/specs/prefill-wp-prev-resolution-repair/ Task 12
      Requirements 7.1 / 7.2 / 7.3 / 7.5

用法
----

    python backend/scripts/diagnose/verify_prefill_wp_prev_live.py
    python backend/scripts/diagnose/verify_prefill_wp_prev_live.py --all-cycles
    python backend/scripts/diagnose/verify_prefill_wp_prev_live.py --project <uuid>

为什么必须有这个脚本
------------------

本 spec 修的缺陷正是「`--check` 归零 / 测试全绿，但真实库一格数据都取不到」——
`parsed_data['cells']` 全库零命中而 fail-soft 无告警。**同款机理在本轮又复现一次**：
`read_anchor_value` 首版把 `checklist_responses` 的列名写成 `workpaper_id`（真实列名
是 `wp_id`），SQL 抛 `UndefinedColumnError` → 被 `_resolve_wp_formula` 的
`except Exception` 吞成 `logger.warning` → 对外仍是 `None`，与「本项目未编制」
完全同形。四层验证（`get_diagnostics` / 单测替身 / Vite / 语法校验）全绿。

⇒ **唯一能证明链路活着的证据是「真实库取到数」**，这就是本脚本的职责。

六态（禁合并成「无数据」）
------------------------

======================  ====================================================
`HIT`                   取到数（value 非 None）
`EMPTY`                 `item_id` 存在但值为空 / 非数值 / 空数组
`NO_WORKPAPER`          该 wp_code 在本项目无底稿（未生成，正常业务态）
`NO_ITEM`               底稿存在但 `item_id` 未落库（明细表未编制，非缺陷）
`NO_COLUMN`             行数组里无该列键 / `ROW` 形态 `row_key` 未命中
`UNALIGNED`             三参组不在 `ANCHOR_MAP`（在待对齐清单或未登记）
======================  ====================================================

把 `NO_ITEM`（用户没录）与 `UNALIGNED`（链路仍是死的）合并，正是本缺陷长期潜伏的机理。

输出约定
-------

控制台**只打 ASCII**（Windows GBK 控制台遇到 emoji / `⇒` 会 `UnicodeEncodeError`
且崩点在写盘之后 → 看起来像脚本失败其实已成功）；完整报告用
`Path.write_text(encoding='utf-8')` 落**绝对路径**（写相对路径会落在 CWD 而非脚本目录，
下一步 `read_file` 按预期路径读必 ENOENT）。

**禁构造 fixture 冒充「已修好」**（R7.5）—— 某锚点在真实库未编制就如实报 `NO_ITEM`。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import sqlalchemy as sa  # noqa: E402

from app.services.prefill_anchor_map import (  # noqa: E402
    ANCHOR_MAP,
    UNALIGNED,
    AnchorReadStatus,
    read_anchor_value,
    resolve_anchor,
)

_PRESET_JSON = _BACKEND / "data" / "prefill_formula_mapping.json"
_OUT = Path(__file__).resolve().parent / "verify_prefill_wp_prev_live.txt"


# ─────────────────────────── 预设解析（与守卫同口径）───────────────────────────


def _iter_preset_calls(fn: str) -> set[tuple[str, str, str]]:
    """从预设 JSON 抽 ``fn('a','b','c')`` 三元组。

    🔴 实参里可能含**半角括号**（``PREV('D2','附注披露信息(上市公司)','上年账面价值')``）
    ⇒ 禁用 ``\\(([^)]*)\\)``，那会在第一个 ``)`` 处截断把 3 参读成 2 参并静默丢条。
    改为逐字符扫引号内实参，只在引号外遇到 ``)`` 才收尾。
    """
    doc = json.loads(_PRESET_JSON.read_text(encoding="utf-8"))
    out: set[tuple[str, str, str]] = set()
    needle = f"{fn}("
    for block in doc.get("mappings") or []:
        for cell in block.get("cells") or []:
            expr = str(cell.get("formula") or "")
            idx = 0
            while True:
                pos = expr.find(needle, idx)
                if pos < 0:
                    break
                before = expr[pos - 1] if pos > 0 else "="
                idx = pos + len(needle)
                if before.isalnum() or before == "_":
                    continue  # TB_SUM( 被 SUM( 前缀误配
                args: list[str] = []
                i = idx
                while i < len(expr):
                    ch = expr[i]
                    if ch == "'":
                        j = expr.find("'", i + 1)
                        if j < 0:
                            break
                        args.append(expr[i + 1 : j])
                        i = j + 1
                    elif ch == ")":
                        break
                    else:
                        i += 1
                if len(args) >= 3:
                    out.add((args[0], args[1], args[2]))
    return out


# ─────────────────────────── 求值 ───────────────────────────


#: 取值层抛异常时的专用态（不属六态，但**绝不能**并进「无数据」——本轮 P0 正是这样藏住的）
_ERROR = "ERROR"

#: 🔴 **态名口径唯一约定：全大写**（`HIT` / `NO_ITEM` / `ERROR`）。
#:
#: `AnchorReadStatus` 的 `value` 是**小写**（`"hit"`），而报告的分布统计、ERROR 分支、
#: 验收判据都按大写态名比对 ⇒ 中间必须有且只有一处 `.upper()`。
#: 本轮在这一处上连踩两次反向的错：首版忘了 `.upper()` ⇒ 分布恒 0 / ERROR 分支恒不触发 /
#: 已有 4 条 HIT 却报 INCONCLUSIVE；修复时又把比对侧改成小写而生产侧仍 `.upper()` ⇒
#: 自检打红。⇒ 判据与展示的态名一律**从枚举派生后统一 `.upper()`**，禁写字面量。
_HIT = AnchorReadStatus.HIT.value.upper()

#: 统计与展示的态名全集（大写）。**从枚举派生**而非手写清单 ——
#: 手写清单与实际产出的态名一旦漂移，`Counter.get()` 静默返 0，
#: 报告就会出现「明细里有 HIT、分布全 0」这种自相矛盾的输出。
_STATUS_NAMES: tuple[str, ...] = tuple(
    s.value.upper() for s in AnchorReadStatus
) + (_ERROR,)


@dataclass
class _Row:
    project: str
    triple: tuple[str, str, str]
    status: str
    value: str
    detail: str


async def _eval_triples(
    db, project_id: UUID, project_label: str, triples: list[tuple[str, str, str]]
) -> list[_Row]:
    rows: list[_Row] = []
    for triple in triples:
        wp_code, sheet, cell_ref = triple
        spec = resolve_anchor(wp_code, sheet, cell_ref)
        if spec is None:
            reason = UNALIGNED.get(triple, "未登记（既不在 ANCHOR_MAP 也不在 UNALIGNED）")
            rows.append(
                _Row(
                    project_label,
                    triple,
                    AnchorReadStatus.UNALIGNED.value.upper(),
                    "-",
                    reason[:120],
                )
            )
            continue
        try:
            res = await read_anchor_value(db, project_id, wp_code, spec)
        except Exception as exc:  # noqa: BLE001
            # 🔴 这里**不能**吞成「无数据」—— 本轮的 P0 正是这样藏了一整轮
            rows.append(
                _Row(
                    project_label,
                    triple,
                    _ERROR,
                    "-",
                    f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        rows.append(
            _Row(
                project_label,
                triple,
                # 🔴 必须 .upper() —— 枚举 value 是小写（`hit`），而分布统计/验收判据
                # 按大写态名比对。首版漏了它 ⇒ 六态分布全 0、ERROR 分支恒不触发、
                # 验收判据把「已有 4 条 HIT」误报成 INCONCLUSIVE（脚本级假阴性）。
                res.status.value.upper(),
                "-" if res.value is None else str(res.value),
                res.detail,
            )
        )
    return rows


async def _pick_projects(db, only: str | None) -> list[tuple[UUID, str, int]]:
    if only:
        row = (
            await db.execute(
                sa.text(
                    "SELECT id::text, COALESCE(name, id::text), COALESCE(audit_year, 2025) "
                    "FROM projects WHERE id = CAST(:pid AS uuid)"
                ),
                {"pid": only},
            )
        ).first()
        if row is None:
            raise SystemExit(f"project {only} not found")
        return [(UUID(row[0]), row[1], int(row[2]))]

    # 默认：按「命中本 spec 锚点 item_id 的行数」降序，取前 3 个
    item_ids = sorted({s.item_id for s in ANCHOR_MAP.values()})
    res = await db.execute(
        sa.text(
            """
            SELECT p.id::text,
                   COALESCE(p.name, p.id::text) AS nm,
                   COALESCE(p.audit_year, 2025) AS yr,
                   count(cr.id) AS n
            FROM projects p
            JOIN working_paper wp ON wp.project_id = p.id AND wp.is_deleted = false
            JOIN wp_index wi ON wi.id = wp.wp_index_id AND wi.wp_code LIKE 'D%'
            LEFT JOIN checklist_responses cr
                   ON cr.wp_id = wp.id AND cr.item_id = ANY(:items)
            GROUP BY p.id, p.name, p.audit_year
            ORDER BY n DESC, nm ASC
            LIMIT 3
            """
        ),
        {"items": item_ids},
    )
    return [(UUID(r[0]), r[1], int(r[2])) for r in res.all()]


async def _run(args: argparse.Namespace) -> str:
    from app.core.database import async_session

    lines: list[str] = []
    d_wp = sorted(t for t in _iter_preset_calls("WP") if t[0].startswith("D"))
    all_wp = sorted(_iter_preset_calls("WP"))
    all_prev = sorted(_iter_preset_calls("PREV"))

    lines.append("=" * 78)
    lines.append("prefill WP()/PREV() 真实库验收")
    lines.append("=" * 78)
    lines.append(f"预设规模：WP {len(all_wp)} 三元组 / PREV {len(all_prev)} 三元组")
    lines.append(f"D 循环 WP 三元组：{len(d_wp)}")
    lines.append(f"ANCHOR_MAP 已对齐：{len(ANCHOR_MAP)}    UNALIGNED 待对齐：{len(UNALIGNED)}")
    lines.append("")

    async with async_session() as db:
        projects = await _pick_projects(db, args.project)
        lines.append(f"参与验收的项目（{len(projects)} 个）：")
        for pid, name, yr in projects:
            lines.append(f"  - {name}  ({pid}, audit_year={yr})")
        lines.append("")

        targets = all_wp if args.all_cycles else d_wp
        all_rows: list[_Row] = []
        for pid, name, _yr in projects:
            all_rows += await _eval_triples(db, pid, name, targets)

    # 六态分布
    dist = Counter(r.status for r in all_rows)

    # 🔴 自检：每一行的 status 都必须落在 _STATUS_NAMES 内，否则统计静默恒 0。
    # 首版就是因为大小写不一致而「逐条明细有 HIT、分布却全 0、验收判据报 INCONCLUSIVE」——
    # 一个只报告不落库的脚本，其唯一产出就是这份报告，报告本身错了等于白跑。
    unknown = sorted({r.status for r in all_rows} - set(_STATUS_NAMES))
    if unknown:
        raise SystemExit(
            f"[FATAL] 出现未登记的状态名 {unknown}，分布统计会静默漏计。"
            f"合法态名：{list(_STATUS_NAMES)}"
        )
    if all_rows and sum(dist.get(st, 0) for st in _STATUS_NAMES) != len(all_rows):
        raise SystemExit(
            f"[FATAL] 分布合计 {sum(dist.get(st, 0) for st in _STATUS_NAMES)} "
            f"!= 实际行数 {len(all_rows)}，统计口径有漏。"
        )

    lines.append("-" * 78)
    lines.append("六态分布（跨全部参与项目）")
    lines.append("-" * 78)
    for st in _STATUS_NAMES:
        lines.append(f"  {st:<14}{dist.get(st, 0)}")
    lines.append("")

    if dist.get(_ERROR):
        lines.append("!! 出现 ERROR —— 取值层抛异常。这是接线缺陷不是「无数据」。")
        for r in all_rows:
            if r.status == _ERROR:
                lines.append(f"   {r.project} | {'|'.join(r.triple)} -> {r.detail}")
        lines.append("")

    # 逐条明细（非 --all-cycles 时全打；--all-cycles 只打 HIT/ERROR）
    lines.append("-" * 78)
    lines.append("逐条结果（HIT 附取值路径供人工核对）")
    lines.append("-" * 78)
    for r in all_rows:
        if args.all_cycles and r.status not in (_HIT, _ERROR):
            continue
        lines.append(f"[{r.status:<12}] {r.project}")
        lines.append(f"    WP({r.triple[0]!r}, {r.triple[1]!r}, {r.triple[2]!r})")
        lines.append(f"    value  = {r.value}")
        lines.append(f"    detail = {r.detail}")
    lines.append("")

    # 验收判据
    hits = [r for r in all_rows if r.status == _HIT]
    lines.append("=" * 78)
    lines.append("验收判据")
    lines.append("=" * 78)
    if dist.get(_ERROR):
        lines.append("FAIL：存在 ERROR，取值层有接线缺陷。")
    elif hits:
        lines.append(f"PASS：{len(hits)} 条取到数（链路已活）。逐条金额见上方 detail。")
        lines.append("      注意：value=0 同样是 HIT —— 「余额为 0」与「取不到」必须可区分，")
        lines.append("      这正是六态存在的意义（0 是实证值，None 才是缺失）。")
    else:
        lines.append("INCONCLUSIVE：无一条 HIT。逐个查上方状态：")
        lines.append("  - 全 NO_ITEM  => 真实库该明细表未编制，如实报告，不得用 fixture 冒充")
        lines.append("  - 有 UNALIGNED => 该三元组在待对齐清单（派生列等），属预期")
        lines.append("  - 有 NO_COLUMN => 映射的列键与真实落库键不符，需修 ANCHOR_MAP")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__ or "")
    ap.add_argument("--project", help="只验收指定 project uuid")
    ap.add_argument(
        "--all-cycles",
        action="store_true",
        help="扫全部循环的 WP 三元组（非 D 循环预期全 UNALIGNED）",
    )
    args = ap.parse_args()

    report = asyncio.run(_run(args))
    _OUT.write_text(report, encoding="utf-8")
    # 控制台只打 ASCII 摘要（GBK 控制台遇非 ASCII 会崩在写盘之后）
    print(f"[OK] report written: {_OUT}")
    for ln in report.splitlines():
        if ln.startswith(("PASS", "FAIL", "INCONCLUSIVE")):
            print("[RESULT] " + ln.encode("ascii", "replace").decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
