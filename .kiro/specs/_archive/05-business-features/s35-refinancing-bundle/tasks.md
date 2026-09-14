# Implementation Plan: S35 再融资审核聚合组件

## Overview

对齐 `s34-ipo-bundle` / `a17-bundle` 聚合模式：1 个 bundle componentType + 5 核查底稿及子表 skip + 一行页签 + GtAProgramConsole embedded + 明细核查子表（子 sheet 切换 + 公式重算 + 导入导出）+ 完成仪表盘。PBT 用 fast-check。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3"] },
    { "id": "wave3", "tasks": ["3.1", "3.2"] },
    { "id": "wave4", "tasks": ["4.1", "4.2", "4.3"] },
    { "id": "wave5", "tasks": ["5.1", "5.2"] },
    { "id": "wave6", "tasks": ["6.1", "6.2", "6.3"] },
    { "id": "wave7", "tasks": ["7.1", "7.2"] }
  ]
}
```

## Notes

- 铁律：任务标记不假绿；optional(*) 也要做完；改动后必 Playwright 实测。
- 导入导出用 http(axios) 不用原生 fetch（避免 401）；中文文件名 RFC5987。
- 完成后归档并更新 `.kiro/specs/INDEX.md`。

## Tasks

- [x] 1. Phase0 双源核对：S35 结构落定
  - 运行 `analyze_s_category.py`，确认 S35-1~5 程序表 + 明细核查子表（S35-x-1）sheet 名、公式与核查判断列
  - 产出 5 核查底稿 Tab 标签 + 子表映射表
  - _Requirements: 3.1, 3.3, 4.1_

- [x] 2. 后端注册与 skip 映射
  - [x] 2.1 VALID_COMPONENT_TYPES 新增 `s35-refinance-bundle`
    - _Requirements: 1.4_
  - [x] 2.2 wp_code_overrides：`S35→s35-refinance-bundle`，S35-1~5 及子表 → `skip`
    - _Requirements: 1.2, 2.1, 2.2_
  - [x] 2.3 validate_overrides 校验通过（单测）
    - _Requirements: 1.4_

- [x] 3. useS35BundleState composable
  - [x] 3.1 wpIdMap（wp_index 过滤 S35-*，含子表）+ 可见 Tab 计算
    - _Requirements: 6.1, 6.2_
  - [x] 3.2 completionMap + progressSummary + refreshCompletion
    - _Requirements: 8.1_

- [x] 4. GtS35Bundle.vue 主入口 + 子表
  - [x] 4.1 5 核查底稿 TabDef + el-tabs；子表子 sheet 切换（核查程序/明细核查表）
    - _Requirements: 3.1, 3.2, 3.3_
  - [x] 4.2 明细子表公式实时重算（公式列只读）+ 保留核查判断列 + 动态行导入导出
    - _Requirements: 4.1, 4.2, 4.3_
  - [x] 4.3 sheetName 路由 + readonly 透传
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 8.4, 8.5_

- [x] 5. 引用与前端注册
  - [x] 5.1 索引列 GtIndexChip（prop `value`）内部/外部跳转分流 + 灰态兜底
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x] 5.2 htmlRendererRegistry 注册 `s35-refinance-bundle`（defineAsyncComponent, contextProps standard）
    - _Requirements: 1.1, 1.3_

- [x] 6. 完成仪表盘与空状态
  - [x] 6.1 页签栏上方完成进度仪表盘（三色）
    - _Requirements: 8.1, 8.2, 8.3_
  - [x] 6.2 wp_id 不存在→Tab 隐藏
    - _Requirements: 6.2, 6.3_
  - [x] 6.3 无任何 S35→空状态提示
    - _Requirements: 6.4_

- [x] 7. PBT 与集成测试
  - [x] 7.1 PBT（fast-check ≥100 次）：P1 skip / P2 wp_id / P3 可见性 / P4 路由 / P5 子表公式 / P6 进度 / P7 readonly
    - _Requirements: 1.2, 2.1, 2.2, 6.1, 6.2, 6.3, 6.4, 5.1, 5.4, 4.2, 8.1, 8.4_
  - [x] 7.2 集成 + Playwright：点击 S35→页签切换→子表填写重算→导入导出往返→只读模式
    - _Requirements: 3.2, 4.2, 4.3, 8.5_
