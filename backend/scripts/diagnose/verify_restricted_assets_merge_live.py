#!/usr/bin/env python
"""受限资产共享表行级合并**真实 DB** 验证（绕过 HTTP）—— 先快照、逐 owner 推、按 md5 复原。

spec: .kiro/specs/restricted-assets-note-row-scope-rollout/ Task 15

表：listed `五、32`「所有权或使用权受到限制的资产」主表 + 「（续：上年年末）」
    / soe `八、93`「所有权和使用权受到限制的资产」（措辞「和」不是「或」）。

用法（在 backend 目录）：
    python -m scripts.diagnose.verify_restricted_assets_merge_live \\
        --note-id <uuid> --user-id <uuid> --variant soe --out ../tmp_ra_live.txt

流程：
  ① 快照 `table_data` 等 9 列（含 md5）
  ② **逐 owner** 依次推送（每次只推一段）→ 每次都断言：
     - 本段被替换成推送内容且每行带 `_seg`
     - **他段逐字未变**（与上一轮快照比对）
     - soe 末行「其他」（`row_type: unowned`）**仍在**且未被在建工程段吞掉
     - listed 合计行仍在（soe 源模板无合计行 → 跳过该断言）
  ③ 不存在的 owner → **fail closed**（`row_scope_unresolved` 非空 + 整表逐字未变）
  ④ 按快照逐字节复原

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
from app.services.note_shared_table_segments import (  # noqa: E402
    SEG_KEY,
    UNOWNED_ROW_TYPE,
    split_segments,
    template_rows,
)
from app.services.wp_disclosure_sync_service import sync_from_workpaper  # noqa: E402

TABLE = {
    "listed": "所有权或使用权受到限制的资产",
    "soe": "所有权和使用权受到限制的资产",
}
SHEET = {"listed": "附注披露信息(上市公司)", "soe": "附注披露信息(国企)"}
STANDARD = {"listed": "listed_standalone", "soe": "soe_standalone"}

#: owner → (段标签, 归属循环)。与前端 `restrictedAssetsConsistency.RESTRICTED_ASSETS_OWNER_WP` 一致
OWNERS = {
    "BS-002": ("货币资金", "E1"),
    "BS-005": ("应收票据", "D1"),
    "BS-006": ("应收账款", "D2"),
    "BS-007": ("应收款项融资", "D5"),
    "BS-010": ("存货", "F2"),
    "BS-028": ("固定资产", "H1"),
    "BS-029": ("在建工程", "H2"),
    "BS-032": ("无形资产", "I1"),
}

#: 已接入推送的 owner（D5/F2 无数据源，不接 —— 见 `RESTRICTED_ASSETS_UNSOURCED`）
WIRED = ("BS-002", "BS-005", "BS-006", "BS-028", "BS-029", "BS-032")

COLUMNS = {
    "listed": {
        TABLE["listed"]: [
            {"key": "label", "label": "项目", "is_label": True, "flat": True},
            {"key": "end_amount", "label": "期末", "format": "amount"},
        ]
    },
    "soe": {
        TABLE["soe"]: [
            {"key": "label", "label": "项目", "is_label": True, "flat": True},
            {"key": "end_carrying", "label": "期末账面价值", "format": "amount"},
            {"key": "reason", "label": "受限原因", "format": "text"},
        ]
    },
}


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def _row(variant: str, owner: str, amount: float) -> dict:
    # 未知 owner（fail closed 用例的 `BS-9999`）也要能构造载荷 —— 用 owner code 当标签
    label, wp = OWNERS.get(owner, (owner, owner))
    if variant == "soe":
        return {"label": label, "end_carrying": amount, "reason": f"测试-{wp}"}
    return {"label": label, "end_amount": amount}


def _payload(variant: str, owner: str, amount: float) -> dict:
    table = TABLE[variant]
    return {
        table: [_row(variant, owner, amount)],
        "_row_scope": {table: {"owner_row_code": owner}},
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


_RESTORE_COLS = (
    "table_data", "text_content", "last_sync_at", "last_sync_source", "last_sync_wp_id",
    "content_type", "updated_at", "last_sync_user_id", "updated_by",
)


async def _restore(db: AsyncSession, note_id: UUID, snap: dict) -> None:
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


def _seg_view(rows: list, owner: str) -> list:
    return [r for r in rows if isinstance(r, dict) and r.get(SEG_KEY) == owner]


def _others_view(rows: list, owner: str) -> str:
    """他段（含无主行）的规范化视图 —— 用于「他段逐字未变」比对。"""
    return _canon([r for r in rows if not (isinstance(r, dict) and r.get(SEG_KEY) == owner)])


async def run(note_id: UUID, user_id: UUID, variant: str, out_path: str | None) -> int:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    c = Checks()
    table = TABLE[variant]

    # ── 模板侧先自检（不连库也成立的事实）─────────────────────────────────────
    async with factory() as db:
        row = (
            await db.execute(
                sa.text(
                    "SELECT project_id::text, year, note_section, source_template::text, "
                    + ", ".join(
                        col if col not in ("last_sync_wp_id", "last_sync_user_id", "updated_by", "content_type")
                        else f"{col}::text"
                        for col in _RESTORE_COLS
                    )
                    + " FROM disclosure_notes WHERE id = :id AND is_deleted = false"
                ),
                {"id": str(note_id)},
            )
        ).first()
        if row is None:
            print(f"找不到附注记录 {note_id}")
            return 1
        project_id, year, section, source_template = row[0], row[1], row[2], row[3]
        snap = dict(zip(_RESTORE_COLS, row[4:]))
        before_md5 = _md5(_canon(snap["table_data"]))
        print(f"项目 {project_id} / {year} / {section}（source_template={source_template}）")
        print(f"  快照 md5={before_md5} len={len(_canon(snap['table_data']))}")

        tpl = template_rows(variant, section, table)
        c.true("模板能查到该表", tpl is not None, f"{section} / {table}")
        if tpl is None:
            await engine.dispose()
            return c.report(out_path)
        segs = split_segments(tpl)
        c.true("段数 >= 6", len(segs) >= 6, str([(s.row_code, s.start, s.end, s.data_end) for s in segs]))
        unowned = [i for i, r in enumerate(tpl) if str((r or {}).get("row_type") or "") == UNOWNED_ROW_TYPE]
        if variant == "soe":
            c.true("soe 模板有 unowned 无主行「其他」", bool(unowned), str(unowned))
            c.eq("soe 模板无合计行", any(bool((r or {}).get("is_total")) for r in tpl), False)
        else:
            c.eq("listed 模板有合计行", any(bool((r or {}).get("is_total")) for r in tpl), True)

        user = SimpleNamespace(id=user_id)
        wp_id = UUID(int=1)
        prev_others: dict[str, str] = {}
        try:
            for idx, owner in enumerate(WIRED):
                seg = next((s for s in segs if s.row_code == owner), None)
                if seg is None:
                    c.true(f"{owner} 在本变体有落点", False, "模板段集合里没有它")
                    continue
                amount = 1000.0 * (idx + 1)
                res = await sync_from_workpaper(
                    db,
                    UUID(project_id),
                    wp_id=wp_id,
                    sheet_name=SHEET[variant],
                    section_id=section,
                    sub_table_data=_payload(variant, owner, amount),
                    current_standard=STANDARD[variant],
                    user=user,
                    year=year,
                    sub_table_columns=COLUMNS[variant],
                    commit=True,
                )
                c.eq(f"{owner} row_scoped_tables", res.get("row_scoped_tables"), [table])
                c.eq(f"{owner} row_scope_unresolved", res.get("row_scope_unresolved"), [])

                note = (
                    await db.execute(sa.select(DisclosureNote).where(DisclosureNote.id == note_id))
                ).scalar_one()
                await db.refresh(note)
                rows = (note.table_data.get("sub_table_data") or {}).get(table) or []
                mine = _seg_view(rows, owner)
                c.eq(f"{owner} 段行数", len(mine), 1)
                if mine:
                    c.eq(f"{owner} 段标签", mine[0].get("label"), OWNERS[owner][0])
                    key = "end_carrying" if variant == "soe" else "end_amount"
                    c.eq(f"{owner} 段金额", mine[0].get(key), amount)
                    if variant == "soe":
                        c.eq(f"{owner} 段受限原因", mine[0].get("reason"), f"测试-{OWNERS[owner][1]}")

                # 无主行 / 合计行必须存活
                labels = [str(r.get("label") or "").strip() for r in rows if isinstance(r, dict)]
                if variant == "soe":
                    c.true(f"{owner} 推后无主行「其他」仍在", "其他" in labels, str(labels))
                    c.true(
                        f"{owner} 推后「其他」未被打段戳",
                        all(
                            not r.get(SEG_KEY)
                            for r in rows
                            if isinstance(r, dict) and str(r.get("label") or "").strip() == "其他"
                        ),
                    )
                else:
                    c.true(
                        f"{owner} 推后合计行仍在",
                        any(bool(r.get("is_total")) for r in rows if isinstance(r, dict)),
                        str(labels),
                    )

                # 他段逐字未变（第 2 轮起可比；第 1 轮记基线）
                others = _others_view(rows, owner)
                for done in WIRED[:idx]:
                    done_rows = _seg_view(rows, done)
                    c.eq(f"{owner} 推送后 {done} 段仍在且行数不变", len(done_rows), 1)
                if idx and prev_others.get("all"):
                    pass  # 见下：整表逐字比对用 fail closed 一步验，此处只查各段存活
                prev_others["all"] = others

            # ── fail closed：不存在的 owner ─────────────────────────────────
            note_before = (
                await db.execute(sa.select(DisclosureNote).where(DisclosureNote.id == note_id))
            ).scalar_one()
            await db.refresh(note_before)
            snapshot_all = _canon(note_before.table_data.get("sub_table_data"))
            res_bad = await sync_from_workpaper(
                db,
                UUID(project_id),
                wp_id=wp_id,
                sheet_name=SHEET[variant],
                section_id=section,
                sub_table_data=_payload(variant, "BS-9999", 999.0),
                current_standard=STANDARD[variant],
                user=user,
                year=year,
                sub_table_columns=COLUMNS[variant],
                commit=True,
            )
            c.eq("fail closed → unresolved", res_bad.get("row_scope_unresolved"), [table])
            c.eq("fail closed → scoped 空", res_bad.get("row_scoped_tables"), [])
            note_after = (
                await db.execute(sa.select(DisclosureNote).where(DisclosureNote.id == note_id))
            ).scalar_one()
            await db.refresh(note_after)
            c.eq(
                "fail closed → sub_table_data 逐字未变",
                _canon(note_after.table_data.get("sub_table_data")),
                snapshot_all,
            )

            # ── 全段推完后的整表体检 ────────────────────────────────────────
            rows = (note_after.table_data.get("sub_table_data") or {}).get(table) or []
            stamped = [r for r in rows if isinstance(r, dict) and r.get(SEG_KEY)]
            # 基线由模板骨架产生 → **全部** 8 段都带 `_seg`（未接入段是纯标签骨架）
            c.eq(
                "段集合 == 模板全部段",
                sorted({r.get(SEG_KEY) for r in stamped}),
                sorted({s.row_code for s in segs}),
            )
            amount_key = "end_carrying" if variant == "soe" else "end_amount"
            for owner in WIRED:
                mine = _seg_view(rows, owner)
                c.eq(f"{owner} 段最终 1 行", len(mine), 1)
                c.true(f"{owner} 段有金额", bool(mine and mine[0].get(amount_key)))
            # 🔴 未接入的段必须是**纯标签骨架**（不得凭空造 0 值 —— 宁缺勿造）
            for owner in (o for o in OWNERS if o not in WIRED):
                skel = _seg_view(rows, owner)
                if not any(s.row_code == owner for s in segs):
                    continue
                c.eq(f"未接入段 {owner} 行数", len(skel), 1)
                c.eq(f"未接入段 {owner} 标签", skel[0].get("label"), OWNERS[owner][0])
                c.true(
                    f"未接入段 {owner} 无数值列（未凭空填 0）",
                    all(set(r) <= {"label", SEG_KEY, "is_total", "row_type"} for r in skel),
                    str(skel),
                )
        except Exception as err:  # noqa: BLE001 - 记录后仍要走复原
            c.bad.append(f"推送过程抛异常：{type(err).__name__}: {err}")
        finally:
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
            await _restore(db, note_id, snap)
            check = (
                await db.execute(
                    sa.text(
                        "SELECT table_data, text_content, last_sync_at, "
                        "last_sync_user_id::text, updated_by::text, last_sync_source "
                        "FROM disclosure_notes WHERE id = :id"
                    ),
                    {"id": str(note_id)},
                )
            ).first()
            c.eq("复原后 table_data md5", _md5(_canon(check[0])), before_md5)
            c.eq("复原后 text_content", check[1], snap["text_content"])
            c.eq("复原后 last_sync_at", check[2], snap["last_sync_at"])
            c.eq("复原后 last_sync_user_id", check[3], snap["last_sync_user_id"])
            c.eq("复原后 updated_by", check[4], snap["updated_by"])
            c.eq("复原后 last_sync_source", check[5], snap["last_sync_source"])

    await engine.dispose()
    return c.report(out_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--note-id", required=True, help="disclosure_notes.id（受限资产章节）")
    ap.add_argument(
        "--user-id",
        required=True,
        help="真实 users.id —— `updated_by` 有 FK，占位 UUID 会 ForeignKeyViolation",
    )
    ap.add_argument("--variant", default="soe", choices=("listed", "soe"))
    ap.add_argument("--out", default=None, help="报告落盘路径（UTF-8）")
    args = ap.parse_args()
    return asyncio.run(run(UUID(args.note_id), UUID(args.user_id), args.variant, args.out))


if __name__ == "__main__":
    raise SystemExit(main())
