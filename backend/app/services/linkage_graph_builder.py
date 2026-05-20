"""统一依赖图构建器 — Unified Linkage Bus

从 6 个数据源合并构建统一依赖图：
1. prefill_formula_mapping.json → TB/ADJ/WP/PREV 边
2. cross_wp_references.json → WP→WP/NOTE/REPORT 边
3. report_config DB → TB→REPORT / ROW→REPORT 边
4. address_registry_l3_dependencies.json → 同文件跨 sheet 边
5. note_account_mapping DB → WP→NOTE 边
6. account_mapping DB → MAPPING→TB/WP/REPORT 边

输出格式：unified_dependency_graph.json
{
  "nodes": [{"uri": "...", "module": "...", "code": "..."}],
  "edges": [{"source": "...", "target": "...", "type": "...", "severity": "..."}]
}
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Data directory
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class LinkageGraphBuilder:
    """统一依赖图构建器：从 6 个数据源合并构建全局依赖图。"""

    def __init__(self, db: AsyncSession | None = None):
        self._db = db
        self._nodes: dict[str, dict[str, Any]] = {}  # uri -> node dict
        self._edges: list[dict[str, Any]] = []

    # ─── Public API ───────────────────────────────────────────────

    async def build(self) -> dict[str, Any]:
        """构建统一依赖图（主入口）。

        Returns:
            {"nodes": [...], "edges": [...]}
        """
        # 1. JSON 数据源（不需要 DB）
        self._from_prefill_mapping()
        self._from_cross_wp_references()
        self._from_l3_dependencies()
        self._from_docx_placeholders()

        # 2. DB 数据源（需要 async session）
        if self._db:
            await self._from_report_config()
            await self._from_note_account_mapping()
            await self._from_account_mapping()

        # 3. Formula reverse index (Sprint 3)
        await self._build_formula_reverse_index()

        # 4. 去重 + 输出
        self._deduplicate()

        graph = {
            "nodes": list(self._nodes.values()),
            "edges": self._edges,
        }

        # 持久化到 JSON
        output_path = DATA_DIR / "unified_dependency_graph.json"
        output_path.write_text(
            json.dumps(graph, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "Unified dependency graph built: %d nodes, %d edges → %s",
            len(graph["nodes"]),
            len(graph["edges"]),
            output_path,
        )

        # 自动通知 stale_engine + reverse_index 重建（spec 复盘 P1.2）
        try:
            from app.services.stale_propagation_engine import stale_engine
            stale_engine.reload_graph()

            from app.services.formula_reverse_index import invalidate_reverse_index
            invalidate_reverse_index()
        except Exception as e:
            logger.warning("Failed to reload downstream consumers: %s", e)

        return graph

    # ─── Data Source 1: prefill_formula_mapping.json ──────────────

    def _from_prefill_mapping(self) -> None:
        """解析 prefill_formula_mapping.json → TB/ADJ/WP/PREV 边。"""
        path = DATA_DIR / "prefill_formula_mapping.json"
        if not path.exists():
            logger.warning("prefill_formula_mapping.json not found, skipping")
            return

        data = json.loads(path.read_text(encoding="utf-8"))
        mappings = data.get("mappings", [])

        for mapping in mappings:
            wp_code = mapping.get("wp_code", "")
            sheet = mapping.get("sheet", "")
            cells = mapping.get("cells", [])

            for cell in cells:
                formula = cell.get("formula", "")
                cell_ref = cell.get("cell_ref", "")
                formula_type = cell.get("formula_type", "")

                # Target node: the cell being filled
                target_uri = f"WP:{wp_code}:{sheet}:{cell_ref}"
                self._ensure_node(target_uri, "WP", wp_code)

                # Parse formula to extract source
                source_uri = self._parse_prefill_formula(formula, formula_type)
                if source_uri:
                    self._ensure_node(source_uri, *self._parse_uri_parts(source_uri))
                    self._add_edge(source_uri, target_uri, "data_flow", "blocking")

    def _parse_prefill_formula(self, formula: str, formula_type: str) -> str | None:
        """解析预填充公式，返回 source URI。"""
        if not formula:
            return None

        # =TB('1122','期末余额') → TB:1122::期末余额
        tb_match = re.match(r"=TB\('([^']+)','([^']+)'\)", formula)
        if tb_match:
            code, label = tb_match.groups()
            return f"TB:{code}::{label}"

        # =TB_SUM('1121~1122','期末余额') → TB:1121~1122::期末余额
        tb_sum_match = re.match(r"=TB_SUM\('([^']+)','([^']+)'\)", formula)
        if tb_sum_match:
            code_range, label = tb_sum_match.groups()
            return f"TB:{code_range}::{label}"

        # =ADJ('1122','aje') → ADJ:1122::aje
        adj_match = re.match(r"=ADJ\('([^']+)','([^']+)'\)", formula)
        if adj_match:
            code, adj_type = adj_match.groups()
            return f"ADJ:{code}::{adj_type}"

        # =PREV('D2','审定表D2-1','审定数') → WP:D2:审定表D2-1:审定数 (PREV)
        prev_match = re.match(r"=PREV\('([^']+)','([^']+)','([^']+)'\)", formula)
        if prev_match:
            wp, sheet, field = prev_match.groups()
            return f"WP:{wp}:{sheet}:{field}"

        # =WP('H1','折旧分配分析表H1-13','销售费用折旧') → WP:H1:折旧分配分析表H1-13:销售费用折旧
        wp_match = re.match(r"=WP\('([^']+)','([^']+)','([^']+)'\)", formula)
        if wp_match:
            wp, sheet, field = wp_match.groups()
            return f"WP:{wp}:{sheet}:{field}"

        return None

    # ─── Data Source 2: cross_wp_references.json ─────────────────

    def _from_cross_wp_references(self) -> None:
        """解析 cross_wp_references.json → WP→WP/NOTE/REPORT 边。"""
        path = DATA_DIR / "cross_wp_references.json"
        if not path.exists():
            logger.warning("cross_wp_references.json not found, skipping")
            return

        data = json.loads(path.read_text(encoding="utf-8"))
        references = data.get("references", [])

        for ref in references:
            source_wp = ref.get("source_wp", "")
            source_sheet = ref.get("source_sheet", "")
            source_cell_label = ref.get("source_cell_label", ref.get("source_cell", ""))
            severity = ref.get("severity", "warning")

            source_uri = f"WP:{source_wp}:{source_sheet}:{source_cell_label}"
            self._ensure_node(source_uri, "WP", source_wp)

            targets = ref.get("targets", [])
            for target in targets:
                target_wp = target.get("wp_code", "")
                target_sheet = target.get("sheet", "")
                target_cell_label = target.get("cell_label", target.get("cell", ""))

                target_uri = f"WP:{target_wp}:{target_sheet}:{target_cell_label}"
                self._ensure_node(target_uri, "WP", target_wp)
                self._add_edge(source_uri, target_uri, "data_flow", severity)

    # ─── Data Source 3: report_config DB ─────────────────────────

    async def _from_report_config(self) -> None:
        """查 DB report_config.formula → TB→REPORT / ROW→REPORT 边。"""
        if not self._db:
            return

        try:
            result = await self._db.execute(
                text(
                    "SELECT row_code, row_name, formula, report_type::text, applicable_standard "
                    "FROM report_config WHERE formula IS NOT NULL AND formula != '' "
                    "AND is_deleted = false"
                )
            )
            rows = result.fetchall()
        except Exception as e:
            logger.warning("Failed to query report_config: %s", e)
            try:
                await self._db.rollback()
            except Exception:
                pass
            return

        for row in rows:
            row_code = row[0]
            formula = row[2]
            report_type = row[3] if len(row) > 3 else ""
            std = row[4] if len(row) > 4 else ""

            target_uri = f"REPORT:{row_code}:{std or ''}:{report_type or ''}"
            self._ensure_node(target_uri, "REPORT", row_code)

            # Parse TB()/SUM_TB()/ROW() from formula
            source_uris = self._parse_report_formula(formula)
            for src_uri in source_uris:
                self._ensure_node(src_uri, *self._parse_uri_parts(src_uri))
                self._add_edge(src_uri, target_uri, "data_flow", "warning")

    def _parse_report_formula(self, formula: str) -> list[str]:
        """解析 report_config.formula 中的 TB()/SUM_TB()/ROW()。"""
        uris: list[str] = []
        if not formula:
            return uris

        # TB('1002','期末余额')
        for m in re.finditer(r"TB\('([^']+)','([^']+)'\)", formula):
            code, label = m.groups()
            uris.append(f"TB:{code}::{label}")

        # SUM_TB('1401~1499','期末余额')
        for m in re.finditer(r"SUM_TB\('([^']+)','([^']+)'\)", formula):
            code_range, label = m.groups()
            uris.append(f"TB:{code_range}::{label}")

        # ROW('BS-009')
        for m in re.finditer(r"ROW\('([^']+)'\)", formula):
            row_code = m.group(1)
            uris.append(f"REPORT:{row_code}::")

        return uris

    # ─── Data Source 4: L3 dependencies ──────────────────────────

    def _from_l3_dependencies(self) -> None:
        """读 address_registry_l3_dependencies.json → 同文件跨 sheet 边。"""
        path = DATA_DIR / "address_registry_l3_dependencies.json"
        if not path.exists():
            logger.warning("address_registry_l3_dependencies.json not found, skipping")
            return

        data = json.loads(path.read_text(encoding="utf-8"))
        dependencies = data.get("dependencies", [])

        for dep in dependencies:
            source_wp = dep.get("source_wp", "")
            source_sheet = dep.get("source_sheet", "")
            source_cell = dep.get("source_cell", "")
            target_sheet = dep.get("target_sheet", "")
            target_cell = dep.get("target_cell", "")

            source_uri = f"WP:{source_wp}:{source_sheet}:{source_cell}"
            target_uri = f"WP:{source_wp}:{target_sheet}:{target_cell}"

            self._ensure_node(source_uri, "WP", source_wp)
            self._ensure_node(target_uri, "WP", source_wp)
            self._add_edge(target_uri, source_uri, "intra_wp", "info")

    # ─── Data Source 5: note_account_mapping DB ──────────────────

    async def _from_note_account_mapping(self) -> None:
        """查 DB note_account_mappings → WP→NOTE 边。

        语义重载：note_section_code 字段存的是业务名称（如"应收账款"），
        不是机械编号"五、N"/"八、N"。运行时按 disclosure_notes.section_title
        反查实际章节编号生成 NOTE URI。

        合并版（consolidated）多家加总，不直接对应底稿，seed 不生成此类条目。
        单体版（standalone）单家维度，精确对应底稿，本方法处理。
        """
        if not self._db:
            return

        # 加载 section_title → [note_section] 索引（项目无关，全 PG 累计）
        title_to_sections: dict[str, set[str]] = {}
        try:
            r2 = await self._db.execute(
                text(
                    "SELECT DISTINCT note_section, section_title FROM disclosure_notes "
                    "WHERE section_title IS NOT NULL AND section_title != '' "
                    "AND is_deleted = false"
                )
            )
            for ns, title in r2.fetchall():
                key = (title or "").strip()
                if key:
                    title_to_sections.setdefault(key, set()).add(ns)
        except Exception as e:
            logger.warning("Failed to load section_title index: %s", e)
            try:
                await self._db.rollback()
            except Exception:
                pass
            return

        # 取 note_account_mappings 单体版条目（合并版无底稿映射）
        try:
            result = await self._db.execute(
                text(
                    "SELECT wp_code, note_section_code, report_row_code, fetch_mode, table_index "
                    "FROM note_account_mappings "
                    "WHERE wp_code IS NOT NULL AND wp_code != '' "
                    "AND template_type IN ('soe_standalone', 'listed_standalone')"
                )
            )
            rows = result.fetchall()
        except Exception as e:
            logger.warning("Failed to query note_account_mappings: %s", e)
            try:
                await self._db.rollback()
            except Exception:
                pass
            return

        edge_count = 0
        for row in rows:
            wp_code = row[0] or ""
            section_title = row[1] or ""  # 业务名称（语义重载）
            report_row = row[2] or ""
            fetch_mode = row[3] or "total"
            table_idx = row[4] or 0

            source_uri = f"WP:{wp_code}::{fetch_mode}"
            self._ensure_node(source_uri, "WP", wp_code)

            # 按 section_title 反查 disclosure_notes 实际章节编号
            actual_sections = title_to_sections.get(section_title.strip(), set())
            if not actual_sections:
                # 项目尚未生成附注，仍创建一个稳定的 NOTE URI 作占位
                target_uri = f"NOTE:{section_title}:{table_idx}:{fetch_mode}"
                self._ensure_node(target_uri, "NOTE", section_title)
                self._add_edge(source_uri, target_uri, "data_flow", "warning")
                edge_count += 1
            else:
                for actual_ns in actual_sections:
                    target_uri = f"NOTE:{actual_ns}:{table_idx}:{fetch_mode}"
                    self._ensure_node(target_uri, "NOTE", actual_ns)
                    self._add_edge(source_uri, target_uri, "data_flow", "warning")
                    edge_count += 1

            # 报表行 → 附注（仅当有 report_row 时）
            if report_row:
                report_uri = f"REPORT:{report_row}::"
                self._ensure_node(report_uri, "REPORT", report_row)
                # 用第一个匹配的实际章节编号作目标（或占位）
                if actual_sections:
                    for actual_ns in actual_sections:
                        target_uri = f"NOTE:{actual_ns}:{table_idx}:{fetch_mode}"
                        self._add_edge(report_uri, target_uri, "data_flow", "info")
                else:
                    target_uri = f"NOTE:{section_title}:{table_idx}:{fetch_mode}"
                    self._add_edge(report_uri, target_uri, "data_flow", "info")

        logger.info(
            "_from_note_account_mapping: %d wp→note edges (title resolved against %d real sections)",
            edge_count, len(title_to_sections),
        )

    # ─── Data Source 6: account_mapping DB ───────────────────────

    async def _from_account_mapping(self) -> None:
        """查 DB account_mapping → MAPPING→TB/WP/REPORT 边。"""
        if not self._db:
            return

        try:
            result = await self._db.execute(
                text(
                    "SELECT original_account_code, standard_account_code, mapping_type "
                    "FROM account_mapping WHERE is_deleted = false"
                )
            )
            rows = result.fetchall()
        except Exception as e:
            logger.warning("Failed to query account_mapping: %s", e)
            try:
                await self._db.rollback()
            except Exception:
                pass
            return

        for row in rows:
            original_code = row[0] or ""
            standard_code = row[1] or ""

            source_uri = f"MAPPING:{original_code}::{standard_code}"
            target_uri = f"TB:{standard_code}::"

            self._ensure_node(source_uri, "MAPPING", original_code)
            self._ensure_node(target_uri, "TB", standard_code)
            self._add_edge(source_uri, target_uri, "mapping", "info")

    # ─── Deduplication ───────────────────────────────────────────

    def _deduplicate(self) -> None:
        """去重边（相同 source+target+type 只保留一条）。"""
        seen: set[tuple[str, str, str]] = set()
        unique_edges: list[dict[str, Any]] = []

        for edge in self._edges:
            key = (edge["source"], edge["target"], edge["type"])
            if key not in seen:
                seen.add(key)
                unique_edges.append(edge)

        self._edges = unique_edges

    # ─── Data Source 7: docx placeholders (Sprint 4) ───────────────

    def _from_docx_placeholders(self) -> None:
        """读 docx_placeholder_registry.json → docx 占位符节点和边。"""
        path = DATA_DIR / "docx_placeholder_registry.json"
        if not path.exists():
            logger.warning("docx_placeholder_registry.json not found, skipping")
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to parse docx_placeholder_registry.json: %s", e)
            return

        placeholders = data.get("placeholders", [])
        for ph in placeholders:
            uri = ph.get("uri", "")
            file_name = ph.get("file", "")
            placeholder = ph.get("placeholder", "")

            if not uri:
                continue

            # 创建占位符节点
            self._ensure_node(uri, "WP", placeholder)

            # 从文件名提取 wp_code，建立 docx 文件 → 占位符的边
            wp_code_match = re.match(r"([A-Z]\d+(?:-\d+)?)", file_name.split("/")[-1])
            if wp_code_match:
                wp_code = wp_code_match.group(1)
                wp_uri = f"WP:{wp_code}::"
                self._ensure_node(wp_uri, "WP", wp_code)
                self._add_edge(wp_uri, uri, "docx_placeholder", "info")

        logger.info(
            "docx_placeholder_registry: added %d placeholder nodes",
            len(placeholders),
        )

    # ─── Data Source 8: Formula Reverse Index (Sprint 3) ─────────────

    async def _build_formula_reverse_index(self) -> None:
        """使用 FormulaReverseIndex 构建反向边（被引用方 → 引用方）。

        反向边 type="reverse_ref"，severity="info"。
        这些边让 BFS 可以从被引用方出发找到所有引用方。
        """
        from app.services.formula_reverse_index import FormulaReverseIndex

        reverse_index = FormulaReverseIndex(db=self._db)
        index = await reverse_index.build()

        for source_uri, referencing_uris in index.items():
            self._ensure_node(source_uri, *self._parse_uri_parts(source_uri))
            for ref_uri in referencing_uris:
                self._ensure_node(ref_uri, *self._parse_uri_parts(ref_uri))
                self._add_edge(source_uri, ref_uri, "reverse_ref", "info")

        logger.info(
            "FormulaReverseIndex: added %d reverse edges from %d source URIs",
            sum(len(v) for v in index.values()),
            len(index),
        )

    # ─── Helpers ─────────────────────────────────────────────────

    def _ensure_node(self, uri: str, module: str, code: str) -> None:
        """确保节点存在于图中。"""
        if uri not in self._nodes:
            self._nodes[uri] = {"uri": uri, "module": module, "code": code}

    def _add_edge(
        self, source: str, target: str, edge_type: str, severity: str
    ) -> None:
        """添加一条边。"""
        self._edges.append(
            {
                "source": source,
                "target": target,
                "type": edge_type,
                "severity": severity,
            }
        )

    def _parse_uri_parts(self, uri: str) -> tuple[str, str]:
        """从 URI 解析 module 和 code。"""
        parts = uri.split(":", 2)
        module = parts[0] if len(parts) > 0 else ""
        code = parts[1] if len(parts) > 1 else ""
        return module, code
