"""附注内容分层处理策略 — 5 层

Requirements: 46.1, 46.2, 46.5, 46.6, 46.7

A 层（会计政策）：模板文字 + 占位符替换，不联动底稿
B 层（合并科目注释）：底稿联动核心，90%+ 自动填充
C 层（母公司注释）：同 B 但取单体 TB
D 层（补充信息）：50% 自动 + 50% 手动
E 层（附录索引）：100% 自动生成

处理顺序：E → A → B → C → D
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------

class NoteLayer(str, Enum):
    """附注内容层级"""
    A = "A"  # 会计政策
    B = "B"  # 合并科目注释
    C = "C"  # 母公司注释
    D = "D"  # 补充信息
    E = "E"  # 附录索引


# 处理顺序：E → A → B → C → D
PROCESSING_ORDER = [NoteLayer.E, NoteLayer.A, NoteLayer.B, NoteLayer.C, NoteLayer.D]


@dataclass
class LayerConfig:
    """层级配置"""
    layer: NoteLayer
    description: str
    auto_fill_target: float  # 目标自动填充率 (0.0 ~ 1.0)
    links_workpaper: bool  # 是否联动底稿
    uses_standalone_tb: bool = False  # 是否使用单体 TB（C 层）
    template_text_only: bool = False  # 是否仅模板文字（A 层）
    fully_auto: bool = False  # 是否 100% 自动（E 层）


# 层级配置表
LAYER_CONFIGS: dict[NoteLayer, LayerConfig] = {
    NoteLayer.A: LayerConfig(
        layer=NoteLayer.A,
        description="会计政策：模板文字 + 占位符替换，不联动底稿",
        auto_fill_target=0.1,
        links_workpaper=False,
        template_text_only=True,
    ),
    NoteLayer.B: LayerConfig(
        layer=NoteLayer.B,
        description="合并科目注释：底稿联动核心，90%+ 自动填充",
        auto_fill_target=0.9,
        links_workpaper=True,
    ),
    NoteLayer.C: LayerConfig(
        layer=NoteLayer.C,
        description="母公司注释：同 B 但取单体 TB",
        auto_fill_target=0.9,
        links_workpaper=True,
        uses_standalone_tb=True,
    ),
    NoteLayer.D: LayerConfig(
        layer=NoteLayer.D,
        description="补充信息：50% 自动 + 50% 手动",
        auto_fill_target=0.5,
        links_workpaper=True,
    ),
    NoteLayer.E: LayerConfig(
        layer=NoteLayer.E,
        description="附录索引：100% 自动生成",
        auto_fill_target=1.0,
        links_workpaper=False,
        fully_auto=True,
    ),
}


@dataclass
class LayerProcessResult:
    """层级处理结果"""
    layer: NoteLayer
    sections_processed: int = 0
    cells_filled: int = 0
    cells_total: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def fill_rate(self) -> float:
        if self.cells_total == 0:
            return 0.0
        return round(self.cells_filled / self.cells_total * 100, 1)


@dataclass
class StrategyResult:
    """分层处理总结果"""
    layer_results: list[LayerProcessResult] = field(default_factory=list)
    total_sections: int = 0
    total_cells_filled: int = 0
    total_cells: int = 0

    @property
    def overall_fill_rate(self) -> float:
        if self.total_cells == 0:
            return 0.0
        return round(self.total_cells_filled / self.total_cells * 100, 1)


# ---------------------------------------------------------------------------
# Layer Strategy Service
# ---------------------------------------------------------------------------

class NoteLayerStrategy:
    """附注内容分层处理策略

    按 E → A → B → C → D 顺序处理各层附注内容。
    """

    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # 层级分类
    # ------------------------------------------------------------------

    @staticmethod
    def classify_section(section: dict[str, Any]) -> NoteLayer:
        """根据章节属性判断所属层级

        Args:
            section: {section_code, layer, title, ...}
        """
        # 如果已有 layer 标记，直接使用
        layer_str = section.get("layer", "").upper()
        if layer_str and layer_str in [l.value for l in NoteLayer]:
            return NoteLayer(layer_str)

        # 根据 section_code 或 title 推断
        code = section.get("section_code", "")
        title = section.get("title", "")

        # E 层：附录索引
        if code.startswith("appendix_") or "附录" in title or "索引" in title:
            return NoteLayer.E

        # A 层：会计政策
        if (
            code.startswith("note_accounting_polic")
            or code.startswith("note_significant_")
            or "会计政策" in title
            or "重要会计政策" in title
            or "重要会计估计" in title
        ):
            return NoteLayer.A

        # C 层：母公司注释
        if "母公司" in title or code.startswith("parent_"):
            return NoteLayer.C

        # D 层：补充信息
        if (
            code.startswith("note_supplement")
            or code.startswith("note_subsequent")
            or "补充信息" in title
            or "期后事项" in title
            or "或有事项" in title
            or "承诺事项" in title
        ):
            return NoteLayer.D

        # 默认 B 层：合并科目注释
        return NoteLayer.B

    # ------------------------------------------------------------------
    # 层级处理
    # ------------------------------------------------------------------

    def process_layer_a(self, sections: list[dict[str, Any]], placeholders: dict[str, str]) -> LayerProcessResult:
        """A 层处理：模板文字 + 占位符替换

        Args:
            sections: A 层章节列表
            placeholders: {placeholder_key: replacement_value}
        """
        result = LayerProcessResult(layer=NoteLayer.A)
        result.sections_processed = len(sections)

        for sec in sections:
            text = sec.get("text_content", "") or ""
            # 占位符替换
            for key, value in placeholders.items():
                text = text.replace(f"{{{key}}}", value)
            sec["text_content"] = text
            # A 层不计入数值单元格统计
            result.cells_total += 1
            result.cells_filled += 1  # 文字替换视为已填充

        return result

    def process_layer_b(
        self,
        sections: list[dict[str, Any]],
        fill_data: dict[str, dict[str, Any]] | None = None,
    ) -> LayerProcessResult:
        """B 层处理：底稿联动核心，90%+ 自动填充

        Args:
            sections: B 层章节列表
            fill_data: {section_code: {cells_filled, cells_total}}
        """
        result = LayerProcessResult(layer=NoteLayer.B)
        result.sections_processed = len(sections)
        data = fill_data or {}

        for sec in sections:
            code = sec.get("section_code", "")
            sec_data = data.get(code, {})
            result.cells_filled += sec_data.get("cells_filled", 0)
            result.cells_total += sec_data.get("cells_total", 0)

        return result

    def process_layer_c(
        self,
        sections: list[dict[str, Any]],
        fill_data: dict[str, dict[str, Any]] | None = None,
    ) -> LayerProcessResult:
        """C 层处理：同 B 但取单体 TB

        Args:
            sections: C 层章节列表
            fill_data: {section_code: {cells_filled, cells_total}}
        """
        result = LayerProcessResult(layer=NoteLayer.C)
        result.sections_processed = len(sections)
        data = fill_data or {}

        for sec in sections:
            code = sec.get("section_code", "")
            sec_data = data.get(code, {})
            result.cells_filled += sec_data.get("cells_filled", 0)
            result.cells_total += sec_data.get("cells_total", 0)

        return result

    def process_layer_d(
        self,
        sections: list[dict[str, Any]],
        fill_data: dict[str, dict[str, Any]] | None = None,
    ) -> LayerProcessResult:
        """D 层处理：50% 自动 + 50% 手动

        Args:
            sections: D 层章节列表
            fill_data: {section_code: {cells_filled, cells_total}}
        """
        result = LayerProcessResult(layer=NoteLayer.D)
        result.sections_processed = len(sections)
        data = fill_data or {}

        for sec in sections:
            code = sec.get("section_code", "")
            sec_data = data.get(code, {})
            result.cells_filled += sec_data.get("cells_filled", 0)
            result.cells_total += sec_data.get("cells_total", 0)

        return result

    def process_layer_e(self, sections: list[dict[str, Any]], project_info: dict[str, Any] | None = None) -> LayerProcessResult:
        """E 层处理：100% 自动生成（附录索引）

        Args:
            sections: E 层章节列表
            project_info: 项目信息用于生成索引
        """
        result = LayerProcessResult(layer=NoteLayer.E)
        result.sections_processed = len(sections)

        for sec in sections:
            # 附录索引 100% 自动生成
            result.cells_total += 1
            result.cells_filled += 1

        return result

    # ------------------------------------------------------------------
    # 按顺序处理所有层
    # ------------------------------------------------------------------

    def process_all_layers(
        self,
        sections: list[dict[str, Any]],
        placeholders: dict[str, str] | None = None,
        fill_data: dict[str, dict[str, Any]] | None = None,
        project_info: dict[str, Any] | None = None,
    ) -> StrategyResult:
        """按 E → A → B → C → D 顺序处理所有层

        Args:
            sections: 所有附注章节
            placeholders: 占位符替换数据
            fill_data: 填充数据
            project_info: 项目信息
        """
        # 分层
        layer_sections: dict[NoteLayer, list[dict[str, Any]]] = {
            layer: [] for layer in NoteLayer
        }
        for sec in sections:
            layer = self.classify_section(sec)
            sec["layer"] = layer.value
            layer_sections[layer].append(sec)

        strategy_result = StrategyResult()
        strategy_result.total_sections = len(sections)

        # 按顺序处理：E → A → B → C → D
        for layer in PROCESSING_ORDER:
            layer_secs = layer_sections[layer]
            if not layer_secs:
                continue

            if layer == NoteLayer.E:
                lr = self.process_layer_e(layer_secs, project_info)
            elif layer == NoteLayer.A:
                lr = self.process_layer_a(layer_secs, placeholders or {})
            elif layer == NoteLayer.B:
                lr = self.process_layer_b(layer_secs, fill_data)
            elif layer == NoteLayer.C:
                lr = self.process_layer_c(layer_secs, fill_data)
            elif layer == NoteLayer.D:
                lr = self.process_layer_d(layer_secs, fill_data)
            else:
                continue

            strategy_result.layer_results.append(lr)
            strategy_result.total_cells_filled += lr.cells_filled
            strategy_result.total_cells += lr.cells_total

        return strategy_result

    # ------------------------------------------------------------------
    # 获取层级配置
    # ------------------------------------------------------------------

    @staticmethod
    def get_layer_config(layer: NoteLayer) -> LayerConfig:
        """获取层级配置"""
        return LAYER_CONFIGS[layer]

    @staticmethod
    def get_processing_order() -> list[NoteLayer]:
        """获取处理顺序"""
        return list(PROCESSING_ORDER)
