# Implementation Plan: H0 固定资产循环函证模块

## Overview

H0 固定资产循环函证对齐 D0 架构：复用 D0 共享组件（6 个 componentType 直接映射 + a-program-console + confirmation-hub）+ 新建 H0-5 替代程序组件（1 个）。源模板 1 个 xlsx / 9 sheet。

**参照文档**：[`h0_d0_alignment.md`](./h0_d0_alignment.md)（D0↔H0 完整对照 + 当前缺口）

## 实现状态（2026-07-05）

| 模块 | 状态 | 说明 |
|------|------|------|
| H0→confirmation-hub | ✅ | overrides 9 条已齐 |
| H0-1~H0-7 共享组件映射 | ✅ | overrides 已对齐 D0 |
| account_package H0 | ✅ | H0_fixed_asset_confirmation |
| confirmation-alternative-h05 | ✅ | 注册 + GtConfirmationAlternativeH05 + 后端三件套 |
| Phase 0 文档 | ✅ | h0_structure_summary.json + h0_conflict_resolution.md |
| E2E h-cycle-h0-confirmation-hub | ✅ | findWorkpaper + h0-alternative-h05 testid |

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave0", "tasks": ["0.1", "0.2"] },
    { "id": "wave1", "tasks": ["1.1", "1.2"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5"] },
    { "id": "wave3", "tasks": ["3.1"] },
    { "id": "wave4", "tasks": ["4.1"] },
    { "id": "wave5", "tasks": ["5.1", "5.2"] },
    { "id": "wave6", "tasks": ["6.1", "6.2"] },
    { "id": "wave7", "tasks": ["7.1"] },
    { "id": "wave8", "tasks": ["8.1", "8.2"] }
  ]
}
```

## Notes

- H0 是函证循环，架构与 **F0/G0/L0 完全一致**：复用 D0 共享 + 新建循环特有替代程序
- H0 **仅 1 个**替代程序（对标 D0-5，无 D0-6 姊妹表）
- H0 **无** D0-4b 差异检查表示例 sheet
- H0-5 壳层**复用** D0-5 的 Dashboard/Master/CheckBlock（同 F0-5 已验证模式）
- D0 共享 9 类 confirmation-* 已由 D0 spec 完成；此处仅补 H0 overrides + H05 组件
- H0 无截止自动提取（函证类不适用）

## Tasks

### Phase 0: 双源输入（参照 D0 / F0 Phase 0）

- [ ] 0.1 openpyxl 实读 `H0 固定资产循环函证.xlsx` 全 9 sheet
  - 确认 H0-5 每区块实际列头 / 行数 / 公式
  - 产出：`h0_structure_summary.json`
  - _Requirements: 2.5_

- [ ] 0.2 D0 架构交叉验证
  - 对照 `h0_d0_alignment.md` 与 D0 overrides / F0-5 实现
  - 产出：`h0_conflict_resolution.md`（列配置与 xlsx 冲突决议）
  - _Requirements: 1, 2_

### Phase 1: 组件注册与基础配置（对标 F0 task 1）

- [x] 1.1 修正 overrides + account_package（对标 D0）
  - [x] `wp_code_overrides.json` 9 条 H0 映射（H0A/H0-1~H0-7）
  - [x] `account_package_registry.json` → `H0_fixed_asset_confirmation`（sheet_type 同 G0）
  - [ ] 注册 `confirmation-alternative-h05`（VALID_COMPONENT_TYPES + registry + DISPATCH）
  - [ ] 人工审核 `H0.yaml` component_type
  - _Requirements: 1.1~1.4, 4_

- [ ]* 1.2 编写注册契约测试
  - `test_h0_registration_contract.py`：9 条 overrides + h05 dispatch
  - 更新 `htmlRendererRegistry.spec.ts`
  - _Requirements: 4_

### Phase 2: 公式引擎 useH0FormulaEngine.ts

- [ ] 2.1 创建 `alternativeH05/composables/useH0FormulaEngine.ts`
  - calcBlockTotal / calcCheckRatio / calcRowVariance / isAbnormal
  - _Requirements: 5_

- [ ]* 2.2 Property P1 PBT：区块合计
  - **Feature: confirmation-alternative-h05, Property P1**

- [ ]* 2.3 Property P2 PBT：检查比例（除零→0）

- [ ]* 2.4 Property P3 PBT：行差异与零差异恒等

- [ ]* 2.5 Property P4 PBT：异常判定

### Phase 3: Composable 数据管理（参照 useAlternativeF05Data）

- [ ] 3.1 创建 `useAlternativeH05Data.ts`
  - Master-Detail（公司→4 区块检查表）
  - `blockColumnConfigsH05.ts` 四区块列定义
  - loadAll / persistAll（`_format: alternative-h05-v1`）
  - importFromSummary（H0-1 未回函，对标 D0-1→D0-5）
  - _Requirements: 2, 3_

### Phase 4: Vue 组件（参照 GtConfirmationAlternativeF05）

- [ ] 4.1 创建 `alternativeH05/GtConfirmationAlternativeH05.vue`
  - 复用 AlternativeD05Dashboard / Master / CheckBlock
  - 余额汇总 + 抽样参数 + 4 区块宽表 + OCR + 导入导出下拉
  - ref_index → H1 / L1 / L3
  - useVersionTrail + 复核 provide
  - _Requirements: 2, 6_

### Phase 5: 后端

- [ ] 5.1 创建 `_h0_confirmation.py` + `_h0_confirmation_import_export.py` + `_h0_confirmation_ai.py`
  - 注册 router（参照 `_f0_import_export` / `_g0_confirmation`）
  - _Requirements: 3, 4_

- [ ] 5.2 创建 `useH0ImportExport.ts`
  - _Requirements: 3_

### Phase 6: 跨模块联动

- [ ] 6.1 confirmation-hub 验证 H0 全 Tab 路由
  - ConfirmationTabs 按 wp_code 分发 H0-5 → h05
  - _Requirements: 7_

- [ ] 6.2 EventBus 联动
  - H0-1→H0-5 importFromSummary
  - confirmation:updated 刷新
  - _Requirements: 2.8, 5_

### Phase 7: 版本链

- [ ] 7.1 GtConfirmationAlternativeH05 集成 useVersionTrail
  - _Requirements: 6_

### Phase 8: 测试与 E2E

- [ ]* 8.1 集成测试 `h0Confirmation.integration.spec.ts`
  - overrides 映射 / 四区块 CRUD / 导入导出 round-trip

- [ ]* 8.2 E2E 扩展 `h-cycle-h0-confirmation-hub.spec.ts`
  - 对齐 `g-cycle-g0-confirmation` 模式：H0-1 summary testid、H0-5 四区块可见
  - 使用 `ensure-test-project` findWorkpaper + loginAs
  - _Requirements: 全部_

## D0 参照速查

| 实现任务 | 直接参照代码路径 |
|----------|-----------------|
| overrides 9 条 | `wp_code_overrides.json` D0-1~D0-8 + F0 系列 |
| H05 薄壳组件 | `alternativeF05/GtConfirmationAlternativeF05.vue` |
| H05 数据层 | `alternativeF05/composables/useAlternativeF05Data.ts` |
| 列配置模式 | `alternativeD05/blockColumnConfigs.ts` + `alternativeF05/blockColumnConfigsF05.ts` |
| 导入导出后端 | `backend/.../ _f0_import_export.py` 或 `_g0_confirmation_import_export.py` |
| hub Tab 路由 | `confirmation/ConfirmationTabs.vue`（F0/G0 已接入） |
