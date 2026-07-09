# Implementation Plan

> S34 首发审核（IPO）特项底稿聚合组件

## Overview

波次化任务，PBT 用 fast-check（前端）。对齐 `a17-bundle` 聚合模式与 D4 标准。核心：componentType 注册 + skip 映射 + S34-0 总览面板 + 分组可滚动页签 + 公式子检查表 + GtIndexChip + 完成仪表盘。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave1", "tasks": ["1"] },
    { "id": "wave2", "tasks": ["2.1", "2.2", "2.3", "3.1", "3.2"] },
    { "id": "wave3", "tasks": ["4.1", "4.2", "4.3"] },
    { "id": "wave4", "tasks": ["5.1", "5.2", "5.3", "5.4", "6.1", "6.2", "6.3"] },
    { "id": "wave5", "tasks": ["7.1", "7.2", "7.3", "8.1", "8.2", "8.3", "9.1", "9.2"] },
    { "id": "wave6", "tasks": ["10.1", "10.2", "10.3"] },
    { "id": "wave7", "tasks": ["11.1", "11.2", "11.3"] }
  ]
}
```

## Tasks

- [x] 1. Phase0 双源核对：S34 结构落定
  - 运行 `backend/scripts/analyze_s_category.py` + `dump_s34_content.py`，逐一确认 S34-0~41 的 sheet 名、子检查表清单、公式与跨底稿引用
  - 交叉验证底稿模板库 md，产出 41 底稿的分组表 + 子表清单 + regRef（证监会/沪深北条目）映射表
  - _Requirements: 3.2, 4.3, 5.1, 12.1_

- [x] 2. 后端 componentType 注册与 skip 映射
  - [x] 2.1 在 `wp_classification_service.py` 的 VALID_COMPONENT_TYPES 新增 `s34-ipo-bundle`
    - _Requirements: 1.5_
  - [x] 2.2 在 `wp_code_overrides.json` 设 `S34→s34-ipo-bundle`，S34-0~41 及子表编码 → `skip`
    - _Requirements: 1.2, 2.1, 2.2, 2.4_
  - [x] 2.3 后端启动 validate_overrides 校验通过（单测）
    - _Requirements: 1.5_

- [x] 3. S34-0 核查清单 API
  - [x] 3.1 新增 `GET /api/projects/{project_id}/s34-checklist` 返回 `S34ChecklistItem[]`（wpCode/name/regRef/applicability/status）
    - _Requirements: 3.2, 9.1, 12.1_
  - [x] 3.2 router_registry 注册 + 后端单测
    - _Requirements: 3.2_

- [x] 4. useS34BundleState composable
  - [x] 4.1 实现 wpIdMap（wp_index 过滤 S34-*）、checklist 加载、applicableCodes
    - _Requirements: 8.1, 8.3, 9.1_
  - [x] 4.2 实现 completionMap + progressSummary + refreshCompletion
    - _Requirements: 10.1, 10.2, 10.5_
  - [x] 4.3 实现 regRefMap（从清单解析）
    - _Requirements: 12.1, 12.3_

- [x] 5. GtS34Bundle.vue 主入口
  - [x] 5.1 TabDef 分组配置（8 主题，顺序按 S34-0 序号），el-tabs 可滚动 + 分组
    - _Requirements: 4.1, 4.2, 4.3, 4.6_
  - [x] 5.2 overview 面板默认展示，专项 Tab 渲染 GtAProgramConsole(embedded, wp-id)
    - _Requirements: 3.1, 4.4_
  - [x] 5.3 sheetName / route.query.sheet 路由激活 Tab
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x] 5.4 readonly 透传到所有子组件
    - _Requirements: 11.1, 11.2, 11.3_

- [x] 6. GtS34ChecklistOverview.vue 总览面板
  - [x] 6.1 表格呈现 底稿编号/名称/各交易所监管条目/适用状态/完成状态
    - _Requirements: 3.2, 12.3_
  - [x] 6.2 点击行跳转对应 Tab；「仅显示适用」筛选；板块高亮
    - _Requirements: 3.3, 5.5, 9.3, 9.5_
  - [x] 6.3 整体完成进度统计（已完成/进行中/未开始/不适用）+ 不适用理由填写
    - _Requirements: 3.4, 9.2, 10.2_

- [x] 7. 专项子检查表渲染
  - [x] 7.1 GtS34SubCheckTable.vue：Tab 内子 sheet 切换（核查程序 / 明细检查表）
    - _Requirements: 5.1_
  - [x] 7.2 子表公式实时重算（S34-16-1 SUM、占比 C24/C23），公式列只读
    - _Requirements: 5.2, 5.5_
  - [x] 7.3 保留合理性/真实性核查判断列；动态明细行导入导出
    - _Requirements: 5.3, 5.4_

- [x] 8. 跨底稿引用与法规溯源
  - [x] 8.1 索引列以 GtIndexChip（prop `value`）呈现，内部/外部跳转分流
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 8.2 引用不存在→灰态提示
    - _Requirements: 6.4_
  - [x] 8.3 专项 Tab 顶部 regRef「方法论上下文」区块（琥珀色左边线）
    - _Requirements: 12.2_

- [ ] 9. 前端注册与完成仪表盘
  - [ ] 9.1 htmlRendererRegistry 注册 `s34-ipo-bundle`（defineAsyncComponent, contextProps standard）
    - _Requirements: 1.1, 1.3, 1.4_
  - [~] 9.2 页签栏上方完成进度仪表盘（三色，联动 overview）
    - _Requirements: 10.2, 10.3, 10.4_

- [ ] 10. PBT（fast-check，≥100 次/property）
  - [~] 10.1 P1 skip 映射完整性 / P2 wp_id 解析 / P3 Tab 可见性
    - _Requirements: 1.2, 2.1, 2.2, 2.4, 8.1, 8.3, 8.4, 4.1, 9.1, 9.4_
  - [~] 10.2 P4 sheetName 路由 / P5 进度统计 / P6 法规溯源
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 10.1, 10.2, 12.1, 12.3, 12.4_
  - [~] 10.3 P7 readonly 透传 / P8 子表汇总公式确定性
    - _Requirements: 11.1, 11.2, 11.3, 5.2, 5.5_

- [ ] 11. 集成测试与 Playwright 实测
  - [~] 11.1 挂载 mock wp_index + S34-0 API，验证 overview→Tab、子组件渲染、regRef 上下文
    - _Requirements: 3.1, 3.3, 4.4_
  - [~] 11.2 Playwright：点击 S34 → 分组页签切换 → 子检查表填写重算 → 只读模式
    - _Requirements: 4.2, 5.2, 11.1_
  - [~] 11.3 空状态（无 S34 专项）仅显示 overview
    - _Requirements: 9.4_

## Notes

- 铁律：任务标记不假绿；optional(*) 也要做完；改动后必 Playwright 实测。
- D~N/S 专属组件不能有内部 el-tabs（本 bundle 顶层 el-tabs 允许，子组件接 sheetName v-if）。
- 导入导出 composable 用 http(axios) 不用原生 fetch（避免 401）；中文文件名 RFC5987。
- 完成后归档到 `_archive/` 对应分类并更新 `.kiro/specs/INDEX.md`。
