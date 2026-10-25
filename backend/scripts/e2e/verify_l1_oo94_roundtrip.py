# -*- coding: utf-8 -*-
"""L1 真 OnlyOffice 引擎往返验证（HTML → OO → HTML）。

spec: l-cycle-true-adapter-registration · Task 10 · LR-P24

═══ 链路（每一步都是生产代码，无合成替身）═══

  ① `phase5_l1_short_term_loans.attach_adapters()` 按 manifest + 真库 published
     representation 挂 adapter（走 Task 75 的冻结身份观测器）
  ② `CanonicalResolutionService.resolve(extract)` 取当前 representation 的**真实字节**
  ③ HTML store 载荷（2 行，带稳定 rowId）→ `build_store_projection` → overlay 发布态
  ④ `adapter.materialize` 写出 xlsx
  ⑤ 🔴 **交给真 OnlyOffice 引擎重存一遍**：本机起一个临时 HTTP 文件服务，容器
     `audit-onlyoffice` 经 `host.docker.internal` 拉文件，`ConvertService.ashx`
     xlsx→xlsx 重新序列化（OO 用自己的电子表格引擎解析 + 重写 OOXML，隐藏列 / 公式 /
     defined name 是否幸存只有这一步能证）
  ⑥ `adapter.extract` 反读 OO 产物 → G1 等值门 `_assert_roundtrip_equivalent`
  ⑦ `merge_projection_into_store_rows` 合并回 store 行 ⇒ 与输入载荷逐字段比
  ⑧ openpyxl 断言：受管行 K/R/S/T/U **仍是公式**；`审定表L1-1` R7~R11 × B..L 与权威模板逐格相同
  ⑨ 真库 `L1-adj-*` 前后快照 digest 相同（本脚本**不写库**）

退出码 0 = 全绿；1 = 任一断言失败（会打印失败环节与形态，不降级为合成通过）。

用法（仓库根）::

    .venv\\Scripts\\python.exe backend/scripts/e2e/verify_l1_oo94_roundtrip.py
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import http.server
import json
import os
import socket
import sys
import tempfile
import threading
import urllib.request
import uuid
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

import sqlalchemy as sa  # noqa: E402

ENTRY_ID = "xlsx/gt-l1-short-term-loans"
OO_URL = os.environ.get("L1_OO_URL", "http://localhost:8080")
#: 容器内看宿主机的地址（Docker Desktop 约定）。
HOST_FROM_CONTAINER = os.environ.get("L1_OO_HOST_ALIAS", "host.docker.internal")
MANAGED_SHEET = "明细表L1-2"
DERIVED_SHEET = "审定表L1-1"
FORMULA_COLS = ("K", "R", "S", "T", "U")

#: 两行 HTML 载荷。rowId 用固定 UUID ⇒ 重跑结果可比；业务值覆盖全部可输入列类型。
ROWS: list[dict[str, Any]] = [
    {
        "rowId": "5f0c1e8a-1a2b-4c3d-8e9f-000000000001",
        "seqNo": 1, "loanType": "信用借款", "bank": "工商银行北京分行",
        "startDate": "2025-01-15", "endDate": "2026-01-14", "rate": 0.0345, "rateKind": "固定",
        "beginning": 1000000, "creditAmount": 500000, "debitAmount": 200000,
        "priorAje": 0, "priorRje": 0, "ajeIncrease": 0, "ajeDecrease": 0,
        "rjeIncrease": 0, "rjeDecrease": 0,
        "purpose": "流动资金周转", "guarantee": "无", "contractNo": "L1-HT-001",
        "isOverdue": "否", "confirmationRef": "L1-QZ-01", "creditReportChecked": "是",
        "remark": "往返验证行一",
    },
    {
        "rowId": "5f0c1e8a-1a2b-4c3d-8e9f-000000000002",
        "seqNo": 2, "loanType": "保证借款", "bank": "建设银行上海分行",
        "startDate": "2025-03-01", "endDate": "2026-02-28", "rate": 0.036, "rateKind": "浮动",
        "beginning": 0, "creditAmount": 800000, "debitAmount": 0,
        "priorAje": 0, "priorRje": 0, "ajeIncrease": 50000, "ajeDecrease": 0,
        "rjeIncrease": 0, "rjeDecrease": 0,
        "purpose": "采购原材料", "guarantee": "母公司担保", "contractNo": "L1-HT-002",
        "isOverdue": "否", "confirmationRef": "L1-QZ-02", "creditReportChecked": "是",
        "remark": "往返验证行二",
    },
]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("0.0.0.0", 0))
        return int(sock.getsockname()[1])


def oo_resave(src: Path, dst: Path) -> dict[str, Any]:
    """把 src 交给真 OO 引擎 xlsx→xlsx 重存，结果写 dst。返回 OO 响应体。"""
    port = _free_port()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(src.parent))
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        body = {
            "async": False,
            "filetype": "xlsx",
            "outputtype": "xlsx",
            "key": uuid.uuid4().hex,
            "title": src.name,
            "url": f"http://{HOST_FROM_CONTAINER}:{port}/{src.name}",
        }
        req = urllib.request.Request(
            f"{OO_URL}/ConvertService.ashx",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if not result.get("endConvert") or not result.get("fileUrl"):
            raise RuntimeError(f"OO ConvertService 未完成转换: {result}")
        file_url = str(result["fileUrl"])
        with urllib.request.urlopen(file_url, timeout=120) as resp:
            dst.write_bytes(resp.read())
        return result
    finally:
        server.shutdown()


def _cells(path: Path, sheet: str, rows: range, cols: str) -> dict[str, Any]:
    import openpyxl
    from openpyxl.utils import column_index_from_string

    ws = openpyxl.load_workbook(path, data_only=False)[sheet]
    start, end = (column_index_from_string(c) for c in cols.split(":"))
    out: dict[str, Any] = {}
    for r in rows:
        for c in range(start, end + 1):
            out[ws.cell(row=r, column=c).coordinate] = ws.cell(row=r, column=c).value
    return out


def _managed_formula_report(path: Path) -> tuple[list[int], dict[str, Any]]:
    """找到 bank 列（C）命中本脚本两行的物理行，返回各行 K/R/S/T/U 原值。"""
    import openpyxl

    ws = openpyxl.load_workbook(path, data_only=False)[MANAGED_SHEET]
    banks = {r["bank"] for r in ROWS}
    hit_rows = [r for r in range(1, ws.max_row + 1) if ws[f"C{r}"].value in banks]
    vals = {f"{c}{r}": ws[f"{c}{r}"].value for r in hit_rows for c in FORMULA_COLS}
    return hit_rows, vals


async def _adj_digest(session: Any) -> tuple[int, str]:
    rows = (
        await session.execute(
            sa.text(
                "SELECT item_id, coalesce(remark,'') FROM checklist_responses "
                "WHERE item_id LIKE 'L1-adj-%' ORDER BY item_id, wp_id"
            )
        )
    ).fetchall()
    h = hashlib.sha256(json.dumps([list(r) for r in rows], ensure_ascii=False).encode()).hexdigest()
    return len(rows), h


def _fail(step: str, msg: str) -> int:
    print(f"[{step}] ❌ {msg}")
    return 1


async def run() -> int:
    from app.core.database import async_session
    from app.services.workpaper_sync import phase5_l1_short_term_loans as L1
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

    async with async_session() as session:
        target = (
            await session.execute(
                sa.text(
                    "SELECT es.wp_id, wp.project_id FROM working_paper_sync_entry_state es "
                    "JOIN working_paper wp ON wp.id = es.wp_id WHERE es.entry_id = :e"
                ),
                {"e": ENTRY_ID},
            )
        ).first()
        if target is None:
            return _fail("0", "entry_state 无 L1 行 —— 先完成 task 7b 首版发布")
        wp_id, project_id = target.wp_id, target.project_id
        adj_before = await _adj_digest(session)
        print(f"[0] wp={str(wp_id)[:8]} project={str(project_id)[:8]} L1-adj 快照={adj_before[0]} 行")

        # ① 生产 attach
        registry = WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        ids = await L1.attach_adapters(registry, session=session)
        if ids != (L1.ADAPTER_ID,):
            return _fail("①", f"attach 返回 {ids!r}（manifest capability 或 representation 未就位）")
        registration = registry.resolve_for_entry(ENTRY_ID)
        contract = registration.contract
        print(f"[①] attach={ids}")

        # ② 真实 substrate
        resolver = CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND))
        resolution = await resolver.resolve(
            intent=ResolutionIntent.extract, project_id=project_id, wp_id=wp_id, entry_id=ENTRY_ID
        )
        substrate = resolution.artifact_path
        print(f"[②] generation={resolution.representation_generation} substrate={substrate.name}")

        # ③ store → projection（+ overlay 发布态）
        payload = json.dumps(ROWS, ensure_ascii=False)
        store_projection = L1.build_store_projection(payload, contract=contract)
        projection, _ = await _overlay_with_published_substrate(
            resolution=resolver, project_id=project_id, wp_id=wp_id, entry_id=ENTRY_ID,
            registration=registration, store_projection=store_projection,
        )
        n_rows = sum(len(v) for v in projection.row_keys.values())
        print(f"[③] projection values={len(projection.values)} rows={n_rows}")
        if n_rows != len(ROWS):
            return _fail("③", f"projection 行数 {n_rows} ≠ 输入 {len(ROWS)}")

        with tempfile.TemporaryDirectory() as tmp:
            mat = Path(tmp) / "l1-materialized.xlsx"
            oo = Path(tmp) / "l1-oo-resaved.xlsx"
            # ④ materialize
            registration.adapter.materialize(
                substrate=substrate, projection=projection, output=mat, contract=contract
            )
            print(f"[④] materialize size={mat.stat().st_size}")
            mat_copy = Path(tmp) / "l1-materialized-snapshot.xlsx"
            mat_copy.write_bytes(mat.read_bytes())
            keep = os.environ.get("L1_KEEP_DIR")
            if keep:
                Path(keep).mkdir(parents=True, exist_ok=True)
                (Path(keep) / "substrate.xlsx").write_bytes(Path(substrate).read_bytes())
                (Path(keep) / "materialized.xlsx").write_bytes(mat.read_bytes())

            # ⑤ 真 OO 引擎重存
            try:
                oo_result = oo_resave(mat, oo)
            except Exception as exc:  # noqa: BLE001 —— 真栈须如实报告
                return _fail("⑤", f"OO ConvertService 失败 {type(exc).__name__}: {exc}")
            print(f"[⑤] OO resave OK size={oo.stat().st_size} percent={oo_result.get('percent')}")

            # ⑥ extract + G1 等值门
            extracted = registration.adapter.extract(artifact=oo, contract=contract)
            try:
                ContentMutationService._assert_roundtrip_equivalent(
                    None,  # type: ignore[arg-type]
                    intended=projection, extracted=extracted, contract=contract,
                )
            except Exception as exc:  # noqa: BLE001
                return _fail("⑥", f"G1 等值门失败 {type(exc).__name__}: {exc}")
            print(f"[⑥] extract values={len(extracted.values)} · G1 等值门 OK")

            # ⑦ 合并回 store 行，逐字段比
            merged, *_ = L1.merge_projection_into_store_rows(projection=extracted, base_rows=ROWS)
            by_id = {r["rowId"]: r for r in merged}
            diffs = []
            for src in ROWS:
                got = by_id.get(src["rowId"])
                if got is None:
                    diffs.append(f"rowId {src['rowId'][-4:]} 丢失")
                    continue
                for k, v in src.items():
                    gv = got.get(k)
                    same = (float(gv) == float(v)) if isinstance(v, (int, float)) and gv not in (None, "") else (str(gv) == str(v))
                    if not same:
                        diffs.append(f"{src['rowId'][-4:]}.{k}: {v!r} → {gv!r}")
            if diffs:
                return _fail("⑦", f"store 往返后不等 {len(diffs)} 处: {diffs[:8]}")
            # 🔴 substrate 保留模板 R10~R25 的 16 条预印行（只有序号 1..16），新行落在其后；
            #    它们若被合并回 store 就是幽灵行 —— 必须被 ghost_row_anchor（bank）挡掉。
            extra = [r for r in merged if r.get("rowId") not in by_id or r.get("rowId") not in {x["rowId"] for x in ROWS}]
            if len(merged) != len(ROWS) or extra:
                return _fail("⑦", f"合并回 store 得 {len(merged)} 行（期望 {len(ROWS)}），多出 {[(e.get('rowId'), e.get('seqNo')) for e in extra][:5]}")
            print(f"[⑦] L1-2-rows 往返逐字段相等（{len(ROWS)} 行 × {len(ROWS[0])} 键，rowId 稳定）")

            # ⑧ 公式列幸存 + 审定表只读投影未被写坏
            hit_rows, fvals = _managed_formula_report(oo)
            not_formula = {k: v for k, v in fvals.items() if not (isinstance(v, str) and v.startswith("="))}
            if len(hit_rows) != len(ROWS) or not_formula:
                return _fail("⑧", f"受管行={hit_rows} 非公式格={not_formula}")
            print(f"[⑧a] OO 重存后受管行 {hit_rows} 的 K/R/S/T/U {len(fvals)} 格全部仍是公式")
            # 🔴 分两段比，否则分不清「谁改的」：
            #   模板 → materialize：只允许裸 IF 格被 OO 崩溃中性化（task 6 有意挂载，GC-2 策略）
            #   materialize → OO：一格都不许变（OO 引擎不得改写只读投影）
            tpl = _cells(L1.authoritative_template_path(), DERIVED_SHEET, range(7, 12), "B:L")
            mid = _cells(mat_copy, DERIVED_SHEET, range(7, 12), "B:L")
            after = _cells(oo, DERIVED_SHEET, range(7, 12), "B:L")
            by_oo = {k: (mid[k], after[k]) for k in mid if mid[k] != after[k]}
            if by_oo:
                return _fail("⑧", f"OO 引擎改写了 {DERIVED_SHEET} {len(by_oo)} 格: {list(by_oo.items())[:4]}")
            by_us = {k: (tpl[k], mid[k]) for k in tpl if tpl[k] != mid[k]}
            def _bare_if(v: Any) -> bool:
                return isinstance(v, str) and "IF(" in v.upper() and "IFERROR(" not in v.upper()
            unexpected = {k: v for k, v in by_us.items() if not _bare_if(v[0])}
            if unexpected:
                return _fail("⑧", f"materialize 改了非裸 IF 格 {list(unexpected.items())[:4]}")
            print(
                f"[⑧b] {DERIVED_SHEET} R7~R11×B..L {len(tpl)} 格：OO 引擎改写 0 格；"
                f"materialize 只中性化裸 IF {len(by_us)} 格 {sorted(by_us)}（task 6 挂载的 OO 崩溃中性化，预期）"
            )

        # ⑨ 不写库：L1-adj 快照不变
        adj_after = await _adj_digest(session)
        if adj_after != adj_before:
            return _fail("⑨", f"L1-adj-* 快照变化 {adj_before} → {adj_after}")
        print(f"[⑨] L1-adj-* {adj_after[0]} 行快照 digest 不变")

    print("✅ L1 真 OO 引擎往返全绿（HTML→OO→HTML）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
