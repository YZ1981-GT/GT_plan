# -*- coding: utf-8 -*-
"""公式管理全量门禁 —— 运行时权威分母枚举 + 幂等输出 + 漂移 --check 门。

spec: formula-manager-closure · Task 8.1 · 需求 12.1 / 12.4 / 12.6
design 锚点: ADR-FMC-08、§7.1（运行时权威分母）、§7.4（幂等输出，防永红，铁律㉗）

═══ 这个脚本产出什么 ═══

§7.1 要求门禁先通过**项目 API 枚举全部可访问 `working_paper`**，逐张 GET render-config，
展开「每个真实 sheet + whole_workbook + redirect」，形成**运行时权威分母**；每项记录
``project_id / wp_id / wp_code / sheet_uid / sheet_code / host / componentType``。

本脚本是该分母的单一真源枚举器：
  1. 从真库枚举未软删项目下的未软删 ``working_paper``（JOIN ``wp_index`` 取 ``wp_code``）。
  2. 每张底稿经 render-config 实现（``_get_render_config_impl``，与 HTTP 端点同一实现，
     只是绕过 HTTP 鉴权——分母枚举是只读内省，不是越权）在进程内展开其真实 sheet；
     redirect 底稿（如 B15）标 ``redirect=true``；无 sheet 的整册页标 ``whole_workbook``。
  3. 对每项用 ``wp_code_overrides.json`` 的运行时映射解析 ``componentType``。
  4. 判「口径外」404 与 redirect 项经 `gate_exemptions.exempted_keys()` 校验通过者
     **从非 redirect 分母剔除**并登记理由（§7.3，Task 2.2/2.3 产物复用）。
  5. 输出**幂等** JSON 分母矩阵（§7.4①：内容不变不改时间戳、排序稳定、无机器名/绝对路径）。

═══ §7.4 幂等三条（防永红，铁律㉗）═══

① **内容不变不改时间戳**：JSON 的 ``generated_at`` 只在**分母内容指纹变化**时更新；指纹不变
   则沿用磁盘上旧 ``generated_at``（照 `disclosure-payload` T29 教训：每次写 now() 的产物 +
   `git diff` 判据必然恒红、门禁被忽略）。排序稳定（分母项按稳定键排序）、无绝对路径/机器名。
② **沿用 `--check` 约定**：``--check`` 比对磁盘 JSON 与现算指纹，漂移则 **exit 2** 并点名
   新增/缺失项；**不用** ``--write`` 后 ``git diff``（后者因时间戳每次必 diff → 恒红）。
③ 子进程编码交给调用方（门禁 spec 设 ``PYTHONIOENCODING=utf-8`` + ``errors='replace'`` 且
   断言 stdout 含预期内容）；本脚本把 stdout/stderr reconfigure 为 utf-8，中文信息能稳定输出。

═══ DB 可达性（如实，不假绿）═══

render-config 实现需要真库 + 渲染流水线。真库不可达时本脚本**不假装分母为空且绿**：
``--check`` 在拿不到真库时 exit 3（``db_unavailable``，区别于漂移 exit 2 / 通过 exit 0），
门禁 spec 据此跳过「需真库的运行时断言」并如实标注（而非当成通过）。

用法：
  现算并写盘（取基线/刷新分母）：  python backend/scripts/check/check_formula_manager_all_pages_denominator.py --write
  漂移门（CI / 门禁子进程）：       python backend/scripts/check/check_formula_manager_all_pages_denominator.py --check
  只打印 JSON（不写盘）：           python backend/scripts/check/check_formula_manager_all_pages_denominator.py --json

分母 JSON 落 ``backend/data/formula_manager_all_pages_denominator.json``（随代码入库）。
自测 / 门禁复用见 ``audit-platform/frontend/src/components/formula/__tests__/
formula-manager-all-accessible-pages.spec.ts``。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_DENOMINATOR_PATH = _BACKEND / "app" / "data" / "formula_manager_all_pages_denominator.json"

#: 退出码约定（§7.4②）。
EXIT_OK = 0           # --check 通过（磁盘分母与现算一致）
EXIT_DRIFT = 2        # --check 漂移（分母内容变化，点名新增/缺失）
EXIT_DB_UNAVAILABLE = 3  # 真库不可达（如实标 db_unavailable，不假绿）


# ───────────────────────── 分母项数据结构 ─────────────────────────


def _item_key(item: dict[str, Any]) -> str:
    """分母项的稳定排序/去重键（project_id + wp_id + sheet_uid + host）。

    稳定键不含时间戳/随机值，保证同输入排序稳定（§7.4①）。
    """
    return "\u0001".join(
        (
            str(item.get("project_id", "")),
            str(item.get("wp_id", "")),
            str(item.get("sheet_uid", "")),
            str(item.get("host", "")),
        )
    )


def _canonical_fingerprint(items: list[dict[str, Any]]) -> str:
    """分母**内容指纹**：对排序后的分母项取 canonical JSON 的 sha256。

    指纹刻意**不含** generated_at / 机器名 / 绝对路径 —— 只覆盖分母的实质内容
    （每项的 project_id/wp_id/wp_code/sheet_uid/sheet_code/host/componentType/
    redirect/exempted/exempt_reason）。指纹不变 ⇒ 内容未变 ⇒ 不改时间戳（§7.4①）。
    """
    stable = sorted(items, key=_item_key)
    text = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
    """把一个原始分母项归一为**稳定键序**的 dict（字段齐全、禁绝对路径/机器名）。"""
    return {
        "project_id": str(raw.get("project_id", "")),
        "wp_id": str(raw.get("wp_id", "")),
        "wp_code": str(raw.get("wp_code", "")),
        "sheet_uid": str(raw.get("sheet_uid", "")),
        "sheet_code": str(raw.get("sheet_code", "")),
        "host": str(raw.get("host", "")),
        "component_type": str(raw.get("component_type", "")),
        "redirect": bool(raw.get("redirect", False)),
        # 经豁免登记校验通过而从非 redirect 分母剔除的项（redirect / 口径外 404）。
        "exempted": bool(raw.get("exempted", False)),
        "exempt_key": str(raw.get("exempt_key", "")),
        "render_config_resolved": bool(raw.get("render_config_resolved", False)),
    }


# ───────────────────────── 真库枚举（§7.1）─────────────────────────


async def _enumerate_from_db() -> list[dict[str, Any]]:
    """从真库枚举可访问 working_paper → render-config 展开运行时权威分母。

    真库不可达 / 渲染流水线不可用时抛异常（由 run() 捕获判 db_unavailable）。
    """
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    os.environ.setdefault("DB_DISABLE_SSL", "True")

    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.services.wp_code_override_loader import load_wp_code_overrides

    url = str(settings.DATABASE_URL)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    overrides = load_wp_code_overrides()
    engine = create_async_engine(url, poolclass=NullPool, echo=False)
    items: list[dict[str, Any]] = []
    try:
        from app.models.core import User as _User

        # ① 枚举未软删项目下未软删底稿（JOIN wp_index 取 wp_code）+ 取 admin 用户。
        async with AsyncSession(engine) as session:
            admin = (
                await session.execute(
                    sa.select(_User).where(_User.role == "admin").limit(1)
                )
            ).scalars().first()
            if admin is None:
                admin = (await session.execute(sa.select(_User).limit(1))).scalars().first()
            # render-config 实现只读 current_user.id（§1 实测：固化 _user_id = current_user.id
            # 作审计摘要，读路径不写库）。用轻量 shim 携带 id，避免 ORM 对象跨 session 过期。
            from types import SimpleNamespace

            admin_user = SimpleNamespace(id=getattr(admin, "id", None)) if admin else None

            rows = (
                await session.execute(
                    sa.text(
                        """
                        SELECT wp.id AS wp_id, wp.project_id AS project_id,
                               wi.wp_code AS wp_code
                        FROM working_paper wp
                        JOIN wp_index wi ON wi.id = wp.wp_index_id
                        JOIN projects p ON p.id = wp.project_id
                        WHERE wp.is_deleted = false
                          AND wi.is_deleted = false
                          AND p.is_deleted = false
                        ORDER BY wp.project_id, wi.wp_code
                        """
                    )
                )
            ).all()
            catalog = [(str(r.wp_id), str(r.project_id), str(r.wp_code or "")) for r in rows]

        # ② 每张底稿用**独立 session** 展开 render-config。
        #    🔴 为什么一 wp 一 session：真库存在 `wp_file_status` 枚举漂移（status='completed'
        #    不在枚举内），render-config 内的 auto_data_source 查询会抛 asyncpg 错误并**使整个
        #    事务 aborted**（PG：事务内首条失败后，后续所有语句报 "current transaction is
        #    aborted"）。共用一个 session 会让第一张出错底稿之后的所有底稿连带全挂（只解析出 1
        #    张）。独立 session 把故障隔离到单张 ⇒ 其余底稿照常展开。这不掩盖枚举漂移（单张
        #    仍标 render_config_resolved=false），只避免一张的 DB 层缺陷污染整个分母。
        for wp_id, project_id, wp_code in catalog:
            component_type = overrides.get(wp_code, "")
            try:
                async with AsyncSession(engine) as wp_session:
                    page_items = await _expand_render_config(
                        wp_session, wp_id, project_id, wp_code, component_type, admin_user
                    )
            except Exception:
                page_items = [
                    _normalize_item(
                        {
                            "project_id": project_id,
                            "wp_id": wp_id,
                            "wp_code": wp_code,
                            "component_type": component_type,
                            "host": "html",
                            "sheet_uid": "",
                            "sheet_code": "",
                            "render_config_resolved": False,
                        }
                    )
                ]
            items.extend(page_items)
    finally:
        await engine.dispose()

    return items


async def _expand_render_config(
    session: Any,
    wp_id: str,
    project_id: str,
    wp_code: str,
    component_type: str,
    current_user: Any,
) -> list[dict[str, Any]]:
    """对单张底稿调 render-config 实现，展开 sheet / whole_workbook / redirect。

    render-config 解析失败时**不静默丢**该底稿——以 whole_workbook 兜底 +
    ``render_config_resolved=false`` 如实标注（分母仍收录，门禁可见该项未能真跑）。
    """
    from uuid import UUID

    base = {
        "project_id": project_id,
        "wp_id": wp_id,
        "wp_code": wp_code,
        "component_type": component_type,
        "host": "html",
    }

    try:
        from app.routers.wp_render_config import _get_render_config_impl

        # 分母枚举用系统视角只读内省：传真实 admin current_user（实现只读其 .id 作审计摘要，
        # 读路径不写库）。渲染失败由 except 兜底（如实标 render_config_resolved=false）。
        result = await _get_render_config_impl(UUID(wp_id), None, session, current_user)
    except Exception:
        return [
            _normalize_item(
                {
                    **base,
                    "sheet_uid": "",
                    "sheet_code": "",
                    "redirect": False,
                    "render_config_resolved": False,
                }
            )
        ]

    if not isinstance(result, dict):
        return [
            _normalize_item({**base, "sheet_uid": "", "sheet_code": "", "render_config_resolved": False})
        ]

    # redirect 底稿（如 B15）：render-config 标 redirect。
    if result.get("redirect") or result.get("redirect_to") or result.get("redirectTo"):
        return [
            _normalize_item(
                {
                    **base,
                    "sheet_uid": "",
                    "sheet_code": "",
                    "redirect": True,
                    "render_config_resolved": True,
                }
            )
        ]

    sheets = result.get("sheets") if isinstance(result.get("sheets"), list) else []
    if not sheets:
        # 无真实 sheet：整册页。
        return [
            _normalize_item(
                {
                    **base,
                    "sheet_uid": "whole_workbook",
                    "sheet_code": "",
                    "render_config_resolved": True,
                }
            )
        ]

    out: list[dict[str, Any]] = []
    for sh in sheets:
        if not isinstance(sh, dict):
            continue
        sheet_uid = str(sh.get("sheet_name") or sh.get("sheetName") or sh.get("sheet_code") or "")
        sheet_code = str(sh.get("sheet_code") or sh.get("sheetCode") or "")
        ct = str(sh.get("componentType") or sh.get("component_type") or component_type)
        out.append(
            _normalize_item(
                {
                    **base,
                    "component_type": ct,
                    "sheet_uid": sheet_uid,
                    "sheet_code": sheet_code,
                    "render_config_resolved": True,
                }
            )
        )
    return out


# ───────────────────────── 豁免登记剔除（§7.3）─────────────────────────


def _apply_exemptions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """用 gate_exemptions.exempted_keys() 把 redirect / 口径外 404 项标 exempted。

    复用 Task 2.2 / 2.3 的 ``formula_manager_gate_exemptions.json`` +
    ``gate_exemptions``（可伪证 + 防空转）。只把**校验通过**的 key 对应项从非
    redirect 分母剔除（标 exempted=true 并记 exempt_key）。
    """
    from app.services.formula_management.gate_exemptions import exempted_keys

    valid = exempted_keys()  # 校验通过的 key 集合（redirect-materiality / classification-404-...:X）

    for it in items:
        wp_code = it.get("wp_code", "")
        # redirect 底稿：key = redirect-materiality（B15 口径；可伪证字段比对运行时 override）。
        if it.get("redirect"):
            # 门禁豁免 key 按 wp_code 对齐（B15 → redirect-materiality）。
            if "redirect-materiality" in valid and wp_code == "B15":
                it["exempted"] = True
                it["exempt_key"] = "redirect-materiality"
            continue
        # 口径外 404：key = classification-404-out-of-scope:{wp_code}。
        key = f"classification-404-out-of-scope:{wp_code}"
        if key in valid:
            it["exempted"] = True
            it["exempt_key"] = key

    return items


# ───────────────────────── 分母组装 / 读写（§7.4①）─────────────────────────


def compute_denominator() -> tuple[list[dict[str, Any]], str | None]:
    """现算运行时权威分母。返回 (排序后的分母项, 失败原因或 None)。

    真库不可达 → 返回 ([], "db_unavailable")（如实，不假绿）。
    """
    try:
        raw = asyncio.run(_enumerate_from_db())
    except Exception as exc:  # noqa: BLE001
        return [], f"db_unavailable: {type(exc).__name__}: {exc}"

    try:
        raw = _apply_exemptions(raw)
    except Exception as exc:  # noqa: BLE001
        return [], f"exemption_error: {type(exc).__name__}: {exc}"

    items = sorted((_normalize_item(r) for r in raw), key=_item_key)
    return items, None


def load_existing() -> dict[str, Any] | None:
    if not _DENOMINATOR_PATH.exists():
        return None
    try:
        with open(_DENOMINATOR_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def build_document(items: list[dict[str, Any]], prev: dict[str, Any] | None) -> dict[str, Any]:
    """组装幂等文档：指纹不变则沿用旧 generated_at（§7.4①）。"""
    from datetime import datetime, timezone

    fingerprint = _canonical_fingerprint(items)
    prev_fp = (prev or {}).get("fingerprint")
    prev_at = (prev or {}).get("generated_at")

    if prev is not None and prev_fp == fingerprint and prev_at:
        generated_at = prev_at  # 内容未变 → 不改时间戳（防恒 diff / 恒红）
    else:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    non_redirect = [i for i in items if not i["redirect"] and not i["exempted"]]
    return {
        "_doc": (
            "公式管理全量门禁的运行时权威分母（Task 8.1 / §7.1）。每项 = 一张底稿的一个"
            "真实 sheet / whole_workbook / redirect。redirect 与校验通过的口径外 404 标"
            " exempted=true 并记 exempt_key（经 gate_exemptions 可伪证校验剔除）。"
            "本文件幂等：内容指纹不变则不改 generated_at（§7.4①，禁恒 diff）。禁写死计数、"
            "交付期须重扫。"
        ),
        "schema_version": 1,
        "generated_at": generated_at,
        "fingerprint": fingerprint,
        "counts": {
            "total": len(items),
            "redirect": sum(1 for i in items if i["redirect"]),
            "exempted": sum(1 for i in items if i["exempted"]),
            "non_redirect_in_scope": len(non_redirect),
            "render_config_resolved": sum(1 for i in items if i["render_config_resolved"]),
        },
        "items": items,
    }


def write_document(doc: dict[str, Any]) -> None:
    text = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False)
    _DENOMINATOR_PATH.write_text(text + "\n", encoding="utf-8")


# ───────────────────────── 漂移比对（--check，§7.4②）─────────────────────────


def diff_items(
    disk_items: list[dict[str, Any]], live_items: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """返回 (新增项键, 缺失项键)。用稳定键比对。"""
    disk_keys = {_item_key(i) for i in disk_items}
    live_keys = {_item_key(i) for i in live_items}
    added = sorted(live_keys - disk_keys)
    removed = sorted(disk_keys - live_keys)
    return added, removed


# ───────────────────────── main（退出码约定）─────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="公式管理全量门禁运行时分母枚举 + 漂移门")
    ap.add_argument("--write", action="store_true", help="现算并写盘（刷新分母）")
    ap.add_argument("--check", action="store_true", help="漂移门：磁盘 vs 现算，漂移 exit 2")
    ap.add_argument("--json", action="store_true", help="只打印 JSON 文档（不写盘）")
    args = ap.parse_args(argv)

    items, failure = compute_denominator()

    if failure is not None:
        # 真库不可达：如实报，不假绿。--check 返 EXIT_DB_UNAVAILABLE（区别于通过/漂移）。
        print(f"[DB_UNAVAILABLE] 运行时分母无法枚举：{failure}", file=sys.stderr)
        print(
            "[DB_UNAVAILABLE] 运行时权威分母需真库 + 渲染流水线（start-dev / PG）。"
            "未假装分母为空且绿——门禁据此跳过需真库的运行时断言并如实标注。"
        )
        if args.check:
            return EXIT_DB_UNAVAILABLE
        # --write / --json 在无库时不覆盖已有磁盘分母（避免把真分母清空）。
        prev = load_existing()
        if prev is not None:
            print("[DB_UNAVAILABLE] 保留磁盘上已有分母，不覆盖。")
        return EXIT_DB_UNAVAILABLE

    prev = load_existing()
    doc = build_document(items, prev)

    if args.check:
        if prev is None:
            print(
                "[DRIFT] 磁盘分母缺失（formula_manager_all_pages_denominator.json 不存在），"
                "请先 --write 取基线。",
                file=sys.stderr,
            )
            return EXIT_DRIFT
        disk_items = [_normalize_item(i) for i in (prev.get("items") or [])]
        added, removed = diff_items(disk_items, items)
        if added or removed:
            print("[DRIFT] 运行时分母与磁盘基线不一致：", file=sys.stderr)
            for k in added:
                print(f"  + 新增项: {k.replace(chr(1), ' | ')}", file=sys.stderr)
            for k in removed:
                print(f"  - 缺失项: {k.replace(chr(1), ' | ')}", file=sys.stderr)
            print(
                "[DRIFT] 分母任何新增/缺失须有对应承接（新页入门禁 / 下线页更新基线）。"
                "确认无误后 --write 刷新基线。",
                file=sys.stderr,
            )
            return EXIT_DRIFT
        print(
            f"[OK] 运行时分母与磁盘基线一致：total={doc['counts']['total']}、"
            f"non_redirect_in_scope={doc['counts']['non_redirect_in_scope']}、"
            f"redirect={doc['counts']['redirect']}、exempted={doc['counts']['exempted']}。"
        )
        return EXIT_OK

    if args.write:
        write_document(doc)
        print(
            f"[WRITE] 已写盘运行时分母：total={doc['counts']['total']}、"
            f"non_redirect_in_scope={doc['counts']['non_redirect_in_scope']}、"
            f"fingerprint={doc['fingerprint'][:12]}…（generated_at="
            f"{'沿用旧值' if prev and prev.get('fingerprint') == doc['fingerprint'] else '已更新'}）。"
        )
        return EXIT_OK

    # 默认 / --json：打印文档（不写盘）。
    print(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
