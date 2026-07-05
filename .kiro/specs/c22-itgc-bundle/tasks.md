# Implementation Plan: C22 IT 一般控制测试聚合组件

## Overview

对齐 `s34-ipo-bundle`/`a17-bundle` 聚合模式：1 个 bundle componentType + C21/C21-1 skip + ITGC 矩阵总览 + 4 大类（SA/PE/PM/NS）分组可滚动页签 + 33 IT 控制域子页 + 缺陷联动汇总 C21-1 + 完成/缺陷仪表盘。PBT 用 fast-check。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3"] },
    { "id": "wave3", "tasks": ["3.1", "3.2"] },
    { "id": "wave4", "tasks": ["4.1", "4.2", "4.3"] },
    { "id": "wave5", "tasks": ["5.1", "5.2", "5.3"] },
    { "id": "wave6", "tasks": ["6.1", "6.2"] },
    { "id": "wave7", "tasks": ["7.1", "7.2"] },
    { "id": "wave8", "tasks": ["8.1", "8.2", "8.3"] }
  ]
}
```

## Notes

- 铁律：任务标记不假绿；optional(*) 也要做完；改动后必 Playwright 实测。
- C22 33 子页同属一个工作簿，走 render-config sheets 内部分发；C21/C21-1 独立底稿走 wp_index。
- bundle 顶层 el-tabs 允许。完成后归档并更新 `.kiro/specs/INDEX.md`。

## Tasks

- [x] 1. Phase0 双源核对
  - 运行 `analyze_c_category.py` + `dump_c_content.py`，确认 C22 主矩阵列结构、33 子页 sheet 名与 4 大类归属、子页对主表的公式引用、C21/C21-1 结构
  - 产出 TabDef 分组表 + 缺陷字段映射
  - _Requirements: 3.2, 4.1, 4.4, 5.1_

- [x] 2. 后端注册与 skip
  - [x] 2.1 VALID_COMPONENT_TYPES 新增 `c22-itgc-bundle`
    - _Requirements: 1.4_
  - [x] 2.2 wp_code_overrides：`C22→c22-itgc-bundle`，C21/C21-1 → `skip`
    - _Requirements: 1.2, 2.1, 2.2_
  - [x] 2.3 validate_overrides + 注册契约测试
    - _Requirements: 1.4_

- [x] 3. useC22BundleState composable
  - [x] 3.1 sheetTabs 分组 + wpIdMap（C21/C21-1）+ completionMap 推导
    - _Requirements: 4.1, 7.1_
  - [x] 3.2 缺陷收集（是否异常=是）+ progressSummary + refreshCompletion
    - _Requirements: 5.1, 5.2, 7.1, 7.2, 7.4_

- [x] 4. GtC22ItgcBundle.vue 主入口
  - [x] 4.1 htmlRendererRegistry 注册 + matrix 总览面板（点击行跳子页）
    - _Requirements: 1.1, 3.1, 3.2, 3.3, 3.4_
  - [x] 4.2 4 大类分组可滚动 el-tabs + IT 控制域子页渲染（设计/执行有效性+样本+缺陷评估）+ 公式引用
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [x] 4.3 sheetName 路由 + readonly 透传
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 9.1, 9.2, 9.3_

- [x] 5. 缺陷联动、C21/C21-1、仪表盘
  - [x] 5.1 缺陷汇总联动 C21-1（GtIndexChip 跳转 + 补充影响/整改建议）
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [x] 5.2 C21 IT 专业成员 Tab（下拉选项 + 持久化）
    - _Requirements: 8.1, 8.2, 8.3_
  - [x] 5.3 完成/缺陷仪表盘（三色 + 缺陷总数，实时更新）
    - _Requirements: 7.2, 7.3_

- [x] 6. PBT
  - [x] 6.1 fast-check：P1 skip/注册 / P2 子页分组 / P3 缺陷汇总 / P4 进度统计
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 4.1, 5.1, 5.2, 7.1, 7.2_
  - [x] 6.2 fast-check：P5 sheetName 路由 / P6 readonly 透传
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 9.1, 9.2_

- [x] 7. 集成与实测
  - [x] 7.1 集成：挂载 mock render-config + wp_index，验证矩阵/分组/子页/缺陷联动
    - _Requirements: 3.1, 4.1, 5.2_
  - [x] 7.2 Playwright：打开 C22 → 矩阵点击 → SA/PE/PM/NS 分组切换 → 子页缺陷 → C21-1 汇总 → 只读
    - _Requirements: 3.3, 4.1, 5.2, 9.1_

- [x] 8. 交互增强（点选/附件OCR证据编号/缺陷回写）
  - [x] 8.1 设计/执行有效性结论、是否异常、IT类别、应用系统点选控件 + tooltip + 方法论上下文
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - [x] 8.2 子页审计证据/样本 📎 附件上传 + 证据索引号自动建议（C22.SA-3-1）+ OCR merge + 持久化
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
  - [x] 8.3 缺陷回写 C21-1（是否异常联动增删）+ GtIndexChip 跳 A14 带摘要 + 双向追溯（P7/P8/P9 PBT）
    - _Requirements: 12.1, 12.2, 12.3, 12.4_
