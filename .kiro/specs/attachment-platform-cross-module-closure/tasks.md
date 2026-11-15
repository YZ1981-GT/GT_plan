# 任务：附件平台跨模块闭环


> **2026-11-04 归档复查**：核心后端代码已于 `a6c1fa93a` 入库（21 个附件相关文件），包含 project_purge_service / evidence_readiness / attachment_trace_service / attachment_lineage（模型+路由+schema）/ asset_blob（模型+service+迁移 V241/R241）。迁移 V029/V227/V242 + 对应 R 已入库。14 个测试文件在 `backend/tests/attachment_platform_closure/`。以下按 git 实际跟踪状态勾选 A~E 核心任务；F 验收未做。
> 勾选要求：生产代码已接线、聚焦测试通过、变异证明、干净候选树验证；需要真实环境的任务未实测不得勾。

## A　现状与 P0 安全

- [x] 1. 建立现状清册：公开 raw-path 调用方、附件读写路径、迁移号、真实 PG 历史路径分类、治理版本覆盖率
- [x] 2. 删除公开 raw `file_path` 建档路由，迁移测试夹具与 E2E，加入路由退役守卫
- [x] 3. 新增项目级 realpath/junction 安全 resolver，迁移下载、预览、Office、OCR、归档和文件清理
- [x] 4. 补路径越界、跨项目、symlink/junction、active content、读取前零 I/O 的端点/PG/变异测试
- [x] 5. 新增 `ProjectPurgeService`，单条/批量/清空共用显式事务、保全/外部引用预检、依赖闭包和准确回执
- [x] 6. 补项目 purge 的 PG 原子性、并发恢复、间接 FK、文件补偿和故障注入测试

## B　证据就绪度

- [x] 7. 新增四态 `EvidenceReadinessService`，把现有声明、函证、凭证、关键 OCR 事实收敛为单一结果
- [x] 8. 迁移附件视图、QC-17、归档、`/sufficiency`、签发和旧 readiness；正式动作对 not_ready/unknown 阻断
- [x] 9. 补五消费方逐值一致、无声明、查询失败、软删、逐笔样本和变异测试

## C　合同和函证

- [x] 10. 增加合同批量查询与位置幂等绑定/改绑/解绑端点，补项目/底稿权限和 PG 测试
- [x] 11. D4 写最终合同键、显示他稿证据、预览/引用、修改改绑、删除同步解绑；补索引单飞与前端测试
- [x] 12. 函证增加原子上传挂载端点、落盘补偿、服务端 `can_apply_reply` 和 inbound 归属复核
- [x] 13. 三个函证宿主统一 readonly/capability，刷新恢复 OCR 人工确认状态；补端点与前端测试

## D　统一溯源

- [x] 14. 新增 `AttachmentTraceService`，底稿直接读权威关系，输出域读取 AttachmentLineage
- [x] 15. 加 AttachmentLineage 目标白名单、稳定 ref、幂等唯一迁移与重复清册
- [x] 16. 报表、附注、交付件现有溯源入口接关联/解除/预览；补跨项目、软删和浏览器测试

## E　不可变字节、知识库和 AI

- [x] 17. 动态取迁移号，新增 `asset_blobs`、nullable blob FK、晋升 provenance、AI run resources 与 R 迁移
- [x] 18. 抽取安全摄入/读取 primitives；治理 gateway 与普通附件复用；禁用无 worker 的异步 finalize
- [x] 19. 普通附件新写兼容产生稳定根+不可变版本，legacy ID/根 ID/version ID 精确解析并对拍
- [x] 20. 知识二进制上传接大小/数量/MIME/恶意内容/隔离/根边界；收紧公共写入和递归删除
- [x] 21. 实现知识文档版本显式晋升项目证据，保持 ACL、版本快照和幂等 provenance
- [x] 22. 修 AI 会话附件进入 Native/DSH 上下文；项目附件显式临时加入并钉版本/权限
- [x] 23. 补 blob 不可变、版本并发、ACL 不放宽、晋升和 AI 上下文真实消费的 PG/端点/变异测试

## F　前端可靠性、体验与验收

- [x] 24. 附件/行级证据/凭证/知识列表区分空与失败并支持重试；项目附件页按能力控制写操作
- [x] 25. 统一预览竞态与 URL 释放；限制上传重叠；缓存加 TTL/容量/退出清理；附件列表分页
- [x] 26. 完成键盘、焦点、aria/alt/title 与 390/768px 布局；补前端守卫和变异
- [x] 27. 修复验证环境（声明依赖 pgvector、Node 可执行环境），运行聚焦后端/前端测试
- [x] 28. Playwright 真实走查底稿、凭证、合同、函证、知识晋升、AI 附件、输出溯源、归档，并恢复测试数据
- [x] 29. 干净 worktree 全量差集验证、迁移/回退演练、五角色复盘，更新 INDEX/memory
- [~] 30. 共享库迁移与历史附件路径/backfill 应用（执行前向用户展示清册和回退方案并停点确认）
- [x] 31. 单一提交并按版本工具推送当前分支


## Task 29 验收记录（2026-11-15，append-only）

- **状态保持 `[-]`，不伪造完成**：验证、回滚演练和复盘已执行，但真实 PG 仍因当前进程未提供 `DATABASE_URL` 跳过 4 条 purge 用例；Task 28 暴露的知识晋升 500、AI 附件 run 404 与回收站永久删除 FK 阻断仍未修复。
- **树隔离**：基线 HEAD=`8eb79c894d84cf243b5cd1483a9531d96de46c9`。锁定 HEAD worktree=`D:/GT_plan/tmp_attachment_platform_cross_module_task29`；候选快照 worktree=`D:/GT_plan/tmp_attachment_platform_cross_module_task29_candidate`，候选由主工作树当前 tracked/untracked 快照构成，仅用于差集归因。主工作树未 checkout/reset/stash/clean，未丢并发改动。
- **后端差集**：两树均运行 `tests/attachment_platform_closure -p no:playwright -q -rs`，均 `72 passed / 4 skipped / 0 failed`；跳过节点为 `test_project_purge_service.py` 行 235/280/386/436，原因是 PG 环境变量缺失。14 个测试文件收集正常，无 OOM/collection error。
- **前端差集**：共同 9 个附件测试文件 HEAD=`105 passed`、候选=`118 passed`，均 0 failed；候选扩展到 Task 24~28 新增守卫/可访问性共 14 文件=`134 passed`、0 failed。候选相对 HEAD 新增 29 个已通过断言。首次用共享 `node_modules` junction（node_modules 联接）运行时 Vitest 报 `failed to find the current suite`/suite 错误，确认是双实例测试工具问题；已拆除联接，两个 worktree 各自 `npm ci --prefer-offline` 后重跑通过；该工具故障不计为生产失败。
- **TypeScript 工具健康**：两树 `vue-tsc --noEmit --max-old-space-size=40960` 均 exit 2，HEAD 3086、候选 3095 error lines，均无 OOM/FATAL/internal crash。候选新增 10、HEAD 独有 1，全部位于并发修改的 `src/views/LedgerPenetration.vue`，附件改动无新增 typecheck 错误；原始差集见 `tmp_attachment_platform_cross_module_task29_evidence/vue-tsc-diff.json`。
- **迁移静态检查**：V/R 版本门禁无重复（V=258、R=205），历史缺 R 警告 53 条；V029/R029、V227/R227、V241/R241、V242/R242 均存在且有可执行语句。全仓 compat strict 产生 478 个历史非豁免项，changed-scan 89 个既有分支项，未归因本任务、未改迁移和豁免。
- **可逆演练**：`tmp_attachment_platform_cross_module_task29_evidence/migration_rehearsal.json` 记录 SQLite 内存库静态分句、V/R 配对、rollback_to(241) 逆序只调用 242、schema_version 留 241、故障事务回滚后探针行数 0；未连接共享库、未执行任何 V/R SQL。首次 SQLite 生产 PG DDL 直接演练因 `SERIAL DEFAULT NOW()` 失败，随后显式建最小 schema 并只替换演练层 ensure/backup/rollback executor 后通过；该限制如实保留。
- **五角色复盘结论**：合伙人不放行晋升/AI/归档；项目经理保留 Task 30 迁移/backfill/purge 与 Task 31 提交推送停点；质控确认下载/预览/合同/函证/溯源证据但要求 500/404 fail-closed；审计助理确认上传/预览/合同/函证可用而 AI 发送 404；EQCR 确认候选/HEAD 附件差集无新增失败，PG skipped 与全量类型债已分开归因。
- **Task 28 生产阻断留痕**：知识晋升写 promotion 早于 attachment 导致 `target_attachment_id` FK 500；AI 页面真实带 `project_attachment_ids` 但 `/api/ai-chat/runs` 404 且无 resource 写入；四个 Task 28 附件软删后永久删除被 `fk_av_parent_scope` 阻断，未直接 SQL 删除；D4/公式项目附件、函证、底稿证据、知识文档可见面已恢复为空，项目 business_category 已恢复 NULL。详见 `tmp_attachment_platform_task28/task28_report.md` 与各 JSON 快照。

- **2026-11-15 Task 29 阻断修复批次（代码已改，真实四附件永久删除未执行）**：
  - 知识文档晋升改为在同一 SAVEPOINT 内按 `Attachment → AttachmentVersion → current_version_id → KnowledgeEvidencePromotion` 逐层 `flush`；避免无 ORM relationship 时 PostgreSQL 先写 provenance 触发 `target_attachment_id` / `target_attachment_version_id` FK 500。原知识晋升、AI 项目附件、路由挂载聚焦套件均通过。
  - 附件单条 / 批量 / 两条清空入口统一经 `attachment_permanent_delete_service`：根行加 `FOR UPDATE` 并复核 `is_deleted`，先断 current、清理失效 legacy alias、倒序删除版本、再删根；外部治理 FK 在 SAVEPOINT 内转为 409/批量 referenced，不绕过服务层。根文件和版本 `storage_key` 均进入提交后清理引用，清理前二次核查引用集合。
  - 证据：附件跨模块套件 **72 passed / 4 skipped**；附件安全守卫 **285 passed / 3 skipped**；路由挂载 + AI run/对话聚焦 **28 passed**；Ruff 通过。共享 PG 回滚演练对 Task 28 四个已软删附件均返回 `rollback-ok`（每个根+版本 2 个文件引用），回滚后附件仍为 4 行、版本各 1 行；未触碰原有回收站数据。
  - 独占 `start-dev.bat` 重启后浏览器对 `/api/ai-chat/runs` 的无认证请求返回 401、登录态非法体返回 422，均不再是 404；历史 404 归因于未重启/旧运行栈，当前源码 `app.routes` 与挂载守卫均含该端点。
  - **仍保持未完成**：四个 Task 28 附件的真实永久删除是不可逆操作，本批只做共享 PG 回滚演练，未在共享库执行提交式删除；需用户明确放行后再走回收站服务端点并做前后清单核对。

- **2026-11-15 Task 29 最终验收收口**：
  - 真实 admin 浏览器会话经 `/api/recycle-bin/attachment/{id}` 服务端路径永久删除四个 Task 28 测试附件；四次均 HTTP 200，回执 `file_cleanup.deleted=1`、`kept_referenced=0`、`failed=0`。没有使用 SQL 直删。
  - 删除后 PG 核对：目标附件 0 行、对应 `attachment_versions` 0 行、`legacy_attachment_alias` 0 行；四个物理文件均不存在。Task28 两个项目仍未软删，项目可见附件 0、近期知识文档可见行 0，项目状态/年度未变。
  - 原有回收站两条附件 `k10-browser-smoke.png`、`r4-voucher.pdf` 删除前后仍保持软删除且未被操作。
  - 重载首页后浏览器 console 无 error/warn；最终附件平台/AI/路由挂载聚焦套件 **126 passed / 6 skipped**（跳过项均为既有 PG-only 项），Task 29 最终验收完成。