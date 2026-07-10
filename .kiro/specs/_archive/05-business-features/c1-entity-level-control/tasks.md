# Implementation Plan: C1 企业层面控制测试专属组件

## Overview

对齐 D4 标准：componentType 注册 + sheetName v-if 分发 + 五要素分组程序中控台（复用 GtAProgramConsole）+ 财报内控过程记录子表（样本公式）+ GtIndexChip + checklist_responses 持久化（前缀 C1-）。零新表零新端点。PBT 用 fast-check + hypothesis。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3"] },
    { "id": "wave3", "tasks": ["3.1", "3.2"] },
    { "id": "wave4", "tasks": ["4.1", "4.2", "4.3"] },
    { "id": "wave5", "tasks": ["5.1", "5.2"] },
    { "id": "wave6", "tasks": ["6.1", "6.2"] },
    { "id": "wave7", "tasks": ["7.1", "7.2", "7.3"] }
  ]
}
```

## Notes

- 铁律：任务标记不假绿；optional(*) 也要做完；改动后必 Playwright 实测。
- 专属组件不含内部 el-tabs，接 sheetName v-if 分发。
- 完成后归档并更新 `.kiro/specs/INDEX.md`。

## Tasks

- [x] 1. Phase0 双源核对
  - 运行 `analyze_c_category.py` + `dump_c_content.py`，确认 C1 主程序表五要素切分行、C1-1~3 示例、C1-4-x 过程记录字段与 C1-4-4 样本公式
  - 产出 sheetName 分发表 + item_id 命名规范
  - _Requirements: 2.1, 4.2, 4.3_

- [x] 2. 后端注册与渲染
  - [x] 2.1 VALID_COMPONENT_TYPES + wp_code_overrides：C1 → `c1-entity-level-control`
    - _Requirements: 1.2, 1.3_
  - [x] 2.2 RENDERER_DISPATCH 注册 C1 render 策略；render schema yaml + guidance
    - _Requirements: 1.4_
  - [x] 2.3 validate_overrides + 注册契约测试
    - _Requirements: 1.3_

- [x] 3. composable
  - [x] 3.1 useC1ControlData：GET/PUT checklist-responses（C1- 前缀）+ debounce/即时保存
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x] 3.2 useC1SampleEngine：C1-4-4 样本借贷勾稽纯函数
    - _Requirements: 4.4_

- [x] 4. GtC1EntityControl.vue
  - [x] 4.1 htmlRendererRegistry 注册 + sheetName v-if 分发；五要素分组程序中控台（GtAProgramConsole）
    - _Requirements: 1.1, 1.5, 2.1, 2.2, 2.3, 2.4_
  - [x] 4.2 适用性裁剪（是否适用 + 理由）+ 过程记录子表 + 样本明细 + 示例只读
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3_
  - [x] 4.3 GtIndexChip 引用 + UI 铁律（13px/公式虚线/el-card/AI 按钮/元）+ 只读透传
    - _Requirements: 6.1, 6.2, 6.3, 8.1, 8.2, 8.3, 8.4_

- [x] 5. PBT
  - [x] 5.1 前端 fast-check：P1 注册 / P2 五要素分组 / P3 进度排除 / P4 样本勾稽 / P6 readonly
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 3.2, 3.3, 4.4, 8.1_
  - [x] 5.2 后端 hypothesis：P5 往返一致性
    - _Requirements: 7.1, 7.4_

- [x] 6. 集成与实测
  - [x] 6.1 集成：挂载组件 mock checklist-responses，验证分组/适用性/样本重算/sheet 分发
    - _Requirements: 2.1, 3.2, 4.4_
  - [x] 6.2 Playwright：打开 C1 → 五要素切换 → 适用性裁剪 → 过程记录样本填写 → 只读模式
    - _Requirements: 2.3, 3.1, 4.3, 8.1_

- [x] 7. 交互增强（点选/附件OCR/回写）
  - [x] 7.1 判断/枚举字段点选控件（是否适用/测试方法/结论/频率）+ 顶部引导区 + 方法论上下文 + tooltip
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_
  - [x] 7.2 C1-4-x 过程记录与样本行 📎 附件上传 + OCR 识别 + 确认弹窗 merge + 附件持久化
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - [x] 7.3 整体结论点选+自动建议 + EventBus 发布 B50 + 缺陷 GtIndexChip 跳 A14 带摘要（P7/P8/P9 PBT）
    - _Requirements: 11.1, 11.2, 11.3, 11.4_
