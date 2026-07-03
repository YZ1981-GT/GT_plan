# Implementation Plan: F0 存货循环函证模块

## Overview

F0存货循环函证对齐D0架构：复用D0共享组件(7个componentType直接映射) + 新建F0-5/F0-6替代程序组件(2个)。overrides映射已完成，仅需注册新componentType+创建2个Vue组件。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["2.1", "2.2", "2.3", "2.4"] },
    { "id": "wave2", "tasks": ["3.1", "3.2", "4.1", "4.2"] },
    { "id": "wave3", "tasks": ["5.1"] },
    { "id": "wave4", "tasks": ["6.1", "6.2"] },
    { "id": "wave5", "tasks": ["7.1"] }
  ]
}
```

## Tasks

- [x] 1. overrides映射对齐D0（已完成2026-07-01）
  - [x] 1.1 wp_code_overrides.json F0系列映射完成
    - F0→confirmation-hub, F0A→a-program-console, F0-1→confirmation-summary, F0-2→confirmation-entity-verify, F0-3→confirmation-followup, F0-4→confirmation-diff-reconcile, F0-4b→confirmation-diff-checklist, F0-5→confirmation-alternative-f05, F0-6→confirmation-alternative-f06, F0-7→confirmation-reliability, F0-8→confirmation-fraud-risk
    - _Requirements: 1_
  - [x] 1.2 F0.yaml render schema更新完成
    - 11个sheet的component_type和class_code准确反映真实模板
    - _Requirements: 1_

- [ ] 2. 注册新componentType
  - [ ] 2.1 VALID_COMPONENT_TYPES注册confirmation-alternative-f05/f06
    - 在wp_classification_service.py的VALID_COMPONENT_TYPES中添加2个新类型
    - _Requirements: 4_
  - [ ] 2.2 htmlRendererRegistry注册f05/f06
    - 添加type union + registry entry + defineAsyncComponent import
    - _Requirements: 4_
  - [ ] 2.3 后端RENDERER_DISPATCH注册f05/f06
    - 复用confirmation通用renderer（返回checklist_responses snapshot）
    - _Requirements: 4_
  - [ ] 2.4 更新htmlRendererRegistry.spec.ts
    - expected componentType列表添加confirmation-alternative-f05/f06
    - _Requirements: 4_

- [ ] 3. 创建GtConfirmationAlternativeF05.vue
  - [ ] 3.1 创建composable `useAlternativeF05Data.ts`
    - 定义4区块列配置（按xlsx实际列头：区块①15列/区块②13列/区块③13列/区块④15列）
    - 实现Master-Detail数据管理（按公司分组，每公司4区块独立行数据）
    - 实现余额汇总区（函证项目/年初余额/借方发生额/贷方发生额/期末余额 + 本期采购金额/付款比例/入库比例）
    - 实现loadAll/persistAll（JSON→checklist_responses.remark）
    - 实现addRow/removeRow/updateCell（每区块独立CRUD）
    - 实现合计行计算（SUM金额列）
    - _Requirements: 2, 5_

  - [ ] 3.2 创建组件 `alternativeF05/GtConfirmationAlternativeF05.vue`
    - 多公司Master-Detail（el-tabs按公司+ElMessageBox.prompt新增公司）
    - 抽样参数区（6字段textarea表单）
    - 余额汇总区（2行表格：函证项目+本期采购）
    - 4区块检查宽表（每区块el-table，记账凭证5列为固定分组，检查证据为可横滚分组）
    - 每区块合计行 + 索引号列(GtIndexChip) + 是否异常列(下拉)
    - 行级OCR上传按钮（📎列）
    - 底部审计说明+审计结论textarea（AI辅助按钮）
    - ~400行
    - _Requirements: 2_

- [ ] 4. 创建GtConfirmationAlternativeF06.vue
  - [ ] 4.1 创建composable `useAlternativeF06Data.ts`
    - 定义4区块列配置（按xlsx实际列头：区块①15列/区块②13列/区块③15列/区块④13列）
    - 实现Master-Detail数据管理（按公司分组，每公司4区块独立行数据）
    - 实现余额汇总区（函证项目应付票据+应付账款/年初/借方/贷方/期末 + 本期采购/入库比例/付款比例）
    - 实现loadAll/persistAll（JSON→checklist_responses.remark）
    - 实现addRow/removeRow/updateCell
    - 实现合计行计算
    - _Requirements: 3, 5_

  - [ ] 4.2 创建组件 `alternativeF06/GtConfirmationAlternativeF06.vue`
    - 多公司Master-Detail + 抽样参数区 + 余额汇总区 + 4区块宽表
    - 与F05结构一致，仅4区块列配置和标题不同
    - ~400行
    - _Requirements: 3_

- [ ] 5. 导入导出端点
  - [ ] 5.1 创建后端 `_f0_import_export.py`
    - 实现 export-template（按sheet=F0-5/F0-6，4区块→4个sheet含列头+说明）
    - 实现 export-data（当前数据导出）
    - 实现 import-data（校验列头+解析行+回写checklist_responses）
    - 路径：`/api/workpapers/{wp_id}/f0/export-template?sheet=F0-5`
    - _Requirements: 5_

- [ ] 6. 验证
  - [ ] 6.1 运行注册契约测试确认无回归
    - vitest run htmlRendererRegistry.spec.ts
    - _Requirements: 4_
  - [ ]* 6.2 编写F05/F06单元测试
    - 测试4区块列配置正确性 + CRUD逻辑 + 合计行计算
    - 测试导入导出模板列头匹配
    - _Requirements: 2, 3, 5_

## Notes

- F0-1~F0-4/F0-4b/F0-7/F0-8直接复用D0共享组件，无需任何新代码
- confirmation-hub已处理tab分发逻辑（ConfirmationTabs.vue按wp_code路由）
- F0-5/F0-6是唯一需要新建的组件（替代程序4区块按科目不同）
- D0-5模式：Master列表(按公司) + Detail(4区块el-table动态行) + 抽样配置顶部卡片
- 跨循环共享的组件已由D0 spec完成开发（283任务全绿），此处仅补2个F循环特有组件


- [ ] 7. 版本链集成
  - [ ] 7.1 集成useVersionTrail到F0-5/F0-6主入口
    - 在GtConfirmationAlternativeF05/F06中import并调用useVersionTrail(wpId)
    - 在debouncedSave成功回调中调用versionTrail.autoSnapshot()
    - 工具栏右侧添加"版本历史"按钮（el-button icon="Clock"）
    - 点击按钮打开GtWpVersionTrail drawer（direction="rtl" size="400px"）
    - GtWpVersionTrail内嵌VersionDiffPanel支持两版本差异对比
    - 提供手动创建命名快照入口（ElMessageBox.prompt输入备注）
    - _Requirements: 6_
