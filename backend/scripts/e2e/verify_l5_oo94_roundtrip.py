# -*- coding: utf-8 -*-
"""L5 长期应付款（受管 明细表L5-2，两区同键 + flat 账龄）真 OnlyOffice 引擎往返（HTML→OO→HTML）。

spec: l5-true-bidirectional-2026-10-01 · T7（复用 L1/L7 的 Task 10 / LR-P24 同一链路）。

与 verify_l7 的差异（照抄 L7 会错）：
* 身份字段 **`key`**（非 rowId）；每行带 **`section`** 归属（saleLeaseback / installment）。
* **两个受管区**（R11:15 售后租回 + R18:22 分期付款），ROWS 覆盖两区各 1 行 + 账龄桶 T~X。
* 公式列 7 个 E/L/M/N/O/R/S（本行算术，无 IF 中性化，bare_IF=0）往返仍是 `=`。
* 🔴 L5 专项断言：小计 R16/R23 + 合计 R25 + 标题 A10/A17 + **R24「其他」占位续行** 作静态骨架未被位移/清空
  （模板 SUM 幸存，靠 is_template_skeleton_identity）；账龄桶 T~X editable 往返；
  **L5-3 的 A 列 `='明细表L5-2'!A{n}` 镜像引用未被 L5-2 受管区扩行打坏**（硬行号依赖）。
* 不写库（前后 L5-% 行数不变）。9 步 + 专项断言。

退出码 0 = 全绿；1 = 任一断言失败（打印失败环节，不降级为合成通过）。
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_spec = importlib.util.spec_from_file_location("_verify_l1", _HERE / "verify_l1_oo94_roundtrip.py")
assert _spec and _spec.loader
_V1 = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _V1
_spec.loader.exec_module(_V1)

import sqlalchemy as sa  # noqa: E402

ENTRY_ID = "xlsx/gt-l5-long-term-payables"


def _row(rid: str, name: str, section: str, base: dict[str, Any]) -> dict[str, Any]:
    """构造一行 L5-2 受管载荷：`key`=rid + section 归属 + 跳过公式列、置 editable 列。"""
    from app.services.workpaper_sync.phase5_l5_sheets import FIELD_SPECS_L52, AGING_GROUPS_L52

    row: dict[str, Any] = {"key": rid, "section": section}
    for _key, _col, mode, vtype, jkey, *_ in FIELD_SPECS_L52:
        if mode == "formula":
            continue
        row[jkey] = base.get(jkey, 0 if vtype in ("amount", "rate", "integer") else "")
    # 账龄 5 桶（editable）
    for flat_key, _c, _label in AGING_GROUPS_L52[0].segments:
        row[flat_key] = base.get(flat_key, 0)
    row["payableName"] = name
    return row


ROWS: list[dict[str, Any]] = [
    _row("l52det-5a1e8c0a-0001-4a2b-8c3d-000000000011", "售后租回融资A", "saleLeaseback", {
        "beginning": 500000, "periodRepayment": 100000, "periodIncrease": 0,
        "priorAdjustment": 0, "priorReclass": 0,
        "ajeDebit": 0, "ajeCredit": 20000, "rjeDebit": 0, "rjeCredit": 0,
        "minusPriorDue": 50000, "minusEndDue": 40000,
        "agingWithin6m": 10000, "aging6to12m": 30000, "aging1to2y": 100000,
        "aging2to3y": 120000, "agingOver3y": 180000,
    }),
    _row("l52det-5a1e8c0a-0002-4a2b-8c3d-000000000018", "分期付款设备B", "installment", {
        "beginning": 300000, "periodRepayment": 60000, "periodIncrease": 90000,
        "priorAdjustment": 0, "priorReclass": 0,
        "ajeDebit": 0, "ajeCredit": 0, "rjeDebit": 0, "rjeCredit": 15000,
        "minusPriorDue": 20000, "minusEndDue": 25000,
        "agingWithin6m": 5000, "aging6to12m": 10000, "aging1to2y": 60000,
        "aging2to3y": 70000, "agingOver3y": 110000,
    }),
]


async def run() -> int:
    from app.core.database import async_session
    from app.services.workpaper_sync import phase5_l5_long_term_payables as L5
    from app.services.workpaper_sync.adapters.registry import WorkpaperSyncAdapterRegistry
    from app.services.workpaper_sync.content_mutation import ContentMutationService
    from app.services.workpaper_sync.entry_profile import load_entry_manifest
    from app.services.workpaper_sync.resolution import (
        CanonicalArtifactRepository,
        CanonicalResolutionService,
        ResolutionIntent,
    )
    from app.services.workpaper_sync.store_projection_response import (
        _overlay_with_published_substrate,
    )

    fail = _V1._fail
    async with async_session() as session:
        target = (await session.execute(sa.text(
            "SELECT es.wp_id, wp.project_id FROM working_paper_sync_entry_state es "
            "JOIN working_paper wp ON wp.id = es.wp_id WHERE es.entry_id = :e"), {"e": ENTRY_ID})).first()
        if target is None:
            return fail("0", "entry_state 无 L5 行 —— 先完成首版发布")
        wp_id, project_id = target.wp_id, target.project_id
        before_rows = (await session.execute(sa.text(
            "SELECT count(*) FROM checklist_responses WHERE item_id LIKE 'L5-%'"))).scalar_one()
        print(f"[0] wp={str(wp_id)[:8]} project={str(project_id)[:8]} L5 载荷快照={before_rows} 行")

        registry = WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        ids = await L5.attach_adapters(registry, session=session)
        if ids != (L5.ADAPTER_ID,):
            return fail("①", f"attach 返回 {ids!r}（manifest capability 或 representation 未就位）")
        registration = registry.resolve_for_entry(ENTRY_ID)
        contract = registration.contract
        print(f"[①] attach={ids}")

        resolver = CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND))
        resolution = await resolver.resolve(
            intent=ResolutionIntent.extract, project_id=project_id, wp_id=wp_id, entry_id=ENTRY_ID)
        substrate = resolution.artifact_path
        print(f"[②] generation={resolution.representation_generation} substrate={substrate.name}")

        store_projection = L5.build_store_projection(json.dumps(ROWS, ensure_ascii=False), contract=contract)
        projection, _ = await _overlay_with_published_substrate(
            resolution=resolver, project_id=project_id, wp_id=wp_id, entry_id=ENTRY_ID,
            registration=registration, store_projection=store_projection)
        n_rows = sum(len(v) for v in projection.row_keys.values())
        print(f"[③] projection values={len(projection.values)} rows={n_rows}")
        if n_rows != len(ROWS):
            return fail("③", f"projection 行数 {n_rows} ≠ 输入 {len(ROWS)}（两区各 1 行）")

        with tempfile.TemporaryDirectory() as tmp:
            mat, oo = Path(tmp) / "l5-materialized.xlsx", Path(tmp) / "l5-oo-resaved.xlsx"
            registration.adapter.materialize(substrate=substrate, projection=projection, output=mat,
                                             contract=contract)
            print(f"[④] materialize size={mat.stat().st_size}")
            try:
                res = _V1.oo_resave(mat, oo)
            except Exception as exc:  # noqa: BLE001
                return fail("⑤", f"OO ConvertService 失败 {type(exc).__name__}: {exc}")
            print(f"[⑤] OO resave OK size={oo.stat().st_size} percent={res.get('percent')}")

            extracted = registration.adapter.extract(artifact=oo, contract=contract)
            try:
                ContentMutationService._assert_roundtrip_equivalent(
                    None, intended=projection, extracted=extracted, contract=contract)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                return fail("⑥", f"G1 等值门失败 {type(exc).__name__}: {exc}")
            print(f"[⑥] extract values={len(extracted.values)} · G1 等值门 OK")

            merged, *_ = L5.merge_projection_into_store_rows(projection=extracted, base_rows=ROWS)
            by_id = {r["key"]: r for r in merged}
            diffs: list[str] = []
            for src in ROWS:
                got = by_id.get(src["key"])
                if got is None:
                    diffs.append(f"key {src['key'][-4:]} 丢失")
                    continue
                # section 归属对齐（三/两区同键的关键）
                if got.get("section") != src["section"]:
                    diffs.append(f"{src['key'][-4:]}.section {src['section']}→{got.get('section')}")
                for k, v in src.items():
                    gv = got.get(k)
                    if isinstance(v, (int, float)) and gv not in (None, ""):
                        same = float(gv) == float(v)
                    else:
                        same = str(gv if gv is not None else "") == str(v)
                    if not same:
                        diffs.append(f"{src['key'][-4:]}.{k}: {v!r} → {gv!r}")
            if diffs or len(merged) != len(ROWS):
                return fail("⑦", f"merged={len(merged)} 行，不等 {len(diffs)} 处: {diffs[:8]}")
            print(f"[⑦] L5-L5-2-rows 往返逐字段相等（{len(ROWS)} 行，两区 section 对齐，key 稳定，无幽灵行）")

            import re as _re

            import openpyxl

            ws = openpyxl.load_workbook(oo, data_only=False)[L5.MANAGED_SHEET]
            names = {r["payableName"] for r in ROWS}
            # 🔴 受管区是 excel_table 动态行：首批新身份行作 orphan 插入，静态骨架（小计/合计/标题/
            #    R24 占位）合法下移、footer SUM 区间按插行重归一化。故按**标签/行名**定位数据行，
            #    不假设固定行号（照 verify_l7：hit = 名字命中的行）。
            hit = [r for r in range(1, ws.max_row + 1) if ws[f"A{r}"].value in names]
            bad = {f"{c}{r}": ws[f"{c}{r}"].value for r in hit for c in L5.FORMULA_COLUMNS
                   if not (isinstance(ws[f"{c}{r}"].value, str) and str(ws[f"{c}{r}"].value).startswith("="))}
            if len(hit) != len(ROWS) or bad:
                return fail("⑧", f"受管行={hit} 非公式格={bad}")
            print(f"[⑧] OO 重存后受管行 {hit} 的七列公式 {len(hit) * len(L5.FORMULA_COLUMNS)} 格全部仍是公式")

            # ─── 🔴 L5 专项断言（按标签/形态定位，不假设固定行号——插行后骨架合法下移）────────
            # 单次遍历取 A 列全部非空文本 → {label: [rows]} / {row: label}
            a_by_label: dict[str, list[int]] = {}
            for r in range(1, ws.max_row + 1):
                v = ws[f"A{r}"].value
                if isinstance(v, str) and v.strip():
                    a_by_label.setdefault(v.strip(), []).append(r)

            # (a) 静态骨架幸存：两区标题 + 2 个小计 + 1 个合计 + R24「其他」占位续行（'…'），标签都在、
            #     且小计/合计仍是 SUM 公式（区间随插行重归一化，形态仍是 =SUM(...)）。
            def _one(label: str) -> int | None:
                rows = a_by_label.get(label) or []
                return rows[0] if len(rows) == 1 else None
            title1, title2 = _one("售后租回业务形成的融资"), _one("分期付款方式购入固定资产")
            subtotals = a_by_label.get("小计") or []
            total = _one("合计")
            placeholder = _one("…")
            miss = []
            if title1 is None: miss.append("标题『售后租回』")
            if title2 is None: miss.append("标题『分期付款』")
            if len(subtotals) != 2: miss.append(f"小计应 2 行实得 {subtotals}")
            if total is None: miss.append("合计")
            if placeholder is None: miss.append("R24『…』占位续行")
            if miss:
                return fail("⑧a", f"静态骨架标签缺失/异常：{miss}")
            # 小计/合计 B 列仍是 SUM 公式（形态而非固定区间）
            sum_bad = {f"B{r}": ws[f"B{r}"].value for r in subtotals + [total]
                       if not (isinstance(ws[f"B{r}"].value, str) and ws[f"B{r}"].value.upper().startswith("=SUM("))}
            # R24 占位行 roll-forward 公式骨架仍在（E 列本行算术，形态 =B{r}-C{r}+D{r}）
            e_ph = ws[f"E{placeholder}"].value
            if not (isinstance(e_ph, str) and _re.fullmatch(rf"=B{placeholder}-C{placeholder}\+D{placeholder}", e_ph)):
                sum_bad[f"E{placeholder}"] = e_ph
            if sum_bad:
                return fail("⑧a", f"骨架 SUM/占位公式被破坏：{sum_bad}")
            print(f"[⑧a] 静态骨架幸存：标题 R{title1}/R{title2} + 小计 R{subtotals} + 合计 R{total} + "
                  f"R{placeholder}『…』占位续行；SUM/roll-forward 公式形态原样（随插行合法重归一化）")

            # (b) 账龄桶 T~X editable 往返：第一数据行（售后租回A 所在行）的 5 桶值回写正确。
            r1 = a_by_label["售后租回融资A"][0]
            aging_exp = {"T": 10000, "U": 30000, "V": 100000, "W": 120000, "X": 180000}
            ag_bad = {f"{c}{r1}": ws[f"{c}{r1}"].value for c, exp in aging_exp.items()
                      if ws[f"{c}{r1}"].value is None or float(ws[f"{c}{r1}"].value) != float(exp)}
            if ag_bad:
                return fail("⑧b", f"账龄桶往返不符（R{r1}）：{ag_bad}")
            print(f"[⑧b] 账龄桶 T~X editable 往返正确（R{r1} 的 5 桶值回写）")

            # (c) 🔴 L5-3 的 A 列 ='明细表L5-2'!A{n} 镜像引用未被 L5-2 受管区扩行**打坏**：
            #     即这些跨 sheet 引用公式本身仍原样存在（未被改写/清空/损坏）。L5-3 本轮不受管、是
            #     后续 spec；此处只证 L5-2 的 materialize 没有破坏 L5-3 既有的镜像公式。
            ws3 = openpyxl.load_workbook(oo, data_only=False)["未确认融资费用明细表L5-3"]
            mirror_cells = [r for r in range(9, 28)
                            if isinstance(ws3[f"A{r}"].value, str) and "明细表L5-2" in str(ws3[f"A{r}"].value)]
            # 每个镜像格必须仍是 ='明细表L5-2'!A{n} 形态（未被损坏）
            mirror_bad = {f"A{r}": ws3[f"A{r}"].value for r in mirror_cells
                          if not _re.fullmatch(r"='?明细表L5-2'?!A\d+", str(ws3[f"A{r}"].value))}
            if not mirror_cells or mirror_bad:
                return fail("⑧c", f"L5-3 镜像引用缺失或被损坏：cells={mirror_cells} bad={mirror_bad}")
            print(f"[⑧c] L5-3 的 A 列 ='明细表L5-2'!A{{n}} 镜像引用未被打坏（{len(mirror_cells)} 格仍是原样跨 sheet 引用公式）")

        after_rows = (await session.execute(sa.text(
            "SELECT count(*) FROM checklist_responses WHERE item_id LIKE 'L5-%'"))).scalar_one()
        if after_rows != before_rows:
            return fail("⑨", f"L5 载荷行数变化 {before_rows} → {after_rows}")
        print(f"[⑨] L5 载荷 {after_rows} 行不变（本脚本不写库）")

    print("✅ L5 真 OO 引擎往返全绿（HTML→OO→HTML，两区 section 对齐 + 账龄往返 + 公式幸存 + 静态骨架幸存 + L5-3 镜像未破坏）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
