# D4-12 合同检查表升级 — 任务清单

## Phase 1: Composable + 数据结构

- [x] 1.1 创建 `useD4ContractInspection.ts` composable
  - [x] 1.1.1 定义 ContractInspectionItem 类型（21字段 + 附件元数据）
  - [x] 1.1.2 实现 loadContracts / addContract / removeContract / updateField
  - [x] 1.1.3 实现 coverageRate computed（合同金额总和 / D4-1审定收入）
  - [x] 1.1.4 实现 debounce 2s 持久化（D4-12-contracts-v2 + D4-12-note + D4-12-conclusion）
  - [x] 1.1.5 实现 auditNote / auditConclusion 读写
  - [x] 1.1.6 实现 summaryConclusion computed（自动生成汇总结论文本）

## Phase 2: 合同卡片子组件

- [x] 2.1 创建 `D4ContractCard.vue` 子组件
  - [x] 2.1.1 分5组展示20+1字段（基础信息5/交付条款4/合同条款4/签署确认2/收入确认5+结论1）
  - [x] 2.1.2 Y/N/NA 字段用 el-radio-group（签字/盖章）
  - [x] 2.1.3 金额字段 el-input-number + 格式化
  - [x] 2.1.4 长文本字段 textarea（特殊约定/特定交易说明/结论）
  - [x] 2.1.5 顶部附件上传区（el-upload拖拽 + 已上传文件名展示 + OCR状态badge）

## Phase 3: 主组件重写

- [x] 3.1 重写 `D4TabContract.vue`
  - [x] 3.1.1 顶部工具条（el-segmented双模式 + 导入导出dropdown + GtIndexChip×3）
  - [x] 3.1.2 概览横幅（覆盖率进度环 + 合同数量tag + "添加合同"按钮走ElMessageBox.prompt）
  - [x] 3.1.3 合同卡片区（el-tabs card模式，每tab一份合同，动态增删）
  - [x] 3.1.4 编制提示折叠区（4段details，蓝左边线+浅蓝背景）
  - [x] 3.1.5 审计意见区（el-card包裹：说明textarea + 结论textarea + AI辅助按钮右对齐 + 复核按钮）
  - [x] 3.1.6 OnlyOffice 模式（GtOnlyOfficeSheet fallback）

## Phase 4: 后端OCR端点

- [x] 4.1 创建 `_d4_contract_ocr.py` 路由
  - [x] 4.1.1 POST `/api/workpapers/{wp_id}/d4/contract-ocr` 端点（multipart/form-data）
  - [x] 4.1.2 文件存储到附件系统（process_record_service.create_attachment）
  - [x] 4.1.3 调用 UnifiedOCRService 识别文本
  - [x] 4.1.4 OCR文本 + 20字段schema → vLLM 结构化提取（chat_completion）
  - [x] 4.1.5 返回 attachment_id + ocr_text + extracted_fields + confidence
  - [x] 4.1.6 注册路由到 router_registry（"AI与辅助"组）

## Phase 5: 前端OCR集成

- [x] 5.1 D4ContractCard 内上传触发OCR
  - [x] 5.1.1 上传文件调后端 `/d4/contract-ocr` 端点
  - [x] 5.1.2 processing状态展示（el-skeleton + 进度提示）
  - [x] 5.1.3 返回后弹 OcrFillConfirmDialog（左列提取结果 / 右列当前值 / diff高亮）
  - [x] 5.1.4 确认后 merge 填充（空字段直接填 / 非空字段提示覆盖）
  - [x] 5.1.5 附件关联到底稿（attachmentId / attachmentName 存入合同数据）

## Phase 6: AI辅助

- [x] 6.1 审计结论AI生成
  - [x] 6.1.1 调 `/d4/ai-generate` section=`contract-conclusion`
  - [x] 6.1.2 上下文：所有合同的结论汇总 + 覆盖率 + 异常合同列表
  - [x] 6.1.3 弹确认预览 → 填入结论textarea

## Phase 7: 注册 + 集成验证

- [x] 7.1 确保 D4-12 在 account_package_registry / wp_code_overrides 正确映射
- [x] 7.2 GtD4OperatingRevenue 中 sheetName 匹配 D4-12 → D4TabContract
- [x] 7.3 useD4Inspection 中旧 contractRows 逻辑标记 deprecated（不删除，渐进迁移）

## Phase 8: 测试

- [x] 8.1 PBT fast-check: useD4ContractInspection 纯函数（覆盖率/汇总结论/字段校验）
- [x] 8.2 vitest 单元测试: D4ContractCard props渲染 + OCR填充merge逻辑
- [x] 8.3 后端 pytest: _d4_contract_ocr 端点（mock OCR + mock LLM）
