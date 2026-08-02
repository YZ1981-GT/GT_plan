#!/usr/bin/env python
"""行级合并**真实 DB** 验证（绕过 HTTP）—— 先快照、后推送、逐行比对、按 md5 复原。

spec: .kiro/specs/disclosure-note-row-level-merge/ Task 12

用法（在 backend 目录）：
    python -m scripts.diagnose.verify_row_level_merge_live --note-id <uuid>

流程：
  ① 快照 `table_data` / `text_content` / `last_sync_at`（含 md5）
  ② 跑一次 E1 外币段推送（`_row_scope` owner=BS-002）
  ③ 断言：货币资金段被替换、他四段逐字未变、每行带 `_seg`、返回值字段正确
  ④ 再跑一次 **fail closed**（不存在的 owner）→ 断言整表未写
  ⑤ 按快照逐字节复原（`CAST(:td AS jsonb)` + `json.dumps(ensure_ascii=False)`）

🔴 全程只动一条 `disclosure_notes` 记录；任何断言失败都会先复原再退出。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.report_models import DisclosureNote  # noqa: E402
from app.services.note_shared_table_segments import SEG_KEY  # noqa: E402
from app.services.wp_disclosure_sync_service import sync_from_workpaper  # noqa: E402

FX_TABLE = "外币货币性项目"
OWNER = "BS-002"
OTHER_SEGMENTS = ("BS-006", "BS-031", "BS-061", "BS-062")
SHEET = "附注披露信息(国企)"

FX_COLUMNS = {
    FX_TABLE: [
        {"key": "label", "label": "项目", "is_label": True, "flat": True},
        {"key": "end_fc", "label": "期末外币余额", "format": "amount"},
        {"key": "rate", "label": "折算汇率", "format": "rate"},
        {"key": "end_rmb", "label": "期末折算人民币余额", "format": "amount"},
    ]
}

FX_ROWS = [
    {"label": "货币资金", "end_fc": None, "rate": None, "end_rmb": 111637.60},
    {"label": "其中：美元", "end_fc": 14000, "rate": 7.1884, "end_rmb": 100637.60},
    {"label": "欧元", "end_fc": 1400, "rate": 7.8572, "end_rmb": 11000.00},
]


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _payload(owner: str) -> dict:
    return {
        FX_TABLE: [dict(r) for r in FX_ROWS],
        "_row_scope": {FX_TABLE: {"owner_row_code": owner}},
    }


class Checks:
    def __init__(self) -> None:
        self.ok: list[str] = []
        self.bad: list[str] = []

    def eq(self, label: str, got, want) -> None:
        (self.ok if got == want else self.bad).append(f"{label}: got={got!r} want={want!r}")

    def true(self, label: str, cond: bool, detail: str = "") -> None:
        (self.ok if cond else self.bad).append(f"{label}{(' — ' + detail) if detail else ''}")

    def report(self, out_path: str | None = None) -> int:
        # 🔴 Windows 控制台是 GBK，`✓`/`✗` 会 UnicodeEncodeError → 只用 ASCII 标记，
        #    完整报告另写 UTF-8 文件（PowerShell `>` 重定向会腌坏中文，故由本脚本自己写盘）
        lines = [f"PASS {len(self.ok)} / FAIL {len(self.bad)}"]
        lines += [f"  [OK] {x}" for x in self.ok]
        lines += [f"  [!!] {x}" for x in self.bad]
        text = "\n".join(lines)
        if out_path:
            Path(out_path).write_text(text, encoding="utf-8")
            print(f"报告已写入 {out_path}")
        for line in lines:
            print(line.encode("ascii", "backslashreplace").decode("ascii"))
        return 1 if self.bad else 0


async def _restore(db: AsyncSession, note_id: UUID, snap: dict) -> None:
    # 🔴 `sync_from_workpaper` 写的列必须**逐个**复位。首版漏了
    # `last_sync_user_id` / `updated_by` → 实测在 df5b8403 的记录上留下了
    # 一个 admin 的 uuid（原值 NULL），靠与未触碰的同章节兄弟记录比对才发现。
    await db.execute(
        sa.text(
            "UPDATE disclosure_notes SET table_data = CAST(:td AS jsonb), "
            "text_content = :tc, last_sync_at = :ls, last_sync_source = :lss, "
            "last_sync_wp_id = :lwp, last_sync_user_id = :lsu, "
            "content_type = :ct, updated_at = :ua, updated_by = :ub "
            "WHERE id = :id"
        ),
        {
            "td": json.dumps(snap["table_data"], ensure_ascii=False, default=str),
            "tc": snap["text_content"],
            "ls": snap["last_sync_at"],
            "lss": snap["last_sync_source"],
            "lwp": snap["last_sync_wp_id"],
            "lsu": snap["last_sync_user_id"],
            "ct": snap["content_type"],
            "ua": snap["updated_at"],
            "ub": snap["updated_by"],
            "id": str(note_id),
        },
    )
    await db.commit()


async def run(
    note_id: UUID,
    user_id: UUID,
    out_path: str | None = None,
    standard: str = "soe_standalone",
    sheet: str = SHEET,
) -> int:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    c = Checks()
    async with factory() as db:
        row = (
            await db.execute(
                sa.text(
                    "SELECT project_id::text, year, note_section, source_template::text, "
                    "table_data, text_content, last_sync_at, last_sync_source, "
                    "last_sync_wp_id::text, content_type::text, updated_at, "
                    "last_sync_user_id::text, updated_by::text "
                    "FROM disclosure_notes WHERE id = :id AND is_deleted = false"
                ),
                {"id": str(note_id)},
            )
        ).first()
        if row is None:
            print(f"✗ 找不到附注记录 {note_id}")
            return 1
        (
            project_id, year, section, source_template, table_data, text_content,
            last_sync_at, last_sync_source, last_sync_wp_id, content_type, updated_at,
            last_sync_user_id, updated_by,
        ) = row
        snap = {
            "table_data": table_data,
            "text_content": text_content,
            "last_sync_at": last_sync_at,
            "last_sync_source": last_sync_source,
            "last_sync_wp_id": last_sync_wp_id,
            "content_type": content_type,
            "updated_at": updated_at,
            "last_sync_user_id": last_sync_user_id,
            "updated_by": updated_by,
        }
        before_md5 = _md5(_canon(table_data))
        print(f"项目 {project_id} / {year} / {section}（{source_template}）")
        print(f"  快照 md5={before_md5} len={len(_canon(table_data))}")

        user = SimpleNamespace(id=user_id)
        # `last_sync_wp_id` 无 FK（实测），用占位 UUID 便于事后辨识
        wp_id = UUID(int=1)
        try:
            # ── ② 正常推送 ────────────────────────────────────────────────
            res = await sync_from_workpaper(
                db,
                UUID(project_id),
                wp_id=wp_id,
                sheet_name=sheet,
                section_id=section,
                sub_table_data=_payload(OWNER),
                current_standard=standard,
                user=user,
                year=year,
                sub_table_columns=FX_COLUMNS,
                commit=True,
            )
            c.eq("返回 row_scoped_tables", res.get("row_scoped_tables"), [FX_TABLE])
            c.eq("返回 row_scope_unresolved", res.get("row_scope_unresolved"), [])

            note = (
                await db.execute(sa.select(DisclosureNote).where(DisclosureNote.id == note_id))
            ).scalar_one()
            await db.refresh(note)
            rows = (note.table_data.get("sub_table_data") or {}).get(FX_TABLE) or []
            c.true("落库有该表", bool(rows), f"{len(rows)} 行")
            c.true("每行都带 _seg", all(SEG_KEY in r for r in rows))
            segs = [r.get(SEG_KEY) for r in rows]
            c.eq("段集合完整（5 段）", sorted(set(segs)), sorted({OWNER, *OTHER_SEGMENTS}))

            owner_rows = [r for r in rows if r.get(SEG_KEY) == OWNER]
            c.eq("货币资金段行数 = 推送行数", len(owner_rows), len(FX_ROWS))
            c.eq(
                "货币资金段标签",
                [r.get("label") for r in owner_rows],
                [r["label"] for r in FX_ROWS],
            )
            c.eq("货币资金段金额", owner_rows[1].get("end_rmb"), 100637.60)
            c.true(
                "段内合计自洽",
                abs(
                    (owner_rows[1].get("end_rmb") or 0)
                    + (owner_rows[2].get("end_rmb") or 0)
                    - (owner_rows[0].get("end_rmb") or 0)
                )
                < 0.005,
            )

            for code in OTHER_SEGMENTS:
                seg_rows = [r for r in rows if r.get(SEG_KEY) == code]
                c.eq(f"他段 {code} 行数（模板骨架 5 行）", len(seg_rows), 5)
                c.true(
                    f"他段 {code} 无数值列（骨架，未被凭空填值）",
                    all(set(r) <= {"label", SEG_KEY, "is_total", "row_type"} for r in seg_rows),
                    str(seg_rows[:1]),
                )

            after_first = _canon(note.table_data.get("sub_table_data"))

            # ── ④ fail closed ────────────────────────────────────────────
            res2 = await sync_from_workpaper(
                db,
                UUID(project_id),
                wp_id=wp_id,
                sheet_name=sheet,
                section_id=section,
                sub_table_data=_payload("BS-9999"),
                current_standard=standard,
                user=user,
                year=year,
                sub_table_columns=FX_COLUMNS,
                commit=True,
            )
            c.eq("fail closed → unresolved", res2.get("row_scope_unresolved"), [FX_TABLE])
            c.eq("fail closed → scoped 空", res2.get("row_scoped_tables"), [])
            note2 = (
                await db.execute(sa.select(DisclosureNote).where(DisclosureNote.id == note_id))
            ).scalar_one()
            await db.refresh(note2)
            c.eq(
                "fail closed → sub_table_data 逐字未变",
                _canon(note2.table_data.get("sub_table_data")),
                after_first,
            )
        except Exception as err:  # noqa: BLE001 - 记录后仍要走复原
            c.bad.append(f"推送过程抛异常：{type(err).__name__}: {err}")
        finally:
            # ── ⑤ 复原 ───────────────────────────────────────────────────
            # 前面若因 flush 失败让 session 进入 PendingRollback，必须先回滚
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001 - 回滚失败不阻断复原尝试
                pass
            await _restore(db, note_id, snap)
            check = (
                await db.execute(
                    sa.text("SELECT table_data, text_content, last_sync_at FROM disclosure_notes WHERE id = :id"),
                    {"id": str(note_id)},
                )
            ).first()
            after_md5 = _md5(_canon(check[0]))
            c.eq("复原后 table_data md5", after_md5, before_md5)
            c.eq("复原后 text_content", check[1], snap["text_content"])
            c.eq("复原后 last_sync_at", check[2], snap["last_sync_at"])
            cols = (
                await db.execute(
                    sa.text(
                        "SELECT last_sync_user_id::text, updated_by::text, last_sync_source "
                        "FROM disclosure_notes WHERE id = :id"
                    ),
                    {"id": str(note_id)},
                )
            ).first()
            c.eq("复原后 last_sync_user_id", cols[0], snap["last_sync_user_id"])
            c.eq("复原后 updated_by", cols[1], snap["updated_by"])
            c.eq("复原后 last_sync_source", cols[2], snap["last_sync_source"])

    await engine.dispose()
    return c.report(out_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--note-id", required=True, help="disclosure_notes.id（外币章节）")
    ap.add_argument(
        "--user-id",
        required=True,
        help="真实 users.id —— `updated_by` 有 FK，占位 UUID 会 ForeignKeyViolation",
    )
    ap.add_argument("--out", default=None, help="报告落盘路径（UTF-8）")
    ap.add_argument("--standard", default="soe_standalone", help="current_standard")
    ap.add_argument("--sheet", default=SHEET, help="底稿披露 sheet 名（真实 tab 名）")
    args = ap.parse_args()
    return asyncio.run(
        run(UUID(args.note_id), UUID(args.user_id), args.out, args.standard, args.sheet)
    )


if __name__ == "__main__":
    raise SystemExit(main())
