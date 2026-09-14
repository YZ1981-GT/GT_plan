"""自定义底稿（componentType=custom）真实库验收 —— 只读为主，写路径默认 dry-run。

spec: custom-workpaper-dual-mode-formula-and-batch Task 25（R11.5）

用法::

    python backend/scripts/diagnose/verify_custom_workpaper_live.py            # 只读
    python backend/scripts/diagnose/verify_custom_workpaper_live.py --apply    # 真跑写路径并复原

🔴 设计红线（平台既有铁律，逐条都踩过）：

1. **诚实输出 `UNVERIFIABLE`** —— 库里没有 custom 底稿时如实报「不可验证」，
   **禁用 fixture 冒充真实库**（`verify_parent_company_note_live.py` 范式）。
2. **JSONB 复原必须赋 dict**，不能赋 `json.dumps(...)`：后者会把列写成
   **JSON 字符串标量**（`jsonb_typeof` 变 `string`），下游 `->>` / `? 'k'` 全失效，
   而脚本会自报「已复原」。复原后必须用 `jsonb_typeof` + `md5(col::text)` 双证。
3. **控制台禁 emoji**（Windows GBK `UnicodeEncodeError` 会在写盘之后炸，
   造成「退出码非零但改动已落盘」的误判）→ 一律 `[OK]` / `[ERR]` ASCII 标记。
4. `--apply` 前先抓 **全文快照 + md5 + jsonb_typeof** 三件；只记 length 不够
   （保存操作会新增副产键，反推不出基线形态）。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import sqlalchemy as sa  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []  # (status, check, detail)


def rec(status: str, check: str, detail: str = "") -> None:
    RESULTS.append((status, check, detail))


def _md5(v) -> str:
    return hashlib.md5(json.dumps(v, sort_keys=True, default=str).encode()).hexdigest()



async def _create_probe_wp(db) -> dict | None:
    """真实创建一个探针 custom 底稿（走生产路径 `_create_one_custom_workpaper`）。

    🔴 编号带时间戳前缀避免与真实底稿撞号；验证完毕由 `_cleanup_probe` 彻底删除
    （软删两表 + 删 xlsx 文件），不留残留。
    """
    import uuid as _uuid
    from datetime import datetime

    from app.routers.wp_template import _create_one_custom_workpaper

    pid = (
        await db.execute(
            sa.text(
                "SELECT id FROM projects WHERE is_deleted = false "
                "ORDER BY created_at DESC LIMIT 1"
            )
        )
    ).scalar()
    if pid is None:
        rec("ERR", "无可用项目", "projects 表无未删除记录，探针无法创建")
        return None

    code = "ZZPROBE" + datetime.now().strftime("%H%M%S")
    try:
        res = await _create_one_custom_workpaper(
            db,
            project_id=pid,
            wp_code=code,
            wp_name="自定义底稿验收探针（脚本自动创建，将自动删除）",
            audit_cycle="Z",
            year=datetime.now().year,
            created_by=None,
        )
        await db.commit()
    except Exception as e:  # noqa: BLE001
        rec("ERR", "探针创建抛错", repr(e)[:300])
        await db.rollback()
        return None

    return {
        "wp_id": _uuid.UUID(res["wp_id"]),
        "wp_code": code,
        "project_id": pid,
        "file_path": res["file_path"],
    }


async def _probe_cell_write(db, probe: dict) -> None:
    """探针模式专属：验证「HTML 格编辑 → 写回 xlsx → 刷新投影」往返。"""
    from app.services.custom_workpaper_projection import (
        project_custom_workpaper,
        write_cells_to_xlsx,
    )

    fp = probe["file_path"]
    real = next(
        (p for p in (Path(fp), BACKEND / fp, BACKEND.parent / fp) if p.exists()), None
    )
    if real is None:
        rec("ERR", "探针 xlsx 文件缺失", str(fp)[:160])
        return

    target = "H30"  # 远离表头区，验证恒等坐标
    try:
        n = write_cells_to_xlsx(str(real), probe["wp_code"], {target: 123.45})
        grid = project_custom_workpaper(str(real), probe["wp_code"])
    except Exception as e:  # noqa: BLE001
        rec("ERR", "探针写回/投影抛错", repr(e)[:300])
        return

    cells = grid.get("cells") or {}
    got = cells.get(target)
    # 🔴 投影 cell 的实测结构 = {'v': 值, 'r': 行, 'c': 列, 'style': {...}}
    #    值在 `v` 键（不是 `value`）—— 判据读错键名会把「坐标恒等成立」误报成 ERR。
    #    行/列一并核：r/c 必须与目标坐标一致，才真正证明没有重编行号。
    if isinstance(got, dict):
        raw = got.get("v")
        row_ok = got.get("r") == 30
        col_ok = got.get("c") == 8  # H 列 = 第 8 列
    else:
        raw = got
        row_ok = col_ok = got is not None
    hit = raw is not None and str(raw).startswith("123.45") and row_ok and col_ok
    rec(
        "OK" if hit else "ERR",
        "恒等坐标往返（写 H30 读 H30）",
        f"written={n} keys_near_H={sorted(k for k in cells if k.startswith('H'))[:5]} value={got}",
    )
    if not hit:
        rec("ERR", "坐标不恒等", "写 H30 后 H30 读不到 —— 投影重编了行号，编辑会写坏别的格")


async def _cleanup_probe(db, probe: dict) -> None:
    """彻底删除探针底稿（软删两表 + 删 xlsx 文件）。"""
    try:
        await db.execute(
            sa.text("UPDATE working_paper SET is_deleted = true WHERE id = :i"),
            {"i": probe["wp_id"]},
        )
        await db.execute(
            sa.text(
                "UPDATE wp_index SET is_deleted = true WHERE project_id = :p "
                "AND wp_code = :c"
            ),
            {"p": probe["project_id"], "c": probe["wp_code"]},
        )
        await db.commit()
    except Exception as e:  # noqa: BLE001
        rec("ERR", "探针软删失败", repr(e)[:300])
        await db.rollback()
        return

    fp = probe["file_path"]
    for cand in (Path(fp), BACKEND / fp, BACKEND.parent / fp):
        try:
            if cand.exists():
                cand.unlink()
        except Exception:  # noqa: BLE001
            pass

    left = (
        await db.execute(
            sa.text(
                "SELECT count(*) FROM wp_index WHERE project_id = :p "
                "AND wp_code = :c AND is_deleted = false"
            ),
            {"p": probe["project_id"], "c": probe["wp_code"]},
        )
    ).scalar()
    file_left = any(
        p.exists() for p in (Path(fp), BACKEND / fp, BACKEND.parent / fp)
    )
    rec(
        "OK" if left == 0 and not file_left else "ERR",
        "探针已彻底清理",
        f"active_wp_index={left} file_left={file_left}",
    )


async def _all(apply: bool, create_probe: bool = False) -> None:
    from app.core.database import async_session
    from app.services.custom_workpaper_context import resolve_is_custom
    from app.services.custom_workpaper_projection import (
        grid_has_content,
        project_custom_workpaper,
    )

    async with async_session() as db:
        # ── 1. 找出真实的 custom 底稿 ────────────────────────────────────────
        # custom 判定不是列而是派生：`source_type == manual` 且编号不像标准编号。
        rows = (
            await db.execute(
                sa.text(
                    """
                    SELECT wp.id AS wp_id, wp.project_id, wp.file_path,
                           wp.status AS file_status, wi.wp_code, wi.wp_name,
                           jsonb_typeof(wp.parsed_data) AS pd_type,
                           length(wp.parsed_data::text) AS pd_len
                    FROM working_paper wp
                    JOIN wp_index wi ON wi.id = wp.wp_index_id
                    WHERE wp.is_deleted = false
                      AND wi.is_deleted = false
                      AND wp.source_type = 'manual'
                    ORDER BY wp.created_at DESC
                    LIMIT 50
                    """
                )
            )
        ).mappings().all()

        rec("INFO", "manual 底稿候选数", str(len(rows)))
        if not rows and not create_probe:
            rec("UNVERIFIABLE", "库中无 source_type=manual 底稿",
                "无法验证 custom 链路；禁用 fixture 冒充真实库。"
                "可加 --create-probe --confirm 真实创建探针底稿走完整链路后彻底删除")
            return

        probe_ids: dict | None = None
        if not rows and create_probe:
            probe_ids = await _create_probe_wp(db)
            if probe_ids is None:
                rec("UNVERIFIABLE", "探针底稿创建失败", "见上条 ERR")
                return
            rows = (
                await db.execute(
                    sa.text(
                        """
                        SELECT wp.id AS wp_id, wp.project_id, wp.file_path,
                               wp.status AS file_status, wi.wp_code, wi.wp_name,
                               jsonb_typeof(wp.parsed_data) AS pd_type,
                               length(wp.parsed_data::text) AS pd_len
                        FROM working_paper wp
                        JOIN wp_index wi ON wi.id = wp.wp_index_id
                        WHERE wp.id = :i
                        """
                    ),
                    {"i": probe_ids["wp_id"]},
                )
            ).mappings().all()
            rec("OK", "探针底稿已创建", f"wp_code={probe_ids['wp_code']}")

        customs = []
        for r in rows:
            wp = (
                await db.execute(
                    sa.text("SELECT * FROM working_paper WHERE id = :i"),
                    {"i": r["wp_id"]},
                )
            ).mappings().first()
            try:
                is_custom = await resolve_is_custom(db, wp, r["wp_code"])
            except Exception as e:  # noqa: BLE001
                rec("ERR", f"resolve_is_custom({r['wp_code']}) 抛错", repr(e)[:200])
                continue
            if is_custom:
                customs.append(r)

        rec("INFO", "判定为 custom 的底稿数", str(len(customs)))
        if not customs:
            rec(
                "UNVERIFIABLE",
                "库中无 componentType=custom 底稿",
                "resolve_is_custom 全部返 False（可能都是标准编号）；"
                "投影/公式/导出/批量四条链路无法在真实库验证",
            )
            return

        # ── 2. 投影可见性（R1：网格不得恒显示「暂无内容」）────────────────
        empty_grid = []
        for r in customs:
            pd = (
                await db.execute(
                    sa.text("SELECT parsed_data FROM working_paper WHERE id = :i"),
                    {"i": r["wp_id"]},
                )
            ).scalar()
            html = (pd or {}).get("html_data") or {}
            sheet = html.get(r["wp_code"]) or {}
            has = grid_has_content(sheet) if sheet else False
            if not has:
                empty_grid.append(r["wp_code"])
        if empty_grid:
            rec("WARN", "投影为空的 custom 底稿", ",".join(empty_grid[:10]))
        else:
            rec("OK", "全部 custom 底稿投影非空", f"n={len(customs)}")

        # ── 3. 恒等坐标（R1.2：xlsx 坐标 == cells 键，不重编行号）────────
        checked = 0
        for r in customs[:5]:
            fp = r["file_path"]
            cand = [Path(fp), BACKEND / fp, BACKEND.parent / fp]
            real = next((p for p in cand if p.exists()), None)
            if real is None:
                rec("WARN", f"{r['wp_code']} xlsx 文件缺失", str(fp)[:120])
                continue
            try:
                grid = project_custom_workpaper(str(real), r["wp_code"])
            except Exception as e:  # noqa: BLE001
                rec("ERR", f"{r['wp_code']} 恒等投影抛错", repr(e)[:200])
                continue
            hr = grid.get("header_rows")
            if hr not in (0, None):
                rec("ERR", f"{r['wp_code']} header_rows != 0",
                    f"恒等投影不得剥表头，实测 {hr}")
            else:
                checked += 1
        rec("OK" if checked else "WARN", "恒等坐标投影可复算", f"n={checked}")

        # ── 4. 公式双写（R6：wp_formula 行的值必须也写进 xlsx）───────────
        frows = (
            await db.execute(
                sa.text(
                    """
                    SELECT f.wp_id, f.sheet_name, f.target_cell, f.formula_type,
                           f.lifecycle_state, f.last_computed_at
                    FROM wp_formula f
                    WHERE f.wp_id = ANY(:ids)
                    """
                ),
                {"ids": [r["wp_id"] for r in customs]},
            )
        ).mappings().all()
        if not frows:
            rec("UNVERIFIABLE", "custom 底稿上无 wp_formula 行",
                "「公式值双写 xlsx」无法在真实库验证（wp_formula 全库可能 0 行）")
        else:
            rec("OK", "custom 底稿公式行数", str(len(frows)))

        # ── 5. 导出路径（R7：读 xlsx 本体，不调 load_schema）──────────────
        from app.services.custom_workpaper_export import (
            CustomExportError,
            export_custom_workpaper,
        )

        ok_exp = 0
        for r in customs[:3]:
            wp = (
                await db.execute(
                    sa.text("SELECT * FROM working_paper WHERE id = :i"),
                    {"i": r["wp_id"]},
                )
            ).mappings().first()

            class _WP:  # 轻量替身：导出只用到 file_path
                file_path = wp["file_path"]

            try:
                buf = export_custom_workpaper(_WP())
                n = len(buf.getvalue())
                if n < 1000:
                    rec("ERR", f"{r['wp_code']} 导出体积过小", f"{n} bytes（疑似空白 workbook）")
                else:
                    ok_exp += 1
            except CustomExportError as e:
                rec("WARN", f"{r['wp_code']} 导出抛 CustomExportError", str(e)[:160])
            except Exception as e:  # noqa: BLE001
                rec("ERR", f"{r['wp_code']} 导出抛未预期异常", repr(e)[:200])
        rec("OK" if ok_exp else "WARN", "custom 导出可产出非空 xlsx", f"n={ok_exp}")

        # ── 6. 批量预览只读（Property 11）─────────────────────────────────
        pid = customs[0]["project_id"]
        before = (
            await db.execute(
                sa.text(
                    "SELECT (SELECT count(*) FROM wp_index WHERE project_id=:p) AS wi,"
                    " (SELECT count(*) FROM working_paper WHERE project_id=:p) AS wp"
                ),
                {"p": pid},
            )
        ).mappings().first()

        from app.routers.wp_template import _custom_code_exists

        probe = await _custom_code_exists(db, pid, "__NO_SUCH_CODE__")
        after = (
            await db.execute(
                sa.text(
                    "SELECT (SELECT count(*) FROM wp_index WHERE project_id=:p) AS wi,"
                    " (SELECT count(*) FROM working_paper WHERE project_id=:p) AS wp"
                ),
                {"p": pid},
            )
        ).mappings().first()
        if dict(before) == dict(after) and probe is False:
            rec("OK", "重号探测只读且不误报", f"wi={before['wi']} wp={before['wp']}")
        else:
            rec("ERR", "重号探测改变了行数", f"{dict(before)} -> {dict(after)}")

        # ── 7. 写路径（默认 dry-run）──────────────────────────────────────
        if probe_ids is not None:
            # 探针模式：额外验证单元格写回，然后彻底删除
            await _probe_cell_write(db, probe_ids)
            await _cleanup_probe(db, probe_ids)

        if not apply:
            rec("SKIP", "写路径（单元格编辑 + 投影刷新）", "未传 --apply，跳过")
            return

        target = customs[0]
        wp_obj = (
            await db.execute(
                sa.text("SELECT parsed_data FROM working_paper WHERE id = :i"),
                {"i": target["wp_id"]},
            )
        ).mappings().first()
        snap = wp_obj["parsed_data"]
        snap_md5 = _md5(snap)
        pd_type = (
            await db.execute(
                sa.text(
                    "SELECT jsonb_typeof(parsed_data) FROM working_paper WHERE id=:i"
                ),
                {"i": target["wp_id"]},
            )
        ).scalar()
        rec("INFO", "写路径基线", f"md5={snap_md5[:12]} jsonb_typeof={pd_type}")

        try:
            from app.services.custom_workpaper_projection import (
                refresh_custom_projection,
            )
            from app.models.workpaper_models import WorkingPaper

            orm = (
                await db.execute(
                    sa.select(WorkingPaper).where(WorkingPaper.id == target["wp_id"])
                )
            ).scalar_one()
            refresh_custom_projection(orm, target["wp_code"])
            await db.flush()
            new_type = (
                await db.execute(
                    sa.text(
                        "SELECT jsonb_typeof(parsed_data) FROM working_paper WHERE id=:i"
                    ),
                    {"i": target["wp_id"]},
                )
            ).scalar()
            rec(
                "OK" if new_type == "object" else "ERR",
                "投影刷新后 jsonb_typeof",
                f"{new_type}（必须是 object，写成 string 说明赋了 json.dumps）",
            )
        finally:
            # 🔴 复原赋 **dict** 不赋 json.dumps
            await db.execute(
                sa.text(
                    "UPDATE working_paper SET parsed_data = CAST(:v AS jsonb) WHERE id=:i"
                ),
                {"v": json.dumps(snap, default=str) if snap is not None else None,
                 "i": target["wp_id"]},
            )
            await db.commit()
            back = (
                await db.execute(
                    sa.text("SELECT parsed_data, jsonb_typeof(parsed_data) AS t "
                            "FROM working_paper WHERE id=:i"),
                    {"i": target["wp_id"]},
                )
            ).mappings().first()
            same = _md5(back["parsed_data"]) == snap_md5
            rec(
                "OK" if same and back["t"] == pd_type else "ERR",
                "写路径数据已复原",
                f"md5_equal={same} typeof={back['t']}（基线 {pd_type}）",
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真跑写路径并自动复原")
    ap.add_argument(
        "--create-probe",
        action="store_true",
        help="库中无 custom 底稿时，真实创建一个探针底稿走完全链再彻底删除（需 --confirm）",
    )
    ap.add_argument("--confirm", action="store_true", help="确认执行写库动作")
    args = ap.parse_args()
    if args.create_probe and not args.confirm:
        print("[ERR] --create-probe is destructive; pass --confirm to proceed")
        return 1

    try:
        asyncio.run(_all(args.apply, args.create_probe))
    except Exception as e:  # noqa: BLE001
        rec("ERR", "脚本自身异常", repr(e)[:400])

    width = max((len(c) for _, c, _ in RESULTS), default=10)
    lines = ["=== custom workpaper live verification ==="]
    for st, chk, det in RESULTS:
        lines.append(f"[{st:<12}] {chk:<{width}}  {det}")
    counts: dict[str, int] = {}
    for st, _, _ in RESULTS:
        counts[st] = counts.get(st, 0) + 1
    lines.append("--- summary: " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    verdict = "FAIL" if counts.get("ERR") else (
        "UNVERIFIABLE" if counts.get("UNVERIFIABLE") else "PASS"
    )
    lines.append(f"VERDICT={verdict}")

    text = "\n".join(lines)
    out = Path(__file__).resolve().parent / "verify_custom_workpaper_live_out.txt"
    out.write_text(text, encoding="utf-8")
    # ASCII-safe 控制台输出（GBK 环境禁 emoji）
    print(text.encode("ascii", "replace").decode("ascii"))
    return 0 if verdict != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
