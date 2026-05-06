# Refinement Round 4 — 任务清单

按 README 约定：一轮 ≤ 20 任务，分 **2 个 Sprint**。前置依赖：R1 需求 2 的 `ReviewRecord` 单元格红点机制。与 R3 可并行实施（相互独立）。

## Sprint 1：编辑器三栏 + AI + 程序要求（需求 1~3, 6）

- [ ] 1. 后端：程序要求聚合 API
  - `GET /api/projects/{pid}/workpapers/{wp_id}/requirements`
  - 聚合 `wp_manuals + procedures + continuous_audit.prior_year_summary`
  - _需求_ 1

- [ ] 2. 前端：ProgramRequirementsSidebar 组件
  - `src/components/workpaper/ProgramRequirementsSidebar.vue`
  - 三数据源合并展示 + 折叠
  - URL query `?from_procedure=xxx` 时高亮对应程序条目
  - 程序条目"标记为已完成"调 `updateProcedureTrim`
  - 折叠状态存 `localStorage.wp_sidebar_collapsed`
  - _需求_ 1

- [ ] 3. 前端：AiAssistantSidebar 组件
  - `src/components/workpaper/AiAssistantSidebar.vue`
  - 嵌入现有 `AIChatPanel.vue`
  - 自动传 `wp_id/project_id/selected_cell/procedure_code` 上下文
  - 3 快捷 prompt 按钮
  - "插入到结论区"一键写入 `parsed_data.conclusion`
  - 宽度可拖拽（`localStorage.ai_sidebar_width`）
  - _需求_ 2

- [ ] 4. 后端：AI 脱敏前置过滤
  - `wp_chat_service` 调用前先过 `export_mask_service.mask_context(cell_context)`
  - 替换金额/客户名为 `[amount] / [client]` 占位
  - 保留业务语义让 LLM 理解
  - _需求_ 2（风险缓解）

- [ ] 5. 前端：SmartTipList 可点击定位
  - `src/components/workpaper/SmartTipList.vue` 替代现有单行 smartTip
  - 聚合 badge "⚠ N"，点击展开下拉
  - 每条 finding 点击调 Univer API 滚动到 `cell_reference` + 闪烁 3 次
  - 按 severity 染色（blocking 红 / warning 黄 / info 蓝）
  - _需求_ 3

- [ ] 6. 前端：WorkpaperEditor 三栏重构
  - `src/views/WorkpaperEditor.vue` 改为三栏（左程序 + 中 Univer + 右 AI）
  - 两侧栏可独立折叠
  - 单元格红点渲染（读 `ReviewRecord where status='open'`，R1 落地的真源）
  - 点击红点弹 popover 显示意见全文
  - _需求_ 1, 2, 3

- [ ] 7. 前端：MyProcedureTasks 跳转带上下文
  - `openWP` 函数 `router.push({ query: { from_procedure: row.procedure_code } })`
  - WorkpaperEditor 在 URL 读 query 传给 ProgramRequirementsSidebar
  - _需求_ 1

- [ ] 8. 前端：工作流引导三处增强
  - `useWorkflowGuide.ts` 补 `first_login / first_open_workpaper / first_submit_review` 三 key
  - 首次登录、首次打开底稿、首次提交复核时触发
  - 设置页新增"重置所有引导"按钮
  - _需求_ 6

- [ ] Sprint 1 验收
  - 集成测试：`test_workpaper_editor_sidebar.py`（程序要求 + AI + 红点）
  - UAT：requirements.md UAT 第 1/5/8 条走完

## Sprint 2：上年对比 + 穿透 + 附件 + 移动端 + 时间线（需求 4, 5, 7~10）

- [ ] 9. 后端：上年底稿 API
  - `GET /api/projects/{pid}/workpapers/{wp_id}/prior-year`
  - 复用 `continuous_audit_service.get_prior_year_workpaper`
  - 无对应返回 404
  - _需求_ 4

- [ ] 10. 前端：PriorYearCompareDrawer 抽屉
  - `src/components/workpaper/PriorYearCompareDrawer.vue`
  - 双栏对比（当前 / 上年）只读 Univer
  - "复制上年结论到今年"按钮
  - 记 `audit_logger_enhanced` 事件 `workpaper_prior_year_viewed`
  - `WorkpaperEditor` 工具栏仅续审项目显示"📜 对比上年"按钮
  - _需求_ 4

- [ ] 11. 后端：按金额穿透端点
  - `GET /api/projects/{pid}/ledger/penetrate-by-amount`
  - 四策略匹配（exact / tolerance / code+amount / summary_keyword）
  - 结果超 200 条截断提示
  - 性能 P95 < 2s（用现有索引）
  - _需求_ 5

- [ ] 12. 前端：LedgerPenetrateDrawer
  - `src/components/workpaper/LedgerPenetrateDrawer.vue`
  - 按策略层级展示结果
  - "导出穿透结果到附件"调 `attachment_service.upload` 附到当前底稿
  - Univer 右键菜单注册"🔍 穿透序时账"，金额单元格可见
  - _需求_ 5

- [ ] 13. 后端：预填充 provenance 回写
  - `workpaper_fill_service.prefill` 填充时写 `parsed_data.cell_provenance`
  - supersede 策略：重填时覆盖，最多保留 1 次历史
  - _需求_ 7

- [ ] 14. 前端：CellProvenanceTooltip
  - `src/components/workpaper/CellProvenanceTooltip.vue`
  - 单元格 hover 显示来源 tooltip
  - 来源点击跳转（trial_balance → TrialBalance 页；prior_year → 抽屉；ledger → 穿透抽屉）
  - _需求_ 7

- [ ] 15. 后端：底稿 HTML 预览（移动端）
  - `GET /api/projects/{pid}/workpapers/{wp_id}/html`
  - 复用 `excel_html_converter`
  - 支持 `?mask=true` 脱敏
  - _需求_ 8

- [ ] 16. 前端：MobileWorkpaperEditor 改只读
  - 替换现有 el-empty 占位
  - 顶部 meta + HTML 预览 + 复核意见回复框
  - 移除"下载"按钮（大 xlsx 移动端体验差），改灰色"在电脑上编辑"提示
  - 路由 meta label 改"简化查看版"
  - _需求_ 8

- [ ] 17. 前端：AttachmentDropZone
  - `src/components/workpaper/AttachmentDropZone.vue`
  - `dragover/drop` 事件接收图片/PDF/Word
  - 上传成功后创建 `workpaper_attachment_link(wp_id, attachment_id, cell_ref, type='evidence')`
  - 单元格右上角 📎 图标（Univer decoration）
  - 20MB 上限 + 类型白名单
  - _需求_ 9

- [ ] 18. 前端：useFocusTracker + PersonalDashboard 时间线
  - `src/composables/useFocusTracker.ts` 纯 localStorage 实现（按周归档键 `focus_tracker_<weekStart>`）
  - `WorkpaperEditor` onMounted 调用追踪器
  - `PersonalDashboard.vue` 新增第四列"本周时间线"，读 localStorage
  - 两列展示"焦点时长（本地）"和"已填报（系统）"
  - 4 小时超时提示，可关闭
  - **无任何后端调用**（跨轮约束 8）
  - _需求_ 10

- [ ] Sprint 2 验收
  - 单元测试：按金额穿透四策略 12 用例 / useFocusTracker 按周归档 4 用例
  - 集成测试：`test_workpaper_editor_full.py`（对比上年 + 穿透 + 附件拖拽）
  - UAT：requirements.md UAT 第 2/3/4/6/7 条走完

## 完成标志

- 所有任务 `[x]`
- UAT 8 项有通过记录
- 单页面完成助理 80% 工作量（主观判定，UAT 第 1 条连续复核 10 张无反复切页）
- Round 4 关闭

## Sprint 3：协作锁 + OCR 填入（需求 11~12，新增）

5 个任务。

- [ ] 19. 后端：编辑软锁
  - 新建 `backend/app/models/workpaper_editing_lock_models.py` (`WorkpaperEditingLock`)
  - `backend/app/services/editing_lock_service.py`
  - `POST /editing-lock` + `PATCH .../heartbeat` + `DELETE .../release`
  - 5 分钟过期清理（新 worker 或惰性检查都行，选惰性简单）
  - Alembic 脚本
  - _需求_ 11

- [ ] 20. 前端：WorkpaperEditor 编辑锁集成
  - `onMounted` 调用 `acquire_lock`，失败弹"张三正在编辑"对话框
  - `setInterval(heartbeat, 120_000)` 续期
  - `beforeUnload` 释放
  - "强制编辑"按钮 + 通知原持有人
  - _需求_ 11

- [ ] 21. 后端：OCR 字段提取端点
  - `POST /api/attachments/{id}/ocr-fields`
  - 若 `ocr_status != completed` 触发异步 OCR，状态 202 + job_id
  - 结果缓存到 `attachment.ocr_fields_cache` JSONB
  - _需求_ 12

- [ ] 22. 前端：OCR 右键菜单 + 抽屉
  - Univer 右键菜单"📄 从附件 OCR 提取"（底稿有关联附件时可见）
  - 抽屉列附件 + 字段预览 + 填入按钮
  - 填入时 cell_provenance 记 `source='ocr'`（扩展 R4 需求 7）
  - _需求_ 12

- [ ] 23. 管理员：编辑锁监控小工具
  - `ManagerDashboard.vue` 新增"当前编辑中"卡片
  - 展示锁列表 staff/wp/已持续时间
  - _需求_ 11

- [ ] Sprint 3 验收
  - 单元测试：锁过期逻辑 5 用例
  - 集成测试：`test_editing_lock_concurrent.py`（同时打开同张底稿）
  - UAT 新增：
    - 两个浏览器同时开同张底稿 → 第二个弹"正在编辑"对话框
    - OCR 一张发票 → 字段填入后 hover 看到 provenance = 'ocr'
