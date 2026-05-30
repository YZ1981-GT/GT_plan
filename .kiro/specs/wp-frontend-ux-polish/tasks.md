# 实施计划：底稿前端体验优化

## 任务

- [ ] 1. 侧栏 4 功能组收敛
  - [ ] 1.1 WorkpaperSidePanel 重构为 el-tabs 嵌套（一级 4 组 + 组内二级）
  - [ ] 1.2 badge 汇总到组标签
  - [ ] 1.3 保留所有现有子面板组件（只改容器结构）

- [ ] 2. 横幅折叠
  - [ ] 2.1 EditorBanners 改为折叠容器（阻断性常驻 + 信息性折叠）
  - [ ] 2.2 摘要行"⚠ N 项待处理" + 展开/收起

- [ ] 3. 首次渐进引导
  - [ ] 3.1 接入 el-tour（Element Plus 2.4+）
  - [ ] 3.2 定义引导步骤（保存/面板/穿透溯源）
  - [ ] 3.3 localStorage 记录 + 跳过/不再提示

- [ ] 4. 门禁引导式
  - [ ] 4.1 新建 usePrerequisiteStatus composable
  - [ ] 4.2 生成/导出页面进入时主动查前置条件 + 显示状态
  - [ ] 4.3 未满足项一键跳转

- [ ] 5. 异步进度统一
  - [ ] 5.1 新建 AsyncJobProgress.vue（统一进度条 + 状态文案）
  - [ ] 5.2 import/word-export/archive/generate 接入

- [ ] 6. 错误处理 component 层扩扫（proposal 第七章 P2-2 补漏）
  - [ ] 6.1 `audit-elmessage-error.mjs` 扩展扫描范围到 `components/workpaper/`
    - _Requirements: 6.1_
  - [ ] 6.2 修复 ProcedureTrimmingPanel 3 处裸 ElMessage.error → handleApiError
    - _Requirements: 6.2_
  - [ ] 6.3 修复 WorkpaperAuditNav / SideStandardsTab 手工拼接 error.value 模式
    - _Requirements: 6.3_

- [ ] 7. quality_score 纳入门禁 + 指标口径统一（proposal 第二十四章增量 1/3 补漏）
  - [ ] 7.1 提交复核门禁纳入"质量分 < 阈值警告"
    - _Requirements: 7.1_
  - [ ] 7.2 PM 看板按质量分排序
    - _Requirements: 7.2_
  - [ ] 7.3 统一 completion_rate 计算口径（当前 7+ 处各算各的）
    - _Requirements: 7.3_

- [ ] 8. 审计轨迹前端可视化（proposal 第二十二章补漏）
  - [ ] 8.1 cell history 时间线组件（点单元格看"谁何时改了什么"）
    - _Requirements: 8.1_
  - [ ] 8.2 接入 wp_audit_trail_service.get_cell_history
    - _Requirements: 8.2_

- [ ] 9. 验收
  - [ ]* vitest 0 fail / vue-tsc 0 errors
  - [ ]* Playwright：侧栏 4 组可见 + 横幅折叠 + 引导弹出

## 说明
- 纯前端体验提升，不改业务逻辑
- 约 1-2 周
