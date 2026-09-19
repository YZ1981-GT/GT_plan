# Implementation Plan: S32 应对551文舞弊核查聚合组件

## Overview

对齐 `s34-ipo-bundle` / `a17-bundle` 聚合模式：1 个 bundle componentType + 13 舞弊情形 skip + 可滚动页签 + GtAProgramConsole embedded + 导引表/披露格式参考子 sheet + 提示折叠 + 完成仪表盘。PBT 用 fast-check。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3"] },
    { "id": "wave3", "tasks": ["3.1", "3.2"] },
    { "id": "wave4", "tasks": ["4.1", "4.2", "4.3", "4.4"] },
    { "id": "wave5", "tasks": ["5.1", "5.2"] },
    { "id": "wave6", "tasks": ["6.1", "6.2", "6.3"] },
    { "id": "wave7", "tasks": ["7.1", "7.2"] }
  ]
}
```

## Notes

- 铁律：任务标记不假绿；optional(*) 也要做完；改动后必 Playwright 实测。
- bundle 顶层 el-tabs 允许；子组件接 sheetName v-if 分发。
- 完成后归档并更新 `.kiro/specs/INDEX.md`。

## Tasks

- [x] 1. Phase0 双源核对：S32 结构落定
  - 运行 `analyze_s_category.py`，确认 S32-1~13 的程序表 sheet 名、IC-0 导引表、IC-X 披露格式参考、提示 sheet 清单
  - 产出 13 舞弊情形 Tab 标签 + 子 sheet 映射表
  - _Requirements: 3.1, 3.3, 3.4_

- [x] 2. 后端注册与 skip 映射
  - [x] 2.1 VALID_COMPONENT_TYPES 新增 `s32-fraud-bundle`
    - _Requirements: 1.4_
  - [x] 2.2 wp_code_overrides：`S32→s32-fraud-bundle`，S32-1~13 → `skip`
    - _Requirements: 1.2, 2.1, 2.2_
  - [x] 2.3 validate_overrides 校验通过（单测）
    - _Requirements: 1.4_

- [x] 3. useS32BundleState composable
  - [x] 3.1 wpIdMap（wp_index 过滤 S32-*）+ 可见 Tab 计算
    - _Requirements: 5.1, 5.2_
  - [x] 3.2 completionMap + progressSummary + refreshCompletion
    - _Requirements: 7.1_

- [x] 4. GtS32Bundle.vue 主入口
  - [x] 4.1 13 舞弊情形 TabDef + el-tabs 可滚动
    - _Requirements: 3.1, 3.2_
  - [x] 4.2 含 IC-0/IC-X 底稿的子 sheet 切换（核查程序/导引/披露格式参考）
    - _Requirements: 3.3_
  - [x] 4.3 提示长文本 details 折叠区块
    - _Requirements: 3.4_
  - [x] 4.4 sheetName 路由 + readonly 透传
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 8.1, 8.2_

- [x] 5. 引用与前端注册
  - [x] 5.1 索引列 GtIndexChip（prop `value`）+ 灰态兜底
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 5.2 htmlRendererRegistry 注册 `s32-fraud-bundle`（defineAsyncComponent, contextProps standard）
    - _Requirements: 1.1, 1.3_

- [x] 6. 完成仪表盘与空状态
  - [x] 6.1 页签栏上方完成进度仪表盘（三色）
    - _Requirements: 7.2, 7.3, 7.4_
  - [x] 6.2 wp_id 不存在→Tab 隐藏
    - _Requirements: 5.2, 5.3_
  - [x] 6.3 无任何 S32→空状态提示
    - _Requirements: 5.4_

- [x] 7. PBT 与集成测试
  - [x] 7.1 PBT（fast-check ≥100 次）：P1 skip / P2 wp_id / P3 可见性 / P4 路由 / P5 进度 / P6 readonly
    - _Requirements: 1.2, 2.1, 2.2, 5.1, 5.2, 5.3, 5.4, 4.1, 4.4, 7.1, 8.1_
  - [x] 7.2 集成 + Playwright：点击 S32→情形页签切换→导引/披露子 sheet→只读模式
    - _Requirements: 3.2, 3.3, 8.1_
