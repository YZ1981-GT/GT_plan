# Phase 12: 底稿深度开发 - 实施任务

## 阶段0: 规格硬化与实施前置

- [x] 1. 数据库迁移：新增 wp_ai_generations 表
  - [x] 1.1 创建 WpAiGeneration ORM 模型（id, wp_id, prompt_version, model, input_hash, output_text, output_structured, status, created_by, created_at, confirmed_by, confirmed_at）
  - [x] 1.2 创建 Alembic 迁移脚本 001_add_wp_ai_generations.sql
  - [x] 1.3 添加索引 idx_wp_ai_generations_wp(wp_id, created_at DESC)

- [x] 2. 数据库迁移：新增 background_jobs / background_job_items 表
  - [x] 2.1 创建 BackgroundJob ORM 模型（id, project_id, job_type, status, payload, progress_total, progress_done, failed_count, initiated_by, created_at, updated_at）
  - [x] 2.2 创建 BackgroundJobItem ORM 模型（id, job_id, wp_id, status, error_message, finished_at）
  - [x] 2.3 创建迁移脚本 002_add_background_jobs.sql
  - [x] 2.4 添加索引 idx_background_jobs_project 和 idx_background_job_items_job

- [x] 3. 数据库迁移：working_papers 表新增状态字段
  - [x] 3.1 新增 workflow_status VARCHAR(30) DEFAULT 'draft'
  - [x] 3.2 新增 explanation_status VARCHAR(30) DEFAULT 'not_started'
  - [x] 3.3 新增 consistency_status VARCHAR(30) DEFAULT 'unknown'
  - [x] 3.4 新增 last_parsed_sync_at TIMESTAMP
  - [x] 3.5 新增 partner_reviewed_at TIMESTAMP 和 partner_reviewed_by UUID
  - [x] 3.6 创建迁移脚本 003_alter_working_papers_status.sql

- [x] 4. Pydantic Schema 定义
  - [x] 4.1 创建 wp_explanation_schemas.py（GenerateDraftResponse, ConfirmDraftRequest, RefineDraftRequest, AiGenerationRecord）
  - [x] 4.2 创建 background_job_schemas.py（JobCreateResponse, JobStatusResponse, JobItemResponse, JobRetryResponse）
  - [x] 4.3 扩展 workpaper_schemas.py 新增 workflow_status / explanation_status / consistency_status 字段

## 阶段1: P0问题修复

- [x] 5. P0-1: prefill_stale 前端通知
  - [x] 5.1 WorkpaperList.vue 底稿列表添加 stale 橙色⚠图标（prefill_stale=true 时显示）
  - [x] 5.2 WorkpaperEditor.vue 编辑器顶部添加黄色过期横幅（含刷新按钮调用 POST /prefill/{wp_id}）
  - [x] 5.3 WorkpaperWorkbench.vue 工作台树节点添加 stale 标记图标

- [x] 6. P0-2: WOPI 只读浏览模式
  - [x] 6.1 wopi_service.py check_file_info 增强：非锁持有者返回 ReadOnly=True + ReadOnlyReason
  - [x] 6.2 wopi_service.py check_file_info 增强：复核人角色始终返回只读
  - [x] 6.3 WorkpaperEditor.vue 只读模式 UI 适配（隐藏编辑工具栏，显示只读原因提示）

- [x] 7. P0-3: parse_workpaper_real 审计说明提取
  - [x] 7.1 prefill_engine.py 新增审计说明提取逻辑：识别"审计说明"/"审计结论"/"执行情况"等关键词
  - [x] 7.2 提取关键词后连续非空单元格文本，写入 parsed_data.audit_explanation

- [x] 8. P0-4: 底稿列表角色裁剪
  - [x] 8.1 WorkpaperList.vue 前端配合 scope_cycles 参数过滤底稿列表
  - [x] 8.2 working_paper.py 验证后端 list_workpapers 的 scope_cycles 过滤已生效

## 阶段2: MVP核心闭环

- [x] 9. P1-1 后端：审计说明智能生成服务
  - [x] 9.1 创建 backend/app/services/wp_explanation_service.py（WpExplanationService 类）
  - [x] 9.2 实现 generate_draft 方法：数据采集（TB+调整+科目+TSJ+抽样）→ Prompt构建 → LLM调用 → 返回草稿+generation_id+prompt_version
  - [x] 9.3 实现 confirm_draft 方法：写回底稿工作簿 → 刷新 parsed_data.audit_explanation → 更新 explanation_status → 记录 confirmed_by/confirmed_at
  - [x] 9.4 实现 refine_draft 方法：基于用户修改和反馈优化草稿
  - [x] 9.5 实现 wp_ai_generations 表写入（每次生成记录 generation_id, prompt_version, model, status）
  - [x] 9.6 创建 backend/app/routers/wp_explanation.py 路由（POST generate-explanation, POST confirm-explanation, POST refine-explanation）
  - [x] 9.7 注册路由到 main.py / router_registry.py

- [x] 10. P1-1 前端：审计说明交互面板
  - [x] 10.1 WorkpaperWorkbench.vue 新增审计说明生成面板（右栏或独立区域）
  - [x] 10.2 实现 SSE 流式输出草稿展示（首字节<3秒目标）
  - [x] 10.3 集成 TipTap 编辑器用于草稿编辑
  - [x] 10.4 实现采纳/重新生成/手动编写三种模式切换
  - [x] 10.5 采纳后调用 confirm-explanation API，展示写回状态（syncing → synced / sync_failed）

- [x] 11. P1-2 前端：复核工作台组件
  - [x] 11.1 创建 audit-platform/frontend/src/views/ReviewWorkstation.vue 三栏布局
  - [x] 11.2 左栏：待复核队列列表（按提交时间排序，区分首次/退回重提交）
  - [x] 11.3 中栏：底稿只读预览（关键数据标红：审定数、差异、AI生成内容）
  - [x] 11.4 右栏：复核操作区（AI预审结果 + 复核意见输入 + 通过/退回按钮）
  - [x] 11.5 快捷键支持：Ctrl+Enter 通过，Ctrl+Shift+Enter 退回
  - [x] 11.6 注册路由 /projects/:projectId/review-workstation

- [x] 12. P1-2 后端：AI预审服务
  - [x] 12.1 wp_ai_service.py 新增 review_workpaper_content 方法（数据一致性+说明完整性+结论合理性三项检查）
  - [x] 12.2 创建 POST /api/projects/{id}/wp-ai/{wp_id}/review-content API 端点
  - [x] 12.3 返回 issues 列表（description, severity: warning/blocking, suggested_action）

- [x] 13. P1-4: 数据一致性监控
  - [x] 13.1 创建 audit-platform/frontend/src/components/workpaper/DataConsistencyMonitor.vue
  - [x] 13.2 实现一致性矩阵：底稿审定数 vs 试算表审定数，差异>0.01元标红
  - [x] 13.3 实现重新预填按钮（调用 POST /prefill/{wp_id}）
  - [x] 13.4 保留人工填写的差异原因说明（不被刷新覆盖）

- [x] 14. P1-6: 内容级QC规则
  - [x] 14.1 qc_engine.py 新增 QC-15 审计说明完整性规则（parsed_data.audit_explanation 非空且≥50字，explanation_status=synced，包含程序+发现+结论）
  - [x] 14.2 qc_engine.py 新增 QC-16 数据引用一致性规则（parsed_data.audited_amount vs trial_balance.audited_amount，误差>0.01元阻断）
  - [x] 14.3 qc_engine.py 新增 QC-17 附件证据充分性规则（重要性以上科目底稿至少关联1个附件）
  - [x] 14.4 qc_engine.py 新增 QC-18 交叉引用完整性规则（parsed_data.cross_refs 引用的底稿编号存在且状态≠draft）

- [x] 15. P1-7: 签字前底稿专项检查
  - [x] 15.1 partner_service.py 新增 check_workpaper_readiness 方法（5项检查：复核状态/QC通过/说明非空/数据一致/证据充分）
  - [x] 15.2 创建 POST /api/projects/{id}/partner/workpaper-readiness API 端点
  - [x] 15.3 PartnerDashboard.vue 新增签字前检查清单弹窗（未通过项列出明细，点击跳转）

## 阶段2.5: 后台任务与可用性基线

- [x] 16. AI生成失败降级
  - [x] 16.1 创建 backend/app/services/availability_fallback_service.py（AvailabilityFallbackService 类）
  - [x] 16.2 实现 handle_llm_failure：检测 vLLM 服务状态，设置 Redis 降级标志 llm_fallback=true，每30秒检测恢复
  - [x] 16.3 WorkpaperWorkbench.vue 前端降级提示："AI服务暂不可用"+ 手动编写模式切换

- [x] 17. 后台任务编排服务
  - [x] 17.1 创建 backend/app/services/background_job_service.py（BackgroundJobService 类）
  - [x] 17.2 实现 create_job：创建 background_jobs + background_job_items 记录，返回 job_id
  - [x] 17.3 实现 run_job：按 wp 粒度执行，记录成功/失败，结束后置为 succeeded/partial_failed/failed
  - [x] 17.4 实现 retry_job：仅重试失败项，保留原始审计轨迹
  - [x] 17.5 实现 get_job_status / get_job_stream（SSE 事件流）
  - [x] 17.6 创建 backend/app/routers/background_jobs.py 路由（GET /jobs/{job_id}, GET /jobs/{job_id}/events, POST /jobs/{job_id}/retry）
  - [x] 17.7 注册路由到 router_registry.py

- [x] 18. 网络中断与页面刷新恢复
  - [x] 18.1 前端 utils/offline_storage.ts：IndexedDB 本地暂存未同步数据（<10MB 限制）
  - [x] 18.2 后端 POST /api/sync-pending-data 端点：接收前端暂存数据，冲突检测（版本号比对），无冲突合并保存

- [x] 19. 底稿锁定冲突处理
  - [x] 19.1 WorkpaperEditor.vue 锁冲突提示 UI："其他用户正在编辑"+ "只读浏览"/"稍后提醒"两个选项
  - [x] 19.2 "稍后提醒"定时器（30秒后检测锁释放，自动通知用户）

## 阶段3: AI评估与灰度上线

- [x] 20. Prompt版本固化
  - [x] 20.1 wp_explanation_service.py 中 prompt_version 基线固化为 'wp_expl_v1'
  - [x] 20.2 创建历史底稿 explanation_status / last_parsed_sync_at 补录迁移脚本 008_backfill_explanation_status.sql

- [x] 21. 灰度上线开关
  - [x] 21.1 feature_flags.py 新增 'wp_ai_explanation' 功能开关（默认关闭，按项目/角色控制）
  - [x] 21.2 前端审计说明生成面板根据功能开关显示/隐藏
  - [x] 21.3 后端 generate-explanation API 检查功能开关，关闭时返回 403

## 阶段4: 角色化体验优化与增强能力

- [x] 22. P1-3: 进度总览面板
  - [x] 22.1 ProjectProgressBoard.vue 底稿 Tab 增强：进度矩阵（循环×状态）
  - [x] 22.2 关键指标卡片（完成率/待复核/逾期/stale）
  - [x] 22.3 甘特图实现（编制周期可视化，ECharts）
  - [x] 22.4 人员负荷视图（识别负荷不均）

- [x] 23. P1-5: 批量操作面板
  - [x] 23.1 WorkpaperList.vue 新增批量模式 checkbox（全选/循环选/状态选）
  - [x] 23.2 批量操作菜单（分配/刷新/生成说明/提交复核/下载）
  - [x] 23.3 创建 backend/app/routers/wp_batch.py 5个批量API端点（assign/prefill/batch-explanation/submit-review/download-pack）
  - [x] 23.4 批量API统一返回 job_id，集成 BackgroundJobService
  - [x] 23.5 前端 job_id 状态查询/失败重试/进度订阅（SSE）集成
  - [x] 23.6 注册 wp_batch 路由到 router_registry.py

- [x] 24. P2-1: 风险底稿聚焦视图
  - [x] 24.1 partner_service.py 新增 get_risk_workpapers 方法（筛选：金额>重要性/有AJE/QC阻断/被退回/prefill_stale）
  - [x] 24.2 创建 GET /api/projects/{id}/partner/risk-workpapers API 端点
  - [x] 24.3 PartnerDashboard.vue 新增风险底稿列表展示

- [x] 25. P2-2: 独立抽查工作台
  - [x] 25.1 创建 backend/app/services/qc_sampling_service.py（智能抽样算法：风险分层+循环均匀+编制人覆盖）
  - [x] 25.2 QCDashboard.vue 新增抽查 Tab（抽查清单交互+逐项确认）
  - [x] 25.3 抽查报告生成（结构化 HTML/Markdown 草稿）

- [x] 26. P2-3: 证据链可视化
  - [x] 26.1 创建 backend/app/services/attachment_evidence_chain_service.py（get_wp_attachments, quick_attach, generate_evidence_graph, get_attachment_timeline）
  - [x] 26.2 创建证据链 API 路由（GET attachments, POST quick-attach, GET evidence-graph, GET attachment-timeline）
  - [x] 26.3 WorkpaperWorkbench.vue 新增关联附件列表 + 快速关联 + 证据图谱（ECharts 力导向图）

- [x] 27. P2-4: 底稿推荐反馈闭环
  - [x] 27.1 数据库迁移：创建 wp_recommendation_feedback 表 + 索引
  - [x] 27.2 创建 backend/app/services/wp_mapping_feedback_service.py（record_recommendation, record_feedback, get_recommend_stats, optimize_recommend_rules）
  - [x] 27.3 创建反馈 API 路由（POST recommend-feedback, GET recommend-stats）

- [x] 28. P2-5: 底稿编制智能引导
  - [x] 28.1 创建 backend/app/services/wp_guidance_service.py（get_guidance 按底稿类型返回引导, check_procedure_progress 检查程序执行状态）
  - [x] 28.2 创建引导 API 路由（GET guidance, GET procedure-check）
  - [x] 28.3 WorkpaperWorkbench.vue 新增引导面板 UI

- [x] 29. P2-6: 数据提取可视化增强
  - [x] 29.1 创建 backend/app/services/wp_visualization_service.py（get_formula_cells 从 parsed_data 缓存读取, get_cell_data_source, compare_refresh_diff, generate_diff_summary）
  - [x] 29.2 创建可视化 API 路由（GET formula-cells, GET cell-data-source, POST compare-refresh）
  - [x] 29.3 WorkpaperEditor.vue 公式单元格高亮 + hover 显示来源 + 刷新差异对比弹窗

- [x] 30. 底稿对话上下文增强
  - [x] 30.1 wp_chat_service.py 增强 build_enhanced_context（注入底稿数据+关联科目+审计程序+QC结果+复核意见+TSJ要点）
  - [x] 30.2 实现 extract_suggestion 从 LLM 回复提取数值建议（cell_ref + suggested_value + reason）

- [x] 31. ONLYOFFICE插件部署验证
  - [x] 31.1 创建 backend/scripts/check_onlyoffice_plugins.py（检查容器内插件目录+config.json+XHR可达性）
  - [x] 31.2 audit-formula 插件增强：新增 EXPLAIN() 和 REFRESH() 函数，错误提示本地化为中文

## 阶段5: 延伸功能与模板管理

- [x] 32. 模板热更新服务
  - [x] 32.1 创建 backend/app/services/wp_template_migration_service.py（compare_versions 新旧模板差异对比, batch_upgrade 批量升级保留用户数据）
  - [x] 32.2 创建模板热更新 API 路由（POST compare, POST batch-upgrade）

- [x] 33. 底稿离线工作包
  - [x] 33.1 创建 backend/app/services/wp_offline_pack_service.py（pack_workpapers 整循环打包ZIP+manifest, unpack_and_sync 回传同步+冲突检测）
  - [x] 33.2 创建离线工作包 API 路由（POST download-pack, POST upload-pack）

- [x] 34. 底稿编制时间统计
  - [x] 34.1 数据库迁移：创建 wp_edit_sessions 表（id, wp_id, user_id, started_at, ended_at, duration_seconds, source）
  - [x] 34.2 wopi_service.py 增强：WOPI lock/unlock 时自动采集编辑时间写入 wp_edit_sessions
  - [x] 34.3 创建编辑时间统计 API（GET /working-papers/{wp_id}/edit-time）

- [x] 35. 底稿间数据穿透
  - [x] 35.1 WorkpaperWorkbench.vue 交叉引用可点击跳转（parsed_data.cross_refs 中的底稿编号渲染为链接）
  - [x] 35.2 WP() 公式 hover 提示（显示引用底稿名称和当前值）
  - [x] 35.3 后端反向引用查询 API（GET /working-papers/{wp_id}/reverse-refs）

- [x] 36. 审计程序与底稿双向绑定
  - [x] 36.1 数据库迁移：procedure_instances 新增 working_paper_id UUID FK
  - [x] 36.2 procedure_service.py 增强：程序裁剪时联动底稿状态（skip→底稿标记不适用）
  - [x] 36.3 working_paper_service.py 增强：底稿完成时联动程序状态（edit_complete→程序标记已执行）

- [x] 37. 归档导出标准目录包
  - [x] 37.1 定义致同标准归档目录结构（按审计循环 B/C/D-N/A/S 分目录）
  - [x] 37.2 wp_storage_service.py 增强：生成底稿索引表（编号/名称/编制人/复核人/状态/页数）
  - [x] 37.3 调整汇总表导出（AJE/RJE 汇总 Excel）

## 测试与验收

- [x] 38. 单元测试
  - [x] 38.1 wp_explanation_service 测试（generate_draft/confirm_draft/refine_draft，至少15个用例）
  - [x] 38.2 qc_engine QC-15~18 测试（每条规则通过/阻断各1个用例，至少8个）
  - [x] 38.3 background_job_service 测试（create/run/retry/status，至少10个用例）
  - [x] 38.4 partner_service workpaper_readiness 测试（5项检查各通过/失败，至少10个用例）
  - [x] 38.5 availability_fallback_service 测试（降级/恢复，至少4个用例）

- [x] 39. 集成测试
  - [x] 39.1 写回同步场景：AI草稿确认 → 写回工作簿 → 刷新 parsed_data → explanation_status=synced
  - [x] 39.2 QC门禁场景：explanation_status≠synced 时提交复核被阻断
  - [x] 39.3 后台任务场景：创建 job → 执行 → 部分失败 → 重试失败项 → 全部成功
