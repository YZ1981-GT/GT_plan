# Implementation Plan: C25/C26 专项控制测试专属组件

## Overview

对齐 D4 标准：2 个专属 componentType + 命名区域下拉 + AI 辅助文本 + 动态行矩阵（C26）+ GtIndexChip + checklist_responses 持久化（前缀 C25-/C26-）。零新表零新端点。PBT 用 fast-check + hypothesis。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3"] },
    { "id": "wave3", "tasks": ["3.1"] },
    { "id": "wave4", "tasks": ["4.1", "4.2", "4.3"] },
    { "id": "wave5", "tasks": ["5.1", "5.2"] },
    { "id": "wave6", "tasks": ["6.1", "6.2"] },
    { "id": "wave7", "tasks": ["7.1", "7.2"] }
  ]
}
```

## Notes

- 铁律：任务标记不假绿；optional(*) 也要做完；改动后必 Playwright 实测。
- C26 动态行需命名的先 ElMessageBox.prompt 输入控制名再创建。
- 叙述式文本区用 autosize textarea。完成后归档并更新 `.kiro/specs/INDEX.md`。

## Tasks

- [x] 1. Phase0 双源核对
  - 运行 `analyze_c_category.py` + `dump_c_content.py`，确认 C25 10 步程序与命名下拉、C26 矩阵列结构与四要素、填写说明长文本
  - 产出 item_id 命名 + 下拉选项清单
  - _Requirements: 2.1, 2.2, 3.1, 3.4, 4.1_
  - _产出文件: `.kiro/specs/c25-c26-internal-audit-info-control/phase0-analysis.md`_

- [x] 2. 后端注册
  - [x] 2.1 VALID_COMPONENT_TYPES + wp_code_overrides：C25/C26 → 对应类型
    - _Requirements: 1.2, 1.3_
  - [x] 2.2 RENDERER_DISPATCH 注册两类 + render schema yaml + guidance
    - _Requirements: 1.4_
  - [x] 2.3 validate_overrides + 注册契约测试
    - _Requirements: 1.3_

- [x] 3. composable
  - [x] 3.1 useC25C26Data：GET/PUT checklist-responses（C25-/C26- 前缀）+ debounce/即时保存 + 动态行增删
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 3.3_

- [x] 4. Vue 组件
  - [x] 4.1 GtC25InternalAudit.vue：注册 + 10 步评估程序 + 命名下拉 + 利用结论 + AI 辅助
    - _Requirements: 1.1, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5_
  - [x] 4.2 GtC26InfoControl.vue：注册 + 信息处理控制矩阵动态行 + 四要素标记 + 循环分组筛选 + AI 辅助
    - _Requirements: 1.1, 1.5, 3.1, 3.2, 3.3, 3.4, 3.5_
  - [x] 4.3 方法论上下文区块 + GtIndexChip + UI 铁律（13px/el-card/details/autosize）+ 只读透传
    - _Requirements: 4.1, 4.2, 5.1, 5.2, 5.3, 7.1, 7.2, 7.3, 7.4_

- [x] 5. PBT
  - [x] 5.1 fast-check：P1 注册 / P2 C25 步骤 / P3 C26 增删 / P4 四要素 / P6 readonly
    - _Requirements: 1.1, 1.2, 2.1, 2.3, 3.3, 3.4, 7.1_
  - [x] 5.2 hypothesis：P5 往返一致性
    - _Requirements: 6.1, 6.4_

- [x] 6. 集成与实测
  - [x] 6.1 集成：挂载组件 mock checklist-responses，验证步骤/矩阵/四要素/增删/AI
    - _Requirements: 2.1, 3.3, 3.4_
  - [x] 6.2 Playwright：C25 评估录入 → 结论；C26 矩阵增删 → 四要素 → 只读模式
    - _Requirements: 2.4, 3.3, 7.1_

- [x] 7. 交互增强（点选/附件OCR/联动）
  - [x] 7.1 是否适用/结论/四要素/控制类别点选 + 循环标签点选切换 + 引导区 + tooltip + 方法论上下文
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  - [x] 7.2 C26 证据/C25 内审报告 📎 附件上传 + OCR merge + 持久化 + GtIndexChip 跳 A14/C21-1/计划底稿带摘要（P7/P8 PBT）
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 10.1, 10.2, 10.3_
