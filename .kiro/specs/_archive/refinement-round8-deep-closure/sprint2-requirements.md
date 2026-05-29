# Sprint 2（P1）需求文档 — 核心角色功能深化

## 目标

3 周内完成 14 项中风险改进，覆盖 5 角色核心功能深化 + 联动断点修复 + 权限/枚举/表单规范。

## 需求清单

### R8-S2-01：WorkpaperSidePanel 统一右栏（审计助理核心）
- 新建 `components/workpaper/WorkpaperSidePanel.vue`（7 Tab 容器）
- Tab：🤖 AI / 📋 程序 / 📜 上年 / 📎 附件 / 📚 知识库 / 💬 批注 / 🔍 自检
- WorkpaperEditor 右栏替换为 WorkpaperSidePanel
- 每 Tab 懒加载（v-if="active === 'xxx'"），首次点击才拉数据
- 自检 Tab 调 `GET /api/projects/{pid}/fine-checks/workpaper/{wp_id}`，失败项可点击"定位"

### R8-S2-02：自检结果进 WorkpaperEditor
- SidePanel "🔍 自检" Tab 展示 fine-check 结果
- 失败项数量显示在 Tab 标签 badge
- 点击失败项"定位"按钮跳到 Univer 指定单元格
- 未通过自检项 > 0 时，"提交复核"按钮 tooltip 提示

### R8-S2-03：Stale 三态跨视图显示（联动断点 2）
- 新建 `composables/useStaleStatus.ts`
- ReportView / DisclosureEditor / AuditReportEditor 顶部加 stale 提示横幅
- 横幅文案："上游数据已变更（{changedAt}），建议点击重算 →"
- 点击"重算"调 `POST /api/projects/{pid}/trial-balance/recalc`
- 重算完成后横幅消失

### R8-S2-04：ShadowCompareRow 组件 + 5 Tab 接入（EQCR 核心）
- 新建 `components/eqcr/ShadowCompareRow.vue`
- Props：label / teamValue / shadowValue / unit / thresholdPct / verdict
- 差异超阈值标红
- 判断写入 EqcrVerdict 表
- EqcrProjectView 5 判断 Tab（materiality/estimate/related_party/going_concern/opinion_type）各放 1-3 个 ShadowCompareRow

### R8-S2-05：EQCR 备忘录版本历史 + Word 导出
- `eqcr_memo` JSONB 扩展 `history` 数组（最多 10 版）
- 每次保存前把旧 sections 压入 history
- EqcrProjectView memo Tab 增加"版本"下拉
- 新建后端 `GET /api/eqcr/projects/{pid}/memo/export?format=docx`
- 前端 memo Tab 增加"📄 导出 Word"按钮

### R8-S2-06：合伙人签字决策面板
- 新建 `views/PartnerSignDecision.vue`
- 路由 `/partner/sign-decision/:projectId/:year`（partner/admin 可见）
- 三栏布局：左=GateReadinessPanel / 中=报告 PDF 预览 / 右=风险摘要
- 中栏 PDF 预览：优先用已有 PDF 导出端点 iframe 渲染；若无则降级为 AuditReportEditor 只读模式嵌入
- 底栏操作：回退到复核 / 签字 / 查看历史
- 签字按钮走 confirmSignature（必须输入客户名）

### R8-S2-07：风险摘要端点
- 新建后端 `GET /api/projects/{pid}/risk-summary`
- 返回：high_findings / unresolved_comments / material_misstatements / unconverted_rejected_aje / ai_flags / budget_overrun / sla_breached / going_concern_flag
- 任一高危项非空时，签字按钮 disabled + tooltip 提示原因
- PartnerSignDecision 右栏展示

### R8-S2-08：ManagerDashboard 四 Tab 升级
- 升级 `views/ManagerDashboard.vue` 为 4 Tab：项目矩阵 / 团队成本 / 客户承诺 / 异常告警
- 项目矩阵：行=我管辖项目，列=进度%/底稿数/逾期/工时/风险/签字阶段
- 异常告警：聚合预算超支/逾期底稿/卡住导入/签字阻塞/质控未整改
- 后端新建 `GET /api/manager/projects/matrix` + `GET /api/manager/alerts`

### R8-S2-09：QcHub.vue 新建（质控核心）
- 新建 `views/qc/QcHub.vue`
- 路由 `/qc` 默认命中
- 顶部卡片组：本月应抽查/逾期整改/高风险客户/规则预警
- 主工作区 4 Tab：待抽查 / 抽查中 / 整改中 / 已完结
- 侧边快捷入口：规则管理/案例库/年报/客户趋势
- QCDashboard.vue 降级为 ProjectDashboard 内 Tab "质控"
- 新建 `components/qc/QCDashboardEmbed.vue`（从 QCDashboard 抽取核心内容，去掉 GtPageHeader，嵌入模式）

### R8-S2-10：v-permission 关键按钮铺设
- 盘点 15+ 个危险操作按钮（见 v2 §8.6.2 清单）
- 逐一加 v-permission
- 后端 `GET /api/users/me` 确认返回 permissions 字段
- ROLE_PERMISSIONS 补齐新增权限字符串
- 脚本 `scripts/find-missing-v-permission.mjs` 输出未加权限的危险按钮

### R8-S2-11：常量 statusEnum.ts + 表单 formRules.ts
- 新建 `constants/statusEnum.ts`（WP_STATUS/REPORT_STATUS/ADJUSTMENT_STATUS/PROJECT_STATUS 等 18 套）
- 替换 `.vue` 中 `=== 'draft'` 等硬编码字符串比较（高频 10 处先做）
- 新建 `utils/formRules.ts`（required/amount/clientName/accountCode/email/phone/ratio）
- 3 个高频表单接入 formRules（ProjectWizard/StaffManagement/UserManagement）

### R8-S2-12：附注行 → 底稿穿透（联动断点 3）
- 新建后端 `GET /api/notes/{project_id}/{year}/{note_section}/row/{row_code}/related-workpapers`
- DisclosureEditor 右键菜单增加"查看相关底稿"
- 单底稿直接跳转 WorkpaperEditor
- 多底稿弹列表选择

### R8-S2-13：重要性变更 → 错报阈值即时重算（联动断点 4）
- Misstatements.vue 订阅 eventBus `materiality:changed` 事件
- 收到事件后重新拉取重要性阈值 + 刷新列表
- GateReadinessPanel 订阅 `materiality:changed` 自动 revalidate
- 后端新建 `POST /api/projects/{pid}/misstatements/recheck-threshold`

### R8-S2-14：未保存提醒 + beforeunload
- WorkpaperEditor `onBeforeRouteLeave` 调 `confirmLeave('底稿')`
- 注册 `beforeunload` listener
- DisclosureEditor / AuditReportEditor 同样接入
- useWorkpaperAutoSave 暴露 `isDirty` ref

## 验收标准

- [ ] WorkpaperEditor 右栏 7 Tab 切换流畅
- [ ] 自检失败项点击"定位"跳 Univer 单元格
- [ ] ReportView/DisclosureEditor 有 stale 横幅
- [ ] EQCR 5 Tab 有 ShadowCompareRow，差异超阈值标红
- [ ] 备忘录可切换历史版本 + 导出 Word
- [ ] PartnerSignDecision 单页完成签字判断
- [ ] 风险摘要有红项时签字按钮 disabled
- [ ] ManagerDashboard 4 Tab 可用
- [ ] QcHub 4 Tab 可用
- [ ] v-permission 接入 ≥ 15 个视图
- [ ] 附注行右键可查看相关底稿
- [ ] 改重要性 → Misstatements 阈值线即时移动
- [ ] 关闭浏览器有未保存时弹 confirmLeave
