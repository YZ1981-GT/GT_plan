# Implementation Plan: C23/C24 会计分录测试专属组件

## Overview

对齐 D4 标准：2 个专属 componentType + sheetName v-if 分发 + useC24AnalyticsEngine 纯函数（借贷平衡/科目对比/跳号/异常筛选/本福特）+ C23 人员核对 + 导入导出 + GtIndexChip + checklist_responses 持久化（前缀 C23-/C24-）。PBT 用 fast-check + hypothesis。

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
    { "id": "wave7", "tasks": ["7.1", "7.2"] },
    { "id": "wave8", "tasks": ["8.1", "8.2", "8.3"] }
  ]
}
```

## Notes

- 铁律：任务标记不假绿；optional(*) 也要做完；改动后必 Playwright 实测。
- 专属组件不含内部 el-tabs，接 sheetName v-if 分发；公式/分析结果列只读。
- 大数据量分录分批计算避免卡顿。完成后归档并更新 `.kiro/specs/INDEX.md`。

## Tasks

- [x] 1. Phase0 双源核对
  - 运行 `analyze_c_category.py` + `dump_c_content.py`，确认 C23A/C23-1/C23-2 结构、C24-0~C24-5 各 sheet 列结构、本福特 sheet 公式、异常分录规则清单
  - 产出 sheetName 分发表 + 引擎输入/输出规格 + item_id 命名
  - _Requirements: 2.1, 3.1, 4.1, 5.1, 6.1_

- [x] 2. 后端注册
  - [x] 2.1 VALID_COMPONENT_TYPES + wp_code_overrides：C23/C24 → 对应类型
    - _Requirements: 1.2, 1.3_
  - [x] 2.2 RENDERER_DISPATCH 注册两类 + 导入导出三端点（分录明细）
    - _Requirements: 1.4, 7.3_
  - [x] 2.3 validate_overrides + 注册契约测试
    - _Requirements: 1.3_

- [x] 3. 分析引擎与数据 composable
  - [x] 3.1 useC24AnalyticsEngine：借贷平衡/科目余额对比/跳号/异常筛选/本福特（纯函数）
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 5.1, 5.2_
  - [x] 3.2 useC23ControlData（人员核对）+ useC24ImportExport（分录导入）
    - _Requirements: 2.4, 7.1, 7.2, 7.3_

- [x] 4. Vue 组件
  - [x] 4.1 GtC23JournalControl.vue：注册 + sheetName 分发 + C23-1 清单 + C23-2 样本 + 人员核对偏差 + 结论
    - _Requirements: 1.1, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5_
  - [x] 4.2 GtC24JournalDetail.vue：注册 + sheetName 分发 + C24-1~5 + 本福特图表 + C24-0 汇总 + 异常规则参数
    - _Requirements: 1.1, 1.5, 3.4, 4.3, 4.4, 5.3, 5.4, 6.1, 6.2, 6.3_
  - [x] 4.3 导入导出 dropdown + GtIndexChip + UI 铁律 + 只读透传
    - _Requirements: 7.1, 7.4, 8.2, 8.3, 8.4_

- [x] 5. PBT 前端
  - [x] 5.1 fast-check：P2 借贷平衡 / P3 跳号 / P4 本福特 / P5 异常筛选
    - _Requirements: 3.1, 3.3, 5.1, 5.2, 4.1, 4.4_
  - [x] 5.2 fast-check：P1 注册 / P6 人员核对 / P7 公式不可覆盖
    - _Requirements: 1.1, 1.2, 2.4, 2.5, 3.4_

- [x] 6. PBT 后端与持久化
  - [x] 6.1 hypothesis：P8 往返一致性（C23-/C24- item_id）
    - _Requirements: 8.1_
  - [x] 6.2 持久化即时/debounce 保存 + readonly 禁编辑测试
    - _Requirements: 8.3, 8.5_

- [x] 7. 集成与实测
  - [x] 7.1 集成：导入分录 → 完整性/跳号/异常/本福特 端到端 + C24-0 汇总
    - _Requirements: 3.1, 3.3, 5.1, 6.2_
  - [x] 7.2 Playwright：C24 导入分录 → 各测试项 → 本福特图表 → 只读；C23 人员核对偏差
    - _Requirements: 2.4, 5.3, 7.2, 8.3_

- [x] 8. 交互增强（点选/附件OCR/异常回写）
  - [x] 8.1 是否偏差/结论点选 + 异常规则可勾选清单 + 阈值 input-number + 引导区 + tooltip
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - [x] 8.2 C23-2 样本 📎 上传 OCR 识别人员/日期 merge + C24 异常核查证据上传 + 分录导入 + 持久化
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - [x] 8.3 异常确认错报 GtIndexChip 跳 A13/相关循环带摘要 + 结论回填 C24-0 + 扩大核查提示（P9/P10/P11 PBT）
    - _Requirements: 11.1, 11.2, 11.3, 11.4_
