# 实施计划：LLM 联动与审计实务闭环

> 以 design.md ADR-LLM-001~019 为准。用户已批准按建议实施；明确延后的 pgvector、DSH allowlist 扩面和 8 个插件实现不在完成条件内。临时产物放仓库根 `tmp_llm_closure/`。主工作树存在并发改动，重叠文件只做定点合并。标完成须有生产代码、针对性测试、故障注入/反向证据和浏览器实测；环境依赖项如实标 `[ ]*`。

## A. 先止血：接线、安全和假成功

- [x] 0. 冻结基线与调用清册
  - 现算 Chat/LLM/OCR 生产入口、能力声明、prompt 来源、确认流、项目鉴权、运行模型字段和测试集合；输出到 `tmp_llm_closure/baseline/`
  - 核对本 spec 与已归档 `project-pid-path-authz-coverage`、LLM/OCR、DSH/KB、AI 采纳 specs 的边界

- [ ] 1. Chat Run 真实上下文计划（ADR-LLM-002/005/006）
  - 接入 mention、附件、review prompt 与统一预算；Native/DSH 共用 ContextPlan/Manifest
  - capability 由生产 consumer 推导，未接能力不得显示可用
  - Verify：四类上下文正反用例；删任一 consumer 后 capability 守卫红

- [ ] 2. 事件、引用与实际模型留痕（ADR-LLM-007）
  - citation 键单一来源；前端显示和可鉴权跳转
  - coordinator 落实际 model/deployment/fallback/attempts
  - Verify：Run→SSE→前端→DB 契约；本机失败转服务器用例

- [ ] 3. 文件夹上下文、全局范围和未保存提示（需求 3）
  - 文件夹逐文档判权、稳定排序、逐篇 manifest
  - 全局范围提示与真实检索一致；有项目无文档不静默变全局
  - 第一批先提示未保存内容未纳入
  - Verify：混合权限/旧版本/排序；前端范围文案

- [ ] 4. 项目鉴权与角色能力（ADR-LLM-008/010）
  - 修 `role_ai_features` 四端点；AI ask/draft/review/adopt/agent 能力单一来源
  - AI 复核工具栏按 capability；QC/EQCR 只读独立复核可用、不可采纳
  - metrics/内部健康端点收紧
  - Verify：端点级未登录/跨项目/五角色矩阵

- [ ] 5. Typed LLM 结果与失败止写（ADR-LLM-003）
  - 建 `LLMInvocationResult`/兼容 adapter；废止失败即正文
  - 迁移附注、WpAIService、单页/批量复核及高频调用方；实际模型替代硬编码，删除伪置信度
  - 全仓同类调用清册建立只减棘轮
  - Verify：断连/429/超时/空输出/无效 JSON 均无成功草稿

- [ ] 6. AI 复核不假通过与专业边界（ADR-LLM-011/013）
  - 单页/批量复核 parse failure、unknown、证据不足统一 manual
  - 分离确定性检查、AI findings、人工状态；AI 不产生业务 pass
  - task 级专业边界；改“总体审计意见”等 prompt/文案
  - Verify：空 findings、占位串、确定性失败、重大判断请求

## B. 统一任务内核与高频实务链

- [ ] 7. `AiTaskSpec`、Prompt Registry 与执行 facade（ADR-LLM-001/004/017）
  - 任务注册、风险/角色/信任域/context recipe/output schema/verifier/writeback policy
  - Prompt append-only 版本；先登记 Chat、附注、底稿复核、项目摘要
  - DraftArtifact facade 复用现有 message + ai_content_log，不新造第三套确认流
  - Verify：注册闭合、版本不可覆盖、未登记任务 fail-closed

- [ ] 8. 模型信任域与远程兜底策略（ADR-LLM-009）
  - 迁移+ORM+管理 UI：trust zone/client-data/mask policy
  - 任务过滤候选；服务器兜底显示与留痕；修不实 local_only
  - Verify：受限任务拒绝外部候选、事务所私有候选可按策略兜底

- [ ] 9. 附注事实包与四类生成统一（ADR-LLM-012/014）
  - 服务端构建 NoteFactPack；变动分析不收客户端事实
  - 续写/改写/政策/分析统一预览 diff + generation ID + pending
  - 数字/日期/主体逐值验证，失败不准采纳
  - Verify：真实读取方口径、stale、缺数据、数字变异

- [ ] 10. 底稿复核与高频专项调用迁移
  - 单页/批量复核及高频底稿结论改走 AiTaskExecutor
  - 规则先行，AI 只增加疑点；来源地址可点击
  - 低频硬编码 prompt 登债务清单，只许减少
  - Verify：确定性规则与 LLM 结果组合矩阵

- [ ] 11. 耐久批任务（ADR-LLM-015）
  - `ai_task_jobs/items` 迁移、ORM、worker、租约、取消、恢复、逐项幂等
  - 批量附注和批量复核迁移；每项返回稳定 generation ID，采纳不重跑
  - Verify：响应丢失、重启恢复、单项失败续行、取消

- [ ] 12. CAS 精确写回、diff 与撤销（ADR-LLM-016）
  - target adapter、基线版本/before hash、锁和权限；确认后应用原 patch
  - 记录 after version/hash、领域事件；安全撤销
  - pending 加载失败显示 unknown，正式输出 fail-closed
  - Verify：并发编辑、重复确认、锁、撤销冲突、事件

## C. 上下文深化、分布式状态与运营闭环

- [ ] 13. 审计关系图上下文与 draft overlay
  - 按任务接 TB/调整/报表/附注/上下游底稿/证据/上年/同行业同模板同科目知识
  - 受限未保存草稿 overlay，绑定宿主、基线和 hash
  - Verify：跨项目零注入、预算裁剪、overlay 版本冲突

- [ ] 14. 多 worker 状态与观测（ADR-LLM-018/019）
  - MCP budget/revocation、批任务锁/进度迁 Redis/DB
  - TTFT、tokens/s、deployment/fallback/error、验证结果、采纳/修订/拒绝、token/成本
  - 可复现 envelope：task/prompt/model/参数/app/context/output/verifier hashes
  - Verify：两 worker 竞争、重启、低基数指标、敏感正文不进入 metrics

- [ ] 15. 实务 UI 收口与 stub 清理
  - 系统检查/AI 提示/人工结论分栏；实际模型位置、stale、裁剪、diff
  - QC/EQCR 独立挑战模式；插件执行入口隐藏或标开发中
  - 删除/下线旧重复 Chat 与无调用 AI 壳前先证明 0 调用
  - Verify：五角色、窄屏、键盘、中文提示

- [ ] 16. 金标、真实 canary、全回归与浏览器终验
  - 无客户数据金标：引用、数字、拒绝下结论、权限、stale、fallback、注入、OCR
  - deterministic CI + 可选 live-model canary；候选树与干净 HEAD 逐节点对比
  - 浏览器使用 `http://127.0.0.1:3030`，测试项目写入后按平台路径恢复
  - INDEX.md 登记、复盘、单一 commit、按版本工具推送
  - Verify：本 spec 新增失败 0；所有完成项有实际代码与证据