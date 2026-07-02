# Implementation Plan: F0 存货循环函证模块

## Overview

F0存货循环函证对齐D0架构：复用D0共享组件(7个componentType直接映射) + 新建F0-5/F0-6替代程序组件(2个)。overrides映射已完成，仅需注册新componentType+创建2个Vue组件。

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
  - [ ] 3.1 创建组件（参照GtConfirmationAlternativeD05模式）
    - 多公司Master-Detail + 抽样配置区 + 余额汇总 + 4区块检查宽表
    - 4区块：①预付账款期后收货检查②期末余额支持性证据③本期付款检查④本期采购证据
    - 支持从confirmation-hub带入未回函公司 + 增删行 + 动态宽表编辑
    - ~350行
    - _Requirements: 2_

- [ ] 4. 创建GtConfirmationAlternativeF06.vue
  - [ ] 4.1 创建组件（参照GtConfirmationAlternativeD06模式）
    - 多公司Master-Detail + 抽样配置区 + 余额汇总 + 4区块检查宽表
    - 4区块：①应付账款期后付款检查②期末余额支持性证据③本期采购检查④本期入库证据
    - 支持从confirmation-hub带入未回函公司 + 增删行 + 动态宽表编辑
    - ~350行
    - _Requirements: 3_

- [ ] 5. 验证
  - [ ] 5.1 运行注册契约测试确认无回归
    - vitest run htmlRendererRegistry.spec.ts
    - _Requirements: 4_
  - [ ]* 5.2 编写F05/F06单元测试
    - 测试4区块列配置正确性 + CRUD逻辑
    - _Requirements: 2, 3_

## Notes

- F0-1~F0-4/F0-4b/F0-7/F0-8直接复用D0共享组件，无需任何新代码
- confirmation-hub已处理tab分发逻辑（ConfirmationTabs.vue按wp_code路由）
- F0-5/F0-6是唯一需要新建的组件（替代程序4区块按科目不同）
- D0-5模式：Master列表(按公司) + Detail(4区块el-table动态行) + 抽样配置顶部卡片
- 跨循环共享的组件已由D0 spec完成开发（283任务全绿），此处仅补2个F循环特有组件
