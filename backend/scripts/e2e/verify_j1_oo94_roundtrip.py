# -*- coding: utf-8 -*-
"""J1 真 OnlyOffice 引擎往返验证（HTML → OO → HTML），两轮。

spec: j-cycle-sync-foundation-and-first-canary · Task 24 · JF-P42
范式：照 `verify_l1_oo94_roundtrip.py`（L1 Task 10）—— 每一步都是生产代码，无合成替身。

═══ 链路 ═══
  ① `phase5_j1_employee_compensation.attach_pilot_adapters()` 按 manifest + 真库 published
     representation 挂 adapter（Task 75 冻结身份观测器）
  ② `CanonicalResolutionService.resolve(extract)` 取当前 representation 的真实字节
  ③ HTML store 载荷 → `build_store_projection` → overlay 发布态
  ④ `adapter.materialize` 写出 xlsx
  ⑤ 🔴 真 OO 引擎 `ConvertService.ashx` xlsx→xlsx 重存（容器经 host.docker.internal 拉文件）
  ⑥ `adapter.extract` 反读 OO 产物 → G1 等值门
  ⑦ `merge_projection_into_store_rows` 合并回 store 行 ⇒ 与输入逐字段比（含幽灵行防护）
  ⑧ openpyxl：受管行 G/I **仍是公式**；第二轮另用 data_only 读 OO 重算后的缓存值，
     验 `G = ROUND(D*F, 2)` 与 `I = G - H`（Task 24 前置断言 ⑥）
  ⑨ 真库 `J1-%` 前后快照 digest 相同（本脚本**不写库**）

═══ 两轮（Task 24 前置断言 ⑥）═══
  · 第一轮「骨架」：19 行全 0 金额（复刻 spec Task 20 记录的真库 3473 B 载荷形态 —— 🔴 该载荷在
    2026-10-01 的真库里已不存在（库疑被重置），故按其已登记形态重建，只验结构）
  · 第二轮「带金额」：同 19 行填合成金额，验两个公式

🔴 业务行按 **A 列非空**判，**不**套 `明细表J1-2 ` 的「B 列 + 三 footer」口径（前置断言 ⑤）。
🔴 只经声明的 write_carrier；不改任何键名；不碰 `J1-2-detail-*` / `J1-disc-*`（前置断言 ①④）。

用法（仓库根）::  .venv\\Scripts\\python.exe backend/scripts/e2e/verify_j1_oo94_roundtrip.py
"""
from __future__ import annotations

import argparse
import asyncio
import functools
import hashlib
import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
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

ENTRY_ID = "xlsx/j1/gt-j1-employee-compensation"
OO_URL = os.environ.get("J1_OO_URL", "http://localhost:8080")
HOST_FROM_CONTAINER = os.environ.get("J1_OO_HOST_ALIAS", "host.docker.internal")
MANAGED_SHEET = "计提情况检查表J1-6"
FIRST_ROW, LAST_ROW = 17, 35
TEMPLATE_ID = "J16S"
FORMULA_COLS = ("G", "I")
EVIDENCE_SOURCE_FILES = (
    "backend/app/services/workpaper_sync/phase5_j1_employee_compensation.py",
    "backend/app/services/workpaper_sync/phase5_j1_06_accrual_check.py",
    "backend/data/workpaper_sync_contracts/j1.accrual_check_short_term.json",
    "backend/wp_templates/J/J1 应付职工薪酬.xlsx",
    "audit-platform/frontend/src/components/workpaper/j1/inspection/j1AccrualSkeleton.json",
    "audit-platform/frontend/src/components/workpaper/j1/inspection/j1AccrualRowIdentity.ts",
    "audit-platform/frontend/src/components/workpaper/j1/inspection/J1TabAccrualCheck.vue",
)


def _source_digest() -> str:
    h = hashlib.sha256()
    for rel in EVIDENCE_SOURCE_FILES:
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update((_REPO / rel).read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _frontend_skeleton() -> list[dict[str, Any]]:
    """真实前端骨架单一来源；同时逐字节对账权威模板，禁止测试从模板自造必等输入。"""
    import openpyxl

    from app.services.workpaper_sync import phase5_j1_employee_compensation as J1

    source = _REPO / (
        "audit-platform/frontend/src/components/workpaper/j1/inspection/j1AccrualSkeleton.json"
    )
    doc = json.loads(source.read_text(encoding="utf-8"))
    if doc.get("templateId") != TEMPLATE_ID or int(doc.get("firstRow", -1)) != FIRST_ROW:
        raise RuntimeError(f"前端骨架 identity 元数据漂移: {doc.get('templateId')}/{doc.get('firstRow')}")
    rows = list(doc.get("rows") or [])
    ws = openpyxl.load_workbook(J1.authoritative_template_path(), data_only=False)[MANAGED_SHEET]
    template_labels = [ws[f"A{r}"].value for r in range(FIRST_ROW, LAST_ROW + 1)]
    frontend_labels = [r.get("label") for r in rows]
    if frontend_labels != template_labels:
        diffs = [
            f"R{FIRST_ROW + i}: frontend={a!r} template={b!r}"
            for i, (a, b) in enumerate(zip(frontend_labels, template_labels)) if a != b
        ]
        raise RuntimeError(f"前端骨架标签不是模板原字节: {diffs[:5]}")
    return rows


def _rows(defaults: list[dict[str, Any]], *, with_amounts: bool) -> list[dict[str, Any]]:
    rows = []
    for i, default in enumerate(defaults, 1):
        label = str(default["label"])
        row: dict[str, Any] = {
            # 🔴 与前端 `j1AccrualRowIdentity.shortTermTemplateRowId` 同口径：骨架行身份 = 模板行身份。
            #    首轮用 `acr-*` 时实测行翻倍（38 行），那就是本脚本抓到的缺陷。
            #    变异反证：`J1_RT_LEGACY_IDS=1` 改回旧身份，本脚本 SHALL 在 ⑦ 打红（行翻倍）。
            "id": (
                f"acr-rt-{i:02d}"
                if os.environ.get("J1_RT_LEGACY_IDS") == "1"
                else f"GTROW-{TEMPLATE_ID}-{FIRST_ROW + i - 1:04d}"
            ),
            "label": label,
            "indent": int(default["indent"]),
            "baseName": f"计提基数{i}" if with_amounts else "",
            "baseAmount": 100000 + i * 1234.5 if with_amounts else 0,
            "baseIndex": f"J1-6-{i}" if with_amounts else "",
            "rate": round(0.01 * (i % 7 + 1), 4) if with_amounts else 0,
            "actual": 1000 + i * 37 if with_amounts else 0,
            "diffReason": "往返验证" if with_amounts else "",
            "conclusion": "相符" if with_amounts else "",
        }
        rows.append(row)
    return rows


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("0.0.0.0", 0))
        return int(sock.getsockname()[1])


def oo_resave(src: Path, dst: Path) -> dict[str, Any]:
    port = _free_port()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(src.parent))
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        body = {
            "async": False, "filetype": "xlsx", "outputtype": "xlsx",
            "key": uuid.uuid4().hex, "title": src.name,
            "url": f"http://{HOST_FROM_CONTAINER}:{port}/{src.name}",
        }
        req = urllib.request.Request(
            f"{OO_URL}/ConvertService.ashx", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if not result.get("endConvert") or not result.get("fileUrl"):
            raise RuntimeError(f"OO ConvertService 未完成转换: {result}")
        with urllib.request.urlopen(str(result["fileUrl"]), timeout=120) as resp:
            dst.write_bytes(resp.read())
        return result
    finally:
        server.shutdown()


async def _j_digest(session: Any) -> tuple[int, str]:
    rows = (
        await session.execute(
            sa.text(
                "SELECT item_id, wp_id::text, coalesce(remark,''), coalesce(conclusion,'') "
                "FROM checklist_responses WHERE item_id LIKE 'J1-%' ORDER BY 1, 2"
            )
        )
    ).fetchall()
    h = hashlib.sha256(json.dumps([list(r) for r in rows], ensure_ascii=False).encode()).hexdigest()
    return len(rows), h


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and b not in (None, ""):
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return False
    if a in (None, "") and b in (None, ""):
        return True
    return str(a) == str(b)


def _round2(x: float) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def _one_round(name: str, rows: list[dict[str, Any]], ctx: dict[str, Any]) -> str | None:
    """返回 None = 本轮全绿；否则返回失败描述。"""
    import openpyxl

    from app.services.workpaper_sync import phase5_j1_employee_compensation as J1
    from app.services.workpaper_sync.content_mutation import ContentMutationService
    from app.services.workpaper_sync.store_projection_response import (
        _overlay_with_published_substrate,
    )

    reg, contract = ctx["registration"], ctx["registration"].contract
    store_projection = J1.build_store_projection(json.dumps(rows, ensure_ascii=False), contract=contract)
    projection, _ = await _overlay_with_published_substrate(
        resolution=ctx["resolver"], project_id=ctx["project_id"], wp_id=ctx["wp_id"],
        entry_id=ENTRY_ID, registration=reg, store_projection=store_projection,
    )
    n_rows = sum(len(v) for v in projection.row_keys.values())
    print(f"  [{name}③] projection values={len(projection.values)} rows={n_rows}")
    if n_rows != len(rows):
        return f"③ projection 行数 {n_rows} ≠ 输入 {len(rows)}"

    with tempfile.TemporaryDirectory() as tmp:
        mat, oo = Path(tmp) / f"j1-{name}-mat.xlsx", Path(tmp) / f"j1-{name}-oo.xlsx"
        reg.adapter.materialize(substrate=ctx["substrate"], projection=projection, output=mat, contract=contract)
        print(f"  [{name}④] materialize size={mat.stat().st_size}")
        keep = os.environ.get("J1_KEEP_DIR")
        if keep:
            Path(keep).mkdir(parents=True, exist_ok=True)
            (Path(keep) / "substrate.xlsx").write_bytes(Path(ctx["substrate"]).read_bytes())
            (Path(keep) / f"{name}-materialized.xlsx").write_bytes(mat.read_bytes())
        try:
            res = oo_resave(mat, oo)
        except Exception as exc:  # noqa: BLE001
            return f"⑤ OO ConvertService 失败 {type(exc).__name__}: {exc}"
        print(f"  [{name}⑤] OO resave OK size={oo.stat().st_size} percent={res.get('percent')}")

        extracted = reg.adapter.extract(artifact=oo, contract=contract)
        try:
            ContentMutationService._assert_roundtrip_equivalent(
                None, intended=projection, extracted=extracted, contract=contract  # type: ignore[arg-type]
            )
        except Exception as exc:  # noqa: BLE001
            return f"⑥ G1 等值门失败 {type(exc).__name__}: {exc}"
        print(f"  [{name}⑥] extract values={len(extracted.values)} · G1 等值门 OK")

        merged, *_ = J1.merge_projection_into_store_rows(projection=extracted, base_rows=rows)
        by_id = {r["id"]: r for r in merged}
        diffs = [
            f"{src['id']}.{k}: {v!r} → {by_id.get(src['id'], {}).get(k)!r}"
            for src in rows
            for k, v in src.items()
            if src["id"] not in by_id or not _same(v, by_id[src["id"]].get(k))
        ]
        if diffs:
            return f"⑦ store 往返后不等 {len(diffs)} 处: {diffs[:6]}"
        if len(merged) != len(rows):
            return f"⑦ 合并回 store 得 {len(merged)} 行（期望 {len(rows)}）—— 幽灵行防护失效"
        print(f"  [{name}⑦] J1-6-short-term 往返逐字段相等（{len(rows)} 行，id 稳定）")

        ws_f = openpyxl.load_workbook(oo, data_only=False)[MANAGED_SHEET]
        labels = {r["label"] for r in rows}
        hit = [r for r in range(1, ws_f.max_row + 1) if ws_f[f"A{r}"].value in labels]
        not_formula = {
            f"{c}{r}": ws_f[f"{c}{r}"].value
            for r in hit for c in FORMULA_COLS
            if not (isinstance(ws_f[f"{c}{r}"].value, str) and str(ws_f[f"{c}{r}"].value).startswith("="))
        }
        if len(hit) != len(rows) or not_formula:
            return f"⑧ 受管行 {len(hit)}/{len(rows)}，非公式格 {list(not_formula.items())[:4]}"
        print(f"  [{name}⑧a] OO 重存后 {len(hit)} 行的 G/I {len(hit) * 2} 格全部仍是公式")

        if ctx.get("check_values"):
            # 🔴 不读 OO 产物的**缓存值**判公式：ConvertService xlsx→xlsx 不触发重算（实测 G/I 缓存恒 0，
            #    与输入无关）⇒ 拿它判会把「引擎没重算」误报成「公式错」。正确判据分两半：
            #    ①公式文本逐行恰为 `=ROUND(D{r}*F{r},2)` / `=G{r}-H{r}`（行号与本行对齐，没串行）
            #    ②输入格 D/F/H 往返后逐值等于载荷 ⇒ 用同一公式在本地重算得到的 G/I 就是 Excel 侧结果
            by_label = {r["label"]: r for r in rows}
            bad = []
            for r in hit:
                g_f, i_f = ws_f[f"G{r}"].value, ws_f[f"I{r}"].value
                if g_f != f"=ROUND(D{r}*F{r},2)" or i_f != f"=G{r}-H{r}":
                    bad.append(f"R{r} 公式 G={g_f!r} I={i_f!r}")
                    continue
                src = by_label[ws_f[f"A{r}"].value]
                d, f, h = (ws_f[f"{c}{r}"].value for c in ("D", "F", "H"))
                if not (_same(src["baseAmount"], d) and _same(src["rate"], f) and _same(src["actual"], h)):
                    bad.append(f"R{r} 输入格 D/F/H={d!r}/{f!r}/{h!r} ≠ 载荷")
            if bad:
                return f"⑧b 公式/输入不符 {len(bad)} 行: {bad[:4]}"
            sample = rows[0]
            g0 = _round2(float(sample["baseAmount"]) * float(sample["rate"]))
            print(
                f"  [{name}⑧b] {len(hit)} 行公式逐行 `=ROUND(D*F,2)` / `=G-H` 且 D/F/H 往返逐值相等"
                f"（例：首行 G={g0}、I={_round2(float(g0) - float(sample['actual']))}）"
            )
    return None


def _onlyoffice_version() -> dict[str, Any]:
    """记录真实引擎版本；HTTP info 受部署策略 403 时，以容器包版本为权威。"""
    try:
        req = urllib.request.Request(f"{OO_URL}/info/info.json", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            server = resp.headers.get("Server")
        version = data.get("version") or data.get("buildVersion") or data.get("buildNumber")
        if version:
            return {"version": str(version), "source": "info/info.json", "server": server}
    except Exception:
        pass
    container = os.environ.get("J1_OO_CONTAINER", "audit-onlyoffice")
    proc = subprocess.run(
        ["docker", "exec", container, "dpkg-query", "-W", "-f=${Version}", "onlyoffice-documentserver"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    version = proc.stdout.strip()
    if proc.returncode != 0 or not version:
        raise RuntimeError(f"无法取得 OnlyOffice 版本: rc={proc.returncode} stderr={proc.stderr[:200]!r}")
    return {"version": version, "source": f"docker:{container}/dpkg-query"}


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=_REPO, check=True,
        capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()


def _zip_external_links(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return sorted(
            n for n in zf.namelist()
            if n.startswith("xl/externalLinks/") or (
                n.endswith(".rels") and b'TargetMode="External"' in zf.read(n)
            )
        )


async def _active_definition_evidence(session: Any, resolution: Any, contract: Any) -> dict[str, Any]:
    """current representation → approved bundle → 四 child digest → active template bytes。"""
    from app.models.workpaper_sync_models import WorkpaperArtifact, WorkpaperSyncDefinitionArtifact
    from app.services.workpaper_sync import phase5_j1_employee_compensation as J1
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.definitions import canonical_digest
    from app.services.workpaper_sync.models import BundleSlot

    expected = {
        "authority_model": canonical_digest(J1.authority_model_payload()),
        "template": contract.template_definition_sha256,
        "instrumentation": contract.instrumentation_definition_sha256,
        "contract": contract.canonical_sha256,
    }
    actual = {
        "authority_model": resolution.bundle.authority_model_definition_sha256,
        **{slot.value: resolution.bundle.slots[slot].slot_digest for slot in BundleSlot},
    }
    if actual != expected:
        raise RuntimeError(f"active bundle digest 与 provider 当前定义不一致: actual={actual} expected={expected}")

    template_ref = resolution.bundle.slots[BundleSlot.template].slot_ref
    template_id = uuid.UUID(str(template_ref).removeprefix("definition:"))
    row = (
        await session.execute(
            sa.select(WorkpaperSyncDefinitionArtifact, WorkpaperArtifact)
            .join(WorkpaperArtifact, WorkpaperArtifact.id == WorkpaperSyncDefinitionArtifact.blob_artifact_id)
            .where(WorkpaperSyncDefinitionArtifact.id == template_id)
        )
    ).one()
    definition, artifact = row
    path = CanonicalArtifactRepository(_BACKEND).resolve_relative_path(artifact.relative_path)
    external = _zip_external_links(path)
    authority_external = _zip_external_links(J1.authoritative_template_path())
    if external or authority_external:
        raise RuntimeError(f"模板仍有外链: active={external} authority={authority_external}")
    return {
        "representation_id": str(resolution.representation_id),
        "generation": resolution.representation_generation,
        "bundle_id": str(resolution.bundle.bundle_id),
        "bundle_sha256": resolution.bundle.bundle_sha256,
        "digests": actual,
        "template_definition_source_commit": definition.source_commit,
        "active_template_artifact": artifact.relative_path,
        "active_template_sha256": artifact.sha256,
        "external_links": [],
    }


async def run(*, project_id: uuid.UUID, wp_id: uuid.UUID, evidence_path: Path) -> int:
    from app.core.database import async_session
    from app.services.workpaper_sync import phase5_j1_employee_compensation as J1
    from app.services.workpaper_sync.adapters.registry import WorkpaperSyncAdapterRegistry
    from app.services.workpaper_sync.entry_profile import load_entry_manifest
    from app.services.workpaper_sync.resolution import (
        CanonicalArtifactRepository,
        CanonicalResolutionService,
        ResolutionIntent,
    )

    async with async_session() as session:
        targets = (
            await session.execute(
                sa.text(
                    "SELECT es.wp_id, wp.project_id, wi.wp_code FROM working_paper_sync_entry_state es "
                    "JOIN working_paper wp ON wp.id = es.wp_id "
                    "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                    "WHERE es.entry_id = :e AND es.wp_id = CAST(:w AS uuid) "
                    "AND wp.project_id = CAST(:p AS uuid)"
                ),
                {"e": ENTRY_ID, "w": str(wp_id), "p": str(project_id)},
            )
        ).all()
        if len(targets) != 1:
            print(f"[0] ❌ 指定 project/wp 必须精确命中 1 条 J1 entry_state，实际 {len(targets)}")
            return 1
        target = targets[0]
        if target.wp_code != "J1":
            print(f"[0] ❌ 指定底稿 wp_code={target.wp_code!r}，不是 J1")
            return 1
        before = await _j_digest(session)
        print(f"[0] wp={str(target.wp_id)[:8]} project={str(target.project_id)[:8]} J1-% 快照={before[0]} 行")

        registry = WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        ids = await J1.attach_pilot_adapters(registry, session=session)
        if ids != (J1.ADAPTER_ID,):
            print(f"[①] ❌ attach 返回 {ids!r}")
            return 1
        print(f"[①] attach={ids}")

        resolver = CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND))
        resolution = await resolver.resolve(
            intent=ResolutionIntent.extract, project_id=target.project_id,
            wp_id=target.wp_id, entry_id=ENTRY_ID,
        )
        active = await _active_definition_evidence(session, resolution, registry.resolve_for_entry(ENTRY_ID).contract)
        oo_info = _onlyoffice_version()
        print(
            f"[②] generation={resolution.representation_generation} substrate={resolution.artifact_path.name} "
            f"bundle={str(resolution.bundle.bundle_id)[:8]} OO={oo_info['version']}"
        )
        ctx = {
            "registration": registry.resolve_for_entry(ENTRY_ID), "resolver": resolver,
            "project_id": target.project_id, "wp_id": target.wp_id,
            "substrate": resolution.artifact_path,
        }
        defaults = _frontend_skeleton()
        print("[第一轮] 前端真实骨架（金额全 0，只验结构）")
        err = await _one_round("R1", _rows(defaults, with_amounts=False), {**ctx, "check_values": False})
        if err:
            print(f"[R1] ❌ {err}")
            return 1
        print("[第二轮] 合成带金额载荷（验 G=ROUND(D*F,2) 与 I=G-H）")
        err = await _one_round("R2", _rows(defaults, with_amounts=True), {**ctx, "check_values": True})
        if err:
            print(f"[R2] ❌ {err}")
            return 1

        after = await _j_digest(session)
        if after != before:
            print(f"[⑨] ❌ J1-% 快照变化 {before} → {after}")
            return 1
        print(f"[⑨] J1-% {after[0]} 行快照 digest 不变（本脚本未写库）")

        db_fingerprint = (
            await session.execute(
                sa.text(
                    "SELECT current_database(), current_setting('server_version'), "
                    "pg_postmaster_start_time()::text"
                )
            )
        ).one()
        evidence = {
            "schema_version": "j1-oo94-evidence:v1",
            "status": "passed",
            "source_commit": _git_commit(),
            "source_digest": _source_digest(),
            "source_files": list(EVIDENCE_SOURCE_FILES),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "database": {
                "name": db_fingerprint[0],
                "server_version": db_fingerprint[1],
                "postmaster_started_at": db_fingerprint[2],
            },
            "project_id": str(project_id),
            "wp_id": str(wp_id),
            "wp_code": "J1",
            "entry_id": ENTRY_ID,
            "active": active,
            "onlyoffice": oo_info,
            "rounds": ["frontend_skeleton_19_rows", "frontend_payload_with_amounts_19_rows"],
            "store_snapshot": {"row_count": after[0], "sha256": after[1], "unchanged": True},
            "legacy_identity_mutation_enabled": os.environ.get("J1_RT_LEGACY_IDS") == "1",
        }
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes((json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        print(f"[evidence] {evidence_path}")

    print("✅ J1 真 OO 引擎两轮往返全绿（HTML→OO→HTML）")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True, type=uuid.UUID)
    parser.add_argument("--wp-id", required=True, type=uuid.UUID)
    parser.add_argument(
        "--evidence",
        default=str(_REPO / ".kiro/specs/j1-post-publish-semantic-and-evidence-closure/evidence/oo94.json"),
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(project_id=args.project_id, wp_id=args.wp_id, evidence_path=Path(args.evidence))))
