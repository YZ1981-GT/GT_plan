#!/usr/bin/env python
"""附注模板 `report_row_code` 陈旧编号重映射（平台级幂等修订）。

**问题**：`note_template_{listed,soe}.json` 里 134 行带 `report_row_code`，
但全部指向**旧编号体系**（实证样本）::

    附注行标签   现写编号   该编号当前 row_name   位移
    固定资产      BS-014     其他流动资产           14
    短期借款      BS-031     使用权资产             10
    应收票据      BS-004     衍生金融资产            1
    存货          BS-008     预付款项                2
    应付账款      BS-033     开发支出               12

位移量不一致（14 / 10 / 1 / 2 / 12）→ **任何「统一加 N」的猜测都是错的**，
唯一可靠依据 = `report_config.row_name` 与附注行标签匹配。

今日这 134 行**全部同时带 `account_codes`**，故 `REPORT()` 不触发 = inert；
但属定时炸弹：`DISCLOSURE_NOTE_FORMULA_ENABLED` 一旦开启且未来新增无
`account_codes` 的行，就会取到完全不相干的报表行金额。

**真源**：`report_config` **DB 表**（不是 `data/report_config_seed.json` ——
实测两者编号体系不同：seed 的 BS-004 是「拆出资金」，DB 的 BS-004 是
「衍生金融资产」；平台铁律已定 DB 为准）。

因 CI 无 DB，脚本支持把 DB 反查索引物化成 committed 快照
`backend/data/report_row_code_index.json`，供离线守卫消费（同
`note_workpaper_sync_registry.json` 的模式）。

Usage::

    # 1) 从 DB 物化反查索引（需 DATABASE_URL）
    python backend/scripts/fix/remap_note_report_row_codes.py --dump-index

    # 2) 看清单（不写模板）
    python backend/scripts/fix/remap_note_report_row_codes.py --check

    # 3) 只改能唯一解析的行
    python backend/scripts/fix/remap_note_report_row_codes.py --apply

spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R6
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND))

DATA_DIR = _BACKEND / "data"
INDEX_PATH = DATA_DIR / "report_row_code_index.json"
PATHS = [
    DATA_DIR / "note_template_listed.json",
    DATA_DIR / "note_template_soe.json",
]


# ─────────────────────────── 标签归一 ───────────────────────────

_PREFIX_RE = re.compile(r"^(加：|减：|其中：|加:|减:|其中:)\s*")
_SECTION_RE = re.compile(r"^[一二三四五六七八九十]+、\s*")


def normalize_label(name: Any) -> str:
    """与 `fill_report_formulas.normalize_name` 同口径的标签归一。

    去 `△▲` 标记、章节序号、`其中：`/`加：`/`减：` 前缀、全部冒号与空白。
    """
    if not isinstance(name, str):
        return ""
    s = re.sub(r"[△▲]", "", name)
    s = _SECTION_RE.sub("", s)
    s = _PREFIX_RE.sub("", s)
    s = s.replace("：", "").replace(":", "").replace(" ", "").replace("\u3000", "")
    return s.strip()


# ─────────────────────────── 反查索引 ───────────────────────────

async def _fetch_report_config_rows() -> list[tuple[str, str, str, str]]:
    """从 DB 读 `report_config` 的 (row_code, row_name, applicable_standard, report_type)。"""
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _resolve_db_url()
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            # `report_config` 是**扁平表**（row_code / row_name 直接在表上，实证
            # information_schema），非 config + config_row 两表结构。
            result = await conn.execute(
                sa.text(
                    "SELECT DISTINCT row_code, row_name, applicable_standard, report_type "
                    "FROM report_config WHERE COALESCE(is_deleted, false) = false"
                )
            )
            return [(str(a), str(b), str(c), str(d)) for a, b, c, d in result.all()]
    finally:
        await engine.dispose()


def _resolve_db_url() -> str:
    """取 DB URL：环境变量优先，否则用 app settings（由 PG_* 组装）。"""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        try:
            from app.core.config import settings  # noqa: PLC0415

            url = str(getattr(settings, "DATABASE_URL", "") or "")
        except Exception as exc:  # pragma: no cover - 环境缺依赖时给明确提示
            raise SystemExit(f"ERROR: 无法解析 DATABASE_URL（{exc}）") from exc
    if not url:
        raise SystemExit("ERROR: DATABASE_URL 为空，无法物化反查索引")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


#: 准则家族：附注模板 listed 只能对 listed_* 的报表行，soe 只能对 soe_*。
#: 不按家族切分会引入跨家族歧义（实测 soe 的 BS-055 是「短期借款」，
#: 而 listed 的 BS-055 是「应付股利」）。
FAMILIES = ("listed", "soe")


def _family_of(standard: str) -> str | None:
    s = (standard or "").lower()
    if s.startswith("listed"):
        return "listed"
    if s.startswith("soe"):
        return "soe"
    return None


def dump_index() -> dict[str, Any]:
    rows = asyncio.run(_fetch_report_config_rows())

    by_label: dict[str, dict[str, set[str]]] = {f: {} for f in FAMILIES}
    by_code: dict[str, dict[str, set[str]]] = {f: {} for f in FAMILIES}
    for code, name, standard, _report_type in rows:
        family = _family_of(standard)
        if family is None or not code:
            continue
        label = normalize_label(name)
        if not label:
            continue
        by_label[family].setdefault(label, set()).add(code)
        by_code[family].setdefault(code, set()).add(label)

    payload = {
        "_source": (
            "生成自 report_config DB 表（平台真源；注意 data/report_config_seed.json "
            "的编号体系与 DB 不同，不可作为反查依据）。按准则家族（listed / soe）分别索引。"
            "重生成：python backend/scripts/fix/remap_note_report_row_codes.py --dump-index"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "label_to_codes": {
            f: {k: sorted(v) for k, v in sorted(by_label[f].items())} for f in FAMILIES
        },
        "code_to_labels": {
            f: {k: sorted(v) for k, v in sorted(by_code[f].items())} for f in FAMILIES
        },
    }
    INDEX_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def load_index() -> dict[str, Any]:
    if not INDEX_PATH.exists():
        raise SystemExit(
            f"ERROR: 缺少反查索引 {INDEX_PATH.name}，请先跑 --dump-index（需 DATABASE_URL）"
        )
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


# ─────────────────────────── 解析与改写 ───────────────────────────

@dataclass
class Resolution:
    variant: str
    section: str
    label: str
    old_code: str
    new_code: str | None
    reason: str  # 'ok' | 'unchanged' | 'ambiguous' | 'not_found'

    def __str__(self) -> str:
        tail = {
            "ok": f"{self.old_code} → {self.new_code}",
            "unchanged": f"{self.old_code}（已正确）",
            "ambiguous": f"{self.old_code}（标签映射到多个编号，保留）",
            "not_found": f"{self.old_code}（标签在 report_config 中找不到，保留）",
        }[self.reason]
        return f"{self.variant} §{self.section} 「{self.label}」 {tail}"


def _walk_rows(rows: Any) -> Iterable[dict[str, Any]]:
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        yield row
        yield from _walk_rows(row.get("children"))


def resolve_doc(
    doc: dict[str, Any],
    variant: str,
    index: dict[str, Any],
    *,
    apply: bool,
) -> list[Resolution]:
    label_to_codes: dict[str, list[str]] = index["label_to_codes"][variant]
    code_to_labels: dict[str, list[str]] = index["code_to_labels"][variant]
    out: list[Resolution] = []

    def handle(row: dict[str, Any], section_no: str) -> None:
        old = row.get("report_row_code")
        if not isinstance(old, str) or not old:
            return
        label = normalize_label(row.get("label") or row.get("name"))
        if not label:
            out.append(Resolution(variant, section_no, "(无标签)", old, None, "not_found"))
            return
        codes = label_to_codes.get(label) or []
        if not codes:
            out.append(Resolution(variant, section_no, label, old, None, "not_found"))
            return
        if len(codes) > 1:
            out.append(Resolution(variant, section_no, label, old, None, "ambiguous"))
            return
        new = codes[0]
        if new == old:
            out.append(Resolution(variant, section_no, label, old, old, "unchanged"))
            return
        out.append(Resolution(variant, section_no, label, old, new, "ok"))
        if apply:
            row["report_row_code"] = new

    for section in doc.get("sections", []) or []:
        section_no = str(section.get("section_number") or "?")
        for row in _walk_rows(section.get("rows")):
            handle(row, section_no)
        for tbl in section.get("tables") or []:
            if isinstance(tbl, dict):
                for row in _walk_rows(tbl.get("rows")):
                    handle(row, section_no)
    # 顺带把「该编号当前指向什么」写进日志，便于人工复核
    for res in out:
        if res.reason in ("ok", "ambiguous", "not_found"):
            cur = code_to_labels.get(res.old_code) or []
            if cur:
                res.label = f"{res.label}（现 {res.old_code} = {'/'.join(cur)}）"
    return out


def process(path: Path, index: dict[str, Any], *, apply: bool, check_only: bool) -> tuple[bool, list[str]]:
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    variant = "listed" if "listed" in path.name else "soe"
    log = [f"=== {path.name} ==="]

    results = resolve_doc(doc, variant, index, apply=apply and not check_only)
    stale = [r for r in results if r.reason == "ok"]
    manual = [r for r in results if r.reason in ("ambiguous", "not_found")]
    ok = [r for r in results if r.reason == "unchanged"]

    log.append(f"共 {len(results)} 行带 report_row_code：已正确 {len(ok)} / 需改写 {len(stale)} / 待人工 {len(manual)}")
    if manual:
        log.append("待人工核对（脚本不改）：")
        log.extend("  ~ " + str(r) for r in manual)

    if check_only:
        if stale:
            log.append(f"[FAIL] {len(stale)} 行编号陈旧：")
            log.extend("  x " + str(r) for r in stale)
            return False, log
        log.append("无陈旧编号")
        return True, log

    if not stale:
        log.append("无需修改")
        return True, log

    log.append(f"改写 {len(stale)} 行：")
    log.extend("  " + str(r) for r in stale)

    if not apply:
        log.append("[dry-run] 未写文件（加 --apply 才写）")
        return True, log

    trailing = "\n" if raw.endswith("\n") else ""
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + trailing, encoding="utf-8")
    log.append(f"已写入 {path}")
    return True, log


def main() -> int:
    ap = argparse.ArgumentParser(description="附注模板 report_row_code 重映射（幂等）")
    ap.add_argument("--dump-index", action="store_true", help="从 DB 物化反查索引")
    ap.add_argument("--dry-run", action="store_true", help="只打印清单（默认行为）")
    ap.add_argument("--apply", action="store_true", help="写入文件")
    ap.add_argument("--check", action="store_true", help="仅校验（供 CI）")
    args = ap.parse_args()

    if args.dump_index:
        payload = dump_index()
        parts = [
            f"{f}: 标签 {len(payload['label_to_codes'][f])} / 编号 {len(payload['code_to_labels'][f])}"
            for f in FAMILIES
        ]
        print(
            f"[OK] 索引已物化 {INDEX_PATH.name}："
            f"report_config 行 {payload['row_count']}；" + "；".join(parts)
        )
        return 0

    index = load_index()
    ok_all = True
    for path in PATHS:
        ok, log = process(path, index, apply=args.apply, check_only=args.check)
        print("\n".join(log))
        print()
        ok_all = ok_all and ok

    if not ok_all:
        print("[FAIL] 存在陈旧编号")
        return 1
    print("[OK] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
