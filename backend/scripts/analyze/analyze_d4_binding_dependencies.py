"""真库 D4 entry 的**跨 binding 顺序依赖**实证审计（39 binding 全量、确定性）。

spec: oo-single-pass-materialize-and-room-leave · Requirement 1.2 · Task 2

用法（仓库根）：

    .venv\\Scripts\\python.exe backend/scripts/analyze/analyze_d4_binding_dependencies.py

证据落 `docs/operations/evidence/oo-single-pass-materialize/binding-dependencies.json`。

═══ 为什么是**常驻工具**（无 `_` 前缀）═══

任务 2 只是第一次跑它。它还要被跑至少两次：

* 任务 3 落地单趟写入后，必须重跑确认「计划位置无关」这条前提仍成立 —— 它是单趟正确性的
  充要条件，不是一次性结论；
* 任务 4 的新旧等值判据要用同一份逐 binding 计划签名做对照（自己再写一份签名口径 =
  两个真源）。

而且它的结论会随**契约**变（受管表集合、受管区行列、footer 归属），不随代码变 ⇒ 契约一动
就得重跑。一次性脚本在这里等于「同一份审计口径写三遍」。

═══ 审计的五类依赖（逐类给判决，拿不到实证就说拿不到）═══

| 类 | 问题 | 判法 |
|---|---|---|
| D1 同格写入 | 两个 binding 写同一格？ | 逐对求 `(part, coord)` 交集（**全量**，非抽样） |
| D2 计划位置无关 | 后一 binding 的**计划**是否读到前一 binding 的写入？ | 同一 binding 的计划在「原始字节」与「链式字节」上算两遍，逐字段比签名 |
| D3 公式落格 | 写入是否改 `<f>`、让别人读到新公式？ | 统计 `cached_value_only` / `preserved_formulas`，核对 apply 的写入面 |
| D4 跨 sheet 引用 | 受管 sheet 的公式是否引用**另一个** binding 写的格？ | 扫受管 sheet 的 `<f>` 文本找 `其它受管sheet名!坐标` |
| D5 命名区域 | 计划期读的 definedName / `_GT_SYNC` 是否被本趟写入改动？ | 核对「有没有任何 plan 写 workbook.xml / `_GT_SYNC` 部件」 |

🔴 D1 的实现刻意**不**复用单趟路径那条 decline 检查：审计要的是「碰撞在哪、是否值敏感」的
**完整**图景，decline 要的是「能不能合并」这个布尔，两者口径不同。任务 2 时那条检查还按
`for coord in set(plan.coords)` 遍历、命中即抛（报的列号随进程 hash 种子变，实测见过 `C38`
与 `E38`，且抛第一处之后不再看剩下的）—— 任务 3 已把它改成逐对求交 + 排序 + 报完整集合，
两边**共用** `excel_materialize.coord_sort_key` 这一个排序口径，但求交与判决仍各自独立。
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import platform
import re
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DEFAULT_OUT_DIR = _REPO / "docs" / "operations" / "evidence" / "oo-single-pass-materialize"
DEFAULT_LABEL = "binding-dependencies"

def _write_signature(write: Any) -> dict[str, Any]:
    """一处写入的**可比对**签名。`value` 用 `repr` —— `0` 与 `0.0` 必须区分得开。"""
    return {
        "coord": write.coord,
        "kind": write.kind.value,
        "value_repr": repr(write.value),
        "field_key": write.stable_field_key,
        "row_key": write.row_key,
        "mode": None if write.mode is None else str(write.mode),
        "formula_text": write.formula_text,
    }


def _plan_signature(step: Any) -> dict[str, Any]:
    """一个 binding 的**完整**计划签名：计划里被 apply 消费的每一项都进来。

    只比 `write_count` 之类的汇总量会漏掉「值变了但个数没变」这种最危险的情形，
    因此逐写入进签名（按坐标排序，消掉遍历顺序的噪声）。
    """
    plan = step.plan
    region = step.substrate_view.region
    return {
        "sheet_part": plan.sheet_part,
        "sheet_name": plan.sheet_name,
        "writes": sorted(
            (_write_signature(w) for w in plan.writes),
            key=lambda item: (item["coord"], item["kind"], item["field_key"]),
        ),
        "preserved_formulas": dict(sorted(plan.preserved_formulas.items())),
        "footer_marker_row": plan.footer_marker_row,
        "row_shift": None if plan.row_shift is None else plan.row_shift.as_dict(),
        "total_formula_rows": list(plan.total_formula_rows),
        "table_part": plan.table_part,
        "managed_sheet_key": plan.managed_sheet_key,
        "managed_table_name": plan.managed_table_name,
        "workbook_row_change": (
            None
            if plan.workbook_row_change is None
            else plan.workbook_row_change.as_dict()
        ),
        "dynamic_column_columns": {
            table: dict(sorted(cols.items()))
            for table, cols in sorted(plan.dynamic_column_columns.items())
        },
        # 计划期的**读取面**也进签名：region 区间 / runtime binding 若被前一 binding 改动，
        # 即使写入清单恰好没变，也说明「读到了别人的写入」。
        "region": {
            "sheet_part": region.sheet_part,
            "sheet_name": region.sheet_name,
            "uuid_column": region.uuid_column,
            "row_span": [int(min(region.row_span)), int(max(region.row_span))],
        },
        "runtime_binding": dict(sorted(dict(step.runtime_binding).items())),
        "strategy": step.strategy.strategy.value,
    }


def _diff_keys(left: Mapping[str, Any], right: Mapping[str, Any]) -> list[str]:
    """两份签名里**取值不同**的顶层键（排序，确定性）。"""
    return sorted(key for key in left if left[key] != right.get(key))


@dataclasses.dataclass(frozen=True)
class _Ctx:
    """一次审计要反复喂给 `_plan_materialize_step` 的那组不变量（取自**生产 adapter**）。

    刻意从 `world.adapter` 上取 role/kind/state/capability/limits/bindings，而不是在这里
    另填一组默认值：填错任何一个，算出来的计划就不是生产路径那一份，整篇审计作废。
    """

    definitions: Any
    projection: Any
    bindings: tuple[Any, ...]
    primary_table_key: str
    role: Any
    kind: Any
    state: Any
    capability: Any
    limits: Any


def _plan_step(ctx: _Ctx, *, binding: Any, substrate: Path, source_bytes: bytes) -> Any:
    """算一个 binding 的计划（生产内核 `_plan_materialize_step`，不是复刻）。"""
    from app.services.workpaper_sync.excel_materialize import _plan_materialize_step

    return _plan_materialize_step(
        substrate=substrate,
        projection=ctx.projection,
        definitions=ctx.definitions,
        binding=binding,
        substrate_role=ctx.role,
        substrate_kind=ctx.kind,
        substrate_state=ctx.state,
        source_bytes=source_bytes,
        capability=ctx.capability,
        intended_formulas=None,
        limits=ctx.limits,
        retain_identity_inventory=(binding.table_key == ctx.primary_table_key),
    )


def _plan_all_on_original(ctx: _Ctx, *, substrate: Path) -> list[Any]:
    """全部 binding 的计划都算在**原始** substrate 字节上（= 单趟路径的做法）。"""
    source_bytes = substrate.read_bytes()
    return [
        _plan_step(ctx, binding=binding, substrate=substrate, source_bytes=source_bytes)
        for binding in ctx.bindings
    ]


def _plan_all_chained(ctx: _Ctx, *, substrate: Path, workdir: Path) -> list[Any]:
    """逐 binding **链式**算计划：第 k 个算在前 k-1 个的写入结果上（= 现状路径的做法）。

    这就是 D2 的实验：两组计划若逐字段相同，「后一 binding 读到前一 binding 的写入」在真实
    契约上就**不成立**（对本 projection）。它比「读代码看有没有引用」强，因为计划期的读取面
    实际是**整本 zip**（`_plan_materialize_step` 把 `substrate_entries` 全量喂给
    `plan_managed_writes`），靠读代码穷举不完。
    """
    from app.services.workpaper_sync.excel_extract import release_scoped_workbooks
    from app.services.workpaper_sync.excel_materialize import _apply_step_to_bytes

    steps: list[Any] = []
    current_path = substrate
    current_bytes = substrate.read_bytes()
    intermediates: list[Path] = []
    try:
        for index, binding in enumerate(ctx.bindings):
            step = _plan_step(
                ctx, binding=binding, substrate=current_path, source_bytes=current_bytes
            )
            steps.append(step)
            current_bytes, _ = _apply_step_to_bytes(
                source_bytes=current_bytes, step=step, definitions=ctx.definitions
            )
            current_path = workdir / f"chained-{index:02d}.xlsx"
            current_path.write_bytes(current_bytes)
            intermediates.append(current_path)
    finally:
        # 先释放作用域内的 zip 句柄再删（Windows 上顺序反了就删不掉 —— 与生产同一纪律）。
        for path in intermediates:
            release_scoped_workbooks(path)
            path.unlink(missing_ok=True)
    return steps


# ═══════════════════════════════════════════════════════════════════════════
# D1 同格写入：全量、确定性的坐标交集
# ═══════════════════════════════════════════════════════════════════════════


def _collisions(steps: Sequence[Any]) -> dict[str, Any]:
    """逐对求 `(sheet_part, coord)` 交集，报**完整**碰撞集合。

    与单趟路径那个 decline 检查的差别（也是本函数存在的理由）：那个检查按
    `set(plan.coords)` 遍历、命中第一处就抛 ⇒ 报的列号不确定、剩下的碰撞看不见。这里排序、
    穷举、并带上「各方用哪个 projection 字段写它」——后者决定碰撞是否**值敏感**：

    * 两边 `field_key` 不同 ⇒ 同一格由两个**不同**字段驱动 ⇒ 值可以不同 ⇒ 谁最后写决定结果；
    * 两边 `field_key` 相同 ⇒ 恒同值 ⇒ 写入顺序不影响产物字节（但仍是契约层的重复归属）。
    """
    # part → coord → table_key → 该 binding 在这一格的写入签名
    index: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for step in steps:
        part = str(step.plan.sheet_part)
        table_key = str(step.binding.table_key)
        for write in step.plan.writes:
            index.setdefault(part, {}).setdefault(write.coord, {})[table_key] = (
                _write_signature(write)
            )

    cells: list[dict[str, Any]] = []
    pair_counter: dict[tuple[str, str], list[str]] = {}
    for part in sorted(index):
        for coord in sorted(index[part], key=_coord_sort_key):
            writers = index[part][coord]
            if len(writers) < 2:
                continue
            keys = sorted(writers)
            field_keys = {writers[k]["field_key"] for k in keys}
            payloads = [
                tuple(sorted(writers[k].items())) for k in keys
            ]
            cells.append(
                {
                    "cell": f"{part}!{coord}",
                    "part": part,
                    "coord": coord,
                    "row": _coord_sort_key(coord)[0],
                    "column": _coord_sort_key(coord)[1],
                    "writers": keys,
                    "per_writer": {k: writers[k] for k in keys},
                    # 🔴 值敏感性：不同 field_key ⇒ 两个字段各自的值可以不同 ⇒ 顺序决定结果。
                    "value_sensitive": len(field_keys) > 1,
                    # 🔴 更强的一条：各方写入的**整份 payload**（kind/value/mode/formula_text）
                    #    完全相同 ⇒ 后写覆盖前写是恒等操作 ⇒ 顺序不影响产物。
                    "payload_identical": len(set(payloads)) == 1,
                    "distinct_field_keys": sorted(field_keys),
                }
            )
            for left, right in combinations(keys, 2):
                pair_counter.setdefault((left, right), []).append(f"{part}!{coord}")

    return {
        "colliding_cell_count": len(cells),
        "value_sensitive_cell_count": sum(1 for c in cells if c["value_sensitive"]),
        "payload_identical_cell_count": sum(1 for c in cells if c["payload_identical"]),
        "colliding_cells": cells,
        "colliding_pairs": [
            {
                "bindings": [left, right],
                "cell_count": len(sorted(coords)),
                "cells": sorted(coords, key=lambda c: _coord_sort_key(c.split("!", 1)[1])),
            }
            for (left, right), coords in sorted(pair_counter.items())
        ],
        "method": (
            "逐对求 (sheet_part, coord) 交集后排序；不是 set 抽样"
        ),
    }


def _coord_sort_key(coord: str) -> tuple[int, str, str]:
    """`C38` → `(38, 'C', 'C38')`：先行后列，让同一行的碰撞在报告里挨着。

    🔴 委托给生产实现 `excel_materialize.coord_sort_key`：任务 3 之后，单趟路径的 decline
    原因也按这个键排碰撞清单。两边各写一份排序口径 ⇒ 同一批碰撞在本审计证据里与生产日志里
    顺序可能不同，对不上账。这里只是**共用排序**，D1 的求交仍然不复用那条 decline 检查
    （理由见模块 docstring）。
    """
    from app.services.workpaper_sync.excel_materialize import coord_sort_key

    return coord_sort_key(coord)


# ═══════════════════════════════════════════════════════════════════════════
# D3 公式落格 / D5 命名区域：写入面的归属核对
# ═══════════════════════════════════════════════════════════════════════════


def _write_footprint(steps: Sequence[Any], *, substrate_bytes: bytes) -> dict[str, Any]:
    """一趟里**真正被改动的 zip 部件**，以及公式格的写法统计。

    `apply_plan_zip_with_report` 在 `plan.row_shift is None` 时只 patch `plan.sheet_part`
    一个部件（位移、Table ref 增长、workbook.xml 传播、`_GT_SYNC` 重冻结四段全部挂在
    `row_shift is not None` 分支下）。因此「全部 binding 都无位移」这一事实直接推出：
    workbook.xml 的 definedName 与 `_GT_SYNC` 的 runtime binding 在整趟里**逐字节不变**
    ⇒ D5 无依赖。这条不是读注释得来的，是下面 `row_shift_bindings` 为空的实测推论。
    """
    import io

    from app.services.workpaper_sync.excel_materialize import _gt_sync_sheet_part

    with zipfile.ZipFile(io.BytesIO(substrate_bytes)) as zf:
        entries = {name: zf.read(name) for name in zf.namelist()}
    gt_sync_part = _gt_sync_sheet_part(entries, substrate_bytes)

    touched_parts = sorted({str(step.plan.sheet_part) for step in steps})
    kind_counts: dict[str, int] = {}
    for step in steps:
        for write in step.plan.writes:
            kind_counts[write.kind.value] = kind_counts.get(write.kind.value, 0) + 1
    return {
        "touched_parts": touched_parts,
        "touched_part_count": len(touched_parts),
        "gt_sync_part": gt_sync_part,
        "gt_sync_written": gt_sync_part in touched_parts,
        "workbook_xml_written": "xl/workbook.xml" in touched_parts,
        "row_shift_bindings": [
            str(step.binding.table_key)
            for step in steps
            if step.plan.row_shift is not None
        ],
        "workbook_row_change_bindings": [
            str(step.binding.table_key)
            for step in steps
            if step.plan.workbook_row_change is not None
        ],
        "write_kind_counts": dict(sorted(kind_counts.items())),
        #: `cached_value_only` = 只改 `<v>`、`<f>` 逐字保留 ⇒ 写入**不会**让别人读到新公式。
        "cached_value_only_count": kind_counts.get("cached_value_only", 0),
        "preserved_formula_total": sum(
            len(step.plan.preserved_formulas) for step in steps
        ),
        "formula_text_rewrites": sorted(
            f"{step.plan.sheet_part}!{write.coord}"
            for step in steps
            for write in step.plan.writes
            if write.formula_text
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# D4 跨 sheet 引用：受管 sheet 的公式指向别的 binding 写的格？
# ═══════════════════════════════════════════════════════════════════════════

_FORMULA = re.compile(r"<f[^>]*>(.*?)</f>", re.S)
#: `'某 sheet'!$C$38` / `Sheet14!C38`（含跨 sheet 区间的起点）。
_XSHEET_REF = re.compile(r"(?:'([^']+)'|([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff.\- ]*))!(\$?[A-Z]{1,3}\$?\d+)")


def _cross_sheet_refs(steps: Sequence[Any], *, substrate_bytes: bytes) -> dict[str, Any]:
    """扫**整本工作簿**的 `<f>` 文本，找指向某个 binding 写入面的跨 sheet 引用。

    刻意扫全部 46 张 sheet 而不是只扫 33 张受管 sheet：把源限定在受管 sheet 会漏掉
    「未受管 sheet 的公式引用受管格」这一半，而那一半同样是「读别人写的结果」。

    找到也**不**等于写入顺序依赖：materialize 对受管公式格走 `cached_value_only`（缓存值
    来自 projection，不重算），所以 A 写完 B 的引用格并不会因此变值 —— 链式与单趟同此。
    但引用的存在必须如实记录：它是「Excel 重算语义上的依赖」，若将来有人让 materialize 去
    **重算**公式，写入顺序就会立刻变成正确性问题。
    """
    import io

    with zipfile.ZipFile(io.BytesIO(substrate_bytes)) as zf:
        entries = {name: zf.read(name) for name in zf.namelist()}

    # part → {coord} 写入面；sheet_name → part
    writes_by_part: dict[str, set[str]] = {}
    part_by_sheet_name: dict[str, str] = {}
    for step in steps:
        part = str(step.plan.sheet_part)
        writes_by_part.setdefault(part, set()).update(step.plan.coords)
        part_by_sheet_name[str(step.plan.sheet_name)] = part

    all_sheet_parts = sorted(
        name for name in entries if name.startswith("xl/worksheets/") and name.endswith(".xml")
    )
    hits: list[dict[str, Any]] = []
    scanned_formulas = 0
    for part in all_sheet_parts:
        xml = entries[part].decode("utf-8")
        for formula in _FORMULA.findall(xml):
            scanned_formulas += 1
            for quoted, bare, ref in _XSHEET_REF.findall(formula):
                sheet = quoted or bare
                target_part = part_by_sheet_name.get(sheet)
                if target_part is None or target_part == part:
                    continue
                normalized = ref.replace("$", "")
                if normalized in writes_by_part.get(target_part, set()):
                    hits.append(
                        {
                            "from_part": part,
                            "from_part_is_managed": part in writes_by_part,
                            "to_sheet": sheet,
                            "to_part": target_part,
                            "to_coord": normalized,
                            "formula": formula[:160],
                        }
                    )

    unique = sorted({(h["from_part"], h["to_part"], h["to_coord"]) for h in hits})
    return {
        "scanned_sheet_part_count": len(all_sheet_parts),
        "scanned_formula_count": scanned_formulas,
        "managed_sheet_count": len(writes_by_part),
        "reference_hit_count": len(hits),
        "hits_from_unmanaged_sheets": sum(
            1 for h in hits if not h["from_part_is_managed"]
        ),
        "unique_edges": [
            {"from_part": a, "to_part": b, "to_coord": c} for a, b, c in unique
        ],
        "samples": hits[:20],
        "note": (
            "命中 = 某 sheet 的公式引用了另一 binding 写入面里的格（源扫全部 worksheet，"
            "不限受管）。materialize 对受管公式格只写缓存值（cached_value_only）不重算 ⇒ "
            "这类引用在链式与单趟两条路径上表现相同，不构成写入顺序依赖。"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# D1b 碰撞是否**真的**顺序敏感：拿两个不同值做一次反证
# ═══════════════════════════════════════════════════════════════════════════


def _distinct_pair(value: Any) -> tuple[Any, Any] | None:
    """给一个现值，造两个**同类型且互不相同**的值；造不出来返回 `None`（如实记「造不出」）。"""
    from decimal import Decimal

    if isinstance(value, bool):
        return (True, False)
    if isinstance(value, Decimal):
        return (Decimal("111111"), Decimal("222222"))
    if isinstance(value, int):
        return (111111, 222222)
    if isinstance(value, float):
        return (111111.0, 222222.0)
    if isinstance(value, str):
        return ("GT-PROBE-A", "GT-PROBE-B")
    return None


def _cell_body(xml: str, coord: str) -> str | None:
    from app.services.workpaper_sync.excel_materialize import build_sheet_cell_index

    view = build_sheet_cell_index(xml).view(coord)
    return None if view is None else view.body


def _plan_by_table_key(
    ctx: _Ctx, *, substrate: Path, source_bytes: bytes, table_keys: Sequence[str]
) -> dict[str, Any]:
    return {
        str(key): _plan_step(
            ctx,
            binding=next(b for b in ctx.bindings if str(b.table_key) == str(key)),
            substrate=substrate,
            source_bytes=source_bytes,
        )
        for key in table_keys
    }


def _order_probe(
    ctx: _Ctx, *, substrate: Path, collision: Mapping[str, Any]
) -> dict[str, Any]:
    """碰撞格上「谁最后写」到底改不改结果 —— 两个实验，都在真契约真字节上跑。

    ① **顺序不变性**：按真 projection 把碰撞的两个 binding 的计划以 A→B 与 B→A 各 apply 一遍，
       逐字节比**整个受管 sheet part**（不是只比那一格 —— 只比一格会漏掉「别处也被顺序影响」）。
    ② **共享字段追踪**：把碰撞格背后那个 `stable_field_key` 改成一个**新值**，重算两个 binding
       的计划，看两边在该坐标上是否都写出新值。

    为什么必须有 ②：harness 的 projection 取自 substrate 自身反读 ⇒ 碰撞格当前值恰好都是
    `Decimal('0')`。只有 ① 会让人误以为「顺序无所谓只是因为当前值凑巧相同」。② 证明两个
    binding 读的是**同一个字段**，于是对**任意** projection 值都同写 —— 恒等覆盖，与值无关。
    """
    import io

    from app.services.workpaper_sync.excel_materialize import _apply_step_to_bytes

    part = str(collision["part"])
    coord = str(collision["coord"])
    per_writer = dict(collision["per_writer"])
    writers = [str(key) for key in collision["writers"]]
    if len(writers) != 2:
        return {"performed": False, "reason": f"碰撞方不是两个（{writers}）"}

    source_bytes = substrate.read_bytes()
    real = _plan_by_table_key(
        ctx, substrate=substrate, source_bytes=source_bytes, table_keys=writers
    )

    def _apply(order: Sequence[str]) -> tuple[bytes, str | None]:
        staged = source_bytes
        for key in order:
            staged, _ = _apply_step_to_bytes(
                source_bytes=staged, step=real[key], definitions=ctx.definitions
            )
        with zipfile.ZipFile(io.BytesIO(staged)) as zf:
            xml = zf.read(part).decode("utf-8")
        return xml.encode("utf-8"), _cell_body(xml, coord)

    forward, backward = writers, list(reversed(writers))
    xml_forward, body_forward = _apply(forward)
    xml_backward, body_backward = _apply(backward)

    # ② 共享字段追踪
    field_keys = sorted({str(per_writer[key]["field_key"]) for key in writers})
    tracking: dict[str, Any] = {"performed": False}
    if len(field_keys) == 1 and field_keys[0]:
        field_key = field_keys[0]
        current = ctx.projection.values.get(field_key)
        pair = None if current is None else _distinct_pair(current.value)
        if current is None:
            tracking["reason"] = f"projection 里没有字段 {field_key}"
        elif pair is None:
            tracking["reason"] = (
                f"字段 {field_key} 现值类型 {type(current.value).__name__} 造不出同类型的新值"
            )
        else:
            probe_value = pair[0] if pair[0] != current.value else pair[1]
            values = dict(ctx.projection.values)
            values[field_key] = dataclasses.replace(current, value=probe_value)
            probe_ctx = dataclasses.replace(
                ctx, projection=dataclasses.replace(ctx.projection, values=values)
            )
            probed = _plan_by_table_key(
                probe_ctx,
                substrate=substrate,
                source_bytes=source_bytes,
                table_keys=writers,
            )
            def _written_at(plans: Mapping[str, Any]) -> dict[str, str]:
                return {
                    key: repr(
                        next(
                            (w.value for w in plans[key].plan.writes if w.coord == coord),
                            None,
                        )
                    )
                    for key in writers
                }

            baseline_written = _written_at(real)
            written = _written_at(probed)
            tracking = {
                "performed": True,
                "field_key": field_key,
                "projection_value_before": repr(current.value),
                "projection_value_probe": repr(probe_value),
                "planned_write_value_baseline": baseline_written,
                "planned_write_value_by_binding": written,
                # 判据不比 `repr(probe_value)`：计划期会按字段类型归一化（int 0 → Decimal('0')），
                # 拿 projection 侧的 repr 去比写入侧的 repr 必然对不上。真正要的两条是：
                # ① 两个 binding 写出**同一个**值；② 这个值随共享字段一起**变了**。
                "both_bindings_agree": len(set(written.values())) == 1,
                "changed_with_shared_field": written != baseline_written,
                "both_track_shared_field": (
                    len(set(written.values())) == 1 and written != baseline_written
                ),
            }
    else:
        tracking["reason"] = f"两方 field_key 不唯一（{field_keys}）⇒ 不是共享字段场景"

    return {
        "performed": True,
        "cell": f"{part}!{coord}",
        "part": part,
        "order_forward": forward,
        "order_backward": backward,
        "cell_body_forward": body_forward,
        "cell_body_backward": body_backward,
        "sheet_part_bytes_equal_across_orders": xml_forward == xml_backward,
        "order_matters": xml_forward != xml_backward,
        "shared_field_tracking": tracking,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════


def audit(workdir: Path) -> dict[str, Any]:
    """铺真 D4 world → 两组计划 → 五类依赖判决 → 顺序敏感性反证。"""
    from app.services.workpaper_sync.excel_extract import workbook_read_scope
    from tests.workpaper_sync.d4_materialize_harness import ENTRY_ID, build_world

    world = build_world(workdir)
    adapter = world.adapter
    ctx = _Ctx(
        definitions=adapter.definitions,
        projection=world.projection,
        bindings=tuple(adapter._all_bindings()),
        primary_table_key=str(adapter.binding.table_key),
        role=adapter.substrate_role,
        kind=adapter.substrate_kind,
        state=adapter.substrate_state,
        capability=adapter.capability,
        limits=adapter._limits,
    )
    substrate_bytes = world.base.read_bytes()

    # 作用域包住整趟：与生产 `adapter.materialize` 同相，免得中间产物句柄残留（Windows）。
    with workbook_read_scope():
        original = _plan_all_on_original(ctx, substrate=world.base)
        chained = _plan_all_chained(ctx, substrate=world.base, workdir=workdir)

        sig_original = [_plan_signature(step) for step in original]
        sig_chained = [_plan_signature(step) for step in chained]
        drifted = [
            {
                "index": index,
                "table_key": str(ctx.bindings[index].table_key),
                "differing_keys": _diff_keys(sig_original[index], sig_chained[index]),
            }
            for index in range(len(ctx.bindings))
            if sig_original[index] != sig_chained[index]
        ]

        collisions = _collisions(original)
        footprint = _write_footprint(original, substrate_bytes=substrate_bytes)
        cross_sheet = _cross_sheet_refs(original, substrate_bytes=substrate_bytes)

        cells = collisions["colliding_cells"]
        # 优先探值敏感的那格（顺序真会改结果的形态）；没有就探第一格证明顺序不变。
        target = next((c for c in cells if c["value_sensitive"]), cells[0] if cells else None)
        probe = (
            _order_probe(ctx, substrate=world.base, collision=target)
            if target is not None
            else {"performed": False, "reason": "无跨 binding 碰撞格 ⇒ 无需探顺序"}
        )

    bindings_report = [
        {
            "index": index,
            "table_key": str(step.binding.table_key),
            "table_name": str(step.binding.table_name),
            "sheet_part": str(step.plan.sheet_part),
            "sheet_name": str(step.plan.sheet_name),
            "write_count": len(step.plan.writes),
            "field_write_count": len(step.plan.field_writes),
            "identity_write_count": len(step.plan.identity_writes),
            "preserved_formula_count": len(step.plan.preserved_formulas),
            "footer_marker_row": step.plan.footer_marker_row,
            "row_shift": None if step.plan.row_shift is None else step.plan.row_shift.as_dict(),
            "strategy": step.strategy.strategy.value,
        }
        for index, step in enumerate(original)
    ]
    part_multiplicity: dict[str, list[str]] = {}
    for entry in bindings_report:
        part_multiplicity.setdefault(entry["sheet_part"], []).append(entry["table_key"])

    return {
        "label": None,
        "captured_at": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "spec": "oo-single-pass-materialize-and-room-leave",
        "requirements": ["1.2"],
        "task": "2 · binding 顺序依赖调查",
        "scope": {
            "entry_id": ENTRY_ID,
            "binding_count": len(ctx.bindings),
            "primary_table_key": ctx.primary_table_key,
            "substrate_bytes": len(substrate_bytes),
            "projection_field_count": len(ctx.projection.values),
            "projection_source": "substrate 自身反读（覆盖每个 binding 的受管区）",
        },
        "bindings": bindings_report,
        "sheet_part_multiplicity": {
            part: keys for part, keys in sorted(part_multiplicity.items()) if len(keys) > 1
        },
        "classes": {
            "D1_same_cell_write": collisions,
            "D1b_order_probe": probe,
            "D2_plan_position_independence": {
                "compared_bindings": len(ctx.bindings),
                "drifted_bindings": drifted,
                "independent": not drifted,
                "method": (
                    "同一 binding 的计划分别算在「原始 substrate 字节」与「前 k-1 个 binding "
                    "写入后的字节」上，逐字段比签名（含 writes/preserved_formulas/region/"
                    "runtime_binding/row_shift/workbook_row_change/strategy）"
                ),
            },
            "D3_formula_into_cell": footprint,
            "D4_cross_sheet_reference": cross_sheet,
            "D5_named_range": {
                "workbook_xml_written": footprint["workbook_xml_written"],
                "gt_sync_written": footprint["gt_sync_written"],
                "gt_sync_part": footprint["gt_sync_part"],
                "row_shift_bindings": footprint["row_shift_bindings"],
                "note": (
                    "definedName（workbook.xml）与 _GT_SYNC runtime binding 只在 "
                    "row_shift is not None 时被改写（_apply_workbook_propagation / "
                    "_refresh_gt_sync_runtime_binding 都挂在该分支下）。row_shift_bindings 为空 "
                    "⇒ 整趟里这两处逐字节不变 ⇒ 计划期读到的命名区域不可能是别人写的结果。"
                ),
            },
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "openpyxl": __import__("openpyxl").__version__,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(
        prefix="d4-binding-deps-", ignore_cleanup_errors=True
    ) as raw:
        evidence = audit(Path(raw))
    evidence["label"] = args.label

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{args.label}.json"
    target.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    classes = evidence["classes"]
    d1 = classes["D1_same_cell_write"]
    d2 = classes["D2_plan_position_independence"]
    probe = classes["D1b_order_probe"]
    print(f"[evidence] {target}")
    print(f"  binding 数 = {evidence['scope']['binding_count']}")
    print(
        f"  D1 跨 binding 碰撞格 = {d1['colliding_cell_count']}"
        f"（值敏感 {d1['value_sensitive_cell_count']}"
        f" / payload 全同 {d1['payload_identical_cell_count']}）"
    )
    for cell in d1["colliding_cells"]:
        print(
            f"    {cell['cell']}  ←  {' / '.join(cell['writers'])}"
            f"  字段 {cell['distinct_field_keys']}"
            f"  值敏感={cell['value_sensitive']}"
            f"  payload全同={cell['payload_identical']}"
        )
    for pair in d1["colliding_pairs"]:
        print(f"    碰撞对 {pair['bindings']}  共 {pair['cell_count']} 格")
    print(
        f"  D2 计划位置无关 = {d2['independent']}"
        f"（漂移 binding {len(d2['drifted_bindings'])} 个）"
    )
    if d2["drifted_bindings"]:
        for item in d2["drifted_bindings"]:
            print(f"    漂移 {item['table_key']}：{item['differing_keys']}")
    print(
        f"  D3 写入部件 = {classes['D3_formula_into_cell']['touched_part_count']}"
        f"，公式文本改写 {len(classes['D3_formula_into_cell']['formula_text_rewrites'])} 处"
        f"，插行 binding {classes['D3_formula_into_cell']['row_shift_bindings']}"
    )
    d4 = classes["D4_cross_sheet_reference"]
    print(
        f"  D4 跨 sheet 引用命中 = {d4['reference_hit_count']}"
        f"（扫了 {d4['scanned_sheet_part_count']} 张 sheet / "
        f"{d4['scanned_formula_count']} 条公式；"
        f"其中来自未受管 sheet {d4['hits_from_unmanaged_sheets']}）"
    )
    print(
        f"  D5 workbook.xml 被写={classes['D5_named_range']['workbook_xml_written']}"
        f"  _GT_SYNC 被写={classes['D5_named_range']['gt_sync_written']}"
    )
    if probe.get("performed"):
        print(
            f"  D1b 顺序探针：{probe['cell']}  顺序影响结果={probe['order_matters']}"
            f"  两序 sheet part 字节相等={probe['sheet_part_bytes_equal_across_orders']}"
        )
        print(f"       格内容（A→B）= {probe['cell_body_forward']}")
        print(f"       格内容（B→A）= {probe['cell_body_backward']}")
        tracking = probe.get("shared_field_tracking", {})
        if tracking.get("performed"):
            print(
                f"       共享字段追踪 {tracking['field_key']}："
                f"{tracking['projection_value_before']} → "
                f"{tracking['projection_value_probe']}；"
                f"两 binding 同写={tracking['both_bindings_agree']}"
                f"  随字段变={tracking['changed_with_shared_field']}"
                f"  {tracking['planned_write_value_by_binding']}"
            )
        else:
            print(f"       共享字段追踪未做：{tracking.get('reason')}")
    else:
        print(f"  D1b 顺序探针未做：{probe.get('reason')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
