# Design Document: 审定表导出模板动态生成器

## Overview

本设计实现一个统一的审定表（`^[A-N]\d+-1$`）导出模板动态生成器，替代现有 `export-template` 端点直接返回磁盘源 xlsx 的行为。生成器接收 wp_id，按 wp_code 参数化生成含多行合并表头、编制说明 sheet、行骨架的空白 xlsx 模板。

核心设计原则：
- **单一生成器复用**：所有 D~N 审定表走同一个 `AdjudicationExportTemplateService`，差异通过 wp_code/wp_name/aging_config 参数化注入
- **最小侵入**：仅在现有 `export_template` 函数中添加 wp_code 判断分支，不改变接口签名
- **复用已有基础设施**：`workbook_to_response`(RFC5987 中文文件名)、`resolve_aging_segments`/`build_aging_headers`(账龄列)、`extract_audit_rows`(行骨架)

## Architecture

### 模块结构

```
backend/app/services/
  adjudication_export_template_service.py    # 核心生成器（纯函数 + async 账龄解析）

backend/app/routers/
  wp_render_config.py                        # 修改 export_template() 添加路由分支
```

### 调用流程

```
GET /workpapers/{wp_id}/export-template
  → wp_render_config.export_template()
    → 查 wp_index 获取 wp_code、wp_name
    → if wp_code matches ^[A-N]\d+-1$:
        → AdjudicationExportTemplateService.generate(wp_id, wp_code, wp_name, db)
          → 1. 构建编制说明 sheet (instruction_sheet)
          → 2. 构建数据模板 sheet (data_sheet)
            → 2a. 标题行 (row 1)
            → 2b. 多行合并表头 (rows 2-3)
            → 2c. 账龄列 (if applicable, via resolve_aging_segments + build_aging_headers)
            → 2d. 行骨架 (via extract_audit_rows from template xlsx)
        → workbook_to_response(wb, filename)
    → else:
        → 原逻辑 (FileResponse 返回磁盘源文件)
```

### 数据流

```
输入:
  - wp_id → working_paper → wp_index → wp_code, wp_name
  - wp_code → 判定是否审定表、是否含账龄列
  - project_id + subject → AgingConfig segments (for aging wp_codes)
  - template_file_path + sheet_name → extract_audit_rows → row_skeleton

输出:
  - io.BytesIO (xlsx workbook)
  - Content-Disposition: filename*=UTF-8''{wp_code}_{wp_name}审定表_模板.xlsx
```

## Components and Interfaces

### 1. AdjudicationExportTemplateService

**文件**: `backend/app/services/adjudication_export_template_service.py`

**职责**: 动态生成审定表空白 xlsx 模板

**公开接口**:

```python
class AdjudicationExportTemplateService:
    # 含账龄列的 wp_code 前缀（去掉 -1 后缀后的科目标识）
    AGING_SUBJECTS: dict[str, str] = {
        "D2": "D2", "D3": "D3", "F1": "F1",
        "K1": "K1", "K3": "K3", "G5": "G5",
    }

    @staticmethod
    def is_adjudication_table(wp_code: str) -> bool:
        """判断 wp_code 是否为审定表（匹配 ^[A-N]\d+-1$）"""

    @staticmethod
    async def generate(
        wp_id: str,
        wp_code: str,
        wp_name: str,
        db: AsyncSession,
        template_file_path: str | None = None,
    ) -> tuple[io.BytesIO, str]:
        """生成审定表 xlsx 模板。
        
        Returns: (xlsx_bytes_io, filename)
        """
```

**内部方法**:

```python
    @staticmethod
    def _build_instruction_sheet(ws, wp_code: str, wp_name: str, has_aging: bool):
        """填充编制说明 sheet 内容"""

    @staticmethod
    def _build_data_sheet(
        ws, wp_code: str, wp_name: str,
        row_skeleton: list[dict],
        aging_headers: list[str] | None = None,
    ):
        """填充数据模板 sheet（标题+表头+行骨架）"""

    @staticmethod
    def _build_multi_row_header(ws, start_col: int, aging_headers: list[str] | None):
        """构建 2-3 行多行合并表头"""

    @staticmethod
    def _get_aging_subject(wp_code: str) -> str | None:
        """从 wp_code 提取账龄科目标识（如 D2-1 → D2）"""

    @staticmethod
    def _get_row_skeleton(template_file_path: str | None, wp_code: str) -> list[dict]:
        """从模板 xlsx 提取审定表行骨架（降级返回 []）"""
```

### 2. export_template 路由修改

**文件**: `backend/app/routers/wp_render_config.py` (修改现有函数)

**改动**: 在 `export_template` 函数中，查出 wp_code 后判断：
- 匹配 `^[A-N]\d+-1$` → 调用 `AdjudicationExportTemplateService.generate()`
- 不匹配 → 保持原有 FileResponse 逻辑

## Data Models

### 审定表列结构（标准 12 列）

| 列号 | 一级表头 | 二级表头 | 列键 | 可编辑 |
|------|----------|----------|------|--------|
| 1 | 项目 | — | item | ✓ (预填) |
| 2 | 期初 | 未审 | priorUnadjusted | ✓ |
| 3 | 期初 | AJE | priorAje | ✓ |
| 4 | 期初 | RJE | priorRje | ✓ |
| 5 | 期初 | 审定 | priorAudited | ✗ (= 未审+AJE+RJE) |
| 6 | 期末 | 未审 | currentUnadjusted | ✓ |
| 7 | 期末 | AJE | currentAje | ✓ |
| 8 | 期末 | RJE | currentRje | ✓ |
| 9 | 期末 | 审定 | currentAudited | ✗ (= 未审+AJE+RJE) |
| 10 | 变动额 | — | change | ✗ (= 期末审定-期初审定) |
| 11 | 变动率 | — | changeRate | ✗ (= 变动额/期初审定) |
| 12 | 原因分析 | — | reason | ✓ |

### 含账龄列的扩展结构

账龄列插入在"期末审定"之后、"变动额"之前（与前端 el-table 对齐）。具体位置由 `build_aging_headers` 返回的列头决定。

### 行骨架结构 (from extract_audit_rows)

```python
{
    "id": "row-1",
    "item": "应收账款",          # 项目名称
    "account_code": "1122",     # 科目代码（可选）
    "is_section": False,        # 是否分节标题
    "is_total": False,          # 是否合计行
    "indent": 0,                # 缩进层级
}
```

## Algorithms

### 1. wp_code 识别算法

```python
import re
_ADJUDICATION_RE = re.compile(r"^[A-N]\d+-1$")

def is_adjudication_table(wp_code: str) -> bool:
    return bool(_ADJUDICATION_RE.match(wp_code or ""))
```

### 2. 多行合并表头构建算法

```
Row 2: [项目(merge 2-3)] [期初(merge cols 2-5)] [期末(merge cols 6-9)] [*aging cols*] [变动额(merge 2-3)] [变动率(merge 2-3)] [原因分析(merge 2-3)]
Row 3: [—]               [未审|AJE|RJE|审定]    [未审|AJE|RJE|审定]   [*aging cols*] [—]                  [—]                  [—]

合并操作：
- 项目: merge_cells(row=2, col=1, end_row=3, end_col=1)
- 期初: merge_cells(row=2, col=2, end_row=2, end_col=5)
- 期末: merge_cells(row=2, col=6, end_row=2, end_col=9)
- 变动额: merge_cells(row=2, col=C, end_row=3, end_col=C)  # C = 10 + len(aging_headers)
- 变动率: merge_cells(row=2, col=C+1, end_row=3, end_col=C+1)
- 原因分析: merge_cells(row=2, col=C+2, end_row=3, end_col=C+2)
```

### 3. 账龄科目判定算法

```python
# 去掉 -1 后缀，检查是否在 AGING_SUBJECTS 中
def _get_aging_subject(wp_code: str) -> str | None:
    prefix = wp_code.replace("-1", "")  # "D2-1" → "D2"
    return prefix if prefix in AGING_SUBJECTS else None
```

### 4. 行骨架获取算法

```python
def _get_row_skeleton(template_file_path, wp_code):
    # 1. 构造 sheet_name（审定表的 sheet 名称通常为"审定表{wp_code}"或"{科目}审定表{wp_code}"）
    # 2. 调用 extract_audit_rows(template_file_path, sheet_name) 提取行
    # 3. 失败时返回 [] (降级)
```

## Error Handling

| 场景 | 处理方式 |
|------|----------|
| wp_index 不存在 | 404（与现有行为一致） |
| template_file_path 不存在 | 生成无行骨架的模板（仅表头）|
| AgingConfig 查询失败 | 回退到默认预设段（复用 resolve_aging_segments 内置降级）|
| extract_audit_rows 返回空 | 生成仅含表头的模板 |
| openpyxl 生成失败 | 500 内部错误（极端情况，记录日志）|

## Performance Considerations

- 生成器为**无状态纯函数**（除 DB 读取 AgingConfig），每次请求独立生成
- openpyxl 生成空模板（~20 行）性能极高（< 50ms）
- `extract_audit_rows` 使用 calamine 适配器读取模板 xlsx，I/O 可忽略
- 无缓存需求（模板内容随 AgingConfig 变化、随项目科目行变化）

## Correctness Properties

### Property 1: wp_code 识别一致性
FOR ALL wp_code matching `^[A-N]\d+-1$`, `is_adjudication_table(wp_code)` SHALL return True; FOR ALL wp_code NOT matching this pattern, it SHALL return False.

**Validates: Requirements 1.1, 1.2**

### Property 2: 模板 sheet 结构完整性
FOR ALL valid adjudication wp_codes, the generated workbook SHALL contain exactly 2 sheets: the first named "编制说明", the second named with a data-sheet title containing the wp_code.

**Validates: Requirements 2.2**

### Property 3: 多行合并表头对称性
FOR ALL generated data sheets, row 2 SHALL contain "项目"/"期初"/"期末"/"变动额"/"变动率"/"原因分析" as level-1 headers, and row 3 SHALL contain "未审"/"AJE"/"RJE"/"审定" repeated under both "期初" and "期末".

**Validates: Requirements 3.1, 3.2**

### Property 4: 账龄列动态性
FOR ALL wp_codes in {D2-1, D3-1, F1-1, K1-1, K3-1, G5-1} with N aging segments, the generated template SHALL contain aging column headers whose count equals N × period_count (where period_count is 3 for D2/K1/K3/G5 and 2 for D3/F1).

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 5: 行骨架保序性
FOR ALL wp_codes where template xlsx exists and extract_audit_rows returns non-empty, the data sheet project column (from row 4 onwards) SHALL contain the same items in the same order as extract_audit_rows output.

**Validates: Requirements 6.1, 6.2**

### Property 6: 文件名 RFC5987 合规性
FOR ALL generated responses, the Content-Disposition header SHALL contain `filename*=UTF-8''` followed by a percent-encoded filename matching `{wp_code}_{wp_name}审定表_模板.xlsx`.

**Validates: Requirements 7.1, 7.2**

### Property 7: 非审定表零回归
FOR ALL wp_codes NOT matching `^[A-N]\d+-1$`, the export_template endpoint SHALL return the same FileResponse as before (磁盘源 xlsx), with no behavioral change.

**Validates: Requirements 9.1, 9.4**

### Property 8: 编制说明完整性
FOR ALL generated workbooks, the instruction sheet SHALL contain text describing: (1) column meanings, (2) read-only auto-calculated columns with formulas, (3) user-editable columns, (4) import rules.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

### Property 9: 列数一致性
FOR ALL non-aging adjudication tables, the data sheet header row SHALL have exactly 12 columns. FOR aging tables with N segments and P periods, it SHALL have 12 + N×P columns.

**Validates: Requirements 3.1, 3.2, 4.2**

### Property 10: 合并单元格正确性
FOR ALL generated data sheets, merged_cells SHALL include: (1) vertical merges for "项目"/"变动额"/"变动率"/"原因分析" spanning rows 2-3, (2) horizontal merges for "期初" spanning 4 columns and "期末" spanning 4 columns in row 2.

**Validates: Requirements 3.3, 3.4**

### Property 11: BytesIO 有效性
FOR ALL generate() calls that succeed, the returned BytesIO SHALL be a valid xlsx file loadable by openpyxl without errors.

**Validates: Requirements 2.1, 10.4**

## Dependencies

### 复用的现有模块

| 模块 | 用途 |
|------|------|
| `_cycle_import_export_common.workbook_to_response` | RFC5987 StreamingResponse |
| `_cycle_import_export_common.resolve_aging_segments` | 项目级账龄段解析 |
| `_cycle_import_export_common.build_aging_headers` | 账龄列头生成 |
| `_cycle_import_export_common.subject_aging_periods` | 科目账龄期间列表 |
| `wp_audit_sheet_extract.extract_audit_rows` | 行骨架提取 |
| `wp_render_config._resolve_template_path` | 模板文件路径解析 |

### 新增依赖

无新增外部依赖。openpyxl 已在项目中使用。

## Testing Strategy

- **PBT (Hypothesis)**: P1 (wp_code 识别)、P4 (账龄列数)、P9 (列数一致性)
- **Unit tests**: P2 (sheet 结构)、P3 (表头内容)、P5 (行骨架保序)、P10 (合并单元格)、P11 (xlsx 有效性)
- **Integration test**: P6 (RFC5987 header)、P7 (非审定表零回归)、P8 (编制说明内容)
