"""FormulaReverseIndex — 反向联动索引 (Sprint 3)

被引用方 → 引用方 反向索引：
- "TB:1122::期末余额" → ["WP:D2:审定表D2-1:未审数", "REPORT:BS-005::当期金额"]
- "WP:H1:折旧分配分析表H1-13:销售费用折旧" → ["WP:K8:审定表K8-1:折旧"]

数据源：
1. prefill_formula_mapping.json — 解析 =TB()/=WP()/=ADJ()/=NOTE() 公式
2. report_config DB — 解析 TB()/SUM_TB()/ROW() 公式
3. cross_wp_references.json — targets[].formula 中的 =WP() 引用

Validates: Requirements F9, F10, F11, F12, F13, F14, F15
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Data directory
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# ─── Regex patterns for formula parsing ─────────────────────────────────────

# =TB('1122','期末余额')
_RE_TB = re.compile(r"TB\('([^']+)','([^']+)'\)")
# =SUM_TB('1401~1499','期末余额')
_RE_SUM_TB = re.compile(r"SUM_TB\('([^']+)','([^']+)'\)")
# =ADJ('1122','aje')
_RE_ADJ = re.compile(r"ADJ\('([^']+)','([^']+)'\)")
# =WP('H1','折旧分配分析表H1-13','销售费用折旧')
_RE_WP = re.compile(r"WP\('([^']+)','([^']+)','([^']+)'\)")
# =NOTE('5.7','应收账款','期末余额')
_RE_NOTE = re.compile(r"NOTE\('([^']+)','([^']+)','([^']+)'\)")
# =PREV('D2','审定表D2-1','审定数')
_RE_PREV = re.compile(r"PREV\('([^']+)','([^']+)','([^']+)'\)")
# ROW('BS-009')
_RE_ROW = re.compile(r"ROW\('([^']+)'\)")


class FormulaReverseIndex:
    """被引用方 → 引用方 反向索引。

    build() 从 3 个数据源构建反向索引：
    1. prefill_formula_mapping.json — 每条公式的引用目标
    2. report_config.formula — TB()/SUM_TB()/ROW() 引用
    3. cross_wp_references.json — targets[].formula 中的 =WP() 引用

    query(changed_uri) 返回引用方 URI 列表（"谁引用了我"）。
    """

    def __init__(self, db: AsyncSession | None = None):
        self._db = db
        self._index: dict[str, list[str]] = defaultdict(list)
        self._built: bool = False

    # ─── Public API ───────────────────────────────────────────────────

    async def build(self) -> dict[str, list[str]]:
        """从 3 个数据源构建反向索引。

        Returns:
            dict mapping source_uri → list of referencing URIs
        """
        self._index.clear()

        # 1. prefill_formula_mapping.json
        self.build_from_prefill_mapping()

        # 2. report_config DB
        if self._db:
            await self.build_from_report_config()

        # 3. cross_wp_references.json
        self._build_from_cross_wp_references()

        self._built = True
        logger.info(
            "FormulaReverseIndex built: %d source URIs indexed",
            len(self._index),
        )
        return dict(self._index)

    def query(self, changed_uri: str) -> list[str]:
        """返回引用方 URI 列表（"谁引用了 changed_uri"）。

        Parameters
        ----------
        changed_uri : str
            变更源 URI，格式 {module}:{code}:{sheet_name}:{label}

        Returns
        -------
        list[str]
            引用了 changed_uri 的 URI 列表
        """
        if not self._built:
            logger.warning("FormulaReverseIndex.query called before build()")
            return []

        results: list[str] = []

        # Exact match
        if changed_uri in self._index:
            results.extend(self._index[changed_uri])

        # Prefix match for broader queries (e.g., "TB:1122::" matches "TB:1122::期末余额")
        # Only do prefix match if exact match yields nothing and URI has empty trailing segments
        if not results:
            parts = changed_uri.split(":")
            if len(parts) >= 2:
                prefix = f"{parts[0]}:{parts[1]}:"
                for key, refs in self._index.items():
                    if key.startswith(prefix) and key != changed_uri:
                        results.extend(refs)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for uri in results:
            if uri not in seen:
                seen.add(uri)
                unique.append(uri)

        return unique

    # ─── Data Source 1: prefill_formula_mapping.json ──────────────────

    def build_from_prefill_mapping(self) -> None:
        """解析 prefill_formula_mapping.json 中的 =TB()/=WP()/=ADJ()/=NOTE() 公式。

        每条 mapping 的 cells[].formula 引用了某个源 URI，
        而 cell 本身属于某个底稿（WP:{wp_code}:{sheet}:{cell_ref}）。
        反向索引：源 URI → 引用方底稿 URI。
        """
        path = DATA_DIR / "prefill_formula_mapping.json"
        if not path.exists():
            logger.warning("prefill_formula_mapping.json not found, skipping")
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read prefill_formula_mapping.json: %s", e)
            return

        mappings = data.get("mappings", [])
        for mapping in mappings:
            wp_code = mapping.get("wp_code", "")
            sheet = mapping.get("sheet", "")
            cells = mapping.get("cells", [])

            for cell in cells:
                formula = cell.get("formula", "")
                cell_ref = cell.get("cell_ref", "")
                if not formula:
                    continue

                # The referencing URI (who uses the source)
                referencing_uri = f"WP:{wp_code}:{sheet}:{cell_ref}"

                # Parse formula to find source URIs
                source_uris = self._parse_formula_sources(formula)
                for source_uri in source_uris:
                    self._index[source_uri].append(referencing_uri)

    # ─── Data Source 2: report_config DB ─────────────────────────────

    async def build_from_report_config(self) -> None:
        """解析 report_config.formula 中 TB()/SUM_TB()/ROW() 公式。

        每行 report_config 的 formula 引用了 TB 科目或其他报表行，
        而该行本身是 REPORT:{row_code}::{report_type}。
        反向索引：TB/REPORT 源 URI → 引用方报表行 URI。
        """
        if not self._db:
            return

        try:
            result = await self._db.execute(
                text(
                    "SELECT row_code, formula, report_type::text, applicable_standard "
                    "FROM report_config "
                    "WHERE formula IS NOT NULL AND formula != '' "
                    "AND is_deleted = false"
                )
            )
            rows = result.fetchall()
        except Exception as e:
            logger.warning("Failed to query report_config for reverse index: %s", e)
            try:
                await self._db.rollback()
            except Exception:
                pass
            return

        for row in rows:
            row_code = row[0]
            formula = row[1]
            report_type = row[2] if len(row) > 2 else ""
            std = row[3] if len(row) > 3 else ""

            # The referencing URI (the report row that uses the formula)
            referencing_uri = f"REPORT:{row_code}:{std or ''}:{report_type or ''}"

            # Parse formula to find source URIs
            source_uris = self._parse_report_formula_sources(formula)
            for source_uri in source_uris:
                self._index[source_uri].append(referencing_uri)

    # ─── Data Source 3: cross_wp_references.json ─────────────────────

    def _build_from_cross_wp_references(self) -> None:
        """解析 cross_wp_references.json 中的跨底稿引用。

        每条 reference 的 source → targets 表示 source 底稿引用了 target 底稿。
        反向索引：target URI → source URI（"target 被 source 引用"）。
        """
        path = DATA_DIR / "cross_wp_references.json"
        if not path.exists():
            logger.warning("cross_wp_references.json not found, skipping")
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read cross_wp_references.json: %s", e)
            return

        references = data.get("references", [])
        for ref in references:
            source_wp = ref.get("source_wp", "")
            source_sheet = ref.get("source_sheet", "")
            source_label = ref.get("source_cell_label", ref.get("source_cell", ""))

            # The referencing URI (who does the referencing)
            referencing_uri = f"WP:{source_wp}:{source_sheet}:{source_label}"

            targets = ref.get("targets", [])
            for target in targets:
                target_wp = target.get("wp_code", "")
                target_sheet = target.get("sheet", "")
                target_label = target.get("cell_label", target.get("cell", ""))

                # The source URI (who is being referenced)
                source_uri = f"WP:{target_wp}:{target_sheet}:{target_label}"
                self._index[source_uri].append(referencing_uri)

    # ─── Formula Parsing Helpers ─────────────────────────────────────

    def _parse_formula_sources(self, formula: str) -> list[str]:
        """解析预填充公式，返回被引用的源 URI 列表。"""
        uris: list[str] = []
        if not formula:
            return uris

        # =TB('1122','期末余额') → TB:1122::期末余额
        for m in _RE_TB.finditer(formula):
            code, label = m.groups()
            uris.append(f"TB:{code}::{label}")

        # =SUM_TB('1401~1499','期末余额') → TB:1401~1499::期末余额
        for m in _RE_SUM_TB.finditer(formula):
            code_range, label = m.groups()
            uris.append(f"TB:{code_range}::{label}")

        # =ADJ('1122','aje') → ADJ:1122::aje
        for m in _RE_ADJ.finditer(formula):
            code, adj_type = m.groups()
            uris.append(f"ADJ:{code}::{adj_type}")

        # =WP('H1','折旧分配分析表H1-13','销售费用折旧') → WP:H1:折旧分配分析表H1-13:销售费用折旧
        for m in _RE_WP.finditer(formula):
            wp, sheet, field = m.groups()
            uris.append(f"WP:{wp}:{sheet}:{field}")

        # =NOTE('5.7','应收账款','期末余额') → NOTE:5.7:应收账款:期末余额
        for m in _RE_NOTE.finditer(formula):
            section, name, field = m.groups()
            uris.append(f"NOTE:{section}:{name}:{field}")

        # =PREV('D2','审定表D2-1','审定数') → WP:D2:审定表D2-1:审定数
        for m in _RE_PREV.finditer(formula):
            wp, sheet, field = m.groups()
            uris.append(f"WP:{wp}:{sheet}:{field}")

        return uris

    def _parse_report_formula_sources(self, formula: str) -> list[str]:
        """解析 report_config.formula 中的 TB()/SUM_TB()/ROW()。"""
        uris: list[str] = []
        if not formula:
            return uris

        # TB('1002','期末余额')
        for m in _RE_TB.finditer(formula):
            code, label = m.groups()
            uris.append(f"TB:{code}::{label}")

        # SUM_TB('1401~1499','期末余额')
        for m in _RE_SUM_TB.finditer(formula):
            code_range, label = m.groups()
            uris.append(f"TB:{code_range}::{label}")

        # ROW('BS-009')
        for m in _RE_ROW.finditer(formula):
            row_code = m.group(1)
            uris.append(f"REPORT:{row_code}::")

        return uris

    @property
    def is_built(self) -> bool:
        """是否已构建索引。"""
        return self._built

    @property
    def index_size(self) -> int:
        """索引中源 URI 数量。"""
        return len(self._index)


# ─── Module-level singleton with lazy build ───────────────────────────────

_singleton: FormulaReverseIndex | None = None
_singleton_lock = None  # asyncio.Lock created on first use


async def get_reverse_index(db: AsyncSession | None = None, *, force_rebuild: bool = False) -> FormulaReverseIndex:
    """获取共享的 FormulaReverseIndex 单例。

    避免每次 API 调用都重建索引（spec 复盘 P1.1）。

    - 首次调用时构建
    - force_rebuild=True 时强制重建（如 prefill_mapping JSON 改动后）
    - 并发安全（asyncio.Lock）
    """
    global _singleton, _singleton_lock
    import asyncio

    if _singleton_lock is None:
        _singleton_lock = asyncio.Lock()

    async with _singleton_lock:
        if _singleton is None or force_rebuild:
            idx = FormulaReverseIndex(db=db)
            await idx.build()
            _singleton = idx
        return _singleton


def invalidate_reverse_index() -> None:
    """触发下次访问时重建（如 JSON 文件 mtime 变化）。"""
    global _singleton
    _singleton = None
