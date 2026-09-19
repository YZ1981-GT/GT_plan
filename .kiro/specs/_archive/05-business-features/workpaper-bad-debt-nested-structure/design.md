# Design Document: 坏账准备明细表嵌套子表结构

## Overview

本设计实现致同 2025 修订版 D2-3（应收账款坏账准备明细表）的嵌套子表结构。核心是一个两层树结构：Parent_Row（计提类别）→ Child_Row（明细行），加上 Summary_Row（合计行）做顶层汇总。

关键能力：
- **枚举定义**：INDIVIDUAL / CREDIT_RISK_AGING / CREDIT_RISK_OTHER / OTHER 四种计提方法
- **嵌套 CRUD**：父行+子行动态增删，层级关系完整性保证
- **Auto-SUM**：子行→父行→合计行三级汇总 + 平衡公式校验
- **辅助预填**：从试算表 1231 科目自动带入期初/期末未审数
- **AJE 联动**：审定数与未审数差额自动生成建议调整分录
- **公式引擎集成**：WP 函数支持按父行级别引用汇总值
- **序列化**：完整 round-trip JSON 序列化/反序列化
- **导出**：14 列致同模板格式 xlsx 输出

技术栈：FastAPI + SQLAlchemy async + PostgreSQL / Vue3 + Univer / hypothesis(max_examples=5)

## Architecture

```mermaid
graph TD
    subgraph Frontend[Vue3 + Univer]
        UE[Univer Editor<br/>层级渲染/展折/右键菜单]
        API[apiProxy<br/>REST 调用]
    end

    subgraph Backend[FastAPI]
        R[bad_debt_router.py<br/>/api/workpapers/{wp_id}/bad-debt-rows]
        NTS[NestedTableService<br/>CRUD + 层级管理]
        ASE[AutoSumEngine<br/>三级汇总 + 校验]
        PFS[PrefillService<br/>TB 1231 预填]
        AJE[AjeGenerator<br/>差额→建议分录]
        SER[Serializer<br/>JSON round-trip]
        FE[FormulaEngine<br/>WP 函数扩展]
    end

    subgraph DB[PostgreSQL]
        T[bad_debt_detail_rows<br/>V070]
    end

    UE --> API --> R
    R --> NTS
    NTS --> ASE
    NTS --> PFS
    NTS --> AJE
    NTS --> SER
    FE -.->|WP('D2','坏账..','本期计提合计')| NTS
    NTS --> T
    PFS --> TBS[TrialBalanceService]
    AJE --> ADJ[AdjustmentService]
```

设计原则：
1. **service 只 flush 不 commit**：router 统一 commit
2. **三层一致**：V070 DDL + ORM Model + Service 方法同步
3. **router_registry 注册**：新 router 注册到 `workpaper.py` 的「数据」组
4. **乐观锁**：version 字段防止并发覆写

## Components and Interfaces

### 1. NestedTableService (`backend/app/services/bad_debt_nested_table_service.py`)

核心服务，管理父子行 CRUD、排序、层级校验。

```python
class NestedTableService:
    def __init__(self, db: AsyncSession): ...

    # CRUD
    async def get_tree(self, wp_index_id: UUID) -> BadDebtTree: ...
    async def create_parent_row(self, wp_index_id: UUID, data: CreateParentRowDTO) -> ParentRowResponse: ...
    async def create_child_row(self, parent_row_id: UUID, data: CreateChildRowDTO) -> ChildRowResponse: ...
    async def update_row(self, row_id: UUID, data: UpdateRowDTO) -> RowResponse: ...
    async def delete_row(self, row_id: UUID) -> None: ...

    # 序列化
    async def serialize(self, wp_index_id: UUID) -> dict: ...
    async def deserialize(self, wp_index_id: UUID, payload: dict) -> list[str]: ...

    # 校验
    async def validate_integrity(self, wp_index_id: UUID) -> list[ValidationError]: ...
```

### 2. AutoSumEngine (`backend/app/services/bad_debt_auto_sum.py`)

纯计算模块，无 DB 依赖（接收行数据列表，返回汇总结果）。

```python
class AutoSumEngine:
    AMOUNT_COLUMNS: ClassVar[list[str]]  # amount_b ~ amount_n (13列)

    @staticmethod
    def sum_children(children: list[RowAmounts]) -> RowAmounts: ...

    @staticmethod
    def sum_parents(parents: list[RowAmounts]) -> RowAmounts: ...

    @staticmethod
    def validate_balance_formula(row: RowAmounts) -> BalanceCheck: ...
```

平衡公式：`N = E + F + G - H - I - J + L + M`

### 3. PrefillService (`backend/app/services/bad_debt_prefill_service.py`)

从 TrialBalanceService 查科目 1231 余额，仅空值时预填。

```python
class BadDebtPrefillService:
    def __init__(self, db: AsyncSession): ...

    async def prefill_summary(self, wp_index_id: UUID, project_id: UUID, year: int) -> PrefillResult: ...
```

### 4. AjeGenerator (`backend/app/services/bad_debt_aje_generator.py`)

计算审定数-未审数差额，生成建议调整分录。

```python
class BadDebtAjeGenerator:
    def __init__(self, db: AsyncSession): ...

    async def generate_suggestion(self, wp_index_id: UUID) -> AjeSuggestion | None: ...
```

### 5. Router (`backend/app/routers/bad_debt_rows.py`)

RESTful 端点，注册到 `router_registry/workpaper.py` 数据组。

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/workpapers/{wp_id}/bad-debt-rows` | 获取完整树 |
| POST | `/api/workpapers/{wp_id}/bad-debt-rows/parents` | 新增父行 |
| POST | `/api/workpapers/{wp_id}/bad-debt-rows/{parent_id}/children` | 新增子行 |
| PUT | `/api/workpapers/{wp_id}/bad-debt-rows/{row_id}` | 更新单行金额 |
| DELETE | `/api/workpapers/{wp_id}/bad-debt-rows/{row_id}` | 删除行 |
| GET | `/api/workpapers/{wp_id}/bad-debt-rows/provision-methods` | 查枚举列表 |
| POST | `/api/workpapers/{wp_id}/bad-debt-rows/prefill` | 触发预填 |
| GET | `/api/workpapers/{wp_id}/bad-debt-rows/aje-suggestion` | 获取建议分录 |
| POST | `/api/workpapers/{wp_id}/bad-debt-rows/serialize` | 导出 JSON |
| POST | `/api/workpapers/{wp_id}/bad-debt-rows/deserialize` | 导入 JSON |

### 6. FormulaEngine WP 函数扩展

在现有 `WPExecutor.execute` 中扩展对 D2-3 嵌套结构的寻址：

- `=WP('D2','坏账准备明细表D2-3','本期计提合计')` → Summary_Row.amount_f
- `=WP('D2','坏账准备明细表D2-3','单项评估计提.期末审定数')` → INDIVIDUAL 父行.amount_n

### 7. 前端组件 (`frontend/src/views/workpaper/components/GtBadDebtSheet.vue`)

Univer 编辑器上层封装：
- 层级渲染（父行加粗 / 子行缩进 "其中：XXX"）
- 展开/折叠交互
- 右键菜单（新增/删除/插入子行）
- 汇总列只读保护
- 预填来源 tooltip


## Data Models

### Database Table: `bad_debt_detail_rows` (V070)

```sql
CREATE TABLE IF NOT EXISTS bad_debt_detail_rows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wp_index_id UUID NOT NULL REFERENCES wp_index(id) ON DELETE CASCADE,
    parent_row_id UUID REFERENCES bad_debt_detail_rows(id) ON DELETE CASCADE,
    provision_method VARCHAR(30),  -- 仅父行有值: INDIVIDUAL/CREDIT_RISK_AGING/CREDIT_RISK_OTHER/OTHER
    sort_order INT NOT NULL DEFAULT 0,
    row_label VARCHAR(200) NOT NULL,
    -- 13 金额列 (B~N，排除 A 项目名)
    amount_b NUMERIC(18,2),  -- 期初未审数
    amount_c NUMERIC(18,2),  -- 期初账项调整
    amount_d NUMERIC(18,2),  -- 重分类调整(期初)
    amount_e NUMERIC(18,2),  -- 期初审定数
    amount_f NUMERIC(18,2),  -- 本期计提
    amount_g NUMERIC(18,2),  -- 其他增加
    amount_h NUMERIC(18,2),  -- 本期转回
    amount_i NUMERIC(18,2),  -- 核销
    amount_j NUMERIC(18,2),  -- 其他减少
    amount_k NUMERIC(18,2),  -- 期末未审数
    amount_l NUMERIC(18,2),  -- 期末账项调整
    amount_m NUMERIC(18,2),  -- 重分类调整(期末)
    amount_n NUMERIC(18,2),  -- 期末审定数
    version INT NOT NULL DEFAULT 1,  -- 乐观锁
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_bad_debt_rows_wp_index ON bad_debt_detail_rows(wp_index_id);
CREATE INDEX IF NOT EXISTS ix_bad_debt_rows_parent ON bad_debt_detail_rows(parent_row_id);
-- 同一 wp_index 下 provision_method 唯一（仅父行有值）
CREATE UNIQUE INDEX IF NOT EXISTS uq_bad_debt_provision_method
    ON bad_debt_detail_rows(wp_index_id, provision_method)
    WHERE provision_method IS NOT NULL;
```

### ORM Model

```python
class ProvisionMethod(str, Enum):
    INDIVIDUAL = "INDIVIDUAL"                    # 按单项评估计提
    CREDIT_RISK_AGING = "CREDIT_RISK_AGING"      # 信用风险组合-账龄分析法
    CREDIT_RISK_OTHER = "CREDIT_RISK_OTHER"      # 信用风险组合-其他组合
    OTHER = "OTHER"                              # 其他

PROVISION_METHOD_LABELS: dict[ProvisionMethod, str] = {
    ProvisionMethod.INDIVIDUAL: "按单项评估计提",
    ProvisionMethod.CREDIT_RISK_AGING: "信用风险组合-账龄分析法",
    ProvisionMethod.CREDIT_RISK_OTHER: "信用风险组合-其他组合",
    ProvisionMethod.OTHER: "其他",
}


class BadDebtDetailRow(Base, TimestampMixin):
    __tablename__ = "bad_debt_detail_rows"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wp_index_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("wp_index.id", ondelete="CASCADE"), nullable=False)
    parent_row_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bad_debt_detail_rows.id", ondelete="CASCADE"), nullable=True)
    provision_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_label: Mapped[str] = mapped_column(String(200), nullable=False)
    # 13 金额列
    amount_b: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_c: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_d: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_e: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_f: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_g: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_h: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_i: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_j: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_k: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_l: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_m: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_n: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # relationships
    children: Mapped[list["BadDebtDetailRow"]] = relationship(
        "BadDebtDetailRow", back_populates="parent", cascade="all, delete-orphan",
        order_by="BadDebtDetailRow.sort_order"
    )
    parent: Mapped["BadDebtDetailRow | None"] = relationship(
        "BadDebtDetailRow", remote_side="BadDebtDetailRow.id", back_populates="children"
    )

    @property
    def is_parent(self) -> bool:
        return self.parent_row_id is None and self.provision_method is not None

    @property
    def is_child(self) -> bool:
        return self.parent_row_id is not None
```

### Pydantic Schemas (Request/Response)

```python
class RowAmounts(BaseModel):
    """13 金额列的值对象"""
    amount_b: Decimal | None = None
    amount_c: Decimal | None = None
    # ... amount_d ~ amount_n
    amount_n: Decimal | None = None

class CreateParentRowDTO(BaseModel):
    provision_method: ProvisionMethod
    row_label: str

class CreateChildRowDTO(BaseModel):
    row_label: str
    amount_e: Decimal | None = None  # 期初审定数
    amount_k: Decimal | None = None  # 期末未审数
    amount_n: Decimal | None = None  # 期末审定数

class UpdateRowDTO(BaseModel):
    row_label: str | None = None
    amounts: RowAmounts | None = None
    version: int  # 乐观锁必传

class ChildRowResponse(BaseModel):
    id: UUID
    parent_row_id: UUID
    sort_order: int
    row_label: str
    amounts: RowAmounts
    version: int

class ParentRowResponse(BaseModel):
    id: UUID
    provision_method: ProvisionMethod
    provision_method_label: str
    sort_order: int
    row_label: str
    amounts: RowAmounts
    children: list[ChildRowResponse]
    version: int
    is_editable: bool  # 无子行时可编辑金额

class SummaryRowResponse(BaseModel):
    amounts: RowAmounts
    balance_check: BalanceCheck

class BadDebtTreeResponse(BaseModel):
    wp_index_id: UUID
    summary: SummaryRowResponse
    parents: list[ParentRowResponse]
    prefill_source: str | None  # "试算表 1231 坏账准备" or None

class BalanceCheck(BaseModel):
    """平衡公式校验结果"""
    is_balanced: bool
    expected_n: Decimal
    actual_n: Decimal
    diff: Decimal
```

### ProvisionMethod Enum（数据库侧用 VARCHAR 存储，不建 PG enum type）

设计决策：使用 VARCHAR(30) + 应用层枚举校验，避免 ALTER TYPE ADD VALUE 的事务限制问题。unique partial index 已保证同一底稿下不重复。


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of the system—a formal statement bridging human-readable specs and machine-verifiable guarantees. 全部以 hypothesis 实现，max_examples=5。*

### Property 1: 父行汇总等于子行合计

*For any* Parent_Row with a set of Child_Rows, each of the 13 amount columns of the Parent_Row equals the sum of the corresponding columns across all its Child_Rows (when children exist).

**Validates: Requirements 3.1, 3.3**

### Property 2: 合计行等于所有父行合计

*For any* set of Parent_Rows, each of the 13 amount columns of the Summary_Row equals the sum of the corresponding columns across all Parent_Rows.

**Validates: Requirements 3.2, 3.3**

### Property 3: 平衡公式不变量

*For any* row, the balance check computes expected_n = E + F + G - H - I - J + L + M, and is_balanced is true iff |expected_n - actual_n| < 0.01.

**Validates: Requirements 3.4**

### Property 4: Decimal 精度保持

*For any* sum operation over amount columns, the result retains exactly 2 decimal places and uses Decimal arithmetic (no float drift).

**Validates: Requirements 3.6, 10.3**

### Property 5: 枚举唯一性

*For any* sequence of create_parent_row operations on the same wp_index, attempting to create a second parent with an already-used provision_method is rejected.

**Validates: Requirements 1.3, 2.6**

### Property 6: 预填仅空值

*For any* prefill operation, only cells that are empty (None) before prefill are populated; cells with existing values remain unchanged.

**Validates: Requirements 4.3**

### Property 7: AJE 方向正确性

*For any* difference between audited_n and unaudited_k: if audited_n > unaudited_k, the suggested AJE debits 资产减值损失 / credits 坏账准备; if audited_n < unaudited_k, the reverse. The AJE amount equals |audited_n - unaudited_k|.

**Validates: Requirements 5.2, 5.3, 5.4**

### Property 8: 序列化 Round-Trip

*For any* valid nested structure, serialize then deserialize produces a semantically equivalent structure (same parents, children, ordering, provision_methods, amounts).

**Validates: Requirements 11.1, 11.2, 11.3**

### Property 9: 层级完整性

*For any* nested structure, every Child_Row's parent_row_id references a valid Parent_Row within the same wp_index_id; no orphan child rows exist.

**Validates: Requirements 2.6, 10.4**

### Property 10: 级联删除

*For any* Parent_Row deletion, all its Child_Rows are also deleted (no orphans remain).

**Validates: Requirements 8.4**

### Property 11: 乐观锁冲突检测

*For any* two concurrent updates to the same row with the same starting version, the second update (with stale version) is rejected with a 409 conflict.

**Validates: Requirements 8.5**

### Property 12: 子行新增排序单调

*For any* sequence of create_child_row operations on the same parent, each new child receives a sort_order strictly greater than all existing children's sort_orders.

**Validates: Requirements 2.4**

## Error Handling

| 错误场景 | 处理策略 | HTTP |
|----------|----------|------|
| 重复 provision_method 父行 | unique partial index 拦截 → ValueError | 409 |
| 删除最后一个父行 | service 拒绝 + 提示至少保留一个 | 400 |
| 乐观锁 version 不匹配 | 检测 stale version | 409 |
| Child_Row parent_row_id 无效 | 层级完整性校验失败 | 422 |
| 金额超 NUMERIC(18,2) 精度 | Pydantic + DB 约束拦截 | 422 |
| TB 无 1231 科目 | 预填跳过不报错 | 200 (no-op) |
| deserialize JSON 缺字段/层级无效 | 返回详细 ValidationError 列表 | 422 |
| 父行有子行时直接编辑金额列 | 前端只读保护 + 后端拒绝 | 400 |

通用原则：service 只 flush 不 commit（router 统一 commit）；汇总重算失败不阻塞单行保存（标记校验警告）；AJE 建议生成失败记日志不阻塞底稿保存。

## Testing Strategy

### Property-Based Tests（hypothesis，max_examples=5）

12 条 correctness property 各对应一个 PBT，标记格式：
```python
# Feature: workpaper-bad-debt-nested-structure, Property N: {描述}
@given(...)
@settings(max_examples=5, deadline=None)
def test_property_N_...(...): ...
```

| Property | 测试文件 | 生成策略 |
|----------|----------|----------|
| P1 父汇总=子合计 | test_bad_debt_auto_sum_properties.py | st_child_rows() |
| P2 合计=父合计 | test_bad_debt_auto_sum_properties.py | st_parent_rows() |
| P3 平衡公式 | test_bad_debt_auto_sum_properties.py | st_row_amounts() |
| P4 Decimal 精度 | test_bad_debt_auto_sum_properties.py | st_decimals() |
| P5 枚举唯一 | test_bad_debt_nested_properties.py | st_provision_methods() |
| P6 预填仅空值 | test_bad_debt_prefill_properties.py | st_cell_states() |
| P7 AJE 方向 | test_bad_debt_aje_properties.py | st_amount_pairs() |
| P8 序列化 round-trip | test_bad_debt_serialize_properties.py | st_nested_tree() |
| P9 层级完整 | test_bad_debt_nested_properties.py | st_nested_tree() |
| P10 级联删除 | test_bad_debt_nested_properties.py | st_nested_tree() |
| P11 乐观锁 | test_bad_debt_nested_properties.py | st_concurrent_updates() |
| P12 排序单调 | test_bad_debt_nested_properties.py | st_child_sequence() |

### Unit Tests
- AutoSumEngine 边界：空子行/单子行/负数金额/None 混合
- AjeGenerator：零差额（不生成）/补提/冲回
- PrefillService：1231 缺失/已有值不覆盖
- Serializer：缺字段/层级断裂的 deserialize 错误

### 集成测试
- 全链路：建父行→建子行→编辑→Auto-SUM→预填→生成 AJE→序列化 round-trip
- 契约测试：V070 DDL 列 == ORM Mapped 列（三层一致）
- in-process ASGI httpx 调通全部 10 个端点（200/409/422）
