# Implementation Plan: bad-debt-sheet-enhancement

## Overview

为 GtBadDebtSheet 组件增加四大功能：导出空模板、导出含数据表、Excel 导入（预览弹窗确认）、账龄段枚举字典弹窗。后端 Python/FastAPI，前端 Vue3/TypeScript/Element-Plus。分 5 个 Sprint 增量交付，每个 Sprint 以 checkpoint 收尾。

## Tasks

- [x] 1. Sprint 1 — 导出模板 + 导出数据（后端）
  - [x] 1.1 增强 BadDebtExportService 支持 template_only 参数
    - 在 `bad_debt_export_service.py` 的 `export_bytes` 方法签名中增加 `template_only: bool = False`
    - `template_only=True` 时 `_write_row` 跳过所有金额列写入（B~N 列留空）
    - 空树（无父行）时仅输出列标题行（无数据行）
    - _Requirements: 1.2, 1.4, 1.5_

  - [x] 1.2 新增 export-template 和 export-data 路由端点
    - 在 `bad_debt_rows.py` router 中新增 `GET .../export-template`（StreamingResponse，Content-Disposition 附件下载）
    - 新增 `GET .../export-data`（复用已有 export_bytes，template_only=False）
    - 静态路径声明在 `/{row_id}` 之前
    - _Requirements: 1.1, 2.1, 2.2, 2.3_

  - [ ]* 1.3 Property test: Template structure preserves tree hierarchy
    - **Property 1: Template structure preserves tree hierarchy**
    - **Validates: Requirements 1.2, 1.3, 1.4**
    - 使用 Hypothesis 生成随机树结构（0~5 parents × 0~8 children），调用 export_bytes(template_only=True)，验证 xlsx 行数/缩进/空金额

  - [ ]* 1.4 单元测试 BadDebtExportService template_only
    - 测试空树输出仅含标题
    - 测试有子行树输出父行加粗 + 子行两空格缩进 + 金额空
    - 测试 template_only=False 时金额正常写入
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 2.4_

- [x] 2. Checkpoint — Sprint 1 验收
  - Ensure all tests pass, ask the user if questions arise.
  - 验收门槛：`GET export-template` 返回合法 xlsx（14 列标题 + 树结构行 + 空金额）；`GET export-data` 返回含金额 xlsx

- [x] 3. Sprint 2 — Excel 导入服务（后端）
  - [x] 3.1 创建 BadDebtImportService（parse_and_match）
    - 新建 `backend/app/services/bad_debt_import_service.py`
    - 实现 `parse_and_match(file, wp_index_id)` → ImportParseResult
    - 校验 xlsx 格式（>=14 列，A 列非空）；跳过表头行（R1~R11）从 R12 开始
    - A 列去前导空格后与当前树 row_label 精确匹配
    - 解析 B~N 列金额（int/float/Decimal，空=None）
    - 定义 Pydantic 模型：ImportRowMatch、ImportParseResult
    - _Requirements: 3.1, 3.2, 3.3, 3.8_

  - [x] 3.2 实现 BadDebtImportService.commit_matched_rows
    - 仅处理 status="matched" 行
    - 对每行仅覆盖 amounts 中非 None 的金额列（空单元格不覆盖原值）
    - 返回实际更新行数
    - _Requirements: 3.6, 5.3_

  - [x] 3.3 新增 import-parse 和 import-commit 路由端点
    - `POST .../import-parse`（multipart，接收 UploadFile，≤10MB 限制）
    - `POST .../import-commit`（JSON body: list[ImportRowMatch]）
    - 422 错误返回结构化 error_code + detail
    - _Requirements: 3.1, 3.6, 3.8_

  - [ ]* 3.4 Property test: Row label matching correctness
    - **Property 2: Row label matching correctness**
    - **Validates: Requirements 3.2, 3.3**
    - 生成随机树 + 随机 Excel 行（部分精确匹配、部分不匹配），验证匹配结果正确性

  - [ ]* 3.5 Property test: Partial import preserves existing values
    - **Property 4: Partial import preserves existing values**
    - **Validates: Requirements 5.3, 3.6**
    - 生成随机已填树 + 部分空单元格导入数据，commit 后验证空单元格对应原值不变

  - [ ]* 3.6 单元测试 BadDebtImportService
    - 测试格式校验（列数不足 → 422，A 列空 → 422，金额解析错 → 422）
    - 测试精确匹配 + 未匹配行标记
    - 测试 commit 仅覆盖非空值
    - _Requirements: 3.2, 3.3, 3.6, 3.7, 3.8_

- [x] 4. Checkpoint — Sprint 2 验收
  - Ensure all tests pass, ask the user if questions arise.
  - 验收门槛：`POST import-parse` 返回匹配结果 JSON；`POST import-commit` 批量更新且空单元格不覆盖

- [x] 5. Sprint 3 — 账龄段服务 + 迁移（后端）
  - [x] 5.1 创建数据库迁移 V091__aging_segments.sql
    - 新建 `backend/migrations/V091__aging_segments.sql`
    - CREATE TABLE aging_segments (id UUID PK, wp_index_id UUID FK UNIQUE, preset VARCHAR(20), segments JSONB, created_at, updated_at)
    - 含索引 + COMMENT
    - 新建 `backend/migrations/R091__aging_segments.sql` 回滚文件（DROP TABLE IF EXISTS aging_segments）
    - _Requirements: 4.11_

  - [x] 5.2 创建 AgingSegment ORM 模型
    - 新建 `backend/app/models/aging_segment_model.py`
    - AgingSegment(Base, TimestampMixin)：id, wp_index_id(unique FK), preset, segments(JSONB)
    - _Requirements: 4.11_

  - [x] 5.3 创建 AgingSegmentService
    - 新建 `backend/app/services/aging_segment_service.py`
    - 实现 `get_config(wp_index_id)` → AgingSegmentConfig | None
    - 实现 `save_config(wp_index_id, config)` → upsert + 同步 CREDIT_RISK_AGING 子行（删旧创新）
    - 实现 `check_has_amounts(wp_index_id)` → bool
    - 含 PRESETS 字典（THREE_YEAR / FIVE_YEAR）
    - 段名校验：非空 + 不重复
    - _Requirements: 4.2, 4.3, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11_

  - [x] 5.4 新增 aging-segments 路由端点
    - `GET .../aging-segments` → AgingSegmentConfig
    - `PUT .../aging-segments` → 保存 + 同步子行
    - `GET .../aging-segments/has-amounts` → bool
    - _Requirements: 4.1, 4.7, 4.10_

  - [ ]* 5.5 Property test: Aging segment validation
    - **Property 5: Aging segment validation**
    - **Validates: Requirements 4.6**
    - 生成随机字符串列表，验证 validation 函数对空名/重复名拒绝、有效列表接受

  - [ ]* 5.6 Property test: Aging segment persistence round-trip and child sync
    - **Property 6: Aging segment persistence round-trip and child sync**
    - **Validates: Requirements 4.7, 4.8, 4.11**
    - 生成随机有效段列表，save → load 比对 + 查 CREDIT_RISK_AGING 子行 row_labels 顺序

  - [ ]* 5.7 单元测试 AgingSegmentService
    - 测试 get_config 不存在返回 None
    - 测试 save_config 创建 + 更新（upsert）
    - 测试子行同步（旧子行删除 + 新子行按序创建）
    - 测试 check_has_amounts（有金额 True / 空 False）
    - 测试段名校验拒绝（空/重复）
    - _Requirements: 4.6, 4.7, 4.8, 4.9, 4.10, 4.11_

- [x] 6. Checkpoint — Sprint 3 验收
  - Ensure all tests pass, ask the user if questions arise.
  - 验收门槛：V091 迁移成功；aging-segments CRUD 正常；子行同步与段列表一致；段名校验拒绝空/重复

- [x] 7. Sprint 4 — 前端组件 + 集成
  - [x] 7.1 创建 ImportPreviewDialog.vue 组件
    - el-dialog 弹窗 + el-table 展示匹配结果
    - 行状态标记：matched 绿色 / unmatched 红色高亮
    - 底部统计（N 行匹配 / M 行未匹配）
    - 确认/取消按钮，emit confirm/cancel/update:visible
    - _Requirements: 3.4, 3.5, 3.7_

  - [x] 7.2 创建 AgingDictionaryDialog.vue 组件
    - 左侧预设方案选择（三年段/五年段/自定义）
    - 右侧段列表可编辑（拖拽排序/新增/删除/改名）
    - 实时校验：段名非空且不重复（红框 + 提示）
    - 确认时若有已填金额，先弹二次确认警告
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.10_

  - [x] 7.3 集成到 GtBadDebtSheet.vue 工具栏
    - 工具栏新增 4 个按钮：导出模板 / 导出数据 / 导入 / 账龄段设置
    - 导出模板：调用 GET export-template，触发浏览器下载
    - 导出数据：调用 GET export-data，触发浏览器下载
    - 导入：el-upload 选文件 → POST import-parse → 弹 ImportPreviewDialog → 确认 → POST import-commit → 刷新树
    - 账龄段设置：打开 AgingDictionaryDialog → saved 事件刷新树
    - _Requirements: 1.1, 2.1, 3.1, 3.9, 4.1_

  - [ ]* 7.4 前端单元测试 ImportPreviewDialog
    - vitest + @vue/test-utils 挂载
    - 测试 matched/unmatched 行渲染样式
    - 测试 confirm/cancel emit
    - _Requirements: 3.4, 3.5_

  - [ ]* 7.5 前端单元测试 AgingDictionaryDialog
    - 测试预设选择切换
    - 测试自定义编辑（新增/删除/改名）
    - 测试校验拒绝空名/重复名
    - _Requirements: 4.2, 4.3, 4.5, 4.6_

- [x] 8. Checkpoint — Sprint 4 验收
  - Ensure all tests pass, ask the user if questions arise.
  - 验收门槛：工具栏 4 按钮可点击；导入预览弹窗正确展示匹配状态；账龄段弹窗预设/自定义/校验功能正常

- [x] 9. Sprint 5 — Round-trip 一致性 + 端到端验证
  - [ ]* 9.1 Property test: Export-Import round-trip
    - **Property 3: Export-Import round-trip**
    - **Validates: Requirements 5.1, 5.2**
    - 生成随机已填树（Decimal(18,2) 金额），export → parse → commit → 对比原始值（精度内相等）

  - [x] 9.2 后端集成测试：新端点覆盖
    - 测试 export-template 200 返回 xlsx content-type
    - 测试 export-data 200 返回 xlsx content-type
    - 测试 import-parse 422（非法格式）+ 200（合法文件）
    - 测试 import-commit 200（写入成功）
    - 测试 aging-segments GET/PUT/has-amounts 200/422
    - _Requirements: 1.1, 2.1, 3.1, 3.8, 4.7_

  - [x] 9.3 前端 API 层封装 + 错误处理
    - 在 API 层新增 badDebtApi（exportTemplate/exportData/importParse/importCommit/getAgingSegments/saveAgingSegments/checkHasAmounts）
    - 422 → ElMessage.error(detail)；409 → 提示刷新；网络错误 → 通用提示
    - _Requirements: 3.8, 3.9_

- [x] 10. Final Checkpoint — 全部验收
  - Ensure all tests pass, ask the user if questions arise.
  - 验收门槛：
    - 导出模板 xlsx 结构正确（14 列 + 树行 + 空金额）
    - 导出数据 xlsx 含已填金额
    - 导入解析匹配正确，preview 弹窗展示，确认写入成功
    - 账龄段弹窗预设/自定义/校验/保存/子行同步
    - Round-trip：export → import → commit 金额一致
    - 6 个 Property-Based Tests 全部 PASSED

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 后端 Python（FastAPI + SQLAlchemy + openpyxl），前端 TypeScript（Vue3 + Element-Plus）
- PBT 使用 Hypothesis 库，每个 property test ≥100 iterations
- 迁移编号 V091（紧跟 V090__custom_account_packages）
- 所有静态路径端点声明在 `/{row_id}` 之前避免路径冲突
