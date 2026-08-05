"""报告正文段落级回填 —— 真实链路验收（deliverable-lineage-wiring-and-writeback-closure Task 20）

Spec 铁律：**禁止用合成 docx 顶替真实链路验证**（前序 spec 22/22 假绿的直接教训）。
本脚本在**真实库 + 真实交付 docx** 上跑生产代码路径，并在结束时**按快照复原**。

验收链条（需求 9.1~9.6 / 12.1~12.3）：

1. 真实项目存在 ``doc_type='audit_report'`` 的交付件且有版本文件；
2. 对**真实交付 docx** 跑 Task 17 的定位器：扫出章节 → 写 ``sec_rb_*`` 锚点 →
   可见段落文字序列逐字不变 → 锚点可反扫回；
3. 章节状态落库（``persist_report_body_section_states``）→ ``/section-states``
   查询非空且 ``anchor_name`` 与 ``section_id`` 一一对应；
4. ``report_body_json.sections`` 落库（Task 17 的 additive 键）；
5. 跑**生产** ``DeliverableWritebackService.writeback``（注入改过一段文字的 docx）
   → 断言 ``report_body_json.sections`` 里那一段**真的变了**；
6. 派生段落（准则标准表述）被拒 → 内容未变；
7. 附注 ``disclosure_notes`` **逐字未被触碰**（需求 9.2 SHALL NOT）；
8. 复原：``report_body_json`` 回写原值、``deliverable_section_state`` 删除本次插入行。

用法（默认 dry-run，只读探查）::

    python backend/scripts/diagnose/verify_report_body_writeback_live.py
    python backend/scripts/diagnose/verify_report_body_writeback_live.py --apply

``--apply`` 会临时写库并自动复原；复原结果在报告末尾核实。
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import sys
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402

from app.core.database import async_session  # noqa: E402

DOC_TYPE = "audit_report"

# 用于回填的探针文字（复原时按原值回写，故不会残留）
PROBE_SUFFIX = "【回填验收探针：本句由 Task 20 写入，脚本结束时已复原】"


@dataclass
class Report:
    rows: list[tuple[str, bool, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append((name, ok, detail))

    def render(self) -> str:
        width = 100
        out = ["=" * width, "报告正文段落级回填 —— 真实链路验收结果".center(width - 20), "=" * width]
        for name, ok, detail in self.rows:
            tag = "[PASS]" if ok else "[FAIL]"
            out.append(f"  {tag} {name}")
            if detail:
                out.append(f"         {detail}")
        if self.notes:
            out.append("-- 备注 --")
            out.extend(f"  * {n}" for n in self.notes)
        failed = sum(1 for _, ok, _ in self.rows if not ok)
        out.append("=" * width)
        out.append(f"合计 {len(self.rows)} 项，失败 {failed} 项")
        return "\n".join(out)

    @property
    def failed(self) -> int:
        return sum(1 for _, ok, _ in self.rows if not ok)


async def _pick_task(db, project_id: UUID | None):
    from app.models.phase13_models import WordExportTask, WordExportTaskVersion

    stmt = (
        sa.select(
            WordExportTask.id,
            WordExportTask.project_id,
            WordExportTask.status,
            WordExportTask.created_by,
        )
        .where(WordExportTask.doc_type == DOC_TYPE)
        .order_by(WordExportTask.created_at.desc())
    )
    if project_id is not None:
        stmt = stmt.where(WordExportTask.project_id == project_id)
    rows = (await db.execute(stmt)).all()
    for row in rows:
        # 终态不可回填（signed/confirmed/archived），跳过
        if row.status in {"signed", "confirmed", "archived"}:
            continue
        ver = (
            await db.execute(
                sa.select(
                    WordExportTaskVersion.version_no, WordExportTaskVersion.file_path
                )
                .where(WordExportTaskVersion.word_export_task_id == row.id)
                .order_by(WordExportTaskVersion.version_no.desc())
            )
        ).first()
        if ver is None or not ver.file_path:
            continue
        if _resolve_file(ver.file_path) is not None:
            return row, ver
    return None, None


def _resolve_file(file_path: str) -> Path | None:
    """解析版本文件的真实路径。

    🔴 `word_export_task_versions.file_path` 存的是**相对 `backend/` 的相对路径**
    （形如 ``storage\\deliverables\\...``，Windows 反斜杠）。按当前工作目录直接
    ``Path(file_path).exists()`` 在仓库根下必落空 —— 首版脚本即因此报
    「无 audit_report 交付件或版本文件缺失」，而真实文件是存在的。
    """
    raw = (file_path or "").replace("\\", "/")
    for cand in (Path(raw), BACKEND_ROOT / raw, BACKEND_ROOT.parent / raw):
        if cand.exists():
            return cand
    return None


async def _year_of(db, project_id: UUID) -> int:
    from app.models.report_models import AuditReport

    y = (
        await db.execute(
            sa.select(AuditReport.year)
            .where(AuditReport.project_id == project_id)
            .order_by(AuditReport.year.desc())
        )
    ).scalar_one_or_none()
    return int(y) if y is not None else 2025


def _visible_texts(doc) -> list[str]:
    from docx.oxml.ns import qn

    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    return [
        "".join(t.text or "" for t in p.iter(f"{{{ns_w}}}t"))
        for p in doc.element.body.iter(qn("w:p"))
    ]


async def run(project_id: UUID | None, apply: bool) -> Report:
    from docx import Document
    from docx.oxml.ns import qn

    from app.models.report_models import AuditReport, DisclosureNote
    from app.services.deliverable_section_state_service import (
        DeliverableSectionStateService,
        persist_report_body_section_states,
    )
    from app.services.report_body_section_blocks import (
        build_report_body_sections_payload,
        report_body_anchor_name,
        scan_report_body_sections,
    )
    from app.services.section_anchor_utils import (
        block_text_hash,
        scan_anchor_blocks,
        write_section_anchors,
    )
    from app.services.writeback_target_adapters import (
        DERIVED_REPORT_BODY_SECTIONS,
        ReportBodyAdapter,
    )

    rep = Report()

    async with async_session() as db:
        task, ver = await _pick_task(db, project_id)
        if task is None:
            rep.add("找到可回填的报告正文交付件", False, "无 audit_report 交付件或版本文件缺失")
            return rep
        year = await _year_of(db, task.project_id)
        rep.add(
            "找到可回填的报告正文交付件",
            True,
            f"task={task.id} project={task.project_id} year={year} "
            f"status={task.status} v{ver.version_no}",
        )

        # ── 2. 真实交付 docx 上跑定位器 + 锚点 ────────────────────────────────
        docx_file = _resolve_file(ver.file_path)
        assert docx_file is not None  # _pick_task 已保证
        raw = docx_file.read_bytes()
        doc = Document(BytesIO(raw))
        before_texts = _visible_texts(doc)
        secs = scan_report_body_sections(doc)
        rep.add(
            "真实交付 docx 扫出章节",
            bool(secs),
            f"{len(secs)} 个: {[s.section_id for s in secs]}",
        )
        if not secs:
            rep.notes.append(
                "该 docx 无可识别章节标题 —— 可能不是标准致同模板产出，无法继续"
            )
            return rep

        anchor_map = write_section_anchors(
            doc, [s.to_section_block() for s in secs], namer=report_body_anchor_name
        )
        rep.add(
            "写入 sec_rb_* 段落锚点",
            len(anchor_map) == len(secs)
            and all(a.startswith("sec_rb_") for a in anchor_map.values()),
            f"{len(anchor_map)} 个: {sorted(anchor_map.values())[:3]}",
        )
        rep.add(
            "可见段落文字序列逐字不变（需求 12.4 档 2）",
            _visible_texts(doc) == before_texts,
            f"{len(before_texts)} 段",
        )
        rep.add(
            "锚点确实写进 XML",
            len(list(doc.element.body.iter(qn("w:bookmarkStart")))) >= len(anchor_map),
        )
        rep.add(
            "附注回填的扫描器看不见报告正文锚点（命名空间隔离）",
            scan_anchor_blocks(doc) == [],
            f"scan_anchor_blocks -> {len(scan_anchor_blocks(doc))}",
        )

        payload = build_report_body_sections_payload(doc)
        block_hashes = {s.section_id: block_text_hash(s.content_els) for s in secs}
        rep.add(
            "构造 report_body_json.sections 载荷",
            len(payload) == len(secs) and all(p["content"] for p in payload),
            f"{len(payload)} 段，首段 {payload[0]['section_id']} 长度 {len(payload[0]['content'])}",
        )

        # 选一个**可回填**章节与一个**派生**章节
        writable = next(
            (s.section_id for s in secs if s.section_id not in DERIVED_REPORT_BODY_SECTIONS),
            None,
        )
        derived = next(
            (s.section_id for s in secs if s.section_id in DERIVED_REPORT_BODY_SECTIONS),
            None,
        )
        rep.add(
            "同时存在可回填章节与派生章节（供两侧验证）",
            writable is not None and derived is not None,
            f"writable={writable} derived={derived}",
        )
        if writable is None:
            return rep

        if not apply:
            rep.notes.append("dry-run：未写库。加 --apply 执行真实回填并自动复原。")
            return rep

        # ── 快照（复原基线）────────────────────────────────────────────────
        report_row = (
            await db.execute(
                sa.select(AuditReport).where(
                    AuditReport.project_id == task.project_id,
                    AuditReport.year == year,
                )
            )
        ).scalar_one_or_none()
        if report_row is None:
            rep.add("存在 audit_report 记录", False, "该项目/年度无 audit_report 行")
            return rep
        body_backup = copy.deepcopy(report_row.report_body_json)
        rep.add(
            "已快照 report_body_json（复原基线）",
            True,
            f"原键集: {sorted((body_backup or {}).keys())}",
        )

        state_svc = DeliverableSectionStateService(db)
        states_before = await state_svc.get_section_states(task.id)
        codes_before = {s["section_code"] for s in states_before}

        notes_before = (
            await db.execute(
                sa.select(DisclosureNote.id, DisclosureNote.text_content).where(
                    DisclosureNote.project_id == task.project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.is_deleted == sa.false(),
                )
            )
        ).all()
        notes_snapshot = {r.id: r.text_content for r in notes_before}

        try:
            # ── 4. sections + 章节状态落库（模拟 confirm 的 Task 17 行为）──────
            report_row.report_body_json = {**(body_backup or {}), "sections": payload}
            await db.flush()
            n = await persist_report_body_section_states(
                db,
                word_export_task_id=task.id,
                project_id=task.project_id,
                year=year,
                anchor_map=anchor_map,
                rendered_block_hashes=block_hashes,
                version_no=ver.version_no,
            )
            await db.commit()

            states = await state_svc.get_section_states(task.id)
            new_states = [s for s in states if s["section_code"] in anchor_map]
            rep.add(
                "/section-states 返回非空且锚点一一对应",
                len(new_states) == len(anchor_map)
                and all(
                    s["anchor_name"] == report_body_anchor_name(s["section_code"])
                    for s in new_states
                ),
                f"落库 {n} 段，查得 {len(new_states)} 段",
            )
            rep.add(
                "章节状态携带 rendered_block_hash",
                all(s.get("rendered_block_hash") for s in new_states),
                f"非空 {sum(1 for s in new_states if s.get('rendered_block_hash'))}/{len(new_states)}",
            )

            # ── 5. 生产 writeback（注入改过一段的 docx）────────────────────────
            edited = Document(BytesIO(raw))
            esecs = scan_report_body_sections(edited)
            write_section_anchors(
                edited,
                [s.to_section_block() for s in esecs],
                namer=report_body_anchor_name,
            )
            target = next(s for s in esecs if s.section_id == writable)
            last_para = [el for el in target.content_els if el.tag == qn("w:p")][-1]
            runs = list(last_para.iter(qn("w:t")))
            runs[-1].text = (runs[-1].text or "") + PROBE_SUFFIX
            # 派生章节也改一段，用于验证被拒
            derived_probe_applied = False
            if derived is not None:
                dtarget = next(s for s in esecs if s.section_id == derived)
                dparas = [el for el in dtarget.content_els if el.tag == qn("w:p")]
                if dparas:
                    druns = list(dparas[-1].iter(qn("w:t")))
                    if druns:
                        druns[-1].text = (druns[-1].text or "") + PROBE_SUFFIX
                        derived_probe_applied = True

            buf = BytesIO()
            edited.save(buf)

            from app.services.deliverable_writeback_service import (
                DeliverableWritebackService,
            )

            wb = DeliverableWritebackService(db)
            result = await wb.writeback(
                task.id,
                task.project_id,
                year,
                task.created_by,
                docx_bytes=buf.getvalue(),
            )
            await db.commit()

            rep.add(
                "生产 writeback 把可回填章节计入 written",
                writable in (result.get("written") or []),
                f"written={result.get('written')} failed="
                f"{[f['section_code'] for f in (result.get('failed') or [])]}",
            )

            # ── 6/7. DB 列真值 + 附注未被触碰 ──────────────────────────────
            raw_body = (
                await db.execute(
                    sa.select(AuditReport.report_body_json).where(
                        AuditReport.project_id == task.project_id,
                        AuditReport.year == year,
                    )
                )
            ).scalar_one()
            got = {
                s.get("section_id"): (s.get("content") or "")
                for s in (raw_body or {}).get("sections") or []
            }
            rep.add(
                "report_body_json.sections 的 DB 列真值确实变了",
                PROBE_SUFFIX in got.get(writable, ""),
                f"章节 {writable} 含探针: {PROBE_SUFFIX in got.get(writable, '')}",
            )
            if derived is not None and derived_probe_applied:
                rep.add(
                    "派生段落被拒（内容未变，需求 9.4）",
                    PROBE_SUFFIX not in got.get(derived, ""),
                    f"章节 {derived} 未被写入探针",
                )

            notes_after = (
                await db.execute(
                    sa.select(DisclosureNote.id, DisclosureNote.text_content).where(
                        DisclosureNote.project_id == task.project_id,
                        DisclosureNote.year == year,
                        DisclosureNote.is_deleted == sa.false(),
                    )
                )
            ).all()
            unchanged = all(
                notes_snapshot.get(r.id) == r.text_content for r in notes_after
            )
            rep.add(
                "附注 disclosure_notes 逐字未被触碰（需求 9.2 SHALL NOT）",
                unchanged and len(notes_after) == len(notes_before),
                f"{len(notes_after)} 条附注全部未变",
            )

            # ── 8. 需求 9.6：重新生成保留人工文字 ─────────────────────────────
            from app.services.template_fill_service import TemplateFillService

            tfs = TemplateFillService(db)
            preserved = await tfs._update_report_body_json(
                task.project_id,
                year,
                optional_sections={},
                guidance_version_path="(verify)",
                template_version="(verify)",
                company_subtype=None,
                template_variant=None,
                missing_fields=[],
                sections=None,  # 模拟锚点扫描失败
            )
            rep.add(
                "sections=None 时保留上一版人工文字（需求 9.6）",
                PROBE_SUFFIX
                in {
                    s.get("section_id"): s.get("content") or ""
                    for s in preserved.get("sections") or []
                }.get(writable, ""),
                "未提供 sections 时不清空已回填内容",
            )
            await db.rollback()

        finally:
            # ── 复原 ───────────────────────────────────────────────────────
            from app.models.audit_platform_models import DeliverableSectionState

            fresh = (
                await db.execute(
                    sa.select(AuditReport).where(
                        AuditReport.project_id == task.project_id,
                        AuditReport.year == year,
                    )
                )
            ).scalar_one_or_none()
            if fresh is not None:
                fresh.report_body_json = copy.deepcopy(body_backup)
            added = [c for c in anchor_map if c not in codes_before]
            if added:
                await db.execute(
                    sa.delete(DeliverableSectionState).where(
                        DeliverableSectionState.word_export_task_id == task.id,
                        DeliverableSectionState.section_code.in_(added),
                    )
                )
            await db.commit()

            check_body = (
                await db.execute(
                    sa.select(AuditReport.report_body_json).where(
                        AuditReport.project_id == task.project_id,
                        AuditReport.year == year,
                    )
                )
            ).scalar_one_or_none()
            left = (
                await db.execute(
                    sa.select(sa.func.count()).select_from(DeliverableSectionState).where(
                        DeliverableSectionState.word_export_task_id == task.id,
                        DeliverableSectionState.section_code.in_(added or ["__none__"]),
                    )
                )
            ).scalar_one()
            rep.add(
                "复原核实：report_body_json 回到原值",
                check_body == body_backup,
                f"键集 {sorted((check_body or {}).keys())}",
            )
            rep.add(
                "复原核实：本次新增的章节状态行已删除",
                left == 0,
                f"残留 {left} 行（新增 {len(added)} 行）",
            )
            rep.notes.append(f"项目 {task.project_id} / 年度 {year} / 交付件 {task.id}")

    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", help="项目 UUID（缺省自动挑一个可回填的）")
    ap.add_argument(
        "--apply", action="store_true", help="真实写库并自动复原（缺省只读 dry-run）"
    )
    args = ap.parse_args()
    pid = UUID(args.project) if args.project else None
    rep = asyncio.run(run(pid, args.apply))
    print(rep.render())
    return 1 if rep.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
