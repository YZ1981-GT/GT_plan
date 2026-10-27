"""存量底稿文件梳理（spec procedure-chain-hardening-and-java-contracts R14）。

生成入口已改为落本底稿自己的文件（procedure-chain-followup-closure R3.3、本 spec R11），存量 ``working_paper.file_path``
仍有历史形态。本模块分类计数（只读），并对能安全处理的几类给出处理：写入只在 ``apply_backlog`` 里、由调用方放行。

一张底稿只落一类：

- ``own_file``：本底稿自己的文件（不动）
- ``empty``：没有文件路径
- ``placeholder``：旧占位路径 ``storage/projects/<项目>/workpapers/...`` 且文件不存在（含链路编排建的内嵌子底稿）
- ``template``：指向共享模板目录（在线保存已 copy-on-write，但打开前仍读共享模板）
- ``missing``：配置了别的路径但文件不存在 —— 可能丢了编辑内容，只报告
- ``rejected``：路径越界（不在允许的存储根内）—— 只报告

可处理的是 ``empty`` / ``placeholder`` / ``template``：本底稿存储位置已有懒加载落的文件 ⇒ 只回写 ``file_path``；
否则 ``template`` 复制所指的模板文件，``empty`` / ``placeholder`` 按模板落文件（找不到模板建空白册）。
``file_path`` 用条件更新（原值未变才写），0 行 ⇒ 删掉刚落的文件。
"""
from __future__ import annotations

import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper, WpIndex

CATEGORIES = ("own_file", "empty", "placeholder", "template", "missing", "rejected")
FIXABLE = frozenset({"empty", "placeholder", "template"})
CATEGORY_LABELS = {
    "own_file": "本底稿自己的文件",
    "empty": "没有文件路径",
    "placeholder": "旧占位路径（文件不存在）",
    "template": "指向共享模板目录",
    "missing": "文件缺失（配置了路径但找不到，只报告）",
    "rejected": "路径越界（只报告）",
}
_PLACEHOLDER = re.compile(r"^\.?[\\/]?storage[\\/]+projects[\\/]+[0-9a-fA-F-]{32,36}[\\/]+workpapers[\\/]+")
_OWN_SUFFIXES = (".xlsx", ".xlsm", ".docx", ".doc")
_SAMPLES = 5


@dataclass(frozen=True)
class BacklogRow:
    wp_id: UUID
    project_id: UUID
    wp_code: str
    wp_name: str
    file_path: str | None
    category: str
    referenced: Path | None  # 解析到的文件（own_file / template）
    own_existing: Path | None  # 本底稿存储位置已有的文件（懒加载落过）

    def to_payload(self) -> dict:
        """契约 workpaper-file-materialization.schema.json 的一行。"""
        return {"wp_id": str(self.wp_id), "project_id": str(self.project_id), "wp_code": self.wp_code,
                "file_path": self.file_path, "category": self.category, "fixable": self.category in FIXABLE}


def own_storage_file(project_id: UUID, wp_id: UUID) -> Path | None:
    """本底稿存储位置（wp_storage/{项目}/{底稿 id}.*）已有的文件；不建目录。"""
    from app.services import wp_template_init_service as _init

    base = _init.STORAGE_DIR / str(project_id) / str(wp_id)
    for suffix in _OWN_SUFFIXES:
        candidate = base.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def classify(raw: str | None) -> tuple[str, Path | None]:
    """``file_path`` 原值 → (分类, 解析到的文件)。"""
    from app.services.workpaper_sync.canonical_paths import TEMPLATE_ROOT, is_within_root
    from app.services.wp_export.wp_file_resolver import resolve_wp_file

    res = resolve_wp_file(raw, wp_code=None, allow_template_fallback=False)
    if res.verdict == "file":
        return ("template" if is_within_root(TEMPLATE_ROOT, res.path) else "own_file"), res.path
    if res.verdict == "empty":
        return "empty", None
    if res.verdict == "path_rejected":
        return "rejected", None
    return ("placeholder" if _PLACEHOLDER.match(str(raw).strip()) else "missing"), None


async def scan_backlog(db: AsyncSession, project_id: UUID | None = None) -> list[BacklogRow]:
    """在用底稿（底稿与索引都未删除）逐份分类。只读。"""
    stmt = (
        sa.select(WorkingPaper.id, WorkingPaper.project_id, WorkingPaper.file_path, WpIndex.wp_code, WpIndex.wp_name)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.is_deleted == sa.false(), WpIndex.is_deleted == sa.false())
        .order_by(WorkingPaper.project_id, WpIndex.wp_code)
    )
    if project_id is not None:
        stmt = stmt.where(WorkingPaper.project_id == project_id)
    rows: list[BacklogRow] = []
    for wp_id, pid, raw, code, name in (await db.execute(stmt)).all():
        category, referenced = classify(raw)
        own = own_storage_file(pid, wp_id) if category in FIXABLE else None
        rows.append(BacklogRow(wp_id, pid, code or "", name or "", raw, category, referenced, own))
    return rows


def summarize(rows: list[BacklogRow], *, skip_codes: frozenset[str] = frozenset()) -> dict:
    """分类计数（总计 / 按项目 / 内嵌子底稿）+ 每类样例；``skip_codes`` = 内嵌在主底稿里的子底稿编码。"""
    totals = Counter(r.category for r in rows)
    by_project: dict[str, Counter] = defaultdict(Counter)
    samples: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_project[str(r.project_id)][r.category] += 1
        if r.category != "own_file" and len(samples[r.category]) < _SAMPLES:
            samples[r.category].append({"project_id": str(r.project_id), "wp_code": r.wp_code, "file_path": r.file_path})
    fixable = [r for r in rows if r.category in FIXABLE]
    return {
        "total": len(rows),
        "totals": {c: totals.get(c, 0) for c in CATEGORIES},
        "labels": CATEGORY_LABELS,
        "fixable": len(fixable),
        "fixable_rebind_only": sum(1 for r in fixable if r.own_existing is not None),
        "skip_sub_workpapers": dict(Counter(r.category for r in rows if r.wp_code in skip_codes)),
        "by_project": {pid: {c: n for c, n in sorted(c_.items())} for pid, c_ in sorted(by_project.items())},
        "samples": dict(samples),
    }


async def _bind(db: AsyncSession, row: BacklogRow, path: Path) -> bool:
    result = await db.execute(
        sa.update(WorkingPaper)
        .where(WorkingPaper.id == row.wp_id, WorkingPaper.file_path.is_not_distinct_from(row.file_path))
        .values(file_path=str(path))
        .execution_options(synchronize_session=False)
    )
    return bool(result.rowcount)


async def apply_backlog(db: AsyncSession, rows: list[BacklogRow], *, scenario_of) -> dict:
    """处理可处理的几类（调用方已放行、已备份原值）。``scenario_of(project_id) -> (scenario, 有外币)``。只 flush 不 commit。"""
    from app.services import wp_template_init_service as _init
    from app.services.wp_generate_file import GeneratedWorkpaperFile, discard_generated_file, materialize_workpaper_file

    done: Counter = Counter()
    for row in rows:
        if row.category not in FIXABLE:
            continue
        if row.own_existing is not None:
            done["rebound" if await _bind(db, row, row.own_existing) else "changed_meanwhile"] += 1
            continue
        if row.category == "template" and row.referenced is not None:
            target = _init.get_workpaper_storage_path(row.project_id, row.wp_id).with_suffix(row.referenced.suffix)
            shutil.copy2(row.referenced, target)
            generated = GeneratedWorkpaperFile(path=target, from_template=True)
        else:
            scenario, has_fc = await scenario_of(row.project_id)
            generated = materialize_workpaper_file(row.project_id, row.wp_id, row.wp_code, row.wp_name,
                                                   scenario=scenario, has_foreign_currency=has_fc)
        if await _bind(db, row, generated.path):
            done["materialized" if generated.from_template else "blank"] += 1
        else:  # 期间被别处改过：不覆盖，删掉刚落的文件
            discard_generated_file(generated)
            done["changed_meanwhile"] += 1
    await db.flush()
    return dict(done)
