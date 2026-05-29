# 全局建议书剩余 27 项 — 任务清单

## Sprint 0：部分实现补齐 4 项（3.5 天）

- [x] 0.1 **M-1** 多项目甘特图：ManagerDashboard 新增 ECharts gantt 组件（横轴时间/纵轴项目，按循环着色），数据源复用 `/api/manager/projects/matrix` 端点（实际复用 /api/dashboard/manager/projects-overview）
- [x] 0.2 **M-5** 工时审批关联底稿进度：WorkHourApprovalTab 表格新增"底稿完成度"列，后端 workhour_approval 端点 JOIN working_paper 统计 assignee 的 wp 完成率
- [x] 0.3 **G-1** GtPageHeader 使用审查：grep 全仓库 `GtPageHeader` 使用情况，简单 CRUD 页面（人员/知识库/附件等）替换为白色简洁工具栏
- [x] 0.4 **D-1** Univer 大底稿懒加载：WorkpaperEditor 加载 parsed_data 时仅传入 active sheet 数据，切换 sheet 时按需 fetch 对应 sheet cells（减少首屏 JSON 体积）

## Sprint 1：快修 5 项（3 天）

- [x] 1.1 **D-2** 编辑模式过渡动画：useEditMode 切换时增加 300ms opacity transition（CSS class `gt-edit-transition`），WorkpaperEditor / DisclosureEditor / AuditReportEditor 三处接入
- [x] 1.2 **D-5** 字号切换后列宽自适应：displayPrefs watch fontSize 变化时 `nextTick(() => document.querySelectorAll('.el-table').forEach(t => t.__vue__?.doLayout?.()))` 全局生效
- [x] 1.3 **W-4** 加班工时自动识别：WorkHour 模型/schema 新增 `is_overtime: bool`（hours > 8 自动计算），WorkHoursPage 加班行高亮橙色背景
- [x] 1.4 **A-5** 底稿内计时器：WorkpaperSidePanel 新增 SideTimerTab.vue（开始/暂停/停止 + localStorage 持久化 + 保存底稿时自动 POST /api/workhour-entries）
- [x] 1.5 **DT-3** 枚举管理 UI：SystemSettings.vue 新增"枚举管理"Tab，el-table CRUD 调用 `/api/system/dicts`（后端已有，仅缺前端界面）

## Sprint 2：联动增强 3 项（6 天）

- [x] 2.1 **L-2** 后端 `POST /api/projects/{pid}/adjustments/preview-impact`：模拟调整分录影响（不写 DB），返回受影响报表行 + 底稿列表
- [x] 2.2 **L-2** 前端 `AdjustmentImpactPreview.vue`：嵌入调整分录编辑弹窗右侧，debounce 500ms 调用 preview-impact
- [x] 2.3 **L-3** 后端 prefill_engine 执行时记录 TB 快照到 `working_paper.prefill_tb_snapshot` JSONB
- [x] 2.4 **L-3** 前端 PrefillDiffPanel 增加"与上次快照对比"列，差异 > 0 标记 stale
- [x] 2.5 **K-2** 后端 `GET /api/knowledge/tsj/{cycle_name}` 返回对应循环的审计复核提示词 Markdown
- [x] 2.6 **K-2** 前端 WorkpaperSidePanel 新增 SideStandardsTab.vue（第 11 个 Tab "准则"），按 wp_code 前缀匹配加载

## Sprint 3：搜索+导出+附件 4 项（6 天）

- [x] 3.1 **S-2** 优先接入 useTableSearch 到 10 个高频表格页（WorkpaperList/TrialBalance/Adjustments/Misstatements/Projects/StaffManagement/WorkHoursPage/ReviewWorkbench/KnowledgeBase/AttachmentHub）
- [x] 3.2 **C-2** useExcelIO 导出增加样式模板：仿宋_GB2312 中文 + Arial Narrow 数字 + 三线表边框 + 列宽自适应
- [x] 3.3 **C-3** 批量导出增加 SSE 进度推送：后端异步任务 + `export.progress` 事件 + 完成后返回 ZIP 下载链接
- [x] 3.4 **AT-1** 底稿编辑器内拖拽上传附件：WorkpaperEditor 增加 drop zone overlay，上传后自动关联当前 wp_id + active sheet

## Sprint 4：深度功能 3 项（7 天）

- [x] 4.1 **L-4** 附注公式引擎扩展：支持 `=TB()`/`=REPORT()`/`=WP()` 三源自动提数，覆盖率目标 ≥ 80%（当前约 50%）
- [x] 4.2 **K-4** LLMService 输出格式扩展：新增 reasoning/references/data_sources/confidence 字段，前端 LLM 输出区增加可折叠"推理依据"面板
- [x] 4.3 **Y-2** ProjectWizard 新增"继承配置"步骤：7 个 checkbox（科目表/映射/模板/人员/复核链/VR/重要性），后端 clone-from 端点增加 options 参数

## Sprint 5：重型功能 4 项 + 运维治理 4 项（8 天）

- [x] 5.1 **S-3** 高级查询构建器：可视化条件拖拽 + SQL 预览 + 结果导出（新建 AdvancedQueryBuilder.vue + 后端 /api/query/execute）
- [x] 5.2 **AT-2** Office 文件在线预览：后端 LibreOffice 转 PDF 端点 + 前端 iframe 嵌入预览（需 Docker 增加 libreoffice-headless 层）
- [x] 5.3 **AT-3** 附件版本管理：attachment 表增加 version 字段 + 上传同名文件时保留历史版本 + 前端版本列表+回滚按钮
- [x] 5.4 **S-4** 历史版本搜索：版本对比页面增加搜索框，支持在历史版本 parsed_data 中搜索特定值
- [x] 5.5 **UI-8** 微交互增强：gt-polish.css 增加按钮 active 缩放 0.95 + 拖拽时元素浮起阴影 + 状态标签切换 flip 动画（CSS only，无 JS）
- [x] 5.6 **MT-5** 后端服务依赖图：新建 `scripts/gen_service_deps.py`（基于 import 分析生成 mermaid 图），输出 `docs/SERVICE_DEPENDENCY.md`
- [x] 5.7 **MT-8** 日志集中查看：后端 structlog JSON 格式统一输出到文件 + SystemSettings 新增"日志查看"Tab（admin only，读取最近 1000 行）
- [x] 5.8 **MT-9** 配置中心文档：新建 `docs/CONFIGURATION_REFERENCE.md`，列出所有 .env / config.py / 前端 env 可配置项 + 默认值 + 影响范围

## 验收标准

- 每个 Sprint 完成后跑 pytest + vitest 零新增失败
- Sprint 0-4 完成后建议书覆盖率 ≥ 95%
- Sprint 5 完成后建议书覆盖率 = 100%（不含外部依赖 K-1/W-3）
- 每项功能至少 1 个单测覆盖核心逻辑
- 总计 27 项功能 / 30 个实施 task / 6 Sprint / ~33.5 天单人工时
