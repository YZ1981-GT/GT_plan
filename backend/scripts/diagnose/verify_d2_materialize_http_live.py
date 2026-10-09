"""真库 D2：store-projection → pending-mutation → materialize 的 HTTP 取证。

spec: workpaper-sync-materialize-large-table-performance · Wave 4 Task 8
Requirements: 4.2, 4.3 · Property 9

用法（仓库根，**需要** 真后端；默认对齐 start-dev.bat 的 9980）::

    python backend/scripts/diagnose/verify_d2_materialize_http_live.py
    python backend/scripts/diagnose/verify_d2_materialize_http_live.py \\
        --base http://127.0.0.1:9980 \\
        --out .kiro/specs/_archive/15-workpaper-sync-engine-hardening/workpaper-sync-materialize-large-table-performance/evidence/http-materialize-live.json

（该 spec 已于 2026-09-25 归档；`--out` 无默认值，照抄旧 active 路径会 `FileNotFoundError`。）

判据：materialize 在软上限内返回带 room_id / document 的 descriptor；
数字现场实测，不手抄。失败 exit 1（无法连库/后端 → exit 2）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

ENTRY_ID = "xlsx/gt-d2-accounts-receivable"
SHEET_KEY = "d22-managed"
DEFAULT_BASE = "http://127.0.0.1:9980"


def _http(
    method: str,
    url: str,
    *,
    token: str,
    body: dict[str, Any] | None = None,
    idempotency: str | None = None,
    timeout: float = 180.0,
) -> tuple[int, dict[str, Any], float]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if idempotency is not None:
        headers["Idempotency-Key"] = idempotency
    req = Request(url, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status = int(resp.status)
    except HTTPError as exc:
        elapsed = time.perf_counter() - started
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw[:2000]}
        return int(exc.code), payload if isinstance(payload, dict) else {"raw": payload}, elapsed
    elapsed = time.perf_counter() - started
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {"raw": raw[:2000]}
    # 平台 envelope：部分端点被中间件包一层 {code,data}
    if isinstance(payload, dict) and "data" in payload and "code" in payload:
        inner = payload.get("data")
        if isinstance(inner, dict):
            return status, inner, elapsed
    return status, payload if isinstance(payload, dict) else {"raw": payload}, elapsed


async def _resolve_scope() -> dict[str, str]:
    """从真库挑一份：有 published D2 substrate + 有 D2-detail-rows 的底稿 + 可用用户。"""
    import sqlalchemy as sa
    from app.core.database import async_session

    async with async_session() as db:
        # materialize 需要 entry_state.current_representation；没有 substrate 的大表
        # 会 422 materialize_substrate_not_published —— 不能只按 remark 字节最大选。
        wp = (
            await db.execute(
                sa.text(
                    """
                    SELECT wp.id::text AS wp_id,
                           wp.project_id::text AS project_id,
                           length(cr.remark) AS remark_bytes,
                           a.relative_path AS substrate_rel,
                           a.sha256 AS substrate_sha256
                    FROM working_paper_sync_entry_state es
                    JOIN working_paper wp ON wp.id = es.wp_id
                    JOIN working_paper_content_representation r
                      ON r.id = es.current_representation_id
                    JOIN working_paper_artifact a ON a.id = r.artifact_id
                    JOIN checklist_responses cr
                      ON cr.wp_id = wp.id
                     AND cr.item_id = 'D2-detail-rows'
                    WHERE es.entry_id = 'xlsx/gt-d2-accounts-receivable'
                      AND COALESCE(wp.is_deleted, false) = false
                    ORDER BY length(cr.remark) DESC NULLS LAST
                    LIMIT 1
                    """
                )
            )
        ).mappings().first()
        if wp is None:
            raise RuntimeError(
                "真库没有「已 published D2 representation + D2-detail-rows」的 working_paper"
            )
        # 用户表列因版本而异：先探测可用列再查。
        cols = {
            str(r[0])
            for r in (
                await db.execute(
                    sa.text(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = 'users'
                        """
                    )
                )
            ).fetchall()
        }
        where = ["true"]
        if "is_deleted" in cols:
            where.append("COALESCE(is_deleted, false) = false")
        if "is_active" in cols:
            where.append("COALESCE(is_active, true) = true")
        order = "id"
        if "created_at" in cols:
            order = "created_at NULLS LAST"
        # 优先挑看起来像管理员的用户
        prefer = "true"
        prefer_bits = []
        if "role" in cols:
            prefer_bits.append("role::text ILIKE '%admin%'")
        if "username" in cols:
            prefer_bits.append("username ILIKE '%admin%'")
        if "email" in cols:
            prefer_bits.append("email ILIKE '%admin%'")
        if prefer_bits:
            prefer = "(" + " OR ".join(prefer_bits) + ")"
        user = (
            await db.execute(
                sa.text(
                    f"""
                    SELECT id::text AS user_id FROM users
                    WHERE {' AND '.join(where)}
                    ORDER BY CASE WHEN {prefer} THEN 0 ELSE 1 END, {order}
                    LIMIT 1
                    """
                )
            )
        ).mappings().first()
        if user is None:
            raise RuntimeError("真库没有可用用户可签发 token")
        return {
            "project_id": str(wp["project_id"]),
            "wp_id": str(wp["wp_id"]),
            "user_id": str(user["user_id"]),
            "remark_bytes": str(wp["remark_bytes"] or 0),
            "substrate_rel": str(wp["substrate_rel"]),
            "substrate_sha256": str(wp["substrate_sha256"]),
        }


def _err_code(body: dict[str, Any]) -> Any:
    for key in ("detail", "message"):
        nested = body.get(key)
        if isinstance(nested, dict) and nested.get("error_code"):
            return nested.get("error_code")
    return body.get("error_code")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--soft-limit",
        type=float,
        default=None,
        help="覆盖配置软上限（秒）；默认读 SyncLimits",
    )
    args = parser.parse_args(argv)

    import asyncio

    from app.core.security import create_access_token
    from app.services.workpaper_sync.limits import load_limits

    try:
        scope = asyncio.run(_resolve_scope())
    except Exception as exc:  # noqa: BLE001 - 诊断脚本要可见失败
        print(f"[http-live] cannot resolve scope from DB: {exc}", file=sys.stderr)
        return 2

    soft_limit = (
        float(args.soft_limit)
        if args.soft_limit is not None
        else float(load_limits().materialize_soft_limit_seconds)
    )
    token = create_access_token({"sub": scope["user_id"]})
    prefix = (
        f"{args.base.rstrip('/')}/api/projects/{scope['project_id']}"
        f"/workpapers/{scope['wp_id']}/sync/entries/{ENTRY_ID}"
    )

    report: dict[str, Any] = {
        "script": "verify_d2_materialize_http_live.py",
        "spec": "workpaper-sync-materialize-large-table-performance",
        "task": "Wave 4 Task 8",
        "entry_id": ENTRY_ID,
        "sheet_key": SHEET_KEY,
        "base": args.base,
        "scope": scope,
        "soft_limit_seconds": soft_limit,
        "steps": {},
    }

    # 0) health
    try:
        h_status, h_body, h_sec = _http("GET", f"{args.base.rstrip('/')}/api/health", token=token, timeout=10)
    except URLError as exc:
        print(f"[http-live] backend unreachable: {exc}", file=sys.stderr)
        return 2
    report["steps"]["health"] = {"status": h_status, "seconds": round(h_sec, 3), "body_keys": sorted(h_body)}
    if h_status != 200:
        print(f"[http-live] health={h_status}", file=sys.stderr)
        _write(args.out, report)
        return 2

    # 1) store-projection
    print("[http-live] GET store-projection …", flush=True)
    s_status, s_body, s_sec = _http("GET", f"{prefix}/store-projection", token=token, timeout=120)
    report["steps"]["store_projection"] = {
        "status": s_status,
        "seconds": round(s_sec, 3),
        "field_count": s_body.get("field_count"),
        "row_count": s_body.get("row_count"),
        "store_field_count": s_body.get("store_field_count"),
        "overlay_applied": s_body.get("overlay_applied"),
        "expected_revision": s_body.get("expected_revision"),
    }
    print(
        f"[http-live] store-projection {s_status} in {s_sec:.2f}s "
        f"fields={s_body.get('field_count')} store_fields={s_body.get('store_field_count')} "
        f"overlay={s_body.get('overlay_applied')} rows={s_body.get('row_count')}",
        flush=True,
    )
    if s_status != 200:
        _write(args.out, report)
        return 1
    values = (s_body.get("projection") or {}).get("values")
    if not isinstance(values, dict) or not values:
        report["error"] = "store-projection returned empty values"
        _write(args.out, report)
        return 1
    if s_body.get("overlay_applied") is not True:
        report["error"] = (
            "store-projection overlay_applied!=true —— 服务端未叠加 substrate 基线，"
            "纯 store 会在 materialize roundtrip 上因 GTROW 脚手架失败"
        )
        _write(args.out, report)
        return 1
    expected_revision = int(s_body["expected_revision"])
    projection = s_body["projection"]

    # pending → materialize 必须共用同一 Idempotency-Key（token 内嵌该 key）
    idem = f"d2-mat-live-{uuid.uuid4()}"
    # 2) pending-mutation
    print("[http-live] POST pending-mutations …", flush=True)
    p_body = {
        "sheet_key": SHEET_KEY,
        "expected_revision": expected_revision,
        "projection": projection,
    }
    p_status, p_resp, p_sec = _http(
        "POST",
        f"{prefix}/pending-mutations",
        token=token,
        body=p_body,
        idempotency=idem,
        timeout=120,
    )
    token_pm = p_resp.get("pending_mutation_token") or p_resp.get("pendingMutationToken")

    report["steps"]["pending_mutation"] = {
        "status": p_status,
        "seconds": round(p_sec, 3),
        "has_token": bool(token_pm),
        "error_code": _err_code(p_resp),
        "idempotency_key": idem,
    }
    print(f"[http-live] pending-mutations {p_status} in {p_sec:.2f}s", flush=True)
    if p_status != 200 or not token_pm:
        report["pending_response_keys"] = sorted(p_resp)
        report["pending_message"] = p_resp.get("message") or p_resp.get("detail")
        _write(args.out, report)
        return 1

    # 3) materialize
    print("[http-live] POST materialize …", flush=True)
    m_body = {
        "sheet_key": SHEET_KEY,
        "expected_revision": expected_revision,
        "pending_mutation_token": token_pm,
        "projection": projection,
    }
    m_status, m_resp, m_sec = _http(
        "POST",
        f"{prefix}/materialize",
        token=token,
        body=m_body,
        idempotency=idem,
        timeout=max(soft_limit + 30.0, 180.0),
    )
    descriptor_ok = bool(
        m_resp.get("room_id")
        or m_resp.get("roomId")
        or (isinstance(m_resp.get("onlyoffice_config"), dict))
        or (isinstance(m_resp.get("onlyofficeConfig"), dict))
        or (isinstance(m_resp.get("document"), dict))
        or (isinstance(m_resp.get("descriptor"), dict))
    )
    within_soft = m_sec <= soft_limit
    report["steps"]["materialize"] = {
        "status": m_status,
        "seconds": round(m_sec, 3),
        "within_soft_limit": within_soft,
        "descriptor_present": descriptor_ok,
        "response_keys": sorted(m_resp)[:40],
        "error_code": _err_code(m_resp),
        "message": m_resp.get("message"),
        "room_id": m_resp.get("room_id") or m_resp.get("roomId"),
        "idempotency_key": idem,
    }
    print(
        f"[http-live] materialize {m_status} in {m_sec:.2f}s "
        f"soft_ok={within_soft} descriptor={descriptor_ok}",
        flush=True,
    )

    passed = m_status == 200 and descriptor_ok and within_soft
    report["passed"] = passed
    report["linearity_offline_note"] = (
        "see evidence/baseline-post-wave3.json for offline linearity PASS"
    )
    _write(args.out, report)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text, flush=True)
    return 0 if passed else 1


def _write(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[http-live] wrote {path}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
