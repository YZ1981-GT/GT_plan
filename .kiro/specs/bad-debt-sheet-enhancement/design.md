# Design Document — bad-debt-sheet-enhancement

## Overview

为 GtBadDebtSheet 组件增加四大增强能力：导出空模板、导出数据、Excel 导入（带预览弹窗确认）、账龄段枚举字典弹窗。核心思路是复用已有 `BadDebtExportService`（导出引擎）和 `NestedTableService`（嵌套表 CRUD），新增导入解析服务 `BadDebtImportService` 和账龄段持久化 `AgingSegmentService`，前端新增两个 element-plus 对话框组件。

设计决策：
- **导出模板**复用 `BadDebtExportService`，增加 `template_only=True` 参数跳过金额写入
- **导入**采用两阶段模式（parse → preview → commit），后端负责行匹配逻辑，前端仅展示
- **账龄段**独立持久化表 `aging_segments`，关联 `wp_index_id` 级别，支持预设方案+自定义

## Architecture

```mermaid
graph TD
    subgraph Frontend[Vue3 + Element-Plus]
        BDS[GtBadDebtSheet.vue]
        IPD[ImportPreviewDialog.vue]
        ADD[AgingDictionaryDialog.vue]
    end

    subgraph Backend[FastAPI]
        R[bad_debt_rows router<br/>/api/workpapers/{wp_id}/bad-debt-rows]
        EXP[BadDebtExportService<br/>导出模板 + 导出数据]
        IMP[BadDebtImportService<br/>解析 + 匹配 + 批量写入]
        AGS[AgingSegmentService<br/>账龄段 CRUD + 子行同步]
        NTS[NestedTableService<br/>已有嵌套表 CRUD]
    end

    subgraph DB[PostgreSQL]
        ROWS[(bad_debt_detail_rows)]
        AGING[(aging_segments)]
    end

    BDS --> R
    IPD --> R
    ADD --> R
    R --> EXP
    R --> IMP
    R --> AGS
    IMP --> NTS
    AGS --> NTS
    EXP --> NTS
    NTS --> ROWS
    AGS --> AGING
```

**数据流：**
- 导出模板：前端 GET → router → `BadDebtExportService.export_bytes(wp_index_id, template_only=True)` → xlsx 流式响应
- 导出数据：前端 GET → router → `BadDebtExportService.export_bytes(wp_index_id)` → xlsx 流式响应
- 导入解析：前端 POST multipart → router → `BadDebtImportService.parse_and_match(file, wp_index_id)` → 匹配结果 JSON
- 导入写入：前端 POST JSON → router → `BadDebtImportService.commit_matched_rows(wp_index_id, matched_rows)` → 批量 PUT 各行
- 账龄段 CRUD：前端 ↔ router ↔ `AgingSegmentService` ↔ `aging_segments` 表 + `NestedTableService` 同步子行

## Components and Interfaces

### 1. BadDebtExportService 增强

已有服务，新增 `template_only` 参数：

```python
class BadDebtExportService:
    async def export_bytes(
        self,
        wp_index_id: UUID,
        meta: BadDebtExportMeta | None = None,
        template_only: bool = False,  # 新增：True 时金额列全部留空
    ) -> io.BytesIO: ...
```

`template_only=True` 时，`_write_row` 跳过金额写入（所有 amount 列留空），仅保留行标签结构。

### 2. BadDebtImportService（新建）

```python
class ImportRowMatch(BaseModel):
    """单行匹配结果"""
    excel_row_index: int           # Excel 行号（1-based）
    excel_label: str               # A 列原始项目名
    status: Literal["matched", "unmatched"]
    matched_row_id: UUID | None    # matched 时指向 bad_debt_detail_rows.id
    matched_row_label: str | None  # 匹配到的树行标签
    is_parent: bool                # 是否父行
    amounts: dict[str, Decimal | None]  # B~N 列解析后的金额

class ImportParseResult(BaseModel):
    """解析+匹配结果"""
    rows: list[ImportRowMatch]
    matched_count: int
    unmatched_count: int
    errors: list[str]  # 格式校验错误（非空时整体拒绝）

class BadDebtImportService:
    def __init__(self, db: AsyncSession): ...

    async def parse_and_match(
        self, file: UploadFile, wp_index_id: UUID
    ) -> ImportParseResult:
        """
        1. 校验 xlsx 格式（>=14 列，A 列非空）
        2. 跳过表头行（R1-R11），从 R12 开始读数据行
        3. 去除 A 列前导空格后与当前树 row_label 精确匹配
        4. 解析 B~N 列金额（支持 int/float/Decimal，空值=None）
        """
        ...

    async def commit_matched_rows(
        self, wp_index_id: UUID, rows: list[ImportRowMatch]
    ) -> int:
        """
        批量更新匹配到的行：
        - 仅处理 status="matched" 的行
        - 对每行，仅覆盖 amounts 中非 None 的金额列（空单元格不覆盖原值）
        - 返回实际更新行数
        """
        ...
```

### 3. AgingSegmentService（新建）

```python
class AgingPreset(str, Enum):
    THREE_YEAR = "THREE_YEAR"  # 1年以内/1-2年/2-3年/3年以上
    FIVE_YEAR = "FIVE_YEAR"   # 1年以内/1-2年/2-3年/3-4年/4-5年/5年以上
    CUSTOM = "CUSTOM"

class AgingSegmentConfig(BaseModel):
    """账龄段配置"""
    preset: AgingPreset
    segments: list[str]  # 有序段名列表

class AgingSegmentService:
    PRESETS: dict[AgingPreset, list[str]] = {
        AgingPreset.THREE_YEAR: ["1年以内", "1-2年", "2-3年", "3年以上"],
        AgingPreset.FIVE_YEAR: ["1年以内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上"],
    }

    async def get_config(self, wp_index_id: UUID) -> AgingSegmentConfig | None:
        """获取当前底稿的账龄段配置（不存在返回 None）"""

    async def save_config(
        self, wp_index_id: UUID, config: AgingSegmentConfig
    ) -> None:
        """
        保存账龄段配置 + 同步 CREDIT_RISK_AGING 子行：
        1. upsert aging_segments 表
        2. 找到/创建 CREDIT_RISK_AGING 父行
        3. 删除旧子行，按 segments 列表依次创建新子行
        """

    async def check_has_amounts(self, wp_index_id: UUID) -> bool:
        """检查 CREDIT_RISK_AGING 子行是否有已填金额（用于前端警告）"""
```

### 4. Router 新端点

在已有 `bad_debt_rows` router 中追加端点（静态路径，声明在 `/{row_id}` 之前）：

| Method | Path | Description |
|--------|------|-------------|
| GET | `.../export-template` | 导出空模板 xlsx（StreamingResponse） |
| GET | `.../export-data` | 导出含数据 xlsx（StreamingResponse） |
| POST | `.../import-parse` | 上传 xlsx 解析+匹配（multipart） |
| POST | `.../import-commit` | 确认写入匹配行 |
| GET | `.../aging-segments` | 获取账龄段配置 |
| PUT | `.../aging-segments` | 保存账龄段配置 + 同步子行 |
| GET | `.../aging-segments/has-amounts` | 检查是否有已填金额 |

### 5. 前端组件

#### ImportPreviewDialog.vue

```typescript
// Props
interface Props {
  visible: boolean
  parseResult: ImportParseResult | null
}

// Emits
defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
  (e: 'update:visible', val: boolean): void
}>()
```

功能：
- el-dialog 弹窗，el-table 展示匹配结果
- 行状态标记：matched 绿色、unmatched 红色高亮
- 底部显示统计（N 行匹配 / M 行未匹配）
- 确认/取消按钮

#### AgingDictionaryDialog.vue

```typescript
interface Props {
  visible: boolean
  wpId: string
}

defineEmits<{
  (e: 'saved', segments: string[]): void
  (e: 'update:visible', val: boolean): void
}>()
```

功能：
- 左侧预设方案选择（三年段/五年段/自定义）
- 右侧段列表可编辑（拖拽排序/新增/删除/改名）
- 实时校验：段名非空且不重复
- 确认时若有已填金额，先弹二次确认警告
- 确认后调用 PUT aging-segments 保存

## Data Models

### 新建表：aging_segments（迁移 V091）

```sql
-- V091__aging_segments.sql
CREATE TABLE IF NOT EXISTS aging_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wp_index_id UUID NOT NULL REFERENCES wp_index(id) ON DELETE CASCADE,
    preset VARCHAR(20) NOT NULL DEFAULT 'CUSTOM',  -- THREE_YEAR/FIVE_YEAR/CUSTOM
    segments JSONB NOT NULL DEFAULT '[]'::jsonb,    -- ["1年以内","1-2年",...]
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_aging_segments_wp UNIQUE (wp_index_id)
);

CREATE INDEX ix_aging_segments_wp ON aging_segments(wp_index_id);

COMMENT ON TABLE aging_segments IS '账龄段枚举配置（每个底稿一条，关联 wp_index_id）';
```

### ORM 模型

```python
class AgingSegment(Base, TimestampMixin):
    __tablename__ = "aging_segments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wp_index_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("wp_index.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    preset: Mapped[str] = mapped_column(String(20), nullable=False, default="CUSTOM")
    segments: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
```

### 已有表复用

- `bad_debt_detail_rows`：无需改动，CREDIT_RISK_AGING 父行的子行即为账龄段子行
- `wp_index`：通过 FK 关联账龄段配置

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Template structure preserves tree hierarchy

*For any* valid bad debt tree (with 0..N parents, each with 0..M children), exporting a template should produce an xlsx where:
- Row count in data area = sum of (1 + len(children)) for each parent
- Each parent row A column = row_label (no indent)
- Each child row A column = "  " + row_label (two-space indent)
- All B~N columns (amount cells) are empty (None)
- Header area has exactly 14 columns with correct group titles

**Validates: Requirements 1.2, 1.3, 1.4**

### Property 2: Row label matching correctness

*For any* set of Excel data rows and any bad debt tree, the import matching algorithm should:
- Strip leading whitespace from Excel A column before comparing
- Mark a row as "matched" if and only if the stripped label equals some row_label in the tree
- Mark all other rows as "unmatched"
- Return exactly one match per Excel row (no duplicates, no missed rows)

**Validates: Requirements 3.2, 3.3**

### Property 3: Export-Import round-trip

*For any* filled bad debt tree (parents with children, all amounts as Decimal(18,2) or None), exporting data to xlsx then importing and committing should produce amounts equal to the original values (within Decimal(18,2) precision).

**Validates: Requirements 5.1, 5.2**

### Property 4: Partial import preserves existing values

*For any* tree with pre-existing amounts and any import file where some cells are empty (None), committing the import should:
- Overwrite only the cells where the import has a non-None value
- Leave cells corresponding to empty import cells unchanged (original value preserved)

**Validates: Requirements 5.3, 3.6**

### Property 5: Aging segment validation

*For any* list of segment names submitted to the aging segment service:
- If any segment name is empty string or whitespace-only, validation rejects
- If any two segment names are identical (after trim), validation rejects
- A valid list (all non-empty, all unique) is accepted

**Validates: Requirements 4.6**

### Property 6: Aging segment persistence round-trip and child sync

*For any* valid aging segment configuration (preset + ordered segments list), saving then loading should return an equivalent configuration. Additionally, after save, the CREDIT_RISK_AGING parent's children should have row_labels matching the segments list in exact order.

**Validates: Requirements 4.7, 4.8, 4.11**

## Error Handling

| 场景 | HTTP 状态码 | 错误描述 |
|------|------------|----------|
| 导入 xlsx 格式不合法（<14 列） | 422 | `{"error_code": "INVALID_FORMAT", "detail": "..."}` |
| 导入 xlsx A 列缺失 | 422 | `{"error_code": "MISSING_LABEL_COLUMN", "detail": "..."}` |
| 金额解析失败（非数字文本） | 422 | `{"error_code": "AMOUNT_PARSE_ERROR", "detail": "row X, col Y: ..."}` |
| 账龄段段名为空 | 422 | `{"error_code": "EMPTY_SEGMENT_NAME", "detail": "..."}` |
| 账龄段段名重复 | 422 | `{"error_code": "DUPLICATE_SEGMENT_NAME", "detail": "..."}` |
| commit 时行已被他人修改（version 冲突） | 409 | 复用 OptimisticLockError |
| wp_index_id 不存在 | 404 | 标准 404 |
| 文件过大（>10MB） | 413 | 在 router 层拦截 |

前端错误处理：
- 422 错误展示后端返回的 detail 信息（ElMessage.error）
- 409 冲突提示用户刷新后重试
- 网络错误降级为通用"操作失败"提示

## Testing Strategy

### 单元测试（pytest + vitest）

后端：
- `test_bad_debt_import_service.py`：解析/匹配/写入逻辑
- `test_aging_segment_service.py`：CRUD + 子行同步
- `test_bad_debt_export_template.py`：template_only 模式

前端：
- `ImportPreviewDialog.spec.ts`：挂载 + props 驱动渲染
- `AgingDictionaryDialog.spec.ts`：预设选择 + 自定义编辑 + 校验

### Property-Based Tests（Hypothesis）

库：`hypothesis`（Python PBT 库），每个 property test 至少 100 iterations。

每个 property test 必须以注释标注对应 design property：

```python
# Feature: bad-debt-sheet-enhancement, Property 1: Template structure preserves tree hierarchy
# Feature: bad-debt-sheet-enhancement, Property 2: Row label matching correctness
# Feature: bad-debt-sheet-enhancement, Property 3: Export-Import round-trip
# Feature: bad-debt-sheet-enhancement, Property 4: Partial import preserves existing values
# Feature: bad-debt-sheet-enhancement, Property 5: Aging segment validation
# Feature: bad-debt-sheet-enhancement, Property 6: Aging segment persistence round-trip and child sync
```

**Property 1** 生成随机树结构（0~5 parents × 0~8 children，随机 row_label），调用 export template，验证 xlsx 结构。

**Property 2** 生成随机树 + 随机 Excel 行（部分精确匹配、部分不匹配），验证匹配结果正确性。

**Property 3** 生成随机已填树（Decimal(18,2) 金额），export → parse → commit → 对比原始值。

**Property 4** 生成随机已填树 + 部分空单元格的导入数据，commit 后验证空单元格对应的原值不变。

**Property 5** 生成随机字符串列表，验证 validation 函数的接受/拒绝行为。

**Property 6** 生成随机有效段列表，save → load 比对 + 查 children row_labels。

### 集成测试

- Playwright E2E：完整工具栏按钮 → 弹窗 → 确认流程
- API 冒烟测试：新端点 200/422/404 响应码覆盖
