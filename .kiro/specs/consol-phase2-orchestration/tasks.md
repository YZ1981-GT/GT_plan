# 任务清单：consol-phase2-orchestration（合并模块 Phase 2 编排 + 接线 + 报表穿透）

> 关联设计：#[[file:.kiro/specs/consol-phase2-orchestration/design.md]]
> 关联需求：#[[file:.kiro/specs/consol-phase2-orchestration/requirements.md]]
> 前置：consol-phase0（B1/breakdown）+ consol-phase1（统一引擎/抵销 APPROVED/事件重算）完成。~2 人天。
> 任务约定：`[ ]` 未开始 / `[x]` 完成 / `[ ]*` 可选。铁律：编排单一入口 / A5 worker+SSE / feature flag 灰度 / router_registry 必查 / 改动后必 Playwright 实测。

---

## 阶段 0：基线核实

- [x] 0. 实证基线
  - [x] 0.1 readCode `generate_full_consol_notes`(V2, line 792) vs `generate_consol_notes_sync`(老版, line 745) 返回结构，确认契约一致性（S4 前提）
  - [x] 0.2 readCode consol_notes 路由 3 端点（确认调老版）+ 既有 reaggregate 端点
  - [x] 0.3 readCode `auto_generate_eliminations` 端点 + `calculate_elimination_amount`(4 规则) 现状，确认未接通
  - [x] 0.4 grep 既有散落 recalc 端点（worksheet recalc / trial recalculate / notes reaggregate）作编排者复用清单
  - [x] 0.5 确认既有 job/SSE 基础设施（import_job 式）可复用于 refresh-all
  - _需求：全部（基线）_ _铁律：彻底解决不绕开 / 触类旁通 grep_

---

## 阶段 1：cascade_refresh 编排者（A6/C2）

- [x] 1. consol_cascade_refresh_service
  - [x] 1.1 新建 `backend/app/services/consol_cascade_refresh_service.py`，实现 `refresh_all(db, parent_project_id, year, progress_cb=None) -> CascadeRefreshResult`
  - [x] 1.2 DAG 自底向上编排：build_tree → recalc_full → recalculate_trial → reconcile → generate_consol_reports → generate_full_consol_notes（复用既有 service 不重写）
  - [x] 1.3 失败隔离：每步 try/except 记 errors；关键步中断、下游步标部分成功继续
  - [x] 1.4 `CascadeRefreshResult` 数据类（nodes_refreshed/steps_completed/errors/duration_ms/reconciliation）
  - _需求：1.1~1.5_ _属性：S1/S2/S6_ _铁律：编排单一入口 DAG_

---

## 阶段 2：一键刷新端点 + worker + SSE（A5）

- [x] 2. refresh-all 端点 + 后台 worker
  - [x] 2.1 `POST /api/consolidation/{project_id}/{year}/refresh-all` 入队后台 worker 返回 job_id（不在请求线程跑，关联 R1）
  - [x] 2.2 worker 调 refresh_all(progress_cb=publish_sse)
  - [x] 2.3 SSE 进度端点推 `{step,total,current_node,status}`；SSE 用独立连接/Redis pub-sub（不占 asyncpg pool，关联 R5）
  - [x] 2.4 job 状态 GET 兜底查询（SSE 断开可查，关联 EH6）；worker 异常置 failed + SSE error（EH2）
  - [x] 2.5 端点挂现有 consolidation router 或 router_registry 登记（防 404）
  - _需求：2.1~2.4_ _铁律：A5 worker+SSE 不占连接 / router_registry 必查_

---

## 阶段 3：V2 附注接线（feature flag）

- [x] 3. CONSOL_NOTES_V2_ENABLED 灰度
  - [x] 3.1 新增开关 `CONSOL_NOTES_V2_ENABLED`（默认 False 老版）
  - [x] 3.2 consol_notes 路由 3 端点改：flag=true 调 `generate_full_consol_notes`(V2)，false 调 `generate_consol_notes_sync`(老版)
  - [x] 3.3 校验 V2 与老版返回结构契约一致（章节列表 schema，关联 S4）
  - [x] 3.4 V2 异常回退老版 + warning（不破坏可用性，关联 EH3/R2）
  - _需求：3.1~3.4_ _属性：S4_ _铁律：feature flag 灰度_

---

## 阶段 4：B3 自动抵销生成（draft）

- [x] 4. auto_generate_eliminations 接通
  - [x] 4.1 端点接通 `calculate_elimination_amount`（4 类规则），读子公司内部交易/往来
  - [x] 4.2 生成 EliminationEntry **强制 review_status=DRAFT**，不触发重算（关联 S3/ADR-203）
  - [x] 4.3 无匹配数据返回 0 不生成、不报错（关联 EH4）
  - [x] 4.4 草稿审批（→APPROVED）经 Phase 1 `ELIMINATION_APPROVED` 事件触发重算（依赖 Phase 1）
  - _需求：4.1~4.4_ _属性：S3_

---

## 阶段 5：报表穿透后端（衔接4）

- [x] 5. consol-breakdown 端点
  - [x] 5.1 `GET /api/consolidation/report/{project_id}/{year}/{account_code}/consol-breakdown` 返回各子公司金额+抵销+占比+合并数
  - [x] 5.2 复用 Phase 0 `consol_trial.consolidation_breakdown` + worksheet node_company_code 明细（不重算）
  - [x] 5.3 无 breakdown 返回空 by_company + "请先刷新合并数"（关联 EH5）
  - [x] 5.4 端点挂现有 consolidation router 或登记
  - _需求：5.1~5.4_ _属性：S5_ _铁律：router_registry 必查_

---

## 阶段 5B：cross_template 接线 + 公式管理 + 签字冻结 + 前端路径

- [x] 5C. cross_template 孤儿接线（需求 6）
  - [x] 5C.1 grep 确认 `consol_cross_template_service` 3 API 当前 0 router 引用
  - [x] 5C.2 V2 附注汇总路径（generate_full_consol_notes / reaggregate）内，template_type 不同时调 `translate_child_section`
  - [x] 5C.3 feature flag 受控（随 CONSOL_NOTES_V2_ENABLED 或独立开关）
  - [x] 5C.4 无匹配映射降级原样汇总 + warning（关联 EH7）
  - _需求：6.1~6.4_ _属性：S7_ _铁律：feature flag 灰度 / 消除孤儿_

- [x] 5D. 公式管理联动（需求 7）
  - [x] 5D.1 公式管理数据源树补"合并工作底稿"/"合并报表"节点
  - [x] 5D.2 合并公式审计纳入 formula_audit_log（module='consol'）
  - [x] 5D.3 合并公式求值复用 Phase 1 report_engine 安全解析器（保证展示=求值，前置依赖 Phase 1）
  - _需求：7.1~7.4_ _铁律：依赖 Phase 1 公式引擎统一_

- [x] 5E. P2 签字冻结（需求 8）
  - [x] 5E.1 readCode `create_snapshot` 确认当前只存 {created_at} 空壳
  - [x] 5E.2 序列化签字时刻 consol_trial/worksheet/report/notes 全量 + 哈希存 ConsolSnapshot（大数据 base64+gzip，关联 EH8）
  - [x] 5E.3 签字后锁定快照只读 + 还原"签字时合并数"对比
  - [x] 5E.4 快照创建写审计留痕（复用 Phase 0 log_consol_action）
  - _需求：8.1~8.4_ _属性：S8_

- [x] 5F. F3 前端补 V2/refresh-all 路径（需求 9）
  - [x] 5F.1 前端 `consolidation.notes` apiPaths 补 `reaggregate`/`refresh-all` 路径定义
  - [x] 5F.2 前端加"一键刷新全部"按钮 + "重新汇总附注"入口
  - [x] 5F.3 前端路径与 Phase 2 后端端点一一对应核对不遗漏
  - _需求：9.1~9.3_ _铁律：前后端必须联动_

---

## 阶段 6：测试

- [x] 6. PBT + 集成（hypothesis）
  - [x] 6.1 S1 DAG 顺序：mock service → steps_completed 顺序恒定
  - [x] 6.2 S2 失败隔离：随机某步抛错 → errors 记录 + 关键步中断/下游继续
  - [x] 6.3 S3 自动抵销仅 draft：生成 entry 全 DRAFT 不触发重算
  - [x] 6.4 S5 穿透自洽：Σ by_company amount == individual_sum
  - [x] 6.5 S6 一键刷新幂等：连续两次结果数值一致
  - [x] 6.6 S4 V2 灰度结构契约集成测试（V2/老版返回 schema 一致）
  - [x] 6.7 cross_template 接线：template_type 不同时章节翻译后汇总，无映射降级不丢章节（需求 6，S7）
  - [x] 6.8 P2 签字冻结：快照存真实数据 + 签字后还原"签字时合并数"（需求 8，S8）
  - _需求：1/3/4/5/6/8_ _属性：S1~S8_ _铁律：hypothesis 调速 10~15_

- [-] 7. Playwright 实测（脚本就绪，执行待 start-dev.bat 重启）
  - [ ] 7.1 一键刷新按钮 → SSE 进度条显示 → 完成
  - [ ] 7.2 V2 附注 flag 开启后前端"生成合并附注"表现
  - [ ] 7.3 F3 前端"一键刷新全部" + "重新汇总附注"入口调通后端（需求 9）
  - _需求：NFR-1.2_ _铁律：改动后必 Playwright 实测_
  - _状态：e2e 脚本已就绪 `audit-platform/frontend/e2e/consol-phase2-orchestration.spec.ts`（RUN_FULL_E2E 门控，3 用例覆盖 7.1/7.2/7.3）；**执行阻塞**=运行中后端为改动前进程，新路由 refresh-all / refresh-status / report consol-breakdown 实测均 404（FastAPI 不热加载 router 注册），需用户 `start-dev.bat` 重启后端（同时跑 D6 迁移）再 `set RUN_FULL_E2E=1 && set CONSOL_PROJECT_ID=<合并母项目> && npx playwright test e2e/consol-phase2-orchestration.spec.ts`；标"待环境"不伪绿_

- [ ] 8.* 真实数据 UAT（外部依赖，待数据）
  - [ ] 8.1* V2 附注消费真实子公司数据正确性 + 一键刷新真实集团端到端；显式标"待数据"不伪绿
  - [ ] 8.2* cross_template 真实国企↔上市映射替换 mock CSV（卡审计师 P-5）
  - _需求：NFR-1.3_ _阻塞：PG consolidated 项目 0 + 审计师真实映射_

---

## 阶段 7：收尾

- [-] 9. 文档与沉淀
  - [ ] 9.1 ADR-CONSOL-201~206 落地 `docs/adr/`（注册前查编号防冲突）
  - [ ] 9.2 更新 INDEX.md + memory Phase 2 完成记录
  - [ ] 9.3 单 commit（commit 前 git status 确认无其他 staged）
  - _铁律：单 commit / ADR 编号防冲突_

---

## 完成度判定口径

- **必需完成** = 任务 0~7 + 9（无星号，含阶段 5B 的 5C/5D/5E/5F）全绿。
- **可选/外部** = 任务 8（真实 UAT，卡 PG 合并数据 + cross_template 真实映射）。
- **判定铁律**：S1~S8 全绿 + 一键刷新 SSE 闭环 Playwright 实测 + V2 灰度结构契约通过 + cross_template 降级不丢章节（S7）+ P2 签字快照可还原（S8）+ 公式管理审计写入 formula_audit_log（需求 7 集成测试）+ F3 前端路径调通后端（需求 9 Playwright）；自动抵销只产 draft 验证；标 completed 必须代码+测试证据，真实 UAT 标"待数据"不伪绿。
