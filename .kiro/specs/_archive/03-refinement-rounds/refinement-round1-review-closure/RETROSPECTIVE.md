# Refinement Round 1 — 复盘汇总

本文件汇总 Round 1 的 26 个原任务 + 三轮复盘（Batch 1/2/3）共 42 项补丁的全貌，
供 Round 2 起草时查阅，也作为"5 角色轮转"迭代方法论的首轮完整记录。

## Round 1 原 26 任务

| 任务 | 状态 | 备注 |
|-----|------|-----|
| Task 1 数据模型迁移：枚举扩展 + 字段扩展 + archive_jobs 表 | ✅ | Alembic `round1_review_closure_signature_20260508` |
| Task 2 合并 ReviewInbox 入口（后端不改，增补测试） | ✅ | 10 tests（pm_dashboard 全局/单项目） |
| Task 3 前端 ReviewWorkbench 三栏视图 + 删除 ReviewWorkstation | ✅ | 中栏元信息卡 + "打开完整编辑器"跳转（真只读嵌入留 Round 2） |
| Task 4 复核意见 → 工单联动（SAVEPOINT 隔离 + 事件补偿） | ✅ | `REVIEW_RECORD_CREATED` 事件 + IssueTicketList source 筛选 |
| Task 5 底稿编辑器单元格红点（Univer `attachPopup`） | ✅ | 无副作用（不调 setCellValue 故不污染 dirty） |
| Task 6 工单 → ReviewRecord 反向同步（强一致，整体回滚） | ✅ | 令牌 `[系统] 已整改，请复验` 追加而非覆盖 |
| Task 7 Readiness 门面化 + gate_eval_id 5 分钟幂等 | ✅ | `gate_eval_store.py` Redis + 本地字典降级 |
| Task 8 新增 gate 规则 UnconvertedRejectedAJERule + EventCascadeHealthRule | ✅ | R1-AJE-UNCONVERTED warning + R1-EVENT-CASCADE 动态 severity |
| Task 9 AJE 一键转错报端点 | ✅ | `POST /api/adjustments/{group_id}/convert-to-misstatement` |
| Task 10 GateReadinessPanel 公共组件 + Adjustments 转错报按钮 | ✅ | `defaultOpenGroupIds` + 内置跳转映射 |
| Task 11 签字前置依赖校验 + 最高级同事务切 AuditReport.status | ✅ | `PREREQUISITE_NOT_MET` / `GATE_STALE` 403 |
| Task 12 签字流水线 UI（SignatureWorkflowLine + 弹窗内嵌 GateReadinessPanel） | ✅ | sign-list 卡片文案"已 X/Y 级，待你签" |
| Sprint 1 验收 | ✅ | 6 条用例 + e2e 回归 |
| Task 13 ArchiveOrchestrator（4 步串行 + 断点续传） | ✅ | 3 个旧 archive 端点 `X-Deprecated: true` |
| Task 14 archive_section_registry（插件化章节） | ✅ | 00/01/99 注册，04/02/03 留给 R3/R5 |
| Task 15 封面 + 签字流水 PDF（LibreOffice + 水印） | ✅ | SHA-256 hash 占位"待归档完成后填入" |
| Task 16 归档完整性 persist_checks + manifest_hash | ✅ | persist 失败不阻断归档 |
| Task 17 ArchiveWizard 3 步向导 + 章节级进度条 | ✅ | 轮询 `/jobs/{id}` 每 3s |
| Task 18 移除 PBC/函证空壳入口（方案 A） | ✅ | `include_in_schema=False` + Round 2 TODO |
| Task 19 notification_types 字典 + 归档完成通知 | ✅ | 跨轮约束第 1 条的单一真源 |
| Sprint 2 验收 | ✅ | happy path + 断点续传 + SHA-256 校验 e2e |
| Task 20 数据模型：audit_log + independence + rotation_override | ✅ | Alembic `round1_long_term_compliance_20260508` |
| Task 21 audit_logger_enhanced 真实落库 + 哈希链 + verify-chain | ✅ | Redis 队列 + 批量 writer + 脱敏 |
| Task 22 独立性声明端点 + IndependenceDeclarationCompleteRule | ✅ | legacy 兼容（`wizard_state.independence_confirmed=true`）+ 20 问模板 |
| Task 23 独立性声明前端表单 + 合伙人 Dashboard 提醒 + 归档章节 04 预留 | ✅ | yes/no/多选/文本/附件 |
| Task 24 保留期（10 年）+ 轮换检查（上市 5 年/非上市 7 年） | ✅ | `RETENTION_LOCKED` 403 + rotation_check_service |
| Task 25 轮换预警 + Override 双签流程 | ✅ | 合规 + 首席风控双签（复用 R1 签字流水） |
| Task 26 PBT：哈希链防篡改 4 个属性 | ✅ | 正确链通过/篡改 payload/篡改 hash/交换顺序 |
| Sprint 3 验收 | ✅ | e2e + 哈希链性能 6000 并发 P95 < 50ms |

**合计：26 个任务 + 3 次 Sprint 验收，157 测试全绿（02e3731 之前）。**

## 复盘 Batch 1（14 项代码修复 + 文档，commit 02e3731）

| # | 问题 | 修复 |
|---|-----|------|
| 1 | `prerequisite_signature_ids` 前端读 `s.id` 但后端 `get_workflow` 未返回 id 字段 → 前置校验永远拿不到 id，失效 | `SignService.get_workflow` 返回 `id: str(r.id)` |
| 2 | `GET /api/audit-logs/verify-chain` 无权限校验 | 加 `get_current_user` + 限 admin/qc/signing_partner/eqcr/manager/partner |
| 3 | `audit_log_writer_worker` 多副本 prev_hash race | PG `pg_advisory_xact_lock(hash(project_id))` + README 单实例约束 |
| 4 | `IndependenceDeclarationCompleteRule` legacy 项目上线瞬间全阻断 | 加 `archived_at IS NOT NULL` 跳过 + `LEGACY_CUTOFF_DATE=2026-05-05` 宽容期 |
| 5 | ArchiveOrchestrator 断点续传只认 `last_succeeded_section`（部分失败场景漏步） | 新增 `section_progress` dict + `_get_next_section_index` |
| 6 | RotationCheckService 硬编码上市 5 年，非上市事务所也用 | `is_listed_company` 参数 + 非上市 7 年 |
| 7 | 前端 PartnerDashboard N+1 独立性检查（每项目一次 HTTP） | 新增 `GET /api/my/pending-independence` 批量端点 |
| 8 | 前端错误处理散落各 catch（有的 toast 有的吞） | 新增 `composables/useApiError.ts` 统一 parse/show |
| 9 | PDF 导出依赖 LibreOffice（单路径 + Windows/Docker 都要装 soffice） | 优先 weasyprint（`pip install weasyprint`），降级 LibreOffice |
| 10 | ReviewRecord → IssueTicket 反向同步缺事务隔离，可能整事务回滚 | `db.begin_nested()` SAVEPOINT + `REVIEW_RECORD_CREATED` 事件补偿 |
| 11 | 新增 ADR 文档 `003-review-issue-transaction-strategy.md` | Accepted 2026-05-08 |
| 12 | 新增 `backend/tests/README.md` 记录测试盲点（并发/竞态/worker 故障） | 供 Round 2 Round2-Task-A 消费 |
| 13 | 新增 `backend/app/workers/README.md` 记录单实例约束 + 部署建议 | Docker Compose/K8s/systemd 三种形式 |
| 14 | steering `memory.md` 超 200 行拆分到 architecture/conventions/dev-history | 保持活跃状态摘要 |

## 复盘 Batch 2（14 项测试 + 一致性收尾，commit 01881a7）

| # | Batch 1 遗留 | 修复 |
|---|-----|------|
| 2-1 | `section_progress` 零测试 | 补 3 tests：`_get_next_section_index` 空/全 succeeded/中间失败 |
| 2-2 | 非上市 7 年 case 零测试 | 补 1 test `check_rotation(is_listed_company=False)` 超 6 年不阻、超 7 年阻断 |
| 2-3 | legacy 宽容期零测试 | 补 3 tests：archived 跳过 / legacy 放行 + warning / 新项目严格阻断 |
| 2-4 | `/api/my/pending-independence` 零测试 | 补 4 tests：pending only / archived 排除 / 无 assignment / submitted+approved 排除 |
| 2-5 | useApiError 无页面实际消费 | PartnerDashboard/ArchiveWizard/Adjustments 三处接入 |
| 2-6 | `_get_next_section_index` 签名还接 `last_succeeded_section` 参数，双数据源矛盾 | 签名改为只接 `section_progress`（字段仍写但不参与路由） |
| 2-7 | frontend loadPendingIndependence 报错只 console.warn 吞 | 改为 `ElMessage.warning('独立性待声明检查失败，请刷新')` |
| 2-8 | Adjustments 转错报按钮 409 `ALREADY_CONVERTED` 错误吞 | 加 `parseApiError(err)` + 提示"已转过，无需重复" |
| 2-9 | LEGACY_CUTOFF_DATE 硬编码字符串 | 改为 `settings.INDEPENDENCE_LEGACY_CUTOFF_DATE`（空串=关闭宽容期） |
| 2-10 | `/api/my/pending-independence` 无 limit 参数，前端拉全量风险 | 新增 `limit: int = Query(50, ge=1, le=500)` + `has_more` |
| 2-11 | weasyprint 降级路径零测试 | 补 3 tests：weasyprint 可用/不可用降级/两者皆失败 |
| 2-12 | `_send_admin_notification` 只写 logger.critical 不真发通知 | 调 `NotificationService.send_notification_to_many`（本轮 notification_type 复用 GATE_ALERT，Batch 3-2 修） |
| 2-13 | AuditLogWriterWorker 启动 warning 不明显 | 启动时 `logger.warning("如果看到两个此 worker 实例同时打印此行...")`（Batch 3-5 再降级） |
| 2-14 | 新增 `backend/docs/adr/README.md` 索引表 + tasks.md 追加 Round2-Task-A~F | 6 条候选任务 |

## 复盘 Batch 3（14 项安全/配置/文档，当前）

| # | Batch 2 遗留 | 修复 | 状态 |
|---|-----|------|-----|
| 3-1 | `_resolve_legacy_cutoff` 解析失败静默盖默认 2026-05-05（和"空串关闭"语义矛盾） | 统一返回 None + WARNING 日志 | ✅ |
| 3-2 | `_send_admin_notification` 误用 `GATE_ALERT` 类型 → 前端跳转 gate-readiness 找不到项目 | 新增 `AUDIT_LOG_WRITE_FAILED` 常量 + 前后端同步 + 路由到 `/audit-logs/verify-chain` | ✅ |
| 3-3 | `/api/my/pending-independence` 返回 `total` 但前端只用 `projects.length` 做 badge → limit=50 被截断时 badge 误导 | 前端 `pendingIndependenceProjects` 扩展为 `{projects, total, hasMore}`，badge 显示 total | ✅ |
| 3-4 | `last_succeeded_section` 与 `section_progress` 双写，前端可能只读前者导致 UI 与实际分叉 | 后端字段加 DEPRECATED 注释 + `_job_to_dict` docstring 明确权威；前端 `progressPercent` 优先读 `section_progress` | ✅ |
| 3-5 | AuditLogWriterWorker 启动每次 `logger.warning` 误告警 | 降级为 `logger.info` + 附上 `worker_id={host}-{pid}`，运维看到重复 id 才报警 | ✅ |
| 3-6 | ADR README 001/002 占位未说明"废弃" | 标为 ~~Deprecated~~ + 加说明段 | ✅ |
| 3-7 | legacy 宽容期下线时机未文档化（何时可以关？如何关？） | 新增 `INDEPENDENCE_LEGACY_GRACE_ENABLED` 配置（默认 True，R6+ 改 False 彻底下线） | ✅ |
| 3-8 | `_send_admin_notification` 每次失败开新 session，短时高并发失败可能耗尽连接池 | 函数签名改为接收 `db: AsyncSession`，调用方 `_handle_write_failure` 开一次 session 复用 | ✅ |
| 3-9 | `_send_admin_notification` 零测试 | 补 4 tests：全 admin 发送 / 无 admin 返 False / NotificationService 异常 / _handle_write_failure MAX_RETRIES 触发 | ✅ |
| 3-10 | 前端 `has_more=true` 但无"加载更多"按钮，用户看不到剩余的 | 新增 `loadMorePendingIndependence()`，底部 el-button link "加载更多（还有 N 个）" | ✅ |
| 3-11 | Round2-Task-A~F 未排优先级 | 标注 P1/P2 + 工期估计，并对已完成任务加 strikethrough 标记 | ✅ |
| 3-12 | 无复盘汇总文档 | 新建本文件 `RETROSPECTIVE.md` | ✅ |
| 3-13 | `_resolve_legacy_cutoff` 3 分支零测试 | 补 3 tests：空串返 None / 非法串返 None + WARNING / 合法串返 tz-aware datetime | ✅ |
| 3-14 | `INDEPENDENCE_LEGACY_GRACE_ENABLED` 开关零测试 | 补 2 tests：False 时 legacy 项目走严格路径 / True（默认）时 legacy 项目走宽容路径 | ✅ |

## 测试数变化

| 时点 | 后端测试数 | 备注 |
|-----|----------|------|
| Round 1 开始前 | 0 | - |
| Round 1 完成（26 task） | 157 | Sprint 1/2/3 验收全绿 |
| Batch 1 后 | 171 | +14（fix 回归测试 + 新端点测试） |
| Batch 2 后 | 188 | +17（section_progress/非上市 7 年/legacy 宽容/pending_independence/weasyprint 降级） |
| Batch 3 后 | 198+ | +10（_resolve_legacy_cutoff 3 + GRACE_ENABLED 2 + _send_admin_notification 4 + 回归修正 1） |

## Round 2 任务候选最终状态

| ID | 描述 | 状态 | 优先级 |
|----|-----|------|-------|
| Round2-Task-A | 补测试盲点（并发 3 + worker 3 + PBT 5） | 待做 | **P1, 3-5d** |
| Round2-Task-B | legacy 日期配置化 | ✅ Batch 2-9 | - |
| Round2-Task-C | /api/my/pending-independence 加 limit | ✅ Batch 2-10 | - |
| Round2-Task-D | AuditLogWriterWorker 启动 warning | ✅ Batch 3-5 | - |
| Round2-Task-E | section_progress 加 GIN 索引（PG 迁移） | 待做 | **P2, 1d** |
| Round2-Task-F | weasyprint 降级路径补测试 | ✅ Batch 2-11 | - |

## 结论

- **代码层面**：Round 1 + Batch 1/2/3 三轮修复共 42 项 patch 全部 closed，backend 测试套件 198+ 绿灯。
- **文档层面**：ADR-003（事务策略）、backend/tests/README（测试盲点）、backend/app/workers/README（单实例约束）、本 RETROSPECTIVE.md 齐备。
- **流程层面**：验证了"PDCA 5 角色轮转 + 多轮复盘直到零新建议"方法论可行，Round 2 可延用。
- **剩余**：UAT 6 项（需真人浏览器操作）未执行，是进入 Round 2 前唯一硬缺口。

## 复盘纪律沉淀（Round 2+ 请遵守）

1. **子代理报告必须 grep 核查**，不信表面声明——Batch 2 发现"已实现"但实际未接线的 useApiError，Batch 3 发现"已发通知"但用错 type。
2. **每轮修复后复盘一次，直到零新建议**——Batch 1 14 项 → Batch 2 再发现 14 项 → Batch 3 又 14 项，收敛条件是"看完整轮代码无可改进项"。
3. **测试覆盖缺失单独开一项补齐，不混入特性改动**——避免 review 时注意力分散。Batch 3 的 3-9/3-13/3-14 三项都是"之前已修但没测"的补齐，不涉及功能变更。
4. **双写字段必须明确权威**——Batch 3-4 `last_succeeded_section` vs `section_progress` 的教训：任何"为了向后兼容而双写"的字段，必须在代码注释和文档两处说清楚哪个是权威、什么时候可以下线。
5. **宽容期/降级逻辑必须文档化下线条件**——Batch 3-7 `INDEPENDENCE_LEGACY_GRACE_ENABLED` 的教训：legacy 代码留在仓库里就会被后人当成"必须保留的行为"，必须在设计阶段写清"满足什么条件可以彻底删除"。
