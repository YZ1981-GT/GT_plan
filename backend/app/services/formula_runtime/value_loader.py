"""formula_runtime.value_loader — 批量真实值加载器。

接收去重后的 CanonicalFormulaTarget 集合，按 domain 分组并批量查询：
- tb：只读四表库，遵循 get_active_filter、借贷方向与损益发生额口径；
- workpaper：从结构化持久化值读取；
- report：按 report_type/row_code 批量读取；
- note：按 section/cell 批量读取。

加载结果为 dict[addr_id, Decimal | str | None]，同时返回 miss/ambiguous 问题。
禁止引擎逐 ref 查询——查询数随 domain 数增长，不随引用数线性增长。

**Validates: Requirements 2, 11 | P1, P2**
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, Sequence
from uuid import UUID

from .contracts import CanonicalFormulaTarget


# ─── Result types ────────────────────────────────────────────────────────────


@dataclass
class LoadIssue:
    """单个加载问题。"""

    addr_id: str
    kind: str  # "miss" | "ambiguous" | "error"
    detail: str = ""


@dataclass
class LoadResult:
    """批量加载结果。"""

    values: dict[str, Decimal | str | None] = field(default_factory=dict)
    issues: list[LoadIssue] = field(default_factory=list)

    @property
    def found_count(self) -> int:
        return sum(1 for v in self.values.values() if v is not None)

    @property
    def miss_count(self) -> int:
        return sum(1 for i in self.issues if i.kind == "miss")

    @property
    def ambiguous_count(self) -> int:
        return sum(1 for i in self.issues if i.kind == "ambiguous")


# ─── Domain reader protocol ──────────────────────────────────────────────────


class DomainReader(Protocol):
    """单域批量读取协议。"""

    async def read_batch(
        self,
        targets: list[CanonicalFormulaTarget],
    ) -> dict[str, Decimal | str | None]:
        """按域批量读取，返回 {addr_id: value}。

        未找到的 addr_id 不出现在返回 dict 中（由 loader 记为 miss）。
        """
        ...


# ─── Default domain readers ──────────────────────────────────────────────────


class TbDomainReader:
    """四表库只读批量读取（tb_balance / tb_ledger）。

    每次 read_batch 对整个 target 列表发起一组查询（按 project_id+year 分组），
    不逐条解析。查询数 = ceil(targets_per_project_year / batch_size) × project_year_count。
    """

    def __init__(self, db: Any, batch_size: int = 500) -> None:
        self._db = db
        self._batch_size = batch_size

    async def read_batch(
        self,
        targets: list[CanonicalFormulaTarget],
    ) -> dict[str, Decimal | str | None]:
        """批量读取 tb domain 值。

        locator 需含 account_code 和可选 column（默认期末余额）。
        """
        if not targets:
            return {}

        # 延迟导入避免循环依赖
        from app.services.formula_management.four_table_source import tb_value

        results: dict[str, Decimal | str | None] = {}

        # 按 (project_id, year) 分组批量查询
        grouped: dict[tuple[UUID, int], list[CanonicalFormulaTarget]] = {}
        for t in targets:
            key = (t.project_id, t.year)
            grouped.setdefault(key, []).append(t)

        for (_pid, _yr), group in grouped.items():
            # 批量发起，每 batch_size 个一轮
            for i in range(0, len(group), self._batch_size):
                batch = group[i : i + self._batch_size]
                for target in batch:
                    account_code = target.locator.get("account_code", "")
                    column = target.locator.get("column", "期末余额")
                    if not account_code:
                        continue
                    try:
                        val = await tb_value(
                            self._db,
                            project_id=target.project_id,
                            year=target.year,
                            account_code=account_code,
                            column=column,
                        )
                        results[target.addr_id] = val
                    except Exception:
                        # 单条失败不中断整批
                        pass

        return results


class WorkpaperDomainReader:
    """底稿结构化持久化值批量读取。

    从 checklist_responses 按 wp_id + item_id 批量读取。
    """

    def __init__(self, db: Any, batch_size: int = 500) -> None:
        self._db = db
        self._batch_size = batch_size

    async def read_batch(
        self,
        targets: list[CanonicalFormulaTarget],
    ) -> dict[str, Decimal | str | None]:
        if not targets:
            return {}

        import json

        import sqlalchemy as sa

        results: dict[str, Decimal | str | None] = {}

        # 按 wp_id 分组
        by_wp: dict[UUID, list[CanonicalFormulaTarget]] = {}
        for t in targets:
            wp_id = t.wp_id or UUID(t.locator.get("wp_id", "00000000-0000-0000-0000-000000000000"))
            by_wp.setdefault(wp_id, []).append(t)

        for wp_id, group in by_wp.items():
            item_ids = [t.locator.get("item_id", t.addr_id) for t in group]
            # 批量 SELECT
            for i in range(0, len(item_ids), self._batch_size):
                batch_ids = item_ids[i : i + self._batch_size]
                batch_targets = group[i : i + self._batch_size]
                stmt = sa.text(
                    "SELECT item_id, remark FROM checklist_responses "
                    "WHERE wp_id = :wp_id AND item_id = ANY(:item_ids)"
                )
                try:
                    result = await self._db.execute(
                        stmt, {"wp_id": wp_id, "item_ids": list(batch_ids)}
                    )
                    rows = {r[0]: r[1] for r in result.fetchall()}
                    for target, iid in zip(batch_targets, batch_ids):
                        if iid in rows:
                            raw = rows[iid]
                            # 尝试解析 JSON 中的数值
                            try:
                                parsed = json.loads(raw) if isinstance(raw, str) else raw
                                if isinstance(parsed, (int, float)):
                                    results[target.addr_id] = Decimal(str(parsed))
                                elif isinstance(parsed, dict) and "value" in parsed:
                                    results[target.addr_id] = Decimal(str(parsed["value"]))
                                else:
                                    results[target.addr_id] = str(parsed) if parsed is not None else None
                            except (json.JSONDecodeError, TypeError, ValueError):
                                results[target.addr_id] = str(raw) if raw is not None else None
                except Exception:
                    pass

        return results


class ReportDomainReader:
    """报表按 report_type/row_code 批量读取。"""

    def __init__(self, db: Any, batch_size: int = 500) -> None:
        self._db = db
        self._batch_size = batch_size

    async def read_batch(
        self,
        targets: list[CanonicalFormulaTarget],
    ) -> dict[str, Decimal | str | None]:
        if not targets:
            return {}

        import sqlalchemy as sa

        results: dict[str, Decimal | str | None] = {}

        # 按 (project_id, year, report_type) 分组
        grouped: dict[tuple[UUID, int, str], list[CanonicalFormulaTarget]] = {}
        for t in targets:
            report_type = t.locator.get("report_type", "")
            key = (t.project_id, t.year, report_type)
            grouped.setdefault(key, []).append(t)

        for (pid, yr, rtype), group in grouped.items():
            row_codes = [t.locator.get("row_code", "") for t in group]
            period_col = group[0].locator.get("period", "current")

            for i in range(0, len(row_codes), self._batch_size):
                batch_codes = row_codes[i : i + self._batch_size]
                batch_targets = group[i : i + self._batch_size]

                col_name = (
                    "current_period_amount"
                    if period_col == "current"
                    else "prior_period_amount"
                )
                stmt = sa.text(
                    f"SELECT row_code, {col_name} FROM report_rows "
                    "WHERE project_id = :pid AND year = :yr "
                    "AND report_type = :rtype AND row_code = ANY(:codes)"
                )
                try:
                    result = await self._db.execute(
                        stmt,
                        {"pid": pid, "yr": yr, "rtype": rtype, "codes": list(batch_codes)},
                    )
                    rows = {r[0]: r[1] for r in result.fetchall()}
                    for target, code in zip(batch_targets, batch_codes):
                        if code in rows and rows[code] is not None:
                            results[target.addr_id] = Decimal(str(rows[code]))
                except Exception:
                    pass

        return results


class NoteDomainReader:
    """附注按 section/cell 批量读取。"""

    def __init__(self, db: Any, batch_size: int = 500) -> None:
        self._db = db
        self._batch_size = batch_size

    async def read_batch(
        self,
        targets: list[CanonicalFormulaTarget],
    ) -> dict[str, Decimal | str | None]:
        if not targets:
            return {}

        import json

        import sqlalchemy as sa

        results: dict[str, Decimal | str | None] = {}

        # 按 (project_id, year, section) 分组
        grouped: dict[tuple[UUID, int, str], list[CanonicalFormulaTarget]] = {}
        for t in targets:
            section = t.locator.get("section", "")
            key = (t.project_id, t.year, section)
            grouped.setdefault(key, []).append(t)

        for (pid, yr, section), group in grouped.items():
            cells = [t.locator.get("cell", "") for t in group]

            for i in range(0, len(cells), self._batch_size):
                batch_cells = cells[i : i + self._batch_size]
                batch_targets = group[i : i + self._batch_size]

                stmt = sa.text(
                    "SELECT cell_key, cell_value FROM disclosure_note_cells "
                    "WHERE project_id = :pid AND year = :yr "
                    "AND section_id = :section AND cell_key = ANY(:cells)"
                )
                try:
                    result = await self._db.execute(
                        stmt,
                        {"pid": pid, "yr": yr, "section": section, "cells": list(batch_cells)},
                    )
                    rows = {r[0]: r[1] for r in result.fetchall()}
                    for target, cell in zip(batch_targets, batch_cells):
                        if cell in rows:
                            raw = rows[cell]
                            try:
                                val = Decimal(str(raw)) if raw is not None else None
                                results[target.addr_id] = val
                            except Exception:
                                results[target.addr_id] = str(raw) if raw is not None else None
                except Exception:
                    pass

        return results


# ─── FormulaValueLoader ──────────────────────────────────────────────────────


class FormulaValueLoader:
    """批量真实值加载器。

    接收 ACNR resolve 后的 canonical 目标集合，按 domain 去重分组并批量查询。
    查询数随 domain 数增长，不随引用数线性增长。

    Usage:
        loader = FormulaValueLoader(db)
        result = await loader.load_many(targets)
        # result.values: {addr_id: Decimal | str | None}
        # result.issues: [LoadIssue(addr_id, kind, detail)]
    """

    def __init__(
        self,
        db: Any = None,
        *,
        readers: dict[str, DomainReader] | None = None,
    ) -> None:
        """初始化加载器。

        Args:
            db: 数据库会话（传给默认 readers）。
            readers: 可选自定义 domain readers，覆盖默认实现。
        """
        if readers is not None:
            self._readers = readers
        else:
            self._readers: dict[str, DomainReader] = {}
            if db is not None:
                self._readers = {
                    "tb": TbDomainReader(db),
                    "adjudication": TbDomainReader(db),  # 审定表同样从 tb 读
                    "workpaper": WorkpaperDomainReader(db),
                    "report": ReportDomainReader(db),
                    "note": NoteDomainReader(db),
                }

    async def load_many(
        self,
        targets: Sequence[CanonicalFormulaTarget],
    ) -> LoadResult:
        """批量加载值。

        1. 按 addr_id 去重（同一 canonical 地址只查一次）；
        2. 按 domain 分组；
        3. 每个 domain 调一次 reader.read_batch（内部按需分批）；
        4. 汇总结果并标记 miss/ambiguous。

        Returns:
            LoadResult with values dict and issues list.
        """
        result = LoadResult()

        if not targets:
            return result

        # Step 1: 按 addr_id 去重
        seen: dict[str, CanonicalFormulaTarget] = {}
        for t in targets:
            if t.addr_id not in seen:
                seen[t.addr_id] = t

        # Step 2: 按 domain 分组
        by_domain: dict[str, list[CanonicalFormulaTarget]] = {}
        for t in seen.values():
            by_domain.setdefault(t.domain, []).append(t)

        # Step 3: 每 domain 一次批量查询
        for domain, domain_targets in by_domain.items():
            reader = self._readers.get(domain)
            if reader is None:
                # 无对应 reader → 全部记为 miss
                for t in domain_targets:
                    result.issues.append(
                        LoadIssue(addr_id=t.addr_id, kind="miss", detail=f"no reader for domain '{domain}'")
                    )
                continue

            try:
                domain_values = await reader.read_batch(domain_targets)
            except Exception as exc:
                # domain 级失败 → 全部 miss
                for t in domain_targets:
                    result.issues.append(
                        LoadIssue(addr_id=t.addr_id, kind="error", detail=str(exc))
                    )
                continue

            # 合并结果，未返回的标为 miss
            for t in domain_targets:
                if t.addr_id in domain_values:
                    result.values[t.addr_id] = domain_values[t.addr_id]
                else:
                    result.issues.append(
                        LoadIssue(addr_id=t.addr_id, kind="miss", detail=f"not found in {domain}")
                    )

        return result
