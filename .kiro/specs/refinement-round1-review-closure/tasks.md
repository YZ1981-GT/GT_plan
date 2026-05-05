# Refinement Round 1 — 任务清单

按 README 约定：一轮 ≤ 20 任务，分 2 个 Sprint，每 Sprint 结束做回归测试 + UAT。

## Sprint 1：复核闭环（需求 1~4）

- [x] 1. 数据模型迁移：新增枚举值与字段
  - 扩展 `IssueTicket.source` 枚举到 11 个值（一次性迁移）
  - 扩展 `AssignmentRole` 新增 `eqcr`
  - `SignatureRecord` 新增 `required_order/required_role/prerequisite_signature_ids`
  - `ReviewRecord` 新增 `status/reply_text`
  - `IssueTicket` 新增 `source_ref_id`
  - 创建 `archive_jobs` 表（`backend/app/models/archive_models.py`）
  - Alembic 脚本 `round1_review_closure_signature_20260508.py`
  - _依赖_ README v2.2 数据库迁移约定；_需求_ 1~6

- [x] 2. 后端：合并 ReviewInbox 入口（不改后端，仅前端消费）
  - 确认 `ReviewInboxService.get_inbox` 全局/单项目都可用，补 API 测试覆盖
  - 路由 `pm_dashboard.py` 确认 `GET /api/review-inbox` 和 `GET /api/projects/{id}/review-inbox` 均走同一 service
  - _需求_ 1

- [x] 3. 前端：新建 `ReviewWorkbench.vue` 三栏视图
  - 左栏队列（含筛选）+ 中栏只读底稿预览 + 右栏 AI 预审 + 意见输入
  - 快捷键 `Ctrl+Enter / Ctrl+Shift+Enter / ↑↓`
  - "批量模式"切换表格视图（复用 `ReviewInbox` 现有批量能力）
  - 自动切下一条底稿
  - `router/index.ts` 把 `/review-inbox` 和 `/projects/:id/review-inbox` 组件指向 `ReviewWorkbench`
  - 删除 `ReviewWorkstation.vue`
  - _需求_ 1

- [x] 4. 后端：复核意见→工单联动
  - `wp_review_service.add_comment` 里"退回"时创建 `IssueTicket(source='review_comment', source_ref_id=review_record.id)`
  - 订阅 `REVIEW_RECORD_CREATED` 事件做补偿（工单创建失败不阻断复核动作）
  - `IssueTicketList` source 筛选 UI 增加"复核意见"
  - _需求_ 2

- [x] 5. 前端：底稿编辑器单元格红点
  - `WorkpaperEditor.vue` 拉取 `ReviewRecord where status='open' and cell_reference is not null`
  - Univer 自定义装饰在对应单元格显示红点
  - 点击红点弹 popover 显示意见全文 + 关联工单链接
  - _需求_ 2

- [x] 6. 后端：工单→ReviewRecord 状态反向同步
  - 工单切 `pending_recheck` 时，关联 `ReviewRecord.reply_text` 追加"已整改"
  - 工单切 `closed` 时 `ReviewRecord.status='resolved'`，底稿 `review_status` 回退 `level1_rejected → pending_level1`
  - _需求_ 2

- [x] 7. 后端：Readiness 门面化改造
  - `SignReadinessService.check_sign_readiness` 内部调 `gate_engine.evaluate('sign_off')`，保留 8 项类目映射
  - `ArchiveReadinessService.check_readiness` 内部调 `gate_engine.evaluate('export_package')`
  - 统一响应 schema：`{ready, groups, gate_eval_id, expires_at}`
  - `gate_eval_id` 5 分钟 TTL（Redis 缓存）
  - _需求_ 3

- [x] 8. 后端：新增两个 gate 规则
  - `UnconvertedRejectedAJERule`：扫描 rejected 但未转错报的 AJE 组（warning 级）
  - `EventCascadeHealthRule`：检查 1 小时内 `WORKPAPER_SAVED` 事件全部消费（首次部署 warning 不阻断，满月后升 blocking）
  - 注册到 `gate_rules_phase14.register_phase14_rules()`
  - _需求_ 3

- [x] 9. 后端：AJE 一键转错报
  - `POST /api/adjustments/{group_id}/convert-to-misstatement` 封装现有 `misstatement_service.create_from_rejected_aje`
  - 响应包含新建 `misstatement_id`，审计日志记动作
  - _需求_ 3

- [x] 10. 前端：GateReadinessPanel 公共组件
  - `src/components/gate/GateReadinessPanel.vue`
  - 按 groups 折叠展开，findings 带跳转（底稿/错报/附注）
  - "剩余 Ns"倒计时 + 过期自动刷新
  - `Adjustments.vue` 新增"转错报"按钮列（仅 rejected 行）
  - _需求_ 3

- [x] 11. 后端：签字前置依赖校验
  - `POST /api/signatures/sign` 校验 `prerequisite_signature_ids` 全部 signed，否则 403 `PREREQUISITE_NOT_MET`
  - 校验 `gate_eval_id` 存在 + 未过期 + 对应 ready=true，否则 403 `GATE_STALE`
  - **最高级签完后同事务切 `AuditReport.status`**（review/eqcr_approved → final）
  - `GET /api/signatures/workflow/{project_id}` 新增
  - _需求_ 4

- [x] 12. 前端：签字流水线 UI
  - `src/components/signature/SignatureWorkflowLine.vue` 显示 order/role/status 时间线
  - `PartnerDashboard.vue` 签字弹窗内嵌 `GateReadinessPanel` + `SignatureWorkflowLine` + "立即签字"按钮
  - 签字后 toast + 刷新待签字列表
  - `sign-list` 卡片文案改为"已 X/Y 级，待你签"
  - _需求_ 4

- [x] Sprint 1 验收
  - 单元测试：新规则 6 条用例全过
  - 集成测试：`test_review_closure_e2e.py` 走完退回→工单→整改→复验→通过
  - 回归测试：原批量通过/退回、原签字接口、旧 readiness schema 兼容
  - UAT：README UAT 清单第 1/2/3/4 条走完

## Sprint 2：归档 + 合规文档（需求 5~7）

- [x] 13. 后端：ArchiveOrchestrator 服务
  - 新建 `backend/app/services/archive_orchestrator.py`
  - 串行执行 `gate_engine → wp_storage.archive → private_storage.push_to_cloud(若请求) → data_lifecycle.archive_project_data`
  - 失败时记 `archive_jobs.failed_section / failed_reason`
  - `POST /api/projects/{id}/archive/orchestrate` + `GET .../jobs/{id}` + `POST .../retry`
  - 旧 3 个 archive 端点加 `X-Deprecated: true` 响应头
  - _需求_ 5

- [x] 14. 后端：归档章节化 registry
  - 新建 `backend/app/services/archive_section_registry.py`
  - 提供 `register(order_prefix, filename, generator_func)` / `list_all()` API
  - R1 本轮注册：`00-项目封面` / `01-签字流水` / `99-审计日志`
  - 预留 R3/R5 章节位（文档说明，不注册）
  - _需求_ 6

- [x] 15. 后端：封面与签字流水 PDF 生成
  - `generate_project_cover_pdf(project_id)` → 填模板 `backend/data/archive_templates/project_cover.docx`
  - `generate_signature_ledger_pdf(project_id)` → 填模板 `signature_ledger.docx`，支持 N 级签字（预留 EQCR 扩展）
  - 走 `pdf_export_engine`（LibreOffice）
  - 水印"本归档包由审计平台 v{ver} 于 {time} 自动生成，SHA-256: {hash}"
  - _需求_ 6

- [x] 16. 后端：归档完整性记录
  - `ArchiveOrchestrator` 完成后调 `ExportIntegrityService.persist_hash_checks`
  - 章节级断点续传：重试从 `last_succeeded_section` 下一个章节开始，已完成章节的 hash 保留
  - 下载时不重算，后台每日调 `verify_package` 校验归档包可选
  - _需求_ 5, 6

- [x] 17. 前端：ArchiveWizard 3 步向导
  - `src/views/ArchiveWizard.vue`
  - 步骤 1 就绪检查（嵌 `GateReadinessPanel`）→ 步骤 2 选项（推云/清本地）→ 步骤 3 确认
  - 执行中显示章节级进度条（轮询 jobs/{id} 每 3s）
  - 失败时显示失败章节 + "重试"按钮
  - 路由 `/projects/:projectId/archive` + `/projects/:projectId/archive/jobs/:jobId`
  - _需求_ 5

- [x] 18. 前端：移除 PBC/函证空壳入口（方案 A）
  - DefaultLayout 与侧边栏移除 PBC/函证链接
  - `pbc.py` / `confirmations.py` 路由加 `include_in_schema=False`
  - OpenAPI 不暴露
  - README 中登记 Round 2 的 TODO
  - _需求_ 7

- [x] 19. 通知字典 + 归档完成通知
  - 新建 `backend/app/services/notification_types.py` 常量集（本轮仅收口 Round 1 用到的类型：`archive_done / signature_ready / gate_alert`）
  - 前端 `src/services/notificationTypes.ts` 同步字典与跳转规则
  - `ArchiveOrchestrator` 成功时发通知给项目成员
  - _依赖_ README 跨轮约束第 1 条；_需求_ 5

- [x] Sprint 2 验收
  - 集成测试：`test_archive_orchestrate_e2e.py` happy path + 断点续传 + SHA256 校验
  - 回归测试：旧 3 个归档端点仍可用（标 deprecated）
  - UAT：README UAT 清单第 5/6 条走完（归档包打开验证封面+签字流水+水印，PBC/函证入口移除）

## Sprint 1 + 2 合计 19 个任务（未满 20 任务上限）

## 完成标志

- 本文件所有任务标记 `[x]`
- UAT 6 项全部走完并有通过记录
- 未引入新的 vue-tsc 错误（新增预存错误 ≤ 0）
- `pytest backend/tests/ -v` 全过（或失败原因与预存失败清单一致）
- Round 1 关闭，进入 Round 2 实施

## Sprint 3：长期运营合规（需求 9~11，新增）

本 Sprint 为 v1.5 合伙人第三轮复盘新增，7 个任务。建议在 Sprint 1/2 完成后单独跑，不并入 Sprint 1/2 避免超限。

- [x] 20. 数据模型：审计日志 + 独立性声明 + 保留期 + 轮换 override
  - 新建 `backend/app/models/audit_log_models.py` (`AuditLogEntry`)
  - 新建 `backend/app/models/independence_models.py` (`IndependenceDeclaration`)
  - 新建 `backend/app/models/rotation_models.py` (`PartnerRotationOverride`)
  - `Project` 表扩展 `archived_at / retention_until`
  - Alembic 脚本 `round1_long_term_compliance_{date}.py`
  - _需求_ 9, 10, 11

- [x] 21. 后端：audit_logger_enhanced 真实落库 + 哈希链
  - 重写 `audit_logger_enhanced.log_action` 走 Redis 队列 + batch writer
  - 新建 worker `backend/app/workers/audit_log_writer_worker.py`（参考 sla_worker 模式）
  - `GET /api/audit-logs/verify-chain?project_id=&from=&to=`
  - 脱敏接入 `export_mask_service.mask_log_payload`
  - 写失败触发告警 `AUDIT_LOG_WRITE_FAILED`
  - _需求_ 9

- [x] 22. 后端：独立性声明端点 + gate 规则
  - `backend/app/services/independence_service.py`
  - `GET/POST/PATCH /api/projects/{id}/independence-declarations`
  - `POST .../submit` 触发 SignatureRecord + audit log
  - 预置 20 条问题 seed `backend/data/independence_questions.json`
  - `gate_rules_phase14` 新增 `IndependenceDeclarationCompleteRule` 注册到 sign_off
  - 兼容逻辑：旧 `independence_confirmed: true` 视为 legacy 通过 + 升级提醒
  - _需求_ 10

- [x] 23. 前端：独立性声明表单
  - `src/views/independence/IndependenceDeclarationForm.vue`
  - 按问题模板渲染，yes/no/多选/文本/附件上传
  - 合伙人 Dashboard 新增"独立性待声明"提醒卡
  - 归档章节 04 注册：`archive_section_registry.register('04', 'independence_declarations/', independence_pdf_generator)`
  - _需求_ 10

- [x] 24. 后端：保留期 + 轮换检查
  - `data_lifecycle.purge_project_data` 硬校验 `retention_until`，违反 403 `RETENTION_LOCKED`
  - 归档成功时自动写 `Project.archived_at = now()` + `retention_until = archived_at + 10 years`
  - 新建 `backend/app/services/rotation_check_service.py`
  - `GET /api/rotation/check?staff_id=&client_name=` 返回连续年数
  - `project_wizard` 创建项目选人时前端调用检查，阻断/警告
  - _需求_ 11

- [x] 25. 前端：轮换预警 + override 流程
  - Dashboard admin 视角新增"轮换预警"卡片
  - 超限时 override 需合规合伙人 + 首席风控合伙人双签（复用 R1 签字流水机制，`SignatureRecord.object_type='rotation_override'`）
  - _需求_ 11

- [x] 26. 属性测试：哈希链防篡改
  - `test_audit_log_hash_chain_property.py`（hypothesis）：随机生成日志序列，任意位置修改一条 → verify-chain 必定检出
  - _需求_ 9

- [x] Sprint 3 验收
  - 集成测试：`test_long_term_compliance_e2e.py`（声明→签字→归档→验证保留锁→哈希链校验）
  - 性能测试：`log_action` 6000 并发 P95 < 50ms
  - UAT 新增条目：
    - 声明 20 问全填 + 附件上传 + 提交 → sign_off gate 通过
    - 某项目 sign 后立即调 `purge` 返回 403，"合规+风控"双签后可 purge
    - 连续 5 年签字同客户时创建新项目被阻断，override 后放行并留痕
    - 手动 UPDATE 改某条 audit_log 的 payload，`verify-chain` 能检出断链点
