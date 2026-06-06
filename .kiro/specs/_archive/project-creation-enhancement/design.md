# Design Document: 建项流程增强

## Overview

本设计覆盖审计作业平台建项流程六大增强：USCC 格式校验、项目简称必填、唯一性校验、合并/单户前端区分显示、批量建项（模板导出+导入+数据导出）、独立账套导入页。

核心设计原则：
- **前后端双侧校验**：所有业务规则（USCC、必填、唯一性）在前端即时反馈 + 后端权威拒绝，确保安全性
- **存量兼容**：Legacy_Project（company_code 为空）不受新约束影响，新增字段全 nullable + DB 默认值
- **最小侵入**：复用现有 `project_wizard_service.create_project()` 流程，在其内部注入校验链；前端复用 `BasicInfoStep.vue` 表单扩展
- **批量建项复用单项校验**：Batch_Import_Service 逐行调用与单项目相同的校验逻辑，不单独实现校验分支

## Architecture

```mermaid
graph TD
    subgraph Frontend["前端 Vue3"]
        BIS[BasicInfoStep.vue<br/>新增 short_name + USCC 校验]
        PL[Projects.vue<br/>后缀显示规则]
        LIP[LedgerImportPage.vue<br/>新增独立路由页]
        BatchUI[批量建项弹窗<br/>模板下载 + 文件上传 + 结果展示]
        USCCFe[uscc_validator.ts<br/>前端 USCC 校验]
    end

    subgraph Backend["后端 FastAPI"]
        PW[project_wizard.py router<br/>POST /api/projects]
        BWR[batch_project.py router<br/>POST /api/projects/batch-import<br/>GET /api/projects/batch-template<br/>POST /api/projects/batch-export]
        PWS[project_wizard_service.py<br/>create_project() + 校验链]
        USCCBe[uscc_validator.py<br/>后端 USCC 校验]
        UC[uniqueness_checker.py<br/>三元组去重]
        BIS_Svc[batch_project_service.py<br/>Excel 解析 + 逐行校验]
    end

    subgraph DB["PostgreSQL"]
        PJ[projects 表<br/>+short_name VARCHAR(100)<br/>+唯一索引]
    end

    BIS --> PW
    BatchUI --> BWR
    PW --> PWS
    BWR --> BIS_Svc
    PWS --> USCCBe
    PWS --> UC
    BIS_Svc --> PWS
    PWS --> PJ
    USCCFe -.->|等价实现| USCCBe
    LIP --> |复用 components/ledger-import/| LIP
```

### 校验执行顺序（create_project 内）

1. `short_name` 非空 → 拒绝
2. `company_code` 非空 → 拒绝
3. USCC 格式校验（长度 → 字符集 → 校验码）→ 拒绝
4. 唯一性校验（company_code + audit_year + report_scope 三元组）→ 拒绝
5. 通过 → 写入 DB

## Components and Interfaces

### 1. USCC_Validator（前后端各一份）

**后端** `backend/app/services/uscc_validator.py`

```python
def validate_uscc(code: str) -> tuple[bool, str | None]:
    """校验 USCC，返回 (is_valid, error_message)。"""
    ...
```

**前端** `audit-platform/frontend/src/utils/uscc_validator.ts`

```typescript
export function validateUSCC(code: string): { valid: boolean; message?: string }
```

校验规则：
- 长度必须 18 位
- 字符集：`0-9` + `A-H, J-N, P-T, U-W, X`（排除 I, O, Z, S, V）
- 模 31 校验码算法：Wi = 3^(i-1) mod 31（i=1..17），C18 = 31 - (Σ(Ci×Wi) mod 31)，余数 31 映射为 0

### 2. Uniqueness_Checker

**后端** `backend/app/services/uniqueness_checker.py`

```python
async def check_uniqueness(
    company_code: str, audit_year: int, report_scope: str, db: AsyncSession
) -> tuple[bool, str | None]:
    """检查三元组唯一性，返回 (is_unique, error_message)。
    排除 is_deleted=True 的项目。"""
    ...
```

### 3. Batch_Import_Service

**后端** `backend/app/services/batch_project_service.py`

```python
async def generate_template() -> BytesIO:
    """生成建项模板 Excel（数据表 + 说明事项 sheet）。"""

async def parse_and_import(file: UploadFile, db: AsyncSession) -> BatchImportResult:
    """解析上传文件，逐行校验并创建项目。返回成功数+失败明细。"""

async def export_projects(project_ids: list[UUID], db: AsyncSession) -> BytesIO:
    """导出选中项目为 Excel。"""
```

### 4. 前端组件

| 组件 | 变更 |
|------|------|
| `BasicInfoStep.vue` | 新增 `short_name` 字段（必填）；`company_code` 改为必填 + USCC 实时校验 |
| `Projects.vue` | 项目名后追加"（合并）"/"（母公司）"后缀 |
| `BatchImportDialog.vue`（新建）| 批量建项弹窗：模板下载、文件上传、结果预览 |
| `LedgerImportPage.vue`（新建）| 独立账套导入页，组合现有 ledger-import 组件 |

### 5. API Endpoints

| Method | Path | 描述 |
|--------|------|------|
| POST | `/api/projects` | 创建项目（增加 USCC + short_name + 唯一性校验）|
| GET | `/api/projects/batch-template` | 下载建项模板 Excel |
| POST | `/api/projects/batch-import` | 批量导入建项 |
| POST | `/api/projects/batch-export` | 导出选中项目数据为 Excel |

### 6. Ledger Import Page 路由

新增路由 `projects/:projectId/ledger-import`，指向 `LedgerImportPage.vue`。

## Data Models

### DB 迁移（V055）

```sql
-- V055__project_creation_enhancement.sql
ALTER TABLE projects ADD COLUMN IF NOT EXISTS short_name VARCHAR(100);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS audit_year INT;

-- 回填 audit_year（从 wizard_state JSONB 或 name 后缀提取）
UPDATE projects SET audit_year = (wizard_state->'steps'->'basic_info'->'data'->>'audit_year')::int
WHERE audit_year IS NULL
  AND wizard_state->'steps'->'basic_info'->'data'->>'audit_year' IS NOT NULL;

UPDATE projects SET audit_year = EXTRACT(YEAR FROM audit_period_end)::int
WHERE audit_year IS NULL AND audit_period_end IS NOT NULL;

-- 唯一性约束：company_code + audit_year + report_scope（仅非删除 + 非空 company_code）
CREATE UNIQUE INDEX IF NOT EXISTS uq_project_company_year_scope
ON projects (company_code, audit_year, report_scope)
WHERE is_deleted = false AND company_code IS NOT NULL AND audit_year IS NOT NULL;
```

### Schema 变更

`BasicInfoSchema` 新增/修改字段：

```python
class BasicInfoSchema(BaseModel):
    # ... existing fields ...
    company_code: str = Field(min_length=18, max_length=18)  # 必填，USCC 18 位
    short_name: str = Field(min_length=1, max_length=100)  # 项目简称（必填）
```

注：ORM 层 `short_name` 和 `audit_year` 保持 `nullable=True`（存量兼容），Schema 层强制必填（Pydantic 校验在 API 入口拒绝空值）。

### ORM 变更

`Project` 模型新增：

```python
short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
audit_year: Mapped[int | None] = mapped_column(nullable=True, comment="审计年度（物化列，唯一性索引依赖）")
```

### 批量导入结果模型

```python
class BatchImportResult(BaseModel):
    success_count: int
    fail_count: int
    failures: list[BatchImportFailure]

class BatchImportFailure(BaseModel):
    row_number: int
    errors: list[str]
```



## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: USCC 校验一致性（前后端等价）

*For any* arbitrary string input, the frontend `validateUSCC()` function and the backend `validate_uscc()` function SHALL return the same boolean validity result.

**Validates: Requirements 1.8**

### Property 2: 合法 USCC 通过校验（构造正确性）

*For any* 17-character prefix composed entirely of USCC_Charset characters, computing the mod-31 check digit and appending it to form an 18-character code SHALL result in the USCC_Validator judging the code as valid.

**Validates: Requirements 1.6**

### Property 3: 非法 USCC 被拒绝

*For any* string that violates at least one of: (a) length ≠ 18, (b) contains characters outside USCC_Charset, (c) check digit mismatch, the USCC_Validator SHALL return invalid with an appropriate error message.

**Validates: Requirements 1.3, 1.4, 1.5**

### Property 4: 必填字段为空时拒绝创建

*For any* project creation request where `company_code` is empty/None OR `short_name` is empty/whitespace-only, the Project_Service SHALL reject creation and return the corresponding error message.

**Validates: Requirements 1.1, 2.2**

### Property 5: Short_Name 持久化往返

*For any* valid project creation request with a non-whitespace `short_name`, after successful creation, reading the project back SHALL return the same `short_name` value (trimmed).

**Validates: Requirements 2.4, 2.5**

### Property 6: 唯一性三元组重复拒绝

*For any* `(company_code, audit_year, report_scope)` triple, if a non-deleted project with that triple already exists, attempting to create another project with the same triple SHALL be rejected with error message containing the scope's Chinese label ("单户" or "合并").

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 7: 不同 Report_Scope 可共存

*For any* `(company_code, audit_year)` pair, creating one project with `report_scope=standalone` and another with `report_scope=consolidated` SHALL both succeed (no uniqueness violation).

**Validates: Requirements 3.5**

### Property 8: 软删除项目不阻塞新建

*For any* `(company_code, audit_year, report_scope)` triple where the existing project is soft-deleted (`is_deleted=True`), creating a new project with that same triple SHALL succeed.

**Validates: Requirements 3.7**

### Property 9: 项目显示后缀规则

*For any* project, the display name suffix function SHALL: append "（合并）" if `report_scope=consolidated`; append "（母公司）" if `report_scope=standalone` AND a non-deleted consolidated project exists with the same `company_code` and `audit_year`; append nothing otherwise.

**Validates: Requirements 4.1, 4.2, 4.3, 4.5**

### Property 10: 批量导入结果计数一致性

*For any* batch import file with N rows, the returned `success_count + fail_count` SHALL equal N, and `failures` list length SHALL equal `fail_count`.

**Validates: Requirements 5.6**

### Property 11: 批量导出/导入回环解析

*For any* set of existing projects, exporting them to Excel and then parsing that Excel through the batch import parser SHALL successfully parse every row (field structure compatible), preserving Chinese characters.

**Validates: Requirements 5.8, 5.9**

## Error Handling

| 场景 | HTTP Status | 错误消息 |
|------|------------|----------|
| company_code 为空 | 422 | 企业代码为必填项 |
| short_name 为空 | 422 | 项目简称为必填项 |
| USCC 长度错误 | 422 | 统一社会信用代码必须为 18 位 |
| USCC 字符集错误 | 422 | 统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）|
| USCC 校验码错误 | 422 | 统一社会信用代码校验码错误 |
| 唯一性冲突（单户）| 409 | 已存在该单位该年度的单户项目 |
| 唯一性冲突（合并）| 409 | 已存在该单位该年度的合并项目 |
| 批量导入文件格式错误 | 400 | 文件格式不正确，请使用标准建项模板 |
| 批量导入文件过大 | 413 | 文件超过最大行数限制（500 行）|
| 账套导入识别失败 | 现有 API 错误码 | 中文错误信息透传至前端展示 |

前端校验在 blur/submit 时即时反馈，后端作为权威拒绝层。前端校验不通过时阻止请求发出。

## Testing Strategy

### 单元测试

- **USCC Validator（Python）**：已知合法/非法 USCC 样本；边界值（17位/19位/空串）
- **USCC Validator（TypeScript）**：等价样本，确保前后端一致
- **Uniqueness Checker**：mock DB 查询结果测试判重逻辑
- **Batch Import Parser**：Excel 解析正确性（含中文、空行、异常格式）
- **Display Suffix Function**：各种 report_scope 组合的后缀输出

### Property-Based Testing

- **库**：Python 使用 `hypothesis`（已有依赖）；TypeScript 使用 `fast-check`
- **配置**：`max_examples=5`（用户偏好）
- **每条 Correctness Property 对应一个 PBT 测试**，测试注释标注：

```python
# Feature: project-creation-enhancement, Property 1: USCC 校验一致性（前后端等价）
@given(code=st.text(min_size=0, max_size=30))
@settings(max_examples=5)
def test_uscc_frontend_backend_consistency(code):
    ...
```

```python
# Feature: project-creation-enhancement, Property 2: 合法 USCC 通过校验（构造正确性）
@given(prefix=st.text(alphabet=USCC_CHARSET, min_size=17, max_size=17))
@settings(max_examples=5)
def test_valid_uscc_accepted(prefix):
    ...
```

### 集成测试

- **create_project E2E**：in-process ASGI（httpx.ASGITransport）调 POST /api/projects，验证校验链完整执行
- **batch-import E2E**：生成模板 → 填入数据 → 上传 → 验证成功/失败计数
- **Playwright E2E**（独立账套导入页）：导航到新路由 → 验证步骤流程可用

### 测试文件布局

```
backend/tests/test_uscc_validator.py          # Property 1-3 + unit
backend/tests/test_project_creation_validation.py  # Property 4-8
backend/tests/test_project_display_suffix.py  # Property 9
backend/tests/test_batch_project_service.py   # Property 10-11 + unit
audit-platform/frontend/src/utils/__tests__/uscc_validator.spec.ts  # 前端 USCC 单元测试
```
