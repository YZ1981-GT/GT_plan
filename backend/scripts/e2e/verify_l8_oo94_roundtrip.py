# -*- coding: utf-8 -*-
"""L8 财务费用（受管 明细表L8-2）真 OnlyOffice 引擎往返验证（HTML → OO → HTML）。

spec: l8-true-bidirectional-2026-10-01 · 第6步（复用 L1/L7 的 Task 10 / LR-P24 同一链路）

链路与 `verify_l7_oo94_roundtrip.py` 相同骨架，但 L8 走**方案 D1 混合身份**，有三件补课需专门断言：
生产 attach（断言 ids==('l8.financial_expenses',)）→ 真 representation substrate → HTML 载荷
（🔴 方案 D1：**10 个输入骨架行用模板身份 GTROW-L82-NNNN** + 1 个用户新增行自铸 l82det-*；
  **3 个派生行 R11/R13/R20 不进 store**——模板计算只读行；稳定 **key**，_row 跳过 formula/auto_source 列
  N/Q/R/W、置 itemName + editable 列含 monthly 数组 + O/P/S/T/U/V）
→ materialize → docker `audit-onlyoffice` 的 `ConvertService.ashx` xlsx→xlsx 重存 → extract →
G1 等值门 → merge 回 store 逐字段比（**key** 稳定、GTROW 骨架行命中已存在槽位回填不新建、
用户 l82det 行走建新、无幽灵行、行命中数==输入数）→
受管行 **N/Q/W 三列**公式往返后仍是公式（🔴 **不含 R 列** —— R=auto_source、被 neutralize 摘成纯值，
对 R 断言会误判失败）→ 不写库（前后 L8-% 行数不变）。

🔴 补课专项断言（L8 特有，L7 脚本没有）：
  ①28 裸 IF 中性化不破坏 materialize：materialize 不抛、受管区几何不变
    （R9~R21 行命中数==输入数，footer R22 / 静态行 R23 未被位移）。
  ②派生行 R11/R13/R20 的 B 列跨行预置公式幸存：OO 重存后 ws['B11'] 仍以 `=` 开头（=B9-B10）。
    若此断言红 → 补课① 障碍坐实信号，停下报 warning。

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

ENTRY_ID = "xlsx/gt-l8-financial-expenses"
#: 公式幸存只断言 N/Q/W（R 被中性化摘成纯值）。
SURVIVING_FORMULA_COLS = ("N", "Q", "W")
#: 跨行派生行的主输入格（B 列），OO 重存后应仍是 `=` 公式（方案 D1：派生行不进 store ⇒ 幸存）。
DERIVED_ROW_PROBE = {"B11": "=B9-B10", "B13": "=B11-B12", "B20": "=B17-B18-B19"}
#: 派生行骨架身份（下标 2/4/11 = R11/R13/R20），不进 store 载荷。
_DERIVED_IDX = (2, 4, 11)


def _gtrow(idx: int) -> str:
    """第 idx 条骨架行（0 起）的模板身份 GTROW-L82-NNNN（与前端 l82TemplateRowId 同口径）。"""
    return f"GTROW-L82-{9 + idx:04d}"


def _row(rid: str, name: str, base: dict[str, Any]) -> dict[str, Any]:
    """构造一行 L8DetailRow。🔴 身份字段是 `key`（非 rowId）；monthly 是长度 12 数组。"""
    from app.services.workpaper_sync.phase5_l8_sheets import MANAGED_FIELD_SPECS_7

    row: dict[str, Any] = {"key": rid, "monthly": [0] * 12}
    for _key, _col, mode, vtype, jkey, *_ in MANAGED_FIELD_SPECS_7:
        if mode in ("formula", "auto_source"):
            continue
        if jkey.startswith("monthly/"):
            idx = int(jkey.split("/", 1)[1])
            row["monthly"][idx] = base.get(jkey, 0)
            continue
        row[jkey] = base.get(jkey, 0 if vtype in ("amount", "rate", "integer") else "")
    row["itemName"] = name
    return row


def _build_rows() -> list[dict[str, Any]]:
    """方案 D1 的真实 store 载荷：10 个输入骨架行（GTROW 身份，部分填数据）+ 1 个用户新增行（l82det-*）。
    🔴 3 个派生行（idx 2/4/11）**不进 store**（模板计算只读行）—— 这正是让跨行公式幸存的机制。"""
    from app.services.workpaper_sync.phase5_l8_sheets import MANAGED_SHEET  # noqa: F401

    # 13 行骨架科目名（与前端 L82_SKELETON_ITEMS 同序）
    names = [
        "利息费用总额", "减：利息资本化", "利息费用", "减：利息收入", "利息净支出",
        "未确认融资费用", "减：未实现融资收益", "承兑汇票贴息", "汇兑损失",
        "减：汇兑收益", "减：汇兑损益资本化", "汇兑净损失", "手续费及其他",
    ]
    # 给几个输入行填真实月度/调整数据
    data: dict[int, dict[str, Any]] = {
        0: {"monthly/0": 12000, "monthly/1": 12000, "monthly/5": 15000, "monthly/11": 18000,
            "aje": 0, "rje": 2000, "crossRef": "短期借款利息/L1", "priorUnadjusted": 60000},
        1: {"monthly/0": 3000, "crossRef": "资本化利息"},
        12: {"monthly/2": 800, "monthly/7": 1200, "monthly/10": 600,
             "aje": 100, "crossRef": "手续费", "priorUnadjusted": 5000},
    }
    rows: list[dict[str, Any]] = []
    for i, name in enumerate(names):
        if i in _DERIVED_IDX:
            continue  # 🔴 派生行不进 store
        rows.append(_row(_gtrow(i), name, data.get(i, {})))
    # 1 个用户新增行（自铸 l82det-* 身份），验证动态行走建新 target
    rows.append(_row("l82det-00000000-0000-4000-8000-0000000000u1", "保函手续费（用户新增）",
                     {"monthly/3": 450, "crossRef": "保函费"}))
    return rows


ROWS: list[dict[str, Any]] = _build_rows()


async def run() -> int:
    from app.core.database import async_session
    from app.services.workpaper_sync import phase5_l8_financial_expenses as L8
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
            return fail("0", "entry_state 无 L8 行 —— 先完成首版发布")
        wp_id, project_id = target.wp_id, target.project_id
        before_rows = (await session.execute(sa.text(
            "SELECT count(*) FROM checklist_responses WHERE item_id LIKE 'L8-%'"))).scalar_one()
        print(f"[0] wp={str(wp_id)[:8]} project={str(project_id)[:8]} L8 载荷快照={before_rows} 行")

        registry = WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        ids = await L8.attach_adapters(registry, session=session)
        if ids != (L8.ADAPTER_ID,):
            return fail("①", f"attach 返回 {ids!r}（manifest capability 或 representation 未就位）")
        registration = registry.resolve_for_entry(ENTRY_ID)
        contract = registration.contract
        print(f"[①] attach={ids}")

        resolver = CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND))
        resolution = await resolver.resolve(
            intent=ResolutionIntent.extract, project_id=project_id, wp_id=wp_id, entry_id=ENTRY_ID)
        substrate = resolution.artifact_path
        print(f"[②] generation={resolution.representation_generation} substrate={substrate.name}")

        store_projection = L8.build_store_projection(json.dumps(ROWS, ensure_ascii=False), contract=contract)
        projection, _ = await _overlay_with_published_substrate(
            resolution=resolver, project_id=project_id, wp_id=wp_id, entry_id=ENTRY_ID,
            registration=registration, store_projection=store_projection)
        n_rows = sum(len(v) for v in projection.row_keys.values())
        print(f"[③] projection values={len(projection.values)} rows={n_rows}")
        if n_rows != len(ROWS):
            return fail("③", f"projection 行数 {n_rows} ≠ 输入 {len(ROWS)}")

        with tempfile.TemporaryDirectory() as tmp:
            mat, oo = Path(tmp) / "l8-materialized.xlsx", Path(tmp) / "l8-oo-resaved.xlsx"
            try:
                registration.adapter.materialize(substrate=substrate, projection=projection, output=mat,
                                                 contract=contract)
            except Exception as exc:  # noqa: BLE001
                # 🔴 补课①/③ 障碍坐实信号：materialize 对「28 裸 IF 中性化」或「B~M editable 夹预置公式」失败
                return fail("④", f"materialize 失败（补课①/③ 障碍坐实）{type(exc).__name__}: {exc}")
            print(f"[④] materialize size={mat.stat().st_size}（28 裸 IF 中性化 + B~M editable 夹派生公式未抛错）")
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

            merged, *_ = L8.merge_projection_into_store_rows(projection=extracted, base_rows=ROWS)
            by_id = {r["key"]: r for r in merged}
            diffs: list[str] = []
            for src in ROWS:
                got = by_id.get(src["key"])
                if got is None:
                    diffs.append(f"key {src['key'][-4:]} 丢失")
                    continue
                for k, v in src.items():
                    gv = got.get(k)
                    if k == "monthly":
                        # 逐月比
                        for mi, mv in enumerate(v):
                            gmv = (gv or [0] * 12)[mi] if isinstance(gv, list) else None
                            same = (gmv not in (None, "")) and float(gmv) == float(mv) if (isinstance(mv, (int, float)) and mv != 0) else True
                            if isinstance(mv, (int, float)) and mv != 0 and not same:
                                diffs.append(f"{src['key'][-4:]}.monthly[{mi}]: {mv!r} → {gmv!r}")
                        continue
                    if isinstance(v, (int, float)) and gv not in (None, ""):
                        same = float(gv) == float(v)
                    else:
                        same = str(gv if gv is not None else "") == str(v)
                    if not same:
                        diffs.append(f"{src['key'][-4:]}.{k}: {v!r} → {gv!r}")
            if diffs or len(merged) != len(ROWS):
                return fail("⑦", f"merged={len(merged)} 行，不等 {len(diffs)} 处: {diffs[:8]}")
            print(f"[⑦] L8-2-full-data 往返逐字段相等（{len(ROWS)} 行，key 稳定，无幽灵行）")

            import openpyxl

            ws = openpyxl.load_workbook(oo, data_only=False)[L8.MANAGED_SHEET]
            names = {r["itemName"] for r in ROWS}
            hit = [r for r in range(1, ws.max_row + 1) if ws[f"A{r}"].value in names]
            # ⑧ N/Q/W 三列公式幸存（不含 R —— auto_source、被中性化摘成纯值）
            bad = {f"{c}{r}": ws[f"{c}{r}"].value for r in hit for c in SURVIVING_FORMULA_COLS
                   if not (isinstance(ws[f"{c}{r}"].value, str) and str(ws[f"{c}{r}"].value).startswith("="))}
            # 🔴 方案 D1：10 输入骨架行 + 1 用户新增行 = 11 行应全部在受管区找到（名字命中）
            if len(hit) < len(ROWS) or bad:
                return fail("⑧", f"受管行={hit}（期望≥{len(ROWS)}）非公式格={bad}")
            print(f"[⑧] OO 重存后受管行 {len(hit)} 行的 N/Q/W 三列 {len(hit) * len(SURVIVING_FORMULA_COLS)} 格全部仍是公式（R 列 auto_source 已中性化为纯值，不断言）")

            # ⑧a 补课① 专项：派生行 R11/R13/R20 的 B 列跨行预置公式幸存
            derived_bad = {coord: ws[coord].value for coord, expect in DERIVED_ROW_PROBE.items()
                           if not (isinstance(ws[coord].value, str) and str(ws[coord].value).startswith("="))}
            if derived_bad:
                return fail("⑧a", f"派生行跨行预置公式被破坏（补课① 障碍坐实）={derived_bad}")
            print(f"[⑧a] 派生行 R11/R13/R20 的 B 列跨行预置公式幸存：{ {k: ws[k].value for k in DERIVED_ROW_PROBE} }")

            # ⑧b 补课③ 专项：28 裸 IF 中性化不破坏 footer/静态行结构。
            # 🔴 用户新增行会合法下移 footer（动态插行）⇒ 不锁死 A22，改按 marker 定位：
            #   「合计」唯一存在、「各月比例」紧随其下一行（相对结构不变即可）。
            a_col = {r: ws[f"A{r}"].value for r in range(1, ws.max_row + 1)}
            total_rows = [r for r, v in a_col.items() if v == "合计"]
            ratio_rows = [r for r, v in a_col.items() if v == "各月比例"]
            if len(total_rows) != 1:
                return fail("⑧b", f"footer「合计」应恰 1 行，实得行号 {total_rows}")
            if len(ratio_rows) != 1 or ratio_rows[0] != total_rows[0] + 1:
                return fail("⑧b", f"静态行「各月比例」应紧随「合计」下一行，合计={total_rows} 各月比例={ratio_rows}")
            print(f"[⑧b] 28 裸 IF 中性化后 footer/静态行结构不变（「合计」R{total_rows[0]}、「各月比例」R{ratio_rows[0]}，用户新增行合法下移 footer）")

        after_rows = (await session.execute(sa.text(
            "SELECT count(*) FROM checklist_responses WHERE item_id LIKE 'L8-%'"))).scalar_one()
        if after_rows != before_rows:
            return fail("⑨", f"L8 载荷行数变化 {before_rows} → {after_rows}")
        print(f"[⑨] L8 载荷 {after_rows} 行不变（本脚本不写库）")

    print("✅ L8 真 OO 引擎往返全绿（HTML→OO→HTML）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
