# 账表导入统一方案 — 技术设计

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                     前端：LedgerImportDialog                        │
│   [上传]  →  [预检弹窗]  →  [列映射确认]  →  [进度/错误弹窗]        │
└─────────────────────────────────────────────────────────────────────┘
                               │ ↓ ↑ ↓
          ┌────────────────────┴────────────────────┐
          │          FastAPI  /api/ledger-import/*  │
          └────────────────────┬────────────────────┘
                               │
      ┌────────────────────────┴────────────────────────┐
      │          ImportOrchestrator（编排）            │
      │  ┌──────────────┐  ┌──────────────┐  ┌───────┐ │
      │  │  Detector    │→ │  Identifier  │→ │Parser │ │
      │  │（前 20 行）  │  │（置信度+适配）│  │(流式) │ │
      │  └──────────────┘  └──────────────┘  └───────┘ │
      │           ↓                ↓              ↓    │
      │  ┌────────────────┐  ┌──────────┐ ┌──────────┐│
      │  │ Adapter Registry│  │Validator │ │ Writer   ││
      │  │  (用友/金蝶...)│  │ (3 级)   │ │ (COPY)   ││
      │  └────────────────┘  └──────────┘ └──────────┘│
      └──────────────────────┬──────────────────────────┘
                              ↓
      ┌──────────────────────┴──────────────────────────┐
      │                   PostgreSQL                     │
      │  tb_balance / tb_ledger / tb_aux_balance /       │
      │  tb_aux_ledger / import_jobs / import_artifacts /│
      │  ledger_datasets / import_column_mapping_history │
      └──────────────────────────────────────────────────┘
```

## 2. 模块拆分

新目录 `backend/app/services/ledger_import/`（不污染既有 `smart_import_engine.py`，待稳定后逐步替换）：

```
backend/app/services/ledger_import/
├── __init__.py                    # 公共 API 出口
├── orchestrator.py                # ImportOrchestrator 编排器（唯一入口）
├── detector.py                    # 探测：表头 / 前 20 行 / 合并单元格
├── identifier.py                  # 识别：3 级策略 + 置信度评分
├── adapters/
│   ├── __init__.py                # AdapterRegistry
│   ├── base.py                    # BaseAdapter 抽象
│   ├── yonyou.py                  # 用友 U8/NC/T+
│   ├── kingdee.py                 # 金蝶 K3/EAS/Cloud
│   ├── sap.py                     # SAP
│   ├── oracle.py                  # Oracle EBS
│   ├── inspur.py                  # 浪潮 GS
│   ├── newgrand.py                # 新中大
│   └── generic.py                 # 通用兜底
├── parsers/
│   ├── excel_parser.py            # openpyxl 流式读
│   ├── csv_parser.py              # CSV stream
│   └── zip_parser.py              # ZIP 解压递归
├── aux_dimension.py               # 辅助维度解析（6 种格式）
├── merge_strategy.py              # 多 sheet 合并（auto/by_month/manual）
├── writer.py                      # COPY 流式写入 PG
├── validator.py                   # 3 级校验
├── year_detector.py               # 年度自动识别
├── encoding_detector.py           # 编码探测
├── column_mapping_service.py      # 列映射持久化/复用
├── detection_types.py             # Pydantic schemas
└── errors.py                      # 分级错误定义
```

## 3. 核心数据结构

```python
# detection_types.py

from pydantic import BaseModel, Field
from typing import Literal, Optional

TableType = Literal["balance", "ledger", "aux_balance", "aux_ledger", "account_chart", "unknown"]
ConfidenceLevel = Literal["high", "medium", "low", "manual_required"]
ErrorSeverity = Literal["fatal", "blocking", "warning"]

class ColumnMatch(BaseModel):
    """单列识别结果"""
    column_index: int
    column_header: str
    standard_field: Optional[str]   # 如 "account_code" / "debit_amount" / None（进 raw_extra）
    column_tier: Literal["key", "recommended", "extra"]  # 列分层
    confidence: int = Field(ge=0, le=100)
    source: Literal["header_exact", "header_fuzzy", "content_pattern", "manual", "ai_fallback"]
    sample_values: list[str] = []
    
    @property
    def is_key_column(self) -> bool:
        return self.column_tier == "key"
    
    @property
    def passes_threshold(self) -> bool:
        """按分层判断是否达到自动映射门槛"""
        if self.column_tier == "key":
            return self.confidence >= 80
        elif self.column_tier == "recommended":
            return self.confidence >= 50
        else:  # extra
            return True   # 非关键列无门槛，原样存 raw_extra


class SheetDetection(BaseModel):
    """单 sheet 识别结果"""
    file_name: str
    sheet_name: str
    row_count_estimate: int
    header_row_index: int           # 表头在第几行（从 0 开始）
    data_start_row: int
    
    table_type: TableType
    table_type_confidence: int = Field(ge=0, le=100)
    confidence_level: ConfidenceLevel
    
    adapter_id: Optional[str]       # 命中的适配器（yonyou / kingdee / ...）
    column_mappings: list[ColumnMatch]
    
    has_aux_dimension: bool = False
    aux_dimension_columns: list[int] = []
    
    preview_rows: list[list[str]]   # 前 20 行原始数据
    
    detection_evidence: dict         # 决策树 { "level1_sheetname": true, "level2_headers": [...] }
    
    warnings: list[str] = []


class FileDetection(BaseModel):
    """单文件识别结果"""
    file_name: str
    file_size_bytes: int
    file_type: Literal["xlsx", "xls", "csv", "zip"]
    encoding: Optional[str]         # 仅 csv
    sheets: list[SheetDetection]
    errors: list["ImportError"] = []


class LedgerDetectionResult(BaseModel):
    """总探测结果（用于前端预检弹窗）"""
    upload_token: str
    files: list[FileDetection]
    
    detected_year: Optional[int]
    year_confidence: int = 0
    year_evidence: dict = {}
    
    merged_tables: dict[TableType, list[tuple[str, str]]]  # 合并后哪些 (file, sheet) 合为同一张表
    
    missing_tables: list[TableType] = []  # 4 张表中缺哪几张
    can_derive: dict[TableType, bool] = {} # 缺失的能否从其他表派生
    
    errors: list["ImportError"] = []
    requires_manual_confirm: bool  # 前端是否需要弹窗确认


class ImportError(BaseModel):
    code: str              # 如 "MISSING_KEY_COLUMN" / "AMOUNT_NOT_NUMERIC_KEY"
    severity: ErrorSeverity
    message: str
    file: Optional[str] = None
    sheet: Optional[str] = None
    row: Optional[int] = None
    column: Optional[str] = None
    suggestion: Optional[str] = None
```

## 4. 识别策略详解

### 4.1 Level 1 — Sheet 名识别

关键词映射表（`ledger_import/identifier.py:SHEET_NAME_PATTERNS`）：

```python
SHEET_NAME_PATTERNS = {
    "balance": [
        r"(?i)(科目余额|余额表|试算平衡|总账|general\s*ledger)",
        r"^TB\s*[0-9]{4}",             # 有的软件 sheet 名就叫 "TB2025"
    ],
    "ledger": [
        r"(?i)(凭证|序时|日记账|明细账|detail\s*ledger|journal)",
        r"^(1|2|...|12)月(凭证)?$",    # 按月拆分的 sheet
    ],
    "aux_balance": [
        r"(?i)(辅助余额|核算项目|辅助核算)",
    ],
    "aux_ledger": [
        r"(?i)(辅助明细|核算项目.*明细|多维.*明细)",
    ],
    "account_chart": [
        r"(?i)(科目|账户|科目表|chart\s*of\s*accounts)",
    ],
}
```

命中任一 pattern → 置信度 90（表名精确）或 75（表名模糊）。

### 4.2 Level 2 — 表头特征识别（关键列驱动）

每张表定义**关键列组合**（key_signals）、**排除列**（negative_signals）、**推荐列**（recommended）；识别判断只看关键列是否命中，不混合推荐列（`ledger_import/identifier.py:TABLE_SIGNATURES`）：

```python
TABLE_SIGNATURES = {
    "balance": {
        # 所有组要满足（AND），组内元素可二选一（OR tuple）
        "key_signals": [
            ["account_code"],                                          # 必须
            [("opening_balance",), ("opening_debit", "opening_credit")],  # 期初二选一组
            [("closing_balance",), ("closing_debit", "closing_credit")],  # 期末二选一组
            # debit_amount/credit_amount 本期发生额不是必须（某些导出只有期初期末）
        ],
        "negative_signals": ["voucher_date", "voucher_no"],  # 命中则一定不是余额表
        "recommended": ["account_name", "debit_amount", "credit_amount", "level", "company_code"],
    },
    "ledger": {
        "key_signals": [
            ["voucher_date"],
            ["voucher_no"],
            ["account_code"],
            [("debit_amount", "credit_amount"), ("amount", "direction")],  # 金额方向二选一模式
        ],
        "negative_signals": ["opening_balance", "closing_balance"],
        "recommended": ["summary", "preparer", "currency_code", "voucher_type", "entry_seq"],
    },
    "aux_balance": {
        # 继承 balance 的 key_signals + 辅助维度
        "key_signals_inherit": "balance",
        "key_signals_extra": [
            [("aux_type",), ("aux_dimensions_raw",)],  # 类型或原始维度字段二选一
            [("aux_code",), ("aux_name",)],             # 编码或名称二选一（至少一个可识别）
        ],
        "recommended": ["aux_name", "debit_amount", "credit_amount"],
    },
    "aux_ledger": {
        "key_signals_inherit": "ledger",
        "key_signals_extra": [
            [("aux_type",), ("aux_dimensions_raw",)],
            [("aux_code",), ("aux_name",)],
        ],
        "recommended": ["summary", "aux_code", "aux_name"],
    },
    "account_chart": {
        "key_signals": [["account_code"], [("account_name",)]],
        "negative_signals": ["voucher_date", "opening_balance"],
        "recommended": ["level", "category", "direction"],
    },
}
```

算法（与旧版本不同）：
1. 对每张表类型，检查所有 `key_signals` 是否全部命中（组内 OR，组间 AND）
2. 命中所有关键列组 → 置信度 = 80（基础）+ `recommended` 命中率 × 15（最多 +15）= 80-95
3. 命中部分关键列 → 置信度 = 50 + 组命中比例 × 25 = 50-75（不自动用，要人工确认）
4. `negative_signals` 命中任一 → 得分 × 0.1（几乎排除该类型）
5. 得分最高且 > 80 的类型胜出为自动判定；50-79 的让用户确认；< 50 的下探到 Level 3

### 4.3 Level 3 — 内容样本识别

前 10 行数据特征：
- 有日期列且日期格式规则 → 倾向 ledger
- 有"借/贷"或"1/-1"方向列 → 倾向 ledger
- 金额列数量 ≥ 4（期初借贷+期末借贷）→ 倾向 balance
- 单元格内含 `:` 且前半段是"客户/供应商/项目" → 有辅助维度

置信度 30-59，仅作为 Level 1+2 失败时的兜底。

### 4.4 Level 4 — 人工确认

所有 `confidence < 60` 的 sheet 进入"需人工确认"队列，前端弹窗让用户指定。

## 5. 适配器机制

### 5.1 BaseAdapter 抽象

```python
class BaseAdapter:
    id: str                  # "yonyou" / "kingdee" / ...
    display_name: str        # "用友 U8/NC"
    priority: int            # 优先级，数字越大越先匹配
    
    def match(self, file_detection: FileDetection) -> float:
        """返回 0-1 的匹配度"""
        raise NotImplementedError
    
    def get_column_aliases(self, table_type: TableType) -> dict[str, list[str]]:
        """返回 { "account_code": ["科目编码", "科目代码", "ACCOUNT CODE"] }"""
        raise NotImplementedError
    
    def preprocess_rows(self, table_type: TableType, rows: list[dict]) -> list[dict]:
        """软件特定的行级处理（如用友的日期是 Excel 序列号，需要转换）"""
        return rows
```

### 5.2 示例：用友适配器

```python
# adapters/yonyou.py
class YonyouAdapter(BaseAdapter):
    id = "yonyou"
    display_name = "用友 U8/NC/T+"
    priority = 80
    
    def match(self, fd: FileDetection) -> float:
        score = 0
        # 文件名含"用友"/"NC"/"U8"
        if re.search(r"(用友|UFIDA|U8|NC\d|T\+)", fd.file_name, re.I):
            score += 0.5
        # 关键列名命中用友特色
        yonyou_cols = {"科目编码", "科目名称", "方向", "年初余额", "借方本期", "贷方本期", "期末余额"}
        for sheet in fd.sheets:
            headers = {m.column_header for m in sheet.column_mappings}
            if len(headers & yonyou_cols) >= 3:
                score += 0.3
        return min(score, 1.0)
    
    def get_column_aliases(self, table_type: TableType) -> dict[str, list[str]]:
        if table_type == "balance":
            return {
                "account_code": ["科目编码", "科目代码"],
                "account_name": ["科目名称", "科目全名"],
                "opening_balance": ["年初余额", "期初余额"],
                "opening_debit": ["年初借方", "期初借方"],
                "opening_credit": ["年初贷方", "期初贷方"],
                "debit_amount": ["借方本期", "本期借方", "本期借方发生额"],
                "credit_amount": ["贷方本期", "本期贷方", "本期贷方发生额"],
                "closing_balance": ["期末余额"],
                "closing_debit": ["期末借方"],
                "closing_credit": ["期末贷方"],
                "level": ["级次"],
                "currency_code": ["币种", "币别"],
            }
        elif table_type == "ledger":
            return {
                "voucher_date": ["日期", "凭证日期", "制单日期"],
                "voucher_no": ["凭证号", "凭证字号"],
                "voucher_type": ["凭证类型", "字"],
                "summary": ["摘要"],
                "account_code": ["科目编码", "科目"],
                "account_name": ["科目名称"],
                "debit_amount": ["借方金额", "借方"],
                "credit_amount": ["贷方金额", "贷方"],
                "preparer": ["制单人", "制单"],
                "currency_code": ["币种"],
            }
        return {}
```

### 5.3 AdapterRegistry

```python
# adapters/__init__.py
class AdapterRegistry:
    def __init__(self):
        self._adapters: list[BaseAdapter] = []
    
    def register(self, adapter: BaseAdapter):
        self._adapters.append(adapter)
        self._adapters.sort(key=lambda a: a.priority, reverse=True)
    
    def detect_best(self, fd: FileDetection) -> tuple[BaseAdapter, float]:
        """返回最匹配的适配器（至少 GenericAdapter 兜底）"""
        scores = [(a, a.match(fd)) for a in self._adapters]
        best = max(scores, key=lambda t: t[1])
        return best

# 全局实例（模块加载时自动注册）
registry = AdapterRegistry()
registry.register(YonyouAdapter())
registry.register(KingdeeAdapter())
# ...
registry.register(GenericAdapter())  # priority=0 兜底
```

## 6. 辅助维度解析

```python
# aux_dimension.py
import re
from typing import Optional

# 顺序匹配，首个命中即返回
PATTERNS = [
    # JSON: {"客户":"001","项目":"P01"}
    (r"^\{.*\}$", "json"),
    # 类型:编码 名称 | 类型：编码 名称
    (r"^(?P<type>[^:：/|]+)[:：](?P<code>\S+)\s+(?P<name>.+)$", "colon_code_name"),
    # 类型/编码/名称
    (r"^(?P<type>[^/]+)/(?P<code>[^/]+)/(?P<name>.+)$", "slash_separated"),
    # 类型|编码|名称
    (r"^(?P<type>[^|]+)\|(?P<code>[^|]+)\|(?P<name>.+)$", "pipe_separated"),
    # 类型: 名称（无编码）
    (r"^(?P<type>[^:：]+)[:：]\s*(?P<name>.+)$", "colon_name_only"),
    # 编码 名称（无类型）
    (r"^(?P<code>[A-Z0-9]+)\s+(?P<name>.+)$", "code_name"),
    # 箭头: 项目 -> 研发部
    (r"^(?P<type>[^→\->]+?)\s*[->→]+\s*(?P<name>.+)$", "arrow"),
]

def parse_aux_dimension(raw: str) -> list[dict]:
    """解析辅助维度字符串，返回维度列表 [{aux_type, aux_code, aux_name}]"""
    if not raw or not raw.strip():
        return []
    raw = raw.strip()
    
    # 多维度用 , 或 ; 分隔
    parts = re.split(r"[,;；]\s*", raw)
    result = []
    for part in parts:
        for pattern, fmt in PATTERNS:
            m = re.match(pattern, part)
            if m:
                gd = m.groupdict()
                if fmt == "json":
                    import json
                    try:
                        obj = json.loads(part)
                        for k, v in obj.items():
                            result.append({"aux_type": k, "aux_code": None, "aux_name": str(v)})
                    except:
                        pass
                    break
                result.append({
                    "aux_type": gd.get("type", "").strip() or None,
                    "aux_code": gd.get("code", "").strip() or None,
                    "aux_name": gd.get("name", "").strip() or None,
                })
                break
        else:
            # 无法解析，原样存
            result.append({"aux_type": None, "aux_code": None, "aux_name": part})
    return result
```

## 7. API 契约

### 7.1 预检接口

```
POST /api/projects/{project_id}/ledger-import/detect
  multipart/form-data:
    files[]: <binary>
    year_override: int | null
    adapter_hint: str | null  # 用户指定适配器

Response 200:
  LedgerDetectionResult
  
Response 400:
  { "code": "FILE_TOO_LARGE", "severity": "fatal", ... }
```

### 7.2 确认并提交

```
POST /api/projects/{project_id}/ledger-import/submit
  {
    "upload_token": "...",
    "year": 2025,
    "confirmed_mappings": [
      {
        "file": "book.xlsx",
        "sheet": "总账",
        "table_type": "balance",        # 用户确认或修改
        "column_mapping": { "0": "account_code", ... },
        "aux_dimension_columns": [5]
      }
    ],
    "force_activate": false
  }

Response 200:
  { "job_id": "...", "status": "queued" }
```

### 7.3 进度查询（SSE）

```
GET /api/projects/{project_id}/ledger-import/jobs/{job_id}/stream

Content-Type: text/event-stream

data: {"phase":"parsing","file":"book.xlsx","sheet":"总账","rows":50000,"percent":15}
data: {"phase":"validating","percent":88}
data: {"phase":"activating","percent":99}
data: {"phase":"completed","dataset_id":"..."}
```

## 8. 前端组件

### 8.1 目录

```
audit-platform/frontend/src/components/ledger-import/
├── LedgerImportDialog.vue         # 总入口（原 AccountImportStep 升级）
├── UploadStep.vue                 # 步骤 1：选择文件
├── DetectionPreview.vue           # 步骤 2：预检结果展示
├── ColumnMappingEditor.vue        # 步骤 3：列映射调整
├── ImportProgress.vue             # 步骤 4：进度 + SSE
├── ErrorDialog.vue                # 分级错误弹窗
└── DiagnosticPanel.vue            # 诊断详情（支持/管理员）
```

### 8.2 关键 UI 决策

- **预检表格**：每个 sheet 一行，列：[选中 ✓] [文件] [sheet] [识别类型 下拉可改] [置信度 badge] [必填列状态] [预览 →]
- **置信度 badge**：绿(≥80) / 黄(60-79) / 红(<60)
- **错误弹窗**：3 栏布局（问题描述 / 定位 / 修复建议），支持折叠多个错误
- **进度条**：四段式（上传→解析→校验→激活），每段独立进度

## 9. 数据库变更

### 9.1 新增表（需求 9）

```sql
-- 列映射历史表
CREATE TABLE import_column_mapping_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    software_fingerprint VARCHAR(100) NOT NULL,  -- 如 "yonyou_U8_v13_balance"
    table_type VARCHAR(30) NOT NULL,
    column_mapping JSONB NOT NULL,                -- { "科目编码": "account_code", ... }
    used_count INT NOT NULL DEFAULT 1,
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_icmh_project_fingerprint
  ON import_column_mapping_history(project_id, software_fingerprint);
```

### 9.2 ImportJob 现有字段复用（避免重复加列）

实测 `import_jobs` 表（`backend/app/models/dataset_models.py:147`）已具备：

| 字段 | 类型 | 本方案用途 |
|------|------|----------|
| `options` | JSONB | 存 `{adapter_hint, force_activate, year_override, confirmed_mappings_ref}` |
| `result_summary` | JSONB | 存 `{counts, dataset_id, diagnostics_ref}` |
| `progress_message` / `current_phase` | Text/Varchar | SSE 直接读 |
| `error_message` | Text | 存第一个 fatal/blocking 错误简述 |

### 9.3 ImportJob 真正需要新增的字段（需求 19）

```sql
ALTER TABLE import_jobs
  ADD COLUMN IF NOT EXISTS detection_result JSONB,   -- 完整 LedgerDetectionResult 快照（仅 v2 引擎）
  ADD COLUMN IF NOT EXISTS adapter_used VARCHAR(50); -- 命中的适配器 id
```

注：`error_list JSONB` 不新增——直接用 `result_summary.errors` 子键承载，避免字段膨胀。

### 9.4 四表增加 raw_extra 列（需求 21）

```sql
-- 四张账表统一加 raw_extra JSONB，原样保留用户文件里未被映射的非关键列
ALTER TABLE tb_balance     ADD COLUMN IF NOT EXISTS raw_extra JSONB;
ALTER TABLE tb_ledger      ADD COLUMN IF NOT EXISTS raw_extra JSONB;
ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS raw_extra JSONB;
ALTER TABLE tb_aux_ledger  ADD COLUMN IF NOT EXISTS raw_extra JSONB;

-- 可选：GIN 索引（仅在频繁查询 raw_extra 字段时加，默认不加）
-- CREATE INDEX CONCURRENTLY idx_tb_ledger_raw_extra_gin ON tb_ledger USING GIN (raw_extra);
```

**写入规则**（`writer.py`）：
- 一行数据里，已映射到 `standard_field`（key 或 recommended）的列**不**重复写 raw_extra
- 剩余列按 `{原始列名: 原始值}` 存入 raw_extra
- 单行 raw_extra 大小 ≤ 8KB（PG JSONB 不强制但内部 TOAST 阈值，超过性能下降）；超限只保留前 N 列 + 生成 `EXTRA_TRUNCATED` warning
- 空 dict 时存 `NULL`（不存 `{}`，节省空间）

**聚合查询端点**（需求 21.5）：

```
GET /api/projects/{project_id}/ledger/raw-extra-fields?year=2025&table=tb_ledger

Response:
{
  "tb_ledger": {
    "审核人": { "row_count": 125000, "sample_values": ["张三", "李四", "王五"] },
    "结算方式": { "row_count": 98000, "sample_values": ["现金", "转账", "支票"] },
    "部门": { "row_count": 12000, "sample_values": ["销售部", "财务部"] }
  }
}
```

便于用户或支持人员发现"哦原来还有部门列可以识别"，写迁移脚本把 raw_extra 里某字段提升为标准列。

## 10. 错误码表（按列分层严重级）

### 10.1 致命（fatal）— 无法启动

| 错误码 | 说明 | 典型触发 |
|--------|------|----------|
| `FILE_TOO_LARGE` | 文件超过上限 | 单文件 > 1GB |
| `UNSUPPORTED_FILE_TYPE` | 不支持的文件类型 | 上传 .doc |
| `CORRUPTED_FILE` | 文件损坏无法打开 | openpyxl 抛异常 |
| `XLS_NOT_SUPPORTED` | .xls 暂不支持 | 上传老版 Excel |
| `ENCODING_DETECTION_FAILED` | CSV 编码无法检测 | 非标准编码 |

### 10.2 阻塞（blocking）— 关键列相关

| 错误码 | 说明 | 典型触发 |
|--------|------|----------|
| `NO_VALID_SHEET` | 没识别出任何业务 sheet | 全是空 sheet |
| `MISSING_KEY_COLUMN` | 缺关键列（置信度 < 80） | 无 account_code / 无期末金额 |
| `AMOUNT_NOT_NUMERIC_KEY` | 关键金额列非数字 | debit_amount 有字母 |
| `DATE_INVALID_KEY` | voucher_date 无法解析 | 日期格式乱 |
| `EMPTY_VALUE_KEY` | 关键列值为空 | account_code 整列 NULL |
| `BALANCE_UNBALANCED` | 借贷不平（L2） | sum(debit) ≠ sum(credit) |
| `ACCOUNT_NOT_IN_CHART` | 科目不在科目表（L2） | 序时账用未定义科目 |
| `BALANCE_LEDGER_MISMATCH` | 余额与序时累计不一致（L3） | 超过容差 1 元 |

### 10.3 警告（warning）— 次关键列或非阻断业务问题

| 错误码 | 说明 | 行为 |
|--------|------|------|
| `MISSING_RECOMMENDED_COLUMN` | 缺次关键列 | 值置 NULL，不阻断 |
| `AMOUNT_NOT_NUMERIC_RECOMMENDED` | 次关键金额列非数字 | 该值置 NULL |
| `DATE_INVALID_RECOMMENDED` | 次关键日期列无法解析 | 该值置 NULL |
| `YEAR_MISMATCH` | 年度与项目期不符 | 提示用户确认 |
| `AUX_DIMENSION_PARSE_FAILED` | 辅助维度无法解析 | 存 aux_dimensions_raw |
| `HEADER_ROW_AMBIGUOUS` | 表头位置不确定 | 让用户手工指定 |
| `SHEET_MERGE_HEURISTIC` | 自动合并了多 sheet | 提示 1-12 月合并结果 |
| `AUX_ACCOUNT_MISMATCH` | 辅助表科目⊄主表（L3） | 提示用户核对 |
| `EXTRA_TRUNCATED` | raw_extra 超 8KB 被截断 | 保留前 N 列 |
| `CURRENCY_MIX` | 同科目多币种 | 提示用户 |

### 10.4 信息（info）— 仅记录不弹窗

| 错误码 | 说明 |
|--------|------|
| `RAW_EXTRA_COLUMNS_PRESERVED` | 保留了 N 个未识别列到 raw_extra |
| `AI_FALLBACK_USED` | 某列走了 AI 兜底识别 |
| `HISTORY_MAPPING_APPLIED` | 应用了历史列映射 |

## 11. 性能优化要点

1. **前 20 行探测**：openpyxl `read_only=True` + `iter_rows(max_row=20)`
2. **Chunk 大小**：50,000 行（经验值，兼顾内存和 COPY 效率）
3. **COPY 写入**：`writer.py` 用 psycopg2 `copy_expert` 走 STDIN，比 `INSERT VALUES` 快 10×
4. **并发**：多文件串行（避免 OOM），单文件内 sheet 串行，sheet 内按 chunk 流式
5. **PG 索引**：`tb_ledger` 的 `(project_id, year, voucher_date)` 复合索引 + `(account_code)` 分区索引
6. **SSE**：后端用 `asyncio.Queue` 推进度，前端 `EventSource` 订阅

## 12. 测试策略

### 12.1 单元测试

```
backend/tests/ledger_import/
├── test_detector.py               # 探测逻辑 + 合并单元格
├── test_identifier.py             # 3 级识别 + 置信度
├── test_adapters/
│   ├── test_yonyou.py
│   ├── test_kingdee.py
│   └── ...
├── test_aux_dimension.py          # 6 种格式解析
├── test_merge_strategy.py         # 多 sheet 合并
├── test_validator.py              # 3 级校验
├── test_year_detector.py
└── fixtures/
    ├── yonyou_u8_sample.xlsx
    ├── kingdee_k3_sample.xlsx
    ├── sap_sample.csv
    ├── mixed_12months.xlsx        # 按月拆 sheet
    ├── merged_headers.xlsx         # 合并表头
    ├── large_ledger_1m_rows.csv   # 大文件
    └── ...
```

### 12.2 集成测试

端到端走 `/detect` → `/submit` → `/jobs/{id}/stream` 全链路，断言：

- 8 家软件样本**关键列**识别率 ≥ 85%（次关键列不计入指标）
- 大文件（100 万行）入库耗时 < 10 分钟
- 并发 5 个导入作业不冲突
- 中途取消能清理 staged 数据
- `raw_extra` 正确保留所有未识别列

### 12.3 属性测试（Hypothesis）

- 对任意辅助维度字符串，`parse_aux_dimension` 不抛异常
- 对任意 (file_name, sheet_name, headers) 组合，`identifier.detect()` 返回有效 TableType

## 13. 灰度与回退

### 13.1 开关机制（对齐现有 `feature_flags.py`）

现实：`backend/app/services/feature_flags.py` 是进程内内存字典（`_DEFAULT_FLAGS`），**不读 env 变量**；项目级 override 在 `_project_overrides` 内存字典，重启失效。

因此本方案的开关落地为：

```python
# backend/app/services/feature_flags.py
_DEFAULT_FLAGS: dict[str, bool] = {
    ...,
    "ledger_import_v2": False,   # 新增：新账表导入引擎
}
```

检查点（两处）：
1. `router_registry.py` 注册 v2 router 时包一层 `if is_enabled("ledger_import_v2"): include_router(...)`
2. `import_job_runner.py` 收到 Job 时判断 `is_enabled("ledger_import_v2", project_id=job.project_id)` 决定走 v2 或旧 `smart_import_engine`

### 13.2 灰度阶段

| 阶段 | 开关状态 | 覆盖范围 | 持续时间 |
|------|---------|---------|---------|
| Phase 0（内测） | 默认 False，指定 test project override 为 True | 1-2 个内部测试项目 | 1 周 |
| Phase 1（Beta） | 默认 False，允许业务方在项目设置里启用 | 自愿加入的项目 | 2 周 |
| Phase 2（默认开启） | 默认 True | 新项目走 v2，老项目手动迁移 | 2 周 |
| Phase 3（GA） | 默认 True，无法关闭 | 全量 | — |
| Phase 4（清理） | 删除旧 `smart_import_engine.py` | — | Phase 3 稳定 1 个月后 |

### 13.3 回退预案

1. 新引擎报错率 > 5% 或 P95 耗时翻倍：`feature_flags.set_project_flag(pid, "ledger_import_v2", False)` 单项目回退
2. 大面积问题：直接把 `_DEFAULT_FLAGS["ledger_import_v2"]` 改回 False 并热重启（内存字典随进程死亡）
3. 关键：**新引擎的 staged dataset 与旧引擎的完全隔离**（LedgerDataset 表已有 source_type 区分），回退不需数据回滚

### 13.4 不使用的机制（避免混乱）

- **不**用 URL 参数 `?engine=v2`（前端要维护两套调用路径，易出错）
- **不**用独立 `engine` 字段（ImportJob.options JSONB 里记 `engine_version`，诊断用，不作为路由决策依据）
- **不**改 env 变量（feature_flags.py 本身不读 env，引入 env 会造成两套真源）

## 14. 监控指标

- `ledger_import_detect_duration_ms`（直方图）
- `ledger_import_submit_duration_ms`（直方图）
- `ledger_import_rows_per_second`（直方图）
- `ledger_import_success_rate`（计数器，按 adapter_id 分桶）
- `ledger_import_manual_confirm_rate`（需要人工确认的比例）
- `ledger_import_error_count`（按错误码分桶）

写入 Prometheus，通过 Metabase 大盘展示。


---

## 15. 多 sheet 合并算法（需求 6）

`merge_strategy.py` 实现三种策略：

### 15.1 `auto` 策略（默认）

```python
def auto_merge(sheets: list[SheetDetection]) -> list[MergedGroup]:
    """按表头签名聚类，同类型 + 同表头 → 合并为一组"""
    groups: dict[tuple, list[SheetDetection]] = {}
    for s in sheets:
        # 签名 = (table_type, 标准化后的必填列集合)
        required_fields = frozenset(
            m.standard_field for m in s.column_mappings
            if m.standard_field and m.confidence >= 60
        )
        sig = (s.table_type, required_fields)
        groups.setdefault(sig, []).append(s)
    
    return [MergedGroup(sheets=v, strategy="auto") for v in groups.values() if len(v) >= 1]
```

### 15.2 `by_month` 策略（序时账专用）

触发条件：同一 table_type 的多 sheet，sheet 名匹配 `^\d{1,2}月` 或 `^(01|02|...|12)$`

合并后逻辑主键：`(voucher_date, voucher_no, entry_seq)`，写入时去重（`ON CONFLICT DO NOTHING`）

### 15.3 `manual` 策略

用户在前端 DetectionPreview 勾选"把这几个 sheet 作为同一张表"，前端传 `merge_groups: [[(f1, s1), (f1, s2)]]` 到 submit 接口。

### 15.4 合并后记录

`ImportBatch.file_name` 字段改为 `"merged:f1#s1,f1#s2,f1#s3"`（最长 255 字符，超限只留首 3 个+省略号）；完整 sources 存到 `result_summary.merge_sources`。

---

## 16. 年度识别优先级（需求 13）

`year_detector.py` 按优先级尝试，首个命中即返回（带置信度）：

| 优先级 | 来源 | 置信度 | 正则/算法 |
|-------|------|--------|----------|
| P1 | 文件名 | 95 | `r"20[0-9]{2}(?:年度?|年)"` |
| P2 | Sheet 名 | 90 | 同上 |
| P3 | 表头前 10 行文本 | 85 | `r"会计期间[:：]?\s*20(\d{2})[-/年]\s*(\d{1,2})"` 取年份 |
| P4 | 序时账日期列众数 | 75 | 抽样前 1000 行，按 year(voucher_date) 统计众数 |
| P5 | 余额表期末日期列 | 70 | 同 P4 |
| P6 | 默认当前年-1 | 30 | 审计通常做上年账套 |
| P7 | 人工选择 | 100 | 弹窗让用户选 |

**冲突处理**：P1-P5 命中多个且年份不一致时，按置信度最高者胜出；若 P1 vs P4 年份冲突，UI 弹警告"文件名 2024 但数据日期众数 2025"。

---

## 17. 编码探测（需求 14）

`encoding_detector.py` 只针对 CSV，xlsx 是二进制不存在此问题。

```python
def detect_encoding(content: bytes) -> tuple[str, float]:
    """返回 (encoding_name, confidence_0_to_1)"""
    # 1. BOM 检测（100% 置信度）
    if content.startswith(b"\xef\xbb\xbf"):
        return ("utf-8-sig", 1.0)
    if content.startswith(b"\xff\xfe") or content.startswith(b"\xfe\xff"):
        return ("utf-16", 1.0)
    
    # 2. 按候选列表逐个试解码前 4KB
    probe = content[:4096]
    for enc in ("utf-8", "gb18030", "gbk", "big5", "latin1"):
        try:
            probe.decode(enc)
            return (enc, 0.85)
        except UnicodeDecodeError:
            continue
    
    # 3. 兜底：chardet 第三方库
    try:
        import chardet
        result = chardet.detect(content[:65536])
        if result["confidence"] > 0.7:
            return (result["encoding"], result["confidence"])
    except ImportError:
        pass
    
    return ("latin1", 0.3)  # 兜底（不会失败但可能乱码）
```

注意：
- `gb18030` 放在 `gbk` 前，因为 gb18030 是 gbk 的超集
- 置信度 < 0.5 时，前端 UI 弹窗请用户确认编码

---

## 18. 表头识别算法（需求 15）

`detector.py::detect_header_row()` 步骤：

```python
def detect_header_row(rows: list[list[Any]]) -> tuple[int, list[str]]:
    """
    返回 (header_row_index, merged_header_cells)
    
    算法：
    1. 跳过前 5 行中纯标题行（单行跨表宽、含"公司"/"年度"/"报表"）
    2. 识别合并表头（相邻 2-3 行都是字符串、上行有合并单元格 > 2 列）
    3. 若检测到合并，按列 index 拼接："期初.借方" / "期初.贷方"
    4. 第一个非空数据行之前的最后一行（或合并后）即为 header_row
    """
    skip = 0
    for i, row in enumerate(rows[:5]):
        non_empty = [str(c) for c in row if c]
        # 标题行特征：单列占满表宽 或 行内关键词
        if (len(non_empty) <= 2 and any(
            kw in "".join(non_empty) for kw in ("公司", "年度", "报表", "科目余额表")
        )):
            skip = i + 1
        else:
            break
    
    # 检测合并表头
    candidate_rows = rows[skip:skip + 3]
    if len(candidate_rows) < 2:
        return (skip, [str(c) for c in rows[skip]])
    
    row0, row1 = candidate_rows[0], candidate_rows[1]
    # 上行所有非空格占比 < 50%（提示有合并）且下行非空格 >= 3
    top_fill_ratio = sum(1 for c in row0 if c) / max(len(row0), 1)
    if top_fill_ratio < 0.5 and sum(1 for c in row1 if c) >= 3:
        # 合并表头：向左填充上行（合并单元格的语义）
        merged_top = []
        last = ""
        for c in row0:
            if c:
                last = str(c).strip()
            merged_top.append(last)
        # 拼接：上行.下行
        headers = [
            f"{t}.{b}" if t and b and t != b else (b or t or "")
            for t, b in zip(merged_top, [str(c or "") for c in row1])
        ]
        return (skip + 1, headers)  # 数据从第 skip+2 行开始
    
    return (skip, [str(c or "") for c in rows[skip]])
```

无法识别时（置信度低），前端 UI 提供"手动指定表头所在行"的数字输入框。

---

## 19. 三级校验层（需求 11）

`validator.py` 结构：

```python
class ValidationFinding(BaseModel):
    level: Literal["L1", "L2", "L3"]
    severity: ErrorSeverity   # fatal/blocking/warning
    code: str
    message: str
    location: dict             # { file, sheet, row, column }
    blocking: bool             # True 时阻塞激活（除非 force_activate）

class Validator:
    async def validate_l1(self, rows: list[dict], table_type: TableType) -> list[ValidationFinding]:
        """解析期校验：金额数值 / 日期可解析 / 必填非空"""
    
    async def validate_l2(self, db, dataset_id: UUID) -> list[ValidationFinding]:
        """全量后校验：借贷平衡 / 年度范围 / 科目存在"""
    
    async def validate_l3(self, db, dataset_id: UUID) -> list[ValidationFinding]:
        """跨表校验：余额期末=序时累计（容差 1 元）/ 辅助与主表科目一致"""
    
    def evaluate_activation(
        self, findings: list[ValidationFinding], force: bool
    ) -> ActivationGate:
        """返回 allowed + blocking_findings；force=True 时 L2/L3 的 blocking 可跳过"""
```

### 19.1 L1 规则（必经，按列分层）

| 规则 | 触发 | 关键列严重级 | 次关键列严重级 | 非关键列 |
|-----|------|-------------|---------------|---------|
| `L1_AMOUNT_NOT_NUMERIC` | 金额列出现非数字 | blocking（`AMOUNT_NOT_NUMERIC_KEY`） | warning（值置 NULL） | 不校验（原样入 raw_extra） |
| `L1_DATE_INVALID` | 日期解析失败 | blocking 仅 voucher_date（`DATE_INVALID_KEY`） | warning（值置 NULL） | 不校验 |
| `L1_EMPTY_VALUE` | 必填列为空 | blocking 仅关键列（`EMPTY_VALUE_KEY`） | 不校验 | 不校验 |
| `L1_DUPLICATE_PK` | 同 (voucher_date, voucher_no, entry_seq) 重复 | warning（保留首条） | — | — |

### 19.2 L2 规则（整库后）

| 规则 | 查询 | severity | 可 force 跳过 |
|-----|------|---------|--------------|
| `L2_BALANCE_NOT_BALANCED` | `SUM(opening_debit) = SUM(opening_credit)` | blocking | ✓ |
| `L2_LEDGER_YEAR_OUT_OF_RANGE` | voucher_date 不在 year 内 | blocking | ✗（数据质量硬底线） |
| `L2_ACCOUNT_NOT_IN_CHART` | ledger.account_code 不在 account_chart | blocking | ✓ |
| `L2_CURRENCY_MIX` | 同科目出现多币种未标记 | warning | ✓ |

### 19.3 L3 规则（跨表）

| 规则 | 查询 | 容差 | severity |
|-----|------|------|---------|
| `L3_BALANCE_LEDGER_MISMATCH` | balance.closing = opening + sum(ledger.debit) - sum(ledger.credit) | 1 元 | blocking（可 force） |
| `L3_AUX_ACCOUNT_MISMATCH` | aux_balance.account_code ⊂ balance.account_code | — | warning |
| `L3_AUX_SUM_MISMATCH` | sum(aux_balance.closing) = balance.closing（按科目） | 1 元 | warning |

### 19.4 `force_activate` 审批链

- 普通用户：只能跳过 warning，不能跳过 blocking
- partner / admin：可勾选 `force_activate=true` 跳过 L2/L3 blocking
- force 动作写入 `audit_log`：`{actor, findings_skipped, reason}`，UI 要求输入原因

---

## 20. 回滚 API（需求 12）

### 20.1 API 契约

```
POST /api/projects/{project_id}/ledger-import/datasets/{dataset_id}/rollback
  {
    "reason": "2025 Q1 账套导入时列映射错误，回滚到上一版本"
  }

Response 200:
  {
    "rolled_back_to": "dataset_xxx",  # 回滚到的版本 id
    "superseded_dataset_id": "...",    # 本次被废弃的版本
    "affected_tables": ["tb_balance", "tb_ledger", ...],
    "event_published": "ledger.dataset_rolled_back"
  }
```

### 20.2 DatasetService 扩展

```python
class DatasetService:
    @staticmethod
    async def rollback_to_previous(
        db: AsyncSession, project_id: UUID, year: int,
        reason: str, actor_id: UUID,
    ) -> RollbackResult:
        """
        1. 找到当前 active dataset
        2. 找到上一个 active（按 activated_at DESC LIMIT 1 OFFSET 1）
        3. 事务内：当前 → superseded；上一个 → active
        4. 发布 LEDGER_DATASET_ROLLED_BACK 事件（复用既有枚举）
        5. 写 audit_log：{actor, from, to, reason}
        """
```

### 20.3 下游响应

事件名复用现有 `EventType.LEDGER_DATASET_ROLLED_BACK`（`audit_platform_schemas.py:747`）；订阅方（试算表/报表/附注）已有 `MAPPING_CHANGED` 的处理器，可复用模式。

### 20.4 回滚限制

- 只能在 90 天内回滚（`activated_at + 90 days > now()`）
- 有后续 workpaper 数据依赖当前版本时禁止回滚（返回 409 + 冲突列表）
- 回滚后原版本不物理删除，状态切为 `rolled_back`

---

## 21. 映射复用与 diff（需求 9 扩展）

### 21.1 软件指纹（software_fingerprint）

```python
def compute_fingerprint(file_detection: FileDetection, table_type: TableType) -> str:
    """
    指纹 = adapter_id + table_type + 排序后表头的 md5 前 8 位
    
    例如：yonyou_U8 + balance + md5(科目编码,科目名称,期初借方,期初贷方,...)[:8]
        → "yonyou_balance_a3b2c1d4"
    """
```

### 21.2 复用策略

```python
async def resolve_mapping(
    db, project_id: UUID, fingerprint: str, auto_detected: dict
) -> ResolvedMapping:
    """
    1. 查历史映射（project_id, fingerprint）
    2. 存在：
       a. 完全覆盖当前自动检测的列 → 用历史（置信度 95）
       b. 历史覆盖 ≥ 80% 列 → 用历史+补齐（置信度 85）
       c. 历史覆盖 < 80% → 不用历史，提示用户 diff
    3. 不存在：用自动检测
    """
```

### 21.3 Diff 呈现

UI 显示：
- 绿色：本次新增的列映射（历史没有）
- 蓝色：与历史一致（默认保留）
- 黄色：与历史不同（让用户确认用哪个）
- 灰色：历史有但本次没检测到（可能是导出配置变化）

---

## 22. AI 兜底识别（可选，需求 2 扩展）

### 22.1 触发条件

所有 Level 1-3 结果置信度 < 30，且 `feature_flags.is_enabled("ledger_import_ai_fallback")` 为 true。

### 22.2 调用方式

复用 `unified_ai_service.py`：

```python
async def ai_identify_sheet(preview_rows: list[list[str]], sheet_name: str) -> AIIdentification:
    prompt = f"""你是财务审计数据识别专家。以下是 Excel 某 sheet 的前 20 行：
Sheet 名称：{sheet_name}
表头与数据（前 20 行）：
{format_table(preview_rows)}

判断这张表属于哪类：
- balance（科目余额表）
- ledger（序时账 / 凭证明细）
- aux_balance（辅助核算余额表）
- aux_ledger（辅助核算明细账）
- account_chart（科目表）
- unknown

同时给出列映射（列号 → 标准字段名：account_code / voucher_date / ...）。

返回 JSON：
{{"table_type": "...", "confidence": 0-100, "column_mapping": {{"0": "account_code", ...}}, "reasoning": "..."}}
"""
    response = await unified_ai_service.generate(prompt, model="qwen3:8b", max_tokens=800)
    return AIIdentification.model_validate_json(response)
```

### 22.3 安全与成本

- AI 结果置信度封顶为 60（永远低于规则 Level 2），避免 hallucination 主导决策
- 数据脱敏：金额用 `***` 替代，客户名用 `[client]` 替代（复用 `export_mask_service.mask_context`）
- 单次调用耗时 < 5s，超时直接放弃
- 单项目每天 AI 兜底次数上限 20 次（防刷）
- 识别结果必须人工确认（触发前端 manual_required 分支）

### 22.4 数据记录

AI 识别结果存到 `detection_evidence.ai_fallback`：
```json
{
  "model": "qwen3:8b",
  "latency_ms": 2300,
  "response": {...},
  "rule_confidence": 25,
  "ai_confidence": 55,
  "final_decision": "ai"
}
```

---

## 23. 前端性能要点（需求 17 扩展）

| 场景 | 目标 | 实现 |
|------|------|------|
| 多文件并发预检 | 10 文件 30s 内 | `Promise.all(files.map(detectFile))` + 后端 upload endpoint 支持 concurrent |
| 预览表格虚拟滚动 | 1000 行不卡 | `el-table-v2`（element-plus），行高固定 32px |
| 前 20 行限 | 最多 200 列宽 | `max-width: 200px; text-overflow: ellipsis` |
| sessionStorage 恢复 | 刷新 5 秒内恢复 | key=`ledger_import_preview_${project_id}`，ttl 30 分钟 |
| 断点续传状态 | 关闭浏览器可续 | 已上传 chunks 存 localStorage，上传前对比后端 `/upload/status` |

---

## 24. 取消语义细化（需求 18 扩展）

### 24.1 取消流程

```
用户点"取消"按钮
    ↓
前端调 POST /api/projects/{pid}/ledger-import/jobs/{job_id}/cancel
    ↓
后端 ImportJob.status = canceling（不是 canceled）
    ↓
import_job_runner 下次循环检查 status → 发现 canceling
    ↓
中断当前解析（抛 ImportCanceledException，在 parser chunk 边界检查）
    ↓
触发 cleanup：DatasetService.mark_failed(dataset_id, cleanup_rows=True)
    ↓
ImportJob.status = canceled（终态），progress_message="已取消"
    ↓
SSE 推送 {"phase":"canceled"} 后关闭流
```

### 24.2 取消响应时延

- 解析阶段取消：< 5s（chunk 边界检查）
- 写入阶段取消：< 10s（等当前 COPY 命令返回）
- 校验阶段取消：< 3s（L2/L3 查询可 cancel_scope）
- 激活阶段：**不允许取消**（原子操作已开始，会完整 commit 或 rollback）

### 24.3 取消后数据状态

- staged 行：已清理（`is_deleted=true` 且 dataset 状态 `failed`）
- ImportJob：状态 `canceled`，保留诊断供用户查看
- ImportArtifact：保留 7 天，用户可基于原文件点"重新导入"

---

## 25. 模块间依赖图

```
orchestrator.py ─┬─→ detector.py ──→ encoding_detector.py
                 ├─→ identifier.py ─┬─→ adapters/ (8 家)
                 │                  └─→ detection_types.py
                 ├─→ year_detector.py
                 ├─→ parsers/ ──────┬─→ excel_parser.py
                 │                  ├─→ csv_parser.py
                 │                  └─→ zip_parser.py
                 ├─→ aux_dimension.py
                 ├─→ merge_strategy.py
                 ├─→ column_mapping_service.py
                 ├─→ writer.py ────→ fast_writer.copy_insert
                 ├─→ validator.py ──→ (3 级规则)
                 └─→ errors.py

依赖外部模块：
- app.services.dataset_service.DatasetService （staged/active 机制）
- app.services.event_bus （LEDGER_DATASET_* 事件）
- app.services.feature_flags （灰度开关）
- app.services.unified_ai_service （AI 兜底，可选）
- app.services.export_mask_service （AI 脱敏）
```

---

## 26. 已知约束与未解决问题

1. **.xls 文件**：当前 smart_import_engine 已拒绝，本方案继续拒绝；未来考虑用 `xlrd==1.2.0`（受限许可）或 LibreOffice headless 转换
2. **合并 sheet 时的 entry_seq 冲突**：1 月 sheet 和 2 月 sheet 都用 entry_seq=1 时会撞；建议合并时重写 entry_seq 为全局序号
3. **adapter 打分 tie-breaker**：两家软件打分相同时（如都 0.6），目前按 priority 数字胜出；若需要更精细可引入"最近使用"权重
4. **AI 兜底的成本监控**：Phase 2 前需加 AI 调用次数指标，防刷
5. **samples 脱敏流程**：Sprint 0 必须先和业务方对齐脱敏规则（客户名 → `[client_N]`，金额按数量级而非具体数）


---

## 27. 四表联动契约（关键列单一真源）

本章通过列出所有"四表联动查询"的真实 SQL，反推出必须保证的关键列清单——这是识别规则和校验规则的**合同锚点**。任何修改识别规则的 PR 必须先检查是否破坏本章任何一条 SQL 的执行。

### 27.1 穿透查询（从余额表到序时账）

```sql
-- 从科目余额表的期末金额，定位到支持它的序时账凭证
SELECT
    l.voucher_date, l.voucher_no, l.debit_amount, l.credit_amount, l.summary
FROM tb_balance b
JOIN tb_ledger l
  ON l.project_id = b.project_id
 AND l.year = b.year
 AND l.account_code = b.account_code    -- 【关键列】两表都必须有 account_code
WHERE b.project_id = $1
  AND b.year = $2
  AND b.account_code = $3
ORDER BY l.voucher_date, l.voucher_no;

-- 依赖关键列：
--   tb_balance:   account_code
--   tb_ledger:    voucher_date, voucher_no, account_code, debit_amount, credit_amount
```

### 27.2 对账查询（余额与序时累计一致性）

```sql
-- 容差 1 元：余额表期末 = 期初 + 累计借 - 累计贷（资产类）
SELECT
    b.account_code,
    b.opening_balance,
    COALESCE(SUM(l.debit_amount - l.credit_amount), 0) AS period_net,
    b.opening_balance + COALESCE(SUM(l.debit_amount - l.credit_amount), 0) AS computed_closing,
    b.closing_balance AS declared_closing,
    ABS(
        b.closing_balance
        - b.opening_balance
        - COALESCE(SUM(l.debit_amount - l.credit_amount), 0)
    ) AS diff
FROM tb_balance b
LEFT JOIN tb_ledger l
  ON l.project_id = b.project_id
 AND l.year = b.year
 AND l.account_code = b.account_code
WHERE b.project_id = $1 AND b.year = $2
GROUP BY b.account_code, b.opening_balance, b.closing_balance
HAVING ABS(...) > 1;

-- 依赖关键列：
--   tb_balance:   account_code, opening_balance, closing_balance
--   tb_ledger:    account_code, debit_amount, credit_amount
```

### 27.3 辅助维度汇总（按客户/项目/部门维度）

```sql
-- 例：按客户维度汇总应收账款（科目 1122 开头）
SELECT
    a.aux_type,
    a.aux_code,
    a.aux_name,
    SUM(a.closing_balance) AS total
FROM tb_aux_balance a
WHERE a.project_id = $1
  AND a.year = $2
  AND a.account_code LIKE '1122%'   -- 【关键列】account_code
  AND a.aux_type = '客户'             -- 【关键列】aux_type
GROUP BY a.aux_type, a.aux_code, a.aux_name
ORDER BY total DESC
LIMIT 100;

-- 依赖关键列：
--   tb_aux_balance: account_code, aux_type, aux_code（或 aux_name）, closing_balance
```

### 27.4 辅助维度穿透（从辅助余额到辅助明细）

```sql
-- 查某客户某科目的所有凭证明细
SELECT
    al.voucher_date, al.voucher_no, al.debit_amount, al.credit_amount, al.summary,
    al.aux_type, al.aux_code, al.aux_name
FROM tb_aux_ledger al
WHERE al.project_id = $1
  AND al.year = $2
  AND al.account_code = $3
  AND al.aux_type = $4
  AND al.aux_code = $5                 -- 【关键列】aux_code
ORDER BY al.voucher_date, al.voucher_no;

-- 依赖关键列：
--   tb_aux_ledger: voucher_date, voucher_no, account_code, aux_type, aux_code, debit_amount, credit_amount
```

### 27.5 余额表与辅助表一致性校验（L3）

```sql
-- 辅助余额按科目汇总应等于主余额表（容差 1 元）
SELECT
    b.account_code,
    b.closing_balance AS main_total,
    COALESCE(SUM(a.closing_balance), 0) AS aux_total,
    ABS(b.closing_balance - COALESCE(SUM(a.closing_balance), 0)) AS diff
FROM tb_balance b
LEFT JOIN tb_aux_balance a
  ON a.project_id = b.project_id
 AND a.year = b.year
 AND a.account_code = b.account_code   -- 【关键列】account_code 对齐
WHERE b.project_id = $1 AND b.year = $2
GROUP BY b.account_code, b.closing_balance
HAVING ABS(...) > 1;
```

### 27.6 关键列清单汇总（识别引擎的合同）

| 表 | 关键列 | 说明 |
|---|-------|------|
| tb_balance | `account_code` | 所有联动的 Join Key |
| tb_balance | `opening_balance` 或 (`opening_debit` + `opening_credit`) | 期初（二选一组） |
| tb_balance | `closing_balance` 或 (`closing_debit` + `closing_credit`) | 期末（二选一组） |
| tb_ledger | `voucher_date` | 期间切分 |
| tb_ledger | `voucher_no` | 凭证聚合 |
| tb_ledger | `account_code` | Join Key |
| tb_ledger | `debit_amount` + `credit_amount` | 发生额（不可二选一，两个都要） |
| tb_aux_balance | 上面余额表关键列 + `aux_type` + (`aux_code` 或 `aux_name`) | 维度识别需要 type + code/name 至少一个 |
| tb_aux_ledger | 上面序时账关键列 + `aux_type` + (`aux_code` 或 `aux_name`) | 同上 |

**次关键列**（识别失败不阻断，值置 NULL）：
`account_name` / `summary` / `preparer` / `currency_code` / `voucher_type` / `level` / `entry_seq` / `company_code` / `accounting_period` / `opening_debit` / `opening_credit`（当 opening_balance 已识别时）

**非关键列**（一律入 `raw_extra`）：
用户文件里除上述两类之外的所有列（审核人、结算方式、部门、外币金额等）

### 27.7 识别引擎与校验引擎的一致性

`identifier.py::TABLE_SIGNATURES.key_signals` 必须与本章 27.6 表格**完全对齐**。变更此表需同步修改：

1. `identifier.py::TABLE_SIGNATURES`
2. `validator.py::Validator.validate_l1()` 中的 key_fields 常量
3. `ColumnMatch.column_tier` 的判定逻辑
4. 前端 `ColumnMappingEditor.vue` 三区分组规则
5. 本章 27.6 表格

为避免漂移，建议在 `detection_types.py` 定义**单一真源**：

```python
# ledger_import/detection_types.py
KEY_COLUMNS: dict[TableType, list[str | tuple[str, ...]]] = {
    "balance": [
        "account_code",
        ("opening_balance", ("opening_debit", "opening_credit")),
        ("closing_balance", ("closing_debit", "closing_credit")),
    ],
    "ledger": [
        "voucher_date", "voucher_no", "account_code",
        "debit_amount", "credit_amount",
    ],
    "aux_balance": [
        # 继承 balance 的 key
        ..., "aux_type", ("aux_code", "aux_name"),
    ],
    "aux_ledger": [
        ..., "aux_type", ("aux_code", "aux_name"),
    ],
}

RECOMMENDED_COLUMNS: dict[TableType, list[str]] = {
    "balance": ["account_name", "debit_amount", "credit_amount", "level", "company_code", "currency_code"],
    "ledger": ["summary", "preparer", "currency_code", "voucher_type", "entry_seq", "company_code"],
    # aux_* 同上
}
```

所有其他模块导入这两个常量，不允许各自写死。


---

## 28. 架构演进方向（v2.1 — 通用化重构）

> **背景**：Sprint 1-4 实装后用真实样本（重庆医药集团两家子企业）验证，暴露了三个结构性问题：
> 1. 合并表头检测依赖硬编码的"非空率 < 0.5"启发式，对 2 行标题 + 2 行合并表头的格式失效
> 2. 识别流程 L1→L2→L3 串行且 L3 仅在 L1+L2 都低时触发，浪费了内容特征信息
> 3. 模糊匹配（Levenshtein/子串）对短列名产生误报
>
> **核心原则**：通用规则、声明式配置、表头+内容联合判断、动态适配而非定制化。

### 28.1 识别流程重构：表头+内容联合打分

**现状**（串行降级）：
```
L1(sheet名) → if conf<90: L2(表头) → if conf<60: L3(内容)
```

**目标**（并行联合）：
```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│ L1 Sheet名  │   │ L2 表头特征 │   │ L3 内容特征 │
│  权重 0.2   │   │  权重 0.5   │   │  权重 0.3   │
└──────┬──────┘   └──────┬──────┘   └──────┬──────┘
       └─────────────────┼─────────────────┘
                         ↓
              加权聚合 → 最终置信度
```

- L1/L2/L3 **始终并行执行**，各自独立产出 `(table_type, score_0_to_1)`
- 最终置信度 = `L1_score × 0.2 + L2_score × 0.5 + L3_score × 0.3`（权重可配置）
- L3 不再是"兜底"，而是与 L2 互补的信号源（前 20 行数据量不大，计算开销可忽略）
- 冲突时按加权分最高的 table_type 胜出，evidence 记录各级投票

### 28.2 合并表头检测：通用算法

**目标**：基于"连续行中非空率变化梯度"自动判断表头边界，而非硬编码阈值。

**算法**：
1. 对前 10 行计算每行的 `unique_value_count`（去重后非空单元格数）和 `fill_ratio`（非空/总列数）
2. **标题行判定**：`unique_value_count <= 2`（所有单元格值相同或只有 1-2 个不同值）→ 跳过
3. **表头边界判定**：找到第一行满足 `fill_ratio >= 0.5 AND unique_value_count >= 3` 的行作为"表头起始"
4. **合并表头判定**：如果表头起始行的下一行也满足 `fill_ratio >= 0.5 AND unique_value_count >= 3`，且两行的列名集合不重叠（上行是分组名如"年初余额"，下行是子列名如"借方金额"），则判定为合并表头
5. **数据起始行**：表头结束后的第一行

**关键改进**：不再依赖 `non_empty_ratio < 0.5` 这个脆弱阈值，改用"值多样性"作为判据。

### 28.3 识别规则声明式配置

**目标**：将识别规则从 Python 代码抽离为 JSON/YAML 配置，支持热加载和用户自定义。

**规则文件结构**（`backend/data/ledger_recognition_rules.json`）：
```json
{
  "version": "2.1",
  "table_signatures": {
    "balance": {
      "sheet_name_patterns": ["(?i)(科目余额|余额表|试算平衡|总账)"],
      "key_columns": {
        "account_code": {"aliases": ["科目编码","科目代码","账户编码"], "required": true},
        "opening_balance": {"aliases": ["年初余额","期初余额"], "required": false, "alternatives": ["opening_debit+opening_credit"]},
        "closing_balance": {"aliases": ["期末余额"], "required": true, "alternatives": ["closing_debit+closing_credit"]},
        "debit_amount": {"aliases": ["借方金额","本期借方","借方发生额","借方"], "required": true},
        "credit_amount": {"aliases": ["贷方金额","本期贷方","贷方发生额","贷方"], "required": true}
      },
      "content_signals": {
        "numeric_columns_min": 4,
        "has_date_column": false,
        "has_direction_column": false
      },
      "negative_signals": ["voucher_date", "voucher_no"]
    },
    "ledger": {
      "sheet_name_patterns": ["(?i)(凭证|序时|日记账|明细账)"],
      "key_columns": {
        "voucher_date": {"aliases": ["记账日期","凭证日期","制单日期","业务日期"], "required": true, "content_validator": "date"},
        "voucher_no": {"aliases": ["凭证号","凭证字号","凭证编号"], "required": true},
        "account_code": {"aliases": ["科目编码","科目代码","账户编码"], "required": true},
        "debit_amount": {"aliases": ["借方金额","借方","Debit","DR"], "required": true, "content_validator": "numeric"},
        "credit_amount": {"aliases": ["贷方金额","贷方","Credit","CR"], "required": true, "content_validator": "numeric"}
      },
      "content_signals": {
        "has_date_column": true,
        "has_direction_column": true,
        "numeric_columns_min": 2
      },
      "negative_signals": ["opening_balance", "closing_balance"]
    }
  },
  "matching_config": {
    "exact_match_confidence": 95,
    "fuzzy_match_confidence": 70,
    "min_fuzzy_length": 3,
    "levenshtein_max_distance": 2,
    "min_levenshtein_length": 4,
    "weights": {"sheet_name": 0.2, "header": 0.5, "content": 0.3}
  }
}
```

**好处**：
- 新增财务软件只需加 JSON 文件，不改 Python 代码
- 用户可在项目设置中自定义规则覆盖
- 规则版本化，可回溯

### 28.4 列匹配增强：表头+内容双重验证

**现状**：仅靠列名匹配（exact/fuzzy），不看列内容。

**目标**：对每个候选映射，用前 N 行数据做 `content_validator` 验证：
- `date` 验证器：列中 ≥ 50% 的非空值可解析为日期 → 加分
- `numeric` 验证器：列中 ≥ 80% 的非空值可解析为数字 → 加分
- `code` 验证器：列中值符合"字母+数字"编码模式 → 加分
- 验证失败 → 降低该映射的置信度（而非直接否决）

**实现**：在 `_match_header` 返回候选后，对每个候选列跑 `content_validator`：
```python
def validate_column_content(values: list[str], validator_type: str) -> float:
    """返回 0.0-1.0 的内容匹配度"""
```

最终列置信度 = `header_confidence × 0.7 + content_confidence × 0.3`

### 28.5 实施路径

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| Phase A | 合并表头通用算法（替换当前 `_detect_header_row`） | P0 — 直接影响识别率 |
| Phase B | L2+L3 并行联合打分（重构 `identify()` 函数） | P0 — 提升识别准确率 |
| Phase C | 列内容验证器（`content_validator`） | P1 — 消除误匹配 |
| Phase D | 规则声明式配置（JSON 外置） | P2 — 提升可扩展性 |

Phase A+B 在 Sprint 5 测试阶段落地（用真实样本驱动）；Phase C+D 在 UAT 迭代中逐步推进。


---

## 29. 序时账增量导入（v2.2 — 按期间追加）

> **驱动场景**：陕西华氏按月导出序时账（12 个文件），预审导入 1-11 月，年审只需追加 12 月；
> 和平药房按日期段拆分 CSV（20250101-1011 + 20251012-1031）。
> 余额表每次全量覆盖（因为期末数会变），但序时账是追加式的——已入库的月份不应重复导入。

### 29.1 核心概念

| 概念 | 说明 |
|------|------|
| **期间（period）** | 序时账的凭证日期所属月份（如 2025-01 ~ 2025-12） |
| **已入库期间** | 当前 active dataset 中 tb_ledger 已有数据覆盖的月份集合 |
| **增量期间** | 本次导入文件中的凭证日期覆盖的月份 - 已入库期间 = 需要追加的月份 |
| **全量覆盖** | 余额表始终全量替换（staged → activate 覆盖旧版本） |
| **追加模式** | 序时账只写入增量期间的行，已有期间的行跳过（或提示用户确认是否覆盖） |

### 29.2 导入模式选择

在 submit 阶段，用户可选择：

```
导入模式：
  ○ 全量覆盖（默认）— 余额表+序时账全部替换
  ○ 序时账增量追加 — 余额表全量覆盖，序时账只追加新期间
```

增量追加时的行为：
1. 扫描本次文件中所有 `voucher_date`，提取覆盖的月份集合 `file_periods`
2. 查询当前 active dataset 中 `tb_ledger` 已有的月份集合 `existing_periods`
3. 计算 `new_periods = file_periods - existing_periods`
4. 如果 `new_periods` 为空 → 提示"所有期间已存在，无需导入"
5. 如果有重叠（`file_periods ∩ existing_periods` 非空）→ 弹窗确认：
   - "以下月份已存在：1月、2月...，是否覆盖？"
   - 用户选"跳过已有" → 只导入 new_periods 的行
   - 用户选"覆盖" → 删除已有期间的行后重新写入
6. 只导入 new_periods 的行 → 追加到现有 dataset（不新建 staged，直接 append）

### 29.3 前端交互

DetectionPreview 阶段新增：
- 显示"本次文件覆盖期间：2025-01 ~ 2025-11"
- 显示"已入库期间：2025-01 ~ 2025-10"
- 显示"增量期间：2025-11（1 个月）"
- 如果有重叠，显示黄色警告 + 确认按钮

### 29.4 数据模型影响

- `tb_ledger` 已有 `year` 字段，新增查询维度 `accounting_period`（YYYY-MM 格式）
- 或者直接用 `voucher_date` 的月份做 GROUP BY 统计已有期间
- ImportJob.options 新增 `"import_mode": "full" | "incremental"`
- ImportJob.options 新增 `"target_periods": ["2025-11", "2025-12"]`（增量时记录）

### 29.5 与现有机制的关系

- **全量模式**（默认）：行为不变，staged → activate 原子切换
- **增量模式**：不走 staged → activate，而是直接 append 到 active dataset 的 tb_ledger
  - 这意味着增量模式下不需要"激活"步骤
  - 回滚粒度变为"按期间回滚"（删除指定月份的行）
  - 需要新增 `DELETE FROM tb_ledger WHERE dataset_id = ? AND accounting_period IN (?)`

### 29.6 实施优先级

Phase A（当前 Sprint 5）：先把 9 家样本的识别+全量导入跑通
Phase B（下一轮迭代）：实现增量追加模式（需要前端 UI + 后端 period diff 逻辑）
