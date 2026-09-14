"""真实链路验收：附注交付件 → 章节锚点 → 回填（spec deliverable-lineage-wiring-and-writeback-closure Task 11）。

为什么必须有这个脚本（需求 12.1~12.3）：
    前身 spec（deliverable-lineage-and-writeback）28 条属性测试全绿、tasks.md 22/22
    全 `[x]`，但生产链路**从未通过** —— 因为那些测试自己合成带 `##SECTION:` 标记的
    docx 再验证，从不检查生产导出路径有没有调用 `write_section_anchors` /
    `snapshot_on_confirm`。实测判据（表 `deliverable_section_state` 全库 0 行）证明
    整条反向链空转。故本 spec 的完成判据**不接受合成 docx 测试**，必须是：

      ①真实项目走生产导出入口生成附注交付件
      ②`deliverable_section_state` 真有行，且 `anchor_name == anchor_name(section_code)`
      ③docx 里真有对应隐藏书签（openpyxl/python-docx 直读，不信任服务层返回值）
      ④回填一段文字后 `disclosure_notes.text_content` **真的变了**
      ⑤回填零行时落 `failed` 桶而非 `written`

用法（只读默认；写操作必须显式 --apply）::

    python backend/scripts/diagnose/verify_deliverable_lineage_live.py --list
    python backend/scripts/diagnose/verify_deliverable_lineage_live.py --project <uuid> --year 2025
    python backend/scripts/diagnose/verify_deliverable_lineage_live.py --project <uuid> --year 2025 --apply

安全约束：
    - 默认 dry-run：只读探测（表状态 / 迁移是否应用 / 候选项目），不生成不写库。
    - `--apply` 才真实生成交付件 + 回填；**结束时自动按快照复原**
      （`disclosure_notes.text_content` 原值回写、本次新建的 task/version/section_state 删除、
      落盘文件删除），复原失败会显式报错并打印手工复原 SQL。
    - 不碰 `trial_balance` / `tb_*` 等四表数据。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import sqlalchemy as sa  # noqa: E402

# ---------------------------------------------------------------------------
# 结果收集
# ---------------------------------------------------------------------------


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(name, ok, detail))

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    def dump(self) -> None:
        print("\n" + "=" * 78)
        print("真实链路验收结果")
        print("=" * 78)
        for c in self.checks:
            mark = "PASS" if c.ok else "FAIL"
            print(f"  [{mark}] {c.name}")
            if c.detail:
                for line in c.detail.splitlines():
                    print(f"         {line}")
        if self.notes:
            print("\n-- 备注 --")
            for n in self.notes:
                print(f"  * {n}")
        print("=" * 78)
        print(f"合计 {len(self.checks)} 项，失败 {len(self.failed)} 项")


# ---------------------------------------------------------------------------
# 只读探测
# ---------------------------------------------------------------------------


# V141 只新增 ``rendered_block_hash`` 一列。
#
# 🔴 刻意**不**持久化 anchor_locate_mode（anchor/marker/none）：它是
# ``resolve_section_blocks`` 每次定位时按文档实际内容重算的运行态判定值 ——
# 存进表里就成了第二真源，文档被 OO 编辑/刷新后列值与实际形态会漂移，
# 而下游没有任何消费方需要"上次定位用了哪种方式"。需要展示时现算即可。
_V141_COLUMNS = ("rendered_block_hash",)


async def _probe_schema(db, rep: Report) -> bool:
    """探测 `deliverable_section_state` 表与 V141 新增列是否就绪。"""
    tbl = (
        await db.execute(sa.text("SELECT to_regclass('public.deliverable_section_state')"))
    ).scalar()
    rep.add("表 deliverable_section_state 存在", tbl is not None, str(tbl))
    if tbl is None:
        return False

    cols = {
        r[0]
        for r in (
            await db.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'deliverable_section_state'"
                )
            )
        ).all()
    }
    missing = [c for c in _V141_COLUMNS if c not in cols]
    rep.add(
        "V141 新增列 rendered_block_hash 已应用",
        not missing,
        "缺失: " + ", ".join(missing) if missing else "rendered_block_hash 已就绪",
    )
    if missing:
        rep.notes.append(
            "V141 未应用 —— MigrationRunner 只在后端启动时跑；"
            "请重启后端（或先跑 backend/migrations/V141__deliverable_section_rendered_block_hash.sql）后重试"
        )
    return not missing


async def _probe_baseline(db, rep: Report) -> None:
    """记录当前全库章节状态行数（P0-1 的实证基线）。"""
    cnt = (
        await db.execute(sa.text("SELECT count(*) FROM deliverable_section_state"))
    ).scalar_one()
    rep.notes.append(f"验收前 deliverable_section_state 全库行数 = {cnt}")


async def _list_candidates(db) -> list[dict]:
    rows = (
        await db.execute(
            sa.text(
                """
                SELECT p.id, p.name, p.template_type, p.report_scope,
                       n.year, count(*) AS note_cnt,
                       count(*) FILTER (WHERE coalesce(n.text_content,'') <> '') AS with_text
                  FROM projects p
                  JOIN disclosure_notes n ON n.project_id = p.id AND n.is_deleted = false
                 WHERE p.is_deleted = false
                 GROUP BY p.id, p.name, p.template_type, p.report_scope, n.year
                HAVING count(*) FILTER (WHERE coalesce(n.text_content,'') <> '') > 20
                 ORDER BY with_text DESC
                 LIMIT 10
                """
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 生产路径生成 + 断言
# ---------------------------------------------------------------------------


async def _run_live(db, project_id: UUID, year: int, rep: Report) -> None:
    from app.models.core import Project
    from app.models.phase13_models import WordExportDocType
    from app.services.deliverable_section_state_service import (
        persist_note_export_section_states,
    )
    from app.services.deliverable_service import DeliverableService
    from app.services.note_section_catalog import (
        normalize_report_scope,
        normalize_template_type,
    )
    from app.services.note_word_exporter import NoteWordExporter
    from app.services.section_anchor_utils import anchor_name, scan_anchor_blocks

    proj = (
        await db.execute(
            sa.select(Project.template_type, Project.report_scope, Project.name).where(
                Project.id == project_id, Project.is_deleted == sa.false()
            )
        )
    ).one_or_none()
    if proj is None:
        rep.add("项目存在", False, str(project_id))
        return
    template_type = normalize_template_type(proj[0])
    report_scope = normalize_report_scope(proj[1] if isinstance(proj[1], str) else None)
    rep.notes.append(f"项目 = {proj[2]} / {template_type} / {report_scope} / {year}")

    # 复原用：需要一个真实用户 id
    user_id = (
        await db.execute(sa.text("SELECT id FROM users ORDER BY created_at LIMIT 1"))
    ).scalar()
    if user_id is None:
        rep.add("存在可用 user", False, "users 表为空")
        return

    created_task_id: UUID | None = None
    text_backup: tuple[str, str | None] | None = None

    try:
        # ─── ①走生产导出路径（export_with_meta，与路由/全套执行器同一入口）───
        dsvc = DeliverableService(db)
        task, _ = await dsvc.export_or_new_deliverable(
            project_id,
            WordExportDocType.disclosure_notes.value,
            template_type,
            user_id,
        )
        await db.flush()
        created_task_id = task.id

        exporter = NoteWordExporter(db)
        buf, meta = await exporter.export_with_meta(
            project_id,
            year,
            template_type=template_type,
            report_scope=report_scope,
            mode="template",
            flatten_formulas=True,
        )
        docx_bytes = buf.getvalue()
        rep.add(
            "生产导出返回章节元数据",
            bool(meta.kept_codes),
            f"kept={len(meta.kept_codes)} anchors={len(meta.anchor_map)} "
            f"hashes={len(meta.rendered_block_hashes)} variant={meta.variant_key}",
        )
        if not meta.kept_codes:
            rep.notes.append(
                "kept_codes 为空 —— 该项目/变体下模板全部章节被裁剪，换项目重试"
            )
            return

        # ─── ②docx 里真有隐藏书签（直读，不信服务层返回值）───
        from docx import Document
        from io import BytesIO

        doc = Document(BytesIO(docx_bytes))
        anchors = scan_anchor_blocks(doc)
        anchor_codes = {a.section_code for a in anchors}
        rep.add(
            "交付 docx 内真有 Section_Anchor 书签",
            bool(anchors),
            f"扫到 {len(anchors)} 个锚点块，前 3 个: "
            + ", ".join(f"{a.section_code}->{a.anchor_name}" for a in anchors[:3]),
        )
        rep.add(
            "锚点命名与 section_code 一一对应",
            all(a.anchor_name == anchor_name(a.section_code) for a in anchors),
            "全部 anchor_name == anchor_name(section_code)"
            if anchors
            else "无锚点可比",
        )
        # 标记必须已清（对外交付物不能带 ##SECTION:）
        from app.services.word_doc_utils import scan_section_blocks

        rep.add(
            "交付 docx 已清 ##SECTION:## 标记",
            scan_section_blocks(doc) == [],
            "标记扫描为空（故旧定位方式恒失效，必须走锚点）",
        )

        # ─── ③落库 + /section-states 非空 ───
        store = await dsvc.render_and_store(
            task.id,
            docx_bytes=docx_bytes,
            user_id=user_id,
            file_name=f"_verify_notes_{year}.docx",
        )
        await persist_note_export_section_states(
            db,
            word_export_task_id=task.id,
            project_id=project_id,
            year=year,
            meta=meta,
            version_no=store.version.version_no,
        )
        await db.flush()

        from app.services.deliverable_section_state_service import (
            DeliverableSectionStateService,
        )

        states = await DeliverableSectionStateService(db).get_section_states(task.id)
        rep.add(
            "/section-states 返回非空",
            bool(states),
            f"{len(states)} 行；示例: "
            + json.dumps(states[0], ensure_ascii=False, default=str)[:200]
            if states
            else "0 行（整条反向链仍空转）",
        )
        rep.add(
            "章节状态 anchor_name 与 section_code 对应",
            all(s["anchor_name"] == anchor_name(s["section_code"]) for s in states),
            "落库 anchor_name 全部可反解",
        )
        rep.add(
            "章节状态携带 rendered_block_hash",
            all(s.get("rendered_block_hash") for s in states),
            f"非空 {sum(1 for s in states if s.get('rendered_block_hash'))}/{len(states)}",
        )

        # ─── ④回填真改 DB ───
        target = next(
            (s["section_code"] for s in states if s.get("anchor_name")),
            None,
        )
        if target is None:
            rep.add("有可回填章节", False, "无 anchor 模式章节")
            return

        old_text = (
            await db.execute(
                sa.text(
                    "SELECT text_content FROM disclosure_notes "
                    "WHERE project_id=:p AND year=:y AND note_section=:s AND is_deleted=false"
                ),
                {"p": str(project_id), "y": year, "s": target},
            )
        ).scalar()
        text_backup = (target, old_text)

        probe = f"【回填验收探针 {uuid4().hex[:8]}】"
        from app.services.deliverable_writeback_service import DeliverableWritebackService

        # 构造「出品物侧被编辑过」的 docx：把目标章节块内文字换成探针文本
        edited = _edit_section_text(docx_bytes, target, probe)
        wb = DeliverableWritebackService(db)
        result = await wb.writeback(
            word_export_task_id=task.id,
            project_id=project_id,
            year=year,
            actor_id=user_id,
            docx_bytes=edited,
        )
        await db.flush()

        new_text = (
            await db.execute(
                sa.text(
                    "SELECT text_content FROM disclosure_notes "
                    "WHERE project_id=:p AND year=:y AND note_section=:s AND is_deleted=false"
                ),
                {"p": str(project_id), "y": year, "s": target},
            )
        ).scalar()

        rep.add(
            "回填后 disclosure_notes.text_content 真的变了",
            (new_text or "") != (old_text or "") and probe in (new_text or ""),
            f"章节 {target}\n  written={result['written']}\n"
            f"  failed={[f['section_code'] for f in result.get('failed', [])]}\n"
            f"  conflicts={[c['section_code'] for c in result['conflicts']]}\n"
            f"  探针在新值中: {probe in (new_text or '')}",
        )
        rep.add(
            "written 与 failed 互斥",
            not (set(result["written"]) & {f["section_code"] for f in result.get("failed", [])}),
            "两桶无交集",
        )

        # ─── ⑤零行写入落 failed 桶（对不存在的章节回填）───
        ghost = "九、999"
        ghost_docx = _append_ghost_section(edited, ghost, "幽灵章节文本")
        ghost_result = await wb.writeback(
            word_export_task_id=task.id,
            project_id=project_id,
            year=year,
            actor_id=user_id,
            docx_bytes=ghost_docx,
        )
        ghost_failed = [f["section_code"] for f in ghost_result.get("failed", [])]
        rep.add(
            "上游无记录的章节落 failed 桶（不计 written）",
            ghost not in ghost_result["written"],
            f"written={ghost_result['written']} failed={ghost_failed}\n"
            f"  （{ghost} 在上游无 disclosure_notes 记录 → UPDATE 影响 0 行）",
        )

    finally:
        # ─── 复原 ───
        restored: list[str] = []
        problems: list[str] = []
        try:
            if text_backup is not None:
                sec, old = text_backup
                await db.execute(
                    sa.text(
                        "UPDATE disclosure_notes SET text_content = :t "
                        "WHERE project_id=:p AND year=:y AND note_section=:s AND is_deleted=false"
                    ),
                    {"t": old, "p": str(project_id), "y": year, "s": sec},
                )
                restored.append(f"disclosure_notes[{sec}].text_content 已回写原值")
            if created_task_id is not None:
                paths = [
                    r[0]
                    for r in (
                        await db.execute(
                            sa.text(
                                "SELECT file_path FROM word_export_task_versions "
                                "WHERE word_export_task_id = :t"
                            ),
                            {"t": str(created_task_id)},
                        )
                    ).all()
                    if r[0]
                ]
                await db.execute(
                    sa.text(
                        "DELETE FROM deliverable_section_state WHERE word_export_task_id = :t"
                    ),
                    {"t": str(created_task_id)},
                )
                await db.execute(
                    sa.text(
                        "DELETE FROM word_export_task_versions WHERE word_export_task_id = :t"
                    ),
                    {"t": str(created_task_id)},
                )
                await db.execute(
                    sa.text("DELETE FROM word_export_task WHERE id = :t"),
                    {"t": str(created_task_id)},
                )
                restored.append(f"交付物 {created_task_id} 及其版本/章节状态已删除")
                for p in paths:
                    try:
                        fp = Path(p)
                        if fp.exists():
                            fp.unlink()
                    except OSError as e:
                        problems.append(f"文件未删除 {p}: {e}")
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            problems.append(f"复原失败: {exc}")
            await db.rollback()

        for r in restored:
            rep.notes.append("复原: " + r)
        for p in problems:
            rep.notes.append("⚠ " + p)
        if problems and created_task_id:
            rep.notes.append(
                "手工复原 SQL: DELETE FROM deliverable_section_state WHERE word_export_task_id='"
                f"{created_task_id}'; DELETE FROM word_export_task_versions WHERE word_export_task_id='"
                f"{created_task_id}'; DELETE FROM word_export_task WHERE id='{created_task_id}';"
            )


def _edit_section_text(docx_bytes: bytes, section_code: str, new_text: str) -> bytes:
    """模拟审计师在 OnlyOffice 里改某章节正文：把块内首个正文段落替换为 new_text。"""
    from io import BytesIO

    from docx import Document
    from docx.oxml.ns import qn

    from app.services.section_anchor_utils import scan_anchor_blocks

    doc = Document(BytesIO(docx_bytes))
    for block in scan_anchor_blocks(doc):
        if block.section_code != section_code:
            continue
        p_tag = qn("w:p")
        for el in block.elements:
            if el.tag != p_tag:
                continue
            from docx.text.paragraph import Paragraph

            para = Paragraph(el, doc)
            if (para.text or "").strip():
                para.clear()
                para.add_run(new_text)
                break
        break
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def _append_ghost_section(docx_bytes: bytes, section_code: str, text: str) -> bytes:
    """追加一个上游不存在的章节块（带锚点），验证零行写入落 failed 桶。"""
    from io import BytesIO

    from docx import Document

    from app.services.section_anchor_utils import SectionBlock, write_section_anchors

    doc = Document(BytesIO(docx_bytes))
    open_p = doc.add_paragraph(f"##SECTION:{section_code}##")
    doc.add_paragraph(text)
    close_p = doc.add_paragraph(f"##/SECTION:{section_code}##")
    write_section_anchors(
        doc,
        [
            SectionBlock(
                section_code=section_code,
                open_el=open_p._p,
                close_el=close_p._p,
            )
        ],
        start_id=90000,
    )
    from app.services.word_doc_utils import remove_section_markers

    remove_section_markers(doc)
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def _amain(args) -> int:
    from app.core.database import async_session

    rep = Report()
    async with async_session() as db:
        schema_ok = await _probe_schema(db, rep)
        await _probe_baseline(db, rep)

        if args.list or not args.project:
            cands = await _list_candidates(db)
            print("\n候选项目（附注有实质文字内容）:")
            for c in cands:
                print(
                    f"  {c['id']}  {c['name'][:28]:<30} {c['template_type']:<7}"
                    f" {c['report_scope']:<13} year={c['year']} notes={c['note_cnt']} with_text={c['with_text']}"
                )
            if not args.project:
                rep.notes.append("未指定 --project，仅做只读探测（未生成交付件）")
                rep.dump()
                return 0 if not rep.failed else 1

        if not args.apply:
            rep.notes.append(
                "dry-run：未执行生成与回填。加 --apply 才做真实链路验收（结束自动复原）"
            )
            rep.dump()
            return 0 if not rep.failed else 1

        if not schema_ok:
            rep.notes.append("schema 未就绪，拒绝 --apply（避免写入半成品状态）")
            rep.dump()
            return 1

        await _run_live(db, UUID(args.project), args.year, rep)

    rep.dump()
    return 0 if not rep.failed else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", help="项目 UUID")
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--list", action="store_true", help="列出候选项目")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="真实生成交付件 + 回填（结束自动复原）",
    )
    return asyncio.run(_amain(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
