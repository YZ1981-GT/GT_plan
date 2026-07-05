# Implementation Plan: C2~C15 控制测试组件翻新

## Overview

翻新 `c-control-test` 组件内部结构匹配真实模板：目录导航 + 控制测试汇总表(15列下拉) + 逐控制测试子页(抽样) + Cx-2 偏差评价决策树(6步IF) + 样本规模自动建议 + 缺陷联动A14 + B23/B50 EventBus。沿用 componentType 与 C{n}- 前缀（兼容历史）。取代已归档 c-control-test-component。PBT 用 fast-check + hypothesis。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1"] },
    { "id": "wave2", "tasks": ["2.1", "2.2"] },
    { "id": "wave3", "tasks": ["3.1", "3.2", "3.3"] },
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
- 沿用 componentType `c-control-test`，组件内部翻新；必须兼容历史 C{n}- 数据。
- 新增控制点需先 ElMessageBox.prompt 命名。完成后归档并更新 INDEX.md（标注取代 c-control-test-component）。

## Tasks

- [x] 1. Phase0 双源核对
  - 运行 `analyze_c_category.py` + `dump_c_content.py`，确认 Cx 汇总表 15 列、Cx-1-X 子页结构、Cx-2 六步 IF 公式链、命名下拉选项、样本规模区间表
  - 核对历史 C{n}- checklist_responses 数据结构确保兼容
  - _Requirements: 2.1, 3.1, 4.1, 5.1, 1.5_

- [x] 2. 后端与注册保持
  - [x] 2.1 保持 wp_code_overrides C2~C15 → `c-control-test`；后端 conclusion 白名单新增偏差性质值
    - _Requirements: 1.1, 1.2, 8.1_
  - [x] 2.2 白名单契约测试 + 历史数据兼容测试
    - _Requirements: 1.5_

- [x] 3. 引擎与数据 composable
  - [x] 3.1 useSampleSizeEngine：样本规模区间表纯函数
    - _Requirements: 3.1, 3.2_
  - [x] 3.2 useDeviationDecisionTree：Cx-2 六步 IF 决策树纯函数
    - _Requirements: 5.1, 5.2, 5.3_
  - [x] 3.3 useCControlTestData：GET/PUT checklist-responses（C{n}- 兼容）+ 即时/debounce 保存 + 动态行
    - _Requirements: 8.1, 8.2, 8.3, 2.3_

- [x] 4. GtCControlTest.vue 翻新
  - [x] 4.1 sheetName v-if 分发（目录/汇总/子页/偏差）+ 目录导航 + 循环上下文 + 项目信息
    - _Requirements: 1.3, 1.4, 6.1, 6.2, 6.3, 6.4_
  - [x] 4.2 控制测试汇总表 15 列 + 命名下拉 + 动态增删 + 样本规模建议 + 索引跳子页
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.3, 3.4_
  - [x] 4.3 Cx-1-X 子页抽样测试 + 偏差回填汇总 + Cx-2 六步决策树 + 评价结论
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.4, 5.5_

- [x] 5. 联动与只读/UI
  - [x] 5.1 缺陷 GtIndexChip → A14；B23/B50 跳转；EventBus control:test-concluded → B50
    - _Requirements: 5.3, 7.1, 7.2, 7.3_
  - [x] 5.2 UI 铁律（13px/el-card/details）+ 只读透传 + 方法论上下文（样本规模区间）
    - _Requirements: 3.4, 8.4, 8.5, 8.6_

- [x] 6. PBT
  - [x] 6.1 fast-check：P2 样本规模 / P3 决策树全路径 / P4 A14 联动 / P5 偏差回填 / P6 EventBus
    - _Requirements: 3.1, 3.2, 5.1, 5.2, 5.3, 4.3, 7.2, 7.3_
  - [x] 6.2 hypothesis：P1 数据兼容 / P7 往返 + readonly
    - _Requirements: 1.5, 8.1, 8.3, 8.4_

- [x] 7. 集成与实测
  - [x] 7.1 集成：历史数据加载兼容 + 汇总/子页/决策树端到端 + EventBus B50
    - _Requirements: 1.5, 4.3, 5.2, 7.2_
  - [x] 7.2 Playwright：打开 C2 → 汇总表控制点 → 子页抽样 → Cx-2 决策树 → A14 跳转 → 只读
    - _Requirements: 2.4, 4.2, 5.3, 8.4_

- [x] 8. 交互增强（点选/附件OCR/一键联动回写）
  - [x] 8.1 汇总表命名下拉点选 + 样本结果点选按钮 + Cx-2 六步单选自动推进 + 引导区 + tooltip
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_
  - [x] 8.2 Cx-1-X 样本行 📎 附件上传 + OCR merge + 抽样工具引用 GtIndexChip + 持久化
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - [x] 8.3 索引一键跳子页 + 偏差回填汇总 + 缺陷跳 A14 带摘要回填 + B23 一键引用生成汇总行 + EventBus B50（P8/P9/P10/P11 PBT）
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
