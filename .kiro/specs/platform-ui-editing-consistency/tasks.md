# 实施计划：平台 UI、编辑状态与全局组件一致性

## 任务总览

> 本节保留主任务索引；实际排期和执行以“详细落地拆解”为准。

- [ ] 1. 页面骨架统一
  - [ ] 1.1 新建或固化 `GtPageShell`
  - [ ] 1.2 接入 `GtPageHeader`、`ProjectContextBar`、`GtToolbar`
  - [ ] 1.3 选取 5 个高频页面试点迁移
  - [ ] 1.4 视觉验收：头部、工具栏、状态区一致
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] 2. 表格组件治理
  - [ ] 2.1 更新 CI 裸 `el-table` baseline
  - [ ] 2.2 扫描新增裸 `el-table`
  - [ ] 2.3 迁移高频展示表到 `GtTableExtended`
  - [ ] 2.4 迁移高频编辑表到 `GtFormTable`
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 3. 金额与 Decimal 统一
  - [ ] 3.1 扫描页面级 `toFixed` / 原生浮点求和
  - [ ] 3.2 金额列接入 `GtAmountCell`
  - [ ] 3.3 统一负数、千分位、单位显示
  - [ ] 3.4 测试：金额汇总不产生浮点误差
  - _Requirements: 3.1, 3.2_

- [ ] 4. 复制粘贴统一
  - [ ] 4.1 扩展 `useCopyPaste` 支持 Excel 多行多列
  - [ ] 4.2 支持括号负数、千分位、空格识别
  - [ ] 4.3 粘贴前 diff 预览
  - [ ] 4.4 粘贴操作接入 undo 与审计日志
  - _Requirements: 3.3, 3.4_

- [ ] 5. 编辑状态机
  - [ ] 5.1 新建 `useEditStateMachine`
  - [ ] 5.2 统一 dirty/saving/saved/conflict/locked/archived 状态
  - [ ] 5.3 接入底稿、附注、报表配置、调整分录页面
  - [ ] 5.4 测试：dirty 离开拦截与保存失败提示
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 6. 加载、空态、异常统一
  - [ ] 6.1 扩展 `GtEmpty` 使用规范
  - [ ] 6.2 扫描并替换裸 `ElMessage.error`
  - [ ] 6.3 异步任务统一使用 `AsyncJobProgress`
  - [ ] 6.4 测试：无权限、加载失败、开发中状态展示一致
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 7. 显示偏好
  - [ ] 7.1 扩展 `displayPrefs`
  - [ ] 7.2 试算表、底稿、报表、附注、合并表格接入字号和密度
  - [ ] 7.3 编写字体字号与导出样式映射文档
  - _Requirements: 6.1, 6.2, 6.3_

- [ ] 8. 验收
  - [ ]* vue-tsc 0 errors
  - [ ]* Vitest 关键组件测试通过
  - [ ]* UAT：助理连续使用 4 小时无明显视觉割裂

---

## 详细落地拆解（执行以本节为准）

### P0-MVP：一周内最小可交付

- [ ] MVP-1. `GtPageShell` 在 1 个页面试点接入
- [ ] MVP-2. `GtAmountCell` + Decimal 测试覆盖展示/复制/解析
- [ ] MVP-3. `handleApiError` 覆盖权限、网络、后端 detail、degraded
- [ ] MVP-4. `useEditStateMachine` 在 `WorkpaperEditor` 跑通 dirty/saving/saved
- [ ] MVP-5. 测试文件落地：
  - `audit-platform/frontend/src/components/common/__tests__/GtPageShell.spec.ts`
  - `audit-platform/frontend/src/components/common/__tests__/GtAmountCell.spec.ts`
  - `audit-platform/frontend/src/__tests__/useEditStateMachine.spec.ts`
  - `audit-platform/frontend/src/utils/__tests__/errorHandler.spec.ts`

### P0：页面骨架、金额、错误处理、编辑状态

- [ ] P0-1. UI 现状扫描
  - [ ] P0-1.1 扫描裸 `el-table`、裸 `ElMessage.error`、页面级 `toFixed`
  - [ ] P0-1.2 盘点 5 个试点页面的 header、toolbar、loading、empty、save 状态实现
  - [ ] P0-1.3 输出 `docs/frontend/ui-consistency-migration-inventory.md`
  - _Requirements: 1.3, 2.3, 3.2, 5.3_

- [ ] P0-2. GtPageShell 最小实现
  - [ ] P0-2.1 新建 `components/common/GtPageShell.vue`
  - [ ] P0-2.2 slot：header、context、toolbar、banners、default
  - [ ] P0-2.3 接入 `GtPageHeader` 和 `ProjectContextBar`
  - [ ] P0-2.4 在 `TrialBalance` 和 `WorkpaperEditor` 试点
  - [ ] P0-2.5 明确适用边界：非项目页、登录页、纯弹窗页可不接入
  - _Requirements: 1.1, 1.2_

- [ ] P0-3. 金额与 Decimal 统一
  - [ ] P0-3.1 建立 `GtAmountCell` 使用规范
  - [ ] P0-3.2 替换试点页面金额展示
  - [ ] P0-3.3 扫描并修复原生浮点求和
  - [ ] P0-3.4 Vitest：金额展示/复制/解析不改变 Decimal 值
  - _Requirements: 3.1, 3.2_

- [ ] P0-4. 错误处理统一
  - [ ] P0-4.1 扩展现有错误处理扫描脚本到 `views` + `components`
  - [ ] P0-4.2 替换试点页面裸 `ElMessage.error`
  - [ ] P0-4.3 `handleApiError` 支持权限、网络、后端 detail、degraded 四类
  - [ ] P0-4.4 Vitest：错误输入映射到统一文案
  - _Requirements: 5.3_

- [ ] P0-5. 编辑状态机最小闭环
  - [ ] P0-5.1 新建 `useEditStateMachine`
  - [ ] P0-5.2 支持 pristine/dirty/saving/saved/conflict/readonly/locked/archived
  - [ ] P0-5.3 接入 `WorkpaperEditor`、`DisclosureEditor`
  - [ ] P0-5.4 测试：dirty 离开拦截、保存失败不清 dirty
  - _Requirements: 4.1, 4.2, 4.3_

### P1：表格、复制粘贴、空态、显示偏好

- [ ] P1-1. 表格组件迁移试点
  - [ ] P1-1.1 `TrialBalance` 表格能力对账：双表头、合计、右键、编辑列
  - [ ] P1-1.2 `ReportView` 表格能力对账：动态列、合并单元格、横向滚动
  - [ ] P1-1.3 `DisclosureEditor` 表格能力对账：动态行列、合并、公式
  - [ ] P1-1.4 `TrialBalance` 独立迁移任务：双表头、合计、右键、编辑列全部验收
  - [ ] P1-1.5 `ReportView` 独立迁移任务：动态列、合并单元格、横向滚动全部验收
  - [ ] P1-1.6 `DisclosureEditor` 独立迁移任务：动态行列、合并、公式全部验收
  - _Requirements: 2.1, 2.2_

- [ ] P1-2. 复制粘贴增强
  - [ ] P1-2.1 `useCopyPaste` 支持 HTML table 与纯文本 matrix
  - [ ] P1-2.2 支持括号负数、千分位、百分比、空白单元格
  - [ ] P1-2.3 粘贴前 diff 预览
  - [ ] P1-2.4 粘贴写入 undo stack
  - [ ] P1-2.5 审计日志仅记录结构化摘要，不记录大段剪贴板原文
  - _Requirements: 3.3, 3.4_

- [ ] P1-3. 加载、空态、异步任务统一
  - [ ] P1-3.1 首屏 skeleton 规范
  - [ ] P1-3.2 `GtEmpty` 四类预设接入试点页面
  - [ ] P1-3.3 import/export/generate/archive 使用 `AsyncJobProgress`
  - [ ] P1-3.4 UAT：断网、无权限、空数据、开发中状态一致
  - _Requirements: 5.1, 5.2_

- [ ] P1-4. 显示偏好
  - [ ] P1-4.1 扩展 `displayPrefs.ts`：density/fontSize/amountUnit/fixedColumns
  - [ ] P1-4.2 试算表、底稿、报表、附注、合并页面接入
  - [ ] P1-4.3 编写 `docs/frontend/display-preferences.md`
  - _Requirements: 6.1, 6.2, 6.3_

### P2：全量治理与退役

- [ ] P2-1. 全量页面迁移
  - [ ] P2-1.1 按访问频率迁移剩余页面
  - [ ] P2-1.2 裸 `el-table` 降到豁免白名单
  - [ ] P2-1.3 新增页面 PR 必须声明组件选择
  - _Requirements: 1.3, 2.3_

- [ ] P2-2. `GtEditableTable` 退役计划
  - [ ] P2-2.1 统计现有调用方
  - [ ] P2-2.2 editable=true 迁移 `GtFormTable`
  - [ ] P2-2.3 editable=false 迁移 `GtTableExtended`
  - [ ] P2-2.4 grep 0 调用后删除 wrapper
  - _Requirements: 2.1, 2.2_

### 验收与回归

- [ ] UAT-1 助理：连续编辑底稿 30 分钟，保存/冲突/离开提示一致
- [ ] UAT-2 助理：Excel 粘贴金额后汇总无误差
- [ ] UAT-3 经理：调整字号和紧凑模式后各核心表格一致变化
- [ ] UAT-4 QC：API 失败时错误提示统一且可重试
- [ ] CI-1 `check_naked_el_table` 无新增违规
- [ ] CI-2 `check_elmessage_error` 无新增违规
- [ ] CI-3 金额 Decimal 测试全绿
