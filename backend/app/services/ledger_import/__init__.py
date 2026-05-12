"""账表导入统一引擎 (v2) — 公共 API。

模块结构（对齐 .kiro/specs/ledger-import-unification/design.md）：

- orchestrator   : ImportOrchestrator 编排器（detect / submit / resume）
- detector       : 探测层（文件类型 / 前 20 行 / 合并表头 / 大文件流式）
- identifier     : 识别层（3 级并行策略 + 加权聚合 + 合并表头语义映射）
- converter      : 数据转换层（原始行 → 标准化四表记录）
- adapters/      : 财务软件适配器（7 家 + JSON 热加载）
- parsers/       : 流式解析（Excel/CSV/ZIP，50k/chunk）
- writer         : COPY 流式写入 PG + raw_extra JSONB
- validator      : 3 级分层校验（key blocking / recommended warning / extra skip）
- aux_dimension  : 辅助维度解析（7 种格式 + 多维组合）
- merge_strategy : 多 sheet 合并（auto/by_month/manual）
- year_detector  : 年度自动识别（文件名 → sheet 名 → 内容众数）
- encoding_detector : CSV 编码探测（BOM → 候选 → chardet → latin1）
- column_mapping_service : 列映射历史持久化 / 跨项目复用
- detection_types : Pydantic schemas（单一真源）
- errors         : 31 个分级错误码

替代关系：
- 本模块替代旧 smart_import_engine.py（3000+ 行单文件，已标记 deprecated）
- 通过 feature_flag 'ledger_import_v2' 灰度切换
"""

from .converter import convert_balance_rows, convert_ledger_rows
from .detection_types import (
    ColumnMatch,
    FileDetection,
    LedgerDetectionResult,
    SheetDetection,
    TableType,
)
from .detector import detect_file, detect_file_from_path
from .orchestrator import ImportOrchestrator

__all__ = [
    "ImportOrchestrator",
    "detect_file",
    "detect_file_from_path",
    "convert_balance_rows",
    "convert_ledger_rows",
    "FileDetection",
    "SheetDetection",
    "LedgerDetectionResult",
    "ColumnMatch",
    "TableType",
]
