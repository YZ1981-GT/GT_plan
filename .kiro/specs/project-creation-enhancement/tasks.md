# Tasks: 建项流程增强

> **任务依赖**：Task 1→3→5 / Task 4→5→12 / Task 2→6 / Task 5→8 / Task 7 独立 / Task 9 依赖 8 / Task 10+11 独立可并行
> **实施建议顺序**：1→2→3→4→5→12→6→7→8→9→10→11

## Task 1: USCC 校验器（后端）

- [x] 1.1 创建 `backend/app/services/uscc_validator.py`，实现 `validate_uscc(code: str) -> tuple[bool, str | None]`，包含长度检查、字符集检查、模 31 校验码计算
- [x] 1.2 创建 `backend/tests/test_uscc_validator.py`，包含 Property 2（合法 USCC 通过）和 Property 3（非法 USCC 被拒）的 hypothesis PBT 测试（max_examples=5）+ 已知样本单元测试

## Task 2: USCC 校验器（前端）

- [x] 2.1 创建 `audit-platform/frontend/src/utils/uscc_validator.ts`，实现 `validateUSCC(code: string): { valid: boolean; message?: string }`，逻辑与后端等价
- [x] 2.2 创建 `audit-platform/frontend/src/utils/__tests__/uscc_validator.spec.ts`，单元测试覆盖合法/非法样本

## Task 3: USCC 前后端一致性验证

- [x] 3.1 创建 `backend/tests/fixtures/uscc_test_vectors.json`，包含 50 个测试向量（25 合法 + 25 非法），每条记录 `{input, expected_valid, expected_message}`
- [x] 3.2 在 `backend/tests/test_uscc_validator.py` 中添加测试：读取 fixtures JSON，逐条验证 Python `validate_uscc()` 结果与 expected 一致
- [x] 3.3 在 `audit-platform/frontend/src/utils/__tests__/uscc_validator.spec.ts` 中添加测试：读取同一份 fixtures JSON，逐条验证 TS `validateUSCC()` 结果与 expected 一致（跨语言一致性通过共享 golden file 保证）

## Task 4: 项目简称 + 审计年度物化列（DB + ORM + Schema）

- [x] 4.1 创建 `backend/migrations/V055__project_creation_enhancement.sql`：ADD COLUMN short_name VARCHAR(100) + ADD COLUMN audit_year INT + 回填 audit_year（从 wizard_state JSONB / audit_period_end）+ CREATE UNIQUE INDEX uq_project_company_year_scope
- [x] 4.2 创建 `backend/migrations/R055__project_creation_enhancement.sql` 回滚脚本
- [x] 4.3 在 `backend/app/models/core.py` Project 类新增 `short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)` 和 `audit_year: Mapped[int | None] = mapped_column(nullable=True)`
- [x] 4.4 在 `backend/app/models/audit_platform_schemas.py` BasicInfoSchema 修改 `company_code: str = Field(min_length=18, max_length=18)` 和新增 `short_name: str = Field(min_length=1, max_length=100)`

## Task 5: 建项校验链（后端 service 层）

- [x] 5.1 创建 `backend/app/services/uniqueness_checker.py`，实现 `check_uniqueness(company_code, audit_year, report_scope, db) -> tuple[bool, str | None]`
- [x] 5.2 修改 `backend/app/services/project_wizard_service.py` 的 `create_project()`，在写 DB 前依次执行：short_name 非空校验 → company_code 非空校验 → USCC 格式校验 → 唯一性校验
- [x] 5.3 修改 `_sync_basic_info_to_project()` 同步 `short_name` 和 `audit_year` 字段（audit_year 物化写入）
- [x] 5.4 创建 `backend/tests/test_project_creation_validation.py`，包含 Property 4（必填字段为空拒绝）、Property 5（short_name 往返）、Property 6（唯一性重复拒绝）、Property 7（不同 scope 可共存）、Property 8（软删除不阻塞）的 PBT 测试

## Task 6: 前端建项表单增强

- [x] 6.1 修改 `BasicInfoStep.vue`：新增 `short_name` 输入框（必填），`company_code` 改为必填 + blur 时调用 `validateUSCC()` 实时校验并显示错误
- [x] 6.2 在 wizard store（`useWizardStore`）的 BasicInfo 类型中新增 `short_name` 字段

## Task 7: 项目列表后缀显示

- [x] 7.1 创建 `audit-platform/frontend/src/utils/project_display.ts`，导出 `getProjectDisplayName(project, allProjects)` 函数实现后缀规则
- [x] 7.2 修改 `Projects.vue` 项目列表和下拉使用 `getProjectDisplayName()`
- [x] 7.3 创建 `backend/tests/test_project_display_suffix.py`，实现 Property 9 的 PBT 测试（纯函数逻辑在后端也实现一份供 API 响应使用）

## Task 8: 批量建项（后端）

- [x] 8.1 创建 `backend/app/services/batch_project_service.py`，实现 `generate_template()`（两个 sheet：数据表+说明事项）、`parse_and_import(file, db)`（逐行校验+创建）、`export_projects(project_ids, db)`
- [x] 8.2 创建 `backend/app/routers/batch_project.py`，实现 GET /api/projects/batch-template、POST /api/projects/batch-import、POST /api/projects/batch-export
- [x] 8.3 在 `backend/app/router_registry/` 对应组注册新 router
- [x] 8.4 创建 `backend/tests/test_batch_project_service.py`，包含 Property 10（结果计数一致）和 Property 11（导出/导入回环解析）的 PBT 测试 + 单元测试

## Task 9: 批量建项（前端）

- [x] 9.1 创建 `audit-platform/frontend/src/components/wizard/BatchImportDialog.vue`，包含模板下载按钮、文件上传区、结果展示表格（成功数+失败行号+错误原因）
- [x] 9.2 在 `Projects.vue` 添加「批量建项」按钮触发 BatchImportDialog

## Task 10: 独立账套导入页

- [x] 10.1 创建 `audit-platform/frontend/src/views/LedgerImportPage.vue`，组合 UploadStep + DetectionPreview + ColumnMappingEditor + ImportProgress + ErrorDialog，实现步骤式流程
- [x] 10.2 在 `router/index.ts` 新增路由 `projects/:projectId/ledger-import` 指向 LedgerImportPage
- [x] 10.3 导入成功后跳转至查账页（`/projects/:projectId/ledger`）
- [x] 10.4 修改 `Projects.vue` 的 `openImport()` 导航目标从 `/projects/${id}/ledger?import=1` 改为 `/projects/${id}/ledger-import`

## Task 11: 查账页 404 容错

- [x] 11.1 修改 `LedgerPenetration.vue`：对 `/account-chart` 和 `/ledger/datasets` 的 404 响应静默处理（catch 不弹 toast），新项目无数据时显示空态引导而非红色报错

## Task 12: ProjectCreateResponse 扩展

- [x] 12.1 在 `audit_platform_schemas.py` 的 `ProjectCreateResponse` 新增 `short_name: str | None`、`company_code: str | None`、`audit_year: int | None` 字段
- [x] 12.2 修改 `project_wizard.py` 的 `_to_project_response()` 填充 `short_name`、`company_code`、`audit_year`
