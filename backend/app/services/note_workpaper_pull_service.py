"""附注「刷新」时从底稿取数（spec note-pull-header-formula-closure R2 / ADR-2）。

附注编辑器「🔄 刷新 / 🔁 全部刷新 / 📝 生成附注」前都会调 ``pull-from-workpapers``。原先它只给已有同步指纹的
章节打标记、不取任何数（design §1 F2）。现在按项目准则（国企 / 上市）找到章节对应的底稿，执行**公式推送**：

    试算表审定数（过完调整分录） → 底稿披露项 → 附注主表

规则即公式管理「📤 公式推送」页的有效规则（可改写 / 停用、逐目标可溯源）；人工 / 锁定格保留、复核通过的底稿与
已确认的附注不改写、只作用于项目审计年度 —— 都是推送引擎既有规则，这里只是多一个触发入口。推送后对这些章节执行
附注公式（逐表合计 / 账面价值 / 用户公式，只写 auto 格）。只有披露表才有的明细（账龄、坏账、前五名……）由前端
离屏同步（``noteHeadlessDisclosure.ts``）负责，后端算不出（ADR-1）。

``pull_sections`` 只 flush 不 commit 的部分（同步指纹标记）由路由提交；推送本身经 ``run_and_commit`` 自带提交与
SSE 广播（与推送页「立即推送」同一路径，失败另记运行记录）。
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger(__name__)

#: 每个章节回报的跳过原因条数上限（提示条只放得下几条）
_REASONS_PER_SECTION = 3


def codes_by_section(variant: str, sections: list[str] | None) -> dict[str, list[str]]:
    """本准则下 章节 → 底稿编码（共用章节如 五、42 / 八、42 对应 K3 / L2 / M1 多张底稿）。

    ``sections`` 为空 = 注册表里本准则的全部章节。映射真源 = ``note_workpaper_sync_registry.json``。
    """
    from app.services.note_readiness_service import _load_registry_entries

    wanted = set(sections) if sections else None
    out: dict[str, list[str]] = defaultdict(list)
    for entry in _load_registry_entries():
        code = str(entry.get("wp_code") or "").strip()
        sec = str(entry.get(variant) or "").strip()
        if not code or not sec or (wanted is not None and sec not in wanted):
            continue
        if code not in out[sec]:
            out[sec].append(code)
    if wanted:
        for sec in wanted:
            out.setdefault(sec, [])
    return dict(out)


def _section_of(addr_id: str | None) -> str | None:
    """``note://八、5/表名/行.end`` → ``八、5``。"""
    if not addr_id or not addr_id.startswith("note://"):
        return None
    return addr_id[len("note://"):].split("/", 1)[0] or None


def summarize_push(result: Any, sections: list[str]) -> dict[str, dict[str, Any]]:
    """推送结果按附注章节汇总：写入 / 未变 / 保留（人工、锁定）/ 跳过 + 前几条跳过原因。"""
    per: dict[str, dict[str, Any]] = {s: {"written": 0, "unchanged": 0, "kept": 0, "skipped": 0, "reasons": []}
                                      for s in sections}
    reasons: dict[str, Counter] = defaultdict(Counter)
    for item in getattr(result, "items", None) or []:
        if getattr(item, "domain", None) != "note":
            continue
        sec = _section_of(getattr(item, "addr_id", None))
        if sec not in per:
            continue
        action = item.action
        if action == "write":
            per[sec]["written"] += 1
        elif action == "unchanged":
            per[sec]["unchanged"] += 1
        elif action in ("keep_locked", "keep_manual", "keep_pending"):
            per[sec]["kept"] += 1
        elif action in ("skipped", "conflict"):
            per[sec]["skipped"] += 1
            if item.reason:
                reasons[sec][item.reason] += 1
    for sec, counter in reasons.items():
        per[sec]["reasons"] = [r for r, _n in counter.most_common(_REASONS_PER_SECTION)]
    return per


async def _push(db: AsyncSession, project_id: UUID, year: int, codes: list[str],
                user_id: UUID | None) -> tuple[Any | None, str | None]:
    """经推送页同一提交包装执行推送；业务上不能推（年度不符等）回原因，不抛。"""
    from app.services.formula_push import engine

    try:
        result = await engine.run_and_commit(
            db, project_id=project_id, year=year, trigger=engine.MANUAL, triggered_by=user_id, codes=codes,
        )
    except engine.PushActionError as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001 —— run_and_commit 已回滚并记失败运行；刷新其余步骤照常
        logger.warning("附注刷新：公式推送失败 project=%s year=%s: %s", project_id, year, exc, exc_info=True)
        return None, f"公式推送失败：{type(exc).__name__}: {exc}"
    return result, None


async def _workpaper_ids(db: AsyncSession, project_id: UUID, codes: list[str]) -> dict[str, str]:
    """本项目这些底稿编码的底稿 id（同码多张取最早建的一张，与推送引擎同口径）——前端离屏同步按它取底稿数据。"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    if not codes:
        return {}
    rows = (await db.execute(
        sa.select(WpIndex.wp_code, WorkingPaper.id)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code.in_(codes),
            WorkingPaper.is_deleted == sa.false(),
        )
        .order_by(WpIndex.wp_code, WorkingPaper.created_at)
    )).all()
    out: dict[str, str] = {}
    for code, wp_id in rows:
        out.setdefault(code, str(wp_id))
    return out


async def _applicable_standards(db: AsyncSession, project_id: UUID) -> list[str]:
    """与底稿 render-config 注入的「适用准则」同一来源（披露同步载荷的 current_standard 据此判单体 / 合并）。"""
    try:
        from app.services.standard_unification_service import StandardUnificationService, derive_applicable_standards

        async with db.begin_nested():
            return list(derive_applicable_standards(await StandardUnificationService(db).get_standard(project_id)))
    except Exception as exc:  # noqa: BLE001 —— 取不到按单体处理（前端 resolve*CurrentStandard 的缺省）
        logger.warning("附注刷新：适用准则读取失败 project=%s: %s", project_id, exc)
        return []


def manual_value_count(table_data: Any) -> int:
    """附注表格里人工填过的格数（``_cell_modes`` 为 manual / locked 且有值）。

    旧生成器把不少格标成 manual 却没有值（重药安徽 八、5 十五张表全是空 manual 格）—— 只数有值的。
    前端离屏同步据此判断：从未由底稿同步、又有人工填写的章节不拿底稿数据覆盖（同步后编辑器改显示披露表投影，
    人工填的模板表格会被盖住）。
    """
    if not isinstance(table_data, dict):
        return 0
    tables = table_data.get("_tables")
    tables = tables if isinstance(tables, list) and tables else [table_data]
    count = 0
    for table in tables:
        for row in (table.get("rows") if isinstance(table, dict) else None) or []:
            if not isinstance(row, dict):
                continue
            modes = row.get("_cell_modes") or {}
            values = row.get("values") if isinstance(row.get("values"), list) else []
            if not isinstance(modes, dict):
                continue
            for col, mode in modes.items():
                if mode not in ("manual", "locked") or not str(col).isdigit() or int(col) >= len(values):
                    continue
                v = values[int(col)]
                if v not in (None, "") and not (isinstance(v, (int, float)) and v == 0):
                    count += 1
    return count


async def _apply_note_formulas(db: AsyncSession, project_id: UUID, year: int,
                               sections: list[str]) -> dict[str, dict[str, Any]]:
    """推送后对章节执行附注公式（合计 / 账面价值 / 用户公式随推送写入的审定数更新；spec R3.4）。

    系统路径（不写编辑人）；只写 auto 格；逐章节保存点 —— 一节失败只回滚这一节、回原因。跨表取数多章节共用一次预载。
    回 ``{章节: {updated, skipped, error}}``（只列有公式的章节）。
    """
    from app.services.formula_settings.note_settings import materialize_quietly
    from app.services.note_formula_generator import execute_note_formulas

    if not sections:
        return {}
    await materialize_quietly(db, project_id, sections)  # 全局 / 本项目公式设置（新建附注还没物化）
    shared: dict[str, Any] = {}
    out: dict[str, dict[str, Any]] = {}
    for sec in sections:
        try:
            async with db.begin_nested():
                res = await execute_note_formulas(db, project_id, year, sec, cross_data=shared)
        except Exception as exc:  # noqa: BLE001 —— 一节公式失败不影响其余章节与刷新
            logger.warning("附注刷新：附注公式执行失败 project=%s section=%s: %s", project_id, sec, exc, exc_info=True)
            out[sec] = {"updated": 0, "skipped": 0, "error": f"{type(exc).__name__}: {exc}"}
            continue
        if res.get("executed") or res.get("results"):
            skipped = sum(1 for r in res.get("results") or [] if r.get("status") == "skipped")
            out[sec] = {"updated": int(res.get("updated") or 0), "skipped": skipped, "error": None}
    return out


async def _mark_synced_sections(db: AsyncSession, project_id: UUID, year: int,
                                sections: list[str]) -> dict[str, Any]:
    """已由底稿同步过（带 ``_last_sync_wp_id``）的章节补 ``_source=workpaper``；不改同步时间（没有同步就不算同步）。

    另回逐章节状态 ``states[章节] = {exists, synced_before, manual_values}``（前端离屏同步的覆盖判断）。指纹只由底稿
    披露同步写（公式推送 2026-10-27 起不写，spec note-pull-followup-closure R3.2）⇒ 本请求先跑的推送不会把章节
    冒充成「同步过」，离屏同步「已有人工填写不覆盖」的保护有效。
    """
    from app.models.report_models import DisclosureNote

    synced = skipped = never = 0
    states: dict[str, dict[str, Any]] = {}
    notes = {
        n.note_section: n for n in (await db.execute(sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section.in_(sections),
            DisclosureNote.is_deleted == sa.false(),
        ))).scalars().all()
    } if sections else {}
    for sec in sections:
        note = notes.get(sec)
        if note is None:
            skipped += 1
            states[sec] = {"exists": False, "synced_before": False, "manual_values": 0}
            continue
        td = note.table_data if isinstance(note.table_data, dict) else {}
        states[sec] = {"exists": True, "synced_before": bool(td.get("_last_sync_wp_id")),
                       "manual_values": manual_value_count(td)}
        if not td.get("_last_sync_wp_id"):
            never += 1
            continue
        synced += 1
        if td.get("_source") not in ("workpaper", "workpaper_html"):
            td = dict(td)
            td["_source"] = "workpaper"
            note.table_data = td
            flag_modified(note, "table_data")
    await db.flush()
    return {"synced": synced, "skipped": skipped, "skipped_never_synced": never, "states": states}


async def _other_section_states(db: AsyncSession, project_id: UUID, year: int,
                                exclude: set[str]) -> dict[str, dict[str, Any]]:
    """本项目本年度其余已有附注章节的 ``{exists, synced_before, manual_values}``（与 ``_mark_synced_sections`` 同口径）。

    离屏同步的 provider 一次可写多个章节（spec note-pull-followup-closure R1.1），注册表外的章节（如 G1 的衍生金融资产）
    不在取数结果的章节行里；没有这份状态，「从未由底稿同步、已有人工填写的章节不覆盖」就判不了。
    """
    from app.models.report_models import DisclosureNote

    rows = (await db.execute(sa.select(DisclosureNote.note_section, DisclosureNote.table_data).where(
        DisclosureNote.project_id == project_id,
        DisclosureNote.year == year,
        DisclosureNote.is_deleted == sa.false(),
    ))).all()
    out: dict[str, dict[str, Any]] = {}
    for sec, td in rows:
        if not sec or sec in exclude:
            continue
        td = td if isinstance(td, dict) else {}
        out[sec] = {"exists": True, "synced_before": bool(td.get("_last_sync_wp_id")),
                    "manual_values": manual_value_count(td)}
    return out


async def pull_sections(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    sections: list[str] | None,
    user_id: UUID | None,
) -> dict[str, Any]:
    """按章节从底稿取数（公式推送），回逐章节结果。``sections`` 为空 = 本准则全部有底稿映射的章节。"""
    from app.models.core import Project
    from app.services.formula_push.bindings import supported_wp_codes

    project = await db.get(Project, project_id)
    if project is None:
        raise LookupError("项目不存在")
    variant = project.template_type or "soe"
    by_section = codes_by_section(variant, sections)
    target_sections = list(by_section)
    supported = set(supported_wp_codes())
    codes = sorted({c for cs in by_section.values() for c in cs if c in supported})

    result, push_error = (None, None)
    if codes:
        result, push_error = await _push(db, project_id, year, codes, user_id)
    per = summarize_push(result, target_sections) if result is not None else {}
    formula_runs = await _apply_note_formulas(db, project_id, year, target_sections)

    marks = await _mark_synced_sections(db, project_id, year, target_sections)
    states = marks.pop("states", None) or {}
    # 全部刷新：一张底稿可写多个章节（注册表只记主章节），离屏同步对注册表外的章节同样按「已有人工填写不覆盖」判
    other_states = {} if sections else await _other_section_states(db, project_id, year, set(target_sections))
    all_codes = sorted({c for cs in by_section.values() for c in cs})
    wp_ids = await _workpaper_ids(db, project_id, all_codes)
    rows = []
    for sec in target_sections:
        sec_codes = by_section.get(sec) or []
        rows.append({
            "section": sec,
            "wp_codes": sec_codes,
            "wp_ids": {c: wp_ids[c] for c in sec_codes if c in wp_ids},
            **(states.get(sec) or {"exists": False, "synced_before": False, "manual_values": 0}),
            "push_wp_codes": [c for c in sec_codes if c in supported],
            "unsupported_wp_codes": [c for c in sec_codes if c not in supported],
            **(per.get(sec) or {"written": 0, "unchanged": 0, "kept": 0, "skipped": 0, "reasons": []}),
            "formula_updated": (formula_runs.get(sec) or {}).get("updated", 0),
        })
    summary = result.summary() if result is not None else None
    return {
        **marks,
        "variant": variant,
        "formulas": {
            "updated": sum(r["updated"] for r in formula_runs.values()),
            "sections": [s for s in target_sections if (formula_runs.get(s) or {}).get("updated")],
            "errors": [f"{s}：{r['error']}" for s, r in formula_runs.items() if r.get("error")],
        },
        "applicable_standards": await _applicable_standards(db, project_id),
        "section_states": {**other_states, **states},
        "push": {
            "ran": result is not None,
            "error": push_error,
            "wp_codes": codes,
            "written": sum(r["written"] for r in rows),
            "kept": sum(r["kept"] for r in rows),
            "skipped": sum(r["skipped"] for r in rows),
            "run_id": (summary or {}).get("run_id"),
            "warnings": (summary or {}).get("warnings") or ([push_error] if push_error else []),
        },
        "sections": rows,
    }
