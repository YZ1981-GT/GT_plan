# 实施任务：交付中心三件套一键出具

> 顺序即依赖。每项 `[x]` 必须有真实代码、修复前红/修复后绿/故障注入证据。仅在工作树通过而未进入目标 HEAD 时，不得标完成。`[ ]*` 是外部依赖或需用户明确授权的待办，不等于跳过。

- [ ] 1. 基线与入口清册
  - 核对当前分支/HEAD/冲突/未跟踪的 phase2/phase3 实现；对交付相关文件做工作树 vs HEAD 逐块审计，不覆盖并行改动。
  - 现算 `FullDeliverablesExecutor` 顺序、`ExportJobService.retry_failed` 行为、`DeliverableService.render_and_store` 失败后版本状态，以及现有路由/模型/迁移/前端接口契约。
  - 给出最小修复前红用例：文件落盘失败后仍有成功版本、retry 只复位状态、unadjusted 计入三件套等。失败断言必须指向实际错误形态。
  - _需求：1.1, 2.1, 3.1, 5.2, 7.1_

- [ ] 2. readiness 基线与硬/软闸门
  - `DeliverableReadinessService` 真读取 TB、公式推送、调整、报表、底稿、附注的项目年度状态；phase3 未在 HEAD 的能力 fail-closed。
  - stale、漂移、准则/模板、快照和历史文件逐项产出稳定 code、中文原因及证据；warning 与 blocker 分离。
  - SQLite 真 ORM + TestClient；删掉任一硬闸门必须红，软 warning 不应阻断的反向样本必须绿。
  - _需求：1.1, 1.2, 1.3, 1.4, 1.6_

- [ ] 3. 快照与 schema/ORM 三层一致
  - 现算最高迁移号，按项目规则新增 V/R 配对与必要的 job/item/attempt/snapshot/version 字段；`IF NOT EXISTS`，数值版本不得撞号。
  - 快照 digest 不含生成时间和本机绝对路径，三项均引用同一快照；PG 两次执行幂等、约束和 R 回滚测试。
  - 修改快照输入、让其中一项换 snapshot 或迁移漏列的变异必须红。
  - _需求：1.5, 2.4, 3.2, 7.5_

- [ ] 4. 文件指纹与版本 fail-closed
  - `render_and_store` 先生成/落盘/校验最终文件，再创建成功版本；失败清理本 attempt 临时文件且不删除旧有效版本。
  - 统一 SHA-256/大小/可读性校验；版本复用、readiness 和下载共享同一验证逻辑。
  - 文件写失败、删除、截断、哈希不匹配、版本先写后的五类故障注入，修复前红/修复后绿/改回即红。
  - _需求：3.1–3.6, 7.3_

- [ ] 5. executor 固定顺序与步骤依赖
  - 正式 `TRIO_STEPS` 只包含 `financial_report → disclosure_notes → audit_report`，`financial_report_unadjusted` 仅辅助。
  - 三件套共享 snapshot；audit_report 在前置失败时标 `blocked_by_dependency`；状态聚合只统计正式三项。
  - SQLite 真 ORM 测试调换顺序、把辅助项算正式项、前置失败后仍生成正文等变异必须红。
  - _需求：2.1–2.6, 4.4_

- [ ] 6. savepoint 隔离与事务边界
  - 每步骤 `begin_nested()`；服务仅 flush，路由/编排统一 commit；失败步骤业务写入回滚，成功步骤与失败留痕保留。
  - SQLite 真 ORM + 真 PG 临时 schema：制造第 2 步约束/导出器异常，验证第 1 步版本、失败 attempt 和第 3 步依赖状态；去掉 savepoint 必须红。
  - _需求：4.1, 4.2, 4.3, 4.5, 7.2_

- [ ] 7. job/item/attempt 不可变历史
  - 失败记录含异常类型、诊断、中文消息、快照、阶段和时间；多次尝试单调编号，保留原始失败原因。
  - 中断/超时后的 running 恢复策略 fail-closed；TestClient 查询与 ORM 断言完整历史；覆盖写旧 attempt 的变异必须红。
  - _需求：4.3, 4.4, 4.6, 5.4_

- [ ] 8. 真正重试失败步骤
  - `ExportJobService.retry_failed` 实际调用 executor 步骤入口，重新渲染、落盘、指纹和版本；成功项复用前校验文件。
  - 失败后恢复文件写权限/路径，再 retry 应新增 attempt、生成真实文件和版本；只改 queued 状态的旧实现必须红。
  - 旧快照与当前数据不一致返回冲突或建新 job，绝不混用快照。
  - _需求：5.2–5.5_

- [ ] 9. readiness/生成/重试/下载端点与权限
  - 路由登记在 `router_registry`，项目成员/只读/编辑权限经真依赖链校验；创建/重试由 router commit。
  - TestClient 真请求覆盖 ready/blocked、job 属主项目校验、403 零写入、重试冲突、下载前物理哈希校验；去鉴权与错项目变异必须红。
  - _需求：1.6, 3.5, 5.1, 5.6, 7.4_

- [ ] 10. 前端交付中心三件套状态
  - `deliverableApi.ts` 增 readiness/trio/item/attempt 类型和真实端点；`DeliverableCenter.vue` 显示固定顺序、硬/软闸门、快照和 `0/3` 至 `3/3` 进度。
  - `platform_persist_failed` / 文件缺失 / 指纹错误不提示正式下载成功；全部用户可见文案中文。
  - Vitest 真挂载验证阻断、成功、部分失败和文件失败；删失败状态显示的变异必须红。
  - _需求：6.1, 6.2, 6.4, 6.6_

- [ ] 11. 前端失败项重试与历史
  - 仅失败且有权限、快照仍有效时展示重试入口；点击调用真实 retry API 并继续轮询，保留旧 attempt 错误。
  - Vitest 真挂载覆盖失败到重试成功和旧快照/无权限置灰；把按钮只改状态、不发请求的变异必须红。
  - _需求：5.6, 6.3, 6.5_

- [ ] 12. SQLite 真 ORM/文件故障全链回归
  - 用真实 executor、版本服务和任务模型跑 readiness → 三件套生成 → 第 2 步失败 → retry → 完成，逐项比较 snapshot、文件和指纹。
  - 并行运行 phase2/phase3 相关定向回归，区分本阶段引入与预存红；五类文件故障必须全部 fail-closed。
  - _需求：2.1–2.6, 3.1–3.6, 4.1–4.6, 5.1–5.6, 7.1–7.3_

- [ ] 13. 真 PG 临时 schema 与事务回滚
  - 迁移、约束、savepoint、行锁和下载指纹验证；试跑前后 job/version/attempt/文件指纹零痕迹。
  - 不使用真实项目写库作本任务“通过”证据；缺 PG 时如实标依赖阻断。
  - _需求：7.5_

- [ ]* 14. 真实项目事务内 dry-run
  - 仅在可连接环境下选择项目，按项目/年度分事务执行 readiness 与 dry-run，逐表/逐文件做前后指纹比对；严禁无授权 commit。
  - 真实项目没有可用数据时标 data-blocked，不以 SQLite 或 HTTP 200 冒充。
  - _需求：7.5_

- [ ]* 15. Playwright 真实浏览器验证
  - 测试一键出具的阻断/软警告、三件套顺序、失败原因、可重试按钮、文件下载失败中文提示。
  - 打开自动保存页面前停到 `about:blank`；真实“立即出具”会写库，须用户明确确认；未经确认只验只读/dry-run UI 并保留本项未完成。
  - _需求：7.6_

- [ ]* 16. 真实出具三件套写库验收
  - 用户明确授权后对指定项目执行真实一键出具，核对三个正式文件的版本、文件路径、大小、SHA-256、同一快照和可下载性。
  - 未授权时保持 `[ ]*`，不得以合成 SSE 或本地文件生成冒充生产交付。
  - _需求：2.6, 7.5, 7.6_

- [ ] 17. clean HEAD 对照与冲突归因
  - 检查 `git ls-files` 覆盖本链的生产、迁移、规则、测试和 spec；新建 clean HEAD 临时 worktree 跑相同定向命令，报告 HEAD 预存红/并行未提交红/本阶段引入红。
  - 冲突未清、模块未跟踪或只在工作树绿时不得勾选本项；确认提交前后 HEAD 未并发移动，不覆盖他人暂存。
  - _需求：7.7, 8.1, 8.4_

- [ ] 18. 收尾与追溯
  - INDEX 登记和真实进度同步；memory 仅追加准确交付状态，清理本阶段一次性探针；复核 phase2/phase3 待办仍如实未勾。
  - 交付文案分别标明“代码已改但未实测”“已通过 SQLite/PG”“已通过 clean HEAD”“已获授权真浏览器出具”，不得混用。
  - _需求：7.7, 8.1–8.4_
