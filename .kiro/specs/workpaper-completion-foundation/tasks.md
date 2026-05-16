# Implementation Plan: 底稿模板内容预设基础设施

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|----------|
| v1.0 | 2026-05-17 | 初始版本 | design.md 审批通过 |

## Overview

将 design.md 的 7 项基础设施能力转化为可执行的编码任务，按 3 个 Sprint 递进实施：
- Sprint 1（2 天）：后端数据层 + 4 个前端 composables + 属性测试
- Sprint 2（2 天）：前端 UI 集成（WorkpaperEditor 工具栏/标记/标签/菜单 + WorkpaperWorkbench 徽章）
- Sprint 3（1 天）：Playwright E2E 测试 + UAT 验收

实现语言：后端 Python（FastAPI + SQLAlchemy + openpyxl）/ 前端 TypeScript + Vue 3

## Tasks

- [ ] 1. Sprint 1：后端 + Composables + 属性测试
  - [ ] 1.0 验证底稿模板完整加载链路（Requirement 0 关键前置）
    - 确认后端 GET /xlsx-to-json 对陕西华氏 D2 返回 20 sheets / 13024+ cells / 含 mergeData + columnData + freeze
    - 确认前端 WorkpaperEditor Strategy 3 调用 GET /xlsx-to-json 成功（非 POST FormData）
    - 确认 `univerAPI.createWorkbook(jsonData)` 后 Univer 渲染全部 20 sheet tabs
    - 确认不走 final fallback（空白 workbook）——如走了则定位并修复
    - 确认合并单元格 / 冻结窗格 / 格式（粗体/底色/边框）在 Univer 中正确渲染
    - 如有问题则在此 task 内修复（不能带着"空白"问题进入后续 task）
    - **验收标准**：用 Playwright 截图 D2 底稿编辑器，确认 ≥ 3 个 sheet tab 可见 + 审定表有数据行
    - _Requirements: 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8_

  - [ ] 1.1 新增 gt-tokens.css 预填充标记 token
    - 在 `audit-platform/frontend/src/styles/gt-tokens.css` 新增 4 个 CSS 变量：`--gt-marker-prefill-tb: #E3F2FD` / `--gt-marker-prefill-aje: #E8F5E9` / `--gt-marker-prefill-prev: #F3E5F5` / `--gt-marker-prefill-wp: #E0F7FA`
    - 新增 `--gt-marker-prefill-error` border 色 `#FF5149`
    - _Requirements: 1.1, 1.3_

  - [ ] 1.2 后端 GET /xlsx-to-json 注入 prefill_source 到 cellData
    - 修改 `backend/app/routers/workpaper_template_file.py` 的 xlsx-to-json 转换逻辑
    - 读取 `backend/data/prefill_formula_mapping.json`，按 wp_code 匹配当前底稿
    - 对匹配的 cell 坐标写入 `cellData[row][col].custom.prefill_source` + `cellData[row][col].custom.prefill_formula`
    - 按 source type 设置 `cellData[row][col].s.bg.rgb` 对应颜色
    - prefill 失败的 cell 写入 `custom.prefill_source = "ERROR"` + `custom.prefill_error` + 红色 border style
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6_

  - [ ] 1.2b 后端 prefill_engine 新增 TB_AUX formula_type 支持
    - 修改 `backend/app/services/prefill_engine.py`
    - 新增 `_resolve_tb_aux(account_code, aux_type, column)` 方法：从 tb_aux_balance 表按 (project_id, year, account_code, aux_type) 查询，返回明细行数组
    - 在 prefill 主循环中识别 formula_type="TB_AUX" 条目，调用 _resolve_tb_aux 取数
    - TB_AUX 返回多行时写入连续 cell（从 mapping 指定的起始行向下填充）
    - 辅助维度不存在时 cell 留空 + prefill_source="AUX_UNAVAILABLE" + logger.warning
    - _Requirements: Cycle-D R2.2, R2.3（Foundation 承担引擎扩展，Cycle-D 只产出数据）_

  - [ ] 1.3 Alembic 迁移：cell_annotations 新增 annotation_type + sheet_name
    - 新建 `backend/alembic/versions/workpaper_completion_cell_annotations_20260517.py`
    - `ALTER TABLE cell_annotations ADD COLUMN IF NOT EXISTS annotation_type VARCHAR(30) NOT NULL DEFAULT 'comment'`
    - `ALTER TABLE cell_annotations ADD COLUMN IF NOT EXISTS sheet_name VARCHAR(100)`
    - down_revision 接续当前 Alembic 链末端
    - _Requirements: 4.7_

  - [ ] 1.4 新建后端端点 GET /api/projects/{pid}/workpapers/review-status
    - 新建 `backend/app/routers/wp_review_status.py`
    - 聚合 cell_annotations 表 WHERE annotation_type='review_mark' 按 wp_id 分组统计
    - 返回 `{ cycles: [{ cycle_code, cycle_name, total_workpapers, reviewed_workpapers, workpapers: [...] }] }`
    - 注册到 router_registry.py（使用下一个可用 §编号）
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [ ] 1.5 新建前端 composable: usePrefillMarkers
    - 新建 `audit-platform/frontend/src/composables/usePrefillMarkers.ts`
    - 从 IWorkbookData 的 cellData 中提取所有含 `custom.prefill_source` 的 cell
    - 提供 `getPrefillInfo(row, col)` 返回 source type + formula + error
    - 提供 `getTooltipText(row, col)` 返回 hover tooltip 内容（来源类型中文 + 公式表达式）
    - 提供 `getFormulaBarText(row, col)` 返回选中时公式栏显示内容
    - 提供 `SOURCE_COLOR_MAP` 常量映射 4 种来源到 CSS token
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ] 1.6 新建前端 composable: useCrossModuleRefs
    - 新建 `audit-platform/frontend/src/composables/useCrossModuleRefs.ts`
    - 从 `cross_wp_references.json` 加载当前 wp_code 的所有 targets
    - 提供 `getRefsForCell(sheet, cellRef)` 返回 CrossModuleRef[]
    - 提供 `computeRouterPath(ref)` 生成跳转路由
    - 提供 `TARGET_COLOR_MAP` 常量：附注=紫色, 报表=蓝色, 底稿=青色
    - _Requirements: 3.1, 3.2, 3.3, 3.5_

  - [ ] 1.7 新建前端 composable: useReviewMarks
    - 新建 `audit-platform/frontend/src/composables/useReviewMarks.ts`
    - 提供 `createReviewMark(wpId, sheetName, cellRef, status, comment)` 调用后端 API
    - 提供 `getReviewMarks(wpId)` 查询当前底稿所有复核标记
    - 提供 `getIndicatorColor(status)` 返回 green(reviewed) / orange(questioned)
    - 提供 `reviewStats` computed 统计已复核/待确认/有疑问数量
    - _Requirements: 4.2, 4.3, 4.6, 4.7_

  - [ ] 1.8 新建前端 composable: useUserOverrides
    - 新建 `audit-platform/frontend/src/composables/useUserOverrides.ts`
    - 维护 `userOverrides: Ref<Record<string, boolean>>` 集合（key = "SheetName!CellRef"）
    - 提供 `markAsOverride(sheet, cellRef)` 添加到集合
    - 提供 `removeOverride(sheet, cellRef)` 从集合移除
    - 提供 `isOverridden(sheet, cellRef)` 查询
    - 提供 `serializeOverrides()` 返回 JSON 用于保存到 parsed_data.user_overrides
    - 提供 `loadOverrides(parsedData)` 从 parsed_data 恢复
    - _Requirements: 7.1, 7.3, 7.7_

  - [ ]* 1.9 属性测试：Property 1 - Prefill cell style correctness
    - 新建 `backend/tests/test_workpaper_completion_properties.py`
    - **Property 1: Prefill cell style correctness**
    - 用 hypothesis 生成随机 prefill_source 值，验证转换后 cellData 的 bg.rgb 与 SOURCE_COLOR_MAP 一致
    - ERROR 类型验证有红色 border style
    - **Validates: Requirements 1.1, 1.6**

  - [ ]* 1.10 属性测试：Property 2 - Color mapping uniqueness
    - **Property 2: Source/reference type → color mapping uniqueness**
    - 验证 4 种 source type 和 3 种 reference target type 的颜色映射互不相同
    - **Validates: Requirements 1.3, 3.5**

  - [ ]* 1.11 属性测试：Property 5 - Prefill summary message correctness
    - **Property 5: Prefill summary message correctness**
    - 用 hypothesis 生成随机 per-source breakdown，验证 X + Y + Z + W = N
    - **Validates: Requirements 2.5, 7.6**

  - [ ]* 1.12 属性测试：Property 9 - Review mark persistence round-trip
    - **Property 9: Review mark persistence round-trip**
    - 用 hypothesis 生成随机 review mark 数据，创建后查询验证字段完整保留
    - **Validates: Requirements 4.2, 4.7**

  - [ ]* 1.13 属性测试：Property 12 - User override detection on edit
    - **Property 12: User override detection on edit**
    - 验证编辑含 prefill_source 的 cell 后，该 cell ref 被加入 user_overrides 集合
    - **Validates: Requirements 7.1**

  - [ ]* 1.14 属性测试：Property 13 - Prefill skip logic for overrides
    - **Property 13: Prefill skip logic for overrides**
    - 用 hypothesis 生成随机 overrides 集合，验证 prefill 执行后这些 cell 值不变
    - **Validates: Requirements 7.2**

  - [ ]* 1.15 属性测试：Property 14 - User override round-trip persistence
    - **Property 14: User override round-trip persistence**
    - 验证 serializeOverrides → 保存 → loadOverrides 后集合完全一致
    - **Validates: Requirements 7.7**

  - [ ] 1.16 Checkpoint - Sprint 1 验证
    - 确保所有属性测试通过（`python -m pytest backend/tests/test_workpaper_completion_properties.py`）
    - 确保 getDiagnostics 对 4 个 composable 文件零错误
    - 确保后端启动无 import error
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 2. Sprint 2：前端 UI 集成
  - [ ] 2.1 WorkpaperEditor 工具栏"📊 一键填充"按钮
    - 修改 `audit-platform/frontend/src/views/WorkpaperEditor.vue` 工具栏区域
    - 新增"📊 一键填充"按钮，点击调用 prefill API（仅当前 wp_code）
    - 按钮 loading 状态 + 禁止重复点击
    - 无 prefill mapping 时 disabled + tooltip "当前底稿无预设公式配置"
    - 完成后 reload workbook data + 应用视觉标记 + toast 摘要
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ] 2.2 WorkpaperEditor 预填充 cell hover tooltip
    - 监听 Univer cell hover 事件
    - 调用 `usePrefillMarkers.getTooltipText()` 显示来源类型 + 公式
    - 选中 cell 时在公式栏区域显示 `getFormulaBarText()`
    - ERROR cell 显示红色 tooltip "取数失败: {error_message}"
    - _Requirements: 1.2, 1.4, 1.6_

  - [ ] 2.3 WorkpaperEditor 跨模块跳转标签 overlay
    - 在 Univer 容器上方新增 `<div class="gt-cross-ref-overlay">` 绝对定位层
    - 调用 `useCrossModuleRefs.getRefsForCell()` 计算可视区域内的标签
    - 单引用显示 tag（如 "→ 附注 5.7"），多引用显示 stacked badge + count
    - 点击 tag 调用 `router.push(computeRouterPath(ref))`
    - 目标不可用时灰色 + tooltip "目标不可用"
    - 滚动时监听 Univer scroll 事件同步更新位置
    - 虚拟化：只渲染可视区域内的标签（性能保护）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 2.4 WorkpaperEditor 右键菜单"✓ 标记复核"
    - 扩展 WorkpaperEditor 右键菜单，新增"✓ 标记复核"选项
    - 点击后弹出 ElDialog 输入可选 comment + 选择 status（已复核/待确认/有疑问）
    - 调用 `useReviewMarks.createReviewMark()` 保存到后端
    - 保存成功后在 cell 角落显示绿色/橙色 checkmark indicator
    - hover indicator 显示 popover（reviewer name + timestamp + comment）
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6_

  - [ ] 2.5 WorkpaperEditor 侧面板"复核标记"Tab
    - 在 WorkpaperSidePanel 新增"复核标记"Tab
    - 列出当前底稿所有 review marks（cell ref + status + reviewer + time）
    - 支持按 status 筛选（已复核/待确认/有疑问）
    - 点击列表项定位到对应 cell
    - _Requirements: 4.5_

  - [ ] 2.6 WorkpaperEditor User Override 检测与标记
    - 监听 Univer `onCellEdited` 事件
    - 检查被编辑 cell 是否有 `custom.prefill_source`
    - 若有，调用 `useUserOverrides.markAsOverride()`
    - 在 cell 角落显示 ✏️ pencil icon
    - hover 显示 tooltip "已手动修改，刷新取数时将跳过此单元格"
    - 右键菜单新增"恢复预填充"选项，调用 `removeOverride()` + 重新 prefill 该 cell
    - _Requirements: 7.1, 7.3, 7.4, 7.5_

  - [ ] 2.7 WorkpaperEditor 刷新取数逻辑（跳过 overrides + 摘要）
    - "📊 一键填充"执行时读取 `useUserOverrides` 集合
    - 将 overrides 集合传给后端 prefill API（后端跳过这些 cell）
    - 完成后显示摘要 toast："已刷新 N 个单元格，跳过 M 个手动修改的单元格"
    - _Requirements: 7.2, 7.6_

  - [ ] 2.8 WorkpaperEditor 保存时持久化 user_overrides
    - 在 `onSave` 流程中，将 `useUserOverrides.serializeOverrides()` 写入 `parsed_data.user_overrides`
    - 加载底稿时调用 `loadOverrides(parsedData)` 恢复集合
    - _Requirements: 7.7_

  - [ ] 2.9 WorkpaperWorkbench 循环级复核状态徽章
    - 修改 `audit-platform/frontend/src/views/WorkpaperWorkbench.vue` 底稿树
    - 在每个 Cycle_Node 上显示 "{reviewed_count}/{total_count} 已复核" badge
    - 全部完成时绿色 "✓ 全部完成"，无复核时灰色 "0/{total} 待复核"
    - 订阅 eventBus `review-mark:changed` 事件，3 秒内刷新 badge
    - badge 可点击展开 per-workpaper 复核状态列表
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.6_

  - [ ] 2.10 Checkpoint - Sprint 2 验证
    - getDiagnostics 对所有修改的 Vue 文件零错误
    - vue-tsc --noEmit 通过
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Sprint 3：E2E 测试 + 验收
  - [ ] 3.1 Playwright E2E 配置与测试数据准备
    - 确认 `audit-platform/frontend/playwright.config.ts` baseURL 指向 localhost:3030
    - 在 `audit-platform/frontend/e2e/workpaper-completion/` 目录下新建测试文件
    - 准备测试数据 seed：陕西华氏项目 D2 底稿（已有真实数据）
    - _Requirements: 6.1, 6.6_

  - [ ] 3.2 E2E 测试：预填充视觉标记验证
    - 新建 `e2e/workpaper-completion/prefill-markers.spec.ts`
    - 登录 → 导航到陕西华氏项目 D2 底稿 → 验证预填充 cell 有视觉标记（背景色）
    - 验证 hover 显示 tooltip 含来源类型
    - _Requirements: 6.2_

  - [ ] 3.3 E2E 测试：一键填充功能验证
    - 新建 `e2e/workpaper-completion/one-click-prefill.spec.ts`
    - 点击"📊 一键填充" → 验证 cell 值更新 → 验证 toast 摘要出现
    - _Requirements: 6.3_

  - [ ] 3.4 E2E 测试：复核标记功能验证
    - 新建 `e2e/workpaper-completion/review-marks.spec.ts`
    - 右键 cell → 选择"标记复核" → 填写 comment → 验证绿色 indicator 出现
    - _Requirements: 6.4_

  - [ ] 3.5 E2E 测试：循环徽章验证
    - 新建 `e2e/workpaper-completion/cycle-badge.spec.ts`
    - 导航到 WorkpaperWorkbench → 验证循环节点显示正确的复核计数
    - _Requirements: 6.5_

  - [ ] 3.6 E2E 运行验证
    - 确保 `npx playwright test e2e/workpaper-completion/` 全部通过
    - 总耗时 < 60 秒
    - _Requirements: 6.7_

  - [ ] 3.7 Final Checkpoint - 全部验证
    - 后端属性测试全绿
    - 前端 vue-tsc 零错误
    - E2E 4 个用例全绿
    - Ensure all tests pass, ask the user if questions arise.

## UAT 验收清单

| # | 验收项 | Requirements | Tester | Date | Status | 备注 |
|---|--------|-------------|--------|------|--------|------|
| 1 | 打开 D2 底稿，预填充 cell 有浅蓝/绿/紫/青背景色 | 1.1, 1.3 | | | ○ pending | |
| 2 | hover 预填充 cell 显示来源类型+公式 tooltip | 1.2 | | | ○ pending | |
| 3 | 点击"📊 一键填充"后 cell 值更新 + toast 摘要 | 2.2, 2.4, 2.5 | | | ○ pending | |
| 4 | 手动编辑预填充 cell 后出现 ✏️ 图标 | 7.1, 7.3 | | | ○ pending | |
| 5 | 刷新取数跳过手动修改的 cell + 摘要显示跳过数 | 7.2, 7.6 | | | ○ pending | |
| 6 | 右键"标记复核"后 cell 角落出现绿色/橙色标记 | 4.1, 4.3, 4.6 | | | ○ pending | |
| 7 | 底稿树循环节点显示"3/8 已复核"徽章 | 5.1 | | | ○ pending | |
| 8 | 跨模块标签"→ 附注 5.7"可见且可点击跳转 | 3.1, 3.2 | | | ○ pending | |

Status 枚举：✓ pass / ⚠ partial / ○ pending / ✗ fail

## 已知缺口与技术债

| ID | 缺口 | 优先级 | 触发条件 | 后续 spec | 修复时间 |
|----|------|--------|----------|-----------|----------|
| TD-1 | 跨模块标签 overlay 大量标签（>50）性能未验证 | P2 | 复杂底稿含大量跨引用 | 独立优化 | 上线后观察 |
| TD-2 | Univer Canvas cell 坐标 API 兼容性未验证 | P1 | Univer 版本升级 | - | Sprint 2 实施时验证 |
| TD-3 | cross_wp_references.json 当前仅 20 条规则 | P2 | 更多循环底稿上线 | workpaper-deep-optimization | 持续扩展 |
| TD-4 | 复核标记"已复核"判定逻辑（哪些 cell 是 required）未定义 | P1 | 循环级进度计算 | 独立需求 | Sprint 2 后补充 |

## Notes

- Tasks marked with `*` are optional property-based tests and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from design.md
- 后端属性测试使用 hypothesis 库（已安装 6.152.4），max_examples=5（MVP 阶段）
- 前端 composables 不依赖新 npm 包，使用现有 Vue 3 Composition API + eventBus
- Alembic 迁移 down_revision 需在实施时确认当前链末端
