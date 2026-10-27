"""抽凭 / 截止测试的「已抽排除」与批次比较：按凭证键与分录指纹（spec voucher-identity-writeback-and-audit-phase
任务 5，需求 2.4 / 2.6）。

回填日志 ``extraction_criteria`` 里的样本身份：

- 新格式：``filled_line_fps``（分录指纹）+ ``filled_voucher_keys``（凭证键）。账套重导后行 id 全换，
  指纹经 :func:`resolve_line_fps` 映射到当前账套的行；凭证键按行值 NOT IN 整张排除。
- 旧格式：只有 ``filled_voucher_nos``（凭证号）/ ``filled_unit_ids``（行 id）。按旧口径兼容 ——
  凭证号整张排除（会连带同号别日、同日同号别凭证字的凭证），行 id 只在原账套有效 ——
  并在抽凭历史与抽凭结果上标 ``legacy_exclusion``（「旧记录按凭证号排除」）。

排除粒度：分录行单位按分录（指纹）；整张凭证单位与截止测试按凭证（凭证键）；
项目级（exclude_scope=project）按登记表里的凭证键整张排除。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import WorkpaperExtractionLog
from app.services.voucher_identity import (
    LineFingerprint,
    VoucherKey,
    norm_text,
    parse_voucher_keys,
    resolve_line_fps,
    voucher_label,
)


def _texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(norm_text(v) for v in value if norm_text(v)))


@dataclass(frozen=True)
class LogIdentity:
    """一条回填日志里的样本身份（新格式与旧格式二选一）。"""

    line_fps: tuple[str, ...] = ()
    voucher_keys: tuple[VoucherKey, ...] = ()
    legacy_voucher_nos: tuple[str, ...] = ()
    legacy_line_ids: tuple[str, ...] = ()

    @property
    def is_new(self) -> bool:
        return bool(self.line_fps or self.voucher_keys)

    @property
    def legacy(self) -> bool:
        """只有凭证号 / 行 id 的旧日志（它参与的排除按旧口径）。"""
        return not self.is_new and bool(self.legacy_voucher_nos or self.legacy_line_ids)


def log_identity(criteria: Any) -> LogIdentity:
    if not isinstance(criteria, dict):
        return LogIdentity()
    fps = tuple(_texts(criteria.get("filled_line_fps")))
    keys = list(parse_voucher_keys(criteria.get("filled_voucher_keys") or []))
    if fps and not keys:  # 只记了指纹：凭证键从指纹里取
        for fp in fps:
            try:
                vk = LineFingerprint.parse(fp).vk
            except ValueError:
                continue
            if vk not in keys:
                keys.append(vk)
    if fps or keys:
        return LogIdentity(line_fps=fps, voucher_keys=tuple(keys))
    return LogIdentity(
        legacy_voucher_nos=tuple(_texts(criteria.get("filled_voucher_nos"))),
        legacy_line_ids=tuple(_texts(criteria.get("filled_unit_ids"))),
    )


@dataclass
class SamplingExclusions:
    """一次抽样要排除的已抽样本（对应 LedgerQueryFilters 的四个 exclude_* 字段）。"""

    voucher_keys: list[str] = field(default_factory=list)  # 凭证键串：整张排除
    line_ids: list[str] = field(default_factory=list)  # 当前账套分录行 id：逐条排除
    voucher_nos: list[str] = field(default_factory=list)  # 旧日志 / 旧登记：凭证号整张排除
    legacy_line_ids: list[str] = field(default_factory=list)  # 旧日志记的行 id（只在原账套有效）
    legacy: bool = False  # 有旧口径参与
    unresolved_line_fps: int = 0  # 当前账套里找不到的已抽分录（分录已改或已删）

    def filter_kwargs(self) -> dict[str, list[str]]:
        """交给 LedgerQueryFilters 的四个 exclude_* 字段（抽凭与截止测试两个路由共用这一映射）。"""
        return {
            "exclude_voucher_keys": list(self.voucher_keys),
            "exclude_line_ids": list(self.line_ids),
            "exclude_voucher_nos": list(self.voucher_nos),
            "exclude_unit_ids": list(self.legacy_line_ids),
        }

    def to_stats(self) -> dict[str, Any]:
        return {
            "excluded_voucher_count": len(self.voucher_keys),
            "excluded_line_count": len(self.line_ids),
            "legacy_exclusion": self.legacy,
            "legacy_excluded_voucher_nos": len(self.voucher_nos),
            "unresolved_excluded_lines": self.unresolved_line_fps,
        }


async def collect_exclusions(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    workpaper_id: UUID,
    extraction_type: str,
    sampling_unit: str,
    exclude_extracted: bool,
    phase: str | None = None,
    exclude_scope: str = "workpaper",
) -> SamplingExclusions:
    """收集本次抽样要排除的已抽样本。

    - ``exclude_extracted``：本底稿该类型未撤销的回填全部排除；
    - ``phase == "final"``：另外排除本底稿预审回填（关掉 exclude_extracted 也排除 —— 年审不重抽预审样本）；
    - ``exclude_scope == "project"``（且 exclude_extracted）：叠加登记表里的项目级已抽凭证。
    """
    from app.services.sampled_voucher_queries import project_level_extracted_vouchers

    out = SamplingExclusions()
    if not exclude_extracted and phase != "final":
        return out
    rows = (
        await db.execute(
            sa.select(WorkpaperExtractionLog.extraction_criteria).where(
                WorkpaperExtractionLog.workpaper_id == workpaper_id,
                WorkpaperExtractionLog.extraction_type == extraction_type,
                WorkpaperExtractionLog.is_undone == sa.false(),
            )
        )
    ).scalars().all()

    by_line = sampling_unit == "ledger_line"
    fps: dict[str, None] = {}
    keys: dict[str, None] = {}
    nos: dict[str, None] = {}
    old_ids: dict[str, None] = {}
    for criteria in rows:
        if not isinstance(criteria, dict):
            continue
        if not exclude_extracted and criteria.get("phase") != "preliminary":
            continue
        ident = log_identity(criteria)
        if by_line and ident.line_fps:
            fps.update(dict.fromkeys(ident.line_fps))
        elif ident.voucher_keys:
            keys.update(dict.fromkeys(k.to_str() for k in ident.voucher_keys))
        elif ident.legacy:
            out.legacy = True
            if by_line and ident.legacy_line_ids:
                old_ids.update(dict.fromkeys(ident.legacy_line_ids))
            else:
                nos.update(dict.fromkeys(ident.legacy_voucher_nos))

    if fps:
        resolved = await resolve_line_fps(db, project_id=project_id, year=year, fps=list(fps))
        out.line_ids = sorted({str(v) for v in resolved.values()})
        out.unresolved_line_fps = len(fps) - len(resolved)
    if exclude_extracted and exclude_scope == "project":
        reg_keys, reg_nos = await project_level_extracted_vouchers(db, project_id, year)
        keys.update(dict.fromkeys(k.to_str() for k in reg_keys))
        if reg_nos:
            out.legacy = True
            nos.update(dict.fromkeys(reg_nos))
    out.voucher_keys, out.voucher_nos, out.legacy_line_ids = list(keys), list(nos), list(old_ids)
    return out


def _legacy_voucher_nos(criteria: Any, before_data: Any) -> set[str]:
    nos = set(_texts(criteria.get("filled_voucher_nos"))) if isinstance(criteria, dict) else set()
    if not nos and isinstance(before_data, list):
        nos = {norm_text(r["voucher_no"]) for r in before_data if isinstance(r, dict) and norm_text(r.get("voucher_no"))}
    return nos


def compare_identity(record_a: Any, record_b: Any) -> tuple[set[str], set[str], str]:
    """两批回填的比较口径：都有凭证键时按凭证（称呼「2025-01-07 FY-0003」）；否则按凭证号（旧口径）。"""
    a, b = log_identity(record_a.extraction_criteria), log_identity(record_b.extraction_criteria)
    if a.voucher_keys and b.voucher_keys:
        return {voucher_label(k) for k in a.voucher_keys}, {voucher_label(k) for k in b.voucher_keys}, "voucher_key"
    return (
        _legacy_voucher_nos(record_a.extraction_criteria, record_a.before_data),
        _legacy_voucher_nos(record_b.extraction_criteria, record_b.before_data),
        "voucher_no",
    )
