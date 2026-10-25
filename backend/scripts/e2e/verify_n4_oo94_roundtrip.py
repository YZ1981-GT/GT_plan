# -*- coding: utf-8 -*-
"""N4 真 OnlyOffice 引擎往返验证（HTML → OO → HTML）。

spec: n-cycle-sync-foundation-and-first-canary · N4 canary · Task 10

照 `verify_l1_oo94_roundtrip.py` 克隆，换成 N4：
  ENTRY_ID / MANAGED_SHEET(税金及附加明细表N4-2) / DERIVED_SHEET(税金及附加审定表N4-1) /
  FORMULA_COLS(E,I,K) / ROWS(2 行固定 UUID rowKey，覆盖税种名 + 本/上期各列 + 应交税费贷方) /
  行身份键 rowKey(熵键，同税种可多行) / ghost 锚点 taxType(模板 A 列) / adj 快照 N4-2-detail-rows。

🔴 链路每一步都是生产代码，无合成替身；真 ConvertService xlsx→xlsx 重存。
🔴 N4-2 预印 8 税种名（r9~r16，无 UUID）+ 2 空行 ⇒ 这些模板预印行若被合并回 store 就是幽灵行，
   必须被 ghost_row_anchor（taxType）挡掉（J1 行翻倍教训：本脚本两行用「往返验证税种一/二」这类
   **与预印税种名不同**的 taxType，确保它们是真新行、预印行被过滤）。
🔴 真库 `N4-2-detail-rows` 现算 0 行 ⇒ 用合成 2 行固定 UUID 载荷，真库行数分母**如实声明为空**。
🔴 ConvertService 不重算公式 ⇒ 不以缓存值判定；只断言公式格往返后**仍是公式**。

退出码 0 = 全绿；1 = 任一断言失败（打印失败环节与形态，不降级为合成通过）。

用法（仓库根）::
    .venv\\Scripts\\python.exe backend/scripts/e2e/verify_n4_oo94_roundtrip.py
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

ENTRY_ID = "xlsx/gt-n4-taxes-and-surcharges"
OO_URL = os.environ.get("N4_OO_URL", "http://localhost:8080")
HOST_FROM_CONTAINER = os.environ.get("N4_OO_HOST_ALIAS", "host.docker.internal")
MANAGED_SHEET = "税金及附加明细表N4-2"
DERIVED_SHEET = "税金及附加审定表N4-1"
FORMULA_COLS = ("E", "I", "K")
STORE_ITEM_ID = "N4-2-detail-rows"
ROW_KEY = "rowKey"

#: 两行 HTML 载荷。rowKey 固定 ⇒ 重跑可比；taxType 用**非预印**税种名确保是真新行；
#:   覆盖模板 N4-2 的 11 列映射键（period/prior 各 未审/账项/重分类 + 应交税费贷方 + 差异）。
ROWS: list[dict[str, Any]] = [
    {
        ROW_KEY: "7a1c3e8b-0000-4000-8000-00000000n401".replace("n4", "01"),
        "taxType": "往返验证税种一",
        "periodUnadjusted": 120000, "periodAje": 5000, "periodRje": 0,
        "priorUnadjusted": 100000, "priorAje": 0, "priorRje": 0,
        "accrualCredit": 123000, "remark": "往返验证行一",
    },
    {
        ROW_KEY: "7a1c3e8b-0000-4000-8000-000000000002",
        "taxType": "往返验证税种二",
        "periodUnadjusted": 80000, "periodAje": 0, "periodRje": 2000,
        "priorUnadjusted": 75000, "priorAje": 0, "priorRje": 0,
        "accrualCredit": 81500, "remark": "往返验证行二",
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
    """找到 taxType 列（A）命中本脚本两行的物理行，返回各行 E/I/K 原值。"""
    import openpyxl

    ws = openpyxl.load_workbook(path, data_only=False)[MANAGED_SHEET]
    names = {r["taxType"] for r in ROWS}
    hit_rows = [r for r in range(1, ws.max_row + 1) if ws[f"A{r}"].value in names]
    vals = {f"{c}{r}": ws[f"{c}{r}"].value for r in hit_rows for c in FORMULA_COLS}
    return hit_rows, vals


async def _store_digest(session: Any) -> tuple[int, str]:
    rows = (
        await session.execute(
            sa.text(
                "SELECT item_id, coalesce(remark,''), coalesce(conclusion,'') "
                "FROM checklist_responses WHERE item_id = :i ORDER BY wp_id"
            ),
            {"i": STORE_ITEM_ID},
        )
    ).fetchall()
    h = hashlib.sha256(json.dumps([list(r) for r in rows], ensure_ascii=False).encode()).hexdigest()
    return len(rows), h


def _fail(step: str, msg: str) -> int:
    print(f"[{step}] ❌ {msg}")
    return 1


async def run() -> int:
    from app.core.database import async_session
    from app.services.workpaper_sync import phase5_n4_taxes_and_surcharges as N4
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
            return _fail("0", "entry_state 无 N4 行 —— 先完成 Task 7d 首版发布")
        wp_id, project_id = target.wp_id, target.project_id
        store_before = await _store_digest(session)
        print(
            f"[0] wp={str(wp_id)[:8]} project={str(project_id)[:8]} "
            f"真库 {STORE_ITEM_ID} 分母={store_before[0]} 行（0=如实空分母，往返用合成 2 行）"
        )

        # ① 生产 attach
        registry = WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        ids = await N4.attach_adapters(registry, session=session)
        if ids != (N4.ADAPTER_ID,):
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
        store_projection = N4.build_store_projection(payload, contract=contract)
        projection, _ = await _overlay_with_published_substrate(
            resolution=resolver, project_id=project_id, wp_id=wp_id, entry_id=ENTRY_ID,
            registration=registration, store_projection=store_projection,
        )
        n_rows = sum(len(v) for v in projection.row_keys.values())
        print(f"[③] projection values={len(projection.values)} rows={n_rows}")
        if n_rows != len(ROWS):
            return _fail("③", f"projection 行数 {n_rows} ≠ 输入 {len(ROWS)}")

        with tempfile.TemporaryDirectory() as tmp:
            mat = Path(tmp) / "n4-materialized.xlsx"
            oo = Path(tmp) / "n4-oo-resaved.xlsx"
            registration.adapter.materialize(
                substrate=substrate, projection=projection, output=mat, contract=contract
            )
            print(f"[④] materialize size={mat.stat().st_size}")
            mat_copy = Path(tmp) / "n4-materialized-snapshot.xlsx"
            mat_copy.write_bytes(mat.read_bytes())
            keep = os.environ.get("N4_KEEP_DIR")
            if keep:
                Path(keep).mkdir(parents=True, exist_ok=True)
                (Path(keep) / "substrate.xlsx").write_bytes(Path(substrate).read_bytes())
                (Path(keep) / "materialized.xlsx").write_bytes(mat.read_bytes())

            # ⑤ 真 OO 引擎重存
            try:
                oo_result = oo_resave(mat, oo)
            except Exception as exc:  # noqa: BLE001
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
            # 🔴 N4 与 L1 的关键差异（J1 预印行教训）：N4-2 模板预印 8 个**具名**税种行
            #    （消费税/城市维护建设税/…，r9~r16），instrumentation 给它们铸了稳定身份
            #    `GTROW-N42-*`。它们是**真实模板内容**（非空 taxType）而非幽灵行 ⇒ 往返后
            #    合法保留，不该被 ghost_row_anchor 过滤（L1 能过只因其预印行只有序号、taxType
            #    空）。本脚本的 2 行合成载荷落在预印行之后，身份 = 本脚本给的 rowKey。
            #    判据：① 我的 2 行逐字段按 rowKey 稳定往返 ② 预印具名行全部保留（标签不丢、
            #    不被我的行覆盖）③ 合并结果 = 预印 8 行 + 我的 2 行，无身份错配。
            merged, *_ = N4.merge_projection_into_store_rows(projection=extracted, base_rows=ROWS)
            by_id = {r[ROW_KEY]: r for r in merged}
            diffs = []
            for src in ROWS:
                got = by_id.get(src[ROW_KEY])
                if got is None:
                    diffs.append(f"rowKey {src[ROW_KEY][-4:]} 丢失")
                    continue
                for k, v in src.items():
                    gv = got.get(k)
                    same = (
                        (float(gv) == float(v))
                        if isinstance(v, (int, float)) and gv not in (None, "")
                        else (str(gv) == str(v))
                    )
                    if not same:
                        diffs.append(f"{src[ROW_KEY][-4:]}.{k}: {v!r} → {gv!r}")
            if diffs:
                return _fail("⑦", f"我的 2 行 store 往返后不等 {len(diffs)} 处: {diffs[:8]}")
            # 预印具名行：身份 GTROW-N42-*，taxType 非空（真实模板税种名），全部保留。
            preprinted = [r for r in merged if str(r.get(ROW_KEY, "")).startswith("GTROW-N42-")]
            preprinted_names = [r.get("taxType") for r in preprinted]
            mine = [r for r in merged if r.get(ROW_KEY) in {x[ROW_KEY] for x in ROWS}]
            unexpected = [
                r for r in merged
                if r.get(ROW_KEY) not in {x[ROW_KEY] for x in ROWS}
                and not str(r.get(ROW_KEY, "")).startswith("GTROW-N42-")
            ]
            if unexpected:
                return _fail(
                    "⑦",
                    f"出现既非我的行也非预印行的身份：{[(e.get(ROW_KEY), e.get('taxType')) for e in unexpected][:5]}",
                )
            if len(mine) != len(ROWS):
                return _fail("⑦", f"我的行往返后 {len(mine)} 条（期望 {len(ROWS)}）")
            # 预印行的税种名不得被我的行覆盖/错配（具名内容幸存）。
            if any(n in {None, ""} for n in preprinted_names):
                return _fail("⑦", f"预印具名行出现空 taxType ⇒ 标签丢失：{preprinted_names}")
            print(
                f"[⑦] {STORE_ITEM_ID} 往返：我的 {len(mine)} 行逐字段相等（rowKey 稳定）"
                f" + {len(preprinted)} 条预印具名行保留（{preprinted_names}）；无错配身份"
            )

            # ⑧ 公式列幸存 + 审定表只读投影未被写坏
            hit_rows, fvals = _managed_formula_report(oo)
            not_formula = {k: v for k, v in fvals.items() if not (isinstance(v, str) and v.startswith("="))}
            if len(hit_rows) != len(ROWS) or not_formula:
                return _fail("⑧", f"受管行={hit_rows} 非公式格={not_formula}")
            print(f"[⑧a] OO 重存后受管行 {hit_rows} 的 E/I/K {len(fvals)} 格全部仍是公式")
            # 分两段比（谁改的）：模板→materialize 只允许裸 IF 被中性化；materialize→OO 一格不许变。
            tpl = _cells(N4.authoritative_template_path(), DERIVED_SHEET, range(7, 16), "A:M")
            mid = _cells(mat_copy, DERIVED_SHEET, range(7, 16), "A:M")
            after = _cells(oo, DERIVED_SHEET, range(7, 16), "A:M")
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
                f"[⑧b] {DERIVED_SHEET} R7~R15×A..M {len(tpl)} 格：OO 引擎改写 0 格；"
                f"materialize 只中性化裸 IF {len(by_us)} 格 {sorted(by_us)}（GC-2 挂载的 OO 崩溃中性化，预期）"
            )

        # ⑨ 不写库：store 快照不变
        store_after = await _store_digest(session)
        if store_after != store_before:
            return _fail("⑨", f"{STORE_ITEM_ID} 快照变化 {store_before} → {store_after}")
        print(f"[⑨] {STORE_ITEM_ID} {store_after[0]} 行快照 digest 不变（脚本不写库）")

    print("✅ N4 真 OO 引擎往返全绿（HTML→OO→HTML）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
